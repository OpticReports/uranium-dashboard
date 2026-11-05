#!/usr/bin/env python3
"""Study 2 (results.md addendum 53 follow-up): does an overnight EXIT rule gated on the held fund NOT
being oversold help KMLM and HG? Addendum 53 found every unconditional exit rule loses because bad
overnights after oversold closes are followed by better sessions; its edge section's intersection
block showed the cell the overlay never tested: a -5% own gap when the fund was NOT oversold (RSI(10)
>= 30 at the prior close) ran -0.92% open-to-close (t -2.5, n 208, SOXL/TECL/TQQQ, one trade per day,
2010-26) - an in-sample cell from the same data, and one that contained the 2026-11-05 morning itself
on a half-day print (ex 11-05: n 207, -0.86%, t -2.3; the panel below stops at 11-04).

Reuses the add. 53 harness unchanged: overnight_study.py (load_paths, mornings, apply, evaluate with
the 2,000-draw same-side placebo, 15 + 10 bps, MIN_W, START 2015-06-01) and edge_study.py (wilder_rsi
on adjusted closes - the engines' RSI - mornings_all, tstat with the sample sd, the family-wise
permutation test).

1. Engine-path rules (KMLM, HG), exit the leveraged long at the 09:30 open: own gap <= -3/-5/-8% and
   sector gap <= -1/-2%, each ungated (add. 53) and gated on the held fund's RSI(10) at the prior
   close >= 30 / 40 / 50, the converse (< 30), no fund in the engine's dip-buy list oversold (the
   tree's thresholds), none of the five 3x funds oversold (add. 53's definition), the leg being a
   switcher pick rather than a dip-buy branch, and the three gates together; plus the gap-up mirrors:
   51 rules per engine. Two family-wise permutation p over all 51 (max t over the family, 4,000
   draws): by ROW (shuffle the per-fire exit gains across the eligible mornings; two legs held on the
   same day count twice) and by DAY (the unit is the day, its value the mean gain over that day's
   eligible legs; a rule's t is over its fire-days). Both are on the engine's per-fire gain t, not the
   leg's open-to-close t. Costs 15 + 10 (add. 53), 25 + 15, gross, 50 + 50 and 80 + 80 (add. 53's
   stressed-open fills); leave-one-year-out for the candidate rules.
2. Model-free panel: every 2x/3x long and inverse fund in daily.json, 2010-01-01..2026-11-04 (the
   engine window's last day; 11-05, the morning that prompted the study, is excluded so the panel and
   the engine share a window), open-to-close by gap bucket x RSI(10) state at the prior close (< 30 /
   30-50 / >= 50, >= 30 = the gate, >= 70 as the mirror): n, mean, t, win rate; per fund, pooled by
   rows, and pooled one-trade-per-day (the honest t).
3. The 2026-11-05 case: what each gate definition does with the morning that prompted the study, on
   the live holding (the shadow ledger's 11-04 KMLM row) and on the tree's 16:00-close target.
Ex-distribution mornings (raw vs adjusted day return differ by > 5 bps: the phantom gaps add. 53's
counter-agent flagged) are excluded from firing and from the placebo pool.
Writes composer/results/conditioned-exits-2026-11-05.json. Usage: conditioned_exits.py [--quick] [--out PATH]
"""
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overnight_study as os_  # noqa: E402
import edge_study as es  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "conditioned-exits-2026-11-05.json")
LEDGER = os.path.join(HERE, "..", "..", "results", "monitor", "shadow-ledger.jsonl")
PANEL_START = "2010-01-01"
PANEL_END = "2026-11-04"          # the engine window's last day; 2026-11-05 (the morning that prompted the study) stays out
NOV05 = "2026-11-05"
LONG_LEV = {"SOXL": "SMH", "TECL": "XLK", "TQQQ": "QQQ", "SPXL": "SPY", "LABU": "XBI", "UPRO": "SPY", "UDOW": "SPY", "SSO": "SPY",
            "QLD": "QQQ", "FAS": "SPY", "TNA": "IWM", "USD": "SMH"}
LEV2X = {"SSO", "QLD", "USD"}
INV_LEV = {"SOXS": "SMH", "SQQQ": "QQQ", "SPXS": "SPY", "TZA": "IWM"}
FIVE = ("SOXL", "TECL", "TQQQ", "SPXL", "LABU")                      # add. 53's "no fund oversold" set
DIPBUY = {"KMLM": {"TQQQ": 30, "SOXL": 30, "SPXL": 30, "LABU": 25},  # the trees' dip-buy triggers (fixtures/approved)
          "HG": {"TQQQ": 30}}
