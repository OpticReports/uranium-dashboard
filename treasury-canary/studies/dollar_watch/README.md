# dollar_watch — scoping artefacts for studies/dollar-watch.md (2026-11-02)

SCOPING ONLY: nothing here is pre-registered or graded.

- `notes/` — the three finders' research notes (A the 1971–2026 event record with real ICE DXY; B the
  mechanism and the measurable factors, every endpoint probed; C the academic literature and the
  pre-registrable design) and the transcript of the Oct-2026 talk the question came from. Numbers in
  the notes are as the finders wrote them; the memo carries the reviewer-corrected values.
- `verdicts/` — the two adversarial reviews (1 numbers and data; 2 logic and design). Reviewer 2's
  blocking findings against the orchestrator's first draft are recorded there and applied in the memo.
- `code/` — orchestrator scoping (`dollar_scoping.py`, `decel_test.py`, `decel_realtime.py`,
  `decel_monthly_oos.py`, `chart_*.py`; run with `python3 -I <script> <raw dir> <out dir>`), the
  finders' scripts (`finderA_*`, `finderB_*`, `finderC_*`) and the reviewers' re-implementations
  (`check_*.py`, `review2_*.py`). Session paths are replaced by `<scratch>`.
- `data/` — finder A's tables (`dxy_daily.csv` ICE DXY daily 1971-01-04+, from Yahoo; `dollar_monthly.csv`
  with the FRED and BIS indices; `crises.csv` 25 crises + Plaza with sources; `crises_metrics.csv`,
  `band_excursions.csv`, `speed_events.csv`, `band_summary.csv`, `base_rates.csv`, `gold_daily.csv`
  (GC=F 2000+), `gold_monthly.csv` (World Bank), `chain_2022.csv`, `rr_*` Reinhart–Rogoff flags);
  the scoping outputs (`dollar_summary.json`, `decel_test.json`, `decel_realtime*.json`,
  `decel_monthly_oos.json`, `dollar_monthly.csv` = the monthly panel used by the scoping);
  finder B's `analyze_out.json` (lead/lag dates) and `johnson_quarterly.csv` (BIS USD credit vs dollar).
  Not committed: FRED/BIS/OFR raw pulls (re-fetchable; IDs in the notes), the Shiller workbook.
- `figs/` — `fig_dollar_scoping.png`, `fig_decel_rule.png` (orchestrator), `fig_funding_leadlag_finderB.png`,
  `fig_band_onsets_finderC.png`.
