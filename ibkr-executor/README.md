# ibkr-executor — the IBKR execution service

ALL automated trading through Interactive Brokers routes through this one
service. Strategy engines stay keyless and emit decisions; this service
holds the IBKR connection and executes them — same separation of powers as
btc-executor (Coinbase) enforces for the BTC book.

## Architecture

```
strategy managers (keyless decision brains)     ibkr-executor
  app/manager.py  El Nino options ladder   -->  IB Gateway (containerized,
  <future>        next IBKR strategies          ib_async) -> IBKR
```

- Each strategy is a state machine emitting ORDER INTENTS
  ({OPEN|CLOSE, structure, budget, reason}); the execution layer prices,
  places (combo orders for spreads), and reports fills back.
- Safety doctrine (inherited from btc-executor): DRY_RUN default, paper
  account first, per-strategy budgets and kill switches, Telegram alerts
  on every action, persisted state, /status surface.

## Strategies

| module | book | status |
|---|---|---|
| manager.py (El Nino ladder) | NG call spread -> SB put spread -> SLV call spread, triggered + sequential, house-money rolling (see elnino-lab/ELNINO.md) | infra deployed OFFLINE; combo placement lands with paper phase; live target Nov 2026 window |
| blend.py (blend3070) | H13 30/70: R2-A sleeve (tracker gate-on fires, 1% sleeve risk, 3xATR GTC trail + 90d time stop, BIL on idle cash) / SPY core, 5pp rebalance band (genomics-alpha-tracker HYPOTHESES.md H11/H13) | paper-phase adapter LANDED (real IBAdapter stock surfaces, see below); BLEND_ENABLED=false default — zero behavior change until flipped |

## blend3070: intents contract + rollout

The genomics tracker (keyless decision brain) publishes
`GET {TRACKER_URL}/blend3070/intents` once per trading day:

- `gate` — XBI prior-close vs prior-day 200dma (R2-A convention; an
  undefined gate never binds)
- `entries` — CANDIDATE auto-call fires from the last trading day, listed
  only while the gate is on: `{symbol, call_id, fire_date, flag_type,
  risk_frac, entry_ref, note}` (`entry_ref` = fire-day close, the sizing
  reference)
- `stops` — the current R2-A trailing-stop level per open call (drives the
  daily GTC cancel/replace)
- `exits` — trail/time-stop signals (advisory, echoed 7 days; the resting
  GTC stops and this service's own 90-calendar-day clock are the real
  backstops)
- `rebalance.needed` is null: sleeve weights are computed HERE — the
  tracker never learns positions or account equity (the poll is a bare
  authenticated GET)

This service reconciles intents against its own persisted book
(`BLEND_STATE_PATH`), sizes in dollars (shares = 1% of sleeve equity /
(entry_ref - trail)), and emits MOO entries, GTC STP cancel/replace, MKT
time-stop exits, band rebalances, and BIL sweeps through the same adapter
modes as the ladder (OFFLINE -> DRY -> PAPER -> LIVE, DRY_RUN default true).

### Cycle order (reconciliation-first — counter-agent-mandated law)

`run_cycle` runs EVERY loop iteration — a tracker outage does NOT skip it:
the service calls `run_cycle(payload=None)` when the poll fails, so the
reconcile pass and the local safety belt are unconditional and only
tracker-dependent decisions are skipped (re-review N13). If the adapter
cannot answer the reconcile queries (e.g. `ExecutorConnectionError`: the
gateway is down) the cycle FAILS CLOSED — no decision is ever taken against
unreconciled venue state. Phases IN ORDER:

1. **RECONCILE venue truth before any decision**
   a. ingest resting-stop fills (`poll_stock_fills`) — a stop that filled
      marks its position CLOSED, so the tracker's later exit signal/echo
      for it is a no-op (idempotent; never a second sell). A mid-ingestion
      failure RE-QUEUES the unprocessed fills on the adapter — a raising
      save/alert can never lose a venue fill (re-review N3);
   b. adopt or clear write-ahead ENTRY intents: the journal is persisted
      BEFORE any MOO is placed, and venue order history is checked by the
      deterministic idempotency key `blend-{call_id}-entry` (IB orderRef)
      before anything re-places — a crash between placement and persist
      can never duplicate an entry;
   c. adopt or clear write-ahead BOOK orders the same way — CORE_BUY,
      the rebalance core-sell, and BIL sweeps are journaled with
      deterministic ids `blend-{kind}-{date}-{seq}` before placement, so
      a crash window can never duplicate the book's largest orders
      (re-review N15);
   d. retry cancelling retired stops whose cancel failed (their fills
      alert RED as possible shorts);
   e. re-place any missing protective stop — a STOP_MISSING position is
      alerted loudly every cycle and BLOCKS all new entries until placed.
