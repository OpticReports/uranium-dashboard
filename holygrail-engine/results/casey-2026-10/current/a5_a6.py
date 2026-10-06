"""Analysis A, sections A5 (moves) and A6 (proposed 15%-vol liquid book, backtests, stress, forward).
Run after a1_a4.py:  cd holygrail-engine && python results/casey-2026-10/current/a5_a6.py"""
from __future__ import annotations

import copy
import json
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq

from hg_common import (lab as slab, OUT, P, SPREAD, STREAM_SLEEVE, TARGET, BookView, Position, base_raw, build, buy, loader,
                       neff_rows, pos, prepare_moments, revert_loans, score, sell, set_prior, settings, sleeve_table,
                       summary_row, drop_zero, COMPOSER_LIVE_START, IBKR_CARD, ibkr_interest, ibkr_spread_over_rf)
from holygrail import report
from holygrail.allocate import quadrant_balance, risk_budget_weights
from holygrail.backtest import BacktestConfig, run_backtest
from holygrail.core import effective_bets, percent_risk_contributions
from holygrail.data import tbill_period_returns
from holygrail.environments import BOXES, environment_balance, exposures_from_mapping, stream_box_mapping
from holygrail.estimate import aligned_returns, infer_periods_per_year
from holygrail.forward import SCENARIOS, SimConfig, replay_scenario, run_forward
from holygrail.metrics import performance_metrics

VOLS = json.load(open(OUT / "data" / "prior_vols.json"))
RF = json.load(open(OUT / "data" / "rf.json"))["rf"]
SER, INK, INK2 = report.SERIES, report.INK, report.INK2
M = {"post_hoc": []}
ALPHA_HAIRCUT = {"composer_hg", "composer_kmlm", "composer_crash", "composer_vixhyg", "BTC", "GH", "TWST", "TEM", "LLY",
                 "VIST", "JOINN", "BOT", "FTZFF", "SHAZ", "TSLA"}
CASHLIKE = {"BOXX", "BIL", "cash", "usdc_idle", "st_loans_16", "evergrande", "margin_loan"}


def prior_raw(sharpe=0.30, haircut=None):
    r = base_raw(spliced=True)
    set_prior(r, VOLS, RF, sharpe, haircut)
    return r


PRIORS = {"base_0.30": prior_raw(), "low_0.25": prior_raw(0.25), "alpha_haircut": prior_raw(0.30, ALPHA_HAIRCUT)}


def exp_at_15(sc, spread=SPREAD):
    """PRIOR-DRIVEN expected return if the risky part is scaled to 15% vol, cash-like deployed first,
    then borrowing at rf + spread."""
    rows = sc["streams"]
    risky = [r for r in rows if r["stream"] not in CASHLIKE]
    u = sum(r["dollar_share"] for r in risky)
    m_r = sum(r["dollar_share"] * r["exp_return"] for r in risky)
    L = TARGET / sc["portfolio"]["vol"]
    c = 1 - L * u
    return L * m_r + c * (RF if c >= 0 else RF + spread), L, c


def row_for(label, raws_by_prior, view="liquid"):
    out = {}
    for pk, r in raws_by_prior.items():
        sc = score(r, view)
        e15, L, c = exp_at_15(sc)
        if pk == "base_0.30":
            out.update(summary_row(label, sc))
            st = {s["stream"]: s for s in sc["streams"]}
            sl = {s["sleeve"]: s for s in sleeve_table(sc)}
            out.update({"btc_risk": st.get("BTC", {}).get("risk_share", 0.0),
                        "composer_momentum_risk": sl.get("composer_equity_momentum", {}).get("risk_share", 0.0),
                        "single_names_risk": sl.get("single_names", {}).get("risk_share", 0.0),
                        "cash_like_share": sl.get("cash_like", {}).get("dollar_share", 0.0),
                        "L_to_15_cash_first": L, "borrowed_share_at_15": max(-c, 0.0),
                        "gross_now": (1 - c) / L, "gross_at_15": 1 - c})
        out[f"exp_now_{pk}"] = sc["portfolio"]["exp_return"]
        out[f"exp_at15_{pk}"] = e15
    return out


# ---------------------------------------------------------------------------------------------------
# A5 moves
# ---------------------------------------------------------------------------------------------------
def m0(r): revert_loans(r)
def m1(r): buy(r, "TLT", 250_000)
def m2(r): buy(r, "TIP", 200_000)
def m3(r): buy(r, "DBC", 150_000)


def m4(r):
    for n in ("U84 TSLA", "U84 FTZFF Fitzroy Minerals", "U84 SHAZ SharonAI"):
        sell(r, n, pos(r, n)["value_usd"] / 2)


def m5(r): sell(r, "BTC (sheet)", 139_400)


def m6(r):
    hg, km = pos(r, "Composer hg")["value_usd"], pos(r, "Composer kmlm")["value_usd"]
    k = 120_000 / (hg + km)
    sell(r, "Composer hg", hg * (1 - k)); sell(r, "Composer kmlm", km * (1 - k))
    fundbuy_existing(r, "Composer crash", 30_000)


def fundbuy_existing(r, name, usd):
    from hg_common import fund
    fund(r, usd)
    pos(r, name)["value_usd"] += usd


def m7(r): fundbuy_existing(r, "U84 KMLM", 100_000)


def m8(r):
    for n in ("U26 SPY", "U84 AVUV", "U84 AVDV", "U84 AVEM", "U84 QUAL", "NEW TLT", "NEW TIP", "NEW DBC"):
        try:
            v = pos(r, n)["value_usd"]
        except KeyError:
            continue
        if n.startswith("NEW "):
            buy(r, n[4:], 0.5 * v)
        else:
            fundbuy_existing(r, n, 0.5 * v)


def m9(r): buy(r, "allw_replica", 250_000)


MOVES = [("M0", "16% loans revert to BOXX (+$310.9k BOXX; scheduled)", m0),
         ("M1", "+$250k long Treasuries (TLT)", m1), ("M2", "+$200k TIPS (TIP)", m2),
         ("M3", "+$150k broad commodities (DBC)", m3), ("M4", "halve TSLA, FTZFF, SHAZ (-$47.8k)", m4),
         ("M5", "cap BTC: sell $139.4k (half the sheet BTC)", m5),
         ("M6", "Composer as one equity-momentum budget: HG+KMLM switcher $184.3k->$120k; +$30k Crash Convexity", m6),
         ("M7", "+$100k KMLM trend", m7), ("M8", "gear balanced core 1.5x (SPY/AV*/QUAL/TLT/TIP/DBC)", m8)]
ALT = [("M9", "ALT: +$250k ALLW (replica of published exposures)", m9)]

