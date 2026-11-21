"""Dynamic sleeve weight (PREREG.md): the sleeve at 50% while a market state is on and 15% while it is off
(and the mirror), against the book at one constant sleeve weight equal to the policy's own average.
Writes out/dynsleeve.json."""
import bisect
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("macro_2026-11", "forward_2026-11"):
    sys.path.insert(0, os.path.join(HERE, "..", p))
import fdata as fd  # noqa: E402
import mdata as md  # noqa: E402

w = md.w
HIGH, LOW, COST, NWL = 0.50, 0.15, 5.856e-4, 63
days = md.sessions()
pos = {d: i for i, d in enumerate(days)}
E = md.engines()
LATE = fd.late_engines()
PRIMARY = ["VA", "V3", "RA", "R1", "OA", "SU.SPY.s.50", "SD.SPY.s.50", "SU.QQQ.s.50", "TA.SPY"]
SAMPLES = {"verdict": ("2015-06-01", "9999"), "shape": ("1994-06-02", "2015-06-01"), "real": ("2021-06-02", "9999")}


def ema(x, n):
    out = np.full(len(x), np.nan)
    a, last, k = 2.0 / (n + 1), np.nan, 0
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        last = v if np.isnan(last) else a * v + (1 - a) * last
        k += 1
        if k >= n:
            out[i] = last
    return out


def roll_q(x, n, q):
    """q-quantile of the trailing n values (current included); nan until n valid values"""
    out = np.full(len(x), np.nan)
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    ok = ~np.isnan(v).any(1)
    out[n - 1:][ok] = np.quantile(v[ok], q, axis=1)
    return out


def qqq_level():
    PL = w.long_panel()["QQQ"]
    real = w.kdata.series("QQQ", md.END)
    cut = min(real)
    k = real[cut] / PL[cut]
    return {**{d: v * k for d, v in PL.items() if d < cut}, **real}


def states():
    S0, _ = md.states()
    S = {k: S0[k] for k in ("V1", "V3", "R1", "R3", "R7", "O1")}
    M = md.monthly()
    cape = M["cape"]
    ms = sorted(cape)
    va, vb = {}, {}
    for i, m in enumerate(ms):
        if i >= 120:
            va[m] = float(cape[m] > float(np.median([cape[x] for x in ms[i - 119:i + 1]])))
        if i >= 240:
            win = sorted(cape[x] for x in ms[i - 239:i + 1])
            vb[m] = float(bisect.bisect_left(win, cape[m]) / len(win) >= 2 / 3)
    cape_av = lambda m: md.month_add(m, 2) + "-01"                              # noqa: E731
    S["VA"] = md.asof(md.from_monthly(va, cape_av), 0)
    S["VB"] = md.asof(md.from_monthly(vb, cape_av), 0)
    y10 = md.asof(md.fred("DGS10"), 2)
    S["RA"] = md.flag(y10 > md.sma(y10, 1260), ~np.isnan(md.sma(y10, 1260)))
    S["RB"] = md.flag(y10 > md.sma(y10, 252), ~np.isnan(md.sma(y10, 252)))
    oil = md.asof(md.fred("DCOILWTICO"), 4)
    oil = np.where(oil > 5, oil, np.nan)
    S["OA"] = md.flag(oil > md.sma(oil, 200), ~np.isnan(md.sma(oil, 200)))
    S["OB"] = md.flag(md.roc(oil, 63) > 0.25, ~np.isnan(md.roc(oil, 63)))
    PX = {"SPY": md.asof(md.yahoo("^GSPC"), 1), "QQQ": md.asof(qqq_level(), 1)}
    for x, px in PX.items():
        S[f"TA.{x}"] = md.flag(px > md.sma(px, 200), ~np.isnan(md.sma(px, 200)))
        for k, f in (("s", md.sma), ("e", ema)):
            for n in (20, 50):
                dist = px / f(px, n) - 1
                hi, lo = roll_q(dist, 1260, 0.90), roll_q(dist, 1260, 0.10)
                S[f"SU.{x}.{k}.{n}"] = md.flag(dist > hi, ~np.isnan(hi) & ~np.isnan(dist))
                S[f"SD.{x}.{k}.{n}"] = md.flag(dist < lo, ~np.isnan(lo) & ~np.isnan(dist))
    return S


