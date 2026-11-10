"""Round-4 close-settlement gates (2026-10-27, docs/HALT_2026-10-07.md s3).

Two independent verifiers attacked the round-4 tree (3eac6f7). What these
gates bind:

- the position is read FIRST and an unmoved own exposure is unambiguous:
  two closes rejected in one poll no longer hold each other ambiguous for
  ever (both legs stopless, no retry, no close_stuck, a hand flatten never
  booked); the ambiguity rules apply to a MOVE only, and what they protect
  (the other leg's unbooked fill) still holds;
- the three-poll netting grace does not outlast the close's two looks when
  the other leg's trail moved in the send poll (a REGRESSION that halted a
  healthy book and flattened the leg the engine still held);
- a full move is not booked against an affirmative CANCELLED/0 record
  while the leg is not stuck (the other leg's stop read OPEN on two polls);
- an own exposure that reads LARGER than at the send (another leg's maker
  fill unbooked in the same status outage; a retry sent off a lagging
  node) is ambiguous, never "unmoved";
- a genuine partial IOC followed by the other leg's stop does not halt;
- the verdict poll never re-arms a stop (exit-flag branch); the retry
  budget resets after a halt flatten; boot restarts the per-process
  counters and the poll-count rule holds after a restart; looks must be
  consecutive; sub-lot dust does not defeat the flat-venue attribution; a
  ref with no baseline never books from the position; close_stuck's log
  text is stable and says the exact size.
"""
import pytest

import app.alerts as alerts
from app import mirror
from test_executor_gates import _hold, _pos, mkexec, target, NOW
from test_close_settle_gates import (Clock, _book, _poll, _kinds, _xs, _healthy,
                                     PULL, TREND, STOP)
from test_close_settle_gates_r3 import (PollVenue, _book_sizes, _fire_trend_stop,
                                        _ledger_sum, _spy_sends)

UNK = {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
OPENR = {"status": "OPEN", "filled_qty": 0.0, "avg_price": None}


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


# -------------------------------------------- two refs in flight (BLOCKING)

@pytest.mark.parametrize("record", ["unknownOid", "UNKNOWN"])
def test_gate_r4_two_rejected_closes_in_one_poll_are_bounded_and_recoverable(
        tmp_path, clock, pings, record):
    """Both legs exit in one poll and both sends raise (one rate-limit
    burst), unknownOid after. Round 4: each leg's tiebreak saw the other's
    ref and returned 'ambiguous' before any position read - no verdict,
    no retry, no close_stuck, both legs stopless for ever, and a hand
    flatten was never booked. Now: an unmoved own exposure is unambiguous,
    each leg runs its bounded retries to close_stuck, and a hand flatten
    books both on two looks."""
    v = PollVenue(drop=99, dropped_reads=record)
    ex, _ = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(60):
        _poll(ex, clock, target())
        assert ex.state.halted is None
    k = _kinds(ex, n0)
    assert k.count("close_stuck") >= 2 and k.count("close_never_happened") >= 6
    per_leg = {c[:2] for _, c, _ in v.sends}
    assert len([s for s in v.sends if s[1].startswith("P-")]) == 1 + mirror.CLOSE_NEVER_MAX
    assert len([s for s in v.sends if s[1].startswith("T-")]) == 1 + mirror.CLOSE_NEVER_MAX
    assert p.qty == PULL and t.qty == pytest.approx(TREND) and per_leg == {"P-", "T-"}
    assert p.close_cloid and t.close_cloid
    v._add("MARKET", "SELL", PULL + TREND, "operator-flatten")   # the documented recovery
    n1 = len(ex.state.events)
    for _ in range(3):
        _poll(ex, clock, target())
    assert p.qty == 0.0 and t.qty == 0.0 and p.close_cloid is None and t.close_cloid is None
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert p.close_never_n == 0 and t.close_never_n == 0 and ex.state.halted is None
    assert _kinds(ex, n1).count("close_settled_by_position") == 2


@pytest.mark.parametrize("dropped_reads", ["unknownOid", "UNKNOWN"])
def test_gate_r4_other_legs_unbooked_close_fill_is_never_booked_as_this_close(
        tmp_path, clock, dropped_reads):
    """What the in-flight ambiguity protects: equal sizes, both exit in one
    poll, the trend's IOC fills (record UNKNOWN for ten polls), the
    pullback's send is dropped (its record reads CANCELLED/0, or nothing
    usable at all). The pullback's exposure reads fully gone (the trend's
    unbooked fill) but must NOT book; once the trend is booked the
    pullback is unmoved, verdicts and its retry fills."""
    v = PollVenue(drop=1, status_fn=lambda p, c: "UNKNOWN" if p <= 10 else None,
                  dropped_reads=dropped_reads)
    ex, _ = _book_sizes(tmp_path, v, 0.5, 0.5)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target())
    first = p.close_cloid                             # the dropped send
    assert first and t.close_cloid
    for i in range(2, 19):
        _poll(ex, clock, target())
        assert ex.state.halted is None
        assert not any(first in e["msg"] for e in ex.state.events[n0:]
                       if e["kind"] == "close_settled_by_position"), \
            "the trend's unbooked fill was booked as the pullback's close"
    # (the trend's own close, which really filled, books from the position
    # on two looks: the pullback's record affirmatively never traded, so it
    # cannot explain the trend's move; the pullback is then unmoved,
    # verdicts, and its retry fills - booked from the position too once
    # the venue is flat, which is right)
    assert t.qty == 0.0 and p.qty == 0.0
    assert "close_never_happened" in _kinds(ex, n0)
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert len(_xs(v)) == 2 and "netting_inconsistent" not in _kinds(ex, n0)


