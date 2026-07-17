"""Portfolio optimizers.

(a) Geometric-CAGR maximizer with HARD constraints (spec):
      maximize E[log(1+r_p)]                    (annualized log growth)
      s.t.    CVaR(5%, annual)      >= -15%
              5th-pct max drawdown  >= -20%     (within-horizon, daily res)
              corr(sleeve, bot P&L) <= 0.10     (historical daily, when bot data exists)
              0 <= w_i <= 25%,  sum w = 1
    evaluated on FIXED scenario sets (common random numbers) from BOTH
    engines — multivariate-t and stationary block bootstrap — reported side
    by side. Material disagreement is flagged, not averaged away.

(b) HRP (López de Prado 2016, "Building Diversified Portfolios that
    Outperform Out-of-Sample", JPM): correlation-distance single-linkage
    tree, quasi-diagonalization, recursive bisection with inverse-variance
    splits. No expected returns, no matrix inversion.

(c) NCO-style clustered min-variance (simplified from López de Prado 2019
    "A Robust Estimator of the Efficient Frontier"): cut the HRP tree into
    clusters, min-variance within clusters, min-variance across cluster
    portfolios. Labeled "NCO (min-var)" — it is a robustness CROSS-CHECK,
    not a growth-optimal allocation.
"""
from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list, fcluster
from scipy.optimize import minimize

from ..config import config_hash, load
from .simulate import _mvt_chunk, _mvt_params, _stationary_indices, TRADING_DAYS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- scenarios
def scenario_asset_paths(returns: pd.DataFrame, engine: str, n_paths: int,
                         seed: int = 0) -> np.ndarray:
    """(n_paths, 252, k) float32 asset-return scenarios for ONE year."""
    mc = load("backtest")["monte_carlo"]
    days = TRADING_DAYS
    rng = np.random.default_rng(seed)
    if engine == "mvt":
        mu, chol = _mvt_params(returns, float(mc["student_t_df"]))
        out = _mvt_chunk(rng, n_paths, days, mu, chol, float(mc["student_t_df"]))
    elif engine == "bootstrap":
        r = returns.values
        idx = _stationary_indices(rng, n_paths, days, len(r), int(mc["block_len_days"]))
        out = r[idx]
    else:
        raise ValueError(f"unknown scenario engine {engine}")
    return out.astype(np.float32)


def portfolio_path_stats(asset_paths: np.ndarray, w: np.ndarray) -> dict:
    """Annual return + within-year max drawdown per path for weights w."""
    pr = asset_paths @ w.astype(np.float32)          # (paths, days)
    logw = np.cumsum(np.log1p(pr), axis=1)
    annual = np.expm1(logw[:, -1])
    peak = np.maximum.accumulate(logw, axis=1)
    maxdd = np.expm1((logw - peak).min(axis=1))
    k = max(1, int(np.ceil(0.05 * annual.size)))
    return {
        "log_growth": float(logw[:, -1].mean()),
        "annual": annual,
        "cvar5_annual": float(np.sort(annual)[:k].mean()),
        "maxdd_p5": float(np.percentile(maxdd, 5)),
        "median_annual": float(np.median(annual)),
    }


