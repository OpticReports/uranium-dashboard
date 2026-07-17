"""The two research questions the platform exists to answer.

Q1 — Is a 5% tail sleeve worth its carry, for the COMBINED book?
    Variants: TAIL / CAOS / BTAL / NONE / 50-50 splits, joined with the bot's
    return stream under three kill-switch assumptions (perfect / lag1 / fails).
    Head-to-head comparison runs on the COMMON date window (fairness), with
    each variant's full-window stats also shown. MC = stationary block
    bootstrap of the joint daily series (>=20k paths). Decision metric: the
    combined book's 5th-percentile 1-year outcome, weighed against the
    median-CAGR carry cost.

    Documented decision rule (config-free, stated here once):
      IMPROVED      best variant's Δp5(1y) > +0.5pp vs NONE AND the winner is
                    the same under BOTH kill-switch extremes (perfect, fails)
                    AND ΔCAGR_median >= -0.5 × Δp5 (insurance efficiency 2:1)
      NO_CHANGE     no variant beats NONE's p5 by > +0.5pp
      INCONCLUSIVE  anything else (winner unstable across scenarios, or
                    efficiency test failed)

Q2 — Realized rebalancing bonus on the actual sleeve history:
    threshold-band vs calendar vs buy-and-hold, net of costs. Significance
    via stationary bootstrap CI on the paired daily return differences.
"""
from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd

from ..config import config_hash, load
from ..backtest.engine import resolve_targets, simulate
from ..backtest.metrics import cagr, summary
from ..report.render import research_report, significance_section
from ..stats.pbo import cscv_pbo
from ..stats.trials import register_trial, significance_block
from .combined import bot_return_series, combined_returns
from .simulate import bootstrap_paths, path_metrics

logger = logging.getLogger(__name__)


def _variants() -> list[str]:
    t = load("portfolio")["tail_sleeve"]
    return list(t["candidates"]) + ["+".join(pair) for pair in t.get("splits", [])]


def _sleeve_daily(con, variant: str) -> pd.Series:
    from ..ingest.series import returns_matrix
    targets = resolve_targets(variant)
    mat = returns_matrix(con, list(targets.keys()), spliced=True).dropna()
    w = np.array([targets[t] for t in targets])
    return pd.Series(mat.values @ w, index=mat.index, name=f"sleeve_{variant}")


