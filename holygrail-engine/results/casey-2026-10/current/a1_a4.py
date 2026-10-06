"""Analysis A, sections A1-A4 (scorecards, OO grid, diversifiers, needs-work).
Run: cd holygrail-engine && python results/casey-2026-10/current/a1_a4.py"""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd

from hg_common import (lab as slab, OUT, P, PRIOR_SHARPE, BookView, Position, base_raw, build, loader, neff_rows, pos,
                       prepare_moments, revert_loans, score, set_prior, settings, sleeve_table, summary_row)
from holygrail import report

M = {"post_hoc": []}

# ---- 1. prior vols: one moments pass over every market/series stream (base window) -------------
raw0 = base_raw(spliced=True)
book0 = build(raw0)
emp = [n for n in book0.universe.names if book0.universe[n].kind in ("market", "series") and not n.endswith("_live")]
fake = BookView("all-empirical", [Position(n, 1.0, n) for n in emp], float(len(emp)))
st = settings()
m_all, prov_all, rf_info, _, rets_all = prepare_moments(book0, fake, loader, st)
RF = rf_info["value"]
VOLS = {n: float(v) for n, v in zip(m_all.names, m_all.vol)}
M["rf"] = rf_info
M["prior_vols_base_window"] = VOLS
M["base_window"] = {"start": str(m_all.estimate.start.date()), "end": str(m_all.estimate.end.date()),
                    "n_obs": m_all.estimate.n_obs, "ppy": m_all.estimate.periods_per_year,
                    "shrinkage": m_all.estimate.shrinkage}
print("base window", M["base_window"], "rf", RF)


def prior_raw(sharpe=PRIOR_SHARPE, haircut=None, spliced=True):
    r = base_raw(spliced=spliced)
    set_prior(r, VOLS, RF, sharpe, haircut)
    return r


RAW = prior_raw()
json.dump(VOLS, open(OUT / "data" / "prior_vols.json", "w"), indent=1)
json.dump({"rf": RF}, open(OUT / "data" / "rf.json", "w"))

# ---- A1 scorecards --------------------------------------------------------------------------------
views = {}
views["whole_at_mark"] = (RAW, "investable", None)
for oo in (10e6, 15e6, 20e6):
    r = copy.deepcopy(RAW); pos(r, "Organics Ocean")["value_usd"] = oo
    views[f"whole_oo_{int(oo/1e6)}m"] = (r, "investable", None)
views["investable_ex_oo"] = (RAW, "investable", ["Organics Ocean"])
views["liquid_now"] = (RAW, "liquid", None)
rpr = copy.deepcopy(RAW); revert_loans(rpr)
views["liquid_post_revert"] = (rpr, "liquid", None)

A1 = {}
rows = []
for k, (r, vw, ex) in views.items():
    sc = score(r, vw, exclude=ex)
    A1[k] = {"summary": summary_row(k, sc), "neff": neff_rows(sc), "streams": sc["streams"],
             "sleeves": sleeve_table(sc), "flags": sc["flags"], "environment": sc["environment"],
             "gearing": sc["gearing"], "portfolio": sc["portfolio"],
             "covariance": sc["honesty"]["measurement_basis"]["covariance"], "not_modelled": sc["honesty"]["not_modelled"]}
    rows.append(summary_row(k, sc))
    print(k, f"vol {sc['portfolio']['vol']:.3f} DR2 {sc['effective_bets']['dr2']:.2f}",
          [(s['stream'], round(s['risk_share'], 3)) for s in sc["streams"][:4]])
M["A1"] = A1
report.write_rows(pd.DataFrame(rows), OUT / "a1_views_summary")

# robustness of the headline views
ROB = {}
for k in ("whole_at_mark", "liquid_now", "liquid_post_revert"):
    r, vw, ex = views[k]
    for lab, s in (("R1_longest_common_daily", settings(window_years=20.0)), ("R2_weekly_3y", settings(freq="W")),
                   ("R3_sample_daily_3y", settings(estimator="sample"))):
        sc = score(r, vw, st=s, exclude=ex)
        cv = sc["honesty"]["measurement_basis"]["covariance"]
        ROB[f"{k}|{lab}"] = {"vol": sc["portfolio"]["vol"], "dr2": sc["effective_bets"]["dr2"],
                             "top1": sc["streams"][0]["stream"], "top1_risk": sc["streams"][0]["risk_share"],
                             "window": f"{cv['start']}..{cv['end']} n={cv['n_obs']}", "balance_score": sc["environment"]["balance_score"]}
        print("ROB", k, lab, {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in ROB[f"{k}|{lab}"].items()})
