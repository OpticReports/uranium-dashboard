"""No-leverage follow-up, N1 (corrected liquid book, variants D/P) and N2 (unlevered balanced liquid proposal).

Run: cd holygrail-engine && HG_OFFLINE=1 python results/casey-2026-10/no-leverage/liquid_n1_n2.py
Parameters: predeclared_params.json in this folder (declared before any result). Reuses the current-book helpers
(results/casey-2026-10/current/hg_common.py) and their estimation settings (daily, trailing 3y, lw_cc).
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "current"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

from hg_common import (OUT as CUR_OUT, BookView, Position, base_raw, build, drop_zero, loader, neff_rows, pos,  # noqa: E402
                       prepare_moments, revert_loans, score, set_prior, settings, summary_row)
from holygrail import report  # noqa: E402
from holygrail.allocate import quadrant_balance, risk_budget_weights  # noqa: E402
from holygrail.backtest import BacktestConfig, run_backtest  # noqa: E402
from holygrail.data import tbill_period_returns  # noqa: E402
from holygrail.environments import BOXES, exposures_from_mapping, stream_box_mapping  # noqa: E402
from holygrail.estimate import aligned_returns, infer_periods_per_year  # noqa: E402
from holygrail.forward import SCENARIOS, replay_scenario  # noqa: E402
from holygrail.metrics import drawdown, performance_metrics  # noqa: E402

PP = json.loads((HERE / "predeclared_params.json").read_text())
VOLS = json.load(open(CUR_OUT / "data" / "prior_vols.json"))
RF = json.load(open(CUR_OUT / "data" / "rf.json"))["rf"]
SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
SHEET_NW = 19_765_406.0
PLUG = "Short-term 16% loans (out of BOXX)"
DOMINION = "Film Dominion bridge (returned 2026-09-25)"
COMMIT = {k: float(v) for k, v in PP["N1"]["commitments"].items() if k in ("Series X uncalled", "DexMat", "Jarod Production")}
COMMIT_USD = sum(COMMIT.values())          # 410,200
COMMIT_SHEET = float(PP["N1"]["commitments"]["sheet_total_alongside"])   # 435,200
ALPHA_HAIRCUT = {"composer_hg", "composer_kmlm", "composer_crash", "composer_vixhyg", "BTC", "GH", "TWST", "TEM", "LLY",
                 "VIST", "JOINN", "BOT", "FTZFF", "SHAZ", "TSLA"}
CASHLIKE = {"BOXX", "BIL", "cash", "usdc_idle", "st_loans_16", "evergrande", "margin_loan"}
HL_NAMES = {"HL ETH carry (UETH spot + perp short)", "HL spot USDC", "HL BTC trend long (notional)"}
CASH_FUND_ORDER = ["U84 BOXX", "U26 BIL", "U26 settled cash", "U84 settled cash", "U358 cash", "Cash/stables ex-Hyperliquid",
                   "U26 NAV residual"]
M: dict = {"params_file": "predeclared_params.json", "post_hoc": [], "rf": RF}
CHARTS: list = []

SLEEVE = {"BOXX": "cash-like", "BIL": "cash-like", "cash": "cash-like", "usdc_idle": "cash-like", "st_loans_16": "cash-like",
          "evergrande": "cash-like", "SPY": "equity beta", "AVUV": "equity beta", "AVDV": "equity beta", "AVEM": "equity beta",
          "QUAL": "equity beta", "core_equity": "equity beta", "TLT": "long Treasuries", "TIP": "TIPS", "DBC": "commodities",
          "PHYS": "gold & silver", "PSLV": "gold & silver", "physical_metals": "gold & silver", "gold_silver": "gold & silver",
          "KMLM": "KMLM trend", "BTC": "BTC", "eth_carry": "HL ETH carry",
          **{c: "Composer (one sleeve)" for c in ("composer_hg", "composer_kmlm", "composer_crash", "composer_vixhyg", "composer_all")},
          **{c: "single names" for c in ("GH", "TWST", "TEM", "LLY", "VIST", "JOINN", "BOT", "FTZFF", "SHAZ", "TSLA", "single_names")}}


def A(v, s, c="low"):
    return {"value": float(v), "source": s, "confidence": c}


def prior_raw(sharpe=0.30, haircut=None):
    r = base_raw(spliced=True)
    set_prior(r, VOLS, RF, sharpe, haircut)
    return r


PRIORS = {"base_0.30": prior_raw(), "alpha_haircut": prior_raw(0.30, ALPHA_HAIRCUT)}


# ------------------------------------------------------------------ N1 variants (predeclared)
def apply_variant(raw, v):
    r = copy.deepcopy(raw)
    out, rate = (200_000.0, 0.16) if v == "D" else (129_166.0, 0.15)
    p = pos(r, PLUG)
    p["value_usd"] = out
    p["note"] = f"variant {v}: {'Dominion' if v == 'D' else 'Plus One'} outstanding (~45d), the other already in IBKR BOXX live"
    st = r["streams"]["st_loans_16"]
    st["default"]["coupon"] = A(rate * 45 / 365 + RF * 320 / 365,
                                f"variant {v}: {rate:.0%} p.a. x 45/365 + rf x 320/365 (loan then BOXX); 'annualised' reading kept (flag)", "medium")
    r["positions"] = [q for q in r["positions"] if q["name"] != DOMINION]
    return r


def pay_commitments(raw, usd):
    c = pos(raw, "Cash/stables ex-Hyperliquid")
    t = min(usd, c["value_usd"]); c["value_usd"] -= t; usd -= t
    b = pos(raw, "U84 BOXX")
    t = min(usd, b["value_usd"]); b["value_usd"] -= t; usd -= t
    assert usd < 1e-6, usd


def sleeves_of(sc):
    out = {}
    for s in sc["streams"]:
        k = SLEEVE.get(s["stream"], s["stream"])
        d = out.setdefault(k, {"sleeve": k, "usd": 0.0, "dollar_share": 0.0, "risk_share": 0.0})
        d["usd"] += s["usd"]; d["dollar_share"] += s["dollar_share"]; d["risk_share"] += s["risk_share"]
    return out


def liquid_metrics(sc):
    nr = neff_rows(sc)
    pick = lambda tag: next(v["value"] for k, v in nr.items() if k.startswith(tag))  # noqa: E731
    sl = sleeves_of(sc)
    st = {s["stream"]: s for s in sc["streams"]}
    env = sc["environment"]
    return {"nav_usd": sc["nav_usd"], "vol": sc["portfolio"]["vol"], "dr2": sc["effective_bets"]["dr2"],
            "neff_equal_rho": pick("(a)"), "neff_pca_entropy": pick("(c)"), "neff_inv_hhi_prc": pick("(b)"),
            "neff_min_torsion": pick("(d)"), "btc_risk_share": st.get("BTC", {}).get("risk_share", 0.0),
            "btc_dollar_share": st.get("BTC", {}).get("dollar_share", 0.0),
            "cash_like_share": sl.get("cash-like", {}).get("dollar_share", 0.0), "cash_like_usd": sl.get("cash-like", {}).get("usd", 0.0),
            **{f"box_{b}": env["risk_share"][b] for b in BOXES}, "box_unmapped": env["unmapped_risk_share"],
            "balance_score": env["balance_score"], "exp_return_prior": sc["portfolio"]["exp_return"],
            "gross": 1.0 - sl.get("cash-like", {}).get("dollar_share", 0.0)}


def totals(raw):
    ps = raw["positions"]
    return {"whole_usd": sum(p["value_usd"] for p in ps),
            "investable_usd": sum(p["value_usd"] for p in ps if p.get("investable", True)),
            "liquid_usd": sum(p["value_usd"] for p in ps if p.get("liquidity", "liquid") == "liquid")}


base = PRIORS["base_0.30"]
N1 = {"sheet_net_worth": SHEET_NW, "book_as_built": totals(base), "variants": {}}
rows_n1 = []
sc_old = score(base, "liquid")
rows_n1.append({"variant": "old book", "case": "liquid now (plug $310,876)", **liquid_metrics(sc_old)})
VAR_RAW = {}
for v in ("D", "P"):
    rv = apply_variant(base, v)
    VAR_RAW[v] = {k: apply_variant(r, v) for k, r in PRIORS.items()}
    t = totals(rv)
    inv = score(rv, "investable")
    d = {"outstanding_loan_usd": pos(rv, PLUG)["value_usd"], **t, "sheet_overstatement_usd": SHEET_NW - t["whole_usd"],
         "investable_vol": inv["portfolio"]["vol"], "investable_dr2": inv["effective_bets"]["dr2"], "cases": {}}
    pr = copy.deepcopy(rv); revert_loans(pr)
    cases = {"liquid now (loan outstanding)": rv, "liquid post-revert (loan back in BOXX)": pr}
    for lbl, usd in (("net of commitments $410,200", COMMIT_USD), ("net of sheet commitments $435,200", COMMIT_SHEET)):
        r2 = copy.deepcopy(pr); pay_commitments(r2, usd); cases[f"post-revert, {lbl}"] = r2
    for k, r in cases.items():
        sc = score(r, "liquid")
        mtr = liquid_metrics(sc)
        d["cases"][k] = mtr
        rows_n1.append({"variant": v, "case": k, **mtr})
        print("N1", v, k, {a: round(b, 4) for a, b in mtr.items() if a in ("nav_usd", "vol", "dr2", "btc_risk_share", "cash_like_share", "balance_score")})
    N1["variants"][v] = d
M["N1"] = N1
report.write_rows(pd.DataFrame(rows_n1), HERE / "n1_corrected_liquid")

# ------------------------------------------------------------------ N2 proposal
BUD = PP["N2"]["risk_budgets_of_budgeted_risk"]
CORE = ["core_equity", "TLT", "TIP", "DBC", "gold_silver"]
ALPHA = {"BTC": BUD["BTC"], "composer_all": BUD["composer_all"], "KMLM": BUD["KMLM"], "single_names": BUD["single_names"]}
BUDGETED = CORE + list(ALPHA)
FIX_ETH, FIX_USDC = 30_110.0, 67_322.59


def norm(d):
    t = sum(d.values()); return {k: x / t for k, x in d.items()}


def mixes(r):
    val = {p["name"]: p["value_usd"] for p in r["positions"]}
    return {"core_equity": {"SPY": val["U26 SPY"], "AVUV": val["U84 AVUV"], "AVDV": val["U84 AVDV"], "AVEM": val["U84 AVEM"], "QUAL": val["U84 QUAL"]},
            "gold_silver": {"physical_metals": val["Physical metals"], "PHYS": val["U84 PHYS"], "PSLV": val["U84 PSLV"]},
            "single_names": {"GH": val["U26 GH"], "TWST": val["U26 TWST"], "TEM": val["U26 TEM"], "LLY": val["U26 LLY"],
                             "VIST": val["U84 VISTAA (as VIST)"], "JOINN": val["U84 Joinn Labs 603127"], "BOT": val["U84 BOT RoboStrategy"],
                             "FTZFF": val["U84 FTZFF Fitzroy Minerals"], "SHAZ": val["U84 SHAZ SharonAI"], "TSLA": val["U84 TSLA"]},
            "composer_all": {"composer_hg": val["Composer hg"], "composer_kmlm": val["Composer kmlm"],
                             "composer_crash": val["Composer crash"], "composer_vixhyg": val["Composer vixhyg"]}}


AC = {"core_equity": "equity", "gold_silver": "gold", "single_names": "equity", "composer_all": None}


def add_composites(r, mx):
    for k, comp in mx.items():
        st = {"type": "composite", "components": norm(comp), "description": f"{k} at the current $ mix (N2)"}
        if AC[k]:
            st["asset_class"] = AC[k]
        else:
            # Composer as ONE sleeve: boxes from its parts (HG/KMLM equity, Crash growth_down, VIX growth_up) are not a
            # single canonical class; mapped equity (its $-dominant parts) - stated
            st["asset_class"] = "equity"
        r["streams"][k] = st


def post_revert(r):
    x = copy.deepcopy(r); revert_loans(x); drop_zero(x); return x


def proposal(v, hold_gold=False):
    PR = {k: post_revert(r) for k, r in VAR_RAW[v].items()}
    mx = mixes(PR["base_0.30"])
    for r in PR.values():
        add_composites(r, mx)
    nav = totals(PR["base_0.30"])["liquid_usd"]
    deploy = nav - COMMIT_USD - FIX_USDC - FIX_ETH
    gold_usd = sum(mx["gold_silver"].values()) if hold_gold else 0.0
    core = [c for c in CORE if not (hold_gold and c == "gold_silver")]
    solve_names = core + list(ALPHA)
    book = build(PR["base_0.30"])
    fv = BookView("budgeted", [Position(n, 1.0, n) for n in solve_names], float(len(solve_names)))
    mB, *_ = prepare_moments(book, fv, loader, settings())
    names = mB.names
    S = mB.cov
    core_ix = [names.index(c) for c in core]
    mp, _ = stream_box_mapping(book.universe, core)
    Mx, _ = exposures_from_mapping(core, mp)
    q = quadrant_balance(S[np.ix_(core_ix, core_ix)], Mx, BOXES)
    b = {c: BUD["balanced_core"] * cb for c, cb in zip(core, q.budgets)}
    b.update(ALPHA)
    bud = np.array([b[n] for n in names]); bud = bud / bud.sum()
    w = risk_budget_weights(S, bud)
    usd = {n: float(w[i] * (deploy - gold_usd)) for i, n in enumerate(names)}
    if hold_gold:
        usd["gold_silver"] = gold_usd
    hl_btc = pos(PR["base_0.30"], "HL BTC trend long (notional)")["value_usd"]
    books = {}
    for k, r in PR.items():
        x = copy.deepcopy(r)
        x["positions"] = [p for p in x["positions"] if p["name"] in HL_NAMES or p.get("liquidity", "liquid") != "liquid"]
        cmix = norm(mx["composer_all"])
        for n, u in usd.items():
            parts = {c: u * f for c, f in cmix.items()} if n == "composer_all" else {n: u - (hl_btc if n == "BTC" else 0.0)}
            for sn, su in parts.items():   # Composer solved as ONE sleeve, held as its 4 symphonies (own box tags)
                x["positions"].append({"name": f"PROP {sn}", "value_usd": su, "stream": sn, "sleeve": "stocks",
                                       "liquidity": "liquid", "mark_basis": "market", "tags": ["proposed"], "investable": True})
        x["positions"].append({"name": "PROP reserve (BOXX, committed cash)", "value_usd": COMMIT_USD, "stream": "BOXX", "sleeve": "stocks",
                               "liquidity": "liquid", "mark_basis": "market", "tags": ["proposed", "reserve"], "investable": True})
        books[k] = x
    info = {"nav_usd": nav, "deployable_usd": deploy, "usd": usd, "budgets": dict(zip(names, bud.tolist())), "hold_gold": hold_gold,
            "core_quadrant_budgets": dict(zip(core, q.budgets.tolist())), "core_box_shares": dict(zip(BOXES, q.box_shares.tolist())),
            "gross_of_nav": (deploy + FIX_ETH) / nav}
    return PR, books, info


def pro_rata(PRr, target=0.15):
    """current mix, non-cash non-HL positions x L, funded from uncommitted cash (reserve and HL untouched)."""
    risky = [p["name"] for p in PRr["positions"] if p.get("liquidity", "liquid") == "liquid" and p["stream"] not in CASHLIKE
             and p["name"] not in HL_NAMES and p["value_usd"] > 0 and not p.get("investable") is False]
    cash_names = [n for n in CASH_FUND_ORDER if any(p["name"] == n for p in PRr["positions"])]
    cash_tot = sum(pos(PRr, n)["value_usd"] for n in cash_names)
    risky_tot = sum(pos(PRr, n)["value_usd"] for n in risky)
    L_max = 1.0 + (cash_tot - COMMIT_USD) / risky_tot

    def make(L):
        r = copy.deepcopy(PRr)
        need = (L - 1.0) * risky_tot
        for n in risky:
            pos(r, n)["value_usd"] *= L
        for n in cash_names:
            p = pos(r, n)
            t = min(need, max(p["value_usd"], 0.0)); p["value_usd"] -= t; need -= t
        assert need < 1e-6
        return r

    f = lambda L: score(make(L), "liquid")["portfolio"]["vol"] - target  # noqa: E731
    if f(L_max) < 0:
        L, binding = L_max, True
    else:
        L, binding = brentq(f, 1.0, L_max, xtol=1e-5), False
    return make, L, {"L": L, "L_max_cash": L_max, "cash_binding": binding, "risky_usd_before": risky_tot,
                     "uncommitted_cash_usd": cash_tot - COMMIT_USD, "deployed_usd": (L - 1) * risky_tot}


N2 = {}
BOOKS_BT = {}
rows_n2, rows_sleeve, rows_env = [], [], []
for v in ("D", "P"):
    PR, PROPB, info = proposal(v)
    make, Lpr, prinfo = pro_rata(PR["base_0.30"])
    variants = {"current as is": PR, "current, cash deployed pro rata": {k: make(Lpr) if k == "base_0.30" else None for k in PR},
                "UNLEVERED balanced proposal": PROPB}
    _, PROPG, infog = proposal(v, hold_gold=True)   # POST-HOC (labelled): physical + paper metals held, not sold
    variants["POST-HOC: proposal, metals held"] = PROPG
    # pro-rata book under each prior: same positions, prior streams from that prior's raw
    for k in PR:
        if k != "base_0.30":
            r = copy.deepcopy(variants["current, cash deployed pro rata"]["base_0.30"])
            r["streams"] = copy.deepcopy(PR[k]["streams"])
            variants["current, cash deployed pro rata"][k] = r
    out = {"proposal_solve": info, "proposal_metals_held_solve_POST_HOC": infog, "pro_rata": prinfo, "books": {}}
    for bk, rr in variants.items():
        sc = score(rr["base_0.30"], "liquid")
        mtr = liquid_metrics(sc)
        mtr["exp_return_prior_alpha_haircut"] = score(rr["alpha_haircut"], "liquid")["portfolio"]["exp_return"]
        mtr["exp_return_prior_base_0.30"] = mtr.pop("exp_return_prior")
        mtr["btc_cap_20pct_ok"] = mtr["btc_risk_share"] <= 0.20
        sl = sleeves_of(sc)
        mtr["composer_risk_share"] = sl.get("Composer (one sleeve)", {}).get("risk_share", 0.0)
        out["books"][bk] = {"metrics": mtr, "sleeves": list(sl.values()),
                            "streams": [{k2: s[k2] for k2 in ("stream", "usd", "dollar_share", "risk_share", "exp_return")} for s in sc["streams"]]}
        rows_n2.append({"variant": v, "book": bk, **{k2: v2 for k2, v2 in mtr.items()}})
        for s in sl.values():
            rows_sleeve.append({"variant": v, "book": bk, **s})
        rows_env.append({"variant": v, "book": bk, **{b: mtr[f"box_{b}"] for b in BOXES}, "unmapped": mtr["box_unmapped"],
                         "balance_score": mtr["balance_score"]})
        print("N2", v, bk, {a: round(b, 4) for a, b in mtr.items() if isinstance(b, float) and a in
                            ("nav_usd", "vol", "dr2", "neff_inv_hhi_prc", "btc_risk_share", "composer_risk_share", "balance_score",
                             "exp_return_prior_base_0.30", "exp_return_prior_alpha_haircut", "gross")})
        if v == "D":
            BOOKS_BT[bk] = sc
    N2[v] = out
M["N2"] = N2
M["post_hoc"].append({"item": "N2 'POST-HOC: proposal, metals held' added after seeing the predeclared solve put $0 in gold_silver",
                      "why": "the engine quadrant algebra covers inflation-up with TIP + DBC and gives gold a zero budget, which would mean "
                             "selling $170,650 of physical bullion (dealer spread, tax not modelled) against Casey's sheet goal "
                             "'Gold & Silver ... $600,000 GOAL'. Variant: metals held at today's $, everything else solved as declared."})
report.write_rows(pd.DataFrame(rows_n2), HERE / "n2_scorecards")
report.write_rows(pd.DataFrame(rows_sleeve), HERE / "n2_risk_vs_dollar_by_sleeve")
report.write_rows(pd.DataFrame(rows_env), HERE / "n2_environment_boxes")
trade = pd.DataFrame([{"stream": n, "target_usd": u} for n, u in N2["D"]["proposal_solve"]["usd"].items()])
report.write_rows(trade, HERE / "n2_proposal_targets_D")

# ------------------------------------------------------------------ N2 stress + constant-mix backtests (variant D)
PR_D, PROP_D, _ = proposal("D")
book_u = build(PROP_D["base_0.30"])
U = book_u.universe
CUR_STREAMS = ["SPY", "AVUV", "AVDV", "AVEM", "QUAL", "physical_metals", "PHYS", "PSLV", "GH", "TWST", "TEM", "LLY", "VIST",
               "JOINN", "BOT", "FTZFF", "SHAZ", "TSLA", "KMLM", "BTC", "composer_hg", "composer_kmlm", "composer_crash",
               "composer_vixhyg", "BOXX", "BIL"]
FACTORS = ["SPY", "TLT", "GLD", "DBC"]
NATURAL = {"AVUV": "IWM", "AVDV": "EFA", "AVEM": "VEIEX", "QUAL": "SPY", "PHYS": "GLD", "PSLV": "SLV"}
leaf_names = sorted(set(U.leaves(CUR_STREAMS + BUDGETED + ["IWM", "EFA", "VEIEX", "IEF", "GLD", "SLV", "TLT", "DBC"])[0]))
levels, _ = loader.stream_levels(U, leaf_names)
LR = aligned_returns(levels.loc[:"2026-09-30"], "D")
dtb3 = loader.fred("DTB3").values
LR = LR.loc[LR.index >= pd.Timestamp("2006-05-01")]
rf_d = tbill_period_returns(dtb3, LR.index)
first_real = {c: LR[c].first_valid_index() for c in LR.columns}
LB = LR.copy()
for c, px in NATURAL.items():
    m = LB[c].isna(); LB.loc[m, c] = LB.loc[m, px]
for c in ("BIL", "BOXX"):
    m = LB[c].isna()
    if c == "BOXX":
        mb = m & LB["BIL"].notna() & (LB.index >= first_real["BIL"]); LB.loc[mb, c] = LR.loc[mb, "BIL"]; m = LB[c].isna()
    LB.loc[m, c] = rf_d[m]
wk = (1 + LR).resample("W-FRI").prod(min_count=1) - 1
for c in LB.columns:
    if c in FACTORS or not LB[c].isna().any():
        continue
    dd_ = wk[[c] + FACTORS].dropna()
    bb = np.linalg.lstsq(dd_[FACTORS].to_numpy(), dd_[c].to_numpy(), rcond=None)[0]
    m = LB[c].isna(); LB.loc[m, c] = LB.loc[m, FACTORS].to_numpy() @ bb
assert not LB.isna().any().any()
ppyB = infer_periods_per_year(LB.index)


def stream_panel(leafR, streams):
    return pd.DataFrame({s: (leafR[s] if s in leafR.columns else U.series_returns(s, leafR, rf_d.reindex(leafR.index), ppyB)) for s in streams})


ALL = list(dict.fromkeys(CUR_STREAMS + BUDGETED + ["IEF"]))
PB = stream_panel(LB, ALL)
PA = stream_panel(LR, ALL).dropna(how="any")
PA = PA.loc[PA.index >= pd.Timestamp("2023-04-20")]
rfA = rf_d.reindex(PA.index)
ppyA = infer_periods_per_year(PA.index)


def wmap_from(sc):
    out = {}
    for s in sc["streams"]:
        if s["stream"] in PB.columns:
            out[s["stream"]] = out.get(s["stream"], 0.0) + s["dollar_share"]
    return out   # everything else (cash lines, HL USDC, ETH carry, st loans) = cash at rf


WM = {bk: wmap_from(sc) for bk, sc in BOOKS_BT.items()}
WM["SPY"] = {"SPY": 1.0}
WM["60/40 SPY/IEF"] = {"SPY": 0.6, "IEF": 0.4}


def const_alloc(wmap):
    def f(S, win):
        return np.array([wmap.get(c, 0.0) for c in win.columns])
    f.__name__ = "constant_mix_hindsight"
    return f


def bt(R, wmap, rf, ppy):
    cols = [c for c in R.columns if wmap.get(c, 0.0) != 0.0]
    cfg = BacktestConfig(allocator=const_alloc(wmap), window=2, min_periods=2, rebalance="M", cost_bps=5.0, financing_spread=0.0,
                         max_leverage=1.0 + 1e-9, periods_per_year=ppy)
    return run_backtest(R[cols], cfg, rf=rf)


BT = {"A": {bk: bt(PA, w_, rfA, ppyA) for bk, w_ in WM.items()}, "B": {bk: bt(PB, w_, rf_d, ppyB) for bk, w_ in WM.items()}}
btm = {}
for pnl, d in BT.items():
    t0 = max(b_.equity.index[0] for b_ in d.values())
    btm[pnl] = {}
    for bk, b_ in d.items():
        rr = b_.returns.loc[b_.returns.index > t0]
        btm[pnl][bk] = {**performance_metrics(rr, periods_per_year=b_.config["periods_per_year"], rf=rf_d.reindex(rr.index), base_value=1.0),
                        "start": str(t0.date())}
M["N2_backtest"] = {"basis": "CONSTANT MIX of today's weights (HINDSIGHT), monthly rebalance, 5bp, daily MTM, cash at DTB3. Panel A real data "
                              "(Composer = IN-SAMPLE backtests before live); panel B 2006-05.. backfilled with natural proxies then factor "
                              "replicas (full-sample betas: look-ahead). IN-SAMPLE, NOT a forecast.",
                    "weights": WM, "metrics": btm}
strows = []
for sk, (a, b, desc) in SCENARIOS.items():
    for bk, wmap in WM.items():
        rr = replay_scenario(PB, wmap, a, b, rebalance="none", rf_period=rf_d, label=f"{bk} {sk}")
        win = PB.loc[(PB.index > pd.Timestamp(a)) & (PB.index <= pd.Timestamp(b))]
        syn = 0.0
        for k, x in wmap.items():
            leaves = U.exposure(k).coefs if k in U.names else {k: 1.0}
            syn += abs(x) * sum(a_ for l_, a_ in leaves.items() if first_real.get(l_) is not None and first_real[l_] > win.index[0])
        strows.append({"scenario": sk, "window": f"{a}..{b}", "book": bk, "cum_return": rr["cum_return"], "max_drawdown": rr["max_drawdown"],
                       "max_dd_usd_on_nav": rr["max_drawdown"] * N2["D"]["proposal_solve"]["nav_usd"], "weight_on_proxy_or_replica": syn})
M["N2_stress"] = strows
ST = pd.DataFrame(strows)
report.write_rows(ST, HERE / "n2_stress")
print(ST.round(3).to_string())
for pnl in btm:
    for bk, x in btm[pnl].items():
        print("BT", pnl, bk, {k: round(x[k], 3) for k in ("cagr", "vol", "max_drawdown", "sharpe")})


# ------------------------------------------------------------------ charts
def save(fig, name):
    fig.tight_layout(); p = HERE / f"{name}.png"; fig.savefig(p, dpi=150, facecolor=SURF); plt.close(fig); return str(p)


def chart(png, csv, cap):
    CHARTS.append({"png": png, "rows_csv": csv, "caption": cap})


# N1: three panels (vol, cash-like share, BTC risk share), one axis each
df = pd.DataFrame(rows_n1)
df["label"] = df["variant"] + " | " + df["case"].str.replace("(loan outstanding)", "", regex=False).str.replace("(loan back in BOXX)", "", regex=False)
fig, axs = plt.subplots(1, 3, figsize=(13, 4.6), sharey=True)
y = np.arange(len(df))
cols = [SER[1] if v_ == "old book" else SER[0] if v_ == "D" else SER[2] for v_ in df.variant]
for ax, col, ttl in zip(axs, ("vol", "cash_like_share", "btc_risk_share"), ("Liquid vol", "Cash-like share of NAV", "BTC share of risk")):
    ax.barh(y, df[col] * 100, color=cols, height=0.62)
    for yi, x_ in zip(y, df[col]):
        ax.text(x_ * 100 + 0.6, yi, f"{x_:.1%}", va="center", fontsize=7, color=INK2)
    if col == "vol":
        ax.axvline(15, color=INK2, lw=0.8, ls="--"); ax.text(15.2, -0.6, "15% target", fontsize=7, color=INK2)
    report._style(ax, ttl, "%", "")
axs[0].set_yticks(y, df.label, fontsize=7.5); axs[0].invert_yaxis()
chart(save(fig, "n1_corrected_liquid"), str(HERE / "n1_corrected_liquid.csv"),
      "N1: corrected liquid book, variant D (Dominion out) and P (Plus One out), now / post-revert / net of commitments ($410.2k; sheet $435.2k), vs the old plug book")

# N2: dollars vs risk by sleeve, three books (variant D)
dfs = pd.DataFrame(rows_sleeve)
dfs = dfs[dfs.variant == "D"]
books = list(dict.fromkeys(dfs.book))
order = ["equity beta", "long Treasuries", "TIPS", "commodities", "gold & silver", "KMLM trend", "Composer (one sleeve)", "BTC",
         "single names", "HL ETH carry", "cash-like"]
fig, axs = plt.subplots(1, 4, figsize=(16, 4.6), sharey=True)
yy = np.arange(len(order))
for ax, bk, c in zip(axs, books, (SER[1], SER[3], SER[0], SER[2])):
    d = dfs[dfs.book == bk].set_index("sleeve").reindex(order).fillna(0.0)
    ax.barh(yy + 0.2, d.dollar_share * 100, 0.38, color=GRID, label="dollars")
    ax.barh(yy - 0.2, d.risk_share * 100, 0.38, color=c, label="risk")
    for yi, x_ in zip(yy, d.risk_share):
        if abs(x_) > 0.005:
            ax.text(x_ * 100 + 0.8, yi - 0.2, f"{x_:.0%}", va="center", fontsize=7, color=INK2)
    report._style(ax, bk, "% of NAV / % of risk", "")
    ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="lower right")
axs[0].set_yticks(yy, order, fontsize=8); axs[0].invert_yaxis()
chart(save(fig, "n2_risk_vs_dollar"), str(HERE / "n2_risk_vs_dollar_by_sleeve.csv"),
      "N2 (variant D): dollar share vs Euler risk share by sleeve - current, current with cash deployed pro rata, unlevered proposal (no margin)")

dfe = pd.DataFrame(rows_env); dfe = dfe[dfe.variant == "D"]
fig, ax = plt.subplots(figsize=(8.5, 4))
xb = np.arange(len(BOXES) + 1)
for i, (bk, c) in enumerate(zip(books, (SER[1], SER[3], SER[0], SER[2]))):
    r_ = dfe[dfe.book == bk].iloc[0]
    vals = [r_[b] * 100 for b in BOXES] + [r_["unmapped"] * 100]
    ax.bar(xb + (i - 1.5) * 0.2, vals, 0.18, color=c, label=f"{bk} (balance {r_['balance_score']:.2f})")
    for xi, v_ in zip(xb, vals):
        ax.text(xi + (i - 1.5) * 0.2, v_ + 0.8, f"{v_:.0f}", ha="center", fontsize=6, color=INK2)
ax.axhline(25, color=INK2, lw=0.8, ls="--")
ax.set_xticks(xb, ["growth up", "growth down", "inflation up", "inflation down", "unmapped"])
report._style(ax, "Share of risk by All Weather box (target 25%)", "", "% of risk")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2)
chart(save(fig, "n2_environment_boxes"), str(HERE / "n2_environment_boxes.csv"), "N2 (variant D): environment-box risk shares (engine canonical map; KMLM/cash unmapped)")

# backtests (panel B, log) + drawdowns
for pnl, ttl in (("B", "2006-05..2026-09, backfilled (IN-SAMPLE, hindsight weights)"), ("A", "2023-04..2026-09, real data, Composer IN-SAMPLE")):
    t0 = max(b_.equity.index[0] for b_ in BT[pnl].values())
    curves = {bk: BT[pnl][bk].equity.loc[t0:] for bk in ["UNLEVERED balanced proposal", "current as is", "current, cash deployed pro rata", "SPY", "60/40 SPY/IEF", "POST-HOC: proposal, metals held"]}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    rows = []
    for i, (bk, e) in enumerate(curves.items()):
        e = e / e.iloc[0]
        m_ = btm[pnl][bk]
        a1.plot(e.index, e.to_numpy(), color=SER[i], lw=2 if i == 0 else 1.4, label=f"{bk}  CAGR {m_['cagr']:.1%}, vol {m_['vol']:.1%}, maxDD {m_['max_drawdown']:.0%}")
        ddv = drawdown(e)
        a2.plot(ddv.index, ddv.to_numpy() * 100, color=SER[i], lw=1.2)
        rows += [{"date": dt.strftime("%Y-%m-%d"), "series": bk, "equity": x1, "drawdown": x2} for dt, x1, x2 in zip(e.index, e.to_numpy(), ddv.to_numpy())]
    a1.set_yscale("log")
    report._style(a1, f"Constant-mix backtest {pnl}: {ttl}", "", "growth of $1 (log)")
    report._style(a2, "", "", "drawdown %")
    a1.legend(frameon=False, fontsize=7, labelcolor=INK2)
    csv = report.write_rows(pd.DataFrame(rows), HERE / f"n2_backtest_{pnl}")["csv"]
    chart(save(fig, f"n2_backtest_{pnl}"), csv, f"N2 constant-mix backtest {pnl} ({ttl}); variant-D weights; equity (log) and drawdowns")

fig, ax = plt.subplots(figsize=(9, 4))
sc_list = list(SCENARIOS)
bks = ["UNLEVERED balanced proposal", "current as is", "current, cash deployed pro rata", "SPY", "60/40 SPY/IEF", "POST-HOC: proposal, metals held"]
xs = np.arange(len(sc_list))
for i, bk in enumerate(bks):
    vals = [100 * ST[(ST.scenario == s_) & (ST.book == bk)].max_drawdown.iloc[0] for s_ in sc_list]
    ax.bar(xs + (i - 2.5) * 0.14, vals, 0.13, color=SER[i], label=bk)
    for xi, v_ in zip(xs, vals):
        ax.text(xi + (i - 2.5) * 0.14, v_ - 2.2, f"{v_:.0f}", ha="center", fontsize=6, color=INK2)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(xs, ["2008 GFC", "2020 Covid", "2022 inflation"])
report._style(ax, "Stress replays, today's weights buy-and-hold: max drawdown", "", "%")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="lower left")
chart(save(fig, "n2_stress"), str(HERE / "n2_stress.csv"), "N2 stress replays (variant D weights): 2008 / 2020 / 2022 max drawdown; proxies/replicas where real data is missing (share in CSV)")

M["charts"] = CHARTS
report.write_json(M, HERE / "metrics_liquid.json")
print("done")
