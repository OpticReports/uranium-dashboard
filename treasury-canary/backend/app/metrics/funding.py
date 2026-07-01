"""D. Funding / plumbing metrics (from FRED daily rates)."""
from __future__ import annotations

from .assemble import simple_metric
from .base import MetricResult
from .curve import build_spread


def build_funding_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []
    sofr = bundle.get("sofr", ([], []))
    effr = bundle.get("effr", ([], []))
    iorb = bundle.get("iorb", ([], []))

    # SOFR-EFFR (bps): secured vs unsecured overnight; a spike = collateral/funding stress.
    d, spread = build_spread(effr[0], effr[1], sofr[0], sofr[1])  # sofr - effr
    out.append(simple_metric(
        "funding.sofr_effr", "D", "SOFR − EFFR", d, spread, unit="bps", scale=100.0,
        note="Secured minus unsecured overnight; sustained spike = funding/collateral stress.",
        source="FRED:SOFR-EFFR"))

    d2, s2 = build_spread(iorb[0], iorb[1], sofr[0], sofr[1])  # sofr - iorb
    out.append(simple_metric(
        "funding.sofr_iorb", "D", "SOFR − IORB", d2, s2, unit="bps", scale=100.0,
        note="SOFR above IORB signals reserves scarcity / repo pressure.",
        source="FRED:SOFR-IORB"))
    return out
