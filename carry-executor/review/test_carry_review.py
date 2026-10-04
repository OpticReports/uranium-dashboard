"""Gates for the monthly carry review (carry_review.py). No network: venue
data is built here in the venue's own formats (hourly funding rows a few ms
after the mark; MERGED daily rows for days older than ~8 days); fetch_all
and main run against fakes."""
from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import carry_review as R  # noqa: E402

H = R.HOUR_MS
D = R.DAY_MS
T0 = R.CARRY_START_MS                     # 2026-10-04 16:47Z
PAIR = "@151"
RATE = 0.0000125                          # 10.95%/yr, HL's baseline hourly rate


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


def first_mark_after(t):
    return -(-(t + 1) // H) * H


def hourly_funding(rp, perp_f, t_from, t_to, rate=RATE, skip=()):
    """The venue's hourly rows: one per held mark, ~17 ms after it, paid on
    the size held just before the mark at that mark's price."""
    rows, m = [], first_mark_after(t_from)
    while m <= t_to:
        p = rp.at(m - 1).perp
        if abs(p) > R.MIN_QTY and m not in skip:
            rows.append({"time": m + 17, "hash": "0x0", "delta": {
                "type": "funding", "coin": "ETH", "usdc": str(-p * perp_f(m) * rate),
                "szi": str(p), "fundingRate": str(rate), "nSamples": None}})
        m += H
    return rows


def merge_days(rows, older_than):
    """What the venue does to rows older than ~8 days: one row per UTC day,
    stamped D 00:00:00.000, nSamples = hours paid, usdc = the day's sum."""
    days, keep = {}, []
    for r in rows:
        if r["time"] >= older_than:
            keep.append(r)
            continue
        d = (r["time"] // D) * D
        x = days.setdefault(d, {"usdc": 0.0, "n": 0, "szi": 0.0})
        x["usdc"] += float(r["delta"]["usdc"])
        x["n"] += 1
        x["szi"] += float(r["delta"]["szi"])
    merged = [{"time": d, "hash": "0x0", "delta": {
        "type": "funding", "coin": "ETH", "usdc": str(x["usdc"]), "szi": str(x["szi"] / x["n"]),
        "fundingRate": str(RATE), "nSamples": x["n"]}} for d, x in sorted(days.items())]
    return merged + keep


def rate_rows(t_from, t_to, rate=RATE):
    out, m = [], (t_from // H) * H
    while m <= t_to:
        out.append({"coin": "ETH", "fundingRate": str(rate), "premium": "0", "time": m + 30})
        m += H
    return out


def venue(fills, funding, now, spot_f, perp_f, spot_qty=None, szi=None, liq=None,
          rates=None, cash=0.04, eng=None, cum=None):
    rp = R.replay(fills, PAIR)
    b = rp.at(now)
    return R.VenueData(
        fills=fills, funding=funding,
        rates=rate_rows(T0 - 40 * D, now) if rates is None else rates,
        perp_h=candles(T0 - 2 * D, now, perp_f), perp_d=candles(T0 - 5 * D, now, perp_f, D),
        spot_h=candles(T0 - 2 * D, now, spot_f), spot_d=candles(T0 - 5 * D, now, spot_f, D),
        spot_pair=PAIR,
        snap_spot_qty=b.s_net if spot_qty is None else spot_qty,
        snap_perp_szi=b.perp if szi is None else szi,
        liq_px=liq, perp_mid=perp_f(now), spot_mid=spot_f(now),
        engine_funding={"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 10.0}}}
        if eng is None else eng,
        cash_apy=cash, now_ms=now, chart_from_ms=T0 - 10 * D, cum_since_open=cum)


def flat(px):
    return lambda t: px


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
RP_REAL = R.replay(REAL, PAIR)


# ------------------------------------------------------------------ replay

def test_replay_reproduces_the_venue_holdings_from_real_fills():
    b = RP_REAL.at(T0 + 10 * H)
    assert b.s_net == pytest.approx(11.09603845, abs=1e-9)   # venue UETH total
    assert b.perp == pytest.approx(-11.096, abs=1e-9)        # venue szi
    assert b.fee_ueth == pytest.approx(0.00746155, abs=1e-12)
    assert b.fee_spot_usd == pytest.approx(0.007456578 * 2703.7 + 0.000004972 * 2704.3)
    assert b.fees_usdc == pytest.approx(3.118903 + 4.277409 + 5.556112 + 0.008645)
    assert RP_REAL.flags == []                               # startPosition chain agrees
    assert len(RP_REAL.passes) == 2                          # open pass + top-up pass
    assert RP_REAL.perp_open_ms() == T0 + 112_000


def test_value_books_fees_at_fill_price_and_marks_what_is_held():
    b = RP_REAL.at(T0 + H)
    m = R.value(b, spot_px=2800.0, perp_px=2810.0)
    spot_cost = 11.0961 * 2703.7 + 0.0074 * 2704.3
    perp_proceeds = 11.0886 * 2703.9 + 0.0074 * 2704.3
    fee_spot_usd = 0.007456578 * 2703.7 + 0.000004972 * 2704.3
    assert m["fees"] == pytest.approx(b.fees_usdc + fee_spot_usd, abs=1e-9)
    price = (11.09603845 * 2800.0 - spot_cost + fee_spot_usd) + (perp_proceeds - 11.096 * 2810.0)
    assert m["price"] == pytest.approx(price, abs=1e-6)
    # the total is what the account actually has: UETH held + cash moved + short
    total = 11.09603845 * 2800.0 - spot_cost + (perp_proceeds - 11.096 * 2810.0) - b.fees_usdc
    assert m["price"] - m["fees"] == pytest.approx(total, abs=1e-6)


def test_a_month_with_no_fills_has_no_fees():
    now = T0 + 70 * D
    v = venue(REAL, [], now, lambda t: 2700 + t / 1e8, lambda t: 2700 + t / 1e8)
    a, b = R.month_bounds("2026-11")
    w = R.window(v, RP_REAL, a, b, "2026-11")
    assert w["fees_usd"] == 0.0


def test_pre_existing_inventory_is_seeded_and_flagged():
    fills = [fill(T0 + 60_000, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 0.5)]
    rp = R.replay(fills, PAIR)
    assert rp.at(T0 + H).s_net == pytest.approx(1.499)
    assert any("held before the first sleeve fill" in f for f in rp.flags)


def test_a_fill_the_replay_missed_is_flagged():
    fills = [fill(T0 + 60_000, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 0.0),
             fill(T0 + 9 * H, PAIR, "B", 1.0, 2000.0, 0.001, "UETH", 1.5)]  # venue had 1.5
    assert any("spot replay drift" in f for f in R.replay(fills, PAIR).flags)


# ------------------------------------------------------------------ prices

def test_price_at_uses_the_last_closed_candle_never_a_future_one():
    cs = [{"t": k * H, "T": (k + 1) * H - 1, "o": str(100 + k), "c": str(200 + k)}
          for k in range(10, 15)]
    assert R.price_at(cs, 13 * H) == 212.0          # boundary: candle 12 closed, 13 open
    assert R.price_at(cs, 13 * H - 1) == 212.0      # exactly at candle 12's close
    assert R.price_at(cs, 13 * H - 2) == 211.0
    assert R.price_at(cs, 5 * H) == 110.0           # before every close: first open
    assert R.price_at(cs, 99 * H) == 214.0


def test_daily_candles_mark_boundaries_older_than_the_hourly_history():
    now = T0 + 300 * D
    v = venue(REAL, [], now, lambda t: 1000.0 + t / 1e9, lambda t: 1000.0 + t / 1e9)
    v.perp_h = [c for c in v.perp_h if c["t"] >= now - 5000 * H]   # venue keeps 5000
    t = T0 + 3 * D
    assert v.px("perp", t) == pytest.approx(R.price_at(v.perp_d, t))
    assert v.px("perp", now) == v.perp_mid


def test_clean_candles_drops_the_in_progress_candle_and_duplicates():
    now = 10 * H + 5
    cs = [{"t": 9 * H, "T": 10 * H - 1, "c": "1"}, {"t": 10 * H, "T": 11 * H - 1, "c": "2"},
          {"t": 9 * H, "T": 10 * H - 1, "c": "1"}]
    assert R.clean_candles(cs, now) == [{"t": 9 * H, "T": 10 * H - 1, "c": "1"}]


# ------------------------------------------------------------------ windows

def round_trip(close_at, p_open=2000.0, basis=1.0, p_close=2100.0):
    """Open 10 UETH / -9.99 ETH, close both at p_close. Spot buy fee 0.01 UETH,
    spot sell fee $2 USDC, perp fees $5 per side."""
    return [
        fill(T0 + 60_000, PAIR, "B", 10.0, p_open, 0.01, "UETH", 0.0),
        fill(T0 + 62_000, "ETH", "A", 9.99, p_open + basis, 5.0, "USDC", 0.0),
        fill(close_at, PAIR, "A", 9.99, p_close, 2.0, "USDC", 9.99),
        fill(close_at + 2_000, "ETH", "B", 9.99, p_close, 5.0, "USDC", -9.99),
    ]


def test_round_trip_total_is_funding_minus_fees_plus_basis():
    close = T0 + 50 * H + 30 * 60_000
    fills = round_trip(close)
    rp = R.replay(fills, PAIR)
    now = T0 + 60 * H
    fund = hourly_funding(rp, flat(2050.0), T0, now)
    v = venue(fills, fund, now, flat(2100.0), flat(2050.0))
    v.perp_mid = v.spot_mid = 2100.0
    w = R.window(v, rp, T0, now, "ltd")
    funding = sum(float(r["delta"]["usdc"]) for r in fund)
    fees = 5.0 + 5.0 + 2.0 + 0.01 * 2000.0              # UETH fee at its fill price
    price = (0.0 * 2100 - 20000.0 + 9.99 * 2100.0 + 0.01 * 2000.0) \
        + (9.99 * 2001.0 - 9.99 * 2100.0)
    assert w["funding_usd"] == pytest.approx(funding, abs=0.01)
    assert w["fees_usd"] == pytest.approx(fees, abs=0.01)
    assert w["price_usd"] == pytest.approx(price, abs=0.01)
    assert w["total_usd"] == pytest.approx(funding - fees + price, abs=0.02)
    assert (w["opens"], w["closes"]) == (1, 1)
    assert w["on_hours"] == len(fund) == 51             # 17:00 d0 .. 19:00 d2
    # same price and rate as the payments: expected must equal received
    assert w["expected_funding_usd"] == pytest.approx(funding, abs=0.01)
    assert w["hours_without_rate"] == 0


def test_month_windows_add_up_to_inception_to_date():
    now = T0 + 40 * D

    def wave(t):
        return 2700 + 50 * math.sin(t / 7e7)
    fund = hourly_funding(RP_REAL, wave, T0, now)
    v = venue(REAL, fund, now, wave, lambda t: wave(t) + 1)
    nov = R.month_bounds("2026-11")[0]
    a = R.window(v, RP_REAL, T0, nov, "oct")
    b = R.window(v, RP_REAL, nov, now + 1, "nov")
    ab = R.window(v, RP_REAL, T0, now + 1, "ab")
    for k in ("funding_usd", "fees_usd", "price_usd", "total_usd", "expected_funding_usd"):
        assert a[k] + b[k] == pytest.approx(ab[k], abs=0.03), k
    assert a["on_hours"] + b["on_hours"] == ab["on_hours"]
    assert a["hour_marks"] + b["hour_marks"] == ab["hour_marks"]


def test_a_fully_open_month_reads_100_percent_across_its_boundaries():
    """Rows land ~17 ms after the mark: the Nov 1 00:00 payment is November's,
    the Dec 1 00:00 payment December's (booked at the mark, [t0, t1))."""
    now = T0 + 70 * D
    fund = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0))
    w = R.window(v, RP_REAL, *R.month_bounds("2026-11"), "2026-11")
    assert w["hour_marks"] == w["on_hours"] == 720
    assert w["uptime_pct"] == 100.0
    assert w["funding_usd"] == pytest.approx(720 * 11.096 * 2700.0 * RATE, abs=0.01)
    cur = R.window(v, RP_REAL, *R.month_bounds("2026-12"), "2026-12")
    assert cur["uptime_pct"] == 100.0


def test_merged_daily_rows_give_the_same_month_as_hourly_rows():
    """THE venue behaviour the first version missed: on 2026-11-01 everything
    older than ~8 days comes back as one row per day. Results must not move."""
    now = R.month_bounds("2026-11")[0] + 8 * H + 56 * 60_000      # 1 Nov 08:56Z
    hourly = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    merged = merge_days(hourly, now - 8 * D - 9 * H)
    assert merged[0]["time"] == (T0 // D) * D and merged[0]["delta"]["nSamples"] == 7
    rv = venue(REAL, hourly, now, flat(2700.0), flat(2700.0))
    mv = venue(REAL, merged, now, flat(2700.0), flat(2700.0))
    oct_h = R.window(rv, RP_REAL, *R.month_bounds("2026-10"), "oct")
    oct_m = R.window(mv, RP_REAL, *R.month_bounds("2026-10"), "oct")
    for k in ("funding_usd", "on_hours", "hour_marks", "uptime_pct", "expected_funding_usd",
              "total_usd", "funding_yield_ann_pct", "net_yield_ann_pct"):
        assert oct_m[k] == pytest.approx(oct_h[k], abs=0.01), k
    assert oct_m["uptime_pct"] == 100.0
    assert oct_m["funding_yield_ann_pct"] == pytest.approx(RATE * 8760 * 100, abs=0.01)
    assert R.integrity(mv, RP_REAL) == []
    assert "INVESTIGATE" not in [k for k, _ in R.proposals(oct_m, None, oct_m, mv, [])]
    # and the chart spreads a merged day back over its hours
    s_h, s_m = R.series(rv, RP_REAL), R.series(mv, RP_REAL)
    assert s_m["funding"][-1] == pytest.approx(s_h["funding"][-1], abs=0.01)
    assert max(abs(a - b) for a, b in zip(s_m["funding"], s_h["funding"])) < 0.05


def test_a_merged_row_fetched_from_mid_day_is_not_lost():
    """fetch_all asks from the start of the UTC day: a mid-day startTime
    drops the merged row of the sleeve's first day (live-verified)."""
    calls = []

    def post(body):
        t = body["type"]
        if t == "spotMeta":
            return {"tokens": [{"name": "USDC", "index": 0}, {"name": "UETH", "index": 221}],
                    "universe": [{"name": "@151", "tokens": [221, 0], "index": 151}]}
        if t == "userFunding":
            calls.append(body["startTime"])
            return []
        if t in ("userFillsByTime", "fundingHistory"):
            return []
        if t == "candleSnapshot":
            return candles(T0 - D, T0 + 3 * H, flat(1.0))
        if t == "clearinghouseState":
            return {"assetPositions": []}
        if t == "spotClearinghouseState":
            return {"balances": []}
        return {"ETH": "1", "@151": "1"}
    R.fetch_all(T0 + 3 * H, T0, post=post, get=lambda u: {})
    assert calls[0] == (T0 // D) * D


def test_uptime_counts_hour_marks_and_short_windows_are_not_annualised():
    now = T0 + 20 * 60_000                                  # 20 minutes in: one mark
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0))
    w = R.window(v, RP_REAL, T0, now + 1, "x")
    assert w["uptime_pct"] == 100.0 and w["hour_marks"] == 1
    assert w["net_yield_ann_pct"] is None and w["funding_yield_ann_pct"] is None


def test_dust_after_a_close_does_not_count_as_open():
    assert R.is_on(R.Book(s_gross=10.0), 2000.0)
    assert not R.is_on(R.Book(s_gross=0.004), 2000.0)       # $8 of UETH dust


# ------------------------------------------------------------------ integrity

def test_integrity_is_clean_on_a_matching_venue():
    now = T0 + 20 * H
    fund = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    cum = -sum(float(r["delta"]["usdc"]) for r in fund)
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0), cum=cum)
    assert R.integrity(v, RP_REAL) == []


