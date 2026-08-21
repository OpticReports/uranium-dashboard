"""blend3070 gates: state transitions on fixture intents, 1%-risk sizing,
GTC stop cancel/replace, time stop, band rebalance, BIL sweep, budget cap,
kill switch, DryAdapter stock fills, /status shape, and the safety
invariants (BLEND_ENABLED=false changes nothing; the tracker never learns
account equity; DRY_RUN defaults true). All offline."""
from __future__ import annotations

import json
import os
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
    dry_run = True              # mode-guard: tests run a "dry:paper" book
    trading_mode = "paper"


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


def _wait_until(cond, timeout=10.0):
    """Poll for an async condition (R2: the loop thread executes the /kill
    flatten after LOOP_WAKE — service tests wait for it, house idiom)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


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
    # Pinned contract (law #8, counter-agent N2): cancelling a FILLED order
    # RAISES — never an ambiguous False that could mask a fill race.
    with pytest.raises(RuntimeError):
        a.cancel_stock_order(s["order_ref"])
    assert a.cancel_stock_order("never-seen-ref") is False  # not found: False
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
            # /kill halts the blend book IMMEDIATELY and queues the flatten
            # for the execution loop (R2 two-stage), which closes positions
            # within seconds (LOOP_WAKE).
            r = c.get("/kill", params={"token": "sekrit"})
            assert r.json()["blend"] == "flatten_queued"
            assert service.BLEND.state.halted == "KILL"
            assert _wait_until(
                lambda: service.BLEND.state.positions == {}
                and service.BLEND.state.flatten_request is None)
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


# --- counter-agent regression gates (the 7 material findings + minors) --------
# Each scenario below is derived from the counter-agent's repro script
# (scratchpad/attack_blend.py): the attacks that CONFIRMED the defects are
# now merge-blocking gates asserting the fixed behavior.

class _RejectStopAdapter(DryAdapter):
    """STP placements rejected while reject_stp is True (venue outage sim)."""

    def __init__(self):
        super().__init__()
        self.reject_stp = True

    def place_stock_order(self, symbol, qty, order_type, **kw):
        if order_type == "STP" and self.reject_stp:
            raise RuntimeError("venue reject (simulated)")
        return super().place_stock_order(symbol, qty, order_type, **kw)


class _FlakyStopAdapter(DryAdapter):
    """First N STP placements rejected, later ones fine (transient reject)."""

    def __init__(self, fails=1):
        super().__init__()
        self.fails_left = fails

    def place_stock_order(self, symbol, qty, order_type, **kw):
        if order_type == "STP" and self.fails_left > 0:
            self.fails_left -= 1
            raise RuntimeError("venue reject (simulated)")
        return super().place_stock_order(symbol, qty, order_type, **kw)


class _NoFillPriceAdapter(DryAdapter):
    """MKT sells ack as filled but WITHOUT a fill price (broken venue ack)."""

    def place_stock_order(self, symbol, qty, order_type, **kw):
        r = super().place_stock_order(symbol, qty, order_type, **kw)
        if order_type == "MKT" and qty < 0:
            r = dict(r)
            r.pop("fill_price", None)
        return r


def _executions(a, symbol):
    """Actual sell executions for symbol: stop fills + filled MKT/MOO sells
    (a resting STP placement is not an execution)."""
    out = []
    for e in a.log:
        if e.get("symbol") != symbol or e.get("qty", 0) >= 0:
            continue
        if e["action"] == "stop_triggered":
            out.append(e)
        elif e["action"] == "place_stock_order" and e.get("status") == "filled":
            out.append(e)
    return out


# M1: venue stop fills reconciled BEFORE any decision; exit echo is a no-op.

def test_gate_m1_stop_fill_reconciled_before_exit_echo(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    a.trigger_stop(pos.stop_order_ref)      # the GTC stop fills intraday
    # Next day the tracker echoes the trail exit: must be a NO-OP.
    echo = payload(exits=[{"symbol": "CRSP", "call_id": 1,
                           "reason": "trail", "trail_level": 44.0}])
    run_cycle(m, a, echo, "2026-08-21", alert=lambda _: None)
    assert "1" not in m.state.positions
    sells = _executions(a, "CRSP")
    assert len(sells) == 1 and sells[0]["action"] == "stop_triggered"
    assert any("stop_filled" in e["msg"] for e in m.state.events)
    # Idempotent: a second echo cycle still does nothing.
    out = run_cycle(m, a, echo, "2026-08-22", alert=lambda _: None)
    assert not [i for i in out if i["action"] == "EXIT"]
    assert len(_executions(a, "CRSP")) == 1


def test_gate_m1_stop_fill_books_cash_at_the_stop_fill(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    a.trigger_stop(pos.stop_order_ref)      # 5 shares fill at 44.0
    run_cycle(m, a, None, "2026-08-21", alert=lambda _: None)
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 44.0)


# M2: one per-cycle cash ledger — a single clamped BIL sell funds everything;
# lowest-priority actions are skipped rather than overdrawing.

def test_gate_m2_entry_plus_rebalance_share_one_bil_ledger(tmp_path):
    # The counter-agent's attack 1: bil_qty went to -20 and core_cash -500.
    m = mk(tmp_path)
    m.state.initialized = True
    m.state.sleeve_cash = 0.0
    m.state.bil_qty = 20
    m.state.spy_qty = 30       # sleeve weight 40% -> sleeve_to_core wanted
    m.state.core_cash = 0.0
    ent = {"symbol": "TITE", "call_id": 7, "fire_date": "2026-08-20",
           "flag_type": "x", "risk_frac": 0.01, "entry_ref": 50.0, "note": ""}
    stp = {"symbol": "TITE", "call_id": 7, "trail_level": 49.9}
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[ent], stops=[stp]), "2026-08-20",
              alert=lambda _: None)
    assert m.state.bil_qty == 0                       # clamped, never short
    assert m.state.sleeve_cash >= -1e-6
    assert m.state.core_cash >= -1e-6
    bil_sells = [e for e in a.log if e["action"] == "place_stock_order"
                 and e["symbol"] == "BIL" and e["qty"] < 0]
    assert len(bil_sells) == 1 and bil_sells[0]["qty"] == -20   # ONE funding sell
    # The rebalance (lowest priority) was deferred, not overdrawn.
    assert any("rebalance deferred" in e["msg"] for e in m.state.events)


def test_gate_m2_unfundable_rebalance_deferred_never_oversells(tmp_path):
    # A sleeve->core transfer bigger than cash + ALL BIL: deferred with an
    # event, no BIL sell beyond holdings, ledger never negative.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=5_000.0, bil_qty=2, spy_qty=30)
    _held_position(m, qty=50, fill=100.0, stop_level=90.0,
                   time_stop="2099-01-01")            # sleeve mostly illiquid
    a = DryAdapter()
    run_cycle(m, a, payload(stops=[stop_row(trail=90.0)]), "2026-08-20",
              alert=lambda _: None)
    assert m.state.bil_qty >= 0
    bil_sells = [e for e in a.log if e["action"] == "place_stock_order"
                 and e["symbol"] == "BIL" and e["qty"] < 0]
    assert bil_sells == []                            # nothing to sell safely
    assert any("rebalance deferred" in e["msg"] for e in m.state.events)
    assert m.state.sleeve_cash >= -1e-6


# M3: failed initial stop placement -> retry in-cycle, STOP_MISSING alert,
# retried every cycle, blocks new entries until protected.

def test_gate_m3_transient_stop_reject_recovers_in_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(blend_mod, "STOP_RETRY_SLEEP_S", 0)
    m = mk(tmp_path)
    _seed_initialized(m)
    a = _FlakyStopAdapter(fails=1)
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    pos = m.state.positions["1"]
    assert pos.stop_missing is False
    assert pos.stop_order_ref in a._stops       # retry within the cycle won


def test_gate_m3_stop_missing_alerts_blocks_entries_then_heals(tmp_path, monkeypatch):
    monkeypatch.setattr(blend_mod, "STOP_RETRY_SLEEP_S", 0)
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10_000.0)
    a = _RejectStopAdapter()
    alerts: list[str] = []
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.stop_missing is True and pos.stop_order_ref is None
    assert any("STOP_MISSING" in msg for msg in alerts)
    # New entries are BLOCKED while any position is naked; the placement is
    # retried (and re-alerted) every cycle.
    alerts.clear()
    e2 = entry(call_id=2, symbol="NTLA")
    s2 = stop_row(call_id=2, symbol="NTLA", trail=44.0)
    out = run_cycle(m, a, payload(entries=[e2], stops=[s2, stop_row()]),
                    "2026-08-21", alert=alerts.append)
    assert not [i for i in out if i["action"] == "ENTER"]
    assert "2" not in m.state.positions
    assert any("STOP_MISSING" in msg for msg in alerts)
    assert any("entries BLOCKED" in msg for msg in alerts)
    # Venue heals: the reconcile pass restores the stop and entries resume.
    a.reject_stp = False
    run_cycle(m, a, payload(entries=[e2], stops=[s2, stop_row()]),
              "2026-08-22", alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.stop_missing is False and pos.stop_order_ref in a._stops
    assert "2" in m.state.positions             # entry unblocked after heal


# M4: exit/stop instructions must match BOTH call_id AND symbol.

def test_gate_m4_exit_symbol_mismatch_refused_with_alert(tmp_path):
    # The counter-agent's attack 4: {symbol: OTHER, call_id: 1} force-closed
    # the held CRSP position.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    out = m.step("2026-08-21",
                 payload(exits=[{"symbol": "OTHER", "call_id": 1,
                                 "reason": "trail", "trail_level": 10.0}]),
                 PRICES)
    assert not [i for i in out if i["action"] == "EXIT"]
    assert any(i["action"] == "ALERT" and "REFUSED exit" in i["msg"]
               for i in out)
    assert "1" in m.state.positions             # position kept


def test_gate_m4_stop_symbol_mismatch_refused(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    out = m.step("2026-08-21",
                 payload(stops=[{"symbol": "OTHER", "call_id": 1,
                                 "trail_level": 47.0}]), PRICES)
    assert not [i for i in out if i["action"] == "ADJUST_STOP"]
    assert any(i["action"] == "ALERT" and "REFUSED stop" in i["msg"]
               for i in out)
    assert m.state.positions["1"].stop_level == 44.0


def test_gate_m4_recycled_call_id_refused_with_alert(tmp_path):
    # entered_ids blocking a RE-USED call_id for a different symbol must be
    # loud (tracker DB reset detection), never a silent no-entry book.
    m = mk(tmp_path)
    _seed_initialized(m)
    m.state.entered_ids = [1]
    m.state.entered_symbols = {"1": "CRSP"}
    out = m.step("2026-08-20",
                 payload(entries=[entry(symbol="NEWCO")],
                         stops=[stop_row(symbol="NEWCO")]),
                 {**PRICES, "NEWCO": 50.0})
    assert not [i for i in out if i["action"] == "ENTER"]
    assert any(i["action"] == "ALERT" and "RECYCLED" in i["msg"] for i in out)


# M5: stop replace is place-NEW-first, cancel-old-second; a rejected
# replacement keeps the old stop.

def test_gate_m5_replace_places_new_stop_before_cancelling_old(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    run_cycle(m, a, payload(stops=[stop_row(trail=47.0)]), "2026-08-21",
              alert=lambda _: None)
    ops = [e for e in a.log
           if e["action"] in ("place_stock_order", "cancel_stock_order")]
    assert ops[0]["action"] == "place_stock_order"      # NEW stop first
    assert ops[0]["order_type"] == "STP" and ops[0]["stop_price"] == 47.0
    assert ops[1]["action"] == "cancel_stock_order"     # old cancelled after
    assert ops[1]["ref"] == "old-stop"
    assert m.state.positions["1"].stop_level == 47.0


def test_gate_m5_rejected_replacement_keeps_old_stop_working(tmp_path, monkeypatch):
    monkeypatch.setattr(blend_mod, "STOP_RETRY_SLEEP_S", 0)
    m = mk(tmp_path)
    _seed_initialized(m)
    a = _RejectStopAdapter()
    a.reject_stp = False
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    old_ref = m.state.positions["1"].stop_order_ref
    assert old_ref in a._stops
    a.reject_stp = True                           # the replacement will fail
    alerts: list[str] = []
    run_cycle(m, a, payload(stops=[stop_row(trail=47.0)]), "2026-08-21",
              alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.stop_order_ref == old_ref          # old stop untouched
    assert pos.stop_level == 44.0                 # ratchet not recorded
    assert old_ref in a._stops                    # ...and still WORKING
    assert any("REJECTED" in msg for msg in alerts)
    # Level unchanged means the ratchet retries next cycle once the venue
    # heals — never a naked window in between.
    a.reject_stp = False
    run_cycle(m, a, payload(stops=[stop_row(trail=47.0)]), "2026-08-22",
              alert=alerts.append)
    assert m.state.positions["1"].stop_level == 47.0


# M6: write-ahead journal + deterministic client order ids close the
# crash-window duplicate-MOO hole.

def test_gate_m6_boot_reconcile_adopts_orphan_venue_order(tmp_path):
    # Crash between placement and persist: the MOO reached the venue, the
    # state file never learned. On restart the order history is adopted —
    # never re-placed.
    m = mk(tmp_path)
    _seed_initialized(m)
    it = {"action": "ENTER", "call_id": 1, "symbol": "CRSP", "qty": 5,
          "entry_ref": 50.0, "stop_level": 44.0, "time_stop_days": 90,
          "reason": "test"}
    m.record_pending_entry(it, "2026-08-20")            # write-ahead persisted
    a = DryAdapter()
    a.place_stock_order("CRSP", 5, "MOO", tif="OPG", ref_price=50.0,
                        client_order_id=blend_mod.entry_client_id(1))
    # ...crash here. Restart:
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert "1" in m2.state.pending_entries              # journal survived
    run_cycle(m2, a, payload(stops=[stop_row()]), "2026-08-20",
              alert=lambda _: None)
    pos = m2.state.positions["1"]
    assert pos.qty == 5 and pos.fill_price == 50.0
    assert m2.state.pending_entries == {}
    assert pos.stop_order_ref in a._stops               # protective stop placed
    moos = [e for e in a.log if e["action"] == "place_stock_order"
            and e.get("order_type") == "MOO"]
    assert len(moos) == 1                               # NO duplicate MOO
    assert m2.state.sleeve_cash == pytest.approx(3_000.0 - 250.0 -
                                                 m2.state.bil_qty * 100.0)


def test_gate_m6_journal_without_venue_order_is_cleared_and_entry_retried(tmp_path):
    # Crash BEFORE placement: journal exists, venue never saw the order —
    # the journal clears and the same-day republish enters exactly once.
    m = mk(tmp_path)
    _seed_initialized(m)
    m.record_pending_entry({"action": "ENTER", "call_id": 1, "symbol": "CRSP",
                            "qty": 5, "entry_ref": 50.0, "stop_level": 44.0,
                            "time_stop_days": 90, "reason": "test"},
                           "2026-08-20")
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    assert m.state.positions["1"].qty == 5
    moos = [e for e in a.log if e["action"] == "place_stock_order"
            and e.get("order_type") == "MOO"]
    assert len(moos) == 1


def test_gate_m6_duplicate_client_order_id_suppressed_venue_side():
    a = DryAdapter()
    r1 = a.place_stock_order("CRSP", 5, "MOO", ref_price=50.0,
                             client_order_id="blend-1-entry")
    r2 = a.place_stock_order("CRSP", 5, "MOO", ref_price=50.0,
                             client_order_id="blend-1-entry")
    assert r2["order_ref"] == r1["order_ref"] and r2.get("duplicate") is True
    placed = [e for e in a.log if e["action"] == "place_stock_order"]
    assert len(placed) == 1                             # one real order only


# M7: a fill without a fill price is UNRECONCILED — never booked at 0.0.

def test_gate_m7_exit_without_fill_price_is_unreconciled_not_zero(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = _NoFillPriceAdapter()
    alerts: list[str] = []
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=alerts.append)
    assert "1" not in m.state.positions
    assert "1" in m.state.unreconciled                  # parked, not booked
    # NOTHING was credited at 0.0 (or at all): cash+BIL unchanged at the
    # post-entry level (2,750 seeded - 250 entry cost debited by the fixture).
    assert m.state.sleeve_cash + m.state.bil_qty * 100.0 == pytest.approx(2_500.0)
    assert any("UNRECONCILED" in msg for msg in alerts)


def test_gate_m7_stop_fill_without_price_is_unreconciled(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    a._fills.append({"order_ref": "old-stop", "symbol": "CRSP", "qty": -5,
                     "fill_price": None})
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-21", alert=alerts.append)
    assert "1" not in m.state.positions and "1" in m.state.unreconciled
    # cash stays at the post-entry level (2,750 - 250 fixture entry debit):
    # the price-less stop fill booked NOTHING.
    assert m.state.sleeve_cash == pytest.approx(2_500.0)
    assert any("UNRECONCILED" in msg or "NOT booked" in msg for msg in alerts)


def test_gate_m7_on_exited_refuses_a_none_fill(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    _held_position(m)
    with pytest.raises(ValueError):
        m.on_exited(1, None, "x")


# Minor findings: stale payload guard, non-positive trail guard, no-op
# rebalance alert suppression, DryAdapter fill queue/order lookup, dedicated
# read-only intents token.

def test_gate_stale_payload_blocks_decisions_but_still_reconciles(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    stale = payload(entries=[entry(call_id=2, symbol="NTLA")],
                    stops=[stop_row(call_id=2, symbol="NTLA")])
    alerts: list[str] = []
    out = run_cycle(m, a, stale, "2026-08-28", alert=alerts.append)
    assert out == []                                    # no new decisions
    assert "1" not in m.state.positions                 # but the fill reconciled
    assert "2" not in m.state.positions
    assert any("stale" in msg for msg in alerts)


def test_gate_nonpositive_trail_is_never_placed(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    out = m.step("2026-08-21", payload(stops=[stop_row(trail=-1.0)]), PRICES)
    assert not [i for i in out if i["action"] == "ADJUST_STOP"]
    m2 = Blend3070Manager(m.cfg, str(tmp_path / "b2.json"))
    _seed_initialized(m2)
    out2 = m2.step("2026-08-20",
                   payload(entries=[entry()], stops=[stop_row(trail=-1.0)]),
                   PRICES)
    assert not [i for i in out2 if i["action"] == "ENTER"]


def test_gate_noop_rebalance_does_not_alert(tmp_path):
    # w=0 wants core_to_sleeve, but no SPY is held to sell: the rebalance is
    # a no-op and must NOT fire the REBALANCE alert (counter-agent nit).
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=0, spy_qty=0,
                      core_cash=7_000.0)
    alerts: list[str] = []
    run_cycle(m, DryAdapter(), payload(), "2026-08-20", alert=alerts.append)
    assert not [x for x in alerts if "REBALANCE" in x]  # nothing moved


def test_gate_dry_adapter_fill_queue_and_order_lookup():
    a = DryAdapter()
    s = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                            client_order_id="blend-1-stp-44.0000")
    assert a.poll_stock_fills() == []
    a.trigger_stop(s["order_ref"])
    (f,) = a.poll_stock_fills()
    assert f["order_ref"] == s["order_ref"] and f["fill_price"] == 44.0
    assert a.poll_stock_fills() == []                   # drained
    o = a.find_stock_order("blend-1-stp-44.0000")
    assert o["status"] == "filled" and o["fill_price"] == 44.0
    assert a.find_stock_order("never-seen") is None


def test_gate_fetch_prefers_dedicated_readonly_token(monkeypatch):
    """TRACKER_API_TOKEN set -> the poll sends ONLY the X-API-Token header:
    the executor never transmits the dashboard password."""
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
        tracker_url = "https://research.optic.capital"
        tracker_user = "casey"
        tracker_password = "pw"
        tracker_api_token = "tok-123"

    assert fetch_intents(C()) == {"ok": True}
    assert set(seen["kwargs"]) == {"headers", "timeout"}
    assert seen["kwargs"]["headers"] == {"X-API-Token": "tok-123"}


# --- re-review regression gates (counter-agent N13/N14/N15/N5 + minors) -------
# Each scenario is derived from the re-review's repro scripts
# (scratchpad/new_attacks*.py): the attacks that CONFIRMED the defects are
# now merge-blocking gates asserting the fixed behavior.


# N13: a tracker outage must NEVER skip reconcile or the local belt — the
# cycle runs with payload=None; only tracker-dependent decisions skip.

def test_gate_n13_outage_cycle_still_ingests_fills_and_heals_stops(
        tmp_path, monkeypatch):
    monkeypatch.setattr(blend_mod, "STOP_RETRY_SLEEP_S", 0)
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10_000.0)
    a = _RejectStopAdapter()
    a.reject_stp = False
    run_cycle(m, a, payload(entries=[entry(), entry(call_id=2, symbol="NTLA")],
                            stops=[stop_row(),
                                   stop_row(call_id=2, symbol="NTLA")]),
              "2026-08-20", alert=lambda _: None)
    # Outage begins. Intraday: CRSP's stop fills; NTLA's stop dies venue-side.
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    m.state.positions["2"].stop_missing = True
    m.state.positions["2"].stop_order_ref = None
    # Tracker unreachable -> the cycle STILL runs with payload=None:
    run_cycle(m, a, None, "2026-08-21", alert=lambda _: None)
    assert "1" not in m.state.positions          # stop fill ingested
    pos2 = m.state.positions["2"]
    assert pos2.stop_missing is False            # protective stop re-placed
    assert pos2.stop_order_ref in a._stops


def test_gate_n13_time_stop_belt_fires_during_tracker_outage(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, time_stop="2026-08-19", stop_ref=None)
    m.state.positions["1"].stop_missing = True
    a = _RejectStopAdapter()                     # stop re-place keeps failing
    run_cycle(m, a, None, "2026-09-01", alert=lambda _: None)
    assert "1" not in m.state.positions          # belt exited it anyway
    sells = _executions(a, "CRSP")
    assert len(sells) == 1


def test_gate_n13_time_stop_belt_fires_on_stale_payload(tmp_path):
    # The re-review's N8b: position past its time stop + stale payload was
    # still held. The belt must fire whenever the cycle runs.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, time_stop="2026-08-25", stop_ref=None)
    stale = payload()                            # as_of 2026-08-20
    run_cycle(m, DryAdapter(), stale, "2026-09-01", alert=lambda _: None)
    assert "1" not in m.state.positions


def test_gate_n13_service_loop_runs_cycle_when_tracker_unreachable(
        tmp_path, monkeypatch):
    """The service loop calls run_cycle even when fetch_intents returns None
    (tracker outage) — reconcile + belt are unconditional."""
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    calls = []

    def fake_run_cycle(mgr, adapter, payload, today, alert=None):
        calls.append(payload)
        return []

    monkeypatch.setattr(blend_mod, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    monkeypatch.setattr(settings, "poll_seconds", 3600)
    assert settings.tracker_url == ""            # fetch_intents -> None
    try:
        with TestClient(service_app):
            for _ in range(200):
                if calls:
                    break
                _time.sleep(0.05)
            assert calls, "run_cycle was never called on a tracker outage"
            assert calls[0] is None              # the outage payload
    finally:
        service.BLEND = None
        service.MGR = None


# N14: /kill reconciles FIRST and closes only positions still actually held
# (idempotent with a stop fill that already happened at the venue).

def test_gate_n14_kill_does_not_double_sell_a_stop_filled_position(
        tmp_path, monkeypatch):
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B, A = service.BLEND, service.ADAPTER
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B, stop_ref=None)
            pos = B.state.positions["1"]
            rs = A.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     tif="GTC",
                                     client_order_id="blend-1-stp-44.0000")
            pos.stop_order_ref = rs["order_ref"]
            B.save()
            A.trigger_stop(pos.stop_order_ref)   # fills; NOT yet polled
            cash_before = B.state.sleeve_cash
            r = c.get("/kill", params={"token": "sekrit"})
            assert r.json()["halted"] == "KILL"
            # R2: the loop thread reconciles-first then flattens
            assert _wait_until(lambda: B.state.flatten_request is None)
            sells = _executions(A, "CRSP")
            assert len(sells) == 1               # the stop fill ONLY
            assert sells[0]["action"] == "stop_triggered"
            # proceeds booked exactly once, at the stop fill price
            assert B.state.sleeve_cash - cash_before == pytest.approx(5 * 44.0)
            assert B.state.positions == {} and B.state.halted == "KILL"
            assert A._fills == []                # nothing left unpolled
    finally:
        service.BLEND = None
        service.MGR = None


def test_gate_n14_kill_refuses_blind_flatten_when_reconcile_fails(
        tmp_path, monkeypatch):
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B, A = service.BLEND, service.ADAPTER
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B)

            def boom():
                raise RuntimeError("venue unreachable (simulated)")

            monkeypatch.setattr(A, "poll_stock_fills", boom)
            r = c.get("/kill", params={"token": "sekrit"})
            assert r.json()["halted"] == "KILL"
            assert B.state.halted == "KILL"      # halt is IMMEDIATE
            # R2: wait for the loop's flatten attempt — reconcile fails,
            # so the cycle fails CLOSED and nothing is blind-sold.
            assert _wait_until(
                lambda: service.BLEND_CYCLE["ok"] is False)
            assert "1" in B.state.positions      # NOT blind-sold
            assert _executions(A, "CRSP") == []
            # the flatten request survives to retry once the venue answers
            assert B.state.flatten_request is not None
    finally:
        service.BLEND = None
        service.MGR = None


# N15: CORE_BUY / rebalance core-sell / BIL sweep are write-ahead journaled
# with deterministic client ids and adopted from venue history after a crash.

class _CrashAfterPlaceAdapter(DryAdapter):
    """Simulates the process dying right AFTER the venue accepted+filled
    one targeted order (the N15 crash window)."""

    def __init__(self, symbol, direction):
        super().__init__()
        self.symbol = symbol
        self.direction = direction               # +1 buy / -1 sell
        self.armed = True

    def place_stock_order(self, symbol, qty, order_type, **kw):
        r = super().place_stock_order(symbol, qty, order_type, **kw)
        if (self.armed and symbol == self.symbol
                and qty * self.direction > 0 and order_type != "STP"):
            self.armed = False
            raise KeyboardInterrupt("crash AFTER venue accept (simulated)")
        return r


def _venue_fills(a, symbol, direction):
    return [e for e in a.log if e.get("symbol") == symbol
            and e.get("qty", 0) * direction > 0
            and e["action"] == "place_stock_order"
            and e.get("status") == "filled"]


def test_gate_n15_core_buy_crash_window_never_duplicates(tmp_path):
    # The re-review's repro: crash between the boot CORE_BUY fill and
    # on_core_trade left the venue at 140 SPY vs book 70.
    m = mk(tmp_path)
    a = _CrashAfterPlaceAdapter("SPY", +1)
    with pytest.raises(KeyboardInterrupt):
        run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    m2 = Blend3070Manager(m.cfg, m.state_path)   # restart
    assert m2.state.pending_book_orders          # journal survived the crash
    run_cycle(m2, a, payload(), "2026-08-20", alert=lambda _: None)
    spy_buys = _venue_fills(a, "SPY", +1)
    assert len(spy_buys) == 1                    # venue holds ONE buy
    assert m2.state.spy_qty == spy_buys[0]["qty"]  # book == venue
    assert m2.state.core_cash == pytest.approx(0.0)
    assert m2.state.pending_book_orders == {}    # journal fulfilled


def test_gate_n15_sweep_crash_window_never_duplicates(tmp_path):
    m = mk(tmp_path)
    a = _CrashAfterPlaceAdapter("BIL", +1)
    with pytest.raises(KeyboardInterrupt):
        run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    m2 = Blend3070Manager(m.cfg, m.state_path)
    run_cycle(m2, a, payload(), "2026-08-20", alert=lambda _: None)
    bil_buys = _venue_fills(a, "BIL", +1)
    assert len(bil_buys) == 1
    assert m2.state.bil_qty == bil_buys[0]["qty"]
    assert m2.state.sleeve_cash >= -1e-6
    assert m2.state.pending_book_orders == {}


def test_gate_n15_rebalance_core_sell_crash_window_never_duplicates(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=20, spy_qty=80)  # w = 20%
    a = _CrashAfterPlaceAdapter("SPY", -1)
    with pytest.raises(KeyboardInterrupt):
        run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    m2 = Blend3070Manager(m.cfg, m.state_path)
    run_cycle(m2, a, payload(), "2026-08-20", alert=lambda _: None)
    spy_sells = _venue_fills(a, "SPY", -1)
    assert len(spy_sells) == 1                   # the $1,000 sell, ONCE
    assert m2.state.spy_qty == 70                # booked once
    # transfer applied exactly once: sleeve got the proceeds (cash or BIL)
    assert m2.sleeve_value({"SPY": 100.0, "BIL": 100.0}) == pytest.approx(3_000.0)
    assert m2.state.core_cash == pytest.approx(0.0)
    assert m2.state.pending_book_orders == {}


def test_gate_n15_book_journal_without_venue_order_cleared(tmp_path):
    # Crash BEFORE placement: journal exists, venue never saw the order —
    # cleared, then step re-plans naturally (exactly one real order).
    m = mk(tmp_path)
    cid = m.record_pending_book_order("core-buy", "SPY", 70, "2026-08-19")
    a = DryAdapter()
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    assert cid not in m.state.pending_book_orders
    assert len(_venue_fills(a, "SPY", +1)) == 1
    assert m.state.spy_qty == 70


# N5: deferred/unreconciled exit proceeds never fund same-cycle entries.

class _RaisingCancelAdapter(DryAdapter):
    def cancel_stock_order(self, order_ref):
        raise RuntimeError("venue cancel error (simulated)")


def test_gate_n5_deferred_exit_drops_same_cycle_entries(tmp_path):
    # The re-review's repro: sleeve_cash 0, a $2,500 exit deferred (raising
    # cancel), a new entry sized on its proceeds still bought -> ledger -2,500.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=0)
    _held_position(m, call_id=9, symbol="OLD", qty=50, fill=50.0,
                   time_stop="2099-01-01", stop_ref="old-stop-9")
    m.state.sleeve_cash = 0.0                    # fixture debit undone: broke
    a = _RaisingCancelAdapter()
    newent = entry(call_id=10, symbol="NEW")
    newstp = stop_row(call_id=10, symbol="NEW", trail=49.0)
    alerts: list[str] = []
    run_cycle(m, a,
              payload(entries=[newent],
                      stops=[newstp, stop_row(call_id=9, symbol="OLD")],
                      exits=[{"symbol": "OLD", "call_id": 9, "reason": "trail",
                              "trail_level": 44.0}]),
              "2026-08-20", alert=alerts.append)
    assert "9" in m.state.positions              # exit deferred, kept
    assert "10" not in m.state.positions         # entry NOT taken
    assert _executions(a, "NEW") == [] and not [
        e for e in a.log if e.get("symbol") == "NEW"
        and e["action"] == "place_stock_order"]
    assert m.state.sleeve_cash >= -1e-6          # ledger never negative
    assert any("funding exit did not book" in msg for msg in alerts)


def test_gate_n5_unreconciled_exit_drops_same_cycle_entries(tmp_path):
    # Same law when the exit sells but the venue ack has no fill price:
    # proceeds are NOT booked -> the planned entry must not spend them.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=0)
    _held_position(m, call_id=9, symbol="OLD", qty=50, fill=50.0,
                   time_stop="2099-01-01", stop_ref=None)
    m.state.sleeve_cash = 0.0                    # fixture debit undone: broke
    m.state.positions["9"].stop_missing = False  # exit path w/o stop cancel
    a = _NoFillPriceAdapter()
    alerts: list[str] = []
    run_cycle(m, a,
              payload(entries=[entry(call_id=10, symbol="NEW")],
                      stops=[stop_row(call_id=10, symbol="NEW", trail=49.0)],
                      exits=[{"symbol": "OLD", "call_id": 9, "reason": "trail",
                              "trail_level": 44.0}]),
              "2026-08-20", alert=alerts.append)
    assert "9" in m.state.unreconciled           # parked, nothing booked
    assert "10" not in m.state.positions         # entry NOT taken
    assert m.state.sleeve_cash >= -1e-6


# N2 (minor): an ambiguous stop cancel is verified before the market sell.

class _FalseCancelRaceAdapter(DryAdapter):
    """The stop fills in the instant before the cancel lands, and the venue
    answers the ambiguous False ('already gone') instead of raising."""

    def cancel_stock_order(self, order_ref):
        if order_ref in self._stops:
            self.trigger_stop(order_ref)         # the fill wins the race
        self._rec("cancel_stock_order", ref=order_ref, found=False)
        return False


def test_gate_n2_false_cancel_verified_never_double_sells(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = _FalseCancelRaceAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 44.0}]),
              "2026-08-21", alert=lambda _: None)
    sells = _executions(a, "CRSP")
    assert len(sells) == 1                       # the racing stop fill ONLY
    assert sells[0]["action"] == "stop_triggered"
    assert "1" not in m.state.positions
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 44.0)


def test_gate_n2_cancel_of_filled_order_raises_then_reconciles(tmp_path):
    """Pinned adapter contract: cancel of a FILLED order RAISES — the exit
    defers, and the next cycle's reconcile books the stop fill (one sell)."""

    class _Race(DryAdapter):
        def cancel_stock_order(self, order_ref):
            if order_ref in self._stops:
                self.trigger_stop(order_ref)
            return super().cancel_stock_order(order_ref)   # now RAISES

    m = mk(tmp_path)
    _seed_initialized(m)
    a = _Race()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 44.0}]),
              "2026-08-21", alert=lambda _: None)
    run_cycle(m, a, None, "2026-08-22", alert=lambda _: None)
    assert len(_executions(a, "CRSP")) == 1
    assert "1" not in m.state.positions and not m.state.unreconciled


