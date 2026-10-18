"""Fill the store with a realistic past week, so the family summary and adherence
report have history to talk about in the demo (a recurring dizzy spell, a few missed
evening doses, a refill running low).

    CARELOOP_DB=demo.db python scripts/seed_demo_week.py
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from careloop.core import CareLoop  # noqa: E402
from careloop.store import make_store  # noqa: E402

today = date.fromisoformat(os.getenv("SEED_TODAY", date.today().isoformat()))


def at(d: date, hhmm: str) -> str:
    return f"{d.isoformat()}T{hhmm}"


care = CareLoop(make_store(), person=os.getenv("CARELOOP_PERSON_NAME", "Amma"))

os.environ["CARELOOP_NOW"] = at(today - timedelta(days=7), "07:00")
care.add_medication("Amlodipine", "every morning", "5mg", purpose="blood pressure", pills_left=12)
care.add_medication("Metformin", "twice a day after meals", "500mg", purpose="diabetes", pills_left=40,
                    instructions="after food")

# (days ago, Amlodipine time or None, Metformin morning, Metformin night)
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
            os.environ["CARELOOP_NOW"] = at(d, t)
            care.log_dose_taken(med)

for days_ago, text in ((4, "feeling dizzy after lunch"), (2, "a bit dizzy when I stand up")):
    os.environ["CARELOOP_NOW"] = at(today - timedelta(days=days_ago), "15:00")
    care.log_symptom(text)

print(f"Seeded 6 days of history ending {today - timedelta(days=1)} into {care.store.backend}.")
