# notes_B1 — harness and engine for cycle nowcast v2 (2026-10-20)

Task B1 of the pre-registered study `studies/cycle-nowcast-v2.md` (SPEC v1 is the
contract). Files written, all under `studies/cycle_nowcast_v2/`:

| file | what |
|---|---|
| `engine.py` | pure numpy engine: axis, g6, expanding z, COIN, leading composite (deployed form), lag-generalized bridge, COIN_HH(P) completion, CLAIMS / CLAIMS_HH, row admission K(d), IS label, ENS, ENS_GRID (REPRO and D3 member builders), persistence forms, band plumbing, `issue(state, d)` |
| `metrics.py` | RMSE, ex-2020, 3-phase / transition / directional accuracy, DM NW-6, onset calendar advantage, false alarms, leave-one-year-out, band percentiles (expanding), per-pattern error table |
| `gates.py` | the §7.1 reproduction gate on F1 (reproduction_mode), the scoring-mode delta row, the identity gates, legacy deployed outputs, the §7.2 engine gates on F1 / F3 / F4; writes `gate_report_F1.json` |
| `gate_report_F1.json` | 120 rows: computed / target / tolerance / status, fixture hashes, diagnostics |
| `test_engine.py` | pytest, offline, ~20 s |

Nothing was scored: no v2 member (ENS_HH, CLAIMS_HH, completion-error band,
ENS_GRID_D3) is aggregated over the evaluation window on any fixture. The only
metric computations are the named gate rows (the August forms in
reproduction_mode, the scoring-mode delta row on the same August forms, the
ENS_BC_S soft row). F5 does not exist; the lag simulation is not scored.

## 1. Gate outcome (from `gate_report_F1.json`; every number is the engine's own)

PASS 94 · FAIL 6 (4 hard, 2 soft) · INFO 16 · NOT_RUN 4. Runtime 5.3 s.

