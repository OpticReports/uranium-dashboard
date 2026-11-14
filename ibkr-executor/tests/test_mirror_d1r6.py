"""D1 round 6 - follow-ups to the K5 replacement schedule (2026-11-13): records, two wordings, pins.

Round 5's two independent verifiers found no BLOCKING or SERIOUS defect in the doubling schedule; both found the same
MINOR trade-off - a LATE connect-time open-orders answer is taken as LOST - and two NOTEs in what the operator is told.
This round changes no connection or trading behaviour: when sessions are dropped, connected or replaced, the schedule,
the backoff and every order path are as on 33850e01. ib_adapter.py gains records (_unsynced_replace_interval,
UNSYNCED_REPLACE_MAX_S), the recovery notice's words (_recovered) and the DOWN page's count (_unsynced_sessions);
service.py a record of the /kill alert's measured length next to MIRROR_KILL_BOUND.

Everything but part W runs on the simulated clock: test_mirror_d1r4's part-M rig, the REAL MirrorManager driving the
REAL IBAdapter over PendingIB at production values, the service loop modelled (the book's tick, the keepalive, then
park next_wait(), floored at 0.5 s, at most poll_seconds = 300 s).

  P  PINS (twins: pass on 33850e01 and after; they pin round 5's lost-versus-late choice, so p2-p4 FAIL on 170191c0,
     round 4, by design). Every new session's connect-time open-orders end arrives L s after its connect began; the
     gateway drops at 15:54:20 and the decision meets it, the loop parked until decide_at + 0.2 s ("decide": the
     round-5 verifier's v6, test_mirror_d1r5 m1) or ticking at the drop ("drop": the other verifier's l1):
       p1  L <= 95 s trades exactly as on 170191c0: the same sessions, the same order instants
       p2  L = 150 s sends no order - the documented expectation (170191c0 traded at 15:57:46-52)
       p3  two LOST answers met at the decision trade before plan_by (170191c0: nothing traded)
       p4  overnight from the 23:45 drop (the other verifier's l2): L = 600 s ends the outage after 26 min with no
           page and the decision trades; L = 1200 s never ends it (66 replacements, one DOWN page, no trade)
  G  GATES (fail on 33850e01, pass after):
       g1  an alerted K5 outage cured by a replacement is announced RECONNECTED with its true cause: the open orders
           were unreadable (no trade, no flatten), the positions and cash were read - never "could not read the
           account", which contradicted the DOWN page ("positions and cash are read normally")
       g2  every K5 recovery notice (RECONNECTED and READABLE again, the mirror's and the blend's) says the same
       g3  the DOWN page counts every fresh session the outage tried, also when each reconnect made right after a
           replacement's drop is refused once (IB's 326: the schedule restarts each time) - it said none was tried
       g4  ... and a session that a gateway FIN brought, accepted at once (the schedule's step does not count it)
     twins (pass on both): g2's plain-outage notices to the letter; g3's never-answering night counts as before, the
     boot's own session is the first one, and the count starts over with each outage
  W  MEASUREMENT + twin: the /kill alert's longest form with the live configuration's shape (the live and the dry
     book, the blend's notes) against alerts.send's 4000-character cut, and how long the exception texts it quotes
     would have to be for it to pass the cut
"""
from __future__ import annotations

import itertools
import types
from datetime import timedelta

import pytest

import app.ib_adapter as ib_mod
import test_mirror as tm
import test_mirror_d1r4 as d4
from test_mirror import payload
from test_mirror_connection import D2, ROT, sound

POLL_S = 300.0                                          # settings.poll_seconds: the loop's longest park


def _et(t):
    return t.astimezone(tm.mm.ET).strftime("%H:%M:%S")


def _loop(r, until, watch=None):
    """service._loop with a live mirror book: the book's tick, the keepalive (_mirror_keepalive), then park
    _loop_wait(): next_wait() floored at 0.5 s, at most poll_seconds"""
    while r.clock.now < until:
        r.m.tick(r.ad)
        r.ad.keepalive()
        if watch is not None:
            watch()
        w = r.m.next_wait()
        r.vt.advance(POLL_S if w is None else min(POLL_S, max(float(w), 0.5)))


