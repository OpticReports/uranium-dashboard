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

---

## SPEC v1 — amendments after counter-agent review, still BEFORE any forward return

Counter-agent verdict on v0: "sound enough to run once B1-B3 are amended". Its
synthetic power check (walk-forward on a 0.97-persistent feature, h=12, OOS
from month 240): the v0 gate passed ~3-5% of the time on NO effect, and only
~5-7% at a realistic effect (a rate variable explaining 3-8% of 12m return
variance). With 39 gateable cells, a v0 pass would more likely be noise than
signal. Every item below SUPERSEDES the v0 text it names.

**A1 (B1) — ONE confirmatory test.** The gate is model (c) SMALL at h = 12
only. Pass = v0 conditions 1 and 2 AND R1 sign agreement AND R3 sign
agreement, where for SMALL: **R1** = each of its three logistic coefficients
has the same sign fitted on 1971-1999 origins and on 2000-end origins; **R3**
= each keeps its full-sample sign with the 20y-splice origins removed. Code:
`yield_dynamics/study.py::gate_small`, the SAME function `power.py` calls. Every other model × horizon cell is EXPLORATORY: reported with its
CI, never the headline. The gate's POWER is measured before the run by a
simulation on the REAL feature paths (synthetic returns whose 12m variance is
0 / 2 / 5 / 10 / 15 / 20 / 30% explained by the SMALL features, overlap
reproduced by summing monthly shocks; 200 simulations per size). A failed gate is reported as "base rate; any rate effect is
below the detectable size of ~X", never as "rates don't matter".

**A2 (B2) — base rate is specified.** Headline base rate = the 1971+ grid,
with a 90% CI from the stationary bootstrap (A3). 1928+ ^GSPC shown as a
sensitivity.

**A3 (B3) — inference that respects persistent predictors.** M1/M2 p-values
from a CIRCULAR-SHIFT null: rotate each feature series against the outcomes
by every shift ≥ 36 months (preserves both autocorrelations). CIs: stationary
bootstrap, mean block = max(h, 24). M3 BSS CI: stationary bootstrap, mean
block = 2h. EPISODE = a run of qualifying origins, runs < h months apart
merged; a cell with < 5 episodes is labelled anecdotal.

**A4 (S1) — real-time splice.** 20y fill = DGS30 + mean(DGS20 − DGS30) over
1986-01..1986-12 (known in real time). Counter-agent measured the method's
error where both series exist: RMSE 0.21pp in level, 0.15pp in 12m change.

**A5 (S2) — feature set.** dC20_3 is an exact identity (S20_12 − S3_12) and
is REPLACED by **SB_12 = 12m change in the 3-month bill (DTB3)** — the policy
stance, which v0 listed but never used. Also in the kNN set. DISCLOSED: this
swap was chosen after seeing today's features (3y +138bp vs bill +22bp: the
market pricing a Fed that has not moved) but before any forward return.

**A6 (S3) — overlap weighting in models.** Ridge (d): sample weight 1/h so
C = 1.0 regularizes against the real sample size. kNN: neighbours ≥ max(h,
12) months apart; P = (ups + 2·base)/(k + 2) — no 0/1 forecasts from 10
analogs.

**A7 (S4) — regime deadband per leg.** |x| < 0.25pp counts as 0. Both 0 →
QUIET; opposite nonzero signs → TWIST; one leg 0 → classified by the other
(a>0 BEAR-FLAT, b>0 BEAR-STEEP, a<0 BULL-STEEP, b<0 BULL-FLAT). M2 is
DESCRIPTIVE only (not in the FDR family).

**A8 (S5) — outcomes that match the decision.** Secondary, descriptive,
never gated: P(r_h ≤ −10%), P(r_h ≤ −20%), P(worst drawdown inside the
window ≤ −20%, daily closes), and P(r_h < 3-month-bill carry over h) — cash
is the real hurdle for sale proceeds, not zero. R4 total return = ^GSPC
month-end closes plus Shiller monthly dividend yield accrued /12 per month
(multpl mirror; matches Shiller's own file within 0.01 over 630 overlapping
months).

