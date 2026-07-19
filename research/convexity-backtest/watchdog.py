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
def _excess(daily: pd.Series, rf_annual) -> pd.Series:
    """Subtract the risk-free rate so Sharpe measures excess (not total) return.
    rf_annual may be a scalar (%/yr as decimal) or a Series of annualized %/yr."""
    d = daily.dropna()
    if rf_annual is None:
        return d
    if isinstance(rf_annual, pd.Series):
        rf_d = (rf_annual.reindex(d.index).ffill() / 100.0) / TD
    else:
        rf_d = float(rf_annual) / TD
    return (d - rf_d).dropna()


def perf_stats(daily: pd.Series, rf_annual=None) -> dict:
    """Performance stats. Sharpe/Sortino are computed on EXCESS returns when a
    risk-free series/scalar is supplied (rf as %/yr); total-return CAGR is kept."""
    d = daily.dropna()
    n = len(d)
    if n < 2:
        return {"n": n}
    ex = _excess(d, rf_annual)
    ann_ret = (1 + d).prod() ** (TD / n) - 1
    ann_vol = d.std(ddof=1) * np.sqrt(TD)
    sharpe = (ex.mean() / ex.std(ddof=1)) * np.sqrt(TD) if ex.std(ddof=1) > 0 else np.nan
    curve = (1 + d).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    downside = ex[ex < 0].std(ddof=1) * np.sqrt(TD)
    sortino = (ex.mean() * TD) / downside if downside > 0 else np.nan
    return {
        "n": n,
        "years": round(n / TD, 2),
        "cagr": round(float(ann_ret), 4),
        "vol": round(float(ann_vol), 4),
        "sharpe": round(float(sharpe), 3),  # excess-return Sharpe when rf given
        "sortino": round(float(sortino), 3),
        "max_drawdown": round(float(dd), 4),
        "skew": round(float(stats.skew(d)), 3),
        "excess_kurtosis": round(float(stats.kurtosis(d)), 3),
        "rf_adjusted": rf_annual is not None,
    }


def reconstruction_tracking(synth_ret: pd.Series, real_ret: pd.Series,
                            min_corr: float = 0.95, beta_tol: float = 0.15) -> dict:
    """
    REAL engine-correctness test (replaces the old tautological Sharpe check).
    Compare synthetic daily returns to the ACTUAL ETF's daily returns on their
    overlap: daily-return correlation, OLS beta (should be ~1), and annualized
    tracking error. Catches sign flips (corr<0), scale/leverage errors (beta off
    1), and gross mis-specification (high tracking error) that a Sharpe-ordering
    check cannot.
    """
    a, b = synth_ret.dropna().align(real_ret.dropna(), join="inner")
    if len(a) < TD:
        return {"overlap_days": len(a), "sufficient": False}
    corr = float(np.corrcoef(a, b)[0, 1])
    beta = float(np.cov(a, b, ddof=1)[0, 1] / np.var(b, ddof=1))
    te = float((a - b).std(ddof=1) * np.sqrt(TD))
    passed = (corr >= min_corr) and (abs(beta - 1.0) <= beta_tol)
    return {
        "overlap": [str(a.index.min().date()), str(a.index.max().date())],
        "overlap_days": len(a),
        "daily_return_corr": round(corr, 4),
        "beta_vs_real": round(beta, 4),
        "annualized_tracking_error": round(te, 4),
        "passed": bool(passed),
        "criteria": f"corr>={min_corr} and |beta-1|<={beta_tol}",
    }


# --------------------------------------------------------------------------- #
# Is the Sharpe even real?
# --------------------------------------------------------------------------- #
def _sharpe_se(d: pd.Series, sr_daily: float) -> float:
    """Std error of the (daily) Sharpe estimate, skew/kurtosis-adjusted (Lo 2002 /
    Bailey-LdP). This is the natural dispersion scale for the DSR benchmark."""
    n = len(d)
    g3 = stats.skew(d)
    g4 = stats.kurtosis(d, fisher=False)
    return float(np.sqrt((1 - g3 * sr_daily + (g4 - 1) / 4 * sr_daily**2) / (n - 1)))


