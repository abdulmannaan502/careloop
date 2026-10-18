"""CareLoop MCP server (Streamable HTTP).

Run locally:   python -m careloop.server            -> http://localhost:8000/mcp
Health check:  GET /health
"""
from __future__ import annotations

import logging
import os
from typing import Annotated

from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import LATEST_PROTOCOL_VERSION, ToolAnnotations

from .core import CareLoop
from .store import make_store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

INSTRUCTIONS = """CareLoop helps an older adult manage their medicines and health by voice, and keeps their family informed.
Use it when the person talks about: taking a tablet or medicine, what medicine is due, adding or stopping a medicine,
how they are feeling (symptoms), running out of medicine, or when the family asks how their parent is doing.
Every tool returns a short `say` field written for speaking aloud: read it back to the person, in a warm, simple way.
If log_symptom returns urgent=true, read the emergency instruction first and do not add anything that delays it.
Never give medical advice beyond what the tools return."""

care = CareLoop(
    make_store(),
    user=os.getenv("CARELOOP_USER", "default"),
    person=os.getenv("CARELOOP_PERSON_NAME", "Amma"),
)

mcp = MCPServer(
    name="careloop",
    title="CareLoop: medication and wellbeing companion",
    instructions=INSTRUCTIONS,
    version="1.0.0",
    website_url="https://github.com/",
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


@mcp.tool(
    title="Add a medicine",
    annotations=WRITE,
    description=(
        "Add or update a medicine on the person's schedule. Use when they say things like "
        "'add my sugar tablet twice a day after meals' or 'the doctor gave me Amlodipine 5mg every morning'. "
        "Pass the schedule exactly as spoken; CareLoop converts it to clock times."
    ),
)
def add_medication(
    name: Annotated[str, Field(description="Medicine name, e.g. 'Metformin' or 'Amlodipine'")],
    schedule: Annotated[str, Field(description="When to take it, as spoken: 'twice a day after meals', 'morning and night', '8am'")],
    dosage: Annotated[str, Field(description="Strength or amount, e.g. '500mg' or '1 tablet'")] = "",
    purpose: Annotated[str, Field(description="What it's for, e.g. 'blood pressure', 'diabetes'. Lets the person say 'my BP tablet'.")] = "",
    pills_left: Annotated[int | None, Field(description="How many tablets are in the strip or bottle now", ge=0)] = None,
    pills_per_dose: Annotated[int, Field(description="Tablets per dose", ge=1)] = 1,
    instructions: Annotated[str, Field(description="Short note like 'after food' or 'with water'")] = "",
) -> dict:
    return care.add_medication(name, schedule, dosage, purpose, pills_left, pills_per_dose, instructions)


@mcp.tool(
    title="Log a dose taken",
    annotations=WRITE,
    description=(
        "Record that the person took a medicine. Use for 'I took my BP tablet', 'had my morning pills', "
        "'took Metformin at 8'. The medicine can be named loosely (by name, nickname or purpose). "
        "If the result has possible_double_dose=true, read the warning; only call again with "
        "confirm_extra_dose=true if the person says they really did take an extra dose."
    ),
)
def log_dose_taken(
    medication: Annotated[str, Field(description="What the person called it: 'BP tablet', 'sugar pill', 'Metformin'")],
    when: Annotated[str | None, Field(description="When it was taken if not just now: 'at 8', 'this morning', ISO time")] = None,
    confirm_extra_dose: Annotated[bool, Field(description="True only after the person confirms they took an extra dose")] = False,
) -> dict:
    return care.log_dose_taken(medication, when, confirm_extra_dose)


@mcp.tool(
    title="What's due now",
    annotations=READ,
    description="Tell the person which medicines to take right now, which were missed earlier today, and what's next. Use for 'what do I need to take?', 'any medicine now?'.",
)
def whats_due_now() -> dict:
    return care.whats_due_now()


@mcp.tool(
    title="Log how I feel",
    annotations=WRITE,
    description=(
        "Record a symptom or how the person is feeling: 'I'm feeling dizzy', 'bad headache today', 'knees hurt'. "
        "Detects emergency warning signs and repeated symptoms. If urgent=true, read the emergency instruction immediately."
    ),
)
def log_symptom(
    description: Annotated[str, Field(description="The symptom in the person's own words")],
    severity: Annotated[int | None, Field(description="1 (mild) to 5 (severe), if the person said how bad it is", ge=1, le=5)] = None,
) -> dict:
    return care.log_symptom(description, severity)


@mcp.tool(
    title="Refill check",
    annotations=READ,
    description="List medicines that are running low. Use for 'do I need to buy medicines?' or proactively after logging doses.",
)
def refill_alert(
    days_threshold: Annotated[int, Field(description="Warn when fewer than this many days of tablets remain", ge=1, le=30)] = 5,
) -> dict:
    return care.refill_alert(days_threshold)


@mcp.tool(
    title="Family update",
    annotations=READ,
    description=(
        "Write today's plain-language update for the family: doses taken and missed, symptoms, refills, "
        "and anything worth a phone call. Use when a family member asks 'how is Amma doing today?'."
    ),
)
def daily_summary_for_family(
    day: Annotated[str | None, Field(description="Date as YYYY-MM-DD; defaults to today")] = None,
) -> dict:
    return care.daily_summary_for_family(day)


@mcp.tool(
    title="Adherence report",
    annotations=READ,
    description="Percentage of doses taken on time over recent days. Use for 'how have I been doing this week?' or doctor visits.",
)
def adherence_report(
    days: Annotated[int, Field(description="Number of days to look back", ge=1, le=30)] = 7,
) -> dict:
    return care.adherence_report(days)


@mcp.tool(title="List medicines", annotations=READ, description="Read out the person's current medicine schedule.")
def list_medications() -> dict:
    return care.list_medications()


@mcp.tool(
    title="Remove a medicine",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False),
    description="Remove a medicine the doctor has stopped. Confirm with the person before calling.",
)
def remove_medication(name: Annotated[str, Field(description="Medicine to remove")]) -> dict:
    return care.remove_medication(name)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {"status": "ok", "server": "careloop", "storage": care.store.backend, "protocol": LATEST_PROTOCOL_VERSION}
    )


class BearerAuth:
    """Optional shared-secret check. Set CARELOOP_API_KEY to require 'Authorization: Bearer <key>' on /mcp."""

    def __init__(self, app, key: str):
        self.app, self.key = app, key

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization", b"").decode() != f"Bearer {self.key}":
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app():
    hosts = [h.strip() for h in os.getenv("CARELOOP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = (
        TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=[])
        if hosts
        else TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=os.getenv("CARELOOP_STATELESS", "1") == "1",  # stateless scales behind a load balancer
        transport_security=security,
        host=os.getenv("HOST", "0.0.0.0"),
    )
    key = os.getenv("CARELOOP_API_KEY")
    return BearerAuth(app, key) if key else app


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
