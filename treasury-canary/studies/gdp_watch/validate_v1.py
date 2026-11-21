"""GDP watch study v1: out-of-sample check of the fan bands, and the study's charts.

Band check: per-country error quantiles of the chosen method are fitted on origins <= 2015-Q4 (pandemic targets
excluded), then the share of 2016+ outcomes inside the p10-p90 and p25-p75 bands is counted, with and without the
pandemic quarters. A well-calibrated 80% band covers about 80%.

    python3 -I validate_v1.py <out_dir>
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, MUTED, GRID = "#0a1022", "#e2e8f0", "#94a3b8", "#1e293b"
SLOTS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]   # validated, dark
SPLIT = "2015-Q4"


def q(s, p):
    s = sorted(s)
    return s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]


def coverage(rows, m, by_country=False):
    out, per = {}, {}
    for h in (1, 2, 3, 4):
        fit = {}
        for r in rows:
            if r["h"] == h and r["t"] <= SPLIT and not r["pandemic"]:
                fit.setdefault(r["c"], []).append(r[m])
        bands = {c: (q(e, .10), q(e, .25), q(e, .75), q(e, .90)) for c, e in fit.items() if len(e) >= 20}
        test = [r for r in rows if r["h"] == h and r["t"] > SPLIT and r["c"] in bands]
        if h == 4:
            for c in sorted(bands):
                sel = [r for r in test if r["c"] == c and not r["pandemic"]]
                if sel:
                    per[c] = {"n": len(sel), "in_80": round(sum(bands[c][0] <= r[m] <= bands[c][3] for r in sel) / len(sel), 2)}
            out["_tested"] = sorted(bands)
        for label, sel in (("ex_pandemic", [r for r in test if not r["pandemic"]]), ("all", test)):
            in80 = sum(bands[r["c"]][0] <= r[m] <= bands[r["c"]][3] for r in sel)
            in50 = sum(bands[r["c"]][1] <= r[m] <= bands[r["c"]][2] for r in sel)
            out.setdefault(str(h), {})[label] = {"n": len(sel), "in_80": round(in80 / len(sel), 3) if sel else None,
                                                 "in_50": round(in50 / len(sel), 3) if sel else None}
    return (out, per) if by_country else out


def block_bootstrap(rows, a, b, reps=1000, block=8, seed=20261116):
    """95% interval of MAE(b)/MAE(a) - 1 (pooled, h = 1..4 averaged, pandemic out), resampling blocks of consecutive
    origin quarters across all economies together (errors overlap across horizons and countries)."""
    import random
    rows = [r for r in rows if not r["pandemic"]]
    origins = sorted({r["t"] for r in rows})
    by_t = {}
    for r in rows:
        by_t.setdefault(r["t"], []).append(r)
    rng, stats = random.Random(seed), []
    for _ in range(reps):
        pick = []
        while len(pick) < len(origins):
            i = rng.randrange(0, len(origins) - block + 1)
            pick += origins[i:i + block]
        sel = [r for t in pick[:len(origins)] for r in by_t[t]]
        ma = statistics.fmean(abs(r[a]) for r in sel)
        mb = statistics.fmean(abs(r[b]) for r in sel)
        stats.append(mb / ma - 1)
    stats.sort()
    return {"lo": round(stats[int(0.025 * reps)], 4), "hi": round(stats[int(0.975 * reps)], 4), "reps": reps, "block": block}


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(color=GRID, linewidth=0.6)


if __name__ == "__main__":
    out = sys.argv[1]
    res = json.load(open(os.path.join(out, "backtest_v1.json"), encoding="utf-8"))
    with gzip.open(os.path.join(out, "backtest_v1_errors.json.gz"), "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    m = res["chosen"]
    recent = {}
    for c in sorted({r["c"] for r in rows}):             # mean miss (actual - projection) 4 quarters ahead, targets 2023-Q1+
        e = [r[m] for r in rows if r["c"] == c and r["h"] == 4 and r["target"] >= "2023-Q1"]
        recent[c] = {"n": len(e), "mean_error": round(statistics.fmean(e), 3) if e else None}   # 3 dp: no double rounding
    cov, per = coverage(rows, m, by_country=True)
    tested = cov.pop("_tested")
    bias = {}
    for c in sorted({r["c"] for r in rows}):              # the chosen rule's misses 4 quarters ahead, all origins, pandemic out
        e = sorted(r[m] for r in rows if r["c"] == c and r["h"] == 4 and not r["pandemic"])
        bias[c] = {"n": len(e), "n_over": sum(x < 0 for x in e), "median": round(statistics.median(e), 3),
                   "mean": round(statistics.fmean(e), 3)}
    by_c = res["by_country_ex_pandemic"]
    t_better = sorted(c for c in by_c if statistics.fmean(by_c[c]["T"][str(h)]["mae"] for h in (1, 2, 3, 4))
                      < statistics.fmean(by_c[c][m][str(h)]["mae"] for h in (1, 2, 3, 4)))
    mean_all = {k: statistics.fmean(res["pooled_all"][k][str(h)]["mae"] for h in (1, 2, 3, 4)) for k in ("N", "T", "A")}
    val = {"split": SPLIT, "method": m, "coverage": cov, "coverage_tested": tested,
           "coverage_by_country_h4": per, "recent_bias_h4_since_2023": recent, "bias_h4": bias,
           "choice": {"t_vs_a_bootstrap": block_bootstrap(rows, m, "T"), "t_better_in": t_better,
                      "pick_if_pandemic_in": min(mean_all, key=mean_all.get),
                      "margin_if_pandemic_in": round(mean_all[m] / mean_all["T"] - 1, 4)}}
    # per economy, four quarters ahead: MAE(naive)/MAE(rule) - 1 with a block-bootstrap 95% interval; lo > 0 means
    # the rule's edge over "last value holds" clears the noise there (the "18 of 20" is a point count)
    val["skill_h4_ci"] = {c: block_bootstrap([r for r in rows if r["c"] == c and r["h"] == 4], m, "N")
                          for c in sorted({r["c"] for r in rows})}
    json.dump(val, open(os.path.join(out, "validation_v1.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
    print(json.dumps(val["coverage"], indent=0))

    fig, axes = plt.subplots(3, 1, figsize=(9, 11.5), facecolor=SURFACE, gridspec_kw={"height_ratios": [1, 1.1, 1.5]})
    # 1. error by horizon
    ax = axes[0]
    style(ax)
    names = {"N": "naive (last YoY holds)", "T": "trend (median q/q)", "A": "AR(1) toward trend (chosen)"}
    for i, k in enumerate(("N", "T", "A")):
        ys = [res["pooled_ex_pandemic"][k][str(h)]["mae"] for h in (1, 2, 3, 4)]
        ax.plot([1, 2, 3, 4], ys, marker="o", markersize=6, linewidth=2, color=SLOTS[i], label=names[k])
        ax.annotate(f"{ys[-1]:.2f}", (4, ys[-1]), xytext=(6, {"N": 0, "T": 5, "A": -5}[k]), textcoords="offset points",
                    color=INK, fontsize=8, va="center")
    ax.set_xticks([1, 2, 3, 4], ["1 quarter", "2 quarters", "3 quarters", "4 quarters ahead"])
    ax.set_ylabel("mean absolute error, pp", color=MUTED, fontsize=8)
    ax.set_title(f"Forecast error by horizon, 20 economies, origins 2006-2025 (n = {res['pooled_ex_pandemic']['A']['1']['n']} "
                 "per horizon, pandemic quarters excluded)", fontsize=9, loc="left", color=INK)
    ax.legend(facecolor=SURFACE, edgecolor=GRID, labelcolor=INK, fontsize=8, loc="upper left")
    # 2. skill by country at h = 4
    ax = axes[1]
    style(ax)
    bc = res["by_country_ex_pandemic"]
    sk = sorted(((1 - bc[c][m]["4"]["mae"] / bc[c]["N"]["4"]["mae"], c) for c in bc), reverse=True)
    ax.bar(range(len(sk)), [100 * s for s, _ in sk], color=[SLOTS[0] if s >= 0 else SLOTS[1] for s, _ in sk], width=0.7)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(range(len(sk)), [c for _, c in sk], fontsize=7)
    ax.set_ylabel("% less error than naive", color=MUTED, fontsize=8)
    ax.set_title("4 quarters ahead: the chosen rule's error cut against naive, by economy (orange = naive did better)",
                 fontsize=9, loc="left", color=INK)
    # 3. the record for three economies: actual vs the forecast made a year earlier
    ax = axes[2]
    style(ax)
    for i, c in enumerate(("USA", "CHN", "DEU")):
        rc = sorted((r for r in rows if r["c"] == c and r["h"] == 4), key=lambda r: r["target"])
        xs = [int(r["target"][:4]) + (int(r["target"][-1]) - 0.5) / 4 for r in rc]
        ax.plot(xs, [r["actual"] for r in rc], color=SLOTS[i], linewidth=2, label=f"{c} actual")
        ax.plot(xs, [r["actual"] - r[m] for r in rc], color=SLOTS[i], linewidth=1.4, linestyle="--",
                label=f"{c} forecast made 4 quarters earlier")
    ax.axvspan(2020.0, 2022.0, color=GRID, alpha=0.6, linewidth=0)
    ax.set_xticks(range(2008, 2027, 2), [str(y) for y in range(2008, 2027, 2)])   # whole years, not 2007.5
    ax.text(2020.1, ax.get_ylim()[1] * 0.9, "pandemic\n(excluded from scores)", color=MUTED, fontsize=7)
    ax.set_ylabel("real GDP, % on a year earlier", color=MUTED, fontsize=8)
    ax.set_title("What the rule said a year ahead vs what happened (China: its 10-year trend lags the slowdown)",
                 fontsize=9, loc="left", color=INK)
    ax.legend(facecolor=SURFACE, edgecolor=GRID, labelcolor=INK, fontsize=7, ncol=3, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "gdp_forecast_study_v1.png"), dpi=160, facecolor=SURFACE)
    print("chart:", os.path.join(out, "gdp_forecast_study_v1.png"))
