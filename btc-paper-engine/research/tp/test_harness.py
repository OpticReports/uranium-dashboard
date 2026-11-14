"""Gate tests for the take-profit harness. Merge-blocking for RESEARCH_TP.md:
if any fails, no study number is valid.

run: cd research/tp && python -m pytest -q test_harness.py
"""
import dataclasses
import importlib.util
import os
import sys

import pytest

from harness import (BASE, S3_CFG, S4_CFG, T_2013, T_2022, T_IS_END, Book,
                     Position, RESEARCH_SIGNAL, RESEARCH_TRADE, V,
                     _close_full, _close_part, blend_exit_step, load_asset,
                     prepare, run_s3, run_s4)
from app.engine.core import _close_position
from app.engine.replay import run_replay
from variants import ROUND1, ROUND3, ROUND4

ASSETS = {s: load_asset(s) for s in ("btc", "eth", "ltc", "xrp", "bch")}
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)


def _same(a, b):
    return len(a) == len(b) and all(
        dataclasses.asdict(x) == dataclasses.asdict(y) for x, y in zip(a, b))


# G1: BASE reproduces the engine's S4 trade list exactly, every asset/window,
# with the deployed halt and with the halt off.
@pytest.mark.parametrize("sym", list(ASSETS))
@pytest.mark.parametrize("win", [(None, None), (T_2013, T_IS_END), (T_2022, T_IS_END)])
@pytest.mark.parametrize("cfg", [S4_CFG, NOHALT])
def test_g1_base_is_engine(sym, win, cfg):
    A = ASSETS[sym]
    rr = run_replay(A.bars, [cfg], RESEARCH_SIGNAL, RESEARCH_TRADE,
                    start_ts=win[0], end_ts=win[1])
    book, _ = run_s4(A, BASE, win[0], win[1], cfg=cfg)
    assert _same(rr.books["S4"].trades, book.trades)


# G2: S3 through the harness loop is the engine's S3.
def test_g2_s3_is_engine():
    A = ASSETS["btc"]
    rr = run_replay(A.bars, [S3_CFG], RESEARCH_SIGNAL, RESEARCH_TRADE,
                    start_ts=T_2022, end_ts=T_IS_END)
    b3, _ = run_s3(A, T_2022, T_IS_END)
    assert _same(rr.books["S3"].trades, b3.trades)


# G3: the exit-step blend is bench_blend.blend_curve plus the window start.
def test_g3_blend_matches_bench():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "backend",
                        "scripts", "bench_blend.py")
    argv = sys.argv
    sys.argv = ["bench_blend.py", "unused.csv"]
    try:
        spec = importlib.util.spec_from_file_location("bench_blend", path)
        bb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bb)
    finally:
        sys.argv = argv
    A = ASSETS["btc"]
    b3, _ = run_s3(A, T_2022, T_IS_END)
    b4, _ = run_s4(A, BASE, T_2022, T_IS_END)
    ref = bb.blend_curve(b3, b4, 0.30, 1.5, T_2022, T_IS_END)
    mine = blend_exit_step(b3, b4, 0.30, 1.5, T_2022, T_IS_END)
    assert mine[0] == (T_2022, 1.0)
    assert mine[1:] == ref


# G4: no look-ahead. Truncating the future changes nothing that closed
# before the cut, for every registered variant.
@pytest.mark.parametrize("v", ROUND1 + ROUND3 + ROUND4, ids=lambda v: v.name)
def test_g4_no_lookahead(v):
    A = ASSETS["btc"]
    full, _ = run_s4(A, v, T_2022, None, cfg=NOHALT)
    for cut in (24000, 27500, 31000):          # all inside the 2022+ run (G4 cut fix)
        At = prepare("btc", A.bars[:cut])
        part, _ = run_s4(At, v, T_2022, None, cfg=NOHALT)
        last = A.bars[cut - 1].ts
        a = [t for t in full.trades if t.exit_ts <= last]
        b = [t for t in part.trades if t.exit_ts <= last]
        assert _same(a, b), (v.name, cut)


# G5: a partial close then a full close at one price books exactly what one
# full close books (P&L, fees, equity), to float precision.
def test_g5_partial_accounting():
    for side in ("L", "S"):
        def mk():
            b = Book(cfg=S4_CFG)
            p = Position(side=side, entry_ts=0, entry_price=50_000.0,
                         qty=1.234567, notional=1.234567 * 50_000.0,
                         stop_price=0.0, atr_at_entry=900.0, signal_ts=0,
                         fee_bps=12.0)
            b.position = p
            return b, p
        b1, p1 = mk()
        _close_position(b1, p1, 14400, 53_210.5, "X", RESEARCH_TRADE)
        b2, p2 = mk()
        _close_part(b2, p2, 0.411522, 14400, 53_210.5, "TP_PART")
        _close_full(b2, p2, 14400, 53_210.5, "X", RESEARCH_TRADE)
        assert b2.equity == pytest.approx(b1.equity, rel=0, abs=1e-6)
        assert sum(t.fees_usd for t in b2.trades) == pytest.approx(
            b1.trades[0].fees_usd, rel=0, abs=1e-9)


# G6: every hook set to a never-firing value is the baseline, exactly.
NOOPS = [V(name="n_tp", tp_k=1e9), V(name="n_ptp", ptp_k=1e9, ptp_f=0.5),
         V(name="n_lock", lock_k=1e9, lock_m=2.5), V(name="n_be", be_k=1e9),
         V(name="n_ext", ext_z=1e9), V(name="n_rsi", rsi_l=-1.0),
         V(name="n_time", time_n=10 ** 9), V(name="n_clx", climax_k=1e9),
         V(name="n_er", er_k=1e9, er_x=0.3), V(name="n_volx", volx_v=1e9),
         V(name="n_plc", placebo_q=0.0), V(name="n_lock5", lock_k=0.0, lock_m=5.0)]


@pytest.mark.parametrize("v", NOOPS, ids=lambda v: v.name)
def test_g6_noop_is_base(v):
    A = ASSETS["btc"]
    a, _ = run_s4(A, BASE, None, None, cfg=NOHALT)
    b, _ = run_s4(A, v, None, None, cfg=NOHALT)
    assert _same(a.trades, b.trades)


# G7 (AMENDMENT 1): stand-aside only ever blocks entries after a profit exit.
# A never-firing take-profit with a cooldown is the baseline; a zero cooldown
# is the underlying rule; the cooldown leaves stop-outs re-arming at once.
@pytest.mark.parametrize("v", ROUND4, ids=lambda v: v.name)
def test_g7_cooldown_plumbing(v):
    A = ASSETS["btc"]
    base, _ = run_s4(A, BASE, None, None, cfg=NOHALT)
    never, _ = run_s4(A, V(name="n", tp_k=1e9, cool_n=30), None, None, cfg=NOHALT)
    assert _same(base.trades, never.trades)
    under = dataclasses.replace(v, cool_n=None)
    zero = dataclasses.replace(v, cool_n=0)
    a, _ = run_s4(A, under, None, None, cfg=NOHALT)
    b, _ = run_s4(A, zero, None, None, cfg=NOHALT)
    assert _same(a.trades, b.trades)
    c, _ = run_s4(A, v, None, None, cfg=NOHALT)
    # no same-side entry lands within 30 bars of a profit exit on that side
    for t1, t2 in zip(c.trades, c.trades[1:]):
        if t1.exit_reason in ("TP", "EXT", "RSI", "TIME", "CLIMAX", "ER", "VOLX") and t2.side == t1.side:
            assert t2.entry_ts - t1.exit_ts > 30 * 14400 - 1
