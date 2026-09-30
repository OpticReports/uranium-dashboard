"""Labor Stress Board — the rules of studies/labor-stress-board.md, computed
from raw FRED observations. The study imports THIS module, so the backtest
scores exactly what the dashboard shows.

Pure functions over monthly dicts keyed by (year, month). Conventions (spec):
- a weekly series enters a month as its last weekly value dated in it;
- missing months are skipped, never interpolated; a 3-month average needs
  >= 2 values; 12-/24-month windows use whatever months exist;
- every threshold comparison is on values rounded to 3 decimals.
"""
from __future__ import annotations

from datetime import date, timedelta

YM = tuple[int, int]

# Thresholds fixed in the pre-registration (★ = external/published).
RULES: dict[str, dict] = {
    "A1": {"leg": "A", "label": "Insured unemployment (Richmond Fed SOS) ★",
           "threshold": 0.20, "strict": True, "unit": "pp"},
    "A2": {"leg": "A", "label": "Job losers, Sahm-style", "threshold": 0.30,
           "strict": False, "unit": "pp"},
    "A3": {"leg": "A", "label": "Continuing claims y/y (not seasonally adj.)",
           "threshold": 10.0, "strict": False, "unit": "%"},
    "B1": {"leg": "B", "label": "Prime-age employment rate drawdown",
           "threshold": 0.50, "strict": False, "unit": "pp", "watch": 0.30},
    "B2": {"leg": "B", "label": "Participation-adjusted unemployment, Sahm-style",
           "threshold": 0.50, "strict": False, "unit": "pp"},
    "C1": {"leg": "C", "label": "Sahm rule ★", "threshold": 0.50, "strict": False,
           "unit": "pp"},
}


def ym(d: date) -> YM:
    return (d.year, d.month)


