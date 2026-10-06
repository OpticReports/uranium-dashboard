# Dalio Holy Grail — replication study, 2026-10

Run 2026-10-06 · `python results/study-2026-10/study.py` (from `holygrail-engine/`) · parameters frozen
in `predeclared_params.json` before any result · numbers below are copied from `metrics.json` and the CSVs.

## Results first

1. **The arithmetic is exact.** 15 uncorrelated 18%-vol bets: 8.050% / 5.692% / 4.648% at N = 5/10/15;
   return-to-risk 0.333 → 1.291 = **3.87x (√15)**. Dalio's "4.3x" divides by 0.3 instead of 0.333.
2. **Liquid markets hold about 2.3 independent bets, not 15.** 11-asset ERC portfolio, monthly
   2004-12..2026-09: DR² **2.30** (90% bootstrap CI 1.99–2.74), mean pairwise ρ 0.40. Calm months 2.47,
   stress months 2.20 (2.11 with weights held). Rolling 36m DR²: 1.53 (2025-07) to 5.55 (2012-12),
   median 2.54; 2.23 at 2008-12, 3.29 at 2020-03, 1.98 at 2022-12.
3. **The Holy Grail identity holds in data.** Mean stream Sharpe 0.31 × DR 1.52 = 0.47 vs realised
   ERC Sharpe 0.51. Diversification multiplied Sharpe by ~1.5x — the √N_eff it had, not √15.
4. **But "equally good" failed in this window, so balance lost to stocks.** Walk-forward 2007-11..2026-09:

| Strategy | CAGR | Vol | Sharpe | Max DD |
|---|---|---|---|---|
| US equity (VFINX) | 11.1% | 15.6% | 0.66 | −48.8% |
| 60/40 | 7.9% | 9.5% | 0.69 | −29.6% |
| Equal weight (11) | 5.3% | 9.8% | 0.44 | −30.1% |
| ERC unlevered | 4.9% | 7.2% | 0.51 | −17.2% |
| ERC geared to 10% | 4.3% | 12.5% | 0.29 | −38.9% |
| Quadrant (All-Weather-style) geared to 10% | 4.0% | 12.4% | 0.27 | −38.1% |
| ERC geared to equity vol | 6.6% | 17.2% | 0.38 | −44.2% |

   US equity's 0.66 Sharpe vs 0.10–0.53 for the other ten streams (SE ≈ 0.24 each) broke the premise.
5. **Gearing on a trailing 36m vol estimate cost ~2.4pp/yr.** The vol target levered ERC to
   **2.5–2.7x** (Quadrant **2.6–2.8x**) going into 2008, then de-levered to ~1.2–1.4x for the recovery.
   Holding the same average leverage constant (1.72x ERC / 1.86x Quadrant — hindsight, not a strategy)
   gives 6.7% / Sharpe 0.48 and 6.3% / 0.44. Corr(leverage, next-month excess return) −0.18.
6. **Regime decides the stock/bond balance.** ERC(stocks, bonds) geared to 10%, 1994-10..2026-09: 9.5%,
   Sharpe 0.67 (60/40 8.6% / 0.69). 2000–21 (stock-bond ρ −0.30): Sharpe 0.82 vs 60/40 0.61.
   2022–26 (ρ +0.52): −1.8%/yr, max DD −31.5%.
7. **Live implementations track the backtest.** RPAR 2020-01..2026-09: corr 0.92, TE 5.4%, cum +23.8% vs
   +22.9%. ALLW 2025-04..2026-09 (18 months — too short to conclude): corr 0.97, cum +18.8% vs +10.8%.
8. **Forward (bootstrap of 2004–26 history, NOT a forecast).** 10y CAGR p5/p50/p95: US equity
   2.4/11.6/18.4%; ERC@10% 1.3/6.5/11.7%; Quadrant@10% 0.8/6.0/11.4%. Max-DD p5 −53.4 / −34.0 / −34.5%.
   Correlation stress (post-hoc, toward the monthly 2022 matrix): P(10y loss) 3.5–4.1%, max-DD p5 ≈ −40%.

**Reading:** the math of the Holy Grail is a certainty; its payoff is conditional on (a) streams that are
really comparable in quality, (b) correlations that stay low in the regime you live through, and
(c) gearing that is not timed off a lagging risk estimate. In 2007–26 all three bit.

## HONESTY BOX (frozen 2026-10-06)

- **Basis:** month-end mark-to-market of monthly total returns (Yahoo adjclose, FRED DTB3, fetched
  2026-10-06). Intra-month drawdowns (e.g. March 2020) are invisible, so geared max DDs are understated;
  margin calls and intra-month de-levering are not modelled.
- **Walk-forward vs in-sample:** S3 weights are walk-forward (estimate through t, earn from t+1), but the
  universe, the 60/40 bond leg, PCRIX over DBC and the quadrant map were chosen in 2026 — selection and
  survivorship bias apply. The only walk-forward start (forced by GLD 2004-11 + 36m warm-up) puts peak
  leverage at the GFC onset, which drives the geared verdict; the 1994+ two-asset run gives the opposite
  verdict for 2000–21.
- **S5 is in-sample:** it resamples 2004–26 realised returns, so its centre IS the historical mean
  (US equity median 11.6% vs realised 11.1%). It has no trading costs, and its cash/financing rate is drawn
  from 2004–26 history (mean DTB3 ≈ 1.4%) vs ≈ 4.0% today. Not a forecast.
- **Financing:** DTB3 + 50 bp is futures/institutional-grade. Retail margin at ≈ +150 bp would cost about
  0.7pp/yr more on ERC@10% (average borrowed fraction 0.72).
- **Post-hoc item:** the S5 stress toward the MONTHLY 2022 correlation matrix was added after the declared
  daily-matrix stress proved a near no-op (asynchronous NAVs dilute daily correlation: stock-bond ρ 0.21
  daily vs 0.58 monthly). Labelled as such.
- **Constant-leverage rows** use realised mean leverage (known only ex post): diagnostics, not strategies.
- **Not modelled:** taxes; fund-vs-ETF/futures implementation and fees; currency; daily vol targeting;
  tactical overlays; purchase/redemption fees.
- **Data flags:** VFITX 1993-12-31 unadjusted capital-gains distribution (long-run estimation windows
  only); VEIEX annual returns differ from published by up to ≈1.4pp (2008); the stress rule also flags
  recovery tails (2005, 2009–10, 2023).
- **Verification:** independent counter-agent recompute from raw Yahoo/FRED with its own code (no engine
  calls): PASS WITH FIXES. S1, S2, S3 (US, 60/40, EW, ERC, ERC@10% incl. financing, ERC@equity-vol, worst
  windows, long-run), S4 raw side and S5 reproduce to 4+ decimals or within MC noise; no lookahead, no
  silent splices, no post-hoc tuning beyond the labelled item. Its two blocking items are fixed here:
  this summary/honesty box now exists, and the 2008 leverage is stated as 2.5–2.7x / 2.6–2.8x (it was
  understated as 2.2–2.5x). Its artifact bug (study.py leverage index on the last month) is fixed and the
  gearing decomposition regenerated (reconstruction corr 0.999999). Not independently recomputed: the
  Quadrant allocator rows (S3 row 6, S4 tracking stats, S5 Quadrant).
