#!/usr/bin/env python3
"""What a long-only value / momentum stock sleeve could earn in IBKR (results.md addendum 52).

Owner, 2026-11-03: "What about making a momentum vs value sleeve strategy within IBKR, outside of
Composer? What could returns look like? Can we make a better performing strategy than our current
IBKR SPY and Genomics sleeve?"

Evidence, in the order it should be trusted:
  A. Ken French's long-only portfolios (CRSP/Compustat; survivorship-free; point-in-time; value-
     weighted; monthly; GROSS of trading costs):
       BIG rows   the 2x3 sorts (size above the NYSE median x the top 30% on the signal, NYSE
                  breakpoints): BIG HiPRIOR (prior 12-2 month return, monthly rebalance; ~300 names),
                  BIG HiBM (book-to-market, June rebalance; ~140 names), BIG HiOP (operating
                  profitability, June; ~310 names). These are the sleeve: the names an IBKR account
                  would trade, enough of them to be a portfolio.
       "20" rows  the 5x5 corner cells (largest size quintile x top signal quintile): the concentrated
                  versions. The value corner holds 6-31 names (median 23) and is bank-heavy; shown as a
                  sensitivity, not as the sleeve (counter-agent, add. 52).
       all-cap    the top deciles (10_Portfolios_Prior_12_2, BE-ME, OP): hundreds of names including
                  microcaps; not holdable at this size, kept for the long record.
     Two- and three-sleeve portfolios are monthly-rebalanced equal mixes of the rows.
  B. The live ETFs that implement these, NET of fees, real fills: MTUM / VLUE (2013-), SPMO (2015-),
     QVAL / QMOM (2015 / 2016-), VFMO / VFVA (2018-), VTV / IWD; QQQ / RSP / IWF for contrast;
     ARKG / XBI / IBB / GNOM as genomics CONTEXT (they are not the owner's sleeve).
Benchmarks: the CRSP value-weighted market (Mkt-RF + RF) in the French era; SPY from 1993-02.
Costs: French rows are gross. COSTS below is an ASSUMED annual drag applied as a sensitivity: a monthly
12-2 sort keeps a top-30% name with p ~0.8 a month, i.e. ~250% one-way turnover a year, at 10-20 bps a
round trip in mega caps ~0.4-0.5%/yr at $150k (more at $50k: IBKR Pro's $1 minimum per order); the June
sorts turn over 20-30% a year. Taxes are not modeled (Act 60).

Inputs (scratchpad vmi/, fetched 2026-11-03): french_ports.json (parse_french.py over the library's
CSV zips: value-weighted monthly returns and the firm counts), etf_adj.json (Yahoo monthly adjusted
closes, range=max). French's last month is 2026-09 and every window stops there; the ETFs' complete
2026-10 is reported separately. Writes composer/results/vm-ibkr-2026-11-03.json. Usage: vm_ibkr.py
"""
import json
import math
import os
import statistics

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/vmi"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "vm-ibkr-2026-11-03.json")
END = "2026-09"                        # French's last month; every window stops here
END_ETF = "2026-10"                    # the ETFs' last complete month (reported separately)
ERAS = {"1927-2026": ("1927-01", END), "1963-2026": ("1963-07", END), "1993-2026": ("1993-02", END),
        "2010-2026": ("2010-01", END), "2013-2026": ("2013-06", END)}
COSTS = {"BIG-MOM": 0.5, "BIG-VAL": 0.2, "BIG-QUAL": 0.2, "BIG-MOM20": 0.5, "BIG-VAL20": 0.2, "BIG-QUAL20": 0.2}
ROLL = 120                             # rolling window, months
SOURCES = {"MKT": ("F-F_Research_Data_Factors", "Mkt-RF + RF"),
           "BIG-MOM": ("6_Portfolios_ME_Prior_12_2", "BIG HiPRIOR"), "BIG-VAL": ("6_Portfolios_2x3", "BIG HiBM"),
           "BIG-QUAL": ("6_Portfolios_ME_OP_2x3", "BIG HiOP"),
           "BIG-LOMOM": ("6_Portfolios_ME_Prior_12_2", "BIG LoPRIOR"), "BIG-GROWTH": ("6_Portfolios_2x3", "BIG LoBM"),
           "BIG-MOM20": ("25_Portfolios_ME_Prior_12_2", "BIG HiPRIOR"), "BIG-VAL20": ("25_Portfolios_5x5", "BIG HiBM"),
           "BIG-QUAL20": ("25_Portfolios_ME_OP_5x5", "BIG HiOP"),
           "MOM10": ("10_Portfolios_Prior_12_2", "Hi PRIOR"), "MOM1": ("10_Portfolios_Prior_12_2", "Lo PRIOR"),
           "VAL10": ("Portfolios_Formed_on_BE-ME", "Hi 10"), "VAL1": ("Portfolios_Formed_on_BE-ME", "Lo 10"),
           "QUAL10": ("Portfolios_Formed_on_OP", "Hi 10")}


