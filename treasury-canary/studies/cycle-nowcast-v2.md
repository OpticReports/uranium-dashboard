# Cycle nowcast v2 — a reading every day, a completed coincident, and the Chauvet–Piger cross-check

Casey, 2026-10-20: "pre-register 1+2 and 5 as the next study" (ROBUSTNESS
BACKLOG in `CYCLE_NOWCAST.md`). Status: **SPEC v1 (below, after the two
reviews) is the operative pre-registration — nothing scored.** SPEC v0 is kept
for the record. Process: research pass (done, counter-verified) → SPEC v0
(this file) → two independent reviews (statistics; data/timing, hunting
look-ahead) → SPEC v1 → engine + merge-blocking gate tests + synthetic dry run
→ ONE scored run → two independent verifiers → results, honesty box, charts,
panel wiring.

Data and scripts: `cycle_nowcast_v2/` (data/MANIFEST.md lists every file with
its source URL and retrieval date). The finders' and verifiers' notes live in
the session scratchpad and are not committed; their verified content is in §1.

## 0. Question

Backlog 1: the deployed one-month-ahead nowcast exists only ~8–13 days a month
(its bridge is fitted at fixed publication lags and returns None once a
component publishes). Backlog 2: the headline coincident for the latest month is
a partial mean of 2 or 3 of its 4 members. Backlog 5: the dashboard has no
probability line; the Chauvet–Piger dynamic-factor Markov-switching probability
on the same four series exists free. The study asks:

1. Does a bridge fitted per component × observed lag, with a bridge-completed
   coincident feeding the claims regressor (ENS_BC_HH), deliver a nowcast on
   every calendar day with at least the accuracy the August study claimed?
2. Is the completed coincident a better headline than the partial mean?
3. Measured against the public comparator (Philadelphia Fed ADS, same four
   series plus claims and GDP, daily, 1,575 real-time vintages), is the home-
   built reading worth keeping as the headline?
4. What does the Chauvet–Piger probability add, scored on its real-time
   release history rather than its smoothed back-history?

---

## 1. Research pass (2026-10-20; three finders, three adversarial verifiers, all PASS_WITH_FIXES)

Only CONFIRMED or CORRECTED facts; corrected values used.

| # | Finding | Consequence for the spec |
|---|---|---|
| 1 | The frozen August study reproduces EXACTLY only with a **1959-01** data start (PERS RMSE 0.4674 / 0.5316, phase acc 82.6, transitions 114 / 75, COIN 2026-06 −0.4917); the deployed `compute()` starts 1960-01 (120/81, 81.7). The original harness is not in the repo. | Harness rebuilt at 1959-01; reproduction gate §7 on the 2026-08-07 fixture only. |
| 2 | Both defects are live today (2026-10-20 data): `nowcast()` → None (catch-up gate; INDPRO at lag 0); headline COIN(2026-09) = −0.019 from 2 of 4 members. | Today's pull is fixture F3: deployed → None, v2 → a value with lags {INDPRO 0, W875RX1 1, CMRMTSPL 2}. |
| 3 | Within-month information sets are **three**, not four: CMRMTSPL(M−1) and W875RX1(M) print the same BEA day (5 of 5 months in 2026). IS-A payrolls Friday; IS-B after the G.17; IS-C after Personal Income & Outlays. A pre-payrolls IS-D has a 1–8 day window — dropped. | §3. |
| 4 | A true real-time replay of all four members exists only from **2013-06-14** (first CMRMTSPL ALFRED vintage; W875RX1 2010-05-28; ICSA 2009-05-28). Nothing fills the gap (RTDSM has neither series). 2013+ holds one recession. | §4: two regimes, never pooled. |
| 5 | The 2025 shutdown pushed CMRMTSPL to lag 4 (2025-12-01); at the payrolls-day issue dates 2025-12-16, 2026-01-09 and 2026-02-06 the deployed engine returns None for three different reasons. | §2.4 shutdown rule; those dates are gate cases (fixture F4). |
| 6 | Comparator: ADS (daily Kalman factor on the same four monthly series + weekly claims + quarterly GDP; 7.33 updates/month; 1,575 archived vintages 2008-12-05..2026-10-16). Its end-point revises by mean-abs 0.36 ex-COVID and understated the 2008 trough by 1.5–3 units in real time. No official recession threshold. | §5: calibrated real-time ADS at identical issue dates; the honest bar is "match", not "beat". |
| 7 | Chauvet–Piger real-time record (240 releases 2006-08..2026-09, Piger's file in DECIMAL, ×100 = FRED): the 3×80% rule declared 2007-09 at the **2009-01-01** release (13 months after the peak, a month after NBER), **never fired for 2020**, and printed a one-release **44.4%** false spike for Sep-2021. Release lag median 60 days. | §6: scored on the real-time path by release date; descriptive, n = 2 recessions. |
| 8 | The 2026-09-30 NIPA annual revision moved realized COIN 2026-06 from **−0.49 to −0.21** (W875RX1 z +0.5..+0.8σ; three 2023 labels flipped). Any fresh pull breaks the existing −0.60..−0.35 composite gate on its own. | §7: gate on the frozen fixture, score on a new frozen pull; re-baseline the composite bounds; honesty box. |
| 9 | ALFRED keyless vintages are feasible: ~0.6–1.0 s sequential, ~0.15 s at 8-parallel, no 429 in ~430 requests; transient 502/504 must be retried; the CSV header echoes the REQUESTED date, so the served vintage must be identified by content hash or the vintage list. Event-snapped 2013–2026 replay ≈ 6.5k requests. | §4.3 pull engineering. |
| 10 | First-print revisions of 6-month annualized growth (2015–2026, pp mean-abs / own sd): PAYEMS 0.28/5.0, INDPRO 1.57/6.5, **W875RX1 1.57/3.4 (0.47 sd, +0.9 pp bias)**, CMRMTSPL 1.26/6.1. | Score on first prints AND latest; the realized target itself moves. |
| 11 | Mechanism correction: the deployed CLAIMS member's full-sample z is NOT a look-ahead (OLS with intercept is affine-invariant); its −0.449 vs the spec's −0.429 comes from the training window (1970-07 vs 1977-09). | Spec-alignment change only (§2.3). |
| 12 | UMCSENT: FRED now posts the Michigan final one month late (from the 2026-09-25 release); the replay is unaffected (ALFRED timely through 2026-08), the live leading composite's sentiment member is ~M−2 at payrolls day. | Board caveat (Q11), not a study item. |

Benchmarks (hindsight unless stated): CFNAI-MA3 < −0.70 → 12 spells, 0 false,
onset lags 0..+10 months; CFNAI publishes ~3 weeks after month end, after
payrolls and IP. Conference Board CEI = the same four series with imputed first
prints (history paywalled). Literature: the gain from intra-month updating is
where the value lives (GDP nowcast RMSFE −50% first-to-last vintage, Bańbura–
Giannone–Reichlin; "precision increases with the data flow"; daily financial
variables do not help). Chauvet–Piger 2008 (JBES): no false positives in
simulated real time, troughs ~8 months ahead of NBER.

Counter-agent log: R1 method digest PASS_WITH_FIXES (5 confirmed / 3 corrected;
missed: NIPA revision magnitude, the n = 587 partial-row resolution, affine
invariance, six look-ahead holes D1–D6 in the first design text, the UMCSENT
delay); R2 data PASS_WITH_FIXES (5/3; corrected earliest vintages, Piger release
counts, the ALFRED header-echo hazard; missed: shutdown issue-date cases, replay
sizing); R3 benchmarks PASS_WITH_FIXES (7/2, one refuted clause: "never above 5%
since 2021" — the 2021-10-29 spike; corrected the 2020 path and the CMRMTSPL
release pattern; missed: CEI, WEI, the ADS post-2023 parameter regime, the
shutdown claims-only ADS updates). 31 findings; 17 confirmed, 8 corrected,
1 refuted, 6 NOTE skipped by the severity rule.

---

## SPEC v0 — pre-registered 2026-10-20 (SUPERSEDED by SPEC v1 below after two BLOCK reviews; kept for the record)

### 1. Target and composites (exact reconstruction of the August study)

- Month axis = PAYEMS months; data start **1959-01**; expanding z with a
  120-observation warm-up inclusive of the current month, population sd;
  growth g6 = 2·(ln x_M − ln x_{M−6}) (units: log, not percent).
- COIN(M) = mean of available members' z (PAYEMS, INDPRO, W875RX1, CMRMTSPL);
  3-member mean 1969-06..1977-05 (CMRMTSPL z from 1977-06); first COIN 1969-06.
- Leading composite as deployed (curve T10Y3M monthly mean, GS10−TB3MS before
  1982-01; permits g6; −claims g6 on monthly-mean ICSA, weeks assigned by their
  week-ending Saturday; AWHMAN level; ΔUMCSENT; −BAA10YM; mean of z; 3-month MA).
- Phases for scoring: CONTRACTION < −0.75 ≤ STALL < 0 ≤ EXPANSION.
- Evaluation targets 1972-01..2026-06 (n = 654), subsample 1990-01+ (n = 438);
  ex-2020 = targets 2020-01..2020-12 dropped; population RMSE.
- Pre-registered readings of what the August doc left silent (A2, A3/A7, A5,
  A6, A9, A14, A4, A8, A10, A11, A13, A15, A19): z stats include the current
  month and bridged members exclude the projected month; missing-member months
  use the available mean; a transition = realized 3-phase label(M) ≠ label(M−1);
  onset window [onset−6, onset+12], calendar advantage (m_c − m_n) + 1;
  Diebold–Mariano on squared-error differences, Newey–West lag 6, Bartlett
  weights, no small-sample correction; directional ties count as wrong (n
  reported); bridge fallback below 24 training rows = g(M−L); ENS_GRID past-OOS
  MSE cumulative from the first OOS forecast, 24-month warm-up; CLAIMS n = 587
  on the fixture includes the 2026-07 payrolls-only partial row as a training
  target (reproduction only) — the v2 harness EXCLUDES partial-member targets
  from training (D6).

### 2. The v2 engine

**2.1 Lag-generalized bridge (backlog 1).** For c ∈ {INDPRO, W875RX1, CMRMTSPL}
and observed lag L ∈ {1, 2, 3}: g_c(M) ~ 1 + g_c(M−L) + g_PAYEMS(M), expanding
OLS on rows t ≤ M−L with all terms defined (D1), refit at every issue date;
L = 0 → the actual z; PAYEMS is always L0 (it defines the target month).
Projection z-scored against g_c history through M−L (projection excluded).
**The lag is keyed off the actual vintage in hand at the issue date, never the
calendar** (CMRMTSPL(M−2) is in hand on payrolls Friday in ~85–95% of normal
months, not always).

**2.2 Completed coincident (backlog 2).** COIN_HH(M | IS) = mean over the four
members of actual z where published, bridged z otherwise. At IS-C (all four
actual for M−1) the completed COIN(M−1) equals the realized one — the
reproduction identity. The headline month's band = the empirical p10–p90 of the
walk-forward completion error at that IS (from the lag simulation, §3),
reported separately per IS.

**2.3 CLAIMS_HH and the ensemble.** CLAIMS_HH(M | IS): COIN(M) ~ 1 +
COIN_HH(M−1 | IS) + z_claims6(M) + [z_claims6(M) − z_claims6(M−3)] + z_curve(M),
both regressors expanding-z (120); one fit per IS; training rows t ≤ M−2 at
IS-A/IS-B and t ≤ M−1 at IS-C (D2: a training target must have been published
at the issue date; when the BEA release slips past payrolls day the vintage
decides, t ≤ M−3); partial-member targets excluded (D6); historical COIN_HH(t−1)
regressors are the STORED walk-forward completions, never recomputed with the
current fit (D4); persistence before 1977-09. ENS_HH = 0.5·BRIDGE_HH +
0.5·CLAIMS_HH, weights fixed. ENS_GRID is reported only as a no-hindsight check
with selector errors through M−2 (D3). Persistence is reported in three forms:
realized COIN(M−1) (the August baseline), available-members COIN(M−1), and
HH-completed COIN(M−1) per IS (D5).

Spec-alignment changes to the deployed module, made regardless of results:
one z start (1959) for `compute()` and `nowcast()`; the CLAIMS member on
expanding z so the gate pins the spec's estimator; the `len(y) < 200` guards
replaced by the 24-row rule; the bare `except Exception: return None` replaced
by a `reason` field.

**2.4 Shutdown / over-lag rule (DEFAULT, pending Casey Q3).** Lags 1–3 are
bridged with their own fit. A component at lag ≥ 4 is **dropped and the mean is
re-taken over the remaining members**, the payload flags `dropped` and the band
widens to the p10–p90 of the dropped-member simulation. The nowcast is None only
when PAYEMS itself is absent for the target month (then the target is the last
PAYEMS month), and every None carries a `reason`. The four shutdown issue dates
(2025-11-20, 2025-12-16, 2026-01-09, 2026-02-06) are gate cases: a value with
per-component `lags` on the first three, None-with-reason only where the rule
says so.

**2.5 Board contract (DEFAULT, pending Q6).** `current.coincident` keeps its
partial-mean semantics (gates, provisional band and alert baseline unchanged);
add `current.coincident_completed`, `band_p10_p90`, `members_bridged`; the
nowcast carries `info_set` ∈ {A, B, C}, `lags` per component, `dropped`,
`reason`.

### 3. Day-of-month evaluation (lag-pattern simulation, final-vintage data)

For every target 1972-01..2026-06 and each information set under its lag
pattern — A: PAYEMS 0 / INDPRO 1 / W875RX1 1 / CMRMTSPL 2; B: 0/0/1/2;
C: 0/0/0/1 — compute BRIDGE_HH, CLAIMS_HH, ENS_HH, the completed COIN(M−1) and
the three persistence forms, walk-forward. Historical publication calendars are
NOT modeled (an honesty item); the simulation answers "what does each
information set buy", the real-time replay (§4) answers "what did it buy".

Metrics per IS, vs realized COIN(M): RMSE (full, 1990+, ex-2020), directional
accuracy, phase accuracy, transition accuracy (n = 114 / 75), DM vs realized
PERS (NW-6; with and without 2020), onset calendar advantage for the 7 onsets,
false-alarm months (nowcast < −0.75 with no realized < −0.75 within ±3 months),
and the completion error of COIN_HH(M−1 | IS) vs realized (RMSE, p10–p90 — the
headline band). Sanity hypothesis, not a grade: RMSE_A ≥ RMSE_B ≥ RMSE_C.

### 4. Real-time replay

**4.1 Two regimes, never pooled.** (i) **True real-time 2013-06-14..2026-10**:
every series from its ALFRED vintage as of the issue date (PAYEMS, INDPRO,
W875RX1, CMRMTSPL, PERMIT, AWHMAN, UMCSENT, ICSA; T10Y3M and BAA10YM are
unrevised and taken current). One recession (2020). (ii) **Pseudo-real-time
2000-01..2013-05**: final-vintage data with publication lags emulated from the
observed lag table (fixture: `data/alfred_lag_table_1st_of_month.txt`),
covering 2001 and 2007–09. Headline numbers are labelled by regime; the honesty
box says which recessions each regime contains. (DEFAULT, pending Q2.)

**4.2 Issue dates.** Three per month: payrolls day (IS-A), G.17 day (IS-B), PI&O
day (IS-C), taken from the ALFRED first-vintage dates of PAYEMS, INDPRO and
W875RX1 respectively — never from a calendar. Targets scored against (a) the
first full-member print of COIN(M) and (b) the latest vintage; both reported.

**4.3 Pull engineering.** Keyless ALFRED CSV, cache on disk keyed (series,
vintage date), served vintage identified by content hash against the full
vintage list, 5xx retried with backoff and never read as "no vintage",
concurrency ≤ 8. ~6.5k requests. Claims before 2009-05-28: final seasonal
factors (a stated look-ahead of the CLAIMS half, Q10; DEFAULT accept with the
caveat, ICNSA + frozen SA as a sensitivity if time allows).

### 5. Comparator: calibrated real-time ADS

- ADS vintage dated ≤ issue date from the 1,575-column archive; two readings:
  the last point and the last complete month's average (the "right line" is
  not recoverable).
