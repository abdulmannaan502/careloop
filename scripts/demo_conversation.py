"""Play a scripted day with CareLoop over real MCP Streamable HTTP.

Each step shows what the person says, which tool Alexa+ would call, and what Alexa
would say back. Useful for the demo video and for checking a deployed server.

    python scripts/demo_conversation.py                      # local server
    python scripts/demo_conversation.py https://your-host/mcp --key SECRET
"""
from __future__ import annotations

import argparse
import asyncio
import json

from mcp.client.client import Client

SCRIPT = [
    ("Add my BP tablet, Amlodipine 5mg, every morning. I have 6 left.",
     "add_medication", {"name": "Amlodipine", "dosage": "5mg", "schedule": "every morning",
                        "purpose": "blood pressure", "pills_left": 6}),
    ("The doctor gave me Metformin 500 for sugar, twice a day after meals. 30 tablets.",
     "add_medication", {"name": "Metformin", "dosage": "500mg", "schedule": "twice a day after meals",
                        "purpose": "diabetes", "pills_left": 30, "instructions": "after food"}),
    ("Alexa, what medicine do I need to take now?", "whats_due_now", {}),
    ("I took my BP tablet.", "log_dose_taken", {"medication": "BP tablet"}),
    ("I took my BP tablet.  (said again by mistake)", "log_dose_taken", {"medication": "BP tablet"}),
    ("I'm feeling a bit dizzy today.", "log_symptom", {"description": "feeling a bit dizzy"}),
    ("Do I need to buy any medicines?", "refill_alert", {}),
    ("[Family member, evening] Alexa, how is Amma doing today?", "daily_summary_for_family", {}),
]


async def main(url: str, key: str | None) -> None:
    target = url
    if key:
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

        http = create_mcp_http_client(headers={"Authorization": f"Bearer {key}"})
        target = streamable_http_client(url, http_client=http)

    async with Client(target) as client:
        tools = await client.list_tools()
        print(f"Connected to {client.server_info.name} (protocol {client.protocol_version})")
        print("Tools:", ", ".join(t.name for t in tools.tools), "\n")
        for said, tool, args in SCRIPT:
            result = await client.call_tool(tool, args)
            data = result.structured_content or json.loads(result.content[0].text)
            data = data.get("result", data)
            print(f"🧓  {said}")
            print(f"    ↳ tool: {tool}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
            print(f"🔵  Alexa: {data['say']}\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("url", nargs="?", default="http://localhost:8000/mcp")
    p.add_argument("--key", default=None, help="Bearer key if CARELOOP_API_KEY is set on the server")
    a = p.parse_args()
    asyncio.run(main(a.url, a.key))