2. **Staleness guard**: a payload whose `as_of` is more than 5 calendar
   days old (long-weekend tolerant) — or malformed — triggers no new
   decisions; the book is still reconciled and stop-protected.
3. **step()**: with NO usable payload (outage/stale), only the LOCAL
   90-calendar-day time-stop belt runs — it fires during an outage too.
   With a payload, step plans against ONE per-cycle cash ledger: exits
   (each must match BOTH call_id AND symbol — a mismatch or a recycled
   call_id is refused with a RED alert, the tracker-DB-reset tell), the
   90d belt, ratchet-only stop adjustments (trail must be > 0), entries,
   and the band rebalance. All cash needs are funded by AT MOST one BIL
   sell clamped to holdings; if cash + BIL cannot cover the plan, the
   rebalance is deferred first, then the newest entries are skipped — the
   ledger never goes negative and a short-BIL order cannot exist. Under a
   BLEND_BUDGET the idle-cash BIL sweep is clamped to the remaining gross
   headroom.
4. **Execute in order**: exits (stop cancel is non-fatal; a RAISING cancel
   defers the sell; after ANY non-raising cancel queued fills are ingested
   FIRST so a PARTIALLY-filled stop books its filled shares and the MKT
   sell sizes from the venue-truth REMAINING qty — never the step-time
   full qty (adapter review M3); an ambiguous FALSE cancel sells only a
   verified still-held position, re-review N2 — and if the venue-history
   horizon was exceeded (no successful reconcile for > 1 day) that case
   is UNVERIFIABLE: parked + alerted, never sold, adapter review m2) ->
   stop adjustments (place the NEW stop FIRST, cancel the old second —
   never a naked window; a rejected replacement keeps the old stop) ->
   BIL cash-raise -> entries (write-ahead journal, MOO, protective stop
   with in-cycle retry/backoff; an entry is DROPPED when a funding exit
   deferred/failed to book this cycle, and each entry re-checks SETTLED
   sleeve cash minus cash reserved by a pending sweep — phantom proceeds
   are never spent, re-review N5) ->
   rebalance transfer -> core buy -> BIL sweep (all journaled per 1c).
   **Book-order idempotency (adapter review M1)**: while ANY book-order
   journal (CORE_BUY / rebalance core-sell / BIL sweep) is pending
   adoption, step() plans NO new book-level order — a MKT that returns
   `working` (e.g. placed outside RTH) simply waits for pass 1c to adopt
   or clear it; the client id is deterministic PER INTENT (a retry reuses
   the journaled cid), so a working order can never be stacked with
   duplicates cycle after cycle.
   **Missing quotes (adapter review M4)**: a missing/None SPY or BIL
   quote SKIPS the rebalance computation and the equity snapshot that
   cycle (a zeroed ledger side would manufacture a spurious rebalance —
   repo law: no silent zero), with a one-shot alert per outage.
5. **No silent zeros** (repo law): any fill without a fill price is
   UNRECONCILED — the trade is parked in state, nothing books at 0.0,
   P&L for it is blocked, and Telegram gets a RED alert.
6. **/kill reconciles FIRST** (re-review N14): the emergency flatten runs
   the same reconcile pass inside the blend lock before closing, then
   closes only positions STILL actually held (idempotent with a stop fill
   that already happened); an ambiguous stop cancel is verified before
   the MKT sell. If reconcile itself fails, the book is halted but NOT
   blind-flattened — a loud alert asks for manual action.

Adapter contract (pinned, now implemented by BOTH adapters): cancelling a
FILLED order must RAISE (IB errors on it) — bool False is reserved for
not-found/already-cancelled; fill polling is venue-history-based and
supports re-queueing. A shared contract-conformance test suite runs
identically against DryAdapter and the (mocked) IBAdapter.

### Paper-phase adapter: the real IBAdapter stock/ETF surfaces (LANDED)

`app/ib_adapter.py::IBAdapter` now implements the blend3070 stock surfaces
against IB Gateway via ib_async (same synchronous-facade pattern as the
El Nino combo reads):

- `place_stock_order` — SMART/USD stock contracts, qualified once and
  cached; MOO = MarketOrder `tif=OPG`, MKT = MarketOrder DAY,
  STP = StopOrder GTC; signed qty maps to BUY/SELL; `client_order_id`
  maps to IB `orderRef`, and placements DEDUPE against venue order
  history by orderRef before placing — retries are idempotent.
