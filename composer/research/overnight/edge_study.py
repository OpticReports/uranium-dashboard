#!/usr/bin/env python3
"""The other side of addendum 53: if a bad overnight after an oversold close predicts a BETTER session,
is that an edge to BUY, not a reason to sell? Owner, 2026-11-05: "i thought you said the indicator shows
mid day bounce tho? we are looking for any edge/alpha."

Measured on the same data as overnight_study.py / dipbuy_events.py:
  E1  a standalone morning trade: on a morning when a 3x fund closed with RSI(10) < 30 and the signal
      fires before 09:30, buy the fund at the 09:30 open and sell at the 16:00 close (one trade per
      day; several qualifying funds equal-weighted; 30 bps round trip). Per-trade statistics with the
      sample sd, win rate, year-by-year, worst trades, the mean without the best three trades, a
      family-wise permutation p (the max t over the 13 "bad overnight" rules under 4,000 shuffles of
      the day returns), the mirrored signals, and the intersection test (is it the gap, the oversold
      state, or both?).
  OOS the same rule on seven 2x/3x funds the hypothesis was NOT found on (TNA FAS UDOW UPRO SSO QLD USD).
  E2  an add-on inside the KMLM engine: on a leveraged-long morning when the signal fires, top the
      leveraged exposure up to 100% of the symphony at the open (capped at 1 - the day's total
      leveraged weight, so a two-leg day cannot exceed 100%) and sell the extra at the close; with a
      300-draw placebo of random long mornings. The counter-agent's fixes (review53b) are built in.
Writes composer/results/overnight-edge-2026-11-05.json. Usage: edge_study.py"""
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overnight_study as os_  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "overnight-edge-2026-11-05.json")
FUNDS = {"SOXL": "SMH", "TECL": "XLK", "TQQQ": "QQQ", "SPXL": "SPY", "LABU": "XBI"}
OOS_FUNDS = {"TNA": "IWM", "FAS": "SPY", "UDOW": "SPY", "UPRO": "SPY", "SSO": "SPY", "QLD": "QQQ", "USD": "SMH"}
RT_BPS = 30                      # round trip: buy at the open, sell at the close, 3x ETF, $50-150k
PERM_N, PLACEBO_N = 4000, 300
random.seed(20261105)


def wilder_rsi(closes, w):
    out = [None] * len(closes)
    g = l = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        up, dn = max(ch, 0.0), max(-ch, 0.0)
        if i <= w:
            g += up / w
            l += dn / w
            if i == w:
                out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
        else:
            g = (g * (w - 1) + up) / w
            l = (l * (w - 1) + dn) / w
            out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def keys(D, f):
    return sorted(k for k in D[f] if not k.startswith("_"))


def mornings_all(D, funds):
    """every morning of each fund with the prior close's RSI(10) and the pre-open signals"""
    rows = []
    for f, sec in funds.items():
        ks = keys(D, f)
        rsi = wilder_rsi([D[f][d]["a"] for d in ks], 10)
        for i in range(11, len(ks) - 1):
            if rsi[i] is None:
                continue
            d0, d1 = ks[i], ks[i + 1]
            gi = os_.gap_intraday(D, f, d1)
            if gi is None:
                continue
            sg = os_.gap_intraday(D, sec, d1) if sec in D else None
            eu = os_.gap_intraday(D, "^GDAXI", d1)
            rows.append({"date": d1, "fund": f, "rsi": rsi[i], "oversold": rsi[i] < 30, "gap": gi["gap"], "intra": gi["intra"], "day": gi["day"],
                         "entry_day": D[f][d0]["c"] / D[f][ks[i - 1]]["c"] - 1, "sec_gap": sg["gap"] if sg else None,
                         "asia": os_.asia(D, d1), "eu_open": eu["gap"] if eu else None, "vix": os_.level(D, "^VIX", d1)})
    return rows