# N3 (minor): a mid-ingestion failure re-queues fills — none are ever lost.

def test_gate_n3_ingest_failure_requeues_fills_then_heals(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=6_000.0)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry(),
                                     entry(call_id=2, symbol="NTLA")],
                            stops=[stop_row(),
                                   stop_row(call_id=2, symbol="NTLA")]),
              "2026-08-20", alert=lambda _: None)
    a.trigger_stop(m.state.positions["1"].stop_order_ref)
    a.trigger_stop(m.state.positions["2"].stop_order_ref)
    cash_before = m.state.sleeve_cash

    def bomb(_msg):
        raise RuntimeError("telegram down (simulated raising alert)")

    with pytest.raises(RuntimeError):
        run_cycle(m, a, None, "2026-08-21", alert=bomb)
    assert a._fills                              # unprocessed fills RE-QUEUED
    # next cycle (alerts healthy) books everything exactly once
    run_cycle(m, a, None, "2026-08-22", alert=lambda _: None)
    assert m.state.positions == {}
    # each entry sized 10 sh (1% of $6,000 sleeve / $6 per-share risk):
    # both fills booked exactly once at the 44.0 stop
    assert m.state.sleeve_cash - cash_before == pytest.approx(2 * 10 * 44.0)
    assert len(_executions(a, "CRSP")) == 1
    assert len(_executions(a, "NTLA")) == 1


