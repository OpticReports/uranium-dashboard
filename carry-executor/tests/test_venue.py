"""Gates for the carry venue adapter (app/venue.py). No network: a fake SDK is
installed into sys.modules; the SDK-existence gate reads the REAL SDK."""
from __future__ import annotations

import ast
import inspect
import sys
import types

import pytest

from app.venue import grid_px, round_down


class _FakeInfo:
    def __init__(self, *a, **kw):
        self.spot = {"balances": [{"coin": "USDC", "total": "70000.0", "hold": "0"},
                                  {"coin": "UETH", "total": "7.5", "hold": "0.5"}]}
        self.state = {"assetPositions": [
            {"position": {"coin": "BTC", "szi": "0.03"}},
            {"position": {"coin": "ETH", "szi": "-7.5", "liquidationPx": "9100.5"}}]}
        self.mids = {"ETH": "4001.5", "@151": "4000.1", "BTC": "84000"}

    def spot_meta(self):
        return {"tokens": [{"name": "USDC", "index": 0, "szDecimals": 8},
                           {"name": "UBTC", "index": 197, "szDecimals": 5},
                           {"name": "UETH", "index": 221, "szDecimals": 4}],
                "universe": [{"name": "@142", "tokens": [197, 0], "index": 142},
                             {"name": "@151", "tokens": [221, 0], "index": 151}]}

    def meta(self, dex=""):
        return {"universe": [{"name": "BTC", "szDecimals": 5},
                             {"name": "ETH", "szDecimals": 4}]}

    def spot_user_state(self, address):
        return self.spot

    def user_state(self, address, dex=""):
        return self.state

    def all_mids(self, dex=""):
        return self.mids

    def user_funding_history(self, user, startTime, endTime=None):
        return [{"delta": {"coin": "ETH", "usdc": "1.25"}},
                {"delta": {"coin": "BTC", "usdc": "-9.0"}},
                {"delta": {"coin": "ETH", "usdc": "0.75"}}]


class _FakeExchange:
    def __init__(self, *a, **kw):
        self.sent = []
        self.resp = None
        self.lev = []

    def order(self, name, is_buy, sz, limit_px, order_type, reduce_only=False,
              cloid=None, builder=None):
        self.sent.append(dict(name=name, is_buy=is_buy, sz=sz, px=limit_px,
                              type=order_type, reduce_only=reduce_only))
        return self.resp or {"status": "ok", "response": {"data": {"statuses": [
            {"filled": {"totalSz": str(sz), "avgPx": str(limit_px)}}]}}}

    def update_leverage(self, leverage, name, is_cross=True):
        self.lev.append((leverage, name, is_cross))
        return {"status": "ok"}


@pytest.fixture
def venue(monkeypatch):
    ex_mod = types.ModuleType("hyperliquid.exchange")
    ex_mod.Exchange = _FakeExchange
    info_mod = types.ModuleType("hyperliquid.info")
    info_mod.Info = _FakeInfo
    const_mod = types.ModuleType("hyperliquid.utils.constants")
    const_mod.MAINNET_API_URL = "https://api.hyperliquid.xyz"
    const_mod.TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
    utils_mod = types.ModuleType("hyperliquid.utils")
    utils_mod.constants = const_mod
    pkg = types.ModuleType("hyperliquid")
    pkg.exchange, pkg.info, pkg.utils = ex_mod, info_mod, utils_mod
    eth_mod = types.ModuleType("eth_account")

    class _Acct:
        address = "0xagent"

        @staticmethod
        def from_key(k):
            return _Acct()
    eth_mod.Account = _Acct
    for name, mod in (("hyperliquid", pkg), ("hyperliquid.exchange", ex_mod),
                      ("hyperliquid.info", info_mod), ("hyperliquid.utils", utils_mod),
                      ("hyperliquid.utils.constants", const_mod), ("eth_account", eth_mod)):
        monkeypatch.setitem(sys.modules, name, mod)
    from app.venue import HLCarryVenue

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = "0xMAIN"
        hl_testnet = False
        perp_coin = "ETH"
        spot_token = "UETH"
    return HLCarryVenue(Cfg())


