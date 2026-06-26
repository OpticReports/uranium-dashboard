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
from ..schemas import MoverOut

router = APIRouter(prefix="/views", tags=["views"])


MOMENTUM_DAYS = 7
HIGH_IMPACT = 0.6
N_COMPONENTS = 5

DRIVER_LABELS = {
    "revision_velocity": "analyst revisions rising",
    "catalyst_score": "near-term catalyst",
    "hype_divergence": "chatter leading price",
    "positioning": "squeeze/positioning",
    "runway_penalty": "balance-sheet strength",
}


def _latest_scores(session: Session) -> dict[str, ScoreSnapshot]:
    latest: dict[str, ScoreSnapshot] = {}
    for snap in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
        latest[snap.symbol] = snap
    return latest


def _history(session: Session) -> dict[str, list[ScoreSnapshot]]:
    hist: dict[str, list[ScoreSnapshot]] = {}
    for snap in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
        hist.setdefault(snap.symbol, []).append(snap)
    return hist


def _momentum(snaps: list[ScoreSnapshot], days: int = MOMENTUM_DAYS) -> float | None:
    """Change in composite vs the closest snapshot >= `days` ago. None if unknowable."""
    if not snaps or snaps[-1].composite is None:
        return None
    latest = snaps[-1]
    cutoff = latest.asof - timedelta(days=days)
    prior = next((s for s in reversed(snaps[:-1]) if s.asof <= cutoff), None)
    if prior is None:
        prior = snaps[0] if len(snaps) > 1 else None
    if prior is None or prior.composite is None or prior is latest:
        return None
    return latest.composite - prior.composite


def _driver(snap: ScoreSnapshot | None) -> str | None:
    """Plain-language label for the component contributing the most to the score."""
    if snap is None:
        return None
    comps = (snap.formula or {}).get("components", {})
    best_key, best_w = None, None
    for key, val in comps.items():
        w = val.get("weighted")
        if w is None:
            continue
        if best_w is None or w > best_w:
            best_key, best_w = key, w
    if best_key is None:
        return None
    return DRIVER_LABELS.get(best_key, best_key.replace("_", " "))


def _completeness(snap: ScoreSnapshot | None) -> float | None:
    if snap is None:
        return None
    return max(0.0, 1.0 - len(snap.missing or []) / N_COMPONENTS)


def _sparkline(member_syms: list[str], hist: dict, max_points: int = 10) -> list[float]:
    """Subsector avg composite bucketed by date — a small trend series."""
    by_date: dict[str, list[float]] = {}
    for sym in member_syms:
        for s in hist.get(sym, []):
            if s.composite is None:
                continue
            by_date.setdefault(s.asof.date().isoformat(), []).append(s.composite)
    dates = sorted(by_date)[-max_points:]
    return [round(sum(by_date[d]) / len(by_date[d]), 1) for d in dates]


