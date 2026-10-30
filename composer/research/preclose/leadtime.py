#!/usr/bin/env python3
"""Pre-close preview lead-time study (results.md addendum 49).

Over the sessions Yahoo still has 5-minute bars for (~60), for each engine's approved logic (the era
in force that day):
  1. how often its answer at 15:00 / 15:15 / 15:30 / 15:40 ET matches its answer at 15:50 (Composer's
     decision minute): the same holdings (half-L1 <= 3%) and no material change (< 25%)
  2. whether the 15:15 flip labels (coin-flip / could flip / firm, preclose.flip) sort the sessions
     whose answer changed materially by 15:50
  3. the size of the move to 15:50 of every decision ticker in daily sigmas (20 sessions to the day
     before), from each earlier minute: the scale the live preview applies to sqrt(minutes / 390)
     (preclose.SIGMA_SCALE), on tickers with a full day of 5-minute bars (liquid) and on all
  4. HG's SPY 200-day gate: sessions where its state at the minute differs from 15:50

Prices: every decision ticker's close on the day is replaced by its price at the minute (close of the
5-minute bar ending then, none older than 30 minutes), scaled onto the adjusted series by the official
close: shadow_runner.at_times' method. Logic only: Composer's holdings and KMLM's corridor are not
part of it (the logic's targets are compared), nor are live-feed problems (stale quotes).

Writes composer/results/preclose-leadtime-2026-10-30.json. Usage: leadtime.py
"""
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "preclose-leadtime-2026-10-30.json")
OFFSETS = (60, 45, 30, 20, 10)     # minutes before the close: 15:00, 15:15, 15:30, 15:40, 15:50
REF, LABEL_AT = 10, 45


def at(prices, raw, bars, tickers, d, hhmm):
    """prices with each ticker's close on d replaced by its price at hh:mm; None if one is missing"""
    p = dict(prices)
    for t in tickers:
        px = sr.bar_price(((bars.get(t) or {}).get(d)) or {}, hhmm)
        rc = (raw.get(t) or {}).get(d)
        if px is None or not rc or d not in prices.get(t, {}):
            return None
        p[t] = dict(prices[t])
        p[t][d] = prices[t][d] * px / rc
    return p