def probabilistic_sharpe(daily: pd.Series, sr_benchmark: float = 0.0, rf_annual=None) -> float:
    """P(true Sharpe > benchmark), correcting for sample length, skew, kurtosis.
    Operates on EXCESS returns when rf is supplied so it answers 'Sharpe > rf'."""
    d = _excess(daily, rf_annual)
    n = len(d)
    sr_daily = (d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else 0.0
    bench_daily = sr_benchmark / np.sqrt(TD)
    se = _sharpe_se(d, sr_daily)
    if se == 0:
        return float("nan")
    psr = stats.norm.cdf((sr_daily - bench_daily) / se)
    return round(float(psr), 4)


def expected_max_sharpe_z(n_trials: int) -> float:
    """Expected maximum of n_trials i.i.d. standard normals (Bailey & Lopez de
    Prado 2014). Zero for a single trial -> no deflation when nothing was searched."""
    if n_trials <= 1:
        return 0.0
    emc = 0.5772156649015329
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float((1 - emc) * z1 + emc * z2)


def deflated_sharpe(daily: pd.Series, n_trials: int, sr_dispersion_annual: float = None,
                    rf_annual=None) -> float:
    """
    Deflated Sharpe Ratio: PSR against a benchmark Sharpe inflated by how many
    strategy variants were tried. Answers "is this Sharpe still significant once
    we admit we went looking for it across n_trials configurations?"

    FIX (was a no-op at n_trials=1): the benchmark is
        SR* = sr_dispersion_annual * E[max of n_trials N(0,1)]
    with E[max]=0 at n_trials<=1, so DSR reduces to PSR-vs-0 (no deflation) rather
    than the old norm.ppf(0)=-inf degeneracy that returned 1.0 for ANY series,
    losers included. `sr_dispersion_annual` is the spread of Sharpes across the
    trials; with a single evaluated series it defaults to that series' own
    annualized Sharpe standard error (a conservative dispersion proxy).
    """
    d = _excess(daily, rf_annual)
    n_trials = max(int(n_trials), 1)
    sr_daily = (d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else 0.0
    if sr_dispersion_annual is None:
        sr_dispersion_annual = _sharpe_se(d, sr_daily) * np.sqrt(TD)
    sr0 = expected_max_sharpe_z(n_trials) * sr_dispersion_annual  # annualized benchmark
    return probabilistic_sharpe(daily, sr_benchmark=float(sr0), rf_annual=rf_annual)


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
                    inputs: pd.DataFrame, test_dates: int = 40, seed: int = 3,
                    include_same_bar: bool = True) -> dict:
    """
    Prove a strategy function is causal: the position decided FOR bar t may use
    information only through t-1. For several dates t, corrupt input rows from t
    onward (t inclusive by default) and assert the position at t is unchanged.
    Any change means the function used bar t's own data or later -> look-ahead.

    Two fixes over the naive version:
      * `include_same_bar=True` corrupts row t itself, so a strategy that trades
        on TODAY's close (unimplementable live) is caught -- the old >t-only probe
        certified same-bar peeking as causal.
      * corruption is a LARGE deterministic level shift plus noise, so leaks that
        depend on the mean of many future points can't average back to ~no-change.
    """
    rng = np.random.default_rng(seed)
    pos_ref = strategy_fn(inputs)
    idx = inputs.index
    lo = max(220, len(idx) // 4)  # leave warm-up room for long look-backs
    span = idx[lo:-2]
    step = max(1, len(span) // test_dates)
    checkpoints = span[::step][:test_dates]
    violations = 0
    for t in checkpoints:
        corrupted = inputs.copy()
        mask = corrupted.index >= t if include_same_bar else corrupted.index > t
        # large deterministic shift (x3) + noise -> defeats mean-averaging leaks
        corrupted.loc[mask] = corrupted.loc[mask] * (3.0 + rng.normal(0, 0.5, corrupted.loc[mask].shape))
        pos_c = strategy_fn(corrupted)
        if not np.isclose(pos_ref.get(t, np.nan), pos_c.get(t, np.nan), equal_nan=True):
            violations += 1
    return {"checkpoints_tested": int(len(checkpoints)),
            "same_bar_included": include_same_bar,
            "lookahead_violations": int(violations),
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


def evaluate(daily: pd.Series, label: str, n_trials: int = 1, rf_annual=None,
             strategy_fn: Callable = None, strategy_inputs: pd.DataFrame = None) -> WatchdogReport:
    """Run the full skeptic battery on a return series and raise flags.

    n_trials: number of strategy configurations searched to arrive at this one
              (drives the deflated Sharpe). Pass the TRUE count when optimizing.
    rf_annual: risk-free (%/yr scalar or Series) -> excess-return Sharpe/PSR/DSR.
    strategy_fn/strategy_inputs: if given, also run the causality probe and flag
              look-ahead. Omit for a parameter-free series (e.g. buy & hold)."""
    rep = WatchdogReport(label=label)
    rep.stats = perf_stats(daily, rf_annual=rf_annual)
    rep.probabilistic_sharpe = probabilistic_sharpe(daily, rf_annual=rf_annual)
    rep.deflated_sharpe = deflated_sharpe(daily, n_trials=n_trials, rf_annual=rf_annual)
    rep.bootstrap = block_bootstrap_ci(daily)
    rep.leave_one_year_out = leave_one_year_out(daily)
    rep.walk_forward = walk_forward_degradation(daily)
    if strategy_fn is not None and strategy_inputs is not None:
        rep.lookahead = lookahead_probe(strategy_fn, strategy_inputs)

    # Flagging heuristics -- these are the automatic "false positive" alarms.
    if rep.probabilistic_sharpe is not None and rep.probabilistic_sharpe < 0.95:
        rep.flags.append(f"PSR<0.95 ({rep.probabilistic_sharpe}): Sharpe not statistically > rf.")
    if rep.deflated_sharpe is not None and rep.deflated_sharpe < 0.95:
        rep.flags.append(f"DSR<0.95 ({rep.deflated_sharpe}): Sharpe may be a multiple-testing artefact "
                         f"(n_trials={n_trials}).")
    if rep.bootstrap.get("sharpe_p_gt_0", 1) < 0.95:
        rep.flags.append("Bootstrap: >5% of resamples have Sharpe<=0 (edge not robust to luck).")
    wf = rep.walk_forward.get("degradation")
    if wf is not None and wf > 0.5:
        rep.flags.append(f"Walk-forward degradation {wf}: large early->late Sharpe drop.")
    loyo = rep.leave_one_year_out.get("max_single_year_dependence")
    if loyo is not None and loyo < -0.4:
        rep.flags.append(
            f"Single-year dependence: removing {rep.leave_one_year_out.get('most_load_bearing_year')} "
            f"cuts Sharpe by {abs(loyo)} -> result may rest on one regime.")
    if rep.lookahead and not rep.lookahead.get("causal", True):
        rep.flags.append(
            f"LOOK-AHEAD: {rep.lookahead.get('lookahead_violations')} causality violations "
            f"-> strategy peeks at current/future data. Result is INVALID.")
    return rep
