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


def margin_series(bundle: dict, sp: tuple[list, list]
                  ) -> tuple[list, list[float | None], list[float | None], list[float | None]]:
    """(dates, margin_yoy %, excess_yoy pp, coverage x) from the FINRA series.
    Excess is only populated where the S&P leg exists (FRED SP500 ~10y)."""
    md, mdv = bundle.get("margin_debit", ([], []))
    _, mcv = bundle.get("margin_credit", ([], []))
    mc_by_date = {d: c for d, c in zip(md, mcv) if c is not None}
    pts = [(d, v) for d, v in zip(md, mdv) if v is not None]

    spx_me = _month_end_closes(sp)
    dates: list = []
    yoy_vals: list[float | None] = []
    excess_vals: list[float | None] = []
    cov_vals: list[float | None] = []
    for i, (d, v) in enumerate(pts):
        dates.append(d)
        base = pts[i - 12][1] if i >= 12 else None
        y = round((v / base - 1) * 100, 1) if base else None
        yoy_vals.append(y)
        ym, ym12 = f"{d.year:04d}-{d.month:02d}", f"{d.year - 1:04d}-{d.month:02d}"
        s_now, s_then = spx_me.get(ym), spx_me.get(ym12)
        spx_yoy = (s_now / s_then - 1) * 100 if (s_now and s_then) else None
        excess_vals.append(round(y - spx_yoy, 1) if (y is not None and spx_yoy is not None) else None)
        c = mc_by_date.get(d)
        cov_vals.append(round(c / v, 2) if (c and v) else None)
    return dates, yoy_vals, excess_vals, cov_vals


# Leverage-cycle state machine + what happened next, historically. Stats from
# the 1997-2026 SPY study (MARGIN_DEBT.md): mutually-exclusive monthly states,
# forward S&P returns (overlapping windows — treat as descriptive, not iid).
def leverage_state(yoy: float | None, excess: float | None) -> str | None:
    if yoy is None:
        return None
    if yoy <= -15:
        return "WASHOUT"
    if yoy < 0:
        return "SQUEEZE"
    if (excess is not None and excess >= 25) or yoy >= 40:
        return "BLOWOFF"
    if (excess is not None and excess >= 15) or yoy >= 30:
        return "ELEVATED"
    return "NEUTRAL"


POST_BLOWOFF_W = 6      # months; pre-registered (study_post_blowoff.py)


def leverage_states_path(yoy_vals: list, excess_vals: list) -> list:
    """Path-aware monthly states: identical to leverage_state except that
    ELEVATED/NEUTRAL months within POST_BLOWOFF_W months AFTER a BLOWOFF
    month are labeled POST_BLOWOFF — the rollover leg. A memoryless snapshot
    read the historically dangerous transition (blowoff subsiding) as
    de-escalation (user finding, 2026-08-15). Rules, frozen a priori:
    - BLOWOFF and SQUEEZE/WASHOUT always win: re-inflation (excess >= +25pp
      or YoY >= 40) returns to BLOWOFF and re-anchors; YoY < 0 hands off to
      the squeeze states.
    - Beyond W months with no re-entry the rollover FIZZLES to its plain
      level state (roughly half of blowoffs fizzle).
    Anchor uses only PAST months — no lookahead (gate-tested)."""
    out, last_blow = [], None
    for i, (y, e) in enumerate(zip(yoy_vals, excess_vals)):
        lvl = leverage_state(y, e)
        if lvl == "BLOWOFF":
            last_blow = i
        if (lvl in ("ELEVATED", "NEUTRAL") and last_blow is not None
                and 1 <= i - last_blow <= POST_BLOWOFF_W):
            out.append("POST_BLOWOFF")
        else:
            out.append(lvl)
    return out