RULES = {
    "fund gap <= -3%": lambda r: r["gap"] <= -0.03,
    "fund gap <= -5%": lambda r: r["gap"] <= -0.05,
    "fund gap <= -8%": lambda r: r["gap"] <= -0.08,
    "sector gap <= -1%": lambda r: r["sec_gap"] is not None and r["sec_gap"] <= -0.01,
    "sector gap <= -2%": lambda r: r["sec_gap"] is not None and r["sec_gap"] <= -0.02,
    "Asia <= -1%": lambda r: r["asia"] is not None and r["asia"] <= -0.01,
    "Asia <= -2%": lambda r: r["asia"] is not None and r["asia"] <= -0.02,
    "DAX open <= -1%": lambda r: r["eu_open"] is not None and r["eu_open"] <= -0.01,
    "DAX open <= -2%": lambda r: r["eu_open"] is not None and r["eu_open"] <= -0.02,
    "VIX > 30": lambda r: r["vix"] is not None and r["vix"] > 30,
    "gap <= -5% OR DAX <= -2%": lambda r: r["gap"] <= -0.05 or (r["eu_open"] is not None and r["eu_open"] <= -0.02),
    "gap <= -3% AND (Asia <= -1% OR DAX <= -1%)": lambda r: r["gap"] <= -0.03 and ((r["asia"] is not None and r["asia"] <= -0.01) or (r["eu_open"] is not None and r["eu_open"] <= -0.01)),
    "gap <= -5% AND sector gap <= -2%": lambda r: r["gap"] <= -0.05 and r["sec_gap"] is not None and r["sec_gap"] <= -0.02,
    "any oversold morning (no signal)": lambda r: True,
    "MIRROR: fund gap >= +5%": lambda r: r["gap"] >= 0.05,
    "MIRROR: DAX open >= +1%": lambda r: r["eu_open"] is not None and r["eu_open"] >= 0.01,
}
FAMILY = [k for k in RULES if not k.startswith("MIRROR") and not k.startswith("any")]


def daily_trades(rows, fire, cost=RT_BPS / 1e4):
    """one trade per day: the equal-weighted open->close return of the qualifying funds, less costs"""
    by_day = {}
    for r in rows:
        if fire(r):
            by_day.setdefault(r["date"], []).append(r)
    return [{"date": d, "funds": [r["fund"] for r in rs], "ret": statistics.mean(r["intra"] for r in rs) - cost,
             "gap": statistics.mean(r["gap"] for r in rs)} for d, rs in sorted(by_day.items())]


def tstat(x):
    if len(x) < 3:
        return None
    s = statistics.stdev(x)
    return statistics.mean(x) / (s / math.sqrt(len(x))) if s else None


def trade_stats(trades, full=True):
    if not trades:
        return {"n": 0}
    x = [t["ret"] for t in trades]
    m = statistics.mean(x)
    lv, peak, dd = 1.0, 1.0, 0.0
    for v in x:
        lv *= 1 + v
        peak = max(peak, lv)
        dd = min(dd, lv / peak - 1)
    out = {"n": len(x), "mean": m, "median": statistics.median(x), "sd": statistics.stdev(x) if len(x) > 1 else None, "t": tstat(x),
           "win": sum(1 for v in x if v > 0) / len(x), "total": lv - 1, "maxdd": dd,
           "from": trades[0]["date"], "to": trades[-1]["date"],
           "per_year": len(x) / max(1, int(trades[-1]["date"][:4]) - int(trades[0]["date"][:4]) + 1)}
    if len(x) > 4:
        xs = sorted(x)[:-3]
        out["drop_best3"] = {"mean": statistics.mean(xs), "t": tstat(xs), "win": sum(1 for v in xs if v > 0) / len(xs)}
    if full:
        yrs = {}
        for t in trades:
            yrs.setdefault(t["date"][:4], []).append(t["ret"])
        out["worst"] = sorted(trades, key=lambda t: t["ret"])[:5]
        out["best"] = sorted(trades, key=lambda t: -t["ret"])[:3]
        out["by_year"] = {y: {"n": len(v), "mean": statistics.mean(v), "win": sum(1 for q in v if q > 0) / len(v)} for y, v in sorted(yrs.items())}
        out["trades"] = [[t["date"], round(t["ret"], 5), "+".join(t["funds"])] for t in trades]
        out["ex_2020_03"] = trade_stats([t for t in trades if not t["date"].startswith("2020-03")], False)
        out["ex_2025_04"] = trade_stats([t for t in trades if not t["date"].startswith("2025-04")], False)
    return out


