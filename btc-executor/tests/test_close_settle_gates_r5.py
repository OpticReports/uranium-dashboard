"""Round-5 close-settlement gates (2026-10-28, docs/HALT_2026-10-07.md s3).

Two independent verifiers attacked the round-5 tree (cd9367a). What these
gates bind:

- the netting-grace deferral is BOUNDED to the close's own settle window
  (an external reduction of the other leg under a dropped ref halts the
  book within a few polls instead of hiding for ever);
- the absorb deferral is gone: an unattributable net with a filled stop
  and a single ref open halts, bounded, instead of stranding the stop
  ref and paging every poll;
- an unbooked change on the other leg EQUAL to this close no longer
  reads as "unmoved": the verdict waits while that leg's entry is
  unreadable or filled beyond what is booked (both verdict doors);
- unmoved looks must be consecutive across an ambiguous move;
- a partially filled trigger keeps its residue on its own leg;
- close_stuck is logged once per leg per ten minutes (two stuck legs);
- hl.position() refuses a response without a positions list.
"""
import pytest

import app.alerts as alerts
from app import mirror
from app.hl import HyperliquidVenue
from test_executor_gates import _hold, _pos, mkexec, target, NOW
from test_close_settle_gates import (Clock, _book, _poll, _kinds, _xs, PULL, TREND,
                                     STOP)
from test_close_settle_gates_r3 import (PollVenue, _fire_trend_stop, _ledger_sum,
                                        _spy_sends)

UNK = {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(mirror.time, "time", c)
    return c


@pytest.fixture
def pings(monkeypatch):
    out = []
    monkeypatch.setattr(alerts, "send", lambda m: out.append(m))
    return out


# ------------------------------------------------- the deferral is bounded

@pytest.mark.parametrize("record", ["unknownOid", "UNKNOWN"])
def test_gate_r5_external_close_of_the_other_leg_under_a_dropped_ref_halts_bounded(
        tmp_path, clock, pings, record):
    """The pullback's send never reached the venue; the trend's exposure
    leaves by a hand not ours (its reduce-only stop reads CANCELLED). The
    pullback's own exposure reads a partial move for ever (held), so round
    5's deferral - for the life of the ref - hid the phantom trend and the
    stopless, un-exited pullback for two hours with no halt and no retry.
    Now the deferral ends with the close's settle window and the book
    halts within a few polls (the halt flattens the leg the engine wanted
    closed); nothing else is sent."""
    v = PollVenue(drop=1, dropped_reads=record)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))          # send poll: dropped
    assert p.close_cloid and p.stop_cloid is None
    v._add("MARKET", "SELL", TREND, "external-close-trend")
    v.orders[t.stop_cloid]["status"] = "CANCELLED"
    assert v._true_position() == pytest.approx(PULL)
    halt_poll = None
    for i in range(2, 16):
        _poll(ex, clock, target(trend=trend_tl))
        if ex.state.halted:
            halt_poll = i
            break
    assert ex.state.halted == "LEDGER_DIVERGENCE" and halt_poll <= 12, _kinds(ex, n0)[-8:]
    assert abs(v._true_position()) < 1e-9, "the halt did not flatten the real exposure"
    assert len(v.sends) == 1 and "close_never_happened" not in _kinds(ex, n0)


