#!/usr/bin/env python3
"""Model-free companion to overnight_study.py: every morning after a 3x fund closed with Wilder
RSI(10) < 30 (the engines' dip-buy trigger, computed on adjusted closes), 2010-2026, what the fund did
overnight (prev close -> open) and intraday (open -> close), and whether anything known before 09:30
(Asia's closes, the DAX open, VIX, the fund's own pre-open gap) sorted the good mornings from the bad.
No engine path needed, so thousands of events instead of hundreds. Writes
composer/results/overnight-events-2026-11-05.json. Usage: dipbuy_events.py"""
import json
import math
import os
import statistics

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "overnight-events-2026-11-05.json")
FUNDS = {"SOXL": "SMH", "TECL": "XLK", "TQQQ": "QQQ", "SPXL": "SPY", "LABU": "LABU"}
RSI_W, RSI_THR = 10, 30


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


def main():
    D = {t: v["rows"] for t, v in json.load(open(os.path.join(S, "overnight", "daily.json"))).items()}

    def ret_on(t, d, keys):
        i = keys.index(d)
        if i == 0:
            return None
        return D[t][d]["c"] / D[t][keys[i - 1]]["c"] - 1

    idx = {t: sorted(D[t]) for t in D}
    res = {"generated": "2026-11-05", "rsi": [RSI_W, RSI_THR], "funds": {}}
    allrows = []
    for f, sec in FUNDS.items():
        ks = idx[f]
        closes = [D[f][d]["a"] for d in ks]
        rsi = wilder_rsi(closes, RSI_W)
        rows = []
        for i in range(RSI_W + 1, len(ks) - 1):
            if rsi[i] is None or rsi[i] >= RSI_THR:
                continue
            d0, d1 = ks[i], ks[i + 1]
            r0, r1 = D[f][d0], D[f][d1]
            if not r1.get("o") or not r0.get("c"):
                continue
            gap, intra, day = r1["o"] / r0["c"] - 1, r1["c"] / r1["o"] - 1, r1["c"] / r0["c"] - 1
            sg = None
            if d1 in D[sec] and d0 in D[sec] and D[sec][d1].get("o"):
                sg = D[sec][d1]["o"] / D[sec][d0]["c"] - 1
            av = []
            for a in ("^N225", "^KS11", "^TWII"):
                if d1 in D[a]:
                    k2 = idx[a]
                    j = k2.index(d1)
                    if j:
                        av.append(D[a][d1]["c"] / D[a][k2[j - 1]]["c"] - 1)
            asia = statistics.mean(av) if len(av) >= 2 else None
            eu = None
            if d1 in D["^GDAXI"]:
                k2 = idx["^GDAXI"]
                j = k2.index(d1)
                if j and D["^GDAXI"][d1].get("o"):
                    eu = D["^GDAXI"][d1]["o"] / D["^GDAXI"][k2[j - 1]]["c"] - 1
            vix = D["^VIX"][d0]["c"] if d0 in D["^VIX"] else None
            rows.append({"fund": f, "date": d1, "entry_day": r0["c"] / D[f][ks[i - 1]]["c"] - 1, "rsi": rsi[i], "gap": gap, "intra": intra, "day": day,
                         "sec_gap": sg, "asia": asia, "eu_open": eu, "vix": vix})
        allrows += rows

        def bucket(cond, name):
            sel = [r for r in rows if cond(r)]
            if not sel:
                return {"n": 0}
            return {"n": len(sel), "gap": statistics.mean(r["gap"] for r in sel), "intra": statistics.mean(r["intra"] for r in sel),
                    "day": statistics.mean(r["day"] for r in sel), "intra_neg": sum(1 for r in sel if r["intra"] < 0) / len(sel),
                    "intra_median": statistics.median(r["intra"] for r in sel)}

        F = {"n": len(rows), "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None,
             "all": bucket(lambda r: True, "all"),
             "by_gap": {f"<= -{t:.0%}": bucket(lambda r, t=t: r["gap"] <= -t, "") for t in (0.02, 0.05, 0.08, 0.10)},
             "by_gap_up": {f">= +{t:.0%}": bucket(lambda r, t=t: r["gap"] >= t, "") for t in (0.02, 0.05)},
             "by_asia": {f"<= -{t:.1%}": bucket(lambda r, t=t: r["asia"] is not None and r["asia"] <= -t, "") for t in (0.005, 0.01, 0.02)},
             "by_asia_up": {f">= +{t:.1%}": bucket(lambda r, t=t: r["asia"] is not None and r["asia"] >= t, "") for t in (0.005, 0.01)},
             "by_eu": {f"<= -{t:.1%}": bucket(lambda r, t=t: r["eu_open"] is not None and r["eu_open"] <= -t, "") for t in (0.005, 0.01, 0.02)},
             "by_sector_gap": {f"<= -{t:.1%}": bucket(lambda r, t=t: r["sec_gap"] is not None and r["sec_gap"] <= -t, "") for t in (0.005, 0.01, 0.02, 0.03)},
             "by_vix": {f"> {v}": bucket(lambda r, v=v: r["vix"] is not None and r["vix"] > v, "") for v in (20, 25, 30, 40)},
             "by_entry": {f"<= -{t:.0%}": bucket(lambda r, t=t: r["entry_day"] <= -t, "") for t in (0.05, 0.08, 0.10)},
             "combo_gap5_asia1": bucket(lambda r: r["gap"] <= -0.05 and r["asia"] is not None and r["asia"] <= -0.01, ""),
             "combo_gap5_eu1": bucket(lambda r: r["gap"] <= -0.05 and r["eu_open"] is not None and r["eu_open"] <= -0.01, ""),
             "combo_asia1_eu1": bucket(lambda r: r["asia"] is not None and r["asia"] <= -0.01 and r["eu_open"] is not None and r["eu_open"] <= -0.01, "")}
        res["funds"][f] = F
    # pooled, equal weight across funds
    res["pooled_n"] = len(allrows)
    # correlation of the overnight signals with the subsequent intraday move (does the signal predict open->close?)
    def corr(xs, ys):
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        return num / den if den else None
    res["pooled_corr_with_intraday"] = {}
    for key in ("gap", "sec_gap", "asia", "eu_open", "vix", "entry_day"):
        pairs = [(r[key], r["intra"]) for r in allrows if r.get(key) is not None]
        res["pooled_corr_with_intraday"][key] = {"n": len(pairs), "corr": corr([p[0] for p in pairs], [p[1] for p in pairs])}
    # does the gap predict the intraday? deciles of the gap -> mean intraday
    srt = sorted(allrows, key=lambda r: r["gap"])
    dec = []
    for k in range(10):
        chunk = srt[k * len(srt) // 10:(k + 1) * len(srt) // 10]
        dec.append({"gap_mean": statistics.mean(r["gap"] for r in chunk), "intra_mean": statistics.mean(r["intra"] for r in chunk),
                    "intra_neg": sum(1 for r in chunk if r["intra"] < 0) / len(chunk), "n": len(chunk)})
    res["gap_deciles"] = dec
    json.dump(res, open(OUT, "w"), indent=1)

    for f, F in res["funds"].items():
        a = F["all"]
        print(f"\n{f}: {F['n']} mornings after RSI(10)<30 closes, {F['from']}..{F['to']}: mean gap {a['gap']:+.2%}, intraday {a['intra']:+.2%} ({a['intra_neg']:.0%} negative), day {a['day']:+.2%}")
        for grp in ("by_gap", "by_gap_up", "by_sector_gap", "by_asia", "by_asia_up", "by_eu", "by_vix", "by_entry"):
            print(f"  {grp:14s} " + "  ".join(f"{k}: n{v['n']} intra {v['intra']:+.2%} ({v['intra_neg']:.0%} neg)" if v["n"] else f"{k}: n0" for k, v in F[grp].items()))
        for k in ("combo_gap5_asia1", "combo_gap5_eu1", "combo_asia1_eu1"):
            v = F[k]
            print(f"  {k:16s} " + (f"n{v['n']} intra {v['intra']:+.2%} ({v['intra_neg']:.0%} neg)" if v["n"] else "n0"))
    print("\npooled correlation of pre-open signals with the subsequent open->close move:", {k: (v["n"], round(v["corr"], 3) if v["corr"] is not None else None) for k, v in res["pooled_corr_with_intraday"].items()})
    print("gap deciles -> intraday:", " | ".join(f"{d['gap_mean']:+.1%}->{d['intra_mean']:+.2%} ({d['intra_neg']:.0%} neg)" for d in dec))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
