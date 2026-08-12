#!/usr/bin/env python3
"""AMENDMENT A17 — cross-equity-internals timing signals (s15-s18) + rules 9/10.

Builder AND first referee in one run (single-agent round — labeled as such in
A17_INTERNALS.md). Everything below the A-PRIORI block was frozen BEFORE any
result was computed; no thresholds were searched, no variants beyond the four
signals + two rules pre-registered in SPEC.md A17 were run.

DATA (all frozen, no network)
-----------------------------
- research/fixtures/french12.json — Ken French 12-industry VALUE-WEIGHTED
  monthly returns, PERCENT units, keyed YYYY-MM. Fixture covers 1926-07 ->
  2026-06 but SPEC A17 says "industries 1935->": per the literal spec the
  signals use 1935-01 onward (amendment A18; affects only s18's expanding-z
  baseline — the 12-1 momenta are trailing and identical either way).
- fixtures/fred_baa10ym.json — frozen copy (provenance inside + PROVENANCE.md)
  of treasury-canary's cycle fixture BAA10YM: Moody's Baa minus 10Y Treasury
  spread, pp, monthly average, 1959-01 -> 2026-07.
- panel_monthly.json — Phase-1 frozen GDE-synth / SPY / bills panel.

A-PRIORI DEFINITIONS (amendments A18-A21, fixed before computation)
-------------------------------------------------------------------
A18  French data window starts 1935-01 (literal SPEC text; fixture starts
     1926-07 — discrepancy logged, not silently resolved).
A19  Risk-off ("adverse") side of each signal is the natural zero boundary —
     no threshold search:
      s15 def_cyc   : 12-1 relmom (equal-weight Utils+NoDur+Hlth basket) minus
                      12-1 relmom (equal-weight Durbl+Manuf+Money basket) > 0
                      -> defensives leading -> RISK-OFF.
      s16 utils_mkt : Utils 12-1 minus market 12-1 > 0 -> RISK-OFF
                      (market = equal-weight mean of all 12 industry returns,
                      Utils included, per SPEC text).
      s17 baa_chg3  : spread(t) - spread(t-3) > 0 (widening) -> RISK-OFF.
      s18 corr12_z  : trailing 12m mean pairwise Pearson corr of the 12
                      industries (window t-11..t, 66 pairs), expanding z
                      (walk-forward mean/std incl. t, ddof=1, min 24 obs —
                      repo standing burn-in); z > 0 -> RISK-OFF.
     Isolation hit-rate mapping (Phase-2 precedent: equity weakness -> GDE
     relative win, cf. sma10_spy): RISK-OFF -> pred +1 ("GDE beats SPY next
     12m"), benign -> -1. Direction frozen here; kill is judged on THIS
     mapping, no post-hoc flips.
A20  Availability: French industry month-t returns and the month-t Baa spread
     average are treated as knowable at month-end t (both derive from
     real-time public market prices; the published French library lags —
     flagged as an approximation, bounded by the mandatory 1-month lag
     stress). 12-1 convention = compounded months t-11..t-1 skipping t
     (repo standard); baskets are equal-weight monthly-rebalanced means of
     industry returns compounded as baskets.
A21  If MORE than one signal survives the kill bar, "internals adverse" for
     rules 9 and 10 = ANY surviving signal on its risk-off side (union —
     fixed now, before any hit rate or rule backtest was seen). Rules:
      rule 9  internals_exit : default GDE; adverse -> BOXX.
      rule 10 relmom_gated   : rule-2 (relmom_cash) state, except state==GDE
                               AND adverse -> BOXX; SPY/BOXX states untouched.

EVALUATION (frozen, identical to Phase 2 / Phase 4)
---------------------------------------------------
- Isolation: OOS hit rate vs sign of next-12m GDE-synth minus SPY compounded
  relative return; warmup 1975-02..1990-01 (15y), eval t = 1990-01..2025-07;
  N and the 54.8% always-GDE base rate reported; KILL if hit <= 50%.
- Rules: decision at month-end t earns month t+1 (next-open convention),
  5bp x one-way turnover, BOXX = bills - 5bp/yr; FULL window 1977-02 ->
  2026-07, OOS 1990-02 -> 2026-07. Truncation + future-perturbation
  self-checks HARD-EXIT on failure. Sharpe > 1.2 -> stop and audit.
- Referee battery (same code paths as qa_phase4.py conventions): start-date
  grid 1990..2015, drop-single-year 1990..2026, 1-month lag stress
  (decision t earns t+2), circular block bootstrap (24m, 4000) vs null AND
  vs relmom_cash. Multiple-testing family after A17: 14 P2 signals + 4 P3
  rules + 4 A12 exits + 4 A17 signals = 26 tested variants, + 2 A17 rules
  = 28; adjusted p reported x2 (A17 rules), x10 (all rule-level candidates
  vs null: 4+4+2) and x28 (full logged family).
"""
import itertools
import json
import math
import os