- Calibration to composite units: walk-forward OLS of realized COIN(t) on the
  ADS monthly average, fit at each issue date using ONLY months whose four
  members had printed by that date (t ≤ M−2 at IS-A/B, t ≤ M−1 at IS-C; the
  vintage decides when BEA slipped). No full-sample mapping anywhere in a
  scored number; hindsight charts back to 1960 are labelled in-sample.
- Scored at the same three issue dates per month: 2013-06+ both sides true
  real-time; 2009-01..2013-05 ADS true, v2 pseudo (labelled). Same metrics as
  §3, plus **availability**: days per month with a valid reading, explicitly
  through the 2025–26 shutdown (ADS printed from claims alone; the deployed gate
  returned None for the whole backlog). ADS's post-2023-09-28 parameter regime
  (COVID excluded from estimation) is stated.
- Comparator reproduction gate: re-derive the ADS accuracy note's correlations
  0.866 / 0.916 / 0.956 (Nov-2008..Oct-2010 vs the 2010-12-03 vintage) from the
  archive before ADS enters the scored run.

### 6. Chauvet–Piger cross-check (backlog 5)

- Chart: RECPROUSM156N (percent, smoothed, lands ~1st of M+2) with the
  published rule (three consecutive months > 80% = recession start, < 20% =
  end). The back-history is two-sided and is labelled so.
- Scoring (descriptive, no grade — two recessions in the real-time history):
  Piger's 240-release first-release path aligned by RELEASE DATE (median +60
  days after month end), rule = the published 3×80%/3×20% (DEFAULT, Q8), with a
  1-month ≥ 50% reading as sensitivity. Report: declaration date vs the NBER
  peak month and vs NBER's announcement; vs our realized −0.75 crossing and vs
  ENS_HH at IS-A; false declarations (2021-10-29 44.4% under the sensitivity
  rule). Values taken from ALFRED where 0.01 pp matters (Piger's 2014–2024
  columns are rounded to 0.1 pp); cross-validated to 1.4e-14 on three vintages.
- Honesty: the same four inputs (a different model, not independent data); the
  2020-12-23 re-basing of Mar–Jul 2020. No MS-DFM is fitted in this study.

### 7. Gates (merge-blocking), fixtures, and the freeze

**7.1 Reproduction gate — on the 2026-08-07 fixture ONLY, 1959 start, targets
1972-01..2026-06:**