LEVERAGE_PLAYBOOK: dict[str, dict] = {
    "POST_BLOWOFF": {
        "label": "Post-blowoff rollover — leverage peaked and is unwinding",
        "evidence": "Episode-level permutation p=0.028 vs all-months baseline "
                    "(fwd12 mean -3.8% vs +8.4%; 10 episodes incl. the current "
                    "one) - SHARPER separation than BLOWOFF itself (p=0.058), "
                    "consistent with the decision-test finding that crash "
                    "damage lands AFTER the blowoff ends. Basis: ^GSPC price, "
                    "1997+, rule frozen before scoring (scripts/"
                    "study_post_blowoff.py, 2026-08-15).",
        "stats": {"fwd3": {"n": 31, "mean": 2.1, "median": 0.4, "pct_lower": 48, "worst": -12.2},
                  "fwd6": {"n": 30, "mean": 4.7, "median": 7.3, "pct_lower": 40, "worst": -20.6},
                  "fwd12": {"n": 26, "mean": -3.8, "median": -7.6, "pct_lower": 58, "worst": -44.8}},
        "read": "The dangerous leg of the cycle: leverage has peaked and is "
                "unwinding, but hasn't squeezed yet. 58% of months here saw "
                "the S&P LOWER 12 months later - median -7.6%, worst -44.8% "
                "(baseline +8.4%). Burns slow: 3m median +0.4%. Past episodes: "
                "1998, the 2000 top, 2007-09..2008-03, 2010 (fizzled), "
                "2021-22, 2025-11..2026-03 (re-inflated).",
        "action": "Treat as BLOWOFF-or-worse, NOT de-escalation: keep reducing "
                  "leverage-sensitive risk over quarters, tighten stops. "
                  "Re-inflation (excess >= +25pp) returns to BLOWOFF; margin "
                  "YoY < 0 starts the SQUEEZE - where crash damage "
                  "historically lands.",
    },
    "BLOWOFF": {
        "label": "Blowoff — leverage building far faster than the market",
        "evidence": "SUGGESTIVE, not proven: episode-level bootstrap p=0.058 (8 episodes). And the decision test failed: mechanically de-risking on this state (50% or 0% exposure, acted at publication lag, 1998-2026) REDUCED risk-adjusted returns vs holding — historical crash damage lands after BLOWOFF ends, in SQUEEZE/WASHOUT months. Treat as risk-awareness, not a timing rule.",
        "stats": {"fwd3": {"n": 28, "mean": 0.7, "median": 0.9, "pct_lower": 39, "worst": -13.2},
                  "fwd6": {"n": 28, "mean": -0.4, "median": -1.2, "pct_lower": 61, "worst": -18.8},
                  "fwd12": {"n": 27, "mean": -7.3, "median": -11.8, "pct_lower": 78, "worst": -37.4}},
        "read": "21 of 27 months here (78%) saw the S&P LOWER 12 months later — median "
                "−12%, worst −37%. But only 39% were lower 3 months out: this signal "
                "burns slow. Historically the 1999-2000, 2007 and 2021 tops.",
        "action": "Not a sell-this-month trigger — a reduce-and-hedge-over-quarters "
                  "regime. Tighten stops, trim leverage, demand more edge per position.",
    },
    "ELEVATED": {
        "label": "Elevated build — leverage outpacing the market",
        "evidence": "Not statistically distinguishable from baseline (bootstrap p=0.69, 18 episodes).",
        "stats": {"fwd3": {"n": 42, "mean": 1.5, "median": 1.3, "pct_lower": 40, "worst": -14.3},
                  "fwd6": {"n": 39, "mean": 1.8, "median": 2.6, "pct_lower": 46, "worst": -13.5},
                  "fwd12": {"n": 35, "mean": 1.6, "median": 5.5, "pct_lower": 31, "worst": -44.8}},
        "read": "Forward returns compress well below baseline (12m mean +1.6% vs +11.6% "
                "in NEUTRAL) with a fat left tail (worst −45%). The staging area for "
                "blowoffs.",
        "action": "Normal positioning, but stop adding leverage-sensitive risk and "
                  "watch for the push into BLOWOFF.",
    },
    "NEUTRAL": {
        "label": "Neutral — leverage tracking the market",
        "evidence": "VALIDATED: best-regime claim holds under episode-level bootstrap (p=0.007, CI90 82-95% positive vs 76% baseline).",
        "stats": {"fwd3": {"n": 165, "mean": 3.1, "median": 3.7, "pct_lower": 24, "worst": -19.9},
                  "fwd6": {"n": 165, "mean": 6.5, "median": 6.9, "pct_lower": 16, "worst": -20.6},
                  "fwd12": {"n": 164, "mean": 11.6, "median": 11.9, "pct_lower": 12, "worst": -38.3}},
        "read": "The best regime: 88% of months here saw the S&P higher 12 months later "
                "(mean +11.6%). Margin risk is not the binding constraint.",
        "action": "No leverage-cycle adjustment needed. Trade the other signals.",
    },
    "SQUEEZE": {
        "label": "Squeeze — leverage contracting (0 to −15% YoY)",
        "evidence": "Not statistically distinguishable from baseline (bootstrap p=0.82, 14 episodes) — the re-entry read rests on direction and the fast strip's validated WASHED_OUT analog, not this sample alone.",
        "stats": {"fwd3": {"n": 62, "mean": 0.8, "median": 2.7, "pct_lower": 39, "worst": -30.0},
                  "fwd6": {"n": 62, "mean": 2.3, "median": 5.1, "pct_lower": 26, "worst": -42.6},
                  "fwd12": {"n": 62, "mean": 11.7, "median": 14.0, "pct_lower": 21, "worst": -36.8}},
        "read": "The squeeze-out: 12m forward returns back to full-baseline (+11.7% mean, "
                "79% higher) — the excess leverage is largely behind you. Near-term still "
                "choppy (worst 3m: −30%).",
        "action": "Historically a re-entry zone for scaling in, NOT a reason to sell. "
                  "Selling on 'margin debt collapsing' headlines here = selling the low.",
    },
    "WASHOUT": {
        "label": "Washout — deep deleveraging (YoY ≤ −15%)",
        "evidence": "Unprovable at this n (7 episodes, bootstrap CI90 22-100%): direction only.",
        "stats": {"fwd3": {"n": 42, "mean": 1.0, "median": 2.4, "pct_lower": 43, "worst": -23.7},
                  "fwd6": {"n": 42, "mean": 1.9, "median": 1.9, "pct_lower": 43, "worst": -34.7},
                  "fwd12": {"n": 42, "mean": 5.8, "median": 10.5, "pct_lower": 38, "worst": -28.2}},
        "read": "Crash in progress: forced selling is happening NOW. Bimodal outcomes — "
                "median 12m +10.5% (bottoms form inside washouts) but 38% of months "
                "still had more downside (2001-02, 2008-09 mid-crash reads).",
        "action": "Scale in staged, don't lump in — and don't sell into it. The move to "
                  "SQUEEZE (contraction easing) marks the leverage reset completing.",
    },
}