# Remaining minors: malformed as_of, sweep-vs-budget drift, journaled-order
# fills never RED-alerted as unknown.

def test_gate_minor_malformed_as_of_treated_stale_not_fresh(tmp_path):
    from app.blend import payload_is_stale

    assert payload_is_stale({"as_of": "not-a-date"}, "2026-08-20") is True
    m = mk(tmp_path)
    _seed_initialized(m)
    bad = payload(entries=[entry()], stops=[stop_row()])
    bad["as_of"] = "garbage"
    alerts: list[str] = []
    out = run_cycle(m, DryAdapter(), bad, "2026-08-20", alert=alerts.append)
    assert out == []                             # no decisions on garbage
    assert any("stale" in msg for msg in alerts)


def test_gate_minor_bil_sweep_respects_budget_cap(tmp_path):
    # Gross must not drift above BLEND_BUDGET via the cash vehicle: the
    # idle-cash sweep is clamped to the remaining gross headroom.
    m = mk(tmp_path, blend_budget=7_500.0)
    _seed_initialized(m, sleeve_cash=3_000.0, bil_qty=0, spy_qty=70)
    (sw,) = [o for o in m.step("2026-08-20", payload(), PRICES)
             if o["action"] == "SWEEP"]
    assert sw["qty"] == 5                        # $500 headroom, not $3,000
    # and without a budget the sweep is unclamped as before
    m2 = mk(tmp_path)
    _seed_initialized(m2, sleeve_cash=3_000.0, bil_qty=0, spy_qty=70)
    (sw2,) = [o for o in m2.step("2026-08-20", payload(), PRICES)
              if o["action"] == "SWEEP"]
    assert sw2["qty"] == 30


def test_gate_minor_journaled_order_fill_is_not_unknown_alerted(tmp_path):
    # A venue that streams MOO fills through the fill poll: the fill of a
    # JOURNALED entry is absorbed by the journal reconcile, never the
    # unknown-order RED alert (real-venue contract note).
    m = mk(tmp_path)
    _seed_initialized(m)
    it = {"action": "ENTER", "call_id": 1, "symbol": "CRSP", "qty": 5,
          "entry_ref": 50.0, "stop_level": 44.0, "time_stop_days": 90,
          "reason": "test"}
    m.record_pending_entry(it, "2026-08-20")
    a = DryAdapter()
    r = a.place_stock_order("CRSP", 5, "MOO", tif="OPG", ref_price=50.0,
                            client_order_id=blend_mod.entry_client_id(1))
    a._fills.append({"order_ref": r["order_ref"], "symbol": "CRSP", "qty": 5,
                     "fill_price": 50.0})
    alerts: list[str] = []
    m2 = Blend3070Manager(m.cfg, m.state_path)
    run_cycle(m2, a, payload(stops=[stop_row()]), "2026-08-20",
              alert=alerts.append)
    assert not any("UNKNOWN order" in msg for msg in alerts)
    pos = m2.state.positions["1"]
    assert pos.qty == 5 and pos.fill_price == 50.0     # adopted once
    moos = [e for e in a.log if e.get("order_type") == "MOO"]
    assert len(moos) == 1


