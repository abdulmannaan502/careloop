"""CareLoop care logic, independent of MCP so it is easy to test.

Every public method returns a dict with a short "say" field (what a voice assistant
should speak back) plus structured data for anything else that wants it.
"""
from __future__ import annotations

import difflib
import os
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from . import notify
from . import timeparse as tp
from .store import Store
from .summary import write_family_summary

# Everyday nicknames people use for their medicines.
NICKNAMES = {
    "bp": ["blood pressure", "hypertension", "bp"],
    "pressure": ["blood pressure", "hypertension"],
    "sugar": ["diabetes", "sugar", "glucose"],
    "diabetes": ["diabetes", "sugar"],
    "thyroid": ["thyroid"],
    "cholesterol": ["cholesterol"],
    "heart": ["heart", "cardiac"],
    "vitamin": ["vitamin", "supplement"],
    "pain": ["pain"],
    "sleep": ["sleep"],
}

# Phrases that must never be treated as a routine log entry.
URGENT_SIGNS = [
    "chest pain", "can't breathe", "cannot breathe", "trouble breathing", "short of breath",
    "fainted", "passed out", "unconscious", "face drooping", "slurred", "can't move",
    "cannot move", "numb on one side", "severe bleeding", "fell and can't get up", "fell down",
]

SYMPTOM_KEYS = [
    "dizzy", "dizziness", "headache", "tired", "fatigue", "weak", "nausea", "vomit",
    "breathless", "chest", "fever", "cough", "cold", "back pain", "knee pain", "joint pain",
    "stomach", "sleep", "anxious", "swelling", "pain",
]

EMERGENCY_NUMBER = os.getenv("CARELOOP_EMERGENCY_NUMBER", "112")


def _symptom_key(text: str) -> str:
    t = text.lower()
    for key in SYMPTOM_KEYS:
        if key in t:
            return {"dizziness": "dizzy", "fatigue": "tired", "vomit": "nausea"}.get(key, key)
    return re.sub(r"\b(i am|i'm|feeling|feel|a bit|a little|today|very|so)\b", "", t).strip(" .,")


def _guess_severity(text: str) -> int:
    t = text.lower()
    if any(s in t for s in URGENT_SIGNS):
        return 5
    if any(w in t for w in ["very", "really bad", "terrible", "severe", "a lot"]):
        return 4
    if any(w in t for w in ["slight", "little", "bit", "mild"]):
        return 1
    return 2


