# cycle_nowcast_v2/data — files from the 2026-10-20 research pass

All fetched 2026-10-20 unless the filename says otherwise. Untrusted data: parse with `python3 -I`, never execute. Source URLs: `DATA_MANIFEST.csv` (29 datasets) and studies/cycle-nowcast-v2.md §1; FRED keyless CSV = https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES ; ALFRED vintages = https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=SERIES&vintage_date=YYYY-MM-DD ; Piger = https://jeremypiger.com/recession_probs/ ; NBER announcements = https://www.nber.org/research/business-cycle-dating/business-cycle-dating-committee-announcements ; ADS = https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/ads ; CFNAI = https://api.data.chicagofed.org/CFNAI/ .

Correction 2026-10-20 (data/timing review DT-17): `alfred_first_vintage_2026.csv` row AWHMAN 2026-04 was a binary-search artifact (2026-07-12); corrected to 2026-05-08, the verified first vintage. The sha256 row below is of the corrected file.

Not committed (size): the ADS all-vintages workbook (203 MB) — re-download from the ADS page; the 371 ALFRED battery vintages of the research pass (re-pulled by the study's cached fetcher).

Review fixes 2026-10-20 (B1/B2 counter-agent passes), files added or changed in this directory:

- `vintages_raw.tar.xz` — F6 raw ALFRED vintage cache frozen in git (SERIOUS-1, DT-4): 1,589 served CSV bodies + 1,589 `.meta.json` sidecars (3,178 members, 50.5 MB raw, 392,944 bytes xz; `tar --sort=name --owner=0 --group=0 --numeric-owner --mtime='2026-10-20 00:00:00Z' --format=gnu | xz -T1 -6`). sha256 `acb7f966fbac2e08fdded085cea567f526b6e18f8a6d09b33bfa1c3add17b17a`, recorded in `vintages_panel/build_summary.json` (`raw_tarball`). `vintages.py build|calendar` and `as_of()` read it when no `--cache` is given; every row of `vintages_panel/vintage_table.csv` re-hashes identically from the extracted files (test_pipelines). Includes the four earliest listed T10Y3M / BAA10YM vintages (2014-01-27, 2026-01-02 / 2014-05-16, 2026-01-02) fetched for the extended §4.1 unrevised check (MINOR-2) and not in `vintage_table.csv` (not replay series). results.json must record this hash as part of F6.
- `alfred_shutdown/alf_ICSA_2025-11-20.csv`, `alf_ICSA_2025-12-11.csv`, `alf_ICSA_2026-02-05.csv` — the ICSA vintages v1 §2.4 says F4 gains (D3), at the latest LISTED vintage date <= each issue date (2025-11-20, 2025-12-16 -> 2025-12-11, 2026-02-06 -> 2026-02-05; §4.4 fetch-by-list). Copied byte-for-byte from the F6 cache (hashes equal the `vintage_table.csv` rows; a fresh 2025-11-20 pull on 2026-10-20 was byte-identical). `alf_ICSA_2026-01-09.csv` (research pass) is the listed 2026-01-08 vintage with the requested date echoed in its header (body identical to the cache's `ICSA_2026-01-08.csv`); it stays and is used for 2026-01-09. T10Y3M on the three dates is taken current (the 2026-10-20 pull, days <= the issue date) per v1 §4.1; the 2026-01-09 vintage file is used where it exists.
- `DATA_MANIFEST.csv` — `local_file` column scrubbed from absolute session paths to paths relative to the scratchpad (NOTE-5; no other column changed, CRLF kept).

| file | bytes | sha256[:16] |
|---|---|---|
| DATA_MANIFEST.csv | 9418 | 3f442ff77ac609c0 |
| alfred_cmrmtspl_m3d10.json | 1772 | 6ef40d80a3136ad1 |
| alfred_first_vintage_2026.csv | 3564 | 90a83cf232782900 |
| alfred_lag_table_1st_of_month.txt | 4046 | 7ef1c738e8eb809f |
| alfred_revisions.json | 7076 | 14fa68e0347e6511 |
| fred_2026-10-20/AWHMAN.csv | 16872 | 10e14acf1b3a3ab5 |
| fred_2026-10-20/BAA10YM.csv | 14137 | 19f3a0dc9825dfa5 |
| fred_2026-10-20/CMRMT.csv | 6745 | b0be58a594ec382c |
| fred_2026-10-20/CMRMTSPL.csv | 16088 | c84bd6dc387d54f2 |
| fred_2026-10-20/GS10.csv | 14206 | 40323f225e613a19 |
| fred_2026-10-20/HMRMT.csv | 6503 | 92f7ea1753f89cd9 |
| fred_2026-10-20/ICSA.csv | 56184 | 2b1eb1b4a5f5bf48 |
| fred_2026-10-20/INDPRO.csv | 24460 | 0fc53a503386efaf |
| fred_2026-10-20/PAYEMS.csv | 18405 | c8c429818ed73de6 |
| fred_2026-10-20/PERMIT.csv | 12713 | 216dcf040c76d9a4 |
| fred_2026-10-20/RECPROUSM156N.csv | 11510 | e372f9c471adda60 |
| fred_2026-10-20/T10Y3M.csv | 186289 | d16594e5fdf89ea4 |
| fred_2026-10-20/TB3MS.csv | 17865 | 631bc444a8c5370c |
| fred_2026-10-20/UMCSENT.csv | 13422 | 27ce18aeda2ab875 |
| fred_2026-10-20/USREC.csv | 26829 | a42a3581fe9c260d |
| fred_2026-10-20/W875RC1.csv | 28928 | 74e310822a455a17 |
| fred_2026-10-20/W875RX1.csv | 14961 | fa12b2e42b79f1bd |
| fred_2026-10-20/multi_series.csv | 46782 | 0d2fd097bd2311b1 |
| alfred_shutdown/alf_CMRMTSPL_2025-11-20.csv | 15821 | 3037129462a4cc4a |
| alfred_shutdown/alf_CMRMTSPL_2025-12-16.csv | 15821 | 82ad01aaf63a6bcc |
| alfred_shutdown/alf_CMRMTSPL_2026-01-09.csv | 15867 | 189c2295bc52610e |
| alfred_shutdown/alf_CMRMTSPL_2026-02-06.csv | 15890 | cd4b686b34711fc4 |
| alfred_shutdown/alf_ICNSA_2026-01-09.csv | 55475 | acf65ef7bde76b96 |
| alfred_shutdown/alf_ICSA_2026-01-09.csv | 55473 | 0d5309d58a9ce673 |
| alfred_shutdown/alf_ICSA_2025-11-20.csv | 55347 | dc42a4a6a184cd6d |
| alfred_shutdown/alf_ICSA_2025-12-11.csv | 55401 | cd0515896159d2ef |
| alfred_shutdown/alf_ICSA_2026-02-05.csv | 55545 | ca4d9c513eaaaf79 |
| alfred_shutdown/alf_INDPRO_2025-11-20.csv | 24211 | f3ed61d59622a4df |
| alfred_shutdown/alf_INDPRO_2025-12-16.csv | 24229 | 9c490e0fa4b09d07 |
| alfred_shutdown/alf_INDPRO_2026-01-09.csv | 24269 | 1904361fc2bc40ef |
| alfred_shutdown/alf_INDPRO_2026-02-06.csv | 24289 | 842d7e28885d2b1b |
| alfred_shutdown/alf_PAYEMS_2025-11-20.csv | 18198 | bc0b00fa1f18e963 |
| alfred_shutdown/alf_PAYEMS_2025-12-16.csv | 18234 | c449c146f4e381de |
| alfred_shutdown/alf_PAYEMS_2026-01-09.csv | 18252 | f1d37befcb87530f |
| alfred_shutdown/alf_PAYEMS_2026-02-06.csv | 18252 | 85bd4ee4c257c0ac |
| alfred_shutdown/alf_T10Y3M_2026-01-09.csv | 183110 | 8f4e85dc225d13de |
| alfred_shutdown/alf_UMCSENT_2026-01-09.csv | 13303 | cf6522e57434fb29 |
| alfred_shutdown/alf_UMCSENT_2026-02-06.csv | 13319 | 1438ec2eb9333a7a |
| alfred_shutdown/alf_W875RX1_2025-11-20.csv | 14742 | 543119a0c9636c6d |
| alfred_shutdown/alf_W875RX1_2025-12-16.csv | 14761 | fce0b29f89f34c90 |
| alfred_shutdown/alf_W875RX1_2026-01-09.csv | 14761 | 202d84c72258f0ad |
| alfred_shutdown/alf_W875RX1_2026-02-06.csv | 14799 | 19088fdec3f6d9c3 |
| alfred_vintage_lists/vd_CMRMTSPL.txt | 1760 | 323e62d03747940d |
| alfred_vintage_lists/vd_INDPRO.txt | 13486 | 18e36fb47f91c11f |
| alfred_vintage_lists/vd_PAYEMS.txt | 9482 | aba1d155f6faafc6 |
| alfred_vintage_lists/vd_W875RX1.txt | 2178 | ac4f93af806b250f |
| piger/History_of_Real_Time_Recession_Probabilities.xlsx | 850125 | 297de74203772a44 |
| piger/piger_current_9_30_26.csv | 18501 | 1228dddd9464baeb |
| piger/piger_first_release_by_month.csv | 7939 | b6568223fda35a88 |
| piger/piger_realtime_history.csv | 13881 | 2d3ff2f6807e00dd |
| piger/piger_realtime_releases_clean.csv | 10094 | 1cff8b7aeec2728a |
| ads_cfnai/ADS_Index_Most_Current_Vintage.xlsx | 784375 | 5e5ef57efde51b3b |
| ads_cfnai/ads_realtime_endpoint_by_vintage.csv | 70804 | 9ecd81092b8da325 |
| ads_cfnai/cfnai-data-series-csv.csv | 32980 | 8994854297341bf2 |
| ads_cfnai/fred_CFNAI.csv | 11763 | 411c9468074fb1a5 |
| ads_cfnai/fred_CFNAIMA3.csv | 11733 | a20109d250b08a98 |
| nber/nber_turning_points_announcements.csv | 3886 | 24e1e2b997a9f677 |

## Run-day re-pull 2026-10-28 (F8 / F6 / F5 for the scored run; commands and outputs in `../notes_freeze.md`)

- `vintage_lists/`: every list re-fetched by the harness (`vintages.py pull` / `pi-list`). Content changed for two: `vd_ICSA.txt` (+2026-10-22, n 903) and `vd_T10Y3M.txt` (+2026-10-20..2026-10-27, n 3149); PAYEMS, INDPRO, W875RX1, CMRMTSPL, RECPROUSM156N, BAA10YM, PI unchanged (identical hashes, new `retrieved` stamps); AWHMAN not re-fetched (calendar check only). `SHA256SUMS` / `manifest.json` rewritten by the harness.
- `vintages_raw.tar.xz` REBUILT from the raw cache after the re-pull: 1,591 served CSV bodies (+ ICSA 2026-10-22, the one new panel vintage since 2026-10-20; + T10Y3M 2026-10-27, the listed 2026 vintage the v1 §4.1 run-day re-check reads; BAA10YM's latest listed 2026 vintage 2026-10-01 was already cached), 394,036 bytes xz, sha256 `4388498dc652c400ebdc01d4a433d543dc991f5360a480c20c590d823bd047b6` (same tar/xz flags as above, `--mtime='2026-10-28 00:00:00Z'`); recorded in `vintages_panel/build_summary.json` by `vintages.py build`. `vintage_table.csv` has 1,572 rows (+1); `issue_dates.csv` / `issue_panel_*.csv` are byte-identical to the 2026-10-20 build (an ICSA vintage adds no issue date).
- `piger/History_of_Real_Time_Recession_Probabilities.xlsx` re-downloaded 2026-10-28T15:45:31Z: byte-identical (sha256 `297de742…`; no new release since 2026-09-30). `realtime_path.csv` / `realtime_events.json` re-derived by `piger.py --cache`: identical except `built`.
- `fred_2026-10-28/` = **F5**, the ONE frozen run-day pull (13 series, keyless `fredgraph.csv`, HTTP 200 each, 2026-10-28T15:46:23Z..26Z) with `MANIFEST.json` (sha256, retrieval time, last observation, diff vs F3 per series). CMRMTSPL (last 2026-07) and W875RX1 (last 2026-08) are byte-identical to `fred_2026-10-20/`; PERMIT (1 revised value), ICSA (+week 2026-10-17, 1 revision), UMCSENT (+2026-09), T10Y3M (+6 days to 2026-10-27) moved.