def nw_p(d, lags=NWL):
    """two-sided p that the mean of d is zero, Newey-West"""
    x = d - d.mean()
    s0 = x @ x
    for k in range(1, lags + 1):
        s0 += 2 * (1 - k / (lags + 1)) * (x[k:] @ x[:-k])
    t = d.mean() / (math.sqrt(s0) / len(d))
    return float(math.erfc(abs(t) / math.sqrt(2)))


def maxdd(r):
    lvl = np.cumprod(1 + r)
    return float(np.max(1 - lvl / np.maximum.accumulate(lvl)))


def merged(s, gap=63):
    on = np.flatnonzero(s == 1)
    return 0 if len(on) == 0 else int(1 + (np.diff(on) > gap).sum())


def policy(s, H, K, Sl, flip=False):
    """book returns with the sleeve at HIGH while s is on (LOW while off); flip swaps them. Returns the
    policy, its equal-average-weight benchmark, and the weights."""
    wt = np.where(s == 1, LOW if flip else HIGH, HIGH if flip else LOW)
    turn = 2 * np.abs(np.diff(wt, prepend=wt[0]))
    oth = (H + K) / 2
    pol = (1 - wt) * oth + wt * Sl - COST * turn
    wb = wt.mean()
    return pol, (1 - wb) * oth + wb * Sl, wt


def score(s, H, K, Sl, ds, flip=False):
    pol, ben, wt = policy(s, H, K, Sl, flip)
    d = np.log1p(pol) - np.log1p(ben)
    g = lambda x: float(np.log1p(x).mean() * 252)                              # noqa: E731
    o = np.sort(d)[::-1]
    yrs = np.array([x[:4] for x in ds])
    keep = ~np.isin(yrs, ("2020", "2022"))
    return {"avg_weight": float(wt.mean()), "growth": g(pol), "growth_benchmark": g(ben), "d_growth": g(pol) - g(ben), "maxdd": maxdd(pol), "maxdd_benchmark": maxdd(ben),
            "d_maxdd": maxdd(pol) - maxdd(ben), "p_newey_west": nw_p(d), "sum_of_daily_edge": float(d.sum()), "best_20_sessions": float(o[:20].sum()), "worst_20_sessions": float(o[-20:].sum()),
            "d_growth_without_2020_2022": float(d[keep].mean() * 252) if keep.sum() > 250 else None,
            "sharpe": float(pol.mean() / pol.std(ddof=1) * math.sqrt(252)), "sharpe_benchmark": float(ben.mean() / ben.std(ddof=1) * math.sqrt(252))}


def shift_p(s, H, K, Sl):
    """every circular shift of the state: the arithmetic edge mean((w_t - wbar) x spread_t), two-sided"""
    wt = np.where(s == 1, HIGH, LOW)
    x = (Sl - (H + K) / 2)
    a = wt - wt.mean()
    allk = np.real(np.fft.ifft(np.fft.fft(x) * np.conj(np.fft.fft(a))))
    n = len(s)
    act, ref = allk[0], allk[63:n - 63]
    return float((1 + np.sum(np.abs(ref - ref.mean()) >= abs(act - ref.mean()))) / (1 + len(ref)))


def run_state(sv, sample, lag, late=False):
    """sv: state on the session calendar. Session j uses the state of index j - lag (lag 1 = read at one
    close, weights moved by the next)."""
    src = LATE if late else E
    lo, hi = SAMPLES[sample]
    ds = [d for d in sorted(E["BOOK"]) if lo <= d < hi and all(d in src[e] for e in ("HG", "KMLM", "SLEEVE"))]
    s = np.array([sv[pos[d] - lag] for d in ds])
    ok = ~np.isnan(s)
    ds = [d for d, k in zip(ds, ok) if k]
    s = s[ok]
    if len(s) < 500 or s.sum() < 40 or (1 - s).sum() < 40:
        return None
    H, K, Sl = (np.array([src[e][d] for d in ds]) for e in ("HG", "KMLM", "SLEEVE"))
    spread = Sl - (H + K) / 2
    out = {"n": len(ds), "span": [ds[0], ds[-1]], "on_share": float(s.mean()), "switches_per_yr": float(np.abs(np.diff(s)).sum() / len(s) * 252), "regimes": merged(s),
           "sleeve_minus_others_per_yr": {"on": float(spread[s == 1].mean() * 252), "off": float(spread[s == 0].mean() * 252)},
           "on_high": score(s, H, K, Sl, ds), "on_low": score(s, H, K, Sl, ds, flip=True), "p_shift": shift_p(s, H, K, Sl)}
    return out, ds, s, (H, K, Sl)


