#!/usr/bin/env python3
"""Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere", read against this book
(results.md addendum 51). Owner's questions: what in it improves or changes our symphonies, alone or
together; whether it argues for a new symphony; other uses (liquidity as a gate); whether to build a
value engine.

Inputs (scratchpad, fetched 2026-11-01; see fetch notes in the addendum):
  vme/aqr_vme.json      AQR's updated VME factors, monthly 1972-01..2025-12 (the paper's own factors,
                        rank-weighted long-short, excess returns): VAL/MOM EVERYWHERE, ^SS (stocks),
                        ^AA (asset allocation), and per market/asset class
  vme/french.json       Ken French US Mkt-RF, SMB, HML, RF and UMD (Mom); Developed ex-US
  vme/etf_adj.json      Yahoo adjusted closes (max range) for the ETF proxies
  vme/dl/fred_*.csv     FRED TEDRATE (to 2022-01) and VIXCLS; BAMLH0A0HYM2 (HY OAS) was asked for but FRED serves
                        only 2023- of it without a key, so it drops out (the 60-month floor)
  long1997/book1997_ts_synth.json   add. 47's WEEKLY book and engine paths 1997-01..2026-10 (rebuilt
                        prices before launch; the rules were built on 2015-26: IN SAMPLE there)

Measurements (all monthly, calendar months, simple returns):
  1. factor exposure  book and each engine regressed on Mkt-RF + VAL + MOM (AQR everywhere; the
                      US HML/UMD version; the stocks/asset-allocation split), full and by era
  2. diversification  correlation of the book with VAL and MOM; the Sharpe of the book paired with
                      the VAL factor at equal risk (a bound: the factor is not buyable), then with
                      buyable long-only value ETFs (IWD since 2000, VLUE since 2013) at 0-30%
  3. liquidity        AR(2) shocks of -TED, -HY OAS, -VIX (the paper's construction): the
                      contemporaneous exposure of the book, engines, VAL and MOM; and whether this
                      month's shock or spread level says anything about the book's NEXT month (a gate)
  4. a buyable VME    long-only asset-class ETFs (SPY EFA EEM IEF TLT GLD DBC VNQ UUP): each month-end
                      long the top 3 by 12-1 momentum (MOM sleeve) and the top 3 by -5-year return
                      (VAL sleeve, the paper's non-stock value), 50/50; vs SPY, 60/40 and equal weight;
                      and its blend with the book
Writes composer/results/vme-2026-11-01.json. Usage: vme_study.py
"""
import csv
import datetime
import json
import math
import os

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "vme-2026-11-01.json")
ERAS = {"1997-2014": ("1997-01", "2014-12"), "2015-2025": ("2015-01", "2025-12"), "1997-2025": ("1997-01", "2025-12")}


# ------------------------------------------------------------------ loading
def ym(d):
    return d[:7]


def month_ends(daily):
    """{YYYY-MM: last value in the month} from {YYYY-MM-DD: value}"""
    out = {}
    for d in sorted(daily):
        out[ym(d)] = daily[d]
    return out


def to_returns(levels):
    ks = sorted(levels)
    return {ks[i]: levels[ks[i]] / levels[ks[i - 1]] - 1 for i in range(1, len(ks)) if levels[ks[i - 1]]}


def load_book():
    d = json.load(open(os.path.join(S, "long1997", "book1997_ts_synth.json")))
    P = d["paths"]
    dates = P["dates"]
    if isinstance(dates, dict):                      # {index: date} or {date: ...}
        dates = [dates[k] for k in sorted(dates, key=lambda x: int(x))] if all(str(k).isdigit() for k in dates) else sorted(dates)
    out = {}
    for k in ("book", "HG", "KMLM", "SLEEVE", "HARV", "SPY", "QQQ"):
        v = P[k]
        if isinstance(v, dict) and "value" in v:         # add. 47's shape: {'value': [weekly levels]}
            v = v["value"]
        if isinstance(v, dict):
            lv = {dt: x for dt, x in v.items() if x} if not all(str(q).isdigit() for q in v) else \
                 {dates[int(i)]: x for i, x in v.items() if x}
        else:
            lv = {dt: x for dt, x in zip(dates, v) if x}
        out[k] = to_returns(month_ends(lv))
    return out