def test_gate_carry_calls_only_real_sdk_methods():
    ex = pytest.importorskip("hyperliquid.exchange")
    info = pytest.importorskip("hyperliquid.info")
    import app.venue as vmod
    tree = ast.parse(open(vmod.__file__).read())
    called: dict[str, set] = {"exchange": set(), "info": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if node.value.attr in called:
                called[node.value.attr].add(node.attr)
    assert called["exchange"] and called["info"]
    missing = ([m for m in sorted(called["exchange"]) if not hasattr(ex.Exchange, m)]
               + [m for m in sorted(called["info"]) if not hasattr(info.Info, m)])
    assert not missing, f"venue.py calls SDK methods that do not exist: {missing}"
    # and the positional order this adapter relies on
    assert list(inspect.signature(ex.Exchange.update_leverage).parameters)[:4] == \
        ["self", "leverage", "name", "is_cross"]
    assert "reduce_only" in inspect.signature(ex.Exchange.order).parameters


def test_resolves_the_ueth_pair_and_decimals(venue):
    assert venue.spot_pair == "@151" and venue.spot_sz_dec == 4
    assert venue.perp_sz_dec == 4


def test_read_reports_both_legs_and_ignores_btc(venue):
    r = venue.read()
    assert r["spot_qty"] == 7.5 and r["spot_hold"] == 0.5
    assert r["perp_qty"] == -7.5 and r["liq_px"] == 9100.5
    assert r["perp_mid"] == 4001.5 and r["spot_mid"] == 4000.1


def test_read_confirmed_flat_vs_unreadable(venue):
    venue.info.state = {"assetPositions": []}
    venue.info.spot = {"balances": [{"coin": "USDC", "total": "1"}]}
    r = venue.read()
    assert r["perp_qty"] == 0.0 and r["spot_qty"] == 0.0
    venue.info.state = None
    with pytest.raises(RuntimeError):
        venue.read()
    venue.info.state = {"assetPositions": []}
    venue.info.mids = {"BTC": "1"}
    with pytest.raises(RuntimeError):
        venue.read()


def test_account_address_is_mandatory(monkeypatch, venue):
    from app.venue import HLCarryVenue

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = " "
        hl_testnet = False
        perp_coin = "ETH"
        spot_token = "UETH"
    with pytest.raises(RuntimeError, match="HL_ACCOUNT_ADDRESS"):
        HLCarryVenue(Cfg())


def test_missing_spot_pair_refuses_to_construct(monkeypatch, venue):
    from app.venue import HLCarryVenue
    monkeypatch.setattr(_FakeInfo, "spot_meta", lambda self: {"tokens": [], "universe": []})

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = "0xMAIN"
        hl_testnet = False
        perp_coin = "ETH"
        spot_token = "UETH"
    with pytest.raises(RuntimeError, match="UETH/USDC"):
        HLCarryVenue(Cfg())


def test_ioc_spot_buy_goes_to_the_pair_rounded_onto_the_grid(venue):
    r = venue.ioc("spot", True, 7.56789, 4000.1, 15.0)
    o = venue.exchange.sent[-1]
    assert o["name"] == "@151" and o["is_buy"] is True
    assert o["sz"] == 7.5678                             # floored to 4 dp
    assert o["px"] <= 4000.1 * 1.0015 and o["px"] == 4006.1   # 5 sig figs, down
    assert o["type"] == {"limit": {"tif": "Ioc"}} and o["reduce_only"] is False
    assert r["filled"] == pytest.approx(7.5678)


def test_ioc_perp_sell_rounds_up_and_passes_reduce_only(venue):
    venue.ioc("perp", False, 1.0, 4001.5, 15.0, reduce_only=True)
    o = venue.exchange.sent[-1]
    assert o["name"] == "ETH" and o["is_buy"] is False and o["reduce_only"] is True
    assert o["px"] >= 4001.5 * (1 - 0.0015)


def test_ioc_no_liquidity_is_a_zero_fill_other_errors_raise(venue):
    venue.exchange.resp = {"status": "ok", "response": {"data": {"statuses": [
        {"error": "Order could not immediately match against any resting orders."}]}}}
    assert venue.ioc("spot", True, 1.0, 4000.0, 15.0)["filled"] == 0.0
    venue.exchange.resp = {"status": "ok", "response": {"data": {"statuses": [
        {"error": "Insufficient margin to place order."}]}}}
    with pytest.raises(RuntimeError, match="Insufficient margin"):
        venue.ioc("perp", False, 1.0, 4000.0, 15.0)
    venue.exchange.resp = {"status": "err", "response": "bad"}
    with pytest.raises(RuntimeError):
        venue.ioc("perp", False, 1.0, 4000.0, 15.0)


def test_ensure_cross_sets_cross_margin(venue):
    venue.ensure_cross(5)
    assert venue.exchange.lev == [(5, "ETH", True)]


def test_funding_received_counts_only_the_perp_coin(venue):
    assert venue.funding_received(0) == pytest.approx(2.0)


@pytest.mark.parametrize("px,dec,maxd,mode,want", [
    (4006.1006, 4, 6, "down", 4006.1),      # perp ETH: 5 sig figs -> 1 dp
    (4006.1006, 4, 6, "up", 4006.2),
    (84123.456, 5, 6, "down", 84123.0),     # BTC: integer
    (0.123456, 4, 8, "down", 0.1234),       # spot cap 8-4 = 4 dp
    (12.34567, 4, 6, "up", 12.35),          # perp cap 6-4 = 2 dp
])
def test_price_grid(px, dec, maxd, mode, want):
    assert grid_px(px, dec, maxd, mode) == pytest.approx(want)


def test_round_down_never_rounds_up():
    assert round_down(7.56789, 4) == 7.5678
    assert round_down(0.00009, 4) == 0.0


def test_only_eth_ueth_may_be_traded(venue):
    from app.venue import HLCarryVenue

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = "0xMAIN"
        hl_testnet = False
        perp_coin = "BTC"
        spot_token = "UBTC"
    with pytest.raises(RuntimeError, match="btc-executor"):
        HLCarryVenue(Cfg())


def test_refuses_btc_executors_agent_key(monkeypatch, venue):
    from app.venue import HLCarryVenue
    monkeypatch.setattr(_FakeInfo, "extra_agents", lambda self, u: [
        {"name": "BTC EXECUTOR 2", "address": "0xAGENT"}], raising=False)

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = "0xMAIN"
        hl_testnet = False
        perp_coin = "ETH"
        spot_token = "UETH"
    with pytest.raises(RuntimeError, match="separate API wallet"):
        HLCarryVenue(Cfg())
    monkeypatch.setattr(_FakeInfo, "extra_agents", lambda self, u: [
        {"name": "CARRY EXECUTOR", "address": "0xagent"}], raising=False)
    assert HLCarryVenue(Cfg()).spot_pair == "@151"


def test_btc_executor_readiness_check(monkeypatch):
    from app import feed

    class R:
        def __init__(self, d):
            self.d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self.d
    monkeypatch.setattr(feed.httpx, "get", lambda *a, **k: R({"build": "abc"}))
    assert feed.btc_executor_ready("x")[0] is False
    monkeypatch.setattr(feed.httpx, "get",
                        lambda *a, **k: R({"equity_counts_spot_tokens": True}))
    assert feed.btc_executor_ready("x")[0] is True

    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(feed.httpx, "get", boom)
    assert feed.btc_executor_ready("x")[0] is False
