"""Tests for the calls-performance time series (the learning-loop instrument)."""
from __future__ import annotations

from datetime import date, timedelta

from app.calls.performance import calls_performance
from app.models import FlagOutcome, Security, TradeCall


def _call(session, symbol, call_date, exit_date, r, entry=100.0):
    stop = entry - 6.0
    exit_price = entry + r * (entry - stop)
    call = TradeCall(
        symbol=symbol, call_date=call_date, direction="long", source="auto_flag",
        flag_type="pre_catalyst_sentiment_ramp", entry_price=entry, stop_price=stop,
        target_price=entry + 3 * (entry - stop),
        expires_on=call_date + timedelta(days=45), status="expired",
        exit_date=exit_date, exit_price=exit_price,
        return_pct=(exit_price - entry) / entry, r_multiple=r,
    )
    session.add(call)


def test_performance_series(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    base = date(2026, 5, 1)
    # Month 1: two losers; month 2: two winners — later cohort better.
    _call(session, "CRSP", base, base + timedelta(days=10), -1.0)
    _call(session, "CRSP", base + timedelta(days=5), base + timedelta(days=15), -1.0)
    _call(session, "CRSP", base + timedelta(days=35), base + timedelta(days=45), 2.0)
    _call(session, "CRSP", base + timedelta(days=40), base + timedelta(days=50), 3.0)
    session.commit()

    perf = calls_performance(session)
    assert perf["closed_calls"] == 4
    assert perf["cum_r"] == 3.0
    assert [p["cum_r"] for p in perf["equity_curve"]] == [-1.0, -2.0, 0.0, 3.0]
    last_roll = perf["rolling"][-1]
    assert last_roll["n"] == 4 and last_roll["win_rate"] == 0.5
    months = {m["month"]: m for m in perf["monthly_cohorts"]}
    assert months["2026-05"]["avg_r"] == -1.0
    assert months["2026-06"]["avg_r"] == 2.5   # the learning signal: later > earlier


def test_performance_flag_cohorts_prefer_excess(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    session.add(FlagOutcome(flag_id=1, symbol="CRSP", flag_type="volume_anomaly",
                            fired_on=date(2026, 5, 3), price_at_fire=100.0,
                            fwd_1m=0.10, excess_1m=0.04))
    session.add(FlagOutcome(flag_id=2, symbol="CRSP", flag_type="volume_anomaly",
                            fired_on=date(2026, 5, 20), price_at_fire=100.0,
                            fwd_1m=-0.05, excess_1m=-0.02))
    session.commit()
    perf = calls_performance(session)
    fc = perf["flag_cohorts"]
    assert len(fc) == 1 and fc[0]["month"] == "2026-05"
    assert fc[0]["n"] == 2 and fc[0]["hit_rate"] == 0.5
    assert abs(fc[0]["avg_excess"] - 0.01) < 1e-9


def test_performance_empty_is_graceful(session):
    perf = calls_performance(session)
    assert perf["closed_calls"] == 0
    assert perf["equity_curve"] == [] and perf["monthly_cohorts"] == []
