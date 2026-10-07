"""Independent carry-gate + carry-income recompute (XBTUSD proxy) for the
three offset-0 windows, in ANALOGUE time (no shift), then compared with the
flips and funding totals the integrator reports (shifted dates)."""
import bisect, csv, json, os, time
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
CAGR = os.path.abspath(os.path.join(STRESS, "..", "cagr"))
BAR, DAY = 14400, 86400
res = json.load(open(os.path.join(STRESS, "results.json")))
def d(ts): return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
def load_rates(src):
    out = {}
    with open(os.path.join(STRESS, "data", f"funding_bitmex_{src}.csv")) as fh:
        for r in csv.DictReader(fh): out[int(r["ts_ms"]) // 1000] = float(r["rate_8h"])
    return out
eth = {}
with open(os.path.join(CAGR, "data", "bars_4h_ethusd.csv")) as fh:
    for r in csv.DictReader(fh): eth[int(r["ts_open_unix"])] = float(r["close"])
for src in ("XBTUSD", "ETHUSD"):
    rates = load_rates(src); st = sorted(rates); ann = [rates[s] * 1095 * 100 for s in st]
    pref = [0.0]
    for a in ann: pref.append(pref[-1] + a)
    for scen in ("COVID", "2008", "1999"):
        S = res["scenarios"][scen]
        p = S["paths"]["off+0"]
        a_ts = int(datetime.strptime(p["anchor_date"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        n = p["n_bars"]
        if st[0] > a_ts - 30 * DAY:
            print(src, scen, "not covered (first stamp", d(st[0]), ")"); continue
        run = (S["runs"] if src == "XBTUSD" else S["runs_quanto"])["K0.75"]["off+0"]
        t0 = res["meta"]["t0"]; shift = t0 - a_ts
        # simple independent sim in analogue time
        armed, on, qty, entry = True, True, 11.096, 2703.9 * (eth[a_ts] / 2577.55)   # entry scaled like the path? no: entry is today's 2703.9 (unscaled)
        entry = 2703.9
        scale = 2577.55 / eth[a_ts]
        cash = 30000 - qty * entry; cash0 = cash; fund = 0.0; fees = 0.0
        guard_until = -1e18; last_month = datetime.fromtimestamp(a_ts, tz=timezone.utc).strftime("%Y-%m")
        flips = []; si = bisect.bisect_left(st, a_ts + BAR)
        for j in range(n):
            T = a_ts + j * BAR; C = T + BAR; px = eth[T] * scale
            C_next = C + BAR if j + 1 < n else C + 1
            E = -(-T // 21600) * 21600
            while E < C:
                lo = bisect.bisect_left(st, E - 30 * DAY); hi = bisect.bisect_right(st, E); cnt = hi - lo
                if cnt and cnt / 90 >= 0.5:
                    m = (pref[hi] - pref[lo]) / cnt
                    if not armed and m >= 8 - 1e-9: armed = True
                    elif armed and m < 5 - 1e-9: armed = False
                E += 21600
            if on and qty > 0:
                usdc = 70000 + cash - cash0
                liq = (usdc / qty + entry) / 1.02
                if px >= liq * 0.85:
                    fee = qty * px * 11.5e-4; cash += qty * px + qty * (entry - px) - fee; fees += fee; qty = 0; on = False; guard_until = C + DAY
                    flips.append((C + shift, "margin_guard"))
            desired = armed and C >= guard_until
            if desired and not on:
                qty = 30000 / px; fee = qty * px * 11.5e-4; cash -= qty * px + fee; fees += fee; entry = px; on = True; flips.append((C + shift, "gate_on"))
            elif not desired and on:
                fee = qty * px * 11.5e-4; cash += qty * px + qty * (entry - px) - fee; fees += fee; qty = 0; on = False; flips.append((C + shift, "gate_off"))
            m = datetime.fromtimestamp(T, tz=timezone.utc).strftime("%Y-%m")
            if m != last_month:
                last_month = m
                if on and qty > 0 and abs(qty * px / 30000 - 1) > 0.25:
                    tq = 30000 / px; dq = tq - qty; fee = abs(dq) * px * 11.5e-4
                    if dq > 0: entry = (qty * entry + dq * px) / tq; cash -= dq * px
                    else: cash += -dq * px + (-dq) * (entry - px)
                    cash -= fee; fees += fee; qty = tq
            while si < len(st) and st[si] < C_next:
                if on and qty > 0:
                    fund += qty * px * rates[st[si]]; cash += qty * px * rates[st[si]]
                si += 1
        value = cash + qty * entry
        theirs = [(f["ts"], f["kind"]) for f in run["carry"]["flips"]]
        mine = flips
        print(f"{src} {scen}: mine flips {len(mine)} funding {fund:,.2f} fees {fees:,.2f} value {value:,.2f} | theirs flips {run['carry']['n_flips']} funding {run['carry']['funding_total']:,.2f} fees {run['carry']['fees']:,.2f} value {run['carry']['final_value']:,.2f} | flips equal: {[(d(a), b) for a, b in mine] == [(d(a), b) for a, b in theirs]}")
        if [(d(a), b) for a, b in mine] != [(d(a), b) for a, b in theirs]:
            print("   mine  ", [(d(a), b) for a, b in mine]); print("   theirs", [(d(a), b) for a, b in theirs])
