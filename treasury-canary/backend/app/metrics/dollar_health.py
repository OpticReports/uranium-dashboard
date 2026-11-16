"""Telegram pings for the Dollar tab's DATA HEALTH (Casey, 2026-11-16: "add the health pings").

Data alarms only, never a market signal: the gauge itself may colour or notify only after a D-3 PASS
(SPEC v1, Q6). The conditions are the ones offered and accepted, plus the build itself:

- the forward ledger could not be written, or is unreadable (one problem, whatever the step that hit it);
- the CP rate behind the funding word is stale or missing: FRED itself more than a week behind, the CP fetch
  failed, the Fed publishing no rate for over 5 business days (n.a. when too few trades print), or no CP data at all;
- the rebuild failed (the tab is serving the previous build, has no live data, or is down).

Other pre-registration problems (unarchived inputs, late months) show on the tab and do not ping.

A problem pings once when it opens and once when it is resolved, never while it persists, in one message per
run. A failed build proves nothing was fixed, so it never resolves anything. The open problems live beside the
ledger on the persistent disk, with an in-process copy for when that disk refuses the write (its likeliest
failure is the one being reported). Only the scheduler's rebuild calls this; a page view never sends anything.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

STATE_NAME = "dollar_health_state.json"
TAG = "(a data problem, not a market signal)"
HEAD = f"🔧 Canary — Dollar tab data health {TAG}"
DONE = f"🔧 Canary — Dollar tab data health: resolved {TAG}"
LEVEL = "WARN"
_LEDGER_MARKS = (" not saved: ", "the ledger file is unreadable")     # forward.problems that are ledger reads/writes
_MEMORY: dict[str, dict] = {}                                          # state path -> the last open set, this process


def _build_text(payload: dict) -> str:
    e = payload["build_error"]
    return {"empty": f"The last rebuild failed ({e}); the tab has no live data.",
            "none": f"The last rebuild failed ({e}) and no fallback build was possible; the tab is down."}.get(
        payload.get("build_fallback") or "", f"The last rebuild failed ({e}); the tab is showing the previous build.")


def _cp_text(payload: dict) -> str | None:
    cp = next((r for r in ((payload.get("funding") or {}).get("rows") or []) if r.get("id") == "cp_fin"), None)
    if cp is None:
        return None
    why, last, ref = cp.get("mean_5d_stale_why"), cp.get("mean_5d_to"), cp.get("mean_5d_ref")
    if why == "fetch" and ref:
        return f"FRED data end {ref}: the fetch is more than a week behind, so the funding readings are stale."
    if why == "cp_fetch" and last:
        return f"The CP fetch failed; the tab shows the last good copy (data end {last})."
    if why == "gap" and last:
        return (f"The Fed has published no 90-day AA financial CP rate since {last} (too few trades); until it prints "
                "again the funding summary is judged without CP.")
    if cp.get("latest") is None and cp.get("status") == "error":
        return "No CP data at all: the fetch failed and nothing is cached, so the funding summary has no CP reading."
    return None


def problems(payload: dict) -> dict[str, str]:
    """stable key -> one plain line, from what a successful build reports (see notify for a failed one)."""
    out: dict[str, str] = {}
    if payload.get("build_error"):
        out["build"] = _build_text(payload)
    led = payload.get("ledger") or {}
    msgs = [str(led["problem"])] if led.get("status") == "error" and led.get("problem") else []
    msgs += [str(p) for p in ((payload.get("forward") or {}).get("problems") or [])
             if any(m in str(p) for m in _LEDGER_MARKS) and str(p) not in msgs]
    if msgs:
        out["ledger"] = "Forward ledger: " + "; ".join(msgs) + "."
    cp = _cp_text(payload)
    if cp:
        out["cp"] = cp
    return out


def _load(path: str) -> dict:
    if path in _MEMORY:                          # this process knows better than a file it may have failed to write
        return dict(_MEMORY[path])
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        open_ = data.get("open") if isinstance(data, dict) else None
        return {k: v for k, v in open_.items() if isinstance(v, dict)} if isinstance(open_, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001  (an unreadable state file costs at most one repeated ping)
        logger.warning("dollar health state unreadable (%s); starting empty", exc)
        return {}


def _save(path: str, open_now: dict) -> None:
    _MEMORY[path] = dict(open_now)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"open": open_now}, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar health state not saved (kept in memory): %s", exc)


def notify(payload: dict, state_path: str, today: str, send: Callable[[str], None],
           allowed: Callable[[str], bool]) -> list[str]:
    """One message per run for the problems that opened and those resolved; returns what was (or would be) sent."""
    prev = _load(state_path)
    now = problems(payload)
    if payload.get("build_error"):               # a failed build proves nothing was fixed: everything open stays open,
        now = {"build": now["build"], **{k: str(v.get("text") or k) for k, v in prev.items() if k != "build"}}
    opened = [k for k in now if k not in prev]
    resolved = [k for k in prev if k not in now]
    parts = []
    if opened:
        parts.append(HEAD + "\n" + "\n".join(f"• {now[k]}" for k in opened))
    if resolved:
        lines = "\n".join(f"• Was: {prev[k].get('text') or k}" for k in resolved)
        parts.append((DONE + "\n" if not opened else "Resolved:\n") + lines)
    msgs = ["\n".join(parts)] if parts else []
    if msgs and allowed(LEVEL):
        send(msgs[0])
    state = {k: {"since": (prev.get(k) or {}).get("since") or today, "text": t} for k, t in now.items()}
    if state != prev:                            # a changed text (the CP cause moving) is saved, never re-pinged
        _save(state_path, state)
    return msgs


def state_path(ledger_file: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(ledger_file)), STATE_NAME)
