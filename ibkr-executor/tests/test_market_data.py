"""Gates for the market-data fix (2026-08-24): the book could not seed its
SPY core because reqMarketDataType was never called - live data (type 1) on
an unsubscribed paper account returns nan for every quote, silently."""
import sys
import time
import types

import pytest

import app.ib_adapter as ib_mod
from tests.test_ib_stock_adapter import (FakeIB, FakeStock, FakeMarketOrder,
                                         FakeStopOrder, _Cfg)


class MDFakeIB(FakeIB):
    """FakeIB that serves prices PER market-data type, like IB does."""

    def __init__(self):
        super().__init__()
        self.md_type = 1                 # IB's default when never requested
        self.md_requests: list[int] = []
        self.prices_by_type: dict[int, dict] = {1: {}, 3: {}}

    def reqMarketDataType(self, t):
        self.md_requests.append(t)
        self.md_type = t

    def reqMktData(self, contract, generic, snapshot, regulatory):
        from tests.test_ib_stock_adapter import FakeTicker
        px = self.prices_by_type.get(self.md_type, {}).get(
            contract.symbol, float("nan"))
        return FakeTicker(px)


@pytest.fixture
def md_adapter(monkeypatch):
    mod = types.ModuleType("ib_async")
    mod.IB = MDFakeIB
    mod.Stock = FakeStock
    mod.Future = FakeStock
    mod.MarketOrder = FakeMarketOrder
    mod.StopOrder = FakeStopOrder
    monkeypatch.setitem(sys.modules, "ib_async", mod)
    monkeypatch.setattr(ib_mod, "WAIT_TICK_S", 0.0)
    cfg = _Cfg()
    cfg.ib_market_data_type = 1
    cfg.ib_allow_delayed = True
    cfg.ib_quote_wait_s = 0.6            # keep failing waits fast in tests
    a = ib_mod.IBAdapter(cfg)
    return a


def test_market_data_type_requested_at_connect(md_adapter):
    """The root cause: NEVER requesting a type left IB serving live data to
    an unsubscribed paper account -> nan on every quote, no trades, forever."""
    assert md_adapter.ib.md_requests[:1] == [1]


def test_live_nan_escalates_to_delayed_visibly(md_adapter, monkeypatch):
    sent = []
    from app import alerts
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    md_adapter.ib.prices_by_type[3]["SPY"] = 640.25   # delayed has it
    px = md_adapter.spot("SPY")
    assert px == 640.25
    assert 3 in md_adapter.ib.md_requests             # escalated
    # the degradation is ANNOUNCED - delayed pricing must never be inferred
    assert any("DELAYED" in m and "ACTION NEEDED" in m for m in sent), sent
    # ...and announced ONCE, not per quote
    sent.clear()
    md_adapter.ib.prices_by_type[3]["BIL"] = 91.5
    md_adapter.spot("BIL")
    assert not sent


def test_go_live_posture_hard_fails_instead_of_delayed(md_adapter, monkeypatch):
    """IB_ALLOW_DELAYED=false is the live-money posture: pricing real orders
    on 15-minute-stale quotes silently is not acceptable, so the cycle must
    fail closed instead."""
    md_adapter.cfg.ib_allow_delayed = False
    md_adapter.ib.prices_by_type[3]["SPY"] = 640.25   # delayed WOULD work
    with pytest.raises(RuntimeError, match="delayed fallback disabled"):
        md_adapter.spot("SPY")
    assert 3 not in md_adapter.ib.md_requests


def test_both_feeds_dry_names_the_subscription(md_adapter):
    with pytest.raises(RuntimeError, match="subscription"):
        md_adapter.spot("SPY")
    # configured type restored so one bad symbol does not leave the session
    # stuck on delayed for everyone else
    assert md_adapter.ib.md_requests[-1] == 1


def test_live_quote_never_touches_delayed(md_adapter):
    md_adapter.ib.prices_by_type[1]["SPY"] = 641.0
    assert md_adapter.spot("SPY") == 641.0
    assert 3 not in md_adapter.ib.md_requests


def test_await_tick_falls_back_through_tick_fields(md_adapter):
    """A flat 3s sleep + single marketPrice() read missed feeds that only
    populate last/close/bid - a WORKING subscription read as no-price."""
    from tests.test_ib_stock_adapter import FakeTicker
    t = FakeTicker(float("nan"))
    t.close = 639.9
    assert md_adapter._await_tick(t, 0.3) == 639.9


def test_persistent_quote_outage_stays_visible_on_health():
    """The alert-once pattern is right for Telegram but made a persistent
    no-quote condition self-silencing: one alert, then /health green and
    zero trades indefinitely. /health now carries the outage AGE."""
    from fastapi.testclient import TestClient
    import app.service as svc

    class _St:
        quotes_missing_since = time.time() - 3600

    class _Blend:
        state = _St()
    old_blend = svc.BLEND
    try:
        svc.BLEND = _Blend()
        body = TestClient(svc.app).get("/health").json()
        assert body["blend_loop"]["quotes_missing_for_s"] == pytest.approx(
            3600, abs=30)
    finally:
        svc.BLEND = old_blend
