#!/usr/bin/env python3
"""AMENDMENT A12 — GDE-anchored exit-engine family (rules 6 / 6b / 7 / 8).

Frozen in SPEC.md (owner, 2026-08-12, before computation). Default position
IS GDE-synth; exits are regime/vol-triggered. Success criterion (owner):
GDE's drawdown materially reduced while CAGR stays above B&H SPY.

RULES (parameters frozen; no tuning, no extra variants):
 6.  vol_exit      : hold GDE; exit to cash (BOXX) when trailing 63d realized
                     vol of the GDE synthetic > its expanding 85th percentile;
                     re-enter when vol < expanding 70th percentile.
 6b. vol_exit_spy  : same triggers as 6; exit DESTINATION is SPY when SPY's
                     own 10m trend is positive at that month-end, else cash.
 7.  corr_exit     : hold GDE; exit to cash when trailing 63d gold-equity
                     correlation > its expanding 90th percentile AND GDE 3m
                     return < 0 (Oct-2008 phenotype); re-enter when either
                     condition clears.
 8.  dual_exit     : exit on (6) OR (7); re-enter when BOTH clear
                     (vol < 70th pct AND corr-spike condition absent).

TIMING (repo standing convention, same as rules.py — verified in-code by the
QA gates below): state decided at month-end t from data knowable at t,
executed next month's open, earns the month t+1 panel return. 5bp x one-way
turnover charged in the traded month; BOXX = bills - 5bp/yr. Walk-forward
only: every percentile is EXPANDING (past-only-plus-current), burn-in
MEDIAN_MIN_OBS = 24 monthly observations (the repo's a-priori expanding-
estimator convention from signals.py).

IMPLEMENTATION CHOICES fixed a-priori BEFORE results were computed (logged
as amendments A13-A16 in EXIT_RULES.md):
 A13 vol63/corr63 are computed from the DAILY fixtures (63 TRADING days,
     ddof=1, x sqrt(252); pairwise 63d Pearson corr of daily gold-futures-
     excess-proxy returns vs daily equity returns), sampled at the last
     trading day <= month-end t. Expanding percentiles are taken over the
     MONTH-END history of the statistic (decisions are monthly), including
     month t. Daily gold exists only from 1976-02-26 (PROVENANCE.md): NO
     monthly approximation is substituted before that (a "63d" vol from 3
     monthly points is not an estimator, it is noise) — the A12 family
     simply starts later; dates flagged. Pre-1993 daily equity = ^GSPC +
     smeared Shiller dividends (standing flag, as in rule 5's sigma60).
 A14 6b's destination is re-evaluated EVERY month while in the exit state
     (SPY-trend = SPY TR index >= its 10m SMA of month-end levels, the
     signals.py convention); destination changes incur normal switch costs.
 A15 Rule 7 "GDE 3m return" = trailing 3-month compounded return of monthly
     GDE-synth including month t (the tsmom_3 convention); "negative" = <0.
     Because exit requires (corr AND ret3) and re-entry requires either to
     clear, rule 7 is memoryless: cash iff both conditions hold at t.
 A16 Boundary conventions: exit on strict >, re-enter on strict < (vol);
     corr trigger strict >. Initial state = GDE (default position IS GDE)
     at the first month all four rules' inputs are defined.

Free parameters per rule: 6/6b = 2 (P=85, Q=70); 7 = 2 (90th pct, 3m);
8 = union, still <=3 per the brief's cap read per-rule. Zero estimated
quantities beyond the expanding percentiles themselves (walk-forward).
Multiple-testing family grows by 4 (SPEC A12): 14 signals + 4 Phase-3 rules
+ 4 exit variants; Phase 4 recomputes adjusted bars on that count.
"""
import json
import math
import os

import numpy as np
import pandas as pd

import datalib as dl
from signals import BOXX_DRAG, SWITCH_COST, MEDIAN_MIN_OBS, load_panel, _cum
from rules import (OOS_START, REGIMES, W_MAP, build_daily_assets, backtest,
                   nw_tstat, window_stats)

HERE = os.path.dirname(os.path.abspath(__file__))

P_EXIT, Q_REENTER, CORR_P = 0.85, 0.70, 0.90     # FROZEN (SPEC A12)
VOL_WINDOW_D = 63                                # FROZEN (SPEC A12)
RULE_NAMES = ["vol_exit", "vol_exit_spy", "corr_exit", "dual_exit"]
PRETTY = {"vol_exit": "6 vol_exit", "vol_exit_spy": "6b vol_exit_spy",
          "corr_exit": "7 corr_exit", "dual_exit": "8 dual_exit"}


