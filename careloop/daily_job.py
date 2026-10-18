"""AWS Lambda handler: every evening, write the family summary with Bedrock and send it via SNS.

Scheduled by EventBridge (see infra/template.yaml). Can also be run locally:
    python -m careloop.daily_job
"""
from __future__ import annotations

import json
import os

from . import notify
from .core import CareLoop
from .store import make_store


def handler(event=None, context=None):
    care = CareLoop(
        make_store(),
        user=os.getenv("CARELOOP_USER", "default"),
        person=os.getenv("CARELOOP_PERSON_NAME", "Amma"),
    )
    result = care.daily_summary_for_family((event or {}).get("day"))
    sent = notify.send(f"CareLoop: {care.person}'s day ({result['facts']['date']})", result["summary"])
    return {"sent": sent, "written_by": result["written_by"], "summary": result["summary"]}


if __name__ == "__main__":
    print(json.dumps(handler(), indent=2))
