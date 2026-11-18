"""B.5 overlay study - full evaluation per PREREG.md + DEVIATIONS.md amendment 1.
Run: python run.py   -> ../results.json (+ _cache/series.pkl for charts)
"""
import json, os, pickle, sys, time
import numpy as np, pandas as pd
import common as C, arms as A, engine as E

sys.path.insert(0, os.path.join(C.LAB, "src"))
from barbell.stats.dsr import deflated_sharpe, moments  # noqa: E402

SEED = 20261118; DRAWS = 4000
NOMASK = np.zeros(8, bool)
EPISODES = [("GFC", "2007-10-09", "2009-03-09"), ("2009-17", "2009-03-10", "2017-04-06"),
            ("2018 Q4", "2018-09-20", "2018-12-24"), ("COVID crash", "2020-02-19", "2020-03-23"),
            ("COVID rebound", "2020-03-24", "2020-12-31"), ("2022", "2022-01-03", "2022-10-14"),
            ("2023-26", "2023-01-03", "2026-11-17")]
t00 = time.time()


def log(*a):
    print(f"[{time.time() - t00:6.0f}s]", *a, flush=True)


class Tape:
    def __init__(self, p, variant):
        self.p = p; self.v = variant
        self.t = C.build_tape(p, variant)
        self.cal = self.t["cal"]; self.R = np.ascontiguousarray(self.t["R"].values); self.me = self.t["me"]
        self.c = self.R[:, -1].copy(); self.T = len(self.cal)
        i0 = int(self.cal.searchsorted(C.EXT0)); ic = int(self.cal.searchsorted(C.CONF0))
        self.win = {"EXT": (i0, self.T), "DISC": (i0, ic), "CONF": (ic, self.T)}
        self.baseW = np.repeat(C.BASE[None, :], self.T, 0)
        self.cost = C.COST.copy()
        self.base = self.sim(self.baseW)
        self.nav = pd.Series(np.cumprod(1 + self.base[0]), index=self.cal)

    def sim(self, W, win="EXT", cost=None, me=None, band=C.BAND, partial=True, tm=NOMASK, tmult=0.0):
        i0, i1 = self.win[win] if isinstance(win, str) else win
        return E.simulate(self.R, np.ascontiguousarray(W), self.cost if cost is None else cost,
                          self.me if me is None else me, band, C.CAL_DAYS, 1e-9, partial, tm, tmult, i0, i1)

    def met(self, out, win):
        i0, i1 = self.win[win] if isinstance(win, str) else win
        r, turn, cst, trig, _ = out
        return E.metrics(r[i0:i1], self.c[i0:i1], turn[i0:i1], cst[i0:i1], trig[i0:i1])

    def control(self, W, win, cost=None):
        """D4: static band-rebalanced book whose REALIZED average weights over the window match the arm's."""
        i0, i1 = self.win[win] if isinstance(win, str) else win
        n = i1 - i0
        target = self.sim(W, (i0, i1), cost)[4] / n
        c = target.copy()
        for _ in range(6):
            out = self.sim(np.repeat(c[None, :], self.T, 0), (i0, i1), cost)
            real = out[4] / n
            c = np.clip(c + (target - real), 0, None); c /= c.sum()
        out = self.sim(np.repeat(c[None, :], self.T, 0), (i0, i1), cost)
        return out, c, float(np.abs(out[4] / n - target).max()), target


def delta(ma, mb):
    return dict(d_sharpe=ma["sharpe"] - mb["sharpe"], d_cagr=ma["cagr"] - mb["cagr"], d_maxdd=ma["maxdd"] - mb["maxdd"],
                d_ulcer=ma["ulcer"] - mb["ulcer"], d_calmar=ma["calmar"] - mb["calmar"], d_vol=ma["vol"] - mb["vol"])