# ------------------------------------------------------------ daily inputs --
def build_daily_components():
    """Daily returns: gde-synth / equity / boxx from rules.build_daily_assets
    (identical series rule 5 used for sigma60) + the gold leg (GCUSD aligned
    to the equity calendar, spot-like returns) for the gold-equity corr."""
    da = build_daily_assets()                      # gde, spy(=equity), boxx
    d = dl.load_daily()
    gold = dl.align_returns_to(d["gspc"].loc["1976-02-25":], d["gc"]).reindex(da.index)
    out = da.copy()
    out["gold"] = gold
    return out.dropna()


def month_end_stats(daily):
    """vol63 (ann.) of daily GDE-synth and 63d gold-equity corr, sampled at
    the last trading day of each month. Causal: rolling windows end at t."""
    per = daily.index.to_period("M")
    vol_d = daily["gde"].rolling(VOL_WINDOW_D).std(ddof=1) * math.sqrt(252.0)
    corr_d = daily["gold"].rolling(VOL_WINDOW_D).corr(daily["spy"])
    return vol_d.groupby(per).last(), corr_d.groupby(per).last()


# ----------------------------------------------------------------- states --
def exit_states(panel, daily):
    """State labels per DECISION month t for the four A12 rules. Purely
    causal: expanding percentiles include data through month t only."""
    vol_me, corr_me = month_end_stats(daily)
    q_hi = vol_me.expanding(MEDIAN_MIN_OBS).quantile(P_EXIT)
    q_lo = vol_me.expanding(MEDIAN_MIN_OBS).quantile(Q_REENTER)
    q_corr = corr_me.expanding(MEDIAN_MIN_OBS).quantile(CORR_P)

    gde, spy = panel["gde_synth"], panel["spx_tr"]
    ret3 = _cum(gde) / _cum(gde).shift(3) - 1.0            # incl. month t (A15)
    idx_spy = _cum(spy)
    spy_trend = idx_spy >= idx_spy.rolling(10).mean()      # signals.py conv.

    inputs = pd.DataFrame({
        "vol": vol_me, "q_hi": q_hi, "q_lo": q_lo,
        "corr": corr_me, "q_corr": q_corr,
        "ret3": ret3, "spy_trend_ok": idx_spy.rolling(10).mean(),
    }).reindex(panel.index)
    live = inputs.dropna().index
    if len(live) == 0:
        return pd.DataFrame(columns=RULE_NAMES), inputs
    start = live[0]

    in6, in8 = True, True                                  # A16: start in GDE
    rows = {}
    for t in panel.index[panel.index >= start]:
        if t not in live:
            continue
        v, hi, lo = inputs.at[t, "vol"], inputs.at[t, "q_hi"], inputs.at[t, "q_lo"]
        spike = (inputs.at[t, "corr"] > inputs.at[t, "q_corr"]) and \
                (inputs.at[t, "ret3"] < 0.0)
        # rule 6 hysteresis
        if in6 and v > hi:
            in6 = False
        elif (not in6) and v < lo:
            in6 = True
        # rule 8: exit on 6-trigger OR 7-trigger; re-enter when both clear
        if in8 and (v > hi or spike):
            in8 = False
        elif (not in8) and (v < lo and not spike):
            in8 = True
        dest6b = "spy" if bool(spy_trend.at[t]) else "boxx"   # A14
        rows[t] = {"vol_exit": "gde" if in6 else "boxx",
                   "vol_exit_spy": "gde" if in6 else dest6b,
                   "corr_exit": "boxx" if spike else "gde",   # A15 memoryless
                   "dual_exit": "gde" if in8 else "boxx"}
    states = pd.DataFrame.from_dict(rows, orient="index")
    states.index = pd.PeriodIndex(states.index, freq="M")
    return states[RULE_NAMES], inputs


def compute_exit_weights(panel, daily):
    """Single pipeline entry point (panel+daily -> weight frames per rule) so
    the QA gates exercise the REAL code path."""
    states, inputs = exit_states(panel, daily)
    W = {r: pd.DataFrame([W_MAP[s] for s in states[r]], index=states.index)
         for r in states.columns}
    return W, states, inputs


