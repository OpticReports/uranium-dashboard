# PRE-REGISTRATION — does S3's edge survive the fee we actually pay?

**Registered 2026-09-10, BEFORE any corrected backtest was run.** Committed on
its own so the timestamp precedes every result. Nothing below may be edited
after the first run; corrections go in an amendment section with their own date.

Authorised by Casey 2026-09-10 ("do it all"). Trials declared: **14** (see §7).

## 1. The problem

`core.py` `_process_pullback` builds its `Position` without `fee_bps`, so S3
falls through to the dataclass default of **6.0 bps round trip**. That default
is *correct for the strategy as designed*: a maker entry costs 0 and a taker
exit costs `taker_fee_bps`. `_process_donchian` passes `2 * taker_fee_bps`
because it enters at market. Neither is a coding error.

The error is that the design assumption does not hold live.

## 2. What the live record says (measured 2026-09-10, n=17 fills)

Every fill on the account carries `crossed: true` and a fee of **exactly 4.32
bps**. Isolating the four fills that were *intended* to be post-only maker
entries on the pullback leg:

| entry | size | notional | fee bps | crossed |
|---|---|---|---|---|
| 2026-08-31 00:00:37 | 0.00195 | $151.36 | 4.32 | yes |
| 2026-09-01 16:01:10 | 0.00194 | $151.07 | 4.32 | yes |
| 2026-09-08 08:00:37 | 0.00193 | $151.24 | 4.32 | yes |
| 2026-09-09 16:00:37 | 0.02481 | $1,949.00 | 4.32 | yes |

**Four of four rested for zero seconds.** `hl.place_limit` sends `tif=Alo`, the
venue rejects it as marketable, and the except branch re-sends `tif=Gtc` with
the price rounded *into* the market. The maker entry is a taker fill every
time observed so far.

So the true round trip is **8.64 bps** (4.32 in + 4.32 out) against a modelled
6.00. Note this is the net of two errors pointing opposite ways: the model
gives the entry away free (understates by 4.32) and charges the exit at 6.0
when Hyperliquid charges 4.32 (overstates by 1.68).

**Stated limitation, not to be smoothed over: n = 4.** Four for four is
consistent with a rejection rate anywhere above roughly 40% at 95% confidence.
The point estimate is 100%; the study must not present it as established.

## 3. Hypotheses, fixed now

- **H1 (cost).** Charging S3 the live 8.64 bps instead of 6.00 reduces its
  net edge. Direction is arithmetic, not in question; the study measures
  magnitude on CAGR, MAR, win rate and max drawdown.
- **H2 (sizing).** The Kelly recommendation for S3/S5/S6 falls when re-fitted
  on corrected net returns. **This is the question that matters** — everything
  else is bookkeeping.
- **H3 (ladder).** The KELLY_M ladder 0.135 → 0.20 → 0.35 remains inside the
  drawdown-budget envelope after correction.

**Prior, recorded so it cannot be claimed retroactively:** H3 most likely
holds. KELLY.md's DD30-budget recommendation for S6 is 0.70x, and the whole
ladder tops out at 0.35 — half of it. A ~6% edge haircut is unlikely to close
a 2x gap. If that is how it lands, the honest conclusion is *"measured, small,
ladder unaffected"*, and saying so is a successful outcome, not a null result
to be talked up.

## 4. Method, fixed now

1. **Fee model.** Add an explicit `fee_bps` to `_process_pullback`'s
   `Position`, parameterised as `entry_taker_frac * taker + taker`, where
   `entry_taker_frac` is the share of entries that cross. Run the registered
   grid in §7. No other engine change.
2. **Windows.** The committed fixture `bars_4h_btcusd.csv`, warmup 210,
   `RESEARCH_BOOKS` / `RESEARCH_SIGNAL` / `RESEARCH_TRADE`. Full window
   2022-01-01 → end, plus the HL-era sub-window from 2023-05-12, declared now
   and not chosen after seeing results.
3. **Metrics.** Trade-close CAGR, mark-to-market max drawdown, MAR, win rate,
   profit factor, exit mix, final equity. MTM drawdown is reported alongside
   trade-close because the exit-only curve flatters DD.
4. **Kelly re-fit.** KELLY.md's published pipeline, unmodified: numeric argmax
   of g(m); stationary block bootstrap (Politis–Romano, mean block 10, 2000
   draws); recommendation = `min(half-Kelly, boot p10, c*·m*, m at the
   P(maxDD>30%) ≤ 10% budget)`; the >25% non-positive-resample kill rule.
   Same seed discipline, reported.

## 5. Decision rules, fixed now

| result | action |
|---|---|
| S6 recommended m stays above 0.35 | ladder proceeds unchanged; record the corrected numbers and move on |
| S6 recommended m lands between 0.20 and 0.35 | the 0.35 rung is retired; ladder stops at 0.20 pending live evidence |
| S6 recommended m lands below 0.20 | ladder is halted at 0.135 and the corrected edge goes to Casey as a sizing decision |
| the kill rule fires on S3 (>25% of resamples non-positive) | escalate immediately; this would put the whole pullback book in question, not just its size |

No action is taken on any result until the counter-agent pass in §6 clears it.

## 6. Verification, required before any conclusion is acted on

Adversarial counter-agent review per CLAUDE.md, covering at minimum: the fee
arithmetic, the bootstrap implementation, whether the corrected run differs
from baseline *only* through the fee channel, and whether any window or metric
drifted from what this document fixes.

## 7. Trials declared: 14

`entry_taker_frac` ∈ {0.00, 0.25, 0.50, 0.66, 0.75, 1.00} × {full, HL-era}
= 12, plus 2 baseline reruns at the current 6.0 bps to prove the harness
reproduces the committed numbers before anything is changed.

0.66 is included because it is the backtest-derived marketability estimate;
1.00 is the live observation. Both are declared so that whichever the report
leads with, the other was registered rather than discovered.

To be added to the §1 registry on completion, whatever the outcome. A
registered trial counts from registration, not from success.

## 8. What this study is NOT

- Not an execution fix. That the post-only never rests is a separate,
  actionable engineering question worth roughly $45/yr, tracked apart from
  this and not to be bundled into the conclusion.
- Not a re-optimisation. No parameter other than `fee_bps` may move. If the
  corrected edge looks poor, the answer is smaller size, never a re-tuned
  strategy fitted on the same window.
- Not out-of-sample. Every number will be in-sample on a fixture already used
  for ~2,491 prior trials, and per §2 of the protocol must be read as an
  **upper bound**.
