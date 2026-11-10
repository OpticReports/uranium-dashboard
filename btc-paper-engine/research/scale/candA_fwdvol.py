"""CANDIDATE A - the failure-mode test the brief demands: does vol-targeting
concentrate size exactly when volatility is ABOUT TO rise?

Vol-targeting sizes off TRAILING ATR14. It is only risk-neutral if trailing
vol predicts the vol that is actually realised over the hold. Three tests:

  T1  VOL MEAN-REVERSION. Bucket every bar by trailing-ATR percentile and
      measure forward realised vol over the hold horizon / trailing vol.
      If calm bars systematically expand, VT upsizes into understated risk.
  T2  REALISED RISK EQUALISATION. VT's whole claim is that dollar risk is
      CONSTANT. Test the realised loss distribution, not the intended one.
  T3  GAP RISK. The sim fills STOP exits AT the stop. VT carries more
      notional in calm regimes, so a gap through the stop costs more. Measure
      real gap-through on the fixture and re-price both arms with gap fills.

STRUCTURAL FACT used throughout (verified in V0 below): notional_frac =
min(risk/s, cap) for VT and = leverage for FIXED -- BOTH are equity-path
independent, so per-trade equity return ret_eq = notional_frac * (price_ret
- fee) is a deterministic function of the bars alone. Counterfactual
re-pricing by recompounding ret_eq is therefore EXACT, not an approximation
(up to core.py's qty = round(.,6)).

Output: candA_fwdvol.json
"""
import csv
import json
import math
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from app.engine.core import Bar, BookCfg, TradeCfg          # noqa: E402
from app.engine.replay import run_replay                    # noqa: E402
from app.indicators import atr as atr_pure                  # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
BAR_S = 4 * 3600
SIZING_STOP = {"pullback": 2.5, "trend": 5.0}
W_TREND, BLEND_LEV = 0.25, 1.5


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def leg_cfg(leg, sizing, risk=0.0, cap=1.0):
    if leg == "pullback":
        return BookCfg(name="P", sizing=sizing, strategy="pullback",
                       leverage=1.0, risk=risk, cap=cap, dd_halt=0.30)
    return BookCfg(name="T", sizing=sizing, strategy="donchian", trail_atr=5.0,
                   leverage=1.0, risk=risk, cap=cap, dd_halt=0.50)


def run_leg(bars, leg, sizing, risk=0.0, cap=1.0):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZING_STOP[leg])
    res = run_replay(bars, [leg_cfg(leg, sizing, risk, cap)],
                     RESEARCH_SIGNAL, tc, cash_apy=0.0)
    return res.books["P" if leg == "pullback" else "T"], tc


def pct(a, q):
    return float(np.percentile(np.asarray(a, float), q))


def dist(a):
    a = np.asarray(a, float)
    if len(a) == 0:
        return {}
    return dict(n=int(len(a)), mean=float(a.mean()), median=pct(a, 50),
                p5=pct(a, 5), p10=pct(a, 10), p25=pct(a, 25), p75=pct(a, 75),
                p90=pct(a, 90), p95=pct(a, 95), p99=pct(a, 99),
                min=float(a.min()), max=float(a.max()), sd=float(a.std()))


