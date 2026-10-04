"""Gates for the monthly carry review (carry_review.py). No network: venue
data is built here; fetch_all runs against a fake `post`."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import carry_review as R  # noqa: E402

H = R.HOUR_MS
T0 = R.CARRY_START_MS
PAIR = "@151"


def fill(t, coin, side, sz, px, fee, tok, start=None):
    return {"time": t, "coin": coin, "side": side, "sz": str(sz), "px": str(px),
            "fee": str(fee), "feeToken": tok,
            "startPosition": None if start is None else str(start)}


def candles(t_from, t_to, f, iv=H):
    out, t = [], (t_from // iv) * iv
    while t + iv <= t_to:
        out.append({"t": t, "T": t + iv - 1, "o": str(f(t)), "c": str(f(t + iv)),
                    "h": "0", "l": "0", "v": "0", "n": 1})
        t += iv
    return out


def funding_row(t, szi, rate, px):
    return {"time": t, "delta": {"type": "funding", "coin": "ETH",
                                 "usdc": str(-szi * px * rate), "szi": str(szi),
                                 "fundingRate": str(rate), "nSamples": None}}


def venue(fills, funding, now, spot_f, perp_f, spot_qty=None, szi=None, liq=None,
          rates=None, cash=0.04, eng=None):
    rp = R.replay(fills, PAIR)
    b = rp.at(now)
    return R.VenueData(
        fills=fills, funding=funding, rates=rates or [],
        perp_h=candles(T0 - 2 * 24 * H, now, perp_f), perp_d=candles(T0 - 5 * 24 * H, now, perp_f, 24 * H),
        spot_h=candles(T0 - 2 * 24 * H, now, spot_f), spot_d=candles(T0 - 5 * 24 * H, now, spot_f, 24 * H),
        spot_pair=PAIR,
        snap_spot_qty=b.s_net if spot_qty is None else spot_qty,
        snap_perp_szi=b.perp if szi is None else szi,
        liq_px=liq, perp_mid=perp_f(now), spot_mid=spot_f(now),
        engine_funding=eng or {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 10.0}}},
        cash_apy=cash, now_ms=now, chart_from_ms=T0 - 10 * 24 * H)


# the sleeve's real opening fills, 2026-10-04
REAL = [
    fill(T0 + 111_000, PAIR, "B", 7.8752, 2703.7, 0.005292134, "UETH", 0.0),
    fill(T0 + 111_000, PAIR, "B", 3.2209, 2703.7, 0.002164444, "UETH", 7.869907866),
    fill(T0 + 112_000, "ETH", "A", 2.6701, 2703.9, 3.118903, "USDC", 0.0),
    fill(T0 + 112_000, "ETH", "A", 3.6619, 2703.9, 4.277409, "USDC", -2.6701),
    fill(T0 + 112_000, "ETH", "A", 4.7566, 2703.9, 5.556112, "USDC", -6.332),
    fill(T0 + 414_000, PAIR, "B", 0.0074, 2704.3, 0.000004972, "UETH", 11.088643422),
    fill(T0 + 415_000, "ETH", "A", 0.0074, 2704.3, 0.008645, "USDC", -11.0886),
]


def test_replay_reproduces_the_venue_holdings_from_real_fills():
    rp = R.replay(REAL, PAIR)
    b = rp.at(T0 + 10 * H)
    assert b.s_net == pytest.approx(11.09603845, abs=1e-9)   # venue UETH total
    assert b.perp == pytest.approx(-11.096, abs=1e-9)        # venue szi
    assert b.fee_ueth == pytest.approx(0.00746155, abs=1e-12)
    assert b.fees_usdc == pytest.approx(3.118903 + 4.277409 + 5.556112 + 0.008645)
    assert rp.flags == []                                    # startPosition chain agrees
    assert len(rp.passes) == 2                               # open pass + top-up pass


def test_value_splits_price_and_fees_by_hand():
    rp = R.replay(REAL, PAIR)
    b = rp.at(T0 + H)
    m = R.value(b, spot_px=2800.0, perp_px=2810.0)
    spot_cost = 11.0961 * 2703.7 + 0.0074 * 2704.3
    perp_proceeds = 11.0886 * 2703.9 + 0.0074 * 2704.3
    price = (11.1035 * 2800.0 - spot_cost) + (perp_proceeds - 11.096 * 2810.0)
    assert m["price"] == pytest.approx(price, abs=1e-6)
    assert m["fees"] == pytest.approx(b.fees_usdc + 0.00746155 * 2800.0, abs=1e-6)
    # the identity the report relies on: net UETH x px - cash = price - UETH fees
    assert b.s_net * 2800.0 + b.spot_cash == pytest.approx(
        b.s_gross * 2800.0 + b.spot_cash - b.fee_ueth * 2800.0)


def round_trip(close_at, p_open=2000.0, p_close=2100.0, basis=0.0):
    """Open 10 UETH / -10 ETH at p_open, close at p_close; spot fee 0.01 UETH
    on the buy, $2 USDC on the sell, perp fees $5 per side."""
    return [
        fill(T0 + 60_000, PAIR, "B", 10.0, p_open, 0.01, "UETH", 0.0),
        fill(T0 + 62_000, "ETH", "A", 9.99, p_open + basis, 5.0, "USDC", 0.0),
        fill(close_at, PAIR, "A", 9.99, p_close, 2.0, "USDC", 9.99),
        fill(close_at + 2_000, "ETH", "B", 9.99, p_close, 5.0, "USDC", -9.99),
    ]


def test_round_trip_total_is_funding_minus_fees_plus_basis():
    close = T0 + 50 * H + 30 * 60_000
    fills = round_trip(close, basis=1.0)                    # shorted $1 above spot buy
    fund = [funding_row(T0 + h * H, -9.99, 0.0000125, 2050.0) for h in range(1, 51)]
    now = T0 + 60 * H
    v = venue(fills, fund, now, lambda t: 2100.0, lambda t: 2100.0)
    rp = R.replay(fills, PAIR)
    w = R.window(v, rp, T0, now, "ltd")
    funding = sum(float(r["delta"]["usdc"]) for r in fund)
    fees = 5.0 + 5.0 + 2.0 + 0.01 * 2100.0                  # UETH fee marked at 2100
    # spot: bought 10 @2000, sold 9.99 @2100 -> 0.01 UETH left = the fee; perp:
    # short 9.99 @2001, bought back @2100
    price = (0.01 * 2100.0 - 20000.0 + 9.99 * 2100.0) + (9.99 * 2001.0 - 9.99 * 2100.0)
    assert w["funding_usd"] == pytest.approx(round(funding, 2), abs=0.01)
    assert w["fees_usd"] == pytest.approx(fees, abs=0.01)
    assert w["price_usd"] == pytest.approx(round(price, 2), abs=0.01)
    assert w["total_usd"] == pytest.approx(round(funding - fees + price, 2), abs=0.02)
    assert (w["opens"], w["closes"]) == (1, 1)
    assert w["on_hours"] == 50


def test_month_windows_add_up_to_inception_to_date():
    """Additivity: the books are marked at each boundary, so two adjacent
    windows must sum to the window that spans both."""
    fills = REAL
    now = T0 + 40 * 24 * H
    fund = [funding_row(T0 + h * H, -11.096, 0.0000125 + (h % 7) * 1e-6, 2700.0)
            for h in range(1, int((now - T0) / H))]
    import math
    v = venue(fills, fund, now, lambda t: 2700 + 50 * math.sin(t / 7e7),
              lambda t: 2701 + 50 * math.sin(t / 7e7))
    rp = R.replay(fills, PAIR)
    mid = T0 + 20 * 24 * H + 17 * 60_000
    a, b = R.window(v, rp, T0, mid, "a"), R.window(v, rp, mid, now, "b")
    ab = R.window(v, rp, T0, now, "ab")
    for k in ("funding_usd", "fees_usd", "price_usd", "total_usd"):
        assert a[k] + b[k] == pytest.approx(ab[k], abs=0.03), k
    assert a["on_hours"] + b["on_hours"] == ab["on_hours"]


def test_dust_after_a_close_does_not_count_as_open():
    b = R.Book(s_gross=10.0, fee_ueth=0.0, perp=0.0)
    assert R.is_on(b, 2000.0)
    b = R.Book(s_gross=0.004, perp=0.0)                    # $8 of UETH dust
    assert not R.is_on(b, 2000.0)


def test_pre_existing_inventory_is_seeded_and_flagged():
    fills = [fill(T0 + 60_000, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 0.5)]
    rp = R.replay(fills, PAIR)
    assert rp.at(T0 + H).s_net == pytest.approx(1.499)
    assert any("held before the first sleeve fill" in f for f in rp.flags)


def test_a_fill_the_replay_missed_is_flagged():
    fills = [fill(T0 + 60_000, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 0.0),
             fill(T0 + 9 * H, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 1.5)]  # venue had 1.5
    rp = R.replay(fills, PAIR)
    assert any("spot replay drift" in f for f in rp.flags)


def test_integrity_catches_venue_mismatch_and_missing_funding():
    now = T0 + 20 * H
    fund = [funding_row(T0 + h * H, -11.096, 0.0000125, 2700.0)
            for h in range(1, 20) if h not in (5, 6, 7)]
    v = venue(REAL, fund, now, lambda t: 2700.0, lambda t: 2700.0, spot_qty=11.5)
    flags = R.integrity(v, R.replay(REAL, PAIR))
    assert any("!= venue" in f for f in flags)
    assert any("carry no funding payment" in f for f in flags)
    v2 = venue(REAL, [funding_row(T0 + h * H, -11.096, 0.0000125, 2700.0)
                      for h in range(1, 20)], now, lambda t: 2700.0, lambda t: 2700.0)
    assert R.integrity(v2, R.replay(REAL, PAIR)) == []


def test_paginate_never_drops_or_doubles_rows_at_a_page_edge():
    rows = [{"time": t, "k": i} for i, t in enumerate([1, 2, 3, 3, 4, 5, 6, 6, 7, 8])]

    def page(s, e, cap=3):
        return [r for r in rows if s <= r["time"] <= e][:cap]
    out = R.paginate(lambda s, e: page(s, e), 0, 100, 3)
    assert sorted(r["k"] for r in out) == list(range(len(rows)))


def test_paginate_refuses_a_full_page_of_one_timestamp():
    rows = [{"time": 5, "k": i} for i in range(4)]
    with pytest.raises(R.FetchError, match="share timestamp"):
        R.paginate(lambda s, e: [r for r in rows if r["time"] >= s][:3], 5, 100, 3)


def test_paginate_rejects_a_non_list_page():
    with pytest.raises(R.FetchError):
        R.paginate(lambda s, e: None, 0, 10, 5)


def test_daily_candles_mark_boundaries_older_than_the_hourly_history():
    now = T0 + 300 * 24 * H
    v = venue(REAL, [], now, lambda t: 1000.0 + t / 1e9, lambda t: 1000.0 + t / 1e9)
    v.perp_h = [c for c in v.perp_h if c["t"] >= now - 5000 * H]   # venue keeps 5000
    t = T0 + 3 * 24 * H
    assert v.px("perp", t) == pytest.approx(R.price_at(v.perp_d, t))
    assert v.px("perp", now) == v.perp_mid


def test_proposals_fire_on_their_rules_and_only_propose():
    now = T0 + 70 * 24 * H
    v = venue(REAL, [], now, lambda t: 2700.0, lambda t: 2700.0, liq=3500.0,
              eng={"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 5.6}}})
    low = {"empty": False, "net_yield_ann_pct": 2.0, "opens": 2, "closes": 2,
           "uptime_pct": 40.0, "funding_usd": 100.0, "price_usd": -80.0,
           "expected_funding_usd": 150.0}
    kinds = [k for k, _ in R.proposals(low, dict(low), low, v, [])]
    text = " ".join(t for _, t in R.proposals(low, dict(low), low, v, []))
    assert kinds.count("PROPOSE") == 3          # below cash x2, flapping, liq 30%
    assert "INVESTIGATE" in kinds                # price drag + funding mismatch
    assert "NOTE" in kinds and "OFF line" in text
    clean = {"empty": False, "net_yield_ann_pct": 9.0, "opens": 0, "closes": 0,
             "uptime_pct": 100.0, "funding_usd": 200.0, "price_usd": 5.0,
             "expected_funding_usd": 201.0}
    v.liq_px = 8800.0
    v.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 10.0}}}
    assert [k for k, _ in R.proposals(clean, dict(clean), clean, v, [])] == ["CANDIDATE"]
    assert [k for k, _ in R.proposals(clean, None, clean, v, [])] == ["NONE"]
    assert R.proposals(clean, None, clean, v, ["x"])[0][0] == "INVESTIGATE"


def test_build_markdown_and_chart_end_to_end(tmp_path):
    now = T0 + 30 * 24 * H
    fund = [funding_row(T0 + h * H, -11.096, 0.0000125, 2700.0)
            for h in range(1, int((now - T0) / H) + 1)]
    rates = [{"coin": "ETH", "fundingRate": "0.0000125", "premium": "0",
              "time": T0 - 40 * 24 * H + h * H} for h in range(70 * 24)]
    v = venue(REAL, fund, now, lambda t: 2700.0, lambda t: 2701.0, liq=8800.0,
              rates=rates)
    r = R.build(v, R.ym_of(now))
    rp = r.pop("_replay")
    assert r["integrity_flags"] == []
    md = R.markdown(r)
    assert "Integrity: CLEAN" in md and "Proposals" in md and "Honesty box" in md
    json.dumps(r)                                            # serialisable
    png = tmp_path / "c.png"
    R.chart(v, rp, R.series(v, rp), str(png), "t")
    assert png.stat().st_size > 10_000


def test_fetch_all_filters_coins_and_refuses_a_null_snapshot():
    fills = REAL + [fill(T0 + 70_000, "BTC", "B", 0.01, 80000, 1, "USDC", 0)]
    meta = {"tokens": [{"name": "USDC", "index": 0}, {"name": "UETH", "index": 221}],
            "universe": [{"name": "@151", "tokens": [221, 0], "index": 151}]}
    now = T0 + 5 * H

    def post(body, snap_null=False):
        t = body["type"]
        if t == "spotMeta":
            return meta
        if t == "userFillsByTime":
            return [f for f in fills if body["startTime"] <= f["time"] <= body["endTime"]]
        if t == "userFunding":
            return [funding_row(T0 + H, -11.096, 0.0000125, 2700.0),
                    {"time": T0 + H, "delta": {"coin": "BTC", "usdc": "-1", "szi": "0.03",
                                               "fundingRate": "0.00001"}}]
        if t in ("fundingHistory", "candleSnapshot"):
            return []
        if t == "clearinghouseState":
            return None if snap_null else {"assetPositions": [{"position": {
                "coin": "ETH", "szi": "-11.096", "liquidationPx": "8847.4"}}]}
        if t == "spotClearinghouseState":
            return {"balances": [{"coin": "UETH", "total": "11.09603845"}]}
        if t == "allMids":
            return {"ETH": "2705", "@151": "2704"}
        raise AssertionError(t)

    def get(url):
        return {"venues": {}} if url.endswith("/funding") else {"cash_apy": 0.04}
    v = R.fetch_all(now, T0, post=post, get=get)
    assert {f["coin"] for f in v.fills} == {"ETH", PAIR}
    assert len(v.funding) == 1 and v.liq_px == pytest.approx(8847.4)
    assert v.cash_apy == 0.04

    def post_null(body):
        return post(body, snap_null=True)
    with pytest.raises(R.FetchError):
        R.fetch_all(now, T0, post=post_null, get=get)


def test_uptime_counts_hour_marks_and_short_windows_are_not_annualised():
    now = T0 + 20 * 60_000                                  # 20 minutes after start
    v = venue(REAL, [funding_row(T0 + 13 * 60_000, -11.096, 0.0000125, 2700.0)],
              now, lambda t: 2700.0, lambda t: 2700.0)
    w = R.window(v, R.replay(REAL, PAIR), T0, now, "x")
    assert w["uptime_pct"] <= 100.0
    assert w["net_yield_ann_pct"] is None and w["funding_yield_ann_pct"] is None
    now = T0 + 10 * 24 * H                                  # 10 days, every hour paid
    fund = [funding_row(((T0 // H) + h) * H + 3, -11.096, 0.0000125, 2700.0)
            for h in range(1, 10 * 24 + 1)]
    v = venue(REAL, fund, now, lambda t: 2700.0, lambda t: 2700.0)
    w = R.window(v, R.replay(REAL, PAIR), T0, now, "x")
    assert w["uptime_pct"] == pytest.approx(100.0, abs=0.5)
    assert w["funding_yield_ann_pct"] == pytest.approx(0.0000125 * 8760 * 100, rel=0.01)


def test_end_labels_are_spread_apart_in_order():
    out = R.spread([0.37, -1.12, -33.12, -33.87], 2.5)
    srt = sorted(out)
    assert all(b - a >= 2.5 - 1e-9 for a, b in zip(srt, srt[1:]))
    assert out[0] > out[1] > out[2] > out[3]                # order kept
    assert R._money(-33.87) == "-$33.87" and R._money(0.37) == "$0.37"