import numpy as np
import pandas as pd

import datalib as dl

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
REPO_FIX = os.path.normpath(os.path.join(HERE, "..", "fixtures"))

FRENCH_START = pd.Period("1935-01", "M")   # A18
Z_MIN_OBS = 24                             # repo standing expanding burn-in
EVAL_START = pd.Period("1990-01", "M")     # 15y warmup, Phase-2 convention
FULL_START = pd.Period("1977-02", "M")     # first held month, rules 1-5 window
OOS_START = pd.Period("1990-02", "M")
END = pd.Period("2026-07", "M")
BOXX_DRAG = 0.0005
COST = 0.0005
N_BOOT, BLOCK = 4000, 24
RNG = np.random.default_rng(20260812)

DEFENSIVE = ["Utils", "NoDur", "Hlth"]
CYCLICAL = ["Durbl", "Manuf", "Money"]

REGIMES = [("1980-99", "1980-01", "1999-12"), ("2001-11", "2001-01", "2011-12"),
           ("2012-18", "2012-01", "2018-12"), ("2022->", "2022-01", "2026-07")]

STATE_W = {"gde": np.array([1.0, 0.0, 0.0]), "spy": np.array([0.0, 1.0, 0.0]),
           "boxx": np.array([0.0, 0.0, 1.0]), "5050": np.array([0.5, 0.5, 0.0])}


# ---------------------------------------------------------------- loaders --
def load_panel():
    j = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]
    df = pd.DataFrame.from_dict(j, orient="index").astype(float)
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df.sort_index()


def load_french():
    j = json.load(open(os.path.join(REPO_FIX, "french12.json")))
    df = pd.DataFrame.from_dict(j["rows"], orient="index")
    df.columns = j["names"]
    df.index = pd.PeriodIndex(df.index, freq="M")
    df = df.sort_index() / 100.0           # percent -> decimal
    return df[df.index >= FRENCH_START]    # A18
def load_baa():
    j = json.load(open(os.path.join(FIX, "fred_baa10ym.json")))
    s = pd.Series({r[0]: r[1] for r in j["rows"]}, dtype=float)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.sort_index()


# ---------------------------------------------------------------- signals --
def mom121(r):
    c = (1.0 + r).cumprod()
    return c.shift(1) / c.shift(12) - 1.0   # months t-11..t-1, skip t


def mean_pairwise_corr12(fr):
    """Trailing 12m mean pairwise Pearson corr of the 12 industries at each
    month t (window t-11..t)."""
    X = fr.values
    n = len(fr)
    out = np.full(n, np.nan)
    iu = np.triu_indices(fr.shape[1], k=1)
    for i in range(11, n):
        C = np.corrcoef(X[i - 11:i + 1].T)
        out[i] = C[iu].mean()
    return pd.Series(out, index=fr.index)


def build_internals(french, baa):
    """Signal frame in {+1,-1} (+1 = risk-off/adverse), NaN where undefined.
    Decision-month indexed; uses only data through month-end t (A20)."""
    d_basket = french[DEFENSIVE].mean(axis=1)
    c_basket = french[CYCLICAL].mean(axis=1)
    mkt = french.mean(axis=1)
    sig, raw = {}, {}

    raw["s15"] = mom121(d_basket) - mom121(c_basket)
    raw["s16"] = mom121(french["Utils"]) - mom121(mkt)
    raw["s17"] = baa - baa.shift(3)
    corr12 = mean_pairwise_corr12(french)
    mu = corr12.expanding(min_periods=Z_MIN_OBS).mean()
    sd = corr12.expanding(min_periods=Z_MIN_OBS).std(ddof=1)
    raw["s18"] = (corr12 - mu) / sd

    idx = french.index.union(baa.index)
    for k, v in raw.items():
        v = v.reindex(idx)
        sig[k] = pd.Series(np.where(v > 0, 1.0, -1.0), index=idx)
        sig[k][v.isna()] = np.nan
    out = pd.DataFrame(sig, index=idx)
    out.attrs["corr12"] = corr12
    return out


