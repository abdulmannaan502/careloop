import os

import pytest

os.environ["CARELOOP_DISABLE_BEDROCK"] = "1"  # tests never call real AWS

from careloop.core import CareLoop  # noqa: E402
from careloop.store import SQLiteStore  # noqa: E402
from careloop.timeparse import parse_schedule  # noqa: E402


@pytest.fixture
def care(tmp_path, monkeypatch):
    monkeypatch.setenv("CARELOOP_NOW", "2026-10-18T09:10")
    c = CareLoop(SQLiteStore(str(tmp_path / "t.db")), person="Amma")
    c.add_medication("Amlodipine", "every morning", "5mg", purpose="blood pressure", pills_left=4)
    c.add_medication("Metformin", "twice a day after meals", "500mg", purpose="diabetes", pills_left=30)
    return c


def test_spoken_schedules():
    assert parse_schedule("twice a day after meals") == ["09:00", "21:00"]
    assert parse_schedule("8am and 8:30 pm") == ["08:00", "20:30"]
    assert parse_schedule("2 tablets daily") == ["09:00"]


def test_nickname_matching(care):
    r = care.log_dose_taken("my BP tablet")
    assert r["logged"] and r["dose"]["medication"] == "Amlodipine"
    r = care.log_dose_taken("sugar pill")
    assert r["logged"] and r["dose"]["medication"] == "Metformin"


def test_double_dose_guard(care):
    care.log_dose_taken("Amlodipine")
    r = care.log_dose_taken("Amlodipine")
    assert not r["logged"] and r["possible_double_dose"]
    r = care.log_dose_taken("Amlodipine", confirm_extra_dose=True)
    assert r["logged"] and r["dose"]["extra"]


def test_due_now_and_refill(care):
    due = care.whats_due_now()
    assert {d["medication"] for d in due["due_now"]} == {"Amlodipine", "Metformin"}
    care.log_dose_taken("Amlodipine")
    assert any(i["medication"] == "Amlodipine" for i in care.refill_alert()["low_stock"])


def test_urgent_symptom(care):
    r = care.log_symptom("I have chest pain")
    assert r["urgent"] and "112" in r["say"]


def test_recurring_symptom_and_family_summary(care, monkeypatch):
    monkeypatch.setenv("CARELOOP_NOW", "2026-10-17T10:00")
    care.log_symptom("feeling a bit dizzy")
    monkeypatch.setenv("CARELOOP_NOW", "2026-10-18T23:00")
    r = care.log_symptom("dizzy again")
    assert r["days_this_week"] == 2
    care.log_dose_taken("Amlodipine", when="2026-10-18T08:05")
    s = care.daily_summary_for_family()
    f = s["facts"]
    assert f["doses_scheduled"] == 3 and f["doses_taken_on_time"] == 1
    assert {m["medication"] for m in f["missed"]} == {"Metformin"}
    assert "dizzy" in f["recurring_symptoms"]
    assert s["written_by"] == "template" and "Metformin" in s["summary"]


def test_bedrock_path_used_when_configured(care, monkeypatch):
    import boto3

    calls = {}

    class FakeBedrock:
        def converse(self, **kw):
            calls.update(kw)
            return {"output": {"message": {"content": [{"text": "Amma had a calm day."}]}}}

    monkeypatch.delenv("CARELOOP_DISABLE_BEDROCK", raising=False)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeBedrock())
    s = care.daily_summary_for_family()
    assert s["written_by"] == "bedrock" and s["summary"] == "Amma had a calm day."
    assert calls["modelId"] == "amazon.nova-lite-v1:0" and "adherence_percent" in calls["messages"][0]["content"][0]["text"]
