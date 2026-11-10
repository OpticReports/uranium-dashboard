"""ROUND 8 volatility models: estimators, a hand-rolled GARCH(1,1), and the
look-ahead-free regime machinery Part A is registered to run on.

Contract: docs/VARIANTS_PREREGISTRATION_R8_VOL.md, committed (7d8458a) BEFORE
any round-8 code existed.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE. Every quantity here is a function
of the past only. The house convention (inherited from
`backtest_core_variants._trailing`) is SAME-CLOSE decide/execute:

    returns are indexed so that `rets[j]` is the return FROM dates[j] TO
    dates[j+1]. The information set at date index `i` is therefore
    `rets[:i]` — every return that has printed by dates[i]'s close — and a
    forecast made at date `i` is a forecast OF `rets[i]`.

Nothing in this file ever touches `rets[i:]` when producing an estimate for
date `i`. The regime thresholds are EXPANDING-window quantiles for the same
reason: the registration forbids full-sample quantiles as look-ahead, and
`test_vol_overlay_r8.py` pins that with a shuffle test on the future.

NO NEW DEPENDENCY. `arch` is not installed in this environment, so GARCH(1,1)
is fitted here by Gaussian MLE with a Nelder-Mead simplex written out below
(~70 lines). numpy is present but deliberately unused: the rest of the
campaign's engine is pure-stdlib and mixing the two invites silent dtype
differences between a test and a run.
"""
from __future__ import annotations

import bisect
import math
import statistics

TRADING_DAYS = 252

# --- estimators ---------------------------------------------------------------------


def trailing_vol(rets: list[float], i: int, window: int = 20) -> float | None:
    """Annualized realized vol from the `window` returns ending WITH the return
    INTO dates[i] — i.e. `rets[i-window:i]`. None during warm-up.

    This is `backtest_core_variants._trailing` + stdev, spelled out so round 8
    cannot drift from the C4 rule it is registered to re-run over 20 years.
    """
    if i - window < 0:
        return None
    w = rets[i - window:i]
    if len(w) < 2:
        return None
    return statistics.stdev(w) * math.sqrt(TRADING_DAYS)


def trailing_vol_series(rets: list[float], window: int = 20) -> list[float | None]:
    """`trailing_vol` at every date index 0..len(rets) (one per DATE, not per
    return), so it aligns with a date list of length len(rets)+1."""
    return [trailing_vol(rets, i, window) for i in range(len(rets) + 1)]


def ewma_var_series(rets: list[float], lam: float = 0.94,
                    init_window: int = 20) -> list[float | None]:
    """RiskMetrics EWMA conditional variance, one value per DATE index.

    `out[i]` is the variance forecast for `rets[i]` built from `rets[:i]`:
        h_{k+1} = lam * h_k + (1 - lam) * rets[k]^2
    seeded with the sample variance of the first `init_window` returns, so the
    first usable index is `init_window`.
    """
    n = len(rets)
    out: list[float | None] = [None] * (n + 1)
    if n < init_window:
        return out
    h = statistics.pvariance(rets[:init_window])
    out[init_window] = h
    for k in range(init_window, n):
        h = lam * h + (1 - lam) * rets[k] * rets[k]
        out[k + 1] = h
    return out


# --- GARCH(1,1), Gaussian MLE, hand-rolled -------------------------------------------

GARCH_MIN_VAR = 1e-12


def _garch_unpack(theta: list[float], var0: float) -> tuple[float, float, float, float]:
    """Unconstrained -> (mu, omega, alpha, beta) with alpha+beta<1, omega>0.

    alpha and beta are carved out of a persistence in (0,1) and a split in
    (0,1), which is the standard reparameterisation that keeps the simplex
    from wandering into an explosive corner where the likelihood is undefined.
    """
    mu = theta[0]
    omega = math.exp(max(-40.0, min(10.0, theta[1]))) * var0
    persist = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, theta[2]))))
    split = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, theta[3]))))
    persist = min(persist, 0.999_9)
    alpha = persist * split
    beta = persist - alpha
    return mu, omega, alpha, beta


def garch_negloglik(theta: list[float], rets: list[float], var0: float) -> float:
    mu, omega, alpha, beta = _garch_unpack(theta, var0)
    h = var0
    ll = 0.0
    for r in rets:
        if h < GARCH_MIN_VAR:
            h = GARCH_MIN_VAR
        e = r - mu
        ll += math.log(h) + e * e / h
        h = omega + alpha * e * e + beta * h
    if not math.isfinite(ll):
        return 1e18
    return 0.5 * ll


