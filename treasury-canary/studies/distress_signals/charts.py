#!/usr/bin/env python3
"""Figures for studies/distress-signals.md (reads results.json + data/).

    python3 charts.py [outdir]
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402
import load as D  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figs")
os.makedirs(OUT, exist_ok=True)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, S2, S3, BASE, CRIT = "#2a78d6", "#eb6834", "#1baf7a", "#8a8985", "#e34948"
REC, MASK = "#e9e8e4", "#f3efe6"
CLS = {"LEAD": S3, "COINCIDENT": S2, "LATE": CRIT, "FALSE": INK2, "PENDING": BASE,
       "NEUTRAL": BASE}
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})
RES = json.load(open(os.path.join(HERE, "results.json")))
TITLES = {
    "national": "National bankruptcy filings did not lead: no +10% onset came in the 18 months before the 1990 or "
                "2001 recessions.\n"
                "Business filings' onsets came just after both ended (1992-01, 2002-01), consumer filings' after 2001 "
                "(2002-01); the 1986 and 1996 onsets were years early",
    "liabilities": "Liabilities of failing firms, 1967-83 out of sample: the +25% alert fired after the 1969 and 1973 "
                   "recessions began\n(as it did at 8 of 10 peaks in 1896-1938); its only early signal (1980-11) came "
                   "from one giant failure month and is discounted",
    "states": "A state's filing growth predicted its own job losses in 1981-2000, mostly from the 1980s; since 2002 only\n"
              "business filings -> job losses (p 0.047). The pre-registered test needs both eras plus out-of-sample: "
              "no state alert",
    "bank": "Bank loan stress: no series warned before every recession; all-loan charge-offs confirm "
            "(2 months before 1990, at the 2001 start, 1 month before 2007)",
}


def fmt_p(p: float) -> str:
    """p as printed in distress-signals.md: 3 decimals rounded half-up, p<0.001 below that."""
    if p < 0.001:
        return "p<0.001"
    return "p=" + str(Decimal(str(p)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def style(ax):
    ax.set_facecolor(SURF)
    ax.grid(color=GRID, lw=0.8, axis="y")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def d_of(m: int) -> dt.date:
    return dt.date(m // 12, m % 12 + 1, 15)


def d_str(s: str) -> dt.date:
    return dt.date(int(s[:4]), int(s[5:7]), 15)


def shade(ax, lo=1955):
    for p, tau in E.PEAKS:
        if p // 12 >= lo:
            ax.axvspan(d_of(p), d_of(tau), color=REC, lw=0, zorder=0)


def qdate(qs: str) -> dt.date:
    y, q = int(qs[:4]), int(qs[5])
    return dt.date(y, 3 * q, 15)


def mark_onsets(ax, onsets, yfun, size=46):
    for o in onsets:
        c = CLS.get(o["class"], BASE)
        d = d_str(o["release"])
        ax.scatter([d], [yfun(d)], s=size, color=c, edgecolor=SURF, lw=1.2, zorder=5)


# ------------------------------------------------------------------ national
def fig_national():
    qn = RES["Q_N"]
    us_pop = D.us_pop()
    ann = D.nonbusiness_annual_50dc()          # 50 states + DC, the study's one per-capita basis
    fig, axes = plt.subplots(3, 1, figsize=(12, 9.6), sharex=True,
                             gridspec_kw={"height_ratios": [1.15, 1, 1]})
    fig.patch.set_facecolor(SURF)
    for ax in axes:
        style(ax)
        shade(ax, 1979)
    ax = axes[0]
    ys = sorted(y for y in ann if y in us_pop)
    nb = [ann[y] / us_pop[y] for y in ys]                          # per 1,000 (pop in thousands)
    ax.plot([dt.date(y, 7, 1) for y in ys], nb, color=S1, lw=2, marker="o", ms=3)
    s12 = D.f2_state("12month", "nb_all")
    nb12 = sum(s12[s][D.qi(2026, 2)] for s in D.STATES) / D.pop_at(us_pop, 2026.0)
    ax.plot([dt.date(2026, 6, 30)], [nb12], "o", color=CRIT, ms=7, mec=SURF, mew=1.5)
    ax.annotate(f"{nb12:.2f} per 1,000\n(12 months to Jun-2026)", (dt.date(2026, 6, 30), nb12),
                xytext=(-120, 38), textcoords="offset points", fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    for when, lab in ((dt.date(2005, 10, 17), "BAPCPA\n(Oct-2005)"), (dt.date(2020, 3, 27), "pandemic\nsupport")):
        ax.axvline(when, color=INK2, lw=0.8, ls=":")
        ax.text(when, ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] else 6, lab, fontsize=7.5, color=INK2, ha="left")
    ax.set_ylabel("consumer filings\nper 1,000 residents")
    ax.set_title("Consumer (non-business) bankruptcy filings per 1,000 residents (50 states + DC), 1980-2026",
                 loc="left", fontsize=10, color=INK)
    # N1 and N2 growth with onsets
    for ax, key, title in ((axes[1], "N1", "Business filings: growth of the 4-quarter sum vs a year earlier"),
                           (axes[2], "N2", "Consumer filings: annual growth")):
        if key == "N1":
            g = {qdate(k): v for k, v in qn["_series"]["N1_g"].items()}
            ons = qn["N1_combos"]["N1|1995Q4"]["primary"]["onsets"]
        else:
            g = {dt.date(int(k), 7, 1): v for k, v in qn["N2_annual_g"].items()}
            ons = qn["N2_annual"]["primary"]["onsets"]
        xs = sorted(g)
        masked = [x for x in xs if (dt.date(2005, 4, 1) <= x <= dt.date(2010, 9, 30)
                                    or dt.date(2020, 4, 1) <= x <= dt.date(2023, 9, 30))]
        ax.plot(xs, [100 * g[x] for x in xs], color=S1 if key == "N2" else S2, lw=1.5)
        for a, b in ((dt.date(2005, 4, 1), dt.date(2010, 9, 30)), (dt.date(2020, 4, 1), dt.date(2023, 9, 30))):
            ax.axvspan(a, b, color=MASK, lw=0, zorder=0, hatch="///", edgecolor=GRID)
        ax.axhline(10, color=CRIT, lw=1, ls="--")
        ax.text(dt.date(1981, 1, 1), 12, "rule: on above +10%", fontsize=7.5, color=CRIT)
        lim = 60
        ax.set_ylim(-lim, lim)
        mark_onsets(ax, ons, lambda d: 10)
        ax.set_ylabel("% vs a year earlier")
        ax.set_title(title, loc="left", fontsize=10, color=INK)
    for c, lab in ((S3, "warning before a recession (LEAD)"), (S2, "at the start (COINCIDENT)"),
                   (CRIT, "inside the recession (LATE)"), (INK2, "no recession followed (FALSE)"),
                   (BASE, "too recent to judge (PENDING)")):
        axes[2].scatter([], [], color=c, s=40, label=lab)
    axes[2].legend(loc="lower left", fontsize=7.5, frameon=False, ncol=3)
    axes[2].set_xlim(dt.date(1979, 6, 1), dt.date(2027, 3, 1))
    fig.suptitle(TITLES["national"],
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "Grey bands = NBER recessions; hatched = masked (2005 law change, 2020-21 support, and the "
             "quarters whose growth still compares against them). Dots sit on the +10% line at the date each "
             "warning would have been published.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(os.path.join(OUT, "fig_national_filings.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ Q-H
def fig_liabilities():
    qh = RES["Q_H"]
    g = {d_str(k): v for k, v in qh["_series"]["real_12m_g"].items()}
    fig, ax = plt.subplots(figsize=(12, 4.6))
    fig.patch.set_facecolor(SURF)
    style(ax)
    ax.axvspan(dt.date(1967, 1, 1), dt.date(1983, 12, 31), color="#eef4fb", lw=0, zorder=0)
    for p, tau in [(E.M(1957, 8), E.M(1958, 4)), (E.M(1960, 4), E.M(1961, 2))] + list(E.PEAKS):
        if 1955 <= p // 12 <= 1986:
            ax.axvspan(d_of(p), d_of(tau), color=REC, lw=0, zorder=1, alpha=0.9)
    xs = sorted(g)
    ax.plot(xs, [100 * g[x] for x in xs], color=S1, lw=1.4)
    ax.axhline(25, color=CRIT, lw=1, ls="--")
    ax.text(dt.date(1955, 6, 1), 30, "rule: on above +25%", fontsize=7.5, color=CRIT)
    ons = [o for o in qh["primary_real_cpi"]["primary"]["onsets"]]
    notes = {"LATE": "fired {r}:\nrecession had begun {p}", "LEAD": "{r}: one giant month\n(Sep-1980), discounted"}
    for o in ons:
        c = BASE if o.get("discounted") else CLS.get(o["class"], BASE)
        d = d_str(o["release"])
        ax.scatter([d], [25], s=52, color=c, edgecolor=SURF, lw=1.2, zorder=5)
        txt = notes.get(o["class"], "").format(r=o["release"], p=o.get("peak"))
        if txt:
            ax.annotate(txt, (d, 25), xytext=(6, -38), textcoords="offset points", fontsize=7.5, color=INK2)
    ax.text(dt.date(1967, 3, 1), ax.get_ylim()[1] * 0.9, "out-of-sample test window 1967-1983",
            fontsize=8, color=S1)
    ax.set_ylabel("real liabilities, 12-month sum, % vs a year earlier")
    ax.set_xlim(dt.date(1955, 1, 1), dt.date(1987, 1, 1))
    ax.set_title(TITLES["liabilities"], loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_failure_liabilities.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ Q-R
def fig_states():
    qr = RES["Q_R"]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), gridspec_kw={"width_ratios": [1.1, 1]})
    fig.patch.set_facecolor(SURF)
    ax = axes[0]
    style(ax)
    rows = []
    for pan, plab in (("panel_A", "1981-2000"), ("panel_B", "2002-2025")):
        for sig, slab in (("S1", "consumer"), ("S2", "business")):
            for tgt, tlab in (("a", "unemployment"), ("b", "job losses")):
                r = qr[pan][f"{sig}/{tgt}"]
                rows.append((f"{plab}: {slab} filings -> {tlab}", r["wcb_division"]["t"], r["wcb_division"]["p"]))
    for i, (lab, t, p) in enumerate(rows[::-1]):
        c = S3 if p <= 0.05 else (S2 if p <= 0.10 else BASE)
        ax.barh([i], [t], color=c, height=0.6)
        ax.text(max(t, 0) + 0.15, i, fmt_p(p), va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows[::-1]], fontsize=7.5)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.axvline(1.645, color=CRIT, lw=0.8, ls="--")
    ax.set_xlabel("t-statistic (division-clustered); bootstrap p shown")
    ax.set_title("Does a state's filing growth predict its own deterioration next year?", loc="left",
                 fontsize=10, color=INK)
    ax = axes[1]
    style(ax)
    for sig, col in (("S1", S1), ("S2", S2)):
        es = qr["panel_B"][f"{sig}/a"]["event_study"]
        reg = es.get("regional")
        if not reg:
            continue
        ks = sorted(int(k) for k in reg["path_filings"])
        ax.plot(ks, [reg["path_filings"][str(k)] for k in ks], color=col, lw=2,
                label=f"{'consumer' if sig == 'S1' else 'business'} filings")
        if sig == "S1":
            ax.plot(ks, [reg["path_claims"][str(k)] for k in ks], color=INK2, lw=1.5, ls="--",
                    label="jobless claims")
    ax.axvline(0, color=CRIT, lw=1)
    ax.axhline(0, color=INK2, lw=0.6)
    ax.set_xlabel("quarters relative to a state's unemployment upturn")
    ax.set_ylabel("growth vs other states (state SDs)")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    n = qr["panel_B"]["S1/a"]["event_study"]["n_regional"]
    ax.set_title(f"Around {n} state-only unemployment upturns (2014-19)", loc="left", fontsize=10, color=INK)
    fig.suptitle(TITLES["states"], x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, "fig_state_panels.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ Q-C
NAMES = {"DRALACBS": "All loans, delinquency", "DRBLACBS": "Business (C&I), delinquency",
         "DRCLACBS": "Consumer, delinquency", "DRCCLACBS": "Credit card, delinquency",
         "DRSFRMACBS": "Home mortgage, delinquency", "DRCRELEXFACBS": "Commercial real estate, delinquency",
         "CORALACBS": "All loans, charge-offs", "CORBLACBS": "Business (C&I), charge-offs",
         "CORCCACBS": "Credit card, charge-offs"}


def fig_bank():
    qc = RES["Q_C"]
    fig, axes = plt.subplots(3, 3, figsize=(12.5, 8.4), sharex=True)
    fig.patch.set_facecolor(SURF)
    for ax, (sid, v) in zip(axes.ravel(), qc["series"].items()):
        style(ax)
        shade(ax, 1984)
        r = D.fred_quarterly(sid)
        xs = sorted(r)
        ax.plot([dt.date(i // 4, 3 * (i % 4) + 2, 15) for i in xs], [r[i] for i in xs], color=S1, lw=1.3)
        ons = v["grade"]["primary"]["onsets"]
        for o in ons:
            d = d_str(o["release"])
            ax.axvline(d, color=CLS.get(o["class"], BASE), lw=1.2, alpha=0.9)
        g = v["grade"]
        tag = "ALERT" if v["ALERT"] else ("confirms" if v["PANEL"] else "")
        ax.set_title(f"{NAMES[sid]} {('- ' + tag) if tag else ''}", loc="left", fontsize=8.5, color=INK)
    fig.suptitle(TITLES["bank"],
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "Vertical lines = rule onsets at their publication date: green before a recession, "
             "orange at its start, red inside it, dark grey no recession followed, light grey too recent or neutral "
             "(at the exogenous 2020 recession).",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    fig.savefig(os.path.join(OUT, "fig_bank_rates.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ map
GRIDPOS = {  # tile-grid cartogram (row, col)
    "AK": (0, 0), "ME": (0, 10), "VT": (1, 9), "NH": (1, 10), "WA": (2, 1), "ID": (2, 2), "MT": (2, 3),
    "ND": (2, 4), "MN": (2, 5), "IL": (2, 6), "WI": (2, 7), "MI": (2, 8), "NY": (2, 9), "MA": (2, 10),
    "OR": (3, 1), "NV": (3, 2), "WY": (3, 3), "SD": (3, 4), "IA": (3, 5), "IN": (3, 6), "OH": (3, 7),
    "PA": (3, 8), "NJ": (3, 9), "CT": (3, 10), "RI": (3, 11), "CA": (4, 1), "UT": (4, 2), "CO": (4, 3),
    "NE": (4, 4), "MO": (4, 5), "KY": (4, 6), "WV": (4, 7), "VA": (4, 8), "MD": (4, 9), "DE": (4, 10),
    "AZ": (5, 2), "NM": (5, 3), "KS": (5, 4), "AR": (5, 5), "TN": (5, 6), "NC": (5, 7), "SC": (5, 8),
    "DC": (5, 9), "OK": (6, 4), "LA": (6, 5), "MS": (6, 6), "AL": (6, 7), "GA": (6, 8), "HI": (7, 0),
    "TX": (7, 4), "FL": (7, 9)}


def fig_map():
    # per 1,000 on the one basis (population at the window's midpoint); results.json's
    # descriptive `current` block divides by the 2025 population instead
    pop = D.state_pop()
    rows = {r["state"]: dict(r, nonbusiness_per_1000=r["nonbusiness_12m"] / D.pop_at(pop[r["state"]], 2026.0))
            for r in RES["current"]["state_12m_to_2026Q2"]}
    vals = [rows[s]["nonbusiness_per_1000"] for s in rows]
    lo, hi = min(vals), max(vals)
    cmap = plt.get_cmap("Oranges")
    fig, ax = plt.subplots(figsize=(11, 6.4))
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s, (r, c) in GRIDPOS.items():
        v = rows[s]["nonbusiness_per_1000"]
        yoy = rows[s]["nonbusiness_yoy"]
        col = cmap(0.15 + 0.8 * (v - lo) / (hi - lo))
        ax.add_patch(plt.Rectangle((c, -r), 0.94, 0.94, color=col))
        dark = (v - lo) / (hi - lo) > 0.55
        ax.text(c + 0.47, -r + 0.62, s, ha="center", va="center", fontsize=9, weight="bold",
                color=SURF if dark else INK)
        ax.text(c + 0.47, -r + 0.36, f"{v:.1f}", ha="center", va="center", fontsize=7.5,
                color=SURF if dark else INK)
        ax.text(c + 0.47, -r + 0.14, f"{100 * yoy:+.0f}%", ha="center", va="center", fontsize=7,
                color=SURF if dark else INK2)
    ax.set_xlim(-0.2, 12.2)
    ax.set_ylim(-7.2, 1.1)
    ax.axis("off")
    nat = RES["current"]["national_nonbusiness_12m_yoy_2026Q2"]
    ax.set_title(f"Consumer filings per 1,000 residents, 12 months to Jun-2026 (number), and change vs a year "
                 f"earlier (%). Nation {100 * nat:+.1f}%", loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_state_map_2026Q2.png"), dpi=150, facecolor=SURF)


if __name__ == "__main__":
    fig_national()
    fig_liabilities()
    fig_states()
    fig_bank()
    fig_map()
    print("written to", OUT)
