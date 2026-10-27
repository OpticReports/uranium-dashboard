"""Round-3 close-settlement gates (2026-10-27, docs/HALT_2026-10-07.md s3).

Two independent verifiers attacked the round-2 settle path with probes;
each probe is a gate here. What they bind:

- the position tiebreak reads THIS LEG'S OWN exposure (net minus the other
  legs' ledger, before and now), never a frozen net: another leg's stop
  fill absorbed in the window is not booked as this close, and the other
  leg's size is never orphaned on the venue (the BLOCKING finding);
- a full move books only when it holds on two polls (a stop reads OPEN in
  the instant it fires); a partial move never books from the position;
- a same-sign leg whose single close is in flight is attributed when the
  venue goes flat after the other leg's stop (the two-leg deadlock);
- a never-happened verdict binds the whole poll: no send, no stop re-arm;
- an affirmative CANCELLED/0 record must repeat on two tiebreak polls;
- the retry budget (close_never_n) belongs to one close cycle;
- close_stuck is rate-limited and its recovery text is right (a hand close
  alone recovers; adopt fits only a flat venue);
- an explicit zero in the send answer is not a booking.

Venues are POLL-indexed (answers keyed on the poll number since the send):
the fill watch and the _close_leg head also read order_status, which
consumes call-indexed scripts and made the round-2 comments wrong.
"""
import time

import pytest

import app.alerts as alerts
from app import mirror
from test_executor_gates import _hold, _pos, mkexec, target
from test_close_settle_gates import (Clock, SilentVenue, ResponseVenue, _book,
                                     _poll, _kinds, _xs, _healthy, PULL, TREND,
                                     STOP, POLL_S)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(mirror.time, "time", c)
    return c


class PollVenue(SilentVenue):
    """'-X' status answers `status_fn(poll, cloid)` ("UNKNOWN", "unknownOid"
    -> CANCELLED/0, (status, filled) or None = the truth); position() lags
    (the pre-send net) while `stale_fn(poll)`; `stop_fn(poll)` True makes
    every STOP read UNKNOWN. Poll 1 = the send poll. `drop`: the first n
    '-X' sends raise (never reach the venue) and read CANCELLED/0 after
    (unknownOid). `never_fill`: cloid prefixes whose '-X' orders rest
    unfilled forever. `raise_after`: the send raises after the venue filled
    it. `fills`: the fills endpoint shows the print."""

    def __init__(self, *a, status_fn=None, stale_fn=None, stop_fn=None,
                 drop=0, never_fill=(), raise_after=False, fills=False, **k):
        super().__init__(*a, **k)
        self.status_fn = status_fn or (lambda p, c: None)
        self.stale_fn = stale_fn or (lambda p: False)
        self.stop_fn = stop_fn or (lambda p: False)
        self.drop, self.never_fill = drop, tuple(never_fill)
        self.raise_after, self.fills = raise_after, fills
        self._t0, self._pre = None, None
        self.sends, self.dropped = [], []

    def poll(self):
        if self._t0 is None:
            return 0
        return int((time.time() - self._t0) / POLL_S) + 1

    def place_market(self, side, qty, cloid, reduce_only=False):
        if not cloid.endswith("-X"):
            return super().place_market(side, qty, cloid, reduce_only=reduce_only)
        if self._t0 is None:
            self._t0, self._pre = time.time(), self._true_position()
        self.sends.append((self.poll(), cloid, round(qty, 5)))
        if len(self.dropped) < self.drop:
            self.dropped.append(cloid)
            self.calls.append(("MARKET_DROPPED", side, round(qty, 5), cloid))
            raise RuntimeError("order rejected: rate limited")
        if self.never_fill and cloid.startswith(self.never_fill):
            self.orders[cloid] = {"type": "MARKET", "side": side, "qty": qty,
                                  "px": None, "status": "OPEN", "part": 0.0}
            self.calls.append(("MARKET", side, round(qty, 5), cloid))
            return None
        r = super().place_market(side, qty, cloid, reduce_only=reduce_only)
        if self.raise_after:
            raise RuntimeError("read timeout after send")
        return r

    def order_status(self, cloid):
        if cloid in self.dropped:
            return {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None}
        o = self.orders.get(cloid)
        if o and o["type"] == "STOP" and self.stop_fn(self.poll()):
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        if cloid.endswith("-X"):
            ans = self.status_fn(self.poll(), cloid)
            if ans == "UNKNOWN":
                return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
            if ans == "unknownOid":
                return {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None}
            if isinstance(ans, tuple):
                return {"status": ans[0], "filled_qty": ans[1], "avg_price": None}
        return super().order_status(cloid)

    def position(self):
        if self._pre is not None and self.stale_fn(self.poll()):
            return self._pre
        return super().position()

    def fill_pnl(self, cloid):
        if not self.fills:
            return None
        o = self.orders.get(cloid)
        if o and o["status"] == "FILLED" and o["type"] == "MARKET":
            return {"pnl": 0.0, "fee": 0.0, "qty": o["qty"],
                    "exit_px": o["px"] or self._mid}
        return None


