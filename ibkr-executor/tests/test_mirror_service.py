"""Gate tests for the Composer mirror's wiring into the service (app/service.py).

  S1  MIRROR_ENABLED off (the default): no book, no key on /health, /status, /kill or /resume, every
      /mirror route a 404, and the loop parks for exactly the poll interval
  S2  enabled on an offline service: one paper book of all four engines; /health and /status carry
      it; /kill halts it and says so; /resume lifts it; /mirror/halt and /mirror/resume touch nothing
      else; the feed is behind READ_TOKEN; transfers and credits are validated and queued
  S3  a mirror that cannot be built leaves the rest of the service up, loudly
  S4  the real loop drives a paper session end to end and then asks for nothing
  S5  the deploy file puts both mirror books on the mounted disk and never switches the mirror on
  S6  the adversarial review's service findings: /health carries no account text (A-15); a non-string
      "book" is a 400 (A-18); with the mirror off every /mirror path is the 404 an unknown path gets,
      before any auth and whatever the method (A-22); /kill is not queued behind a mirror tick's brain
      read (A-23); a halt that is not on disk says so (A-10); /resume says which halt it lifted; the
      operator's repair routes (/mirror/resolve, /mirror/adjust) validate and queue
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import mirror as mm
from app.config import settings

PX = {"BIL": 91.5, "SOXL": 40.0, "TECL": 100.0, "PULS": 49.5, "BOXX": 113.0}
TARGETS = {"HG": {"BIL": 1.0}, "KMLM": {"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}, "SLEEVE": {"BOXX": 1.0},
           "HARV": {"PULS": 1.0}}


def _wait_until(cond, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


class FakeBrain:
    """the brain's two answers (contract schema 2) on the wall clock: the decision bar ends
    `decide_in` seconds after the first read"""
    decide_in = 3600.0

    def __init__(self, url=None, token=None):
        self.t0 = datetime.now(timezone.utc).replace(microsecond=0)
        self.intents_calls = 0

    def session(self):
        now = datetime.now(timezone.utc)
        decide = self.t0 + timedelta(seconds=self.decide_in)
        day = now.astimezone(mm.ET).date().isoformat()
        return {"schema": 2, "kind": mm.SESSION_KIND, "now_utc": mm._iso(now), "session": day,
                "open_utc": mm._iso(decide - timedelta(hours=6)), "decide_utc": mm._iso(decide),
                "decide_et": decide.astimezone(mm.ET).strftime("%H:%M"),
                "close_utc": mm._iso(decide + timedelta(minutes=6)), "close_et": "16:00"}, "ok"

    def intents(self, after):
        self.intents_calls += 1
        now = datetime.now(timezone.utc)
        engines = {n: {"status": "ok", "target": t, "rule": "threshold" if n == "KMLM" else "daily",
                       "corridor": 0.1 if n == "KMLM" else None, "version": "v-" + n, "symphony": "s", "label": "firm"}
                   for n, t in TARGETS.items()}
        return {"schema": 2, "kind": mm.INTENTS_KIND, "session": now.astimezone(mm.ET).date().isoformat(),
                "pinned": True, "asof_utc": after, "built_utc": mm._iso(now),
                "decision_bar": {"end_utc": after, "spy_utc": after, "complete": True}, "replay": False,
                "engines": engines, "prices": dict(PX), "price_times": {}, "price_notes": {}, "dividends": [],
                "splits": [], "sync": {}, "problems": []}, "ok"


def _boot(tmp_path, monkeypatch, enabled=True, **over):
    from app import service
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "read_token", over.pop("read_token", ""))
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "mirror_enabled", enabled)
    monkeypatch.setattr(settings, "mirror_capital_usd", 100_000.0)
    monkeypatch.setattr(settings, "mirror_state_path", str(tmp_path / "mirror.json"))
    monkeypatch.setattr(settings, "mirror_dry_state_path", str(tmp_path / "mirror_dry.json"))
    monkeypatch.setattr(settings, "mirror_decide_offset_s", 0.0)
    for k, v in over.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(mm, "HttpBrain", FakeBrain)
    monkeypatch.setattr(service, "nino34_weekly", lambda: None)
    monkeypatch.setattr(service, "MIRROR", {})
    monkeypatch.setattr(service, "ADAPTER", None)
    monkeypatch.setattr(service, "BLEND", None)
    monkeypatch.setattr(service, "MGR", None)
    monkeypatch.setattr(service, "LAST", {"loop_ok": 0.0, "nino34": None, "mode": "OFFLINE"})
    sent = []
    monkeypatch.setattr(service, "send", sent.append)
    return TestClient(service.app), service, sent


def _ready(service):
    assert _wait_until(lambda: service.MGR is not None and service.LAST["loop_ok"] > 0)


T = {"token": "sekrit"}


# --- S1 ---------------------------------------------------------------------------------------------
def test_s1_disabled_the_service_is_what_it_was(tmp_path, monkeypatch):
    client, service, sent = _boot(tmp_path, monkeypatch, enabled=False, read_token="r")
    with client as c:
        _ready(service)
        assert service.MIRROR == {}
        assert service._loop_wait() == settings.poll_seconds
        assert "mirror" not in c.get("/health").json()
        assert "mirror" not in c.get("/status", params=T).json()
        k = c.post("/kill", params=T).json()
        assert set(k) == {"ok", "halted", "ladder", "blend"}
        r = c.post("/resume", params=T).json()
        assert set(r) == {"ok", "cleared", "blend_cleared", "kill_journal_cleared"}
        assert c.get("/mirror/feed", headers={"X-Read-Token": "r"}).status_code == 404
        for route in ("/mirror/halt", "/mirror/resume", "/mirror/transfer", "/mirror/credit", "/mirror/resolve",
                      "/mirror/adjust"):
            assert c.post(route, params=T, json={}).status_code == 404, route
        assert not any("mirror" in m for m in sent)
    assert not [f for f in os.listdir(tmp_path) if f.startswith("mirror")]     # no state file either


# --- S2 ---------------------------------------------------------------------------------------------
def test_s2_enabled_offline_is_one_paper_book_with_its_controls(tmp_path, monkeypatch):
    client, service, sent = _boot(tmp_path, monkeypatch, read_token="r", mirror_live_engines="HARV")
    with client as c:
        _ready(service)
        assert set(service.MIRROR) == {"dry"}                 # offline: MIRROR_LIVE_ENGINES is ignored
        book = service.MIRROR["dry"]
        assert book.cfg.engines == ("HG", "KMLM", "SLEEVE", "HARV") and book.cfg.live is False
        assert _wait_until(lambda: set(book.view()["book"]["sleeves"]) == set(TARGETS))
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["mirror"]["dry"]["mode"] == "paper" and h["mirror"]["dry"]["halted"] is False
        s = c.get("/status", params=T).json()["mirror"]["dry"]
        assert s["book"]["cash"] == pytest.approx(100_000.0) and s["halt"] == {}
        assert any("mirror[dry] paper" in m for m in sent)    # the boot message names the book

        # /mirror/halt: the mirror only
        assert c.post("/mirror/halt").status_code == 401
        assert c.post("/mirror/halt", params=T).json() == {"ok": True, "halted": {"dry": True}}
        assert c.get("/health").json()["mirror"]["dry"]["halted"] is True
        assert c.get("/status", params=T).json()["halted"] is None            # the ladder was not touched
        lifted = c.post("/mirror/resume", params=T).json()["mirror"]["dry"]
        assert lifted["was_halted"] is True and lifted["lifted"]["reason"] == "operator halt" and lifted["lifted"]["by"] == "operator"
        assert book.halt_state()["halted"] is False
        assert any("mirror resume requested" in m and "'operator halt' set by operator" in m for m in sent)

        # /kill halts it too and reports it; /resume lifts it
        k = c.post("/kill", params=T).json()
        assert k["mirror"] == {"dry": "halted"} and k["halted"] == "KILL"
        assert book.halt_state()["halted"] is True
        assert any("mirror[dry] HALTED" in m for m in sent)
        r = c.post("/resume", params=T).json()
        assert r["mirror"]["dry"]["was_halted"] is True and book.halt_state()["halted"] is False
        assert r["mirror"]["dry"]["lifted"]["reason"] == "KILL"
        assert any("mirror resumed (dry)" in m and "the halt 'KILL' set by operator" in m for m in sent)
        assert any("mirror[dry] HALTED" in m and "hands the loop back within ONE venue call" in m for m in sent)

        # the feed: READ_TOKEN only
        assert c.get("/mirror/feed").status_code == 401
        assert c.get("/mirror/feed", headers={"X-Read-Token": "sekrit"}).status_code == 401
        f = c.get("/mirror/feed", headers={"X-Read-Token": "r"}).json()
        assert f["kind"] == "composer-mirror-feed" and set(f["books"]) == {"dry"} and "history" in f["books"]["dry"]

        # requests: validated, then queued for the loop
        assert c.post("/mirror/transfer", json={"from": "HG", "to": "HARV", "amount": 100}).status_code == 401
        assert c.post("/mirror/transfer", params=T, json={"from": "HG", "to": "HG", "amount": 100}).status_code == 400
        assert c.post("/mirror/transfer", params=T, json={"from": "HG", "to": "NOPE", "amount": 100}).status_code == 400
        assert c.post("/mirror/transfer", params=T, json={"from": "HG", "to": "HARV", "amount": 100,
                                                          "book": "live"}).status_code == 400
        ok = c.post("/mirror/transfer", params=T, json={"from": "HG", "to": "HARV", "amount": 100, "note": "op 3"}).json()
        assert ok["ok"] and ok["book"] == "dry" and ok["request"]["kind"] == "transfer"
        assert c.post("/mirror/credit", params=T, json={"sleeve": "HARV", "amount": 0}).status_code == 400
        assert c.post("/mirror/credit", params=T, json={"sleeve": "HARV", "amount": 12.5}).json()["ok"]
        service.LOOP_WAKE.set()
        assert _wait_until(lambda: len(book.view()["pending_requests"]) == 2)

        # the operator's repair routes: validated, then queued for the loop (which applies or refuses them)
        assert c.post("/mirror/resolve", json={"id": "mirror-x", "filled": 0}).status_code == 401
        assert c.post("/mirror/resolve", params=T, json={"id": "mirror-x", "filled": 5}).status_code == 400     # no price
        assert c.post("/mirror/resolve", params=T, json={"filled": 0}).status_code == 400                       # no id
        ok = c.post("/mirror/resolve", params=T, json={"id": "mirror-x", "filled": 0, "note": "gone"}).json()
        assert ok["ok"] and ok["request"]["kind"] == "resolve" and ok["request"]["order"] == "mirror-x"
        assert _wait_until(lambda: any("resolve request" in m and "REFUSED" in m for m in sent))      # no such order: said
        assert c.post("/mirror/adjust", json={"sleeve": "HG", "cash": 1.0, "note": "x"}).status_code == 401
        assert c.post("/mirror/adjust", params=T, json={"sleeve": "HG", "cash": 1.0}).status_code == 400        # no note
        assert c.post("/mirror/adjust", params=T, json={"sleeve": "HG", "shares": -3, "note": "x"}).status_code == 400
        assert c.post("/mirror/adjust", params=T, json={"sleeve": "HG", "note": "x"}).status_code == 400
        assert c.post("/mirror/adjust", params=T, json={"sleeve": "NOPE", "cash": 1.0, "note": "x"}).status_code == 400
        ok = c.post("/mirror/adjust", params=T, json={"sleeve": "HG", "cash": -12.5, "note": "wire fee"}).json()
        assert ok["ok"] and ok["request"]["kind"] == "adjust"
        assert _wait_until(lambda: book.view()["book"]["sleeves"]["HG"]["cash"] == pytest.approx(29_000.0 - 12.5))
        assert any("ADJUSTED by the operator" in m for m in sent)
        assert c.get("/mirror/halt", params=T).status_code == 405             # enabled: a wrong method is a 405, as ever
        assert c.post("/mirror/nope", params=T).status_code == 404


def test_s2_the_feed_is_dark_without_a_read_token(tmp_path, monkeypatch):
    client, service, _ = _boot(tmp_path, monkeypatch, read_token="")
    with client as c:
        _ready(service)
        assert c.get("/mirror/feed", headers={"X-Read-Token": ""}).status_code == 404


# --- S3 ---------------------------------------------------------------------------------------------
def test_s3_a_mirror_that_cannot_be_built_leaves_the_service_up(tmp_path, monkeypatch):
    client, service, sent = _boot(tmp_path, monkeypatch, mirror_weights="HG:0.5,KMLM:0.4")
    with client as c:
        _ready(service)
        assert service.MIRROR == {}
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/status", params=T).status_code == 200
        assert c.post("/kill", params=T).json()["halted"] == "KILL"           # the kill switch still works
        assert any("mirror NOT built" in m for m in sent)


# --- S4 ---------------------------------------------------------------------------------------------
def test_s4_the_loop_drives_a_paper_session_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(FakeBrain, "decide_in", 1.0)          # the decision bar ends a second after boot
    client, service, sent = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        book = service.MIRROR["dry"]
        assert _wait_until(lambda: book.state.get("last_session") is not None, timeout=20)
        v = c.get("/status", params=T).json()["mirror"]["dry"]
        assert v["last_run"]["outcome"] == "traded"
        assert set(v["book"]["positions"]) == set(PX)
        for name, tgt in TARGETS.items():
            for sym, w in tgt.items():
                assert v["book"]["sleeves"][name]["weights"][sym] == pytest.approx(w, abs=0.01)
        assert v["book"]["sleeves"]["KMLM"]["rule"] == "threshold"
        assert book.brain.intents_calls == 1                  # one decision, one read
        assert book.next_wait() is None and service._loop_wait() == settings.poll_seconds
        assert any("traded" in m and "mirror[dry" in m for m in sent)
        assert c.get("/health").json()["mirror"]["dry"]["last_outcome"] == "traded"
        # the service's own adapter saw none of it: a paper book has a private one
        assert [e for e in getattr(service.ADAPTER, "log", []) if e.get("action") == "place_stock_order"] == []


def test_s4_the_loop_wakes_for_the_decision_instant(tmp_path, monkeypatch):
    monkeypatch.setattr(FakeBrain, "decide_in", 120.0)
    client, service, _ = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        assert _wait_until(lambda: service.MIRROR["dry"].next_wait() is not None)
        w = service._loop_wait()
        assert 100.0 < w <= 120.5 < settings.poll_seconds     # parked until the decision, not the poll


# --- S5 ---------------------------------------------------------------------------------------------
def test_s5_the_deploy_file_keeps_the_books_on_the_disk_and_the_mirror_off():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(os.path.dirname(here), "render.yaml")).read()
    start = text.index("name: ibkr-executor")
    nxt = text.find("\n  - type:", start)
    block = text[start:] if nxt == -1 else text[start:nxt]
    assert "mountPath: /app/data" in block
    for key, value in (("MIRROR_STATE_PATH", "/app/data/mirror_state.json"),
                       ("MIRROR_DRY_STATE_PATH", "/app/data/mirror_dry_state.json")):
        assert f"key: {key}\n        value: {value}" in block, key
    for key in ("MIRROR_ENABLED", "MIRROR_BRAIN_URL", "MIRROR_API_TOKEN", "MIRROR_CAPITAL_USD", "MIRROR_LIVE_ENGINES"):
        assert f"key: {key}\n        sync: false" in block, key      # typed in the dashboard, never a blueprint literal
    assert settings.__class__.model_fields["mirror_enabled"].default is False
    assert settings.__class__.model_fields["mirror_live_engines"].default == ""


# --- S6: the adversarial review's service findings -------------------------------------------------
def test_s6_a15_health_carries_no_account_text(tmp_path, monkeypatch):
    """A-15: the pre-trade reason ('AAPL: the book holds 0, the venue 3', 'the book's cash $x exceeds
    the account's $y') used to be published verbatim on the UNAUTHENTICATED /health"""
    import test_mirror as tm
    client, service, _ = _boot(tmp_path, monkeypatch, enabled=False)
    r = tm.live_rig(tmp_path / "live")
    r.venue.seed_position("AAPL", 3)                       # a stranger's shares in the account
    r.clock.interrupt = True
    r.tick("15:55:05")
    with client as c:
        _ready(service)
        monkeypatch.setattr(service, "MIRROR", {"live": r.m})
        first = c.get("/health")                           # no token
        assert first.status_code == 200
        r.venue._positions.pop("AAPL")
        r.venue.cash = 90_000.0
        r.clock.now += timedelta(seconds=3)
        r.m.tick(r.venue)
        second = c.get("/health")
        status = c.get("/status", params=T).json()["mirror"]["live"]
        monkeypatch.setattr(service, "MIRROR", {})
    assert "AAPL" in (r.m._why or "") or "exceeds the account's $90,000.00" in r.m._why    # (the reason does exist ...)
    assert "exceeds the account's $90,000.00" in status["waiting_on"]                       # ... and is on /status)
    for body in (first, second):
        text = body.text
        assert "AAPL" not in text and "the venue" not in text and "90,000" not in text and "$" not in text
        block = body.json()["mirror"]["live"]
        assert block["waiting"] is True and block["error"] is False and "waiting_on" not in block and "last_error" not in block
        for k, v in block.items():                         # configuration, enumerated states, booleans: no sentence
            assert isinstance(v, (bool, list)) or v is None or (isinstance(v, str) and " " not in v), (k, v)


def test_s6_a18_a_book_that_is_not_a_name_is_a_400(tmp_path, monkeypatch):
    client, service, _ = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        for bad in (["dry"], {"a": 1}, 7, True):
            for route, body in (("/mirror/transfer", {"from": "HG", "to": "HARV", "amount": 100}),
                                ("/mirror/credit", {"sleeve": "HG", "amount": 1}),
                                ("/mirror/resolve", {"id": "x", "filled": 0}),
                                ("/mirror/adjust", {"sleeve": "HG", "cash": 1.0, "note": "x"})):
                assert c.post(route, params=T, json=dict(body, book=bad)).status_code == 400, (route, bad)
        assert c.post("/mirror/transfer", params=T, json={"from": ["HG"], "to": "HARV", "amount": 100}).status_code == 400
        assert c.post("/mirror/credit", params=T, json={"sleeve": {"x": 1}, "amount": 1}).status_code == 400
        assert c.post("/mirror/transfer", params=T, json={"from": "HG", "to": "HARV", "amount": 100,
                                                          "book": "dry"}).status_code == 200      # the twin


def test_s6_a22_with_the_mirror_off_every_mirror_path_is_the_404_of_an_unknown_path(tmp_path, monkeypatch):
    client, service, _ = _boot(tmp_path, monkeypatch, enabled=False, read_token="r")
    with client as c:
        _ready(service)
        ref = c.post("/nope/halt", params=T)
        assert ref.status_code == 404
        for route in ("halt", "resume", "transfer", "credit", "resolve", "adjust", "feed", "anything/else"):
            for call in (lambda u: c.post(u), lambda u: c.post(u, params=T), lambda u: c.get(u, params=T),
                         lambda u: c.put(u, params=T), lambda u: c.delete(u), lambda u: c.post(u, params=T, json={"x": 1})):
                got = call(f"/mirror/{route}")
                assert (got.status_code, got.json()) == (ref.status_code, ref.json()), (route, got.status_code, got.text)
        # ... and nothing else moved: the other routes answer as they always did
        assert c.post("/kill").status_code == 401 and c.get("/kill", params=T).status_code == 405


def test_s6_n03_with_the_mirror_off_a_malformed_request_is_still_the_404_of_an_unknown_path(tmp_path, monkeypatch):
    """round 2 (N-03): FastAPI validated the body (and /mirror/feed's `history`) BEFORE the handler's
    off-check, so a malformed request got a 422 that says the route exists"""
    client, service, _ = _boot(tmp_path, monkeypatch, enabled=False, read_token="r")
    with client as c:
        _ready(service)
        ref = c.post("/nope/transfer", content=b"[1, 2", headers={"content-type": "application/json"})
        assert ref.status_code == 404
        for route in ("transfer", "credit", "resolve", "adjust", "halt", "resume"):
            for body in (b"[1, 2", b"[1, 2]", b'"x"', b"\xff\xfe", b"{}"):
                for params in ({}, T):
                    got = c.post(f"/mirror/{route}", params=params, content=body, headers={"content-type": "application/json"})
                    assert (got.status_code, got.json()) == (404, ref.json()), (route, body, got.status_code, got.text)
        for hist in ("x", "-1", "9999", "1.5", ""):
            got = c.get("/mirror/feed", params={"history": hist}, headers={"X-Read-Token": "r"})
            assert (got.status_code, got.json()) == (404, ref.json()), hist


def test_s6_n03_with_the_mirror_on_a_malformed_request_is_the_422_it_was(tmp_path, monkeypatch):
    client, service, _ = _boot(tmp_path, monkeypatch, read_token="r")
    with client as c:
        _ready(service)
        js = {"content-type": "application/json"}
        for route in ("transfer", "credit", "resolve", "adjust"):
            for body in (b"[1, 2", b"[1, 2]", b'"x"', b"7"):
                assert c.post(f"/mirror/{route}", params=T, content=body, headers=js).status_code == 422, (route, body)
            assert c.post(f"/mirror/{route}", params=T).status_code == 400            # no body: an empty request, refused
            assert c.post(f"/mirror/{route}", params=T, content=b"null", headers=js).status_code == 400
            assert c.post(f"/mirror/{route}", json={}).status_code == 401             # ... and the token is still asked for
        for hist in ("x", "-1", "9999", "1.5"):
            assert c.get("/mirror/feed", params={"history": hist}, headers={"X-Read-Token": "r"}).status_code == 422, hist
        f = c.get("/mirror/feed", params={"history": "0"}, headers={"X-Read-Token": "r"})
        assert f.status_code == 200 and "history" not in f.json()["books"]["dry"]
        assert "history" in c.get("/mirror/feed", params={"history": "120"}, headers={"X-Read-Token": "r"}).json()["books"]["dry"]
        assert c.get("/mirror/feed", headers={"X-Read-Token": "r"}).status_code == 200


def test_s6_n01_force_reaches_the_book_only_as_a_literal_true(tmp_path, monkeypatch):
    """round 2 (N-01): an adjustment or a debit that would put a sleeve in debt is refused by the
    loop unless the request carries "force": true"""
    client, service, sent = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        book = service.MIRROR["dry"]
        assert _wait_until(lambda: set(book.view()["book"]["sleeves"]) == set(TARGETS))
        cash = lambda: book.view()["book"]["sleeves"]["HG"]["cash"]             # noqa: E731
        adj = {"sleeve": "HG", "cash": -29_500.0, "note": "wire fee 29.50"}
        for force in (None, "true", 1, "yes", False):          # only a literal JSON true is force
            body = dict(adj) if force is None else dict(adj, force=force)
            ok = c.post("/mirror/adjust", params=T, json=body).json()
            assert ok["ok"] and ok["request"]["force"] is False
        assert _wait_until(lambda: len([m for m in sent if "adjust request" in m and "REFUSED" in m and "IN DEBT" in m]) == 5)
        assert cash() == pytest.approx(29_000.0)
        assert c.post("/mirror/credit", params=T, json={"sleeve": "HG", "amount": -30_000.0}).json()["request"]["force"] is False
        assert c.post("/mirror/credit", params=T, json={"sleeve": "HG", "amount": -1.0, "force": True}).json()["request"]["force"] is True
        ok = c.post("/mirror/adjust", params=T, json=dict(adj, force=True)).json()
        assert ok["request"]["force"] is True
        assert _wait_until(lambda: cash() == pytest.approx(-500.0))
        assert any("ADJUSTED by the operator" in m for m in sent)


def test_s6_n08_the_books_are_built_with_the_services_trading_day_calendar(tmp_path, monkeypatch):
    client, service, _ = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        assert all(b._trading_day is service._is_trading_day for b in service.MIRROR.values())


def test_s6_a23_the_kill_is_not_queued_behind_the_mirror_ticks_brain_read(tmp_path, monkeypatch):
    """through the REAL service loop: the first thing the loop thread does after a mirror tick is
    nino34_weekly(), and the stage right behind it is 'a /kill that landed while this iteration was
    parked'. A tick blocked in a 3 s brain read used to hold it for the 3 s."""
    slow = 3.0
    real = FakeBrain.intents
    state = {"in": 0.0}

    def intents(self, after):
        state["in"] = time.time()
        time.sleep(slow)                                   # the brain is building
        return real(self, after)
    monkeypatch.setattr(FakeBrain, "intents", intents)
    monkeypatch.setattr(FakeBrain, "decide_in", 1.0)
    client, service, sent = _boot(tmp_path, monkeypatch)
    stamps = []
    monkeypatch.setattr(service, "nino34_weekly", lambda: stamps.append(time.time()))
    with client as c:
        _ready(service)
        assert _wait_until(lambda: state["in"] > 0, timeout=15)           # the tick is inside the brain read
        t0 = time.time()
        assert c.post("/kill", params=T).json()["ok"]                     # answers at once (stage 1) ...
        answered = time.time() - t0
        assert _wait_until(lambda: any(t > t0 for t in stamps), timeout=15)
        waited = min(t for t in stamps if t > t0) - t0                    # ... stage 2 is the loop thread's
        book = service.MIRROR["dry"]
        assert book.halt_state()["halted"] is True and book.state["last_session"] is None      # nothing was traded
    assert answered < 0.5 and waited < 1.0, (answered, waited)


def test_s6_a10_a_kill_whose_mirror_halt_is_not_on_disk_says_so(tmp_path, monkeypatch):
    client, service, sent = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        real = mm.atomic_write

        def broken(path, obj):
            if path.endswith(".halt"):
                raise OSError(30, "Read-only file system")
            return real(path, obj)
        monkeypatch.setattr(mm, "atomic_write", broken)
        k = c.post("/kill", params=T).json()
        assert k["mirror"] == {"dry": "halted_not_persisted"}
        assert any("mirror[dry] HALTED" in m and "NOT written to disk" in m and "RESTART would forget" in m for m in sent)
        h = c.post("/mirror/halt", params=T).json()
        assert h["not_persisted"] == ["dry"]
        monkeypatch.setattr(mm, "atomic_write", real)
        sent.clear()
        k = c.post("/kill", params=T).json()                               # the twin: written
        assert k["mirror"] == {"dry": "halted"} and not any("NOT written to disk" in m for m in sent if "mirror[dry]" in m)