# ------------------------------------------------------------------ loading
def norm(s):
    return "".join(s.lower().split())


def load_french():
    f = json.load(open(os.path.join(S, "french_ports.json")))

    def col(name, colname):
        t = f[name]
        cols = [norm(c) for c in t["cols"]]
        if norm(colname) not in cols:
            raise KeyError(f"{name}: {colname!r} not in {t['cols']}")
        return t, cols.index(norm(colname))

    ff = f["F-F_Research_Data_Factors"]
    cols = [norm(c) for c in ff["cols"]]
    rf = {m: v[cols.index("rf")] / 100 for m, v in ff["rows"].items() if m <= END}
    mkt = {m: v[cols.index("mkt-rf")] / 100 + rf[m] for m, v in ff["rows"].items() if m <= END}
    P, firms = {"MKT": mkt}, {}
    for k, (name, colname) in SOURCES.items():
        if k == "MKT":
            continue
        t, i = col(name, colname)
        P[k] = {m: v[i] / 100 for m, v in t["rows"].items() if v[i] is not None and m <= END}
        if "firms" in t:
            ks = sorted(m for m in t["firms"] if m >= "1963-07" and t["firms"][m][i] is not None)
            vals = [t["firms"][m][i] for m in ks]
            firms[k] = {"min": min(vals), "median": statistics.median(vals), "max": max(vals), "latest": vals[-1],
                        "latest_month": ks[-1], "since": ks[0]}
    return P, rf, firms


def load_etfs(end=END):
    adj = json.load(open(os.path.join(S, "etf_adj.json")))
    out = {}
    for t, lv in adj.items():
        ks = sorted(k for k in lv if k <= end)
        out[t] = {ks[i]: lv[ks[i]] / lv[ks[i - 1]] - 1 for i in range(1, len(ks))}
    return out


# ------------------------------------------------------------------ stats
def common(*series, lo=None, hi=None):
    ks = set(series[0])
    for s in series[1:]:
        ks &= set(s)
    return sorted(k for k in ks if (lo is None or k >= lo) and (hi is None or k <= hi))


def mean(x):
    return sum(x) / len(x) if x else float("nan")


def sd(x):
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else float("nan")


def cagr(r):
    g = 1.0
    for v in r:
        g *= 1 + v
    return g ** (12 / len(r)) - 1 if r else float("nan")


def total(r):
    g = 1.0
    for v in r:
        g *= 1 + v
    return g - 1


def maxdd(r):
    peak, lv, worst = 1.0, 1.0, 0.0
    for v in r:
        lv *= 1 + v
        peak = max(peak, lv)
        worst = min(worst, lv / peak - 1)
    return worst


def levels(r):
    out, lv = [], 1.0
    for v in r:
        lv *= 1 + v
        out.append(lv)
    return out