def nelder_mead(f, x0: list[float], *, step: float = 0.5, maxiter: int = 2000,
                tol: float = 1e-10) -> list[float]:
    """Textbook Nelder-Mead simplex. Deterministic: no randomness anywhere, so
    a GARCH fit is byte-reproducible from the returns alone."""
    n = len(x0)
    simplex = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step if p[i] == 0 else step * (1 + abs(p[i]))
        simplex.append(p)
    fv = [f(p) for p in simplex]
    for _ in range(maxiter):
        order = sorted(range(n + 1), key=lambda k: fv[k])
        simplex = [simplex[k] for k in order]
        fv = [fv[k] for k in order]
        if abs(fv[-1] - fv[0]) <= tol * (abs(fv[0]) + abs(fv[-1]) + 1e-30):
            break
        centroid = [sum(p[i] for p in simplex[:-1]) / n for i in range(n)]
        xr = [centroid[i] + 1.0 * (centroid[i] - simplex[-1][i]) for i in range(n)]
        fr = f(xr)
        if fr < fv[0]:
            xe = [centroid[i] + 2.0 * (centroid[i] - simplex[-1][i]) for i in range(n)]
            fe = f(xe)
            simplex[-1], fv[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < fv[-2]:
            simplex[-1], fv[-1] = xr, fr
        else:
            xc = [centroid[i] + 0.5 * (simplex[-1][i] - centroid[i]) for i in range(n)]
            fc = f(xc)
            if fc < fv[-1]:
                simplex[-1], fv[-1] = xc, fc
            else:
                for k in range(1, n + 1):
                    simplex[k] = [simplex[0][i] + 0.5 * (simplex[k][i] - simplex[0][i])
                                  for i in range(n)]
                    fv[k] = f(simplex[k])
    best = min(range(n + 1), key=lambda k: fv[k])
    return simplex[best]


def garch_fit(rets: list[float]) -> dict:
    """Fit GARCH(1,1) with Gaussian innovations by MLE on `rets`.

    Started from the conventional (omega, alpha, beta) = (0.05 * var, 0.08,
    0.90) corner and polished twice from the previous optimum, which is enough
    for this likelihood's very flat ridge in (alpha, beta).
    """
    var0 = statistics.pvariance(rets) if len(rets) > 2 else 1e-6
    var0 = max(var0, GARCH_MIN_VAR)

    def obj(theta: list[float]) -> float:
        return garch_negloglik(theta, rets, var0)

    # theta = [mu, log(omega/var0), logit(persistence), logit(alpha share)]
    x = [statistics.fmean(rets), math.log(0.05), math.log(0.98 / 0.02),
         math.log(0.08 / 0.90)]
    for step in (0.5, 0.15, 0.05):
        x = nelder_mead(obj, x, step=step)
    mu, omega, alpha, beta = _garch_unpack(x, var0)
    return {"mu": mu, "omega": omega, "alpha": alpha, "beta": beta,
            "persistence": alpha + beta, "nll": obj(x), "n": len(rets),
            "uncond_var": omega / (1 - alpha - beta) if alpha + beta < 1 else float("nan")}


def garch_var_path(rets: list[float], params: dict, *, upto: int | None = None,
                   var0: float | None = None) -> list[float | None]:
    """Conditional variance one value per DATE index: `out[i]` is the forecast
    for `rets[i]`, built ONLY from `rets[:i]` and the given parameters.

    Seeded at the unconditional variance implied by the parameters (falling
    back to the sample variance of the fit window), which is the standard
    recursion start and, unlike seeding from the whole sample, uses no future
    information.
    """
    n = len(rets) if upto is None else upto
    mu, omega, alpha, beta = params["mu"], params["omega"], params["alpha"], params["beta"]
    h0 = var0
    if h0 is None:
        h0 = params.get("uncond_var")
    if h0 is None or not math.isfinite(h0) or h0 <= 0:
        h0 = max(statistics.pvariance(rets[:max(2, min(len(rets), 60))]), GARCH_MIN_VAR)
    out: list[float | None] = [None] * (n + 1)
    h = h0
    out[0] = h
    for k in range(n):
        e = rets[k] - mu
        h = omega + alpha * e * e + beta * h
        h = max(h, GARCH_MIN_VAR)
        out[k + 1] = h
    return out


def garch_walk_forward(rets: list[float], dates: list[str], *,
                       init_days: int = 756, refit_month: str = "01") -> dict:
    """WALK-FORWARD GARCH(1,1): fit on an EXPANDING history, refit ANNUALLY.

    `init_days` returns (3 years) train the first model; from then on the
    parameters in force on date index `i` are those fitted on `rets[:cut]` for
    the most recent annual cut at or before `i`. The variance for `rets[i]` is
    then produced by running the recursion forward from that cut with the
    frozen parameters over `rets[:i]` — so the forecast for day i uses returns
    through day i-1 and parameters estimated strictly earlier. There is no
    point in the series at which a parameter has seen the return it prices.

    Returns {"var": [...one per date index...], "fits": [...], "start": idx}.
    """
    n = len(rets)
    out: list[float | None] = [None] * (n + 1)
    if n <= init_days + 5:
        return {"var": out, "fits": [], "start": None}

    cuts = [init_days]
    seen_year = dates[init_days][:4]
    for i in range(init_days + 1, n):
        if dates[i][:4] != seen_year and dates[i][5:7] == refit_month:
            cuts.append(i)
            seen_year = dates[i][:4]
    fits = []
    for c in cuts:
        p = garch_fit(rets[:c])
        p["fit_through"] = dates[c]
        p["fit_n"] = c
        fits.append(p)

    # Forward pass: at every index the recursion is driven by the parameters of
    # the newest fit whose cut is <= that index.
    h = None
    fi = -1
    for i in range(init_days, n + 1):
        while fi + 1 < len(cuts) and cuts[fi + 1] <= i:
            fi += 1
            p = fits[fi]
            # Re-seed the recursion at the new parameters' unconditional
            # variance and roll it forward over the history to date i.
            h = p.get("uncond_var")
            if h is None or not math.isfinite(h) or h <= 0:
                h = max(statistics.pvariance(rets[:cuts[fi]]), GARCH_MIN_VAR)
            for k in range(max(0, cuts[fi] - 500), i):
                e = rets[k] - p["mu"]
                h = max(p["omega"] + p["alpha"] * e * e + p["beta"] * h, GARCH_MIN_VAR)
        if h is None:
            continue
        out[i] = h
        if i < n:
            p = fits[fi]
            e = rets[i] - p["mu"]
            h = max(p["omega"] + p["alpha"] * e * e + p["beta"] * h, GARCH_MIN_VAR)
    return {"var": out, "fits": fits, "start": init_days}


# --- forecast scoring -----------------------------------------------------------------


def qlike(h: float, r2: float) -> float:
    """QLIKE loss, the standard robust variance-forecast loss: log h + r^2/h.
    Lower is better; it is minimised in expectation at the true conditional
    variance even though the proxy r^2 is noisy."""
    h = max(h, GARCH_MIN_VAR)
    return math.log(h) + r2 / h


def score_forecasts(var_hat: list[float | None], rets: list[float],
                    idx: list[int]) -> dict:
    """RMSE and QLIKE of a one-day-ahead VARIANCE forecast against the
    squared-return proxy, over the shared index set `idx`."""
    se, ql = [], []
    for i in idx:
        h = var_hat[i]
        if h is None:
            continue
        r2 = rets[i] * rets[i]
        se.append((h - r2) ** 2)
        ql.append(qlike(h, r2))
    if not se:
        return {"n": 0, "rmse": float("nan"), "qlike": float("nan")}
    return {"n": len(se), "rmse": math.sqrt(statistics.fmean(se)), "qlike": statistics.fmean(ql)}


def score_vs_forward_vol(var_hat: list[float | None], rets: list[float],
                         idx: list[int], window: int = 20) -> dict:
    """SECONDARY, descriptive: RMSE in ANNUALIZED VOL POINTS against the
    forward `window`-day realized vol. Less noisy than r^2 and easier to read,
    but it scores a horizon nobody forecast, so it never adjudicates."""
    se = []
    for i in idx:
        h = var_hat[i]
        if h is None or i + window > len(rets):
            continue
        fwd = statistics.stdev(rets[i:i + window]) * math.sqrt(TRADING_DAYS)
        se.append((math.sqrt(max(h, 0.0) * TRADING_DAYS) - fwd) ** 2)
    if not se:
        return {"n": 0, "rmse_vol_pts": float("nan")}
    return {"n": len(se), "rmse_vol_pts": math.sqrt(statistics.fmean(se))}


# --- regimes ---------------------------------------------------------------------------


def _quantile_sorted(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation quantile on an already-sorted list."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def expanding_regimes(vol: list[float | None], q_lo: float, q_hi: float, *,
                      min_history: int = 252) -> list[str | None]:
    """Regime labels from EXPANDING-window quantiles of `vol`.

    At index i the thresholds are the `q_lo`/`q_hi` quantiles of every vol
    observation available STRICTLY UP TO AND INCLUDING i. Nothing after i is
    consulted, which is the whole point: the registration forbids full-sample
    quantiles as look-ahead. `min_history` observations must exist before any
    day is labelled, so the first labels are not decided by a handful of
    points.

    Implemented with an insertion-sorted running list — O(n^2) worst case in
    principle, ~5,000 elements in practice, and exact rather than approximate.
    """
    out: list[str | None] = [None] * len(vol)
    hist: list[float] = []
    for i, v in enumerate(vol):
        if v is None or not math.isfinite(v):
            continue
        bisect.insort(hist, v)
        if len(hist) < min_history:
            continue
        lo = _quantile_sorted(hist, q_lo)
        hi = _quantile_sorted(hist, q_hi)
        out[i] = "low" if v <= lo else ("high" if v >= hi else "mid")
    return out


def fixed_regimes(vol: list[float | None], q_lo: float, q_hi: float, *,
                  train_days: int = 756) -> list[str | None]:
    """Thresholds estimated ONCE on the first `train_days` observations and
    then held FIXED — the registration's third sensitivity ("a fixed 20/80"),
    read as fixed *thresholds* rather than re-estimated ones. Still causal:
    the training block precedes every day it labels."""
    obs = [(i, v) for i, v in enumerate(vol) if v is not None and math.isfinite(v)]
    out: list[str | None] = [None] * len(vol)
    if len(obs) <= train_days:
        return out
    train = sorted(v for _i, v in obs[:train_days])
    lo, hi = _quantile_sorted(train, q_lo), _quantile_sorted(train, q_hi)
    for i, v in obs[train_days:]:
        out[i] = "low" if v <= lo else ("high" if v >= hi else "mid")
    return out


def full_sample_regimes(vol: list[float | None], q_lo: float, q_hi: float) -> list[str | None]:
    """LOOK-AHEAD ON PURPOSE — full-sample quantiles, reported only as the
    diagnostic that shows how much the forbidden version flatters the answer.
    Never used for any strategy weight."""
    vals = sorted(v for v in vol if v is not None and math.isfinite(v))
    if len(vals) < 2:
        return [None] * len(vol)
    lo, hi = _quantile_sorted(vals, q_lo), _quantile_sorted(vals, q_hi)
    return [None if v is None or not math.isfinite(v)
            else ("low" if v <= lo else ("high" if v >= hi else "mid")) for v in vol]


def wilson(k: int, n: int, z: float = 1.959_963_984_540_054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def persistence(labels: list[str | None], state: str, horizon: int) -> dict:
    """P(label[i+h] == state | label[i] == state), with a Wilson 95% interval.

    Both endpoints must be labelled; unlabelled warm-up days are excluded
    rather than imputed.
    """
    k = n = 0
    for i in range(len(labels) - horizon):
        if labels[i] != state:
            continue
        nxt = labels[i + horizon]
        if nxt is None:
            continue
        n += 1
        k += int(nxt == state)
    lo, hi = wilson(k, n)
    return {"state": state, "horizon": horizon, "k": k, "n": n,
            "p": (k / n if n else float("nan")), "ci_lo": lo, "ci_hi": hi}


def autocorr(x: list[float], lag: int) -> float:
    """Sample autocorrelation at `lag` (mean removed once, on the full series)."""
    n = len(x)
    if lag >= n or n < 3:
        return float("nan")
    m = statistics.fmean(x)
    num = sum((x[i] - m) * (x[i + lag] - m) for i in range(n - lag))
    den = sum((v - m) ** 2 for v in x)
    return num / den if den > 0 else float("nan")