def test_integrity_catches_each_kind_of_mismatch():
    now = T0 + 20 * H
    fund = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0), spot_qty=11.5)
    assert any(f"replayed {R.SPOT_TOKEN}" in f for f in R.integrity(v, RP_REAL))
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0), szi=-8.0)
    assert any("replayed ETH perp" in f for f in R.integrity(v, RP_REAL))
    gone = first_mark_after(T0) + 5 * H                     # 22:00 on day one
    v = venue(REAL, [r for r in fund if r["time"] // H * H != gone], now,
              flat(2700.0), flat(2700.0))
    assert any("held 7 h, paid 6" in f for f in R.integrity(v, RP_REAL))   # even ONE hour
    dup = fund + [{"time": first_mark_after(T0) + 40, "delta": {   # one hour paid twice
        "coin": "ETH", "usdc": "1", "szi": "-1", "fundingRate": "0.00001", "nSamples": None}}]
    v = venue(REAL, dup, now, flat(2700.0), flat(2700.0))
    assert any("paid 8" in f for f in R.integrity(v, RP_REAL))
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0), cum=-999.0)
    assert any("cumFunding.sinceOpen" in f for f in R.integrity(v, RP_REAL))


def test_a_run_seconds_after_the_hour_is_not_a_missing_payment():
    m = first_mark_after(T0) + 10 * H
    now = m + 500                                           # row for mark m not out yet
    fund = [r for r in hourly_funding(RP_REAL, flat(2700.0), T0, now) if r["time"] < m]
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0))
    assert R.integrity(v, RP_REAL) == []


