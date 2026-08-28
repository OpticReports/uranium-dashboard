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
| manager.py (El Nino ladder) | NG call spread -> SB put spread -> SLV call spread, triggered + sequential, house-money rolling (see elnino-lab/ELNINO.md) | **PARKED (Casey, 2026-08-24): LADDER_ENABLED defaults false — blend3070 is the ONLY strategy authorized on IBKR.** Re-arming is a Casey decision via the Render dashboard, not a code default; leg-3 SLV also carries an open fidelity question (study says silver/GOLD ratio, leg is outright SLV) to settle before any re-arm |
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
      (`filled` + price → the exit books AT that price, or a PARTIAL of
      exactly the shares the stop covered when it was RESIZED below the
      position — counter-review Z-B: this guard keyed on
      `stop_order_ref`/`stop_missing`, so a resized stop's blackout fill
      booked the FULL position, credited $220 for a $132 sale and
      abandoned 2 real shares with no book row and no stop; `filled`
      without a price → parked UNRECONCILED, never a silent 0.0;
      `working` → the stop never filled). A stop the book does NOT believe
      still rests can never settle a position here: pass 1 (the live fill
      poll) runs first and leaves every booked stop `stop_missing`, so
      double-booking is impossible in either direction. Account POSITIONS
      (`stock_position` sums EVERY account STK row for the symbol) are
      CORROBORATION, never proof, and the full decision matrix is:

      | account rows | this position's stop | outcome |
      |---|---|---|
      | held == booked | `working` | UNPARKED; that stop is kept |
      | held == booked | dead/unknown | UNPARKED as STOP_MISSING; pass 1e re-places it |
      | held < booked, no same-symbol peer | any | parked UNRECONCILED, resting stop RETIRED first (counter-review N1) |
      | held < booked, same-symbol peers exist | any | the shortfall is NOT attributable to one position: NOBODY is parked or sacrificed, all stay flagged (counter-review x5) — but resting SELL cover is ALIGNED PRO RATA to `held`, only as far as the aggregate requires (counter-review ZF-1), and every peer whose resized cover ends below its own qty is flagged UNVERIFIABLE too so the cap cannot drift back (counter-review Z1 / Z-A) |
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
      RED + STOP_MISSING and the placement is RETRIED on every reconcile
      that still sees the shortfall — never silently naked, and never
      restored above the allocation.
      **Protection is never removed that the aggregate did not require**
      (counter-review ZF-1): the reduce leg walks the peers only while the
      RUNNING aggregate still exceeds `held`, and each restore is capped at
      the remaining slack (`held` minus the cover already resting elsewhere
      on that symbol). Aligning every peer unconditionally ran the reduce
      leg in cells that were already compliant, where it is a pure
      subtraction — measured: cover 4 against 5 held became cover **2**,
      because the healthy peer was cut and the zero-cover peer's restore
      was blocked by its own unACKed orphan.
      **"<= its pro-rata allocation" is the explicit exception** to the
      rule that no SELL stop is (re-)placed for an UNVERIFIABLE position.
      Not "strictly reducing": Y1 forbids cover the account may not be able
      to honour, and since the allocation sums to exactly `held`, cover at
      or below it is provably short-safe whichever direction an individual
      peer moved. Cover is
      only ever restored FROM ZERO (never stacked on a stop that already
      rests, never while an unACKed orphan of that position's own cover may
      still rest), because leaving a real position at cover 0 indefinitely
      is the unbounded naked downside of counter-review X3.
      **The cap is DURABLE** (counter-review Z-A): a peer whose TARGET
      cover this round is below its own qty is marked `history_gap` in the
      same breath — the target, not the bare allocation, so a peer the
      round leaves alone is never mothballed for a cap it never took. The
      resize deliberately spans same-symbol peers that are NOT themselves
      flagged (the invariant is a per-symbol aggregate, so their cover
      counts) — and a cap recorded only in `stop_cover_qty` was undone for
      exactly those peers, by pass 4 in the same reconcile when the replace
      was rejected, or by the next ordinary trail ratchet when it
      succeeded (measured: cover 6 -> 7 against 6 held, then venue 6 ->
      **-1**, reported as a plain green "position closed"). The flag buys
      the Y1 ratchet guard, the pass-4 guard, the escalation cadence and
      the restore-full-cover branch with no new state machine; the ratchet
      additionally refuses to touch a stop whose `stop_cover_qty` is below
      its position, so the door has two locks. A mixed flagged/unflagged
      same-symbol pair needs no hand-editing to arise: reconcile pass 2
      adopts a crash-window entry as a brand-new unflagged position beside
      a parked peer.
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
      states honestly whether a resting stop still protects the shares —
      and HOW MANY of them, read off the position itself so that a stop
      RESIZED to cover 3 of 5 shares is never re-described as full
      protection when the cell later flips to conflation (counter-review
      Z-E). A flagged position with no working stop is also marked
      STOP_MISSING with its dead `stop_order_ref` dropped, so `/status`
      (`unverifiable` + `stop_missing` + `unprotected`) and `/blend/feed`
      (per-position `unverifiable` / `unprotected` / `unverified_cycles`,
      plus book-level counts) show it on the Execution tab — pass 1e still
      refuses to re-place its stop. **PARTIAL cover counts as
      `unprotected`** on both surfaces (counter-review Z-F): a position
      whose resting stop was resized below it has real shares standing
      bare, and reporting it as protected is the same silence Z2 removed
      from the alerts;
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
      Only a duplicate the venue still reports **working** is adopted as
      that protection (counter-review ZF-2): a deterministic stop id whose
      prior order already FILLED comes back `{duplicate, status: filled}`
      with NOTHING resting, and adopting it cleared `stop_missing` and
      alerted "protective stop restored" over shares with no stop at the
      venue — reported protected on `/status` and `/blend/feed`, with
      entries unblocked and no re-placement ever. Nothing is placeable
      under a spent id, so the position stays STOP_MISSING and says so.
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

