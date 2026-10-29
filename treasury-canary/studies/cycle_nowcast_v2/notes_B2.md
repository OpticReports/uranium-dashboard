# notes_B2 — data pipelines for cycle-nowcast v2 (SPEC v1 §4–§6; F6, F7, F8)

Built 2026-10-20 (19:15–19:40 UTC) in the session container, through the agent proxy. Scope: TASK B2 only
(vintages.py, ads.py, piger.py, nber.py, test_pipelines.py and the derived data under `data/`). **Nothing is
scored**: no composite, nowcast, calibration or v2 metric is computed anywhere in these files; the only
gate-type numbers are the §5 comparator reproduction gate (`data/ads_panel/gate_ads.json`), the §6 known-event
checks on Piger's release history, the §4.1 unrevised re-check and the DT-17 calendar check. The engine
(engine.py / gates.py / metrics.py, another builder) was not touched and was not run over the panel.

> Post-review (2026-10-20, counter-agent pass on B2; supersedes the two
> "stay out of git" statements below): the raw cache IS in git as
> `data/vintages_raw.tar.xz` (392,944 bytes; sha256 `acb7f966…` in
> `build_summary.json` → `raw_tarball`; 3,178 members = 1,589 CSV bodies +
> sidecars). `vintages.py build | calendar` and `as_of()` read it when no
> `--cache` is given; `test_committed_raw_cache_tarball_matches_vintage_table`
> re-hashes all 1,571 `vintage_table.csv` rows from it. Other fixes: §4.4
> validator refuses non-finite values, non-strictly-increasing dates and a body
> without a trailing newline (cut transfer) — the reviewer's "empty field = cut
> transfer" rule was NOT adopted: ALFRED serves empty fields as missing values
> (T10Y3M 2014-01-27: 348 empty rows, no '.'; 2026-01-02: 478; ICSA 2018-11-21
> and 2019-07-03: one each), so it would hard-fail real pulls. §4.1 unrevised
> check now compares the current FRED CSV with the earliest listed vintage
> (T10Y3M 2014-01-27: 8,017 dates; BAA10YM 2014-05-16: 733), the earliest 2026
> vintage (2026-01-02: 11,002 / 873) and the latest cached 2026 vintage
> (11,201 / 882): 0 changed in all six. Panels carry `row_kind` ('nowcast' when
> trigger month = M; 'completion' on the 10 W875RX1 rows for M−1 — 6 at IS-A,
> 4 at IS-B — which complete COIN(M−1), never a second nowcast target for M;
> n per IS on nowcast rows 159 / 160 / 148), `is_c_identity` (131 IS-C rows
> with L_CMRMTSPL = 1; the lag-2 flag, 16 rows, and the lag-3 row 2015-09-28 are
> not identity rows) and `members_ahead` (empty 2013–2026). `pull()` docstring
> corrected, pull statistics incremented under a lock. `DATA_MANIFEST.csv`
> `local_file` paths scrubbed to scratchpad-relative paths; the identifier test
> now covers every study file and every committed text data file. results.json
> must record the inner content hashes (vintage_table / panel / ref /
> realtime_path sha256) plus the tarball hash, not the timestamped JSONs' own
> hashes. Not changed (spec owner): NOTE-1 (§5 sampling clause), NOTE-2 (§6 peak
> wording), NOTE-3 (§6 Piger clock text); the retry-budget cap of NOTE-4 was not
> applied (tests pin the retry sequences; the tries² worst case was never hit).

Raw ALFRED vintage CSVs (57 MB, 1,574 files) stay out of git in the session scratchpad under
`cnv2/vintages_raw/<ID>/<ID>_<YYYY-MM-DD>.csv` (+ `.meta.json` sidecars); every row of
`data/vintages_panel/vintage_table.csv` carries the file's sha256 and byte count, so the cache is verifiable
and re-pullable (fetch-by-list is deterministic as long as ALFRED serves the same bytes; a changed hash is a
changed vintage). The ADS monthly sum/count matrix (`ads_monthly_matrix.npz`, 1.9 MB, sha256
dbecce8e…) also stays in the scratchpad; its hash is in `ads_hashes.json`.

