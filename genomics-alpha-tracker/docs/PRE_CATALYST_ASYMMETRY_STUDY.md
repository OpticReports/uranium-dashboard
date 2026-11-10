# Pre-Catalyst Asymmetry Study — the Moderna-miss postmortem

_Frozen 2026-08-19 · 37 web-verified binary readout events, 2022-2025 ·
daily adjusted closes (stockanalysis.com) · NO historical option prices used
anywhere · counter-agent verdict logged below._

## Why this exists

On 2026-08-19 MRNA rose +130% intraday (\$62.96 → \$144.91 by 12:03 ET) on the
Phase 3 INTerpath-001 melanoma readout (intismeran / mRNA-4157, partnered with
Merck) — the first successful Phase 3 for any mRNA cancer therapy — and the
genomics tracker had zero visibility. Postmortem found three stacked failures:

1. **Universe hole** — MRNA was never in `watchlist.yaml` (BNTX and ARCT
   carried the `mrna` tag; Moderna itself didn't).
2. **Sponsor-name blindness** — the catalyst scanner queried ClinicalTrials.gov
   by display name. "Moderna" matches 1 trial; the registered sponsor
   "ModernaTX" matches 40, and the pivotal Phase 3 is lead-sponsored by Merck
   (reachable only through the collaborator match).
3. **Calendar semantics** — INTerpath-001's primary completion date is
   2029-10-26; today was an *interim analysis*. A PCD-based calendar can never
   date this event class. The tell was public anyway: the Phase 2b 5-year data
   (−49% recurrence risk) was presented at ASCO in June, and MRNA re-rated
   +33% over the following 60 sessions while the tracker watched nothing.

All three are fixed or systematized in the same commit as this doc
(MRNA + `ctgov_names` aliases + partnered-trial ingestion + radar-gap warning
+ `quiet_before_catalyst` observe-only flag; plus the new
`catalyst-options-engine` paper service).

## Study design

- **Events:** 38 curated binary catalyst events (phase 2/3 readouts, interims,
  PDUFA, AdComm) 2022-2025; 37 verified (SAVA excluded — unverifiable price
  series). 22 positive / 15 negative. Every date web-verified against the
  press release AND cross-checked against the price series (move sign must
  match the outcome). Drop log kept alongside the dataset.
- **Metrics per event:** pre-event windows END AT t-1 (no look-ahead);
  `drift_z10` = 10d return / (20d realized vol scaled to 10d); event move =
  close-to-close on the readout trading day.
- **Options simulation:** ATM straddle / ATM call / 20%-OTM call bought at the
  close 10 trading days before the event, Black-Scholes entry at scenario IVs
  (60%…300% annualized), exit at INTRINSIC on the event close (all remaining
  time value forfeited — conservative). Strikes rounded to whole dollars off
  the entry close.

## Results (frozen)

Median |event-day move|: **39.9%** (range −82% to +586%).

ATM straddle, all 37 events, by entry IV. MEDIANS are the planning numbers —
means lean on one +586% outlier (ABVX adds ~1x to the mean at 100% IV alone):

| entry IV | median mult | mean mult | % profitable | straddle cost (% spot) | breakeven sharp-share (median-based / mean-based)* |
|---|---|---|---|---|---|
| 60%  | 3.57x | 6.70x | 89% | 11.7% | 11% / 5%  |
| 80%  | 2.74x | 5.07x | 84% | 15.5% | 22% / 11% |
| 100% | 2.24x | 4.07x | 76% | 19.4% | 32% / 16% |
| 120% | 1.87x | 3.40x | 68% | 23.2% | 43% / 21% |
| 150% | 1.50x | 2.73x | 62% | 29.0% | 59% / 29% |
| 200% | 1.13x | 2.06x | 54% | 38.5% | 86% / 43% |
| 300% | 0.77x | 1.39x | 38% | 57.1% | 100% / 69% |

\* share of ALL real events that must land "sharp" (like this selected sample)
for the straddle book to break even, assuming non-sharp events fizzle at |8%|.
This is the selection-bias correction lens: the sample was curated for sharp
movers, so every multiple is an upper bound. The median-based column is the
honest planning number (counter-agent correction — the mean-based one is
tail-flattered).

Quiet vs running (|drift_z10| ≤ 0.75 vs >): quiet n=12 median |move| 40.1%,
running n=25 median 37.5%; Spearman(|drift_z|, |move|) = +0.25, not
significant (p≈0.14). A quiet-vs-running straddle-payoff split was computed
and then EXCLUDED: the counter-agent showed it look-ahead contaminated
(classification uses drift through t-1, entry is at t-10).

## Findings

1. **SUPPORTED:** when biotech binaries land, moves are enormous (median |40%|
   in the selected sample). The MRNA case (ATM call 3-10 sessions before →
   14-32x at 60-120% IV scenarios) is representative of the class, not a fluke.
2. **SUPPORTED (as breakeven arithmetic, not as measured EV):** long-vol
   structures clear breakeven **only when entry IV is well below the
   known-binary zone** (150-300% annualized,
   `knowledge/fda_catalyst_stats.md` [HEURISTIC]) — the median straddle
   crosses below 1x between 150% and 200% IV, and at 200%+ IV the
   breakeven sharp-share is 86-100% (impossible). The low-IV payoffs are
   UPPER BOUNDS (selected sample, no real option prices) — the paper engine
   tests them live. The exploitable class is events the market has NOT
   dated: interim analyses, partnered assets, off-radar names. Exactly
   today's event.
3. **REJECTED:** "quiet price into the event → bigger event move." No
   detectable relationship in either direction (Spearman +0.25, p≈0.14;
   medians indistinguishable). The desk intuition survives only in its IV
   form: quiet price → cheaper option → better payoff per premium dollar —
   untestable historically without option data.
4. **TO GRADE LIVE:** finding 3's IV form. The options engine snapshots real
   chains (Nasdaq, keyless) daily and grades `quiet_before_catalyst` +
   entry-IV setups observe-only (H7 in HYPOTHESES.md).

## Honesty box

- **Selection bias is the dominant caveat.** Events were curated and verified
  as sharp movers; in-line/fizzle readouts are under-represented by
  construction. Every payoff multiple is an upper bound; the breakeven-share
  column is the correction lens.
- **No historical option prices** — BS entries at stated scenario IVs, uniform
  across caps; intrinsic-only exits; no spreads, skew, slippage, or borrow.
- **Measurement basis:** close-to-close adjusted prices; MRNA "today" figures
  are a 12:03 ET intraday print, not a settled close.
- **Survivorship:** ISEE, RETA, SAGE dropped (delisted, no price series) —
  likely removes negative-outcome events. SAVA excluded as unverifiable.
- **Small n:** 37 events; 12 in the quiet bucket. The quiet/running comparison
  is indicative, not significant. In-sample throughout; nothing is a forecast.

## Counter-agent verdict

**PASS WITH CORRECTIONS** (2026-08-19, adversarial review; full report in
`docs/pre_catalyst_asymmetry/counter_agent_verdict.md`). Data integrity: all
37 moves reproduce from cached prices and fresh API re-pulls; 6 events
re-verified against independent primary sources; no direction or attribution
errors. Code: 3 events re-derived end-to-end; windows end at t-1, no
look-ahead in the core metrics; BS/parity, Spearman, bootstrap reproduce
exactly. Material corrections, ALL APPLIED to this doc and the results:
(1) quiet-vs-running straddle split excluded as look-ahead contaminated;
(2) OTM strike collision on low-priced names fixed;
(3) median-based breakeven shares added alongside tail-flattered mean-based
ones; means never quoted as EV;
(4) findings 2 and 3 reworded (upper-bound framing; "no detectable
relationship" instead of "the reverse").

## Visual companion

Charts (MRNA case, event-move distribution, IV frontier, breakeven guard,
drift-vs-move scatter): published as the "The Moderna Miss" artifact,
2026-08-19.
