"""Telegram alerts for canary events — fire-and-forget, never blocks refresh.

Same bot as the executor's (one bot, one chat, two services): set
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID on this service too. Unset = no-op.
TELEGRAM_MIN_SEVERITY (default WARN) filters which events reach the phone:
WARN covers rate-path probability shifts; RED/CRITICAL covers metric flips,
band crossings and re-steepening alarms.
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)

_RANK = {"INFO": 0, "WARN": 1, "RED": 2, "CRITICAL": 3}
_ICON = {"WARN": "🟡", "RED": "🔴", "CRITICAL": "🚨"}


def min_severity() -> str:
    return os.environ.get("TELEGRAM_MIN_SEVERITY", "WARN").upper()


def should_send(severity: str) -> bool:
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and
            os.environ.get("TELEGRAM_CHAT_ID")):
        return False
    return _RANK.get(severity.upper(), 0) >= _RANK.get(min_severity(), 1)


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    def _post():
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": text[:4000]}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram send failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()


# Plain-English headers. The phone should read like a note from an analyst,
# not a log line: no event-type slugs, no [WARN] tags.
_TITLE = {
    "squeeze_condition_flip": "Squeeze Radar — a condition changed",
    "squeeze_prebrief": "Squeeze Radar — event coming up",
    "composite_band_cross": "Stress score moved to a new band",
    "curve_resteepening": "Yield curve re-steepened",
    "curve_new_inversion": "Yield curve inverted",
    "rate_path_shift": "Fed rate odds moved",
    "cycle_phase_change": "Business cycle changed phase",
}
_LEVEL = {"WARN": "heads-up", "RED": "alert", "CRITICAL": "critical"}


def _title(event_type: str) -> str:
    if event_type.startswith("metric_red:"):
        return "A metric turned red"
    return _TITLE.get(event_type, event_type.replace("_", " "))


def format_event(event_type: str, severity: str, rationale: str) -> str:
    sev = severity.upper()
    icon = _ICON.get(sev, "ℹ️")
    return f"{icon} Canary — {_title(event_type)} ({_LEVEL.get(sev, sev.lower())})\n{rationale}"


# ── Squeeze Radar wording ────────────────────────────────────────────────────
# One plain line per registered condition: what it is actually watching.
_SQUEEZE_PLAIN = {
    "F1": "hedge funds' short in bond futures",
    "F2": "the short base in TLT",
    "F3": "how cheap long bonds are on term premium",
    "F4": "how hard or costly it is to borrow TLT to short",
    "T1": "the Fed pivoting to rate cuts",
    "T2": "the job market breaking",
    "T3": "inflation cooling enough to allow cuts",
    "T4": "Treasury cutting long-bond supply or buying it back",
    "T5": "a bond-market vol spike or dislocation",
}
_STATE = {"MET": "ON", "NOT_MET": "OFF", "PARTIAL": "partly on",
          "UNVERIFIED": "unverified", "STALE": "no data"}


def _score(fuel: float, trig: float) -> str:
    return f"fuel {fuel:g} of 4 · triggers {trig:g} of 5"


def squeeze_flip_text(cond: dict, prev_state: str, fuel: float, trig: float) -> str:
    cid = cond["id"]
    kind = "Trigger" if cid.startswith("T") else "Fuel"
    now, was = _STATE.get(cond["state"], cond["state"]), _STATE.get(prev_state, prev_state)
    lines = [
        f"{kind} {cid} ({cond['label']}) switched {now} — was {was}.",
        f"It watches {_SQUEEZE_PLAIN.get(cid, 'this condition')}.",
    ]
    if cond.get("detail"):
        lines.append(f"Reading now: {cond['detail']}.")
    tail = "A trigger just went live — this is the one to act on." if (
        kind == "Trigger" and cond["state"] == "MET") else "Nothing has fired."
    lines.append(f"Scorecard: {_score(fuel, trig)}. {tail}")
    return "\n".join(lines)


def squeeze_prebrief_text(event: str, when, days_out: int, estimated: bool,
                          fuel: float, trig: float) -> str:
    day = when.strftime("%a %b %-d")
    approx = "around " if estimated else ""
    soon = "today" if days_out == 0 else ("tomorrow" if days_out == 1 else f"in {days_out} days")
    return "\n".join([
        f"{event} is {soon} ({approx}{day}).",
        "Triggers fire on scheduled dates like this one — worth watching.",
        f"Scorecard going in: {_score(fuel, trig)}.",
    ])
