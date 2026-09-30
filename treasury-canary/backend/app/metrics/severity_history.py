"""Severity index over time (studies/severity-history.md, spec v0).

Each point re-runs the LIVE build_severity, unchanged, on the bundle truncated
to what had been PUBLISHED by that month-end (observation stamp + publication
lag <= t), using only inputs whose as-of history already spans >= 10 years.
That is what the dashboard would have said then, on today's data vintage.
Ranks are point-in-time (expanding from 1976), not today's yardstick.
"""
from __future__ import annotations

from datetime import date, timedelta

from .severity import build_severity

# publication lag (days) from FRED's observation date stamp
_WEEKLY, _MONTHLY, _QUARTERLY = 7, 60, 180
LAGS: dict[str, int] = {
    "effr": _WEEKLY, "hy_oas": _WEEKLY, "mtg30": _WEEKLY,
    "core_pce": _MONTHLY, "saving_rate": _MONTHLY, "inv_sales": _MONTHLY,
    "months_supply": _MONTHLY, "margin_debit": _MONTHLY,
    "gdp": _QUARTERLY, "hh_debt_gdp": _QUARTERLY, "priv_credit": _QUARTERLY,
    "corp_debt": _QUARTERLY, "margin_debt": _QUARTERLY, "bottom50_nw": _QUARTERLY,
    "dsr": _QUARTERLY, "equity_liab": _QUARTERLY, "med_house_px": _QUARTERLY,
    "delinq_cc": _QUARTERLY, "delinq_cre": _QUARTERLY, "fed_debt_gdp": _QUARTERLY,
    "vac_rental": _QUARTERLY, "vac_owner": _QUARTERLY, "capex_info": _QUARTERLY,
    "capex_soft": _QUARTERLY,
    "deficit_gdp": 300,       # fiscal year stamped Jan 1, published ~October
    "med_income": 630,        # stamped Jan 1, Census publishes September next year
}
MIN_HISTORY_DAYS = 3652       # an input enters only with >= 10 years of as-of history
GRID_FROM = date(1986, 1, 1)
LIVE_SHARE_TO_DRAW = 0.5      # the chart does not draw points with fewer live inputs

# NBER business-cycle peaks since the grid starts (the analog anchors)
PEAKS = [(date(1990, 7, 1), date(1991, 3, 1), False), (date(2001, 3, 1), date(2001, 11, 1), False),
         (date(2007, 12, 1), date(2009, 6, 1), False), (date(2020, 2, 1), date(2020, 4, 1), True)]