### Gateway supervision + outage ledger (2026-08-24)

The gateway was started as `"$GW" &` and never looked at again: uvicorn is
PID 1, so a gateway that crashed, was OOM-killed, or gave up after a failed
login stayed dead **until a human redeployed** — while `/health` kept
answering 200 (it reports the API, not the gateway), so Render never
restarted the container either. The executor then reconnected forever,
correctly, to a process that no longer existed. That is the difference
between the 3-minute daily restart and the 30+ minute outage on 2026-08-24.

- `start.sh` now SUPERVISES the gateway: restart on exit with 5s→300s
  backoff (env values validated at boot — a non-numeric value used to kill
  the supervisor silently and a negative one made it a fork bomb), reset
  after `IBGW_HEALTHY_S` of clean uptime, a circuit breaker after
  `IBGW_MAX_CONSEC_FAIL` consecutive short-lived starts (a permanently
  unstartable gateway would otherwise attempt ~250–290 IBKR logins/day —
  enough to lock the account), and no restart on a signal exit (143/130).
  Every restart is appended to the restart log (rotated) with its exit code
  and uptime. Honesty note: on a normal container stop Docker signals PID 1
  (uvicorn) only, so the supervisor dies with the container — there is no
  trap, because `exec` discards traps and a claimed-but-inert guarantee is
  worse than none.
- Gateway state deliberately does **not** gate `/health`. Wiring it in would
  make Render restart the whole container — executor included, possibly
  mid-order — on every routine blip, the mandatory daily restart included.
  Supervision restarts the gateway process alone; `/health` only reports.
