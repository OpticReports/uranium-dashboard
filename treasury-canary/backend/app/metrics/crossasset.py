"""H. Cross-asset: stock-bond correlation regime, flight-to-quality, credit OAS.

The stocks<->treasuries relationship: a negative 60d correlation = healthy
diversification / flight-to-quality intact; a flip to positive = regime break
(both fall together, 2022-style) — flagged loudly.
"""
from __future__ import annotations

import math

from .assemble import simple_metric
from .base import MetricResult, Status
from ..scoring import thresholds as T


def _aligned_returns(sp: tuple[list, list], y10: tuple[list, list]):
    """Common-date daily S&P returns and a bond price-return proxy (−Δyield)."""
    msp = dict(zip(sp[0], sp[1]))
    my = dict(zip(y10[0], y10[1]))
    common = sorted(set(msp) & set(my))
    dates, sp_ret, bond_ret = [], [], []
    for i in range(1, len(common)):
        d0, d1 = common[i - 1], common[i]
        p0, p1 = msp.get(d0), msp.get(d1)
        y0, y1 = my.get(d0), my.get(d1)
        if None in (p0, p1, y0, y1) or not p0:
            continue
        dates.append(d1)
        sp_ret.append((p1 - p0) / p0)
        bond_ret.append(-(y1 - y0))  # price up when yield down
    return dates, sp_ret, bond_ret


def _rolling_corr(a: list[float], b: list[float], win: int = 60) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(a)):
        xa = a[max(0, i - win + 1): i + 1]
        xb = b[max(0, i - win + 1): i + 1]
        if len(xa) < max(10, win // 2):
            out.append(None)
            continue
        ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
        cov = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
        va = math.sqrt(sum((x - ma) ** 2 for x in xa))
        vb = math.sqrt(sum((y - mb) ** 2 for y in xb))
        out.append(round(cov / (va * vb), 3) if va and vb else None)
    return out


def build_crossasset_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []
    sp = bundle.get("sp500", ([], []))
    y10 = bundle.get("10y", ([], []))
    dates, sp_ret, bond_ret = _aligned_returns(sp, y10)

    corr = _rolling_corr(sp_ret, bond_ret)
    out.append(simple_metric(
        "crossasset.stock_bond_corr", "H", "Stock-bond corr (60d)", dates, corr,
        unit="ρ", source="FRED:SP500,DGS10",
        note="Negative = diversification intact (flight-to-quality works); positive flip = regime break."))

    # Flight-to-quality: fraction of recent equity down-days on which bonds rallied.
    ftq_dates, ftq_vals = [], []
    win = 20
    for i in range(len(sp_ret)):
        lo = max(0, i - win + 1)
        downs = [(s, br) for s, br in zip(sp_ret[lo:i + 1], bond_ret[lo:i + 1]) if s < 0]
        ftq_dates.append(dates[i])
        ftq_vals.append(round(sum(1 for _, br in downs if br > 0) / len(downs), 2) if downs else None)
    out.append(simple_metric(
        "crossasset.flight_to_quality", "H", "Flight-to-quality (20d)", ftq_dates, ftq_vals,
        unit="frac", source="FRED:SP500,DGS10",
        note="Share of equity down-days with a Treasury bid. Falling = money not rotating stocks->bonds."))

    hy = bundle.get("hy_oas", ([], []))
    out.append(simple_metric(
        "crossasset.hy_oas", "H", "HY OAS", hy[0], hy[1], unit="bps", scale=100.0,
        source="FRED:BAMLH0A0HYM2",
        note="Credit cross-confirmation: Treasury stress + widening HY = higher-conviction recession signal."))
    ig = bundle.get("ig_oas", ([], []))
    out.append(simple_metric(
        "crossasset.ig_oas", "H", "IG OAS", ig[0], ig[1], unit="bps", scale=100.0,
        source="FRED:BAMLC0A0CM", note="Investment-grade credit spread trend."))
    return out