def _margin_metrics(bundle: dict, sp: tuple[list, list]) -> list[MetricResult]:
    """FINRA margin-debt gauges. Backtest (1997-2026, MARGIN_DEBT.md at the
    project root): margin growth in EXCESS of the market's own growth is the
    validated leading cell — YoY excess > +25pp preceded negative 12m S&P
    returns in 16 of 17 months (the 1999-2000 / 2007 / 2021 clusters). The raw
    level, and the viral "record net debit balance" framing, do NOT backtest:
    the credit/debit coverage ratio trends structurally lower, so record lows
    carry no timing signal — that context ships on the tiles on purpose."""
    yoy_dates, yoy_vals, excess_vals, cov_vals = margin_series(bundle, sp)
    _, mdv = bundle.get("margin_debit", ([], []))

    out: list[MetricResult] = []
    debit_now = last_valid(list(mdv) or [None])
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

    cm = simple_metric(
        "crossasset.margin_coverage", "H", "Investor cash coverage (credit/debit)",
        yoy_dates, cov_vals, unit="x", source="FINRA margin stats",
        note="The viral 'record net debit balance' metric, normalized. Trends "
             "structurally lower (portfolio margin, cash swept outside brokerage), so "
             "record lows recur by construction and carry NO timing signal — bottom-"
             "decile months actually preceded ABOVE-baseline 12m returns. Watch the "
             "excess-growth gauge instead.")
    cm.informational = True
    cm.status = Status.GREEN if cm.value is not None else Status.STALE
    out.append(cm)
    return out
