#!/usr/bin/env python3
"""Phase 4 — ADVERSARIAL referee battery (independent reimplementation).

Referee discipline: nothing here imports datalib/signals/rules. All series are
recomputed from the frozen panel_monthly.json with fresh code; the builder's
rules_results.json is used ONLY as the object under audit (its stored states /
monthly returns are compared against, never trusted). Battery per frozen
SPEC.md Phase 4: start-date sensitivity, drop-single-year, signal-noise flips
(15%/30% x 2000), bootstrap CIs vs the 50/50 null AND vs SPY (A5), 1-month lag
stress, oracle gap, plus a timestamp/alignment audit and the pessimistic
pre-2007 carry variant. Output: qa_results.json + printed tables.
"""
import json
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BOXX_DRAG = 0.0005          # BOXX = bills - 5bp/yr
COST = 0.0005               # 5bp per full one-way switch
OOS = pd.Period("1990-02", "M")     # first HELD month of the verdict window
FULL = pd.Period("1977-02", "M")
END = pd.Period("2026-07", "M")
N_BOOT, BLOCK = 4000, 24
N_NOISE = 2000
RNG = np.random.default_rng(20260812)

STATE_I = {"gde": 0, "spy": 1, "boxx": 2, "5050": 3}
WMAT = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.5, 0.5, 0]], dtype=float)


# ------------------------------------------------------------------ loaders --
def load_panel():
    j = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]
    df = pd.DataFrame.from_dict(j, orient="index").astype(float)
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df.sort_index()


def load_builder():
    return json.load(open(os.path.join(HERE, "rules_results.json")))


# -------------------------------------------------------------- my stats -----
def stats(r, rf):
    """Same stated conventions as the brief (recoded from scratch):
    geometric CAGR; vol = std(m)*sqrt12; Sharpe = mean excess *12 / std(excess)
    *sqrt12; Sortino MAR=rf full-sample downside denominator; maxDD/underwater/
    Calmar/Ulcer on month-end curve; worst rolling 12m."""
    r = r.dropna()
    rf = rf.reindex(r.index)
    ex = r - rf
    n = len(r)
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (12.0 / n) - 1
    vol = r.std(ddof=1) * math.sqrt(12)
    sharpe = ex.mean() * 12 / (ex.std(ddof=1) * math.sqrt(12))
    ddev = math.sqrt((np.minimum(ex, 0) ** 2).mean()) * math.sqrt(12)
    sortino = ex.mean() * 12 / ddev if ddev > 0 else np.nan
    dd = eq / eq.cummax() - 1
    maxdd = dd.min()
    uw, longest, cur = dd < -1e-12, 0, 0
    for f in uw:
        cur = cur + 1 if f else 0
        longest = max(longest, cur)
    calmar = cagr / abs(maxdd) if maxdd < 0 else np.nan
    ulcer = math.sqrt(((dd * 100) ** 2).mean())
    worst12 = ((1 + r).rolling(12).apply(np.prod, raw=True) - 1).min()
    return {"months": n, "CAGR": cagr, "Vol": vol, "Sharpe": sharpe,
            "Sortino": sortino, "MaxDD": maxdd, "UW": longest,
            "Calmar": calmar, "Ulcer": ulcer, "Worst12m": worst12}


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


# ------------------------------------------------- my rule-2 implementation --
def mom121(x):
    c = (1 + x).cumprod()
    return c.shift(1) / c.shift(12) - 1     # months t-11..t-1, skip month t


def rule2_states(panel):
    g, s, b = (mom121(panel[c]) for c in ("gde_synth", "spx_tr", "bills"))
    df = pd.concat({"g": g, "s": s, "b": b}, axis=1).dropna()
    winner = np.where(df["g"] > df["s"], "gde", "spy")
    ok = np.where(winner == "gde", df["g"] > df["b"], df["s"] > df["b"])
    return pd.Series(np.where(ok, winner, "boxx"), index=df.index)


