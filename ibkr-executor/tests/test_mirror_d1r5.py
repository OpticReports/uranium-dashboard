"""D1 round 5 - the open-orders wait (K5): a kept unsynced session is replaced on a doubling schedule (2026-11-13).

Round 4 replaced a session whose connect-time open-orders sync never ended ONCE per outage. Its independent verifier
found the liveness regression that left (SERIOUS): when that one fresh session lost its answer too, it was kept for as
long as it lived - every guarded read failed at once, the mirror did not trade and a /kill flatten could not sell,
where one more fresh session would have synced (1de7535c recovered at its next guarded read). Now a kept unsynced
session is replaced on a schedule: UNSYNCED_REPLACE_WAITS x the bound after its connect gave up (40 s, round 4's
first step), then twice the previous interval each time (80, 160, 320, 640 s), capped at UNSYNCED_REPLACE_MAX_S
(15 min); the schedule starts over when the outage has no session at all and when the outage ends. A guarded read
takes a replacement that is due, so a decision or a /kill flatten recovers in-process.

Every gate below FAILS on 170191c0 (the code before this round) and passes after it.
  R  the INSTALLED ib_async on a real localhost socket, scaled as in test_mirror_d1r4 (the bound 0.3 s for 20 s, the
     connect's sync wait 0.3 s for 15 s, the backoff 0.6 s up to 1.2 s): the verifier's v_r1 and v_r2, ported
     (fixverify/r4_d1_tests/test_zz_r4d1_verify.py), and the schedule with its cap
  M  the REAL MirrorManager driving the REAL IBAdapter on ONE virtual clock at production values (test_mirror_d1r4's
     part M), with the service loop's cadence modelled (service._loop: the mirror's tick, _mirror_keepalive, then
     park _loop_wait()): two lost answers met at the decision; a /kill flatten during them
  S  the schedule itself on the virtual clock (production values): the exact intervals and the cap, both resets
  W  the /kill alert's bound names the keepalive's reconnect stall (the verifier's NOTE 3)
Invariants checked in every scenario: no open-orders request is ever sent while one is pending (K4) - at the client
before each request, on the wire (R), in the virtual gateway (M, S); one DOWN page per outage at most."""
from __future__ import annotations

import math
import sys
import time
from datetime import timedelta

import pytest

import app.ib_adapter as ib_mod
import test_mirror as tm
import test_mirror_connection as tmc
import test_mirror_d1r4 as d4
from app.outages import OutageLog
from test_mirror import payload
from test_mirror_connection import D2, ROT, _REAL_CONNECT, _RealCfg, sound

try:
    import ib_async as real_ib_async
except Exception:  # noqa: BLE001
    real_ib_async = None

needs_ib_async = pytest.mark.skipif(real_ib_async is None, reason="ib_async is not installed")
BOUND, SYNC = d4.BOUND, d4.SYNC          # 0.3 s for 20 s, 0.3 s for 15 s


# ============================================================================== the rigs: a real socket
class K4Gateway(d4.WireGateway):
    """test_mirror_d1r4's WireGateway, plus K4 on the WIRE: every open-orders request (reqOpenOrders 5 at connect,
    reqAllOpenOrders 16) is logged when it arrives, with when its end is sent (now + the policy's delay; never for
    None). A request that arrives on a session while an earlier one's end is still unsent is a violation: a K4
    client sends only once it has PROCESSED the earlier end, which the gateway sent before."""

    def __init__(self, policy=None):
        self.oo_log: list = []                          # (session, n, arrived, end sent at)
        super().__init__(policy)

    @property
    def policy(self):
        return self._recording

    @policy.setter
    def policy(self, fn):
        fn = fn or (lambda s, n: 0)

        def recording(s, n):
            d = fn(s, n)
            now = time.monotonic()
            self.oo_log.append((s, n, now, math.inf if d is None else now + d))
            return d
        self._recording = recording

    def k4_wire(self) -> list:
        return [(s, n) for i, (s, n, t, _) in enumerate(self.oo_log)
                if any(s2 == s and n2 < n and end > t for s2, n2, _, end in self.oo_log[:i])]


