"""Forward simulation, correlation stress and historical scenario replay.

Simulated returns are per-period SIMPLE returns of the streams; the book is a
constant-mix (rebalanced every period) portfolio:
    r_p = w'r + c rf - b spread + const,   c = 1 - sum w,  b = max(-c, 0) by default.
Gearing enters through w and the financing terms; for a book, book_terms gears
the NON-cash streams and charges the spread only on new borrowing b beyond the
book's own cash, whose deployed part costs its own stated rate (the scorecard's
convention).  A per-period return <= -100% wipes the path out (wealth absorbs at 0).
All simulations are seeded (numpy default_rng(seed)), so a config reproduces
bit-for-bit.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .core import validate_covariance
from .errors import ValidationError
from .metrics import max_drawdown

SCENARIOS = {
    "gfc": ("2007-10-09", "2009-03-09", "2008 GFC: S&P 500 peak to trough"),
    "covid": ("2020-02-19", "2020-03-23", "2020 Covid crash: S&P 500 peak to trough"),
    "inflation_2022": ("2022-01-03", "2022-10-12", "2022 inflation shock: stocks and bonds fell together"),
}


def _sqrt_psd(cov: np.ndarray) -> np.ndarray:
    """Matrix L with L L' = cov (Cholesky, or symmetric eigen root if singular)."""
    try:
        return np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        lam, V = np.linalg.eigh(cov)
        return V * np.sqrt(np.clip(lam, 0, None))


@dataclass
class SimConfig:
    """Monte Carlo settings.  method: 'mvn' | 't' | 'bootstrap'."""
    years: float = 10.0
    periods_per_year: int = 12
    n_paths: int = 10_000
    seed: int = 0
    method: str = "mvn"
    df: float = 5.0                  # Student-t degrees of freedom (> 2)
    mean_block: float | None = None  # bootstrap mean block length (periods); default ~ q/4, >= 1

    @property
    def n_periods(self) -> int:
        """Horizon in periods = round(years * periods_per_year)."""
        return int(round(self.years * self.periods_per_year))

    def validate(self) -> None:
        """Raise ValidationError on non-positive horizon/paths, unknown method, df <= 2, mean_block < 1."""
        if self.years <= 0 or self.periods_per_year <= 0 or self.n_paths < 1:
            raise ValidationError("years, periods_per_year, n_paths must be positive")
        if self.method not in ("mvn", "t", "bootstrap"):
            raise ValidationError(f"unknown method {self.method!r}")
        if self.method == "t" and self.df <= 2:
            raise ValidationError("Student-t needs df > 2 (finite variance)")
        if self.mean_block is not None and self.mean_block < 1:
            raise ValidationError("mean_block must be >= 1")


