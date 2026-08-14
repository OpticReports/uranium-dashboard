#!/usr/bin/env python3
"""Phase 3 — the FIVE pre-registered rules from SPEC.md, walk-forward only.

Timing discipline (same as signals.py, pre-registered): weights decided at
month-end t from data knowable at t (CPI/DXY carry an extra availability-lag
month inside the signal construction — "t-1 data earns month t+1"), executed
at the NEXT month's open, earn the month t+1 panel return. Before any result
is trusted, this file runs (a) a truncation-invariance check and (b) a
future-perturbation check on its own pipeline; results are printed and stored.

RULES (frozen; interpretation ambiguities resolved a-priori, logged as
amendments A8/A9 in RULES.md):
 1. static_5050  : 50/50 GDE-synth/SPY, monthly rebalanced (the null).
 2. relmom_cash  : 12-1 relative momentum picks GDE or SPY; absolute filter =
                   winner's own 12-1 return vs bills over the same window;
                   filter fails -> BOXX. (0 estimated params)
 3. realrate_gate: real-10y 12m trend <=0 (down/flat) -> GDE; trend rising and
                   level <= expanding median -> SPY; trend rising AND level
                   high ("both negative for gold") -> BOXX. (1 estimated
                   param: the expanding median, walk-forward, min 24 obs)
 4. composite    : M = rule-2 state, R = real-rate trend signal.
                   M==GDE and R gold-favorable -> GDE; M==BOXX and R
                   unfavorable ("both negative") -> BOXX; else -> 50/50.
 5. voltarget_15 : rule-4 weights scaled by lam = min(1, 15% / sigma60),
                   sigma60 = trailing 60-TRADING-DAY ann. vol of the rule-4
                   target portfolio from the daily fixtures (pre-1993 equity
                   leg = ^GSPC + smeared Shiller dividends — flagged);
                   (1-lam) parked in BOXX. No leverage (lam capped at 1,
                   amendment A11).

Owner amendment A5 (SPEC.md, logged 2026-08-12 before results were seen):
every rule table gains a vs-SPY column set for Q2 ("does any GDE-containing
portfolio dominate B&H SPY: >= SPY CAGR AND better maxDD/Calmar/Sortino"),
shown LEVERAGE-AWARE — GDE-synth is ~180% risk notional (0.9 SPX + 0.9 gold),
so each rule reports its average gross risk notional (1.8*w_gde + 1.0*w_spy)
alongside raw deltas; scale-free stats (Sharpe/Sortino/ulcer) are the
leverage-honest comparison. Final Q2 verdict is Phase 4's (drop-single-year
is decisive per the amendment).

Free parameters across all rules: expanding median (walk-forward) — 1;
everything else (10m/12-1/3-6-12m lookbacks, 60d, 15% target) fixed a-priori
by the brief. <=3 ✓. Costs: 5bp x one-way turnover (full switch = 5bp),
charged in the month the trade opens; BOXX = bills - 5bp/yr. Variant count
for the multiple-testing adjustment: 14 signals (Phase 2) + 4 active rules
vs 1 null (Phase 3); no unreported variants were run.
"""
import json
import math
import os

import numpy as np
import pandas as pd

import datalib as dl
from signals import (BOXX_DRAG, SWITCH_COST, MEDIAN_MIN_OBS, build_macro,
                     build_signal_frame, load_panel, _me, _fred_fix, _cum)

HERE = os.path.dirname(os.path.abspath(__file__))

FULL_START = pd.Period("1977-02", "M")   # first held month with all rules live
OOS_START = pd.Period("1990-02", "M")    # 15y-warmup window (matches Phase 2)
REGIMES = [("1980-99", "1980-01", "1999-12"), ("2001-11", "2001-01", "2011-12"),
           ("2012-18", "2012-01", "2018-12"), ("2022->", "2022-01", "2026-07")]
VOL_TARGET, VOL_WINDOW_D = 0.15, 60

W_MAP = {"gde": {"gde": 1.0, "spy": 0.0, "boxx": 0.0},
         "spy": {"gde": 0.0, "spy": 1.0, "boxx": 0.0},
         "boxx": {"gde": 0.0, "spy": 0.0, "boxx": 1.0},
         "5050": {"gde": 0.5, "spy": 0.5, "boxx": 0.0}}