# ------------------------------------------------------------------ proposals

def _m(**kw):
    base = {"empty": False, "net_yield_ann_pct": 9.0, "funding_yield_ann_pct": 9.5,
            "fees_usd": 0.0, "opens": 0, "closes": 0,
            "uptime_pct": 100.0, "funding_usd": 200.0, "price_usd": 5.0,
            "expected_funding_usd": 200.5}
    base.update(kw)
    return base


def _kinds(month, prev, v, flags=()):
    return [k for k, _ in R.proposals(month, prev, month, v, list(flags))]


@pytest.fixture
def pv():
    return venue(REAL, [], T0 + 70 * D, flat(2700.0), flat(2700.0), liq=8800.0)


def test_each_proposal_rule_fires_alone_at_its_threshold(pv):
    assert _kinds(_m(), None, pv) == ["NONE"]
    low = _m(net_yield_ann_pct=3.9)
    assert _kinds(low, _m(net_yield_ann_pct=3.9), pv) == ["PROPOSE"]       # below cash x2
    assert _kinds(low, _m(net_yield_ann_pct=4.1), pv) == ["NONE"]          # only one month
    assert _kinds(_m(opens=2, closes=1, uptime_pct=59.0), None, pv) == ["PROPOSE"]
    assert _kinds(_m(opens=2, closes=1, uptime_pct=61.0), None, pv) == ["NONE"]
    assert _kinds(_m(price_usd=-101.0), None, pv) == ["INVESTIGATE"]       # > half funding
    assert _kinds(_m(price_usd=-99.0), None, pv) == ["NONE"]
    assert _kinds(_m(expected_funding_usd=197.0), None, pv) == ["INVESTIGATE"]   # 1.5% off
    assert _kinds(_m(expected_funding_usd=199.0), None, pv) == ["NONE"]          # 0.5% off
    assert _kinds(_m(funding_usd=2.10, expected_funding_usd=1.90), None, pv) == ["NONE"]  # < $1
    pv.liq_px = 5000.0                                                     # +85%
    assert _kinds(_m(), None, pv) == ["PROPOSE"]
    pv.liq_px = 8800.0
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 5.9}}}
    assert _kinds(_m(), None, pv) == ["NOTE"]
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 10.0}}}
    hi = _m(funding_yield_ann_pct=8.1)
    assert _kinds(hi, _m(funding_yield_ann_pct=8.1), pv) == ["CANDIDATE"]
    assert _kinds(_m(funding_yield_ann_pct=7.9), hi, pv) == ["NONE"]
    # fees count against it: 8.5% gross with 10% of funding spent on fees = 7.65%
    assert _kinds(_m(funding_yield_ann_pct=8.5, fees_usd=20.0), hi, pv) == ["NONE"]
    # never on basis: a big price component plus normal funding is no CANDIDATE
    assert _kinds(_m(price_usd=180.0, net_yield_ann_pct=16.0), _m(net_yield_ann_pct=16.0),
                  pv) == ["INVESTIGATE"]
    # never beside a proposal to cut back (below cash on net, despite funding)
    assert _kinds(_m(net_yield_ann_pct=3.0, funding_yield_ann_pct=9.0),
                  _m(net_yield_ann_pct=3.0, funding_yield_ann_pct=9.0), pv) == ["PROPOSE"]
    # never beside an open question
    assert _kinds(_m(funding_yield_ann_pct=12.0, price_usd=-150.0), hi, pv) == ["INVESTIGATE"]
    pv.liq_px = 6000.0                                                     # +122%: too close
    assert _kinds(hi, hi, pv) == ["NONE"]
    pv.liq_px = 8800.0
    assert _kinds(_m(), None, pv, ["x"]) == ["INVESTIGATE"]