def simulate_returns(mu, cov, n_periods: int, n_paths: int, *, periods_per_year: float, method: str = "mvn",
                     df: float = 5.0, seed: int = 0, jumps: list | None = None) -> np.ndarray:
    """Per-period stream returns, shape (n_paths, n_periods, N).

    mvn: r ~ N(mu/q, cov/q).
    t:   r = mu/q + sqrt(W) Z,  Z ~ N(0, cov/q (df-2)/df),  W = df / chi2_df,
         so Cov(r) = cov/q exactly and tails are fatter (multivariate Student-t).
    jumps: [{'base_index': i, 'prob': p_annual, 'loss': L}] adds the
         two-point ANNUAL default model of streams.DefaultModel: in each
         simulated year (block of q periods from the start) the stream
         defaults with probability p, at most once, losing L in one period
         drawn uniformly within the year.  The diffusive mean is raised by
         p L / q per period so E[r_i] stays mu_i/q, and the annual jump
         variance is exactly p (1-p) L^2 -- the term Moments.base_diffusive_cov
         removes, so total variance matches the declared vol.  Pass the
         DIFFUSIVE covariance with jumps.  Needs an integer q.
    (mu, cov annual.)"""
    mu = np.asarray(mu, float)
    cov = validate_covariance(cov)
    N = len(mu)
    if cov.shape[0] != N:
        raise ValidationError("mu and cov sizes differ")
    q = float(periods_per_year)
    rng = np.random.default_rng(seed)
    m = mu / q
    qi = int(round(q))
    if jumps:
        if abs(q - qi) > 1e-9 or qi < 1:
            raise ValidationError(f"default jumps need an integer periods_per_year (got {q})")
        m = m.copy()
        for j in jumps:
            if not 0.0 <= j["prob"] <= 1.0:
                raise ValidationError(f"default probability {j['prob']} not in [0, 1]")
            m[j["base_index"]] += j["prob"] * j["loss"] / q
    if method == "mvn":
        L = _sqrt_psd(cov / q)
        Z = rng.standard_normal((n_paths, n_periods, N))
        out = m + Z @ L.T
    elif method == "t":
        if df <= 2:
            raise ValidationError("df must be > 2")
        L = _sqrt_psd(cov / q * (df - 2.0) / df)
        Z = rng.standard_normal((n_paths, n_periods, N)) @ L.T
        Wm = df / rng.chisquare(df, size=(n_paths, n_periods, 1))
        out = m + np.sqrt(Wm) * Z
    else:
        raise ValidationError(f"unknown method {method!r} (bootstrap uses bootstrap_returns)")
    if jumps:
        ny = -(-n_periods // qi)  # simulated years, the last possibly partial
        rows = np.arange(n_paths)[:, None]
        for j in jumps:
            hit = rng.random((n_paths, ny)) < j["prob"]
            when = np.arange(ny)[None, :] * qi + rng.integers(0, qi, size=(n_paths, ny))
            ok = hit & (when < n_periods)
            out[np.broadcast_to(rows, ok.shape)[ok], when[ok], j["base_index"]] -= j["loss"]
    return out


def stationary_bootstrap_indices(T: int, n_periods: int, n_paths: int, mean_block: float,
                                 rng: np.random.Generator) -> np.ndarray:
    """Politis & Romano (1994) stationary bootstrap row indices, shape
    (n_paths, n_periods): a new block starts with probability 1/mean_block
    (geometric block lengths), at a uniform random row; within a block the
    index advances by one, wrapping circularly.  Each simulated row is a real
    historical row (cross-asset dependence kept) and the marginal of every
    index is uniform on 0..T-1."""
    if T < 2:
        raise ValidationError("need at least 2 historical rows to bootstrap")
    p = 1.0 / float(mean_block)
    new = rng.random((n_paths, n_periods)) < p
    new[:, 0] = True
    starts = rng.integers(0, T, size=(n_paths, n_periods))
    pos = np.arange(n_periods)[None, :].repeat(n_paths, axis=0)
    last_start = np.where(new, pos, 0)
    last_start = np.maximum.accumulate(last_start, axis=1)
    start_val = np.take_along_axis(starts, last_start, axis=1)
    return (start_val + (pos - last_start)) % T


def bootstrap_returns(history, n_periods: int, n_paths: int, *, mean_block: float, seed: int = 0) -> np.ndarray:
    """Stationary block bootstrap of a (T x N) history (no NaN):
    returns (n_paths, n_periods, N) built from historical rows."""
    H = history.to_numpy(float) if isinstance(history, (pd.DataFrame, pd.Series)) else np.asarray(history, float)
    if H.ndim == 1:
        H = H[:, None]
    if not np.all(np.isfinite(H)):
        raise ValidationError("bootstrap history has NaN/inf; use a common window")
    rng = np.random.default_rng(seed)
    ix = stationary_bootstrap_indices(H.shape[0], n_periods, n_paths, mean_block, rng)
    return H[ix]


def portfolio_returns(asset_returns: np.ndarray, weights, *, rf_period: float = 0.0, spread_period: float = 0.0,
                      const_period: float = 0.0, cash_weight: float | None = None,
                      spread_weight: float | None = None) -> np.ndarray:
    """Constant-mix book returns (n_paths, n_periods):
    r_p = w'r + c rf - b spread + const, c = 1 - sum w and b = max(-c, 0) by default.
    Pass ``cash_weight`` (and ``spread_weight``, the fraction of NAV that pays
    the financing spread) explicitly for look-through books, where w are leaf
    exposures (a composite's internal leverage is already financed inside
    ``const``) and only NEW book-level borrowing pays the spread: book_terms
    builds all four for a book geared L x."""
    w = np.asarray(weights, float)
    if asset_returns.shape[-1] != len(w):
        raise ValidationError("weights length differs from simulated streams")
    c = 1.0 - w.sum() if cash_weight is None else float(cash_weight)
    b = max(-c, 0.0) if spread_weight is None else float(spread_weight)
    if b < 0:
        raise ValidationError("spread_weight must be >= 0")
    return asset_returns @ w + c * rf_period - b * spread_period + const_period


def book_terms(moments, weights, *, leverage: float = 1.0, spread: float = 0.0, include_own_mu: bool = True) -> dict:
    """Leaf-level constant-mix terms of a book whose NON-CASH streams are geared
    L x (the convention of scorecard.gearing and core.new_borrowing):

      cash streams  = streams with no leaf exposure (Moments.A row = 0); they
                      fund the extra exposure first and are not scaled
      x             = L A'w_nc                      (leaf exposures)
      const         = L (c_nc + d_nc) + P - D(L) d  (cash premium still held)
      cash_weight   = 1 - L u,  u = sum(w_nc)        (earns rf)
      spread_weight = new_borrowing(L, 1 - u)        (pays the spread)
    with c_nc = w_nc'(rf_coef rf + const) (composite cash/financing/fees),
    d_nc = w_nc'(mu - A base_mu - rf_coef rf - const): a stream's OWN
    expected_return assumption over its look-through mean (e.g. a composite
    with a stated return), and (P, d) = core.cash_premium_terms: P =
    w_cash'(mu_cash - rf) is the cash's premium over rf as held and d the
    blended premium of the book's positive cash, forgone on the cash deployed
    D(L) = core.cash_deployed(L, 1 - u) so deployed cash costs its own rate
    (liabilities and net-liability books keep P at every L).  The simulated
    drift x'base_mu + const + cash_weight rf - spread_weight spread
    (``expected_return``, annual) equals the scorecard's book mean exactly,
    geared or not.  include_own_mu=False drops d_nc (bootstrap: history only)
    and lists the affected streams in ``own_mu_ignored``."""
    from .core import cash_deployed, cash_premium_terms, new_borrowing

    w = np.asarray(weights, float)
    if w.shape != (len(moments.names),):
        raise ValidationError("weights must align with moments.names")
    L = float(leverage)
    cash = np.all(moments.A == 0, axis=1)
    wn = np.where(cash, 0.0, w)
    x, c_nc = moments.look_through(wn)
    lt = moments.A @ moments.base_mu + moments.rf_coef * moments.rf + moments.const
    own = moments.mu - lt
    own_names = [n for n, d, k in zip(moments.names, own, ~cash) if k and abs(d) > 1e-12]
    d_nc = float(wn @ own) if include_own_mu else 0.0
    u = float(wn.sum())
    rf = float(moments.rf)
    prem, prem_rate = cash_premium_terms(w[cash], np.asarray(moments.mu, float)[cash], rf, 1.0 - u)
    cash_prem = prem - cash_deployed(L, 1.0 - u) * prem_rate
    const = L * (c_nc + d_nc) + cash_prem
    cw = 1.0 - L * u
    sw = new_borrowing(L, 1.0 - u)
    exp = float(L * x @ moments.base_mu) + const + cw * rf - sw * float(spread)
    return {"x": L * x, "const": float(const), "cash_weight": float(cw), "spread_weight": float(sw),
            "cash_share": 1.0 - u, "leverage": L, "expected_return": exp, "cash_premium": float(cash_prem),
            "own_mu_ignored": [] if include_own_mu else own_names, "own_mu_streams": own_names}


def horizon_stats(port: np.ndarray, periods_per_year: float, *, quantiles=(0.05, 0.25, 0.5, 0.75, 0.95),
                  cvar_alpha: float = 0.05) -> dict:
    """Distribution summary of simulated book returns (n_paths, n_periods).

    wealth W = prod(1 + r) (0 once a period return <= -100%), CAGR =
    W^(1/years) - 1, P(loss at horizon) = P(W < 1), per-year returns (complete
    years) -> P(losing year) and P(at least one losing year), max drawdown per
    path, CVaR_alpha = mean of the worst alpha share of path CAGRs (and of
    annual returns), plus quantiles of CAGR, terminal wealth and max DD."""
    P, H = port.shape
    q = float(periods_per_year)
    years = H / q
    gr = np.clip(1.0 + port, 0.0, None)
    wealth_path = np.cumprod(gr, axis=1)
    W = wealth_path[:, -1]
    cagr = np.where(W > 0, W ** (1.0 / years) - 1.0, -1.0)
    peak = np.maximum.accumulate(np.concatenate([np.ones((P, 1)), wealth_path], axis=1), axis=1)[:, 1:]
    mdd = np.min(np.where(peak > 0, wealth_path / peak - 1.0, -1.0), axis=1)
    out = {
        "years": years, "n_paths": P, "periods_per_year": q,
        "p_loss_horizon": float(np.mean(W < 1.0)),
        "p_wipeout": float(np.mean(W <= 0)),
        "mean_cagr": float(np.mean(cagr)),
        "cagr_quantiles": {str(k): float(np.quantile(cagr, k)) for k in quantiles},
        "wealth_quantiles": {str(k): float(np.quantile(W, k)) for k in quantiles},
        "max_dd_quantiles": {str(k): float(np.quantile(mdd, k)) for k in quantiles},
        "median_max_dd": float(np.median(mdd)),
    }
    k = max(1, int(math.floor(cvar_alpha * P)))
    out[f"cvar_{cvar_alpha:g}_cagr"] = float(np.mean(np.sort(cagr)[:k]))
    out[f"var_{cvar_alpha:g}_cagr"] = float(np.sort(cagr)[k - 1])
    ipy = int(round(q))
    ny = H // ipy if abs(q - ipy) < 1e-9 else 0
    if ny >= 1:
        yr = np.prod(gr[:, : ny * ipy].reshape(P, ny, ipy), axis=2) - 1.0
        flat = np.sort(yr.ravel())
        ka = max(1, int(math.floor(cvar_alpha * flat.size)))
        out["p_losing_year"] = float(np.mean(yr < 0))
        out["p_any_losing_year"] = float(np.mean((yr < 0).any(axis=1)))
        out[f"cvar_{cvar_alpha:g}_annual"] = float(np.mean(flat[:ka]))
        out["annual_return_quantiles"] = {str(k): float(np.quantile(yr, k)) for k in quantiles}
    out["_wealth_bands"] = {str(k): np.quantile(wealth_path, k, axis=0) for k in quantiles}
    return out


@dataclass
class ForwardResult:
    """run_forward output: config, horizon_stats dict, the rf/spread/const/weights used, notes."""
    config: dict
    stats: dict
    assumptions: dict
    notes: list = field(default_factory=list)


def run_forward(weights, config: SimConfig, *, mu=None, cov=None, history=None, rf: float = 0.0,
                spread: float = 0.0, const: float = 0.0, cash_weight: float | None = None,
                spread_weight: float | None = None, jumps: list | None = None, chunk: int = 2000) -> ForwardResult:
    """Simulate the constant-mix book ``weights`` for config.years.

    Parametric methods ('mvn', 't') need annual (mu, cov); 'bootstrap' needs
    ``history`` (per-period returns at config.periods_per_year frequency, no
    NaN).  rf / spread / const are ANNUAL (divided by q per period);
    ``cash_weight`` / ``spread_weight`` as in portfolio_returns.  Paths are
    generated in chunks (bounded memory) from one seeded generator stream per
    chunk (seed + chunk number), so results are reproducible."""
    config.validate()
    q = config.periods_per_year
    H = config.n_periods
    w = np.asarray(weights, float)
    ports = []
    done = 0
    ci = 0
    while done < config.n_paths:
        n = min(chunk, config.n_paths - done)
        seed = config.seed * 1_000_003 + ci
        if config.method == "bootstrap":
            if history is None:
                raise ValidationError("bootstrap needs history")
            mb = config.mean_block or max(1.0, q / 4.0)
            sim = bootstrap_returns(history, H, n, mean_block=mb, seed=seed)
        else:
            if mu is None or cov is None:
                raise ValidationError(f"{config.method} needs mu and cov")
            sim = simulate_returns(mu, cov, H, n, periods_per_year=q, method=config.method, df=config.df,
                                   seed=seed, jumps=jumps)
        ports.append(portfolio_returns(sim, w, rf_period=rf / q, spread_period=spread / q, const_period=const / q,
                                       cash_weight=cash_weight, spread_weight=spread_weight))
        done += n
        ci += 1
    port = np.concatenate(ports, axis=0)
    stats = horizon_stats(port, q)
    notes = ["constant-mix book rebalanced every period; no trading costs or taxes",
             "simulated distribution under the stated model: a scenario engine, not a forecast"]
    if config.method == "bootstrap":
        notes.append("bootstrap replays history: it cannot produce regimes absent from the sample")
    if jumps:
        notes.append("default jumps: at most one default per simulated year (annual two-point model), timed "
                     "uniformly within the year; non-absorbing (position not written off after a default)")
    return ForwardResult(asdict(config), stats, {"rf": rf, "spread": spread, "const": const,
                                                 "cash_weight": cash_weight, "spread_weight": spread_weight,
                                                 "weights": w.tolist()}, notes)


# --------------------------------------------------------------------------- #
# correlation stress
# --------------------------------------------------------------------------- #
def stress_correlation(cov, *, method: str = "floor", rho: float | None = None, crisis_corr=None,
                       alpha: float | None = None, vol_multiplier=1.0, return_info: bool = False):
    """Stressed covariance keeping (scaled) vols:
      'floor':   C_ij <- max(C_ij, rho)  -- a STRESS: no correlation is ever
                 lowered.  If the floored matrix is not PSD it is replaced by
                 the common-factor lift C_s = (1 - a) C + a 11' with the
                 smallest a putting every C_ij >= rho (PSD, unit diagonal,
                 still never lowers a correlation; reported in info).
      'blend':   C_s = (1 - alpha) C + alpha C_crisis   (convex blend of two
                 correlation matrices is a correlation matrix: PSD, unit diag)
      'uniform': WHAT-IF, not a stress: every off-diagonal correlation SET to
                 rho (PSD iff rho >= -1/(N-1)); it lowers any correlation
                 above rho.
    Apply it to the LEAF covariance and rebuild streams through the
    look-through map (stress_look_through), so identities such as a 3x fund
    vs its underlying (correlation 1) survive.  vol_multiplier (scalar or
    per-stream) scales vols.  Zero-vol streams stay uncorrelated.
    return_info=True returns (cov, {'method': used, 'lift': a})."""
    S = validate_covariance(cov)
    n = S.shape[0]
    sig = np.sqrt(np.diag(S))
    pos = sig > 0
    C = np.eye(n)
    C[np.ix_(pos, pos)] = S[np.ix_(pos, pos)] / np.outer(sig[pos], sig[pos])
    np.fill_diagonal(C, 1.0)
    info = {"method": method, "lift": None}
    m = int(pos.sum())
    if method in ("uniform", "floor"):
        if rho is None or not np.isfinite(rho) or not -1.0 <= rho <= 1.0:
            raise ValidationError(f"{method} stress needs rho in [-1, 1]")
    if method == "uniform":
        if m > 1 and rho < -1.0 / (m - 1):
            raise ValidationError(f"rho={rho} makes the matrix non-PSD for {m} streams")
        Cs = np.eye(n)
        sub = np.full((m, m), float(rho))
        np.fill_diagonal(sub, 1.0)
        Cs[np.ix_(pos, pos)] = sub
    elif method == "floor":
        Cp = C[np.ix_(pos, pos)]
        Cf = np.maximum(Cp, float(rho))
        np.fill_diagonal(Cf, 1.0)
        below = Cp < rho
        if m > 1 and below.any() and np.linalg.eigvalsh(Cf)[0] < -1e-12:
            a = float(np.max((rho - Cp[below]) / (1.0 - Cp[below])))
            Cf = (1.0 - a) * Cp + a * np.ones_like(Cp)
            np.fill_diagonal(Cf, 1.0)
            info = {"method": "common_factor_lift", "lift": a}
        Cs = np.eye(n)
        Cs[np.ix_(pos, pos)] = Cf
    elif method == "blend":
        if crisis_corr is None or alpha is None or not 0 <= alpha <= 1:
            raise ValidationError("blend stress needs crisis_corr and alpha in [0, 1]")
        Cc = validate_covariance(crisis_corr, name="crisis correlation")
        if Cc.shape != C.shape or np.max(np.abs(np.diag(Cc) - 1)) > 1e-9:
            raise ValidationError("crisis_corr must be an N x N unit-diagonal correlation matrix")
        Cs = (1 - alpha) * C + alpha * Cc
    else:
        raise ValidationError(f"unknown stress method {method!r}")
    vm = np.broadcast_to(np.asarray(vol_multiplier, float), (n,))
    s2 = sig * vm
    out = validate_covariance(Cs * np.outer(s2, s2), name="stressed covariance")
    return (out, info) if return_info else out


def stress_look_through(A, base_cov, *, return_info: bool = False, **kw):
    """Stream covariance under a correlation stress applied to the LEAF
    (base) covariance: A stress_correlation(base_cov) A'.  A stream that is a
    function of the same leaves as another (QQQ vs a 3x QQQ fund) keeps its
    exact relation; stressing at stream level would break it."""
    A = np.asarray(A, float)
    Sb, info = stress_correlation(base_cov, return_info=True, **kw)
    out = validate_covariance(A @ Sb @ A.T, name="stressed stream covariance")
    return (out, info) if return_info else out


# --------------------------------------------------------------------------- #
# historical scenario replay
# --------------------------------------------------------------------------- #
def replay_scenario(returns: pd.DataFrame, weights: dict, start, end, *, rebalance: str = "none",
                    rf_period: pd.Series | float = 0.0, missing: str = "raise", label: str = "") -> dict:
    """Apply today's weights to the historical daily returns in [start, end].

    rebalance 'none' = buy and hold from ``start`` (weights drift);
    'daily' = constant mix.  Cash = 1 - sum w earns rf_period (borrowing pays it).
    missing: 'raise' (default) if a weighted stream lacks data anywhere in the
    window; 'cash' sets its missing returns to 0% (not rf) and records it.
    Returns cumulative return, max drawdown, worst day, per-stream
    contribution (buy-and-hold) and the equity path."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    names = [k for k, v in weights.items() if v != 0]
    unknown = [k for k in names if k not in returns.columns]
    if unknown:
        raise ValidationError(f"scenario {label}: no return series for {unknown}")
    win = returns.loc[(returns.index > start) & (returns.index <= end), names].astype(float)
    if win.empty:
        raise ValidationError(f"scenario {label}: no data between {start.date()} and {end.date()}")
    gaps = {c: int(win[c].isna().sum()) for c in names if win[c].isna().any()}
    notes = []
    if gaps:
        if missing == "raise":
            raise ValidationError(f"scenario {label}: missing returns {gaps} (history too short; declare a proxy)")
        notes.append(f"missing returns set to 0% - stream NOT modelled in this window (understates loss if it fell): {gaps}")
        win = win.fillna(0.0)
    w0 = np.array([weights[k] for k in names], float)
    rf = pd.Series(rf_period, index=win.index, dtype=float) if np.isscalar(rf_period) else pd.Series(rf_period).reindex(win.index).fillna(0.0)
    X = win.to_numpy()
    E = [1.0]
    w = w0.copy()
    for k in range(len(win)):
        c = 1.0 - w.sum()
        rp = float(w @ X[k] + c * rf.iloc[k])
        E.append(E[-1] * (1 + rp))
        if rebalance == "none":
            w = w * (1 + X[k]) / (1 + rp)
        elif rebalance != "daily":
            raise ValidationError("rebalance must be 'none' or 'daily'")
    eq = pd.Series(E[1:], index=win.index)
    contrib = {}
    if rebalance == "none":
        growth = (1 + win).prod() - 1.0
        contrib = {k: float(w0[i] * growth[k]) for i, k in enumerate(names)}
    full = pd.concat([pd.Series([1.0], index=[start]), eq])
    return {"label": label, "start": str(start.date()), "end": str(end.date()), "days": len(win),
            "cum_return": float(eq.iloc[-1] - 1.0), "max_drawdown": max_drawdown(full),
            "worst_day": float((eq / eq.shift(1).fillna(1.0) - 1).min()), "contributions": contrib,
            "rebalance": rebalance, "notes": notes, "path": eq}
