"""Gate tests for the TRANSFER-ONLY credential of POST /mirror/transfer (MIRROR_TRANSFER_TOKEN,
MIRROR_TRANSFER_MAX_FRAC; app/service.py, app/mirror.py, app/config.py; composer/IBKR_MIRROR.md).

The daily POLICY routine mirrors a Composer capital move on the executor the same day and must not
hold EXEC_TOKEN (which can also /kill). Each gate has its broken twin on the other side.

  X1  the token in the X-Transfer-Token header queues a transfer on a paper book and on a live book,
      marked "via": "transfer_token"; EXEC_TOKEN works as before, unmarked and uncapped
  X2  the token opens nothing else: every other mutating route, /status and the feed refuse it; it is
      never read from a query parameter or from the exec header
  X3  a wrong or absent token gets exactly the answer a bad exec token gets (whether the feature is
      on is not revealed); with the mirror off the route is the 404 it was, before any auth
  X4  the feature is off when the token is empty, shorter than 24 characters, or equal to EXEC_TOKEN
      or READ_TOKEN - and the last three are said once at boot, at warning level, without the token
  X5  the daily cap: the day's total by token never passes max_frac x the book's published equity;
      it survives a restart, resets on a new ET date (ET, not UTC), is per book, is not consumed by
      a refused request or by an exec-authorised one, and holds under concurrent requests; a book
      with no computable equity takes none; an unreadable total refuses; an old book (no total file)
      starts at zero
  X6  every transfer taken by the token is alerted at warning level with the day's used and cap; the
      note stays one line
  X7  the session applies a transfer queued by the token exactly like an exec-authorised one
  X8  settings: blank = default, clamped to 0..1; the deploy file declares both keys

The independent review's findings (each gate below failed at c740d160):

  T1  nothing below $1 is taken by the token, and the amount is rounded to cents before it is counted
  T2  at most 6 transfers by token per book per cap period; refusals are logged, alerted a few times
  T3  the cap period ends when the ET date has changed AND the book has run a session since (the x5
      "period" gates): a weekend or a midnight is one allowance; a total dated in the future refuses;
      a total written before the session key loads
  T4  a refusal tells the token's holder nothing about the book (no equity, cap, total, path or name);
      the specifics go to the log and the alert; the public schema does not describe the token
  T5  control characters never reach the note
"""
from __future__ import annotations

import json
import logging
import os
import threading

import pytest
from fastapi.testclient import TestClient

from app import mirror as mm
from app import mirror_core as mc
from app.config import Settings, settings
from tests.test_mirror import PX, Rig, at, invested, payload, sound

EXEC = "sekrit-exec"
READ = "sekrit-read"
TT = "transfer-only-token-0123456789abcdef"            # 36 characters
H = {"X-Transfer-Token": TT}
E = {"X-Exec-Token": EXEC}
MOVE = {"from": "HG", "to": "HARV", "amount": 1000.0, "note": "POLICY op 1"}
OVER = "refused: over the day's transfer allowance"       # all a holder of the token is told (T4)
BUSY = "refused: transfers by token are unavailable for this book right now"
INVALID = "refused: not a valid transfer"


def _service(monkeypatch, books, **over):
    """the service's app over ready-made books (no loop thread: these routes only queue)"""
    from app import service
    monkeypatch.setattr(settings, "exec_token", over.pop("exec_token", EXEC))
    monkeypatch.setattr(settings, "read_token", over.pop("read_token", READ))
    monkeypatch.setattr(settings, "tws_userid", over.pop("tws_userid", ""))
    monkeypatch.setattr(settings, "tws_password", over.pop("tws_password", ""))
    monkeypatch.setattr(settings, "mirror_transfer_token", over.pop("mirror_transfer_token", TT))
    monkeypatch.setattr(settings, "mirror_transfer_max_frac", over.pop("mirror_transfer_max_frac", 0.25))
    assert not over
    monkeypatch.setattr(service, "MIRROR", dict(books))
    monkeypatch.setattr(service, "MGR", None)
    monkeypatch.setattr(service, "BLEND", None)
    sent = []
    monkeypatch.setattr(service, "send", sent.append)
    return TestClient(service.app), service, sent


def paper(tmp_path, **kw):
    r = Rig(tmp_path, **kw)
    r.tick("15:00")                                       # the sleeves are seeded: $100,000 of equity, all cash
    return r


def equity(book):
    return book.view()["book"]["equity"]


def inbox(book):
    try:
        with open(book._inbox_path()) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def post(c, body=MOVE, headers=H, **kw):
    return c.post("/mirror/transfer", json=body, headers=headers, **kw)


