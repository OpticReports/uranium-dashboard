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


LAST = {}


def holdings(k, d, bt):
    """weights held INTO the session after d: the monitor snapshot of d; on a day with no snapshot the
    last snapshot is carried forward (verifier A: the model's weights are wrong on such days - Composer
    did not rebalance 10-26..28 and the live book stayed in SOXL while the backtest moved to TLT).
    Before the first snapshot (07-07..07-15) the Composer backtest's weights are the only record."""
    s = (snaps.get(d) or {}).get("symphonies", {}).get(IDS[k])
    if s and s.get("holdings"):
        LAST[k] = dict(s["holdings"])
        return LAST[k], "snapshot"
    if k in LAST:
        return LAST[k], "carried"
    return {t: w.get(d, 0.0) for t, w in bt["w"].items() if w.get(d, 0.0) > 0}, "backtest"


PAY_LAG = {"ZVOL": 1, "PULS": 2}          # sessions from ex-date to pay date (addendum 38)


out = {}
bil_tr, _ = fund("BIL")
for k in ("HARV", "KMLM"):
    ds, val, da = live_series(k)
    bt = lib.load_bt(f"{D}/bt_{k}.json")
    src = {"snapshot": 0, "carried": 0, "backtest": 0}
    H = [None] + [holdings(k, ds[i - 1], bt) for i in range(1, len(ds))]       # H[i]: held into session i
    for i in range(1, len(ds)):
        src[H[i][1]] += 1
    leak = 0.0; leak_rows = []; inside_rows = []
    pnl_disp = pnl_bil = 0.0
    sl_tr = sl_disp = 0.0; sw_disp = 0.0
    part_ret = {"sleeve": [], "switcher": []}
    legs = {}
    for i in range(1, len(ds)):
        d0, d1 = ds[i - 1], ds[i]
        r_disp = da[i] / da[i - 1] - 1
        pnl_disp += val[i - 1] * r_disp
        pnl_bil += val[i - 1] * bil_tr.get(d1, 0.0)
        h = H[i][0]
        w_sl = r_sl_tr = r_sl_disp = 0.0
        for t, w in h.items():
            if t.startswith("$") or t == "cash":
                continue
            tr, px = fund(t)
            legs[t] = legs.get(t, 0.0) + val[i - 1] * w * tr.get(d1, 0.0)
            if t not in SLEEVE_FUNDS:
                continue
            w_sl += w; r_sl_tr += w * tr.get(d1, 0.0)
            leaked = False
            if d1 in DIV[t] and CLOSE[t].get(d0):
                usd = val[i - 1] * w / CLOSE[t][d0] * DIV[t][d1]
                # a distribution is credited INSIDE the symphony only if the fund is still held on the
                # pay date; otherwise Composer pays it to account cash (addenda 37-38)
                j = i + PAY_LAG.get(t, 1)
                still = j < len(H) and H[j][0].get(t, 0.0) > 1e-9 if j < len(H) else True
                if still:
                    inside_rows.append((d1, t, round(usd, 0)))
                else:
                    leaked = True; leak += usd; leak_rows.append((d1, t, round(usd, 0)))
            r_sl_disp += w * (px.get(d1, 0.0) if leaked else tr.get(d1, 0.0))
        sl_tr += val[i - 1] * r_sl_tr; sl_disp += val[i - 1] * r_sl_disp
        # the switcher part is the residual: what the symphony showed minus what its sleeve showed
        sw_disp += val[i - 1] * (r_disp - r_sl_disp)
        if w_sl > 1e-9:
            part_ret["sleeve"].append((d1, r_sl_tr / w_sl))
        if 1 - w_sl > 1e-9 and k == "KMLM":
            part_ret["switcher"].append((d1, (r_disp - r_sl_disp) / (1 - w_sl)))
    part = {"sleeve": [sl_disp, sl_tr], "switcher": [sw_disp, sw_disp]}
    assert abs(sl_disp + sw_disp - pnl_disp) < 1.0, (sl_disp, sw_disp, pnl_disp)      # parts add up
    twr_disp = da[-1] / da[0] - 1
    out[k] = {"from": ds[0], "to": ds[-1], "sessions": len(ds) - 1, "value_last": val[-1],
              "twr_displayed": twr_disp, "pnl_displayed_usd": pnl_disp,
              "distributions_paid_outside_usd": leak, "pnl_with_distributions_usd": pnl_disp + leak,
              "distribution_rows": leak_rows, "distributions_credited_inside": inside_rows, "tbills_same_dollars_usd": pnl_bil,
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
    twr_true = twr_disp + leak / (sum(val[:-1]) / len(val[:-1]))
    out[k]["twr_with_distributions_approx"] = twr_true
    out[k]["model_windows"] = {"n": len(wins), "share_below_live_displayed": sum(1 for x in wins if x <= twr_disp) / len(wins),
                               "share_below_live_with_distributions": sum(1 for x in wins if x <= twr_true) / len(wins),
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
out["KMLM"]["switcher_live_daily"] = out["KMLM"]["part_ret"]["switcher"]      # the residual series, for q4's live books
for k in out:
    out[k].pop("part_ret")
json.dump(out, open("out/q1_live.json", "w"), indent=1, default=str)
for k, v in out.items():
    print("==", k, v["from"], "->", v["to"], v["sessions"], "sessions; holdings from", v["holdings_source_days"])
    for kk in ("twr_displayed", "twr_with_distributions_approx", "pnl_displayed_usd", "distributions_paid_outside_usd", "pnl_with_distributions_usd", "distributions_credited_inside",
               "tbills_same_dollars_usd", "model_same_dates", "parts_usd_displayed_basis", "parts_usd_total_return",
               "legs_usd_total_return", "part_twr", "model_windows", "distribution_rows"):
        print("  ", kk, v[kk])
h = out["HARV"]
print("HARV dollars in switcher:", round(h["same_dollars_in_switcher_usd"]), "| in KMLM symphony:", round(h["same_dollars_in_kmlm_symphony_usd"]))
print("live stats:", json.dumps(h["live_stats"], default=lambda x: round(x, 4))[:900]); print("corr HARV/switcher live", h["live_corr_with_switcher"])
