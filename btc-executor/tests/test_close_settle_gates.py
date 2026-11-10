"""Close-settlement gates: a same-side / single-leg close is booked from the
venue's own answer to the order, never from one status or position read.

The 2026-10-07 08:01Z LEDGER_DIVERGENCE halt (docs/HALT_2026-10-07.md): the
executor closed a pullback leg the engine had not booked (IOC reduce-only
SELL 0.93614, filled IN FULL in four prints in the same millisecond per the
venue's historicalOrders/userFills), read the order ONCE, got a terminal
read that satisfied `0.0 < filled + 1e-9 < qty` (a zero-fill read does -
unknownOid from an info node that did not yet know the order), and booked
the difference as a residue "retrying next poll". Nothing retried: the
single-leg path never set a close ref. The next three polls compared that
belief against the venue (net = the trend leg only); the trend's resting
stop read OPEN so the second look gave grace twice; the third poll halted
the book and the halt flattened the trend leg.

Two review rounds (2026-10-27) attacked the fix with probes; each probe is
a gate here, run against a clock that advances one poll period (20 s) per
step so the wall-clock rules are exercised. Outcome pinned in the venue's
terms: the ledger equals what the venue did, within the bounded settle
window; no residue is invented; nothing halts; the other leg keeps its
stop and is never closed by this leg's retry; exactly one close order
unless the venue really never filled it.
"""
import time

import pytest

from app import hl, mirror
from test_executor_gates import FakeVenue, _hold, _pos, mkexec, target

PULL, TREND = 0.9, 0.03                 # same-side book: both long
STOP = 56_500.0
POLL_S = 20.0


class Clock:
    def __init__(self):
        self.t = float(int(time.time()))

    def __call__(self):
        return self.t

    def tick(self, s=POLL_S):
        self.t += s


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(mirror.time, "time", c)
    return c


class ResponseVenue(FakeVenue):
    """place_market answers like hl.place_market: the exchange's own fill.
    `part` makes the first '-X' close a genuine partial IOC."""

    def __init__(self, *a, part=None, **k):
        super().__init__(*a, **k)
        self.part, self._done = part, False
        self.position_calls = 0

    def position(self):
        self.position_calls += 1
        return super().position()

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and self.part is not None and not self._done:
            self._done, qty = True, min(qty, self.part)
        super().place_market(side, qty, cloid, reduce_only=reduce_only)
        o = self.orders.get(cloid)
        if o and o["status"] == "FILLED":
            return {"filled_qty": o["qty"], "avg_px": o["px"], "resting": False}
        return {"filled_qty": 0.0, "avg_px": None, "resting": False}


class SilentVenue(FakeVenue):
    """No usable send answer (the Coinbase adapter, a parse failure): the
    order record settles it. Reduce-only orders are clamped against the
    TRUE position (the venue's own rule) even when position() is made to
    lag below, so a wrong retry shows up as the other leg being closed."""

    def _true_position(self):
        return FakeVenue.position(self)

    def place_market(self, side, qty, cloid, reduce_only=False):
        if reduce_only:
            self.reduce_only_cloids = getattr(self, "reduce_only_cloids", []) + [cloid]
            net = self._true_position()
            if abs(net) <= 1e-9 or (net > 0) != (side == "SELL"):
                self.calls.append(("MARKET_NOOP", side, round(qty, 5), cloid))
                return None
            qty = min(qty, abs(net))
        self._add("MARKET", side, qty, cloid, px=self._mid)
        return None


