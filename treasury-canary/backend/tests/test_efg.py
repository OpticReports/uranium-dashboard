"""E (auctions) / G (liquidity) / F (foreign) builders."""
from datetime import date, timedelta

from app.metrics.auctions import build_auction_metrics
from app.metrics.base import Status
from app.metrics.foreign import build_foreign_metrics
from app.metrics.liquidity import build_liquidity_metrics
from app.sources.treasury import _f


def _auction(i: int, b2c: float, dealer: float, indirect: float) -> dict:
    return {"auction_date": (date(2026, 1, 1) + timedelta(days=3 * i)).isoformat(),
            "security_type": "Note", "security_term": "10-Year",
            "bid_to_cover": b2c, "dealer_pct": dealer, "indirect_pct": indirect,
            "direct_pct": 100.0 - dealer - indirect, "high_yield": 4.5}


def test_auction_metrics_healthy():
    auctions = [_auction(i, 2.6, 10.0, 70.0) for i in range(20)]
    by = {m.metric_id: m for m in build_auction_metrics(auctions)}
    assert by["auctions.bid_to_cover"].value == 2.6
    assert by["auctions.bid_to_cover"].status is Status.GREEN
    assert by["auctions.dealer_takedown"].status is Status.GREEN
    assert by["auctions.indirect_share"].status is Status.GREEN
    assert all(m.category == "E" for m in by.values())


def test_auction_metrics_deteriorating():
    # healthy history, then 8 weak auctions: b2c 2.1, dealers forced to 25%, indirect 45%
    auctions = ([_auction(i, 2.6, 10.0, 70.0) for i in range(12)]
                + [_auction(12 + i, 2.1, 25.0, 45.0) for i in range(8)])
    by = {m.metric_id: m for m in build_auction_metrics(auctions)}
    assert by["auctions.bid_to_cover"].status is Status.RED        # 2.1 < 2.2
    assert by["auctions.dealer_takedown"].status is Status.RED     # 25 > 20
    assert by["auctions.indirect_share"].status is Status.RED      # 45 < 50
    assert by["auctions.bid_to_cover"].delta_20d is not None
    assert by["auctions.bid_to_cover"].delta_20d < 0               # trend down vs prior 8


def test_auction_metrics_empty_stale():
    by = {m.metric_id: m for m in build_auction_metrics([])}
    assert all(m.status is Status.STALE for m in by.values())


def test_fiscaldata_float_parser():
    assert _f("2.590000") == 2.59
    assert _f("null") is None
    assert _f(None) is None


def test_liquidity_ofr_fsi():
    d = [date(2026, 1, 1) + timedelta(days=i) for i in range(30)]
    calm = build_liquidity_metrics({"ofr_fsi": (d, [0.2] * 30)})[0]
    hot = build_liquidity_metrics({"ofr_fsi": (d, [0.2] * 29 + [3.5])})[0]
    assert calm.status is Status.GREEN
    assert hot.status is Status.RED
    assert build_liquidity_metrics({})[0].status is Status.STALE


def test_foreign_custody_26w():
    weeks = [date(2025, 1, 1) + timedelta(weeks=i) for i in range(60)]
    flat = build_foreign_metrics({"custody": (weeks, [3_000_000.0] * 60)})[0]
    assert flat.status is Status.GREEN and flat.value == 0.0
    # 6% decline over the last 26 weeks -> RED
    vals = [3_000_000.0] * 34 + [3_000_000.0 * (1 - 0.06 * (i / 25)) for i in range(26)]
    selling = build_foreign_metrics({"custody": (weeks, vals)})[0]
    assert selling.value is not None and selling.value <= -5.0
    assert selling.status is Status.RED
    assert build_foreign_metrics({})[0].status is Status.STALE