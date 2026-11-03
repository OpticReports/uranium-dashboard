#!/usr/bin/env python3
"""What a long-only value / momentum stock sleeve could earn in IBKR (results.md addendum 52).

Owner, 2026-11-03: "What about making a momentum vs value sleeve strategy within IBKR, outside of
Composer? What could returns look like? Can we make a better performing strategy than our current
IBKR SPY and Genomics sleeve?"

Evidence, in the order it should be trusted:
  A. Ken French's long-only portfolios (CRSP/Compustat; survivorship-free; point-in-time; value-
     weighted; monthly; GROSS of trading costs):
       momentum   deciles on the prior 12-2 month return, rebalanced monthly (10_Portfolios_Prior_12_2)
       value      deciles on book-to-market, rebalanced each June (Portfolios_Formed_on_BE-ME)
       quality    deciles on operating profitability, June (Portfolios_Formed_on_OP; 1963-07 on)
       BIG rows   the largest-size quintile (NYSE breakpoints) of the 5x5 size x momentum, size x
                  book-to-market and size x profitability sorts: the names an IBKR sleeve would trade
       value+quality  the HiBM HiOP corner of the 5x5 book-to-market x profitability sort
     Two- and three-sleeve portfolios are monthly-rebalanced equal mixes of the single sorts.
  B. The live ETFs that implement these, NET of fees, real fills: MTUM / VLUE (2013-), QVAL / QMOM
     (2015 / 2016-), SPMO (2015-), VFMO / VFVA (2018-), VTV / IWD; QQQ / RSP / IWF for contrast;
     ARKG / XBI / IBB / GNOM as genomics CONTEXT (they are not the owner's sleeve).
Benchmarks: the CRSP value-weighted market (Mkt-RF + RF) in the French era; SPY from 1993-02.
Costs: French portfolios are gross. COSTS below is an ASSUMED annual drag (turnover x a round-trip
cost), applied as a sensitivity, not a measurement.

Inputs (scratchpad vmi/, fetched 2026-11-03): french_ports.json (parse_french.py over the library's
CSV zips), etf_adj.json (Yahoo monthly adjusted closes, range=max). Writes
composer/results/vm-ibkr-2026-11-03.json. Usage: vm_ibkr.py
"""
import json
import math
import os

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/vmi"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "vm-ibkr-2026-11-03.json")
END = "2026-09"                        # French's last month; every window stops here
ERAS = {"1927-2026": ("1927-01", END), "1963-2026": ("1963-07", END), "1993-2026": ("1993-02", END),
        "2010-2026": ("2010-01", END), "2013-2026": ("2013-06", END)}
# assumed annual drag, % per year: one-way turnover x round-trip cost. Momentum deciles turn over
# ~100%+ one-way a year, value ~25%, profitability ~20%; big caps cost ~10-20 bps a round trip at this
# size, the all-cap deciles hold microcaps that cost several times that.
COSTS = {"MOM10": 1.5, "BIG-MOM": 0.5, "VAL10": 0.5, "BIG-VAL": 0.2, "QUAL10": 0.5, "BIG-QUAL": 0.2,
         "VAL+QUAL": 0.5}
ROLL = 120                             # rolling window, months


# ------------------------------------------------------------------ loading
def norm(s):
    return "".join(s.lower().split())