NAMES = {"s15": "def_cyc_relmom", "s16": "utils_mkt_relmom",
         "s17": "baa_chg3", "s18": "corr12_z"}


# ------------------------------------------------------------- evaluation --
def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def hit_rates(sigs, panel):
    g, s = panel["gde_synth"], panel["spx_tr"]
    f = lambda r: (1 + r).cumprod().shift(-12) / (1 + r).cumprod() - 1.0
    fwd_rel = f(g) - f(s)
    res = {}
    m0 = (fwd_rel.index >= EVAL_START) & fwd_rel.notna()
    base_up = float((np.sign(fwd_rel[m0]) == 1).mean())
    for name in sigs.columns:
        sg = sigs[name].reindex(fwd_rel.index)
        m = m0 & sg.notna()
        pred, actual = sg[m], np.sign(fwd_rel[m])
        n = int(m.sum())
        hr = float((pred == actual).mean())
        z = (hr - 0.5) * math.sqrt(4 * n)
        z_adj = (hr - 0.5) * math.sqrt(4 * n / 12.0)
        res[name] = {"n": n, "hit_rate": hr, "p_naive": _norm_sf(z),
                     "p_overlap_adj": _norm_sf(z_adj),
                     "killed": bool(hr <= 0.50),
                     "below_base_rate": bool(hr < base_up)}
    return res, base_up


# ------------------------------------------------------------------ rules --
def rule2_states(panel):
    g, s, b = (mom121(panel[c]) for c in ("gde_synth", "spx_tr", "bills"))
    df = pd.concat({"g": g, "s": s, "b": b}, axis=1).dropna()
    winner = np.where(df["g"] > df["s"], "gde", "spy")
    ok = np.where(winner == "gde", df["g"] > df["b"], df["s"] > df["b"])
    return pd.Series(np.where(ok, winner, "boxx"), index=df.index)


def adverse_series(sigs, survivors):
    """A21: adverse = ANY surviving signal on its risk-off side (+1).
    Defined only where ALL survivors are defined."""
    sub = sigs[survivors].dropna()
    return (sub > 0).any(axis=1)


def rule9_states(adverse):
    return pd.Series(np.where(adverse, "boxx", "gde"), index=adverse.index)


def rule10_states(r2, adverse):
    idx = r2.index.intersection(adverse.index)
    r2 = r2.reindex(idx)
    gate = adverse.reindex(idx) & (r2 == "gde")
    return pd.Series(np.where(gate, "boxx", r2), index=idx)


def bt(states, A, start_held=FULL_START, lag=1):
    """Decision month t earns month t+lag; drift-aware one-way turnover,
    5bp x turnover in the traded month; initial buy-in uncharged."""
    Av = A[["gde", "spy", "boxx"]]
    rets, tos, prev = {}, {}, None
    for t in states.index:
        h = t + lag
        if h not in Av.index or h < start_held:
            continue
        w = STATE_W[states.loc[t]]
        to = 0.0 if prev is None else 0.5 * np.abs(w - prev).sum()
        r = Av.loc[h].values
        rets[h] = float(w @ r - COST * to)
        tos[h] = float(to)
        grown = w * (1 + r)
        prev = grown / grown.sum()
    return pd.Series(rets), pd.Series(tos)


def win(r, a, b=END):
    return r[(r.index >= a) & (r.index <= b)]


def nw_t(d, lags=6):
    d = d.dropna().values
    n = len(d)
    mu = d.mean()
    e = d - mu
    s = (e * e).mean()
    for j in range(1, lags + 1):
        g = (e[j:] * e[:-j]).mean() * (n - j) / n
        s += 2 * (1 - j / (lags + 1)) * g
    return mu / math.sqrt(s / n)


