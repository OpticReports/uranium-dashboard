"""GET /metrics (master table) and /metrics/{id}/history."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..jobs.refresh import compute_all
from ..sources.fred import fetch_bundle
from ..store.db import get_session
from ..store.models import MetricSnapshot

router = APIRouter(prefix="/metrics", tags=["metrics"])

_CATEGORY_LABELS = {
    "A": "Yield curve", "B": "Volatility", "C": "Term premium & real rates",
    "D": "Funding / plumbing", "E": "Auctions", "F": "Foreign / flows",
    "G": "Liquidity", "H": "Cross-asset", "I": "Recession model", "J": "Labor",
    "K": "Leading stack (additive, not in composite)",
}


@router.get("")
def list_metrics():
    """The master traffic-light table — computed live from the (cached) bundle."""
    bundle = fetch_bundle()
    metrics, _, composite, _ = compute_all(bundle)
    return {
        "categories": _CATEGORY_LABELS,
        "metrics": [m.as_dict() for m in metrics],
        "composite": {
            "score": composite.score, "band": composite.band,
            "coverage": composite.coverage, "category_scores": composite.category_scores,
            "contributions": composite.contributions,
            "n_red": composite.n_red, "n_critical": composite.n_critical,
        },
    }


@router.get("/{metric_id}/history")
def metric_history(metric_id: str, session: Session = Depends(get_session)):
    rows = session.execute(
        select(MetricSnapshot).where(MetricSnapshot.metric_id == metric_id)
        .order_by(MetricSnapshot.asof.asc())
    ).scalars().all()
    return [{"asof": r.asof.isoformat(), "value": r.value, "status": r.status,
             "percentile": r.percentile} for r in rows]