class StatusScriptVenue(SilentVenue):
    """'-X' status reads follow a script of answers (then the truth);
    position() reads follow a script of lags (True = stale pre-send net)."""

    def __init__(self, *a, status_script=(), stale_script=(), **k):
        super().__init__(*a, **k)
        self.status_script = list(status_script)
        self.stale_script = list(stale_script)
        self._pre = None

    def place_market(self, side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X"):
            self._pre = self._true_position()
        return super().place_market(side, qty, cloid, reduce_only=reduce_only)

    def order_status(self, cloid):
        if cloid.endswith("-X") and self.status_script:
            ans = self.status_script.pop(0)
            if ans == "UNKNOWN":
                return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
            if ans == "unknownOid":
                return {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None}
            if isinstance(ans, tuple):            # (status, filled_qty)
                return {"status": ans[0], "filled_qty": ans[1], "avg_price": None}
        return super().order_status(cloid)

    def position(self):
        if self.stale_script and self._pre is not None:
            if self.stale_script.pop(0):
                return self._pre
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


class RaiseAfterAcceptVenue(SilentVenue):
    """The send raises AFTER the venue accepted and filled the order."""

    def place_market(self, side, qty, cloid, reduce_only=False):
        super().place_market(side, qty, cloid, reduce_only=reduce_only)
        if cloid.endswith("-X"):
            raise RuntimeError("read timeout after send")


def _book(tmp_path, v, trend_stop=STOP, pull_tl=None):
    """Pullback long PULL + trend long TREND, venue holding the net, the
    trend leg with a resting venue stop (the 10-07 shape)."""
    ex = mkexec(tmp_path, v, dry_run=False)
    ex.state.legs["pullback"].qty = PULL
    ex.state.legs["trend"].qty = TREND
    _hold(v, PULL + TREND)
    trend_tl = _pos(side="L", stop=trend_stop)
    ex.step(target(pull=pull_tl or _pos(side="L", stop=STOP), trend=trend_tl))
    assert ex.state.halted is None
    assert ex.state.legs["trend"].stop_cloid, "trend stop not armed"
    return ex, trend_tl


def _poll(ex, clock, tgt):
    ex.step(tgt)
    clock.tick()


def _kinds(ex, since=0):
    return [e["kind"] for e in ex.state.events[since:]]


def _xs(v):
    return [c for c in v.calls if c[0] == "MARKET" and c[3].endswith("-X")]


def _healthy(ex, v, n0, xs=1):
    t = ex.state.legs["trend"]
    assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert "close_partial" not in _kinds(ex, n0)
    assert "close_never_happened" not in _kinds(ex, n0)
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert v.orders[t.stop_cloid]["status"] == "OPEN", "trend lost its stop"
    assert len(_xs(v)) == xs, _xs(v)
    assert v._true_position() == pytest.approx(TREND) if hasattr(v, "_true_position") \
        else v.position() == pytest.approx(TREND)


# ----------------------------------------------------------------- send answer

def test_gate_send_response_books_the_full_close_without_a_position_read(
        tmp_path, clock):
    v = ResponseVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # engine reports the pullback flat
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None and p.close_mode is None
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "engine_exit" in closed[0]["msg"]
    assert "via send response" in closed[0]["msg"]
    assert "close_settled_by_position" not in _kinds(ex, n0)
    assert ex.state.coverage_live.get("signal_exit", 0) == 1
    for _ in range(4):
        _poll(ex, clock, target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_send_response_partial_ioc_keeps_the_venue_residue(tmp_path, clock):
    v = ResponseVenue(part=0.5)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == pytest.approx(PULL - 0.5) and p.close_cloid is None
    assert v.position() == pytest.approx(TREND + PULL - 0.5)
    assert "leg_partially_closed" in _kinds(ex, n0)
    _poll(ex, clock, target(trend=trend_tl))     # the remainder, a new cloid
    assert p.qty == 0.0 and v.position() == pytest.approx(TREND)
    _healthy(ex, v, n0, xs=2)


def test_gate_fill_from_response_shapes():
    f = hl.HyperliquidVenue._fill_from_response
    ok = {"status": "ok", "response": {"data": {"statuses": [
        {"filled": {"totalSz": "0.93614", "avgPx": "84113.0", "oid": 1}}]}}}
    assert f(ok) == {"filled_qty": 0.93614, "avg_px": 84113.0, "resting": False}
    rest = {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 1}}]}}}
    assert f(rest)["resting"] is True and f(rest)["filled_qty"] == 0.0
    assert f({"status": "ok", "response": {"data": {"statuses": [{"filled": {}}]}}}) is None
    assert f({"status": "ok", "response": {"data": {"statuses": ["waitingForFill"]}}}) is None
    assert f({"status": "ok", "response": {"data": {"statuses": []}}}) is None
    assert f("garbage") is None and f(None) is None


