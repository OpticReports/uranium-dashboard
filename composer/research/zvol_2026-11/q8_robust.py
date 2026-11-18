"""Robustness checks added after the two counter-agent reviews (2026-11-18). NOT pre-registered; each one
answers a reviewer's objection and is labelled as such in the report.
(a) sub-periods of the long path, with and without bills            (reviewer B, S3)
(b) acting one close late; cost per trade from 5 to 30 bps           (B, S4)
(c) live ZVOL fills against the official close                       (B, S4)
(d) the plain trigger: RSI(SPY,2) < 25 alone                          (B, minor)
(e) "is it better than T-bills" with the harvester at other paces   (B, S2)
(f) break-even switcher pace for moving HARV into KMLM; live vol     (B, S1)
(g) exposure on the worst short-volatility days; after-spike return against the usual 10 days (B, S5)
(h) trailing one-year return in excess of bills                      (B, S3)
Usage: python3 q8_robust.py DATA_DIR REPO_COMPOSER_DIR"""
import json, math, random, sys
import lib, sim
import q4_books as q4

D, REPO = sys.argv[1], sys.argv[2]; C = D + "/cache"
P = sim.panel(D); out = {}
base = sim.run(P, cost_bps=5.0)
days = base["days"]; tb = [P["BIL"][d] for d in days]
def seg(r, a, b, days=days):
    idx = [i for i, d in enumerate(days) if a <= d <= b]
    x = [r[i] for i in idx]; t = [P["BIL"][days[i]] for i in idx]
    s = lib.stats(x, t)
    return {"n": len(x), "cagr": s["cagr"], "sharpe": s["sharpe"], "maxdd": s["maxdd"], "bills": lib.stats(t)["cagr"], "excess_cagr": s["cagr"] - lib.stats(t)["cagr"]}
SP = [("2006-07..2009", "2006-07-03", "2009-12-31"), ("2010..2019", "2010-01-01", "2019-12-31"), ("2020..2023-04-18", "2020-01-01", "2023-04-18"),
      ("2023-04-19..2025", "2023-04-19", "2025-12-31"), ("2026 to 11-17", "2026-01-01", "2026-11-17"),
      ("all before ZVOL, without 2008", None, None), ("all before ZVOL", "2006-07-03", "2023-04-18")]
out["subperiods"] = {}
for nm, a, b in SP:
    if a is None:
        idx = [i for i, d in enumerate(days) if d <= "2023-04-18" and d[:4] != "2008"]
        x = [base["ret"][i] for i in idx]; t = [tb[i] for i in idx]; s = lib.stats(x, t)
        out["subperiods"][nm] = {"n": len(x), "cagr": s["cagr"], "sharpe": s["sharpe"], "maxdd": s["maxdd"], "bills": lib.stats(t)["cagr"], "excess_cagr": s["cagr"] - lib.stats(t)["cagr"]}
    else:
        out["subperiods"][nm] = seg(base["ret"], a, b)
# (b) lag and cost
out["lag"] = {}
for lg in (0, 1):
    r = sim.run(P, cost_bps=5.0, lag=lg)
    W = [w["ZVOL"] for w in r["w"]]
    for nm, a, b in (("all before ZVOL", "2006-07-03", "2023-04-18"), ("real era", "2023-04-19", "2026-11-17"), ("2010..2019", "2010-01-01", "2019-12-31")):
        idx = [i for i, d in enumerate(r["days"]) if a <= d <= b]
        s = lib.stats([r["ret"][i] for i in idx], [P["BIL"][r["days"][i]] for i in idx])
        held = sum(W[i] for i in idx)
        out["lag"][f"{nm} | lag {lg}"] = {"cagr": s["cagr"], "sharpe": s["sharpe"], "maxdd": s["maxdd"],
                                          "zvol_bps_when_held": 1e4 * sum(W[i] * P["ZVOL"][r["days"][i]] for i in idx) / max(held, 1e-12)}
out["cost"] = {}
for c in (0, 5, 10, 15, 20, 30):
    r = sim.run(P, cost_bps=float(c))
    out["cost"][c] = {nm: seg(r["ret"], a, b, r["days"])["cagr"] for nm, a, b in (("all before ZVOL", "2006-07-03", "2023-04-18"), ("real era", "2023-04-19", "2026-11-17"))}
