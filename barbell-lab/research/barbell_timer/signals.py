#!/usr/bin/env python3
"""Phase 2 — signal library, each signal in ISOLATION, per frozen SPEC.md.

Universe: monthly panel research/barbell_timer/panel_monthly.json (Phase 1
frozen; 1975-02 -> 2026-07, month-END convention) + macro built here from the
frozen fixtures (DFII10, DGS10, CPIAUCSL, FEDFUNDS, DTWEXM/DTWEXBGS).

TIMING DISCIPLINE (pre-registered, shared with rules.py)
--------------------------------------------------------
- A signal dated month t is computed ONLY from data available at month-end t;
  the position it implies is executed at the NEXT month's open and earns the
  month t+1 panel return (close(t) -> close(t+1); the overnight open gap is
  part of the intramonth-blind approximation, flagged in BASELINES.md).
- Market prices (panel TR indices, DFII10, DGS10 month-end): month-t value is
  known at month-end t.
- CPI availability lag: at month-end t the latest CPI print is for month t-1
  (mid-month release). All CPI-using series therefore use CPI through t-1,
  i.e. "t-1 data earns month t+1".
- DXY (Fed H.10) publishes weekly with a few days' lag; a month-end value can
  be unpublished at the next open. Conservatively lagged 1 month (t-1 value
  used at month-end t). Amendment A10.
- FEDFUNDS monthly average: daily EFFR is public in real time, so month-t
  average is computable at month-end t (no extra lag).

SIGNAL DEFINITIONS (all lookbacks fixed a-priori; the ONLY estimated
quantity is an expanding median, walk-forward, min 24 obs)
--------------------------------------------------------
Each signal emits pred in {+1,-1}: +1 = "GDE beats SPY over the next 12m".
 1. sma10_gde      GDE-synth TR index >= its 10m SMA -> +1 (else -1)
 2. sma10_spy      SPY TR index >= its 10m SMA -> -1 (SPY strong; else +1)
 3. mom12_1_abs_gde  GDE 12-1 return > matching bills return -> +1
 4. mom12_1_abs_spy  SPY 12-1 return > matching bills return -> -1 (else +1)
 5. mom12_1_rel    GDE 12-1 minus SPY 12-1 > 0 -> +1
 6. ratio_sma10    gold-spot/SPY TR ratio >= its 10m SMA -> +1
 7-9. tsmom_{3,6,12}_gde  GDE trailing k-m return > k-m bills -> +1 (incl. month t)
10. tips_level     real 10y <= expanding median (walk-forward) -> +1
11. tips_chg3      real 10y 3m change <= 0 -> +1
12. tips_trend12   real 10y 12m change <= 0 -> +1
13. real_ffr       FEDFUNDS - trailing-12m CPI infl <= 0 -> +1 (a-priori 0 threshold)
14. term structure -> INFEASIBLE with frozen fixtures, logged, not faked (A7)
15. dxy_trend12    spliced trade-weighted USD 12m change > 0 -> -1 (else +1)

12-1 convention: product of monthly returns t-11..t-1 (11 months, skipping
month t). TSMOM includes month t (standard). SMA10 = mean of month-end index
levels t-9..t.

Real 10y splice (FLAGGED, amendment A6): DFII10 month-end from 2003-01;
before that DGS10 month-end minus trailing-12m CPI inflation (CPI through
t-1). The proxy is nominal-minus-REALIZED-inflation, not a market real yield;
the overlap diff 2003-07 is printed by this script and quoted in SIGNALS.md.

EVALUATION (frozen): hit rate of pred vs sign of next-12m GDE-minus-SPY
compounded relative return, OUT-OF-SAMPLE only: first 15y (1975-02..1990-01)
are warmup; evaluation months t = 1990-01..2025-07 (last t with a full 12m
forward window). Overlapping windows -> serial correlation: p-values are
reported both naive-binomial and with N_eff = N/12 (the honest one).
KILL RULE: OOS hit rate <= 50% -> signal killed (still reported).
Single-signal rule: monthly toggle per the mapping in META (relative signals
toggle GDE/SPY; absolute signals toggle sleeve/BOXX), positions decided at t,
earn t+1, 5bp per switch, BOXX = bills - 5bp/yr; stats on 1990-02 -> 2026-07.
"""
import json
import math
import os

import numpy as np
import pandas as pd

import datalib as dl

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

WARMUP_END = pd.Period("1990-01", "M")   # first 15y = warmup (1975-02..1990-01)
EVAL_START = pd.Period("1990-01", "M")   # first evaluated signal month
BOXX_DRAG = 0.0005                       # BOXX = bills - 5bp/yr
SWITCH_COST = 0.0005                     # 5bp per full portfolio switch
MEDIAN_MIN_OBS = 24                      # expanding-median burn-in (a-priori)


