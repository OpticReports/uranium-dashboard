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
    assert rep["nav"] == 90 and rep["trades"] == 15 and rep["revisions"] == 0
    # mark of day d is recorded as the CLOSE of d-1; intraday equity is
    # info-only and NEVER a nav row (referee bug 1: same-date mixing)
    first = con.execute("SELECT MIN(date) FROM edge_nav_daily").fetchone()[0]
    assert first == "2026-04-30"
    assert con.execute("SELECT COUNT(*) FROM edge_nav_daily WHERE "
                       "source='executor_live'").fetchone()[0] == 0
    rep2 = adapter_coinbase.sync(con, status=st)
    assert rep2["nav"] <= 1 and rep2["trades"] == 0 and rep2["revisions"] == 0
    # vendor rewrites an old mark -> revision, not overwrite
    st["marks"][0]["equity"] += 50.0
    rep3 = adapter_coinbase.sync(con, status=st)
    assert rep3["revisions"] == 1


def test_gate_no_deadlock_when_live_equity_differs(tmp_path):
    """Referee bug 1 (blocks-deploy, closed): live intraday equity that
    differs from the day's mark must produce ZERO revisions on repeated
    syncs — the old design revised itself into permanent YELLOW."""
    con = _con(tmp_path)
    st = _status()
    st["equity"] = st["marks"][-1]["equity"] + 137.5   # intraday <> mark
    for _ in range(3):
        rep = adapter_coinbase.sync(con, status=st)
        assert rep["revisions"] == 0
    assert edb.unresolved_revisions(con, adapter_coinbase.STRATEGY_ID) == 0


def test_gate_revision_resolution_is_human_gated(tmp_path):
    con = _con(tmp_path)
    edb.record_nav(con, "X", "2026-08-01", 100.0, "t")
    edb.record_nav(con, "X", "2026-08-01", 101.0, "t")
    assert edb.unresolved_revisions(con, "X") == 1
    with pytest.raises(ValueError):
        edb.resolve_revisions(con, "X", "ok")
    assert edb.resolve_revisions(con, "X",
                                 "verified vs venue statement 2026-08") == 1
    assert edb.unresolved_revisions(con, "X") == 0


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
    t0 = datetime(2026, 5, 15, tzinfo=timezone.utc)
    for i in range(70):
        edb.record_nav(con, "S5-live",
                       (t0 + timedelta(days=i)).date().isoformat(),
                       100.0 + i * 0.01, "t")
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


def test_gate_no_cross_episode_dual_red(tmp_path):
    """Referee bug 2 (closed): a resolved YELLOW episode's breach stamp must
    not combine with a later unrelated breach into a phantom RED."""
    con = _register_min(tmp_path)
    statemachine.step(con, "S5-live",
                      [_mk("return_cusum", "breach", half_threshold_ok=False)],
                      today="2026-08-01")
    for i in range(20):
        statemachine.step(con, "S5-live",
                          [_mk("freshness", "ok"),
                           _mk("return_cusum", "ok", half_threshold_ok=True)],
                          today=f"2026-08-{i + 2:02d}")
    assert con.execute("SELECT state FROM edge_strategies").fetchone()[0] == "GREEN"
    sm = statemachine.step(con, "S5-live", [_mk("slip_cusum", "breach")],
                           today="2026-08-25")
    assert sm["state"] == "YELLOW"          # NOT RED — episode was closed


