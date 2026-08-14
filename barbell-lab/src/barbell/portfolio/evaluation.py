"""M5 capstone: the "beat the benchmark" walk-forward evaluation.

Question: do OPTIMIZED weights (geo-CAGR under the hard constraints, refit
each year on training data only) beat the CURRENT target weights out of
sample, after costs and multiple-testing correction?

Protocol (leak-free by construction):
  * expanding train window (config walk_forward), 12m test, 12m step;
  * at each step the optimizer sees ONLY the train window: scenarios are
    generated from train returns, constraints evaluated on those scenarios;
  * both books then run through the SAME threshold-band cost-paying
    simulator on the untouched test window;
  * OOS daily series are concatenated across test windows per arm.

Reported: per-window table, concatenated OOS stats per arm, paired
stationary-bootstrap CI on the daily OOS difference, DSR vs the cumulative
trial registry, CSCV PBO over the two arms' joint OOS matrix, and a verdict.

The optimizer arm registers ONE trial per refit window (each refit is a
selection event); the benchmark registers one.
"""
from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd

from ..config import config_hash, load
from ..backtest.engine import resolve_targets, simulate
from ..backtest.metrics import summary
from ..report.render import research_report, significance_section
from ..stats.dsr import moments, sharpe_ratio
from ..stats.pbo import cscv_pbo
from ..stats.trials import register_trial, significance_block
from .optimizers import geo_cagr_optimize, scenario_asset_paths
from .simulate import _stationary_indices

logger = logging.getLogger(__name__)


def _windows(index: pd.DatetimeIndex) -> list[tuple[slice, slice]]:
    wf = load("backtest")["walk_forward"]
    min_train = int(wf["min_train_years"] * 252)
    test_len = int(wf["test_months"] * 21)
    step = int(wf["step_months"] * 21)
    out = []
    start = min_train
    while start + test_len <= len(index):
        out.append((slice(0, start), slice(start, start + test_len)))
        start += step
    if not out:
        raise ValueError("not enough joint history for a single walk-forward window")
    return out


