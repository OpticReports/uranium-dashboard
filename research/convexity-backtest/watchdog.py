"""
Overfitting / error watchdog -- the "method that watches for false positives".

A longer backtest is only worth anything if the extra history is (a) computed
correctly and (b) not being mined for a result that won't survive out of sample.
This module is the automated skeptic. It never asserts a strategy is good; it
only tries to prove a promising number is FAKE, and reports what it could not
break. Its verdicts gate any "this is validated" claim in the report.

Checks, and the false positive each one targets:

  perf_stats ................ baseline metrics (with skew/kurtosis, since Sharpe
                             lies about fat-tailed / convex payoffs).
  probabilistic_sharpe ...... is Sharpe > 0 even statistically, given the sample
                             length and non-normality? (Bailey & Lopez de Prado)
  deflated_sharpe ........... corrects Sharpe for the NUMBER OF TRIALS. Testing
                             many variants and keeping the best manufactures
                             Sharpe from noise; DSR subtracts that back out.
  block_bootstrap_ci ........ confidence interval on CAGR/Sharpe by resampling
                             blocks of returns -> is the edge distinguishable
                             from luck?
  leave_one_year_out ........ recompute dropping each calendar year -> is the
                             whole result carried by ONE lucky regime (e.g. only
                             Mar-2020)?
  walk_forward_degradation .. in-sample vs out-of-sample Sharpe across rolling
                             splits -> how much of the edge evaporates OOS.
  lookahead_probe ........... structural test that a strategy function cannot see
                             the future: perturb data AFTER date t, assert the
                             position AT t is unchanged.
  assumption_sensitivity .... re-run across a grid of soft inputs (financing,
                             fees, roll drag) -> does the conclusion depend on a
                             number we guessed?
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable
import numpy as np
import pandas as pd
from scipy import stats

TD = 252


# --------------------------------------------------------------------------- #
# Baseline performance
# --------------------------------------------------------------------------- #
def perf_stats(daily: pd.Series) -> dict:
    d = daily.dropna()
    n = len(d)
    if n < 2:
        return {"n": n}
    ann_ret = (1 + d).prod() ** (TD / n) - 1
    ann_vol = d.std(ddof=1) * np.sqrt(TD)
    sharpe = (d.mean() / d.std(ddof=1)) * np.sqrt(TD) if d.std(ddof=1) > 0 else np.nan
    curve = (1 + d).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    downside = d[d < 0].std(ddof=1) * np.sqrt(TD)
    sortino = (d.mean() * TD) / downside if downside > 0 else np.nan
    return {
        "n": n,
        "years": round(n / TD, 2),
        "cagr": round(float(ann_ret), 4),
        "vol": round(float(ann_vol), 4),
        "sharpe": round(float(sharpe), 3),
        "sortino": round(float(sortino), 3),
        "max_drawdown": round(float(dd), 4),
        "skew": round(float(stats.skew(d)), 3),
        "excess_kurtosis": round(float(stats.kurtosis(d)), 3),
    }


# --------------------------------------------------------------------------- #
# Is the Sharpe even real?
# --------------------------------------------------------------------------- #
def probabilistic_sharpe(daily: pd.Series, sr_benchmark: float = 0.0) -> float:
    """P(true Sharpe > benchmark), correcting for sample length, skew, kurtosis."""
    d = daily.dropna()
    n = len(d)
    sr = (d.mean() / d.std(ddof=1)) * np.sqrt(TD)
    sr_daily = sr / np.sqrt(TD)
    bench_daily = sr_benchmark / np.sqrt(TD)
    g3 = stats.skew(d)
    g4 = stats.kurtosis(d, fisher=False)  # non-excess
    denom = np.sqrt(1 - g3 * sr_daily + (g4 - 1) / 4 * sr_daily**2)
    psr = stats.norm.cdf((sr_daily - bench_daily) * np.sqrt(n - 1) / denom)
    return round(float(psr), 4)


def deflated_sharpe(daily: pd.Series, n_trials: int) -> float:
    """
    Deflated Sharpe Ratio: PSR against a benchmark Sharpe inflated by how many
    independent strategy variants were tried. Answers "is this Sharpe still
    significant once we admit we went looking for it?"
    """
    d = daily.dropna()
    if n_trials < 1:
        n_trials = 1
    sr = (d.mean() / d.std(ddof=1)) * np.sqrt(TD)
    var_sr = d.std(ddof=1)  # placeholder; we estimate cross-trial sigma below
    # Expected max Sharpe under the null of `n_trials` zero-skill trials
    # (Bailey & Lopez de Prado 2014). Uses an estimate of dispersion of trial SRs;
    # with a single series we assume unit dispersion (sr units) -> conservative.
    emc = 0.5772156649
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / n_trials * np.e ** -1)
    sr0 = z1 * (1 - emc) + z2 * emc  # expected max of n_trials standard normals
    return probabilistic_sharpe(d, sr_benchmark=float(sr0))


# --------------------------------------------------------------------------- #
# Luck vs edge
# --------------------------------------------------------------------------- #
def block_bootstrap_ci(daily: pd.Series, block: int = 21, iters: int = 2000,
                       seed: int = 7) -> dict:
    """Stationary-ish block bootstrap CI for CAGR and Sharpe."""
    d = daily.dropna().values
    n = len(d)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    cagrs, sharpes = [], []
    for _ in range(iters):
        starts = rng.integers(0, n - block, size=n_blocks)
        sample = np.concatenate([d[s:s + block] for s in starts])[:n]
        m, s = sample.mean(), sample.std(ddof=1)
        cagrs.append((1 + sample).prod() ** (TD / n) - 1)
        sharpes.append((m / s) * np.sqrt(TD) if s > 0 else np.nan)
    q = lambda a, p: round(float(np.nanpercentile(a, p)), 4)
    return {
        "cagr_ci95": [q(cagrs, 2.5), q(cagrs, 97.5)],
        "sharpe_ci95": [q(sharpes, 2.5), q(sharpes, 97.5)],
        "sharpe_p_gt_0": round(float(np.mean(np.array(sharpes) > 0)), 4),
    }


def leave_one_year_out(daily: pd.Series) -> dict:
    """Recompute Sharpe dropping each calendar year; flag single-regime dependence."""
    d = daily.dropna()
    base = perf_stats(d)["sharpe"]
    per = {}
    for yr, grp in d.groupby(d.index.year):
        rest = d[d.index.year != yr]
        per[int(yr)] = round(perf_stats(rest)["sharpe"] - base, 3)  # delta if year removed
    worst_year = min(per, key=per.get)  # removing it drops Sharpe the most -> most load-bearing
    return {
        "base_sharpe": base,
        "delta_sharpe_if_year_removed": per,
        "most_load_bearing_year": worst_year,
        "max_single_year_dependence": per[worst_year],
    }


def walk_forward_degradation(daily: pd.Series, folds: int = 5) -> dict:
    """Compare Sharpe on first (in-sample) vs later (out-of-sample) contiguous folds."""
    d = daily.dropna()
    bounds = np.linspace(0, len(d), folds + 1).astype(int)
    chunks = [d.iloc[bounds[i]:bounds[i + 1]] for i in range(folds)]
    sr = [perf_stats(c)["sharpe"] for c in chunks if len(c) > TD // 4]
    if len(sr) < 2:
        return {"folds": len(sr)}
    is_sr, oos_sr = float(np.mean(sr[: len(sr) // 2 or 1])), float(np.mean(sr[len(sr) // 2:]))
    return {
        "per_fold_sharpe": [round(x, 3) for x in sr],
        "in_sample_mean_sharpe": round(is_sr, 3),
        "out_of_sample_mean_sharpe": round(oos_sr, 3),
        "degradation": round(is_sr - oos_sr, 3),
    }


# --------------------------------------------------------------------------- #
# Structural correctness
# --------------------------------------------------------------------------- #
def lookahead_probe(strategy_fn: Callable[[pd.DataFrame], pd.Series],
                    inputs: pd.DataFrame, test_dates: int = 30, seed: int = 3) -> dict:
    """
    Prove a strategy function is causal. For several dates t, corrupt ALL input
    rows strictly after t, re-run, and assert the position AT t did not change.
    A single change means the function peeks at the future -> instant red flag.
    """
    rng = np.random.default_rng(seed)
    pos_ref = strategy_fn(inputs)
    idx = inputs.index
    checkpoints = idx[max(20, len(idx) // 3):-2][:: max(1, (len(idx) // 3) // test_dates)]
    violations = 0
    for t in checkpoints[:test_dates]:
        corrupted = inputs.copy()
        future = corrupted.index > t
        corrupted.loc[future] = corrupted.loc[future] * (1 + rng.normal(0, 0.5, corrupted.loc[future].shape))
        pos_c = strategy_fn(corrupted)
        if not np.isclose(pos_ref.get(t, np.nan), pos_c.get(t, np.nan), equal_nan=True):
            violations += 1
    return {"checkpoints_tested": int(min(test_dates, len(checkpoints))),
            "lookahead_violations": violations,
            "causal": violations == 0}


def assumption_sensitivity(build_fn: Callable[[dict], pd.Series], grid: dict) -> dict:
    """
    Re-run a reconstruction across a grid of soft assumptions and report the
    spread of the headline metric. A conclusion that flips across plausible
    inputs is a modelling artefact, not a finding.
    """
    import itertools
    keys = list(grid)
    rows = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, combo))
        s = perf_stats(build_fn(params))
        rows.append({**params, "cagr": s.get("cagr"), "sharpe": s.get("sharpe"),
                     "max_drawdown": s.get("max_drawdown")})
    sharpes = [r["sharpe"] for r in rows if r["sharpe"] == r["sharpe"]]
    return {"runs": rows,
            "sharpe_range": [round(min(sharpes), 3), round(max(sharpes), 3)] if sharpes else None,
            "sharpe_spread": round(max(sharpes) - min(sharpes), 3) if sharpes else None}


@dataclass
class WatchdogReport:
    label: str
    stats: dict = field(default_factory=dict)
    probabilistic_sharpe: float = None
    deflated_sharpe: float = None
    bootstrap: dict = field(default_factory=dict)
    leave_one_year_out: dict = field(default_factory=dict)
    walk_forward: dict = field(default_factory=dict)
    lookahead: dict = field(default_factory=dict)
    sensitivity: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def evaluate(daily: pd.Series, label: str, n_trials: int = 1) -> WatchdogReport:
    """Run the full skeptic battery on a return series and raise flags."""
    rep = WatchdogReport(label=label)
    rep.stats = perf_stats(daily)
    rep.probabilistic_sharpe = probabilistic_sharpe(daily)
    rep.deflated_sharpe = deflated_sharpe(daily, n_trials=n_trials)
    rep.bootstrap = block_bootstrap_ci(daily)
    rep.leave_one_year_out = leave_one_year_out(daily)
    rep.walk_forward = walk_forward_degradation(daily)

    # Flagging heuristics -- these are the automatic "false positive" alarms.
    if rep.probabilistic_sharpe is not None and rep.probabilistic_sharpe < 0.95:
        rep.flags.append(f"PSR<0.95 ({rep.probabilistic_sharpe}): Sharpe not statistically > 0.")
    if rep.deflated_sharpe is not None and rep.deflated_sharpe < 0.95:
        rep.flags.append(f"DSR<0.95 ({rep.deflated_sharpe}): Sharpe may be a multiple-testing artefact.")
    if rep.bootstrap.get("sharpe_p_gt_0", 1) < 0.95:
        rep.flags.append("Bootstrap: >5% of resamples have Sharpe<=0 (edge not robust to luck).")
    wf = rep.walk_forward.get("degradation")
    if wf is not None and wf > 0.5:
        rep.flags.append(f"Walk-forward degradation {wf}: large in->out-of-sample Sharpe drop.")
    loyo = rep.leave_one_year_out.get("max_single_year_dependence")
    if loyo is not None and loyo < -0.4:
        rep.flags.append(
            f"Single-year dependence: removing {rep.leave_one_year_out.get('most_load_bearing_year')} "
            f"cuts Sharpe by {abs(loyo)} -> result may rest on one regime.")
    return rep