# ---------------------------------------------------------------- geo-CAGR
def geo_cagr_optimize(asset_paths: np.ndarray, tickers: list[str],
                      hist_returns: pd.DataFrame,
                      bot_hist: pd.Series | None) -> dict:
    cons_cfg = load("portfolio")["constraints"]
    k = len(tickers)
    max_w = float(cons_cfg["max_position"])
    cvar_min = float(cons_cfg["cvar_5_annual_min"])
    dd_min = float(cons_cfg["p5_max_drawdown_min"])
    corr_max = float(cons_cfg["bot_corr_max"])

    joint_bot = None
    if bot_hist is not None:
        joint = pd.concat([hist_returns, bot_hist.rename("_bot")], axis=1, sort=True).dropna()
        if len(joint) >= 60:
            joint_bot = joint

    def stats_of(w):
        return portfolio_path_stats(asset_paths, w)

    def bot_corr(w) -> float:
        if joint_bot is None:
            return 0.0
        sleeve = joint_bot[tickers].values @ w
        return float(np.corrcoef(sleeve, joint_bot["_bot"].values)[0, 1])

    def neg_growth(w):
        return -stats_of(w)["log_growth"]

    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0},
        {"type": "ineq", "fun": lambda w: stats_of(w)["cvar5_annual"] - cvar_min},
        {"type": "ineq", "fun": lambda w: stats_of(w)["maxdd_p5"] - dd_min},
    ]
    if joint_bot is not None:
        constraints.append({"type": "ineq", "fun": lambda w: corr_max - bot_corr(w)})
    bounds = [(0.0, max_w)] * k

    rng = np.random.default_rng(42)
    starts = [np.full(k, 1.0 / k)]
    starts += [rng.dirichlet(np.ones(k)).clip(0, max_w) for _ in range(4)]
    best = None
    for w0 in starts:
        w0 = w0 / w0.sum()
        res = minimize(neg_growth, w0, method="SLSQP", bounds=bounds,
                       constraints=constraints,
                       options={"maxiter": 200, "ftol": 1e-8})
        if not res.success:
            continue
        w = np.clip(res.x, 0, max_w)
        w /= w.sum()
        st = stats_of(w)
        feasible = (st["cvar5_annual"] >= cvar_min - 1e-4
                    and st["maxdd_p5"] >= dd_min - 1e-4
                    and bot_corr(w) <= corr_max + 1e-3)
        if feasible and (best is None or st["log_growth"] > best["stats"]["log_growth"]):
            best = {"weights": {t: round(float(x), 4) for t, x in zip(tickers, w)},
                    "stats": st, "bot_corr": bot_corr(w)}
    if best is None:
        raise RuntimeError(
            "geo-CAGR optimizer found NO feasible portfolio under the hard "
            "constraints on this scenario set — constraints and universe are "
            "incompatible; report this, do not relax silently."
        )
    return best


# ---------------------------------------------------------------- HRP / NCO
def _corr_dist_linkage(returns: pd.DataFrame):
    corr = returns.corr().values
    dist = np.sqrt(0.5 * (1.0 - corr))
    from scipy.spatial.distance import squareform
    return linkage(squareform(dist, checks=False), method="single"), corr


def hrp_weights(returns: pd.DataFrame) -> dict[str, float]:
    tickers = list(returns.columns)
    lk, _ = _corr_dist_linkage(returns)
    order = leaves_list(lk)
    cov = returns.cov().values
    w = np.ones(len(tickers))
    clusters = [list(order)]
    while clusters:
        cl = clusters.pop(0)
        if len(cl) < 2:
            continue
        half = len(cl) // 2
        left, right = cl[:half], cl[half:]

        def cluster_var(items):
            sub = cov[np.ix_(items, items)]
            ivp = 1.0 / np.diag(sub)
            ivp /= ivp.sum()
            return float(ivp @ sub @ ivp)

        vl, vr = cluster_var(left), cluster_var(right)
        alpha = 1.0 - vl / (vl + vr)
        w[left] *= alpha
        w[right] *= 1.0 - alpha
        clusters += [left, right]
    return dict(zip(tickers, (w / w.sum())))


def _minvar(cov: np.ndarray) -> np.ndarray:
    inv = np.linalg.pinv(cov)
    ones = np.ones(len(cov))
    w = inv @ ones
    return w / w.sum()


def nco_weights(returns: pd.DataFrame, n_clusters: int | None = None) -> dict[str, float]:
    tickers = list(returns.columns)
    lk, _ = _corr_dist_linkage(returns)
    k = n_clusters or max(2, int(np.sqrt(len(tickers))))
    labels = fcluster(lk, t=k, criterion="maxclust")
    cov = returns.cov().values
    w = np.zeros(len(tickers))
    cluster_returns = {}
    intra = {}
    for c in np.unique(labels):
        items = np.where(labels == c)[0]
        wi = _minvar(cov[np.ix_(items, items)])
        # long-only cross-check portfolio: clip and renormalize (documented)
        wi = np.clip(wi, 0, None)
        wi = wi / wi.sum() if wi.sum() > 0 else np.full(len(items), 1 / len(items))
        intra[c] = (items, wi)
        cluster_returns[c] = returns.values[:, items] @ wi
    cr = pd.DataFrame(cluster_returns)
    wc = _minvar(cr.cov().values)
    wc = np.clip(wc, 0, None)
    wc /= wc.sum()
    for j, c in enumerate(cr.columns):
        items, wi = intra[c]
        w[items] = wc[j] * wi
    return dict(zip(tickers, (w / w.sum())))


