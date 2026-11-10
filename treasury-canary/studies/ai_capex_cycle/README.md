# ai_capex_cycle — scoping artefacts for studies/ai-capex-cycle.md (2026-10-31)

SCOPING ONLY: nothing here is pre-registered or graded.

- `notes/` — the three finders' research notes (A history of capex booms; B the measurable chain,
  every endpoint probed; C predictive methods and the earthquake test design). Numbers in them are
  as the finders wrote them; the memo carries the reviewer-corrected values.
- `verdicts/` — the two adversarial reviews (1 numbers and data integrity; 2 logic and design).
- `code/` — the orchestrator's scoping scripts (`earthquake_scoping.py`, `earthquake_variants.py`,
  `chart_*.py`; run with `python3 -I <script> <raw dir> <out dir>`) and the reviewers' re-implementation
  and confound scripts (`eq_indep.py`, `footer_stats.py`, `rzone_check.py`, `confound_checks.py`,
  `within_vol_checks.py`, `damage_timing.py`), kept so every number in the chart footers is reproducible.
- `data/` — `hyperscaler_capex_ocf_quarterly.csv` (EDGAR companyfacts, 2018Q4-2026Q3, tags per notes_B
  §2a), `census_datacenter_monthly.csv`, `rpo_quarterly.csv`, `nvda_dso_dio.csv`, FRED CSVs
  (TBSDODNS, NCBDBIQ027S, BCNSDODNS, GDP, QUSNAM770A, QUSPAM770A, USREC; keyless fredgraph), and the
  scoping outputs `episodes.json` / `summary.json` / `variants.json`.
  NOT committed (2.3 MB): Ken French `49_Industry_Portfolios.csv` (CRSP vintage 202609, sha256
  633958bf36d25da6…) and `F-F_Research_Data_Factors.csv` (sha256 a3894d74d553cab8…), from
  https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html — re-download into a raw/
  folder to re-run the scoping.
- `figs/` — `fig_earthquake_scoping.png`, `fig_rzone_scoping.png`, `fig_capex_chain_scoping.png`.
