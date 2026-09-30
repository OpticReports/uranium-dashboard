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

---

## SPEC v1 — amendments after counter-agent review, still BEFORE any outcome

Counter-agent verdict on v0: "not runnable" — it would publish words about an
event set it never measured. Verified against the raw files before adopting:
the 26-week merge chains 1979-10 → 1982-02 into one 125-week episode (64 of
155 spike weeks); the live 75/60 state machine fires **39 WARN events**
(0.79/yr) on daily data, 7 of them never a Friday SPIKE week; there are **6**
onsets since 1977 (1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03), not
7; the 2002-06 Treasury fill has seams of +17bp (2002-02-19) and −16bp
(2006-02-09); DTB3's discount basis runs −0.38pp vs DGS3MO in 1981-85. Every
item below SUPERSEDES the v0 text it names.

**A1 (B1) — the unit is the alert.** Primary unit = each WARN event from the
exact live state machine on DAILY d60 (d60 rounded to whole bp, fire at ≥ +75,
re-arm below +60). The 12-month clock starts at each event. Secondary: weekly
SPIKE episodes under RATE_SHOCK's 35-day rule, for comparability. The 26-week
merge is dropped as a unit (it survives only as the "same episode" label, A6).

**A2 (B2) — an outcome a real-time reader could use.** **RT12**: an origin
hits if any USREC=1 month falls in [origin month, origin month + 12]. An
origin is EXCLUDED only if its month has USREC=1 AND its date is on/after
that recession's NBER peak announcement (1980-06-03, 1982-01-06, 1991-04-25,
2001-11-26, 2008-12-01, 2020-06-08) — i.e. only once the recession was known.
Each hit is tagged LEAD (onset after the origin month) or LATE (underway, not
yet announced). Onset = first USREC=1 month; 1981-08 is a distinct onset.
2020 included; ex-2020 a sensitivity; strict ONSET12 and ANY12 sensitivities.
Last eligible origin = last USREC month − 24 (2024-08) — the newest zeros are
provisional (NBER takes 4-12 months).

**A3 (B4) — T1, one coherent test with its power measured first.**
R = event hit rate (RT12) ÷ RT12 rate over all eligible trading days (spike
days included). p = circular shift of the event dates against the outcome
path by every shift ≥ 504 trading days (the observed alignment counts as one
draw; shifting the event set with the path approximates re-running the state
machine on the rotated path, exact except at the wrap point). 90% Wilson CI on
k/N at the event level AND with N = episodes (events < 26 weeks apart merged,
hit if the episode's first event hits). **Power first** (`power.py`, before
the real run): synthetic recessions at a base monthly hazard calibrated to ~6
onsets over the sample, with hazard ×1 / ×2 / ×3 in the 12 months after each
REAL event; real durations and announcement lags resampled; 1,000 draws each;
report how often the gate passes.
"About 2× recession odds" requires ALL of: R ≥ 1.8; p < 0.10; hits spread
over ≥ 3 distinct onsets; ratio ex-1979-82 ≥ 1.5. Otherwise the words are
"R× (k of N events); too few recessions to confirm; effects below ~X× are
undetectable" — never "chance".

**A4 (B3) — T2, against the curve the live model actually uses.** Curve =
DGS10 − BEY(DTB3) before 1981-09, BEY = 365·d / (360 − 0.91·d) (d in %,
checked vs DGS3MO: mean residual −0.015pp), DGS10 − DGS3MO from 1981-09;
value as of the origin day. Probit link, as in `metrics/recession_model.py`.
Outcome RT12, eligible days. Report (a) the full-sample SPIKE coefficient
with a circular-shift p (rotate the spike-day indicator only); (b) event hit
rates split by curve-model probability ≥ 30% vs < 30% at the event (full-
sample fit — in-sample, stated). Words: "adds warning beyond the yield curve"
only if (a) p < 0.10 AND the < 30% stratum's hit rate ÷ base ≥ 1.5.
"Overlaps with the curve" only if the < 30% stratum has 0 hits in ≥ 5 events.
Otherwise: "can't be separated from the yield curve with 6 recessions." The
alert always quotes the live curve-model probability next to it. Disclosed: a
long-end spike STEEPENS 10y−3m, so the curve model's odds tend to fall exactly
when this alert fires.

**A5 (S1) — seam-corrected d60 for the study.** d60 = chained daily changes
with the 2002-02-19 and 2006-02-09 changes replaced by DGS20's change that day;
raw DGS30 as a sensitivity. The LIVE alert is unaffected (it only reads the
last 60 observations).

**A6 (S3) — alert rules tightened.** INFO "approaching" carries NO odds claim
(the +60 level is not tested here) and at the default TELEGRAM_MIN_SEVERITY
(WARN) stays on the dashboard, off the phone. "Quiet" = WARN armed. No INFO on
a day a WARN fires. A WARN within 26 weeks of the previous one reads
"re-crossing, same episode". DISCLOSED: the live d60 was +58bp at registration
(2026-09-28), so INFO will likely fire within days of shipping.

**A7 (S4) — every surface follows the result.** The decision rule governs the
alert text, the chart-line label, `routes_rates._summary`, the
`RATE_MATRIX` / `RATE_SHOCK_STATS` evidence strings and the panel copy
(`RateShockPanel.tsx`), which today repeat "44% vs 21%" and say "began within
12 months" for a statistic that is ANY12.

**A8 (NITs).** Loader accepts "." and "" as missing. Counts: 155 SPIKE weeks,
22 episodes under the 35-day rule; without RATE_SHOCK's splice the
replication will not match its 151 weeks exactly. Comparison stated as "vs all
eligible trading days".