def answer_question1(con: sqlite3.Connection, kill_switch: str = "all",
                     allow_bot_model: bool = False, n_paths: int = 20000) -> str:
    mc = load("backtest")["monte_carlo"]
    scenarios = ["perfect", "lag1", "fails"] if kill_switch == "all" else [kill_switch]
    variants = _variants()
    h = config_hash({"q": 1, "variants": variants, "scenarios": scenarios,
                     "n_paths": n_paths, "bot_model": allow_bot_model})

    body: list[str] = []
    winners: dict[str, str] = {}
    delta_best: dict[str, dict] = {}
    common_matrix_for_pbo = None
    bot_provenance = "?"

    for ks in scenarios:
        bot = bot_return_series(con, allow_model=allow_bot_model, kill_switch=ks)
        bot_provenance = bot.attrs.get("provenance", "real")
        sleeves = {v: _sleeve_daily(con, v) for v in variants}
        # fairness: common window across ALL variants and the bot
        start = max(s.index.min() for s in sleeves.values())
        start = max(start, bot.index.min())
        rows, per_variant = [], {}
        pbo_cols = {}
        for v in variants:
            joint = combined_returns(sleeves[v].loc[start:], bot.loc[start:])
            pbo_cols[v] = joint["combined"]
            paths = bootstrap_paths(joint[["sleeve", "bot"]], np.array([0.8, 0.2]),
                                    n_paths, 1, int(mc["block_len_days"]),
                                    seed=int(mc["seed"]))
            pm = path_metrics(paths)
            paths10 = bootstrap_paths(joint[["sleeve", "bot"]], np.array([0.8, 0.2]),
                                      max(2000, n_paths // 10), 10,
                                      int(mc["block_len_days"]), seed=int(mc["seed"]) + 1)
            pm10 = path_metrics(paths10)
            hist = summary(joint["combined"])
            per_variant[v] = {"p5_1y": np.percentile(paths["annual_returns"], 5),
                              "med_1y": np.median(paths["annual_returns"]),
                              "cvar5": pm["cvar5_annual"], "dd_p5": pm["maxdd_p5"],
                              "tw10_p5": pm10["terminal_p5"], "tw10_p50": pm10["terminal_p50"],
                              "hist_cagr": hist["cagr"]}
            register_trial(con, h, "question1", f"Q1 {v} ks={ks}",
                           float(joint["combined"].mean() / joint["combined"].std(ddof=1)),
                           len(joint), per_variant[v] | {"note": "combined book"})
        none_row = per_variant["NONE"]
        for v in variants:
            d = per_variant[v]
            rows.append(
                f"| {v} | {d['p5_1y']:+.2%} | {d['p5_1y']-none_row['p5_1y']:+.2%} "
                f"| {d['med_1y']:+.2%} | {d['med_1y']-none_row['med_1y']:+.2%} "
                f"| {d['cvar5']:+.2%} | {d['dd_p5']:+.2%} "
                f"| {d['tw10_p5']:.2f}x / {d['tw10_p50']:.2f}x | {d['hist_cagr']:+.2%} |")
        best = max(variants, key=lambda v: per_variant[v]["p5_1y"])
        winners[ks] = best
        delta_best[ks] = {
            "dp5": per_variant[best]["p5_1y"] - none_row["p5_1y"],
            "dmed": per_variant[best]["med_1y"] - none_row["med_1y"],
        }
        if common_matrix_for_pbo is None:
            common_matrix_for_pbo = pd.DataFrame(pbo_cols).dropna()
        body += [
            f"## Kill-switch scenario: {ks}  (bot data: {bot_provenance})",
            "",
            f"*common window starts {start:%Y-%m-%d}; 1y bootstrap x{n_paths} paths; "
            f"10y x{max(2000, n_paths // 10)} paths*",
            "",
            "| variant | p5 1y | Δp5 vs NONE | median 1y | Δmed | CVaR5 | p5 maxDD "
            "| 10y wealth p5/p50 | hist CAGR (full common window) |",
            "|---|---|---|---|---|---|---|---|---|",
            *rows,
            "",
            f"**best p5(1y): {best}** (Δp5 {delta_best[ks]['dp5']:+.2%}, "
            f"carry cost Δmedian {delta_best[ks]['dmed']:+.2%})",
            "",
        ]

    # statistical honesty: PBO across variants + DSR for the selected winner
    pbo = cscv_pbo(common_matrix_for_pbo.values, n_blocks=10)
    ref_ks = scenarios[0]
    best_series = common_matrix_for_pbo[winners[ref_ks]]
    from ..stats.dsr import moments, sharpe_ratio
    mom = moments(best_series.values)
    sig = significance_block(con, sharpe_ratio(best_series.values),
                             len(best_series), mom["skew"], mom["kurt"])
    body += [significance_section(sig, pbo), ""]

    # ---- documented decision rule ----
    stable = len(set(winners.values())) == 1
    d = delta_best[ref_ks]
    if d["dp5"] <= 0.005:
        verdict = "NO_CHANGE"
        basis = (f"No tail variant lifts the combined book's 5th-percentile 1y outcome "
                 f"by more than +0.5pp over NONE (best: {winners[ref_ks]} at {d['dp5']:+.2%}). "
                 f"The 5% sleeve is better spent pro-rata across the core.")
    elif stable and d["dmed"] >= -0.5 * d["dp5"]:
        verdict = "IMPROVED"
        basis = (f"{winners[ref_ks]} lifts p5(1y) by {d['dp5']:+.2%} at median carry cost "
                 f"{d['dmed']:+.2%} (efficiency ≥ 2:1) and wins under every kill-switch "
                 f"scenario tested ({', '.join(scenarios)}).")
    else:
        verdict = "INCONCLUSIVE"
        basis = (f"Winner set {set(winners.values())} across scenarios {scenarios}; "
                 f"Δp5 {d['dp5']:+.2%}, Δmedian {d['dmed']:+.2%}. Either the winner is "
                 f"kill-switch-dependent or the carry cost fails the 2:1 efficiency rule. "
                 f"Do not reallocate on this evidence.")
    if bot_provenance.startswith("model"):
        basis += (" CAVEAT: bot stream is the PARAMETERIZED MODEL, not realized P&L — "
                  "re-run with real bot history before acting.")
    prov = f"proxy-extended sleeve + bot[{bot_provenance}]"
    return research_report("question1", "Q1 — tail sleeve vs carry, combined book",
                           "\n".join(body), h, prov, verdict, basis)


def answer_question2(con: sqlite3.Connection, n_boot: int = 5000) -> str:
    port = load("portfolio")
    tail = port["tail_sleeve"]["current"]
    targets = resolve_targets(tail)
    from ..ingest.series import returns_matrix
    mat = returns_matrix(con, list(targets.keys()), spliced=True).dropna()
    h = config_hash({"q": 2, "targets": targets})

    sims = {m: simulate(mat, targets, mode=m) for m in ("threshold", "calendar", "none")}
    cagrs = {m: cagr(s.returns) for m, s in sims.items()}
    for m, s in sims.items():
        register_trial(con, h, "question2", f"Q2 rebalance mode={m}",
                       float(s.returns.mean() / s.returns.std(ddof=1)),
                       len(s.returns), {"cagr": cagrs[m]})

    # paired significance: stationary bootstrap CI on mean daily difference
    rng = np.random.default_rng(11)
    diff = (sims["threshold"].returns - sims["none"].returns).dropna().values
    t = len(diff)
    block = 21
    means = []
    from .simulate import _stationary_indices
    idx = _stationary_indices(rng, n_boot, t, t, block)
    means = diff[idx].mean(axis=1) * 252
    lo, hi = np.percentile(means, [2.5, 97.5])
    point = float(diff.mean() * 252)

    pbo = cscv_pbo(pd.DataFrame({m: s.returns for m, s in sims.items()}).dropna().values,
                   n_blocks=10)
    from ..stats.dsr import moments, sharpe_ratio
    r_thr = sims["threshold"].returns
    mom = moments(r_thr.values)
    sig = significance_block(con, sharpe_ratio(r_thr.values), len(r_thr),
                             mom["skew"], mom["kurt"])

    body = [
        f"Universe: {targets} — joint history {mat.index.min():%Y-%m-%d} → "
        f"{mat.index.max():%Y-%m-%d} ({len(mat)} days), costs per config.",
        "",
        "| mode | CAGR (net) | rebalances | turnover ×/yr | cost drag |",
        "|---|---|---|---|---|",
        *[f"| {m} | {cagrs[m]:+.2%} | {s.n_rebalances} | {s.turnover:.2f} "
          f"| {s.cost_drag_annual:.3%} |" for m, s in sims.items()],
        "",
        f"**Realized rebalancing bonus (threshold − buy&hold): {cagrs['threshold']-cagrs['none']:+.2%}/yr**",
        f"(annualized mean daily difference {point:+.2%}, 95% bootstrap CI "
        f"[{lo:+.2%}, {hi:+.2%}], {n_boot} stationary-bootstrap resamples)",
        f"threshold − calendar: {cagrs['threshold']-cagrs['calendar']:+.2%}/yr",
        "",
        significance_section(sig, pbo),
    ]
    if lo > 0:
        verdict, basis = "IMPROVED", (
            f"Threshold-band rebalancing added {cagrs['threshold']-cagrs['none']:+.2%}/yr "
            f"net of costs on realized history and the bootstrap CI excludes zero. "
            f"Act 60 makes this bonus fully harvestable.")
    elif point <= 0:
        verdict, basis = "NO_CHANGE", (
            "No positive realized rebalancing bonus net of costs on this history.")
    else:
        verdict, basis = "INCONCLUSIVE", (
            f"Point estimate {point:+.2%}/yr is positive but the 95% CI "
            f"[{lo:+.2%}, {hi:+.2%}] includes zero — keep threshold bands (harmless, "
            f"theoretically grounded) but do not credit the bonus in projections.")
    return research_report("question2", "Q2 — realized rebalancing bonus",
                           "\n".join(body), h, "proxy-extended joint history",
                           verdict, basis)