def _book_sizes(tmp_path, v, pull, trend):
    ex = mkexec(tmp_path, v, dry_run=False)
    ex.state.legs["pullback"].qty = pull
    ex.state.legs["trend"].qty = trend
    _hold(v, pull + trend)
    trend_tl = _pos(side="L", stop=STOP)
    ex.step(target(pull=_pos(side="L", stop=STOP), trend=trend_tl))
    assert ex.state.halted is None and ex.state.legs["trend"].stop_cloid
    return ex, trend_tl


def _fire_trend_stop(v, ex):
    t = ex.state.legs["trend"]
    v.orders[t.stop_cloid]["status"] = "FILLED"


def _ledger_sum(ex):
    return sum(l.qty for l in ex.state.legs.values())


def _spy_sends(ex, v):
    """(poll_seq, cloid) of every '-X' send, and the poll_seq of every
    close_never_happened verdict."""
    sends, verdicts = [], []
    orig_pm, orig_ev = v.place_market, ex._event

    def pm(side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X"):
            sends.append((ex._poll_seq, cloid))
        return orig_pm(side, qty, cloid, reduce_only=reduce_only)

    def ev(level, kind, msg):
        if kind == "close_never_happened":
            verdicts.append(ex._poll_seq)
        return orig_ev(level, kind, msg)
    v.place_market, ex._event = pm, ev
    return sends, verdicts


# ------------------------------------------------ the baseline (BLOCKING)

@pytest.mark.parametrize("trend", [TREND, 0.003])
def test_gate_r3_other_legs_absorbed_stop_is_never_booked_as_this_close(
        tmp_path, clock, trend):
    """The close never reached the venue (the send raised; unknownOid
    after). One poll later the trend's stop fires and its own stop
    maintenance absorbs it. Round 3: the frozen-net tiebreak booked the
    trend's 0.03 as the pullback's partial fill after six polls, re-closed
    the 'remainder', and left the trend's size on the venue with a flat
    ledger, no stop and no halt (under the drift tolerance: no page at
    all). Now: the pullback's own exposure is unmoved, the verdict fires,
    the retry closes it, and the ledger equals the venue."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book_sizes(tmp_path, v, PULL, trend)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))          # send poll: rejected
    assert p.close_cloid and p.qty == PULL and p.stop_cloid is None
    _fire_trend_stop(v, ex)
    assert v._true_position() == pytest.approx(PULL)
    for _ in range(12):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
        assert "leg_partially_closed" not in _kinds(ex, n0), \
            "the trend's absorbed stop fill was booked as the pullback's close"
    k = _kinds(ex, n0)
    assert "stop_filled_on_venue" in k and t.qty == 0.0
    assert "close_never_happened" in k and "close_settled_by_position" not in k
    assert p.qty == 0.0 and p.close_cloid is None
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == pytest.approx(0.0)
    assert len(_xs(v)) == 1, _xs(v)                   # one real close; one dropped
    assert len(v.sends) == 2 and "netting_inconsistent" not in k


def test_gate_r3_equal_sizes_race_books_nothing_on_one_look(tmp_path, clock):
    """Sizes match. The trend's stop fires in the instant it still reads
    OPEN ('triggered') at the age-40 poll: the pullback's own exposure
    then reads as fully gone on ONE look. Round 3 booked the full close
    off that look; the trend's absorb then saw a ledger it could not
    attribute and halted LEDGER_DIVERGENCE in three polls (the 10-07
    shape by another door). Now: a full move books only when it holds on
    two polls; by the second the stop reads FILLED and is absorbed."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book_sizes(tmp_path, v, 0.5, 0.5)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))          # send poll: rejected
    _poll(ex, clock, target(trend=trend_tl))          # age 20
    _fire_trend_stop(v, ex)
    orig = v.order_status

    def triggered(cloid):                             # OPEN for the age-40 poll only
        if cloid == t.stop_cloid and v.poll() == 3:
            return {"status": "OPEN", "filled_qty": 0.0, "avg_price": None}
        return orig(cloid)
    v.order_status = triggered
    _poll(ex, clock, target(trend=trend_tl))          # age 40: one look
    assert p.close_cloid and p.qty == 0.5 and p.close_moved_polls == 1
    assert "close_settled_by_position" not in _kinds(ex, n0)
    _poll(ex, clock, target(trend=trend_tl))          # age 60: stop reads FILLED
    assert "stop_filled_on_venue" in _kinds(ex, n0) and t.qty == 0.0
    assert p.close_cloid and p.qty == 0.5, "booked off the other leg's fill"
    assert any("stop reads FILLED" in e["msg"] for e in ex.state.events[n0:]
               if e["kind"] == "close_unconfirmed")
    for _ in range(8):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    k = _kinds(ex, n0)
    assert "netting_inconsistent" not in k and "close_settled_by_position" not in k
    assert p.qty == 0.0 and _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert len(v.sends) == 2


def test_gate_r3_both_legs_exit_in_one_poll_book_each_their_own_fill(tmp_path, clock):
    """Both legs exit in the same poll: the trend's IOC fills, the
    pullback's rests unfilled. The pullback's record is unusable
    throughout; the trend's answers from the next poll. Round 3 booked the
    trend's 0.03 twice (its own close, then the pullback's 'partial') and
    the ledger drifted 0.03 under the venue. Now the pullback's exposure
    is unmoved and its retries are bounded; the ledger equals the venue."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if c.startswith("P-") else None,
                  never_fill=("P-",))
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(24):
        _poll(ex, clock, target())                    # both legs flat on the engine
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
        assert "leg_partially_closed" not in _kinds(ex, n0)
    k = _kinds(ex, n0)
    assert t.qty == 0.0 and k.count("leg_closed") == 1
    assert p.qty == PULL and v._true_position() == pytest.approx(PULL)
    assert _ledger_sum(ex) == pytest.approx(v._true_position())
    assert "close_stuck" in k and "netting_inconsistent" not in k


def test_gate_r3_venue_flat_after_other_legs_stop_attributes_the_single_close(
        tmp_path, clock):
    """The pullback's close FILLED but its record is unusable; the trend's
    stop fires one poll later. Round 3 deadlocked: the pullback's tiebreak
    kept its ref because the trend's stop read FILLED, and the trend's
    absorb returned None every poll because a same-sign leg held 0.9 with
    no stop - netting_inconsistent x3, LEDGER_DIVERGENCE on a venue that
    did exactly what was asked. Now a flat venue attributes the in-flight
    single close and both legs book."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN")
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))          # filled; answer unusable
    assert p.close_cloid and p.qty == PULL
    _fire_trend_stop(v, ex)
    assert v._true_position() == pytest.approx(0.0)
    for _ in range(6):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-8:]
    k = _kinds(ex, n0)
    assert p.qty == 0.0 and p.close_cloid is None and t.qty == 0.0
    assert "netting_inconsistent" not in k and len(_xs(v)) == 1
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert any("venue flat after trend's stop" in e["msg"] for e in closed), closed


