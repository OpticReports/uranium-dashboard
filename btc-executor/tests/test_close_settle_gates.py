"""Close-settlement gates: a same-side / single-leg close is booked from the
venue's own answer to the order, never from one status or position read.

The 2026-10-07 08:01Z LEDGER_DIVERGENCE halt (docs/HALT_2026-10-07.md): the
executor closed a pullback leg the engine had not booked (IOC reduce-only
SELL 0.93614, filled IN FULL in four prints in the same second per the
venue's historicalOrders/userFills), read the order ONCE, got a terminal
read that satisfied `0.0 < filled + 1e-9 < qty` (a zero-fill read does -
unknownOid from an info node that did not yet know the order), and booked
the difference as a residue "retrying next poll". Nothing retried: the
single-leg path never set a close ref. The next three polls compared that
belief against the venue (net = the trend leg only); the trend's resting
stop read OPEN so the second look gave grace twice; the third poll halted
the book and the halt flattened the trend leg.

The review's adversarial probes (A: position lagging forever; B: position
part-applied on the first read; C: status UNKNOWN forever, order never
filled; E: unknownOid on the first read with a stale first position read)
are each a gate here. Outcome pinned in the venue's terms: the ledger
equals what the venue did, within the bounded settle window; no residue is
invented; nothing halts; the other leg keeps its stop; exactly one close
order unless the venue really never filled it.
"""
import time

import pytest

from app import mirror
from test_executor_gates import FakeVenue, _hold, _pos, mkexec, target

PULL, TREND = 0.9, 0.03                 # same-side book: both long
STOP = 56_500.0


class ResponseVenue(FakeVenue):
    """place_market answers like hl.place_market: the exchange's own fill.
    `part` makes the first '-X' close a genuine partial IOC."""

    def __init__(self, *a, part=None, **k):
        super().__init__(*a, **k)
        self.part, self._done = part, False

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and self.part is not None and not self._done:
            self._done, qty = True, min(qty, self.part)
        super().place_market(side, qty, cloid, reduce_only=reduce_only)
        o = self.orders.get(cloid)
        if o and o["status"] == "FILLED":
            return {"filled_qty": o["qty"], "avg_px": o["px"], "resting": False}
        return {"filled_qty": 0.0, "avg_px": None, "resting": False}


class SilentVenue(FakeVenue):
    """No usable send answer (the Coinbase adapter, or a parse failure):
    the ref is kept and settled on later polls."""


class UnknownOidFirstReadVenue(SilentVenue):
    """Probe E: the first status read of the '-X' order answers as
    hl.order_status maps unknownOid (CANCELLED / 0), and the first
    position() read after the send is the stale pre-close net."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._first_status = True
        self._stale_pos = None

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X"):
            self._stale_pos = self.position()
        super().place_market(side, qty, cloid, reduce_only=reduce_only)

    def order_status(self, cloid):
        if cloid.endswith("-X") and self._first_status:
            self._first_status = False
            return {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None}
        return super().order_status(cloid)

    def position(self):
        if self._stale_pos is not None:
            p, self._stale_pos = self._stale_pos, None
            return p
        return super().position()


class UnknownForNReadsVenue(SilentVenue):
    def __init__(self, *a, n=1, **k):
        super().__init__(*a, **k)
        self.unknown_left = n

    def order_status(self, cloid):
        if cloid.endswith("-X") and self.unknown_left > 0:
            self.unknown_left -= 1
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        return super().order_status(cloid)


class LagPositionVenue(SilentVenue):
    """Probe A: position() frozen at the pre-close net forever; the order
    record is truthful."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.frozen = None

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and self.frozen is None:
            self.frozen = self.position()
        super().place_market(side, qty, cloid, reduce_only=reduce_only)

    def position(self):
        return self.frozen if self.frozen is not None else super().position()


