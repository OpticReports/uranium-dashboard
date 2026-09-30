# Long-yield spikes → recession odds: does the "doubles the odds" claim hold?

**Question (Casey, 2026-09-30):** RATE_SHOCK.md says a sharp long-yield spike
(30y +75bp in 60 trading days) roughly doubled 12-month recession odds (44% vs
21%). How does the dashboard use that — and can it carry an alert and a marked
line on the chart that means "recession odds have doubled"?

What exists today: `/rates/shock` + the Rate Shock panel already draw the
+75bp line on the 60-day-change chart, labelled only "spike +75bp". No alert
fires on a crossing, and the recession claim is not tied to the line.

Why re-test before wiring an alert: the 44%/21% figures count overlapping
WEEKS (151 spike weeks, 24 episodes), count weeks already inside a recession
as "recession within 12 months", and were never checked against the yield
curve the dashboard's recession model already uses. An alert that says
"recession odds doubled" must be true at the level it is read.

---

## SPEC v0 — pre-registered 2026-09-30, BEFORE any outcome is computed

**Data** (keyless FRED, frozen in `rate_spike/data/`): DGS30 daily 1977-02+
(Treasury's own 2002-06 fill is in the file; no splice), DGS10, DTB3 (3-month
bill, 1954+), DGS3MO (1981-09+), T10Y3M (1982+), USREC monthly.

**Grid.** Weekly origins = last DGS30 observation of each calendar week,
from the first week with a 60-observation history (1977-05) to the last week
whose 12-month outcome has closed. `d60` = DGS30 now minus 60 observations
earlier (the live panel's exact definition). SPIKE = d60 ≥ +0.75pp.

**Outcomes.**
- **Primary — ONSET12:** a recession STARTS (first USREC=1 month after a 0
  month) within the 12 calendar months after the origin month. Origins whose
  month is already in recession are EXCLUDED (a recession in progress cannot
  start).
- Replication — ANY12 (RATE_SHOCK's definition): any USREC=1 month in the
  next 12 months, all origins.

**Episodes.** Consecutive SPIKE weeks form a run; runs less than 26 weeks
apart merge into one episode (one tightening/sell-off cycle). An episode
"hits" if a recession starts within 12 months of its FIRST week. The 35-day
gap rule from RATE_SHOCK is reported alongside for comparability.

**Tests.**
- **T1 (the claim):** episode hit rate vs the week-level base rate of ONSET12
  among non-recession origins. Ratio + circular-shift p (rotate the SPIKE
  indicator against the outcome by every shift ≥ 104 weeks; the observed
  shift counts as one draw) + 90% stationary-bootstrap CI (mean block 52
  weeks) on the week-level spike-minus-base difference.
- **T2 (beyond the curve):** logistic ONSET12 ~ curve + SPIKE, curve = DGS10
  − DTB3 (1977+, both daily, the bill on its discount basis — a ~20-40bp level
  bias, stated; T10Y3M 1982+ as sensitivity). (a) Full-sample SPIKE
  coefficient with bootstrap CI; (b) walk-forward from 1990: each origin
  trains only on origins whose 12-month outcome had closed; Brier skill of
  curve+spike vs curve-only, stationary-bootstrap CI (mean block 104 weeks).
- **T3 sensitivity:** excluding 1979-1982 (Volcker), and the 1982+ T10Y3M
  curve.

**Decision rule for the WORDS the dashboard uses** (the alert fires on a
+75bp crossing regardless — the threshold is RATE_SHOCK's, not refitted here):
- "historically about 2× recession odds" is allowed only if T1's ratio ≥ 1.8
  AND circular-shift p < 0.10. Otherwise the line/alert states the measured
  ratio and "not statistically distinguishable from chance".
- "adds warning beyond the yield curve" is allowed only if T2(b) Brier skill
  > 0 with the 90% CI lower bound > 0. Otherwise: "overlaps with what the yield
  curve already says".

**Alert design (fixed now):** WARN when the live d60 crosses up through
+75bp (dedup: once per crossing; re-arms after d60 falls back below +60bp).
INFO "approaching" when d60 first reaches +60bp in a quiet period (re-arms
below +45bp). Chart: the +75bp line carries the validated wording; a shaded
+60..+75 approach band.

**Limits stated up front.** ~24 spike episodes in 49 years and 7 recession
onsets since 1977: any rate is small-n. NBER dates are hindsight. Nothing here
is a stock signal (RATE_SHOCK found none for spikes).