| Quantity | Target | Tolerance |
|---|---|---|
| PERS RMSE full / 1990+ / ex-2020 | 0.4674 / 0.5316 / 0.2580 | ±0.0005 / ±0.0005 / ±0.001 |
| Phase acc; transitions; realized-cross months | 82.6; 114 and 75; 1974-01, 1979-09, 1981-11, 1990-09, 2001-03, 2008-02, 2020-03 | ±0.1; exact; exact |
| BRIDGE RMSE full / 1990+; live 2026-07 | 0.3348 / 0.3656; −0.347 | ±0.002; ±0.002 |
| CLAIMS (expanding-z) RMSE; live; coefficients; n | 0.3930; −0.429; spec to 1e-3; 587 | ±0.003; ±0.003; —; exact |
| ENS_BC RMSE full / 1990+ / ex-2020; dir; phase; transitions; DM; DM ex-2020 | 0.3344 / 0.3692 / 0.2202; 69.8; 83.8; 29/114; −1.63; −5.33 | ±0.002; ±0.5 pp; ±0.3; exact; ±0.1; ±0.3 |
| ENS_BC and CLAIMS onset months; false alarms | as the August table; ENS_BC [1981-06], CLAIMS [1981-06, 1981-07] | exact |
| ENS_GRID RMSE; 50/50 chosen | 0.3319; 354/630 | ±0.003; ±5 |
| Legacy deployed output on the fixture | bridge −0.347, claims −0.449, ens −0.398; spec form −0.347 / −0.429 / −0.388 | ±0.005 |
| Identity: IS-C CLAIMS_HH fit == original CLAIMS; IS-C completed COIN(M−1) == realized | — | exact |
| SOFT (the QA harness is not recoverable): ENS_BC_S −24.2% / −7.0% / DM −2.76 / onsets 5-1-1; ENS_BC_HH −29.8% / −12.5% / transitions 30.7% / onsets 4-1-2 | — | ±1 pp; a miss is raised to Casey, never widened |

**7.2 Engine gates.** F3 (today's 2026-10-20 pull): deployed → None, v2 → a
value with lags {INDPRO 0, W875RX1 1, CMRMTSPL 2}. F4 (four shutdown issue-date
vintages): per §2.4. `test_gate_nowcast_bails_on_stale_bridge_inputs` is
inverted (lag 3 → value with lags; lag ≥ 4 → dropped-and-re-meaned, or None
with reason per the rule); `test_gate_partial_month_invariance` kept; a
`coincident_completed` bound from the deterministic algorithm, not from study
metrics. Look-ahead gates: shifting any input series forward by one month
changes no number issued before that month (D1/D2/D4 tests); a synthetic series
with a known structure reproduces its own bridge coefficients.

**7.3 Fixtures.** F1 = `backend/tests/fixtures_cycle_fred.json` (2026-08-07,
IS-A) for §7.1 only. F2 = ALFRED full pulls at 2026-08-18 (IS-B) and 2026-08-26
(IS-C) for target 2026-07. F3 = the 2026-10-20 pull. F4 = the shutdown
vintages. **F5 = ONE new frozen pull taken on the run day, on which the single
scored run is made** (DEFAULT, pending Q4); the August numbers will not
reproduce on it (CMRMTSPL 2026-06 now published; NIPA revision) and both are
reported; every composite gate bound (−0.60..−0.35) is re-baselined on F5 with
the reason logged.

**7.4 Freeze.** SPEC v1 (after the two reviews and Casey's answers) is committed
before any v2 number is computed; the run script writes
`cycle_nowcast_v2/results.json` once; corrections after verification are
labelled correction runs and change no tested number without a logged reason.

### 8. Pre-registered success and kill criteria

Primary (lag simulation, IS-A, full sample): ENS_HH RMSE ≤ −25% vs realized
PERS, and ≤ −8% ex-2020; DM NW-6 negative at the 10% level ex-2020.
Secondary (reported, unadjusted, labelled): transitions ≥ 20% at every IS; zero
missed onsets at every IS; no IS worse than PERS; IS-C completed-COIN(M−1) RMSE
vs realized < 0.126 (the QA gap); RMSE_A ≥ RMSE_B ≥ RMSE_C.
Real-time (2013-06+, true vintages, both scoring targets): reported, no
pass/fail — one recession.
Comparator (DEFAULTS, pending Casey Q1): **success** = IS-A ENS_HH RMSE within
**X = 10%** of calibrated real-time ADS on 2013-06+ true vintages, onset timing
no worse, a valid reading every issue date through the shutdown; **kill** = if
calibrated ADS beats ENS_HH by more than **Y = 25%** RMSE (DM NW-6, 10% level,
with and without 2020), the dashboard headline becomes calibrated ADS and the
bridge becomes the explainable cross-check line.
Multiplicity: one primary comparison; secondary metrics are descriptive.
Deterministic throughout; no seeds.

### 9. Honesty, stated now

- Final-vintage data for the lag simulation; the realized target itself moved
  0.1–0.3σ between the August fixture and today (2026-09-30 NIPA); the frozen
  mid-2026 "STALL near −0.5" was largely pre-revision W875RX1.
- True real-time only from 2013-06 (one recession); 2000–2013 is pseudo-real-
  time with emulated lags; historical calendars are not modeled in §3.
- Pre-2009 claims on final seasonal factors (CLAIMS half); W875RX1 first prints
  revise by 0.47 sd with a +0.9 pp bias; ADS end-point revises by 0.36 mean-abs
  and its post-2023 vintages embed a COVID-exclusion regime.
- Chauvet–Piger shares the inputs; its real-time record is two recessions, one
  declared 13 months late, one never.
- The QA variants' numbers (−24.2% / −29.8%) are soft gates: their harness is
  not recoverable.
- UMCSENT is ~M−2 on the live board since September 2026 (FRED's one-month
  delay); the replay is unaffected.

### 10. Pending questions (living ledger; first asked 2026-10-20; expiry 2026-12-19)

| Pri | # | Question | Default in SPEC v0 | What it moves | Status |
|---|---|---|---|---|---|
| P1 | Q1 | Comparator bar: X (within-X% = success) and Y (kill margin that makes calibrated ADS the headline)? | X = 10%, Y = 25% | go/no-go of keeping the home-built headline | asked |
| P1 | Q2 | Real-time scope: two regimes (true 2013+, pseudo 2000–2013) or 2013+ only? | two regimes, never pooled | whether 2001/2008 enter any real-time claim | asked |
| P1 | Q3 | Lag ≥ 4 / shutdown rule: drop-and-re-mean, pooled ≥3 bucket, or carry forward? | drop-and-re-mean with a flag | whether a nowcast exists on every shutdown day | asked |
| P1 | Q4 | Gate on the frozen 2026-08-07 fixture, score on a new frozen pull? | yes, both reported | which numbers go in the honesty box | asked |
| P1 | Q5 | Is the August harness retrievable (nowcast_study.md, results_raw.json, nowcasts.npz, the QA re-run, the ALFRED study)? | assumed not | hard vs soft gates on −24.2% / −29.8% | asked |
| P2 | Q6 | Keep `coincident` partial and ADD `coincident_completed`, or replace the headline? | add | board contract, alert baseline, two gate tests | asked |
| P2 | Q7 | Three information sets, IS-D dropped? | yes | engine state machine | asked |
| P2 | Q8 | Chauvet–Piger rule: 3×80% (never fired for 2020) or 1-month ≥ 50% (Mar-2020 caught; Sep-2021 spike)? | 3×80%, ≥50% as sensitivity | cross-check text | asked |
| P2 | Q9 | Primary comparator metric: RMSE after walk-forward calibration, or phase/onset at walk-forward thresholds? | RMSE primary, onsets secondary | the kill number | asked |
| P2 | Q10 | Pre-2009 claims: accept the seasonal-factor look-ahead with a caveat, or ICNSA + frozen SA? | accept, sensitivity if time | CLAIMS half honesty | asked |
| P2 | Q11 | Live board: flag UMCSENT's new one-month delay, or source Michigan directly? | flag | leading composite timing on the board | asked |
| P3 | Q12 | Accept the §1 readings of what the doc left silent? | yes | gate tolerances | asked |
| P3 | Q13 | A FRED API key for the study container (keyed API returns all vintages per call)? | keyless (~6.5k requests) | fetch time | asked |
| P3 | Q14 | CFNAI-MA3, CEI, WEI as chart-only context? | chart-only | benchmark panel completeness | asked |
| P3 | Q15 | ADS readings = last point + last complete month average? | yes | comparator definition | asked |

### 11. Run order

1. SPEC v0 (this) → statistics review + data/timing review (look-ahead hunt) → SPEC v1 with Casey's answers folded in; nothing scored.
2. Engine + harness in `cycle_nowcast_v2/` (pure functions, no network in tests) → reproduction gate on F1 → engine gates on F3/F4 → synthetic dry run.
3. ALFRED pull (2013–2026 event-snapped) and ADS archive conversion, with the comparator reproduction gate.
4. ONE scored run on F5; `results.json` committed unedited.
5. Two independent verifiers (recompute; claims and wording) → correction run if needed → RESULTS, honesty box with frozen numbers, charts → panel wiring behind the gates → redeploy note (treasury-canary).

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| research pass R1/R2/R3 (2026-10-20) | PASS_WITH_FIXES ×3 — see §1 | all, in §1 and the spec defaults |

---

## SPEC v1 — OPERATIVE. Amended 2026-10-20 after the statistics review (BLOCK, 21 findings) and the data/timing review (BLOCK, 24 findings), before any v2 number is computed

Every amendment below is the reviewers' text adopted (ids F01–F21 statistics,
DT-1–DT-24 data/timing; their notes are in the session scratchpad; the
counter-agent log at the end records verdicts). Where v0 is not restated it
stands. Defaults for Casey's open questions are unchanged (both reviewers kept
Q1–Q4, Q6–Q10, Q12, Q14; Q15 is redefined per F06/DT-3; Q13 becomes a P3
convenience per DT-24).

### 1. Target, composites and conventions (v0 §1 plus)

- **Directional accuracy (A8, F07):** share of targets with
  sign(ŷ(M) − COIN_real(M−1)) == sign(COIN_real(M) − COIN_real(M−1)), realized
  COIN(M−1) on both sides, every method and every IS; ties wrong, n reported;
  no directional statistic against the available-members or HH-completed
  reference.