def main():
    D = os_.load_daily()
    allrows = mornings_all(D, FUNDS)
    rows = [r for r in allrows if r["oversold"]]
    days_all = sorted({r["date"] for r in rows})
    res = {"generated": "2026-11-05", "rt_bps": RT_BPS, "events": len(rows), "event_days": len(days_all), "E1": {}, "E2": {}, "OOS": {}, "intersection": {}}

    # ---- E1
    base_days = daily_trades(rows, lambda r: True)
    base_ret = {t["date"]: t["ret"] for t in base_days}
    sets = {name: {t["date"] for t in daily_trades(rows, fire)} for name, fire in RULES.items()}
    for name, fire in RULES.items():
        tr = daily_trades(rows, fire)
        st = trade_stats(tr)
        if st["n"] and not name.startswith("any"):
            k = min(st["n"], len(base_days))
            draws = sorted(statistics.mean(t["ret"] for t in random.sample(base_days, k)) for _ in range(2000))
            st["placebo"] = {"p05": draws[int(0.05 * len(draws))], "p50": draws[len(draws) // 2], "p95": draws[int(0.95 * len(draws))],
                             "percentile_of_actual": sum(1 for v in draws if v < st["mean"]) / len(draws)}
        res["E1"][name] = st
    # family-wise permutation: shuffle the day returns (the all-funds equal-weighted series), keep each rule's days,
    # record the max t over the family; p_fw(rule) = share of draws whose max t >= the rule's observed t
    obs_t = {name: tstat([base_ret[d] for d in sets[name]]) for name in FAMILY}
    vals = [base_ret[d] for d in days_all]
    maxts = []
    for _ in range(PERM_N):
        random.shuffle(vals)
        perm = dict(zip(days_all, vals))
        mt = max(tstat([perm[d] for d in sets[name]]) or 0.0 for name in FAMILY)
        maxts.append(mt)
    maxts.sort()
    res["family"] = {"rules": FAMILY, "perm_n": PERM_N, "null_max_t_p50": maxts[len(maxts) // 2], "null_max_t_p95": maxts[int(0.95 * len(maxts))],
                     "p_fw": {name: (sum(1 for m in maxts if m >= obs_t[name]) / len(maxts)) if obs_t[name] is not None else None for name in FAMILY},
                     "t_on_base_series": obs_t, "bonferroni_x16": {}}
    for name in FAMILY:
        st = res["E1"][name]
        if st.get("t") and st["n"] > 2:
            # two-sided normal approximation of the single-test p, times 16
            z = abs(st["t"])
            p1 = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
            res["family"]["bonferroni_x16"][name] = min(1.0, 16 * p1)
    # LABU split and tech-only for the primary rule
    prim = daily_trades(rows, RULES["fund gap <= -5%"])
    res["E1_splits"] = {"LABU only": trade_stats([t for t in prim if t["funds"] == ["LABU"]], False),
                        "without LABU days": trade_stats([t for t in prim if "LABU" not in t["funds"]], False),
                        "tech only (SOXL/TECL/TQQQ rows)": trade_stats(daily_trades([r for r in rows if r["fund"] in ("SOXL", "TECL", "TQQQ")], RULES["fund gap <= -5%"]), False)}

    # ---- intersection: SOXL/TECL/TQQQ, own oversold state x own gap
    tech = [r for r in allrows if r["fund"] in ("SOXL", "TECL", "TQQQ")]
    os_by_day = {}
    for r in allrows:
        if r["oversold"]:
            os_by_day.setdefault(r["date"], set()).add(r["fund"])
    conds = {"gap <= -5%, no RSI condition": lambda r: r["gap"] <= -0.05,
             "gap <= -5% AND own RSI < 30 (E1, tech)": lambda r: r["gap"] <= -0.05 and r["oversold"],
             "gap <= -5% AND own RSI >= 30": lambda r: r["gap"] <= -0.05 and not r["oversold"],
             "gap <= -5%, own RSI >= 30, another fund oversold": lambda r: r["gap"] <= -0.05 and not r["oversold"] and (os_by_day.get(r["date"], set()) - {r["fund"]}),
             "gap <= -5%, own RSI >= 30, no fund oversold": lambda r: r["gap"] <= -0.05 and not r["oversold"] and not os_by_day.get(r["date"]),
             "own RSI < 30, gap > -5%": lambda r: r["oversold"] and r["gap"] > -0.05,
             "own RSI < 30, -5% < gap <= -3%": lambda r: r["oversold"] and -0.05 < r["gap"] <= -0.03}
    for name, c in conds.items():
        res["intersection"][name] = trade_stats(daily_trades(tech, c), False)

    # ---- OOS: the seven other leveraged funds
    oos_rows = [r for r in mornings_all(D, OOS_FUNDS) if r["oversold"]]
    prim_days = set(sets["fund gap <= -5%"])
    res["OOS"]["all 7 pooled, fund gap <= -5%"] = trade_stats(daily_trades(oos_rows, RULES["fund gap <= -5%"]), False)
    res["OOS"]["all 7 pooled, sector gap <= -2%"] = trade_stats(daily_trades(oos_rows, RULES["sector gap <= -2%"]), False)
    res["OOS"]["TNA+FAS (sector-distinct), fund gap <= -5%"] = trade_stats(daily_trades([r for r in oos_rows if r["fund"] in ("TNA", "FAS")], RULES["fund gap <= -5%"]), False)
    res["OOS"]["QLD+USD (copies of TQQQ/SOXL), fund gap <= -5%"] = trade_stats(daily_trades([r for r in oos_rows if r["fund"] in ("QLD", "USD")], RULES["fund gap <= -5%"]), False)
    res["OOS"]["all 7, days not among the primary rule's 40"] = trade_stats([t for t in daily_trades(oos_rows, RULES["fund gap <= -5%"]) if t["date"] not in prim_days], False)
    for f in OOS_FUNDS:
        res["OOS"][f"{f} alone, fund gap <= -5%"] = trade_stats(daily_trades([r for r in oos_rows if r["fund"] == f], RULES["fund gap <= -5%"]), False)

    # ---- E2 inside the KMLM engine, capped per day
    P = os_.load_paths()["KMLM"]
    sel = [i for i, d in enumerate(P["days"]) if d >= os_.START]
    base = [P["rets"][i] for i in sel]
    base_sum = os_.summary(base)
    morn = os_.mornings(D, P)
    by_day = {}
    for r in morn:
        if r["side"] == "long":
            by_day.setdefault(r["date"], []).append(r)
    lev_w = {d: sum(r["w"] for r in rs) for d, rs in by_day.items()}
    day_index = {d: i for i, d in enumerate(P["days"])}
    oversold_days = {(r["date"], r["fund"]) for r in rows}

    def topup_path(fire_days):
        """returns (overlay path, n days, worst extra, share of fired days that were oversold mornings)"""
        out, n, worst, ovs = list(P["rets"]), 0, (0.0, None), 0
        for d, rs in by_day.items():
            q = [r for r in rs if d in fire_days[0] and (fire_days[1] is None or fire_days[1](r))]
            if not q:
                continue
            cap = max(0.0, 1.0 - lev_w[d])
            extra = cap * (statistics.mean(r["intra"] for r in q) - RT_BPS / 1e4)
            out[day_index[d]] += extra
            n += 1
            if any((d, r["fund"]) in oversold_days for r in q):
                ovs += 1
            if extra < worst[0]:
                worst = (extra, d)
        return out, n, worst, (ovs / n if n else None)

    long_days = sorted(by_day)
    for name, fire in RULES.items():
        if name.startswith("MIRROR") or name.startswith("any"):
            continue
        fired = {d for d, rs in by_day.items() if any(fire(r) for r in rs)}
        path, n, worst, ovs = topup_path((fired, fire))
        a = os_.summary([path[i] for i in sel])
        # placebo: random long mornings, same count, top-up on all legs that day
        draws = []
        for _ in range(PLACEBO_N):
            pick = set(random.sample(long_days, min(n, len(long_days))))
            pp, _, _, _ = topup_path((pick, None))
            draws.append(os_.summary([pp[i] for i in sel])["cagr"] - base_sum["cagr"])
        draws.sort()
        res["E2"][name] = {"n_days": n, "share_oversold": ovs, "dcagr": a["cagr"] - base_sum["cagr"], "dsharpe": a["sharpe"] - base_sum["sharpe"],
                           "dmaxdd": a["maxdd"] - base_sum["maxdd"], "worst_extra": worst[0], "worst_date": worst[1],
                           "placebo": {"p05": draws[int(0.05 * len(draws))], "p50": draws[len(draws) // 2], "p95": draws[int(0.95 * len(draws))],
                                       "percentile_of_actual": sum(1 for v in draws if v < a["cagr"] - base_sum["cagr"]) / len(draws)}}
    res["E2"]["base"] = base_sum
    # how often the engine already held a leveraged leg on the primary rule's days since 2015-06
    pd_ = [t for t in prim if t["date"] >= os_.START]
    held = [t["date"] for t in pd_ if t["date"] in by_day]
    res["E1_engine_overlap"] = {"primary_days_since_2015": len(pd_), "engine_already_long": len(held),
                               "not_long_trades": [[t["date"], round(t["ret"], 4)] for t in pd_ if t["date"] not in by_day]}
    json.dump(res, open(OUT, "w"), indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)

    # ---- console
    print(f"{len(rows)} oversold mornings on {len(days_all)} distinct days; one trade per day, {RT_BPS} bps round trip; t with the sample sd\n")
    print("E1 standalone morning trade (buy the open, sell the close)")
    print(f"  {'rule':46s} {'days':>5s} {'/yr':>5s} {'mean':>7s} {'median':>7s} {'win':>5s} {'t':>5s} {'drop3':>7s} {'t3':>5s} {'total':>7s} {'maxDD':>6s} {'p_fw':>6s} {'Bonf16':>7s}  worst")
    for name, st in res["E1"].items():
        if not st["n"]:
            continue
        d3 = st.get("drop_best3") or {}
        fw = res["family"]["p_fw"].get(name)
        bf = res["family"]["bonferroni_x16"].get(name)
        print(f"  {name:46s} {st['n']:5d} {st['per_year']:5.1f} {st['mean']:+7.2%} {st['median']:+7.2%} {st['win']:5.0%} {(st['t'] or 0):5.1f} {d3.get('mean', 0):+7.2%} {(d3.get('t') or 0):5.1f} {st['total']:+7.0%} {st['maxdd']:6.0%} "
              + (f"{fw:6.2f}" if fw is not None else "      ") + (f" {bf:7.2f}" if bf is not None else "        ") + "  "
              + ", ".join(f"{w['date']} {w['ret']:+.0%}" for w in st["worst"][:2]))
    print(f"  family-wise null max t: p50 {res['family']['null_max_t_p50']:.2f}, p95 {res['family']['null_max_t_p95']:.2f}")
    print("  splits of the primary rule:", {k: (v['n'], f"{v['mean']:+.2%}", round(v['t'] or 0, 2)) for k, v in res["E1_splits"].items()})
    print("  engine overlap:", res["E1_engine_overlap"])
    print("\nintersection (SOXL/TECL/TQQQ, one trade per day):")
    for k, v in res["intersection"].items():
        print(f"  {k:52s} n {v['n']:4d} mean {v['mean']:+.2%} median {v['median']:+.2%} t {(v['t'] or 0):+.2f} win {v['win']:.0%}")
    print("\nOOS, the seven other leveraged funds:")
    for k, v in res["OOS"].items():
        if v["n"]:
            print(f"  {k:52s} n {v['n']:4d} mean {v['mean']:+.2%} median {v['median']:+.2%} t {(v['t'] or 0):+.2f} win {v['win']:.0%} drop3 {(v.get('drop_best3') or {}).get('mean', 0):+.2%}")
    print("\nE2 inside the KMLM engine, capped top-up (as built CAGR {:.1%}, Sharpe {:.2f}, maxDD {:.0%})".format(base_sum["cagr"], base_sum["sharpe"], base_sum["maxdd"]))
    for name, v in res["E2"].items():
        if name == "base":
            continue
        pl = v["placebo"]
        print(f"  {name:46s} days {v['n_days']:4d} oversold {v['share_oversold']:.0%} dCAGR {v['dcagr']:+6.1%} dSharpe {v['dsharpe']:+.2f} dMaxDD {v['dmaxdd']:+.1%} worst {v['worst_extra']:+.1%} ({v['worst_date']}) placebo p05/p50/p95 {pl['p05']:+.1%}/{pl['p50']:+.1%}/{pl['p95']:+.1%} pct {pl['percentile_of_actual']:.0%}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
