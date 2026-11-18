"""Q4: counterfactual books. Real era from Composer backtests (net of Composer's 5 bps), live window from
the live symphony series. Usage: python3 q4_books.py DATA_DIR"""
import datetime as dt, json, math, random, sys
import lib

D = sys.argv[1]; C = D + "/cache"
E = {k: lib.load_bt(f"{D}/bt_{k}.json") for k in ("HG", "KMLM", "SLEEVE", "HARV", "SWITCHER")}
bil = lib.rets(lib.series("BIL", C, "adj"))
days = [d for d in E["HARV"]["dates"][1:] if all(d in E[k]["ret"] for k in E)]
SLEEVE_FUNDS = ("ZVOL", "VXZ", "PULS")
kd = E["KMLM"]["dates"]
wsw = {}                                           # switcher's share of the KMLM symphony held into day d
for i in range(1, len(kd)):
    w = {t: m.get(kd[i - 1], 0.0) for t, m in E["KMLM"]["w"].items()}
    tot = sum(v for t, v in w.items() if not t.startswith("$")) or 1.0
    wsw[kd[i]] = sum(v for t, v in w.items() if t not in SLEEVE_FUNDS and not t.startswith("$")) / tot
R = {k: [E[k]["ret"][d] for d in days] for k in E}
R["BIL"] = [bil.get(d, 0.0) for d in days]; WS = [wsw[d] for d in days]
n = len(days)
# books: weights on (HG, KMLM symphony, SLEEVE, HARV, SWITCHER, BIL)
BOOKS = {"KEEP 29/29/27/15": (.29, .29, .27, .15, 0, 0),
         "A  HARV -> KMLM symphony": (.29, .44, .27, 0, 0, 0),
         "B  HARV -> pure switcher": (.29, .29, .27, 0, .15, 0),
         "C  strip the VIX sleeve only": (.29, 0, .27, .15, .29, 0),
         "D  no harvester anywhere": (.29, 0, .27, 0, .44, 0),
         "E  HARV -> T-bills": (.29, .29, .27, 0, 0, .15)}
ORDER = ("HG", "KMLM", "SLEEVE", "HARV", "SWITCHER", "BIL")


def shift_for(target_cagr):
    """constant daily log-return shift that brings the switcher's real-era CAGR to target (vol kept)"""
    lg = sum(math.log(1 + x) for x in R["SWITCHER"]) / n
    return math.log(1 + target_cagr) / 252.0 - lg


def book_rets(wts, idx, shift):
    out = []
    for i in idx:
        sw = (1 + R["SWITCHER"][i]) * math.exp(shift) - 1
        km = R["KMLM"][i] + WS[i] * ((1 + R["SWITCHER"][i]) * (math.exp(shift) - 1))      # only its switcher part is cut
        v = {"HG": R["HG"][i], "KMLM": km, "SLEEVE": R["SLEEVE"][i], "HARV": R["HARV"][i], "SWITCHER": sw, "BIL": R["BIL"][i]}
        out.append(sum(w * v[k] for w, k in zip(wts, ORDER)))
    return out


def metrics(r, tb):
    s = lib.stats(r, tb)
    # worst calendar-month-length (21 session) return
    w21 = min(math.prod(1 + x for x in r[i:i + 21]) - 1 for i in range(0, max(1, len(r) - 20)))
    return {"cagr": s["cagr"], "vol": s["vol"], "sharpe": s["sharpe"], "maxdd": s["maxdd"], "cvar5": s["cvar5"], "worst21": w21, "worst_day": s["worst"]}


live_sw = json.load(open("out/q1_live.json"))["KMLM"]["part_twr"]["switcher"]
live_ann = (1 + live_sw[0]) ** (252.0 / live_sw[1]) - 1
LENSES = {"as-measured": 0.0, "haircut (a): switcher at its live pace": shift_for(live_ann), "haircut (b): half of that": shift_for(live_ann / 2)}
out = {"window": [days[0], days[-1], n], "switcher_live_annualised": live_ann,
       "switcher_backtest_cagr": lib.stats(R["SWITCHER"])["cagr"], "lenses": {}, "engines": {k: metrics(R[k], R["BIL"]) for k in E},
       "corr": {a + "/" + b: lib.corr(R[a], R[b]) for a in E for b in E if a < b}}
