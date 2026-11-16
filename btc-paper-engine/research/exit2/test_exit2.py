"""EXIT2 gate tests - merge-blocking for RESEARCH_EXIT2.md.

run: cd research/exit2 && python -m pytest -q test_exit2.py
"""
import dataclasses
import random

import pytest

from harness2 import (BASE, HOLDOUT, INSAMPLE, RESEARCH_TRADE, S4_CFG, T_2013,
                      T_2022, T_IS_END, X, extend, load_asset, load_holdout,
                      prepare, run_s4x, s4_step_x)
from harness import RESEARCH_SIGNAL, Asset, Bar, Book, Ind, Position, _fresh_state
from app.engine.replay import run_replay
from variants2 import ALL
import run2

run2.setup_models()
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
AS = {**{s: load_asset(s) for s in INSAMPLE}, **{s: load_holdout(s) for s in HOLDOUT}}
EX = {s: extend(A) for s, A in AS.items()}


def _same(a, b):
    return len(a) == len(b) and all(
        dataclasses.asdict(x) == dataclasses.asdict(y) for x, y in zip(a, b))


# G1: BASE is the engine, every in-sample and holdout coin, halt on and off
@pytest.mark.parametrize("sym", list(AS))
@pytest.mark.parametrize("cfg", [S4_CFG, NOHALT], ids=["halt", "nohalt"])
def test_g1_base_is_engine(sym, cfg):
    A = AS[sym]
    wins = [(None, None)] + ([(T_2013, T_IS_END), (T_2022, T_IS_END)] if sym == "btc" else [])
    for a, b in wins:
        rr = run_replay(A.bars, [cfg], RESEARCH_SIGNAL, RESEARCH_TRADE, start_ts=a, end_ts=b)
        bk, _ = run_s4x(A, EX[sym], BASE, a, b, cfg=cfg)
        assert _same(rr.books["S4"].trades, bk.trades), (sym, a)


# G4: no look-ahead for any registered config (cuts inside the 2022+ run)
@pytest.mark.parametrize("x", ALL, ids=lambda x: x.name)
def test_g4_no_lookahead(x):
    A = AS["btc"]
    full, _ = run_s4x(A, EX["btc"], x, T_2022, None, cfg=NOHALT)
    for cut in (24000, 27500, 31000):
        At = prepare("btc", A.bars[:cut])
        part, _ = run_s4x(At, extend(At), x, T_2022, None, cfg=NOHALT)
        last = A.bars[cut - 1].ts
        assert _same([t for t in full.trades if t.exit_ts <= last],
                     [t for t in part.trades if t.exit_ts <= last]), (x.name, cut)


# G6: never-firing settings are the baseline exactly
NOOPS = [X(name="n_vs", vs_band=2.0), X(name="n_rg", rg_map="flat"),
         X(name="n_acc", acc_alpha=0.0), X(name="n_accp", accp_beta=0.0),
         X(name="n_sar", psar_max=0.0), X(name="n_lr", lr_theta=1.01)]


@pytest.mark.parametrize("x", NOOPS, ids=lambda x: x.name)
def test_g6_noop_is_base(x):
    for sym in ("btc", "eth", "sol"):
        a, _ = run_s4x(AS[sym], EX[sym], BASE, None, None, cfg=NOHALT)
        b, _ = run_s4x(AS[sym], EX[sym], x, None, None, cfg=NOHALT)
        assert _same(a.trades, b.trades), (x.name, sym)


# G8: fire logic on hand-built bars
H = 14400


class _E:
    def __init__(self, n, rv=0.01, t=None):
        self.rv42 = [rv] * n
        self.tstat = {L: [t] * n for L in (30, 90, 270, 810)}
        self.atr_mean = [1.0] * n
        self.sma1200 = [100.0] * n
        self.er60 = [0.5] * n
        self.ret20z = [0.0] * n


def _asset(n=6, atr=1.0):
    ind = Ind(sma50=100.0, sma200=100.0, rsi14=50.0, atr14=atr, vol_sma20=1.0,
              hi20=200.0, lo20=1.0)
    bars = [Bar(ts=k * H, open=100, high=100.5, low=99.5, close=100, volume=1) for k in range(n)]
    return Asset("syn", bars, [ind] * n, [200.0] * n, [1.0] * n, [0.5] * n, [atr] * n)


def _short_book(qty=1.0):
    b = Book(cfg=S4_CFG)
    b.position = Position(side="S", entry_ts=0, entry_price=100.0, qty=qty, notional=100.0 * qty,
                          stop_price=110.0, atr_at_entry=1.0, signal_ts=-H, fee_bps=12.0, trail=110.0)
    st = _fresh_state(1.0, 100.0)
    st.update(qty0=qty, frac=1.0, vol0=0.01, sar=None, ep=None, af=None)
    b._st = st
    return b


def _step(b, A, E, i, x, **bar):
    br = Bar(ts=i * H, **{**dict(open=100, high=100.5, low=99.5, close=100, volume=1), **bar})
    A.bars[i] = br
    s4_step_x(b, br, A.inds[i], i, A, E, RESEARCH_TRADE, None, x)


def test_scale_partial_fills_next_open():
    A, E = _asset(), _E(6, rv=0.02)                       # vol doubled vs entry 0.01
    b, x = _short_book(), X(vs_band=0.25, vs_kind="rv")
    _step(b, A, E, 1, x)
    assert b.trades == [] and abs(b._st["flag_f"] - 0.5) < 1e-12      # judged at this close
    _step(b, A, E, 2, x, open=99.2)
    t = b.trades[-1]
    assert t.exit_reason == "SCALE" and t.exit_price == 99.2 and abs(t.qty - 0.5) < 1e-9
    assert abs(b._st["frac"] - 0.5) < 1e-9 and b.position.qty == 0.5


def test_trend_flip_exits_next_open():
    A, E = _asset(), _E(6, t=+3.0)                         # trend now UP against the short
    b, x = _short_book(), X(ts_set=(30,), ts_div=2.0, ts_mode="flip")
    _step(b, A, E, 1, x)
    assert b.trades == []
    _step(b, A, E, 2, x, open=100.7)
    assert b.trades[-1].exit_reason == "TREND" and b.trades[-1].exit_price == 100.7


def test_no_flag_on_fill_bar():
    A, E = _asset(), _E(6, rv=0.05, t=+3.0)
    b = _short_book()
    x = X(vs_band=0.10, vs_kind="rv", ts_set=(30,), ts_mode="flip")
    _step(b, A, E, 0, x)                                   # bar 0 is the fill bar
    assert b._st["flag"] is None


def test_psar_tightens_and_binds():
    A, E = _asset(n=12, atr=10.0), _E(12)                  # wide 5-ATR trail, so the SAR binds first
    b, x = _short_book(), X(psar_max=0.2)
    b.position.trail = None                                # SAR initialises from the trail
    _step(b, A, E, 0, x)                                   # fill bar: SAR := trail
    sar0 = b._st["sar"]
    for i, lo in zip(range(1, 6), (98, 96, 94, 92, 90)):
        _step(b, A, E, i, x, open=lo + 1, high=lo + 1.2, low=lo, close=lo + 0.5)
    assert b._st["sar"] < sar0 and b._st["af"] > 0.02     # accelerated toward price
    lvl = b._st["sar"]
    _step(b, A, E, 6, x, open=lvl - 0.5, high=lvl + 1, low=lvl - 1, close=lvl)
    t = b.trades[-1]
    assert t.exit_reason == "SAR" and t.exit_price == max(lvl, lvl - 0.5)   # touched: fills at the level
