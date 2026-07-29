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