rng = random.Random(20261118)
paths = [lib.stationary_bootstrap_idx(n, 10, rng) for _ in range(2000)]
allidx = list(range(n))
for ln, sh in LENSES.items():
    res = {}
    base = {b: metrics(book_rets(w, allidx, sh), R["BIL"]) for b, w in BOOKS.items()}
    diffs = {b: {m: [] for m in ("cagr", "sharpe", "maxdd", "cvar5")} for b in BOOKS if not b.startswith("KEEP")}
    for p in paths:
        tb = [R["BIL"][i] for i in p]
        mk = None
        for b, w in BOOKS.items():
            m = metrics(book_rets(w, p, sh), tb)
            if b.startswith("KEEP"):
                mk = m
            else:
                for q in diffs[b]:
                    diffs[b][q].append(m[q] - mk[q])
    for b in BOOKS:
        res[b] = {"point": base[b]}
        if b in diffs:
            res[b]["vs_keep"] = {q: {"point": base[b][q] - base["KEEP 29/29/27/15"][q], "lo": sorted(v)[int(.05 * len(v))], "hi": sorted(v)[int(.95 * len(v))],
                                     "share_above_0": sum(1 for x in v if x > 0) / len(v)} for q, v in diffs[b].items()}
    out["lenses"][ln] = res

# live window: actual symphony returns since HARV was funded
live = json.load(open(D + "/live.json"))
def lser(k):
    v = live[k]; ds = [dt.datetime.fromtimestamp(m / 1000, tz=dt.timezone.utc).date().isoformat() for m in v["epoch_ms"]]
    return {ds[i]: v["deposit_adjusted_series"][i] / v["deposit_adjusted_series"][i - 1] - 1 for i in range(1, len(ds)) if ds[i] <= lib.END}
L = {k: lser(k) for k in ("HG", "KMLM", "SLEEVE", "HARV")}
ld = sorted(d for d in L["HARV"] if all(d in L[k] for k in L))
q1 = json.load(open("out/q1_live.json"))
# HARV on a total-return basis: spread the distributions paid outside over their ex-dates
harv_tr = dict(L["HARV"])
hv = live["HARV"]; hds = [dt.datetime.fromtimestamp(m / 1000, tz=dt.timezone.utc).date().isoformat() for m in hv["epoch_ms"]]
hval = dict(zip(hds, hv["series"]))
for d, t, usd in q1["HARV"]["distribution_rows"]:
    i = hds.index(d)
    harv_tr[d] = harv_tr.get(d, 0.0) + usd / hval[hds[i - 1]]
sw_live = {}
# switcher part of live KMLM: rebuilt in q1 (holdings x total returns); re-derive here from the backtest weights
sw_bt = E["SWITCHER"]["ret"]
lv = {}
for b, w in BOOKS.items():
    for basis, hr in (("displayed", L["HARV"]), ("with distributions", harv_tr)):
        r = [w[0] * L["HG"][d] + w[1] * L["KMLM"][d] + w[2] * L["SLEEVE"][d] + w[3] * hr[d] + w[4] * sw_bt.get(d, 0.0) + w[5] * bil.get(d, 0.0) for d in ld]
        lv.setdefault(b, {})[basis] = {"total": math.prod(1 + x for x in r) - 1, "maxdd": lib.stats(r)["maxdd"], "worst_day": min(r), "vol": lib.stats(r)["vol"]}
out["live_window"] = {"from": ld[0], "to": ld[-1], "n": len(ld), "books": lv,
                      "note": "pure-switcher returns in books B, C, D are the model's (Composer backtest) on those dates; every other engine is live"}
json.dump(out, open("out/q4_books.json", "w"), indent=1)
pc = lambda x: f"{x:+.1%}"
print("window", out["window"], "| switcher backtest CAGR", pc(out["switcher_backtest_cagr"]), "| live annualised", pc(live_ann))
print("engines:", {k: (pc(v["cagr"]), f"Sh {v['sharpe']:.2f}", f"DD {v['maxdd']:.1%}") for k, v in out["engines"].items()})
print("corr:", {k: round(v, 3) for k, v in out["corr"].items()})
for ln, res in out["lenses"].items():
    print("==", ln)
    for b, v in res.items():
        p = v["point"]; s = f"  {b:30s} CAGR {pc(p['cagr'])} vol {p['vol']:.1%} Sharpe {p['sharpe']:.2f} maxDD {p['maxdd']:.1%} CVaR5 {p['cvar5']:.2%} worst21 {pc(p['worst21'])} worst day {pc(p['worst_day'])}"
        if "vs_keep" in v:
            k = v["vs_keep"]; s += f" | dCAGR {pc(k['cagr']['point'])} [{pc(k['cagr']['lo'])}, {pc(k['cagr']['hi'])}] | dSharpe {k['sharpe']['point']:+.2f} [{k['sharpe']['lo']:+.2f}, {k['sharpe']['hi']:+.2f}] | dMaxDD {k['maxdd']['point']:+.1%} [{k['maxdd']['lo']:+.1%}, {k['maxdd']['hi']:+.1%}]"
        print(s)
print("== live", out["live_window"]["from"], out["live_window"]["to"], out["live_window"]["n"])
for b, v in lv.items():
    print(f"  {b:30s}", {k: (pc(x["total"]), f"DD {x['maxdd']:.1%}", f"worst {pc(x['worst_day'])}") for k, x in v.items()})