# ------------------------------------------------- the verdict binds the poll

@pytest.mark.parametrize("branch", ["engine_flat", "exit_flag"])
def test_gate_r3_verdict_poll_never_sends(tmp_path, clock, branch):
    """The never-happened verdict is rendered by the top-of-leg settle in
    _sync_leg, whose return is discarded; round 3's `return False` bound
    only the head-guard caller, so _close_leg sent a new close in the
    verdict poll against the very read just judged unmoved. Now the
    retry goes out on the NEXT poll, after a fresh corroboration."""
    v = PollVenue(drop=1)
    pull_tl = _pos(side="L", stop=STOP) if branch == "exit_flag" else None
    ex, trend_tl = _book(tmp_path, v, pull_tl=pull_tl)
    sends, verdicts = _spy_sends(ex, v)
    tgt = (target(pull=_pos(side="L", stop=STOP, flag="SIGNAL"), trend=trend_tl)
           if branch == "exit_flag" else target(trend=trend_tl))
    n0 = len(ex.state.events)
    for _ in range(8):
        _poll(ex, clock, tgt)
    assert verdicts and len(sends) == 2, (verdicts, sends)
    assert sends[1][0] == verdicts[0] + 1, "re-sent inside the verdict poll"
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert p.qty == 0.0 and ex.state.halted is None
    assert "netting_inconsistent" not in _kinds(ex, n0)
    assert len(_xs(v)) == 1 and v._true_position() == pytest.approx(TREND)
    assert t.qty == pytest.approx(TREND) and t.stop_cloid


