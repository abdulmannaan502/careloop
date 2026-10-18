"""Turn the way people actually talk about medicine times into clock times.

"twice a day after meals", "morning and night", "8am and 8pm" -> ["09:00", "21:00"]
"""
from __future__ import annotations

import os
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("CARELOOP_TZ", "Asia/Kolkata"))

# Default clock times for common spoken phrases.
SLOTS = {
    "before breakfast": "07:30",
    "after breakfast": "09:00",
    "breakfast": "09:00",
    "morning": "08:00",
    "before lunch": "12:30",
    "after lunch": "14:00",
    "lunch": "14:00",
    "afternoon": "14:00",
    "evening": "18:00",
    "before dinner": "19:30",
    "after dinner": "21:00",
    "dinner": "21:00",
    "night": "21:30",
    "bedtime": "22:00",
    "bed": "22:00",
}

FREQUENCY = {
    "once": ["09:00"],
    "twice": ["09:00", "21:00"],
    "two times": ["09:00", "21:00"],
    "thrice": ["09:00", "14:00", "21:00"],
    "three times": ["09:00", "14:00", "21:00"],
    "four times": ["08:00", "13:00", "18:00", "22:00"],
}

# A dose counts as "on time" within this window of its scheduled slot.
ON_TIME_WINDOW = timedelta(minutes=int(os.getenv("CARELOOP_ON_TIME_MINUTES", "90")))

_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.I)


def now() -> datetime:
    """Current local time. CARELOOP_NOW=2026-10-18T09:10 pins it for demos/tests."""
    pinned = os.getenv("CARELOOP_NOW")
    if pinned:
        return datetime.fromisoformat(pinned).replace(tzinfo=TZ)
    return datetime.now(TZ)


def _fmt(h: int, m: int) -> str:
    return f"{h % 24:02d}:{m:02d}"


def parse_schedule(text: str) -> list[str]:
    """Return sorted HH:MM times for a spoken schedule."""
    t = text.lower().strip()
    times: set[str] = set()

    # Explicit clock times: "8am", "9:30 pm", "21:00"
    for match in _CLOCK.finditer(t):
        h_s, m_s, ampm = match.groups()
        preceded_by_at = t[max(0, match.start() - 3):match.start()].strip() == "at"
        # Bare numbers ("2 tablets") are not times unless written "at 8", "8pm" or "8:30".
        if not (ampm or m_s or preceded_by_at):
            continue
        h, m = int(h_s), int(m_s or 0)
        if ampm:
            ampm = ampm.replace(".", "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            if ampm == "am" and h == 12:
                h = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            times.add(_fmt(h, m))

    # Named slots, longest phrase first so "after breakfast" beats "breakfast".
    remaining = t
    for phrase in sorted(SLOTS, key=len, reverse=True):
        if phrase in remaining:
            times.add(SLOTS[phrase])
            remaining = remaining.replace(phrase, " ")

    # Frequency words ("twice a day after meals") when nothing more specific was said.
    if not times:
        for phrase, slot_times in FREQUENCY.items():
            if phrase in t:
                times.update(slot_times)
                break
        if "meal" in t and not times:
            times.update(FREQUENCY["thrice"])
        if "daily" in t or "every day" in t or "a day" in t:
            times = times or set(FREQUENCY["once"])

    return sorted(times) or ["09:00"]


def to_today(hhmm: str, ref: datetime | None = None) -> datetime:
    ref = ref or now()
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(ref.date(), time(h, m), tzinfo=TZ)


def parse_when(text: str | None, ref: datetime | None = None) -> datetime:
    """'just now', 'at 8', 'this morning', ISO strings -> datetime (defaults to now)."""
    ref = ref or now()
    if not text or text.strip().lower() in {"now", "just now", "right now"}:
        return ref
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
    except ValueError:
        pass
    slots = parse_schedule(text)
    return to_today(slots[0], ref)


def human_time(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"