def test_gate_r5_unattributable_net_with_a_single_ref_open_halts_bounded(
        tmp_path, clock, pings):
    """The pullback's send is dropped; the trend's stop fires; an external
    BUY lands on the account. The trend's absorb cannot attribute the net
    and round 5 never counted the poll while a single ref was open: no
    halt for ever, the FILLED stop ref stranded, `stop_filled_on_venue`
    paged every poll. Now the poll counts and the book halts in three."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    assert p.close_cloid
    _fire_trend_stop(v, ex)
    v._add("MARKET", "BUY", 0.5, "external-buy")
    halt_poll = None
    for i in range(2, 14):
        _poll(ex, clock, target(trend=trend_tl))
        if ex.state.halted:
            halt_poll = i
            break
    assert ex.state.halted == "LEDGER_DIVERGENCE" and halt_poll <= 6, _kinds(ex, n0)[-8:]
    assert _kinds(ex, n0).count("stop_filled_on_venue") <= 5
    assert len([m for m in pings if "stop_filled_on_venue" in m]) <= 5


# ---------------------------------------- an unbooked change of equal size

@pytest.mark.parametrize("door", ["affirmative", "hard"])
def test_gate_r5_equal_size_unbooked_maker_fill_never_reads_as_unmoved(
        tmp_path, clock, door):
    """The trend alone holds 0.03; its IOC close fills (venue flat); its
    record lies (unknownOid, or nothing usable at all). In the same
    outage the pullback's resting maker entry prints EXACTLY 0.03 with
    its status unreadable: the trend's own exposure reads 0.03 - 0 ==
    at the send, "unmoved". Round 5 rendered the verdict through either
    door and the retry sold the pullback's fill. Now the unmoved look is
    not counted while the other leg's entry is unreadable; the close
    books from its record once it answers."""
    if door == "affirmative":
        v = PollVenue(status_fn=lambda p, c: ("unknownOid" if 3 <= p <= 11 else
                                               "UNKNOWN" if p < 3 else None))
    else:
        v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 11 else None)
    ex = mkexec(tmp_path, v, dry_run=False)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    t.qty = TREND
    _hold(v, TREND)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend, trend=_pos(side="L", stop=STOP)))
    clock.tick()
    assert t.stop_cloid and p.entry_cloid
    entry = p.entry_cloid
    orig = v.order_status

    def ostat(cloid):
        if cloid == entry and 1 <= v.poll() <= 9:
            return dict(UNK)
        return orig(cloid)
    v.order_status = ostat
    n0 = len(ex.state.events)
    _poll(ex, clock, target(pull=pend))               # trend flat -> close fills
    assert t.close_cloid and v._true_position() == pytest.approx(0.0)
    v.orders[entry]["qty"] = TREND                    # the maker prints EXACTLY 0.03
    v.orders[entry]["status"] = "FILLED"
    for _ in range(2, 12):
        _poll(ex, clock, target(pull=pend))
        assert len(v.sends) == 1, f"a retry was sent off a masked close: {v.sends}"
        assert "close_never_happened" not in _kinds(ex, n0)
        assert ex.state.halted is None
    _poll(ex, clock, target(pull=pend))               # poll 12: the record answers
    _poll(ex, clock, target(pull=pend))
    assert t.qty == 0.0 and t.close_cloid is None
    assert p.qty == pytest.approx(TREND) and "entry_filled_early" in _kinds(ex, n0)
    assert _ledger_sum(ex) == pytest.approx(v._true_position())
    assert ex.state.halted is None and len(v.sends) == 1


def test_gate_r5_unmoved_looks_must_be_consecutive_across_an_ambiguous_move(
        tmp_path, clock):
    """The close FILLED; its record lies unknownOid from poll 3; the
    position is stale on polls 3 and 5 and fresh on 4, where the trend's
    stop reads UNKNOWN (ambiguous). Round 5 counted polls 3 and 5 as two
    unmoved looks and rendered the verdict; the retry was clamped onto
    the trend and the book halted. Now an ambiguous move resets the
    unmoved count: no verdict, nothing sent, no halt."""
    v = PollVenue(status_fn=lambda p, c: "unknownOid" if p >= 3 else "UNKNOWN",
                  stale_fn=lambda p: p in (3, 5), stop_fn=lambda p: p == 4)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    sends, verdicts = _spy_sends(ex, v)
    n0 = len(ex.state.events)
    for _ in range(11):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert not verdicts and len(sends) == 1
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert v._true_position() == pytest.approx(TREND)


# ------------------------------------------------- a partial trigger fill

def test_gate_r5_partially_filled_trigger_keeps_its_residue_on_its_own_leg(
        tmp_path, clock):
    """The pullback's IOC fills 0.5 of 0.9 (record unusable); the trend's
    stop fires but fills only 0.01 of 0.03. Round 5's partial_single took
    the trend flat and left 0.02 on the venue with no ledger row and no
    stop. Now the trend keeps 0.02 (a stop residue, re-armed) and the
    pullback books its partial from the record (which answers inside the
    close's settle window; a record slower than that halts the book while
    the residue is stopless - fail loud)."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 4 else None)
    v.part = 0.5
    orig = v.place_market

    def pm(side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and v.part is not None:
            qty, v.part = min(qty, v.part), None
        return orig(side, qty, cloid, reduce_only=reduce_only)
    v.place_market = pm
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    v.orders[t.stop_cloid]["qty"] = 0.01              # a partial trigger fill
    v.orders[t.stop_cloid]["status"] = "FILLED"
    assert v._true_position() == pytest.approx(0.42)
    for _ in range(2, 9):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert t.qty == pytest.approx(0.02) and "stop_residue" in _kinds(ex, n0)
    assert p.qty == 0.0 and "leg_partially_closed" in _kinds(ex, n0)
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == pytest.approx(0.02)
    # the residue's stop is re-armed once the pullback's record resolved
    # the divergence (stopless while it was ambiguous - paged each poll)
    assert t.stop_cloid and v.orders[t.stop_cloid]["status"] == "OPEN"


# ---------------------------------------------------------- paging and HL

def test_gate_r5_two_stuck_legs_log_once_per_ten_minutes_each(tmp_path, clock, pings):
    v = PollVenue(drop=99)
    ex, _ = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(90):                               # 30 min, both legs stuck
        _poll(ex, clock, target())
    k = _kinds(ex, n0)
    assert k.count("close_stuck") <= 10, k.count("close_stuck")
    assert len([m for m in pings if "close_stuck" in m]) <= 2
    assert len(v.sends) == 2 * (1 + mirror.CLOSE_NEVER_MAX)


def test_gate_r5_hl_position_refuses_a_response_without_positions():
    class Info:
        def __init__(self, st):
            self._st = st

        def user_state(self, addr):
            return self._st
    hv = HyperliquidVenue.__new__(HyperliquidVenue)
    hv.coin, hv.address = "BTC", "0xabc"
    hv.info = Info({})
    with pytest.raises(RuntimeError):
        hv.position()
    hv.info = Info({"marginSummary": {"accountValue": "1"}})
    with pytest.raises(RuntimeError):
        hv.position()
    hv.info = Info({"assetPositions": []})
    assert hv.position() == 0.0
    hv.info = Info({"assetPositions": [{"position": {"coin": "BTC", "szi": "-0.5"}}]})
    assert hv.position() == -0.5


# ----------------------------------------------- round-6 verifier follow-ups

def test_gate_r6_slow_partial_record_with_the_other_stop_resting_never_halts(
        tmp_path, clock):
    """What the deferral's "every other leg's stop resting" clause protects
    (the round-6 verifier found it unbound): the pullback's IOC fills 0.5
    of 0.9, its record is unusable for eight polls - longer than the
    close's settle window - and the trend's trail moved in the send poll
    so its stop maintenance corroborates every poll. The trend's exposure
    is accounted and protected (its stop reads OPEN), so the gap can only
    be the pullback's own partial: no halt; the partial books from the
    record, the remainder is re-closed, the trend keeps its stop."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 8 else None)
    v.part = 0.5
    orig = v.place_market

    def pm(side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and v.part is not None:
            qty, v.part = min(qty, v.part), None
        return orig(side, qty, cloid, reduce_only=reduce_only)
    v.place_market = pm
    ex, _ = _book(tmp_path, v)
    moved = _pos(side="L", stop=STOP * 1.01)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(10):
        _poll(ex, clock, target(trend=moved))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert "leg_partially_closed" in _kinds(ex, n0) and p.qty == 0.0
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert v.orders[t.stop_cloid]["status"] == "OPEN"
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == pytest.approx(TREND)
    assert len(_xs(v)) == 2 and "ledger_divergence" not in _kinds(ex, n0)


def test_gate_r6_both_stuck_each_legs_hand_close_books_on_its_own(tmp_path, clock, pings):
    """Both legs stuck (two rejected closes, retries spent). The stuck text
    prescribes a per-leg hand close; round 6's unconditional in-flight
    rule held one leg's hand close ambiguous because the OTHER stuck leg's
    ref was in flight. A stuck leg's ref is no witness (its exposure
    leaves only by hand): the pullback books on its own hand close, then
    the trend on its own."""
    v = PollVenue(drop=99)
    ex, _ = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(60):
        _poll(ex, clock, target())
    assert p.close_never_n > mirror.CLOSE_NEVER_MAX and t.close_never_n > mirror.CLOSE_NEVER_MAX
    v._add("MARKET", "SELL", PULL, "operator-close-pullback")
    for _ in range(3):
        _poll(ex, clock, target())
    assert p.qty == 0.0 and p.close_cloid is None and p.close_never_n == 0
    assert t.qty == pytest.approx(TREND) and t.close_cloid     # untouched
    v._add("MARKET", "SELL", TREND, "operator-close-trend")
    for _ in range(3):
        _poll(ex, clock, target())
    assert t.qty == 0.0 and t.close_cloid is None
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert ex.state.halted is None and len(v.sends) == 2 * (1 + mirror.CLOSE_NEVER_MAX)


def test_gate_r6_unreadable_other_entry_pages_a_distinct_red_past_the_hard_streak(
        tmp_path, clock, pings):
    """The trend's close is dropped; the pullback's resting maker entry
    reads UNKNOWN for a long time. The unmoved verdict waits (the entry
    could hide the close) - bounded only by that record: past the hard
    streak the wait is paged as its own RED naming the recovery; nothing
    is sent; when the entry reads again the verdict and retry follow."""
    v = PollVenue(drop=1)
    ex = mkexec(tmp_path, v, dry_run=False)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    t.qty = TREND
    _hold(v, TREND)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend, trend=_pos(side="L", stop=STOP)))
    clock.tick()
    entry = p.entry_cloid
    orig = v.order_status

    def ostat(cloid):
        if cloid == entry and 1 <= v.poll() <= 14:
            return dict(UNK)
        return orig(cloid)
    v.order_status = ostat
    n0 = len(ex.state.events)
    for _ in range(14):
        _poll(ex, clock, target(pull=pend))
        assert len(v.sends) == 1 and ex.state.halted is None
    k = _kinds(ex, n0)
    assert "close_blocked_by_other_leg" in k and "close_never_happened" not in k
    assert len([m for m in pings if "close_blocked_by_other_leg" in m]) == 1
    for _ in range(4):                                # the entry reads again
        _poll(ex, clock, target(pull=pend))
    assert t.qty == 0.0 and len(v.sends) == 2 and ex.state.halted is None
    assert _ledger_sum(ex) == pytest.approx(v._true_position())