**A9 (S6) — valuation.** Shiller CAPE as an M4/M5 stratifier (analogs split
above/below the median CAPE) and R6: does SMALL's coefficient survive adding
CAPE? No gate tests added. The stock-bond correlation regime is covered by
RATE_SHOCK.md and is cited, not re-tested.

**A10 (S7) — robustness can overturn a pass.** A gate pass whose R1 or R3
sign flips is downgraded to exploratory.

**A11 (NITs).** CPI YoY from CPIAUCNS (never revised), lagged one month on a
calendar index, last published print carried ≤ 2 months (Oct-2025 shutdown).
TODAY's origin = closes of 2026-09-24 (yields) / 2026-09-25 (^GSPC), a
PARTIAL month; 12m changes vs the 2025-09 month-end. R2 uses NBER dates known
only in hindsight — labelled. PRIOR KNOWLEDGE disclosed: RATE_SHOCK.md already
related long-yield moves to 12m forward S&P (1977+), so this pre-registration
is not blind on S20_12 / S10_12.

**Not adopted:** Holm-adjusted CIs on the exploratory cells (tail quantiles at
0.1/38 are unstable at 2,000 resamples). Exploratory cells carry unadjusted
90% CIs, are labelled exploratory, and cannot be the headline — that is the
protection.

### Gate power — measured 2026-09-28, BEFORE the real run (`yield_dynamics/power.py`)

200 simulations per effect size on the REAL feature paths, synthetic S&P-like
12m returns (mean ~9%, sd ~15%, overlap reproduced), effect placed exactly
where the gate looks (a combination of the SMALL features):

| rate effect (% of 12m return variance) | gate passes | c1 skill+CI | c2 both halves | R1 | R3 | median OOS skill |
|---|---|---|---|---|---|---|
| 0% (false-positive rate) | **0.5%** | 0.5% | 2.0% | 21% | 68% | −0.044 |
| 2% | 1.0% | 1.5% | 7.5% | 20% | 69% | −0.041 |
| 5% | 3.0% | 5.5% | 12.5% | 22% | 70% | −0.034 |
| 10% | 2.5% | 4.5% | 12.0% | 29% | 77% | −0.016 |
| 15% | 1.5% | 4.0% | 21.0% | 34% | 78% | −0.001 |
| 20% | 6.0% | 10.5% | 29.5% | 46% | 87% | +0.024 |
| 30% | 14.0% | 25.0% | 45.5% | 51% | 92% | +0.061 |

**What this means, fixed before the answer is known:** the confirmatory gate
cannot detect a rate effect of any realistic size (2-10%) in 1971-2026 data —
it passes ~1-3% of the time, barely above its 0.5% false-positive rate. Median
out-of-sample skill stays NEGATIVE until rates would explain ~15% of 12-month
return variance. This is a limit of ~55 independent years, not of this test.
Therefore: a FAIL is the expected outcome and is uninformative about whether
rates matter; a PASS would be strong evidence. The headline will almost
certainly be the base rate, with the conditional history as context.

**Known flaw, recorded rather than fixed:** R1 as defined (every coefficient
keeps its sign across 1971-99 / 2000+) passes only ~50% even at a 30% effect,
because the three SMALL features are correlated and individual coefficients
trade off. It is left as registered — changing the gate after seeing its
power, however well-meant, is a fork — and it does not change the verdict:
c1 and c2 alone already cap power at ≤25%.

---

## RESULTS — frozen 2026-09-28 (`yield_dynamics/results.json`, one pre-registered run + verifier fixes)

**Today (2026-09-24/25 closes, partial month):** 10y 5.18% · 3y +1.38pp / 10y
+1.02pp / 20y +0.82pp over 12 months · 3-month bill +0.22pp · 10y 1.34pp above
its 5-year mean · regime **BEAR-FLAT** (front-end-led) · CAPE 40.9.

### Verdict

