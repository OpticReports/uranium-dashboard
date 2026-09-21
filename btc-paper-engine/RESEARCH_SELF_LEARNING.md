# Self-learning engine — design pass (2026-09-21)

Casey: *"we want to build our engine to be self learning and improving, always
looking for alpha and improved relative returns. is this logic you can build?
... as its placing trades, it has more data to back test with ... we need to
make something extremely robust here."*

Method: 17 agents — 3 codebase mappers, 4 rival architectures, 8 red teams (a
hostile statistician and a hostile operator on each), 1 synthesis, 1
completeness critic. 71 mapped findings, 40 blockers. Two of the findings were
independently re-verified by running the code; both are LIVE DEFECTS and are
recorded in §1 rather than filed as design inputs.

## 0. The answer

Buildable — but the thing that can be learned here is what trading **COSTS**,
not what to trade. The premise needs correcting with numbers:

- **Trading does not generate backtest data.** 4h bars accrue at 2,190/yr
  whether or not a contract is traded. One year of live trading adds +21.9%
  more bars to the 10,002-bar fixture and shrinks the standard error on the
  annualized Sharpe by ~9.5%. The *trades* it generates (50-100/yr against 318
  replay round trips already in hand) are one more draw from the same
  distribution — bought with real money.
- **A search loop makes the existing books LESS certified, not more.** DSR
  deflates against the CUMULATIVE registry. Searching at 800 cells/month for a
  year moves the hurdle SR0 from 1.65 to 1.81 and drops S5's DSR from 0.29 to
  0.18 **with S5 unchanged**. The protocol's current reading is already
  "formally, none of these is yet distinguishable from selection bias."
- **The marginal information is not in P&L at all.** It is per-fill:
  ~120-250 fills/yr, ~40-75 venue `crossed` booleans/yr (the venue returns
  this free and btc-executor reads it nowhere), ~1,700 in-position funding
  accruals/yr (currently measured at exactly zero), and an order-decision
  denominator that does not exist today in any form. 10-100x the sample rate
  of anything P&L-class — see research/learnability.png.

The archetype is already on the record: the 8.64-vs-6.00 bps finding came from
**n=4**, was about EXECUTION, and made the book SMALLER.

## 1. Two live defects found on the way (both re-verified by running the code)

### 1a. Pullback fee accounting is disconnected from config — FIXED 2026-09-21

`core.py` built the pullback `Position(...)` with **no `fee_bps`**, so it took
the dataclass default 6.0; the donchian path passes `2 * tcfg.taker_fee_bps`.
Measured on the full fixture before the fix:

| taker_fee_bps | S3 equity | S3 fees | S4 equity | S4 fees |
|---|---|---|---|---|
| 4.32 | 207,863 | 17,290 | 226,501 | 20,216 |
| 6.00 | 207,863 | 17,290 | 216,991 | 27,433 |
| 8.00 | 207,863 | 17,290 | 206,185 | 35,585 |
| 20.00 | **207,863** | **17,290** | 112,461 | 58,667 |

S3 had **one** distinct equity across a 4.6x fee range; S4 had five. S1 and S2
are pullback books and were equally pinned.

**Fixed:** the pullback path now stamps `fee_bps=2 * tcfg.taker_fee_bps`, and
`backend/tests/test_fee_wiring.py` (10 gates, mutation-checked — reverting the
wiring fails 8) asserts every book's dollars move with the config and that
fees equal `notional x 2 x taker / 10_000` exactly.

**CORRECTION to the first statement of this finding.** The restatement was
first reported as $10,138 / 10.1pp. That figure is the wiring fix **plus**
re-basing `taker_fee_bps` to the measured 4.32/side. The wiring fix alone, at
the **shipped default of 6.00/side**, restates S3's dollar equity from
**207,863 to 185,531 — -$22,332 / -22.3pp**, because the default charges a
12.00 bps round trip. The larger number is the one that ships.

**The sharper finding underneath it.** The engine carried TWO fee models that
disagreed by 2x. `research_basis_stats` charges `2 * tcfg.taker_fee_bps` and
reproduces the reference backtest **exactly at 6.00/side — a 12.00 bps round
trip — and at no other value** (measured: S3 48.1/-14.2, S1 64.5/-22.3, S2
101.4/-22.9 land on the reference at 6.00; at 4.32 they read 50.3 / 68.3 /
106.6). Meanwhile the dollar path charged pullback books 6.00 **round trip**.
So the registered objective is 12.00 bps round trip, RESEARCH_FEES.md measured
**8.64**, and the dollar path was running 6.00. Three numbers, one book.

`taker_fee_bps` has therefore been **left at 6.0**. Re-registering the
objective at the measured fee restates every published MAR in the repo and is
a dated protocol amendment Casey signs — P1 question 4 below — not a default
an agent edits while fixing a wiring bug.