def _recorded_replacements(a):
    """a.replaced: (monotonic, how long the session's sync had been unended, the interval the schedule asked for)
    at every replacement the adapter takes (_spend_unsynced_replacement), whoever takes it"""
    a.replaced = []
    orig = a._spend_unsynced_replacement

    def spend():
        now = time.monotonic()
        interval = getattr(a, "_unsynced_replace_interval", lambda: None)()
        a.replaced.append((now, now - (a._sync_pending_since or now), interval))
        orig()
    a._spend_unsynced_replacement = spend


@pytest.fixture
def w5(monkeypatch, tmp_path):
    """make(policy, boot=True): a real IBAdapter on the installed ib_async, scaled (test_mirror_d1r4's `wire`: the
    bound 0.3 s, the connect's sync wait 0.3 s, the backoff 0.6 s up to 1.2 s, the DOWN page after 2.5 s), its outage
    ledger on disk, its alerts in make.sent, K4 checked at the client (a.k4_violations) and on the wire
    (gw.k4_wire()), its drops and replacements counted; boot: connected by the service's own _connect"""
    if real_ib_async is None:
        pytest.skip("ib_async is not installed")
    monkeypatch.setitem(sys.modules, "ib_async", real_ib_async)
    monkeypatch.setattr(ib_mod.IBAdapter, "_connect", lambda self: None)
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", BOUND)
    monkeypatch.setattr(ib_mod, "OUTAGE_ALERT_S", d4.ALERT)
    monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 0.6)
    made = []

    def make(policy, boot=True):
        gw = K4Gateway(policy)
        a = ib_mod.IBAdapter(_RealCfg())
        a._reconnect_backoff, a.reconnect_backoff_max_s, a.mirror_only = 0.6, 1.2, True
        a.outages = OutageLog(str(tmp_path / f"outages{len(made)}.json"))
        real = a.ib.connect
        a.connects = 0

        def to_gw(host, port, clientId, timeout=15):
            a.connects += 1
            return real("127.0.0.1", gw.port, clientId=clientId, timeout=SYNC)
        a.ib.connect = to_gw
        tmc._counted_drops(a)
        d4._k4_checked(a)
        _recorded_replacements(a)
        made.append((a, gw))
        if boot:
            _REAL_CONNECT(a)
            a.connects = 0
        return a, gw
    make.sent = sent
    yield make
    for a, gw in made:
        try:
            a.ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        gw.close()


def _k4_clean(a, gw):
    time.sleep(0.05)
    assert a.k4_violations == 0 and gw.k4_wire() == [], (a.k4_violations, gw.k4_wire())


# ============================================================================== part R: the installed library
@needs_ib_async
def test_r1_v_r1_two_lost_connect_time_answers_then_healthy_sessions_trade_in_process(w5, monkeypatch):
    """the verifier's v_r1: the boot session and the next one both lose their connect-time open-orders answer (a
    gateway still warming up after its nightly restart, say); every later session syncs at once. 170191c0: the one
    replacement is spent on the boot session, the second session is then KEPT - every read fails at once for as
    long as it lives (the mirror and a /kill flatten cannot sell). Now: the boot session is replaced 2 x the bound
    after its connect, the second 4 x the bound after its own, and the third answers.
    (The DOWN page here is moved to 10 s: in production the outage lasts ~2.5 min against the page's 30.)"""
    monkeypatch.setattr(ib_mod, "OUTAGE_ALERT_S", 10.0)
    a, gw = w5(lambda s, n: None if (n == 1 and s <= 2) else 0)
    reads, answers, _ = tmc._decision_reads(a, 4.0)
    assert answers and set(answers) == {0}, (reads, answers, gw.sessions, a.drops, a.replaced)
    assert [round(i / BOUND) for _, _, i in a.replaced] == [2, 4], a.replaced     # 2 x, then 4 x the bound
    assert all(w >= i for _, w, i in a.replaced), a.replaced
    assert a.drops == 2 and gw.sessions == 3 and a.connects == 2                    # two replacements, no other drop
    assert not a.outages.open and len(a.outages.history) == 1 and a._disconnected_since is None
    assert w5.sent == []                                                             # no page: it never lasted
    _k4_clean(a, gw)