# ----------------------------------------------------------- the order record

def test_gate_no_send_answer_settles_from_the_order_record(tmp_path, clock):
    v = SilentVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # record FILLED/full -> booked
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None and p.close_mode is None
    assert "close_unconfirmed" not in _kinds(ex, n0)
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "via order record" in closed[0]["msg"]
    _healthy(ex, v, n0)


def test_gate_probe_E_unknownoid_first_read_is_waited_out(tmp_path, clock):
    """The 10-07 read shape: a terminal zero-fill answer seconds after the
    send plus a stale first position read. Pre-fix: the whole leg booked
    as a 'residue', three polls, LEDGER_DIVERGENCE, trend flattened."""
    v = StatusScriptVenue(status_script=["unknownOid"], stale_script=[True])
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # CANCELLED/0 at age 0: wait
    p = ex.state.legs["pullback"]
    assert p.close_cloid and p.qty == PULL and p.close_unknown_polls == 1
    assert "close_unconfirmed" in _kinds(ex, n0)
    _poll(ex, clock, target(trend=trend_tl))     # the truth: FILLED/full
    assert p.qty == 0.0 and p.close_cloid is None
    for _ in range(3):
        _poll(ex, clock, target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_transitional_partial_first_read_books_no_residue(tmp_path, clock):
    """Shape (ii): a terminal read seconds after the send showing half,
    then the final record. Binds CLOSE_SETTLE_MIN_AGE_S."""
    for first in (("CANCELLED", 0.5), ("FILLED", 0.5)):
        v = StatusScriptVenue(status_script=[first])
        ex, trend_tl = _book(tmp_path / first[0], v)
        n0 = len(ex.state.events)
        _poll(ex, clock, target(trend=trend_tl))
        p = ex.state.legs["pullback"]
        assert p.close_cloid and p.qty == PULL, first
        assert "leg_partially_closed" not in _kinds(ex, n0)
        _poll(ex, clock, target(trend=trend_tl))
        assert p.qty == 0.0 and "leg_partially_closed" not in _kinds(ex, n0)
        _healthy(ex, v, n0)


def test_gate_genuine_partial_record_books_after_the_min_age(tmp_path, clock):
    v = StatusScriptVenue(status_script=[("CANCELLED", 0.5)] * 6)
    v.part = 0.5                                  # the venue really filled half
    orig = v.place_market

    def pm(side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and v.part is not None:
            qty, v.part = min(qty, v.part), None
        return orig(side, qty, cloid, reduce_only=reduce_only)
    v.place_market = pm
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # age 0: wait
    _poll(ex, clock, target(trend=trend_tl))     # age 20: wait
    p = ex.state.legs["pullback"]
    assert p.qty == PULL and p.close_cloid
    _poll(ex, clock, target(trend=trend_tl))     # age 40: the partial books,
    assert "leg_partially_closed" in _kinds(ex, n0)   # remainder re-closed
    assert p.qty == 0.0 and p.close_cloid is None     # after a fresh corroboration
    _healthy(ex, v, n0, xs=2)


def test_gate_unknown_reads_keep_the_ref_and_never_resend(tmp_path, clock):
    v = StatusScriptVenue(status_script=["UNKNOWN"])
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # UNKNOWN: ref kept, RED
    p = ex.state.legs["pullback"]
    assert p.close_cloid and len(_xs(v)) == 1
    _poll(ex, clock, target(trend=trend_tl))     # record FILLED/full
    assert p.qty == 0.0 and p.close_cloid is None
    _healthy(ex, v, n0)


def test_gate_head_guard_never_spends_the_netting_grace(tmp_path, clock):
    """While the ref is open the close's own fill must not be read as a
    divergence: no netting_inconsistent at all, static trend trail."""
    v = StatusScriptVenue(status_script=["UNKNOWN"] * 4)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(3):
        _poll(ex, clock, target(trend=trend_tl))
    assert ex.state.legs["pullback"].qty == 0.0
    _healthy(ex, v, n0)


# ------------------------------------------------------ position tiebreak

def test_gate_unknown_streak_is_settled_from_the_position_change(tmp_path, clock):
    v = StatusScriptVenue(status_script=["UNKNOWN"] * 12)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(1 + mirror.CLOSE_UNKNOWN_MAX_POLLS):   # ages 0, 20, 40
        _poll(ex, clock, target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    # round 3: a full move books only when it holds on TWO tiebreak polls
    # (another leg's stop reads OPEN in the instant it fires)
    assert p.qty == PULL and p.close_cloid and p.close_moved_polls == 1
    assert "close_settled_by_position" not in _kinds(ex, n0)
    _poll(ex, clock, target(trend=trend_tl))      # age 60: the second look
    assert p.qty == 0.0 and p.close_cloid is None
    assert "close_settled_by_position" in _kinds(ex, n0)
    reds = [e for e in ex.state.events[n0:] if e["kind"] == "close_unconfirmed"]
    assert len(reds) >= 2 and len({e["msg"] for e in reds}) == len(reds), \
        "close_unconfirmed must not dedupe into silence"
    _healthy(ex, v, n0)


def test_gate_round2_send_poll_settle_via_the_other_legs_stop_maintenance(
        tmp_path, clock):
    """The trend trail moved >5bp in the send poll, so its stop maintenance
    corroborates, sees the close's fill as a divergence and settles the
    pullback ref INSIDE the send poll - with a stale position read. Round
    2: the call-counted tiebreak fired at age 0 and cleared the ref."""
    v = StatusScriptVenue(status_script=["UNKNOWN"] * 6,
                          stale_script=[False, True])
    ex, _ = _book(tmp_path, v)
    moved = _pos(side="L", stop=STOP * 1.01)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=moved))
    p = ex.state.legs["pullback"]
    assert p.close_cloid and p.qty == PULL, _kinds(ex, n0)
    assert "close_never_happened" not in _kinds(ex, n0)
    for _ in range(4):
        _poll(ex, clock, target(trend=moved))
    assert p.qty == 0.0 and ex.state.halted is None, _kinds(ex, n0)[-10:]
    assert "close_never_happened" not in _kinds(ex, n0)
    t = ex.state.legs["trend"]
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert len(_xs(v)) == 1 and v._true_position() == pytest.approx(TREND)


def test_gate_round2_unusable_reads_and_a_lagging_node_never_close_the_other_leg(
        tmp_path, clock):
    """Status unusable for three polls and the position stale on every read
    in that window (one lagging info node). Round 2: close_never_happened
    at poll 2, a retry sized to the whole leg, clamped by the venue onto
    the trend's 0.03 - the wrong leg closed, no halt, a phantom leg."""
    v = StatusScriptVenue(status_script=["UNKNOWN"] * 9,
                          stale_script=[True] * 12)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(4):                            # ages 0, 20, 40, 60
        _poll(ex, clock, target(trend=trend_tl))
        assert len(_xs(v)) == 1, "a second close was sent off a stale read"
        assert "close_never_happened" not in _kinds(ex, n0)
    assert ex.state.legs["pullback"].qty == 0.0   # the record arrived
    _healthy(ex, v, n0)


def test_gate_probe_A_lagging_position_never_halts_a_recorded_fill(tmp_path, clock):
    v = StatusScriptVenue(stale_script=[True] * 40)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))     # record FILLED/full -> booked
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and p.close_cloid is None
    for _ in range(5):                            # the venue keeps answering 0.93
        _poll(ex, clock, target(trend=trend_tl))
    assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert "position_drift" in _kinds(ex, n0), "a lagging venue must stay visible"
    assert ex.state.legs["trend"].stop_cloid and len(_xs(v)) == 1