**A second defect the fix exposed.** `test_dollar_vs_research_basis_gap_is_
short_squared_terms` asserted `research - dollar < 10.0` and passed at 9.6
**only because the dollar path was under-charging S3 by half the fee**. With
both bases on 12.00 the true gap is 13.7pp (research 48.1, dollar 34.4). The
guard was calibrated against the defect. It is now a two-sided band
(11.5 < gap < 16.0), so if a pullback book ever stops charging the configured
fee the gap collapses toward 9.6 and the LOWER bound fires. A one-sided bound
is what let this sit undetected.

Engine suite after the fix: **102 passed** (baseline 92, plus the 10 new
gates, zero regressions).

### 1b. barbell-lab is live, publicly reachable and has no authentication

`grep -cE "Depends|HTTPBearer|Security|add_middleware|verify_token"
barbell-lab/src/barbell/web/app.py` returns **0**. Verified live:
`GET https://barbell-lab.onrender.com/api/versions` returns 200 with data and
no token. Exposed POST routes include `/api/promote` (own docstring: *"this
changes the live book's targets"*), `/api/run/*`, and `/api/chat`. The
promote "typed confirmation" is the version label — which that same
unauthenticated GET returns, so it is not a secret.

`POST /api/chat` reaches `register_trial(con, ..., "chat", ..., None, ...)`
(`chat/agent.py:265`) with **sharpe=None** — an unauthenticated endpoint
appending rows to the cumulative trial registry, the exact corrupting case
§3 below bars. The service also holds an env var named `EXEC_TOKEN`
(render.yaml:130, commented "btc-executor /status read secret"); whether the
VALUE is `EXEC_READ_TOKEN` or the full trading token is not determinable from
the repo. **P1 question for Casey.** No POST route was exercised.

## 2. Recommended architecture — three layers, one direction, no closed loop

1. **LEDGER**, inside btc-executor. Recording what it did is not a strategy
   opinion, so this breaches no standing law. Append-only SQLite on the
   existing disk: `fills` (venue's own `time`, cloid, order class, `crossed`,
   `fee_usd`, `closed_pnl_usd`, `engine_intent_px`, `kelly_m_at_decide`),
   `orders` — **one row per order DECIDED including never-sent**, the
   denominator that does not exist today — and `funding`. Read-only behind the
   existing read token.
2. **REPORT**, in a keyless reader. Monthly, human-read, with charts: realized
   cost waterfall in dollars and bps/yr, slip-vs-spread, crossing-rate Wilson
   interval widening with n, measured-minus-modelled drift, order-outcome
   histogram. Estimates scalars. Never an edge.
3. **PRs**. The only path from a learned number to live behaviour is a
   committed `cost_model.yaml` that Casey merges. Nothing is wired into the
   order path.

Stages, ordered by sample rate: **0** substrate fixes (§1a + provenance +
archive-before-reset + fail-loud config) → **1** ledger → **2** monthly cost
report → **3** discrete-event PR trigger (fee-tier change; crossing-rate
interval excludes the model) → **4** display-only slip CUSUM, ships dark →
**5** advisory retirement SPRT that publishes and never fires.

## 3. Do not build

- **Any automatic sizer.** Measured signal-to-noise 0.07: the whole 1.32
  bps/side fee discovery moves `recommended_m` 0.99 → 0.96, while 40 block
  resamples of the same 190 trades give mean 0.75, sd 0.43, with 7 of 40
  tripping the kill rule to 0.00. `{"max_kelly_m": NaN}` parses cleanly and
  sizes every leg at zero with no event fired.
- **Walk-forward parameter search.** The test folds ARE the incumbent's fit
  window (the ~1,500-trial pullback research was fit on 2024-26), a confound
  1.8-5.7x the effect and pointed the wrong way. Transfer has been tested
  twice in this repo and failed twice (trail rho = **-0.064**; ETH passing
  only on the window BTC was fit on).
- **An adaptive blend weight.** Not expressible: `mirror.py:1467-1473` is
  `weight = w if leg == "trend" else 1.0 - w`, a single scalar, so cutting
  trend RAISES pullback one-for-one. And the argmax-growth w has a 90% CI of
  the entire [0,1] axis at 1, 2, 3 and 4.47 years — the width does not shrink.
- **min()/argmin over a specification grid sold as "the conservative
  envelope".** Selection bias is a property of taking an extremum, not of its
  direction: E[min of 16 iid draws] sits 1.77 sd below the mean, so the
  governed size drops by more than the entire fee correction purely by
  enumerating more cells.
- **Measurement cells in the strategy trial registry.** `var_sr` is computed
  from that registry's own stored Sharpes. Writing `sharpe=0.0` RAISES S5's
  DSR 0.29 → 0.82 (0.94 after three years) — the loop would certify the live
  book as 94% genuine skill by writing zeros.
- **Any blocking venue call in the order-decision path.** `grep -n timeout
  btc-executor/app/hl.py` returns nothing. The precedent is STOP_REPLACE_MAX,
  which exists only because an unbounded loop in this same path placed 4,320
  live orders and 4,320 pages in one day.
- **Re-fitting a parameter in response to disappointing live results.**
  `research/fees/PREREG.md:120-122` already bans it by name.

## 4. Invariants

- The live sample may only ever estimate a scalar COST, never an EDGE.
- No clause of the form "if live P&L underperforms, adapt X" ships — including
  one this system proposes later.
- Recording is not a strategy opinion; estimating is. That is what lets the
  ledger live where the credentials are.
- The engine gains no outbound dependency. The executor pulls.
- Any writer reachable from the order path must be physically incapable of
  raising.
- Every automatic action is down-only, floored, expiring and loud.
- No number moves money without a Render deploy.
- A trial is any config evaluated, counted from registration, in any bucket.
- Holdout is a consumable; forward bars at 2,190/yr are the only renewable
  source.
- A detector whose input is downstream of its own output is suspended, not fed.
- State that decides money is re-derived on boot from its append-only log and
  refuses to serve until it matches.

## 5. Honest expected value

**This mostly protects you from losing. It does not find alpha, and no live
return series will ever confirm it helped.** At full ramp the book's annual vol
is ~8.2%, so a t-stat of 1.96 on a 150 bps/yr execution effect takes **114
years**, and on the 30 bps/yr fee error already found, **2,847 years**. It is
knowable only as arithmetic on ledger rows. Every framing of it as "improving
relative returns" should be struck.

Near-certain, weeks: the §1a fix. High-confidence, months: funding, plausibly
the largest cost line in the system at 45-240 bps/yr at full ramp and currently
measured at exactly zero. Sizing the prize honestly: at CURRENT live notional
the entire annual value of a perfect execution model is about **$15** — this is
infrastructure built deliberately BEFORE size, because discovering a 1.32
bps/side modelling error after the ramp is expensive and before it is free.

**The largest term is a cost avoided.** Not spending 9,600 trials a year is
probably the single most valuable thing on this list.

## 6. Pending DD questions (ranked)

| # | P | Question | What it moves |
|---|---|---|---|
| 1 | P1 | Does barbell-lab's `EXEC_TOKEN` hold the read-only value or the full trading token? | Whether a zero-auth public service holds /kill and /drill authority over the live book |
| 2 | P1 | Are null/placebo/calibration/specification cells trials? `research/trail/PREREG.md` says no; RESEARCH_PROTOCOL.md:36-37 charged them anyway | Whether measurement is free (~0-30 cells/yr) or charged (3-4x), and whether Stage 2 needs a registry at all |
| 3 | P1 | Your honest posterior on this book's forward expectancy — a number | Every monitoring threshold. At 12%/yr a false 30-day stand-down costs ~$985; at 0%/yr it costs $0 and monitors should be far more aggressive |
| 4 | P1 | Approve re-registering the §4 objective at the measured fee (8.64 bps round trip) as a dated amendment? | Every historical MAR is either restated or stamped "objective v1". Prerequisite to §1a being meaningful |
| 5 | P1 | Has `purge_cli.py` been run on the live edge_trades disk? `mirror.py:837-841` says the slip verdict "must not authorize sizing" until it has | Whether Stage 4 can start at all |
| 6 | P2 | Pre-register the ramp release condition as a NUMBER now? | Otherwise this system becomes the thing that sets it post hoc — the exact failure pre-registration exists to prevent |
| 7 | P2 | Should `POST /books/reset` continue to exist once archive-before-reset lands? | Whether the live record can ever be destroyed again |
| 8 | P2 | Do you accept that "self-learning" here is bookkeeping plus pull requests — no learned number reaching the order path automatically, ever, absent a dated amendment to KELLY.md? | Whether Stages 4-5 have any promotion path or ship permanently display-only |

## 7. What the critic caught in the synthesis itself

- Four of five promotion gates were **vacuously satisfiable**. Stage 3's "two
  consecutive quarters in which every fired PR was judged correct" is true over
  the empty set. Stage 2's "reconcile ledger fees to userFills within 1 bp"
  tests a copy, not the accounting, and passes at n=0. Stage 1's "30
  consecutive days" is a TIME gate on a RATE phenomenon.
- The staging order **inverted its own criterion**: the S4 MTM path carries
  **8,941 trade-bar observations (2,000/yr)** already on disk, and MAE/MFE —
  reconstructible in ~20 lines, S3 MAE median -2.00% / MFE +2.41% against a
  median stop distance of 3.44% — appeared in no stage at all. That is the
  cheapest 80%.
- Nobody in four designs and eight red teams noticed that the paper engine
  fills **99.0% of its limit entries (190 of 192)** while the live venue
  crossed **4 of 4**. The paper book's entry price is idealized on essentially
  every trade — a divergence larger and more systematic than the fee error the
  whole design is built around.

These are corrections to the plan, not to the recommendation. Fix the gates,
put MAE/MFE and the MTM path in Stage 1, and add the fill-rate divergence as
its own measured line.
