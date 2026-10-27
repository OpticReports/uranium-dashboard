# Pre-registration — ROUND 10, sleeve sizing (does the 30% sleeve sit idle?)

Committed BEFORE any round-10 code exists. Nothing here is a live change;
the output is a proposal for the tracker's published `risk_frac` (or a
sizing mode the executor would have to implement), or a null.

## Question (Casey, 2026-10-05)

"That would need a lot of active positions to fill the total 30%, so much
of that cash is sitting around doing nothing? Would it be better to
dynamically increase or decrease the trade size of the 30% sleeve based on
how many open trades there are, or a better way to manage the cash?"

Facts the question rests on: the sleeve sizes each entry at `risk_frac` =
1% of sleeve equity divided by the distance to the 3-ATR trail (≈ 10–15% of
price), so one position is ≈ 7–10% of the sleeve in notional; the cap is
10 open; the live book holds 4 positions ≈ 26% of the sleeve; idle sleeve
cash is in BIL (the R3-A carry). The replay never reported the sleeve's
deployed fraction. This round MEASURES it and tests the sizing levers.

## Hypotheses

* **H15a (deployment):** the live 30/70 rules keep the sleeve well under
  full deployment on average (prior: 20–40% of sleeve notional in open
  positions, 10-slot cap reached on a small minority of days).
* **H15b (uniform risk):** raising `risk_frac` raises sleeve CAGR and max
  drawdown together, with no Sharpe improvement that survives the paired
  bootstrap (sizing is a leverage dial, not an edge).
* **H15c (dynamic sizing):** sizing by free slots (bigger trades when few
  are open) does NOT improve Sharpe: open count is a regime signal (few
  fires = quiet or gated regimes), so inverse-occupancy sizing concentrates
  risk exactly when the signal set is thin, and the paired interval will
  not exclude zero on the positive side.

## Arms (all on the executor path: T+2 fill, IBKR costs, BIL carry, the
live cap of 10, the XBI gate; book = 30/70 with the 5pp band, as the live
book runs; the sleeve-only series is reported alongside)

| arm | sizing | risk per entry |
|---|---|---|
| S0 | risk (anchor; the live rule) | 1.0% of sleeve equity |
| S1 | risk | 1.5% |
| S2 | risk | 2.0% |
| S3 | risk | 3.0% |
| D1 | slot-fill: notional = spendable sleeve cash ÷ (10 − open) at entry | implied |
| D2 | inverse-occupancy: risk = clamp(1% × 10 ÷ (open + 1), 1%, 3%) | 1–3% |

Whole shares and the cash clip apply to every arm (the executor's rules).
Two capital bases: the replay's $100,000 book, and the LIVE book after the
deposit ($120,000; a $36,000 sleeve) so whole-share rounding is visible.

## Metrics (per arm, per base; full 2016-01-04 → 2026-08-19 and the mirror's
5y / 2y trailing windows)

Book level (30/70): CAGR, Sharpe, max DD, longest underwater. Sleeve level:
the same, plus **average deployed fraction** (1 − sleeve cash ÷ sleeve
equity, daily mean and p10/p50/p90), **share of days at ≥ 9 open**, entries
taken, `skipped_zero_qty`, and the worst single trade as % of sleeve equity
at entry. Primary statistic: the paired stationary block bootstrap of the
book-level Sharpe DIFFERENCE vs S0 (the round-9 construction: identical
block draws for both series, 10,000 draws, mean block 21 days, seed
20261005; Bonferroni family = 5 arms; 63-day block sensitivity reported).

## Decision rule (fixed now)

Propose a sizing change ONLY if, for that arm, all of: (1) the Bonferroni
interval of the book-level Sharpe delta vs S0 lies entirely above zero;
(2) the arm's book max DD is no more than 2 pp worse than S0; (3) the sign
of the Sharpe delta holds in the 5y window. Otherwise the answer is NULL:
keep 1%, and the idle sleeve cash is the carry by design. A positive CAGR
delta with a wider drawdown is reported as leverage, not improvement.

## What this cannot tell us (honesty, carried into the results)

In-sample over the same 10.6 years as every prior round; the fire set is
the tracker's (survivor-shaped universe); the fire rate (≈ 9/month live) is
taken as given, so an arm that would change which calls fire is out of
scope; costs are the IBKR fixed schedule, slippage by tier; BIL carry is
the realised BIL total return, not a forecast; a dynamic arm changes the
executor's sizing contract and would need an executor build plus a tracker
publication to go live.
