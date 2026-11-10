# Counter-agent verdict — pre-catalyst asymmetry study (2026-08-19)

Reviewer: adversarial counter-agent pass per repo convention. Everything below was independently recomputed from the cached price series, from fresh stockanalysis.com API pulls, and from my own re-implementations of the metrics — not by re-running the study's code.

## 1. Data integrity

**day_move_pct recheck: 37/37 verified events recomputed from `px_cache/` adjusted closes match the JSON to the cent, and all direction labels match the move sign.** To break the circularity of checking the cache against itself, I re-fetched 6 tickers fresh from the stockanalysis.com API (MDGL, ABVX, GERN, LLY, AKRO, SRRK — 7 events) and got identical moves. Cache is not stale or tampered.

| Ticker | Date | Claimed | Recomputed | Fresh API | Independent source check |
|---|---|---|---|---|---|
| BIIB | 2022-09-28 | +39.85 | +39.85 | — | — |
| MRNA | 2022-12-13 | +19.63 | +19.63 | — | — |
| LLY | 2023-05-03 | +6.68 | +6.68 | +6.68 | — |
| LLY | 2025-08-07 | -14.14 | -14.14 | -14.14 | — |
| VKTX | 2024-02-27 | +121.02 | +121.02 | — | — |
| MDGL | 2022-12-19 | +268.07 | +268.07 | +268.07 | GlobeNewswire PR confirms 2022-12-19 topline, MAESTRO-NASH, first NASH Ph3 win — matches |
| GERN | 2024-03-15 | +92.00 | +92.00 | +92.00 | ODAC 12-2 vote 2024-03-14 confirmed (OncLive/CancerNetwork); no 2024-03-14 bar in series (halt handled correctly: move is 03-15 vs 03-13 close) |
| SRRK | 2024-10-07 | +361.99 | +361.99 | +361.99 | BusinessWire PR confirms 2024-10-07 SAPPHIRE primary-endpoint hit — matches |
| ABVX | 2025-07-23 | +586.00 | +586.00 | +586.00 | GlobeNewswire PR dated 2025-07-22 (after-hours), move printed 07-23 — matches dataset convention |
| QURE | 2025-09-24 | +247.73 | +247.73 | — | GlobeNewswire PR confirms 2025-09-24, 75% cUHDRS slowing, pivotal Ph1/2 — matches |
| KROS | 2024-12-12 | -73.15 | -73.15 | — | 8-K + PR confirm 2024-12-12 halt of 3.0/4.5 mg/kg TROPOS arms on pericardial effusion — matches |
| AKRO | 2023-10-10 | -62.61 | -62.61 | -62.61 | — |
| APLT | 2024-11-29 | -76.31 | -76.31 | — | see note below |
| ...all remaining 24 events | | match | match | | |

No event description misattributes drug, indication, or event type in the 6 externally cross-checked cases; drug/trial names in the other rows are consistent with my knowledge (KarXT EMERGENT-2, HELIOS-B, SEQUOIA-HCM, ASPEN, AFFIRM-AL, etc.). No sign/direction mismatches anywhere.

Integrity notes (not errors, but worth stating):
- **MDGL 2024-03-15 PDUFA has weak event isolation**: t-1 (03-14) was -10.8%, event day +11.0% — net ~flat over two sessions. The dataset blurb "every verified event shows an outsized move" is a stretch here and for LLY 2023-05-03 (+6.7%).
- **APLT t-1 (2024-11-27) fell -16.1% before the after-close CRL** — anticipation/informed flow inside the drift window; and its z is still "quiet" (-0.23) because vol20 was already enormous. Shows the z-normalization can classify violent names as quiet.

## 2. Code correctness

Independent end-to-end re-derivation (my own code, not the library) for VKTX 2024-02-27, GERN 2024-03-15, ABVX 2025-07-23: **r10, vol20, drift_z10, event_ret, BS call/put, straddle multiple, and cost_pct all match to full precision.**

- **No look-ahead in the metrics.** `window_ret(n)` ends at t-1 (`a(prev)/a(prev-n)`); vol20 ends at t-1 and never touches the event bar; event_ret is t-1 close → event close. Verified on the VKTX calendar: event bar 2024-02-27, entry bar (idx-10) = 2024-02-12, t-1 = 2024-02-26 — entry is exactly 10 trading days before the event bar.
- **BS formulas correct**: call verified against my implementation; put via put-call parity with r=0.04 is exact. European pricing slightly understates American premia → multiples slightly flattered; immaterial at 15/252 years.
- **Straddle exit** = |S1−K_atm| with K rounded from the ENTRY-day close — as specified. Intrinsic-only exit is a genuine floor (conservative).
- **Spearman**: tie-averaged ranks + Pearson-on-ranks, correct; reproduces +0.2473 exactly.
- **Bootstrap**: reproduced their CI90 at IV 1.0 exactly ([2.549, 5.987]). Percentile indexing uses `means[200]` where the 5th percentile of 4000 is arguably `means[199]` — off-by-one, immaterial.
- **Headline numbers all verify**: n=37, 22/15, median |move| 39.85% (~39.9%), quiet n=12 median 40.1% vs running n=25 median 37.5%, straddle means 6.70/4.07/2.73/2.06/1.39x and profitable share 89.2%→37.8%, bias_guard 5.2%/29.5%/68.7%.

