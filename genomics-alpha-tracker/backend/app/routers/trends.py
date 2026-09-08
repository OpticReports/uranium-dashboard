"""GET /trends — Google Trends attention-top detector (OBSERVE-ONLY; feeds
no score, generates no call). One entry per keyword in config/trends.yaml:
the weekly interest series paired with its traded proxy's weekly close, the
detector's per-week state and the latest flags. /trends/study serves the
frozen event-study numbers the panel's honesty box shows."""
from __future__ import annotations

import bisect
import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..config import BACKEND_DIR
from ..db import get_session
from ..ingestion import trends as lane
from ..models import PriceBar, TrendPoint
from ..trends.detector import PARAMS, compute, summary

router = APIRouter(prefix="/trends", tags=["trends"])

NOTE = ("OBSERVE-ONLY attention gauge - Google Trends weekly interest vs the "
        "traded proxy. CLIMAX = record + parabolic attention with price near "
        "highs; FADING = attention -35% from the climax while price holds; "
        "DIVERGENCE = new price high on much less attention. Feeds no score, "
        "generates no call (HYPOTHESES.md H14). In the 11-series study the "
        "FIRST climax of a run was usually early; tops were stage-2+ climaxes.")


def _weekly_closes(session: Session, symbol: str, week_starts: list) -> list:
    """Close of the last trading day inside each Google week (start+6d)."""
    bars = session.exec(select(PriceBar.date, PriceBar.close)
                        .where(PriceBar.symbol == symbol.upper())
                        .where(PriceBar.close.is_not(None))
                        .order_by(PriceBar.date)).all()
    if not bars:
        return [None] * len(week_starts)
    dates = [b[0] for b in bars]
    closes = [b[1] for b in bars]
    out = []
    for ws in week_starts:
        j = bisect.bisect_right(dates, ws + timedelta(days=6)) - 1
        out.append(closes[j] if j >= 0 and dates[j] >= ws else None)
    return out


def _series(session: Session, kw: dict) -> dict:
    rows = list(session.exec(select(TrendPoint).where(TrendPoint.keyword == kw["keyword"])
                             .order_by(TrendPoint.date)).all())
    # DataForSEO's last point is the in-progress week (missing_data=true):
    # a partial week would flip the state mid-week, so it is not scored.
    while rows and rows[-1].missing:
        rows.pop()
    dates = [r.date for r in rows]
    interest = [r.value for r in rows]
    close = _weekly_closes(session, kw["price_symbol"], dates) if kw.get("price_symbol") else None
    pts = compute([d.isoformat() for d in dates], interest, close)
    return {"keyword": kw["keyword"], "label": kw.get("label", kw["keyword"]),
            "price_symbol": kw.get("price_symbol"), "theme": kw.get("theme"),
            "positions": kw.get("positions"),
            "fetched_at": rows[-1].fetched_at.isoformat() if rows and rows[-1].fetched_at else None,
            "window": rows[-1].window if rows else None,
            "summary": summary(pts),
            "points": [p.as_dict() for p in pts]}


@router.get("")
def list_trends(weeks: int = Query(156, le=520), session: Session = Depends(get_session)):
    items = []
    for kw in lane.keywords():
        s = _series(session, kw)
        s["points"] = s["points"][-weeks:]
        items.append(s)
    order = {"CLIMAX": 0, "FADING": 1, "DIVERGENCE": 2, "COOLED": 3, "ELEVATED": 4, "QUIET": 5, "NO_DATA": 6}
    items.sort(key=lambda s: order.get(s["summary"].get("state"), 9))
    return {"items": items, "status": lane.status(), "params": PARAMS, "note": NOTE}


@router.get("/status")
def trends_status():
    return lane.status()


@router.get("/study")
def study():
    """Frozen study numbers (docs/trends_peak/study_results.json; mirrored into
    config/trends_study_frozen.json for the container, which has no docs/)."""
    for path in (BACKEND_DIR.parent / "docs" / "trends_peak" / "study_results.json",
                 BACKEND_DIR / "config" / "trends_study_frozen.json"):
        if path.exists():
            data = json.loads(Path(path).read_text())
            return {"pooled": data.get("pooled"), "params": data.get("params"),
                    "n_base_weeks": data.get("n_base_weeks"),
                    "events": {k: {"price_peak": v["price_peak"], "trend_peak": v["trend_peak"],
                                   "climax": [(r["date"], r["stage"], r["wk_vs_price_peak"], r["r26"], r["dd26"])
                                              for r in v["flags"]["climax"]]}
                               for k, v in (data.get("events") or {}).items()}}
    raise HTTPException(404, "study results not found")


@router.get("/{keyword}")
def one(keyword: str, session: Session = Depends(get_session)):
    for kw in lane.keywords():
        if kw["keyword"].lower() == keyword.lower():
            return dict(_series(session, kw), note=NOTE)
    raise HTTPException(404, f"keyword '{keyword}' not in config/trends.yaml")
