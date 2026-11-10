# notes_freeze.md — run-day FREEZE for studies/cycle-nowcast-v2.md (SPEC v1 + v1.1 + v1.2), 2026-10-28

Prepared from the notes_B3 §6 checklist. **Nothing was scored**: `CNV2_SCORED_RUN` was never set, `--real` was never
passed, `scoring.armed()` read False before and after every step. Casey's answers (2026-10-28): all defaults; the
August harness is `not_retrievable`. Every command below ran from this directory; `$S` is the session scratchpad
the SESSION SCRATCHPAD directory (absolute path given in the hand-back and in notes_B2 §0's sense, not recorded here — NOTE-5 keeps absolute session paths out of committed files), `$CACHE = $S/cnv2/vintages_raw`
(the raw ALFRED cache named in notes_B2 §0 and `build_summary.json.cache`). Raw logs: `$S/freeze_1028/logs/01..13_*.log`.

## 0. Results first

| item | result |
|---|---|
| F8 lists | 10 lists re-fetched by the harness; content changed for **ICSA** (+2026-10-22) and **T10Y3M** (+2026-10-20..27); all others identical hashes |
| New panel vintages since 2026-10-20 | **one**: ICSA 2026-10-22 (last obs 2026-10-17, 56,211 B, sha256 `26844f8a…`). PAYEMS / INDPRO / W875RX1 / CMRMTSPL / RECPROUSM156N: none |
| Piger | no new release (file byte-identical, sha256 `297de742…`; last release 2026-09-30, latest month 2026-08 at 0.62%); records re-derived, identical except `built` |
| §4.1 unrevised vintages in cache | T10Y3M **2026-10-27** (fetched, 186,394 B), BAA10YM **2026-10-01** (latest listed 2026 date, already cached) — both 0 changed values vs F5 |
| F6 rebuilt | tarball 1,591 bodies, sha256 `4388498d…`; `vintage_table.csv` 1,572 rows; issue tables byte-identical to 2026-10-20; round-trip test PASS |
| F5 | `data/fred_2026-10-28/` 13 series + `MANIFEST.json`; CMRMTSPL and W875RX1 **did not move** (byte-identical to F3) |
| ADS matrix | `$S/cnv2/ads_panel_aux/ads_monthly_matrix.npz` sha256 `dbecce8e…` == `ads_hashes.json.matrix_sha256` → smoothed-fit sensitivity WILL run with `--ads-matrix` |
| freeze.json | FROZEN, every field at the template default, `validate_freeze(require_frozen=True) == []`, sha256 `64109389…` |
| Read-only pre-flight | `verify_hashes` 19/19 OK, output guard OK, unrevised re-check OK; only the committed-state check (exit 10) is pending the commit |
| pytest | 166 passed, 6 xfailed, **1 failed — pre-existing** (`test_engine.py::test_no_hard_gate_failures`, the four v1.1-ruled rows; same failure in the 2026-10-20 log; not a `--real` blocker) |
| Edits outside `data/` | `freeze.json` (new), `notes_freeze.md` (new), `test_pipelines.py:377` pinned count 1571 → 1572 (one constant; no harness code path changed; `dryrun_synthetic_results.json` stays current — its test passed) |

## 1. F8 re-pull (checklist §6.3)

Pre-check: the scratchpad cache is byte-identical to the committed tarball (`tar -xJf data/vintages_raw.tar.xz -C $S/freeze_1028/tar_extract && diff -rq …/vintages_raw $CACHE` → no output; 3,178 members). ALFRED's list endpoint refuses curl with the harness UA (HTTP/2 INTERNAL_ERROR, the hazard noted in vintages.py) but the harness's own httpx transport returns 200 — all pulls below used the harness.

### 1a. T10Y3M / BAA10YM lists (no range vintages: `--start 2027-01-01`)
```
python3 vintages.py pull --cache $CACHE --series T10Y3M,BAA10YM --start 2027-01-01 --out $S/freeze_1028/pull_unrev
[list] T10Y3M: 3149 listed (2014-01-27..2026-10-27), 0 wanted >= 2027-01-01, 0 cached
[list] BAA10YM: 149 listed (2014-05-16..2026-10-01), 0 wanted >= 2027-01-01, 0 cached
exit 0   (latest listed 2026 dates: T10Y3M 2026-10-27, BAA10YM 2026-10-01)
```
### 1b. one LISTED 2026 vintage each into the raw cache (v1.2 run-day rule)
```
python3 vintages.py pull --cache $CACHE --series T10Y3M,BAA10YM --start 2027-01-01 --extra T10Y3M:2026-10-27 --extra BAA10YM:2026-10-01 --out $S/freeze_1028/pull_unrev
T10Y3M  {'wanted': 1, 'cached_before': 0, 'requested': 1, 'ok': 1, 'failed': 0, 'bytes': 186394}
BAA10YM {'wanted': 1, 'cached_before': 1, 'requested': 0, 'ok': 1, 'failed': 0, 'bytes': 14146}
T10Y3M_2026-10-27.meta.json: header observation_date,T10Y3M_20261027, http 200, n_rows 11692, last_obs 2026-10-27, sha256 578651f14f4c36bd…
```
### 1c. the six panel-series lists + every new listed vintage (defaults: PAYEMS,INDPRO,W875RX1,CMRMTSPL,ICSA,RECPROUSM156N from 2013-01-01 / 2012-09-04)
```
python3 vintages.py pull --cache $CACHE --out data/vintages_panel        # rewrites data/vintages_panel/pull_stats.json
[list] PAYEMS: 860 listed (1955-05-06..2026-10-02), 166 wanted, 166 cached
[list] INDPRO: 1224 listed (1927-01-26..2026-10-16), 176 wanted, 176 cached
[list] W875RX1: 196 listed (2010-05-28..2026-09-30), 164 wanted, 164 cached
[list] CMRMTSPL: 158 listed (2013-06-14..2026-09-30), 158 wanted, 158 cached
[list] ICSA: 903 listed (2009-05-28..2026-10-22), 715 wanted, 714 cached       <- the one new vintage
[list] RECPROUSM156N: 167 listed (2012-09-04..2026-10-01), 167 wanted, 167 cached
[pull] 1546/1546 done, 1 requests, 2s, failures 0        exit 0
ICSA_2026-10-22.meta.json: header observation_date,ICSA_20261022, http 200, n_rows 3120, last_obs 2026-10-17, sha256 26844f8a48410a5c…
```
### 1d. BEA PI list
```
python3 vintages.py pi-list
{"file": "vd_PI.txt", "first": "1966-01-18", "last": "2026-09-30", "n": 731, "retrieved": "2026-10-28T15:46:19Z", "sha256": "a5c04caf…"}   (unchanged content)   exit 0
```
`data/vintage_lists/SHA256SUMS` after the re-pull (changed rows marked):
```
4792bb7b…  vd_AWHMAN.txt            (not re-fetched; calendar check only)
21022d42…  vd_BAA10YM.txt
fea297b6…  vd_CMRMTSPL.txt
1c2da904…  vd_ICSA.txt              CHANGED (was 5d30a547…; +2026-10-22)
30f4b11e…  vd_INDPRO.txt
717cbf72…  vd_PAYEMS.txt
a5c04caf…  vd_PI.txt
e2151de5…  vd_RECPROUSM156N.txt
2a3dc36a…  vd_T10Y3M.txt            CHANGED (was f12f68ba…; +2026-10-20,21,22,23,26,27)
bb9044ea…  vd_W875RX1.txt
```
### 1e. Piger history file and derived records
```
curl -sS -o $S/freeze_1028/piger_dl/History_of_Real_Time_Recession_Probabilities.xlsx https://jeremypiger.com/assets/files/History_of_Real_Time_Recession_Probabilities.xlsx
HTTP 200 850125B 0.53s at 2026-10-28T15:45:31Z
sha256 297de74203772a44374dc66247b1bb9d11f4b9de52f066ca0bceca786a11cb64  (downloaded)  == committed data/piger/… (byte-identical; copied over anyway)
python3 piger.py --cache $CACHE          # default --xlsx / --out data/piger
exit 3 = all_known_events_pass False: only '2008_peak_dated_2008-02_as_task_text' fails, the check SPEC v1.1 RULED (run_study.PIGER_RULED_CHECKS); the other six pass
realtime_events.json: n_releases 240, first 2006-08-01, last 2026-09-30, last_latest_month 2026-08 (0.62%), source_sha256 297de742…, realtime_path_sha256 6d4b2e2d…;
  fields differing from the committed file: ['built'] only.  realtime_path.csv byte-identical to committed.
```

## 2. F6 rebuild (tarball, tables, build_summary) and round-trip test
```
cd $S/cnv2 && tar --sort=name --owner=0 --group=0 --numeric-owner --mtime='2026-10-28 00:00:00Z' --format=gnu -cf - vintages_raw | xz -T1 -6 > data/vintages_raw.tar.xz
394,036 bytes; sha256 4388498dc652c400ebdc01d4a433d543dc991f5360a480c20c590d823bd047b6; 1,591 .csv members (1,589 + ICSA_2026-10-22 + T10Y3M_2026-10-27)
python3 vintages.py build --cache $CACHE       exit 0
build_summary.json changes vs 2026-10-20: built; n_vintages 1571 -> 1572; n_vintages_in_range 1545 -> 1546; per_series.ICSA n 714 -> 715, last 2026-10-15 -> 2026-10-22,
  bytes 35,453,057 -> 35,509,268; raw_tarball {392944, acb7f966…} -> {394036, 4388498d…}; vintage_table_sha256 1c5a1273… -> 3d4bbb47…
  UNCHANGED: issue_dates_sha256 daa466d1…, issue_panel_wide_sha256 fef6fe44…, issue_panel_long_sha256 1b363408…, n_issue_dates 477, n_issue_rows 997,
  n_rows_nowcast 467, n_rows_completion 10, is_counts, missing [].
Round trip: tar -xJf data/vintages_raw.tar.xz -C $S/freeze_1028/tar_extract2 && diff -rq …/vintages_raw $CACHE  -> identical (1,591 csv)
python3 -m pytest -q test_pipelines.py -k tarball
  first run: FAILED at test_pipelines.py:377 `assert len(vt) == 1571` (1572 rows now) — the pinned 2026-10-20 count, every hash assertion downstream unaffected;
  the constant was updated to 1572 with a comment naming this re-pull; re-run inside the full suite below: PASS.
```

## 3. F5 pull — `data/fred_2026-10-28/` (F3 layout: `<ID>.csv`, header `observation_date,<ID>`)
```
for sid in PAYEMS INDPRO W875RX1 CMRMTSPL PERMIT ICSA AWHMAN UMCSENT T10Y3M BAA10YM GS10 TB3MS USREC   # == gates.DEPLOYED_SERIES
  curl -sS -o data/fred_2026-10-28/$sid.csv "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$sid"        # keyless; all HTTP 200, 2026-10-28T15:46:23Z..26Z
```
| series | sha256[:16] | bytes | last obs | last value | vs fred_2026-10-20 |
|---|---|---|---|---|---|
| PAYEMS | c8c429818ed73de6 | 18405 | 2026-09 | 159044 | identical bytes |
| INDPRO | 0fc53a503386efaf | 24460 | 2026-09 | 103.9506 | identical bytes |
| W875RX1 | fa12b2e42b79f1bd | 14961 | **2026-08** | 17046.6 | identical bytes — did not move |
| CMRMTSPL | c84bd6dc387d54f2 | 16088 | **2026-07** | 1598922.000 | identical bytes — did not move |
| PERMIT | b83f05a2d8cdcaeb | 12713 | 2026-09 | 1398 | 1 revised value of 801 |
| ICSA | f3e28edbe435d0dc | 56202 | 2026-10-17 (wk) | 194000 | +1 week, 1 revised |
| AWHMAN | 10e14acf1b3a3ab5 | 16872 | 2026-09 | 42.0 | identical bytes |
| UMCSENT | 3076277f9f21f4bd | 13438 | 2026-09 | 48.1 | +2026-09 (was 2026-08) |
| T10Y3M | 6e8101f32e569d8c | 186385 | 2026-10-27 (daily) | 0.77 | +6 days |
| BAA10YM | 19f3a0dc9825dfa5 | 14137 | 2026-09 | 1.48 | identical bytes |
| GS10 | 40323f225e613a19 | 14206 | 2026-09 | 4.99 | identical bytes |
| TB3MS | 631bc444a8c5370c | 17865 | 2026-09 | 3.94 | identical bytes |
| USREC | a42a3581fe9c260d | 26829 | 2026-09 | 0 | identical bytes |

`data/fred_2026-10-28/MANIFEST.json` carries, per series, sha256, bytes, n_rows, retrieval time (UTC), HTTP status, last observation and value, URL, and the diff vs F3. (The run reads only `*.csv`; the manifest is not hashed into results.)

## 4. ADS archive matrix (smoothed-fit sensitivity)
```
sha256sum $S/cnv2/ads_panel_aux/ads_monthly_matrix.npz -> dbecce8e7826d6f7a35c7ecfc2c7d093e930e78512e10c53d6c11169511d33cd
data/ads_panel/ads_hashes.json.matrix_sha256            -> dbecce8e7826d6f7a35c7ecfc2c7d093e930e78512e10c53d6c11169511d33cd   MATCH
```
Pass `--ads-matrix $S/cnv2/ads_panel_aux/ads_monthly_matrix.npz`. It is outside git (session scratchpad); if the run happens in another container the flag must be omitted and `comparator_sensitivities.smoothed_fit` is NOT_RUN with the reason.

## 5. freeze.json
Built from `freeze_template.json` by a script that asserted exactly these keys differ from the template: `_about`, `status` (FROZEN), `answered_by` ("Casey (defaults; harness not retrievable)"), `answered_on` (2026-10-28), `f5_pull_date` (2026-10-28), `freeze_note` (names SPEC v1 + v1.1 + v1.2, F5 and this file). Every other field is the template default: X_pct 10, Y_pct 25, regime_scope two_regimes_never_pooled, shutdown_rule drop_and_remean, fixture_policy gate_F1_score_F5_both_reported, harness_status not_retrievable, comparator_calibration_store regime_i_stored_readings_symmetric_rows, target_first_agreement same_outcome_class, board_contract add_coincident_completed, information_sets three_IS_D_dropped, piger_rule 3x80_primary_1m50_sensitivity, comparator_metric rmse_primary_onsets_secondary, pre2009_claims accept_with_caveat_no_sensitivity, umcsent flag, silent_readings accept, fred_key keyless, benchmarks chart_only, ads_readings avg_primary_last_descriptive.
```
scoring.validate_freeze(fz, require_frozen=True)  -> []        scoring.validate_freeze(fz, require_frozen=False) -> []
scoring.arm_real_run('freeze.json') without CNV2_SCORED_RUN -> RealDataGuard "CNV2_SCORED_RUN=1 is not set …" (refuses as designed); armed() False
sha256 freeze.json = 641093896892f582ccffcf666b78fe0f851ac9df81c58a8e4c9b0dbb9ccc50fb
```

## 6. Read-only pre-flight of the `--real` refusal steps (harness functions, nothing armed, nothing scored) — `$S/freeze_1028/logs/13_preflight_readonly.log`
```
run_study.load_freeze('freeze.json','real')                 -> OK (status FROZEN)                                   [exit 7 cleared]
run_study.expected_hashes_real(DATA, ads_matrix)            -> 19 files;  verify_hashes -> checked 19, mismatches 0, missing 0   [exit 4 cleared]
run_study.real_output_guard(results.json)                   -> OK (no results*.json / corrections.log here)          [exit 3 cleared]
F1 = backend/tests/fixtures_cycle_fred.json present; F5 csv set == SERIES13                                          [exit 9 / 8 cleared]
run_study.unrevised_recheck('real', paths_real(...))        -> T10Y3M vintage 2026-10-27 (raw cache, listed): 11,207 common, 0 changed, unrevised True
                                                               BAA10YM vintage 2026-10-01 (raw cache, listed):    882 common, 0 changed, unrevised True   [exit 8 cleared]
run_study.git_state(committed_state_paths(freeze.json))     -> HEAD 5b6bb88b, clean False, 25 dirty paths          [exit 10: PENDING THE COMMIT]
```
Not pre-run here (they run inside `--real` and need no new inputs): the F1 reproduction gate (its HARD misses G04 / S01_claims / S01_ens / S04 are in `RULED_DESCRIPTIVE`, so `blocking == []`; byte-identical to `gate_report_F1.json` on 2026-10-20), the ADS note-literal gate, the Piger known-event checks (the 2008-02 row is in `PIGER_RULED_CHECKS`; the six others pass per §1e).

## 7. Test suite
```
python3 -m pytest -q      -> 1 failed, 166 passed, 6 xfailed in 86.29s
FAILED test_engine.py::test_no_hard_gate_failures — "HARD gate misses raised to Casey, not widened: G04 …; S01_claims …; S01_ens …; S04 …"
```
Pre-existing and by design (the test "stays red until Casey rules on every id in hard_fail_ids"; the same four ids failed in the 2026-10-20 run, `$S/cnv2_pytest_all.txt`). SPEC v1.1 ruled those rows DESCRIPTIVE and `run_study.RULED_DESCRIPTIVE` carries the ruling, so `--real` does not refuse on them; the test itself was not amended by this pass (a code-file edit outside the freeze's scope — flagged for the orchestrator). No harness code path changed, so `dryrun_synthetic_results.json` was NOT regenerated (`test_committed_dry_run_is_current` passed).

## 8. What the orchestrator must do
1. Commit (the guard refuses exit 10 on any uncommitted path among the spec, every `*.py` here, `data/`, `freeze.json`):
   `treasury-canary/studies/cycle_nowcast_v2/data/` (modified: `piger/realtime_events.json`, `vintage_lists/{SHA256SUMS,manifest.json,vd_ICSA.txt,vd_T10Y3M.txt}`, `vintages_panel/{build_summary.json,pull_stats.json,vintage_table.csv}`, `vintages_raw.tar.xz`, `MANIFEST.md`; new: `fred_2026-10-28/` 13 CSVs + `MANIFEST.json`), `freeze.json` (new), `test_pipelines.py` (one constant), and `notes_freeze.md` (this file; not guard-checked, commit it with the rest). The spec `studies/cycle-nowcast-v2.md` is unchanged and already committed.
2. From this directory, ONCE:
```
CNV2_SCORED_RUN=1 python3 run_study.py --real --f5 data/fred_2026-10-28 --freeze freeze.json --ads-matrix $S/cnv2/ads_panel_aux/ads_monthly_matrix.npz
```
   (~3 min + the F1 gate; writes `results.json` here.) Drop `--ads-matrix` only if the scratchpad file is gone (smoothed-fit sensitivity then NOT_RUN).
3. Then §11 step 5: the results / honesty box into the spec, commit; redeploy nothing (study only).
