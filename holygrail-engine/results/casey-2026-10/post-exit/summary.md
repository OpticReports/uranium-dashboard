# Analysis B: the $18M post-exit plan vs Dalio-balanced alternatives (2026-10-06)

> **Status:** verified by two independent counter-agents (data integrity; independent recompute). Numbers are
> post-repair (financing re-priced from IBKR's own tiers; two rounding slips corrected). **Superseded for
> recommendations** by `../no-leverage/`: Casey ruled out leverage, and SPCX is a crash-contingent $0.5–1M SpaceX
> buy, not a standing $3.6M basket. Kept as the record of the levered comparison.

Run (from holygrail-engine/): `python results/casey-2026-10/post-exit/analysis.py` (HG_OFFLINE=1 for cache-only).
"Composer HG symphony" is Casey's 3x-momentum strategy, not Dalio's Holy Grail.

## Results first

| | PLAN (as written) | ALT-1 (minimal fix) | ALT-2 (Dalio-balanced, geared) |
|---|---|---|---|
| What it is | 80%: Composer 30 / SPY 50 / Treasury 20; 20%: SPCX | Treasury → IEF + TIP; SPCX capped at 20% of risk ($3.6M → $1.71M) | quadrant-balanced core 70% of risk, Composer 15%, SPCX 15%, geared to 15% vol |
| Ex-ante vol | 16.5% | 14.5% | 15.0% |
| DR² (stream / sleeve) | 2.5 / 1.4 | 2.6 / 1.6 | 4.0 / 3.1 |
| R² of daily returns on QQQ | 0.83 | 0.79 | 0.52 |
| Box risk (g↑ / g↓ / i↑ / i↓), balance | 51 / −1 / 0 / 50, 0.32 | —, 0.33 | 35 / 14 / 15 / 35, 0.73 |
| PRIOR-driven mean / Sharpe at 15% | 8.2% / 0.28 | 8.3% / 0.29 | 10.45% / 0.43 |
| Gross / borrowed | 1.0 / 0 | 1.0 / 0 | 2.09x / ~$19.6M |
| Replay troughs on $18M (2000-02 / 2008 / 2020 / 2022) | −8.8 / −7.3 / −4.7 / −4.4M | −7.3 / −6.8 / −4.3 / −4.2M | −4.8 / −8.0 / −5.9 / −6.1M |
| Worst calendar year 2006–26 (proxy, hindsight) | −30.4% (2008) | −28.7% (2008) | −30.4% (2022, −$5.47M) |
| Bootstrap p5 year, base / correlation stress | −$2.6M / −$3.5M | −$2.1M / −$3.0M | −$1.79M / −$3.83M |

- **PLAN is one bet.** 83% of its daily variance is QQQ beta and ~100% of its risk sits in equity-like sleeves
  (SPY 34% / Composer 26% / SPCX 41% / Treasury 0% of risk on 40 / 24 / 20 / 16% of dollars). Other effective-bet
  measures for PLAN: 1/ΣPRC² 5.4.
- **ALT-2 delivers Dalio's structure** (DR² 4.0, balance 0.73) but only by borrowing ~$19.6M with TIPS at 85% of NAV;
  the four-box algebra gives gold zero weight. It wins a 2000–02 tech bust and loses more than PLAN in 2008, 2020,
  2022 and the correlation-stress bootstrap.
- **ALT-2 unlevered (post-hoc):** 7.2% vol, prior mean 7.4%, Sharpe 0.48; replay troughs −11 / −24 / −16 / −16%;
  bootstrap p5 year −2.3%.
- **Composer is the weakest input:** 2.87 in-sample Sharpe over the 3y window becomes ~0.14 under the zero-alpha
  prior; its beta proxy (R² 0.24) misses the HG symphony badly, so replay rows bracket rather than measure its risk.
- **Financing (repaired):** IBKR >$1M tier ≈ DTB3 + 0.62%; blended 0.635% on ALT-2's loan.

## HONESTY BOX (frozen 2026-10-06)

- Basis: daily mark-to-market; sample covariance of daily simple returns 2023-10-02..2026-09-30 (no 2008 or 2022
  inside); longest-common-window check within 0.4pp of vol and 0.1 of DR².
- Expected returns are PRIOR-DRIVEN, not forecasts: betas rf 4.01% + 0.30 × vol; single names and symphonies get zero
  alpha. ALT-2 outranks PLAN on Sharpe because of the equally-good-betas prior (at beta Sharpe 0.20 the gap is ~1.2pp).
- Backtests are constant-mix replays of today's weights (hindsight). Backtest A uses Composer IN-SAMPLE backtests
  plus live tails and an AI basket (NVDA/AVGO/TSLA/ISRG/RKLB) picked because it won — illustrative only.
  Backtest B and the replays use proxies (Composer = QQQ/TLT/GLD/DBC beta proxy; SPCX = QQQ in 2000–02 and 2008).
- The forward bootstrap resamples 2023–26 daily returns re-centred on the prior means: in-sample, not a forecast.
- Not modelled: taxes; capacity of 3x ETFs/symphonies at $4.32M; margin calls; futures/repo implementation of 2x
  TIPS and commodities; the Organics Ocean sale failing or pricing below $18M.
- Post-hoc (labelled in metrics.json): the unlevered ALT-2 row, the SPCX/SpaceX note, the c7 display change.
