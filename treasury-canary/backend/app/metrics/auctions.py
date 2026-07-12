"""E. Auction demand — is structural demand for Treasury duration eroding?

Built on recent COMPLETED coupon auctions (Notes+Bonds) from FiscalData. Each
metric is a trailing-8-auction average, with the change vs the prior 8 as the
trend and a percentile vs all rolling-8 windows in the fetched history. Weak
auctions are the slow-burn version of the fiscal pin: bid-to-cover fading,
dealers forced to absorb more, foreign (indirect) share shrinking.
"""
from __future__ import annotations

from datetime import date, datetime

from ..scoring import thresholds as T
from .base import MetricResult, Status, percentile_rank

WINDOW = 8  # auctions per averaging window (~1 month of coupon supply)


def _rolling_mean(vals: list[float], window: int = WINDOW) -> list[float | None]:
    return [round(sum(vals[i - window + 1:i + 1]) / window, 2) if i >= window - 1 else None
            for i in range(len(vals))]


def _asof(auctions: list[dict]) -> date | None:
    if not auctions:
        return None
    try:
        return datetime.strptime(auctions[-1]["auction_date"], "%Y-%m-%d").date()
    except (KeyError, ValueError, TypeError):
        return None


def _metric_from(auctions: list[dict], key: str, metric_id: str, label: str,
                 note: str) -> MetricResult:
    vals = [a[key] for a in auctions if a.get(key) is not None]
    roll = _rolling_mean(vals) if len(vals) >= WINDOW else []
    cur = roll[-1] if roll else None
    prev = roll[-1 - WINDOW] if len(roll) > WINDOW and roll[-1 - WINDOW] is not None else None
    return MetricResult(
        metric_id=metric_id, category="E", label=label, value=cur,
        status=T.classify(metric_id, cur) if cur is not None else Status.STALE,
        asof=_asof(auctions), unit="%" if key != "bid_to_cover" else "x",
        delta_20d=(round(cur - prev, 2) if (cur is not None and prev is not None) else None),
        percentile=percentile_rank(roll, cur), note=note,
        source_series="FiscalData:auctions_query (Notes+Bonds)",
    )


def build_auction_metrics(auctions: list[dict]) -> list[MetricResult]:
    return [
        _metric_from(
            auctions, "bid_to_cover", "auctions.bid_to_cover",
            f"Bid-to-cover (avg last {WINDOW} coupon auctions)",
            "Total bids / amount sold. The headline demand gauge: <2.4 = soft, <2.2 = "
            "historically weak. Fading b2c while deficits grow = structural demand eroding."),
        _metric_from(
            auctions, "dealer_pct", "auctions.dealer_takedown",
            f"Primary-dealer takedown (avg last {WINDOW})",
            "Share of competitive accepted absorbed by dealers — the buyers of LAST resort. "
            "High/rising takedown = real investors stepped back and dealers were forced to "
            "warehouse supply. The single best 'weak auction' tell."),
        _metric_from(
            auctions, "indirect_pct", "auctions.indirect_share",
            f"Indirect (foreign proxy) share (avg last {WINDOW})",
            "Indirect bidders ≈ foreign central banks/institutions routing through dealers. "
            "A sustained slide is the auction-level symptom of the foreign-demand story "
            "(cross-check category F custody holdings)."),
    ]
