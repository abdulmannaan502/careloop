"""CareLoop web demo: a simulated Alexa+ experience on top of the real MCP server.

    streamlit run streamlit_app.py

Each message goes through an MCP client session to the CareLoop server (in-process by
default, or a deployed server if CARELOOP_MCP_URL is set). The right-hand panel is the
family's view of the same data.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

os.environ.setdefault("CARELOOP_DB", os.path.join(tempfile.gettempdir(), "careloop_demo.db"))

# Streamlit Cloud secrets (e.g. AWS keys, BEDROCK_MODEL_ID) become environment variables.
try:
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ.setdefault(k, v)
except Exception:
    pass

from mcp.client.client import Client  # noqa: E402

from careloop import server  # noqa: E402
from careloop.assistant import _payload, handle  # noqa: E402
from careloop.demo_data import seed_week  # noqa: E402
from careloop.store import SQLiteStore  # noqa: E402
from careloop.timeparse import human_time  # noqa: E402

TZ = ZoneInfo(os.getenv("CARELOOP_TZ", "Asia/Kolkata"))
PERSON = os.getenv("CARELOOP_PERSON_NAME", "Amma")

st.set_page_config(page_title="CareLoop", page_icon="💊", layout="wide")

st.markdown(
    """
<style>
:root { --teal:#0F5C5A; --teal2:#E3EFEC; --saff:#E8902A; --saff2:#FBE7CF; --red:#B8402F; --red2:#F7DCD6; --ink:#1F2A2E; --muted:#5E6B6F; --line:#D9D0C2; }
.stApp { background:#FBF6EE; }
.block-container { padding-top:3.2rem; max-width:1250px; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.5px; }
.brand { font-size:2.1rem; font-weight:800; color:var(--teal); margin:0; }
.tag { color:var(--muted); font-size:1.05rem; margin-top:.15rem; }
.bubble { padding:.75rem 1rem; border-radius:16px; margin:.35rem 0; font-size:1.05rem; line-height:1.45; max-width:92%; }
.me { background:#fff; border:1.5px solid var(--line); margin-left:auto; }
.alexa { background:var(--teal); color:#fff; }
.alexa.warn { background:var(--red2); color:var(--red); border:1.5px solid var(--red); }
.who { font-size:.75rem; font-weight:700; color:var(--muted); margin-top:.6rem; text-transform:uppercase; letter-spacing:.06em; }
.who.r { text-align:right; }
.tool { font-family:ui-monospace,monospace; font-size:.78rem; color:var(--saff); margin:.15rem 0 .2rem; }
.card { background:#fff; border:1.5px solid var(--line); border-radius:16px; padding:1rem 1.1rem; margin-bottom:.8rem; }
.pill { display:inline-block; font-size:.78rem; font-weight:700; padding:.15rem .6rem; border-radius:999px; }
.done { background:var(--teal2); color:var(--teal); } .due { background:var(--saff2); color:#9A5A10; }
.missed { background:var(--red2); color:var(--red); } .later { background:#EEE; color:var(--muted); }
.row { display:flex; justify-content:space-between; align-items:center; padding:.35rem 0; border-bottom:1px solid #F0EAE0; }
.row:last-child { border-bottom:none; }
.big { font-size:2.4rem; font-weight:800; color:var(--teal); line-height:1; }
.note { color:var(--muted); font-size:.85rem; }
div.stButton > button { border-radius:999px; border:1.5px solid var(--line); background:#fff; }
div.stButton > button:hover { border-color:var(--teal); color:var(--teal); }
</style>
""",
    unsafe_allow_html=True,
)


# ---------- MCP plumbing ----------
def _target():
    url = os.getenv("CARELOOP_MCP_URL")
    return url if url else server.mcp


_LOCK = threading.Lock()  # one demo household at a time touches the shared server object


def run(coro_fn):
    async def go():
        async with Client(_target()) as client:
            return await coro_fn(client)

    with _LOCK:
        server.care.store = st.session_state.store
        os.environ["CARELOOP_NOW"] = st.session_state.clock.strftime("%Y-%m-%dT%H:%M")
        return asyncio.run(go())


def call(tool: str, args: dict | None = None) -> dict:
    return run(lambda c: _call(c, tool, args or {}))


async def _call(c, tool, args):
    return _payload(await c.call_tool(tool, args))


# ---------- session state ----------
ss = st.session_state
ss.setdefault("chat", [])
ss.setdefault("clock", datetime.combine(datetime.now(TZ).date(), time(9, 10)))
ss.setdefault("seeded", False)

if not ss.seeded:
    # Fresh demo household per browser session.
    path = os.path.join(tempfile.gettempdir(), f"careloop_{uuid.uuid4().hex}.db")
    ss.store = SQLiteStore(path)
    with _LOCK:
        server.care.store = ss.store
        seed_week(server.care, ss.clock.date())
    ss.seeded = True

# ---------- sidebar: demo controls ----------
with st.sidebar:
    st.markdown("### Demo clock")
    st.caption("Move time forward to see reminders, misses and the evening update.")
    presets = {"Morning · 9:10 AM": time(9, 10), "Afternoon · 2:00 PM": time(14, 0),
               "Evening · 9:15 PM": time(21, 15), "Late · 11:00 PM": time(23, 0)}
    for label, t in presets.items():
        if st.button(label, use_container_width=True):
            ss.clock = datetime.combine(ss.clock.date(), t)
            st.rerun()
    st.markdown(f"**Now:** {ss.clock:%A, %d %b · %I:%M %p}")
    st.divider()
    if st.button("Reset demo household", use_container_width=True):
        for k in ("chat", "seeded", "clock", "summary"):
            ss.pop(k, None)
        st.rerun()
    st.caption(
        "Includes 6 days of history. Data lives only in this demo session. "
        + ("Assistant: Amazon Bedrock tool-use agent." if os.getenv("BEDROCK_MODEL_ID") else
           "Assistant: built-in phrase router (set BEDROCK_MODEL_ID for a Bedrock agent).")
    )

# ---------- header ----------
st.markdown('<p class="brand">◔ CareLoop</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="tag">A simulated Alexa+ conversation running on the CareLoop MCP server. '
    f'Talk as {PERSON} on the left; the family sees the right.</p>',
    unsafe_allow_html=True,
)

left, right = st.columns([1.15, 1], gap="large")

# ---------- conversation ----------
with left:
    st.markdown(f"### 🗣️ {PERSON} talks to Alexa")
    suggestions = [
        "What medicine do I need to take now?",
        "I took my BP tablet",
        "I'm feeling a bit dizzy today",
        "Do I need to buy any medicines?",
        "Add Atorvastatin 10mg for cholesterol at bedtime, 20 tablets",
        "I have chest pain",
    ]
    cols = st.columns(2)
    clicked = None
    for i, s in enumerate(suggestions):
        if cols[i % 2].button(s, key=f"s{i}", use_container_width=True):
            clicked = s
    typed = st.chat_input(f"Type what {PERSON} says…")
    utterance = clicked or typed
    if utterance:
        hist = [{"role": "user" if m["who"] == "me" else "assistant", "content": [{"text": m["text"]}]}
                for m in ss.chat if m["text"]]
        turn = run(lambda c: handle(c, utterance, hist))
        ss.chat.append({"who": "me", "text": utterance})
        urgent = any(x["result"].get("urgent") or x["result"].get("possible_double_dose") for x in turn.calls)
        ss.chat.append({"who": "alexa", "text": turn.reply, "calls": turn.calls, "warn": urgent})

    if not ss.chat:
        st.markdown('<p class="note">Tap a suggestion or type below to start.</p>', unsafe_allow_html=True)
    for m in ss.chat[-2:]:  # the latest exchange, like a smart display
        if m["who"] == "me":
            st.markdown(f'<div class="who r">{PERSON}</div><div class="bubble me">{m["text"]}</div>',
                        unsafe_allow_html=True)
        else:
            tools = " · ".join(
                f'{c["tool"]}({", ".join(f"{k}={v!r}" for k, v in c["args"].items())})' for c in m["calls"]
            )
            st.markdown(
                f'<div class="tool">MCP → {tools}</div>'
                f'<div class="who">Alexa</div><div class="bubble alexa {"warn" if m["warn"] else ""}">{m["text"]}</div>',
                unsafe_allow_html=True,
            )

# ---------- family view ----------
with right:
    st.markdown("### 👨‍👩‍👧 Family view")
    due = call("whats_due_now")
    rows = []
    for status, items in (("done", due["taken"]), ("due", due["due_now"]),
                          ("missed", due["overdue"]), ("later", due["upcoming"])):
        for i in items:
            rows.append((i["time"], i["medication"], i["dosage"], status))
    label = {"done": "Taken", "due": "Due now", "missed": "Not logged", "later": "Later"}
    html = "".join(
        f'<div class="row"><span><b>{human_time(t)}</b> &nbsp; {n} {d}</span>'
        f'<span class="pill {s}">{label[s]}</span></div>'
        for t, n, d, s in sorted(rows)
    )
    st.markdown(f'<div class="card"><b>Today\'s medicines</b>{html or "<p class=note>None scheduled</p>"}</div>',
                unsafe_allow_html=True)

    rep = call("adherence_report", {"days": 7})
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f'<div class="card"><div class="big">{rep["adherence_percent"]}%</div>'
                    f'<div class="note">doses on time, last 7 days</div></div>', unsafe_allow_html=True)
        refill = call("refill_alert")
        low = refill["low_stock"]
        txt = "<br>".join(f'{x["medication"]}: ~{x["days_left"]} days' for x in low) or "All stocked"
        st.markdown(f'<div class="card"><b>Refills</b><br><span class="note">{txt}</span></div>',
                    unsafe_allow_html=True)
    with c2:
        import pandas as pd

        df = pd.DataFrame({
            "day": [datetime.fromisoformat(d["date"]).strftime("%d %a") for d in rep["days"]],
            "% on time": [d["adherence_percent"] for d in rep["days"]],
        }).set_index("day")
        st.bar_chart(df, color="#0F5C5A", height=210)

    st.markdown("**Tonight's update for the family**")
    if st.button(f"Ask: “How is {PERSON} doing today?”", use_container_width=True):
        ss["summary"] = call("daily_summary_for_family")
    if "summary" in ss:
        s = ss["summary"]
        src = "Amazon Bedrock" if s["written_by"] == "bedrock" else "template (Bedrock not configured)"
        st.markdown(f'<div class="card">{s["summary"]}<br><span class="note">Written by {src}</span></div>',
                    unsafe_allow_html=True)

st.markdown(
    '<p class="note" style="margin-top:2rem">CareLoop is a reminder and journaling tool, not medical advice. '
    'In an emergency call your local emergency number. Source: MCP server in <code>careloop/server.py</code>.</p>',
    unsafe_allow_html=True,
)
