"""blend3070 gates: state transitions on fixture intents, 1%-risk sizing,
GTC stop cancel/replace, time stop, band rebalance, BIL sweep, budget cap,
kill switch, DryAdapter stock fills, /status shape, and the safety
invariants (BLEND_ENABLED=false changes nothing; the tracker never learns
account equity; DRY_RUN defaults true). All offline."""
from __future__ import annotations

import time

import pytest

from app import blend as blend_mod
from app.blend import Blend3070Manager, fetch_intents, run_cycle
from app.ib_adapter import DryAdapter


class Cfg:
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""


def mk(tmp_path, **cfg_over):
    cfg = Cfg()
    for k, v in cfg_over.items():
        setattr(cfg, k, v)
    return Blend3070Manager(cfg, str(tmp_path / "blend.json"))


def payload(gate=True, entries=(), exits=(), stops=(), max_open=10):
    return {
        "as_of": "2026-08-20",
        "gate": {"xbi_above_200dma_prior": gate, "since": None},
        "entries": list(entries),
        "exits": list(exits),
        "stops": list(stops),
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": {"max_open": max_open, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
        "contract": "executor reconciles and sizes",
    }


PRICES = {"SPY": 100.0, "BIL": 100.0, "CRSP": 50.0}


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


def _held_position(m, call_id=1, symbol="CRSP", qty=5, fill=50.0,
                   stop_level=44.0, entry_date="2026-08-01",
                   time_stop="2026-10-30", stop_ref="old-stop"):
    m.on_entered({"call_id": call_id, "symbol": symbol, "qty": qty,
                  "entry_ref": fill, "stop_level": stop_level},
                 fill, "entry-ref", entry_date)
    pos = m.state.positions[str(call_id)]
    pos.time_stop = time_stop
    pos.stop_order_ref = stop_ref
    return pos


# --- bootstrap + sweep --------------------------------------------------------

def test_gate_bootstrap_splits_30_70_and_parks_cash(tmp_path):
    m = mk(tmp_path)
    out = m.step("2026-08-20", payload(), PRICES)
    acts = {(o["action"], o.get("symbol")) for o in out}
    assert ("CORE_BUY", "SPY") in acts and ("SWEEP", "BIL") in acts
    core = next(o for o in out if o["action"] == "CORE_BUY")
    sweep = next(o for o in out if o["action"] == "SWEEP")
    assert core["qty"] == 70          # $7,000 core at $100
    assert sweep["qty"] == 30         # $3,000 sleeve idle -> BIL
    assert m.state.sleeve_cash == pytest.approx(3_000.0)
    assert m.state.core_cash == pytest.approx(7_000.0)


def test_gate_full_dry_cycle_persists_book(tmp_path):
    m = mk(tmp_path)
    run_cycle(m, DryAdapter(), payload(), "2026-08-20", alert=lambda _: None)
    assert m.state.spy_qty == 70 and m.state.bil_qty == 30
    assert m.state.core_cash == pytest.approx(0.0)
    assert m.state.sleeve_cash == pytest.approx(0.0)
    # persistence across restart (LadderManager doctrine)
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert m2.state.spy_qty == 70 and m2.state.initialized is True


# --- entries ------------------------------------------------------------------

def test_gate_entry_sizing_is_1pct_of_sleeve_over_per_share_risk(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)                     # sleeve equity $3,000
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]), PRICES)
    (ent,) = [o for o in out if o["action"] == "ENTER"]
    # risk$ = 1% * 3,000 = 30; per-share = 50 - 44 = 6 -> 5 shares MOO
    assert ent["qty"] == 5
    assert ent["stop_level"] == 44.0 and ent["entry_ref"] == 50.0


def test_gate_entry_executes_moo_then_gtc_stop(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    assert pos.qty == 5 and pos.fill_price == 50.0   # MOO at the reference
    assert pos.stop_order_ref in a._stops            # GTC stop resting
    assert a._stops[pos.stop_order_ref]["stop_price"] == 44.0
    assert pos.time_stop == "2026-11-18"             # entry + 90 CALENDAR days
    assert m.state.sleeve_cash + m.state.bil_qty * 100.0 == pytest.approx(
        3_000.0 - 250.0)                             # cost left the sleeve


def test_gate_no_entry_when_gate_off(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    out = m.step("2026-08-20",
                 payload(gate=False, entries=[entry()], stops=[stop_row()]),
                 PRICES)
    assert not [o for o in out if o["action"] == "ENTER"]


def test_gate_cap_10_open(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=1_000_000.0)
    entries = [entry(call_id=i, symbol=f"S{i}") for i in range(1, 13)]
    stops = [stop_row(call_id=i, symbol=f"S{i}") for i in range(1, 13)]
    out = m.step("2026-08-20", payload(entries=entries, stops=stops),
                 {**PRICES, **{f"S{i}": 50.0 for i in range(1, 13)}})
    assert len([o for o in out if o["action"] == "ENTER"]) == 10


def test_gate_no_reentry_of_a_previously_traded_call(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    m.state.entered_ids = [1]
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]), PRICES)
    assert not [o for o in out if o["action"] == "ENTER"]


