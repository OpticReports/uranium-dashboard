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

---

# AMENDMENT 1 — 2026-09-10, after the first counter-agent pass

Recorded under §7's own rule that corrections go in a dated amendment rather
than editing frozen text. Two deviations, one of them an error I introduced.

## A1.1 — the maker leg was priced at ZERO. It is 1.44 bps. (ERROR, corrected)

`run_grid.py` used `fee = frac * 4.32 + 4.32`, which charges the non-crossing
share nothing. Hyperliquid does charge it. Verified directly from `userFees`
on the live account:

```
userCrossRate 0.00045  ->  4.50 bps list  ->  4.32 after the 4% referral discount
userAddRate   0.00015  ->  1.50 bps list  ->  1.44 after the same discount
activeReferralDiscount 0.04
```

The 4.32 cross rate reproduces the fee on all 18 fills exactly, which is what
makes the 1.44 add rate credible: the same discount demonstrably applies.

Corrected parameterisation: `frac*4.32 + (1-frac)*1.44 + 4.32`.

| frac | as first run | corrected |
|---|---|---|
| 0.00 | 4.32 | **5.76** |
| 0.50 | 6.48 | 7.20 |
| 0.66 | 7.17 | **7.66** |
| 1.00 | 8.64 | 8.64 — unchanged |

**The headline arm is untouched.** The live regime is all-crossing, so frac=1
has no maker component and the 8.64 figure, the H1/H2/H3 results and the
ladder decision all stand. What moves is every `frac < 1` arm, which was
optimistic by `1.44 × (1-frac)`.

Two consequences beyond the grid, both of which pointed the flattering way:

- The old chart implied the shipped 6.00 model corresponds to ~39% of entries
  crossing. With maker priced correctly the equivalence is `(6.00-5.76)/2.88`
  ≈ **8%**. The shipped model is far more optimistic than the first chart made
  it look, which strengthens the study's own case rather than weakening it.
- §8's "$45/yr" for making post-only actually rest was computed against a
  0-bps counterfactual. The real saving is `4.32 − 1.44 = 2.88` bps, about
  **$30/yr** — and even that ignores that entries which then rest may never
  fill at all, a selection effect rather than a fee change.

## A1.2 — `TAKER` vs `HL_TAKER` (silent deviation from frozen text, now declared)

§4.1 registered the model as `entry_taker_frac * taker + taker`. Read
literally with the engine's own `RESEARCH_TRADE.taker_fee_bps = 6.0`, that is
a 6–12 bps grid. `run_grid.py` instead used the measured venue rate 4.32 for
both terms, leaving the 6.0 constant defined but unused.

The script's choice is the empirically correct one — 6.0 is a Coinbase-era
number and the venue demonstrably charges 4.32 — but it is a deviation from
frozen text that moved the answer in the flattering direction, and it went
undeclared until a reviewer found it. Declared here.

## A1.3 — 8.64 is the engine's convention, not the realised number

The engine charges the whole round trip on ENTRY notional. Hyperliquid charges
the exit on EXIT notional. Realised on the three completed live round trips:

| entry | realised round trip, on entry notional |
|---|---|
| E1 | 8.71 bps |
| E2 | 8.84 bps |
| E3 | 8.70 bps |
| notional-weighted | **8.75 bps** |

The bias is systematic: it understates for winners and overstates for losers,
and this book wins 63% with positive expectancy, so it nets an understatement.
Small (~0.11 bps to date) and it makes the study CONSERVATIVE, but the claim
should read "8.64 by the engine's convention; 8.75 realised to date".

## A1.4 — scope: three books were corrected, not one

S1 and S2 are also pullback books and also move across arms. Correct
behaviour, but `run_grid.py`'s docstring says "the PULLBACK book's Position"
in the singular and the framing reads as S3-only. The S4 donchian book is
bit-identical across all 14 arms, which is the isolation evidence.

## A1.5 — NOT fixed here, carried forward as separate work

The pullback fee is hard-wired to the `Position` dataclass default and does
not track config: `load_strategy()` accepts `trade.taker_fee_bps` from YAML,
and changing it moves the donchian book while every pullback book stays pinned
at 6.0. A third, independent fee expression lives at `replay.py`
`research_basis_stats` (flat `tcfg.taker_fee_bps` per trade, ignoring
`Position.fee_bps`), and `main.py` serves it to the API as `research_basis` —
still reporting the uncorrected number. Any real fix has to move all three
sites together. That is an engine change, out of scope for a measurement
study, and it is not being smuggled in here.

## A1.6 — an unmeasured offset, flagged rather than modelled

A post-only rejected as marketable retries as a crossing limit and fills at
the ask, which is at or inside our limit, while the engine books the entry at
exactly the limit. So the live entry PRICE is weakly better than modelled,
partly offsetting the 4.32. Sizing it needs the live engine's pending limit
for those four `signal_ts`, which we do not have. Per CLAUDE.md that is an
input to request, not to model around, so the study does not estimate it and
the reported cost is an upper bound on the fee channel alone.