def test_a_missing_cash_benchmark_never_reads_as_zero(pv):
    pv.cash_apy = None
    assert _kinds(_m(net_yield_ann_pct=5.0), _m(net_yield_ann_pct=5.0), pv) == ["NOTE"]
    assert _kinds(_m(net_yield_ann_pct=2.0), _m(net_yield_ann_pct=2.0), pv) == ["NOTE"]


# ------------------------------------------------------------------ fetching

def test_paginate_never_drops_or_doubles_rows_at_a_page_edge():
    rows = [{"time": t, "k": i} for i, t in enumerate([1, 2, 3, 3, 4, 5, 6, 6, 7, 8])]
    out = R.paginate(lambda s, e: [r for r in rows if s <= r["time"] <= e][:3], 0, 100, 3)
    assert sorted(r["k"] for r in out) == list(range(len(rows)))


def test_paginate_refuses_a_full_page_of_one_timestamp():
    rows = [{"time": 5, "k": i} for i in range(4)]
    with pytest.raises(R.FetchError, match="share timestamp"):
        R.paginate(lambda s, e: [r for r in rows if r["time"] >= s][:3], 5, 100, 3)


def test_paginate_rejects_a_non_list_page():
    with pytest.raises(R.FetchError):
        R.paginate(lambda s, e: None, 0, 10, 5)


def fake_post(fills, now, snap_null=False, no_candles=False):
    meta = {"tokens": [{"name": "USDC", "index": 0}, {"name": "UETH", "index": 221}],
            "universe": [{"name": "@151", "tokens": [221, 0], "index": 151}]}
    fund = hourly_funding(R.replay([f for f in fills if f["coin"] != "BTC"], PAIR),
                          flat(2700.0), T0, now)

    def post(body):
        t = body["type"]
        if t == "spotMeta":
            return meta
        if t == "userFillsByTime":
            return [f for f in fills if body["startTime"] <= f["time"] <= body["endTime"]]
        if t == "userFunding":
            return fund + [{"time": T0 + H, "delta": {"coin": "BTC", "usdc": "-1",
                                                      "szi": "0.03", "fundingRate": "1e-5"}}]
        if t == "fundingHistory":
            return rate_rows(body["startTime"], body["endTime"])[:500]
        if t == "candleSnapshot":
            iv = H if body["req"]["interval"] == "1h" else D
            return [] if no_candles else candles(body["req"]["startTime"], now,
                                                 flat(2700.0), iv)[:5000]
        if t == "clearinghouseState":
            return None if snap_null else {"assetPositions": [{"position": {
                "coin": "ETH", "szi": "-11.096", "liquidationPx": "8847.4",
                "cumFunding": {"sinceOpen": str(-sum(float(r["delta"]["usdc"]) for r in fund))}}}]}
        if t == "spotClearinghouseState":
            return {"balances": [{"coin": "UETH", "total": "11.09603845"}]}
        if t == "allMids":
            return {"ETH": "2700", "@151": "2700"}
        raise AssertionError(t)
    return post