@router.get("/heatmap")
def heatmap(session: Session = Depends(get_session)):
    """Subsector roll-up enriched for decision-making.

    Per tile: level (avg composite) AND momentum (WoW change), breadth, a
    trend sparkline, near-term catalyst density, active-flag counts, and a
    data-completeness confidence factor — plus a ranked member list with each
    name's dominant driver, flags, and next catalyst (for instant drill-down).
    """
    today = date.today()
    secs = [s for s in session.exec(select(Security)).all() if s.active]
    hist = _history(session)
    latest = {sym: snaps[-1] for sym, snaps in hist.items() if snaps}

    # Active flags (deduped to the most recent per (symbol, type), last 14d).
    since = datetime.utcnow() - timedelta(days=14)
    flags_by_sym: dict[str, dict[str, FlagEvent]] = {}
    for f in session.exec(select(FlagEvent).where(FlagEvent.asof >= since)).all():
        flags_by_sym.setdefault(f.symbol, {})[f.flag_type] = f

    # Upcoming catalysts per symbol.
    cats_by_sym: dict[str, list[Catalyst]] = {}
    for c in session.exec(
        select(Catalyst).where(Catalyst.date >= today).order_by(Catalyst.date.asc())
    ).all():
        cats_by_sym.setdefault(c.symbol, []).append(c)

    by_tag: dict[str, list[Security]] = {}
    for sec in secs:
        for tag in sec.subsector or ["untagged"]:
            by_tag.setdefault(tag, []).append(sec)

    tiles = []
    for tag, members in sorted(by_tag.items()):
        m_rows = []
        for sec in members:
            snap = latest.get(sec.symbol)
            composite = snap.composite if snap else None
            mom = _momentum(hist.get(sec.symbol, []))
            flags = list(flags_by_sym.get(sec.symbol, {}).values())
            ucats = cats_by_sym.get(sec.symbol, [])
            nxt = ucats[0] if ucats else None
            m_rows.append({
                "symbol": sec.symbol,
                "name": sec.name,
                "composite": composite,
                "momentum": mom,
                "driver": _driver(snap),
                "completeness": _completeness(snap),
                "flags": [{"type": f.flag_type, "severity": f.severity, "message": f.message}
                          for f in flags],
                "next_catalyst": None if nxt is None else {
                    "event_type": nxt.event_type, "date": nxt.date.isoformat(),
                    "days_until": (nxt.date - today).days, "impact": nxt.effective_impact,
                },
            })

        comps = [r["composite"] for r in m_rows if r["composite"] is not None]
        moms = [r["momentum"] for r in m_rows if r["momentum"] is not None]
        comps_sorted = sorted(comps)
        median = comps_sorted[len(comps_sorted) // 2] if comps_sorted else None
        rising = sum(1 for m in moms if m > 0)
        completes = [r["completeness"] for r in m_rows if r["completeness"] is not None]
        member_syms = [r["symbol"] for r in m_rows]
        cat30 = sum(
            1 for sym in member_syms for c in cats_by_sym.get(sym, [])
            if 0 <= (c.date - today).days <= 30 and c.effective_impact >= HIGH_IMPACT
        )
        cat90 = sum(
            1 for sym in member_syms for c in cats_by_sym.get(sym, [])
            if 0 <= (c.date - today).days <= 90 and c.effective_impact >= HIGH_IMPACT
        )
        flag_total = sum(len(r["flags"]) for r in m_rows)
        flag_high = sum(1 for r in m_rows for f in r["flags"] if f["severity"] == "high")
        best = max((r for r in m_rows if r["composite"] is not None),
                   key=lambda r: r["composite"], default=None)
        worst = min((r for r in m_rows if r["composite"] is not None),
                    key=lambda r: r["composite"], default=None)

        tiles.append({
            "subsector": tag,
            "count": len(members),
            "avg_composite": (sum(comps) / len(comps)) if comps else None,
            "median_composite": median,
            "momentum": (sum(moms) / len(moms)) if moms else None,
            "breadth": (rising / len(moms)) if moms else None,
            "data_completeness": (sum(completes) / len(completes)) if completes else None,
            "sparkline": _sparkline(member_syms, hist),
            "catalysts_30d": cat30,
            "catalysts_90d": cat90,
            "flag_count": flag_total,
            "flag_high": flag_high,
            "best": None if best is None else {"symbol": best["symbol"], "composite": best["composite"]},
            "worst": None if worst is None else {"symbol": worst["symbol"], "composite": worst["composite"]},
            "members": sorted(m_rows, key=lambda r: (r["composite"] is None, -(r["composite"] or 0))),
        })
    # Strongest themes first (by momentum, then level).
    tiles.sort(key=lambda t: (-(t["momentum"] or -999), -(t["avg_composite"] or 0)))
    return {"asof": datetime.utcnow().isoformat(), "tiles": tiles}


@router.get("/treemap")
def treemap(session: Session = Depends(get_session)):
    """Flat per-name data for a Finviz-style treemap.

    Each name: primary subsector (for grouping), market cap (tile size), and the
    metrics you can color by — Alpha Signal composite, Δ7d momentum, and recent
    price change.
    """
    today = date.today()
    secs = [s for s in session.exec(select(Security)).all() if s.active]
    hist = _history(session)
    latest = {sym: snaps[-1] for sym, snaps in hist.items() if snaps}

    # Latest market cap per symbol.
    mcap: dict[str, float | None] = {}
    for f in session.exec(select(Fundamental).order_by(Fundamental.asof.asc())).all():
        mcap[f.symbol] = f.market_cap

    # Recent 1-bar price change per symbol.
    pchg: dict[str, float | None] = {}
    for sec in secs:
        bars = session.exec(
            select(PriceBar).where(PriceBar.symbol == sec.symbol)
            .order_by(PriceBar.date.desc()).limit(2)
        ).all()
        if len(bars) == 2 and bars[1].close:
            pchg[sec.symbol] = (bars[0].close - bars[1].close) / bars[1].close

    nodes = []
    for sec in secs:
        snap = latest.get(sec.symbol)
        nodes.append({
            "symbol": sec.symbol,
            "name": sec.name,
            "subsector": (sec.subsector or ["untagged"])[0],  # primary theme
            "market_cap": mcap.get(sec.symbol),
            "composite": snap.composite if snap else None,
            "momentum": _momentum(hist.get(sec.symbol, [])),
            "price_change": pchg.get(sec.symbol),
        })
    return {"asof": datetime.utcnow().isoformat(), "nodes": nodes}


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
