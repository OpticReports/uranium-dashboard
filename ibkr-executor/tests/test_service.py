"""Service + adapter-logic gates: offline mode, auth, kill; pure helpers."""
from fastapi.testclient import TestClient

from app.config import settings
from app.ib_adapter import DryAdapter, pick_expiry, pick_strike, size_combos
from app.service import app


def test_gate_adapter_helpers():
    assert pick_expiry(["20270115", "20270219", "20270319"], "2027-02") == "20270219"
    assert pick_expiry(["20261218"], "2027-02") == "20261218"   # best available
    assert pick_expiry([], "2027-02") is None
    assert pick_strike([2.5, 2.75, 3.0, 3.25], 2.9) == 3.0
    # $10k at $0.55 net debit on NG's 10,000 multiplier -> 1 combo ($5.5k each)
    assert size_combos(10_000, 0.55, 10_000) == 1
    assert size_combos(10_000, 0.04, 1_120) == 223          # sugar-scale
    assert size_combos(10_000, 0.0, 100) == 0               # degenerate quote


def test_gate_dry_adapter_lifecycle():
    a = DryAdapter()
    r = a.open_spread({"underlying": "NG", "kind": "call_spread"}, 9_500)
    assert r["premium"] == 9_500
    assert a.mark(r["order_ref"]) == 9_500
    out = a.close_spread(r["order_ref"])
    assert out["value"] == 9_500
    assert a.mark(r["order_ref"]) is None
    assert [e["action"] for e in a.log] == ["open_spread", "close_spread"]


def test_gate_offline_service_and_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200            # public
        assert c.get("/status").status_code == 401
        assert c.post("/kill").status_code == 401
        r = c.get("/status", params={"token": "sekrit"})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert set(body["ladder"]) == {"NG", "SB", "SLV"}
        # kill halts the ladder even with nothing open
        r = c.get("/kill", params={"token": "sekrit"})
        assert r.json()["halted"] == "KILL"
        r = c.get("/resume", params={"token": "sekrit"})
        assert r.json()["ok"] is True


# --- gateway watch + disabled-book guard (2026-09-04) -------------------------
# MUTATION-VERIFIED: dropping `since_drop <= 1` turns test_gateway_watch_stall_
# diagnosis red (crash-loop case); dropping the weekday guard turns the
# Saturday case red; dropping the once-per-outage flag turns the repeat case
# red; dropping the `real:` mode check turns test_disabled_book_guard red.
import json as _json
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _Zone

from app import service as svc

_ET = _Zone("America/New_York")


def _ts(y, mo, d, h, mi):
    return _dt(y, mo, d, h, mi, tzinfo=_ET).timestamp()


