# Cycle nowcast v2 — a reading every day, a completed coincident, and the Chauvet–Piger cross-check

Casey, 2026-10-20: "pre-register 1+2 and 5 as the next study" (ROBUSTNESS
BACKLOG in `CYCLE_NOWCAST.md`). Status: **SPEC v0 pre-registered 2026-10-20 —
nothing scored.** Process: research pass (done, counter-verified) → SPEC v0
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

## SPEC v0 — pre-registered 2026-10-20, before any v2 number is computed

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