def walkforward_eval(con: sqlite3.Connection, tail: str = "TAIL",
                     n_paths: int = 20000, engine: str = "bootstrap") -> str:
    from ..ingest.series import returns_matrix
    from .combined import bot_return_series

    targets = resolve_targets(tail)
    tickers = list(targets.keys())
    mat = returns_matrix(con, tickers, spliced=True).dropna()
    h = config_hash({"eval": "walkforward", "tail": tail, "engine": engine,
                     "n_paths": n_paths, "targets": targets})

    bot = None
    try:
        bot = bot_return_series(con, allow_model=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("no real bot P&L — correlation constraint not enforced: %s", exc)

    oos_opt, oos_base, rows = [], [], []
    for i, (tr, te) in enumerate(_windows(mat.index)):
        train, test = mat.iloc[tr], mat.iloc[te]
        paths = scenario_asset_paths(train, engine, n_paths, seed=100 + i)
        try:
            res = geo_cagr_optimize(paths, tickers, train, bot)
            w_opt = res["weights"]
            note = ""
        except RuntimeError:
            # no feasible portfolio on this train set -> optimizer arm falls
            # back to benchmark weights, and says so (never silently)
            w_opt, note = dict(targets), "INFEASIBLE->benchmark"
        sim_o = simulate(test, w_opt, mode="threshold")
        sim_b = simulate(test, targets, mode="threshold")
        oos_opt.append(sim_o.returns)
        oos_base.append(sim_b.returns)
        register_trial(con, h, "walkforward",
                       f"WF window {i} refit ({engine}) {note}".strip(),
                       float(sim_o.returns.mean() / sim_o.returns.std(ddof=1)),
                       len(sim_o.returns), {"weights": w_opt})
        rows.append((f"{test.index[0]:%Y-%m}", f"{test.index[-1]:%Y-%m}",
                     summary(sim_o.returns)["cagr"], summary(sim_b.returns)["cagr"], note))

    ro = pd.concat(oos_opt)
    rb = pd.concat(oos_base)
    register_trial(con, h, "walkforward", "WF benchmark (current targets)",
                   float(rb.mean() / rb.std(ddof=1)), len(rb), {"weights": targets})
    so, sb = summary(ro), summary(rb)

    # paired significance on the OOS daily difference
    diff = (ro - rb).dropna().values
    rng = np.random.default_rng(23)
    idx = _stationary_indices(rng, 5000, len(diff), len(diff), 21)
    ann_means = diff[idx].mean(axis=1) * 252
    lo, hi = np.percentile(ann_means, [2.5, 97.5])
    point = float(diff.mean() * 252)

    pbo = cscv_pbo(pd.concat([ro.rename("opt"), rb.rename("base")], axis=1, sort=True)
                   .dropna().values, n_blocks=10)
    mom = moments(ro.values)
    sig = significance_block(con, sharpe_ratio(ro.values), len(ro),
                             mom["skew"], mom["kurt"])

    body = [
        f"Universe: {tickers} (tail={tail}); joint history "
        f"{mat.index.min():%Y-%m-%d} → {mat.index.max():%Y-%m-%d}; "
        f"optimizer refit yearly on expanding train windows, {engine} scenarios "
        f"x{n_paths}; both arms pay full costs in the same threshold-band simulator.",
        "",
        "| test window | optimized CAGR (OOS) | benchmark CAGR (OOS) | note |",
        "|---|---|---|---|",
        *[f"| {a} → {b} | {c:+.2%} | {d:+.2%} | {n} |" for a, b, c, d, n in rows],
        "",
        "### Concatenated out-of-sample",
        "",
        "| metric | optimized | benchmark (current targets) |",
        "|---|---|---|",
        f"| CAGR | {so['cagr']:+.2%} | {sb['cagr']:+.2%} |",
        f"| ann. vol | {so['ann_vol']:.2%} | {sb['ann_vol']:.2%} |",
        f"| Sharpe (ann.) | {so['sharpe_annual']:.2f} | {sb['sharpe_annual']:.2f} |",
        f"| max drawdown | {so['max_drawdown']:+.2%} | {sb['max_drawdown']:+.2%} |",
        f"| CVaR5 (overlapping annual) | {so['cvar5_annual_overlapping']:+.2%} "
        f"| {sb['cvar5_annual_overlapping']:+.2%} |",
        "",
        f"**OOS edge (optimized − benchmark): {point:+.2%}/yr**, "
        f"95% bootstrap CI [{lo:+.2%}, {hi:+.2%}]",
        "",
        significance_section(sig, pbo),
    ]

    if lo > 0:
        verdict = "IMPROVED"
        basis = (f"Optimized weights beat the current targets out of sample by "
                 f"{point:+.2%}/yr net of costs with a CI excluding zero, after "
                 f"{sig['trial_count']} cumulative trials (Holm p = {sig['p_holm']:.4f}).")
    elif hi < 0:
        verdict = "NO_CHANGE"
        basis = (f"Optimized weights LOSE to the current targets out of sample "
                 f"({point:+.2%}/yr, CI [{lo:+.2%}, {hi:+.2%}]). Keep the current mix — "
                 f"the in-sample optimizer edge does not survive contact with OOS data.")
    else:
        verdict = "NO_CHANGE" if abs(point) < 0.005 else "INCONCLUSIVE"
        basis = (f"OOS difference {point:+.2%}/yr with CI [{lo:+.2%}, {hi:+.2%}] spanning "
                 f"zero. No statistical basis to abandon the current targets; the "
                 f"benchmark stands.")
    if bot is None:
        basis += (" NOTE: bot-correlation constraint not enforced (no real bot P&L "
                  "imported yet).")
    return research_report("walkforward", "M5 — optimizer vs current targets, walk-forward OOS",
                           "\n".join(body), h, "proxy-extended joint history",
                           verdict, basis)
