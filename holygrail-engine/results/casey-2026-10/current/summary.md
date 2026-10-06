
# Analysis A: Casey's current book through the Dalio Holy Grail lens (2026-10-06)

> **Status (2026-10-06):** verified by two independent counter-agents (data integrity; independent recompute of 30+ numbers). 7 blocking items found, all fixed and re-checked; numbers below are post-repair. **Superseded for recommendations** by `../no-leverage/` after Casey ruled out leverage. **Pending Casey:** the two 16% BOXX loans are Dominion and Plus One, one still out — the $310,876 plug here overstates the liquid book by $111k-$182k (refreshed in `../no-leverage/`).


"Dalio Holy Grail" means Ray Dalio's diversification framework. The Composer HG symphony is Casey's 3x-momentum strategy; the two are always kept apart.

Run (from holygrail-engine/): python results/casey-2026-10/current/a1_a4.py && python results/casey-2026-10/current/a5_a6.py && python results/casey-2026-10/current/make_metrics.py

Return-free numbers (vol, risk shares, N_eff, box balance) come first. PRIOR = rf + 0.30 x vol, not a forecast.

## Results first

**1. Whole book: one bet.**
- Organics Ocean (OO) is 95% of risk and 61% of net worth. DR^2 1.46, vol 44.6%.
- At OO $10M / $15M / $20M: DR^2 1.56 / 1.37 / 1.28.
- A2 grid (OO vol 40-100% x corr 0.2-0.6): OO risk 88-98%, DR^2 1.30-1.90. The conclusion survives every assumption.
- Investable ex-OO: vol 15.7%, DR^2 3.38, venture basket 69% of risk.

**2. Liquid book ($2.49M), now.**
- Vol 10.4%.
- Correlation-aware family: DR^2 4.00, Meucci PCA 5.11.
- Risk-balance family: 1/sum PRC^2 5.01, min-torsion 12.9.
- After the loans revert to BOXX: 10.3%, DR^2 3.79.

| sleeve | $ share | risk share |
|---|---|---|
| BTC | 11% | 40% |
| Composer HG symphony + KMLM switcher | 7% | 17% |
| gold/silver | 10% | 16% |
| single names | 6% | 15% |
| equity beta | 11% | 11% |
| cash-like | 47% | 1% |
| Crash Convexity | 3% | -0.8% |

Boxes (canonical map): growth up 45%, growth down -0.8%, inflation up 34%, inflation down 22%. Balance score 0.61.