# --------------------------------------------------------------- QA gates --
def qa_checks(panel, daily, W_full, cuts=("1990-12", "2005-06", "2019-12")):
    """(a) truncation invariance: inputs cut at month-end T -> identical
    decisions <= T. (b) future-perturbation: violent shocks to post-T panel
    and daily inputs -> decisions <= T unchanged. Hard-exit on failure."""
    rng = np.random.default_rng(12)
    out = {}
    for cut in cuts:
        T = pd.Period(cut, "M")
        p_tr = panel[panel.index <= T]
        d_tr = daily[daily.index.to_period("M") <= T]
        Wt, _, _ = compute_exit_weights(p_tr, d_tr)
        trunc_ok = all(
            len(Wt[k].loc[:T]) == len(W_full[k].loc[:T]) and
            np.allclose(Wt[k].loc[:T].values, W_full[k].loc[:T].values,
                        atol=1e-12)
            for k in W_full)
        p_pe = panel.copy()
        fut = p_pe.index > T
        p_pe.loc[fut] = p_pe.loc[fut] * (1 + rng.normal(0, 0.5, (fut.sum(), p_pe.shape[1])))
        d_pe = daily.copy()
        futd = d_pe.index.to_period("M") > T
        d_pe.loc[futd] = d_pe.loc[futd] * 3.0 + 0.01
        Wp, _, _ = compute_exit_weights(p_pe, d_pe)
        pert_ok = all(
            np.allclose(Wp[k].loc[:T].values, W_full[k].loc[:T].values,
                        atol=1e-12) for k in W_full)
        out[cut] = {"truncation_invariance": bool(trunc_ok),
                    "future_perturbation_invariance": bool(pert_ok)}
        print(f"QA cut {cut}: truncation {'PASS' if trunc_ok else 'FAIL'}, "
              f"perturbation {'PASS' if pert_ok else 'FAIL'}")
    return out