def test_gate_kd_kill_raising_cancel_never_market_sells(tmp_path, monkeypatch):
    """Final-review K-d: a RAISING stop cancel means the stop FILLED (pinned
    law #8) — /kill must park the position for reconcile, never MKT-sell it
    (the venue would hold a double sell)."""
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B, A = service.BLEND, service.ADAPTER
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B, stop_ref=None)
            pos = B.state.positions["1"]
            rs = A.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     tif="GTC",
                                     client_order_id="blend-1-stp-44.0000")
            pos.stop_order_ref = rs["order_ref"]
            B.save()

            def raising_cancel(ref):
                raise RuntimeError("order already filled")
            monkeypatch.setattr(A, "cancel_stock_order", raising_cancel)

            r = c.get("/kill", params={"token": "sekrit"})
            assert r.json()["halted"] == "KILL"
            # R2: the loop thread executes the flatten; K-d must survive.
            assert _wait_until(lambda: B.state.flatten_request is None)
            # No market sell may be placed against the maybe-filled stop.
            mkt_sells = [e for e in _executions(A, "CRSP")
                         if e["action"] != "stop_triggered"]
            assert mkt_sells == []
            # Parked, not silently dropped: position retained + orphan tracked
            # so reconcile settles it on the next pass.
            assert "1" in B.state.positions
            assert pos.stop_order_ref in B.state.orphan_stop_refs
    finally:
        service.BLEND = None
        service.MGR = None


# --- adapter-review regression gates (M3/M4 + escalated m2/m3/m4 minors) ------
# Scenarios derived from the failed IB-adapter review's attack notes.


# M3: partial-fill-aware cancel/flatten — never oversell.

def test_gate_adapt_m3_partial_stop_then_exit_sells_only_remaining(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)       # 5 sh CRSP, stop 44
    a.trigger_stop_partial(m.state.positions["1"].stop_order_ref, 3)
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    alerts: list[str] = []
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=alerts.append)
    assert "1" not in m.state.positions
    sold = -sum(e["qty"] for e in _executions(a, "CRSP"))
    assert sold == 5                      # 3 partial + 2 remainder, NEVER 8
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 44.0)
    assert any("PARTIAL" in msg for msg in alerts)


def test_gate_adapt_m3_partial_stop_remainder_reprotected(tmp_path):
    # No exit signal: after a partial stop fill the remainder must get a
    # NEW protective stop from reconcile (the old one is terminal).
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    a.trigger_stop_partial(m.state.positions["1"].stop_order_ref, 3)
    run_cycle(m, a, payload(stops=[stop_row()]), "2026-08-21",
              alert=lambda _: None)
    pos = m.state.positions["1"]
    assert pos.qty == 2                              # partial booked
    assert pos.stop_missing is False
    assert pos.stop_order_ref in a._stops            # remainder re-protected
    assert a._stops[pos.stop_order_ref]["qty"] == -2


def test_gate_adapt_m3_kill_after_partial_stop_never_oversells(
        tmp_path, monkeypatch):
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B, A = service.BLEND, service.ADAPTER
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B, stop_ref=None)
            pos = B.state.positions["1"]
            rs = A.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     tif="GTC",
                                     client_order_id="blend-1-stp-44.0000")
            pos.stop_order_ref = rs["order_ref"]
            B.save()
            A.trigger_stop_partial(rs["order_ref"], 3)   # 3 fill, stop dies
            c.get("/kill", params={"token": "sekrit"})
            # R2: loop-thread flatten — partial booked by reconcile first
            assert _wait_until(
                lambda: B.state.positions == {}
                and B.state.flatten_request is None)
            assert B.state.halted == "KILL"
            sold = -sum(e["qty"] for e in _executions(A, "CRSP"))
            assert sold == 5                 # 3 partial + 2 MKT, never 8
    finally:
        service.BLEND = None
        service.MGR = None


# M4: a missing SPY/BIL quote must never manufacture a rebalance.

def test_gate_adapt_m4_missing_core_quote_skips_rebalance_alerts_once(
        tmp_path):
    # The review's attack: SPY quote missing -> core valued 0 -> sleeve
    # weight ~1 -> spurious sleeve_to_core transfer booked, unwound later
    # with REAL trades.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=30, spy_qty=70)  # at target
    no_spy = {"BIL": 100.0}
    out = m.step("2026-08-20", payload(), no_spy)
    assert not [o for o in out if o["action"] == "REBALANCE"]
    (al,) = [o for o in out if o["action"] == "ALERT"]
    assert "missing quote" in al["msg"]
    # alert fires ONCE per outage: the next cycle stays quiet
    out2 = m.step("2026-08-20", payload(), no_spy)
    assert not [o for o in out2 if o["action"] in ("ALERT", "REBALANCE")]
    # missing BIL likewise (fresh book: its own state file — the armed
    # flag is persisted now, r3)
    m2 = Blend3070Manager(Cfg(), str(tmp_path / "b2.json"))
    _seed_initialized(m2, sleeve_cash=0.0, bil_qty=30, spy_qty=70)
    out3 = m2.step("2026-08-20", payload(), {"SPY": 100.0})
    assert not [o for o in out3 if o["action"] == "REBALANCE"]
    assert [o for o in out3 if o["action"] == "ALERT"]
    # no equity snapshot on absent CORE/BIL quotes (distorted valuation)
    m.record_equity_snapshot("2026-08-20", no_spy)
    assert m.state.equity_curve == []


class _NoSpyQuoteAdapter(DryAdapter):
    def spot(self, symbol):
        if symbol == "SPY":
            raise RuntimeError("no market price for SPY (simulated)")
        return super().spot(symbol)


def test_gate_adapt_m4_cycle_with_failed_spy_quote_books_nothing(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=30, spy_qty=70)  # at target
    a = _NoSpyQuoteAdapter()
    core_before, sleeve_before = m.state.core_cash, m.state.sleeve_cash
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _: None)
    assert m.state.core_cash == core_before          # no phantom transfer
    assert m.state.sleeve_cash == sleeve_before
    assert m.state.pending_book_orders == {}         # no orders either
    assert m.state.equity_curve == []                # no distorted snapshot


# m2 (escalated): multi-day blackout — cancel False + verify-empty +
# horizon exceeded is UNVERIFIABLE (park + alert), never a MKT sell.

def test_gate_adapt_m2min_blackout_horizon_parks_instead_of_selling(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)                    # stop ref the venue never saw
    m.state.last_reconcile_ts = time.time() - 3 * 86_400   # 3-day blackout
    a = DryAdapter()                     # cancel("old-stop") -> False
    alerts: list[str] = []
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=alerts.append)
    assert "1" not in m.state.positions
    assert "1" in m.state.unreconciled           # parked for manual review
    assert _executions(a, "CRSP") == []          # NOTHING sold (no short)
    assert any("UNVERIFIABLE" in msg for msg in alerts)
    # nothing was booked from the unverifiable exit: cash + BIL stay at the
    # post-entry level (idle cash may have been swept to BIL in-cycle)
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(2_500.0))


def test_gate_adapt_m2min_fresh_history_false_cancel_still_sells(tmp_path):
    # Control: with a fresh reconcile history the same False cancel remains
    # the normal verified-sell path (no behavior regression).
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    m.state.last_reconcile_ts = time.time() - 600     # 10 minutes ago
    a = DryAdapter()
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=lambda _: None)
    assert "1" not in m.state.positions
    assert not m.state.unreconciled
    assert len(_executions(a, "CRSP")) == 1


# R1 (re-review residual): the blackout guard must be MORE than one cycle
# deep — UNVERIFIABLE positions stay parked until a reconcile POSITIVELY
# verifies them at the venue (positions data), never cleared by timestamp.
# Scenarios derived from the re-review's probe A1 (scratchpad
# attack_reround.py): the demonstrated naked short on cycle N+1.

EXIT_CRSP = {"symbol": "CRSP", "call_id": 1, "reason": "trail",
             "trail_level": 47.0}


class _NoVenuePositionsAdapter(DryAdapter):
    """Venue cannot answer the positions query — verification must stay
    parked (fail closed), never clear on a fresh reconcile timestamp."""

    def stock_position(self, symbol):
        raise RuntimeError("positions unavailable (simulated)")


def test_gate_r1_blackout_flag_survives_past_first_recovered_cycle(tmp_path):
    """Probe A1: the stop filled INSIDE a 3-day blackout (history gone, the
    fill invisible forever). Cycle N (tracker down) reconciles fine and
    stamps the horizon clock; the exit lands on cycle N+1 — the old code's
    gap check had reset and MKT-sold shares the venue no longer held (a
    naked short). With positions data unavailable the flag must persist."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, stop_ref=None)
    m.state.positions["1"].stop_missing = True       # stop died in the blackout
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    a = _NoVenuePositionsAdapter()
    alerts: list[str] = []
    # cycle N: tracker still down -> reconcile-only; the position gets
    # flagged and NOTHING (not even a protective stop) is placed for it —
    # a new SELL stop on shares the account may not hold is a short path.
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert m.state.positions["1"].history_gap is True
    assert not [e for e in a.log if e.get("symbol") == "CRSP"]
    # cycle N+1: the tracker recovers and publishes the pierced-trail exit.
    run_cycle(m, a, payload(exits=[EXIT_CRSP], stops=[stop_row()]),
              "2026-08-24", alert=alerts.append)
    assert "1" in m.state.positions                  # NOT sold
    assert m.state.positions["1"].history_gap is True
    assert not [e for e in a.log if e.get("symbol") == "CRSP"]  # no short
    assert any("UNVERIFIABLE" in msg for msg in alerts)
    assert any("deferred" in msg for msg in alerts)
    # the flag is journaled: a restart cannot lose the parked state
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert m2.state.positions["1"].history_gap is True


def test_gate_r1_venue_gone_parks_unreconciled_never_sells(tmp_path):
    """Probe A1 with the venue answering positions: the shares are GONE
    (the stop filled invisibly) and no priced fill is served — the position
    parks UNRECONCILED on the first reconcile; the later exit is a no-op
    and no MKT sell ever reaches the venue."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)                    # stop ref the venue never saw
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    a = DryAdapter()                     # stock_position("CRSP") == 0: gone
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)      # cycle N
    assert "1" not in m.state.positions
    assert "1" in m.state.unreconciled   # parked for manual booking
    run_cycle(m, a, payload(exits=[EXIT_CRSP], stops=[stop_row()]),
              "2026-08-24", alert=alerts.append)                  # cycle N+1
    assert _executions(a, "CRSP") == []  # NOTHING sold across both cycles
    assert any("UNVERIFIABLE" in msg for msg in alerts)
    # nothing booked at a guessed price: cash + BIL stay at the post-entry
    # level (idle cash may have been swept to BIL in-cycle)
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(2_500.0))


def test_gate_r1_positive_verification_unparks_and_exit_proceeds(tmp_path):
    """The venue POSITIVELY holds the shares and the stop still works:
    the flag clears and the next exit executes normally — parking is a
    guard, not a wedge."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    rs = a.place_stock_order("CRSP", 5, "MKT", ref_price=50.0)   # venue holds 5
    rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                             client_order_id="blend-1-stp-44.0000")
    m.state.positions["1"].stop_order_ref = rs["order_ref"]
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)      # cycle N
    pos = m.state.positions["1"]
    assert pos.history_gap is False                  # unparked on evidence
    assert pos.stop_order_ref in a._stops            # stop kept working
    assert any("POSITIVELY verified" in msg for msg in alerts)
    run_cycle(m, a, payload(exits=[EXIT_CRSP], stops=[stop_row()]),
              "2026-08-24", alert=alerts.append)                  # cycle N+1
    assert "1" not in m.state.positions and not m.state.unreconciled
    sells = _executions(a, "CRSP")
    assert len(sells) == 1 and sells[0]["qty"] == -5  # exactly one exit sell


def test_gate_r1_blackout_stop_fill_recovered_from_history_books_at_price(
        tmp_path):
    """The shares are gone AND refreshed order history still serves the
    priced stop fill (the fill-event stream was lost to a restart): book
    the exit at the REAL venue price — never a guess, never a sell."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = DryAdapter()
    rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                             client_order_id="blend-1-stp-44.0000")
    m.state.positions["1"].stop_order_ref = rs["order_ref"]
    # the stop filled during the blackout; the drain-once event stream was
    # lost with the process, but the order lookup still serves the price
    a._orders[rs["order_ref"]]["status"] = "filled"
    a._orders[rs["order_ref"]]["fill_price"] = 44.0
    a._stops.pop(rs["order_ref"], None)
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" not in m.state.positions and not m.state.unreconciled
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(2_500.0 + 5 * 44.0))    # booked AT the fill
    assert not [e for e in a.log if e.get("symbol") == "CRSP"
                and e["action"] == "place_stock_order"
                and e.get("order_type") != "STP"]    # nothing sold
    assert any("recovered from venue history" in msg for msg in alerts)


