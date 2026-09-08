"""A book halt must reach the phone — proven END TO END, not against mocks.

`book.halted` is set inside engine.core._close_position and cleared by
exactly one thing: a human calling POST /books/<name>/resume. It persists
across restarts. Until 2026-09-08 nothing announced it.

The first cut of these tests hand-replicated the loop (Engine.__new__ +
manual resolve_open_exit) and the counter-agent proved they guarded nothing:
the snapshot could be moved after resolve_open_exit, the production
alert_fn wiring could be deleted, and the poll() stop path - the likeliest
halt trigger of all - was never bracketed, and every test still passed.
These drive the real loops against a temp SQLite.
"""
import time

import pytest

import app.alerts as alerts
import app.store.db as db
from app.config import settings
from app.engine.core import BAR_SECONDS, Bar, Book, BookCfg, Pending, Position
from app.live import Engine


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    """Point the engine at a throwaway DB. db._engine is a lazy module
    singleton, so it must be reset around the URL swap."""
    old_url, old_engine = settings.database_url, db._engine
    monkeypatch.setattr(settings, "database_url",
                        f"sqlite:///{tmp_path}/t.db")
    db._engine = None
    db.init_db()
    yield
    db._engine = old_engine
    settings.database_url = old_url


def _bar(ts, px):
    return Bar(ts=ts, open=px, high=px, low=px, close=px, volume=1.0)


def _losing_engine(dd_halt=0.10, exit_flag=None):
    """Engine with one book, long 1 BTC from 100k, halt line 10% below."""
    eng = Engine()
    eng.sent = []
    eng.alert_fn = lambda m: eng.sent.append(m)
    cfg = BookCfg(name="T", sizing="fixed", leverage=1.0,
                  start_equity=100_000.0, dd_halt=dd_halt)
    b = Book(cfg=cfg)
    b.position = Position(side="L", entry_ts=0, entry_price=100_000.0,
                          qty=1.0, notional=100_000.0, stop_price=90_000.0,
                          atr_at_entry=1.0, signal_ts=0)
    if exit_flag:
        b.position.exit_flag = exit_flag       # type: ignore[attr-defined]
    eng.books = {"T": b}
    eng._persisted_trades = {"T": 0}
    return eng, b


# ---------------------------------------------------------------- poll() path

def test_intrabar_stop_out_halt_pages(tmpdb, monkeypatch):
    """poll() runs the protective stop at poll granularity and calls
    _close_position DIRECTLY, then persists. The first cut bracketed
    catch_up only, so this halt - the likeliest one - was lost forever:
    the DB already said halted=True by the next bar."""
    eng, b = _losing_engine()
    now = int(time.time())
    cur_open = now // BAR_SECONDS * BAR_SECONDS
    eng.bars = [_bar(cur_open - BAR_SECONDS, 100_000.0), _bar(cur_open, 100_000.0)]
    eng.last_data_ok = time.time()
    monkeypatch.setattr("app.live.last_price", lambda: 85_000.0)   # through the stop
    monkeypatch.setattr("app.live.kraken_price", lambda: 85_000.0)
    assert b.halted is False
    eng.poll()
    assert b.halted is True and b.halt_reason == "dd_halt"
    assert len(eng.sent) == 1
    assert "T" in eng.sent[0] and "HALTED" in eng.sent[0]
    assert "/books/T/resume" in eng.sent[0]
    assert "dd_halt" in eng.sent[0]
    eng.poll()                                          # persists; no re-page
    assert len(eng.sent) == 1


# ------------------------------------------------------------- catch_up() path

