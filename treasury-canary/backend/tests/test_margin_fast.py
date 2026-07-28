from datetime import date, timedelta
from unittest.mock import patch

from app.api.routes_margin_fast import (
    FAST_PLAYBOOK, _z_series, fast_state, margin_fast,
)
from app.sources.cftc import parse_emini_pct_oi


def test_parse_emini_pct_oi():
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-07-21T00:00:00.000",
         "lev_money_positions_long": "146834",
         "lev_money_positions_short": "469699",
         "open_interest_all": "1939493"},
        {"report_date_as_yyyy_mm_dd": "2026-07-14T00:00:00.000",
         "lev_money_positions_long": "100",
         "lev_money_positions_short": "50",
         "open_interest_all": "0"},          # zero OI -> dropped
        {"report_date_as_yyyy_mm_dd": "bad-date",
         "lev_money_positions_long": "1", "lev_money_positions_short": "1",
         "open_interest_all": "10"},          # unparseable -> dropped
    ]
    d, v = parse_emini_pct_oi(rows)
    assert d == [date(2026, 7, 21)]
    assert round(v[0], 1) == -16.6            # structurally net short, as % of OI


def test_z_series_warmup_and_value():
    vals = [0.0] * 51
    z = _z_series(vals, window=156, min_n=52)
    assert all(x is None for x in z)          # below min_n -> no z yet
    vals = [0.0] * 60 + [10.0]
    z = _z_series(vals, window=156, min_n=52)
    assert z[50] is None and z[51] is not None
    assert z[-1] > 3.0                        # a 10-sigma-ish outlier scores high


def test_fast_state_pre_registered_rules():
    # order: FLUSH beats WASHED_OUT beats RISK_BUILD beats CALM
    assert fast_state(None, -1.0, 9.0) is None
    assert fast_state(-2.0, -1.0, 9.0) == "FLUSH"        # both flush legs met
    assert fast_state(-1.5, 0.2, -1.0) == "WASHED_OUT"   # flushed z, calm vol
    assert fast_state(-1.5, 0.2, 3.0) == "CALM"          # z low but vix20 > 0
    assert fast_state(1.4, 0.3, 2.0) == "RISK_BUILD"
    assert fast_state(1.4, 0.3, 6.0) == "CALM"           # vol already moving
    assert fast_state(0.0, 0.0, 0.0) == "CALM"
    for s in ("FLUSH", "WASHED_OUT", "RISK_BUILD", "CALM"):
        pb = FAST_PLAYBOOK[s]
        assert pb["stats"]["fwd12m"]["n"] > 0 and pb["action"]


def test_margin_fast_endpoint_shape():
    # 60 weeks of COT (flat then a plunge), 300 days of VIX & HY
    weeks = [date(2024, 1, 2) + timedelta(weeks=i) for i in range(60)]
    # noisy base (sd ~2) then a 5-week plunge: dz4 << -0.5 with a sane z scale
    cot_vals = ([-10.0 + (2.0 if i % 2 else -2.0) for i in range(55)]
                + [-13.0, -16.0, -19.0, -22.0, -25.0])
    days = [date(2025, 6, 1) + timedelta(days=i) for i in range(300)]
    bundle = {
        "vix": (days, [15.0] * 280 + [15.0 + i for i in range(20)]),  # spiking
        "hy_oas": (days, [3.0] * 300),                                # % -> 300bp
    }
    perp = {"mark_price": 63000.0, "oi_usd": 7.2e8, "funding_8h": -1e-4,
            "funding_ann_pct": -10.95}
    with patch("app.api.routes_margin_fast.fetch_bundle", return_value=bundle), \
         patch("app.api.routes_margin_fast.fetch_emini_leveraged",
               return_value=(weeks, cot_vals)), \
         patch("app.api.routes_margin_fast.fetch_btc_perp", return_value=perp), \
         patch("app.api.routes_margin_fast.fetch_funding_history",
               return_value=([date(2026, 7, 27)], [-10.95])), \
         patch("app.api.routes_margin_fast._persist_oi_snapshot",
               return_value=[{"date": "2026-07-28", "oi_usd": 7.2e8}]):
        r = margin_fast()
    # plunging positioning + spiking vol -> FLUSH under pre-registered rules
    assert r["state"] == "FLUSH"
    assert r["cot"]["z"] is not None and r["cot"]["dz4"] < -0.5
    assert r["vix"]["d20"] >= 8
    assert r["hy"]["current_bp"] == 300
    assert r["btc"]["perp"]["funding_ann_pct"] < 0
    assert r["cross_read"]["FLUSH"]["BLOWOFF"]
    assert r["relationship"] and r["playbook"]["WASHED_OUT"]["stats"]["fwd12m"]["pct_pos"] == 95


def test_margin_fast_endpoint_degrades_when_sources_missing():
    with patch("app.api.routes_margin_fast.fetch_bundle", return_value={}), \
         patch("app.api.routes_margin_fast.fetch_emini_leveraged",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast.fetch_btc_perp", return_value=None), \
         patch("app.api.routes_margin_fast.fetch_funding_history",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast._persist_oi_snapshot", return_value=[]):
        r = margin_fast()
    assert r["state"] is None
    assert r["cot"]["z"] is None and r["vix"]["d20"] is None
    assert r["btc"]["perp"] is None
