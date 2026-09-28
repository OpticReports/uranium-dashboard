"""Gate tests for the CAGR-study harness. Run: python3 -m pytest -q test_harness.py

The harness is a scoring instrument, so it must be proven against the
production code path before any number it produces is read.
"""
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                                                 # noqa: E402
from app.engine.core import BookCfg, SignalCfg, TradeCfg          # noqa: E402
from app.engine.replay import run_replay                           # noqa: E402

BARS = H.load_bars("btcusd")
T0 = H.ts_of("2019-01-01")
TCFG = TradeCfg(taker_fee_bps=H.LIVE_TAKER_BPS)


def _prod_trades(strategy):
    cfg = BookCfg(name="X", sizing="fixed", strategy=strategy, trail_atr=5.0,
                  leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9)
    res = run_replay(BARS, [cfg], SignalCfg(), TCFG, start_ts=T0)
    b = res.books["X"]
    return [(t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price,
             t.exit_reason) for t in b.trades]


@pytest.mark.parametrize("strategy", ["pullback", "donchian"])
def test_default_hooks_reproduce_run_replay_exactly(strategy):
    mine = [(t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price,
             t.reason)
            for t in H.leg_trades(BARS, strategy, start_ts=T0, tcfg=TCFG)
            if t.exit_ts is not None]
    prod = _prod_trades(strategy)
    assert len(prod) > 50
    assert mine == prod


@pytest.mark.parametrize("strategy", ["pullback", "donchian"])
def test_reproduces_run_replay_from_first_bar(strategy):
    """No start_ts: covers the warmup boundary, which the 2019 case above
    cannot see (a warmup off-by-one survived mutation without this)."""
    bars = BARS[:4000]
    cfg = BookCfg(name="X", sizing="fixed", strategy=strategy, trail_atr=5.0,
                  leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9)
    b = run_replay(bars, [cfg], SignalCfg(), TCFG).books["X"]
    prod = [(t.entry_ts, t.exit_ts, t.exit_price) for t in b.trades]
    mine = [(t.entry_ts, t.exit_ts, t.exit_price)
            for t in H.leg_trades(bars, strategy, tcfg=TCFG)
            if t.exit_ts is not None]
    assert prod and mine == prod


def test_monkeypatch_is_restored():
    from app.engine import core
    orig = core._process_donchian
    H.leg_trades(BARS[:3000], "donchian",
                 donchian_fn=H.process_donchian_resting_stop)
    assert core._process_donchian is orig


def test_resting_stop_variant_differs_and_never_fills_above_open_on_longs():
    base = H.leg_trades(BARS, "donchian", start_ts=T0, tcfg=TCFG)
    alt = H.leg_trades(BARS, "donchian", start_ts=T0, tcfg=TCFG,
                       donchian_fn=H.process_donchian_resting_stop)
    assert [t.entry_ts for t in base] != [t.entry_ts for t in alt]
    by_ts = {b.ts: b for b in BARS}
    for t in alt:
        if t.exit_ts is None:
            continue
        b = by_ts[t.exit_ts]
        # a stop fill must be a price the bar actually traded
        assert b.low - 1e-6 <= t.exit_price <= b.high + 1e-6


def test_simulate_single_trade_arithmetic():
    """One long, hand-computed: P&L, both fees, MTM path."""
    closes = {"btcusd": {0: 100.0, BAR_S: 110.0, 2 * BAR_S: 120.0}}
    tr = [H.Trade("p", "L", 0, 100.0, 2 * BAR_S, 120.0, "SIGNAL")]
    r = H.simulate([H.LegSpec(tr, 1.0)], closes, k=0.5, fee_bps=10.0,
                   start_equity=1000.0)
    notional = 500.0
    qty = 5.0
    efee = 0.001 * notional
    xfee = 0.001 * qty * 120.0
    want_end = 1000.0 - efee + qty * 20.0 - xfee
    assert r.equity[-1] == pytest.approx(want_end)
    assert r.equity[0] == pytest.approx(1000.0 - efee)        # marked at 100
    assert r.equity[1] == pytest.approx(1000.0 - efee + qty * 10.0)
    assert r.fees == pytest.approx(efee + xfee)


def test_simulate_short_pnl_sign():
    closes = {"btcusd": {0: 100.0, BAR_S: 90.0}}
    tr = [H.Trade("t", "S", 0, 100.0, BAR_S, 90.0, "STOP")]
    r = H.simulate([H.LegSpec(tr, 1.0)], closes, k=1.0, fee_bps=0.0,
                   start_equity=1000.0)
    assert r.equity[-1] == pytest.approx(1100.0)


def test_simulate_scales_linearly_in_k_for_one_trade():
    closes = {"btcusd": {0: 100.0, BAR_S: 105.0}}
    tr = [H.Trade("p", "L", 0, 100.0, BAR_S, 105.0, "SIGNAL")]
    r1 = H.simulate([H.LegSpec(tr, 1.0)], closes, k=1.0, fee_bps=0.0)
    r2 = H.simulate([H.LegSpec(tr, 1.0)], closes, k=2.0, fee_bps=0.0)
    g1 = r1.equity[-1] / 100_000 - 1
    g2 = r2.equity[-1] / 100_000 - 1
    assert g2 == pytest.approx(2 * g1)


def test_open_position_at_end_is_marked_not_dropped():
    closes = {"btcusd": {0: 100.0, BAR_S: 150.0}}
    tr = [H.Trade("p", "L", 0, 100.0, None, None, "OPEN")]
    r = H.simulate([H.LegSpec(tr, 1.0)], closes, k=1.0, fee_bps=0.0,
                   start_equity=1000.0)
    assert r.equity[-1] == pytest.approx(1500.0)


def test_k_safe_is_monotone_in_target():
    rng = np.random.default_rng(0)
    ret = rng.normal(0.0004, 0.01, 8000)
    k20, _ = H.k_safe(ret, target_dd=0.20, n_paths=300)
    k30, _ = H.k_safe(ret, target_dd=0.30, n_paths=300)
    assert 0 < k20 < k30


BAR_S = H.BAR_S


def test_weight_fn_overrides_static_weight_at_entry():
    closes = {"btcusd": {0: 100.0, BAR_S: 110.0, 2 * BAR_S: 100.0,
                         3 * BAR_S: 110.0}}
    tr = [H.Trade("p", "L", 0, 100.0, BAR_S, 110.0, "S"),
          H.Trade("p", "L", 2 * BAR_S, 100.0, 3 * BAR_S, 110.0, "S")]
    wf = lambda ts: 1.0 if ts == 0 else 0.0     # second trade gets zero size
    r = H.simulate([H.LegSpec(tr, 5.0, weight_fn=wf)], closes, k=1.0,
                   fee_bps=0.0, start_equity=1000.0)
    assert r.equity[-1] == pytest.approx(1100.0)   # only the first trade