# ------------------------------------------------------------ daily assets --
def build_daily_assets():
    """Daily gde-synth / spy / bills returns (baselines.py construction),
    1976-03 ->, used ONLY for the rule-5 sigma60 estimate. FLAG: pre-1993
    equity = ^GSPC price + smeared Shiller dividends."""
    d = dl.load_daily()
    _, sh_div, _, _ = dl.load_monthly_raw()
    cal = d["gspc"].loc["1976-03-01":].index
    spy_r = d["spy"].pct_change().dropna()
    gspc_r = d["gspc"].pct_change().reindex(cal)
    div_rate = pd.Series(sh_div.values, index=pd.PeriodIndex(sh_div.index, freq="M"))
    gspc_me = d["gspc"].groupby(d["gspc"].index.to_period("M")).last()
    dy_m = (div_rate / 12.0 / gspc_me).dropna()
    per = pd.PeriodIndex(cal, freq="M")
    days_in_m = pd.Series(1, index=cal).groupby(per).transform("sum").values
    dy_d = pd.Series(dy_m.reindex(per).values / days_in_m, index=cal)
    eq_r = gspc_r + dy_d
    eq_r.loc[spy_r.index.intersection(cal[cal >= "1993-02-01"])] = \
        spy_r.reindex(cal).loc["1993-02-01":]
    gc_r = dl.align_returns_to(d["gspc"].loc["1976-02-25":], d["gc"]).reindex(cal)
    dtb3 = d["dtb3"]
    bill_r = dl.bill_daily_returns(cal, dtb3).reindex(cal)
    dty = cal.to_series().diff().dt.days / 365.0
    y = dtb3.reindex(dtb3.index.union(cal)).ffill().reindex(cal)
    lease = pd.Series([(dl.EFFECTIVE_LEASE_2007ON if t.year >= 2007
                        else dl.lease_rate_for(t)) for t in cal], index=cal)
    carry = ((y.shift(1) - lease) / 100.0) * dty
    gde_d = (0.90 * eq_r + 0.10 * bill_r + 0.90 * (gc_r - carry)
             - (dl.GDE_FEE + dl.ROLL_COST) * dty)
    return pd.DataFrame({"gde": gde_d, "spy": eq_r,
                         "boxx": bill_r - BOXX_DRAG * dty}).dropna()


# ----------------------------------------------------------------- states --
def rule_states(sigs):
    """Rule 2/3/4 state labels per decision month t (strings), NaN-free rows
    only. Derived purely from the Phase-2 signal frame (causal)."""
    need = ["mom12_1_rel", "mom12_1_abs_gde", "mom12_1_abs_spy",
            "tips_trend12", "tips_level"]
    s = sigs[need].dropna()
    winner = np.where(s["mom12_1_rel"] > 0, "gde", "spy")
    abs_ok = np.where(winner == "gde", s["mom12_1_abs_gde"] > 0,
                      s["mom12_1_abs_spy"] < 0)   # spy-favorable when -1
    r2 = np.where(abs_ok, winner, "boxx")
    r_fav = s["tips_trend12"] > 0                 # +1 = trend down/flat, gold-fav
    lvl_low = s["tips_level"] > 0                 # +1 = level <= expanding median
    r3 = np.where(r_fav, "gde", np.where(lvl_low, "spy", "boxx"))
    r4 = np.where((r2 == "gde") & r_fav, "gde",
                  np.where((r2 == "boxx") & ~r_fav, "boxx", "5050"))
    return pd.DataFrame({"rule2": r2, "rule3": r3, "rule4": r4}, index=s.index)


def weights_from_states(states, col):
    return pd.DataFrame([W_MAP[x] for x in states[col]], index=states.index)


def voltarget_weights(w4, daily):
    """lam[t] = min(1, target / sigma60(target portfolio, data <= month-end t));
    residual to BOXX."""
    me_pos = daily.index.to_period("M")
    out = {}
    for t, w in w4.iterrows():
        dsub = daily[me_pos <= t]
        window = dsub.iloc[-VOL_WINDOW_D:]
        if len(window) < VOL_WINDOW_D:
            continue
        port_d = (window * w.values).sum(axis=1)
        sig60 = float(port_d.std(ddof=1) * math.sqrt(252.0))
        lam = min(1.0, VOL_TARGET / sig60) if sig60 > 0 else 1.0
        wv = w * lam
        wv["boxx"] += 1.0 - lam
        out[t] = {"gde": wv["gde"], "spy": wv["spy"], "boxx": wv["boxx"],
                  "lam": lam, "sig60": sig60}
    df = pd.DataFrame.from_dict(out, orient="index")
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df[["gde", "spy", "boxx"]], df[["lam", "sig60"]]


