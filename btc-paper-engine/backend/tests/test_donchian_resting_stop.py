"""Gate: the donchian trail is tested as the RESTING stop the venue holds
(RESEARCH_CAGR.md H1, 2026-09-29). Merge-blocking."""
from app.engine.core import (Bar, Book, BookCfg, Ind, Position, TradeCfg,
                             _process_donchian)

TCFG = TradeCfg()


def _book(trail, entry_ts=0):
    b = Book(cfg=BookCfg(name="S4", sizing="fixed", strategy="donchian",
                         trail_atr=5.0, start_equity=100_000.0, dd_halt=0.5))
    b.position = Position(side="L", entry_ts=entry_ts, entry_price=100.0,
                          qty=1.0, notional=100.0, stop_price=trail,
                          atr_at_entry=1.0, signal_ts=0, fee_bps=0.0,
                          trail=trail)
    return b


IND = Ind(sma50=None, sma200=None, rsi14=None, atr14=2.0, vol_sma20=None)


def test_wick_below_new_level_but_above_resting_stop_holds():
    """Resting trail 90. Bar t wicks to 94 and closes at 110: the ratchet from
    close(t) is 110 - 5*2 = 100. The old order tested the 94 low against 100
    and booked an exit the venue (holding 90) never took."""
    b = _book(trail=90.0)
    _process_donchian(b, Bar(ts=4 * 3600, open=100, high=111, low=94,
                             close=110, volume=1), IND, TCFG, None)
    assert b.position is not None, "a resting stop at 90 is not hit by a 94 low"
    assert b.position.trail == 100.0, "trail ratchets from the close AFTER the test"


def test_touch_of_resting_stop_fills_at_the_level():
    b = _book(trail=90.0)
    _process_donchian(b, Bar(ts=4 * 3600, open=95, high=96, low=89, close=92,
                             volume=1), IND, TCFG, None)
    assert b.position is None
    assert b.trades[-1].exit_price == 90.0


def test_gap_through_the_stop_fills_at_the_open():
    b = _book(trail=90.0)
    _process_donchian(b, Bar(ts=4 * 3600, open=85, high=87, low=80, close=86,
                             volume=1), IND, TCFG, None)
    assert b.trades[-1].exit_price == 85.0, "a gap fills at the open, not the level"


def test_no_stop_test_on_the_entry_bar():
    b = _book(trail=90.0, entry_ts=4 * 3600)
    _process_donchian(b, Bar(ts=4 * 3600, open=100, high=101, low=80, close=100,
                             volume=1), IND, TCFG, None)
    assert b.position is not None
