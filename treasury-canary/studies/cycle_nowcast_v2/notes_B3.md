# notes_B3 — the run script and its synthetic dry run (cycle nowcast v2, 2026-10-20)

Task B3 of `studies/cycle-nowcast-v2.md` (SPEC v1 + v1.1 is the contract). **No real number
was scored.** Files, all under `studies/cycle_nowcast_v2/`:

| file | what |
|---|---|
| `scoring.py` | the study computations as pure functions over the engine / metrics / pipeline outputs; every reported quantity is a tagged record `{tag: DECISION or DESCRIPTIVE, value, basis, n, window, spec}`; the real-data guard |
| `run_study.py` | the single-shot runner: freeze.json → hash verification (F6/F7/F8) → F1 reproduction gate (v1.1 rulings non-blocking) → sections in order → `results.json` written ONCE (`--correction "<reason>"` for a labelled correction run); `--real` guarded |
| `synthetic.py` | generators: 13-series panel 1959–2026 with a latent factor, recession spells and an exact bridge structure; ALFRED-format vintage cache + lists with revisions of known size and a synthetic shutdown; ADS archive = affine in COIN + noise + end-point revision; Piger releases that trigger the rules on known dates; NBER file; the F1 analog |
| `test_run_synthetic.py` | pytest, offline, ~50 s: run_study.py end to end on two bundles (noisy, zero-noise) in parallel subprocesses, the known expectations, tagging, refusals, determinism, the guard |
| `dryrun_synthetic_results.json` | the committed synthetic dry run (noisy bundle); `run_id` pins the code and generator state (the test fails when it is stale) |
| `freeze_template.json` | every freeze field with the SPEC default and the question it answers (Q1–Q15); the real run refuses anything but `status: FROZEN` with `answered_by` |
| `vintages.py` (addition only) | `fetch_pi_vintage_list` (BEA PI, DATES ONLY, F8) and `list_proxy_issue_dates` (regime (ii) issue points from lists); `data/vintage_lists/vd_PI.txt` (731 listed dates 1966-01-18..2026-09-30) fetched by list and hashed into `SHA256SUMS` / `manifest.json` |

The engine (`engine.py`, `metrics.py`), `gates.py`, `ads.py`, `piger.py`, `nber.py` and all
committed data are untouched. `test_engine.py` (118 passed, 6 xfailed, the deliberately red
`test_no_hard_gate_failures` from B1) and `test_pipelines.py` (32 passed) are unchanged in outcome.

## 1. Results first — the synthetic dry run (noisy bundle, `dryrun_synthetic_results.json`)

Runtime 33 s (F1 gate 5 s, regime (i) 20 s). Three decisions, resolved exactly as the
generator predicts. **`gates.F1_reproduction` inside this synthetic file is the pre-registered
v1 §7.1 / §7.2 gate (`gates.run_all`) on the committed REAL fixtures F1 / F3 / F4 — the same 120
rows as `gate_report_F1.json` (B1), no study metric (N1/D10); every number under `results` is
synthetic.** The file's `statement` says the same.

| decision | synthetic outcome | the number | why the generator predicts it |
|---|---|---|---|
| D-1 primary (IS-A ENS_HH vs PERS) | **PASS** | −78.0 % full, −75.1 % ex-2020, DM ex-2020 −16.8 (n 643); LOYO range reported | members are affine in the factor plus small noise, persistence lags the factor by a month |
| D-2 completed vs partial | **PASS** | RMSE 0.0346 vs 0.0400 full, 0.0347 vs 0.0403 ex-2020 (n 589, 1977-07+) | the bridged CMRMTSPL(L1) carries information the 3-member mean lacks once members have own noise |
| D-3 comparator (IS-A, 2013-06+ analog) | **KILL** | r = 2.76 ex-2020 (n 9), one-sided DM t 8.65; X = 10 / Y = 25 from the template | the synthetic ADS is an affine function of the final COIN with 0.002 noise and a 0.1 end-point revision: after calibration it is nearly exact while ENS_HH carries the members' noise |
| RMSE_A ≥ RMSE_B ≥ RMSE_C | holds | 0.0999 / 0.0962 / 0.0854 (full), also 1990+ and ex-2020 | more actual members, less error |

