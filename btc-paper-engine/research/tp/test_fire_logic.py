"""G8: fire-logic gates on hand-built bars (counter-agent A, defect 2: the
replay gates could not see a TP filled at its level after a gap, or a
close-based exit filled on the bar that triggered it - two planted mutants
passed 81/81). Each case drives s4_step directly.

run: cd research/tp && python -m pytest -q test_fire_logic.py
"""
import random

from harness import (Asset, Bar, Book, Ind, Position, RESEARCH_TRADE, S4_CFG,
                     V, _fresh_state, s4_step)

H = 14400


def asset(n=4, atr=1.0):
    ind = Ind(sma50=100.0, sma200=100.0, rsi14=50.0, atr14=atr, vol_sma20=1.0,
              hi20=200.0, lo20=1.0)
    return Asset("syn", [None] * n, [ind] * n, [200.0] * n, [1.0] * n,
                 [0.5] * n, [atr] * n)


def short_book(entry=100.0, trail=110.0, atr0=1.0):
    b = Book(cfg=S4_CFG)
    b.position = Position(side="S", entry_ts=0, entry_price=entry, qty=1.0,
                          notional=entry, stop_price=trail, atr_at_entry=atr0,
                          signal_ts=-H, fee_bps=12.0, trail=trail)
    b._st = _fresh_state(atr0, entry)
    return b


def step(b, A, i, bar, v):
    s4_step(b, bar, A.inds[i], i, A, RESEARCH_TRADE, None, v, random.Random(0))


def test_tp_gap_fills_at_open():
    A, b, v = asset(), short_book(), V(tp_k=3.0)          # TP buy limit at 97
    step(b, A, 1, Bar(ts=H, open=95.0, high=95.5, low=94.0, close=94.5, volume=1), v)
    t = b.trades[-1]
    assert t.exit_reason == "TP" and t.exit_price == 95.0  # not 97


def test_tp_touch_fills_at_level():
    A, b, v = asset(), short_book(), V(tp_k=3.0)
    step(b, A, 1, Bar(ts=H, open=99.0, high=99.5, low=96.5, close=97.5, volume=1), v)
    assert b.trades[-1].exit_price == 97.0


def test_stop_beats_tp_in_one_bar():
    A, b, v = asset(), short_book(trail=101.0), V(tp_k=3.0)
    step(b, A, 1, Bar(ts=H, open=100.0, high=101.5, low=96.0, close=98.0, volume=1), v)
    assert b.trades[-1].exit_reason == "STOP" and b.trades[-1].exit_price == 101.0


def test_close_based_exit_fills_next_open():
    A, b, v = asset(), short_book(), V(time_n=1)
    step(b, A, 1, Bar(ts=H, open=99.0, high=99.5, low=98.0, close=98.5, volume=1), v)
    assert b.trades == [] and b.position is not None       # judged at this close...
    step(b, A, 2, Bar(ts=2 * H, open=97.7, high=98.0, low=97.0, close=97.5, volume=1), v)
    t = b.trades[-1]
    assert t.exit_reason == "TIME" and t.exit_ts == 2 * H and t.exit_price == 97.7


def test_no_close_based_exit_on_fill_bar():
    A, b, v = asset(), short_book(), V(time_n=0)
    step(b, A, 0, Bar(ts=0, open=100.0, high=100.5, low=99.0, close=99.5, volume=1), v)
    assert b._st["flag"] is None                           # the fill bar is exempt


def test_partial_tp_takes_fraction_once():
    A, b, v = asset(), short_book(), V(ptp_k=3.0, ptp_f=0.5)
    for i, lo in ((1, 96.0), (2, 95.0)):
        step(b, A, i, Bar(ts=i * H, open=98.0, high=98.5, low=lo, close=97.0, volume=1), v)
    parts = [t for t in b.trades if t.exit_reason == "TP_PART"]
    assert len(parts) == 1 and parts[0].qty == 0.5 and b.position.qty == 0.5


def test_stand_aside_blocks_same_side_only():
    A = asset(n=40)
    b = Book(cfg=S4_CFG)
    b._st = {}
    b._cool = ("S", 0)
    v = V(tp_k=3.0, cool_n=30)
    # same side blocked through bar 29 after the exit bar (signals at bars
    # 0..29 suppressed, so the earliest re-entry fills at bar 31); the
    # opposite side is never blocked
    for side, i, blocked in (("S", 5, True), ("L", 5, False), ("S", 29, True),
                             ("L", 29, False), ("S", 30, False), ("S", 31, False)):
        b.pending = None
        s4_step(b, Bar(ts=i * H, open=100, high=100, low=100, close=100, volume=1),
                A.inds[i], i, A, RESEARCH_TRADE, side, v, random.Random(0))
        assert (b.pending is None) == blocked, (side, i)