rows_one, rows_cum = [], []
base_row = row_for("current", PRIORS)
rows_one.append({"move": "current", "desc": "liquid book now", **base_row})
rows_cum.append({"move": "current", "desc": "liquid book now", **base_row})
cum = {k: copy.deepcopy(v) for k, v in PRIORS.items()}
for code, desc, fn in MOVES + ALT:
    one = {}
    for k, v in PRIORS.items():
        r = copy.deepcopy(v); fn(r); one[k] = r
    rows_one.append({"move": code, "desc": desc, **row_for(code, one)})
    if code != "M9":
        for k in cum:
            fn(cum[k])
        rows_cum.append({"move": code, "desc": desc, **row_for("cum " + code, cum)})
    print(code, "one:", {k: round(rows_one[-1][k], 3) for k in ("vol", "dr2", "balance_score", "btc_risk", "exp_at15_base_0.30")},
          "cum:", {k: round(rows_cum[-1][k], 3) for k in ("vol", "dr2", "balance_score", "btc_risk", "exp_at15_base_0.30")})
R1, RC = pd.DataFrame(rows_one), pd.DataFrame(rows_cum)
report.write_rows(R1, OUT / "a5_moves_one_at_a_time")
report.write_rows(RC, OUT / "a5_moves_cumulative")
report.write_rows(pd.concat([R1.assign(path="one_at_a_time"), RC.assign(path="cumulative")]), OUT / "a5_moves")
M["A5"] = {"one_at_a_time": rows_one, "cumulative": rows_cum}
CUM_FINAL = cum["base_0.30"]

fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
x = np.arange(len(RC))
for ax, col, ttl, f in ((axs[0], "vol", "Book vol (%)", 100), (axs[1], "dr2", "Effective bets DR^2", 1),
                        (axs[2], "balance_score", "Environment balance (1 = balanced)", 1)):
    ax.plot(x, RC[col] * f, color=SER[0], lw=2, marker="o", ms=5, label="cumulative")
    ax.plot(x, R1[R1.move != "M9"][col] * f, color=SER[1], lw=0, marker="o", ms=5, label="one at a time")
    if col == "vol":
        ax.axhline(15, color=INK2, lw=0.8, ls="--")
    ax.set_xticks(x, RC.move, fontsize=8)
    report._style(ax, ttl, "move", "")
axs[0].legend(frameon=False, fontsize=8, labelcolor=INK2)
fig.tight_layout(); fig.savefig(OUT / "a5_moves.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# ---------------------------------------------------------------------------------------------------
# A6 proposed book
# ---------------------------------------------------------------------------------------------------
RPR = copy.deepcopy(PRIORS["base_0.30"]); revert_loans(RPR); drop_zero(RPR)
NAV = sum(p["value_usd"] for p in RPR["positions"] if p.get("liquidity", "liquid") == "liquid")
val = {p["name"]: p["value_usd"] for p in RPR["positions"]}
CORE_EQ = {"SPY": val["U26 SPY"], "AVUV": val["U84 AVUV"], "AVDV": val["U84 AVDV"], "AVEM": val["U84 AVEM"], "QUAL": val["U84 QUAL"]}
GOLD = {"physical_metals": val["Physical metals"], "PHYS": val["U84 PHYS"], "PSLV": val["U84 PSLV"]}
SINGLE = {"GH": val["U26 GH"], "TWST": val["U26 TWST"], "TEM": val["U26 TEM"], "LLY": val["U26 LLY"],
          "VIST": val["U84 VISTAA (as VIST)"], "JOINN": val["U84 Joinn Labs 603127"], "BOT": val["U84 BOT RoboStrategy"],
          "FTZFF": val["U84 FTZFF Fitzroy Minerals"], "SHAZ": val["U84 SHAZ SharonAI"], "TSLA": val["U84 TSLA"]}
MOM = {"composer_hg": val["Composer hg"], "composer_kmlm": val["Composer kmlm"]}


def norm(d):
    t = sum(d.values()); return {k: v / t for k, v in d.items()}


def add_composites(raw):
    st = raw["streams"]
    st["core_equity"] = {"type": "composite", "components": norm(CORE_EQ), "asset_class": "equity",
                         "description": "equity beta core: SPY/AVUV/AVDV/AVEM/QUAL at the current $ mix"}
    st["gold_silver"] = {"type": "composite", "components": norm(GOLD), "asset_class": "gold",
                         "description": "physical metals + PHYS + PSLV at the current $ mix"}
    st["single_names"] = {"type": "composite", "components": norm(SINGLE), "asset_class": "equity",
                          "description": "single names at the current $ mix"}
    st["composer_momentum"] = {"type": "composite", "components": norm(MOM), "asset_class": "equity",
                               "description": "Composer HG symphony + Composer KMLM switcher, ONE equity-momentum budget (current $ split)"}


for r in PRIORS.values():
    add_composites(r)
add_composites(RPR)
add_composites(CUM_FINAL)

AP = P["A6_proposed"]["risk_budgets_of_total"]
CORE = ["core_equity", "TLT", "TIP", "DBC", "gold_silver"]
ALPHA_B = {"BTC": AP["BTC"], "composer_momentum": list(v for k, v in AP.items() if k.startswith("composer_momentum"))[0],
           "composer_crash": AP["composer_crash"], "composer_vixhyg": AP["composer_vixhyg"], "KMLM": AP["KMLM"],
           "single_names": list(v for k, v in AP.items() if k.startswith("single_names"))[0]}
CORE_SHARE = AP["balanced_beta_core"]
FIXED = P["A6_proposed"]["fixed_unbudgeted"]
BUDGETED = CORE + list(ALPHA_B)

book_c = build(RPR)
fv = BookView("budgeted", [Position(n, 1.0, n) for n in BUDGETED + ["eth_carry"]], float(len(BUDGETED) + 1))
mB, *_ = prepare_moments(book_c, fv, loader, settings())
names_B = mB.names
S_all = mB.cov


def core_budgets(S_core, core_names, universe):
    mp, _ = stream_box_mapping(universe, core_names)
    Mx, _ = exposures_from_mapping(core_names, mp)
    q = quadrant_balance(S_core, Mx, BOXES)
    return dict(zip(core_names, q.budgets)), q


def solve_budget_weights(S, names, universe, fixed_w=None, core_share=CORE_SHARE, alpha=ALPHA_B):
    """Risk-budget weights (sum 1) over the budgeted streams present in ``names``."""
    core = [n for n in CORE if n in names]
    ic = [names.index(n) for n in core]
    cb, q = core_budgets(S[np.ix_(ic, ic)], core, universe)
    b = {n: core_share * cb[n] for n in core}
    b.update({k: v for k, v in alpha.items() if k in names})
    tot = sum(b.values())
    bud = np.array([b.get(n, 0.0) / tot for n in names])
    w = risk_budget_weights(S, bud)
    return w, bud, cb


ib = [names_B.index(n) for n in BUDGETED]
w_rb, bud, cb = solve_budget_weights(S_all[np.ix_(ib, ib)], BUDGETED, book_c.universe)
f_eth = FIXED["eth_carry"] / NAV
ie = names_B.index("eth_carry")


def tot_vol(L):
    x = np.zeros(len(names_B)); x[ib] = L * w_rb; x[ie] = f_eth
    return math.sqrt(float(x @ S_all @ x))


L_star = brentq(lambda L: tot_vol(L) - TARGET, 1e-3, 10.0)
prop_usd = {n: float(L_star * w_rb[i] * NAV) for i, n in enumerate(BUDGETED)}
cash_usd = NAV - sum(prop_usd.values()) - FIXED["eth_carry"] - FIXED["usdc_idle"]
print("proposed L", round(L_star, 3), {k: round(v) for k, v in prop_usd.items()}, "cash", round(cash_usd))
M["A6_solve"] = {"nav": NAV, "L": L_star, "usd": prop_usd, "cash_or_borrow_usd": cash_usd,
                 "budgets": dict(zip(BUDGETED, bud.tolist())), "core_quadrant_budgets": cb,
                 "gross_of_nav": (sum(prop_usd.values()) + FIXED["eth_carry"]) / NAV}


def proposed_raw(base):
    r = copy.deepcopy(base)
    keep = {"HL ETH carry (UETH spot + perp short)", "HL spot USDC", "HL BTC trend long (notional)"}
    r["positions"] = [p for p in r["positions"] if p["name"] in keep or p.get("liquidity", "liquid") != "liquid"]
    hl_btc = val["HL BTC trend long (notional)"]
    for n, usd in prop_usd.items():
        v = usd - hl_btc if n == "BTC" else usd
        r["positions"].append({"name": f"PROP {n}", "value_usd": v, "stream": n, "sleeve": "stocks", "liquidity": "liquid",
                               "mark_basis": "market", "tags": ["proposed"], "investable": True})
    if cash_usd >= 0:
        r["positions"].append({"name": "PROP cash (BOXX)", "value_usd": cash_usd, "stream": "BOXX", "sleeve": "stocks",
                               "liquidity": "liquid", "mark_basis": "market", "tags": ["proposed"], "investable": True})
    else:
        r["positions"].append({"name": "Margin loan", "value_usd": cash_usd, "stream": "margin_loan", "sleeve": "stocks",
                               "liquidity": "liquid", "mark_basis": "market", "tags": ["proposed", "margin"],
                               "investable": True, "liability": True})
    return r


PROP = {k: proposed_raw(v) for k, v in PRIORS.items()}
sc_prop, m_prop, rets_prop, book_prop, v_prop = score(PROP["base_0.30"], "liquid", return_moments=True)
prop_row = {"move": "PROPOSED", "desc": "risk-budgeted, geared to 15%", **row_for("proposed", PROP)}
M["A6_scorecard"] = {"summary": summary_row("proposed", sc_prop), "neff": neff_rows(sc_prop), "streams": sc_prop["streams"],
                     "sleeves": sleeve_table(sc_prop), "environment": sc_prop["environment"], "portfolio": sc_prop["portfolio"],
                     "flags": sc_prop["flags"], "row": prop_row}
print("PROPOSED", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prop_row.items() if k in
      ("vol", "dr2", "balance_score", "btc_risk", "exp_now_base_0.30", "exp_now_low_0.25", "exp_now_alpha_haircut")})
