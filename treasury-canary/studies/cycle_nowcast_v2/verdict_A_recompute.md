# verify_A — independent recomputation of cycle-nowcast-v2 results.json (HEAD 168aafe1)

## VERDICT: PASS_WITH_NOTES

All three decision verdicts (D1 PASS, D2 PASS, D3 SUCCESS) and every decision number reproduce
to full double precision from my own implementation of the SPEC v1/v1.1/v1.2 text. No BLOCKING,
no SERIOUS finding. Notes below are labelling/auditability items that change no number.

Scratch code (no engine functions called): `lagsim_lib.py`, `d1_recompute.py`, `d2_windows_honesty.py`,
`d3_recompute.py`, `replay_rows.py` in this directory; outputs `*.out`. Raw ALFRED vintages extracted
to `raw/` from the committed `data/vintages_raw.tar.xz`. Nothing committed was edited; no armed run.

Measurement basis of every number below: population RMSE of (estimate − realized COIN(M)) on
final-vintage F5 (fred_2026-10-28) for D-1/D-2 and the honesty rows; for D-3, calibrated readings
vs target_latest = F5 COIN(M), ex-2020 = targets 2020-01..2020-12 dropped and the series concatenated.

## Table

| item | recorded (results.json) | my recomputation | match | note |
|---|---|---|---|---|
| D-1 window / n / n_ex2020 | 1972-01..2026-07 / 655 / 643 | same | exact | last complete COIN month on F5 = 2026-07 (CMRMTSPL ends 2026-07) |
| D-1 RMSE ENS_HH IS-A full / 1990+ / ex-2020 | 0.32742915932787736 / 0.3569729149130916 / 0.2254194780763595 | identical to 1e-16 | exact | from raw F5 CSVs, own bridge+CLAIMS_HH |
| D-1 RMSE PERS (realized COIN(M−1)) full / ex-2020 | 0.4668985572609485 / 0.25754620217593505 | identical | exact | |
| D-1 % vs PERS full (bar −25) | −29.871456179103596 | −29.871456179103596 | exact | PASS |
| D-1 % vs PERS ex-2020 (bar −8) | −12.47415952095039 | −12.47415952095039 | exact | PASS |
| D-1 DM ex-2020 NW-6 (bar −1.645) | −4.687028409905656 (n 643) | −4.687028409905656 (n 643) | exact | d = e_ENS² − e_PERS², Bartlett 1−j/7, no small-sample corr. |
| D-1 DM full (descriptive) | −1.5704576204677108 | −1.5704576204677108 | exact | |
| D-1 claims fallback months / n_fit last target | 93 / 585 | 93 / 585 | exact | |
| D-1 LOYO ex-2020 min/max | 0.8698 (1974) / 0.8831 (2009) | same by_year dict | exact | all 54 years < 0.92 |
| D-2 months / n / n_ex2020 | 1977-07..2026-07 / 589 / 577 | same | exact | every complete month bridges exactly CMRMTSPL at L1 |
| D-2 RMSE completed vs partial, full | 0.13310048562245 vs 0.16788068198156608 | identical | exact | PASS |
| D-2 RMSE completed vs partial, ex-2020 | 0.09922268224990864 vs 0.14150705879774494 | identical | exact | PASS |
| D-2 bias / p10 / p50 / p90 (completed, full) | 0.0026 / −0.1306 / 0.0007 / 0.1243 | identical | exact | partial: 0.0401 / −0.1266 / 0.0298 / 0.2145 identical |
| D-2 LOYO ratio ex-2020 min/max | 0.6846 (1987) / 0.7247 (2009) | same | exact | |
| D-3 n_rows_at_is / n_cal / n_without / n_intersection / n_ex2020 | 159 / 134 / 25 / 132 / 120 | 159 / 134 / 25 / 132 / 120 | exact | 134 − 2 (2026-08, 2026-09 have no target_latest) = 132; −12 = 120 |
| D-3 first calibrated month | 2015-07 (cal_n 24, rows through 2015-05) | 2015-07; 24 stored IS-A months 2013-06..2015-05 ≤ K=2015-05; previous row (M 2015-06, K 2015-04) has 23 | exact | no off-by-one: "≥ 24 rows" first satisfied at M = 2015-07 |
| D-3 RMSE ENS_cal / ADS_cal ex-2020 | 0.21836237376937492 / 0.3061281914382982 | identical | exact | from stored rows |
| D-3 r ex-2020 (SUCCESS ≤ 1.10) | 0.7133037069974885 | 0.7133037069974885 | exact | SUCCESS |
| D-3 DM one-sided (kill needs ≥ 1.282 and r > 1.25) | −1.7476603797821568 (n 120, mean_d −0.04603) | identical | exact | no kill |
| D-3 r with-2020 (never decides) / raw ENS RMSE ex-2020 | 0.3900078548403031 / 0.22400965400492664 | identical | exact | |
| D-3 LOYO r min/max | 0.6498 (2022) / 0.9023 (2021) | identical | exact | all ≤ 1.10 |
| D-3 r_first / DM_first / class | 0.7035965331710478 / −2.7158 / SUCCESS | identical / SUCCESS | exact | same class → not DEFERRED (v1.2 Q17) |
| D-3 ads_cal/ens_cal = coef·reading (all 134 rows) | — | max abs residual 0.0 / 0.0 | exact | |
| D-3 walk-forward (all 134 cal rows) | — | cal_rows_through ≤ K < M for every row; min M−K = 2; cal_n non-decreasing | ok | |
| Regime-(i) replay from raw vintages, 5 IS-A rows (2013-07-05, 2015-08-07, 2020-04-03, 2023-01-06, 2026-10-02) | bridge_hh, claims_hh, ens_hh, completed_prev, claims_fit n/rows, n_stored_used, vintages used | identical to full precision, vintage choice identical | exact | own vintage selection (latest listed ≤ d), own z/bridge/CLAIMS, store overlay from results.regime_i.stores with issue_date < d |
| §5 calibration coefficients, same 5 rows (4 with calibration) | ads_cal_coef, ens_cal_coef, cal_n, through | identical to full precision | exact | rebuilt vintage-consistent COIN(t) from the raw vintages; proves the coefficients use only t ≤ K and the vintage at d |
| ADS_avg(M \| d) and ADS vintage, 5 rows | e.g. 2020-03: −17.870849390885216 @ 2020-04-03 | identical | exact | from data/ads_panel/ads_vintage_panel.csv, latest vintage ≤ d |
| target_first(M), 4 rows with v*(M) | e.g. 2020-03: −1.6778546831082328, v* 2020-05-29 | identical | exact | v*(M) from vintage_table.csv, COIN from the member vintages ≤ v* |
| windows: first_coin / last_payems / n_targets / n_ex2020 / n_1990plus | 1969-06 / 2026-09 / 655 / 643 / 439 | identical | exact | |
| windows: onsets (USREC 0→1, 1972-01+) | 7 onsets 1973-12 … 2020-03 | identical | exact | |
| F5 last obs PAYEMS/INDPRO/W875RX1/CMRMTSPL | — | 2026-09 / 2026-09 / 2026-08 / 2026-07 | ok | complete[2026-08] = False (CMRMTSPL missing) → scoring through 2026-07 is correct; 2026-08 COIN would be a partial 3-member mean |
| gates.F1_reproduction vs gate_report_F1.json | 120 rows | same 120 ids; status/computed/target/tolerance identical on every row | exact | 6 FAIL rows = G04, S01_claims, S01_ens, S04 (hard) + Q01, Q04 (soft); all 6 ∈ run_study.RULED_DESCRIPTIVE; blocking = [] |
| honesty f1_vs_f5_realized_drift rms / max_abs / flips | 0.01821940525115412 / 0.21980044956788009 @ 2026-03 / 3 flips (2023-01, 2023-09, 2023-11 S→E), n 653 | identical | exact | own F1 fixture loader (sha256 6a342c0a… matches) |
| honesty august_forms_on_f5 ENS_BC / PERS (full/1990/ex) | 0.33373 / 0.36862 / 0.21967 ; 0.46690 / 0.53078 / 0.25755 | identical | exact | reproduction mode, original CLAIMS form, own code |
| honesty ens_hh_IS_A_on_F1 pct_full / pct_ex / DM / n | −29.88483048710977 / −12.537783864679996 / −4.724918239298354 / 653 | identical | exact | window 1972-01..2026-05 (F1 last complete) |
| honesty realized_last_months 2026-04..07 | −0.268012 / −0.196552 / −0.207119 / −0.211309 | identical | exact | |
| F6 raw vintages vs vintage_table.csv | runner: 19 hashes checked, 0 mismatches | 1572/1572 CSV sha256 match; 0 missing; 19 extra files (10 AWHMAN calendar-check + T10Y3M/BAA10YM 2026 unrevised-check vintages) | ok | |
| lag-sim diagnostic RMSE_A ≥ RMSE_B ≥ RMSE_C | holds (0.3274 ≥ 0.2892 ≥ 0.2422; ex-2020 0.2254 ≥ 0.2013 ≥ 0.1458) | not independently recomputed for B/C | n/a | A recomputed; B/C read only |