# N1/N2 (counter-review of the R1 pass): the blackout verification itself
# must not create the very orders it exists to prevent.
#   N1 — a position parked UNRECONCILED must have its resting stop RETIRED
#        first (a -qty stop the book abandons is a naked short waiting to
#        trigger) and the alert must state the venue's ACTUAL quantity.
#   N2 — `stock_position` sums EVERY account STK row for the symbol, so
#        shares held OUTSIDE the blend book must never verify a position
#        whose own stop actually filled. The stop ORDER's status is
#        order-scoped evidence and is consulted FIRST; position rows are
#        corroboration only.

def _blackout_stop(m, a, call_id=1, symbol="CRSP", qty=5, level=44.0):
    """Held position + its real resting GTC stop at the venue, then a
    3-day reconcile blackout (the R1 flagging condition)."""
    _held_position(m, call_id=call_id, symbol=symbol, qty=qty,
                   stop_level=level)
    rs = a.place_stock_order(symbol, -qty, "STP", stop_price=level, tif="GTC",
                             client_order_id=f"blend-{call_id}-stp-{level:.4f}")
    m.state.positions[str(call_id)].stop_order_ref = rs["order_ref"]
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    return rs["order_ref"]


def test_gate_n1_blackout_park_retires_the_resting_stop(tmp_path):
    """Probe B1: the operator manually sold 3 of the 5 during the blackout
    (the /kill loop-down alert invites exactly that) while the -5 GTC stop
    kept resting. The park must RETIRE that stop: left resting it triggers
    into a 2-share account — short 3, visible to the book only as a
    post-hoc UNKNOWN-order alert."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 2                     # manual sale of 3, in the dark
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" not in m.state.positions and "1" in m.state.unreconciled
    assert ref not in a._stops or ref in m.state.orphan_stop_refs
    assert _executions(a, "CRSP") == []          # nothing sold by the book
    assert a._positions["CRSP"] == 2             # and no short at the venue
    # honest wording: the venue holds 2 of the 5 the book claims — the
    # position is NOT simply "gone"
    (park,) = [msg for msg in alerts if "parked for manual booking" in msg]
    assert "holds 2 of the 5" in park and "UNPROTECTED" in park
    assert "GONE" not in park


def test_gate_n1_unretirable_stop_is_orphan_tracked(tmp_path):
    """The cancel of the abandoned stop RAISES (pinned contract: the stop
    FILLED) — it must land in orphan_stop_refs (the /kill park pattern) so
    pass 3 retries it and a fill on it alerts RED, never be forgotten."""
    class _RaisingCancel(DryAdapter):
        def cancel_stock_order(self, ref):
            raise RuntimeError("cancel unavailable (simulated)")

    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = _RaisingCancel()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 0                     # shares gone entirely
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" in m.state.unreconciled
    assert ref in m.state.orphan_stop_refs        # tracked, retried, RED on fill
    assert any("could NOT be cancelled" in msg for msg in alerts)
    assert _executions(a, "CRSP") == []


def test_gate_n2_external_shares_never_verify_a_stopped_out_position(tmp_path):
    """Probe B2: the blend's 5 CRSP were stopped out inside the blackout
    (fill event lost with the restart) while the ACCOUNT holds 6 CRSP
    bought outside the book. Account rows say 6 >= 5 — but the position's
    OWN stop is FILLED with a price, and that order-scoped evidence wins:
    the exit books at the venue price instead of a phantom being unparked
    and 'protected' by a dead order."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._orders[ref]["status"] = "filled"          # filled in the dark
    a._orders[ref]["fill_price"] = 44.0
    a._stops.pop(ref, None)
    a._positions["CRSP"] = 6                     # external/manual shares only
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" not in m.state.positions and not m.state.unreconciled
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(2_500.0 + 5 * 44.0))     # booked AT the stop
    assert _executions(a, "CRSP") == []
    assert not any("POSITIVELY verified" in msg for msg in alerts)


def test_gate_n2_no_sell_stop_re_placed_on_external_shares(tmp_path):
    """Probe B2b: same conflation with the blend stop CANCELLED inside the
    blackout. Order history is silent and the account rows are conflated
    (6 > 5 booked) — nothing proves the shares are the book's, so the
    position stays UNVERIFIABLE. Unparking it would let pass 4 place a
    fresh -5 SELL stop on the OPERATOR's own shares."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a.cancel_stock_order(ref)                    # cancelled during the blackout
    a._positions["CRSP"] = 6                     # external/manual shares only
    run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
    assert m.state.positions["1"].history_gap is True     # still parked
    assert not [e for e in a.log if e["action"] == "place_stock_order"
                and e.get("order_type") == "STP" and e["ref"] != ref]
    assert any("conflated with external shares" in e["msg"]
               for e in m.state.events)


def test_gate_x1_working_stop_never_verifies_conflated_shares(tmp_path):
    """X1 (supersedes the cde6fb7 gate that pinned the OPPOSITE outcome —
    this one attacks the same cell strictly harder).

    A WORKING stop is ORDER-scoped proof that THAT STOP did not fill. It
    proves nothing about whether the book's shares left by another route
    (manual sale out of a pooled position, broker liquidation, transfer)
    while same-symbol shares stay in the account. With held > booked the
    two cases are indistinguishable, so the guard must NOT convert "the
    stop is alive" into "the shares are ours": the position stays flagged,
    nothing is sold, no new stop is placed — and the working stop is LEFT
    RESTING, because retiring it would strip real protection."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 6                     # 5 booked + 1 external
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.history_gap is True               # NOT unparked
    assert pos.stop_order_ref == ref and ref in a._stops   # same stop kept
    assert any("conflated with external shares" in e["msg"]
               and "shares OUTSIDE the blend book" in e["msg"]
               for e in m.state.events)
    # the alert must never assert ownership on conflated rows
    assert not any("POSITIVELY verified" in msg for msg in alerts)
    assert not any("the shares are held" in msg for msg in alerts)
    (esc,) = [msg for msg in alerts if "UNRESOLVED after the blackout" in msg]
    assert "UNPROVABLE" in esc and "LEFT RESTING" in esc
    # and the tracker's next exit must not MKT-sell the operator's shares
    run_cycle(m, a, payload(exits=[EXIT_CRSP], stops=[stop_row()]),
              "2026-08-24", alert=alerts.append)
    assert "1" in m.state.positions and _executions(a, "CRSP") == []
    assert a._positions["CRSP"] == 6             # untouched at the venue
    # ...nor may /kill flatten it (C10)
    m.request_flatten("2026-08-24")
    kill_alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=kill_alerts.append)
    assert "1" in m.state.positions and _executions(a, "CRSP") == []
    assert a._positions["CRSP"] == 6
    (summary,) = [msg for msg in kill_alerts if "flatten finished" in msg]
    assert "NOT closed" in summary and "CRSP" in summary


def test_gate_x3_conflated_dead_stop_stays_loud_and_visible(tmp_path):
    """X3: the fail-closed cell must not fail SILENTLY. Conflated rows
    (ONE extra same-symbol share is enough) plus a stop the venue cancelled
    inside the blackout leave a REAL position with zero stops at the venue
    — cde6fb7 left it stop_missing=False with a stale ref and no alert
    after cycle 1, indefinitely (law #3's liveness clause). It must stay
    flagged, drop the dead ref, mark itself unprotected for /status and the
    feed, and keep escalating on a re-armed cadence."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a.cancel_stock_order(ref)                    # IB-initiated GTC cancel
    a._positions["CRSP"] = 6                     # the book's 5 + ONE external
    placed_before = len([e for e in a.log
                         if e["action"] == "place_stock_order"])
    per_cycle: list[int] = []
    for c in range(2 * blend_mod.UNVERIFIED_REALERT_CYCLES):
        alerts: list[str] = []
        run_cycle(m, a, None, "2026-08-%02d" % (24 + c), alert=alerts.append)
        per_cycle.append(sum(1 for msg in alerts
                             if "UNRESOLVED after the blackout" in msg))
        m.state.last_reconcile_ts = time.time()  # normal cadence from here
    pos = m.state.positions["1"]
    assert pos.history_gap is True               # never unparked
    assert pos.stop_missing is True              # law #3 visibility
    assert pos.stop_order_ref is None            # no stale ref on /status
    assert not a._stops                          # nothing rests at the venue
    assert len([e for e in a.log
                if e["action"] == "place_stock_order"]) == placed_before
    # loud on cycle 0, re-armed after — never silent, never per-cycle spam
    assert per_cycle[0] == 1
    assert sum(per_cycle[1:]) >= 1
    assert sum(per_cycle) < len(per_cycle)
    assert m.status_summary()["unverifiable"] == ["1"]
    assert m.status_summary()["stop_missing"] == ["1"]
    feed_pos = m.feed({}, "2026-08-30")["positions"][0]
    assert feed_pos["unverifiable"] is True and feed_pos["unprotected"] is True


def test_gate_n2_filled_stop_without_a_price_parks_never_sells(tmp_path):
    """Matrix cell filled-but-unpriced with conflated position rows: the
    order-scoped fill is proof the position closed, the missing price
    forbids booking it (repo law: no silent 0.0) — park UNRECONCILED, and
    never treat the account's external shares as the position."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._orders[ref]["status"] = "filled"          # filled, price unknown
    a._stops.pop(ref, None)
    a._positions["CRSP"] = 6                     # external shares
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" not in m.state.positions and "1" in m.state.unreconciled
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(2_500.0))           # nothing booked at a guess
    assert _executions(a, "CRSP") == []
    assert any("NO fill price" in msg for msg in alerts)


class _FalseCancelAdapter(DryAdapter):
    """The venue answers "not found / already cancelled" (False) while the
    stop in fact keeps resting — the realistic post-restart case: the
    session-scoped orderId no longer resolves, and `cancel_stock_order`
    returns False by contract. Indistinguishable from a gone order."""

    def cancel_stock_order(self, ref):
        rec = self._orders.get(ref)
        if rec is not None and rec["status"] == "filled":
            raise RuntimeError(f"cannot cancel {ref}: order already FILLED")
        self._rec("cancel_stock_order", ref=ref, found=False)
        return False


def test_gate_x2_ambiguous_cancel_stays_tracked_and_fill_alerts_red(tmp_path):
    """X2: N1's original naked short, end to end. The park's cancel comes
    back False (ambiguous), so the -5 stop may still rest. cde6fb7 wrote
    the ref into orphan_stop_refs and pass 3 POPPED it in the SAME
    reconcile (it ignored the return value and logged a "cancelled on
    retry" the venue never said) — tracking survived zero cycles, the stop
    later triggered into a 2-share account (venue net -3, a real naked
    short) and surfaced only as "fill for UNKNOWN order".

    Tracking must now be cleared ONLY by a definitively ACKed cancel, and a
    fill on a retired ref must route to the RED possible-short branch."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = _FalseCancelAdapter()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 2                     # manual sale of 3, in the dark
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" in m.state.unreconciled
    assert ref in m.state.orphan_stop_refs        # survives its own cycle
    assert not any("cancelled on retry" in e["msg"] for e in m.state.events)
    assert any("would NOT ACK the cancel" in msg for msg in alerts)
    # it survives further cycles too, and keeps being retried
    run_cycle(m, a, None, "2026-08-25", alert=lambda _: None)
    assert ref in m.state.orphan_stop_refs
    # the abandoned stop now triggers into a 2-share account
    a.trigger_stop(ref)
    alerts2: list[str] = []
    run_cycle(m, a, None, "2026-08-26", alert=alerts2.append)
    assert any("RETIRED stop" in msg and "possible short" in msg
               for msg in alerts2)
    assert not any("UNKNOWN order" in msg for msg in alerts2)
    assert f"orphan-{ref}" in m.state.unreconciled


def test_x2_companion_acked_cancel_still_clears_tracking(tmp_path):
    """Companion (NOT a gate — it passes at cde6fb7 by construction): the
    other side of X2. A cancel the venue actually ACKs must still drain the
    tracking, so tightening the clear condition does not wedge the guard on
    every orphan forever."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    rs = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                             client_order_id="blend-9-stp-44.0000")
    m.record_orphan_stop(rs["order_ref"], {"symbol": "CRSP", "qty": -5,
                                           "call_id": 9})
    run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
    assert rs["order_ref"] not in m.state.orphan_stop_refs
    assert any("cancelled on retry" in e["msg"] for e in m.state.events)


