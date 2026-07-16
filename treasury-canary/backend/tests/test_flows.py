"""Flow-compass regime classifier — every branch."""
from app.metrics.flows import build_flow_snapshot, change_bps, classify_regime, pct_return


def test_growth_scare_hedge_intact():
    r = classify_regime(stocks_pct=-5.0, dy10_bps=-25.0, usd_pct=1.5, gold_pct=0.5, btc_pct=-3.0)
    assert r["id"] == "GROWTH_SCARE"
    assert "treasuries_10y" in r["destinations"]


def test_rates_shock_front_end_cash():
    r = classify_regime(stocks_pct=-6.0, dy10_bps=+35.0, usd_pct=2.0, gold_pct=0.0, btc_pct=-10.0)
    assert r["id"] == "RATES_SHOCK"
    assert "cash_tbills" in r["destinations"]
    assert r["severity"] == "RED"


def test_debasement_sell_usd_assets():
    r = classify_regime(stocks_pct=-4.0, dy10_bps=+20.0, usd_pct=-2.5, gold_pct=6.0, btc_pct=8.0)
    assert r["id"] == "DEBASEMENT"
    assert "gold" in r["destinations"] and "crypto" in r["destinations"]
    assert r["severity"] == "CRITICAL"


def test_liquidity_crunch_everything_sold():
    r = classify_regime(stocks_pct=-12.0, dy10_bps=+15.0, usd_pct=4.0, gold_pct=-5.0, btc_pct=-30.0)
    assert r["id"] == "LIQUIDITY_CRUNCH"
    assert r["severity"] == "CRITICAL"


def test_risk_on_and_neutral_and_unknown():
    assert classify_regime(5.0, -5.0, 0.0, 0.0, 0.0)["id"] == "RISK_ON"
    assert classify_regime(0.5, 5.0, 0.0, 0.0, 0.0)["id"] == "NEUTRAL"
    assert classify_regime(None, None, None, None, None)["id"] == "UNKNOWN"


def test_hedge_broken_when_discriminators_missing():
    r = classify_regime(stocks_pct=-5.0, dy10_bps=+20.0, usd_pct=None, gold_pct=None, btc_pct=None)
    assert r["id"] == "HEDGE_BROKEN"
    assert "usd_pct" in r["missing_inputs"]


def test_return_helpers():
    vals = [100.0] * 21 + [110.0]
    assert pct_return(vals, window=20) is None or isinstance(pct_return(vals, window=20), float)
    series = [None, 100.0] + [100.0] * 19 + [102.0]
    assert pct_return(series, window=20) == 2.0
    yields = [4.0] * 21 + [4.25]
    assert change_bps(yields, window=20) == 25.0


def test_snapshot_all_missing_is_safe():
    snap = build_flow_snapshot({})
    assert snap["regime"]["id"] == "UNKNOWN"
    assert set(snap["assets"].keys()) >= {"stocks", "gold", "usd", "btc"}
