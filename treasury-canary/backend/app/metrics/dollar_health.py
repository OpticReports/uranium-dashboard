"""Telegram pings for the Dollar tab's DATA HEALTH (Casey, 2026-11-16: "add the health pings").

Data alarms only, never a market signal: the gauge itself may colour or notify only after a D-3 PASS
(SPEC v1, Q6). Every problem here is one the build already reports on the tab:

- the rebuild failed (the tab is serving the previous build);
- the forward ledger could not be written, or is unreadable (`ledger.problem`);
- the pre-registration record has a problem (`forward.problems`: unarchived inputs, late months, ...);
- the CP rate behind the funding word is more than a week stale: FRED itself is behind, the CP fetch
  failed, or the Fed has published no rate for over 5 business days (it publishes n.a. when too few
  trades print).

A ping fires when a problem first appears and once more when it is resolved, never while it persists.
The open problems are kept beside the ledger on the persistent disk, so a restart does not re-ping.
Only the scheduler's rebuild calls this; a page view never sends anything.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

logger = logging.getLogger(__name__)

STATE_NAME = "dollar_health_state.json"
HEAD = "🟡 Canary — Dollar tab data health (a data problem, not a market signal)"
DONE = "✅ Canary — Dollar tab data health: resolved"


def _stable(text: str) -> str:
    """a key that survives changing counts and dates inside the same problem text."""
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)|\d+", "", text)).strip()[:80]


def problems(payload: dict) -> dict[str, str]:
    """stable key -> one plain line, from what the build already reports."""
    out: dict[str, str] = {}
    if payload.get("build_error"):
        out["build"] = f"The last rebuild failed ({payload['build_error']}); the tab is showing the previous build."
    led = payload.get("ledger") or {}
    if led.get("status") == "error" and led.get("problem"):
        out["ledger"] = f"Forward ledger: {led['problem']}."
    for p in ((payload.get("forward") or {}).get("problems") or []):
        out["forward:" + _stable(str(p))] = f"Pre-registration record: {p}."
    cp = next((r for r in ((payload.get("funding") or {}).get("rows") or []) if r.get("id") == "cp_fin"), {})
    why, last, ref = cp.get("mean_5d_stale_why"), cp.get("mean_5d_to"), cp.get("mean_5d_ref")
    text = {"fetch": f"FRED data end {ref}: the fetch is more than a week behind, so the funding readings are stale.",
            "cp_fetch": f"The CP fetch failed; the tab shows the last good copy (data end {last}).",
            "gap": (f"The Fed has published no 90-day AA financial CP rate since {last} (too few trades); the tab "
                    "withholds the funding word until it prints again.")}.get(why or "")
    if text:
        out["cp:" + why] = text
    return out


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("open") if isinstance(data, dict) and isinstance(data.get("open"), dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001  (an unreadable state file costs at most one repeated ping)
        logger.warning("dollar health state unreadable (%s); starting empty", exc)
        return {}


def _save(path: str, open_now: dict) -> None:
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"open": open_now}, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar health state not saved: %s", exc)


def notify(payload: dict, state_path: str, today: str, send: Callable[[str], None],
           allowed: Callable[[str], bool]) -> list[str]:
    """Send one message per newly opened and per resolved problem; returns the messages."""
    now, prev = problems(payload), _load(state_path)
    msgs = [f"{HEAD}\n{text}" for k, text in now.items() if k not in prev]
    msgs += [f"{DONE}\n{(prev[k] or {}).get('text', k)}" for k in prev if k not in now]
    if msgs and allowed("WARN"):
        for m in msgs:
            send(m)
    if msgs or set(now) != set(prev):
        _save(state_path, {k: {"since": (prev.get(k) or {}).get("since") or today, "text": t} for k, t in now.items()})
    return msgs


def state_path(ledger_file: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(ledger_file)), STATE_NAME)