def ym_add(k: YM, n: int) -> YM:
    i = k[0] * 12 + (k[1] - 1) + n
    return (i // 12, i % 12 + 1)


def ym_diff(a: YM, b: YM) -> int:
    return (a[0] * 12 + a[1]) - (b[0] * 12 + b[1])


def monthly(dates: list[date], vals: list[float | None]) -> dict[YM, float]:
    """Monthly (or weekly -> last value dated in the month)."""
    out: dict[YM, float] = {}
    for d, v in zip(dates, vals):
        if v is not None:
            out[ym(d)] = float(v)          # later obs in the month overwrite
    return out


def _months(x: dict[YM, float]) -> list[YM]:
    return sorted(x)


def ma3(x: dict[YM, float]) -> dict[YM, float]:
    out = {}
    for k in _months(x):
        w = [x[m] for m in (ym_add(k, -2), ym_add(k, -1), k) if m in x]
        if len(w) >= 2:
            out[k] = sum(w) / len(w)
    return out


def rise_over_prior_min(x: dict[YM, float], window: int = 12) -> dict[YM, float]:
    """Sahm-style: MA3 minus the minimum MA3 over the prior `window` months."""
    m = ma3(x)
    out = {}
    for k in _months(m):
        prior = [m[j] for j in (ym_add(k, -i) for i in range(1, window + 1)) if j in m]
        if prior:
            out[k] = round(m[k] - min(prior), 3)
    return out


def drawdown_from_prior_max(x: dict[YM, float], window: int = 12) -> dict[YM, float]:
    m = ma3(x)
    out = {}
    for k in _months(m):
        prior = [m[j] for j in (ym_add(k, -i) for i in range(1, window + 1)) if j in m]
        if prior:
            out[k] = round(max(prior) - m[k], 3)
    return out


def sos(dates: list[date], iursa: list[float | None]) -> dict[YM, float]:
    """Richmond Fed SOS: 26-week average of the insured unemployment rate minus
    its minimum over the prior 52 weeks; weekly -> month via last week."""
    pts = [(d, float(v)) for d, v in zip(dates, iursa) if v is not None]
    avg: list[tuple[date, float]] = []
    for i in range(25, len(pts)):
        avg.append((pts[i][0], sum(v for _, v in pts[i - 25:i + 1]) / 26))
    wk: list[tuple[date, float]] = []
    for i in range(52, len(avg)):
        wk.append((avg[i][0], round(avg[i][1] - min(v for _, v in avg[i - 52:i]), 3)))
    return monthly([d for d, _ in wk], [v for _, v in wk])


def claims_yoy(dates: list[date], ccnsa: list[float | None]) -> dict[YM, float]:
    """4-week average of NSA continuing claims vs the same 4 weeks 52 weeks
    earlier (364 days — the same weekday), in %; weekly -> month via last week."""
    pts = [(d, float(v)) for d, v in zip(dates, ccnsa) if v is not None]
    by = {d: v for d, v in pts}
    out_d, out_v = [], []
    for i in range(3, len(pts)):
        d = pts[i][0]
        cur = [pts[j][1] for j in range(i - 3, i + 1)]
        prev = [by.get(pts[j][0] - timedelta(days=364)) for j in range(i - 3, i + 1)]
        if None in prev:
            continue
        out_d.append(d)
        out_v.append(round(100 * (sum(cur) / sum(prev) - 1), 3))
    return monthly(out_d, out_v)


def paur(unemploy: dict[YM, float], clf: dict[YM, float],
         lfpr_prime: dict[YM, float], pop: dict[YM, float]) -> dict[YM, float]:
    """Participation-adjusted unemployment rate: add back as unemployed the
    prime-age participation shortfall vs its 24-month high, scaled to the 16+
    population. An UPPER bound — every shortfall counts as hidden unemployment."""
    out = {}
    for k in _months(unemploy):
        if k not in clf or k not in lfpr_prime or k not in pop:
            continue
        hist = [lfpr_prime[j] for j in (ym_add(k, -i) for i in range(0, 24)) if j in lfpr_prime]
        gap = max(0.0, max(hist) - lfpr_prime[k]) / 100 * pop[k]
        out[k] = 100 * (unemploy[k] + gap) / (clf[k] + gap)
    return out


def rule_values(series: dict[str, tuple[list[date], list[float | None]]]
                ) -> dict[str, dict[YM, float]]:
    """All six rule VALUES (not yet thresholded). `series` keys:
    iursa, ccnsa, job_losers, clf, epop_prime, lfpr_prime, pop16, unemploy, sahm."""
    g = {k: monthly(*v) for k, v in series.items() if k not in ("iursa", "ccnsa")}
    jl = {k: 100 * g["job_losers"][k] / g["clf"][k]
          for k in g.get("job_losers", {}) if k in g.get("clf", {})}
    pa = paur(g.get("unemploy", {}), g.get("clf", {}), g.get("lfpr_prime", {}),
              g.get("pop16", {}))
    return {
        "A1": sos(*series["iursa"]) if "iursa" in series else {},
        "A2": rise_over_prior_min(jl),
        "A3": claims_yoy(*series["ccnsa"]) if "ccnsa" in series else {},
        "B1": drawdown_from_prior_max(g.get("epop_prime", {})),
        "B2": rise_over_prior_min(pa),
        "C1": {k: round(v, 3) for k, v in g.get("sahm", {}).items()},
        "_paur": pa,
    }


def lit(values: dict[str, dict[YM, float]]) -> dict[str, dict[YM, bool]]:
    out = {}
    for rid, spec in RULES.items():
        t = spec["threshold"]
        out[rid] = {k: (round(v, 3) > t if spec["strict"] else round(v, 3) >= t)
                    for k, v in values.get(rid, {}).items()}
    return out


def board(lit_map: dict[str, dict[YM, bool]], window: int = 1) -> dict[YM, str]:
    """ALERT when >= 1 Leg-A rule AND >= 1 Leg-B/C rule are lit within the last
    `window` months (window=1: same month); WATCH when any rule is lit this
    month; else CLEAR."""
    months = sorted(set().union(*[set(v) for v in lit_map.values()]))
    out: dict[YM, str] = {}
    for k in months:
        recent = [ym_add(k, -i) for i in range(window)]
        a = any(lit_map[r].get(m) for r in ("A1", "A2", "A3") for m in recent)
        b = any(lit_map[r].get(m) for r in ("B1", "B2", "C1") for m in recent)
        now = any(lit_map[r].get(k) for r in RULES)
        out[k] = "ALERT" if (a and b) else ("WATCH" if now else "CLEAR")
    return out
