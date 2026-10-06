"""No-leverage follow-up, repair item 2 (POST-HOC, counter-agent): EMBEDDED leverage inside 'no leverage' books.

Borrowing is zero in every N2/N3 book and gross <= 1 (ETFs counted at face). But Casey's Composer symphonies hold
daily-reset 3x ETFs (SPXL/TQQQ/SOXL/TECL/UPRO/LABU/TNA, TMF; UVXY 1.5x), sized per his own plan. This script adds a
LOOK-THROUGH NOTIONAL per book: an UPPER BOUND that counts every Composer dollar at 3x (the risk-on state), plus the
Composer sleeve's measured 3y beta and vol relative to SPY (how much equity it actually carried on average).
No number in N1-N4 changes. Reads metrics_liquid.json / metrics_postexit.json (run after liquid_n1_n2.py and
postexit_n3.py) and the cached spliced Composer series (no Composer API calls).

Run: cd holygrail-engine && HG_OFFLINE=1 python results/casey-2026-10/no-leverage/repair_lookthrough.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from holygrail import report  # noqa: E402

SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
ML = json.loads((HERE / "metrics_liquid.json").read_text())
MP = json.loads((HERE / "metrics_postexit.json").read_text())
CUR_DATA = HERE.parent / "current" / "data"
X3 = 3.0
WIN = ("2023-10-02", "2026-09-30")          # the N1/N2/N3 trailing-3y window
POLICY = {"hg": 0.29, "kmlm": 0.29, "crash": 0.27, "vixhyg": 0.15}
LIVE_START = {"hg": "2025-12-05", "kmlm": "2026-07-07", "crash": "2026-07-07", "vixhyg": "2026-07-22"}   # hg_common.py


def A(v, s, c):
    return {"value": float(v), "source": s, "confidence": c}


ASSUME = {
    "composer_max_multiple": A(X3, "symphony holdings (Composer book summary 2026-10-06): HG rotates 3x UPRO/TQQQ/SOXL/LABU/TNA; "
                                   "KMLM switcher risk-on 3x SPXL/TQQQ/SOXL/TECL; Crash sleeve holds TMF (3x); daily-reset 3x is the "
                                   "largest multiple held -> UPPER BOUND (the sleeve is never all 3x at once: PULS/BIL/IEF/SHY legs)", "high"),
    "other_positions_multiple": A(1.0, "ETFs, single names, BTC, private loans and venture at face; KMLM and DBC are fully "
                                       "collateralised futures funds (notional ~1x NAV) - NOTE only", "medium"),
    "hl_eth_carry": A(0.0, "UETH spot long + perp short is a delta-hedge; the perp short leg (~$30k) is reported as a separate "
                           "column, not added to the headline", "medium"),
}

# ---------------------------------------------------------------- Composer sleeve: measured exposure (IN-SAMPLE before live)
spy = pd.read_csv(ROOT / "data" / "cache" / "yahoo" / "SPY.csv", parse_dates=["date"]).set_index("date")["value"]
R = {"SPY": spy.pct_change()}
for s in POLICY:
    lv = pd.read_csv(CUR_DATA / f"composer_{s}_spliced.csv", parse_dates=["date"]).set_index("date")["value"]
    R[s] = lv.pct_change()
R = pd.DataFrame(R).loc[WIN[0]:WIN[1]].dropna()
cv = R.cov() * 252
meas = {}
for s in POLICY:
    meas[s] = {"beta_to_spy": cv.loc[s, "SPY"] / cv.loc["SPY", "SPY"], "vol": float(np.sqrt(cv.loc[s, s])),
               "vol_ratio_to_spy": float(np.sqrt(cv.loc[s, s] / cv.loc["SPY", "SPY"])),
               "share_of_window_in_sample": float((R.index < pd.Timestamp(LIVE_START[s])).mean())}
w = np.array([POLICY[s] for s in POLICY])
comp = R[list(POLICY)].to_numpy() @ w
meas["policy_mix_29_29_27_15"] = {"beta_to_spy": float(np.cov(comp, R["SPY"])[0, 1] / R["SPY"].var()),
                                  "vol": float(comp.std(ddof=1) * np.sqrt(252)),
                                  "vol_ratio_to_spy": float(comp.std(ddof=1) / R["SPY"].std(ddof=1))}
print("Composer measured", {k: {a: round(b, 2) for a, b in v.items()} for k, v in meas.items()})

# ---------------------------------------------------------------- books
rows = []
for v in ("D", "P"):
    for bk, b in ML["N2"][v]["books"].items():
        m = b["metrics"]
        sl = {x["sleeve"]: x for x in b["sleeves"]}
        nav = m["nav_usd"]
        c_usd = sl.get("Composer (one sleeve)", {}).get("usd", 0.0)
        eth = sl.get("HL ETH carry", {}).get("usd", 0.0)
        rows.append({"section": f"N2 liquid, variant {v}", "book": bk, "nav_usd": nav, "borrowing_usd": 0.0,
                     "gross_at_face": m["gross"], "composer_usd": c_usd, "composer_share": c_usd / nav,
                     "lookthrough_upper_3x": m["gross"] + (X3 - 1.0) * c_usd / nav,
                     "eth_perp_short_leg_share": eth / nav})
nav3 = MP["nav_usd"]
for cand, wts in MP["weights"].items():
    if not isinstance(wts, dict):
        continue
    cs = sum(x for s, x in wts.items() if s.startswith("c_"))
    gross = sum(wts.values()) - wts.get("BOXX", 0.0)
    rows.append({"section": "N3 $18M post-exit", "book": cand, "nav_usd": nav3, "borrowing_usd": 0.0, "gross_at_face": gross,
                 "composer_usd": cs * nav3, "composer_share": cs, "lookthrough_upper_3x": gross + (X3 - 1.0) * cs,
                 "eth_perp_short_leg_share": 0.0})
df = pd.DataFrame(rows)
print(df[["section", "book", "gross_at_face", "composer_usd", "composer_share", "lookthrough_upper_3x"]].round(3).to_string())
report.write_rows(df, HERE / "lookthrough_notional")

# ---------------------------------------------------------------- chart: gross at face vs look-through upper bound (one axis)
keep = df[(df.section != "N2 liquid, variant P")].reset_index(drop=True)
keep["label"] = np.where(keep.section.str.startswith("N3"), "N3 | " + keep.book, "N2 (D) | " + keep.book)
fig, ax = plt.subplots(figsize=(10, 5.2))
yy = np.arange(len(keep))
ax.barh(yy + 0.2, keep.gross_at_face, 0.38, color=GRID, label="gross at face (what 'no leverage' measured)")
ax.barh(yy - 0.2, keep.lookthrough_upper_3x, 0.38, color=SER[1], label="look-through upper bound (Composer at 3x)")
for yi, a_, b_ in zip(yy, keep.gross_at_face, keep.lookthrough_upper_3x):
    ax.text(a_ + 0.01, yi + 0.2, f"{a_:.2f}x", va="center", fontsize=7, color=INK2)
    ax.text(b_ + 0.01, yi - 0.2, f"{b_:.2f}x", va="center", fontsize=7, color=INK2)
ax.axvline(1.0, color=INK2, lw=0.9, ls="--"); ax.text(1.005, -0.62, "1.0x", fontsize=7, color=INK2)
ax.set_yticks(yy, keep.label, fontsize=8); ax.invert_yaxis()
ax.set_xlim(0, max(keep.lookthrough_upper_3x) * 1.12)
report._style(ax, "Borrowing is zero everywhere; Composer's 3x ETFs are not", "notional / NAV", "")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="upper right")
fig.tight_layout(); png = HERE / "lookthrough_notional.png"; fig.savefig(png, dpi=150, facecolor=SURF); plt.close(fig)

out = {"item": "repair 2 (POST-HOC, counter-agent): embedded leverage under 'no leverage'",
       "rule_scope": "Casey's 'no leverage' rule as applied here = no borrowing / margin and no levered balanced funds (ALLW/UPAR/RSSB). "
                     "It does NOT remove the daily-reset 3x ETFs inside Casey's own Composer strategy, which every book keeps "
                     "(sized per his plan: N2 risk budget 16%; N3 $4.32M = 24%).",
       "assumptions": ASSUME, "composer_measured_3y": meas,
       "composer_measured_basis": f"daily, {WIN[0]}..{WIN[1]}, spliced series: IN-SAMPLE backtest before each live start "
                                  f"({LIVE_START}), live after",
       "rows": rows, "numbers_changed_in_N1_N4": "none",
       "chart": {"png": str(png), "rows_csv": str(HERE / "lookthrough_notional.csv"),
                 "caption": "Gross at face vs look-through notional upper bound (every Composer dollar at 3x), N2 variant D and N3"}}
report.write_json(out, HERE / "metrics_repair.json")
print("done")