HG_SWITCHER = {"TQQQ", "UPRO", "UDOW", "SSO", "TNA"}                  # HG: "top 1 by RSI" momentum leg
HG_DIP = {"TECL", "QLD", "LABU", "USD", "SMH"}                        # HG: "bottom 1 by RSI" when TQQQ RSI(10) < 30
GAP_BUCKETS = [("<= -8%", -1.0, -0.08), ("-8..-5%", -0.08, -0.05), ("-5..-3%", -0.05, -0.03), ("-3..-1%", -0.03, -0.01),
               ("-1..+1%", -0.01, 0.01), ("+1..+3%", 0.01, 0.03), ("+3..+5%", 0.03, 0.05), ("+5..+8%", 0.05, 0.08), ("> +8%", 0.08, 9.0)]
RSI_STATES = [("<30", 0, 30), ("30-50", 30, 50), (">=50", 50, 101), (">=30", 30, 101), (">=70", 70, 101), ("all", 0, 101)]
PHANTOM = 5e-4
PERM_N = 4000
COSTS = [(15, 10), (25, 15), (0, 0), (50, 50), (80, 80)]
ROBUST_RULES = ("gap <= -8% & held RSI >= 30", "gap <= -8% & held RSI >= 40", "gap <= -8% & held RSI >= 50")


# ------------------------------------------------------------------ helpers
def rsi_table(D, funds, field="a"):
    """{fund: {date: RSI(10) at that close}} on adjusted closes (field "c": raw), edge_study's Wilder implementation"""
    out = {}
    for f in funds:
        if f not in D:
            continue
        ks = es.keys(D, f)
        r = es.wilder_rsi([D[f][d][field] for d in ks], 10)
        out[f] = {d: v for d, v in zip(ks, r) if v is not None}
    return out


def adj_day(D, f, d, prev):
    a1, a0 = D[f][d].get("a"), D[f][prev].get("a")
    return a1 / a0 - 1 if a1 and a0 else None


def stats(x):
    if not x:
        return {"n": 0}
    m = statistics.mean(x)
    return {"n": len(x), "mean": m, "median": statistics.median(x), "t": es.tstat(x), "win": sum(1 for v in x if v > 0) / len(x),
            "sd": statistics.stdev(x) if len(x) > 1 else None}


def costed(path, rows, fire, exit_bps, reentry_bps, start=os_.START):
    """dCAGR / dMaxDD / per-fire gain at other cost assumptions, same mechanics as evaluate (no placebo)"""
    sel = [i for i, d in enumerate(path["days"]) if d >= start]
    full, fires = os_.apply(path, rows, fire, "exit", exit_bps=exit_bps, reentry_bps=reentry_bps)
    rets = [full[i] for i in sel]
    base = [path["rets"][i] for i in sel]
    sv = [f["saved"] for f in fires]
    return {"n": len(fires), "n_days": len({f["date"] for f in fires}), "saved_mean": statistics.mean(sv) if sv else None, "t_saved": es.tstat(sv),
            "hit": (sum(1 for v in sv if v > 0) / len(sv)) if sv else None,
            "delta_cagr": os_.cagr(rets) - os_.cagr(base), "delta_maxdd": os_.maxdd(rets) - os_.maxdd(base)}


# ------------------------------------------------------------------ engine rows
def engine_rows(D, e, path, R):
    """add. 53's morning rows (long legs, weight >= MIN_W) plus the prior close's RSI state, the
    dip-buy triggers, the leg type, and the phantom-gap flag"""
    rows = [r for r in os_.mornings(D, path) if r["side"] == "long"]
    trig = DIPBUY[e]
    for r in rows:
        f, d = r["fund"], r["date"]
        prev = os_.prev_day(D[f], d)
        r["prev"] = prev
        r["rsi"] = R[f].get(prev)
        ad = adj_day(D, f, d, prev)
        r["phantom"] = ad is None or abs(ad - r["day"]) > PHANTOM
        trig_state = {t: R.get(t, {}).get(prev) for t in trig}
        r["dip_trigger"] = any(trig_state[t] is not None and trig_state[t] < thr for t, thr in trig.items())
        r["trig_rsi"] = trig_state
        r["any5"] = any(R[t].get(prev) is not None and R[t][prev] < 30 for t in FIVE)
        if e == "KMLM":
            r["leg"] = "dip" if r["w"] >= 0.7 else "switcher"
        else:
            r["leg"] = "switcher" if f in HG_SWITCHER else ("dip" if f in HG_DIP else "other")
    return rows


