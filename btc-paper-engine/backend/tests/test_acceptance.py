"""Spec §6 acceptance: replay 2024-07-24 -> 2026-07-24 must reproduce the
research backtest. The research-basis comparison reproduces every table row
EXACTLY (0.0 deviation) on the frozen fixture; tolerances kept as specced so a
future fixture refresh (revised exchange data) degrades gracefully.

Known artifact (documented, not a bug): the reference CSV's timestamp labels
are shifted +1 bar for trades before ~2024-09-10 (its own dataset stitching);
entry/exit PRICES match ours to the penny for all 89 trades, so identity is
checked on prices, with timestamps required to match within one bar.
"""
import csv
import os
from datetime import datetime, timezone

from app.engine.core import Bar, BookCfg, SignalCfg, TradeCfg
from app.engine.replay import book_stats, research_basis_stats, run_replay

HERE = os.path.dirname(__file__)
FIX = os.path.join(HERE, "fixtures", "bars_4h_btcusd.csv")
REF = os.path.join(HERE, "..", "reference", "btc_trades_limit_entry_reference.csv")

BOOKS = [
    BookCfg(name="S1", sizing="vol_target", risk=0.055, long_mult=0.75, cap=3.0, dd_halt=0.30),
    BookCfg(name="S2", sizing="fixed", leverage=1.95, long_mult=0.75, cap=2.5, dd_halt=0.45),
    BookCfg(name="S3", sizing="fixed", leverage=1.0, long_mult=1.0, cap=1.0, dd_halt=0.30),
]


def _ts(s):
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def _replay():
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(FIX))]
    return run_replay(bars, BOOKS, SignalCfg(), TradeCfg(),
                      start_ts=_ts("2024-07-24 00:00"), end_ts=_ts("2026-07-24 00:00"))


def test_acceptance_table():
    res = _replay()
    trades = res.books["S3"].trades
    ref = list(csv.DictReader(open(REF)))

    # trade count & exit mix & win rate
    assert abs(len(trades) - 89) <= 2
    mix = {r: sum(1 for t in trades if t.exit_reason == r) for r in ("SIGNAL", "STOP")}
    assert abs(mix["SIGNAL"] - 58) <= 3 and abs(mix["STOP"] - 31) <= 3
    wr = 100 * sum(1 for t in trades if t.pnl_usd > 0) / len(trades)
    assert abs(wr - 62.9) <= 1.5

    # research-basis book table
    rb = research_basis_stats(trades, TradeCfg(), BOOKS)
    assert abs(rb["S3"]["total_return_pct"] - 48.1) <= 3
    assert abs(rb["S3"]["max_dd_pct"] - -14.2) <= 2
    assert abs(rb["S1"]["total_return_pct"] - 64.5) <= 4
    assert abs(rb["S1"]["max_dd_pct"] - -22.3) <= 2
    assert abs(rb["S2"]["total_return_pct"] - 101.4) <= 5
    assert abs(rb["S2"]["max_dd_pct"] - -22.9) <= 2
    oos = research_basis_stats(trades, TradeCfg(), BOOKS, from_ts=_ts("2025-12-01 00:00"))
    assert abs(oos["S1"]["total_return_pct"] - 29.9) <= 3
    assert abs(oos["S1"]["max_dd_pct"] - -10.3) <= 2

    # per-trade identity on PRICES (>=95%), timestamps within one bar
    n_match = 0
    for r, t in zip(ref, trades):
        prices_ok = (abs(float(r["entry_price"]) - t.entry_price) <= 0.01
                     and abs(float(r["exit_price"]) - t.exit_price) <= 0.05
                     and r["exit_reason"] == t.exit_reason)
        ref_sig = int(datetime.strptime(r["signal_bar"], "%Y-%m-%d %H:%M:%S%z").timestamp())
        ts_ok = abs(ref_sig - t.signal_ts) <= 4 * 3600
        n_match += prices_ok and ts_ok
    assert n_match / len(ref) >= 0.95, f"only {n_match}/{len(ref)} matched"


def test_dollar_vs_research_basis_gap_is_short_squared_terms():
    """The live dollar book must land BELOW the research basis (short
    accounting) within a BOUNDED BAND — a guard against silently changing
    either basis.

    REBASED 2026-09-21, and the reason is the point of the test. The old
    bound was one-sided, `research - dollar < 10.0`, and it passed at 9.6
    ONLY because the dollar path was under-charging S3. `_process_pullback`
    built its Position without `fee_bps`, taking the 6.0 default, while
    `research_basis_stats` charges `2 * tcfg.taker_fee_bps` = 12.00 — so the
    two bases were running on fees that differed by 2x and the accidental
    offset flattered the dollar book into the bound. With the wiring fixed
    both bases charge 12.00 and the true basis gap is 13.7pp
    (research 48.1, dollar 34.4).

    Now TWO-SIDED, so the defect cannot return quietly: if a pullback book
    ever stops charging the configured fee again, its dollar return rises,
    the gap collapses back toward 9.6 and the LOWER bound fires. A one-sided
    bound is what let this sit undetected.
    """
    res = _replay()
    dollar = book_stats(res.books["S3"])["total_return_pct"]
    research = research_basis_stats(res.books["S3"].trades, TradeCfg(), BOOKS)["S3"]["total_return_pct"]
    gap = research - dollar
    assert research > dollar          # ratio basis flatters shorts
    assert 11.5 < gap < 16.0, (
        f"basis gap {gap:.1f}pp is outside the band measured on a correctly "
        f"charged engine (13.7pp); below it usually means a book stopped "
        f"charging the configured fee")
