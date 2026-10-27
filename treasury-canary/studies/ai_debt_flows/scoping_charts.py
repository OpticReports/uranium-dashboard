#!/usr/bin/env python3
"""Charts for studies/ai-debt-flows.md (scoping pass, rev 1). Reads only the
verified data files in data/ and the memo's corrected tally tables.

    python3 scoping_charts.py [outdir]     # -> figs/fig_aidebt_*.png
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figs")
os.makedirs(OUT, exist_ok=True)
SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8985", "#e6e5e1"
BLUE, ORANGE, GREEN, CRIT, PURPLE = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#8b5cf6"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})


def _style(ax, y0=True):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if y0:
        ax.axhline(0, color=INK2, lw=0.8)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _ym(s):  # "2026-07" / "202607" -> fractional year for plotting
    s = s.replace("-", "")
    return int(s[:4]) + (int(s[4:6]) - 0.5) / 12


def _roll12(vals):
    out = [np.nan] * len(vals)
    for i in range(11, len(vals)):
        w = vals[i - 11:i + 1]
        out[i] = sum(w) if not any(np.isnan(w)) else np.nan
    return out


# --------------------------------------------------------------- 1. the tally
# The memo's corrected tables (verifier C re-included Amazon C$14.0bn and
# CoreWeave $2.0bn; totals per distress... ai-debt-flows.md s.3a/3b), $bn.
BUCKETS = [("Hyperscaler bonds (Meta, Alphabet, Amazon, Oracle)", [16.8, 108.4, 217.5]),
           ("Off-balance-sheet SPV / project debt", [0, 74.7, 40.9]),
           ("Neocloud / miner (CoreWeave, Nebius, IREN...)", [8.0, 21.5, 49.5]),
           ("Chips / memory (Nvidia, Broadcom, AMD, Intel, Micron)", [13.6, 18.2, 40.8]),
           ("AI lab (SpaceX)", [0, 5.0, 25.0]),
           ("Power", [0, 5.6, 17.1]),
           ("Data-center ABS / landlord", [1.4, 9.3, 9.3])]
RATINGS = [("AA", [10.5, 82.7, 217.5]), ("A", [2.5, 33.8, 30.1]), ("BBB", [17.9, 43.3, 70.6]),
           ("BB", [0, 5.9, 26.3]), ("Unrated / private", [8.0, 62.4, 26.7]),
           ("ABS tranched", [0.8, 4.2, 2.7]), ("Rating not captured", [0, 10.5, 26.0])]
# (2025 "not captured" = memo 8.5 + the re-included CoreWeave $2.0bn the verifier left unbucketed)
YEARS = ["2024", "2025", "2026 YTD\n(to 15 Oct)"]
SEQ_B = ["#1b4f9c", "#2a78d6", "#5e9be3", "#8fbbec", "#b9d4f3", "#d6e5f8", "#e9f1fb"]
SEQ_O = ["#9c3a14", "#eb6834", "#f08a5f", "#f5ab8a", "#f9c9b3", "#fbdfd1", "#fdefe8"]


def fig_tally():
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), facecolor=SURF)
    for ax, rows, pal, title in ((axes[0], BUCKETS, SEQ_B, "by bucket"),
                                 (axes[1], RATINGS, SEQ_O, "by rating at issue (S&P letter at pricing)")):
        ax.set_facecolor(SURF)
        bottom = np.zeros(3)
        for (lab, v), c in zip(rows, pal):
            v = np.array(v, float)
            ax.bar(range(3), v, bottom=bottom, color=c, width=0.62, label=lab, edgecolor=SURF, linewidth=1.5)
            for i in range(3):
                if v[i] >= 24:
                    ax.text(i, bottom[i] + v[i] / 2, f"{v[i]:.0f}", ha="center", va="center", fontsize=7.5,
                            color=SURF if c in pal[:3] else INK)
            bottom += v
        for i, t in enumerate(bottom):
            ax.text(i, t + 6, f"\\${t:.0f}bn", ha="center", fontsize=9, color=INK, fontweight="bold")
        ax.set_xticks(range(3))
        ax.set_xticklabels(YEARS)
        ax.set_ylim(0, 455)
        _style(ax, y0=False)
        ax.set_title(f"AI-trade debt raised, {title}", loc="left", fontsize=10, color=INK)
        ax.legend(fontsize=7, frameon=False, loc="upper left")
    axes[0].set_ylabel("\\$bn (non-USD legs at the trade-date FX rate)", color=INK2)
    fig.suptitle("The AI trade has raised \\$682bn of debt since 2024 — \\$400bn of it this year; 54% rated AA, none AAA",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, "Rev 1 tally from SEC filings: 67% of dollars traced to a fetched prospectus or 8-K, 12% to "
             "press, 20% to search snippets. ~\\$18.5bn of miner deals found by the verifier are not yet in.\n"
             "Microsoft issued nothing 2024-26. Ratings are the agency letter printed at pricing; "
             "\"not captured\" = no rating in the fetched document.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(os.path.join(OUT, "fig_aidebt_tally.png"), dpi=150, facecolor=SURF)


# --------------------------------------------------------------- 2. Japan
def fig_japan():
    tic = _read(os.path.join(DATA, "tic_net_purchases_by_country_2015_2026.csv"))
    tx = [_ym(r["month"]) for r in tic]
    def col(name):
        return _roll12([float(r[name]) / 1000 if r[name] not in ("", "nan") else np.nan for r in tic])
    boj = _read(os.path.join(DATA, "boj_japan_US_ltdebt_sovereign_vs_nonsovereign_monthly.csv"))
    bx = [_ym(r["month"]) for r in boj]
    b_sov = _roll12([float(r["JP_net_purch_US_sovereign_LT_100mJPY"]) / 1e4 for r in boj])      # JPY trn
    b_non = _roll12([float(r["residual_nonsovereign_LT_100mJPY"]) / 1e4 for r in boj])
    mof = _read(os.path.join(DATA, "mof_japan_lt_debt_net_purchases_by_investor_type_monthly.csv"))
    mof = [r for r in mof if r["year_month"] >= "2013-01"]
    mx = [_ym(r["year_month"]) for r in mof]
    def mcol(name):
        return _roll12([float(r[name]) / 1e4 if r[name] not in ("", "-") else np.nan for r in mof])

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), facecolor=SURF)
    (a, b), (c, d) = axes
    for ax in axes.flat:
        ax.set_facecolor(SURF)
        _style(ax)
        ax.set_xlim(2015, 2027)
        ax.axvspan(2024, 2026.8, color="#f1efe9", zorder=0)

    a.plot(tx, col("Japan_net_Treasuries_usd_mn"), color=BLUE, lw=2, label="long-term Treasuries")
    a.plot(tx, col("Japan_net_CorpBonds_usd_mn"), color=ORANGE, lw=2, label="US corporate bonds")
    a.set_title("Japan: net purchases of US securities, 12-month sum (\\$bn, TIC, long-term only)", loc="left",
                fontsize=9.5, color=INK)
    a.legend(frameon=False, fontsize=8, loc="lower left")
    a.text(2015.3, 112, "12m to Jul-26: Treasuries +\\$4bn (−\\$49bn once bills are included); corporates +\\$12bn",
           fontsize=7.5, color=INK, va="top")

    b.plot(bx, b_sov, color=BLUE, lw=2, label="US sovereign (Treasuries + agencies)")
    b.plot(bx, b_non, color=ORANGE, lw=2, label="US non-sovereign (corporate residual)")
    b.set_title("Japanese residents: net purchases of US long-term debt, 12m sum (JPY trn, BoJ)",
                loc="left", fontsize=9, color=INK)
    b.legend(frameon=False, fontsize=8, loc="lower left")

    c.plot(tx, col("Grand Total_net_Treasuries_usd_mn"), color=BLUE, lw=2, label="long-term Treasuries")
    c.plot(tx, col("Grand Total_net_CorpBonds_usd_mn"), color=ORANGE, lw=2, label="US corporate bonds")
    c.set_title("ALL foreigners: net purchases, 12-month sum (\\$bn, TIC) — real rotation, unattributable",
                loc="left", fontsize=9.5, color=INK)
    c.legend(frameon=False, fontsize=8, loc="upper left")

    for name, colr, lab in (("Banks(Banking Accounts)", BLUE, "banks"),
                            ("Life Insurance Companies", ORANGE, "life insurers"),
                            ("Banks and Trust banks(Trust Accounts)", GREEN, "trust accounts (pension money)"),
                            ("Investment Trust Management Companies", PURPLE, "investment trusts")):
        d.plot(mx, mcol(name), color=colr, lw=2, label=lab)
    d.set_title("Japanese investors by type: net purchases of ALL foreign LT debt, 12m sum (JPY trn, MOF)",
                loc="left", fontsize=9, color=INK)
    d.legend(frameon=False, fontsize=8, loc="lower left", ncol=2)
    for ax in (b, d):
        ax.set_ylabel("JPY trn", color=INK2)
    for ax in (a, c):
        ax.set_ylabel("\\$bn", color=INK2)
    fig.suptitle("Japan is selling Treasuries and NOT buying US corporates in their place: the money is going home",
                 x=0.01, ha="left", fontsize=11.5, color=INK)
    fig.text(0.01, 0.01, "Shaded = the AI issuance wave (2024→). TIC attributes by custody country and asset class only; "
             "BoJ 'non-sovereign' = all US long-term debt minus Treasuries/agencies/munis. 2026 data to Jul (TIC), "
             "Aug (BoJ), Sep (MOF).", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(os.path.join(OUT, "fig_aidebt_japan.png"), dpi=150, facecolor=SURF)


# --------------------------------------------------------------- 3. breaking
NIC30 = {  # 30-year tranche spread at issue (bp over Treasuries), USD deals, from the FWPs / memo s.5
    "Meta": [("2024-08-07", 115), ("2025-10-30", 98), ("2026-04-30", 132)],
    "Alphabet": [("2025-04-28", 62), ("2025-11-04", 82), ("2026-02-10", 83), ("2026-08-07", 115)],
    "Amazon": [("2025-11-17", 75), ("2026-03-10", 105), ("2026-07-07", 110)],
    "Oracle": [("2025-09-24", 125), ("2026-02-02", 180)],
}


def _fred(series, since="2023-10-01"):
    rows = _read(os.path.join(DATA, "fred", f"fred_{series}.csv"))
    xs, ys = [], []
    for r in rows:
        d, v = r["observation_date"], r[series]
        if d >= since and v not in ("", "."):
            y, m, dd = (int(p) for p in d.split("-"))
            xs.append(y + (m - 1 + (dd - 1) / 31) / 12)
            ys.append(float(v))
    return xs, ys


def fig_breaking():
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), facecolor=SURF)
    for ax in axes:
        ax.set_facecolor(SURF)
        _style(ax, y0=False)
    a, b, c = axes
    half = [2024, 2024.5, 2025, 2025.5, 2026, 2026.5]
    half_lab = ["Jan-24", "Jul-24", "Jan-25", "Jul-25", "Jan-26", "Jul-26"]
    for ax in (a, b):
        ax.set_xticks(half)
        ax.set_xticklabels(half_lab)
    for s, colr, lab in (("BAMLH0A3HYC", CRIT, "CCC & lower"), ("BAMLH0A1HYBB", ORANGE, "BB"),
                         ("BAMLC0A4CBBB", BLUE, "BBB"), ("BAMLC0A2CAA", GREEN, "AA")):
        x, y = _fred(s)
        a.plot(x, [v * 100 for v in y], color=colr, lw=1.6, label=lab)
        a.text(x[-1] + 0.03, y[-1] * 100, f"{lab} {y[-1] * 100:.0f}", fontsize=7.5, color=colr, va="center")
    a.set_yscale("log")
    a.set_yticks([50, 100, 200, 400, 800, 1600])
    a.set_yticklabels(["50", "100", "200", "400", "800", "1600"])
    a.set_xlim(2023.75, 2027.2)
    a.set_title("Spreads by rating (bp, ICE BofA OAS; log scale)", loc="left", fontsize=9.5, color=INK)
    a.legend(frameon=False, fontsize=7.5, loc="upper left")

    x, y = _fred("DGS30", "2024-01-01")
    b.plot(x, y, color=BLUE, lw=1.6, label="30-year Treasury yield")
    acm = _read(os.path.join(DATA, "fred", "acm_term_premium_daily.csv"))
    ax_, ay_ = [], []
    for r in acm:
        if r["date"] >= "2024-01-01":
            yy, mm, dd = (int(p) for p in r["date"].split("-"))
            ax_.append(yy + (mm - 1 + (dd - 1) / 31) / 12)
            ay_.append(float(r["ACMTP10"]))
    b.plot(ax_, ay_, color=ORANGE, lw=1.6, label="10-year term premium (ACM)")
    b.text(x[-1] + 0.03, y[-1], f"{y[-1]:.2f}", fontsize=7.5, color=BLUE, va="center")
    b.text(ax_[-1] + 0.03, ay_[-1], f"{ay_[-1]:.2f}", fontsize=7.5, color=ORANGE, va="center")
    b.set_xlim(2024, 2027)
    b.set_title("The Treasury side (%): 30y at 5.67% on 7 Oct, highest since 2002", loc="left", fontsize=9.5, color=INK)
    b.legend(frameon=False, fontsize=7.5, loc="center left")

    for (iss, pts), colr in zip(NIC30.items(), (BLUE, GREEN, ORANGE, CRIT)):
        xs = [int(d[:4]) + (int(d[5:7]) - 1 + (int(d[8:]) - 1) / 31) / 12 for d, _ in pts]
        ys = [v for _, v in pts]
        c.plot(xs, ys, color=colr, lw=1.4, marker="o", ms=6, label=iss)
        c.text(xs[-1] + 0.04, ys[-1], f"{iss} {ys[-1]}", fontsize=7.5, color=colr, va="center")
    c.set_xlim(2024.5, 2027.1)
    c.set_ylim(40, 200)
    c.set_title("Hyperscaler deals: 30y spread at issue (bp over UST)", loc="left",
                fontsize=9.5, color=INK)
    c.set_xticks([2024.5, 2025, 2025.5, 2026, 2026.5])
    c.set_xticklabels(["Jul-24", "Jan-25", "Jul-25", "Jan-26", "Jul-26"])
    fig.suptitle("Breaking gauges, free and daily: CCC at a 2026 high while AA/BBB are calm; the cost of AI money "
                 "rises deal by deal", x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, "FRED serves only 3 years of ICE OAS history since April 2026. Spreads at issue from the "
             "pricing term sheets (FWPs) on EDGAR; Oracle was cut to BBB- on 9 Jul 2026. Data to 14 Oct 2026.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(os.path.join(OUT, "fig_aidebt_breaking.png"), dpi=150, facecolor=SURF)


if __name__ == "__main__":
    fig_tally()
    fig_japan()
    fig_breaking()
    print("wrote", OUT)