# --------------------------------------------------------------- backtest --
def backtest(W, assets, start=FULL_START):
    """W indexed by DECISION month t -> earns month t+1. Drift-aware one-way
    turnover, 5bp x turnover charged in the traded month. Initial buy-in not
    charged (identical for every rule). Returns (net returns, turnover,
    state-switch turnover series) indexed by HELD month."""
    cols = ["gde", "spy", "boxx"]
    W = W[cols]
    first_dec = start - 1
    rets, tos = {}, {}
    prev_end = None
    for t in W.index:
        ht = t + 1
        if ht not in assets.index or t < first_dec:
            continue
        w = W.loc[t].values
        to = 0.0 if prev_end is None else 0.5 * np.abs(w - prev_end).sum()
        r = assets.loc[ht, cols].values
        rets[ht] = float((w * r).sum() - SWITCH_COST * to)
        tos[ht] = float(to)
        grown = w * (1.0 + r)
        prev_end = grown / grown.sum()
    return pd.Series(rets), pd.Series(tos)


def nw_tstat(d, lags=6):
    d = d.dropna().values
    n = len(d)
    mu = d.mean()
    e = d - mu
    s = (e * e).mean()
    for j in range(1, lags + 1):
        g = (e[j:] * e[:-j]).mean() * (n - j) / n
        s += 2.0 * (1.0 - j / (lags + 1.0)) * g
    se = math.sqrt(s / n)
    return mu / se if se > 0 else np.nan


def window_stats(r, rf, p0, p1):
    w = r[(r.index >= pd.Period(p0, "M")) & (r.index <= pd.Period(p1, "M"))]
    if len(w) < 12:
        return None
    return dl.perf_stats(w, rf.reindex(w.index))


# --------------------------------------------------------------- QA gates --
def compute_all_weights(panel, macro, daily):
    """Full pipeline panel/macro/daily -> weights per rule (decision-month
    indexed). Single entry point so the QA checks exercise the REAL code."""
    sigs = build_signal_frame(panel, macro)
    states = rule_states(sigs)
    w1 = pd.DataFrame([W_MAP["5050"]] * len(panel), index=panel.index)
    w2 = weights_from_states(states, "rule2")
    w3 = weights_from_states(states, "rule3")
    w4 = weights_from_states(states, "rule4")
    w5, lam = voltarget_weights(w4, daily)
    return {"static_5050": w1, "relmom_cash": w2, "realrate_gate": w3,
            "composite": w4, "voltarget_15": w5}, states, lam


def qa_checks(panel, macro, daily, W_full, cuts=("1990-12", "2005-06", "2019-12")):
    """(a) truncation invariance: weights computed from inputs truncated at
    month-end T must equal full-sample weights for all decisions <= T.
    (b) perturbation: shocking inputs AFTER T must not change decisions <= T."""
    rng = np.random.default_rng(7)
    out = {}
    for cut in cuts:
        T = pd.Period(cut, "M")
        p_tr = panel[panel.index <= T]
        m_tr = macro[macro.index <= T]
        d_tr = daily[daily.index.to_period("M") <= T]
        Wt, _, _ = compute_all_weights(p_tr, m_tr, d_tr)
        trunc_ok = all(
            np.allclose(Wt[k].loc[:T].values,
                        W_full[k].loc[:T].reindex(Wt[k].loc[:T].index).values,
                        atol=1e-12, equal_nan=True)
            and len(Wt[k].loc[:T]) == len(W_full[k].loc[:T])
            for k in W_full)
        p_pe = panel.copy()
        fut = p_pe.index > T
        p_pe.loc[fut] = p_pe.loc[fut] * (1 + rng.normal(0, 0.5, (fut.sum(), p_pe.shape[1])))
        m_pe = macro.copy()
        futm = m_pe.index > T
        m_pe.loc[futm] = m_pe.loc[futm] + rng.normal(0, 2.0, (futm.sum(), m_pe.shape[1]))
        d_pe = daily.copy()
        futd = d_pe.index.to_period("M") > T
        d_pe.loc[futd] = d_pe.loc[futd] * 3.0
        Wp, _, _ = compute_all_weights(p_pe, m_pe, d_pe)
        pert_ok = all(
            np.allclose(Wp[k].loc[:T].values, W_full[k].loc[:T].values,
                        atol=1e-12, equal_nan=True) for k in W_full)
        out[cut] = {"truncation_invariance": bool(trunc_ok),
                    "future_perturbation_invariance": bool(pert_ok)}
        print(f"QA cut {cut}: truncation {'PASS' if trunc_ok else 'FAIL'}, "
              f"perturbation {'PASS' if pert_ok else 'FAIL'}")
    return out