- **Async fills (design decision)**: DryAdapter's synchronous MOO/MKT
  fills are a SIMULATION convenience. The real venue fills a MOO at the
  next open, so placement returns `working` immediately (never blocks on
  OPG) and the write-ahead journal + reconcile passes 2/2b adopt the fill
  from venue order history by orderRef on a later cycle. MKT gets ONE
  bounded synchronous-fill window (5s — liquid ETFs fill well inside it
  during RTH) because the exit/kill paths book from the placement result;
  a MKT that misses the window returns `working` and the exit routes to
  the loud UNRECONCILED path — proceeds are never booked at a faked or
  0.0 price.
- `cancel_stock_order` — the pinned tri-state: FILLED → RAISES (also when
  the fill wins the race mid-cancel), not-found/already-cancelled →
  False, venue-acked cancel → True; an ambiguous ack timeout (10s)
  RAISES — fail closed, the blend defers the dependent sell and the next
  reconcile settles the truth.
- `poll_stock_fills` — drain-once events for DONE protective stops,
  derived from venue order history; partial fills are aggregated per
  order at the share-weighted average price (qty signed by side); an
  unknown price is None, never 0.0; MOO/MKT fills are deliberately NOT
  emitted (the journal reconcile adopts them by orderRef, so they never
  surface as unknown-order alerts). `requeue_stock_fills` restores
  un-ingested events after a mid-ingestion failure.
- `find_stock_order` — orderRef lookup over the session's trades, with a
  reqAllOpenOrders/reqCompletedOrders refresh fallback for orders from a
  previous session. Reconcile also uses it to RE-VERIFY every believed-
  working protective stop each cycle: a stop the venue reports CANCELLED
  (an IB-initiated GTC cancel, e.g. corporate action) demotes the
  position to STOP_MISSING and is re-placed the same pass — never a
  naked position believed protected (adapter review m4).
- **Reconnect with backoff (adapter review M5)**: every surface checks the
  connection and, when the gateway has dropped (its DAILY AUTO-RESTART
  included), attempts a reconnect with exponential backoff (15s doubling
  to a 300s cap — about one attempt per cycle). While down, surfaces
  raise `ExecutorConnectionError` — reconcile raises and the blend cycle
  FAILS CLOSED; once the gateway is back the next cycle reconnects and
  proceeds on its own. The daily restart window is a NON-EVENT: Telegram
  is alerted only when the outage exceeds 30 minutes (one alert, plus a
  recovery notice when the connection returns). Reconnects reuse the same
  clientId, so orderIds stay monotone and the drain-once fill keys
  persist — no re-emission, no double booking. The combo path shares the
  same gate (`spot()` goes through it).
- **Rejected-order lifecycle (adapter review m1)**: a journaled order the
  venue REJECTS (status maps to `cancelled`) is CLEARED by the next
  reconcile — a rejected ENTRY releases its max_open slot, writes an
  `entry_rejected` row to the trade log (display-only, fill_price 0 —
  nothing books) and alerts RED; a rejected BOOK order clears its journal
  and is re-planned as a fresh intent next cycle. Nothing sits
  `pending_*` forever; a republished fire retries cleanly because venue
  dedupe excludes cancelled priors.
- `spot()` quotes any non-ladder symbol (SPY/BIL/sleeve names) as a
  SMART/USD stock.
- **Cached quotes (adapter review M2)**: the ib_async loop belongs to the
  service loop thread. `/status` and `/blend/feed` run on API worker
  threads and NEVER call the adapter — run_cycle refreshes a mark cache
  (prices + timestamp) once per cycle and both endpoints serve that
  cache, reporting its age as `marks_age_s` (staleness shown, not
  hidden). The ONE API path allowed to touch the adapter is `/kill`, and
  only under BLEND_LOCK — the loop thread holds the same lock around
  run_cycle, so the two never pump the ib_async loop concurrently; the
  emergency flatten must act on live venue truth and must not queue
  behind a possibly wedged loop.

SUPERVISED FIRST SESSION: flip `DRY_RUN=false` (with `TRADING_MODE=paper`)
DURING MARKET HOURS and keep eyes on Telegram + `/status` through the
session — watch the first MOO entry get adopted by reconcile after the
open, its GTC stop land, and the first ratchet cancel/replace. Known
loud-but-safe behaviors on the real venue: an exit MKT that misses the 5s
fill window parks the trade UNRECONCILED (RED alert, manual booking); a
service restart can re-emit an already-booked stop fill as an
unknown-order RED alert (noise, never a double booking); a journaled
MOO/MKT the venue REJECTS is cleared by the next reconcile with a RED
alert (entry slot released, book order re-planned — see the
rejected-order lifecycle above). VENUE HISTORY HORIZON: IB serves
current-day executions on connect — an executor blackout spanning a day
or more while a stop fills can exceed what reconcile can see. The
exit/kill flatten paths guard this automatically: when the gap since the
last successful reconcile exceeds 1 day and a stop cancel comes back
"already gone" with nothing verifiable, the position is parked
UNVERIFIABLE (RED alert, nothing sold — a MKT sell could short
already-stopped-out shares); after any multi-day outage, verify positions
against the account manually before booking the parked trades.

