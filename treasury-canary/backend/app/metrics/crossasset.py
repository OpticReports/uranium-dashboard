"""H. Cross-asset: stock-bond correlation regime, flight-to-quality, credit OAS.

The stocks<->treasuries relationship: a negative 60d correlation = healthy
diversification / flight-to-quality intact; a flip to positive = regime break
(both fall together, 2022-style) — flagged loudly.
"""
from __future__ import annotations

import math

from .assemble import simple_metric
from .base import MetricResult, Status, last_valid
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
    out.extend(_margin_metrics(bundle, sp))
    return out


def _month_end_closes(sp: tuple[list, list]) -> dict[str, float]:
    """'YYYY-MM' -> last close in that month (daily series in, monthly map out)."""
    out: dict[str, float] = {}
    for d, v in zip(sp[0], sp[1]):
        if v is not None:
            out[str(d)[:7]] = v
    return out


def _margin_metrics(bundle: dict, sp: tuple[list, list]) -> list[MetricResult]:
    """FINRA margin-debt gauges. Backtest (1997-2026, MARGIN_DEBT.md at the
    project root): margin growth in EXCESS of the market's own growth is the
    validated leading cell — YoY excess > +25pp preceded negative 12m S&P
    returns in 16 of 17 months (the 1999-2000 / 2007 / 2021 clusters). The raw
    level, and the viral "record net debit balance" framing, do NOT backtest:
    the credit/debit coverage ratio trends structurally lower, so record lows
    carry no timing signal — that context ships on the tiles on purpose."""
    md, mdv = bundle.get("margin_debit", ([], []))
    _, mcv = bundle.get("margin_credit", ([], []))
    pts = [(d, v) for d, v in zip(md, mdv) if v is not None]

    yoy_dates: list = []
    yoy_vals: list[float | None] = []
    excess_vals: list[float | None] = []
    spx_me = _month_end_closes(sp)
    for i, (d, v) in enumerate(pts):
        yoy_dates.append(d)
        base = pts[i - 12][1] if i >= 12 else None
        y = round((v / base - 1) * 100, 1) if base else None
        yoy_vals.append(y)
        ym, ym12 = f"{d.year:04d}-{d.month:02d}", f"{d.year - 1:04d}-{d.month:02d}"
        s_now, s_then = spx_me.get(ym), spx_me.get(ym12)
        spx_yoy = (s_now / s_then - 1) * 100 if (s_now and s_then) else None
        excess_vals.append(round(y - spx_yoy, 1) if (y is not None and spx_yoy is not None) else None)

    out: list[MetricResult] = []
    debit_now = last_valid([v for _, v in pts] or [None])
    out.append(simple_metric(
        "crossasset.margin_excess_yoy", "H", "Margin debt excess growth",
        yoy_dates, excess_vals, unit="pp", source="FINRA margin stats / FRED:SP500",
        note="Margin-debt YoY minus S&P YoY: leverage building FASTER than the market. "
             ">+25pp preceded negative 12m returns in 16 of 17 months (2000/2007/2021 "
             "clusters — n=3 independent episodes). Slow signal: 12m horizon, no "
             "monthly timing power."))

    m = simple_metric(
        "crossasset.margin_yoy", "H", "Margin debt growth (YoY)",
        yoy_dates, yoy_vals, unit="%", source="FINRA margin stats",
        note="Context for the excess gauge. Peaks LED the S&P peak in all five major "
             "drawdowns since 1997 (by 1-9 months). CONTRACTION is historically a "
             "buy-zone, not a warning — post-contraction 12m returns beat baseline.")
    m.informational = True
    if debit_now is not None:
        m.extra["debit_usd_bn"] = round(debit_now / 1e3, 0)
    out.append(m)

    cov_dates = [d for d, _ in pts]
    cov_vals: list[float | None] = []
    mc_by_date = {d: c for d, c in zip(md, mcv) if c is not None}
    for d, v in pts:
        c = mc_by_date.get(d)
        cov_vals.append(round(c / v, 2) if (c and v) else None)
    cm = simple_metric(
        "crossasset.margin_coverage", "H", "Investor cash coverage (credit/debit)",
        cov_dates, cov_vals, unit="x", source="FINRA margin stats",
        note="The viral 'record net debit balance' metric, normalized. Trends "
             "structurally lower (portfolio margin, cash swept outside brokerage), so "
             "record lows recur by construction and carry NO timing signal — bottom-"
             "decile months actually preceded ABOVE-baseline 12m returns. Watch the "
             "excess-growth gauge instead.")
    cm.informational = True
    cm.status = Status.GREEN if cm.value is not None else Status.STALE
    out.append(cm)
    return out