# ---------------------------------------------- the grace vs the two looks

def test_gate_r4_netting_grace_does_not_outlast_the_second_look(tmp_path, clock):
    """REGRESSION in round 4: the close FILLED, its record reads UNKNOWN
    for six polls, no fills endpoint, the position is fresh, and the
    trend's trail moved >5bp in the send poll. The trend's stop
    maintenance corroborated each poll, read the unbooked fill as a
    divergence and spent the three-poll grace before the pullback's
    second look: LEDGER_DIVERGENCE on a venue that did as asked, and the
    halt flattened the trend. Now the gap that a settling single close
    explains is not counted toward the halt."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 6 else None)
    ex, _ = _book(tmp_path, v)
    moved = _pos(side="L", stop=STOP * 1.01)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(6):
        _poll(ex, clock, target(trend=moved))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert p.qty == 0.0 and p.close_cloid is None
    assert "close_settled_by_position" in _kinds(ex, n0)
    assert "ledger_divergence" not in _kinds(ex, n0)
    assert t.qty == pytest.approx(TREND) and t.stop_cloid and len(_xs(v)) == 1
    assert v._true_position() == pytest.approx(TREND)


# ---------------------------------------------------- the affirmative record

def test_gate_r4_full_move_is_not_booked_against_an_affirmative_record(tmp_path, clock):
    """Equal sizes; the pullback's send never reached the venue (record
    CANCELLED/0); the trend's stop fires at age 20 and its record reads
    OPEN ('triggered') on the two tiebreak polls 3 and 4 (a slow node).
    Round 4 booked the trend's fill as the pullback's close on the second
    look and the trend's absorb then halted. Now an affirmative record
    beats the position inference while the leg is not stuck."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book_sizes(tmp_path, v, 0.5, 0.5)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    _poll(ex, clock, target(trend=trend_tl))
    _fire_trend_stop(v, ex)
    orig = v.order_status

    def triggered(cloid):
        if cloid == t.stop_cloid and v.poll() in (3, 4):
            return dict(OPENR)
        return orig(cloid)
    v.order_status = triggered
    for _ in range(12):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
        assert "close_settled_by_position" not in _kinds(ex, n0)
    assert t.qty == 0.0 and p.qty == 0.0
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert len(v.sends) == 2 and "netting_inconsistent" not in _kinds(ex, n0)


# -------------------------------------------- an exposure that reads larger