def load_aqr():
    raw = json.load(open(os.path.join(S, "vme", "aqr_vme.json")))
    out = {}
    for name, s in raw.items():
        key = {"VAL|EVERYWHERE": "VAL_ALL", "MOM|EVERYWHERE": "MOM_ALL", "VAL^SS": "VAL_SS", "MOM^SS": "MOM_SS",
               "VAL^AA": "VAL_AA", "MOM^AA": "MOM_AA", "VALLS_VME_US90": "VAL_US", "MOMLS_VME_US90": "MOM_US"}.get(name, name)
        out[key] = {}
        for dt, v in s.items():
            m, d_, y = dt.split("/")
            out[key][f"{y}-{m}"] = v
    return out


def load_french():
    f = json.load(open(os.path.join(S, "vme", "french.json")))
    return {"MKT": f["US:Mkt-RF"], "HML": f["US:HML"], "UMD": f.get("US:Mom") or f["US:Mom   "], "RF": f["US:RF"], "SMB": f["US:SMB"]}


def load_etfs():
    adj = json.load(open(os.path.join(S, "vme", "etf_adj.json")))
    return {t: to_returns(month_ends(s)) for t, s in adj.items()}, adj


def load_fred(name):
    out = {}
    with open(os.path.join(S, "vme", "dl", f"fred_{name}.csv")) as f:
        for row in csv.DictReader(f):
            v = row.get(name) or row.get("value") or ""
            try:
                out[row["observation_date"] if "observation_date" in row else row["DATE"]] = float(v)
            except ValueError:
                pass
    return out


# ------------------------------------------------------------------ stats
def common(*series, lo=None, hi=None):
    ks = set(series[0])
    for s in series[1:]:
        ks &= set(s)
    return sorted(k for k in ks if (lo is None or k >= lo) and (hi is None or k <= hi))


def mean(x):
    return sum(x) / len(x)


def sd(x):
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else float("nan")


def sharpe(r):
    return mean(r) / sd(r) * math.sqrt(12) if len(r) > 2 and sd(r) > 0 else float("nan")