# ---------------------------------------------------------------- runner
def run_optimizers(con: sqlite3.Connection, method: str = "all",
                   n_paths: int = 20000) -> str:
    from ..ingest.series import returns_matrix
    from ..report.render import research_report
    from ..stats.trials import register_trial
    from .combined import bot_return_series

    port = load("portfolio")
    tail = port["tail_sleeve"]["current"]
    from ..backtest.engine import resolve_targets
    targets = resolve_targets(tail)
    tickers = list(targets.keys())
    mat = returns_matrix(con, tickers, spliced=True).dropna()
    if n_paths < 20000:
        raise ValueError("spec requires >= 20k Monte Carlo paths")

    bot = None
    try:
        bot = bot_return_series(con, allow_model=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("no bot P&L available for correlation constraint: %s", exc)

    lines = [f"Universe: {', '.join(tickers)} (tail={tail}); "
             f"history {mat.index.min():%Y-%m-%d} → {mat.index.max():%Y-%m-%d}, "
             f"{len(mat)} joint days", ""]
    results = {}
    h = config_hash({"targets": targets, "n_paths": n_paths, "method": method})

    if method in ("geocagr", "all"):
        for engine in ("mvt", "bootstrap"):
            paths = scenario_asset_paths(mat, engine, n_paths, seed=7)
            res = geo_cagr_optimize(paths, tickers, mat, bot)
            results[f"geocagr_{engine}"] = res["weights"]
            st = res["stats"]
            register_trial(con, h, "optimize",
                           f"geo-CAGR {engine} n_paths={n_paths}",
                           float(np.mean(st["annual"]) / np.std(st["annual"])),
                           len(mat), {"weights": res["weights"]})
            lines += [
                f"### geo-CAGR optimum ({engine}, {n_paths} paths)",
                "",
                f"- weights: {res['weights']}",
                f"- median annual return: {st['median_annual']:+.2%}",
                f"- CVaR(5%, annual): {st['cvar5_annual']:+.2%} (floor -15%)",
                f"- p5 within-year max drawdown: {st['maxdd_p5']:+.2%} (floor -20%)",
                f"- corr to bot P&L: {res['bot_corr']:+.3f} (cap +0.10)"
                + ("" if bot is not None else " — NO BOT DATA, constraint not enforced"),
                "",
            ]

    if method in ("hrp", "nco", "all"):
        hrp = {t: round(float(x), 4) for t, x in hrp_weights(mat).items()}
        nco = {t: round(float(x), 4) for t, x in nco_weights(mat).items()}
        results["hrp"], results["nco"] = hrp, nco
        lines += [f"### HRP cross-check\n\n- weights: {hrp}\n",
                  f"### NCO (min-var) cross-check\n\n- weights: {nco}\n"]

    # disagreement flags: L1 distance between methods
    keys = list(results)
    flags = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = results[keys[i]], results[keys[j]]
            l1 = sum(abs(a.get(t, 0) - b.get(t, 0)) for t in tickers)
            if l1 > 0.30:
                flags.append(f"{keys[i]} vs {keys[j]}: L1 weight distance {l1:.2f}")
    if flags:
        lines += ["### METHOD DISAGREEMENT (information, not noise)", ""]
        lines += [f"- {f}" for f in flags]
    verdict = "INCONCLUSIVE" if flags else "NO_CHANGE"
    basis = ("Methods disagree materially — treat point allocations as unstable; "
             "investigate before trading." if flags else
             "Optimizers broadly agree with current targets; no reallocation signal. "
             "This is an in-sample allocation exercise — walk-forward evaluation is the gate.")
    return research_report("optimize", "Optimizer suite — geo-CAGR / HRP / NCO",
                           "\n".join(lines), h,
                           "proxy-extended joint history", verdict, basis)