def test_fetch_all_filters_coins_and_refuses_bad_snapshots():
    fills = REAL + [fill(T0 + 70_000, "BTC", "B", 0.01, 80000, 1, "USDC", 0)]
    now = T0 + 5 * H

    def get(url):
        return {"venues": {}} if url.endswith("/funding") else {"cash_apy": 0.04}
    v = R.fetch_all(now, T0, post=fake_post(fills, now), get=get)
    assert {f["coin"] for f in v.fills} == {"ETH", PAIR}
    assert v.funding and all(r["delta"]["coin"] == "ETH" for r in v.funding)
    assert v.liq_px == pytest.approx(8847.4) and v.cash_apy == 0.04 and v.notes == []
    assert v.cum_since_open is not None
    assert R.integrity(v, R.replay(v.fills, v.spot_pair)) == []
    with pytest.raises(R.FetchError):
        R.fetch_all(now, T0, post=fake_post(fills, now, snap_null=True), get=get)
    with pytest.raises(R.FetchError, match="no candles"):
        R.fetch_all(now, T0, post=fake_post(fills, now, no_candles=True), get=get)


def test_an_engine_outage_degrades_but_never_kills_the_review():
    now = T0 + 5 * H

    def down(url):
        raise R.FetchError("engine down")
    v = R.fetch_all(now, T0, post=fake_post(REAL, now), get=down)
    assert v.engine_funding == {} and v.cash_apy is None and len(v.notes) == 2
    r = R.build(v, "2026-10")
    r.pop("_replay")
    md = R.markdown(r)
    assert "Degraded inputs" in md and "UNKNOWN" in md


# ------------------------------------------------------------------ end to end

def test_build_markdown_series_and_chart_end_to_end(tmp_path):
    now = T0 + 30 * D
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2701.0), liq=8800.0)
    r = R.build(v, R.ym_of(now))
    rp = r.pop("_replay")
    assert r["integrity_flags"] == [] and r["notes"] == []
    assert [x["label"] for x in r["months"]] == ["2026-10", "2026-11"]
    md = R.markdown(r)
    assert "Integrity: CLEAN" in md and "Proposals" in md and "Honesty box" in md
    assert "Short liquidates at 8,800" in md
    json.dumps(r)
    s = R.series(v, rp)
    assert s["t"] == sorted(s["t"])
    assert s["total"][-1] == pytest.approx(r["inception_to_date"]["total_usd"], abs=0.02)
    assert s["funding"][-1] == pytest.approx(r["inception_to_date"]["funding_usd"], abs=0.02)
    assert s["rate"][-1] == pytest.approx(RATE * 8760 * 100)
    png = tmp_path / "c.png"
    R.chart(v, rp, s, str(png), "t")
    assert png.stat().st_size > 10_000


def test_previous_month_of_january_is_december():
    now = R.month_bounds("2027-01")[0] + 9 * H
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0), liq=8800.0)
    r = R.build(v, "2027-01")
    assert r["month"]["label"] == "2027-01" and r["previous_month"]["label"] == "2026-12"
    assert r["previous_month"]["hour_marks"] == 31 * 24


def test_main_writes_the_numbers_even_when_the_chart_fails(tmp_path, monkeypatch):
    now = T0 + 3 * D
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0), liq=8800.0)
    monkeypatch.setattr(R, "fetch_all", lambda *a, **k: v)

    def boom(*a, **k):
        raise RuntimeError("no display")
    monkeypatch.setattr(R, "chart", boom)
    rc = R.main(["--month", "current", "--out", str(tmp_path), "--now-ms", str(now)])
    assert rc == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "carry_review_2026-10.json", "carry_review_2026-10.md"]
    assert "chart failed" in (tmp_path / "carry_review_2026-10.md").read_text()
    assert any("chart failed" in n for n in
               json.loads((tmp_path / "carry_review_2026-10.json").read_text())["notes"])
    v.snap_perp_szi = -5.0                                  # an integrity flag -> exit 2
    v.notes = []
    assert R.main(["--month", "current", "--out", str(tmp_path), "--now-ms", str(now)]) == 2


def test_end_labels_are_spread_apart_in_order():
    out = R.spread([0.37, -1.12, -33.12, -33.87], 2.5)
    srt = sorted(out)
    assert all(b - a >= 2.5 - 1e-9 for a, b in zip(srt, srt[1:]))
    assert out[0] > out[1] > out[2] > out[3]
    assert R._money(-33.87) == "-$33.87" and R._money(0.37) == "$0.37"
    assert R._money(-0.001) == "$0.00" and R._usd(-0.004) == "$0.00"
    assert str(R._r(-0.001)) == "0.0"                       # no -0.0 in the json



# ------------------------------------------------------------------ re-review gaps

