"""Q3 step 1 (PREREG.md "Macro"): do six pre-named macro states predict the forward return of the
switcher's two sides? Sample 2010-03-12 (SOXL's second day) to the latest close; every state is known
the session BEFORE the day it is used (OFR two sessions). Writes out/macro.json.

Targets, over the next 1, 5 and 21 sessions from the close of day t:
  on    the risk-on basket (TECL and SOXL, equal, rebalanced daily) minus T-bills (BIL)
  spread  risk-on minus risk-off (SQQQ and TLT, equal, rebalanced daily)
Test per (input, target, horizon): Newey-West regression of the forward return on the 0/1 state, the
walk-forward out-of-sample R2 against the expanding mean (first third burn-in, refit every 21 sessions
on closed windows), Holm across the 36 tests, and a mirror: the state circularly shifted 1,000 times.
An input "works" only if Holm p < 0.05 AND out-of-sample R2 > 0 (on any of its six tests).
Point in time: prices, the curve and TIPS yields are used at a one-session lag; the OFR index at two; the
broad dollar index at six, because it is released weekly (corrected after review: at one session its
21-session t was 1.5, at six 1.2). The OFR index and the FRED series are the latest vintage: OFR revises
its index, so the stress state is not exactly what was published on the day (DEVIATIONS.md 7).
"""
import csv
import io
import json
import math
import os
import random
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "zvol_2026-11"))
import data  # noqa: E402
import ksim as ks  # noqa: E402
import lib  # noqa: E402

END = "2026-11-20"
MAC = data.SCRATCH + "/kmlm/macro"
SHIFTS, SEED = 1000, 20261120


