"""GET /gdp-watch: real GDP growth for the 20 largest economies with current quarterly data, with a simple,
backtested 4-quarter projection (studies/gdp-watch.md, studies/gdp_watch/backtest_v1.py).

Series: OECD quarterly real GDP growth, % on the same quarter a year earlier (seasonally adjusted). Per capita:
that growth deflated by population growth over the same four quarters, from the IMF's annual population
(log-linear between mid-years, IMF projections ahead).

Projection (the study's rule, frozen; parity with the study's code is a gate test): each coming quarter's
quarter-on-quarter growth decays toward the median of the last 40 (non-pandemic) quarters at the AR(1) rate
estimated on them, and the published YoY is rolled forward one quarter at a time, so the quarters already in hand
count. The bands are the rule's own backtest errors (10th-90th and 25th-75th percentiles by horizon, pandemic
quarters excluded), on today's revised data, not real-time vintages.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import os
import statistics
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKTEST_FILE = os.path.join(HERE, "sources", "gdp_backtest_v1.json")
WINDOW, MIN_WINDOW, MIN_PAIRS, PHI_MAX = 40, 20, 12, 0.8          # frozen with the study (backtest_v1.py)
PANDEMIC = {f"{y}-Q{q}" for y in (2020, 2021) for q in (1, 2, 3, 4)}
H = (1, 2, 3, 4)
DEFAULT_N = 6
NAMES = {"USA": "United States", "CHN": "China", "DEU": "Germany", "JPN": "Japan", "GBR": "United Kingdom",
         "IND": "India", "FRA": "France", "ITA": "Italy", "CAN": "Canada", "BRA": "Brazil", "ESP": "Spain",
         "KOR": "South Korea", "AUS": "Australia", "MEX": "Mexico", "TUR": "Turkey", "IDN": "Indonesia",
         "NLD": "Netherlands", "SAU": "Saudi Arabia", "CHE": "Switzerland", "POL": "Poland",
         "G20": "G20 (OECD aggregate)", "OECD": "OECD total"}
_RANK = {"ok": 0, "stale": 1, "partial": 2, "snapshot": 3, "error": 4}


def _load(path: str) -> tuple[dict, str | None]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("GDP backtest record unreadable: %s", exc)
        return {}, f"{type(exc).__name__}: {exc}"


BACKTEST, BACKTEST_ERROR = _load(BACKTEST_FILE)


def qi(s: str) -> int:
    return int(s[:4]) * 4 + int(s[-1]) - 1


def qs(i: int) -> str:
    return f"{i // 4}-Q{i % 4 + 1}"


def _r(x, k=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, k)


def _f(x: float, d: int = 1, sign: bool = False) -> str:
    """half-up text for a recorded number (2.25 -> 2.3, 1.285 -> 1.29), never binary half-even."""
    q = Decimal(str(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{'+' if sign and q > 0 else ''}{q}"


FISCAL = {"IND": "fiscal years (April-March): 2026 means FY2026/27"}
def pop_note(code: str, pop: dict) -> str | None:
    """the known population-series breaks that move per-person growth, checked against and worded from the series
    actually served (a later IMF vintage that smooths a break drops its note)."""
    g = {y: 100 * (pop[str(y)] / pop[str(y - 1)] - 1) for y in range(2001, 2031)
         if isinstance(pop.get(str(y)), (int, float)) and isinstance(pop.get(str(y - 1)), (int, float)) and pop[str(y - 1)]}
    if code == "SAU":
        w = [g[y] for y in range(2018, 2023) if y in g]
        if len(w) == 5 and max(w) - min(w) > 4:
            return (f"Saudi Arabia: the IMF population series swings by several points a year from 2018 to 2022 "
                    f"({_f(min(w), sign=True)}% to {_f(max(w), sign=True)}%), so per-person growth in those years moves "
                    "with population as much as with output.")
    if code == "POL" and all(y in g for y in (2020, 2021, 2022)):
        if g[2021] < -1.5 and abs(g[2020]) < 0.5 and abs(g[2022]) < 0.5:
            return (f"Poland: the IMF population series drops {_f(-g[2021])}% in 2021 (a one-year level break; the years "
                    "either side move by under 0.5%), so the per-person rate around 2021 jumps with population, not output.")
    return None


# ---------------------------------------------------------------------------- the frozen rule (== study)
def trend_phi(q: dict, t: int) -> tuple[float | None, float]:
    win = [qs(i) for i in range(t - WINDOW + 1, t + 1)]
    vals = [q[s] for s in win if s in q and s not in PANDEMIC]
    if len(vals) < MIN_WINDOW:
        return None, 0.0
    mu = statistics.median(vals)
    pairs = [(q[qs(qi(s) - 1)] - mu, q[s] - mu) for s in win
             if s in q and qs(qi(s) - 1) in q and s not in PANDEMIC and qs(qi(s) - 1) not in PANDEMIC]
    sxx = sum(x * x for x, _ in pairs)
    phi = sum(x * y for x, y in pairs) / sxx if len(pairs) >= MIN_PAIRS and sxx > 0 else 0.0
    return mu, min(PHI_MAX, max(0.0, phi))


def forecast_path(y: dict, q: dict, t: int) -> tuple[list[float] | None, float | None, float]:
    """(YoY path for t+1..t+4, mu, phi) from data <= t; the study's method 'A'."""
    if qs(t) not in y or any(qs(t - k) not in q for k in range(4)):
        return None, None, 0.0
    mu, phi = trend_phi(q, t)
    if mu is None:
        return None, None, 0.0
    path, level = [], 1 + y[qs(t)] / 100
    for h in H:
        qhat = mu + phi ** h * (q[qs(t)] - mu)
        level = level * (1 + qhat / 100) / (1 + q[qs(t + h - 4)] / 100)
        path.append(100 * (level - 1))
    return path, mu, phi