for lab, s in (("R1_longest_common_daily", settings(window_years=20.0)), ("R2_weekly_3y", settings(freq="W")),
               ("R3_sample_daily_3y", settings(estimator="sample"))):
    scx = score(PROP["base_0.30"], "liquid", st=s)
    M.setdefault("A6_robustness", {})[lab] = {"vol": scx["portfolio"]["vol"], "dr2": scx["effective_bets"]["dr2"],
                                              "balance_score": scx["environment"]["balance_score"]}
print("A6 robustness", M["A6_robustness"])


# ---------------------------------------------------------------------------------------------------
# v2 (POST-HOC, declared in post_hoc_v2.json before computing): standalone-vol alpha sizing, gold held,
# core quadrant-balanced and scaled to 15%, gross cap 2.0x
# ---------------------------------------------------------------------------------------------------
M["post_hoc"].append(json.load(open(OUT / "post_hoc_v2.json")))
GOLD_W = sum(GOLD.values()) / NAV
CAP2 = 2.0
CORE2 = ["core_equity", "TLT", "TIP", "DBC"]


def v2_weights(S, names, universe, fixed_extra=None):
    """weights over ``names`` (subset of BUDGETED + gold_silver [+ eth_carry]) for v2."""
    vol_ = np.sqrt(np.diag(S))
    x = np.zeros(len(names))
    for k, b in ALPHA_B.items():
        if k in names:
            i = names.index(k); x[i] = b * TARGET / vol_[i]
    if "gold_silver" in names:
        x[names.index("gold_silver")] = GOLD_W
    for k, v in (fixed_extra or {}).items():
        if k in names:
            x[names.index(k)] = v
    core = [n for n in CORE2 if n in names]
    ic = [names.index(n) for n in core]
    cb, q = core_budgets(S[np.ix_(ic, ic)], core, universe)
    wc = risk_budget_weights(S[np.ix_(ic, ic)], np.array([cb[n] for n in core]))

    def vol_at(sc_):
        y = x.copy(); y[ic] += sc_ * wc
        return math.sqrt(float(y @ S @ y))
    base_gross = float(x[[i for i, n in enumerate(names) if n != "eth_carry"]].sum())
    s_cap = max(CAP2 - base_gross - (fixed_extra or {}).get("eth_carry", 0.0), 0.0)
    if vol_at(0.0) >= TARGET:
        s_ = 0.0
    elif vol_at(s_cap) < TARGET:
        s_ = s_cap
    else:
        s_ = brentq(lambda z: vol_at(z) - TARGET, 0.0, s_cap)
    y = x.copy(); y[ic] += s_ * wc
    return y, {"core_scale": s_, "core_budgets": cb, "vol": vol_at(s_), "cap_binding": bool(s_ >= s_cap - 1e-9)}


names2 = BUDGETED + ["gold_silver"] if "gold_silver" not in BUDGETED else list(BUDGETED)
names2 = [n for n in names2] + ["eth_carry"]
i2 = [names_B.index(n) for n in names2]
y2, info2 = v2_weights(S_all[np.ix_(i2, i2)], names2, book_c.universe, {"eth_carry": f_eth})
prop2_usd = {n: float(y2[k] * NAV) for k, n in enumerate(names2) if n != "eth_carry"}
cash2_usd = NAV - sum(prop2_usd.values()) - FIXED["eth_carry"] - FIXED["usdc_idle"]
print("PROPOSED v2", {k: round(v) for k, v in prop2_usd.items()}, "cash", round(cash2_usd), info2)
M["A6_v2_solve"] = {"usd": prop2_usd, "cash_or_borrow_usd": cash2_usd, **info2,
                    "gross_of_nav": (sum(prop2_usd.values()) + FIXED["eth_carry"]) / NAV}


def proposed_raw2(base):
    global prop_usd, cash_usd
    keep_p, keep_c = prop_usd, cash_usd
    prop_usd, cash_usd = prop2_usd, cash2_usd
    try:
        return proposed_raw(base)
    finally:
        prop_usd, cash_usd = keep_p, keep_c


