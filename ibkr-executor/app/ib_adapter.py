"""IBKR venue adapter (ib_async against the in-container IB Gateway).

Translates the manager's venue-agnostic structures into IBKR combo orders:
  {"underlying": "NG", "kind": "call_spread", "expiry_hint": "2027-02",
   "lo_strike_pct": 1.10, "hi_strike_pct": 1.45}
-> qualify underlying -> option chain -> nearest expiry >= hint -> strikes
   nearest pct-of-spot on the real grid -> 2-leg BAG combo, limit at mid,
   quantity = budget // (net debit per combo).

DryAdapter mirrors the interface with logged intents and synthetic fills so
the service runs green with no gateway and no credentials (OFFLINE mode).
Everything venue-real is validated in the PAPER phase before live matters.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# The outage ledger's cause for a K5 outage (OutageLog.mark_kind): the gateway
# is connected, logged in and answering, but no session's connect-time
# open-orders sync ends, so nothing can be traded. The service's gateway watch
# reads it (service._gateway_watch). Defined HERE, not imported from
# .outages: this module is also loaded on its own, outside the package, for
# its pure rounding helpers (composer/scripts/tests/test_mirror_dry.py).
KIND_OPEN_ORDERS_UNSYNCED = "open_orders_unsynced"

UNDERLYINGS = {
    # symbol -> (secType, exchange, currency, option multiplier)
    "NG": ("FUT", "NYMEX", "USD", 10_000),
    "SB": ("FUT", "NYBOT", "USD", 1_120),     # ICE US softs route as NYBOT
    "SLV": ("STK", "SMART", "USD", 100),
}

# -- stock/ETF (blend3070 paper phase) -----------------------------------------
STOCK_EXCHANGE = "SMART"
STOCK_CURRENCY = "USD"
VENUE_HISTORY_TIMEOUT_S = 20.0  # bound on reqAllOpenOrders / reqCompletedOrders.
                             # ib_async's RequestTimeout defaults to 0 = wait
                             # FOREVER; on 2026-09-08 the gateway never
                             # answered reqCompletedOrders after a relogin and
                             # the loop thread hung on the first cycle with
                             # /health reading "ok" (loop_age null) for 15 min.
PLACE_ACK_TIMEOUT_S = 10.0   # no venue ack within this -> raise (idempotent
                             # retry via the deterministic client_order_id)
MKT_FILL_WAIT_S = 5.0        # bounded wait for a synchronous MKT fill (liquid
                             # ETFs fill in well under this during RTH); a MKT
                             # still working after it returns 'working'
CANCEL_ACK_TIMEOUT_S = 10.0  # ambiguous cancel timeout -> RAISE (fail closed)
WAIT_TICK_S = 0.25           # event-loop pump granularity inside waits
QUOTE_WAIT_S = 8.0           # B8: bounded WAIT-FOR-TICK for spot() when the
                             # config carries no `ib_quote_wait_s` (the real
                             # Config does: 6.0). The fixed `sleep(3)` this
                             # replaced was a guess in both directions: it
                             # burned 3s on every quote that had already
                             # arrived, and it gave up on every one that had
                             # not (a cold subscription on a thin name
                             # routinely needs longer).
MKT_DATA_TYPE_DELAYED = 3    # reqMarketDataType(3) = delayed: the PER-CALL
                             # escalation target when the configured feed
                             # (`ib_market_data_type`, default 1 = live)
                             # returns nothing and `ib_allow_delayed` permits
                             # it. B8 asked for 4 (delayed-frozen) so that an
                             # UNENTITLED instrument degrades instead of
                             # returning nan forever (the gateway answers an
                             # unentitled request with error 354 and NO tick
                             # at all, which `marketPrice()` reports as nan —
                             # the exact symptom of an ordinary missing
                             # quote). The merge keeps that intent but makes
                             # the degradation EXPLICIT: escalated per call,
                             # alerted once, refused under the go-live
                             # posture; the "frozen" half is served by the
                             # explicit previous-close read in the walk.
                             # Marks are never fill prices (fills come back
                             # from the venue), and a delayed or close-derived
                             # mark is logged as such, never silently adopted.
COMMISSION_WAIT_S = 1.5      # after a synchronous fill, wait this long for
                             # IB's commissionReport before reading it
                             # (counter-agent round 2: read too early = 0.0)
# ib_async warning codes: informational, never a rejection reason
_IB_WARNING_CODES = {105, 110, 165, 321, 329, 399, 404, 434, 492, 10167}
# ... except these, which KILL an order rather than annotate it, and are
# therefore the reason a dead one died. Round 20 (2026-09-11): 110 was in
# the suppression set, so the three refused GH stops — refused for exactly
# this, "the price does not conform to the minimum price variation" — each
# reported "no venue reason recorded", and the cause had to be inferred
# from the price rather than read. Deliberately a SHORT list: only codes
# this book has seen kill an order (110 today; 321 the read-only refusals
# of 2026-09-08..10) or that cannot mean anything else (404, shares not
# available for short sale). Everything else keeps round 3's behaviour —
# a 399 "your order will not be placed until ..." on a cancelled order is
# still not why it was cancelled. Add to this set when a new code is
# OBSERVED killing an order, never on a guess.
_IB_DEAD_REASON_CODES = {110, 321, 404}
# ... and these are the venue's REPLY to a cancel this client sent, never why
# an order died. 2026-10-19 (live, BIL x56, permId 2127961299): the order went
# PendingSubmit -> Inactive with no error at all, the placement path cancelled
# it, IB answered 161 "Cancel attempted when order is not in a cancellable
# state", and _order_errors kept only that last message - so every reconcile
# page quoted our own cancel's reply as "venue: [161] ..." and hid that IBKR
# had given no reason. Kept out of every reason surface, and both are a
# REFUSAL of the cancel whose ib_async overlay is undone
# (_undo_refusal_overlay). 161 is observed; 10148 ("cannot be cancelled,
# state: <state>", usually a cancel already pending) is IB's documented
# explicit refusal, added on both verifiers' advice (2026-10-26): left as
# ib_async's Cancelled, a partially filled stop's remaining fill was never
# emitted and the book sold the shares again. 10147 ("not found": IB holds no
# such order) stays out - ib_async's Cancelled is the truth there.
_IB_CANCEL_REPLY_CODES = {161, 10148}
# IB's CONFIRMATION that an order is cancelled ("Order Canceled - reason:").
# ib_async 2.1 marks a not-done trade Cancelled CLIENT-SIDE on ANY non-warning
# order error (wrapper.error), so a Cancelled that arrived through an error is
# the venue's ack only when the error is this one. Through any other - 161
# above, IB REFUSING the cancel - it is ib_async's overlay on an order that
# may still be working or may have filled (_cancel_refusal).
_IB_CANCEL_CONFIRMED_CODE = 202
RECONNECT_BACKOFF_S = 15.0   # first retry delay after the gateway drops
RECONNECT_BACKOFF_MAX_S = 300.0  # backoff cap (~one attempt per blend cycle)
OUTAGE_ALERT_S = 30 * 60.0   # alert ONLY when down longer than this — the
                             # daily IB gateway auto-restart is far shorter
                             # and must be a non-event (fail closed, then
                             # auto-recover silently)
UNSYNCED_REPLACE_WAITS = 2.0  # K5 (D1 round 4): a session whose connect-time
                             # open-orders sync has still not ended this many
                             # VENUE_HISTORY_TIMEOUT_S after the connect gave
                             # up on it (40 s; ~55 s after the request was
                             # sent) is replaced by a fresh one, by the
                             # keepalive or the guarded read that meets it
                             # first (_unsynced_replace_due). Twice the
                             # bound a guarded read waits for the same answer:
                             # an answer that late is taken as lost, not slow
                             # (a 45-s-late one still lands, at 30 s); far under
                             # OUTAGE_ALERT_S, so a one-off lost answer is
                             # replaced long before the DOWN page is due; short
                             # enough that one met at the decision is replaced
                             # well inside its window (decide_at to cancel_at
                             # is 275 s), backoff and connect included.
                             # That is the FIRST replacement of an unsynced
                             # spell; each later one waits twice as long as the
                             # one before it (D1 round 5: 40, 80, 160, 320, 640
                             # s), never longer than UNSYNCED_REPLACE_MAX_S
                             # (_unsynced_replace_interval).
UNSYNCED_REPLACE_MAX_S = 15 * 60.0  # K5 (D1 round 5): the replacement interval's
                             # cap. Round 4 replaced ONCE per outage, so a fresh
                             # session that lost its answer too was kept for as
                             # long as it lived: every guarded read failed - no
                             # trade, no /kill flatten sell - where one more
                             # fresh session would have synced. A schedule keeps
                             # that cure without churn: a gateway that never
                             # answers sees one fresh session per ~15 min once
                             # the doubling reaches the cap (each connect holds
                             # the loop thread for its 15 s sync wait), and two
                             # lost answers met at the decision (15:54:25) still
                             # trade about 2.5 min later, before plan_by.
                             # KNOWN, NOT BUILT (D1 round 6, recorded): an
                             # answer that has not come by the interval is taken
                             # as LOST, never as late - the adapter cannot tell
                             # the two apart before it drops the session. A
                             # gateway that answers EVERY new session's sync a
                             # fixed ~125-220 s late after a drop at the decision
                             # therefore does not trade (round 4 kept session 2
                             # and did), and more than ~15 min late overnight
                             # never ends the outage. The record, with the cap's
                             # own costs: _unsynced_replace_interval.

# IB order states that mean the order can no longer fill.
# Terminal-dead order statuses - and ONLY these. CORRECTION (2026-08-25,
# counter-agent FATAL on 3905f98): 'ValidationError' is NOT a venue
# rejection. ib_async sets it CLIENT-SIDE for warning-class error codes
# (321, 399, 21xx...) on an order that is STILL LIVE at the broker
# (ib_async order.py: member of ActiveStates/WorkingStates, absent from
# DoneStates; a real rejection displays 'Cancelled'). Treating it as
# terminal made the dedupe re-place live orders (probe: 180 SPY bought
# where the book intended 90) and the journal clear working orders whose
# fills nothing would ever book. It maps "working"; the stuck-journal
# case is resolved by CANCEL-CONFIRMATION in the blend's pass 2b, never
# by assuming death from a status ib_async's own docs call live.
_IB_CANCELLED = ("Cancelled", "ApiCancelled", "Inactive")
# 2026-11-12 (the mirror's morning check passed on yesterday's positions):
# ib_async's sync facade only learns that the socket closed when its event
# loop RUNS, and one pump reads at most a few hundred kB - a close queued
# behind a night of account updates survives it. _drain pumps until a pump
# receives nothing; past this bound the read fails closed.
DRAIN_MAX_S = 5.0
PROVE_LIVE_TIMEOUT_S = 5.0     # bound on the liveness round trip (prove_live)
PROVE_FRESH_S = 2.0            # a session THIS connection proved less than this ago is
#                                not asked again (prove_live: ib_insync #479)
QUALIFY_TIMEOUT_S = 10.0       # bound on spot_ex's contract lookup: a gateway that
#                                stops answering must not wedge the loop thread
POSITIONS_FAIL_MEMO_S = 30.0   # a position download that timed out is not asked
#                                for again (10 s of blocking each) for this long
POSITIONS_SYNC_TIMEOUT_S = 10.0  # bound on the explicit position download of a
                                 # session whose connect-time one did not end


class ExecutorConnectionError(RuntimeError):
    """The gateway connection is down: every stock-order surface raises this
    instead of guessing — the blend cycle FAILS CLOSED on it (reconcile
    raises, no decision is taken against unreconciled venue state)."""


class ExecutorNotSyncedError(ExecutorConnectionError):
    """Connected, but this gateway session's account state cannot be read
    yet (its position download has not ended, or a backlog is still being
    read): the caller gets an error, never an empty or a cached answer."""


def _usable_px(value) -> float | None:
    """A price we are willing to act on: finite, positive, float-able."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v <= 0:                    # NaN or non-positive
        return None
    return v


# VENUE PRICE INCREMENTS (live blocker, 2026-09-11). US equities quote in
# whole CENTS at or above $1.00 and in $0.0001 increments below it (SEC Rule
# 612). IBKR REJECTS an order whose price is not a multiple of the increment
# — error 110, "The price does not conform to the minimum price variation
# for this contract" — and the order comes back Cancelled. The tracker
# publishes trail levels to four decimals (`trail_level` in the payload is
# `round(level, 4)`), so the FIRST protective stop this book ever sent live
# was 137.0507 on GH: refused three times, the position left naked and all
# new entries blocked. Nothing between the tracker and `placeOrder` had ever
# snapped a price to the venue's grid.
TICK_AT_OR_ABOVE_1 = Decimal("0.01")
TICK_BELOW_1 = Decimal("0.0001")


def stock_tick(price: Decimal) -> Decimal:
    """The venue's minimum price increment for a US equity at `price`."""
    return TICK_BELOW_1 if price < Decimal("1") else TICK_AT_OR_ABOVE_1


