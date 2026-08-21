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
   0. blackout-horizon guard (adapter re-review R1): when the gap since
      the last successful reconcile exceeds what venue order history can
      serve (1 day), every held position is flagged UNVERIFIABLE
      (persisted) — a stop may have filled invisibly inside the blackout.
      The flag clears ONLY on positive venue evidence, ranked (counter-
      review N2): the position's OWN stop order FIRST — a lookup by its
      deterministic client id is ORDER-SCOPED, so same-symbol shares held
      in the account outside the blend book can neither fake nor hide it
      (`filled` + price → the exit books AT that price; `filled` without
      one → parked UNRECONCILED, never a silent 0.0; `working` → the stop
      never filled). Account POSITIONS (`stock_position` sums EVERY
      account STK row for the symbol) are CORROBORATION, never proof, and
      the full decision matrix is:

      | account rows | this position's stop | outcome |
      |---|---|---|
      | held == booked | `working` | UNPARKED; that stop is kept |
      | held == booked | dead/unknown | UNPARKED as STOP_MISSING; pass 1e re-places it |
      | held < booked, no same-symbol peer | any | parked UNRECONCILED, resting stop RETIRED first (counter-review N1) |
      | held < booked, same-symbol peers exist | any | the shortfall is NOT attributable to one position: NOBODY is parked or sacrificed, all stay flagged (counter-review x5) — but resting SELL cover is RESIZED PRO RATA down to `held` (counter-review Z1) |
      | held > booked (CONFLATION) | `working` | stays flagged; the working stop is LEFT RESTING |
      | held > booked (CONFLATION) | dead/unknown | stays flagged, marked UNPROTECTED; no new stop is rested |
      | positions unanswerable | any | stays flagged |

      **held > booked is CONFLATION with same-symbol shares held outside
      the blend book, and it makes ownership of the BOOK's shares
      UNPROVABLE — including behind a WORKING stop** (counter-review X1):
      a working stop is order-scoped proof that THAT STOP did not fill, not
      that the book's shares did not leave by another route (manual sale
      out of a pooled position, broker liquidation, transfer). The two
      cases are indistinguishable from here, so the position stays
      UNVERIFIABLE — but its working stop is LEFT RESTING, because
      retiring it would strip real protection from shares that may well be
      the book's. NEVER cleared by timestamp alone; while flagged, exits
      and /kill defer (nothing MKT-sells shares whose stop may already
      have filled — the naked-short path) and no new protective stop is
      placed for the position (a fresh SELL stop on shares that may not be
      the book's is the same harm);
   0a. **COVER INVARIANT (counter-review Z1), the one line to check:**
      for each symbol, the total quantity of blend-placed RESTING SELL
      stops must never exceed the venue-verified `held` for that symbol,
      and **the executor must never CHOOSE to leave cover > held**. A
      single-position shortfall already satisfies it (the stop is retired,
      cover 0) and conflation satisfies it arithmetically (cover <= booked
      < held). The peer-shortfall cell did NOT: 9 shares booked across two
      same-symbol positions with 6 held left 9 shares of SELL stops
      resting, and when they triggered the account went to **-3, a real
      naked short**, reported as two green "position closed" alerts.
      Entries dedupe on `call_id` only, never on symbol, so two calls on
      one ticker is ordinary. That cell now RESIZES cover instead:
      `floor(held * qty / book_qty)` per position, the remainder to the
      largest fractional part (ties: lowest `call_id`), which sums to
      exactly `held` and makes NO attribution claim — the whole point of
      x5. A 0 allocation RETIRES that stop and marks the position
      STOP_MISSING. The reduction is **cancel-old-then-place-smaller** (the
      opposite of the daily ratchet's place-then-cancel: placing first
      would transiently rest 9 + 6 = 15 against 6 held, the exact harm);
      the brief unprotected window is the accepted trade on a position that
      is already flagged and already blocking entries. A failed replace is
      RED + STOP_MISSING and is retried next cycle, never silently naked.
      A strictly-REDUCING resize is the explicit exception to the rule that
      no SELL stop is (re-)placed for an UNVERIFIABLE position: it lowers
      venue exposure, so it closes a short path instead of opening one.
      Where the venue will not ACK the cancel, cover > held can persist and
      is unpreventable — that residual is tracked in `orphan_stop_refs` and
      a fill on it alerts RED as a possible short (counter-review X2); the
      invariant is about what the executor CHOOSES, never a promise about a
      venue that refuses to answer. When the account is restored to the
      booked quantity, a resized stop is retired first and FULL cover
      re-placed, so unparking can never leave the book silently
      under-covered.
   0b. **fail-closed is never fail-SILENT** (counter-review X3). Only the
      operator can resolve the cells above, so a position that stays
      flagged keeps escalating: a 🚨🚨 Telegram alert on the cycle it is
      first detected and then every `UNVERIFIED_REALERT_CYCLES` (4)
      reconciles until it is resolved — the re-armed budget-alarm pattern
      rather than order-safety law #3's literal every-cycle alert, which
      for a cell that can never self-heal would be pure spam. The alert
      states honestly whether a resting stop still protects the shares. A
      flagged position with no working stop is also marked STOP_MISSING
      with its dead `stop_order_ref` dropped, so `/status`
      (`unverifiable` + `stop_missing`) and `/blend/feed` (per-position
      `unverifiable` / `unprotected` / `unverified_cycles`, plus book-level
      counts) show it on the Execution tab — pass 1e still refuses to
      re-place its stop;
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
   d. retry cancelling retired stops whose cancel never ACKed (their fills
      alert RED as possible shorts). Tracking is cleared ONLY by a
      definitively ACKed cancel (`True`): a `False` is the venue saying
      "not found / already cancelled", which after a session boundary
      cannot be told apart from a resting order it can no longer resolve
      by ref — clearing on it is how an abandoned -5 stop was lost and
      later triggered into a 2-share account (counter-review X2). A ref
      that is unsafe to cancel (the persisted, session-scoped `orderId` of
      a stop the venue cannot locate by client id, counter-review x13) is
      watched but never blind-cancelled. The escalation alert is re-armed
      every `ORPHAN_REALERT_CYCLES` (4) retries: loud when recorded, then
      periodic — never per-cycle spam, never silent;
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
6. **/kill is TWO-STAGE** (adapter re-review R2): the HTTP handler never
   touches the venue — ib_async binds its event loop to the thread that
   owns the connection (the blend loop thread), so an API-thread flatten
   would pump a fresh loop against the shared transport, time out every
   wait, mis-park healthy stops as "likely filled", and risk session
   corruption. Stage 1 (the handler): journal a persisted flatten request
   (it survives a restart, same doctrine as `pending_entries`), halt the
   book immediately (no new entries), wake the loop, and answer honestly:
   "halt engaged; flatten QUEUED". Stage 2 (the loop thread, seconds
   later): reconcile FIRST (re-review N14 — stop fills book before
   anything sells, so only positions STILL actually held close), then
   flatten with all the standing guards: a RAISING stop cancel parks the
   position (K-d — never a MKT sell on a likely-filled stop), and
   R1-UNVERIFIABLE positions stay parked untouched. The completion alert
   states exactly what closed vs what parked — the kill switch never
   overclaims. If reconcile fails, the book stays halted, the request
   stays journaled, and every failing cycle alerts loudly until the
   flatten lands; /resume clears a still-queued request (a stale kill
   must never flatten a resumed book).

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
  hidden). NO API path touches the adapter — `/kill` included (adapter
  re-review R2): it journals a flatten request under BLEND_LOCK and the
  loop thread, owner of the ib_async event loop, executes it on its next
  (immediately woken) iteration — see the two-stage `/kill` above.

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
rejected-order lifecycle above). VENUE HISTORY HORIZON (adapter re-review
R1): IB serves current-day executions on connect — an executor blackout
spanning a day or more while a stop fills can exceed what reconcile can
see FOREVER, not just on the first recovered cycle. The first reconcile
after such a gap therefore flags every held position UNVERIFIABLE
(persisted, restart-safe) and only POSITIVE venue evidence clears it, in
rank order: the position's own STOP ORDER (order-scoped, immune to
same-symbol shares held elsewhere in the account — a priced `filled`
books the exit at that price, an unpriced one parks it UNRECONCILED, a
`working` one proves the stop never filled), then `stock_position`
(account positions — no history horizon) as CORROBORATION that the
shares are actually there. Fewer shares than booked parks the trade
UNRECONCILED for manual booking after RETIRING its resting stop (never
abandoning a -qty order the book no longer tracks), and the park alert
states what the retire ACTUALLY did — cancelled, uncancelled, ambiguous,
or unlocatable — never a flat "stop retired" (counter-review X4); more
shares than booked is external-share CONFLATION and it verifies nothing
on its own **even behind a working stop**, so the position stays flagged
indefinitely and keeps escalating on a re-armed cadence until the
operator resolves it (see the matrix in phase 1.0/1.0b). While flagged,
exits and /kill defer with a RED alert and no protective stop is
(re-)placed — nothing is ever MKT-sold, and no NEW or RAISED SELL stop is
ever rested, against shares whose ownership is unproven (the naked-short
path probe A1 demonstrated, and the counter-review's N1/N2/X1 variants of
it). The single exception is the Z1 pro-rata resize above, which only ever
REPLACES a resting stop with a SMALLER one so that aggregate cover can
never exceed the shares the venue says the account holds. A stop that DOES
fill on a flagged position is still booked (a fill is order-scoped venue
truth) but is never reported green: the alert states that the position was
UNVERIFIABLE and that under conflation the shares just sold may have been
the operator's own (counter-review Z2). Such a
position blocks all new entries (`has_naked_position`), so an unresolved
conflation wedges the sleeve until it is cleared by hand — the
deliberate, documented cost of not guessing.

