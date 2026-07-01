"""B. Volatility metrics. MOVE has no free feed -> a labeled realized-vol PROXY
built from daily 10y yield changes, scaled toward MOVE units. VIX from FRED.
"""
from __future__ import annotations

import math

from .assemble import simple_metric
from .base import (
    MetricResult, Status, delta, last_valid, percentile_rank,
)
from ..scoring import thresholds as T


def _move_proxy_series(dates: list, dgs10: list[float | None]) -> tuple[list, list[float | None]]:
    """Rolling 20d annualized stdev of daily 10y yield CHANGES, scaled to ~MOVE units.

    MOVE is bp-vol of options; this realized-vol proxy tracks its regime, not its
    level. Scaling constant is a rough calibration — label as PROXY in the UI.
    """
    changes: list[float | None] = [None]
    for i in range(1, len(dgs10)):
        a, b = dgs10[i], dgs10[i - 1]
        changes.append((a - b) if (a is not None and b is not None) else None)
    win = 20
    out: list[float | None] = []
    SCALE = 1000.0  # bp/day realized vol (in pct pts) -> MOVE-ish units; heuristic
    for i in range(len(changes)):
        window = [c for c in changes[max(0, i - win + 1): i + 1] if c is not None]
        if len(window) < win // 2:
            out.append(None)
            continue
        mean = sum(window) / len(window)
        var = sum((c - mean) ** 2 for c in window) / len(window)
        out.append(math.sqrt(var) * math.sqrt(252) * SCALE)
    return dates, out


def build_volatility_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []
    vixd, vixv = bundle.get("vix", ([], []))
    out.append(simple_metric(
        "vol.vix", "B", "VIX", vixd, vixv, unit="", source="FRED:VIXCLS",
        note="Equity implied vol. Rising rate-vol with falling equity-vol = rates-led stress."))

    dgs10 = bundle.get("10y", ([], []))
    md, mv = _move_proxy_series(dgs10[0], dgs10[1])
    move = simple_metric(
        "vol.move", "B", "MOVE (proxy)", md, mv, unit="≈MOVE", source="PROXY:realized 10y vol",
        note="PROXY: realized vol of daily 10y yield changes, scaled to MOVE units. Regime, not level.")
    out.append(move)

    # MOVE/VIX ratio: rates stress relative to equity stress.
    move_val = last_valid(mv)
    vix_val = last_valid(vixv)
    ratio = round(move_val / vix_val, 2) if (move_val and vix_val) else None
    ratio_status = T.classify("vol.move_vix", ratio) if ratio is not None else Status.STALE
    out.append(MetricResult(
        metric_id="vol.move_vix", category="B", label="MOVE/VIX (proxy)", value=ratio,
        status=ratio_status, note="High = rates-driven stress dominating equity stress.",
        source_series="PROXY"))
    return out
