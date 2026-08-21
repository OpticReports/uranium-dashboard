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
TRADE_LOG_MAX = 200         # persisted closed/booked trade rows kept (feed)
EQUITY_CURVE_MAX = 1500     # daily book-value snapshots kept (~6 years)
UTIL_ALERT_ON = 0.85        # budget-utilization alert threshold (one-shot)
UTIL_ALERT_OFF = 0.75       # re-arm threshold once utilization drops back
STALE_PAYLOAD_DAYS = 5      # as_of older than this vs today -> no decisions
                            # (5, not the review's 2: a Monday poll after a
                            # long holiday weekend legitimately sees a 4-day-
                            # old last trading day; reconciliation still runs)
HISTORY_HORIZON_S = 86_400.0  # venue-history horizon (adapter review m2): a
                              # gap since the LAST successful reconcile longer
                              # than this means order history may not cover
                              # fills that happened inside the blackout — a
                              # cancel-False/verify-empty flatten is then
                              # UNVERIFIABLE (park + alert, never a MKT sell)


def _utc_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


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
    risk_per_share: float = 0.0  # entry_ref - day-one trail, frozen at entry
                                 # (R-multiple denominator; 0.0 on legacy
                                 # state rows -> R reported as null)
    history_gap: bool = False   # R1 blackout guard: a reconcile gap exceeded
                                # the venue-history horizon, so a stop fill
                                # inside the blackout may be invisible
                                # FOREVER — UNVERIFIABLE. Cleared ONLY by
                                # positive venue evidence (reconcile pass
                                # 1b), never by timestamp; exits//kill park
                                # while set


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
    flatten_request: dict | None = None  # /kill journal (R2): {ts, date} —
                                         # persisted like pending_entries so
                                         # a restart resumes the flatten; the
                                         # LOOP thread executes it (it owns
                                         # the ib_async event loop)
    events: list = field(default_factory=list)
    trades: list = field(default_factory=list)   # booked fills, oldest first
                                                 # (bounded TRADE_LOG_MAX;
                                                 # feeds the Execution tab)
    equity_curve: list = field(default_factory=list)  # [[date, book_value]]
                                                      # one row per cycle day
    last_gate: bool | None = None    # last tracker gate seen (feed display)
    util_alert_armed: bool = True    # one-shot 85% budget alert armed?
    last_reconcile_ts: float = 0.0   # wall clock of the last SUCCESSFUL
                                     # reconcile pass (venue-history horizon
                                     # guard, adapter review m2)


