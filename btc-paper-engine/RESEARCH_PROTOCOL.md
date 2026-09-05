# Research protocol + standing audit (2026-07)

The nine questions every strategy test must face, run against S1-S6. This doc
is the trial registry and the pre-registration template. Update it with EVERY
future test batch — an uncounted trial silently lowers the evidence bar.

## 1. Trial registry (running count)

| Batch | Trials | Where documented |
|---|---|---|
| Original pullback research (2024-26 window) | ~1,500 | BTC_Winning_Strategies_Report |
| 14.5y strategy lab (5 families) | 28 | RESEARCH_S4.md |
| Blend weight × leverage frontier | 20 | RESEARCH_S4.md |
| Blend weight/win-rate scan | 5 | session notes 2026-07 |
| ETH transfer test (frozen BTC params) | 1 | §10 below |
| Forecasting foundation models (registered, NOT yet run) | 10 | RESEARCH_FORECAST_FM.md |
| Win-rate rule battery (2026-08) | 12 | RESEARCH_WINRATE.md |
| Astrology battery, standalone (2026-09) | 153 | RESEARCH_ASTRO.md |
| Astrology overlays on S6 (2026-09) | 699 | RESEARCH_ASTRO.md addendum |
| S4 trail robustness diagnostic (2026-09) | 63 | RESEARCH_TRAIL.md |
| **Total** | **~2,491** | |

Backfill note (2026-09-05): the win-rate and astrology batches had been
documented in their own files but never added here, so the running count sat
at ~1,564 while ~864 further configs had been evaluated. Fixed above. The
trail row counts 63, not the 21 its pre-registration declared: 21 registered
cells + 21 post-hoc kill-switch-off cells + 21 placebo cells were all
evaluated on the same window, and a config evaluated is a trial spent
whichever bucket it was labelled with.

Registered-but-unrun trials are counted from registration, not from
completion. Counting them only on success is how a registry stops
deflating anything.

## 2. Deflated Sharpe audit (barbell-lab stats, modern era 2022-2026)

DSR = probability the observed Sharpe reflects skill rather than being the
best-of-N selection artifact. Hurdle SR0 = what the best of N zero-skill
trials would show. Computed with conservative independence assumptions:

| Book | SR (ann.) | Hurdle SR0 | **DSR** |
|---|---|---|---|
| S3 pullback 1× (N=1,500) | 1.04 | 1.58 | **0.12** |
| S4 donchian 1× (N=28) | 0.76 | 0.96 | **0.31** |
| S5 blend 1.5× (N=1,548) | 1.39 | 1.58 | **0.33** |

**Reading: formally, none of these is yet distinguishable from selection
bias.** Two mitigations keep this from being a death sentence: (a) the 1,500
trials were highly correlated variants, so the true hurdle is lower than the
independence assumption implies; (b) 2022-24 was semi-out-of-sample for the
pullback. But the direction is unambiguous: **treat every backtest number as
an upper bound, size accordingly, and let the live record adjudicate.** This
is the quantitative justification for the small-first deployment rule.

## 3. Economic rationale (who pays us) — all pass, recorded

- Pullback: harvests forced liquidations / retail panic exits at moving
  averages inside an intact trend; counterparty = levered late entrants.
- Donchian trend: harvests slow information diffusion + herding; counterparty
  = anchored holders who sell strength late and buy weakness late.
- Blends: no separate edge claimed — portfolio arithmetic on corr −0.15.
- RULE: no future backtest runs until the candidate's rationale is written.

## 4. Objective function (fixed BEFORE any future test)

Primary: MAR over the modern era (2022→), min 100 trades, net of 6 bps/side.
Secondary: DSR against the registry count. A candidate that wins on another
metric but loses on these is a rejection, not a "different kind of win."

## 5. Pre-registration template (copy for every future test)

    HYPOTHESIS: <edge + who pays>
    TRIALS THIS BATCH: <n configs>            (add to §1 on completion)
    DECISION RULE: adopt iff <metric> >= <x> on TRAIN and VALIDATE and
      holdout touched ONCE; else record failure here.
    RETIREMENT RULE (if adopted): <pre-registered exit condition>

## 6. Power analysis — what live evidence can/cannot show

At S1's pace (~46 trades/yr, ~1.0 ann. Sharpe class):

- Win rate 62.9% vs coin flip: ~60 trades ≈ **15 months** to 95% confidence.
- Sharpe 1.0 vs 0 on daily marks: ~900 days ≈ **2.5 years**.
- PF 1.3 vs 1.0: order of **150-300 trades** ≈ 3-6 years.