def month_ends(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while True:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        t = nxt - timedelta(days=1)
        if t > end:
            return out
        out.append(t)
        y, m = nxt.year, nxt.month


def as_of(bundle: dict, t: date) -> dict:
    """The bundle as published by t: each series truncated to observations
    whose stamp + lag <= t, and dropped unless that history spans >= 10y."""
    out = {}
    for key, lag in LAGS.items():
        d, v = bundle.get(key, ([], []))
        cut = t - timedelta(days=lag)
        pts = [(dd, vv) for dd, vv in zip(d, v) if dd <= cut and vv is not None]
        if pts and (pts[-1][0] - pts[0][0]).days >= MIN_HISTORY_DAYS:
            out[key] = ([p[0] for p in pts], [p[1] for p in pts])
        else:
            out[key] = ([], [])
    return out


def _n_components(result: dict) -> tuple[int, int]:
    comps = [c for b in result["blocks"] for c in b["components"]]
    return sum(1 for c in comps if c["score"] is not None), len(comps)


def severity_history(bundle: dict, *, end: date | None = None) -> list[dict]:
    """Monthly point-in-time readings with block scores and input coverage."""
    last_obs = max((d[-1] for d, _ in (bundle.get(k, ([], [])) for k in LAGS) if d),
                   default=None)
    end = end or last_obs or date.today()
    rows = []
    for t in month_ends(GRID_FROM, end):
        r = build_severity(as_of(bundle, t))
        live, total = _n_components(r)
        rows.append({
            "month": f"{t.year}-{t.month:02d}", "score": r["severity_score"],
            "class": r["severity_class"], "live": live, "total": total,
            "drawn": r["severity_score"] is not None and live >= LIVE_SHARE_TO_DRAW * total,
            "blocks": {b["id"]: b["score"] for b in r["blocks"]},
        })
    return rows


# What followed each recession start (historical facts, frozen from FRED in
# studies/severity-history.md: NBER length, max unemployment within 30 months
# of the peak minus the peak-month rate, peak-to-trough real GDP (GDPC1)).
RECESSION_OUTCOMES = {
    "1990-07": {"months": 8, "unemployment_rise_pp": 2.3, "real_gdp_pct": -1.4, "exogenous": False},
    "2001-03": {"months": 8, "unemployment_rise_pp": 2.0, "real_gdp_pct": -0.4, "exogenous": False},
    "2007-12": {"months": 18, "unemployment_rise_pp": 5.0, "real_gdp_pct": -3.8, "exogenous": False},
    "2020-02": {"months": 2, "unemployment_rise_pp": 11.3, "real_gdp_pct": -9.1, "exogenous": True},
}
ANALOG_BAND = 5.0          # nearest readings: within +/- 5 points of today
ANALOG_MIN_LIVE = 0.75     # ... using >= 75% of the inputs
ANALOG_HORIZON = 24        # months of what-followed


def _ym(s: str) -> int:
    y, m = s.split("-")
    return int(y) * 12 + int(m) - 1


def _ym_str(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


def history_payload(bundle: dict, *, end: date | None = None) -> dict:
    rows = severity_history(bundle, end=end)
    live = build_severity(bundle)
    today = live["severity_score"]
    by = {r["month"]: r for r in rows}
    full = [r for r in rows if r["drawn"] and r["live"] >= ANALOG_MIN_LIVE * r["total"]]
    pctile = (round(100 * sum(1 for r in full if r["score"] <= today) / len(full))
              if full and today is not None else None)
    peaks = [f"{p.year}-{p.month:02d}" for p, _, _ in PEAKS]

    starts = []
    for (p, tr, exo), key in zip(PEAKS, peaks):
        r = by.get(_ym_str(_ym(key) - 1))
        starts.append({"peak": key, "trough": f"{tr.year}-{tr.month:02d}",
                       "reading": r["score"] if r else None,
                       "class": r["class"] if r else None,
                       "live": r["live"] if r else None, "total": r["total"] if r else None,
                       **RECESSION_OUTCOMES.get(key, {})})

    ud, uv = bundle.get("unrate", ([], []))
    un = {f"{d.year}-{d.month:02d}": v for d, v in zip(ud, uv) if v is not None}
    last = _ym(rows[-1]["month"]) if rows else 0
    episodes: list[list[dict]] = []
    if today is not None:
        for r in full:
            if abs(r["score"] - today) > ANALOG_BAND or _ym(r["month"]) > last - ANALOG_HORIZON:
                continue
            if episodes and _ym(r["month"]) - _ym(episodes[-1][-1]["month"]) < 6:
                episodes[-1].append(r)
            else:
                episodes.append([r])
    nearest = []
    for ep in episodes:
        s = _ym(ep[0]["month"])
        rec = next((k for k in peaks if 0 <= _ym(k) - s <= ANALOG_HORIZON), None)
        in_rec = any(_ym(k) <= s <= _ym(f"{tr.year}-{tr.month:02d}")
                     for k, (_, tr, _) in zip(peaks, PEAKS))
        u0, u1 = un.get(ep[0]["month"]), un.get(_ym_str(s + ANALOG_HORIZON))
        nearest.append({
            "from": ep[0]["month"], "to": ep[-1]["month"], "months": len(ep),
            "mean_reading": round(sum(x["score"] for x in ep) / len(ep), 1),
            "already_in_recession": in_rec,
            "recession_within_24m": rec,
            "unemployment_chg_24m": round(u1 - u0, 1) if u0 is not None and u1 is not None else None,
        })
    return {
        "series": [{k: r[k] for k in ("month", "score", "class", "live", "total", "drawn")}
                   for r in rows],
        "blocks": [{"month": r["month"], **r["blocks"]} for r in rows],
        "today": {"score": today, "class": live["severity_class"]},
        "today_pctile": pctile,
        "pctile_from": full[0]["month"] if full else None,
        "share_severe": (round(100 * sum(1 for r in rows if r["drawn"] and r["score"] > 60)
                               / max(1, sum(1 for r in rows if r["drawn"]))) if rows else None),
        "bands": {"mild_below": 35, "severe_above": 60},
        "recessions": [{"start": k, "end": f"{tr.year}-{tr.month:02d}", "exogenous": exo}
                       for k, (_, tr, exo) in zip(peaks, PEAKS)],
        "analogs": {"recession_starts": starts, "nearest": nearest, "band": ANALOG_BAND},
        "method": ("Each point re-runs today's index code on the data published by that "
                   "month (current vintage; ranks use only history up to then, from 1976). "
                   "Inputs enter once they have 10 years of history, so the early line uses "
                   "fewer inputs; it is not drawn below half. Last point is today's live "
                   "reading."),
    }
