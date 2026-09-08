"""A book halt must reach the phone.

`book.halted` is set inside engine.core._close_position and is cleared by
exactly one thing: a human calling POST /books/<name>/resume. It is persisted
and restored on boot, so it is permanent until someone acts. Until 2026-09-08
nothing announced it — the book just stopped taking entries, /books still
returned 200, and btc-executor (which never read legs.<n>.halted) booked the
leg going flat as a routine exit. A leg that silently never trades again is
the healthy-while-doing-nothing failure mode.
"""
from app.engine.core import Bar, Book, BookCfg, Position, TradeCfg
from app.engine.core import resolve_open_exit
from app.live import Engine


class _Sess:
    """log_event only ever calls .add()."""

    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)


def _eng(books):
    eng = Engine.__new__(Engine)          # no DB, no network, no poll thread
    eng.books = books
    eng.alert_fn = lambda m: eng.sent.append(m)
    eng.sent = []
    return eng


def _losing_book(dd_halt=0.10):
    cfg = BookCfg(name="T", sizing="fixed", leverage=1.0,
                  start_equity=100_000.0, dd_halt=dd_halt)
    b = Book(cfg=cfg)
    b.equity = b.peak_equity = 100_000.0
    b.position = Position(side="L", entry_ts=0, entry_price=100_000.0,
                          qty=1.0, notional=100_000.0, stop_price=0.0,
                          atr_at_entry=1.0, signal_ts=0)
    b.position.exit_flag = "SIGNAL"       # type: ignore[attr-defined]
    return b


def test_halt_on_the_resolve_open_exit_path_pages():
    """The snapshot must be taken BEFORE resolve_open_exit, not just around
    process_closed_bar: that path closes a position too, so it trips dd_halt
    just the same. Placing the snapshot after it would miss this halt."""
    b = _losing_book()
    eng = _eng({"T": b})
    was = {n: x.halted for n, x in eng.books.items()}
    resolve_open_exit(b, Bar(ts=14400, open=85_000.0, high=85_000.0,
                             low=85_000.0, close=85_000.0, volume=1.0),
                      TradeCfg())
    assert b.halted is True               # precondition: the halt really fired
    s = _Sess()
    eng._alert_new_halts(was, s)
    assert len(eng.sent) == 1
    msg = eng.sent[0]
    assert "T" in msg and "HALTED" in msg
    assert "/books/T/resume" in msg       # names the ONLY thing that clears it
    assert "survives restarts" in msg
    assert len(s.rows) == 1               # and it is in the event log


def test_halt_pages_once_not_every_bar():
    """Level-triggered would page forever: nothing clears the flag by code."""
    b = _losing_book()
    eng = _eng({"T": b})
    b.halted = True
    eng._alert_new_halts({"T": True}, _Sess())     # already halted last bar
    assert eng.sent == []


def test_no_page_while_healthy():
    b = _losing_book()
    eng = _eng({"T": b})
    eng._alert_new_halts({"T": False}, _Sess())
    assert eng.sent == []


def test_alerting_failure_cannot_stall_the_bar_loop():
    """Alerting is best-effort by design everywhere else in this repo; a
    Telegram outage must not be able to stop the engine processing bars."""
    b = _losing_book()
    eng = _eng({"T": b})

    def boom(_m):
        raise RuntimeError("telegram down")

    eng.alert_fn = boom
    b.halted = True
    eng._alert_new_halts({"T": False}, _Sess())    # must not raise


def test_reports_the_drawdown_that_tripped_it():
    b = _losing_book()
    eng = _eng({"T": b})
    b.equity, b.peak_equity, b.halted = 84_000.0, 100_000.0, True
    eng._alert_new_halts({"T": False}, _Sess())
    assert "-16.00%" in eng.sent[0] and "-10% dd_halt" in eng.sent[0]
