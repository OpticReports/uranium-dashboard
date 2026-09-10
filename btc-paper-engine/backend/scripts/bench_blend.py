"""Bench: S5/S6 blend exit-step curves + stats on the carry-study windows.

Regenerates blend_bench.json for research_carry.py's V6 composition and
benchmarks. S5 = 75/25 pullback/donchian @1.5x, S6 = same @2.0x. Each
window is a FRESH run_replay with start_ts=t0 (research basis, cash_apy 0,
engine code path untouched) so no trade carries pre-window P&L across the
boundary — the same self-contained convention the carry variants use.
Curves are EXIT-STEP (trade-close): points are (exit_ts, cumulative blend
factor). MTM runs deeper — see RESEARCH_CARRY.md honesty box.

Usage: python3 bench_blend.py <bars_csv> <out_dir>
"""
import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1]
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
BAR_S = 4 * 3600
HL_START = 1683849600                    # Hyperliquid funding history start


def blend_curve(b3, b4, w, lev, t0, t1):
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
                years=yrs)


def main():
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]
    now = bars[-1].ts + BAR_S
    windows = {"2y": (now - 730 * 86400, now), "3.3y-full-HL": (HL_START, now)}
    out = {}
    for wname, (t0, t1) in windows.items():
        res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                         start_ts=t0, end_ts=t1, cash_apy=0.0)
        b3, b4 = res.books["S3"], res.books["S4"]
        out[wname] = {}
        for nm, w, lv in (("S5", 0.25, 1.5), ("S6", 0.25, 2.0)):
            c = blend_curve(b3, b4, w, lv, t0, t1)
            out[wname][nm] = stats(c)
            out[wname][f"{nm}_curve"] = c
            s = out[wname][nm]
            print(f"{wname} {nm}: tot={s['total_pct']:.1f}% "
                  f"cagr={s['cagr_pct']:.1f}% mdd={s['maxdd_pct']:.1f}% "
                  f"MAR={s['mar']:.2f} ({s['years']:.2f}y, exit-step basis; "
                  f"MTM DD ~1-4pp deeper)")
    path = os.path.join(OUT_DIR, "blend_bench.json")
    json.dump(out, open(path, "w"), default=float)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
