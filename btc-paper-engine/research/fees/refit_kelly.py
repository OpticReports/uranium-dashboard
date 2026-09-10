"""Kelly re-fit on fee-corrected returns — see PREREG.md §4.4.

Reuses the SHIPPED pipeline (app.engine.kelly.analyze) and the SHIPPED blend
construction (scripts/bench_blend.blend_curve) unchanged. Re-implementing
either would make the corrected numbers incomparable to KELLY.md's, which is
the whole point of the comparison.

    python3 research/fees/refit_kelly.py <bars_csv> <out_dir>
"""
from __future__ import annotations
import csv, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

import app.engine.core as core                                    # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze                              # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)
from bench_blend import blend_curve                               # noqa: E402

BARS_CSV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE

HL_TAKER = 4.32
BASELINE_FEE = 6.0
LIVE_FEE = 2 * HL_TAKER          # frac 1.00: all four live entries crossed
START = 1640995200               # full window, as registered
_OrigPosition = core.Position


def load(path):
    with open(path) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


def replay_at(bars, fee_bps):
    def _P(*a, **kw):
        kw.setdefault("fee_bps", fee_bps)
        return _OrigPosition(*a, **kw)
    core.Position = _P
    try:
        return run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                          RESEARCH_TRADE, start_ts=START, cash_apy=0.0)
    finally:
        core.Position = _OrigPosition


def book_steps(book):
    """Per-step equity returns, the input KELLY.md's pipeline expects."""
    return [t.equity_after / t.equity_before - 1
            for t in book.trades if t.equity_before]


def blend_steps(b3, b4, w, lev):
    curve = blend_curve(b3, b4, w, lev, START, 10 ** 12)
    nav = [c[1] for c in curve]
    return [nav[i] / nav[i - 1] - 1 for i in range(1, len(nav))]


def main():
    bars = load(BARS_CSV)
    report = {}
    for arm, fee in (("baseline_6.0", BASELINE_FEE), ("live_8.64", LIVE_FEE)):
        res = replay_at(bars, fee)
        b3, b4 = res.books["S3"], res.books["S4"]
        series = {
            "S1": book_steps(res.books["S1"]),
            "S2": book_steps(res.books["S2"]),
            "S3": book_steps(b3),
            "S4": book_steps(b4),
            "S5": blend_steps(b3, b4, 0.25, 1.5),
            "S6": blend_steps(b3, b4, 0.25, 2.0),
        }
        report[arm] = {k: analyze(v, k) for k, v in series.items()}
        print(f"\n=== {arm}  (pullback fee {fee:.2f} bps round trip) ===")
        print(f"{'book':<5} {'n':>4} {'m*':>6} {'p10':>6} {'halfK':>6} "
              f"{'c*':>6} {'ddm30':>7} {'REC':>6}  verdict")
        for k in ("S1", "S2", "S3", "S4", "S5", "S6"):
            a = report[arm][k]
            if "verdict" in a and a.get("n", 0) < 30:
                print(f"{k:<5} {a.get('n', 0):>4}  {a['verdict']}"); continue
            print(f"{k:<5} {a['n']:>4} {a['kelly_m']:>6.2f} "
                  f"{a['bootstrap']['p10']:>6.2f} {a['half_kelly_m']:>6.2f} "
                  f"{a['shrinkage_c_star']:>6.2f} "
                  f"{a['dd_constrained']['p_maxdd30_le_10pct']:>7.2f} "
                  f"{a['recommended_m']:>6.2f}  {a['verdict'][:46]}")
    with open(os.path.join(OUT, "kelly_refit.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)

    print("\n=== DECISION (PREREG §5), on S6 ===")
    b = report["baseline_6.0"]["S6"]["recommended_m"]
    c = report["live_8.64"]["S6"]["recommended_m"]
    print(f"  S6 recommended m: baseline {b:.2f}  ->  fee-corrected {c:.2f} "
          f"({(c - b) / b * 100:+.1f}%)")
    ladder = [0.135, 0.20, 0.35]
    for rung in ladder:
        print(f"    ladder rung {rung:<5} vs corrected {c:.2f}  -> "
              f"{'INSIDE the envelope' if rung <= c else 'OUTSIDE'}")
    if c > 0.35:
        print("  RULE: ladder proceeds unchanged.")
    elif c >= 0.20:
        print("  RULE: retire the 0.35 rung; stop at 0.20.")
    else:
        print("  RULE: halt the ladder at 0.135 and escalate.")


if __name__ == "__main__":
    main()
