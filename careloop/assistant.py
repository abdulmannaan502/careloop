"""A stand-in for Alexa+ used by the web demo: turns an utterance into MCP tool calls.

Two modes:
  * Bedrock agent (BEDROCK_MODEL_ID set): the model sees the MCP server's tool list and
    picks tools itself, exactly the role Alexa+ plays.
  * Rule-based router (default): simple patterns, so the demo runs with no cloud account.

Either way, every call goes through a real MCP client session to the CareLoop server.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from mcp.client.client import Client


@dataclass
class Turn:
    reply: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "rules"


def _payload(result) -> dict[str, Any]:
    if result.structured_content:
        data = result.structured_content
        return data.get("result", data)
    return json.loads(result.content[0].text)


# ---------------- rule-based router ----------------
_ADD = re.compile(
    r"(?:add|doctor (?:gave|prescribed)(?: me)?|started|new medicine)\s+(?:my\s+)?"
    r"(?P<name>[A-Za-z][A-Za-z-]+)\s*(?P<dose>\d+\s*(?:mg|mcg|ml|g)?)?"
    r"(?:\s+for\s+(?P<purpose>[a-z ]+?))?[,.]?\s+(?P<sched>(?:every|once|twice|thrice|three|four|in the|at|morning|after|before|daily|night).*?)"
    r"(?:[.,]\s*(?:i have\s+)?(?P<left>\d+)\s*(?:tablets|pills|left)?.*)?$",
    re.I,
)


def route(text: str) -> tuple[str, dict[str, Any]]:
    t = text.lower().strip()
    if m := _ADD.search(text):
        args: dict[str, Any] = {"name": m["name"].capitalize(), "schedule": m["sched"].strip(" .")}
        if m["dose"]:
            d = m["dose"].replace(" ", "")
            args["dosage"] = d if not d.isdigit() else d + "mg"
        if m["purpose"]:
            args["purpose"] = m["purpose"].strip()
        if m["left"]:
            args["pills_left"] = int(m["left"])
        return "add_medication", args
    if re.search(r"\b(stop|stopped|remove)\b", t):
        name = re.sub(r".*\b(stop|stopped|remove)\b\s*(taking\s+)?(my\s+)?", "", t).strip(" .")
        return "remove_medication", {"name": name}
    if re.search(r"\b(took|taken|had my|have taken)\b", t):
        med = re.sub(r".*\b(took|taken|had|have taken)\b\s*", "", t).strip(" .!")
        extra = bool(re.search(r"\b(yes|really|extra|by mistake)\b", t))
        return "log_dose_taken", {"medication": med or t, "confirm_extra_dose": extra}
    if re.search(r"how (is|was|has) .*(doing|day|been)|family update|summary", t):
        return "daily_summary_for_family", {}
    if re.search(r"this week|adherence|how have i been|how am i doing", t):
        return "adherence_report", {"days": 7}
    if re.search(r"\b(refill|buy|run(ning)? out|stock)\b", t):
        return "refill_alert", {}
    if re.search(r"\b(what|which|any)\b.*\b(take|due|medicine|tablet)\b|\bdue\b", t):
        return "whats_due_now", {}
    if re.search(r"\b(list|my medicines|schedule)\b", t):
        return "list_medications", {}
    return "log_symptom", {"description": text.strip()}


# ---------------- Bedrock agent ----------------
SYSTEM = (
    "You are the voice assistant in an older person's home, using the CareLoop tools. "
    "Call the right tool for what they said, then reply with the tool's `say` text, lightly smoothed for speech. "
    "Keep replies short and warm. Never give medical advice beyond what tools return."
)


async def _bedrock_turn(client: Client, text: str, history: list[dict]) -> Turn:
    import boto3

    tools = (await client.list_tools()).tools
    tool_cfg = {
        "tools": [
            {"toolSpec": {"name": t.name, "description": t.description or "", "inputSchema": {"json": t.input_schema}}}
            for t in tools
        ]
    }
    br = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    messages = history[-6:] + [{"role": "user", "content": [{"text": text}]}]
    calls = []
    for _ in range(4):
        resp = br.converse(
            modelId=os.environ["BEDROCK_MODEL_ID"],
            system=[{"text": SYSTEM}],
            messages=messages,
            toolConfig=tool_cfg,
            inferenceConfig={"maxTokens": 400, "temperature": 0.2},
        )
        msg = resp["output"]["message"]
        messages.append(msg)
        uses = [c["toolUse"] for c in msg["content"] if "toolUse" in c]
        if not uses:
            reply = " ".join(c.get("text", "") for c in msg["content"]).strip()
            return Turn(reply, calls, "bedrock")
        results = []
        for u in uses:
            data = _payload(await client.call_tool(u["name"], u["input"]))
            calls.append({"tool": u["name"], "args": u["input"], "result": data})
            results.append({"toolResult": {"toolUseId": u["toolUseId"], "content": [{"json": data}]}})
        messages.append({"role": "user", "content": results})
    return Turn(calls[-1]["result"]["say"] if calls else "Sorry, I didn't catch that.", calls, "bedrock")


async def handle(client: Client, text: str, history: list[dict] | None = None) -> Turn:
    if os.getenv("BEDROCK_MODEL_ID") and os.getenv("CARELOOP_DISABLE_BEDROCK") != "1":
        try:
            return await _bedrock_turn(client, text, history or [])
        except Exception:
            pass  # fall back to rules so the demo never stalls
    tool, args = route(text)
    data = _payload(await client.call_tool(tool, args))
    return Turn(data["say"], [{"tool": tool, "args": args, "result": data}], "rules")