def test_gate_r3_one_affirmative_read_does_not_render_the_verdict(tmp_path, clock):
    """Record UNKNOWN on every poll but the fourth (one CANCELLED/0 read at
    age 60), position lagging through poll 5. Round 3: that single
    affirmative read plus two unmoved polls rendered close_never_happened
    and the retry was clamped onto the trend. Now the affirmative read
    must repeat on two tiebreak polls; the fresh position then books the
    close on two looks and nothing else is sent."""
    v = PollVenue(status_fn=lambda p, c: "unknownOid" if p == 4 else "UNKNOWN",
                  stale_fn=lambda p: p <= 5)
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(5):
        _poll(ex, clock, target(trend=trend_tl))
        assert len(v.sends) == 1 and "close_never_happened" not in _kinds(ex, n0)
        assert p.close_cloid and p.qty == PULL
    _poll(ex, clock, target(trend=trend_tl))          # poll 6: fresh, first look
    _poll(ex, clock, target(trend=trend_tl))          # poll 7: second look
    assert p.qty == 0.0 and p.close_cloid is None
    assert "close_settled_by_position" in _kinds(ex, n0)
    _healthy(ex, v, n0)


def test_gate_r3_hard_streak_needs_the_position_unmoved_twice(tmp_path, clock):
    """The hard streak (6 unusable polls) clears the ref only with the
    position unmoved on two tiebreak polls. The trend's stop reads
    UNKNOWN on polls 3-5 (ambiguous: nothing is counted), so the first
    unmoved look is poll 6 - no verdict there, one on poll 7."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN", never_fill=("P-",),
                  stop_fn=lambda p: 3 <= p <= 5)
    ex, trend_tl = _book(tmp_path, v)
    sends, verdicts = _spy_sends(ex, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(6):
        _poll(ex, clock, target(trend=trend_tl))
    assert p.close_unknown_polls == 6 and p.close_unmoved_polls == 1
    assert not verdicts and p.close_cloid
    _poll(ex, clock, target(trend=trend_tl))          # poll 7: unmoved twice
    assert verdicts == [ex._poll_seq] and p.close_cloid is None
    assert len(sends) == 1
    _poll(ex, clock, target(trend=trend_tl))          # poll 8: the retry
    assert len(sends) == 2 and ex.state.halted is None


def test_gate_r3_partial_move_never_books_from_the_position(tmp_path, clock):
    """A genuine partial IOC whose record never answers: the position
    shows half gone. Round 3 booked that after six polls as a 'bounded
    tiebreak'; a partial move is also what another leg's unbooked change
    looks like. Now the ref is kept, loudly, until the record or the
    venue's fills answer - and when they do, it books right."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 10 else None)
    v.part = 0.5
    orig = v.place_market

    def pm(side, qty, cloid, reduce_only=False):
        if cloid.endswith("-X") and v.part is not None:
            qty, v.part = min(qty, v.part), None
        return orig(side, qty, cloid, reduce_only=reduce_only)
    v.place_market = pm
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(10):
        _poll(ex, clock, target(trend=trend_tl))
        assert p.close_cloid and p.qty == PULL and len(v.sends) == 1
        assert ex.state.halted is None
    assert "leg_partially_closed" not in _kinds(ex, n0)
    assert "close_settled_by_position" not in _kinds(ex, n0)
    assert any("partial move is ambiguous" in e["msg"] for e in ex.state.events[n0:])
    _poll(ex, clock, target(trend=trend_tl))          # poll 11: the record answers
    assert "leg_partially_closed" in _kinds(ex, n0)   # 0.5 booked, the remainder
    assert p.qty == 0.0 and p.close_cloid is None     # re-closed after a fresh look
    _healthy(ex, v, n0, xs=2)