@needs_ib_async
def test_r2_v_r2_a_gateway_that_answers_again_without_a_restart_is_traded_on_in_process(w5):
    """the verifier's v_r2 (1de7535c's test_k5_never_first recovery step, which round 4 changed to need a FIN): no
    session's connect-time request is answered for a while, then the gateway answers NEW sessions' syncs again with
    no restart and no FIN. 170191c0: the kept second session never syncs and nothing is replaced again - no answer,
    ever. Now: the session the schedule replaces next syncs."""
    a, gw = w5(lambda s, n: None if n == 1 else 0)
    said: set = set()
    reads, answers, _ = tmc._decision_reads(a, 2.0, said)
    assert answers == [] and reads >= 5
    gw.policy = lambda s, n: 0                          # answers every request again; the session stays up
    reads, answers, _ = tmc._decision_reads(a, 4.0, said)
    assert answers and set(answers) == {0}, (reads, answers, gw.sessions, a.drops, a.replaced)
    assert a.drops == len(a.replaced) >= 2 and not a.outages.open and a._disconnected_since is None
    guard = [m for m in said if "still unanswered" in m]                # what the mirror's red alert quotes
    assert guard and all("restart the gateway if this persists" in m for m in guard), said
    _k4_clean(a, gw)


@needs_ib_async
def test_r3_a_never_answering_gateway_gets_a_fresh_session_on_the_doubling_schedule_up_to_its_cap(w5, monkeypatch):
    """the overnight shape on the wire: no session's connect-time request is ever answered; the keepalive runs every
    50 ms. The cap is scaled with the bound (2.4 s here, 15 min in production: 8 x the bound's 0.3 s, so the cap is
    met at the third step). Each replacement comes when its session's sync has been unended for the schedule's
    interval - 0.6, 1.2, then 2.4 s and 2.4 s again (the cap) - never sooner, and within one keepalive pass after it
    is due; two replacements are never closer than the later one's interval. One cause and one DOWN page all along,
    nothing sent while a request is pending. 170191c0: one replacement, then the second session kept for good."""
    monkeypatch.setattr(ib_mod, "UNSYNCED_REPLACE_MAX_S", 8 * BOUND, raising=False)
    a, gw = w5(lambda s, n: None if n == 1 else 0)
    end = time.monotonic() + 9.0
    while time.monotonic() < end:
        assert a.keepalive() is True
        assert a.outages.open is not None and a.outages.open.get("kind") == d4.UNSYNCED
        time.sleep(0.05)
    assert len(a.replaced) == a.drops == 4 and gw.sessions == 5 and a.connects == 4, a.replaced
    steps = [round(i / BOUND) for _, _, i in a.replaced]
    assert steps == [2, 4, 8, 8], a.replaced
    for _, waited, interval in a.replaced:
        assert interval <= waited < interval + 0.35, a.replaced
    for (t0, _, _), (t1, _, i1) in zip(a.replaced, a.replaced[1:]):
        assert t1 - t0 >= i1, a.replaced                 # never closer than the current interval
    downs = [m for m in w5.sent if "DOWN for over" in m]
    assert len(downs) == 1 and "fresh gateway session" in downs[0] and "already tried" in downs[0], w5.sent
    assert not [m for m in w5.sent if "RECONNECTED" in m or "READABLE" in m] and a.outages.history == []
    _k4_clean(a, gw)


# ============================================================================== part M: the mirror, virtual time
POLL_S = 300.0                                          # settings.poll_seconds: the loop's longest park


def _loop(r, until):
    """the service loop with a live mirror book (service._loop): the book's tick, then _mirror_keepalive (the
    adapter's keepalive), then park _loop_wait(): the book's next_wait() floored at 0.5 s, at most poll_seconds"""
    while r.clock.now < until:
        r.m.tick(r.ad)
        r.ad.keepalive()
        w = r.m.next_wait()
        r.vt.advance(POLL_S if w is None else min(POLL_S, max(float(w), 0.5)))


