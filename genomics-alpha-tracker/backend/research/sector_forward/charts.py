"""Forward test calibration charts (EXPLORATORY, last year's data).

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.charts
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "charts"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
SERIES = {"B1": ("volatility (60-day)", "#2a78d6"), "R1": ("trial date (nearest completion)", "#eb6834"),
          "H1": ("hybrid (readout window first, then volatility)", "#1baf7a")}


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    c2 = json.loads((HERE / "calibration2.json").read_text())
    OUT.mkdir(exist_ok=True)

    # 1. hit@K by ranking, all caps vs small/mid caps
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True, facecolor=SURFACE)
    for ax, scope, title in ((axes[0], "rankings_all", "All genomics names (incl. big pharma)"),
                             (axes[1], "rankings_small_mid", "Small/mid caps only (< $10B)")):
        style(ax)
        d = c2[scope]
        ks = ["10", "25", "40"]
        w = 0.26
        for j, key in enumerate(("B1", "R1", "H1")):
            lab, col = SERIES[key]
            xs = [i + (j - 1) * (w + 0.02) for i in range(len(ks))]
            ys = [100 * d[k][key] for k in ks]
            ax.bar(xs, ys, width=w, color=col, label=lab, edgecolor=SURFACE, linewidth=2)
            for x, y, k in zip(xs, ys, ks):
                if k == "25":   # selective labels: the list length a desk would scan
                    ax.text(x, y + 1.2, f"{y:.0f}%", ha="center", va="bottom", fontsize=8, color=INK)
        for i, k in enumerate(ks):
            r = 100 * d[k]["random"]
            ax.hlines(r, i - 0.45, i + 0.45, colors=INK2, linestyles=(0, (3, 2)), lw=1.4,
                      label="random list" if i == 0 else None)
        ax.set_xticks(range(len(ks)), [f"top {k}" for k in ks])
        ax.set_title(f"{title} — {d['events']} moves", fontsize=10, color=INK, loc="left")
        ax.set_ylim(0, 85)
    axes[0].set_ylabel("share of next-day 20% moves on the list, %", color=INK2, fontsize=9)
    axes[1].legend(fontsize=8, frameon=False, loc="upper left")
    fig.suptitle("Which list held tomorrow's big genomics movers? Past year, exploratory calibration",
                 fontsize=11, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "calibration_hit_rates.png", dpi=140, facecolor=SURFACE)
    plt.close(fig)

    # 2. event rate by volatility quintile, with the readout-window odds ratio
    fig, ax = plt.subplots(figsize=(7.5, 4), facecolor=SURFACE)
    style(ax)
    q = c2["event_rate_by_vol_quintile"]
    xs = list(range(1, 6))
    ys = [100 * q[str(i)] for i in xs]
    ax.bar(xs, ys, width=0.6, color="#2a78d6", edgecolor=SURFACE, linewidth=2)
    for x, y in zip(xs, ys):
        ax.text(x, y + 0.02, f"{y:.2f}%", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(xs, ["lowest", "2", "3", "4", "highest"])
    ax.set_xlabel("60-day volatility quintile", color=INK2, fontsize=9)
    ax.set_ylabel("chance of a 20% move next day, %", color=INK2, fontsize=9)
    mh = c2["readout_window_mh"]
    ax.text(0.02, 0.95, f"In a readout window, same volatility and size:\nodds ×{mh['odds_ratio']:.2f} "
                        f"(90% CI {mh['ci90_name_bootstrap'][0]:.2f}–{mh['ci90_name_bootstrap'][1]:.2f})",
            transform=ax.transAxes, va="top", fontsize=9, color=INK)
    ax.set_title("Volatility predicts big moves 20×; trial dates add ~nothing", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "calibration_signal.png", dpi=140, facecolor=SURFACE)
    plt.close(fig)
    print("charts written")


if __name__ == "__main__":
    main()