def test_gateway_watch_stall_diagnosis():
    sent = []
    st = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    drop = _ts(2026, 9, 3, 19, 49)                 # the real Thursday drop
    # 20 min in, one relaunch at the drop: too early, nothing
    assert svc._gateway_watch(drop + 20 * 60, {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st) == []
    # 31 min in, still only that one relaunch: alive-but-not-logged-in
    assert svc._gateway_watch(drop + 31 * 60, {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st) == ["stall"]
    assert "NOT logged in" in sent[-1] and "IBKR Mobile" in sent[-1]
    # once per outage: the next cycle is silent
    assert svc._gateway_watch(drop + 36 * 60, {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st) == []
    # a CRASH LOOP (many relaunches since the drop) is a different problem:
    # no stall diagnosis
    st2 = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    loop = [drop + 5, drop + 20, drop + 50, drop + 110, drop + 230]
    assert svc._gateway_watch(drop + 31 * 60, {"currently_down_since": drop},
                              {"recent_ts": loop, "readable": True}, sent.append, st2) == ["loop"]
    assert "crash-looping" in sent[-1]
    st2b = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    assert svc._gateway_watch(drop + 31 * 60, {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True,
                               "circuit_open": True}, sent.append, st2b) == ["loop"]
    assert "circuit breaker is now OPEN" in sent[-1]
    st2c = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    assert svc._gateway_watch(drop + 31 * 60, {"currently_down_since": drop},
                              {"recent_ts": [], "readable": False, "path": "/app/data/x"},
                              sent.append, st2c) == ["unreadable"]
    assert "/app/data/x" in sent[-1]
    svc._gateway_watch(drop + 32 * 60, None, {"recent_ts": [], "readable": True},
                       sent.append, st)
    assert st["outage_since"] == drop and st["diagnosed"] is True
    # recovery clears the bookkeeping
    svc._gateway_watch(drop + 40 * 60, {"currently_down_since": None},
                       {"recent_ts": [], "readable": True}, sent.append, st)
    assert st["outage_since"] is None and st["diagnosed"] is False


def test_gateway_watch_preopen_page():
    sent = []
    st = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    drop = _ts(2026, 9, 3, 19, 49)
    friday_0845 = _ts(2026, 9, 4, 8, 45)
    out = svc._gateway_watch(friday_0845, {"currently_down_since": drop},
                             {"recent_ts": [drop + 5], "readable": True}, sent.append, st)
    assert "preopen" in out
    assert "opens in 45 min" in sent[-1]
    # once per day
    assert "preopen" not in svc._gateway_watch(
        friday_0845 + 300, {"currently_down_since": drop},
        {"recent_ts": [drop + 5], "readable": True}, sent.append, st)
    # outside the window: nothing (noon)
    # mid-outage state, stall already diagnosed: only the window matters
    st3 = {"outage_since": drop, "diagnosed": True, "preopen_paged": ""}
    assert svc._gateway_watch(_ts(2026, 9, 4, 12, 0), {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st3) == []
    # Saturday 08:45: no market, no page
    st4 = {"outage_since": drop, "diagnosed": True, "preopen_paged": ""}
    assert svc._gateway_watch(_ts(2026, 9, 5, 8, 45), {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st4) == []
    st5 = {"outage_since": drop, "diagnosed": True, "preopen_paged": ""}
    assert svc._gateway_watch(_ts(2026, 9, 7, 8, 45), {"currently_down_since": drop},
                              {"recent_ts": [drop + 5], "readable": True}, sent.append, st5) == []
    blip = _ts(2026, 9, 4, 8, 40)
    st6 = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}
    assert svc._gateway_watch(blip + 5 * 60, {"currently_down_since": blip},
                              {"recent_ts": [], "readable": True}, sent.append, st6) == []
    assert svc._gateway_watch(blip + 11 * 60, {"currently_down_since": blip},
                              {"recent_ts": [], "readable": True}, sent.append, st6) == ["preopen"]
    svc._gateway_watch(blip + 12 * 60, {"currently_down_since": None},
                       {"recent_ts": [], "readable": True}, sent.append, st6)
    assert svc._gateway_watch(blip + 25 * 60, {"currently_down_since": blip + 13 * 60},
                              {"recent_ts": [], "readable": True}, sent.append, st6) == []


def test_disabled_book_guard(tmp_path):
    p = tmp_path / "blend_state.json"
    # a real:live book with holdings -> reported
    p.write_text(_json.dumps({"mode": "real:live", "initialized": True,
                              "positions": {}, "spy_qty": 45, "bil_qty": 136,
                              "sleeve_cash": 2533.24, "halted": None}))
    book = svc._check_disabled_blend_book(str(p))
    assert book and book["spy_qty"] == 45 and book["bil_qty"] == 136
    sent = []
    svc._disabled_book_alert(book, sent.append)
    assert "DISABLED" in sent[0] and "136 BIL" in sent[0]
    # a dry/paper book is fiction: no claim
    p.write_text(_json.dumps({"mode": "dry:paper", "spy_qty": 45, "bil_qty": 1,
                              "sleeve_cash": 9.0, "positions": {}}))
    assert svc._check_disabled_blend_book(str(p)) is None
    # an empty real book: nothing to abandon
    p.write_text(_json.dumps({"mode": "real:live", "spy_qty": 0, "bil_qty": 0,
                              "sleeve_cash": 0.0, "positions": {}}))
    assert svc._check_disabled_blend_book(str(p)) is None
    # missing / corrupt file: never raises
    assert svc._check_disabled_blend_book(str(tmp_path / "nope.json")) is None
    p.write_text("{not json")
    assert svc._check_disabled_blend_book(str(p)) is None
    p.write_text(_json.dumps({"mode": "real:live", "spy_qty": "x", "bil_qty": 1,
                              "sleeve_cash": 9.0, "positions": {}}))
    assert svc._check_disabled_blend_book(str(p)) is None
