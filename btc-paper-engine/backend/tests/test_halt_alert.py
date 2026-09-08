"""A book halt must reach the phone - proven END TO END, not against mocks.

`book.halted` is set by engine.core._close_position (dd_halt), by
POST /books/<n>/halt, or arrives already set from reset_books; it is cleared
by exactly one thing, POST /books/<n>/resume, and persists across restarts.
Until 2026-09-08 nothing announced it.

Design under test: announced-vs-halted (Book.halt_announced), scanned by
Engine._announce_halts at every persist site. Two review panels broke the
earlier snapshot-vs-now design: it lost the edge to the poll() stop path it
did not bracket, and to any exception between the halting close and the
compare. These tests drive the real loops against a temp SQLite.
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
    old_url, old_engine = settings.database_url, db._engine
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/t.db")
    db._engine = None
    db.init_db()
    yield
    db._engine = old_engine
    settings.database_url = old_url


def _bar(ts, px):
    return Bar(ts=ts, open=px, high=px, low=px, close=px, volume=1.0)


def _losing_engine(dd_halt=0.10, exit_flag=None, name="T"):
    """Engine with one book, long 1 BTC from 100k, halt line 10% below."""
    eng = Engine()
    eng.sent = []
    eng.alert_fn = lambda m: eng.sent.append(m)
    cfg = BookCfg(name=name, sizing="fixed", leverage=1.0,
                  start_equity=100_000.0, dd_halt=dd_halt)
    b = Book(cfg=cfg)
    b.position = Position(side="L", entry_ts=0, entry_price=100_000.0,
                          qty=1.0, notional=100_000.0, stop_price=90_000.0,
                          atr_at_entry=1.0, signal_ts=0)
    if exit_flag:
        b.position.exit_flag = exit_flag       # type: ignore[attr-defined]
    eng.books = {name: b}
    eng._persisted_trades = {name: 0}
    return eng, b


def _arm_poll(eng, monkeypatch, px=85_000.0):
    now = int(time.time())
    cur_open = now // BAR_SECONDS * BAR_SECONDS
    eng.bars = [_bar(cur_open - BAR_SECONDS, 100_000.0), _bar(cur_open, 100_000.0)]
    eng.last_data_ok = time.time()
    monkeypatch.setattr("app.live.last_price", lambda: px)
    monkeypatch.setattr("app.live.kraken_price", lambda: px)


# ---------------------------------------------------------------- poll() path

def test_intrabar_stop_out_halt_pages(tmpdb, monkeypatch):
    """poll() runs the protective stop at poll granularity and calls
    _close_position DIRECTLY. Largest single loss a book takes, the
    likeliest way to cross dd_halt, and the only way to halt BETWEEN bars.
    The first cut never announced it."""
    eng, b = _losing_engine()
    _arm_poll(eng, monkeypatch)
    eng.poll()
    assert b.halted is True and b.halt_reason == "dd_halt"
    assert b.halt_announced is True
    assert len(eng.sent) == 1
    m = eng.sent[0]
    assert "T" in m and "HALTED" in m and "/books/T/resume" in m and "dd_halt" in m
    eng.poll()
    assert len(eng.sent) == 1                          # idempotent


# ------------------------------------------------------------- catch_up() path

def test_resolve_open_exit_halt_pages_through_catch_up(tmpdb):
    eng, b = _losing_engine(exit_flag="SIGNAL")
    now = int(time.time())
    t1 = now // BAR_SECONDS * BAR_SECONDS - BAR_SECONDS
    eng.bars = [_bar(t1 - BAR_SECONDS, 100_000.0), _bar(t1, 85_000.0)]
    eng.last_processed = t1 - BAR_SECONDS
    with db.session_scope() as s:
        eng.catch_up(s)
    assert b.halted is True and len(eng.sent) == 1 and "HALTED" in eng.sent[0]


def test_halt_pages_once_across_bars(tmpdb):
    eng, b = _losing_engine(exit_flag="SIGNAL")
    now = int(time.time())
    t1 = now // BAR_SECONDS * BAR_SECONDS - 2 * BAR_SECONDS
    eng.bars = [_bar(t1 - BAR_SECONDS, 100_000.0), _bar(t1, 85_000.0),
                _bar(t1 + BAR_SECONDS, 85_000.0)]
    eng.last_processed = t1 - BAR_SECONDS
    with db.session_scope() as s:
        eng.catch_up(s)
    assert b.halted is True and len(eng.sent) == 1


# ------------------------------------------------ path independence (the point)

def test_halt_set_by_any_path_is_announced_on_the_next_scan(tmpdb):
    """reset_books installs replay-halted books; an exception between the
    halting close and the scan skips it once. Both were silent under the
    snapshot design. Announced-vs-halted does not care who set the flag."""
    eng, b = _losing_engine()
    b.position = None
    b.halted, b.halt_reason = True, "dd_halt"        # arrived already set
    with db.session_scope() as s:
        eng._announce_halts(s)
    assert len(eng.sent) == 1 and b.halt_announced is True
    with db.session_scope() as s:
        eng._announce_halts(s)
    assert len(eng.sent) == 1


def test_failed_page_is_retried_next_scan(tmpdb):
    eng, b = _losing_engine()
    b.position = None
    b.halted = True
    n = {"calls": 0}

    def flaky(_m):
        n["calls"] += 1
        if n["calls"] == 1:
            raise RuntimeError("telegram down")
        eng.sent.append(_m)

    eng.alert_fn = flaky
    with db.session_scope() as s:
        eng._announce_halts(s)                       # raises, swallowed
    assert b.halt_announced is False and eng.sent == []
    with db.session_scope() as s:
        eng._announce_halts(s)                       # retried
    assert b.halt_announced is True and len(eng.sent) == 1


# ------------------------------------------------------- restart / wiring

def test_boot_restore_of_a_halted_book_does_not_page(tmpdb):
    eng, b = _losing_engine()
    b.halted, b.halt_reason, b.halt_announced = True, "dd_halt", True
    raw = eng._serialize_book(b)
    eng2, b2 = _losing_engine()
    eng2._restore_book(b2, raw)
    assert (b2.halted, b2.halt_reason, b2.halt_announced) == (True, "dd_halt", True)
    with db.session_scope() as s:
        eng2._announce_halts(s)
    assert eng2.sent == []


def test_pre_flag_halted_row_is_treated_as_announced(tmpdb):
    """A halted row persisted before halt_announced existed must not page on
    the first boot after deploy."""
    import json
    eng, b = _losing_engine()
    raw = json.dumps({"equity": 80_000.0, "peak": 100_000.0, "halted": True,
                      "position": None, "pending": None})
    eng._restore_book(b, raw)
    assert b.halted is True and b.halt_announced is True


def test_restore_drops_pending_onto_a_halted_book(tmpdb):
    """`halted` blocks NEW pendings only; a restored one still filled next
    bar and a halted book opened a position the executor mirrored."""
    import json
    eng, b = _losing_engine()
    raw = json.dumps({"equity": 80_000.0, "peak": 100_000.0, "halted": True,
                      "position": None,
                      "pending": {"side": "L", "limit": 1.0, "signal_ts": 1,
                                  "atr_signal": 1.0}})
    eng._restore_book(b, raw)
    assert b.pending is None


def test_production_wiring_is_the_real_telegram_sender():
    assert Engine().alert_fn is alerts.send


def test_alerting_failure_cannot_stall_the_loop(tmpdb, monkeypatch):
    eng, b = _losing_engine()
    _arm_poll(eng, monkeypatch)

    def boom(_m):
        raise RuntimeError("telegram down")

    eng.alert_fn = boom
    eng.poll()                                        # must not raise
    assert b.halted is True and b.halt_announced is False


def test_blend_clause_only_for_blend_ingredients(tmpdb):
    eng, b = _losing_engine(name="S1")
    b.position = None
    b.halted = True
    with db.session_scope() as s:
        eng._announce_halts(s)
    assert "research-only" in eng.sent[0] and "blend runs" not in eng.sent[0]


# ------------------------------------------------- control surface (no lifespan)

def _client():
    """No `with`: the app's lifespan starts the real engine loop (network).
    The first cut of this test started it twice and leaked state."""
    from fastapi.testclient import TestClient
    import app.main as m
    return TestClient(m.app), m


def test_manual_halt_drops_pending_records_reason_and_resume_rearms(tmpdb):
    c, m = _client()
    b = m.ENGINE.books["S3"]
    old = (b.halted, b.halt_reason, b.halt_announced, b.pending, settings.exec_token)
    try:
        settings.exec_token = ""
        b.pending = Pending(side="L", limit=1.0, signal_ts=1, atr_signal=1.0)
        r = c.post("/books/S3/halt")
        assert r.status_code == 200 and r.json()["pending_dropped"] is True
        assert b.halted is True and b.halt_reason == "manual" and b.pending is None
        b.halt_announced = True
        c.post("/books/S3/resume")
        assert (b.halted, b.halt_reason, b.halt_announced) == (False, None, False)
    finally:
        b.halted, b.halt_reason, b.halt_announced, b.pending, settings.exec_token = old


def test_control_endpoints_require_the_exec_token(tmpdb):
    """The runbook's remedy for a halt was an UNAUTHENTICATED mutation on a
    public URL (completeness critic, 2026-09-08)."""
    c, m = _client()
    old = settings.exec_token
    settings.exec_token = "sekrit"
    try:
        for path in ("/books/S3/halt", "/books/S3/resume", "/resume-data"):
            assert c.post(path).status_code == 401, path
        assert c.post("/books/reset").status_code == 401
        b = m.ENGINE.books["S3"]
        was = (b.halted, b.halt_reason, b.halt_announced, b.peak_equity)
        try:
            r = c.post("/books/S3/resume", headers={"x-exec-token": "sekrit"})
            assert r.status_code == 200
        finally:
            b.halted, b.halt_reason, b.halt_announced, b.peak_equity = was
    finally:
        settings.exec_token = old


def test_manual_halt_is_not_reported_as_a_drawdown(tmpdb):
    eng, b = _losing_engine()
    b.position = None
    b.halt_reason, b.halted = "manual", True
    with db.session_scope() as s:
        eng._announce_halts(s)
    assert "operator" in eng.sent[0] and "dd_halt" not in eng.sent[0]


def test_exec_target_carries_halted_and_reason(tmpdb):
    """The field the entire executor-side fix depends on. It could be
    hardwired False with the engine suite green (panel, 2026-09-08)."""
    c, m = _client()
    b = m.ENGINE.books["S4"]
    old = (b.halted, b.halt_reason, m.ENGINE.booted, settings.exec_token)
    try:
        settings.exec_token = ""
        m.ENGINE.booted = True
        b.halted, b.halt_reason = True, "manual"
        leg = c.get("/exec/target").json()["legs"]["trend"]
        assert leg["halted"] is True and leg["halt_reason"] == "manual"
        assert leg["state"] == "HALTED"
        b.halted, b.halt_reason = False, None
        leg = c.get("/exec/target").json()["legs"]["trend"]
        assert leg["halted"] is False and leg["halt_reason"] is None
    finally:
        b.halted, b.halt_reason, m.ENGINE.booted, settings.exec_token = old


def test_exec_target_refuses_until_booted(tmpdb):
    """Fresh Book() defaults are not an engine state: served during boot they
    read as halted=False / no position / bar_ts=0 and the executor acted on
    them (a false 'resumed' page per restart; a flatten of a live leg)."""
    c, m = _client()
    old = (m.ENGINE.booted, settings.exec_token)
    try:
        settings.exec_token = ""
        m.ENGINE.booted = False
        assert c.get("/exec/target").status_code == 503
        m.ENGINE.booted = True
        assert c.get("/exec/target").status_code == 200
    finally:
        m.ENGINE.booted, settings.exec_token = old