def test_gate_r4_other_legs_unbooked_maker_fill_never_masks_this_close(tmp_path, clock):
    """The trend alone holds 0.03 with its stop; the pullback's maker
    entry rests. The trend exits: its IOC fills, its record reads UNKNOWN
    then unknownOid; in the same outage the pullback's entry FILLS on the
    venue with its status unreadable (unbooked). Round 4 read the trend's
    exposure as 'unmoved' (the increase masked the fill), rendered
    close_never_happened and the retry sold 0.03 of the PULLBACK's
    exposure. Now a larger-than-at-send exposure is ambiguous and the
    entry's unreadable status keeps the ref; once readable, the entry is
    booked and the close books on two looks."""
    v = PollVenue(status_fn=lambda p, c: ("unknownOid" if 3 <= p <= 11 else
                                           "UNKNOWN" if p < 3 else None))
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
    v.orders[entry]["status"] = "FILLED"              # the maker fills, unbooked
    for _ in range(8):                                # polls 2-9: the outage
        _poll(ex, clock, target(pull=pend))
        assert len(v.sends) == 1, "a retry was sent off a masked close"
        assert "close_never_happened" not in _kinds(ex, n0)
        assert ex.state.halted is None
    for _ in range(2):                                # polls 10-11: entry readable,
        _poll(ex, clock, target(pull=pend))           # the record still lies
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
        assert len(v.sends) == 1 and t.close_cloid    # an affirmative record
    assert "entry_filled_early" in _kinds(ex, n0)     # holds a moved exposure
    for _ in range(2):                                # poll 12: the record answers
        _poll(ex, clock, target(pull=pend))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert t.qty == 0.0 and t.close_cloid is None
    assert p.qty == pytest.approx(v.orders[entry]["qty"])
    assert _ledger_sum(ex) == pytest.approx(v._true_position())
    assert len(v.sends) == 1 and "ledger_divergence" not in _kinds(ex, n0)


def test_gate_r4_retry_off_a_lagging_node_never_books_a_full_move(tmp_path, clock):
    """The lagging-node residual's second door: record UNKNOWN; the
    position lags through the verdict (poll 6) and is fresh from poll 8.
    The retry (poll 7) is clamped by the venue onto the trend's 0.03;
    round 4 then read a FULL 0.9 move off the stale baseline on two fresh
    looks and booked it, leaving a phantom trend leg and no halt. Now an
    exposure that reads beyond the ledger is ambiguous; when the retry's
    record answers it books its 0.03 as a partial and the divergence is
    caught by the halt - the documented end state."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 9 else None,
                  stale_fn=lambda p: p <= 7)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(14):
        _poll(ex, clock, target(trend=trend_tl))
        booked = [e for e in ex.state.events[n0:] if e["kind"] == "close_settled_by_position"]
        assert not any("0.9" in e["msg"].split("moved")[-1][:12] for e in booked), booked
        if ex.state.halted:
            break
    assert "leg_closed" not in [k for k in _kinds(ex, n0)] or ex.state.halted
    assert ex.state.halted == "LEDGER_DIVERGENCE" or \
        _ledger_sum(ex) == pytest.approx(v._true_position())


# ---------------------------------------- partial close + the other's stop

def test_gate_r4_partial_close_then_other_legs_stop_does_not_halt(tmp_path, clock):
    """A genuine partial IOC (0.5 of 0.9), record unusable, then the
    trend's stop fires: the venue nets 0.4 (the pullback's remainder).
    Round 4's absorb found d_new < 0, returned None every poll and halted
    LEDGER_DIVERGENCE on a venue that did as asked. Now the trend books
    flat, the pullback's ref is held as a partial move and books from its
    record when it answers."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN" if p <= 12 else None)
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
    _fire_trend_stop(v, ex)
    assert v._true_position() == pytest.approx(0.4)
    for _ in range(11):                               # polls 2-12
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
        assert "ledger_divergence" not in _kinds(ex, n0)
    assert t.qty == 0.0 and "stop_filled_on_venue" in _kinds(ex, n0)
    assert p.qty == PULL and p.close_cloid
    _poll(ex, clock, target(trend=trend_tl))          # poll 13: the record answers
    assert "leg_partially_closed" in _kinds(ex, n0)
    assert p.qty == 0.0 and ex.state.halted is None   # remainder re-closed
    assert _ledger_sum(ex) == pytest.approx(v._true_position()) == 0.0
    assert len(_xs(v)) == 2