def main():
    bars = load_bars()
    n = len(bars)
    ts = np.array([b.ts for b in bars])
    o = np.array([b.open for b in bars]); h = np.array([b.high for b in bars])
    lo = np.array([b.low for b in bars]); c = np.array([b.close for b in bars])
    a14 = np.array([x if x is not None else np.nan for x in
                    atr_pure(list(h), list(lo), list(c), 14)], float)
    ix = {int(t): i for i, t in enumerate(ts)}
    out = {"meta": dict(bars=n, fee_rt_bps=2 * RESEARCH_TRADE.taker_fee_bps)}

    # ================= T1: vol mean-reversion ==========================
    # Realised vol over a forward window of H bars, in the SAME units as the
    # sizer's input: mean true-range / price. That makes the ratio
    # forward/trailing directly interpretable as "how wrong was the sizer".
    tr = np.full(n, np.nan)
    for i in range(1, n):
        pc = c[i - 1]
        tr[i] = max(h[i] - lo[i], abs(h[i] - pc), abs(lo[i] - pc))
    trn = tr / c                       # normalised true range per bar
    a14n = a14 / c                     # the sizer's own s-input (per 1.0 mult)
    t1 = {}
    for H in (10, 20, 41, 60):         # 41 = mean hold of the pullback leg
        fwd = np.full(n, np.nan)
        for i in range(210, n - H):
            fwd[i] = np.nanmean(trn[i + 1:i + 1 + H])
        m = np.isfinite(fwd) & np.isfinite(a14n)
        ratio = fwd[m] / a14n[m]
        trail = a14n[m]
        q = np.quantile(trail, np.linspace(0, 1, 6))
        buckets = []
        for j in range(5):
            sel = (trail >= q[j]) & (trail <= q[j + 1] if j == 4 else trail < q[j + 1])
            buckets.append(dict(
                quintile=j + 1, trail_lo=float(q[j]), trail_hi=float(q[j + 1]),
                n=int(sel.sum()),
                ratio_median=float(np.median(ratio[sel])),
                ratio_mean=float(ratio[sel].mean()),
                ratio_p90=float(np.percentile(ratio[sel], 90)),
                pct_expanded=float((ratio[sel] > 1).mean())))
        t1[f"H{H}"] = dict(
            overall=dist(ratio), buckets=buckets,
            spearman=float(np.corrcoef(
                np.argsort(np.argsort(trail)), np.argsort(np.argsort(ratio)))[0, 1]),
            q1_over_q5=float(np.median(ratio[(trail >= q[0]) & (trail < q[1])])
                             / np.median(ratio[(trail >= q[4])])))
    out["T1_vol_mean_reversion"] = t1
    for H, v in t1.items():
        print(f"T1 {H}: fwd/trail median={v['overall']['median']:.3f} "
              f"Q1(calm)={v['buckets'][0]['ratio_median']:.3f} "
              f"Q5(wild)={v['buckets'][4]['ratio_median']:.3f} "
              f"Q1/Q5={v['q1_over_q5']:.3f} rho={v['spearman']:+.3f}")

    # ================= build both arms ==================================
    base, risk_match = {}, {}
    for leg in ("pullback", "trend"):
        bk, tc = run_leg(bars, leg, "fixed", cap=1.0)
        rows = []
        for t in bk.trades:
            s = tc.stop_atr * t.atr_at_entry / t.entry_price
            rows.append(dict(t=t, s=s, nf=t.notional / t.equity_before,
                             rf=t.notional / t.equity_before * s))
        base[leg] = dict(bk=bk, tc=tc, rows=rows)
        risk_match[leg] = float(np.mean([r["rf"] for r in rows]))
    print("risk-match:", {k: f"{v:.4%}" for k, v in risk_match.items()})

    # ---- V0: verify ret_eq is equity-path independent -----------------
    v0 = {}
    for leg in ("pullback", "trend"):
        for cap, tag in ((1.0, "fixed"), (2.0, "vt2"), (99.0, "vtinf")):
            if tag == "fixed":
                bk, tc = base[leg]["bk"], base[leg]["tc"]
            else:
                bk, tc = run_leg(bars, leg, "vol_target", risk_match[leg], cap)
            recomp, eq = 1.0, bk.cfg.start_equity
            for t in bk.trades:
                recomp *= 1 + t.pnl_usd / t.equity_before
            v0[f"{leg}_{tag}"] = dict(
                engine_equity=float(bk.equity),
                recompounded=float(bk.cfg.start_equity * recomp),
                rel_err=float(abs(bk.cfg.start_equity * recomp - bk.equity)
                              / bk.equity))
    out["V0_recompound_exact"] = v0
    print("V0 max rel err:", max(v["rel_err"] for v in v0.values()))

    arms = {}
    for tag, cap, sizing in (("FIXED", 1.0, "fixed"), ("VT_cap2.0", 2.0, "vol_target"),
                             ("VT_uncapped", 99.0, "vol_target")):
        arms[tag] = {}
        for leg in ("pullback", "trend"):
            bk, tc = run_leg(bars, leg, sizing, risk_match[leg], cap)
            rr = []
            for t in bk.trades:
                s = tc.stop_atr * t.atr_at_entry / t.entry_price
                i = ix[t.exit_ts]
                nf = t.notional / t.equity_before
                # realised price return on notional, sign-aware, gross of fee
                sgn = 1.0 if t.side == "L" else -1.0
                gross = sgn * (t.exit_price / t.entry_price - 1)
                fee = t.fees_usd / t.notional
                # GAP: did the exit bar OPEN beyond the stop?
                gapped, gap_fill = False, t.exit_price
                if t.exit_reason == "STOP":
                    if t.side == "L" and o[i] < t.stop_price:
                        gapped, gap_fill = True, o[i]
                    elif t.side == "S" and o[i] > t.stop_price:
                        gapped, gap_fill = True, o[i]
                    # adverse excursion beyond the stop within the exit bar
                    exc = ((t.stop_price - lo[i]) / t.stop_price if t.side == "L"
                           else (h[i] - t.stop_price) / t.stop_price)
                else:
                    exc = 0.0
                gross_gap = sgn * (gap_fill / t.entry_price - 1)
                # forward realised vol actually experienced over the hold
                j0, j1 = ix[t.entry_ts], i
                fwd_tr = float(np.nanmean(trn[j0:j1 + 1])) if j1 > j0 else float(trn[j1])
                rr.append(dict(
                    entry_ts=t.entry_ts, exit_ts=t.exit_ts, side=t.side,
                    reason=t.exit_reason, s=s, nf=nf, rf=nf * s,
                    ret_eq=nf * (gross - fee), ret_eq_gap=nf * (gross_gap - fee),
                    gross=gross, gapped=bool(gapped), excursion=float(exc),
                    bars_held=t.bars_held, atr_n=t.atr_at_entry / t.entry_price,
                    fwd_tr=fwd_tr,
                    fwd_over_trail=fwd_tr / (t.atr_at_entry / t.entry_price)))
            arms[tag][leg] = dict(bk=bk, rows=rr)

    # ================= T2: realised risk equalisation ==================
    t2 = {}
    for leg in ("pullback", "trend"):
        f = arms["FIXED"][leg]["rows"]
        v = arms["VT_cap2.0"][leg]["rows"]
        vu = arms["VT_uncapped"][leg]["rows"]
        assert len(f) == len(v) == len(vu), (len(f), len(v), len(vu))
        lf = np.array([-r["ret_eq"] for r in f])     # loss as +ve eq fraction
        lv = np.array([-r["ret_eq"] for r in v])
        lvu = np.array([-r["ret_eq"] for r in vu])
        t2[leg] = dict(
            intended_risk_frac=dict(
                FIXED=dist([r["rf"] for r in f]),
                VT_cap2=dist([r["rf"] for r in v]),
                VT_uncapped=dist([r["rf"] for r in vu])),
            realised_loss_frac_losers=dict(
                FIXED=dist(lf[lf > 0]), VT_cap2=dist(lv[lv > 0]),
                VT_uncapped=dist(lvu[lvu > 0])),
            # the number that matters: does VT's LOSS TAIL grow faster than
            # its MEAN loss? (tail/mean ratio -- scale-free)
            tail_over_mean=dict(
                FIXED=float(pct(lf[lf > 0], 95) / lf[lf > 0].mean()),
                VT_cap2=float(pct(lv[lv > 0], 95) / lv[lv > 0].mean()),
                VT_uncapped=float(pct(lvu[lvu > 0], 95) / lvu[lvu > 0].mean())),
            mean_loss_ratio_vt_over_fixed=dict(
                VT_cap2=float(lv[lv > 0].mean() / lf[lf > 0].mean()),
                VT_uncapped=float(lvu[lvu > 0].mean() / lf[lf > 0].mean())),
            p95_loss_ratio_vt_over_fixed=dict(
                VT_cap2=float(pct(lv[lv > 0], 95) / pct(lf[lf > 0], 95)),
                VT_uncapped=float(pct(lvu[lvu > 0], 95) / pct(lf[lf > 0], 95))),
            cv_of_realised_loss=dict(
                FIXED=float(lf[lf > 0].std() / lf[lf > 0].mean()),
                VT_cap2=float(lv[lv > 0].std() / lv[lv > 0].mean()),
                VT_uncapped=float(lvu[lvu > 0].std() / lvu[lvu > 0].mean())))
        # per-trade: does the size multiplier predict a WORSE outcome?
        mult = np.array([vu[i]["nf"] / f[i]["nf"] for i in range(len(f))])
        fo = np.array([r["fwd_over_trail"] for r in f])
        gr = np.array([r["gross"] for r in f])
        t2[leg]["size_mult_vs_outcome"] = dict(
            mult=dist(mult),
            corr_mult_fwd_over_trail=float(np.corrcoef(np.log(mult), np.log(fo))[0, 1]),
            corr_mult_gross_ret=float(np.corrcoef(np.log(mult), gr)[0, 1]),
            # the direct test: bucket by size multiple, report realised
            # per-$ outcome and the vol surprise in each bucket
            buckets=[])
        qs = np.quantile(mult, [0, .2, .4, .6, .8, 1.0])
        for j in range(5):
            sel = (mult >= qs[j]) & (mult <= qs[j + 1] if j == 4 else mult < qs[j + 1])
            t2[leg]["size_mult_vs_outcome"]["buckets"].append(dict(
                quintile=j + 1, n=int(sel.sum()),
                mult_median=float(np.median(mult[sel])),
                fwd_over_trail_median=float(np.median(fo[sel])),
                gross_ret_mean_bps=float(1e4 * gr[sel].mean()),
                win_rate=float((gr[sel] > 0).mean()),
                # realised eq-loss under VT in this bucket vs FIXED
                vt_mean_eqret_bps=float(1e4 * np.array(
                    [vu[i]["ret_eq"] for i in np.where(sel)[0]]).mean()),
                fx_mean_eqret_bps=float(1e4 * np.array(
                    [f[i]["ret_eq"] for i in np.where(sel)[0]]).mean())))
    out["T2_risk_equalisation"] = t2
    for leg, v in t2.items():
        print(f"T2 {leg}: mean-loss ratio VTinf/FIX="
              f"{v['mean_loss_ratio_vt_over_fixed']['VT_uncapped']:.3f} "
              f"p95 ratio={v['p95_loss_ratio_vt_over_fixed']['VT_uncapped']:.3f} "
              f"CV FIX={v['cv_of_realised_loss']['FIXED']:.3f} "
              f"VTinf={v['cv_of_realised_loss']['VT_uncapped']:.3f} "
              f"corr(mult,volsurprise)={v['size_mult_vs_outcome']['corr_mult_fwd_over_trail']:+.3f}")

    # ================= T3: gap risk =====================================
    t3 = {}
    for leg in ("pullback", "trend"):
        f = arms["FIXED"][leg]["rows"]
        stops = [r for r in f if r["reason"] == "STOP"]
        g = [r for r in stops if r["gapped"]]
        t3[leg] = dict(
            n_trades=len(f), n_stops=len(stops), n_gapped=len(g),
            gap_rate=len(g) / len(stops) if stops else None,
            excursion_beyond_stop=dist([r["excursion"] for r in stops]))
        # re-price each arm with gap fills, exact recompound
        for tag in ("FIXED", "VT_cap2.0", "VT_uncapped"):
            rr = arms[tag][leg]["rows"]
            for key, fld in (("clean", "ret_eq"), ("gapfill", "ret_eq_gap")):
                eq, peak, mdd = 1.0, 1.0, 0.0
                for r in rr:
                    eq *= 1 + r[fld]
                    peak = max(peak, eq)
                    mdd = min(mdd, eq / peak - 1)
                t3[leg].setdefault(tag, {})[key] = dict(
                    final=float(eq), maxdd_pct=100 * float(mdd))
            a = t3[leg][tag]
            a["gap_cost_final_pct"] = 100 * (a["gapfill"]["final"] / a["clean"]["final"] - 1)
            a["gap_cost_dd_pp"] = a["gapfill"]["maxdd_pct"] - a["clean"]["maxdd_pct"]
    out["T3_gap_risk"] = t3
    for leg, v in t3.items():
        print(f"T3 {leg}: stops={v['n_stops']} gapped={v['n_gapped']} "
              f"({(v['gap_rate'] or 0):.1%}) | gap cost on final: "
              f"FIX={v['FIXED']['gap_cost_final_pct']:+.2f}% "
              f"VTinf={v['VT_uncapped']['gap_cost_final_pct']:+.2f}% | DD pp: "
              f"FIX={v['FIXED']['gap_cost_dd_pp']:+.2f} "
              f"VTinf={v['VT_uncapped']['gap_cost_dd_pp']:+.2f}")

    # blend-level gap re-pricing (exit-step, 75/25 @1.5)
    def blend_from_rows(pr, tr_, fld):
        evs = sorted([(r["exit_ts"], "P", r) for r in pr]
                     + [(r["exit_ts"], "T", r) for r in tr_])
        eq, peak, mdd = 1.0, 1.0, 0.0
        steps = []
        for _, which, r in evs:
            w = (1 - W_TREND) if which == "P" else W_TREND
            step = BLEND_LEV * w * r[fld]
            eq *= 1 + step
            steps.append(step)
            peak = max(peak, eq)
            mdd = min(mdd, eq / peak - 1)
        return float(eq), 100 * float(mdd), steps
    bl = {}
    for tag in ("FIXED", "VT_cap2.0", "VT_uncapped"):
        pr, tr_ = arms[tag]["pullback"]["rows"], arms[tag]["trend"]["rows"]
        bl[tag] = {}
        for key, fld in (("clean", "ret_eq"), ("gapfill", "ret_eq_gap")):
            fin, mdd, st = blend_from_rows(pr, tr_, fld)
            bl[tag][key] = dict(final=fin, maxdd_pct=mdd, n=len(st))
        bl[tag]["gap_cost_final_pct"] = 100 * (
            bl[tag]["gapfill"]["final"] / bl[tag]["clean"]["final"] - 1)
        bl[tag]["gap_cost_dd_pp"] = (bl[tag]["gapfill"]["maxdd_pct"]
                                     - bl[tag]["clean"]["maxdd_pct"])
    out["T3_blend_gap"] = bl
    for tag, v in bl.items():
        print(f"T3 blend {tag:12s}: clean final={v['clean']['final']:.4f} "
              f"dd={v['clean']['maxdd_pct']:.2f}% | gapfill final="
              f"{v['gapfill']['final']:.4f} dd={v['gapfill']['maxdd_pct']:.2f}% "
              f"({v['gap_cost_final_pct']:+.2f}%, {v['gap_cost_dd_pp']:+.2f}pp)")

    out["risk_match"] = risk_match
    p = os.path.join(HERE, "candA_fwdvol.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