def round_stop_to_tick(stop_price: float, action: str) -> float:
    """Snap a protective stop to a price the venue will accept, NEVER
    tightening it.

    A SELL stop protects a long: rounding DOWN can only trigger it later,
    which is the conservative direction — the pre-registered risk per share
    (`entry_ref - trail`) is never silently reduced by a rounding. A BUY
    stop covers a short, so it rounds UP for the same reason. The move is
    at most one tick (half a cent on the GH case) and is LOGGED by the
    caller, never silent.

    Decimal, not `round()`: binary floats put 137.0507 fractionally below
    the value a decimal reader sees, and a stop is the one price on this
    book that must be exactly what the venue can hold."""
    try:
        px = Decimal(str(float(stop_price)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"stop price {stop_price!r} is not a number") from exc
    if not px.is_finite() or px <= 0:      # NaN first: it compares by raising
        raise ValueError(f"stop price {stop_price!r} must be a positive number")
    tick = stock_tick(px)
    mode = ROUND_FLOOR if action.upper() == "SELL" else ROUND_CEILING
    try:
        snapped = px.quantize(tick, rounding=mode)
    except (InvalidOperation, ValueError) as exc:   # past Decimal's context
        raise ValueError(                           # precision, e.g. 1e26
            f"stop price {stop_price!r} cannot be expressed on the venue's "
            f"{tick} grid") from exc
    if snapped <= 0:
        # a sub-tick stop that floors to zero is not a stop the venue can
        # hold; fail closed rather than send a price of 0.00
        raise ValueError(
            f"stop price {stop_price!r} rounds to {snapped} at the venue's "
            f"{tick} increment — no protective stop is placeable there")
    return float(snapped)


def round_limit_to_tick(limit_price: float, action: str) -> float:
    """Snap a LIMIT price to the venue's grid, NEVER loosening it: a BUY limit
    rounds DOWN (the order can only pay less than the caller sized it at), a
    SELL limit rounds UP. The mirror of round_stop_to_tick, whose directions
    are the opposite because a stop protects and a limit bounds. Same
    Decimal arithmetic, same fail-closed errors."""
    try:
        px = Decimal(str(float(limit_price)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"limit price {limit_price!r} is not a number") from exc
    if not px.is_finite() or px <= 0:
        raise ValueError(f"limit price {limit_price!r} must be a positive number")
    tick = stock_tick(px)
    mode = ROUND_FLOOR if action.upper() == "BUY" else ROUND_CEILING
    try:
        snapped = px.quantize(tick, rounding=mode)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"limit price {limit_price!r} cannot be expressed on the venue's "
            f"{tick} grid") from exc
    if snapped <= 0:
        raise ValueError(
            f"limit price {limit_price!r} rounds to {snapped} at the venue's "
            f"{tick} increment - no limit order is placeable there")
    return float(snapped)


def _map_status(ib_status: str) -> str:
    """IB order state -> the adapter contract's {filled, working, cancelled}."""
    if ib_status == "Filled":
        return "filled"
    if ib_status in _IB_CANCELLED:
        return "cancelled"
    return "working"


_STATUS_ECHOES = {"cancelled", "apicancelled", "inactive", "submitted",
                  "presubmitted", "filled", "pendingsubmit", "pendingcancel"}


def _trade_errors(trade, dead: bool = False, venue: str = "") -> str:
    """IB's own words for why an order died, from the trade log. Without
    this the ValidationError alert could only say 'state UNKNOWN' - the
    reason was sitting in trade.log, discarded.

    `dead=True` (the order is in a cancelled state): when no entry carries
    an error code or 'error' text, fall back to the LAST log message. An
    opening-auction order refused after the bell is cancelled with a plain
    'Order Canceled - reason: ...' line and no errorCode, so the filter
    above dropped it and five MRK rejections on 2026-09-03 read only
    'status Cancelled' (the cause had to be inferred from the order type)."""
    out = []
    dead_msg = ""
    for entry in (getattr(trade, "log", None) or []):
        code = getattr(entry, "errorCode", 0) or 0
        msg = str(getattr(entry, "message", "") or "").strip()
        status = str(getattr(entry, "status", "") or "")
        if code in _IB_CANCEL_REPLY_CODES:
            continue                # our cancel's reply, never the reason
        if (dead and code and code not in _IB_DEAD_REASON_CODES
                and (code in _IB_WARNING_CODES or 2100 <= code < 2200)):
            # the wrapper logs warnings into trade.log too: a warning is
            # never a CANCELLATION reason (round 3); for a live-but-warned
            # order it is the context the UNKNOWN alert needs, so it stays.
            # The exception is _IB_DEAD_REASON_CODES — see there.
            continue
        if code or ("rror" in msg):
            out.append(f"[{code}] {msg}" if code else msg)
        elif (msg and status in _IB_CANCELLED
              and msg.lower().replace(" ", "") not in _STATUS_ECHOES):
            dead_msg = msg          # the cancel entry's own words, if any
    # Counter-agent round 1: the reason for an after-the-bell OPG rejection
    # is delivered on ib_async's errorEvent / trade.advancedError, not as a
    # trade.log line - and a bare status echo ("Cancelled") is not a reason.
    adv = str(getattr(trade, "advancedError", "") or "").strip()
    if adv and adv not in out:
        out.append(adv)
    if venue and venue not in out:
        out.append(venue)
    if not out and dead and dead_msg:
        out.append(dead_msg)
    return "; ".join(out[-3:])


def _correction_key(fill) -> tuple:
    """(base, n) of an execution IB can correct, else (None, None). IB: "A
    correction is indicated by an ExecId which differs from a previous ExecId
    in only the digits after the final period, e.g. an ExecId ending in ".02"
    would be a correction of a previous execution with an ExecId ending in
    ".01"" (TWS API reference, IBApi.Execution.ExecId), delivered "as an
    additional execDetails callback with all parameters identical except for
    the execID" (TWS API, Executions and Commissions). Real execIds look like
    0000e0d5.6556c9f3.01.01: base = everything before the final period, n =
    the digits after it."""
    ex = getattr(fill, "execution", None)
    eid = str(getattr(ex, "execId", "") or "") if ex is not None else ""
    base, dot, tail = eid.rpartition(".")
    if not dot or not base or not tail.isdigit():
        return None, None
    return base, int(tail)


def _current_fills(fills) -> list:
    """A trade's executions with every CORRECTION in place of what it
    corrects. ib_async 2.1.0 stores each execution under its full execId
    (wrapper.execDetails: `if execId not in self.fills` -> self.fills[execId]
    and trade.fills.append), so a correction is one MORE Fill on the trade:
    summed, a 100-share execution corrected once read as 200 shares (and two
    prices, two commissions). Kept: for each base execId only the execution
    with the highest correction number (the first seen of equal ones); an
    execution whose execId has no such form is kept as it is. Order kept.
    Each correction seen is logged once, raw (_log_corrections)."""
    fills = list(fills or [])
    best: dict = {}
    for i, f in enumerate(fills):
        base, n = _correction_key(f)
        if base is not None and (base not in best or n > best[base][1]):
            best[base] = (i, n)
    keep = {i for i, _ in best.values()}
    try:
        _log_corrections(fills, best)
    except Exception as exc:  # noqa: BLE001  - observability only: never in the way of the count
        logger.debug("execution correction log failed: %s", exc)
    return [f for i, f in enumerate(fills)
            if _correction_key(f)[0] is None or i in keep]


# The execIds of executions seen CORRECTED (_current_fills), each logged once per process. Corrections
# are rare; the set is cleared past _CORRECTIONS_KEEP so it cannot grow without bound.
_CORRECTIONS_LOGGED: set = set()
_CORRECTIONS_LOCK = threading.Lock()
_CORRECTIONS_KEEP = 10_000


def _raw_fill(f) -> str:
    """one execution as IB reported it: execId, side, shares, price, commission (or that none came yet)"""
    ex = getattr(f, "execution", None)
    rep_ = getattr(f, "commissionReport", None)
    reported = rep_ is not None and bool(getattr(rep_, "execId", None))
    comm = (f"commission {getattr(rep_, 'commission', None)!r} {getattr(rep_, 'currency', '') or ''}".rstrip()
            if reported else "commission not reported yet")
    return (f"execId {getattr(ex, 'execId', None)!r} {getattr(ex, 'side', None)} {getattr(ex, 'shares', None)!r}"
            f" @ {getattr(ex, 'price', None)!r}, {comm} (orderId {getattr(ex, 'orderId', None)}, permId "
            f"{getattr(ex, 'permId', None)}, orderRef {getattr(ex, 'orderRef', None)!r}, time "
            f"{getattr(ex, 'time', None) or getattr(f, 'time', None)})")


def _log_corrections(fills: list, best: dict) -> None:
    """2026-11-13 (the buying guard's review): WARNING once per corrected execId - the raw executions
    of its base (execIds, shares, prices, commissions as seen now, and which one is counted), so the
    first correction IB sends a live order can be checked against IB's rule (_correction_key) and
    against what the adapter booked. Nothing here changes what _current_fills returns. A correction
    that arrives after its order was booked reaches this only if something reads that order's fills
    again (a late commission's true-up); ib_async's wrapper logs each execDetails and each
    commissionReport it can match at INFO (wrapper.execDetails / wrapper.commissionReport)."""
    groups: dict = {}
    for f in fills:
        base, _ = _correction_key(f)
        if base is not None:
            groups.setdefault(base, []).append(f)
    for base, group in groups.items():
        ids = {str(f.execution.execId) for f in group}
        if len(ids) < 2:
            continue                # one execution (or the same one twice): nothing was corrected
        kept = str(fills[best[base][0]].execution.execId)
        with _CORRECTIONS_LOCK:
            new = sorted(ids - {kept} - _CORRECTIONS_LOGGED)
            if not new:
                continue
            if len(_CORRECTIONS_LOGGED) >= _CORRECTIONS_KEEP:
                _CORRECTIONS_LOGGED.clear()
            _CORRECTIONS_LOGGED.update(new)
        logger.warning("execution CORRECTED by IB: %s superseded by %r, which alone is counted. Raw, as seen: %s",
                       ", ".join(map(repr, new)), kept, "; ".join(_raw_fill(f) for f in group))


def _agg_commission(trade) -> float:
    """Total commission the venue reported on a trade's executions (each
    ib_async Fill carries a commissionReport once IB sends it; 0.0 until
    then). The book debits this from the bucket that traded - before
    2026-09-04 the ledger booked price x qty and silently drifted $1/order
    from the account. A corrected execution counts once (_current_fills)."""
    total = 0.0
    for f in _current_fills(getattr(trade, "fills", []) or []):
        rep_ = getattr(f, "commissionReport", None)
        c = getattr(rep_, "commission", None) if rep_ is not None else None
        cur = getattr(rep_, "currency", "") if rep_ is not None else ""
        try:
            c = float(c)
        except (TypeError, ValueError):
            return None             # unreadable = UNREPORTED, never 0.0
        # IB's UNSET sentinel is ~1.8e308; a non-USD report is not ours.
        # An ignored report is UNREPORTED (the ledger's loud path), not an
        # authoritative 0.0 (round 3).
        if not (0.0 <= abs(c) < 1e6) or (cur and cur != "USD"):
            logger.warning("commission report ignored: %r %s", c, cur)
            return None
        total += c
    return round(total, 4)


def _commission_reported(trade) -> bool:
    """True when every execution carries a commissionReport with an execId
    - IB delivers the report a moment AFTER the fill. Of a corrected
    execution, the correction's (_current_fills)."""
    fills = _current_fills(getattr(trade, "fills", []) or [])
    if not fills:
        return False    # a completed-orders Trade carries no fills: no report
    for f in fills:
        rep_ = getattr(f, "commissionReport", None)
        if rep_ is None or not getattr(rep_, "execId", None):
            return False
    return True


def _agg_fill_price(trade) -> float | None:
    """Share-weighted average price over a trade's executions (a corrected
    one counted once, at its correction: _current_fills). None when the
    venue reported no usable price — NEVER 0.0 (repo law: a silent zero fill
    price would vaporize proceeds downstream)."""
    fills = _current_fills(getattr(trade, "fills", []) or [])
    shares = sum(int(f.execution.shares) for f in fills)
    if shares > 0:
        num = sum(int(f.execution.shares) * float(f.execution.price)
                  for f in fills)
        if num > 0:
            return num / shares
    avg = float(getattr(trade.orderStatus, "avgFillPrice", 0.0) or 0.0)
    return avg if avg > 0 else None


def _order_ref(trade) -> str:
    """The adapter-level order handle: IB's orderId (stable across a
    same-clientId reconnect; permId is accepted as an alias on lookup)."""
    return str(trade.order.orderId)


def pick_expiry(expirations: list[str], hint_ym: str) -> str | None:
    """Nearest expiry on/after the hint month (YYYYMM...)."""
    want = hint_ym.replace("-", "")
    cands = sorted(e for e in expirations if e[:6] >= want[:6])
    return cands[0] if cands else (sorted(expirations)[-1] if expirations else None)


def pick_strike(strikes: list[float], target: float) -> float | None:
    return min(strikes, key=lambda s: abs(s - target)) if strikes else None


def size_combos(budget: float, net_debit: float, multiplier: int) -> int:
    """Whole combos purchasable with budget at the quoted net debit."""
    per = net_debit * multiplier
    return max(0, int(budget // per)) if per > 0 else 0


class IBAdapter:
    def __init__(self, cfg, outage_log=None):
        # The adapter is built inside the service's daemon loop thread:
        # ensure that thread owns an asyncio event loop BEFORE IB() binds
        # one (review sub-note — a constructor raise here used to kill the
        # loop thread silently; service._loop also guards the build now).
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        from ib_async import IB               # lazy: tests inject a mock module
        self.cfg = cfg
        self.ib = IB()
        # stock/ETF surfaces (blend3070): qualified-contract cache, drain-once
        # bookkeeping for poll_stock_fills, and the re-queue buffer blend's
        # _ingest_fills uses on a mid-ingestion failure.
        self._stock_contracts: dict[str, object] = {}
        self._emitted_fill_keys: set[str] = set()
        self._requeued_fills: list[dict] = []
        # Venue error text keyed by orderId, captured off ib_async's
        # errorEvent (emitted unconditionally) so a rejection's REASON reaches
        # the operator even when trade.log carries only a status change.
        self._order_errors: dict[int, str] = {}
        # IB's REPLY to a cancel this client sent (161: not in a cancellable
        # state - usually already final), kept apart so it never overwrites
        # or poses as the rejection reason above, yet stays on the reconcile
        # page as a labelled trace. On a WORKING order a 161 can also mean
        # the cancel lost a race with a fill (_undo_refusal_overlay).
        self._cancel_replies: dict[int, str] = {}
        self._completed_orders_unavailable = False
        ev = getattr(self.ib, "errorEvent", None)
        if ev is not None:
            try:
                ev += self._on_ib_error
            except Exception as exc:  # noqa: BLE001
                logger.warning("errorEvent hook unavailable: %s", exc)
        # M5 reconnect bookkeeping: the gateway's daily auto-restart drops
        # the session — every surface reconnects with backoff via
        # _require_connected instead of staying wedged until a manual
        # container restart. Shared by the stock surfaces AND the combo
        # path (spot() goes through the same gate).
        self._reconnect_backoff = RECONNECT_BACKOFF_S
        self._next_reconnect_ts = 0.0
        # the backoff's ceiling. The default is the blend's (one attempt per
        # cycle); the service lowers it when ONLY the Composer mirror trades
        # through this adapter (mirror_only): one decision a day, timed to
        # the minute, and a /kill flatten must not wait five minutes for the
        # next connect attempt. mirror_only also words the outage alerts.
        self.reconnect_backoff_max_s = RECONNECT_BACKOFF_MAX_S
        self.mirror_only = False
        self._in_keepalive = False
        self._proven: tuple | None = None   # (monotonic, connection) of the last answered prove_live
        self._positions_failed: tuple | None = None   # (monotonic, why)
        self._disconnected_since: float | None = None
        self._outage_alerted = False
        # K5: the outage is a session up but with its open-orders sync unended
        self._open_orders_unsynced = False
        # K5 (D1 rounds 4-5), all per gateway session unless said otherwise:
        # when THIS session was found with its connect-time open-orders sync
        # unended (None: it has ended, or it never was) - while set, the
        # pending open-orders request IS that sync (K4: no other is sent
        # while one is pending); whether a guarded read already waited one
        # full VENUE_HISTORY_TIMEOUT_S for it on this session; how many
        # unsynced sessions the open OUTAGE has replaced since it last had no
        # session at all (the replacement schedule's step,
        # _unsynced_replace_interval); how many sessions the open outage
        # found with their connect-time sync unended, reset only when it
        # closes (the DOWN page's count, D1 round 6: the step restarts at a
        # failed connect and skips a session a gateway FIN brought, so it
        # under-counted); and whether the open outage saw a reconnect (the
        # recovery notice's words)
        self._sync_pending_since: float | None = None
        self._sync_wait_failed = False
        self._unsynced_replacements = 0
        self._unsynced_sessions = 0
        self._outage_reconnected = False
        # the position list of THIS session is trusted only once its
        # download is known to have ended (_session_positions); and why the
        # last account_cash() made no claim (it never raises): kind is
        # "disconnected" | "unreadable" | "no_claim"
        self._positions_synced = False
        self.last_cash_error: str | None = None
        self.last_cash_kind: str | None = None
        # Persisted outage ledger (optional). Observability must never be
        # able to break trading, so every call site tolerates None.
        self.outages = outage_log
        # market-data posture: which feed IB is actually serving, and whether
        # the operator has been told we fell back to delayed
        self._md_type: int = int(getattr(cfg, "ib_market_data_type", 1))
        self._delayed_announced = False
        # Contradictory or unsafe postures fail AT BOOT, loudly, instead of
        # producing quiet stale pricing (counter-agent A3 + go-live pin):
        # - allow_delayed=False with a delayed type configured is a
        #   contradiction (the config itself asks for what the flag forbids)
        # - live money must never boot with the delayed fallback armed
        allow = bool(getattr(cfg, "ib_allow_delayed", True))
        if not allow and self._md_type != 1:
            raise RuntimeError(
                f"config contradiction: ib_allow_delayed=false but "
                f"ib_market_data_type={self._md_type} (delayed) - refusing "
                f"to boot into silent stale pricing")
        if getattr(cfg, "trading_mode", "paper") == "live" and allow:
            raise RuntimeError(
                "go-live posture violation: trading_mode=live requires "
                "IB_ALLOW_DELAYED=false (live orders must never price on "
                "delayed or prior-close data) - set the env and redeploy")
        self._connect()

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None,
                     *args) -> None:
        """errorEvent handler: reqId is the orderId for order-scoped errors.
        Bounded: only the last message per id, ids pruned above 512."""
        try:
            if reqId is None or int(reqId) < 0:
                return
            code = int(errorCode or 0)
            if code in _IB_WARNING_CODES or 2100 <= code < 2200:
                return                       # a warning is not a reason
            # reqId shares its namespace with market-data / contract
            # requests (same counter) and the sequence restarts at the
            # gateway's nextValidId after a reconnect: record ONLY ids that
            # are this client's orders, else a stale quote error becomes a
            # later order's "reason" (round 3, HIGH)
            try:
                trades = [t for t in (self.ib.trades() or [])
                          if getattr(t.order, "orderId", None) == int(reqId)]
            except Exception:  # noqa: BLE001
                trades = []
            if not trades:
                return
            # the reply to our own cancel is never the reason: kept apart
            store = (self._cancel_replies if code in _IB_CANCEL_REPLY_CODES
                     else self._order_errors)
            store[int(reqId)] = f"[{code}] {errorString}"
            if len(store) > 512:
                for k in list(store)[:-256]:
                    store.pop(k, None)
            if code in _IB_CANCEL_REPLY_CODES:
                for t in trades:
                    self._undo_refusal_overlay(t, code)
        except Exception:  # noqa: BLE001
            pass

    def _undo_refusal_overlay(self, trade, code: int) -> None:
        """Undo ib_async's client-side Cancelled on an order whose cancel IB
        REFUSED (161 "not in a cancellable state", or 10148).

        ib_async 2.1 (wrapper.error) marks a not-done trade Cancelled on ANY
        non-warning order error, logs it, and only then emits errorEvent, so
        this handler finds the overlay as the trade's last log entry. A
        refusal says nothing about the order's state: it may be filling,
        locked for an auction, or already cancelling, and the venue's own
        next orderStatus (Filled, Cancelled) says which. Left in place, the
        overlay read as dead to every reader of the session (2026-10-26,
        verifiers A and B): cancel_stock_order took it as the ack and its
        pre-check as "already gone", find_stock_order as "cancelled"
        (reconcile 2b re-planned a stuck order: bought twice), and
        poll_stock_fills as a done stop with no fills (its later fill was
        swallowed). The status goes back to the one the venue last reported
        before any cancel - skipping the PendingCancel that ib_async's own
        IB.cancelOrder logs client-side the moment a cancel is sent - so the
        session believes no more than the venue said. Cost: an order that
        died without the session hearing reads working until the next
        reconnect resyncs it, and every cancel of it raises meanwhile (fail
        closed)."""
        log = list(getattr(trade, "log", None) or [])
        if (not log or trade.orderStatus.status != "Cancelled"
                or str(getattr(log[-1], "status", "") or "") != "Cancelled"
                or int(getattr(log[-1], "errorCode", 0) or 0) != code):
            return                  # not ib_async's overlay of this reply
        prior = ""
        for e in reversed(log[:-1]):
            st = str(getattr(e, "status", "") or "")
            if not st or st == "PendingCancel" or (st == "Cancelled" and int(
                    getattr(e, "errorCode", 0) or 0) in _IB_CANCEL_REPLY_CODES):
                continue            # a cancel in flight, or an earlier overlay
            prior = st
            break
        if not prior or prior in _IB_CANCELLED or prior == "Filled":
            prior = "Submitted"     # not done before the overlay: working
        trade.orderStatus.status = prior
        logger.warning("order %s: IBKR refused the executor's cancel ([%d]); "
                       "ib_async's client-side Cancelled undone, status back "
                       "to %s until the venue says otherwise",
                       _order_ref(trade), code, prior)

    def _venue_error(self, trade) -> str:
        oid = getattr(getattr(trade, "order", None), "orderId", None)
        try:
            return self._order_errors.get(int(oid), "") if oid is not None else ""
        except (TypeError, ValueError):
            return ""

    def _cancel_reply(self, trade) -> str:
        oid = getattr(getattr(trade, "order", None), "orderId", None)
        try:
            return self._cancel_replies.get(int(oid), "") if oid is not None else ""
        except (TypeError, ValueError):
            return ""

    def _connect(self):
        port = 4002 if self.cfg.trading_mode == "paper" else 4001
        for attempt in range(20):             # gateway boots slowly (~2 min)
            try:
                self.ib.connect(self.cfg.ib_host, port,
                                clientId=self.cfg.ib_client_id, timeout=15)
                logger.info("connected to IB gateway (%s)", self.cfg.trading_mode)
                self._apply_market_data_type()
                if self._note_connect_sync():
                    # K5: the boot session's open-orders sync did not
                    # end - not usable for open-orders reads until it does:
                    # the outage clock starts now (_reconnect's rule), its
                    # cause on the ledger (the gateway watch reads it). Ended
                    # by the first adapter call or keepalive after the late
                    # end lands - the service loop runs the keepalive while
                    # the ledger is open, whatever trades (D1 round 4).
                    logger.warning("IB gateway connected, but its open-orders "
                                   "sync did not end: not usable until it does")
                    self._disconnected_since = time.monotonic()
                    self._open_orders_unsynced = True
                    self._unsynced_sessions = int(getattr(self, "_unsynced_sessions", 0) or 0) + 1
                    self._outage("start", time.time())
                    self._outage("mark_kind", KIND_OPEN_ORDERS_UNSYNCED)
                return
            except Exception as exc:  # noqa: BLE001
                logger.info("gateway not ready (%d/20): %s", attempt + 1, exc)
                time.sleep(15)
        # a CONNECTION failure, typed: the boot-retry loop feeds the gateway
        # watch (stall / pre-open pages) only for this shape (round 3: a
        # plain RuntimeError here silenced the watch in the very state the
        # pre-open page exists for)
        raise ExecutorConnectionError("could not connect to IB gateway")

    # -- the adapter's real methods (spot, chain, open_spread, marks, close)
    # are exercised ONLY in the paper phase; each call degrades to an
    # exception the service logs rather than acts on. Implementation uses
    # ib_async primitives: qualifyContracts, reqSecDefOptParams,
    # reqMktData for legs, Bag contract with ComboLegs, LimitOrder at mid.

    def _apply_market_data_type(self, mdt: int | None = None) -> None:
        """Tell IB which data feed to serve. NEVER called before 2026-08-24,
        so IB defaulted to LIVE (type 1); a paper account without market-data
        subscriptions then returned nan for every quote, spot() raised, every
        price went absent, and the book could not seed the SPY core, sweep
        BIL or rebalance - silently, forever."""
        want = int(mdt if mdt is not None
                   else getattr(self.cfg, "ib_market_data_type", 1))
        try:
            self.ib.reqMarketDataType(want)
            self._md_type = want
        except Exception as exc:  # noqa: BLE001
            logger.warning("reqMarketDataType(%d) failed: %s", want, exc)

    def spot(self, symbol: str) -> float:
        return self.spot_ex(symbol)[0]

    def spot_ex(self, symbol: str) -> tuple[float, str]:
        """(price, source) with source in {live, last, close}.

        CR-N2: B8 gave the quote walk a previous-CLOSE fallback so that a
        thin or out-of-RTH quote stops being indistinguishable from a
        missing market-data subscription. That is right for SIZING and
        VALUATION and wrong for a FILL: a previous session's close is not
        a price anything traded at today. `spot()` alone cannot say which
        it returned, so the two callers that adopt a venue fill lacking a
        reported price were booking a close as a fill basis where the
        pre-B8 code raised and failed closed. The source is the caller's
        only way to tell, so it is returned rather than merely logged."""
        import asyncio
        from ib_async import Future, Stock
        self._require_live()
        # Symbols outside the El Nino table (SPY/BIL/sleeve names from the
        # blend book) quote as plain SMART/USD stocks.
        sec_type, exch, cur, _ = UNDERLYINGS.get(
            symbol, ("STK", STOCK_EXCHANGE, STOCK_CURRENCY, 100))
        if sec_type == "STK":
            c = Stock(symbol, exch, cur)
        else:
            c = Future(symbol, exchange=exch, currency=cur)
            c = sorted(self.ib.reqContractDetails(c),
                       key=lambda d: d.contract.lastTradeDateOrContractMonth
                       )[0].contract
        # bounded: ib_async's sync calls wait forever by default
        # (RequestTimeout 0), and a gateway that went silent without closing
        # the socket would park the loop thread here
        prev = getattr(self.ib, "RequestTimeout", 0)
        try:
            self.ib.RequestTimeout = QUALIFY_TIMEOUT_S
            self.ib.qualifyContracts(c)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise ExecutorConnectionError(
                f"IB gateway did not answer the contract lookup for {symbol} "
                f"within {QUALIFY_TIMEOUT_S:.0f}s (a session that stopped "
                f"answering)") from exc
        finally:
            self.ib.RequestTimeout = prev
        # B8 + the market-data posture (2026-08-24), composed at the merge:
        #  * a data type is requested BEFORE subscribing (B8: without it an
        #    unentitled request gets error 354 and never a single field,
        #    reported as the SAME "no market price" a thin quote produces)
        #  * WHICH type is the operator's `ib_market_data_type` (default 1,
        #    live), never a hard-coded delayed-frozen: delayed data is a
        #    visible, deliberate degradation - escalated per call, alerted
        #    once, and refused outright under the go-live posture
        #    (`ib_allow_delayed=false`, enforced at boot in live mode)
        #  * the previous CLOSE is read explicitly (B8: ib_async's
        #    marketPrice() has no close fallback, in any release) but ONLY
        #    while delayed
        #    data is allowed - a prior-close print is stale data by another
        #    name (counter-agent A4, executed proof: allow=False still
        #    returned yesterday's 600.0) - and the SOURCE goes back to the
        #    caller so a close is never booked as a fill basis (CR-N2)
        wait = float(getattr(self.cfg, "ib_quote_wait_s", QUOTE_WAIT_S))
        allow = bool(getattr(self.cfg, "ib_allow_delayed", True))
        configured = int(getattr(self.cfg, "ib_market_data_type", 1))
        # Escalation is PER CALL, bracketed by these two applies: the first
        # heals any session state (IB resets the type per session, so after
        # a gateway restart the old sticky escalation left _md_type lying
        # and every quote wedged on "already active" - the book went
        # quote-dead again daily); the finally guarantees the session is
        # never left parked on delayed for other reqMktData users.
        self._apply_market_data_type(configured)
        try:
            px, source, mdt = self._quote_once(c, symbol, wait,
                                               allow_close=allow)
            if px == px and px > 0:
                if source != "live" or (mdt is not None and mdt != 1):
                    # Honesty: say what actually backed the mark. Delayed/
                    # frozen/close-derived marks are usable for sizing and
                    # valuation (they are never fill prices) but they must
                    # never look like live.
                    logger.warning("spot(%s) = %.4f from %s data "
                                   "(marketDataType=%s) — not a live tick",
                                   symbol, px, source, mdt)
                return float(px), source
            # Configured feed returned nothing. Escalate to delayed only if
            # allowed - and say so: a degradation that prices real orders
            # must be visible, never inferred. Disallowed (go-live posture)
            # = hard failure, the cycle fails closed as it should.
            if not allow:
                raise RuntimeError(
                    f"no market price for {symbol} (market-data type "
                    f"{configured}; delayed fallback disabled)")
            if configured == MKT_DATA_TYPE_DELAYED:
                raise RuntimeError(
                    f"no market price for {symbol} on the configured "
                    f"DELAYED feed after {wait:.0f}s: no tick, no last, and "
                    f"NO PREVIOUS CLOSE - usually a MISSING MARKET-DATA "
                    f"SUBSCRIPTION / entitlement for {symbol}; check this "
                    f"account's IB market-data subscription")
            self._apply_market_data_type(MKT_DATA_TYPE_DELAYED)
            px, source, mdt = self._quote_once(c, symbol, wait,
                                               allow_close=True)
            if px != px or px <= 0:
                raise RuntimeError(
                    f"no market price for {symbol} on live OR delayed data "
                    f"after {wait:.0f}s each: no live tick, no last, and NO "
                    f"PREVIOUS CLOSE. A quote that is merely thin still "
                    f"carries a close, so on a real gateway this is usually "
                    f"a MISSING MARKET-DATA SUBSCRIPTION / entitlement for "
                    f"{symbol} (or the wrong data type) - check this "
                    f"account's IB market-data subscription before assuming "
                    f"the feed is slow")
            if not self._delayed_announced:
                self._delayed_announced = True
                from .alerts import send
                send("🔴 ACTION NEEDED (you) — IBKR is serving DELAYED "
                     "(~15min) quotes: this account has no live market-data "
                     "subscription. The 30/70 book is valuing and "
                     "rebalancing on delayed prices. Acceptable on paper; "
                     "attach a subscription and set IB_ALLOW_DELAYED=false "
                     "BEFORE switching to live money.")
            logger.warning("spot(%s) = %.4f priced on DELAYED data (from %s, "
                           "marketDataType=%s) — not a live tick",
                           symbol, px, source, mdt)
            return float(px), source
        finally:
            if getattr(self, "_md_type", configured) != configured:
                self._apply_market_data_type(configured)

    def _quote_once(self, contract, symbol: str, wait_s: float,
                    allow_close: bool) -> tuple[float, str, int | None]:
        """One subscription, one bounded wait, one guaranteed cancel.

        Returns (price, source, marketDataType as served); price is nan when
        nothing usable arrived. The subscription is ALWAYS retired, even
        when the wait raises - the pre-B8 body leaked it on every failure
        path."""
        t = self.ib.reqMktData(contract, "", False, False)
        try:
            px, source = self._await_quote(t, wait_s, symbol,
                                           allow_close=allow_close)
        finally:
            try:
                self.ib.cancelMktData(contract)
            except Exception as exc:        # noqa: BLE001
                logger.debug("cancelMktData(%s) failed: %s", symbol, exc)
        return px, source, getattr(t, "marketDataType", None)

    def _await_quote(self, ticker, wait_s: float, symbol: str = "?",
                     allow_close: bool = True) -> tuple[float, str]:
        """B8: wait for a usable tick, bounded - not a blind fixed sleep -
        and report WHICH field backed it.

        Field chain: live marketPrice, then last, bid, ask, and close only
        when allowed. source in {live, last, bid, ask, close}, or
        (nan, "none") when nothing usable arrived inside wait_s.
        Pumps the ib_async event loop the way every other bounded wait in
        this adapter does. A close-sourced price is logged per symbol,
        never silent."""
        fields = ("last", "bid", "ask") + (("close",) if allow_close else ())
        deadline = time.monotonic() + max(0.5, wait_s)
        while True:
            self.ib.sleep(WAIT_TICK_S)
            try:
                px = _usable_px(ticker.marketPrice())
            except Exception:               # noqa: BLE001  (a fake/partial
                px = None                   # ticker must not break the walk)
            if px is not None:
                return px, "live"
            for attr in fields:
                px = _usable_px(getattr(ticker, attr, None))
                if px is not None:
                    if attr == "close":
                        logger.warning("%s priced from PRIOR CLOSE (no live "
                                       "tick yet)", symbol)
                    return px, attr
            if time.monotonic() >= deadline:
                return float("nan"), "none"

    def open_spread(self, structure: dict, budget: float) -> dict:
        """Build+place the combo; returns {order_ref, premium} once filled.
        Raises on anything ambiguous — the service reports, never improvises."""
        raise NotImplementedError(
            "combo construction lands with the paper-phase deploy; "
            "OFFLINE/DRY runs never reach this path")

    def mark(self, order_ref: str) -> float | None:
        raise NotImplementedError

    def close_spread(self, order_ref: str) -> dict:
        raise NotImplementedError

    # -- stock/ETF orders (blend3070 paper phase) ------------------------------
    # Real ib_async implementation of the DryAdapter-pinned contract:
    #   * MOO = MarketOrder tif OPG; MKT = MarketOrder DAY; STP = StopOrder GTC
    #   * client_order_id maps to IB orderRef (idempotency key); placements
    #     dedupe against venue order history by orderRef before placing
    #   * cancel tri-state: FILLED -> RAISE, not-found/already-cancelled ->
    #     False, cancelled -> True; an ambiguous ack timeout RAISES (fail
    #     closed — blend defers the dependent action to the next cycle)
    #   * no silent zero fill prices: an unknown price is None, never 0.0
    #   * every method raises ExecutorConnectionError when the gateway is
    #     down — reconcile raises and the blend cycle FAILS CLOSED
    # ASYNC-FILL DESIGN (differs from DryAdapter ON PURPOSE): DryAdapter's
    # synchronous MOO/MKT fills are a SIMULATION convenience. The real venue
    # fills MOO at the next open, so place_stock_order returns status
    # 'working' immediately (never blocks on OPG) and blend's write-ahead
    # journal + reconcile pass 2/2b adopt the fill from order history by
    # orderRef on a later cycle. MKT gets one bounded MKT_FILL_WAIT_S wait
    # because blend's exit path (_execute_exit / kill) books from the
    # placement result: a MKT that misses the window returns 'working' and
    # the exit routes to the loud UNRECONCILED/provisional paths — never a
    # faked price. Threading follows the combo methods' pattern: plain
    # synchronous ib_async calls (self.ib.sleep pumps the event loop) from
    # the service loop thread that built the adapter.

    def _outage(self, method: str, *args) -> None:
        """Ledger call that can never propagate. OutageLog guards its own
        methods too; this guards the adapter against any other ledger."""
        lg = self.outages
        if lg is None:
            return
        try:
            getattr(lg, method)(*args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage ledger %s failed (ignored): %s",
                           method, exc)

    def _require_connected(self) -> None:
        if self.ib.isConnected():
            if getattr(self, "_disconnected_since", None) is not None:
                # K5: connected while the outage is still open - this
                # session's open-orders sync had not ended (_reconnect,
                # _connect). Over once it has; until then the clock runs
                # on to the 30-min DOWN page (once). Only the connect-time
                # sync holds the outage open: a request a guarded read sent
                # after it ended is that read's business (_open_orders_refusal).
                now = time.monotonic()
                if (self._open_orders_pending()
                        and getattr(self, "_sync_pending_since", None) is not None):
                    self._maybe_outage_alert(now)
                else:
                    self._recovered(now)
            return
        # M5: the gateway dropped (e.g. its daily auto-restart) — try to
        # reconnect with backoff instead of staying wedged. Still raises
        # while down: the blend cycle FAILS CLOSED, then auto-recovers on
        # a later cycle once the gateway is back.
        self._reconnect()
        if not self.ib.isConnected():
            raise ExecutorConnectionError(
                "IB gateway disconnected — stock-order surface unavailable "
                "(blend cycle fails closed; auto-reconnect with backoff is "
                "running)")

    def _reconnect(self) -> None:
        """One backed-off reconnect attempt. Alerts only when the outage
        exceeds OUTAGE_ALERT_S (the daily gateway restart stays a
        non-event); sends a recovery notice after an alerted outage. A
        session whose open-orders sync has not ended does not end the
        outage (K5)."""
        now = time.monotonic()
        self._proven = None             # whatever happens next, the proven session is gone
        if self._disconnected_since is None:
            self._disconnected_since = now
            logger.warning("IB gateway connection lost — reconnecting with "
                           "backoff (alert only if down > %d min)",
                           int(OUTAGE_ALERT_S // 60))
            # wall clock, not monotonic: the ledger outlives this process
            self._outage("start", time.time())
        # a blocked adapter call - NOT a cycle: this guard fronts six
        # surfaces and reference_prices loops per symbol. The keepalive is
        # not a call anything was waiting on: it runs every loop iteration
        # and would only count the outage's length in iterations.
        if not getattr(self, "_in_keepalive", False):
            self._outage("blocked_call")
        if now < self._next_reconnect_ts:
            self._maybe_outage_alert(now)
            return
        try:
            try:
                self.ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            port = 4002 if self.cfg.trading_mode == "paper" else 4001
            self.ib.connect(self.cfg.ib_host, port,
                            clientId=self.cfg.ib_client_id, timeout=15)
        except Exception as exc:  # noqa: BLE001
            # from the END of the attempt: a connect that hangs for its 15 s
            # timeout used to eat the whole first backoff step
            ended = time.monotonic()
            self._sync_pending_since = None
            if getattr(self, "_open_orders_unsynced", False):
                # no session at all now: a plain outage again - and the
                # gateway watch's login-stall clock starts here, not at the
                # unsynced outage's start (a gateway restarting mid-outage is
                # not a stalled login the moment it drops)
                self._outage("mark_kind", None)
            self._open_orders_unsynced = False  # no session at all: a plain outage
            # ... and the replacement schedule starts over (D1 round 5): an
            # unsynced session that a LATER connect brings is its spell's
            # first, replaced UNSYNCED_REPLACE_WAITS x the bound after it.
            # KNOWN, NOT BUILT (D1 round 5, recorded): only a FAILED attempt
            # restarts it. A session the gateway closed (its FIN) followed by
            # a reconnect that succeeds at once keeps the spell's interval (up
            # to 15 min): a gateway-only restart already back by the attempt
            # its FIN triggers, whose first session loses its answer, is not
            # replaced in the decision's window (scripted gateway, after an
            # unsynced night: no trade). A real restart refuses connections
            # for tens of seconds (the JVM, the login), so that attempt fails
            # first and lands here (scripted with a 30 s refusal: traded
            # 161 s after decide_at). The fix would restart the schedule when
            # the GATEWAY closed the session, not this adapter. The converse
            # (D1 round 6, recorded): a gateway that refuses the reconnect
            # made right after each replacement's drop (IB's 326) restarts it
            # every time - _unsynced_replace_interval's record. The DOWN page
            # counts the sessions tried with _unsynced_sessions, not this step.
            self._unsynced_replacements = 0
            self._next_reconnect_ts = ended + self._reconnect_backoff
            self._reconnect_backoff = min(
                self._reconnect_backoff * 2,
                float(getattr(self, "reconnect_backoff_max_s",
                              RECONNECT_BACKOFF_MAX_S)))
            logger.warning("IB gateway reconnect failed (next attempt in "
                           "%.0fs): %s", self._next_reconnect_ts - ended, exc)
            self._maybe_outage_alert(now)
            return
        # IB's market-data type is PER SESSION: without this, the fresh
        # session serves live while _md_type still says delayed, and every
        # spot() wedges on the "already escalated" state - the book went
        # quote-dead again after each daily gateway restart (counter-agent
        # 2026-08-24, CRITICAL).
        self._apply_market_data_type()
        self._positions_synced = False  # a new session: its own download counts
        self._positions_failed = None
        if hasattr(self, "_order_errors"):
            self._order_errors.clear()  # order ids restart at nextValidId
        if hasattr(self, "_cancel_replies"):
            self._cancel_replies.clear()    # same: a stale 161 must label nothing
        self._outage_reconnected = True     # the outage saw a reconnect (_recovered's words)
        if self._note_connect_sync():
            # K5: connected, but this session's connect-time open-orders
            # sync did not end (IB.connect only LOGS that timeout,
            # ib.py:2077-2084), so a guarded open-orders read waits for it
            # (once per session) and then fails closed, KEEPING the session
            # for its late end (_open_orders_refusal). NOT a recovery: the
            # outage stays open (ledger with its cause, the 30-min DOWN
            # page) until the sync ends (_require_connected), a kept session
            # is replaced on the doubling schedule (_unsynced_replace_due),
            # and the next attempt waits out the backoff as after a failed one. It
            # used to count as recovered: on a gateway that never answers
            # that request every read dropped the session, every reconnect
            # "recovered", nothing paged.
            ended = time.monotonic()
            if not getattr(self, "_open_orders_unsynced", False):
                self._outage("mark_kind", KIND_OPEN_ORDERS_UNSYNCED)
            self._open_orders_unsynced = True
            self._unsynced_sessions = int(getattr(self, "_unsynced_sessions", 0) or 0) + 1
            self._next_reconnect_ts = ended + self._reconnect_backoff
            self._reconnect_backoff = min(
                self._reconnect_backoff * 2,
                float(getattr(self, "reconnect_backoff_max_s",
                              RECONNECT_BACKOFF_MAX_S)))
            logger.warning("IB gateway reconnected, but the new session's "
                           "open-orders sync did not end: still not usable "
                           "(next fresh session no sooner than %.0fs)",
                           max(self._next_reconnect_ts - ended,
                               self._unsynced_replace_interval()))
            self._maybe_outage_alert(ended)
            return
        self._recovered(now)

    def _note_connect_sync(self) -> bool:
        """K5: right after a connect, is THIS session's connect-time
        open-orders sync still unended (IB.connect only logged its timeout)?
        Recorded per session (_sync_pending_since): while it stands, the
        pending open-orders request is known to be that sync."""
        pending = self._open_orders_pending()
        self._sync_pending_since = time.monotonic() if pending else None
        self._sync_wait_failed = False
        return pending

    def _recovered(self, now: float) -> None:
        """The outage is over: a session is connected and its open-orders
        sync has ended. Recovery notice after an alerted outage, state
        resets, ledger closed. The notice says RECONNECTED only when the
        outage saw a reconnect: an unsynced outage whose late sync ended on
        the session it began on was never a reconnect (D1 round 4). Its words
        come from the outage's LAST cause (D1 round 6): an alerted unsynced
        outage now usually ends through a replacement - a reconnect - and the
        plain outage's "could not read the account" contradicted the DOWN
        page ("positions and cash are read normally"). After an unsynced one:
        the open orders were unreadable, so nothing was traded or flattened;
        the positions and the cash were read. Recorded, not built: an outage
        whose cause changed is worded by the last one only. An unsynced page
        followed by a spell with no session at all (a gateway restart that
        refused connects; a gateway that refuses each reconnect made right
        after a replacement's drop, IB's 326) ends with the plain words; a
        plain page followed by unsynced sessions ends with these."""
        unsynced = getattr(self, "_open_orders_unsynced", False)
        reconnected = getattr(self, "_outage_reconnected", False)
        self._open_orders_unsynced = False
        self._sync_pending_since = None
        self._sync_wait_failed = False
        down_s = now - self._disconnected_since
        logger.info("IB gateway %s after %.0fs (same clientId: orderIds stay "
                    "monotone, drain-once keys persist)",
                    "reconnected" if reconnected else
                    "session's open-orders sync ended", down_s)
        if self._outage_alerted:
            from .alerts import send
            if unsynced:
                meanwhile = (
                    " (open orders were unreadable, so the Composer mirror "
                    "could not trade or flatten meanwhile; positions and cash "
                    "were read; it keeps no resting stops at the venue)"
                    if getattr(self, "mirror_only", False) else
                    " (open orders were unreadable, so cycles were failing "
                    "closed meanwhile; positions and cash were read; GTC stops "
                    "rested at the venue throughout)")
                if reconnected:
                    send(f"🧬 IB gateway RECONNECTED after {down_s / 60:.0f} "
                         f"min — executor resumed" + meanwhile)
                else:
                    send(f"🧬 IB gateway open orders READABLE again after "
                         f"{down_s / 60:.0f} min — the session's late "
                         f"open-orders sync ended (no reconnect was needed): "
                         f"executor resumed" + meanwhile)
            elif getattr(self, "mirror_only", False):
                send(f"🧬 IB gateway RECONNECTED after {down_s / 60:.0f} min — "
                     f"executor resumed (the Composer mirror could not read "
                     f"the account or trade meanwhile; it keeps no resting "
                     f"stops at the venue)")
            else:
                send(f"🧬 IB gateway RECONNECTED after {down_s / 60:.0f} min — "
                     f"executor resumed (cycles were failing closed meanwhile; "
                     f"GTC stops rested at the venue throughout)")
        # State resets come FIRST. Closing the ledger before them meant a
        # raise inside end() left the adapter permanently believing it was
        # mid-outage while actually connected - the next real drop would then
        # skip the outage start and fire a spurious DOWN alert with a bogus
        # multi-hour duration (counter-agent 2026-08-24, CRITICAL).
        self._disconnected_since = None
        self._outage_alerted = False
        self._outage_reconnected = False
        self._unsynced_replacements = 0     # the next unsynced outage's schedule starts over
        self._unsynced_sessions = 0         # ... and its count of the sessions tried
        self._reconnect_backoff = RECONNECT_BACKOFF_S
        self._next_reconnect_ts = 0.0
        self._outage("end", time.time())

    def _maybe_outage_alert(self, now: float) -> None:
        if (self._outage_alerted or self._disconnected_since is None
                or now - self._disconnected_since <= OUTAGE_ALERT_S):
            return
        self._outage_alerted = True
        self._outage("mark_alerted")
        from .alerts import send
        if getattr(self, "_open_orders_unsynced", False):
            # K5: the gateway is up and logged in, so say what is true of it
            # (D1 round 4): the positions and the cash ARE read; it is the
            # open orders that are not, so nothing can be sold or bought.
            # The service's gateway watch skips its login-stall diagnosis
            # for this cause (the ledger's kind): this page is the one page.
            # The fresh sessions tried are every session this outage found
            # unsynced but the first (D1 round 6: the schedule's own step
            # restarts at a failed connect and skips a session a gateway FIN
            # brought, so the page under-counted - it said none was tried when
            # each reconnect after a replacement was refused once).
            n = max(int(getattr(self, "_unsynced_sessions", 0) or 0) - 1, 0)
            tried = ""
            if n:
                tried = (" A fresh gateway session was already tried and its "
                         "sync did not end either;" if n == 1 else
                         f" {n} fresh gateway sessions were already tried and "
                         f"none synced;")
                tried += (f" another is tried after a wait that doubles each "
                          f"time, up to {UNSYNCED_REPLACE_MAX_S / 60:.0f} min, "
                          f"until one syncs.")
            why = (f" CAUSE: the gateway connects and answers, but the "
                   f"open-orders request each new session sends at connect goes "
                   f"unanswered, so no open-orders read can be trusted and "
                   f"nothing is sold or bought.{tried} Restart the gateway "
                   f"(Render → ibkr-executor → Restart service, then approve "
                   f"the IBKR push).")
            if getattr(self, "mirror_only", False):
                send(f"🚨 IB gateway DOWN for over {int(OUTAGE_ALERT_S // 60)} "
                     f"min for trading — logged in, but the Composer mirror "
                     f"cannot trade: open orders unreadable (positions and cash "
                     f"are read normally). It keeps NO resting stops at the "
                     f"venue: the positions stay as they are, and if this lasts "
                     f"to the decision, 6 minutes before the close, that session "
                     f"will NOT trade; a /kill flatten cannot sell either." + why)
                return
            send(f"🚨 IB gateway DOWN for over {int(OUTAGE_ALERT_S // 60)} min "
                 f"for trading — logged in, but the executor cannot trade: open "
                 f"orders unreadable (positions and cash are read normally); "
                 f"cycles fail closed (no entries/exits/stop ratchets), GTC "
                 f"stops still rest at the venue." + why)
            return
        if getattr(self, "mirror_only", False):
            send(f"🚨 IB gateway DOWN for over {int(OUTAGE_ALERT_S // 60)} min "
                 f"— the Composer mirror cannot read the account or trade. "
                 f"It keeps NO resting stops at the venue: the positions stay "
                 f"as they are, and if the gateway is still down at the "
                 f"decision, 6 minutes before the close, that session will NOT "
                 f"trade; a /kill flatten waits for the gateway too. "
                 f"Auto-reconnect keeps retrying "
                 f"with backoff; check the gateway container if this persists")
            return
        send(f"🚨 IB gateway DOWN for over {int(OUTAGE_ALERT_S // 60)} min "
             f"— executor is failing closed (no entries/exits/stop "
             f"ratchets); GTC stops still rest at the venue. Auto-reconnect "
             f"keeps retrying with backoff; check the gateway container if "
             f"this persists")

    def _pump(self) -> None:
        """Process pending gateway messages (ib_async sync facade)."""
        self.ib.sleep(0)

    def _recv_bytes(self) -> int | None:
        """Bytes this session has received so far; None when that cannot be
        told (not connected, or a client without the counter)."""
        try:
            return int(self.ib.client.connectionStats().numBytesRecv)
        except Exception:  # noqa: BLE001
            return None

    def _drain(self) -> None:
        """Pump until nothing more is waiting on the socket, so that a
        connection that died while nobody pumped is SEEN dead before anything
        is read from the session's caches.

        ib_async 2.1 (verified in its source and against a socket): the sync
        facade runs the event loop only inside ib.sleep()/a request, so
        IB.isConnected() stays True and positions()/accountValues() keep the
        dead session's values until the loop runs; the close is processed in
        stream order, AFTER whatever the gateway sent before it, and one
        ib.sleep(0) reads a bounded amount - behind a backlog of a few
        hundred kB (a night of account updates) the first pump leaves the
        session looking connected with its old caches (2026-11-12: the
        mirror's position check passed on them). The pump that does process
        the close can itself raise ConnectionError("Socket disconnect").
        Does not detect a connection that is silently half-open (no FIN, no
        RST): nothing arrives on one, so only a request can."""
        deadline = time.monotonic() + DRAIN_MAX_S
        while True:
            before = self._recv_bytes()
            try:
                self._pump()
            except Exception as exc:  # noqa: BLE001
                if self.ib.isConnected():
                    raise
                logger.warning("IB gateway connection found closed while "
                               "pumping: %s", exc)
                return
            if not self.ib.isConnected():
                return
            after = self._recv_bytes()
            if before is None or after is None or after == before:
                return
            if time.monotonic() >= deadline:
                raise ExecutorNotSyncedError(
                    f"IB gateway backlog still being read after "
                    f"{DRAIN_MAX_S:.0f}s - nothing is read from the session "
                    f"behind it (retried on the next call)")

    def _require_live(self) -> None:
        """Pump FIRST, then require connected (reconnecting through
        _reconnect's backoff): the gate of every surface the Composer mirror
        reads or trades through. _require_connected alone trusts
        isConnected(), which is stale until the loop is pumped."""
        self._drain()
        self._require_connected()

    def prove_live(self, timeout: float = PROVE_LIVE_TIMEOUT_S) -> None:
        """A bounded liveness ROUND TRIP. _require_live only listens: on a
        connection that died without a FIN (a host that vanished, a dropped
        NAT mapping, a gateway that stopped answering) nothing arrives, the
        session keeps reading "connected" and its caches keep the last
        values it was sent. Only an answered request proves the session.

        ib_async 2.1.0: IB.reqCurrentTime (ib.py:865-871) is
        _run(reqCurrentTimeAsync()); _run passes IB.RequestTimeout to
        util.run (ib.py:427-428), which wraps the request in asyncio.wait_for
        when the timeout is non-zero (util.py:350-351) and lets its
        TimeoutError out of run_until_complete (util.py:359-360). The request
        is one message (client.py:912-913: send(49, 1)); the answer ends the
        "currentTime" future (wrapper.py:1515-1517). A socket found closed
        meanwhile fails that future with ConnectionError("Socket disconnect")
        (wrapper.py:361-365).

        No answer in time, or any error: the session is treated as dead -
        disconnected, then the existing reconnect path (backoff, outage
        ledger, alerts). Returns on a proven or a freshly connected session
        (the connect handshake is itself a round trip); raises
        ExecutorConnectionError while the gateway cannot be reached. Called
        where a stale read would be acted on (the keepalive, the mirror's
        pre-trade account gate, a flatten round) - not on every surface.

        FRESH (K3b): the mirror's account gate proves the session and the
        service loop's keepalive proves it again a few ms later. A gateway
        that ignores a reqCurrentTime sent within about a second of the one
        before (ib_insync #479, TWS 10.16.1f) would turn every such pair into
        a 5 s stall and the disconnect of a healthy session. So once the
        drain above has run (a FIN or an RST is still seen at every call), a
        session that THIS connection proved less than PROVE_FRESH_S ago is
        not asked again. The record is (monotonic time, _connection()) of the
        last answered request; it is cleared before every request (a request
        that fails leaves none) and by every reconnect (_reconnect), and
        another connection never matches it."""
        self._require_live()
        proven, conn = getattr(self, "_proven", None), self._connection()
        if (proven is not None and conn is not None and proven[1] is conn
                and 0.0 <= time.monotonic() - proven[0] < PROVE_FRESH_S):
            return
        self._proven = None
        prev = getattr(self.ib, "RequestTimeout", 0)
        try:
            self.ib.RequestTimeout = timeout
            self.ib.reqCurrentTime()
            conn = self._connection()
            self._proven = (time.monotonic(), conn) if conn is not None else None
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("IB gateway session did not answer a liveness "
                           "request within %.0fs (%s: %s) - treated as dead: "
                           "disconnecting and reconnecting", timeout,
                           type(exc).__name__, exc)
        finally:
            self.ib.RequestTimeout = prev
        try:
            self.ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self._positions_synced = False
        self._require_connected()

    def _connection(self):
        """The object that is THIS gateway connection's and no other's, or
        None. ib_async 2.1.0: client.conn is ONE Connection for the client's
        whole life (client.py:103) and is reused by every connect
        (client.py:216), so it says nothing about the session; its
        `transport` is the asyncio transport of the current TCP connection:
        made by each connect (connection.py:38, loop.create_connection), set
        to None by Connection.reset() at the start of every connect
        (connection.py:25-26, 35) and by connection_lost (connection.py:62-63).
        A reconnect therefore always brings a different object, and the
        reference _proven keeps holds the old one alive, so `is` can never
        take one for the other. A client without it (a test double): None,
        and such a session is never taken as proven."""
        try:
            return self.ib.client.conn.transport
        except Exception:  # noqa: BLE001
            return None

    def keepalive(self) -> bool:
        """Cheap liveness pass for the service loop when nothing else touches
        the adapter (the mirror alone trades once a day): notices an
        overnight drop and reconnects through the same backoff, outage
        ledger and alerts as any other surface. One prove_live: a round
        trip, or none when the session was proven less than PROVE_FRESH_S
        ago (the mirror's own gate, a moment before). Never raises; False
        while the gateway is unreachable.

        K5 (D1 rounds 4-5): a session whose connect-time open-orders sync
        has not ended is replaced when the replacement schedule says it is old
        enough and the backoff allows (_unsynced_replace_due) - a one-off lost
        answer is then cured overnight, before any page, instead of at the
        decision's first read, and a gateway whose answers come back without
        a restart is found by the next fresh session. A healthy session never
        reaches that step."""
        self._in_keepalive = True
        try:
            if getattr(self, "_sync_pending_since", None) is not None:
                self._replace_unsynced_session()
            self.prove_live()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("IB keepalive: %s", exc)
            return False
        finally:
            self._in_keepalive = False

    def _unsynced_replace_due(self) -> bool:
        """K5 (D1 rounds 4-5): is the current session - its connect-time
        open-orders sync unended - due to be replaced by a fresh one? When
        that sync has been unended for the schedule's current interval
        (_unsynced_replace_interval, counted from when the connect gave up on
        it) and the reconnect backoff allows an attempt now. Taken by
        whichever call meets it first: the keepalive (an idle night) or a
        guarded read that must refuse (a decision, a /kill flatten, a blend
        cycle).

        Why a schedule. The outage stays open across a replacement
        (_reconnect's K5 branch), so a fresh session that syncs ends it - no
        DOWN page, no wait at the decision - while one whose sync does not end
        either is KEPT for its late end until the next replacement is due.
        Round 4 replaced once per outage: when that fresh session lost its
        answer too (a gateway still warming up after its nightly restart, a
        spell of unanswered syncs that cleared with no FIN), it was kept for
        as long as it lived and every guarded read failed - the mirror did
        not trade and a /kill flatten could not sell - where one more fresh
        session would have synced. The doubling keeps a gateway that never
        answers that request free of churn (each connect blocks the loop
        thread for its 15 s sync wait): two replacements are never closer
        together than the current interval, since each is counted from the
        connect of the session it replaces, which came after the one before.
        The schedule starts over when the outage has no session at all
        (_reconnect's failure branch) and when the outage ends (_recovered)."""
        since = getattr(self, "_sync_pending_since", None)
        if since is None or getattr(self, "_disconnected_since", None) is None:
            return False
        now = time.monotonic()
        return (now - since >= self._unsynced_replace_interval()
                and now >= getattr(self, "_next_reconnect_ts", 0.0))

    def _unsynced_replace_interval(self) -> float:
        """K5 (D1 round 5): how long the current session's connect-time sync
        may stay unended, from when the connect gave up on it, before the
        session is replaced: UNSYNCED_REPLACE_WAITS x VENUE_HISTORY_TIMEOUT_S
        for the spell's first replacement (40 s), twice the previous interval
        for each later one (80, 160, 320, 640 s), never more than
        UNSYNCED_REPLACE_MAX_S (15 min).

        KNOWN, NOT BUILT (D1 round 6, recorded; measured on the simulated
        clock and on scripted gateways, never on a real IB gateway):
        - LATE versus LOST. Both are an unended sync, and the adapter cannot
          tell them apart before it drops the session; the schedule takes
          the answer as lost, the failure actually observed (round 4 waited
          for a late one by keeping its second session for good, and when
          that session's answer was lost too nothing traded). Cost: a gateway
          that answers EVERY new session's connect-time open-orders request
          a fixed time late, after a drop at the decision (15:54:20): up to
          ~95 s late it trades as round 4 did (the same sessions, the same
          instants); ~95-125 s late it trades ~95 s later, close to the
          cancel instant (buys as late as 15:58:59); ~125-220 s late it does
          not trade (round 4 kept session 2, its late end landed and it
          traded); later than that neither does. The simulated clock's edges:
          122/123 and 215/220 s with the loop parked until decide_at, 128/129
          and 220/225 s with it ticking at the drop. Overnight, more than ~15
          min late never ends the outage (66 replacements by the next
          decision, one DOWN page, that decision not traded; round 4 kept its
          second session, closed the outage when the late end landed and
          traded). A design that keeps both (probe a new session on a second
          clientId before dropping the kept one) is not built. Pinned:
          tests/test_mirror_d1r6.py part P.
        - A failed connect restarts the schedule (_reconnect). If a real
          gateway refuses an immediate same-clientId reconnect (IB error
          326), the interval never doubles past 40 s: measured ~12 connect
          attempts and 6 sessions an hour idle (one attempt per 300 s
          keepalive), ~72 attempts and 36 sessions an hour during a /kill
          flatten, bounded by the reconnect backoff (30 s; 45 s between
          attempts at the least, with a refused connect modelled as waiting
          out its 15 s) - no storm, though the DOWN page's "doubles each
          time" is then not what happens. Its count of the sessions tried
          stays true (_unsynced_sessions).
        - The cap's cost. After a spell long enough to reach 900 s, a
          gateway that heals with no FIN is found up to ~15 min later. Three
          lost answers met at the decision do not trade (the 4th session is
          due ~325 s after decide_at, past the cancel instant); a /kill
          flatten sells after ~322 s with three lost, ~658 s with four.
        - A gateway-only restart that accepts at once keeps the interval:
          the schedule does not restart on a gateway FIN (_reconnect's
          record).
        - Considered, not built: the first step (40 s) inside the decision
          window and during a flatten (it costs the late band from ~55 s:
          every answer later than that is replaced before it lands); a reset
          on a gateway FIN; a ~1 s pause between a replacement's drop and
          its reconnect.
        - Pre-existing (mirror.py _summary/_finish): a session lost to an
          outage inside the window ends with an info-level "traded" summary
          (sold 0/N ...); the loud lines are the per-order red "NOT sent"
          alerts."""
        first = UNSYNCED_REPLACE_WAITS * VENUE_HISTORY_TIMEOUT_S
        n = max(int(getattr(self, "_unsynced_replacements", 0) or 0), 0)
        return min(first * 2.0 ** min(n, 32), max(UNSYNCED_REPLACE_MAX_S, first))

    def _replace_unsynced_session(self) -> None:
        """K5 (D1 rounds 4-5), the keepalive's half of _unsynced_replace_due:
        drop the session so that prove_live's reconnect tries a FRESH one.
        The socket is drained first: a late end already waiting in it means
        the sync HAS ended (prove_live's _require_connected then ends the
        outage) and nothing is replaced."""
        if not self._unsynced_replace_due() or not self.ib.isConnected():
            return
        self._drain()
        if not self.ib.isConnected() or not self._open_orders_pending():
            return
        self._spend_unsynced_replacement()

    def _spend_unsynced_replacement(self) -> None:
        """One step of the replacement schedule: count it (the next interval
        doubles) and drop the session; the caller's next venue call
        reconnects through _reconnect, whose backoff _unsynced_replace_due
        has already found clear."""
        waited = time.monotonic() - (self._sync_pending_since or 0.0)
        self._unsynced_replacements = int(getattr(self, "_unsynced_replacements", 0) or 0) + 1
        logger.warning("IB gateway session's open-orders sync has not ended "
                       "%.0fs after the connect: fresh session %d of this "
                       "unsynced outage is tried (if its sync does not end "
                       "either, it is replaced %.0fs after its connect; the "
                       "outage stays open until a session syncs)", waited,
                       max(int(getattr(self, "_unsynced_sessions", 0) or 0), 1),
                       self._unsynced_replace_interval())
        self._drop_session()

    def _positions_pending(self) -> bool | None:
        """Has this session's connect-time position download NOT ended?
        None when it cannot be told. ib_async 2.1: IB.connectAsync starts
        reqPositionsAsync (wrapper.startReq("positions")) and waits for it
        with a timeout it only LOGS; wrapper.positionEnd pops the request
        (_endReq), so the key is present exactly while positionEnd has not
        arrived."""
        try:
            return "positions" in self.ib.wrapper._futures
        except Exception:  # noqa: BLE001
            return None

    def _session_positions(self) -> list:
        """ib.positions() of THIS gateway session, once its position download
        is known to have ended. IB.connect() returns "connected" even when
        the download timed out, and an account that reads EMPTY for that
        reason cannot be told from a flat one: the download is then asked for
        once more, bounded, and a session that still has not delivered it
        RAISES (never an empty or a cached list)."""
        if not getattr(self, "_positions_synced", False):
            if self._positions_pending() is not False:
                # a download that just timed out is not asked for again at
                # once: every read would block the loop thread a fresh
                # POSITIONS_SYNC_TIMEOUT_S (a decision retries its gate, a
                # flatten its round). The failure stands for a short while.
                failed = getattr(self, "_positions_failed", None)
                if failed and 0 <= time.monotonic() - failed[0] < POSITIONS_FAIL_MEMO_S:
                    raise ExecutorNotSyncedError(
                        f"the account's positions are not yet synced on this "
                        f"gateway session ({failed[1]}; asked again "
                        f"{POSITIONS_FAIL_MEMO_S:.0f}s after that failure)")
                prev = getattr(self.ib, "RequestTimeout", 0)
                try:
                    self.ib.RequestTimeout = POSITIONS_SYNC_TIMEOUT_S
                    self.ib.reqPositions()
                except Exception as exc:  # noqa: BLE001
                    self._positions_failed = (
                        time.monotonic(), f"{type(exc).__name__}: {exc}")
                    raise ExecutorNotSyncedError(
                        f"the account's positions are not yet synced on this "
                        f"gateway session ({type(exc).__name__}: {exc})"
                    ) from exc
                finally:
                    self.ib.RequestTimeout = prev
            self._positions_failed = None
            self._positions_synced = True
        return list(self.ib.positions())

    def _stock_contract(self, symbol: str):
        c = self._stock_contracts.get(symbol)
        if c is None:
            from ib_async import Stock
            qualified = self.ib.qualifyContracts(
                Stock(symbol, STOCK_EXCHANGE, STOCK_CURRENCY))
            if not qualified:
                raise RuntimeError(f"cannot qualify stock contract {symbol}")
            c = qualified[0]
            self._stock_contracts[symbol] = c
        return c

    def _open_orders_pending(self) -> bool:
        """Is an open-orders request of this session unanswered right now
        (no wait)? The key stays in wrapper._futures until an openOrderEnd
        pops it (wrapper.py:384-395, 719-720) or the session is reset; a
        request that timed out leaves it there, its future cancelled."""
        futures = getattr(getattr(self.ib, "wrapper", None), "_futures", None)
        return isinstance(futures, dict) and "openOrders" in futures

    def _open_orders_unanswered(self) -> str | None:
        """K4: is an earlier open-orders request still unanswered on this
        session? ib_async keys EVERY open-orders request "openOrders"
        (ib.py:2263-2271), a new request replaces a pending one
        (wrapper.py:370-377), and openOrderEnd carries no request id
        (decoder.py:85), so it ends whichever request is current
        (wrapper.py:384-395, 719-720). While an earlier request is
        unanswered - the connect-time sync's (a timeout there is only
        logged, ib.py:2077-2082) or one that timed out and kept the session
        (order_absent_today) - ITS late end would end a new request with a
        partial list, and a partial "open orders" answer reads a working
        order as gone: a resting SELL undercounted (a short), or an order
        called absent and placed again. No such request = an honest answer.

        PROTOCOL ASSUMPTION the whole argument rests on (IB's documented
        behaviour; NOT verified against a live gateway - every test here runs
        on scripted ones): the gateway sends exactly ONE openOrderEnd per
        open-orders request, after that request's rows. An unsolicited
        openOrderEnd arriving inside a later request's answer would end it
        early with a partial list, and ib_async 2.1 offers no client-side
        defence (the message carries no request id). K4 had the same
        exposure; nothing here widens it.

        K5: a pending one is first WAITED for, pumping, at most
        VENUE_HISTORY_TIMEOUT_S per read: once its own end has arrived (the
        key popped) no late end can follow - every request site refuses to
        start one while the key is there, so at most one is ever
        outstanding - and the new request is honest. Without the wait a
        gateway that answers the connect-time request late on every session
        had every read drop the session, and the mirror never traded.
        Nothing pending (a normal day): no wait, no pump - one dict lookup.
        A session's connect-time sync is waited for in FULL once per session
        (D1 round 4): once one read has waited the whole bound for it, a
        later read on the same session fails at once while it is still
        pending (_require_live has drained the socket first, so an end that
        has arrived is seen), instead of blocking the loop thread another
        VENUE_HISTORY_TIMEOUT_S on every guarded read for as long as the
        session lasts.

        Returns None when nothing is pending (send the request), else why
        the read must fail closed - what _open_orders_refusal acts on:
          "sync"    this session's connect-time sync (_sync_pending_since)
          "request" an earlier request of this session's own guarded reads
                    (order_absent_today's timed-out one), or one this adapter
                    did not see start (a session it did not connect itself)
          "closed"  the session closed during the wait: nothing answered here

        KNOWN, NOT BUILT (D1 round 4, recorded): a gateway that answers the
        connect-time request but never a LATER reqAllOpenOrders makes every
        read time out and drop the session, and every reconnect counts as
        recovered - the outage never lasts, so no DOWN page (the mirror's
        red alerts still quote "restart the gateway if this persists"). The
        fix would track answered open-orders requests across sessions."""
        if not self._open_orders_pending():
            self._sync_pending_since = None     # if it was the sync, it has ended
            return None
        sync = getattr(self, "_sync_pending_since", None) is not None
        if sync and getattr(self, "_sync_wait_failed", False):
            return "sync"                       # waited for in full once on this session already
        deadline = time.monotonic() + VENUE_HISTORY_TIMEOUT_S
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                if sync:
                    self._sync_wait_failed = True
                return "sync" if sync else "request"
            try:
                self.ib.sleep(min(WAIT_TICK_S, left))
            except Exception:  # noqa: BLE001
                return "closed"     # the pump that met the close (_drain): nothing answered here
            if not self.ib.isConnected():
                return "closed"
            if not self._open_orders_pending():
                self._sync_pending_since = None
                return None

    def _open_orders_refusal(self, why: str) -> str:
        """K5 (D1 rounds 4-5): what a guarded read that must NOT send its
        open-orders request (_open_orders_unanswered said why) does with the
        session, and the text it fails closed with.
          "request": DROPPED, so the next read runs on a fresh session (that
                     request's late end can never reach a new one).
          "sync":    KEPT. Its late end can still land (a gateway answering
                     every session's sync 45 s late now trades), and a drop
                     on every read cannot help when every new session sends
                     the same request - except when the replacement schedule
                     says it is due (_unsynced_replace_due): the read then
                     takes the replacement itself, so a decision or a /kill
                     flatten that meets a lost answer recovers in-process.
          "closed":  nothing to drop; the next call reconnects.
        K4 is untouched either way: nothing is sent while a request is
        pending, and a drop resets the wrapper's requests (ib.py:405-406)."""
        if why == "request":
            self._drop_session()
            return (f"an earlier open-orders request is still unanswered after "
                    f"a {VENUE_HISTORY_TIMEOUT_S:.0f}s wait: the session is "
                    f"dropped and reconnected (restart the gateway if this "
                    f"persists)")
        # each text fits the 160 characters the mirror's red alert quotes of
        # it (mirror.one_line(exc, 160)): the remedy must not be cut off
        if why == "sync":
            if self._unsynced_replace_due():
                self._spend_unsynced_replacement()
                return ("this session's connect-time open-orders sync is still "
                        "unanswered: nothing is read, and a fresh session is "
                        "tried (restart the gateway if this persists)")
            return ("this session's connect-time open-orders sync is still "
                    "unanswered: nothing read, session kept for its late answer "
                    "(restart the gateway if this persists)")
        return ("the IB gateway session closed while this read waited for an "
                "earlier open-orders request: nothing was read (the next call "
                "reconnects)")

    def _drop_session(self) -> None:
        """Disconnect so the next surface reconnects on a fresh session
        (ib_async's disconnect resets the wrapper's requests and caches,
        ib.py:405-406)."""
        self._proven = None
        self._sync_pending_since = None
        self._sync_wait_failed = False
        try:
            self.ib.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _all_trades(self, refresh: bool = False) -> list:
        """This session's trades; refresh=True additionally asks the venue
        for open + completed orders (covers orders placed in a previous
        session that the connect-time sync missed)."""
        trades = list(self.ib.trades())
        if refresh:
            why = self._open_orders_unanswered()
            if why:
                raise ExecutorConnectionError(self._open_orders_refusal(why))
            # the wait above may have pumped: a late sync can have delivered
            # one of OUR earlier orders, which may have filled since and so be
            # in neither answer below - the dedupe must still see it
            # (place_stock_order: a second SELL of the same shares is a short)
            trades = list(self.ib.trades())
            seen = {(t.order.orderId, getattr(t.order, "permId", 0))
                    for t in trades}
            # BOUNDED (2026-09-08): RequestTimeout=0 waits forever, and a
            # gateway that never sends completedOrdersEnd wedged the loop
            # thread for good. A timeout is NOT "no extra orders" - treating
            # it so would let a reconcile clear a journal the venue may
            # still hold and re-place the order. It fails the cycle CLOSED.
            prev = getattr(self.ib, "RequestTimeout", 0)
            self._completed_orders_unavailable = False
            try:
                self.ib.RequestTimeout = VENUE_HISTORY_TIMEOUT_S
                # OPEN orders are REQUIRED: "is it still working?" has no
                # other source. COMPLETED orders are best effort: on
                # 2026-09-08 this gateway never answered reqCompletedOrders
                # on ANY session (every cycle reconnected, timed out, failed
                # closed - the book frozen for hours), so "did it fill?" is
                # answered from the venue's EXECUTION reports instead (see
                # find_stock_order), which the connect-time sync already
                # delivers and reqExecutions refreshes reliably.
                # KNOWN, NOT BUILT (D1 round 4, recorded): completed orders
                # share K4's key hazard - ib_async keys every such request
                # "completedOrders" (ib.py:2273-2276) and completedOrdersEnd
                # carries no request id (wrapper.py:727-733), so a timed-out
                # connect-time reqCompletedOrders answering late could end
                # this one with the connect-time list while history_complete()
                # still reads True. Its weak link: an order that completed
                # after the connect and that this session does not know.
                # The fix would be the K4/K5 pending check on that key.
                for fn, args, required in (("reqAllOpenOrders", (), True),
                                           ("reqCompletedOrders", (False,), False)):
                    try:
                        extra = getattr(self.ib, fn)(*args) or []
                    except (TimeoutError, asyncio.TimeoutError) as exc:
                        # (aliases on 3.11+, distinct classes on 3.10: both,
                        # or an older base image reads a timeout as "venue
                        # never saw it" - counter-agent MED)
                        if not required:
                            self._completed_orders_unavailable = True
                            logger.warning("%s timed out after %.0fs: falling "
                                           "back to execution reports", fn,
                                           VENUE_HISTORY_TIMEOUT_S)
                            continue
                        # Drop the session: the next _require_connected runs
                        # _reconnect (backoff, outage ledger, the 30-min page,
                        # the pre-open page) and a fresh wrapper - a wedged-
                        # but-connected gateway is otherwise invisible: the
                        # cycle would fail closed every 5 min with /health
                        # "ok" and nobody told (counter-agent MED).
                        try:
                            self.ib.disconnect()
                        except Exception:  # noqa: BLE001
                            pass
                        raise ExecutorConnectionError(
                            f"{fn} timed out after {VENUE_HISTORY_TIMEOUT_S:.0f}s: "
                            f"venue order history unavailable - cycle fails "
                            f"closed (restart the gateway if this persists)"
                        ) from exc
                    except ConnectionError as exc:
                        if required:
                            # D1 round 4 (NOTE 6): the session died while the
                            # REQUIRED request was in flight ("Socket
                            # disconnect", wrapper.py:361-365; "Not
                            # connected", client.py:250-251). It used to be
                            # logged at debug and skipped, so the caller got
                            # this session's cached trades WITHOUT the venue's
                            # list: cancel_stock_order could then answer "not
                            # found" (False) for an order still resting. The
                            # same exception as a timeout or _require_live's;
                            # every caller already handles it from this call.
                            raise ExecutorConnectionError(
                                f"{fn} failed: the IB gateway session closed "
                                f"while it was in flight ({exc}): venue order "
                                f"history unavailable (the next call "
                                f"reconnects)") from exc
                        logger.debug("%s failed: %s", fn, exc)
                        self._completed_orders_unavailable = True
                        continue
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("%s failed: %s", fn, exc)
                        if not required:
                            self._completed_orders_unavailable = True
                        continue
                    for t in extra:
                        key = (t.order.orderId, getattr(t.order, "permId", 0))
                        if key not in seen:
                            seen.add(key)
                            trades.append(t)
            finally:
                self.ib.RequestTimeout = prev
        return trades

    def _result_from_executions(self, client_order_id: str) -> dict | None:
        """'Did this orderRef fill?' from the venue's execution reports -
        the fallback when reqCompletedOrders is unanswered (2026-09-08).
        The session's fills (synced at connect) plus a bounded
        reqExecutions refresh; a refresh timeout FAILS CLOSED (never 'no
        fills'). None when no execution carries the ref."""
        fills = self._executions_refreshed()
        by_id: dict = {}
        for f in fills:
            ex = getattr(f, "execution", None)
            if ex is None or (getattr(ex, "orderRef", "") or "") != client_order_id:
                continue
            by_id[getattr(ex, "execId", "") or id(f)] = f
        if not by_id:
            return None
        # one orderRef can span a rejected-then-retried attempt: the LATEST
        # orderId is the order that binds (counter-agent LOW)
        latest = max(getattr(f.execution, "orderId", 0) for f in by_id.values())
        fs = _current_fills([f for f in by_id.values()     # a correction counts once
                             if getattr(f.execution, "orderId", 0) == latest])
        trade = type("_Synth", (), {})()
        trade.fills = fs
        trade.order = type("_O", (), {})()
        trade.order.orderId = latest
        px = _agg_fill_price(trade)
        out = {"order_ref": str(latest), "status": "filled",
               # the executions cannot prove completeness: the consumer
               # books filled_qty, never its journaled qty (counter-agent HIGH)
               "filled_qty": int(sum(int(f.execution.shares) for f in fs)),
               "source": "executions"}
        if px is not None:
            out["fill_price"] = float(px)
        if _commission_reported(trade):
            c = _agg_commission(trade)
            if c is not None:
                out["commission"] = c
        logger.warning("order %s resolved from execution reports (completed "
                       "orders unavailable): %s", client_order_id, out)
        return out

    def _executions_refreshed(self) -> list:
        """The wrapper's fill store after a bounded reqExecutions refresh.
        The store is keyed by execId and commission-patched in place; the
        request's own return value is NOT used - ib_async appends a fresh
        Fill with an EMPTY CommissionReport for an already-known execId,
        which would have overwritten the reported commission
        (counter-agent MED). A timeout fails CLOSED."""
        prev = getattr(self.ib, "RequestTimeout", 0)
        try:
            self.ib.RequestTimeout = VENUE_HISTORY_TIMEOUT_S
            try:
                self.ib.reqExecutions()
            except (TimeoutError, asyncio.TimeoutError) as exc:
                try:
                    self.ib.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                raise ExecutorConnectionError(
                    f"reqExecutions timed out after {VENUE_HISTORY_TIMEOUT_S:.0f}s "
                    f"with completed orders also unavailable - cycle fails "
                    f"closed (restart the gateway if this persists)") from exc
            except Exception as exc:  # noqa: BLE001
                logger.debug("reqExecutions failed: %s", exc)
        finally:
            self.ib.RequestTimeout = prev
        return list(getattr(self.ib, "fills", lambda: [])() or [])

    def history_complete(self) -> bool:
        """False after a refresh in which the venue's completed-order
        history was unavailable: a journal older than today that the
        session does not know then CANNOT be proven never-filled (today's
        executions do not cover yesterday) - the reconcile leaves it
        pending instead of clearing it (counter-agent MED)."""
        return not getattr(self, "_completed_orders_unavailable", False)

    def _executed_order_ids(self) -> set:
        out = set()
        for f in self._executions_refreshed():
            ex = getattr(f, "execution", None)
            if ex is None:
                continue
            for k in (getattr(ex, "orderId", None), getattr(ex, "permId", None)):
                if k:
                    out.add(str(k))
        return out

    def _find_trade_by_ref(self, order_ref: str, refresh: bool = False):
        ref = str(order_ref)
        for t in self._all_trades(refresh):
            if str(t.order.orderId) == ref:
                return t
            perm = getattr(t.order, "permId", 0)
            if perm and str(perm) == ref:
                return t
        return None

    def _find_trade_by_client_id(self, client_order_id: str,
                                 refresh: bool = False):
        """Latest, most-alive trade carrying this orderRef (idempotency key):
        filled > working > cancelled — the dedupe/journal passes care about
        the order that still binds, not a dead earlier attempt."""
        rank = {"cancelled": 0, "working": 1, "filled": 2}
        best = None
        for t in self._all_trades(refresh):
            if (getattr(t.order, "orderRef", "") or "") != client_order_id:
                continue
            if (best is None or rank[_map_status(t.orderStatus.status)]
                    >= rank[_map_status(best.orderStatus.status)]):
                best = t
        return best

    def _trade_result(self, trade) -> dict:
        out = {"order_ref": _order_ref(trade),
               "status": _map_status(trade.orderStatus.status)}
        if out["status"] == "cancelled":
            # Surface the venue's reason on the reconcile path too (the
            # async MOO/OPG outcome is only ever read from here).
            why = _trade_errors(trade, dead=True, venue=self._venue_error(trade))
            reply = self._cancel_reply(trade)
            out["reason"] = why or (
                f"IBKR gave no rejection reason (its {reply.split(']')[0]}] "
                f"reply to the executor's cancel: the order was normally "
                f"already final)"
                if reply else "no venue reason recorded")
            # ... and any EXECUTIONS the cancelled order carries (a partial
            # fill before the cancel): the caller must not treat "cancelled"
            # as "nothing happened" (round 19 review, CASH-3).
            try:
                filled = int(getattr(trade.orderStatus, "filled", 0) or 0)
            except (TypeError, ValueError):
                filled = 0
            if filled > 0:
                out["filled_qty"] = filled
        if out["status"] == "filled":
            px = _agg_fill_price(trade)
            if px is not None:              # unknown price -> NO key, never 0.0
                out["fill_price"] = float(px)
            # commission: present only when the venue has reported it; an
            # absent key is booked as 0 LOUDLY by the ledger (never silently)
            if _commission_reported(trade):
                c = _agg_commission(trade)
                if c is not None:
                    out["commission"] = c
        return out

    def _await_placement(self, trade, order_type: str) -> None:
        """Bounded post-placement wait: surfaces rejections as exceptions
        (the stop-retry/STOP_MISSING paths need them), gives MKT one bounded
        chance at a synchronous fill, and NEVER blocks waiting for MOO/OPG.
        A missing ack past PLACE_ACK_TIMEOUT_S raises — the deterministic
        client_order_id makes the caller's retry idempotent (venue-side
        dedupe by orderRef adopts the order if it did land)."""
        ack_deadline = time.monotonic() + PLACE_ACK_TIMEOUT_S
        fill_deadline = (time.monotonic() + MKT_FILL_WAIT_S
                         if order_type in ("MKT", "LMT") else None)
        while True:
            self._pump()
            s = trade.orderStatus.status
            if s == "Filled":
                # give IB's commissionReport a bounded moment to land so the
                # ledger books the real commission, not 0.0
                cdead = time.monotonic() + COMMISSION_WAIT_S
                while (not _commission_reported(trade)
                       and time.monotonic() < cdead):
                    self.ib.sleep(WAIT_TICK_S)
                return
            if s in _IB_CANCELLED:
                why = _trade_errors(trade, dead=True,
                                    venue=self._venue_error(trade))
                if s == "Inactive":
                    # ROUND 21 (2026-09-11, live). IB's "Inactive" is NOT
                    # dead: the order was accepted by the system and is
                    # merely not active - it is cancellable, and it can go
                    # LIVE later. This method reports it as a rejection
                    # (the caller must not count on it), so make the two
                    # agree: cancel it. Four such stops stacked on GH in
                    # fifteen minutes when the ratchet's second sell-stop
                    # came back Inactive each cycle and was left resting.
                    try:
                        self.ib.cancelOrder(trade.order)
                        logger.warning("order %s came back Inactive - "
                                       "cancelled so it cannot go live "
                                       "unrecorded", _order_ref(trade))
                    except Exception as exc:    # noqa: BLE001
                        logger.warning("cancel of Inactive order %s failed: "
                                       "%s", _order_ref(trade), exc)
                raise RuntimeError(
                    f"order rejected by venue (status {s})"
                    + (f": {why}" if why else ": IBKR gave no reason"))
            # 'ValidationError' = ib_async's warning overlay: the order may
            # be live and may yet transition to Submitted/Filled. Neither an
            # ack nor a death - keep waiting; the ack timeout below raises
            # UNKNOWN with the captured warning text.
            if s in ("PreSubmitted", "Submitted"):
                # Acked and resting. MOO/STP return 'working' right away;
                # MKT keeps one bounded window open for the synchronous fill.
                if fill_deadline is None or time.monotonic() >= fill_deadline:
                    return
            elif time.monotonic() >= ack_deadline:
                why = _trade_errors(trade)
                raise RuntimeError(
                    f"no venue ack within {PLACE_ACK_TIMEOUT_S:.0f}s "
                    f"(status {s!r}) — state UNKNOWN; retry is idempotent "
                    f"via orderRef" + (f" | venue log: {why}" if why else ""))
            self.ib.sleep(WAIT_TICK_S)

    def place_stock_order(self, symbol: str, qty: int, order_type: str,
                          stop_price: float | None = None, tif: str = "DAY",
                          ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        """qty signed (+buy/-sell); order_type in {MOO, MKT, STP}. Returns
        {order_ref, status, fill_price?}: MOO/STP come back 'working' (the
        journal/reconcile design adopts async fills); MKT returns 'filled'
        with the venue's average price when it fills inside the bounded
        wait, else 'working'. ref_price is the caller's sizing reference —
        never used as a fill price here."""
        if order_type not in ("MOO", "MKT", "STP"):
            raise ValueError(f"unsupported stock order type {order_type}")
        if order_type == "STP" and stop_price is None:
            raise ValueError("STP order requires stop_price")
        qty = int(qty)
        if qty == 0:
            raise ValueError("qty must be non-zero (signed +buy/-sell)")
        self._require_live()
        if client_order_id:
            # B1 (live-blocker, naked-short path): the idempotency key must
            # be resolved against the VENUE, not against this process's
            # trade list. `_find_trade_by_client_id` with the default
            # refresh=False reads `self.ib.trades()`, which is THIS SESSION
            # ONLY: after a restart — a Render deploy, an OOM, a gateway
            # reconnect that rebuilt the client — it is EMPTY, so a retry
            # carrying the same deterministic client id (e.g. the flatten's
            # `blend-{call_id}-kill`) saw no prior and placed a SECOND sell
            # of shares the first sell had already sold. Reproduced: venue
            # CRSP -10 against a 5-share book position, reported to the
            # operator as "flatten complete", with zero alerts mentioning a
            # short. `find_stock_order` — the boot/crash reconcile's own
            # lookup — has always used the two-stage form; the placement
            # path, the one that can actually create the short, did not.
            #
            # Fast path first (a binding order already in this session needs
            # no round-trip), then ask the venue for open + completed orders
            # whenever this session holds nothing that still binds.
            prior = self._find_trade_by_client_id(client_order_id)
            if (prior is None
                    or _map_status(prior.orderStatus.status) == "cancelled"):
                prior = (self._find_trade_by_client_id(client_order_id,
                                                       refresh=True)
                         or prior)
            if (prior is not None
                    and _map_status(prior.orderStatus.status) != "cancelled"):
                # Venue-side dedupe by orderRef (pinned contract): a working
                # or filled order under this idempotency key is returned,
                # never re-placed.
                logger.info("stock order %s duplicate-suppressed by orderRef "
                            "(prior %s)", client_order_id, _order_ref(prior))
                out = {**self._trade_result(prior), "duplicate": True}
                aux = _usable_px(getattr(prior.order, "auxPrice", None))
                if aux is not None:     # the price the PRIOR order holds,
                    out["stop_price"] = aux    # never the one just asked for
                return out
        from ib_async import MarketOrder, StopOrder
        action = "BUY" if qty > 0 else "SELL"
        placed_stop = None
        if order_type == "STP":
            placed_stop = round_stop_to_tick(stop_price, action)
            if placed_stop != float(stop_price):
                logger.info("stop %s %s snapped %s -> %s (venue price "
                            "increment)", action, symbol, stop_price,
                            placed_stop)
            order = StopOrder(action, abs(qty), placed_stop)
            order.tif = "GTC"               # protective stops always rest GTC
        else:
            order = MarketOrder(action, abs(qty))
            order.tif = "OPG" if order_type == "MOO" else "DAY"
        if client_order_id:
            order.orderRef = client_order_id
        contract = self._stock_contract(symbol)
        trade = self.ib.placeOrder(contract, order)
        self._await_placement(trade, order_type)
        out = self._trade_result(trade)
        if placed_stop is not None:
            # the price the venue actually holds, so the book can record it
            # and its next idempotency key matches what rests
            out["stop_price"] = placed_stop
        logger.info("stock order placed: %s %s x%d %s -> %s (%s)",
                    action, symbol, abs(qty), order_type, out["status"],
                    out["order_ref"])
        return out

    def _binding_prior(self, client_order_id: str):
        """The order that still BINDS under this idempotency key (working or
        filled), or None: this session first, then - whenever the session
        holds nothing that binds - the venue's open and completed orders.
        The same two-stage lookup place_stock_order makes (B1: after a
        restart the session's own trade list is empty, and a retry that only
        looked there placed a second order)."""
        prior = self._find_trade_by_client_id(client_order_id)
        if (prior is None
                or _map_status(prior.orderStatus.status) == "cancelled"):
            prior = (self._find_trade_by_client_id(client_order_id,
                                                   refresh=True)
                     or prior)
        if (prior is not None
                and _map_status(prior.orderStatus.status) != "cancelled"):
            return prior
        return None

    def place_limit_order(self, symbol: str, qty: int, limit_price: float,
                          tif: str = "DAY", ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        """A DAY LIMIT stock order (the Composer mirror's buys): qty signed
        (+buy/-sell), never filled above (buy) / below (sell) limit_price,
        which is snapped to the venue's grid WITHOUT loosening it (a buy
        limit rounds down, a sell limit up). Returns what place_stock_order
        returns for MKT - {order_ref, status, fill_price?, commission?} after
        one bounded synchronous-fill wait, else 'working' - plus limit_price,
        the price the venue holds. Raises on a rejection or a missing ack.
        Venue-side dedupe by client_order_id exactly as place_stock_order:
        a working or filled order under the key is returned (duplicate=True),
        never re-placed, and the lookup asks the VENUE when this session
        holds nothing that binds. LIMIT of that dedupe (the same as
        place_stock_order's): it reads open and completed orders, not the
        execution store, so on a gateway whose completed orders are
        unavailable a prior FILLED in an EARLIER session is not seen here.
        A caller that may retry across sessions asks find_stock_order (which
        does read the executions) or order_absent_today first - the mirror
        does. ref_price is the caller's reference - never used as a price
        here."""
        if str(tif).upper() != "DAY":
            raise ValueError(f"unsupported limit order tif {tif!r} (DAY only)")
        qty = int(qty)
        if qty == 0:
            raise ValueError("qty must be non-zero (signed +buy/-sell)")
        action = "BUY" if qty > 0 else "SELL"
        placed_limit = round_limit_to_tick(limit_price, action)
        self._require_live()
        if client_order_id:
            prior = self._binding_prior(client_order_id)
            if prior is not None:
                logger.info("limit order %s duplicate-suppressed by orderRef "
                            "(prior %s)", client_order_id, _order_ref(prior))
                out = {**self._trade_result(prior), "duplicate": True}
                held = _usable_px(getattr(prior.order, "lmtPrice", None))
                if held is not None:    # the price the PRIOR order holds
                    out["limit_price"] = held
                return out
        from ib_async import LimitOrder
        order = LimitOrder(action, abs(qty), placed_limit)
        order.tif = "DAY"
        if client_order_id:
            order.orderRef = client_order_id
        contract = self._stock_contract(symbol)
        trade = self.ib.placeOrder(contract, order)
        self._await_placement(trade, "LMT")
        out = self._trade_result(trade)
        out["limit_price"] = placed_limit
        logger.info("limit order placed: %s %s x%d @ %s -> %s (%s)",
                    action, symbol, abs(qty), placed_limit, out["status"],
                    out["order_ref"])
        return out

    def order_absent_today(self, client_order_id: str) -> bool | None:
        """Is it PROVEN that no order under this idempotency key is working
        and that none executed today? True only when BOTH venue requests
        answered - the open orders and today's executions - and neither shows
        the key; False when either does (or this session knows the order);
        None when either request did not answer (nothing is proven).

        For the caller that must tell "never reached the venue" from "the
        venue forgot" on a gateway that never answers reqCompletedOrders
        (history_complete() False): an order of TODAY that is not open and
        has no execution today filled nothing, whatever became of it.
        It proves nothing about an order of an earlier day - that is the
        caller's check. Read-only and additive: bounded like the other
        history requests, but it never drops the session on a timeout of
        its own. An EARLIER open-orders request still unanswered (K4,
        _open_orders_unanswered) is different: this request's answer could
        be ended by that one's late reply with a partial list and call a
        working order absent, so it is waited for (K5, bounded), and if it
        stays unanswered nothing is proven (None); the session is dropped
        when that request was a guarded read's, kept when it is the
        session's own connect-time sync (_open_orders_refusal)."""
        self._require_live()
        if self._find_trade_by_client_id(client_order_id) is not None:
            return False
        why = self._open_orders_unanswered()
        if why:
            logger.warning("order_absent_today: nothing proven - %s",
                           self._open_orders_refusal(why))
            return None
        prev = getattr(self.ib, "RequestTimeout", 0)
        try:
            self.ib.RequestTimeout = VENUE_HISTORY_TIMEOUT_S
            try:
                opens = list(self.ib.reqAllOpenOrders() or [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("order_absent_today: open orders did not "
                               "answer (%s)", exc)
                return None
            if any((getattr(t.order, "orderRef", "") or "") == client_order_id
                   for t in opens):
                return False
            try:
                fresh = list(self.ib.reqExecutions() or [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("order_absent_today: executions did not "
                               "answer (%s)", exc)
                return None
        finally:
            self.ib.RequestTimeout = prev
        store = list(getattr(self.ib, "fills", lambda: [])() or [])
        for f in store + fresh:
            ex = getattr(f, "execution", None)
            if ex is not None and (getattr(ex, "orderRef", "") or "") == client_order_id:
                return False
        return True

    def cancel_inactive_stock_order(self, client_order_id: str) -> bool:
        """Send a cancel for the order under this idempotency key when the
        venue holds it as INACTIVE. IB's Inactive is not dead - "it is
        cancellable, and it can go LIVE later" (round 21, _await_placement,
        which cancels one on sight at placement). This is the same cancel
        for an order that turned Inactive AFTER its ack, when the placement
        path is long gone. True when a cancel was sent; False when no order
        under the key is Inactive. No ack is awaited: the caller re-reads the
        order. Raises when disconnected."""
        self._require_live()
        trade = self._find_trade_by_client_id(client_order_id)
        if trade is None:
            trade = self._find_trade_by_client_id(client_order_id,
                                                  refresh=True)
        if trade is None or trade.orderStatus.status != "Inactive":
            return False
        self.ib.cancelOrder(trade.order)
        logger.warning("order %s (%s) is Inactive at the venue - cancel sent "
                       "so it cannot go live unrecorded", client_order_id,
                       _order_ref(trade))
        self._pump()
        return True

    def cancel_stock_order(self, order_ref: str) -> bool:
        """CONTRACT (order-safety law #8): cancelling an order that has
        FILLED must RAISE, never return False. False is reserved for 'order
        not found / already cancelled'. True only after the venue ACKS the
        cancel; an ambiguous ack timeout RAISES (fail closed) — the blend
        exit path defers the dependent sell and the next reconcile settles
        the truth (a silent False on a filled stop would be the double-sell
        race, counter-agent N2/N14). A cancel IB REFUSES is no ack: unless the
        venue's own Filled or Cancelled follows inside the window, it RAISES
        (_undo_refusal_overlay, _cancel_refusal)."""
        self._require_live()
        trade = self._find_trade_by_ref(order_ref)
        if trade is None:
            trade = self._find_trade_by_ref(order_ref, refresh=True)
        if trade is None:
            # Not open, not in the session. With completed orders
            # unavailable a stop that FILLED during an outage looks exactly
            # like "not found" - and False here is the double-sell race
            # (law #8). The execution reports settle it (counter-agent HIGH).
            if (getattr(self, "_completed_orders_unavailable", False)
                    and str(order_ref) in self._executed_order_ids()):
                raise RuntimeError(
                    f"cannot cancel {order_ref}: order already FILLED "
                    f"(execution reports; completed orders unavailable)")
            return False
        s = trade.orderStatus.status
        if s == "Filled":
            raise RuntimeError(
                f"cannot cancel {order_ref}: order already FILLED")
        if s in _IB_CANCELLED:
            return False
        since = len(getattr(trade, "log", None) or [])
        self._cancel_replies.pop(int(trade.order.orderId), None)  # THIS cancel's
        self.ib.cancelOrder(trade.order)
        deadline = time.monotonic() + CANCEL_ACK_TIMEOUT_S
        while True:
            self._pump()
            s = trade.orderStatus.status
            if s in ("Cancelled", "ApiCancelled"):
                refused = self._cancel_refusal(trade, since)
                if not refused:
                    return True
                # an error-set Cancelled _undo_refusal_overlay does not undo
                # (10147 "not found", or a code not yet seen on this book)
                raise RuntimeError(
                    f"cancel of {order_ref} REFUSED by IBKR ({refused}): "
                    f"ib_async marks the order Cancelled, but a refused cancel "
                    f"is not a cancel - it may have FILLED or may still be "
                    f"working — state UNKNOWN (fail closed)")
            refused = self._cancel_reply(trade)
            if s == "Filled":
                # The fill won the race with the cancel: surface it exactly
                # like a cancel-of-filled (the caller's raising path books
                # the fill via reconcile before any market sell).
                raise RuntimeError(
                    f"cannot cancel {order_ref}: order FILLED before the "
                    f"cancel landed"
                    + (f" (IBKR refused the cancel: {refused})" if refused
                       else ""))
            if time.monotonic() >= deadline:
                if refused:
                    raise RuntimeError(
                        f"cancel of {order_ref} REFUSED by IBKR ({refused}) "
                        f"and neither a fill nor a cancel followed within "
                        f"{CANCEL_ACK_TIMEOUT_S:.0f}s - the order may still be "
                        f"working or may have filled — state UNKNOWN (fail "
                        f"closed)")
                raise RuntimeError(
                    f"cancel of {order_ref} not acknowledged within "
                    f"{CANCEL_ACK_TIMEOUT_S:.0f}s — state UNKNOWN "
                    f"(fail closed)")
            self.ib.sleep(WAIT_TICK_S)

    def _cancel_refusal(self, trade, since: int) -> str:
        """Why `trade` reads Cancelled, when that is ib_async's word rather
        than the venue's: the text of the error that set the latest
        Cancelled in trade.log since this client's cancel was sent (entries
        from index `since`), unless it is IB's cancel confirmation (202). ""
        when the venue said it: an orderStatus (errorCode 0) or a 202.

        ib_async 2.1 sets a not-done trade Cancelled CLIENT-SIDE on any
        non-warning order error. Read as an ack, IB's REFUSAL of the cancel
        (161, "not in a cancellable state") made cancel_stock_order return
        True for an order that may still be working or may have FILLED - the
        fill that won the race reaches the session AFTER the refusal - and
        every caller acted on "cancelled": reconcile 2b re-planned a stuck
        order (bought twice), the exit and /kill paths market-sold beside a
        stop that filled, the ratchet placed a second stop, park and pass 3
        stopped tracking a stop still resting. A 161 or 10148 is undone
        where it lands (_undo_refusal_overlay); this is the belt for an
        error code that is not. Only the LATEST Cancelled counts: a refusal
        followed by the venue's own cancel in the same window is a cancel."""
        latest = None
        for e in (getattr(trade, "log", None) or [])[since:]:
            if str(getattr(e, "message", "") or "").startswith("Fill "):
                # ib_async's execDetails entry copies the CURRENT status: a
                # fill landing on an overlay reads (Cancelled, 0) and is no
                # venue status (verifier A, round 3)
                continue
            # ApiCancelled only ever comes from the venue (errorCode 0): it
            # counts as the venue's word after an undone refusal (verifier A)
            if str(getattr(e, "status", "") or "") in ("Cancelled", "ApiCancelled"):
                latest = e
        code = int(getattr(latest, "errorCode", 0) or 0) if latest else 0
        if not code or code == _IB_CANCEL_CONFIRMED_CODE:
            return ""
        stored = self._cancel_reply(trade) or self._venue_error(trade)
        if stored.startswith(f"[{code}]"):
            return stored
        return f"[{code}] {str(getattr(latest, 'message', '') or '').strip()}"

    def poll_stock_fills(self) -> list[dict]:
        """Drain-once fill events for resting protective stops, derived from
        venue order history (self.ib.trades(), synced on connect): each DONE
        STP order with executions is emitted EXACTLY once as
        {order_ref, client_order_id, symbol, qty, fill_price, action}, with
        partial fills aggregated per order at the share-weighted average
        price (qty signed by side). MOO/MKT fills are deliberately NOT
        emitted here — blend's journal reconcile (pass 2/2b) adopts them by
        orderRef, so they never surface as unknown-order alerts. A restart
        can re-emit an already-booked stop fill (the emitted-set is
        in-memory): blend's unknown-order branch turns that into RED noise,
        never a double booking — the documented tradeoff."""
        self._require_connected()
        self._pump()
        out, self._requeued_fills = self._requeued_fills, []
        for trade in self._all_trades():
            if getattr(trade.order, "orderType", "") != "STP":
                continue
            if trade.orderStatus.status not in ("Filled", "Cancelled",
                                                "ApiCancelled"):
                continue                      # still resting: nothing final yet
            keys = {str(trade.order.orderId)}
            perm = getattr(trade.order, "permId", 0)
            if perm:
                keys.add(str(perm))
            if keys & self._emitted_fill_keys:
                continue                      # never re-emit
            fills = _current_fills(getattr(trade, "fills", []) or [])   # a correction counts once
            shares = sum(int(f.execution.shares) for f in fills)
            if shares <= 0:
                # cancelled untouched: no event, and NOT marked emitted - a
                # status that later proves wrong (ib_async's Cancelled after
                # a refused cancel, verifier B 2026-10-26) must not swallow
                # the fill that lands afterwards
                continue
            self._emitted_fill_keys |= keys
            side = fills[0].execution.side    # 'BOT' | 'SLD'
            out.append({
                "order_ref": _order_ref(trade),
                "client_order_id": getattr(trade.order, "orderRef", "") or None,
                "symbol": trade.contract.symbol,
                "qty": shares if side == "BOT" else -shares,
                "fill_price": _agg_fill_price(trade),   # None, never 0.0
                "action": side,
                "commission": (_agg_commission(trade)      # None if ignored
                               if _commission_reported(trade) else None),
            })
        return out

    def requeue_stock_fills(self, fills: list[dict]) -> None:
        """Push un-ingested fill events back to the FRONT of the queue —
        blend's _ingest_fills re-queues on a mid-ingestion failure so a
        raising save()/alert never loses a venue fill (counter-agent N3)."""
        self._requeued_fills[:0] = list(fills)

    def find_stock_order(self, client_order_id: str) -> dict | None:
        """Look up a stock order by its idempotency key (IB orderRef).
        Returns {order_ref, status, fill_price?} or None if the venue never
        saw it — the boot/crash reconcile checks this before re-placing."""
        self._require_live()
        trade = self._find_trade_by_client_id(client_order_id)
        if trade is None:
            trade = self._find_trade_by_client_id(client_order_id,
                                                  refresh=True)
        if trade is not None:
            return self._trade_result(trade)
        if getattr(self, "_completed_orders_unavailable", False):
            # not open, not in the session: only the execution reports can
            # still say "it filled" (2026-09-08 fallback)
            return self._result_from_executions(client_order_id)
        return None

    def account_cash(self) -> dict | None:
        """The account's cash as IB reports it: {total_cash, net_liq, ts} in
        USD, or None meaning NO CLAIM. Never raises and never fails a cycle
        closed - in stage 1 nothing decides on it; it is the corroboration
        the book's order-derived cash ledger never had (dividends, interest,
        commissions and anything a human does are invisible to the ledger).
        TotalCashValue, not AvailableFunds: the latter moves with margin and
        open orders. AvailableFunds is returned ALONGSIDE it (never instead,
        stage 2, 2026-10-05) as `available_funds`, None when the venue does
        not report it: the capital adoption waits on it so a deposit that
        has landed but not settled is not spent before the venue would let
        it be.

        WHY a call made no claim is kept for the caller that must say it
        (the mirror's gates): last_cash_error (text; None after a claim) and
        last_cash_kind - "disconnected" (the gateway session is down),
        "unreadable" (connected, the values did not come) or "no_claim" (the
        account itself gives none: several accounts, no TotalCashValue)."""
        self.last_cash_error, self.last_cash_kind = None, None
        try:
            self._require_live()
            # accountValues() is the connect-time subscription: non-blocking
            # (accountSummary() issues a request with no timeout and could
            # wedge the loop thread - counter-agent round 2). Fall back to
            # the summary only when the subscription has nothing yet.
            rows = []
            try:
                rows = list(self.ib.accountValues() or [])
            except Exception:  # noqa: BLE001
                rows = []
            if not rows:
                # bounded: RequestTimeout defaults to 0 (= wait forever)
                prev = getattr(self.ib, "RequestTimeout", 0)
                try:
                    self.ib.RequestTimeout = 5
                    rows = list(self.ib.accountSummary() or [])
                finally:
                    self.ib.RequestTimeout = prev
            try:
                accts = list(self.ib.managedAccounts() or [])
            except Exception:  # noqa: BLE001
                accts = []
            if len(accts) > 1:
                # an advisor/master login: accts[0]'s values are consolidated
                # across sub-accounts - never a claim (round 3)
                logger.warning("account_cash: %d managed accounts (%s) - no "
                               "claim", len(accts), accts)
                return self._no_cash(f"{len(accts)} managed accounts on this "
                                     f"login", "no_claim")
            want = accts[0] if accts else None
            vals: dict[str, float] = {}
            seen_accts: set = set()
            for row in rows:
                tag = getattr(row, "tag", "")
                cur = getattr(row, "currency", "") or ""
                acct = getattr(row, "account", "") or ""
                if tag not in ("TotalCashValue", "NetLiquidation",
                               "AvailableFunds"):
                    continue
                if cur not in ("USD", ""):      # BASE may not be USD
                    continue
                if want and acct and acct != want:
                    continue
                if tag == "TotalCashValue" and acct:
                    seen_accts.add(acct)
                vals[tag] = float(getattr(row, "value", "nan"))
            if len(seen_accts) > 1:
                logger.warning("account_cash: %d accounts report cash (%s) - "
                               "no claim", len(seen_accts), sorted(seen_accts))
                return self._no_cash(f"{len(seen_accts)} accounts report cash",
                                     "no_claim")
            if "TotalCashValue" not in vals or vals["TotalCashValue"] != vals["TotalCashValue"]:
                return self._no_cash("the gateway reports no TotalCashValue in "
                                     "USD for this account", "no_claim")
            avail = vals.get("AvailableFunds")
            if avail is not None and avail != avail:      # NaN -> no claim
                avail = None
            return {"total_cash": vals["TotalCashValue"],
                    "net_liq": vals.get("NetLiquidation"),
                    "available_funds": avail,
                    "ts": time.time()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("account_cash unavailable (no claim): %s", exc)
            down = (isinstance(exc, ConnectionError)
                    or (isinstance(exc, ExecutorConnectionError)
                        and not isinstance(exc, ExecutorNotSyncedError)))
            try:
                down = down or not self.ib.isConnected()
            except Exception:  # noqa: BLE001
                pass
            return self._no_cash(f"{type(exc).__name__}: {exc}",
                                 "disconnected" if down else "unreadable")

    def _no_cash(self, why: str, kind: str) -> None:
        self.last_cash_error, self.last_cash_kind = why, kind
        return None

    def stock_position(self, symbol: str) -> int:
        """Net venue holding for a SMART/USD stock — what the ACCOUNT
        actually holds NOW. The R1 blackout guard's positive-verification
        basis: order history has a horizon, positions do not."""
        self._require_live()
        qty = 0
        for p in self._session_positions():
            c = getattr(p, "contract", None)
            if (c is not None and getattr(c, "symbol", "") == symbol
                    and getattr(c, "secType", "STK") in ("", "STK")):
                qty += int(p.position)
        return qty

    def open_sell_qty(self, symbol: str, exclude: str | None = None) -> int:
        """Shares of stock `symbol` that SELL orders still OPEN at the venue
        (any client, any order type) have yet to sell - the unfilled
        remainder of each. `exclude`: an orderRef whose own orders are not
        counted. For the mirror's checks before a sell (a run's, a
        flatten's): a sell on top of one already resting (a halted symbol, a
        stop placed by hand) would take the position short when both fill.
        Read-only and additive; bounded like the other history requests;
        RAISES when the open orders do not answer (the caller must then not
        sell). A request that TIMES OUT drops the session first, as
        _all_trades does: the next call reconnects (backoff, outage ledger,
        alerts) instead of waiting another 20 s on a session that answers
        the liveness round trip but never openOrderEnd.

        What is counted (K3a): (a) every order in THIS call's
        reqAllOpenOrders answer and (b) this client's own orders that the
        session still holds as working - never the rest of the session's
        cache. ib_async 2.1.0 caches every open order it is told of, whoever
        placed it (wrapper.py:685-712), keeps only this client's in sync
        (ib.py:942-948: other clients' orders "will not be kept in sync"),
        and a later completedOrder never replaces an order it already knows
        (wrapper.py:728-730): a sell placed by hand and cancelled after an
        earlier read in the same session counted for ever (a run's sell
        refused; a flatten refusing the symbol until it gave up).
        Why neither source misses a live order (an undercount allows a short):
          (a) is the venue's own list of the orders open NOW, any client's,
              complete once openOrderEnd ends the request; each entry comes
              with its status and fill (openOrder + orderStatus);
          (b) covers an order of ours the venue does not list yet (sent a
              moment ago: PendingSubmit). Every status change of this
              clientId's orders is sent to this client (wrapper.py:735-792,
              ib_async sets order.clientId at placeOrder: ib.py:805), so one
              the session still holds as working may still fill.
        An order of another client that only the cache still holds is not on
        the venue's list: it is no longer open and can sell nothing more.

        That completeness holds only when no EARLIER open-orders request is
        unanswered (K4, _open_orders_unanswered; it also rests on IB sending
        one openOrderEnd per request, see there): its late end could finish
        this request with a partial list. It is waited for (at most
        VENUE_HISTORY_TIMEOUT_S, K5); still unanswered, this read fails
        closed (the caller holds the sell and asks again) and the session is
        dropped - or kept, when the unanswered one is the session's own
        connect-time sync (_open_orders_refusal)."""
        self._require_live()
        why = self._open_orders_unanswered()
        if why:
            raise ExecutorConnectionError(self._open_orders_refusal(why))
        prev = getattr(self.ib, "RequestTimeout", 0)
        try:
            self.ib.RequestTimeout = VENUE_HISTORY_TIMEOUT_S
            opens = list(self.ib.reqAllOpenOrders() or [])
        except (TimeoutError, asyncio.TimeoutError) as exc:
            self._proven = None
            try:
                self.ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            raise ExecutorConnectionError(
                f"reqAllOpenOrders timed out after {VENUE_HISTORY_TIMEOUT_S:.0f}s: "
                f"the venue's open orders are unavailable (the session is "
                f"dropped and reconnected; restart the gateway if this "
                f"persists)") from exc
        finally:
            self.ib.RequestTimeout = prev
        cid = getattr(self.cfg, "ib_client_id", None)
        mine = [t for t in list(self.ib.trades())
                if cid is not None and getattr(t.order, "clientId", None) == cid]
        seen, qty = set(), 0
        for t in opens + mine:              # the venue's answer, then this client's own
            key = (t.order.orderId, getattr(t.order, "permId", 0))
            if key in seen:
                continue
            seen.add(key)
            c = getattr(t, "contract", None)
            if (c is None or getattr(c, "symbol", "") != symbol
                    or getattr(c, "secType", "STK") not in ("", "STK")
                    or getattr(t.order, "action", "") != "SELL"
                    or _map_status(t.orderStatus.status) != "working"):
                continue
            if exclude and (getattr(t.order, "orderRef", "") or "") == exclude:
                continue
            left = (float(t.order.totalQuantity)
                    - float(getattr(t.orderStatus, "filled", 0) or 0))
            if left > 0:
                qty += int(math.ceil(left))
        return qty

    def positions_snapshot(self) -> dict:
        """Everything the ACCOUNT holds, for a strategy that must own the whole
        account (the Composer mirror): {"stocks": {symbol: whole shares},
        "other": [text]}. `other` names what is not a whole stock lot - an
        option, a future, a fractional share - so the caller can refuse to
        treat the account as its own. Read-only; raises when disconnected, and
        when this gateway session has not delivered its positions
        (ExecutorNotSyncedError) - never the list of a dead session."""
        self._require_live()
        stocks: dict[str, int] = {}
        other: list[str] = []
        for p in self._session_positions():
            c = getattr(p, "contract", None)
            sym = getattr(c, "symbol", "?") if c is not None else "?"
            try:
                qty = float(p.position)
            except (TypeError, ValueError):
                other.append(f"{sym} unreadable position {p.position!r}")
                continue
            if qty == 0:
                continue
            sec = getattr(c, "secType", "STK") if c is not None else "?"
            if sec not in ("", "STK"):
                other.append(f"{sec} {sym} {qty:g}")
            elif qty != int(qty):
                other.append(f"STK {sym} fractional {qty:g}")
            else:
                stocks[sym] = stocks.get(sym, 0) + int(qty)
        return {"stocks": {k: v for k, v in sorted(stocks.items()) if v},
                "other": other}

    def stock_order_fills(self, client_order_id: str) -> dict | None:
        """What the order carrying this idempotency key EXECUTED, whatever
        its status: {filled_qty, avg_price, commission, venue_status}, or
        None when the venue has no order and no execution under the key.

        filled_qty  int, or None when no source is conclusive
        avg_price   None when no usable price was reported (never 0.0)
        commission  None until IB reports it for every execution
        venue_status  IB's own word for the order ("Filled", "Cancelled",
                    "Inactive", "Submitted", ...); None when only executions
                    were found. "Inactive" is not dead - see
                    cancel_inactive_stock_order.

        Sources, in the order they are trusted: the trade's own fills; the
        adapter's EXECUTION STORE by orderRef (ib_async builds a completed-
        order Trade with no fills and never attaches an execution it already
        stored, so a trade this session did not place can carry none of the
        shares it executed - _result_from_executions reads the same store);
        orderStatus.filled; and a completed order's filledQuantity. A zero is
        reported only where it is proven: the venue's completed-order record
        says 0, or the trade is in THIS session (whose execution store is
        current). Anything else is None - the caller must not book a guess.

        No venue-history request is made for a trade already in the session
        (the store is read as it stands); a trade the session does not know
        costs the bounded open/completed-orders refresh and one bounded
        reqExecutions, either of which FAILS CLOSED by raising. Read-only."""
        self._require_live()
        trade = self._find_trade_by_client_id(client_order_id)
        in_session = trade is not None
        if trade is None:
            trade = self._find_trade_by_client_id(client_order_id,
                                                  refresh=True)
        own = _current_fills(getattr(trade, "fills", []) or []) if trade is not None else []
        own_shares = sum(int(f.execution.shares) for f in own)
        by_id: dict = {}
        for f in own:
            by_id[getattr(f.execution, "execId", "") or id(f)] = f
        if in_session:
            pool = list(getattr(self.ib, "fills", lambda: [])() or [])
        elif own_shares <= 0:
            pool = self._executions_refreshed()
        else:
            pool = []
        extra: dict = {}
        for f in pool:
            ex = getattr(f, "execution", None)
            if ex is None or (getattr(ex, "orderRef", "") or "") != client_order_id:
                continue
            extra[getattr(ex, "execId", "") or id(f)] = f
        if extra:
            # one orderRef can span a rejected-then-retried attempt: only the
            # executions of the order that binds count (the trade's own id
            # when it is known, else the latest - _result_from_executions)
            ids = {getattr(f.execution, "orderId", 0) or 0 for f in extra.values()}
            want = (getattr(trade.order, "orderId", 0) or 0) if trade is not None else 0
            pick = want if want in ids else max(ids)
            for key, f in extra.items():
                if (getattr(f.execution, "orderId", 0) or 0) == pick:
                    by_id.setdefault(key, f)
        if trade is None and not by_id:
            return None
        src = type("_Fills", (), {})()
        # a correction and what it corrects can come one from each source:
        # the merged list counts each execution once, at its latest correction
        src.fills = _current_fills(list(by_id.values()))
        src.orderStatus = (trade.orderStatus if trade is not None
                           else type("_S", (), {"avgFillPrice": 0.0})())
        shares = sum(int(f.execution.shares) for f in src.fills)
        counts = [shares]
        done = None
        if trade is not None:
            try:
                counts.append(int(getattr(trade.orderStatus, "filled", 0) or 0))
            except (TypeError, ValueError):
                pass
            try:
                fq = float(getattr(trade.order, "filledQuantity", None))
                if 0 <= fq < 1e12 and fq == int(fq):   # IB's UNSET is ~1.8e308
                    done = int(fq)
                    counts.append(done)
            except (TypeError, ValueError):
                pass
        best = max(counts)
        if best > 0:
            filled = best
        elif done == 0 or in_session:
            filled = 0
        else:
            filled = None
        px = _agg_fill_price(src) if (filled or 0) > 0 else None
        comm = _agg_commission(src) if _commission_reported(src) else None
        return {"filled_qty": filled,
                "avg_price": float(px) if px is not None else None,
                "commission": comm,
                "venue_status": (str(trade.orderStatus.status)
                                 if trade is not None else None)}


class DryAdapter:
    """No gateway, no orders: synthesizes fills at the budget and marks flat.
    Lets the full decision loop + alerting run before any credential exists."""

    def __init__(self):
        self.log: list[dict] = []
        self._open: dict[str, float] = {}
        self._stops: dict[str, dict] = {}   # working GTC stock stops (blend)
        self._orders: dict[str, dict] = {}  # order_ref -> full stock-order record
        self._by_client: dict[str, str] = {}  # client_order_id -> order_ref
        self._fills: list[dict] = []        # stop-fill events awaiting poll
        self._last_px: dict[str, float] = {}  # last ref/fill price per symbol
        self._positions: dict[str, int] = {}  # net venue holdings from filled
                                              # orders (stock_position surface)

    def _rec(self, action, **kw):
        e = {"ts": int(time.time()), "action": action, **kw}
        self.log.append(e)
        logger.info("DRY %s", e)

    def spot(self, symbol: str) -> float:
        # Sleeve names quote at the last reference/fill price seen, so dry
        # exit fills and P&L are anchored to real inputs rather than a
        # fictional flat 100 (counter-agent minor finding).
        if symbol in self._last_px:
            return self._last_px[symbol]
        return {"NG": 2.6, "SB": 15.6, "SLV": 55.9}.get(symbol, 100.0)

    def spot_ex(self, symbol: str) -> tuple[float, str]:
        """Dry quotes are synthetic but they are never STALE — every one is
        produced for the cycle asking for it, so none of them is the
        previous-close case CR-N2 guards against."""
        return self.spot(symbol), "live"

    def seed_price(self, symbol: str, px: float) -> None:
        """Anchor a dry quote to a REAL input (a tracker entry_ref) before
        any fill exists for that symbol. Without it a dry sleeve name
        quotes at a fictional flat 100, which the entry_ref sanity band
        would read as a 10x mispricing on a $9 stock and refuse. A real
        fill still wins: this only fills in a symbol never seen."""
        if px and px > 0 and symbol not in self._last_px:
            self._last_px[symbol] = float(px)

    def open_spread(self, structure: dict, budget: float) -> dict:
        ref = f"dry-{structure['underlying']}-{int(time.time())}"
        self._open[ref] = budget
        self._rec("open_spread", structure=structure, budget=budget, ref=ref)
        return {"order_ref": ref, "premium": budget}

    def mark(self, order_ref: str) -> float | None:
        return self._open.get(order_ref)

    def close_spread(self, order_ref: str) -> dict:
        v = self._open.pop(order_ref, 0.0)
        self._rec("close_spread", ref=order_ref, value=v)
        return {"value": v}

    # -- stock/ETF orders (blend3070) -----------------------------------------
    # MOO/MKT fill immediately at the provided reference price (fall back to
    # spot); STP rests as a working GTC order until cancelled or triggered
    # via trigger_stop() (tests / simulated stop-outs). Triggered stops queue
    # a fill event that poll_stock_fills() drains — the blend cycle's
    # reconciliation-first pass. Two resting stops for the same symbol may
    # coexist transiently (place-new-then-cancel-old replace ordering).
    # client_order_id is the idempotency key: a duplicate placement while the
    # prior order is working/filled returns the PRIOR order (venue-side
    # dedupe, mirroring what the paper IBAdapter must do with orderRef).

    def _order_result(self, rec: dict) -> dict:
        out = {"order_ref": rec["order_ref"], "status": rec["status"]}
        if rec.get("fill_price") is not None:
            out["fill_price"] = rec["fill_price"]
        if rec["status"] == "filled":
            out["commission"] = 0.0     # synthetic fill: a REPORTED zero, so
        return out                      # dry runs do not page "unreported"

    def place_stock_order(self, symbol: str, qty: int, order_type: str,
                          stop_price: float | None = None, tif: str = "DAY",
                          ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        if order_type not in ("MOO", "MKT", "STP"):
            raise ValueError(f"unsupported stock order type {order_type}")
        if client_order_id:
            prior = self._orders.get(self._by_client.get(client_order_id, ""))
            if prior is not None and prior["status"] in ("working", "filled"):
                self._rec("duplicate_suppressed", symbol=symbol, qty=qty,
                          client_order_id=client_order_id,
                          ref=prior["order_ref"])
                out = {**self._order_result(prior), "duplicate": True}
                if prior.get("stop_price") is not None:
                    out["stop_price"] = prior["stop_price"]
                return out
        ref = f"dry-stk-{symbol}-{len(self.log)}-{int(time.time())}"
        if order_type == "STP":
            if stop_price is None:
                raise ValueError("STP order requires stop_price")
            # Snapped exactly as the live adapter snaps it: a paper run that
            # rests a price the real venue would REJECT is the simulation
            # lying about the one order that protects the book.
            stop_price = round_stop_to_tick(
                stop_price, "BUY" if qty > 0 else "SELL")
            self._stops[ref] = {"symbol": symbol, "qty": qty,
                                "stop_price": stop_price, "tif": tif}
            rec = {"order_ref": ref, "symbol": symbol, "qty": qty,
                   "order_type": "STP", "stop_price": stop_price, "tif": tif,
                   "status": "working", "fill_price": None,
                   "client_order_id": client_order_id}
            self._orders[ref] = rec
            if client_order_id:
                self._by_client[client_order_id] = ref
            self._rec("place_stock_order", symbol=symbol, qty=qty,
                      order_type=order_type, stop_price=stop_price, tif=tif,
                      ref=ref, status="working")
            return {"order_ref": ref, "status": "working",
                    "stop_price": stop_price}
        fill = ref_price if ref_price is not None else self.spot(symbol)
        self._last_px[symbol] = fill
        self._positions[symbol] = self._positions.get(symbol, 0) + qty
        rec = {"order_ref": ref, "symbol": symbol, "qty": qty,
               "order_type": order_type, "tif": tif, "status": "filled",
               "fill_price": fill, "client_order_id": client_order_id}
        self._orders[ref] = rec
        if client_order_id:
            self._by_client[client_order_id] = ref
        self._rec("place_stock_order", symbol=symbol, qty=qty,
                  order_type=order_type, tif=tif, ref=ref, status="filled",
                  fill_price=fill)
        return self._order_result(rec)

    def cancel_stock_order(self, order_ref: str) -> bool:
        rec = self._orders.get(order_ref)
        if rec is not None and rec["status"] == "filled":
            # Pinned contract (order-safety law #8): a cancel of a FILLED
            # order RAISES — mirroring IB, which errors on such a cancel —
            # so the caller's raising-cancel deferral path handles it. A
            # bool False stays reserved for not-found/already-cancelled.
            self._rec("cancel_stock_order", ref=order_ref, error="filled")
            raise RuntimeError(f"cannot cancel {order_ref}: order already "
                               f"FILLED")
        found = self._stops.pop(order_ref, None) is not None
        if found and order_ref in self._orders:
            self._orders[order_ref]["status"] = "cancelled"
        self._rec("cancel_stock_order", ref=order_ref, found=found)
        return found

    def trigger_stop(self, order_ref: str) -> dict:
        """Simulate the market touching a resting stop: fills AT the stop and
        queues a fill event for the next poll_stock_fills()."""
        o = self._stops.pop(order_ref)
        if order_ref in self._orders:
            self._orders[order_ref]["status"] = "filled"
            self._orders[order_ref]["fill_price"] = o["stop_price"]
        self._last_px[o["symbol"]] = o["stop_price"]
        self._positions[o["symbol"]] = (self._positions.get(o["symbol"], 0)
                                        + o["qty"])
        self._fills.append({"order_ref": order_ref, "symbol": o["symbol"],
                            "qty": o["qty"], "fill_price": o["stop_price"]})
        self._rec("stop_triggered", ref=order_ref, symbol=o["symbol"],
                  qty=o["qty"], fill_price=o["stop_price"])
        return {"order_ref": order_ref, "status": "filled",
                "fill_price": o["stop_price"]}

    def trigger_stop_partial(self, order_ref: str, shares: int) -> dict:
        """Simulate a PARTIAL fill at the stop followed by a venue cancel
        (adapter review M3): `shares` fill AT the stop, the remainder is
        cancelled at the venue; ONE aggregated fill event with the SIGNED
        PARTIAL qty queues for the poll — mirroring the real adapter's
        terminal-order emission of a partially-filled-then-cancelled STP."""
        o = self._stops.pop(order_ref)
        sign = -1 if o["qty"] < 0 else 1
        shares = min(shares, abs(o["qty"]))
        if order_ref in self._orders:
            self._orders[order_ref]["status"] = "cancelled"
            self._orders[order_ref]["fill_price"] = o["stop_price"]
        self._last_px[o["symbol"]] = o["stop_price"]
        self._positions[o["symbol"]] = (self._positions.get(o["symbol"], 0)
                                        + sign * shares)
        self._fills.append({"order_ref": order_ref, "symbol": o["symbol"],
                            "qty": sign * shares,
                            "fill_price": o["stop_price"]})
        self._rec("stop_triggered", ref=order_ref, symbol=o["symbol"],
                  qty=sign * shares, fill_price=o["stop_price"],
                  partial=True)
        return {"order_ref": order_ref, "status": "cancelled",
                "fill_price": o["stop_price"]}

    def poll_stock_fills(self) -> list[dict]:
        """Drain queued stop-fill events (read-only: not logged as an intent)."""
        out, self._fills = self._fills, []
        return out

    def requeue_stock_fills(self, fills: list[dict]) -> None:
        """Push un-ingested fill events back to the FRONT of the queue —
        reconcile re-queues on a mid-ingestion failure so a raising save()
        or alert callback never loses a venue fill (counter-agent N3)."""
        self._fills[:0] = list(fills)

    def find_stock_order(self, client_order_id: str) -> dict | None:
        rec = self._orders.get(self._by_client.get(client_order_id, ""))
        return self._order_result(rec) if rec is not None else None

    def account_cash(self) -> dict | None:
        return None                      # no venue, no claim

    def stock_position(self, symbol: str) -> int:
        """Net venue holding for symbol, from filled orders — mirrors the
        IBAdapter positions surface (the R1 blackout guard's positive-
        verification basis)."""
        return self._positions.get(symbol, 0)

    def seed_position(self, symbol: str, qty: int) -> None:
        """Assert what the ACCOUNT holds without routing an order through
        the fill path — the same class of simulation hook as
        `trigger_stop`/`trigger_stop_partial`. A book seeded straight into
        the manager (a restored state file, a test fixture) describes shares
        this adapter never filled, and the flatten's venue ceiling reads
        THIS surface: without a seed such a book looks like a naked short to
        every guard, which is exactly right and exactly not what those
        setups mean."""
        self._positions[symbol] = self._positions.get(symbol, 0) + int(qty)

    def prove_live(self, timeout: float = 0.0) -> None:
        """Mirrors IBAdapter.prove_live: no gateway behind a paper adapter,
        so there is no session to prove."""
        return None

    def positions_snapshot(self) -> dict:
        """Mirrors IBAdapter.positions_snapshot: the simulated account's whole
        stock lots; nothing else can exist here."""
        return {"stocks": {k: v for k, v in sorted(self._positions.items()) if v},
                "other": []}

    def stock_order_fills(self, client_order_id: str) -> dict | None:
        """Mirrors IBAdapter.stock_order_fills for the simulated orders: a
        filled order executed its whole quantity at its fill price, anything
        else executed nothing (a simulator's zero is always proven)."""
        rec = self._orders.get(self._by_client.get(client_order_id, ""))
        if rec is None:
            return None
        done = rec["status"] == "filled" and rec.get("fill_price") is not None
        return {"filled_qty": abs(int(rec["qty"])) if done else 0,
                "avg_price": float(rec["fill_price"]) if done else None,
                "commission": 0.0 if done else None,
                "venue_status": {"filled": "Filled", "cancelled": "Cancelled",
                                 "working": "Submitted"}.get(rec["status"])}

    def history_complete(self) -> bool:
        """Mirrors IBAdapter.history_complete: the simulator's order memory
        has no horizon, so 'no such order' is always the whole truth."""
        return True

    def place_limit_order(self, symbol: str, qty: int, limit_price: float,
                          tif: str = "DAY", ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        """Mirrors IBAdapter.place_limit_order: the limit is recorded snapped
        to the venue's grid the way the live adapter snaps it; a BUY fills AT
        the reference price when that is at or below the limit asked for (a
        SELL when it is at or above), else it rests 'working' until
        cancelled. A resting limit is kept with the resting stops, so
        cancel_stock_order cancels it and trigger_stop simulates the market
        reaching its limit."""
        if str(tif).upper() != "DAY":
            raise ValueError(f"unsupported limit order tif {tif!r} (DAY only)")
        qty = int(qty)
        if qty == 0:
            raise ValueError("qty must be non-zero (signed +buy/-sell)")
        limit = round_limit_to_tick(limit_price, "BUY" if qty > 0 else "SELL")
        if client_order_id:
            prior = self._orders.get(self._by_client.get(client_order_id, ""))
            if prior is not None and prior["status"] in ("working", "filled"):
                self._rec("duplicate_suppressed", symbol=symbol, qty=qty,
                          client_order_id=client_order_id,
                          ref=prior["order_ref"])
                out = {**self._order_result(prior), "duplicate": True}
                if prior.get("limit_price") is not None:
                    out["limit_price"] = prior["limit_price"]
                return out
        ref = f"dry-stk-{symbol}-{len(self.log)}-{int(time.time())}"
        px = float(ref_price) if ref_price is not None else self.spot(symbol)
        # compared with the limit AS GIVEN: a paper fill at the reference is
        # the caller's contract, and a sub-cent reference just above a grid
        # point must not strand it (the recorded limit is the snapped one)
        asked = float(limit_price)
        crosses = px <= asked if qty > 0 else px >= asked
        rec = {"order_ref": ref, "symbol": symbol, "qty": qty,
               "order_type": "LMT", "tif": tif, "limit_price": limit,
               "status": "filled" if crosses else "working",
               "fill_price": px if crosses else None,
               "client_order_id": client_order_id}
        self._orders[ref] = rec
        if client_order_id:
            self._by_client[client_order_id] = ref
        if crosses:
            self._last_px[symbol] = px
            self._positions[symbol] = self._positions.get(symbol, 0) + qty
        else:
            self._stops[ref] = {"symbol": symbol, "qty": qty,
                                "stop_price": limit, "tif": tif}
        self._rec("place_limit_order", symbol=symbol, qty=qty, tif=tif,
                  limit_price=limit, ref=ref, status=rec["status"],
                  fill_price=rec["fill_price"])
        return {**self._order_result(rec), "limit_price": limit}

    def cancel_inactive_stock_order(self, client_order_id: str) -> bool:
        """Mirrors IBAdapter.cancel_inactive_stock_order: a simulated order
        is never Inactive, so there is never a cancel to send."""
        return False

    def order_absent_today(self, client_order_id: str) -> bool | None:
        """Mirrors IBAdapter.order_absent_today: the simulator's order
        memory is whole, so it always answers - True when it never saw the
        key."""
        return self._orders.get(self._by_client.get(client_order_id, "")) is None
