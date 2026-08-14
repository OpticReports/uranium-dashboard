#!/usr/bin/env python3
"""A12 exit-engine chart: drawdown profiles vs B&H GDE and vs relmom_cash.

Palette: dataviz validator ALL CHECKS PASS on #2a78d6/#008300/#4a3aa7
(tritan 7.6 in the 6-8 floor band -> secondary encoding satisfied: the three
entities differ by mark TYPE — filled area / solid line / dashed line — and
every series is direct-labeled). Color follows the ENTITY, repo-wide:
B&H GDE keeps sleeve blue (figs 1-5), relmom_cash keeps violet (figs 4-6);
the four A12 exit rules are separated by SMALL MULTIPLES (one panel each,
identity from the panel title), sharing green — the one fresh slot — rather
than minting four new hues (9th-series rule: facet, don't cycle).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
C_GDE, C_RULE, C_RELMOM, C_SHADE = "#2a78d6", "#008300", "#4a3aa7", "#b9b8b3"
PRETTY = {"vol_exit": "Rule 6 — vol-exit (63d vol > exp. 85th pct)",
          "vol_exit_spy": "Rule 6b — vol-exit, to SPY if SPY trend up",
          "corr_exit": "Rule 7 — corr-spike exit (corr > 90th & 3m ret < 0)",
          "dual_exit": "Rule 8 — dual trigger (6 OR 7)"}

ex = json.load(open(os.path.join(HERE, "rules_exit_results.json")))
r3 = json.load(open(os.path.join(HERE, "rules_results.json")))
panel = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]

FULL0, FULL1 = pd.Period("1978-05", "M"), pd.Period("2026-07", "M")


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
relmom = dd(ser(r3["monthly_returns"]["relmom_cash"]))
rules = {k: dd(ser(v)) for k, v in ex["monthly_returns"].items()}
states = {k: pd.Series(v) for k, v in ex["states"].items()}

fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.6), sharex=True, sharey=True,
                         facecolor=SURF)
fig.subplots_adjust(hspace=0.30, wspace=0.10, top=0.845, bottom=0.08,
                    left=0.06, right=0.985)

for ax, name in zip(axes.flat, ["vol_exit", "vol_exit_spy",
                                "corr_exit", "dual_exit"]):
    ax.set_facecolor(SURF)
    # exit-state shading (held months = decision month + 1)
    st = states[name]
    held = pd.PeriodIndex(st.index, freq="M") + 1
    out_mask = (st != "gde").values
    for p, is_out in zip(held, out_mask):
        if is_out:
            t0 = p.to_timestamp(how="start")
            t1 = p.to_timestamp(how="end")
            ax.axvspan(t0, t1, color=C_SHADE, alpha=0.35, lw=0)
    ax.fill_between(bh_gde.index, bh_gde.values, 0, color=C_GDE, alpha=0.15,
                    lw=0)
    ax.plot(bh_gde.index, bh_gde.values, color=C_GDE, lw=1.2, alpha=0.8)
    ax.plot(relmom.index, relmom.values, color=C_RELMOM, lw=1.6, ls=(0, (4, 2)))
    r = rules[name]
    ax.plot(r.index, r.values, color=C_RULE, lw=2.0)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(pd.Timestamp("1990-02-01"), color=INK2, lw=0.8, ls=":")
    ax.set_title(PRETTY[name], fontsize=10.5, color=INK, loc="left", pad=4)
    st_oos = ex["rules"][name]["oos"]
    ax.text(0.985, 0.06,
            f"OOS maxDD {st_oos['MaxDD_m']*100:.0f}%  CAGR {st_oos['CAGR']*100:.1f}%"
            f"  in GDE {ex['rules'][name]['time_in_gde']['oos']*100:.0f}%",
            transform=ax.transAxes, ha="right", fontsize=8.5, color=INK2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.grid(axis="y", color=INK2, alpha=0.15, lw=0.6)

axes[0, 0].set_ylim(-70, 4)
axes[0, 0].set_ylabel("drawdown (%, month-end curve)", fontsize=9, color=INK2)
axes[1, 0].set_ylabel("drawdown (%, month-end curve)", fontsize=9, color=INK2)

# annotations of the two decisive episodes
a = axes[0, 0]
a.annotate("exited Oct-79: missed +83%\nblow-off, re-entered mid-bust",
           xy=(pd.Timestamp("1980-01-31"), -4), fontsize=8, color=INK,
           xytext=(pd.Timestamp("1983-06-30"), -58),
           arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a.annotate("dodged Oct-08, then missed\n2009-10 recovery (cash to May-10)",
           xy=(pd.Timestamp("2008-10-31"), -15), fontsize=8, color=INK,
           xytext=(pd.Timestamp("1994-06-30"), -46),
           arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a7 = axes[1, 0]
a7.annotate("never fired for Oct-08: 63d corr\nstill negative at Sep-08 month-end",
            xy=(pd.Timestamp("2008-10-31"), -44), fontsize=8, color=INK,
            xytext=(pd.Timestamp("1993-06-30"), -58),
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a7.annotate("whipsawed 5x in 1980-82 bust:\nmaxDD -62%, DEEPER than B&H GDE",
            xy=(pd.Timestamp("1982-06-30"), -62), fontsize=8, color=INK,
            xytext=(pd.Timestamp("1985-09-30"), -44),
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))

handles = [
    plt.matplotlib.patches.Patch(facecolor=C_GDE, alpha=0.25, edgecolor=C_GDE,
                                 label="B&H GDE-synth (drawdown)"),
    plt.Line2D([], [], color=C_RULE, lw=2, label="A12 exit rule (per panel)"),
    plt.Line2D([], [], color=C_RELMOM, lw=1.6, ls=(0, (4, 2)),
               label="relmom_cash (Phase-3 champion)"),
    plt.matplotlib.patches.Patch(facecolor=C_SHADE, alpha=0.35,
                                 label="months OUT of GDE"),
    plt.Line2D([], [], color=INK2, lw=0.8, ls=":", label="OOS start 1990-02"),
]
fig.legend(handles=handles, loc="upper left", ncol=5, fontsize=8.5,
           frameon=False, bbox_to_anchor=(0.05, 0.905), columnspacing=1.2,
           handlelength=1.6)
fig.text(0.06, 0.965, "AMENDMENT A12 — GDE-anchored exit engines: drawdown "
         "profiles vs B&H GDE and relmom_cash, 1978-05 → 2026-07",
         fontsize=12.5, color=INK, weight="bold")
fig.text(0.06, 0.935, "Walk-forward, net of 5bp/switch. GDE-synth is a model "
         "(±1%/yr carry band pre-2007); month-end curves are intramonth-blind "
         "(~4pp deeper daily). Gray bands = rule out of GDE.",
         fontsize=9, color=INK2)
out = os.path.join(FIGS, "fig7_exit_rules_drawdowns.png")
fig.savefig(out, dpi=160, facecolor=SURF)
print("wrote", out)