def test_gate_dd_red_recovery_e2e(tmp_path):
    """Referee bug 3 (closed): crash -> dd RED -> equity recovers ->
    re-promotion sticks (next runs stay GREEN) and ramps 0.25->0.5->1.0
    without a YELLOW ever exceeding the ramp cap."""
    con = _register_min(tmp_path)
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
    nav, navs = 10_000.0, []
    for i in range(30):
        nav *= 0.994 if i < 25 else 0.9      # slow bleed then crash
        navs.append(((t0 + timedelta(days=i)).date().isoformat(), nav))
    for d, v in navs:
        edb.record_nav(con, "S5-live", d, v, "t")
    checks = layers.run_daily(con, "S5-live", today="2026-05-31")
    sm = statemachine.step(con, "S5-live", checks, today="2026-05-31")
    assert sm["state"] == "RED"
    # equity recovers to a new high
    for i in range(30, 45):
        nav *= 1.06
        edb.record_nav(con, "S5-live",
                       (t0 + timedelta(days=i)).date().isoformat(), nav, "t")
    statemachine.re_promote(con, "S5-live",
                            "reviewed: vol event, venue confirmed, re-entering at ramp")
    edb.kv_set(con, "S5-live", "last_sync_utc", "2026-06-15T09:00:00+00:00")
    checks = layers.run_daily(con, "S5-live", today="2026-06-15")
    sm = statemachine.step(con, "S5-live", checks, today="2026-06-15")
    assert sm["state"] == "GREEN"            # dd statistic recovered with equity
    assert con.execute("SELECT size_mult FROM edge_strategies").fetchone()[0] == 0.25
    # a YELLOW during ramp must NOT double size (referee F2)
    sm = statemachine.step(con, "S5-live",
                           [_mk("slip_cusum", "breach")], today="2026-06-16")
    assert sm["state"] == "YELLOW" and sm["size_mult"] == 0.125


def test_gate_day_one_crash_is_visible(tmp_path):
    """Referee note (closed): a first-day crash must register in check_dd
    (equity is anchored at 1.0)."""
    con = _register_min(tmp_path)
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i, v in enumerate([8_600.0, 8_580.0, 8_560.0, 8_590.0, 8_570.0, 8_540.0]):
        edb.record_nav(con, "S5-live",
                       (t0 + timedelta(days=i)).date().isoformat(), v, "t")
    # returns exist only from day 2; a -14% first PRINT is invisible by
    # construction (nav starts at first row) — but a -14% move INSIDE the
    # series must show:
    edb.record_nav(con, "S5-live", "2026-05-07", 8_540.0 * 0.86, "t")
    c = {x["metric"]: x for x in layers.run_daily(con, "S5-live",
                                                  today="2026-05-08")}
    assert c["dd_percentile"]["value"] <= -0.13
    assert c["dd_percentile"]["red"] is True


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


def test_gate_adapter_skips_void_fills(tmp_path):
    """2026-08-26 phantom incident: fills marked void by the executor are
    broken measurements (1320bps against a days-stale reference; one never
    happened at all). They must not enter edge_trades, where slip stats
    authorize KELLY_M sizing. Mutation-tested: removing the filter fails."""
    con = _con(tmp_path)
    st = _status(n_fills=3)
    st["fills"].append({"ts": st["fills"][-1]["ts"] + 60, "leg": "trend",
                        "role": "chase", "cloid": "poison", "side": "BUY",
                        "px": 77_575.0, "ref_px": 68_525.61,
                        "slip_bps": 1320.59, "live": True, "void": True})
    rep = adapter_coinbase.sync(con, status=st)
    assert rep["trades"] == 3, "void fill must not be ingested"
    assert rep.get("voided_skipped") == 1
    n = con.execute("SELECT COUNT(*) FROM edge_trades WHERE "
                    "trade_id LIKE 'poison%'").fetchone()[0]
    assert n == 0, "the poison row reached edge_trades"


# ---------------------------------------------------------------------------
# 2026-08-27: the void filter only stops RE-ingestion. Rows already in
# edge_trades — and any slip_norms frozen from them — needed a purge, because
# those norms gate the CUSUM that authorizes KELLY_M sizing.
def _trade(i, slip, ts_day=1):
    return {"trade_id": f"t{i}", "ts_utc": f"2026-08-{ts_day:02d}T00:00:{i:02d}+00:00",
            "side": "BUY", "fill_px": 70_000.0, "model_px": 70_000.0,
            "slip_bps": slip}


