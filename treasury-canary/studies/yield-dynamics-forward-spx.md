# Yield dynamics → forward S&P 500 odds (6 / 12 / 18 months)

**Question (Casey, 2026-09-27):** bond yields are rising fast. Using their
LEVEL, their SPEED of rise, and the SHAPE of the curve across 3y / 10y / 20y,
what are the odds the S&P 500 is up or down 6, 12 and 18 months from now?
Find similar regimes since 1971 and make the calculation accurate. Context:
a company sale closes ~July 2027, so the 6/12/18m windows from today straddle
it (Mar-27 / Sep-27 / Mar-28).

Prior work this does NOT duplicate: RATE_SHOCK.md (60-day ±75bp shocks on the
30y × stock-bond correlation regime, 12m horizon only) and the EWM (deal-value
model, not equity odds).

---

## SPEC v0 — pre-registered 2026-09-27, BEFORE any forward return was computed

### Data (keyless, frozen in `yield_dynamics/data/`)

- Yields: FRED daily constant-maturity DGS3 (1962+), DGS10 (1962+), DGS20
  (1962-01..1986-12, 1993-10+), DGS30 (1977-02+); DTB3 3-month bill (1954+,
  discount basis — used only as the policy anchor, never mixed in levels with
  CMT series).
- **20y splice:** 1987-01..1993-09 has no DGS20. Filled with DGS30 + the mean
  (DGS20 − DGS30) over the 12 months after DGS20 resumed (1993-10..1994-09).
  Robustness R3 drops every origin whose 20y features touch the splice.
- Equity: S&P 500 price index (^GSPC, Yahoo daily close, 1927+). PRICE return
  — the number on the screen. Total return (dividends) is robustness R4 if a
  dividend series is obtainable; otherwise stated as not modeled.
- CPI (CPIAUCSL) for the real-yield feature, lagged ONE month for publication.
- Recession bands (USREC) — descriptive only.

### Grid

Month-end origins (last business day with data) 1971-01 → the last origin
whose h-month window has closed. Outcome: `r_h = P(t+h)/P(t) − 1` on month-end
closes, h ∈ {6, 12, 18}. `up_h = r_h > 0`.

### Features (all known at the origin's close; fixed set, no additions later)

| id | feature | why |
|---|---|---|
| L10 | 10y level | "where they're at" |
| L10_dev | 10y minus its trailing 60-month mean | level relative to the recent norm (5% in 1981 ≠ 5% in 2026) |
| R10 | 10y minus CPI YoY (1-month lag) | real level |
| S3_12 | 12m change, 3y (pp) | front-end speed |
| S10_12 | 12m change, 10y | mid speed |
| S20_12 | 12m change, 20y | long speed |
| S10_6 | 6m change, 10y | faster-window speed |
| C10_3 | 10y − 3y | curve shape, belly |
| C20_3 | 20y − 3y | curve shape, long vs short |
| dC20_3 | 12m change in C20_3 | steepening (+) vs flattening (−) |

**Curve-move regime (categorical, 12m window):** with a = S3_12, b = S20_12:
BEAR-FLAT (a>0, b>0, a>b) · BEAR-STEEP (a>0, b>0, b≥a) · BULL-STEEP (a<0, b<0,
a<b) · BULL-FLAT (a<0, b<0, b≤a) · TWIST (opposite signs). Deadband: a move
with |a| and |b| both < 0.25pp is QUIET (overrides the above).

### Methods

- **M0 base rate.** P(up), median, 10th percentile of r_h, all origins.
- **M1 terciles.** Each feature split at full-sample terciles (IN-SAMPLE —
  descriptive only). Per tercile × horizon: P(up), median, p10. CI: circular
  moving-block bootstrap, block = h months, 2,000 resamples. Test statistic:
  P(up) top − bottom tercile; Benjamini-Hochberg q = 0.10 across the 10 × 3 = 30
  tests.
- **M2 regime.** Same outputs by curve-move regime.
- **M3 walk-forward (the gate).** OOS origins 1991-01 → end. At origin t a
  model trains ONLY on origins s with s + h ≤ t (the outcome must be KNOWN at
  t — no overlap leakage). Models, all fixed ex ante, no tuning:
  (a) base rate = expanding mean of up_h;
  (b) univariate logistic per feature (10);
  (c) SMALL logistic: S10_12, C20_3, L10_dev;
  (d) FULL ridge logistic, all 10 standardized on the training window, C = 1.0;
  (e) kNN analog: standardized (L10_dev, S3_12, S10_12, C20_3, dC20_3),
      Euclidean, k = 10 de-clustered neighbours (≥ 12 months apart), P(up) =
      share up.
  Score: Brier, Brier skill vs (a), AUC. CI on BSS: block bootstrap, block = h.
- **M4 analogs for TODAY.** kNN as in (e) over all closed origins; list each
  analog month, its features, its r_6/r_12/r_18; plot forward paths.
- **M5 today's reading.** Feature values, tercile placement, regime, analogs,
  model probabilities.

### Decision rule (fixed now)

A model "adds information" at horizon h only if ALL hold:
1. OOS BSS > 0 and the bootstrap 90% CI lower bound > 0;
2. BSS > 0 in BOTH OOS halves (1991-2008 and 2009-end);
3. for (b), the feature also passes FDR in M1.

If a model passes, today's headline odds come from it (reported with its CI).
If none passes, the headline is the BASE RATE, and M1/M2/M4 are shown as
"conditional history, not validated as predictive".

### Robustness (reported, cannot rescue a failed gate)

R1 sub-periods 1971-1999 vs 2000-end (sign agreement of M1 top−bottom).
R2 recession-origin exclusion (drop origins inside NBER recessions).
R3 20y splice exclusion. R4 total return, if obtainable.
R5 alt speed: 12m change relative to level (Δ / L_{t−12}).

### What this cannot answer (stated up front)

~55 non-overlapping 12-month windows since 1971; ~37 at 18 months. Rates are
one input; earnings, valuation and shocks are not modeled. Any conditional
cell with < 5 independent episodes is labelled anecdotal.
