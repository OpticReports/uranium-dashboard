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
| Switch study round 1 (S5↔S6 leverage rules, incl. random benchmark) | ~41 | RESEARCH_SWITCH.md |
| Switch study round 2 (16 pre-registered rules + 6 statics) | 22 | RESEARCH_SWITCH.md |
| S4 drought candidate batch (H1 ensemble 1 + H2 sizing 2, **run 2026-08-19**; H3 breakout-confirm 2, registered but §7-blocked, NOT run) | 5 | RESEARCH_S4_DROUGHT.md §5, §9 |
| **Total** | **~1,622** | |

*Note (2026-08-19 registry correction, per the S4 drought study): the two
switch-study rounds ran 2026-08-07 but were never added here — an uncounted
trial silently lowers the evidence bar, so they are counted now. The round-1
count (~41) is inferred from its statistical panel's "best-of-41" selection-
noise bar; round-2's own panel used burden 57 for its nulls. Treat ~1,617 as
an estimate with that stated uncertainty. See RESEARCH_S4_DROUGHT.md §6.*

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