def curl(url, path):
    ua = [] if "stlouisfed.org" in url else ["-A", "Mozilla/5.0"]
    if not os.path.exists(path):
        r = subprocess.run(["curl", "-sSL", "--http1.1", "--retry", "2", "--retry-delay", "3", "--retry-all-errors",
                            "--connect-timeout", "20", "--max-time", "90"] + ua + ["-o", path, url], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 200:
            raise RuntimeError(f"fetch failed {url}: {r.stderr.strip()[:200]}")
    return path


def fred(sid):
    out = {}
    for row in csv.reader(io.StringIO(open(curl(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", f"{MAC}/{sid}.csv")).read())):
        if len(row) == 2 and re.match(r"\d{4}-\d{2}-\d{2}", row[0]):
            try:
                out[row[0]] = float(row[1])
            except ValueError:
                pass
    return out


def ofr():
    rd = csv.reader(io.StringIO(open(curl("https://www.financialresearch.gov/financial-stress-index/data/fsi.csv", f"{MAC}/ofr_fsi.csv")).read()))
    hdr = next(rd)
    col = next((i for i, h in enumerate(hdr) if h.strip().upper() in ("OFR FSI", "OFRFSI", "FSI")), 1)
    out = {}
    for row in rd:
        if row and re.match(r"\d{4}-\d{2}-\d{2}", row[0]):
            try:
                out[row[0]] = float(row[col])
            except (ValueError, IndexError):
                pass
    return out


def asof(series, days, lag):
    """{day: the series' last value published at least `lag` sessions before that day}"""
    ks_, out, j, last = sorted(series), {}, 0, None
    for i, d in enumerate(days):
        cut = days[i - lag] if i >= lag else None
        while cut is not None and j < len(ks_) and ks_[j] <= cut:
            last = series[ks_[j]]
            j += 1
        out[d] = last if cut is not None else None
    return out


def states(days):
    os.makedirs(MAC, exist_ok=True)
    hyg, ief, spy, tlt = (data.series(t, END) for t in ("HYG", "IEF", "SPY", "TLT"))
    ratio = {d: hyg[d] / ief[d] for d in hyg if d in ief}
    r50 = ks.sma_series(ratio, 50)
    rs, rt = data.rets(spy), data.rets(tlt)
    cd = [d for d in sorted(rs) if d in rt]
    corr60 = {}
    for i in range(59, len(cd)):
        a = np.array([rs[x] for x in cd[i - 59:i + 1]])
        b = np.array([rt[x] for x in cd[i - 59:i + 1]])
        corr60[cd[i]] = float(np.corrcoef(a, b)[0, 1])
    usd = fred("DTWEXBGS")
    u50 = ks.sma_series(usd, 50)
    tips = fred("DFII10")
    td = sorted(tips)
    tchg = {td[i]: tips[td[i]] - tips[td[i - 20]] for i in range(20, len(td))}
    raw = {
        "M1_credit": ({d: ratio[d] > r50[d] for d in ratio if r50.get(d) is not None}, 1),
        "M2_stress": ({d: v < 0 for d, v in ofr().items()}, 2),
        "M3_stockbond": ({d: v < 0 for d, v in corr60.items()}, 1),
        "M4_dollar": ({d: usd[d] < u50[d] for d in usd if u50.get(d) is not None}, 6),   # released weekly (review)
        "M5_curve": ({d: v > 0 for d, v in fred("T10Y3M").items()}, 1),
        "M6_realrate": ({d: v < 0.25 for d, v in tchg.items()}, 1),
    }
    return {k: asof({d: float(v) for d, v in s.items()}, days, lag) for k, (s, lag) in raw.items()}


def targets():
    P = {t: data.series(t, END) for t in ("TECL", "SOXL", "SQQQ", "TLT", "BIL")}
    days = sorted(set.intersection(*(set(v) for v in P.values())))
    r = {t: {days[i]: P[t][days[i]] / P[t][days[i - 1]] - 1 for i in range(1, len(days))} for t in P}
    days = days[1:]
    on = np.array([0.5 * (r["TECL"][d] + r["SOXL"][d]) - r["BIL"][d] for d in days])
    off = np.array([0.5 * (r["SQQQ"][d] + r["TLT"][d]) - r["BIL"][d] for d in days])
    return days, {"on": on, "spread": on - off}


def fwd(x, h):
    """forward h-session compounded return from the close of each day (nan where the window is open)"""
    lg = np.log1p(x)
    c = np.concatenate([[0.0], np.cumsum(lg)])
    out = np.full(len(x), np.nan)
    out[:len(x) - h] = np.expm1(c[h + 1:] - c[1:len(x) - h + 1])
    return out


def oos_r2(xs, ys, h):
    n = len(ys)
    start = n // 3
    se_f = se_m = 0.0
    fit = None
    for i in range(start, n):
        if (i - start) % 21 == 0:
            xt, yt = xs[:max(2, i - h)], ys[:max(2, i - h)]
            m1 = yt[xt > 0.5].mean() if (xt > 0.5).any() else yt.mean()
            m0 = yt[xt <= 0.5].mean() if (xt <= 0.5).any() else yt.mean()
            fit = (m1, m0, yt.mean())
        f = fit[0] if xs[i] > 0.5 else fit[1]
        se_f += (ys[i] - f) ** 2
        se_m += (ys[i] - fit[2]) ** 2
    return 1 - se_f / se_m


def main():
    days, tg = targets()
    st = states(days)
    rng = random.Random(SEED)
    out = {"sample": [days[0], days[-1]], "inputs": {}, "share_on": {}}
    tests = []
    for name, s in st.items():
        x_all = np.array([np.nan if s[d] is None else s[d] for d in days])
        out["share_on"][name] = float(np.nanmean(x_all))
        out["inputs"][name] = {}
        for tname, y in tg.items():
            for h in (1, 5, 21):
                f = fwd(y, h)
                ok = ~np.isnan(x_all) & ~np.isnan(f)
                xs, ys = x_all[ok], f[ok]
                b, t, r2 = lib.nw_t(ys, xs, lags=max(h - 1, 5))
                p = math.erfc(abs(t) / math.sqrt(2))
                n = len(xs)
                ts = []
                for _ in range(SHIFTS):
                    k = rng.randrange(60, n - 60)
                    ts.append(abs(lib.nw_t(ys, np.roll(xs, k), lags=max(h - 1, 5))[1]))
                res = {"n": int(n), "on_mean": float(ys[xs > 0.5].mean()), "off_mean": float(ys[xs <= 0.5].mean()),
                       "diff": float(b), "t_nw": float(t), "p": p, "oos_r2": float(oos_r2(xs, ys, h)),
                       "mirror_p": float(np.mean(np.array(ts) >= abs(t)))}
                out["inputs"][name][f"{tname}.h{h}"] = res
                tests.append((p, name, f"{tname}.h{h}"))
    tests.sort()
    m, run = len(tests), 0.0
    for k, (p, name, key) in enumerate(tests):
        adj = min(1.0, max(run, (m - k) * p))
        run = adj
        r = out["inputs"][name][key]
        r["p_holm"] = adj
        r["works"] = bool(adj < 0.05 and r["oos_r2"] > 0)
    out["works"] = sorted({name for name, v in out["inputs"].items() if any(r["works"] for r in v.values())})
    out["current"] = {name: s[days[-1]] for name, s in st.items()}
    json.dump(out, open(os.path.join(HERE, "out", "macro.json"), "w"), indent=1)
    print("sample", out["sample"], "| tests", m)
    for name, v in out["inputs"].items():
        print(f"{name} (on {out['share_on'][name]:.0%} of days; now {'on' if out['current'][name] else 'off'})")
        for key, r in v.items():
            print(f"   {key:10s} n={r['n']} on {r['on_mean']*1e4:+7.1f}bp off {r['off_mean']*1e4:+7.1f}bp diff {r['diff']*1e4:+7.1f}bp "
                  f"t {r['t_nw']:+.2f} p_holm {r['p_holm']:.3f} OOS R2 {r['oos_r2']:+.4f} mirror p {r['mirror_p']:.3f} works={r['works']}")
    print("inputs that work:", out["works"] or "none")


if __name__ == "__main__":
    main()