### Gate power — measured 2026-09-30, BEFORE the real run (`rate_spike/power.py`)

Real daily grid and real WARN event dates; synthetic recessions at a base
monthly hazard calibrated to ~6 onsets, multiplied ×1/×2/×3 in the 12 months
after each real event; real durations and announcement lags resampled; 1,000
draws each; the full "about 2×" gate (circular-shift step 5 here).

| true hazard multiplier after a spike | gate passes | median measured R | p < 0.10 | ≥3 onsets hit | ex-Volcker R ≥ 1.5 |
|---|---|---|---|---|---|
| ×1 (false-positive rate) | **3.5%** | 0.97 | 10% | 68% | 18% |
| ×2 | **8.6%** | 1.26 | 27% | 95% | 28% |
| ×3 | **11.0%** | 1.35 | 40% | 100% | 36% |

Fixed before the answer is known: (1) the gate cannot confirm even a real
TRIPLING of recession hazard more than ~1 time in 9 — a FAIL is expected and
says "too few recessions to confirm", not "no effect"; (2) a true ×2 hazard
shows up as only a ~1.3× RT12 ratio (the outcome window also counts
recessions already under way, and the boosted months lift the base rate), so
RATE_SHOCK's week-level 44% vs 21% (≈2.1×) is larger than a genuine doubling
of hazard would typically produce — it leans on the Volcker cluster. The
words shipped will state the measured ratio with its CI and this limit.

---

## RESULTS — frozen 2026-09-30 (`rate_spike/results.json`, one run; a
deterministic re-run after a JSON-format fix reproduced it bit for bit)

**Gate "about 2×": FAIL** — and it fails on the ex-1979-82 condition under
every outcome definition, not on a p-value near the line.

| unit | record | vs base (RT12, random eligible day 20%) |
|---|---|---|
| **spike episode** (A3/A6 unit) | **3 of 20** (15%) — 1979-10, 1980-08, 1990-02; all LEAD | 0.75× |
| episodes since 1990-04 | **0 of 13** | — |
| alert (crossing) | 10 of 33 (30%; Wilson 90% 19-45%), one-sided shift p 0.11 | 1.51× |
| alerts, ex-1979-82 | 2 of 25 (8%) | **0.53×** |

- 8 of the 10 alert-level hits are repeat crossings inside two Volcker
  episodes; 2 (1981-08-20, 1981-10-20) are LATE — that recession had begun
  but was not yet announced. Per episode, the record sits BELOW the base rate.
- Definition sensitivity: strict ONSET12 R 1.83 (p 0.052); ex-2020 R 1.69
  (p 0.056); ANY12 R 1.80 on [m, m+12] (1.88 on [m+1, m+12]) with p 0.012 —
  its extra 6 hits are alerts that fired inside already-announced recessions.
  The ex-Volcker condition fails under all of them (RT12 0.53, ONSET12 0.80,
  ANY12 1.28).
- **T2:** spike coefficient 0.42 given the curve, rotation p 0.49 — per A4,
  "can't be separated from the yield curve with 6 recessions". The curve alone
  expected 8.2 of the 10 alert hits. The ≥30%-curve stratum ratio (3.75) is vs
  the unconditional base and is NOT quoted anywhere.
- **Why RATE_SHOCK said 44% vs 21%:** of the 68 spike WEEKS it scored as hits,
  64 were 1979-82 and 4 fell inside the already-announced 2008-09 recession;
  the other 83 spike weeks had none (vs a 14% base). Reproduced independently
  by both verifiers and here.
- **Cannot be said:** that spikes now LOWER recession odds (the post-1983
  negative coefficient comes from a subsample chosen where the hits stop), or
  that the effect is zero (power 8.6% at a true ×2).

**Words shipped** (every surface, gated in `backend/tests/test_rate_spike.py`):
alert — "a recession began within 12 months after 3 of 20 past spike episodes
(15%, vs 20% for a random day), all by 1990; none of the 13 since. Too few
recessions to confirm or rule out a link. Yield-curve recession model: N%";
a crossing within 26 weeks of the last reads "re-crossing, same episode"
without repeating the history. **Deviation from A3's template** ("R× (k of N
events)"): the event count repeats two Volcker episodes eight times and A6
already makes the episode the alert's unit, so the episode figure leads; the
event figure is kept in the frozen record, not in the words.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| spec v0 (2026-09-30) | not runnable: unit ≠ alert, NBER hindsight in the outcome, T2 gate near-certain to fail and ship its default words, T1 mixed units, power unknown | B1-B4, S1-S4, NITs (A1-A8); each data claim re-derived from raw files first |
| gate power (2026-09-30) | measured before the run: 3.5% false-positive, 8.6% at a true ×2, 11% at ×3 | recorded; gate unchanged; words built to state the limit |
| results, verifier A (2026-09-30) — independent re-derivation | all 39 events, 6 onsets, 6 exclusions, 10/33, R 1.513, p 0.1118, ex-Volcker 0.534 reproduced bit-for-bit; my brief's "0 of 21 since 1990" wrong (17 alerts / 13 episodes) | count fixed before shipping (my own gate caught it first); ANY12 window stated; NaN → null in results.json |
| results, verifier B — inference/wording | gate FAIL holds; BLOCKING: the "10 of 33, 30% vs 20%" headline misdescribed 2 LATE hits and was inflated by repeat Volcker crossings (per episode 3/20 = 15%); A6 re-crossing rule unimplemented | words rebuilt on the episode unit; re-crossing branch + gate; curve model always quoted ("unavailable" if missing); erratum names the 64/68 Volcker driver; no "lower odds" wording (gated) |
