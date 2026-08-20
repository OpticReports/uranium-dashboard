"""blend3070 manager — the H13 30/70 book's execution brain (venue-agnostic).

Runs the R2-A 30/70 construction validated in replay (genomics-alpha-tracker
docs/BACKTEST_VARIANTS_R2.md + HYPOTHESES.md H11/H13):
  30% sleeve : the tracker's gate-on auto-call fires, 1% of SLEEVE equity
               risked per call, <=10 open, exits by 3.0xATR trailing stop
               (daily GTC cancel/replace) or 90-calendar-day time stop;
               idle sleeve cash parked in BIL.
  70% core   : SPY buy-and-hold.
  Rebalance  : back to 30/70 when the sleeve weight drifts beyond +-5pp.

Separation of powers (CLAUDE.md law): the TRACKER is the keyless decision
brain — it publishes fires, gate state, and per-call R2-A trail levels at
GET {TRACKER_URL}/blend3070/intents. THIS manager owns the book: positions,
sleeve equity, SPY/BIL holdings, and all dollar sizing live here and are
never sent back to the tracker (the poll is a bare GET). The tracker's
login gate is HTTP Basic, so the poll authenticates with the dashboard
credentials TRACKER_USER / TRACKER_PASSWORD (dashboard login only — no
broker credential is read anywhere in this module).

ORDER-SAFETY LAWS (counter-agent review, merge-blocking):
  1. RECONCILIATION FIRST: every cycle ingests venue truth (resting-stop
     fills, orphaned orders from a crash window, failed cancels, missing
     protective stops) BEFORE any new decision. A tracker exit for a
     position the venue's stop already closed is a no-op (idempotent).
     EVERY cycle means every cycle: a tracker outage never skips the
     reconcile pass or the local 90-day belt — run_cycle(payload=None) is
     the outage path, and only tracker-DEPENDENT decisions are skipped.
  2. SINGLE PER-CYCLE CASH LEDGER: all cash needs (entries + rebalance)
     are planned together and funded by AT MOST ONE BIL sell, clamped to
     holdings; if the ledger cannot fund everything, the rebalance is
     deferred first, then the newest entries are skipped — the ledger
     never goes negative and a short-BIL order can never be emitted.
     Deferred/unreconciled exit proceeds are NOT spendable: if a funding
     exit does not actually book this cycle, the remaining entries are
     dropped, and each entry re-checks SETTLED cash before placement.
  3. A position without a working protective stop is STOP_MISSING: alerted
     loudly, retried every cycle, and it BLOCKS all new entries.
  4. Exit/stop instructions must match BOTH call_id AND symbol against the
     held position; a mismatch (tracker DB reset) is refused with a RED
     alert, never acted on.
  5. Stop replace is place-NEW-first, cancel-old-second: there is never a
     naked window. A rejected replacement keeps the old stop.
  6. ALL order placement is write-ahead journaled with a deterministic
     client_order_id — sleeve entries (blend-{call_id}-entry) AND the
     book-level CORE_BUY / rebalance core-sell / BIL sweep orders
     (blend-{kind}-{date}-{seq}); boot/crash reconcile checks venue order
     history before anything re-places.
  7. A fill without a fill price is UNRECONCILED: nothing is ever booked
     at a silent 0.0 — the trade is parked for manual reconciliation and
     alerted RED.
  8. An ambiguous stop cancel (False / "already gone") is VERIFIED before
     any market sell: queued fills are ingested and only a position the
     book still holds is sold — idempotent with a stop fill that won the
     race. The paper/live adapter contract pins the unambiguous case:
     cancelling a FILLED order must RAISE, never return False.

Same state-machine idioms as LadderManager: persisted JSON state, step()
emitting order intents, on_* execution callbacks, deduped event log. The
adapter executes; run_cycle() is the loop body service.py calls.

SIZING REFERENCE (documented decision): shares = floor(risk$ / per-share
risk) where risk$ = risk_frac x sleeve equity and per-share risk =
entry_ref - trail_level, with entry_ref = the FIRE-DAY CLOSE the tracker
published (the R2-A entry convention) and trail_level = the tracker's
day-one trail (entry - 3xATR14 through the fire day). The MOO fill may
differ from entry_ref; the risk unit stays frozen at the reference, exactly
as the replay accounted entries at fire-day closes.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import date

import httpx

logger = logging.getLogger(__name__)

CORE = "SPY"
CASH_VEHICLE = "BIL"
TARGET_SLEEVE = 0.30
BAND = 0.05
MAX_OPEN = 10
RISK_FRAC = 0.01
TIME_STOP_DAYS = 90
MIN_ORDER_USD = 50.0        # dust guard: never emit orders smaller than this
STOP_EPS = 1e-6             # stop cancel/replace only on a real level change
CASH_EPS = 1e-6             # ledger tolerance
STOP_RETRY_ATTEMPTS = 3     # in-cycle protective-stop placement retries
STOP_RETRY_SLEEP_S = 1.0    # backoff base between retries (tests patch to 0)
STALE_PAYLOAD_DAYS = 5      # as_of older than this vs today -> no decisions
                            # (5, not the review's 2: a Monday poll after a
                            # long holiday weekend legitimately sees a 4-day-
                            # old last trading day; reconciliation still runs)


def entry_client_id(call_id: int) -> str:
    return f"blend-{call_id}-entry"


def stop_client_id(call_id: int, level: float) -> str:
    return f"blend-{call_id}-stp-{level:.4f}"


def exit_client_id(call_id: int) -> str:
    return f"blend-{call_id}-exit"


@dataclass
class BlendPosition:
    call_id: int
    symbol: str
    qty: int
    entry_ref: float            # fire-day close (sizing reference)
    fill_price: float           # actual MOO fill
    entry_date: str             # ISO
    time_stop: str              # ISO, entry_date + 90 CALENDAR days
    stop_level: float
    stop_order_ref: str | None = None
    stop_missing: bool = False  # placement failed; retried every cycle and
                                # blocks ALL new entries until protected


@dataclass
class BlendState:
    initialized: bool = False
    positions: dict = field(default_factory=dict)   # str(call_id) -> BlendPosition
    entered_ids: list = field(default_factory=list)  # every call_id ever entered
                                                     # (bounded at 2000: recycled-id
                                                     # detection beyond that horizon
                                                     # is a documented tradeoff)
    entered_symbols: dict = field(default_factory=dict)  # str(call_id) -> symbol
    pending_entries: dict = field(default_factory=dict)  # write-ahead journal:
                                                         # str(call_id) -> {intent, date}
    pending_book_orders: dict = field(default_factory=dict)  # write-ahead journal for
                                                             # CORE_BUY / rebalance
                                                             # core-sell / BIL sweep:
                                                             # client_id -> record
    book_order_seq: int = 0     # monotone id sequence for book-level orders
    unreconciled: dict = field(default_factory=dict)     # trades with no fill price:
                                                         # key -> frozen record (manual)
    orphan_stop_refs: dict = field(default_factory=dict)  # retired stops whose
                                                          # cancel failed (retry)
    sleeve_cash: float = 0.0
    bil_qty: int = 0
    spy_qty: int = 0
    core_cash: float = 0.0
    halted: str | None = None   # KILL | None
    events: list = field(default_factory=list)


class Blend3070Manager:
    def __init__(self, cfg, state_path: str):
        self.cfg = cfg
        self.state_path = state_path
        self.state = self._load()

    # ---------- persistence (LadderManager pattern) ----------

    def _load(self) -> BlendState:
        try:
            raw = json.load(open(self.state_path))
            st = BlendState(
                initialized=raw.get("initialized", False),
                entered_ids=raw.get("entered_ids", []),
                entered_symbols=raw.get("entered_symbols", {}),
                pending_entries=raw.get("pending_entries", {}),
                pending_book_orders=raw.get("pending_book_orders", {}),
                book_order_seq=raw.get("book_order_seq", 0),
                unreconciled=raw.get("unreconciled", {}),
                orphan_stop_refs=raw.get("orphan_stop_refs", {}),
                sleeve_cash=raw.get("sleeve_cash", 0.0),
                bil_qty=raw.get("bil_qty", 0),
                spy_qty=raw.get("spy_qty", 0),
                core_cash=raw.get("core_cash", 0.0),
                halted=raw.get("halted"),
            )
            st.positions = {k: BlendPosition(**v)
                            for k, v in raw.get("positions", {}).items()}
            st.events = raw.get("events", [])[-300:]
            return st
        except Exception:  # noqa: BLE001
            return BlendState()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        json.dump({"initialized": self.state.initialized,
                   "positions": {k: asdict(v)
                                 for k, v in self.state.positions.items()},
                   "entered_ids": self.state.entered_ids,
                   "entered_symbols": self.state.entered_symbols,
                   "pending_entries": self.state.pending_entries,
                   "pending_book_orders": self.state.pending_book_orders,
                   "book_order_seq": self.state.book_order_seq,
                   "unreconciled": self.state.unreconciled,
                   "orphan_stop_refs": self.state.orphan_stop_refs,
                   "sleeve_cash": self.state.sleeve_cash,
                   "bil_qty": self.state.bil_qty,
                   "spy_qty": self.state.spy_qty,
                   "core_cash": self.state.core_cash,
                   "halted": self.state.halted,
                   "events": self.state.events[-300:]},
                  open(self.state_path, "w"), indent=1)

    def _event(self, level: str, msg: str) -> None:
        last = self.state.events[-1] if self.state.events else None
        if last and last.get("msg") == msg:
            return
        self.state.events.append({"ts": int(time.time()), "level": level,
                                  "msg": msg})
        logger.info("[blend] %s", msg)

    # ---------- valuation (executor-side only; never leaves this service) ----

    def _mark_price(self, pos: BlendPosition, prices: dict[str, float]) -> float:
        """Conservative mark for an unquoted held name: the working stop
        level (the near-guaranteed exit), never the entry reference — a
        failed quote on a cratered name must not overstate sleeve equity or
        the per-entry risk$ built on it (counter-agent minor finding)."""
        return prices.get(pos.symbol,
                          pos.stop_level if pos.stop_level > 0 else pos.entry_ref)

    def sleeve_value(self, prices: dict[str, float]) -> float:
        v = self.state.sleeve_cash + self.state.bil_qty * prices.get(CASH_VEHICLE, 0.0)
        for pos in self.state.positions.values():
            v += pos.qty * self._mark_price(pos, prices)
        return v

    def core_value(self, prices: dict[str, float]) -> float:
        return self.state.core_cash + self.state.spy_qty * prices.get(CORE, 0.0)

    def book_value(self, prices: dict[str, float]) -> float:
        return self.sleeve_value(prices) + self.core_value(prices)

    def gross_exposure(self, prices: dict[str, float]) -> float:
        """Everything at risk in the market (holdings, ex-cash) — what the
        BLEND_BUDGET cap binds on."""
        v = self.state.bil_qty * prices.get(CASH_VEHICLE, 0.0)
        v += self.state.spy_qty * prices.get(CORE, 0.0)
        for pos in self.state.positions.values():
            v += pos.qty * self._mark_price(pos, prices)
        return v

    def has_naked_position(self) -> bool:
        """Any held position without a working protective stop (safety-first:
        blocks all new entries until resolved)."""
        return any(p.stop_missing or not p.stop_order_ref
                   for p in self.state.positions.values())

    # ---------- the decision step ----------

    def step(self, today: str, payload: dict | None,
             prices: dict[str, float]) -> list[dict]:
        """One evaluation against the tracker's intent payload. Returns order
        intents (plus ALERT intents for refused/suspicious instructions);
        state changes only via the on_* callbacks (plus first-boot seeding
        and halt bookkeeping, mirroring LadderManager).

        Intents come back in EXECUTION order: exits -> stop adjustments ->
        BIL cash-raise -> entries -> rebalance transfer -> core buy -> BIL
        sweep — so cash is always raised before it is spent."""
        intents: list[dict] = []
        alerts: list[str] = []
        st = self.state
        if st.halted:
            return intents
        if payload is None:
            # Tracker unreachable or stale: NO tracker-dependent decision is
            # taken, but the LOCAL safety belt still runs — the 90-calendar-
            # day time stop is this executor's own clock and must fire even
            # (especially) during a tracker outage (counter-agent N13).
            for key, pos in st.positions.items():
                if today > pos.time_stop:
                    intents.append({"action": "EXIT", "call_id": pos.call_id,
                                    "symbol": pos.symbol, "qty": pos.qty,
                                    "stop_order_ref": pos.stop_order_ref,
                                    "reason": "time_stop"})
            return intents

        params = payload.get("book_params") or {}
        max_open = min(MAX_OPEN, params.get("max_open", MAX_OPEN))
        risk_frac = params.get("risk_frac", RISK_FRAC)
        band = params.get("band", BAND)
        target = (payload.get("rebalance") or {}).get("target", TARGET_SLEEVE)
        budget = getattr(self.cfg, "blend_budget", 0.0) or 0.0

        if not st.initialized:
            book = getattr(self.cfg, "blend_book_usd", 10_000.0)
            if budget > 0:
                book = min(book, budget)
            st.sleeve_cash = target * book
            st.core_cash = (1.0 - target) * book
            st.initialized = True
            self._event("INFO", f"book initialized: ${book:,.0f} "
                                f"({target:.0%} sleeve / {1 - target:.0%} core)")

        stops_by_id = {s["call_id"]: s for s in payload.get("stops", [])}
        exiting: set[str] = set()
        exit_intents: list[dict] = []
        bil_px = prices.get(CASH_VEHICLE, 0.0)
        projected_cash = st.sleeve_cash
        funds = projected_cash + st.bil_qty * bil_px  # cash + BIL, spendable

        # 1) exits the tracker signalled (trail pierced / time stop reached),
        #    reconciled against OUR book: act only on call_ids we hold, and
        #    ONLY when the row's symbol matches the held position — a
        #    mismatch means recycled call_ids (tracker DB reset): refuse.
        for ex in payload.get("exits", []):
            key = str(ex["call_id"])
            pos = st.positions.get(key)
            if pos is None or key in exiting:
                continue
            if ex.get("symbol") != pos.symbol:
                msg = (f"REFUSED exit for call {ex['call_id']}: tracker says "
                       f"{ex.get('symbol')!r} but book holds {pos.symbol} — "
                       f"tracker DB reset? Position kept; manual review needed")
                self._event("RED", msg)
                alerts.append(msg)
                continue
            exit_intents.append({"action": "EXIT", "call_id": pos.call_id,
                                 "symbol": pos.symbol, "qty": pos.qty,
                                 "stop_order_ref": pos.stop_order_ref,
                                 "reason": ex.get("reason", "trail")})
            exiting.add(key)
            proceeds = pos.qty * self._mark_price(pos, prices)
            projected_cash += proceeds
            funds += proceeds

        # 2) executor-side time-stop belt: our own 90-calendar-day clock —
        #    the backstop the intents contract names (a tracker outage or a
        #    reconciliation gap must never leave a position open past day 90).
        for key, pos in st.positions.items():
            if key in exiting or today <= pos.time_stop:
                continue
            exit_intents.append({"action": "EXIT", "call_id": pos.call_id,
                                 "symbol": pos.symbol, "qty": pos.qty,
                                 "stop_order_ref": pos.stop_order_ref,
                                 "reason": "time_stop"})
            exiting.add(key)
            proceeds = pos.qty * self._mark_price(pos, prices)
            projected_cash += proceeds
            funds += proceeds

        # 3) daily GTC stop adjustment (place-new-then-cancel-old). The trail
        #    RATCHETS UP ONLY — a published level below the working stop is
        #    never applied; a non-positive level is a data bug, never placed;
        #    a symbol mismatch on the stop row is refused like an exit.
        adjust_intents: list[dict] = []
        for key, pos in st.positions.items():
            if key in exiting:
                continue
            s = stops_by_id.get(pos.call_id)
            if s is None:
                continue
            if s.get("symbol") != pos.symbol:
                msg = (f"REFUSED stop for call {pos.call_id}: tracker says "
                       f"{s.get('symbol')!r} but book holds {pos.symbol} — "
                       f"tracker DB reset? Working stop kept")
                self._event("RED", msg)
                alerts.append(msg)
                continue
            lvl = s.get("trail_level")
            if lvl is None or lvl <= 0:
                self._event("WARN", f"non-positive trail {lvl} for "
                                    f"{pos.symbol} (call {pos.call_id}): ignored")
                continue
            if lvl > pos.stop_level + STOP_EPS:
                adjust_intents.append({"action": "ADJUST_STOP",
                                       "call_id": pos.call_id,
                                       "symbol": pos.symbol, "qty": pos.qty,
                                       "old_ref": pos.stop_order_ref,
                                       "stop_level": lvl,
                                       "reason": f"trail ratchet "
                                                 f"{pos.stop_level:.2f}"
                                                 f" -> {lvl:.2f}"})

        # 4) entries: gate-on candidate fires, sized in dollars HERE.
        #    sleeve_eq is frozen pre-entries (no equity circularity — a
        #    fire's own outflow never feeds its or a sibling's sizing).
        entry_intents: list[dict] = []
        gate_on = (payload.get("gate") or {}).get("xbi_above_200dma_prior") is not False
        sleeve_eq = self.sleeve_value(prices)
        open_count = len(st.positions) - len(exiting) + len(st.pending_entries)
        projected_gross = self.gross_exposure(prices)
        for it in exit_intents:      # exits convert holdings back to cash
            pos = st.positions[str(it["call_id"])]
            projected_gross -= pos.qty * self._mark_price(pos, prices)
        naked = self.has_naked_position()
        if gate_on and naked and payload.get("entries"):
            msg = ("entries BLOCKED: a held position has no working stop "
                   "(STOP_MISSING) — protect the book before adding risk")
            self._event("RED", msg)
            alerts.append(msg)
        if gate_on and not naked:
            for e in payload.get("entries", []):
                key = str(e["call_id"])
                if key in st.positions or key in st.pending_entries:
                    continue
                if e["call_id"] in st.entered_ids:
                    prev = st.entered_symbols.get(key)
                    if prev is not None and prev != e["symbol"]:
                        msg = (f"call_id {e['call_id']} RECYCLED: previously "
                               f"{prev}, republished as {e['symbol']} — "
                               f"tracker DB reset? Entry refused; manual "
                               f"review needed")
                        self._event("RED", msg)
                        alerts.append(msg)
                    continue
                if open_count + len(entry_intents) >= max_open:
                    self._event("INFO", f"cap {max_open} open: skipping "
                                        f"{e['symbol']} (call {e['call_id']})")
                    continue
                entry_ref = e.get("entry_ref")
                srow = stops_by_id.get(e["call_id"])
                if srow is not None and srow.get("symbol") != e["symbol"]:
                    msg = (f"REFUSED entry {e['symbol']} (call {e['call_id']}): "
                           f"stop row names {srow.get('symbol')!r} — "
                           f"tracker DB inconsistency")
                    self._event("RED", msg)
                    alerts.append(msg)
                    continue
                trail = (srow or {}).get("trail_level")
                if (not entry_ref or trail is None or trail <= 0
                        or entry_ref <= trail):
                    self._event("WARN", f"no sizing reference for {e['symbol']} "
                                        f"(call {e['call_id']}): skipped")
                    continue
                risk_usd = risk_frac * sleeve_eq
                qty = int(risk_usd // (entry_ref - trail))
                avail = max(funds, 0.0)
                qty = min(qty, int(avail // entry_ref)) if entry_ref > 0 else 0
                if qty <= 0:
                    self._event("INFO", f"{e['symbol']} sized to zero: skipped")
                    continue
                cost = qty * entry_ref
                # Budget binds on projected gross; the BIL-funded slice of an
                # entry swaps one holding for another (gross-neutral) — only
                # the cash-funded slice adds exposure.
                from_cash = min(max(projected_cash, 0.0), cost)
                if budget > 0 and projected_gross + from_cash > budget:
                    self._event("WARN", f"BLEND_BUDGET ${budget:,.0f} would be "
                                        f"exceeded: {e['symbol']} entry blocked")
                    continue
                entry_intents.append({"action": "ENTER", "call_id": e["call_id"],
                                      "symbol": e["symbol"], "qty": qty,
                                      "entry_ref": entry_ref, "stop_level": trail,
                                      "time_stop_days": TIME_STOP_DAYS,
                                      "reason": f"gate-on fire {e.get('flag_type')} "
                                                f"({e.get('fire_date')}), risk "
                                                f"${risk_usd:,.0f} @ "
                                                f"{entry_ref - trail:.2f}/sh"})
                projected_gross += from_cash
                projected_cash -= cost
                funds -= cost

        # 5) band rebalance (~1x/year expected): executor-side weights.
        rebalance_intent = None
        book = self.book_value(prices)
        if book > 0:
            w = self.sleeve_value(prices) / book
            if abs(w - target) > band:
                usd = round(abs(w - target) * book, 2)
                direction = "core_to_sleeve" if w < target else "sleeve_to_core"
                rebalance_intent = {"action": "REBALANCE",
                                    "direction": direction, "usd": usd,
                                    "reason": f"sleeve weight {w:.1%} outside "
                                              f"{target:.0%} +-{band:.0%} band"}
                if direction == "core_to_sleeve":
                    # SPY sale proceeds land in sleeve cash -> swept to BIL.
                    projected_cash += usd
                    funds += usd
                else:
                    projected_cash -= usd
                    funds -= usd

        # 6) SINGLE PER-CYCLE CASH LEDGER resolution: everything above was
        #    planned against one projected ledger; fund the total shortfall
        #    with AT MOST one BIL sell clamped to holdings. If cash + BIL
        #    cannot cover the plan, SKIP lowest-priority actions — the
        #    rebalance first, then the newest entries — never overdraw.
        if (funds < -CASH_EPS and rebalance_intent is not None
                and rebalance_intent["direction"] == "sleeve_to_core"):
            projected_cash += rebalance_intent["usd"]
            funds += rebalance_intent["usd"]
            self._event("WARN", f"rebalance deferred: cycle cash ledger cannot "
                                f"fund the ${rebalance_intent['usd']:,.0f} "
                                f"sleeve->core transfer alongside entries")
            rebalance_intent = None
        while funds < -CASH_EPS and entry_intents:
            dropped = entry_intents.pop()               # newest entry first
            cost = dropped["qty"] * dropped["entry_ref"]
            projected_cash += cost
            funds += cost
            self._event("WARN", f"entry {dropped['symbol']} "
                                f"(call {dropped['call_id']}) skipped: cycle "
                                f"cash ledger cannot fund it")
        bil_sell = 0
        if projected_cash < -CASH_EPS and bil_px > 0 and st.bil_qty > 0:
            bil_sell = min(st.bil_qty, math.ceil(-projected_cash / bil_px))
            projected_cash += bil_sell * bil_px
        if projected_cash < -CASH_EPS:
            # Belt (should be unreachable): refuse rather than overdraw.
            self._event("RED", "cash ledger still negative after BIL funding: "
                               "dropping remaining sleeve actions")
            for dropped in entry_intents:
                projected_cash += dropped["qty"] * dropped["entry_ref"]
            entry_intents = []
            if (rebalance_intent is not None
                    and rebalance_intent["direction"] == "sleeve_to_core"):
                projected_cash += rebalance_intent["usd"]
                rebalance_intent = None

        # 7) core: idle core cash is always fully in SPY (buy-and-hold).
        spy_px = prices.get(CORE, 0.0)
        core_cash_proj = st.core_cash + (
            rebalance_intent["usd"]
            if (rebalance_intent is not None
                and rebalance_intent["direction"] == "sleeve_to_core") else 0.0)
        core_buy = None
        if spy_px > 0 and core_cash_proj > max(MIN_ORDER_USD, spy_px):
            core_buy = {"action": "CORE_BUY", "symbol": CORE,
                        "qty": int(core_cash_proj // spy_px),
                        "reason": "invest idle core cash"}

        # 8) BIL sweep of idle sleeve cash (buy) from the resolved ledger.
        #    Under a budget cap, the sweep is clamped to the remaining gross
        #    headroom — economically cash, but gross must never drift above
        #    BLEND_BUDGET via the cash vehicle (counter-agent minor).
        sweep_buy = None
        if bil_px > 0 and projected_cash > max(MIN_ORDER_USD, bil_px):
            sweep_qty = int(projected_cash // bil_px)
            if budget > 0:
                gross_proj = projected_gross
                if (rebalance_intent is not None
                        and rebalance_intent["direction"] == "core_to_sleeve"):
                    gross_proj -= rebalance_intent["usd"]   # SPY sold for cash
                if core_buy is not None and spy_px > 0:
                    gross_proj += core_buy["qty"] * spy_px
                headroom = budget - gross_proj
                sweep_qty = min(sweep_qty, int(max(headroom, 0.0) // bil_px))
            if sweep_qty > 0:
                sweep_buy = {"action": "SWEEP", "symbol": CASH_VEHICLE,
                             "qty": sweep_qty,
                             "reason": "sweep idle sleeve cash to BIL"}

        # Assemble in EXECUTION order (cash raised before it is spent).
        intents.extend(exit_intents)
        intents.extend(adjust_intents)
        if bil_sell > 0:
            intents.append({"action": "SWEEP", "symbol": CASH_VEHICLE,
                            "qty": -bil_sell,
                            "reason": "sell BIL to fund sleeve orders "
                                      "(single per-cycle cash ledger)"})
        intents.extend(entry_intents)
        if rebalance_intent is not None:
            intents.append(rebalance_intent)
        if core_buy is not None:
            intents.append(core_buy)
        if sweep_buy is not None:
            intents.append(sweep_buy)
        for msg in alerts:
            intents.append({"action": "ALERT", "level": "RED", "msg": msg})
        return intents

    # ---------- execution callbacks (run_cycle reports results) ----------

    def record_pending_entry(self, intent: dict, today: str) -> None:
        """Write-ahead journal: persisted BEFORE the MOO is placed so a crash
        between placement and on_entered is reconciled on the next cycle via
        the deterministic client_order_id — never a duplicate MOO."""
        self.state.pending_entries[str(intent["call_id"])] = {
            "intent": dict(intent), "date": today}
        self.save()

    def clear_pending_entry(self, call_id: int) -> None:
        if self.state.pending_entries.pop(str(call_id), None) is not None:
            self.save()

    def record_pending_book_order(self, kind: str, symbol: str, qty: int,
                                  today: str) -> str:
        """Write-ahead journal for book-level orders (CORE_BUY, the
        rebalance core-sell, BIL sweeps) — the same crash-window discipline
        as sleeve entries (counter-agent N15). Persisted BEFORE placement;
        returns the deterministic client_order_id. kind in
        {core-buy, core-rebal-sell, sweep}; qty signed (+buy/-sell)."""
        self.state.book_order_seq += 1
        cid = f"blend-{kind}-{today}-{self.state.book_order_seq}"
        self.state.pending_book_orders[cid] = {
            "kind": kind, "symbol": symbol, "qty": qty, "date": today}
        self.save()
        return cid

    def clear_pending_book_order(self, client_id: str) -> None:
        if self.state.pending_book_orders.pop(client_id, None) is not None:
            self.save()

    def on_entered(self, intent: dict, fill_price: float, order_ref: str,
                   today: str) -> None:
        from datetime import date, timedelta

        d = date.fromisoformat(today)
        pos = BlendPosition(
            call_id=intent["call_id"], symbol=intent["symbol"],
            qty=intent["qty"], entry_ref=intent["entry_ref"],
            fill_price=fill_price, entry_date=today,
            time_stop=(d + timedelta(days=intent.get("time_stop_days",
                                                     TIME_STOP_DAYS))).isoformat(),
            stop_level=intent["stop_level"])
        key = str(pos.call_id)
        self.state.positions[key] = pos
        self.state.entered_ids.append(pos.call_id)
        self.state.entered_ids = self.state.entered_ids[-2000:]
        self.state.entered_symbols[key] = pos.symbol
        keep = {str(i) for i in self.state.entered_ids}
        self.state.entered_symbols = {k: v for k, v
                                      in self.state.entered_symbols.items()
                                      if k in keep}
        self.state.pending_entries.pop(key, None)   # journal fulfilled
        self.state.sleeve_cash -= pos.qty * fill_price
        self._event("INFO", f"ENTER {pos.symbol} x{pos.qty} @ {fill_price:.2f} "
                            f"(call {pos.call_id}, stop {pos.stop_level:.2f})")
        self.save()

    def on_stop_placed(self, call_id: int, order_ref: str, level: float) -> None:
        pos = self.state.positions.get(str(call_id))
        if pos is not None:
            pos.stop_order_ref = order_ref
            pos.stop_level = level
            pos.stop_missing = False
            self.save()

    def mark_stop_missing(self, call_id: int) -> None:
        pos = self.state.positions.get(str(call_id))
        if pos is not None:
            pos.stop_missing = True
            pos.stop_order_ref = None
            self._event("RED", f"STOP_MISSING: {pos.symbol} x{pos.qty} "
                               f"(call {call_id}) has NO working stop")
            self.save()

    def record_orphan_stop(self, order_ref: str, info: dict) -> None:
        """A retired stop whose cancel failed: two stops may rest at the
        venue. Retried every reconcile pass; a fill on it alerts RED."""
        self.state.orphan_stop_refs[order_ref] = {**info, "ts": int(time.time())}
        self._event("WARN", f"retired stop {order_ref} could not be "
                            f"cancelled; retrying every cycle")
        self.save()

    def on_exited(self, call_id: int, fill_price: float, reason: str) -> None:
        """fill_price is REQUIRED (repo law: no silent zero). A missing fill
        price must route through on_exit_unreconciled instead."""
        if fill_price is None:
            raise ValueError("on_exited requires a fill price; use "
                             "on_exit_unreconciled for a missing one")
        pos = self.state.positions.pop(str(call_id), None)
        if pos is None:
            return
        pnl = (fill_price - pos.fill_price) * pos.qty
        self.state.sleeve_cash += pos.qty * fill_price
        self._event("INFO", f"EXIT {pos.symbol} x{pos.qty} @ {fill_price:.2f} "
                            f"({reason}) -> P&L ${pnl:+,.0f}")
        self.save()

    def on_exit_unreconciled(self, call_id: int, reason: str) -> None:
        """The position left the book at the venue but no fill price is
        known: NOTHING is booked (never 0.0) — the trade is parked in
        state.unreconciled for manual reconciliation and alerted RED."""
        pos = self.state.positions.pop(str(call_id), None)
        if pos is None:
            return
        self.state.unreconciled[str(call_id)] = {**asdict(pos),
                                                 "reason": reason,
                                                 "ts": int(time.time())}
        self._event("RED", f"UNRECONCILED exit {pos.symbol} x{pos.qty} "
                           f"(call {call_id}): {reason} — proceeds NOT "
                           f"booked, manual reconciliation required")
        self.save()

    def on_core_trade(self, qty_delta: int, price: float) -> None:
        self.state.spy_qty += qty_delta
        self.state.core_cash -= qty_delta * price
        self.save()

    def on_sweep(self, qty_delta: int, price: float) -> None:
        self.state.bil_qty += qty_delta
        self.state.sleeve_cash -= qty_delta * price
        self.save()

    def on_transfer(self, usd: float) -> None:
        """+usd moves core -> sleeve; -usd moves sleeve -> core."""
        self.state.sleeve_cash += usd
        self.state.core_cash -= usd
        self.save()

    # ---------- control ----------

    def halt(self, reason: str = "KILL") -> None:
        self.state.halted = reason
        self._event("RED", f"blend halted ({reason})")
        self.save()

    def resume(self) -> None:
        self.state.halted = None
        self._event("INFO", "blend resumed")
        self.save()

    def status_summary(self, prices: dict[str, float] | None = None) -> dict:
        st = self.state
        out = {
            "enabled": True,
            "halted": st.halted,
            "initialized": st.initialized,
            "positions": {k: asdict(v) for k, v in st.positions.items()},
            "open_count": len(st.positions),
            "stop_missing": [k for k, v in st.positions.items()
                             if v.stop_missing or not v.stop_order_ref],
            "pending_entries": sorted(st.pending_entries),
            "pending_book_orders": sorted(st.pending_book_orders),
            "unreconciled": st.unreconciled,
            "orphan_stops": sorted(st.orphan_stop_refs),
            "sleeve_cash": round(st.sleeve_cash, 2),
            "bil_qty": st.bil_qty,
            "spy_qty": st.spy_qty,
            "core_cash": round(st.core_cash, 2),
            "budget_cap": getattr(self.cfg, "blend_budget", 0.0) or None,
            "events": st.events[-40:],
        }
        if prices:
            out["sleeve_value"] = round(self.sleeve_value(prices), 2)
            out["core_value"] = round(self.core_value(prices), 2)
            book = self.book_value(prices)
            out["book_value"] = round(book, 2)
            out["sleeve_weight"] = round(self.sleeve_value(prices) / book, 4) if book else None
        return out


# ---------- tracker poll + cycle execution ------------------------------------

def fetch_intents(cfg) -> dict | None:
    """GET the tracker's intent set. A bare authenticated GET: no params, no
    body — the tracker never learns positions or account equity. None on any
    failure (a dead tracker blocks NEW actions; resting GTC stops and the
    time-stop belt still protect the book)."""
    base = (getattr(cfg, "tracker_url", "") or "").rstrip("/")
    if not base:
        return None
    kwargs: dict = {"timeout": 30}
    token = getattr(cfg, "tracker_api_token", "")
    if token:
        # Preferred: the dedicated read-only intents token — the executor
        # never holds the dashboard password.
        kwargs["headers"] = {"X-API-Token": token}
    elif getattr(cfg, "tracker_user", ""):
        kwargs["auth"] = (cfg.tracker_user, cfg.tracker_password)
    try:
        r = httpx.get(f"{base}/blend3070/intents", **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("blend intents fetch failed: %s", exc)
        return None


def payload_is_stale(payload: dict, today: str) -> bool:
    """True when the tracker's as_of is too old to act on (its bar feed
    stalled): reconciliation still runs, but no NEW decision is taken
    against a possibly-stale gate or days-old fires."""
    as_of = payload.get("as_of")
    if not as_of:
        return False
    try:
        return (date.fromisoformat(today)
                - date.fromisoformat(str(as_of))).days > STALE_PAYLOAD_DAYS
    except ValueError:
        # A malformed as_of is a data bug on the tracker side: treat the
        # payload as STALE (no new decisions), never as fresh
        # (counter-agent minor).
        logger.warning("blend: malformed payload as_of %r — treated as stale",
                       as_of)
        return True


def reference_prices(adapter, mgr: Blend3070Manager, payload: dict | None) -> dict:
    """Reference prices for every symbol the cycle can touch, via the
    adapter (DryAdapter returns synthetic quotes offline)."""
    symbols = {CORE, CASH_VEHICLE}
    symbols.update(p.symbol for p in mgr.state.positions.values())
    if payload:
        symbols.update(e["symbol"] for e in payload.get("entries", []) if e.get("symbol"))
    prices: dict[str, float] = {}
    for s in symbols:
        try:
            prices[s] = adapter.spot(s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("spot %s failed: %s", s, exc)
    return prices


def _ensure_stop(mgr: Blend3070Manager, adapter, pos: BlendPosition,
                 alert) -> bool:
    """Place pos's protective GTC stop with in-cycle retry/backoff. On final
    failure the position is marked STOP_MISSING (blocks all new entries,
    retried every cycle) and Telegram is alerted loudly. The deterministic
    client_order_id makes the retry idempotent: a stop that actually reached
    the venue on a crashed attempt is adopted, not duplicated."""
    if pos.stop_level <= 0:
        mgr.mark_stop_missing(pos.call_id)
        alert(f"🚨🚨 blend STOP_MISSING: {pos.symbol} x{pos.qty} "
              f"(call {pos.call_id}) has a non-positive stop level "
              f"({pos.stop_level}) — no stop placeable; new entries BLOCKED")
        return False
    last_exc: Exception | None = None
    for attempt in range(STOP_RETRY_ATTEMPTS):
        try:
            rs = adapter.place_stock_order(
                pos.symbol, -pos.qty, "STP", stop_price=pos.stop_level,
                tif="GTC",
                client_order_id=stop_client_id(pos.call_id, pos.stop_level))
            mgr.on_stop_placed(pos.call_id, rs["order_ref"], pos.stop_level)
            return True
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("stop placement %s attempt %d failed: %s",
                           pos.symbol, attempt + 1, exc)
            if attempt < STOP_RETRY_ATTEMPTS - 1:
                time.sleep(STOP_RETRY_SLEEP_S * (attempt + 1))
    mgr.mark_stop_missing(pos.call_id)
    alert(f"🚨🚨 blend STOP_MISSING: {pos.symbol} x{pos.qty} "
          f"(call {pos.call_id}) has NO working stop after "
          f"{STOP_RETRY_ATTEMPTS} attempts ({last_exc}) — new entries "
          f"BLOCKED, retrying every cycle until placed")
    return False


def _ingest_one_fill(mgr: Blend3070Manager, adapter, f: dict, alert) -> None:
    """Book a single polled fill event against the book (venue truth)."""
    st = mgr.state
    ref = f.get("order_ref")
    pos = next((p for p in st.positions.values()
                if p.stop_order_ref == ref), None)
    if pos is not None:
        fill = f.get("fill_price")
        if fill is None:
            mgr.on_exit_unreconciled(pos.call_id,
                                     "stop filled WITHOUT a fill price")
            alert(f"🚨 blend stop fill for {pos.symbol} "
                  f"(call {pos.call_id}) carried NO fill price — trade "
                  f"UNRECONCILED, proceeds NOT booked, manual "
                  f"reconciliation needed")
        else:
            mgr.on_exited(pos.call_id, fill, "stop_filled")
            alert(f"🧬 blend STOP FILLED {pos.symbol} x{pos.qty} @ "
                  f"{fill:.2f} (call {pos.call_id}) — position closed "
                  f"at the venue")
    elif ref in st.orphan_stop_refs:
        info = st.orphan_stop_refs.pop(ref)
        st.unreconciled[f"orphan-{ref}"] = {
            **info, "fill_price": f.get("fill_price"),
            "reason": "retired stop filled after a failed cancel "
                      "(possible short at the venue)"}
        mgr.save()
        alert(f"🚨🚨 blend: RETIRED stop {ref} FILLED "
              f"({info.get('symbol')} {info.get('qty')}) — possible "
              f"short at the venue, manual action needed")
    elif ref in _journaled_order_refs(mgr, adapter):
        # A venue that also streams MOO/MKT fills through the fill poll
        # (real-venue contract note): a fill for a JOURNALED order is
        # adopted by the journal reconcile passes, not here — no RED noise.
        logger.info("blend: fill for journaled order %s handled by the "
                    "journal reconcile", ref)
    else:
        alert(f"🚨 blend: fill for UNKNOWN order {ref} ({f}) — manual "
              f"reconciliation needed")


def _journaled_order_refs(mgr: Blend3070Manager, adapter) -> set:
    """Venue order_refs belonging to journaled (pending) orders — their
    fills are adopted by the journal passes, never the unknown-order path."""
    refs = set()
    ids = [entry_client_id(rec["intent"]["call_id"])
           for rec in mgr.state.pending_entries.values()]
    ids.extend(mgr.state.pending_book_orders)
    for cid in ids:
        try:
            o = adapter.find_stock_order(cid)
        except Exception:  # noqa: BLE001
            continue
        if o is not None:
            refs.add(o.get("order_ref"))
    return refs


def _ingest_fills(mgr: Blend3070Manager, adapter, alert) -> None:
    """Drain and book queued fill events. A mid-loop failure RE-QUEUES the
    unprocessed fills on the adapter before re-raising — a raising save()
    or alert callback can never silently lose a venue fill (counter-agent
    N3). A fill whose booking completed before the failure may be seen
    twice; the second pass lands in the detected unknown-order branch
    (noise, never a double booking)."""
    fills = adapter.poll_stock_fills()
    for i, f in enumerate(fills):
        try:
            _ingest_one_fill(mgr, adapter, f, alert)
        except Exception:
            requeue = getattr(adapter, "requeue_stock_fills", None)
            if requeue is not None:
                requeue(fills[i:])
            else:
                logger.error("blend: fill ingestion failed and the adapter "
                             "cannot re-queue — fills at risk: %s", fills[i:])
            raise


def _apply_book_order(mgr: Blend3070Manager, rec: dict, fill: float) -> None:
    """Book a filled book-level order into the ledgers by journal kind."""
    kind, qty = rec["kind"], rec["qty"]
    if kind == "core-buy":
        mgr.on_core_trade(qty, fill)
    elif kind == "core-rebal-sell":
        mgr.on_core_trade(qty, fill)          # qty is negative (a sell)
        mgr.on_transfer(-qty * fill)          # proceeds move core -> sleeve
    elif kind == "sweep":
        mgr.on_sweep(qty, fill)
    else:  # unknown journal kind: freeze for manual reconciliation
        mgr.state.unreconciled[f"book-{kind}-{int(time.time())}"] = {
            **rec, "fill_price": fill,
            "reason": "unknown book-order journal kind"}
        mgr.save()


def reconcile(mgr: Blend3070Manager, adapter, today: str, alert) -> None:
    """Venue-truth-first pass, run BEFORE any decision in EVERY cycle —
    including tracker-outage cycles (payload=None) and /kill:
      1. ingest resting-stop fills — a stop that filled marks its position
         CLOSED, so a later tracker exit/echo for it is a no-op;
      2. adopt or clear write-ahead entry intents (crash between placement
         and persist), checked against venue order history by
         client_order_id — never a duplicate MOO;
      2b. adopt or clear write-ahead BOOK orders (CORE_BUY / rebalance
         core-sell / BIL sweep) the same way — never a duplicate SPY/BIL
         order (counter-agent N15);
      3. retry cancelling retired stops whose cancel failed;
      4. re-place any missing protective stop (STOP_MISSING).
    Raises if the adapter cannot answer (paper IBAdapter until implemented):
    the cycle FAILS CLOSED — no decision against unreconciled state."""
    st = mgr.state

    # 1) stop fills
    _ingest_fills(mgr, adapter, alert)

    # 2) write-ahead entry journal
    for key, rec in list(st.pending_entries.items()):
        it = rec["intent"]
        o = adapter.find_stock_order(entry_client_id(it["call_id"]))
        if o is None:
            mgr.clear_pending_entry(it["call_id"])
            mgr._event("INFO", f"pending entry {it['symbol']} "
                               f"(call {it['call_id']}) never reached the "
                               f"venue; journal cleared")
        elif o.get("status") == "filled":
            fill = o.get("fill_price")
            if fill is None:
                fill = it["entry_ref"]
                alert(f"⚠️ blend: reconciled entry {it['symbol']} "
                      f"(call {it['call_id']}) has no venue fill price — "
                      f"booked at entry_ref {fill:.2f} (basis provisional)")
            mgr.on_entered(it, fill, o["order_ref"], rec.get("date", today))
            mgr.mark_stop_missing(it["call_id"])   # stop placed in pass 4
            alert(f"🧬 blend reconciled orphan ENTER {it['symbol']} "
                  f"x{it['qty']} (call {it['call_id']}) from venue order "
                  f"history (crash-window recovery)")
        # status "working": an async MOO awaiting its fill — keep the journal.

    # 2b) write-ahead BOOK-order journal (CORE_BUY / rebalance core-sell /
    #     BIL sweep): the crash window between placement and the on_* booking
    #     is closed the same way as entries — venue order history is checked
    #     by the deterministic client id; a filled orphan is ADOPTED into the
    #     ledgers, one that never reached the venue is cleared and re-planned
    #     naturally by step() (counter-agent N15).
    for cid, rec in list(st.pending_book_orders.items()):
        o = adapter.find_stock_order(cid)
        if o is None:
            mgr.clear_pending_book_order(cid)
            mgr._event("INFO", f"pending {rec['kind']} {rec['symbol']} "
                               f"x{rec['qty']} never reached the venue; "
                               f"journal cleared")
        elif o.get("status") == "filled":
            fill = o.get("fill_price")
            if fill is None:
                # A real venue holding/lacking SPY or BIL MUST be tracked —
                # book at the current spot as a PROVISIONAL basis and say so
                # loudly (same asymmetry as entry adoption: parking would
                # desync the holdings themselves, worse than a fuzzy basis).
                fill = adapter.spot(rec["symbol"])
                alert(f"🚨 blend: reconciled {rec['kind']} {rec['symbol']} "
                      f"x{rec['qty']} has no venue fill price — booked at "
                      f"spot {fill:.2f} (basis PROVISIONAL, verify manually)")
            st.pending_book_orders.pop(cid, None)
            _apply_book_order(mgr, rec, fill)
            alert(f"🧬 blend reconciled orphan {rec['kind']} {rec['symbol']} "
                  f"x{rec['qty']} @ {fill:.2f} from venue order history "
                  f"(crash-window recovery)")
        # status "working": async order awaiting its fill — keep the journal.

    # 3) retired stops whose cancel failed
    for ref in list(st.orphan_stop_refs):
        try:
            adapter.cancel_stock_order(ref)
            st.orphan_stop_refs.pop(ref, None)
            mgr.save()
            mgr._event("INFO", f"retired stop {ref} cancelled on retry")
        except Exception as exc:  # noqa: BLE001
            alert(f"⚠️ blend: retired stop {ref} STILL uncancelled ({exc}) — "
                  f"two stops may rest at the venue")

    # 4) missing protective stops
    for pos in list(st.positions.values()):
        if pos.stop_missing or not pos.stop_order_ref:
            if _ensure_stop(mgr, adapter, pos, alert):
                alert(f"🧬 blend: protective stop restored for {pos.symbol} "
                      f"(call {pos.call_id}) at {pos.stop_level:.2f}")


def _execute_enter(mgr: Blend3070Manager, adapter, it: dict, today: str,
                   alert) -> None:
    """Write-ahead journal -> MOO with deterministic client_order_id ->
    persist fill -> protective stop (retry; STOP_MISSING on failure)."""
    mgr.record_pending_entry(it, today)             # journal BEFORE placement
    r = adapter.place_stock_order(it["symbol"], it["qty"], "MOO", tif="OPG",
                                  ref_price=it["entry_ref"],
                                  client_order_id=entry_client_id(it["call_id"]))
    if r.get("status") != "filled":
        # Async venue (real OPG fills at the next open): the journal stays;
        # the reconcile pass adopts the fill once the venue reports it.
        alert(f"🧬 blend ENTER {it['symbol']} x{it['qty']} MOO accepted, "
              f"awaiting fill — reconciled next cycle")
        return
    fill = r.get("fill_price")
    if fill is None:
        # An ENTRY ack without a price still leaves a real position needing
        # stop protection: book at the sizing reference and say so loudly
        # (exits, where a silent default would vaporize proceeds, go to
        # UNRECONCILED instead — see _execute_exit).
        fill = it["entry_ref"]
        alert(f"⚠️ blend ENTER {it['symbol']}: venue ack without fill price — "
              f"booked at entry_ref {fill:.2f}, basis provisional")
    mgr.on_entered(it, fill, r["order_ref"], today)
    pos = mgr.state.positions[str(it["call_id"])]
    _ensure_stop(mgr, adapter, pos, alert)
    alert(f"🧬 blend ENTER {it['symbol']} x{it['qty']} MOO "
          f"(stop {it['stop_level']:.2f}): {it['reason']}")


def _execute_adjust_stop(mgr: Blend3070Manager, adapter, it: dict,
                         alert) -> None:
    """Cancel/replace with NO naked window: place the NEW stop first, cancel
    the old second. A rejected replacement keeps the old stop working; a
    failed cancel of the old leaves it tracked as an orphan (retried every
    cycle, its fill alerted RED)."""
    try:
        rs = adapter.place_stock_order(
            it["symbol"], -it["qty"], "STP", stop_price=it["stop_level"],
            tif="GTC",
            client_order_id=stop_client_id(it["call_id"], it["stop_level"]))
    except Exception as exc:  # noqa: BLE001
        alert(f"⚠️ blend stop replace REJECTED for {it['symbol']} at "
              f"{it['stop_level']:.2f} ({exc}) — old stop kept working, "
              f"will retry next cycle")
        return
    mgr.on_stop_placed(it["call_id"], rs["order_ref"], it["stop_level"])
    old_ref = it.get("old_ref")
    if old_ref:
        try:
            adapter.cancel_stock_order(old_ref)   # False = already gone: fine
        except Exception as exc:  # noqa: BLE001
            mgr.record_orphan_stop(old_ref, {"symbol": it["symbol"],
                                             "qty": -it["qty"],
                                             "call_id": it["call_id"]})
            alert(f"⚠️ blend: cancel of retired stop {old_ref} failed "
                  f"({exc}) — TWO stops may rest for {it['symbol']}; "
                  f"retrying cancel every cycle")
    alert(f"🧬 blend STOP {it['symbol']}: {it['reason']}")


def _execute_exit(mgr: Blend3070Manager, adapter, it: dict,
                  prices: dict[str, float], alert) -> bool:
    """Cancel the resting stop (non-fatal), then MKT-sell. If the cancel
    RAISES, the stop's state is unknown — the sell is deferred to the next
    cycle rather than risking a double-sell on top of a possibly-working
    stop (a fill meanwhile is ingested by the reconcile pass). A FALSE
    cancel ("already gone") is VERIFIED before selling: queued fills are
    ingested and only a still-held position is sold — idempotent with a
    stop fill that won the race (counter-agent N2/N14). A sell fill without
    a price goes to UNRECONCILED — never booked at 0.0.

    Returns True only when the exit's proceeds actually BOOKED this cycle
    (directly or via the racing stop fill) — a deferred or UNRECONCILED
    exit returns False so run_cycle drops the entries its proceeds were
    meant to fund (counter-agent N5)."""
    key = str(it["call_id"])
    ref = it.get("stop_order_ref")
    if ref:
        try:
            cancelled = adapter.cancel_stock_order(ref)
        except Exception as exc:  # noqa: BLE001
            alert(f"⚠️ blend EXIT {it['symbol']} deferred: stop cancel "
                  f"failed ({exc}); position kept — retried next cycle "
                  f"(a stop fill meanwhile reconciles first)")
            return False
        if not cancelled:
            # "Already gone" is ambiguous: the stop may have JUST filled.
            # Ingest any queued fills and sell only what is still held.
            _ingest_fills(mgr, adapter, alert)
            if key not in mgr.state.positions:
                alert(f"🧬 blend EXIT {it['symbol']} no-op: its stop had "
                      f"already filled — booked from the venue fill")
                return key not in mgr.state.unreconciled
    r = adapter.place_stock_order(it["symbol"], -it["qty"], "MKT",
                                  ref_price=prices.get(it["symbol"]),
                                  client_order_id=exit_client_id(it["call_id"]))
    fill = r.get("fill_price")
    if fill is None:
        mgr.on_exit_unreconciled(it["call_id"],
                                 f"{it['reason']}: venue ack without a fill "
                                 f"price")
        alert(f"🚨 blend EXIT {it['symbol']} x{it['qty']} UNRECONCILED: no "
              f"fill price from the venue — proceeds NOT booked, manual "
              f"reconciliation needed")
        return False
    mgr.on_exited(it["call_id"], fill, it["reason"])
    alert(f"🧬 blend EXIT {it['symbol']} x{it['qty']} ({it['reason']})")
    return True


def run_cycle(mgr: Blend3070Manager, adapter, payload: dict | None,
              today: str, alert=None) -> list[dict]:
    """One blend cycle: RECONCILE (venue truth first) -> step -> execute
    intents on the adapter -> callbacks. Every action alerts; any single
    intent failing never blocks the rest."""
    from .alerts import send as _send
    alert = alert or _send

    # PHASE 0 — reconciliation-first (order-safety law #1). Raises if the
    # adapter cannot reconcile: the cycle fails closed.
    reconcile(mgr, adapter, today, alert)

    if payload is not None and payload_is_stale(payload, today):
        alert(f"⚠️ blend: tracker payload is stale (as_of "
              f"{payload.get('as_of')}, today {today}) — no new decisions "
              f"this cycle (book still reconciled and stop-protected)")
        payload = None

    prices = reference_prices(adapter, mgr, payload)
    intents = mgr.step(today, payload, prices)
    exit_unsettled = False     # a funding exit deferred/UNRECONCILED (N5)
    for it in intents:
        try:
            act = it["action"]
            if act == "ALERT":
                alert(f"🚨 blend: {it['msg']}")
            elif act == "ENTER":
                if mgr.has_naked_position():
                    # An earlier intent this cycle left a position naked:
                    # stop adding risk immediately, not next cycle.
                    alert(f"🚨 blend ENTER {it['symbol']} skipped: a "
                          f"position is STOP_MISSING — protect the book "
                          f"before adding risk")
                    continue
                if exit_unsettled:
                    # The cycle plan counted an exit's proceeds that did NOT
                    # book: those funds are phantom — never spend them.
                    alert(f"⚠️ blend ENTER {it['symbol']} skipped: a funding "
                          f"exit did not book this cycle — entry re-planned "
                          f"once the exit settles")
                    continue
                if (it["qty"] * it["entry_ref"]
                        > mgr.state.sleeve_cash + CASH_EPS):
                    # Belt: entries spend only SETTLED cash (exits + the BIL
                    # raise have already booked by this point in intent
                    # order) — the ledger never goes negative.
                    alert(f"⚠️ blend ENTER {it['symbol']} skipped: settled "
                          f"sleeve cash ${mgr.state.sleeve_cash:,.2f} cannot "
                          f"fund ${it['qty'] * it['entry_ref']:,.2f}")
                    continue
                _execute_enter(mgr, adapter, it, today, alert)
            elif act == "ADJUST_STOP":
                _execute_adjust_stop(mgr, adapter, it, alert)
            elif act == "EXIT":
                if not _execute_exit(mgr, adapter, it, prices, alert):
                    exit_unsettled = True
            elif act == "REBALANCE":
                if _execute_rebalance(mgr, adapter, it, prices, today):
                    alert(f"🧬 blend REBALANCE {it['direction']} "
                          f"${it['usd']:,.0f}: {it['reason']}")
            elif act == "CORE_BUY":
                px = prices.get(CORE, 0.0)
                qty = it["qty"]
                if px > 0:   # never overdraw core cash on a short transfer
                    qty = min(qty, int(max(mgr.state.core_cash, 0.0) // px))
                if qty > 0:
                    # Write-ahead journal + deterministic client id: a crash
                    # between placement and booking is adopted by reconcile
                    # pass 2b, never re-bought (counter-agent N15).
                    cid = mgr.record_pending_book_order("core-buy", CORE,
                                                        qty, today)
                    r = adapter.place_stock_order(CORE, qty, "MKT",
                                                  ref_price=px or None,
                                                  client_order_id=cid)
                    if r.get("status") != "filled":
                        alert(f"🧬 blend CORE buy {CORE} x{qty} accepted, "
                              f"awaiting fill — reconciled next cycle")
                        continue                # journal stays until adopted
                    fill = r.get("fill_price")
                    if fill is None:
                        fill = px
                    if not fill:
                        # Journal kept: reconcile adopts at spot, loudly.
                        raise RuntimeError("core buy fill price unknown")
                    mgr.state.pending_book_orders.pop(cid, None)
                    mgr.on_core_trade(qty, fill)   # saves journal-pop + booking
                    alert(f"🧬 blend CORE buy {CORE} x{qty}")
            elif act == "SWEEP":
                qty = it["qty"]
                if qty < 0:   # hard floor: never sell BIL beyond holdings
                    qty = -min(-qty, mgr.state.bil_qty)
                else:
                    # A buy planned on proceeds that never booked (e.g. an
                    # UNRECONCILED exit earlier this cycle) is clamped to
                    # the cash actually held — the ledger never goes negative.
                    px = prices.get(CASH_VEHICLE) or 0.0
                    if px > 0:
                        qty = min(qty, int(max(mgr.state.sleeve_cash, 0.0) // px))
                if qty != 0:
                    cid = mgr.record_pending_book_order("sweep", CASH_VEHICLE,
                                                        qty, today)
                    r = adapter.place_stock_order(CASH_VEHICLE, qty, "MKT",
                                                  ref_price=prices.get(CASH_VEHICLE),
                                                  client_order_id=cid)
                    if r.get("status") != "filled":
                        alert(f"🧬 blend SWEEP {CASH_VEHICLE} "
                              f"{'+' if qty > 0 else ''}{qty} accepted, "
                              f"awaiting fill — reconciled next cycle")
                        continue                # journal stays until adopted
                    fill = r.get("fill_price")
                    if fill is None:
                        fill = prices.get(CASH_VEHICLE)
                    if not fill:
                        raise RuntimeError("sweep fill price unknown")
                    mgr.state.pending_book_orders.pop(cid, None)
                    mgr.on_sweep(qty, fill)        # saves journal-pop + booking
                    alert(f"🧬 blend SWEEP {CASH_VEHICLE} "
                          f"{'+' if qty > 0 else ''}{qty}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("blend intent %s failed: %s", it, exc)
            alert(f"🚨 blend intent failed ({it.get('action')} "
                  f"{it.get('symbol')}): {exc}\n→ no action needed from you — "
                  f"forward this to Claude")
    mgr.save()
    return intents


def _execute_rebalance(mgr: Blend3070Manager, adapter, it: dict,
                       prices: dict[str, float], today: str) -> bool:
    """Returns True only when something actually moved (the REBALANCE alert
    fires only then). sleeve_to_core NEVER sells BIL here — funding was
    raised by this cycle's single BIL SWEEP (executed earlier in intent
    order), and the transfer is clamped to the cash the sleeve holds."""
    usd = it["usd"]
    spy_px = prices.get(CORE, 0.0)
    if it["direction"] == "core_to_sleeve":
        # Sell SPY for ~usd, move the proceeds to the sleeve (swept to BIL
        # by this cycle's SWEEP, which executes after the transfer).
        if spy_px <= 0:
            return False
        qty = min(mgr.state.spy_qty, int(round(usd / spy_px)))
        if qty <= 0:
            return False
        # Write-ahead journal + deterministic client id (counter-agent N15):
        # a crash after placement is adopted by reconcile pass 2b — the SPY
        # sell and its core->sleeve transfer are never repeated.
        cid = mgr.record_pending_book_order("core-rebal-sell", CORE, -qty,
                                            today)
        r = adapter.place_stock_order(CORE, -qty, "MKT", ref_price=spy_px,
                                      client_order_id=cid)
        if r.get("status") != "filled":
            return False                    # journal stays until adopted
        fill = r.get("fill_price")
        if fill is None:
            fill = spy_px
        mgr.state.pending_book_orders.pop(cid, None)
        mgr.on_core_trade(-qty, fill)       # saves journal-pop + booking
        mgr.on_transfer(qty * fill)
        return True
    moved = min(usd, max(mgr.state.sleeve_cash, 0.0))
    if moved <= 0:
        return False
    mgr.on_transfer(-moved)
    return True