def _watched(r, monkeypatch):
    """(placed, checks, connects): every order placed (instant, symbol, action), every sell check's open-orders read
    that ANSWERED (instant, symbol), every gateway connect (instant), on the virtual clock"""
    placed, checks, connects = [], [], []
    real_place, real_osq, real_connect = r.ib.placeOrder, r.ad.open_sell_qty, r.ib.connect
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (placed.append((r.clock.now, c.symbol, o.action)),
                                                          real_place(c, o))[1])

    def osq(sym, exclude=None):
        out = real_osq(sym, exclude=exclude)
        checks.append((r.clock.now, sym))
        return out
    monkeypatch.setattr(r.ad, "open_sell_qty", osq)

    def connect(*args, **kw):
        connects.append(r.clock.now)
        return real_connect(*args, **kw)
    monkeypatch.setattr(r.ib, "connect", connect)
    return placed, checks, connects


def _et(t):
    return t.astimezone(tm.mm.ET).strftime("%H:%M:%S")


def test_m1_two_lost_answers_met_at_the_decision_trade_before_plan_by(tmp_path, monkeypatch):
    """the gateway drops at 15:54:20 and the decision (15:54:25) meets it: the reconnect's session loses its
    connect-time open-orders answer, so does the one that replaces it; every later session is healthy. The loop runs
    as in production (its ticks at the book's next_wait, the keepalive after each). 170191c0: the first session is
    replaced at 2 x the bound, the second is KEPT - no sell is ever checked, nothing trades. Now: the second session
    is replaced 80 s after its connect (4 x the bound), the third syncs, and every sell is checked and sent and every
    buy placed BEFORE plan_by (15:58:00, a minute before the cancel instant) - nothing ever sent while a request
    was pending, no DOWN page (the outage lasts ~2.5 min)."""
    r = d4._rig(tmp_path, monkeypatch)
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    d4._tick_at(r, "09:30:05")                          # the morning check, on a healthy session
    placed, checks, connects = _watched(r, monkeypatch)
    r.vt.advance((tm.at("15:54:20", D2) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None if n <= 2 else 0
    r.ib.drop()
    r.vt.advance((tm.at("15:54:25", D2) - r.clock.now).total_seconds() + 0.2)      # next_wait: decide_at + 0.2 s
    _loop(r, tm.at("16:03:00", D2))
    info = r.m._today_info(r.clock.now)
    plan_by, cancel_at = info["plan_by"], info["cancel_at"]
    assert _et(plan_by) == "15:58:00" and _et(cancel_at) == "15:59:00"
    sells = [t for t, _, a in placed if a == "SELL"]
    buys = [t for t, _, a in placed if a == "BUY"]
    report = {"connects": [_et(t) for t in connects], "sell checks answered": [(_et(t), s) for t, s in checks],
              "sells sent": [_et(t) for t in sells], "buys placed": [_et(t) for t in buys]}
    print("\nM1 two_lost at the decision:", report)
    assert len(sells) == 3 and len(buys) == 3, (report, r.red()[-3:])
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded", row
    assert sorted((s, a, q) for s, a, q, _ in r.ib.placed[-6:]) == d4.ROT_ORDERS
    assert all(o["filled"] == o["qty"] for o in row["orders"]), row["orders"]
    assert len(checks) >= 3 and max(t for t, _ in checks) < plan_by, report       # checked ...
    assert max(sells) < plan_by and max(buys) < plan_by, report                    # ... sent, placed: before plan_by
    assert r.ib.n_sessions == 3 and len(connects) == 3, report                      # two lost, the third synced
    assert r.ib.violations == 0                                                      # K4
    assert not r.ad.outages.open and len(r.ad.outages.history) == 1 and not r.sent  # no DOWN page, no RECONNECTED
    sound(r)


def test_m2_a_kill_flatten_during_two_lost_answers_sells_once_a_healthy_session_comes(tmp_path, monkeypatch):
    """/kill at 11:00 on a session day, just as the gateway drops: the reconnect's session loses its connect-time
    open-orders answer, so does the one that replaces it; every later session is healthy. The flatten's open-orders
    reads fail closed meanwhile (nothing may be sold on top of a resting sell it cannot see). 170191c0: the second
    session is kept for good - the flatten never sells. Now: it sells every position once the third session (the
    schedule's second replacement, 80 s after the second session's connect) has synced - about 2.5 minutes in."""
    r = d4._rig(tmp_path, monkeypatch)
    held = dict(r.venue_pos())
    placed, _, connects = _watched(r, monkeypatch)
    r.vt.advance((tm.at("11:00:00", D2) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None if n <= 2 else 0
    r.ib.drop()
    r.m.halt("KILL", flatten=True)
    _loop(r, tm.at("11:10:00", D2))
    sells = [(t, s) for t, s, a in placed if a == "SELL"]
    report = {"connects": [_et(t) for t in connects], "sells": [(_et(t), s) for t, s in sells]}
    print("\nM2 /kill flatten during two_lost:", report)
    assert sorted(s for _, s in sells) == sorted(held), report                     # every position, once
    assert not [1 for _, _, a in placed if a == "BUY"]
    assert r.venue_pos() == {} and all(q >= 0 for q in r.acct.pos.values())
    assert r.ib.n_sessions == 3 and len(connects) == 3, report
    assert min(t for t, _ in sells) >= connects[2]                                 # on the healthy session
    assert max(t for t, _ in sells) < tm.at("11:04:00", D2), report
    assert r.ib.violations == 0
    assert r.m.halt_state().get("flatten_done") is True


# ============================================================================== part S: the schedule, exactly
def _replaced_on_vt(r):
    """the adapter's replacements on the virtual clock: (instant, unended for, the interval asked for)"""
    r.replaced = []
    orig = r.ad._spend_unsynced_replacement

    def spend():
        now = r.vt.now()
        interval = getattr(r.ad, "_unsynced_replace_interval", lambda: None)()
        r.replaced.append((now, now - (r.ad._sync_pending_since or now), interval))
        orig()
    r.ad._spend_unsynced_replacement = spend


def _idle(r, seconds, every=1.0):
    """an idle stretch: the keepalive every `every` s (finer than the loop's 300 s, to time each replacement)"""
    end = r.vt.now() + seconds
    while r.vt.now() < end:
        r.ad.keepalive()
        r.vt.advance(every)


def _nightly_drop(r, policy):
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = policy
    r.ib.drop()


def test_s1_the_schedule_doubles_from_twice_the_bound_to_the_15_min_cap(tmp_path, monkeypatch):
    """production values on the virtual clock: no session's connect-time request is ever answered. The kept session
    is replaced when its sync has been unended 40 s (2 x the 20 s bound), the next 80 s after ITS connect gave up,
    then 160, 320, 640 s, then every 900 s (the cap) - each within the 1 s keepalive cadence of its due time. Two
    replacements are never closer than the later one's interval (each is counted from the connect of the session it
    replaces, 15 s of sync wait after the one before). 170191c0: one replacement, then none for good."""
    r = d4._rig(tmp_path, monkeypatch)
    _replaced_on_vt(r)
    _nightly_drop(r, lambda n: None)
    _idle(r, 3 * 3600.0)
    # 3 h: the reconnect after the drop (15 s), then 5 doubling steps (40 + 80 + 160 + 320 + 640 s, each followed by
    # its fresh session's 15 s connect: the 5th at 1315 s), then one per 900 + 15 s: 10 more by 10800 s
    assert len(r.replaced) == 5 + int((3 * 3600.0 - 1315) // 915) == 15, r.replaced
    asked = [i for _, _, i in r.replaced]
    assert asked == [40.0, 80.0, 160.0, 320.0, 640.0] + [900.0] * 10, r.replaced
    for _, waited, interval in r.replaced:
        assert interval <= waited < interval + 1.01, r.replaced
    for (t0, _, _), (t1, _, i1) in zip(r.replaced, r.replaced[1:]):
        assert t1 - t0 >= i1 + d4.CONNECT_SYNC_S - 1e-6, r.replaced
    assert r.ib.violations == 0 and r.ad.outages.history == [] and r.ad.outages.open is not None
    assert len([m for m in r.sent if "DOWN for over" in m]) == 1 and not [m for m in r.sent if "RECONNECTED" in m]


def test_s2_the_schedule_starts_over_when_the_outage_turns_plain(tmp_path, monkeypatch):
    """three replacements (40, 80, 160 s: the next would wait 320 s), then the gateway goes away - the session's FIN,
    connects refused: no session at all, a plain outage (the ledger's cause cleared). When it comes back, still
    never answering, the first unsynced session of that spell is replaced 40 s after its connect again, then 80 s -
    the schedule restarted (_reconnect's failure branch). 170191c0: no replacement after the first, before or after."""
    r = d4._rig(tmp_path, monkeypatch)
    _replaced_on_vt(r)
    _nightly_drop(r, lambda n: None)
    _idle(r, 40 + 80 + 160 + 3 * 15 + 30)
    assert len(r.replaced) == 3 and [i for _, _, i in r.replaced] == [40.0, 80.0, 160.0], r.replaced
    r.ib.gateway_up = False
    r.ib.drop()
    _idle(r, 60)                                        # refused: plain, the cause cleared
    assert r.ad.outages.open is not None and r.ad.outages.open.get("kind") is None
    assert not r.ad.ib.isConnected() and r.ad._unsynced_replacements == 0
    r.ib.gateway_up = True                              # back - and still never answering the sync
    n = len(r.replaced)
    _idle(r, 30 + 15 + 40 + 15 + 80 + 15)
    assert r.ad.outages.open.get("kind") == d4.UNSYNCED
    assert [i for _, _, i in r.replaced[n:]] == [40.0, 80.0], r.replaced
    for _, waited, interval in r.replaced[n:]:
        assert interval <= waited < interval + 1.01, r.replaced
    assert r.ib.violations == 0 and r.ad.outages.history == []         # all one outage


def test_s3_the_schedule_starts_over_when_the_outage_ends(tmp_path, monkeypatch):
    """an outage whose first three sessions lose their answer ends on the fourth (replacements at 40, 80, 160 s); the
    next outage, whose first two sessions lose theirs, is replaced at 40 then 80 s again - not at 320 s. 170191c0: the
    first outage never ends (its second session is kept for good)."""
    r = d4._rig(tmp_path, monkeypatch)
    _replaced_on_vt(r)
    _nightly_drop(r, lambda n: None if n <= 3 else 0)
    _idle(r, 40 + 80 + 160 + 4 * 15 + 30)
    assert not r.ad.outages.open and len(r.ad.outages.history) == 1 and r.ad._disconnected_since is None, \
        r.replaced
    assert [i for _, _, i in r.replaced] == [40.0, 80.0, 160.0], r.replaced
    n = len(r.replaced)
    first = r.ib.n_sessions
    r.ib.policy = lambda k: None if k <= first + 2 else 0
    r.ib.drop()
    _idle(r, 40 + 80 + 3 * 15 + 30)
    assert [i for _, _, i in r.replaced[n:]] == [40.0, 80.0], r.replaced
    assert not r.ad.outages.open and len(r.ad.outages.history) == 2
    assert r.ib.violations == 0 and not [m for m in r.sent if "DOWN" in m]


# ============================================================================== part W: the words
def test_w1_the_kill_alert_names_the_keepalives_reconnect_stall():
    """the verifier's NOTE 3: between two ticks the loop's keepalive can be inside one reconnect attempt - 15 s against
    a gateway at its login prompt (ib_async waits out the handshake even after the peer closes), or for a fresh
    session whose start-up sync does not end. The /kill alert's bound did not say so."""
    import app.service as svc
    bound = svc.MIRROR_KILL_BOUND
    assert "keepalive" in bound and "login prompt" in bound and "up to 15s" in bound, bound
    assert "open-orders read can first wait up to 20s" in bound                  # round 4's words stay
