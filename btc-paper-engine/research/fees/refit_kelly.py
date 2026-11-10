"""Kelly re-fit on fee-corrected returns — PREREG §4.4, as amended.

AMENDMENT 2. The first cut ran ONE cell (full window, cash_apy 0.0) and
reported its answer as if it were the answer. It is not: a counter-agent
showed the S6 recommendation moves by more across the cash_apy axis than the
fee correction moves it at all, and that on KELLY.md's own window the
corrected S6 lands in a band that FLIPS the §5 decision. Neither the Kelly
window nor cash_apy was pre-registered. Both are declared now and all four
cells are reported.

Blend steps are the SHIPPED consumer's, replicated verbatim from
main.py:501-513 (it is nested inside the /kelly/compare endpoint and cannot
be imported). The first cut rebuilt them from bench_blend.blend_curve's NAV,
which silently DROPPED the first step (n=317 vs the shipped 318).

    python3 research/fees/refit_kelly.py <bars_csv> <out_dir>
"""
from __future__ import annotations
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)

import app.engine.core as core                                    # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze                              # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
BASELINE_FEE, LIVE_FEE = 6.0, 8.64
LADDER = [0.135, 0.20, 0.35]
_OrigPosition = core.Position


def load(path):
    with open(path) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


def blend_steps(b3, b4, w_trend, lev):
    """VERBATIM from main.py:501-513, the code that produced KELLY.md."""
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity)
                  for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity)
                    for t in b4.trades])
    p3 = p4 = 1.0
    steps = []
    for _, which, ratio in evs:
        if which == "P":
            steps.append(lev * (ratio / p3 - 1) * (1 - w_trend)); p3 = ratio
        else:
            steps.append(lev * (ratio / p4 - 1) * w_trend); p4 = ratio
    return steps


def cell(bars, fee_bps, start_ts, cash_apy):
    def _P(*a, **kw):
        kw.setdefault("fee_bps", fee_bps)
        return _OrigPosition(*a, **kw)
    core.Position = _P
    try:
        res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                         start_ts=start_ts, cash_apy=cash_apy)
    finally:
        core.Position = _OrigPosition
    b3, b4 = res.books["S3"], res.books["S4"]
    streams = {n: [t.equity_after / t.equity_before - 1 for t in b.trades
                   if t.equity_before > 0] for n, b in res.books.items()}
    streams["S5"] = blend_steps(b3, b4, 0.25, 1.5)
    streams["S6"] = blend_steps(b3, b4, 0.25, 2.0)
    return {k: analyze(v, k) for k, v in streams.items()}


def main():
    bars = load(BARS_CSV)
    last = bars[-1].ts
    CELLS = {                                    # declared in AMENDMENT 2
        "2y_cash0.04":   (last - 730 * 86400, 0.04),   # = KELLY.md's config
        "2y_cash0.00":   (last - 730 * 86400, 0.00),
        "full_cash0.04": (1640995200, 0.04),
        "full_cash0.00": (1640995200, 0.00),           # what the 1st cut ran
    }
    report, rows = {}, []
    for cname, (start, apy) in CELLS.items():
        report[cname] = {}
        for arm, fee in (("baseline_6.0", BASELINE_FEE), ("live_8.64", LIVE_FEE)):
            report[cname][arm] = cell(bars, fee, start, apy)
        b = report[cname]["baseline_6.0"]["S6"]["recommended_m"]
        c = report[cname]["live_8.64"]["S6"]["recommended_m"]
        top = max(r for r in LADDER if r <= c) if any(r <= c for r in LADDER) else None
        rule = ("proceed unchanged" if c > 0.35 else
                "retire the 0.35 rung, stop at 0.20" if c >= 0.20 else
                "HALT the ladder at 0.135 and escalate")
        rows.append((cname, report[cname]["baseline_6.0"]["S6"]["n"], b, c,
                     (c - b) / b * 100 if b else 0, top, rule))
    with open(os.path.join(OUT, "kelly_refit.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)

    print("=== HARNESS VALIDATION: does 2y/cash0.04 reproduce KELLY.md? ===")
    k = report["2y_cash0.04"]["baseline_6.0"]
    print(f"  KELLY.md published: S3 rec 0.60 | S4 killed 0.0 | S6 rec 0.70")
    print(f"  reproduced here   : S3 rec {k['S3']['recommended_m']:.2f} | "
          f"S4 rec {k['S4']['recommended_m']:.2f} | S6 rec {k['S6']['recommended_m']:.2f}"
          f"   (n: S3 {k['S3']['n']}, S4 {k['S4']['n']}, S6 {k['S6']['n']})")

    print("\n=== S6 RECOMMENDED m ACROSS ALL FOUR CELLS ===")
    print(f"{'cell':<15} {'n':>4} {'baseline':>9} {'corrected':>10} "
          f"{'fee effect':>11} {'top rung':>9}  §5 decision")
    for cname, n, b, c, pct, top, rule in rows:
        print(f"{cname:<15} {n:>4} {b:>9.2f} {c:>10.2f} {pct:>10.1f}% "
              f"{str(top):>9}  {rule}")
    print("\n  The four cells DISAGREE on the §5 decision. See RESEARCH_FEES.md.")


if __name__ == "__main__":
    main()