**Real code-level findings:**

1. **LOOK-AHEAD in the quiet/running STRADDLE split** (`straddle_quiet`/`straddle_running` in run_study.py). Classification uses r10 measured through t-1, but the simulated trades are entered at t-10. Between entry and t-1 the "running" names drifted up to ±30% (CYTK +30.2%, VKTX +21.3%, ABVX +20.3%, QURE -21.9% inside the holding window) — so `straddle_running` (mean 4.94x at IV 1.0 vs quiet 2.27x) is mechanically inflated by drift that happens AFTER entry. These two result blocks cannot be presented as strategy economics. The headline claims avoid them, but they sit in study_results.json waiting to be quoted. A tradeable test of the quiet flag requires entry at t-1 close (6 days to expiry, different premium) — untested.
2. **OTM strike collision**: `round(s0*1.2)` equals `round(s0)` for GERN (s0=2.00 → both K=2) and MREO (s0=2.79 → both K=3). Their "20% OTM call" is actually ATM. Contaminates otm_call aggregates mildly; not in headline claims.

## 3. Methodology

- **Selection on the dependent variable is explicit and severe.** The droplog drops events for "price move too small" (SRPT '23 approval -7.9%, AMLX approval +3.3%, VRTX acute-pain +2.4%, APLS +5.4%). Median |move| 39.9% and every mean multiple are therefore UPPER BOUNDS on the class, full stop. The study knows this (bias_guard exists) — but see next point.
- **bias_guard arithmetic is correct** (p·m_sel + (1−p)·m_fizzle = 1 ⇒ p = (1−m_fizzle)/(m_sel−m_fizzle)) **but its inputs are the rosiest defensible choices**: (i) m_sel is the outlier-dominated MEAN (ABVX's 37.8x alone contributes ~1.0 of the 4.07 mean at IV 1.0). Median-based breakeven sharp-shares are roughly double: ~32% vs 16% at IV 1.0; ~59% vs 29% at IV 1.5; ~11% vs 5% at IV 0.6. (ii) The 8% fizzle is GENEROUS to the strategy — the study's own dropped events fizzled at 2.4–7.9%; at 4% fizzle the mean-based share rises 16%→21% (IV 1.0). The guard bounds the bias only under its own favorable assumptions; both the median-based row and fizzle sensitivity must be shown.
- **Uniform scenario IV across mega-cap and micro-cap is unreal in both directions**: LLY never trades at 300% IV, ABVX-type names never at 60% before a dated readout. The per-IV rows answer "given moves like these, what does entry IV x pay?" — they are NOT portfolio-realistic returns, and the cheap-IV rows are dominated by exactly the micro-caps that would never be cheap. No actual historical option prices anywhere in the study.
- **Intrinsic-only exit** is genuinely conservative (floor value; ~5 trading days of time value forfeited). Partially offsets, does not cure, the selection bias.
- **Frictions unmodeled**: micro-cap chains (GERN at $2, MREO at $2.79, ARDX at $4) have $0.50 strike grids, wide spreads, thin size. Whole-dollar rounding maxed at +7.5% skew (MREO) — tolerable — but real fills on a 19%-of-spot straddle in these names would materially degrade multiples.
- **Survivorship**: 4 delisted names dropped (ISEE, RETA, SAGE, SAVA). SAVA's ~-84% and SAGE's CRL were straddle WINNERS, and ISEE/RETA were acquired after positive catalysts — exclusion likely biases straddle stats slightly DOWN, not up. Not a rescue of the selection problem, but the direction is honest to state.
- **Quiet/running split, tiny n and tails**: quiet n=12 / running n=25. Medians 40.1% vs 37.5% — statistically indistinguishable. Spearman(|z|,|move|)=+0.25 has t≈1.51, p≈0.14 — NOT significant. Removing the single largest outlier (ABVX, a "running" name): running median falls to 36.0%, running mean 0.96→0.76 vs quiet 0.48 — the mean ordering survives top-1 removal but remains tail-driven, and the MEDIANS actually put quiet slightly HIGHER. So: no evidence quiet moves more; equally no significant evidence of "the reverse."
- Adjusted-vs-unadjusted mixing exists only in the open-gap field (documented, unused in headlines). Adjusted-close strikes are scale-invariant for multiples. r=0.04, no dividends: trivial at 15 days. All fine.

## 4. Conclusion audit

**(a) "Binary readouts in the selected sample produced median |40%| event-day moves" — SUPPORTED** as worded (verifies to 39.85%; "in the selected sample" does the load-bearing work). Presentation must say the selection was partly ON move size (droplog), so 40% is an upper-bound estimate of the class median, not an estimate of it.

**(b) "Long-vol decisively +EV only when entry IV well below the 150-300% known-binary zone; exploitable class = undated events" — OVERSTATED.** The directional shape is real and survives medians: median multiple crosses 1.0 between IV 1.5 (1.50x) and 2.0 (1.13x), 0.77x at IV 3.0; even this favorably-selected sample fails to pay at known-binary IV — that half is solid and is the study's strongest finding. But "decisively +EV" at low IV rests on (i) outlier-driven means from a sharp-mover-selected sample (median-based breakeven sharp-shares 32%/59% at IV 1.0/1.5), (ii) a generous 8% fizzle, and (iii) zero evidence that identifiable events actually trade at 60-100% IV (no options data). Safe wording: "at known-binary IV the trade fails even on this favorable sample; below it, profitability is plausible but is an upper bound conditional on selection, and untested against real option prices."

**(c) "Quiet into event does NOT predict larger event moves; if anything the reverse; value must come via cheaper IV, untested" — SUPPORTED except the middle clause.** The null result is real (medians 40.1 vs 37.5, n=12/25). "If anything the reverse" is OVERSTATED: it leans on a non-significant Spearman (+0.25, p≈0.14) and an outlier/tail-driven mean gap, while the medians point (weakly) the other way. Also note the quiet-subset straddle economics in the results file are look-ahead contaminated (Section 2) and must not be cited in support of anything. The "cheaper IV, untested, grade live" framing is exactly right.

## MATERIAL ISSUES (must-fix before presenting)

1. **Look-ahead in `straddle_quiet`/`straddle_running`**: classification at t-1, entry at t-10 — running-name multiples embed up to ±30% of post-entry drift. Remove these blocks, or re-run with entry at t-1 close, or label them "not tradeable — diagnostic only" in the results and any writeup.
2. **bias_guard headline (5%/29%/69%) uses outlier-dominated means and the most generous defensible fizzle.** Must present alongside: median-based breakeven shares (~11%/~32%/~59% at IV 0.6/1.0/1.5) and fizzle sensitivity 4-10%. Never quote 6.70x/4.07x mean multiples as strategy EV.
3. **Conclusion (b) wording**: drop "decisively +EV." The supported claim is one-sided: known-binary IV doesn't pay even on a favorably selected sample; low-IV profitability is an upper bound under selection, untested vs real option prices.
4. **Conclusion (c) wording**: delete or explicitly hedge "if anything the reverse" — non-significant, tail-driven, contradicted by the medians.

## MINOR ISSUES

- OTM strike == ATM strike for GERN and MREO (`round(s0*1.2)` collision) — fix `k_otm` (use max(k_atm+1, ...) or fractional strikes) or exclude sub-$5 names from otm_call stats.
- Bootstrap percentile off-by-one (`means[200]` vs `[199]` of 4000) — immaterial.
- Dataset blurb "every verified event shows an outsized move" overstated for LLY 2023 (+6.7%) and MDGL 2024 (+11% after -10.8% the prior day; weak event isolation).
- APLT t-1 -16.1% pre-announcement drop — anticipation inside the drift window; worth a footnote.
- Micro-cap option realism (strike grids, spreads, size) unmodeled — keep in the honesty box.
- Survivorship note: 4 delisted exclusions likely bias straddle stats slightly DOWN (SAVA -84% was a straddle winner) — honest to state, not a fix for selection.
- European BS / no dividends / r=0.04 — trivial at 15 days, fine as is.

## VERDICT

**PASS WITH CORRECTIONS.**

Data layer is clean: 37/37 moves reproduce from source, cache verified against fresh API pulls, 6 events verified against independent press releases/coverage, no direction or attribution errors, halt/holiday date conventions handled correctly. Metrics and pricing code are correct with no look-ahead in the measurement windows. The four material issues are all at the inference/presentation layer: a look-ahead-contaminated subgroup table that must not be quoted, an outlier-and-assumption-flattered bias guard that needs its median/sensitivity rows shown, and two conclusion phrasings ("decisively +EV", "if anything the reverse") that claim more than the sample supports. Fix those and the study is presentable.