# (c) live ZVOL fills against the official close
fills = json.load(open(REPO + "/results/slippage-ledger.json"))["fills"]
zc = lib.series("ZVOL", C, "close"); rows = []
for f in fills.values():
    if f.get("t") == "ZVOL" and f.get("d") in zc:
        rows.append({"d": f["d"], "side": f["side"], "bps_worse_than_close": f["side"] * (f["fill"] / zc[f["d"]] - 1) * 1e4, "notional": abs(f.get("notional") or 0.0), "hhmm": f.get("hhmm")})
x = sorted(r["bps_worse_than_close"] for r in rows); n = len(x)
out["zvol_fills_vs_close"] = {"n": n, "median_bps": x[n // 2] if n else None, "mean_bps": sum(x) / n if n else None,
                              "notional_weighted_bps": (sum(r["bps_worse_than_close"] * r["notional"] for r in rows) / max(1e-9, sum(r["notional"] for r in rows))) if n else None,
                              "share_adverse": sum(1 for v in x if v > 0) / n if n else None, "one_cent_bps_at_6.46": 1 / 6.46 * 100,
                              "sd_bps": (math.sqrt(sum((v - sum(x) / n) ** 2 for v in x) / (n - 1)) if n > 1 else None)}
fc = sim.run(P, fund_cost={"ZVOL": 14.0, "VXZ": 3.0, "PULS": 0.0, "SVXY": 14.0})
out["cost"]["ZVOL 14 / VXZ 3 / PULS 0"] = {nm: seg(fc["ret"], a, b, fc["days"])["cagr"] for nm, a, b in (("all before ZVOL", "2006-07-03", "2023-04-18"), ("real era", "2023-04-19", "2026-11-17"))}
# (d) the plain trigger
allp = P["days"]; hits = {"pre": [], "real": []}; everyday = {"pre": [], "real": []}
for i in range(1, len(allp)):
    d0, d1 = allp[i - 1], allp[i]; k = "pre" if d1 <= "2023-04-18" else "real"
    everyday[k].append(P["ZVOL"][d1])
    x = P["rsi"][2].get(d0)
    if x is not None and x < 25:
        hits[k].append(P["ZVOL"][d1])
out["plain_trigger"] = {k: {"days": len(v), "share_of_days": len(v) / len(everyday[k]), "zvol_bps_next_day": 1e4 * sum(v) / len(v), "all_days_bps": 1e4 * sum(everyday[k]) / len(everyday[k])} for k, v in hits.items()}
# (e) book E against KEEP with the harvester at other paces (switcher at its live pace)
LA = "haircut (a): switcher at its live pace"; sh = q4.LENSES[LA]
hv_real = lib.stats(q4.R["HARV"])["cagr"]
rng = random.Random(20261118); paths = [lib.stationary_bootstrap_idx(q4.n, 10, rng) for _ in range(1000)]
allidx = list(range(q4.n)); out["bills_vs_harvester"] = {}
for nm, target in (("as measured 2023-26", hv_real), ("long-run pace before ZVOL", out["subperiods"]["all before ZVOL"]["cagr"] - out["subperiods"]["all before ZVOL"]["bills"] + lib.stats(q4.R["BIL"])["cagr"]),
                   ("2010-19 pace", out["subperiods"]["2010..2019"]["cagr"] - out["subperiods"]["2010..2019"]["bills"] + lib.stats(q4.R["BIL"])["cagr"])):
    hs = math.log(1 + target) / 252.0 - sum(math.log(1 + v) for v in q4.R["HARV"]) / q4.n
    kb = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], allidx, sh, hs), q4.R["BIL"])
    eb = q4.metrics(q4.book_rets(q4.BOOKS["E  HARV -> T-bills"], allidx, sh, hs), q4.R["BIL"])
    ab = q4.metrics(q4.book_rets(q4.BOOKS["A  HARV -> KMLM symphony"], allidx, sh, hs), q4.R["BIL"])
    de, da, dd = [], [], []
    for p in paths:
        t = [q4.R["BIL"][i] for i in p]
        k2 = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], p, sh, hs), t)
        de.append(q4.metrics(q4.book_rets(q4.BOOKS["E  HARV -> T-bills"], p, sh, hs), t)["cagr"] - k2["cagr"])
        a2 = q4.metrics(q4.book_rets(q4.BOOKS["A  HARV -> KMLM symphony"], p, sh, hs), t)
        da.append(a2["cagr"] - k2["cagr"]); dd.append(a2["maxdd"] - k2["maxdd"])
    q = lambda v: [sorted(v)[int(.05 * len(v))], sorted(v)[int(.95 * len(v))]]
    out["bills_vs_harvester"][nm] = {"harvester_cagr": target, "E_minus_KEEP_cagr": [eb["cagr"] - kb["cagr"]] + q(de), "A_minus_KEEP_cagr": [ab["cagr"] - kb["cagr"]] + q(da),
                                     "A_minus_KEEP_maxdd": [ab["maxdd"] - kb["maxdd"]] + q(dd),
                                     "usd_per_year_over_bills_on_37.5k": 37541 * (target - lib.stats(q4.R["BIL"])["cagr"])}