| row | computed | target ± tol | status |
|---|---|---|---|
| PERS RMSE full / 1990+ / ex-2020 | 0.467416 / 0.531598 / 0.258044 | 0.4674 / 0.5316 / 0.2580 ± 0.0001 | PASS (population pinned; n−1 forms 0.46777 / 0.25825 would fail) |
| phase acc; transitions; realized crossings | 82.569; 114 / 75; 1974-01 … 2020-03 | 82.6 ± 0.1; exact; exact | PASS |
| BRIDGE RMSE full / 1990+; live 2026-07 | 0.334582 / 0.365647; −0.346864 | 0.3348 / 0.3656 ± 0.002; −0.347 ± 0.002 | PASS |
| BRIDGE full-history coefficients vs spec (3 members) | max Δ < 1e-6, n 803 / 803 / 705 | 1e-6 | PASS |
| CLAIMS RMSE; live; coefficients; n | 0.393004; −0.429033; max Δ 1e-7; 587 | 0.3930 ± 0.003; −0.429 ± 0.003; 1e-3; exact | PASS |
| ENS_BC RMSE full / 1990+ / ex-2020 | 0.334098 / 0.369196 / 0.220029 | 0.3344 / 0.3692 / 0.2202 ± 0.002 | PASS |
| ENS_BC dir / phase / transitions / DM / DM ex-2020 | 69.725 / 83.792 / 29 of 114 / −1.6335 / −5.3379 | 69.8 ± 0.5 / 83.8 ± 0.3 / exact / −1.63 ± 0.1 / −5.33 ± 0.3 | PASS |
| ENS_BC and CLAIMS onset months; false alarms | as the August table; [1981-06]; [1981-06, 1981-07] | exact | PASS |
| ENS_GRID_REPRO RMSE | 0.331865 | 0.3319 ± 0.003 | PASS |
| ENS_GRID_REPRO 50/50 chosen | **361** of 630 | 354 ± 5 | **FAIL (miss by 2 beyond tolerance)** |
| legacy deployed bridge / claims / ens | −0.347 / −0.449 / −0.398 | ± 0.005 | PASS |
| spec form live bridge / claims / ens | −0.346864 / −0.429033 / −0.387949 | −0.347 / −0.429 / −0.388 ± 0.005 | PASS |
| identity IS-C CLAIMS_HH == original (rows ≤ 2026-05, n 585) | max Δcoef 0.0 | 1e-9 | PASS |
| identity IS-C completed COIN(M−1) == realized (n 684) | max Δ 0.0 | 1e-12 | PASS |
| completed COIN(2026-06), 1-bridged (deterministic bound) | −0.322149 | −0.3221 ± 0.0015 (verify_R1) | PASS |
| scoring-mode delta, D1+D6 reading | ΔBRIDGE +0.0005, ΔCLAIMS 0.0, ΔENS −0.0012, Δdir −0.15 pp, flips {1980-11} only | ≤ 0.003 / ≤ 1 pp / expected 1980-11 | PASS |
| scoring-mode delta, literal D1+D2+D6 reading | ΔBRIDGE +0.0005, **ΔCLAIMS −0.0307, ΔENS −0.0118**, Δdir −0.31 pp, flips 1979-10 / 1980-11 / 1981-04 / 1993-03, onset 1980-02 crossing 1979-10 → 1979-12 | ≤ 0.003 | **FAIL on CLAIMS / ENS; counts logged** |
| SOFT ENS_BC_S vs PERS full / ex-2020 / DM ex-2020 / onsets | −22.09 % / −7.88 % / −3.07 / 4-2-1 | −24.2 / −7.0 ± 1 pp / −2.76 / 5-1-1 | **soft FAIL** (full, onsets), PASS (ex-2020) |
| SOFT ENS_BC_HH | — | −29.8 / −12.5 / 30.7 / 4-1-2 | NOT_RUN by rule (see §2 J) |
| F3 (2026-10-20): deployed; v2 | None (catch-up gate); value, IS-B, lags {0,0,1,2}, K 2026-07, ENS_HH −0.190 STALL | per v1 §7.2 | PASS |
| F4 2025-11-20 / 12-16 / 2026-01-09 / 02-06 | IS-A {0,1,1,2}; IS-A {0,2,2,4} dropped [CMRMTSPL]; IS-A {0,1,3,3}; IS-B {0,0,1,2} for 2025-12 — bridge half a value on all four; claims half on 2026-01-09 only | v1 §2.4 | PASS; claims half NOT_RUN on three dates (no ICSA vintage in F4) |
| engine F1: lag 3 → value with lags; lag 4 → dropped; partial-month invariance; all-published → None with reason | as expected | v1 §7.2 | PASS |

## 2. Ambiguities resolved (spec section → reading → consequence)