def boot(tp, pairs, win, block, seed=SEED):
    """pairs: list of (arm_ret_full, ctrl_ret_full). Returns dict of arrays (K,) and the D x K Sharpe draws."""
    i0, i1 = tp.win[win] if isinstance(win, str) else win
    Aex = np.column_stack([a[i0:i1] - tp.c[i0:i1] for a, _ in pairs]); Bex = np.column_stack([b[i0:i1] - tp.c[i0:i1] for _, b in pairs])
    idx = E.block_index(i1 - i0, block, DRAWS, seed)
    dS, dM, dD, dU = E.boot_pairs(np.ascontiguousarray(Aex), np.ascontiguousarray(Bex), idx)
    obs = np.array([E.sharpe(Aex[:, k]) - E.sharpe(Bex[:, k]) for k in range(Aex.shape[1])])
    se = dS.std(0, ddof=1); se = np.where(se > 1e-12, se, np.nan)
    tstat = obs / se
    Z = (dS - obs) / se
    return dict(obs=obs, se=se, t=tstat, Z=Z, p_raw=np.array([(Z[:, k] >= tstat[k]).mean() for k in range(len(obs))]),
                ci=np.percentile(dS, [2.5, 97.5], axis=0), ci_dd=np.percentile(dD, [2.5, 97.5], axis=0),
                ci_ulcer=np.percentile(dU, [2.5, 97.5], axis=0), ci_ret=np.percentile(dM, [2.5, 97.5], axis=0),
                p_dd=(dD <= 0).mean(0), p_ulcer=(dU >= 0).mean(0))


def maxt(b, cols):
    Z = np.nan_to_num(b["Z"][:, cols], nan=-9); mx = Z.max(1)
    return {k: float((mx >= b["t"][k]).mean()) for k in cols}, float(np.percentile(mx, 90))


def eval_arm(tp, mult, lag=1, costmult=1.0, wins=("EXT", "DISC", "CONF")):
    cost = tp.cost * costmult
    W = A.lagged(A.weights(mult), lag)
    out = tp.sim(W, "EXT", cost)
    res = dict(W=W, out=out, win={})
    for w in wins:
        co, cw, resid, target = tp.control(W, w, cost)
        ma = tp.met(out, w); mc = tp.met(co, w)
        res["win"][w] = dict(arm=ma, ctrl=mc, d=delta(ma, mc), d_live=delta(ma, tp.met(tp.base, w)),
                             ctrl_w=cw, resid=resid, avg_w=target, ctrl_ret=co[0])
    return res


def episodes(tp, r):
    out = {}
    for name, a, b in EPISODES:
        i = int(tp.cal.searchsorted(pd.Timestamp(a))); j = int(tp.cal.searchsorted(pd.Timestamp(b), side="right"))
        x = r[i:j]
        out[name] = dict(ret=float(np.prod(1 + x) - 1), maxdd=E.maxdd(x))
    return out


