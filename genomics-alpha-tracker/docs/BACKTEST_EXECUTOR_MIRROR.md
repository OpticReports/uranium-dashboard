# Executor-mirror backtest — the blend3070 book replayed with the executor's mechanics

_Script `backend/scripts/backtest_executor_mirror.py` · results
`backend/data/backtest_executor_mirror_results.json` · served at
`GET /blend3070/mirror-backtest` · shown on the Calls Log page under the Scorecard_

**Question (Casey, 2026-10-01):** "have you run a 2-5-10 year backtest on how
the geo executor would have performed? how do you know what the max DD is?"

**Short answer:** the only numbers that existed were the PAPER R2-A book
(BACKTEST_VARIANTS_R2.md: +14.73% CAGR, 35.6% max DD, Sharpe 0.73, 10y) and
the paper 30/70 blends (R3). The ibkr-executor's blend3070 book does NOT
trade the way that paper book does — it fills a session later, in whole
shares, never leveraged, with a resting day-zero stop, a ratchet-up-only
trail seeded at the fire close, a fire-anchored time stop, commissions, and
BIL carry. This study replays the SAME 5,008 fires on the SAME bars with
the executor's mechanics, one delta at a time, so every difference to the
paper number is attributable — and reports max DD on the daily curve for
the full 10y, trailing 5y and trailing 2y windows, with a block-bootstrap
cone around each.

**Status:** code + synthetic-bar tests + this doc are in the repo. The
numbers are NOT yet produced — the replay needs the gitignored 10-year
bars cache (`backend/data/backtest_bars.json`), which lives on Casey's
machine, not in the agent container or on the Render disk. See "How to
run". The results section at the bottom is written by the script.

## Read this first (honesty block — one line each)