M["A1_robustness"] = ROB

# ---- chart: risk vs dollar by sleeve (liquid now, whole at mark) ----------------------------------
import matplotlib.pyplot as plt  # noqa: E402

SER, INK2 = report.SERIES, report.INK2


def sleeve_chart(key, title, fname):
    sl = [s for s in A1[key]["sleeves"] if abs(s["dollar_share"]) > 1e-4 or abs(s["risk_share"]) > 1e-4]
    sl = sl[::-1]
    y = np.arange(len(sl))
    fig, ax = plt.subplots(figsize=(7.8, 0.42 * len(sl) + 1.4))
    ax.barh(y + 0.19, [100 * s["dollar_share"] for s in sl], height=0.36, color=SER[0], label="dollar share")
    ax.barh(y - 0.19, [100 * s["risk_share"] for s in sl], height=0.36, color=SER[1], label="risk share")
    ax.set_yticks(y, [s["sleeve"] for s in sl])
    ax.axvline(0, color=INK2, lw=0.8)
    report._style(ax, title, "% of book", "")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
    fig.tight_layout(); fig.savefig(OUT / f"{fname}.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)
    report.write_rows(pd.DataFrame(sl[::-1]), OUT / fname)


sleeve_chart("liquid_now", "Liquid book now: where the money is vs where the risk is", "a1_liquid_risk_vs_dollar")
sleeve_chart("whole_at_mark", "Whole book at mark: where the money is vs where the risk is", "a1_whole_risk_vs_dollar")

# ---- A2 Organics Ocean grid ----------------------------------------------------------------------
grid = []
for vol in P["A2_grid"]["oo_vol"]:
    for rho in P["A2_grid"]["oo_corr_IWM"]:
        r = copy.deepcopy(RAW)
        o = r["streams"]["organics_ocean"]
        o["vol"] = {"value": vol, "source": "A2 grid", "confidence": "placeholder"}
        o["factor_correlations"] = {"IWM": {"value": rho, "source": "A2 grid", "confidence": "placeholder"}}
        sc = score(r, "investable")
        oo = next(s for s in sc["streams"] if s["stream"] == "organics_ocean")
        grid.append({"oo_vol": vol, "oo_corr_iwm": rho, "oo_risk_share": oo["risk_share"],
                     "whole_dr2": sc["effective_bets"]["dr2"], "whole_vol": sc["portfolio"]["vol"],
                     "neff_inv_hhi_prc": neff_rows(sc)["1/sum PRC^2"]["value"] if "1/sum PRC^2" in neff_rows(sc) else None})
        print("A2", vol, rho, round(oo["risk_share"], 3), round(sc["effective_bets"]["dr2"], 2))
G = pd.DataFrame(grid)
report.write_rows(G, OUT / "a2_oo_grid")
M["A2"] = grid
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
for ax, col, ttl, fmt in ((axs[0], "oo_risk_share", "Organics Ocean share of whole-book risk", "{:.0%}"),
                          (axs[1], "whole_dr2", "Whole-book effective bets (DR^2)", "{:.2f}")):
    piv = G.pivot(index="oo_vol", columns="oo_corr_iwm", values=col)
    im = ax.imshow(piv.to_numpy(), cmap="Blues", aspect="auto", origin="lower")
    ax.set_xticks(range(len(piv.columns)), [f"{c:.1f}" for c in piv.columns])
    ax.set_yticks(range(len(piv.index)), [f"{v:.0%}" for v in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iat[i, j]
            ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=9,
                    color="white" if v > piv.to_numpy().mean() else report.INK)
    report._style(ax, ttl, "corr(OO, small caps IWM)", "OO vol")
    ax.grid(False)
fig.tight_layout(); fig.savefig(OUT / "a2_oo_grid.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# ---- A3 / A4: correlations within the liquid book (post-revert weights) ---------------------------
sc_pr, m_pr, rets_pr, book_pr, v_pr = score(rpr, "liquid", return_moments=True)
names = m_pr.names
S, vol, C = m_pr.cov, m_pr.vol, m_pr.corr()
w = np.array([v_pr.stream_values()[n] / v_pr.total_usd for n in names])
iSPY = names.index("SPY")
spy_r = rets_pr["SPY"].dropna()
worst = spy_r[spy_r <= spy_r.quantile(0.05)].index
a3 = []
for i, n in enumerate(names):
    if vol[i] <= 1e-9:
        continue
    wr = w.copy(); wr[i] = 0.0
    sr = math_sqrt = float(np.sqrt(wr @ S @ wr))
    corr_rest = float((S @ wr)[i] / (vol[i] * sr)) if sr > 0 else float("nan")
    kind = book_pr.universe[n].kind
    if n in rets_pr.columns:
        sr_n = rets_pr[n]
    elif kind == "composite":
        sr_n = book_pr.universe.series_returns(n, rets_pr, RF / m_pr.estimate.periods_per_year, m_pr.estimate.periods_per_year)
    else:
        sr_n = None
    down = float(sr_n.reindex(worst).mean()) if sr_n is not None else None
    a3.append({"stream": n, "usd": v_pr.stream_values()[n], "vol": float(vol[i]), "corr_rest_of_liquid": corr_rest,
               "corr_spy": float(C[i, iSPY]), "mean_ret_spy_worst5pct_days": down,
               "basis": "assumption (parametric)" if kind == "parametric" else "measured",
               "risk_share": next(s["risk_share"] for s in sc_pr["streams"] if s["stream"] == n)})
spy_down = float(spy_r.reindex(worst).mean())
A3 = pd.DataFrame(a3).sort_values("corr_rest_of_liquid")
A3["label"] = [slab(n) for n in A3.stream]
report.write_rows(A3, OUT / "a3_diversifiers")
M["A3"] = {"rows": a3, "spy_worst5pct_mean": spy_down, "n_worst_days": len(worst)}
print(A3.round(3).to_string())

# weekly cross-check of the same correlations
sc_w, m_w, rets_w, _, v_w = score(rpr, "liquid", st=settings(freq="W"), return_moments=True)
Cw = m_w.corr(); Sw = m_w.cov
ww = np.array([v_w.stream_values()[n] / v_w.total_usd for n in m_w.names])
wk = {}
for i, n in enumerate(m_w.names):
    if m_w.vol[i] <= 1e-9:
        continue
    wr = ww.copy(); wr[i] = 0
    wk[n] = {"corr_rest_weekly": float((Sw @ wr)[i] / (m_w.vol[i] * np.sqrt(wr @ Sw @ wr))),
             "corr_spy_weekly": float(Cw[i, m_w.names.index("SPY")])}
M["A3_weekly"] = wk

sel = A3[A3.stream.isin(["KMLM", "PHYS", "PSLV", "physical_metals", "composer_crash", "eth_carry", "composer_vixhyg",
                         "BTC", "composer_hg", "composer_kmlm", "AVUV", "SPY", "TSLA"])].sort_values("corr_rest_of_liquid")
fig, ax = plt.subplots(figsize=(8, 0.45 * len(sel) + 1.4))
y = np.arange(len(sel))
ax.barh(y + 0.19, sel.corr_rest_of_liquid, height=0.36, color=SER[0], label="corr to rest of liquid book")
ax.barh(y - 0.19, sel.corr_spy, height=0.36, color=SER[1], label="corr to SPY")
ax.set_yticks(y, [slab(n) for n in sel.stream])
ax.axvline(0, color=INK2, lw=0.8)
report._style(ax, "Which streams already diversify (daily, trailing 3y)", "correlation", "")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "a3_diversifiers.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# private credit vs liquid book (assumption-driven, whole-book moments)
sc_wh, m_wh, _, _, v_wh = score(RAW, "investable", return_moments=True)
nm = m_wh.names
Cwh = m_wh.corr()
pc = {}
for n in ("film_gap_loans", "gary_loan", "spirit_fund", "film_father_of_us", "real_estate", "em_special_sits", "organics_ocean", "venture_basket"):
    pc[n] = {"corr_spy": float(Cwh[nm.index(n), nm.index("SPY")]), "corr_btc": float(Cwh[nm.index(n), nm.index("BTC")]),
             "basis": "ASSUMPTION (factor correlation to HYG/IWM/VNQ/EMB x measured factor covariance)"}
M["A3_private"] = pc

# ---- A4 overlap matrix -----------------------------------------------------------------------------
ov = P["A3_A4"]["overlap_set"]
fv = BookView("overlap", [Position(n, 1.0, n) for n in ov], float(len(ov)))
mo, *_ = prepare_moments(build(RAW), fv, loader, settings())
mow, *_ = prepare_moments(build(RAW), fv, loader, settings(freq="W"))
Co = pd.DataFrame(mo.corr(), index=ov, columns=ov)
Cow = pd.DataFrame(mow.corr(), index=ov, columns=ov)
report.write_rows(Co.reset_index().rename(columns={"index": "stream"}), OUT / "a4_overlap_corr")
report.write_rows(Cow.reset_index().rename(columns={"index": "stream"}), OUT / "a4_overlap_corr_weekly")
M["A4_overlap_daily"] = Co.round(4).to_dict()
M["A4_overlap_weekly"] = Cow.round(4).to_dict()
lab = {"composer_hg": "Composer HG symphony", "composer_kmlm": "Composer KMLM switcher", "composer_vixhyg": "Composer VIX Harvester",
       "KMLM": "KMLM (trend ETF)", "TSLA": "TSLA", "BTC": "BTC", "SPY": "SPY", "QQQ": "QQQ"}
fig, ax = plt.subplots(figsize=(7.2, 6))
im = ax.imshow(Co.to_numpy(), cmap=report.DIVERGING, vmin=-1, vmax=1)
ax.set_xticks(range(len(ov)), [lab[o] for o in ov], rotation=40, ha="right")
ax.set_yticks(range(len(ov)), [lab[o] for o in ov])
for i in range(len(ov)):
    for j in range(len(ov)):
        ax.text(j, i, f"{Co.iat[i, j]:.2f}", ha="center", va="center", fontsize=8, color=report.INK)
report._style(ax, "Overlap: daily correlations, trailing 3y", "", "")
ax.grid(False)
fig.colorbar(im, ax=ax, fraction=0.046)
fig.tight_layout(); fig.savefig(OUT / "a4_overlap_corr.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# cash-like share and what it does to vol
def cash_stats(key):
    sl = {s["sleeve"]: s for s in A1[key]["sleeves"]}
    cs = sl.get("cash_like", {"dollar_share": 0.0})["dollar_share"]
    vol_ = A1[key]["portfolio"]["vol"]
    return {"cash_like_share": cs, "cash_like_usd": sl.get("cash_like", {"usd": 0})["usd"], "vol": vol_,
            "vol_of_noncash_part": vol_ / (1 - cs), "scorecard_leverage_to_15": A1[key]["gearing"]["leverage_to_target"],
            "risky_fraction_needed_for_15": 0.15 / (vol_ / (1 - cs)),
            "cash_to_deploy_for_15_usd": (0.15 / (vol_ / (1 - cs)) - (1 - cs)) * A1[key]["summary"]["nav_usd"]}
M["A4_cash"] = {k: cash_stats(k) for k in ("liquid_now", "liquid_post_revert")}
print(M["A4_cash"])

# ---- repair pass (post-hoc, labelled): committed cash and the F4/F5 double-count question ----------
# Sheet H2 roll-out (live-linked to Cash/Stables $381,066): upcoming $435,200 = Series X $215,200 uncalled
# + DexMat $100,000 + Jarod Production $120,000; 'Cash Remaining' -$54,134 = 381,066 - 435,200.
COMMIT = {"Series X (uncalled)": 215_200.0, "DexMat": 100_000.0, "Jarod Production": 120_000.0}
COMMIT_USD = sum(COMMIT.values())
PLUG = "Short-term 16% loans (out of BOXX)"
M["post_hoc"].append({
    "item": "repair pass 2026-10-06: A4_cash_net_of_commitments and A1_at_stake_F4_F5 added after the counter-agent review",
    "why": "'cash to deploy for 15%' treated $435,200 of committed cash (sheet H2 roll-out 'upcoming') as free; and the "
           "$310,876 16% loan plug may double count the Dominion $200k bridge (F4/F5). The F4/F5 rows are AT STAKE, "
           "not results: the question is with Casey (DD P1) and the liquid headlines are HELD until he answers."})


def pay_commitments(raw, usd):
    """Commitments are paid from 'Cash/stables ex-Hyperliquid' first, then BOXX (never from Hyperliquid USDC)."""
    c = pos(raw, "Cash/stables ex-Hyperliquid")
    t = min(usd, c["value_usd"]); c["value_usd"] -= t; usd -= t
    b = pos(raw, "U84 BOXX")
    t = min(usd, b["value_usd"]); b["value_usd"] -= t; usd -= t
    assert usd < 1e-6, usd


def liquid_case(r):
    sc = score(r, "liquid")
    sl = {s["sleeve"]: s for s in sleeve_table(sc)}
    cs, cu = sl["cash_like"]["dollar_share"], sl["cash_like"]["usd"]
    vol_ = sc["portfolio"]["vol"]
    st_ = {s["stream"]: s for s in sc["streams"]}
    return {"nav_usd": sc["nav_usd"], "vol": vol_, "dr2": sc["effective_bets"]["dr2"],
            "btc_risk": st_.get("BTC", {}).get("risk_share", 0.0), "cash_like_share": cs, "cash_like_usd": cu,
            "leverage_to_15": sc["gearing"]["leverage_to_target"], "vol_of_noncash_part": vol_ / (1 - cs),
            "cash_to_deploy_for_15_usd": (0.15 / (vol_ / (1 - cs)) - (1 - cs)) * sc["nav_usd"]}


CASES = {
    "book_as_is": ("plug $310,876 as two outstanding 16% loans; no commitments paid", 0.0, False),
    "commitments_paid": ("book as is, then the $435,200 H2 commitments paid out of liquid cash", 0.0, True),
    "plug_less_200k": ("AT STAKE: Dominion $200k is one of the two BOXX loans and its returned capital is already in "
                       "the liquid view (IBKR BOXX or Cash/Stables): plug -$200,000", 200_000.0, False),
    "plug_less_200k_commitments_paid": ("AT STAKE: plug -$200,000 and the $435,200 commitments paid", 200_000.0, True),
    "plug_zero": ("AT STAKE: the two BOXX loans are Dominion $200k + Plus One $129,166, both returned and already "
                  "in the liquid view: plug -> $0", 310_876.3, False),
    "plug_zero_commitments_paid": ("AT STAKE: plug $0 and the $435,200 commitments paid", 310_876.3, True),
}
AT = {}
for k, (desc, cut, paid) in CASES.items():
    r = copy.deepcopy(RAW)
    pos(r, PLUG)["value_usd"] -= cut
    if paid:
        pay_commitments(r, COMMIT_USD)
    AT[k] = {"desc": desc, "plug_usd": pos(r, PLUG)["value_usd"], "commitments_paid_usd": COMMIT_USD if paid else 0.0,
             **liquid_case(r)}
    print("AT", k, {kk: round(vv, 4) for kk, vv in AT[k].items() if isinstance(vv, float)})
M["A4_cash_net_of_commitments"] = {
    "commitments": COMMIT, "commitments_usd": COMMIT_USD,
    "source": "sheet 'Portfolio Tracking - 2026 H2 Future Spend Planning' H2 roll-out: upcoming column; Cash Remaining "
              "-$54,134 = Cash/Stables $381,066 - $435,200 (call timing not supplied)",
    "rule": "commitments paid from Cash/stables ex-Hyperliquid ($280,948) first, then BOXX; Hyperliquid USDC untouched",
    "liquid_now": AT["book_as_is"], "liquid_now_commitments_paid": AT["commitments_paid"],
    "basis": "same formula as A4_cash: risky $ needed for 15% = 0.15 x NAV / vol of the non-cash part; cash-like ~0 vol"}
for _k in ("liquid_now", "liquid_post_revert"):
    M["A4_cash"][_k]["caveat"] = ("GROSS: treats the $435,200 of committed cash (sheet H2 roll-out 'upcoming') as free and carries the "
                                  "$310,876 16% loan plug in full (F4/F5 open). Net figures: A4_cash_net_of_commitments; at stake: A1_at_stake_F4_F5")
    A1[_k]["status"] = "HELD pending Casey's answer to DD P1 (F4/F5): the 16% loan plug may double count the Dominion $200k"
M["A1_at_stake_F4_F5"] = {
    "status": "HELD - NOT A RESULT. Question with Casey (DD P1): are Dominion ($200k @16%, 9/8->9/25/26, returned) and "
              "Plus One ($129,166 @15%, 9/3->9/29/26, returned) the two '16% loans out of BOXX', and where is the returned "
              "capital now? The liquid headlines (vol, cash-like share, leverage to 15%, cash to deploy) ship only after "
              "the answer (CLAUDE.md: ask, don't analyse around missing inputs).",
    "cases": AT}
report.write_rows(pd.DataFrame([{"case": k, **v} for k, v in AT.items()]), OUT / "a4_at_stake_F4_F5_commitments")

report.write_json(M, OUT / "metrics_a1_a4.json")
print("done")
