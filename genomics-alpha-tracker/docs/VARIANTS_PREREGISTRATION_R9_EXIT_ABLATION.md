# Pre-registration — ROUND 9, exit-rule ablation (executor mirror vs paper R2-A)

Committed BEFORE any round-9 code exists (the commit hash of this file
precedes the ablation code). Nothing here is a live change; the output is a
proposal for the TRACKER's published levels, or a null.

## Question

The executor-mirror replay (docs/BACKTEST_EXECUTOR_MIRROR.md, 2026-10-04)
measured a −5.55 pp CAGR / −0.20 Sharpe "mechanics" gap between the
executor's rules with no costs and no carry (`exec_t1_nocost_nocarry`) and
the paper R2-A recipe (`r2a_ref`), on the same bars, same fires, same gate,
same cap. The counter-agent established that this is a RULE MISMATCH inside
our own stack: the executor obeys the tracker's published shadow levels
(`app/calls/shadow.py grade_trailing`: fire-close peak seed, ratchet-up-only
trail, day-zero stop at the published level, deadline = fire + 90 d, exit at
the next open), while the campaign's grader (`backtest_variants_10y.
grade_trailing`, reused by `build_trailing_rows`) seeds the peak at the
entry close, has no entry-bar stop, lets the trail fall when ATR expands,
and the paper book sizes with fractional shares, no cash clip and a 0.5×
entry risk cap. WHICH knob carries the gap is unknown. This round measures
it.

**Hypothesis (H14, proposed):** the ratchet-up-only trail carries the
majority of the mechanics gap; the day-zero stop and the fire-close peak
seed are second-order; sizing knobs (whole shares, cash clip, risk cap) are
third-order. Prior written before the run: ratchet ≥ 50% of the gap.

## Knobs (ExecCfg fields; paper value → executor value)

| knob | paper (R2A_MODE) | executor (EXEC_T1, mechanics only) |
|---|---|---|
| peak_seed | entry_close | fire_close |
| ratchet | False (trail may fall) | True (up only) |
| day_zero_stop | False | True |
| risk_cap | 0.5 × entry | None (uncapped 3×ATR) |
| time_stop_anchor | entry | fire |
| time_stop_fill | deadline_close | next_open |
| integer_shares | False | True |
| cash_clip | False | True |
| paper_arith | True (stored entry/risk) | False (lane fill, recomputed risk) |

Costs none, BIL order cost off, carry off, entry lag 1, sleeve target 1.0 on
every arm. Gate and cap identical to the mirror (XBI > 200dma prior close;
cap 10, slot held from the gate date).

## Arms

- **P** paper: R2A_MODE through `run_executor_book` (reduces to run_call_book
  to 1e-10, machinery check 2).
- **F_k** (forward, 9 arms): P with ONE knob flipped to the executor value.
- **B_k** (backward, 9 arms): E with ONE knob flipped back to the paper value.
- **G_stop** = P + {peak_seed, ratchet, day_zero_stop}; **G_time** = P +
  {time_stop_anchor, time_stop_fill}; **G_size** = P + {risk_cap,
  integer_shares, cash_clip, paper_arith}.
- **E** executor mechanics only (all knobs flipped) = `exec_t1_nocost_nocarry`.

23 arms, one run each, deterministic.

## Metrics, fixed now

Full window 2016-01-04 → 2026-08-19 and the house sub-periods (2016-2019,
2020-2022, 2023-2026): end value, CAGR, max DD, Sharpe (rf = 0, √252),
Calmar, n_taken. Per arm:

- **gap share** (forward arms): (CAGR_F − CAGR_P) / (CAGR_E − CAGR_P).
- **recovery share** (backward arms): (CAGR_B − CAGR_E) / (CAGR_P − CAGR_E).
- **paired stationary block bootstrap** (mean block 21 d, 2,000 draws, seed
  20261004, identical block draws for arm and base) of the Sharpe
  DIFFERENCE vs the arm's base (P for forward, E for backward): p2.5 / p50 /
  p97.5.

**A knob CARRIES the gap** when all four hold: forward gap share ≥ 0.50;
backward recovery share ≥ 0.50; the paired-bootstrap 95% interval of the
Sharpe delta excludes zero in BOTH directions; the sign of the CAGR delta
holds in ≥ 2 of 3 sub-periods. Shares can sum to more or less than 1
(interactions); the group arms show the interaction.

**Action bar** (a PROPOSAL only, never a change from this study): a change
to the tracker's published levels is proposed for a knob that carries the
gap AND whose backward flip leaves the full-window max DD no more than 2 pp
worse than E's. Anything else is a null and is reported as one.

## Honesty (carried verbatim into the results)

- In-sample: the exit rule is being selected on the same history the engine
  was selected on; R3-F showed the trail × time-stop map is not a plateau.
  A winner here is a hypothesis for the live shadow record, not a result.
- The bars are the FMP dividend-adjusted lane, not the August campaign cache
  (R2-A +9% end value on this lane, one cap flip); all arms share the lane,
  so the deltas are internally consistent, the absolute levels are not the
  R2/R3 docs'.
- Deltas below the lane-drift noise floor (~0.8 pp CAGR) are not robust.
- Survivor universe, hindsight tiers, costs and carry deliberately OFF (this
  measures rules, not economics).
- Never present these in-sample CAGRs as a forecast.

## Mandatory

Counter-agent review of the code before it runs and of the results before
they are presented; verdicts logged in docs/BACKTEST_EXECUTOR_MIRROR.md.
