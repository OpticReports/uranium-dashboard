"""B.5 structure study - evaluation per PREREG.md + DEVIATIONS.md amendment 1.
Run: python run2.py  -> ../results2.json (+ _cache/series2.pkl for charts)."""
import json, os, pickle, time
import numpy as np, pandas as pd
from scipy.stats import norm
import lib2 as L
from lib2 import C, E, IX, LIVE, N, vec

SEED = 20261119; DRAWS = 4000
SIX = ["AVUV", "PHYS", "QUAL", "KMLM", "AVDV", "AVEM"]; SIXI = [IX[l] for l in SIX]; SIXW = LIVE[SIXI]
EPIS = [("2008 crisis", "2007-10-09", "2009-03-09"), ("2009 rebound", "2009-03-10", "2009-12-31"), ("2018 Q4", "2018-09-20", "2018-12-24"),
        ("2020 fall", "2020-02-19", "2020-03-23"), ("2020 rebound", "2020-03-24", "2020-12-31"), ("2022", "2022-01-03", "2022-10-14"),
        ("2025 tariff drop", "2025-02-19", "2025-04-08")]
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:5.0f}s]", *a, flush=True)


def swap(**delta):
    """Live weights plus the given changes (in weight points)."""
    w = LIVE.copy()
    for k, v in delta.items():
        w[IX[k]] += v
    assert abs(w.sum() - 1) < 1e-9 and w.min() > -1e-12, w
    return w


def p1_changes(tape, mode="cov", shrink=0.5):
    """D3: yearly targets from equal risk contribution across the six non-TAIL legs (cap 25% of book inside the
    solver), expanding weekly excess-return covariance since the first real KMLM-chain return, min 52 weeks."""
    cal = tape["cal"]; R = tape["R"]; ex = R[SIX].sub(R["BIL"], axis=0).loc[tape["kmlm_real_from"]:]
    wk = (1 + ex).resample("W-FRI").prod() - 1
    six_total = SIXW.sum(); out = []; log_w = {}
    for y in range(cal[0].year, cal[-1].year):
        ye = cal[cal.year == y][-1]; x = wk.loc[:ye]                   # weekly labels <= year-end: only weeks that have fully ended
        if len(x) < 52:
            continue
        cov = np.cov(x.values.T) if mode == "cov" else L.semicov(x.values)
        w6 = L.erc(cov, cap=0.25 / six_total) * six_total
        w = LIVE.copy(); w[SIXI] = shrink * SIXW + (1 - shrink) * w6
        first_day = cal[cal.searchsorted(ye) + 1]
        out.append((first_day, w)); log_w[str(y + 1)] = {l: round(float(w[IX[l]]), 4) for l in SIX}
    return out, log_w


def lever_changes(tape, base_changes, r_base, r_live, cap=1.30, min_days=252):
    """D4: each year-end gross = min(cap, max(1, vol(L)/vol(base) since the base book first differed from L))."""
    cal = tape["cal"]; out = []; gl = {}
    if not base_changes:
        return out, gl
    start = int(cal.searchsorted(base_changes[0][0]))
    for d, w in base_changes:
        i = int(cal.searchsorted(d)); g = 1.0
        if i - start >= min_days:
            g = float(min(cap, max(1.0, r_live[start:i].std() / r_base[start:i].std())))
        wl = w * g; wl[-1] = 1.0 - g
        out.append((d, wl)); gl[str(pd.Timestamp(d).year)] = round(g, 4)
    return out, gl


def stats(r, c):
    m = E.metrics(r, c); m["sortino_m"] = L.sortino(r - c); m["sortino_avg"] = L.sortino_avg(r - c); return m


def scaled_live(rl, c, k, spread=0.015):
    """L scaled to k times its exposure: T-bills for the rest, or a loan at T-bills + spread (D13)."""
    return k * rl + (1 - k) * c - max(k - 1, 0) * spread / 252