PROP2 = {k: proposed_raw2(v) for k, v in PRIORS.items()}
sc_prop2 = score(PROP2["base_0.30"], "liquid")
prop2_row = {"move": "PROPOSED_v2", "desc": "POST-HOC: alpha standalone vol budgets, gold held, core balanced, cap 2x", **row_for("proposed_v2", PROP2)}
M["A6_v2_scorecard"] = {"summary": summary_row("proposed_v2", sc_prop2), "neff": neff_rows(sc_prop2), "streams": sc_prop2["streams"],
                        "sleeves": sleeve_table(sc_prop2), "environment": sc_prop2["environment"], "portfolio": sc_prop2["portfolio"],
                        "flags": sc_prop2["flags"], "row": prop2_row}
# repair pass: v2's own 2.0x cap binds below 15%, so its 'at 15%' figures need more gross than v2 allows
_v2_cap_bind = bool(info2["cap_binding"]) and prop2_row["gross_at_15"] > CAP2 + 1e-9
M["A6_v2_scorecard"]["at_15_attainable_under_v2_cap"] = not _v2_cap_bind
M["A6_v2_scorecard"]["at_cap"] = {"vol": prop2_row["vol"], "gross": prop2_row["gross_now"],
                                  "exp_return_prior_base_0.30": prop2_row["exp_now_base_0.30"],
                                  "exp_return_prior_low_0.25": prop2_row["exp_now_low_0.25"],
                                  "exp_return_prior_alpha_haircut": prop2_row["exp_now_alpha_haircut"]}
M["A6_v2_scorecard"]["at_15_note"] = (
    f"v2's 2.0x gross cap binds at {prop2_row['vol']:.1%} vol. Its 'at 15%' figures (row exp_at15_*, summary "
    f"exp_return_at_15_prior) need {prop2_row['gross_at_15']:.2f}x gross, ABOVE v2's own cap: NOT attainable under v2's rules. "
    f"The attainable figure is at the cap: {prop2_row['exp_now_base_0.30']:.1%} PRIOR-DRIVEN at {prop2_row['vol']:.1%} vol."
    if _v2_cap_bind else "v2 reaches 15% within its 2.0x cap")
M["post_hoc"].append({"item": "repair pass 2026-10-06: v2 'at 15%' figures flagged as above v2's own 2.0x cap; at-cap figures added",
                      "why": "counter-agent: the v2 '12.2% at 15%' implied 2.22x gross"})
print("PROPOSED v2 score", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prop2_row.items() if k in
      ("vol", "dr2", "balance_score", "btc_risk", "exp_now_base_0.30", "exp_now_low_0.25", "exp_now_alpha_haircut")})
for lab, s in (("R1_longest_common_daily", settings(window_years=20.0)), ("R2_weekly_3y", settings(freq="W")),
               ("R3_sample_daily_3y", settings(estimator="sample"))):
    scx = score(PROP2["base_0.30"], "liquid", st=s)
    M.setdefault("A6_v2_robustness", {})[lab] = {"vol": scx["portfolio"]["vol"], "dr2": scx["effective_bets"]["dr2"],
                                                 "balance_score": scx["environment"]["balance_score"]}
print("A6 v2 robustness", M["A6_v2_robustness"])
W_PROP2_STATIC = {n: v / NAV for n, v in prop2_usd.items()}

# routes
borrow = max(-cash2_usd, 0.0)
bs = borrow / NAV
borrow_v1 = max(-cash_usd, 0.0)
routes = [
    {"route": "IBKR margin (Pro, tiered)", "spread_over_rf": ibkr_spread_over_rf(borrow, RF), "cost_basis": "on borrowed $ only, blended by tier at each book's own loan size",
     "source": IBKR_CARD + f"; blended at v2's ${borrow:,.0f}: {ibkr_interest(borrow) / borrow:.3%} = rf + {ibkr_spread_over_rf(borrow, RF):.2%}; "
               f"at v1's ${borrow_v1:,.0f}: {ibkr_interest(borrow_v1) / borrow_v1:.3%} = rf + {ibkr_spread_over_rf(borrow_v1, RF):.2%} (rf = DTB3 {RF:.2%})",
     "confidence": "high", "spread_over_rf_v1": ibkr_spread_over_rf(borrow_v1, RF)},
    {"route": "Futures (ES/MES equity, ZN/ZB/UB Treasuries)", "spread_over_rf": 0.004, "cost_basis": "implied financing on notional; collateral stays in T-bills/BOXX",
     "source": "CME Group (search snippet, page not opened): equity index roll implied financing +81 bp over 3m SOFR (Q2-2026), +38 bp (Q2-2025); Treasury futures implied repo ~SOFR (judgement). Blend 0.4% = judgement; no TIPS future (TIPS stay cash/margin)",
     "confidence": "low"},
    {"route": "Levered balanced ETF: ALLW", "spread_over_rf": 0.0085 / 0.87 + 0.003, "cost_basis": "0.85% fee on the whole position / 0.87 borrowed per $ + embedded futures financing ~0.3%",
     "source": "SSGA ALLW 497K (0.85%), SSGA page exposures 2026-10-05 gross 1.87x (dalio_canon s6, factcheck C6 CONFIRMED)", "confidence": "medium"},
    {"route": "Levered balanced ETF: UPAR", "spread_over_rf": 0.0065 / 0.68 + 0.003, "cost_basis": "0.65% fee / ~0.68 borrowed per $ + embedded financing",
     "source": "AAII/issuer summary via search (not opened): expense 0.65%, targets 1.6-1.8x NAV (1.68x)", "confidence": "low"},
    {"route": "Return-stacked: RSSB (stocks+Treasuries ~2x)", "spread_over_rf": 0.0039 + 0.003, "cost_basis": "0.39% fee per ~1x borrowed + embedded financing",
     "source": "etfdb/AAII via search (not opened): expense 0.39%, $1 global equity + $1 Treasury futures per $1; no TIPS/commodities", "confidence": "low"},
]
for rt in routes:
    rt["annual_cost_usd_on_proposed_borrowing"] = borrow * rt["spread_over_rf"]
    rt["exp_return_v2_prior"] = prop2_row["exp_now_base_0.30"] + bs * (SPREAD - rt["spread_over_rf"])
    rt["annual_cost_usd_v1_borrowing"] = borrow_v1 * rt.get("spread_over_rf_v1", rt["spread_over_rf"])
M["post_hoc"].append({
    "item": "repair pass 2026-10-06: IBKR route costs now blended by tier at each book's own loan size",
    "why": (f"the route row applied the ~$1M blend (rf + {SPREAD:.2%}) to v2's ${borrow:,.0f} and v1's ${borrow_v1:,.0f}. "
            f"Tiered: v2 rf + {ibkr_spread_over_rf(borrow, RF):.2%} = ${ibkr_interest(borrow) - RF * borrow:,.0f}/yr over rf "
            f"(was ${borrow * SPREAD:,.0f}); v1 rf + {ibkr_spread_over_rf(borrow_v1, RF):.2%} = "
            f"${ibkr_interest(borrow_v1) - RF * borrow_v1:,.0f}/yr (was ${borrow_v1 * SPREAD:,.0f})."),
    "not_changed": (f"the predeclared modelling spread rf + {SPREAD:.2%} (the card's blend for a ~$1M loan) is KEPT for every "
                    "modelled return (A5 moves, v1/v2 rows, backtests, forward). It is conservative for loans above ~$1M "
                    f"(v2 by {SPREAD - ibkr_spread_over_rf(borrow, RF):.2%} and v1 by {SPREAD - ibkr_spread_over_rf(borrow_v1, RF):.2%} "
                    f"on borrowed $: v2's PRIOR-DRIVEN return is understated by ~{bs * (SPREAD - ibkr_spread_over_rf(borrow, RF)):.2%}/yr, "
                    f"v1's by ~{borrow_v1 / NAV * (SPREAD - ibkr_spread_over_rf(borrow_v1, RF)):.2%}/yr) and optimistic for loans under "
                    f"~$1M (e.g. $250k costs rf + {ibkr_spread_over_rf(250_000, RF):.2%})")})
