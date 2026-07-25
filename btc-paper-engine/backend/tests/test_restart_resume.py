"""Restart-resume: killing the engine at ANY bar and rebooting from the DB must
produce bit-identical books vs an uninterrupted run. Serialization round-trips
the full mid-flight state: open position (incl. a flagged-but-unexecuted exit),
pending limit order, equity, halt flag.
"""
import csv
import json
import os

from app.config import RESEARCH_BOOKS
from app.engine.core import Bar, Book, SignalCfg, TradeCfg
from app.engine.replay import compute_indicators, run_replay
from app.engine.core import eval_signal, process_closed_bar, resolve_open_exit
from app.live import Engine

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")


def _bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(FIX))]


def _run_span(bars, books, scfg, tcfg, inds, lo, hi):
    for i in range(lo, hi):
        bar = bars[i]
        for b in books.values():
            resolve_open_exit(b, bar, tcfg)
        sig = eval_signal(bar, inds[i], scfg)
        for b in books.values():
            process_closed_bar(b, bar, inds[i], scfg, tcfg, sig)


def test_kill_and_resume_identical_at_many_cut_points():
    bars = _bars()[:2000]
    scfg, tcfg = SignalCfg(), TradeCfg()
    inds = compute_indicators(bars)
    baseline = {c.name: Book(cfg=c) for c in RESEARCH_BOOKS}
    _run_span(bars, baseline, scfg, tcfg, inds, 210, 2000)

    eng = Engine()  # used only for its (de)serializers — no network, no DB
    for cut in (300, 555, 731, 1024, 1500, 1777):
        first = {c.name: Book(cfg=c) for c in RESEARCH_BOOKS}
        _run_span(bars, first, scfg, tcfg, inds, 210, cut)
        # serialize -> fresh books -> restore (simulated process death)
        blobs = {n: eng._serialize_book(b) for n, b in first.items()}
        resumed = {c.name: Book(cfg=c) for c in RESEARCH_BOOKS}
        for n, b in resumed.items():
            eng._restore_book(b, blobs[n])
            b.trades = list(first[n].trades)      # closed trades come from DB rows
        _run_span(bars, resumed, scfg, tcfg, inds, cut, 2000)
        for n in resumed:
            a, z = resumed[n], baseline[n]
            assert abs(a.equity - z.equity) < 1e-6, (cut, n)
            assert len(a.trades) == len(z.trades), (cut, n)
            for ta, tz in zip(a.trades, z.trades):
                assert ta.entry_ts == tz.entry_ts and ta.exit_ts == tz.exit_ts
                assert abs(ta.pnl_usd - tz.pnl_usd) < 1e-6


def test_serialize_roundtrip_preserves_exit_flag_and_pending():
    eng = Engine()
    bars = _bars()
    scfg, tcfg = SignalCfg(), TradeCfg()
    inds = compute_indicators(bars)
    books = {c.name: Book(cfg=c) for c in RESEARCH_BOOKS}
    saw_flag = saw_pending = False
    for i in range(210, len(bars)):
        _run_span(bars, books, scfg, tcfg, inds, i, i + 1)
        for b in books.values():
            blob = eng._serialize_book(b)
            d = json.loads(blob)
            if b.pending is not None:
                saw_pending = True
                assert d["pending"]["limit"] == b.pending.limit
            if b.position is not None and getattr(b.position, "exit_flag", None):
                saw_flag = True
                assert d["position"]["exit_flag"] == b.position.exit_flag
        if saw_flag and saw_pending:
            break
    assert saw_flag and saw_pending
