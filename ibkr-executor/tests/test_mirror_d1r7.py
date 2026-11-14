"""D1 round 7 - the K5 recovery notice names every cause the outage had; the DOWN page words the wait as it runs
(2026-11-14).

Round 6's independent verifier (FIX-THEN-SHIP: one MINOR, four NOTEs, behaviour neutrality proven) found the recovery
notice worded from the outage's LAST cause: an outage paged as plain ("cannot read the account or trade") that ended
through a short K5 tail was announced as "open orders were unreadable ... positions and cash were read" - false for
most of the outage and contradicting the page - and the converse (a K5 page, then a spell with no session) ended with
the plain words. This round changes no connection, schedule, backoff, ledger or order behaviour: only the notice's and
the DOWN page's words and the state that chooses them (IBAdapter._outage_had_no_session / _outage_had_unsynced: set
where a spell of each kind is seen and where the page states its cause, reset when the outage closes), docstrings,
comments and composer/IBKR_MIRROR.md.

Everything runs on the simulated clock: test_mirror_d1r4's rig (the REAL MirrorManager over the REAL IBAdapter on
PendingIB at production values), the idle night as the service loop runs it (the keepalive every 300 s), external
events (a FIN, a gateway refusing or accepting again) fired at their instants while the loop is parked.

  N  THE RECOVERY NOTICE (_recovered): it names every cause the outage had - both, each "at times", when it had both -
     so it is true of the whole outage and the cause its DOWN page stated is always among them
       n1  GATE  a plain page, then a K5 tail (the first session back loses its answer), then a sync - mirror and
                 blend (952177f: the K5 words alone, "positions and cash were read", where the page had said the
                 account could not be read and for ~40 of the 45 minutes it could not)
       n2  GATE  a K5 page, then each reconnect after a replacement refused once (IB's 326), then a heal - mirror
                 and blend (952177f: the plain words, "could not read the account", after a page that said positions
                 and cash ARE read)
       n3  GATE  a K5 page, then a gateway-only restart (FIN, connects refused 30 s), then a sync - mirror and blend
       n4  GATE  _recovered over the recorded state, every wording: mirror/blend x RECONNECTED/READABLE again x the
                 two orders of the causes. (READABLE again - no reconnect - cannot come with a spell with no session
                 through the adapter, since only a reconnect ends one; its words are pinned all the same)
       n7  GATE  the cause the page stated is named even when nothing else recorded it (_maybe_outage_alert's own
                 record), for both page kinds
       n8  GATE  the boot's session never syncs, then the gateway goes down: the plain page, then a sync (the boot
                 connect's record)
       n9  GATE  n1's night with the reconnect after the K5 session's replacement refused once (a reconnect's record)
       n10 GATE  a K5 page, then a session lost inside the reconnect backoff - no connect ever refused (the
                 backoff wait's record)
       n5  TWIN  single-cause outages keep their words to the letter: K5 only, cured by a replacement (RECONNECTED)
                 or healed on the boot session (READABLE again); plain only - mirror and blend
       n6  TWIN  an outage that was never paged sends no notice, whatever its causes, and leaves none to the next
  P  THE DOWN PAGE's wait (_maybe_outage_alert)
       p1  GATE  the 326 world: the page says the wait goes back to 40 s after a failed connect (952177f: "doubles
                 each time", where every wait was 40 s)
       p2  GATE  a never-answering night: the page's sentence to the letter
       p3  TWIN  the first 60 characters of every DOWN page (mirror/blend x K5/plain) are unchanged, and every page
                 fits alerts.send's 4000-character cut
"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest

import app.ib_adapter as ib_mod
import test_mirror as tm
import test_mirror_d1r4 as d4
from test_mirror_connection import D2

POLL_S = 300.0                                          # settings.poll_seconds: the idle loop's park
REC_RE = re.compile(r"^🧬 IB gateway (RECONNECTED after (\d+) min — executor resumed|open orders READABLE again after "
                    r"(\d+) min — the session's late open-orders sync ended \(no reconnect was needed\): executor "
                    r"resumed)(.*)$", re.S)
K5_MIRROR = (" (open orders were unreadable, so the Composer mirror could not trade or flatten meanwhile; positions "
             "and cash were read; it keeps no resting stops at the venue)")
K5_BLEND = (" (open orders were unreadable, so cycles were failing closed meanwhile; positions and cash were read; GTC "
            "stops rested at the venue throughout)")
PLAIN_MIRROR = " (the Composer mirror could not read the account or trade meanwhile; it keeps no resting stops at the venue)"
PLAIN_BLEND = " (cycles were failing closed meanwhile; GTC stops rested at the venue throughout)"
BOTH_MIRROR = (" (the Composer mirror could not trade or flatten meanwhile: at times no gateway session was up, so the "
               "account could not be read; at others open orders were unreadable while positions and cash were read; "
               "it keeps no resting stops at the venue)")
BOTH_BLEND = (" (cycles were failing closed meanwhile: at times no gateway session was up, so the account could not be "
              "read; at others open orders were unreadable while positions and cash were read; GTC stops rested at "
              "the venue throughout)")
WORDS = {(True, "k5"): K5_MIRROR, (False, "k5"): K5_BLEND, (True, "plain"): PLAIN_MIRROR,
         (False, "plain"): PLAIN_BLEND, (True, "both"): BOTH_MIRROR, (False, "both"): BOTH_BLEND}


# ============================================================================== the rig
def _rig(tmp_path, monkeypatch, mirror_only=True):
    """test_mirror_d1r4's rig (the mirror's adapter: mirror_only, its 30 s backoff cap), or the blend's adapter: its
    words and the default 300 s cap"""
    r = d4._rig(tmp_path, monkeypatch)
    if not mirror_only:
        r.ad.mirror_only, r.ad.reconnect_backoff_max_s = False, ib_mod.RECONNECT_BACKOFF_MAX_S
    return r


def _spy(r, monkeypatch):
    """accepted / refused connect instants and the replacements' instants"""
    s = {"accepted": [], "refused": [], "replaced": []}
    real_connect = r.ib.connect

    def connect(*a, **k):
        try:
            out = real_connect(*a, **k)
        except Exception:
            s["refused"].append(r.clock.now)
            raise
        s["accepted"].append(r.clock.now)
        return out
    monkeypatch.setattr(r.ib, "connect", connect)
    spend = r.ad._spend_unsynced_replacement

    def spent():
        s["replaced"].append(r.clock.now)
        spend()
    r.ad._spend_unsynced_replacement = spent
    return s