# --- X1 ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("live", [False, True], ids=["paper", "live"])
def test_x1_the_token_queues_a_transfer_on_a_paper_book_and_on_a_live_book(tmp_path, monkeypatch, live):
    r = invested(tmp_path) if live else paper(tmp_path)
    name = "live" if live else "dry"
    c, _, sent = _service(monkeypatch, {name: r.m})
    got = post(c)
    assert got.status_code == 200, got.text
    out = got.json()
    assert out["ok"] and out["book"] == name
    req = out["request"]
    assert req["kind"] == "transfer" and req["via"] == "transfer_token" and req["id"].startswith("transfer-")
    assert (req["from"], req["to"], req["amount"], req["note"]) == ("HG", "HARV", 1000.0, "POLICY op 1")
    assert req["day"] == "2026-11-10" and req["day_used"] == 1000.0
    assert req["day_cap"] == pytest.approx(0.25 * equity(r.m), abs=0.01)
    assert inbox(r.m) == [req]                            # queued for the loop, the mark with it
    assert len(sent) == 1


def test_x1_exec_auth_is_what_it_was_unmarked_uncapped_and_not_counted(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    big = dict(MOVE, amount=60_000.0)                     # 60% of the book: far beyond the token's 25%
    for kw in ({"headers": E}, {"headers": {}, "params": {"token": EXEC}}):
        got = post(c, big, **kw)
        assert got.status_code == 200, got.text
        req = got.json()["request"]
        assert set(req) == {"kind", "from", "to", "amount", "note", "id", "utc"}        # the row it always was
    assert sent == []                                     # no alert for the operator's own request, as before
    assert not os.path.exists(r.m._transfer_day_path())   # nothing counted
    assert post(c, dict(MOVE, amount=25_000.0)).status_code == 200                      # the token's whole day is still there
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400                           # the twin: now it is used up


def test_x1_a_request_carrying_both_credentials_is_treated_as_the_tokens(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    got = post(c, dict(MOVE, amount=60_000.0), headers=dict(H, **E))
    assert got.status_code == 400 and got.json()["detail"] == OVER                      # capped: the weaker one binds
    assert post(c, headers=dict(H, **E)).json()["request"]["via"] == "transfer_token"


def test_x1_a_request_that_cannot_be_is_a_400_and_uses_none_of_the_day(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    for bad in (dict(MOVE, to="HG"), dict(MOVE, to="NOPE"), dict(MOVE, amount=-5), dict(MOVE, amount="1000"),
                dict(MOVE, amount=None), dict(MOVE, book="live"), dict(MOVE, book=["dry"])):
        got = post(c, bad)
        assert got.status_code == 400 and got.json()["detail"] == INVALID, bad
    assert inbox(r.m) == [] and not os.path.exists(r.m._transfer_day_path())
    assert len(sent) == 5 and all("REFUSED" in m for m in sent)      # said to the operator (a book that is not: log only)
    assert post(c, dict(MOVE, amount=25_000.0)).status_code == 200


# --- X2 ---------------------------------------------------------------------------------------------
OTHER_ROUTES = [("POST", "/kill", None), ("POST", "/resume", None), ("POST", "/mirror/halt", None),
                ("POST", "/mirror/resume", None), ("POST", "/mirror/credit", {"sleeve": "HG", "amount": 5.0}),
                ("POST", "/mirror/resolve", {"id": "mirror-x", "filled": 0}),
                ("POST", "/mirror/adjust", {"sleeve": "HG", "cash": 1.0, "note": "x"}), ("GET", "/status", None)]


@pytest.mark.parametrize("method, route, body", OTHER_ROUTES, ids=[r for _, r, _ in OTHER_ROUTES])
def test_x2_the_token_opens_no_other_route(tmp_path, monkeypatch, method, route, body):
    r = paper(tmp_path)
    c, service, sent = _service(monkeypatch, {"dry": r.m})
    before = json.dumps(r.m.view(), sort_keys=True, default=str)
    for kw in ({"headers": H}, {"headers": {"X-Exec-Token": TT}}, {"params": {"token": TT}},
               {"headers": H, "params": {"token": TT, "x_transfer_token": TT}}):
        got = c.request(method, route, json=body, **kw)
        assert got.status_code == 401 and got.json() == {"detail": "bad exec token"}, (route, kw, got.text)
    assert r.m.halt_state() == {} and inbox(r.m) == [] and sent == []
    assert json.dumps(r.m.view(), sort_keys=True, default=str) == before
    assert post(c).status_code == 200                     # the twin: the same header on its own route


def test_x2_the_token_does_not_read_the_feed(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    assert c.get("/mirror/feed", headers=H).status_code == 401
    assert c.get("/mirror/feed", headers={"X-Read-Token": TT}).status_code == 401
    assert c.get("/mirror/feed", headers={"X-Read-Token": READ}).status_code == 200     # the twin


def test_x2_the_token_is_never_read_from_a_query_parameter_or_the_exec_header(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    for kw in ({"params": {"token": TT}}, {"params": {"x_transfer_token": TT}}, {"params": {"X-Transfer-Token": TT}},
               {"params": {"transfer_token": TT}}, {"headers": {"X-Exec-Token": TT}}, {"headers": {"X-Read-Token": TT}}):
        got = post(c, **dict({"headers": {}}, **kw))
        assert got.status_code == 401 and got.json() == {"detail": "bad exec token"}, kw
    assert inbox(r.m) == [] and sent == []


# --- X3 ---------------------------------------------------------------------------------------------
def test_x3_a_wrong_or_absent_token_gets_the_answer_a_bad_exec_token_gets(tmp_path, monkeypatch):
    r = paper(tmp_path)
    answers = {}
    for feature, tok in (("on", TT), ("off", "")):
        c, _, _ = _service(monkeypatch, {"dry": r.m}, mirror_transfer_token=tok)
        ref = post(c, headers={"X-Exec-Token": "wrong"})                                 # what the route says today
        assert ref.status_code == 401
        for headers in ({}, {"X-Transfer-Token": "wrong"}, {"X-Transfer-Token": ""}, {"X-Transfer-Token": TT + "x"},
                        {"X-Transfer-Token": TT[:-1]}, {"X-Transfer-Token": ("é" * 30).encode()}):       # not ASCII: no crash
            got = post(c, headers=headers)
            assert (got.status_code, got.json()) == (ref.status_code, ref.json()), (feature, headers)
            assert dict(got.headers).keys() == dict(ref.headers).keys()
        answers[feature] = (ref.status_code, ref.json())
    assert answers["on"] == answers["off"]                # nothing tells the two apart
    assert inbox(r.m) == []


def test_x3_an_unset_exec_token_on_a_service_that_can_trade_is_the_503_it_was(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m}, exec_token="", tws_userid="u", tws_password="p")
    ref = post(c, headers={})
    assert ref.status_code == 503
    bad = post(c, headers={"X-Transfer-Token": "wrong"})
    assert (bad.status_code, bad.json()) == (503, ref.json())
    assert post(c).status_code == 200                     # the token is a credential of its own


def test_x3_with_the_mirror_off_the_route_is_a_404_before_any_auth(tmp_path, monkeypatch):
    c, _, sent = _service(monkeypatch, {})
    ref = c.post("/nope/transfer", json=MOVE, headers=H)
    for headers in (H, E, {}):
        got = post(c, headers=headers)
        assert (got.status_code, got.json()) == (404, ref.json())
    assert sent == []


# --- X4 ---------------------------------------------------------------------------------------------
def test_x4_an_empty_token_never_accepts_the_header(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, service, sent = _service(monkeypatch, {"dry": r.m}, mirror_transfer_token="")
    for value in ("", TT, "x" * 24, EXEC + "x"):
        assert post(c, headers={"X-Transfer-Token": value}).status_code == 401, value
    assert post(c, headers={}).status_code == 401
    assert inbox(r.m) == [] and sent == []
    assert service._transfer_token_off_why() is None      # unset is not a misconfiguration: nothing to say


@pytest.mark.parametrize("token, exec_token, read_token, why", [
    ("x" * 23, EXEC, READ, "shorter than 24"),
    ("e" * 30, "e" * 30, READ, "equals EXEC_TOKEN"),
    ("r" * 30, EXEC, "r" * 30, "equals READ_TOKEN"),
], ids=["short", "is-exec", "is-read"])
def test_x4_a_token_that_is_not_its_own_long_secret_is_off_and_said_once_at_boot(tmp_path, monkeypatch, caplog, token,
                                                                                  exec_token, read_token, why):
    r = paper(tmp_path)
    c, service, sent = _service(monkeypatch, {}, mirror_transfer_token=token, exec_token=exec_token, read_token=read_token)
    monkeypatch.setattr(mm, "build", lambda *a, **k: {"dry": r.m})
    with caplog.at_level(logging.WARNING):
        service._build_mirror()                           # the boot
    said = [x for x in caplog.records if "MIRROR_TRANSFER_TOKEN" in x.getMessage()]
    assert len(said) == 1 and said[0].levelno == logging.WARNING and why in said[0].getMessage()
    assert len(sent) == 1 and sent[0].startswith("⚠️") and why in sent[0] and "OFF" in sent[0]
    assert token not in sent[0] and token not in said[0].getMessage()
    got = post(c, headers={"X-Transfer-Token": token})
    if token == exec_token:
        # the exec token in the wrong header is not the exec token either: nothing is authorised by it there
        assert got.status_code == 401
    else:
        assert got.status_code == 401 and got.json() == {"detail": "bad exec token"}
    assert inbox(r.m) == [] and len(sent) == 1            # and nothing more is said per request
    if token == read_token:
        assert c.get("/mirror/feed", headers={"X-Read-Token": token}).status_code == 200   # still only a read token


def test_x4_a_proper_token_boots_in_silence(tmp_path, monkeypatch, caplog):
    r = paper(tmp_path)
    c, service, sent = _service(monkeypatch, {})
    monkeypatch.setattr(mm, "build", lambda *a, **k: {"dry": r.m})
    with caplog.at_level(logging.WARNING):
        service._build_mirror()
    assert not [x for x in caplog.records if "MIRROR_TRANSFER_TOKEN" in x.getMessage()] and sent == []
    assert post(c).status_code == 200
    c2, service, sent = _service(monkeypatch, {}, mirror_transfer_token="x" * 24)       # 24 is long enough
    monkeypatch.setattr(service, "MIRROR", {"dry": r.m})
    assert post(c2, headers={"X-Transfer-Token": "x" * 24}).status_code == 200


# --- X5 ---------------------------------------------------------------------------------------------
def test_x5_the_days_total_never_passes_the_cap(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    eq = equity(r.m)
    assert eq == pytest.approx(100_000.0)                 # the figure the feed publishes
    assert post(c, dict(MOVE, amount=20_000.0)).status_code == 200
    over = post(c, dict(MOVE, amount=5_000.01))
    assert over.status_code == 400
    assert over.json()["detail"] == OVER                  # the caller reads no figure (T4) ...
    msg = sent[1]                                         # ... the operator reads them all
    assert "REFUSED" in msg and "$25,000.00" in msg and "$20,000.00 already used" in msg and "25.00%" in msg
    assert "2026-11-10" in msg and "MIRROR_TRANSFER_MAX_FRAC" in msg
    assert len(inbox(r.m)) == 1 and len(sent) == 2        # refused: not queued, not counted
    ok = post(c, dict(MOVE, amount=5_000.0))              # exactly to the cap
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 25_000.0
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    assert [x["amount"] for x in inbox(r.m)] == [20_000.0, 5_000.0]
    assert post(c, dict(MOVE, amount=40_000.0), headers=E).status_code == 200            # the operator is not capped


def test_x5_the_cap_follows_the_setting_and_is_clamped(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m}, mirror_transfer_max_frac=0.0)
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400                           # 0: the token moves nothing
    monkeypatch.setattr(settings, "mirror_transfer_max_frac", -3.0)
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    monkeypatch.setattr(settings, "mirror_transfer_max_frac", 0.10)
    assert post(c, dict(MOVE, amount=10_000.01)).status_code == 400
    assert post(c, dict(MOVE, amount=10_000.0)).status_code == 200
    monkeypatch.setattr(settings, "mirror_transfer_max_frac", 7.0)                      # never more than the whole book
    assert post(c, dict(MOVE, amount=90_000.01)).status_code == 400
    assert post(c, dict(MOVE, amount=90_000.0)).json()["request"]["day_cap"] == 100_000.0


def test_x5_the_total_survives_a_restart(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, service, _ = _service(monkeypatch, {"dry": r.m})
    assert post(c, dict(MOVE, amount=20_000.0)).status_code == 200
    service.MIRROR["dry"] = r.boot()                      # the process restarts: a new manager from the disk
    assert equity(service.MIRROR["dry"]) == pytest.approx(100_000.0)
    assert post(c, dict(MOVE, amount=5_000.01)).status_code == 400
    ok = post(c, dict(MOVE, amount=5_000.0))
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 25_000.0
    with open(r.m._transfer_day_path()) as f:
        assert json.load(f) == {"day": "2026-11-10", "used": 25_000.0, "count": 2, "last_session": None}


def _session(r, day):
    """the book runs the session of `day`"""
    r.brain.make = lambda now: payload(now, session=day)
    r.tick("15:55:05", day=day)
    assert r.m.view()["last_session"] == day


def test_x5_the_period_ends_on_a_new_et_date_only_once_a_session_has_run(tmp_path, monkeypatch):
    """T3: everything queued between two sessions rides ONE plan, so it shares one allowance. A new
    calendar date alone (midnight; a weekend) is not a new allowance."""
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    r.clock.now = at("18:00")                             # 23:00Z on the 10th
    assert post(c, dict(MOVE, amount=25_000.0)).status_code == 200
    r.clock.now = at("20:30")                             # 01:30Z on the 11th, still the 10th in New York
    assert r.clock.now.date().isoformat() == "2026-11-11"
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    r.clock.now = at("23:59:59")
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    r.clock.now = at("00:00:01", day="2026-11-11")        # a new day in New York, no session since: the same allowance
    got = post(c, dict(MOVE, **{"from": "KMLM", "amount": 25_000.0}))
    assert got.status_code == 400 and got.json()["detail"] == OVER
    r.clock.now = at("09:00", day="2026-11-11")
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    _session(r, "2026-11-11")                             # the plan that applied them has run
    r.clock.now = at("16:35", day="2026-11-11")
    ok = post(c, dict(MOVE, amount=20_000.0))
    assert ok.status_code == 200
    assert (ok.json()["request"]["day"], ok.json()["request"]["day_used"]) == ("2026-11-11", 20_000.0)
    with open(r.m._transfer_day_path()) as f:
        assert json.load(f) == {"day": "2026-11-11", "used": 20_000.0, "count": 1, "last_session": "2026-11-11"}


def test_x5_friday_evening_the_weekend_and_monday_morning_share_one_allowance(tmp_path, monkeypatch):
    r = Rig(tmp_path)
    _session(r, "2026-11-13")                             # Friday's session
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    eq = equity(r.m)
    took = []
    for hms, day, src, amount in (("16:35", "2026-11-13", "HG", 14_000.0), ("12:00", "2026-11-14", "KMLM", 25_000.0),
                                  ("12:00", "2026-11-15", "SLEEVE", 25_000.0), ("09:00", "2026-11-16", "HG", 14_000.0),
                                  ("09:01", "2026-11-16", "KMLM", 11_000.0)):
        r.clock.now = at(hms, day)
        got = post(c, {"from": src, "to": "HARV", "amount": amount})
        took.append(got.status_code)
        if got.status_code == 200:
            assert got.json()["request"]["day"] == "2026-11-13"           # the period that began on Friday
    assert took == [200, 400, 400, 400, 200]              # $25,000 in all into Monday's ONE plan, not $78,000
    assert sum(x["amount"] for x in inbox(r.m)) == 25_000.0 == round(0.25 * eq, 2)
    _session(r, "2026-11-16")
    assert sum(t["moved"] for t in r.m.state["last_run"]["transfers"]) == pytest.approx(25_000.0, abs=1.0)
    r.clock.now = at("16:35", "2026-11-16")
    ok = post(c, {"from": "HG", "to": "HARV", "amount": 1_000.0})          # the twin: a session ran on a later date
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 1_000.0
    sound(r)


def test_x5_a_total_dated_in_the_future_refuses(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    for junk in ('{"day": "2099-01-01", "used": 0}', '{"day": "2026-11-11", "used": 0, "count": 0, "last_session": null}',
                 '{"day": "tomorrow", "used": 0}', '{"day": "2026-11-10", "used": 0, "count": -1}',
                 '{"day": "2026-11-10", "used": 0, "count": "0"}', '{"day": "2026-11-10", "used": 0, "last_session": 5}'):
        with open(r.m._transfer_day_path(), "w") as f:
            f.write(junk)
        got = post(c)
        assert got.status_code == 400 and got.json()["detail"] == BUSY, junk
    assert inbox(r.m) == [] and "cannot be read" in sent[0]
    with open(r.m._transfer_day_path(), "w") as f:
        f.write('{"day": "2026-11-10", "used": 0, "count": 0, "last_session": null}')       # the twin: today's
    assert post(c).status_code == 200


def test_x5_a_total_written_before_the_session_key_loads(tmp_path, monkeypatch):
    """{"day", "used"} alone (what c740d160 wrote): no count yet, and the period ends when the date has
    changed and the book's last session is on or after the record's date"""
    r = paper(tmp_path)                                   # never ran a session
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    with open(r.m._transfer_day_path(), "w") as f:
        f.write('{"day": "2026-11-10", "used": 24000.0}')
    assert post(c, dict(MOVE, amount=1_000.01)).status_code == 400                      # the same date: it counts
    ok = post(c, dict(MOVE, amount=1_000.0))
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 25_000.0
    with open(r.m._transfer_day_path(), "w") as f:
        f.write('{"day": "2026-11-09", "used": 25000.0}')
    assert post(c).status_code == 400                     # the date changed, no session on or after the 9th: kept
    _session(r, "2026-11-10")
    ok = post(c)
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 1_000.0        # a session since: a new period
    with open(r.m._transfer_day_path()) as f:
        assert json.load(f) == {"day": "2026-11-10", "used": 1_000.0, "count": 1, "last_session": "2026-11-10"}


# --- T1..T5: the independent review's findings (each failed at c740d160) -------------------------------
def test_t1_below_a_dollar_is_refused_and_the_amount_is_rounded_to_cents(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    for dust in (0.01, 0.99, 0.994, 4e-10):
        got = post(c, dict(MOVE, amount=dust))
        assert got.status_code == 400 and got.json()["detail"] == INVALID, dust
    assert inbox(r.m) == [] and not os.path.exists(r.m._transfer_day_path())
    req = post(c, dict(MOVE, amount=1234.567)).json()["request"]
    assert (req["amount"], req["day_used"]) == (1234.57, 1234.57)                       # counted as queued
    assert post(c, dict(MOVE, amount=0.999)).json()["request"]["amount"] == 1.0
    assert post(c, dict(MOVE, amount=1.0)).status_code == 200
    with open(r.m._transfer_day_path()) as f:
        assert json.load(f)["used"] == 1236.57
    # the twin: the operator's path is what it was - no floor, no rounding
    assert post(c, dict(MOVE, amount=0.014), headers=E).json()["request"]["amount"] == 0.014


def test_t2_six_transfers_by_token_per_period_and_no_more(tmp_path, monkeypatch):
    assert mm.TRANSFER_TOKEN_MAX_PER_DAY == 6
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    took = [post(c, dict(MOVE, amount=1.0)).status_code for _ in range(40)]
    assert took == [200] * 6 + [400] * 34                 # $6 of a $25,000 cap: the COUNT refuses
    assert post(c, dict(MOVE, amount=1.0)).json()["detail"] == OVER
    assert len(inbox(r.m)) == 6
    with open(r.m._transfer_day_path()) as f:
        assert json.load(f) == {"day": "2026-11-10", "used": 6.0, "count": 6, "last_session": None}
    assert len([m for m in sent if "REFUSED" not in m]) == 6
    assert post(c, dict(MOVE, amount=1.0), headers=E).status_code == 200                # the operator is not counted
    r.clock.now = at("09:00", day="2026-11-11")           # a new date alone is not a new count (T3)
    assert post(c, dict(MOVE, amount=1.0)).status_code == 400
    _session(r, "2026-11-11")
    r.clock.now = at("16:35", day="2026-11-11")
    assert post(c, dict(MOVE, amount=1.0)).json()["request"]["day_used"] == 1.0         # the twin


def test_t2_refusals_are_all_logged_and_alerted_only_a_few_times_a_day(tmp_path, monkeypatch, caplog):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    with caplog.at_level(logging.WARNING):
        for _ in range(25):
            assert post(c, dict(MOVE, amount=99_999.0)).status_code == 400
    assert len([x for x in caplog.records if "REFUSED" in x.getMessage()]) == 25
    assert len(sent) == mm.TRANSFER_TOKEN_MAX_PER_DAY and "not alerted" in sent[-1] and "not alerted" not in sent[0]
    assert not any(TT in m for m in sent)


LEAKS = ("100,000", "25,000", "20,000", "100000", "25000", "equity", "cap ", "MAX_FRAC", "mirror_dry", "transfer_day",
         ".json", "dry", "KMLM", "SLEEVE", "['", "2026-")


def test_t4_a_refusal_tells_the_tokens_holder_nothing_about_the_book(tmp_path, monkeypatch, caplog):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    assert str(tmp_path) and post(c, dict(MOVE, amount=20_000.0)).status_code == 200
    seen = {}

    def refused(body, want):
        got = post(c, body)
        assert got.status_code == 400 and got.json() == {"detail": want}, (body, got.text)
        assert not [w for w in LEAKS + (str(tmp_path),) if w in got.text], got.text
        seen[want] = seen.get(want, 0) + 1

    with caplog.at_level(logging.WARNING):
        refused(dict(MOVE, amount=99_999.0), OVER)        # at c740d160: "... equity of $100,000.00 ..."
        refused(dict(MOVE, to="NOPE"), INVALID)           # "... is not a sleeve of the dry book"
        refused(dict(MOVE, to="HG"), INVALID)
        refused(dict(MOVE, amount="x"), INVALID)
        refused(dict(MOVE, book="nope"), INVALID)         # "name the book: one of ['dry']"
        with open(r.m._transfer_day_path(), "w") as f:
            f.write("{not json")
        refused(MOVE, BUSY)                               # "... (<the path>) cannot be read ..."
        os.remove(r.m._transfer_day_path())
        r.m._view["book"]["equity"] = None
        refused(MOVE, BUSY)                               # "the dry book's equity cannot be computed ..."
    assert seen == {OVER: 1, INVALID: 4, BUSY: 2}
    said = " | ".join(x.getMessage() for x in caplog.records)
    for part in ("$100,000.00", "cap $25,000.00", "$20,000.00 already used", "not a sleeve of the dry book",
                 "name the book: one of ['dry']", r.m._transfer_day_path(), "equity cannot be computed"):
        assert part in said, part                         # the operator's log has every specific
    assert "$100,000.00" in " | ".join(sent) and all(m.startswith("⚠️") for m in sent)
    # the twin: the operator's own request reads the reason as before
    got = post(c, dict(MOVE, to="NOPE"), headers=E)
    assert got.json()["detail"] == "'NOPE' is not a sleeve of the dry book"
    assert "one of ['dry']" in post(c, dict(MOVE, book="nope"), headers=E).json()["detail"]


def test_t4_the_public_schema_does_not_describe_the_transfer_token(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"dry": r.m})
    doc = c.get("/openapi.json")
    assert doc.status_code == 200
    text = doc.text.lower()
    for word in ("transfer-token", "transfer_token", "transfer-only", "max_frac"):
        assert word not in text, word
    op = doc.json()["paths"]["/mirror/transfer"]["post"]
    assert [p["name"] for p in op["parameters"]] == ["token", "x-exec-token"]            # what it listed before the feature
    assert "Queue a move of capital" in op["description"]
    assert post(c).status_code == 200                     # the twin: the header still works


def test_t5_control_characters_never_reach_the_note_the_log_or_the_alert(tmp_path, monkeypatch, caplog):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    evil = "ok\x1b[31m red\x00nul\x7fdel\ttab\x08\x1b]0;title\x07 end"
    with caplog.at_level(logging.WARNING):
        got = post(c, dict(MOVE, note=evil))
    note = got.json()["request"]["note"]
    assert note == "ok [31m red nul del tab ]0;title end"
    for text in (note, sent[0], inbox(r.m)[0]["note"], *[x.getMessage() for x in caplog.records]):
        assert not [ch for ch in text if ord(ch) < 32 or ord(ch) == 127], repr(text)
    assert "\x1b" in post(c, dict(MOVE, note=evil), headers=E).json()["request"]["note"]   # the operator's path: as it was


def test_x5_each_book_has_its_own_day(tmp_path, monkeypatch):
    live = invested(tmp_path)
    dry = paper(tmp_path)
    c, _, _ = _service(monkeypatch, {"live": live.m, "dry": dry.m})
    cap = round(0.25 * equity(live.m), 2)
    assert post(c, dict(MOVE, amount=cap, book="live")).status_code == 200
    assert post(c, dict(MOVE, amount=1.0, book="live")).status_code == 400
    assert post(c, dict(MOVE, amount=25_000.0, book="dry")).status_code == 200          # the other book's day is its own
    assert post(c, dict(MOVE, amount=1.0, book="dry")).status_code == 400
    assert post(c, MOVE).status_code == 400               # two books: the book must be named, as ever


def test_x5_a_book_without_equity_takes_no_transfer_by_token(tmp_path, monkeypatch):
    r = Rig(tmp_path)                                     # not seeded yet: equity 0
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    assert equity(r.m) == 0.0
    got = post(c, dict(MOVE, amount=1.0))
    assert got.status_code == 400 and got.json()["detail"] == BUSY
    r.tick("15:00")
    r.m._view["book"]["equity"] = None                    # a held symbol with no mark: the feed publishes none
    got = post(c, dict(MOVE, amount=1.0))
    assert got.status_code == 400 and got.json()["detail"] == BUSY
    assert inbox(r.m) == [] and len(sent) == 2 and all("REFUSED" in m and "equity" in m for m in sent)
    assert post(c, dict(MOVE, amount=1.0), headers=E).status_code == 200                # the operator still can


def test_x5_an_old_book_without_the_total_loads_and_starts_at_zero(tmp_path, monkeypatch):
    r = invested(tmp_path)                                # a state file written before this feature
    assert not os.path.exists(r.m._transfer_day_path())
    with open(r.m.cfg.state_path) as f:
        old = f.read()
    assert "transfer_day" not in old and "day_used" not in old
    m = r.boot()
    assert m.archived_state is None and m.halt_state() == {}
    c, _, _ = _service(monkeypatch, {"live": m})
    ok = post(c)
    assert ok.status_code == 200 and ok.json()["request"]["day_used"] == 1000.0


@pytest.mark.parametrize("junk", ["{not json", "[1, 2]", '{"day": "2026-11-10"}', '{"day": "2026-11-10", "used": -5}',
                                  '{"day": 7, "used": 1}', '{"day": "2026-11-10", "used": "0"}'])
def test_x5_a_total_that_cannot_be_read_refuses_and_never_counts_from_zero(tmp_path, monkeypatch, junk):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    with open(r.m._transfer_day_path(), "w") as f:
        f.write(junk)
    got = post(c)
    assert got.status_code == 400 and got.json()["detail"] == BUSY
    assert inbox(r.m) == [] and len(sent) == 1 and "cannot be read" in sent[0]
    assert post(c, headers=E).status_code == 200          # exec auth does not depend on it
    os.remove(r.m._transfer_day_path())
    assert post(c).status_code == 200                     # the twin


def test_x5_a_total_that_cannot_be_written_queues_nothing(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    real = mm.atomic_write

    def broken(path, obj):
        if path.endswith(".transfer_day.json"):
            raise OSError("disk full")
        return real(path, obj)
    monkeypatch.setattr(mm, "atomic_write", broken)
    got = post(c)
    assert got.status_code == 400 and got.json()["detail"] == BUSY
    assert inbox(r.m) == [] and len(sent) == 1 and "cannot be written" in sent[0]


def test_x5_concurrent_requests_cannot_pass_the_cap_together(tmp_path):
    r = paper(tmp_path)
    results, gate = [], threading.Barrier(12)

    def one():
        gate.wait()
        try:
            results.append(r.m.request_transfer("HG", "HARV", 5_000.0, "race", via="token", max_frac=0.25))
        except ValueError as exc:
            results.append(exc)
    threads = [threading.Thread(target=one) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    taken = [x for x in results if isinstance(x, dict)]
    assert len(taken) == 5 and len(results) == 12         # 5 x $5,000 = the $25,000 cap, never a sixth
    assert sorted(x["day_used"] for x in taken) == [5_000.0, 10_000.0, 15_000.0, 20_000.0, 25_000.0]
    assert len(inbox(r.m)) == 5 and len({x["id"] for x in inbox(r.m)}) == 5


# --- X6 ---------------------------------------------------------------------------------------------
def test_x6_every_transfer_by_token_is_alerted_at_warning_level(tmp_path, monkeypatch, caplog):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    with caplog.at_level(logging.WARNING):
        assert post(c, dict(MOVE, amount=1234.5, note="POLICY op 5")).status_code == 200
        assert post(c, dict(MOVE, amount=100.0)).status_code == 200
    assert len(sent) == 2
    first = sent[0]
    assert first.startswith("⚠️")
    for part in ("mirror[dry]", "TRANSFER TOKEN", "HG -> HARV", "$1,234.50", "POLICY op 5", "$1,234.50 of the cap $25,000.00"):
        assert part in first, part
    assert "$1,334.50 of the cap $25,000.00" in sent[1]
    logged = [x for x in caplog.records if "TRANSFER TOKEN" in x.getMessage()]
    assert len(logged) == 2 and all(x.levelno == logging.WARNING for x in logged)
    assert not any(TT in m for m in sent) and not any(TT in x.getMessage() for x in caplog.records)


def test_x6_the_note_stays_one_line_of_200_characters(tmp_path, monkeypatch):
    r = paper(tmp_path)
    c, _, sent = _service(monkeypatch, {"dry": r.m})
    req = post(c, dict(MOVE, note="line one\nline two\r\n🚨 mirror[live] HALTED " + "x" * 500)).json()["request"]
    assert "\n" not in req["note"] and "\r" not in req["note"] and len(req["note"]) == 200
    assert req["note"].startswith("line one line two")
    assert "\n" not in sent[0] and req["note"] in sent[0]
    assert post(c, {"from": "HG", "to": "HARV", "amount": 5.0}).json()["request"]["note"] == ""   # optional, as ever
    assert "(no note)" in sent[1]


# --- X7 ---------------------------------------------------------------------------------------------
def _session_after(tmp_path, monkeypatch, headers):
    """M14's pattern with the request made through the route: a live book, a restart, the next session"""
    r = invested(tmp_path)
    eq0 = mc.snapshot(r.m.book, PX)
    c, _, _ = _service(monkeypatch, {"live": r.m})
    got = post(c, {"from": "HG", "to": "HARV", "amount": 5_000.0, "note": "POLICY op 3"}, headers=headers)
    assert got.status_code == 200, got.text
    r.boot()                                              # the inbox is on disk: a restart keeps it
    r.brain.make = lambda now: payload(now, session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")
    return r, eq0, got.json()["request"]


def test_x7_the_session_applies_a_transfer_by_token_exactly_like_an_exec_authorised_one(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    r, eq0, req = _session_after(tmp_path / "a", monkeypatch, H)
    assert req["via"] == "transfer_token"
    eq1 = mc.snapshot(r.m.book, PX)
    assert eq1["sleeves"]["HG"]["equity"] == pytest.approx(eq0["sleeves"]["HG"]["equity"] - 5_000.0, abs=1.0)
    assert eq1["sleeves"]["HARV"]["equity"] == pytest.approx(eq0["sleeves"]["HARV"]["equity"] + 5_000.0, abs=1.0)
    assert eq1["equity"] == pytest.approx(eq0["equity"], abs=0.01)                      # zero-sum
    assert r.m.state["last_run"]["transfers"][0]["status"] == "moved" and r.m.state["requests"] == []
    assert not r.red()
    queued = [x for x in r.journal() if x["event"] == "request"]
    assert len(queued) == 1 and queued[0]["via"] == "transfer_token"                    # the audit trail says who asked

    twin, _, treq = _session_after(tmp_path / "b", monkeypatch, E)                      # the same move, exec-authorised
    assert "via" not in treq
    assert r.m.book.to_dict() == twin.m.book.to_dict()    # the same shares and the same cash, sleeve for sleeve
    assert r.orders() == twin.orders()
    assert r.m.state["last_run"]["transfers"] == twin.m.state["last_run"]["transfers"]

    r.brain.make = lambda now: payload(now, session="2026-11-12")
    r.tick("15:55:05", day="2026-11-12")
    assert r.m.state["last_run"]["transfers"] == []       # applied once
    sound(r)


# --- X8 ---------------------------------------------------------------------------------------------
def test_x8_the_settings_blank_is_the_default_and_the_fraction_is_clamped(monkeypatch):
    for k in ("MIRROR_TRANSFER_TOKEN", "MIRROR_TRANSFER_MAX_FRAC"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.mirror_transfer_token == "" and s.mirror_transfer_max_frac == 0.25         # off by default
    for raw, want in (("", 0.25), ("   ", 0.25), ("0.1", 0.1), ("0", 0.0), ("1", 1.0), ("7", 1.0), ("-0.5", 0.0),
                      ("nan", 0.0), ("inf", 1.0)):
        monkeypatch.setenv("MIRROR_TRANSFER_MAX_FRAC", raw)
        assert Settings(_env_file=None).mirror_transfer_max_frac == want, raw
    monkeypatch.setenv("MIRROR_TRANSFER_TOKEN", TT)
    assert Settings(_env_file=None).mirror_transfer_token == TT


def test_x8_the_deploy_file_declares_both_keys_and_never_a_value_for_the_token():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "..", "render.yaml")) as f:
        text = f.read()
    block = text[text.index("- key: MIRROR_ENABLED"):text.index("- key: MIRROR_DIVIDEND_RULE")]
    assert "- key: MIRROR_TRANSFER_TOKEN\n        sync: false\n" in block
    assert "- key: MIRROR_TRANSFER_MAX_FRAC\n        sync: false\n" in block
    assert text.count("MIRROR_TRANSFER_TOKEN\n") == 1