M["A6_routes"] = {"borrowed_usd_v2": borrow, "borrowed_share_v2": bs, "borrowed_usd_v1": borrow_v1, "routes": routes}
report.write_rows(pd.DataFrame(routes), OUT / "a6_gearing_routes")

# budgets chart rows
brow = []
for s in sc_prop["streams"]:
    if abs(s["risk_share"]) < 1e-4 and abs(s["dollar_share"]) < 1e-4:
        continue
    brow.append({"stream": s["stream"], "usd": s["usd"], "dollar_share": s["dollar_share"], "risk_share": s["risk_share"],
                 "budget": dict(zip(BUDGETED, bud.tolist())).get(s["stream"], None)})
report.write_rows(pd.DataFrame(brow), OUT / "a6_proposed_v1_risk_budgets")
brow2 = [{"stream": s_["stream"], "label": slab(s_["stream"]), "usd": s_["usd"], "dollar_share": s_["dollar_share"], "risk_share": s_["risk_share"]}
         for s_ in sc_prop2["streams"] if abs(s_["risk_share"]) >= 1e-4 or abs(s_["dollar_share"]) >= 1e-4]
report.write_rows(pd.DataFrame(brow2), OUT / "a6_proposed_v2_risk_budgets")
bb = [b for b in brow2 if b["stream"] not in ("margin_loan",)][::-1]
fig, ax = plt.subplots(figsize=(8, 0.42 * len(bb) + 1.4))
y = np.arange(len(bb))
ax.barh(y + 0.19, [100 * b["dollar_share"] for b in bb], height=0.36, color=SER[0], label="dollar share (of NAV)")
ax.barh(y - 0.19, [100 * b["risk_share"] for b in bb], height=0.36, color=SER[1], label="risk share")
ax.set_yticks(y, [slab(b["stream"]) for b in bb])
report._style(ax, "Proposed v2 (post-hoc) liquid book at 15% vol: dollars vs risk", "% of NAV (sums > 100: geared)", "")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "a6_proposed_v2_risk_budgets.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# environment chart: liquid now / post-revert / cumulative moves / proposed
envrows = []
a14 = json.load(open(OUT / "metrics_a1_a4.json"))
for lab, env in (("liquid now", a14["A1"]["liquid_now"]["environment"]), ("after M0-M8", score(CUM_FINAL, "liquid")["environment"]),
                 ("proposed v1 @15% (pre-declared)", sc_prop["environment"]), ("proposed v2 @15% (post-hoc)", sc_prop2["environment"])):
    envrows.append({"book": lab, **{b: env["risk_share"][b] for b in BOXES}, "unmapped": env["unmapped_risk_share"],
                    "balance_score": env["balance_score"]})
E = pd.DataFrame(envrows)
report.write_rows(E, OUT / "a6_environment_boxes")
fig, ax = plt.subplots(figsize=(8, 3.6))
xb = np.arange(len(BOXES) + 1)
wd = 0.2
for i, rr in E.iterrows():
    ax.bar(xb + (i - 1.5) * wd, [100 * rr[b] for b in BOXES] + [100 * rr["unmapped"]], width=wd - 0.02, color=SER[i], label=rr["book"])