def load_french():
    f = json.load(open(os.path.join(S, "french_ports.json")))

    def series(name, colname):
        t = f[name]
        cols = [norm(c) for c in t["cols"]]
        if norm(colname) not in cols:
            raise KeyError(f"{name}: {colname!r} not in {t['cols']}")
        i = cols.index(norm(colname))
        return {m: v[i] / 100 for m, v in t["rows"].items() if v[i] is not None and m <= END}

    ff = f["F-F_Research_Data_Factors"]
    cols = [norm(c) for c in ff["cols"]]
    rf = {m: v[cols.index("rf")] / 100 for m, v in ff["rows"].items() if m <= END}
    mkt = {m: v[cols.index("mkt-rf")] / 100 + rf[m] for m, v in ff["rows"].items() if m <= END}
    P = {"MKT": mkt,
         "MOM10": series("10_Portfolios_Prior_12_2", "Hi PRIOR"),
         "MOM1": series("10_Portfolios_Prior_12_2", "Lo PRIOR"),
         "VAL10": series("Portfolios_Formed_on_BE-ME", "Hi 10"),
         "VAL1": series("Portfolios_Formed_on_BE-ME", "Lo 10"),
         "QUAL10": series("Portfolios_Formed_on_OP", "Hi 10"),
         "BIG-MOM": series("25_Portfolios_ME_Prior_12_2", "BIG HiPRIOR"),
         "BIG-LOMOM": series("25_Portfolios_ME_Prior_12_2", "BIG LoPRIOR"),
         "BIG-VAL": series("25_Portfolios_5x5", "BIG HiBM"),
         "BIG-GROWTH": series("25_Portfolios_5x5", "BIG LoBM"),
         "BIG-QUAL": series("25_Portfolios_ME_OP_5x5", "BIG HiOP"),
         "VAL+QUAL": series("25_Portfolios_BEME_OP_5x5", "HiBM HiOP")}
    chosen = {"MOM10": "10_Portfolios_Prior_12_2: Hi PRIOR", "VAL10": "Portfolios_Formed_on_BE-ME: Hi 10",
              "QUAL10": "Portfolios_Formed_on_OP: Hi 10", "BIG-MOM": "25_Portfolios_ME_Prior_12_2: BIG HiPRIOR",
              "BIG-VAL": "25_Portfolios_5x5: BIG HiBM", "BIG-QUAL": "25_Portfolios_ME_OP_5x5: BIG HiOP",
              "VAL+QUAL": "25_Portfolios_BEME_OP_5x5: HiBM HiOP", "MKT": "F-F_Research_Data_Factors: Mkt-RF + RF"}
    return P, rf, chosen


def load_etfs():
    adj = json.load(open(os.path.join(S, "etf_adj.json")))
    out = {}
    for t, lv in adj.items():
        ks = sorted(k for k in lv if k <= END)
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


