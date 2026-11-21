"""The macro study's tests (PREREG.md "Tests" 1-5). Writes out/macro.json.
All placebo p-values come from circular shifts of the state over the sample's own sessions (the state keeps
its persistence and its share of days); the map and P1 growth use the exact shift distribution by FFT."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdata as md  # noqa: E402

w = md.w
ks = w.ks
SHIFTS, SEED, COST = 1000, 20261127, 5.856e-4
rng = np.random.default_rng(SEED)
days = md.sessions()
pos = {d: i for i, d in enumerate(days)}
S, FAM = md.states()
E = md.engines()
TB = E["TBILL"]


def sample(target, which):
    a, b, c = md.STRETCH[target]
    lo, hi = {"shape": (a, b), "verdict": (b, "9999"), "real": (c, "9999")}[which]
    ds = [d for d in sorted(E[target]) if lo <= d < hi and d in TB]
    return ds, np.array([E[target][d] for d in ds]), np.array([TB[d] for d in ds])


def circ_all(s, x):
    """sum_t s[(t - k) mod n] * x[t] for every shift k"""
    return np.real(np.fft.ifft(np.fft.fft(x) * np.conj(np.fft.fft(s))))


def episodes(s):
    return int(((s[1:] == 1) & (s[:-1] == 0)).sum())


def falls(r, k=3):
    lvl = np.cumprod(1 + r)
    pk = np.maximum.accumulate(lvl)
    dd = 1 - lvl / pk
    out, i = [], 0
    while i < len(dd):
        if dd[i] > 0:
            j = i
            while j < len(dd) and dd[j] > 0:
                j += 1
            c = i + int(np.argmax(dd[i:j]))
            out.append((float(dd[c]), i, c))
            i = j
        else:
            i += 1
    return sorted(out, reverse=True)[:k]


def maxdd(r):
    lvl = np.cumprod(1 + r, axis=-1)
    return np.max(1 - lvl / np.maximum.accumulate(lvl, axis=-1), axis=-1)


def holm(ps, m=None):
    """Holm over m registered tests (states that could not be scored still count)"""
    order = sorted(ps, key=ps.get)
    out, run, m = {}, 0.0, max(m or 0, len(order))
    for k, name in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[name]))
        out[name] = run
    return out


def map_row(s, r):
    """state-conditional mean daily log return, on minus off, with the exact shift distribution"""
    ok = ~np.isnan(s)
    s, lr = s[ok], np.log1p(r[ok])
    n, n1 = len(s), s.sum()
    if n1 < 40 or n - n1 < 40:
        return None
    stat = lambda dot: (dot / n1 - (lr.sum() - dot) / (n - n1)) * 252          # noqa: E731
    act = stat(float(s @ lr))
    allk = stat(circ_all(s, lr)[63:n - 63])
    return {"n": int(n), "on_share": float(n1 / n), "episodes": episodes(s), "on_per_yr": float(s @ lr / n1 * 252), "off_per_yr": float((lr.sum() - s @ lr) / (n - n1) * 252),
            "diff_per_yr": float(act), "p_two_sided": float((1 + np.sum(np.abs(allk - allk.mean()) >= abs(act - allk.mean()))) / (1 + len(allk)))}, ok


def p1(s, r, tb, ks_shift=None):
    """half exposure while the state is on, against a constant mix with the same average exposure.
    The placebo uses EVERY circular shift from 63 to n-63 (ks_shift is ignored; kept for old callers)."""
    n = len(s)
    e = 1 - 0.5 * s
    turn = np.abs(np.diff(np.concatenate([[1.0], e])))
    pol = e * r + (1 - e) * tb - COST * turn
    ebar = e.mean()
    mix = ebar * r + (1 - ebar) * tb
    g = lambda x: float(np.log1p(x).mean() * 252)                              # noqa: E731
    act = {"avg_exposure": float(ebar), "growth": g(pol), "growth_mix": g(mix), "d_growth": g(pol) - g(mix), "maxdd": float(maxdd(pol)), "maxdd_mix": float(maxdd(mix)), "maxdd_full": float(maxdd(r)),
           "d_maxdd": float(maxdd(pol) - maxdd(mix))}
    mir = (1 - 0.5 * (1 - s))
    mp = mir * r + (1 - mir) * tb
    mm = mir.mean() * r + (1 - mir.mean()) * tb
    act["mirror_d_growth"] = g(mp) - g(mm)
    allk = np.arange(63, n - 63)
    cg = cd = 0
    for a in range(0, len(allk), 400):
        idx = (np.arange(n)[None, :] - allk[a:a + 400, None]) % n
        Eh = 1 - 0.5 * s[idx]
        Pm = Eh * r[None, :] + (1 - Eh) * tb[None, :]
        cg += int(np.sum(np.log1p(Pm).mean(1) * 252 - g(mix) >= act["d_growth"]))
        cd += int(np.sum(maxdd(Pm) - maxdd(mix) <= act["d_maxdd"]))
    act["p_growth"] = (1 + cg) / (1 + len(allk))
    act["p_maxdd"] = (1 + cd) / (1 + len(allk))
    act["shifts"] = len(allk)
    return act


def tilt_path(s, LR, R, month_start, base=(0.341, 0.341, 0.318), step=0.15, min_on=60, burn=60):
    """book returns with 15 points moved, on state-on days, from the engine with the worst to the one with
    the best mean log return on EARLIER on-days (estimated at each month start; after `burn` months)"""
    cs = np.cumsum(s[:, None] * LR, 0)
    cnt = np.cumsum(s)
    W = np.tile(np.array(base), (len(s), 1))
    for j in range(burn, len(month_start)):
        a = month_start[j]
        b = month_start[j + 1] if j + 1 < len(month_start) else len(s)
        if cnt[a - 1] >= min_on:
            m = cs[a - 1] / cnt[a - 1]
            hi_, lo_ = int(np.argmax(m)), int(np.argmin(m))
            if hi_ != lo_:
                on = s[a:b] == 1
                W[a:b][on, hi_] += step
                W[a:b][on, lo_] -= step
    turn = np.abs(np.diff(W, axis=0, prepend=W[:1])).sum(1)
    return (W * R).sum(1) - COST * turn, W


def main():
    out = {"map": {}, "p1": {}, "p2": {}, "cross": {}, "reentry": {}, "meta": {"shifts": SHIFTS, "primary": md.PRIMARY, "families": FAM}}
    # ---------- 1. the map, and 2. P1
    for target in ("BOOK", "HG", "KMLM", "SLEEVE"):
        for which in ("verdict", "shape", "real"):
            ds, r, tb = sample(target, which)
            if len(ds) < 500:
                continue
            ii = np.array([pos[d] for d in ds])
            fl = falls(r)
            fall_days = np.zeros(len(ds), bool)
            for _, a, c in fl:
                fall_days[a:c + 1] = True
            key = f"{target}.{which}"
            out["map"][key] = {"span": [ds[0], ds[-1], len(ds)], "growth_per_yr": float(np.log1p(r).mean() * 252), "maxdd": float(maxdd(r)), "states": {}}
            ps = {}
            for sid, x in S.items():
                res = map_row(x[ii], r)
                if res is None:
                    continue
                row, ok = res
                sx = x[ii][ok]
                row["share_of_deepest_fall_days_on"] = float(sx[fall_days[ok]].mean()) if fall_days[ok].any() else None
                out["map"][key]["states"][sid] = row
                if sid in md.PRIMARY:
                    ps[sid] = row["p_two_sided"]
            for sid, p in holm(ps, len(md.PRIMARY)).items():
                out["map"][key]["states"][sid]["p_holm"] = p
            if which == "real":
                continue
            out["p1"][key] = {}
            n = len(ds)
            ksh = rng.integers(63, n - 63, SHIFTS)
            pg = {}
            for sid in md.PRIMARY + ["T1"]:
                s = x_ = S[sid][ii]
                if np.isnan(s).any():
                    s = np.where(np.isnan(x_), 0.0, x_)
                if s.sum() < 40 or (1 - s).sum() < 40:
                    continue
                out["p1"][key][sid] = p1(s, r, tb, ksh)
                out["p1"][key][sid]["episodes"] = episodes(s)
                if sid in md.PRIMARY:
                    pg[sid] = min(out["p1"][key][sid]["p_growth"], out["p1"][key][sid]["p_maxdd"])
            for sid, p in holm(pg, len(md.PRIMARY)).items():
                out["p1"][key][sid]["p_holm_best_of_growth_or_fall"] = p
    # ---------- 3. P2 tilt between engines (book)
    for which in ("verdict", "shape", "all"):
        if which == "all":
            ds = [d for d in sorted(E["BOOK"])]
        else:
            ds, _, _ = sample("BOOK", which)
        ii = np.array([pos[d] for d in ds])
        R = np.array([[E[e][d] for e in ("HG", "KMLM", "SLEEVE")] for d in ds])
        LR = np.log1p(R)
        ms = [i for i, d in enumerate(ds) if i == 0 or d[:7] != ds[i - 1][:7]]
        fixed = (np.array([0.341, 0.341, 0.318]) * R).sum(1)
        g = lambda x: float(np.log1p(x).mean() * 252)                          # noqa: E731
        out["p2"][which] = {"span": [ds[0], ds[-1], len(ds)], "fixed_growth": g(fixed), "fixed_maxdd": float(maxdd(fixed)), "states": {}}
        n = len(ds)
        ksh = rng.integers(63, n - 63, SHIFTS)
        pg = {}
        for sid in md.PRIMARY:
            s = np.where(np.isnan(S[sid][ii]), 0.0, S[sid][ii])
            if s.sum() < 120:
                continue
            pol, W = tilt_path(s, LR, R, ms)
            mir, _ = tilt_path(1 - s, LR, R, ms)
            dg = np.array([g(tilt_path(np.roll(s, int(k)), LR, R, ms)[0]) for k in ksh[:400]]) - g(fixed)
            dev = np.abs(W - np.array([0.341, 0.341, 0.318])).sum(1) > 1e-9
            row = {"d_growth": g(pol) - g(fixed), "d_maxdd": float(maxdd(pol) - maxdd(fixed)), "mirror_d_growth": g(mir) - g(fixed), "p_growth": float((1 + np.sum(dg >= g(pol) - g(fixed))) / (1 + len(dg))),
                   "share_of_days_tilted": float(dev.mean()), "avg_weights_when_tilted": [float(v) for v in W[dev].mean(0)] if dev.any() else None, "episodes": episodes(s)}
            out["p2"][which]["states"][sid] = row
            pg[sid] = row["p_growth"]
        for sid, p in holm(pg, len(md.PRIMARY)).items():
            out["p2"][which]["states"][sid]["p_holm"] = p
    # ---------- 4. cross-engine signals (each known at the prior close)
    import s1_sleeve as s1
    PL = w.long_panel()
    PRH, PRS = w.real_panel("HG"), w.real_panel("SLEEVE")
    X = {}
    spy = {**{d: v for d, v in PL["SPY"].items() if d <= "2015-08-31"}, **{d: v for d, v in PRH["SPY"].items() if d > "2015-08-31"}}
    sm = ks.sma_series(spy, 200)
    gate_off = {d: (None if sm[d] is None else spy[d] < sm[d]) for d in spy}
    X["X1"] = gate_off
    import q1_cells as q1
    Pab = dict(w.kdata.panel_ab(md.END), KMLM=md.w.sdata.fund_tr(md.END))
    fa, fb = q1.flag_rsi(PL, 10), q1.flag_rsi(Pab, 10)
    X["X2"] = {**{d: (None if v is None else not v) for d, v in fa.items() if d <= "2020-12-01"}, **{d: (None if v is None else not v) for d, v in fb.items() if d > "2020-12-01"}}
    tree = w.approved("SLEEVE")
    _, fheld = s1.path(s1.half(tree, "FrontrunBonds"), PL, PRS)
    X["X3"] = {d: any(t not in ("BOXX", "BIL") and v > 1e-9 for t, v in h.items()) for d, h in fheld.items()}
    ih = {}
    for P, lo, hi in ((PL, "0", "2023-01-31"), (PRS, "2023-02-01", "9")):
        a, b = ks.rsi_series(P["IEF"], 8), ks.rsi_series(P["PSQ"], 45)
        ih.update({d: (None if a[d] is None or b.get(d) is None else a[d] < b[d]) for d in a if lo <= d <= hi})
    X["X4"] = ih
    X["X5"] = {d: (None if any(X[k].get(d) is None for k in ("X1", "X2", "X4")) else sum(X[k][d] for k in ("X1", "X2", "X4")) >= 2) for d in X["X1"]}
    own = {"X1": "HG", "X2": "KMLM", "X3": "SLEEVE", "X4": "SLEEVE", "X5": None}
    for xid, st in X.items():
        out["cross"][xid] = {}
        for target in ("HG", "KMLM", "SLEEVE", "BOOK"):
            if target == own[xid]:
                continue
            for which in ("verdict", "shape"):
                ds, r, tb = sample(target, which)
                prev = {b: a for a, b in zip(days, days[1:])}
                sv = np.array([np.nan if st.get(prev.get(d)) is None else float(st[prev[d]]) for d in ds])
                res = map_row(sv, r)
                if res is None:
                    continue
                row, ok = res
                lr = np.log1p(r)
                f5 = np.array([lr[i:i + 5].sum() for i in range(len(lr))])
                r5 = map_row(sv[:-4], np.expm1(f5[:-4]))
                row["next5_diff_per_yr"] = r5[0]["diff_per_yr"] / 5 if r5 else None
                row["next5_p"] = r5[0]["p_two_sided"] if r5 else None
                s0 = np.where(np.isnan(sv), 0.0, sv)
                row["p1"] = p1(s0, r, tb, rng.integers(63, len(ds) - 63, SHIFTS))
                out["cross"][xid][f"{target}.{which}"] = row
    # ---------- 5. re-entry (Holy Grail's ungated tree on gate-off days)
    ung = ks.sr.load_tree(ks.sr.load_manifest()["HG"]["eras"][1])
    a = w.simulate(ung, PL, w.SPAN["HG"]["M"][0], w.SPAN["HG"]["R"][1])
    b = w.simulate(ung, PRH, *w.SPAN["HG"]["A"])
    U = {**dict(zip(a["days"], a["ret"])), **dict(zip(b["days"], b["ret"]))}
    baa, nf, px = md.asof(md.fred("BAA10Y"), 2), md.asof(md.fred("NFCI"), 4), md.asof(md.yahoo("^GSPC"), 1)
    RE = {"RE1": md.flag(md.chg(baa, 63) < -0.20, ~np.isnan(md.chg(baa, 63))), "RE2": md.flag(md.chg(nf, 65) < 0, ~np.isnan(md.chg(nf, 65))), "RE3": md.flag(px > md.sma(px, 50), ~np.isnan(md.sma(px, 50)))}
    prev = {b_: a_ for a_, b_ in zip(days, days[1:])}
    for which, lo, hi in (("verdict", "2006-07-18", "9999"), ("shape", "1991-04-01", "2006-07-18")):
        ds = [d for d in sorted(U) if lo <= d < hi and d in TB and gate_off.get(prev.get(d)) is True]
        ex = np.array([U[d] - TB[d] for d in ds])
        ii = np.array([pos[d] for d in ds])
        out["reentry"][which] = {"gate_off_days": len(ds), "ungated_minus_tbills_per_yr": float(np.log1p(ex).mean() * 252), "states": {}}
        ps = {}
        for rid, x in RE.items():
            res = map_row(x[ii], ex)
            if res:
                out["reentry"][which]["states"][rid] = res[0]
                ps[rid] = res[0]["p_two_sided"]
        for rid, p in holm(ps, 3).items():
            out["reentry"][which]["states"][rid]["p_holm"] = p
    json.dump(out, open(os.path.join(HERE, "out", "macro.json"), "w"), indent=1)
    # ---------- print
    for key in ("BOOK.verdict", "BOOK.shape", "HG.verdict", "HG.shape", "SLEEVE.verdict", "KMLM.verdict", "KMLM.shape"):
        m = out["map"][key]
        print(f"\nMAP {key} {m['span']} growth {m['growth_per_yr']:+.2f} maxdd {m['maxdd']:.2f}")
        for sid in md.PRIMARY + ["T1"]:
            v = m["states"].get(sid)
            if v:
                q = out["p1"].get(key, {}).get(sid)
                print(f"  {sid:12s} on {v['on_share']:.2f} ep {v['episodes']:3d} on {v['on_per_yr']:+.2f} off {v['off_per_yr']:+.2f} diff {v['diff_per_yr']:+.2f} p {v['p_two_sided']:.3f} holm {v.get('p_holm', float('nan')):.2f} falls-on {v['share_of_deepest_fall_days_on']:.2f}"
                      + (f" | P1 dG {q['d_growth']:+.3f} (p {q['p_growth']:.3f}) dDD {q['d_maxdd'] * 100:+.1f}pts (p {q['p_maxdd']:.3f}) mirror dG {q['mirror_d_growth']:+.3f}" if q else ""))
    for which, v in out["p2"].items():
        print(f"\nP2 tilt {which} {v['span']} fixed growth {v['fixed_growth']:+.2f} maxdd {v['fixed_maxdd']:.2f}")
        for sid, x in v["states"].items():
            print(f"  {sid:12s} dG {x['d_growth']:+.3f} p {x['p_growth']:.3f} holm {x['p_holm']:.2f} dDD {x['d_maxdd'] * 100:+.1f}pts mirror {x['mirror_d_growth']:+.3f} tilted {x['share_of_days_tilted']:.2f} w {[round(z, 2) for z in x['avg_weights_when_tilted']] if x['avg_weights_when_tilted'] else None}")
    print()
    for xid, v in out["cross"].items():
        for key, x in v.items():
            print(f"CROSS {xid} -> {key:15s} on {x['on_share']:.2f} ep {x['episodes']:3d} next-day diff {x['diff_per_yr']:+.2f}/yr p {x['p_two_sided']:.3f} | next-5 {x['next5_diff_per_yr'] if x['next5_diff_per_yr'] is None else round(x['next5_diff_per_yr'], 2)} p {x['next5_p']} | P1 dG {x['p1']['d_growth']:+.3f} (p {x['p1']['p_growth']:.3f}) dDD {x['p1']['d_maxdd'] * 100:+.1f}")
    for which, v in out["reentry"].items():
        print("REENTRY", which, v["gate_off_days"], round(v["ungated_minus_tbills_per_yr"], 3), {k: (round(x["on_share"], 2), round(x["on_per_yr"], 2), round(x["off_per_yr"], 2), round(x["p_two_sided"], 3), round(x.get("p_holm", 9), 2)) for k, x in v["states"].items()})


if __name__ == "__main__":
    main()
