"""Gate tests for reads during a scheduler write.

The scheduler writes on a background thread while the web worker serves the
dashboard out of the same SQLite file. Under default SQLite that combination
returned "database is locked" to the browser — a 500 — for the whole window a
scan was writing, which on a full rollup was minutes.
"""
from __future__ import annotations

import threading
import time

from sqlalchemy import text
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Candidate


def test_wal_and_busy_timeout_are_actually_set():
    init_db()
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() >= 5000


def test_reads_succeed_while_another_session_is_writing():
    """The exact production symptom: a dashboard read during a scan write."""
    init_db()
    with Session(engine) as s:
        s.add(Candidate(ticker="LOCK1", company="Seed"))
        s.commit()

    errors: list[Exception] = []
    stop = threading.Event()

    def writer():
        try:
            for i in range(25):
                with Session(engine) as s:
                    row = s.exec(select(Candidate).where(
                        Candidate.ticker == "LOCK1")).first()
                    row.heat = float(i)
                    s.add(row)
                    s.commit()
                time.sleep(0.002)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    reads = 0
    while not stop.is_set() and reads < 200:
        with Session(engine) as s:
            s.exec(select(Candidate).where(Candidate.ticker == "LOCK1")).all()
        reads += 1
    t.join(timeout=15)

    assert not errors, f"writer failed: {errors[:1]}"
    assert reads > 0, "no concurrent reads were attempted"