Implication: live results will not "prove" the edge on a useful timescale.
The standard is triangulation: live consistent with backtest + rationale +
OOS survival. Neither 10 straight wins nor 5 straight losses means anything.

## 7. Stopping rule (in force)

Signal-space search is CLOSED until the live gate concludes (15-20 fresh
trades). Open work is portfolio-layer only: cash yield on idle capital, ETH
book research pass, rebalance cadence, vol-targeting the blend. Rationale:
the last three signal searches produced two holdout failures and one rejected
family, while both real improvements (S5/S6) came from construction.

## 8. Evidence bar (asymmetric by design)

False positive (deploying a fake edge levered) costs capital; false negative
costs opportunity. Therefore: adoption needs TRAIN + VALIDATE + single-touch
HOLDOUT + rationale + DSR reported; retirement needs only the pre-registered
trigger. Ties break toward NOT deploying.

## 9. Build backlog produced by this audit

1. Cash-yield modeling on idle capital (real, ~+0.7pp CAGR, no risk added).
2. ETH pullback research pass (breadth — the only lever that raises win rate
   AND lowers DD; full protocol, own pre-registration).
3. Live-vs-backtest gap panel (the engine's stated purpose, §6 power numbers
   as the "n needed" context) — surfaces automatically when the gate matures.
4. DSR/trial-count wired into /replay/compare output so every window shows
   its deflation context.
5. **Alert on a book `halted` transition, and make the executor see it.**
   `book.halted` is set at `core.py:215` and cleared only by a manual
   `POST /books/<n>/resume`; it persists across restarts. btc-executor never
   reads `legs.<leg>.halted`, so an S4 halt books as a routine
   `INFO leg_closed engine_exit`, pages nobody, and `/pulse` reads healthy
   while the trend leg is permanently flat and the blend runs 25% cash.
   README's halt/resume line documents `{S1|S2|S3}` only. Found by the
   trail study's counter-agent panel (RESEARCH_TRAIL.md, forwardable #2).
6. Fix the blend curve's dropped first exit (`bench_blend.py:46-48` appends
   the first point after applying the first return, so every published S5/S6
   number silently omits one trade's P&L — +0.4% to +5.3% depending on the
   window). Its own change, because it moves committed numbers.

## 9a. Protocol violations, recorded (2026-09-05)

- **§7 violated by the S4 trail robustness diagnostic** (RESEARCH_TRAIL.md).
  §7 closes signal-space *search*, not merely adoption, and lists what stays
  open ("portfolio-layer only" + four named items); an S4 exit-parameter
  sweep is on none of them. Its pre-registration conceded the sweep is
  signal-space search and then argued that barring adoption made it
  permissible — that reads §7 as if it were §8. Recorded, not waived. The
  `dd_halt=1.0` grid inside that study was not registered at all.
- **The single-touch holdout for S4 exit parameters is spent.** RESEARCH_S4
  reserved 2024-07..2026-07 for one touch; the trail study swept it 21 times
  (63 counting the post-hoc and placebo grids). §8 requires a single-touch
  holdout for adoption, so the §8 adoption path for the S4 exit family is
  **closed**, not deferred. Any future work there needs genuinely new data.

## 10. ETH transfer test — pre-registered, executed 2026-07-26: DO NOT ADOPT

Hypothesis: the pullback edge is a crypto-microstructure property, not
BTC-specific. Design: ONE trial, BTC parameters frozen, engine code path,
Bitstamp ETH/USD 4h, 1x unlevered. Rule (fixed before running): adopt an
observe book iff expectancy > 0 AND MAR >= 0.7 on BOTH windows, >=100 trades.

| Window | n | expectancy | return | max DD | MAR | verdict |
|---|---|---|---|---|---|---|
| 2022-01..2024-06 | 101 | −0.24% | −28.1% | −43.7% | −0.29 | FAIL |
| 2024-07..2026-07 | 85 | +0.58% | +50.5% | −23.0% | 1.02 | pass |

**Decision: not adopted. No refits run** (an ETH-tuned variant would be a new
batch with its own registration).

The informative part: ETH PASSES on exactly the window the BTC research was
fit on, and FAILS the earlier one — while BTC's pullback made +79% in that
earlier window. So the edge did NOT transfer across assets in the same
period, which weakens the microstructure rationale and raises the
probability that part of BTC's own edge is period-specific. This is a
Bayesian update DOWN on the pullback family, consistent with the DSR audit
(§2), and further justification for the live gate + small-first rule.
