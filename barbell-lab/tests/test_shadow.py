"""BARBELL-SHADOW gates (BARBELL_SHADOW_SPEC.md, frozen 2026-08-12).

The load-bearing gate is research parity: the live decision brain must
reproduce the study's rule-2 states EXACTLY on the frozen fixture. Every
builder's first implementation in this repo had a timing defect only a
referee caught — this gate makes the live-vs-research divergence class
impossible to ship silently.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from barbell import db, shadow

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BT = os.path.join(_ROOT, "research", "barbell_timer")


def _panel():
    j = json.load(open(os.path.join(_BT, "panel_monthly.json")))["panel"]
    df = pd.DataFrame.from_dict(j, orient="index").astype(float)
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df.sort_index()


# ------------------------------------------------------------- parity gate --
def test_gate_relmom_parity_with_research_fixture():
    """shadow.relmom_states on the frozen study panel must equal rules.py's
    rule-2 states for EVERY month the study emitted. (The study index starts
    later — its signal frame also drops rows for tips burn-in — so the shadow
    series may have extra early months, but on the overlap: exact match.)"""
    panel = _panel()
    got = shadow.relmom_states(panel["gde_synth"], panel["spx_tr"], panel["bills"])
    exp = json.load(open(os.path.join(_BT, "rules_results.json")))["states"]["rule2"]
    assert len(exp) > 500
    mismatches = {m: (exp[m], str(got.get(pd.Period(m, "M"))))
                  for m in exp if str(got.get(pd.Period(m, "M"))) != exp[m]}
    assert not mismatches, f"live brain diverged from studied brain: {mismatches}"
    # and the shadow series must COVER the study's window entirely
    first_exp = pd.Period(min(exp), "M")
    assert got.index.min() <= first_exp


def test_gate_mom121_convention():
    """12-1 = compounded t-11..t-1, skipping month t."""
    r = pd.Series([0.01] * 14, index=pd.period_range("2020-01", periods=14, freq="M"))
    m = shadow.mom121(r)
    assert m.iloc[:12].isna().all()
    assert m.iloc[12] == pytest.approx(1.01 ** 11 - 1)
    # month t excluded: a huge month-t return must not move month-t's own signal
    r2 = r.copy()
    r2.iloc[12] = 5.0
    assert shadow.mom121(r2).iloc[12] == pytest.approx(m.iloc[12])


def test_gate_gating_logic():
    """V2 fires only on GDE states; SPY/BOXX pass through untouched."""
    idx = pd.period_range("2025-01", periods=4, freq="M")
    states = pd.Series(["gde", "gde", "spy", "boxx"], index=idx)
    riskoff = pd.Series([True, False, True, True], index=idx)
    out = shadow.gate_states(states, riskoff)
    assert list(out) == ["boxx", "gde", "spy", "boxx"]


def test_gate_s16_direction():
    """Utilities LEADING (XLU 12-1 > SPY 12-1) = risk-off. The study's twist:
    equity risk-off predicts GDE WINNING — the gate still parks in BOXX
    because rule 10's shape was frozen that way (A21)."""
    idx = pd.period_range("2020-01", periods=15, freq="M")
    xlu = pd.Series(0.02, index=idx)
    spy = pd.Series(0.01, index=idx)
    ro = shadow.s16_riskoff(xlu, spy)
    assert bool(ro.iloc[-1]) is True
    assert bool(shadow.s16_riskoff(spy, xlu).iloc[-1]) is False


# ---------------------------------------------------------- timing + costs --
def test_gate_complete_month_rule():
    """A month is complete only when a later-month observation exists —
    the last month present is always dropped."""
    days = pd.bdate_range("2026-05-01", "2026-07-15")
    px = pd.Series(np.linspace(100, 110, len(days)), index=days)
    me = shadow.complete_monthly_closes(px)
    assert str(me.index.max()) == "2026-06"     # July (partial) dropped
    # and June's value is June's LAST close, not July's first
    assert me.loc[pd.Period("2026-06", "M")] == px[px.index.month == 6].iloc[-1]


def test_gate_backtest_timing_and_cost():
    """Decision t earns month t+1; 5bp x one-way drift-aware turnover."""
    didx = pd.period_range("2026-01", periods=3, freq="M")
    aidx = pd.period_range("2026-01", periods=4, freq="M")
    assets = pd.DataFrame({"gde": [0.10, 0.02, 0.03, 0.04],
                           "spy": [0.0, 0.0, 0.0, 0.0],
                           "boxx": [0.0, 0.0, 0.0, 0.0]}, index=aidx)
    states = pd.Series(["gde", "gde", "boxx"], index=didx)
    r, to = shadow.shadow_backtest(states, assets)
    # decision 2026-01 earns FEB (0.02), not January's 0.10
    assert r.loc[pd.Period("2026-02", "M")] == pytest.approx(0.02)
    # full switch gde->boxx: turnover 1.0, cost 5bp charged in the traded month
    assert to.loc[pd.Period("2026-04", "M")] == pytest.approx(1.0)
    assert r.loc[pd.Period("2026-04", "M")] == pytest.approx(0.0 - shadow.SWITCH_COST)
    # initial buy-in uncharged
    assert to.loc[pd.Period("2026-02", "M")] == 0.0


