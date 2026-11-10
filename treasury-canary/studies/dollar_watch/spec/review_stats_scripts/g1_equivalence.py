"""Code-equivalence check on IN-SAMPLE DTWEXBGS only (D-0, already seen).
Compares firing DATES of decel_realtime.py's logic (calendar B∩V∩Y, loop to n-2) with
build_reference.py's scramble_firings (calendar B∩Y, loop to n-1). Prints firing dates and
roc20 max only, plus the committed json's further-rise numbers for G1 comparison.
No D-1 currency and no DXY 1973-2005 data are read."""
import csv, json, os, sys
import numpy as np

FRED = sys.argv[1]
DATA = sys.argv[2]


def fredd(fid):
    o = {}
    for r in csv.DictReader(open(os.path.join(FRED, fid + ".csv"))):
        v = r[fid]
        if v not in ("", "."):
            o[r["observation_date"]] = float(v)
    return o


bd, vix, y10 = fredd("DTWEXBGS"), fredd("VIXCLS"), fredd("DGS10")


def realtime_style(days, rearm):
    B = np.array([bd[d] for d in days]); Y = np.array([y10[d] for d in days])
    roc = np.full(len(B), np.nan)
    for k in range(20, len(B)):
        roc[k] = B[k] / B[k - 20] - 1
    fires = []; last = -999; last_mx = 0.0
    for k in range(80, len(B) - 1):
        mx = np.nanmax(roc[k - 60:k + 1]); kmx = k - 60 + int(np.nanargmax(roc[k - 60:k + 1]))
        if mx >= 0.04 and roc[k] <= 0.5 * mx and B[k] >= 0.97 * max(B[k - 60:k + 1]) and Y[k] < Y[max(0, kmx - 20)] and (k - last > 120 or (rearm and mx >= 1.5 * last_mx)):
            last = k; last_mx = mx
            pk = k + int(np.argmax(B[k:min(len(B), k + 250)]))
            # also the SPEC's S1 window (k, k+250] max, for window-definition comparison only (in-sample)
            hi = min(len(B) - 1, k + 250)
            mx_spec = B[k + 1:hi + 1].max() if hi > k else np.nan
            fires.append((days[k], round(100 * mx, 1), round(100 * (B[pk] / B[k] - 1), 1), round(100 * (mx_spec / B[k] - 1), 1)))
    return fires


cal3 = sorted(d for d in bd if d in vix and d in y10)
cal2 = sorted(d for d in bd if d in y10)
print("calendar sizes: B∩V∩Y", len(cal3), " B∩Y", len(cal2), " B", len(bd))
for rearm in (False, True):
    f3 = realtime_style(cal3, rearm); f2 = realtime_style(cal2, rearm)
    print("\nrearm" if rearm else "\nunpatched")
    print("  B∩V∩Y (decel_realtime):", [(d, m) for d, m, _, _ in f3])
    print("  B∩Y   (build_reference):", [(d, m) for d, m, _, _ in f2])
    print("  same dates:", [d for d, *_ in f3] == [d for d, *_ in f2])
    print("  further rise [k,k+250) vs SPEC S1 window (k,k+250]:", [(d, a, b) for d, _, a, b in f3])

for fn in ("decel_realtime.json", "decel_realtime_rearm.json"):
    J = json.load(open(os.path.join(DATA, fn)))
    print("\ncommitted", fn, [(f["fire"], f["roc20_max_pct"], f["dollar_more_rise_pct"]) for f in J])

# sigma_B and the '2.7 sigma' claim
d = sorted(bd); x = np.log(np.array([bd[k] for k in d]))
lr = np.diff(x)
sel = [i for i in range(1, len(d)) if "2006-01-03" <= d[i] <= "2026-10-23"]
s = np.std(np.diff(x)[[i - 1 for i in sel]], ddof=1)
print("\nsigma_B daily log change (B's own calendar, 2006-01-03..2026-10-23): %.5f" % s)
print("20-day sigma (sqrt20): %.4f ; 4%% gate in 20d-sigma units: %.2f" % (s * 20 ** 0.5, 0.04 / (s * 20 ** 0.5)))
r20 = x[20:] - x[:-20]
print("empirical sd of overlapping 20-day log changes: %.4f ; gate in those units: %.2f" % (np.std(r20, ddof=1), np.log(1.04) / np.std(r20, ddof=1)))
