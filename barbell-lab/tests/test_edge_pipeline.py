"""EDGE-MONITOR production-layer gates: schema/tripwires, adapter parsing,
baseline registration on the frozen S5 fixture, state machine (pinned rules),
insufficiency contract, blueprint-sync."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from barbell.edge import adapter_coinbase, baseline, db as edb, layers, run, statemachine

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(_ROOT, "research", "fixtures", "s5_backtest_daily.json")


def _con(tmp_path):
    con = sqlite3.connect(tmp_path / "e.db")
    con.executescript("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY "
                      "KEY, ts_utc TEXT, kind TEXT, message TEXT, details TEXT)")
    edb.ensure_schema(con)
    return con


def _status(n_days=90, n_fills=15, eq0=10_000.0, drift=0.001):
    """Synthetic executor /status payload."""
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
    marks = [{"d": (t0 + timedelta(days=i)).date().isoformat(),
              "equity": round(eq0 * (1 + drift) ** i, 2)} for i in range(n_days)]
    fills = [{"ts": int((t0 + timedelta(days=i * 3)).timestamp()), "leg": "trend",
              "role": "entry", "cloid": f"c{i}", "side": "BUY", "px": 60_000.0,
              "ref_px": 59_990.0, "slip_bps": 1.7} for i in range(n_fills)]
    return {"ready": True, "equity": marks[-1]["equity"], "marks": marks,
            "fills": fills}


# ------------------------------------------------------------ db tripwire --
def test_gate_nav_append_only_revision_flag(tmp_path):
    con = _con(tmp_path)
    assert edb.record_nav(con, "X", "2026-08-01", 100.0, "t") == "inserted"
    assert edb.record_nav(con, "X", "2026-08-01", 100.0, "t") == "unchanged"
    assert edb.record_nav(con, "X", "2026-08-01", 101.0, "t") == "REVISION"
    # stored row NOT overwritten
    assert con.execute("SELECT nav FROM edge_nav_daily WHERE date='2026-08-01'"
                       ).fetchone()[0] == 100.0
    assert edb.unresolved_revisions(con, "X") == 1


def test_gate_nav_ret_chain(tmp_path):
    con = _con(tmp_path)
    edb.record_nav(con, "X", "2026-08-01", 100.0, "t")
    edb.record_nav(con, "X", "2026-08-02", 102.0, "t")
    ret = con.execute("SELECT ret FROM edge_nav_daily WHERE date='2026-08-02'"
                      ).fetchone()[0]
    assert ret == pytest.approx(0.02)


# --------------------------------------------------------------- adapter --
def test_gate_adapter_sync_and_idempotence(tmp_path):
    con = _con(tmp_path)
    st = _status()
    rep = adapter_coinbase.sync(con, status=st)
    assert rep["nav"] >= 90 and rep["trades"] == 15 and rep["revisions"] == 0
    rep2 = adapter_coinbase.sync(con, status=st)
    assert rep2["nav"] <= 1 and rep2["trades"] == 0 and rep2["revisions"] == 0
    # vendor rewrites an old mark -> revision, not overwrite
    st["marks"][0]["equity"] += 50.0
    rep3 = adapter_coinbase.sync(con, status=st)
    assert rep3["revisions"] == 1


def test_gate_adapter_blind_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("EXEC_TOKEN", raising=False)
    with pytest.raises(adapter_coinbase.FeedBlind):
        adapter_coinbase.fetch_status()


# -------------------------------------------------------------- baseline --
def test_gate_baseline_registration_from_frozen_fixture(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO edge_strategies (strategy_id, venue, cadence) "
                "VALUES ('S5-live','coinbase','per_trade')")
    fx = json.load(open(FIXTURE))
    bid = baseline.register(con, "S5-live", fx)
    b = baseline.load(con, "S5-live")
    assert b["baseline_id"] == bid
    assert b["n_backtest_days"] == len(fx["returns"])
    assert 0 < b["sr_annual"] < 3.5          # sane, not a bug artifact
    assert b["trials_basis"].startswith("UNKNOWN")   # declared penalty, honest
    assert b["mintrl_days"] is None or b["mintrl_days"] > 100
    assert b["cusum"]["h"] > 0 and not b["cusum"]["censoring_binds"]
    # budget: <1 false RED per strategy per 3y  =>  E[REDs/5y] < 1.67; the
    # measured S5 rate (~0.3/5y, fat-tailed crypto blend) must stay inside
    # with margin. (Gaussian toy was 0.07 — the whole point of measuring on
    # the strategy's own distribution.)
    assert b["policy_mc"]["false_red_per_5y"] < 0.5
    assert "terminal-RED" in b["policy_mc"]["note"]
    # idempotent
    assert baseline.register(con, "S5-live", fx) == bid


# ------------------------------------------------------- layers + honesty --
def test_gate_insufficiency_is_first_class(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO edge_strategies (strategy_id, venue, cadence) "
                "VALUES ('S5-live','coinbase','per_trade')")
    fx = json.load(open(FIXTURE))
    baseline.register(con, "S5-live", fx)
    stale = _status(n_days=10, n_fills=3)
    stale.pop("equity")          # marks only: feed genuinely stale
    adapter_coinbase.sync(con, status=stale)
    checks = {c["metric"]: c for c in layers.run_daily(
        con, "S5-live", today="2026-08-14")}
    assert checks["return_cusum"]["status"] == "insufficient"
    assert checks["slip_cusum"]["status"] == "insufficient"
    assert checks["dd_percentile"]["status"] in ("ok", "breach")   # 5d met
    assert checks["behavior_drift"]["status"] == "insufficient"
    # freshness: nav ends ~2026-05-10 vs today 2026-08-14 -> breach (blind-ish)
    assert checks["freshness"]["status"] == "breach"


def test_gate_layers_on_healthy_feed(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO edge_strategies (strategy_id, venue, cadence) "
                "VALUES ('S5-live','coinbase','per_trade')")
    fx = json.load(open(FIXTURE))
    baseline.register(con, "S5-live", fx)
    st = _status(n_days=90, n_fills=15)
    adapter_coinbase.sync(con, status=st)
    today = st["marks"][-1]["d"]
    checks = {c["metric"]: c for c in layers.run_daily(con, "S5-live", today=today)}
    assert checks["freshness"]["status"] == "ok"
    assert checks["data_integrity"]["status"] == "ok"
    assert checks["return_cusum"]["status"] in ("ok", "breach")
    assert checks["slip_cusum"]["status"] == "ok"     # constant benign slip


# ---------------------------------------------------------- state machine --
def _register_min(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO edge_strategies (strategy_id, venue, cadence) "
                "VALUES ('S5-live','coinbase','per_trade')")
    fx = json.load(open(FIXTURE))
    baseline.register(con, "S5-live", fx)
    return con


def _mk(metric, status, **kw):
    return {"metric": metric, "status": status, "escalates": True, **kw}


def test_gate_green_to_yellow_and_cusum_reset(tmp_path):
    con = _register_min(tmp_path)
    for i in range(70):
        edb.record_nav(con, "S5-live", f"2026-06-{i % 30 + 1:02d}" if i < 30
                       else f"2026-07-{i - 29:02d}", 100.0 + i * 0.01, "t")
    sm = statemachine.step(con, "S5-live",
                           [_mk("return_cusum", "breach", half_threshold_ok=False)],
                           today="2026-08-01")
    assert sm["state"] == "YELLOW" and sm["size_mult"] == 0.5
    assert edb.kv_get(con, "S5-live", "cusum_reset_i") > 0   # pinned reset rule


def test_gate_blind_feed_cannot_vacuously_recover(tmp_path):
    con = _register_min(tmp_path)
    statemachine.step(con, "S5-live", [_mk("freshness", "breach")],
                      today="2026-08-01")
    assert con.execute("SELECT state FROM edge_strategies").fetchone()[0] == "YELLOW"
    # 25 days of BLIND checks -> must NOT recover (referee hole, closed)
    for i in range(25):
        statemachine.step(con, "S5-live",
                          [{"metric": "freshness", "status": "blind"}],
                          today=f"2026-08-{i + 2:02d}")
    assert con.execute("SELECT state FROM edge_strategies").fetchone()[0] == "YELLOW"
    # 20 clean fresh days -> recovers
    for i in range(20):
        statemachine.step(con, "S5-live",
                          [_mk("freshness", "ok"),
                           _mk("return_cusum", "ok", half_threshold_ok=True)],
                          today=f"2026-09-{i + 1:02d}")
    assert con.execute("SELECT state FROM edge_strategies").fetchone()[0] == "GREEN"


def test_gate_dual_confirmation_red_and_human_only_repromote(tmp_path):
    con = _register_min(tmp_path)
    statemachine.step(con, "S5-live",
                      [_mk("slip_cusum", "breach")], today="2026-08-01")
    sm = statemachine.step(con, "S5-live",
                           [_mk("return_cusum", "breach", half_threshold_ok=False)],
                           today="2026-08-10")
    assert sm["state"] == "RED" and sm["size_mult"] == 0.0
    # scheduler can never un-RED it
    sm2 = statemachine.step(con, "S5-live",
                            [_mk("return_cusum", "ok", half_threshold_ok=True)],
                            today="2026-09-20")
    assert sm2["state"] == "RED"
    with pytest.raises(ValueError):
        statemachine.re_promote(con, "S5-live", "no")
    statemachine.re_promote(con, "S5-live", "false alarm: vendor NAV restatement, verified vs venue")
    row = con.execute("SELECT state, size_mult FROM edge_strategies").fetchone()
    assert row == ("GREEN", 0.25)            # ramp re-entry, not full size


def test_gate_dd_p99_is_immediate_red(tmp_path):
    con = _register_min(tmp_path)
    sm = statemachine.step(con, "S5-live",
                           [_mk("dd_percentile", "breach", red=True)],
                           today="2026-08-01")
    assert sm["state"] == "RED"


# ------------------------------------------------------------- e2e + sync --
def test_gate_run_nightly_e2e_blind(tmp_path, monkeypatch):
    monkeypatch.delenv("EXEC_TOKEN", raising=False)
    con = _con(tmp_path)
    line = run.run_nightly(con)
    assert "S5-live" in line
    kinds = [r[0] for r in con.execute("SELECT kind FROM alerts")]
    assert "edge_baseline" in kinds and "edge_blind" in kinds
    assert con.execute("SELECT state FROM edge_strategies").fetchone()[0] == "YELLOW"


def test_gate_blueprint_sync():
    ryaml = open(os.path.join(_ROOT, "..", "render.yaml")).read()
    assert "EXEC_TOKEN" in ryaml
    ex = open(os.path.join(_ROOT, "..", "btc-executor", "app", "main.py")).read()
    assert '"fills": getattr(st, "fills"' in ex   # /status exposes fills
