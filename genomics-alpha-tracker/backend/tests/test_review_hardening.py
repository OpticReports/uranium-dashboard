"""Tests for the adversarial-review hardening pass:

gap-aware exit fills, binary-expiry refusal, median-ADDV liquidity tiers,
Tier-C auto-call exclusion, hardened pullback/volume/insider flags, flag
re-fire suppression, and the uncensored flag forward-return track record.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import select

from app.calls import manager
from app.calls.rules import BarLike, addv, grade_call, liquidity_tier
from app.models import Catalyst, FlagEvent, InsiderTxn, PriceBar, ScoreSnapshot, Security
from app.scoring import components as C
from app.scoring.flags import evaluate_flags
from app.scoring.outcomes import evaluate_flag_outcomes, flag_track_record


# --- gap-aware fills + open-first resolution --------------------------------------

def test_gap_up_then_fade_is_a_win_not_a_stop():
    # The classic biotech readout day: opens way above target, fades hard
    # intraday through the stop. The open is the KNOWN first event — this is
    # a target exit at the open, not a -1R stop.
    bars = [BarLike(date(2026, 1, 2), 116.0, 95.0, 98.0, open=115.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "target_hit" and ex.exit_price == 115.0


def test_short_gap_down_then_squeeze_is_a_win():
    bars = [BarLike(date(2026, 1, 2), 105.0, 84.0, 103.0, open=85.0)]
    ex = grade_call("short", 100.0, 104.0, 92.0, date(2026, 2, 1), bars)
    assert ex.status == "target_hit" and ex.exit_price == 85.0


def test_open_through_stop_still_resolves_first():
    # Opens below the stop, then rips through the target intraday: the open
    # was first — stopped at the open, not a win.
    bars = [BarLike(date(2026, 1, 2), 112.0, 94.0, 111.0, open=95.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped" and ex.exit_price == 95.0


def test_monday_binary_exits_at_friday_close():
    # Expiry lands on a Sunday (event Monday). The first bar on/after expiry
    # is the event day itself — the time-stop must exit at Friday's close.
    fri = date(2026, 1, 9)   # Friday
    sun = date(2026, 1, 11)  # expires_on (event Monday the 12th)
    mon = date(2026, 1, 12)
    bars = [
        BarLike(fri, 101.0, 99.0, 100.5, open=100.0),
        BarLike(mon, 70.0, 55.0, 60.0, open=65.0),  # post-event crash
    ]
    ex = grade_call("long", 100.0, 90.0, 120.0, sun, bars)
    assert ex.status == "expired"
    assert ex.exit_date == fri and ex.exit_price == 100.5


# --- gap-aware fills ------------------------------------------------------------

def test_gap_through_stop_fills_at_open():
    # Close 100, stop 96 — next bar gaps open at 87. Real fill is 87, not 96.
    bars = [BarLike(date(2026, 1, 2), 90.0, 85.0, 88.0, open=87.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped" and ex.exit_price == 87.0


def test_gap_through_target_fills_at_open():
    bars = [BarLike(date(2026, 1, 2), 120.0, 111.0, 115.0, open=112.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "target_hit" and ex.exit_price == 112.0


def test_intrabar_touch_still_fills_at_level():
    # Opens inside the range, trades down through the stop intrabar.
    bars = [BarLike(date(2026, 1, 2), 101.0, 95.0, 97.0, open=100.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped" and ex.exit_price == 96.0


def test_short_gap_through_stop_fills_at_open():
    bars = [BarLike(date(2026, 1, 2), 112.0, 105.0, 110.0, open=108.0)]
    ex = grade_call("short", 100.0, 104.0, 92.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped" and ex.exit_price == 108.0


# --- liquidity ------------------------------------------------------------------

def _bars_with_dollar(n, close, start=date(2026, 1, 1)):
    return [BarLike(start + timedelta(days=i), close + 1, close - 1, close) for i in range(n)]


def test_addv_is_median_not_mean():
    bars = _bars_with_dollar(21, close=10.0)
    volumes = [100_000.0] * 20 + [50_000_000.0]  # one blowout day
    # median dollar volume stays ~$1M; a mean would be ~$25M+.
    value = addv(bars, volumes, 20)
    assert value == 10.0 * 100_000.0


def test_liquidity_tiers():
    assert liquidity_tier(30e6, 25e6, 5e6) == "A"
    assert liquidity_tier(10e6, 25e6, 5e6) == "B"
    assert liquidity_tier(1e6, 25e6, 5e6) == "C"
    assert liquidity_tier(None, 25e6, 5e6) is None


def test_tier_c_names_do_not_generate_auto_calls(session):
    # Thin name: $10 close x 10k shares = $100k/day => Tier C.
    session.add(Security(symbol="THIN", name="Thin Name", active=True))
    start = date.today() - timedelta(days=30)
    for i in range(30):
        session.add(PriceBar(symbol="THIN", date=start + timedelta(days=i),
                             open=10.0, high=10.5, low=9.5, close=10.0, volume=10_000))
    session.add(ScoreSnapshot(symbol="THIN", composite=90.0))
    session.add(FlagEvent(symbol="THIN", flag_type="pre_catalyst_sentiment_ramp",
                          severity="high", message="ramp", evidence={}))
    session.commit()
    assert manager.generate_calls(session) == []


# --- binary expiry refusal --------------------------------------------------------

def test_call_refused_when_binary_too_close(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    start = date.today() - timedelta(days=30)
    for i in range(30):
        session.add(PriceBar(symbol="CRSP", date=start + timedelta(days=i),
                             open=100.0, high=101.0, low=99.0, close=100.0, volume=1e6))
    last_bar = start + timedelta(days=29)
    # Binary catalyst 3 days after the last bar: exit-before = day 2 < min horizon 5.
    session.add(Catalyst(symbol="CRSP", date=last_bar + timedelta(days=3),
                         event_type="pdufa", title="PDUFA", impact_weight=1.0))
    session.add(ScoreSnapshot(symbol="CRSP", composite=85.0))
    session.add(FlagEvent(symbol="CRSP", flag_type="pre_catalyst_sentiment_ramp",
                          severity="high", message="ramp", evidence={}))
    session.commit()
    # The flag fires but no call is generated — too close to the event.
    assert manager.generate_calls(session) == []


# --- hardened flags ----------------------------------------------------------------

def _sec(symbol="TEST"):
    return Security(symbol=symbol, name=symbol, active=True)


def _base_raw(**over):
    raw = {
        "mention_accel_z": None, "mention_z": None, "iv_z": None, "runway": None,
        "pullback_pct": None, "last_close": None, "atr14": None,
        "above_50dma": None, "volume_z": None, "last_dollar_volume": None,
        "insider_buys": [],
        "evidence": {"catalysts": [], "revisions": [], "mentions": []},
    }
    raw.update(over)
    return raw


def _catalyst(days_out, impact=0.9, asof=None):
    asof = asof or date.today()
    return Catalyst(symbol="TEST", date=asof + timedelta(days=days_out),
                    event_type="phase3_readout", title="P3", impact_weight=impact)


def test_pullback_flag_fires_with_all_qualifiers():
    asof = date.today()
    raw = _base_raw(
        pullback_pct=0.15, last_close=85.0, atr14=4.0, above_50dma=True,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    flags = evaluate_flags(_sec(), asof, raw, {})
    types = [f.flag_type for f in flags]
    assert "pullback_into_catalyst" in types


def test_pullback_flag_needs_trend_qualifier():
    asof = date.today()
    raw = _base_raw(
        pullback_pct=0.15, last_close=85.0, atr14=4.0, above_50dma=False,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert not any(f.flag_type == "pullback_into_catalyst"
                   for f in evaluate_flags(_sec(), asof, raw, {}))


def test_pullback_flag_rejects_breakdown_depth():
    asof = date.today()
    raw = _base_raw(
        pullback_pct=0.45, last_close=55.0, atr14=4.0, above_50dma=True,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert not any(f.flag_type == "pullback_into_catalyst"
                   for f in evaluate_flags(_sec(), asof, raw, {}))


def test_pullback_flag_needs_atr_depth():
    # 10% off the high but the name swings 8 points a day — noise, not a pullback.
    asof = date.today()
    raw = _base_raw(
        pullback_pct=0.10, last_close=90.0, atr14=8.0, above_50dma=True,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert not any(f.flag_type == "pullback_into_catalyst"
                   for f in evaluate_flags(_sec(), asof, raw, {}))


def test_pullback_flag_respects_catalyst_min_days():
    asof = date.today()
    raw = _base_raw(
        pullback_pct=0.15, last_close=85.0, atr14=4.0, above_50dma=True,
        evidence={"catalysts": [_catalyst(5, asof=asof)], "revisions": []},
    )
    assert not any(f.flag_type == "pullback_into_catalyst"
                   for f in evaluate_flags(_sec(), asof, raw, {}))


def test_volume_anomaly_needs_dollar_floor():
    asof = date.today()
    quiet = _base_raw(volume_z=3.0, last_dollar_volume=200_000)
    assert not any(f.flag_type == "volume_anomaly"
                   for f in evaluate_flags(_sec(), asof, quiet, {}))
    real = _base_raw(volume_z=3.0, last_dollar_volume=5_000_000)
    assert any(f.flag_type == "volume_anomaly"
               for f in evaluate_flags(_sec(), asof, real, {}))


def test_volume_zscore_is_log_scaled():
    # A prior blowout day would crush a raw-volume z; log tames it.
    base = [1e6] * 40 + [5e7] + [1e6] * 19  # one 50x day in history
    spike = base + [1e7]                     # today: 10x normal
    z = C.volume_zscore_raw(spike)
    assert z is not None and z > 2.5


def test_insider_cluster_requires_distinct_insiders():
    asof = date.today()
    same = [
        InsiderTxn(symbol="TEST", date=asof - timedelta(days=i), insider="CEO Jane",
                   txn_type="buy", shares=1000, value=50_000)
        for i in (3, 10)
    ]
    raw = _base_raw(insider_buys=same)
    assert not any(f.flag_type == "insider_buying_cluster"
                   for f in evaluate_flags(_sec(), asof, raw, {}))
    two = [
        InsiderTxn(symbol="TEST", date=asof - timedelta(days=3), insider="CEO Jane",
                   txn_type="buy", shares=1000, value=50_000),
        InsiderTxn(symbol="TEST", date=asof - timedelta(days=8), insider="CFO Bob",
                   txn_type="buy", shares=500, value=30_000),
    ]
    raw = _base_raw(insider_buys=two)
    assert any(f.flag_type == "insider_buying_cluster"
               for f in evaluate_flags(_sec(), asof, raw, {}))


def test_insider_cluster_requires_min_value():
    asof = date.today()
    tiny = [
        InsiderTxn(symbol="TEST", date=asof - timedelta(days=3), insider="CEO Jane",
                   txn_type="buy", shares=10, value=1_000),
        InsiderTxn(symbol="TEST", date=asof - timedelta(days=8), insider="CFO Bob",
                   txn_type="buy", shares=10, value=1_500),
    ]
    raw = _base_raw(insider_buys=tiny)
    assert not any(f.flag_type == "insider_buying_cluster"
                   for f in evaluate_flags(_sec(), asof, raw, {}))


# --- flag outcomes (the uncensored learning loop) ---------------------------------

def _seed_prices(session, symbol, closes, start):
    session.add(Security(symbol=symbol, name=symbol, active=True))
    for i, c in enumerate(closes):
        session.add(PriceBar(symbol=symbol, date=start + timedelta(days=i),
                             open=c, high=c + 1, low=c - 1, close=c, volume=1e6))
    session.commit()


def test_flag_outcome_forward_and_excess_returns(session):
    start = date.today() - timedelta(days=120)
    # Name rallies 1% a bar; XBI is flat -> positive excess.
    _seed_prices(session, "WINR", [100.0 * (1.01 ** i) for i in range(80)], start)
    _seed_prices(session, "XBI", [100.0] * 80, start)
    fired = start + timedelta(days=10)
    flag = FlagEvent(symbol="WINR", flag_type="pre_catalyst_sentiment_ramp",
                     severity="high", message="test", evidence={})
    flag.asof = flag.asof.replace(year=fired.year, month=fired.month, day=fired.day)
    session.add(flag)
    session.commit()

    n = evaluate_flag_outcomes(session)
    assert n == 1
    record = flag_track_record(session)
    stats = record["by_flag_type"]["pre_catalyst_sentiment_ramp"]
    h1m = stats["horizons"]["1m"]
    assert stats["fired"] == 1
    assert h1m["n"] == 1
    assert h1m["hit_rate"] == 1.0
    assert h1m["avg_excess"] is not None and h1m["avg_excess"] > 0.15
    assert h1m["vs_benchmark"] is True


def test_flag_fired_after_newest_bar_anchors_at_last_close(session):
    # A flag fired intraday (before today's bar prints) must anchor at the
    # most recent close, not be skipped forever.
    start = date.today() - timedelta(days=40)
    _seed_prices(session, "LATE", [50.0] * 20, start)  # bars end 20 days ago
    _seed_prices(session, "XBI", [100.0] * 20, start)
    session.add(FlagEvent(symbol="LATE", flag_type="volume_anomaly",
                          severity="warn", message="t", evidence={}))
    session.commit()
    assert evaluate_flag_outcomes(session) == 1
    from app.models import FlagOutcome
    out = session.exec(select(FlagOutcome)).one()
    assert out.price_at_fire == 50.0
    assert out.fired_on == start + timedelta(days=19)


def test_flag_outcome_incomplete_until_bars_exist(session):
    start = date.today() - timedelta(days=10)
    _seed_prices(session, "FRSH", [100.0] * 8, start)
    _seed_prices(session, "XBI", [100.0] * 8, start)
    flag = FlagEvent(symbol="FRSH", flag_type="volume_anomaly",
                     severity="warn", message="t", evidence={})
    session.add(flag)
    session.commit()
    evaluate_flag_outcomes(session)
    rec = flag_track_record(session)["by_flag_type"].get("volume_anomaly")
    # Fired is counted, but 1m/3m horizons have no graded rows yet.
    if rec is not None:
        assert rec["horizons"]["3m"]["n"] == 0


def test_track_record_reports_declared_basis(session):
    # With no benchmark data at all, stats must say basis=raw, not fake "vs XBI".
    start = date.today() - timedelta(days=120)
    _seed_prices(session, "NOBM", [100.0 + i for i in range(80)], start)
    flag = FlagEvent(symbol="NOBM", flag_type="volume_anomaly",
                     severity="warn", message="t", evidence={})
    flag.asof = flag.asof.replace(year=start.year, month=start.month, day=start.day)
    session.add(flag)
    session.commit()
    evaluate_flag_outcomes(session)
    h1m = flag_track_record(session)["by_flag_type"]["volume_anomaly"]["horizons"]["1m"]
    assert h1m["basis"] == "raw"
    assert h1m["vs_benchmark"] is False
    assert h1m["n"] == h1m["n_raw"] == 1
    assert h1m["n_excess"] == 0


def test_outcomes_group_analyst_clusters_by_direction(session):
    from app.scoring.outcomes import outcome_key

    assert outcome_key("analyst_revision_cluster", {"direction": "upward"}) == \
        "analyst_revision_cluster:upward"
    assert outcome_key("analyst_revision_cluster", {"direction": "downward"}) == \
        "analyst_revision_cluster:downward"
    assert outcome_key("volume_anomaly", {}) == "volume_anomaly"
    assert outcome_key("volume_anomaly", None) == "volume_anomaly"


# --- flag re-fire suppression -------------------------------------------------------

def test_opposite_direction_cluster_is_not_suppressed():
    # Suppression keys must include direction: a downward analyst cluster
    # fired 3 days ago must NOT suppress a fresh upward cluster.
    from app.scoring.outcomes import outcome_key

    down_key = ("CRSP", outcome_key("analyst_revision_cluster", {"direction": "downward"}))
    up_key = ("CRSP", outcome_key("analyst_revision_cluster", {"direction": "upward"}))
    assert down_key != up_key

def test_flags_do_not_refire_within_suppression_window(session):
    from app.scoring.engine import compute_scores

    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    start = date.today() - timedelta(days=120)
    # Persistent condition: low runway fires runway_cliff_approaching each run.
    for i in range(100):
        session.add(PriceBar(symbol="CRSP", date=start + timedelta(days=i),
                             open=100.0, high=101.0, low=99.0, close=100.0, volume=1e6))
    from app.models import Fundamental
    session.add(Fundamental(symbol="CRSP", asof=date.today(), cash=10e6,
                            quarterly_burn=5e6, runway_quarters=2.0))
    session.commit()

    compute_scores(session)
    first = session.exec(select(FlagEvent)).all()
    compute_scores(session)  # immediate second run — same conditions
    second = session.exec(select(FlagEvent)).all()
    assert len(second) == len(first)  # suppressed, no duplicates
