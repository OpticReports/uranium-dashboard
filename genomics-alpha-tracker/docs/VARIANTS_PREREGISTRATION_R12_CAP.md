# Pre-registration — ROUND 12, the open-position cap (does a fuller sleeve help?)

Committed BEFORE any round-12 code exists. Nothing here is a live change;
the output is a proposal for the open-position cap, or a null.

## Question (Casey, 2026-10-20)

"I still feel like the amount we're allocating to these positions are pretty
small ... we only have five or six trades open at a single time ... there's
just not enough exposure." Then, after the round-10 recap: "run the cap
study."

Facts the question rests on, all from the stored round-11 live-rule arm
(`backend/data/backtest_per_symbol_study_results.json`, arm U2, $120,000
base = cap 10, at most 2 open calls per symbol, risk 1%):

- the sleeve holds names worth 36.8% of itself on an average day (p50 41%,
  p90 74%); 0 open on 27.6% of days (the 200dma gate is off); AT the 10-cap
  on 22.2% of days;
- 2,210 of 3,059 gated fires (72%) were skipped because 10 calls were
  already open; 204 more were refused as third entries in one name;
- round 10 named the cap (with the gate) as the binding constraint on
  deployment and the cap study as the next lever (BACKTEST_EXECUTOR_MIRROR.md,
  round 10, "Next step"). A cap arm changes WHICH calls are taken, so it is a
  selection study, not a sizing one.

## Hypotheses

* **H17a (deployment):** raising the cap raises the sleeve's mean deployed
  fraction and saturates well short of 100%, because the gate-off days and
  the cash clip bound it. Prior: C15 ≈ 45%, C20 ≈ 50%, CU 50–60%.
* **H17b (the claim the decision rule tests):** the fires the 10-cap skips
  carry an edge comparable to the ones it takes and are imperfectly
  correlated with the names already held, so book Sharpe RISES with the cap.
  The competing reading: they arrive in hot biotech regimes when ten names
  are already held, so they add correlated risk (wider drawdown, flat
  Sharpe).
* **H17c (selection quality, diagnostic):** the mean r_net of the fires an
  arm admits that C10 does not is no lower than the mean r_net of C10's
  taken set. (Round 11's replacement fires were weaker: +0.14 vs +0.20.)
* **H17d (Casey's framing, diagnostic):** the sleeve's daily correlation and
  beta to SPY rise with deployment (a scratch check on 2026-10-20 read the
  executor replay's sleeve at 0.26 / 0.29 overall but 0.36 / 0.58 on days
  with positions open, so cash days dilute it).

## Arms (all on the live executor path: T+2 fill, IBKR costs, BIL carry, XBI
200dma gate, risk 1% of sleeve equity, whole shares, the cash clip, at most 2
open calls per symbol; book = 30/70 with the 5pp band; LIVE base $120,000)

| arm | open-position cap |
|---|---|
| C10 | 10 — anchor, the live rule (= round-11 U2) |
| C15 | 15 |
| C20 | 20 |
| CU | none — the sleeve's cash (the clip) is the only limit |

The cap and the per-symbol limit use `select_capped_exec`'s live slot
occupancy (a call holds its slot from its gate date, the T+1 sizing cycle
when the executor counts a pending MOO, through its exit date). Selection
order is unchanged (gate date, entry date, symbol, flag). Calls are graded
once, independently of the cap (exits do not depend on what else is held),
so the arms differ only in which graded calls are taken and in the cash
each entry finds.

**Reduction checks (any failure stops the run, nothing written):** C10 at
$120,000 reproduces the stored round-11 U2 book end value to within $1;
cap 10 with NO per-symbol limit at $100,000 reproduces the stored mirror
`blend3070_t2_carry` end value to within $1.

## Metrics (per arm; full 2016-01-04 → 2026-08-19 and the mirror's 5y / 2y
trailing windows)

Book: CAGR, Sharpe, Sortino, Calmar, max DD, longest underwater. Sleeve
(time-weighted, band transfers removed, round 11's convention): CAGR,
Sharpe, max DD, daily correlation and beta to SPY. Deployment: mean deployed
fraction (p10 / p50 / p90, mean on open days), share of days at the arm's
own cap and at 0 open, max open. Selection: entries taken, skipped at the
cap, refused as repeats, skipped for zero shares, and entries whose size the
cash clip cut below the 1% risk size. Concentration: largest single-name
share of the sleeve (p50 / p90 / max), mean distinct names per open day.
Quality: mean r_net of the taken set, and of the ADMITTED set (taken by the
arm, not by C10).

Primary statistic: the paired stationary block bootstrap of the book-level
Sharpe DIFFERENCE vs C10 (identical block draws, 10,000 draws, mean block 21
days, seed 20261020, Bonferroni family = 3 arms); 63-day block sensitivity
at 2,000 draws reported.

## Decision rule (fixed now)

Propose an arm ONLY if all four hold:

1. the Bonferroni-3 interval of the full-window book Sharpe delta vs C10
   lies entirely above zero;
2. the arm's book max DD is no more than 2 pp worse than C10's;
3. the 5y-window book Sharpe delta vs C10 is positive;
4. leave-one-year-out: for every calendar year y in the window, the
   full-window point Sharpe delta recomputed on daily returns with year y
   removed (both arms, same days) is positive. (Round 10's D1 lesson: one
   year carried 47% of an apparent edge.)

Otherwise NULL: keep cap 10. If several arms pass, propose the one with the
highest full-window point Sharpe delta; if a smaller cap's delta is within
0.01 of it, propose the smaller cap. A positive CAGR delta with a wider
drawdown is reported as leverage, not improvement.

## What a pass would change (and what it would not)

A pass is a PROPOSAL; nothing goes live without Casey's decision. Going live
would take three changes, because the cap lives in three places: the
executor's hard `MAX_OPEN = 10` (ibkr-executor/app/blend.py; the tracker can
only tighten it), the tracker's published `book_params.max_open`
(app/routers/blend.py), and the tracker's auto-call creation cap
`max_open_calls` (default 10, /tuning). The executor change is a live-money
code change with its own review, deploy and 2FA restart. The kill ledger's
sleeve drawdown lines were set on cap 10 and would be re-derived. The
per-symbol limit, the risk rule and the 30/70 target stay as they are.

## What this cannot tell us (honesty, carried into the results)

- In-sample over the same 10.6 years as every prior round; a winner here is
  a hypothesis, not a result. Never present these CAGRs as a forecast.
- The fire set is the tracker's (survivor-shaped universe). The fires a
  higher cap admits are exactly the ones the live tracker has never created
  (its creation cap is also 10), so no live call has ever tested them.
- Costs: IBKR fixed schedule + tiered slippage; BIL carry is the realised
  BIL total return.
- The cash clip: the replay clips an entry on its entry day only (zero
  shares = skipped for good); the live executor re-sizes a clipped-to-zero
  candidate on later cycles inside its entry window, and waits instead of
  placing a clipped entry while a BIL order is resting. BLEND_BUDGET (the
  gross cap) is not modeled.
- Occupancy basis, measurement basis (daily MTM on adjusted closes, CAGR
  calendar-day, Sharpe √252 with rf = 0), and the conditional-interval
  caveats are rounds 10–11's, unchanged.