def test_cum_check_survives_a_merged_close_and_reopen_day():
    """A same-UTC-day close + reopen whose day is later MERGED: the merged row
    also holds the payments on the previous short, which cumFunding.sinceOpen
    does not count (verified on the BTC book, 2026-09-18)."""
    day = (T0 // D) * D
    close_at, reopen_at = day + 5 * D + 10 * H, day + 5 * D + 14 * H
    fills = REAL + [
        fill(close_at, PAIR, "A", 11.09603845, 2700.0, 30.0, "USDC", 11.09603845),
        fill(close_at + 2000, "ETH", "B", 11.096, 2700.0, 13.0, "USDC", -11.096),
        fill(reopen_at, PAIR, "B", 11.1, 2700.0, 0.0074, "UETH", 0.0),
        fill(reopen_at + 2000, "ETH", "A", 11.09, 2700.0, 13.0, "USDC", 0.0)]
    rp = R.replay(fills, PAIR)
    now = day + 20 * D + 8 * H + 56 * 60_000
    hourly = hourly_funding(rp, flat(2700.0), T0, now)
    assert rp.perp_open_ms() == reopen_at + 2000
    cum = -sum(float(r["delta"]["usdc"]) for r in hourly if r["time"] // H * H >= reopen_at)
    merged = merge_days(hourly, now - 8 * D)
    assert any(R.is_daily(r) and r["time"] == day + 5 * D for r in merged)
    v = venue(fills, merged, now, flat(2700.0), flat(2700.0), cum=cum)
    assert R.integrity(v, rp) == []
    v = venue(fills, hourly, now, flat(2700.0), flat(2700.0), cum=cum)
    assert R.integrity(v, rp) == []
    v = venue(fills, merged, now, flat(2700.0), flat(2700.0), cum=cum - 1.0)   # still bites
    assert any("cumFunding.sinceOpen" in f for f in R.integrity(v, rp))
    # the reopen and close are counted; the closed hours lower uptime
    w = R.window(v, rp, T0, now + 1, "ltd")
    assert (w["opens"], w["closes"]) == (2, 1)
    assert w["on_hours"] == w["hour_marks"] - 4 and w["uptime_pct"] < 100.0


def test_merged_rows_survive_fetch_all_and_are_booked_on_their_day():
    """Through the real fetch path: the sleeve's first day comes back merged and
    stamped Oct 4 00:00:00.000 - before CARRY_START (16:47) - and must be kept."""
    now = R.month_bounds("2026-11")[0] + 8 * H + 56 * 60_000
    hourly = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    merged = merge_days(hourly, now - 8 * D - 9 * H)
    first = merged[0]
    assert first["time"] < T0 and R.funding_key(first) == (T0 // D) * D + 23 * H
    post = fake_post(REAL, now)

    def post2(body):
        if body["type"] == "userFunding":
            return [r for r in merged if body["startTime"] <= r["time"] <= body["endTime"]]
        return post(body)
    v = R.fetch_all(now, now - 60 * D, post=post2, get=lambda u: {"cash_apy": 0.04})
    assert v.funding[0] is not None and any(R.is_daily(r) and r["time"] == first["time"]
                                            for r in v.funding)
    v.cum_since_open = -sum(float(r["delta"]["usdc"]) for r in hourly)
    assert R.integrity(v, R.replay(v.fills, v.spot_pair)) == []
    oct_ = R.window(v, R.replay(v.fills, v.spot_pair), *R.month_bounds("2026-10"), "oct")
    assert oct_["funding_usd"] == pytest.approx(
        sum(float(r["delta"]["usdc"]) for r in hourly if r["time"] < R.month_bounds("2026-11")[0]),
        abs=0.01)


@pytest.mark.parametrize("now_iso,want", [("2026-11-01T08:56:00", "2026-10"),
                                          ("2027-01-01T08:56:00", "2026-12")])
def test_the_routine_invocation_reviews_the_previous_month(tmp_path, monkeypatch, now_iso, want):
    import datetime as dt
    now = int(dt.datetime.fromisoformat(now_iso).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0), liq=8800.0,
              cum=None)
    monkeypatch.setattr(R, "fetch_all", lambda *a, **k: v)
    monkeypatch.setattr(R, "chart", lambda *a, **k: None)
    assert R.main(["--month", "previous", "--out", str(tmp_path), "--now-ms", str(now)]) == 0
    r = json.loads((tmp_path / f"carry_review_{want}.json").read_text())
    assert r["month"]["label"] == want
    a, b = R.month_bounds(want)
    assert r["month"]["uptime_pct"] == 100.0
    assert r["month"]["hour_marks"] == len(R.hour_marks(a, b, now))


def test_round_trip_uptime_and_a_closed_month():
    close = T0 + 50 * H + 30 * 60_000
    fills = round_trip(close)
    rp = R.replay(fills, PAIR)
    now = T0 + 40 * D
    v = venue(fills, hourly_funding(rp, flat(2050.0), T0, now), now, flat(2100.0), flat(2050.0))
    w = R.window(v, rp, T0, T0 + 60 * H, "x")
    assert w["hour_marks"] == 60 and w["on_hours"] == 51 and w["uptime_pct"] == 85.0
    nov = R.window(v, rp, *R.month_bounds("2026-11"), "2026-11")      # closed all month
    assert nov["on_hours"] == 0 and nov["uptime_pct"] == 0.0
    assert nov["funding_yield_ann_pct"] is None and nov["fees_usd"] == 0.0
    assert (nov["opens"], nov["closes"]) == (0, 0)
    assert _kinds(nov, None, v) == ["NONE"]


def test_a_run_a_minute_after_the_hour_with_the_row_present_is_clean():
    m = first_mark_after(T0) + 10 * H
    now = m + 61_000                                        # row for mark m IS published
    fund = hourly_funding(RP_REAL, flat(2700.0), T0, now)
    assert any(r["time"] // H * H == m for r in fund)
    v = venue(REAL, fund, now, flat(2700.0), flat(2700.0))
    assert R.integrity(v, RP_REAL) == []


def test_an_open_short_without_a_liquidation_price_still_reports(tmp_path, monkeypatch):
    now = T0 + 5 * H
    post = fake_post(REAL, now)

    def post2(body):
        out = post(body)
        if body["type"] == "clearinghouseState":
            out["assetPositions"][0]["position"]["liquidationPx"] = None
        return out
    v = R.fetch_all(now, T0, post=post2, get=lambda u: {"cash_apy": 0.04})
    assert v.liq_px is None
    r = R.build(v, "2026-10")
    r.pop("_replay")
    assert "liquidation price unavailable" in R.markdown(r)


def test_a_malformed_engine_answer_is_unknown_not_a_crash(pv):
    for eng in ({"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": "9.5"}}},
                {"venues": {"HL_ETH": {"armed": "yes", "mean_ann_pct": "abc"}}},
                {"venues": None}, {"venues": []}, [], None):
        pv.engine_funding = eng
        R.proposals(_m(), None, _m(), pv, [])
        g = R.gate_state(pv)
        assert g["armed"] in (True, False, None)
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": "5.5"}}}
    assert _kinds(_m(), None, pv) == ["NOTE"]               # coerced, rule still works


def test_a_venue_that_cannot_be_read_gives_an_error_report_and_exit_3(tmp_path, monkeypatch):
    def down(*a, **k):
        raise R.FetchError("info spotMeta failed after 4 tries: null response")
    monkeypatch.setattr(R, "fetch_all", down)
    now = R.month_bounds("2026-11")[0] + 9 * H
    assert R.main(["--month", "previous", "--out", str(tmp_path), "--now-ms", str(now)]) == 3
    md = (tmp_path / "carry_review_2026-10.md").read_text()
    assert "NOT PRODUCED" in md and "null response" in md
    assert "error" in json.loads((tmp_path / "carry_review_2026-10.json").read_text())


def test_the_eth_move_sits_beside_the_price_component():
    """Casey's question: the review must SHOW that price risk is hedged."""
    now = T0 + 30 * D

    def up(t):
        return 2700.0 * (1 + 0.10 * (t - T0) / (30 * D))    # ETH +10% over the month
    v = venue(REAL, hourly_funding(RP_REAL, up, T0, now), now, up, up)
    w = R.window(v, RP_REAL, T0, now + 1, "ltd")
    assert w["eth_move_pct"] == pytest.approx((up(now) / 2703.9 - 1) * 100, abs=0.01)
    assert w["unhedged_equiv_usd"] == pytest.approx(11.096 * (up(now) - 2703.9), abs=1.0)
    assert abs(w["price_usd"]) < 0.01 * abs(w["unhedged_equiv_usd"])   # hedged: ~0
    r = R.build(v, R.ym_of(now))
    r.pop("_replay")
    md = R.markdown(r)
    assert "naked long of the same size" in md and "ETH move" in md and "## By month" in md



# ------------------------------------------------------------------ final-round gaps

def close_reopen(close_at, reopen_at, px=2700.0):
    return REAL + [
        fill(close_at, PAIR, "A", 11.09603845, px, 30.0, "USDC", 11.09603845),
        fill(close_at + 2000, "ETH", "B", 11.096, px, 13.0, "USDC", -11.096),
        fill(reopen_at, PAIR, "B", 11.1, px, 0.0074, "UETH", 0.0),
        fill(reopen_at + 2000, "ETH", "A", 11.09, px, 13.0, "USDC", 0.0)]


@pytest.mark.parametrize("reopen_h", [14, 22.99, 23.5])
def test_cum_check_clean_for_a_merged_reopen_at_any_hour(reopen_h):
    """A reopen after 23:00 books the merged open-day row BEFORE the open: then
    nothing may be subtracted (it was never counted)."""
    day = (T0 // D) * D
    close_at = day + 5 * D + 10 * H
    reopen_at = day + 5 * D + int(reopen_h * H)
    fills = close_reopen(close_at, reopen_at)
    rp = R.replay(fills, PAIR)
    now = day + 20 * D + 8 * H + 56 * 60_000
    hourly = hourly_funding(rp, flat(2700.0), T0, now)
    cum = -sum(float(r["delta"]["usdc"]) for r in hourly if r["time"] // H * H > reopen_at)
    merged = merge_days(hourly, now - 8 * D)
    v = venue(fills, merged, now, flat(2700.0), flat(2700.0), cum=cum)
    assert R.integrity(v, rp) == []
    v = venue(fills, merged, now, flat(2700.0), flat(2700.0), cum=cum - 1.0)
    assert any("cumFunding.sinceOpen" in f for f in R.integrity(v, rp))


def test_a_missing_rate_on_the_merged_open_day_skips_with_a_note():
    day = (T0 // D) * D
    close_at, reopen_at = day + 5 * D + 10 * H, day + 5 * D + 14 * H
    fills = close_reopen(close_at, reopen_at)
    rp = R.replay(fills, PAIR)
    now = day + 20 * D + 8 * H + 56 * 60_000
    hourly = hourly_funding(rp, flat(2700.0), T0, now)
    cum = -sum(float(r["delta"]["usdc"]) for r in hourly if r["time"] // H * H >= reopen_at)
    gone = day + 5 * D + 3 * H                              # a HELD pre-open mark
    rates = [r for r in rate_rows(T0 - 40 * D, now) if r["time"] // H * H != gone]
    v = venue(fills, merge_days(hourly, now - 8 * D), now, flat(2700.0), flat(2700.0),
              cum=cum - 1.0, rates=rates)
    assert R.integrity(v, rp) == []
    assert sum("cumFunding check skipped" in n for n in v.notes) == 1


def test_the_naked_long_counts_only_the_hours_held():
    """Final-review SERIOUS: the yardstick must follow the hours the short was
    actually held, not the whole window's ETH move."""
    nov0 = R.month_bounds("2026-11")[0]
    close_at, reopen_at = nov0 + 9 * D + 12 * H, nov0 + 19 * D + 12 * H
    now = nov0 + 30 * D + 9 * H
    # (A) ETH +10% only while the sleeve was CLOSED
    def a(t):
        return 2700.0 if t < close_at else (2970.0 if t >= reopen_at else
                                             2700.0 + 270.0 * (t - close_at) / (reopen_at - close_at))
    fills = close_reopen(close_at, reopen_at, px=2700.0)
    fills[-2]["px"] = fills[-1]["px"] = "2970.0"            # reopened at the new price
    rp = R.replay(fills, PAIR)
    v = venue(fills, hourly_funding(rp, a, T0, now), now, a, a)
    w = R.window(v, rp, *R.month_bounds("2026-11"), "nov")
    assert w["uptime_pct"] < 70
    assert abs(w["unhedged_equiv_usd"]) < 1.0               # nothing moved while held
    # (C) ETH 2700 -> 3000 while OPEN, back to 2700 while CLOSED
    def c(t):
        if t <= close_at:
            return 2700.0 + 300.0 * max(0, t - nov0) / (close_at - nov0)
        return 2700.0
    fills = close_reopen(close_at, reopen_at, px=2700.0)
    fills[-4]["px"] = fills[-3]["px"] = "3000.0"            # closed at the top
    rp = R.replay(fills, PAIR)
    v = venue(fills, hourly_funding(rp, c, T0, now), now, c, c)
    w = R.window(v, rp, *R.month_bounds("2026-11"), "nov")
    assert w["unhedged_equiv_usd"] == pytest.approx(11.096 * 300.0, rel=0.01)
    assert w["eth_move_pct"] == pytest.approx(0.0, abs=0.01)


def test_eth_move_from_inception_uses_the_entry_fill_not_a_candle():
    now = T0 + 3 * D
    fills = [dict(f, px="2800.0") for f in REAL]
    rp = R.replay(fills, PAIR)
    v = venue(fills, hourly_funding(rp, flat(2700.0), T0, now), now, flat(2700.0), flat(2700.0))
    w = R.window(v, rp, T0, now + 1, "ltd")
    assert w["eth_move_pct"] == pytest.approx((2700.0 / 2800.0 - 1) * 100, abs=0.01)
    assert w["unhedged_equiv_usd"] == pytest.approx(11.096 * -100.0, abs=0.5)


def test_a_flip_through_zero_is_a_new_open():
    fills = REAL + [fill(T0 + 5 * H, "ETH", "B", 20.0, 2700.0, 1.0, "USDC", -11.096)]
    rp = R.replay(fills, PAIR)
    assert rp.at(T0 + 6 * H).perp == pytest.approx(8.904)
    assert rp.perp_open_ms() == T0 + 5 * H


def test_inception_to_date_equals_the_months_when_run_exactly_on_a_mark():
    now = R.month_bounds("2026-11")[0] + 5 * D            # exactly 00:00:00.000
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2701.0), liq=8800.0)
    r = R.build(v, "2026-11")
    for k in ("funding_usd", "hour_marks", "on_hours"):
        assert r["inception_to_date"][k] == pytest.approx(
            sum(m[k] for m in r["months"]), abs=0.02), k


def test_hours_older_than_the_hourly_history_are_counted():
    now = T0 + 300 * D
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0))
    v.perp_h = [c for c in v.perp_h if c["t"] >= now - 5000 * H]
    w = R.window(v, RP_REAL, *R.month_bounds("2026-10"), "oct")
    assert w["hours_priced_daily"] == w["on_hours"] > 0
    w = R.window(v, RP_REAL, *R.month_bounds("2027-07"), "jul")
    assert w["hours_priced_daily"] == 0


def test_candidate_needs_steady_uptime_a_clean_prior_month_and_an_open_gate(pv):
    hi = _m(funding_yield_ann_pct=12.0, net_yield_ann_pct=11.0)
    assert _kinds(hi, hi, pv) == ["CANDIDATE"]
    assert _kinds(_m(funding_yield_ann_pct=15.0, uptime_pct=25.0), hi, pv) == ["NONE"]
    assert _kinds(hi, _m(funding_yield_ann_pct=12.0, price_usd=-150.0), pv) == ["NONE"]
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 5.6}}}
    assert _kinds(hi, hi, pv) == ["NOTE"]                  # about to close: no size-up
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 5.6,
                                               "insufficient": True}}}
    assert _kinds(hi, hi, pv) == ["CANDIDATE"]             # frozen gate: no close NOTE