- `app/outages.py` persists an outage ledger. On Render it MUST live on
  the mounted disk — `OUTAGE_LOG_PATH=/app/data/...` in render.yaml — the
  `./data` default is the ephemeral layer and dies on every deploy,
  including the redeploy that fixes a wedged gateway. Each record carries
  `duration_s`, `blocked_calls` (blocked ADAPTER CALLS, not cycles — it
  scales with book size, so it is a cost signal, not a rate), `alerted`,
  and `ended_by`: `reconnect` (self-healed) vs `process_restart` (it did
  not). That last field separates "IBKR being IBKR" from "our container is
  broken". The ledger may never raise into the trading path: every method
  is exception-shimmed AND every adapter call site is wrapped.

**What this does and does not reduce.** Expect the REPORTED `outages_30d`
count to go UP as the tail collapses: one human-gated multi-hour outage
becomes several short self-healed ones. Count and tail move in opposite
directions — judge on `needed_a_restart` and the duration tail, not the
count. Frequency of underlying incidents is unchanged — IBKR
mandates a daily gateway restart and runs its own maintenance windows, and
those stay irreducible. What collapses is the TAIL: process-death and
login-wedge outages go from unbounded (human-gated) to seconds. Uptime %
is the wrong metric; `cycles_blocked` is the right one, because an outage
that overlaps no decision point costs nothing. Before this there was no
history at all, so no reduction could be claimed OR measured — after ~30
days, `self_healed` vs `needed_a_restart` answers it with arithmetic
instead of assertion.

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

GATEWAY WRITE-ARMING: IBC's ReadOnlyApi DEFAULTS TO ON - reads (quotes,
positions) work while every placeOrder is refused with error 321 ("API
interface is currently in Read-Only mode"). The paper book's first-ever
orders died on this, 2026-08-25. Arm with `READ_ONLY_API=no` in the Render
dashboard (sync:false - an arming var is never a blueprint literal). This
is a REQUIRED step of both the paper phase and go-live; it sits underneath
DRY_RUN in the safety stack: DRY_RUN gates whether the executor SENDS
orders, ReadOnlyApi gates whether the gateway ACCEPTS them.

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
rests cover at or below a position's share of what the venue says the
account holds, so aggregate cover can never exceed it. A stop that DOES
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
| `BLEND_STATE_PATH` | persisted book state (default `./data/blend_state.json`). Saves are atomic: a UNIQUE temp file per write (`mkstemp` in the state directory) + fsync + rename, so two threads saving at once can never clobber each other's partial file or publish truncated JSON (counter-review x11 — a single shared `.tmp` made that promise false; the same treatment now covers `STATE_PATH`, the El Niño ladder book; an unreadable ladder book — and a leg-row SCHEMA DRIFT after a deploy rollback — is PRESERVED as `.corrupt-<ts>` and loud, and a drifted book additionally comes back `halted="SCHEMA_DRIFT"` with every leg field this build understands intact, so `step()` cannot re-OPEN a spread that is still live at the venue, counter-review y2). The BLEND book gets the same treatment on its own position rows (counter-review Z-D — Z1 added `stop_cover_qty`, so a rollback to a build without it hit an unfiltered `BlendPosition(**row)` and came back a FRESH, un-halted book with entries UNBLOCKED while real shares and GTC stops rested at the venue): unknown fields are dropped, fields the row does not carry are DEFAULTED (a renamed or removed field used to raise inside the handler and fall through to the fresh-book branch — counter-review ZF-4; the ladder never had that hole because every `LegState` field is defaulted), a row that still cannot be rebuilt is NAMED and left to the preserved file rather than dropped in silence (counter-review ZF-6), positions/cash/stop refs are kept, the file is preserved as `.corrupt-<ts>` and the book comes back `halted="SCHEMA_DRIFT"` — reconcile still runs and still protects it, only new decisions stop. **What this protects is the NEXT rollback — a book written by a FUTURE build, read by THIS one. It cannot protect a rollback FROM this build to an older one** (counter-review ZF-3): the reader is the older build, the fix is not in it, and the fix is therefore structurally unreachable from this side — see the deploy note under "Rollout gates". Both managers PERSIST that recovered state at load (counter-review Z-J: it used to live in memory until the loop's first save, so a crash in between lost the halt AND the preserved rows) — but only when the `.corrupt-<ts>` rename actually SUCCEEDED, because when it fails the file still sitting at the state path is the only copy of the evidence and the boot save would destroy it (counter-review ZF-7); the halt then lives in memory only and the alert says so. A `SCHEMA_DRIFT` halt is cleared by `/resume` exactly like a KILL — deliberately, because every field this build understands survives the drifted load, so nothing live is re-opened — and the resume alert NAMES the halt it cleared, for the ladder and for the blend book separately (counter-review Z-K). Service writers additionally serialize their read-modify-write under `BLEND_LOCK` (blend) / `MGR_LOCK` (ladder). The state is MODE-TAGGED (`dry:paper` / `real:paper` / `real:live`): on any mode change the previous book is archived alongside and a FRESH book starts, with a Telegram alert — a book's fills are fiction in any other mode (DRY fills at placeholder prices; paper fills aren't live fills), so they must never be reconciled against a venue that never saw them. Losing a `real:*` book that way is NOT routine, and `_current_mode()` reports `dry` whenever creds are merely ABSENT — an unauthenticated boot (a gateway still waiting on its 2FA approval) is enough to trigger it. Such a load is `archived_state_critical` and comes back `halted="MODE_CHANGE_FROM_REAL"`; `/resume` clears THAT halt only and grants NO permission to seed. The next cycle then meets the separate bootstrap guard, which refuses to seed a fresh book while the venue still holds SPY/BIL (or cannot answer) — seeding on top of real holdings takes a SECOND, separately-informed `/resume`. Both belts exist because a fresh book's ledger is structurally blind to venue holdings, so `BLEND_BUDGET` cannot see the double-deployment coming |
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

