"""Merge-blocking gate: re-emitting a known event must not undo the refresh.

Detectors re-emit the same (event_type, dedup_key) on every refresh while a
condition holds (a curve re-steepening, a squeeze pre-brief window, a labor
ledger onset). The old _persist_event answered the duplicate with
session.rollback(), which discarded every snapshot and event the refresh had
written before it — the live history stopped updating while /metrics (computed
live) looked healthy."""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes_labor import board_ledger_events
from app.jobs.refresh import _persist_event, _upsert_snapshot
from app.scoring.events import Event
from app.store.models import Base, EventLog, MetricSnapshot


def _session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'canary.db'}",
                        connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    # same configuration as app.store.db.SessionLocal
    return sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)


def _snap(s, day):
    _upsert_snapshot(s, metric_id="curve.3m10y", category="A", asof=day, value=0.1,
                     status="GREEN", percentile=None, note=None)


def _ev(key, day):
    return Event(event_type="curve_resteepening", severity="CRITICAL", asof=day,
                 dedup_key=key, rationale="x", detail={})


def test_a_repeated_event_keeps_the_rest_of_the_refresh(tmp_path):
    SL = _session_factory(tmp_path)
    ledger = {"month": "2026-10", "ledger": [
        {"month": "2026-10", "kind": "B1", "event": "B1 onset", "value": 0.51}]}
    d1, d2 = date(2026, 10, 3), date(2026, 10, 4)
    with SL() as s:                                       # refresh 1
        _snap(s, d1)
        assert _persist_event(s, _ev("3m10y:2026-09-01", d1))
        assert all(_persist_event(s, e) for e in board_ledger_events(ledger, d1))
        s.commit()
    with SL() as s:                                       # refresh 2 re-emits both
        _snap(s, d2)
        new_before = _persist_event(s, _ev("3m10y:2026-10-04", d2))
        dup_curve = _persist_event(s, _ev("3m10y:2026-09-01", d2))
        dup_ledger = [_persist_event(s, e) for e in board_ledger_events(ledger, d2)]
        new_after = _persist_event(s, _ev("3m10y:2026-10-05", d2))
        s.commit()
    assert new_before and new_after and not dup_curve and dup_ledger == [False]
    with SL() as s:
        snaps = sorted(r.asof for r in s.execute(select(MetricSnapshot)).scalars())
        keys = {r.dedup_key: r for r in s.execute(select(EventLog)).scalars()}
    assert snaps == [d1, d2]                              # refresh 2's snapshot survived
    assert {"3m10y:2026-09-01", "3m10y:2026-10-04", "3m10y:2026-10-05",
            "B1:2026-10"} == set(keys)
    # the ledger keeps its FIRST sighting
    assert json.loads(keys["B1:2026-10"].detail_json)["first_seen"] == "2026-10-03"


def test_duplicate_as_the_first_write_of_a_refresh(tmp_path):
    SL = _session_factory(tmp_path)
    d1, d2 = date(2026, 10, 3), date(2026, 10, 4)
    with SL() as s:
        assert _persist_event(s, _ev("k", d1))
        s.commit()
    with SL() as s:                                       # duplicate before any DML
        assert not _persist_event(s, _ev("k", d2))
        _snap(s, d2)
        assert _persist_event(s, _ev("k2", d2))
        s.commit()
    with SL() as s:
        assert [r.asof for r in s.execute(select(MetricSnapshot)).scalars()] == [d2]
        assert {r.dedup_key for r in s.execute(select(EventLog)).scalars()} == {"k", "k2"}


def test_a_crash_before_commit_pages_again_next_refresh(tmp_path):
    # at-least-once: a new event written as the FIRST statement of a refresh
    # must stay inside the refresh transaction (a pysqlite SAVEPOINT issued
    # before any other write commits on RELEASE, so a crash between logging
    # and paging would drop the page for good)
    SL = _session_factory(tmp_path)
    d1 = date(2026, 10, 3)
    with SL() as s:
        assert _persist_event(s, _ev("band:LOW->HIGH", d1))
        s.rollback()                                     # process died before commit
    with SL() as s:
        assert s.execute(select(EventLog)).first() is None
        assert _persist_event(s, _ev("band:LOW->HIGH", d1))   # so it pages again
        s.commit()
    with SL() as s:
        row = s.execute(select(EventLog)).scalars().one()
        assert row.dedup_key == "band:LOW->HIGH" and row.alert_sent is False
        assert row.created_at is not None                # column defaults still applied