def test_gate_probe_B_part_applied_position_read_books_nothing_wrong(tmp_path, clock):
    class PartApplied(SilentVenue):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._armed = False

        def place_market(self, side, qty, cloid, reduce_only=False):
            r = super().place_market(side, qty, cloid, reduce_only=reduce_only)
            if cloid.endswith("-X"):
                self._armed = True
            return r

        def position(self):
            if self._armed:
                self._armed = False
                return super().position() + 0.4
            return super().position()
    v = PartApplied()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.qty == 0.0 and "leg_partially_closed" not in _kinds(ex, n0)
    for _ in range(4):
        _poll(ex, clock, target(trend=trend_tl))
    _healthy(ex, v, n0)


def test_gate_probe_C_unknown_forever_unfilled_is_bounded_and_loud(tmp_path, clock):
    v = UnknownForeverUnfilledVenue()
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(30):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    p = ex.state.legs["pullback"]
    assert p.qty == PULL                          # it really never filled
    assert v._true_position() == pytest.approx(PULL + TREND)
    assert "close_never_happened" in _kinds(ex, n0)
    assert "close_stuck" in _kinds(ex, n0), "the retry loop must end loud"
    assert len(_xs(v)) == 1 + mirror.CLOSE_NEVER_MAX, _xs(v)
    reds = [e for e in ex.state.events[n0:] if e["level"] == "RED"]
    assert len(reds) >= 20, "a RED every poll, no dedupe into silence"
    assert "netting_inconsistent" not in _kinds(ex, n0)
    t = ex.state.legs["trend"]
    assert t.qty == pytest.approx(TREND) and t.stop_cloid


