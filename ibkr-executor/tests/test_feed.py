"""Execution-feed gates: GET /blend/feed shape + READ_TOKEN gate (absent /
wrong / disabled), public-safety key blacklist (no credential material in the
feed), the persisted trade log + daily equity curve, the 85%-of-BLEND_BUDGET
one-shot utilization alert with 75% re-arm, and /health's blend_loop
visibility. All offline (DryAdapter)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import service
from app.blend import Blend3070Manager, run_cycle
from app.config import settings
from app.ib_adapter import DryAdapter
from app.service import app


class Cfg:
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""
    dry_run = True              # mode-guard: tests run a "dry:paper" book
    trading_mode = "paper"


def mk(tmp_path, **cfg_over):
    cfg = Cfg()
    for k, v in cfg_over.items():
        setattr(cfg, k, v)
    return Blend3070Manager(cfg, str(tmp_path / "blend.json"))


def payload(gate=True, entries=(), stops=()):
    return {
        "as_of": "2026-08-20",
        "gate": {"xbi_above_200dma_prior": gate, "since": None},
        "entries": list(entries),
        "exits": [],
        "stops": list(stops),
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
    }


def entry(call_id=1, symbol="CRSP", entry_ref=50.0):
    return {"symbol": symbol, "call_id": call_id, "fire_date": "2026-08-20",
            "flag_type": "pre_catalyst_sentiment_ramp", "risk_frac": 0.01,
            "entry_ref": entry_ref, "note": "test"}


def stop_row(call_id=1, symbol="CRSP", trail=44.0):
    return {"symbol": symbol, "call_id": call_id, "trail_level": trail}


def _seed_initialized(m, sleeve_cash=3_000.0, spy_qty=70, bil_qty=0,
                      core_cash=0.0):
    m.state.initialized = True
    m.state.sleeve_cash = sleeve_cash
    m.state.spy_qty = spy_qty
    m.state.bil_qty = bil_qty
    m.state.core_cash = core_cash


def _entered_book(tmp_path, **cfg_over):
    """Manager + adapter with one CRSP position entered via a full cycle."""
    m = mk(tmp_path, **cfg_over)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    assert "1" in m.state.positions
    return m, a


def _wire(monkeypatch, mgr, adapter, token="read-tok"):
    monkeypatch.setattr(service, "BLEND", mgr)
    monkeypatch.setattr(service, "ADAPTER", adapter)
    monkeypatch.setattr(settings, "read_token", token)
    return TestClient(app)          # no lifespan: endpoints only, no loop


# --- trade log + equity curve (feed source of truth) --------------------------

def test_gate_trade_log_records_entry_and_stop_exit_with_r_and_pnl(tmp_path):
    m, a = _entered_book(tmp_path)
    kinds = [(t["kind"], t["side"], t["symbol"]) for t in m.state.trades]
    assert ("entry", "BUY", "CRSP") in kinds
    assert ("sweep", "BUY", "BIL") in kinds       # idle sleeve cash to BIL
    buy = next(t for t in m.state.trades if t["kind"] == "entry")
    assert buy == {"symbol": "CRSP", "side": "BUY", "qty": 5,
                   "fill_price": 50.0, "date": "2026-08-20", "kind": "entry",
                   "r_multiple": None, "pnl": None}
    # stop-out at the venue -> SELL row with R and $ P&L booked
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    run_cycle(m, a, None, "2026-08-21", alert=lambda _: None)
    sell = next(t for t in m.state.trades if t["side"] == "SELL"
                and t["symbol"] == "CRSP")
    assert sell["kind"] == "stop_filled"
    assert sell["fill_price"] == 44.0
    assert sell["pnl"] == pytest.approx(-30.0)    # (44-50) x 5
    assert sell["r_multiple"] == pytest.approx(-1.0)   # risk/share was 6
    # persisted across restart
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert m2.state.trades == m.state.trades


def test_gate_equity_curve_one_point_per_cycle_day(tmp_path):
    m, a = _entered_book(tmp_path)
    assert m.state.equity_curve == [["2026-08-20", pytest.approx(10_000.0)]]
    # a second cycle the SAME day updates in place, never a second row
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    assert len(m.state.equity_curve) == 1
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    run_cycle(m, a, None, "2026-08-21", alert=lambda _: None)
    assert len(m.state.equity_curve) == 2
    assert m.state.equity_curve[1][0] == "2026-08-21"
    assert m.state.equity_curve[1][1] == pytest.approx(9_970.0)  # -$30 stop-out


# --- utilization alert (85% one-shot, 75% re-arm) -----------------------------

def test_gate_utilization_alert_fires_once_per_crossing_and_rearms(tmp_path):
    m = mk(tmp_path, blend_budget=10_000.0)
    _seed_initialized(m, spy_qty=86)              # gross $8,600 = 86%
    prices = {"SPY": 100.0, "BIL": 100.0}
    alerts: list[str] = []
    m.check_budget_alarm(prices, alerts.append)
    assert len(alerts) == 1
    assert "budget utilization 86%" in alerts[0]
    assert "raise BLEND_BUDGET" in alerts[0]
    m.check_budget_alarm(prices, alerts.append)   # same level: no repeat
    assert len(alerts) == 1
    m.state.spy_qty = 80                          # 80%: below ON, above OFF
    m.check_budget_alarm(prices, alerts.append)   # stays disarmed
    m.state.spy_qty = 90
    m.check_budget_alarm(prices, alerts.append)   # re-cross while disarmed
    assert len(alerts) == 1
    # disarmed flag survives a restart (never re-fires on boot)
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert m2.state.util_alert_armed is False
    m.state.spy_qty = 74                          # < 75%: re-arms
    m.check_budget_alarm(prices, alerts.append)
    assert len(alerts) == 1 and m.state.util_alert_armed is True
    m.state.spy_qty = 88
    m.check_budget_alarm(prices, alerts.append)   # fresh crossing fires again
    assert len(alerts) == 2


def test_gate_utilization_disabled_without_budget_and_runs_in_cycle(tmp_path):
    # no budget -> never alerts, utilization is null
    m = mk(tmp_path)
    _seed_initialized(m, spy_qty=1_000)
    alerts: list[str] = []
    m.check_budget_alarm({"SPY": 100.0, "BIL": 100.0}, alerts.append)
    assert alerts == [] and m.budget_utilization({"SPY": 100.0}) is None
    # and run_cycle wires the check end-to-end (86% book under a $10k budget)
    m2 = mk(tmp_path, blend_budget=10_000.0)
    _seed_initialized(m2, sleeve_cash=0.0, spy_qty=86)
    run_cycle(m2, DryAdapter(), None, "2026-08-20", alert=alerts.append)
    assert any("raise BLEND_BUDGET" in a for a in alerts)


# --- GET /blend/feed ----------------------------------------------------------

def test_gate_feed_shape(tmp_path, monkeypatch):
    m, a = _entered_book(tmp_path, blend_budget=20_000.0)
    monkeypatch.setattr(service, "BLEND_CYCLE",
                        {"date": "2026-08-20", "ok": True, "error": None,
                         "error_ts": None})
    c = _wire(monkeypatch, m, a)
    r = c.get("/blend/feed", headers={"X-Read-Token": "read-tok"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"mode", "halted", "gate", "book", "positions",
                         "trades", "equity_curve", "unreconciled",
                         "unverifiable", "unprotected",
                         "last_cycle", "marks_age_s", "cash"}
    assert body["marks_age_s"] is not None       # cached-marks staleness
    assert body["marks_age_s"] < 60.0            # cache just refreshed
    assert set(body["book"]) == {"sleeve_cash", "core_qty", "bil_qty",
                                 "equity_estimate", "budget_utilization",
                                 "initial_book_usd"}
    assert body["gate"] is True and body["halted"] is None
    assert body["book"]["core_qty"] == 70
    assert body["book"]["equity_estimate"] == pytest.approx(10_000.0)
    assert body["book"]["budget_utilization"] == pytest.approx(0.4975)
    assert body["book"]["initial_book_usd"] == 10_000.0
    (pos,) = body["positions"]
    assert pos == {"symbol": "CRSP", "qty": 5, "entry": 50.0,
                   "entry_date": "2026-08-20", "trail_level": 44.0,
                   "days_held": pos["days_held"], "unverifiable": False,
                   "unprotected": False, "unverified_cycles": 0}
    assert isinstance(pos["days_held"], int)
    assert any(t["kind"] == "entry" for t in body["trades"])
    assert body["equity_curve"] == [["2026-08-20", 10_000.0]]
    assert body["unreconciled"] == 0
    assert body["unverifiable"] == 0 and body["unprotected"] == 0
    assert body["last_cycle"] == {"date": "2026-08-20", "ok": True,
                                  "error": None}


def test_gate_feed_token_absent_wrong_disabled(tmp_path, monkeypatch):
    m, a = _entered_book(tmp_path)
    c = _wire(monkeypatch, m, a, token="read-tok")
    assert c.get("/blend/feed").status_code == 401                    # absent
    assert c.get("/blend/feed",
                 headers={"X-Read-Token": "nope"}).status_code == 401  # wrong
    monkeypatch.setattr(settings, "read_token", "")
    assert c.get("/blend/feed",
                 headers={"X-Read-Token": "read-tok"}).status_code == 404
    # blend disabled entirely -> 404 even with a valid token configured
    monkeypatch.setattr(settings, "read_token", "read-tok")
    monkeypatch.setattr(service, "BLEND", None)
    assert c.get("/blend/feed",
                 headers={"X-Read-Token": "read-tok"}).status_code == 404


def _all_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            _all_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _all_keys(v, out)
    return out


def test_gate_feed_contains_no_credential_material(tmp_path, monkeypatch):
    """Public-safety blacklist: NOTHING credential-shaped may appear in any
    feed key, at any nesting depth — the feed crosses a service boundary."""
    m, a = _entered_book(tmp_path)
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    run_cycle(m, a, None, "2026-08-21", alert=lambda _: None)
    c = _wire(monkeypatch, m, a)
    body = c.get("/blend/feed", headers={"X-Read-Token": "read-tok"}).json()
    keys = _all_keys(body, set())
    banned = ("token", "password", "secret", "credential", "account",
              "userid", "user_id", "tws", "api_key", "private",
              "order_ref", "client_order_id", "auth")
    for key in keys:
        for frag in banned:
            assert frag not in key, f"feed leaks credential-shaped key {key!r}"
    # and the token itself never round-trips into the body
    import json
    assert "read-tok" not in json.dumps(body)


# --- /health blend_loop -------------------------------------------------------

def test_gate_health_blend_loop_surfaces_cycle_failures(tmp_path, monkeypatch):
    m, a = _entered_book(tmp_path)
    c = _wire(monkeypatch, m, a)
    import time as _time
    monkeypatch.setattr(service, "BLEND_CYCLE",
                        {"date": "2026-08-20", "ok": False,
                         "error": "adapter cannot reconcile",
                         "error_ts": _time.time() - 120.0})
    body = c.get("/health").json()
    assert body["blend_loop"]["ok"] is False
    assert body["blend_loop"]["last_error_age_s"] == pytest.approx(120.0,
                                                                   abs=5.0)
    # healthy loop -> ok true, stale error age still visible
    monkeypatch.setattr(service, "BLEND_CYCLE",
                        {"date": "2026-08-20", "ok": True, "error": None,
                         "error_ts": None})
    body = c.get("/health").json()
    assert body["blend_loop"] == {"ok": True, "last_error_age_s": None,
                                  "quotes_missing_for_s": None}
    # BLEND disabled -> the section does not exist (byte-identical /health)
    monkeypatch.setattr(service, "BLEND", None)
    assert "blend_loop" not in c.get("/health").json()


# --- M2 (adapter review): API threads never touch the adapter -----------------
# /status and /blend/feed run on FastAPI worker threads; the ib_async event
# loop belongs to the service loop thread. Both endpoints must serve the
# loop-thread-refreshed mark cache ONLY.


class _NoTouchAdapter(DryAdapter):
    """Guard adapter: ANY adapter surface call from the API thread fails
    the test — the endpoints must never reach the (ib_async) adapter."""

    def _boom(self, *a, **kw):
        raise AssertionError("API thread touched the adapter (M2)")

    spot = _boom
    place_stock_order = _boom
    cancel_stock_order = _boom
    poll_stock_fills = _boom
    requeue_stock_fills = _boom
    find_stock_order = _boom
    mark = _boom
    open_spread = _boom
    close_spread = _boom


def test_gate_m2_feed_and_status_never_call_adapter(tmp_path, monkeypatch):
    from app.manager import LadderManager

    m, _ = _entered_book(tmp_path)       # run_cycle populated the mark cache
    guard = _NoTouchAdapter()
    monkeypatch.setattr(service, "BLEND", m)
    monkeypatch.setattr(service, "ADAPTER", guard)
    monkeypatch.setattr(service, "MGR",
                        LadderManager(settings, str(tmp_path / "s.json")))
    monkeypatch.setattr(settings, "read_token", "read-tok")
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    c = TestClient(app)
    body = c.get("/blend/feed", headers={"X-Read-Token": "read-tok"}).json()
    # served entirely from the cached marks — no adapter call happened
    assert body["book"]["equity_estimate"] == pytest.approx(10_000.0)
    assert body["marks_age_s"] is not None
    body = c.get("/status", params={"token": "sekrit"}).json()
    assert body["blend"]["book_value"] == pytest.approx(10_000.0)
    assert body["blend"]["marks_age_s"] is not None


def test_gate_m2_marks_staleness_shown_not_hidden(tmp_path, monkeypatch):
    import time as _time

    m, a = _entered_book(tmp_path)
    m.mark_cache = {"prices": {"SPY": 100.0, "BIL": 100.0, "CRSP": 50.0},
                    "ts": _time.time() - 900.0}      # 15-minute-old marks
    c = _wire(monkeypatch, m, a)
    body = c.get("/blend/feed", headers={"X-Read-Token": "read-tok"}).json()
    assert body["marks_age_s"] == pytest.approx(900.0, abs=10.0)
    # a cache never filled (loop hasn't completed a cycle) serves no marks
    # and no fake age — nothing pretends to be fresh
    m.mark_cache = {"prices": {}, "ts": None}
    body = c.get("/blend/feed", headers={"X-Read-Token": "read-tok"}).json()
    assert body["marks_age_s"] is None
    assert body["book"]["equity_estimate"] is None
