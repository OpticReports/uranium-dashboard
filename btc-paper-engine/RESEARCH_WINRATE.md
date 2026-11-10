# RESEARCH_WINRATE.md — can the S6 blend's win rate be pushed to 54–55%?

Question (Casey, 2026-08-17): top quant desks run 54–55% win rates; get S6
(or the general strategy) there for comfort. Study run on refetched Bitstamp
4h bars 2020-06 → 2026-08-17 (13,612 bars, gap-checked), trading window
2021-01 →, research basis (cash_apy 0, 6bp fees), engine code path untouched.
Script: `backend/scripts/research_winrate.py` (pre-registration in docstring).

Reproduce: `python3 backend/scripts/fetch_bars.py bars.csv` regenerates the
dataset from Bitstamp (the CSV itself is not committed); then
`python3 backend/scripts/research_winrate.py bars.csv` and
`python3 backend/scripts/research_winrate_null.py bars.csv`. Verified
2026-08-24: both rerun to the identical table values.

## Headline answer

1. **S6 already sits in the zone on the full sample: 54.8%** (387 ingredient
   trades, 2021→2026). The discomfort is recent: 2024 printed 46.7%, 2025
   53.2%. Per-year n ≈ 60–80 → binomial SE ≈ 5.7pp — **every yearly
   deviation from 54.8% is inside one standard error.** The "win rate
   dropped" signal is mostly sampling noise on a stable process.
2. **No promotable rule found.** 12 pre-registered rules (chop/trend gates,
   donchian entry confirmation, stop-width), split-sample fit A=2021-23 /
   validate B=2024-26 both directions, promotion bar frozen up front
   (WR ≥ 54% on validation half AND MAR/mean-step not degraded AND beats a
   best-of-N random-gate null). **Zero of 12 passed.** Win rate and MAR
   traded against each other in every single case:

   | rule (validation half B) | WR | MAR | verdict |
   |---|---|---|---|
   | baseline S6 | 51.3% | 0.61 | — |
   | don breakout margin 0.25·ATR | **55.1%** | 0.27 | WR ✓, MAR gutted |
   | don 200d-aligned / don slope | **62.6%** | 0.45 | mix-shift: deletes the trend leg (11 trades/5.6y) |
   | wider stop 3.0·ATR | 52.4% | 0.26 | WR ✗ and MAR gutted |
   | ER chop q40 (pullback gate) | 48.9% | **1.18** | MAR ✓, WR *lower* |

3. **The selection-noise null is the referee and it kills everything.**
   Two null bases, converging: (a) trade-list 30-day block gates matched to
   each rule's drop fraction — best-of-N q95 = +6.4pp WR; the best real WR
   gain (+3.8pp, D2a) sits at that null's *median*; (b) the counter-agent's
   full-replay null (200 random pullback block-gates, matched drop) —
   best-of-12 B-half MAR median 1.24, q95 3.04, so the ER filter's 1.18 is
   the MEDIAN outcome of luck, **P(best-of-12 random ≥ 1.18) = 0.55**, and
   29% of purely random pullback-thinning beats baseline B MAR outright.
   (The WR bar itself was honest: random-gate B WR q95 = 52.5%, so 54% was
   a real hurdle — nothing legitimate got near it.) Mechanically, win rate
   is trivially manufacturable — dropping the whole donchian leg buys
   +11.3pp by pure mix arithmetic while destroying the diversifier that
   made 2022 survivable. That is the trap in targeting WR.
4. **Registered rule C1 (best-P + best-D combo) turned out degenerate**: no
   family member passed its own MAR-eligibility constraint on either fit
   half, so the combo was undefined per its spec; the counter-agent closed
   it with an unconstrained probe (P4+D2a) — fails both halves (B: WR
   53.3% vs bar 54.0, MAR 0.53 vs 0.61). Logged rather than silently
   dropped from the registered N.

## What this means for the 54–55% goal