def test_gate_r4_sub_lot_dust_does_not_defeat_the_flat_venue_attribution(tmp_path, clock):
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN", mult=1e-5)
    ex = mkexec(tmp_path, v, dry_run=False)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    p.qty, t.qty = 0.900004, TREND
    _hold(v, 0.900004 + TREND)
    trend_tl = _pos(side="L", stop=STOP)
    ex.step(target(pull=_pos(side="L", stop=STOP), trend=trend_tl))
    clock.tick()
    assert t.stop_cloid
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    assert p.close_qty == pytest.approx(0.9) and p.close_cloid
    _fire_trend_stop(v, ex)
    for _ in range(6):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None, _kinds(ex, n0)[-6:]
    assert p.qty == 0.0 and t.qty == 0.0 and p.close_cloid is None
    assert "netting_inconsistent" not in _kinds(ex, n0)


# ------------------------------------------------ the unpinned round-4 rules

def test_gate_r4_verdict_poll_never_rearms_the_stop_on_the_exit_flag_branch(
        tmp_path, clock, pings):
    """Written by the round-4 verifier B as the gate that kills the
    _maintain_stop verdict-guard mutant."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book(tmp_path, v, pull_tl=_pos(side="L", stop=STOP))
    sends, verdicts = _spy_sends(ex, v)
    stops = []
    orig_ps = v.place_stop

    def ps(side, qty, trigger_px, cloid):
        if cloid.startswith("P-"):
            stops.append((ex._poll_seq, cloid))
        return orig_ps(side, qty, trigger_px, cloid)
    v.place_stop = ps
    tgt = target(pull=_pos(side="L", stop=STOP, flag="SIGNAL"), trend=trend_tl)
    for _ in range(8):
        _poll(ex, clock, tgt)
    assert verdicts, "no verdict rendered"
    assert not any(s[0] == verdicts[0] for s in stops), "a stop was re-armed in the verdict poll"
    assert len(sends) == 2 and sends[1][0] == verdicts[0] + 1


def test_gate_r4_halt_flatten_resets_the_retry_budget_for_the_next_trade(
        tmp_path, clock, pings):
    """close_never_n belongs to one close cycle: a leg taken flat by the
    halt flatten starts the next trade with its retries intact."""
    v = PollVenue(drop=99)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target(trend=trend_tl))
    assert "close_stuck" in _kinds(ex, n0) and p.close_never_n > mirror.CLOSE_NEVER_MAX
    v.drop = 0                                        # the venue takes orders again
    ex.halt("KILL", "operator")
    assert p.qty == 0.0 and t.qty == 0.0 and ex.state.halted == "KILL"
    assert abs(v._true_position()) < 1e-9
    assert ex.resume() is True and ex.state.halted is None
    _poll(ex, clock, target())                        # a flat leg resets the budget
    assert p.close_never_n == 0
    p.qty = PULL
    _hold(v, PULL, cloid="seed2")
    ex.step(target(pull=_pos(side="L", stop=STOP, entry_ts=NOW + 14_400)))
    clock.tick()
    assert p.stop_cloid
    v.drop, v.dropped = 99, []
    sends0 = len(v.sends)
    n1 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target())
    assert len(v.sends) - sends0 == 1 + mirror.CLOSE_NEVER_MAX, _kinds(ex, n1)[:10]


def test_gate_r4_restart_resets_the_looks_and_keeps_the_poll_count_rule(tmp_path, clock):
    """A ref persisted mid-window (sent 60 s ago, one look already
    counted): boot resets the per-process counters, the boot settle
    counts as ONE poll and takes no look (age alone is not enough), the
    next poll looks once, the one after books."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN")
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    for _ in range(3):                                # send, age 20, age 40 (look 1)
        _poll(ex, clock, target(trend=trend_tl))
    assert p.close_cloid and p.close_moved_polls == 1 and p.close_unknown_polls == 3
    ex2 = mkexec(tmp_path, v, dry_run=False)          # restart at age 60
    p2 = ex2.state.legs["pullback"]
    assert p2.close_cloid and p2.qty == PULL, "boot booked off age alone"
    assert p2.close_unknown_polls == 1 and p2.close_moved_polls == 0
    assert p2.close_affirm_polls == 0 and p2.close_verdict_seq == -1
    _poll(ex2, clock, target(trend=trend_tl))        # look 1 again
    assert p2.close_cloid and p2.close_moved_polls == 1
    _poll(ex2, clock, target(trend=trend_tl))        # look 2: booked
    assert p2.qty == 0.0 and p2.close_cloid is None
    assert len(_xs(v)) == 1 and ex2.state.halted is None


