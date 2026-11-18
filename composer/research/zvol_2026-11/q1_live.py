"""Q1: the live record in dollars. Inputs (frozen copies under DATA): live.json (Composer per-symphony
series), snapshots.json (daily monitor snapshots from git history), bt_*.json (Composer backtests).
Usage: python3 q1_live.py DATA_DIR   (DATA_DIR holds live.json, snapshots.json, bt_*.json and cache/)"""
import datetime as dt, json, math, sys
import lib

D = sys.argv[1]; C = D + "/cache"
live = json.load(open(D + "/live.json")); snaps = json.load(open(D + "/snapshots.json"))
IDS = {"HG": "mbkiXcuNDjueXpiox5Av", "KMLM": "YPTSJFJwD2ZKfAeYJUbW", "SLEEVE": "nNdBk7hc5NiBzeRvbI5T", "HARV": "ORQNCfZnA18wmsMWVhf8"}
SLEEVE_FUNDS = ("ZVOL", "VXZ", "PULS")
TR = {}; PX = {}; DIV = {}; CLOSE = {}


def fund(t):
    if t not in TR:
        y = lib.load(t, C)
        TR[t] = lib.rets({d: (v["adj"] or v["close"]) for d, v in y["rows"].items()})
        PX[t] = lib.rets({d: v["close"] for d, v in y["rows"].items()})
        DIV[t] = dict(y["divs"]); CLOSE[t] = {d: v["close"] for d, v in y["rows"].items()}
    return TR[t], PX[t]


def live_series(k):
    v = live[k]
    ds = [dt.datetime.fromtimestamp(m / 1000, tz=dt.timezone.utc).date().isoformat() for m in v["epoch_ms"]]
    keep = [i for i, d in enumerate(ds) if d <= lib.END]
    return [ds[i] for i in keep], [v["series"][i] for i in keep], [v["deposit_adjusted_series"][i] for i in keep]


def holdings(k, d, bt):
    """weights held INTO the session after d: the monitor snapshot of d if there is one, else the
    Composer backtest's weights for d (the shadow ledger shows they agree on all but knife-edge days)"""
    s = (snaps.get(d) or {}).get("symphonies", {}).get(IDS[k])
    if s and s.get("holdings"):
        return dict(s["holdings"]), "snapshot"
    return {t: w.get(d, 0.0) for t, w in bt["w"].items() if w.get(d, 0.0) > 0}, "backtest"