- **Diebold–Mariano (F08):** d_t = e_candidate(t)² − e_baseline(t)²; DM =
  mean(d) / NW-6 s.e. (Bartlett 1 − j/7); negative = candidate better. Primary
  criterion: two-sided |t| ≥ 1.645 with the required sign. Comparator kill:
  one-sided t ≥ 1.282 in the stated direction. Ex-2020 statistics drop the 12
  rows of 2020 and concatenate the remaining series (gap closed) for RMSE, DM
  and percentiles alike.
- **PERS (F08):** in every criterion PERS = realized COIN(M−1). The
  available-members and HH-completed persistence forms are reported in a table
  headed BASELINES (descriptive) and enter no criterion.
- **z form of training-row regressors (DT-11):** z_claims6(t) and z_curve(t) in
  row t are the series values with statistics through t (population sd,
  120-month warm-up inclusive of t); the forecast row uses statistics through
  M. Bridged members: projection z against history through M−L, projection
  excluded; actual members: through their own month.
- **ICSA weeks (DT-23):** a week belongs to the month of its week-ending
  Saturday; the week ending the first Saturday of M+1 belongs to M+1; month M's
  mean never contains it.
- **Windows (F17):** reproduction gate 1972-01..2026-06 on F1. Scored window =
  1972-01..the last month in which all four members are published in F5 (the
  harness computes and logs it; expected 2026-07 or 2026-08); n reported; every
  bar applies to that window; the F1-vs-F5 realized-target differences (RMS,
  max, label flips) are tabulated in the honesty box.
- **ENS_GRID (F21, DT-22):** ENS_GRID_REPRO (August member forms; selector
  errors through M−1; 354/630) is a gate only. ENS_GRID_D3 (members in their
  HH/available forms at IS-A/IS-B; selector errors through M−2) is the reported
  no-hindsight check. Only the latter appears outside §7.1.

### 2. The v2 engine (v0 §2 plus)

**2.1 Lag-generalized bridge.** As v0. The 1959 z start is applied to the
COINCIDENT members only (DT-10); the leading composite keeps its 1960 start and
its frozen claims (3 of 15 spells false, strictly early 4 of 7, 82.5% real-time
agreement) are annotated in the docstring as measured on 1960-start labels.

**2.2 Completed coincident and its band (F03, F12, DT-19).**
- COIN_HH(M−1 | d) completes each member at lag L_c − 1 (floored at 0); the
  §2.4 drop rule applies there too.
- The band is keyed to the **bridged pattern P of the displayed month** (the
  set of {member: lag} actually bridged for that month at that issue date),
  never to the IS label. For every pattern that can occur on the board —
  {CMRMTSPL: 1}, {W875RX1: 1, CMRMTSPL: 2}, {INDPRO: 1, W875RX1: 1, CMRMTSPL: 2}
  and the lag-3 / dropped-member variants — the lag simulation stores the
  walk-forward error distribution e = realized − COIN_HH(P) over targets
  1990-01+ ex-2020 where ≥ 1 member is bridged (PRIMARY band); 1977-07+ full
  and with-2020 as sensitivities. The board draws [completed + p10(e),
  completed + p90(e)] (asymmetric if the data are) and names P.
- A bridged member whose g history through M−L has < 120 observations is
  skipped and the mean re-taken, flagged members_bridged / members_skipped.
- The band around any historical point is estimated from completion errors
  dated before that point (expanding); the live band uses all history; any
  reported coverage is walk-forward. Label: "completion error only,
  final-vintage data; first-print revision not included" until the real-time
  replay band is scored.
- Reviewer's fixture estimates for the record (not gates): 1 bridged p10/p90
  −0.123/+0.117 (RMSE 0.126); 2 bridged −0.219/+0.216 (0.257); 3 bridged
  −0.293/+0.276 (0.335).

**2.3 CLAIMS_HH, row admission and the IS label (DT-2, DT-7, DT-16).**
- ROW ADMISSION (D2, all information sets, both regimes): with P_c(d) the
  latest month of member c in the vintage ≤ d, M = P_PAYEMS(d), L_c = M −
  P_c(d) and K(d) = min_c P_c(d) = M − max_c L_c, a training or calibration row
  t is admissible at d iff t ≤ K(d) and its target is not a partial-member mean
  (D6; the 1969-06..1977-05 three-member months count as complete). Canonical
  values K = M−2 (IS-A, IS-B), M−1 (IS-C); the vintage, never the calendar,
  decides (IS-A: M−3 when CMRMTSPL(M−2) is not in hand; IS-C: M−2 on the 24 of
  160 W875RX1 days 2013–2026 when CMRMTSPL(M−1) is not in hand; shutdown
  states: whatever max_c L_c gives).
- IS LABEL at any date d: A if P_INDPRO < M; B if P_INDPRO = M and P_W875RX1 <
  M; C if P_W875RX1 = M. The CMRMTSPL state is carried as a lag, never in the
  label; the CLAIMS_HH fit used is the labelled IS's. Every scorecard row
  carries the lag pattern in hand; IS-C rows with L_CMRMTSPL = 2 are flagged.
- Identity gates: IS-C completed COIN(M−1) == realized only on rows with
  L_CMRMTSPL = 1; IS-C CLAIMS_HH coefficients == the original CLAIMS to 1e-9
  when both fits are restricted to rows t ≤ 2026-05 (no partial targets); the
  n = 587 reproduction is a separate gate on the original form.
- Spec-alignment changes to the deployed module (DT-10): the commit writes a
  schema key into `cycle_phase.json` and `phase_change()` re-adopts the baseline
  quietly when the key is missing or differs (no alert from re-standardisation
  alone); the counter-agent records the current label before/after on F1 and
  F3; the frontend renders `nowcast.reason` as display text.

**2.4 Shutdown / over-lag rule (DT-7, F13).** The target is always the last
PAYEMS month in hand; the nowcast is None only when no PAYEMS observation exists
for a month later than the last complete COIN, and every None carries a reason.
Lags 1–3 bridged with their own fit; lag ≥ 4 dropped and the mean re-taken,
flagged. Dropped-member band = p10–p90 of (realized 4-member COIN − k-member
mean of the remaining actual/bridged members) over targets 1977-07+ ex-2020 for
that exact dropped set, from the lag simulation (the deployed partial 3-member
error — fixture RMSE 0.143, p10/p90 −0.12/+0.21, bias +0.03 on 1990+ ex-2020 —
is the {CMRMTSPL dropped} case). Expected F4 outputs, written now: 2025-11-20 →
value, IS-A, lags {0,1,1,2}; 2025-12-16 → value, IS-A, lags {0,2,2,4},
dropped = [CMRMTSPL], wide band; 2026-01-09 → value, IS-A, lags {0,1,3,3};
2026-02-06 → value for 2025-12, IS-B, lags {0,0,1,2} (an engine gate, not an
issue date). F4 gains the ICSA vintages at 2025-11-20, 2025-12-16 and
2026-02-06 (T10Y3M may be current).

**2.5 Board contract.** As v0; alerts and the provisional rule stay on the
partial `coincident` until the real-time replay band (which includes first-
print revision) is scored; the band shown is keyed to the displayed month's
pattern (§2.2).

### 3. Lag simulation (v0 §3 plus F11, F15)

RMSE_A ≥ RMSE_B ≥ RMSE_C is a DIAGNOSTIC evaluated on the full-sample, 1990+
and ex-2020 aggregates only: a violation halts the read-out and triggers a bug
hunt (training-row admission, z history, lag keying) before any result is
quoted; it is neither pass nor fail. Availability is a descriptive table: days
per calendar month (2013-06+ and the 2025-10..2026-04 shutdown window
separately) with a reading for the latest PAYEMS month — deployed gate vs v2 vs
ADS — plus the frequency of each lag pattern and of dropped members.

### 4. Real-time replay (v0 §4 rewritten per DT-1, DT-5, DT-8, DT-9, DT-13, DT-14, DT-20)

**4.1 Regime (i), true real-time 2013-06-14..2026-10.** EVERY quantity entering
a nowcast issued at d is computed from the vintages dated ≤ d: the month axis,
the expanding-z histories (mean, sd, warm-up) of every member and regressor,
the bridge fits, the CLAIMS_HH training TARGETS COIN(t) for t ≤ K(d), the ADS
calibration targets, and the persistence baselines. The only objects carried
across issue dates are the stored completions COIN_HH(t−1 | IS) (D4): for t
with an issue date in regime (i) they are the values stored at t's own issue
date; for earlier t they are the canonical-lag completions recomputed
walk-forward on the vintage in hand at d (fits through t−1−L only), labelled
`spliced history` in results.json. No final-vintage value enters any
regime-(i) number except the latest scoring target of §4.2(b). Series pulled:
PAYEMS, INDPRO, W875RX1, CMRMTSPL, ICSA; T10Y3M and BAA10YM taken current
(basis: 0 changed values in six ALFRED vintages 2015–2026; re-checked on the
run day against one 2026 vintage and recorded in results.json). Leading-set
vintages (PERMIT, AWHMAN, UMCSENT) are NOT pulled for the scored run; a
real-time 5-phase label, if charted, is labelled unscored. Regime (i) contains
three shutdown windows (2013-10, 2018-12..2019-02, 2025-10..2026-01); rows with
a dropped member or any lag ≥ 3 are flagged and counted per IS.

**4.2 Regime (ii), pseudo-real-time 2000-01..2013-05** = the §3 lag simulation
(canonical patterns on final-vintage data) evaluated at ACTUAL issue dates:
IS-A and IS-B from the ALFRED first-vintage dates of PAYEMS and INDPRO; IS-C
from the first-vintage dates of BEA Personal Income (PI, ALFRED from
≤ 1998-01-09) as the PI&O-day proxy, W875RX1's own dates from 2010-05-28. The
1st-of-month lag table is evidence only, not an emulation source. CMRMTSPL did
not exist before 2013-06; regime (ii) is the same computation as §3 with dated
issue points, used only to align the ADS (2009-01+), Chauvet–Piger and
NBER-announcement comparisons. The two regimes are never pooled.