def test_gate_r3_fills_endpoint_books_before_any_position_read(tmp_path, clock):
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN", stale_fn=lambda p: True,
                  fills=True)
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(3):                                # ages 0, 20, 40
        _poll(ex, clock, target(trend=trend_tl))
    assert p.qty == 0.0 and p.close_cloid is None
    closed = [e for e in ex.state.events[n0:] if e["kind"] == "leg_closed"]
    assert len(closed) == 1 and "via venue fills" in closed[0]["msg"]
    assert "close_settled_by_position" not in _kinds(ex, n0)
    _healthy(ex, v, n0)


def test_gate_r3_raise_path_counts_the_send_poll(tmp_path, clock):
    v = PollVenue(drop=1)
    ex, trend_tl = _book(tmp_path, v)
    _poll(ex, clock, target(trend=trend_tl))
    p = ex.state.legs["pullback"]
    assert p.close_cloid and p.close_unknown_polls == 1


# ------------------------------------------------- close_stuck and recovery

def test_gate_r3_close_stuck_pages_once_per_half_hour(tmp_path, clock, monkeypatch):
    pings = []
    monkeypatch.setattr(alerts, "send", lambda m: pings.append(m))
    v = PollVenue(drop=99)
    ex, trend_tl = _book(tmp_path, v)
    n0 = len(ex.state.events)
    for _ in range(40):                               # 13 min
        _poll(ex, clock, target(trend=trend_tl))
    k = _kinds(ex, n0)
    assert k.count("close_stuck") >= 10, "the event log keeps every line"
    assert len([m for m in pings if "close_stuck" in m]) == 1
    clock.tick(1800)
    _poll(ex, clock, target(trend=trend_tl))
    assert len([m for m in pings if "close_stuck" in m]) == 2
    assert len(v.sends) == 1 + mirror.CLOSE_NEVER_MAX and ex.state.halted is None


def test_gate_r3_hand_close_recovers_close_stuck_and_resets_the_budget(
        tmp_path, clock):
    v = PollVenue(drop=99)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target(trend=trend_tl))
    assert "close_stuck" in _kinds(ex, n0) and p.close_never_n > mirror.CLOSE_NEVER_MAX
    assert p.qty == PULL and p.close_cloid and p.stop_cloid is None
    stuck = [e for e in ex.state.events[n0:] if e["kind"] == "close_stuck"][-1]["msg"]
    assert "no /resume needed" in stuck and "FLAT venue" in stuck
    v._add("MARKET", "SELL", PULL, "operator-close")  # the documented recovery
    n1 = len(ex.state.events)
    for _ in range(2):                                # two looks
        _poll(ex, clock, target(trend=trend_tl))
    assert p.qty == 0.0 and p.close_cloid is None and p.close_never_n == 0
    assert "close_settled_by_position" in _kinds(ex, n1)
    assert ex.state.halted is None and not ex._boot_mismatch
    assert t.qty == pytest.approx(TREND) and t.stop_cloid
    assert len(v.sends) == 1 + mirror.CLOSE_NEVER_MAX


