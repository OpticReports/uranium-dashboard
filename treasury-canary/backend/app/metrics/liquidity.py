"""G. Liquidity — the OFR Financial Stress Index as external cross-check.

The OFR FSI is a daily, 33-variable cross-asset stress index published by the
Office of Financial Research (0 = average conditions; positive = above-average
stress). It is INDEPENDENT of this dashboard's composite, which makes it the
ideal disagreement detector: our composite hot while FSI is calm suggests
rates-localized stress; both hot = broad-based.

(On-the-run/off-the-run spreads still have no clean free source; that slot
remains open rather than filled with a fake proxy.)
"""
from __future__ import annotations

from .assemble import simple_metric
from .base import MetricResult


def build_liquidity_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    d, v = bundle.get("ofr_fsi", ([], []))
    return [simple_metric(
        "liquidity.ofr_fsi", "G", "OFR Financial Stress Index", d, v, unit="idx",
        source="OFR:fsi.csv",
        note="Independent 33-variable stress index (0 = average). >1 = elevated, >3 = "
             "crisis-grade. Use as the disagreement check on this dashboard's own composite.")]