def run_tape(p, variant, full=True):
    tp = Tape(p, variant); T = tp.T; cal = tp.cal
    res = dict(variant=variant, tail_fit=tp.t["tail_fit"], windows={k: [str(cal[a].date()), str(cal[b - 1].date()), b - a] for k, (a, b) in tp.win.items()})
    res["live"] = {w: tp.met(tp.base, w) for w in tp.win}
    res["live_episodes"] = episodes(tp, tp.base[0])
    arms, flags = A.build(p, tp.t, tp.nav)
    ids = list(arms)
    prim = [ids.index(k) for k in A.PRIMARY]
    log(variant, "LIVE EXT", {k: round(v, 4) for k, v in res["live"]["EXT"].items() if k in ("cagr", "sharpe", "maxdd", "vol")})

    # ---- arms + mirrors at the primary setting
    ev = {k: eval_arm(tp, arms[k]["mult"]) for k in ids}
    evm = {k: eval_arm(tp, arms[k]["mirror"], wins=("EXT",) if not full else ("EXT", "DISC", "CONF")) for k in ids}
    log(variant, "arms evaluated")
    i0, i1 = tp.win["EXT"]
    rows = {}
    for k in ids:
        a = arms[k]; e = ev[k]; Wd = A.weights(a["mult"])
        ch = np.abs(Wd - C.BASE).max(1) > 1e-9
        states, counts = np.unique(np.round(Wd[i0:i1], 6), axis=0, return_counts=True)
        rows[k] = dict(id=k, label=a["label"], fam=a["fam"], primary=a["primary"],
                       first_active=str(cal[ch.argmax()].date()) if ch.any() else None,
                       first_active_ext=str(cal[i0 + ch[i0:].argmax()].date()) if ch[i0:].any() else None,
                       share_off_base=float(ch[i0:i1].mean()), top_state_share=float(counts.max() / counts.sum()),
                       near_static=bool(counts.max() / counts.sum() > .95),
                       inert_2008=bool(not ch[int(cal.searchsorted(pd.Timestamp("2008-01-01"))):int(cal.searchsorted(pd.Timestamp("2009-01-01")))].any()),
                       avg_exposure={w: float(1 - e["win"][w]["avg_w"][-1]) for w in e["win"]},
                       ctrl_resid={w: e["win"][w]["resid"] for w in e["win"]},
                       win={w: dict(arm=e["win"][w]["arm"], ctrl=e["win"][w]["ctrl"], d=e["win"][w]["d"], d_live=e["win"][w]["d_live"]) for w in e["win"]},
                       mirror={w: dict(arm=evm[k]["win"][w]["arm"], d=evm[k]["win"][w]["d"], d_live=evm[k]["win"][w]["d_live"]) for w in evm[k]["win"]},
                       episodes=episodes(tp, e["out"][0]), ctrl_episodes=episodes(tp, e["win"]["EXT"]["ctrl_ret"]))

    # ---- bootstrap: arm vs matched control (each window; 21d and 63d blocks), max-T on primary 8 and all 53
    for w in tp.win:
        pairs = [(ev[k]["out"][0], ev[k]["win"][w]["ctrl_ret"]) for k in ids]
        b21 = boot(tp, pairs, w, 21); b63 = boot(tp, pairs, w, 63)
        for nm, b in (("b21", b21), ("b63", b63)):
            pa8, crit8 = maxt(b, prim); pa53, crit53 = maxt(b, list(range(len(ids))))
            for j, k in enumerate(ids):
                rows[k]["win"][w][nm] = dict(se=float(b["se"][j]), t=float(b["t"][j]), p_raw=float(b["p_raw"][j]),
                                             ci=[float(b["ci"][0, j]), float(b["ci"][1, j])],
                                             ci_dd=[float(b["ci_dd"][0, j]), float(b["ci_dd"][1, j])],
                                             ci_ulcer=[float(b["ci_ulcer"][0, j]), float(b["ci_ulcer"][1, j])],
                                             p_maxt8=pa8.get(j), p_maxt53=pa53[j],
                                             mde_single=float(2.1232 * b["se"][j]),
                                             mde_family=float(((crit8 if j in prim else crit53) + .8416) * b["se"][j]))
            res.setdefault("maxt_crit", {})[f"{w}_{nm}"] = dict(crit8=crit8, crit53=crit53)
        if w == "EXT":
            pm = [(evm[k]["out"][0], evm[k]["win"][w]["ctrl_ret"]) for k in ids]
            bm = boot(tp, pm, w, 21)
            for j, k in enumerate(ids):
                rows[k]["mirror"]["EXT"]["b21"] = dict(se=float(bm["se"][j]), p_raw=float(bm["p_raw"][j]), ci=[float(bm["ci"][0, j]), float(bm["ci"][1, j])])
    log(variant, "bootstrap done")

    # ---- placebo: all admissible circular offsets, per window (D5); mirrors on EXT
    plc = {}
    for w, (a0, a1) in tp.win.items():
        offs = np.arange(63, (a1 - a0) - 63, dtype=np.int64)
        store = {}
        for k in ids:
            W = ev[k]["W"]
            pl = E.placebo_shift(tp.R, np.ascontiguousarray(W[a0:a1]), C.BASE.copy(), tp.cost, tp.me, C.BAND, C.CAL_DAYS, 1e-9,
                                 True, NOMASK, 0.0, a0, a1, offs, tp.c)
            store[k] = pl
            am = ev[k]["win"][w]["arm"]; cm = ev[k]["win"][w]["ctrl"]
            rows[k]["win"][w]["placebo"] = dict(n=len(offs), pct_sharpe=float((pl[:, 0] < am["sharpe"]).mean() * 100),
                                                pct_maxdd=float((pl[:, 1] < am["maxdd"]).mean() * 100),
                                                pct_ulcer=float((pl[:, 2] > am["ulcer"]).mean() * 100),
                                                pct_cagr=float((pl[:, 3] < am["cagr"]).mean() * 100),
                                                mean_sharpe=float(pl[:, 0].mean()), mean_maxdd=float(pl[:, 1].mean()),
                                                mean_ulcer=float(pl[:, 2].mean()), mean_cagr=float(pl[:, 3].mean()))
        for fam_name, fam in (("fw8", [ids[j] for j in prim]), ("fw53", ids)):
            for stat, col, key in (("maxdd", 1, "maxdd"), ("sharpe", 0, "sharpe")):
                imp = np.column_stack([store[k][:, col] - ev[k]["win"][w]["ctrl"][key] for k in fam])
                mx = imp.max(1)
                for k in fam:
                    act = ev[k]["win"][w]["arm"][key] - ev[k]["win"][w]["ctrl"][key]
                    rows[k]["win"][w]["placebo"][f"p_{fam_name}_{stat}"] = float((mx >= act).mean())
        plc[w] = store
        if w == "EXT":
            for k in ids:
                W = evm[k]["W"]
                pl = E.placebo_shift(tp.R, np.ascontiguousarray(W[a0:a1]), C.BASE.copy(), tp.cost, tp.me, C.BAND, C.CAL_DAYS, 1e-9,
                                     True, NOMASK, 0.0, a0, a1, offs, tp.c)
                am = evm[k]["win"][w]["arm"]
                rows[k]["mirror"]["EXT"]["placebo"] = dict(pct_sharpe=float((pl[:, 0] < am["sharpe"]).mean() * 100),
                                                           pct_maxdd=float((pl[:, 1] < am["maxdd"]).mean() * 100))
    log(variant, "placebo done")

    # ---- stress: execution lag and costs (all arms)
    for k in ids:
        st = {}
        for name, lag, cm in (("lag0", 0, 1), ("lag2", 2, 1), ("lag5", 5, 1), ("cost2", 1, 2), ("cost4", 1, 4)):
            e = eval_arm(tp, arms[k]["mult"], lag, cm)
            st[name] = {w: dict(d_sharpe=e["win"][w]["d"]["d_sharpe"], d_maxdd=e["win"][w]["d"]["d_maxdd"],
                                d_cagr=e["win"][w]["d"]["d_cagr"], sharpe=e["win"][w]["arm"]["sharpe"]) for w in e["win"]}
        rows[k]["stress"] = st
    log(variant, "stress done")

    # ---- DSR on the best Sharpe difference among every evaluated timing configuration (arms + mirrors)
    dser = {k: ev[k]["out"][0][i0:i1] - ev[k]["win"]["EXT"]["ctrl_ret"][i0:i1] for k in ids}
    dser.update({k + "_mirror": evm[k]["out"][0][i0:i1] - evm[k]["win"]["EXT"]["ctrl_ret"][i0:i1] for k in ids})
    srs = {k: float(v.mean() / v.std(ddof=1)) for k, v in dser.items() if v.std() > 0}
    best = max(srs, key=srs.get); mo = moments(dser[best])
    d = deflated_sharpe(srs[best], len(dser[best]), len(srs), float(np.var(list(srs.values()), ddof=1)), skew=mo["skew"], kurt=mo["kurt"])
    res["dsr"] = dict(best=best, n_trials=len(srs), sr_ann=srs[best] * np.sqrt(252), dsr=float(d["dsr"]), sr0_ann=float(d["sr0"] * np.sqrt(252)),
                      note="Sharpe of the daily (arm - matched control) return difference, not the Sharpe difference")

    # ---- verdicts (PREREG + D2/D4/D5/D13)
    for k in ids:
        r = rows[k]; W = r["win"]; fam = "p_maxt8" if r["primary"] else "p_maxt53"
        p_adj = max(W["EXT"]["b21"][fam], W["EXT"]["b63"][fam])
        sv = dict(d_ext_pos=W["EXT"]["d"]["d_sharpe"] > 0, p_adj=p_adj, p_adj_lt_10=p_adj < .10,
                  both_halves=W["DISC"]["d"]["d_sharpe"] > 0 and W["CONF"]["d"]["d_sharpe"] > 0,
                  placebo90=W["EXT"]["placebo"]["pct_sharpe"] >= 90,
                  lag2=r["stress"]["lag2"]["EXT"]["d_sharpe"] > 0, cost2=r["stress"]["cost2"]["EXT"]["d_sharpe"] > 0,
                  ge_live=W["EXT"]["d_live"]["d_sharpe"] >= 0)
        sv["pass"] = bool(all(v for kk, v in sv.items() if kk != "p_adj"))
        pf = W["EXT"]["placebo"]["p_fw8_maxdd" if r["primary"] else "p_fw53_maxdd"]
        dt = dict(dd2_both=W["DISC"]["d"]["d_maxdd"] >= .02 and W["CONF"]["d"]["d_maxdd"] >= .02,
                  ulcer_both=W["DISC"]["d"]["d_ulcer"] < 0 and W["CONF"]["d"]["d_ulcer"] < 0,
                  cagr_within=W["EXT"]["d"]["d_cagr"] >= -.005, p_fw=pf, p_fw_lt_10=pf < .10,
                  lag2=r["stress"]["lag2"]["DISC"]["d_maxdd"] > 0 and r["stress"]["lag2"]["CONF"]["d_maxdd"] > 0)
        dt["pass"] = bool(all(v for kk, v in dt.items() if kk != "p_fw"))
        r["verdict"] = dict(survives=sv, drawdown_tool=dt)
    res["arms"] = rows

    series = dict(cal=cal, live=tp.base[0], cash=tp.c, arms={k: ev[k]["out"][0] for k in ids},
                  ctrl={k: ev[k]["win"]["EXT"]["ctrl_ret"] for k in ids}, mirror={k: evm[k]["out"][0] for k in ids},
                  exposure={k: 1 - ev[k]["W"][:, -1] for k in ids}, W={k: ev[k]["W"] for k in A.PRIMARY},
                  placebo={w: {k: plc[w][k] for k in ids} for w in plc}, legs=tp.t["R"], src=tp.t["S"],
                  flags={k: (v.values if hasattr(v, "values") else v) for k, v in flags.items()})

    # ---- structural (static) and harvest arms vs LIVE
    def static(w):
        w = np.asarray(w, float); return tp.sim(np.repeat((w / w.sum())[None, :], T, 0))
    S = {}
    b = C.BASE
    for x in (.9, .8, .7):
        w = b * x; w[-1] = 1 - x; S[f"S-CASH{int(x * 100)}"] = (f"Book {int(x * 100)}% / bills {int(100 - x * 100)}%", static(w))
    for leg, vals in (("TAIL", (0, .10, .15)), ("KMLM", (0, .20, .25))):
        j = C.IX[leg]
        for v in vals:
            w = b.copy(); rest = 1 - b[j]; w = w * (1 - v) / rest; w[j] = v; w[-1] = 0
            S[f"S-{leg}{int(v * 100)}"] = (f"{leg} at {int(v * 100)}% (rest pro-rata)", static(w))
    for leg in C.LEGS:
        j = C.IX[leg]
        w = b.copy(); w[j] = 0; S[f"LOO-{leg}-prorata"] = (f"Drop {leg}, rest pro-rata", static(w))
        w = b.copy(); w[-1] = w[j]; w[j] = 0; S[f"LOO-{leg}-bil"] = (f"Drop {leg} into bills", static(w))
    allme = np.ones(T, bool); hm = np.zeros(8, bool); hm[[C.IX["KMLM"], C.IX["TAIL"]]] = True; am7 = np.ones(8, bool); am7[-1] = False
    H = {"H1": ("Band 10%", tp.sim(tp.baseW, band=.10)), "H2": ("Band 15%", tp.sim(tp.baseW, band=.15)),
         "H3": ("Band 30%", tp.sim(tp.baseW, band=.30)), "H4": ("Daily band check 20%", tp.sim(tp.baseW, me=allme)),
         "H5": ("Daily trim of any leg > 1.25x target", tp.sim(tp.baseW, tm=am7, tmult=1.25)),
         "H6": ("Daily trim of KMLM/TAIL > 1.25x target", tp.sim(tp.baseW, tm=hm, tmult=1.25))}
    res["static"] = {}
    names = list(S) + list(H); outs = [S[k][1] if k in S else H[k][1] for k in names]
    for w in tp.win:
        bb = boot(tp, [(o[0], tp.base[0]) for o in outs], w, 21)
        b6 = boot(tp, [(o[0], tp.base[0]) for o in outs], w, 63)
        for j, k in enumerate(names):
            m = tp.met(outs[j], w)
            res["static"].setdefault(k, dict(label=(S[k][0] if k in S else H[k][0]), win={}))["win"][w] = dict(
                m=m, d=delta(m, res["live"][w]), ci=[float(bb["ci"][0, j]), float(bb["ci"][1, j])],
                ci63=[float(b6["ci"][0, j]), float(b6["ci"][1, j])],
                ci_dd=[float(bb["ci_dd"][0, j]), float(bb["ci_dd"][1, j])], ci_ulcer=[float(bb["ci_ulcer"][0, j]), float(bb["ci_ulcer"][1, j])],
                p_raw=float(bb["p_raw"][j]))
    for k in names:
        res["static"][k]["episodes"] = episodes(tp, (S[k][1] if k in S else H[k][1])[0])
    series["static"] = {k: (S[k][1] if k in S else H[k][1])[0] for k in names}
    log(variant, "static + harvest done")

    # ---- walk-forward (D7): pick the best expanding-window arm each year-end, LIVE is a candidate
    cand = {"LIVE": (tp.base[0], tp.baseW)}; cand.update({k: (ev[k]["out"][0], ev[k]["W"]) for k in ids})
    res["walkforward"] = {}
    years = list(range(2010, cal[-1].year + 1))
    for crit in ("sharpe", "calmar"):
        W = tp.baseW.copy(); picks = {}
        for y in years:
            j0 = int(cal.searchsorted(pd.Timestamp(f"{y}-01-01"))); j1 = int(cal.searchsorted(pd.Timestamp(f"{y + 1}-01-01")))
            sc = {}
            for k, (r, _) in cand.items():
                m = E.metrics(r[i0:j0], tp.c[i0:j0]); sc[k] = m[crit]
            bk = max(sc, key=sc.get); picks[y] = bk
            W[j0:j1] = cand[bk][1][j0:j1]
        ws = (int(cal.searchsorted(pd.Timestamp("2010-01-01"))), T)
        out = tp.sim(W, ws); co, cw, resid, _ = tp.control(W, ws)
        ma = tp.met(out, ws); mc = tp.met(co, ws); ml = tp.met(tp.base, ws)
        offs = np.arange(63, (ws[1] - ws[0]) - 63, dtype=np.int64)
        pl = E.placebo_shift(tp.R, np.ascontiguousarray(W[ws[0]:ws[1]]), C.BASE.copy(), tp.cost, tp.me, C.BAND, C.CAL_DAYS, 1e-9,
                             True, NOMASK, 0.0, ws[0], ws[1], offs, tp.c)
        bb = boot(tp, [(out[0], co[0]), (out[0], tp.base[0])], ws, 21)
        res["walkforward"][crit] = dict(picks=picks, arm=ma, ctrl=mc, live=ml, d_ctrl=delta(ma, mc), d_live=delta(ma, ml),
                                        ci_vs_ctrl=[float(bb["ci"][0, 0]), float(bb["ci"][1, 0])], ci_vs_live=[float(bb["ci"][0, 1]), float(bb["ci"][1, 1])],
                                        placebo_pct_sharpe=float((pl[:, 0] < ma["sharpe"]).mean() * 100),
                                        placebo_pct_maxdd=float((pl[:, 1] < ma["maxdd"]).mean() * 100), resid=resid)
        series[f"wf_{crit}"] = out[0]
    log(variant, "walk-forward done")
    return res, series