def run_tape(p, variant, cost_mult=1.0, light=False, sel_override=None):
    tape = L.build(p, variant); cal = tape["cal"]; T = len(cal); c = tape["R"]["BIL"].values; cost = L.COST * cost_mult
    sim = lambda W, spread=None: L.sim(tape, W, cost, spread)
    ix = lambda d: int(cal.searchsorted(pd.Timestamp(d)))
    i0, ic = ix(C.EXT0), ix(C.CONF0)
    rl = sim(L.path(cal, LIVE)); spy = p["ret"]["SPY"].reindex(cal).values
    arms = {}

    def add(k, label, W, win=(i0, T), split=None, fam=False, kind="primary", spread=None, r=None):
        arms[k] = dict(label=label, W=W, r=sim(W, spread) if r is None else r, win=win,
                       split=split if split is not None else (ic if win == (i0, T) else (win[0] + win[1]) // 2), fam=fam, kind=kind, spread=spread)

    # ---- P1 family
    ch1, w1 = p1_changes(tape); W1 = L.path(cal, LIVE, ch1)
    add("P1", "Risk-balanced weights (six legs, halfway to live)", W1, fam=True)
    chb, w1b = p1_changes(tape, shrink=0.0); add("S1b", "Risk-balanced weights, no halfway shrink", L.path(cal, LIVE, chb), kind="secondary")
    chc, w1c = p1_changes(tape, mode="semi"); add("S1c", "Risk-balanced on downside co-movement", L.path(cal, LIVE, chc), kind="secondary")
    lev, gross = lever_changes(tape, ch1, arms["P1"]["r"], rl)
    Wlev = L.path(cal, LIVE, lev); g_path = 1.0 - Wlev[:, -1]                       # gross each day (1.0 until the first lever date)
    for s, k in ((0.015, "P2"), (0.005, "P2lo")):                                  # D15: constant gross, reset daily
        add(k, f"P1 scaled toward live volatility, financing T-bills + {s * 100:.1f}%", Wlev, kind="translation", spread=s,
            r=L.lever(arms["P1"]["r"], c, g_path, s))
    add("P2drift", "P2 as an unmanaged margin loan (leverage drifts between rebalances), T-bills + 1.5%", Wlev, kind="secondary", spread=0.015)
    w12 = LIVE * 1.2; w12[-1] = -0.2
    for s, k in ((0.015, "S2b"), (0.005, "S2blo")):
        add(k, f"Live book at 1.2x, financing T-bills + {s * 100:.1f}%", L.path(cal, w12), kind="secondary", spread=s, r=L.lever(rl, c, 1.2, s))
    # ---- P3 (D1: judged on CONF only)
    b0 = tape["first"]["BTAL"]; mid3 = ix("2022-01-03")
    add("P3", "TAIL replaced by BTAL", L.path(cal, LIVE, [(b0, swap(TAIL=-.059, BTAL=.059))]), win=(ic, T), split=mid3, fam=True)
    add("S3b", "Half of TAIL into BTAL", L.path(cal, LIVE, [(b0, swap(TAIL=-.0295, BTAL=.0295))]), win=(ic, T), split=mid3, kind="secondary")
    # ---- P4 (D5: sign only, from 2010-08-04)
    i4 = ix("2010-08-04")
    add("P4", "Trend sleeve as KMLM + DBMF, same 14.1%", L.path(cal, swap(KMLM=-.0705, DBMFc=.0705)), win=(i4, T), kind="sign-only")
    add("S4b", "Trend blend at 20% (from TAIL and AVUV)", L.path(cal, swap(KMLM=-.041, DBMFc=.10, TAIL=-.0295, AVUV=-.0295)), win=(i4, T), kind="secondary")
    # ---- P5
    eq = {l: -0.10 * pr for l, pr in zip(L.EQ, L.EQP)}
    add("P5", "10% Treasuries (IEF) funded from equity", L.path(cal, swap(IEF=.10, **eq)), fam=True)
    eqb = dict(eq); add("S5b", "5% IEF + 5% TIPS funded from equity", L.path(cal, swap(IEF=.05, TIP=.05, **eqb)), kind="secondary")
    w5c = LIVE.copy(); w5c[IX["IEF"]] = .10; w5c[-1] = -.10
    for s, k in ((0.015, "S5c"), (0.005, "S5clo")):
        add(k, f"Live book + 10% IEF, financed at T-bills + {s * 100:.1f}%", L.path(cal, w5c), kind="secondary", spread=s,
            r=rl + .10 * (tape["R"]["IEF"].values - c - s / 252) - .10 * 2e-4 / 252)
    # ---- P6 (D6: large value is primary)
    add("P6", "8 pts of AVUV to large value (AVLV)", L.path(cal, swap(AVUV=-.08, AVLVc=.08)), fam=True)
    add("S6a", "8 pts of AVUV to QUAL", L.path(cal, swap(AVUV=-.08, QUAL=.08)), kind="secondary")
    u0 = tape["first"]["USMV"]; add("S6b", "8 pts of AVUV to minimum-volatility (USMV)", L.path(cal, LIVE, [(u0, swap(AVUV=-.08, USMV=.08))]),
                                    win=(ix(u0), T), kind="secondary")
    # ---- exploratory
    add("E7", "5% long dollar (UUP) from TAIL", L.path(cal, LIVE, [(tape["first"]["UUP"], swap(TAIL=-.05, UUP=.05))]), kind="exploratory")
    add("E9a", "QUAL replaced by zero-cost collar index (CLLZ)", L.path(cal, swap(QUAL=-.153, CLLZ=.153)), kind="exploratory")
    add("E9b", "QUAL replaced by put-protected index (PPUT)", L.path(cal, swap(QUAL=-.153, PPUT=.153)), kind="exploratory")
    # ---- post-result diagnostics requested by the audit (N4, N5): never adjudicate
    add("C3", "Control: TAIL into T-bills (5.9%)", L.path(cal, LIVE, [(b0, swap(TAIL=-.059, BIL=.059))]), win=(ic, T), split=mid3, kind="control")
    add("C7", "Control: 5 pts of TAIL into T-bills", L.path(cal, LIVE, [(tape["first"]["UUP"], swap(TAIL=-.05, BIL=.05))]), kind="control")
    wfin = LIVE.copy(); wfin[SIXI] = [w1[str(cal[-1].year)][l] for l in SIX]
    add("X1", "Hindsight: idea 1's final weights held from 2007", L.path(cal, wfin), kind="posthoc")

    def window_stats(k, a, b, r=None):
        r = arms[k]["r"] if r is None else r
        ma = stats(r[a:b], c[a:b]); ml = stats(rl[a:b], c[a:b])
        return dict(arm=ma, live=ml, d_sharpe=ma["sharpe"] - ml["sharpe"], d_sortino=ma["sortino_m"] - ml["sortino_m"],
                    d_sortino_avg=ma["sortino_avg"] - ml["sortino_avg"],
                    d_cagr=ma["cagr"] - ml["cagr"], d_maxdd=ma["maxdd"] - ml["maxdd"], d_vol=ma["vol"] - ml["vol"])

    def episodes(r):
        out = {}
        for n, a, b in EPIS:
            i, j = ix(a), int(cal.searchsorted(pd.Timestamp(b), side="right"))
            out[n] = float(np.prod(1 + r[i:j]) - 1)
        return out

    # ---- COMBO (D11): selected on DISC, tape 1 selection passed in by the caller for tape 2
    res = dict(variant=variant, cost_mult=cost_mult, p1_weights=w1, p1_weights_noshrink=w1b, p1_weights_semi=w1c, gross=gross,
               live={w: stats(rl[a:b], c[a:b]) for w, (a, b) in (("EXT", (i0, T)), ("DISC", (i0, ic)), ("CONF", (ic, T)))},
               live_episodes=episodes(rl), arms={})
    sel = []; sel_marg = {}
    for k in (("P6", "P5", "P3", "P4", "P1") if sel_override is None else ()):
        a, b = (ix(b0), ic) if k == "P3" else ((max(i0, arms[k]["win"][0]), ic))
        s = window_stats(k, a, b); sel_marg[k] = dict(d_sharpe=s["d_sharpe"], d_sortino=s["d_sortino"])
        if s["d_sharpe"] > 0 and s["d_sortino"] > 0:
            sel.append(k)
    sel = sel if sel_override is None else list(sel_override)       # D11: tape 2 uses tape 1's selection
    res["combo_selected_on_disc"] = sel
    res["combo_selection_margins"] = sel_marg
    wc = LIVE.copy(); ch = []
    for k in sel:
        if k in ("P6", "P5", "P4"):
            wc = wc + (arms[k]["W"][-1] - LIVE)
    if "P3" in sel:
        w3 = wc.copy(); w3[IX["BTAL"]] += w3[IX["TAIL"]]; w3[IX["TAIL"]] = 0.0; ch.append((b0, w3))
    if "P1" in sel:
        base_now = lambda d: (ch[0][1] if ch and pd.Timestamp(d) >= pd.Timestamp(ch[0][0]) else wc)
        extra = []
        for d, w in ch1:
            wb = base_now(d).copy(); ratio = w[SIXI] / SIXW
            tot = wb[SIXI].sum() + wb[IX["DBMFc"]] + wb[IX["AVLVc"]] + wb[IX["IEF"]]
            wb[SIXI] = wb[SIXI] * ratio; wb[IX["DBMFc"]] *= ratio[SIX.index("KMLM")]; wb[IX["AVLVc"]] *= ratio[SIX.index("AVUV")]
            now = wb[SIXI].sum() + wb[IX["DBMFc"]] + wb[IX["AVLVc"]] + wb[IX["IEF"]]
            for j in SIXI + [IX["DBMFc"], IX["AVLVc"], IX["IEF"]]:
                wb[j] *= tot / now
            extra.append((d, wb))
        ch = sorted(ch + extra, key=lambda x: x[0])
        if "P3" in sel:                                                # keep the BTAL swap after each yearly P1 reset
            ch = [(d, w) for d, w in ch]
    Wc = L.path(cal, wc, ch)
    assert np.allclose(Wc.sum(1), 1) and Wc.min() > -1e-9
    add("COMBO", "DISC-selected combination: " + ("+".join(sel) if sel else "none"), Wc, win=(ic, T), split=mid3, kind="combo")

    keys = list(arms)
    for k in keys:
        a = arms[k]; w0, w1_ = a["win"]; sp = a["split"]
        o = dict(label=a["label"], kind=a["kind"], family=a["fam"], window=[str(cal[w0].date()), str(cal[w1_ - 1].date())], split=str(cal[sp].date()),
                 full=window_stats(k, w0, w1_), h1=window_stats(k, w0, sp), h2=window_stats(k, sp, w1_), episodes=episodes(a["r"]),
                 avg_gross=float(a["W"][w0:w1_, :-1].sum(1).mean()), final_weights={l: round(float(a["W"][-1, IX[l]]), 4) for l in L.COLS if abs(a["W"][-1, IX[l]]) > 1e-9})
        for nm, (x, y) in (("EXT", (i0, T)), ("DISC", (i0, ic)), ("CONF", (ic, T)), ("KMLM_real", (ix("2020-12-03"), T))):
            if x >= w0 or nm in ("CONF", "KMLM_real"):
                o[nm] = window_stats(k, max(x, w0) if nm != "CONF" else x, y)
        if k in ("P3", "S3b"):
            o["context_2011_2017"] = window_stats(k, ix(b0), ic)             # real BTAL vs stand-in TAIL: context only (D1)
        # controls for CAGR / drawdown (D13) and the SPY + T-bills benchmark at the arm's volatility
        ra = a["r"][w0:w1_]; kk = ra.std() / rl[w0:w1_].std(); ks = ra.std() / spy[w0:w1_].std()
        sl = stats(scaled_live(rl[w0:w1_], c[w0:w1_], kk), c[w0:w1_]); sm = stats(scaled_live(spy[w0:w1_], c[w0:w1_], ks), c[w0:w1_])
        o["live_at_arm_vol"] = dict(k=float(kk), cagr=sl["cagr"], maxdd=sl["maxdd"], sharpe=sl["sharpe"], sortino_m=sl["sortino_m"], sortino_avg=sl["sortino_avg"])
        o["spy_bills_at_arm_vol"] = dict(k=float(ks), cagr=sm["cagr"], maxdd=sm["maxdd"], sharpe=sm["sharpe"], sortino_m=sm["sortino_m"], sortino_avg=sm["sortino_avg"])
        res["arms"][k] = o
    if light:
        return res, None
    # ---- bootstrap on EXT rows, per-arm windows via the validity mask (D7), 21d and 63d blocks
    n = T - i0; A = np.column_stack([arms[k]["r"][i0:] - c[i0:] for k in keys]); B = np.repeat((rl[i0:] - c[i0:])[:, None], len(keys), 1)
    V = np.zeros((n, len(keys)), np.bool_)
    for j, k in enumerate(keys):
        V[max(arms[k]["win"][0] - i0, 0):arms[k]["win"][1] - i0, j] = True
    fam = [j for j, k in enumerate(keys) if arms[k]["fam"]]
    obsS = np.array([res["arms"][k]["full"]["d_sharpe"] for k in keys]); obsO = np.array([res["arms"][k]["full"]["d_sortino"] for k in keys])
    bs = {}
    for blk in (21, 63):
        idx = E.block_index(n, blk, DRAWS, SEED); dS, dO = L.boot2(np.ascontiguousarray(A), np.ascontiguousarray(B), V, idx)
        for nm, dr, ob in (("sharpe", dS, obsS), ("sortino", dO, obsO)):
            se, raw, adj, crit = L.pvals(dr, ob, fam)
            bs[(blk, nm)] = dict(se=se, raw=raw, adj=adj, crit=crit, ci=np.nanpercentile(dr, [2.5, 97.5], axis=0), draws=dr)
    for j, k in enumerate(keys):
        o = res["arms"][k]
        for nm in ("sharpe", "sortino"):
            b21, b63 = bs[(21, nm)], bs[(63, nm)]
            o[f"boot_{nm}"] = dict(se=float(max(b21["se"][j], b63["se"][j])), ci21=[float(b21["ci"][0, j]), float(b21["ci"][1, j])],
                                   ci63=[float(b63["ci"][0, j]), float(b63["ci"][1, j])], p_raw=float(max(b21["raw"][j], b63["raw"][j])),
                                   p_adj=float(max(b21["adj"][j], b63["adj"][j])) if j in fam else None,
                                   crit=float(max(b21["crit"], b63["crit"])))
            se = o[f"boot_{nm}"]["se"]; crit = o[f"boot_{nm}"]["crit"]
            o[f"boot_{nm}"]["mde80"] = float((crit + .8416) * se)
            o[f"boot_{nm}"]["power_at_plus_0.05"] = float(1 - norm.cdf(crit - 0.05 / se)) if nm == "sharpe" else None
        # N3: Sortino p with the grid-free estimate (phase-averaged observed change, draws centred on their own mean)
        dr = bs[(21, "sortino")]["draws"][:, j]; se_o = np.nanstd(dr, ddof=1); z = (dr - np.nanmean(dr)) / se_o
        o["boot_sortino"]["p_raw_avg"] = float(np.nanmean(z >= o["full"]["d_sortino_avg"] / se_o)); o["boot_sortino"]["boot_mean"] = float(np.nanmean(dr))
        if j in fam:
            Zf = bs[(21, "sortino")]["draws"][:, fam]; Zf = (Zf - np.nanmean(Zf, 0)) / np.nanstd(Zf, 0, ddof=1); mx = np.nanmax(Zf, 1)
            o["boot_sortino"]["p_adj_avg"] = float((mx >= o["full"]["d_sortino_avg"] / se_o).mean())
            # N6: joint power of IMPROVES' significance leg for a true +0.05 Sharpe (Sortino shifted in proportion)
            zs = (bs[(21, "sharpe")]["draws"][:, j] - obsS[j]) / bs[(21, "sharpe")]["se"][j]; zo = (dr - obsO[j]) / bs[(21, "sortino")]["se"][j]
            ratio = o["full"]["live"]["sortino_m"] / o["full"]["live"]["sharpe"]
            o["joint_power_at_plus_0.05"] = float(np.nanmean((zs + .05 / bs[(21, "sharpe")]["se"][j] > bs[(21, "sharpe")]["crit"]) &
                                                             (zo + .05 * ratio / bs[(21, "sortino")]["se"][j] > bs[(21, "sortino")]["crit"])))
    # N4: increments over a "just hold less TAIL" control (arm minus control, paired bootstrap, 21d blocks)
    res["increments"] = {}
    pairs = [("P3", "C3"), ("E7", "C7")]; Ai = np.column_stack([arms[a]["r"][i0:] - c[i0:] for a, _ in pairs]); Bi = np.column_stack([arms[b]["r"][i0:] - c[i0:] for _, b in pairs])
    Vi = np.column_stack([V[:, keys.index(a)] for a, _ in pairs]); dSi, dOi = L.boot2(np.ascontiguousarray(Ai), np.ascontiguousarray(Bi), np.ascontiguousarray(Vi), E.block_index(n, 21, DRAWS, SEED))
    for j, (a, b) in enumerate(pairs):
        w0, w1_ = arms[a]["win"]; xa = arms[a]["r"][w0:w1_] - c[w0:w1_]; xb = arms[b]["r"][w0:w1_] - c[w0:w1_]
        ds_ = E.sharpe(xa) - E.sharpe(xb); se_ = np.nanstd(dSi[:, j], ddof=1)
        res["increments"][f"{a}_over_{b}"] = dict(d_sharpe=ds_, d_sortino=L.sortino(xa) - L.sortino(xb), d_sortino_avg=L.sortino_avg(xa) - L.sortino_avg(xb),
                                                  ci_sharpe=[float(np.nanpercentile(dSi[:, j], 2.5)), float(np.nanpercentile(dSi[:, j], 97.5))],
                                                  ci_sortino=[float(np.nanpercentile(dOi[:, j], 2.5)), float(np.nanpercentile(dOi[:, j], 97.5))],
                                                  p_raw_sharpe=float(np.nanmean((dSi[:, j] - ds_) / se_ >= ds_ / se_)))
    series = dict(cal=cal, live=rl, cash=c, spy=spy, arms={k: arms[k]["r"] for k in keys}, W={k: arms[k]["W"] for k in ("P1", "S1b", "P2", "COMBO")},
                  win={k: arms[k]["win"] for k in keys})
    return res, series


def verdicts(R1, R2, R1c):
    """PREREG verdicts + D9 kill tests. R1/R2: tapes 1/2 at base cost; R1c: tape 1 at costs x2."""
    out = {}
    for k, a in R1["arms"].items():
        if not a["family"]:
            continue
        pos = lambda o: o["d_sharpe"] > 0 and o["d_sortino"] > 0
        b = R2["arms"][k]; cst = R1c["arms"][k]
        chk = dict(full_pos=pos(a["full"]), halves_pos=pos(a["h1"]) and pos(a["h2"]), p_sharpe=a["boot_sharpe"]["p_adj"], p_sortino=a["boot_sortino"]["p_adj"],
                   significant=a["boot_sharpe"]["p_adj"] < .10 and a["boot_sortino"]["p_adj"] < .10, costs2=pos(cst["full"]),
                   tape2=pos(b["full"]) and pos(b["h1"]) and pos(b["h2"]))
        if k == "P1":
            chk["kill_real_kmlm_sign"] = pos(a["KMLM_real"])
        if k == "P3":
            le = R1["live_episodes"]; chk["kill_episodes"] = all(a["episodes"][e] - le[e] >= -.015 for e in ("2020 fall", "2022"))
        if k == "P5":
            chk["kill_2017"] = pos(a["CONF"]) or (a["episodes"]["2020 fall"] > R1["live_episodes"]["2020 fall"])
        kills = all(v for kk, v in chk.items() if kk.startswith("kill"))
        if chk["full_pos"] and chk["halves_pos"] and chk["significant"] and chk["costs2"] and chk["tape2"] and kills:
            v = "IMPROVES"
        elif chk["full_pos"] and chk["halves_pos"]:
            v = "CANDIDATE"
        else:
            v = "NO"
        chk["verdict"] = v; out[k] = chk
    return out


def context_1993(p):
    r = p["ret"]; cash, _ = C.cash_series(p, p["cal"]); out = {}
    x = pd.concat([r["DFSVX"], r["DFLVX"], r["SPY"], cash.rename("c")], axis=1).loc["1993-03-01":"2007-05-31"].dropna()
    for s in ("DFSVX", "DFLVX", "SPY"):
        m = E.metrics(x[s].values, x["c"].values); out[s] = dict(cagr=m["cagr"], vol=m["vol"], sharpe=m["sharpe"], sortino_m=L.sortino((x[s] - x["c"]).values), maxdd=m["maxdd"])
    return out


def _rnd(o):
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {str(k): _rnd(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_rnd(v) for v in o]
    return o


def main():
    p = L.load()
    R1, S1 = run_tape(p, "T1"); log("tape 1 done")
    R2, S2 = run_tape(p, "T2", sel_override=R1["combo_selected_on_disc"]); log("tape 2 done")
    R1c, _ = run_tape(p, "T1", cost_mult=2.0, light=True, sel_override=R1["combo_selected_on_disc"]); log("costs x2 done")
    out = dict(meta=dict(end=str(p["end"].date()), seed=SEED, draws=DRAWS, family=[k for k, a in R1["arms"].items() if a["family"]],
                         gates=json.load(open(os.path.join(L.STUDY, "gates.json")))),
               T1=R1, T2=R2, T1_costs_x2=R1c, verdicts=verdicts(R1, R2, R1c), context_1993_2007=context_1993(p))
    json.dump(_rnd(json.loads(json.dumps(out, default=float))), open(os.path.join(L.STUDY, "results2.json"), "w"), separators=(",", ":"))
    pickle.dump(dict(T1=S1, T2=S2), open(os.path.join(L.STUDY, "_cache", "series2.pkl"), "wb")); log("saved")


if __name__ == "__main__":
    main()
