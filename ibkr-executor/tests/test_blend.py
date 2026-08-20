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