class CareLoop:
    def __init__(self, store: Store, user: str = "default", person: str = "Amma"):
        self.store = store
        self.user = user
        self.person = person

    # ---------- medications ----------
    def _meds(self) -> list[dict[str, Any]]:
        return sorted(self.store.list_medications(self.user), key=lambda m: m["name"].lower())

    def _find_med(self, spoken: str) -> dict[str, Any] | None:
        meds = self._meds()
        if not meds:
            return None
        s = spoken.lower()
        s = re.sub(r"\b(my|the|tablet|tablets|pill|pills|medicine|medicines|dose|capsule)\b", " ", s).strip()
        # 1. Name contained in what was said, or the reverse.
        for m in meds:
            n = m["name"].lower()
            if n in s or (s and s in n):
                return m
        # 2. Purpose or nickname ("my BP tablet" -> purpose "blood pressure").
        for word, aliases in NICKNAMES.items():
            if re.search(rf"\b{word}\b", s):
                for m in meds:
                    purpose = (m.get("purpose") or "").lower()
                    if any(a in purpose for a in aliases):
                        return m
        for m in meds:
            purpose = (m.get("purpose") or "").lower()
            if purpose and (purpose in s or s in purpose):
                return m
        # 3. Fuzzy spelling ("metforming").
        names = {m["name"].lower(): m for m in meds}
        close = difflib.get_close_matches(s, names.keys(), n=1, cutoff=0.6)
        return names[close[0]] if close else None

    def add_medication(
        self,
        name: str,
        schedule: str,
        dosage: str = "",
        purpose: str = "",
        pills_left: int | None = None,
        pills_per_dose: int = 1,
        instructions: str = "",
    ) -> dict[str, Any]:
        times = tp.parse_schedule(schedule)
        existing = self._find_med(name)
        med_id = existing["id"] if existing and existing["name"].lower() == name.lower() else uuid.uuid4().hex[:8]
        med = {
            "id": med_id,
            "name": name.strip(),
            "dosage": dosage,
            "purpose": purpose,
            "times": times,
            "schedule_text": schedule,
            "pills_left": pills_left,
            "pills_per_dose": max(1, pills_per_dose),
            "instructions": instructions,
            # Days before a medicine was added must not count as missed doses.
            "added_at": (existing or {}).get("added_at") or tp.now().isoformat(),
        }
        self.store.put_medication(self.user, med)
        spoken_times = " and ".join(tp.human_time(t) for t in times)
        extra = f" {dosage}" if dosage else ""
        say = f"Okay. I've added {name}{extra} at {spoken_times}."
        if pills_left is not None:
            say += f" You have {pills_left} left."
        return {"say": say, "medication": med, "updated": bool(existing and existing["id"] == med_id)}

    def remove_medication(self, name: str) -> dict[str, Any]:
        med = self._find_med(name)
        if not med:
            return {"say": f"I couldn't find a medicine called {name}.", "removed": False}
        self.store.delete_medication(self.user, med["id"])
        return {"say": f"I've removed {med['name']} from the schedule.", "removed": True}

    def list_medications(self) -> dict[str, Any]:
        meds = self._meds()
        if not meds:
            return {"say": "There are no medicines on the schedule yet.", "medications": []}
        lines = [
            f"{m['name']}{(' ' + m['dosage']) if m['dosage'] else ''} at "
            + " and ".join(tp.human_time(t) for t in m["times"])
            for m in meds
        ]
        return {"say": "Your medicines: " + "; ".join(lines) + ".", "medications": meds}

    # ---------- doses ----------
    def _day_bounds(self, day: date) -> tuple[str, str]:
        start = datetime.combine(day, datetime.min.time(), tzinfo=tp.TZ)
        return start.isoformat(), (start + timedelta(days=1)).isoformat()

    def _doses_on(self, day: date) -> list[dict[str, Any]]:
        return self.store.events_between(self.user, "dose", *self._day_bounds(day))

    def log_dose_taken(self, medication: str, when: str | None = None, confirm_extra_dose: bool = False) -> dict[str, Any]:
        med = self._find_med(medication)
        if not med:
            names = ", ".join(m["name"] for m in self._meds()) or "none yet"
            return {
                "say": f"I'm not sure which medicine you mean by '{medication}'. Your medicines are: {names}.",
                "logged": False,
            }
        taken_at = tp.parse_when(when)
        taken_today = {d["slot"] for d in self._doses_on(taken_at.date()) if d["med_id"] == med["id"]}
        open_slots = [t for t in med["times"] if t not in taken_today]

        if not open_slots and not confirm_extra_dose:
            return {
                "say": (
                    f"You've already taken all of today's {med['name']}. "
                    "Please don't take another dose unless your doctor told you to. "
                    "If you did take an extra one, tell me and I'll note it for your family."
                ),
                "logged": False,
                "possible_double_dose": True,
            }

        # Match the dose to the nearest scheduled slot that is still open.
        candidates = open_slots or med["times"]
        slot = min(candidates, key=lambda t: abs((tp.to_today(t, taken_at) - taken_at).total_seconds()))
        delay = round((taken_at - tp.to_today(slot, taken_at)).total_seconds() / 60)
        on_time = abs(delay) <= tp.ON_TIME_WINDOW.total_seconds() / 60 and bool(open_slots)

        dose = {
            "id": uuid.uuid4().hex[:8],
            "med_id": med["id"],
            "medication": med["name"],
            "slot": slot if open_slots else f"extra-{taken_at:%H:%M}",
            "taken_at": taken_at.isoformat(),
            "delay_minutes": delay,
            "on_time": on_time,
            "extra": not open_slots,
        }
        self.store.add_event(self.user, "dose", dose["taken_at"], dose)

        if med.get("pills_left") is not None:
            med["pills_left"] = max(0, med["pills_left"] - med.get("pills_per_dose", 1))
            self.store.put_medication(self.user, med)

        if not open_slots:
            say = f"Noted. I've recorded an extra dose of {med['name']} and your family will see it in today's update."
        elif on_time:
            say = f"Got it. {med['name']} for {tp.human_time(slot)} is done. Well done!"
        elif delay > 0:
            say = f"Got it, {med['name']} logged. It was due at {tp.human_time(slot)}, so a little late, but that's okay."
        else:
            say = f"Got it, {med['name']} logged a little early for the {tp.human_time(slot)} dose."

        remaining = [t for t in open_slots if t != slot]
        if remaining:
            say += f" Next {med['name']} is at {tp.human_time(remaining[0])}."
        low = self._days_left(med)
        if low is not None and low <= 3:
            say += f" You only have about {low} days of {med['name']} left, so it's time to get a refill."
        return {"say": say, "logged": True, "dose": dose}

    def whats_due_now(self) -> dict[str, Any]:
        now = tp.now()
        window = tp.ON_TIME_WINDOW
        taken = defaultdict(set)
        for d in self._doses_on(now.date()):
            taken[d["med_id"]].add(d["slot"])

        due, overdue, upcoming, done = [], [], [], []
        for m in self._meds():
            for t in m["times"]:
                slot_dt = tp.to_today(t, now)
                item = {"medication": m["name"], "dosage": m["dosage"], "time": t, "instructions": m["instructions"]}
                if t in taken[m["id"]]:
                    done.append(item)
                elif slot_dt - window <= now <= slot_dt + window:
                    due.append(item)
                elif now > slot_dt + window:
                    overdue.append(item)
                else:
                    upcoming.append(item)

        def fmt(items):
            return ", ".join(
                f"{i['medication']}{(' ' + i['dosage']) if i['dosage'] else ''}"
                f"{(' (' + i['instructions'] + ')') if i['instructions'] else ''}"
                for i in items
            )

        parts = []
        if due:
            parts.append(f"Right now, please take: {fmt(due)}.")
        if overdue:
            parts.append(
                f"You haven't logged {fmt(overdue)} from earlier today. "
                "If you missed it, check the packet or ask your doctor before doubling up."
            )
        if not due and not overdue:
            parts.append("Nothing is due right now.")
        if upcoming:
            nxt = min(upcoming, key=lambda i: i["time"])
            parts.append(f"Next is {nxt['medication']} at {tp.human_time(nxt['time'])}.")
        elif not due and not overdue and done:
            parts.append("You've taken everything for today.")
        return {"say": " ".join(parts), "due_now": due, "overdue": overdue, "upcoming": upcoming, "taken": done}

    # ---------- symptoms ----------
    def log_symptom(self, description: str, severity: int | None = None) -> dict[str, Any]:
        sev = severity if severity is not None else _guess_severity(description)
        sev = min(5, max(1, int(sev)))
        urgent = any(s in description.lower() for s in URGENT_SIGNS)
        now = tp.now()
        entry = {
            "id": uuid.uuid4().hex[:8],
            "description": description.strip(),
            "key": _symptom_key(description),
            "severity": 5 if urgent else sev,
            "urgent": urgent,
            "logged_at": now.isoformat(),
        }
        self.store.add_event(self.user, "symptom", entry["logged_at"], entry)

        if urgent:
            alerted = notify.send(
                f"URGENT: {self.person} reported a warning sign",
                f"{self.person} just told CareLoop: \"{entry['description']}\" at {now:%I:%M %p}. "
                f"They were advised to call {EMERGENCY_NUMBER}. Please call them now.",
            )
            family = "I've also alerted your family." if alerted else "I've marked this as urgent for your family."
            return {
                "say": (
                    f"This could be serious. Please call {EMERGENCY_NUMBER} for emergency help right now, "
                    f"or ask someone nearby to help you. {family}"
                ),
                "symptom": entry,
                "urgent": True,
                "family_alerted": alerted,
            }
        recent = self._symptom_days(entry["key"], now.date(), days=7)
        say = f"I've noted that you're feeling {entry['key'] if len(entry['key']) < 25 else 'unwell'}."
        if len(recent) >= 2:
            say += (
                f" You've mentioned this on {len(recent)} days this week. "
                "I'll let your family know, and it may be worth telling your doctor."
            )
        elif entry["severity"] >= 4:
            say += " That sounds uncomfortable. I'll include it in today's update for your family."
        else:
            say += " Please rest and drink some water. Tell me if it gets worse."
        return {"say": say, "symptom": entry, "urgent": False, "days_this_week": len(recent)}

    def _symptoms_between(self, start: date, end_exclusive: date) -> list[dict[str, Any]]:
        s = datetime.combine(start, datetime.min.time(), tzinfo=tp.TZ).isoformat()
        e = datetime.combine(end_exclusive, datetime.min.time(), tzinfo=tp.TZ).isoformat()
        return self.store.events_between(self.user, "symptom", s, e)

    def _symptom_days(self, key: str, today: date, days: int = 7) -> set[str]:
        items = self._symptoms_between(today - timedelta(days=days - 1), today + timedelta(days=1))
        return {i["logged_at"][:10] for i in items if i.get("key") == key}

    # ---------- refills ----------
    def _days_left(self, med: dict[str, Any]) -> int | None:
        if med.get("pills_left") is None:
            return None
        per_day = med.get("pills_per_dose", 1) * max(1, len(med["times"]))
        return med["pills_left"] // per_day

    def refill_alert(self, days_threshold: int = 5) -> dict[str, Any]:
        low = []
        for m in self._meds():
            d = self._days_left(m)
            if d is not None and d <= days_threshold:
                low.append({"medication": m["name"], "pills_left": m["pills_left"], "days_left": d})
        if not low:
            return {"say": "All your medicines have enough stock for now.", "low_stock": []}
        items = "; ".join(f"{i['medication']}, about {i['days_left']} days left" for i in low)
        return {"say": f"Time to refill: {items}.", "low_stock": low}

    # ---------- reporting ----------
    def _day_facts(self, day: date) -> dict[str, Any]:
        now = tp.now()
        doses = self._doses_on(day)
        taken_slots = {(d["med_id"], d["slot"]) for d in doses}
        scheduled, missed = 0, []
        for m in self._meds():
            added = datetime.fromisoformat(m["added_at"]) if m.get("added_at") else None
            for t in m["times"]:
                slot_dt = datetime.combine(day, datetime.strptime(t, "%H:%M").time(), tzinfo=tp.TZ)
                if added and slot_dt + tp.ON_TIME_WINDOW < added and (m["id"], t) not in taken_slots:
                    continue  # not on the schedule yet
                if (m["id"], t) in taken_slots:
                    scheduled += 1
                elif slot_dt + tp.ON_TIME_WINDOW < now:
                    scheduled += 1
                    missed.append({"medication": m["name"], "time": tp.human_time(t)})
        on_time = sum(1 for d in doses if d["on_time"])
        late = [
            {"medication": d["medication"], "minutes_late": d["delay_minutes"]}
            for d in doses
            if not d["on_time"] and not d.get("extra")
        ]
        extra = [d["medication"] for d in doses if d.get("extra")]
        return {
            "date": day.isoformat(),
            "doses_scheduled": scheduled,
            "doses_taken_on_time": on_time,
            "doses_taken_late": late,
            "extra_doses": extra,
            "missed": missed,
            "adherence_percent": round(100 * on_time / scheduled) if scheduled else 100,
        }

    def adherence_report(self, days: int = 7) -> dict[str, Any]:
        today = tp.now().date()
        series = [self._day_facts(today - timedelta(days=i)) for i in reversed(range(max(1, min(days, 30))))]
        sched = sum(d["doses_scheduled"] for d in series)
        ontime = sum(d["doses_taken_on_time"] for d in series)
        pct = round(100 * ontime / sched) if sched else 100
        worst = min(series, key=lambda d: d["adherence_percent"])
        say = f"Over the last {len(series)} days, {pct}% of doses were taken on time."
        if worst["adherence_percent"] < 100 and sched:
            say += f" The hardest day was {datetime.fromisoformat(worst['date']):%A}."
        return {"say": say, "adherence_percent": pct, "days": series}

    def daily_summary_for_family(self, day: str | None = None) -> dict[str, Any]:
        d = date.fromisoformat(day) if day else tp.now().date()
        facts = self._day_facts(d)
        symptoms_today = self._symptoms_between(d, d + timedelta(days=1))
        week = self._symptoms_between(d - timedelta(days=6), d + timedelta(days=1))
        by_key = defaultdict(set)
        for s in week:
            by_key[s["key"]].add(s["logged_at"][:10])
        recurring = sorted(k for k, v in by_key.items() if len(v) >= 2)
        facts.update(
            {
                "person": self.person,
                "symptoms_today": [
                    {"description": s["description"], "severity": s["severity"], "urgent": s.get("urgent", False)}
                    for s in symptoms_today
                ],
                "recurring_symptoms": recurring,
                "low_stock": self.refill_alert()["low_stock"],
            }
        )
        text, source = write_family_summary(facts)
        return {"say": text, "summary": text, "written_by": source, "facts": facts}