# ---------------------------------------------------------------------------- per capita
def population_quarterly(annual: dict[str, float], first: str, last: str) -> dict[str, float]:
    """Quarterly population, log-linear between annual values placed at mid-year; the edge segments extend."""
    pts = sorted((int(y) + 0.5, math.log(v)) for y, v in annual.items() if isinstance(v, (int, float)) and v > 0)
    out: dict[str, float] = {}
    if len(pts) < 2:
        return out
    for i in range(qi(first), qi(last) + 1):
        x = i // 4 + (i % 4 + 0.5) / 4
        j = max(0, min(len(pts) - 2, next((k for k in range(len(pts) - 1) if pts[k + 1][0] >= x), len(pts) - 2)))
        (x0, y0), (x1, y1) = pts[j], pts[j + 1]
        out[qs(i)] = math.exp(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return out


def per_capita(g: float | None, pop: dict, t: str) -> float | None:
    """GDP growth deflated by population growth over the same four quarters."""
    p1, p0 = pop.get(t), pop.get(qs(qi(t) - 4))
    if g is None or not p1 or not p0:
        return None
    return 100 * ((1 + g / 100) * p0 / p1 - 1)


# ---------------------------------------------------------------------------- the payload
def _band(code: str) -> tuple[dict, str]:
    own = ((BACKTEST.get("bands") or {}).get(code)) or {}
    if all(own.get(str(h)) for h in H):
        return own, "own record"
    return BACKTEST.get("bands_pooled") or {}, "pooled record (this economy's own is too short)"


def _record(code: str) -> dict | None:
    bc = ((BACKTEST.get("by_country_ex_pandemic") or {}).get(code)) or {}
    a4, n4 = ((bc.get("A") or {}).get("4") or {}).get("mae"), ((bc.get("N") or {}).get("4") or {}).get("mae")
    if a4 is None or not n4:
        return None
    rb = ((BACKTEST.get("recent_bias_h4_since_2023") or {}).get(code) or {}).get("mean_error")
    bias = (BACKTEST.get("bias_h4") or {}).get(code) or {}
    return {"mae_h1": ((bc.get("A") or {}).get("1") or {}).get("mae"), "mae_h4": a4, "naive_mae_h4": n4,
            "skill_h4_pct": _r(100 * (1 - a4 / n4), 0), "naive_better": a4 > n4, "origins": bc.get("origins"),
            "mean_miss_h4_since_2023": rb, "n_h4": bias.get("n"), "n_over_h4": bias.get("n_over"),
            "median_miss_h4": bias.get("median"),
            "band_in_sample_only": code not in (BACKTEST.get("coverage_tested") or [])}


def _shares(ngdpd: dict, year: str) -> dict[str, float]:
    w = (ngdpd.get("WEOWORLD") or {}).get(year)
    return {c: 100 * v[year] / w for c, v in ngdpd.items() if c != "WEOWORLD" and w and isinstance(v.get(year), (int, float))}


def country_block(code: str, inp: dict, share: float | None, imf_years: list[str] | None = None) -> dict:
    y, q = (inp.get("yoy") or {}).get(code) or {}, (inp.get("qoq") or {}).get(code) or {}
    quarters = sorted(y)
    blk: dict = {"code": code, "name": NAMES.get(code, code), "share_world_pct": _r(share, 1),
                 "aggregate": code not in NAMES or code in ("G20", "OECD"), "first": quarters[0] if quarters else None,
                 "last": quarters[-1] if quarters else None, "series": None, "forecast": None, "imf": None, "record": None}
    if not quarters:
        return blk
    last_i = qi(quarters[-1])
    pop_annual = (inp.get("pop") or {}).get(code) or {}
    pop = population_quarterly(pop_annual, qs(qi(quarters[0]) - 4), qs(last_i + 4)) if pop_annual else {}
    blk["series"] = {"quarters": quarters, "gdp": [_r(y[t]) for t in quarters],
                     "per_capita": [_r(per_capita(y[t], pop, t)) for t in quarters] if pop else None}
    if blk["aggregate"]:
        return blk                                         # aggregates are shown, never projected (not in the study)
    path, mu, phi = forecast_path(y, q, last_i)
    if path:
        bands, basis = _band(code)
        fq = [qs(last_i + h) for h in H]
        pc = [per_capita(v, pop, t) for v, t in zip(path, fq)] if pop else None
        def band(vals, lo, hi):
            return [[_r(v + (bands.get(str(h)) or {}).get(lo, 0)), _r(v + (bands.get(str(h)) or {}).get(hi, 0))]
                    if v is not None and bands.get(str(h)) else None for h, v in zip(H, vals)]
        blk["forecast"] = {"from": quarters[-1], "quarters": fq, "gdp": [_r(v) for v in path],
                           "per_capita": [_r(v) for v in pc] if pc else None,
                           "band80": {"gdp": band(path, "p10", "p90"), "per_capita": band(pc, "p10", "p90") if pc else None},
                           "band50": {"gdp": band(path, "p25", "p75"), "per_capita": band(pc, "p25", "p75") if pc else None},
                           "band_basis": basis, "trend_qoq_pct": _r(mu, 3), "phi": _r(phi, 2)}
        b50 = blk["forecast"]["band50"]["gdp"][3]
        v4 = blk["forecast"]["gdp"][3]
        blk["forecast"]["line_vs_band"] = (None if not b50 or v4 is None else
                                           "above" if v4 > b50[1] else "below" if v4 < b50[0] else None)
    wg = (inp.get("weo_growth") or {}).get(code) or {}
    years = imf_years or sorted({qs(last_i + h)[:4] for h in H})     # the calendar years the projection reaches
    blk["imf"] = {yr: wg.get(yr) for yr in years} if wg else None
    blk["imf_basis"] = FISCAL.get(code, "calendar years")
    blk["pop_note"] = pop_note(code, pop_annual)
    blk["record"] = _record(code)
    return blk


def summaries(countries: list[dict]) -> list[str]:
    big = [c for c in countries if c.get("default") and (c.get("series") or {}).get("gdp")]
    out = []
    if big:
        last = sorted(((c["series"]["gdp"][-1], c) for c in big if c["series"]["gdp"][-1] is not None), key=lambda x: -x[0])
        if last:
            hi, lo = last[0], last[-1]
            out.append(f"Of the {len(big)} largest economies, {hi[1]['name']} is growing fastest ({hi[0]:+.1f}% on a year earlier, "
                       f"{hi[1]['last']}) and {lo[1]['name']} slowest ({lo[0]:+.1f}%, {lo[1]['last']}).")
        share = sum(c.get("share_world_pct") or 0 for c in big)
        us_cn = sum(c.get("share_world_pct") or 0 for c in countries if c["code"] in ("USA", "CHN"))
        if share:
            out.append(f"Together they are about {share:.0f}% of world GDP at market exchange rates"
                       + (f"; the United States and China alone are about {us_cn:.0f}%." if us_cn else "."))
    pooled = (BACKTEST.get("pooled_ex_pandemic") or {}).get(BACKTEST.get("chosen") or "A") or {}
    naive = (BACKTEST.get("pooled_ex_pandemic") or {}).get("N") or {}
    if pooled.get("4") and naive.get("4") and any(c.get("forecast") for c in countries):
        out.append(f"The dashed projection is a simple rule, not a forecast service: four quarters ahead its typical miss was "
                   f"{_f(pooled['4']['mae'])} points ({_f(naive['4']['mae'])} for 'last value holds'), and it cannot see "
                   "shocks like 2020 coming.")
    for c in countries:
        side, rec = (c.get("forecast") or {}).get("line_vs_band"), c.get("record") or {}
        if side and rec.get("n_h4"):
            word = "over" if side == "above" else "under"
            out.append(f"For {c['name']} the line sits {side} its 50% band four quarters ahead: the rule {word}-projected it in "
                       f"{rec['n_over_h4'] if side == 'above' else rec['n_h4'] - rec['n_over_h4']} of {rec['n_h4']} "
                       f"backtests (median miss {_f(rec['median_miss_h4'], sign=True)} points), so past outcomes landed "
                       f"{'below' if side == 'above' else 'above'} the line, where the band sits.")
    flagged = [c["name"] for c in countries if (c.get("record") or {}).get("naive_better") and c.get("forecast")]
    if flagged:
        names = flagged[0] if len(flagged) == 1 else ", ".join(flagged[:-1]) + " and " + flagged[-1]
        out.append(f"For {names} the rule did worse than 'last value holds' in the backtest: read those projections with "
                   "that record.")
    return out


def gw_untested(tested: list[str]) -> list[str]:
    from ..sources.gdp_data import COUNTRIES
    return [c for c in COUNTRIES if tested and c not in tested]


def _span(vals: list[float]) -> str:
    lo, hi = round(100 * min(vals)), round(100 * max(vals))
    return f"{lo}%" if lo == hi else f"{lo}-{hi}%"


def honesty(max_rule_vs_trend: float | None = None) -> list[str]:
    """The caveats, with every number read from the frozen study record (and today's rule-vs-trend gap)."""
    cov = BACKTEST.get("coverage") or {}
    ex = [v["ex_pandemic"]["in_80"] for v in cov.values() if (v.get("ex_pandemic") or {}).get("in_80") is not None]
    al = [v["all"]["in_80"] for v in cov.values() if (v.get("all") or {}).get("in_80") is not None]
    rb = sorted(((v.get("mean_error"), NAMES.get(c, c)) for c, v in (BACKTEST.get("recent_bias_h4_since_2023") or {}).items()
                 if isinstance(v.get("mean_error"), (int, float))))
    worst = ", ".join(f"{n} {_f(e, sign=True)}" for e, n in rb[:3] if e < 0)
    sens = ((BACKTEST.get("sensitivity") or {}).get("windows") or {})
    w40, w20 = (sens.get("40") or {}).get("pooled_mae_A"), (sens.get("20") or {}).get("pooled_mae_A")
    out = ["The record is on today's revised data, not real-time vintages: first releases get revised, so real-time "
           "errors run larger than shown."]
    tested = BACKTEST.get("coverage_tested") or []
    per = BACKTEST.get("coverage_by_country_h4") or {}
    if ex and al:
        lo_c = min(per.items(), key=lambda kv: kv[1]["in_80"]) if per else None
        hi_c = max(per.items(), key=lambda kv: kv[1]["in_80"]) if per else None
        out.append(f"The pandemic quarters (2020-Q1 to 2021-Q4) are left out of the scores and the bands, and a shock like "
                   f"that falls outside them: fitted on origins to {BACKTEST.get('coverage_split')}, the 80% band held "
                   f"{_span(ex)} of later outcomes without the pandemic and {_span(al)} with it"
                   + (f", tested on {len(tested)} economies (per economy, four quarters ahead: {round(100 * lo_c[1]['in_80'])}% "
                      f"{NAMES.get(lo_c[0], lo_c[0])} to {round(100 * hi_c[1]['in_80'])}% {NAMES.get(hi_c[0], hi_c[0])})"
                      if lo_c and hi_c else "") + "."
                   + (f" {' and '.join(NAMES.get(c, c) for c in gw_untested(tested))} have too short a history for that "
                      "test, so their bands are in-sample only." if gw_untested(tested) else "")
                   + f" The bands drawn use every backtest miss from {BACKTEST.get('first_origin')} on, so they are "
                     "in-sample too; the split test is how far to trust them.")
    ch = BACKTEST.get("choice") or {}
    bs = ch.get("t_vs_a_bootstrap") or {}
    pooled = BACKTEST.get("pooled_ex_pandemic") or {}
    if bs and pooled.get("A") and pooled.get("T"):
        margin = statistics.fmean(pooled["T"][str(h)]["mae"] for h in H) / statistics.fmean(pooled["A"][str(h)]["mae"] for h in H) - 1
        out.append(f"The rule was chosen in-sample, on the same data: it beat 'trend only' by about {_f(100 * margin, 0)}% on "
                   f"the scores, inside the noise (95% interval {_f(100 * bs['lo'], 0, True)}% to "
                   f"{_f(100 * bs['hi'], 0, True)}%); with the pandemic quarters in, trend "
                   f"would have been chosen, and trend had the lower error in {len(ch.get('t_better_in') or [])} of 20 economies."
                   + (f" Today the two differ by at most {_f(max_rule_vs_trend, 1)} points." if max_rule_vs_trend is not None else ""))
    if worst:
        tb = (BACKTEST.get("sensitivity") or {}).get("twenty_better_in") or []
        out.append(f"The trend is a 10-year median, so it lags slowdowns: since 2023 the projection four quarters ahead ran "
                   f"too high in most economies (mean miss {worst} points)."
                   + (f" A 5-year window does better in {len(tb)} of 20 economies (China among them) but worse pooled "
                      f"({_f(w20[-1], 2)} vs {_f(w40[-1], 2)} points four quarters ahead, on the origins both windows "
                      f"share, {(BACKTEST.get('sensitivity') or {}).get('common_origins_from')} on), so the frozen "
                      "10-year rule stands."
                      if w40 and w20 else ""))
    out += ["Per person, the line is the GDP projection less IMF population growth, and its band is the GDP band moved "
            "with it: the per-person version was not backtested on its own.",
            "The IMF projections beside it are an independent reference and are not backtested here.",
            "Descriptive macro context: no trading signal or market edge was tested in this study."]
    return out


def _max_rule_vs_trend(inp: dict) -> float | None:
    """the largest gap, any economy and horizon, between today's rule path and the trend-only path (phi = 0)."""
    gaps = []
    for c, y in (inp.get("yoy") or {}).items():
        q = (inp.get("qoq") or {}).get(c) or {}
        if c in ("G20", "OECD") or not y or not q:
            continue
        t = qi(max(y, key=qi))
        path, mu, phi = forecast_path(y, q, t)
        if not path or mu is None:
            continue
        level = 1 + y[qs(t)] / 100
        for h, v in zip(H, path):
            level = level * (1 + mu / 100) / (1 + q[qs(t + h - 4)] / 100)
            gaps.append(abs(v - 100 * (level - 1)))
    return max(gaps) if gaps else None


def build_gdp_watch(inp: dict, today: str | None = None) -> dict:
    if BACKTEST_ERROR:
        raise RuntimeError(f"GDP backtest record unavailable: {BACKTEST_ERROR}")
    from ..sources.gdp_data import AGGREGATES, COUNTRIES
    today = today or datetime.now(timezone.utc).date().isoformat()
    share_year = str(int(today[:4]) - 1)
    shares = _shares(inp.get("ngdpd") or {}, share_year)
    # one set of IMF years for every row: those the projection from the latest quarter reaches (never the clock)
    latest = max((max(y, key=qi) for c, y in (inp.get("yoy") or {}).items() if c in COUNTRIES and y), default=None, key=qi)
    imf_years = sorted({qs(qi(latest) + h)[:4] for h in H}) if latest else None
    blocks = [country_block(c, inp, shares.get(c), imf_years) for c in COUNTRIES]
    ranked = sorted((b for b in blocks if b["series"]), key=lambda b: -(b["share_world_pct"] or 0))
    for b in blocks:
        b["default"] = b in ranked[:DEFAULT_N]
    aggs = [dict(country_block(a, inp, None), default=False) for a in AGGREGATES]
    st = inp.get("status") or {}
    overall = max((st.get(k) or "error" for k in ("yoy", "qoq", "pop", "ngdpd", "weo_growth")), key=lambda s: _RANK.get(s, 4))
    lastq = max((b["last"] for b in blocks if b["last"]), default=None, key=qi)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "as_of": lastq, "share_year": share_year,
        "status": {"overall": overall, "inputs": st, "filled": inp.get("filled") or None}, "src": inp.get("src"),
        "snapshot_as_of": inp.get("snapshot_as_of"),
        "countries": blocks, "aggregates": aggs,
        "method": {"name": "AR(1) toward the 10-year median quarter-on-quarter growth (slope through the origin of deviations "
                           "from that median), rolled into the year-on-year rate",
                   "window_quarters": WINDOW, "phi_max": PHI_MAX, "pandemic_excluded": sorted(PANDEMIC),
                   "study": "studies/gdp-watch.md (backtest v1, frozen " + str(BACKTEST.get("as_of")) + ")"},
        "record": {"pooled_ex_pandemic": BACKTEST.get("pooled_ex_pandemic"), "pooled_all": BACKTEST.get("pooled_all"),
                   "coverage": BACKTEST.get("coverage"), "sensitivity": BACKTEST.get("sensitivity"),
                   "first_origin": BACKTEST.get("first_origin"), "chosen": BACKTEST.get("chosen")},
        "honesty": honesty(_max_rule_vs_trend(inp)),
    }
    payload["summaries"] = summaries(blocks)
    return payload
