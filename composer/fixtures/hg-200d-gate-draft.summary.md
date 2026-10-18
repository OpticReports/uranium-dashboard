# HG + SPY 200d gate (cash below) | DRAFT, do not invest — logic tree

- Symphony ID: `hZ6NSYPMQi3N0otU6lY6` (version `NyvFccHtb3Bc1mikyuNk`, created 2026-10-18 14:46 ET)
- Renamed to the ARCHIVE name 2026-10-18 15:37 ET (version `dmi7rPQnND7MU1QX1uY3`, logic unchanged)
- Built from: live HG `mbkiXcuNDjueXpiox5Av` version `bP4mvRy6YHHejuPGUBNY` (unchanged)
- Capital: none. Status: EXECUTED on live HG 2026-10-18 (HG version `2oyXahw1VWpFtV15dhIi`); this symphony
  is kept uninvested as the archive copy, renamed "ARCHIVE: HG 200d gate draft (executed on HG 2026-10-18), do not invest".
- Builder: `research/leverage/build_gate_draft.py`; fidelity: `research/leverage/fidelity_check.py`;
  exhibit: `results/hg-200d-gate-draft-2026-10-18.html`; research: results.md addenda 40, 42, 44, 45.
- Raw definition: [`hg-200d-gate-draft.raw.json`](hg-200d-gate-draft.raw.json) (volatile
  `price`/`dollar_volume` fields stripped).

## The change, and only the change

The live HG tree has two places that hold a trend basket (top-1 RSI(10d) of TQQQ, UPRO, UDOW, SSO, TNA):
the main branch (TQQQ 10d MA above 20d MA and RSI(10d) of TQQQ not above 80) and the secondary branch
(below trend, TQQQ and SOXL not oversold, TQQQ price not below its 20d MA). In the draft each of those two
baskets sits behind one condition:

    if current price of SPY > 200-day moving average price of SPY  ->  the basket, as before
    else                                                           ->  BIL

Everything else is byte-for-byte the live tree: the long-vol pop (RSI(10d) of TQQQ > 80 -> bottom-RSI of
UVXY/VIXY/VIXM), the dip-buys (RSI(10d) of TQQQ < 30 -> bottom-RSI of TECL/QLD/LABU/USD/SMH, still 3x), the
two existing BIL defaults, daily rebalance. 51 nodes became 63; every original node keeps its id.

## Composer backtest (v2, reg + TAF fees, 5 bp slippage, 2015-06-11..2026-10-16)

| | live HG | draft |
|---|---|---|
| CAGR (Composer) | 103.3% | 85.8% |
| Sharpe (Composer's field) | 1.73 | 1.62 |
| Max drawdown | 35.8% | 35.8% |

Fidelity against the gate lab's model (`T200 SPY>200d -> cash [trend only]`): daily-return correlation
0.9999, drift +0.20%/yr (the live tree shows the same drift, so it is the engine, not the gate), the same
holding on 2,845 of 2,847 days, and the same 204 cash days out of 2,004 trend days. Composer evaluates the
gate on adjusted prices (an unadjusted-close gate would give 234 cash days).
