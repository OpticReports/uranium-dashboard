"""Execution-simulator edge cases (spec §6 list), driven directly through
process_closed_bar/resolve_open_exit with hand-built indicators."""
from app.engine.core import (
    BAR_SECONDS, Bar, Book, BookCfg, Ind, SignalCfg, TradeCfg,
    process_closed_bar, resolve_open_exit,
)

SC, TC = SignalCfg(), TradeCfg()
T0 = 1_700_000_000 - (1_700_000_000 % BAR_SECONDS)


def _bar(i, o, h, l, c, v=100.0):
    return Bar(ts=T0 + i * BAR_SECONDS, open=o, high=h, low=l, close=c, volume=v)


def _ind(sma50=105.0, sma200=90.0, rsi14=40.0, atr14=2.0, vol=50.0):
    return Ind(sma50=sma50, sma200=sma200, rsi14=rsi14, atr14=atr14, vol_sma20=vol)


def _book(**kw):
    cfg = BookCfg(name="T", sizing="fixed", leverage=1.0, long_mult=1.0, cap=1.0, **kw)
    return Book(cfg=cfg)


def test_unfilled_limit_cancelled_and_can_refire_same_close():
    b = _book()
    process_closed_bar(b, _bar(0, 100, 101, 99, 100), _ind(), SC, TC, "L")
    assert b.pending is not None and b.pending.limit == 100
    # next bar never trades below 100 -> no fill; same close fires a new signal
    process_closed_bar(b, _bar(1, 100.5, 102, 100.2, 101), _ind(), SC, TC, "L")
    assert b.position is None
    assert b.pending is not None and b.pending.limit == 101  # re-armed at new close


def test_fill_and_fill_bar_close_ineligible():
    b = _book()
    process_closed_bar(b, _bar(0, 100, 101, 99, 100), _ind(), SC, TC, "L")
    # fill bar trades through 100 AND closes far above sma50 — exit must NOT flag
    process_closed_bar(b, _bar(1, 100.5, 120, 99.5, 119), _ind(sma50=105), SC, TC, None)
    assert b.position is not None and b.position.entry_price == 100
    assert getattr(b.position, "exit_flag", None) is None
    # next close above sma50 -> flags, executes at following open
    process_closed_bar(b, _bar(2, 119, 121, 118, 120), _ind(sma50=105), SC, TC, None)
    assert getattr(b.position, "exit_flag", None) == "SIGNAL"
    nb = _bar(3, 118.5, 119, 117, 118)
    resolve_open_exit(b, nb, TC)
    t = b.trades[-1]
    assert t.exit_price == 118.5 and t.exit_reason == "SIGNAL" and t.bars_held == 2


def test_stop_beats_signal_exit_same_bar():
    b = _book()
    process_closed_bar(b, _bar(0, 100, 101, 99, 100), _ind(atr14=2.0), SC, TC, "L")
    process_closed_bar(b, _bar(1, 100, 100.5, 99.9, 100.2), _ind(atr14=2.0), SC, TC, None)
    pos = b.position
    assert pos is not None and abs(pos.stop_price - (100 - 5.0)) < 1e-9
    # bar hits the stop intrabar AND closes above sma50: stop wins
    process_closed_bar(b, _bar(2, 100, 120, 94.9, 119), _ind(sma50=105, atr14=2.0), SC, TC, None)
    t = b.trades[-1]
    assert t.exit_reason == "STOP" and abs(t.exit_price - 95.0) < 1e-9


def test_time_stop_fires_at_60_bars():
    b = _book()
    process_closed_bar(b, _bar(0, 100, 101, 99, 100), _ind(atr14=1000.0), SC, TC, "L")
    process_closed_bar(b, _bar(1, 100, 100.5, 99.5, 100), _ind(atr14=1000.0), SC, TC, None)
    assert b.position is not None
    i = 2
    while b.position is not None and i < 70:
        # drift sideways below sma50, never near the (huge-ATR) stop
        process_closed_bar(b, _bar(i, 100, 100.5, 99.5, 100), _ind(sma50=105, atr14=1000.0), SC, TC, None)
        if getattr(b.position, "exit_flag", None):
            resolve_open_exit(b, _bar(i + 1, 100, 100.5, 99.5, 100), TC)
        i += 1
    t = b.trades[-1]
    assert t.exit_reason == "TIME" and t.bars_held == 61  # flagged at 60, filled next open


def test_sizing_cap_clamps_tiny_atr():
    b = _book()
    cfg = BookCfg(name="V", sizing="vol_target", risk=0.055, long_mult=1.0, cap=3.0)
    bv = Book(cfg=cfg)
    process_closed_bar(bv, _bar(0, 100, 101, 99, 100), _ind(atr14=0.01), SC, TC, "L")
    process_closed_bar(bv, _bar(1, 100, 100.5, 99.0, 100), _ind(atr14=0.01), SC, TC, None)
    pos = bv.position
    assert pos is not None
    assert pos.notional <= 3.0 * cfg.start_equity + 1e-6  # clamped, not 22x


def test_dd_halt_blocks_new_entries():
    b = _book(dd_halt=0.02)
    process_closed_bar(b, _bar(0, 100, 101, 99, 100), _ind(atr14=2.0), SC, TC, "L")
    process_closed_bar(b, _bar(1, 100, 100.5, 99.9, 100), _ind(atr14=2.0), SC, TC, None)
    process_closed_bar(b, _bar(2, 95, 96, 94.9, 95), _ind(atr14=2.0), SC, TC, None)  # stopped -5%
    assert b.halted and b.position is None
    process_closed_bar(b, _bar(3, 95, 96, 94, 95), _ind(atr14=2.0), SC, TC, "L")
    assert b.pending is None  # halted book refuses the signal


def test_donchian_book_matches_lab_shape():
    """S4 on the 2024-26 window: trade count/win-rate/DD must match the
    RESEARCH_S4.md lab run (returns differ by documented short accounting)."""
    import csv, os
    from datetime import datetime, timezone
    from app.config import RESEARCH_BOOKS
    from app.engine.replay import run_replay, book_stats
    fix = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(fix))]
    def ts(s): return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    res = run_replay(bars, RESEARCH_BOOKS, SC, TC,
                     start_ts=ts("2024-07-24"), end_ts=ts("2026-07-24"))
    st = book_stats(res.books["S4"])
    assert abs(st["trades"] - 59) <= 3
    assert abs(st["win_rate"] - 33.9) <= 3
    assert abs(st["max_dd_pct"] - -44.3) <= 4
    assert st["exit_mix"]["STOP"] == st["trades"]  # trail-only exits
    # S1-S3 acceptance numbers untouched by the S4 addition
    assert book_stats(res.books["S3"])["trades"] == 89