Env (all optional until the paper gate):

| env | meaning |
|---|---|
| `BLEND_ENABLED` | default false: service boots exactly as today |
| `TRACKER_URL` | tracker base URL, e.g. `https://research.optic.capital` |
| `TRACKER_API_TOKEN` | PREFERRED: the tracker's dedicated read-only `BLEND_API_TOKEN` — valid for GET /blend3070/intents only, so this service never holds the dashboard password. When set, Basic creds are not sent |
| `TRACKER_USER` / `TRACKER_PASSWORD` | fallback: the tracker's HTTP Basic dashboard login (its DASHBOARD_USER/PASSWORD) — dashboard creds only, no broker credential enters the blend path |
| `BLEND_BUDGET` | per-strategy gross-exposure cap in USD; 0 (default) = disabled. When set, crossing 85% utilization sends a one-time Telegram alert ("review and raise BLEND_BUDGET"), re-armed once utilization drops below 75% |
| `BLEND_BOOK_USD` | initial paper book (default 10,000), split 30/70 at first boot |
| `BLEND_STATE_PATH` | persisted book state (default `./data/blend_state.json`). Saves are atomic: a UNIQUE temp file per write (`mkstemp` in the state directory) + fsync + rename, so two threads saving at once can never clobber each other's partial file or publish truncated JSON (counter-review x11 — a single shared `.tmp` made that promise false; the same treatment now covers `STATE_PATH`, the El Niño ladder book; an unreadable ladder book — and a leg-row SCHEMA DRIFT after a deploy rollback — is PRESERVED as `.corrupt-<ts>` and loud, and a drifted book additionally comes back `halted="SCHEMA_DRIFT"` with every leg field this build understands intact, so `step()` cannot re-OPEN a spread that is still live at the venue, counter-review y2). Service writers additionally serialize their read-modify-write under `BLEND_LOCK` (blend) / `MGR_LOCK` (ladder). The state is MODE-TAGGED (`dry:paper` / `real:paper` / `real:live`): on any mode change the previous book is archived alongside and a FRESH book starts, with a Telegram alert — a book's fills are fiction in any other mode (DRY fills at placeholder prices; paper fills aren't live fills), so they must never be reconciled against a venue that never saw them |
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
   `/kill` halts the blend book immediately and queues the flatten for
   the execution loop (two-stage — the completion alert says what closed
   vs parked). VERIFY `/kill` EARLY in the paper week (re-review R2).
   Live is a separate, later decision — same per-leg cutover discipline.

## Service modes (auto-selected at boot)

| mode | condition | behavior |
|---|---|---|
| OFFLINE | no TWS credentials | full decision loop, DryAdapter, no gateway |
| DRY | credentials present, DRY_RUN=true | gateway boots; mutations (and reads) still simulated via DryAdapter |
| PAPER | TRADING_MODE=paper, DRY_RUN=false | real market reads + real paper orders — blend stock/ETF surfaces LANDED (see the paper-phase adapter section); combo placement still pending |
| LIVE | TRADING_MODE=live, DRY_RUN=false | real money (Nov gate, per-leg cutover) |

Control surface: `/health` (public), `/status`, `/kill` (closes all open
ladder legs and halts; the blend flatten is queued to the execution loop
— two-stage, see above), `/resume` — token-gated via `X-Exec-Token`
header or `?token=`, same pattern as btc-executor.

## Rollout gates

1. IB adapter vs IBKR PAPER account (free simulated twin, real market data)
2. Paper rehearsal through at least one full trigger cycle
3. Live cutover per leg, DRY_RUN flip discipline

## Account prerequisites (one-time, in IBKR settings)

- Trading permissions: futures, futures options, option spreads
- Paper trading account activated
- October decision: Secure Login System opt-out for the API user
  (headless login; also restricts withdrawals - security win)
