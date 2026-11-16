"""Telegram pings for the Dollar tab's DATA HEALTH (Casey, 2026-11-16: "add the health pings").

Data alarms only, never a market signal: the gauge itself may colour or notify only after a D-3 PASS
(SPEC v1, Q6). The conditions are the ones offered and accepted, plus the build itself:

- the forward ledger could not be written, or is unreadable, or a step that writes the pre-registration record
  crashed, or the ledger's disk refuses a test write (one problem, whatever the step that hit it). The text never
  names the row or step: most rows are written only when a firing appears, so naming one would announce a firing
  (Q6). The test write runs on every scheduler pass, so a disk alarm never waits for a firing to surface;
- the CP rate behind the funding word is stale or missing: FRED itself more than a week behind, the CP fetch
  failed, the Fed publishing no rate for over 5 business days (n.a. when too few trades print), or no CP data at all;
- the rebuild failed (the tab is serving the previous build, has no live data, or is down).

Other pre-registration problems (unarchived inputs, late months) show on the tab and do not ping.

A problem pings once when it opens, again only if the build fallback gets worse (previous build -> no live
data -> tab down), and once when it is resolved; never while it persists, in one message per run. A failed build
proves nothing was fixed, so it never resolves anything. A change counts as announced only once Telegram has
accepted the message: an unsent or refused ping is retried on the next run, never recorded as sent (so no
orphan "resolved"). The open problems live beside the ledger on the persistent disk, with an in-process copy for
when that disk refuses the write (its likeliest failure is the one being reported). Only the scheduler's rebuild
calls this; a page view never sends anything.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

logger = logging.getLogger(__name__)

STATE_NAME = "dollar_health_state.json"
TAG = "(a data problem, not a market signal)"
HEAD = f"🔧 Canary — Dollar tab data health {TAG}"
DONE = f"🔧 Canary — Dollar tab data health: resolved {TAG}"
LEVEL = "WARN"
_TAB_ONLY = ("inputs not archived for", "dated after their deadline")    # forward.problems that stay on the tab
UNREADABLE = "Forward ledger: the ledger file is unreadable or wrongly shaped; nothing is being recorded."
_EXC = re.compile(r"^([A-Za-z_]\w*(?:Error|Exception)): ")
_FALLBACK_RANK = {"previous": 1, "empty": 2, "none": 3}                  # how bad a failed build's fallback is
PROBE_NAME = ".dollar_health_probe"
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
        return (f"The Fed has published no 90-day AA financial CP rate since {last} (too few trades); the funding "
                "summary leaves CP out until it prints again (after a month-long blank, until five new prints).")
    if cp.get("latest") is None and cp.get("status") == "error":
        return "No CP spread: the CP or bill series is empty (the fetch failed and nothing is cached)."
    return None


def _ledger_text(msgs: list[str], probe_error: str | None) -> str | None:
    """one generic line: the cause (the OS error, or the crash's exception type), never the row or step named."""
    if any("unreadable" in m for m in msgs):
        return UNREADABLE                         # one root cause, one fixed line
    causes: list[str] = []
    for m in msgs:
        if " not saved: " in m:
            c = f"a write failed ({m.rsplit(' not saved: ', 1)[1].strip()})"
        else:
            x = _EXC.match(m)
            c = f"a recording step failed ({x.group(1)})" if x else "a recording step failed"
        if c not in causes:
            causes.append(c)
    if probe_error:
        causes.append(f"the disk refused a test write ({probe_error})")
    return ("Forward ledger: " + "; ".join(causes) + ".") if causes else None


def problems(payload: dict, probe_error: str | None = None) -> dict[str, str]:
    """stable key -> one plain line, from what a successful build reports (see notify for a failed one)."""
    out: dict[str, str] = {}
    if payload.get("build_error"):
        out["build"] = _build_text(payload)
    led = payload.get("ledger") or {}
    msgs = [p.strip() for p in str(led["problem"]).split("; ")] if led.get("status") == "error" and led.get("problem") else []
    msgs += [str(p) for p in ((payload.get("forward") or {}).get("problems") or [])
             if not any(m in str(p) for m in _TAB_ONLY) and str(p) not in msgs]
    text = _ledger_text(msgs, probe_error)
    if text:
        out["ledger"] = text
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


def probe(ledger_file: str) -> str | None:
    """None if the ledger's disk takes a write the size of the ledger (it is rewritten whole) and the ledger file is
    writable; else the error. Run on every scheduler pass, so a disk alarm never waits for a row to be written."""
    d = os.path.dirname(os.path.abspath(ledger_file))
    p = os.path.join(d, PROBE_NAME)
    try:
        size = os.path.getsize(ledger_file) if os.path.exists(ledger_file) else 0
        os.makedirs(d, exist_ok=True)
        with open(p + ".tmp", "wb") as fh:
            fh.write(b"\0" * min(max(size, 4096), 8 << 20))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(p + ".tmp", p)
        os.remove(p)
        if size and not os.access(ledger_file, os.W_OK):
            return "PermissionError: the ledger file is not writable"
        return None
    except Exception as exc:  # noqa: BLE001
        try:
            os.remove(p + ".tmp")
        except OSError:
            pass
        return f"{type(exc).__name__}: {exc}"[:200]


def _rank(payload: dict, key: str) -> int:
    return _FALLBACK_RANK.get(payload.get("build_fallback") or "previous", 1) if key == "build" else 0


def notify(payload: dict, state_path: str, today: str, send: Callable[[str], object],
           allowed: Callable[[str], bool], ledger_file: str | None = None) -> list[str]:
    """One message per run for the problems that opened, got worse or were resolved; returns what was (or would be)
    sent. `send` returns truthy only when the message was delivered; anything else leaves the change unannounced."""
    prev = _load(state_path)
    err = probe(ledger_file) if ledger_file else None
    now = problems(payload, err)
    if payload.get("build_error"):               # a failed build proves nothing was fixed: everything open stays open,
        kept = {k: str(v.get("text") or k) for k, v in prev.items() if k != "build"}
        disk = _ledger_text([], err)             # only today's disk test can open a problem: the payload is a stale copy
        now = {"build": now["build"], **kept, **({"ledger": disk} if disk and "ledger" not in kept else {})}
    opened = [k for k in now if k not in prev]
    resolved = [k for k in prev if k not in now]
    worse = [k for k in now if k in prev and _rank(payload, k) > int(prev[k].get("rank") or 0)]
    parts = []
    if opened or worse:
        parts.append(HEAD + "\n" + "\n".join([f"• {now[k]}" for k in opened] + [f"• Worse: {now[k]}" for k in worse]))
    if resolved:
        lines = "\n".join(f"• Was: {prev[k].get('text') or k}" for k in resolved)
        parts.append((DONE + "\n" if not parts else "Resolved:\n") + lines)
    msgs = ["\n".join(parts)] if parts else []
    delivered = bool(msgs) and allowed(LEVEL) and bool(send(msgs[0]))
    state = {k: {"since": (prev.get(k) or {}).get("since") or today, "text": t, "rank": _rank(payload, k)}
             for k, t in now.items()}
    if msgs and not delivered:                   # unannounced: retry next run (an open unsaved, a resolve or a
        state = {k: v for k, v in state.items() if k not in opened}           # worsening kept as it was)
        state.update({k: prev[k] for k in resolved + worse})
    if state != prev:                            # a changed text (the CP cause moving) is saved, never re-pinged
        _save(state_path, state)
    return msgs


def state_path(ledger_file: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(ledger_file)), STATE_NAME)
