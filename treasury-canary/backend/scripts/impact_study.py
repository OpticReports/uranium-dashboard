"""Impact study — what each recession TYPE did to markets, on what clock.

Run: python -m scripts.impact_study   (from backend/)
Emits frontend/src/lib/severityImpact.ts (generated) + console summary.

Per NBER recession: equity peak->trough drawdown (pre-onset peak within 12m),
months-to-trough, months-to-recover; housing (FHFA 1975+, nominal AND CPI-real,
72-month trough window — housing lags); 10y Treasury 12m/24m total returns from
onset; unemployment rise. Recessions are hand-classified by their balance-sheet
TYPE (classification documented below — this is the key to the map: severity
does not hit markets uniformly; composition decides which market bleeds).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.backtest import add_months, fred_csv, month_key, months_between  # noqa: E402

# type classification (documented judgment, cited in the tab):
# keys = first USREC==1 month (one month after the NBER peak month)
TYPE_OF: dict[str, str] = {
    "1957-09": "inflation_rates", "1960-05": "inflation_rates",
    "1970-01": "inflation_rates", "1973-12": "inflation_rates",
    "1980-02": "inflation_rates", "1981-08": "inflation_rates",
    "1990-08": "household_leverage",   # CRE/S&L — credit-bust family
    "2001-04": "valuation_corporate",
    "2008-01": "household_leverage",
    "2020-03": "exogenous",
}
TYPE_LABEL = {
    "household_leverage": "Household / credit-leverage bust",
    "valuation_corporate": "Valuation / corporate unwind",
    "inflation_rates": "Inflation / rates-driven",
    "exogenous": "Exogenous shock",
}


def mmap(sid: str) -> dict[tuple[int, int], float]:
    d, v = fred_csv(sid)
    return {month_key(dd): vv for dd, vv in zip(d, v) if vv is not None}


eq = mmap("SPASTT01USM661N")
hpi = mmap("USSTHPI")            # quarterly (first month of quarter)
cpi = mmap("CPIAUCSL")
un = mmap("UNRATE")
g10 = mmap("GS10")
tb3 = mmap("TB3MS")
usrec_d, usrec_v = fred_csv("USREC")
urec = {month_key(d): (v or 0) for d, v in zip(usrec_d, usrec_v)}

onsets: list[tuple[int, int]] = []
prev = 1.0
for d in sorted({date(k[0], k[1], 1) for k in urec}):
    k = month_key(d)
    if urec[k] == 1.0 and prev != 1.0:
        onsets.append(k)
    prev = urec[k]

# 10y TR index
tr_idx: dict[tuple[int, int], float] = {}
ms = sorted(set(g10) & set(tb3))
lvl = 100.0
for i, m in enumerate(ms):
    if i:
        y0 = g10[ms[i - 1]] / 100.0
        dur = (1 - (1 + y0 / 2) ** -20) / (y0 / 2)
        dy = g10[m] / 100.0 - y0
        lvl *= 1 + (y0 / 12 - dur * dy + 0.5 * dur * dur * dy * dy)
    tr_idx[m] = lvl

hpi_real = {k: hpi[k] / cpi[k] for k in hpi if k in cpi}


def series_at(series: dict, ym) -> float | None:
    return series.get(ym)


def drawdown(series: dict, onset, pre=12, window=36, recover_cap=120):
    """(dd%, months_to_trough, months_to_recover) around onset."""
    pre_pts = [(k, series[k]) for k in (add_months(onset, -i) for i in range(pre + 1))
               if k in series]
    if not pre_pts:
        return None, None, None
    peak = max(v for _, v in pre_pts)
    post = [(i, series.get(add_months(onset, i))) for i in range(window + 1)]
    post = [(i, v) for i, v in post if v is not None]
    if not post:
        return None, None, None
    ti, tv = min(post, key=lambda p: p[1])
    dd = round((tv / peak - 1) * 100, 1)
    rec = None
    for i in range(ti, recover_cap + 1):
        v = series.get(add_months(onset, i))
        if v is not None and v >= peak:
            rec = i
            break
    return dd, ti, rec


def tr_fwd(onset, h):
    a, b = tr_idx.get(onset), tr_idx.get(add_months(onset, h))
    return round((b / a - 1) * 100, 1) if a and b else None


def unemp_rise(onset, window=36):
    u0 = un.get(onset)
    if u0 is None:
        return None
    vals = [un.get(add_months(onset, i)) for i in range(window + 1)]
    vals = [v for v in vals if v is not None]
    return round(max(vals) - u0, 1) if vals else None


def path(series: dict, onset, lo, hi, step=1):
    base = series.get(onset)
    if not base:
        return []
    out = []
    for i in range(lo, hi + 1, step):
        v = series.get(add_months(onset, i))
        if v is not None:
            out.append({"m": i, "v": round(v / base * 100, 1)})
    return out


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


types: dict[str, dict] = {t: {"label": lbl, "episodes": [], "paths": {}}
                          for t, lbl in TYPE_LABEL.items()}
for onset in onsets:
    key = f"{onset[0]}-{onset[1]:02d}"
    t = TYPE_OF.get(key)
    if t is None:
        continue
    eq_dd, eq_tt, eq_rec = drawdown(eq, onset)
    hn_dd, hn_tt, hn_rec = drawdown(hpi, onset, pre=4, window=72, recover_cap=180)
    hr_dd, hr_tt, hr_rec = drawdown(hpi_real, onset, pre=4, window=72, recover_cap=180)
    types[t]["episodes"].append({
        "onset": key,
        "equity_dd": eq_dd, "equity_tt_mo": eq_tt, "equity_rec_mo": eq_rec,
        "housing_nom_dd": hn_dd, "housing_nom_tt_mo": hn_tt, "housing_nom_rec_mo": hn_rec,
        "housing_real_dd": hr_dd, "housing_real_tt_mo": hr_tt,
        "tsy_12m": tr_fwd(onset, 12), "tsy_24m": tr_fwd(onset, 24),
        "unemp_rise_pp": unemp_rise(onset),
        "eq_path": path(eq, onset, -12, 48),
        "hpi_path": path(hpi, onset, -12, 60, step=3),
    })

for t, blob in types.items():
    eps = blob["episodes"]
    blob["aggregate"] = {
        k: {"median": median([e[k] for e in eps]),
            "values": [e[k] for e in eps]}
        for k in ("equity_dd", "equity_tt_mo", "equity_rec_mo", "housing_nom_dd",
                  "housing_nom_tt_mo", "housing_real_dd", "tsy_12m", "tsy_24m",
                  "unemp_rise_pp")
    }
    # median path across episodes (per month offset)
    for pk, months_rng in (("eq_path", range(-12, 49)), ("hpi_path", range(-12, 61, 3))):
        agg = []
        for m in months_rng:
            vals = [next((p["v"] for p in e[pk] if p["m"] == m), None) for e in eps]
            mv = median(vals)
            if mv is not None:
                agg.append({"m": m, "v": mv})
        blob["paths"][pk] = agg
    for e in eps:
        del e["eq_path"], e["hpi_path"]     # keep payload lean; paths live per type

out = {"generated": date.today().isoformat(), "types": types,
       "meta": {"equities": "OECD US share-price index, PRICE-ONLY, 1957+",
                "housing": "FHFA all-transactions HPI 1975+ (nominal & CPI-real); "
                           "pre-1975 recessions have no housing row",
                "treasury": "10y total-return approximation from GS10",
                "classification": TYPE_OF}}

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ts_path = os.path.join(root, "frontend", "src", "lib", "severityImpact.ts")
with open(ts_path, "w") as f:
    f.write("// GENERATED by backend/scripts/impact_study.py — do not edit by hand.\n")
    f.write("export const IMPACT_DATA = ")
    f.write(json.dumps(out, indent=1))
    f.write(" as const;\n")
print(f"Wrote {ts_path}\n")

for t, blob in types.items():
    a = blob["aggregate"]
    print(f"== {blob['label']} ({len(blob['episodes'])} eps: "
          f"{[e['onset'] for e in blob['episodes']]})")
    print(f"   equity dd {a['equity_dd']['median']}% (trough {a['equity_tt_mo']['median']}mo, "
          f"recover {a['equity_rec_mo']['median']}mo) | housing nom {a['housing_nom_dd']['median']}% "
          f"real {a['housing_real_dd']['median']}% | 10y TR 12m {a['tsy_12m']['median']}% "
          f"24m {a['tsy_24m']['median']}% | U +{a['unemp_rise_pp']['median']}pp")