# --------------------------------------------------------------- QA gates --
def compute_states(panel, french, baa, survivors):
    """Full pipeline -> (rule9 states, rule10 states, adverse, sigs).
    Single entry point so QA exercises the REAL code."""
    sigs = build_internals(french, baa)
    adv = adverse_series(sigs, survivors)
    r2 = rule2_states(panel)
    return rule9_states(adv), rule10_states(r2, adv), adv, sigs


def qa_checks(panel, french, baa, survivors, s9, s10,
              cuts=("1990-12", "2005-06", "2019-12")):
    rng = np.random.default_rng(7)
    out = {}
    for cut in cuts:
        T = pd.Period(cut, "M")
        # truncation invariance
        t9, t10, _, _ = compute_states(panel[panel.index <= T],
                                       french[french.index <= T],
                                       baa[baa.index <= T], survivors)
        trunc_ok = (t9.loc[:T].equals(s9.loc[:T].reindex(t9.loc[:T].index))
                    and len(t9.loc[:T]) == len(s9.loc[:T])
                    and t10.loc[:T].equals(s10.loc[:T].reindex(t10.loc[:T].index))
                    and len(t10.loc[:T]) == len(s10.loc[:T]))
        # future perturbation
        p_pe = panel.copy()
        fut = p_pe.index > T
        p_pe.loc[fut] = p_pe.loc[fut] * (1 + rng.normal(0, 0.5, (fut.sum(), p_pe.shape[1])))
        f_pe = french.copy()
        futf = f_pe.index > T
        f_pe.loc[futf] = f_pe.loc[futf] * (1 + rng.normal(0, 0.5, (futf.sum(), f_pe.shape[1])))
        b_pe = baa.copy()
        futb = b_pe.index > T
        b_pe.loc[futb] = b_pe.loc[futb] + rng.normal(0, 2.0, futb.sum())
        p9, p10, _, _ = compute_states(p_pe, f_pe, b_pe, survivors)
        pert_ok = (p9.loc[:T].equals(s9.loc[:T]) and p10.loc[:T].equals(s10.loc[:T]))
        out[cut] = {"truncation_invariance": bool(trunc_ok),
                    "future_perturbation_invariance": bool(pert_ok)}
        print(f"QA cut {cut}: truncation {'PASS' if trunc_ok else 'FAIL'}, "
              f"perturbation {'PASS' if pert_ok else 'FAIL'}")
    return out


# --------------------------------------------------- vectorized boot stats --
def vstats(R):
    T = R.shape[1]
    eq = np.cumprod(1 + R, axis=1)
    cagr = eq[:, -1] ** (12.0 / T) - 1
    dd = eq / np.maximum.accumulate(eq, axis=1) - 1
    maxdd = dd.min(axis=1)
    return {"CAGR": cagr, "MaxDD": maxdd, "Calmar": cagr / np.abs(maxdd),
            "Ulcer": np.sqrt(((dd * 100) ** 2).mean(axis=1))}


def vsharpe(R, RF):
    ex = R - RF
    mu = ex.mean(axis=1) * 12
    sd = ex.std(axis=1, ddof=1) * math.sqrt(12)
    ddev = np.sqrt((np.minimum(ex, 0) ** 2).mean(axis=1)) * math.sqrt(12)
    return mu / sd, mu / ddev


def sblock(st, keys=("CAGR", "Vol", "Sharpe", "Sortino", "MaxDD_m",
                     "UnderwaterMax_m", "Calmar", "Ulcer", "Worst12m")):
    return {k: float(st[k]) for k in keys}