**Confirmatory gate: FAIL** — SMALL @12m out-of-sample Brier skill −0.032
(90% CI −0.082 … +0.028), negative in both halves (−0.045 / −0.011); R1 and R3
fail too. As the pre-run power analysis said it would (≤3% power at realistic
effects). **Headline = the base rate.** The fail means the data cannot resolve
a rate effect of up to ~±10pp on the odds — NOT that the effect is zero.

### The odds (S&P 500, 1971+ month-end origins; 90% CI stationary bootstrap)

| | 6 months | 12 months | 18 months |
|---|---|---|---|
| **higher (price)** | **71%** (64-77) | **76%** (68-83) | **79%** (70-87) |
| higher, full 1928+ record (Depression included) | 67% | 69% | 73% |
| trailed 3-month bills, total return | 31% (25-38) | 25% (17-32) | 24% (16-34) |
| trailed bills, price only | 36% | 31% | 30% |
| fell ≥20% below the start at some point | 6% | 13% | 17% |
| ended ≥20% lower | 2% | 5% | 6% |
| median return | +4.9% | +11.2% | +14.9% |

Read the 12m odds as **~70-76%** (the post-1971 era was kind). With today's
1.1% dividend yield (vs 2.7% average since 1971) the cash-hurdle figure is
between the total-return and price-only rows: **~25-31%**.

### Rates: what they did and didn't do (fig1, fig4)

- **0 of 30** tercile tests pass BH-FDR; smallest circular-shift p = 0.22. All
  13 walk-forward models have out-of-sample skill ≤ ~0 vs the base rate at every
  horizon (the 10-feature ridge is significantly WORSE).
- **Bounds, not "no effect":** today's tercile vs the base rate at 12m — 3y speed
  +0.5pp (CI −8.5…+8.6), 10y speed +2.0 (−5.3…+9.9), 20y speed +0.6 (−7.5…+9.5),
  10y 6m speed +1.6 (−4.8…+7.9), 10y vs 5-yr mean −0.7 (−9.3…+6.5). History pins
  the effect of today's rate SPEED and SHAPE to within about **±10pp** of the base
  rate, point estimates −1 to +2pp. The level features (10y, real 10y) sit in a
  non-monotone middle tercile (−9 to −10pp) — with 30 comparisons, noise.
- High-speed terciles did NOT carry fatter tails: ≥20% falls within 12m in 9-13%
  of cases vs 12.7% overall.
- **Today's configuration:** BEAR-FLAT regime 78% up at 12m (12 episodes). A
  closer match drawn post hoc from today's reading (3y ≥ +1.00pp AND 20y ≥
  +0.50pp): 77% up at 12m (12 episodes) but it **trailed cash 36%** of the time
  and fell ≥20% below its start within 18m in **21%**. The two BEAR-FLAT
  failures: 1972-76 (33% up; the oil-shock stagflation bear, CAPE ~15 — NOT
  expensive) and 1999-2000 (20% up; CAPE 43).
- **RATE_SHOCK context (corrected 2026-09-30):** the 30y is +0.56pp over 60
  trading days — below the +0.75pp spike line. RATE_SHOCK's "spikes roughly
  doubled recession odds (44% vs 21%)" did not survive a per-alert re-test:
  10 of 33 crossings were followed by a recession within 12 months (30% vs
  20%), all in 1979-1990, none of the 17 since, and inseparable from the yield
  curve (`studies/rate-spike-recession.md`). The 3m10y curve is +0.94pp (not
  inverted).

### Analogs (fig2) — illustrations, not odds

10 nearest rate-matched months (≥18 months apart): 9/10 higher at 12m, median
+16%; 8 of 10 beat cash. But the analog method's out-of-sample skill is worse
than the base rate (12m −0.065, CI −0.17…+0.01; 18m −0.079, CI −0.18…−0.003).
They match on rates, not valuation — four had CAPE under 10. **The only analog at
today's valuation, Nov-1999 (CAPE 43), is the one that fell**: −5% at 12m and 21%
below its start within 18m.

### Valuation (fig5) — a risk to plan around, not a validated signal

