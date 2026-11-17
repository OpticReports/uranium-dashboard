# B.5 Enhanced: weights, rebalance cadence and fill delay (2026-11-16/17)

Three studies run before IBKR account ...3321 went live on B.5. Frozen outputs only; scripts included,
raw price caches not committed (re-fetch from Yahoo / Ken French / FRED / CBOE).

## Decisions taken (Casey)
- Weights: v1.2 without CAOS, rounded: AVUV 23.5, PHYS 23.5, QUAL 15.3, KMLM 14.1, AVDV 11.8, AVEM 5.9,
  TAIL 5.9. Rebalanced on ...3321 on 2026-11-16.
- Cadence: month-end check, +/-20% relative band, whole book back to target, fill next trading day.
- Taxes: none (Act 60).

## 1. v1.0 vs v1.2 (v10_vs_v12/) - counter-agents: 2x PASS WITH CORRECTIONS, applied
Matched window 2023-03-07..2026-11-13: v1.0 CAGR 15.0% / Sharpe 0.91 / maxDD -9.5%; v1.2 13.5% / 0.95 /
-7.4%; v1.2 weights without CAOS 15.1% / 0.95 / -8.7%. Sharpe gap +0.04, 90% CI [-0.09, +0.16]: noise.
CAOS behaved like T-bills (4.8% vs 4.6%). The register's "IMPROVED" for v1.2 came from an unmatched,
calmer window (2023+ vs 2017+).

## 2. Check cadence (cadence/) - counter-agents: 2x PASS WITH CORRECTIONS, applied
Daily, weekly, month-end, quarter-end and annual checks are indistinguishable (every bootstrap interval
contains zero; ~+/-40 bps/yr cannot be ruled out). Daily trailed month-end slightly in every window
(-2 / -35 / -15 bps/yr) and had a 1.4-pt deeper drawdown in the proxied 2017+ window (rebalanced into
March 2020 twice). Rebalancing vs buy-and-hold: +22..+65 bps/yr in history, not supported by resampling.

## 3. Fill delay k=3-5 days after the trigger (delay/) - pre-registered; counter-agents: 2x PASS WITH CORRECTIONS
Verdict per PREREG: NOT PROVEN in every trigger family; the live rule stays k=1.
- Universe A (B.5 analogues, 1990-2026, 434 month-end events): k=4 vs k=1 +2.4 bps/yr, CI [-5.4, +10.9].
- Universe B (stock/bond/gold, 1976-2026, 606 events): +4.5 bps/yr, Holm p 0.19.
- CANDIDATE EDGE, DECAYED (EDGE rule): in the FIRST half of both samples the month-end k=4 delay was
  positive and significant - A 1990-2008 +11.2 bps/yr (Holm p 0.001, CI [2.0, 17.7]); B 1976-2001
  +10.0 bps/yr (Holm p 0.013, CI [1.6, 20.6]); pre-2013 +9.0..9.3 bps/yr in both; same sign after up- and
  down-breaches; survives removing gold. It is gone in the second half (A -6.4, B -0.9 bps/yr). Using it
  would need evidence it has come back; at ~10 bps/yr on ~$230k it is worth ~$230/yr at best.
- Deviations (logged in DEVIATIONS.md): LBMA gold was unobtainable (HTTP 403/404) so COMEX front-month
  was used 1976-2004; no daily EM file (AVEM folded into intl small value); the KMLM analogue (US
  equity, 10y, gold, USD trend) does not match KMLM's composition (no equity leg; commodities,
  currencies, global bonds) and correlates 0.34 daily. Reviewers: none of these can flip the verdict.

Not modelled anywhere: taxes (Act 60), IBKR per-order minimums, intraday execution, partial fills.
All results in-sample; none is a forecast.