def test_resolve_open_exit_halt_pages_through_catch_up(tmpdb):
    """The snapshot must sit BEFORE resolve_open_exit. Moving it after made
    every first-cut test still pass; this one fails if it moves."""
    eng, b = _losing_engine(exit_flag="SIGNAL")
    now = int(time.time())
    t1 = now // BAR_SECONDS * BAR_SECONDS - BAR_SECONDS      # closed bar
    eng.bars = [_bar(t1 - BAR_SECONDS, 100_000.0), _bar(t1, 85_000.0)]
    eng.last_processed = t1 - BAR_SECONDS
    with db.session_scope() as s:
        eng.catch_up(s)
    assert b.halted is True
    assert len(eng.sent) == 1 and "HALTED" in eng.sent[0]


def test_halt_pages_once_across_bars(tmpdb):
    eng, b = _losing_engine(exit_flag="SIGNAL")
    now = int(time.time())
    t1 = now // BAR_SECONDS * BAR_SECONDS - 2 * BAR_SECONDS
    eng.bars = [_bar(t1 - BAR_SECONDS, 100_000.0), _bar(t1, 85_000.0),
                _bar(t1 + BAR_SECONDS, 85_000.0)]
    eng.last_processed = t1 - BAR_SECONDS
    with db.session_scope() as s:
        eng.catch_up(s)                                # both bars processed
    assert b.halted is True and len(eng.sent) == 1


# ------------------------------------------------------- restart / wiring

def test_boot_restore_of_a_halted_book_does_not_page(tmpdb):
    eng, b = _losing_engine()
    b.halted, b.halt_reason = True, "dd_halt"
    raw = eng._serialize_book(b)
    eng2, b2 = _losing_engine()
    eng2._restore_book(b2, raw)
    assert b2.halted is True and b2.halt_reason == "dd_halt"
    assert eng2.sent == []                            # restore is not an edge


def test_production_wiring_is_the_real_telegram_sender():
    """Engine.__new__ in the first-cut tests skipped __init__, so deleting
    this line passed the suite while production raised AttributeError
    inside the alert's own try/except - logged, never paged."""
    assert Engine().alert_fn is alerts.send


def test_alerting_failure_cannot_stall_the_loop(tmpdb, monkeypatch):
    eng, b = _losing_engine()
    now = int(time.time())
    cur_open = now // BAR_SECONDS * BAR_SECONDS
    eng.bars = [_bar(cur_open - BAR_SECONDS, 100_000.0), _bar(cur_open, 100_000.0)]
    eng.last_data_ok = time.time()
    monkeypatch.setattr("app.live.last_price", lambda: 85_000.0)
    monkeypatch.setattr("app.live.kraken_price", lambda: 85_000.0)

    def boom(_m):
        raise RuntimeError("telegram down")

    eng.alert_fn = boom
    eng.poll()                                        # must not raise
    assert b.halted is True


# ------------------------------------------------------- the /halt endpoint

def test_manual_halt_drops_pending_and_records_reason(tmpdb, monkeypatch):
    """`halted` only blocks NEW pendings; a resting one still filled on the
    next bar, so a halted book opened a position the executor then mirrored
    with real money. /halt must drop it, and say it was manual."""
    from fastapi.testclient import TestClient
    import app.main as m
    b = m.ENGINE.books["S3"]
    old = (b.halted, b.halt_reason, b.pending)
    try:
        b.pending = Pending(side="L", limit=1.0, signal_ts=1, atr_signal=1.0)
        with TestClient(m.app) as c:
            r = c.post("/books/S3/halt")
        assert r.status_code == 200 and r.json()["pending_dropped"] is True
        assert b.halted is True and b.halt_reason == "manual"
        assert b.pending is None
        with TestClient(m.app) as c:
            c.post("/books/S3/resume")
        assert b.halted is False and b.halt_reason is None
    finally:
        b.halted, b.halt_reason, b.pending = old


def test_manual_halt_is_not_reported_as_a_drawdown(tmpdb):
    eng, b = _losing_engine()
    b.halted, b.halt_reason = True, "manual"
    with db.session_scope() as s:
        eng._alert_new_halts({"T": False}, s)
    assert "operator" in eng.sent[0] and "dd_halt" not in eng.sent[0]
