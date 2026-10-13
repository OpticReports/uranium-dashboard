#!/usr/bin/env python3
"""Figures for studies/distress-bottoms.md (reads bottoms_results.json + data/).

    python3 bottoms_charts.py [outdir]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bottoms as BT  # noqa: E402
import bottoms_engine as B  # noqa: E402
import load as D  # noqa: E402
from engine import M  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figs")
os.makedirs(OUT, exist_ok=True)
SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8985", "#e6e5e1"
BLUE, ORANGE, GREEN, CRIT = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
REC, BAND = "#e9e8e4", "#f1efe9"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})
RES = json.load(open(os.path.join(HERE, "bottoms_results.json")))


def mi(s: str) -> int:
    return M(int(s[:4]), int(s[5:7]))


def d_of(m: int) -> dt.date:
    return dt.date(m // 12, m % 12 + 1, 15)


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_axisbelow(True)


# ------------------------------------------------------------------ 1. timing strip
def fig_timing():
    P = RES["P"]
    eps = P["shots"]["CONFIRMS-trough"]["episodes"]
    eq = {e["peak"]: e for e in P["shots"]["MARKS-equity"]["episodes"]}
    gpk = {g["peak"]: g for g in P["g_peak"]["episodes"]}
    rows = []
    for e in eps:
        tau = mi(e["trough"])
        b = RES["equity_targets"][e["peak"]]
        eq_e = (mi(b["b"]) - tau) if b["b"] and b["status"] != "no equity low" else None
        rows.append({"label": f"{e['peak'][:4]}–{e['trough'][2:4]}", "sig": e["e"], "outcome": e["outcome"],
                     "eq": eq_e, "eq_status": b["status"], "gpk": gpk.get(e["peak"], {}).get("e_trough"),
                     "src": "D&B failures"})
    for pk, r in RES["R"]["primary"]["episodes"].items():
        p = mi(pk)
        tau = dict(BT.CHRON)[p]
        x = r.get("CONFIRMS-trough", {})
        b = RES["equity_targets"][pk]
        rows.append({"label": f"{pk[:4]}–{BT.mstr(tau)[2:4]}", "sig": x.get("e"), "outcome": x.get("outcome"),
                     "eq": (mi(b["b"]) - tau) if b["b"] and b["status"] != "no equity low" else None,
                     "eq_status": b["status"], "gpk": None, "src": "court filings",
                     "claims": RES["claims"].get(pk, {}).get("C1/CONFIRMS-trough", {}).get("e")})
    ph = json.load(open(os.path.join(HERE, "bottoms_posthoc.json")))
    ph_e = {r["peak"]: r["e_trough"] for r in ph["episodes"]}
    for r_, e in zip(rows, eps):
        x = ph_e.get(e["peak"])
        r_["posthoc"] = x if x is not None and x != r_["sig"] else None
    fig, ax = plt.subplots(figsize=(11.5, 8.2))
    fig.patch.set_facecolor(SURF)
    style(ax)
    n = len(rows)
    ax.axvspan(0, 9, color=BAND, lw=0, zorder=0)
    ax.text(4.5, -1.35, "0–9 months after the trough\n(the 'confirms' window)", ha="center", va="bottom",
            fontsize=7.5, color=INK2)
    ax.axvline(0, color=INK2, lw=1)
    for i, r in enumerate(rows):
        y = n - 1 - i
        ax.axhline(y, color=GRID, lw=0.6, zorder=0)
        if r["eq"] is not None:
            hollow = r["eq_status"] != "valid"
            ax.scatter([r["eq"]], [y], marker="D", s=46, zorder=4, facecolor=SURF if hollow else BLUE,
                       edgecolor=BLUE, lw=1.4)
        if r.get("gpk") is not None:
            ax.scatter([r["gpk"]], [y], marker="o", s=46, zorder=3, facecolor=SURF, edgecolor=MUTED, lw=1.4)
        if r.get("claims") is not None:
            ax.scatter([r["claims"]], [y], marker="^", s=54, zorder=4, color=GREEN, edgecolor=SURF, lw=1)
        if r.get("posthoc") is not None:
            ax.scatter([r["posthoc"]], [y], marker="o", s=62, zorder=5, facecolor=SURF, edgecolor=ORANGE, lw=1.5)
        if r["sig"] is not None:
            ax.scatter([r["sig"]], [y], marker="o" if r["src"] == "D&B failures" else "s", s=62, zorder=5,
                       color=ORANGE, edgecolor=SURF, lw=1.2)
            if r["sig"] < -20:
                ax.annotate("false start", (r["sig"], y), xytext=(6, 4), textcoords="offset points", fontsize=7,
                            color=INK2)
        else:
            ax.text(27.5, y, "censored" if r["outcome"] == "CENSORED" else "no signal", va="center",
                    ha="right", fontsize=8, color=INK2)
        if r.get("posthoc") is not None and r["posthoc"] < -15:
            ax.annotate("1931 false dawn", (r["posthoc"], y), xytext=(6, 4), textcoords="offset points",
                        fontsize=7, color=INK2)
    ax.axhline(3.5, color=INK2, lw=0.8, ls=":")
    ax.text(-29.5, 3.62, "↑ D&B failure counts (primary)", fontsize=7.5, color=INK2)
    ax.text(-29.5, 3.38, "↓ court filings (context) and the jobless-claims benchmark", fontsize=7.5, color=INK2,
            va="top")
    ax.set_yticks(range(n))
    ax.set_yticklabels([r["label"] for r in rows][::-1], fontsize=8)
    ax.set_xlim(-30, 28)
    ax.set_ylim(-1.5, n - 0.4)
    ax.set_xlabel("months relative to the NBER trough (release-dated)")
    for lab, kw in (("roll-over signal (released)", dict(marker="o", color=ORANGE, s=62)),
                    ("post-hoc: re-armed after growth turns negative (not tested)",
                     dict(marker="o", facecolor=SURF, edgecolor=ORANGE, s=62)),
                    ("equity low (hollow: ambiguous/censored)", dict(marker="D", color=BLUE, s=46)),
                    ("growth peak, in hindsight", dict(marker="o", facecolor=SURF, edgecolor=MUTED, s=46)),
                    ("jobless-claims peak (benchmark)", dict(marker="^", color=GREEN, s=54))):
        ax.scatter([], [], label=lab, **kw)
    ax.legend(loc="lower left", fontsize=7.5, frameon=False, ncol=2, bbox_to_anchor=(0.0, 1.0))
    fig.suptitle("Bankruptcy growth slows AFTER the bottom: it confirmed the economic trough months later "
                 "(when it fired) and never marked the stock-market low", x=0.01, ha="left", fontsize=11,
                 color=INK, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(os.path.join(OUT, "fig_bottoms_timing.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ 2. the series
def fig_series():
    rule = B.Rule(**RES["rule"])
    spans = BT.spans_p(D.dnb_count_segments())
    G = BT.growth_by_span(spans, rule)
    sig_rel = {mi(x["release"]): x["kind"] for x in RES["P"]["false_bottoms"]["signals"]}
    P, _ = D.shiller_monthly()
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    fig.patch.set_facecolor(SURF)
    windows = ((M(1895, 1), M(1940, 12), ("A1", "A2", "B")), (M(1940, 1), M(1965, 12), ("C",)))
    for ax, (lo, hi, names) in zip(axes[:2], windows):
        style(ax)
        ax.grid(color=GRID, lw=0.8, axis="y")
        for p, tau in BT.CHRON:
            if lo <= p <= hi:
                ax.axvspan(d_of(p), d_of(tau), color=REC, lw=0, zorder=0)
        for nm in names:
            g = G[nm]["g"]
            a, b = (M(1936, 10), M(1939, 12)) if nm == "B" else (lo, hi)
            if nm == "A2":
                a, b = M(1933, 1), M(1936, 9)
            ks = [t for t in sorted(g) if a <= t <= b and lo <= t <= hi]
            ax.plot([d_of(t) for t in ks], [100 * g[t] for t in ks], color=BLUE, lw=1.3)
        ax.axhline(15, color=CRIT, lw=1, ls="--")
        ax.text(d_of(lo + 2), 18, "armed above +15%", fontsize=7.5, color=CRIT)
        for r, kind in sig_rel.items():
            if lo <= r <= hi:
                ax.axvline(d_of(r), color=ORANGE if kind == "TRUE BOTTOM" else INK2, lw=1.3, ymax=0.92)
        for pk, b in RES["equity_targets"].items():
            if b["b"] and b["status"] != "no equity low" and lo <= mi(b["b"]) <= hi:
                ax.scatter([d_of(mi(b["b"]))], [ax.get_ylim()[1] * 0.0 + 95], marker="v", color=BLUE, s=36,
                           zorder=5)
        ax.set_ylim(-60, 100)
        ax.set_ylabel("failures, 6-month sum,\n% vs a year earlier")
        ax.set_xlim(d_of(lo), d_of(hi))
    axes[0].set_title("Dun & Bradstreet business failures (number), 1895–1940: growth and its roll-overs",
                      loc="left", fontsize=10, color=INK)
    axes[1].set_title("1940–1965 (wartime record lows, then multi-year rises: no roll-over in any postwar "
                      "recession)", loc="left", fontsize=10, color=INK)
    # court filings
    ax = axes[2]
    style(ax)
    ax.grid(color=GRID, lw=0.8, axis="y")
    rq = B.Rule(w=2, lag=4, look=4, theta=rule.theta, frac=rule.frac, floor=rule.floor, k=1)
    vals, bad = BT.court_series()
    g = B.growth(vals, rq, bad=bad)
    qs = sorted(g)
    for p, tau in BT.CHRON:
        if p >= M(1980, 1):
            ax.axvspan(d_of(p), d_of(tau), color=REC, lw=0, zorder=0)
    for a, b in ((M(2005, 4), M(2010, 12)), (M(2020, 4), M(2023, 6))):
        ax.axvspan(d_of(a), d_of(b), color="#f3efe6", lw=0, zorder=0, hatch="///", edgecolor=GRID)
    xs = [d_of(BT.q_release(q) - 1) for q in qs]
    # break the line across the masks
    seg = []
    for q, x in zip(qs, xs):
        if seg and q != seg[-1][0] + 1:
            ax.plot([s[1] for s in seg], [100 * g[s[0]] for s in seg], color=BLUE, lw=1.3)
            seg = []
        seg.append((q, x))
    ax.plot([s[1] for s in seg], [100 * g[s[0]] for s in seg], color=BLUE, lw=1.3)
    ax.axhline(15, color=CRIT, lw=1, ls="--")
    for x in RES["R"]["primary"]["signals"]:
        r = mi(x["release"])
        ax.axvline(d_of(r), color=ORANGE if x["kind"] == "TRUE BOTTOM" else INK2, lw=1.3, ymax=0.92)
        ax.text(d_of(r + 2), 52, x["release"] + ("" if x["kind"] == "TRUE BOTTOM" else "\nno recession"),
                fontsize=7, color=INK2)
    live = RES["R"]["primary"]["live"]
    ax.annotate(f"{live['asof']}: {100 * live['g']:+.0f}%,\narmed, not rolled over", (xs[-1], 100 * g[qs[-1]]),
                xytext=(-140, 20), textcoords="offset points", fontsize=8, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.set_ylim(-60, 70)
    ax.set_xlim(d_of(M(1981, 1)), d_of(M(2027, 3)))
    ax.set_ylabel("business filings, 2-quarter sum,\n% vs a year earlier")
    ax.set_title("Court business bankruptcy filings, 1981–2026 (context): roll-overs 5 months after the 1982 "
                 "and 2001 troughs; two with no recession", loc="left", fontsize=10, color=INK)
    fig.text(0.01, 0.005, "Grey bands = NBER recessions; hatched = masked (2005 law change, 2020-21 support). "
             "Orange lines = roll-over released within -6..+9 months of a trough; dark grey = no recession "
             "nearby. Blue triangles = equity lows.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(os.path.join(OUT, "fig_bottoms_series.png"), dpi=150, facecolor=SURF)


# ------------------------------------------------------------------ 3. trader's view
def fig_trader():
    med = RES["trader"]["median"]
    order = [("rollover_P", "bankruptcy roll-over (D&B)"), ("rollover_R", "bankruptcy roll-over (court)"),
             ("arm_P", "first month failures +15%"), ("random_armed_P", "random month while armed"),
             ("peak_plus_6", "6 months after recession start"), ("minus_20pct", "stocks 20% off their high"),
             ("claims_C1", "jobless-claims peak"), ("claims_C2", "claims roll-over")]
    rows = [(lab, med[k]) for k, lab in order if k in med]
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), sharey=True)
    fig.patch.set_facecolor(SURF)
    stats = (("ret_12m", "median 12-month total return"), ("worst_dd_12m", "median worst further drop (12 m)"),
             ("rebound_missed", "median share of the low-to-+12m rebound\nalready missed at entry"))
    for ax, (k, title) in zip(axes, stats):
        style(ax)
        ax.grid(color=GRID, lw=0.8, axis="x")
        ys = range(len(rows))
        vals = [100 * r[1].get(k, float("nan")) for r in rows]
        cols = [ORANGE if "roll-over (" in r[0] else (GREEN if "claims" in r[0] else BLUE) for r in rows]
        ax.barh(list(ys), vals, color=cols, height=0.55)
        span = max(abs(x) for x in vals if x == x)
        for y, v, r in zip(ys, vals, rows):
            if v != v:
                continue
            txt = f"{v:.0f}%" if k == "rebound_missed" else f"{v:+.0f}%".replace("+0%", "0%").replace("-0%", "0%")
            if k == "worst_dd_12m":           # drops point left: label just right of zero
                ax.text(0.02 * span, y, txt, va="center", ha="left", fontsize=7.5, color=INK2)
            elif v < 0:                       # a negative return: label right of zero
                ax.text(0.02 * span, y, txt, va="center", ha="left", fontsize=7.5, color=INK2)
            else:
                ax.text(v + 0.02 * span, y, txt, va="center", ha="left", fontsize=7.5, color=INK2)
        if k == "worst_dd_12m":
            ax.set_xlim(right=0.18 * span)
        ax.axvline(0, color=INK2, lw=0.8)
        ax.set_title(title, loc="left", fontsize=9, color=INK)
    axes[0].set_yticks(list(range(len(rows))))
    axes[0].set_yticklabels([f"{r[0]}  (n={r[1]['entries']})" for r in rows], fontsize=8)
    axes[0].invert_yaxis()
    fig.suptitle("Buying when bankruptcy growth rolls over: little downside left, but most of the rebound "
                 "already gone", x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "Shiller S&P composite total return, entry the month after each rule fires; medians "
             "over the recessions where the rule fired (n; the episode sets differ by rule).\nRebound missed > 100% = "
             "entered after the first-year rebound was complete. Price data end 2024-06.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(os.path.join(OUT, "fig_bottoms_trader.png"), dpi=150, facecolor=SURF)


if __name__ == "__main__":
    fig_timing()
    fig_series()
    fig_trader()
    print("written to", OUT)
