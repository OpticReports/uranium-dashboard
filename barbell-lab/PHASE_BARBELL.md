# Phase-aware allocation — results (corrected, panel-approved wording)

Spec: PHASE_BARBELL_SPEC.md, frozen 36c9b6d BEFORE any result existed.
First run 2026-08-11; counter-agent panel verdict on that run:
**DO-NOT-SHIP as numbered** — two bugs, both flattering the strategy.
This document reports the CORRECTED numbers only. The uncorrected first
run (CAGR 8.63, maxDD −21.6, Sharpe 0.69) is retracted and appears
nowhere else; commit 5602a00's numbers are superseded.

## What the panel caught

1. **Bond duration ~2x too high** (`+ n(1+y)^-n` double-counted the
   principal in the Macaulay closed form). Synthetic bond vol 14.1%/yr vs
   the real 8.9%. The pre-registered corr/CAGR validation PASSED anyway —
   correlation is dominated by the sign of yield moves and CAGR by carry,
   so both are structurally blind to a volatility-scale error. The gate
   now includes a vol-ratio bound (0.9–1.1; corrected series: 0.979).
2. **Timing one month faster than the spec allowed.** Labels built from
   data through t−1 were earning month t's return; the spec froze
   next-month effect. Worth +0.23pp CAGR and −3.7pp of worst-36m — an
   infeasible-information subsidy. run() now applies labs[t−1]; a
   perturbation gate pins the alignment.
3. Recent SPX dividends were zero-filled in the source (36 months),
   understating the benchmark exactly where the strategy lags. Forward-
   filled (flat-dollar, conservative), disclosed.
4. Tier-B momentum attack DEFUSED by ablation: removing the SPX-momentum
   label member changes 170/618 pre-1960 labels but 1935–59 metrics
   barely move (Sharpe 0.88→0.92, maxDD −18.3→−17.5) — the early-era
   protection is macro, not embedded price momentum.

## Headline (1935-01 → 2026-06, 91.5y, monthly, 10bp one-way costs)

| | CAGR | max DD | Sharpe | Ulcer | worst 36m |
|---|---|---|---|---|---|
| Phase balanced | **8.39%** | **−20.9%** | **0.71** | 5.12 | **−14.3%** |
| Phase aggressive (×1.5) | 9.67% | −31.7% | 0.70 | 7.87 | −23.7% |
| Phase defensive (×0.5) | 6.70% | −15.7% | 0.65 | 2.57 | −6.1% |
| 60/40 | 8.89% | −27.1% | 0.67 | 6.12 | −14.5% |
| S&P 500 total return | 11.34% | −49.0% | 0.64 | 12.47 | −38.7% |

Deflated Sharpe (balanced, 3 risk-variant trials, n=1098): p ≈ 0 — the
Sharpe is not a variant-selection artifact. Bond synthesis validation vs
Damodaran actuals: corr 0.991, CAGR gap +28bp/yr, vol ratio 0.979 (73y).

### Panel-required framing (verbatim)

> On monthly-average (Shiller-convention) prices, which understate
> volatility and drawdowns for strategy and benchmarks alike, the
> phase-aware balanced allocation earned 8.4% vs SPX's 11.3% over
> 1935–2026 with roughly half the max drawdown (−21% vs −49%) and a
> worst-36-month loss of −14% vs −39%. Its Sharpe edge over 60/40 is thin
> (0.71 vs 0.67) and is concentrated in the 1937, 1973-74, 2000-02 and
> 2008 episodes; over the entire 1940–1981 rising-rate era it
> *underperformed* 60/40 on both CAGR and Sharpe, and its worst modern
> episode (2022, −16%) occurred when bonds — its main defensive sleeve —
> crashed. Labels use revised data; bond returns are synthetic; the
> 2023–2026 defensive miss is included. This is a sequence-risk claim,
> not a return-alpha claim, and it does not cover bond-hostile
> inflationary regimes.

## Era splits (balanced | SPX | 60/40 — CAGR / maxDD)

| era | phase | SPX | 60/40 |
|---|---|---|---|
| 1935–59 (synthetic tier) | 7.3 / −20.9 | 13.4 / −41.6 | 9.0 / −25.7 |
| 1960–2026 (full labels) | 8.8 / −18.1 | 10.6 / −49.0 | 8.9 / −27.1 |
| 1940–81 rising rates | 6.4 / −14.5 | 10.5 / −39.2 | 7.5 / −25.0 |
| 2000→ | 7.5 / −16.0 | 8.3 / −49.0 | 6.9 / −27.1 |
| 2020→ | 8.5 / −16.0 | **15.1** / −19.3 | 8.8 / −18.6 |

2020→ is the pre-committed honesty row: the strategy paid ~6.6pp/yr of
CAGR for defense the market didn't need — the same over-prediction streak
the cycle tracker's analog panel discloses. Tier-C label caveat: the
10-member composite is only fully populated ~1977 (W875RX1/CMRMTSPL/ICSA
z-warmups); 1960–77 labels run on a subset.

## Status

Study only — nothing allocates real money. Gates: 10, including spec-
table parity, canary phase-rule parity, no-lookahead truncation, run-level
timing alignment, bond vol-ratio, duration closed-form pin, cost bounds,
corrected-results pin. Next (not started): barbell-lab dashboard panel
with live phase → suggested weights, wired to the treasury-canary /cycle
feed, risk slider per the spec.