def test_gate_r4_looks_must_be_consecutive(tmp_path, clock):
    """Fresh (look 1), stale (unmoved: the look count resets), fresh
    (look 1 again), fresh (look 2: booked)."""
    v = PollVenue(status_fn=lambda p, c: "UNKNOWN", stale_fn=lambda p: p == 4)
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(3):
        _poll(ex, clock, target(trend=trend_tl))      # poll 3: look 1
    assert p.close_moved_polls == 1
    _poll(ex, clock, target(trend=trend_tl))          # poll 4: stale, unmoved
    assert p.close_moved_polls == 0 and p.close_cloid
    _poll(ex, clock, target(trend=trend_tl))          # poll 5: look 1 again
    assert p.close_moved_polls == 1 and p.close_cloid and p.qty == PULL
    assert p.close_unmoved_polls == 0                 # a full move resets the unmoved count
    _poll(ex, clock, target(trend=trend_tl))          # poll 6: look 2
    assert p.qty == 0.0 and p.close_cloid is None
    _healthy(ex, v, n0)


def test_gate_r4_a_ref_without_a_baseline_never_books_from_the_position(tmp_path, clock):
    """A ref persisted by a build before close_others_before existed, whose
    send never reached the venue; the trend's stop fires and is absorbed.
    Round 4's fallback guessed the baseline and booked the trend's fill as
    this close (the round-3 fault again). Now the position tiebreak is off
    for it: no booking, no retry, a RED naming the recovery; a hand flatten
    plus adopt cleans it."""
    v = PollVenue(drop=1)
    ex, trend_tl = _book(tmp_path, v)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    n0 = len(ex.state.events)
    _poll(ex, clock, target(trend=trend_tl))
    p.close_others_before = None                      # the old state file
    _fire_trend_stop(v, ex)
    for _ in range(12):
        _poll(ex, clock, target(trend=trend_tl))
        assert ex.state.halted is None
    k = _kinds(ex, n0)
    assert "close_settled_by_position" not in k and "leg_partially_closed" not in k
    assert "close_never_happened" not in k and len(v.sends) == 1
    assert p.close_cloid and p.qty == PULL and t.qty == 0.0
    assert any("no baseline" in e["msg"] for e in ex.state.events[n0:])
    v._add("MARKET", "SELL", PULL, "operator-flatten")
    assert ex.resume(adopt_venue=True) is True
    assert p.qty == 0.0 and p.close_cloid is None and ex.state.halted is None


def test_gate_r4_stuck_text_names_the_exact_size_and_a_partial_hand_close_is_held(
        tmp_path, clock, pings):
    v = PollVenue(drop=99)
    ex, trend_tl = _book(tmp_path, v)
    p = ex.state.legs["pullback"]
    n0 = len(ex.state.events)
    for _ in range(40):
        _poll(ex, clock, target(trend=trend_tl))
    stuck = [e for e in ex.state.events[n0:] if e["kind"] == "close_stuck"]
    assert stuck and f"exactly {PULL}" in stuck[0]["msg"]
    v._add("MARKET", "SELL", 0.5, "operator-close-half")
    n1 = len(ex.state.events)
    for _ in range(3):
        _poll(ex, clock, target(trend=trend_tl))
    assert p.qty == PULL and p.close_cloid               # held as a partial move
    assert any("partial move is ambiguous" in e["msg"] for e in ex.state.events[n1:])
    v._add("MARKET", "SELL", PULL - 0.5, "operator-close-rest")
    for _ in range(3):
        _poll(ex, clock, target(trend=trend_tl))
    assert p.qty == 0.0 and p.close_cloid is None and p.close_never_n == 0
    assert ex.state.halted is None