def test_gate_entry_without_trail_level_is_skipped(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    out = m.step("2026-08-20", payload(entries=[entry()], stops=[]), PRICES)
    assert not [o for o in out if o["action"] == "ENTER"]
    assert any("no sizing reference" in e["msg"] for e in m.state.events)


# --- stop adjustment (cancel/replace) -----------------------------------------

def test_gate_stop_ratchets_up_via_cancel_replace(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    out = run_cycle(m, a, payload(stops=[stop_row(trail=47.0)]),
                    "2026-08-21", alert=lambda _: None)
    (adj,) = [o for o in out if o["action"] == "ADJUST_STOP"]
    assert adj["old_ref"] == "old-stop"
    pos = m.state.positions["1"]
    assert pos.stop_level == 47.0
    assert pos.stop_order_ref != "old-stop" and pos.stop_order_ref in a._stops
    cancels = [e for e in a.log if e["action"] == "cancel_stock_order"]
    assert cancels and cancels[0]["ref"] == "old-stop"


def test_gate_stop_never_lowers(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, stop_level=47.0)
    out = m.step("2026-08-21", payload(stops=[stop_row(trail=44.0)]), PRICES)
    assert not [o for o in out if o["action"] == "ADJUST_STOP"]


# --- exits --------------------------------------------------------------------

def test_gate_tracker_trail_exit_closes_position(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    run_cycle(m, a,
              payload(exits=[{"symbol": "CRSP", "call_id": 1,
                              "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=lambda _: None)
    assert "1" not in m.state.positions
    # stop cancelled, then a MKT sell of the full position
    assert [e["action"] for e in a.log][:2] == ["cancel_stock_order",
                                                "place_stock_order"]
    assert any("EXIT" in e["msg"] for e in m.state.events)


def test_gate_executor_time_stop_belt_fires_without_tracker(tmp_path):
    # A tracker outage/reconciliation gap must never hold a position past
    # day 90: the executor's own clock exits it.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, time_stop="2026-08-19")
    out = m.step("2026-08-20", payload(), PRICES)
    (ex,) = [o for o in out if o["action"] == "EXIT"]
    assert ex["reason"] == "time_stop" and ex["call_id"] == 1


def test_gate_exit_for_unheld_call_is_ignored(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    out = m.step("2026-08-20",
                 payload(exits=[{"symbol": "CRSP", "call_id": 99,
                                 "reason": "trail", "trail_level": 44.0}]),
                 PRICES)
    assert not [o for o in out if o["action"] == "EXIT"]


# --- band rebalance -----------------------------------------------------------

def test_gate_rebalance_only_beyond_5pp_band(tmp_path):
    m = mk(tmp_path)
    # w = 33% -> inside the band, nothing.
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=33, spy_qty=67)
    assert not [o for o in m.step("2026-08-20", payload(), PRICES)
                if o["action"] == "REBALANCE"]
    # w = 45% -> sleeve_to_core of exactly the 15pp drift.
    m2 = mk(tmp_path)
    _seed_initialized(m2, sleeve_cash=0.0, bil_qty=45, spy_qty=55)
    (rb,) = [o for o in m2.step("2026-08-20", payload(), PRICES)
             if o["action"] == "REBALANCE"]
    assert rb["direction"] == "sleeve_to_core"
    assert rb["usd"] == pytest.approx(1_500.0)


def test_gate_rebalance_core_to_sleeve_executes_and_sweeps(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=20, spy_qty=80)  # w = 20%
    a = DryAdapter()
    out = run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    (rb,) = [o for o in out if o["action"] == "REBALANCE"]
    assert rb["direction"] == "core_to_sleeve"
    assert rb["usd"] == pytest.approx(1_000.0)
    # $1,000 of SPY sold; proceeds swept into BIL. Book back at 30/70.
    assert m.state.spy_qty == 70
    assert m.state.bil_qty == 30
    assert m.sleeve_value({"SPY": 100.0, "BIL": 100.0}) == pytest.approx(3_000.0)


def test_gate_rebalance_sleeve_to_core_funds_from_bil(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=45, spy_qty=55)  # w = 45%
    a = DryAdapter()
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    assert m.state.bil_qty == 30
    # $1,500 moved to core; SPY buy happens the same cycle (CORE_BUY runs
    # after the rebalance in intent order).
    assert m.state.spy_qty == 70
    assert m.core_value({"SPY": 100.0, "BIL": 100.0}) == pytest.approx(7_000.0)


# --- BIL sweep ----------------------------------------------------------------

def test_gate_idle_sleeve_cash_sweeps_to_bil(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=500.0, bil_qty=25, spy_qty=70)
    (sw,) = [o for o in m.step("2026-08-20", payload(), PRICES)
             if o["action"] == "SWEEP"]
    assert sw["qty"] == 5                    # $500 // $100
    # dust below the order floor is left alone
    m.state.sleeve_cash = 20.0
    assert not [o for o in m.step("2026-08-20", payload(), PRICES)
                if o["action"] == "SWEEP"]


# --- budget cap + kill switch -------------------------------------------------

def test_gate_budget_cap_blocks_entries(tmp_path):
    m = mk(tmp_path, blend_budget=100.0)
    _seed_initialized(m)                     # entry cost would be $250 > $100
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]), PRICES)
    assert not [o for o in out if o["action"] == "ENTER"]
    assert any("BLEND_BUDGET" in e["msg"] for e in m.state.events)


def test_gate_budget_zero_means_disabled(tmp_path):
    m = mk(tmp_path, blend_budget=0.0)
    _seed_initialized(m)
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]), PRICES)
    assert [o for o in out if o["action"] == "ENTER"]


def test_gate_kill_switch_halts_everything(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    m.halt("KILL")
    assert m.step("2026-08-20",
                  payload(entries=[entry()], stops=[stop_row()]), PRICES) == []
    m.resume()
    assert m.step("2026-08-20", payload(), PRICES) != []


def test_gate_no_payload_means_no_action(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    assert m.step("2026-08-20", None, PRICES) == []


# --- DryAdapter stock support -------------------------------------------------

def test_gate_dry_adapter_stock_fills():
    a = DryAdapter()
    r = a.place_stock_order("SPY", 70, "MOO", tif="OPG", ref_price=101.5)
    assert r["status"] == "filled" and r["fill_price"] == 101.5
    r = a.place_stock_order("BIL", 30, "MKT")           # falls back to spot
    assert r["status"] == "filled" and r["fill_price"] == 100.0
    s = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    assert s["status"] == "working"
    fill = a.trigger_stop(s["order_ref"])               # STP fills AT the stop
    assert fill["fill_price"] == 44.0
    assert a.cancel_stock_order(s["order_ref"]) is False  # already gone
    with pytest.raises(ValueError):
        a.place_stock_order("SPY", 1, "LMT")
    with pytest.raises(ValueError):
        a.place_stock_order("SPY", 1, "STP")            # STP needs stop_price


# --- safety invariants + service wiring ---------------------------------------

def test_gate_blend_disabled_is_zero_change(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app import service
    from app.service import app

    assert settings.blend_enabled is False   # the shipped default
    assert settings.dry_run is True          # DRY_RUN default true, still
    assert settings.blend_budget == 0.0      # budget cap disabled by default
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        body = c.get("/status", params={"token": "sekrit"}).json()
        assert "blend" not in body           # /status byte-identical
        assert service.BLEND is None         # no manager was ever built


def test_gate_blend_enabled_status_and_kill(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app import service
    from app.service import app

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(app) as c:
            for _ in range(100):             # _build runs on the loop thread
                if service.BLEND is not None:
                    break
                time.sleep(0.05)
            assert service.BLEND is not None
            _seed_initialized(service.BLEND, sleeve_cash=2_750.0)
            _held_position(service.BLEND, stop_ref=None)
            body = c.get("/status", params={"token": "sekrit"}).json()
            b = body["blend"]
            assert set(b) >= {"enabled", "halted", "positions", "open_count",
                              "sleeve_cash", "bil_qty", "spy_qty", "core_cash",
                              "budget_cap", "events"}
            assert b["open_count"] == 1
            # /kill closes blend positions and halts the blend book too
            c.get("/kill", params={"token": "sekrit"})
            assert service.BLEND.state.positions == {}
            assert service.BLEND.state.halted == "KILL"
            c.get("/resume", params={"token": "sekrit"})
            assert service.BLEND.state.halted is None
    finally:
        service.BLEND = None
        service.MGR = None


def test_gate_tracker_never_learns_book_state(monkeypatch):
    """The poll is a bare authenticated GET: no params, no body, no headers
    carrying equity/positions — the tracker stays a keyless decision brain."""
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        seen["kwargs"] = kw

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True}

        return R()

    monkeypatch.setattr(blend_mod.httpx, "get", fake_get)

    class C(Cfg):
        tracker_url = "https://research.optic.capital/"
        tracker_user = "casey"
        tracker_password = "pw"

    assert fetch_intents(C()) == {"ok": True}
    assert seen["url"] == "https://research.optic.capital/blend3070/intents"
    assert set(seen["kwargs"]) == {"auth", "timeout"}   # nothing else sent
    assert seen["kwargs"]["auth"] == ("casey", "pw")


def test_gate_fetch_without_url_or_on_error_returns_none(monkeypatch):
    assert fetch_intents(Cfg()) is None

    def boom(url, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(blend_mod.httpx, "get", boom)

    class C(Cfg):
        tracker_url = "https://x"

    assert fetch_intents(C()) is None
