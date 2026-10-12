# B.5 Enhanced vs SPY — trailing 12 months

Buy at the **2025-10-09 close**, mark at the **2026-10-09 close** (last complete
session; 2026-10-12 was intraday when this ran). 251 return days.

> **STATUS: counter-agent verification PENDING.** Do not act on these numbers
> until the verdict section below is filled in.

![B.5 vs SPY](fig_b5_vs_spy_12m.png)

## Result (frozen)

| | B.5 Enhanced (v1.0, tail=TAIL) | SPY |
|---|---|---|
| Total return | **+17.80%** | **+17.24%** |
| Excess vs SPY | +0.55pp | — |
| Ann. vol | 12.6% | 13.0% |
| Max drawdown | −8.5% (Mar 2 → Mar 20, 2026) | −8.9% (Jan 27 → Mar 30, 2026) |
| Sharpe (excess of BIL) | 1.07 | 1.01 |
| Beta / corr to SPY (daily) | 0.69 / 0.71 | 1 / 1 |
| Monthly up / down capture | 0.92 / 0.69 | — |
| Months beating SPY | 6 / 13 (first and last partial) | — |

Tracking error 9.7%/yr → information ratio 0.06: a statistical tie.

**Path:** B.5 led by +14.9pp on 2026-03-02 (B.5 +17.5% vs SPY +2.6%). From
Mar 2 to Oct 9: B.5 +0.3% vs SPY +14.3%. Gold round-tripped (PHYS +34.7% at
its Jan 29 peak → +4.3% at the end) and SPY ran +10.5% / +5.3% in Apr / May.

**Contribution by holding** (Carino-linked, pre-cost; sums to +17.89pp; costs
−0.10pp → net +17.80%):

| holding | weight | 12m TR | contribution |
|---|---|---|---|
| AVUV | 25% | +22.9% | +5.82pp |
| AVDV | 19% | +25.7% | +4.83pp |
| KMLM | 14% | +21.1% | +2.89pp |
| AVEM | 10% | +27.6% | +2.68pp |
| QUAL | 9% | +17.1% | +1.50pp |
| PHYS | 18% | +4.3% | +0.97pp |
| TAIL | 5% | −14.8% | −0.78pp |

One band rebalance: 2026-05-29 (TAIL drifted to 3.9% vs its 5% target,
outside the ±20% relative band).

## Sensitivities

| variant | B.5 | SPY | excess |
|---|---|---|---|
| **primary** (Yahoo, ±20% bands) | +17.80% | +17.24% | +0.55pp |
| buy-and-hold, same weights | +17.82% | +17.24% | +0.57pp |
| tail = NONE (5% pro-rata to the rest) | +19.54% | +17.24% | +2.29pp |
| older thesis-page weights (MTUM 8%, 3% cash via BIL) | +19.65% | +17.24% | +2.41pp |
| month-end window (2025-09-30 → 2026-09-30) | +17.56% | +15.70% | +1.86pp |
| FMP prices instead of Yahoo | +17.79% | +17.24% | +0.55pp |

## Honesty box

- **Measurement basis:** daily close-to-close MTM, total return (distributions
  reinvested at the ex-date via adjusted closes). Simulated from target weights
  at the start close. This is **not** the live account's holdings, fills or timing.
- **Weights:** the `config/portfolio.yaml` v1.0 seed (`tail_sleeve.current` =
  TAIL). The LIVE version in the Render register can't be read from here. If a
  v1.x was promoted, the definition rows above show the range.
- **Costs:** the platform's one-way bps model, including the entry trade
  (−0.10pp in total). Not modeled: taxes (Act 60), FX, cash drag, and the bot
  sleeve (B.5 is the 80% sleeve only).
- **Sample:** one 12-month window, and it is sensitive to the endpoints:
  moving them by 7 sessions turns +0.55pp into +1.86pp. Not a forecast.
- **Engine:** threshold mode doesn't implement the 12-month calendar fallback
  in `portfolio.yaml`. It wouldn't have fired anyway, because the band
  rebalanced on 2026-05-29.
- **Data:** Yahoo adjclose is the primary source and FMP dividend-adjusted the
  cross-check. Each ticker's 12m TR agrees within 6bp, and no daily return
  differs by more than 50bp (`xcheck.py`). Distribution amounts against an
  independent published source: PENDING (counter-agent).

## Counter-agent verification

PENDING.

## Reproduce

```bash
pip install -e "barbell-lab[dev]" matplotlib
cd barbell-lab/research/b5_vs_spy_12m
python -I b5_vs_spy_12m.py . results.json        # from the frozen prices.parquet
python -I make_charts.py results.json fig_b5_vs_spy_12m.png
python -I xcheck.py; python -I explain.py
# fetch.py <dir> re-downloads into <dir>; point it elsewhere to keep the frozen
# snapshot (vendor adjusted closes re-base after every new distribution).
```

Research only: no service code changed, nothing to redeploy.
