#!/usr/bin/env python3
"""Responsiveness study v2 — HYG guard intraday (IBKR) vs 3:45 window (Composer).

QA fixes vs v1 (hostile audit findings 2/3/8):
- Episodes evaluated ONLY on adjacent-trading-day pairs while the harvester's
  ZVOL sleeve is actually on (tdvm weight >= 1% on BOTH days, consecutive on
  the HYG calendar). v1 compared today's HYG low against closes up to 50
  calendar days stale across sleeve-off gaps — 8 of its 9 "episodes" and
  +104pp of phantom holding return were artifacts. Gaps reset guard state.
- Dividend consistency: intraday exit return adds back the imputed ex-date
  distribution (div = c0*a1/a0 - c1), so the IBKR leg is not stripped of
  distributions the seller still receives.
- Fill estimate: mid(open, close) with [open, close] shown as the estimate
  range and the day LOW as the true worst case (the touch-time fill is not
  bounded by the close; the close is not knowable at fill time — this is an
  estimate, not a simulation).
"""
import json, os, datetime

SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/exec_study"
OUT = os.path.dirname(os.path.abspath(__file__))
EPOCH0 = 719163

def load(t):
    res = json.load(open(f"{SC}/px/{t}.json"))
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    out = {}
    for i, ts in enumerate(res["timestamp"]):
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()
        if q["close"][i] is not None:
            out[d] = {"o": q["open"][i], "h": q["high"][i], "l": q["low"][i],
                      "c": q["close"][i], "a": adj[i] or q["close"][i]}
    return out

hyg, zvol = load("HYG"), load("ZVOL")
bt = json.load(open(f"{SC}/bt-HARV.json"))
zw = {datetime.date.fromordinal(EPOCH0+int(d)).isoformat(): v
      for d, v in bt["tdvm_weights"].get("ZVOL", {}).items()}
cal = sorted(set(hyg) & set(zvol))
idx = {d: i for i, d in enumerate(cal)}

pairs = []           # adjacent trading-day pairs with sleeve ON both days
for d in sorted(zw):
    if zw[d] < 0.01 or d not in idx: continue
    i = idx[d]
    if i == 0: continue
    d0 = cal[i-1]
    if zw.get(d0, 0) >= 0.01:
        pairs.append((d0, d))

ep, ret_c, ret_i = [], 1.0, 1.0
held_c = held_i = True
prev_d1 = None
for d0, d1 in pairs:
    if prev_d1 is not None and d0 != prev_d1:      # gap -> sleeve re-armed
        held_c = held_i = True
    prev_d1 = d1
    hpc = hyg[d0]["c"]
    touch = hyg[d1]["l"] / hpc - 1 <= -0.01
    close_trip = hyg[d1]["c"] / hpc - 1 <= -0.01
    zr_full = zvol[d1]["a"] / zvol[d0]["a"] - 1
    r_c = zr_full if held_c else 0.0
    if held_i and touch:
        div = zvol[d0]["c"] * (zvol[d1]["a"]/zvol[d0]["a"]) - zvol[d1]["c"]
        est = (zvol[d1]["o"] + zvol[d1]["c"]) / 2
        r_i = (est + div) / zvol[d0]["c"] - 1
        r_open = (zvol[d1]["o"] + div) / zvol[d0]["c"] - 1
        r_close = zr_full
        r_low = (zvol[d1]["l"] + div) / zvol[d0]["c"] - 1
        ep.append({"date": d1, "close_confirmed": close_trip,
                   "zvol_fullday_pct": round(zr_full*100, 2),
                   "ibkr_est_pct": round(r_i*100, 2),
                   "est_range_pct": [round(r_open*100, 2), round(r_close*100, 2)],
                   "worst_case_low_pct": round(r_low*100, 2)})
    else:
        r_i = zr_full if held_i else 0.0
    ret_c *= 1 + r_c; ret_i *= 1 + r_i
    held_c = not close_trip
    held_i = (not touch) if held_i else (not close_trip)

print(f"adjacent sleeve-on pairs: {len(pairs)} (of {sum(1 for d in zw if zw[d]>=0.01)} sleeve days)")
print(f"guard episodes: {len(ep)}; whipsaws (recovered by close): "
      f"{sum(1 for e in ep if not e['close_confirmed'])}")
print(f"ZVOL-sleeve cumulative, Composer close-guard: {ret_c-1:+.2%}")
print(f"ZVOL-sleeve cumulative, IBKR intraday-guard:  {ret_i-1:+.2%}")
print(f"intraday edge: {(ret_i/ret_c-1)*100:+.2f} pp over the window")
for e in ep: print(" ", e)
json.dump({"pairs": len(pairs), "episodes": ep,
           "ret_composer": round(ret_c-1, 4), "ret_ibkr": round(ret_i-1, 4)},
          open(f"{OUT}/guard_timing_results.json", "w"), indent=1)