def test_gate_x4_park_alert_states_what_the_retire_actually_did(tmp_path):
    """X4: the park alert appended ", resting stop retired, nothing sold"
    unconditionally — contradicting the 🚨🚨 "could NOT be cancelled" alert
    emitted seconds earlier, and overclaiming in the DANGEROUS direction
    (protection removed when the -5 stop may still be armed)."""
    class _RaisingCancel(DryAdapter):
        def cancel_stock_order(self, ref):
            raise RuntimeError("cancel unavailable (simulated)")

    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = _RaisingCancel()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 2
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    (park,) = [msg for msg in alerts if "parked for manual booking" in msg]
    assert "stop retired" not in park             # never the false claim
    assert "could NOT be cancelled and may STILL rest" in park
    assert "holds 2 of the 5" in park and "UNPROTECTED" in park
    assert any("could NOT be cancelled" in msg for msg in alerts)
    # and the ambiguous-False sibling says its own truth, not "retired"
    m2 = mk(tmp_path / "b")
    _seed_initialized(m2, sleeve_cash=2_750.0)
    a2 = _FalseCancelAdapter()
    _blackout_stop(m2, a2)
    a2._positions["CRSP"] = 2
    alerts2: list[str] = []
    run_cycle(m2, a2, None, "2026-08-24", alert=alerts2.append)
    (park2,) = [msg for msg in alerts2 if "parked for manual booking" in msg]
    assert "stop retired" not in park2
    assert "would not ACK the cancel" in park2
    # ...and so does a clean, ACKed retire
    m3 = mk(tmp_path / "c")
    _seed_initialized(m3, sleeve_cash=2_750.0)
    a3 = DryAdapter()
    _blackout_stop(m3, a3)
    a3._positions["CRSP"] = 2
    alerts3: list[str] = []
    run_cycle(m3, a3, None, "2026-08-24", alert=alerts3.append)
    (park3,) = [msg for msg in alerts3 if "parked for manual booking" in msg]
    assert "its resting stop was CANCELLED at the venue" in park3


def test_gate_x5_same_symbol_shortfall_sacrifices_nobody(tmp_path):
    """x5: `held` is account-wide and `book_qty` mixes same-symbol peers, so
    a shortfall cannot be attributed to any ONE of them. cde6fb7 sacrificed
    whichever came FIRST in dict order — cancelling a healthy peer's
    working stop and parking its real shares UNRECONCILED while the
    position whose shares were actually gone got unparked as verified.

    Z1 UPDATE: "sacrifice nobody" stands (nobody parked, nobody stripped of
    cover, everybody flagged and loud) — but the ORIGINAL refs no longer
    rest, because leaving 12 shares of SELL stops against 9 held is the
    venue short Z1 closes. The old ref-identity assertion is replaced by
    strictly more: the pro-rata sizes, the cover<=held invariant, that every
    position still has REAL cover, that the superseded orders are CANCELLED
    (not abandoned), and that triggering everything cannot go short."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10_000.0)
    a = DryAdapter()
    r1 = _blackout_stop(m, a, call_id=1, qty=5, level=44.0)
    r2 = _blackout_stop(m, a, call_id=2, qty=4, level=43.0)
    r3 = _blackout_stop(m, a, call_id=3, qty=3, level=42.0)
    a._positions["CRSP"] = 9                     # call 3's 3 sold in the dark
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert sorted(m.state.positions) == ["1", "2", "3"]   # nobody sacrificed
    assert not m.state.unreconciled
    assert all(m.state.positions[k].history_gap for k in ("1", "2", "3"))
    # every position keeps REAL cover (nobody stripped), resized pro rata:
    # floor(9*5/12)=3 +1 (largest fraction .75) = 4, floor(9*4/12)=3,
    # floor(9*3/12)=2 -> 4+3+2 == 9 == held.
    assert sorted(-o["qty"] for o in a._stops.values()) == [2, 3, 4]
    assert sum(-o["qty"] for o in a._stops.values()) == 9   # cover == held
    assert [m.state.positions[k].stop_cover_qty for k in ("1", "2", "3")] \
        == [4, 3, 2]
    assert all(m.state.positions[k].stop_order_ref in a._stops
               for k in ("1", "2", "3"))
    assert all(not m.state.positions[k].stop_missing
               for k in ("1", "2", "3"))
    # the superseded orders were CANCELLED at the venue, never abandoned
    for old in (r1, r2, r3):
        assert old not in a._stops
        assert a._orders[old]["status"] == "cancelled"
    assert not m.state.orphan_stop_refs
    assert _executions(a, "CRSP") == []
    assert not any("parked for manual booking" in msg for msg in alerts)
    esc = [msg for msg in alerts if "UNRESOLVED after the blackout" in msg]
    assert len(esc) == 3
    assert all("cannot be attributed to any one of them" in msg for msg in esc)
    assert all("RESIZED protective stop" in msg for msg in esc)
    (resize,) = [msg for msg in alerts if "RESIZED 12 -> 9" in msg]
    assert "PRO RATA" in resize and "call 1: 5 -> 4" in resize
    # and the end state cannot short the account
    for ref in list(a._stops):
        a.trigger_stop(ref)
    after: list[str] = []
    run_cycle(m, a, None, "2026-08-25", alert=after.append)
    assert a._positions["CRSP"] == 0
    assert not any("position closed" in msg and "UNVERIFIABLE" not in msg
                   for msg in after)


def test_gate_x7_unretirable_stop_alerts_rearmed_never_silent(tmp_path):
    """x7: a raising cancel produced two differently-worded alerts in the
    SAME cycle and then "STILL uncancelled" every cycle forever. The
    escalation must be re-armed — loud on record, then periodic — and it
    must never fall silent (`orphan_stop_refs` never drains for a stop the
    venue will not ACK)."""
    class _RaisingCancel(DryAdapter):
        def cancel_stock_order(self, ref):
            raise RuntimeError("cancel unavailable (simulated)")

    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = _RaisingCancel()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 0
    first: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=first.append)
    # pass 3 must not duplicate the record-time alert in the same cycle;
    # the only two mentions are the retire alert and the park alert that
    # now AGREES with it (X4) — never two contradictory claims.
    assert sum(1 for msg in first if "STILL uncancelled" in msg) == 0
    assert sum(1 for msg in first
               if "could NOT be cancelled while parking" in msg) == 1
    assert sum(1 for msg in first if "could NOT be cancelled" in msg) == 2
    assert not any("stop retired" in msg for msg in first)
    per_cycle: list[int] = []
    for c in range(2 * blend_mod.ORPHAN_REALERT_CYCLES):
        alerts: list[str] = []
        run_cycle(m, a, None, "2026-08-%02d" % (25 + c), alert=alerts.append)
        per_cycle.append(sum(1 for msg in alerts
                             if "STILL uncancelled" in msg))
    assert ref in m.state.orphan_stop_refs        # never silently drained
    assert sum(per_cycle) >= 1                    # never silent
    assert sum(per_cycle) < len(per_cycle)        # and never every-cycle spam


def test_gate_x8_filled_unpriced_park_states_the_venue_quantity(tmp_path):
    """x8: the filled+unpriced park never said how many shares remain at
    the venue, unlike its held<booked sibling — inconsistent honesty on the
    same class of event."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._orders[ref]["status"] = "filled"          # filled, price unknown
    a._stops.pop(ref, None)
    a._positions["CRSP"] = 3                     # 3 shares STILL at the venue
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    (park,) = [msg for msg in alerts if "NO fill price" in msg]
    assert "3 CRSP share(s)" in park and "UNPROTECTED" in park
    assert _executions(a, "CRSP") == []


def test_gate_x13_unlocatable_stop_is_never_cancelled_by_a_stale_ref(tmp_path):
    """x13: with the cid lookup returning None the only ref left is the
    PERSISTED one, and IB orderIds are session-scoped — after the restart
    this guard exists for it can address a DIFFERENT order. It must be
    tracked (a fill on it still alerts RED) and never cancelled blind."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, stop_ref="stale-session-ref")   # venue never saw the cid
    m.state.last_reconcile_ts = time.time() - 3 * 86_400
    a = DryAdapter()
    a._positions["CRSP"] = 2
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert "1" in m.state.unreconciled
    assert "stale-session-ref" in m.state.orphan_stop_refs
    assert not [e for e in a.log if e["action"] == "cancel_stock_order"]
    assert any("may address a DIFFERENT order" in msg for msg in alerts)
    # pass 3 keeps watching it but never blind-cancels it either
    run_cycle(m, a, None, "2026-08-25", alert=lambda _: None)
    assert not [e for e in a.log if e["action"] == "cancel_stock_order"]
    assert "stale-session-ref" in m.state.orphan_stop_refs


# R2 (re-review residual): /kill is TWO-STAGE — the handler journals a
# persisted flatten request and halts; the LOOP thread (owner of the
# ib_async event loop) executes the flatten with reconcile-first semantics.
# FakeIB cannot reproduce the cross-thread asyncio failure, so these gates
# pin the NEW mechanism: journal persisted, halt immediate, loop executes,
# honest summaries, restart-resume, no API-thread adapter touch.


def test_gate_r2_flatten_request_persists_and_executes_after_restart(
        tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    assert "1" in m.state.positions
    m.request_flatten("2026-08-20")
    assert m.state.halted == "KILL"          # halt is immediate
    assert "1" in m.state.positions          # nothing sold by the request
    # ...service restarts before the loop ran the flatten...
    m2 = Blend3070Manager(m.cfg, m.state_path)
    assert m2.state.flatten_request is not None      # journal survived
    assert m2.state.halted == "KILL"
    alerts: list[str] = []
    run_cycle(m2, a, None, "2026-08-21", alert=alerts.append)
    assert m2.state.positions == {}          # loop executed the flatten
    assert m2.state.flatten_request is None
    assert m2.state.halted == "KILL"         # halted until /resume
    assert len(_executions(a, "CRSP")) == 1
    assert any("flatten complete" in msg for msg in alerts)


def test_gate_r2_flatten_summary_honest_about_parked_positions(tmp_path):
    """The completion alert must state what actually closed vs parked —
    never 'book closed & halted' while an UNVERIFIABLE position is held."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10_000.0)
    a = _NoVenuePositionsAdapter()           # R1 flag cannot be verified
    run_cycle(m, a, payload(entries=[entry(),
                                     entry(call_id=2, symbol="NTLA")],
                            stops=[stop_row(),
                                   stop_row(call_id=2, symbol="NTLA")]),
              "2026-08-20", alert=lambda _: None)
    m.state.positions["2"].history_gap = True        # blackout-parked
    m.request_flatten("2026-08-21")
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-21", alert=alerts.append)
    assert "1" not in m.state.positions              # CRSP closed
    assert "2" in m.state.positions                  # NTLA parked, NOT sold
    assert m.state.positions["2"].history_gap is True
    assert _executions(a, "NTLA") == []
    (summary,) = [msg for msg in alerts if "flatten finished" in msg]
    assert "WITH EXCEPTIONS" in summary
    assert "1 closed" in summary and "CRSP" in summary
    assert "NOT closed" in summary and "NTLA" in summary
    assert not any("book closed" in msg for msg in alerts)  # never overclaim


def test_gate_r2_flatten_raising_cancel_parks_never_sells(tmp_path):
    """K-d survives the loop-thread flatten: a RAISING stop cancel (stop
    likely FILLED) parks the position — never a MKT sell on top of it."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    a = _RaisingCancelAdapter()
    m.request_flatten("2026-08-21")
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-21", alert=alerts.append)
    assert "1" in m.state.positions                  # parked, not sold
    assert "old-stop" in m.state.orphan_stop_refs    # settled by reconcile
    assert _executions(a, "CRSP") == []
    assert m.state.flatten_request is None
    (summary,) = [msg for msg in alerts if "flatten finished" in msg]
    assert "0 closed" in summary or "none" in summary
    assert "NOT closed" in summary and "CRSP" in summary


def test_gate_r2_resume_clears_a_queued_flatten(tmp_path):
    """/resume before the loop ran the flatten must clear the journal — a
    stale kill request must never flatten a RESUMED book."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m)
    m.request_flatten("2026-08-21")
    m.resume()
    assert m.state.flatten_request is None
    a = DryAdapter()
    run_cycle(m, a, payload(stops=[stop_row()]), "2026-08-21",
              alert=lambda _: None)
    assert "1" in m.state.positions                  # nothing flattened
    assert _executions(a, "CRSP") == []


class _ThreadRecordingAdapter(DryAdapter):
    """Records the thread of every adapter call — the R2 law: ONLY the loop
    thread (owner of the ib_async event loop) may touch the venue."""

    def __init__(self):
        super().__init__()
        import threading
        self.call_threads: set[int] = set()
        self._ident = threading.get_ident

    def _note(self):
        self.call_threads.add(self._ident())

    def place_stock_order(self, *a, **kw):
        self._note()
        return super().place_stock_order(*a, **kw)

    def cancel_stock_order(self, *a, **kw):
        self._note()
        return super().cancel_stock_order(*a, **kw)

    def poll_stock_fills(self):
        self._note()
        return super().poll_stock_fills()

    def find_stock_order(self, *a, **kw):
        self._note()
        return super().find_stock_order(*a, **kw)

    def stock_position(self, *a, **kw):
        self._note()
        return super().stock_position(*a, **kw)

    def spot(self, *a, **kw):
        self._note()
        return super().spot(*a, **kw)


