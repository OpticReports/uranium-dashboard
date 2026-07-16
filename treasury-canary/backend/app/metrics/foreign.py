"""F. Foreign flows — are foreign officials net sellers of Treasuries?

Fed custody holdings (weekly, WMTSECL1): marketable USTs the New York Fed holds
in custody for foreign central banks. A sustained decline = official-sector
selling — structural pressure on demand rather than a cyclical canary, hence
the deliberately low composite weight (0.05). Cross-checks the auction panel's
indirect share and the flow compass's debasement regime.
"""
from __future__ import annotations

from .assemble import simple_metric
from .base import MetricResult

_WEEKS_26 = 26


def build_foreign_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    d, v = bundle.get("custody", ([], []))
    # 26-week % change series so delta/percentile are meaningful.
    clean = [(dd, vv) for dd, vv in zip(d, v) if vv is not None]
    dates = [dd for dd, _ in clean]
    chg: list[float | None] = []
    for i in range(len(clean)):
        prev = clean[i - _WEEKS_26][1] if i >= _WEEKS_26 else None
        chg.append(round((clean[i][1] - prev) / prev * 100.0, 2) if prev else None)
    return [simple_metric(
        "foreign.custody_26w", "F", "Foreign custody holdings (26w change)",
        dates, chg, unit="%", source="FRED:WMTSECL1",
        note="Fed custody of Treasuries for foreign officials. Sustained decline = "
             "official-sector selling — structural demand pressure (slow-moving; weighted "
             "low by design). Confirms/vetoes the auction indirect-share trend.")]
