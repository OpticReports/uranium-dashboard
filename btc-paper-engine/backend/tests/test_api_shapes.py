from app.engine.core import Bar
from app.main import _hold_stats


def _bar(ts, o, c):
    return Bar(ts=ts, open=o, high=max(o, c), low=min(o, c), close=c, volume=1.0)


def test_hold_stats_benchmark():
    # buy at first OPEN (100) with one 6bp taker fee; ride 100 -> 90 -> 120
    bars = [_bar(0, 100.0, 100.0), _bar(14400, 100.0, 90.0),
            _bar(28800, 90.0, 120.0)]
    h = _hold_stats(bars, 100_000.0, 6.0)
    qty = 100_000.0 * (1 - 0.0006) / 100.0
    assert h["trades"] == 1 and h["synthetic"] is True
    assert h["equity"] == round(qty * 120.0, 2)
    assert h["total_return_pct"] == round(100 * (qty * 120.0 / 100_000.0 - 1), 1)
    # drawdown measured off the close path peak (100 -> 90 = -10%)
    assert h["max_dd_pct"] == -10.0
    assert h["win_rate"] is None and h["profit_factor"] is None
    # too short for annualized stats -> None, same rule as the books
    assert h["sharpe"] is None and h["cagr_pct"] is None


def test_hold_stats_needs_two_bars():
    assert _hold_stats([_bar(0, 100.0, 100.0)], 100_000.0, 6.0) is None
    assert _hold_stats([], 100_000.0, 6.0) is None


def test_hold_dd_counts_first_bar_decline():
    # QA nit: peak seeded at the first CLOSE hid an open->close drop on bar 1
    bars = [_bar(0, 100.0, 80.0), _bar(14400, 80.0, 90.0)]
    h = _hold_stats(bars, 100_000.0, 6.0)
    assert h["max_dd_pct"] == -20.0


def test_mark_to_market_values_open_positions():
    # QA finding: exit-only DD flattered books vs HOLD; MTM must see the
    # trough an open position rides through even if the trade later closes
    # at a profit.
    from app.engine.core import Book, BookCfg, Position, _mark_to_market
    b = Book(cfg=BookCfg(name="T", sizing="fixed", start_equity=100_000.0))
    b.position = Position(side="L", entry_ts=0, entry_price=100.0, qty=1000.0,
                          notional=100_000.0, stop_price=0.0, atr_at_entry=1.0,
                          signal_ts=0)
    _mark_to_market(b, 80.0)     # -20% trough while open
    _mark_to_market(b, 120.0)    # recovers to +20%
    assert abs(b.mtm_max_dd + 0.2) < 1e-9
    assert b.mtm_equity == 120_000.0
    assert b.mtm_peak == 120_000.0
    # short side: price falling is a gain
    b2 = Book(cfg=BookCfg(name="T2", sizing="fixed", start_equity=100_000.0))
    b2.position = Position(side="S", entry_ts=0, entry_price=100.0, qty=1000.0,
                           notional=100_000.0, stop_price=0.0, atr_at_entry=1.0,
                           signal_ts=0)
    _mark_to_market(b2, 90.0)
    assert b2.mtm_equity == 110_000.0 and b2.mtm_max_dd == 0.0