## 1. Results first

| item | result | where |
|---|---|---|
| ALFRED pull (fetch-by-list) | **1,568 requests, 134 s at 8 workers (0.085 s/request effective), 0 failures, 0 validation failures, 1 transient timeout retried OK** | `data/vintages_panel/pull_stats.json` |
| F8 vintage lists | 9 series, select-option parse of `downloaddata?seid=<ID>`, hashes in `SHA256SUMS` + `manifest.json` (page sha recorded) | `data/vintage_lists/` |
| F6 vintage table | 1,571 cached listed vintages (1,545 in the 2013-01+ range + 26 INDPRO 2008-12..2010-11 fetched for the ADS gate), each with sha256/bytes/last obs month | `data/vintages_panel/vintage_table.csv` |
| F6 issue dates | 997 (series, month) rows; 15 months flagged `never_latest` (no issue date, §4.3), 5 `left_censored` | `issue_dates.csv` |
| F6 issue panel | 477 issue dates 2013-06-14..2026-10-16: **IS-A 165 / IS-B 164 / IS-C 148**; 48 non-canonical lag patterns, 25 rows with a lag ≥ 3, 4 rows with a dropped member (lag ≥ 4), 16 IS-C rows with CMRMTSPL at lag 2, 10 trigger rows whose trigger month ≠ M | `issue_panel_wide.csv`, `issue_panel_long.csv` |
| §2.4 F4 expectations | 2025-11-20 → A {0,1,1,2}; 2025-12-16 → A {0,2,2,4} dropped CMRMTSPL; 2026-01-09 → A {0,1,3,3} — all reproduced from the vintages in hand; 2026-02-06 is not an issue date (B {0,0,1,2} from the F4 files) | panel + `test_pipelines.py` |
| DT-17 calendar check | **42 / 42** first-vintage dates in `alfred_first_vintage_2026.csv` reproduced content-wise (PAYEMS, AWHMAN incl. the corrected 2026-04 → 2026-05-08, INDPRO, W875RX1, CMRMTSPL, RECPROUSM156N; NOT_YET rows have no issue date); PERMIT/UMCSENT not pulled (DT-13) | `calendar_check_2026.json` |
| §4.1 unrevised re-check | T10Y3M vintage 2026-10-19: 11,201 common dates, **0 changed**; BAA10YM vintage 2026-10-01: 882 common, **0 changed** | `unrevised_check.json` |
| F7 ADS panel | 24,330 daily rows × 1,575 vintages (2008-12-05..2026-10-16) streamed in 196 s; zip sha256 d263487c…, xlsx 21e27f38…; 5 claims-only vintages flagged (2025-10-16..11-13), 9 shutdown-partial (2025-11-20..12-23) | `data/ads_panel/` |
| §5 comparator gate | **MISS under the spec's literal sample** (every vintage 2008-11..2010-10, n = 176): last point 0.8082 vs 0.866 (Δ −0.058), previous-complete-month average 0.9253 vs 0.956 (Δ −0.031). **Computed exactly as the Philadelphia Fed note samples (IP-release-day updates, n = 24): 0.8655 and 0.9560** — both inside ±0.01 (Δ −0.0005 / +0.0000). Reported, not widened; see §4 | `gate_ads.json` |
| §6 Piger real-time path | 240 releases 2006-08-01..2026-09-30; header typo 2025-01-30 → 2026-01-30 corrected and flagged; release lag median **60 d** (min 20, max 69); ALFRED value vector found for 160 releases (first 2012-09-01 → ALFRED 2012-09-04), Piger fallback for 80 | `data/piger/realtime_path.csv`, `realtime_events.json` |
| §6 known events | 3×80%: declared **2009-01-01** (Jul/Aug/Sep-2008 = 88.26/97.68/98.04%), first recession month **2008-02** (chain 51.98% ≥ 50), **peak 2008-01 under the rule as written** — the task/spec text says "peak dated 2008-02" (see §4); 2020 **never** declared; end declared 2010-01-01 with trough 2009-06 (= NBER); **2021-10-29: Sep-2021 = 44.4%**, no fire under either rule; 1-month ≥ 50% catches Mar-2020 at 2020-04-30 and Aug-2008 at 2008-11-01 | `realtime_events.json` |
| NBER | 12 turning points 1980-01..2020-04 with announcement dates; USREC onsets 1972+ = 1973-12, 1980-02, 1981-08, 1990-08, 2001-04, 2008-01, 2020-03 (the August seven); USREC convention cross-checked on all six announced cycles | `data/nber/nber_events.json` |
| tests | **31 passed** offline (`python3 -m pytest test_pipelines.py -q`) | `test_pipelines.py` |

