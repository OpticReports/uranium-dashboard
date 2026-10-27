"""Bar finality gates: a bar is evaluated only from a fetch taken after it
closed (plus bar_final_grace_s), never from the snapshot kept in memory
while it was forming.

The 2026-10-07 missed paper fill (btc-executor/docs/HALT_2026-10-07.md):
the 04:00Z bar entered the in-memory window at the 04:00 boundary refresh
holding only its first seconds (open 84,121.29, one cent ABOVE the pending
limit 84,121.28). No refresh ran until 08:00. The ONE fetch at 08:00:0x
failed (or returned the candle before Bitstamp finalized it), refresh_bars
changed nothing, and catch_up processed the stale snapshot as the closed
bar: low >= limit, pending cancelled, S3 flat - while the venue had filled
the executor's maker order at that limit at 04:00:24. The next refresh
overwrote and persisted the final bar (low 84,010.77) but catch_up skipped
it as already processed. The executor then closed the "orphan" fill and the
settlement fault on its side turned that into a LEDGER_DIVERGENCE halt.

These gates drive Engine.refresh_bars / catch_up / poll against a scripted
fetch and a controlled clock, against a temp SQLite, and pin the outcome:
the stale snapshot is never evaluated; a failed boundary fetch defers and
retries every poll; the final bar fills the pending at the limit.
"""
import csv
import os
import time as _time

import pytest

import app.live as live
import app.store.db as db
from app.config import settings
from app.engine.core import BAR_SECONDS, Bar, Book, BookCfg, Pending
from app.live import Engine

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")
LIMIT = 84_121.28                      # the 2026-10-07 00:00Z close
T1_FORMING = dict(open=84_121.29, high=84_121.29, low=84_121.29,
                  close=84_121.29, volume=0.3)        # first seconds
T1_FINAL = dict(open=84_121.29, high=84_348.23, low=84_010.77,
                close=84_119.73, volume=102.74)       # Bitstamp, as stored


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    old_url, old_engine = settings.database_url, db._engine
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/t.db")
    db._engine = None
    db.init_db()
    yield
    db._engine = old_engine
    settings.database_url = old_url


class Clock:
    def __init__(self, now):
        self.now = float(now)

    def __call__(self):
        return self.now


def _history(t0, n=60):
    """n fixture bars re-timestamped to END at t0 (the bar whose close set
    the pending), prices as in the fixture - only ATR needs to exist."""
    rows = list(csv.DictReader(open(FIX)))[:n]
    out = []
    for i, r in enumerate(rows):
        ts = t0 - (n - 1 - i) * BAR_SECONDS
        out.append(Bar(ts=ts, open=float(r["open"]), high=float(r["high"]),
                       low=float(r["low"]), close=float(r["close"]),
                       volume=float(r["volume"])))
    return out


def _engine(monkeypatch, t0):
    eng = Engine()
    eng.sent = []
    eng.alert_fn = lambda m: eng.sent.append(m)
    cfg = BookCfg(name="S3", sizing="fixed", leverage=1.0,
                  start_equity=100_000.0, dd_halt=0.30)
    b = Book(cfg=cfg)
    b.pending = Pending(side="L", limit=LIMIT, signal_ts=t0, atr_signal=500.0)
    eng.books = {"S3": b}
    eng._persisted_trades = {"S3": 0}
    eng.bars = _history(t0)
    eng._bar_fetched_at = {x.ts: float("inf") for x in eng.bars}
    eng.last_processed = t0
    eng.last_data_ok = _time.time()
    monkeypatch.setattr(live, "last_price", lambda: 84_100.0)
    monkeypatch.setattr(live, "kraken_price", lambda: 84_100.0)
    return eng, b


def _script(monkeypatch, eng):
    """fetch_4h_bars replacement driven by a list of answers; each call pops
    the next; an empty answer models a failed fetch."""
    answers = []

    def fake(start_unix):
        return list(answers.pop(0)) if answers else []

    monkeypatch.setattr(live, "fetch_4h_bars", fake)
    return answers