- **Survivorship**: the 32-name universe is today's watchlist; dead/delisted names are absent — absolute numbers flattered.
- **Hindsight tiers**: liquidity tiers (hence slippage) are full-sample median ADDV, known only ex post.
- **In-sample**: the fire thresholds and the 3×ATR / 90-day exit parameters were chosen on this history; R3-F's sensitivity map (2.5–3.5×, 60–120d) is the honest range, not the center.
- **Replayable shadow, not the live book**: sentiment/revision/options lanes absent; no composite gate; no 14-day per-symbol cooldown (242 duplicate same-day fire pairs remain distinct calls); the live engine runs rolling tiers + discovery, not this fixed universe.
- **Selection effects**: 21 judged variants preceded R2-A; this mirror inherits them.
- **Costs ASSUMED, not measured**: IBKR Fixed ($0.005/sh, $1 min, 1% cap), $1 per BIL order, tiered slippage 10/40/100 bps per side, SPY 10 bps; BIL bid/ask, partial fills and MOO auction slippage beyond the tiered bps are not modeled.
- **Not modeled**: mid-session stop-ratchet lag (the level through bar k−1 is applied from the open of bar k, as grade_trailing does; the executor's ratchet lands ~10:30 — `stop_lag_sessions=0`); STOP_MISSING / budget / pending-order operational skips (can only reduce fills); the unswept pre-fund day and BIL dust; the 30/70 band checked at the close, not intraday.
- **Sizing proxy**: lag-2 entries are sized on sleeve equity at the fire-day close (the executor sizes at T+1 ~10:30 on live marks).
- **Trailing windows are SLICES** of the 10-year curve (positions entered before the window carry in — the house SUB_PERIODS convention), not fresh $100k books started at the window open.
- **Measurement basis**: daily mark-to-market on adjusted closes; max DD on the daily curve; CAGR calendar-day (365.25); Sharpe/Sortino √252, rf = 0; bootstrap = stationary block (mean 21d) of the window's own daily returns.
- **Bars basis**: the August 2026 campaign cache (raw Yahoo chart API) was built in a cloud session, never committed, and no longer exists; the reproducible source is the FMP dividend-adjusted lane (`scripts/refresh_backtest_bars.py`, ATAI basis-normalized by a constant factor, returns unchanged). Bars are CLIPPED to the campaign's data end (2026-08-19) before anything is graded, because a lane that runs later would enter the 44 calls the campaign counted as open at data end. Machinery check 1 then verifies the END VALUE (±1%), the FULL DAILY CURVE against the frozen `data/r2a_daily.json` (max point-wise gap ≤1%, max DD within 0.0065, Sharpe within 0.005 — the V0 gate's own tolerances) and the TRADE-SET counts against the stored R2-A meta: the bar-coverage counts (regraded 4964 / open-at-end 44) must match exactly, taken / skipped-at-cap are reported only (a lane's high/low can land a stop a day earlier near the cap boundary); `cache_verified` needs the end value, the curve, the calendar length and the coverage counts, `cache_exact` records the $1 standard separately, and the results JSON carries the lane, every basis factor, the clip and the gate's first defined date.
- **Never present these in-sample CAGRs as a forecast.**

## Protocol

$100k start · fires = the stored R2-A live-flag rows (`backtest_calls_10y_results.json`
call_rows, 5,008 rows, NEVER regenerated) · bars = the campaign cache
(`backtest_bars.json`, split/dividend-adjusted via `to_adjusted_barlikes`) ·
200dma PRIOR-close XBI gate keyed at fire_date+1 for both lags · ≤10 open
(`select_capped`, pending MOOs count as open) · risk 1% of SLEEVE equity per
call · tiered slippage A=10/B=40/C=100 bps per side on every stock fill ·
daily MTM on adjusted closes forward-filled on the XBI calendar · rf = 0 ·
Sharpe/Sortino √252 · CAGR calendar-day.

**Machinery checks (both must pass before anything is reported):**
1. The REUSED R2-A recipe (`build_trailing_rows` → gate → `select_capped` →
   `run_call_book`) reproduces the stored end value **$430,406.29 to $1**. A
   miss means the bars cache is not the campaign cache: the script aborts
   and writes nothing (`--allow-cache-drift` publishes with
   `protocol.cache_verified=false` and the UI shows a red banner).
2. The new engine in `R2A_MODE` reduces to `run_call_book` to 1e-6 at every
   date and to `build_trailing_rows` row-for-row.

**Variant ladder** (each step adds ONE delta; L0 → L5 is the attribution):

| step | variant | adds |
|---|---|---|
| L0 | `r2a_ref` | paper R2-A (`run_call_book` reused, asserted) |
| L0b | `r2a_ref_carry` | paper R2-A with BIL on idle cash (`run_call_book_yield` reused) |
| L1 | `exec_t1_nocost_nocarry` | executor mechanics only: whole shares, cash clip, uncapped 3×ATR risk, day-zero stop, ratchet-up-only trail seeded at the fire close, fire+90 next-open time stop; T+1 fill; no costs, no carry |
| L2 | `exec_t1_nocarry` | + IBKR Fixed commissions + $1 BIL raise/sweep per leg |
| L3 | `exec_t2_nocarry` | + T+2 fill (pre-fund BIL sell mid-session → MOO post-close) |
| **L4** | **`exec_t2_carry`** | **+ BIL carry on idle sleeve cash = PRIMARY 0/100 book** |
| L5 | `exec_t1_carry` | T+1 at full realism (T+1 vs T+2 delta = L5 − L4) |
| **B1** | **`blend3070_t2_carry`** | **30/70 with the executor's 5pp band rebalance + SPY core = PRIMARY comparison** |
| B2 | `blend3070_t1_carry` | 30/70, T+1 |
| P1 | `blend3070_paper_t2_carry` | 30/70 as R3's daily-rebalanced PAPER mix 0.3·r(L4) + 0.7·r(SPY) — construction reference only |

**Windows**: full (2016-01-04 → 2026-08-19), trailing 5y and trailing 2y ending
at the last bar (first calendar date ≥ END − N×365.25 days). Per window and
variant: CAGR, max DD (daily curve), Sharpe, Sortino, Calmar, longest
underwater stretch (calendar + trading days, peak/recovery dates, flagged
`open` when unrecovered at the window end), worst calendar year (partial
years flagged), trade stats (n, stop rate, avg hold, zero-qty skips,
commissions, BIL orders, rebalances). Bootstrap (L4 and B1 only): stationary
block bootstrap of the window's daily returns, mean block 21d, 2000 draws,
seed 20261001 + {full:0, 5y:1, 2y:2}, p5/p50/p95 CAGR and max DD,
P(CAGR<0). Curves stored at ~400 points per window for display; all stats
computed on the daily curve.

## The deltas (executor vs the paper R2-A) and how each is modeled

| mechanic | paper R2-A | executor (blend.py / README.md / tracker) | modeled as |
|---|---|---|---|
| Entry fill timing | next bar's open after the fire bar (`make_call`: bars[i+1].open) | MOO (tif OPG) placeable only outside RTH; the tracker publishes ~10:30 ET at T+1; pre-fund BIL sell mid-session, MOO post-close → fill at the open TWO sessions after the fire bar; T+1 only when settled cash already covers (README 296-336) | `entry_lag ∈ {1, 2}`: fill = open of bars[i_fire+lag]; the lag-2 pre-fill bar still moves the tracker's trail; BOTH reported (L4 primary, L5) |
| Sizing | rd = 1% of prev-close equity, fractional shares rd/risk, risk = min(3×ATR14 through the fire day, 0.5×entry); NO cash constraint (implicit leverage possible) | risk_usd = 1% of SLEEVE equity; risk_qty = int(risk_usd // (entry_ref − trail)); qty = min(risk_qty, int(avail // entry_ref)); entry_ref = fire-day close; trail = fire close − 3×ATR14, UNCAPPED; qty ≤ 0 skipped (blend.py 1179-1186) | per_share_risk = close_fire − L0 = 3×ATR (uncapped); size on sleeve equity at the fire-day close; floor to whole shares; clip to spendable sleeve cash; zero-qty counted (slot stays consumed); cost at the actual fill (cash may dip below 0 by the fill-vs-entry_ref gap, never clipped at the fill); L0 ≤ 0 → the tracker publishes no stop → skipped |
| Trail level | `grade_trailing` (10y): no stop on the entry bar, peak = max close since ENTRY, trail = peak − 3×ATR14[k−1] recomputed daily and allowed to FALL | tracker `shadow.grade_trailing`: peak seeded at the FIRE-DAY CLOSE, live from the bar after the fire day, ATR14 through the prior bar, ratchets UP ONLY; executor rests a STP GTC at the published level from the fill and only raises it | `peak_seed='fire_close'`, `ratchet=True`, `day_zero_stop=True`; open-first gap fills (open ≤ trail → open; low ≤ trail → trail); the level through k−1 applies from the open of bar k (ratchet lag not modeled) |
| Time stop | expiry = entry_date + 90 cal days; exit at the CLOSE of the last bar ≤ expiry | tracker deadline = fire date + 90 (shadow.py:83), graded at that bar's close, published as an exit the next morning; executor MKT-sells ~10:30 (its own fill+90 belt fires later, so the tracker's wins) | `time_stop_anchor='fire'`, `time_stop_fill='next_open'` (open of the first bar after the deadline, tiered slippage — the nearest daily proxy to a 10:30 MKT); sensitivity to `deadline_close` is one flag |
| Pre-fill tracker exit (lag 2) | n/a | the MOO is placed post-close T+1 on a payload built through T; if T+1 pierces the trail the tracker publishes an exit on T+2 morning while the MOO has already filled; the executor MKT-sells in session | fill at bars[j].open, exit the same bar at bars[j].close unless the resting L0 stop fills first (open ≤ L0 → open; low ≤ L0 → L0); status `prefill_exit`, counted |
| Commissions | none (tiered slippage only) | venue commission per fill (`_charge`); IBKR Fixed: $0.005/sh, $1.00 min, 1% of value max (README 593-597: "$1.00 each"); BIL raise = 1 order, re-sweep = 1 order | `commission_model='ibkr_fixed'` on entry + exit; `bil_order_cost`: +$1 at entry, +$1 at exit, +$1 per sleeve→core move; SPY orders $1 + 10 bps/side; BIL bid/ask ignored |
| Idle cash yield | rf = 0 (R2-D: notional-based BIL accrual) | idle sleeve cash swept to BIL every cycle except dust < max($50, 1 BIL) and the pre-fund day | `carry`: sleeve_cash += max(prior-close sleeve cash, 0) × BIL daily total return (`load_bil_yield`, flat 2%/yr proxy on missing days, flagged); dust / pre-fund day not modeled |
| 0/100 vs 30/70 | sleeve-only = `run_call_book`; R3's 30/70 = daily-rebalanced paper return mix, zero cost | target = BLEND_SLEEVE_TARGET (1.0 or 0.30); band rebalance when \|w − target\| > 0.05 at cycle marks: core_to_sleeve sells round(usd/px) SPY, sleeve_to_core moves cash then `core_buy` floor(core_cash/px) when core_cash > max($50, px) | `sleeve_target ∈ {1.0, 0.30}`, band checked at each CLOSE on adjusted closes, executed at that close (10 bps/side + commission on SPY, $1 BIL on sleeve→core); day-1 seed 30k sleeve / 70k core → floor SPY buy at the first close; P1 = the R3 paper construction for comparison |
| 200dma gate / cap | prior-close XBI > 200dma keyed on entry_date; `select_capped` cap 10 | gate from the payload (evaluated when the tracker publishes at T+1 morning with bars through T); open_count = positions − exiting + pending MOOs vs max_open 10 | identical: gate keyed at fire_date+1 for BOTH lags; `select_capped` reused on the exec rows (entry_date = fill bar); a qty-0 row keeps its slot (documented inefficiency, expected ≈0 at $100k) |
| Universe / tiers | 32 hindsight-tiered names, stored fires | rolling watchlist + discovery, live tiers/cooldowns, full trigger set | not modeled — stated above |
| Operational skips | n/a | STOP_MISSING blocks entries, BLEND_BUDGET cap, pending book orders, ENTER breaker, stale payload, holidays/early closes | not modeled — frictions that can only reduce fills |

## Ambiguity calls (most conservative reading)

- The lag-2 book sizes on the sleeve equity at the fire-day close (nearest daily proxy to the T+1 ~10:30 marks); the lag-1 book sizes on the same quantity, which IS `run_call_book`'s prev-close equity.
- The executor's resting stop on the fill bar is checked against the level through bar j−1 for the whole bar (grade_trailing's prior-bar convention); the real stop sits at L0 until the ~10:30 ratchet.
- A row whose L0 ≤ 0 (3×ATR ≥ close) is skipped — the tracker never publishes a stop row for it and the executor refuses "no sizing reference" entries. The paper book trades such rows with the 0.5×entry cap.
- Entry slippage is paid at the fill (realistic ledger); the paper book books it at exit (`r_net`) — intra-hold equity differs by qty×fill×bps per open position, end values do not.
- `core_buy` floor(core_cash/px) at px×(1+10 bps) + $1 can leave core cash a few dollars negative on the seed day (the executor's own ledger convention; a tiny margin debit in practice).
- Trailing windows are slices; a fresh-book variant is a one-line change (`run_mirror(..., end=)` on a restricted calendar) if Casey prefers it.

## How to run

The replay needs `backend/data/backtest_bars.json` (gitignored, ~10 MB). The
August 2026 campaign cache no longer exists anywhere (built in a cloud
session, never committed), so the cache is REBUILT on the FMP
dividend-adjusted lane by `scripts/refresh_backtest_bars.py` (needs
`FMP_API_KEY`; ATAI is basis-normalized by a constant factor, documented in
`data/backtest_bars_basis.json`; `spy_bars_raw.json` is written alongside so
the SPY leg is total-return). Machinery check 1 then decides: R2-A must
reproduce the stored $430,406.29 within ±1% (the repo's V0 machinery gate;
the FMP lane reproduces V0 itself to $1) or nothing is written.

- **Render shell (genomics-alpha-tracker service, recommended):**
  `cd /app && python3 -m scripts.backtest_executor_mirror --out /app/data/backtest_executor_mirror_results.json --no-report`
  — a missing cache is rebuilt automatically (`--refresh-bars` forces it);
  the results land on the data disk and the Calls Log panel serves them first.
- **Dashboard**: the "Run 10-year replay" button on the Calls Log page →
  `POST /blend3070/mirror-backtest/run` (Basic-gated like every other POST)
  runs the script as a subprocess on the host with `--refresh-bars` when the
  cache is absent, log at `/app/data/backtest_executor_mirror.log`, status at
  `GET …/status`. A failed machinery check exits non-zero and the status
  shows the log tail.
- **Locally** (any machine with `FMP_API_KEY`): `cd genomics-alpha-tracker/backend && python -m scripts.backtest_executor_mirror`
  then commit `backend/data/backtest_executor_mirror_results.json` and this
  doc (the script rewrites the results section below).
- `--refresh-bars` rebuilds from the per-symbol lane files under
  `data/bars_cache_fmp_adj/` when they exist (reproducible, no refetch);
  delete that directory to refetch from FMP.
- Options: `--refresh-bars`, `--allow-cache-drift` (publish with
  cache_verified=false), `--fetch-missing` (symbols absent from the cache,
  never overwrites), `--draws N`, `--seed S`, `--report PATH`, `--no-report`.
- Tests (synthetic bars, no cache): `python -m pytest -q tests/test_executor_mirror.py`.

Serving: `GET /blend3070/mirror-backtest` returns the results JSON from the
data disk (`/app/data/…`, survives redeploys) first, then the committed
`backend/data/…` file, else 404 "not run yet". `served_from` says which.

## Counter-agent verdict

**Round 1 (2026-10-01, on the build): SHIP-WITH-FIXES, all MED items
applied before the first commit; the NUMBERS are still unverified because
no replay has run.** Two independent code reviews (backend, frontend) and
twelve build claims put to three refuters each (8 survived, 4 refuted on
evidence quality - the behaviour held, the offered proof was vacuous).

Backend findings and what changed:
- MED: on Render the persistent disk is mounted AT `/app/data` and shadows
  the image's committed `backend/data` (results AND campaign inputs). The
  Dockerfile now keeps a copy in `/app/seed_data`; the route and the script
  fall back to it. `served_from` names the source.
- MED: a SPY series fetched through an unadjusting provider (FMP sets
  adj_close = close) is price-return only. The script now detects it
  (`protocol.spy_adjusted`) and adds a stated honesty line; the 30/70 rows
  are flagged, never silently understated.
- LOW: the route passes `--no-report` (the doc is not writable on the
  host); the bars-cache write is atomic; machinery checks raise
  `SystemExit` (never a bare `assert`); the lag-2 fill-bar stop convention
  is an open DD question below, not a silent choice.
- Not addressed (noted): single-flight state is in-process (a worker
  restart mid-run forgets the running replay); lag-2 fill-bar stop level
  (L0 vs the ratcheted level) is modeled one way and listed as P2.

Frontend findings and what changed:
- MED: tiles were buttons nesting InfoTip buttons (invalid HTML) - now a
  keyboard-operable div; the tile grid collapses to one column on phones;
  trailing-window curves are RE-BASED to 100 at the window start (absolute
  dollars made an eight-year-old gap look like a window result); the period
  renders as a range; a 500/401 is shown as an error, not as "not run yet".

Still PENDING, mandatory before any number is acted on: the second round
on the RESULTS once the replay has run - re-derive the machinery numbers,
spot-check five rows against the bars, recompute the window stats from the
stored daily curve, and confirm the bootstrap seed reproduces.


**Round 2 (results, 2026-10-04): PASS WITH CORRECTIONS.** Live fidelity of the
executor cfg confirmed against `ibkr-executor/app/blend.py` (ratchet-up-only,
day-zero STP at the published level, risk unit = fire close − trail, 90 d
deadline). Corrections 1–6 listed under Results; all applied. Round 1 on the
FMP-lane code change the same day: BLOCK (refresh inputs unreachable on
Render; bars ran past the campaign's data end) → fixed → PASS WITH
CORRECTIONS → applied.

**Round 9 code (exit-rule ablation, 2026-10-04): BLOCK → rebuilt → PASS WITH
CORRECTIONS → applied.** First draft: three forward arms were no-ops (the
paper-arithmetic switch short-circuited the sizing knobs) and the day-zero
stop was not one; the P reduction was not asserted on real data; proposals
were emitted for knobs nobody can change. Rebuilt on the P0 ledger basis
with the day-zero stop as a resting STP floor at L0, reduction and
E-vs-mirror guards, sign-aware CI, Bonferroni-8, actionability tags
(contract addendum 1, committed before the rebuild). Re-review corrections:
per-arm grading counts, basis-clean flag, 10,000 draws, tracker+executor tag
for ratchet/day-zero, floor-overlap statement. Results pending the host run.

## Round 9 results — exit-rule ablation (2026-10-04, first host run, 4,000-draw preview)

Contract: VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md (+ addenda 1, 2).
FMP lane, bars clipped to 2026-08-19, no costs, no carry, lag 1. Machinery:
P reduced to the mirror's r2a_ref; E ended at $278,246, equal to the
published mirror run. Basis switch P0 − P: −0.07 pp CAGR (clean).
Mechanics gap E − P0: −5.48 pp CAGR, −0.195 Sharpe, max DD 35.4% → 30.7%.

| rule flipped | fwd share (P0 + rule) | bwd recovery (E − rule) | fwd Sharpe CI95 | bwd Sharpe CI95 | sub 3/3 | where |
|---|---|---|---|---|---|---|
| **ratchet-up-only trail (H14, primary)** | **1.02** | **0.76** | [−0.396, −0.024] | [−0.007, +0.359] | yes / yes | tracker+executor |
| day-zero stop at L0 | 0.35 | 0.08 | [−0.170, +0.059] | [−0.031, +0.080] | 2 / 1 | tracker+executor |
| time stop anchored at fire | 0.22 | 0.26 | [−0.140, +0.046] | [−0.022, +0.170] | 3 / 3 | tracker |
| time stop fills next open | 0.19 | 0.19 | [−0.139, +0.060] | [−0.013, +0.110] | 2 / 2 | tracker |
| peak seeded at fire close | 0.18 | −0.13 | [−0.121, +0.098] | [−0.086, +0.014] | 2 / 1 | tracker |
| cash clip | 0.02 | 0.04 | spans 0 | spans 0 | 1 / 2 | not actionable |
| risk cap 0.5× entry | 0.00 | 0.00 | spans 0 | spans 0 | 2 / 1 | executor |
| whole shares | 0.00 | 0.00 | spans 0 | spans 0 | 2 / 2 | not actionable |
| G_stop (seed + ratchet + day-zero) | 0.96 | — | [−0.392, +0.004] | — | 3 | — |

**Verdict under the contract: NULL, no proposal.** The primary fails the
sign-aware CI test on the backward side by 0.007 at 4,000 draws (both
ratchet tests are marginal: half-width ≈ 0.18 either way, forward passes by
0.024), AND the action bar fails on its own: B_ratchet max DD 33.5% vs E
30.7% = +2.8 pp > 2 pp. The pending 10,000-draw interval therefore cannot
change the action, only the label on H14.

**H14 standing**: strongly supported on point estimates (all of the gap
forward, three-quarters backward, 3/3 sub-periods both ways), not confirmed
under the contract's interval test.

**Mechanism** (counter-agent, round 9 results): the stop each day is peak −
3×ATR14 of the prior bar. Without the ratchet the level FALLS when ATR
expands; with it the level is held. ATR expansion in a biotech is catalyst
proximity, which the fire flags select for, so the ratchet pins the stop at
the pre-expansion distance just as the stock starts swinging and the
position is stopped on noise during the move it was bought for. It cannot
protect against the losses that make the drawdown (gap fills are open-first
wherever the stop sits); it trims the right tail. Earlier exits free cap
slots (F_ratchet 658 taken vs P0 600; E 677 vs B_ratchet 632) and each
replacement entry carries fresh gap risk, so turnover rises and drawdown does
not fall: −5.6 pp CAGR for −0.8 pp max DD. E's lower drawdown than paper
(30.7 vs 35.4) is the PACKAGE, not the ratchet: backward DD increments
(ratchet +2.8, cash clip +2.4, peak seed +2.1, time-stop anchor +1.5) sum to
8.5 pp against a 4.7 pp total, strongly non-additive.

**Counter-agent (results): PASS WITH CORRECTIONS**, applied: lead with the
drawdown bar; 10,000 draws as the number of record (addendum 2); both
ratchet tests marginal, the backward interval shifted not wider; "all
forward, three-quarters backward"; DD deltas are point comparisons without an
interval; fixed FIRE set wording; G_stop's spanning interval reported.

**Next step** (no code change to live money): the tracker's shadow grader
re-grades every live call under the SAME ratchet rule the executor obeys, so
the live record cannot yet test H14. Add an observe-only second grading
under the campaign's non-ratchet exit to GET /shadow/track-record, and let
the live record decide.

## Pending DD questions (ranked)

| P | question | what it moves | status |
|---|---|---|---|
| P1 | WHERE is `backend/data/backtest_bars.json` (and `spy_bars_raw.json`)? Both gitignored, absent from the container and the Render disk; an FMP refetch cannot reproduce R2-A. (A) commit the cache (~10 MB, .gitignore exception) so the Run button works on Render, or (B) run on Casey's machine and commit only the results JSON? | gates producing ANY number | asked 2026-10-01 |
| P1 | Which sleeve target is the live book running today (BLEND_SLEEVE_TARGET 1.0 vs 0.30)? | which row is the headline (L4 vs B1) | asked 2026-10-01 |
| P2 | Time-stop fill convention — next-bar open (spec default, ~10:30 MKT proxy) vs the tracker's deadline close? | L1–L5 exits on ~5% of rows | asked 2026-10-01 |
| P2 | IBKR account on Fixed or Tiered commissions? Tiered (~$0.0035/sh + fees) changes the cost row slightly. | L2 cost delta | asked 2026-10-01 |
| P2 | Lag-2 stop timing: accept `stop_lag_sessions=0` (level through k−1 from the open of k) or add a 1-session lag sensitivity row? | stop fills on gap days | asked 2026-10-01 |
| P3 | Trailing 5y/2y as SLICES (default) or fresh $100k books from the window open? | 5y/2y CAGR & DD | asked 2026-10-01 |
| P3 | Bootstrap seed 20261001 (new) vs reuse R3G 20260820? | cone values, not shape | asked 2026-10-01 |
| P3 | Commit policy: the results JSON is now a .gitignore exception (like the other campaign JSONs) — confirm. | committed fallback on Render | asked 2026-10-01 |

## Results

First real run: 2026-10-04 on the genomics-alpha-tracker Render host, FMP
dividend-adjusted lane (start 2015-07-23; ATAI basis 0.0728, ILMN 0.99905),
bars clipped to 2026-08-19, published with `--allow-cache-drift`
(`cache_verified=false`: R2-A replays to $469,242 vs the stored $430,406,
+9.0%, one call of 601 flipped at the cap; bar coverage identical 4964 / 44;
max DD 35.58% vs 35.57%). The results JSON lives on the host's data disk
(`/app/data/backtest_executor_mirror_results.json`) and is served by the
Calls Log panel; it is not committed. Counter-agent round 2 (results):
PASS WITH CORRECTIONS, applied below and in the code (commit after this
doc). The lag-2 rows below predate the live cap-occupancy fix
(select_capped_exec) and move by at most the T+1/T+2 delta on the re-run.

**Full window 2016-01-04 → 2026-08-19, $100k start**

| variant | end | CAGR | max DD | Sharpe | Sortino | Calmar | underwater | worst yr |
|---|---|---|---|---|---|---|---|---|
| r2a_ref (paper, no carry) | $469,242 | 15.67% | 35.6% | 0.76 | 1.15 | 0.44 | 1233 d | 2022 −17.2% |
| r2a_ref_carry (paper + BIL) | $529,524 | 16.99% | 34.3% | 0.82 | 1.23 | 0.50 | 1176 d | 2022 −16.3% |
| exec_t1_nocost_nocarry (mechanics only) | $278,246 | 10.11% | 30.7% | 0.57 | 0.86 | 0.33 | 1305 d | 2022 −16.4% |
| exec_t1_nocarry | $267,048 | 9.69% | 31.0% | 0.55 | 0.83 | 0.31 | 1308 d | 2022 −16.5% |
| exec_t2_nocarry | $259,666 | 9.40% | 30.7% | 0.55 | 0.82 | 0.31 | 1224 d | 2022 −16.2% |
| **exec_t2_carry (live sleeve rules)** | $294,301 | 10.70% | 29.2% | 0.61 | 0.91 | 0.37 | 1181 d | 2022 −15.4% |
| exec_t1_carry | $302,607 | 10.99% | 29.5% | 0.61 | 0.92 | 0.37 | 1270 d | 2022 −15.7% |
| **blend3070_t2_carry (live book)** | $428,445 | 14.69% | 27.4% | 0.98 | 1.39 | 0.54 | 709 d | 2022 −16.4% |
| blend3070_t1_carry | $422,227 | 14.53% | 28.3% | 0.96 | 1.36 | 0.51 | 722 d | 2022 −17.5% |
| blend3070_paper_t2_carry | $422,419 | 14.53% | 27.8% | 0.97 | 1.37 | 0.52 | 710 d | 2022 −16.9% |

**Trailing windows (slices of the same curve; positions carry in)**

| variant | 5y CAGR | 5y max DD | 5y Sharpe | 2y CAGR | 2y max DD | 2y Sharpe |
|---|---|---|---|---|---|---|
| r2a_ref_carry | 11.18% | 22.1% | 0.65 | 10.91% | 19.9% | 0.57 |
| exec_t2_carry | 7.69% | 21.8% | 0.49 | 9.95% | 21.8% | 0.53 |
| blend3070_t2_carry | 11.95% | 19.5% | 0.85 | 16.06% | 13.4% | 1.08 |

**Bootstrap (stationary block, mean 21 d, 2,000 draws, same draws for both)**

| | 10y CAGR p5 / p50 / p95 | 10y max DD p5 / p50 / p95 | P(10y CAGR < 0) |
|---|---|---|---|
| exec_t2_carry | −0.2% / 10.5% / 22.0% | 23% / 34% / 53% | 5.5% |
| blend3070_t2_carry | 6.7% / 14.6% / 22.7% | 15% / 26% / 39% | 0.1% |

**Deltas, full window (CAGR / max DD / Sharpe)**: carry on vs off +1.30 pp /
−1.5 pp / +0.06; costs −0.42 pp / +0.3 pp / −0.02; T+1 vs T+2 +0.29 pp;
mechanics vs paper (no costs, no carry on either side) −5.55 pp / −4.9 pp /
−0.20; executor vs paper with carry on both sides −6.3 pp.

**What the counter-agent corrected (round 2, results)**

1. The −5.5 pp "mechanics" gap is a RULE MISMATCH INSIDE OUR OWN STACK, not
   execution friction: the executor obeys the tracker's published shadow
   levels (`app/calls/shadow.py grade_trailing`: fire-close peak seed, trail
   ratchets up only, day-zero stop), while the campaign's R2-A grader
   (`backtest_variants_10y.grade_trailing`) seeds the peak at the entry
   close, has no entry-bar stop and lets the trail FALL when ATR expands.
   Which knob carries the gap is an ablation question (ratchet, seed,
   day-zero stop, time-stop anchor and fill, cash clip, whole shares, risk
   cap), pre-registered, R3-F sensitivity caveat; a winner lands in the
   tracker's published levels.
2. The 2y "executor beats paper" reading was carry-asymmetric (exec with
   carry vs paper without); like-for-like the executor trails by ~1 pp in
   every window. `exec_vs_r2a` now compares carry-on to carry-on.
3. Noise floor: one cap-boundary flip on this lane moved the 10y end value
   9% (~0.8 pp CAGR). Deltas below that (costs, T+1/T+2, band vs paper)
   are not robust; mechanics, carry and the blend's DD/Sharpe gain are.
4. Lag-2 cap occupancy was one day more generous than live (slot held from
   the fill bar, not the T+1 cycle); fixed in `select_capped_exec`.
5. Bootstrap P(CAGR<0) and the DD cones are reshuffles of this in-sample
   survivor history: lower bounds, not forecasts.
6. 5y/2y rows are the running book's growth over the slice, not a fresh
   5-year track record.

**Verdict for the book**: on the executor's own replay the 30/70 construction
beats the sleeve alone on every stat (Sharpe 0.98 vs 0.61, max DD 27% vs
29%, P(10y CAGR<0) 0.1% vs 5.5%); keep 30/70. The drawdown question is
answered at ~29% realized / 34% bootstrap median / 53% p95 for a sleeve-only
book, 27% / 26% / 39% for the live 30/70 book.