def corr(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def maxdd(r):
    peak, eq, worst = 1.0, 1.0, 0.0
    for x in r:
        eq *= 1 + x
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def cagr(r):
    eq = 1.0
    for x in r:
        eq *= 1 + x
    return eq ** (12 / len(r)) - 1 if r else float("nan")


def solve(A, b):
    """Gauss-Jordan for small systems"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-14:
            return None
        f = M[c][c]
        M[c] = [v / f for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                g = M[r][c]
                M[r] = [a - g * b2 for a, b2 in zip(M[r], M[c])]
    return [M[i][n] for i in range(n)]


def inv(A):
    n = len(A)
    cols = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        cols.append(solve(A, e))
    if any(c is None for c in cols):
        return None
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def ols(y, X, names):
    """OLS with an intercept; HAC (Newey-West, 3 lags) t-stats. X: list of columns"""
    n = len(y)
    k = len(X) + 1
    Z = [[1.0] + [col[i] for col in X] for i in range(n)]
    XtX = [[sum(Z[i][a] * Z[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(k)]
    beta = solve(XtX, Xty)
    XtXi = inv(XtX)
    if beta is None or XtXi is None:
        return None
    res = [y[i] - sum(Z[i][a] * beta[a] for a in range(k)) for i in range(n)]
    L = 3
    Sm = [[0.0] * k for _ in range(k)]
    for lag in range(0, L + 1):
        w = 1 - lag / (L + 1)
        for i in range(lag, n):
            for a in range(k):
                for b in range(k):
                    v = Z[i][a] * res[i] * Z[i - lag][b] * res[i - lag]
                    Sm[a][b] += w * (v if lag == 0 else v)
                    if lag:
                        Sm[a][b] += w * Z[i - lag][a] * res[i - lag] * Z[i][b] * res[i]
    V = [[sum(XtXi[a][p] * Sm[p][q] * XtXi[q][b] for p in range(k) for q in range(k)) for b in range(k)] for a in range(k)]
    se = [math.sqrt(max(V[a][a], 0)) for a in range(k)]
    tss = sum((v - mean(y)) ** 2 for v in y)
    r2 = 1 - sum(r * r for r in res) / tss if tss else float("nan")
    return {"alpha_ann": beta[0] * 12, "t_alpha": beta[0] / se[0] if se[0] else float("nan"), "r2": r2, "n": n,
            "beta": {nm: beta[i + 1] for i, nm in enumerate(names)},
            "t": {nm: (beta[i + 1] / se[i + 1] if se[i + 1] else float("nan")) for i, nm in enumerate(names)}}


def ar2_shocks(level):
    """residuals of an AR(2) on a monthly level series (the paper's liquidity shocks)"""
    ks = sorted(level)
    y = [level[k] for k in ks[2:]]
    X = [[level[k] for k in ks[1:-1]], [level[k] for k in ks[:-2]]]
    fit = ols(y, X, ["l1", "l2"])
    out = {}
    for i, k in enumerate(ks[2:]):
        pred = fit["alpha_ann"] / 12 + fit["beta"]["l1"] * X[0][i] + fit["beta"]["l2"] * X[1][i]
        out[k] = y[i] - pred
    return out


# ------------------------------------------------------------------ study
def excess(r, rf, ks):
    return [r[k] - rf.get(k, 0.0) for k in ks]


def main():
    book = load_book()
    aqr = load_aqr()
    ff = load_french()
    etf_m, etf_d = load_etfs()
    res = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}

    # ---- 0. the factors themselves, as AQR now publishes them (the paper's Table I in its sample, then since)
    fac = {}
    for key in ("VAL_ALL", "MOM_ALL", "VAL_SS", "MOM_SS", "VAL_AA", "MOM_AA", "VAL_US", "MOM_US"):
        s = aqr[key]
        for lo, hi, tag in (("1972-01", "2011-07", "paper"), ("2011-08", "2025-12", "since"), ("1972-01", "2025-12", "all"), ("1997-01", "2025-12", "book era")):
            ks = common(s, lo=lo, hi=hi)
            r = [s[k] for k in ks]
            fac.setdefault(key, {})[tag] = {"sharpe": sharpe(r), "mean_ann": mean(r) * 12, "vol_ann": sd(r) * math.sqrt(12), "maxdd": maxdd(r), "n": len(r)}
    for tag, (lo, hi) in (("paper", ("1972-01", "2011-07")), ("since", ("2011-08", "2025-12")), ("all", ("1972-01", "2025-12")), ("book era", ("1997-01", "2025-12"))):
        ks = common(aqr["VAL_ALL"], aqr["MOM_ALL"], lo=lo, hi=hi)
        v = [aqr["VAL_ALL"][k] for k in ks]
        m = [aqr["MOM_ALL"][k] for k in ks]
        c = [(a + b) / 2 for a, b in zip(v, m)]
        fac.setdefault("COMBO_ALL", {})[tag] = {"sharpe": sharpe(c), "mean_ann": mean(c) * 12, "vol_ann": sd(c) * math.sqrt(12), "maxdd": maxdd(c), "n": len(c), "corr_val_mom": corr(v, m)}
        ks2 = common(aqr["VAL_US"], aqr["MOM_US"], lo=lo, hi=hi)
        fac.setdefault("CORR_US", {})[tag] = corr([aqr["VAL_US"][k] for k in ks2], [aqr["MOM_US"][k] for k in ks2])
    res["factors"] = fac
    # worst stretches of value
    res["value_drawdowns"] = {}
    for key in ("VAL_ALL", "VAL_US", "VAL_SS"):
        s = aqr[key]
        ks = sorted(s)
        eq, peak, pk, worst, trough = 1.0, 1.0, ks[0], 0.0, None
        for k in ks:
            eq *= 1 + s[k]
            if eq > peak:
                peak, pk = eq, k
            dd = eq / peak - 1
            if dd < worst:
                worst, trough = dd, (pk, k)
        res["value_drawdowns"][key] = {"maxdd": worst, "peak": trough[0], "trough": trough[1]}

    # ---- 1. factor exposure of the book and engines
    expo = {}
    rf = ff["RF"]
    models = {
        "AQR everywhere": (["MKT", "VAL_ALL", "MOM_ALL"], {"MKT": ff["MKT"], "VAL_ALL": aqr["VAL_ALL"], "MOM_ALL": aqr["MOM_ALL"]}),
        "French US": (["MKT", "HML", "UMD"], {"MKT": ff["MKT"], "HML": ff["HML"], "UMD": ff["UMD"]}),
        "AQR stocks/assets": (["MKT", "VAL_SS", "MOM_SS", "VAL_AA", "MOM_AA"], {"MKT": ff["MKT"], "VAL_SS": aqr["VAL_SS"], "MOM_SS": aqr["MOM_SS"], "VAL_AA": aqr["VAL_AA"], "MOM_AA": aqr["MOM_AA"]}),
    }
    for name, r in book.items():
        for mname, (names, X) in models.items():
            for era, (lo, hi) in ERAS.items():
                ks = common(r, rf, *X.values(), lo=lo, hi=hi)
                if len(ks) < 36:
                    continue
                y = excess(r, rf, ks)
                fit = ols(y, [[X[nm][k] for k in ks] for nm in names], names)
                fit["corr"] = {nm: corr(y, [X[nm][k] for k in ks]) for nm in names}
                fit["sharpe"] = sharpe(y)
                expo.setdefault(name, {}).setdefault(mname, {})[era] = fit
    res["exposure"] = expo

    # ---- 2. diversification: the factor at equal risk (bound), then buyable value
    div = {"factor_bound": {}, "etf_blend": {}}
    for era, (lo, hi) in ERAS.items():
        for fk in ("VAL_ALL", "MOM_ALL", "VAL_AA", "VAL_SS"):
            ks = common(book["book"], rf, aqr[fk], lo=lo, hi=hi)
            b = excess(book["book"], rf, ks)
            f = [aqr[fk][k] for k in ks]
            scale = sd(b) / sd(f) if sd(f) else 0
            rows = {}
            for w in (0.0, 0.2, 0.5):
                mix = [(1 - w) * x + w * scale * y for x, y in zip(b, f)]
                rows[str(w)] = {"sharpe": sharpe(mix), "maxdd": maxdd(mix), "vol_ann": sd(mix) * math.sqrt(12)}
            div["factor_bound"].setdefault(era, {})[fk] = {"corr": corr(b, f), "mix": rows}
    for proxy, lo0 in (("IWD", "2000-07"), ("VTV", "2004-03"), ("VLUE", "2013-06"), ("QVAL", "2014-12"), ("IVAL", "2015-02")):
        if proxy not in etf_m:
            continue
        for era, (lo, hi) in (("since start", (lo0, "2026-09")), ("2015-2026", ("2015-02", "2026-09")), ("to 2014", (lo0, "2014-12"))):
            ks = common(book["book"], etf_m[proxy], etf_m["SPY"], lo=max(lo, lo0), hi=hi)
            if len(ks) < 36:
                continue
            b = [book["book"][k] for k in ks]
            v = [etf_m[proxy][k] for k in ks]
            spy = [etf_m["SPY"][k] for k in ks]
            rows = {}
            for w in (0.0, 0.1, 0.2, 0.3):
                mix = [(1 - w) * x + w * y for x, y in zip(b, v)]
                rows[str(w)] = {"cagr": cagr(mix), "sharpe": sharpe([x - rf.get(k, 0) for x, k in zip(mix, ks)]), "maxdd": maxdd(mix), "vol_ann": sd(mix) * math.sqrt(12)}
            div["etf_blend"].setdefault(proxy, {})[era] = {"n": len(ks), "corr_book": corr(b, v), "corr_spy": corr(spy, v),
                                                        "proxy": {"cagr": cagr(v), "sharpe": sharpe([x - rf.get(k, 0) for x, k in zip(v, ks)]), "maxdd": maxdd(v)},
                                                        "mix": rows}
    # value minus growth (long-short proxy)
    ks = common(etf_m["IWD"], etf_m["IWF"], book["book"], lo="2000-07", hi="2026-09")
    ls = {k: etf_m["IWD"][k] - etf_m["IWF"][k] for k in ks}
    div["IWD_minus_IWF"] = {"corr_book": corr([book["book"][k] for k in ks], [ls[k] for k in ks]),
                            "corr_VAL_US": corr([ls[k] for k in common(ls, aqr["VAL_US"])], [aqr["VAL_US"][k] for k in common(ls, aqr["VAL_US"])]),
                            "sharpe": sharpe([ls[k] for k in ks]), "n": len(ks)}
    res["diversification"] = div

    # ---- 3. liquidity shocks
    liq = {}
    series = {}
    for name, fred, sign in (("TED", "TEDRATE", -1), ("HY_OAS", "BAMLH0A0HYM2", -1), ("VIX", "VIXCLS", -1)):
        daily = load_fred(fred)
        monthly = {}
        for d in sorted(daily):
            monthly.setdefault(ym(d), []).append(daily[d])
        level = {k: sign * mean(v) for k, v in monthly.items()}      # signed as liquidity, monthly average as the paper
        series[name] = {"level": level, "shock": ar2_shocks(level)}
    targets = {"book": book["book"], "HG": book["HG"], "KMLM": book["KMLM"], "SLEEVE": book["SLEEVE"], "HARV": book["HARV"],
               "SPY": book["SPY"], "VAL_ALL": aqr["VAL_ALL"], "MOM_ALL": aqr["MOM_ALL"], "VAL_US": aqr["VAL_US"], "MOM_US": aqr["MOM_US"]}
    for lname, sr in series.items():
        sh = sr["shock"]
        for tname, r in targets.items():
            ks = common(r, sh, lo="1997-01", hi="2025-12")
            if len(ks) < 60:
                continue
            y = [r[k] - (rf.get(k, 0) if tname in ("book", "HG", "KMLM", "SLEEVE", "HARV", "SPY") else 0) for k in ks]
            x = [sh[k] for k in ks]
            xs = sd(x)
            fit = ols(y, [[v / xs for v in x]], ["shock"])                 # beta per 1-sd shock
            # predictive: next month after a worsening (negative) vs improving shock
            nxt = {}
            for k in ks[:-1]:
                j = ks[ks.index(k) + 1]
                nxt.setdefault("worse" if sh[k] < 0 else "better", []).append(r[j])
            # level gate: spread above its trailing 12-month average (liquidity below average) -> next month
            lv = sr["level"]
            gate = {}
            for k in ks[:-1]:
                prev = [lv[q] for q in sorted(lv) if q < k][-12:]
                if len(prev) < 12:
                    continue
                j = ks[ks.index(k) + 1]
                gate.setdefault("tight" if lv[k] < mean(prev) else "easy", []).append(r[j])
            liq.setdefault(lname, {})[tname] = {
                "beta_1sd_monthly": fit["beta"]["shock"], "t": fit["t"]["shock"], "n": fit["n"],
                "next_month": {s: {"mean_ann": mean(v) * 12, "sharpe": sharpe(v), "n": len(v)} for s, v in nxt.items()},
                "level_gate": {s: {"mean_ann": mean(v) * 12, "sharpe": sharpe(v), "n": len(v)} for s, v in gate.items()}}
    res["liquidity"] = liq

    # ---- 4. a buyable VME on asset-class ETFs
    uni = ["SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "VNQ", "UUP"]
    lv = {t: month_ends(etf_d[t]) for t in uni if t in etf_d}
    months = sorted(set.intersection(*[set(v) for v in lv.values()]))

    def ret(t, a, b):
        return lv[t][b] / lv[t][a] - 1

    def sleeve(signal_fn, lookback, top=3):
        out = {}
        for i in range(lookback + 1, len(months)):
            m0, m1 = months[i - 1], months[i]
            scores = {t: signal_fn(t, i) for t in lv}
            scores = {t: s for t, s in scores.items() if s is not None}
            if len(scores) < top:
                continue
            pick = sorted(scores, key=lambda t: -scores[t])[:top]
            out[m1] = mean([ret(t, m0, m1) for t in pick])
        return out
    mom = sleeve(lambda t, i: ret(t, months[i - 13], months[i - 2]) if i >= 13 else None, 13)
    val = sleeve(lambda t, i: -ret(t, months[i - 60], months[i - 1]) if i >= 60 else None, 60)
    ks = common(mom, val)
    combo = {k: (mom[k] + val[k]) / 2 for k in ks}
    ew = {months[i]: mean([ret(t, months[i - 1], months[i]) for t in lv]) for i in range(1, len(months))}
    sixty = {months[i]: 0.6 * ret("SPY", months[i - 1], months[i]) + 0.4 * ret("IEF", months[i - 1], months[i]) for i in range(1, len(months))}
    vme = {}
    for name, s in (("MOM sleeve", mom), ("VAL sleeve", val), ("50/50", combo), ("equal weight", ew), ("60/40", sixty), ("SPY", etf_m["SPY"]), ("book", book["book"])):
        for era, (lo, hi) in (("2012-2026", (min(ks), "2026-09")), ("2008-2026", (min(mom), "2026-09"))):
            kk = common(s, rf, lo=lo, hi=hi)
            if len(kk) < 24:
                continue
            r = [s[k] for k in kk]
            vme.setdefault(name, {})[era] = {"cagr": cagr(r), "vol_ann": sd(r) * math.sqrt(12), "sharpe": sharpe([x - rf.get(k, 0) for x, k in zip(r, kk)]), "maxdd": maxdd(r), "n": len(r),
                                            "corr_book": corr(r, [book["book"][k] for k in kk]) if all(k in book["book"] for k in kk) else None,
                                            "corr_spy": corr(r, [etf_m["SPY"][k] for k in kk])}
    kk = common(combo, book["book"], rf)
    b = [book["book"][k] for k in kk]
    c = [combo[k] for k in kk]
    vme["book blend 2012-2026"] = {str(w): {"cagr": cagr([(1 - w) * x + w * y for x, y in zip(b, c)]),
                                           "sharpe": sharpe([(1 - w) * x + w * y - rf.get(k, 0) for x, y, k in zip(b, c, kk)]),
                                           "maxdd": maxdd([(1 - w) * x + w * y for x, y in zip(b, c)])} for w in (0.0, 0.1, 0.2, 0.3)}
    # AQR's own asset-allocation factors over the same window, for scale
    for key in ("VAL_AA", "MOM_AA"):
        kk = common(aqr[key], lo=min(ks), hi="2024-12")
        vme[f"AQR {key} (long-short)"] = {"2012-2024": {"sharpe": sharpe([aqr[key][k] for k in kk]), "mean_ann": mean([aqr[key][k] for k in kk]) * 12}}
    res["buyable_vme"] = vme
    res["paths"] = {"months": ks, "mom": [mom[k] for k in ks], "val": [val[k] for k in ks], "combo": [combo[k] for k in ks],
                    "spy": [etf_m["SPY"].get(k) for k in ks], "book": [book["book"].get(k) for k in ks]}
    # factor paths for the chart (monthly, from 1972)
    kf = common(aqr["VAL_ALL"], aqr["MOM_ALL"])
    res["factor_paths"] = {"months": kf, "VAL_ALL": [aqr["VAL_ALL"][k] for k in kf], "MOM_ALL": [aqr["MOM_ALL"][k] for k in kf],
                           "VAL_US": [aqr["VAL_US"].get(k) for k in kf], "book": [book["book"].get(k) for k in kf]}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print("wrote", OUT)
    return res


if __name__ == "__main__":
    r = main()
    f = r["factors"]
    print("\nAQR factors, Sharpe (paper 1972-2011 / since 2011-08 / all):")
    for k in ("VAL_ALL", "MOM_ALL", "COMBO_ALL", "VAL_US", "MOM_US", "VAL_AA", "MOM_AA"):
        print(f"  {k:10s} {f[k]['paper']['sharpe']:.2f} / {f[k]['since']['sharpe']:.2f} / {f[k]['all']['sharpe']:.2f}   maxDD all {f[k]['all']['maxdd']:.0%}")
    print("corr(VAL,MOM) everywhere:", {t: round(f["COMBO_ALL"][t]["corr_val_mom"], 2) for t in f["COMBO_ALL"]})
    print("value drawdowns:", r["value_drawdowns"])
    print("\nexposure (AQR everywhere), beta [t]:")
    for name, m in r["exposure"].items():
        for era, fit in m["AQR everywhere"].items():
            b, t = fit["beta"], fit["t"]
            print(f"  {name:6s} {era}: MKT {b['MKT']:+.2f} [{t['MKT']:.1f}]  VAL {b['VAL_ALL']:+.2f} [{t['VAL_ALL']:.1f}]  MOM {b['MOM_ALL']:+.2f} [{t['MOM_ALL']:.1f}]  alpha {fit['alpha_ann']:+.1%} [{fit['t_alpha']:.1f}] R2 {fit['r2']:.2f}  corrVAL {fit['corr']['VAL_ALL']:+.2f} corrMOM {fit['corr']['MOM_ALL']:+.2f}")
    print("\nfactor bound (book + factor at equal risk):")
    for era, d in r["diversification"]["factor_bound"].items():
        for fk, v in d.items():
            print(f"  {era} {fk}: corr {v['corr']:+.2f}  Sharpe w=0 {v['mix']['0.0']['sharpe']:.2f} w=.2 {v['mix']['0.2']['sharpe']:.2f} w=.5 {v['mix']['0.5']['sharpe']:.2f}")
    print("\nETF value blends:")
    for p, d in r["diversification"]["etf_blend"].items():
        for era, v in d.items():
            print(f"  {p} {era} n={v['n']} corr_book {v['corr_book']:+.2f} proxy Sharpe {v['proxy']['sharpe']:.2f}: " + "  ".join(f"w{w}: S {x['sharpe']:.2f} DD {x['maxdd']:.0%}" for w, x in v['mix'].items()))
    print("IWD-IWF:", r["diversification"]["IWD_minus_IWF"])
    print("\nliquidity (beta per 1-sd shock, monthly; next-month Sharpe after worse/better shock; level gate tight/easy):")
    for lname, d in r["liquidity"].items():
        for t, v in d.items():
            nm = v["next_month"]; lg = v["level_gate"]
            print(f"  {lname:6s} {t:8s} beta {v['beta_1sd_monthly']:+.4f} [{v['t']:.1f}] | next: worse {nm.get('worse', {}).get('sharpe', float('nan')):.2f} better {nm.get('better', {}).get('sharpe', float('nan')):.2f} | gate: tight {lg.get('tight', {}).get('sharpe', float('nan')):.2f} easy {lg.get('easy', {}).get('sharpe', float('nan')):.2f}")
    print("\nbuyable VME:")
    for name, d in r["buyable_vme"].items():
        print(" ", name, json.dumps({k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in d.items()}))