## Spec-conformance checks (definitions, not numbers)

- F08 DM: d_t = e_cand² − e_base², NW lag 6, Bartlett 1 − j/7, no small-sample correction, negative = candidate better; D-1 primary two-sided |t| ≥ 1.645 with t < 0 (implemented as t ≤ −1.645, equivalent); D-3 kill one-sided t ≥ 1.282. Conforms.
- PERS in D-1 = realized COIN(M−1) (F08). The available-members and HH forms sit in `baselines_descriptive` (DESCRIPTIVE) and enter no criterion. Conforms.
- Ex-2020 = drop targets 2020-01..2020-12, concatenate (gap closed) for RMSE, DM, percentiles and LOYO alike. Conforms.
- Windows (v1 §1 F17): scored window 1972-01..last month with all four members published in F5 = 2026-07; n 655 recorded; every bar applied to that window. Conforms.
- Row admission at IS-A (D1/D2/D6): bridge rows t ≤ M−L; CLAIMS_HH rows t ≤ K = M−2, complete targets only; regressor = stored walk-forward completions COIN_HH(t−1 | {CMRMTSPL:1}) with fits through (t−1)−1. My implementation of these rules reproduces every number, so the engine implements the spec's admission, not a looser one.
- D-2 decision scope. SPEC v1.1 ruled the "literal **D2** scoring-mode delta row" (gate rows S01/S04 on F1; "D2" there is the §2.3 ROW-ADMISSION definition D2, not Decision D-2) DESCRIPTIVE. That ruling touches only `gates.F1_reproduction` rows S01_claims / S01_ens / S04. Decision **D-2** (§8: completed 1-bridged RMSE < partial 3-member RMSE on the same 1977-07+ months, full AND ex-2020) is untouched and remains DECISION; its p10/p50/p90/bias/LOYO rows are DESCRIPTIVE as the spec says. Recorded tags match that split (decision_D2.outcome, .rmse, .consequence = DECISION; distributions and LOYO = DESCRIPTIVE). "PASS" is a legitimate output: 0.1331 < 0.1679 and 0.0992 < 0.1415.
- D-3 calibration store (v1.2 Q16 ruling): symmetric regime-(i) stored readings, identical rows both sides, ≥ 24 rows; the ADS side is NOT seeded from the 2008-12+ archive. Recorded `calibration_store` = regime_i_stored_readings_symmetric_rows; first calibrated month 2015-07; warm-up 25 rows; n_ex2020 120 vs the spec's expectation 145 — recorded in decision_D3.calibration_warmup and honesty.d3_calibration_warmup as the ruling requires. Conforms.
- D-3 target_first agreement (v1.2 Q17): outcome-class reading; both classes SUCCESS → decided, not deferred. Conforms.
- D-3 months = intersection of months where both sides have a calibrated reading AND target_latest exists (132); ex-2020 decisive (120); with-2020 reported only. Conforms.
- X = 10, Y = 25 read from freeze.json (FROZEN 2026-10-28, defaults). Conforms.