def leg_check(e, rows):
    """do the leg labels agree with the trees' triggers at the prior close (my RSI vs the engine's)?"""
    out = {}
    if e == "KMLM":
        tests = {"TECL dip (TQQQ RSI<30)": lambda r: r["leg"] == "dip" and r["fund"] == "TECL", "SOXL dip (SOXL RSI<30, TQQQ>=30)": lambda r: r["leg"] == "dip" and r["fund"] == "SOXL",
                 "switcher legs (no trigger)": lambda r: r["leg"] == "switcher"}
        checks = {"TECL dip (TQQQ RSI<30)": lambda r: (r["trig_rsi"]["TQQQ"] or 99) < 30,
                  "SOXL dip (SOXL RSI<30, TQQQ>=30)": lambda r: (r["trig_rsi"]["SOXL"] or 99) < 30 and (r["trig_rsi"]["TQQQ"] or 99) >= 30,
                  "switcher legs (no trigger)": lambda r: not r["dip_trigger"]}
    else:
        tests = {"dip legs (TQQQ RSI<30)": lambda r: r["leg"] == "dip", "switcher legs": lambda r: r["leg"] == "switcher"}
        checks = {"dip legs (TQQQ RSI<30)": lambda r: (r["trig_rsi"]["TQQQ"] or 99) < 30, "switcher legs": lambda r: not r["dip_trigger"]}
    for k, sel in tests.items():
        rs = [r for r in rows if sel(r)]
        out[k] = {"n": len(rs), "agree": sum(1 for r in rs if checks[k](r)), "share": (sum(1 for r in rs if checks[k](r)) / len(rs)) if rs else None}
    return out


SIGNALS = {"gap <= -3%": lambda r: r["gap"] <= -0.03, "gap <= -5%": lambda r: r["gap"] <= -0.05, "gap <= -8%": lambda r: r["gap"] <= -0.08,
           "sector gap <= -1%": lambda r: r["sec_gap"] is not None and r["sec_gap"] <= -0.01,
           "sector gap <= -2%": lambda r: r["sec_gap"] is not None and r["sec_gap"] <= -0.02}
GATES = {"ungated (add. 53)": lambda r: True,
         "held RSI >= 30": lambda r: r["rsi"] >= 30, "held RSI >= 40": lambda r: r["rsi"] >= 40, "held RSI >= 50": lambda r: r["rsi"] >= 50,
         "held RSI < 30 (converse)": lambda r: r["rsi"] < 30,
         "no dip-buy trigger oversold": lambda r: not r["dip_trigger"],
         "no 3x fund oversold": lambda r: not r["any5"],
         "switcher leg": lambda r: r["leg"] == "switcher",
         "RSI >= 30 & no trigger & switcher": lambda r: r["rsi"] >= 30 and not r["dip_trigger"] and r["leg"] == "switcher"}
# the mirror (control): exit the long on a gap UP, gated on the fund NOT being overbought
MIRRORS = {"MIRROR gap >= +5%": lambda r: r["gap"] >= 0.05, "MIRROR gap >= +8%": lambda r: r["gap"] >= 0.08}
MIRROR_GATES = {"ungated": lambda r: True, "held RSI <= 70": lambda r: r["rsi"] <= 70, "held RSI > 70 (converse)": lambda r: r["rsi"] > 70}