LIVE SINCE 2026-08-28 (blend3070 only; the ladder stays PARKED). The
staged paper rehearsal below was NOT completed — the paper phase never
produced a fill (quote outage -> ValidationError -> error 321 -> market
data entitlement, fixed in that order), and Casey elected to go straight
to live money once quotes flowed. Recorded here because the rollout
history is otherwise unreadable from the code.

First live session, 2026-08-28 (verified at the venue):
  book $50,000 (BLEND_BOOK_USD) inside a $60,000 cap (BLEND_BUDGET).
  Venue-confirmed fills, 09:58:30-31 ET: CORE 45 SPY @ 772.00 =
  $34,740.00, SWEEP 163 BIL @ 91.66 = $14,940.58 (2 venues), $1.00
  commission each. $49,680.58 deployed, 83% utilization; sleeve flat,
  parked in BIL. Both legs spent to the weight cap without crossing it
  (46 SPY = $35,512 > the $35,000 core; 164 BIL = $15,032 > the $15,000
  sleeve). Total cost of going live: $2.00. No naked positions - SPY/BIL
  are book-level holdings and carry no stops by design.

WHAT LIVE ACTUALLY REQUIRED (none of it obvious from the paper phase):
1. A SECOND IBKR USERNAME for the gateway. IBKR allows one session per
   username, and Casey's primary holds IB Key. The gateway user logs in
   headless; IB Key stays ACTIVE on it (no SLS opt-out was available on
   this account), so every gateway login fires a PUSH to Casey's phone:
   one per deploy, one per IBKR's forced weekend restart, one per crash.
   Unanswered pushes are safe - the supervisor's circuit breaker
   (MAX_CONSEC_FAIL) stops retrying long before IBKR locks the account.
   IB Key must be activated FOR THAT USERNAME in IBKR Mobile; without it
   IBKR falls back to EMAILED codes, which a headless gateway can never
   answer (this cost a day).
2. MARKET DATA IS A SEPARATE PURCHASE, on the gateway user: the
   fee-waived defaults are NOT enough for SPY/BIL over the API. Needed:
   Market Data API Acknowledgement SIGNED, Non-Professional status set,
   plus the US Securities Snapshot and Futures Value Bundle (and the US
   Equity and Options Add-On Streaming Bundle). Activation was same-day
   here, but next-trading-day is the documented norm.