## 2. What was built (per SPEC v1)

### vintages.py (§4.3–§4.4, F6/F8)
- **Vintage lists**: `alfred.stlouisfed.org/series/downloaddata?seid=<ID>` is an HTML page; the dates are the
  `<option value="YYYY-MM-DD">` entries of the `form_selected_vintage_dates` select. Only those are taken.
  Note for the record: the research pass's committed `data/alfred_vintage_lists/vd_*.txt` were extracted with a
  bare date regex and carry **two artefact lines each** — the observation start (1939-01-01 / 1919-01-01 /
  1959-01-01 / 1967-01-01) and the observation END date (PAYEMS 2026-09-01, INDPRO 2026-09-01, W875RX1
  2026-08-01, CMRMTSPL 2026-07-01). The latter four are exactly the "revision-only vintages" the data/timing
  review cited under DT-17; they are not vintages (ALFRED's select has 860/1224/196/158 entries, not
  862/1226/198/160). DT-17's amendment (content-decided issue dates) stands regardless; CMRMTSPL 2024-10-02 is
  a real listed vintage. The new lists under `data/vintage_lists/` supersede the old ones for the run.
- **Transport**: httpx (pinned prod dep), ≤ 8 workers, retry with exponential backoff (1,2,4,8,16 s) on
  transport errors, 5xx, 429/403 and any other non-200/404; a 200 with a non-CSV body is also retried (then
  hard-fails). ALFRED's edge blocks a bespoke User-Agent on the HTML endpoints ("server disconnected" / HTTP/2
  INTERNAL_ERROR, observed 2026-10-20); a Mozilla-prefixed UA passes, so the module uses one.
- **Validation before caching** exactly as §4.4: HTTP 200; first line `observation_date,<ID>_<YYYYMMDD>` with the
  listed date (a mismatch of date OR series is a `header_mismatch` failure, never "a different vintage");
  ≥ 1 numeric data row; last observation month recorded; sorted dates and numeric values enforced; empty 404
  accepted only for dates strictly before the list's first entry (cannot occur under fetch-by-list, kept as
  contract); nothing is written on any failure; cache key (series, listed date); bytes stored exactly as served.
- **Issue dates** (§4.3): earliest listed vintage whose last observation month is M; a month that was never the
  latest month of any vintage (multi-month vintages: PAYEMS/INDPRO/ICSA 2025-10, W875RX1 2019-02 & 2025-10,
  CMRMTSPL 2013-07, 2013-10, 2015-06, 2018-11, 2025-08; RECPROUSM156N 2018-11, 2019-01, 2025-09, 2025-10,
  2026-01) gets no issue date and status `never_latest` with the first vintage that contained it. The first cached
  month per series is `left_censored` (an earlier uncached vintage could be its true issue date; the replay
  starts 2013-06-14 so none of these enter it).
