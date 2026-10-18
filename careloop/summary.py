"""Family summaries written by Amazon Bedrock, with a rule-based fallback.

The server always computes the facts itself (doses, misses, symptoms, refills).
Bedrock only turns those facts into a short, calm message a family member can read
on their phone. If Bedrock is not configured or fails, a template does the same job,
so the demo never breaks.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("careloop.summary")

SYSTEM_PROMPT = """You write a short daily update for the family of an older adult, based ONLY on the JSON facts given.
Rules:
- 4 to 6 short sentences, warm and calm, plain language, no medical jargon.
- Start with how the day went overall (use the adherence percentage).
- Name any missed doses by medicine and time.
- Mention symptoms with their severity. If a symptom repeats across days or severity is 4-5, gently suggest a call or a doctor visit.
- Mention refills that are running low.
- Never diagnose, never invent facts, never change medication advice.
- End with one kind, practical suggestion for the family (for example, a phone call)."""


def _bedrock_summary(facts: dict[str, Any]) -> str | None:
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id or os.getenv("CARELOOP_DISABLE_BEDROCK") == "1":
        return None
    try:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        resp = client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": json.dumps(facts, indent=2)}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.3},
        )
        return resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:  # network, permissions, throttling: fall back, never crash the tool
        log.warning("Bedrock summary failed, using template: %s", exc)
        return None


def _template_summary(f: dict[str, Any]) -> str:
    name = f["person"]
    parts: list[str] = []
    urgent = [s["description"] for s in f["symptoms_today"] if s.get("urgent")]
    if urgent:
        parts.append(f"IMPORTANT: today {name} reported a warning sign ({'; '.join(urgent)}). Please call them now.")
    pct = f["adherence_percent"]
    if f["doses_scheduled"] == 0:
        parts.append(f"{name} has no medicines scheduled today.")
    elif pct >= 90:
        parts.append(f"Good day for {name}: {f['doses_taken_on_time']} of {f['doses_scheduled']} doses taken on time ({pct}%).")
    elif pct >= 60:
        parts.append(f"Mostly on track for {name}: {f['doses_taken_on_time']} of {f['doses_scheduled']} doses on time ({pct}%).")
    else:
        parts.append(f"{name} had a harder day with medicines: only {f['doses_taken_on_time']} of {f['doses_scheduled']} doses on time ({pct}%).")

    if f["missed"]:
        missed = ", ".join(f"{m['medication']} ({m['time']})" for m in f["missed"])
        parts.append(f"Missed: {missed}.")
    if f["symptoms_today"]:
        sym = "; ".join(f"{s['description']} (severity {s['severity']}/5)" for s in f["symptoms_today"])
        parts.append(f"{name} mentioned: {sym}.")
    if f["recurring_symptoms"]:
        parts.append(
            "This has come up on more than one day recently: "
            + ", ".join(f["recurring_symptoms"])
            + ". It may be worth a call, or a word with their doctor."
        )
    if f["low_stock"]:
        low = ", ".join(f"{m['medication']} (~{m['days_left']} days left)" for m in f["low_stock"])
        parts.append(f"Running low: {low}.")
    if f["missed"] or f["recurring_symptoms"]:
        parts.append(f"A quick phone call to {name} this evening would help.")
    else:
        parts.append(f"No action needed today. Maybe just call {name} to say hello.")
    return " ".join(parts)


def write_family_summary(facts: dict[str, Any]) -> tuple[str, str]:
    """Return (summary_text, source) where source is 'bedrock' or 'template'."""
    text = _bedrock_summary(facts)
    if text:
        return text, "bedrock"
    return _template_summary(facts), "template"
