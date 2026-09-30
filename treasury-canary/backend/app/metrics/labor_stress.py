"""Labor Stress Board — the rules of studies/labor-stress-board.md, computed
from raw FRED observations. The study imports THIS module, so the backtest
scores exactly what the dashboard shows.

Pure functions over monthly dicts keyed by (year, month). Conventions (spec):
- a weekly series enters month M as the week ending 7 days after the CPS
  reference week (the Sun-Sat week containing the 12th) — released the
  Thursday before M's jobs report (spec v1 A6);
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


def ym_str(k: YM) -> str:
    return f"{k[0]}-{k[1]:02d}"


def onsets(flags: dict[YM, bool], quiet: int = 6) -> list[YM]:
    """Spec v1 A3: first lit month preceded by >= `quiet` OBSERVED unlit
    months (missing months are neither); a spell lit at the first computable
    month is left-censored (never an onset)."""
    out, unlit = [], 0
    for k in sorted(flags):
        if flags[k]:
            if unlit >= quiet:
                out.append(k)
            unlit = 0
        else:
            unlit += 1
    return out


def monthly(dates: list[date], vals: list[float | None]) -> dict[YM, float]:
    """Monthly (or weekly -> last value dated in the month)."""
    out: dict[YM, float] = {}
    for d, v in zip(dates, vals):
        if v is not None:
            out[ym(d)] = float(v)          # later obs in the month overwrite
    return out


def ref_week_plus7(k: YM) -> date:
    """Saturday ending the week after the CPS reference week of month k."""
    d12 = date(k[0], k[1], 12)
    sat = d12 + timedelta(days=(5 - d12.weekday()) % 7)
    return sat + timedelta(days=7)


def weekly_to_month(dates: list[date], vals: list[float | None]) -> dict[YM, float]:
    """Weekly -> month via the knowable week (A6): the observation dated the
    target Saturday, else the latest one within the 6 days before it."""
    pts = sorted((d, v) for d, v in zip(dates, vals) if v is not None)
    if not pts:
        return {}
    by = dict(pts)
    ds = [d for d, _ in pts]
    out: dict[YM, float] = {}
    k = ym(ds[0])
    import bisect
    while True:
        t = ref_week_plus7(k)
        if t > ds[-1] + timedelta(days=6):
            break
        if t in by:
            out[k] = by[t]
        else:
            i = bisect.bisect_right(ds, t) - 1
            if i >= 0 and (t - ds[i]).days <= 6:
                out[k] = pts[i][1]
        k = ym_add(k, 1)
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
    for i in range(52, len(avg)):                       # weeks t-52..t-1
        wk.append((avg[i][0], round(avg[i][1] - min(v for _, v in avg[i - 52:i]), 3)))
    return weekly_to_month([d for d, _ in wk], [v for _, v in wk])


def claims_yoy(dates: list[date], ccnsa: list[float | None],
               denom: tuple[list[date], list[float | None]] | None = None
               ) -> dict[YM, float]:
    """4-week average of NSA continuing claims vs the 4-week average exactly 52
    observations earlier, in %. With `denom` (COVEMP), claims are first divided
    by covered employment (the v1 sensitivity). Weekly -> month via A6."""
    pts = [(d, float(v)) for d, v in zip(dates, ccnsa) if v is not None]
    if denom is not None:
        dv = sorted((d, float(v)) for d, v in zip(*denom) if v is not None)
        import bisect
        dd = [d for d, _ in dv]
        norm = []
        for d, v in pts:
            i = bisect.bisect_right(dd, d) - 1
            if i >= 0:
                norm.append((d, v / dv[i][1]))
        pts = norm
    out_d, out_v = [], []
    for i in range(55, len(pts)):
        cur = sum(pts[j][1] for j in range(i - 3, i + 1))
        prev = sum(pts[j][1] for j in range(i - 55, i - 51))
        out_d.append(pts[i][0])
        out_v.append(round(100 * (cur / prev - 1), 3))
    return weekly_to_month(out_d, out_v)


def paur(unemploy: dict[YM, float], clf: dict[YM, float],
         lfpr_prime: dict[YM, float], pop: dict[YM, float]) -> dict[YM, float]:
    """Participation-adjusted unemployment rate: add back as unemployed the
    prime-age participation shortfall vs its 24-month high, times the 25-54
    population (LNU00000060). An UPPER bound — every shortfall counts as
    hidden unemployment."""
    out = {}
    for k in _months(unemploy):
        if k not in clf or k not in lfpr_prime or k not in pop:
            continue
        hist = [lfpr_prime[j] for j in (ym_add(k, -i) for i in range(0, 24)) if j in lfpr_prime]
        gap = max(0.0, max(hist) - lfpr_prime[k]) / 100 * pop[k]
        out[k] = 100 * (unemploy[k] + gap) / (clf[k] + gap)
    return out


def remove_january_steps(x: dict[YM, float], years: tuple[int, ...]) -> dict[YM, float]:
    """v1 A7 sensitivity: remove the EXCESS Dec->Jan step (Jan-Dec minus the
    median Jan-Dec of all other years) in the listed years by shifting every
    pre-January value, so level breaks from population controls vanish."""
    steps = {y: x[(y, 1)] - x[(y - 1, 12)] for y in range(1949, 2100)
             if (y, 1) in x and (y - 1, 12) in x}
    normal = sorted(v for y, v in steps.items() if y not in years)
    med = normal[len(normal) // 2] if normal else 0.0
    out = dict(x)
    for y in sorted(years):
        if y not in steps:
            continue
        excess = steps[y] - med
        for k in list(out):
            if k < (y, 1):
                out[k] += excess
    return out


POP_CONTROL_YEARS = (2000, 2003, 2004, 2008, 2011, 2022, 2025, 2026)


def rule_values(series: dict[str, tuple[list[date], list[float | None]]], *,
                sahm_from: str = "series", a3_normalize: bool = False,
                pop_control_adjust: bool = False) -> dict[str, dict[YM, float]]:
    """All six rule VALUES (not yet thresholded). `series` keys: iursa, ccnsa,
    covemp (optional), job_losers, clf, epop_prime, lfpr_prime, pop_prime,
    unemploy, sahm and/or unrate.
    sahm_from: "series" = SAHMREALTIME (live panel); "unrate" = recomputed from
    current-vintage UNRATE (the study — one vintage for every rule, v1 A5)."""
    weekly = ("iursa", "ccnsa", "covemp")
    g = {k: monthly(*v) for k, v in series.items() if k not in weekly}
    if pop_control_adjust:
        for k in ("epop_prime", "lfpr_prime"):
            if k in g:
                g[k] = remove_january_steps(g[k], POP_CONTROL_YEARS)
    jl = {k: 100 * g["job_losers"][k] / g["clf"][k]
          for k in g.get("job_losers", {}) if k in g.get("clf", {})}
    pa = paur(g.get("unemploy", {}), g.get("clf", {}), g.get("lfpr_prime", {}),
              g.get("pop_prime", {}))
    if sahm_from == "unrate":
        from .labor import _sahm_from_unrate
        ud, uv = series["unrate"]
        sd, sv = _sahm_from_unrate(ud, uv)
        c1 = {ym(d): round(v, 3) for d, v in zip(sd, sv) if v is not None}
    else:
        c1 = {k: round(v, 3) for k, v in g.get("sahm", {}).items()}
    return {
        "A1": sos(*series["iursa"]) if "iursa" in series else {},
        "A2": rise_over_prior_min(jl),
        "A3": (claims_yoy(*series["ccnsa"],
                          denom=series.get("covemp") if a3_normalize else None)
               if "ccnsa" in series else {}),
        "B1": drawdown_from_prior_max(g.get("epop_prime", {})),
        "B2": rise_over_prior_min(pa),
        "C1": c1,
        "_paur": pa,
    }


def lit(values: dict[str, dict[YM, float]],
        thresholds: dict[str, float] | None = None) -> dict[str, dict[YM, bool]]:
    out = {}
    for rid, spec in RULES.items():
        t = (thresholds or {}).get(rid, spec["threshold"])
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


# ── "Real slack" strip: display only, no alerts ─────────────────────────────
# Answers "is 4.1% too good?" (the Board answers "is a layoff-driven downturn
# confirmed?" — the two can disagree). Corrections from the spec review (S5/S6):
# duration items get percentiles from 1994 only (the CPS redesign raised
# measured durations); the long-term unemployment RATE sits beside the share;
# PAUR is labelled an upper bound with its gap in persons; the Jan-2026 NEI
# spike is flagged; nativity series (not seasonally adjusted) show the
# 12-month change only.
STRIP_KEYS = ("unemploy", "clf", "lfpr_prime", "pop_prime", "u6", "nilfwjn", "nei",
              "epop_prime", "ue_flow", "jolts_hires", "jolts_quits", "jolts_layoffs",
              "lt_share", "lt_level", "med_dur", "hours", "fb_lfpr", "nb_lfpr")


TREND_DEAD_BAND = 0.05     # |12-month change| below this reads "flat", not worse/better


def _pct_rank(hist: list[float], v: float) -> float | None:
    return round(100 * sum(1 for h in hist if h <= v) / len(hist)) if hist else None


def _item(key: str, label: str, s: dict[YM, float], *, unit: str, worse: str,
          pct_from: YM | None = None, note="", yoy_only: bool = False,
          decimals: int = 2) -> dict | None:
    if not s:
        return None
    last = max(s)
    v = s[last]
    prev = s.get(ym_add(last, -12))
    hist = [x for k, x in s.items() if pct_from is None or k >= pct_from]
    chg = round(v - prev, decimals) if prev is not None else None
    if chg is None:
        trend = None
    elif abs(chg) < TREND_DEAD_BAND:
        trend = "flat"
    else:
        trend = "worse" if (chg > 0) == (worse == "up") else "better"
    if callable(note):
        note = note(last)
    return {"key": key, "label": label, "month": f"{last[0]}-{last[1]:02d}",
            "value": None if yoy_only else round(v, decimals),
            "chg_12m": chg, "trend": trend,
            "percentile": None if yoy_only else _pct_rank(hist, v),
            "pct_from": f"{pct_from[0]}" if pct_from else None,
            "unit": unit, "worse": worse, "note": note}


def _spans(last: YM, k: YM) -> bool:
    """True while month k falls inside the 12-month change ending at `last`."""
    return 0 <= ym_diff(last, k) < 12


def strip(series: dict[str, tuple[list[date], list[float | None]]]) -> list[dict]:
    g = {k: monthly(*v) for k, v in series.items() if v and v[0]}
    un, lf = g.get("unemploy", {}), g.get("clf", {})
    u3 = {k: 100 * un[k] / lf[k] for k in un if k in lf}
    pa = paur(un, lf, g.get("lfpr_prime", {}), g.get("pop_prime", {}))
    gap_persons = {}
    for k in pa:
        hist = [g["lfpr_prime"][j] for j in (ym_add(k, -i) for i in range(24))
                if j in g["lfpr_prime"]]
        gap_persons[k] = max(0.0, max(hist) - g["lfpr_prime"][k]) / 100 * g["pop_prime"][k]
    wj = g.get("nilfwjn", {})
    u3wj = {k: 100 * (un[k] + wj[k]) / (lf[k] + wj[k]) for k in un if k in lf and k in wj}
    ue = g.get("ue_flow", {})
    ue_rate = {k: 100 * ue[k] / un[ym_add(k, -1)] for k in ue if ym_add(k, -1) in un}
    lt = g.get("lt_level", {})
    lt_rate = {k: 100 * lt[k] / lf[k] for k in lt if k in lf}
    y94 = (1994, 1)
    last_gap = gap_persons[max(gap_persons)] if gap_persons else None
    nei = g.get("nei", {})
    items = [
        _item("u3", "Unemployment rate (U-3, unrounded)", u3, unit="%", worse="up"),
        _item("paur", "Participation-adjusted unemployment (upper bound)", pa, unit="%",
              worse="up", note=(f"adds back {last_gap / 1000:.2f}M prime-age-equivalent "
                                "people below the 24-month participation high, counting "
                                "population-control and immigration effects as hidden "
                                "unemployment" if last_gap is not None else "")),
        _item("u6", "U-6 (incl. part-time for economic reasons, marginally attached)",
              g.get("u6", {}), unit="%", worse="up", decimals=1),
        _item("u3_wantjob", "Unemployed + want a job (not in labor force)", u3wj,
              unit="%", worse="up"),
        _item("nei", "Non-Employment Index (Richmond Fed)", nei, unit="%", worse="up",
              note=("Jan-2026 is a population-control spike (+0.34 then −0.35); its "
                    "12-month change is suppressed in Jan-2027" if (2026, 1) in nei else "")),
        _item("epop_prime", "Prime-age (25-54) employment rate", g.get("epop_prime", {}),
              unit="%", worse="down", decimals=1),
        _item("job_finding", "Job-finding rate (unemployed → employed, monthly)",
              ma3(ue_rate), unit="%", worse="down",
              note="3-month average; flows missing Oct-Nov 2025"),
        _item("hires", "JOLTS hires rate", g.get("jolts_hires", {}), unit="%",
              worse="down", decimals=1),
        _item("quits", "JOLTS quits rate", g.get("jolts_quits", {}), unit="%",
              worse="down", decimals=1),
        _item("layoffs", "JOLTS layoffs rate", g.get("jolts_layoffs", {}), unit="%",
              worse="up", decimals=1),
        _item("lt_share", "Long-term unemployed (27+ wks), share", g.get("lt_share", {}),
              unit="%", worse="up", pct_from=y94, decimals=1,
              note="a share rises mechanically when few new layoffs join the pool"),
        _item("lt_rate", "Long-term unemployed (27+ wks), % of labor force", lt_rate,
              unit="%", worse="up", pct_from=y94),
        _item("med_dur", "Median weeks unemployed", g.get("med_dur", {}), unit="wks",
              worse="up", pct_from=y94, decimals=1),
        _item("hours", "Average weekly hours (private)", g.get("hours", {}), unit="hrs",
              worse="down", decimals=1),
        _item("fb_lfpr", "Foreign-born participation (not seasonally adj.)",
              g.get("fb_lfpr", {}), unit="pp", worse="down", yoy_only=True, decimals=1,
              note=lambda last: ("includes the June-2026 drop (−0.9, NSA; native-born +0.3) "
                                 "— immigration/survey-response effects, not established "
                                 "as demand" if _spans(last, (2026, 6)) else "")),
        _item("nb_lfpr", "Native-born participation (not seasonally adj.)",
              g.get("nb_lfpr", {}), unit="pp", worse="down", yoy_only=True, decimals=1,
              note=lambda last: ("ages 16+ (aging lowers it every year); this change spans "
                                 "the Jan-2026 population-control step (Dec→Jan −0.5 vs a "
                                 "typical −0.1)" if _spans(last, (2026, 1))
                                 else "ages 16+ (aging lowers it every year)")),
    ]
    return [x for x in items if x]


_SHORT = {"u3": "U-3", "paur": "participation-adjusted", "u6": "U-6",
          "u3_wantjob": "unemployed + want a job", "nei": "non-employment index",
          "epop_prime": "prime-age employment rate", "job_finding": "job-finding rate",
          "hires": "hires", "quits": "quits", "layoffs": "layoffs",
          "lt_share": "long-term share", "lt_rate": "long-term unemployment rate",
          "med_dur": "median duration", "hours": "weekly hours",
          "fb_lfpr": "foreign-born participation", "nb_lfpr": "native-born participation"}


def strip_verdict(items: list[dict]) -> str | None:
    """One computed line answering "is the headline rate too good?" from the
    strip itself (no judgment beyond the dead band)."""
    by = {x["key"]: x for x in items}
    u3, pa = by.get("u3"), by.get("paur")
    if not u3 or not pa or u3["value"] is None or pa["value"] is None:
        return None
    gap = pa["value"] - u3["value"]
    out = (f"U-3 {u3['value']:.2f}% vs participation-adjusted {pa['value']:.2f}% (an upper "
           f"bound): at most {gap:.2f}pp of slack sits outside the headline")
    if pa["percentile"] is not None:
        out += f", and that adjusted rate is at the {pa['percentile']:.0f}th percentile of its history"
    out += "."
    if u3["chg_12m"] is not None and pa["chg_12m"] is not None:
        out += (f" Over 12 months: U-3 {u3['chg_12m']:+.2f}pp, adjusted "
                f"{pa['chg_12m']:+.2f}pp.")
    rest = [x for x in items if x["key"] not in ("u3", "paur")]
    worse = [_SHORT.get(x["key"], x["key"]) for x in rest if x.get("trend") == "worse"]
    better = [_SHORT.get(x["key"], x["key"]) for x in rest if x.get("trend") == "better"]
    out += f" Worse than a year ago: {', '.join(worse) or 'none'}."
    out += f" Better: {', '.join(better) or 'none'}."
    return out
