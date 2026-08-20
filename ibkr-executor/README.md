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
| blend.py (blend3070) | H13 30/70: R2-A sleeve (tracker gate-on fires, 1% sleeve risk, 3xATR GTC trail + 90d time stop, BIL on idle cash) / SPY core, 5pp rebalance band (genomics-alpha-tracker HYPOTHESES.md H11/H13) | OFFLINE scaffold, paper gate pending; BLEND_ENABLED=false default — zero behavior change until flipped |

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
cannot answer the reconcile queries (paper IBAdapter until implemented) the
cycle FAILS CLOSED — no decision is ever taken against unreconciled venue
state. Phases IN ORDER:

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
   defers the sell; an ambiguous FALSE cancel is VERIFIED — queued fills
   are ingested and only a still-held position is sold, re-review N2) ->
   stop adjustments (place the NEW stop FIRST, cancel the old second —
   never a naked window; a rejected replacement keeps the old stop) ->
   BIL cash-raise -> entries (write-ahead journal, MOO, protective stop
   with in-cycle retry/backoff; an entry is DROPPED when a funding exit
   deferred/failed to book this cycle, and each entry re-checks SETTLED
   sleeve cash — phantom proceeds are never spent, re-review N5) ->
   rebalance transfer -> core buy -> BIL sweep (all journaled per 1c).
5. **No silent zeros** (repo law): any fill without a fill price is
   UNRECONCILED — the trade is parked in state, nothing books at 0.0,
   P&L for it is blocked, and Telegram gets a RED alert.
6. **/kill reconciles FIRST** (re-review N14): the emergency flatten runs
   the same reconcile pass inside the blend lock before closing, then
   closes only positions STILL actually held (idempotent with a stop fill
   that already happened); an ambiguous stop cancel is verified before
   the MKT sell. If reconcile itself fails, the book is halted but NOT
   blind-flattened — a loud alert asks for manual action.

Adapter contract (pinned for the paper phase): cancelling a FILLED order
must RAISE (IB errors on it) — bool False is reserved for
not-found/already-cancelled; fill polling should be venue-history-based
(idempotent) or support re-queueing.

Env (all optional until the paper gate):

| env | meaning |
|---|---|
| `BLEND_ENABLED` | default false: service boots exactly as today |
| `TRACKER_URL` | tracker base URL, e.g. `https://research.optic.capital` |
| `TRACKER_API_TOKEN` | PREFERRED: the tracker's dedicated read-only `BLEND_API_TOKEN` — valid for GET /blend3070/intents only, so this service never holds the dashboard password. When set, Basic creds are not sent |
| `TRACKER_USER` / `TRACKER_PASSWORD` | fallback: the tracker's HTTP Basic dashboard login (its DASHBOARD_USER/PASSWORD) — dashboard creds only, no broker credential enters the blend path |
| `BLEND_BUDGET` | per-strategy gross-exposure cap in USD; 0 (default) = disabled |
| `BLEND_BOOK_USD` | initial paper book (default 10,000), split 30/70 at first boot |
| `BLEND_STATE_PATH` | persisted book state (default `./data/blend_state.json`) |

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
| DRY | credentials present, DRY_RUN=true | gateway boots; mutations still simulated |
| PAPER | TRADING_MODE=paper, DRY_RUN=false | real combo orders on the paper account |
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
