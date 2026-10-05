# Pre-registration — ROUND 11, one open call per symbol

Committed BEFORE any round-11 code exists. Nothing here is a live change;
the output is a proposal for the executor's entry planner, or a null.

## Question (2026-10-05, from the round-10 follow-up)

The live planner has no per-symbol limit: a name that fires again while
already held takes another cap slot. Measured on the live-rule replay
(S0, $120k base, scratch check before this file): one name is held 2+
times on 87% of open days; 258 of 674 entries (38%) went into a name
already open; the largest single name is a median 20% / p90 40% / max 64%
of the sleeve; mean R of repeat entries equals first entries (+0.20 vs
+0.20). Meanwhile 78% of gated fires are skipped at the 10-slot cap.
Does refusing a repeat entry, and handing the slot to the next gated fire
in a different name, improve the book?

## Hypothesis

**H16:** one open call per symbol raises book Sharpe (more independent
bets for the same ten slots, same expected R per trade) and cuts
single-name concentration, with CAGR and max drawdown no worse.

## Arms (executor path: T+2 fill, IBKR costs, BIL carry, XBI gate, cap 10,
risk 1%; book = 30/70 with the 5pp band; LIVE base $120,000; the $100,000
base runs only as the reduction check)

| arm | rule |
|---|---|
| A0 | anchor: the live rule (no per-symbol limit) = round-10 S0 |
| U1 | at most 1 open call per symbol |
| U2 | at most 2 open calls per symbol |

"Open" uses the replay's live slot occupancy: a call holds its symbol from
its gate date (the T+1 sizing cycle, when the executor counts a pending
MOO) until its exit, exactly as `select_capped_exec` holds its cap slot. A
refused repeat consumes no slot; the next gated fire in time order may
take it. Selection order is otherwise unchanged (gate date, entry date,
symbol).

## Metrics

Book: CAGR, Sharpe, max DD, longest underwater (full, 5y, 2y windows).
Sleeve: CAGR, max DD, mean deployed fraction, days at cap. Concentration:
largest single-name share of sleeve equity, daily median / p90 / max.
Selection: entries taken, entries refused as repeats, distinct names held
per open day (mean). Primary statistic: paired stationary block bootstrap
of the book-level Sharpe DIFFERENCE vs A0 (identical block draws, 10,000
draws, mean block 21 days, seed 20261006, Bonferroni family = 2; 63-day
block sensitivity reported).

## Decision rule (fixed now)

Two tiers; an arm is proposed under the FIRST tier it meets.

1. **PROPOSE (improvement):** Bonferroni-2 lower bound of the Sharpe delta
   > 0; book max DD no more than 2 pp worse than A0; 5y Sharpe delta > 0.
2. **PROPOSE (risk control):** the change is a concentration limit, so it
   may be adopted on NON-INFERIORITY when it measurably reduces
   concentration: one-sided 95% lower bound (p5) of the Sharpe delta
   ≥ −0.10; book max DD no worse than A0 + 0.5 pp; 5y Sharpe delta
   ≥ −0.05; p90 largest-name share of the sleeve at least 10 pp below A0's.

Otherwise NULL. If both U1 and U2 qualify, propose the one with the higher
point Sharpe delta; tie → U1 (simpler).

## Honesty (carried into the results)

In-sample over the same 10.6 years as every prior round; survivor-shaped
fire set; the fire rate is taken as given; repeat-fire behaviour of the
tracker is whatever it was historically; costs IBKR fixed + tiered
slippage; carry realised. A pass changes the executor's planner only (the
tracker keeps publishing every gated fire); the shadow grader and H14 are
unaffected.
