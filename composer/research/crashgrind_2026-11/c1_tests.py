"""Stage C (PREREG.md): can a crash be told from a grind? Episode table, day-level test and the three-level
policy, on the engine paths with volatility funds rebuilt from futures (2006-01 on). Writes out/crashgrind.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "dynsleeve_2026-11"))
import ds1_run as ds1  # noqa: E402
import v2_engines as v2  # noqa: E402

md, fd, vd = ds1.md, ds1.fd, v2.vd
days, pos = ds1.days, ds1.pos
START, COST = "2006-01-03", ds1.COST
BASE, GRIND, CRASH = 0.318, 0.15, 0.50
STRETCH = {"all": ("2006-01-03", "9999"), "2006-01..2011-10 (funds rebuilt from futures)": ("2006-01-03", "2011-11-01"), "2011-11..2020-11": ("2011-11-01", "2020-12-02"),
           "2021-06 on (all real)": ("2021-06-02", "9999")}


def paths():
    E = md.engines()
    new = json.load(open(v2.CACHE + "/engines_new.json"))
    late0 = fd.late_engines()
    same = {"HG": {**E["HG"], **{d: v for d, v in new["HG"].items() if d in E["HG"]}}, "SLEEVE": {**E["SLEEVE"], **{d: v for d, v in new["SLEEVE"].items() if d in E["SLEEVE"]}}, "KMLM": E["KMLM"]}
    late = {"HG": {**late0["HG"], **{d: v for d, v in new["HG.late"].items() if d in late0["HG"]}}, "SLEEVE": {**late0["SLEEVE"], **{d: v for d, v in new["SLEEVE.late"].items() if d in late0["SLEEVE"]}},
            "KMLM": late0["KMLM"]}
    today = json.load(open(v2.CACHE + "/sleeve_today.json")) if os.path.exists(v2.CACHE + "/sleeve_today.json") else {}
    return E, same, late, {**E["SLEEVE"], **{d: v for d, v in today.items() if d in E["SLEEVE"]}}


def crash_states():
    px = md.asof(md.yahoo("^GSPC"), 1)
    vix, v3 = md.asof(md.yahoo("^VIX"), 1), md.asof(md.yahoo("^VIX3M"), 1)
    n = len(days)
    r10 = np.full(n, np.nan)
    r10[10:] = px[10:] / px[:-10] - 1
    roll = lambda x, k, f: np.array([np.nan if i < k - 1 or np.isnan(x[i - k + 1:i + 1]).all() else f(x[i - k + 1:i + 1]) for i in range(n)])   # noqa: E731
    D = {"D1": (roll(r10, 21, np.nanmin) < -0.10).astype(float), "D3": (roll(vix, 21, np.nanmax) > 40).astype(float)}
    inv = np.where(np.isnan(vix) | np.isnan(v3), np.nan, (vix > v3).astype(float))
    D["D2"] = np.where(np.isnan(roll(inv, 10, np.nansum)), np.nan, (roll(inv, 10, np.nansum) >= 5).astype(float))
    D["D2"][np.isnan(inv)] = np.nan
    C = vd.contracts()
    _, det = vd.index("2004-06-01")
    back = {d: float(C[m1][d] > C[m2][d]) for d, (m1, m2) in det["legs"].items() if d in C[m1] and d in C[m2]}
    b = md.asof(back, 1)
    s = roll(b, 10, np.nansum)
    D["D4"] = np.where(np.isnan(b), np.nan, (s >= 5).astype(float))
    for k in ("D1", "D3"):
        D[k][np.isnan(px)] = np.nan
    return D, px, r10


def nw_diff(x, g, lags=63):
    """mean of x where g == 1 less where g == 0, Newey-West p (regression of x on g)"""
    gm = g - g.mean()
    if (gm @ gm) == 0:
        return None, None
    b = (gm @ x) / (gm @ gm)
    z = gm * (x - x.mean() - b * gm)
    s0 = z @ z
    for k in range(1, lags + 1):
        s0 += 2 * (1 - k / (lags + 1)) * (z[k:] @ z[:-k])
    return float(b), float(math.erfc(abs(b / (math.sqrt(s0) / (gm @ gm))) / math.sqrt(2)))


def episodes(s, gap=21):
    on = np.flatnonzero(s == 1)
    if len(on) == 0:
        return []
    return [g for g in np.split(on, np.flatnonzero(np.diff(on) > gap) + 1)]


def main():
    E, same, late, sleeve_today = paths()
    S = ds1.states()
    Bs = {"B1": S["SD.SPY.s.50"], "B2": S["SD.SPY.s.20"], "B3": 1 - S["TA.SPY"]}
    D, px, r10 = crash_states()
    ds = [d for d in sorted(E["BOOK"]) if d >= START and all(d in late[e] for e in ("HG", "KMLM", "SLEEVE"))]
    ii = np.array([pos[d] for d in ds])
    R = {k: np.array([[src[e][d] for e in ("HG", "KMLM", "SLEEVE")] for d in ds]) for k, src in (("same", same), ("late", late))}
    St = np.array([sleeve_today.get(d, same["SLEEVE"][d]) for d in ds])
    spread = {k: v[:, 2] - (v[:, 0] + v[:, 1]) / 2 for k, v in R.items()}
    yr = np.array([d[:4] for d in ds])
    out = {"meta": {"from": ds[0], "to": ds[-1], "n": len(ds), "weights": [BASE, GRIND, CRASH]}, "day": {}, "policy": {}, "episodes": {}, "flags": {}}
    lg = lambda x: float(np.log1p(x).sum())                                    # noqa: E731
    for bk, bv in Bs.items():
        b = np.nan_to_num(bv[ii - 1])                                          # read at one close, acted on by the next
        for dk, dv in D.items():
            c = dv[ii - 1]
            ok = ~np.isnan(c)
            key = f"{bk}.{dk}"
            out["day"][key], out["policy"][key] = {}, {}
            for sk, (lo, hi) in list(STRETCH.items()) + [("all, without 2020", ("2006-01-03", "9999"))]:
                m = ok & np.array([lo <= d < hi for d in ds]) & ((yr != "2020") if "without" in sk else True)
                w_ = m & (b == 1)
                row = {"washed_out_days": int(w_.sum()), "crash_flagged": int((w_ & (c == 1)).sum())}
                for pk in ("same", "late"):
                    x, g = spread[pk][w_], np.nan_to_num(c[w_])
                    if g.sum() >= 10 and (1 - g).sum() >= 10:
                        diff, p = nw_diff(x, g, lags=min(63, max(5, len(x) // 10)))
                        row[pk] = {"spread_crash_per_day": float(x[g == 1].mean()), "spread_grind_per_day": float(x[g == 0].mean()), "diff_per_day": diff, "p": p}
                out["day"][key][sk] = row
                # the three-level policy on this stretch
                wt = np.where(b == 1, np.where(np.nan_to_num(c) == 1, CRASH, GRIND), BASE)[m]
                pol = {}
                for pk in ("same", "late"):
                    H, K, Sl = R[pk][m, 0], R[pk][m, 1], R[pk][m, 2]
                    oth = (H + K) / 2
                    turn = 2 * np.abs(np.diff(wt, prepend=wt[0]))
                    p_ = (1 - wt) * oth + wt * Sl - COST * turn
                    wb = wt.mean()
                    b_ = (1 - wb) * oth + wb * Sl
                    d_ = np.log1p(p_) - np.log1p(b_)
                    lv_p, lv_b = np.cumprod(1 + p_), np.cumprod(1 + b_)
                    dd = lambda lv: float(np.max(1 - lv / np.maximum.accumulate(lv)))   # noqa: E731
                    # the pieces: grind-only (15% on grind days, else base) and crash-only (50% on crash days, else base)
                    pieces = {}
                    for nm, w2 in (("grind_only", np.where((b[m] == 1) & (np.nan_to_num(c[m]) == 0), GRIND, BASE)), ("crash_only", np.where((b[m] == 1) & (np.nan_to_num(c[m]) == 1), CRASH, BASE)),
                                   ("all_washed_out_low", np.where(b[m] == 1, GRIND, BASE))):   # no reading at all: addendum 63's lead on these paths
                        q = (1 - w2) * oth + w2 * Sl - COST * 2 * np.abs(np.diff(w2, prepend=w2[0]))
                        qb = (1 - w2.mean()) * oth + w2.mean() * Sl
                        pieces[nm] = float((np.log1p(q) - np.log1p(qb)).mean() * 252)
                    pol[pk] = {"avg_weight": float(wb), "d_growth": float(d_.mean() * 252), "d_maxdd": dd(lv_p) - dd(lv_b), "p": ds1.nw_p(d_, lags=63), "growth": float(np.log1p(p_).mean() * 252),
                               "growth_benchmark": float(np.log1p(b_).mean() * 252), "maxdd": dd(lv_p), **pieces}
                out["policy"][key][sk] = pol
        # episodes of the base state since 2006
        if bk == "B1":
            for g in episodes(b):
                a, z = g[0], g[-1]
                on = np.zeros(len(ds), bool)
                on[g] = True
                on &= b == 1
                hi = np.nanmax(px[ii[a] - 252:ii[a] + 1])
                trough = np.nanmin(px[ii[a]:ii[z] + 1])
                ep = {"from": ds[a], "to": ds[z], "washed_out_days": int(on.sum()), "depth_from_252d_high": float(trough / hi - 1), "fastest_10_session_fall": float(np.nanmin(r10[ii[a]:ii[z] + 1])),
                      "flags": {dk: (None if np.isnan(dv[ii[g] - 1]).all() else float(np.nanmean(dv[ii[on] - 1]))) for dk, dv in D.items()},
                      "sleeve": lg(R["same"][on, 2]), "others": lg((R["same"][on, 0] + R["same"][on, 1]) / 2), "hg": lg(R["same"][on, 0]), "kmlm": lg(R["same"][on, 1]),
                      "sleeve_late": lg(R["late"][on, 2]), "others_late": lg((R["late"][on, 0] + R["late"][on, 1]) / 2), "sleeve_today_leverage": lg(St[on])}
                out["episodes"].setdefault("B1", []).append(ep)
    for dk, dv in D.items():
        c = dv[ii - 1]
        out["flags"][dk] = {"share_of_days": float(np.nanmean(c)), "first": ds[int(np.argmax(~np.isnan(c)))], "episodes": len(episodes(np.nan_to_num(c)))}
    # Holm over the two primaries: the day-level p without 2020
    ps = {k: out["day"][k]["all, without 2020"].get("same", {}).get("p") for k in ("B1.D1", "B1.D2")}
    order = sorted((k for k in ps if ps[k] is not None), key=lambda k: ps[k])
    run = 0.0
    for j, k in enumerate(order):
        run = max(run, min(1.0, (2 - j) * ps[k]))
        out["day"][k]["all, without 2020"]["same"]["p_holm"] = run
    json.dump(out, open(os.path.join(HERE, "out", "crashgrind.json"), "w"), indent=1)
    print("sample", out["meta"], "| flags", out["flags"])
    print("EPISODES (B1): from..to days depth fastest10 | D1 D2 D3 D4 | sleeve others (late) | today-lev")
    for e in out["episodes"]["B1"]:
        f = e["flags"]
        print(f"  {e['from']}..{e['to']} {e['washed_out_days']:3d} {e['depth_from_252d_high']:+.2f} {e['fastest_10_session_fall']:+.2f} | " + " ".join("  - " if f[k] is None else f"{f[k]:.2f}" for k in ("D1", "D2", "D3", "D4"))
              + f" | {e['sleeve']:+.3f} {e['others']:+.3f} ({e['sleeve_late']:+.3f} {e['others_late']:+.3f}) | {e['sleeve_today_leverage']:+.3f}")
    for key in ("B1.D1", "B1.D2", "B1.D3", "B1.D4", "B2.D1", "B2.D2", "B3.D1", "B3.D2", "B3.D4"):
        for sk, row in out["day"][key].items():
            s_ = row.get("same")
            pl = out["policy"][key][sk]
            print(f"{key} {sk[:22]:22s} washed {row['washed_out_days']:4d} crash {row['crash_flagged']:4d} | "
                  + ("spread c/g %+.4f/%+.4f diff %+.4f p %.3f" % (s_["spread_crash_per_day"], s_["spread_grind_per_day"], s_["diff_per_day"], s_["p"]) if s_ else "too few")
                  + (" late diff %+.4f p %.3f" % (row["late"]["diff_per_day"], row["late"]["p"]) if row.get("late") else "")
                  + f" | unconditional {pl['same']['all_washed_out_low']:+.3f} (late {pl['late']['all_washed_out_low']:+.3f})" + f" | policy dG {pl['same']['d_growth']:+.3f} (p {pl['same']['p']:.2f}) dDD {pl['same']['d_maxdd'] * 100:+.1f} late {pl['late']['d_growth']:+.3f} grind-only {pl['same']['grind_only']:+.3f} crash-only {pl['same']['crash_only']:+.3f}")


if __name__ == "__main__":
    main()
