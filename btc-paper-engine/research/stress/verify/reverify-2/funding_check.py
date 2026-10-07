"""Independent recompute of the BTC perp funding booked by stress.Executor
(SERIOUS finding #3) from each saved run file: trades (entry/exit ts, qty,
side) x spliced closes x BitMEX XBTUSD 8h rates shifted by (t0 - anchor_ts).
Convention under test: a stamp is paid at the first 4h close at or after it;
a position is held at close C of bar T=C-4h iff entry_ts <= T and
(exit_ts is None or exit_ts > T); long pays a positive rate."""
import csv, glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
BAR = 14400
rates = {}
with open(os.path.join(STRESS, "data", "funding_bitmex_XBTUSD.csv")) as fh:
    for r in csv.DictReader(fh):
        rates[int(r["ts_ms"]) // 1000] = float(r["rate_8h"])
files = sorted(glob.glob(os.path.join(STRESS, "runs", "*_bfund_*.json")))
bad = 0
rows = []
for f in files:
    r = json.load(open(f))
    assert r["btc_funding_modelled"], f
    shift = r["t0"] - r["anchor_ts"]
    closes = {ts: c for ts, c in r["spliced_closes"]}
    n = r["n_path_bars"]
    last_close = r["t0"] + n * BAR
    # stamps on today's grid within the path
    by_close = {}
    for s, rate in rates.items():
        s2 = s + shift
        if s2 <= r["t0"] or s2 > last_close:
            continue
        c = -(-s2 // BAR) * BAR
        by_close.setdefault(c, []).append(rate)
    tot = {"pullback": 0.0, "trend": 0.0}
    stamps = 0
    per_trade = []
    for t in r["trades"]:
        sgn = 1.0 if t["side"] == "L" else -1.0
        e, x = t["entry_ts"], t["exit_ts"]
        ft = 0.0
        for c, rl in by_close.items():
            T = c - BAR
            if e <= T and (x is None or x > T):
                px = closes[T]
                for rate in rl:
                    ft += -sgn * t["qty"] * px * rate
                    stamps += 1
        tot[t["leg"]] += ft
        per_trade.append((ft, t["funding"]))
    total = tot["pullback"] + tot["trend"]
    d_tot = total - r["btc_funding_total"]
    d_pb = tot["pullback"] - r["btc_funding_by_leg"]["pullback"]
    d_tr = tot["trend"] - r["btc_funding_by_leg"]["trend"]
    d_st = stamps - r["btc_funding_stamps"]
    worst_trade = max(abs(a - b) for a, b in per_trade) if per_trade else 0.0
    cum_last = r["btc_funding_cum"][-1]
    ok = abs(d_tot) < 0.5 and abs(d_pb) < 0.5 and abs(d_tr) < 0.5 and d_st == 0 and worst_trade < 0.02 and abs(cum_last - r["btc_funding_total"]) < 0.01
    bad += (not ok)
    rows.append((os.path.basename(f), round(total, 2), r["btc_funding_total"], round(d_tot, 3), round(d_pb, 3), round(d_tr, 3), d_st, round(worst_trade, 3), ok))
for row in rows:
    print(*row)
print("files", len(files), "mismatches", bad)
# sign check on a known stamp: deepest negative XBTUSD rate in the COVID window
r = json.load(open(os.path.join(STRESS, "runs", "COVID_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json")))
shift = r["t0"] - r["anchor_ts"]
win = {s: v for s, v in rates.items() if r["anchor_ts"] <= s <= r["anchor_ts"] + r["n_path_bars"] * BAR}
smin = min(win, key=win.get)
import time
print("most negative XBTUSD stamp in the COVID window:", time.strftime("%Y-%m-%d %H:%M", time.gmtime(smin)), win[smin], "-> on grid", time.strftime("%Y-%m-%d %H:%M", time.gmtime(smin + shift)))
c = -(-(smin + shift) // BAR) * BAR
held = [t for t in r["trades"] if t["entry_ts"] <= c - BAR and (t["exit_ts"] is None or t["exit_ts"] > c - BAR)]
for t in held:
    print("  held:", t["leg"], t["side"], "qty", t["qty"], "funding on this trade", t["funding"], "-> expected sign for a", t["side"], "at a negative rate:", "pays (negative)" if t["side"] == "S" else "receives (positive)")