# ------------------------------------------------------------------ LEG tier + signal isolation
def leg_tier(p):
    full = p["cal"]; cal = full[(full >= pd.Timestamp("1995-01-03")) & (full <= p["end"])]
    r = p["ret"]; cash, _ = C.cash_series(p, cal)
    src = {"AVUV": "DFSVX", "AVDV": "DISVX", "AVEM": "DFEMX", "QUAL": "SPY", "PHYS": "GLD"}
    splice = {"AVUV": "2019-10-01", "AVDV": "2019-10-01", "AVEM": "2019-10-01", "QUAL": "2013-07-19", "PHYS": "2010-03-01"}
    me = np.zeros(len(cal), bool); ym = cal.year * 12 + cal.month; me[:-1] = ym[1:] != ym[:-1]
    vix = p["adj"]["^VIX"].reindex(cal); v3 = p["adj"]["^VIX3M"].reindex(cal)
    out = {}; iso = {}; ser = {}
    for leg in C.RISK:
        live = r[leg].reindex(cal); px = r[src[leg]].reindex(cal)
        x = pd.Series(np.where((cal >= pd.Timestamp(splice[leg])) & live.notna().values, live, px), index=cal)
        first = x.first_valid_index(); j0 = int(cal.searchsorted(first)) + 252
        x = x.fillna(0.0); P = (1 + x).cumprod(); cn = (1 + cash).cumprod()
        R2 = np.ascontiguousarray(np.column_stack([x.values, cash.values])); T = len(cal)
        cost = np.array([C.COST[C.IX[leg]], 1e-4])
        s200 = C.sma(P, 200); s100 = C.sma(P, 100); rs = C.rsi(P)
        Pm = P[me]; m10 = Pm.rolling(10, min_periods=10).mean()
        rules = {"SMA200": A._on(P < s200),
                 "10-month SMA": C.monthly_hold((Pm >= m10).astype(float).where(m10.notna()).reindex(cal), me).values,
                 "252d TSMOM": C.monthly_hold((P / P.shift(252) > cn / cn.shift(252)).astype(float).where(P.shift(252).notna()), me).values,
                 "12% stop": C.stop_state(P.values, .12, s100.values),
                 "RSI70 half-trim": C.latch(rs > 70, rs < 50, 1.0, .5)}
        win = (j0, T); n = T - j0; c = cash.values

        def sim(W):
            return E.simulate(R2, np.ascontiguousarray(W), cost, me, C.BAND, C.CAL_DAYS, 1e-9, True, np.zeros(2, bool), 0.0, j0, T)
        bh = sim(np.repeat(np.array([[1.0, 0.0]]), T, 0))
        out[leg] = dict(start=str(cal[j0].date()), source=src[leg], bh=E.metrics(bh[0][j0:], c[j0:]), rules={})
        ser[leg] = dict(cal=cal[j0:], bh=bh[0][j0:], rules={})
        idx = E.block_index(n, 21, DRAWS, SEED)
        for name, st in rules.items():
            st = np.array(st, dtype=float); st[:j0 - 1] = 1.0
            Wd = np.column_stack([st, 1 - st]); W = A.lagged(Wd, 1)
            o = sim(W); tgt = o[4] / n; cw = tgt.copy()
            for _ in range(6):
                oc = sim(np.repeat(cw[None, :], T, 0)); cw = np.clip(cw + (tgt - oc[4] / n), 0, None); cw /= cw.sum()
            oc = sim(np.repeat(cw[None, :], T, 0))
            ma = E.metrics(o[0][j0:], c[j0:], o[1][j0:], o[2][j0:], o[3][j0:]); mc = E.metrics(oc[0][j0:], c[j0:])
            dS, dM, dD, dU = E.boot_pairs(np.ascontiguousarray((o[0][j0:] - c[j0:])[:, None]), np.ascontiguousarray((oc[0][j0:] - c[j0:])[:, None]), idx)
            offs = np.arange(63, n - 63, dtype=np.int64)
            pl = E.placebo_shift(R2, np.ascontiguousarray(W[j0:]), np.array([1.0, 0.0]), cost, me, C.BAND, C.CAL_DAYS, 1e-9, True,
                                 np.zeros(2, bool), 0.0, j0, T, offs, c)
            sub = {}
            for nm, a, b in (("1996-2006", "1996-01-01", "2006-12-31"), ("2007-2016", "2007-01-01", "2016-12-31"), ("2017-2026", "2017-01-01", "2026-12-31")):
                i = max(int(cal.searchsorted(pd.Timestamp(a))), j0); j = int(cal.searchsorted(pd.Timestamp(b), side="right"))
                if j - i > 252:
                    sub[nm] = dict(d_sharpe=E.sharpe(o[0][i:j] - c[i:j]) - E.sharpe(oc[0][i:j] - c[i:j]), d_maxdd=E.maxdd(o[0][i:j]) - E.maxdd(oc[0][i:j]))
            out[leg]["rules"][name] = dict(arm=ma, ctrl=mc, d=delta(ma, mc), avg_exposure=float(tgt[0]),
                                           ci=[float(np.percentile(dS, 2.5)), float(np.percentile(dS, 97.5))],
                                           ci_dd=[float(np.percentile(dD, 2.5)), float(np.percentile(dD, 97.5))],
                                           placebo_pct_sharpe=float((pl[:, 0] < ma["sharpe"]).mean() * 100),
                                           placebo_pct_maxdd=float((pl[:, 1] < ma["maxdd"]).mean() * 100), sub=sub)
            ser[leg]["rules"][name] = dict(arm=o[0][j0:], ctrl=oc[0][j0:])

        # ---- signal isolation: forward BIL-excess returns entered at the close of t+1, conditional on the state at t
        dd = P / P.rolling(252, min_periods=1).max() - 1
        states = {"below SMA200": P < s200, "above SMA200": P > s200, "RSI14 > 70": rs > 70, "RSI14 < 30": rs < 30,
                  "drawdown > 10%": dd < -.10, "252d return < bills": (P / P.shift(252) < cn / cn.shift(252)),
                  "VIX > VIX3M": (vix > v3).where(v3.notna())}
        vr, vc = None, None
        for k, s in enumerate(C.VOLSRC[leg]):
            v = p["vol"][s].reindex(full).astype(float); rr = p["ret"][s].reindex(full)
            z = (v - v.rolling(60, min_periods=60).mean().shift(1)) / v.rolling(60, min_periods=60).std().shift(1)
            cl = ((rr < 0) & (z > 3)).where(z.notna()).reindex(cal)
            st0 = full[min(full.searchsorted(v.dropna().index[0]) + 60, len(full) - 1)] if k > 0 else full[0]
            vc = cl if vc is None else vc.where(cal < st0, cl)
        states["volume climax (down day, z>3)"] = vc
        ex_lp = np.log(P.values) - np.log(cn.values)
        iso[leg] = {}
        rng = np.random.default_rng(SEED)
        for h in (5, 21, 63):
            fwd = np.full(T, np.nan); fwd[:T - h - 1] = np.exp(ex_lp[h + 1:] - ex_lp[1:T - h]) - 1
            for name, s in states.items():
                sv = pd.Series(s, index=cal).astype(float)
                valid = sv.notna().values & ~np.isnan(fwd); valid[:j0] = False
                f = fwd[valid]; g = sv.values[valid] > 0
                if g.sum() < 30:
                    continue
                d = f[g].mean() - f[~g].mean()
                nn = len(f); nb = int(np.ceil(nn / 63)); ds = np.empty(1000)
                for q in range(1000):
                    ii = ((rng.integers(0, nn, nb)[:, None] + np.arange(63)[None, :]) % nn).ravel()[:nn]
                    ff = f[ii]; gg = g[ii]
                    ds[q] = ff[gg].mean() - ff[~gg].mean() if gg.any() and (~gg).any() else np.nan
                spells = int((np.diff(np.concatenate([[0], g.astype(int)])) == 1).sum())
                iso[leg].setdefault(name, {})[str(h)] = dict(n_days=int(g.sum()), spells=spells, share=float(g.mean()),
                                                           mean_in=float(f[g].mean()), mean_out=float(f[~g].mean()), diff=float(d),
                                                           ci=[float(np.nanpercentile(ds, 2.5)), float(np.nanpercentile(ds, 97.5))],
                                                           hit_in=float((f[g] > 0).mean()), hit_out=float((f[~g] > 0).mean()))
        log("leg tier", leg, "done")
    return out, iso, ser


def _rnd(o):
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {k: _rnd(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_rnd(v) for v in o]
    return o


def main():
    p = C.load_panel()
    res = dict(meta=dict(end=str(p["end"].date()), seed=SEED, draws=DRAWS, base=dict(zip(C.COLS, C.BASE.tolist())),
                         cost_bps=dict(zip(C.COLS, (C.COST * 1e4).tolist())), primary=A.PRIMARY, data=p["meta"]))
    series = {}
    for v in ("T1", "T2"):
        res[v], series[v] = run_tape(p, v)
    res["leg_tier"], res["isolation"], series["leg"] = leg_tier(p)
    json.dump(_rnd(json.loads(json.dumps(res, default=float))), open(os.path.join(C.STUDY, "results.json"), "w"), separators=(",", ":"))
    pickle.dump(series, open(os.path.join(C.CACHE, "series.pkl"), "wb"))
    log("saved")


if __name__ == "__main__":
    main()
