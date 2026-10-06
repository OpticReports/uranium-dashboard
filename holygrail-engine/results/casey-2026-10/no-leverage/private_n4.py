"""No-leverage follow-up, N4: private credit and venture as Dalio return streams (measured where data exists).

Run: cd holygrail-engine && HG_OFFLINE=1 python results/casey-2026-10/no-leverage/private_n4.py
Parameters: predeclared_params.json (N4). Moments via current/hg_common.score() (daily, trailing 3y, lw_cc); parametric
streams carry the book's own sourced assumptions, so every correlation/Sharpe for them is ASSUMPTION-driven.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "current"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from hg_common import OUT as CUR_OUT, base_raw, pos, score, set_prior  # noqa: E402
from holygrail import report  # noqa: E402

PP = json.loads((HERE / "predeclared_params.json").read_text())["N4"]
VOLS = json.load(open(CUR_OUT / "data" / "prior_vols.json"))
RF = json.load(open(CUR_OUT / "data" / "rf.json"))["rf"]
SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
M: dict = {"params_file": "predeclared_params.json (N4)", "post_hoc": []}
CHARTS: list = []
PLUG, DOMINION = "Short-term 16% loans (out of BOXX)", "Film Dominion bridge (returned 2026-09-25)"

# ---------------------------------------------------------------- film book concentration (sheet 'Movies')
BASE_LOANS = {"PING gap": 50_000, "Father of Us bridge (past due)": 100_000, "12 Dates of Christmas gap": 550_000,
              "Prank Call gap": 250_000, "Kate Might Die gap": 132_000, "MiniWar gap": 200_000}
LOANS = {"D": {**BASE_LOANS, "Dominion bridge (outstanding)": 200_000},
         "P": {**BASE_LOANS, "Plus One bridge (outstanding)": 129_166}}
RHO_D = 0.30


def conc(d, rho):
    v = np.array(list(d.values()), float); w = v / v.sum(); hhi = float((w ** 2).sum())
    return {"total_usd": float(v.sum()), "n_loans": len(v), "largest": max(d, key=d.get), "largest_share": float(w.max()), "hhi": hhi,
            "n_eff_by_usd": 1 / hhi, "n_eff_at_rho": 1 / (rho + (1 - rho) * hhi)}


film = {v: {**conc(d, RHO_D), "rho_D": RHO_D, "n_eff_grid": {str(r): 1 / (r + (1 - r) * conc(d, r)["hhi"]) for r in (0.0, 0.1, 0.3, 0.5, 1.0)}}
        for v, d in LOANS.items()}
M["film_concentration"] = film

# ---------------------------------------------------------------- income (sheet 'T12 2026')
INC = {"Real Estate": (30_000, 22_500), "Stable Yield": (4_000, 2_500), "Gary Loan": (40_000, 29_997), "Spirit Fund": (31_000, 21_000),
       "Keeta": (200_000, 197_152), "Film Loans": (318_400, 60_820), "River": (75_000, 75_000)}
tot_p, tot_a = sum(p for p, _ in INC.values()), sum(a for _, a in INC.values())
ex = {k: v for k, v in INC.items() if k not in ("Keeta", "River")}
M["income_t12"] = {"rows": {k: {"planned": p, "actual": a, "ratio": a / p} for k, (p, a) in INC.items()},
                   "total": {"planned": tot_p, "actual": tot_a, "ratio": tot_a / tot_p},
                   "total_ex_keeta_river": {"planned": sum(p for p, _ in ex.values()), "actual": sum(a for _, a in ex.values()),
                                            "ratio": sum(a for _, a in ex.values()) / sum(p for p, _ in ex.values())},
                   "film_booked_profits": {"MARX": 3_000, "Kate Might Die bridge": 18_445, "Dustlands": 10_000, "Plus One": 19_375,
                                           "Father of Us (partial, past due)": 10_000},
                   "note": "sheet total $408,969.30 (rows sum to $408,969); film $60,820.30 = the five booked profits; Father of Us "
                           "$10,000 collected of $50,000 expected; Dominion's $32,000 not booked"}

# ---------------------------------------------------------------- venture paper gain (sheet 'Venture')
VEN = {"Organics Ocean": (100_000, 12_000_000), "Persona": (275_000, 625_000), "Google X Fund": (400_000, 400_000),
       "Copper Royalty": (100_000, 270_000), "Argentine GDP Warrants": (200_000, 230_000), "Venezuelan Bond": (100_000, 180_000),
       "Uranium Digital": (50_000, 150_000), "Slip": (50_000, 50_000), "BNB Dat": (75_000, 28_000), "Vernius": (25_000, 25_000),
       "RoboStrategy": (8_000, 24_000), "BITS": (50_000, 0), "Define Fit": (125_000, 0), "OpenAi": (25_000, 0), "Schools PR": (150_000, 0)}
cost, paper = sum(c for c, _ in VEN.values()), sum(p for _, p in VEN.values())
assert cost == 1_733_000 and paper == 13_982_000
gain = paper - cost
M["venture_gain"] = {"cost": cost, "paper": paper, "gain": gain, "oo_gain": 11_900_000, "oo_share_of_gain": 11_900_000 / gain,
                     "oo_share_of_paper": 12_000_000 / paper, "rest_gain": gain - 11_900_000,
                     "realized_total": 307_900, "realized_oo": 254_900, "oo_share_of_realized": 254_900 / 307_900,
                     "rows": {k: {"cost": c, "paper": p, "gain": p - c} for k, (c, p) in VEN.items()}}


# ---------------------------------------------------------------- sleeve DR^2, correlation, risk (engine, assumption-driven)
def variant_raw(v):
    r = base_raw(spliced=True)
    set_prior(r, VOLS, RF)
    pos(r, PLUG)["value_usd"] = 200_000.0 if v == "D" else 129_166.0
    r["positions"] = [q for q in r["positions"] if q["name"] != DOMINION]
    return r


VENT_STREAMS = {"organics_ocean", "venture_basket", "em_special_sits"}
PC_STREAMS = {"film_gap_loans", "film_father_of_us", "gary_loan", "spirit_fund"}


def sleeve_stats(raw, streams, drop_oo=False):
    names_in = [p["name"] for p in raw["positions"] if p["stream"] in streams and not (drop_oo and p["name"] == "Organics Ocean")]
    excl = [p["name"] for p in raw["positions"] if p["name"] not in names_in]
    sc = score(raw, "investable", exclude=excl)
    nr = {r["label"][:3]: r["value"] for r in sc["effective_bets"]["rows"]}
    return {"nav_usd": sc["nav_usd"], "vol": sc["portfolio"]["vol"], "dr2": sc["effective_bets"]["dr2"], "neff_inv_hhi_prc": nr.get("(b)"),
            "exp_return_prior": sc["portfolio"]["exp_return"], "sharpe_prior": (sc["portfolio"]["exp_return"] - RF) / sc["portfolio"]["vol"],
            "streams": [{k: s[k] for k in ("stream", "usd", "dollar_share", "risk_share", "exp_return", "vol")} for s in sc["streams"]],
            "largest_position_share": max(p["value_usd"] for p in raw["positions"] if p["name"] in names_in) /
                                      sum(p["value_usd"] for p in raw["positions"] if p["name"] in names_in)}


def corr_to_rest(raw, streams):
    sc, m, rets, book, v = score(raw, "investable", return_moments=True)
    names = m.names
    sv = v.stream_values()
    w = np.array([sv[n] / v.total_usd for n in names])
    ins = np.array([n in streams for n in names])
    ws, wr = w * ins, w * ~ins
    S = m.cov
    c = float(ws @ S @ wr / np.sqrt((ws @ S @ ws) * (wr @ S @ wr)))
    rs = float(sum(s["risk_share"] for s in sc["streams"] if s["stream"] in streams))
    ds = float(sum(s["dollar_share"] for s in sc["streams"] if s["stream"] in streams))
    return {"corr_to_rest_of_investable": c, "risk_share_of_investable": rs, "dollar_share_of_investable": ds}


SLV = {}
for v in ("D", "P"):
    r = variant_raw(v)
    SLV[v] = {"venture_with_oo": {**sleeve_stats(r, VENT_STREAMS), **corr_to_rest(r, VENT_STREAMS)},
              "venture_without_oo": sleeve_stats(r, VENT_STREAMS, drop_oo=True),
              "private_credit": {**sleeve_stats(r, PC_STREAMS), **corr_to_rest(r, PC_STREAMS)}}
    ro = copy.deepcopy(r); ro["positions"] = [q for q in ro["positions"] if q["name"] != "Organics Ocean"]
    SLV[v]["venture_without_oo"].update(corr_to_rest(ro, VENT_STREAMS))
M["sleeves"] = SLV
for v in SLV:
    for k, d in SLV[v].items():
        print(v, k, {a: round(b, 4) for a, b in d.items() if isinstance(b, float)})

# ---------------------------------------------------------------- Dalio tests (predeclared thresholds)
D = SLV["D"]
pc, vw, vx = D["private_credit"], D["venture_with_oo"], D["venture_without_oo"]
inc = M["income_t12"]["rows"]
pc_inc_ratio = (inc["Film Loans"]["actual"] + inc["Gary Loan"]["actual"] + inc["Spirit Fund"]["actual"]) / \
               (inc["Film Loans"]["planned"] + inc["Gary Loan"]["planned"] + inc["Spirit Fund"]["planned"])
tests = {
    "private_credit": {
        "GOOD": {"prior_sharpe": pc["sharpe_prior"], "realised_income_vs_plan": pc_inc_ratio,
                 "pass": bool(pc["sharpe_prior"] >= 0.2 and pc_inc_ratio >= 0.5)},
        "UNCORRELATED": {"corr_to_rest": pc["corr_to_rest_of_investable"], "n_eff_film_rho0.3": film["D"]["n_eff_at_rho"],
                         "pass": bool(pc["corr_to_rest_of_investable"] <= 0.30 and film["D"]["n_eff_at_rho"] >= 5)},
        "RISK_BALANCED": {"largest_loan_share_of_film": film["D"]["largest_share"], "largest_position_share_of_sleeve": pc["largest_position_share"],
                          "risk_vs_dollar": pc["risk_share_of_investable"] / pc["dollar_share_of_investable"],
                          "pass": bool(pc["largest_position_share"] <= 0.20 and pc["risk_share_of_investable"] <= 2 * pc["dollar_share_of_investable"])}},
    "venture_with_oo": {
        "GOOD": {"prior_sharpe": vw["sharpe_prior"], "realised": "no measured return series; realised $307,900 on $1.733M cost (82.8% from OO)",
                 "pass": False, "why": "no realised-return evidence; marks are a banker indication (OO) and round/cost marks"},
        "UNCORRELATED": {"corr_to_rest": vw["corr_to_rest_of_investable"], "dr2": vw["dr2"],
                         "pass": bool(vw["corr_to_rest_of_investable"] <= 0.30 and vw["dr2"] >= 5)},
        "RISK_BALANCED": {"largest_position_share": vw["largest_position_share"], "risk_vs_dollar": vw["risk_share_of_investable"] / vw["dollar_share_of_investable"],
                          "pass": bool(vw["largest_position_share"] <= 0.20 and vw["risk_share_of_investable"] <= 2 * vw["dollar_share_of_investable"])}},
    "venture_without_oo": {
        "UNCORRELATED": {"corr_to_rest": vx["corr_to_rest_of_investable"], "dr2": vx["dr2"],
                         "pass": bool(vx["corr_to_rest_of_investable"] <= 0.30 and vx["dr2"] >= 5)},
        "RISK_BALANCED": {"largest_position_share": vx["largest_position_share"],
                          "pass": bool(vx["largest_position_share"] <= 0.20)}}}
M["dalio_tests_variant_D"] = tests
print(json.dumps(tests, indent=1, default=str))


# ---------------------------------------------------------------- charts
def save(fig, name):
    fig.tight_layout(); p = HERE / f"{name}.png"; fig.savefig(p, dpi=150, facecolor=SURF); plt.close(fig); return str(p)


rows = [{"variant": v, "loan": k, "usd": x, "share": x / sum(LOANS[v].values())} for v in LOANS for k, x in LOANS[v].items()]
rows += [{"variant": v, "loan": f"n_eff at rho_D={r}", "usd": None, "share": film[v]["n_eff_grid"][r]} for v in LOANS for r in film[v]["n_eff_grid"]]
csv = report.write_rows(pd.DataFrame(rows), HERE / "n4_film_concentration")["csv"]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4), gridspec_kw={"width_ratios": [3, 2]})
d = sorted(LOANS["D"].items(), key=lambda kv: kv[1])
yy = np.arange(len(d))
a1.barh(yy, [x / 1e3 for _, x in d], color=SER[0], height=0.6)
for yi, (_, x) in zip(yy, d):
    a1.text(x / 1e3 + 8, yi, f"${x / 1e3:.0f}k  {x / sum(LOANS['D'].values()):.0%}", va="center", fontsize=7, color=INK2)
a1.set_yticks(yy, [k for k, _ in d], fontsize=8)
report._style(a1, f"Film book, variant D: ${sum(LOANS['D'].values()) / 1e6:.2f}M in {len(d)} loans", "$k outstanding", "")
rr = [0.0, 0.1, 0.3, 0.5, 1.0]
for v, c in (("D", SER[0]), ("P", SER[2])):
    a2.plot(rr, [film[v]["n_eff_grid"][str(r)] for r in rr], color=c, lw=2, marker="o", ms=5, label=f"variant {v}")
a2.axvline(RHO_D, color=INK2, lw=0.8, ls="--"); a2.text(RHO_D + 0.02, 4.6, "book rho_D 0.3", fontsize=7, color=INK2)
report._style(a2, "Effective number of loans", "default correlation rho_D", "n_eff")
a2.legend(frameon=False, fontsize=8, labelcolor=INK2)
CHARTS.append({"png": save(fig, "n4_film_concentration"), "rows_csv": csv,
               "caption": "N4 film book: loan $ shares (variant D) and n_eff = 1/(rho + (1-rho) HHI) across default correlations"})

rows = [{"line": k, "planned": p, "actual": a, "actual_over_plan": a / p} for k, (p, a) in INC.items()]
csv = report.write_rows(pd.DataFrame(rows), HERE / "n4_income_plan_vs_actual")["csv"]
fig, ax = plt.subplots(figsize=(8.5, 3.8))
ks = list(INC)
x = np.arange(len(ks))
ax.bar(x - 0.2, [INC[k][0] / 1e3 for k in ks], 0.38, color=GRID, label="planned (T12)")
ax.bar(x + 0.2, [INC[k][1] / 1e3 for k in ks], 0.38, color=SER[0], label="actual (T12)")
for xi, k in zip(x, ks):
    ax.text(xi + 0.2, INC[k][1] / 1e3 + 4, f"{INC[k][1] / INC[k][0]:.0%}", ha="center", fontsize=7, color=INK2)
ax.set_xticks(x, ks, fontsize=8)
report._style(ax, f"T12 income: ${tot_a / 1e3:.0f}k actual vs ${tot_p / 1e3:.0f}k planned ({tot_a / tot_p:.0%}); film {60_820 / 318_400:.0%}", "", "$k")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
CHARTS.append({"png": save(fig, "n4_income_plan_vs_actual"), "rows_csv": csv, "caption": "N4: sheet 'T12 2026' planned vs actual income by line (measured)"})

rows = sorted([{"position": k, "cost": c, "paper": p, "gain": p - c} for k, (c, p) in VEN.items()], key=lambda r: -r["gain"])
csv = report.write_rows(pd.DataFrame(rows), HERE / "n4_venture_gain")["csv"]
fig, ax = plt.subplots(figsize=(8.5, 3.6))
segs = [("Organics Ocean", 11_900_000, SER[1]), ("all other positions (net)", gain - 11_900_000, SER[0])]
left = 0
for lab_, val_, c in segs:
    ax.barh([0], [val_ / 1e6], left=left / 1e6, color=c, height=0.5, edgecolor=SURF, linewidth=2)
    if val_ / gain > 0.2:
        ax.text((left + val_ / 2) / 1e6, 0, f"{lab_}\n${val_ / 1e6:.2f}M ({val_ / gain:.0%})", ha="center", va="center", fontsize=8, color="white")
    else:
        ax.text((left + val_) / 1e6, 0.33, f"{lab_}: ${val_ / 1e6:.2f}M ({val_ / gain:.0%})", ha="right", va="bottom", fontsize=8, color=INK2)
    left += val_
ax.set_yticks([])
ax.set_xlim(0, gain / 1e6 * 1.02)
report._style(ax, f"Venture paper gain ${gain / 1e6:.2f}M (paper ${paper / 1e6:.2f}M on cost ${cost / 1e6:.2f}M): one position is {11.9e6 / gain:.0%}", "$M", "")
CHARTS.append({"png": save(fig, "n4_venture_gain"), "rows_csv": csv, "caption": "N4: venture paper gain by position (sheet 'Venture'); OO marked at a banker/broker indication"})

M["charts"] = CHARTS
report.write_json(M, HERE / "metrics_private.json")
print("done")