def sd20(series, d):
    ds = [x for x in sorted(series) if x <= d][-21:]
    if len(ds) < 21:
        return None
    r = [series[ds[i]] / series[ds[i - 1]] - 1 for i in range(1, 21)]
    m = sum(r) / 20
    return math.sqrt(sum((x - m) ** 2 for x in r) / 20)


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    today = sr.et_now(now).date().isoformat()
    cfg_all = sr.load_manifest()
    get_bars = sr.bars_fetcher("60d")
    spy_bars = get_bars(["SPY"]).get("SPY") or {}
    days = sorted(d for d, b in spy_bars.items() if d < today and b.get("_close"))
    tick = {"SPY"}
    for cfg in cfg_all.values():
        for era in sr.eras_between(cfg, days[0], days[-1]):
            tick |= sr.tree_tickers(sr.load_tree(era))
    prices, raw, bad = sr.fetch_prices(tick, now)
    bars = get_bars(sorted(tick))
    print(f"{len(days)} sessions {days[0]}..{days[-1]}; {len(tick)} tickers; Yahoo failures: {bad or 'none'}")

    rows, z, gate_rows = [], [], []
    for d in days:
        close = spy_bars[d]["_close"]
        cal = [x for x in sorted(prices["SPY"]) if x < d]
        prev = cal[-1]
        hh = {off: sr._hm(sr._min(close) - off) for off in OFFSETS}
        # 4. the gate
        g = {}
        for off in OFFSETS:
            p = at(prices, raw, bars, ["SPY"], d, hh[off])
            gg = pc.gate(p["SPY"], d, pc.sigma_factor(off - REF)) if p else None
            g[off] = gg and gg["open"]
        gate_rows.append({"date": d, "open": g, "dist_1550": None})
        # 1-2. engines
        day_tk = set()
        for eng, cfg in cfg_all.items():
            era = sr.era_for(cfg, d)
            tree = sr.load_tree(era)
            tk = sr.decision_tickers(tree)
            day_tk |= tk
            res = {}
            for off in OFFSETS:
                p = at(prices, raw, bars, tk, d, hh[off])
                res[off] = sr.run_engine(p, tree, d) if p else None
            row = {"date": d, "engine": eng, "version": era["version"][:8]}
            ref = res.get(REF)
            if not ref or ref[1] is None:
                rows.append(dict(row, status="unavailable"))
                continue
            row["target_1550"] = ref[1]
            row["dist"] = {}
            for off in OFFSETS:
                if res[off] and res[off][1] is not None:
                    row["dist"][hh[off]] = round(sr.distance(res[off][1], ref[1])[0], 4)
            s15 = res.get(LABEL_AT)
            if s15 and s15[1] is not None:
                # searched with the unscaled sqrt(t) factor (the wider radius); labels at any scale follow
                fl = pc.flip(s15[0], tree, d, prev, s15[2], s15[1], {}, None, math.sqrt((LABEL_AT - REF) / pc.SESSION_MIN))
                row.update(flip=fl and {k: fl[k] for k in ("ticker", "move", "sigma")}, target_1515=s15[1])
            rows.append(dict(row, status="ok"))
        # 3. moves to 15:50 in daily sigmas, from each earlier minute
        for t in sorted(day_tk):
            b = (bars.get(t) or {}).get(d) or {}
            a2, sg = sr.bar_price(b, hh[REF]), sd20(prices.get(t, {}), prev)
            liquid = sum(1 for k in b if not k.startswith("_")) >= 0.97 * (sr._min(close) - 570) / 5
            for off in OFFSETS[:-1]:
                a1 = sr.bar_price(b, hh[off])
                if a1 and a2 and sg:
                    z.append((d, t, off - REF, liquid, (a2 / a1 - 1) / sg))
        print(d, " ".join(f"{r['engine']}:{(r.get('flip') or {}).get('sigma', '-')}/{r.get('dist', {}).get(hh[LABEL_AT], '-')}"
                          for r in rows if r["date"] == d), flush=True)

    # summaries
    ok = [r for r in rows if r["status"] == "ok"]
    times = [sr._hm(16 * 60 - off) for off in OFFSETS]
    acc = {}
    for eng in list(cfg_all) + ["all"]:
        rr = [r for r in ok if eng in ("all", r["engine"])]
        acc[eng] = {}
        for hhmm in times:
            ds = [r["dist"][hhmm] for r in rr if hhmm in r["dist"]]
            acc[eng][hhmm] = {"n": len(ds), "same": sum(x <= sr.TOL_DAILY for x in ds),
                              "no_material": sum(x < pc.FLIP_MATERIAL for x in ds)}
    def stats(xs, minutes):
        a = sorted(abs(x) for x in xs)
        if not a:
            return None
        rms = math.sqrt(sum(x * x for x in a) / len(a))
        return {"n": len(a), "rms": round(rms, 4), "sqrt_t": round(math.sqrt(minutes / pc.SESSION_MIN), 4),
                "scale": round(rms / math.sqrt(minutes / pc.SESSION_MIN), 3), "p50_abs": round(a[len(a) // 2], 4),
                "p95_abs": round(a[int(0.95 * len(a))], 4), "p99_abs": round(a[int(0.99 * len(a))], 4),
                "p95_over_rms": round(a[int(0.95 * len(a))] / rms, 2), "p99_over_rms": round(a[int(0.99 * len(a))] / rms, 2)}
    mins = sorted({m for _, _, m, _, _ in z})
    zsum = {grp: {f"{m} min": stats([x for _, _, mm, liq, x in z if mm == m and (grp == "all" or liq)], m) for m in mins}
            for grp in ("liquid", "all")}
    scale = zsum["liquid"][f"{LABEL_AT - REF} min"]["scale"]

    def labels(sc):
        """the 15:15 labels if the preview's sigma were sc x sqrt(t), and what then happened by 15:50"""
        out = {}
        for r in ok:
            if "15:15" not in r["dist"] or "target_1515" not in r:
                continue
            fl = r.get("flip")
            sig = fl["sigma"] / sc if fl else None
            lb = pc.label({"sigma": sig} if sig is not None and sig <= pc.FLIP_MAX else None)
            k = out.setdefault(lb, {"n": 0, "changed": 0, "material": 0})
            k["n"] += 1
            k["changed"] += r["dist"]["15:15"] > sr.TOL_DAILY
            k["material"] += r["dist"]["15:15"] >= pc.FLIP_MATERIAL
        return out
    lab = {"sqrt_t": labels(1.0), "measured": labels(scale), "measured_scale": scale}
    gflips = {sr._hm(16 * 60 - off): sum(1 for g in gate_rows if g["open"].get(off) is not None and
                                          g["open"][REF] is not None and g["open"][off] != g["open"][REF])
              for off in OFFSETS}
    zs = [x / math.sqrt((LABEL_AT - REF) / pc.SESSION_MIN) for _, _, mm, liq, x in z if mm == LABEL_AT - REF and liq]
    edges = [round(-3 + 0.2 * i, 1) for i in range(31)]
    hist = [0] * 30
    for x in zs:
        hist[max(0, min(29, int((x + 3) / 0.2)))] += 1
    res = {"generated": now.isoformat(timespec="seconds"), "sessions": [days[0], days[-1]], "n_sessions": len(days),
           "times": times, "accuracy": acc, "labels_1515": lab, "moves_to_1550": zsum,
           "z_hist_1515_liquid": {"unit": "sqrt(35/390) daily sigmas", "edges": edges, "counts": hist},
           "gate_flips_vs_1550": gflips, "gate_open_1550": sum(1 for g in gate_rows if g["open"][REF]),
           "yahoo_failures": bad, "rows": rows}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in ("accuracy", "labels_1515", "moves_to_1550", "gate_flips_vs_1550",
                                          "gate_open_1550")}, indent=1))


if __name__ == "__main__":
    main()
