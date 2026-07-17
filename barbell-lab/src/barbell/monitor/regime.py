"""Regime dashboard: z-scores of the four macro pillars + 4-quadrant call.

Pillars (config/monitors.yaml):
    labor     ICSA          (initial claims; RISING claims = growth DOWN)
    inflation T5YIE         (5y breakevens)
    credit    BAMLH0A0HYM2  (HY OAS)
    dollar    DTWEXBGS      (broad dollar)

z-scores over a 3y window of each series' own history. The growth axis uses
the INVERTED labor z (claims up = growth down); the inflation axis uses the
breakeven z. Credit and dollar are context columns + trigger inputs, not
quadrant axes. Logged daily to regime_log.
"""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

from .. import db
from ..config import load


def _zscore_latest(s: pd.Series, window_days: int) -> float:
    s = s.dropna()
    if len(s) < 60:
        raise ValueError(f"{s.name}: too little history for a z-score")
    ref = s.tail(window_days)
    sd = ref.std(ddof=1)
    if sd == 0:
        raise ValueError(f"{s.name}: zero variance in window")
    return float((ref.iloc[-1] - ref.mean()) / sd)


def regime_snapshot(con: sqlite3.Connection) -> dict:
    cfg = load("monitors")["regime"]
    window = int(cfg["zscore_window_days"])
    pillars = cfg["pillars"]
    series = {name: db.read_fred(con, sid) for name, sid in pillars.items()}
    z = {name: _zscore_latest(s, window) for name, s in series.items()}

    growth_up = -z["labor"] >= 0          # claims below trend => growth up
    inflation_up = z["inflation"] >= 0
    quadrant = {
        (True, True): "reflation",
        (True, False): "goldilocks",
        (False, True): "stagflation",
        (False, False): "deflation_bust",
    }[(growth_up, inflation_up)]

    asof = max(s.dropna().index.max() for s in series.values())
    snap = {
        "date": f"{asof:%Y-%m-%d}",
        "labor_z": z["labor"], "inflation_z": z["inflation"],
        "credit_z": z["credit"], "dollar_z": z["dollar"],
        "quadrant": quadrant,
        "levels": {name: float(s.dropna().iloc[-1]) for name, s in series.items()},
    }
    con.execute(
        "INSERT INTO regime_log (date, labor_z, inflation_z, credit_z, dollar_z, quadrant, details) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET "
        "labor_z=excluded.labor_z, inflation_z=excluded.inflation_z, "
        "credit_z=excluded.credit_z, dollar_z=excluded.dollar_z, "
        "quadrant=excluded.quadrant, details=excluded.details",
        (snap["date"], snap["labor_z"], snap["inflation_z"], snap["credit_z"],
         snap["dollar_z"], quadrant, json.dumps(snap["levels"])),
    )
    con.commit()
    return snap


def format_regime(snap: dict) -> str:
    lv = snap["levels"]
    return "\n".join([
        f"Regime dashboard — {snap['date']}",
        "",
        "| pillar | level | z (3y) |",
        "|---|---|---|",
        f"| labor (ICSA) | {lv['labor']:,.0f} | {snap['labor_z']:+.2f} |",
        f"| inflation (T5YIE) | {lv['inflation']:.2f}% | {snap['inflation_z']:+.2f} |",
        f"| credit (HY OAS) | {lv['credit']:.2f}% | {snap['credit_z']:+.2f} |",
        f"| dollar (DTWEXBGS) | {lv['dollar']:.1f} | {snap['dollar_z']:+.2f} |",
        "",
        f"**Quadrant: {snap['quadrant'].upper()}** "
        f"(growth {'UP' if -snap['labor_z'] >= 0 else 'DOWN'}, "
        f"inflation {'UP' if snap['inflation_z'] >= 0 else 'DOWN'})",
    ])