def test_gate_2026_10_07_stale_forming_snapshot_is_never_evaluated(
        tmpdb, monkeypatch):
    t0 = 1_791_331_200                       # 2026-10-07 00:00Z
    t1, t2 = t0 + BAR_SECONDS, t0 + 2 * BAR_SECONDS
    clock = Clock(t1 + 5)
    monkeypatch.setattr(live.time, "time", clock)
    eng, b = _engine(monkeypatch, t0)
    answers = _script(monkeypatch, eng)
    bar_t0 = eng.bars[-1]
    # 04:00:05 boundary refresh: the 00:00 bar final, the 04:00 bar forming
    answers.append([bar_t0, Bar(ts=t1, **T1_FORMING)])
    eng.poll()
    assert b.pending is not None and b.position is None
    assert eng.bars[-1].ts == t1 and eng.bars[-1].low == T1_FORMING["low"]
    # 08:00:05: the ONE boundary fetch FAILS. Pre-fix: the forming snapshot
    # is processed as the closed bar -> pending cancelled, no fill, S3 flat.
    clock.now = t2 + 5
    answers.append([])
    eng.poll()
    assert b.pending is not None, "stale forming snapshot was evaluated"
    assert b.position is None
    assert eng.last_processed == t0
    with db.session_scope() as s:
        kinds = [e.event for e in s.query(db.EventRow).all()]
    assert "bar_not_final" in kinds
    # 08:01:05: the next poll retries (bars[-1] is still the 04:00 bar, but
    # the rule is "a closed bar is unprocessed", not "the boundary passed")
    clock.now = t2 + 65
    answers.append([bar_t0, Bar(ts=t1, **T1_FINAL),
                    Bar(ts=t2, open=84_104.7, high=84_104.7, low=84_104.7,
                        close=84_104.7, volume=0.1)])
    eng.poll()
    assert b.pending is None and b.position is not None
    assert b.position.entry_price == LIMIT and b.position.entry_ts == t1
    assert eng.last_processed == t1
    assert eng.bars[-1].ts == t2                 # forming 08:00 bar kept
    assert not eng.bar_final(eng.bars[-1], clock.now)


def test_gate_boundary_fetch_inside_the_grace_is_deferred_then_processed(
        tmpdb, monkeypatch):
    """A fetch that lands 5 s after the close returns a candle Bitstamp may
    not have finalized: wait bar_final_grace_s, then re-fetch and process.
    The pending must not resolve off the early read."""
    t0 = 1_791_331_200
    t1, t2 = t0 + BAR_SECONDS, t0 + 2 * BAR_SECONDS
    clock = Clock(t1 + 5)
    monkeypatch.setattr(live.time, "time", clock)
    monkeypatch.setattr(settings, "bar_final_grace_s", 30)
    eng, b = _engine(monkeypatch, t0)
    answers = _script(monkeypatch, eng)
    bar_t0 = eng.bars[-1]
    answers.append([bar_t0, Bar(ts=t1, **T1_FORMING)])
    eng.poll()
    # 08:00:05: fetch succeeds but is inside the grace; the forming 08:00
    # bar is appended, so the OLD boundary rule would never refresh again
    # before 12:00
    clock.now = t2 + 5
    early = dict(T1_FINAL, low=84_121.29)        # candle not yet finalized
    answers.append([bar_t0, Bar(ts=t1, **early),
                    Bar(ts=t2, open=84_104.7, high=84_104.7, low=84_104.7,
                        close=84_104.7, volume=0.1)])
    eng.poll()
    assert b.pending is not None and b.position is None
    assert eng.closed_unprocessed(clock.now) and eng.bars[-1].ts == t2
    assert not eng.bar_final(eng.bars[-2], clock.now)
    with db.session_scope() as s:        # the early read never reaches the DB
        assert s.get(db.BarRow, t1) is None
    # 08:01:05: past the grace, re-fetched final -> processed
    clock.now = t2 + 65
    answers.append([bar_t0, Bar(ts=t1, **T1_FINAL),
                    Bar(ts=t2, open=84_104.7, high=84_104.7, low=84_104.7,
                        close=84_104.7, volume=0.1)])
    eng.poll()
    assert b.position is not None and b.position.entry_price == LIMIT
    assert not eng.closed_unprocessed(clock.now)
    with db.session_scope() as s:        # the final bar does, as fetched
        assert s.get(db.BarRow, t1).low == T1_FINAL["low"]


def test_gate_bars_without_a_post_close_fetch_are_not_final(tmpdb, monkeypatch):
    """Strict: a bar with no fetch on record is not final, and catch_up
    stops at it IN ORDER (later bars are not processed around it)."""
    t0 = 1_791_331_200
    t1, t2 = t0 + BAR_SECONDS, t0 + 2 * BAR_SECONDS
    clock = Clock(t2 + BAR_SECONDS + 100)
    monkeypatch.setattr(live.time, "time", clock)
    eng, b = _engine(monkeypatch, t0)
    eng.bars = eng.bars + [Bar(ts=t1, **T1_FINAL),
                           Bar(ts=t2, open=84_104.7, high=84_146.34,
                               low=83_404.49, close=83_706.22, volume=229.4)]
    # t1 has NO record; t2 was fetched after its close
    eng._bar_fetched_at[t2] = t2 + BAR_SECONDS + 100
    assert not eng.bar_final(eng.bars[-2], clock.now)
    assert eng.bar_final(eng.bars[-1], clock.now)
    with db.session_scope() as s:
        eng.catch_up(s)
    assert eng.last_processed == t0 and b.pending is not None
    with db.session_scope() as s:
        n = len([e for e in s.query(db.EventRow).all()
                 if e.event == "bar_not_final"])
        eng.catch_up(s)                       # logged once per bar
        n2 = len([e for e in s.query(db.EventRow).all()
                  if e.event == "bar_not_final"])
    assert n == 1 and n2 == 1