# (f) break-even switcher pace for A to match KEEP on CAGR; live-volatility lens
def gap(target, hs=0.0):
    s2 = q4.shift_for(target)
    return q4.metrics(q4.book_rets(q4.BOOKS["A  HARV -> KMLM symphony"], allidx, s2, hs), q4.R["BIL"])["cagr"] - q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], allidx, s2, hs), q4.R["BIL"])["cagr"]
def breakeven(hs):
    lo, hi = -0.5, 3.0
    for _ in range(50):
        m = (lo + hi) / 2
        if gap(m, hs) > 0: hi = m
        else: lo = m
    return m
hs_long = math.log(1 + out["bills_vs_harvester"]["long-run pace before ZVOL"]["harvester_cagr"]) / 252.0 - sum(math.log(1 + v) for v in q4.R["HARV"]) / q4.n
out["breakeven_switcher_cagr"] = {"harvester as measured": breakeven(0.0), "harvester at its long-run pace": breakeven(hs_long)}
q1 = json.load(open("out/q1_live.json")); live_vol = q1["HARV"]["live_stats"]["switcher"]["vol"]; model_vol = lib.stats(q4.R["SWITCHER"])["vol"]
sc = live_vol / model_vol
def shift_scaled(target):
    lg = sum(math.log(max(1e-9, 1 + x * sc)) for x in q4.R["SWITCHER"]) / q4.n
    return math.log(1 + target) / 252.0 - lg
out["live_vol_lens"] = {"model_vol": model_vol, "live_vol": live_vol, "scale": sc}
for nm, tgt in (("live pace", q4.live_ann), ("half the live pace", q4.live_ann / 2)):
    s3 = shift_scaled(tgt)
    k3 = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], allidx, s3, 0.0, sc), q4.R["BIL"]); a3 = q4.metrics(q4.book_rets(q4.BOOKS["A  HARV -> KMLM symphony"], allidx, s3, 0.0, sc), q4.R["BIL"])
    out["live_vol_lens"][nm] = {"keep": k3, "A": a3}
# (g) exposure on the 40 worst short-vol days; after-spike against the usual 10 sessions
worst = sorted(range(len(days)), key=lambda i: P["ZVOL"][days[i]])[:40]
out["worst_short_vol_days"] = {"n": 40, "held_zvol_on": sum(1 for i in worst if base["w"][i]["ZVOL"] > 1e-9), "avg_weight": sum(base["w"][i]["ZVOL"] for i in worst) / 40,
                               "avg_weight_all_days": sum(w["ZVOL"] for w in base["w"]) / len(days), "worst_rule_days": sorted((base["ret"][i], days[i]) for i in range(len(days)))[:5]}
ten = {"pre": [], "real": []}
for i in range(0, len(days) - 10):
    ten["pre" if days[i + 10] <= "2023-04-18" else "real"].append(math.prod(1 + base["ret"][i + k] for k in range(1, 11)) - 1)
