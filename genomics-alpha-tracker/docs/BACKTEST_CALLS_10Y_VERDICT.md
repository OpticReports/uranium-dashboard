# Counter-agent verdict — 10y calls-engine replay (PIT catalyst store)

Reviewed: `backend/scripts/build_pit_catalysts.py`, `backend/scripts/backtest_calls_10y.py`,
`docs/BACKTEST_CALLS_10Y.md`, `backend/data/pit_catalysts.json`,
`backend/data/backtest_calls_10y_results.json`, `backend/data/pit_ctgov_cache/` (~6.9k raw responses).
Date: 2026-08-20.

## 1. PIT look-ahead analysis (evidence)

**The store's interval dates are NOT public-posting dates.** The int-API history `changes[].date`
equals `lastUpdateSubmitQcDate` (verified across the cache: 6505/6508 exact matches), i.e. the
sponsor-submission/QC date. Every cached version payload carries the actual public date
(`lastUpdatePostDateStruct` / `studyFirstPostDateStruct`). Measured QC→post lag over all 6,508
non-v0 versions in the cache:

| | n | min | p50 | p90 | p99 | max |
|---|---|---|---|---|---|---|
| updates (v>0) | 6508 | 0 | **2d** | 5d | 25d | 92d |
| first posting (v0) | 357 | — | **4d** | 9d | 18d | 20d |

So the replay sees registry changes a **median 2 days (updates) / 4 days (first record) before the
market could**. The doc's claim — "a sponsor's update is only visible from the day it was posted,
exactly like the live pipeline" (Read-this-first bullet 1; repeated in "earliest public record" and
"the day that update posts") — is **factually wrong as written**.

**Materiality test — I rebuilt the store with every interval shifted to its true post date and
re-ran all three catalyst flags through the script's own functions:**

| flag | QC-date store (as shipped) | post-date store (corrected) | fire overlap |
|---|---|---|---|
| quiet_before_catalyst | n=349, avg R net **+0.023** | n=352, **+0.045** | 338 shared / 11 QC-only / 14 post-only |
| pullback_into_catalyst | n=157, +0.011 | n=158, +0.016 | 156 shared |
| binary_event_within_n_days | n=278, +0.016 | n=281, +0.016 | 268 shared |

Direction of the bias: the look-ahead **did not flatter the catalyst flags — it marginally hurt
them** (corrected numbers are equal or slightly better; all CIs still straddle zero; every verdict
unchanged). The finding "catalyst-conditioned flags ≈ flat" survives the correction. But the doc
must state the true mechanism and this quantification, not assert posting-date fidelity it does not have.

Interval mechanics (verified in code + cache):
- Half-open [from, to) with pointer advance `to <= d` — no double-counting, no gap at boundaries.
- A version dated d is usable at the close of d. With true post dates that is approximately right
  (posted intraday, fire at close, entry next open); with QC dates it is the 2-5d look-ahead above.
- Trials are invisible before their first version (`d < iv["from"] → skip`) — confirmed; but "first
  visible" is the first QC date, median 4d before actual first public posting (same bias family).
- COMPLETED/TERMINATED as-of-d correctly stops generating catalysts (`status in ACTIVE_STATUSES`
  gate) and past PCDs are excluded (`pcd >= d`) — both confirmed in `pit_calendar_by_bar`.
- Same-date resubmissions: last version of the day wins — correct.
- 3 v0 rows have studyFirstPostDate before the v0 QC date (CT.gov artifact, worst -972d); immaterial.

## 2. Grading fidelity

- `build_levels` / `grade_call` / `atr` imported from `app/calls/rules.py` **unmodified** — no
  reimplementation. Entry-bar semantics safe: entry = next bar's open, and that bar's open can never
  spuriously trigger its own stop/target (stop < entry < target by construction); intrabar
  stop/target on the entry day is correct given an open fill.
- Entry next open is a documented, conservative deviation from the 2y backtest's at-close entries;
  slippage convention (tiered per-side bps, R against original risk unit) is byte-identical to
  `backtest_calls.py` (`SLIPPAGE_BPS_BY_TIER` imported).
