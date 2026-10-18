"""A realistic past week for demos: a recurring dizzy spell, two missed night doses,
one very late BP tablet, and a BP refill running low."""
from __future__ import annotations

import os
from datetime import date, timedelta

from .core import CareLoop


def _at(d: date, hhmm: str) -> str:
    return f"{d.isoformat()}T{hhmm}"


def seed_week(care: CareLoop, today: date) -> None:
    saved = os.environ.get("CARELOOP_NOW")
    try:
        os.environ["CARELOOP_NOW"] = _at(today - timedelta(days=7), "07:00")
        care.add_medication("Amlodipine", "every morning", "5mg", purpose="blood pressure", pills_left=12)
        care.add_medication("Metformin", "twice a day after meals", "500mg", purpose="diabetes",
                            pills_left=40, instructions="after food")
        week = [
            (6, "08:05", "09:10", "21:05"),
            (5, "08:20", "09:30", "21:40"),
            (4, "08:00", "09:05", None),       # forgot the night dose
            (3, "10:45", "09:15", "21:10"),    # BP tablet very late
            (2, "08:10", "09:00", None),       # forgot again
            (1, "08:00", "09:20", "21:15"),
        ]
        for days_ago, amlo, met_am, met_pm in week:
            d = today - timedelta(days=days_ago)
            for med, t in (("Amlodipine", amlo), ("Metformin", met_am), ("Metformin", met_pm)):
                if t:
                    os.environ["CARELOOP_NOW"] = _at(d, t)
                    care.log_dose_taken(med)
        for days_ago, text in ((4, "feeling dizzy after lunch"), (2, "a bit dizzy when I stand up")):
            os.environ["CARELOOP_NOW"] = _at(today - timedelta(days=days_ago), "15:00")
            care.log_symptom(text)
    finally:
        if saved is None:
            os.environ.pop("CARELOOP_NOW", None)
        else:
            os.environ["CARELOOP_NOW"] = saved