# ---------------------------------------------------------------- loaders --
def load_panel():
    j = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]
    df = pd.DataFrame.from_dict(j, orient="index").astype(float)
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df.sort_index()


def _me(daily):
    """Month-end value of a daily series -> PeriodIndex[M]."""
    return daily.groupby(daily.index.to_period("M")).last()


def _fred_fix(name):
    d = json.load(open(os.path.join(FIX, name)))["rows"]
    s = pd.Series({r[0]: r[1] for r in d}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def build_macro():
    """Monthly macro columns, each dated by the month-end at which it is
    KNOWABLE (availability lags already applied — see module docstring)."""
    cpi = _fred_fix("fred_cpiaucsl.json")
    cpi.index = cpi.index.to_period("M")
    # trailing-12m inflation KNOWN at month-end t: CPI[t-1]/CPI[t-13] - 1
    infl_avail = (cpi.shift(1) / cpi.shift(13) - 1.0) * 100.0

    dgs10_me = _me(_fred_fix("fred_dgs10.json"))
    dfii10_me = _me(_fred_fix("fred_dfii10.json"))
    proxy = dgs10_me - infl_avail.reindex(dgs10_me.index)
    real10y = pd.concat([proxy.loc[:"2002-12"], dfii10_me.loc["2003-01":]])
    real10y.name = "real10y"

    ff = _fred_fix("fred_fedfunds.json")
    ff.index = ff.index.to_period("M")
    real_ffr = ff - infl_avail.reindex(ff.index)

    # DXY splice: DTWEXM month-end to 2005-12; DTWEXBGS after, ratio-spliced
    # at 2006-01. Publication lag: shift(1) -> value usable at month-end t is
    # the t-1 month-end print.
    m_ = _me(_fred_fix("fred_dtwexm.json"))
    b_ = _me(_fred_fix("fred_dtwexbgs.json"))
    k = pd.Period("2006-01", "M")
    dxy = pd.concat([m_.loc[:"2005-12"], b_.loc["2006-01":] * (m_[k] / b_[k])])
    dxy_avail = dxy.shift(1)

    out = pd.DataFrame({"real10y": real10y, "real_ffr": real_ffr,
                        "dxy_avail": dxy_avail, "infl_avail": infl_avail})
    out.attrs["splice_diag"] = {
        "real10y_overlap_2003_2007_mean_diff_pp": float(
            (proxy - dfii10_me).loc["2003-01":"2007-12"].mean()),
        "real10y_2002_12_proxy": float(proxy["2002-12"]),
        "real10y_2003_01_dfii10": float(dfii10_me[pd.Period("2003-01", "M")]),
    }
    return out


# ---------------------------------------------------------------- signals --
def _cum(r):
    return (1.0 + r).cumprod()


def _k_ret(r, k, skip1=False):
    """Trailing k-month compounded return; skip1 -> months t-k..t-1 (12-1
    style uses k=11 with skip1)."""
    c = _cum(r)
    out = c / c.shift(k) - 1.0
    return out.shift(1) if skip1 else out


META = {  # name -> (mapping for single-signal rule {+1: asset, -1: asset}, desc)
    "sma10_gde": ({+1: "gde", -1: "boxx"}, "GDE-synth index vs 10m SMA"),
    "sma10_spy": ({+1: "boxx", -1: "spy"}, "SPY index vs 10m SMA (strong SPY -> -1)"),
    "mom12_1_abs_gde": ({+1: "gde", -1: "boxx"}, "GDE 12-1 vs bills"),
    "mom12_1_abs_spy": ({+1: "boxx", -1: "spy"}, "SPY 12-1 vs bills (strong SPY -> -1)"),
    "mom12_1_rel": ({+1: "gde", -1: "spy"}, "GDE 12-1 minus SPY 12-1"),
    "ratio_sma10": ({+1: "gde", -1: "spy"}, "gold-spot/SPY TR ratio vs 10m SMA"),
    "tsmom_3_gde": ({+1: "gde", -1: "boxx"}, "GDE 3m TSMOM vs bills"),
    "tsmom_6_gde": ({+1: "gde", -1: "boxx"}, "GDE 6m TSMOM vs bills"),
    "tsmom_12_gde": ({+1: "gde", -1: "boxx"}, "GDE 12m TSMOM vs bills"),
    "tips_level": ({+1: "gde", -1: "spy"}, "real 10y vs expanding median (spliced pre-2003)"),
    "tips_chg3": ({+1: "gde", -1: "spy"}, "real 10y 3m change (<=0 gold-fav)"),
    "tips_trend12": ({+1: "gde", -1: "spy"}, "real 10y 12m change (<=0 gold-fav)"),
    "real_ffr": ({+1: "gde", -1: "spy"}, "FEDFUNDS minus 12m CPI infl vs 0"),
    "dxy_trend12": ({+1: "gde", -1: "spy"}, "trade-weighted USD 12m change (rising -> -1)"),
}

INFEASIBLE = {
    "futures_term_structure": (
        "INFEASIBLE with frozen fixtures (amendment A7): fmp_gcusd_light is a "
        "price-spliced FRONT-MONTH-only continuous series — no deferred "
        "contracts, so no curve slope exists in the data. A GLD-minus-GCUSD "
        "'basis' surrogate was considered and rejected: it would mix a 1:30pm "
        "COMEX settle against a 4pm NYSE close and a 40bp/yr fee against a "
        "price-spliced roll, so day-to-day 'slope' would be mark noise, not "
        "term structure. Logged as not-tested rather than faked.")
}


def build_signal_frame(panel, macro):
    """All signal series, each dated at its DECISION month t (uses only data
    knowable at month-end t). Returns DataFrame of {+1,-1} with NaN where a
    signal is not yet defined."""
    gde, spy, gold, bills = (panel[c] for c in
                             ["gde_synth", "spx_tr", "gold", "bills"])
    idx_gde, idx_spy, idx_gold = _cum(gde), _cum(spy), _cum(gold)
    sig = {}

    sma_g = idx_gde.rolling(10).mean()
    sma_s = idx_spy.rolling(10).mean()
    sig["sma10_gde"] = np.where(idx_gde >= sma_g, 1, -1)
    sig["sma10_spy"] = np.where(idx_spy >= sma_s, -1, 1)

    m11 = lambda r: _k_ret(r, 11, skip1=True)          # 12-1: months t-11..t-1
    sig["mom12_1_abs_gde"] = np.where(m11(gde) > m11(bills), 1, -1)
    sig["mom12_1_abs_spy"] = np.where(m11(spy) > m11(bills), -1, 1)
    sig["mom12_1_rel"] = np.where(m11(gde) > m11(spy), 1, -1)

    ratio = idx_gold / idx_spy
    sig["ratio_sma10"] = np.where(ratio >= ratio.rolling(10).mean(), 1, -1)

    for k in (3, 6, 12):
        sig[f"tsmom_{k}_gde"] = np.where(
            _k_ret(gde, k) > _k_ret(bills, k), 1, -1)

    r10 = macro["real10y"].reindex(panel.index)
    med = r10.expanding(min_periods=MEDIAN_MIN_OBS).median()
    sig["tips_level"] = np.where(r10 <= med, 1, -1)
    sig["tips_chg3"] = np.where(r10 - r10.shift(3) <= 0, 1, -1)
    sig["tips_trend12"] = np.where(r10 - r10.shift(12) <= 0, 1, -1)

    rffr = macro["real_ffr"].reindex(panel.index)
    sig["real_ffr"] = np.where(rffr <= 0.0, 1, -1)

    dxy = macro["dxy_avail"].reindex(panel.index)
    sig["dxy_trend12"] = np.where(dxy - dxy.shift(12) > 0, -1, 1)

    out = pd.DataFrame(sig, index=panel.index).astype(float)
    # blank out entries where the underlying inputs were NaN (np.where hides them)
    nanmask = {
        "sma10_gde": sma_g, "sma10_spy": sma_s,
        "mom12_1_abs_gde": m11(gde), "mom12_1_abs_spy": m11(spy),
        "mom12_1_rel": m11(gde), "ratio_sma10": ratio.rolling(10).mean(),
        "tsmom_3_gde": _k_ret(gde, 3), "tsmom_6_gde": _k_ret(gde, 6),
        "tsmom_12_gde": _k_ret(gde, 12),
        "tips_level": med, "tips_chg3": r10 - r10.shift(3),
        "tips_trend12": r10 - r10.shift(12), "real_ffr": rffr,
        "dxy_trend12": dxy - dxy.shift(12),
    }
    for name, base in nanmask.items():
        out.loc[base.reindex(panel.index).isna(), name] = np.nan
    return out


# ------------------------------------------------------------- evaluation --
def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def hit_rates(sigs, panel):
    gde, spy = panel["gde_synth"], panel["spx_tr"]
    f = lambda r: _cum(r).shift(-12) / _cum(r) - 1.0   # fwd 12m from t (t+1..t+12)
    fwd_rel = (f(gde) - f(spy))
    res = {}
    for name in sigs.columns:
        s = sigs[name]
        m = (s.index >= EVAL_START) & s.notna() & fwd_rel.notna()
        pred, actual = s[m], np.sign(fwd_rel[m])
        n = int(m.sum())
        hits = int((pred == actual).sum())
        hr = hits / n
        # one-sided binomial vs 0.5, normal approx; overlap-adjusted N/12
        z = (hr - 0.5) * math.sqrt(4 * n)
        z_adj = (hr - 0.5) * math.sqrt(4 * n / 12.0)
        res[name] = {"n": n, "hit_rate": hr,
                     "p_naive": _norm_sf(z), "p_overlap_adj": _norm_sf(z_adj),
                     "killed": bool(hr <= 0.50)}
    return res, fwd_rel


def single_signal_rule(sig, mapping, panel):
    """Toggle rule: position decided at t per mapping, earns month t+1,
    5bp per switch. OOS stats window: returns 1990-02 -> end."""
    assets = pd.DataFrame({
        "gde": panel["gde_synth"], "spy": panel["spx_tr"],
        "boxx": panel["bills"] - BOXX_DRAG / 12.0})
    pos = sig.dropna().map(lambda v: mapping[int(v)])
    pos_held = pos.shift(1).dropna()                  # held during month t
    r = pd.Series([assets.loc[t, p] for t, p in pos_held.items()],
                  index=pos_held.index)
    switch = (pos != pos.shift(1)) & pos.shift(1).notna()
    r = r - switch.shift(1).reindex(r.index).fillna(False) * SWITCH_COST
    r_oos = r[r.index >= pd.Period("1990-02", "M")]
    st = dl.perf_stats(r_oos, panel["bills"].reindex(r_oos.index))
    st["n_switches_oos"] = int(switch[switch.index >= pd.Period("1990-01", "M")].sum())
    return st, r


def main():
    panel = load_panel()
    macro = build_macro()
    diag = macro.attrs["splice_diag"]
    print("real10y splice diagnostic:", {k: round(v, 2) for k, v in diag.items()})

    sigs = build_signal_frame(panel, macro)
    hr, fwd_rel = hit_rates(sigs, panel)

    # base-rate honesty: what would constant +1 / constant -1 have scored?
    m = (fwd_rel.index >= EVAL_START) & fwd_rel.notna()
    base_up = float((np.sign(fwd_rel[m]) == 1).mean())
    print(f"\nOOS eval months: {int(m.sum())} (1990-01..2025-07); "
          f"base rate P(GDE beats SPY next 12m) = {base_up:.1%}\n")

    print(f"{'signal':18s} {'N':>4s} {'hit':>6s} {'p(adj)':>7s} {'kill':>4s}"
          f"   {'CAGR':>7s} {'MaxDD':>7s} {'Ulcer':>6s} {'Sharpe':>6s} {'sw':>3s}")
    results = {}
    for name in sigs.columns:
        st, r_full = single_signal_rule(sigs[name], META[name][0], panel)
        h = hr[name]
        results[name] = {
            "desc": META[name][1],
            "mapping": {str(k): v for k, v in META[name][0].items()},
            "oos_hit": h, "killed": h["killed"],
            "single_rule_oos": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                                for k, v in st.items()},
        }
        print(f"{name:18s} {h['n']:4d} {h['hit_rate']:6.1%} {h['p_overlap_adj']:7.2f}"
              f" {'KILL' if h['killed'] else 'live':>4s}   {st['CAGR']:7.2%}"
              f" {st['MaxDD_m']:7.1%} {st['Ulcer']:6.1f} {st['Sharpe']:6.2f}"
              f" {st['n_switches_oos']:3d}")
        if st["Sharpe"] > 1.2:
            print(f"  ^^ TRIPWIRE Sharpe>1.2 on {name} — STOP AND AUDIT")

    kill_list = [n for n in results if results[n]["killed"]]
    print(f"\nKILL LIST ({len(kill_list)}): {kill_list}")
    print("infeasible (not tested):", list(INFEASIBLE))

    out = {
        "conventions": "see module docstring; decision month t earns t+1; "
                       "CPI/DXY carry an extra availability-lag month",
        "eval_window": "signal months 1990-01..2025-07 (15y warmup), "
                       "single-rule returns 1990-02 -> 2026-07",
        "base_rate_gde_beats_spy_12m": base_up,
        "real10y_splice_diag": diag,
        "signals": results,
        "kill_list": kill_list,
        "infeasible": INFEASIBLE,
        "n_signal_variants_tested": len(results),
    }
    with open(os.path.join(HERE, "signals_results.json"), "w") as fh:
        json.dump(out, fh, default=float, indent=1)
    # frozen signal series for rules.py + Phase 4
    sigs.to_json(os.path.join(HERE, "signal_series.json"), date_format="iso")
    print("\nwrote signals_results.json, signal_series.json")


if __name__ == "__main__":
    main()