def _watched(r, monkeypatch):
    """(placed, connects): every order placed (instant, symbol, action) and every gateway connect (instant)"""
    placed, connects = [], []
    real_place, real_connect = r.ib.placeOrder, r.ib.connect
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (placed.append((r.clock.now, c.symbol, o.action)),
                                                          real_place(c, o))[1])

    def connect(*args, **kw):
        connects.append(r.clock.now)
        return real_connect(*args, **kw)
    monkeypatch.setattr(r.ib, "connect", connect)
    return placed, connects


def _decision(r, monkeypatch, policy, phase):
    """day 2 (ROT: three sells, three buys): the morning check at 09:30:05 on a healthy session; the gateway drops at
    15:54:20 and every NEW session follows `policy`; the loop then runs to 16:03 from decide_at + 0.2 s ("decide") or
    from the drop instant ("drop"). Returns (placed, connects, sells, buys, the day's info)."""
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    d4._tick_at(r, "09:30:05")
    placed, connects = _watched(r, monkeypatch)
    r.vt.advance((tm.at("15:54:20", D2) - r.clock.now).total_seconds())
    r.ib.policy = policy
    r.ib.drop()
    if phase == "decide":
        r.vt.advance((tm.at("15:54:25", D2) - r.clock.now).total_seconds() + 0.2)
    _loop(r, tm.at("16:03:00", D2))
    sells = [t for t, _, a in placed if a == "SELL"]
    buys = [t for t, _, a in placed if a == "BUY"]
    return placed, connects, sells, buys, r.m._today_info(r.clock.now)


# ============================================================================== part P: the pins
# measured with this file's harness on 170191c0 (round 4: session 1 replaced once, session 2 kept for good) and on
# 33850e01 (round 5's schedule): identical - (connects, sells, buys), ET
AS_ON_170191C0 = {
    ("decide", 45): (["15:54:25"], ["15:55:10"] * 3, ["15:55:11"] * 3),
    ("decide", 60): (["15:54:25", "15:55:21"], ["15:56:21"] * 3, ["15:56:22"] * 3),
    ("decide", 90): (["15:54:25", "15:55:21"], ["15:56:51"] * 3, ["15:56:52"] * 3),
    ("decide", 95): (["15:54:25", "15:55:21"], ["15:56:56"] * 3, ["15:56:57"] * 3),
    ("drop", 45): (["15:54:20"], ["15:55:06"] * 3, ["15:55:06"] * 3),
    ("drop", 60): (["15:54:20", "15:55:15"], ["15:56:15"] * 3, ["15:56:16"] * 3),
    ("drop", 90): (["15:54:20", "15:55:15"], ["15:56:45"] * 3, ["15:56:46"] * 3),
    ("drop", 95): (["15:54:20", "15:55:15"], ["15:56:50"] * 3, ["15:56:50"] * 3),
}


@pytest.mark.parametrize("phase,late", sorted(AS_ON_170191C0))
def test_p1_pin_answers_up_to_95s_late_met_at_the_decision_trade_exactly_as_on_170191c0(tmp_path, monkeypatch,
                                                                                         phase, late):
    """PIN. Session 1 is replaced 40 s after its connect gave up (55 s after its request), session 2 only 80 s after
    its own (95 s): an end up to 95 s late lands on session 2 before the schedule would replace it, so round 5 trades
    on the same two sessions at the same instants as round 4 - every order inside the window, K4 clean."""
    r = d4._rig(tmp_path, monkeypatch)
    placed, connects, sells, buys, info = _decision(r, monkeypatch, lambda n: float(late), phase)
    got = ([_et(t) for t in connects], [_et(t) for t in sells], [_et(t) for t in buys])
    assert got == AS_ON_170191C0[(phase, late)], got
    assert sorted((s, a, q) for s, a, q, _ in r.ib.placed[-6:]) == d4.ROT_ORDERS
    assert max(sells + buys) < info["cancel_at"]
    assert r.m.state["last_run"]["outcome"] == "traded"
    assert r.ib.violations == 0 and not r.sent                    # K4; no page
    sound(r)