**4.3 Issue dates and scoring targets (DT-9, DT-17, F19).** Issue date for
(series, M) = the earliest listed vintage whose last observation month is M
(content-decided; revision-only vintages are not issue dates). Each (issue
date, IS) scores exactly one target: the latest month of the trigger series in
that vintage; months that were never the latest month of a trigger series
(e.g. 2025-10 at IS-A/IS-B) have no row at that IS and are never back-filled;
n per IS is reported. (a) target_first(M) = COIN(M) computed wholly from the
vintage dated v*(M) = max over the four members of the first vintage date
containing M, with expanding-z statistics from that vintage (regime (i) only,
M ≥ 2013-04). (b) target_latest(M) = COIN(M) on F5. Both stored in
results.json.

**4.4 Pull engineering (DT-5, DT-24).** Fetch ONLY exact dates from each
series' vintage list (`alfred.stlouisfed.org/series/downloaddata?seid=<ID>`,
frozen as F8, ICSA included), never a snapped date; for issue date d use the
latest listed vintage ≤ d. Validate before caching: HTTP 200; first line
exactly `observation_date,<ID>_<YYYYMMDD>` with YYYYMMDD equal to the listed
date; ≥ 1 data row; last observation month recorded. A 404 with empty body is
allowed only for dates before the list's first entry. 5xx, timeouts and any
non-CSV body: retry with backoff, then hard-fail; never cached, never read as
"no vintage". Cache key = (series, listed vintage date). ~2.5k requests;
concurrency ≤ 8. Q13 (FRED key) is a P3 convenience.

### 5. Comparator: calibrated real-time ADS (v0 §5 rewritten per F06, DT-3, DT-6, DT-18, DT-21)

- **Readings.** ADS_last(d) = last daily value in the latest vintage dated ≤ d
  (descriptive only). ADS_avg(M | d) = mean of the daily values dated within
  target month M present in that vintage (at IS-A the payrolls-day vintage
  already extends to the last calendar day of M). The ADS vintage is the latest
  dated ≤ d, same-day vintages included (information parity with the release
  that defines d); the "< d" choice is a sensitivity.
- **Calibration, PRIMARY.** Vintage-consistent COIN(t) (§4.1) regressed on the
  STORED real-time ADS reading issued for target t at the same IS (one
  calibration for ADS_avg, one for ADS_last), walk-forward, rows t ≤ K(d), at
  least 24 rows else no calibrated reading (first scored month ≥ 2011 on the
  2008-12+ archive). SENSITIVITY: the same regression on the issue-date
  vintage's own monthly averages, labelled "smoothed-fit, filtered-apply".
- **Symmetry.** The identical walk-forward affine step, same rows, is applied
  to ENS_HH; the comparator number is calibrated-vs-calibrated; raw ENS_HH is
  also reported.
- **Months.** All comparator metrics are computed on the intersection of
  months where both sides have a calibrated reading; n reported. ADS
  claims-only vintages (2025-10-16 → first full update) are flagged in the
  availability count and excluded from the accuracy comparison as a
  sensitivity. The ADS post-2023-09-28 parameter regime is stated; it does not
  touch the pre-2023 real-time end-points that are scored.
- **Comparator reproduction gate.** From the archive: correlations of the
  real-time last point (0.866) and the previous-complete-month average (0.956)
  with the 2010-12-03 vintage over every vintage dated 2008-11..2010-10, each
  within ±0.01; the right-line figure (0.916) is quoted, not gated.

### 6. Chauvet–Piger cross-check (v0 §6 plus F09, DT-15)

- Value vector for Piger release r at date d_r with latest month m_r = the
  first ALFRED vintage dated ≥ d_r whose latest observation month is m_r
  (fallback: Piger's column); timestamp d_r. The FRED smoothed series enters no
  scored number.
- Peak dating under the 3×80% rule = the month before the first ≥ 50% month
  preceding the trigger (Chauvet–Piger 2008).
- All comparisons on a calendar-date clock: Piger = release date; our realized
  crossing of m_c = regime (ii) the IS-C issue date (PI proxy) of the month on
  which COIN(m_c) first printed in full, regime (i) v*(m_c); ENS_HH crossing of
  m_n = the payrolls day of m_n+1; 2001 and 2008 are pseudo-real-time on our
  side and labelled so.
- False declarations: none under either rule in 2006-08..2026-09; the
  2021-10-29 release (Sep-2021 44.4%, reversed to 2.4% a month later) is
  reported as the largest non-recession real-time print. Descriptive
  throughout; no grade.

### 7. Gates, fixtures and the freeze (v0 §7 plus F05, F10, F17, DT-4, DT-10, DT-16)

**7.1 Reproduction gate.** Runs the harness in `reproduction_mode` = {bridge
training rows t < M for every lag; CLAIMS rows t ≤ M−1 including the 2026-07
PAYEMS-only partial target; selector errors through M−1}, on F1 only, targets
1972-01..2026-06, the v0 §7.1 table with PERS tolerances tightened to ±0.0001
(deterministic arithmetic; pins population vs n−1). A second gate row runs
`scoring_mode` (D1 rows t ≤ M−L; D2/D6; D3) on the same fixture and RECORDS the
deltas: required |ΔRMSE| ≤ 0.003 for BRIDGE/CLAIMS/ENS, |Δdir| ≤ 1 pp, and any
change in an exact count (transitions, onsets, false alarms) is logged with the
month, both values and the realized value (expected: 1980-11, one transition).
The scored run uses scoring_mode only. An exact-count gate that misses emits
the month-level diff and blocks; it is never widened; it is raised to Casey.

**7.2 Engine gates.** As v0 §7.2 with the §2.4 expected outputs.

**7.3 Fixtures.** F1–F5 as v0 (F1 remains the fixture for the composite /
nowcast / read-box gates with bounds unchanged; F3/F4/F5 carry their own
bounds, any F5 bound written into the test with its deterministic value logged
BEFORE results.json is read). Added: **F6** = the ALFRED vintage panel — a
committed table (series, listed vintage date, sha256, bytes, last observation
month) plus the derived per-issue-date panel (issue date, IS, series, month,
value); raw CSVs may stay out of git if every row carries its hash. **F7** =
the ADS derived panel per vintage (vintage date, last date, last value, monthly
averages for the last three months) with the sha256 of the zip and the xlsx.
**F8** = the vintage lists vd_*.txt (ICSA included) and Piger's history file
re-pulled on the run day and committed with hashes. results.json records the
sha256 of F1–F8 and the first/last vintage date used per series; a correction
run that changes any hash is a new run.

### 8. Pre-registered decisions (v0 §8 rewritten per F01, F02, F04, F16, F18, F20)

Three decisions, each resolved by exactly one number; every column of every
results table carries the tag DECISION or DESCRIPTIVE; no descriptive number is
quoted as a pass or fail in the honesty box or on the panel. Every decision
ratio is reported with its deterministic leave-one-calendar-year-out min/max
and the year that produces each; no bootstrap, no seed.

**D-1 Primary (lag simulation, IS-A, scored window).** ENS_HH RMSE ≤ −25% vs
PERS (realized COIN(M−1)) full-sample AND ≤ −8% ex-2020 AND DM ex-2020 ≤ −1.645
— all three (conjunction). PASS → ENS_HH at the IS in force is the one-month-
ahead reading on the board with the v2 numbers in its stats block. FAIL → the
v2 engine still ships for availability (no better candidate exists; the
deployed fixed-lag gate is strictly worse), the panel text drops the August
accuracy claim and shows the v2 numbers with the missed bar named; no
re-tuning, no alternative ensemble is tried in this study. Secondary
(DESCRIPTIVE): transitions per IS, missed onsets per IS, each IS vs PERS,
onset calendar advantage, false alarms.

**D-2 Completed vs partial headline.** On targets 1977-07+ (months where the
pattern bridges ≥ 1 member), RMSE of (realized − COIN_HH) for the 1-bridged
completion [PAYEMS, INDPRO, W875RX1 actual; CMRMTSPL L1] must be lower than
RMSE of (realized − partial 3-member mean) on the SAME months, both full and
ex-2020, both computed by the v2 harness; p10/p50/p90 and bias of both
reported. The QA gap 0.126 is context only. PASS → `coincident_completed` is
shown as the headline value with its band (Q6 default keeps the partial as the
gate/alert quantity). FAIL → the completed value is shown as a secondary line.

**D-3 Comparator.** IS-A; regime (i) 2013-06+ true vintages; scoring target =
target_latest (PRIMARY), target_first must agree in sign or the decision is
deferred to the next R2; ADS reading = ADS_avg(M | d) after the §5
calibration; ENS_HH calibrated identically; months = the intersection; ex-2020
targets are DECISIVE, with-2020 numbers are reported and never decide. Let r =
RMSE_ENS / RMSE_ADS (ex-2020). SUCCESS: r ≤ 1.10 (point estimate, with its
leave-one-year-out range). KILL: r > 1.25 AND one-sided DM on d_t = e_ENS² −
e_ADS² (H1: mean d > 0, NW-6, p < 0.10) → calibrated ADS becomes the headline
and ENS_HH the cross-check. MIDDLE (1.10 < r ≤ 1.25, or r > 1.25 without DM
significance): keep the home-built headline, add calibrated ADS as a second
line labelled with the measured gap, re-decide at the next R2 calibration.
This is a tracking-accuracy decision on expansion-dominated months and says
nothing about recession-timing skill; the real-time regime cannot establish
v2's edge over persistence ex-2020 (fixture: ratio 0.915, DM −0.89) and no such
claim is made; onset timing on 2013-06+ (one event, expected tie at
2020-04-03) is reported. X = 10% and Y = 25% stay pending Casey (Q1) — with
these definitions, 10% RMSE ≈ 21% MSE is below the ~30% MSE minimum detectable
difference ex-2020 on n ≈ 145, so success is a point-estimate statement and
only the kill is a tested one.

The ICNSA + frozen-SA sensitivity (Q10) is NOT run in this study; it goes to the
robustness backlog (F14).

### 9. Honesty, stated now (v0 §9 plus DT-12, DT-20)

Final-vintage leakage in §3 and regime (ii) includes, beyond level revisions:
two-sided seasonal factors (all members, ICSA), annual/comprehensive revisions
and base-year changes (CES benchmarks each February; the 2013/2018/2023 NIPA
revisions; chained-dollar bases for W875RX1; IP rebasings), series definition
changes (CMRMTSPL built 2013-06 with an HMRMT back-cast before 1997; the
W875RX1 code change 2017-10-30; the CES sample redesign), and final-data
z-score histories; regime (i) removes these from 2013-06 only. Regime (i)'s
three shutdown windows are flagged. The rest as v0 §9.

### 10. Pending questions — as v0 §10, with: Q15 redefined (ADS_avg(M | d) is THE
comparator reading, the last point descriptive); Q13 a P3 convenience (~2.5k
keyless requests); Q10's sensitivity decided (not run). Q1–Q5 remain asked.