- Measured the way the books measure it, **the strategy is already a
  54–55% system**. A committed target of "≥54% every year" is not
  achievable at n≈70 trades/year by any honest strategy at this trade
  frequency — the binomial noise floor alone is ±5.7pp.
- The blend's WR is a **composition fact**: pullback leg 65.4% (n=234),
  donchian leg 38.6% (n=153, avg winner +10.7% vs avg loser −4.5% — low WR
  is what a trend leg IS). Any dial that raises blend WR materially works
  by shrinking the donchian leg, and pays for it in MAR and crash
  convexity.
- **Win rate is the wrong lever for comfort; drawdown is the right one —
  but this study produced no drawdown lead either.** The ER chop filter
  (the RESEARCH_5Y queue hypothesis) *lowers* WR while nearly doubling
  2024-26 MAR (1.18 vs 0.61, maxDD −20.6% vs −28.3%) — and the
  counter-agent's null shows that MAR gain is **consistent with selection
  noise (best-of-12 random-gate median 1.24, p ≈ 0.55)**: thinning
  pullback trades in the weak half improves MAR mechanically, signal or
  not. Per its verdict this is NOT a lead worth a follow-up study on this
  data — same shape as the RESEARCH_SWITCH round-1 lesson. The chop-filter
  hypothesis stays on the queue only in its live-shadow-log form.

## Counter-agent panel

Adversarial audit run before these findings were presented; overall
verdict **CONFIRMED** (negative conclusion sound, reproducible, leak-free).

| lens | verdict | key finding |
|---|---|---|
| Timestamp/look-ahead (truncation test: every gate recomputed from `bars[:i+1]` at sampled i) | **PASS** — max abs error 0.0 across ER/SLOPE50/ADX/SMA/ATR/HI20/LO20 | gates knowable at the signal bar's close; the exit_ts trap from the retracted switch study cannot arise (gates key off signal bars, not exits) |
| Harness equivalence | **PASS** — ungated loop bit-identical to `run_replay` on all 234+153 trades, all fields; books independent; engine files unmodified; 27 tests pass | one caveat: half-B MAR restarts the curve at 1.0 — like-for-like across rules, not comparable to FULL MAR |
| Gate semantics (D2a: 1,108 signal bars re-checked, 0 violations; P1b, D1 spot-verified) | **PASS** | dropped entries independently confirmed below threshold |
| Stop-width mechanics (E1/E2) | **PASS** — S4 untouched, S3 sizing invariant (dev ≤2.5e-07), stop distances exact | modified tcfg flows consistently |
| Data integrity | **PASS** — 13,612 bars, all diffs exactly 14,400s, 0 OHLC violations | |
| Statistical / selection | **PASS with findings** — every rule fails the bar under the most generous reading; C1 degenerate (closed by probe); registered null was not in the study script (run post-hoc, twice, both bases agree); ER-q40 by-product = median of luck (p ≈ 0.55) | |

## Honesty box

- Same engine semantics as §6 acceptance; research fee basis; blend rows
  are exit-step (MTM runs ~1-4pp deeper). Half-B MAR baselines are
  noise-dominated (29% of purely random pullback-thinning beats baseline
  B MAR) — treat all half-B MAR readings as low-signal.
- Process deviation, logged per the audit: promotion-bar guard 5 (the
  random-gate null) was registered in the docstring but implemented in a
  separate script (`research_winrate_null.py`) after the rule runs, not
  inside the study script; the counter-agent independently re-ran it on
  the full replay harness. Both bases agree and guard 5 was never
  load-bearing (guards 1-4 already rejected every rule).
- 2021-23 half overlaps years the rules were validated on (2024-26 was the
  selection window for the original configs) — neither half is pristine.
- Not modeled: funding, slippage beyond the decoded fee model, venue
  differences vs Coinbase execution.
- NOTHING from this study changes any config, sizing, or the live plan
  (S5, KELLY_M ramp per EXECUTOR.md). Negative result, recorded to stop
  future re-derivation.
