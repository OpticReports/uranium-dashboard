#!/usr/bin/env python3
"""The other side of addendum 53: if a bad overnight after an oversold close predicts a BETTER session,
is that an edge to BUY, not a reason to sell? Owner, 2026-11-05: "i thought you said the indicator shows
mid day bounce tho? we are looking for any edge/alpha."

Two uses are measured, on the same data as overnight_study.py / dipbuy_events.py:
  E1  a standalone morning trade: on a morning when a 3x fund closed with RSI(10) < 30 and the signal
      fires before 09:30, buy the fund at the 09:30 open and sell at the 16:00 close (one trade per
      day; several qualifying funds are equal-weighted). Per-trade statistics, t-stat by day, win rate,
      year-by-year, worst trades, costs, placebo (random oversold mornings) and the mirrored signal.
  E2  an add-on inside the KMLM engine: on a leveraged-long morning when the signal fires, raise the leg
      from its weight to 100% of the symphony at the open and sell the extra at the close; and, on
      mornings when the engine is NOT long but a fund qualifies, a 50%-of-NAV day trade in that fund.
      Measured as changes to the engine path's CAGR / Sharpe / max DD, with the single worst day.
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
RT_BPS = 30                      # round trip: buy at the open, sell at the close, 3x ETF, $50-150k
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


def events(D):
    """all (date, fund) mornings after an RSI(10) < 30 close with the pre-open signals"""
    rows = []
    for f, sec in FUNDS.items():
        ks = sorted(k for k in D[f] if not k.startswith("_"))
        rsi = wilder_rsi([D[f][d]["a"] for d in ks], 10)
        for i in range(11, len(ks) - 1):
            if rsi[i] is None or rsi[i] >= 30:
                continue
            d0, d1 = ks[i], ks[i + 1]
            gi = os_.gap_intraday(D, f, d1)
            if gi is None:
                continue
            sg = os_.gap_intraday(D, sec, d1) if sec in D else None
            eu = os_.gap_intraday(D, "^GDAXI", d1)
            rows.append({"date": d1, "fund": f, "gap": gi["gap"], "intra": gi["intra"], "day": gi["day"], "entry_day": D[f][d0]["c"] / D[f][ks[i - 1]]["c"] - 1,
                         "sec_gap": sg["gap"] if sg else None, "asia": os_.asia(D, d1), "eu_open": eu["gap"] if eu else None,
                         "vix": os_.level(D, "^VIX", d1)})
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


def daily_trades(rows, fire, cost=RT_BPS / 1e4):
    """one trade per day: the equal-weighted open->close return of the qualifying funds, less costs"""
    by_day = {}
    for r in rows:
        if fire(r):
            by_day.setdefault(r["date"], []).append(r)
    out = []
    for d in sorted(by_day):
        rs = by_day[d]
        out.append({"date": d, "funds": [r["fund"] for r in rs], "ret": statistics.mean(r["intra"] for r in rs) - cost,
                    "gap": statistics.mean(r["gap"] for r in rs)})
    return out


def trade_stats(trades):
    if not trades:
        return {"n": 0}
    x = [t["ret"] for t in trades]
    m, s = statistics.mean(x), (statistics.pstdev(x) if len(x) > 1 else float("nan"))
    lv, peak, dd = 1.0, 1.0, 0.0
    for v in x:
        lv *= 1 + v
        peak = max(peak, lv)
        dd = min(dd, lv / peak - 1)
    yrs = {}
    for t in trades:
        yrs.setdefault(t["date"][:4], []).append(t["ret"])
    return {"n": len(x), "mean": m, "median": statistics.median(x), "sd": s, "t": (m / (s / math.sqrt(len(x))) if s else float("nan")),
            "win": sum(1 for v in x if v > 0) / len(x), "total": lv - 1, "maxdd": dd, "worst": sorted(trades, key=lambda t: t["ret"])[:5],
            "trades": [[t["date"], round(t["ret"], 5), "+".join(t["funds"])] for t in trades],
            "best": sorted(trades, key=lambda t: -t["ret"])[:3],
            "by_year": {y: {"n": len(v), "mean": statistics.mean(v), "win": sum(1 for q in v if q > 0) / len(v)} for y, v in sorted(yrs.items())},
            "share_2020": sum(1 for t in trades if t["date"].startswith("2020")) / len(x),
            "per_year": len(x) / max(1e-9, (int(trades[-1]["date"][:4]) - int(trades[0]["date"][:4]) + 1)),
            "from": trades[0]["date"], "to": trades[-1]["date"]}


def main():
    D = os_.load_daily()
    rows = events(D)
    days_all = sorted({r["date"] for r in rows})
    res = {"generated": "2026-11-05", "rt_bps": RT_BPS, "events": len(rows), "event_days": len(days_all), "E1": {}, "E2": {}}
    base_days = daily_trades(rows, lambda r: True)
    # E1
    for name, fire in RULES.items():
        tr = daily_trades(rows, fire)
        st = trade_stats(tr)
        if st["n"]:
            # placebo: the same number of random oversold mornings (days), 2000 draws: distribution of the mean
            k = min(st["n"], len(base_days))
            draws = []
            for _ in range(2000):
                pick = random.sample(base_days, k)
                draws.append(statistics.mean(t["ret"] for t in pick))
            draws.sort()
            st["placebo"] = {"p05": draws[int(0.05 * len(draws))], "p50": draws[len(draws) // 2], "p95": draws[int(0.95 * len(draws))],
                             "percentile_of_actual": sum(1 for v in draws if v < st["mean"]) / len(draws)}
        res["E1"][name] = st
    # E2: inside the KMLM engine
    P = os_.load_paths()["KMLM"]
    sel = [i for i, d in enumerate(P["days"]) if d >= os_.START]
    base = [P["rets"][i] for i in sel]
    base_sum = os_.summary(base)
    morn = os_.mornings(D, P)
    long_idx = {(r["date"], r["fund"]): r for r in morn if r["side"] == "long"}
    long_days = {r["date"] for r in morn if r["side"] == "long"}
    ev_by_day = {}
    for r in rows:
        ev_by_day.setdefault(r["date"], []).append(r)
    day_index = {d: i for i, d in enumerate(P["days"])}
    for name, fire in RULES.items():
        if name.startswith("MIRROR") or name.startswith("any"):
            continue
        add, trade = list(P["rets"]), list(P["rets"])
        n_add = n_trade = 0
        worst_add = (0.0, None)
        for r in morn:
            if r["side"] != "long" or not fire(r):
                continue
            extra = (1.0 - r["w"]) * (r["intra"] - RT_BPS / 1e4)        # top the leg up to 100% at the open, sell the extra at the close
            add[r["i"]] += extra
            n_add += 1
            if extra < worst_add[0]:
                worst_add = (extra, r["date"])
        for d, rs in ev_by_day.items():
            if d in long_days or d not in day_index or d < os_.START:
                continue
            q = [r for r in rs if fire(r)]
            if not q:
                continue
            trade[day_index[d]] += 0.5 * (statistics.mean(r["intra"] for r in q) - RT_BPS / 1e4)
            n_trade += 1
        a = os_.summary([add[i] for i in sel])
        t = os_.summary([trade[i] for i in sel])
        res["E2"][name] = {"add_on": {"n": n_add, "dcagr": a["cagr"] - base_sum["cagr"], "dsharpe": a["sharpe"] - base_sum["sharpe"], "dmaxdd": a["maxdd"] - base_sum["maxdd"],
                                      "worst_extra": worst_add[0], "worst_date": worst_add[1]},
                           "day_trade_when_not_long": {"n": n_trade, "dcagr": t["cagr"] - base_sum["cagr"], "dsharpe": t["sharpe"] - base_sum["sharpe"], "dmaxdd": t["maxdd"] - base_sum["maxdd"]}}
    res["E2"]["base"] = base_sum
    # the overnight / intraday split of the five funds unconditionally (context)
    res["split"] = {}
    for f in FUNDS:
        ks = sorted(k for k in D[f] if not k.startswith("_"))
        g, it = [], []
        for i in range(1, len(ks)):
            r = os_.gap_intraday(D, f, ks[i])
            if r and ks[i] >= "2015-06-01":
                g.append(r["gap"])
                it.append(r["intra"])
        res["split"][f] = {"n": len(g), "gap_mean": statistics.mean(g), "intra_mean": statistics.mean(it)}
    json.dump(res, open(OUT, "w"), indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)

    print(f"{len(rows)} oversold mornings on {len(days_all)} distinct days; one trade per day, {RT_BPS} bps round trip\n")
    print("E1 standalone morning trade (buy the open, sell the close)")
    print(f"  {'rule':46s} {'days':>5s} {'/yr':>5s} {'mean':>7s} {'median':>7s} {'win':>5s} {'t':>5s} {'total':>8s} {'maxDD':>7s} {'placebo pct':>11s}  worst")
    for name, st in res["E1"].items():
        if not st["n"]:
            print(f"  {name:46s} {0:5d}")
            continue
        pl = st.get("placebo", {})
        print(f"  {name:46s} {st['n']:5d} {st['per_year']:5.1f} {st['mean']:+7.2%} {st['median']:+7.2%} {st['win']:5.0%} {st['t']:5.1f} {st['total']:+8.0%} {st['maxdd']:7.0%} {pl.get('percentile_of_actual', float('nan')):11.0%}  "
              + ", ".join(f"{w['date']} {w['ret']:+.0%}" for w in st["worst"][:3]))
    for name in ("fund gap <= -5%", "DAX open <= -2%", "gap <= -5% OR DAX <= -2%"):
        st = res["E1"][name]
        print(f"  by year, {name}: " + "  ".join(f"{y} n{v['n']} {v['mean']:+.1%}" for y, v in st["by_year"].items()))
    print("\nE2 inside the KMLM engine (as built CAGR {:.1%}, Sharpe {:.2f}, maxDD {:.0%})".format(base_sum["cagr"], base_sum["sharpe"], base_sum["maxdd"]))
    print(f"  {'rule':46s} {'add-on n':>8s} {'dCAGR':>7s} {'dSharpe':>8s} {'dMaxDD':>7s} {'worst extra (date)':>24s} | {'day-trade n':>11s} {'dCAGR':>7s} {'dSharpe':>8s} {'dMaxDD':>7s}")
    for name, v in res["E2"].items():
        if name == "base":
            continue
        a, t = v["add_on"], v["day_trade_when_not_long"]
        print(f"  {name:46s} {a['n']:8d} {a['dcagr']:+7.1%} {a['dsharpe']:+8.2f} {a['dmaxdd']:+7.1%} {a['worst_extra']:+10.1%} ({a['worst_date']}) | {t['n']:11d} {t['dcagr']:+7.1%} {t['dsharpe']:+8.2f} {t['dmaxdd']:+7.1%}")
    print("\nunconditional overnight / intraday split since 2015-06:", {f: (round(v['gap_mean'], 5), round(v['intra_mean'], 5)) for f, v in res["split"].items()})
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
