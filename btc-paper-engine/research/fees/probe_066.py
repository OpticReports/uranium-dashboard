"""Robustness probe for the HONESTY BOX: does the binding cell's §5 decision
survive at the REGISTERED 0.66 crossing rate (7.66 bps) instead of the live
1.00 (8.64)?

The 100% crossing rate rests on n=4 fills. PREREG §7 registered 0.66 as the
backtest-derived marketability estimate precisely so the conclusion would not
depend on the 1.00 cell alone. This re-runs the Kelly re-fit at 7.66 on the
2y window (the binding one, and KELLY.md's) under both cash_apy settings.

POST-HOC as a Kelly cell — the fee LEVEL is registered, the re-fit at it is
not. Counted in the trial registry (2 new cells; the 8.64 rows are
reproducibility checks of cells already counted).

    python3 research/fees/probe_066.py <bars_csv>
"""
from __future__ import annotations
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BARS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, "..", "..", "backend", "tests", "fixtures", "bars_4h_btcusd.csv")

sys.path.insert(0, HERE)
sys.argv = ["refit_kelly", BARS]          # refit_kelly reads argv at import
import refit_kelly as R                                           # noqa: E402

bars = R.load(BARS)
start_2y = bars[-1].ts - 730 * 86400

print(f"{'cell':<22} {'S6 rec':>7} {'S5 rec':>7} {'n':>5}")
for fee in (7.66, 8.64):                  # 0.66 registered; 8.64 = live, recheck
    for apy in (0.00, 0.04):
        r = R.cell(bars, fee, start_2y, apy)
        print(f"2y cash{apy:.2f} fee {fee:<5.2f} "
              f"{r['S6']['recommended_m']:>7.2f} {r['S5']['recommended_m']:>7.2f} "
              f"{r['S6']['n']:>5}")
        sys.stdout.flush()