def holm(ps, m):
    order = sorted(ps, key=ps.get)
    out, run = {}, 0.0
    for k, name in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[name]))
        out[name] = run
    return out


def main():
    S = states()
    out = {"meta": {"high": HIGH, "low": LOW, "primary": PRIMARY, "states": list(S)}, "states": {}, "curves": {}, "fixed": {}}
    for sample, (lo, hi) in SAMPLES.items():
        ds = [d for d in sorted(E["BOOK"]) if lo <= d < hi]
        H, K, Sl = (np.array([E[e][d] for d in ds]) for e in ("HG", "KMLM", "SLEEVE"))
        out["fixed"][sample] = {f"{wt:.3f}": {"growth": float(np.log1p((1 - wt) / 2 * (H + K) + wt * Sl).mean() * 252), "maxdd": maxdd((1 - wt) / 2 * (H + K) + wt * Sl)} for wt in (LOW, 0.318, HIGH)}
    for sid, sv in S.items():
        row = {}
        for sample in SAMPLES:
            r = run_state(sv, sample, 1)
            if r is None:
                continue
            row[sample] = r[0]
            for tag, kw in (("one_close_late", {"late": True, "lag": 1}), ("lag2", {"lag": 2}), ("lag0", {"lag": 0})):
                x = run_state(sv, sample, kw["lag"], late=kw.get("late", False))
                if x:
                    row[sample][tag] = {k: {a: x[0][k][a] for a in ("d_growth", "d_maxdd", "p_newey_west")} for k in ("on_high", "on_low")}
        out["states"][sid] = row
        if sid in PRIMARY:
            # running sum of the policy's daily edge over the whole history (1994 on), for the chart
            lo = SAMPLES["shape"][0]
            dsa = [d for d in sorted(E["BOOK"]) if d >= lo]
            s = np.array([sv[pos[d] - 1] for d in dsa])
            ok = ~np.isnan(s)
            dsa, s = [d for d, k in zip(dsa, ok) if k], s[ok]
            H, K, Sl = (np.array([E[e][d] for d in dsa]) for e in ("HG", "KMLM", "SLEEVE"))
            pol, ben, _ = policy(s, H, K, Sl)
            c = np.cumsum(np.log1p(pol) - np.log1p(ben))
            out["curves"][sid] = [[d, round(float(v), 4)] for d, v in list(zip(dsa, c))[::5]]
    ps = {sid: out["states"][sid]["verdict"]["on_high"]["p_newey_west"] for sid in PRIMARY if "verdict" in out["states"][sid]}
    for sid, p in holm(ps, len(PRIMARY)).items():
        out["states"][sid]["verdict"]["p_holm"] = p
    json.dump(out, open(os.path.join(HERE, "out", "dynsleeve.json"), "w"), indent=1)
    print("fixed", {k: {a: (round(b["growth"], 3), round(b["maxdd"], 3)) for a, b in v.items()} for k, v in out["fixed"].items()})
    for sid, row in out["states"].items():
        for sample in ("verdict", "shape"):
            if sample not in row:
                continue
            v = row[sample]
            a, b = v["on_high"], v["on_low"]
            print(f"{'*' if sid in PRIMARY else ' '}{sid:13s} {sample:7s} on {v['on_share']:.2f} reg {v['regimes']:3d} sw/yr {v['switches_per_yr']:5.1f} spread on/off {v['sleeve_minus_others_per_yr']['on']:+.2f}/{v['sleeve_minus_others_per_yr']['off']:+.2f} | "
                  f"on->HIGH dG {a['d_growth']:+.3f} dDD {a['d_maxdd'] * 100:+.1f} nw {a['p_newey_west']:.3f} shift {v['p_shift']:.3f} holm {v.get('p_holm', float('nan')):.2f} | late {v['one_close_late']['on_high']['d_growth']:+.3f} lag2 {v['lag2']['on_high']['d_growth']:+.3f} "
                  f"wo2020/22 {a['d_growth_without_2020_2022'] if a['d_growth_without_2020_2022'] is None else round(a['d_growth_without_2020_2022'], 3)} | on->LOW dG {b['d_growth']:+.3f} dDD {b['d_maxdd'] * 100:+.1f}")


if __name__ == "__main__":
    main()
