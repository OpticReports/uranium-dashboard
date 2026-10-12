#!/usr/bin/env python3
"""Scores SPEC v1 of studies/distress-signals.md ONCE (run order step 3).

    python3 study.py            -> prints the report, writes results.json

Every rule, window, mask and ship criterion is the one written in SPEC v1;
nothing here is tuned. Random draws use seed 20261012.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
import load as D  # noqa: E402
import panel as P  # noqa: E402
from engine import M, Period, mstr  # noqa: E402

SEED = 20261012
DRAWS = int(os.environ.get("DISTRESS_DRAWS", 9999))
THETAS = (0.05, 0.10, 0.15, 0.20)
QH_THETAS = (0.15, 0.25, 0.40, 0.60)
RAW_COURT = [(D.qi(2005, 2), D.qi(2008, 4)), (D.qi(2020, 2), D.qi(2021, 4))]
RAW_POLICY = [(D.qi(2020, 2), D.qi(2021, 4))]
R: dict = {"spec": "SPEC v1 (studies/distress-signals.md)", "seed": SEED, "draws": DRAWS,
           "run_month": mstr(E.RUN_MONTH), "T_N": mstr(E.T_N)}


def rng():
    return np.random.default_rng(SEED)


def in_any(i, raws):
    return any(a <= i <= b for a, b in raws)


def fmt_q(i):
    return D.qstr(i)


# ====================================================================== shared
TIE = 12          # round ratios before comparing: 2.34/1.95 - 1 is 0.2 exactly, not 0.19999...


def quarterly(values: dict[int, float], raws, rule, *, transform="sum4", release_lag=1,
              trend_window=None, start=None, end=None, drop_g=()):
    """Quarterly Period list over [start, end] (quarter indices).
    transform sum4: g = sum(t-3..t)/sum(t-7..t-4) - 1 (also d = avg change);
    qyoy: g = v(t)/v(t-4) - 1. rule(g, d) -> bool. Footprint masking over the
    whole input span (a break inside it contaminates the comparison); drop_g:
    quarters whose g is dropped without footprint expansion (Call Report flag)."""
    ks = sorted(values)
    start = ks[0] if start is None else start
    end = ks[-1] if end is None else end
    gvals: dict[int, tuple[float, float]] = {}
    for t in range(start, end + 1):
        if transform == "sum4":
            fp = list(range(t - 7, t + 1))
            if all(k in values for k in fp):
                a1 = sum(values[k] for k in range(t - 3, t + 1))
                a0 = sum(values[k] for k in range(t - 7, t - 3))
                gvals[t] = (round(a1 / a0 - 1, TIE), round((a1 - a0) / 4, TIE))
        elif transform == "qyoy":
            fp = [t - 4, t]
            if all(k in values for k in fp):
                gvals[t] = (round(values[t] / values[t - 4] - 1, TIE), round(values[t] - values[t - 4], TIE))
        else:
            raise ValueError(transform)
    span = 7 if transform == "sum4" else 4
    out, hist = [], []
    for t in range(start, end + 1):
        fp_masked = any(in_any(k, raws) for k in range(t - span, t + 1)) or in_any(t, drop_g)
        on = None
        if t in gvals and not fp_masked:
            g, d = gvals[t]
            if trend_window:
                if len(hist) >= trend_window:
                    med = statistics.median(hist[-trend_window:])
                    on = bool(rule(round(g - med, TIE), d))
                hist.append(g)
            else:
                on = bool(rule(g, d))
        out.append(Period(t, D.q_end_month(t) + release_lag, on))
    return out, gvals


def grade(by_theta: dict[float, list[Period]], L: int, quiet: int, q: int, per_year: int,
          primary=0.10, **kw) -> dict:
    s0 = by_theta[primary]
    S = E.scored_peaks(s0, L, lo=kw.get("lo", 0), hi=kw.get("hi"))
    Sp = E.scored_peaks(s0, L, panel=True, lo=kw.get("lo", 0), hi=kw.get("hi"))
    sc = {th: E.score(s, L, quiet, S, **kw) for th, s in by_theta.items()}
    yrs = E.years_scored(s0, L, per_year, lo=kw.get("lo", 0), hi=kw.get("hi"))
    allead = {th: len(S) >= 2 and sc[th]["n_lead"] == len(S) for th in by_theta}
    fa_ok = sc[primary]["n_false"] <= yrs / 10
    st = E.size_test(s0, L, quiet, S, q, **kw)
    okp = [x for x in sc[primary]["per_peak"] if x["outcome"] in ("LEAD", "COINCIDENT")
           and E.M(int(x["peak"][:4]), int(x["peak"][5:])) in Sp]
    return {
        "scored_peaks": [mstr(p) for p in S], "panel_scored_peaks": [mstr(p) for p in Sp],
        "primary": sc[primary], "by_theta": {str(th): {"per_peak": v["per_peak"], "n_false": v["n_false"],
                                                         "false_alarms": v["false_alarms"],
                                                         "pending": v["pending"]}
                                              for th, v in sc.items()},
        "years_scored": round(yrs, 2), "fa_cap": round(yrs / 10, 2),
        "lead_all_primary": allead[primary], "fa_ok": fa_ok,
        "grid_lead_all": sum(allead.values()), "rotation": st,
        "alert_pre_holm": allead[primary] and fa_ok and sum(allead.values()) >= 2,
        "panel_grade": len(Sp) >= 2 and len(okp) == len(Sp) and fa_ok,
    }


def onset_table(series, idx_list):
    return [mstr(series[i].release) for i in idx_list]


# ====================================================================== Q-N
def q_n() -> dict:
    out: dict = {}
    abi_b = D.abi_quarterly_business()
    f2b = D.f2_national("3month", "bus_all")
    # vintage check (data review): ABI quarters = AO first prints, every year 2001-2025
    vint = {y: (sum(abi_b[D.qi(y, q)] for q in range(1, 5)), sum(f2b[D.qi(y, q)] for q in range(1, 5)))
            for y in range(2001, 2026)}
    out["vintage_check_abi_vs_f2_first_prints"] = {
        "years_equal": sum(1 for a, b in vint.values() if a == b), "years": len(vint)}
    n1 = dict(abi_b)
    n1.update({t: v for t, v in f2b.items() if t >= D.qi(2026, 1)})
    ch12 = D.chapter12_annual()
    n1x = dict(n1)
    n1x[D.qi(1986, 4)] -= ch12[1986]
    for y in range(1987, 2027):
        for q in range(1, 5):
            t = D.qi(y, q)
            if t in n1x:
                n1x[t] -= ch12.get(y, ch12[2025]) / 4     # 2026: 2025 quarterly average
    n1s = dict(n1x)
    n1s[D.qi(1987, 2)] = (n1x[D.qi(1987, 1)] + n1x[D.qi(1987, 3)]) / 2
    out["n1_1995_quarters"] = {fmt_q(D.qi(1995, q)): abi_b[D.qi(1995, q)] for q in range(1, 5)}
    out["n1_1995_quarter_sum_vs_printed_total_vs_annual_table"] = [
        sum(abi_b[D.qi(1995, q)] for q in range(1, 5)), 51878, D.abi_annual()[1995]["business"]]

    def n1_series(base, theta, k95, transform="sum4"):
        v = dict(base)
        if k95:
            v[D.qi(1995, k95)] += 1000
        s, _ = quarterly(v, RAW_COURT, lambda g, d: g >= theta, transform=transform)
        return s

    combos = {}
    for name, base in (("N1", n1), ("N1x", n1x), ("N1s", n1s)):
        for k95 in (1, 2, 3, 4):
            by = {th: n1_series(base, th, k95) for th in THETAS}
            combos[f"{name}|1995Q{k95}"] = grade(by, 18, 4, 8, 4)
    out["N1_combos"] = combos
    worst_p = max(c["rotation"]["p"] for c in combos.values())
    out["N1_rotation_p_worst"] = worst_p
    out["N1_alert_pre_holm_all_combos"] = all(c["alert_pre_holm"] for c in combos.values())
    out["N1_panel_all_combos"] = all(c["panel_grade"] for c in combos.values())
    lead1990 = {k: any(x["peak"] == "1990-07" and x["outcome"] == "LEAD"
                       for x in c["primary"]["per_peak"]) for k, c in combos.items()}
    out["N1_1990_lead_by_combo"] = lead1990
    # robustness: single-quarter y/y; 12-month AO tables from 2001
    by_q = {th: n1_series(n1, th, 4, "qyoy") for th in THETAS}
    out["N1_robust_qyoy"] = grade(by_q, 18, 4, 8, 4)
    s12 = D.f2_national("12month", "bus_all")

    def s12_series(theta):
        vals = {}
        for t in range(D.qi(1981, 4), D.qi(2026, 2) + 1):
            def S(u):
                if u >= D.qi(2001, 1):
                    return s12.get(u)
                return sum(n1[k] for k in range(u - 3, u + 1)) if all(k in n1 for k in range(u - 3, u + 1)) else None
            a1, a0 = S(t), S(t - 4)
            if a1 is not None and a0 is not None:
                vals[t] = a1 / a0 - 1
        ser = []
        for t in range(D.qi(1980, 1), D.qi(2026, 2) + 1):
            masked = any(in_any(k, RAW_COURT) for k in range(t - 7, t + 1))
            on = None if (t not in vals or masked) else bool(vals[t] >= theta)
            ser.append(Period(t, D.q_end_month(t) + 1, on))
        return ser
    out["N1_robust_12month_tables"] = grade({th: s12_series(th) for th in THETAS}, 18, 4, 8, 4)
    # last-month dating and mask carry-over sensitivities (N1 as published, 1995 placement Q4)
    n1_q4 = dict(n1)
    n1_q4[D.qi(1995, 4)] += 1000
    out["N1_sens_lastmonth_dating"] = grade(
        {th: quarterly(n1_q4, RAW_COURT, (lambda th_: (lambda g, d: g >= th_))(th), release_lag=0)[0]
         for th in THETAS}, 18, 4, 8, 4)
    by_c = {th: n1_series(n1, th, 4) for th in THETAS}
    out["N1_sens_mask_carryover"] = grade(by_c, 18, 4, 8, 4, reset_on_mask=False)

    # N2 annual
    ann = D.abi_annual()
    years = sorted(ann)

    def n2_series(theta, trend=False, masks=True):
        g = {y: round(ann[y]["nonbusiness"] / ann[y - 1]["nonbusiness"] - 1, TIE) for y in years if y - 1 in ann}
        out_s, hist = [], []
        for y in years[1:]:
            masked = masks and any(2005 <= yy <= 2008 or 2020 <= yy <= 2021 for yy in (y - 1, y))
            on = None
            if not masked:
                if trend:
                    if len(hist) >= 5:
                        on = bool(round(g[y] - statistics.median(hist[-5:]), TIE) >= theta)
                    hist.append(g[y])
                else:
                    on = bool(g[y] >= theta)
            out_s.append(Period(y, M(y + 1, 1), on))
        return out_s, g
    out["N2_annual"] = grade({th: n2_series(th)[0] for th in THETAS}, 18, 1, 2, 1)
    out["N2_annual_g"] = {str(y): round(v, 4) for y, v in n2_series(0.1)[1].items()}
    out["N2_annual_robust_trend"] = grade({th: n2_series(th, True)[0] for th in THETAS}, 18, 1, 2, 1)
    # +2 month release sensitivity for annual
    def n2_lag2(theta):
        s, _ = n2_series(theta)
        return [Period(p.ref, p.release + 1, p.on) for p in s]
    out["N2_annual_sens_release_plus2"] = grade({th: n2_lag2(th) for th in THETAS}, 18, 1, 2, 1)
    # N2 quarterly (robustness): ABI 1994-2000 + AO 3-month first prints from 2001
    nbq = {t: v for t, v in D.abi_quarterly_nonbusiness().items() if t < D.qi(2001, 1)}
    nbq.update(D.f2_national("3month", "nb_all"))
    by_n2q = {th: quarterly(nbq, RAW_COURT, (lambda th_: (lambda g, d: g >= th_))(th))[0] for th in THETAS}
    s = E.scored_peaks(by_n2q[0.10], 18)
    out["N2_quarterly_robust"] = {"scored_peaks": [mstr(p) for p in s],
                                  "score": E.score(by_n2q[0.10], 18, 4, s)}
    # N3 display only
    n3 = D.f2_national("3month", "bus_ch11")
    n3s, n3g = quarterly(n3, RAW_COURT, lambda g, d: g >= 0.10)
    out["N3_display"] = {"latest_g": {fmt_q(t): round(v[0], 4) for t, v in sorted(n3g.items())[-6:]},
                         "onsets": onset_table(n3s, E.onsets(n3s, 4))}

    # Holm across the family {N1 (worst combo), N2 annual}
    # robustness qualifiers (SPEC v1 s.0): LEAD at every scored peak only under a variant
    n1_variant_leads = any(out[k]["lead_all_primary"] for k in ("N1_robust_qyoy", "N1_robust_12month_tables"))
    out["N1_qualifiers"] = (["transform-sensitive"] if n1_variant_leads
                            and not combos["N1|1995Q4"]["lead_all_primary"] else [])
    out["N2_qualifiers"] = (["trend-sensitive"] if out["N2_annual_robust_trend"]["lead_all_primary"]
                            and not out["N2_annual"]["lead_all_primary"] else [])
    # onsets suppressed by the masks (present without masks, absent with them), primary theta
    def ons(series, quiet):
        return {mstr(series[i].release) for i in E.onsets(series, quiet)}
    n1m = quarterly(n1_q4, RAW_COURT, lambda g, d: g >= 0.10)[0]
    n1u = quarterly(n1_q4, [], lambda g, d: g >= 0.10)[0]
    n2m, n2u = n2_series(0.10)[0], n2_series(0.10, masks=False)[0]
    out["suppressed_onsets"] = {"N1": sorted(ons(n1u, 4) - ons(n1m, 4)),
                                "N2": sorted(ons(n2u, 1) - ons(n2m, 1))}
    # sensitivity: onsets leading the exogenous 2020-02 peak excluded instead of FALSE
    out["sens_2020_excluded"] = {
        "N1": grade(by_c, 18, 4, 8, 4, exo_policy="excluded")["primary"]["false_alarms"],
        "N2": grade({th: n2_series(th)[0] for th in THETAS}, 18, 1, 2, 1,
                    exo_policy="excluded")["primary"]["false_alarms"]}
    hp = E.holm({"N1": worst_p, "N2": out["N2_annual"]["rotation"]["p"]})
    out["holm"] = hp
    out["N1_ALERT"] = out["N1_alert_pre_holm_all_combos"] and hp["N1"] <= 0.10
    out["N2_ALERT"] = out["N2_annual"]["alert_pre_holm"] and hp["N2"] <= 0.10
    out["N1_PANEL"] = out["N1_panel_all_combos"]
    out["N2_PANEL"] = out["N2_annual"]["panel_grade"]

    # descriptive cross-correlation of N1 g with the 4-quarter change in UR
    un = D.fred_monthly("UNRATE", "fred_targets")
    urq = {}
    for t in range(D.qi(1948, 1), D.qi(2026, 3) + 1):
        ms = [m for m in range(12 * (t // 4) + 3 * (t % 4), 12 * (t // 4) + 3 * (t % 4) + 3) if m in un]
        if len(ms) >= 2:
            urq[t] = sum(un[m] for m in ms) / len(ms)
    dur = {t: urq[t] - urq[t - 4] for t in urq if t - 4 in urq and not
           any(in_any(k, RAW_POLICY) for k in range(t - 4, t + 1))}
    ser, gv = quarterly(n1_q4, RAW_COURT, lambda g, d: g >= 0.10)
    slots = [p.ref for p in ser if p.on is not None]
    gx = np.array([gv[t][0] for t in slots])

    def xcorr(gvec):
        res = {}
        for k in range(-8, 9):
            pairs = [(gvec[j], dur[t + k]) for j, t in enumerate(slots) if t + k in dur]
            a, b = np.array(pairs).T
            res[k] = float(np.corrcoef(a, b)[0, 1])
        return res
    obs = xcorr(gx)
    rots = [xcorr(np.roll(gx, k)) for k in range(8, len(gx) - 8 + 1)]
    band = {k: (float(np.percentile([r[k] for r in rots], 5)), float(np.percentile([r[k] for r in rots], 95)))
            for k in obs}
    kpk = max(obs, key=lambda k: obs[k])
    out["N1_xcorr_vs_dUR"] = {"corr_by_lead_q": {k: round(v, 3) for k, v in obs.items()},
                              "band90": {k: [round(a, 3), round(b, 3)] for k, (a, b) in band.items()},
                              "peak_lead_q": kpk, "peak_corr": round(obs[kpk], 3),
                              "peak_outside_band": obs[kpk] > band[kpk][1],
                              "note": "k > 0: filings growth at t vs the UR change ending t+k (filings lead)"}
    out["_series"] = {"N1": {fmt_q(t): v for t, v in sorted(n1.items())},
                      "N1_g": {fmt_q(t): round(v[0], 4) for t, v in sorted(gv.items())}}
    return out


# ====================================================================== Q-C
QC = {"DRALACBS": "dr", "DRBLACBS": "dr", "DRCLACBS": "dr", "DRCCLACBS": "dr", "DRSFRMACBS": "dr",
      "DRCRELEXFACBS": "dr", "CORALACBS": "co", "CORBLACBS": "co", "CORCCACBS": "co"}
FAS = {"DRCCLACBS", "CORCCACBS", "DRCLACBS", "DRALACBS", "CORALACBS"}
TYPE_SPECIFIC = {"DRBLACBS", "DRCLACBS", "DRCCLACBS", "DRSFRMACBS", "DRCRELEXFACBS", "CORBLACBS", "CORCCACBS"}


def qc_raws(sid):
    raws = list(RAW_POLICY)
    if sid in FAS:
        raws.append((D.qi(2010, 1), D.qi(2010, 1)))
    if sid == "CORCCACBS":
        raws.append((D.qi(2005, 3), D.qi(2006, 4)))
    return raws


def q_c() -> dict:
    out: dict = {"series": {}}
    pvals = {}
    joint = {}
    for sid, kind in QC.items():
        r = D.fred_quarterly(sid)
        floor = 0.10 if kind == "dr" else 0.05
        raws = qc_raws(sid)
        mk = lambda th, tr="sum4", extra=(): quarterly(  # noqa: E731
            r, raws + list(extra), (lambda g, d, th=th: g >= th and d >= floor), transform=tr, release_lag=2)[0]
        by = {th: mk(th) for th in THETAS}
        gr = grade(by, 18, 4, 8, 4)
        res = {"grade": gr, "floor_pp": floor, "raw_masks": [[fmt_q(a), fmt_q(b)] for a, b in raws]}
        res["robust_qyoy"] = grade({th: mk(th, "qyoy") for th in THETAS}, 18, 4, 8, 4)
        # pure percentage-point rule
        pp = {}
        for tpp in (0.10, 0.25, 0.50, 1.00):
            s, _ = quarterly(r, raws, (lambda g, d, t=tpp: d >= t), release_lag=2)
            S = E.scored_peaks(s, 18)
            sc = E.score(s, 18, 4, S)
            yrs = E.years_scored(s, 18, 4)
            pp[str(tpp)] = {"scored": [mstr(p) for p in S], "per_peak": sc["per_peak"],
                            "n_false": sc["n_false"],
                            "lead_all_fa_ok": len(S) >= 2 and sc["n_lead"] == len(S) and sc["n_false"] <= yrs / 10}
        res["robust_pp"] = pp
        res["pp_passes"] = sum(v["lead_all_fa_ok"] for v in pp.values()) >= 2
        if sid in TYPE_SPECIFIC:
            s = quarterly(r, raws, (lambda g, d: g >= 0.10 and d >= floor), release_lag=2,
                          drop_g=[(D.qi(2001, 1), D.qi(2002, 3))])[0]
            S = E.scored_peaks(s, 18)
            sc = E.score(s, 18, 4, S)
            res["callreport_2001_without_2001Q1_2002Q3"] = [x for x in sc["per_peak"] if x["peak"] == "2001-03"]
        res["qualifiers"] = ((["transform-sensitive"] if res["robust_qyoy"]["lead_all_primary"] else [])
                             + (["scale-sensitive"] if res["pp_passes"] else [])
                             ) if not gr["lead_all_primary"] else []
        res["robust_qyoy_record"] = {"per_peak": res["robust_qyoy"]["primary"]["per_peak"],
                                     "false_alarms": res["robust_qyoy"]["primary"]["false_alarms"],
                                     "rotation_p": res["robust_qyoy"]["rotation"]["p"],
                                     "lead_all_by_theta": {th: len(res["robust_qyoy"]["scored_peaks"]) >= 2 and all(
                                         x["outcome"] == "LEAD" for x in v["per_peak"])
                                         for th, v in res["robust_qyoy"]["by_theta"].items()}}
        sm = quarterly(r, raws, (lambda g, d: g >= 0.10 and d >= floor), release_lag=2)[0]
        su = quarterly(r, [], (lambda g, d: g >= 0.10 and d >= floor), release_lag=2)[0]
        res["suppressed_onsets"] = sorted({mstr(su[i].release) for i in E.onsets(su, 4)} -
                                          {mstr(sm[i].release) for i in E.onsets(sm, 4)})
        res["sens_2020_excluded_false_alarms"] = grade(by, 18, 4, 8, 4, exo_policy="excluded")["primary"]["false_alarms"]
        out["series"][sid] = res
        pvals[sid] = gr["rotation"]["p"]
        joint[sid] = by[0.10]
    # C&I on the top-100-bank series (Call Report flag)
    r100 = D.fred_quarterly("DRBLT100S")
    s = quarterly(r100, list(RAW_POLICY), lambda g, d: g >= 0.10 and d >= 0.10, release_lag=2)[0]
    S = E.scored_peaks(s, 18)
    out["DRBLT100S_flag_check"] = {"scored": [mstr(p) for p in S],
                                   "per_peak": E.score(s, 18, 4, S)["per_peak"]}
    hp = E.holm(pvals)
    out["holm"] = hp
    for sid in QC:
        g = out["series"][sid]["grade"]
        out["series"][sid]["ALERT"] = bool(g["alert_pre_holm"] and hp[sid] <= 0.10)
        out["series"][sid]["PANEL"] = bool(g["panel_grade"])
    # descriptive family null: rotate all 9 jointly by the same shift over the
    # calendar quarters where every series is computable; share of shifts in
    # which ANY series would meet LEAD-at-all-scored + FA cap
    common = sorted(set.intersection(*[{p.ref for p in s if p.on is not None} for s in joint.values()]))
    hits, total = 0, 0
    ser_idx = {sid: {p.ref: i for i, p in enumerate(s)} for sid, s in joint.items()}
    Ssets = {sid: E.scored_peaks(s, 18) for sid, s in joint.items()}
    for k in range(8, len(common) - 8 + 1):
        any_ship = False
        for sid, s in joint.items():
            vals = [s[ser_idx[sid][t]].on for t in common]
            rv = vals[-k:] + vals[:-k]
            new = list(s)
            for t, v in zip(common, rv):
                new[ser_idx[sid][t]] = Period(t, s[ser_idx[sid][t]].release, v)
            S = Ssets[sid]
            sc = E.score(new, 18, 4, S)
            if len(S) >= 2 and sc["n_lead"] == len(S) and sc["n_false"] <= E.years_scored(new, 18, 4) / 10:
                any_ship = True
                break
        hits += any_ship
        total += 1
    out["joint_rotation_any_series_alertlike_share"] = {"share": hits / total if total else None,
                                                        "shifts": total,
                                                        "common_support": [fmt_q(common[0]), fmt_q(common[-1])]
                                                        if common else None}
    return out


# ====================================================================== Q-H
OOS = (M(1967, 1), M(1983, 12))
CLEAN, FLAGGED = (M(1969, 12), M(1973, 11)), (M(1980, 1), M(1981, 7))


def g12(vals: dict[int, float], t: int):
    a1 = [vals.get(m) for m in range(t - 11, t + 1)]
    a0 = [vals.get(m) for m in range(t - 23, t - 11)]
    if any(v is None for v in a1 + a0):
        return None
    return round(sum(a1) / sum(a0) - 1, TIE)


def capped(vals: dict[int, float], mult: float) -> dict[int, float]:
    out = {}
    for m in sorted(vals):
        prior = [vals[k] for k in range(m - 24, m) if k in vals]
        out[m] = min(vals[m], mult * statistics.median(prior)) if len(prior) == 24 else vals[m]
    return out


def qh_series(vals, theta, lag=2, start=M(1954, 12), end=M(1986, 12), raws=(), peaks=E.PEAKS):
    ser = []
    for m in range(start, end + 1):
        g = g12(vals, m)
        masked = any(a <= k <= b for a, b in raws for k in range(m - 23, m + 1))
        ser.append(Period(m, m + lag, None if (g is None or masked) else bool(g >= theta)))
    return ser


def qh_grade(vals, *, lag=2, attribution=True) -> dict:
    start = M(1954, 12)
    lo, hi = OOS[0] - start, OOS[1] - start
    by = {th: qh_series(vals, th, lag) for th in QH_THETAS}

    def disc_for(theta):
        def disc(i):
            t = start + i
            window = [vals[m] for m in range(t - 23, t + 1)]
            j = int(np.argmax(window))
            others = window[:j] + window[j + 1:]
            w2 = list(window)
            w2[j] = statistics.median(others)
            return round(sum(w2[12:]) / sum(w2[:12]) - 1, TIE) < theta
        return disc if attribution else None
    S = E.scored_peaks(by[0.25], 24, lo=lo, hi=hi)
    sc = {th: E.score(by[th], 24, 6, S, lo=lo, hi=hi, discount=disc_for(th)) for th in QH_THETAS}

    def pattern(s):
        lead = {x["peak"] for x in s["per_peak"] if x["outcome"] == "LEAD"}
        return all(mstr(p) in lead for p in CLEAN) and any(mstr(p) in lead for p in FLAGGED)
    p0 = sc[0.25]
    leads = [x["lead_months"] for x in p0["per_peak"] if x["outcome"] == "LEAD"]
    st = E.size_test(by[0.25], 24, 6, S, 24, lo=lo, hi=hi, discount=disc_for(0.25))
    crit = {"lead_pattern": pattern(p0), "fa_le_2": p0["n_false"] <= 2,
            "median_lead_ge_6": bool(leads) and statistics.median(leads) >= 6,
            "rotation_p_le_0.10": st["p"] <= 0.10,
            "grid_ge_2_of_4": sum(pattern(sc[th]) for th in QH_THETAS) >= 2}
    return {"scored_peaks": [mstr(p) for p in S], "primary": p0,
            "by_theta": {str(th): {"per_peak": v["per_peak"], "n_false": v["n_false"],
                                   "false_alarms": v["false_alarms"], "onsets": v["onsets"]}
                         for th, v in sc.items()},
            "median_lead": statistics.median(leads) if leads else None, "rotation": st,
            "criteria": crit, "passes": all(crit.values())}


def harding_pagan(x: dict[int, float], k=5, min_phase=6, min_cycle=15, censor=6):
    """Bry-Boschan-style monthly turning points (Harding-Pagan rules) on x:
    local extrema within +/-k months, alternation (keep the more extreme),
    then the weaker pair (smaller amplitude) is removed while a phase is
    shorter than min_phase or a peak-to-peak / trough-to-trough cycle shorter
    than min_cycle; turning points within `censor` months of either end are
    dropped."""
    ms = sorted(x)
    lo, hi = ms[0], ms[-1]

    def ext(m, sign):
        nb = [m + j for j in range(-k, k + 1) if j and (m + j) in x]
        return len(nb) == 2 * k and all(sign * x[m] >= sign * x[n] for n in nb)
    tps = sorted([(m, "P") for m in ms if ext(m, 1)] + [(m, "T") for m in ms if ext(m, -1)])
    tps = [tp for tp in tps if lo + censor <= tp[0] <= hi - censor]
    amp = lambda a, b: abs(x[a[0]] - x[b[0]])  # noqa: E731
    changed = True
    while changed and len(tps) > 2:
        changed = False
        for i in range(len(tps) - 1):                     # alternation
            a, b = tps[i], tps[i + 1]
            if a[1] == b[1]:
                drop = b if (x[a[0]] >= x[b[0]]) == (a[1] == "P") else a
                tps.remove(drop)
                changed = True
                break
        if changed:
            continue
        pairs = [(i, amp(tps[i], tps[i + 1])) for i in range(len(tps) - 1)
                 if tps[i + 1][0] - tps[i][0] < min_phase]
        if pairs:                                         # shortest phases: drop the weakest pair
            i = min(pairs, key=lambda z: z[1])[0]
            del tps[i:i + 2]
            changed = True
            continue
        cyc = [i for i in range(len(tps) - 2) if tps[i + 2][0] - tps[i][0] < min_cycle]
        if cyc:
            i = cyc[0]
            # remove whichever adjacent pair inside the short cycle has the smaller amplitude
            j = i if amp(tps[i], tps[i + 1]) <= amp(tps[i + 1], tps[i + 2]) else i + 1
            del tps[j:j + 2]
            changed = True
    return tps


NBER_PRE = [(M(1895, 12), M(1897, 6)), (M(1899, 6), M(1900, 12)), (M(1902, 9), M(1904, 8)),
            (M(1907, 5), M(1908, 6)), (M(1910, 1), M(1912, 1)), (M(1913, 1), M(1914, 12)),
            (M(1918, 8), M(1919, 3)), (M(1920, 1), M(1921, 7)), (M(1923, 5), M(1924, 7)),
            (M(1926, 10), M(1927, 11)), (M(1929, 8), M(1933, 3)), (M(1937, 5), M(1938, 6)),
            (M(1945, 2), M(1945, 10)), (M(1948, 11), M(1949, 10)), (M(1953, 7), M(1954, 5)),
            (M(1957, 8), M(1958, 4)), (M(1960, 4), M(1961, 2))] + E.PEAKS


def q_h() -> dict:
    out: dict = {}
    nom = D.bcd14()
    cpi = D.fred_monthly("CPIAUCNS", "fred_targets")
    pce = D.fred_monthly("PCEPI", "fred_targets")
    real = {m: v / cpi[m] * 100 for m, v in nom.items()}
    out["primary_real_cpi"] = qh_grade(real)
    out["winsorized_3x"] = qh_grade(capped(real, 3.0))
    out["SHIP"] = out["primary_real_cpi"]["passes"] and out["winsorized_3x"]["passes"]
    out["sens_winsorized_2_5x"] = qh_grade(capped(real, 2.5))
    out["sens_pce_deflator"] = qh_grade({m: v / pce[m] * 100 for m, v in nom.items() if m in pce})
    out["sens_nominal"] = qh_grade(nom)
    out["sens_release_plus1"] = qh_grade(real, lag=1)
    out["sens_no_attribution"] = qh_grade(real, attribution=False)
    # Bry-Boschan-style replication on the centred 12-month moving average
    cma = {}
    for m in sorted(real):
        w = [real.get(k) for k in range(m - 6, m + 6)]
        w2 = [real.get(k) for k in range(m - 5, m + 7)]
        if all(v is not None for v in w + w2):
            cma[m] = (sum(w) + sum(w2)) / 24
    tps = harding_pagan(cma)
    trail = {m: sum(real[k] for k in range(m - 11, m + 1)) for m in real if all(k in real for k in range(m - 11, m + 1))}
    tps_tr = harding_pagan(trail)
    rep = []
    for p, _ in NBER_PRE:
        if not (M(1955, 6) <= p <= M(1986, 6)):
            continue
        cand = [m for m, t in tps if t == "T" and p - 36 <= m <= p]
        cand_tr = [m for m, t in tps_tr if t == "T" and p - 36 <= m <= p]
        rep.append({"peak": mstr(p), "liabilities_trough_cma": mstr(cand[-1]) if cand else None,
                    "lead_months_cma": p - cand[-1] if cand else None,
                    "liabilities_trough_trailing": mstr(cand_tr[-1]) if cand_tr else None,
                    "lead_months_trailing": p - cand_tr[-1] if cand_tr else None})
    out["replication_turning_points"] = rep
    tps15 = harding_pagan(cma, min_phase=15)
    rep15 = []
    for r_ in rep:
        pk = E.M(int(r_["peak"][:4]), int(r_["peak"][5:]))
        cand = [m for m, t in tps15 if t == "T" and pk - 36 <= m <= pk]
        rep15.append({"peak": r_["peak"], "lead_months_cma": pk - cand[-1] if cand else None})
    out["replication_phase15"] = rep15
    # context runs (not decisive)
    ma = D.nber_monthly("M0933AUSM144NNBR")
    mc = D.nber_monthly("M0933CUSM144NNBR")
    breaks = [(M(1933, 1), M(1933, 12)), (M(1934, 6), M(1939, 12)), (M(1939, 1), M(1940, 12))]
    ctx = {}
    for name, vals, a, b, peaks in (
            ("1894_1938_nominal_M0933A", ma, M(1896, 1), M(1938, 8), NBER_PRE[:12]),
            ("1948_1966_real_M0933C_BCD", {**{m: v / cpi[m] * 100 for m, v in mc.items() if m in cpi and m < M(1953, 1)},
                                           **{m: v for m, v in real.items() if m < M(1967, 1)}},
             M(1948, 1), M(1966, 12), NBER_PRE[13:17])):
        ser = qh_series(vals, 0.25, 2, start=a, end=b, raws=breaks)
        pk = [(p, t) for p, t in peaks]
        S = E.scored_peaks(ser, 24, peaks=pk, exogenous=frozenset())
        sc = E.score(ser, 24, 6, S, peaks=pk, exogenous=frozenset(), t_n=b)
        ctx[name] = {"scored_peaks": [mstr(p) for p in S], "per_peak": sc["per_peak"],
                     "n_false": sc["n_false"], "false_alarms": sc["false_alarms"],
                     "flags": "1907 and 1930-33 include bank failures (M0933A)" if "1894" in name else ""}
    out["context_runs"] = ctx
    out["_series"] = {"real_12m_g": {mstr(m): round(g12(real, m), 4) for m in range(M(1955, 1), M(1986, 13))
                                     if g12(real, m) is not None}}
    return out


# ====================================================================== Q-R helpers
def quarter_avg(monthly: dict[int, float], need=2) -> dict[int, float]:
    out = {}
    for m in sorted(monthly):
        t = (m // 12) * 4 + (m % 12) // 3
        out.setdefault(t, []).append(monthly[m])
    return {t: sum(v) / len(v) for t, v in out.items() if len(v) >= need}


def q4_avg(monthly: dict[int, float]) -> dict[int, float]:
    out = {}
    for y in range(1976, 2027):
        v = [monthly[M(y, mm)] for mm in (10, 11, 12) if M(y, mm) in monthly]
        if len(v) >= 2:
            out[y] = sum(v) / len(v)
    return out


def claims_quarterly(weekly: dict[dt.date, int]) -> dict[int, float]:
    acc = defaultdict(list)
    for d, v in weekly.items():
        acc[D.qi(d.year, (d.month - 1) // 3 + 1)].append(v)
    return {t: sum(v) / len(v) for t, v in acc.items() if len(v) >= 10}


def claims_annual(weekly: dict[dt.date, int]) -> dict[int, float]:
    acc = defaultdict(list)
    for d, v in weekly.items():
        acc[d.year].append(v)
    return {y: sum(v) / len(v) for y, v in acc.items() if len(v) >= 50}


def winsorize_cols(mat: np.ndarray) -> np.ndarray:
    out = mat.copy()
    for j in range(mat.shape[1]):
        col = mat[:, j]
        ok = ~np.isnan(col)
        if ok.sum() >= 3:
            lo, hi = np.percentile(col[ok], [1, 99])
            out[ok, j] = np.clip(col[ok], lo, hi)
    return out


def logg(S1, S0):
    return math.log((S1 + 0.5) / (S0 + 0.5))


class Panel:
    """Balanced matrices [unit x period] for one signal/target set."""

    def __init__(self, units, periods, g, y, ctrls, w=None, period_month=None, h=4):
        self.units, self.periods = units, periods
        self.g, self.y, self.ctrls, self.w = g, y, ctrls, w
        self.period_month = period_month
        self.h = h

    def usable(self):
        ok = ~np.isnan(self.g) & ~np.isnan(self.y)
        for c in self.ctrls:
            ok &= ~np.isnan(c)
        if self.w is not None:
            ok &= ~np.isnan(self.w)
        return ok

    def fit(self, cells=None, extra=None, no_unit_fe=False):
        ok = self.usable() if cells is None else cells
        u, t = np.nonzero(ok)
        cols = [P.dummies(t, drop_first=False)]
        if not no_unit_fe:
            cols.insert(0, P.dummies(u, drop_first=True))
        cols += [c[u, t] for c in self.ctrls]
        if extra is not None:
            cols += [e[u, t] if e.ndim == 2 else e for e in extra]
        X = np.column_stack(cols)
        w = None if self.w is None else self.w[u, t]
        m = P.FWL(self.y[u, t], self.g[u, t], X, u, w)
        return m, u, t


def div_ids(units):
    return np.array([list(D.DIVISIONS).index(D.DIVISION_OF[s]) for s in units])


def run_panel(pn: Panel, label: str, peaks_exclude: list[tuple[int, int]], oil_cells=None,
              us_target=None, half_split=None) -> dict:
    """Primary inference + co-check + bias/regional checks for one panel/target."""
    r = rng()
    ok = pn.usable()
    m, u, t = pn.fit()
    divs = div_ids(pn.units)
    cl_div = divs[u]
    res = {"label": label, "n_obs": int(ok.sum()), "n_units": int(len(np.unique(u))),
           "n_periods": int(len(np.unique(t))), "beta": m.beta}
    wcb = P.wild_cluster_bootstrap(m, cl_div, DRAWS, r)
    res["wcb_division"] = wcb
    res["se"] = {"division_cr1": m.cr1_se(cl_div), "state_cr1": m.cr1_se(u),
                 "twoway_state_period": m.twoway_se(u, t),
                 "driscoll_kraay": m.driscoll_kraay_se(t, 2 * pn.h)}
    # co-check: within-division Freedman-Lane on the balanced sub-panel
    rows = ok.all(1)
    cols = ok[rows].all(0) if rows.any() else None
    bal_units = np.nonzero(rows)[0]
    keep_t = np.nonzero(ok.all(0))[0]
    if len(keep_t) >= 5:
        sub = np.ix_(np.arange(len(pn.units)), keep_t)
        fl = P.freedman_lane_within(pn.y[sub], pn.g[sub], [c[sub] for c in pn.ctrls],
                                    np.ones((len(pn.units), len(keep_t)), bool), list(divs), DRAWS, rng(),
                                    None if pn.w is None else pn.w[sub])
        res["cocheck_freedman_lane_within_division"] = {**fl, "periods": int(len(keep_t))}
    else:
        res["cocheck_freedman_lane_within_division"] = None
    # split-panel jackknife
    per = np.unique(t)
    if half_split is None:
        cut = per[len(per) // 2]
    else:
        cut = half_split
    b1 = pn.fit(cells=ok & (np.arange(ok.shape[1])[None, :] < cut))[0].beta
    b2 = pn.fit(cells=ok & (np.arange(ok.shape[1])[None, :] >= cut))[0].beta
    res["jackknife"] = {"beta_first": b1, "beta_second": b2, "beta_bc": 2 * m.beta - (b1 + b2) / 2,
                        "split_at_period": pn.periods[cut] if isinstance(cut, (int, np.integer)) else cut}
    # regional checks
    lodo = {}
    for d in range(9):
        cells = ok & (divs != d)[:, None]
        lodo[list(D.DIVISIONS)[d]] = pn.fit(cells=cells)[0].beta
    res["leave_one_division_out"] = lodo
    if pn.period_month is not None:
        near = np.array([any(p - 12 <= pm <= tau + 12 for p, tau in peaks_exclude) for pm in pn.period_month])
        res["excl_near_national_peaks"] = pn.fit(cells=ok & ~near[None, :])[0].beta
    if oil_cells is not None:
        res["excl_oil_patch_2014Q3_2017Q4"] = pn.fit(cells=ok & ~oil_cells)[0].beta
    if us_target is not None:
        nU = len(pn.units)
        inter = [np.where(np.arange(nU)[:, None] == i, us_target[None, :], 0.0) for i in range(1, nU)]
        inter = [np.broadcast_to(x, ok.shape) for x in inter]
        res["state_loadings_on_national_cycle"] = pn.fit(extra=inter)[0].beta
    res["sens_no_state_fe"] = pn.fit(no_unit_fe=True)[0].beta
    checks = [res["jackknife"]["beta_bc"]] + list(lodo.values()) + \
        [res.get(k) for k in ("excl_near_national_peaks", "excl_oil_patch_2014Q3_2017Q4",
                              "state_loadings_on_national_cycle") if res.get(k) is not None]
    res["all_bias_regional_checks_positive"] = bool(all(c > 0 for c in checks))
    return res


# ====================================================================== Q-R data
def state_filings_panel_b(col: str, units: list[str]):
    s12 = D.f2_state("12month", col)
    q0, q1 = D.qi(2001, 1), D.qi(2026, 2)
    return {s: {t: s12[s][t] for t in range(q0, q1 + 1) if t in s12[s]} for s in units}


def build_panel_b(signal: str, target: str, cache: dict) -> Panel:
    units = [s for s in D.STATES if not (signal == "S2" and s == "DE")
             and not (target == "b" and s == "DC")]
    col = "nb_all" if signal == "S1" else "bus_ch7"
    S = state_filings_panel_b(col, units)
    q_lo, q_hi = D.qi(2002, 1), D.qi(2025, 3)
    periods = list(range(q_lo, q_hi + 1))
    nU, nT = len(units), len(periods)
    G = np.full((nU, nT), np.nan)
    W = np.full((nU, nT), np.nan)
    for i, s in enumerate(units):
        for j, t in enumerate(periods):
            if t in S[s] and t - 4 in S[s] and not any(in_any(k, RAW_COURT) for k in range(t - 7, t + 1)):
                G[i, j] = logg(S[s][t], S[s][t - 4])
                W[i, j] = 1 / (1 / max(S[s][t], 0.5) + 1 / max(S[s][t - 4], 0.5))
    G = winsorize_cols(G)
    ur = cache.setdefault("urq", {s: quarter_avg(v) for s, v in D.state_ur().items()})
    emp = cache.setdefault("empq", {s: quarter_avg(v, need=3) for s, v in D.state_payroll_nsa().items()})
    clw = cache.setdefault("claims_w", D.state_claims_weekly())
    clq = cache.setdefault("claims_q", {s: claims_quarterly(v) for s, v in clw.items()})

    def mat(f):
        A = np.full((nU, nT), np.nan)
        for i, s in enumerate(units):
            for j, t in enumerate(periods):
                try:
                    v = f(s, t)
                except (KeyError, ValueError, ZeroDivisionError):
                    v = None
                if v is not None:
                    A[i, j] = v
        return A

    def covid_bad(t):
        return any(in_any(k, RAW_POLICY) for k in range(t - 3, t + 5))   # LDV (t-4,t] or target (t,t+4]

    if target == "a":
        Y = mat(lambda s, t: ur[s][t + 4] - ur[s][t])
    else:
        Y = mat(lambda s, t: -(math.log(emp[s][t + 4]) - math.log(emp[s][t])))
    ctr = [mat(lambda s, t: ur[s][t] - ur[s][t - 4]), mat(lambda s, t: ur[s][t] - ur[s][t - 1]),
           mat(lambda s, t: ur[s][t]), mat(lambda s, t: math.log(emp[s][t]) - math.log(emp[s][t - 4])),
           mat(lambda s, t: math.log(sum(clq[s][k] for k in range(t - 3, t + 1)) /
                                     sum(clq[s][k] for k in range(t - 7, t - 3)))),
           mat(lambda s, t: math.log(clq[s][t] / clq[s][t - 4]))]
    bad = np.array([covid_bad(t) for t in periods])
    Y[:, bad] = np.nan
    w = None
    if signal == "S2":
        # v = cross-state median of within-state var(g) net of its Poisson part (floor 0.0025)
        vs = []
        for i in range(nU):
            ok = ~np.isnan(G[i])
            if ok.sum() > 4:
                vs.append(np.var(G[i, ok]) - np.mean(1 / W[i, ok]))
        v = max(float(np.median(vs)), 0.0025)
        w = 1 / (1 / W + v)
    pm = [D.q_end_month(t) for t in periods]
    pn = Panel(units, [fmt_q(t) for t in periods], G, Y, ctr, w, period_month=pm, h=4)
    pn.raw_S = S
    pn.qperiods = periods
    return pn


def build_panel_a(signal: str, target: str, cache: dict) -> Panel:
    units = [s for s in D.STATES if not (signal == "S2" and s == "DE")
             and not (target == "b" and s == "DC")]
    rows = D._rows(os.path.join(D.DER, "abi_district_annual_1980_2000.csv"))
    S = defaultdict(lambda: defaultdict(int))
    col = "nonbusiness" if signal == "S1" else "business"
    for r in rows:
        if r["row_kind"] == "district" and r["is_territory"] == "0":
            S[r["state"]][int(r["year"])] += int(r[col])
    years = list(range(1981, 2001))
    nU, nT = len(units), len(years)
    G = np.full((nU, nT), np.nan)
    W = np.full((nU, nT), np.nan)
    for i, s in enumerate(units):
        for j, y in enumerate(years):
            if signal == "S2" and y in (1987, 1988):
                continue                                  # Chapter 12 ramp (SPEC v1)
            G[i, j] = logg(S[s][y], S[s][y - 1])
            W[i, j] = 1 / (1 / max(S[s][y], 0.5) + 1 / max(S[s][y - 1], 0.5))
    G = winsorize_cols(G)
    urm = cache.setdefault("ur_m", D.state_ur())
    empm = cache.setdefault("emp_m", D.state_payroll_nsa())
    ur4 = {s: q4_avg(v) for s, v in urm.items()}
    em4 = {s: q4_avg(v) for s, v in empm.items()}

    def mat(f):
        A = np.full((nU, nT), np.nan)
        for i, s in enumerate(units):
            for j, y in enumerate(years):
                try:
                    A[i, j] = f(s, y)
                except (KeyError, ValueError, ZeroDivisionError):
                    pass
        return A
    if target == "a":
        Y = mat(lambda s, y: ur4[s][y + 1] - ur4[s][y])
    else:
        Y = mat(lambda s, y: -(math.log(em4[s][y + 1]) - math.log(em4[s][y])))
    ctr = [mat(lambda s, y: ur4[s][y] - ur4[s][y - 1]),
           mat(lambda s, y: math.log(em4[s][y]) - math.log(em4[s][y - 1]))]
    w = None
    if signal == "S2":
        vs = []
        for i in range(nU):
            ok = ~np.isnan(G[i])
            if ok.sum() > 4:
                vs.append(np.var(G[i, ok]) - np.mean(1 / W[i, ok]))
        v = max(float(np.median(vs)), 0.0025)
        w = 1 / (1 / W + v)
    pn = Panel(units, [str(y) for y in years], G, Y, ctr, w, period_month=[M(y, 12) for y in years], h=1)
    pn.years = years
    pn.raw_S = S
    return pn


def us_change_panel_b(periods, cache):
    un = D.fred_monthly("UNRATE", "fred_targets")
    urq = quarter_avg(un)
    return np.array([urq.get(t + 4, np.nan) - urq.get(t, np.nan) for t in periods])


def us_change_panel_a(years):
    un = D.fred_monthly("UNRATE", "fred_targets")
    u4 = q4_avg(un)
    return np.array([u4.get(y + 1, np.nan) - u4.get(y, np.nan) for y in years])


def sahm_onsets(ur_m: dict[int, float]) -> list[int]:
    """State Sahm-style onsets: 3-month average UR minus the minimum of its
    prior 12 months >= 0.5pp; an onset is the first lit month after >= 12
    unlit months (v0 wording; see the v1.1 erratum)."""
    ms = sorted(ur_m)
    a3 = {}
    for m in ms:
        v = [ur_m[k] for k in (m - 2, m - 1, m) if k in ur_m]
        if len(v) >= 2 and m in ur_m:
            a3[m] = sum(v) / len(v)
    lit = {}
    for m in sorted(a3):
        prior = [a3[k] for k in range(m - 12, m) if k in a3]
        if len(prior) >= 10:
            lit[m] = a3[m] - min(prior) >= 0.5
    out, unlit = [], 0
    for m in sorted(lit):
        if lit[m]:
            if unlit >= 12:
                out.append(m)
            unlit = 0
        else:
            unlit += 1
    return out


def event_study(pn: Panel, cache: dict) -> dict:
    """Panel B event study (SPEC v1) with the claims benchmark."""
    units, periods = pn.units, pn.qperiods
    S = pn.raw_S
    pidx = {t: j for j, t in enumerate(periods)}
    clq = cache["claims_q"]

    def rel_growth(series_by_state):
        A = np.full((len(units), len(periods)), np.nan)
        for i, s in enumerate(units):
            for j, t in enumerate(periods):
                if any(in_any(k, RAW_COURT) for k in range(t - 7, t + 1)):
                    continue
                if t in series_by_state[s] and t - 4 in series_by_state[s]:
                    A[i, j] = math.log((series_by_state[s][t] + 0.5) / (series_by_state[s][t - 4] + 0.5))
        rel = np.full_like(A, np.nan)
        for j in range(A.shape[1]):
            col = A[:, j]
            ok = ~np.isnan(col)
            for i in np.nonzero(ok)[0]:
                rel[i, j] = col[i] - (col[ok].sum() - col[i]) / (ok.sum() - 1)
        sd = np.nanstd(rel, axis=1, keepdims=True)
        return rel / sd
    rF = rel_growth(S)
    C4 = {s: {t: sum(clq[s][k] for k in range(t - 3, t + 1)) for t in periods
              if all(k in clq[s] for k in range(t - 3, t + 1))} for s in units}
    rC = rel_growth(C4)
    urm = cache.setdefault("ur_m", D.state_ur())
    events, regional = [], []
    onset_info = {}
    for i, s in enumerate(units):
        ons = sahm_onsets(urm[s])
        onset_info[s] = [mstr(m) for m in ons]
        for m in ons:
            q = (m // 12) * 4 + (m % 12) // 3
            if q not in pidx:
                continue
            j = pidx[q]
            win = range(j - 12, j + 5)
            if win.start < 0 or win.stop > len(periods):
                continue
            if any(np.isnan(rF[i, k]) or np.isnan(rC[i, k]) for k in win):
                continue
            reg = not any(p - 12 <= m <= tau + 12 for p, tau in E.PEAKS)
            ev = {"state": s, "onset": mstr(m), "quarter": fmt_q(q), "i": i, "j": j, "regional": reg}
            events.append(ev)
            if reg:
                regional.append(ev)

    def D_stat(r, evs):
        if not evs:
            return float("nan")
        return float(np.mean([np.mean(r[e["i"], e["j"] - 4:e["j"]]) - np.mean(r[e["i"], e["j"] - 12:e["j"] - 8])
                              for e in evs]))

    def placebo(evs, draws):
        g = rng()
        all_on = {s: [((m // 12) * 4 + (m % 12) // 3) for m in sahm_onsets(urm[s])] for s in units}
        pools = []
        for e in evs:
            s = e["state"]
            cand = [j for j in range(12, len(periods) - 4)
                    if all(abs(periods[j] - q) >= 8 for q in all_on[s])
                    and not any(np.isnan(rF[e["i"], k]) or np.isnan(rC[e["i"], k]) for k in range(j - 12, j + 5))]
            pools.append(cand)
        if any(not p for p in pools):
            return None
        dF, dC = np.empty(draws), np.empty(draws)
        for b in range(draws):
            pe = [{"i": e["i"], "j": int(g.choice(pool))} for e, pool in zip(evs, pools)]
            dF[b], dC[b] = D_stat(rF, pe), D_stat(rC, pe)
        return dF, dC
    res = {"n_events": len(events), "n_regional": len(regional),
           "regional_years": sorted({e["onset"][:4] for e in regional}),
           "events": [{k: v for k, v in e.items() if k not in ("i", "j")} for e in events]}
    testable = len(regional) >= 8 and len({e["onset"][:4] for e in regional}) >= 4
    res["testable"] = testable
    for name, evs in (("all", events), ("regional", regional)):
        if not evs:
            res[name] = None
            continue
        dF, dC = D_stat(rF, evs), D_stat(rC, evs)
        pl = placebo(evs, DRAWS)
        rec = {"D_F": dF, "D_C": dC, "D_F_minus_D_C": dF - dC}
        # cluster-robust t with episodes = events whose onsets lie within 12 months
        d_e = np.array([np.mean(rF[e["i"], e["j"] - 4:e["j"]]) - np.mean(rF[e["i"], e["j"] - 12:e["j"] - 8])
                        for e in evs])
        months = sorted(range(len(evs)), key=lambda k: evs[k]["onset"])
        ep, cur, last = {}, 0, None
        for k in months:
            mm = M(int(evs[k]["onset"][:4]), int(evs[k]["onset"][5:]))
            if last is not None and mm - last > 12:
                cur += 1
            ep[k], last = cur, mm
        cl = np.array([ep[k] for k in range(len(evs))])
        G = len(np.unique(cl))
        if G >= 2:
            sums = np.bincount(cl, weights=d_e - d_e.mean())
            se = math.sqrt(G / (G - 1) * (sums @ sums)) / len(evs)
            rec["episode_cluster_t"] = float(d_e.mean() / se) if se > 0 else None
        rec["episodes"] = int(G)
        if pl is not None:
            pF, pC = pl
            rec["p_D_F"] = float((1 + np.sum(pF >= dF)) / (1 + DRAWS))
            rec["p_diff"] = float((1 + np.sum((pF - pC) >= (dF - dC))) / (1 + DRAWS))
        # mean paths -8..+8
        rec["path_filings"] = {k: float(np.nanmean([rF[e["i"], e["j"] + k] for e in evs
                                                    if 0 <= e["j"] + k < len(periods)])) for k in range(-12, 5)}
        rec["path_claims"] = {k: float(np.nanmean([rC[e["i"], e["j"] + k] for e in evs
                                                   if 0 <= e["j"] + k < len(periods)])) for k in range(-12, 5)}
        res[name] = rec
    reg = res.get("regional") or {}
    res["criterion_met"] = bool(testable and reg.get("p_D_F", 1) <= 0.05 and reg.get("D_F_minus_D_C", -1) > 0
                                and reg.get("p_diff", 1) <= 0.10)
    return res


def oos_clark_west(pn: Panel) -> dict:
    """Expanding-window OOS on the relative target (Panel B, target a)."""
    periods = pn.qperiods
    ok = pn.usable()

    def demean(A):
        return A - np.nanmean(A, axis=0, keepdims=True)
    y, g = demean(pn.y), demean(pn.g)
    C = [demean(c) for c in pn.ctrls]
    e0s, e1s, f0s, f1s, org = [], [], [], [], []
    for j, t in enumerate(periods):
        if not (D.qi(2015, 1) <= t <= D.qi(2025, 2)) or not ok[:, j].any():
            continue
        train = ok & (np.array(periods)[None, :] <= t - 4)
        if train.sum() < 200:
            continue
        u, tt = np.nonzero(train)
        X1 = np.column_stack([P.dummies(u)] + [c[u, tt] for c in C] + [g[u, tt]])
        X0 = X1[:, :-1]
        b1 = np.linalg.lstsq(X1, y[u, tt], rcond=None)[0]
        b0 = np.linalg.lstsq(X0, y[u, tt], rcond=None)[0]
        nU = len(pn.units)
        units_present = np.unique(u)
        for i in np.nonzero(ok[:, j])[0]:
            if i not in units_present:
                continue
            fe = np.zeros(len(units_present))
            fe[list(units_present).index(i)] = 1
            x1 = np.concatenate([fe, [c[i, j] for c in C], [g[i, j]]])
            f1 = float(x1 @ b1)
            f0 = float(x1[:-1] @ b0)
            e1s.append(y[i, j] - f1)
            e0s.append(y[i, j] - f0)
            f0s.append(f0)
            f1s.append(f1)
            org.append(t)
    if not org:
        return {"origins": 0}
    res = P.clark_west(np.array(e0s), np.array(e1s), np.array(f0s), np.array(f1s), np.array(org))
    res["first_origin"], res["last_origin"] = fmt_q(min(org)), fmt_q(max(org))
    return res


def reverse_and_confirms(pn: Panel) -> dict:
    """Reverse direction g(t->t+4) on dUR(t-4->t) with g(t); and the
    same-window relation dUR(t-4->t) on g(t) (label 'confirms')."""
    periods = pn.qperiods
    nU, nT = pn.g.shape
    S = pn.raw_S
    gfwd = np.full((nU, nT), np.nan)
    for i, s in enumerate(pn.units):
        for j, t in enumerate(periods):
            u = t + 4
            if u in S[s] and t in S[s] and not any(in_any(k, RAW_COURT) for k in range(t - 3, u + 1)):
                gfwd[i, j] = logg(S[s][u], S[s][t])
    dur_past = pn.ctrls[0]
    out = {}
    rev = Panel(pn.units, pn.periods, dur_past, gfwd, [pn.g], None, h=4)
    m, u, t = rev.fit()
    out["reverse_beta_dUR_on_future_g"] = m.beta
    out["reverse_wcb"] = P.wild_cluster_bootstrap(m, div_ids(pn.units)[u], DRAWS, rng())
    same = Panel(pn.units, pn.periods, pn.g, dur_past, [], None, h=4)
    m2, u2, _ = same.fit()
    out["same_window_beta"] = m2.beta
    out["same_window_wcb"] = P.wild_cluster_bootstrap(m2, div_ids(pn.units)[u2], DRAWS, rng())
    return out


def q_r() -> dict:
    out: dict = {"panel_B": {}, "panel_A": {}}
    cache: dict = {}
    nat_peaks = [(p, tau) for p, tau in E.PEAKS]
    for signal in ("S1", "S2"):
        for target in ("a", "b"):
            pn = build_panel_b(signal, target, cache)
            oil = np.zeros(pn.g.shape, bool)
            for i, s in enumerate(pn.units):
                if s in ("AK", "LA", "ND", "NM", "OK", "TX", "WY"):
                    for j, t in enumerate(pn.qperiods):
                        if D.qi(2014, 3) <= t <= D.qi(2017, 4):
                            oil[i, j] = True
            rp = run_panel(pn, f"B/{signal}/{target}", nat_peaks, oil_cells=oil,
                           us_target=us_change_panel_b(pn.qperiods, cache))
            if target == "a":
                rp["event_study"] = event_study(pn, cache)
                rp["oos_clark_west"] = oos_clark_west(pn)
                rp["reverse_and_confirms"] = reverse_and_confirms(pn)
                # robustness: summed 3-month first prints
                s3 = D.f2_state("3month", "nb_all" if signal == "S1" else "bus_ch7")
                alt = {}
                for s in pn.units:
                    alt[s] = {t: sum(s3[s].get(k, 0) for k in range(t - 3, t + 1)) for t in pn.qperiods
                              if all(k in s3[s] for k in range(t - 3, t + 1))}
                G2 = np.full(pn.g.shape, np.nan)
                for i, s in enumerate(pn.units):
                    for j, t in enumerate(pn.qperiods):
                        if t in alt[s] and t - 4 in alt[s] and not np.isnan(pn.g[i, j]):
                            G2[i, j] = logg(alt[s][t], alt[s][t - 4])
                pn2 = Panel(pn.units, pn.periods, winsorize_cols(G2), pn.y, pn.ctrls, pn.w, h=4)
                m2, _, _ = pn2.fit()
                rp["robust_3month_first_prints_beta"] = m2.beta
            out["panel_B"][f"{signal}/{target}"] = rp
        for target in ("a", "b"):
            pa = build_panel_a(signal, target, cache)
            usa = us_change_panel_a(pa.years)
            ra = run_panel(pa, f"A/{signal}/{target}", nat_peaks, us_target=usa,
                           half_split=pa.years.index(1991))
            # sensitivity: drop 1981-83 (state exemption opt-outs)
            ok = pa.usable() & (np.array(pa.years)[None, :] >= 1984)
            ra["sens_drop_1981_1983_beta"] = pa.fit(cells=ok)[0].beta
            # robustness: claims growth 1988-2000
            clw = cache.setdefault("claims_w", D.state_claims_weekly())
            cla = {s: claims_annual(v) for s, v in clw.items()}
            Cm = np.full(pa.g.shape, np.nan)
            for i, s in enumerate(pa.units):
                for j, y in enumerate(pa.years):
                    if y in cla.get(s, {}) and y - 1 in cla.get(s, {}):
                        Cm[i, j] = math.log(cla[s][y] / cla[s][y - 1])
            pc = Panel(pa.units, pa.periods, pa.g, pa.y, pa.ctrls + [Cm], pa.w, h=1)
            okc = pc.usable() & (np.array(pa.years)[None, :] >= 1988)
            mc, uc, _ = pc.fit(cells=okc)
            ra["robust_claims_1988_2000"] = {"beta": mc.beta,
                                             "wcb": P.wild_cluster_bootstrap(mc, div_ids(pa.units)[uc], DRAWS, rng())}
            out["panel_A"][f"{signal}/{target}"] = ra
    # ship logic per signal
    ship = {}
    decisive = {}
    for signal in ("S1", "S2"):
        runs = [out["panel_B"][f"{signal}/{t}"] for t in ("a", "b")] + \
               [out["panel_A"][f"{signal}/{t}"] for t in ("a", "b")]
        decisive[signal] = max(r["wcb_division"]["p"] for r in runs)
    hp = E.holm(decisive)
    for signal in ("S1", "S2"):
        runs = [out["panel_B"][f"{signal}/{t}"] for t in ("a", "b")] + \
               [out["panel_A"][f"{signal}/{t}"] for t in ("a", "b")]
        crit = {
            "beta_positive_all": all(r["beta"] > 0 for r in runs),
            "holm_primary_p_le_0.05": hp[signal] <= 0.05,
            "cocheck_p_le_0.10_all": all((r["cocheck_freedman_lane_within_division"] or {}).get("p", 1) <= 0.10
                                         for r in runs),
            "bias_regional_checks_all": all(r["all_bias_regional_checks_positive"] for r in runs),
            "event_study": out["panel_B"][f"{signal}/a"]["event_study"]["criterion_met"],
            "oos_clark_west_p_le_0.10": out["panel_B"][f"{signal}/a"]["oos_clark_west"].get("p", 1) <= 0.10,
        }
        insample = all(crit[k] for k in ("beta_positive_all", "holm_primary_p_le_0.05",
                                         "cocheck_p_le_0.10_all", "bias_regional_checks_all"))
        rc = out["panel_B"][f"{signal}/a"]["reverse_and_confirms"]
        confirms = rc["same_window_beta"] > 0 and rc["same_window_wcb"]["p"] <= 0.05
        verdict = ("REGIONAL ALERT" if insample and crit["event_study"] and crit["oos_clark_west_p_le_0.10"]
                   else "display-only map with the record" if insample
                   else "confirms (same-window relation)" if confirms else "no evidence of a lead")
        ship[signal] = {"criteria": crit, "decisive_p": decisive[signal], "holm_p": hp[signal],
                        "in_sample_pass": insample, "confirms_same_window": confirms, "verdict": verdict}
    out["ship"] = ship
    return out


# ====================================================================== secondary + current
BEAR_PEAKS = [M(1980, 11), M(1987, 8), M(2000, 3), M(2007, 10), M(2020, 2), M(2022, 1)]


def secondary(qn: dict, qc: dict) -> dict:
    baa = D.fred_monthly("BAA10YM", "fred_targets")
    ms = sorted(baa)
    lit = {m: (m - 6 in baa and baa[m] - baa[m - 6] >= 1.0) for m in ms}
    blow, unlit = [], 0
    for m in ms:
        if lit[m]:
            if unlit >= 12:
                blow.append(m)
            unlit = 0
        else:
            unlit += 1
    out = {"baa_blowouts": [mstr(m) for m in blow], "bear_market_peaks": [mstr(m) for m in BEAR_PEAKS]}

    def against(onsets, events):
        o_hit = sum(1 for o in onsets if any(e - 12 <= o <= e - 1 for e in events))
        e_hit = sum(1 for e in events if any(e - 12 <= o <= e - 1 for o in onsets))
        return {"onsets": len(onsets), "onsets_followed_within_12m": o_hit,
                "events": len(events), "events_preceded_within_12m": e_hit}
    combos = qn["N1_combos"]["N1|1995Q4"]["primary"]["onsets"]
    n1_on = [M(int(x["release"][:4]), int(x["release"][5:])) for x in combos]
    out["N1_vs_bear"] = against(n1_on, [e for e in BEAR_PEAKS if e >= M(1982, 1)])
    out["N1_vs_baa"] = against(n1_on, [e for e in blow if e >= M(1982, 1)])
    for sid, v in qc["series"].items():
        on = [M(int(x["release"][:4]), int(x["release"][5:])) for x in v["grade"]["primary"]["onsets"]]
        out[f"{sid}_vs_bear"] = against(on, BEAR_PEAKS)
        out[f"{sid}_vs_baa"] = against(on, blow)
    return out


def current(qn: dict) -> dict:
    out = {}
    g = qn["_series"]["N1_g"]
    out["N1_g_last8"] = dict(list(g.items())[-8:])
    out["N2_annual_g_last5"] = dict(list(qn["N2_annual_g"].items())[-5:])
    s12_nb = D.f2_state("12month", "nb_all")
    s12_b7 = D.f2_state("12month", "bus_ch7")
    pop = D.state_pop()
    last, prev = D.qi(2026, 2), D.qi(2025, 2)
    rows = []
    tot_nb = sum(s12_nb[s][last] for s in D.STATES)
    tot_nb0 = sum(s12_nb[s][prev] for s in D.STATES)
    for s in D.STATES:
        nb1, nb0 = s12_nb[s][last], s12_nb[s][prev]
        b1, b0 = s12_b7[s][last], s12_b7[s][prev]
        rows.append({"state": s, "nonbusiness_12m": nb1, "nonbusiness_yoy": round(nb1 / nb0 - 1, 4),
                     "nonbusiness_per_1000": round(nb1 / pop[s][2025], 3),
                     "business_ch7_12m": b1, "business_ch7_yoy": round(b1 / b0 - 1, 4) if b0 else None})
    out["state_12m_to_2026Q2"] = rows
    out["national_nonbusiness_12m_yoy_2026Q2"] = round(tot_nb / tot_nb0 - 1, 4)
    return out


def main():
    print("Q-N national filings ...", flush=True)
    R["Q_N"] = qn = q_n()
    print("Q-C bank delinquency ...", flush=True)
    R["Q_C"] = qc = q_c()
    print("Q-H failure liabilities ...", flush=True)
    R["Q_H"] = q_h()
    print("Q-R state panels ...", flush=True)
    R["Q_R"] = q_r()
    R["secondary"] = secondary(qn, qc)
    R["current"] = current(qn)
    with open(os.environ.get("DISTRESS_OUT", os.path.join(HERE, "results.json")), "w") as f:
        json.dump(R, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("wrote results.json")


if __name__ == "__main__":
    main()