- **Issue panel** (§2.3/§4.3): one row per (issue date, trigger series) over the union of PAYEMS/INDPRO/W875RX1
  issue dates ≥ 2013-06-14: P_c(d), M = P_PAYEMS(d), L_c, K(d) = min P_c, the IS label (A if P_INDPRO < M; B if
  P_INDPRO = M and P_W875RX1 < M; C if P_W875RX1 = M), `canonical`, `lag_ge3`, `dropped`, `is_c_cmrmtspl_lag2`,
  `trigger_month_ne_M`, and per series the vintage used (date + sha256), its latest month and the latest value
  (long table). Same-day double triggers exist (PAYEMS + W875RX1 on 2013-08-02, 2013-11-08, 2013-12-06,
  2014-08-01) and are kept as two rows. Shutdown rows 2025-09..2026-03 are in the panel with their actual lags
  (e.g. 2026-01-22 W875RX1-trigger for 2025-11 is labelled B with M = 2025-12 — `trigger_month_ne_M = 1`).
- **`as_of(d)`**: the latest LISTED vintage ≤ d per series from the cache; raises if that listed vintage is not
  cached (never substitutes a neighbour). Smoke (identity only): 2026-10-20 → PAYEMS 10-02 (2026-09), INDPRO
  10-16 (2026-09), W875RX1 09-30 (2026-08), CMRMTSPL 09-30 (2026-07), ICSA 10-15 (week 2026-10-10) — the F3
  state {INDPRO 0, W875RX1 1, CMRMTSPL 2}; 2025-12-16 → INDPRO 12-03 (2025-09), W875RX1 12-05 (2025-09),
  CMRMTSPL 09-26 (2025-07). `monthly()` mirrors the deployed `_monthly()` collapse.
- **Unrevised re-check** (§4.1): 0 changed values for T10Y3M (2026-10-19 vintage) and BAA10YM (2026-10-01);
  basis for "taken current" confirmed on the run day's data.

### ads.py (§5, F7)
- One streaming pass (openpyxl read-only, 196 s) → per vintage: date (from `ADS_INDEX_MMDDYY`), last date/value,
  and for the last three calendar months present: average, days present, completeness. The daily series of the
  2010-12-03 reference vintage is written (`ads_vintage_2010-12-03.csv`, 18,537 rows) so the gate re-runs offline.
- `ADS_last(d)` / `ADS_avg(M | d)`: latest vintage dated ≤ d, same-day included; `strict=True` = the "< d"
  sensitivity. ADS_avg returns the mean of the month-M days present with `n_days`/`complete`, or value None with a
  reason when M is after the vintage's last date or older than the stored window.