def mix(P, weights, drag=0.0):
    """monthly-rebalanced constant mix of return series, less an annual drag (fraction) applied monthly"""
    ms = common(*[P[k] for k in weights])
    return {m: sum(w * P[k][m] for k, w in weights.items()) - drag / 12 for m in ms}


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
                         "best": max(roll), "latest": roll[-1], "latest_window": f"{months[-ROLL]}..{months[-1]}"}
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
    P, rf, chosen = load_french()
    E = load_etfs()
    res = {"generated": "2026-11-03", "columns": chosen, "costs_pct_per_year": COSTS, "roll_months": ROLL}

    # sleeves (gross) and their net versions
    P["V+M"] = mix(P, {"VAL10": .5, "MOM10": .5})
    P["BIG V+M"] = mix(P, {"BIG-VAL": .5, "BIG-MOM": .5})
    P["V+M+Q"] = mix(P, {"VAL10": 1 / 3, "MOM10": 1 / 3, "QUAL10": 1 / 3})
    P["BIG V+M+Q"] = mix(P, {"BIG-VAL": 1 / 3, "BIG-MOM": 1 / 3, "BIG-QUAL": 1 / 3})
    P["BIG V+Q"] = mix(P, {"BIG-VAL": .5, "BIG-QUAL": .5})
    drag = dict(COSTS)
    drag["V+M"] = (COSTS["VAL10"] + COSTS["MOM10"]) / 2
    drag["BIG V+M"] = (COSTS["BIG-VAL"] + COSTS["BIG-MOM"]) / 2
    drag["V+M+Q"] = (COSTS["VAL10"] + COSTS["MOM10"] + COSTS["QUAL10"]) / 3
    drag["BIG V+M+Q"] = (COSTS["BIG-VAL"] + COSTS["BIG-MOM"] + COSTS["BIG-QUAL"]) / 3
    drag["BIG V+Q"] = (COSTS["BIG-VAL"] + COSTS["BIG-QUAL"]) / 2
    NET = {}
    for k, c in drag.items():
        NET[k + " net"] = {m: v - c / 100 / 12 for m, v in P[k].items()}
    res["drag_pct_per_year"] = drag

    # 1. French long-only portfolios vs the market, by era (gross and net)
    names = ["MOM10", "VAL10", "QUAL10", "V+M", "V+M+Q", "BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+Q",
             "BIG V+M+Q", "VAL+QUAL", "MOM1", "VAL1", "BIG-LOMOM", "BIG-GROWTH"]
    res["french"] = {}
    for era, (lo, hi) in ERAS.items():
        res["french"][era] = {}
        for k in names + [n for n in NET]:
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
    for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "MOM10", "VAL10", "V+M", "VAL+QUAL"]:
        ms = common(P[k], P["MKT"], rf)
        res["decades"][k] = decades(P[k], P["MKT"], ms)
        res["rolling"][k] = rolling_series(P[k], P["MKT"], ms)

    # 3. live ETFs vs SPY on each fund's own window (net of fees, real)
    E["MTUM+VLUE"] = mix(E, {"MTUM": .5, "VLUE": .5})
    E["QVAL+QMOM"] = mix(E, {"QVAL": .5, "QMOM": .5})
    E["VFMO+VFVA"] = mix(E, {"VFMO": .5, "VFVA": .5})
    E["SPMO+VLUE"] = mix(E, {"SPMO": .5, "VLUE": .5})
    res["etfs"] = {}
    for t in ["MTUM", "VLUE", "MTUM+VLUE", "SPMO", "SPMO+VLUE", "QVAL", "QMOM", "QVAL+QMOM", "VFMO", "VFVA", "VFMO+VFVA",
              "VTV", "IWD", "IWF", "QQQ", "RSP", "IVAL", "IMOM", "ARKG", "XBI", "IBB", "GNOM"]:
        ms = common(E[t], E["SPY"], rf)
        ms = ms[1:] if ms else ms                   # the first month of a new fund is partial
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
    # French BIG rows on the ETF window, for the gross-vs-net gap
    res["french_on_etf_window"] = {}
    for k in ["BIG-MOM", "BIG-VAL", "BIG V+M", "MOM10", "VAL10"]:
        ms2 = common(P[k], E["SPY"], rf, lo=ms[0], hi=ms[-1])
        res["french_on_etf_window"][k] = stats(P[k], E["SPY"], rf, ms2)

    # 4. blends: SPY + x of the big V+M sleeve (net), 1993- and 2010-
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
        for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q"]:
            ms = common(P[k], P["MKT"], rf, lo=lo, hi=hi)
            c = cagr([P[k][m] for m in ms])
            row[k] = {"cagr": c, "excess": c - cagr([P["MKT"][m] for m in ms]), "n": len(ms), "from": ms[0]}
        for k in ["MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM"]:
            ms = common(E[k], E["SPY"], rf, lo=lo, hi=hi)
            if ms and ms[0] == min(E[k]):
                ms = ms[1:]                              # a fund's first return month is partial
            if len(ms) < 12:
                continue
            c = cagr([E[k][m] for m in ms])
            row[k] = {"cagr": c, "excess": c - cagr([E["SPY"][m] for m in ms]), "n": len(ms), "from": ms[0]}
        ms = common(P["MKT"], lo=lo, hi=hi)
        row["MKT"] = {"cagr": cagr([P["MKT"][m] for m in ms]), "n": len(ms), "from": ms[0]}
        res["rally"][label] = row

    # 5. paths for the exhibit
    def path(src, lo, hi=END):
        ms = common(src, lo=lo, hi=hi)
        return {"months": ms, "levels": [round(v, 5) for v in levels([src[m] for m in ms])]}

    res["paths"] = {
        "A": {k: path(P[k], "1963-07") for k in ["MKT", "BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q"]},
        "A_net": {k: path(NET[k + " net"], "1963-07") for k in ["BIG-MOM", "BIG-VAL", "BIG V+M", "BIG V+M+Q"]},
        "C": {k: path(E[k], "2013-06") for k in ["SPY", "QQQ", "MTUM", "VLUE", "MTUM+VLUE"]},
        "D": {k: path(E[k], "2014-12") for k in ["SPY", "ARKG", "XBI", "IBB"]},
    }
    # drawdown series, market vs big V+M (gross), 1963-
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
        return (f"  {k:14s} {st['cagr']:7.1%} {st['vol']:6.1%} {st['sharpe']:6.2f} {st['maxdd']:7.1%} "
                f"{st['excess_cagr']:+7.1%} {st['te']:6.1%} {st['beta']:5.2f} {st['years_beating']:3d}/{st['years']:<3d}"
                + (f" {r10['share_positive']:5.0%} {r10['worst']:+6.1%} {r10['latest']:+6.1%}" if r10 else ""))

    hdr = "                   CAGR    vol Sharpe   maxDD  excess     TE  beta  yrs>mkt  10y>0 worst10 last10"
    for era in ERAS:
        print(f"\n== French long-only, {era} (gross; 'net' = less the assumed drag) ==")
        print(hdr)
        F = res["french"][era]
        print(row("MKT", F["MKT"]))
        for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+Q", "BIG V+M+Q", "VAL+QUAL", "MOM10", "VAL10", "QUAL10", "V+M", "V+M+Q",
                  "BIG V+M net", "BIG V+M+Q net", "BIG-MOM net", "BIG-VAL net", "MOM1", "VAL1", "BIG-LOMOM", "BIG-GROWTH"]:
            if k in F:
                print(row(k, F[k]))
    s = res["spy_vs_mkt"]
    print(f"\nSPY vs CRSP market {s['from']}..{s['to']}: SPY {s['cagr']:.2%} vs market {s['bench_cagr']:.2%}, corr {s['corr']:.3f}")
    print("\n== live ETFs vs SPY, each on its own window (net of fees) ==")
    print("                   CAGR    vol Sharpe   maxDD  excess     TE  beta  yrs>spy   window")
    for t, st in res["etfs"].items():
        print(row(t, st) + f"   {st['from']}..{st['to']}  SPY {st['bench_cagr']:.1%}")
    print(f"\n== live ETFs on one window {res['etfs_common']['window']} ==")
    for t in core:
        print(row(t, res["etfs_common"][t]))
    print("\n== French BIG rows on that window (gross) ==")
    for k, st in res["french_on_etf_window"].items():
        print(row(k, st) + f"  {st['from']}..{st['to']}")
    print("\n== blends SPY + x sleeve (net) ==")
    for era, d in res["blends"].items():
        for sleeve, rows in d.items():
            print(f"  {era} {sleeve:14s} " + "  ".join(f"x={x}: {v['cagr']:.1%}/{v['sharpe']:.2f}/{v['maxdd']:.0%}" for x, v in rows.items()))
    print("\n== the 2025-26 value rally: excess CAGR vs market / SPY, windows stopped at 2024-12 vs through 2026-09 ==")
    keys = ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM"]
    print("  " + " " * 12 + "".join(f"{w:>18s}" for w in res["rally"]))
    print("  " + f"{'market CAGR':12s}" + "".join(f"{res['rally'][w]['MKT']['cagr']:>18.1%}" for w in res["rally"]))
    for k in keys:
        print(f"  {k:12s}" + "".join(f"{res['rally'][w][k]['excess']:>+18.1%}" if k in res["rally"][w] else f"{'':>18s}" for w in res["rally"]))
    print("\n== decades, excess CAGR vs market (gross) ==")
    ds = sorted({d for k in res["decades"] for d in res["decades"][k]})
    print("  " + " " * 12 + "".join(f"{d:>8s}" for d in ds))
    for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "MOM10", "VAL10"]:
        print(f"  {k:12s}" + "".join(f"{res['decades'][k][d]['excess']:+8.1%}" if d in res["decades"][k] else f"{'':>8s}" for d in ds))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