def test_gate_bills_use_prior_month_end_yield():
    """Month-t bill return comes from DTB3 month-end of t-1 (knowable at the
    start of t) — future yields must not leak backwards."""
    days = pd.bdate_range("2026-01-01", "2026-03-31")
    y = pd.Series(4.0, index=days)
    y[days.month == 2] = 8.0
    y[days.month == 3] = 12.0
    b = shadow.bill_monthly_returns(y)
    assert b.loc[pd.Period("2026-02", "M")] == pytest.approx((1.04) ** (1 / 12) - 1)
    assert b.loc[pd.Period("2026-03", "M")] == pytest.approx((1.08) ** (1 / 12) - 1)


def test_gate_truncation_invariance():
    """Chopping future data must not change earlier decisions (the study's
    walk-forward discipline, applied to the live brain)."""
    rng = np.random.default_rng(3)
    idx = pd.period_range("2020-01", periods=60, freq="M")
    mk = lambda: pd.Series(rng.normal(0.008, 0.04, 60), index=idx)
    g, s, x = mk(), mk(), mk()
    b = pd.Series(0.003, index=idx)
    full = shadow.decisions_frame(g, s, b, x)
    T = pd.Period("2023-06", "M")
    cut = shadow.decisions_frame(g[g.index <= T], s[s.index <= T],
                                 b[b.index <= T], x[x.index <= T])
    pd.testing.assert_frame_equal(full.loc[:T], cut.loc[:T])


# ------------------------------------------------------------ log + board --
def _seed(con, months=20):
    """Synthetic daily prices for all four tickers + DTB3, `months` COMPLETE
    months ending 2026-07 plus a few August days (so July is complete)."""
    days = pd.bdate_range(end="2026-08-06", periods=months * 22)
    rng = np.random.default_rng(11)
    for tkr in ("GDE", "SPY", "BOXX", "XLU"):
        px = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
        df = pd.DataFrame({"ticker": tkr,
                           "date": [d.strftime("%Y-%m-%d") for d in days],
                           "close_adj": px, "close_raw": px, "volume": 0.0,
                           "source": "yahoo"})
        db.upsert_prices(con, df)
    db.upsert_fred(con, "DTB3", pd.Series(4.5, index=days))


def test_gate_log_idempotent_and_append_only(tmp_path):
    con = db.connect(tmp_path / "t.db")
    _seed(con)
    now = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
    first = shadow.log_decisions(con, now=now)
    assert {r["variant"] for r in first} == set(shadow.VARIANTS)
    assert all(r["held_month"] == "2026-08" and r["decision_month"] == "2026-07"
               for r in first)
    # second run: nothing inserted, nothing overwritten
    assert shadow.log_decisions(con, now=now) == []
    con.execute("UPDATE prices SET close_adj = close_adj * 1.5 "
                "WHERE ticker='GDE' AND date < '2026-01-01'")
    con.commit()
    assert shadow.log_decisions(con) == []          # still append-only
    con.close()


def test_gate_board_flags_revision_mismatch(tmp_path):
    """If the vendor rewrites history such that a logged decision no longer
    recomputes, the board must flag it RED — never silently re-score."""
    con = db.connect(tmp_path / "t.db")
    _seed(con)
    shadow.log_decisions(con, now=datetime(2026, 8, 3, tzinfo=timezone.utc))
    b0 = shadow.board(con)
    assert b0["mismatches"] == []
    assert all(r["recompute_ok"] for r in b0["ledger"])
    con.execute("UPDATE shadow_log SET state = ? WHERE variant='relmom_cash'",
                ("spy" if b0["ledger"][0]["state"] != "spy" else "gde",))
    con.commit()
    b1 = shadow.board(con)
    assert len(b1["mismatches"]) == 1
    con.close()


def test_gate_late_stamp():
    assert shadow._late(pd.Period("2026-09", "M"), "2026-09-05T09:00:00+00:00") is False
    assert shadow._late(pd.Period("2026-09", "M"), "2026-09-06T09:00:00+00:00") is True


def test_gate_missing_inputs_raise(tmp_path):
    con = db.connect(tmp_path / "t.db")
    with pytest.raises(shadow.ShadowDataError, match="GDE"):
        shadow.load_inputs(con)
    con.close()


# ----------------------------------------------------- config + spec pins --
def test_gate_config_declares_shadow_inputs():
    """Blueprint-sync lesson: the code's data needs and the ingest config
    must never drift apart."""
    import yaml
    cfg = yaml.safe_load(open(os.path.join(_ROOT, "config", "data.yaml")))
    for tkr in ("GDE", "BOXX", "XLU", "SPY"):
        assert tkr in cfg["tickers"], f"{tkr} missing from config/data.yaml"
        assert cfg["tickers"][tkr]["proxy"] is None   # live history only — no splices
    assert "DTB3" in cfg["fred"]


def test_gate_spec_pins_frozen_constants():
    spec = open(os.path.join(_ROOT, "BARBELL_SHADOW_SPEC.md")).read()
    assert "Frozen 2026-08-12" in spec
    assert str(shadow.FREEZE_DECISION) == "2026-08" and "2026-08" in spec
    assert shadow.SWITCH_COST == 0.0005 and "5bp" in spec
    assert shadow.LATE_DAY == 5 and "5th calendar day" in spec
    # study reference numbers must match the frozen verdict
    assert shadow.STUDY_REFERENCE["relmom_cash"]["cagr"] == 0.1523
    assert shadow.STUDY_REFERENCE["relmom_cash_lagged_1m"]["maxdd"] == -0.493
