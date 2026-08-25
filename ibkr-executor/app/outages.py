"""Persisted IB-gateway outage ledger.

Outage state used to live only on the adapter instance (`_disconnected_since`,
`_outage_alerted`), so a restart erased it and NO history existed at all — the
question "how much downtime do we actually have, and how much of it is IBKR
versus our own container" was unanswerable rather than merely unanswered.

This records every outage to disk so the answer becomes arithmetic:

- `ended_by="reconnect"`   the executor healed itself (backoff worked)
- `ended_by="process_restart"` the process died or was restarted while the
  gateway was down — i.e. it did NOT self-heal. This is the distinction that
  separates "IB being IB" from "our supervision is broken", and it is exactly
  the one an in-memory flag can never make.
- `cycles_blocked`         decision cycles that failed closed during it. This,
  not wall-clock uptime, is what an outage actually costs: an outage that
  overlaps no decision point costs nothing.
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger("ibkr-executor.outages")

HISTORY_MAX = 500
# blocked-call bookkeeping is chatty; persist it at most this often
SAVE_THROTTLE_S = 60.0


def _never_raises(fn):
    """Observability may not break trading. The adapter calls these from
    inside _reconnect(); a raise there escaped as the wrong exception type
    and, on the reconnect-SUCCESS path, left the adapter permanently
    believing it was mid-outage (counter-agent 2026-08-24, CRITICAL).
    Tolerating None was never enough - it also has to tolerate raising."""
    def wrapper(self, *a, **kw):
        try:
            return fn(self, *a, **kw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage ledger %s failed (ignored): %s",
                           fn.__name__, exc)
            return None
    wrapper.__name__ = fn.__name__
    return wrapper


def _num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default          # NaN -> default


class OutageLog:
    """Append-only-ish ledger; safe to construct with a path that cannot be
    written (observability must never break trading)."""

    def __init__(self, path: str | None):
        self.path = path
        self.open: dict | None = None
        self.history: list[dict] = []
        self._last_save = 0.0
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            raw = json.load(open(self.path))
            self.history = list(raw.get("history") or [])[-HISTORY_MAX:]
            self.open = raw.get("open") or None
            self.history = [r for r in self.history if isinstance(r, dict)]
            if not isinstance(self.open, dict):
                self.open = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage log unreadable (%s) — starting fresh", exc)
            self.history, self.open = [], None
            return
        # An outage was in flight when the previous process ended: it did NOT
        # end by reconnecting, and saying so is the whole point of the field.
        # Inside its own guard: this used to sit outside the try, so one
        # malformed record raised out of __init__ -> _build() -> the service
        # came up with NO trading loop (counter-agent 2026-08-24).
        try:
            if self.open:
                rec = dict(self.open)
                start = _num(rec.get("start_ts"), time.time())
                rec["start_ts"] = start
                rec["end_ts"] = _num(rec.get("last_seen_ts"), start) or start
                rec["duration_s"] = max(0.0, round(rec["end_ts"] - start, 1))
                rec["ended_by"] = "process_restart"
                rec.setdefault("blocked_calls", rec.get("cycles_blocked", 0))
                self.history.append(rec)
                self.open = None
                self._save()
        except Exception as exc:  # noqa: BLE001
            logger.warning("open outage record unusable (%s) — dropped", exc)
            self.open = None

    def _save(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.{os.getpid()}.tmp"
            json.dump({"open": self.open,
                       "history": self.history[-HISTORY_MAX:]},
                      open(tmp, "w"))
            os.replace(tmp, self.path)
            self._last_save = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage log not persisted: %s", exc)

    # ---------- recording ----------
    @_never_raises
    def start(self, ts: float | None = None) -> None:
        """Idempotent: the adapter calls this on every failed poll."""
        if self.open:
            return
        self.open = {"start_ts": ts or time.time(), "blocked_calls": 0,
                     "alerted": False, "last_seen_ts": ts or time.time()}
        self._save()

    @_never_raises
    def blocked_call(self) -> None:
        """One adapter call that could not reach the gateway.

        NOT one cycle: _require_connected guards six surfaces and
        reference_prices loops per symbol, so this scales with book size and
        is not comparable across time (counter-agent 2026-08-24). It is a
        cost signal, not a rate. Throttled: it used to rewrite the whole
        ledger (~75 KB at HISTORY_MAX) on every blocked call.
        """
        if not self.open:
            return
        self.open["blocked_calls"] = self.open.get("blocked_calls", 0) + 1
        now = time.time()
        self.open["last_seen_ts"] = now
        if now - self._last_save >= SAVE_THROTTLE_S:
            self._save()

    @_never_raises
    def mark_alerted(self) -> None:
        if self.open and not self.open["alerted"]:
            self.open["alerted"] = True
            self._save()

    @_never_raises
    def end(self, ts: float | None = None) -> dict | None:
        if not self.open:
            return None
        rec = dict(self.open)
        rec["end_ts"] = ts or time.time()
        raw = round(_num(rec["end_ts"]) - _num(rec["start_ts"]), 1)
        if raw < 0:
            # clock stepped backwards (NTP); a negative duration would
            # silently poison total_downtime_s and max_s
            rec["clock_step"] = True
        rec["duration_s"] = max(0.0, raw)
        rec["ended_by"] = "reconnect"
        rec.pop("last_seen_ts", None)
        self.history.append(rec)
        # cap in MEMORY too: only the disk copy was capped, so a long-lived
        # process grew unbounded (counter-agent 2026-08-24)
        self.history = self.history[-HISTORY_MAX:]
        self.open = None
        self._save()
        return rec

    # ---------- reporting ----------
    @_never_raises
    def summary(self, window_days: float = 30.0) -> dict:
        cutoff = time.time() - window_days * 86400
        hist = [r for r in self.history if isinstance(r, dict)]
        recent = [r for r in hist if _num(r.get("start_ts")) >= cutoff]
        durs = sorted(_num(r.get("duration_s")) for r in recent)
        self_healed = sum(1 for r in recent if r.get("ended_by") == "reconnect")
        return {
            "window_days": window_days,
            "outages": len(recent),
            "total_downtime_s": round(sum(durs), 1),
            "clock_steps": sum(1 for r in recent if r.get("clock_step")),
            "median_s": durs[len(durs) // 2] if durs else None,
            "max_s": durs[-1] if durs else None,
            # the number that says whether supervision is working
            "self_healed": self_healed,
            "needed_a_restart": len(recent) - self_healed,
            "blocked_calls": int(sum(_num(r.get("blocked_calls",
                                                 r.get("cycles_blocked")))
                                     for r in recent)),
            "alerted": sum(1 for r in recent if r.get("alerted")),
            "currently_down_since": (self.open or {}).get("start_ts"),
        }