3. `IB_ALLOW_DELAYED=false` is enforced at boot in live mode, and
   `_await_tick` then EXCLUDES the `close` field - so an account without
   a live entitlement reads as "no market price" and the book fails
   closed rather than pricing real orders off yesterday's close. That is
   what a missing subscription looks like from the outside: 21 hours of
   `quotes_missing_for_s` climbing, zero orders, no damage.
4. `DRY_RUN=true` IS NOT A DIAGNOSTIC POSTURE. It swaps in the
   DryAdapter, whose synthetic prices CLEAR the missing-quote counter -
   a false all-clear on the exact thing under test. Diagnose market-data
   problems with the real adapter, fail-closed, or not at all.

`/kill` REMAINS UNVERIFIED AGAINST A REAL VENUE. It was meant to be
proven in the paper week; with a live book it FLATTENS (sells) real
positions, so it can only be tested at a moment when flat is acceptable.
Until then its two-stage path (journal + halt on the API thread, execute
on the loop thread) has never run against IBKR.

The original staged rehearsal, kept for the record and for any FUTURE
strategy's cutover (the per-leg discipline still applies):

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

## Service modes (auto-selected at boot)

| mode | condition | behavior |
|---|---|---|
| OFFLINE | no TWS credentials | full decision loop, DryAdapter, no gateway |
| DRY | credentials present, DRY_RUN=true | gateway boots; mutations (and reads) still simulated via DryAdapter |
| PAPER | TRADING_MODE=paper, DRY_RUN=false | real market reads + real paper orders — blend stock/ETF surfaces LANDED (see the paper-phase adapter section); combo placement still pending |
| LIVE | TRADING_MODE=live, DRY_RUN=false | real money — ACTIVE since 2026-08-28 (blend3070 only, $50k book / $60k cap; ladder parked) |

Control surface: `/health` (public), `/status`, `/kill` (closes all open
ladder legs and halts; the blend flatten is queued to the execution loop
— two-stage, see above), `/resume` — token-gated via `X-Exec-Token`
header or `?token=`, same pattern as btc-executor.

## Rollout gates

1. IB adapter vs IBKR PAPER account (free simulated twin, real market data)
2. Paper rehearsal through at least one full trigger cycle
3. Live cutover per leg, DRY_RUN flip discipline

### Deploy note: ROLLING BACK IS A BOOK-LOSING OPERATION (counter-review ZF-3)

Once this build has written a blend book, `BLEND_STATE_PATH` carries the
`stop_cover_qty` field. **Any build that predates that field reads the file,
raises on the unknown key, and starts a FRESH book** — open positions gone,
`halted` gone, `has_naked_position()` False and entries UNBLOCKED, while real
shares and GTC stops still rest at the venue. The schema-drift handler that
prevents this lives in the build being rolled *away* from, so it cannot help:
the fix protects the forward direction only (a future build's book read by
this one). Deploying this build is therefore a **one-way door for the book**,
and that has to be known before the deploy, not after.

If the executor must be rolled back anyway, do it deliberately, in this
order:

1. **halt first** — `POST /kill` (token-gated), and confirm `/status` shows
   the blend book halted and the flatten resolved;
2. move `BLEND_STATE_PATH` aside by hand (keep it — it is the only record of
   the book) and **then** roll back;
3. **verify positions at the venue** in TWS/Client Portal — every open share
   and every resting GTC stop — and re-seed or reconcile the older build's
   book against what is actually there before clearing the halt.

Skipping any of these resumes trading against a book that does not know what
the account holds.

## Account prerequisites (one-time, in IBKR settings)

- Trading permissions: futures, futures options, option spreads
- Paper trading account activated
- October decision: Secure Login System opt-out for the API user
  (headless login; also restricts withdrawals - security win)
