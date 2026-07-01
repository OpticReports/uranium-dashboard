"""C. Term premium & real rates (FRED: ACM TP10, DFII10, T5YIFR)."""
from __future__ import annotations

from .assemble import simple_metric
from .base import MetricResult


def build_premium_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []
    acm = bundle.get("acm_tp10", ([], []))
    out.append(simple_metric(
        "premium.acm_tp10", "C", "ACM 10y term premium", acm[0], acm[1], unit="pct",
        source="FRED:THREEFYTP10",
        note="Rising/positive = supply/fiscal risk premium; deeply negative historically near cycle tops."))

    real10 = bundle.get("real_10y", ([], []))
    out.append(simple_metric(
        "premium.real_10y", "C", "Real 10y (TIPS)", real10[0], real10[1], unit="pct",
        source="FRED:DFII10",
        note="Restrictive real rates tighten financial conditions with a lag."))

    be = bundle.get("breakeven_5y5y", ([], []))
    # informational (no threshold) — anchoring of long-run inflation expectations
    out.append(simple_metric(
        "premium.breakeven_5y5y", "C", "5y5y breakeven", be[0], be[1], unit="pct",
        source="FRED:T5YIFR",
        note="Long-run inflation expectations; de-anchoring (both tails) is the risk."))
    return out