def test_gate_exit_flag_branch_leaves_no_orphan_stop(tmp_path, clock):
    """The send raises after the venue accepted and filled. On the engine's
    exit_flag branch stop maintenance runs before the close each poll: with
    the ref open it must NOT re-arm a stop that would rest on the other
    leg's exposure once the close books (round 2, probe f). Round 3: the
    window is only exercised when the position read is STALE (a fresh read
    diverges and the second look books the close first), so the record is
    unusable and the position lags for three polls here."""
    class StaleRaise(RaiseAfterAcceptVenue):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pre, self.stale_left = None, 0

        def place_market(self, side, qty, cloid, reduce_only=False):
            if cloid.endswith("-X"):
                self._pre, self.stale_left = self._true_position(), 3
            return super().place_market(side, qty, cloid, reduce_only=reduce_only)

        def order_status(self, cloid):
            if cloid.endswith("-X") and self.stale_left > 0:
                return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
            return super().order_status(cloid)

        def position(self):
            if self.stale_left > 0:
                return self._pre
            return super().position()
    v = StaleRaise()
    flagged = _pos(side="L", stop=STOP, flag="SIGNAL")
    ex, trend_tl = _book(tmp_path, v, pull_tl=_pos(side="L", stop=STOP))
    n0 = len(ex.state.events)
    p = ex.state.legs["pullback"]
    placed0 = len([c for c in v.calls if c[0] == "STOP" and c[3].startswith("P-")])
    for k in range(5):
        _poll(ex, clock, target(pull=flagged, trend=trend_tl))
        if k == 0:
            assert "close_rejected" in _kinds(ex, n0) and p.close_cloid
        placed = len([c for c in v.calls if c[0] == "STOP" and c[3].startswith("P-")])
        assert placed == placed0, "a stop was re-armed with the close in flight"
        v.stale_left -= 1
    assert p.qty == 0.0 and p.close_cloid is None and p.stop_cloid is None
    orphans = [c for c, o in v.orders.items()
               if c.startswith("P-") and o["type"] == "STOP" and o["status"] == "OPEN"]
    assert not orphans, orphans
    _healthy(ex, v, n0)


def test_gate_close_ref_survives_a_restart_and_settles_on_boot(tmp_path, clock):
    v = StatusScriptVenue(status_script=["UNKNOWN"])     # the send poll cannot settle it
    ex, trend_tl = _book(tmp_path, v)
    _poll(ex, clock, target(trend=trend_tl))
    assert ex.state.legs["pullback"].close_cloid
    ex2 = mkexec(tmp_path, v, dry_run=False)        # fresh boot, same state
    p2 = ex2.state.legs["pullback"]
    assert p2.qty == 0.0 and p2.close_cloid is None, "boot did not settle it"
    assert ex2.state.halted is None
    _poll(ex2, clock, target(trend=trend_tl))
    assert p2.qty == 0.0 and len(_xs(v)) == 1 and ex2.state.halted is None
