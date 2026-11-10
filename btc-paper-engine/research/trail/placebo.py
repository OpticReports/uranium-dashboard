"""Placebo sweep (PREREG.md, null #2): does a 21-wide sweep of a DIFFERENT
exit parameter produce a lift as large as the trail's?

Sweeps the pullback book's time_stop_bars (live value 60) over 21 points on
the same window, same blend construction, same best-of-21 statistic. If the
placebo's best-of-21 lift matches the trail's, the trail sweep is measuring
search width, not the trail.

    python3 research/trail/placebo.py <bars_csv>
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, HERE)

from app.engine.core import Bar, TradeCfg                       # noqa: E402
from app.engine.replay import run_replay                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,        # noqa: E402
                        RESEARCH_TRADE)
from sweep import blend_curve, stats                            # noqa: E402

BARS_CSV = sys.argv[1]
BAR_S = 4 * 3600
T0 = 1640995200                                                 # modern
GRID = [20 + 5 * i for i in range(21)]                          # 20..120, 60 in
BASE = 60

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
            high=float(r["high"]), low=float(r["low"]),
            close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS_CSV))]
T1 = bars[-1].ts + BAR_S
books = [b for b in RESEARCH_BOOKS if b.name in ("S3", "S4")]

mars = {}
for g in GRID:
    tcfg = TradeCfg(**{**RESEARCH_TRADE.__dict__, "time_stop_bars": g})
    res = run_replay(bars, books, RESEARCH_SIGNAL, tcfg,
                     start_ts=T0, end_ts=T1, cash_apy=0.0)
    s = stats(blend_curve(res.books["S3"], res.books["S4"], 0.25, 2.0, T0, T1))
    mars[g] = s["mar"]
    print(f"time_stop_bars {g:>4}: S6 MAR {s['mar']:.3f}  "
          f"cagr {s['cagr_pct']:>5.1f}%  dd {s['maxdd_pct']:>6.1f}%"
          + ("   <-- LIVE" if g == BASE else ""))

v = np.array([mars[g] for g in GRID])
med = float(np.median(v))
best = GRID[int(np.argmax(v))]
print(f"\nplacebo best-of-21: {max(v):.3f} at time_stop_bars={best}; "
      f"median {med:.3f}; LIFT = {max(v) - med:+.3f}")
print(f"live value 60 -> MAR {mars[BASE]:.3f}  (lift over median "
      f"{mars[BASE] - med:+.3f})")
print("\nCompare with the trail sweep's best-of-21 lift over ITS grid median.")
