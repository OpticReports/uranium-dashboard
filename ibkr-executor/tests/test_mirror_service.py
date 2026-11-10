"""Gate tests for the Composer mirror's wiring into the service (app/service.py).

  S1  MIRROR_ENABLED off (the default): no book, no key on /health, /status, /kill or /resume, every
      /mirror route a 404, and the loop parks for exactly the poll interval
  S2  enabled on an offline service: one paper book of all four engines; /health and /status carry
      it; /kill halts it and says so; /resume lifts it; /mirror/halt and /mirror/resume touch nothing
      else; the feed is behind READ_TOKEN; transfers and credits are validated and queued
  S3  a mirror that cannot be built leaves the rest of the service up, loudly
  S4  the real loop drives a paper session end to end and then asks for nothing
  S5  the deploy file puts both mirror books on the mounted disk and never switches the mirror on
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
    """the brain's two answers on the wall clock: `decide_in` seconds from the first read"""
    decide_in = 3600.0

    def __init__(self, url=None, token=None):
        self.t0 = datetime.now(timezone.utc).replace(microsecond=0)
        self.intents_calls = 0

    def session(self):
        now = datetime.now(timezone.utc)
        decide = self.t0 + timedelta(seconds=self.decide_in)
        day = now.astimezone(mm.ET).date().isoformat()
        return {"schema": 1, "kind": mm.SESSION_KIND, "now_utc": mm._iso(now), "session": day,
                "open_utc": mm._iso(decide - timedelta(hours=6)), "decide_utc": mm._iso(decide),
                "close_utc": mm._iso(decide + timedelta(minutes=5)), "close_et": "16:00"}, "ok"

    def intents(self, after):
        self.intents_calls += 1
        now = datetime.now(timezone.utc)
        engines = {n: {"status": "ok", "target": t, "rule": "threshold" if n == "KMLM" else "daily",
                       "corridor": 0.1 if n == "KMLM" else None, "version": "v-" + n, "symphony": "s", "label": "firm"}
                   for n, t in TARGETS.items()}
        return {"schema": 1, "kind": mm.INTENTS_KIND, "session": now.astimezone(mm.ET).date().isoformat(),
                "asof_utc": mm._iso(now), "replay": False, "engines": engines, "prices": dict(PX), "price_notes": {},
                "problems": []}, "ok"


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
        for route in ("/mirror/halt", "/mirror/resume", "/mirror/transfer", "/mirror/credit"):
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
        assert c.post("/mirror/resume", params=T).json()["mirror"]["dry"]["was_halted"] is True
        assert book.halt_state()["halted"] is False

        # /kill halts it too and reports it; /resume lifts it
        k = c.post("/kill", params=T).json()
        assert k["mirror"] == {"dry": "halted"} and k["halted"] == "KILL"
        assert book.halt_state()["halted"] is True
        assert any("mirror[dry] HALTED" in m for m in sent)
        r = c.post("/resume", params=T).json()
        assert r["mirror"]["dry"]["was_halted"] is True and book.halt_state()["halted"] is False
        assert any("mirror resumed (dry)" in m for m in sent)

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