---

# AMENDMENT 2 — 2026-09-10, after the second counter-agent pass

This one overturns the first cut's headline. Recorded in full because the
conclusion I initially reached was wrong, and the way it was wrong is the
interesting part.

## A2.1 — the Kelly WINDOW and `cash_apy` were never pre-registered

§4.4 fixed the Kelly *pipeline* and §4.2 fixed the *replay* window, but the
Kelly re-fit silently inherited one window (full, 2022-) and one cash setting
(`cash_apy=0.0`) without either being declared. I then reported that single
cell's answer as though it were the answer.

Declared retroactively, and reported in full below: **{2y, full} × {cash_apy
0.04, 0.00}**. 2y = `last_bar - 730d`; 0.04 is `settings.cash_apy`, the value
KELLY.md's own `/kelly/compare` endpoint uses.

## A2.2 — "different window" was the WRONG explanation for 0.59 vs 0.70

The first cut explained the gap from KELLY.md's published S6 of 0.70 as a
window difference. That is not what it is. Decomposed:

| step | S6 rec |
|---|---|
| 2y, cash 0.04, shipped steps — **KELLY.md's config** | 0.70 |
| same window, cash **0.00** | 0.36 |
| full window, cash 0.00 | 0.60 |
| full window, cash 0.00, first cut's own blend steps | 0.59 |

`cash_apy` moves S6 by **−0.34 on the same window**; the window moves it back
**+0.24**; the dropped blend step takes another −0.01. They happen to net to
the −0.11 I attributed wholly to "window". A near-cancellation of two large
effects is not a window difference, and calling it one was exactly the
papering-over the verification exists to catch.

**Mechanism.** Per-trade streams are immune to idle-cash accrual, which lands
between trades. Blend steps are built from `equity_after / start_equity`, so
they DO capture it in the gaps. KELLY.md's S5/S6 therefore carry a 4% cash
yield that its own S1–S4 rows do not. That is a shipped-pipeline
inconsistency, inherited here and now named.

## A2.3 — the blend steps were not the shipped ones

The first cut rebuilt blend steps from `bench_blend.blend_curve`'s NAV as
`nav[i]/nav[i-1]-1`, which silently drops the first step (n=317 vs the shipped
318), and the dropped element was favourable. `refit_kelly.py` now uses the
function that actually produced KELLY.md, replicated verbatim from
`main.py:501-513` (it is nested inside the endpoint and cannot be imported).

**Harness validation, which §7 asked for and the first cut never did:** the
2y/cash0.04 cell now reproduces KELLY.md's published table exactly —
S3 0.60, S4 killed at 0.00, S6 0.70, n = 88 / 58 / 146.

## A2.4 — THE RESULT: four cells, and they disagree

| cell | n | baseline | fee-corrected | fee effect | §5 decision |
|---|---:|---:|---:|---:|---|
| 2y, cash 0.04 | 146 | 0.70 | 0.59 | −15.7% | proceed unchanged |
| **2y, cash 0.00** | 146 | 0.36 | **0.22** | **−38.9%** | **retire the 0.35 rung** |
| full, cash 0.04 | 318 | 0.63 | 0.62 | −1.6% | proceed unchanged |
| full, cash 0.00 | 318 | 0.60 | 0.58 | −3.3% | proceed unchanged |

The fee effect is **not window-stable**: −1.6% to −38.9% depending on
specification. The first cut reported −3.4% as if it were a property of the
correction. It is a property of one cell.

## A2.5 — which cell governs, and why the conservative one wins

Three of four cells say proceed; one says retire the 0.35 rung. That is not a
vote. Two things break the tie, both pointing the same way:

1. `cash_apy=0.00` is the more defensible setting, not the flattering one.
   It is `run_replay`'s default and the research-basis convention, and per
   A2.2 the 0.04 variants credit the blend with a cash yield the single books
   never get — an inconsistency, not a feature.
2. KELLY.md's own doctrine: *"over-betting destroys growth faster than
   under-betting gives it up (the g-curve is asymmetric), so the conservative
   envelope is the honest size."* When defensible specifications disagree
   about size, the smaller one governs. That rule is already in the repo and
   it was written for exactly this situation.

**Binding number: 0.22.** The 0.135 → 0.20 step clears in every cell. The
0.35 rung does not clear the conservative cell and is retired pending live
evidence.

Stated plainly: this REVERSES the first cut's "ladder proceeds unchanged".

## A2.6 — not fixed, said out loud

The S5/S6 corrected numbers still charge the donchian leg 12.0 bps while the
venue charges 4.32 taker. In scope per §8 (only `fee_bps` may move), and it
biases the blends CONSERVATIVE, but it means the blend rows are not a clean
"live fee" measurement. A full-venue-fee blend is separate work.
