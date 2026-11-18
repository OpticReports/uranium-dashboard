"""Q2: where the harvester's return comes from, real era (Composer backtest weights x total returns).
Usage: python3 q2_attrib.py DATA_DIR"""
import json, math, random, sys
import lib

D = sys.argv[1]; C = D + "/cache"
bt = lib.load_bt(D + "/bt_HARV.json"); ds = bt["dates"]
F = ("ZVOL", "VXZ", "PULS")
TR = {t: lib.rets(lib.series(t, C, "adj")) for t in F}
bil = lib.rets(lib.series("BIL", C, "adj"))
days = ds[1:]                                            # return days
W = {t: [bt["w"][t].get(ds[i - 1], 0.0) for i in range(1, len(ds))] for t in F}      # weight held into the day
R = {t: [TR[t].get(d, 0.0) for d in days] for t in F}
gross = [sum(W[t][i] * R[t][i] for t in F) for i in range(len(days))]
net = [bt["ret"][d] for d in days]
cash = [R["PULS"][i] for i in range(len(days))]
tb = [bil.get(d, 0.0) for d in days]
n = len(days); yrs = n / 252.0
turn = sum(sum(abs(W[t][i] - W[t][i - 1]) for t in F) for i in range(1, n)) / 2 / yrs       # one-way, x per year
out = {"window": [days[0], days[-1], n],
       "gross": lib.stats(gross, tb), "net_composer": lib.stats(net, tb), "cash_puls": lib.stats(cash), "tbills": lib.stats(tb),
       "one_way_turnover_per_year": turn,
       "cost_drag_per_year": lib.stats(gross)["cagr"] - lib.stats(net)["cagr"]}
# by leg, by year: sum of weight x return (arithmetic contribution)
leg = {}
for t in F:
    for i, d in enumerate(days):
        y = d[:4]
        leg.setdefault(t, {}).setdefault(y, 0.0); leg[t][y] += W[t][i] * R[t][i]
        leg[t]["all"] = leg[t].get("all", 0.0) + W[t][i] * R[t][i]
out["leg_contribution"] = leg
# excess of each leg over cash on the same dollars: w * (r - r_cash)
out["leg_excess_over_cash"] = {t: sum(W[t][i] * (R[t][i] - cash[i]) for i in range(n)) for t in ("ZVOL", "VXZ")}
out["avg_weight"] = {t: sum(W[t]) / n for t in F}
out["days_held"] = {t: sum(1 for x in W[t] if x > 1e-9) for t in F}
# static mix at average weights, rebalanced daily
static = [sum(out["avg_weight"][t] * R[t][i] for t in F) for i in range(n)]
out["static_mix"] = lib.stats(static, tb)
out["timing_gain_arith"] = sum(gross) - sum(static)
# conditional mean return of each fund on days held vs all days
out["fund_mean_bps"] = {t: {"when_held": 1e4 * sum(W[t][i] * R[t][i] for i in range(n)) / max(1e-12, sum(W[t])),
                            "all_days": 1e4 * sum(R[t]) / n} for t in F}
# placebo: circular shifts of the whole weight path against the return path
rng = random.Random(20261118)
obs = sum(gross)
shifts = [k for k in range(20, n - 20)]
sh = []
for k in shifts:
    sh.append(sum(sum(W[t][(i + k) % n] * R[t][i] for t in F) for i in range(n)))
out["placebo_circular_shift"] = {"n": len(sh), "observed_sum": obs, "mean": sum(sh) / len(sh),
                                 "p_one_sided": sum(1 for x in sh if x >= obs) / len(sh),
                                 "p95": sorted(sh)[int(.95 * len(sh))], "max": max(sh)}
# per leg placebo
for t in ("ZVOL", "VXZ"):
    o = sum(W[t][i] * (R[t][i] - cash[i]) for i in range(n))
    s2 = [sum(W[t][(i + k) % n] * (R[t][i] - cash[i]) for i in range(n)) for k in shifts]
    out["placebo_circular_shift"][t] = {"observed": o, "mean": sum(s2) / len(s2), "p_one_sided": sum(1 for x in s2 if x >= o) / len(s2)}
# sign-flipped rule (mirror): hold VXZ where it holds ZVOL and ZVOL where it holds VXZ
mirror = [W["ZVOL"][i] * R["VXZ"][i] + W["VXZ"][i] * R["ZVOL"][i] + W["PULS"][i] * R["PULS"][i] for i in range(n)]
out["mirror_rule"] = lib.stats(mirror, tb)
# ZVOL-leg days: carry vs curve change from Cboe settlements
panel = lib.vx_panel(C); mt = lib.midterm_index(panel)
car = cur = tot = 0.0; nd = 0
for i, d in enumerate(days):
    if W["ZVOL"][i] <= 1e-9 or d not in mt or days[i - 1] not in mt:
        continue
    p = mt[days[i - 1]]                                # yesterday's curve and weights
    F4, F5, F6, F7 = p["F"]
    # roll-down for a holder of the long index if the curve does not move: each contract slides one day
    # toward the next-nearer one. Approximate slope per day from the 4th-7th month spread (3 months ~ 63 sessions)
    slope_per_day = (F7 - F4) / 63.0 / ((F4 + F5 + F6 + F7) / 4.0)
    carry_short = slope_per_day                         # the short earns the roll-down in contango
    r_short = -mt[d]["ret"]
    car += W["ZVOL"][i] * carry_short; cur += W["ZVOL"][i] * (r_short - carry_short); tot += W["ZVOL"][i] * R["ZVOL"][i]; nd += 1
out["zvol_leg_carry_vs_curve"] = {"days": nd, "carry": car, "curve_change": cur, "fund_total": tot}
# unconditional carry of the short mid-term position, real era, per year
c_all = [(mt[days[i - 1]]["F"][3] - mt[days[i - 1]]["F"][0]) / 63.0 / (sum(mt[days[i - 1]]["F"]) / 4.0) for i in range(1, n) if days[i - 1] in mt]
out["midterm_carry_all_days_per_year"] = 252 * sum(c_all) / len(c_all)
json.dump(out, open("out/q2_attrib.json", "w"), indent=1)
r4 = lambda x: round(x, 4) if isinstance(x, float) else x
for k, v in out.items():
    print(k, json.dumps(v, default=str) if not isinstance(v, dict) else json.dumps({a: (r4(b) if not isinstance(b, dict) else {c: r4(e) for c, e in b.items()}) for a, b in v.items()}))