# ------------------------------------------------------------------- main --
def main():
    panel = load_panel()
    macro = build_macro()
    daily = build_daily_assets()
    assets = pd.DataFrame({"gde": panel["gde_synth"], "spy": panel["spx_tr"],
                           "boxx": panel["bills"] - BOXX_DRAG / 12.0})
    rf = panel["bills"]

    W, states, lam = compute_all_weights(panel, macro, daily)

    qa = qa_checks(panel, macro, daily, W)
    if not all(v["truncation_invariance"] and v["future_perturbation_invariance"]
               for v in qa.values()):
        raise SystemExit("QA FAILED — timing bug in pipeline, DO NOT trust results")

    results, rets = {}, {}
    null_full = null_oos = None
    for name in W:
        r, to = backtest(W[name], assets)
        rets[name] = r
        st_full = window_stats(r, rf, str(FULL_START), "2026-07")
        st_oos = window_stats(r, rf, str(OOS_START), "2026-07")
        regs = {lab: window_stats(r, rf, a, b) for lab, a, b in REGIMES}
        # turnover + label switches per decade
        dec_to, dec_sw = {}, {}
        state_col = {"relmom_cash": "rule2", "realrate_gate": "rule3",
                     "composite": "rule4", "voltarget_15": "rule4"}.get(name)
        sw = None
        if state_col is not None:
            s = states[state_col]
            sw = (s != s.shift(1)) & s.shift(1).notna()
        for y0 in range(1980, 2030, 10):
            y1 = min(y0 + 9, 2026)
            mask = (to.index >= pd.Period(f"{y0}-01", "M")) & \
                   (to.index <= pd.Period(f"{y1}-12", "M"))
            yrs = mask.sum() / 12.0
            if yrs < 1:
                continue
            dec_to[f"{y0}s"] = float(to[mask].sum() / yrs)          # x/yr one-way
            if sw is not None:
                mk = (sw.index >= pd.Period(f"{y0}-01", "M")) & \
                     (sw.index <= pd.Period(f"{y1}-12", "M"))
                dec_sw[f"{y0}s"] = int(sw[mk].sum())
        results[name] = {"full": st_full, "oos": st_oos, "regimes": regs,
                         "turnover_per_yr_by_decade": dec_to,
                         "switches_by_decade": dec_sw}
        if name == "static_5050":
            null_full, null_oos = st_full, st_oos

    # B&H SPY benchmark rows (owner amendment A5 — Q2 comparison set)
    spy_r = panel["spx_tr"]
    spy_stats = {"full": window_stats(spy_r, rf, str(FULL_START), "2026-07"),
                 "oos": window_stats(spy_r, rf, str(OOS_START), "2026-07"),
                 "regimes": {lab: window_stats(spy_r, rf, a, b)
                             for lab, a, b in REGIMES}}

    # vs-null and vs-SPY comparisons
    for name in W:
        gross = (1.8 * W[name]["gde"] + 1.0 * W[name]["spy"])
        results[name]["avg_gross_risk_notional"] = float(
            gross[gross.index >= FULL_START - 1].mean())
        c = results[name]
        c["vs_spy"] = {}
        for win, bench in (("full", spy_stats["full"]), ("oos", spy_stats["oos"])):
            s = c[win]
            c["vs_spy"][win] = {
                "dCAGR": s["CAGR"] - bench["CAGR"],
                "dMaxDD": s["MaxDD_m"] - bench["MaxDD_m"],
                "dCalmar": s["Calmar"] - bench["Calmar"],
                "dSortino": s["Sortino"] - bench["Sortino"],
                "dSharpe": s["Sharpe"] - bench["Sharpe"],
                "dominates_raw": bool(s["CAGR"] >= bench["CAGR"]
                                      and s["MaxDD_m"] > bench["MaxDD_m"]
                                      and s["Calmar"] > bench["Calmar"]
                                      and s["Sortino"] > bench["Sortino"])}
        if name == "static_5050":
            continue
        d_full = (rets[name] - rets["static_5050"]).dropna()
        d_oos = d_full[d_full.index >= OOS_START]
        c["vs_null"] = {
            "full": {"dCAGR": c["full"]["CAGR"] - null_full["CAGR"],
                     "dMaxDD": c["full"]["MaxDD_m"] - null_full["MaxDD_m"],
                     "dCalmar": c["full"]["Calmar"] - null_full["Calmar"],
                     "dUlcer": c["full"]["Ulcer"] - null_full["Ulcer"],
                     "nw_t_meandiff": float(nw_tstat(d_full))},
            "oos": {"dCAGR": c["oos"]["CAGR"] - null_oos["CAGR"],
                    "dMaxDD": c["oos"]["MaxDD_m"] - null_oos["MaxDD_m"],
                    "dCalmar": c["oos"]["Calmar"] - null_oos["Calmar"],
                    "dUlcer": c["oos"]["Ulcer"] - null_oos["Ulcer"],
                    "nw_t_meandiff": float(nw_tstat(d_oos))}}

    # ---- print master tables ----
    print("\n==== vs B&H SPY (owner amendment A5, Q2) ====")
    for win in ("full", "oos"):
        b = spy_stats[win]
        print(f"[{win}] B&H SPY: CAGR {b['CAGR']:.2%} MaxDD {b['MaxDD_m']:.1%}"
              f" Calmar {b['Calmar']:.2f} Sortino {b['Sortino']:.2f}"
              f" Sharpe {b['Sharpe']:.2f}")
        for name, c in results.items():
            v = c["vs_spy"][win]
            print(f"  {name:14s} dCAGR {v['dCAGR']:+.2%} dMaxDD {v['dMaxDD']:+.1%}"
                  f" dCalmar {v['dCalmar']:+.2f} dSortino {v['dSortino']:+.2f}"
                  f" gross~{c['avg_gross_risk_notional']:.2f}x"
                  f" dominates_raw={v['dominates_raw']}")

    for win in ("full", "oos"):
        print(f"\n==== {win.upper()} window "
              f"({FULL_START if win == 'full' else OOS_START} -> 2026-07) ====")
        print(f"{'rule':14s} {'CAGR':>7s} {'Vol':>6s} {'Sharpe':>6s} {'Sortino':>7s}"
              f" {'MaxDD':>7s} {'UW':>4s} {'Calmar':>6s} {'Ulcer':>6s}"
              f" {'Worst12':>8s} {'NW-t':>5s}")
        for name, c in results.items():
            s = c[win]
            t = c.get("vs_null", {}).get(win, {}).get("nw_t_meandiff", float("nan"))
            print(f"{name:14s} {s['CAGR']:7.2%} {s['Vol']:6.2%} {s['Sharpe']:6.2f}"
                  f" {s['Sortino']:7.2f} {s['MaxDD_m']:7.1%}"
                  f" {s['UnderwaterMax_m']:4d} {s['Calmar']:6.2f} {s['Ulcer']:6.1f}"
                  f" {s['Worst12m']:8.1%} {t:5.2f}")
            if s["Sharpe"] > 1.2:
                print("  ^^ TRIPWIRE Sharpe>1.2 — STOP AND AUDIT before reporting")
    print("\n==== per-regime CAGR / MaxDD / Calmar ====")
    for name, c in results.items():
        row = "  ".join(f"{lab}: {v['CAGR']:6.1%} {v['MaxDD_m']:6.1%} {v['Calmar']:5.2f}"
                        for lab, v in c["regimes"].items() if v)
        print(f"{name:14s} {row}")
    print("\nturnover (one-way switches equiv./yr) + state switches by decade:")
    for name, c in results.items():
        print(f"{name:14s} to/yr {c['turnover_per_yr_by_decade']}"
              f" | switches {c['switches_by_decade']}")

    lam_stats = {"mean_lam": float(lam["lam"].mean()),
                 "pct_scaled_below_1": float((lam["lam"] < 1.0).mean()),
                 "min_lam": float(lam["lam"].min())}
    print("\nvoltarget lambda:", {k: round(v, 3) for k, v in lam_stats.items()})

    out = {
        "conventions": "decision month t (data <= month-end t; CPI/DXY extra "
                       "1m availability lag) earns month t+1; 5bp x one-way "
                       "turnover; BOXX = bills - 5bp/yr; walk-forward only",
        "windows": {"full": f"{FULL_START}->2026-07", "oos": f"{OOS_START}->2026-07"},
        "qa_checks": qa,
        "n_variants_tested": {"signals_phase2": 14, "rules_phase3": 5,
                              "note": "no unreported variants were run; "
                                      "multiple-testing adjustment in Phase 4 "
                                      "should count 4 active rules vs null"},
        "lam_stats": lam_stats,
        "bh_spy_benchmark": spy_stats,
        "rules": results,
        "monthly_returns": {n: {str(k): float(v) for k, v in r.items()}
                            for n, r in rets.items()},
        "states": {c: {str(k): v for k, v in states[c].items()}
                   for c in states.columns},
        "lam_series": {str(k): float(v) for k, v in lam["lam"].items()},
    }
    with open(os.path.join(HERE, "rules_results.json"), "w") as fh:
        json.dump(out, fh, default=float, indent=1)
    print("\nwrote rules_results.json")


if __name__ == "__main__":
    main()
