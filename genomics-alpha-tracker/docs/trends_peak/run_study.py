"""Google Trends attention-top study: replay the detector over eleven frozen
weekly series (Google Trends interest + weekly close) and measure what
happened after each flag. Run from genomics-alpha-tracker/backend:

    python ../docs/trends_peak/run_study.py            # writes study_results.json
    python ../docs/trends_peak/run_study.py --charts   # + charts/*.png (needs matplotlib)

Pure Python except the optional charts. Every number in the study doc's
honesty box comes from study_results.json; tests/test_trends_detector.py
pins the headline rows so a detector change that moves them fails the gate.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "backend"))
from app.trends.detector import compute, episodes, PARAMS  # noqa: E402

HORIZONS = (4, 12, 26)
EVENTS = ["silver_2011", "silver_2026", "bitcoin_2017", "bitcoin_2021", "bitcoin_2025",
          "arkg_2021", "crispr_2021", "uranium_2021", "uranium_2024", "gme_2021", "gold_2026"]


def load(name: str) -> dict:
    return json.load(open(HERE / "fixtures" / f"{name}.json"))


def fwd(close: list, i: int, h: int):
    if i + h >= len(close) or close[i] is None or close[i + h] is None:
        return None
    return round(100 * (close[i + h] / close[i] - 1), 1)


def _segment(close: list, i: int, h: int):
    # Full horizon required (counter-agent 2026-09-08): a flag inside the
    # last h weeks must not pool a truncated drawdown as an h-week one.
    if i + h >= len(close) or close[i] is None:
        return None
    seg = [c for c in close[i:i + h + 1] if c is not None]
    return seg if len(seg) >= 2 else None


def maxdd(close: list, i: int, h: int = 26):
    seg = _segment(close, i, h)
    return None if seg is None else round(100 * (min(seg) / seg[0] - 1), 1)


def maxup(close: list, i: int, h: int = 26):
    seg = _segment(close, i, h)
    return None if seg is None else round(100 * (max(seg) / seg[0] - 1), 1)


def study() -> dict:
    per_event = {}
    pooled = {f: [] for f in ("climax", "fading", "divergence", "cooled")}
    base = []
    for name in EVENTS:
        fx = load(name)
        w = fx["weeks"]
        dates = [x["date"] for x in w]
        interest = [x["interest"] for x in w]
        close = [x["close"] for x in w]
        pts = compute(dates, interest, close)
        valid = [i for i, c in enumerate(close) if c is not None]
        ip = max(valid, key=lambda i: close[i])
        it = max(range(len(interest)), key=lambda i: interest[i])
        ev = {"keyword": fx["keyword"], "price_symbol": fx["price_symbol"], "timeframe": fx["timeframe"],
              "weeks": len(w), "price_peak": dates[ip], "trend_peak": dates[it],
              "trend_peak_minus_price_peak_wk": it - ip, "flags": {}}
        # base rate: every week with 26 weeks of forward data and a warmed-up detector
        for i in range(52, len(w) - 26):
            base.append({"event": name, "r4": fwd(close, i, 4), "r12": fwd(close, i, 12),
                         "r26": fwd(close, i, 26), "dd26": maxdd(close, i), "up26": maxup(close, i)})
        for flag in pooled:
            rows = []
            for i in episodes(pts, flag):
                row = {"date": dates[i], "wk_vs_price_peak": i - ip, "interest": interest[i],
                       "intensity": pts[i].intensity, "stage": pts[i].stage, "close": close[i],
                       "r4": fwd(close, i, 4), "r12": fwd(close, i, 12), "r26": fwd(close, i, 26),
                       "dd26": maxdd(close, i), "up26": maxup(close, i), "note": pts[i].notes[:1]}
                rows.append(row)
                pooled[flag].append(dict(row, event=name))
            ev["flags"][flag] = rows
        ev["states_tail"] = [(p.date, p.state) for p in pts[-6:]]
        # recall: did a climax fire in the 10 weeks up to and including the price peak?
        ev["climax_within_10wk_before_price_peak"] = any(
            pts[i].climax for i in range(max(0, ip - 10), ip + 1))
        ev["divergence_within_10wk_before_price_peak"] = any(
            pts[i].divergence for i in range(max(0, ip - 10), ip + 1))
        per_event[name] = ev

    def agg(rows, key):
        xs = [r[key] for r in rows if r.get(key) is not None]
        if not xs:
            return None
        return {"n": len(xs), "median": round(statistics.median(xs), 1),
                "mean": round(statistics.mean(xs), 1),
                "pct_negative": round(100 * sum(x < 0 for x in xs) / len(xs)),
                "pct_dd_worse_than_20": round(100 * sum(x <= -20 for x in xs) / len(xs)) if key == "dd26" else None}

    stats = {"base_rate": {k: agg(base, k) for k in ("r4", "r12", "r26", "dd26", "up26")}}
    for flag, rows in pooled.items():
        stats[flag] = {"episodes": len(rows), **{k: agg(rows, k) for k in ("r4", "r12", "r26", "dd26", "up26")}}
    for stg, rows in (("climax_stage1", [r for r in pooled["climax"] if r["stage"] == 1]),
                      ("climax_stage2plus", [r for r in pooled["climax"] if (r["stage"] or 1) >= 2])):
        stats[stg] = {"episodes": len(rows), **{k: agg(rows, k) for k in ("r4", "r12", "r26", "dd26", "up26")},
                      "weeks_to_price_peak": sorted(r["wk_vs_price_peak"] for r in rows),
                      "post_hoc": True}
    recall = [ev["climax_within_10wk_before_price_peak"] for ev in per_event.values()]
    stats["recall"] = {"price_peaks": len(recall), "with_climax_within_10wk": sum(recall),
                       "with_climax_or_divergence_within_10wk": sum(
                           ev["climax_within_10wk_before_price_peak"] or ev["divergence_within_10wk_before_price_peak"]
                           for ev in per_event.values())}
    return {"params": PARAMS, "horizons_weeks": HORIZONS, "events": per_event, "pooled": stats,
            "n_base_weeks": len(base)}


def charts(res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = HERE / "charts"
    out.mkdir(exist_ok=True)
    for name in EVENTS:
        fx = load(name)
        w = fx["weeks"]
        dates = [x["date"] for x in w]
        interest = [x["interest"] for x in w]
        close = [x["close"] for x in w]
        pts = compute(dates, interest, close)
        import datetime as dt
        xs = [dt.date.fromisoformat(d) for d in dates]
        fig, ax = plt.subplots(figsize=(11, 4.2))
        ax2 = ax.twinx()
        ax.plot(xs, interest, color="#7c3aed", lw=1.4, label=f'Google Trends "{fx["keyword"]}"')
        ax2.plot(xs, close, color="#111827", lw=1.2, label=f'{fx["price_symbol"]} weekly close')
        if fx["price_symbol"] == "BTCUSD":
            ax2.set_yscale("log")
        mk = {"climax": ("#dc2626", "^", "CLIMAX"), "fading": ("#f59e0b", "v", "FADING"),
              "divergence": ("#2563eb", "s", "DIVERGENCE"), "cooled": ("#6b7280", "x", "COOLED")}
        for flag, (col, m, lab) in mk.items():
            idx = [i for i, p in enumerate(pts) if getattr(p, flag)]
            if idx:
                ax2.scatter([xs[i] for i in idx], [close[i] for i in idx], color=col, marker=m,
                            s=42, zorder=5, label=lab)
        ax.set_ylabel("search interest (0-100, window-relative)", color="#7c3aed")
        ax2.set_ylabel("price")
        ax.set_title(f"{name}: attention vs price")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(out / f"{name}.png", dpi=110)
        plt.close(fig)
    # pooled forward-return chart
    import numpy as np
    fig, ax = plt.subplots(figsize=(8, 4))
    labels, meds, ns = [], [], []
    for k in ("base_rate", "climax", "fading", "divergence", "cooled"):
        s = res["pooled"][k]
        for h in ("r12", "r26", "dd26"):
            a = s.get(h)
            labels.append(f"{k}\n{h}")
            meds.append(a["median"] if a else 0)
            ns.append(a["n"] if a else 0)
    cols = ["#9ca3af"] * 3 + ["#dc2626"] * 3 + ["#f59e0b"] * 3 + ["#2563eb"] * 3 + ["#6b7280"] * 3
    ax.bar(range(len(meds)), meds, color=cols)
    for i, (m, n) in enumerate(zip(meds, ns)):
        ax.text(i, m + (1 if m >= 0 else -4), f"n={n}", ha="center", fontsize=7)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("median forward % (r12, r26) / median 26wk max drawdown %")
    ax.set_title("Pooled outcomes after each flag vs all-weeks base rate (11 series)")
    fig.tight_layout()
    fig.savefig(out / "pooled_outcomes.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    res = study()
    json.dump(res, open(HERE / "study_results.json", "w"), indent=1, default=str)
    for name, ev in res["events"].items():
        print(f"== {name}: price peak {ev['price_peak']}, trend peak {ev['trend_peak']} "
              f"({ev['trend_peak_minus_price_peak_wk']:+d} wk)")
        for flag, rows in ev["flags"].items():
            for r in rows:
                print(f"   {flag:10s} {r['date']} ({r['wk_vs_price_peak']:+4d} wk) stg={r['stage']} r12={r['r12']} r26={r['r26']} dd26={r['dd26']} up26={r['up26']}")
    print(json.dumps(res["pooled"], indent=1))
    if "--charts" in sys.argv:
        charts(res)
        print("charts written")