ax.axhline(25, color=INK2, lw=0.8, ls="--")
ax.set_xticks(xb, list(BOXES) + ["unmapped"])
report._style(ax, "Share of risk by All Weather box (target 25% each)", "", "% of risk")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
fig.tight_layout(); fig.savefig(OUT / "a6_environment_boxes.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)


# ---------------------------------------------------------------------------------------------------
# return panels
# ---------------------------------------------------------------------------------------------------
U = book_prop.universe
CUR_STREAMS = ["SPY", "AVUV", "AVDV", "AVEM", "QUAL", "physical_metals", "PHYS", "PSLV", "GH", "TWST", "TEM", "LLY", "VIST",
               "JOINN", "BOT", "FTZFF", "SHAZ", "TSLA", "KMLM", "BTC", "composer_hg", "composer_kmlm", "composer_crash",
               "composer_vixhyg", "BOXX", "BIL"]
PROP_STREAMS = BUDGETED
FACTORS = ["SPY", "TLT", "GLD", "DBC"]
NATURAL = {"AVUV": "IWM", "AVDV": "EFA", "AVEM": "VEIEX", "QUAL": "SPY", "PHYS": "GLD", "PSLV": "SLV"}
leaf_names = sorted(set(U.leaves(CUR_STREAMS + PROP_STREAMS + ["IWM", "EFA", "VEIEX", "IEF", "GLD", "SLV", "TLT", "DBC"])[0]))
levels, provL = loader.stream_levels(U, leaf_names)
levels = levels.loc[:"2026-09-30"]
LR = aligned_returns(levels, "D")
dtb3 = loader.fred("DTB3").values
start_B = pd.Timestamp("2006-05-01")
LR = LR.loc[LR.index >= start_B]
rf_d = tbill_period_returns(dtb3, LR.index)
first_real = {c: LR[c].first_valid_index() for c in LR.columns}

# backfill (BT_B panel)
LB = LR.copy()
fill_info = {}
for c, px in NATURAL.items():
    m = LB[c].isna()
    LB.loc[m, c] = LB.loc[m, px]
    fill_info[c] = f"natural proxy {px} before {first_real[c].date()}"
for c in ("BIL", "BOXX"):
    m = LB[c].isna()
    if c == "BOXX":
        mb = m & LB["BIL"].notna() & (LB.index >= first_real["BIL"])
        LB.loc[mb, c] = LR.loc[mb, "BIL"]
        m = LB[c].isna()
    LB.loc[m, c] = rf_d[m]
    fill_info[c] = f"BIL then DTB3 cash before {first_real[c].date()}"
wk = (1 + LR).resample("W-FRI").prod(min_count=1) - 1
betas = {}
for c in LB.columns:
    if c in FACTORS or not LB[c].isna().any():
        continue
    d = wk[[c] + FACTORS].dropna()
    X, yv = d[FACTORS].to_numpy(), d[c].to_numpy()
    b = np.linalg.lstsq(X, yv, rcond=None)[0]
    r2 = 1 - ((yv - X @ b) ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
    betas[c] = {**dict(zip(FACTORS, b.tolist())), "r2_weekly": float(r2), "n_weeks": len(d)}
    m = LB[c].isna()
    LB.loc[m, c] = LB.loc[m, FACTORS].to_numpy() @ b
    fill_info[c] = f"factor replica before {first_real[c].date()} (weekly R2 {r2:.2f})"
assert not LB.isna().any().any(), LB.isna().sum()[LB.isna().sum() > 0]
M["panel_B"] = {"start": str(LB.index[0].date()), "end": str(LB.index[-1].date()), "n": len(LB),
                "first_real": {k: str(v.date()) for k, v in first_real.items()}, "fill": fill_info, "replica_betas": betas}
ppyB = infer_periods_per_year(LB.index)


def stream_panel(leafR, streams, rf_series):
    out = {}
    for s in streams:
        if s in leafR.columns:
            out[s] = leafR[s]
        else:
            out[s] = U.series_returns(s, leafR, rf_series, ppyB)
    return pd.DataFrame(out)


ALL_STREAMS = list(dict.fromkeys(CUR_STREAMS + PROP_STREAMS + ["IEF"]))
PB = stream_panel(LB, ALL_STREAMS, rf_d)
PA_full = stream_panel(LR, ALL_STREAMS, rf_d)
PA = PA_full.dropna(how="any")
PA = PA.loc[PA.index >= pd.Timestamp("2023-04-20")]
rfA = rf_d.reindex(PA.index)
ppyA = infer_periods_per_year(PA.index)
M["panel_A"] = {"start": str(PA.index[0].date()), "end": str(PA.index[-1].date()), "n": len(PA), "ppy": ppyA}
print("panel A", M["panel_A"], "panel B", M["panel_B"]["start"], len(PB))

# current (post-revert) constant weights over CUR_STREAMS; cash (incl HL USDC/ETH carry) earns rf
sc_cur = score(RPR, "liquid")
wcur = {s["stream"]: s["dollar_share"] for s in sc_cur["streams"]}
W_CUR = {s: wcur.get(s, 0.0) for s in CUR_STREAMS}
M["current_weights_bt"] = W_CUR
W_PROP_STATIC = {n: prop_usd[n] / NAV for n in BUDGETED}


def const_alloc(wmap):
    def f(S, win):
        return np.array([wmap.get(c, 0.0) for c in win.columns])
    f.__name__ = "constant_mix_hindsight"
    return f


def prop_alloc(S, win):
    cols = list(win.columns)
    names = [c for c in cols if c in BUDGETED]
    idx = [cols.index(c) for c in names]
    Sb = S[np.ix_(idx, idx)]
    w, _, _ = solve_budget_weights(Sb, names, U)
    L = TARGET / math.sqrt(float(w @ Sb @ w))
    out = np.zeros(len(cols))
    out[idx] = L * w
    return out


prop_alloc.__name__ = "proposed_risk_budget_walk_forward"


def prop2_alloc(S, win):
    cols = list(win.columns)
    names = [c for c in cols if c in names2]
    idx = [cols.index(c) for c in names]
    y, _ = v2_weights(S[np.ix_(idx, idx)], names, U)
    out = np.zeros(len(cols)); out[idx] = y
    return out


prop2_alloc.__name__ = "proposed_v2_walk_forward"
P2_STREAMS = [n for n in names2 if n != "eth_carry"]


def bt(R, alloc, rf, ppy, start_when="all"):
    cfg = BacktestConfig(allocator=alloc, window=252, min_periods=252, estimator="lw_cc", rebalance="M", cost_bps=5.0,
                         financing_spread=SPREAD, max_leverage=3.0, periods_per_year=ppy, start_when=start_when)
    return run_backtest(R, cfg, rf=rf)


res = {}
res["A_current_const"] = bt(PA[CUR_STREAMS], const_alloc(W_CUR), rfA, ppyA)
res["A_proposed_wf"] = bt(PA[PROP_STREAMS], prop_alloc, rfA, ppyA)
res["A_proposed2_wf"] = bt(PA[P2_STREAMS], prop2_alloc, rfA, ppyA)
res["A_spy"] = bt(PA[["SPY"]], const_alloc({"SPY": 1.0}), rfA, ppyA)
res["B_current_const"] = bt(PB[CUR_STREAMS], const_alloc(W_CUR), rf_d, ppyB)
res["B_proposed_wf"] = bt(PB[PROP_STREAMS], prop_alloc, rf_d, ppyB)
res["B_proposed2_wf"] = bt(PB[P2_STREAMS], prop2_alloc, rf_d, ppyB)
res["B_spy"] = bt(PB[["SPY"]], const_alloc({"SPY": 1.0}), rf_d, ppyB)
res["B_6040"] = bt(PB[["SPY", "IEF"]], const_alloc({"SPY": 0.6, "IEF": 0.4}), rf_d, ppyB)


def common_metrics(keys, prefix):
    t0 = max(res[k].equity.index[0] for k in keys)
    out = {}
    for k in keys:
        rr = res[k].returns.loc[res[k].returns.index > t0]
        out[k] = performance_metrics(rr, periods_per_year=res[k].config["periods_per_year"], rf=rf_d.reindex(rr.index),
                                     base_value=1.0)
        out[k]["mean_gross"] = float(res[k].leverage.loc[t0:].mean())
        out[k]["max_gross"] = float(res[k].leverage.loc[t0:].max())
    return t0, out


# DIAGNOSTIC (post-hoc, labelled): current mix at EQUAL RISK (15%): risky streams x L, cash-like deployed first
L_CUR15 = rows_cum[1]["L_to_15_cash_first"]
W_CUR15 = {k: (v if k in ("BOXX", "BIL") else v * L_CUR15) for k, v in W_CUR.items()}
_excess = sum(W_CUR15.values()) - sum(W_CUR.values())
W_CUR15["BOXX"] = max(W_CUR15["BOXX"] - _excess, 0.0)
M["post_hoc"].append({"item": f"diagnostic 'current @15%' book (risky weights x {L_CUR15:.3f}, funded from BOXX/cash), added after seeing results",
                      "why": "the current book runs at ~10% vol; comparisons with the 13.5-15% proposals need an equal-risk version"})
res["A_current15_const"] = bt(PA[CUR_STREAMS], const_alloc(W_CUR15), rfA, ppyA)
res["B_current15_const"] = bt(PB[CUR_STREAMS], const_alloc(W_CUR15), rf_d, ppyB)
# DIAGNOSTIC (post-hoc, labelled): how much of the current mix's backtest is the Composer in-sample series
W_CUR_EXC = {k: (0.0 if k.startswith("composer_") else v) for k, v in W_CUR.items()}
res["A_current_exComposer"] = bt(PA[CUR_STREAMS], const_alloc(W_CUR_EXC), rfA, ppyA)
res["B_current_exComposer"] = bt(PB[CUR_STREAMS], const_alloc(W_CUR_EXC), rf_d, ppyB)
M["post_hoc"].append({"item": "diagnostic backtests 'current ex-Composer' (Composer weights -> cash at rf), added after seeing BT results",
                      "why": "to size how much of the current mix's backtest comes from Composer IN-SAMPLE series"})
# DIAGNOSTIC (post-hoc, repair pass): the same for the pre-declared v1 walk-forward (v1 solves ~38% of NAV into Composer)
COMPOSER_STREAMS = {"composer_momentum", "composer_hg", "composer_kmlm", "composer_crash", "composer_vixhyg"}


def ex_composer(alloc):
    def f(S, win):
        w = alloc(S, win)
        return np.array([0.0 if c in COMPOSER_STREAMS else x for c, x in zip(win.columns, w)])
    f.__name__ = alloc.__name__ + "_exComposer"
    return f


res["A_proposed_wf_exComposer"] = bt(PA[PROP_STREAMS], ex_composer(prop_alloc), rfA, ppyA)
res["B_proposed_wf_exComposer"] = bt(PB[PROP_STREAMS], ex_composer(prop_alloc), rf_d, ppyB)
M["post_hoc"].append({"item": "repair pass 2026-10-06: diagnostic backtests 'proposed v1 ex-Composer' (v1 walk-forward weights each month, "
                              "Composer weights -> cash at rf, nothing re-solved)",
                      "why": "counter-agent: v1's 30.5% BT_A CAGR leans on Composer IN-SAMPLE backtests (v1 solves ~38% of NAV into Composer)"})
tA, metA = common_metrics(["A_current_const", "A_proposed_wf", "A_proposed2_wf", "A_spy", "A_current_exComposer", "A_current15_const",
                           "A_proposed_wf_exComposer"], "A")
tB, metB = common_metrics(["B_current_const", "B_proposed_wf", "B_proposed2_wf", "B_spy", "B_6040", "B_current_exComposer", "B_current15_const",
                           "B_proposed_wf_exComposer"], "B")
_comp_v1 = sum(prop_usd[k] for k in prop_usd if k in COMPOSER_STREAMS)
_live_share = {slug: float((PA.index[PA.index > tA] >= pd.Timestamp(d)).mean()) for slug, d in COMPOSER_LIVE_START.items()}
_IS = ("IN-SAMPLE: Composer = in-sample backtests before live (HG 2025-12-05; KMLM/Crash 2026-07-07; VIX 2026-07-22); "
       f"live share of this window's days: HG {_live_share['hg']:.0%}, KMLM {_live_share['kmlm']:.0%}, Crash {_live_share['crash']:.0%}, "
       f"VIX {_live_share['vixhyg']:.0%}")
ROW_LABELS_A = {
    "A_current_const": "IN-SAMPLE (Composer backtests before live) + HINDSIGHT (today's mix replayed); not a forecast",
    "A_proposed_wf": f"IN-SAMPLE Composer: pre-declared v1 walk-forward, ~{_comp_v1 / NAV:.0%} of NAV in Composer at today's solve; not a forecast",
    "A_proposed2_wf": "POST-HOC (v2 declared after v1's results) + IN-SAMPLE Composer; not a forecast",
    "A_spy": "SPY buy-and-hold, real data",
    "A_current_exComposer": "POST-HOC DIAGNOSTIC: current mix, Composer weights -> cash at rf (HINDSIGHT mix)",
    "A_current15_const": "POST-HOC DIAGNOSTIC: current mix scaled to 15% vol (HINDSIGHT mix) + IN-SAMPLE Composer",
    "A_proposed_wf_exComposer": "POST-HOC DIAGNOSTIC: v1 walk-forward weights, Composer weights -> cash at rf"}
ROW_LABELS_B = {
    "B_current_const": "IN-SAMPLE + HINDSIGHT mix; pre-real-data history = factor replicas whose betas are fit on the FULL sample to 2026-09-30 (look-ahead)",
    "B_proposed_wf": "pre-declared v1 walk-forward on the backfilled panel (full-sample replica betas: look-ahead)",
    "B_proposed2_wf": "POST-HOC v2 walk-forward on the backfilled panel (full-sample replica betas: look-ahead)",
    "B_spy": "SPY buy-and-hold, real data", "B_6040": "60/40 SPY/IEF monthly, real data",
    "B_current_exComposer": "POST-HOC DIAGNOSTIC: current mix, Composer weights -> cash at rf",
    "B_current15_const": "POST-HOC DIAGNOSTIC: current mix scaled to 15% vol",
    "B_proposed_wf_exComposer": "POST-HOC DIAGNOSTIC: v1 walk-forward weights, Composer weights -> cash at rf"}
M["BT_A"] = {"start": str(tA.date()), "label": _IS, "composer_live_share_of_window": _live_share,
             "v1_composer_share_of_nav_today": _comp_v1 / NAV, "row_labels": ROW_LABELS_A, "metrics": metA}
M["BT_B"] = {"start": str(tB.date()),
             "label": "IN-SAMPLE with declared proxies/replicas; replica betas fit on the full sample (look-ahead); Composer before its "
                      "first real return = factor replica (no switching logic)",
             "row_labels": ROW_LABELS_B, "metrics": metB}
for k, v in {**metA, **metB}.items():
    print(k, {kk: round(v[kk], 3) for kk in ("cagr", "vol", "sharpe", "max_drawdown") if kk in v}, "gross", round(v["mean_gross"], 2))

LBL = {"A_proposed_wf_exComposer": "proposed v1 ex-Composer (diag., post-hoc)", "B_proposed_wf_exComposer": "proposed v1 ex-Composer (diag., post-hoc)",
       "A_current_exComposer": "current ex-Composer (diag., post-hoc)", "B_current_exComposer": "current ex-Composer (diag., post-hoc)",
       "A_current15_const": "current mix @15% (diag., hindsight)", "B_current15_const": "current mix @15% (diag., hindsight)", "A_current_const": "current liquid mix (constant, hindsight)", "A_proposed_wf": "proposed v1 (pre-declared, walk-forward)",
       "A_proposed2_wf": "proposed v2 (post-hoc, walk-forward)", "B_proposed2_wf": "proposed v2 (post-hoc, walk-forward)",
       "A_spy": "SPY", "B_current_const": "current liquid mix (constant, hindsight)", "B_proposed_wf": "proposed v1 (pre-declared, walk-forward)",
       "B_spy": "SPY", "B_6040": "60/40 SPY/IEF"}
for tag, keys, t0 in (("bt_a", ["A_proposed2_wf", "A_current_const", "A_proposed_wf", "A_spy", "A_current_exComposer", "A_proposed_wf_exComposer"], tA), ("bt_b", ["B_proposed2_wf", "B_current_const", "B_proposed_wf", "B_spy", "B_6040", "B_current15_const"], tB)):
    curves = {LBL[k]: res[k].equity.loc[t0:] for k in keys}
    ttl = ("IN-SAMPLE (Composer = backtests before live), real data, " if tag == "bt_a" else "IN-SAMPLE, declared proxies/replicas, ") + f"{t0:%Y-%m}..2026-09"
    report.equity_curves(OUT, curves, name=f"a6_{tag}_equity", title=ttl + " (log)")
    report.drawdowns(OUT, curves, name=f"a6_{tag}_drawdown")
    lev = pd.DataFrame({LBL[k]: res[k].leverage.loc[t0:] for k in keys if "proposed" in k})
    lev.index.name = "date"
    report.write_rows(lev.reset_index().assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d")), OUT / f"a6_{tag}_proposed_gross")
fig, ax = plt.subplots(figsize=(8, 3.2))
for i_, k_ in enumerate(("B_proposed2_wf", "B_proposed_wf")):
    g = res[k_].leverage.loc[tB:]
    ax.plot(g.index, g.to_numpy(), color=SER[0 if i_ == 0 else 2], lw=1.6, label=LBL[k_])
ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
report._style(ax, "Proposed walk-forward: gross exposure set by trailing-vol gearing", "", "gross (x NAV)")
fig.tight_layout(); fig.savefig(OUT / "a6_bt_b_proposed_gross.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# ---------------------------------------------------------------------------------------------------
# stress replays (BT_B panel, today's weights, buy-and-hold)
# ---------------------------------------------------------------------------------------------------
sc_now = score(PRIORS["base_0.30"], "liquid")
w_now = {s["stream"]: s["dollar_share"] for s in sc_now["streams"] if s["stream"] in CUR_STREAMS}
BOOKS = {"liquid now": w_now, "liquid post-revert": W_CUR, "current @15% (diag.)": W_CUR15, "proposed v1 @15%": W_PROP_STATIC, "proposed v2 @15%": W_PROP2_STATIC, "SPY": {"SPY": 1.0}}
strows = []
for sk, (a, b, desc) in SCENARIOS.items():
    for bk, wmap in BOOKS.items():
        rr = replay_scenario(PB, wmap, a, b, rebalance="none", rf_period=rf_d, label=f"{bk} {sk}")
        win = PB.loc[(PB.index > pd.Timestamp(a)) & (PB.index <= pd.Timestamp(b))]
        # composites: synthetic share = weight of leaves without real data at the window start
        syn = 0.0
        for k, v in wmap.items():
            leaves = U.exposure(k).coefs
            frac = sum(a_ for l, a_ in leaves.items() if first_real.get(l) is not None and first_real[l] > win.index[0])
            syn += abs(v) * frac
        strows.append({"scenario": sk, "window": f"{a}..{b}", "book": bk, "cum_return": rr["cum_return"],
                       "max_drawdown": rr["max_drawdown"], "worst_day": rr["worst_day"], "weight_on_proxy_or_replica": syn,
                       "top_contrib": sorted(rr["contributions"].items(), key=lambda kv: kv[1])[:3]})
ST = pd.DataFrame(strows)
report.write_rows(ST.assign(top_contrib=ST.top_contrib.astype(str)), OUT / "a6_stress")
M["stress"] = strows
print(ST[["scenario", "book", "cum_return", "max_drawdown", "weight_on_proxy_or_replica"]].round(3).to_string())
fig, ax = plt.subplots(figsize=(8.5, 3.8))
sc_list = list(SCENARIOS)
xs = np.arange(len(sc_list))
wd = 0.14
for i, bk in enumerate(BOOKS):
    vals = [100 * ST[(ST.scenario == s) & (ST.book == bk)].max_drawdown.iloc[0] for s in sc_list]
    ax.bar(xs + (i - 2.5) * wd, vals, width=wd - 0.02, color=SER[i], label=bk)
ax.set_xticks(xs, ["2008 GFC", "2020 Covid", "2022 inflation"])
ax.axhline(0, color=INK2, lw=0.8)
report._style(ax, "Stress replays: max drawdown with today's weights (buy-and-hold)", "", "max drawdown (%)")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
fig.tight_layout(); fig.savefig(OUT / "a6_stress.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

# ---------------------------------------------------------------------------------------------------
# forward bootstrap (weekly, recentred on the PRIOR means; shape is in-sample)
# ---------------------------------------------------------------------------------------------------
WB = (1 + PB).resample("W-FRI").prod() - 1
WB = WB.iloc[1:-1] if WB.index[-1] > PB.index[-1] else WB.iloc[1:]
mu_prior = {}
for c in WB.columns:
    e = U.exposure(c)
    mu = 0.0
    for l, a_ in e.coefs.items():
        mu += a_ * (RF if l in ("BOXX", "BIL") else RF + 0.30 * VOLS[l])
    mu_prior[c] = mu
H = WB - WB.mean() + pd.Series(mu_prior) / 52.0
cfg = SimConfig(years=10, periods_per_year=52, n_paths=10_000, seed=20261006, method="bootstrap", mean_block=8)
fw = {}
for bk, wmap in (("liquid post-revert", W_CUR), ("current @15% (diag.)", W_CUR15), ("proposed v1 @15%", W_PROP_STATIC), ("proposed v2 @15%", W_PROP2_STATIC), ("SPY", {"SPY": 1.0})):
    wv = np.array([wmap.get(c, 0.0) for c in H.columns])
    c = 1 - wv.sum()
    fr = run_forward(wv, cfg, history=H, rf=RF, spread=SPREAD, cash_weight=c, spread_weight=max(-c, 0.0))
    stt = fr.stats
    fw[bk] = {k: v for k, v in stt.items() if k != "_wealth_bands"}
    if bk == "proposed v2 @15%":
        report.forward_fan(OUT, stt["_wealth_bands"], 52, name="a6_forward_fan_proposed_v2")
    print("FWD", bk, {k: stt[k] for k in ("mean_cagr", "p_loss_horizon")}, stt["cagr_quantiles"], stt["max_dd_quantiles"]["0.05"])
M["forward"] = {"config": vars(cfg) if hasattr(cfg, "__dict__") else str(cfg), "books": fw,
                "history": f"{H.index[0].date()}..{H.index[-1].date()} weekly n={len(H)}",
                "mu_prior_annual": mu_prior}
fr_rows = []
for bk, d in fw.items():
    for q, v in d["cagr_quantiles"].items():
        fr_rows.append({"book": bk, "stat": "cagr", "quantile": q, "value": v})
    for q, v in d["max_dd_quantiles"].items():
        fr_rows.append({"book": bk, "stat": "max_dd", "quantile": q, "value": v})
FR = pd.DataFrame(fr_rows)
report.write_rows(FR, OUT / "a6_forward_quantiles")
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
for ax, stat, ttl in ((axs[0], "cagr", "10y CAGR (prior-centred bootstrap)"), (axs[1], "max_dd", "10y max drawdown")):
    for i, bk in enumerate(fw):
        d = FR[(FR.book == bk) & (FR.stat == stat)].sort_values("quantile")
        q = d.value.to_numpy() * 100
        ax.plot([q[0], q[-1]], [i, i], color=SER[i], lw=2)
        ax.plot([q[1], q[3]], [i, i], color=SER[i], lw=6, solid_capstyle="butt")
        ax.plot(q[2], i, "o", color=report.SURFACE, mec=SER[i], ms=8, mew=2)
    ax.set_yticks(range(len(fw)), list(fw))
    report._style(ax, ttl, "% (line p5-p95, bar p25-p75, dot median)", "")
fig.tight_layout(); fig.savefig(OUT / "a6_forward_quantiles.png", dpi=150, facecolor=report.SURFACE); plt.close(fig)

report.write_json(M, OUT / "metrics_a5_a6.json")
print("done")