class TransientPositionVenue(SilentVenue):
    """Probe B: the order record reads FILLED/full; the first position()
    read after the send shows the fill only part-applied."""

    def __init__(self, *a, left=0.4, **k):
        super().__init__(*a, **k)
        self.left, self._armed = left, False

    def place_market(self, side, qty, cloid, reduce_only=False):
        super().place_market(side, qty, cloid, reduce_only=reduce_only)
        if cloid.endswith("-X"):
            self._armed = True

    def position(self):
        if self._armed:
            self._armed = False
            return super().position() + self.left
        return super().position()


class UnknownForeverUnfilledVenue(SilentVenue):
    """Probe C: the '-X' order is accepted but never fills and its status
    reads UNKNOWN forever; the position never moves."""

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X"):
            self.orders[cloid] = {"type": "MARKET", "side": side, "qty": qty,
                                  "px": None, "status": "OPEN", "part": 0.0}
            self.calls.append(("MARKET", side, round(qty, 5), cloid))
            return None
        return super().place_market(side, qty, cloid, reduce_only=reduce_only)

    def order_status(self, cloid):
        if cloid.endswith("-X"):
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        return super().order_status(cloid)


def _book(tmp_path, v):
    """Pullback long PULL + trend long TREND, venue holding the net, the
    trend leg with a resting venue stop (the 10-07 shape)."""
    ex = mkexec(tmp_path, v, dry_run=False)
    ex.state.legs["pullback"].qty = PULL
    ex.state.legs["trend"].qty = TREND
    _hold(v, PULL + TREND)
    trend_tl = _pos(side="L", stop=STOP)
    ex.step(target(pull=_pos(side="L", stop=STOP), trend=trend_tl))
    assert ex.state.halted is None
    assert ex.state.legs["trend"].stop_cloid, "trend stop not armed"
    return ex, trend_tl


def _kinds(ex, since=0):
    return [e["kind"] for e in ex.state.events[since:]]


def _xs(v):
    return [c for c in v.calls if c[0] == "MARKET" and c[3].endswith("-X")]


def _healthy(ex, v, n0, xs=1):
    t = ex.state.legs["trend"]
    assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert "close_partial" not in _kinds(ex, n0)
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert v.orders[t.stop_cloid]["status"] == "OPEN", "trend lost its stop"
    assert len(_xs(v)) == xs, _xs(v)


def test_gate_send_response_books_the_full_close(tmp_path):
    v = ResponseVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))          # engine reports the pullback flat
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None and p.close_mode is None
    assert v.position() == pytest.approx(TREND)
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "engine_exit" in closed[0]["msg"]
    assert ex.state.coverage_live.get("signal_exit", 0) == 1
    for _ in range(4):
        ex.step(target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_send_response_partial_ioc_keeps_the_venue_residue(tmp_path):
    v = ResponseVenue(part=0.5)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == pytest.approx(PULL - 0.5) and p.close_cloid is None
    assert v.position() == pytest.approx(TREND + PULL - 0.5)
    assert "leg_partially_closed" in _kinds(ex, n0)
    ex.step(target(trend=trend_tl))         # the remainder, a new cloid
    assert p.qty == 0.0 and v.position() == pytest.approx(TREND)
    _healthy(ex, v, n0, xs=2)


def test_gate_no_send_answer_settles_from_the_order_record(tmp_path):
    v = SilentVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))         # record FILLED/full -> booked
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None and p.close_mode is None
    assert "close_unconfirmed" not in _kinds(ex, n0)
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "engine_exit" in closed[0]["msg"]
    _healthy(ex, v, n0)


