"""Universe management: the single source of truth for the coverage list.

Three editing paths converge here (UI -> API -> these functions; and the
watchlist.yaml file via sync_from_yaml):
  * add / update / deactivate / delete
  * file <-> DB sync (UPSERT — never wipes history)

Deactivating sets active=False and retains all historical child data. Adding a
ticker validates the symbol against the market-data provider and kicks off an
immediate backfill.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from ..config import watchlist_config
from ..models import Security

logger = logging.getLogger(__name__)


class SymbolValidationError(ValueError):
    """Raised when a symbol cannot be validated against the data provider."""


def list_securities(session: Session, include_inactive: bool = True) -> list[Security]:
    stmt = select(Security)
    if not include_inactive:
        stmt = stmt.where(Security.active == True)  # noqa: E712
    return list(session.exec(stmt.order_by(Security.symbol)).all())


def get_security(session: Session, symbol: str) -> Security | None:
    return session.get(Security, symbol.upper())


def upsert_security(
    session: Session,
    symbol: str,
    name: str | None = None,
    subsector: list[str] | None = None,
    active: bool | None = None,
    commit: bool = True,
) -> Security:
    """Insert or update a security WITHOUT touching its historical data."""
    symbol = symbol.upper()
    sec = session.get(Security, symbol)
    if sec is None:
        sec = Security(
            symbol=symbol,
            name=name or symbol,
            subsector=subsector or [],
            active=active if active is not None else True,
        )
        session.add(sec)
    else:
        if name is not None:
            sec.name = name
        if subsector is not None:
            sec.subsector = subsector
        if active is not None:
            sec.active = active
        sec.updated_at = datetime.utcnow()
        session.add(sec)
    if commit:
        session.commit()
        session.refresh(sec)
    return sec


def set_active(session: Session, symbol: str, active: bool) -> Security | None:
    sec = session.get(Security, symbol.upper())
    if sec is None:
        return None
    sec.active = active
    sec.updated_at = datetime.utcnow()
    session.add(sec)
    session.commit()
    session.refresh(sec)
    return sec


def delete_security(session: Session, symbol: str) -> bool:
    """Hard-delete the universe row. (Use deactivate to retain history instead.)"""
    sec = session.get(Security, symbol.upper())
    if sec is None:
        return False
    session.delete(sec)
    session.commit()
    return True


def sync_from_yaml(session: Session) -> dict:
    """Upsert every entry from watchlist.yaml. Never deletes — history-safe.

    Returns a summary {added, updated, total}.
    """
    cfg = watchlist_config()
    entries = cfg.get("universe", [])
    added = 0
    updated = 0
    for entry in entries:
        symbol = str(entry["symbol"]).upper()
        existed = session.get(Security, symbol) is not None
        upsert_security(
            session,
            symbol=symbol,
            name=entry.get("name"),
            subsector=list(entry.get("subsector", [])),
            active=entry.get("active", True),
            commit=False,
        )
        if existed:
            updated += 1
        else:
            added += 1
    session.commit()
    total = len(session.exec(select(Security)).all())
    logger.info("Universe sync: %d added, %d updated, %d total", added, updated, total)
    return {"added": added, "updated": updated, "total": total}


def all_subsectors(session: Session) -> list[str]:
    tags: set[str] = set()
    for sec in session.exec(select(Security)).all():
        tags.update(sec.subsector or [])
    return sorted(tags)
