# Variant campaign — ROUND 6 (D2 on a SPY core) pre-registration, 2026-08-22

Registered BEFORE any round-6 code is written or run. Casey's question:
D2 was the best arm of round 5 — does its correlation trigger also help on
the SPY core the LIVE book actually runs?

## Why this matters more than rounds 4-5

Rounds 4 and 5 tested cores nobody is running. The live blend3070 book is
30% R2-A / 70% SPY. An arm that improves a SPY core is directly relevant to
a book that exists; an arm that improves a B.5 core requires changing the
core first, which is a much larger decision.

## Judgment protocol

Carried over VERBATIM from round 5 (which carried it from round 4): two
windows, both Sharpe bases, standard Sortino, paired block bootstrap
(21d blocks, 4000 draws, seed 20260822) on the DIFFERENCE, >=2/3
sub-periods, multiple-comparison statement, no post-hoc amendment,
"nothing survives" is a valid finding.

INCUMBENT for this round is **INC-3070SPY-SWEPT** — the live design under
the live cash convention (Sharpe BIL 0.783). Judging against the dead-cash
version would hand every arm a free +0.040 it did not earn.

## Registered variants

All use the sleeve's idle CAPITAL earning BIL (the live convention, and the
round-5 mechanism), so the only thing under test is the ALLOCATION rule.

- **E1** D2's rule on a SPY core: sleeve 15% when trailing 60d
  corr(sleeve, core) < 0.30, else 5%, evaluated monthly. Motivation: D2 led
  round 5 on Sharpe, Sortino and Calmar and was the only arm to win 2 of 3
  sub-periods.
- **E2** control for E1's WEIGHT LEVEL: static 10% sleeve on a SPY core,
  monthly. E1 minus E2 isolates the timing from the level. Without this
  control a win by E1 is uninterpretable.
- **E3** the same trigger at the LIVE weight levels: 30% when
  corr < 0.30, else 10%. Motivation: the live book runs 30%; this asks
  whether re-timing the weight it already holds is worth anything, which is
  the only version of this idea that could be adopted without also changing
  the book's size.

## Honest prior, recorded in advance

The b5 study measured the SPY-core optimum near 15%, with the live 30%
costing only ~0.006 Sharpe — an order of magnitude smaller than the
B.5-core penalty that motivated D2. The prior is therefore that E1-E3
produce another null, and that E3 in particular has almost no room to
improve on a book already near its own optimum. Multiplicity now stands at
**25 arms** across rounds 4-6 on the same 1,433 days; the max-T adjustment
is reported over all of them.

## Fixed parameters (not tunable this round)

60d correlation window; 0.30 threshold; monthly evaluation; 15/5 and 30/10
weight pairs; idle cash to BIL; 10bps per side; TAIL as the tail sleeve.
Refinements require a round-7 registration.