**3. A3. Doing well** (daily corr to the rest of the liquid book / to SPY; mean return on SPY's worst 5% days, SPY -2.2%):

| stream | corr rest / SPY | worst-5% days |
|---|---|---|
| Crash Convexity | -0.18 / -0.25 | +2.0% |
| KMLM ETF | 0.04 / -0.05 | 0.0% |
| ETH carry (assumption) | 0.03 / 0.02 | n/a |
| Composer KMLM switcher | 0.15 / 0.28 | +1.0% |
| VIX Harvester | 0.18 / 0.11 | -0.1% |
| BTC | 0.33 / 0.35 | -2.7% |
| physical metals | 0.38 / 0.27 | -0.9% |

Private credit is assumption-driven (film corr to SPY 0.21).

**4. A4. Needs work.**
- BTC is 40% of risk.
- Composer HG symphony overlap: 0.59 with SPY, 0.56 with QQQ, 0.37 with TSLA, 0.29 with BTC, 0.28 with the KMLM switcher. KMLM ETF is <=0.10 to everything.
- The growth-down box is empty.
- Cash-like is 47% ($1.18M); the non-cash part runs at 19.8%. Deploying ~$580k reaches 15% with no borrowing, but keeps BTC at 40% of risk. Net of the sheet's $435,200 committed cash only ~$249k is free; once commitments are paid the liquid book is $2.05M at 12.6% vol.

**5. A5. Moves**

| move | vol | DR^2 | 1/sum PRC^2 | balance | BTC risk | PRIOR exp @15% (0.30 / alpha-haircut) |
|---|---|---|---|---|---|---|
| now | 10.4% | 4.00 | 5.0 | 0.61 | 40% | 12.7% / 6.3% |
| M0 loans to BOXX | 10.3% | 3.79 | 4.9 | 0.61 | 41% | 12.7% / 6.4% |
| M1 +$250k TLT | 10.6% | 4.36 | 5.4 | 0.64 | 39% | 13.1% / 6.9% |
| M2 +$200k TIP | 10.5% | 4.09 | 5.1 | 0.62 | 40% | 12.8% / 6.5% |
| M3 +$150k DBC | 10.7% | 4.20 | 5.4 | 0.61 | 39% | 12.9% / 6.7% |
| M4 halve TSLA/FTZFF/SHAZ | 9.8% | 3.80 | 4.4 | 0.58 | 44% | 12.4% / 6.5% |
| M5 sell $139.4k BTC | 8.5% | 4.51 | 9.4 | 0.66 | 20% | 13.2% / 6.9% |
| M6 HG symphony + KMLM switcher $184k->$120k (+$30k Crash) | 9.8% | 4.08 | 4.4 | 0.58 | 44% | 12.7% / 6.5% |
| M7 +$100k KMLM | 10.4% | 4.16 | 5.1 | 0.61 | 40% | 12.9% / 6.5% |
| M8 gear core 1.5x | 11.0% | 3.91 | 5.6 | 0.64 | 37% | 12.6% / 6.6% |
| M9 (alt) +$250k ALLW replica | 11.0% | 3.91 | 5.8 | 0.64 | 37% | 12.8% / 6.8% |
| cumulative M0-M8 | 8.9% | 5.09 | 11.1 | 0.72 | 17% | 13.7% / 9.1% |

- Trimming the small single names lowers DR^2.
- Bonds fill the growth-down box only when levered: 1% after M1-M3, 4% after M0-M8.

**6. A6. Proposed books** (gross / borrowed / vol / DR^2 / balance / BTC risk / PRIOR exp at 0.30, 0.25, alpha-haircut):

| book | gross | borrowed | vol | DR^2 | balance | BTC risk | PRIOR exp |
|---|---|---|---|---|---|---|---|
| current @15% (cash deployed) | 0.82 | 0 | 15% | 3.8 | 0.61 | 41% | 12.7 / 11.3 / 6.4% |
| v1 pre-declared (60% core risk-budgeted) | 2.66x | $4.18M | 14.9% | 6.06 | 0.89 | 12% | 14.2 / 12.2 / 9.0% |
| v2 POST-HOC (alpha by standalone vol, gold held, cap 2x) | 2.0x (binds) | $2.55M | 13.5% | 3.72 | 0.85 | 4.5% | 11.3 / 9.9 / 9.5% (15% NOT attainable under the 2x cap) |

- v1 is infeasible: TIPS 91% of NAV, gold $0, Crash Convexity x5.8, VIX Harvester x8.
- v2 holdings: equity core $662k, TLT $767k, TIP $1.96M, DBC $757k, gold/silver $248k, BTC $92k, Composer HG symphony + KMLM switcher $91k, Crash Convexity $60k, VIX Harvester $65k, KMLM $188k, single names $49k, margin -$2.55M.

Gearing routes for v2 (spread over rf, yearly cost):

| route | spread | yearly cost | note |
|---|---|---|---|
| futures | ~0.4% | ~$10k | low confidence; no TIPS future |
| IBKR margin | 0.74% | $18.8k | 5.38 / 4.88 / 4.63% tiers (v1: 0.69%, $28.9k) |
| RSSB | ~0.7% | ~$18k | |
| ALLW | ~1.28% | ~$33k | |
| UPAR | ~1.26% | ~$32k | |

**7. Backtests** (CAGR / Sharpe / maxDD):

| book | A: 2024-05..2026-09, IN-SAMPLE (Composer = backtests before live: HG 2025-12-05; KMLM/Crash 2026-07-07; VIX 2026-07-22) | B: 2007-05..2026-09, proxies/replicas (replica betas fit on the full sample) |
|---|---|---|
| current constant (hindsight) | 24.5% / 1.71 / -7% | 12.7% / 1.09 / -22% |
| current @15% | 34.6% / 1.71 / -10% | 17.8% / 1.09 / -31% |
| current ex-Composer | 13.7% / 0.97 / -8% | 9.7% / 0.90 / -19% |
| v1 walk-forward | 30.5% / 1.40 / -15% (ex-Composer 6.1% / 0.19 / -15%) | 6.1% / 0.53 / -29% (ex-Composer 6.4% / 0.37 / -43%) |
| v2 walk-forward | 17.9% / 0.96 / -12% | 6.9% / 0.52 / -34% |
| SPY | 18.7% / 0.88 / -19% | 10.7% / 0.54 / -55% |
| 60/40 | — | 7.9% / 0.62 / -33% |

Stress replays, max drawdown (2008 / 2020 / 2022):

| book | 2008 | 2020 | 2022 |
|---|---|---|---|
| current | -19.6% | -14.4% | -12.5% |
| current @15% | -28.7% | -21.0% | -18.2% |
| v1 | -39.8% | -30.1% | -22.8% |
| v2 | -40.0% | -30.8% | -29.2% |
| SPY | -55.2% | -33.7% | -24.5% |

Forward (prior-centred bootstrap, 10y; median CAGR / p5 max DD):

| book | median CAGR | p5 max DD |
|---|---|---|
| current | 10.1% | -28% |
| current @15% | 12.6% | -41% |
| v1 | 14.4% | -48% |
| v2 | 11.2% | -49% |
| SPY | 7.4% | -59% |

**Reading:**
- The measured problems do not depend on the prior: BTC concentration, the empty growth-down box, idle cash, and OO dominance.
- The cheap fixes are M5, M1 and M7.
- A balanced 15% book needs ~2x gross. That leverage hurt in 2008 and 2022, and it only pays under Dalio's own prior (alphas ~0: ~+3pp/yr at equal risk).

## HONESTY BOX

Frozen 2026-10-06.

Basis
- Covariance: daily simple returns, trailing 3y (2023-10-09..2026-09-30, n=700), Ledoit-Wolf constant-correlation (shrinkage 0.08), engine active-intersection calendar (~235 obs/yr). rf: FRED DTB3 4.01% (2026-10-02).
- Robustness: longest common window (2023-04-20..), weekly, sample covariance. Headline vol and DR^2 move by <=0.6 and BTC stays 40-43% of risk.
- Backtests: daily mark-to-market, monthly rebalance, 5 bp turnover cost, 0.92% financing spread. Stress replays: today's weights, buy-and-hold, borrowing at DTB3 with no spread.
- Measurement: everything goes through the engine's public API (book_from_dict, prepare_moments, scorecard, quadrant_balance, risk_budget_weights, run_backtest, replay_scenario, run_forward). The book YAML was not modified; variants are in-memory edits.

In-sample vs walk-forward
- The current-mix backtests replay today's weights: HINDSIGHT.
- Proposals v1 and v2 are walk-forward (252-day window, monthly re-solve), but their universe and rules were chosen in 2026.
- The forward bootstrap resamples 2006-26 weekly returns (in-sample shape: tails, clustering, co-movement), re-centred on the PRIOR means. It is not a forecast.

Pre-declared vs post-hoc
- All parameters were frozen in predeclared_params.json before results.
- POST-HOC and logged:
  - v2: written after v1 proved infeasible, declared before any v2 number (post_hoc_v2.json).
  - The 'current @15%' and 'current ex-Composer' diagnostics.
- v1 is reported unchanged.

Expected returns
- Every return-dependent number is PRIOR-DRIVEN: rf + 0.30 x own vol (Dalio '.3'; Bridgewater ETRR 2011 betas Sharpe 0.2-0.3, factcheck CONFIRMED).
- Shown with sensitivities at Sharpe 0.25 and with an alpha haircut (Composer, BTC, single names at 0; ETRR: alphas 'slightly negative on average').
- In-sample means feed nothing.

Composer
- Series are IN-SAMPLE backtests before each live start, then live deposit-adjusted returns (HG symphony from 2025-12-05; the others have only 53-64 live days).
- The VIX Harvester's live-vs-backtest daily correlation is 0.12.
- The current mix's backtests lean on these series: ex-Composer the 2007-26 Sharpe falls from 1.09 to 0.90.
- Composer was not called; only cached files were used (read-only rule).

Backfill (backtest B, stress replays, forward)
- 15 streams use factor replicas (SPY/TLT/GLD/DBC, weekly OLS, no residual) before inception. Their weekly R^2 is -0.10 to 0.36; BTC's is 0.03.
- Replicas carry little risk, so pre-inception losses are UNDERSTATED for books holding those streams. Both the current mix and the proposals hold them, and 2008 has 48-105% of each book's weight on proxies or replicas.
- Natural proxies: AVUV->IWM, AVDV->EFA, AVEM->VEIEX, QUAL->SPY, PHYS->GLD, PSLV->SLV, BOXX/BIL->BIL/DTB3. The engine's declared ARKG/BOTZ/IREN splices are kept.

Scope simplifications
- ETH carry and HL USDC are treated as cash at rf in backtests (~-0.1%/yr not charged).
- The 16% loans are treated as BOXX in backtests.
- Private credit, real estate, venture and OO are parametric (assumption-driven correlations).

Not modelled
- taxes (BTC/gold trims realise large gains)
- margin calls and intra-month deleveraging
- TIPS financing (no futures)
- bullion spreads
- the OO sale as a jump
- liabilities
- currency
- correlation change within the window
- Composer execution drift

Sources
- IBKR rates were opened (ibkr.com, 2026-10-06).
- The CME implied-financing (+38/+81 bp over SOFR), UPAR (0.65%, ~1.68x) and RSSB (0.39%) figures come from search snippets; the pages were not opened (low confidence).
- ALLW (0.85% fee, 1.87x gross) comes from the fact-checked canon pack.

Verification
- Counter-agent review: DONE (data-integrity + independent recompute), 7 blocking items fixed and re-checked.
- Not committed (the orchestrator commits).

Request mismatch
- The triggering user message was a sponsor price update ($0.34 vs $0.40, copper), which this analysis does not address (see open questions).