A. **v1 §2.2 skip rule in reproduction mode.** A bridged member whose g history
through M−L has < 120 observations is skipped and the mean re-taken. Applied
in BOTH modes (the August text only says "skipping components the realized
composite also skips"). Affects two targets, 1977-06 and 1977-07 (CMRMTSPL L2
history 118 / 119). BRIDGE RMSE 0.33458 (doc 0.3348); treating those months as
undefined instead (the statistics reviewer's harness, n = 652) gives 0.3350.
Both inside ± 0.002; the v1 rule is closer and keeps n = 654 everywhere.

B. **v1 §7.1 "CLAIMS rows t ≤ M−1 including the 2026-07 partial target" and n = 587.**
Two different fits: the walk-forward fit for the live 2026-07 nowcast uses rows
t ≤ 2026-06 (n = 586, the 2026-06 3-member partial admitted) and gives −0.4290;
the "deployable spec" coefficients (n = 587) are the full-history fit through
2026-07, i.e. INCLUDING the PAYEMS-only partial row as a target (verify_R1 F9).
Gate C03/C04 pin the latter (max Δcoef 1e-7, n = 587); C02 pins the former.
In scoring_mode both partial rows are inadmissible (D6).

C. **v1 §7.1 scoring-mode delta row — what "D2" does to the ORIGINAL CLAIMS form.**
Two readings, both computed and reported:
 (a) D1 + D6 (bridge rows t ≤ M−L; CLAIMS rows t ≤ M−1, partial targets
 excluded): the August CLAIMS regressor COIN(M−1) is treated as "published",
 which is the fiction the August form already makes. Deltas ≤ 0.0012; exactly
 one transition flips, 1980-11 (ENS +0.0006 → −0.0023 vs realized +0.2725) — the
 spec's own expectation, which the statistics reviewer derived this way.
 (b) literal D1 + D2 + D6 (CLAIMS rows t ≤ K(d) = M−2 at the IS-A pattern):
 CLAIMS RMSE 0.3930 → 0.3623 and ENS 0.3341 → 0.3223, driven by 2020 (2020-only
 CLAIMS RMSE 2.33 → 2.02: for the May-2020 target the April-2020 row, the
 highest-leverage row in the sample, is no longer in the fit); ex-2020 deltas
 are +0.0037 (CLAIMS) and +0.0021 (ENS). Four transition calls flip (1979-10,
 1980-11, 1981-04, 1993-03) and the 1980-02 onset crossing moves 1979-10 →
 1979-12 — all logged with values in row S03.
 The JSON carries (b) as the literal gate (S rows, FAIL on |ΔCLAIMS| and |ΔENS|)
 and (a) as the diagnostic (D rows, PASS). **Raised to Casey / the spec owner:**
 which reading §7.1 means. Note the scored run's CLAIMS member is CLAIMS_HH,
 whose rows are t ≤ K by construction; the delta row documents the August
 estimator, it does not decide anything.

D. **ENS_GRID_REPRO conventions (v0 §1 A11, v1 §1).** (i) The LEAD member: the
August LEADREG row (0.4511 / 0.5179) reproduces to 4 decimals only with the
leading composite built on the 1959 axis (the deployed 1960 start gives 0.4513 /
0.5181), so ENS_GRID_REPRO uses the 1959-start LEAD; the board's leading
composite keeps its 1960 start (v1 §2.1, gate G05: identical to the deployed
series at 3 dp). (ii) Before the 24-month warm-up ends the selector's forecast
is PERS (RMSE 0.33187 ≈ 0.3319 exactly; equal-weight gives 0.3313, also inside
± 0.003; excluding those months 0.3327). (iii) Dictionary 5 + 30 + 1 = 36;
cumulative past-OOS MSE from the first target; ties → first in dictionary
order (no ties occur). The 50/50 count is 361 (1959 LEAD) / 370 (1960 LEAD) vs
354 ± 5 under every warm-up (12 / 24 / 36) and both defaults; 97 of 630
selections have a runner-up within 1 % of the best MSE, so the count is
fragile to sub-tolerance differences in the AR2 / LEADREG members that the
August doc does not pin. **Reported as a FAIL, not widened; raised.**

E. **v0 §2.3 "persistence before 1977-09" for CLAIMS_HH.** The fallback when the
fit has < 24 rows or the forecast features are undefined is the regressor in
hand: realized COIN(M−1) in the original form, COIN_HH(M−1 | IS) in the HH form,
the available 3-member mean in the S form. 92 fallback targets 1972-01..1977-08
on F1 in every form.

F. **`issue()` without claims inputs.** If ICSA (or the curve) is absent from the
state, CLAIMS_HH is None with `claims_reason` rather than silently falling back
to persistence; BRIDGE_HH is still issued. This is how the three F4 dates
without an ICSA vintage are gated "bridge half only, and say so".

G. **Bands (v1 §2.2, §2.4) are plumbing only in this stage.** `issue()` takes a
`bands` dict keyed by the displayed month's bridged pattern + dropped set
(`pattern_key`), draws [completed + p10, completed + p90] and names the basis;
with no dict the band is None with basis "pending". The error distributions
come from the scored lag simulation — computing them on F1 now would be the D-2
quantity. The "wide band" for the dropped-member F4 case is asserted
structurally in `test_band_machinery_synthetic`.

H. **F4 inputs.** Member series from the ALFRED vintages (header validated per
v1 §4.4). The curve before 1982 needs GS10 − TB3MS, which F4 does not carry:
taken from the 2026-10-20 pull (H.15 rates are not revised; same basis as
v1 §4.1 for T10Y3M / BAA10YM). Only 2026-01-09 has an ICSA vintage, so only
that date gets the claims half (CLAIMS_HH −0.302, ENS_HH −0.378, IS-A fit n
pinned at K = 2025-09).

I. **Raw data start.** FRED / ALFRED CSVs go back to 1919–1939; the deployed
fetch uses start = 1959-01-01, so every loader drops observations before
1959-01 BEFORE g6 and the z warm-up (otherwise the PAYEMS z history would begin
1939-07 and F3 / F4 numbers would not be comparable to F1). The deployed
`compute()` on F3 was fed the same truncated pairs.

J. **v0 §7.1 SOFT row.** ENS_BC_S (the deployed estimator's own QA number) is
computed with the reading R1 §1.6 gives: August training (realized COIN(t−1)),
serve-time regressor = the available 3-member mean of M−1. It misses the full-
sample figure (−22.1 vs −24.2 %) and the onset split (4-2-1 vs 5-1-1) and meets
the ex-2020 figure (−7.9 vs −7.0 %). A16 says the QA harness's exact S
construction is unknown — reported, raised, not widened. ENS_BC_HH is NOT
computed: it is the D-1 primary quantity on this very window; it belongs to
the scored run, where Q4's default reports both F1 and F5 numbers.

K. **D4 stored completions.** `coin_hh_history(ds, pattern, mode)` computes
COIN_HH(m | pattern) once per (m, pattern) with fits through m−L only, so the
CLAIMS_HH training regressor is never recomputed with a later fit. `issue()`
uses this as the "spliced history" (v1 §4.1) unless a per-issue-date store is
passed via `stored_completions={IS: {month: value}}` (regime (i) hook).

L. **Non-canonical lag states (v1 §2.3).** The CLAIMS_HH fit is the labelled
IS's (its canonical M−1 completion history as regressor); the forecast row's
regressor is the completion of M−1 at the lags actually in hand (L_c − 1,
floored at 0, drop rule applied). `completed_prev.nonstandard_pattern` flags
the mismatch (true on 2025-12-16: {INDPRO 1, W875RX1 1, CMRMTSPL 3}; 2026-01-09:
{W875RX1 2, CMRMTSPL 2}).

M. **Directional accuracy n.** 654 (ENS is defined at every target under A);
the statistics reviewer's 652 excluded 1977-06/07. 69.72 % either way.

N. **ENS_GRID_D3 member forms (v1 §1 F21 / DT-22) — implemented, not run.**
PERS_HH = COIN_HH(M−1 | prev pattern); AR2_HH on [COIN_HH(M−1), COIN(M−2)]
(COIN(M−2) is realized at K = M−2); LEADREG_HH on [COIN_HH(M−1), LEAD(M−1),
ΔLEAD(M−1)]; BRIDGE_HH; CLAIMS_HH; rows t ≤ K; selector errors through M−2.
The spec names the members only as "HH/available forms"; this reading should
be confirmed before the scored run.

O. **Bug found by the identity gate.** A lag-0 member before its first z month
(CMRMTSPL before 1977-06) was classed "missing" → the all-actual completion was
undefined before 1977-06 and the IS-C identity held on 588 months only. Fixed
(existence is checked first; the member is skipped as the realized composite
skips it); the identity now holds on all 684 complete months, max Δ 0.0.

P. **Numerics.** Expanding z keeps the deployed `+1e-9` in the sd denominator;
population sd; numpy means (differ from the deployed pure-Python sums at
1e-16). g6 in 2·ln units. OLS = `numpy.linalg.lstsq` with an intercept column,
the deployed call. Percentiles: numpy "linear".

Q. **Onset window** k = 6 (v0 §1 A6: [onset−6, onset+12]); the seven realized
crossing months reproduce (k = 5..10 all do).

R. **Cache keys.** Walk-forward designs are cached by a content hash of the
design matrix; an earlier run that keyed LEADREG by name alone aliased the
1959- and 1960-start LEAD and produced a wrong ENS_GRID count (371); 361 is the
clean number.

S. **Scoring-mode targets.** The delta row scores the same 654 targets as the
reproduction (incl. the 3-member 2026-06 target) so the deltas are like for
like; the scored run's window is defined on F5 (v1 §1 Windows) and is not
touched here.

## 3. Misses raised to Casey (reported, never widened)

1. G04 ENS_GRID_REPRO 50/50 count 361 vs 354 ± 5 (RMSE reproduces to 0.00004).
2. S01_claims / S01_ens / S04 — the literal D1+D2+D6 scoring row (see §2 C);
   the D1+D6 reading passes and matches the spec's own 1980-11 expectation.
3. Q01 / Q04 — ENS_BC_S soft row (−22.1 % vs −24.2 %; onsets 4-2-1 vs 5-1-1).
4. Q05 — ENS_BC_HH soft row deliberately NOT_RUN (pre-registration rule).
In `test_engine.py` these rows are `xfail(strict)`: the tolerance is unchanged
and an unexpected later pass fails the suite so the row gets re-reviewed.

## 4. Look-ahead tests (what they prove)

- `test_lookahead_shift_changes_nothing_issued_before`: for each of PAYEMS,
  INDPRO, W875RX1, CMRMTSPL, ICSA, T10Y3M, every observation from 2010-01 on is
  perturbed; for IS-A / B / C in scoring_mode with the HH claims form, every
  issued array (BRIDGE_HH, CLAIMS_HH, ENS_HH, completed COIN(M−1), HH and
  available persistence) is bit-identical for targets M < 2010-01 + L_s(IS),
  and differs afterwards (the test has teeth). This covers D1 (bridge rows),
  D2 (training targets through K), D4 (stored completions use fits through
  m−L) and DT-11 (series-form z) at once.
- `test_synthetic_ar_bridge_reproduces_its_own_coefficients`: an exact AR
  structure g_c(t) = a + b·g_c(t−L) + c·g_P(t) for L = 1, 2, 3 is recovered to
  1e-8 and the projection equals the truth; rows end at M−L (scoring) / M−1
  (reproduction).
- `test_row_admission_rejects_unpublished_targets`: K = 2026-05 on F1 (2026-06
  partial rejected); CMRMTSPL at lag 3 → K = 2026-04 and 2026-05 rejected; the
  CLAIMS_HH fit used by `issue()` ends at K.

## 5. Known gaps for the next stages

- Bands need the scored lag simulation's error distributions (G above).
- F4 lacks ICSA vintages on three of four dates (v1 §2.4 says they are to be
  added); the claims half is NOT_RUN there, not failed.
- ENS_GRID_D3 member forms are a reading (N above).
- `issue()` recomputes the spliced completion history on every call (~0.3 s);
  a per-issue-date store is accepted but not yet produced (regime (i) pull).
- The deployed module is imported read-only for the legacy / F3-None rows; if
  the backend cannot be imported those rows report NOT_RUN and the engine's
  own emulation `legacy_form_would_issue` carries the expectation.
- No deployment wiring (backend/app, backend/tests untouched).

## 6. Performance

Gate report 5.3 s; full pytest ≈ 20 s (the report is built once per session
and rebuilt once more for the determinism check).

## 7. Post-review fixes (2026-10-20, counter-agent passes on B1) — supersedes §1's F4 row and §5's ICSA bullet

Applied (ids from the review ledger); NO gated F1 / F3 number moved — every
`computed` value of `gate_report_F1.json` outside the F4 rows is byte-identical
before and after, and the report is identical across two runs:

- **D1 / B1-V-01 (SERIOUS)** `claims_design` content tag now hashes the valid
  mask and `require_complete` as well as the regressor history; `claims_fit` /
  `claims_value` lost the dead `tag` parameter (the design's own tag keys the
  cache). Test: same history, two designs, T = 2026-06 → n 586 (partial 2026-06
  admitted) vs 585 (complete only), in either call order; a scoring simulate
  after a reproduction fit on the same Dataset uses the complete-only design.
- **B1-V-02 (SERIOUS)** a COIN member absent from the vintage, empty, or without
  a z history is no longer classed `not_existing` and dropped from the mean:
  `issue()` returns None with a reason and `flags.members_absent`. `read_alfred_csv`
  refuses an empty body, a header-only and an all-'.' file (v1 §4.4 '≥ 1 data
  row'; B1-V-06 / N5).
- **B1-V-03 (SERIOUS)** `test_no_hard_gate_failures` asserts
  `summary.hard_fail_ids == []` and is RED until Casey rules on G04, S01_claims,
  S01_ens, S04 (the per-row `xfail(strict)` markers stay for information). The
  suite therefore exits non-zero by design: 150 passed, 6 xfailed, 1 failed.
- **B1-V-04 (MINOR)** `nowcast.reason` names the claims half when that is why
  the nowcast is None (`claims half unavailable: …`). F4 row `_f` gates the bridge
  half (value, no bridge-side reason), row `_g` the claims half (value, fit rows
  end at K(d), reason None).
- **D3 (MINOR)** F4 gained the ICSA vintages at the latest LISTED date ≤ each
  issue date (2025-11-20; 2025-12-16 → 2025-12-11; 2026-02-06 → 2026-02-05),
  byte-identical to the hashed F6 cache; T10Y3M on those dates is current per
  v1 §4.1 (2026-10-20 pull, days ≤ d). Pre-written expectation: claims half a
  value on all four. Result, all PASS: CLAIMS_HH / ENS_HH −0.2337 / −0.2565
  (2025-11-20, fit n 575 through 2025-07), −0.2718 / −0.3795 (2025-12-16, n 575
  through 2025-07), −0.3017 / −0.3778 (2026-01-09, unchanged, n 577 through
  2025-09), −0.2820 / −0.3542 (2026-02-06, n 578 through 2025-10). Report now
  PASS 97 · FAIL 6 (4 hard, 2 soft) · INFO 16 · NOT_RUN 1 (Q05).
- **D2 / B1-V-10 (MINOR)** `false_alarms` resolves the ±3-month window by
  calendar month, not list position (gap-list test added); F1 rows unchanged.
- **D4 (MINOR)** `pattern_key` carries the skipped set
  (`bridged[…]|dropped[…]|skipped[…]`); 1977-06/07 are keyed
  `bridged[]|dropped[]|skipped[CMRMTSPL]` and stay out of the PRIMARY band table.
- **N1** `scored_window_end(ds)` (last complete COIN; 2026-05 on F1) for the
  scored-run script; `eval_targets` keeps the F1 gate default. **N2**
  `flags.members_ahead`. **B1-V-09** `flags.w875_ahead_of_indpro`. **B1-V-07**
  the dead LEADREG cache-clear line removed (content hashes separate the designs).
- **B1-V-08** the `delta_ex2020` / `delta_1990` / `rmse_2020_only` entries in the
  S01 / D01 row details are August-form diagnostics (reproduction vs scoring
  rows on the IS-A BRIDGE / CLAIMS / ENS of the August estimator) beyond what
  v1 §7.1 asks; kept knowingly, they are not v2-member numbers and nothing is
  scored.

Not changed, for Casey / the spec owner (recorded, not widened): N3 (G04 361 vs
354 ± 5 is not an arithmetic error), N4 (§7.1 reading of the scoring-mode delta
row: D1+D6 vs literal D1+D2+D6), B1-V-05 (Q05 NOT_RUN by the pre-registration
rule), B1-V-11 (member vintages at non-listed F4 dates; content matches).