# ------------------------------------------------------------------- main --
def main():
    panel = load_panel()
    french = load_french()
    baa = load_baa()
    rf = panel["bills"]
    A = pd.DataFrame({"gde": panel["gde_synth"], "spy": panel["spx_tr"],
                      "boxx": panel["bills"] - BOXX_DRAG / 12.0})
    out = {"amendments": "A18-A21 (see module docstring; frozen before results)"}

    # ---------------- Phase A: isolation hit rates + kill list -------------
    sigs = build_internals(french, baa)
    hr, base_up = hit_rates(sigs, panel)
    print(f"OOS eval: base rate P(GDE beats SPY next 12m) = {base_up:.1%}")
    print(f"{'signal':22s} {'N':>4s} {'hit':>6s} {'p(adj)':>7s} verdict")
    for k in ("s15", "s16", "s17", "s18"):
        h = hr[k]
        tag = "KILL" if h["killed"] else ("live<base" if h["below_base_rate"] else "live")
        print(f"{k}_{NAMES[k]:18s} {h['n']:4d} {h['hit_rate']:6.1%} "
              f"{h['p_overlap_adj']:7.2f} {tag}")
    survivors = [k for k in ("s15", "s16", "s17", "s18") if not hr[k]["killed"]]
    kill_list = [k for k in ("s15", "s16", "s17", "s18") if hr[k]["killed"]]
    out["hit_rates"] = {f"{k}_{NAMES[k]}": hr[k] for k in NAMES}
    out["base_rate_always_gde"] = base_up
    out["kill_list"] = [f"{k}_{NAMES[k]}" for k in kill_list]
    out["survivors"] = [f"{k}_{NAMES[k]}" for k in survivors]
    print(f"\nKILL LIST: {out['kill_list']}  |  survivors: {out['survivors']}")

    if not survivors:
        print("NO SIGNAL SURVIVES — per SPEC A17 the rules are NOT run.")
        with open(os.path.join(HERE, "rules_internals_results.json"), "w") as fh:
            json.dump(out, fh, default=float, indent=1)
        return

    # ---------------- Phase B: rules 9/10 ----------------------------------
    s9, s10, adverse, _ = compute_states(panel, french, baa, survivors)
    r2 = rule2_states(panel)

    qa = qa_checks(panel, french, baa, survivors, s9, s10)
    out["qa_checks"] = qa
    if not all(v["truncation_invariance"] and v["future_perturbation_invariance"]
               for v in qa.values()):
        raise SystemExit("QA FAILED — timing bug, DO NOT trust results")

    series = {"rule9_internals_exit": bt(s9, A)[0],
              "rule10_relmom_gated": bt(s10, A)[0],
              "relmom_cash": bt(r2, A)[0],
              "static_5050": bt(pd.Series("5050", index=panel.index), A)[0]}
    tos = {n: bt(s, A)[1] for n, s in
           (("rule9_internals_exit", s9), ("rule10_relmom_gated", s10))}
    bench = {"bh_gde": panel["gde_synth"], "bh_spy": panel["spx_tr"]}

    stats_tbl = {}
    for nm, r in {**series, **bench}.items():
        stats_tbl[nm] = {"full": sblock(dl.perf_stats(win(r, FULL_START), rf.reindex(win(r, FULL_START).index))),
                         "oos": sblock(dl.perf_stats(win(r, OOS_START), rf.reindex(win(r, OOS_START).index))),
                         "regimes": {}}
        for lab, a, b in REGIMES:
            w = win(r, pd.Period(a, "M"), pd.Period(b, "M"))
            stats_tbl[nm]["regimes"][lab] = sblock(dl.perf_stats(w, rf.reindex(w.index)))
        for wname in ("full", "oos"):
            if stats_tbl[nm][wname]["Sharpe"] > 1.2:
                raise SystemExit(f"TRIPWIRE Sharpe>1.2 on {nm} {wname} — STOP AND AUDIT")
    out["stats"] = stats_tbl

    # %GDE, gross notional, turnover by decade, switch counts
    meta = {}
    for nm, s in (("rule9_internals_exit", s9), ("rule10_relmom_gated", s10),
                  ("relmom_cash", r2)):
        dec = s[(s.index >= FULL_START - 1) & (s.index <= END - 1)]
        deco = s[(s.index >= OOS_START - 1) & (s.index <= END - 1)]
        gross = deco.map({"gde": 1.8, "spy": 1.0, "boxx": 0.0})
        sw = (s != s.shift(1)) & s.shift(1).notna()
        dec_to = {}
        if nm in tos:
            for y0 in range(1980, 2030, 10):
                mask = (tos[nm].index >= pd.Period(f"{y0}-01", "M")) & \
                       (tos[nm].index <= pd.Period(f"{min(y0+9,2026)}-12", "M"))
                if mask.sum() >= 12:
                    dec_to[f"{y0}s"] = float(tos[nm][mask].sum() / (mask.sum() / 12.0))
        meta[nm] = {"pct_gde_oos": float((deco == "gde").mean()),
                    "pct_boxx_oos": float((deco == "boxx").mean()),
                    "avg_gross_notional_oos": float(gross.mean()),
                    "switches_oos": int(sw[(sw.index >= OOS_START - 1)].sum()),
                    "turnover_per_yr_by_decade": dec_to}
    out["meta"] = meta
    out["adverse_share_oos"] = float(
        adverse[(adverse.index >= OOS_START - 1) & (adverse.index <= END - 1)].mean())

    # deltas vs null / vs relmom / vs SPY (Q2 columns)
    comps = {}
    for nm in ("rule9_internals_exit", "rule10_relmom_gated"):
        c = {}
        for bnm, key in (("static_5050", "vs_null"), ("relmom_cash", "vs_relmom")):
            d = (series[nm] - series[bnm]).dropna()
            c[key] = {w: {"dCAGR": stats_tbl[nm][w]["CAGR"] - stats_tbl[bnm][w]["CAGR"],
                          "dMaxDD": stats_tbl[nm][w]["MaxDD_m"] - stats_tbl[bnm][w]["MaxDD_m"],
                          "dCalmar": stats_tbl[nm][w]["Calmar"] - stats_tbl[bnm][w]["Calmar"],
                          "dUlcer": stats_tbl[nm][w]["Ulcer"] - stats_tbl[bnm][w]["Ulcer"],
                          "dSortino": stats_tbl[nm][w]["Sortino"] - stats_tbl[bnm][w]["Sortino"]}
                      for w in ("full", "oos")}
            c[key]["nw_t_oos"] = nw_t(d[d.index >= OOS_START])
        s, b = stats_tbl[nm]["oos"], stats_tbl["bh_spy"]["oos"]
        c["vs_spy_oos"] = {"dCAGR": s["CAGR"] - b["CAGR"], "dMaxDD": s["MaxDD_m"] - b["MaxDD_m"],
                           "dCalmar": s["Calmar"] - b["Calmar"], "dSharpe": s["Sharpe"] - b["Sharpe"],
                           "dSortino": s["Sortino"] - b["Sortino"],
                           "dominates_raw": bool(s["CAGR"] >= b["CAGR"] and s["MaxDD_m"] > b["MaxDD_m"]
                                                 and s["Calmar"] > b["Calmar"] and s["Sortino"] > b["Sortino"])}
        comps[nm] = c
    out["comparisons"] = comps

    print("\n==== OOS master table (1990-02 -> 2026-07) ====")
    hdr = f"{'portfolio':22s} {'CAGR':>7s} {'Vol':>6s} {'Sharpe':>6s} {'Sortino':>7s} {'MaxDD':>7s} {'UW':>4s} {'Calmar':>6s} {'Ulcer':>6s} {'Worst12':>8s}"
    print(hdr)
    for nm in ("bh_gde", "bh_spy", "static_5050", "relmom_cash",
               "rule9_internals_exit", "rule10_relmom_gated"):
        s = stats_tbl[nm]["oos"]
        print(f"{nm:22s} {s['CAGR']:7.2%} {s['Vol']:6.2%} {s['Sharpe']:6.2f} "
              f"{s['Sortino']:7.2f} {s['MaxDD_m']:7.1%} {s['UnderwaterMax_m']:4.0f} "
              f"{s['Calmar']:6.2f} {s['Ulcer']:6.1f} {s['Worst12m']:8.1%}")

    # ---------------- Phase C: referee battery -----------------------------
    # (1) one-month lag stress (decision t earns t+2)
    print("\n==== one-month lag stress ====")
    lagres = {}
    lag_series = {"rule9_internals_exit": bt(s9, A, lag=2)[0],
                  "rule10_relmom_gated": bt(s10, A, lag=2)[0],
                  "relmom_cash": bt(r2, A, lag=2)[0],
                  "static_5050": series["static_5050"]}
    for nm, r in lag_series.items():
        st = dl.perf_stats(win(r, OOS_START), rf.reindex(win(r, OOS_START).index))
        base = stats_tbl[nm]["oos"]
        lagres[nm] = {"lagged": sblock(st),
                      "dCAGR": st["CAGR"] - base["CAGR"],
                      "dMaxDD": st["MaxDD_m"] - base["MaxDD_m"],
                      "dCalmar": st["Calmar"] - base["Calmar"]}
        print(f"{nm:22s} lagged {st['CAGR']:6.2%}/{st['MaxDD_m']:6.1%}/C{st['Calmar']:5.2f} "
              f"(d {lagres[nm]['dCAGR']:+.2%}/{lagres[nm]['dMaxDD']:+.1%}/{lagres[nm]['dCalmar']:+.2f})")
    out["lag_stress"] = lagres
    # Oct-2008 autopsy under lag: what is held in 2008-10?
    oct08 = pd.Period("2008-10", "M")
    aug08, sep08 = pd.Period("2008-08", "M"), pd.Period("2008-09", "M")
    out["oct2008_autopsy"] = {
        "adverse_2008_08": bool(adverse.loc[aug08]),
        "adverse_2008_09": bool(adverse.loc[sep08]),
        "signals_2008_08": {f"{k}_{NAMES[k]}": float(sigs[k].loc[aug08]) for k in NAMES},
        "ontime_hold_oct08": {"relmom": r2.loc[sep08], "rule9": s9.loc[sep08],
                              "rule10": s10.loc[sep08]},
        "lagged_hold_oct08": {"relmom": r2.loc[aug08], "rule9": s9.loc[aug08],
                              "rule10": s10.loc[aug08]},
        "gde_synth_2008_10": float(panel["gde_synth"].loc[oct08])}
    print("Oct-2008 lagged holdings (decision 2008-08):", out["oct2008_autopsy"]["lagged_hold_oct08"])

    # (2) start-date grid
    print("\n==== start-date grid (Jan Y -> 2026-07): dCalmar ====")
    sd = {}
    for y in range(1990, 2016):
        a = pd.Period(f"{y}-01", "M")
        cal = {nm: dl.perf_stats(win(series[nm], a), rf.reindex(win(series[nm], a).index))["Calmar"]
               for nm in series}
        sd[y] = {"calmar": cal,
                 "d9_null": cal["rule9_internals_exit"] - cal["static_5050"],
                 "d10_null": cal["rule10_relmom_gated"] - cal["static_5050"],
                 "d9_relmom": cal["rule9_internals_exit"] - cal["relmom_cash"],
                 "d10_relmom": cal["rule10_relmom_gated"] - cal["relmom_cash"]}
    out["start_date"] = sd
    out["start_date_summary"] = {
        k: {"min": min(v[k] for v in sd.values()), "max": max(v[k] for v in sd.values()),
            "n_neg": sum(1 for v in sd.values() if v[k] <= 0)}
        for k in ("d9_null", "d10_null", "d9_relmom", "d10_relmom")}
    for k, v in out["start_date_summary"].items():
        print(f"{k}: min {v['min']:+.2f} max {v['max']:+.2f} n<=0: {v['n_neg']}/26")

    # (3) drop-single-year
    print("\n==== drop-single-year (OOS) ====")
    dy = {}
    for Y in range(1990, 2027):
        row = {}
        for nm in series:
            r = win(series[nm], OOS_START)
            r = r[r.index.year != Y]
            st = dl.perf_stats(r, rf.reindex(r.index))
            row[nm] = {"CAGR": st["CAGR"], "MaxDD": st["MaxDD_m"], "Calmar": st["Calmar"]}
        row["d9_null"] = row["rule9_internals_exit"]["Calmar"] - row["static_5050"]["Calmar"]
        row["d10_null"] = row["rule10_relmom_gated"]["Calmar"] - row["static_5050"]["Calmar"]
        row["d10_relmom"] = row["rule10_relmom_gated"]["Calmar"] - row["relmom_cash"]["Calmar"]
        dy[Y] = row
    out["drop_year"] = dy
    out["drop_year_summary"] = {
        k: {"min": min(v[k] for v in dy.values()),
            "worst_year": min(dy, key=lambda y: dy[y][k]),
            "n_neg": sum(1 for v in dy.values() if v[k] <= 0)}
        for k in ("d9_null", "d10_null", "d10_relmom")}
    for k, v in out["drop_year_summary"].items():
        print(f"{k}: min {v['min']:+.2f} (drop {v['worst_year']}), n<=0: {v['n_neg']}/37")

    # (4) circular block bootstrap vs null AND vs relmom_cash
    print(f"\n==== block bootstrap ({N_BOOT} draws, {BLOCK}m blocks, OOS) ====")
    M = pd.DataFrame({nm: win(series[nm], OOS_START) for nm in series})
    M["rf"] = rf.reindex(M.index)
    Mv, T = M.values, len(M)
    nblk = math.ceil(T / BLOCK)
    starts = RNG.integers(0, T, size=(N_BOOT, nblk))
    idx = ((starts[:, :, None] + np.arange(BLOCK)[None, None, :]) % T).reshape(N_BOOT, -1)[:, :T]
    boots = {c: Mv[:, i][idx] for i, c in enumerate(M.columns)}
    bs = {}
    for nm in series:
        v = vstats(boots[nm])
        sh, so = vsharpe(boots[nm], boots["rf"])
        bs[nm] = {**v, "Sharpe": sh, "Sortino": so}
    KEY = {"MaxDD": "MaxDD_m"}
    boot = {}
    for nm in ("rule9_internals_exit", "rule10_relmom_gated"):
        row = {}
        for bench_nm in ("static_5050", "relmom_cash"):
            for met, hi in (("Calmar", True), ("Ulcer", False), ("CAGR", True),
                            ("MaxDD", True), ("Sharpe", True), ("Sortino", True)):
                d = bs[nm][met] - bs[bench_nm][met] if met in bs[nm] else None
                if d is None:
                    continue
                p = float((d <= 0).mean()) if hi else float((d >= 0).mean())
                row[f"{met}_vs_{bench_nm}"] = {
                    "point": stats_tbl[nm]["oos"][KEY.get(met, met)]
                             - stats_tbl[bench_nm]["oos"][KEY.get(met, met)],
                    "ci90": [float(np.percentile(d, 5)), float(np.percentile(d, 95))],
                    "p_one_sided": p, "p_x2": min(1.0, p * 2),
                    "p_x10": min(1.0, p * 10), "p_x28": min(1.0, p * 28)}
        boot[nm] = row
    out["bootstrap"] = boot
    for nm in boot:
        for met in ("Calmar", "Ulcer"):
            for b in ("static_5050", "relmom_cash"):
                r0 = boot[nm][f"{met}_vs_{b}"]
                print(f"{nm:22s} d{met} vs {b:12s}: point {r0['point']:+.2f} "
                      f"CI90 [{r0['ci90'][0]:+.2f},{r0['ci90'][1]:+.2f}] "
                      f"p {r0['p_one_sided']:.3f} x2 {r0['p_x2']:.3f} "
                      f"x10 {r0['p_x10']:.3f} x28 {r0['p_x28']:.3f}")

    out["family_note"] = ("multiple-testing family after A17: 26 tested variants "
                          "(14 P2 signals + 4 P3 rules + 4 A12 exits + 4 A17 "
                          "signals) + 2 A17 rules = 28; adjustments reported "
                          "x2 (A17 rules), x10 (rule-level candidates), x28 (full family)")

    # series + states for charts / archive
    out["monthly_returns"] = {n: {str(k): float(v) for k, v in r.items()}
                              for n, r in series.items()}
    out["monthly_returns_lagged"] = {n: {str(k): float(v) for k, v in r.items()}
                                     for n, r in lag_series.items() if n != "static_5050"}
    out["states"] = {"rule9": {str(k): v for k, v in s9.items()},
                     "rule10": {str(k): v for k, v in s10.items()},
                     "adverse": {str(k): bool(v) for k, v in adverse.items()}}
    out["signal_series"] = {f"{k}_{NAMES[k]}": {str(i): (None if pd.isna(v) else float(v))
                                                for i, v in sigs[k].items()}
                            for k in NAMES}

    with open(os.path.join(HERE, "rules_internals_results.json"), "w") as fh:
        json.dump(out, fh, default=float, indent=1)
    print("\nwrote rules_internals_results.json")


if __name__ == "__main__":
    main()
