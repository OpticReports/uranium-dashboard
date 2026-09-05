"""S4 chandelier-trail dose curve on the S6 blend. See PREREG.md.

Diagnostic only: RESEARCH_PROTOCOL section 7 bars adopting anything from an
exit-parameter sweep while the live gate is open. Output is a verdict plus,
at most, a queued item.

    python3 research/trail/sweep.py <bars_csv> <out_dir>

Construction is bench_blend.py's, cell-for-cell: fresh run_replay per window
(start_ts=t0, cash_apy 0, research signal/trade cfg), exit-step blend curve
75% S3 / 25% S4 at 2.0x. One replay per window carries all 21 S4 variants as
separate books so every cell sees an identical indicator pass and an
identical S3 leg.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))

from app.engine.core import Bar, BookCfg                        # noqa: E402
from app.engine.replay import run_replay                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,        # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1]
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else HERE
# POST-HOC (not pre-registered): override S4's dd_halt to isolate the trail's
# own effect from the -50% book kill switch, which the registered run showed
# fires in 13 of 21 cells. 1.0 = effectively off. Default None = live config.
DD_HALT = float(sys.argv[3]) if len(sys.argv) > 3 else None
TAG = "" if DD_HALT is None else f"_ddhalt{DD_HALT:g}"
BAR_S = 4 * 3600

# PRE-REGISTERED grid + windows. Do not edit after 2026-09-05.
GRID = [round(2.0 + 0.25 * i, 2) for i in range(21)]        # 2.00 .. 7.00
BASE = 5.0
HL_START = 1683849600                                        # 2023-05-12
WINDOWS = {
    "modern":   (1640995200, None),                          # 2022-01-01 ->
    "hl":       (HL_START, None),
    "modern_A": (1640995200, 1719705600),                    # -> 2024-06-30
    "modern_B": (1719705600, None),                          # 2024-07-01 ->
}

S3_CFG = next(b for b in RESEARCH_BOOKS if b.name == "S3")
S4_CFG = next(b for b in RESEARCH_BOOKS if b.name == "S4")


def s4_name(m: float) -> str:
    return f"S4_{m:.2f}"


def books_for_sweep() -> list[BookCfg]:
    out = [S3_CFG]
    for m in GRID:
        over = {"name": s4_name(m), "trail_atr": m}
        if DD_HALT is not None:
            over["dd_halt"] = DD_HALT
        out.append(BookCfg(**{**S4_CFG.__dict__, **over}))
    return out


def blend_curve(b3, b4, w, lev, t0, t1):
    """Verbatim bench_blend.blend_curve — exit-step blend factor."""
    evs = sorted([(t.exit_ts, "P", t) for t in b3.trades]
                 + [(t.exit_ts, "T", t) for t in b4.trades])
    p3 = p4 = 1.0
    eq = 1.0
    out = []
    for ts, which, t in evs:
        ratio = t.equity_after / (b3 if which == "P" else b4).cfg.start_equity
        r = (ratio / p3 - 1) * (1 - w) if which == "P" else (ratio / p4 - 1) * w
        if which == "P":
            p3 = ratio
        else:
            p4 = ratio
        if t0 <= ts <= t1:
            eq *= 1 + lev * r
            out.append((ts, eq))
    return out


def stats(curve):
    """Verbatim bench_blend.stats."""
    ts = np.array([c[0] for c in curve])
    nav = np.array([c[1] for c in curve])
    yrs = (ts[-1] - ts[0]) / (365.25 * 86400)
    tot = nav[-1] / nav[0] - 1
    cagr = (nav[-1] / nav[0]) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    r = np.diff(nav) / nav[:-1]
    return dict(total_pct=100 * tot, cagr_pct=100 * cagr, maxdd_pct=100 * mdd,
                mar=cagr / abs(mdd) if mdd < -0.005 else None,
                sharpe=(r.mean() / (r.std() + 1e-12)) * math.sqrt(len(r) / yrs)
                if len(r) > 3 else None,
                years=yrs, n_points=len(nav))


def s4_stats(book, t0, t1):
    """Standalone S4, same exit-step convention at 1x."""
    tr = [t for t in book.trades if t0 <= t.exit_ts <= t1]
    if len(tr) < 2:
        return dict(n=len(tr), mar=None, cagr_pct=None, maxdd_pct=None,
                    win_pct=None)
    eq, prev = 1.0, 1.0
    curve = []
    for t in tr:
        ratio = t.equity_after / book.cfg.start_equity
        eq *= 1 + (ratio / prev - 1)
        prev = ratio
        curve.append((t.exit_ts, eq))
    s = stats(curve)
    wins = sum(1 for t in tr if t.pnl_usd > 0)
    return dict(n=len(tr), mar=s["mar"], cagr_pct=s["cagr_pct"],
                maxdd_pct=s["maxdd_pct"], win_pct=100.0 * wins / len(tr),
                avg_bars=float(np.mean([t.bars_held for t in tr])))


def main():
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]
    end_default = bars[-1].ts + BAR_S
    cfgs = books_for_sweep()
    out = {"grid": GRID, "base": BASE, "dd_halt": DD_HALT, "bars": len(bars),
           "first_ts": bars[0].ts, "last_ts": bars[-1].ts, "windows": {}}

    for wname, (t0, t1_raw) in WINDOWS.items():
        t1 = t1_raw if t1_raw is not None else end_default
        res = run_replay(bars, cfgs, RESEARCH_SIGNAL, RESEARCH_TRADE,
                         start_ts=t0, end_ts=t1, cash_apy=0.0)
        b3 = res.books["S3"]
        cells = {}
        curves = {}
        for m in GRID:
            b4 = res.books[s4_name(m)]
            c = blend_curve(b3, b4, 0.25, 2.0, t0, t1)
            cells[f"{m:.2f}"] = {"s6": stats(c), "s4": s4_stats(b4, t0, t1),
                                 "halted": bool(b4.halted)}
            curves[f"{m:.2f}"] = c
        out["windows"][wname] = {"t0": t0, "t1": t1, "cells": cells}
        if wname == "modern":
            out["curves_modern"] = curves
        # per-trade P&L streams for the bootstrap null (modern window only)
        if wname == "modern":
            evs = {}
            for m in GRID:
                b4 = res.books[s4_name(m)]
                evs[f"{m:.2f}"] = _event_returns(b3, b4, 0.25, 2.0, t0, t1)
            out["events_modern"] = evs

        base = cells[f"{BASE:.2f}"]["s6"]
        mars = [cells[f"{m:.2f}"]["s6"]["mar"] for m in GRID]
        ok = [x for x in mars if x is not None]
        print(f"{wname}: base(5.00) MAR={base['mar']:.3f} "
              f"cagr={base['cagr_pct']:.1f}% dd={base['maxdd_pct']:.1f}% | "
              f"grid MAR {min(ok):.3f}..{max(ok):.3f} "
              f"(argmax {GRID[mars.index(max(ok))]:.2f})")

    path = os.path.join(OUT_DIR, f"trail_sweep{TAG}.json")
    json.dump(out, open(path, "w"), default=float)
    print(f"wrote {path}")


def _event_returns(b3, b4, w, lev, t0, t1):
    """The blend's per-exit levered return stream, in event order. Same
    arithmetic as blend_curve; kept as returns so the bootstrap can resample
    exits while every grid cell is resampled on ITS OWN stream."""
    evs = sorted([(t.exit_ts, "P", t) for t in b3.trades]
                 + [(t.exit_ts, "T", t) for t in b4.trades])
    p3 = p4 = 1.0
    out = []
    for ts, which, t in evs:
        ratio = t.equity_after / (b3 if which == "P" else b4).cfg.start_equity
        r = (ratio / p3 - 1) * (1 - w) if which == "P" else (ratio / p4 - 1) * w
        if which == "P":
            p3 = ratio
        else:
            p4 = ratio
        if t0 <= ts <= t1:
            out.append([ts, lev * r, which])
    return out


if __name__ == "__main__":
    main()