def test_gate_r2_kill_never_touches_the_adapter_from_the_api_thread(
        tmp_path, monkeypatch):
    """The old /kill pumped the adapter from a FastAPI worker thread — on
    the real IBAdapter every wait timed out (ib_async resolves its loop
    per thread) and the flatten deterministically failed. Now every
    adapter call must come from ONE thread: the service loop."""
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    monkeypatch.setattr(service, "DryAdapter", _ThreadRecordingAdapter)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B, A = service.BLEND, service.ADAPTER
            assert _wait_until(lambda: A.call_threads)   # loop cycle 1 ran
            loop_threads = set(A.call_threads)           # THE loop thread
            assert len(loop_threads) == 1
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B, stop_ref=None)
            pos = B.state.positions["1"]
            rs = A.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     tif="GTC",
                                     client_order_id="blend-1-stp-44.0000")
            pos.stop_order_ref = rs["order_ref"]
            B.save()
            A.call_threads.clear()           # only post-kill calls count
            c.get("/kill", params={"token": "sekrit"})
            assert _wait_until(
                lambda: B.state.positions == {}
                and B.state.flatten_request is None)
            # the flatten DID run (cancel + MKT sell) — and every adapter
            # call came from THE loop thread, none from the API thread
            assert A.call_threads == loop_threads
    finally:
        service.BLEND = None
        service.MGR = None


def test_gate_r2_kill_alerts_are_honest_two_stage(tmp_path, monkeypatch):
    """The immediate /kill reply says QUEUED (never 'book closed'); the
    loop's completion alert states what actually closed."""
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    try:
        with TestClient(service_app) as c:
            for _ in range(200):
                if service.BLEND is not None and service.ADAPTER is not None:
                    break
                _time.sleep(0.05)
            B = service.BLEND
            _seed_initialized(B, sleeve_cash=2_750.0)
            _held_position(B, stop_ref=None)
            sent: list[str] = []
            monkeypatch.setattr(service, "send", sent.append)
            r = c.get("/kill", params={"token": "sekrit"})
            assert r.json()["blend"] == "flatten_queued"
            (kill_msg,) = [msg for msg in sent if "KILLED" in msg]
            assert "flatten QUEUED" in kill_msg
            assert "closed & halted" not in kill_msg     # the old overclaim
            assert _wait_until(lambda: B.state.flatten_request is None)
            assert any("flatten complete" in msg and "1 position(s) closed"
                       in msg for msg in sent)
    finally:
        service.BLEND = None
        service.MGR = None


# --- re-review minors (r3-r7): alert semantics, ledger cosmetics --------------
# Scenarios derived from the re-review probes A2/A3/A4/A5 and finding r7.


def test_gate_r3_new_quote_outage_after_recovery_realerts(tmp_path):
    # Probe A2: the outage alert was deduped against the LAST event only,
    # and the skip message is identical across outages — a genuinely new
    # outage after a quiet recovery never re-alerted.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=30, spy_qty=70)
    bad = {"BIL": 100.0}
    out1 = m.step("2026-08-20", payload(), bad)
    assert len([o for o in out1 if o["action"] == "ALERT"]) == 1
    out2 = m.step("2026-08-20", payload(), bad)      # same outage: quiet
    assert not [o for o in out2 if o["action"] == "ALERT"]
    m.step("2026-08-21", payload(), PRICES)          # QUIET recovery
    out3 = m.step("2026-08-24", payload(), bad)      # NEW outage days later
    assert len([o for o in out3 if o["action"] == "ALERT"]) == 1


def test_gate_r4_interleaved_pending_event_does_not_spam_quote_alert(
        tmp_path):
    # Probe A3: pending-book INFO and missing-quote WARN alternate in the
    # event log, defeating last-event dedup — the WARN alerted EVERY cycle.
    m = mk(tmp_path)
    _seed_initialized(m)
    m.state.pending_book_orders["blend-sweep-2026-08-20-1"] = {
        "kind": "sweep", "symbol": "BIL", "qty": 10, "date": "2026-08-20",
        "ref_price": 100.0}
    n = 0
    for _ in range(4):
        n += len([o for o in m.step("2026-08-20", payload(), {})
                  if o["action"] == "ALERT"])
    assert n == 1                                    # once per outage


def test_gate_r5_sweep_slippage_never_leaves_negative_sleeve_cash(tmp_path):
    # Probe A4: reserved sweep cash priced at journal ref_price, adopted at
    # the venue fill 0.9 above it -> sleeve_cash -27.
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=3_000.0)
    m.on_sweep(30, 100.9)
    assert m.state.sleeve_cash == 0.0                # clamped, not negative
    assert m.state.bil_qty == 30
    assert any("slippage absorbed" in e["msg"] for e in m.state.events)


def test_gate_r6_stuck_book_order_escalates_to_warn_after_age(tmp_path):
    # Probe A5 follow-up: a venue-stuck 'working' book order froze
    # sweep/core-buy/rebalance with only a deduped INFO event.
    m = mk(tmp_path)
    _seed_initialized(m)
    m.record_pending_book_order("sweep", "BIL", 10, "2026-08-18",
                                ref_price=100.0)
    out = m.step("2026-08-18", payload(), PRICES)
    assert not [o for o in out if o["action"] == "ALERT"]    # fresh: quiet
    out = m.step("2026-08-20", payload(), PRICES)            # 2 days old
    (al,) = [o for o in out if o["action"] == "ALERT"]
    assert "still working" in al["msg"]
    out = m.step("2026-08-21", payload(), PRICES)            # alerted ONCE
    assert not [o for o in out if o["action"] == "ALERT"]


def test_gate_r7_budget_cap_entries_wait_for_core_quotes(tmp_path):
    # r7: a missing SPY quote zeroes gross_exposure -> the BLEND_BUDGET
    # entry gate computed low while sleeve entries proceeded.
    m = mk(tmp_path, blend_budget=100_000.0)
    _seed_initialized(m)
    no_spy = {"BIL": 100.0, "CRSP": 50.0}
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]), no_spy)
    assert not [o for o in out if o["action"] == "ENTER"]
    assert any("budget gate" in e["msg"] for e in m.state.events)
    # without a cap the entry still proceeds (sleeve-only decision)
    m2 = Blend3070Manager(Cfg(), str(tmp_path / "b2.json"))
    _seed_initialized(m2)
    out2 = m2.step("2026-08-20",
                   payload(entries=[entry()], stops=[stop_row()]), no_spy)
    assert [o for o in out2 if o["action"] == "ENTER"]


# m3 (minor): cancel-ok-then-place-raise must not leave the position
# believed protected by a CANCELLED stop.

class _CancelOkPlaceFailAdapter(DryAdapter):
    """Stop cancel succeeds; the exit MKT sell then raises (venue hiccup)."""

    def place_stock_order(self, symbol, qty, order_type, **kw):
        if order_type == "MKT" and qty < 0:
            raise RuntimeError("venue error after cancel (simulated)")
        return super().place_stock_order(symbol, qty, order_type, **kw)