def _refuse_after_adapter_drops(r, monkeypatch, s, active=lambda: True):
    """IB's 326 (the round-5 verifier's v4): the connect made right after THIS adapter dropped a session is refused
    once, while active(); the next attempt, one backoff later, is accepted"""
    st = {"next": False, "n": 0}
    real = r.ib.connect

    def connect(*a, **k):
        if st["next"]:
            st["next"] = False
            st["n"] += 1
            s["refused"].append(r.clock.now)
            raise ConnectionRefusedError("326 Unable to connect as the client id is already in use (simulated)")
        return real(*a, **k)
    monkeypatch.setattr(r.ib, "connect", connect)
    drop = r.ad._drop_session

    def dropped():
        st["next"] = bool(active())
        drop()
    r.ad._drop_session = dropped
    return st


def _night_start(r, policy, at="23:45:00"):
    """the nightly drop: from `at` every new session follows policy(n)"""
    r.vt.advance((tm.at(at, tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = policy
    r.ib.drop()
    return r.clock.now


def _idle(r, until, events=(), every=POLL_S):
    """the idle night as the service loop runs it: the keepalive every `every` s until `until`; events =
    [(instant, fn)] fired at their instants while the loop is parked"""
    events = sorted(events, key=lambda e: e[0])
    while r.clock.now < until:
        r.ad.keepalive()
        park_end = r.clock.now + timedelta(seconds=every)
        while events and events[0][0] <= park_end:
            t, fn = events.pop(0)
            r.vt.advance((t - r.clock.now).total_seconds())
            fn()
        r.vt.advance((park_end - r.clock.now).total_seconds())


def _downs(r):
    return [m for m in r.sent if "DOWN for over" in m]


def _recs(r):
    return [m for m in r.sent if "RECONNECTED" in m or "READABLE" in m]


def _kind(page):
    """the cause a DOWN page states: 'k5' (logged in, open orders unreadable) or 'plain' (nothing can be read)"""
    if "open orders unreadable (positions and cash are read normally)" in page:
        return "k5"
    assert "cannot read the account or trade" in page or "executor is failing closed" in page, page
    return "plain"


def _notice(r):
    """(RECONNECTED or READABLE, the words in brackets) of the outage's one recovery notice"""
    recs = _recs(r)
    assert len(recs) == 1, r.sent
    m = REC_RE.match(recs[0])
    assert m, recs[0]
    return ("RECONNECTED" if m.group(1).startswith("RECONNECTED") else "READABLE"), m.group(4)


def _names_the_paged_cause(page, words):
    """the notice never contradicts the page: the cause the page stated is one the notice names"""
    if _kind(page) == "k5":
        return "open orders were unreadable" in words and "positions and cash were read" in words
    return words in (PLAIN_MIRROR, PLAIN_BLEND) or "no gateway session was up" in words


# ============================================================================== N: the recovery notice
@pytest.mark.parametrize("mirror_only", [True, False])
def test_n1_a_plain_page_then_a_k5_tail_is_announced_with_both_causes(tmp_path, monkeypatch, mirror_only):
    """GATE (the round-6 verifier's w4, and its blend twin). The gateway refuses connects from 23:45 - the plain page
    at 00:20 - and is back at 00:20:30, still warming up: its FIRST session loses its connect-time answer, is
    replaced, and the next one syncs. 952177f: 'open orders were unreadable ... positions and cash were read' - the
    page had said the account could not be read, and for ~40 of the 45 minutes it could not. Now: both causes."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    r.ib.gateway_up = False
    _night_start(r, lambda n: None if n == 1 else 0)
    paged_before_back = []

    def back():
        paged_before_back.extend(_downs(r))
        r.ib.gateway_up = True
    _idle(r, tm.at("01:30:00", D2), [(tm.at("00:20:30", D2), back)])
    assert len(paged_before_back) == 1 and _kind(paged_before_back[0]) == "plain", r.sent
    assert len(_downs(r)) == 1, r.sent
    assert s["refused"] and len(s["accepted"]) == 2 and len(s["replaced"]) == 1, s     # the K5 tail: one session
    how, words = _notice(r)
    assert how == "RECONNECTED", r.sent
    assert words == WORDS[(mirror_only, "both")], words
    assert _names_the_paged_cause(paged_before_back[0], words)
    assert not r.ad.outages.open and r.ad.outages.history and r.ib.violations == 0


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n2_a_k5_page_then_refused_reconnects_then_a_heal_is_announced_with_both_causes(tmp_path, monkeypatch,
                                                                                         mirror_only):
    """GATE (the round-6 verifier's w5, and its blend twin). The gateway never answers a new session's connect-time
    request from 23:45 and refuses the reconnect made right after each replacement's drop once (IB's 326); at 01:00
    it answers again. The page (00:15-00:20) says logged in, positions and cash read normally - the open orders not.
    952177f: the outage's last spell had no session, so the notice said 'could not read the account or trade',
    contradicting the page. Now: both causes."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    st = _refuse_after_adapter_drops(r, monkeypatch, s)
    heal = tm.at("01:00:00", D2)
    _night_start(r, lambda n: None if r.clock.now < heal else 0)
    _idle(r, tm.at("02:30:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5", r.sent
    assert st["n"] >= 2 and s["replaced"], (st, s)
    how, words = _notice(r)
    assert how == "RECONNECTED"
    assert words == WORDS[(mirror_only, "both")], words
    assert _names_the_paged_cause(downs[0], words)
    assert not r.ad.outages.open and r.ib.violations == 0


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n2_the_326_spell_starting_after_the_k5_page(tmp_path, monkeypatch, mirror_only):
    """GATE (n2 with the order made explicit): no refusal until the K5 page has gone out (never answering from 23:45;
    from 00:30 each reconnect after a replacement's drop is refused once); the gateway answers again at 01:30"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    from_at, heal = tm.at("00:30:00", D2), tm.at("01:30:00", D2)
    st = _refuse_after_adapter_drops(r, monkeypatch, s, active=lambda: r.clock.now >= from_at)
    _night_start(r, lambda n: None if r.clock.now < heal else 0)
    _idle(r, tm.at("03:00:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5", r.sent
    assert st["n"] >= 1 and all(t >= from_at for t in s["refused"]), (st, s["refused"])
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "both")], words
    assert _names_the_paged_cause(downs[0], words)


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n3_a_k5_page_then_a_gateway_only_restart_is_announced_with_both_causes(tmp_path, monkeypatch, mirror_only):
    """GATE (the round-6 verifier's w6, and its blend twin). Never answering from 23:45 - the K5 page - then at
    00:59:50 the gateway restarts: its FIN, connects refused for 30 s, then it accepts and answers. 952177f: the
    plain words after the K5 page. Now: both causes."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    _night_start(r, lambda n: None)
    _idle(r, tm.at("00:59:50", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5", r.sent
    r.ib.policy = lambda n: 0
    r.ib.drop()                                        # the gateway's FIN
    r.ib.gateway_up = False
    r.vt.advance(10.0)
    r.ad.keepalive()                                   # the attempt the FIN triggers: refused
    r.vt.advance(30.0)
    r.ib.gateway_up = True
    _idle(r, tm.at("02:00:00", D2))
    assert s["refused"], s
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "both")], words
    assert _names_the_paged_cause(downs[0], words)
    assert not r.ad.outages.open and r.ib.violations == 0


def _bare(monkeypatch, mirror_only, reconnected, last_unsynced, had_no_session, had_unsynced, alerted=True):
    """an adapter at the instant _recovered closes an outage, its recorded state set by hand (no session machinery)"""
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    a = ib_mod.IBAdapter.__new__(ib_mod.IBAdapter)
    a.outages, a.mirror_only = None, mirror_only
    a._disconnected_since, a._outage_alerted = 1000.0, alerted
    a._open_orders_unsynced, a._outage_reconnected = last_unsynced, reconnected
    a._outage_had_no_session, a._outage_had_unsynced = had_no_session, had_unsynced
    a._recovered(1000.0 + 3600.0)
    assert a._disconnected_since is None and a._outage_alerted is False
    return sent, a


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("reconnected", [True, False])
@pytest.mark.parametrize("order", ["plain_then_k5", "k5_then_plain"])
def test_n4_every_wording_of_an_outage_with_both_causes(monkeypatch, mirror_only, reconnected, order):
    """GATE (_recovered over the recorded state). An outage that had a spell with no session AND a session whose
    open orders could not be read is announced with both, whichever came last; its causes are cleared with it.
    952177f worded it from the last cause alone: the K5 words after 'plain_then_k5', the plain ones after
    'k5_then_plain'."""
    last_unsynced = order == "plain_then_k5"
    sent, a = _bare(monkeypatch, mirror_only, reconnected, last_unsynced, True, True)
    assert len(sent) == 1, sent
    m = REC_RE.match(sent[0])
    assert m, sent[0]
    if reconnected:
        assert sent[0].startswith("🧬 IB gateway RECONNECTED after 60 min — executor resumed ("), sent[0]
    else:
        assert sent[0].startswith("🧬 IB gateway open orders READABLE again after 60 min — "), sent[0]
    assert m.group(4) == WORDS[(mirror_only, "both")], sent[0]
    assert ("GTC" in sent[0]) is (not mirror_only)
    assert a._outage_had_no_session is False and a._outage_had_unsynced is False      # the next outage starts clean


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("paged", ["k5", "plain"])
def test_n7_the_cause_the_page_stated_is_named_even_if_nothing_else_recorded_it(monkeypatch, mirror_only, paged):
    """GATE (_maybe_outage_alert records the cause its page states). The page goes out with one cause; afterwards the
    outage's state shows only the other one (the page's own cause recorded nowhere else): the notice still names the
    page's - both. 952177f: the last cause alone, contradicting the page."""
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    a = ib_mod.IBAdapter.__new__(ib_mod.IBAdapter)
    a.outages, a.mirror_only = None, mirror_only
    a._disconnected_since, a._outage_alerted, a._unsynced_sessions = 1000.0, False, 0
    a._open_orders_unsynced, a._outage_reconnected = paged == "k5", True
    a._maybe_outage_alert(1000.0 + ib_mod.OUTAGE_ALERT_S + 1.0)
    assert len(sent) == 1 and _kind(sent[0]) == paged, sent
    if paged == "k5":                                  # then a spell with no session, as _reconnect records it
        a._open_orders_unsynced, a._outage_had_no_session = False, True
    else:                                              # then a session whose sync does not end (the flag alone)
        a._open_orders_unsynced = True
    a._recovered(1000.0 + 3600.0)
    assert len(sent) == 2, sent
    m = REC_RE.match(sent[1])
    assert m and m.group(4) == WORDS[(mirror_only, "both")], sent[1]
    assert _names_the_paged_cause(sent[0], m.group(4))


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n8_a_boot_session_that_never_syncs_then_a_plain_page_is_announced_with_both_causes(tmp_path, monkeypatch,
                                                                                            mirror_only):
    """GATE (the boot connect records its unsynced session). The service boots at 23:45 into a gateway that never
    answers the connect-time request; at 23:45:30, before any replacement, the gateway goes down (FIN, connects
    refused); the plain page; at 00:40 it is back and answers. 952177f: the plain words alone - but for the boot
    session's spell positions and cash WERE read."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None if r.clock.now < tm.at("00:40:00", D2) else 0
    r.ib.disconnect()                                   # a restart: the old process's session is gone
    d4._REAL_CONNECT(r.ad)                              # the service's own boot connect: unsynced
    assert r.ad.outages.open.get("kind") == d4.UNSYNCED
    r.vt.advance(15.0)
    r.ib.drop()
    r.ib.gateway_up = False
    _idle(r, tm.at("01:30:00", D2), [(tm.at("00:40:00", D2), lambda: setattr(r.ib, "gateway_up", True))])
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "plain" and not s["replaced"] and s["refused"], (r.sent, s)
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "both")], words


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n9_a_plain_page_then_a_k5_session_then_a_refused_reconnect_is_announced_with_both_causes(tmp_path,
                                                                                                  monkeypatch,
                                                                                                  mirror_only):
    """GATE (a reconnect records its unsynced session). n1's night, but the reconnect made right after the K5
    session's replacement is refused once (IB's 326), so the outage's LAST spell, again, has no session. 952177f: the
    plain words alone - but for the K5 session's spell positions and cash WERE read."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    back_at = tm.at("00:20:30", D2)
    st = _refuse_after_adapter_drops(r, monkeypatch, s, active=lambda: r.clock.now >= back_at)
    r.ib.gateway_up = False
    _night_start(r, lambda n: None if n == 1 else 0)
    _idle(r, tm.at("01:30:00", D2), [(back_at, lambda: setattr(r.ib, "gateway_up", True))])
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "plain", r.sent
    assert st["n"] == 1 and len(s["replaced"]) == 1 and len(s["accepted"]) == 2, (st, s)
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "both")], words


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n10_a_k5_session_lost_inside_the_backoff_is_a_spell_with_no_session(tmp_path, monkeypatch, mirror_only):
    """GATE (_reconnect records a wait for the backoff with no session). Never answering from 23:45 - the K5 page;
    at 00:40 a FIN, and the keepalive reconnects (an unsynced session again); 10 s later the gateway closes that one
    too and a read meets the backoff with no session; the gateway then answers, and the next session syncs. No
    connect was ever refused. 952177f: the K5 words alone (the last session's sync had not ended)."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    _night_start(r, lambda n: None)
    _idle(r, tm.at("00:40:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5", r.sent
    n0 = len(s["accepted"])
    r.ib.drop()
    while len(s["accepted"]) == n0:                     # the keepalive's reconnect, once the backoff allows it
        r.ad.keepalive()
        r.vt.advance(1.0)
    assert r.ad._open_orders_unsynced and r.ad._next_reconnect_ts > r.vt.now() + 5.0
    r.vt.advance(5.0)
    r.ib.drop()                                         # inside the backoff: no reconnect is attempted
    with pytest.raises(ib_mod.ExecutorConnectionError):
        r.ad.positions_snapshot()
    assert len(s["accepted"]) == n0 + 1 and not s["refused"]
    r.ib.policy = lambda n: 0                           # the gateway answers again
    _idle(r, tm.at("02:00:00", D2))
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "both")], words
    assert not s["refused"] and not r.ad.outages.open


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n5_twin_a_k5_only_outage_cured_by_a_replacement_keeps_the_k5_words(tmp_path, monkeypatch, mirror_only):
    """TWIN (passes on 952177f and after): never answering from 23:45, the K5 page, then the gateway answers again at
    01:00 with no FIN and no refusal - the next replacement syncs. No spell without a session: the K5 words alone"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    heal = tm.at("01:00:00", D2)
    _night_start(r, lambda n: None if r.clock.now < heal else 0)
    _idle(r, tm.at("03:00:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5" and not s["refused"], (r.sent, s)
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "k5")], words


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n5_twin_a_k5_outage_healed_on_the_boot_session_says_readable_again_with_the_k5_words(tmp_path, monkeypatch,
                                                                                               mirror_only):
    """TWIN (the round-6 verifier's w7): the boot session's sync never ends and nothing replaces it (only position
    and cash reads run); the K5 page; then its late end lands - READABLE again, the K5 words alone"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = lambda n: None
    r.ib.disconnect()
    d4._REAL_CONNECT(r.ad)                             # the service's own boot connect
    for _ in range(7):                                 # 35 min of position reads only
        r.vt.advance(300.0)
        r.ad._require_live()
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5", r.sent
    r.ib.oo_end = r.vt.now() + 1.0
    r.vt.advance(2.0)
    r.ad._require_live()
    how, words = _notice(r)
    assert how == "READABLE" and words == WORDS[(mirror_only, "k5")], words


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n5_twin_a_plain_only_outage_keeps_the_plain_words_to_the_letter(tmp_path, monkeypatch, mirror_only):
    """TWIN (the round-6 verifier's w3): the gateway refuses connects from 23:45 to 00:25, then a healthy session -
    no session whose open orders could not be read: the plain words, to the letter"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    r.ib.gateway_up = False
    _night_start(r, lambda n: 0)
    _idle(r, tm.at("00:25:00", D2))
    r.ib.gateway_up = True
    _idle(r, tm.at("01:30:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "plain", r.sent
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "plain")], words


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("state", [(True, True, True), (False, True, True), (True, True, False), (False, False, True)])
def test_n6_twin_an_outage_that_was_never_paged_sends_no_notice(monkeypatch, mirror_only, state):
    """TWIN (passes on 952177f and after): whatever the outage's causes, no page - no notice"""
    last_unsynced, had_no_session, had_unsynced = state
    sent, _ = _bare(monkeypatch, mirror_only, True, last_unsynced, had_no_session, had_unsynced, alerted=False)
    assert sent == []


@pytest.mark.parametrize("mirror_only", [True, False])
def test_n6_twin_a_short_mixed_outage_sends_nothing_and_leaves_no_cause_to_the_next(tmp_path, monkeypatch,
                                                                                    mirror_only):
    """TWIN (passes on 952177f and after), through the adapter: the gateway refuses connects from 23:45 to 23:50, its
    first session back loses its answer and is replaced, the next syncs - closed well inside 30 min: no page, no
    notice. At 02:00 a K5-only outage (never answering, no refusal, no FIN) pages and heals at 03:00: its notice has
    the K5 words alone - the short outage's spell with no session is not carried into it"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    r.ib.gateway_up = False
    _night_start(r, lambda n: None if n == 1 else 0)
    _idle(r, tm.at("00:30:00", D2), [(tm.at("23:50:30", tm.DAY), lambda: setattr(r.ib, "gateway_up", True))])
    assert s["refused"] and s["replaced"] and not r.ad.outages.open and len(r.ad.outages.history) == 1, s
    assert r.sent == [], r.sent
    r.vt.advance((tm.at("02:00:00", D2) - r.clock.now).total_seconds())
    heal = tm.at("03:00:00", D2)
    r.ib.policy = lambda n: None if r.clock.now < heal else 0
    r.ib.drop()
    _idle(r, tm.at("04:30:00", D2))
    downs = _downs(r)
    assert len(downs) == 1 and _kind(downs[0]) == "k5" and len(r.ad.outages.history) == 2, r.sent
    how, words = _notice(r)
    assert how == "RECONNECTED" and words == WORDS[(mirror_only, "k5")], words


# ============================================================================== P: the DOWN page's wait
NEW_WAIT = (" another is tried at the executor's next check once the wait and the reconnect backoff have passed (the "
            "wait 40 s at first, doubling with each replacement up to 15 min, back to 40 s after a failed connect), "
            "until one syncs.")
# (the final cross-patch review's NOTE: a replacement also waits out the reconnect backoff - up to 300 s with the
# blend or the ladder on - so the page names both)
# (round 7's review NOTE: the wait is the replacement interval; when idle the next session comes only at the next
# keepalive once it has passed - 300, 300, 300, 600, 900 s on a real-socket night - so the page says "at the
# executor's next check once a wait has passed", not "after a wait")


def _night_until_the_page(r, until_hms="00:30:00"):
    """the keepalive every 300 s until `until_hms` on day 2; returns (the one DOWN page, the sessions the gateway had
    accepted when it went out)"""
    page = []
    until = tm.at(until_hms, D2)
    while r.clock.now < until:
        n0 = len(r.sent)
        r.ad.keepalive()
        page += [(m, r.ib.n_sessions) for m in r.sent[n0:] if "DOWN for over" in m]
        r.vt.advance(POLL_S)
    assert len(page) == 1, r.sent
    return page[0]


@pytest.mark.parametrize("mirror_only", [True, False])
def test_p1_the_326_worlds_page_says_the_wait_goes_back_to_40s(tmp_path, monkeypatch, mirror_only):
    """GATE. Never answering from 23:45, each reconnect after a replacement's drop refused once: every failed connect
    restarts the schedule, so every wait is 40 s. 952177f's page: 'after a wait that doubles each time, up to 15
    min'. Now the wait as it runs: 40 s at first, doubling with each replacement, back to 40 s after a failed
    connect. The count (round 6) is unchanged."""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    s = _spy(r, monkeypatch)
    st = _refuse_after_adapter_drops(r, monkeypatch, s)
    _night_start(r, lambda n: None)
    page, sessions = _night_until_the_page(r)
    assert _kind(page) == "k5" and st["n"] >= 2, (page, st)
    assert "doubles each time" not in page, page
    assert f" {sessions - 1} fresh gateway sessions were already tried and none synced;{NEW_WAIT}" in page, page
    assert r.ib.violations == 0


@pytest.mark.parametrize("mirror_only", [True, False])
def test_p2_a_never_answering_nights_page_words_the_wait_to_the_letter(tmp_path, monkeypatch, mirror_only):
    """GATE: no refusal, no FIN - the waits really double (40, 80, 160, 320 s by 00:15), and the page says how the
    wait runs, the restart included; its first sentence and its remedy are what they were"""
    r = _rig(tmp_path, monkeypatch, mirror_only)
    _night_start(r, lambda n: None)
    page, sessions = _night_until_the_page(r)
    assert sessions == 5 and _kind(page) == "k5", (sessions, page)
    assert f" 4 fresh gateway sessions were already tried and none synced;{NEW_WAIT} Restart the gateway (Render → " \
           f"ibkr-executor → Restart service, then approve the IBKR push)." in page, page
    assert page.endswith(" Restart the gateway (Render → ibkr-executor → Restart service, then approve the IBKR "
                         "push)."), page


FIRST60 = {
    (True, "k5"): "🚨 IB gateway DOWN for over 30 min for trading — logged in, b",
    (False, "k5"): "🚨 IB gateway DOWN for over 30 min for trading — logged in, b",
    (True, "plain"): "🚨 IB gateway DOWN for over 30 min — the Composer mirror cann",
    (False, "plain"): "🚨 IB gateway DOWN for over 30 min — executor is failing clos",
}


def _page(monkeypatch, mirror_only, unsynced, sessions):
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    a = ib_mod.IBAdapter.__new__(ib_mod.IBAdapter)
    a.outages, a.mirror_only = None, mirror_only
    a._disconnected_since, a._outage_alerted = 1000.0, False
    a._open_orders_unsynced, a._unsynced_sessions = unsynced, sessions
    a._maybe_outage_alert(1000.0 + ib_mod.OUTAGE_ALERT_S + 1.0)
    assert len(sent) == 1 and a._outage_alerted is True
    return sent[0]


@pytest.mark.parametrize("mirror_only", [True, False])
@pytest.mark.parametrize("kind", ["k5", "plain"])
@pytest.mark.parametrize("sessions", [0, 1, 2, 3, 70])
def test_p3_twin_every_pages_first_60_characters_and_length(monkeypatch, mirror_only, kind, sessions):
    """TWIN (passes on 952177f and after): the first 60 characters of every DOWN page are unchanged (whatever keys
    on them), and every page fits alerts.send's 4000-character cut"""
    page = _page(monkeypatch, mirror_only, kind == "k5", sessions)
    assert page[:60] == FIRST60[(mirror_only, kind)], page[:60]
    assert len(page) < 4000 and _kind(page) == kind
