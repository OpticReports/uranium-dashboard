"""Common ingestion interface.

Every data source implements the same three-step contract so sources can be
added or disabled independently:

    fetch()      -> raw payload from the upstream API (network)
    normalize()  -> list of validated pydantic/dataclass records
    upsert()     -> idempotent write into the DB (no history wipes)

`run()` ties them together and is what the scheduler / backfill call. A source
that is missing its required key must override `available()` to return False and
will be skipped with a logged warning — it must NEVER crash the pipeline.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from sqlmodel import Session

logger = logging.getLogger(__name__)


class IngestionSource(ABC):
    name: str = "source"
    #: human-readable reason shown when unavailable (e.g. "X_BEARER_TOKEN unset")
    requires: str | None = None

    def available(self) -> bool:
        """Whether this source can run (keys present, enabled). Default: yes."""
        return True

    @abstractmethod
    def fetch(self, symbol: str) -> Any:
        ...

    @abstractmethod
    def normalize(self, symbol: str, raw: Any) -> list[Any]:
        ...

    @abstractmethod
    def upsert(self, session: Session, records: list[Any]) -> int:
        ...

    def run(self, session: Session, symbol: str) -> int:
        """fetch -> normalize -> upsert for one symbol. Returns rows written.

        Any exception is caught and logged so one bad symbol/source never breaks
        the whole ingestion run (graceful degradation).
        """
        if not self.available():
            logger.warning(
                "Source '%s' unavailable (%s) -- skipping %s",
                self.name,
                self.requires or "disabled",
                symbol,
            )
            return 0
        try:
            raw = self.fetch(symbol)
            records = self.normalize(symbol, raw)
            n = self.upsert(session, records)
            logger.debug("[%s] %s: wrote %d rows", self.name, symbol, n)
            return n
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] %s failed: %s", self.name, symbol, exc)
            return 0