def bt(states_or_w, A, start_held=FULL, lag=1):
    """Decision month t earns month t+lag. Drift-aware one-way turnover,
    5bp x turnover in the traded month; first buy-in uncharged."""
    rets, prev = {}, None
    isw = isinstance(states_or_w, pd.DataFrame)
    Av = A[["gde", "spy", "boxx"]]
    for t in states_or_w.index:
        h = t + lag
        if h not in Av.index or h < start_held:
            continue
        w = (states_or_w.loc[t].values if isw
             else WMAT[STATE_I[states_or_w.loc[t]]])
        to = 0.0 if prev is None else 0.5 * np.abs(w - prev).sum()
        r = Av.loc[h].values
        rets[h] = float(w @ r - COST * to)
        grown = w * (1 + r)
        prev = grown / grown.sum()
    return pd.Series(rets)


# ------------------------------------------------------- vectorized helpers --
def vstats(R):
    """R: (n, T) matrix of monthly returns -> dict of vectors (CAGR, MaxDD,
    Calmar, Ulcer)."""
    T = R.shape[1]
    eq = np.cumprod(1 + R, axis=1)
    cagr = eq[:, -1] ** (12.0 / T) - 1
    peak = np.maximum.accumulate(eq, axis=1)
    dd = eq / peak - 1
    maxdd = dd.min(axis=1)
    calmar = cagr / np.abs(maxdd)
    ulcer = np.sqrt(((dd * 100) ** 2).mean(axis=1))
    return {"CAGR": cagr, "MaxDD": maxdd, "Calmar": calmar, "Ulcer": ulcer}


def vsharpe(R, RF):
    ex = R - RF
    mu = ex.mean(axis=1) * 12
    sd = ex.std(axis=1, ddof=1) * math.sqrt(12)
    ddev = np.sqrt((np.minimum(ex, 0) ** 2).mean(axis=1)) * math.sqrt(12)
    return mu / sd, mu / ddev


