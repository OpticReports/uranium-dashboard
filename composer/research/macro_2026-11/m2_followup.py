"""Follow-ups on the leads of m1_run.py. EVERYTHING HERE IS POST HOC (defined after the first results were
seen) and is labelled so in the report. Writes out/followup.json.
 regimes     how many separate regimes each primary state really has (spells closer than 63 sessions merged)
 liquidity   the one composite that cleared the pre-registered P1 rule: by calendar year, without its
             strongest years, per engine, and against the FULL book, not only the equal-exposure mix
 gold        the opposite sign to the one registered: de-risk when the gold family is OFF
 others      cross-engine signals re-scored on the OTHER engines only (the book target contained the
             signalling engine's own return)
 redeploy    when Holy Grail's SPY gate is off, move weight from Holy Grail to the other two"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m1_run as m1  # noqa: E402

md, S, E, TB, pos, days = m1.md, m1.S, m1.E, m1.TB, m1.pos, m1.days
rng = np.random.default_rng(20261128)
g = lambda x: float(np.log1p(x).mean() * 252)                                # noqa: E731
out = {}


def merged(s, gap=63):
    on = np.flatnonzero(s == 1)
    if len(on) == 0:
        return 0
    return int(1 + (np.diff(on) > gap).sum())


def by_year(ds, s, r):
    o = {}
    for y in sorted({d[:4] for d in ds}):
        m = np.array([d[:4] == y for d in ds])
        lr = np.log1p(r[m])
        o[y] = {"on_share": float(s[m].mean()), "on_log": float(lr[s[m] == 1].sum()), "off_log": float(lr[s[m] == 0].sum())}
    return o


def p1_full(s, r, tb):
    e = 1 - 0.5 * s
    pol = e * r + (1 - e) * tb - m1.COST * np.abs(np.diff(np.concatenate([[1.0], e])))
    mix = e.mean() * r + (1 - e.mean()) * tb
    return {"avg_exposure": float(e.mean()), "policy": [g(pol), float(m1.maxdd(pol))], "mix": [g(mix), float(m1.maxdd(mix))], "full": [g(r), float(m1.maxdd(r))]}


# ---- regimes
out["regimes"] = {}
for target in ("BOOK", "HG"):
    ds, r, tb = m1.sample(target, "verdict")
    ii = np.array([pos[d] for d in ds])
    out["regimes"][target] = {sid: {"switches_on": m1.episodes(np.nan_to_num(S[sid][ii])), "merged_regimes": merged(np.nan_to_num(S[sid][ii]))} for sid in md.PRIMARY + ["T1"]}
# ---- liquidity and gold on the book
for name, sid, flip in (("liquidity", "F_LIQUIDITY", False), ("gold_off", "F_GOLD", True)):
    out[name] = {}
    for which in ("verdict", "shape"):
        ds, r, tb = m1.sample("BOOK", which)
        ii = np.array([pos[d] for d in ds])
        s = np.nan_to_num(S[sid][ii])
        s = 1 - s if flip else s
        n = len(ds)
        res = {"p1": p1_full(s, r, tb), "by_year": by_year(ds, s, r), "merged_regimes": merged(s)}
        ksh = rng.integers(63, n - 63, 1000)
        res["p1_test"] = {k: v for k, v in m1.p1(s, r, tb, ksh).items()}
        for label, drop in (("without_2020_2021", ("2020", "2021")), ("without_2022", ("2022",)), ("without_2020_2022", ("2020", "2021", "2022"))):
            keep = np.array([d[:4] not in drop for d in ds])
            if which == "verdict" and keep.sum() > 500:
                rr = m1.map_row(s[keep], r[keep])
                res[label] = {"diff_per_yr": rr[0]["diff_per_yr"], "p": rr[0]["p_two_sided"], "p1_d_growth": m1.p1(s[keep], r[keep], tb[keep], rng.integers(63, keep.sum() - 63, 500))["d_growth"]} if rr else None
        res["per_engine_diff"] = {}
        for e in ("HG", "KMLM", "SLEEVE"):
            x = np.array([E[e][d] for d in ds])
            rr = m1.map_row(s, x)
            res["per_engine_diff"][e] = {"diff_per_yr": rr[0]["diff_per_yr"], "p": rr[0]["p_two_sided"]} if rr else None
        out[name][which] = res
# ---- cross-engine, other engines only; and the redeploy policy
prev = {b: a for a, b in zip(days, days[1:])}
X = m1_X = None
import s1_sleeve as s1  # noqa: E402
w, ks = md.w, md.w.ks
PL = w.long_panel()
PRH, PRS = w.real_panel("HG"), w.real_panel("SLEEVE")
spy = {**{d: v for d, v in PL["SPY"].items() if d <= "2015-08-31"}, **{d: v for d, v in PRH["SPY"].items() if d > "2015-08-31"}}
sm = ks.sma_series(spy, 200)
gate_off = {d: (None if sm[d] is None else spy[d] < sm[d]) for d in spy}
_, fheld = s1.path(s1.half(w.approved("SLEEVE"), "FrontrunBonds"), PL, PRS)
ladder = {d: any(t not in ("BOXX", "BIL") and v > 1e-9 for t, v in h.items()) for d, h in fheld.items()}
book_days = sorted(E["BOOK"])
WT = {"HG": 0.341, "KMLM": 0.341, "SLEEVE": 0.318}
out["others"] = {}
for xid, st, own in (("X1_gate_off", gate_off, "HG"), ("X3_ladder_fired", ladder, "SLEEVE")):
    oth = [e for e in WT if e != own]
    out["others"][xid] = {}
    for which, lo, hi in (("verdict", "2015-06-01", "9999"), ("real_2021_06_on", "2021-06-02", "9999"), ("mostly_real_2015_2020", "2015-06-01", "2020-12-02"), ("shape", "1994-06-01", "2015-06-01")):
        ds = [d for d in book_days if lo <= d < hi]
        sv = np.array([np.nan if st.get(prev.get(d)) is None else float(st[prev[d]]) for d in ds])
        r = np.array([sum(WT[e] * E[e][d] for e in oth) / sum(WT[e] for e in oth) for d in ds])
        rr = m1.map_row(sv, r)
        row = dict(rr[0]) if rr else {}
        for e in oth:
            r2 = m1.map_row(sv, np.array([E[e][d] for d in ds]))
            row[e] = {"diff_per_yr": r2[0]["diff_per_yr"], "p": r2[0]["p_two_sided"], "on_per_yr": r2[0]["on_per_yr"], "off_per_yr": r2[0]["off_per_yr"]} if r2 else None
        row["merged_regimes"] = merged(np.nan_to_num(sv))
        row["own_engine_on_per_yr"] = float(np.log1p(np.array([E[own][d] for d in ds]))[np.nan_to_num(sv) == 1].mean() * 252)
        out["others"][xid][which] = row
# redeploy: while the gate is off, `step` of the book moves from Holy Grail to KMLM and the sleeve equally
out["redeploy"] = {}
for step in (0.10, 0.20, 0.341):
    for which, lo, hi in (("verdict", "2015-06-01", "9999"), ("real_2021_06_on", "2021-06-02", "9999"), ("mostly_real_2015_2020", "2015-06-01", "2020-12-02"), ("shape", "1994-06-01", "2015-06-01")):
        ds = [d for d in book_days if lo <= d < hi]
        s = np.nan_to_num(np.array([np.nan if gate_off.get(prev.get(d)) is None else float(gate_off[prev[d]]) for d in ds]))
        R = np.array([[E[e][d] for e in ("HG", "KMLM", "SLEEVE")] for d in ds])
        base = np.array([0.341, 0.341, 0.318])

        def path(sv):
            W = np.tile(base, (len(sv), 1))
            W[sv == 1] += np.array([-step, step / 2, step / 2])
            return (W * R).sum(1) - m1.COST * np.abs(np.diff(W, axis=0, prepend=W[:1])).sum(1)
        fixed, pol, mir = (base * R).sum(1), path(s), path(1 - s)
        n = len(ds)
        dg = np.array([g(path(np.roll(s, int(k)))) for k in rng.integers(63, n - 63, 500)]) - g(fixed)
        ddp = np.array([m1.maxdd(path(np.roll(s, int(k)))) for k in rng.integers(63, n - 63, 500)]) - m1.maxdd(fixed)
        yrs = {}
        for y in sorted({d[:4] for d in ds}):
            m = np.array([d[:4] == y for d in ds])
            yrs[y] = float((np.log1p(pol[m]) - np.log1p(fixed[m])).sum())
        out["redeploy"].setdefault(f"{step:.3f}", {})[which] = {
            "span": [ds[0], ds[-1], n], "gate_off_share": float(s.mean()), "fixed": [g(fixed), float(m1.maxdd(fixed))], "policy": [g(pol), float(m1.maxdd(pol))],
            "d_growth": g(pol) - g(fixed), "d_maxdd": float(m1.maxdd(pol) - m1.maxdd(fixed)), "mirror_d_growth": g(mir) - g(fixed), "p_growth": float((1 + np.sum(dg >= g(pol) - g(fixed))) / (1 + len(dg))),
            "p_maxdd": float((1 + np.sum(ddp <= m1.maxdd(pol) - m1.maxdd(fixed))) / (1 + len(ddp))), "by_year": yrs, "positive_years": int(sum(v > 0 for v in yrs.values())), "years_with_gate_off": int(sum(abs(v) > 1e-9 for v in yrs.values()))}
json.dump(out, open(os.path.join(HERE, "out", "followup.json"), "w"), indent=1)
print("regimes BOOK", {k: (v["switches_on"], v["merged_regimes"]) for k, v in out["regimes"]["BOOK"].items()})
for name in ("liquidity", "gold_off"):
    for which, v in out[name].items():
        print(name, which, "P1", {k: [round(z, 3) for z in x] if isinstance(x, list) else round(x, 3) for k, x in v["p1"].items()}, "dG", round(v["p1_test"]["d_growth"], 3), "p", v["p1_test"]["p_growth"], "dDD", round(v["p1_test"]["d_maxdd"] * 100, 1), "regimes", v["merged_regimes"],
              "| engines", {e: (round(x["diff_per_yr"], 2), round(x["p"], 3)) for e, x in v["per_engine_diff"].items() if x})
        if which == "verdict":
            print("    without:", {k: (round(v[k]["diff_per_yr"], 2), round(v[k]["p"], 3), round(v[k]["p1_d_growth"], 3)) for k in ("without_2020_2021", "without_2022", "without_2020_2022") if v.get(k)})
            print("    by year on-share / on-log / off-log:", {y: (round(x["on_share"], 2), round(x["on_log"], 2), round(x["off_log"], 2)) for y, x in v["by_year"].items()})
for xid, v in out["others"].items():
    for which, x in v.items():
        print(xid, which, "others on-off", round(x["diff_per_yr"], 2), "p", round(x["p_two_sided"], 3), "on share", round(x["on_share"], 2), "regimes", x["merged_regimes"], {e: (round(z["diff_per_yr"], 2), round(z["p"], 3)) for e, z in x.items() if isinstance(z, dict) and "diff_per_yr" in z}, "own on", round(x["own_engine_on_per_yr"], 2))
for step, v in out["redeploy"].items():
    for which, x in v.items():
        print("redeploy", step, which, x["span"][:2], "fixed", [round(z, 3) for z in x["fixed"]], "policy", [round(z, 3) for z in x["policy"]], "dG", round(x["d_growth"], 3), "p", x["p_growth"], "dDD", round(x["d_maxdd"] * 100, 1), "p", x["p_maxdd"], "mirror", round(x["mirror_d_growth"], 3), "years +", x["positive_years"], "/", x["years_with_gate_off"])