@pytest.mark.parametrize("phase", ["decide", "drop"])
def test_p2_pin_an_answer_150s_late_met_at_the_decision_sends_no_order(tmp_path, monkeypatch, phase):
    """PIN - the documented expectation (ib_adapter._unsynced_replace_interval, KNOWN, NOT BUILT): the schedule
    replaces session 2 95 s after its request, before its end 150 s after it would land, and session 3's end comes
    past the cancel instant. Nothing is sent - fail closed, the book still equal to the account - where 170191c0 kept
    session 2 and traded at 15:57:46 (drop) / 15:57:52 (decide). Lost and late cannot be told apart before a drop; a
    design keeping both (a probe session on a second clientId) is not built."""
    r = d4._rig(tmp_path, monkeypatch)
    placed, connects, sells, buys, info = _decision(r, monkeypatch, lambda n: 150.0, phase)
    assert placed == [], [(_et(t), s, a) for t, s, a in placed]
    assert len(connects) == 3 and r.ib.n_sessions == 3, [_et(t) for t in connects]   # two replacements, 40 then 80 s
    assert r.m.state["last_run"]["session"] == D2
    assert all(o["filled"] == 0 for o in r.m.state["last_run"]["orders"]), r.m.state["last_run"]["orders"]
    assert r.ib.violations == 0
    sound(r)


@pytest.mark.parametrize("phase", ["decide", "drop"])
def test_p3_pin_two_lost_answers_met_at_the_decision_trade_before_plan_by(tmp_path, monkeypatch, phase):
    """PIN - the other side of the choice (round 5's cure, test_mirror_d1r5 m1): the reconnect's session and its
    replacement both LOSE their connect-time answer; the third session syncs and every order goes before plan_by"""
    r = d4._rig(tmp_path, monkeypatch)
    placed, connects, sells, buys, info = _decision(r, monkeypatch, lambda n: None if n <= 2 else 0, phase)
    assert len(sells) == 3 and len(buys) == 3, [(_et(t), s, a) for t, s, a in placed]
    assert sorted((s, a, q) for s, a, q, _ in r.ib.placed[-6:]) == d4.ROT_ORDERS
    assert max(sells + buys) < info["plan_by"], ([_et(t) for t in sells + buys], _et(info["plan_by"]))
    assert r.ib.n_sessions == 3 and r.m.state["last_run"]["outcome"] == "traded"
    assert r.ib.violations == 0 and not r.sent
    sound(r)