def test_gate_probe_E_unknownoid_first_read_is_not_never_existed(tmp_path):
    """The 10-07 read shape: a terminal zero-fill answer seconds after the
    send plus a stale first position read. Pre-fix: the whole leg booked
    as a 'residue', three polls, LEDGER_DIVERGENCE, trend flattened."""
    v = UnknownOidFirstReadVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))         # send; CANCELLED/0 too young: wait
    p = ex.state.legs["pullback"]
    assert p.close_cloid and p.qty == PULL and p.close_unknown_polls == 1
    assert "close_never_happened" not in _kinds(ex, n0)
    assert "close_unconfirmed" in _kinds(ex, n0)
    ex.step(target(trend=trend_tl))         # the truth: FILLED/full
    assert p.qty == 0.0 and p.close_cloid is None
    for _ in range(3):
        ex.step(target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_unknown_reads_keep_the_ref_and_never_resend(tmp_path):
    v = UnknownForNReadsVenue(n=1)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))         # UNKNOWN: ref kept, RED, no resend
    p = ex.state.legs["pullback"]
    assert p.close_cloid and len(_xs(v)) == 1
    ex.step(target(trend=trend_tl))         # record FILLED/full
    assert p.qty == 0.0 and p.close_cloid is None
    _healthy(ex, v, n0)


def test_gate_unknown_streak_is_settled_from_the_position_change(tmp_path):
    v = UnknownForNReadsVenue(n=5)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    for _ in range(mirror.CLOSE_UNKNOWN_MAX_POLLS):
        ex.step(target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None
    assert "close_settled_by_position" in _kinds(ex, n0)
    reds = [e for e in ex.state.events[n0:] if e["kind"] == "close_unconfirmed"]
    assert len(reds) >= 1 and len({e["msg"] for e in reds}) == len(reds), \
        "close_unconfirmed must not dedupe into silence"
    _healthy(ex, v, n0)


def test_gate_probe_A_lagging_position_never_halts_a_recorded_fill(tmp_path):
    v = LagPositionVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    ex.step(target(trend=trend_tl))         # record FILLED/full -> booked
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None
    for _ in range(5):                      # the venue keeps answering 0.93
        ex.step(target(trend=trend_tl))
    assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert "position_drift" in _kinds(ex, n0), "a lagging venue must stay visible"
    assert ex.state.legs["trend"].stop_cloid and len(_xs(v)) == 1


def test_gate_probe_B_part_applied_position_read_books_nothing_wrong(tmp_path):
    v = TransientPositionVenue(left=0.4)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    ex.step(target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and "leg_partially_closed" not in _kinds(ex, n0)
    for _ in range(4):
        ex.step(target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_probe_C_unknown_forever_unfilled_is_bounded_and_loud(tmp_path):
    v = UnknownForeverUnfilledVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(2 * (mirror.CLOSE_UNKNOWN_MAX_POLLS + 1)):
        ex.step(target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    p = ex.state.legs["pullback"]
    assert p.qty == PULL                     # it really never filled
    assert v.position() == pytest.approx(PULL + TREND)
    assert "close_never_happened" in _kinds(ex, n0)
    reds = [e for e in ex.state.events[n0:]
            if e["kind"] in ("close_unconfirmed", "close_never_happened",
                             "close_settled_by_position")]
    assert len(reds) >= mirror.CLOSE_UNKNOWN_MAX_POLLS + 1
    assert len(_xs(v)) >= 2                 # retried after each tiebreak
    assert "netting_inconsistent" not in _kinds(ex, n0)
    t = ex.state.legs["trend"]
    assert t.qty == pytest.approx(TREND) and t.stop_cloid


def test_gate_close_ref_survives_a_restart_and_settles_on_boot(tmp_path):
    v = UnknownForNReadsVenue(n=1)          # the send poll cannot settle it
    ex, trend_tl = _book(tmp_path, v)
    ex.step(target(trend=trend_tl))
    assert ex.state.legs["pullback"].close_cloid
    ex2 = mkexec(tmp_path, v, dry_run=False)        # fresh boot, same state
    p2 = ex2.state.legs["pullback"]
    assert p2.qty == 0.0 and p2.close_cloid is None, "boot did not settle it"
    assert ex2.state.halted is None
    ex2.step(target(trend=trend_tl))
    assert p2.qty == 0.0 and len(_xs(v)) == 1 and ex2.state.halted is None
