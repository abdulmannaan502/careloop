"""Fill the store with a realistic past week so the family summary and adherence
report have history to talk about in the demo.

    CARELOOP_DB=demo.db python scripts/seed_demo_week.py
"""
from __future__ import annotations

import os
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from careloop.core import CareLoop  # noqa: E402
from careloop.demo_data import seed_week  # noqa: E402
from careloop.store import make_store  # noqa: E402

today = date.fromisoformat(os.getenv("SEED_TODAY", date.today().isoformat()))
care = CareLoop(make_store(), person=os.getenv("CARELOOP_PERSON_NAME", "Amma"))
seed_week(care, today)
print(f"Seeded 6 days of history ending {today - timedelta(days=1)} into {care.store.backend}.")
