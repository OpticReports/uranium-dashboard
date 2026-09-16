"""What raises return WITHOUT raising drawdown? (Casey, 2026-09-10)

Measures three things on the same fixture and the same corrected fee:
  1. the LEVERAGE ray  - S3 -> S5 -> S6 -> beyond. Moves you ALONG the
     frontier: return and drawdown scale together, MAR ~flat.
  2. the COST lever    - 8.64 bps (what we pay) vs 5.76 (post-only actually
     resting). Pure rate improvement, zero drawdown added.
  3. the CASH lever    - cash_apy 0 vs 0.04 on idle capital. Return added
     between trades, i.e. zero drawdown added.

Exit-step (trade-close) drawdowns throughout - MTM runs deeper. Read the
COMPARISONS, not the levels.

    python3 research/frontier/frontier.py <bars_csv> <out_dir>
"""
from __future__ import annotations
import csv, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)

import app.engine.core as core                                    # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay, book_stats             # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
_OrigPosition = core.Position
FULL_T0 = 1640995200                      # 2022-01-01, the study's window
LIVE_FEE, RESTING_FEE, MODELLED = 8.64, 5.76, 6.00


def load(path):
    with open(path) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


def blend_curve(b3, b4, w, lev):
    """VERBATIM shape from bench_blend.blend_curve (the shipped consumer)."""
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
        eq *= 1 + lev * r
        out.append((ts, eq))
    return out


def curve_stats(curve):
    ts = np.array([c[0] for c in curve], dtype=float)
    nav = np.array([c[1] for c in curve], dtype=float)
    if nav.min() <= 0:                     # levered to ruin
        return {"cagr": float("nan"), "dd": -1.0, "mar": float("nan"),
                "ruined": True}
    yrs = (ts[-1] - ts[0]) / (365.25 * 86400)
    cagr = (nav[-1] / nav[0]) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(nav)
    dd = float((nav / peak - 1).min())
    return {"cagr": cagr * 100, "dd": dd * 100,
            "mar": (cagr / abs(dd)) if dd else float("nan"), "ruined": False}


def run(bars, fee_bps, cash_apy):
    def _P(*a, **kw):
        kw.setdefault("fee_bps", fee_bps)
        return _OrigPosition(*a, **kw)
    core.Position = _P
    try:
        return run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                          start_ts=FULL_T0, cash_apy=cash_apy)
    finally:
        core.Position = _OrigPosition


def main():
    bars = load(BARS_CSV)
    LEVS = [0.5, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
    out = {"levs": LEVS, "rays": {}, "single": {}}

    for label, fee, apy in (("live_fee", LIVE_FEE, 0.0),
                            ("resting_fee", RESTING_FEE, 0.0),
                            ("live_fee_cash4", LIVE_FEE, 0.04),
                            ("both_levers", RESTING_FEE, 0.04)):
        res = run(bars, fee, apy)
        b3, b4 = res.books["S3"], res.books["S4"]
        out["rays"][label] = [curve_stats(blend_curve(b3, b4, 0.25, L))
                              for L in LEVS]
        out["single"][label] = {
            n: {k: v for k, v in book_stats(b).items()
                if k in ("cagr_pct", "mtm_max_dd_pct", "max_dd_pct",
                         "trades", "win_rate")}
            for n, b in res.books.items()}
        print(f"--- {label} (fee {fee}, cash {apy}) ---")
        for L, s in zip(LEVS, out["rays"][label]):
            tag = {1.5: "  <- S5", 2.0: "  <- S6"}.get(L, "")
            if s["ruined"]:
                print(f"  lev {L:<5} RUINED (equity <= 0){tag}")
            else:
                print(f"  lev {L:<5} CAGR {s['cagr']:6.2f}%  DD {s['dd']:7.2f}%"
                      f"  MAR {s['mar']:.3f}{tag}")
        sys.stdout.flush()

    # the two zero-DD levers, measured at the SHIPPED size (S5, lev 1.5)
    i = LEVS.index(1.5)
    base = out["rays"]["live_fee"][i]
    print("\n=== THE TWO LEVERS THAT ARE NOT LEVERAGE (at S5, lev 1.5) ===")
    print(f"  as we trade today   CAGR {base['cagr']:6.2f}%  DD {base['dd']:7.2f}%"
          f"  MAR {base['mar']:.3f}")
    for label, name in (("resting_fee", "post-only actually rests"),
                        ("live_fee_cash4", "4% yield on idle cash"),
                        ("both_levers", "BOTH")):
        s = out["rays"][label][i]
        print(f"  + {name:<24} CAGR {s['cagr']:6.2f}% "
              f"({s['cagr']-base['cagr']:+.2f}pp)  DD {s['dd']:7.2f}% "
              f"({s['dd']-base['dd']:+.2f}pp)  MAR {s['mar']:.3f} "
              f"({s['mar']-base['mar']:+.3f})")

    with open(os.path.join(OUT, "frontier.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nwrote {OUT}/frontier.json")


if __name__ == "__main__":
    main()
