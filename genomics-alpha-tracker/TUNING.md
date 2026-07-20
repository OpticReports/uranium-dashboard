# TUNING.md — the law for the self-improvement loop

An agent may propose changes to this system's trading configuration. This file
is the contract it must follow. It exists because an unconstrained "helpful"
agent will widen scope, fit noise, and narrate plausible-but-wrong changes.

## Hard rules

1. **Never trade, never send anything, never touch delivery.** This loop edits
   configuration and opens pull requests. Nothing else.
2. **Never self-merge.** Every change ships as a PR; a human merges. The merge
   IS the safety system.
3. **One concept per proposal.** One weight, one threshold, one trigger
   promotion/demotion — never a basket. If two changes seem needed, open the
   better one and mention the other in the PR body.
4. **Every proposal cites evidence.** Concrete numbers from the tracker's own
   graded record (flag track record, calls scorecard, post-mortems,
   performance cohorts) — never intuition, never narrative.
5. **Every proposal passes its gate BEFORE the PR is opened** (gate matrix
   below). If the gate fails or lacks data, revert the edit and stop. "No
   proposal this cycle" is a correct and common outcome.
6. **Minimum evidence floors.** No proposal touching a signal with fewer than
   20 graded 1-month outcomes; no exit-parameter change with fewer than 10
   newly closed calls since the last accepted change. Below the floor, report
   "insufficient evidence" and end.
7. **Bounded steps.** A weight moves at most 0.05 per proposal; a threshold at
   most 20% of its current value. Trigger promotion/demotion is binary but
   gated hard (below).
8. **Cooldown.** After a tune PR is merged, no further proposal in the same
   lane for 28 days. Markets print one history; consecutive edits chase noise.
9. **Read aggregates, not raw data.** The evidence inputs are
   `/tuning/evidence` (or its JSON dump) and the gate scripts' outputs. Do not
   load raw price history or full tables into context — that is what the
   deterministic scripts are for.

## Allowed files

- `backend/config/scoring.yaml`   (component weights, min gates)
- `backend/config/flags.yaml`     (flag thresholds, suppression)
- `backend/config/calls.yaml`     (triggers, conviction gate, risk, horizon, liquidity)

Nothing else. Not the engine code, not the tests, not this file.

## Gate matrix — which change requires which proof

| Change | Gate | PASS means |
|---|---|---|
| Component weights (`scoring.yaml`) | `python -m evals.replay ic --proposed <file>` (needs a DB with score-snapshot history — run where that history lives) | Mean daily rank-IC of composite vs 1-month forward XBI-excess return improves, and the bootstrap 90% band of the improvement excludes zero |
| Promote observe-only flag to call trigger (`calls.yaml`) | `python -m evals.replay promotion --flag-type <type>` against the live track record | n ≥ 20 graded 1m outcomes AND Wilson 90% lower bound of hit rate > 0.50 AND avg excess > 0 |
| Demote an active trigger | Same promotion gate, inverted | Wilson 90% UPPER bound < 0.50 at n ≥ 20, or avg excess < 0 at n ≥ 30 |
| Exit params: stop mult / RR / time-stop (`calls.yaml`) | `python -m scripts.backtest_calls --refresh` | Proposed cell beats the current cell on slippage-adjusted avg R AND sits on the plateau (its neighbors agree) |
| Flag thresholds (`flags.yaml`) | Track-record comparison where the aggregates allow; otherwise the change ships OBSERVE-ONLY (threshold change fires flags, never calls) until its own record accrues | Stated in the PR |
| Conviction gate `min_composite` | Calls scorecard cut by `composite_at_call` bands (in the evidence bundle) | Higher band demonstrably outperforms at n ≥ 10 per band |

Behavioral invariants (never hold through a binary, Tier C never auto-calls,
direction rules, gap-aware grading) are enforced by the test suite —
`pytest` must stay green on every proposal, and the agent may not edit tests
to make them pass.

## Workflow per cycle

1. Fetch the evidence bundle: `GET /tuning/evidence` on the deployed app
   (auth-gated), or run `python -m scripts.tune_proposal --local` where the
   production DB lives, or read a JSON dump the operator provides.
2. Run `python -m scripts.tune_proposal --json <dump>` → prints the evidence
   summary and per-lane sufficiency verdicts.
3. If no lane clears its floor: report "insufficient evidence — no proposal"
   and stop. Do not manufacture a proposal.
4. Otherwise pick the single highest-value change, edit a PROPOSED copy of the
   config, run the matching gate, and only on PASS apply the edit.
5. Run `pytest` (all invariants green).
6. Open a PR on a `tune/<date>-<concept>` branch. Body must contain: the
   exact diff, the evidence rows/numbers, the gate output verbatim, the risk,
   and what the reviewer should check. Never claim the change is live.

## Why the gates look paranoid

Reply-rate loops (the pattern this borrows from) get thousands of cheap,
roughly independent outcomes a week. This system generates a handful of
correlated, regime-dependent outcomes a month, and the market cannot be
re-run. A 4-case fixture gate here would be codified hindsight. Hence: minimum
n, resampled confidence bounds, bounded steps, cooldowns, and a strong bias
toward "no change."