- Expiry rule implemented as documented: `min(45d, driving_pcd − 1d)`, clamped to entry date.
  Edge case: **3 of 278** binary_event calls (pcd = fire date) exit at the entry-day close, i.e. ON
  or after the PCD — a technical violation of sell-before-the-event; negligible (PCD is an estimate).
  quiet and pullback: 0 violations.
- Unresolved-at-end exclusion: 143 fires (2/44/16/81 as the doc lists). I marked the recoverable 133
  to market at the last close: they are **in-flight winners** (pullback_price_half mean +0.96R,
  rel_strength +0.78R, volume +0.35R, quiet +1.05R — the 2026 tape into data end). Excluding them
  slightly UNDERSTATES the price flags; conservative direction, does not bias the headline claims.
- Suppression: 0 violations of the 7-calendar-day per-flag-per-name rule across all 7,393 call rows.
  (Note: the START≥2016 filter is applied before suppression, so a hypothetical pre-2016 fire cannot
  suppress an early-2016 one — self-consistent, negligible.)

## 3. Data checks

- **Adjusted closes verified**: LLY bars match stockanalysis.com's adjusted history exactly
  (2026-08-17/18/19 = 1183.16 / 1225.73 / 1280.34); LLY/XBI/BNTX show proper dividend-adjustment
  factors (LLY k=0.833 in 2015 → 1.0 today); all other names k=1.0, consistent with no splits.
- **No stock splits occurred in-window for any universe name.** Every >80% raw close jump traced to a
  real event, not a broken adjustment: ARCT 2017-01-17 (Alcobra MEASE failure), CMPS 2025-06-23,
  PACB 2024-04-16, WGS 2026-05-05 (crashes), MASS 2025-03-04, QSI (squeezes).
