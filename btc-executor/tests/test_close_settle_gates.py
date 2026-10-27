"""Close-settlement gates: the single-leg close books its fill from the
venue's POSITION, never from one order_status read.

The 2026-10-07 08:01Z LEDGER_DIVERGENCE halt (docs/HALT_2026-10-07.md): the
executor closed a pullback leg the engine had not booked (IOC reduce-only
SELL 0.93614, filled IN FULL in four prints in the same second per the
venue's own historicalOrders/userFills), read the order ONCE, got a partial
filled_qty, and booked the difference as a residue "retrying next poll".
Nothing retried: the single-leg path never set close_cloid, so
_settle_close never ran for it. The next three polls compared that belief
against the venue (net = the trend leg only), the trend leg's resting stop
read OPEN so the second look gave grace twice, and the third poll halted the
book - and the halt flattened the trend leg the engine still held.

These gates pin the outcome in the venue's terms: after a close whose first
status read is a transient partial, the ledger equals the venue within one
poll, no residue survives, no netting_inconsistent is raised, nothing halts,
and the other leg keeps its stop. A GENUINE partial IOC keeps exactly the
residue the venue shows and retries. An UNKNOWN read keeps the ref and
settles later without a second close order.
"""
import time

import pytest

from app import mirror
from test_executor_gates import FakeVenue, _hold, _pos, mkexec, target

PULL, TREND = 0.9, 0.03                 # same-side book: both long
STOP = 56_500.0


class TransientPartialVenue(FakeVenue):
    """The first status read of each '-X' close answers FILLED with a
    PARTIAL filled_qty although the order filled in full (the venue's
    position already shows the whole fill) - the 10-07 read."""

    def __init__(self, *a, first_read_qty=0.5, **k):
        super().__init__(*a, **k)
        self.first_read_qty = first_read_qty
        self._seen: set = set()

    def order_status(self, cloid):
        st = super().order_status(cloid)
        if st and cloid.endswith("-X") and cloid not in self._seen:
            self._seen.add(cloid)
            if st["status"] == "FILLED":
                return {**st, "filled_qty": self.first_read_qty}
        return st


class PartialIocVenue(FakeVenue):
    """The first '-X' close genuinely fills only `part`; the position
    reflects exactly that; later closes fill in full."""

    def __init__(self, *a, part=0.5, **k):
        super().__init__(*a, **k)
        self.part = part
        self._done = False

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and not self._done:
            self._done = True
            qty = min(qty, self.part)
        super().place_market(side, qty, cloid, reduce_only=reduce_only)


class UnknownThenFilledVenue(FakeVenue):
    """'-X' status reads UNKNOWN `n` times, then the truth."""

    def __init__(self, *a, unknown_reads=2, **k):
        super().__init__(*a, **k)
        self.unknown_left = unknown_reads

    def order_status(self, cloid):
        if cloid.endswith("-X") and self.unknown_left > 0:
            self.unknown_left -= 1
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


def test_gate_transient_partial_read_on_a_full_close_never_halts(tmp_path,
                                                                 monkeypatch):
    """The 10-07 read: order filled in full, first status read says half.
    Pre-fix: close_partial books a 0.4 residue, three polls of
    netting_inconsistent, LEDGER_DIVERGENCE, the trend leg flattened."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = TransientPartialVenue(first_read_qty=0.5)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))          # engine reports the pullback flat
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert p.qty == 0.0 and p.close_cloid is None, (p.qty, p.close_cloid)
    assert t.qty == pytest.approx(TREND)
    assert v.position() == pytest.approx(TREND)
    assert "close_partial" not in _kinds(ex, n0)
    assert "netting_inconsistent" not in _kinds(ex, n0)
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "engine_exit" in closed[0]["msg"]
    for _ in range(4):
        ex.step(target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert v.orders[t.stop_cloid]["status"] == "OPEN", "trend lost its stop"
    assert len(_xs(v)) == 1, "a second close was sent off a stale residue"
    assert ex.state.coverage_live.get("signal_exit", 0) == 1


def test_gate_genuine_partial_ioc_keeps_the_venue_residue_and_retries(
        tmp_path, monkeypatch):
    """A close that really fills only half: the ledger keeps exactly what
    the venue still holds for that leg, raises no mismatch, and the next
    poll closes the remainder."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = PartialIocVenue(part=0.5)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == pytest.approx(PULL - 0.5)
    assert v.position() == pytest.approx(TREND + PULL - 0.5)
    assert p.close_cloid is None            # settled: residue is venue truth
    assert "leg_partially_closed" in _kinds(ex, n0)
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert ex.state.halted is None
    time.sleep(1.05)                        # close cloids carry the second
    ex.step(target(trend=trend_tl))         # retries the remainder
    assert p.qty == 0.0 and len(_xs(v)) == 2
    assert v.position() == pytest.approx(TREND)
    assert ex.state.halted is None and "netting_inconsistent" not in _kinds(ex, n0)


def test_gate_unknown_close_read_keeps_the_ref_and_settles_without_resend(
        tmp_path, monkeypatch):
    """Status reads UNKNOWN twice after the send: the ref is kept, no second
    close goes out, the third read settles it from the position."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = UnknownThenFilledVenue(unknown_reads=2)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    ex.step(target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.close_cloid and p.close_why == "engine_exit"
    assert "close_unconfirmed" in _kinds(ex, n0)
    assert len(_xs(v)) == 1
    ex.step(target(trend=trend_tl))         # second UNKNOWN, then the truth
    assert len(_xs(v)) == 1, "re-sent a close while one was in flight"
    assert p.qty == 0.0 and p.close_cloid is None and p.close_why is None
    assert ex.state.halted is None
    assert "netting_inconsistent" not in _kinds(ex, n0)
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "engine_exit" in closed[0]["msg"]


def test_gate_close_ref_survives_a_restart_and_settles_on_boot(tmp_path,
                                                               monkeypatch):
    """Belief before the send: a crash between the send and the confirm
    must not lose the close - the persisted ref is settled by the next
    process from the venue's answer."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = UnknownThenFilledVenue(unknown_reads=1)
    ex, trend_tl = _book(tmp_path, v)
    ex.step(target(trend=trend_tl))
    assert ex.state.legs["pullback"].close_cloid
    ex2 = mkexec(tmp_path, v, dry_run=False)        # fresh boot, same state
    p2 = ex2.state.legs["pullback"]
    # the persisted ref is settled by boot reconcile from the venue's answer
    assert p2.qty == 0.0 and p2.close_cloid is None and p2.close_why is None
    assert ex2.state.halted is None
    ex2.step(target(trend=trend_tl))
    assert p2.qty == 0.0 and len(_xs(v)) == 1
    assert ex2.state.halted is None
