# Variant campaign — ROUND 4 (core selection) pre-registration, 2026-08-22

Registered BEFORE any round-4 variant is run. Motivated ONLY by evidence that
existed beforehand: the B.5-as-core study (counter-agent verdict
scratchpad/b5_counter_verdict.md, PASS WITH CORRECTIONS) and rounds 1-3.

## Why this round exists

Casey's question: is there a combination of the R2-A sleeve and the B.5
Enhanced defensive book — weighting, rebalancing, or overlay — that beats
either alone on Sharpe AND Sortino?

## The problem this round must not fall into

The round-4 counter-agent measured the 95% CI on a Sharpe DIFFERENCE in this
data at approximately +/-0.4 (block bootstrap, 21d blocks, 4000 draws). With
~1,400 real trading days, ordinary variant search finds apparent winners that
are noise. A leaderboard is not a finding. Therefore:

## Judgment protocol (fixed BEFORE results)

- Two windows, both reported for every variant, never mixed:
  REAL 2020-12-03..2026-08-19 (all B.5 constituents genuinely trading) and
  SYNTHETIC-EXTENDED 2016-08-23..2026-08-19 (proxy splice, unadjusted).
- Metrics: CAGR, max DD, vol, Sharpe (rf=0 AND BIL-excess, both printed),
  Sortino (standard convention: downside deviation over N, not over the
  count of negative days), Calmar, corr to SPY.
- INCUMBENTS: (a) B.5 alone, (b) 30/70 R2-A/SPY, (c) SPY alone.
- A variant SURVIVES only if ALL of:
  1. Sharpe AND Sortino beat the best incumbent over the FULL real window;
  2. the block-bootstrap 95% CI on the Sharpe DIFFERENCE vs that incumbent
     EXCLUDES ZERO (21d blocks, 4000 draws, paired on dates);
  3. it beats that incumbent in >=2 of 3 equal sub-periods of the real window;
  4. it does not LOSE on the synthetic window by more than 0.10 Sharpe.
- Bonferroni-style caution is REQUIRED in the writeup: with N variants the
  naive 5% threshold is wrong; report the count and the implied bar.
- NO variant may be added, dropped, or re-parameterized after any result is
  seen. Refinements go to a round-5 registration. Nothing here becomes a
  config change or a live weight without a separate promotion (TUNING.md).
- If NOTHING survives, that IS the finding and it gets reported as such.

## Registered variants

Sleeve = R2-A (frozen dollar curve). Core = B.5 Enhanced unless stated.
Tail sleeve held at TAIL for every variant (the conservative corner) so the
unresolved Question #1 cannot flatter one variant over another.

- **C1** static sleeve weights 5 / 10 / 15 / 20 % on a B.5 core.
  Motivation: the b5 study's clean sweep peaked near 5%, live is 30%.
- **C2** three-way static: R2-A / B.5 / SPY at 10/45/45 and 20/40/40.
  Motivation: B.5 and SPY are only 0.769 correlated; both cores may pay.
- **C3** inverse-vol weighting between sleeve and core, monthly, from
  trailing 60d realized vol, sleeve capped at 30%.
  Motivation: round-3 vol-targeting reduced DD; this is its two-asset form.
- **C4** whole-book vol target 10% annualized, monthly, from trailing 20d,
  leverage capped at 1.0 (deleverage only, cash to BIL).
  Motivation: pure DD mechanics, pre-existing round-1 V9 idea.
- **C5** regime-conditional sleeve: sleeve weight 20% while the XBI
  200dma prior-close gate is ON, 0% while OFF (proceeds to core).
  Motivation: the gate is already R2-A's own entry condition; this applies
  it at the ALLOCATION layer, which has never been tested.
- **C6** rebalance-rule sweep on the live 30/70 B.5 blend: 5% band (live),
  10% band, monthly calendar, quarterly calendar.
  Motivation: round-2 slippage work; band choice was never optimized.
- **C7** sleeve idle-cash routing: R2-A's uninvested cash earns the CORE's
  return instead of 0%. The frozen sleeve holds dead cash on 29.6% of days
  (counter-agent measurement), worth ~+0.6pp/yr on the sleeve alone.
  Motivation: a MECHANICAL fix to a known accounting artifact, not a search.
- **C8** correlation-conditional sleeve: sleeve at 30% when trailing 60d
  corr(sleeve, core) < 0.30, else 10%, evaluated monthly.
  Motivation: the diversification premise of the blend is correlation; this
  tests it directly rather than assuming it is constant.

## Fixed parameters (not tunable this round)

60d/20d lookbacks; 10% vol target; 1.0 leverage cap; 0.30 correlation
threshold; 30% sleeve cap; 10bps per side; TAIL as the tail sleeve. If any
looks "almost good", the ONLY allowed action is registering a round-5 variant.
