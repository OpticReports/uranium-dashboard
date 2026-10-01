#!/usr/bin/env python3
"""fig_severity_history.png from results.json (studies/severity-history.md)."""
import datetime as dt
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, CRIT, AMB, REC = "#2a78d6", "#e34948", "#eb6834", "#e9e8e4"
R = json.load(open(os.path.join(HERE, "results.json")))


def t(m):
    y, mo = map(int, m.split("-"))
    return dt.date(y, mo, 15)


fig, ax = plt.subplots(figsize=(12, 5.1))
fig.patch.set_facecolor(SURF)
ax.set_facecolor(SURF)
ax.grid(color=GRID, lw=0.8, axis="y")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for r in R["recessions"]:
    ax.axvspan(t(r["start"]), t(r["end"]), color=REC, lw=0, zorder=0)
xs = [t(r["month"]) for r in R["series"]]
ys = [r["score"] if r["drawn"] else float("nan") for r in R["series"]]
ax.plot(xs, ys, color=S1, lw=1.8)
ax.axhline(60, color=CRIT, lw=1, ls="--")
ax.axhline(35, color=AMB, lw=1, ls="--")
ax.text(dt.date(2026, 12, 1), 61.5, "SEVERE above 60", color=CRIT, fontsize=8, ha="right")
ax.text(dt.date(2026, 12, 1), 36.5, "MILD below 35", color=AMB, fontsize=8, ha="right")
for s in R["analogs"]["recession_starts"]:
    y, m = map(int, s["peak"].split("-"))
    d = dt.date(y - (m == 1), (m - 2) % 12 + 1, 15)
    ax.plot([d], [s["reading"]], "o", color=CRIT, ms=7, mec=SURF, mew=1.5, zorder=4)
    lab = (f"{s['peak'][:4]} (pandemic,\noutside index): {s['reading']:.0f}" if s.get("exogenous")
           else f"{s['peak'][:4]}: {s['reading']:.0f}\nU +{s['unemployment_rise_pp']}pp")
    ax.annotate(lab,
                xy=(d, s["reading"]), xytext=(-40 if s["peak"] < "1995" else 0, 20 if s["peak"] < "1995" else 12),
                textcoords="offset points", ha="center", fontsize=8, color=INK)
ax.plot([xs[-1]], [R["today"]["score"]], "o", color=S1, ms=8, mec=SURF, mew=1.5, zorder=5)
ax.annotate(f"today {R['today']['score']:.0f}", xy=(xs[-1], R["today"]["score"]),
            xytext=(-10, 12), textcoords="offset points", ha="right", fontsize=9,
            color=S1, weight="bold")
ax.set_ylim(20, 100)
ax.set_xlim(dt.date(1985, 6, 1), dt.date(2027, 3, 1))
ax.set_ylabel("severity (0-100)", color=INK2)
ax.set_title(f"Severity index replayed since 1986: up from ~50 in Dec-2023 to {R['today']['score']:.0f} now, at or above "
             f"{R['pctile_all_inputs']}% of months since all inputs exist ({R['all_inputs_from'][:4]}).\n"
             "Before 2007 it read 73 (deep recession), before 2001 67 and 1990 66 (mild); 2012-15 averaged "
             "67 with no recession.\nHousehold debt (Z.1) and debt service (archived 1980+) extended back; "
             "a few inputs start 1996-2000. Grey = NBER recessions.",
             loc="left", fontsize=10.5, color=INK)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig_severity_history.png"), dpi=160, facecolor=SURF)
print("ok")
