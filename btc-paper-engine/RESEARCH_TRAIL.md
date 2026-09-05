# RESEARCH_TRAIL.md — is S4's 5.0×ATR chandelier trail a plateau or a spike?

> **STATUS: PRE-REVIEW.** The mandatory counter-agent panel (harness
> fidelity, null validity, selection accounting, live-risk reading) is still
> running as of this commit. Nothing below has been acted on or presented as
> verified; the claims under attack are frozen in `research/trail/CLAIMS.md`.
> This section is replaced by the panel's verdicts when they land.

Diagnostic run 2026-09-05 on Bitstamp 4h bars 2020-06 → 2026-08 (13,666 bars),
research basis (cash_apy 0, 6bp/side, engine code path untouched), blend =
75% pullback (S3) + 25% donchian (S4) at 2.0×, exit-step curves. Grid, windows
and decision rule fixed in `research/trail/PREREG.md`, **committed before the
first cell was evaluated**. Scripts: `research/trail/`.

Harness validated first: at trail=5.00 on the HL window this harness
reproduces `backend/scripts/bench_blend.py`'s committed `3.3y-full-HL S6` row
exactly — CAGR 28.9%, maxDD −28.3%, MAR 1.02.

## Headline

**No change. The trail multiple is not a lever on this data, and the sweep
that looks for one buys less than picking trades at random.**

| pre-registered criterion | bar | measured | |
|---|---|---|---|
| C1 · 5.0's MAR vs grid max (2022→) | ≥80% | **100%** (5.0 IS the argmax) | pass |
| C2 · 4.0–6.0 spread vs full grid spread | <25% | **62.3%** | fail |
| C3 · Spearman of dose curve, 2022-24H1 vs 2024H2→ | ≥0 | **−0.064** | fail |

**Registered verdict: INDETERMINATE.** Not ROBUST (C2, C3 fail); not FRAGILE
(that needed C1 to fail, and 5.0 is the top cell). Reported as registered
rather than rounded to whichever word the charts suggest.

## What actually moved the numbers — a kill switch, not a trail

S4 carries `dd_halt=0.50`. **It fires in 13 of the 21 grid cells** on the
2022→ window. Cells 5.25–6.25 all die in April 2025 and never trade again;
2.00–3.25 die earlier. The live 5.00 does not halt. So the registered dose
curve is substantially a map of which settings tripped a −50% book halt.

Re-running with the halt disabled (**post-hoc — not pre-registered, and not
used to rescue any failed criterion**) gives the clean picture:

- a cliff at the tight end — 2.00×ATR takes the blend to MAR ≈ 0.00;
- a **plateau from ~2.75 to 7.00**, MAR 1.02–1.54, no interior structure;
- the argmax wanders by window: 4.50 (2022-24H1), 5.00 (2022→ and 2024H2→),
  7.00 (2023-05→).

The decision the parameter encodes is "wide enough that the trail doesn't
knife trend trades," not "5.0 exactly."

## The nulls, which are the referee

1. **30-day calendar-block bootstrap, 2,000 draws, all 21 cells resampled on
   the same draw.** The incumbent's +0.419 MAR lift over the grid median is
   exceeded by a *random* best-of-21 lift in **75%** of draws. "5.00 is the
   argmax" carries no evidential weight.
2. **Same bootstrap, second reading — and this one is mildly reassuring.**
   5.00 is the argmax in 23% of draws (uniform would be 4.8%), median rank
   **4 of 21**, top-5 in 64%, bottom half in 14%. It is a dependable plateau
   member; it is not a demonstrable optimum.
3. **Matched random thinning (21 arbitrary variants per rep, 500 reps).**
   Randomly deleting trend-leg trades to span the same trade counts the trail
   grid spans produces a best-of-21 MAR that beats the **entire trail grid's
   maximum in 100% of reps** (median 2.012 vs the grid's best 1.537), and a
   best-of-21 lift that beats the trail sweep's in 80%. Whatever the sweep is
   measuring, it is worse than noise at it.
4. **Placebo 2a was degenerate and is reported as such.** The registered
   placebo swept the pullback's `time_stop_bars`; it produced exactly zero
   lift because 13 of its 21 cells are identical — the time stop stops
   binding at 55 bars. That is a finding about the time stop, not a null.

## Honesty box

- **`modern` (2022→) is partly in-sample for the parameter under test.**
  RESEARCH_S4.md's original selection used VALIDATE = 2022-24H1, which is
  most of `modern_A`. The only genuinely out-of-sample half is
  **`modern_B` (2024-07→)** — where 5.00 is also the top cell, on 65 S4
  trades. That is the single strongest fact in the study, and 65 trades is
  not much.
- The `modern` and `hl` windows **overlap**, so their +0.73 rank correlation
  is not independent corroboration.
- Exit-step (trade-close) basis throughout; MTM drawdowns run 1–4pp deeper.
- Trial count: 63 configs evaluated (21 registered + 21 post-hoc + 21
  placebo), logged in RESEARCH_PROTOCOL §1. The pre-registration declared 21;
  the larger number is the honest one.
- **Not modeled**: funding, slippage, the live executor's stop placement.
  A wider chandelier is a more distant resting stop, which is a different
  fill-risk object live than in a bar-replay.

## What is forwardable

1. **Nothing to change.** RESEARCH_PROTOCOL §7 bars adopting an
   exit-parameter change while the live gate is open, and the nulls say the
   parameter is not a lever anyway. Do not re-run this sweep to "optimize"
   the trail; §7 aside, null 3 shows that exercise underperforms coin flips.
2. **S4 nearly killed itself in April 2025 at the live setting.** Its book
   drawdown came close enough to the −50% `dd_halt` that neighbouring
   settings tripped it. If it ever does trip, S6 becomes a pure pullback book
   with no diversifier.
3. **`time_stop_bars = 60` is inert on the modern era** — no pullback trade
   runs long enough to reach it. Dead parameter; it is neither helping nor
   hurting, and any future study that sweeps it is wasting trials.
