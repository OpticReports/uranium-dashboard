"""Nightly rebalance-band monitor.

Live positions come from ``data/positions.json`` (broker export or manual
snapshot):

    {"asof": "2026-07-16",
     "positions": {"AVUV": 105000, "AVDV": 80000, ...},   # market value $
     "cash": 2500}

Tickers must match the resolved sleeve targets (TAIL_SLEEVE resolved via
config tail_sleeve.current). Alert fires when any sleeve's live weight is more
than band_relative away from target (relative, e.g. 25% target ±20% → outside
[20%, 30%]). Output is an actionable dollar trade list back to exact targets.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..backtest.engine import resolve_targets
from ..config import ROOT, load


def load_positions(path: str | Path | None = None) -> dict:
    cfg = load("monitors")["rebalance_alert"]
    p = Path(path or ROOT / cfg["positions_path"])
    if not p.exists():
        raise FileNotFoundError(
            f"no positions snapshot at {p} — export broker positions to this "
            "file (see monitor/rebalance.py docstring for the schema)"
        )
    data = json.loads(p.read_text())
    if "positions" not in data or not isinstance(data["positions"], dict):
        raise ValueError(f"{p} missing 'positions' mapping")
    return data


def check_rebalance(con: sqlite3.Connection, positions: dict | None = None) -> dict:
    cfg = load("monitors")["rebalance_alert"]
    band = float(cfg["band_relative"])
    tail = load("portfolio")["tail_sleeve"]["current"]
    targets = resolve_targets(tail)

    snap = positions or load_positions()
    pos = {k.upper(): float(v) for k, v in snap["positions"].items()}
    unknown = set(pos) - set(targets)
    missing = set(targets) - set(pos)
    if unknown:
        raise ValueError(f"positions contain tickers outside the sleeve: {sorted(unknown)}")
    total = sum(pos.values())
    if total <= 0:
        raise ValueError("total sleeve market value is non-positive")

    rows, breached = [], []
    for t, tgt in sorted(targets.items(), key=lambda kv: -kv[1]):
        mv = pos.get(t, 0.0)
        w = mv / total
        rel = w / tgt - 1.0
        trade = tgt * total - mv
        is_breach = abs(rel) > band or t in missing
        if is_breach:
            breached.append(t)
        rows.append({"ticker": t, "target": tgt, "live": w, "rel_drift": rel,
                     "trade_usd": trade, "breach": is_breach})
    result = {"asof": snap.get("asof"), "total_usd": total, "band": band,
              "rows": rows, "breached": breached, "alert": bool(breached)}
    if breached:
        con.execute(
            "INSERT INTO alerts (ts_utc, kind, message, details) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), "rebalance",
             f"band breach: {', '.join(breached)}", json.dumps(result)),
        )
        con.commit()
    return result


def format_rebalance(result: dict) -> str:
    lines = [f"Rebalance check (asof {result['asof']}, sleeve ${result['total_usd']:,.0f}, "
             f"band ±{result['band']:.0%} relative)", ""]
    lines.append("| ticker | target | live | rel drift | trade $ | |")
    lines.append("|---|---|---|---|---|---|")
    for r in result["rows"]:
        flag = "**BREACH**" if r["breach"] else ""
        lines.append(f"| {r['ticker']} | {r['target']:.1%} | {r['live']:.1%} "
                     f"| {r['rel_drift']:+.1%} | {r['trade_usd']:+,.0f} | {flag} |")
    lines.append("")
    lines.append("ALERT: rebalance to targets (trade list above)" if result["alert"]
                 else "within bands — no action")
    return "\n".join(lines)