## Findings

### BLOCKING
None.

### SERIOUS
None.

### MINOR
None (no descriptive number I recomputed was off).

### NOTE
1. **Auditability of the §5 calibration from results.json alone.** The calibration targets (`_coin_in_hand`, vintage-consistent COIN(t) at each issue date) are stripped from results.json (scoring.py `strip_private`), so the per-row `ads_cal_coef` / `ens_cal_coef` cannot be re-derived from results.json by itself. They CAN be re-derived from the committed F6 tarball (`data/vintages_raw.tar.xz`, 1572/1572 hashes match `vintage_table.csv`); I did so for 4 calibrated rows (2015-08-07, 2020-04-03, 2023-01-06, 2026-10-02) and they match exactly, and the stored `cal_rows_through` ≤ K < M on all 134 calibrated rows. Not a gap in verifiability, but a second verifier needs the tarball, not just results.json.
2. **results.spec.version label is stale**: "SPEC v1 (2026-10-20) + v1.1 amendments" (results.json → spec.version), while the run applies the v1.2 rulings (Q16/Q17 via freeze.json) and `spec.sha256` 6da4a8e7… is the hash of the full file including v1.2 (verified). Label only.
3. **sd denominator**: engine uses population sd + 1e-9 (deployed-module convention, documented in engine.py header) where the spec says population sd. Recomputing with eps = 0 moves pct_full by 1.7e-7 pp and DM by 4e-8. No effect on any verdict.
4. **ADS_avg incomplete-month rows**: ~8 IS-A rows in the D-3 intersection have `ads_avg_n_days` 26–29 (ADS vintage not covering every day of M). The spec defines ADS_avg(M|d) as the mean of the daily values present in the vintage, so this is per spec; descriptive flag only.
5. **Regime-(i) real-time ENS_HH vs final-vintage persistence ex-2020 is WORSE**: pct_vs_pers_latest ex-2020 = +20.7% (IS-A), +20.6% (IS-B), +10.7% (IS-C); full-sample −31.6% / −37.4% / −41.9%. DESCRIPTIVE, pre-announced in §8 D-3 ("the real-time regime cannot establish v2's edge over persistence ex-2020"), and the baseline is a hindsight quantity (F5 COIN(M−1), so labelled). It should be stated beside D-1 in any write-up; D-1 itself is a final-vintage lag-simulation result.
6. `results.git.head` = 60fb3006 (parent of 168aafe1, the commit that added results.json) with `clean: true` — consistent with a run on the committed freeze state. An untracked `studies/cycle_nowcast_v2/figs/` directory now exists in the working tree (post-run charts); not part of the scored run.
7. 19 CSVs in the F6 tarball are not rows of `vintage_table.csv` (10 AWHMAN 2026 calendar-check vintages, the 2026 T10Y3M/BAA10YM unrevised-check vintages); they are listed in `calendar_check_vintages.csv` / `unrevised_check.json` and feed no scored number.

## Not verified here (scope)
Regime (ii), Chauvet–Piger, availability tables, bands for patterns other than {CMRMTSPL:1}, the ADS reproduction gate, IS-B/IS-C lag-simulation aggregates, and the remaining 154 IS-A regime-(i) rows (5 replayed from raw vintages; all 132 intersection rows used for the D-3 aggregates as stored).