out["usual_10_sessions"] = {k: sum(v) / len(v) for k, v in ten.items()}
# (h) trailing one-year return in excess of bills
ex = [(1 + a) / (1 + b) - 1 for a, b in zip(base["ret"], tb)]
roll = [(days[i - 1], math.prod(1 + x for x in ex[i - 252:i]) - 1) for i in range(252, len(days) + 1)]
last = roll[-1][1]; prior = [v for d, v in roll if d < "2023-04-19"]; allw = [v for _, v in roll]
out["rolling_excess_1y"] = {"last": last, "pctile_pre_ZVOL": sum(1 for v in prior if v <= last) / len(prior), "pctile_all": sum(1 for v in allw if v <= last) / len(allw),
                            "share_negative_pre_ZVOL": sum(1 for v in prior if v < 0) / len(prior), "median_pre_ZVOL": sorted(prior)[len(prior) // 2]}
# (i) other destinations and a half move (switcher at its live pace), against KEEP
ALT = {"F  HARV -> pro rata to HG / KMLM / SLEEVE": (.29 + .15 * .29 / .85, .29 + .15 * .29 / .85, .27 + .15 * .27 / .85, 0, 0, 0),
       "G  half of HARV -> KMLM symphony": (.29, .365, .27, .075, 0, 0),
       "H  HARV -> SLEEVE": (.29, .29, .42, 0, 0, 0), "I  HARV -> HG": (.44, .29, .27, 0, 0, 0)}
out["other_destinations"] = {}
kb = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], allidx, sh), q4.R["BIL"])
for nm, w in ALT.items():
    b = q4.metrics(q4.book_rets(w, allidx, sh), q4.R["BIL"]); dc, dd, ds = [], [], []
    for p in paths:
        t = [q4.R["BIL"][i] for i in p]
        k2 = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], p, sh), t); b2 = q4.metrics(q4.book_rets(w, p, sh), t)
        dc.append(b2["cagr"] - k2["cagr"]); dd.append(b2["maxdd"] - k2["maxdd"]); ds.append(b2["sharpe"] - k2["sharpe"])
    q = lambda v: [sorted(v)[int(.05 * len(v))], sorted(v)[int(.95 * len(v))]]
    out["other_destinations"][nm] = {"cagr": b["cagr"], "maxdd": b["maxdd"], "sharpe": b["sharpe"], "d_cagr": [b["cagr"] - kb["cagr"]] + q(dc),
                                     "d_maxdd": [b["maxdd"] - kb["maxdd"]] + q(dd), "d_sharpe": [b["sharpe"] - kb["sharpe"]] + q(ds)}
out["actual_weights"] = {"HARV_share_of_book": 37541 / 320694, "harvester_total_share": (37541 + 0.24 * 96437) / 320694}
json.dump(out, open("out/q8_robust.json", "w"), indent=1, default=str)
pc = lambda x: f"{x:+.1%}"
for k, v in out["subperiods"].items(): print(f"{k:32s} n {v['n']:5d} net {pc(v['cagr'])} excess {pc(v['excess_cagr'])} Sharpe {v['sharpe']:.2f} maxDD {v['maxdd']:.0%}")
for k, v in out["lag"].items(): print(f"{k:28s} net {pc(v['cagr'])} Sharpe {v['sharpe']:.2f} ZVOL bps/held day {v['zvol_bps_when_held']:.0f}")
print("cost:", {k: {a: pc(b) for a, b in v.items()} for k, v in out["cost"].items()})
print("fills:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out["zvol_fills_vs_close"].items()})
print("plain trigger:", out["plain_trigger"])
for k, v in out["bills_vs_harvester"].items(): print(f"{k:28s} harvester {pc(v['harvester_cagr'])} | E-KEEP {pc(v['E_minus_KEEP_cagr'][0])} [{pc(v['E_minus_KEEP_cagr'][1])}, {pc(v['E_minus_KEEP_cagr'][2])}] | A-KEEP {pc(v['A_minus_KEEP_cagr'][0])} [{pc(v['A_minus_KEEP_cagr'][1])}, {pc(v['A_minus_KEEP_cagr'][2])}] dDD {pc(v['A_minus_KEEP_maxdd'][0])} [{pc(v['A_minus_KEEP_maxdd'][1])}, {pc(v['A_minus_KEEP_maxdd'][2])}] | $/yr over bills {v['usd_per_year_over_bills_on_37.5k']:,.0f}")
print("breakeven:", {k: pc(v) for k, v in out["breakeven_switcher_cagr"].items()})
print("live-vol lens: scale", round(sc, 2), {k: (pc(v["keep"]["cagr"]), f"DD {v['keep']['maxdd']:.1%}", pc(v["A"]["cagr"]), f"DD {v['A']['maxdd']:.1%}") for k, v in out["live_vol_lens"].items() if isinstance(v, dict)})
for k, v in out["other_destinations"].items(): print(f"{k:42s} CAGR {pc(v['cagr'])} DD {v['maxdd']:.1%} | dCAGR {pc(v['d_cagr'][0])} [{pc(v['d_cagr'][1])}, {pc(v['d_cagr'][2])}] dDD {pc(v['d_maxdd'][0])} [{pc(v['d_maxdd'][1])}, {pc(v['d_maxdd'][2])}] dSharpe {v['d_sharpe'][0]:+.2f} [{v['d_sharpe'][1]:+.2f}, {v['d_sharpe'][2]:+.2f}]")
print("worst days:", out["worst_short_vol_days"]); print("usual 10:", out["usual_10_sessions"]); print("rolling excess:", out["rolling_excess_1y"])