# ------------------------------------------------------------------- main --
def main():
    panel = load_panel()
    daily = build_daily_components()
    assets = pd.DataFrame({"gde": panel["gde_synth"], "spy": panel["spx_tr"],
                           "boxx": panel["bills"] - BOXX_DRAG / 12.0})
    rf = panel["bills"]

    W, states, inputs = compute_exit_weights(panel, daily)
    first_dec = states.index[0]
    full_start = first_dec + 1                 # first HELD month
    print(f"daily coverage: {daily.index[0].date()} -> {daily.index[-1].date()}"
          f" (gold daily absent before 1976-02-26 — no monthly substitute, A13)")
    print(f"first live decision month: {first_dec} (63d stats from 1976-05, "
          f"+{MEDIAN_MIN_OBS}m expanding-percentile burn-in); "
          f"A12 FULL window: {full_start} -> 2026-07 "
          f"(vs 1977-02 for rules 1-5 — flagged)")

    qa = qa_checks(panel, daily, W)
    if not all(v["truncation_invariance"] and v["future_perturbation_invariance"]
               for v in qa.values()):
        raise SystemExit("QA FAILED — timing bug in pipeline, DO NOT trust results")

    # benchmarks over the SAME windows: B&H GDE, B&H SPY (from the panel);
    # static_5050 (null) and relmom_cash (Phase-3 champion) from the frozen
    # rules_results.json series.
    r3 = json.load(open(os.path.join(HERE, "rules_results.json")))
    bench_rets = {
        "bh_gde": panel["gde_synth"],
        "bh_spy": panel["spx_tr"],
        "static_5050": pd.Series({pd.Period(k, "M"): v for k, v in
                                  r3["monthly_returns"]["static_5050"].items()}),
        "relmom_cash": pd.Series({pd.Period(k, "M"): v for k, v in
                                  r3["monthly_returns"]["relmom_cash"].items()}),
    }
    bench = {}
    for name, r in bench_rets.items():
        bench[name] = {
            "full_a12": window_stats(r, rf, str(full_start), "2026-07"),
            "oos": window_stats(r, rf, str(OOS_START), "2026-07"),
            "regimes": {lab: window_stats(r, rf, a, b) for lab, a, b in REGIMES}}

    results, rets = {}, {}
    for name in RULE_NAMES:
        r, to = backtest(W[name], assets, start=full_start)
        rets[name] = r
        st_full = window_stats(r, rf, str(full_start), "2026-07")
        st_oos = window_stats(r, rf, str(OOS_START), "2026-07")
        regs = {lab: window_stats(r, rf, a, b) for lab, a, b in REGIMES}
        s = states[name]
        sw = (s != s.shift(1)) & s.shift(1).notna()
        dec_to, dec_sw = {}, {}
        for y0 in range(1980, 2030, 10):
            y1 = min(y0 + 9, 2026)
            mask = (to.index >= pd.Period(f"{y0}-01", "M")) & \
                   (to.index <= pd.Period(f"{y1}-12", "M"))
            yrs = mask.sum() / 12.0
            if yrs < 1:
                continue
            dec_to[f"{y0}s"] = float(to[mask].sum() / yrs)
            mk = (sw.index >= pd.Period(f"{y0}-01", "M")) & \
                 (sw.index <= pd.Period(f"{y1}-12", "M"))
            dec_sw[f"{y0}s"] = int(sw[mk].sum())
        tig_full = float((s == "gde").mean())
        s_oos = s[s.index >= OOS_START - 1]
        tig_oos = float((s_oos == "gde").mean())
        gross = (1.8 * W[name]["gde"] + 1.0 * W[name]["spy"])
        results[name] = {
            "full_a12": st_full, "oos": st_oos, "regimes": regs,
            "turnover_per_yr_by_decade": dec_to, "switches_by_decade": dec_sw,
            "time_in_gde": {"full_a12": tig_full, "oos": tig_oos},
            "avg_gross_risk_notional": float(gross.mean()),
            "n_exit_episodes": int(((s != "gde") & (s.shift(1) == "gde")).sum()),
        }
        # comparisons: vs B&H GDE (owner's DD criterion), vs B&H SPY (A5/Q2),
        # vs null and vs relmom_cash (head-to-head, NW-t on mean monthly diff)
        c = results[name]
        for tag, bname in (("vs_bh_gde", "bh_gde"), ("vs_spy", "bh_spy"),
                           ("vs_null", "static_5050"),
                           ("vs_relmom_cash", "relmom_cash")):
            c[tag] = {}
            for win in ("full_a12", "oos"):
                b = bench[bname][win]
                sX = c[win]
                d = (r - bench_rets[bname].reindex(r.index)).dropna()
                if win == "oos":
                    d = d[d.index >= OOS_START]
                c[tag][win] = {
                    "dCAGR": sX["CAGR"] - b["CAGR"],
                    "dMaxDD": sX["MaxDD_m"] - b["MaxDD_m"],
                    "dCalmar": sX["Calmar"] - b["Calmar"],
                    "dSortino": sX["Sortino"] - b["Sortino"],
                    "dSharpe": sX["Sharpe"] - b["Sharpe"],
                    "dUlcer": sX["Ulcer"] - b["Ulcer"],
                    "nw_t_meandiff": float(nw_tstat(d)),
                }
        c["vs_spy"]["oos"]["dominates_raw"] = bool(
                c["oos"]["CAGR"] >= bench["bh_spy"]["oos"]["CAGR"]
                and c["oos"]["MaxDD_m"] > bench["bh_spy"]["oos"]["MaxDD_m"]
                and c["oos"]["Calmar"] > bench["bh_spy"]["oos"]["Calmar"]
                and c["oos"]["Sortino"] > bench["bh_spy"]["oos"]["Sortino"])

    # ---- print tables ----
    for win in ("full_a12", "oos"):
        w0 = full_start if win == "full_a12" else OOS_START
        print(f"\n==== {win.upper()} window ({w0} -> 2026-07) ====")
        hdr = (f"{'rule':16s} {'CAGR':>7s} {'Vol':>6s} {'Sharpe':>6s}"
               f" {'Sortino':>7s} {'MaxDD':>7s} {'UW':>4s} {'Calmar':>6s}"
               f" {'Ulcer':>6s} {'Worst12':>8s} {'%GDE':>5s}")
        print(hdr)
        for bname in ("bh_gde", "bh_spy", "static_5050", "relmom_cash"):
            b = bench[bname][win]
            print(f"{bname:16s} {b['CAGR']:7.2%} {b['Vol']:6.2%} {b['Sharpe']:6.2f}"
                  f" {b['Sortino']:7.2f} {b['MaxDD_m']:7.1%}"
                  f" {b['UnderwaterMax_m']:4d} {b['Calmar']:6.2f} {b['Ulcer']:6.1f}"
                  f" {b['Worst12m']:8.1%}  (benchmark)")
        for name in RULE_NAMES:
            sX = results[name][win]
            tig = results[name]["time_in_gde"][win]
            print(f"{PRETTY[name]:16s} {sX['CAGR']:7.2%} {sX['Vol']:6.2%}"
                  f" {sX['Sharpe']:6.2f} {sX['Sortino']:7.2f} {sX['MaxDD_m']:7.1%}"
                  f" {sX['UnderwaterMax_m']:4d} {sX['Calmar']:6.2f}"
                  f" {sX['Ulcer']:6.1f} {sX['Worst12m']:8.1%} {tig:5.0%}")
            if sX["Sharpe"] > 1.2:
                print("  ^^ TRIPWIRE Sharpe>1.2 — STOP AND AUDIT before reporting")

    print("\n==== owner criterion (OOS): GDE DD cut, CAGR still > B&H SPY? ====")
    for name in RULE_NAMES:
        c = results[name]
        g, s5 = c["vs_bh_gde"]["oos"], c["vs_spy"]["oos"]
        print(f"{PRETTY[name]:16s} dMaxDD vs GDE {g['dMaxDD']:+7.1%}"
              f"  dCAGR vs GDE {g['dCAGR']:+6.2%}"
              f" | vs SPY: dCAGR {s5['dCAGR']:+6.2%} dMaxDD {s5['dMaxDD']:+7.1%}"
              f" dominates_raw={s5['dominates_raw']}"
              f" | gross {c['avg_gross_risk_notional']:.2f}x")

    print("\n==== head-to-head vs relmom_cash (OOS) ====")
    for name in RULE_NAMES:
        v = results[name]["vs_relmom_cash"]["oos"]
        print(f"{PRETTY[name]:16s} dCAGR {v['dCAGR']:+6.2%} dMaxDD {v['dMaxDD']:+7.1%}"
              f" dCalmar {v['dCalmar']:+5.2f} dUlcer {v['dUlcer']:+5.1f}"
              f" NW-t {v['nw_t_meandiff']:+5.2f}")

    print("\n==== per-regime CAGR / MaxDD / Calmar ====")
    for name in list(bench) + RULE_NAMES:
        c = bench.get(name) or results[name]
        row = "  ".join(f"{lab}: {v['CAGR']:6.1%} {v['MaxDD_m']:6.1%} {v['Calmar']:5.2f}"
                        for lab, v in c["regimes"].items() if v)
        print(f"{PRETTY.get(name, name):16s} {row}")

    print("\nturnover (one-way/yr) + state switches by decade:")
    for name in RULE_NAMES:
        c = results[name]
        print(f"{PRETTY[name]:16s} to/yr { {k: round(v, 2) for k, v in c['turnover_per_yr_by_decade'].items()} }"
              f" | switches {c['switches_by_decade']}"
              f" | exit episodes {c['n_exit_episodes']}")

    out = {
        "amendment": "A12 (SPEC.md, frozen before computation); implementation "
                     "amendments A13-A16 in EXIT_RULES.md",
        "conventions": "state decided month-end t (63d daily windows ending at "
                       "last trading day <= t; expanding percentiles over "
                       "month-end history incl. t, min 24 obs), earns month "
                       "t+1; 5bp x one-way turnover; BOXX = bills - 5bp/yr; "
                       "walk-forward only; params frozen (P=85, Q=70, corr "
                       "P=90, 63d, 3m)",
        "windows": {"full_a12": f"{full_start}->2026-07 (later than rules 1-5 "
                                f"full window 1977-02, see flags)",
                    "oos": f"{OOS_START}->2026-07"},
        "flags": [
            "daily gold absent before 1976-02-26: A12 family starts "
            f"{full_start} (no monthly-derived 63d substitute was used; A13)",
            "pre-1993 daily equity leg = ^GSPC + smeared Shiller dividends "
            "(affects vol63/corr63 estimation only; standing flag)",
            "GDE-synth is a MODEL (±1%/yr carry band pre-2007); month-end "
            "curves intramonth-blind (~4pp deeper daily, BASELINES.md)",
            "OOS stats windows match Phase 3 (1990-02->2026-07) for "
            "head-to-head comparability",
        ],
        "qa_checks": qa,
        "n_variants_tested": {"signals_phase2": 14, "rules_phase3": 5,
                              "exit_rules_a12": 4,
                              "note": "multiple-testing family grows by 4 "
                                      "(SPEC A12); no unreported variants"},
        "benchmarks": bench,
        "rules": results,
        "monthly_returns": {n: {str(k): float(v) for k, v in r.items()}
                            for n, r in rets.items()},
        "states": {c: {str(k): v for k, v in states[c].items()}
                   for c in states.columns},
        "inputs_month_end": {c: {str(k): (None if pd.isna(v) else float(v))
                                 for k, v in inputs[c].items()}
                             for c in ["vol", "q_hi", "q_lo", "corr", "q_corr",
                                       "ret3"]},
    }
    with open(os.path.join(HERE, "rules_exit_results.json"), "w") as fh:
        json.dump(out, fh, default=float, indent=1)
    print("\nwrote rules_exit_results.json")


if __name__ == "__main__":
    main()
