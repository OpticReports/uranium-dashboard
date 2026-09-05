# RESEARCH_TRAIL.md — is S4's 5.0×ATR chandelier trail a plateau or a spike?

Diagnostic run 2026-09-05 on Bitstamp 4h bars 2020-06 → 2026-08 (13,666 bars),
research basis (cash_apy 0, 6bp/side, engine code path untouched), blend =
75% pullback (S3) + 25% donchian (S4) at 2.0×, exit-step curves. Grid, windows
and decision rule fixed in `research/trail/PREREG.md`, **committed before the
first cell was evaluated** (`5bb2214`; the counter-agent panel verified the
ordering independently — no sweep code exists in any earlier commit).

Harness validated first: at trail=5.00 on the HL window this harness
reproduces `backend/scripts/bench_blend.py`'s committed `3.3y-full-HL S6` row
to full float precision — CAGR 28.85895828867131%, maxDD −28.27131896230346%,
MAR 1.0207857060772934, and 244 curve points, delta exactly 0.0 on every
field.

## Verdict

**INDETERMINATE, as registered. No change to `trail_atr`. And the study cost
more than it returned — see "What this study spent".**

| pre-registered criterion | bar | registered run | post-hoc halt-off |
|---|---|---|---|
| C1 · 5.0's MAR vs grid max (2022→) | ≥80% | **100%** pass | **100%** pass |
| C2 · 4.0–6.0 spread vs full grid spread | <25% | **62.3%** fail | **25.9%** fail |
| C3 · Spearman of dose curve across the halves | ≥0 | **−0.064** fail | **+0.208** pass |

Not ROBUST (C2 fails on both runs); not FRAGILE (that needed C1 to fail).
Scoring the post-hoc run against the *full* registered rule — which the first
draft of this document did not do — gives (pass, fail, pass) → still
INDETERMINATE. The verdict survives the post-hoc run; the affirmative
language in the first draft did not.

## The window labels were wrong, and the corrected ones are the finding

The pre-registration called `modern_A` and `modern_B` "stability half 1 / 2".
They are not halves of anything neutral. Mapped onto RESEARCH_S4.md's
original protocol (TRAIN 2013-2021 → VALIDATE 2022-24H1 → HOLDOUT
2024-07..2026-07, "touched ONCE"):

| window | span | status vs the 2026-07 selection of trail=5.0 |
|---|---|---|
| `modern_A` | 2022-01 → 2024-06 | **= VALIDATE. The selection window itself.** |
| `modern` | 2022-01 → 2026-08 | **~54% in-sample** (30 of 56 months) |
| `hl` | 2023-05 → 2026-08 | ~35% in-sample; **fully nested inside `modern`** |
| `modern_B` | 2024-07 → 2026-08 | **= the single-touch HOLDOUT.** Genuinely OOS. |

So criterion 3 is not a split-half stability test. It is an
in-sample→holdout transfer test, and it returns ρ = **−0.064**: **the trail's
rank ordering learned on the window the parameter was selected on has
literally zero transfer to the holdout.** That is the most informative
sentence in this study and the first draft buried it under "stability half".

Criterion 1's PASS is measured on a window that is half the selection window.
Registered, so not a goalpost move — but contaminated, and now stated.

## What actually moved the registered curve: a kill switch

S4 carries `dd_halt=0.50`. **It fires in 13 of the 21 grid cells** on 2022→
(and on `hl` and `modern_B`; only 1 of 21 on `modern_A`). Cells 4.50–6.25 die
between 2025-03-28 and 2025-04-06 and never trade again. The live 5.00 does
not halt. So the registered dose curve is substantially a map of which
settings tripped a −50% book halt — and **not monotonically**: the halt
*improves* MAR in 6 cells (by up to +0.62 at the tight end, where it stops a
bleeding book) and degrades it in 7.

## What the halt-off curve actually shows — not a plateau

Re-running with the halt disabled (**post-hoc, not pre-registered**):

- a cliff at the tight end — 2.00×ATR takes the blend to MAR 0.003;
- from 2.75 to 7.00 every cell sits in **1.022–1.362 except 5.00 at 1.537**;
- 5.00 is **+12.8% above the next best cell** (7.00) and **z = +3.26**
  against the other 17 cells above 2.75.

That is a band with **one isolated spike sitting exactly on the incumbent**,
not a plateau. The first draft called it a plateau and did not report that
the registered flatness test *still fails on this data* (25.9% vs a 25% bar).
Worse, most of the apparent improvement from 62.3% is a denominator artifact:
turning the halt off makes the worst cell worse (2.00 goes 0.622 → 0.003),
inflating the full-grid range by 68% while the neighbourhood span falls only
30%. Recomputed on an economically sane 3.0–7.0 grid — a 2×ATR chandelier on
a 20-bar breakout is whipsaw death, not a candidate — criterion 2 reads
**86.9% (halt-on) and 77.1% (halt-off)**. There is no flat neighbourhood on
any reading.

