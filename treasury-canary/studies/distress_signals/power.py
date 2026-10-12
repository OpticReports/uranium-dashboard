#!/usr/bin/env python3
"""Power / size check of the SPEC v1 code on SYNTHETIC series (run order step 2).

No real filing, bank or liability data are touched. Checks:
  1. engine cross-check against the statistics reviewer's independent replica
     (same synthetic series, release lag 0) - LEAD and false-alarm counts;
  2. perfect-rule minimum rotation p for N1, N2 annual and Q-H;
  3. N1 ALERT pass rate under the null and under a true 12-month lead;
  4. Q-R inference size: division wild-cluster bootstrap and within-division
     Freedman-Lane on null panels with regional shocks (Panel B-like), and the
     Panel A design (Q4-to-Q4 target + coincident control) when filings only
     track the TRUE unemployment rate that the observed rate measures with noise.

    python3 power.py [n_sims_scale]   -> prints, writes power.json
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
import panel as P  # noqa: E402

SCALE = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
rng = np.random.default_rng(20261012)
OUT: dict = {"seed": 20261012, "scale": SCALE}
REVIEWER = "/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/distress/wf2/stats/engine.py"


# ------------------------------------------------------------ synthetic N1
def quarters(y0, y1q):
    out, y, q = [], y0, 1
    while (y, q) <= y1q:
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


QS = quarters(1980, (2026, 2))
RAW_MASKS = [((2005, 2), (2008, 4)), ((2020, 2), (2021, 4))]


def raw_masked(yq):
    return any(a <= yq <= b for a, b in RAW_MASKS)


def ar2_cycle(n, period, r, sd, burn=200):
    phi1, phi2 = 2 * r * math.cos(2 * math.pi / period), -r * r
    e = rng.normal(0, 1, n + burn)
    c = np.zeros(n + burn)
    for t in range(2, n + burn):
        c[t] = phi1 * c[t - 1] + phi2 * c[t - 2] + e[t]
    c = c[burn:]
    return c / c.std() * sd


def ramp(months, lead_m, A, decay_m=12):
    b = np.zeros(len(months))
    for p, tau in E.PEAKS:
        if p in E.EXOGENOUS:
            continue
        for i, d in enumerate(months):
            if p - lead_m <= d <= tau:
                b[i] = max(b[i], A * min(1.0, (d - (p - lead_m)) / lead_m))
            elif tau < d <= tau + decay_m:
                b[i] = max(b[i], A * (1 - (d - tau) / decay_m))
    return b


def n1_series(levels, theta, release_lag=1):
    """Quarterly g of 4-quarter sums with footprint masks -> list[Period]."""
    x = np.exp(levels)
    out = []
    for i, yq in enumerate(QS):
        ref_m = E.M(yq[0], 3 * yq[1])
        if i < 7 or any(raw_masked(QS[j]) for j in range(i - 7, i + 1)):
            on = None
        else:
            g = x[i - 3:i + 1].sum() / x[i - 7:i - 3].sum() - 1
            on = bool(g >= theta)
        out.append(E.Period(i, ref_m + release_lag, on))
    return out


def n1_grade(levels, release_lag=1):
    ser = {th: n1_series(levels, th, release_lag) for th in (0.05, 0.10, 0.15, 0.20)}
    s10 = ser[0.10]
    S = E.scored_peaks(s10, 18)
    sc = {th: E.score(s, 18, 4, S) for th, s in ser.items()}
    allead = {th: sc[th]["n_lead"] == len(S) for th in ser}
    yrs = E.years_scored(s10, 18, 4)
    fa_ok = sc[0.10]["n_false"] <= yrs / 10
    alert = len(S) >= 2 and allead[0.10] and fa_ok and sum(allead.values()) >= 2
    if alert:
        alert = E.size_test(s10, 18, 4, S, 8)["p"] <= 0.10
    Sp = E.scored_peaks(s10, 18, panel=True)
    ok = [x for x in sc[0.10]["per_peak"] if x["outcome"] in ("LEAD", "COINCIDENT")]
    panel = len(Sp) >= 2 and len(ok) == len(S) and fa_ok
    return alert, panel, S


# ------------------------------------------------------------ 1. engine cross-check
def check_engine():
    spec = importlib.util.spec_from_file_location("rev_engine", REVIEWER)
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    months = [E.M(y, 3 * q) for y, q in QS]
    agree = n = 0
    mism = []
    for k in range(int(300 * SCALE)):
        lv = ar2_cycle(len(QS), 26, 0.85, [0.05, 0.10, 0.20][k % 3]) + rng.normal(0, 0.04, len(QS))
        ser = n1_series(lv, 0.10, release_lag=0)
        S = [E.M(1990, 7), E.M(2001, 3)]
        mine = E.score(ser, 18, 4, S, t_n=E.M(2100, 1))
        dates = [p.release for p in ser]
        states = [p.on for p in ser]
        theirs = R.score(dates, states, R.NBER, 18, 4, tuple(S), exo=(R.M(2020, 2),),
                         reset_on_mask=True)
        n += 1
        if (mine["n_lead"], mine["n_false"]) == (theirs["leads"], theirs["fa"]):
            agree += 1
        elif len(mism) < 5:
            mism.append({"mine": (mine["n_lead"], mine["n_false"]),
                         "theirs": (theirs["leads"], theirs["fa"])})
    OUT["engine_crosscheck"] = {"series": n, "agree": agree, "mismatches": mism}
    print(f"[1] engine vs reviewer replica: {agree}/{n} identical (leads, false alarms)")


# ------------------------------------------------------------ 2. perfect-rule min p
def perfect_min_p():
    res = {}
    # N1: ON exactly in the two quarters released 4-9 months before each scored peak
    ser = n1_series(np.zeros(len(QS)), 0.10)
    S = E.scored_peaks(ser, 18)
    perf = []
    for p in ser:
        on = p.on if p.on is None else any(pk - 9 <= p.release <= pk - 4 for pk in S)
        perf.append(E.Period(p.ref, p.release, on))
    st = E.size_test(perf, 18, 4, S, 8)
    res["N1"] = {"scored": [E.mstr(x) for x in S], "R": st["R"], "p": st["p"], "min_p": st["min_p"]}
    # N2 annual 1980-2025: g from 1981; masked 2005-2009, 2020-2022; released Jan next year
    yrs = list(range(1981, 2026))
    ann = []
    for i, y in enumerate(yrs):
        masked = 2005 <= y <= 2009 or 2020 <= y <= 2022
        ann.append(E.Period(i, E.M(y + 1, 1), None if masked else False))
    S2 = E.scored_peaks(ann, 18)
    perf2 = [E.Period(p.ref, p.release, p.on if p.on is None else (yrs[p.ref] in (1989, 2000)))
             for p in ann]
    st2 = E.size_test(perf2, 18, 1, S2, 2)
    res["N2_annual"] = {"scored": [E.mstr(x) for x in S2], "R": st2["R"], "p": st2["p"],
                        "min_p": st2["min_p"]}
    # Q-H monthly: support 1967-01..1983-12, lead-in from 1955, released month + 2
    months = list(range(E.M(1955, 1), E.M(1986, 13)))
    lo, hi = months.index(E.M(1967, 1)), months.index(E.M(1983, 12))
    peaks_oos = [E.M(1969, 12), E.M(1973, 11), E.M(1980, 1), E.M(1981, 7)]
    qh = [E.Period(i, m + 2, any(pk - 14 <= m + 2 <= pk - 8 for pk in peaks_oos))
          for i, m in enumerate(months)]
    S3 = E.scored_peaks(qh, 24, lo=lo, hi=hi)
    st3 = E.size_test(qh, 24, 6, S3, 24, lo=lo, hi=hi)
    res["QH"] = {"scored": [E.mstr(x) for x in S3], "R": st3["R"], "p": st3["p"], "min_p": st3["min_p"],
                 "observed": st3["observed"]}
    OUT["perfect_rule"] = res
    for k, v in res.items():
        print(f"[2] {k}: scored {v['scored']}  R={v['R']}  perfect-rule p={v['p']:.4f}  min p={v['min_p']:.4f}")


# ------------------------------------------------------------ 3. N1 ALERT size / power
def n1_rates():
    months = [E.M(y, 3 * q) for y, q in QS]
    n = int(400 * SCALE)
    res = {}
    for sd in (0.05, 0.10, 0.20):
        for A, lead in ((0.0, 0), (0.30, 12), (0.30, 6)):
            a = pnl = 0
            for _ in range(n):
                lv = ar2_cycle(len(QS), 26, 0.85, sd) + rng.normal(0, 0.04, len(QS))
                if A:
                    lv = lv + ramp(months, lead, A)
                al, pa, _ = n1_grade(lv)
                a += al
                pnl += pa
            res[f"sd{sd}_A{A}_lead{lead}"] = {"alert": a / n, "panel": pnl / n, "n": n}
            print(f"[3] N1 sd={sd} ramp={A} lead={lead}m: P(ALERT)={a / n:.3f} P(PANEL)={pnl / n:.3f}")
    OUT["n1_alert_rates"] = res


# ------------------------------------------------------------ 4. Q-R inference size
DIV_SIZES = [6, 3, 5, 7, 9, 4, 4, 8, 5]
DIV_OF = np.repeat(np.arange(9), DIV_SIZES)
NU = len(DIV_OF)


def ar1(shape, rho, sd, burn=60):
    T = shape[-1]
    e = rng.normal(0, sd, shape[:-1] + (T + burn,))
    x = np.zeros_like(e)
    for t in range(1, T + burn):
        x[..., t] = rho * x[..., t - 1] + e[..., t]
    return x[..., burn:]


def panel_b_null(T_use=51, regional=True):
    """Null Panel B: UR and filings independent; national + regional + state AR(1)."""
    h, w = 4, 4
    Tr = T_use + 2 * w + h + 8
    u = ar1((1, Tr), 0.97, 0.25) + ar1((NU, Tr), 0.95, 0.15) + \
        (ar1((9, Tr), 0.95, 0.15)[DIV_OF] if regional else 0)
    f = ar1((1, Tr), 0.95, 0.05) + ar1((NU, Tr), 0.90, 0.05) + \
        (ar1((9, Tr), 0.90, 0.05)[DIV_OF] if regional else 0) + rng.normal(0, 0.05, (NU, Tr))
    S = np.stack([np.exp(f[:, t - 3:t + 1]).sum(1) for t in range(3, Tr)], 1)  # col j = t-3
    ts = np.arange(2 * w + 4, 2 * w + 4 + T_use)
    g = np.log(S[:, ts - 3] / S[:, ts - 7])
    y = u[:, ts + h] - u[:, ts]
    c = [u[:, ts] - u[:, ts - 4], u[:, ts] - u[:, ts - 1], u[:, ts]]
    return y, g, c


def fe_design(nU, nT, ctrl):
    uu = np.repeat(np.arange(nU), nT)
    tt = np.tile(np.arange(nT), nU)
    X = np.column_stack([P.dummies(uu), P.dummies(tt, drop_first=True)] + [c.ravel() for c in ctrl])
    return X, uu, tt


def qr_size():
    n = int(200 * SCALE)
    res = {}
    for regional in (False, True):
        rej_w = rej_fl = 0
        for k in range(n):
            y, g, c = panel_b_null(regional=regional)
            X, uu, tt = fe_design(NU, y.shape[1], c)
            m = P.FWL(y.ravel(), g.ravel(), X, uu)
            wcb = P.wild_cluster_bootstrap(m, DIV_OF[uu], 399, rng)
            rej_w += wcb["p"] <= 0.05
            if k < n // 2:
                fl = P.freedman_lane_within(y, g, c, np.ones_like(y, bool), list(DIV_OF), 199, rng)
                rej_fl += fl["p"] <= 0.05
        res[f"panelB_regional={regional}"] = {"wcb_size": rej_w / n, "fl_size": rej_fl / (n // 2),
                                              "sims": n}
        print(f"[4] Panel B null, regional shocks={regional}: WCB size {rej_w / n:.3f}  "
              f"within-division FL size {rej_fl / (n // 2):.3f}")
    # Panel A design: true UR random walk; observed UR = true + noise; filings and
    # payrolls track TRUE annual change (coincident only); nothing predicts the future
    for noise in (0.2, 0.4):
        rej = rej_noctl = 0
        for _ in range(n):
            T, Tm = 22, 22 * 12 + 24
            true = np.cumsum(rng.normal(0, 0.12, (NU, Tm)), 1) + \
                np.cumsum(rng.normal(0, 0.08, (9, Tm)), 1)[DIV_OF]
            obs = true + rng.normal(0, noise, (NU, Tm))
            q4 = lambda a, yr: a[:, 12 * yr + 21:12 * yr + 24].mean(1)  # Oct-Dec of year yr (+offset)
            Uo = np.stack([q4(obs, yr) for yr in range(T)], 1)
            Ut = np.stack([q4(true, yr) for yr in range(T)], 1)
            g = np.diff(Ut, axis=1)[:, :-1] + rng.normal(0, 0.05, (NU, T - 2))     # filings ~ true change t-1->t
            pay = -np.diff(Ut, axis=1)[:, :-1] + rng.normal(0, 0.02, (NU, T - 2))  # payroll growth (coincident)
            y = Uo[:, 2:] - Uo[:, 1:-1]                                            # Q4(t+1) - Q4(t)
            ldv = Uo[:, 1:-1] - Uo[:, :-2]
            X, uu, tt = fe_design(NU, T - 2, [ldv, pay])
            m = P.FWL(y.ravel(), g.ravel(), X, uu)
            rej += P.wild_cluster_bootstrap(m, DIV_OF[uu], 399, rng)["p"] <= 0.05
            X0, _, _ = fe_design(NU, T - 2, [ldv])
            m0 = P.FWL(y.ravel(), g.ravel(), X0, uu)
            rej_noctl += P.wild_cluster_bootstrap(m0, DIV_OF[uu], 399, rng)["p"] <= 0.05
        res[f"panelA_noise{noise}"] = {"primary_size": rej / n, "without_coincident_control": rej_noctl / n,
                                       "sims": n}
        print(f"[4] Panel A, UR noise {noise}pp: primary-model size {rej / n:.3f}; "
              f"without the coincident control {rej_noctl / n:.3f}")
    OUT["qr_size"] = res


if __name__ == "__main__":
    check_engine()
    perfect_min_p()
    n1_rates()
    qr_size()
    with open(os.path.join(HERE, "power.json"), "w") as f:
        json.dump(OUT, f, indent=1)
    print("wrote power.json")