The PRE-REGISTERED split (CAPE above/below its 1971+ median, 21.7) shows
nothing: +0.3pp at 12m (p = 0.96). Cutoffs drawn after seeing the data show a
steady gradient at 18m — CAPE ≥25: 75% up · ≥30: 64% · ≥35: 45% · ≥40: 29% (vs
79%); a ≥20% fall within 18m: 24 / 31 / 36 / 48% (vs 17%). But every cutoff
rests on 1-3 eras, the CIs all cross the base rate, and the two inference
methods disagree on the strongest cell (CAPE ≥ 35 at 18m: circular-shift p =
0.002, bootstrap CI −60…+2pp). By era, CAPE ≥ 30: 1997-2002 → 53% up at 12m, 38%
fell ≥20%; 2017-2025 → 78% up, 13% fell ≥20%. **Today's CAPE of 41 has one
precedent (1999-2000).**

### Honesty box

- Basis: S&P 500 PRICE index, month-end to month-end; total return accrues
  Shiller dividends monthly. Cash = 3-month bill at the origin × h/12 (discount
  basis, no roll). Nothing is a trade simulation.
- Sample: 1971-01 → 2025-08 origins at 12m (656 overlapping months ≈ 55
  independent years; ≈ 37 at 18m). Month-weighted, so long regimes count more.
- In-sample: tercile cut points, regime counts and every valuation cutoff.
  Out-of-sample: only the walk-forward skill scores (1991+).
- Pre-registration was disclosed as not blind on 10y/20y speed (RATE_SHOCK.md);
  SB_12 was chosen after seeing today's features, before any return.
- NOT modeled: earnings, recession probability, fiscal/term-premium shocks, the
  stock-bond correlation regime, anything after 2026-09-25.
- This is not a forecast of the next 6/12/18 months; it is what history says
  about how much the rate picture should move a prior. Answer: not detectably.

### What this means for the sale — ASSUMPTION: all cash at close (Casey, 2026-09-28; may change)

- With all-cash consideration in ~July 2027, the market odds that touch the
  proceeds start AT CLOSE, not today. The 6m and 12m windows measured from
  today mostly end before the money arrives; they describe the sale-price
  environment, not the proceeds.
- Because no rate feature moved the odds detectably, the July-2027 starting
  odds are the same base rates (≈70-76% up over 12m; ~25-31% chance of
  trailing bills) — unless valuation is still near today's level, the one
  unvalidated risk flagged above.
- Re-read the state at signing/close with `python3 yield_dynamics/study.py`
  (refresh the data files first); the study's conclusions don't need
  re-running, only today's reading.
- If the consideration changes (stock, earnout, equity-linked), the relevant
  windows start TODAY and the 6/12m rows above apply directly.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| spec v0 (2026-09-27) | sound once B1-B3 amended; v0 gate ≈ its own false-positive rate at realistic effects | B1-B3, S1-S7, NITs (A1-A11); Holm CIs declined, reason above |
| gate power (2026-09-28) | measured before the run: ≤3% power at realistic effects; R1 collinearity flaw | recorded, gate unchanged |
| results, verifier A (2026-09-28) — independent re-derivation from raw data | every headline number reproduced exactly; ONE bug: the "1928+" sensitivity was silently 1962+ (75.4% reported vs 69.4% true at 12m) | fixed (7df4afd), results regenerated |
| results, verifier B (2026-09-28) — methodology/inference | no code bug moves a rate number; B2: the draft treated valuation more generously than rates (CAPE ≥30 fails the same test, p 0.15-0.39; pre-registered median split null); S1-S7 wording, TR cash hurdle, bounds, analog honesty, RATE_SHOCK context, missing input (sale structure) | all adopted after re-deriving each number; two of B's own claims were wrong and corrected ('five analogs CAPE < 10' → four; 'both BEAR-FLAT failures high-valuation' → 1972-76 was CAPE ~15); p-values now (1+#)/(1+N); AUC dropped; sale structure asked of Casey |
