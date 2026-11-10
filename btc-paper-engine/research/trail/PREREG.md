# PRE-REGISTRATION — S4 chandelier-trail robustness (registered 2026-09-05, BEFORE any run)

Written and committed before a single grid cell was evaluated. Nothing below
is edited after results are seen; results live in `RESEARCH_TRAIL.md`.

## Provenance of the question

The 2026-07 strategy lab (RESEARCH_S4.md) picked **Donchian-20 + 5.0xATR
chandelier trail** out of a 9-config F1 family, fit on TRAIN 2013-2021 and
VALIDATE 2022-24H1, holdout touched once. So the trail multiple *was*
selected — on an era whose regime (violent sustained trends, thin book) the
same document argues is a different instrument from modern BTC. The open
question is not "what is the best trail?" but:

> **Is 5.0 sitting on a plateau or on a spike?**

A parameter that only works at its fitted value, with materially worse
neighbours, is a fitted artifact. One whose neighbourhood is flat is a
structural choice that happens to be parameterised.

## HYPOTHESIS

H0 (the one we expect to fail to reject): S6 blend performance is
**insensitive** to S4's trail multiple over a wide neighbourhood of 5.0,
because (a) S4 carries only 25% of the blend's risk weight, and (b) a
chandelier trail at 4-6 ATR is far enough from price that the exact multiple
changes the exit bar, not the exit regime.

H1: the dose curve is peaked, and 5.0's modern-era MAR is materially below
the grid's best — i.e. the 2013-2021 fit does not transfer.

**Economic rationale (protocol §3, required before running):** none is
claimed, because no new edge is claimed. This is a robustness diagnostic on
an already-adopted parameter, not a candidate.

## TRIALS THIS BATCH

- 21 trail multiples: 2.0 → 7.0 step 0.25 (5.0 is a grid point).
- Evaluated on 4 pre-declared windows (see below). Windows are *evaluation*,
  not selection: no window picks a winner, so the trial count is **21**.
- Null calibration runs are not trials (they evaluate no candidate).

Add 21 to RESEARCH_PROTOCOL.md §1 on completion regardless of outcome.

## WINDOWS (fixed now)

| tag | span | role |
|---|---|---|
| `modern` | 2022-01-01 → last bar | protocol §4 primary objective window |
| `hl` | 2023-05-12 → last bar | the window S5/S6 bench numbers are quoted on |
| `modern_A` | 2022-01-01 → 2024-06-30 | stability half 1 |
| `modern_B` | 2024-07-01 → last bar | stability half 2 |

Basis: research convention — `run_replay` with `cash_apy=0`, 6 bps/side,
engine code path untouched, exit-step (trade-close) curves, blend =
75% S3 + 25% S4 at 2.0x, exactly `backend/scripts/bench_blend.py`'s
construction. Harness must reproduce the committed S6 bench numbers at
trail=5.0 before any other cell is read; if it does not, the study is void.

## DECISION RULE (fixed before running)

**This study cannot adopt anything.** RESEARCH_PROTOCOL §7's stopping rule —
"signal-space search is CLOSED until the live gate concludes (15-20 fresh
trades)" — is in force, and an exit-parameter sweep is signal-space search.
The only outputs permitted are a *verdict* and, if warranted, a queued item
for after the gate.

Verdicts, decided by these thresholds and no others:

- **ROBUST** iff ALL of:
  1. On `modern`, S6 MAR at trail=5.0 ≥ 80% of the grid max MAR.
  2. The neighbourhood 4.0-6.0 spans < 25% of the full grid's MAR range on
     `modern` (flat locally relative to globally).
  3. Spearman rank correlation of the S6 MAR dose curve between `modern_A`
     and `modern_B` is ≥ 0 (the ordering is not sign-flipping across halves).
- **FRAGILE** iff (1) fails, i.e. 5.0 is below 80% of the grid max on
  `modern`, AND the local neighbourhood is steep (2 fails).
- **INDETERMINATE** otherwise — reported as such, not rounded to a verdict.

If FRAGILE: the output is a single queued line in RESEARCH_PROTOCOL §9,
"re-examine S4 trail after the live gate concludes", with the measured
numbers. **No config change, no PR to `RESEARCH_BOOKS`, no live change.**

## NULL CALIBRATION (design fixed now)

The grid max is a best-of-21 statistic on highly correlated variants, so it
is biased upward even under H0. Two nulls:

1. **Stationary block bootstrap over the blend's trade sequence** (mean block
   ~10 exits, 2,000 resamples): resample the *shared* event stream so every
   grid cell sees the same resample, then record the distribution of
   `MAR(grid max) - MAR(trail=5.0)`. If the observed gap sits inside that
   distribution's bulk, the gap is resampling noise, not tuning signal.
2. **Placebo grid**: sweep an exit parameter that should NOT matter in the
   same way — the pullback book's `time_stop_bars` (60) over an equally sized
   21-point grid — and compare the best-of-21 lift. A placebo lift as large
   as the trail's means the sweep is measuring search width, not the trail.

## WHAT WOULD FALSIFY THE STUDY ITSELF

- Harness fails to reproduce committed S6 bench stats at trail=5.0 → void.
- Fewer than 30 S4 trades in any window used for a verdict → that window is
  reported as underpowered and excluded from the verdict, not averaged in.
- MAR undefined (max DD shallower than 0.5%) in any cell → cell reported as
  n/a, not imputed.

## COUNTER-AGENT

Mandatory per CLAUDE.md before any finding is presented. Lenses: harness
fidelity, null validity, selection accounting, protocol §7 compliance.