Env (all optional until the paper gate):

| env | meaning |
|---|---|
| `BLEND_ENABLED` | default false: service boots exactly as today |
| `TRACKER_URL` | tracker base URL, e.g. `https://research.optic.capital` |
| `TRACKER_API_TOKEN` | PREFERRED: the tracker's dedicated read-only `BLEND_API_TOKEN` — valid for GET /blend3070/intents only, so this service never holds the dashboard password. When set, Basic creds are not sent |
| `TRACKER_USER` / `TRACKER_PASSWORD` | fallback: the tracker's HTTP Basic dashboard login (its DASHBOARD_USER/PASSWORD) — dashboard creds only, no broker credential enters the blend path |
| `BLEND_BUDGET` | per-strategy gross-exposure cap in USD; 0 (default) = disabled. When set, crossing 85% utilization sends a one-time Telegram alert ("review and raise BLEND_BUDGET"), re-armed once utilization drops below 75% |
| `BLEND_BOOK_USD` | initial paper book (default 10,000), split 30/70 at first boot |
| `BLEND_STATE_PATH` | persisted book state (default `./data/blend_state.json`) |
| `READ_TOKEN` | READ-ONLY token gating `GET /blend/feed` (header `X-Read-Token`, constant-time compare). SEPARATE from `EXEC_TOKEN` by design: the feed holder sees book state only — never kill/resume. Empty (default) = the feed endpoint 404s. Set the same value as `BLEND_READ_TOKEN` on the genomics tracker, whose server-side proxy powers the research site's Execution tab |

### Read-only feed: `GET /blend/feed` (the Execution tab)

Public-safe JSON for the research dashboard, gated by `READ_TOKEN`:
`{mode, halted, gate, book: {sleeve_cash, core_qty, bil_qty,
equity_estimate, budget_utilization, initial_book_usd}, positions, trades
(last 200, persisted), equity_curve (one point per cycle day),
unreconciled (count), last_cycle: {date, ok, error}, marks_age_s}`. Marks
come from the loop-thread quote cache (adapter review M2 — the feed never
touches the adapter); `marks_age_s` shows their staleness, null until the
first cycle completes. No credentials, no account ids, no order refs —
gate-tested against a key blacklist. The
tracker proxies it at `/api/execution/feed` behind the dashboard login and
injects the token server-side, so the browser never holds it.
`/health` additionally reports `blend_loop: {ok, last_error_age_s}` when
`BLEND_ENABLED` — a silently failing blend cycle is visible from the
outside.

Casey's paper-credential steps when the paper gate opens:

1. Set `TRACKER_URL` + `TRACKER_API_TOKEN` (generate one, set the same
   value as `BLEND_API_TOKEN` on the tracker; or fall back to
   `TRACKER_USER`/`TRACKER_PASSWORD`, the research-hub login) and flip
   `BLEND_ENABLED=true` with NO TWS credentials —
   OFFLINE: full decision loop, DryAdapter, intents logged + Telegram only.
2. After a clean OFFLINE week, add the PAPER `TWS_USERID`/`TWS_PASSWORD`
   (keep `DRY_RUN=true`): gateway boots, mutations stay simulated.
3. Flip `DRY_RUN=false` with `TRADING_MODE=paper` for real paper orders;
   `/kill` closes blend positions and halts the book alongside the ladder.
   Live is a separate, later decision — same per-leg cutover discipline.

## Service modes (auto-selected at boot)

| mode | condition | behavior |
|---|---|---|
| OFFLINE | no TWS credentials | full decision loop, DryAdapter, no gateway |
| DRY | credentials present, DRY_RUN=true | gateway boots; mutations (and reads) still simulated via DryAdapter |
| PAPER | TRADING_MODE=paper, DRY_RUN=false | real market reads + real paper orders — blend stock/ETF surfaces LANDED (see the paper-phase adapter section); combo placement still pending |
| LIVE | TRADING_MODE=live, DRY_RUN=false | real money (Nov gate, per-leg cutover) |

Control surface: `/health` (public), `/status`, `/kill` (closes all open
legs, halts), `/resume` — token-gated via `X-Exec-Token` header or
`?token=`, same pattern as btc-executor.

## Rollout gates

1. IB adapter vs IBKR PAPER account (free simulated twin, real market data)
2. Paper rehearsal through at least one full trigger cycle
3. Live cutover per leg, DRY_RUN flip discipline

## Account prerequisites (one-time, in IBKR settings)

- Trading permissions: futures, futures options, option spreads
- Paper trading account activated
- October decision: Secure Login System opt-out for the API user
  (headless login; also restricts withdrawals - security win)
