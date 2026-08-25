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


class OutageLog:
    """Append-only-ish ledger; safe to construct with a path that cannot be
    written (observability must never break trading)."""

    def __init__(self, path: str | None):
        self.path = path
        self.open: dict | None = None
        self.history: list[dict] = []
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            raw = json.load(open(self.path))
            self.history = list(raw.get("history") or [])[-HISTORY_MAX:]
            self.open = raw.get("open") or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage log unreadable (%s) — starting fresh", exc)
            return
        # An outage was in flight when the previous process ended: it did NOT
        # end by reconnecting, and saying so is the whole point of the field.
        if self.open:
            rec = dict(self.open)
            rec["end_ts"] = rec.get("last_seen_ts") or rec["start_ts"]
            rec["duration_s"] = round(rec["end_ts"] - rec["start_ts"], 1)
            rec["ended_by"] = "process_restart"
            self.history.append(rec)
            self.open = None
            self._save()

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
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage log not persisted: %s", exc)

    # ---------- recording ----------
    def start(self, ts: float | None = None) -> None:
        """Idempotent: the adapter calls this on every failed poll."""
        if self.open:
            return
        self.open = {"start_ts": ts or time.time(), "cycles_blocked": 0,
                     "alerted": False, "last_seen_ts": ts or time.time()}
        self._save()

    def cycle_blocked(self) -> None:
        if not self.open:
            return
        self.open["cycles_blocked"] += 1
        self.open["last_seen_ts"] = time.time()
        self._save()

    def mark_alerted(self) -> None:
        if self.open and not self.open["alerted"]:
            self.open["alerted"] = True
            self._save()

    def end(self, ts: float | None = None) -> dict | None:
        if not self.open:
            return None
        rec = dict(self.open)
        rec["end_ts"] = ts or time.time()
        rec["duration_s"] = round(rec["end_ts"] - rec["start_ts"], 1)
        rec["ended_by"] = "reconnect"
        rec.pop("last_seen_ts", None)
        self.history.append(rec)
        self.open = None
        self._save()
        return rec

    # ---------- reporting ----------
    def summary(self, window_days: float = 30.0) -> dict:
        cutoff = time.time() - window_days * 86400
        recent = [r for r in self.history if r.get("start_ts", 0) >= cutoff]
        durs = sorted(r.get("duration_s", 0.0) for r in recent)
        self_healed = sum(1 for r in recent if r.get("ended_by") == "reconnect")
        return {
            "window_days": window_days,
            "outages": len(recent),
            "total_downtime_s": round(sum(durs), 1),
            "median_s": durs[len(durs) // 2] if durs else None,
            "max_s": durs[-1] if durs else None,
            # the number that says whether supervision is working
            "self_healed": self_healed,
            "needed_a_restart": len(recent) - self_healed,
            "cycles_blocked": sum(r.get("cycles_blocked", 0) for r in recent),
            "alerted": sum(1 for r in recent if r.get("alerted")),
            "currently_down_since": (self.open or {}).get("start_ts"),
        }
