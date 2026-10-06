"""The book Casey controls: whole book minus Organics Ocean (sale-pending), with the verified BOXX-loan correction
(variant D, reading (a): Dominion outstanding $200k; repaid capital assumed inside the sheet's Cash/Stables line) and a
sensitivity on the one soft input that dominates it, the venture-basket volatility.

Run: cd holygrail-engine && HG_OFFLINE=1 python results/casey-2026-10/controllable/ex_oo_view.py
Basis: the current-book helpers and estimation settings (daily, trailing 3y to 2026-09-30, lw_cc); risk shares are Euler
contributions and do not depend on any expected-return input.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "current"))

import pandas as pd  # noqa: E402

from hg_common import OUT as CUR_OUT, base_raw, pos, score, set_prior, sleeve_table, summary_row  # noqa: E402

VOLS = json.load(open(CUR_OUT / "data" / "prior_vols.json"))
RF = json.load(open(CUR_OUT / "data" / "rf.json"))["rf"]
PLUG = "Short-term 16% loans (out of BOXX)"
DOMINION = "Film Dominion bridge (returned 2026-09-25)"
VENTURE_VOLS = [0.30, 0.45, 0.60, 0.80]   # declared before running; 0.60 is the book's own assumption (low confidence)

SLEEVE_NAMES = {"venture_basket": "Other venture (13 names)", "private_credit": "Private credit (film, Gary, Spirit)",
                "real_estate": "Real estate", "em_special_sits": "Venezuela bond + Argentina warrants",
                "crypto_btc": "BTC", "composer_equity_momentum": "Composer HG symphony + KMLM switcher",
                "equity_beta": "Equity ETFs (SPY, B.5 factor funds)", "single_names": "Single stocks",
                "gold_silver": "Gold and silver", "cash_like": "Cash, BOXX, T-bills, 16% loan",
                "composer_vix_harvester": "Composer VIX Harvester", "eth_carry": "ETH carry", "trend": "KMLM trend",
                "composer_crash_convexity": "Composer Crash Convexity"}


def corrected_raw():
    r = base_raw(spliced=True)
    set_prior(r, VOLS, RF, 0.30, None)
    pos(r, PLUG)["value_usd"] = 200_000.0          # variant D: Dominion outstanding
    r["positions"] = [q for q in r["positions"] if q["name"] != DOMINION]
    return r


rows, sens = [], []
for v in VENTURE_VOLS:
    r = copy.deepcopy(corrected_raw())
    r["streams"]["venture_basket"]["vol"]["value"] = v
    sc = score(r, "investable", exclude=["Organics Ocean"])
    s = summary_row(f"ex_oo_venture_vol_{v}", sc)
    sl = sleeve_table(sc)
    vb = next(d for d in sl if d["sleeve"] == "venture_basket")
    sens.append({"venture_vol": v, "nav_usd": s["nav_usd"], "vol": s["vol"], "dr2": s["dr2"],
                 "venture_dollar_share": vb["dollar_share"], "venture_risk_share": vb["risk_share"],
                 "balance_score": s["balance_score"], "box_growth_up": s["box_growth_up"],
                 "box_growth_down": s["box_growth_down"], "box_inflation_up": s["box_inflation_up"],
                 "box_inflation_down": s["box_inflation_down"]})
    if abs(v - 0.60) < 1e-9:
        for d in sl:
            rows.append({"sleeve": SLEEVE_NAMES.get(d["sleeve"], d["sleeve"]), "usd": d["usd"],
                         "dollar_share": d["dollar_share"], "risk_share": d["risk_share"]})
        base_summary = s

pd.DataFrame(rows).to_csv(HERE / "ex_oo_risk_vs_dollar.csv", index=False)
pd.DataFrame(sens).to_csv(HERE / "ex_oo_venture_vol_sensitivity.csv", index=False)
json.dump({"basis": __doc__, "venture_vols_declared": VENTURE_VOLS, "base_summary_venture_vol_0.60": base_summary,
           "sleeves_base": rows, "sensitivity": sens}, open(HERE / "metrics.json", "w"), indent=1, default=float)
print(pd.DataFrame(rows).round(4).to_string()); print(pd.DataFrame(sens).round(4).to_string())
