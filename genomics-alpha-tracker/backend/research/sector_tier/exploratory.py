"""Sector-tier measurements: EXPLORATORY figure (not pre-registered, not decision-grade).

The pre-registered verdict is INCONCLUSIVE because the shipped baseline had
already queued all but 3 of 125 genomics moves. "Queued" is a weak sense of
"seen": the queue held ~540 names on average. This figure puts every list on
one axis - how many names it holds vs how many genomics moves it held the
name of the day before - so the trade-off is visible. It reads results.json
only and changes no pre-registered number.

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.exploratory
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    res = json.loads((HERE / "results.json").read_text())
    run = res["funnel_titles"] if res.get("verdict_from") == "funnel" else res["strict"]
    rows = [r for r in run["moves"] if r["genomics"] and not r["flag_ma"]]
    win = [x for x in run["sizes_by_week"] if "2025-09-29" <= x["monday"] <= "2026-09-28"]
    avg = lambda k: sum(x[k] for x in win) / len(win)  # noqa: E731
    from datetime import date
    from research.sector_tier import measure as M
    core = M.Core({})
    core_avg = sum(len(core.symbols(date.fromisoformat(x["monday"]))) for x in win) / len(win)
    n = len(rows)
    points = [
        ("core watchlist", core_avg, sum(r["baseline_via"] == "core" for r in rows), "#4575b4"),
        ("Tier 1, rules a+b", avg("ab"), sum(r["tier1_ab"] for r in rows), "#1a9850"),
        ("Tier 1, a+b+c\n(c = look-ahead)", avg("abc"), sum(r["tier1_abc"] for r in rows), "#66bd63"),
        ("baseline: core +\nfunnel queue", avg("baseline"), sum(r["baseline_visible"] for r in rows), "#313695"),
        ("Tier 1 a+b: top 25 or\ncatalyst <= 30 days", 25, sum(r["surfaced_ab"] for r in rows), "#d73027"),
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for lab, x, k, col in points:
        ax.scatter([x], [100 * k / n], s=90, color=col, zorder=3)
        ax.annotate(f"{lab}\n{k}/{n}", (x, 100 * k / n), textcoords="offset points", xytext=(8, -4), fontsize=8)
    ax.set_xscale("log")
    ax.set_xlim(18, 1500)
    ax.set_xticks([25, 50, 100, 250, 500, 1000], ["25", "50", "100", "250", "500", "1000"])
    ax.minorticks_off()
    ax.set_xlabel("names on the list (average over the window, log scale)")
    ax.set_ylabel("genomics moves whose name was on the list the day before, %")
    ax.set_ylim(0, 105)
    ax.set_title("EXPLORATORY - list size vs genomics moves covered (125 moves, M&A days excluded)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    (HERE / "charts").mkdir(exist_ok=True)
    fig.savefig(HERE / "charts" / "exploratory_coverage.png", dpi=130)
    print({lab.replace("\n", " "): (round(x), k) for lab, x, k, _ in points})


if __name__ == "__main__":
    main()