Added 2026-10-20 by the B3 fix pass (run-script reviews, findings S1/D1 and D6); both
are carried in `freeze_template.json` and `run_study.py --real` refuses a freeze that
does not answer them (expiry 2026-12-19):

| Pri | # | Question | Default carried by the harness (NOT an answer) | What it moves | Status |
|---|---|---|---|---|---|
| P1 | Q16 | §5 calibration store. As built, both sides are calibrated on the STORED regime-(i) real-time readings at the same IS on identical rows (§5 Symmetry), so the first calibrated reading comes ≥ 24 stored regime-(i) months after the first row: on the real panel IS-A rows start 2013-06, the first calibrated reading is ~2015 and the D-3 decisive sample is ~120 ex-2020 months — not "first scored month ≥ 2011 on the 2008-12+ archive" (§5) and not "n ≈ 145" (§8 D-3). The clauses cannot all hold. Keep the symmetric store (record the gap), or seed the ADS side from the 2008-12+ archive at list-proxy IS points against vintage-consistent COIN(t) with a labelled pseudo ENS side (asymmetric rows; engine change + SPEC v1.2)? | `regime_i_stored_readings_symmetric_rows` (the seeded store is not implemented and refuses) | the D-3 decisive sample (~24 months) and the §8 power note; whether the scored run may start | asked |
| P1 | Q17 | §8 D-3 "target_first must agree in sign or the decision is deferred": the literal reading sign(r_first − 1) == sign(r_latest − 1) defers e.g. r_latest 1.05 / r_first 0.98 although both are SUCCESS; the alternative reading "same outcome class under target_first (same X/Y thresholds, one-sided DM on target_first errors)" defers only when the classes differ. The synthetic dry run shows the two readings CAN differ (KILL vs DEFERRED). Which reading? | `sign_of_r_minus_1` (both readings implemented; both classes always recorded) | whether D-3 is decided or DEFERRED at the margin | asked |

### 11. Run order — as v0 §11, with step 3 = the vintage-list pull (F6), the ADS
archive conversion (F7), the run-day re-pull of lists and Piger's file (F8),
the comparator reproduction gate, and the hashes into results.json.

### Counter-agent log (continued)

| review | verdict | adopted |
|---|---|---|
| statistics, SPEC v0 (2026-10-20) | BLOCK — Q2 criterion vacuous (IS-C identity) / knife-edge (0.126); comparator decision undefined over part of the outcome space and untestable with 2020 in (94.7% of 2013+ persistence SSE is 2020; minimum detectable MSE gap ~30% ex-2020); band keyed to the IS label not the displayed month's bridged pattern (2× wrong at IS-B, zero-width at IS-C); no consequence on a primary miss; reproduction gate did not pin the estimator (scoring mode fails the exact transition count at 1980-11 by 0.003); ADS calibration asymmetric and errors-in-variables; directional and DM conventions unpinned; 14 more | all 21 (F01–F21) |
| data/timing, SPEC v0 (2026-10-20) | BLOCK — regime (i) silently trained and calibrated on final-vintage targets and z-histories; row admission encoded the 2026 calendar (fails on 22 of 56 IS-C days 2013–17 and in shutdown states); ADS calibrated on smoothed in-vintage values but scored on filtered end-points; nothing frozen for the real-time run (F6–F8 added); served-vintage identification unsound (fetch by vintage list); shutdown expected outputs unwritten; pseudo regime's lag table anachronistic (PI-vintage IS-C dates); first-print target undefined; 1959 start would shift the leading composite and could fire a spurious phase alert; 14 more | all 24 (DT-1–DT-24); the AWHMAN 2026-04 row in `data/alfred_first_vintage_2026.csv` corrected to 2026-05-08 (binary-search artifact) |

---

## SPEC v1.1 — amendments 2026-10-20 after the engine build and its three adversarial reviews (still nothing scored)

The engine and pipelines are built (`cycle_nowcast_v2/`: engine.py, metrics.py,
gates.py, vintages.py, ads.py, piger.py, nber.py; 150 tests pass offline, 6
known misses as strict xfails, one deliberately red test that lists the hard
misses below until they are ruled on). The reproduction gate on F1 passes on
every August number (PERS 0.467416 / 0.531598 / 0.258044 to ±0.0001; BRIDGE,
CLAIMS, ENS_BC RMSEs, directional, phase, 29/114 transitions, DM −1.6335 /
−5.3379, every onset month and false alarm; the identity gates to 0.0; the
legacy and spec-form live outputs; F3 and all four F4 shutdown cases produce
the pre-written outputs). Six rows missed and are RULED here — none by
widening a tolerance; each ruling is a definition correction with both values
kept on record:

| miss | computed vs target | ruling |
|---|---|---|
| G04 ENS_GRID_REPRO 50/50 count | 361 of 630 vs 354 ± 5 (361–370 under every convention; RMSE row 0.331865 passes; 97 of 630 selections within 1% MSE of a runner-up) | A hindsight-selector count with near-ties is not reproducible to ±5 without the August harness; ENS_GRID_REPRO is gate-only and feeds nothing scored. Row becomes DESCRIPTIVE (reported, not gated) **pending Casey Q5**; if the August harness is found, the count is re-gated against its selector tie-break. |
| S01/S04 scoring-mode delta row, literal D2 reading (CLAIMS rows t ≤ K = M−2) | ΔCLAIMS −0.0307 (0.3930 → 0.3623; 2020-only 2.33 → 2.02; ex-2020 +0.0037), ΔENS −0.0118; four transition flips, 1980-02 crossing 1979-10 → 1979-12 | The v1 expectation ("1980-11 only, |Δ| ≤ 0.003") was derived under the D1+D6 reading, which passes exactly as written. The literal D2 row is the honest cost of training only on published targets and is kept as a RECORDED row (DESCRIPTIVE), not a gate; the D1+D6 row stays the gate that pins the estimator. The scored member CLAIMS_HH uses rows t ≤ K(d) by construction (§2.3). |
| Q01/Q04 soft ENS_BC_S | −22.09% vs −24.2 ± 1 pp; onsets 4-2-1 vs 5-1-1 (ex-2020 −7.88% passes; DM −3.07) | The QA harness's S construction is not recoverable (A16). Recorded as a soft miss; **Casey Q5** decides whether to hunt further or accept; it enters no decision. |
| Q05 soft ENS_BC_HH | NOT_RUN | Correct by the pre-registration: ENS_HH at IS-A is the D-1 quantity. It is computed once, in the scored run, on F5 (decision) and on F1 (honesty box, beside the August −29.8% / −12.5% / 30.7% / 4-1-2). |
| §5 ADS comparator reproduction gate | every-vintage sample 0.8083 / 0.9253 (n = 176) vs 0.866 / 0.956 ± 0.01; the cited note's own IP-release-day sample reproduces 0.8655 / 0.9560 (n = 24) | The gate is redefined to the note's own sampling (IP-release-day vintages, Nov-2008..Oct-2010, vs the 2010-12-03 vintage), which is what the note computed; PASS. The every-vintage correlations are reported beside it as DESCRIPTIVE. |
| §6 Chauvet–Piger 2008 peak month | rule as written → 2008-01 (Feb-2008 = 51.98% is the first ≥ 50% month); the text said 2008-02 | The rule stands; the text is corrected: under the 3×80% rule declared at the 2009-01-01 release, the model dates the peak 2008-01 (NBER: 2007-12). |

Other v1.1 amendments from the build notes (definitions the builders had to
choose; all recorded in `notes_B1.md` §2 and `notes_B2.md` §5):
- §2.2 skip rule (< 120 g observations through M−L) applies in both modes;
  touches 1977-06/07 only.
- ENS_GRID_REPRO uses a 1959-start leading composite in its LEADREG member
  (pinned by the August LEADREG row to 4 dp); the board's leading composite
  keeps 1960. ENS_GRID_D3 member forms (PERS_HH, AR2_HH with realized
  COIN(M−2), LEADREG_HH) are implemented and must be confirmed against §2.3
  before the scored run.
- §4.4 validation: a missing value in an ALFRED CSV is an empty field or ".",
  both read as None (the T10Y3M vintages have hundreds of empty fields and no
  "." rows).
- F4's twelve member files were fetched at non-listed dates (header echo);
  content verified (lags reproduce); they are re-pulled at listed dates in the
  run-day re-pull (F8). The ICSA vintages for the four F4 dates were added at
  listed dates; the claims half of all four shutdown cases now gates.