def test_gate_r3_adopt_on_a_flat_venue_resets_the_budget_for_the_next_trade(
        tmp_path, clock):
    """Round 3 persisted close_never_n past an adopt: the next trade on
    the leg whose close was rejected once went straight to close_stuck
    with zero retries. And /resume?adopt_venue=1 on a running two-leg book
    refused with 'the HALT STANDS' while nothing was halted."""
    v = PollVenue(drop=99)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target(trend=trend_tl))
    assert "close_stuck" in _kinds(ex, n0)
    n1 = len(ex.state.events)
    assert ex.resume(adopt_venue=True) is False       # the trend is still held
    refused = [e for e in ex.state.events[n1:] if e["kind"] == "adopt_venue_partial"]
    assert refused and "HALT STANDS" not in refused[0]["msg"]
    assert "FLAT venue" in refused[0]["msg"] and ex.state.halted is None
    v._add("MARKET", "SELL", PULL + TREND, "operator-flatten")
    n2 = len(ex.state.events)
    assert ex.resume(adopt_venue=True) is True
    assert p.close_never_n == 0 and p.qty == 0.0 and t.qty == 0.0
    assert "resume" not in _kinds(ex, n2), "nothing was halted"
    # a new trade later, its close rejected: the full retry budget again
    p.qty = PULL
    _hold(v, PULL, cloid="seed2")
    v.drop = 99
    ex.step(target(pull=_pos(side="L", stop=STOP, entry_ts=1_700_100_000)))
    clock.tick()
    assert p.stop_cloid
    n3 = len(ex.state.events)
    sends0 = len(v.sends)
    for _ in range(40):
        _poll(ex, clock, target())
    assert len(v.sends) - sends0 == 1 + mirror.CLOSE_NEVER_MAX, _kinds(ex, n3)[:12]
    assert "close_stuck" in _kinds(ex, n3) and ex.state.halted is None


# ----------------------------------------------------------- send answers

def test_gate_r3_explicit_zero_send_answer_is_not_a_booking(tmp_path, clock):
    """A response reading filled 0 (the fake's NOOP shape; not known to
    occur on HL, whose rejects raise) used to clear the ref with the leg
    unchanged and re-send every poll with no RED and no bound."""
    class ZeroAnswer(ResponseVenue):
        def place_market(self, side, qty, cloid, reduce_only=False):
            if cloid.endswith("-X"):
                self.calls.append(("MARKET_NOOP", side, round(qty, 5), cloid))
                return {"filled_qty": 0.0, "avg_px": None, "resting": False}
            return super().place_market(side, qty, cloid, reduce_only=reduce_only)
    v = ZeroAnswer()
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None
    k = _kinds(ex, n0)
    noops = [c for c in v.calls if c[0] == "MARKET_NOOP"]
    assert len(noops) == 1 + mirror.CLOSE_NEVER_MAX, len(noops)
    assert "leg_partially_closed" not in k and p.qty == PULL
    assert "close_stuck" in k
    assert [e for e in ex.state.events[n0:] if e["level"] == "RED"]


def test_gate_r3_blind_venue_names_a_stopless_residue(tmp_path, clock):
    v = ResponseVenue(part=0.5)
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    _poll(ex, clock, target(trend=trend_tl))
    assert p.qty == pytest.approx(PULL - 0.5) and p.stop_cloid is None
    n0 = len(ex.state.events)

    def blind():
        raise RuntimeError("503")
    v.position = blind
    _poll(ex, clock, target(trend=trend_tl))
    ev = [e for e in ex.state.events[n0:] if e["kind"] == "close_backing_blind"]
    assert ev and "STOPLESS" in ev[0]["msg"] and "stays armed" not in ev[0]["msg"]


def test_gate_r3_order_status_outage_keeps_the_ref_for_its_duration(tmp_path, clock):
    """The close FILLED; from poll 2 every order read (the close's record
    AND the trend's stop) is UNKNOWN for ten polls. The documented bound:
    the ref is kept for the outage - no halt, no second close, no booking
    off one source - and it books on the first poll after."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if 2 <= p <= 11 else None,
                  stop_fn=lambda p: 2 <= p <= 11)
    v.status_fn_send = None
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    # the send poll's record is unusable too (poll 1)
    v.status_fn = lambda p_, c: "UNKNOWN" if p_ <= 11 else None
    for _ in range(11):
        _poll(ex, clock, target(trend=trend_tl))
        assert p.close_cloid and p.qty == PULL and len(v.sends) == 1
        assert ex.state.halted is None
    _poll(ex, clock, target(trend=trend_tl))          # poll 12: the record answers
    assert p.qty == 0.0 and p.close_cloid is None
    _healthy(ex, v, n0)