- **MRNA's final bar (+177% on 2026-08-19, close 174.38, 185M shares) is REAL** — the intismeran
  (V940/Keytruda) phase-3 melanoma readout — not corrupt data. Verified against multiple news sources
  ([Motley Fool](https://www.fool.com/coverage/stock-market-today/2026/08/19/stock-market-today-aug-19-moderna-skyrockets-177-on-positive-phase-3-melanoma-data/),
  [gurufocus](https://www.gurufocus.com/news/9043328/moderna-mrna-shares-surge-over-90-after-successful-skin-cancer-vaccine-trial)).
  Fires on that bar produce no call (no next bar), so it does not inflate the books.
- XBI benchmark: 2,736 bars, aligned via the same date-indexed lookup imported from
  `backtest_signals.py`; benchmark present, adjustment factor sane.
- Universe: 33 active names; ALMR excluded (86 bars < 120) → 32 replayed, matching the header.

## 4. Stats reproduction

- Re-ran `python -m scripts.backtest_calls_10y` from cached bars + store: **report regenerated
  byte-identical** to the committed doc.
- Independently recomputed from the per-fire rows (own bootstrap implementation, same clustering):
  quiet n=349 avg +0.0229 CI90 [-0.0945, +0.1458]; rel_strength n=3041 +0.1475 [+0.0859, +0.2069];
  pullback_into n=157 +0.0111; binary n=278 +0.0162 — **all match the doc to rounding**.
- Combined book independently reproduced: 1,136 taken (+3,872 skipped at cap), total **+106.4R**,
  max DD **96.8R** — matches.
- Baseline = `range(60, len(bars), 5)` — identical construction to `backtest_signals.py` (imported
  constants); baseline 1w/1m/3m +0.29%/+1.03%/+3.42% as claimed.
- `_guard_pre_registered` genuinely compares flags.yaml to **hardcoded literals** (0.10/0.30/1.5/
  true; 2.5/$1M/60; 0.15; 7) matching the pre-registered backtest_signals thresholds — not to itself.
  Gap: the catalyst-window params (quiet 5-45d/0.85, pullback 10-45d/0.7, binary 21d/0.85) are read
  live from flags.yaml without an assertion; they match today, but future yaml tuning would silently
  change a rerun.
- `python -m pytest tests -q`: **225 passed** (exit 0).

## 5. Framing / honesty audit

- **"Excluding LLY+CERS lifts quiet to +0.085R" is NOT in the report at all.** The number reproduces
  (n=245, +0.0853) but the slice is doubly misleading if quoted anywhere: LLY's own quiet book is
  POSITIVE (+4.3R over 55 calls, avg +0.078 — above the full-sample +0.023), so "excluding LLY"
  removes nothing; **the entire lift comes from dropping CERS alone** (n=49, −17.2R; ex-CERS-only
  avg = +0.084). If this slice is presented to Casey it must be labeled post-hoc/diagnostic-only and
  attributed to CERS, not to an LLY+CERS pair.
- Honesty block coverage: PCD≠readout ✓; survivorship/relative-only ✓; composite/confidence gates
  absent ✓; hype/analyst/live-trigger set not replayable ✓; PDUFA/AdComm/earnings lanes missing ✓;
  Yahoo-chart-API deviation ✓ (and verified accurate); trial-cap ✓; multiple-comparison note ✓;
  walled-off-from-sizing ✓.
- NOT covered: (a) the version-date≠posting-date lag and its direction (the doc asserts the
  opposite — see §1); (b) alias/universe hindsight — today's `ctgov_names` (MRNA→ModernaTX) and
  today's watchlist replayed to 2016; mild in practice (MRNA bars start at its 2018 IPO; but LLY,
  a mega-cap added to the list recently, contributes 55/349 quiet and 243/278-scale binary fires and
  16% of the quiet sample from 2016) — the survivorship bullet gestures at this but does not name it.
- Verdict logic (baseline-not-zero bar, CI-low must clear baseline mean) is sound and honestly applied;
  catalyst flags are correctly called UNSUPPORTED.

## MATERIAL ISSUES

1. **Doc misstates the PIT mechanism.** Interval dates are CT.gov submit/QC dates, a median 2 days
   (updates; p90 5d, max 92d) and 4 days (first records) BEFORE public visibility — the doc claims
   posting-date fidelity ("only visible from the day it was posted"). Measured impact: negligible
   and slightly conservative (post-date-corrected quiet +0.045 vs +0.023; verdicts unchanged), but
   the claim as written is false and sits in the doc's honesty block. Fix the three affected lines
   and add one line quantifying the lag + measured direction.
2. **The LLY+CERS quiet slice (+0.085R)** — if it is being presented anywhere (it is absent from the
   doc), it is a post-hoc exclusion whose lift is 100% attributable to CERS; LLY's quiet calls are
   above-average. Label diagnostic-only and re-attribute, or drop it.

## MINOR ISSUES

- 3/278 binary_event calls exit on/after the driving PCD (pcd==fire-date clamp edge).
- 143 open-at-end fires excluded are in-flight winners (mean ≈ +0.8R MTM) — direction conservative;
  worth one line in the doc.
- Catalyst-window thresholds read from live flags.yaml without an assertion guard (price-half
  thresholds are guarded); reproducibility of a future rerun depends on yaml stability.
- Alias/universe hindsight not explicitly named in the honesty block (see §5).
- Doc header says "32 names" (bars basis) while the store section says "22/33" (store basis) —
  consistent but worth a clarifying word.
- START filter applied before suppression; negligible edge effect at the 2016 boundary.

## VERDICT

**PASS WITH CORRECTIONS.** Every claimed headline number reproduces exactly (byte-identical report
regeneration; independent recomputation of CIs, combined book, baselines; 225 tests pass); grading
uses the production code unmodified; the data is clean (including the startling-but-real MRNA final
bar); the look-ahead I found in the PIT store is real (median 2-5 days) but measured to be
immaterial and directionally conservative for the flags under test. Required before merge/presentation:
correct the doc's posting-date claim (+ add the lag quantification), and label/re-attribute the
LLY+CERS slice wherever it is quoted.