- Raw ALFRED vintage CSVs (57 MB) are not in git; `data/vintages_panel/`
  carries the vintage table with per-file sha256 and the per-issue-date panel
  (1,571 vintages; 1,568 requests, 0 validation failures, one transient
  timeout retried); the ADS derived panel carries the archive hashes. A fresh
  container re-pulls by list (~2.5 min) and re-converts (~3.5 min) and must
  reproduce the committed hashes before scoring.
- Bands are plumbing until the scored lag simulation supplies the per-pattern
  p10/p90; `issue()` returns band = None with basis "pending" until then.
- One ALFRED RECPROUSM156N vintage (2023-02-01) carries a back-history load
  glitch (Mar/Apr-2020 at 0.14/0.04% vs Piger's 100/100); no rule outcome
  changes; a chart from ALFRED vectors must mark that release. Seven Piger
  releases have no matching ALFRED vintage and use the Piger-column fallback
  §6 allows.

### Counter-agent log (continued)

| review | verdict | adopted |
|---|---|---|
| build B1 engine, correctness lens | PASS_WITH_FIXES (9) — cache-key aliasing between row-admission designs; absent/empty/short member silently dropped as "not existing"; hard-gate misses hidden behind strict xfails | all applied: keyed caches, explicit member-state classification with reasons, a red test that lists hard misses until ruled |
| build B1 engine, look-ahead lens | PASS_WITH_FIXES (11) — same aliasing seen from the look-ahead side; no look-ahead found in the shifted-input, synthetic-AR and row-admission attacks | applied |
| build B2 pipelines, integrity lens | PASS_WITH_FIXES (10) — the frozen inputs for the real-time run were not fully in git (F6 round trip); empty-field handling; AWHMAN calendar row | applied: F6 round-trip test from the committed table + tar; validation rule corrected; calendar check byte-identical |
| fix pass | 21 applied, 7 rejected with evidence (the six rulings above plus one tested retry-sequence change) | — |
| build B3 run script + synthetic dry run, contract lens (16: 2 SERIOUS, 7 MINOR, 8 NOTE) and look-ahead lens (12: 1 SERIOUS, 2 MINOR, 9 NOTE) (2026-10-20) | SERIOUS: the D-3 decisive sample loses the calibration warm-up unflagged (S1/D1); the §4.1 run-day unrevised re-check cannot execute in --real (S2). MINOR: one-scored-run per --out only, correction runs not hash-checked, --cache bypass, --ads-matrix / --f1 unpinned, no committed-state check, pass/fail booleans in DESCRIPTIVE DM records, list-proxy boundary, raw tracebacks on a missing manifest | fix pass: every SERIOUS / MINOR and the NOTE items applied (notes_B3 §8); Q16 and Q17 opened above; rejected with evidence: requiring an identical spec hash for a correction run (the results are written into this file after the run), and the ENS_GRID_D3 form confirmation (spec-owner item, now a --real blocker) |

---

## SPEC v1.2 — rulings 2026-10-20 on the run-script reviewers' two questions (spec owner; still nothing scored)

- **Q16 (§5 calibration store) — RULED: keep the symmetric regime-(i) store as
  built.** Both sides are calibrated on STORED real-time readings at the same IS
  on identical rows, so the first calibrated reading arrives ≥ 24 stored months
  after the first regime-(i) row (~2015 on the real panel) and the D-3 decisive
  sample is ~120 ex-2020 months, not the ~145 the spec expected. The ~145 was an
  expectation, not a requirement; symmetry is the requirement. The harness
  records the actual n, the first calibrated month and the warm-up in
  `decision_D3.calibration_warmup` and the honesty box. Seeding ADS from the
  2008-12+ archive against a pseudo-real-time ENS side is NOT done (it would
  compare a real-time ADS with a final-vintage ENS — the asymmetry §5 forbids).
  The minimum-detectable-difference caveat in §8 D-3 is restated for n ≈ 120.
- **Q17 (§8 D-3 "target_first must agree") — RULED: outcome-class agreement.**
  D-3 is evaluated twice with identical thresholds and tests: on target_latest
  (PRIMARY) and on target_first. The decision stands only if both land in the
  same class (SUCCESS / MIDDLE / KILL); if the classes differ the decision is
  deferred to the next R2 calibration and both classes are reported. The literal
  sign(r − 1) reading is rejected because it would defer two SUCCESS outcomes
  that straddle r = 1.
- **ENS_GRID_D3 member forms — CONFIRMED** as implemented (PERS_HH; AR2_HH on
  realized COIN(M−2) and the completed COIN(M−1); LEADREG_HH on the completed
  COIN(M−1) and LEAD(M−1)); the "pending confirmation" flag is dropped. It is
  DESCRIPTIVE only.
- **Run-day F8 re-pull** must also fetch one LISTED 2026 vintage each of T10Y3M
  and BAA10YM into the raw cache (the §4.1 unrevised re-check refuses without
  them) and rebuild the F6 tarball and build_summary so the hashes match.
- Casey's Q1–Q5 remain the only open inputs; `run_study.py --real` refuses a
  freeze file that does not answer them.


## RESULTS — the ONE scored run, 2026-10-28 (verified; correction 1 wording-only)

Decided under SPEC v1 (2026-10-20) with the v1.1 and v1.2 amendments (spec sha256
`6da4a8e7…`), freeze.json `64109389…` — Casey answered every question at the SPEC
default on 2026-10-28 (X = 10, Y = 25, two regimes never pooled, drop-and-re-mean,
gate F1 / score F5, Q16/Q17 as ruled; the August harness is **not retrievable**).
F5 = `data/fred_2026-10-28` (13 series, keyless, hashes in `MANIFEST.json`); F6/F7/F8
re-pulled on the run day (`notes_freeze.md`). Real data were scored exactly once
(`results.json`, run_id `79fcb272…`, commit 168aafe1); **correction 1**
(`results.correction-1.json`, run_id `1eac4c97…`) re-ran the same frozen inputs
after the verifiers' notes: **0 numeric leaves differ**, decisions identical; only
basis strings, the matrix hash label, `spec.version` and two honesty statements
changed (`corrections.log`). The superseded original carried a session scratch
path under `inputs.hashes` and is retired from the tree (unedited at 168aafe1,
sha256 `8bfc1b04…` on record).

Verification (both independent of the authors; verdicts logged in
`verdict_A_recompute.md`, `verdict_B_claims_wording.md`):

| verifier | verdict | what it did |
|---|---|---|
| A — recompute | PASS_WITH_NOTES, 0 BLOCKING / 0 SERIOUS / 0 MINOR | own implementation of the spec from the raw F5 CSVs and the F6 tarball: every D-1/D-2/D-3 number, window, count, DM, LOYO, calibration coefficient and 5 regime-(i) rows replayed from raw vintages reproduce to full double precision |
| B — claims & wording | PASS_WITH_NOTES, 0 BLOCKING, 2 SERIOUS (wording/provenance) → correction 1 | every DECISION record traced to §8; thresholds = frozen defaults; rulings v1.1/v1.2 honoured; tag audit 255/0 recounted; §9 honesty items checked |

### Decisions (frozen rules, frozen thresholds)

| decision | rule as frozen | result | verdict |
|---|---|---|---|
| **D-1** one-month-ahead nowcast (ENS_HH at IS-A vs PERS = realized COIN(M−1); final-vintage lag simulation 1972-01..2026-07, n 655 / 643 ex-2020) | RMSE ≤ −25 % full AND ≤ −8 % ex-2020 AND DM NW-6 ex-2020 ≤ −1.645 | **−29.9 % / −12.5 % / t −4.69**; LOYO ratio 0.696–0.875 full, 0.870–0.883 ex-2020 (full-sample DM −1.57 is reported, not a bar) | **PASS** |
| **D-2** completed coincident vs the partial 3-member mean (1977-07..2026-07, n 589 / 577) | completed RMSE < partial, full AND ex-2020 | **0.133 vs 0.168** (full), **0.099 vs 0.142** (ex-2020); bias +0.003 vs +0.040; p10/p90 −0.13/+0.12 vs −0.13/+0.21; LOYO 0.685–0.725 ex-2020 | **PASS** |
| **D-3** calibrated ENS_HH vs calibrated ADS, true real time (regime (i), IS-A, 2015-07..2026-07, n 120 ex-2020) | r = RMSE_ENS/RMSE_ADS ≤ 1.10 SUCCESS; > 1.25 with one-sided DM p < 0.10 KILL; same class under target_first (v1.2 Q17) | **r = 0.713** (0.218 vs 0.306; LOYO 0.650–0.902); DM t −1.75 (ENS not worse); target_first r = 0.704, same class; with-2020 r 0.39 never decides | **SUCCESS** |

Consequences (D-1/D-2 pre-registered text verbatim; the D-3 SUCCESS consequence
is inferred from §8, which pre-registers text for KILL and MIDDLE only):
ENS_HH at the information set in force is the one-month-ahead reading on the
board with the v2 numbers in its stats block; `coincident_completed` is shown as
the headline value with its band (the partial mean stays the gate/alert quantity,
Q6 default); the home-built ENS_HH stays the headline and calibrated ADS is
reported as the comparator (within X).

### What the numbers say (descriptive; no grade)

- **The D-1 edge is real but thinning.** Rolling ratios on the same ex-2020 rows
  (chart-only, post-hoc, not in results.json): 1972–89 0.865, 1990–99 0.892,
  2000–12 0.841, **2013+ 0.940**, 2016+ 0.926. Half the whole-sample edge comes
  from the ensemble: BRIDGE alone −5.1 % ex-2020, CLAIMS alone −7.1 %, ENS −12.5 %.
  The ENS_GRID_D3 selector (DESCRIPTIVE) does not beat the fixed 50/50
  (ex-2020 RMSE 0.2295 vs 0.2254) and picks 50/50 on 345 of 631 targets.
  Onsets at IS-A (window [−6, +12]): earlier 4 (1981 by 6 months, 2008 by 4,
  2001 and 2020 by 1), tie 1 (1990), later 2 (1973/74, 1980 by 1 month), missed 0;
  one sub-−0.75 false alarm (1981-06, two months before the 1981 onset);
  30.5 % of realized phase transitions called a month early. IS-B/IS-C improve
  monotonically (−21.8 % / −43.4 % ex-2020; the §3 diagnostic holds).
- **True real time (regime (i), ALFRED vintages, 159 IS-A issue dates
  2013-06-14..2026-10-02, ONE recession): reported, no verdict.** Ex-2020 RMSE
  vs the final-vintage target: ENS_HH **0.234**; the HINDSIGHT persistence
  (final-vintage COIN(M−1), which nobody holds on the day) **0.194** — ENS is
  **+20.7 % worse** (one-sided DM t +1.37, p 0.085; B +20.6 %, C +10.7 %).
  Against the persistence forms actually in hand it is better: completed
  COIN_HH(M−1) 0.253 (DM −1.64, p 0.05), available-members mean 0.279 (DM −2.13,
  p 0.02) — these two aggregates are computed from the stored rows for the
  write-up, not scored. Full sample (2020 in) −31.6 %. The 2020-03 onset was
  called on the 2020-04-03 issue, one month before the realized line crossed.
  Phase label vs the revised one 78 %. 13 rows had a member at lag ≥ 3, 2 a
  dropped member, 7 fell in the 2025-10..2026-04 shutdown window.
- **Availability.** A v2 reading exists on 100 % of calendar days 2013-06+
  (30.3 days/month) vs 33 % for the retired fixed-lag form (10.1 days/month;
  10.8 % inside the shutdown window); ADS 99.8 %.
- **Regime (ii), 2000-01..2013-05, pseudo-real-time (list-proxy issue points,
  labelled):** ENS_HH crossed −0.75 on 2001-04-06 vs the realized line's first
  full print 2001-05-29 (1 month), and on 2007-12-07 vs 2008-05-01 (4 months).
- **D-3 context.** Calibration is a walk-forward affine fit of each reading to
  realized COIN on identical stored rows (first calibrated 2015-07 after 24
  stored months; 25 IS-A rows uncalibrated; n 120 vs the ~145 the spec
  expected — the ~30 % MSE minimum detectable difference scales by
  sqrt(145/120) ≈ 1.10 to ~33 %, so SUCCESS is a point-estimate statement with
  its LOYO range). ENS barely needs calibration (slope 0.82, raw RMSE 0.224);
  ADS does (mean slope 0.36). Sensitivities: smoothed-fit r 0.704, strict "< d"
  r 0.703; the claims-only exclusion is **identical to the primary because no
  scored row used a claims-only vintage** — it demonstrates nothing. Tracking
  accuracy on expansion-dominated months; one onset event (tie, 2020-04-03).
  ADS reproduction gate: 0.8655 / 0.9560 vs the note's 0.866 / 0.956 (PASS;
  every-vintage correlations 0.808 / 0.925 descriptive).
