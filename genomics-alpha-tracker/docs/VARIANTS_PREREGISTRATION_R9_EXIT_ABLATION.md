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

## Addendum 1 — 2026-10-04, after the counter-agent's code review (BLOCK), before any run

Logged deviations from the original contract, each with its reason. The
rule, the metrics and the action bar are unchanged except where stated.

1. **`paper_arith` is removed from the knob list.** It is not a mechanism:
   with it on, the stored risk and entry short-circuit `risk_cap`,
   `cash_clip` and `integer_shares` (three forward arms were no-ops). The
   ablation base is **P0 = P with `paper_arith=False`** (lane fill, lane
   3×ATR risk with the paper's 0.5× cap, cash debited, fractional shares, no
   clip). The switch **P0 − P is reported as "basis"** and expected ≈ 0; the
   mechanics gap is **E − P0**. P itself stays as the reduction anchor
   (must equal `run_call_book`, asserted on the real data).
2. **`day_zero_stop` is defined as the executor's resting STP at the
   published level L0**: from the fill bar, the effective stop is
   max(L0, trail) and L0 is checked on the fill bar itself. Under the
   executor's own settings (fire-close seed, ratchet) this is identical to
   before; on the paper side it is now a real mechanism (it was a no-op).
3. **Eight knobs**: peak_seed, ratchet, day_zero_stop, risk_cap,
   time_stop_anchor, time_stop_fill, integer_shares, cash_clip. G_size =
   {risk_cap, integer_shares, cash_clip}. 22 arms (P, P0, 8 F, 8 B, 3 G, E).
4. **Sign-aware CI test**: the forward Sharpe-delta interval must lie on the
   gap's side (the sign of Sharpe_E − Sharpe_P0) and the backward interval
   on the opposite side; "excludes zero" alone is not enough.
5. **Multiplicity**: H14 (ratchet) is the single pre-registered primary and
   is tested at the uncorrected 95% level; the other seven knobs are
   exploratory and each verdict also reports whether it survives a
   Bonferroni-8 interval (p0.3125 / p99.6875 from the same draws). Group
   arms are descriptive.
6. **Where a knob lives**: peak_seed, time_stop_anchor, time_stop_fill are
   TRACKER-published; ratchet and day_zero_stop are EXECUTOR code
   (`ibkr-executor/app/blend.py`; the ratchet guard is also a data-bug
   safety); risk_cap is executor sizing; integer_shares and cash_clip are
   NOT actionable (whole shares, solvency). A proposal is emitted only for
   an actionable knob, and names where the change would land.
7. **Block-length sensitivity**: any knob that carries is re-tested with a
   63-day mean block; reported alongside.
8. **Reduction asserted on the real data**: P == the mirror's r2a_ref path
   (REDUCTION_TOL) and E's end value == the mirror results on disk
   (`exec_t1_nocost_nocarry`, $1) when that file is present; otherwise the
   study refuses to run (the bars would have changed under it).
9. **Honesty additions**: the paired CI is conditional on this single
   in-sample path and the fixed trade set (a few dozen divergent trades
   drive it); 21-day blocks overstate the effective sample for ~65-day
   trades; percentile intervals, not bias-corrected; B_cash_clip runs
   negative cash with no margin cost (uncosted leverage); uncapped risk
   uses the lane's ATR, the campaign's uncapped ATR is not stored.

## Addendum 2 — 2026-10-04, after the first host run, before the number of record is read

1. **Draw count.** The contract said 2,000 draws; the committed default was
   raised to 10,000 before any run (the Bonferroni-8 tail at p0.3125 rests
   on ~6 resamples at 2,000) and that is the number of record. A 4,000-draw
   CLI run was made first on the host because deploys kept killing the
   longer one; it is a PREVIEW. The seeded stationary bootstrap consumes one
   RNG stream, so the first 4,000 draws of the 10,000 run are the 4,000 run:
   the same sample extended, not a re-roll.
2. **Wording.** The paired interval is conditional on the fixed FIRE set
   (the trade set changes across arms through cap-slot turnover: 598 to 677
   taken); "taken" is the count handed to the book, not book entries.
3. **Max DD carries no interval** in this design; the 2 pp action bar is a
   single-path, single-episode point comparison, binding as registered.