@pytest.mark.parametrize("late,closes_after_min,sessions,pages,trades", [
    (600, 26.0, 4, 0, True),                            # 170191c0: closed after 15.5 min (2 sessions)
    (1200, None, 67, 1, False),                         # 170191c0: closed after 25.5 min, traded
])
def test_p4_pin_every_sessions_answer_late_overnight(tmp_path, monkeypatch, late, closes_after_min, sessions, pages,
                                                     trades):
    """PIN (the other verifier's l2): the nightly drop at 23:45; every new session's connect-time end arrives `late` s
    after its connect began; the loop runs as in production to the next decision. 600 s late: the session the
    doubling keeps longer than that (the 4th, interval 320 s at the keepalive's 300 s cadence) gets its end, the
    outage closes after 26 min - no DOWN page - and the decision trades. 1200 s late, more than the 15-min cap plus
    the connect: every session is replaced before its end lands - 66 replacements, one DOWN page, the outage never
    closes and the decision does not trade."""
    r = d4._rig(tmp_path, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: float(late)
    r.ib.drop()
    t_drop, closed_at = r.clock.now, []

    def watch():
        if not closed_at and not r.ad.outages.open and r.ad.outages.history:
            closed_at.append(r.clock.now)
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    placed, _ = _watched(r, monkeypatch)
    _loop(r, tm.at("16:03:00", D2), watch=watch)
    after = round((closed_at[0] - t_drop).total_seconds() / 60, 1) if closed_at else None
    assert after == closes_after_min, (after, r.ib.n_sessions)
    assert r.ib.n_sessions == sessions
    assert len([m for m in r.sent if "DOWN for over" in m]) == pages, r.sent
    assert (len([1 for _, _, a in placed if a == "SELL"]) == 3) is trades
    assert r.ib.violations == 0


# ============================================================================== part G: the words
def _replaced_on_vt(r):
    r.replaced = []
    orig = r.ad._spend_unsynced_replacement

    def spend():
        r.replaced.append(r.clock.now)
        orig()
    r.ad._spend_unsynced_replacement = spend


def test_g1_an_alerted_k5_outage_cured_by_a_replacement_is_announced_with_its_true_cause(tmp_path, monkeypatch):
    """GATE. The gateway never answers a new session's connect-time request from 23:45; the DOWN page goes out at
    00:15; at 01:00 it answers again with no restart and no FIN, and the session the schedule tries next syncs. ONE
    notice ends the outage. 33850e01: 'RECONNECTED ... the Composer mirror could not read the account or trade
    meanwhile' - but the DOWN page had said positions and cash ARE read, and they were. Now it names the outage's
    cause (D1 round 7: every cause it had - here this one alone, test_mirror_d1r7): the open orders were unreadable
    (no trade, no flatten); positions and cash were read."""
    r = d4._rig(tmp_path, monkeypatch)
    _replaced_on_vt(r)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    heal_at = tm.at("01:00:00", D2)
    r.ib.policy = lambda n: None if r.clock.now < heal_at else 0
    r.ib.drop()
    _loop(r, tm.at("03:00:00", D2))
    downs = [m for m in r.sent if "DOWN for over" in m]
    recs = [m for m in r.sent if "RECONNECTED" in m or "READABLE" in m]
    assert len(downs) == 1 and len(recs) == 1, r.sent
    assert "positions and cash are read normally" in downs[0]
    assert not r.ad.outages.open and r.ad.outages.history[0].get("kind") == d4.UNSYNCED
    assert r.replaced and r.replaced[-1] >= heal_at                  # ended through a replacement: a reconnect
    rec = recs[0]
    assert rec.startswith("🧬 IB gateway RECONNECTED after "), rec
    assert ("open orders were unreadable" in rec and "could not trade or flatten" in rec
            and "positions and cash were read" in rec and "no resting stops" in rec), rec
    assert "could not read the account" not in rec, rec


def _bare(mirror_only, unsynced, reconnected, monkeypatch, down_min=60):
    """an adapter at the instant _recovered closes an ALERTED outage (no session machinery needed)"""
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    a = ib_mod.IBAdapter.__new__(ib_mod.IBAdapter)
    a.outages, a.mirror_only = None, mirror_only
    a._disconnected_since, a._outage_alerted = 1000.0, True
    a._open_orders_unsynced, a._outage_reconnected = unsynced, reconnected
    a._recovered(1000.0 + down_min * 60)
    assert len(sent) == 1 and a._disconnected_since is None and a._outage_alerted is False
    assert getattr(a, "_unsynced_sessions", 0) == 0
    return sent[0]


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("reconnected", [True, False])
def test_g2_every_k5_recovery_notice_is_worded_from_that_last_cause(monkeypatch, mirror_only, reconnected):
    """GATE (_recovered, the READABLE-again branch checked too): after an unsynced outage the gateway was logged in,
    the positions and the cash were read and the open orders were not - the DOWN page's own words. 33850e01: the
    mirror's RECONNECTED said 'could not read the account'; READABLE said 'could not trade' (not the flatten, not
    what WAS read); the blend's said neither cause."""
    msg = _bare(mirror_only, True, reconnected, monkeypatch)
    assert "open orders were unreadable" in msg and "positions and cash were read" in msg, msg
    assert "could not read the account" not in msg, msg
    if reconnected:
        assert msg.startswith("🧬 IB gateway RECONNECTED after 60 min — executor resumed ("), msg
    else:
        assert msg.startswith("🧬 IB gateway open orders READABLE again after 60 min — "), msg
        assert "no reconnect was needed" in msg and "RECONNECTED" not in msg, msg
    if mirror_only:
        assert "the Composer mirror could not trade or flatten meanwhile" in msg and "no resting stops" in msg, msg
        assert "GTC" not in msg
    else:
        assert "cycles were failing closed meanwhile" in msg and "GTC stops rested at the venue" in msg, msg


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("reconnected", [True, False])
def test_g2_twin_a_plain_outages_notice_is_unchanged_to_the_letter(monkeypatch, mirror_only, reconnected):
    """TWIN (passes before and after): the outage had no session at all, only the plain cause - the words stay
    what they were (round 7 words the notice from every cause the outage had, not its last one)"""
    msg = _bare(mirror_only, False, reconnected, monkeypatch)
    if mirror_only:
        assert msg == ("🧬 IB gateway RECONNECTED after 60 min — executor resumed (the Composer mirror could not "
                       "read the account or trade meanwhile; it keeps no resting stops at the venue)"), msg
    else:
        assert msg == ("🧬 IB gateway RECONNECTED after 60 min — executor resumed (cycles were failing closed "
                       "meanwhile; GTC stops rested at the venue throughout)"), msg


def _night_until_the_page(r, until_hms="00:30:00", snap=lambda: None):
    """the keepalive every 300 s from now (the loop's idle cadence) until `until_hms` on day 2; returns (the DOWN
    page, the sessions the gateway had accepted since the drop when it went out, snap() at that instant)"""
    page = []
    until = tm.at(until_hms, D2)
    while r.clock.now < until:
        n0 = len(r.sent)
        r.ad.keepalive()
        page += [(m, r.ib.n_sessions, snap()) for m in r.sent[n0:] if "DOWN for over" in m]
        r.vt.advance(POLL_S)
    assert len(page) == 1, r.sent
    return page[0]


def _refuse_each_reconnect_after_a_drop(r, monkeypatch):
    """the round-5 verifier's v4: the connect made right after the adapter dropped a session is refused once (a
    clientId still in use, IB's 326); the next attempt, one backoff later, succeeds"""
    state = {"fail_next": False, "refused": 0}
    real = r.ib.connect

    def connect(*a, **k):
        if state["fail_next"]:
            state["fail_next"], state["refused"] = False, state["refused"] + 1
            raise ConnectionRefusedError("326 clientId already in use (simulated)")
        return real(*a, **k)
    monkeypatch.setattr(r.ib, "connect", connect)
    drop = r.ad._drop_session

    def dropped():
        state["fail_next"] = True
        drop()
    r.ad._drop_session = dropped
    return state


def test_g3_the_down_page_counts_every_fresh_session_tried_when_each_reconnect_after_a_replacement_is_refused(
        tmp_path, monkeypatch):
    """GATE. A gateway that never answers the connect-time request AND refuses the reconnect made right after each
    replacement's drop: every failed connect restarts the schedule (the round-5 verifier's v4 - recorded, not
    changed), so its step never passes 1. 33850e01 counted that step: the page said no fresh session had been tried
    while three had. Now it counts every session the outage found unsynced, less the first."""
    r = d4._rig(tmp_path, monkeypatch)
    state = _refuse_each_reconnect_after_a_drop(r, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None
    r.ib.drop()
    page, sessions, (refused, step) = _night_until_the_page(
        r, snap=lambda: (state["refused"], getattr(r.ad, "_unsynced_replacements", None)))
    assert (sessions, refused, step) == (4, 3, 0), (sessions, refused, step)   # 3 replacements, each refused once;
    assert " 3 fresh gateway sessions were already tried and none synced;" in page, page   # the step restarted
    assert r.ib.violations == 0


def test_g4_the_down_page_counts_a_session_a_gateway_fin_brought(tmp_path, monkeypatch):
    """GATE. Never answering from 23:45; at 23:57 the gateway closes the session (its FIN) and accepts the next
    connect at once, still never answering. That session is tried and does not sync, but the schedule did not bring
    it, so its step does not count it (33850e01: '4 fresh gateway sessions' while 5 had been tried)."""
    r = d4._rig(tmp_path, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None
    r.ib.drop()
    fin_at, fin, page = tm.at("23:57:00", tm.DAY), [], []
    until = tm.at("00:30:00", D2)
    while r.clock.now < until:
        n0 = len(r.sent)
        r.ad.keepalive()
        page += [(m, r.ib.n_sessions) for m in r.sent[n0:] if "DOWN for over" in m]
        park = POLL_S
        if not fin and r.clock.now + timedelta(seconds=park) > fin_at:
            before = (fin_at - r.clock.now).total_seconds()
            r.vt.advance(before)
            r.ib.drop()                  # the gateway's FIN while the loop is parked; the next connect is accepted
            fin.append(r.clock.now)
            park -= before
        r.vt.advance(park)
    assert fin and len(page) == 1, r.sent
    msg, sessions = page[0]
    assert sessions == 6, sessions                       # 3 before the FIN, the one it brought, 2 replacements after
    assert getattr(r.ad, "_unsynced_replacements", None) == 4                  # the schedule's step skipped one
    assert " 5 fresh gateway sessions were already tried and none synced;" in msg, msg
    assert r.ib.violations == 0


def test_g3_twin_a_never_answering_night_counts_the_fresh_sessions_as_before(tmp_path, monkeypatch):
    """TWIN (passes before and after): no refusal, no FIN - every session after the first came from a replacement,
    so the count is what it was: at 00:15 the fifth session is up and four fresh ones were tried (the wait's words
    that follow the count changed in D1 round 7: test_mirror_d1r7 p1-p2)"""
    r = d4._rig(tmp_path, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None
    r.ib.drop()
    page, sessions, step = _night_until_the_page(r, snap=lambda: getattr(r.ad, "_unsynced_replacements", None))
    assert (sessions, step) == (5, 4), (sessions, step)
    assert " 4 fresh gateway sessions were already tried and none synced; another is tried at the executor's next " \
           "check once a wait has passed" in page, page


def test_g3_twin_a_boot_into_a_gateway_that_never_answers_counts_its_own_session_as_the_first(tmp_path,
                                                                                               monkeypatch):
    """TWIN (passes before and after): the service boots (its own _connect) into a gateway whose connect-time sync is
    never answered - that session opens the outage and is the first, not a fresh one: four tried after it"""
    r = d4._rig(tmp_path, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None
    r.ib.disconnect()                                   # a restart: the old process's session is gone
    d4._REAL_CONNECT(r.ad)                              # the service's own boot connect
    assert r.ad._disconnected_since is not None and r.ad.outages.open.get("kind") == d4.UNSYNCED
    page, sessions, step = _night_until_the_page(r, snap=lambda: getattr(r.ad, "_unsynced_replacements", None))
    assert (sessions, step) == (5, 4), (sessions, step)
    assert " 4 fresh gateway sessions were already tried and none synced;" in page, page


def test_g3_twin_the_count_starts_over_with_each_outage(tmp_path, monkeypatch):
    """TWIN (passes before and after): a never-answering spell pages and heals (no FIN) at 01:00; the next one, from
    02:00, pages with its own count - the sessions of the first outage are not in it"""
    r = d4._rig(tmp_path, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    heal_at = tm.at("01:00:00", D2)
    r.ib.policy = lambda n: None if r.clock.now < heal_at else 0
    r.ib.drop()
    first, _, _ = _night_until_the_page(r, until_hms="01:30:00")
    assert " 4 fresh gateway sessions were already tried" in first, first
    assert not r.ad.outages.open and len(r.ad.outages.history) == 1
    r.vt.advance((tm.at("02:00:00", D2) - r.clock.now).total_seconds())
    n0 = r.ib.n_sessions
    r.ib.policy = lambda n: None
    r.ib.drop()
    page, sessions, _ = _night_until_the_page(r, until_hms="02:45:00")
    assert sessions - n0 == 5, (sessions, n0)
    assert " 4 fresh gateway sessions were already tried and none synced;" in page, page


# ============================================================================== part W: the /kill alert's length
SEND_CUT = 4000                                         # app/alerts.py send(): text[:4000]
EXC_TEXT = {"text": None}           # None: every simulated failure says what the real one would; a string: they all
                                    # say exactly that (the threshold sweeps of w1)


def _exc(cls, *real):
    text = EXC_TEXT["text"]
    return cls(text) if text is not None else cls(*real)


def _oserror(path):
    """the realistic failure of every write /kill makes: a full disk on Render's mounted volume"""
    return _exc(OSError, 28, "No space left on device", path)


class _Leg:
    def __init__(self, status):
        self.status = status


class _NoHaltState:
    """a ladder state the halt cannot be set on: /kill's 'the ladder halt FAILED' branch"""

    def __init__(self, legs):
        object.__setattr__(self, "legs", legs)
        object.__setattr__(self, "halted", None)

    def __setattr__(self, name, value):
        raise _exc(RuntimeError, "the ladder state is read-only (simulated)")


class _Ladder:
    def __init__(self, legs, journal_fails, save_fails, clear_fails, fault=None):
        legs = {k: _Leg(s) for k, s in legs.items()}
        if fault == "after_halt":                       # a leg key that is not text: the leg list cannot be worded
            legs[1] = _Leg("OPEN")                      # -> 'the ladder IS HALTED, but the /kill could not be ...'
        self.state = (_NoHaltState(legs) if fault == "before_halt" else
                      types.SimpleNamespace(halted=None, legs=legs))
        self.journal_fails, self.save_fails, self.clear_fails = journal_fails, save_fails, clear_fails

    def journal_kill(self, today):
        if self.journal_fails:
            raise _oserror("/app/data/ladder_state.json.kill")

    def save(self):
        if self.save_fails:
            raise _oserror("/app/data/ladder_state.json.tmp")

    def clear_kill(self):
        if self.clear_fails:
            raise _exc(PermissionError, 13, "Permission denied", "/app/data/ladder_state.json.kill")


class _BlendState:
    def __init__(self, broken):
        self._broken, self.halted, self._fr = broken, None, None

    @property
    def flatten_request(self):
        if self._broken:
            raise _exc(RuntimeError, "dictionary changed size during iteration")
        return self._fr

    @flatten_request.setter
    def flatten_request(self, v):
        self._fr = v


class _Blend:
    def __init__(self, mode):
        self.mode, self.state = mode, _BlendState(mode == "halt_failed")

    def request_flatten(self, today):
        if self.mode in ("unpersisted", "halt_failed"):
            raise _oserror("/app/data/blend_state.json.tmp")


class _Book:
    def __init__(self, live, mode, path):
        self.cfg = types.SimpleNamespace(live=live)
        self.mode, self.path = mode, path

    def halt(self, reason, flatten=False):
        if self.mode == "raises":
            raise _oserror(self.path)
        h = {"halted": True}
        if flatten and self.cfg.live:
            h.update(flatten=True, flatten_done=False)
        return dict(h, persisted=self.mode != "not_persisted")


def _kill_alert(monkeypatch, svc, legs, journal_fails, save_fails, clear_fails, blend, loop_down, live_mode,
                dry_mode, fault=None, books=("live", "dry")):
    sent: list = []
    monkeypatch.setattr(svc, "send", sent.append)
    monkeypatch.setattr(svc.settings, "exec_token", "sekrit")
    monkeypatch.setattr(svc, "MGR", _Ladder(legs, journal_fails, save_fails, clear_fails, fault))
    monkeypatch.setattr(svc, "BLEND", None if blend is None else _Blend(blend))
    made = {"live": _Book(True, live_mode, "/app/data/mirror_state.json.halt"),
            "dry": _Book(False, dry_mode, "/app/data/mirror_dry_state.json.halt")}
    monkeypatch.setattr(svc, "MIRROR", {k: made[k] for k in books})
    import time as _time
    monkeypatch.setattr(svc, "LAST", {"loop_ok": 0.0 if loop_down else _time.time(), "nino34": None,
                                      "mode": "LIVE"})
    svc.kill(x_exec_token="sekrit", token=None)
    svc.LADDER_KILL.clear()
    svc.LOOP_WAKE.clear()
    kills = [m for m in sent if "KILLED" in m]
    assert len(kills) == 1, sent
    return kills[0]


ALL_OPEN = {"NG": "OPEN", "SB": "OPEN", "SLV": "OPEN"}
NONE_OPEN = {"NG": "WAITING", "SB": "WAITING", "SLV": "WAITING"}


def _sweep(monkeypatch, svc):
    """every failure branch /kill words, with the live and the dry book: [(length, case, alert)] in a fixed order"""
    out = []
    for legs, jf, sf, cf, fault, blend, loop_down, live_mode, dry_mode in itertools.product(
            (NONE_OPEN, ALL_OPEN), (False, True), (False, True), (False, True), (None, "after_halt", "before_halt"),
            (None, "ok", "unpersisted", "halt_failed"), (False, True),
            ("ok", "not_persisted", "raises"), ("ok", "not_persisted", "raises")):
        msg = _kill_alert(monkeypatch, svc, legs, jf, sf, cf, blend, loop_down, live_mode, dry_mode, fault)
        out.append((len(msg), (sorted(k for k, s in legs.items() if s == "OPEN"), jf, sf, cf, fault, blend,
                               loop_down, live_mode, dry_mode), msg))
    return out


def test_w1_measure_the_longest_kill_alert_with_the_live_configurations_shape(monkeypatch):
    """MEASUREMENT + TWIN (no code changed for it): POST /kill with the live configuration's shape - the live book
    (its flatten queued) and the dry book, the blend's notes, every ladder leg - over every failure branch the handler
    words (3456 combinations), each write failing as on a full disk. alerts.send keeps text[:4000]. Prints the
    smallest, the normal and the longest form; the longest must keep its last line (the resume instruction) inside
    the cut. Then: can it pass the cut? Every alert's length is linear in the length E of the exception texts it
    quotes (n = fixed + k x E, k the texts it quotes), so two sweeps with every simulated failure saying a uniform text
    give both terms per branch, and the shortest E at which ANY branch passes 4000 (the join's own TypeError of the
    'after_halt' branch keeps Python's words)."""
    import app.service as svc
    disk = len(str(_oserror("/app/data/ladder_state.json.kill")))      # a full disk's text, as /kill quotes it
    smallest = _kill_alert(monkeypatch, svc, NONE_OPEN, False, False, False, None, False, "ok", "ok", books=("live",))
    normal = _kill_alert(monkeypatch, svc, NONE_OPEN, False, False, False, "ok", False, "ok", "ok")
    real = _sweep(monkeypatch, svc)
    longest_n, longest_case, longest = max(real, key=lambda x: x[0])
    monkeypatch.setitem(EXC_TEXT, "text", "x" * 100)
    at100 = _sweep(monkeypatch, svc)
    monkeypatch.setitem(EXC_TEXT, "text", "x" * 300)
    at300 = _sweep(monkeypatch, svc)
    assert [c for _, c, _ in at100] == [c for _, c, _ in at300] == [c for _, c, _ in real]
    assert all((b - a) % 200 == 0 for (a, _, _), (b, _, _) in zip(at100, at300))      # exactly linear in E
    e_cut, k_cut, case_cut = min((((SEND_CUT - (a - (b - a) // 2)) / ((b - a) / 200), (b - a) // 200, case)
                                  for (a, case, _), (b, _, _) in zip(at100, at300) if b > a), key=lambda x: x[0])
    print(f"\nW1 /kill alert: the live book alone, blend off, no leg open {len(smallest)} chars; live + dry books with "
          f"the blend on, no failure {len(normal)}; longest {longest_n} over {len(real)} branch combinations (open "
          f"legs, journal/save/clear fail, ladder fault, blend, loop down, live, dry) {longest_case}; alerts.send cut "
          f"{SEND_CUT}; MIRROR_KILL_BOUND {len(svc.MIRROR_KILL_BOUND)}. It passes the cut once every quoted exception "
          f"text is longer than {e_cut:.0f} chars (branch {case_cut}, {k_cut} texts quoted); a full disk's is {disk}")
    print("W1 longest:", longest)
    assert len(smallest) < len(normal) < SEND_CUT
    assert "mirror[live] HALTED, flatten QUEUED" in normal and "mirror[dry] HALTED" in normal
    assert longest_n < SEND_CUT, (longest_n, longest_case)
    assert longest.rstrip().endswith(("halted book)", "once you have")), longest[-200:]
    assert e_cut > disk