- Claims-only flag: vintages 2025-10-16, 10-23, 10-30, 11-06, 11-13 (all Thursdays = claims days; the Philadelphia
  Fed's "special procedures" per its tech doc). The END of the window is not stated by the source; it is inferred
  from the ALFRED lists: 2025-11-20 = first post-shutdown PAYEMS vintage (first ADS update that could carry a
  monthly release), and 2025-11-20..2025-12-23 (CMRMTSPL resumed 12-23) is flagged `shutdown_partial`.
- Comparator gate: see §4.

### piger.py (§6)
- Parses the 712 × 241 workbook (decimals; ×100 = percent), corrects the one header typo (sandwich rule, flagged),
  validates ranges and monotonicity, builds the first-release path by release date.
- §6 value-vector rule: first ALFRED RECPROUSM156N vintage dated ≥ d_r whose latest month is m_r (fallback Piger).
  160 of 240 releases matched; fallbacks after ALFRED's start: 2012-11-01, 2012-12-01, 2013-01-01, 2013-04-01,
  2013-05-01, 2014-08-04, 2026-03-02 (ALFRED's next vintage already carried a later month). Cross-validation
  Piger×100 vs ALFRED: 107 releases at 1.4e-14 pp, 44 at 0.04 pp, 6 at 0.005, 2 at 0.05 (Piger's 0.1-pp rounded
  2014–2024 columns) — and **one anomaly**: ALFRED vintage 2023-02-01 (for the 2023-01-27 release) carries
  2020-03/04 at 0.14/0.04% where Piger's column has 100/100 (the 2023-03-01 ALFRED vintage is back at 100/100).
  A FRED load glitch on one vintage; it touches 2020 back-history only, not the latest month, and changes no
  rule outcome (rules were run on both Piger's columns and the §6 vectors: identical events and states).
- Rules: 3×80% / 3×20% applied release by release to that release's own vector (strict `>`/`<` per Piger's FAQ;
  `>=` tested too — same events), scanning months ≥ 2001-12 so the back-history's recessions cannot trigger;
  peak = month before the first ≥ 50% month of the chain preceding the start triple; trough (this study's
  symmetric extension, descriptive) = month before the first < 50% month of the chain preceding the end triple.
  1-month ≥ 50% sensitivity on each release's latest month (episodes: 2008-11-01..2009-10-01 with a gap at
  2009-01-01 where Oct-2008 read 16.1%, and 2020-04-30..2020-10-30 with gaps at 06-26/07-31).

### nber.py
- Turning points + announcement dates (12, since 1980) validated (alternation, lag arithmetic, dates after the
  turning point), USREC spells 1960+ (first 1 = peak + 1, last 1 = trough) cross-checked on all six announced
  cycles; onsets for the August study's seven recessions; `nber_events.json`.

## 3. Validation failures encountered
- **Zero** §4.4 validation failures over 1,568 + 14 requests (no header mismatch, no empty/short body, no 404 at a
  listed date). One transient timeout (retried once, OK). Non-CSV bodies occurred only on the HTML LIST endpoint
  with the bespoke UA (fixed by the UA prefix before the pull; the smoke run that hit it cached nothing).
- Development-time issue found and fixed before the pull: the committed research-pass lists (artefact lines,
  above) — the pull never used them.

## 4. Gate results, misses and how they are reported (never widened)
1. **§5 comparator reproduction gate — MISS as literally specified, PASS as the source note samples.**
   SPEC v1 §5 (DT-6 text): "correlations … over every vintage dated 2008-11..2010-10 … each within ±0.01".
   Computed on all 176 archived vintages 2008-12-05..2010-10-29 against the 2010-12-03 vintage: last point
   **0.8082** (target 0.866), previous-complete-month average **0.9253** (target 0.956). The note that produced
   0.866/0.956 ("Real-Time Accuracy of the ADS Index", 2011-01-19) explicitly samples **the IP-release-day
   update of each month** (24 points: last point for the Dec-2008..Nov-2010 updates; the average of the month
   before the right line, Nov-2008..Oct-2010). Reproducing that sample (G.17 day = the INDPRO vintage in each
   month whose content moves the last observation to the previous month — the 26 INDPRO 2008-12..2010-11
   vintages were fetched for this; ADS update = first vintage dated ≥ that day) gives **0.8655 and 0.9560** —
   the note's figures to four and five decimals, so the archive conversion is right and the miss is in the spec's
   sampling clause, not in the data. Both are in `gate_ads.json` (`pass: false` on the literal definition;
   `note_literal.*.within_tol: true`). To be raised with the spec owner: adopt the note's sampling in §5's gate
   text, or keep the literal clause and accept that it cannot pass on this archive. Nothing was widened; ADS
   does not enter a scored run until this is resolved.
2. **§6 known event "peak dated 2008-02" — MISS on the label, the values are unambiguous.** At the 2009-01-01
   release the ≥ 50% chain preceding the Jul-2008 trigger runs Feb-2008 51.98, Mar 58.28, Apr 64.52, May 70.44,
   Jun 78.52 (Jan-2008 = 39.28). Under §6's rule as written (peak = the month before the FIRST ≥ 50% month) the
   peak is **2008-01** and the first recession month **2008-02** — Hamilton's "a recession had started in
   February 2008". The spec/task text "peak dated 2008-02" names the first recession month; verify_R3's
   "chain runs back to Mar-2008" overlooked Feb-2008 = 51.98%. Recorded in `realtime_events.json` as
   `2008_peak_dated_2008-02_as_task_text: pass false` with the chain values; the declaration date (2009-01-01),
   first recession month (2008-02), 2020 never, 2021-10-29 = 44.4% and the sensitivity catch all pass.
3. Everything else named for this stage passed: DT-17 calendar 42/42, §4.1 unrevised 0/0 changes, F4 lag
   patterns, Piger header correction, NBER cross-check.

## 5. Ambiguities resolved (recorded, not decided silently)
- F6 "derived per-issue-date panel (issue date, IS, series, month, value)": the full value history per issue
  date is ~3.4 M rows / ~100 MB; committed instead are (a) the lag pattern per issue date (wide) and (b) per
  issue date × series the vintage used, its sha256, its latest month and latest value (long, 2,385 rows); full
  histories come from the hashed raw cache via `as_of(d)`.
- Pull range "2013-01 onward": applied to PAYEMS/INDPRO/W875RX1/CMRMTSPL/ICSA; RECPROUSM156N from its first
  listed vintage 2012-09-04 (4 extra requests; §6 needs the earliest vintages); INDPRO 2008-12..2010-11 (26)
  fetched only to identify G.17 days for the ADS gate (kept in the vintage table, excluded from the issue-date
  derivation); AWHMAN 2026 (10) only for the DT-17 calendar check (`calendar_check_vintages.csv`, not in the
  issue panel); T10Y3M 2026-10-15..19 (3) and BAA10YM 2026-10-01 (1) for the unrevised re-check.
- F7 "monthly averages for the last three months": stored as such (m0 = month of the last date, m1, m2) with
  day counts and completeness; the full monthly-average matrix (all vintages × all months, for the §5
  "smoothed-fit, filtered-apply" sensitivity) is in the scratchpad npz with its hash recorded, not committed.
- ADS claims-only window end: inferred from the component release calendar (see ads.py), flagged on both bounds.
- Piger 3×80% scan start 2001-12; strict `>`/`<` thresholds per the FAQ (`>=` gives identical events here).
- Piger 1-month ≥ 50% sensitivity evaluated on each release's LATEST month (the real-time reading), not on any
  month in the vector.
- IS label for non-canonical states uses the §2.3 availability rule; the trigger series and trigger month are
  carried separately so the engine can apply §4.3's "one target per (issue date, IS)".
- "Never cached, never read as no vintage": 429/403 and other non-200/404 statuses are treated like 5xx
  (retry then hard fail), not as content.

## 6. Deviations from the spec text
- None in substance. The two reported misses (§4.1–2 above) are differences between the spec's wording and the
  sources it cites; both are reported with month-level values, neither was widened or re-defined.
- `data/alfred_vintage_lists/` (research pass) is left untouched (another tree); the run should use
  `data/vintage_lists/` (F8).

## 7. Known gaps
- Raw vintage CSVs and the ADS monthly matrix live in the session scratchpad; a run in another container must
  re-pull (fetch-by-list, ~2.5 min) and re-convert (~3.5 min) and verify the hashes in `vintage_table.csv` /
  `ads_hashes.json`.
- ICSA has no ALFRED vintage between 2025-09-25 and 2025-11-20 (shutdown); the week-months of 2025-10 are
  `never_latest`. The engine's CLAIMS half at the 2025-11-20 issue date sees the 2025-11-20 ICSA vintage.
- ALFRED RECPROUSM156N vintage 2023-02-01 anomaly (2020-03/04 ≈ 0) is recorded; if the §6 chart uses the §6
  vectors for back-history it should mark that release.
- The ADS gate's note-literal sample depends on 26 INDPRO vintages outside the replay range; they are in the
  vintage table and the `ip_days` are stored in `gate_ads.json`, so the check re-runs offline from the stored dates.
- Lists grow monthly; the run-day re-pull (F8, §11 step 3) will change the list hashes — expected.