def family_perm(rows, rule_sets, obs_t, perm_n=PERM_N):
    """edge_study's family-wise test on the engine rows, by ROW: shuffle the per-fire exit gains
    (15 + 10 bps) across the eligible mornings, keep each rule's row set, record the max t over the
    family. Two legs held on the same day are two units."""
    vals = [r["saved"] for r in rows]
    idx = {k: [i for i in s] for k, s in rule_sets.items()}
    maxts = []
    for _ in range(perm_n):
        random.shuffle(vals)
        mt = max((es.tstat([vals[i] for i in ix]) or 0.0) for ix in idx.values())
        maxts.append(mt)
    maxts.sort()
    return {"perm_n": perm_n, "null_max_t_p50": maxts[len(maxts) // 2], "null_max_t_p95": maxts[int(0.95 * len(maxts))],
            "p_fw": {k: (sum(1 for m in maxts if m >= obs_t[k]) / len(maxts)) if obs_t[k] is not None else None for k in rule_sets}}


def family_perm_days(rows, rule_sets, perm_n=PERM_N, seed=20261106):
    """the same test by DAY (counter-agent review2, fix 3): the unit is the eligible day, its value
    the mean per-fire exit gain over the legs held that day; a rule's observed t is over the mean gain
    of its fired legs on each of its fire-days; the null shuffles the day values across the eligible
    days and keeps each rule's day set. Own RNG so the row-level numbers above are untouched."""
    rng = random.Random(seed)
    days = sorted({r["date"] for r in rows})
    pos = {d: i for i, d in enumerate(days)}
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r["saved"])
    vals = [statistics.mean(by_day[d]) for d in days]
    didx, obs = {}, {}
    for k, ix in rule_sets.items():
        per = {}
        for i in ix:
            per.setdefault(rows[i]["date"], []).append(rows[i]["saved"])
        obs[k] = es.tstat([statistics.mean(v) for v in per.values()])
        didx[k] = sorted(pos[d] for d in per)
    maxts = []
    for _ in range(perm_n):
        rng.shuffle(vals)
        maxts.append(max((es.tstat([vals[i] for i in ix]) or 0.0) for ix in didx.values()))
    maxts.sort()
    return {"perm_n": perm_n, "n_days": len(days), "null_max_t_p50": maxts[len(maxts) // 2], "null_max_t_p95": maxts[int(0.95 * len(maxts))],
            "t_day": obs, "n_days_fired": {k: len(v) for k, v in didx.items()},
            "p_fw_day": {k: (sum(1 for m in maxts if m >= obs[k]) / len(maxts)) if obs[k] is not None else None for k in rule_sets}}


def robustness(path, rows, fire):
    """leave-one-year-out, without 2026 (the live year), without the three carrying episodes (counter-agent review2)"""
    yrs = sorted({r["date"][:4] for r in rows if fire(r)})
    loyo = {y: costed(path, rows, lambda r, y=y: fire(r) and r["date"][:4] != y, os_.EXIT_BPS, os_.REENTRY_BPS) for y in yrs}
    return {"leave_one_year_out": loyo, "ex_2026": loyo.get("2026"),
            "ex_2020_2025_2026": costed(path, rows, lambda r: fire(r) and r["date"][:4] not in ("2020", "2025", "2026"), os_.EXIT_BPS, os_.REENTRY_BPS)}


def run_engine(D, e, path, R):
    rows = engine_rows(D, e, path, R)
    n_all = len(rows)
    n_phantom = sum(1 for r in rows if r["phantom"])
    n_norsi = sum(1 for r in rows if r["rsi"] is None)
    rows = [r for r in rows if not r["phantom"] and r["rsi"] is not None]
    # the per-row exit gain at 15 + 10 bps (for the permutation test), from the harness's own mechanics
    _, fires = os_.apply(path, rows, lambda r: True, "exit")
    sv = {(f["date"], f["fund"]): f["saved"] for f in fires}
    for r in rows:
        r["saved"] = sv[(r["date"], r["fund"])]
    sel = [i for i, d in enumerate(path["days"]) if d >= os_.START]
    base = [path["rets"][i] for i in sel]
    E = {"from": path["days"][sel[0]], "to": path["days"][-1], "sessions": len(sel), "base": os_.summary(base),
         "long_mornings_all": n_all, "excluded_phantom": n_phantom, "excluded_no_rsi": n_norsi, "long_mornings": len(rows),
         "funds": {}, "legs": {}, "leg_check": leg_check(e, rows), "rules": {}, "states": {}}
    for r in rows:
        E["funds"][r["fund"]] = E["funds"].get(r["fund"], 0) + 1
        E["legs"][r["leg"]] = E["legs"].get(r["leg"], 0) + 1
    # the state table: what the legs did open-to-close by gap bucket x held-RSI state (the engine's own mornings)
    for gname, lo, hi in GAP_BUCKETS:
        E["states"][gname] = {}
        for sname, slo, shi in RSI_STATES:
            x = [r["intra"] for r in rows if lo < r["gap"] <= hi and slo <= r["rsi"] < shi]
            E["states"][gname][sname] = stats(x)
    sv_all = [r["saved"] for r in rows]
    E["saved_dist"] = dict(stats(sv_all), min=min(sv_all), max=max(sv_all), n_abs_gt_10pct=sum(1 for v in sv_all if abs(v) > 0.10),
                           two_leg_days=sum(1 for r in rows if sum(1 for q in rows if q["date"] == r["date"]) > 1))
    # the rules
    rule_sets, obs_t, fire_fns = {}, {}, {}
    combos = [(s, g) for s in SIGNALS for g in GATES] + [(s, g) for s in MIRRORS for g in MIRROR_GATES]
    for sname, gname in combos:
        sf, gf = (SIGNALS.get(sname) or MIRRORS[sname]), (GATES.get(gname) if sname in SIGNALS else MIRROR_GATES[gname])
        name = f"{sname} & {gname}"
        fire = lambda r, sf=sf, gf=gf: sf(r) and gf(r)
        fired = [r for r in rows if fire(r)]
        ev = os_.evaluate(path, rows, fire, "exit")
        intra = [r["intra"] for r in fired]
        v = {"signal": sname, "gate": gname, "n": len(fired), "n_days": len({r["date"] for r in fired}), "intra": stats(intra),
             "t_saved": es.tstat([r["saved"] for r in fired]),
             "saved_mean": ev["saved_mean"], "hit": ev["hit_rate"], "delta_cagr": ev["delta_cagr"], "delta_sharpe": ev["delta_sharpe"],
             "delta_maxdd": ev["delta_maxdd"], "placebo": ev.get("placebo"), "by_year": ev["by_year"],
             "share_dip_leg": (sum(1 for r in fired if r["leg"] == "dip") / len(fired)) if fired else None,
             "share_two_leg_days": (sum(1 for r in fired if sum(1 for q in fired if q["date"] == r["date"]) > 1) / len(fired)) if fired else None,
             "worst_fire": ev["worst_fire"], "best_fire": ev["best_fire"],
             "costs": {f"{a}+{b}": costed(path, rows, fire, a, b) for a, b in COSTS}}
        E["rules"][name] = v
        rule_sets[name] = [i for i, r in enumerate(rows) if fire(r)]
        obs_t[name] = v["t_saved"]
        fire_fns[name] = fire
    fam = family_perm(rows, rule_sets, obs_t)
    famd = family_perm_days(rows, rule_sets)
    for name in E["rules"]:
        E["rules"][name]["p_fw"] = fam["p_fw"][name]
        E["rules"][name]["t_saved_day"] = famd["t_day"][name]
        E["rules"][name]["p_fw_day"] = famd["p_fw_day"][name]
    E["family"] = {k: v for k, v in fam.items() if k != "p_fw"}
    E["family"]["rules"] = list(E["rules"])
    E["family"]["days"] = {k: v for k, v in famd.items() if k not in ("t_day", "p_fw_day", "n_days_fired")}
    E["robustness"] = {name: robustness(path, rows, fire_fns[name]) for name in ROBUST_RULES if name in fire_fns and E["rules"][name]["n"] >= 5}
    # every fire of the gated gap rules, for the record (date, fund, gap, open-to-close, the engine's net gain)
    E["fires"] = {}
    for name, v in E["rules"].items():
        if v["gate"] in ("held RSI >= 30", "held RSI >= 40") and v["signal"] in ("gap <= -5%", "gap <= -8%"):
            sf, gf = SIGNALS[v["signal"]], GATES[v["gate"]]
            E["fires"][name] = [[r["date"], r["fund"], round(r["w"], 3), round(r["rsi"], 1), round(r["gap"], 4), round(r["intra"], 4), round(r["saved"], 4)] for r in rows if sf(r) and gf(r)]
    return E


# ------------------------------------------------------------------ the panel
def panel(D, R):
    funds = dict(LONG_LEV)
    funds.update(INV_LEV)
    rows = es.mornings_all(D, funds)
    out = {"start": PANEL_START, "end": PANEL_END, "funds": {}, "pooled": {}, "pooled_daily": {}, "n": {}}
    clean = []
    n_ph = 0
    for r in rows:
        if r["date"] < PANEL_START or r["date"] > PANEL_END:
            continue
        prev = os_.prev_day(D[r["fund"]], r["date"])
        ad = adj_day(D, r["fund"], r["date"], prev)
        if ad is None or abs(ad - r["day"]) > PHANTOM:
            n_ph += 1
            continue
        clean.append(r)
    out["n"] = {"rows": len(clean), "phantom_excluded": n_ph, "excluded_after_end": sum(1 for r in rows if r["date"] > PANEL_END)}

    def grid(rs, daily=False):
        g = {}
        for gname, lo, hi in GAP_BUCKETS:
            g[gname] = {}
            for sname, slo, shi in RSI_STATES:
                q = [r for r in rs if lo < r["gap"] <= hi and slo <= r["rsi"] < shi]
                if daily:
                    by_day = {}
                    for r in q:
                        by_day.setdefault(r["date"], []).append(r["intra"])
                    x = [statistics.mean(v) for v in by_day.values()]
                else:
                    x = [r["intra"] for r in q]
                g[gname][sname] = stats(x)
        return g
    groups = {"long 3x (9)": [f for f in LONG_LEV if f not in LEV2X], "long 2x (SSO QLD USD)": sorted(LEV2X), "long all 12": list(LONG_LEV),
              "inverse 3x (SOXS SQQQ SPXS TZA)": list(INV_LEV), "SOXL TECL TQQQ (add. 53 cell)": ["SOXL", "TECL", "TQQQ"]}
    for gname, fs in groups.items():
        rs = [r for r in clean if r["fund"] in fs]
        out["pooled"][gname] = grid(rs)
        out["pooled_daily"][gname] = grid(rs, daily=True)
    for f in list(LONG_LEV) + list(INV_LEV):
        rs = [r for r in clean if r["fund"] == f]
        out["funds"][f] = {"n": len(rs), "from": rs[0]["date"] if rs else None, "to": rs[-1]["date"] if rs else None, "grid": grid(rs)}
    # the add. 53 intersection cell, reproduced with its own conventions (from launch, one trade per day, 30 bps) as a
    # pipeline check. add. 53's figure (n 208, -0.92%, t -2.45) was computed on a half-day 2026-11-05 print and CONTAINS
    # that morning; on the 16:00 closes the same cell reads lower, and without 11-05 it is n 207 (review2 fix 1)
    tech = [r for r in rows if r["fund"] in ("SOXL", "TECL", "TQQQ")]
    os_by_day = {}
    for r in rows:
        if r["fund"] in FIVE and r["oversold"]:
            os_by_day.setdefault(r["date"], set()).add(r["fund"])

    def add53_cell(rs):
        chk = es.daily_trades(rs, lambda r: r["gap"] <= -0.05 and not r["oversold"] and not os_by_day.get(r["date"]))
        return {"n": len(chk), "mean": statistics.mean(t["ret"] for t in chk), "t": es.tstat([t["ret"] for t in chk]),
                "has_1105": any(t["date"] == NOV05 for t in chk)}
    out["add53_cell_check"] = {"published": {"n": 208, "mean": -0.0092, "t": -2.45, "basis": "add. 53's figure, computed on a half-day 2026-11-05 print, includes that morning"},
                               "incl_1105_final_closes": add53_cell(tech), "ex_1105": add53_cell([r for r in tech if r["date"] <= PANEL_END])}
    # the same cell 2010-01..2026-11-04, gross, phantom-free, per fund and one-per-day
    cell = [r for r in clean if r["fund"] in ("SOXL", "TECL", "TQQQ") and r["gap"] <= -0.05 and r["rsi"] >= 30 and not os_by_day.get(r["date"])]
    cell_days = {}
    for r in cell:
        cell_days.setdefault(r["date"], []).append(r["intra"])
    out["cell_2010"] = {"rows": stats([r["intra"] for r in cell]), "daily": stats([statistics.mean(v) for v in cell_days.values()]),
                        "by_fund": {f: stats([r["intra"] for r in cell if r["fund"] == f]) for f in ("SOXL", "TECL", "TQQQ")},
                        "by_year": {}}
    for r in cell:
        out["cell_2010"]["by_year"].setdefault(r["date"][:4], []).append(r["intra"])
    out["cell_2010"]["by_year"] = {y: stats(v) for y, v in sorted(out["cell_2010"]["by_year"].items())}
    return out


# ------------------------------------------------------------------ the 2026-11-05 case
def close_for_rsi(D, f, d, target=30.0):
    """the close on d at which the fund's RSI(10) on adjusted closes would read exactly target"""
    ks = es.keys(D, f)
    c = [D[f][k]["a"] for k in ks[:ks.index(d) + 1]]
    lo, hi = c[-1] * 0.8, c[-1] * 1.2
    for _ in range(60):
        mid = (lo + hi) / 2
        if es.wilder_rsi(c[:-1] + [mid], 10)[-1] < target:
            lo = mid
        else:
            hi = mid
    return hi


def nov05_case(D, R, Rraw):
    """the morning that prompted the study (outside the engine window): the close read vs the 15:54 read
    on the shadow ledger, and what each gate definition does with it at the nominal tree weights,
    15 bps at the open, re-entry not counted"""
    d, prev = NOV05, PANEL_END
    led = None
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("date") == prev and j.get("engine") == "KMLM":
                led = j
    out = {"date": d, "decision_close": prev, "ledger": ({k: led.get(k) for k in ("live", "target", "status", "edge", "src")} if led else None), "funds": {}}
    for f in FIVE:
        gi = os_.gap_intraday(D, f, d)
        out["funds"][f] = {"rsi_adj": R[f].get(prev), "rsi_raw": Rraw[f].get(prev), "gap": gi["gap"], "intra": gi["intra"], "day": gi["day"]}
    c30 = close_for_rsi(D, "SOXL", prev)
    out["soxl_close_for_rsi30"] = {"close": D["SOXL"][prev]["a"], "close_at_rsi30": c30, "pct_from_actual": c30 / D["SOXL"][prev]["a"] - 1}
    S, T = out["funds"]["SOXL"], out["funds"]["TECL"]
    trig = {t: R[t].get(prev) for t in DIPBUY["KMLM"]}
    no_trigger = not any(trig[t] is not None and trig[t] < thr for t, thr in DIPBUY["KMLM"].items())

    def row(gate, holding, fund, w, fires, note):
        g = out["funds"][fund]
        # exit_gain_pp: the symphony's gain from exiting at the open vs riding the leg (None when the gate does not fire);
        # rode_pp: what the leg cost the symphony close-to-close when the gate does not fire
        return {"gate": gate, "holding": holding, "fund": fund, "w": w, "fires": bool(fires), "gap": g["gap"], "intra": g["intra"], "leg_cc": g["day"],
                "exit_gain_pp": (w * (g["gap"] - os_.EXIT_BPS / 1e4) - w * g["day"]) if fires else None, "rode_pp": None if fires else w * g["day"], "note": note}
    out["gates"] = [
        row("switcher leg (the engine's own leg weight: 0.375 = switcher pick, 0.75 = dip-buy)", "live: SOXL 0.75 dip-buy on the 15:54 read", "SOXL", 0.75, False,
            "no RSI feed needed; the live leg was a dip-buy, so no fire"),
        row("own RSI(10) >= 30 on the 16:00 close read", "live: SOXL 0.75 dip-buy", "SOXL", 0.75, S["rsi_adj"] >= 30 and S["gap"] <= -0.08,
            f"SOXL RSI {S['rsi_adj']:.1f} at the close (RSI 30 sits {abs(out['soxl_close_for_rsi30']['pct_from_actual']):.2%} below it)"),
        row("no dip-buy trigger oversold on the 16:00 close read", "live: SOXL 0.75 dip-buy", "SOXL", 0.75, no_trigger and S["gap"] <= -0.08,
            "triggers at the close: " + ", ".join(f"{t} {v:.1f}" for t, v in trig.items())),
        row("the path's own 16:00 logic: gap <= -8% & RSI >= 30 on SOXL", "tree target: SOXL 0.375 + TECL 0.375", "SOXL", 0.375, S["rsi_adj"] >= 30 and S["gap"] <= -0.08,
            "would be the largest fire in the sample; not out of sample (it prompted the study): fire #1 of the execution log"),
        row("the path's own 16:00 logic: gap <= -5% & RSI >= 30 on TECL", "tree target: SOXL 0.375 + TECL 0.375", "TECL", 0.375, T["rsi_adj"] >= 30 and T["gap"] <= -0.05,
            f"TECL RSI {T['rsi_adj']:.1f} at the close")]
    return out


# ------------------------------------------------------------------ main
def main():
    global OUT
    quick = "--quick" in sys.argv
    if "--out" in sys.argv:
        OUT = sys.argv[sys.argv.index("--out") + 1]
    if quick:
        os_.PLACEBO_N = 100
    D = os_.load_daily()
    P = os_.load_paths()
    need = set(LONG_LEV) | set(INV_LEV) | set(FIVE) | {t for e in DIPBUY for t in DIPBUY[e]}
    R = rsi_table(D, need)
    Rraw = rsi_table(D, FIVE, field="c")
    random.seed(20261105)
    res = {"generated": "2026-11-05", "start": os_.START, "exit_bps": os_.EXIT_BPS, "reentry_bps": os_.REENTRY_BPS, "min_w": os_.MIN_W,
           "placebo_n": os_.PLACEBO_N, "perm_n": PERM_N, "phantom_threshold": PHANTOM, "costs": [f"{a}+{b}" for a, b in COSTS],
           "panel_window": [PANEL_START, PANEL_END], "dipbuy_triggers": DIPBUY, "signals": list(SIGNALS), "gates": list(GATES), "engines": {}}
    if os.path.exists(os_.BRIDGE):
        B = json.load(open(os_.BRIDGE))
        res["bridge_0925_vs_open"] = {t: {"median": v["vs_open"]["09:25"]["median"], "sd": v["vs_open"]["09:25"]["sd"], "sessions": v["sessions"]} for t, v in B.items() if "09:25" in v["vs_open"]}
    for e in ("KMLM", "HG"):
        res["engines"][e] = run_engine(D, e, P[e], R)
        print(f"{e} done", flush=True)
    res["panel"] = panel(D, R)
    res["nov05"] = nov05_case(D, R, Rraw)
    json.dump(res, open(OUT, "w"), indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)

    # ---- console
    for e, E in res["engines"].items():
        b = E["base"]
        print(f"\n===== {e}: {E['from']}..{E['to']}; as built CAGR {b['cagr']:.1%} Sharpe {b['sharpe']:.2f} maxDD {b['maxdd']:.0%}; {E['long_mornings']} eligible long mornings "
              f"(of {E['long_mornings_all']}; {E['excluded_phantom']} ex-distribution, {E['excluded_no_rsi']} no RSI) {E['funds']} legs {E['legs']}")
        print("  leg check:", {k: f"{v['agree']}/{v['n']}" for k, v in E["leg_check"].items()})
        print(f"  {'rule':52s} {'n':>4s} {'days':>4s} {'leg O->C':>9s} {'t leg':>6s} {'hit':>4s} {'per fire':>9s} {'t gain':>6s} {'dCAGR':>7s} {'dMaxDD':>7s} {'plc pct':>7s} {'p_fw':>5s} {'p_day':>5s} {'25+15':>7s} {'gross':>7s} {'50+50':>7s} {'dip%':>4s}")
        for name, v in E["rules"].items():
            pl = v["placebo"] or {}
            print(f"  {name:52s} {v['n']:4d} {v['n_days']:4d} {(v['intra'].get('mean') or 0):+9.2%} {(v['intra'].get('t') or 0):+6.2f} {(v['hit'] or 0):4.0%} {(v['saved_mean'] or 0):+9.2%} {(v['t_saved'] or 0):+6.2f} {v['delta_cagr']:+7.1%} {v['delta_maxdd']:+7.1%} "
                  f"{(pl.get('percentile_of_actual') if pl else float('nan')):7.0%} {(v['p_fw'] if v['p_fw'] is not None else float('nan')):5.2f} {(v['p_fw_day'] if v['p_fw_day'] is not None else float('nan')):5.2f} "
                  f"{v['costs']['25+15']['delta_cagr']:+7.1%} {v['costs']['0+0']['delta_cagr']:+7.1%} {v['costs']['50+50']['delta_cagr']:+7.1%} {(v['share_dip_leg'] or 0):4.0%}")
        fd = E["family"]["days"]
        print(f"  family null max t by row: p50 {E['family']['null_max_t_p50']:.2f} p95 {E['family']['null_max_t_p95']:.2f}; by day ({fd['n_days']} eligible days): p50 {fd['null_max_t_p50']:.2f} p95 {fd['null_max_t_p95']:.2f}")
        for name, rb in E["robustness"].items():
            v = E["rules"][name]
            print(f"  robustness {name}: t gain row {v['t_saved']:+.2f} / day {v['t_saved_day']:+.2f} on {v['n_days']} fire-days; LOYO dCAGR " +
                  ", ".join(f"ex-{y} {x['delta_cagr']:+.1%} (t {(x['t_saved'] or 0):+.2f}, n {x['n']}, helped {(x['hit'] or 0):.0%})" for y, x in rb["leave_one_year_out"].items()) +
                  f"; ex 2020/25/26: n {rb['ex_2020_2025_2026']['n']}, {rb['ex_2020_2025_2026']['delta_cagr']:+.1%}, helped {(rb['ex_2020_2025_2026']['hit'] or 0):.0%}; "
                  f"costs 50+50 {v['costs']['50+50']['delta_cagr']:+.1%} (t {(v['costs']['50+50']['t_saved'] or 0):.2f}), 80+80 {v['costs']['80+80']['delta_cagr']:+.1%} (t {(v['costs']['80+80']['t_saved'] or 0):.2f})")
        print("  states (gap bucket x held RSI), mean O->C / n:")
        for g, row in E["states"].items():
            print(f"    {g:9s} " + "  ".join(f"{s}: {(c.get('mean') or 0):+6.2%} n{c['n']:3d}" for s, c in row.items()))
    Pn = res["panel"]
    ck = Pn["add53_cell_check"]
    print(f"\n===== panel {Pn['start']}..{Pn['end']}: {Pn['n']['rows']} fund-mornings ({Pn['n']['phantom_excluded']} ex-distribution excluded, {Pn['n']['excluded_after_end']} after {Pn['end']}); "
          f"add. 53 cell check: published n 208 -0.92% t -2.45 (half-day 11-05 inside); on final closes incl. 11-05 n {ck['incl_1105_final_closes']['n']} {ck['incl_1105_final_closes']['mean']:+.2%} t {ck['incl_1105_final_closes']['t']:+.2f}; "
          f"ex 11-05 n {ck['ex_1105']['n']} {ck['ex_1105']['mean']:+.2%} t {ck['ex_1105']['t']:+.2f}")
    for grp in ("long all 12", "SOXL TECL TQQQ (add. 53 cell)", "inverse 3x (SOXS SQQQ SPXS TZA)"):
        for pool, key in (("rows pooled", "pooled"), ("one per day", "pooled_daily")):
            print(f"  {grp} ({pool}; mean O->C, t, n):")
            for g, row in list(Pn[key][grp].items())[:3]:
                print(f"    {g:9s} " + "  ".join(f"{s}: {(c.get('mean') or 0):+6.2%} t{(c.get('t') or 0):+5.1f} n{c['n']:4d}" for s, c in row.items()))
    N5 = res["nov05"]
    print(f"\n===== {N5['date']} (decided at the {N5['decision_close']} close): ledger {N5['ledger']}")
    for f, v in N5["funds"].items():
        print(f"  {f}: RSI(10) adj {v['rsi_adj']:.3f} raw {v['rsi_raw']:.3f}; gap {v['gap']:+.2%} O->C {v['intra']:+.2%} day {v['day']:+.2%}")
    c = N5["soxl_close_for_rsi30"]
    print(f"  SOXL close {c['close']:.2f}; RSI = 30 at {c['close_at_rsi30']:.2f} ({c['pct_from_actual']:+.2%})")
    for g in N5["gates"]:
        eff = f"exit gain {g['exit_gain_pp']:+.1%} of the symphony" if g["fires"] else f"rode {g['fund']} {g['leg_cc']:+.1%} c-c ({g['rode_pp']:+.1%} of the symphony)"
        print(f"  {g['gate']:78s} {g['holding']:40s} fires {str(g['fires']):5s} {eff}  | {g['note']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
