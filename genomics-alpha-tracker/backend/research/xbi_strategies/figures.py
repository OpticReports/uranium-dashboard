"""Charts for the XBI strategy study (reads results.json)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from research.xbi_strategies.xbi_lib import HERE  # noqa: E402

OUTDIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
BG, PANEL, GRID, TXT = "#0f1420", "#121826", "#1f2937", "#cbd5e1"
COL = {"B0": "#f59e0b", "B1": "#94a3b8", "R1": "#38bdf8", "D1": "#a78bfa", "S2": "#34d399",
       "B2": "#f472b6", "V3": "#fb923c", "C1a": "#22d3ee", "C1b": "#86efac", "C1c": "#e879f9",
       "C1d": "#fbbf24", "T4": "#fde047"}


def style(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=TXT, labelsize=8)
    for sp in ax.spines.values():
        sp.set_color("#334155")
    ax.grid(color=GRID, lw=0.6)


def scatter(r):
    fig, ax = plt.subplots(figsize=(9.5, 6.4), facecolor=BG)
    style(ax)
    b0 = r["variants"]["B0"]["full"]
    for vid, v in r["variants"].items():
        f = v["full"]
        if not f:
            continue
        post = v.get("post_hoc")
        late = v["start"] > "2008-01-01"
        c = "#f59e0b" if vid == "B0" else ("#22d3ee" if post else ("#64748b" if late else "#e2e8f0"))
        ax.scatter(f["max_dd"] * 100, f["cagr"] * 100, s=70 if vid == "B0" else 34, color=c,
                   marker="*" if vid == "B0" else ("D" if post else ("x" if late else "o")), zorder=3)
        ax.annotate(vid, (f["max_dd"] * 100, f["cagr"] * 100), xytext=(4, 3), textcoords="offset points",
                    fontsize=8, color=c)
    ax.axhline(b0["cagr"] * 100, color="#f59e0b", lw=0.8, ls="--", alpha=0.6)
    ax.axhline((b0["cagr"] - 0.02) * 100, color="#f59e0b", lw=0.8, ls=":", alpha=0.6)
    ax.axvline((b0["max_dd"] - 0.10) * 100, color="#f59e0b", lw=0.8, ls=":", alpha=0.6)
    ax.axvspan(0, (b0["max_dd"] - 0.10) * 100, ymin=0, ymax=1, color="#34d399", alpha=0.04)
    ax.set_xlabel("max drawdown % (daily curve)", color=TXT, fontsize=9)
    ax.set_ylabel("CAGR %", color=TXT, fontsize=9)
    ax.set_title("Every variant vs XBI buy & hold, 2007-09 → 2026-10 (x = starts later; ◆ = post-hoc combo)\n"
                 "pass zone = left of the dotted DD line AND above the dotted CAGR line", color="#e2e8f0",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUTDIR / "xbi_scatter.png", dpi=150, facecolor=BG)


def curves(r, ids, name, title):
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, facecolor=BG,
                               gridspec_kw={"height_ratios": [3, 1.3]})
    style(a)
    style(b)
    for vid in ids:
        v = r["variants"].get(vid)
        if not v:
            continue
        pts = v["curve_weekly"]
        x = [date.fromisoformat(d) for d, _ in pts]
        y = [val for _, val in pts]
        f = v["full"]
        lab = f"{vid} {v['note'][:38]}  CAGR {f['cagr']:+.1%} · DD {f['max_dd']:.0%} · Sharpe {f['sharpe']:.2f}"
        a.plot(x, y, color=COL.get(vid, "#e2e8f0"), lw=2.0 if vid == "B0" else 1.3, label=lab)
        peak, dd = y[0], []
        for val in y:
            peak = max(peak, val)
            dd.append(100 * (val / peak - 1))
        b.plot(x, dd, color=COL.get(vid, "#e2e8f0"), lw=1.0)
    a.set_yscale("log")
    a.set_ylabel("growth of 1 (log)", color=TXT, fontsize=8)
    a.legend(facecolor=PANEL, edgecolor="#334155", labelcolor="#e2e8f0", fontsize=7.5, loc="upper left")
    a.set_title(title, color="#e2e8f0", fontsize=10, loc="left")
    b.set_ylabel("drawdown % (weekly pts)", color=TXT, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUTDIR / name, dpi=150, facecolor=BG)


def main():
    r = json.loads((HERE / "results.json").read_text())
    scatter(r)
    curves(r, ["B0", "B1", "R1", "D1", "S2", "B2"], "xbi_curves_prereg.png",
           "Pre-registered variants closest to the pass zone vs XBI and SPY (costs included)")
    curves(r, ["B0", "R1", "C1a", "C1b", "C1c", "C1d"], "xbi_curves_posthoc.png",
           "POST-HOC combos around the inverse-vol XBI/TLT/GLD idea (in-sample selection, not evidence)")
    print("wrote", OUTDIR)


if __name__ == "__main__":
    main()
