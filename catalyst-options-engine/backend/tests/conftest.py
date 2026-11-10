"""Offline test setup: temp SQLite + cache dirs BEFORE the app imports settings.

No test may touch the network — HTTP lanes are exercised via monkeypatched
httpx.get returning captured fixtures (tests/fixtures/*.json are real response
shapes captured live on 2026-08-19).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="coe-tests-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("CACHE_DIR", f"{_TMP}/cache")
os.environ.setdefault("RUN_SCHEDULER", "false")

import pytest  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def session():
    """Fresh in-memory DB session per test."""
    from sqlmodel import Session, SQLModel, create_engine
    from app import models  # noqa: F401

    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
