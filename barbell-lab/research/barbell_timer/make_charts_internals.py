#!/usr/bin/env python3
"""A17 internals chart: drawdown profiles of rules 9/10 vs B&H GDE and
relmom_cash, plus the one-month-lag stress panel (the Oct-2008 question).

Palette: same validated trio as fig7 (dataviz validator ALL CHECKS PASS on
#2a78d6/#008300/#4a3aa7 for this surface; tritan 7.6 in the 6-8 band is
covered by secondary encoding — filled area vs solid vs dashed marks, plus
direct labels). Color follows the ENTITY repo-wide: B&H GDE keeps sleeve
blue, relmom_cash keeps violet; the two A17 rules are separated by SMALL
MULTIPLES (identity from the panel title) sharing green — facet, don't cycle.
The lag panel reuses the same entity colors (same entities, lagged
execution, labeled as such).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
C_GDE, C_RULE, C_RELMOM, C_SHADE = "#2a78d6", "#008300", "#4a3aa7", "#b9b8b3"

j = json.load(open(os.path.join(HERE, "rules_internals_results.json")))
panel = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]
FULL0, FULL1 = pd.Period("1977-02", "M"), pd.Period("2026-07", "M")


def ser(d):
    s = pd.Series(d, dtype=float)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.sort_index().loc[FULL0:FULL1]


def dd(r):
    eq = (1 + r).cumprod()
    out = eq / eq.cummax() - 1
    out.index = out.index.to_timestamp(how="end")
    return out * 100


bh_gde = dd(ser({k: v["gde_synth"] for k, v in panel.items()}))
relmom = dd(ser(j["monthly_returns"]["relmom_cash"]))
r9 = dd(ser(j["monthly_returns"]["rule9_internals_exit"]))
r10 = dd(ser(j["monthly_returns"]["rule10_relmom_gated"]))
states = {k: pd.Series(v) for k, v in j["states"].items()}

OOS0 = pd.Period("1990-02", "M")


def dd_oos(d):
    s = pd.Series(d, dtype=float)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return dd(s.sort_index().loc[OOS0:FULL1])


lag_relmom = dd_oos(j["monthly_returns_lagged"]["relmom_cash"])
lag_r10 = dd_oos(j["monthly_returns_lagged"]["rule10_relmom_gated"])

fig = plt.figure(figsize=(12.5, 9.4), facecolor=SURF)
gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0], hspace=0.34,
                      wspace=0.10, top=0.845, bottom=0.075, left=0.06,
                      right=0.985)
ax9 = fig.add_subplot(gs[0, 0])
ax10 = fig.add_subplot(gs[0, 1], sharey=ax9)
axL = fig.add_subplot(gs[1, :])

for ax, r, name, key in ((ax9, r9, "Rule 9 — internals exit "
                          "(GDE default; ANY of s15-s18 adverse → cash)", "rule9"),
                         (ax10, r10, "Rule 10 — relmom_cash gated by internals",
                          "rule10")):
    ax.set_facecolor(SURF)
    st = states[key]
    held = pd.PeriodIndex(st.index, freq="M") + 1
    for p, s in zip(held, st.values):
        if s == "boxx" and FULL0 <= p <= FULL1:
            ax.axvspan(p.to_timestamp(how="start"), p.to_timestamp(how="end"),
                       color=C_SHADE, alpha=0.35, lw=0)
    ax.fill_between(bh_gde.index, bh_gde.values, 0, color=C_GDE, alpha=0.15, lw=0)
    ax.plot(bh_gde.index, bh_gde.values, color=C_GDE, lw=1.2, alpha=0.8)
    ax.plot(relmom.index, relmom.values, color=C_RELMOM, lw=1.6, ls=(0, (4, 2)))
    ax.plot(r.index, r.values, color=C_RULE, lw=2.0)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(pd.Timestamp("1990-02-01"), color=INK2, lw=0.8, ls=":")
    ax.set_title(name, fontsize=10, color=INK, loc="left", pad=4)
    nm = {"rule9": "rule9_internals_exit", "rule10": "rule10_relmom_gated"}[key]
    s_ = j["stats"][nm]["oos"]
    ax.text(0.985, 0.06, f"OOS maxDD {s_['MaxDD_m']*100:.0f}%  "
            f"CAGR {s_['CAGR']*100:.1f}%  ulcer {s_['Ulcer']:.1f}",
            transform=ax.transAxes, ha="right", fontsize=8.5, color=INK2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.grid(axis="y", color=INK2, alpha=0.15, lw=0.6)
ax9.set_ylim(-70, 4)
ax9.set_ylabel("drawdown (%, month-end)", fontsize=9, color=INK2)
ax9.annotate("in cash 77% of OOS months —\nthe ANY-of-4 union over-fires;\n"
             "CAGR 3.8% vs bills 2.7%",
             xy=(pd.Timestamp("2004-06-30"), -6), fontsize=8, color=INK,
             xytext=(pd.Timestamp("1984-01-31"), -46),
             arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax10.annotate("gated OUT of GDE through most\nof the 2001-11 gold bull:\n"
              "1.9%/yr in the decade GDE won",
              xy=(pd.Timestamp("2006-06-30"), -8), fontsize=8, color=INK,
              xytext=(pd.Timestamp("1987-01-31"), -50),
              arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))

# ---- lag panel ----
axL.set_facecolor(SURF)
axL.plot(lag_relmom.index, lag_relmom.values, color=C_RELMOM, lw=1.6,
         ls=(0, (4, 2)))
axL.plot(lag_r10.index, lag_r10.values, color=C_RULE, lw=2.0)
axL.axhline(0, color=INK2, lw=0.8)
axL.set_title("One-month-LAG stress (decision t earns t+2), OOS — does the "
              "internals gate fix the Oct-2008 lag kill?",
              fontsize=10, color=INK, loc="left", pad=4)
axL.annotate("lagged relmom_cash holds GDE through Oct-08 (-31.6%):\n"
             "maxDD -49.3%, Calmar 0.26 < null 0.28 (the Phase-4 kill)",
             xy=(pd.Timestamp("2008-11-30"), -46), fontsize=8.5, color=INK,
             xytext=(pd.Timestamp("1992-06-30"), -40),
             arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
axL.annotate("lagged rule 10 is in cash for Oct-08 (internals adverse\n"
             "from Aug-08): maxDD -18.2%, Calmar 0.39 — gate FIXES the lag\n"
             "fragility, but on-time it costs -7.7pp/yr CAGR vs relmom_cash",
             xy=(pd.Timestamp("2009-01-31"), -17), fontsize=8.5, color=INK,
             xytext=(pd.Timestamp("2012-06-30"), -38),
             arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
axL.set_ylim(-55, 3)
axL.set_ylabel("drawdown (%, lagged exec.)", fontsize=9, color=INK2)
for sp in ("top", "right"):
    axL.spines[sp].set_visible(False)
for sp in ("left", "bottom"):
    axL.spines[sp].set_color(INK2)
axL.tick_params(colors=INK2, labelsize=8.5)
axL.grid(axis="y", color=INK2, alpha=0.15, lw=0.6)

handles = [
    plt.matplotlib.patches.Patch(facecolor=C_GDE, alpha=0.25, edgecolor=C_GDE,
                                 label="B&H GDE-synth (drawdown)"),
    plt.Line2D([], [], color=C_RULE, lw=2, label="A17 rule (per panel)"),
    plt.Line2D([], [], color=C_RELMOM, lw=1.6, ls=(0, (4, 2)),
               label="relmom_cash (standing candidate)"),
    plt.matplotlib.patches.Patch(facecolor=C_SHADE, alpha=0.35,
                                 label="months in cash"),
    plt.Line2D([], [], color=INK2, lw=0.8, ls=":", label="OOS start 1990-02"),
]
fig.legend(handles=handles, loc="upper left", ncol=5, fontsize=8.5,
           frameon=False, bbox_to_anchor=(0.05, 0.905), columnspacing=1.2,
           handlelength=1.6)
fig.text(0.06, 0.965, "AMENDMENT A17 — cross-equity internals as GDE timing: "
         "drawdown profiles + lag stress, 1977-02 → 2026-07",
         fontsize=12.5, color=INK, weight="bold")
fig.text(0.06, 0.935, "Walk-forward, net of 5bp/switch. GDE-synth is a model "
         "(±1%/yr carry band pre-2007); month-end curves are intramonth-blind "
         "(~4pp deeper daily). Gray bands = rule in cash.",
         fontsize=9, color=INK2)
out = os.path.join(FIGS, "fig9_internals_drawdowns.png")
fig.savefig(out, dpi=160, facecolor=SURF)
print("wrote", out)