Zero-noise bundle (`--zero-noise`): D-1 **PASS** (−97 %), D-2 **FAIL** by construction (the
partial 3-member mean of three exact z-scores of one factor is itself exact: RMSE 7e-10 vs
the completion's z-baseline term 4.7e-3), D-3 **SUCCESS** (r = 0.0045). CLAIMS_HH RMSE 2e-10 at
every IS (the fit target is exactly in the design's column space), the IS-C completion of
M−1 is the identity (0.0), the bridged projections equal the actual growth to 1e-8 with
coefficients (α_c, 0, β_c) at every lag, target_first == target_latest exactly (no
revisions), F1-vs-F5 drift 0.

## 2. What the dry run proves end to end

- The runner takes exactly the real code paths: synthetic ALFRED CSVs go through
  `vintages.vintage_table / issue_dates / issue_panel / as_of`, the ADS workbook shape through
  `ads.derive_panel / load_panel / ads_avg / ads_last / select_vintage`, the Piger workbook
  through `piger.load_history` (header typo corrected and flagged) and `piger.alfred_vectors`
  on synthetic RECPROUSM156N vintages, the NBER CSV through `nber.build`, the F5 directory
  through `engine.load_fred_csv_dir`, the F1 analog through `engine.load_fixture_json`.
- Hash verification happens before any scored input is read and before the raw tarball is
  extracted (N5/D4: `verify_hashes` precedes `paths_real`); a tampered F5 file refuses (exit 4);
  an unreadable or incomplete manifest refuses (4) instead of a traceback (D2); every raw
  vintage `as_of()` reads is compared with the verified F6 vintage-table row for (series,
  vintage date) and a mismatch refuses (8) — a `--cache` directory is no longer a bypass (M4).
- The F1 reproduction gate runs inside the dry run (it IS the real gate on the real fixture,
  an existing gate path): hard fails {G04, S01_claims, S01_ens, S04} are present and
  non-blocking per v1.1; any other hard fail would refuse (exit 5).
- Row admission: at every canonical issue point K = M−2 (IS-A, IS-B) / M−1 (IS-C), and the
  CLAIMS_HH fit rows end at K(d); in the synthetic shutdown (BEA/Census delays) CMRMTSPL reads
  lag 3 on 2019-01-04 (flagged) and lag 4 on 2019-02-01 / 2019-03-01 (dropped, re-meaned, a
  value issued, `nonstandard_prev_pattern` set), the IS label and lags of all 103 nowcast
  rows equal the generator's own calendar (0 mismatches), the overtaken W875RX1(2019-01) is a
  `never_latest` month with no issue date (§4.3), the delayed W875RX1(2018-12) is a completion
  row, never a second nowcast row.
- D4 stores: one completion per IS per month stored at its own issue date (36 / 36 / 34),
  spliced into the walk-forward recomputation for earlier months (counts per row).
- target_first ≠ target_latest by the known first-print mechanism (mean |Δ| 0.10 with
  δ = 0.004–0.005 on the latest print, 0 in the zero-noise bundle) — except 2018-11, whose
  CMRMTSPL first appears two months behind the latest month of the multi-month 2019-03-29
  shutdown vintage, when every member of COIN(2018-11) is already past its revised prints:
  there the first full print IS the latest (a correct consequence of §4.3's v*(M); the test
  asserts the zero-difference months lie in 2018-10..2018-12 and nowhere else).
- The §5 calibration recovers slope 1/b and intercept −a/b (0.5049 / −0.1563 vs 0.5 / −0.15 at
  zero noise; within 5 % with noise), the identical affine step on an exact ENS_HH is the
  identity (0.9994), no calibrated reading before 24 stored months at each IS, the "< d" and
  smoothed-fit sensitivities differ from the primary (the archive revises its end-point), the
  claims-only exclusion equals it (no claims-only vintage in the synthetic archive), X/Y are
  read from the freeze (MIDDLE / SUCCESS / DEFERRED / NOT_DECIDABLE branches exercised).
- Chauvet–Piger: the 3×80 % rule declares at the 2008-09-01 release (trigger 2008-04/05/06,
  first ≥ 50 % month 2008-02 → peak 2008-01 under the rule as written, NBER peak 2007-12,
  0 days vs the synthetic announcement, 9 months after the peak), ends at 2010-01-01 with
  trough 2009-06 = NBER; 2020 is never declared; the ≥ 50 % sensitivity fires at 2020-06-01
  (Mar) and 2020-07-01 (Apr); the largest non-recession print is 44.0 % (Sep-2021 at the
  2021-12-01 release); the one glitched ALFRED vintage is flagged; our crossings are dated on
  the calendar clock (pseudo for 2001/2008, labelled).
- Availability: v2 has a reading on 100 % of days (the engine issues on every lag state,
  dropped members included), the deployed fixed-lag gate on 33 %, ADS on 100 %; days with a
  dropped member equal the lag-pattern count with CMRMTSPL:4.
- Tagging: 244 tagged records, 0 untagged numeric leaves; exactly 14 DECISION records (D-1
  outcome/conditions/consequence, D-2 outcome/rmse/consequence, D-3 outcome/r/margins/DM/
  consequence, and the IS-A ENS_HH RMSE / %-vs-PERS / DM rows); everything else DESCRIPTIVE.
- Determinism: two runs byte-identical except `generated`; identical `run_id`; two generations
  of a bundle hash identically file for file (the Piger workbook is written with fixed document
  properties and re-zipped with fixed entry timestamps — openpyxl otherwise stamps wall-clock
  time into the archive, which would make the bundle hash and `run_id` irreproducible).
- Refusals: `--real` without `CNV2_SCORED_RUN=1` (2), with the flag but no freeze (2), with the
  template (not FROZEN, 2), a freeze without Q16 / Q17 or with an unimplemented answer (2 / 7),
  `--skip-f1-gate` with `--real` (9), existing results.json (3, file untouched), ANY
  results*.json / corrections.log in the study directory whatever `--out` says (3) and `--out`
  outside it (9) in `--real` (M2), `--correction` without an original (9) or with inputs /
  freeze differing from the superseded file (9, M3), uncommitted spec / code / data / freeze
  (10, M6), `--f1` other than the gate's F1_PATH in `--real` (9, M5), no listed 2026 vintage of
  an unrevised series (8, S2), missing / unsupported freeze (7), hash mismatch or unreadable
  manifest (4); `write_once` uses `open(..., "x")`; the halt record never overwrites an
  earlier one (N2).

## 3. The guard (task rule: no real number is scored)

`scoring.StudyInputs(provenance="real", …)` raises `RealDataGuard` unless
`scoring.arm_real_run(freeze_path)` has accepted `CNV2_SCORED_RUN=1` in the environment AND a
freeze.json that validates as `status: FROZEN` with `answered_by` (the only caller is
`run_study.py --real`, which this stage never passes). `provenance="synthetic"` must carry
the bundle manifest (marker + sha256 of the F5 series the generator wrote); every section
re-verifies on entry, so a real series handed in as "synthetic", a forged manifest hash, a
raw dict, or a real-provenance input after `disarm()` all raise. The test asserts each path.
Nothing in `test_run_synthetic.py` runs with the flag set; the subprocess environment strips
it. No `results.json` exists in the study directory.

## 4. Spec points interpreted (section → reading → where)

| § | point | reading |
|---|---|---|
| v1 §1 Windows | scored window end on F5 | `engine.scored_window_end` (last complete COIN month); logged with n |
| v1 §3 | RMSE_A ≥ RMSE_B ≥ RMSE_C "halts the read-out" | the DIAGNOSTIC QUANTITY is ENS_HH (the D-1 quantity; the spec names none — D9); `run_study` writes `diagnostic_halt.json` beside the output (never overwriting an earlier halt record) and exits 6 without results.json; a numerical tie tolerance of 1e-6 (the engine's +1e-9 sd guard makes exact ties float noise) |
| v0/v1 §3, §8 D-1 | RMSE ratios vs PERS | candidate and PERS RMSEs on ONE common finite mask (N3; PERS is finite on every target by construction, so the candidate's rows decide; no number changed on the dry run) |
| v1 §2.2 | bands "for every pattern that can occur on the board" | `BOARD_PATTERNS` (canonical targets and completions, lag-3 variants, the F4 patterns, dropped variants) plus every pattern regime (i) actually met; PRIMARY window 1990-01+ ex-2020 for bridged patterns, 1977-07+ ex-2020 for dropped sets (§2.4); the other windows as sensitivities; walk-forward (expanding) coverage reported; `board_bands` = the dict `engine.issue(bands=…)` consumes (patterns with ≥ 24 errors) |
| v1 §8 D-2 | "matched 1977-07+ months" | months 1977-07..window end where the 1-bridged completion's key is `bridged[CMRMTSPL:1]` and both errors are finite; same months for both sides; full and ex-2020 |
| v1 §4.1 | spliced history | `coin_hh_history` on the vintage in hand (walk-forward) overwritten by the per-issue-date store of the labelled IS for the months it covers; the store takes the FIRST issue of each (IS, month); counts per row |
| v1 §4.1 | unrevised series in regime (i) | T10Y3M (daily) from the F5 pull with observation dates ≤ d; the MONTHLY averages BAA10YM / GS10 / TB3MS only for months strictly before the month of d (D7: a full-month mean is unknown inside its month; changes no number — the PAYEMS axis ends before the month of d; the pre-1982 curve needs GS10−TB3MS) |
| v1 §4.1 | "re-checked on the run day against one 2026 vintage" | `run_study.unrevised_recheck` (S2): in `--real` one LISTED 2026 vintage of T10Y3M and of BAA10YM — from the raw cache, else the F4 file `data/alfred_shutdown/alf_<ID>_<date>.csv` at a listed date, header-validated like a served vintage — compared with F5 and recorded; none available refuses (8). Today: T10Y3M has `alf_T10Y3M_2026-01-09.csv` (listed), BAA10YM has none → the run-day re-pull must fetch one by list. The synthetic bundle has none and records the note (synthetic mode only) |
| v1 §4.1 / §8 real-time | PERS in regime (i) | `pers_realized_latest` = F5 COIN(M−1): the FINAL-VINTAGE (hindsight) persistence baseline in the F08 form, so labelled in the per-IS basis (N7/D8); the in-hand forms travel per row; DESCRIPTIVE DM records carry t / p only, no verdict (M7) |
| v1 §4.3 | target_first(M) | state at v*(M) = max over the four members of `first_vintage_containing(M)` from issue_dates.csv, `Dataset.coin[M]` if complete; None with the reason otherwise |
| v1 §4.3 | completion rows | trigger month ≠ M → completion table; never a second nowcast row; same-day double triggers evaluate the same state |
| v1 §4.1 / §4.3 | a regime-(i) row whose member has no vintage ≤ d | skipped and listed in `regime_i.basis.rows_skipped_no_vintage`, never a bare row in the per-IS arrays (D5; unreachable on the real panel) |
| v1 §4.2 | regime (ii) issue points | **list-only proxy** (content not consulted; the pull range starts 2013): earliest listed date ≥ the 1st (PAYEMS) / 14th (INDPRO) / 20th (PI, W875RX1) of M+1 and ≤ the 1st of M+3 (M1: inclusive upper bound — W875RX1 2018-12 was released 2019-03-01); PI list fetched by list as dates only; W875RX1's own list for months whose PI&O day is on/after 2010-05-28; the honest label "list-only proxy" travels with every row. The proxy's EVIDENCE is recorded in `regime_ii.basis.list_proxy_vs_content_decided_regime_i_months`: per trigger series, the list-proxy dates vs the content-decided F6 issue dates over the regime-(i) months, every mismatch listed (synthetic dry run: 35/35, 35/35, 34/34) |
| v1 §6 | "our realized crossing of m_c = the IS-C issue date of the month on which COIN(m_c) first printed in full" | regime (ii): the IS-C point of target m_c+1 (the PI&O release that carried CMRMTSPL(m_c)); regime (i): v*(m_c). ENS_HH crossing: the IS-A point of target m_n |
| v1 §6 | NBER peak for a declaration | the USREC spell whose peak ≤ the model's first recession month (latest such); the end event matches the spell that start opened (latest onset ≤ the end trigger) |
| v1 §6 | "largest non-recession real-time print" | max latest-month probability over releases whose latest month has USREC = 0 |
| v1 §5 | calibration rows "same rows" for ENS | the intersection of months with a stored ADS reading and a stored ENS_HH at that IS, t ≤ K(d), COIN(t) complete in the vintage at d; ≥ 24. **Consequence (S1/D1): the store holds regime-(i) readings only, so the first calibrated reading comes ≥ 24 stored regime-(i) months after the first row (synthetic: first IS-A row 2016-12, first calibrated 2019-03, 27 rows without a reading; real panel: IS-A rows from 2013-06 → first calibrated ~2015, D-3 n_ex2020 ~120 vs the spec's n ≈ 145 and its "first scored month ≥ 2011 on the 2008-12+ archive"). The spec's clauses cannot all hold; the builder's symmetric reading is now RECORDED (comparator per-IS `first_calibrated_month`, `n_rows_without_calibration`, the D-3 outcome basis, `honesty.d3_calibration_warmup`) and the choice is Q16 (P1) in the freeze — `--real` refuses a freeze without it; the seeded-archive alternative is not implemented and refuses** |
| v1 §5 | smoothed-fit sensitivity | needs the F7 monthly sum/count matrix (`ads_monthly_matrix.npz`, scratchpad, not in git): `--ads-matrix`; NOT_RUN with the reason when absent; the synthetic bundle carries one |
| v1 §5 | comparator reproduction gate in the dry run | not applicable to a synthetic archive (its targets are properties of the real archive); run in `--real` only, note-literal sampling per v1.1 |
| v1 §8 D-3 | "target_first must agree in sign" | TWO readings implemented, chosen in the freeze (Q17, P1): `sign_of_r_minus_1` (sign(r_first − 1) == sign(r_latest − 1), else DEFERRED — the literal text; it defers r_latest 1.05 / r_first 0.98 although both are SUCCESS) or `same_outcome_class` (the class under r_first with the same X/Y thresholds and the one-sided DM on target_first errors equals the class under r_latest). Both classes are always recorded (`decision_D3.class_under_target_first`); the dry run shows the readings CAN differ (class_first MIDDLE vs class_latest KILL: sign reading → KILL, class reading → DEFERRED). When target_first is unavailable the basis says "n/a" (N4) |
| v1 §8 D-3 | X, Y | read from freeze.json (`X_pct`, `Y_pct`); the template carries 10 / 25 and is labelled "not Casey's answers" wherever it is used |
| v1 §3 (F15) | availability "days per month with a reading" | structural: the lag state per calendar day from (vintage date → last observation month); v2 = a PAYEMS month beyond the last complete COIN with ICSA covering it; deployed = lags exactly {1,1,2}; ADS = an archived vintage ≤ d with days in M |
| v1.1 Q05 | ENS_HH on F1 in the honesty box | computed in `section_honesty` on the F1 input (the synthetic F1 analog in the dry run), DESCRIPTIVE, beside the August soft numbers |
| v0 §7.3 Q4 | August forms on F5 | PERS and ENS_BC (reproduction_mode, original CLAIMS) re-run on F5 over the scored window, DESCRIPTIVE, beside the August targets |
| v1 §7.4 | correction runs | `results.correction-<k>.json` + `corrections.log` with the reason and the superseded file's sha256; the original is never touched. A correction run must have the SAME input hashes (F1, F5, F6/F7/F8, Piger, NBER, ADS matrix) and the same freeze.sha256 as the file it supersedes — "a correction run that changes any hash is a new run" (§7.3) — else usage (9); `spec_md` and `code` equality are recorded, not required (the results section is written into the spec file after the run; code changes ARE what a correction is) (M3/D3) |
| v1 §7.4 | "committed before any v2 number" | `--real` refuses (10) unless `git status --porcelain` over the spec, every study `.py`, `data/` and the freeze (when inside the repo) is empty; HEAD is recorded in `results.json.git` (M6) |
| v1 §7.4 | ONE scored run | per study directory, not per `--out`: any `results*.json` / `corrections.log` here refuses (3), `--out` outside here is a usage error (9), a correction supersedes `results.json` here only (M2) |
| v1 §7.3 | `--f1`, `--ads-matrix` in `--real` | `--f1` must be the gate's F1_PATH (the honesty ENS_HH-on-F1 runs on the gated file); `--ads-matrix` enters the verified set with `ads_hashes.json.matrix_sha256` (M5) |
| freeze | unsupported answers | `shutdown_rule` ≠ drop_and_remean, `fixture_policy` ≠ gate-F1-score-F5, `harness_status: retrieved` refuse the run with the change they need; `regime_scope: regime_i_only` skips regime (ii) |

## 5. results.json fields and tags

Top level (metadata, untagged by design): `study`, `spec` (file, version, sha256),
`generated` (the only non-deterministic field), `mode`, `scored_real_data`, `run_id`,
`freeze` (source, path, sha256, values), `inputs` (paths, hash_verification, hashes {F1, F5
per file, F6_F7_F8_verified, piger_history, nber_turning_points, ads_matrix, spec_md, code},
spans per series / vintages / issue rows / ADS vintages / Piger releases / lists,
synthetic_manifest), `gates` (F1_reproduction with the ruled rows and `blocking`,
ADS_comparator, piger_known_events), `section_order`, `decisions` (the three outcomes and
consequence texts, copied from the tagged records), `board_bands`, `correction`,
`statement`, `tag_audit`, `git` (HEAD and the porcelain status in `--real`; null in the dry run).
The non-deterministic fields are `generated` and, in a correction run, `correction.logged`.

`results` — every leaf a tagged record:

| section | fields | tag |
|---|---|---|
| windows | scored_window, n_targets, n_1990plus, n_ex2020, first_coin_month, last_payems_month, onsets | DESCRIPTIVE |
| lag_simulation | basis; per_is[A,B,C] × {ENS_HH, BRIDGE_HH, CLAIMS_HH} × {rmse_full_1990_ex2020, pct_vs_pers_full_1990_ex2020, dm_vs_pers_t_full_ex2020, loyo_ratio_full, loyo_ratio_ex2020, directional_pct, phase_pct, transitions_called_of_realized, transitions_pct, onsets, false_alarms, claims_fallback_months}; completed_COIN_prev {rmse_vs_realized_full_ex2020, band_p10_p50_p90_all}; baselines_descriptive; pattern_keys_seen; claims_n_last_target; diagnostic_rmse_A_ge_B_ge_C; ens_grid_d3 | **DECISION**: per_is.A.ENS_HH rmse / pct_vs_pers / dm rows; all else DESCRIPTIVE |
| regime_i | basis, per_is[A,B,C] (n, RMSE vs latest / first with and without 2020, % vs PERS, DM, directional, phase, onsets, false alarms, flag counts, lag-pattern frequency, store, ENS crossing date), scorecards (one row per nowcast: issue_date, trigger, IS, M, K, lags, dropped, members_bridged/skipped, pattern keys, flags {lag_ge3, dropped, is_c_cmrmtspl_lag2, nonstandard_prev_pattern, canonical, in_shutdown_window, w875_ahead_of_indpro}, bridge_hh, claims_hh, ens_hh, phase, reason, completed_prev/target, persistence_in_hand, claims_fit, regressor_history counts, vintages, target_first (+ vintage, complete), target_latest, pers_realized_latest, errors), completions, stores, target_first_vintages | DESCRIPTIVE |
| bands | basis, patterns[pattern key] (requested pattern, primary window, dropped flag, the four windows' p10/p50/p90/bias/rmse/n, walk-forward coverage), board_bands | DESCRIPTIVE |
| decision_D1 | outcome, conditions, consequence (**DECISION**); loyo_full, loyo_ex2020, missed_bars (DESCRIPTIVE) | mixed |
| decision_D2 | outcome, rmse, consequence (**DECISION**); distribution_completed / _partial (+ ex2020), loyo_ratio_full / _ex2020 (DESCRIPTIVE) | mixed |
| regime_ii | basis, tables[A,B,C], crossings_calendar_clock, ads_alignment_2009plus | DESCRIPTIVE |
| comparator | basis, per_is[A,B,C] (intersection n, RMSE calibrated ENS / ADS / raw ENS ex-2020 and with, r, LOYO r, one-sided DM, vs target_first, onset timing, ADS_last calibrated, coefficients), rows | DESCRIPTIVE |
| comparator_sensitivities | strict_lt_d, excl_claims_only, smoothed_fit — same shape | DESCRIPTIVE |
| decision_D3 | outcome, r_ex2020, margins, dm_one_sided_ex2020 (verdict computed from t), consequence (**DECISION**); calibration_warmup, class_under_target_first, loyo_r_ex2020, r_with2020_reported_never_decides, r_vs_target_first, raw_ens_rmse_ex2020, onset_timing_2013plus, scope_note (DESCRIPTIVE) | mixed |
| availability | basis, all_2013_06plus, shutdown_2025_10_to_2026_04, per_month, lag_pattern_frequency_days, lag_pattern_frequency_issue_rows, dropped_member_frequency_issue_rows | DESCRIPTIVE |
| chauvet_piger | basis, path, declarations_3x80, onsets_never_declared_3x80, sensitivity_1m50, largest_non_recession_print, alfred_glitch_flags, known_event_checks | DESCRIPTIVE |
| honesty | recessions_per_regime (which NBER onsets each regime contains, D11), d3_calibration_warmup (S1/D1), f1_vs_f5_realized_drift, ens_hh_IS_A_on_F1, august_forms_on_f5, regime_i_counts_per_is, unrevised_recheck, input_hashes, statements | DESCRIPTIVE |

## 6. Real-run checklist (what `--real` needs that this stage did not do) — BLOCKERS first

1. **Q16 and Q17 ruled by Casey** (§9 below; P1, decision-gating). `freeze.json` from
   `freeze_template.json` with Casey's answers to Q1–Q17, `status: FROZEN`; the harness refuses a
   freeze without `comparator_calibration_store` / `target_first_agreement`, and refuses the
   seeded-archive store (not implemented: needs an engine change and a SPEC amendment first).
2. **`ENS_GRID_D3` member forms confirmed against §2.3** (v1.1: "must be confirmed before the
   scored run") and the "pending confirmation" flag dropped from `scoring.py` — a blocker until
   done (N6); today the forms are still the notes_B1 N reading.
3. The run-day F5 pull directory (13 FRED CSVs, the F3 layout) → `--f5`; the run-day re-pull of
   the lists and the Piger file (F8, §11 step 3) → the hashes in `SHA256SUMS` /
   `realtime_events.json` must match what the run verifies (a list re-pull changes them: rebuild
   those records before running, never edit by hand); `vintages.py pi-list` refreshes `vd_PI.txt`.
   **The re-pull must also fetch one LISTED 2026 vintage of T10Y3M and of BAA10YM into the raw
   cache** (then rebuild the F6 tarball / `build_summary.json` so the hashes match) — the §4.1
   run-day re-check refuses (8) without them; today only T10Y3M has an F4 file at a listed date.
4. **Everything committed first** (v1 §7.4): the spec, every study `.py`, `data/` and the freeze;
   `--real` refuses (10) on any uncommitted path and records HEAD.
5. `CNV2_SCORED_RUN=1 python3 run_study.py --real --f5 <dir> --freeze freeze.json [--ads-matrix
   <scratchpad npz>]` — once, from a study directory holding no `results*.json` /
   `corrections.log`; `--out` must stay inside it; `--f1` is pinned to the gate's F1_PATH;
   `--ads-matrix` is hash-verified against `ads_hashes.json`. Output `results.json` here.
6. Regime (i) on the real panel: 467 nowcast + 10 completion rows ≈ 0.3 s each (the vintage in
   hand is rebuilt twice per row: once for the spliced history, once inside `engine.issue`);
   expect ~3 minutes plus the F1 gate.
7. Regenerate-and-commit rule (N8/D12): `run_id` hashes every study module, so EVERY code edit
   (an addition in `vintages.py` included) makes `dryrun_synthetic_results.json` stale and
   `test_committed_dry_run_is_current` red until `python3 run_study.py --synthetic <fresh
   bundle> --out dryrun_synthetic_results.json` is re-run and committed in the same change.

## 7. Known gaps

- Regime (ii) issue points are a list-only proxy (the pull range starts 2013 and the lists
  carry no observation months); content-decided dates for 2000–2013 would need a dates-only
  pull extension. Every regime (ii) row says so.
- The smoothed-fit sensitivity needs the scratchpad matrix (`--ads-matrix`); NOT_RUN otherwise.
- The real comparator gate and the Piger known-event gate run only in `--real` (their targets
  are properties of the real archives); the dry run records them as not applicable.
- The synthetic archive has no claims-only ADS vintages, so the claims-only exclusion equals
  the primary there; the code path runs.
- The unrevised re-check inside `run_study` needs one LISTED 2026 vintage of T10Y3M and of
  BAA10YM (cache or F4 file); the synthetic bundle has none (recorded as such, synthetic mode
  only); the real data today refuse on BAA10YM until the run-day re-pull (checklist §6.3).
- `ENS_GRID_D3` member forms are the notes_B1 N reading, flagged "pending confirmation" — a
  blocker for `--real` (checklist §6.2).
- The D-3 decisive sample is ~24 months smaller than the spec states (calibration warm-up,
  S1/D1); recorded everywhere, ruled by Q16.
- `dryrun_synthetic_results.json` is 1.1 MB (scorecards, Piger path, per-month availability).

## 8. Fix pass after the B3 reviews (2026-10-20; contract lens 16 findings, look-ahead lens 12)

Applied (every BLOCKING / SERIOUS and the clear MINOR / NOTE items; no number computed on real
data; no guard weakened; the F1 gate rows re-run byte-identical to `gate_report_F1.json`, all
120 rows, 97 PASS):

| id | fix |
|---|---|
| S1 / D1 (SERIOUS) | calibration warm-up recorded per IS (comparator `first_row_month`, `first_calibrated_month`, `n_rows_without_calibration`, `n_rows_at_is`, `spec_expected_n_ex2020`), named in the D-3 outcome basis and `honesty.d3_calibration_warmup`; **Q16 (P1)** added to the spec ledger, the freeze template and `validate_freeze` — `--real` refuses until ruled; the seeded-archive answer refuses as not implemented |
| S2 (SERIOUS) | `unrevised_recheck`: `--real` compares one LISTED 2026 vintage of T10Y3M / BAA10YM (cache, else the F4 file at a listed date, header-validated) with F5 and refuses (8) when none exists; the "synthetic bundle" note only in synthetic mode |
| M1 | list-proxy upper bound inclusive (`d <= <M+3>-01`); agreement table vs the content-decided F6 issue dates in `regime_ii.basis`; label kept on every row |
| M2 | `real_output_guard`: one scored run per study directory; `--out` outside refuses (9); any `results*.json` / `corrections.log` here refuses (3) |
| M3 / D3 | `check_correction_inputs`: identical F1 / F5 / F6-F7-F8 / Piger / NBER / ADS-matrix hashes and freeze.sha256 required (9), comparison recorded; `spec_md` recorded not required (see rejected) |
| M4 | `_state_from_asof` verifies every raw vintage's sha256 against the F6 vintage table (`InputIntegrityError` → exit 8); a missing table refuses too |
| M5 | `--ads-matrix` hashed against `ads_hashes.json.matrix_sha256`; `--f1` pinned to the gate's F1_PATH in `--real` |
| M6 | `require_committed_state`: porcelain over spec / `*.py` / `data/` / freeze must be empty (10); HEAD in `results.json.git` |
| M7 | DESCRIPTIVE DM records (regime (i) per-IS, comparator per-IS, vs target_first) carry no pass / kill booleans; the D-3 verdict is computed in `decide_d3` from t |
| N1 / D10 | the `statement` and §1 say `gates.F1_reproduction` is the B1 gate on the real fixtures, nothing v2 |
| N2 | `write_halt` never overwrites (`x`, timestamped fallback); `correction.logged` named beside `generated` |
| N3 | one common finite mask for candidate and PERS in `_metrics_vs_realized` / `decide_d1` (n_common recorded; 0 of 13,104 numeric leaves changed on the dry run) |
| N4 | "target_first check: n/a" in the D-3 basis when no target_first rows exist |
| N5 / D4 | `verify_hashes` before `paths_real` (the tarball is verified before extraction; the tarball path follows `--data`); docstring says "before any scored input is read" |
| N6 | ENS_GRID_D3 confirmation listed as a `--real` BLOCKER (checklist §6.2) — the forms themselves need the spec owner |
| N7 / D8 | per-IS basis: PERS_realized_latest = F5 COIN(M−1), final-vintage hindsight baseline |
| N8 / D12 | dry run regenerated; the regenerate-and-commit rule in §6.7 |
| D2 | manifest reads wrapped → `Refusal('hash')` |
| D5 | rows whose member has no vintage ≤ d go to `rows_skipped_no_vintage`, never into the per-IS arrays |
| D6 | both readings of the agreement test implemented and chosen in the freeze (**Q17, P1**); both classes recorded |
| D7 | monthly-mean unrevised series admitted for months strictly before the month of d (no number changes) |
| D9 | §4 names ENS_HH as the diagnostic quantity |
| D11 | `honesty.recessions_per_regime` |

Rejected with evidence:

| id | why |
|---|---|
| D3, the `spec_md` part only | §11 step 5 writes the RESULTS and honesty box into `studies/cycle-nowcast-v2.md` — the very file whose hash `spec_md` records — after the scored run; requiring an identical `spec_md` would make every post-run correction a "new run" and no correction could ever be labelled. §7.3's "any hash" names F1–F8. `spec_md` equality is RECORDED in the correction record (`spec_md_identical`), not required |
| N6, the "confirm the forms" half | the member forms are a spec-owner confirmation against §2.3 (v1.1), not a code fix this pass can make; it is a named blocker in the checklist instead |

## 9. Pending questions (living ledger; ranked; first asked 2026-10-20 by this fix pass; expiry 2026-12-19)

| Pri | # | Question | What it moves | Default carried in the template (NOT Casey's answer) | Status |
|---|---|---|---|---|---|
| P1 | Q16 | §5 calibration store: regime (i) stored readings only, symmetric rows (first calibrated reading ~2015 on the real panel, D-3 n_ex2020 ~120 vs the spec's ≈ 145) — or the ADS side seeded from the 2008-12+ archive at list-proxy IS points against vintage-consistent COIN(t), with a labelled pseudo ENS side (asymmetric rows, needs an engine change + SPEC v1.2)? | the D-3 decisive sample (~24 months) and its power; whether `--real` can run at all | `regime_i_stored_readings_symmetric_rows` | asked |
| P1 | Q17 | §8 D-3 "target_first must agree in sign": the literal sign(r − 1) reading, or "same outcome class under target_first"? The dry run shows they can differ (KILL vs DEFERRED) | whether D-3 is decided or DEFERRED at the margin | `sign_of_r_minus_1` | asked |
| P1 | Q1–Q5 | as SPEC v0 §10 (X / Y, regime scope, shutdown rule, fixture policy, August harness) | go / no-go, which numbers enter the honesty box | per `freeze_template.json` | asked |
| P2 | — | `ENS_GRID_D3` member forms (PERS_HH, AR2_HH with realized COIN(M−2), LEADREG_HH) confirmed against §2.3? (v1.1 build note) | the reported no-hindsight check; a `--real` blocker | notes_B1 N reading | asked |