class Blend3070Manager:
    def __init__(self, cfg, state_path: str):
        self.cfg = cfg
        self.state_path = state_path
        self.state = self._load()
        # M2 (thread-safety): API threads (/status, /blend/feed) serve THIS
        # loop-thread-refreshed quote cache — they must never touch the
        # ib_async event loop themselves. run_cycle republishes it (whole-
        # dict swap: atomic under the GIL) every cycle; staleness is shown,
        # never hidden.
        self.mark_cache: dict = {"prices": {}, "ts": None}
        # m2 (venue-history horizon): seconds between this cycle's reconcile
        # and the previous SUCCESSFUL one — set by reconcile() each cycle.
        self._reconcile_gap_s: float = 0.0

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
                flatten_request=raw.get("flatten_request"),
                trades=raw.get("trades", [])[-TRADE_LOG_MAX:],
                equity_curve=raw.get("equity_curve", [])[-EQUITY_CURVE_MAX:],
                last_gate=raw.get("last_gate"),
                util_alert_armed=raw.get("util_alert_armed", True),
                last_reconcile_ts=raw.get("last_reconcile_ts", 0.0),
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
                   "flatten_request": self.state.flatten_request,
                   "trades": self.state.trades[-TRADE_LOG_MAX:],
                   "equity_curve": self.state.equity_curve[-EQUITY_CURVE_MAX:],
                   "last_gate": self.state.last_gate,
                   "util_alert_armed": self.state.util_alert_armed,
                   "last_reconcile_ts": self.state.last_reconcile_ts,
                   "events": self.state.events[-300:]},
                  open(self.state_path, "w"), indent=1)

    def _event(self, level: str, msg: str) -> bool:
        """Log a deduped event. Returns True only when the event was NEWLY
        recorded (callers use this for alert-once semantics, e.g. the M4
        missing-quote alert fires once per outage, not every cycle)."""
        last = self.state.events[-1] if self.state.events else None
        if last and last.get("msg") == msg:
            return False
        self.state.events.append({"ts": int(time.time()), "level": level,
                                  "msg": msg})
        logger.info("[blend] %s", msg)
        return True

    def _record_trade(self, symbol: str, side: str, qty: int,
                      fill_price: float, when: str, kind: str,
                      r_multiple: float | None = None,
                      pnl: float | None = None) -> None:
        """Append one booked fill to the persisted trade log (feed source).
        Caller saves — every current call site already saves right after."""
        self.state.trades.append({
            "symbol": symbol, "side": side, "qty": abs(qty),
            "fill_price": round(fill_price, 4), "date": when, "kind": kind,
            "r_multiple": round(r_multiple, 2) if r_multiple is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None})
        del self.state.trades[:-TRADE_LOG_MAX]

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
        """Any held position without a working protective stop — or one
        that is blackout-UNVERIFIABLE (R1: its stop state is unknown) —
        (safety-first: blocks all new entries until resolved)."""
        return any(p.stop_missing or not p.stop_order_ref or p.history_gap
                   for p in self.state.positions.values())

    def budget_utilization(self, prices: dict[str, float]) -> float | None:
        """Deployed gross notional as a fraction of BLEND_BUDGET; None when
        no budget cap is configured (0/unset) or no prices are available."""
        budget = getattr(self.cfg, "blend_budget", 0.0) or 0.0
        if budget <= 0 or not prices:
            return None
        return self.gross_exposure(prices) / budget

    def check_budget_alarm(self, prices: dict[str, float], alert) -> None:
        """One-shot-per-crossing Telegram alert when gross notional crosses
        UTIL_ALERT_ON (85%) of BLEND_BUDGET; re-arms once utilization drops
        below UTIL_ALERT_OFF (75%). Armed flag is persisted so a restart
        never re-fires an already-sent alert."""
        util = self.budget_utilization(prices)
        if util is None:
            return
        if self.state.util_alert_armed and util >= UTIL_ALERT_ON:
            self.state.util_alert_armed = False
            self._event("WARN", f"budget utilization {util:.0%} of "
                                f"BLEND_BUDGET (alert sent)")
            self.save()
            alert(f"⚠️ blend budget utilization {util:.0%} — review and "
                  f"raise BLEND_BUDGET")
        elif not self.state.util_alert_armed and util < UTIL_ALERT_OFF:
            self.state.util_alert_armed = True
            self.save()

    def record_equity_snapshot(self, today: str, prices: dict[str, float]) -> None:
        """Daily book-value point for the Execution tab's equity curve: one
        row per cycle day (later cycles the same day update it in place).
        M4: SKIPPED when the CORE or BIL quote is missing — a zero-valued
        ledger side would record a distorted book value (repo law: no
        silent zero)."""
        if not self.state.initialized or not prices:
            return
        if prices.get(CORE, 0.0) <= 0 or prices.get(CASH_VEHICLE, 0.0) <= 0:
            return
        value = round(self.book_value(prices), 2)
        curve = self.state.equity_curve
        if curve and curve[-1][0] == today:
            if curve[-1][1] == value:
                return
            curve[-1][1] = value
        else:
            curve.append([today, value])
            del curve[:-EQUITY_CURVE_MAX]
        self.save()

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
        # M1 (idempotent book orders): while ANY write-ahead book-order
        # journal (CORE_BUY / rebalance core-sell / BIL sweep) is pending,
        # NO new book-level order is planned this cycle — a 'working' MKT
        # (guaranteed for any MKT placed outside RTH) simply waits for
        # reconcile pass 2b to adopt or clear it, instead of being
        # re-planned and re-placed every poll. Cash a pending sweep BUY
        # will debit at adoption is reserved (entries can never spend it),
        # and BIL is not treated as spendable while a sweep is in flight
        # (the funding sell is a book order too).
        pending_book = bool(st.pending_book_orders)
        if pending_book:
            kinds = sorted({r["kind"] for r in st.pending_book_orders.values()})
            self._event("INFO", f"book order(s) pending adoption "
                                f"({', '.join(kinds)}): no new book-level "
                                f"orders this cycle")
        projected_cash = st.sleeve_cash - self.reserved_sleeve_cash()
        funds = projected_cash + (0.0 if pending_book
                                  else st.bil_qty * bil_px)  # spendable

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
        st.last_gate = gate_on          # feed display; persisted on next save
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
        #    M4: NEVER computed from absent prices — a missing SPY (or BIL)
        #    quote zeroes a whole ledger side, manufactures a spurious
        #    sleeve-weight drift, and would book a phantom cash transfer
        #    that later unwinds with REAL trades (repo law: no silent
        #    zero). Skip + alert ONCE per outage.
        #    M1: skipped while any book order is pending adoption.
        rebalance_intent = None
        spy_quote = prices.get(CORE, 0.0)
        if spy_quote <= 0 or bil_px <= 0:
            msg = (f"rebalance/valuation SKIPPED: missing quote "
                   f"(SPY={spy_quote or None}, BIL={bil_px or None}) — no "
                   f"weight decision is taken on absent prices")
            if self._event("WARN", msg):
                alerts.append(msg)
        elif pending_book:
            pass                        # wait for the in-flight book order
        elif (book := self.book_value(prices)) > 0:
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
        if (not pending_book and projected_cash < -CASH_EPS
                and bil_px > 0 and st.bil_qty > 0):
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
        if (not pending_book and spy_px > 0
                and core_cash_proj > max(MIN_ORDER_USD, spy_px)):
            core_buy = {"action": "CORE_BUY", "symbol": CORE,
                        "qty": int(core_cash_proj // spy_px),
                        "reason": "invest idle core cash"}

        # 8) BIL sweep of idle sleeve cash (buy) from the resolved ledger.
        #    Under a budget cap, the sweep is clamped to the remaining gross
        #    headroom — economically cash, but gross must never drift above
        #    BLEND_BUDGET via the cash vehicle (counter-agent minor).
        sweep_buy = None
        if (not pending_book and bil_px > 0
                and projected_cash > max(MIN_ORDER_USD, bil_px)):
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
                                  today: str,
                                  ref_price: float | None = None) -> str:
        """Write-ahead journal for book-level orders (CORE_BUY, the
        rebalance core-sell, BIL sweeps) — the same crash-window discipline
        as sleeve entries (counter-agent N15). Persisted BEFORE placement;
        returns the deterministic client_order_id. kind in
        {core-buy, core-rebal-sell, sweep}; qty signed (+buy/-sell).

        M1: the client id is deterministic PER INTENT, not per attempt —
        while a journal for this kind is outstanding its cid is returned
        UNCHANGED, so a retry can never mint a fresh venue identity for
        the same intent; the seq only advances for a genuinely new intent
        (the prior journal adopted or cleared by reconcile). ref_price is
        stored so a pending sweep BUY's future cash debit can be reserved
        from the spendable ledger."""
        for cid, rec in self.state.pending_book_orders.items():
            if rec["kind"] == kind:
                return cid
        self.state.book_order_seq += 1
        cid = f"blend-{kind}-{today}-{self.state.book_order_seq}"
        self.state.pending_book_orders[cid] = {
            "kind": kind, "symbol": symbol, "qty": qty, "date": today,
            "ref_price": ref_price}
        self.save()
        return cid

    def reserved_sleeve_cash(self) -> float:
        """Sleeve cash a pending (working, not yet adopted) BIL sweep BUY
        will debit at adoption — never spendable by entries (M1)."""
        return sum(rec["qty"] * (rec.get("ref_price") or 0.0)
                   for rec in self.state.pending_book_orders.values()
                   if rec["kind"] == "sweep" and rec["qty"] > 0)

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
            stop_level=intent["stop_level"],
            risk_per_share=max(intent["entry_ref"] - intent["stop_level"], 0.0))
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
        self._record_trade(pos.symbol, "BUY", pos.qty, fill_price, today,
                           "entry")
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
        r_mult = ((fill_price - pos.fill_price) / pos.risk_per_share
                  if pos.risk_per_share > 0 else None)
        self._record_trade(pos.symbol, "SELL", pos.qty, fill_price,
                           _utc_today(), reason, r_multiple=r_mult, pnl=pnl)
        self._event("INFO", f"EXIT {pos.symbol} x{pos.qty} @ {fill_price:.2f} "
                            f"({reason}) -> P&L ${pnl:+,.0f}")
        self.save()

    def on_partial_exit(self, call_id: int, shares: int, fill_price: float,
                        reason: str) -> None:
        """Book a PARTIAL stop fill (adapter review M3): ONLY the filled
        shares leave the book; the remainder keeps the position — with the
        stop marked MISSING, because a polled stop event is TERMINAL at the
        venue (partially-filled-then-cancelled): nothing protects the rest
        until reconcile pass 4 re-places it."""
        if fill_price is None:
            raise ValueError("on_partial_exit requires a fill price; use "
                             "on_exit_unreconciled for a missing one")
        pos = self.state.positions.get(str(call_id))
        if pos is None or shares <= 0:
            return
        shares = min(shares, pos.qty)
        if shares == pos.qty:
            self.on_exited(call_id, fill_price, reason)
            return
        pnl = (fill_price - pos.fill_price) * shares
        self.state.sleeve_cash += shares * fill_price
        pos.qty -= shares
        pos.stop_order_ref = None
        pos.stop_missing = True
        r_mult = ((fill_price - pos.fill_price) / pos.risk_per_share
                  if pos.risk_per_share > 0 else None)
        self._record_trade(pos.symbol, "SELL", shares, fill_price,
                           _utc_today(), f"{reason}_partial",
                           r_multiple=r_mult, pnl=pnl)
        self._event("WARN", f"PARTIAL {reason} {pos.symbol}: {shares} sold @ "
                            f"{fill_price:.2f} (call {call_id}); {pos.qty} "
                            f"remain UNPROTECTED until the stop re-places")
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
        self._record_trade(CORE, "BUY" if qty_delta > 0 else "SELL",
                           qty_delta, price, _utc_today(), "core")
        self.save()

    def on_sweep(self, qty_delta: int, price: float) -> None:
        self.state.bil_qty += qty_delta
        self.state.sleeve_cash -= qty_delta * price
        self._record_trade(CASH_VEHICLE, "BUY" if qty_delta > 0 else "SELL",
                           qty_delta, price, _utc_today(), "sweep")
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

    def request_flatten(self, today: str) -> None:
        """/kill stage 1 (R2): journal the flatten request (persisted — a
        restart resumes it, same doctrine as pending_entries) and halt the
        book immediately (no new entries). Stage 2 — the actual flatten —
        runs on the blend LOOP thread's next cycle (execute_flatten): that
        thread owns the adapter's ib_async event loop, while an API thread
        pumping a fresh loop against the shared connection would time out
        every wait and risk session corruption."""
        self.state.flatten_request = {"ts": int(time.time()), "date": today}
        self.state.halted = "KILL"
        self._event("RED", "kill: halt engaged; flatten queued for the "
                           "execution loop")
        self.save()

    def resume(self) -> None:
        self.state.halted = None
        if self.state.flatten_request is not None:
            # A queued kill-flatten must never fire against a RESUMED book.
            self.state.flatten_request = None
            self._event("WARN", "resume: queued kill-flatten request "
                                "cleared before execution")
        self._event("INFO", "blend resumed")
        self.save()

    def status_summary(self, prices: dict[str, float] | None = None) -> dict:
        st = self.state
        out = {
            "enabled": True,
            "halted": st.halted,
            "flatten_pending": st.flatten_request is not None,
            "initialized": st.initialized,
            "positions": {k: asdict(v) for k, v in st.positions.items()},
            "open_count": len(st.positions),
            "stop_missing": [k for k, v in st.positions.items()
                             if v.stop_missing or not v.stop_order_ref],
            "unverifiable": [k for k, v in st.positions.items()
                             if v.history_gap],
            "pending_entries": sorted(st.pending_entries),
            "pending_book_orders": sorted(st.pending_book_orders),
            "unreconciled": st.unreconciled,
            "orphan_stops": sorted(st.orphan_stop_refs),
            "sleeve_cash": round(st.sleeve_cash, 2),
            "bil_qty": st.bil_qty,
            "spy_qty": st.spy_qty,
            "core_cash": round(st.core_cash, 2),
            "budget_cap": getattr(self.cfg, "blend_budget", 0.0) or None,
            "gate": st.last_gate,
            "budget_utilization": None,
            "events": st.events[-40:],
        }
        if prices:
            out["sleeve_value"] = round(self.sleeve_value(prices), 2)
            out["core_value"] = round(self.core_value(prices), 2)
            book = self.book_value(prices)
            out["book_value"] = round(book, 2)
            out["sleeve_weight"] = round(self.sleeve_value(prices) / book, 4) if book else None
            util = self.budget_utilization(prices)
            out["budget_utilization"] = (round(util, 4)
                                         if util is not None else None)
        return out

    def feed(self, prices: dict[str, float], today: str) -> dict:
        """Public-safe read-only feed body for the Execution dashboard.
        BOOK STATE ONLY — no credentials, no account ids, no token material,
        no order refs (the caller adds mode + last_cycle)."""
        st = self.state
        positions = []
        for pos in st.positions.values():
            try:
                days = (date.fromisoformat(today)
                        - date.fromisoformat(pos.entry_date)).days
            except (ValueError, TypeError):
                days = None
            positions.append({"symbol": pos.symbol, "qty": pos.qty,
                              "entry": round(pos.fill_price, 4),
                              "entry_date": pos.entry_date,
                              "trail_level": round(pos.stop_level, 4),
                              "days_held": days})
        util = self.budget_utilization(prices)
        book_usd = getattr(self.cfg, "blend_book_usd", 0.0) or 0.0
        budget = getattr(self.cfg, "blend_budget", 0.0) or 0.0
        if budget > 0 and book_usd > 0:
            book_usd = min(book_usd, budget)    # same clamp as first boot
        return {
            "halted": st.halted,
            "gate": st.last_gate,
            "book": {
                "sleeve_cash": round(st.sleeve_cash, 2),
                "core_qty": st.spy_qty,
                "bil_qty": st.bil_qty,
                "equity_estimate": (round(self.book_value(prices), 2)
                                    if prices else None),
                "budget_utilization": (round(util, 4)
                                       if util is not None else None),
                "initial_book_usd": book_usd or None,
            },
            "positions": positions,
            "trades": st.trades[-TRADE_LOG_MAX:],
            "equity_curve": st.equity_curve,
            "unreconciled": len(st.unreconciled),
        }


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
        held = pos.qty
        filled = abs(int(f.get("qty") or 0))
        if fill is None:
            mgr.on_exit_unreconciled(pos.call_id,
                                     "stop filled WITHOUT a fill price")
            alert(f"🚨 blend stop fill for {pos.symbol} "
                  f"(call {pos.call_id}) carried NO fill price — trade "
                  f"UNRECONCILED, proceeds NOT booked, manual "
                  f"reconciliation needed")
        elif 0 < filled < held:
            # M3: partially-filled-then-cancelled stop — book ONLY the
            # filled shares; the remainder stays held (and unprotected
            # until pass 4 re-places its stop). Booking the full book qty
            # here was the oversell/short the adapter review flagged.
            mgr.on_partial_exit(pos.call_id, filled, fill, "stop_filled")
            alert(f"⚠️ blend stop PARTIAL fill {pos.symbol} {filled} of "
                  f"{held} @ {fill:.2f} (call {pos.call_id}) — "
                  f"{held - filled} remain held, stop re-placed by "
                  f"reconcile")
        else:
            mgr.on_exited(pos.call_id, fill, "stop_filled")
            alert(f"🧬 blend STOP FILLED {pos.symbol} x{held} @ "
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
         order (counter-agent N15); a venue-REJECTED journal (entry or
         book order) is CLEARED loudly, never left pending forever
         (adapter review m1);
      3. retry cancelling retired stops whose cancel failed;
      3b. re-verify each believed-working protective stop still WORKS at
         the venue (adapter review m4): an IB-initiated GTC cancel
         (corporate action, ack-limbo residue) demotes it to STOP_MISSING;
      4. re-place any missing protective stop (STOP_MISSING).
    Raises if the adapter cannot answer (ExecutorConnectionError while the
    gateway is down): the cycle FAILS CLOSED — no decision against
    unreconciled state. On success the venue-history horizon clock
    (state.last_reconcile_ts) is stamped; the gap since the PREVIOUS
    successful pass is kept on mgr._reconcile_gap_s for the blackout
    guard in the exit/kill flatten paths (adapter review m2)."""
    st = mgr.state
    mgr._reconcile_gap_s = (time.time() - st.last_reconcile_ts
                            if st.last_reconcile_ts else 0.0)

    # 0) blackout-horizon guard (R1): a gap longer than what venue order
    #    history serves means a stop fill INSIDE the blackout may be
    #    invisible FOREVER — not just this cycle. Flag every held position
    #    UNVERIFIABLE (persisted) BEFORE anything acts on it; the flag
    #    clears ONLY on positive venue evidence (pass 1b), never because
    #    a later reconcile stamped a fresh timestamp.
    if mgr._reconcile_gap_s > HISTORY_HORIZON_S:
        newly = [p for p in st.positions.values() if not p.history_gap]
        if newly:
            for pos in newly:
                pos.history_gap = True
            mgr.save()
            names = ", ".join(f"{p.symbol} x{p.qty}" for p in newly)
            mgr._event("RED", f"blackout gap "
                              f"{mgr._reconcile_gap_s / 86400.0:.1f}d exceeds "
                              f"the venue-history horizon: {names} parked "
                              f"UNVERIFIABLE until venue positions verify")
            alert(f"🚨🚨 blend: no successful reconcile for "
                  f"{mgr._reconcile_gap_s / 86400.0:.1f}d — order history "
                  f"cannot prove what filled during the blackout. {names} "
                  f"parked UNVERIFIABLE: no exit or /kill will MKT-sell "
                  f"them until venue POSITIONS positively verify the shares")

    # 1) stop fills
    _ingest_fills(mgr, adapter, alert)

    # 1b) positive verification of UNVERIFIABLE positions (R1): venue
    #     POSITIONS are the strongest evidence — what does the account
    #     actually hold NOW? Shares held -> unpark (stop re-verified /
    #     re-placed by passes 3b/4); shares gone -> the stop filled
    #     invisibly: book it when refreshed order history serves a priced
    #     fill, else park UNRECONCILED (repo law: no silent zero). An
    #     unanswerable venue keeps the flag — fail closed, retried every
    #     cycle.
    get_held = getattr(adapter, "stock_position", None)
    for key, pos in list(st.positions.items()):
        if not pos.history_gap:
            continue
        held = None
        if get_held is not None:
            try:
                held = get_held(pos.symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("blackout verify %s: venue positions "
                               "unavailable (%s)", pos.symbol, exc)
        if held is None:
            mgr._event("WARN", f"{pos.symbol} (call {pos.call_id}) still "
                               f"UNVERIFIABLE: venue positions unavailable")
            continue
        book_qty = sum(p.qty for p in st.positions.values()
                       if p.symbol == pos.symbol)
        if held >= book_qty:
            pos.history_gap = False
            stop = adapter.find_stock_order(
                stop_client_id(pos.call_id, pos.stop_level))
            if stop is None or stop.get("status") != "working":
                pos.stop_missing = True     # pass 4 re-places (same cid:
                pos.stop_order_ref = None   # a surviving stop is adopted)
            mgr.save()
            alert(f"🧬 blend: {pos.symbol} x{pos.qty} (call {pos.call_id}) "
                  f"POSITIVELY verified still held at the venue after the "
                  f"blackout — unparked"
                  + ("" if not pos.stop_missing
                     else " (protective stop re-placing)"))
            continue
        # Shares gone (fully or partly): the stop filled inside the
        # blackout. Book only at a REAL venue price.
        gone = book_qty - max(held, 0)
        o = adapter.find_stock_order(stop_client_id(pos.call_id,
                                                    pos.stop_level))
        fill = (o or {}).get("fill_price")
        peers = [p for p in st.positions.values()
                 if p.symbol == pos.symbol and p.history_gap]
        if (len(peers) == 1 and o is not None
                and o.get("status") == "filled" and fill is not None):
            if gone >= pos.qty:
                mgr.on_exited(pos.call_id, fill, "stop_filled")
                alert(f"🧬 blend: {pos.symbol} stop fill from the blackout "
                      f"window recovered from venue history — booked "
                      f"x{pos.qty} @ {fill:.2f}")
            else:
                mgr.on_partial_exit(pos.call_id, gone, fill, "stop_filled")
                rem = st.positions.get(key)
                if rem is not None:
                    rem.history_gap = False     # remainder is venue truth
                    mgr.save()
                alert(f"⚠️ blend: PARTIAL blackout stop fill {pos.symbol} "
                      f"{gone} of {pos.qty} @ {fill:.2f} booked — remainder "
                      f"re-protected by reconcile")
        else:
            # No priced fill visible (or ambiguous same-symbol peers):
            # the shares left the book at an unknowable price.
            mgr.on_exit_unreconciled(
                pos.call_id,
                "blackout: venue no longer holds the shares and no priced "
                "stop fill is visible — UNVERIFIABLE")
            alert(f"🚨🚨 blend: {pos.symbol} x{pos.qty} (call "
                  f"{pos.call_id}) is GONE at the venue after the blackout "
                  f"and order history serves no priced fill — UNVERIFIABLE, "
                  f"parked for manual booking; nothing sold")

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
        elif o.get("status") == "cancelled":
            # m1: the venue REJECTED the journaled MOO — the journal must
            # not sit pending forever (it consumes a max_open slot and
            # blocks the call_id). Clear it, log a REJECTED trade row
            # (display-only: nothing books), and alert; a republished fire
            # retries cleanly (venue dedupe excludes cancelled priors).
            mgr.clear_pending_entry(it["call_id"])
            mgr._record_trade(it["symbol"], "BUY", it["qty"], 0.0,
                              rec.get("date", today), "entry_rejected")
            mgr._event("RED", f"entry {it['symbol']} (call {it['call_id']}) "
                              f"REJECTED by the venue — journal cleared, "
                              f"max_open slot released")
            mgr.save()
            alert(f"🚨 blend ENTER {it['symbol']} (call {it['call_id']}) "
                  f"REJECTED by the venue — nothing entered; slot released, "
                  f"journal cleared (a republished fire may retry)")
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
        elif o.get("status") == "cancelled":
            # m1: venue-REJECTED book order — clear the journal (it would
            # otherwise accumulate forever while blocking its kind, M1)
            # and let step() re-plan a fresh intent next cycle.
            mgr.clear_pending_book_order(cid)
            mgr._event("RED", f"{rec['kind']} {rec['symbol']} x{rec['qty']} "
                              f"REJECTED by the venue — journal cleared, "
                              f"re-planned next cycle")
            alert(f"🚨 blend {rec['kind']} {rec['symbol']} x{rec['qty']} "
                  f"REJECTED by the venue — journal cleared, re-planned "
                  f"next cycle")
        # status "working": async order awaiting its fill — keep the journal
        # (step() plans no new order of this kind while it is pending, M1).

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

    # 3b) re-verify believed-working protective stops (m4): only POSITIVE
    #     venue evidence demotes — an order KNOWN to the venue and reported
    #     'cancelled' (an IB-initiated GTC cancel never surfaces through the
    #     fill poll, which skips cancelled-no-shares stops by design) marks
    #     the position STOP_MISSING for pass 4 to re-place. An unknown
    #     lookup is left alone.
    for pos in list(st.positions.values()):
        if pos.stop_missing or not pos.stop_order_ref or pos.history_gap:
            continue
        o = adapter.find_stock_order(stop_client_id(pos.call_id,
                                                    pos.stop_level))
        if o is not None and o.get("status") == "cancelled":
            mgr.mark_stop_missing(pos.call_id)
            alert(f"🚨 blend: resting stop for {pos.symbol} "
                  f"(call {pos.call_id}) was CANCELLED at the venue — "
                  f"position naked; re-placing now")

    # 4) missing protective stops. R1: never for an UNVERIFIABLE position —
    #    a new SELL stop on shares the account may no longer hold is itself
    #    a short path; pass 1b must positively verify first.
    for pos in list(st.positions.values()):
        if pos.history_gap:
            continue
        if pos.stop_missing or not pos.stop_order_ref:
            if _ensure_stop(mgr, adapter, pos, alert):
                alert(f"🧬 blend: protective stop restored for {pos.symbol} "
                      f"(call {pos.call_id}) at {pos.stop_level:.2f}")

    # Reconciled against an answering venue: stamp the horizon clock (m2).
    st.last_reconcile_ts = time.time()
    mgr.save()


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

    M3: after ANY non-raising cancel (True or the ambiguous False), queued
    venue fills are ingested FIRST — a partially-filled-then-cancelled stop
    books its filled shares and the MKT sell below sizes from the book's
    venue-truth REMAINING qty, never the step-time full qty (the oversell
    the adapter review flagged).

    m2 (venue-history horizon): a False cancel + verification showing
    nothing + a reconcile gap > 1 day means the stop's fill may predate
    visible order history — UNVERIFIABLE: park + alert, never a MKT sell.

    Returns True only when the exit's proceeds actually BOOKED this cycle
    (directly or via the racing stop fill) — a deferred or UNRECONCILED
    exit returns False so run_cycle drops the entries its proceeds were
    meant to fund (counter-agent N5)."""
    key = str(it["call_id"])
    pos0 = mgr.state.positions.get(key)
    if pos0 is not None and pos0.history_gap:
        # R1: UNVERIFIABLE since a blackout — its stop may have filled
        # invisibly, so a MKT sell could short. Defer until reconcile pass
        # 1b positively verifies the shares at the venue.
        alert(f"🚨 blend EXIT {it['symbol']} deferred: position is "
              f"UNVERIFIABLE after a venue-history blackout — nothing sold "
              f"until venue positions verify it")
        return False
    ref = it.get("stop_order_ref")
    if ref:
        try:
            cancelled = adapter.cancel_stock_order(ref)
        except Exception as exc:  # noqa: BLE001
            alert(f"⚠️ blend EXIT {it['symbol']} deferred: stop cancel "
                  f"failed ({exc}); position kept — retried next cycle "
                  f"(a stop fill meanwhile reconciles first)")
            return False
        # The stop may have (partially) filled before the cancel landed:
        # ingest venue fills so the book's qty is venue truth (M3).
        _ingest_fills(mgr, adapter, alert)
        if key not in mgr.state.positions:
            alert(f"🧬 blend EXIT {it['symbol']} no-op: its stop had "
                  f"already filled — booked from the venue fill")
            return key not in mgr.state.unreconciled
        if (not cancelled
                and getattr(mgr, "_reconcile_gap_s", 0.0) > HISTORY_HORIZON_S):
            # m2: "already gone", nothing verifiable, and the last
            # successful reconcile predates what venue history serves —
            # the stop may have filled INSIDE the blackout. A MKT sell
            # here could short already-stopped-out shares. Park loudly.
            mgr.on_exit_unreconciled(
                it["call_id"],
                f"{it['reason']}: stop already gone and the venue-history "
                f"horizon was exceeded (reconcile gap "
                f"{mgr._reconcile_gap_s / 86400.0:.1f}d) — UNVERIFIABLE")
            alert(f"🚨🚨 blend EXIT {it['symbol']} UNVERIFIABLE after a "
                  f"multi-day blackout: the stop is already gone but its "
                  f"fill may predate visible order history — NOTHING sold; "
                  f"verify the account manually and book by hand")
            return False
    pos = mgr.state.positions.get(key)
    if pos is None:
        return key not in mgr.state.unreconciled
    qty = pos.qty        # M3: venue-truth remaining, never the step-time qty
    try:
        r = adapter.place_stock_order(it["symbol"], -qty, "MKT",
                                      ref_price=prices.get(it["symbol"]),
                                      client_order_id=exit_client_id(it["call_id"]))
    except Exception:
        if ref:
            # m3: the working stop was retired above but the sell did not
            # complete — the position must NOT be believed protected by a
            # cancelled stop. STOP_MISSING is loud, blocks entries, and
            # pass 4 re-places; a MKT that actually landed dedupes by its
            # deterministic exit cid on the retry.
            mgr.mark_stop_missing(it["call_id"])
            alert(f"🚨 blend EXIT {it['symbol']}: stop cancelled but the "
                  f"MKT sell failed — position UNPROTECTED (STOP_MISSING); "
                  f"stop re-placed next reconcile, sell retried via the "
                  f"exit cid")
        raise
    fill = r.get("fill_price")
    if fill is None:
        mgr.on_exit_unreconciled(it["call_id"],
                                 f"{it['reason']}: venue ack without a fill "
                                 f"price")
        alert(f"🚨 blend EXIT {it['symbol']} x{qty} UNRECONCILED: no "
              f"fill price from the venue — proceeds NOT booked, manual "
              f"reconciliation needed")
        return False
    mgr.on_exited(it["call_id"], fill, it["reason"])
    alert(f"🧬 blend EXIT {it['symbol']} x{qty} ({it['reason']})")
    return True


def execute_flatten(mgr: Blend3070Manager, adapter, alert) -> None:
    """/kill stage 2 (R2): the LOOP thread executes a journaled flatten
    request — it owns the adapter's ib_async event loop, and run_cycle has
    already reconciled (N14 reconcile-first still holds: stop fills are
    booked, so only positions STILL actually held are closed). The K-d law
    survives: a RAISING stop cancel means the stop likely FILLED — park,
    never a MKT sell on top of it. R1 UNVERIFIABLE (history_gap) positions
    stay parked untouched. The completion alert states exactly what closed
    vs what parked — the kill switch never overclaims."""
    st = mgr.state
    closed: list[str] = []
    parked: list[str] = []
    unrec: list[str] = []
    for key in list(st.positions):
        pos = st.positions.get(key)
        if pos is None:
            continue
        sym = pos.symbol
        if pos.history_gap:
            # R1: its stop may have filled invisibly inside a blackout —
            # a MKT sell could short. Stays parked until a reconcile
            # positively verifies it at the venue.
            parked.append(sym)
            alert(f"🚨🚨 blend kill: {sym} NOT flattened — UNVERIFIABLE "
                  f"after a venue-history blackout; parked until venue "
                  f"positions verify it, verify the account manually")
            continue
        stop_ref = pos.stop_order_ref
        if stop_ref:
            cancel_raised = False
            try:
                cancelled = adapter.cancel_stock_order(stop_ref)
            except Exception as exc:  # noqa: BLE001
                # Pinned adapter contract: a RAISING cancel means the stop
                # FILLED. Must never fall through to the MKT sell (K-d).
                logger.exception("kill flatten: stop cancel %s raised "
                                 "(stop likely FILLED): %s", key, exc)
                cancel_raised = True
                cancelled = False
            # M3: whether the cancel succeeded or found the stop "already
            # gone", it may have (partially) filled first — ingest venue
            # fills so the sell below sizes from venue truth.
            verify_ok = True
            try:
                _ingest_fills(mgr, adapter, alert)
            except Exception as exc:  # noqa: BLE001
                verify_ok = False
                logger.exception("kill flatten: fill verify failed: %s", exc)
            pos = st.positions.get(key)
            if pos is None:
                # Settled by its own stop fill (or parked priceless).
                (unrec if key in st.unreconciled else closed).append(sym)
                continue
            if cancel_raised or not verify_ok:
                # FAIL CLOSED (K-d): the stop signalled FILLED and/or venue
                # truth is unverifiable — park loudly; reconcile settles it.
                mgr.record_orphan_stop(stop_ref, {"symbol": sym,
                                                  "qty": -pos.qty,
                                                  "call_id": pos.call_id})
                parked.append(sym)
                alert(f"🚨🚨 blend kill: {sym} NOT flattened — stop cancel "
                      f"{'raised (likely filled)' if cancel_raised else 'unverifiable'}; "
                      f"position parked for reconcile, verify manually")
                continue
            if not cancelled:
                if mgr._reconcile_gap_s > HISTORY_HORIZON_S:
                    # m2 belt: "already gone" past the venue-history
                    # horizon — UNVERIFIABLE, park loudly (R1's flag should
                    # already have caught this; keep the belt).
                    mgr.record_orphan_stop(stop_ref, {"symbol": sym,
                                                      "qty": -pos.qty,
                                                      "call_id": pos.call_id})
                    parked.append(sym)
                    alert(f"🚨🚨 blend kill: {sym} NOT flattened — stop "
                          f"already gone past the venue-history horizon: "
                          f"UNVERIFIABLE, nothing sold; verify manually")
                    continue
                # Verified still held with a possibly-resting stop: track
                # it so a later fill alerts RED and the cancel retries.
                mgr.record_orphan_stop(stop_ref, {"symbol": sym,
                                                  "qty": -pos.qty,
                                                  "call_id": pos.call_id})
        try:
            # M3: -pos.qty is the venue-truth REMAINING qty (a partial
            # stop fill above already reduced it).
            r = adapter.place_stock_order(
                sym, -pos.qty, "MKT",
                client_order_id=f"blend-{pos.call_id}-kill")
            fill = r.get("fill_price")
            if fill is None:
                # Repo law: never book at a silent 0.0.
                mgr.on_exit_unreconciled(pos.call_id,
                                         "manual kill: venue ack without "
                                         "a fill price")
                unrec.append(sym)
                alert(f"🚨 blend kill close {sym} x{pos.qty} UNRECONCILED: "
                      f"no fill price — proceeds NOT booked, manual "
                      f"reconciliation needed")
            else:
                mgr.on_exited(pos.call_id, fill, "manual kill")
                closed.append(sym)
        except Exception as exc:  # noqa: BLE001
            logger.exception("kill flatten close %s failed: %s", key, exc)
            if stop_ref:
                # The stop was retired above but the sell failed: the
                # position must not be believed protected (m3 pattern) —
                # pass 4 re-places while the book stays halted.
                mgr.mark_stop_missing(pos.call_id)
            parked.append(sym)
            alert(f"🚨 blend kill: MKT close {sym} FAILED ({exc}) — "
                  f"position still held; book halted, close manually or "
                  f"wait for reconcile")
    st.flatten_request = None       # executed (outcomes alerted below)
    mgr.save()
    # Honest completion summary: exactly what closed vs what did not.
    if parked or unrec:
        alert(f"🔴 blend kill flatten finished WITH EXCEPTIONS: "
              f"{len(closed)} closed ({', '.join(closed) or 'none'})"
              + (f", {len(unrec)} sold but UNRECONCILED "
                 f"({', '.join(unrec)})" if unrec else "")
              + f", {len(parked)} NOT closed ({', '.join(parked)}) — "
                f"parked positions need manual verification; book stays "
                f"halted until /resume")
    elif closed:
        alert(f"🔴 blend kill flatten complete: {len(closed)} position(s) "
              f"closed ({', '.join(closed)}); book halted until /resume")
    else:
        alert("🔴 blend kill flatten complete: book was already flat; "
              "halted until /resume")


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

    # PHASE 0b — a journaled /kill flatten request executes HERE, on the
    # loop thread that owns the adapter's event loop (R2). Reconcile above
    # already booked any stop fills; the book stays halted either way.
    if mgr.state.flatten_request is not None:
        execute_flatten(mgr, adapter, alert)

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
                        > mgr.state.sleeve_cash
                        - mgr.reserved_sleeve_cash() + CASH_EPS):
                    # Belt: entries spend only SETTLED cash (exits + the BIL
                    # raise have already booked by this point in intent
                    # order), minus cash a pending sweep BUY will debit at
                    # adoption (M1) — the ledger never goes negative.
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
                if any(rec["kind"] == "core-buy"
                       for rec in mgr.state.pending_book_orders.values()):
                    # M1 belt (step already suppresses planning): never
                    # stack a second core buy on an unadopted working one.
                    alert(f"🧬 blend CORE buy skipped: a prior core buy is "
                          f"still awaiting adoption")
                    continue
                px = prices.get(CORE, 0.0)
                qty = it["qty"]
                if px > 0:   # never overdraw core cash on a short transfer
                    qty = min(qty, int(max(mgr.state.core_cash, 0.0) // px))
                if qty > 0:
                    # Write-ahead journal + deterministic client id: a crash
                    # between placement and booking is adopted by reconcile
                    # pass 2b, never re-bought (counter-agent N15).
                    cid = mgr.record_pending_book_order("core-buy", CORE,
                                                        qty, today,
                                                        ref_price=px or None)
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
                if any(rec["kind"] == "sweep"
                       for rec in mgr.state.pending_book_orders.values()):
                    # M1 belt (step already suppresses planning): never
                    # stack a second sweep on an unadopted working one.
                    alert(f"🧬 blend SWEEP skipped: a prior sweep is still "
                          f"awaiting adoption")
                    continue
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
                    cid = mgr.record_pending_book_order(
                        "sweep", CASH_VEHICLE, qty, today,
                        ref_price=prices.get(CASH_VEHICLE))
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
    # Post-execution marks (fresh quotes for what the book NOW holds): the
    # pre-cycle price set can miss names entered this cycle.
    post_prices = reference_prices(adapter, mgr, None)
    # M2: publish the mark cache the API threads (/status, /blend/feed)
    # serve — they must NEVER touch the adapter/ib_async loop themselves.
    mgr.mark_cache = {"prices": post_prices, "ts": time.time()}
    mgr.record_equity_snapshot(today, post_prices)  # daily equity point
    mgr.check_budget_alarm(post_prices, alert)      # 85% one-shot / 75% re-arm
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
        if any(rec["kind"] == "core-rebal-sell"
               for rec in mgr.state.pending_book_orders.values()):
            # M1 belt (step already suppresses planning): never stack a
            # second rebalance sell on an unadopted working one.
            return False
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
                                            today, ref_price=spy_px)
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
