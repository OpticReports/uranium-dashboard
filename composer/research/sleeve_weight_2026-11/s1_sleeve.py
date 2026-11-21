"""The sleeve-weight study (PREREG.md): Q1 data or rule (eras by how real the inputs are; each half alone;
attribution by fund; E4 under four KMLM-signal variants), Q2 the hedge by era, Q3 the book by sleeve
weight against T-bills. Reads addendum 59's engine paths from the scratch cache. Writes out/sleeve.json."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "windows_2026-11"))
import wsim as w  # noqa: E402
from q2_stats import boot_idx, stat  # noqa: E402

ks = w.ks
ERAS = (("E1", "1994-06-01", "2002-07-31"), ("E2", "2002-08-01", "2011-10-31"), ("E3", "2011-11-01", "2015-05-31"),
        ("E4", "2015-06-01", "2020-12-01"), ("E5", "2020-12-02", "2023-01-31"), ("E6", "2023-02-01", "2026-11-19"))
WEIGHTS = (0.0, 0.10, 0.20, 0.318, 0.40, 0.50)
KS = w.kdata.SCRATCH + "/kmlm_synth"
rng = np.random.default_rng(20261125)


def half(tree, name):
    t = copy.deepcopy(tree)
    top = t["children"][0]
    top["children"] = [g for g in top["children"] if g.get("name") == name]
    assert len(top["children"]) == 1
    top["children"][0]["weight"] = {"num": 100, "den": 100}
    return t


def path(tree, PL, PR, makers=()):
    """{day: return}, {day: held} over the long panel to 2023-01-31 and fresh closes after"""
    a = w.simulate(tree, PL, w.SPAN["SLEEVE"]["M"][0], "2023-01-31", makers)
    b = w.simulate(tree, PR, *w.SPAN["SLEEVE"]["A"], makers)
    r = dict(zip(a["days"], a["ret"]))
    r.update(zip(b["days"], b["ret"]))
    return r, {**a["held"], **b["held"]}


def ci_log(x, draws=2000):
    lx = np.log1p(x)
    bs = np.array([lx[boot_idx(len(lx), rng)].mean() * 252 for _ in range(draws)])
    return [float(lx.mean() * 252), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))]


def era_stats(r, held=None):
    out = {}
    for e, lo, hi in ERAS:
        ds = [d for d in sorted(r) if lo <= d <= hi]
        x = np.array([r[d] for d in ds])
        s = stat(x)
        out[e] = {"sessions": len(ds), "cagr": s["cagr"], "maxdd": s["maxdd"], "sharpe": s["sharpe"], "vol": float(x.std(ddof=1) * math.sqrt(252)), "log_per_yr_ci90": ci_log(x)}
        if held:
            out[e]["share_out_of_cash"] = float(np.mean([any(t not in ("BOXX", "BIL") and v > 1e-9 for t, v in held[d].items()) for d in ds if d in held]))
    return out


def hedge(sl, ot):
    lo_, hi_ = ot <= np.quantile(ot, 0.05), ot >= np.quantile(ot, 0.95)
    rest = ~lo_
    se = math.sqrt(sl[lo_].var(ddof=1) / lo_.sum() + sl[rest].var(ddof=1) / rest.sum())
    return {"days": int(lo_.sum()), "other_on_worst": float(ot[lo_].mean()), "sleeve_on_worst": float(sl[lo_].mean()), "sleeve_on_other_days": float(sl[rest].mean()),
            "t": float((sl[lo_].mean() - sl[rest].mean()) / se) if se > 0 else 0.0, "sleeve_on_best": float(sl[hi_].mean()), "corr": float(np.corrcoef(sl, ot)[0, 1])}


def main():
    PL, PR = w.long_panel(), w.real_panel("SLEEVE")
    tree = w.approved("SLEEVE")
    out = {"eras": {e: [lo, hi] for e, lo, hi in ERAS}}
    full, held = path(tree, PL, PR)
    chk = json.load(open(w.CACHE + "/cells_SLEEVE.json"))
    ref = dict(zip(chk["long_days"], chk["cells"]["base"]["long"]["ret"]))
    assert max(abs(full[d] - ref[d]) for d in ref) < 1e-12, "not addendum 59's path"
    ih, ih_h = path(half(tree, "InverseHold"), PL, PR)
    fb, fb_h = path(half(tree, "FrontrunBonds"), PL, PR)
    out["q1"] = {"sleeve": era_stats(full, held), "InverseHold": era_stats(ih, ih_h), "FrontrunBonds": era_stats(fb, fb_h)}
    # attribution by fund held (sum of weight x next-day return, as a share of the era's summed return)
    days = sorted(full)
    att = {e: {} for e, _, _ in ERAS}
    for d0, d1 in zip(days[:-1], days[1:]):
        P = PL if d1 <= "2023-01-31" else PR
        e = next((e for e, lo, hi in ERAS if lo <= d1 <= hi), None)
        if e is None or d0 not in held or d1 == "2023-02-02" and d0 <= "2023-01-31":
            continue
        for t, wt in held[d0].items():
            if d0 in P[t] and d1 in P[t]:
                att[e][t] = att[e].get(t, 0.0) + wt * (P[t][d1] / P[t][d0] - 1)
    out["q1"]["by_fund_sum_of_daily_returns"] = {e: dict(sorted(((t, round(v, 4)) for t, v in a.items()), key=lambda kv: -abs(kv[1]))) for e, a in att.items()}
    # E4 under four readings of the one rebuilt input
    import long_panel as lp
    old = lp.build_long_prices()[0]["KMLM"]
    e4 = ERAS[3]
    var = {"rebuilt KMLM (base)": (tree, PL, ())}
    Pold = dict(PL, KMLM=old)
    var["old stand-in (RYMFX)"] = (tree, Pold, ())
    for label, val in (("inverse-fund tests always true", True), ("inverse-fund tests always false", False)):
        t = copy.deepcopy(tree)
        s = w.SLEEVE(t)
        for k, node in enumerate(s.hold):
            w.to_flag(node, k)
        mk = [lambda P, v=val: {d: v for d in P["SPY"]}] * 2
        var[label] = (t, PL, mk)
    out["q1"]["E4_variants"] = {}
    for label, (t, P, mk) in var.items():
        a = w.simulate(t, P, e4[1], e4[2], mk)
        x = np.array(a["ret"])
        s = stat(x)
        out["q1"]["E4_variants"][label] = {"cagr": s["cagr"], "maxdd": s["maxdd"], "sharpe": s["sharpe"], "log_per_yr_ci90": ci_log(x)}
    real = np.array([full[d] for d in days if d >= "2020-12-02"])
    out["q1"]["real_years_from_2020_12"] = {"cagr": stat(real)["cagr"], "maxdd": stat(real)["maxdd"], "log_per_yr_ci90": ci_log(real)}
    # ---- the other engines
    hg = json.load(open(w.CACHE + "/cells_HG.json"))
    HG = {**dict(zip(hg["long_days"], hg["cells"]["base"]["long"]["ret"])), **dict(zip(hg["real_days"], hg["cells"]["base"]["real"]["ret"]))}
    kl, kr = json.load(open(KS + "/cells_long.json")), json.load(open(KS + "/cells_real_tr.json"))
    KM = {**dict(zip(kl["days"], kl["cells"]["base"]["ret"])), **dict(zip(kr["days"], kr["cells"]["base"]["ret"]))}
    bil = {}
    for P, lo, hi in ((PL, "0", "2023-01-31"), (PR, "2023-02-01", "9")):
        b = P.get("BIL") or w.kdata.series("BIL", w.END)
        bd = sorted(b)
        bil.update({d1: b[d1] / b[d0] - 1 for d0, d1 in zip(bd, bd[1:]) if lo <= d1 <= hi})
    common = sorted(set(full) & set(HG) & set(KM) & set(bil))
    # ---- Q2 hedge by era
    out["q2"] = {}
    for e, lo, hi in ERAS + (("real_2021_06_on", "2021-06-02", "2026-11-19"),):
        ds = [d for d in common if lo <= d <= hi]
        if len(ds) < 200:
            continue
        pair = np.array([0.5 * HG[d] + 0.5 * KM[d] for d in ds])
        out["q2"][e] = {nm: {"pair": hedge(np.array([s[d] for d in ds]), pair), "HG": hedge(np.array([s[d] for d in ds]), np.array([HG[d] for d in ds])),
                             "KMLM": hedge(np.array([s[d] for d in ds]), np.array([KM[d] for d in ds]))} for nm, s in (("sleeve", full), ("InverseHold", ih), ("FrontrunBonds", fb))}
    # ---- Q3 the weight
    out["q3"] = {}
    stretches = ERAS[:4] + (("E5b", "2021-06-02", "2023-01-31"), ERAS[5], ("real_2021_06_on", "2021-06-02", "2026-11-19"), ("long_1994_2020", "1994-06-01", "2020-12-01"))
    for e, lo, hi in stretches:
        ds = [d for d in common if lo <= d <= hi]
        if len(ds) < 200:
            continue
        H, K, S, C = (np.array([x[d] for d in ds]) for x in (HG, KM, full, bil))
        book = lambda third, wt: (1 - wt) / 2 * (H + K) + wt * third   # noqa: E731
        row = {"sessions": len(ds), "span": [ds[0], ds[-1]], "engines": {n: {k: stat(x)[k] for k in ("cagr", "maxdd", "sharpe")} for n, x in (("HG", H), ("KMLM", K), ("SLEEVE", S), ("TBILLS", C))},
               "corr": {"HG-KMLM": float(np.corrcoef(H, K)[0, 1]), "HG-SLEEVE": float(np.corrcoef(H, S)[0, 1]), "KMLM-SLEEVE": float(np.corrcoef(K, S)[0, 1])},
               "by_weight": {f"{wt:.3f}": {"sleeve": {k: stat(book(S, wt))[k] for k in ("cagr", "maxdd", "sharpe")}, "tbills": {k: stat(book(C, wt))[k] for k in ("cagr", "maxdd", "sharpe")}} for wt in WEIGHTS}}
        dd = lambda x: float(np.max(1 - np.cumprod(1 + x) / np.maximum.accumulate(np.cumprod(1 + x))))   # noqa: E731
        for name, alt in (("vs_tbills", book(C, 0.318)), ("vs_no_third_leg", book(S, 0.0))):
            live = book(S, 0.318)
            d = np.log1p(live) - np.log1p(alt)
            g, sm = [], 0
            for _ in range(2000):
                ix = boot_idx(len(ds), rng)
                g.append(d[ix].mean() * 252)
                sm += dd(live[ix]) < dd(alt[ix])
            row[name] = {"dlog_per_yr": float(d.mean() * 252), "ci90": [float(np.quantile(g, 0.05)), float(np.quantile(g, 0.95))], "t": float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))),
                         "d_maxdd": dd(live) - dd(alt), "share_of_paths_sleeve_fall_smaller": sm / 2000,
                         "earns_it": bool(np.quantile(g, 0.05) > 0 or (sm / 2000 >= 0.90 and d.mean() >= 0))}
        out["q3"][e] = row
    json.dump(out, open(os.path.join(HERE, "out", "sleeve.json"), "w"), indent=1)
    f = lambda v: f"{v['cagr']:+.1%} dd {v['maxdd']:.0%} sh {v['sharpe']:.2f} log/yr {v['log_per_yr_ci90'][0]:+.2f} [{v['log_per_yr_ci90'][1]:+.2f},{v['log_per_yr_ci90'][2]:+.2f}]" + (f" active {v['share_out_of_cash']:.0%}" if "share_out_of_cash" in v else "")   # noqa: E731
    for nm in ("sleeve", "InverseHold", "FrontrunBonds"):
        for e, v in out["q1"][nm].items():
            print(f"Q1 {nm:13s} {e} n={v['sessions']:4d} {f(v)}")
    for e, a in out["q1"]["by_fund_sum_of_daily_returns"].items():
        print("   by fund", e, dict(list(a.items())[:7]))
    for k, v in out["q1"]["E4_variants"].items():
        print("E4", k, f(v))
    print("real years from 2020-12", out["q1"]["real_years_from_2020_12"])
    for e, v in out["q2"].items():
        for nm in ("sleeve", "InverseHold", "FrontrunBonds"):
            print(f"Q2 {e:16s} {nm:13s}", {o: (round(h['sleeve_on_worst'] * 100, 2), round(h['sleeve_on_other_days'] * 100, 2), round(h['t'], 1), round(h['sleeve_on_best'] * 100, 2), round(h['corr'], 2)) for o, h in v[nm].items()})
    for e, v in out["q3"].items():
        print(f"Q3 {e:16s} {v['span']} engines", {n: (round(x['cagr'], 2), round(x['maxdd'], 2)) for n, x in v["engines"].items()})
        print("      w: sleeve cagr/dd/sharpe | tbills", {wt: ((round(x['sleeve']['cagr'], 2), round(x['sleeve']['maxdd'], 2), round(x['sleeve']['sharpe'], 2)), (round(x['tbills']['cagr'], 2), round(x['tbills']['maxdd'], 2), round(x['tbills']['sharpe'], 2))) for wt, x in v["by_weight"].items()})
        for k in ("vs_tbills", "vs_no_third_leg"):
            print("     ", k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v[k].items()})


if __name__ == "__main__":
    main()