def test_gate_adapt_m3min_cancel_ok_place_fail_marks_stop_missing(
        tmp_path, monkeypatch):
    monkeypatch.setattr(blend_mod, "STOP_RETRY_SLEEP_S", 0)
    m = mk(tmp_path)
    _seed_initialized(m)
    a = _CancelOkPlaceFailAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    alerts: list[str] = []
    run_cycle(m, a, payload(exits=[{"symbol": "CRSP", "call_id": 1,
                                    "reason": "trail", "trail_level": 47.0}]),
              "2026-08-21", alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.stop_missing is True and pos.stop_order_ref is None
    assert any("UNPROTECTED" in msg for msg in alerts)
    # next cycle: reconcile re-places the protective stop (covered again
    # while the exit retries via its deterministic cid)
    run_cycle(m, a, None, "2026-08-22", alert=lambda _: None)
    pos = m.state.positions["1"]
    assert pos.stop_missing is False and pos.stop_order_ref in a._stops


# m4 (minor): an IB-initiated GTC cancel (corporate action) must be
# detected — never a naked position believed protected forever.

def test_gate_adapt_m4min_venue_cancelled_stop_detected_and_replaced(
        tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)
    a = DryAdapter()
    run_cycle(m, a, payload(entries=[entry()], stops=[stop_row()]),
              "2026-08-20", alert=lambda _: None)
    ref = m.state.positions["1"].stop_order_ref
    a.cancel_stock_order(ref)        # IB-initiated GTC cancel, no shares
    assert ref not in a._stops       # naked at the venue, book unaware
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-21", alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.stop_missing is False
    assert pos.stop_order_ref != ref and pos.stop_order_ref in a._stops
    assert any("CANCELLED at the venue" in msg for msg in alerts)


# M1 support: pending sweep cash is reserved — entries can never spend it.

def test_gate_adapt_m1_pending_sweep_cash_reserved_from_entries(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m)                     # sleeve_cash 3,000
    # a working sweep BUY of 29 BIL @ 100 is pending adoption: $2,900 of
    # the settled cash is already spoken for
    m.record_pending_book_order("sweep", "BIL", 29, "2026-08-19",
                                ref_price=100.0)
    assert m.reserved_sleeve_cash() == pytest.approx(2_900.0)
    out = m.step("2026-08-20",
                 payload(entries=[entry()], stops=[stop_row()]),
                 PRICES)
    (ent,) = [o for o in out if o["action"] == "ENTER"]
    # only $100 is spendable -> 2 shares @ 50 (risk sizing alone wants 5)
    assert ent["qty"] == 2
    assert not [o for o in out if o["action"] == "SWEEP"]   # kind suppressed


# --- mode-transition guard + N3 (resume race / atomic save) -------------------

def test_gate_mode_guard_archives_foreign_mode_book(tmp_path):
    """A book built under DRY (placeholder fills) must NOT survive into a
    real mode: the venue never saw those orders, and reconciling them would
    mark fiction at real prices and trade the difference."""
    m = mk(tmp_path)                       # dry:paper
    _seed_initialized(m, spy_qty=700, bil_qty=300)
    _held_position(m)
    m.save()
    m2 = mk(tmp_path, dry_run=False,       # real:paper — same state file
            tws_userid="u", tws_password="p")
    assert m2.archived_state               # loud: startup alerts on this
    assert m2.state.initialized is False
    assert m2.state.positions == {}
    assert m2.state.spy_qty == 0 and m2.state.bil_qty == 0
    assert m2.state.mode == "real:paper"
    archives = list(tmp_path.glob("blend.json.archived-*"))
    assert len(archives) == 1              # old book preserved, not deleted
    old = json.loads(archives[0].read_text())
    assert old["spy_qty"] == 700


def test_gate_mode_guard_archives_legacy_untagged_state(tmp_path):
    """A pre-guard state file (no mode key) is of UNKNOWN mode — it must be
    archived even when the current mode happens to match what wrote it."""
    path = tmp_path / "blend.json"
    path.write_text(json.dumps({"initialized": True, "spy_qty": 700}))
    m = mk(tmp_path)                       # dry:paper, same as the writer was
    assert m.archived_state
    assert m.state.spy_qty == 0
    assert list(tmp_path.glob("blend.json.archived-unknown-*"))


def test_gate_mode_guard_same_mode_restart_keeps_book(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, spy_qty=70)
    _held_position(m)
    m.save()
    m2 = mk(tmp_path)                      # same mode: no archive, book kept
    assert m2.archived_state is None
    assert m2.state.initialized and m2.state.spy_qty == 70
    assert "1" in m2.state.positions


def test_gate_n3_flatten_reasserts_halt_after_raced_resume(tmp_path):
    """If a /resume raced in between the kill request and the loop's flatten
    (halted cleared but the request already picked up), the book must come
    out of the flatten HALTED — never un-halted and entering same-cycle."""
    from app.blend import execute_flatten
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    _held_position(m, stop_ref=None)
    m.request_flatten("2026-08-21")
    m.state.halted = None                  # the race the lock now prevents,
                                           # kept as defense-in-depth
    execute_flatten(m, DryAdapter(), alert=lambda s: None)
    assert m.state.flatten_request is None
    assert m.state.positions == {}
    assert m.state.halted == "KILL"


def test_gate_n3_save_atomic_survives_crash_mid_write(tmp_path, monkeypatch):
    """A crash mid-save must never leave a truncated file that _load
    silently resolves to a fresh empty book (which would re-plan the whole
    book from scratch against live positions)."""
    import app.blend as blend_mod
    m = mk(tmp_path)
    _seed_initialized(m, spy_qty=70)
    m.save()

    def bad_dump(obj, fh, **kw):
        fh.write('{"partial')
        raise IOError("disk full mid-write")

    monkeypatch.setattr(blend_mod.json, "dump", bad_dump)
    m.state.spy_qty = 999
    with pytest.raises(IOError):
        m.save()
    monkeypatch.undo()
    m2 = mk(tmp_path)                      # reload: the LAST GOOD book
    assert m2.state.initialized is True
    assert m2.state.spy_qty == 70          # not 999, and not a fresh book


def test_gate_x11_concurrent_saves_never_corrupt_the_published_book(tmp_path):
    """x11: save()'s docstring promised safety against "two threads racing"
    while every writer shared ONE "<state>.tmp" path — concurrent savers
    clobbered each other's partial file and published truncated JSON (which
    _load's bare except turns into total book amnesia). It also flaked the
    suite with FileNotFoundError on the shared .tmp.

    Production writers all hold BLEND_LOCK; this gate hammers save()
    UNLOCKED so the promise holds on its own."""
    import threading

    m = mk(tmp_path)
    _seed_initialized(m, spy_qty=70)
    # a realistically sized book: the corruption window scales with payload
    m.state.trades = [{"symbol": "CRSP", "side": "SELL", "qty": 5,
                       "fill_price": 44.0, "date": "2026-08-20",
                       "kind": "stop_filled", "r_multiple": -1.0,
                       "pnl": -30.0} for _ in range(200)]
    m.state.events = [{"ts": 1, "level": "INFO", "msg": f"event {i} " + "x" * 80}
                      for i in range(300)]
    m.state.equity_curve = [["2026-08-%02d" % (i % 28 + 1), 10_000.0 + i]
                            for i in range(1500)]
    m.save()
    errors: list[BaseException] = []
    corrupt: list[str] = []
    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            try:
                m.save()
            except BaseException as exc:      # noqa: BLE001
                errors.append(exc)
                return

    def reader():
        while not stop.is_set():
            try:
                json.load(open(m.state_path))
            except FileNotFoundError:
                corrupt.append("missing")
            except ValueError:
                corrupt.append("truncated")

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    threads.append(threading.Thread(target=reader))
    for t in threads:
        t.start()
    time.sleep(1.0)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    assert errors == []                       # no writer ever raised
    assert corrupt == []                      # no truncated published state
    assert mk(tmp_path).state.spy_qty == 70   # and the book reloads intact
    # no scratch files accumulate next to the state file
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []


def test_gate_n3_resume_blocks_behind_blend_lock(tmp_path, monkeypatch):
    """/resume must serialize behind the loop's cycle (BLEND_LOCK): a resume
    racing an in-flight flatten un-halts a book that is being sold."""
    import threading

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
            assert _wait_until(lambda: service.BLEND is not None)
            service.BLEND.state.halted = "KILL"
            done = threading.Event()
            with service.BLEND_LOCK:       # a cycle is "in flight"
                t = threading.Thread(
                    target=lambda: (c.get("/resume",
                                          params={"token": "sekrit"}),
                                    done.set()))
                t.start()
                time.sleep(0.4)
                assert not done.is_set()   # resume waits for the cycle
                assert service.BLEND.state.halted == "KILL"
            assert done.wait(5.0)          # lock released -> resume lands
            t.join(5.0)
            assert service.BLEND.state.halted is None
    finally:
        service.BLEND = None
        service.MGR = None


def test_gate_mode_guard_creds_absent_is_dry_even_without_dry_run(tmp_path):
    """F1: _build runs the DryAdapter whenever TWS creds are absent, DRY_RUN
    or not — the mode tag must mirror that, or a creds-missing boot with
    DRY_RUN=false would tag placeholder fills as a real book (and the guard
    would then PRESERVE the fiction when creds arrive)."""
    m = mk(tmp_path, dry_run=False, tws_userid="", tws_password="")
    assert m.state.mode == "dry:paper"     # creds absent -> dry, flag or not
    _seed_initialized(m, spy_qty=700)
    m.save()
    # Creds arrive (a real PAPER boot): the placeholder book must be archived.
    m2 = mk(tmp_path, dry_run=False, tws_userid="u", tws_password="p")
    assert m2.state.mode == "real:paper"
    assert m2.archived_state
    assert m2.state.spy_qty == 0


def test_gate_mode_guard_creds_pulled_mid_paper_archives_real_book(tmp_path):
    """F1 reverse hole: creds pulled mid-PAPER (DRY_RUN still false) boots
    the DryAdapter — the REAL book must be archived, never traded by the
    placeholder venue."""
    m = mk(tmp_path, dry_run=False, tws_userid="u", tws_password="p")
    assert m.state.mode == "real:paper"
    _seed_initialized(m, spy_qty=12)
    m.save()
    m2 = mk(tmp_path, dry_run=False, tws_userid="", tws_password="")
    assert m2.state.mode == "dry:paper"
    assert m2.archived_state               # real book preserved in archive
    assert m2.state.spy_qty == 0


def test_gate_g3_unreadable_blend_state_is_preserved_and_loud(tmp_path):
    """G3 (the blend half of the ladder's x12): an unreadable book must not
    degrade silently to a fresh one — open positions and `halted` would be
    forgotten and the next save would erase the evidence."""
    m = mk(tmp_path)
    _seed_initialized(m, spy_qty=70)
    _held_position(m)
    m.state.halted = "KILL"
    m.save()
    open(m.state_path, "w").write('{"positions": {"1": {trunc')
    m2 = mk(tmp_path)
    assert m2.archived_state and "unreadable" in m2.archived_state
    assert m2.state.positions == {}          # fresh book, honestly announced
    assert list(tmp_path.glob("blend.json.corrupt-*"))
    m2.save()                                # evidence survives the next save
    assert list(tmp_path.glob("blend.json.corrupt-*"))


def test_gate_y1_ratchet_never_rests_a_stop_on_an_unverifiable_position(tmp_path):
    """Y1 (re-review): passes 3b and 4 refuse to rest a stop on a flagged
    position, but step()'s daily trail RATCHET placed one through a third
    door — and a ratchet rests a NEW -qty SELL order, so it is the same
    short path. Reviewer's X-B: venue 12, book 5 → the ratchet's 5-share
    SELL sells the operator's external shares and books a phantom exit."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    ref = _blackout_stop(m, a)
    a._positions["CRSP"] = 12                    # 5 booked + 7 external
    run_cycle(m, a, None, "2026-08-24", alert=lambda _: None)
    assert m.state.positions["1"].history_gap is True
    # A ratcheting trail arrives while the position is still unverifiable.
    out = m.step("2026-08-25", payload(stops=[stop_row(trail=47.0)]),
                 PRICES)
    assert not [o for o in out if o["action"] == "ADJUST_STOP"]
    assert m.state.positions["1"].stop_level == 44.0    # unchanged
    assert list(a._stops) == [ref]               # no SECOND resting stop
    assert a._positions["CRSP"] == 12            # nothing sold


def test_gate_y1_ratchet_cannot_add_sell_orders_to_a_shortfall(tmp_path):
    """Reviewer's X-K(d), the sharp end. Two same-symbol positions book 9
    shares; 3 were sold by hand during the blackout so the account holds 6.
    The shortfall is not attributable to either position (x5), so both stay
    flagged with their stops resting. A ratchet then used to rest NEW stops
    for both — adding SELL orders on top of a book the venue can no longer
    cover, which ends in a venue short."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    _blackout_stop(m, a, call_id=1, qty=5)
    _blackout_stop(m, a, call_id=2, qty=4)
    a._positions["CRSP"] = 6                     # 3 sold away by hand
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    assert all(p.history_gap for p in m.state.positions.values())
    before = {r: o["qty"] for r, o in a._stops.items()}
    # Day 2 runs the FULL cycle so a ratchet intent would really be placed —
    # inspecting intents alone would pass vacuously.
    run_cycle(m, a, payload(stops=[stop_row(call_id=1, trail=47.0),
                                   stop_row(call_id=2, trail=47.0)]),
              "2026-08-25", alert=alerts.append)
    after = {r: o["qty"] for r, o in a._stops.items()}
    assert after == before                       # no NEW sell orders rested
    assert all(p.stop_level == 44.0 for p in m.state.positions.values())
    assert not any("position closed" in s for s in alerts)


def test_gate_z1_peer_shortfall_never_leaves_cover_above_venue_held(tmp_path):
    """Z1, the reviewer's repro and the LIVE-BLOCKING invariant: for each
    symbol, total blend-placed RESTING SELL cover must never exceed the
    venue-verified `held`, and the executor must never CHOOSE to leave
    cover > held.

    Two same-symbol positions book 9 shares (5+4); 3 were sold by hand
    inside the blackout so the account holds 6. The shortfall is
    attributable to neither (x5), so nobody is parked or sacrificed — but
    leaving 5+4 = 9 shares of SELL stops resting against 6 held is a REAL
    naked short the moment both trigger (venue 6 -> -3), and it used to be
    reported as two cheerful green 'position closed' alerts."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    old1 = _blackout_stop(m, a, call_id=1, qty=5, level=44.0)
    old2 = _blackout_stop(m, a, call_id=2, qty=4, level=43.0)
    a._positions["CRSP"] = 6                     # 3 sold away by hand
    alerts: list[str] = []
    # the FULL cycle, not intents: an intents-only assertion passes vacuously
    run_cycle(m, a, None, "2026-08-24", alert=alerts.append)
    # nobody sacrificed: both positions alive, flagged, neither parked
    assert sorted(m.state.positions) == ["1", "2"]
    assert not m.state.unreconciled
    assert all(p.history_gap for p in m.state.positions.values())
    assert _executions(a, "CRSP") == []           # nothing was sold to fix it
    # what actually RESTS at the venue, observed venue-side (so this gate
    # fails on the HARM at the parent commit, not on a missing field)
    resting = sorted(-o["qty"] for o in a._stops.values())
    # now trigger EVERY resting stop: the account must never go short
    for ref in list(a._stops):
        a.trigger_stop(ref)
    filled: list[str] = []
    run_cycle(m, a, None, "2026-08-25", alert=filled.append)
    assert a._positions["CRSP"] >= 0              # THE invariant, end to end
    assert a._positions["CRSP"] == 0
    # and no fill is reported as a plain green close
    assert not any("position closed" in msg and "UNVERIFIABLE" not in msg
                   for msg in filled)
    assert not any(msg.startswith("🧬 blend STOP FILLED") for msg in filled)
    # cover was resized PRO RATA: floor(6*5/9)=3, floor(6*4/9)=2 +1 (largest
    # fractional part .667) = 3 -> 3+3 == 6 == held, and no attribution.
    assert resting == [3, 3] and sum(resting) == 6
    assert old1 not in a._stops and old2 not in a._stops
    assert a._orders[old1]["status"] == "cancelled"
    assert a._orders[old2]["status"] == "cancelled"
    assert not m.state.orphan_stop_refs           # cancels ACKed, not orphaned
    (resize,) = [msg for msg in alerts if "RESIZED" in msg and "PRO RATA" in msg]
    assert "9 -> 6" in resize and "call 1: 5 -> 3" in resize
    assert "3 share(s) of protection were REMOVED" in resize
    # the remainder is NOT booked as a phantom exit off the same order
    assert [m.state.positions[k].qty for k in ("1", "2")] == [2, 1]
    assert [m.state.positions[k].stop_cover_qty for k in ("1", "2")] == [0, 0]
    assert all(p.history_gap for p in m.state.positions.values())


def test_gate_z1_resized_cover_is_restored_in_full_when_shares_return(tmp_path):
    """Z1's other end: a resized stop covers FEWER shares than the position,
    so unparking it as 'still protected' would leave the book silently
    under-covered — and pass 4 stacking a full stop on top of the resized
    one would put cover back ABOVE held. The resized stop is retired first
    and full cover re-placed, with cover <= held at every step."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=2_750.0)
    a = DryAdapter()
    _blackout_stop(m, a, call_id=1, qty=5, level=44.0)
    _blackout_stop(m, a, call_id=2, qty=4, level=43.0)
    a._positions["CRSP"] = 6
    run_cycle(m, a, None, "2026-08-24", alert=lambda _msg: None)
    assert sum(-o["qty"] for o in a._stops.values()) <= a._positions["CRSP"]
    # the operator restores the missing shares (the in-band resolution)
    a._positions["CRSP"] = 9
    m.state.last_reconcile_ts = time.time()
    alerts: list[str] = []
    run_cycle(m, a, None, "2026-08-25", alert=alerts.append)
    assert not any(p.history_gap for p in m.state.positions.values())
    assert not any(p.stop_missing for p in m.state.positions.values())
    assert [m.state.positions[k].stop_cover_qty for k in ("1", "2")] == [0, 0]
    # full cover, exactly once each, and never more than the account holds
    assert sorted(-o["qty"] for o in a._stops.values()) == [4, 5]
    assert sum(-o["qty"] for o in a._stops.values()) <= a._positions["CRSP"]
    assert not m.has_naked_position()             # entries unblocked again
    assert any("RESIZED stop was retired and FULL cover is re-placing" in msg
               for msg in alerts)