- **Chauvet–Piger (descriptive, 240 releases 2006-08..2026-09, two recessions,
  no grade).** 3×80 % declared 2008 at the 2009-01-01 release — model peak
  2008-01 (NBER 2007-12), first recession month 2008-02, 13 months after the
  peak, 31 days AFTER NBER's own announcement and 391 days after our
  pseudo-real-time ENS_HH crossing; end declared 2010-01-01 (262 days before
  NBER). 2020 was **never declared by 3×80 %** (100 % at the 2020-04-30 release,
  then re-based; the 1-month ≥ 50 % sensitivity catches it). Largest
  non-recession print by USREC: Sep-2020 at 100 % on the 2020-10-30 release
  (post-trough); outside the 2020 episode, 2021-10-29 at 44.4 % (fires under
  neither rule). ALFRED vintage 2023-02-01 differs from Piger's column by > 1 pp
  (flagged); 80 of 240 releases read from Piger's archive where ALFRED has no
  vintage. Latest: 2026-08 at 0.62 % (2026-09-30 release).

### Honesty box (frozen numbers)

- Measurement basis: population RMSE of (estimate − realized COIN(M)) on
  final-vintage F5 for D-1/D-2 and the lag simulation; D-3 on calibrated
  readings vs the F5 target; ex-2020 = the 12 rows of 2020 dropped and the
  series concatenated; DM NW-6 Bartlett.
- Final-vintage data for the lag simulation and regime (ii): seasonal factors,
  benchmark and definition revisions, final z-score histories; publication
  calendars are not modeled there; 2000–2013 is pseudo-real-time with emulated
  lags. True real time only from 2013-06 — one recession.
- The real-time edge over persistence-in-hand is small and rests on that one
  recession; against hindsight persistence the nowcast is worse. The D-1 PASS
  is a final-vintage lag-simulation result.
- Bands = completion error only (final vintage); first-print revision is not
  included (W875RX1 first prints revise by 0.47 sd with a +0.9 pp bias) until the
  real-time band is scored. Pre-2009 claims on final seasonal factors.
- ADS end-points revise by 0.36 mean-abs; post-2023 vintages embed a COVID
  exclusion. Chauvet–Piger shares the four inputs (a different model, not
  independent data); its smoothed FRED series is two-sided in history.
- F1 reproduction gate on the committed August fixtures: 93 PASS, 16 INFO,
  5 NOT_RUN, 6 recorded misses ruled DESCRIPTIVE under v1.1 (G04, S01_claims,
  S01_ens, S04 hard; Q01, Q04 soft) — never gate failures; the estimator-pinning
  row passes. Q05 computed once on F1: −29.9 % / −12.5 % / 30.7 % / onsets 4-1-2
  on 653 targets (August: 654). The August forms re-run on F5 land within 0.001
  of the August values. The realized target itself moved vs the 2026-08-07
  fixture (NIPA 2026-09-30): RMS 0.018, max 0.220 at 2026-03, 3 label flips
  (2023-01/09/11 STALL→EXPANSION); the mid-2026 "STALL near −0.5" on the August
  fixture was largely pre-revision W875RX1 (2026-03: −0.469 → −0.249).
- T10Y3M and BAA10YM taken current: 0 changed values vs the listed 2026-10-27
  and 2026-10-01 ALFRED vintages. UMCSENT is ~M−2 on the live board (FRED delay)
  — flagged on the panel; the replay is unaffected. The QA variants' numbers are
  soft; their harness is not recoverable.
- Not modeled: a real-time completion band; benchmark-revision pre-adjustment;
  the MS-DFM fitted walk-forward; any re-tuning (none was tried — one run).

### Charts (`studies/cycle_nowcast_v2/figs/`, script `make_charts.py`; series asserted equal to results.json)

`fig_cnv2_d1_lagsim.png` (nowcast vs realized 1972–2026, the 2005+ zoom
against persistence, the rolling 36-month RMSE ratio) ·
`fig_cnv2_d2_completed.png` (completed vs partial error series and
distributions) · `fig_cnv2_regime_i_d3.png` (true real-time replay 2013+, the
calibrated ADS comparison, LOYO r by year) · `fig_cnv2_regime_i_baselines.png`
(real-time RMSE vs the three persistence forms) · `fig_cnv2_chauvet_piger.png`
(the real-time probability path by release date with the declarations).

### What shipped on the board (treasury-canary; redeploy needed)

- `backend/app/sources/cycle_engine.py` = the study engine, byte-identical
  (gate test); `cycle_bands.json` = `board_bands` of the scored run, unedited.
- `business_cycle.nowcast` now issues the v2 reading every day (information
  set, lags, dropped members, reason when None); `completed` = the
  bridge-completed coincident for the headline month with its p10/p90 band
  (D-2), served beside the partial mean, which remains the phase/alert
  quantity; `piger` = the FRED Chauvet–Piger print with the 3×80 % state
  (optional); `flags.umcsent_delayed`; `phase_change` re-baselines
  EXPANSION↔STALL flips quietly inside the revision band (|coin| < 0.46).
- Panel: header shows the completed value with its band and the partial in
  brackets; the chart draws the completed point with an error bar and the
  nowcast beside it; the read box carries the completed, nowcast, Piger and
  delay sentences with the frozen numbers. Gate tests pin the fixture values
  (ENS_HH −0.332 at IS-A for 2026-07; completed 2026-06 −0.322 [−0.436, −0.207]).

### Pending questions (living ledger; 60-day expiry from first ask)

| P | question | would move | status |
|---|---|---|---|
| P2 | Real-time completion band: score the first-print revision of the completed value on the stored regime-(i) rows (target_first is stored) so the board band includes revision, not completion error only | the band width shown on the panel; whether PROVISIONAL can retire | open — next R2 |
| P2 | The thinning edge: pre-register a sub-period D-1 (2013+) with its own bar before the next R2, rather than reading the post-hoc 0.94 as a verdict | whether the nowcast keeps its stats block on the panel | open — needs Casey's go |
| P2 | UMCSENT FRED delay (Q11): switch the leading composite's sentiment member to the Michigan release itself if the delay persists | leading composite timeliness | asked 2026-10-28 |
| P3 | Claims-only ADS sensitivity is vacuous (0 rows); keep or drop at the next revision | nothing scored | recorded |
| P3 | Fit the MS-DFM walk-forward in-repo (backlog 5, full step) | a third real-time line | not started |

Q1–Q17 of the SPEC v1 ledger: all answered on 2026-10-28 (defaults; v1.2 rulings).