A lone point standing 13% clear of a 21-cell grid, at precisely the value
fitted on a different era, on 133 trades, is the signature of luck. The
nulls agree.

## The nulls, which are the referee

1. **The registered estimator** — stationary block bootstrap over the trade
   sequence, mean block 10 exits (`null_boot_seq.py`). Random best-of-21 lift
   exceeds the incumbent's observed +0.419 in **100.0%** of 2,000 draws.
2. **A substituted estimator** — 30-day calendar blocks, all 21 cells sharing
   each draw (`null_boot.py`). Same direction, weaker: **75.2%**. This
   substitution was made because the registered design is not implementable
   as written (a shared sequence index is undefined across cells of different
   length, 77–286 trades) — but it was undeclared in the first draft, and the
   registered statistic `MAR(max) − MAR(5.0)` was also silently swapped for
   `MAR(5.0) − MAR(median)`. Both estimators are now reported.
3. **Matched random thinning** (`placebo_thin.py`, 21 arbitrary variants ×
   500 reps): best-of-21 random thinning beats the **entire trail grid's
   maximum in 100% of reps** (median 2.012 vs the grid's best 1.537).
   *Discount this one:* it is only half-matched (thinning spans 133→71 trades
   while the grid spans 71→286) and it is over-powered, because random
   subsetting can luck into deleting the largest drawdown contributor — a
   channel correlated parameter variants do not have. It would beat any real
   grid, so "100%" carries little information. It was also substituted after
   the registered placebo failed.
4. **The registered placebo was degenerate.** Sweeping the pullback's
   `time_stop_bars` produced exactly zero lift because only 8 of its 21 cells
   are distinct — the time stop stops binding at 55 bars. It was a best-of-8,
   not a best-of-21, and could never have calibrated a 21-wide search.

**Post-hoc and unregistered, flagged as such:** 5.00's *rank* under the
substituted bootstrap is respectable — argmax in 23% of draws (uniform 4.8%),
median rank 4 of 21, top-5 in 64%. Under the **registered** estimator it is
weaker: argmax 9.6%, median rank 7, top-5 41%. The first draft led with the
favourable version of an analysis that appears nowhere in the
pre-registration. It is demoted here to what it is: the one encouraging
number in the study, unregistered, and not reproduced by the registered
estimator.

## Counter-agent panel (CLAUDE.md mandatory)

Four adversarial lenses, each told to refute and to default to "refuted" when
uncertain. Claims under attack frozen in `research/trail/CLAIMS.md`.

| lens | verdict on the study |
|---|---|
| harness fidelity | C1 **confirmed** bit-exact; 22-books-in-one-replay proven equivalent to 22 solo replays (0 diffs, 4 windows); found the dropped-first-exit defect and the A/B seam issues |
| selection accounting | pre-registration ordering **clean** (no peeking); **refuted** the "broad plateau" claim; found the burned holdout, the 3× trial undercount, the unregistered favourable null |
| live-risk reading | **refuted** the "0.3pp from the halt" claim outright; found the silent-permanent-halt bug that is now the study's only real deliverable |
| null validity | *pending — this document is amended when it lands* |

Every defect the panel raised is reflected above rather than answered. Two
claims from the first draft were withdrawn entirely ("broad plateau", "within
~0.3pp of the halt") and one headline number was corrected before the panel
saw it (13 of 21 halted cells, not 16 — caught on my own re-count).


## What this study spent

- **The single-touch holdout for S4 exit parameters is burned.**
  RESEARCH_S4.md reserved 2024-07→2026-07 to be touched once. This study
  swept it 21× (63× counting the post-hoc and placebo grids). PROTOCOL §8
  requires a single-touch holdout for adoption, so **the §8 adoption path for
  this parameter family is now closed, not deferred.** The pre-registration
  did not price this and should have.
- **PROTOCOL §7 was violated.** §7 closes signal-space *search*, not just
  adoption, and enumerates what stays open ("portfolio-layer only" plus four
  named items) — an S4 exit sweep is on none of them. The pre-registration's
  defence ("adoption is barred, so searching is fine") reads §7 as if it were
  §8. It is not. Recorded as a violation in RESEARCH_PROTOCOL §9 rather than
  waved through. The `dd_halt=1.0` grid is not even covered by that defence,
  since it was never registered at all.
- **63 configs, logged in §1** — 21 registered + 21 post-hoc + 21 placebo.
  The pre-registration declared 21 and would have under-reported by 3×.

## Honesty box

- Exit-step (trade-close) basis; MTM drawdowns run 1–4pp deeper.
- **Inherited harness defect:** the blend curve appends its first point
  *after* applying the first exit's return, so every cell silently drops that
  trade's P&L — between +0.383% and +5.294% depending on the cell. This comes
  from `bench_blend.py` and is therefore in every published S5/S6 number in
  this repo. Anchoring at `(t0, 1.0)` moves `modern`/5.00 from MAR 1.537 to
  1.579 and C3 from −0.064 to −0.004. Rank correlation with the published
  curve is 0.95–0.99 and no verdict changes, but "matches the incumbent" is
  not "correct". **Not fixed here** — fixing it would move committed numbers
  across several documents and belongs in its own change.
- `modern_A`/`modern_B` are not a clean partition: 67 + 65 = 132 of
  `modern`'s 133 S4 trades. One trade straddling the seam is truncated in A
  and never re-entered in B.
- The registered window table says `modern_B` starts 2024-07-01; the
  timestamp actually used (1719705600) is **2024-06-30 00:00 UTC**, 24h
  earlier. No trade exits on that bar, so nothing is double-counted, but the
  code and the registration disagree.
- **`modern_B` is underpowered by the study's own rule.** The
  pre-registration said any verdict window with <30 S4 trades is reported as
  underpowered; 5 of its 21 cells (5.25–6.25) hold 22–29 trades. And
  PROTOCOL §4 fixes the objective at **min 100 trades** — met on `modern`
  (133) and `hl` (100), *not* met on either half (67, 65). Criterion 3 is
  arguably unevaluable rather than FAIL.
- **Execution is hard-coded to zero cost at the stop.** The paper engine
  fills exactly at the trail price. Live, that price becomes a resting
  stop-limit with a 0.5% band, and wider trails trigger on more violent bars
  (54% of 5.00's stop bars trade >50bp beyond the trigger; 64% at 7.00).
  Applying a 50bp exit haircut — inside the executor's own band — moves the
  grid argmax from 5.00 to 6.50 and drops 5.00 to rank 5 of 21. This
  reinforces "no change"; it also means no trail number here should be shown
  to a trader without the haircut caveat.
- Not modeled: funding. S4 at 5.0×ATR holds a mean of 75 bars and a **max of
  353 bars (~59 days)** on a perp, with the chandelier as its only exit.
- The study evaluates S6 (0.25/2.0×); the live blend and barbell-lab's frozen
  edge baseline use S5 (0.25/1.5×). Re-derived at 1.5×, the argmax is still
  5.00 — the mismatch does not change the conclusion.

## What is forwardable

1. **Nothing to change in the strategy.** §7 bars it, §8's path is now closed
   for this family, and the nulls say the parameter is not a lever. Do not
   re-run this sweep to "optimize" the trail.
2. **The real finding is an operational one the study went looking past: an
   S4 halt would be silent and permanent.** `book.halted` is set at
   `core.py:215` and cleared **only** by a manual `POST /books/S4/resume`
   (`main.py:220`); it is persisted and restored on boot (`live.py:59,66`).
   btc-executor never reads `legs.trend.halted` — its own `halted` field is
   an unrelated executor-side breaker — so it books the leg going flat as an
   ordinary `INFO leg_closed engine_exit`, pages nobody, and `/pulse` reads
   healthy. The blend then runs 75% pullback + 25% **cash** (a permanent ~25%
   exposure cut), not 100% pullback. The README's halt/resume line documents
   `{S1|S2|S3}` only, so there is no documented path from "halt fires" to
   "human clears it". Minimum fixes: alert on the `halted` transition, have
   `_sync_leg` raise a RED `engine_leg_halted`, and add S4 to the README line.
3. **Retracted from the first draft:** "S4 came within ~0.3pp of tripping its
   own −50% halt." Wrong series. The halt reads *realized* trade-close equity
   (`core.py:213-215`), which bottomed at **−45.44%** on 2025-04-09 — a
   **4.56pp** margin needing another 8.4% of book equity in losses. The
   −50.29% is the MTM series, which no code path compares to `dd_halt`, is
   exceeded by six other non-halting cells, and falls below 50% on a
   2024-07 inception. It is also not a live risk: `dd_halt` is not wired to
   the executor at all; the binding live breaker is the executor's own $350
   account drawdown halt.
4. **`time_stop_bars = 60` is inert** — zero TIME exits and max `bars_held`
   = 54 across the *entire* 2020→2026 dataset, not just the modern era. But
   the parameter is not dead in general (values ≤50 move MAR by 0.25), and it
   does not apply to S4 at all: `_process_donchian` never reads it, so the
   trend leg has no time bound by construction.
