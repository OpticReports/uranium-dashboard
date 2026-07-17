"""Monitor orchestration (the nightly entrypoint).

Alerting per config/monitors.yaml: mode "log" writes to the alerts table and
the monitor report only. Email/push are intentionally NOT implemented until
the investor picks a channel — a configured-but-unimplemented channel raises
instead of silently dropping alerts.
"""
from __future__ import annotations

import logging
import sqlite3

from ..config import load
from .rebalance import check_rebalance, format_rebalance
from .regime import format_regime, regime_snapshot
from .triggers import evaluate_triggers, format_triggers

logger = logging.getLogger(__name__)


def run_monitors(con: sqlite3.Connection, what: str = "all") -> str:
    mode = load("monitors")["alerting"]["mode"]
    if mode != "log":
        raise NotImplementedError(
            f"alerting mode '{mode}' not wired yet — alerts would be dropped "
            "silently. Use mode: log, or implement the channel first."
        )
    sections: list[str] = []
    if what in ("rebalance", "all"):
        try:
            sections.append(format_rebalance(check_rebalance(con)))
        except FileNotFoundError as exc:
            # No positions snapshot is a normal state before the first broker
            # export — say so loudly but keep the other monitors running.
            sections.append(f"Rebalance check: SKIPPED — {exc}")
    if what in ("regime", "all"):
        sections.append(format_regime(regime_snapshot(con)))
    if what in ("triggers", "all"):
        sections.append(format_triggers(evaluate_triggers(con)))
    if not sections:
        raise ValueError(f"unknown monitor selection: {what}")
    report = "\n\n---\n\n".join(sections)
    from ..report.render import _write
    _write("monitors", report)
    return report
