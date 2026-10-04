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
- **Bars basis**: the August 2026 campaign cache (raw Yahoo chart API) was built in a cloud session, never committed, and no longer exists; the reproducible source is the FMP dividend-adjusted lane (`scripts/refresh_backtest_bars.py`, ATAI basis-normalized by a constant factor, returns unchanged). Machinery check 1 passes at the repo's ±1% V0 tolerance (`cache_verified`) and separately records whether it lands to the dollar (`cache_exact`); the results JSON carries the lane and every basis factor.
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

_Not run yet. The section between the markers is rewritten by the script on every run._

<!-- RESULTS:BEGIN (written by scripts/backtest_executor_mirror.py — do not edit by hand) -->
_No results yet — run the script on a machine with `backend/data/backtest_bars.json` (see "How to run")._
<!-- RESULTS:END -->
