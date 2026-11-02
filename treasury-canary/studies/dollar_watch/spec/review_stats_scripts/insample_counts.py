"""Mechanical COUNTS on IN-SAMPLE DTWEXBGS 2006-2026 only (already seen, D-0).
Episodes (maximal gate-on runs, merging gaps < 20), firings, share of episodes that fire, |E_f|,
and whether any episode carries 2+ firings. No outcome (S1) is computed.
Variants: (a) frozen rule s=1 with the US-10y condition; (b) s=1 without it;
(c) the D-1 transposition applied to the broad dollar itself (trailing 756d sigma ending k-61,
clip [0.25,8], no yield condition)."""
import csv, os, sys
import numpy as np

FRED = sys.argv[1]


def fredd(fid):
    o = {}
    for r in csv.DictReader(open(os.path.join(FRED, fid + ".csv"))):
        v = r[fid]
        if v not in ("", "."):
            o[r["observation_date"]] = float(v)
    return o


bd, y10 = fredd("DTWEXBGS"), fredd("DGS10")
days = sorted(d for d in bd if d in y10)
B = np.array([bd[d] for d in days]); Y = np.array([y10[d] for d in days]); n = len(B)
lr = np.diff(np.log(B))
sigB = np.std(lr, ddof=1)
roc = np.full(n, np.nan); roc[20:] = B[20:] / B[:-20] - 1


def run(mode):
    s = np.full(n, np.nan)
    if mode == "trailing":
        for k in range(817, n):
            w = lr[k - 61 - 756:k - 61]       # log changes ending at k-61
            s[k] = np.clip(np.std(w, ddof=1) / sigB, 0.25, 8)
        k0 = 817
    else:
        s[:] = 1.0; k0 = 80
    use_y = (mode == "frozen")
    gate = np.zeros(n, bool); near = np.zeros(n, bool); dec = np.zeros(n, bool); ycond = np.ones(n, bool)
    for k in range(k0, n):
        w = roc[k - 60:k + 1]; mx = np.nanmax(w); kmx = k - 60 + int(np.nanargmax(w))
        gate[k] = mx >= 0.04 * s[k]
        dec[k] = roc[k] <= 0.5 * mx
        near[k] = B[k] >= (1 - 0.03 * s[k]) * B[k - 60:k + 1].max()
        if use_y:
            ycond[k] = Y[k] < Y[max(0, kmx - 20)]
    fires = []; last = -10 ** 9
    for k in range(k0, n - 1):
        if gate[k] and dec[k] and near[k] and ycond[k] and k - last > 120:
            fires.append(k); last = k
    # episodes: maximal gate-on runs, merging runs < 20 trading days apart
    runs = []; k = k0
    while k < n:
        if gate[k]:
            j = k
            while j + 1 < n and gate[j + 1]:
                j += 1
            runs.append([k, j]); k = j + 1
        else:
            k += 1
    eps = []
    for a, b in runs:
        if eps and a - eps[-1][1] - 1 < 20:
            eps[-1][1] = b
        else:
            eps.append([a, b])
    out = []
    prev = -10 ** 9
    for f in fires:
        e = [ep for ep in eps if ep[0] <= f <= ep[1]][0]
        Ef = [k for k in range(e[0], e[1] + 1) if gate[k] and near[k] and k - prev > 120]
        nf_in_ep = sum(1 for g in fires if e[0] <= g <= e[1])
        out.append((days[f], days[e[0]], days[e[1]], e[1] - e[0] + 1, len(Ef), nf_in_ep,
                    round(float(s[f]), 2)))
        prev = f
    ep_with_fire = sum(1 for e in eps if any(e[0] <= f <= e[1] for f in fires))
    yrs = (len(range(k0, n))) / 250.0
    print(f"\n[{mode}] eval years ~{yrs:.1f}; episodes {len(eps)} ({len(eps)/yrs:.2f}/yr); firings {len(fires)}; "
          f"episodes with >=1 firing {ep_with_fire} ({ep_with_fire/len(eps):.0%})")
    for row in out:
        print("   fire %s  episode %s..%s (%d d)  |E_f|=%d  firings-in-episode=%d  s=%.2f" % row)
    lens = [e[1] - e[0] + 1 for e in eps]
    print("   episode lengths (trading days):", sorted(lens))


for mode in ("frozen", "no_yield", "trailing"):
    run(mode)