def main():
    panel = load_panel()
    B = load_builder()
    rf = panel["bills"]
    A = pd.DataFrame({"gde": panel["gde_synth"], "spy": panel["spx_tr"],
                      "boxx": panel["bills"] - BOXX_DRAG / 12.0})
    out = {}

    # ================= (7) TIMESTAMP / ALIGNMENT AUDIT =======================
    my_st2 = rule2_states(panel)
    b_st2 = pd.Series(B["states"]["rule2"])
    b_st2.index = pd.PeriodIndex(b_st2.index, freq="M")
    common = my_st2.index.intersection(b_st2.index)
    mism = (my_st2.reindex(common) != b_st2.reindex(common))
    print(f"[audit] rule2 state months compared: {len(common)}, "
          f"mismatches: {int(mism.sum())}")
    if mism.sum():
        print(my_st2[common][mism].head(20), b_st2[common][mism].head(20))

    my_r2 = bt(my_st2, A)
    b_r2 = pd.Series(B["monthly_returns"]["relmom_cash"], dtype=float)
    b_r2.index = pd.PeriodIndex(b_r2.index, freq="M")
    dj = (my_r2 - b_r2.reindex(my_r2.index)).abs()
    print(f"[audit] relmom_cash return series: {len(my_r2)} months, "
          f"max |diff| = {dj.max():.2e}, months >1e-10: {(dj > 1e-10).sum()}")

    # recompute all five rules with my engine (builder states for 3/4/5)
    my = {"relmom_cash": my_r2}
    my["static_5050"] = bt(pd.Series("5050", index=panel.index), A)
    for nm, col in (("realrate_gate", "rule3"), ("composite", "rule4")):
        s = pd.Series(B["states"][col])
        s.index = pd.PeriodIndex(s.index, freq="M")
        my[nm] = bt(s, A)
    lam = pd.Series(B["lam_series"], dtype=float)
    lam.index = pd.PeriodIndex(lam.index, freq="M")
    s4 = pd.Series(B["states"]["rule4"])
    s4.index = pd.PeriodIndex(s4.index, freq="M")
    W4 = pd.DataFrame([WMAT[STATE_I[x]] for x in s4], index=s4.index,
                      columns=["gde", "spy", "boxx"])
    W5 = W4.mul(lam.reindex(W4.index), axis=0)
    W5["boxx"] += 1 - lam.reindex(W4.index)
    my["voltarget_15"] = bt(W5.dropna(), A)
    audit = {}
    for nm in my:
        bser = pd.Series(B["monthly_returns"][nm], dtype=float)
        bser.index = pd.PeriodIndex(bser.index, freq="M")
        d = (my[nm] - bser.reindex(my[nm].index)).abs()
        audit[nm] = {"max_abs_diff": float(d.max()),
                     "n_months_gt_1e-10": int((d > 1e-10).sum())}
        print(f"[audit] {nm:14s} max|diff| {d.max():.2e}")
    out["audit"] = audit
    out["audit"]["rule2_state_mismatches"] = int(mism.sum())

    # lookahead cheat diagnostic: decision t earns t (leak) — how big a leak
    cheat = stats(win(bt(my_st2, A, lag=0), OOS), rf)
    honest = stats(win(my_r2, OOS), rf)
    print(f"[audit] leak diagnostic: honest CAGR {honest['CAGR']:.2%} vs "
          f"same-month-execution (leaked) {cheat['CAGR']:.2%}")
    out["audit"]["leak_diagnostic"] = {"honest_CAGR": honest["CAGR"],
                                       "cheat_lag0_CAGR": cheat["CAGR"]}

    # headline verification (my stats code, my series)
    spy_r, gde_r = panel["spx_tr"], panel["gde_synth"]
    heads = {}
    for nm, r in {**my, "bh_spy": spy_r, "bh_gde": gde_r}.items():
        heads[nm] = {"oos": stats(win(r, OOS), rf), "full": stats(win(r, FULL), rf)}
    out["headline_recompute"] = heads
    print("\n[verify] OOS headline (mine): " + "; ".join(
        f"{nm} {v['oos']['CAGR']:.2%}/{v['oos']['MaxDD']:.1%}/{v['oos']['Calmar']:.2f}"
        for nm, v in heads.items()))
    d_oos = (my["relmom_cash"] - my["static_5050"]).dropna()
    out["nw_t_rule2_vs_null_oos"] = nw_t(d_oos[d_oos.index >= OOS])
    print(f"[verify] NW-t rule2-null OOS: {out['nw_t_rule2_vs_null_oos']:.2f}")
    gross = pd.Series(np.where(my_st2 == "gde", 1.8,
                      np.where(my_st2 == "spy", 1.0, 0.0)), index=my_st2.index)
    out["rule2_avg_gross_oos"] = float(gross[gross.index >= OOS - 1].mean())
    print(f"[verify] rule2 avg gross notional OOS: {out['rule2_avg_gross_oos']:.2f}x")

    # drawdown episode geography (is the DD edge 1-2 episodes?)
    def dd_top(r, k=4):
        eq = (1 + r).cumprod()
        dd = eq / eq.cummax() - 1
        eps, in_dd, t0, mn, tmn = [], False, None, 0, None
        for t, v in dd.items():
            if v < -1e-12 and not in_dd:
                in_dd, t0, mn, tmn = True, t, v, t
            elif in_dd:
                if v < mn:
                    mn, tmn = v, t
                if v >= -1e-12:
                    eps.append((mn, str(t0), str(tmn)))
                    in_dd = False
        if in_dd:
            eps.append((mn, str(t0), str(tmn)))
        return sorted(eps)[:k]
    out["dd_episodes"] = {nm: dd_top(win(my[nm], OOS))
                          for nm in ("relmom_cash", "static_5050")}
    out["dd_episodes"]["bh_spy"] = dd_top(win(spy_r, OOS))
    for nm, eps in out["dd_episodes"].items():
        print(f"[dd] {nm}: " + "; ".join(f"{e[0]:.1%} ({e[1]}->{e[2]})" for e in eps))

    # ==================== (1) START-DATE SENSITIVITY =========================
    print("\n==== start-date sensitivity (start Jan Y -> 2026-07) ====")
    sd = {}
    for y in range(1990, 2016):
        a = pd.Period(f"{y}-01", "M")
        row = {}
        for nm in ("relmom_cash", "static_5050"):
            st = stats(win(my[nm], a), rf)
            row[nm] = {k: st[k] for k in ("CAGR", "MaxDD", "Calmar")}
        row["spy"] = {k: stats(win(spy_r, a), rf)[k]
                      for k in ("CAGR", "MaxDD", "Calmar")}
        row["dCalmar_rule2_null"] = (row["relmom_cash"]["Calmar"]
                                     - row["static_5050"]["Calmar"])
        row["dCalmar_rule2_spy"] = row["relmom_cash"]["Calmar"] - row["spy"]["Calmar"]
        sd[y] = row
        print(f"{y}: r2 {row['relmom_cash']['CAGR']:6.2%} {row['relmom_cash']['MaxDD']:6.1%} "
              f"C{row['relmom_cash']['Calmar']:5.2f} | null C{row['static_5050']['Calmar']:5.2f} "
              f"| dC(null) {row['dCalmar_rule2_null']:+5.2f} dC(spy) {row['dCalmar_rule2_spy']:+5.2f}")
    out["start_date"] = sd
    dcs = [v["dCalmar_rule2_null"] for v in sd.values()]
    out["start_date_summary"] = {
        "rule2_CAGR_min_max": [min(v["relmom_cash"]["CAGR"] for v in sd.values()),
                               max(v["relmom_cash"]["CAGR"] for v in sd.values())],
        "rule2_MaxDD_min_max": [min(v["relmom_cash"]["MaxDD"] for v in sd.values()),
                                max(v["relmom_cash"]["MaxDD"] for v in sd.values())],
        "rule2_Calmar_min_max": [min(v["relmom_cash"]["Calmar"] for v in sd.values()),
                                 max(v["relmom_cash"]["Calmar"] for v in sd.values())],
        "dCalmar_vs_null_min": min(dcs), "dCalmar_vs_null_max": max(dcs),
        "n_starts_dCalmar_neg": sum(1 for x in dcs if x <= 0),
        "dCalmar_vs_spy_min": min(v["dCalmar_rule2_spy"] for v in sd.values())}

    # ======================= (2) DROP-SINGLE-YEAR ============================
    print("\n==== drop-single-year (OOS) ====")
    dy = {}
    for Y in range(1990, 2027):
        row = {}
        for nm in ("relmom_cash", "static_5050"):
            r = win(my[nm], OOS)
            r = r[r.index.year != Y]
            st = stats(r, rf)
            row[nm] = {k: st[k] for k in ("CAGR", "MaxDD", "Calmar")}
        rs = win(spy_r, OOS)
        row["spy"] = {k: stats(rs[rs.index.year != Y], rf)[k]
                      for k in ("CAGR", "MaxDD", "Calmar")}
        row["dMaxDD_rule2_null"] = row["relmom_cash"]["MaxDD"] - row["static_5050"]["MaxDD"]
        row["dCalmar_rule2_null"] = row["relmom_cash"]["Calmar"] - row["static_5050"]["Calmar"]
        dy[Y] = row
    out["drop_year"] = dy
    worstY = min(dy, key=lambda y: dy[y]["dCalmar_rule2_null"])
    out["drop_year_summary"] = {
        "min_dMaxDD": min(v["dMaxDD_rule2_null"] for v in dy.values()),
        "min_dCalmar": dy[worstY]["dCalmar_rule2_null"], "worst_year": worstY,
        "n_years_dCalmar_neg": sum(1 for v in dy.values()
                                   if v["dCalmar_rule2_null"] <= 0)}
    for Y in (2001, 2008, 2020, 2022, worstY):
        v = dy[Y]
        print(f"drop {Y}: r2 {v['relmom_cash']['CAGR']:6.2%}/{v['relmom_cash']['MaxDD']:6.1%}"
              f"/C{v['relmom_cash']['Calmar']:5.2f}  null {v['static_5050']['CAGR']:6.2%}/"
              f"{v['static_5050']['MaxDD']:6.1%}/C{v['static_5050']['Calmar']:5.2f}  "
              f"dDD {v['dMaxDD_rule2_null']:+5.1%} dC {v['dCalmar_rule2_null']:+5.2f}")

    # Q2 full-window drop-1979 / drop-2008 (GDE CAGR edge provenance)
    q2 = {}
    for tag, Y in (("none", None), ("1979", 1979), ("2008", 2008)):
        row = {}
        for nm, r in (("relmom_cash", my["relmom_cash"]),
                      ("static_5050", my["static_5050"]),
                      ("bh_gde", gde_r), ("bh_spy", spy_r)):
            rr = win(r, FULL)
            if Y:
                rr = rr[rr.index.year != Y]
            st = stats(rr, rf)
            row[nm] = {k: st[k] for k in ("CAGR", "MaxDD", "Calmar", "Sortino", "Sharpe")}
        for nm in ("relmom_cash", "static_5050", "bh_gde"):
            row[nm]["dCAGR_vs_spy"] = row[nm]["CAGR"] - row["bh_spy"]["CAGR"]
        q2[tag] = row
        print(f"[Q2 full-window drop {tag}] dCAGR vs SPY: " + ", ".join(
            f"{nm} {row[nm]['dCAGR_vs_spy']:+.2%}" for nm in
            ("relmom_cash", "static_5050", "bh_gde")))
    out["q2_drop"] = q2

    # ===================== (3) SIGNAL-NOISE FLIPS ============================
    print("\n==== signal-noise (state flipped to a random other state) ====")
    noise = {}
    dec0 = pd.Period("1990-01", "M")            # decisions that earn OOS months
    for nm, scol in (("relmom_cash", None), ("realrate_gate", "rule3"),
                     ("composite", "rule4")):
        if scol is None:
            st_full = my_st2
        else:
            st_full = pd.Series(B["states"][scol])
            st_full.index = pd.PeriodIndex(st_full.index, freq="M")
        st_full = st_full[st_full.index <= pd.Period("2026-06", "M")]
        dec = st_full[st_full.index >= dec0]
        si = np.array([STATE_I[x] for x in dec])
        Tn = len(si)
        held = dec.index + 1
        R = A.loc[held].values                          # (T,3)
        RFv = rf.loc[held].values
        prev0 = STATE_I[st_full.loc[dec0 - 1]]
        base_null = stats(win(my["static_5050"], OOS), rf)
        res = {}
        for p in (0.15, 0.30):
            flip = RNG.random((N_NOISE, Tn)) < p
            alt = (si[None, :] + 1 + (RNG.random((N_NOISE, Tn)) *
                   (2 if nm != "composite" else 3)).astype(int)) % (3 if nm != "composite" else 4)
            # for 3-state rules alt in other 2 states; composite has 4 states
            S = np.where(flip, alt, si[None, :])
            Wn = WMAT[S]                                # (n,T,3)
            rets = np.einsum("ntk,tk->nt", Wn, R)
            wprev = np.concatenate([np.repeat(WMAT[prev0][None, None, :],
                                              N_NOISE, axis=0), Wn[:, :-1]], axis=1)
            to = 0.5 * np.abs(Wn - wprev).sum(axis=2)
            rets = rets - COST * to
            vs = vstats(rets)
            res[f"p{int(p*100)}"] = {
                "median_CAGR": float(np.median(vs["CAGR"])),
                "p10_CAGR": float(np.percentile(vs["CAGR"], 10)),
                "median_MaxDD": float(np.median(vs["MaxDD"])),
                "p10_MaxDD": float(np.percentile(vs["MaxDD"], 10)),
                "median_Calmar": float(np.median(vs["Calmar"])),
                "p10_Calmar": float(np.percentile(vs["Calmar"], 10)),
                "frac_Calmar_gt_null": float((vs["Calmar"] >
                                              base_null["Calmar"]).mean()),
                "frac_MaxDD_shallower_null": float((vs["MaxDD"] >
                                                    base_null["MaxDD"]).mean())}
            print(f"{nm:14s} p={p:.0%}: med CAGR {res[f'p{int(p*100)}']['median_CAGR']:.2%} "
                  f"p10 {res[f'p{int(p*100)}']['p10_CAGR']:.2%}; med DD "
                  f"{res[f'p{int(p*100)}']['median_MaxDD']:.1%} p10 "
                  f"{res[f'p{int(p*100)}']['p10_MaxDD']:.1%}; med Calmar "
                  f"{res[f'p{int(p*100)}']['median_Calmar']:.2f}; "
                  f"P(Calmar>null) {res[f'p{int(p*100)}']['frac_Calmar_gt_null']:.0%}")
        noise[nm] = res
    out["signal_noise"] = noise

    # ===================== (4) ONE-MONTH LAG STRESS ==========================
    print("\n==== one-month lag stress (decision t earns t+2) ====")
    lagres = {}
    lag_series = {"relmom_cash": bt(my_st2, A, lag=2),
                  "static_5050": bt(pd.Series("5050", index=panel.index), A, lag=2)}
    for nm, col in (("realrate_gate", "rule3"), ("composite", "rule4")):
        s = pd.Series(B["states"][col])
        s.index = pd.PeriodIndex(s.index, freq="M")
        lag_series[nm] = bt(s, A, lag=2)
    lag_series["voltarget_15"] = bt(W5.dropna(), A, lag=2)
    for nm, r in lag_series.items():
        st = stats(win(r, OOS), rf)
        base = heads[nm]["oos"]
        lagres[nm] = {"lagged": {k: st[k] for k in
                                 ("CAGR", "MaxDD", "Calmar", "Sharpe", "Ulcer")},
                      "dCAGR": st["CAGR"] - base["CAGR"],
                      "dMaxDD": st["MaxDD"] - base["MaxDD"],
                      "dCalmar": st["Calmar"] - base["Calmar"]}
        print(f"{nm:14s} lagged {st['CAGR']:6.2%}/{st['MaxDD']:6.1%}/C{st['Calmar']:5.2f}"
              f"  (d vs unlagged: {lagres[nm]['dCAGR']:+.2%} CAGR,"
              f" {lagres[nm]['dMaxDD']:+.1%} DD, {lagres[nm]['dCalmar']:+.2f} Calmar)")
    out["lag_stress"] = lagres

    # ===================== (5) BLOCK BOOTSTRAP ===============================
    print(f"\n==== circular block bootstrap ({N_BOOT} draws, {BLOCK}m blocks, OOS) ====")
    names = ["relmom_cash", "composite", "voltarget_15", "realrate_gate"]
    M = pd.DataFrame({nm: win(my[nm], OOS) for nm in
                      names + ["static_5050"]})
    M["spy"] = win(spy_r, OOS)
    M["rf"] = rf.reindex(M.index)
    Mv = M.values
    T = len(M)
    nblk = math.ceil(T / BLOCK)
    starts = RNG.integers(0, T, size=(N_BOOT, nblk))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]) % T
    idx = idx.reshape(N_BOOT, -1)[:, :T]
    boots = {c: Mv[:, i][idx] for i, c in enumerate(M.columns)}
    RFb = boots["rf"]
    bs = {}
    for nm in names + ["static_5050", "spy"]:
        v = vstats(boots[nm])
        sh, so = vsharpe(boots[nm], RFb)
        bs[nm] = {**v, "Sharpe": sh, "Sortino": so}
    boot = {}
    for nm in names:
        row = {}
        for bench in ("static_5050", "spy"):
            for met, better_hi in (("Calmar", True), ("Ulcer", False),
                                   ("Sharpe", True), ("Sortino", True),
                                   ("CAGR", True), ("MaxDD", True)):
                d = bs[nm][met] - bs[bench][met]
                p = float((d <= 0).mean()) if better_hi else float((d >= 0).mean())
                row[f"{met}_vs_{bench}"] = {
                    "point": float(heads[nm]["oos"][met] -
                                   heads["bh_spy" if bench == "spy" else bench]["oos"][met]),
                    "ci90": [float(np.percentile(d, 5)), float(np.percentile(d, 95))],
                    "p_one_sided": p, "p_x4": min(1.0, p * 4),
                    "p_x18": min(1.0, p * 18)}
        boot[nm] = row
    out["bootstrap"] = boot
    for nm in names:
        for met in ("Calmar", "Ulcer", "Sharpe"):
            r0 = boot[nm][f"{met}_vs_static_5050"]
            print(f"{nm:14s} d{met} vs null: point {r0['point']:+.2f} "
                  f"CI90 [{r0['ci90'][0]:+.2f},{r0['ci90'][1]:+.2f}] "
                  f"p {r0['p_one_sided']:.4f} x4 {r0['p_x4']:.3f} x18 {r0['p_x18']:.3f}")
    for met in ("Sharpe", "Sortino", "Calmar", "CAGR", "MaxDD"):
        r0 = boot["relmom_cash"][f"{met}_vs_spy"]
        print(f"relmom vs SPY d{met}: point {r0['point']:+.3f} "
              f"CI90 [{r0['ci90'][0]:+.3f},{r0['ci90'][1]:+.3f}] p {r0['p_one_sided']:.4f}"
              f" x4 {r0['p_x4']:.3f}")

    # ===================== (6) ORACLE GAP ====================================
    best = A[["gde", "spy", "boxx"]].idxmax(axis=1)     # held-month best sleeve
    orc_states = pd.Series(best.values, index=best.index - 1)  # decided at t-1
    orc = bt(orc_states, A)
    orc_oos = stats(win(orc, OOS), rf)
    null_oos = heads["static_5050"]["oos"]
    cap = {nm: (heads[nm]["oos"]["CAGR"] - null_oos["CAGR"]) /
               (orc_oos["CAGR"] - null_oos["CAGR"])
           for nm in ("relmom_cash", "composite", "voltarget_15", "realrate_gate")}
    out["oracle"] = {"oos": {k: orc_oos[k] for k in ("CAGR", "MaxDD", "Calmar")},
                     "capture_of_excess_over_null": cap}
    print(f"\n[oracle] OOS perfect-foresight: CAGR {orc_oos['CAGR']:.2%} "
          f"MaxDD {orc_oos['MaxDD']:.1%}; capture of (oracle-null) CAGR: " +
          ", ".join(f"{k} {v:+.1%}" for k, v in cap.items()))

    # ===================== (8) REGIME HONESTY: 1980-99 =======================
    a, b = pd.Period("1980-01", "M"), pd.Period("1999-12", "M")
    reg = {nm: stats(win(my[nm], a, b), rf) for nm in ("relmom_cash", "static_5050")}
    sw = (my_st2 != my_st2.shift(1)) & my_st2.shift(1).notna()
    sw8099 = int(sw[(sw.index >= a) & (sw.index <= b)].sum())
    out["regime_1980_99"] = {
        "relmom": {k: reg["relmom_cash"][k] for k in ("CAGR", "MaxDD", "Calmar")},
        "null": {k: reg["static_5050"][k] for k in ("CAGR", "MaxDD", "Calmar")},
        "dCAGR_pp": (reg["relmom_cash"]["CAGR"] - reg["static_5050"]["CAGR"]),
        "switches": sw8099}
    print(f"\n[regime 80-99] rule2 {reg['relmom_cash']['CAGR']:.2%}/"
          f"{reg['relmom_cash']['MaxDD']:.1%} vs null {reg['static_5050']['CAGR']:.2%}/"
          f"{reg['static_5050']['MaxDD']:.1%}; switches {sw8099}")

    # ================ pessimistic pre-2007 carry variant (±1%/yr band) =======
    pp = panel.copy()
    pre = pp.index < pd.Period("2007-01", "M")
    pp.loc[pre, "gde_synth"] = pp.loc[pre, "gde_synth"] - 0.009 / 12.0
    st2p = rule2_states(pp)
    Ap = pd.DataFrame({"gde": pp["gde_synth"], "spy": pp["spx_tr"],
                       "boxx": pp["bills"] - BOXX_DRAG / 12.0})
    r2p = bt(st2p, Ap)
    nullp = bt(pd.Series("5050", index=pp.index), Ap)
    pv = {"relmom_oos": {k: stats(win(r2p, OOS), rf)[k]
                         for k in ("CAGR", "MaxDD", "Calmar", "Sharpe")},
          "null_oos": {k: stats(win(nullp, OOS), rf)[k]
                       for k in ("CAGR", "MaxDD", "Calmar", "Sharpe")},
          "relmom_dCAGR_vs_spy_oos": stats(win(r2p, OOS), rf)["CAGR"]
                                     - heads["bh_spy"]["oos"]["CAGR"],
          "state_changes_vs_base": int((st2p.reindex(my_st2.index) != my_st2).sum())}
    out["pessimistic_carry"] = pv
    print(f"\n[pessimistic carry] rule2 OOS {pv['relmom_oos']['CAGR']:.2%}/"
          f"{pv['relmom_oos']['MaxDD']:.1%}/C{pv['relmom_oos']['Calmar']:.2f} "
          f"(null C{pv['null_oos']['Calmar']:.2f}); dCAGR vs SPY "
          f"{pv['relmom_dCAGR_vs_spy_oos']:+.2%}; states changed "
          f"{pv['state_changes_vs_base']}")

    with open(os.path.join(HERE, "qa_results.json"), "w") as fh:
        json.dump(out, fh, default=float, indent=1)
    print("\nwrote qa_results.json")


if __name__ == "__main__":
    main()