def test_gate_quarantine_migration_on_a_preexisting_db(tmp_path):
    """THE migration gate: a live DB created by the OLD schema never gains
    columns from CREATE TABLE IF NOT EXISTS — the exact trap that 500'd the
    live disk on edge_revisions in 2026-08-14. Build the old table by hand,
    then prove ensure_schema migrates it AND that inserts still work."""
    p = str(tmp_path / "old.db")
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE edge_trades (strategy_id TEXT NOT NULL, "
        "trade_id TEXT NOT NULL, ts_utc TEXT NOT NULL, side TEXT, qty REAL, "
        "notional_usd REAL, fill_px REAL, model_px REAL, slip_bps REAL, "
        "fees_usd REAL, pnl_usd REAL, PRIMARY KEY (strategy_id, trade_id));")
    con.commit()
    edb.ensure_schema(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(edge_trades)")}
    assert {"quarantined", "quarantine_note"} <= cols, f"not migrated: {cols}"
    # and the widened table must still accept a normal insert (a positional
    # VALUES(...) would blow up here with 11 values for 13 columns)
    assert edb.record_trade(con, "S5-live", _trade(1, 2.0)) == "inserted"
    assert edb.ensure_schema(con) is None          # idempotent, no crash


def test_gate_quarantine_excludes_from_slip_stats(tmp_path):
    con = _con(tmp_path)
    for i in range(10):
        edb.record_trade(con, "S5-live", _trade(i, 2.0))
    edb.record_trade(con, "S5-live", _trade(99, 1320.59))
    con.commit()
    before = layers.check_slippage(con, "S5-live", {})
    assert before["status"] == "breach", \
        f"fixture must trip the CUSUM before the purge: {before}"
    edb.quarantine_trades(con, "S5-live", ["t99"],
                          "phantom incident: stale ref_px, fill never happened")
    after = layers.check_slippage(con, "S5-live", {})
    assert after["status"] == "ok" and after["value"] < before["value"], \
        f"quarantine did not clear the fictitious breach: {before} -> {after}"
    rows = con.execute("SELECT slip_bps FROM edge_trades WHERE strategy_id=? "
                       "AND quarantined=0", ("S5-live",)).fetchall()
    assert 1320.59 not in [r[0] for r in rows]
    # the row SURVIVES with its reason — append-only means you can still see
    # what was excluded and why
    r = con.execute("SELECT slip_bps, quarantine_note FROM edge_trades "
                    "WHERE trade_id='t99'").fetchone()
    assert r[0] == 1320.59 and "phantom" in r[1]


def test_gate_quarantine_drops_contaminated_slip_norms(tmp_path):
    """The norms freeze on the first 10 rows. If a purge changes which rows
    those are, keeping the old norms keeps the contamination — the filter
    alone would not have fixed the live DB."""
    con = _con(tmp_path)
    edb.record_trade(con, "S5-live", _trade(0, 1320.59))
    for i in range(1, 11):
        edb.record_trade(con, "S5-live", _trade(i, 2.0))
    con.commit()
    layers.check_slippage(con, "S5-live", {})          # freezes norms
    norms = edb.kv_get(con, "S5-live", "slip_norms")
    assert norms and norms["mean"] > 100, "fixture did not contaminate norms"
    rep = edb.quarantine_trades(con, "S5-live", ["t0"], "broken measurement row")
    assert rep["quarantined"] == 1 and rep["slip_norms_dropped"] is True
    assert edb.kv_get(con, "S5-live", "slip_norms") is None
    layers.check_slippage(con, "S5-live", {})          # re-freezes clean
    assert edb.kv_get(con, "S5-live", "slip_norms")["mean"] == pytest.approx(2.0)


def test_gate_quarantine_requires_a_written_rationale(tmp_path):
    """Same posture as resolve_revisions: this is the one operation that can
    make a decaying strategy look healthy, so it is never casual."""
    con = _con(tmp_path)
    edb.record_trade(con, "S5-live", _trade(1, 1320.59))
    con.commit()
    for bad in ("", "oops"):
        with pytest.raises(ValueError):
            edb.quarantine_trades(con, "S5-live", ["t1"], bad)
    assert con.execute("SELECT quarantined FROM edge_trades WHERE "
                       "trade_id='t1'").fetchone()[0] == 0


def test_gate_quarantine_never_deletes(tmp_path):
    con = _con(tmp_path)
    for i in range(3):
        edb.record_trade(con, "S5-live", _trade(i, 900.0))
    con.commit()
    edb.quarantine_trades(con, "S5-live", ["t0", "t1", "t2"], "all three broken")
    n = con.execute("SELECT COUNT(*) FROM edge_trades").fetchone()[0]
    assert n == 3, "append-only law violated: rows were deleted"
    log = con.execute("SELECT trigger FROM edge_state_log WHERE "
                      "strategy_id='S5-live'").fetchall()
    assert ("quarantine_trades",) in log, "purge left no audit trail"


def test_gate_find_absurd_slippage_matches_executor_void_rule(tmp_path):
    con = _con(tmp_path)
    edb.record_trade(con, "S5-live", _trade(1, 499.0))
    edb.record_trade(con, "S5-live", _trade(2, 501.0))
    edb.record_trade(con, "S5-live", _trade(3, -1320.59))
    con.commit()
    got = {r["trade_id"] for r in edb.find_absurd_slippage(con, "S5-live")}
    assert got == {"t2", "t3"}, f"threshold/abs mismatch vs |slip|>500: {got}"
    edb.quarantine_trades(con, "S5-live", ["t2"], "already handled this one")
    assert {r["trade_id"] for r in edb.find_absurd_slippage(con, "S5-live")} == {"t3"}


def test_gate_purge_cli_dry_run_changes_nothing(tmp_path):
    from barbell.edge import purge_cli
    p = str(tmp_path / "cli.db")
    con = sqlite3.connect(p)
    edb.ensure_schema(con)
    edb.record_trade(con, "S5-live", _trade(1, 1320.59))
    con.commit()
    con.close()
    assert purge_cli.main(["--db", p]) == 0
    con = sqlite3.connect(p)
    assert con.execute("SELECT quarantined FROM edge_trades").fetchone()[0] == 0, \
        "dry run quarantined a row"
    # and --apply without a rationale is REFUSED, not silently accepted
    assert purge_cli.main(["--db", p, "--apply", "--note", "x"]) == 2
    assert con.execute("SELECT quarantined FROM edge_trades").fetchone()[0] == 0
    assert purge_cli.main(["--db", p, "--apply", "--note",
                           "phantom incident cleanup 2026-08-26"]) == 0
    assert con.execute("SELECT quarantined FROM edge_trades").fetchone()[0] == 1


def test_gate_quarantine_excludes_from_behavior_rate(tmp_path):
    """MUTATION KILLER for check_behavior's quarantine filter.

    Found the hard way (2026-08-27): a counter-agent planted exactly this
    mutation, the container died mid-run, and the orphaned diff proved it
    survived all 26 tests — check_slippage was covered, check_behavior was
    not. A purge that fixes one edge_trades reader and not the other leaves
    the ops tripwire counting rows the stats have already disowned, so a
    phantom-fill burst reads as a strategy that suddenly changed behaviour.

    Fixture: 30 nav days, expected 0.1 trades/day (breach above 0.3/day).
    5 real trades = 0.167/day -> ok. Count the 20 quarantined rows too and
    it is 0.833/day -> a fictitious breach."""
    con = _con(tmp_path)
    for i in range(30):
        edb.record_nav(con, "S5-live", f"2026-07-{i + 1:02d}", 50_000.0 + i, "t")
    for i in range(5):
        edb.record_trade(con, "S5-live", _trade(i, 2.0))
    for i in range(100, 120):
        edb.record_trade(con, "S5-live", _trade(i, 1320.59))
    con.commit()
    base = {"expected_trades_per_day": 0.1}
    before = layers.check_behavior(con, "S5-live", base)
    assert before["status"] == "breach", f"fixture must breach first: {before}"
    edb.quarantine_trades(con, "S5-live", [f"t{i}" for i in range(100, 120)],
                          "phantom fill burst, not real executions")
    after = layers.check_behavior(con, "S5-live", base)
    assert after["status"] == "ok", \
        f"quarantined rows still counted in the trade rate: {after}"
    assert after["value"] == round(5 / 30, 3), \
        f"rate must count the 5 surviving trades only: {after}"