def test_gate_coercion_rejects_nan_inf_and_bool(pv):
    for x in ("nan", "inf", float("nan"), "1e400", True, [1], {}, "", "5.5%"):
        pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": x}}}
        assert R.gate_state(pv)["mean_ann_pct"] is None, x
    pv.engine_funding = {"venues": {"HL_ETH": {"armed": True, "mean_ann_pct": 6.0,
                                               "insufficient": True}}}
    r = R.build(pv, "2026-11")
    r.pop("_replay")
    assert "insufficient data, state frozen" in R.markdown(r)


def test_chart_renders_money_as_text_and_matches_the_md(tmp_path):
    import matplotlib
    now = T0 + 3 * D
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2690.0), liq=8800.0)
    r = R.build(v, "2026-10")
    rp = r.pop("_replay")
    R.chart(v, rp, R.series(v, rp), str(tmp_path / "c.png"), "t", ltd=r["inception_to_date"])
    assert matplotlib.rcParams["text.parse_math"] is False


@pytest.mark.parametrize("where,code", [("fetch", 3), ("build", 4)])
def test_failures_never_leave_a_stale_chart(tmp_path, monkeypatch, where, code):
    month = "2026-10"
    stale = tmp_path / f"carry_review_{month}.png"
    stale.write_bytes(b"old chart")
    now = T0 + 3 * D
    v = venue(REAL, hourly_funding(RP_REAL, flat(2700.0), T0, now), now,
              flat(2700.0), flat(2700.0))
    if where == "fetch":
        monkeypatch.setattr(R, "fetch_all", lambda *a, **k: (_ for _ in ()).throw(KeyError("szi")))
    else:
        monkeypatch.setattr(R, "fetch_all", lambda *a, **k: v)
        monkeypatch.setattr(R, "build", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    assert R.main(["--month", "current", "--out", str(tmp_path), "--now-ms", str(now)]) == code
    assert not stale.exists()
    assert "NOT PRODUCED" in (tmp_path / f"carry_review_{month}.md").read_text()