def corr(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def beta(a, b):
    ma, mb = mean(a), mean(b)
    den = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else float("nan")


def mix(P, weights):
    """monthly-rebalanced constant mix of return series"""
    ms = common(*[P[k] for k in weights])
    return {m: sum(w * P[k][m] for k, w in weights.items()) for m in ms}


def stats(r, bench, rf, months):
    """r, bench, rf: {month: return}; months: the window. Everything vs the benchmark on the same months"""
    x = [r[m] for m in months]
    b = [bench[m] for m in months]
    f = [rf[m] for m in months]
    ex = [v - q for v, q in zip(x, f)]
    bx = [v - q for v, q in zip(b, f)]
    rel = [(1 + v) / (1 + q) - 1 for v, q in zip(x, b)]      # relative wealth return
    yrs = {}
    for m, v, q in zip(months, x, b):
        y = m[:4]
        yrs.setdefault(y, [1.0, 1.0])
        yrs[y][0] *= 1 + v
        yrs[y][1] *= 1 + q
    full = [y for y, (a, c) in yrs.items() if len([m for m in months if m[:4] == y]) == 12]
    wins = sum(1 for y in full if yrs[y][0] > yrs[y][1])
    out = {"n": len(months), "from": months[0], "to": months[-1],
           "cagr": cagr(x), "vol": sd(x) * math.sqrt(12), "sharpe": mean(ex) / sd(ex) * math.sqrt(12),
           "maxdd": maxdd(x), "bench_cagr": cagr(b), "bench_sharpe": mean(bx) / sd(bx) * math.sqrt(12),
           "bench_maxdd": maxdd(b), "excess_cagr": cagr(x) - cagr(b),
           "te": sd([v - q for v, q in zip(x, b)]) * math.sqrt(12),
           "beta": beta(x, b), "corr": corr(x, b), "rel_maxdd": maxdd(rel),
           "years_beating": wins, "years": len(full)}
    out["ir"] = mean([v - q for v, q in zip(x, b)]) * 12 / out["te"] if out["te"] else float("nan")
    if len(months) >= ROLL:
        roll = []
        for i in range(ROLL, len(months) + 1):
            roll.append(cagr(x[i - ROLL:i]) - cagr(b[i - ROLL:i]))
        out["roll10"] = {"share_positive": sum(1 for v in roll if v > 0) / len(roll), "worst": min(roll),
                         "best": max(roll), "latest": roll[-1], "latest_window": f"{months[-ROLL]}..{months[-1]}",
                         "windows": len(roll)}
    return out


def rolling_series(r, bench, months):
    x = [r[m] for m in months]
    b = [bench[m] for m in months]
    return {months[i - 1]: round(cagr(x[i - ROLL:i]) - cagr(b[i - ROLL:i]), 5) for i in range(ROLL, len(months) + 1)}


def decades(r, bench, months):
    out = {}
    for m in months:
        d = m[:3] + "0s"
        out.setdefault(d, [[], []])
        out[d][0].append(r[m])
        out[d][1].append(bench[m])
    return {d: {"n": len(a), "cagr": cagr(a), "bench_cagr": cagr(b), "excess": cagr(a) - cagr(b)} for d, (a, b) in out.items()}


# ------------------------------------------------------------------ main
def main():
    P, rf, firms = load_french()
    E = load_etfs()
    res = {"generated": "2026-11-03", "sources": {k: f"{v[0]}: {v[1]}" for k, v in SOURCES.items()}, "firms": firms,
           "costs_pct_per_year": COSTS, "roll_months": ROLL}

    # sleeves (gross) and the net versions of the big-cap rows and mixes
    P["BIG V+M"] = mix(P, {"BIG-VAL": .5, "BIG-MOM": .5})
    P["BIG V+Q"] = mix(P, {"BIG-VAL": .5, "BIG-QUAL": .5})
    P["BIG V+M+Q"] = mix(P, {"BIG-VAL": 1 / 3, "BIG-MOM": 1 / 3, "BIG-QUAL": 1 / 3})
    P["BIG V+M (20)"] = mix(P, {"BIG-VAL20": .5, "BIG-MOM20": .5})
    P["BIG V+M+Q (20)"] = mix(P, {"BIG-VAL20": 1 / 3, "BIG-MOM20": 1 / 3, "BIG-QUAL20": 1 / 3})
    P["V+M"] = mix(P, {"VAL10": .5, "MOM10": .5})
    P["V+M+Q"] = mix(P, {"VAL10": 1 / 3, "MOM10": 1 / 3, "QUAL10": 1 / 3})
    drag = dict(COSTS)
    drag["BIG V+M"] = (COSTS["BIG-VAL"] + COSTS["BIG-MOM"]) / 2
    drag["BIG V+Q"] = (COSTS["BIG-VAL"] + COSTS["BIG-QUAL"]) / 2
    drag["BIG V+M+Q"] = (COSTS["BIG-VAL"] + COSTS["BIG-MOM"] + COSTS["BIG-QUAL"]) / 3
    drag["BIG V+M (20)"] = (COSTS["BIG-VAL20"] + COSTS["BIG-MOM20"]) / 2
    drag["BIG V+M+Q (20)"] = (COSTS["BIG-VAL20"] + COSTS["BIG-MOM20"] + COSTS["BIG-QUAL20"]) / 3
    NET = {k + " net": {m: v - c / 100 / 12 for m, v in P[k].items()} for k, c in drag.items()}
    res["drag_pct_per_year"] = drag

    # 1. French long-only portfolios vs the market, by era (gross and net)
    names = ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+Q", "BIG V+M+Q",
             "BIG-MOM20", "BIG-VAL20", "BIG-QUAL20", "BIG V+M (20)", "BIG V+M+Q (20)",
             "MOM10", "VAL10", "QUAL10", "V+M", "V+M+Q", "BIG-LOMOM", "BIG-GROWTH", "MOM1", "VAL1"]
    net_names = ["BIG V+M net", "BIG V+M+Q net", "BIG-MOM net", "BIG-VAL net", "BIG V+M (20) net"]
    res["french"] = {}
    for era, (lo, hi) in ERAS.items():
        res["french"][era] = {}
        for k in names + net_names:
            src = NET[k] if k in NET else P[k]
            ms = common(src, P["MKT"], rf, lo=lo, hi=hi)
            if len(ms) < 36:
                continue
            res["french"][era][k] = stats(src, P["MKT"], rf, ms)
        ms = common(P["MKT"], rf, lo=lo, hi=hi)
        res["french"][era]["MKT"] = stats(P["MKT"], P["MKT"], rf, ms)

    # SPY vs the CRSP market where both exist (is the market a fair stand-in for SPY?)
    ms = common(E["SPY"], P["MKT"], rf, lo="1993-02")
    res["spy_vs_mkt"] = stats(E["SPY"], P["MKT"], rf, ms)

    # 2. decades and rolling 10-year excess vs the market (gross)
    res["decades"] = {}
    res["rolling"] = {}
    for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)", "MOM10", "VAL10", "V+M"]:
        ms = common(P[k], P["MKT"], rf)
        res["decades"][k] = decades(P[k], P["MKT"], ms)
        res["rolling"][k] = rolling_series(P[k], P["MKT"], ms)

    # 3. live ETFs vs SPY, each fund from its first return month to END (the first return month is
    #    dropped: the fund's first bar can sit inside a month)
    E["MTUM+VLUE"] = mix(E, {"MTUM": .5, "VLUE": .5})
    E["QVAL+QMOM"] = mix(E, {"QVAL": .5, "QMOM": .5})
    E["VFMO+VFVA"] = mix(E, {"VFMO": .5, "VFVA": .5})
    E["SPMO+VLUE"] = mix(E, {"SPMO": .5, "VLUE": .5})
    res["etfs"] = {}
    for t in ["MTUM", "VLUE", "MTUM+VLUE", "SPMO", "SPMO+VLUE", "QVAL", "QMOM", "QVAL+QMOM", "VFMO", "VFVA", "VFMO+VFVA",
              "VTV", "IWD", "IWF", "QQQ", "RSP", "ARKG", "XBI", "IBB", "GNOM"]:
        ms = common(E[t], E["SPY"], rf)
        ms = ms[1:] if ms else ms
        if len(ms) < 24:
            continue
        res["etfs"][t] = stats(E[t], E["SPY"], rf, ms)
    # the same funds on one common window (2016-02 on: QMOM is the youngest of the core set)
    res["etfs_common"] = {}
    core = ["SPY", "QQQ", "RSP", "MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM", "QVAL+QMOM", "VTV", "IWD", "ARKG", "XBI", "IBB"]
    ms = common(*[E[t] for t in core], rf, lo="2016-02")
    for t in core:
        res["etfs_common"][t] = stats(E[t], E["SPY"], rf, ms)
    res["etfs_common"]["window"] = f"{ms[0]}..{ms[-1]}"
    # French rows on the ETF window, for the gap between the sort and the fund that implements it
    res["french_on_etf_window"] = {}
    for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG-MOM20", "BIG-VAL20", "BIG V+M (20)", "MOM10", "VAL10"]:
        ms2 = common(P[k], E["SPY"], rf, lo=ms[0], hi=ms[-1])
        res["french_on_etf_window"][k] = stats(P[k], E["SPY"], rf, ms2)
    # 3b. the ETFs' complete 2026-10, which the French cut discards
    E10 = load_etfs(END_ETF)
    E10["MTUM+VLUE"] = mix(E10, {"MTUM": .5, "VLUE": .5})
    E10["SPMO+VLUE"] = mix(E10, {"SPMO": .5, "VLUE": .5})
    E10["QVAL+QMOM"] = mix(E10, {"QVAL": .5, "QMOM": .5})
    res["october_2026"] = {"month": END_ETF}
    for t in ["SPY", "QQQ", "MTUM", "VLUE", "MTUM+VLUE", "SPMO", "SPMO+VLUE", "QVAL", "QMOM", "QVAL+QMOM", "VTV", "IWD", "ARKG", "XBI"]:
        ms = common(E10[t], E10["SPY"])[1:]
        row = {"ret": E10[t].get(END_ETF), "from": ms[0], "cagr_to_oct": cagr([E10[t][m] for m in ms]),
               "excess_to_oct": cagr([E10[t][m] for m in ms]) - cagr([E10["SPY"][m] for m in ms])}
        if t in res["etfs"]:
            row["excess_to_sep"] = res["etfs"][t]["excess_cagr"]
        res["october_2026"][t] = row

    # 4. blends: SPY + x of the big-cap sleeve (net), 1993- and 2010-
    res["blends"] = {}
    for era in ["1993-2026", "2010-2026"]:
        lo, hi = ERAS[era]
        res["blends"][era] = {}
        for sleeve in ["BIG V+M net", "BIG V+M+Q net", "BIG-MOM net", "BIG-VAL net"]:
            ms = common(E["SPY"], NET[sleeve], rf, lo=lo, hi=hi)
            row = {}
            for x in (0.0, 0.2, 0.4, 0.6, 1.0):
                blend = {m: (1 - x) * E["SPY"][m] + x * NET[sleeve][m] for m in ms}
                st = stats(blend, E["SPY"], rf, ms)
                row[f"{x:.1f}"] = {k: st[k] for k in ("cagr", "vol", "sharpe", "maxdd", "excess_cagr", "te")}
            res["blends"][era][sleeve] = row

    # 4b. the 2025-26 value rally: the recent windows stopped at 2024-12, and the rally months alone
    res["rally"] = {}
    cuts = {"2010-01..2024-12": ("2010-01", "2024-12"), "2010-01..2026-09": ("2010-01", END),
            "2016-02..2024-12": ("2016-02", "2024-12"), "2016-02..2026-09": ("2016-02", END),
            "2025-01..2026-09": ("2025-01", END)}
    for label, (lo, hi) in cuts.items():
        row = {}
        for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)"]:
            ms = common(P[k], P["MKT"], rf, lo=lo, hi=hi)
            c = cagr([P[k][m] for m in ms])
            row[k] = {"cagr": c, "excess": c - cagr([P["MKT"][m] for m in ms]), "n": len(ms), "from": ms[0],
                      "beta": beta([P[k][m] for m in ms], [P["MKT"][m] for m in ms]),
                      "total": total([P[k][m] for m in ms])}
        for k in ["MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM"]:
            ms = common(E[k], E["SPY"], rf, lo=lo, hi=hi)
            if ms and ms[0] == min(E[k]):
                ms = ms[1:]
            if len(ms) < 12:
                continue
            c = cagr([E[k][m] for m in ms])
            row[k] = {"cagr": c, "excess": c - cagr([E["SPY"][m] for m in ms]), "n": len(ms), "from": ms[0],
                      "beta": beta([E[k][m] for m in ms], [E["SPY"][m] for m in ms]), "total": total([E[k][m] for m in ms])}
        ms = common(P["MKT"], lo=lo, hi=hi)
        row["MKT"] = {"cagr": cagr([P["MKT"][m] for m in ms]), "n": len(ms), "from": ms[0], "total": total([P["MKT"][m] for m in ms])}
        ms = common(E["SPY"], lo=lo, hi=hi)
        row["SPY"] = {"cagr": cagr([E["SPY"][m] for m in ms]), "n": len(ms), "from": ms[0], "total": total([E["SPY"][m] for m in ms])}
        res["rally"][label] = row

    # 5. paths for the exhibit
    def path(src, lo, hi=END):
        ms = common(src, lo=lo, hi=hi)
        return {"months": ms, "levels": [round(v, 5) for v in levels([src[m] for m in ms])]}

    res["paths"] = {
        "A": {k: path(P[k], "1963-07") for k in ["MKT", "BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q"]},
        "C": {k: path(E[k], "2013-06") for k in ["SPY", "QQQ", "MTUM", "VLUE", "MTUM+VLUE"]},
        "D": {k: path(E[k], "2014-12") for k in ["SPY", "ARKG", "XBI", "IBB"]},
    }
    ms = common(P["MKT"], P["BIG V+M"], lo="1963-07")
    for k in ["MKT", "BIG V+M"]:
        lv, peak, dd = 1.0, 1.0, []
        for m in ms:
            lv *= 1 + P[k][m]
            peak = max(peak, lv)
            dd.append(round(lv / peak - 1, 5))
        res["paths"].setdefault("B", {"months": ms})[k] = dd

    json.dump(res, open(OUT, "w"), indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)

    # ---- console summary
    def row(k, st):
        r10 = st.get("roll10") or {}
        return (f"  {k:16s} {st['cagr']:7.1%} {st['vol']:6.1%} {st['sharpe']:6.2f} {st['maxdd']:7.1%} "
                f"{st['excess_cagr']:+7.1%} {st['te']:6.1%} {st['beta']:5.2f} {st['years_beating']:3d}/{st['years']:<3d}"
                + (f" {r10['share_positive']:5.0%} {r10['worst']:+6.1%} {r10['latest']:+6.1%}" if r10 else ""))

    hdr = "                     CAGR    vol Sharpe   maxDD  excess     TE  beta  yrs>mkt  10y>0 worst10 last10"
    print("names per row since 1963-07 (min / median / latest):")
    for k, v in firms.items():
        print(f"  {k:12s} {v['min']:4d} / {v['median']:5.0f} / {v['latest']:4d}  ({res['sources'][k]})")
    for era in ERAS:
        print(f"\n== French long-only, {era} (gross; 'net' = less the assumed drag) ==")
        print(hdr)
        F = res["french"][era]
        print(row("MKT", F["MKT"]))
        for k in names[:6] + net_names + names[6:]:
            if k in F:
                print(row(k, F[k]))
    s = res["spy_vs_mkt"]
    print(f"\nSPY vs CRSP market {s['from']}..{s['to']}: SPY {s['cagr']:.2%} vs market {s['bench_cagr']:.2%}, corr {s['corr']:.3f}")
    print("\n== live ETFs vs SPY, each on its own window (net of fees) ==")
    print("                     CAGR    vol Sharpe   maxDD  excess     TE  beta  yrs>spy   window")
    for t, st in res["etfs"].items():
        print(row(t, st) + f"   {st['from']}..{st['to']}  SPY {st['bench_cagr']:.1%}")
    print(f"\n== live ETFs on one window {res['etfs_common']['window']} ==")
    for t in core:
        print(row(t, res["etfs_common"][t]))
    print("\n== French rows on that window (gross) ==")
    for k, st in res["french_on_etf_window"].items():
        print(row(k, st) + f"  {st['from']}..{st['to']}")
    print(f"\n== the ETFs' {END_ETF} (discarded by the French cut): month return; excess vs SPY to 2026-09 -> to {END_ETF} ==")
    for t, v in res["october_2026"].items():
        if isinstance(v, dict):
            print(f"  {t:10s} {v['ret']:+7.1%}   {v.get('excess_to_sep', float('nan')):+6.1%} -> {v['excess_to_oct']:+6.1%}  (from {v['from']})")
    print("\n== blends SPY + x sleeve (net) ==")
    for era, d in res["blends"].items():
        for sleeve, rows in d.items():
            print(f"  {era} {sleeve:14s} " + "  ".join(f"x={x}: {v['cagr']:.1%}/{v['sharpe']:.2f}/{v['maxdd']:.0%}" for x, v in rows.items()))
    print("\n== the 2025-26 value rally: excess CAGR vs market / SPY; windows stopped at 2024-12 vs through 2026-09 ==")
    keys = ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)", "MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM"]
    print("  " + " " * 14 + "".join(f"{w:>18s}" for w in res["rally"]))
    for b in ("MKT", "SPY"):
        print("  " + f"{b + ' CAGR':14s}" + "".join(f"{res['rally'][w][b]['cagr']:>18.1%}" for w in res["rally"]))
    for k in keys:
        print(f"  {k:14s}" + "".join(f"{res['rally'][w][k]['excess']:>+18.1%}" if k in res["rally"][w] else f"{'':>18s}" for w in res["rally"]))
    print("  betas in the rally window: " + ", ".join(f"{k} {res['rally']['2025-01..2026-09'][k]['beta']:.2f}" for k in ("BIG-VAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "VLUE")))
    print("\n== decades, excess CAGR vs market (gross; months) ==")
    ds = sorted({d for k in res["decades"] for d in res["decades"][k]})
    print("  " + " " * 14 + "".join(f"{d:>9s}" for d in ds))
    for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)", "MOM10", "VAL10"]:
        print(f"  {k:14s}" + "".join(f"{res['decades'][k][d]['excess']:+9.1%}" if d in res["decades"][k] else f"{'':>9s}" for d in ds))
    print("  months        " + "".join(f"{res['decades']['BIG-MOM'][d]['n']:>9d}" for d in ds))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
