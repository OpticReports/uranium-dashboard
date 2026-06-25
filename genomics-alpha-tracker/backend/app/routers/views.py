"""Dashboard aggregation views: heatmap, movers, per-name deep dive."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models import (
    AnalystRevision,
    Catalyst,
    Fundamental,
    PriceBar,
    ScoreSnapshot,
    SciencePub,
    Security,
    SocialMention,
    FlagEvent,
)
from ..schemas import HeatmapTile, MoverOut

router = APIRouter(prefix="/views", tags=["views"])


def _latest_scores(session: Session) -> dict[str, ScoreSnapshot]:
    latest: dict[str, ScoreSnapshot] = {}
    for snap in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
        latest[snap.symbol] = snap
    return latest


@router.get("/heatmap", response_model=list[HeatmapTile])
def heatmap(session: Session = Depends(get_session)):
    """Average composite Alpha Signal rolled up by subsector theme."""
    secs = [s for s in session.exec(select(Security)).all() if s.active]
    scores = _latest_scores(session)
    by_tag: dict[str, list[tuple[str, float | None]]] = {}
    for sec in secs:
        comp = scores.get(sec.symbol)
        composite = comp.composite if comp else None
        for tag in sec.subsector or ["untagged"]:
            by_tag.setdefault(tag, []).append((sec.symbol, composite))
    tiles = []
    for tag, members in sorted(by_tag.items()):
        vals = [c for _, c in members if c is not None]
        tiles.append(HeatmapTile(
            subsector=tag,
            avg_composite=(sum(vals) / len(vals)) if vals else None,
            count=len(members),
            symbols=[s for s, _ in members],
        ))
    return tiles


@router.get("/movers", response_model=list[MoverOut])
def movers(limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    """Names with the largest social mention acceleration this week."""
    scores = _latest_scores(session)
    secs = {s.symbol: s for s in session.exec(select(Security)).all()}
    out: list[MoverOut] = []
    for symbol, snap in scores.items():
        sec = secs.get(symbol)
        if not sec or not sec.active:
            continue
        accel = (snap.formula.get("components", {})
                 .get("hype_divergence", {})
                 .get("mention_acceleration"))
        out.append(MoverOut(
            symbol=symbol, name=sec.name,
            mention_acceleration=accel, composite=snap.composite,
        ))
    out.sort(key=lambda m: (m.mention_acceleration is None, -(m.mention_acceleration or 0)))
    return out[:limit]


@router.get("/deep-dive/{symbol}")
def deep_dive(
    symbol: str,
    days: int = Query(365, ge=30, le=3650),
    session: Session = Depends(get_session),
):
    """Everything for the per-name deep-dive view in one payload."""
    symbol = symbol.upper()
    sec = session.get(Security, symbol)
    if sec is None:
        raise HTTPException(404, f"{symbol} not found")

    since = date.today() - timedelta(days=days)
    prices = session.exec(
        select(PriceBar).where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= since).order_by(PriceBar.date.asc())
    ).all()
    catalysts = session.exec(
        select(Catalyst).where(Catalyst.symbol == symbol).order_by(Catalyst.date.asc())
    ).all()
    revisions = session.exec(
        select(AnalystRevision).where(AnalystRevision.symbol == symbol)
        .where(AnalystRevision.date >= since).order_by(AnalystRevision.date.asc())
    ).all()
    mentions = session.exec(
        select(SocialMention).where(SocialMention.symbol == symbol)
        .where(SocialMention.date >= since).order_by(SocialMention.date.asc())
    ).all()
    pubs = session.exec(
        select(SciencePub).where(SciencePub.symbol == symbol)
        .order_by(SciencePub.date.desc()).limit(50)
    ).all()
    fund = session.exec(
        select(Fundamental).where(Fundamental.symbol == symbol)
        .order_by(Fundamental.asof.desc()).limit(1)
    ).first()
    snap = session.exec(
        select(ScoreSnapshot).where(ScoreSnapshot.symbol == symbol)
        .order_by(ScoreSnapshot.asof.desc()).limit(1)
    ).first()
    flags = session.exec(
        select(FlagEvent).where(FlagEvent.symbol == symbol)
        .where(FlagEvent.asof >= datetime.utcnow() - timedelta(days=14))
        .order_by(FlagEvent.asof.desc())
    ).all()

    return {
        "security": {
            "symbol": sec.symbol, "name": sec.name,
            "subsector": sec.subsector, "active": sec.active,
        },
        "prices": [
            {"date": p.date.isoformat(), "close": p.close, "volume": p.volume}
            for p in prices
        ],
        "catalysts": [
            {"id": c.id, "date": c.date.isoformat(), "event_type": c.event_type,
             "title": c.title, "impact": c.effective_impact, "url": c.url}
            for c in catalysts
        ],
        "revisions": [
            {"date": r.date.isoformat(), "firm": r.firm, "metric": r.metric,
             "direction": r.direction, "old_value": r.old_value, "new_value": r.new_value}
            for r in revisions
        ],
        "mentions": [
            {"date": m.date.isoformat(), "platform": m.platform,
             "volume": m.volume, "sentiment": m.sentiment}
            for m in mentions
        ],
        "publications": [
            {"date": p.date.isoformat(), "kind": p.kind, "title": p.title, "url": p.url}
            for p in pubs
        ],
        "fundamentals": None if fund is None else {
            "asof": fund.asof.isoformat(), "market_cap": fund.market_cap,
            "cash": fund.cash, "quarterly_burn": fund.quarterly_burn,
            "runway_quarters": fund.runway_quarters, "rd_spend": fund.rd_spend,
            "short_interest_pct": fund.short_interest_pct, "iv": fund.iv,
            "iv_skew": fund.iv_skew,
        },
        "score": None if snap is None else {
            "composite": snap.composite, "components": snap.components,
            "missing": snap.missing, "formula": snap.formula, "asof": snap.asof.isoformat(),
        },
        "flags": [
            {"flag_type": f.flag_type, "severity": f.severity,
             "message": f.message, "evidence": f.evidence}
            for f in flags
        ],
    }