out = {}
bil_tr, _ = fund("BIL")
for k in ("HARV", "KMLM"):
    ds, val, da = live_series(k)
    bt = lib.load_bt(f"{D}/bt_{k}.json")
    rows = []; src = {"snapshot": 0, "backtest": 0}
    leak = 0.0; leak_rows = []
    pnl_disp = pnl_tr = pnl_bil = 0.0
    part = {"sleeve": [0.0, 0.0], "switcher": [0.0, 0.0]}       # [displayed-basis $, total-return $]
    part_ret = {"sleeve": [], "switcher": []}                   # daily TR of each part, own capital
    legs = {}
    for i in range(1, len(ds)):
        d0, d1 = ds[i - 1], ds[i]
        r_disp = da[i] / da[i - 1] - 1
        pnl_disp += val[i - 1] * r_disp
        pnl_bil += val[i - 1] * bil_tr.get(d1, 0.0)
        h, s = holdings(k, d0, bt); src[s] += 1
        tot = sum(h.values()) or 1.0
        tr_day = 0.0
        acc = {"sleeve": [0.0, 0.0, 0.0], "switcher": [0.0, 0.0, 0.0]}
        for t, w in h.items():
            if t.startswith("$") or t == "cash":
                continue
            tr, px = fund(t)
            p = "sleeve" if t in SLEEVE_FUNDS else "switcher"
            acc[p][0] += w; acc[p][1] += w * px.get(d1, 0.0); acc[p][2] += w * tr.get(d1, 0.0)
            legs[t] = legs.get(t, 0.0) + val[i - 1] * w * tr.get(d1, 0.0)
            tr_day += w * (tr.get(d1, 0.0) - px.get(d1, 0.0))
            if d1 in DIV[t] and CLOSE[t].get(d0):
                usd = val[i - 1] * w / CLOSE[t][d0] * DIV[t][d1]
                leak += usd; leak_rows.append((d1, t, round(usd, 0)))
        for p in part:
            part[p][0] += val[i - 1] * acc[p][1]; part[p][1] += val[i - 1] * acc[p][2]
            if acc[p][0] > 1e-9:
                part_ret[p].append((d1, acc[p][2] / acc[p][0]))
        pnl_tr += val[i - 1] * (r_disp + tr_day)
    twr_disp = da[-1] / da[0] - 1
    out[k] = {"from": ds[0], "to": ds[-1], "sessions": len(ds) - 1, "value_last": val[-1],
              "twr_displayed": twr_disp, "pnl_displayed_usd": pnl_disp,
              "distributions_paid_outside_usd": leak, "pnl_with_distributions_usd": pnl_disp + leak,
              "distribution_rows": leak_rows, "tbills_same_dollars_usd": pnl_bil,
              "holdings_source_days": src, "parts_usd_displayed_basis": {p: v[0] for p, v in part.items()},
              "parts_usd_total_return": {p: v[1] for p, v in part.items()},
              "legs_usd_total_return": {t: round(v, 0) for t, v in sorted(legs.items(), key=lambda x: x[1])},
              "part_twr": {p: (math.prod(1 + r for _, r in v) - 1, len(v)) for p, v in part_ret.items()},
              "part_ret": part_ret}
    # the model over the same dates
    m = [bt["ret"][d] for d in ds[1:] if d in bt["ret"]]
    out[k]["model_same_dates"] = math.prod(1 + x for x in m) - 1
    # how ordinary is this window for the model? all same-length windows of the real-era backtest
    n = len(ds) - 1; allr = [bt["ret"][d] for d in bt["dates"][1:]]
    wins = [math.prod(1 + x for x in allr[j:j + n]) - 1 for j in range(0, len(allr) - n + 1)]
    out[k]["model_windows"] = {"n": len(wins), "share_below_live_displayed": sum(1 for x in wins if x <= twr_disp) / len(wins),
                               "p10": sorted(wins)[int(.1 * len(wins))], "median": sorted(wins)[len(wins) // 2],
                               "p90": sorted(wins)[int(.9 * len(wins))], "share_negative": sum(1 for x in wins if x < 0) / len(wins)}

# HARV's dollars in the switcher part of KMLM over HARV's own dates (live), and in the whole KMLM symphony
hd, hval, hda = live_series("HARV")
sw = dict(out["KMLM"]["part_ret"]["switcher"]); kd, kval, kda = live_series("KMLM")
kret = {kd[i]: kda[i] / kda[i - 1] - 1 for i in range(1, len(kd))}
alt_sw = sum(hval[i - 1] * sw.get(hd[i], 0.0) for i in range(1, len(hd)))
alt_k = sum(hval[i - 1] * kret.get(hd[i], 0.0) for i in range(1, len(hd)))
out["HARV"]["same_dollars_in_switcher_usd"] = alt_sw
out["HARV"]["same_dollars_in_kmlm_symphony_usd"] = alt_k
sw_r = [sw.get(d, 0.0) for d in hd[1:]]; k_r = [kret.get(d, 0.0) for d in hd[1:]]; h_r = [hda[i] / hda[i - 1] - 1 for i in range(1, len(hd))]
out["HARV"]["live_stats"] = {"harv": lib.stats(h_r), "switcher": lib.stats(sw_r), "kmlm_symphony": lib.stats(k_r)}
out["HARV"]["live_corr_with_switcher"] = lib.corr(h_r, sw_r)
for k in out:
    out[k].pop("part_ret")
json.dump(out, open("out/q1_live.json", "w"), indent=1, default=str)
for k, v in out.items():
    print("==", k, v["from"], "->", v["to"], v["sessions"], "sessions; holdings from", v["holdings_source_days"])
    for kk in ("twr_displayed", "pnl_displayed_usd", "distributions_paid_outside_usd", "pnl_with_distributions_usd",
               "tbills_same_dollars_usd", "model_same_dates", "parts_usd_displayed_basis", "parts_usd_total_return",
               "legs_usd_total_return", "part_twr", "model_windows", "distribution_rows"):
        print("  ", kk, v[kk])
h = out["HARV"]
print("HARV dollars in switcher:", round(h["same_dollars_in_switcher_usd"]), "| in KMLM symphony:", round(h["same_dollars_in_kmlm_symphony_usd"]))
print("live stats:", json.dumps(h["live_stats"], default=lambda x: round(x, 4))[:900]); print("corr HARV/switcher live", h["live_corr_with_switcher"])
