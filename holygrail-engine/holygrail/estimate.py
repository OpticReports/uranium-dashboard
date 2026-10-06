"""Estimation: calendars, frequency alignment, covariance estimators, PSD
repair, annualisation and stale-mark corrections.

All return inputs are SIMPLE per-period returns in a DataFrame (dates x
streams), NaN where a stream has no history yet.  Levels (prices / NAVs) are
DataFrames with NaN where a stream did not print.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .core import validate_covariance
from .errors import CovarianceError, ValidationError

#: NOMINAL periods per year by frequency code.  'D' is a placeholder: daily
#: callers must use infer_periods_per_year on the calendar actually used
#: (~252 for exchange days, ~365 for a crypto-only 7-day calendar).
FREQ_PPY = {"D": 252, "W": 52, "M": 12, "Q": 4, "A": 1}
_RULE = {"W": "W-FRI", "M": "ME", "Q": "QE", "A": "YE"}
#: a stream whose median gap between observations exceeds this many calendar
#: days is sampled too coarsely for the frequency (forward-filling it would
#: fabricate zero returns)
MAX_NATIVE_GAP_DAYS = {"D": 4.0, "W": 10.5, "M": 45.0, "Q": 135.0, "A": 548.0}


# --------------------------------------------------------------------------- #
# calendars and alignment
# --------------------------------------------------------------------------- #
def _check_levels(levels: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(levels, pd.DataFrame):
        raise ValidationError("levels must be a DataFrame (dates x streams)")
    if not isinstance(levels.index, pd.DatetimeIndex):
        raise ValidationError("levels index must be a DatetimeIndex")
    if levels.index.has_duplicates:
        raise ValidationError("levels index has duplicate dates")
    lv = levels.sort_index().astype(float)
    if np.isinf(lv.to_numpy()).any():
        raise ValidationError("levels contain inf")
    nonpos = (lv <= 0) & lv.notna()
    if nonpos.to_numpy().any():
        cols = [c for c in lv.columns if nonpos[c].any()]
        raise ValidationError(f"levels must be > 0; non-positive values in {cols}")
    return lv


def _active_mask(lv: pd.DataFrame) -> pd.DataFrame:
    """True from each column's first observation onward.  A stream never
    'ends': once started, a date it did not print is vetoed, so the common
    panel stops at the earliest last observation (unequal END dates truncate;
    unequal START dates are kept as leading NaN)."""
    idx = lv.index
    mask = {}
    for c in lv.columns:
        f = lv[c].first_valid_index()
        if f is None:
            raise ValidationError(f"stream {c!r} has no observations")
        mask[c] = idx >= f
    return pd.DataFrame(mask, index=idx)


def active_intersection_calendar(levels: pd.DataFrame) -> pd.DatetimeIndex:
    """Dates on which EVERY stream that has started printed.  Mixing a 7-day
    (crypto) and a 5-day (equity) calendar therefore keeps equity trading days
    only, and the crypto return over a weekend compounds into Monday's return;
    an equity holiday drops the date for all streams; trailing crypto weekend
    days after the last equity close are dropped (the panel ends at the
    earliest last observation).  Streams that have not started yet do not veto
    a date (unequal history lengths are kept, as leading NaN)."""
    lv = _check_levels(levels)
    act = _active_mask(lv)
    ok = (lv.notna() | ~act).all(axis=1) & act.any(axis=1)
    return lv.index[ok.to_numpy()]


def native_sampling_days(levels: pd.DataFrame) -> dict:
    """Median gap in calendar days between each stream's own observations
    (1 for exchange-daily data, 7 weekly, ~30 month-end marks).  NaN for a
    stream with fewer than two observations."""
    out = {}
    for c in levels.columns:
        d = pd.Series(levels[c].dropna().index).diff().dt.days.dropna()
        out[c] = float(d.median()) if len(d) else float("nan")
    return out


def check_native_sampling(levels: pd.DataFrame, freq: str, calendar="active_intersection") -> None:
    """Raise ValidationError naming every stream sampled more coarsely than
    ``freq`` (median native gap > MAX_NATIVE_GAP_DAYS[freq]; for an explicit
    daily calendar, > 1.5x its median spacing).  Aligning such a series either
    forward-fills it (stale zero returns: vol and correlation understated,
    N_eff inflated) or, on the daily intersection calendar, collapses every
    stream onto its sparse dates."""
    freq = freq.upper()
    limit = MAX_NATIVE_GAP_DAYS.get(freq)
    if limit is None:
        return
    if freq == "D" and isinstance(calendar, pd.DatetimeIndex) and len(calendar) > 2:
        limit = max(limit, 1.5 * float(pd.Series(calendar.sort_values()).diff().dt.days.median()))
    gaps = native_sampling_days(levels)
    bad = {c: g for c, g in gaps.items() if np.isfinite(g) and g > limit}
    if bad:
        worst = max(bad.values())
        fit = next((f for f in ("W", "M", "Q", "A") if MAX_NATIVE_GAP_DAYS[f] >= worst), "A")
        desc = ", ".join(f"{c} (~every {g:.0f} days)" for c, g in bad.items())
        raise ValidationError(
            f"{desc} sampled more coarsely than freq {freq!r}: aligning would fabricate stale zero returns "
            f"(understated vol and correlation, inflated N_eff) or collapse the daily calendar; use freq {fit!r} "
            f"(or coarser), de-smooth / re-mark the series, or pass stale='allow' knowingly")


def align_levels(levels: pd.DataFrame, freq: str = "D", calendar="active_intersection",
                 stale: str = "raise") -> pd.DataFrame:
    """Put levels on one calendar.

    freq 'D': ``calendar`` = 'active_intersection' (default, see
      active_intersection_calendar), 'union' (every date any stream printed,
      levels forward-filled inside each stream's active range: stale zero
      returns on non-trading days, biases correlations toward 0) or an explicit
      DatetimeIndex (levels taken as-of each date inside the active range).
    freq 'W'/'M'/'Q'/'A': last observed level in each period (W-FRI, month,
      quarter, year end), forward-filled inside the active range, so period
      returns compound every daily move exactly.
    Values before a stream's first observation stay NaN.
    stale: 'raise' (default) refuses a stream sampled more coarsely than
      ``freq`` (check_native_sampling); 'allow' aligns it anyway."""
    lv = _check_levels(levels)
    freq = freq.upper()
    if stale == "raise":
        check_native_sampling(lv, freq, calendar)
    elif stale != "allow":
        raise ValidationError(f"stale must be 'raise' or 'allow', got {stale!r}")
    if freq == "D":
        if isinstance(calendar, pd.DatetimeIndex):
            target = calendar.sort_values()
        elif calendar == "active_intersection":
            return lv.loc[active_intersection_calendar(lv)]
        elif calendar == "union":
            target = lv.index
        else:
            raise ValidationError(f"unknown calendar {calendar!r}")
        full = lv.reindex(lv.index.union(target)).sort_index().ffill()
        for c in lv.columns:
            first, last = lv[c].first_valid_index(), lv[c].last_valid_index()
            if first is None:
                raise ValidationError(f"stream {c!r} has no observations")
            inside = (full.index >= first) & (full.index <= last)
            full.loc[~inside, c] = np.nan
        return full.reindex(target)
    if freq not in _RULE:
        raise ValidationError(f"unknown freq {freq!r}; use D, W, M, Q or A")
    cols = {}
    for c in lv.columns:
        s = lv[c].dropna()
        cols[c] = s.resample(_RULE[freq]).last()
    out = pd.DataFrame(cols).sort_index()
    for c in out.columns:
        first = out[c].first_valid_index()
        last = out[c].last_valid_index()
        seg = out.loc[first:last, c].ffill()
        out.loc[first:last, c] = seg
    # label each period by the LAST ACTUAL observation date inside it (not the
    # nominal period end, which for a running week/month lies in the future)
    obs = pd.Series(lv.index[lv.notna().any(axis=1).to_numpy()],
                    index=lv.index[lv.notna().any(axis=1).to_numpy()])
    last_obs = obs.resample(_RULE[freq]).max().reindex(out.index)
    keep = last_obs.notna().to_numpy()
    out = out.loc[keep]
    out.index = pd.DatetimeIndex(last_obs[keep].to_numpy())
    return out


def levels_to_returns(levels: pd.DataFrame, kind: str = "simple") -> pd.DataFrame:
    """Per-period returns from aligned levels: simple r_t = P_t/P_{t-1} - 1 or
    log ln(P_t/P_{t-1}).  The first row is dropped; NaN propagates (no fill)."""
    lv = _check_levels(levels)
    ratio = lv / lv.shift(1)
    if kind == "simple":
        r = ratio - 1.0
    elif kind == "log":
        r = np.log(ratio)
    else:
        raise ValidationError(f"unknown return kind {kind!r}")
    return r.iloc[1:]


def returns_to_levels(returns: pd.DataFrame | pd.Series, base: float = 1.0):
    """Compound simple returns into a level index starting at ``base`` one
    period before the first return: P_t = base * prod_{s<=t} (1 + r_s)."""
    r = returns.astype(float)
    if (r <= -1).to_numpy().any():
        raise ValidationError("returns <= -100% cannot be compounded into levels")
    return base * (1.0 + r.fillna(0.0)).cumprod().where(r.notna().cummax())


def aligned_returns(levels: pd.DataFrame, freq: str = "D", calendar="active_intersection",
                    stale: str = "raise") -> pd.DataFrame:
    """align_levels then levels_to_returns (simple)."""
    return levels_to_returns(align_levels(levels, freq, calendar, stale))


def infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    """Observed periods per year = (n - 1) / (calendar span in years).  Useful
    to check that a 'D' series on the intersection calendar is ~252/yr and a
    crypto-only one ~365/yr."""
    if len(index) < 3:
        raise ValidationError("need at least 3 dates to infer frequency")
    years = (index[-1] - index[0]).days / 365.25
    if years <= 0:
        raise ValidationError("index spans zero time")
    return float((len(index) - 1) / years)


def common_window(returns: pd.DataFrame, min_obs: int = 2) -> pd.DataFrame:
    """Rows where every stream has a return (the common window).  Raises if
    fewer than ``min_obs`` rows remain."""
    r = returns.dropna(how="any")
    if len(r) < min_obs:
        raise ValidationError(f"common window has {len(r)} rows (< {min_obs}); streams barely overlap")
    return r


# --------------------------------------------------------------------------- #
# covariance estimators (per-period units)
# --------------------------------------------------------------------------- #
def _matrix(returns) -> np.ndarray:
    X = returns.to_numpy(dtype=float) if isinstance(returns, (pd.DataFrame, pd.Series)) else np.asarray(returns, float)
    if X.ndim != 2:
        raise ValidationError("returns must be 2-D (T x N)")
    if not np.all(np.isfinite(X)):
        raise ValidationError("returns contain NaN/inf; take a common window or use pairwise estimation")
    if X.shape[0] < 2:
        raise ValidationError("need at least 2 observations")
    return X


def sample_cov(returns, ddof: int = 1) -> np.ndarray:
    """Sample covariance S = X_c' X_c / (T - ddof), X_c demeaned."""
    X = _matrix(returns)
    Xc = X - X.mean(axis=0)
    return Xc.T @ Xc / (X.shape[0] - ddof)


def ewma_cov(returns, halflife: float, demean: bool = False) -> np.ndarray:
    """Exponentially weighted covariance with decay lambda = 0.5**(1/halflife):
        S = sum_t a_t (x_t - m)(x_t - m)',  a_t = lambda^{T-1-t} / sum lambda^{T-1-s}
    (most recent observation weight largest; m = a-weighted mean if ``demean``
    else 0, the RiskMetrics convention).  No small-sample bias correction."""
    if halflife <= 0:
        raise ValidationError("halflife must be > 0")
    X = _matrix(returns)
    T = X.shape[0]
    lam = 0.5 ** (1.0 / halflife)
    a = lam ** np.arange(T - 1, -1, -1, dtype=float)
    a /= a.sum()
    m = a @ X if demean else np.zeros(X.shape[1])
    Xc = X - m
    return (Xc * a[:, None]).T @ Xc


def ledoit_wolf_identity(returns) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf (2004, JMVA) shrinkage toward a scaled identity m I.

    With X demeaned, S = X'X/T, m = tr(S)/N, d^2 = ||S - mI||_F^2/N,
    b_bar^2 = (1/T^2) sum_t ||x_t x_t' - S||_F^2 / N, b^2 = min(b_bar^2, d^2),
    delta = b^2/d^2;   Sigma = delta m I + (1 - delta) S.
    Returns (Sigma, delta) in per-period units (1/T normalisation, as in
    the paper and scikit-learn)."""
    X = _matrix(returns)
    T, N = X.shape
    Xc = X - X.mean(axis=0)
    S = Xc.T @ Xc / T
    m = np.trace(S) / N
    d2 = np.sum((S - m * np.eye(N)) ** 2) / N
    row_norm2 = np.sum(Xc ** 2, axis=1)
    bbar2 = (np.sum(row_norm2 ** 2) - T * np.sum(S ** 2)) / (T ** 2) / N
    if d2 <= 0:
        return S, 0.0
    b2 = min(bbar2, d2)
    delta = float(max(0.0, b2 / d2))
    return delta * m * np.eye(N) + (1 - delta) * S, delta


def ledoit_wolf_constant_corr(returns) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf (2003/2004, "Honey, I shrunk the sample covariance
    matrix") shrinkage toward the constant-correlation target F:
        F_ii = s_ii,  F_ij = r_bar sqrt(s_ii s_jj),  r_bar = mean off-diag corr.
    Intensity delta = max(0, min(1, (pi - rho)/gamma / T)) with
        pi    = sum_ij mean_t[(x_ti x_tj - s_ij)^2]
        rho   = sum_i pi_ii + r_bar sum_{i!=j} sqrt(s_jj/s_ii) theta_ij,
                theta_ij = mean_t[(x_ti^2 - s_ii)(x_ti x_tj - s_ij)]
        gamma = ||F - S||_F^2
    (x demeaned, S = X'X/T).  Sigma = delta F + (1 - delta) S.  The diagonal
    (variances) is never shrunk.  Returns (Sigma, delta)."""
    X = _matrix(returns)
    T, N = X.shape
    x = X - X.mean(axis=0)
    S = x.T @ x / T
    var = np.diag(S).copy()
    if np.any(var <= 0):
        raise ValidationError("a stream has zero variance in the window; constant-correlation target undefined")
    sd = np.sqrt(var)
    if N == 1:
        return S, 0.0
    R = S / np.outer(sd, sd)
    rbar = (R.sum() - N) / (N * (N - 1))
    F = rbar * np.outer(sd, sd)
    np.fill_diagonal(F, var)
    y = x ** 2
    phi_mat = y.T @ y / T - S ** 2
    phi = phi_mat.sum()
    theta = (x ** 3).T @ x / T - var[:, None] * S
    np.fill_diagonal(theta, 0.0)
    rho = np.trace(phi_mat) + rbar * np.sum(np.outer(1.0 / sd, sd) * theta)
    gamma = np.sum((F - S) ** 2)
    if gamma <= 0:
        return S, 0.0
    kappa = (phi - rho) / gamma
    delta = float(max(0.0, min(1.0, kappa / T)))
    return delta * F + (1 - delta) * S, delta


def pairwise_cov(returns: pd.DataFrame, min_periods: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Pairwise-complete sample covariance: each S_ij uses the dates on which
    both i and j have returns (ddof 1).  Returns (S_raw, n_obs_ij).  S_raw is
    generally NOT PSD when histories differ; pass it through repair_covariance.
    Raises if any pair has fewer than ``min_periods`` overlapping observations."""
    if not isinstance(returns, pd.DataFrame):
        raise ValidationError("pairwise_cov needs a DataFrame")
    obs = returns.notna().astype(float).to_numpy()
    counts = obs.T @ obs
    if counts.min() < min_periods:
        i, j = np.unravel_index(np.argmin(counts), counts.shape)
        raise ValidationError(
            f"pair ({returns.columns[i]!r}, {returns.columns[j]!r}) overlaps on only {int(counts[i, j])} "
            f"observations (< min_periods={min_periods})")
    S = returns.cov(min_periods=min_periods).to_numpy()
    return 0.5 * (S + S.T), counts


# --------------------------------------------------------------------------- #
# PSD repair
# --------------------------------------------------------------------------- #
def _proj_psd(A: np.ndarray, floor: float = 0.0) -> np.ndarray:
    lam, V = np.linalg.eigh(0.5 * (A + A.T))
    lam = np.maximum(lam, floor)
    out = (V * lam) @ V.T
    return 0.5 * (out + out.T)


def nearest_correlation(A, *, tol: float = 1e-10, max_iter: int = 100_000, eig_floor: float = 0.0) -> np.ndarray:
    """Nearest correlation matrix in Frobenius norm (Higham 2002, IMA J.
    Numer. Anal. 22:329-343): alternating projections onto the PSD cone S+ and
    the unit-diagonal set U with Dykstra's correction:
        R = Y - dS;  X = P_S+(R);  dS = X - R;  Y = P_U(X)
    until ||Y - X||_F / ||Y||_F < tol.  A final polish projects onto S+ with
    eigenvalues >= eig_floor and rescales to unit diagonal (D^-1/2 X D^-1/2
    preserves PSD), so the result is EXACTLY unit-diagonal and PSD.
    Input must be square, symmetric and finite."""
    A = np.asarray(A, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise CovarianceError("nearest_correlation needs a square matrix")
    if not np.all(np.isfinite(A)):
        raise CovarianceError("nearest_correlation input has NaN/inf")
    if np.max(np.abs(A - A.T)) > 1e-8 * max(1.0, np.max(np.abs(A))):
        raise CovarianceError("nearest_correlation input is not symmetric")
    A = 0.5 * (A + A.T)
    Y = A.copy()
    dS = np.zeros_like(A)
    X = Y
    for _ in range(max_iter):
        R = Y - dS
        X = _proj_psd(R)
        dS = X - R
        Y_new = X.copy()
        np.fill_diagonal(Y_new, 1.0)
        done = np.linalg.norm(Y_new - X, "fro") / max(1.0, np.linalg.norm(Y_new, "fro")) < tol
        Y = Y_new
        if done:
            break
    else:
        raise CovarianceError(f"nearest_correlation did not converge in {max_iter} iterations")
    X = _proj_psd(Y, eig_floor)
    d = np.sqrt(np.diag(X))
    if np.any(d <= 0):
        raise CovarianceError("nearest_correlation produced a zero diagonal")
    C = X / np.outer(d, d)
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)
    return C


@dataclass
class RepairReport:
    """What repair_covariance changed."""
    repaired: bool
    min_eig_before: float
    min_eig_after: float
    frobenius_change_corr: float


def repair_covariance(S, *, eig_floor: float = 0.0) -> tuple[np.ndarray, RepairReport]:
    """Make a symmetric covariance PSD while keeping its variances: split into
    (sigma, C), replace C by nearest_correlation(C) (Higham 2002), recombine
    S' = diag(sigma) C' diag(sigma).  Returns (S', report).  If S is already
    PSD it is returned unchanged (report.repaired = False)."""
    A = np.asarray(S, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1] or not np.all(np.isfinite(A)):
        raise CovarianceError("repair_covariance needs a finite square matrix")
    A = 0.5 * (A + A.T)
    lo = float(np.linalg.eigvalsh(A)[0])
    sig = np.sqrt(np.clip(np.diag(A), 0, None))
    if np.any(sig == 0):
        raise CovarianceError("repair_covariance needs strictly positive variances")
    if lo >= 0 and eig_floor == 0:
        return A, RepairReport(False, lo, lo, 0.0)
    C = A / np.outer(sig, sig)
    np.fill_diagonal(C, 1.0)
    C2 = nearest_correlation(C, eig_floor=eig_floor)
    out = C2 * np.outer(sig, sig)
    return out, RepairReport(True, lo, float(np.linalg.eigvalsh(out)[0]), float(np.linalg.norm(C2 - C, "fro")))


# --------------------------------------------------------------------------- #
# stale marks / asynchronous prices
# --------------------------------------------------------------------------- #
def geltner_desmooth(r_obs: pd.Series, phi: float | None = None) -> tuple[pd.Series, float]:
    """Geltner (1993) de-smoothing of appraisal / stale-mark returns:
        r_true_t = (r_obs_t - phi r_obs_{t-1}) / (1 - phi).
    phi defaults to the lag-1 autocorrelation of r_obs.  Exact inverse of the
    smoothing model r_obs_t = (1 - phi) r_true_t + phi r_obs_{t-1}.  The first
    observation is dropped.  Returns (r_true, phi)."""
    r = pd.Series(r_obs, dtype=float).dropna()
    if len(r) < 4:
        raise ValidationError("need at least 4 observations to de-smooth")
    if phi is None:
        phi = float(r.autocorr(lag=1))
    if not np.isfinite(phi) or abs(phi) >= 0.99:
        raise ValidationError(f"phi={phi} outside (-0.99, 0.99); de-smoothing unstable")
    out = (r - phi * r.shift(1)) / (1.0 - phi)
    return out.iloc[1:], float(phi)


@dataclass
class DimsonResult:
    """Dimson (1979) aggregated beta: beta = sum of coefficients on the market
    return at lags 0..k (and leads, if requested)."""
    beta: float
    coefs: dict
    ols_beta: float
    n_obs: int


def dimson_beta(asset: pd.Series, market: pd.Series, lags: int = 1, leads: int = 0) -> DimsonResult:
    """OLS of r_asset_t on [1, m_{t+leads}, ..., m_t, ..., m_{t-lags}];
    beta_Dimson = sum of the market coefficients.  Corrects the downward bias
    of the plain OLS beta for stale / thinly traded marks."""
    if lags < 0 or leads < 0:
        raise ValidationError("lags/leads must be >= 0")
    df = pd.DataFrame({"y": asset, "m": market}).astype(float)
    cols = {}
    for k in range(-leads, lags + 1):
        cols[f"m_lag{k}"] = df["m"].shift(k)
    X = pd.DataFrame(cols, index=df.index)
    data = pd.concat([df["y"], X], axis=1).dropna()
    if len(data) < len(cols) + 5:
        raise ValidationError("too few overlapping observations for Dimson regression")
    Xm = np.column_stack([np.ones(len(data)), data[list(cols)].to_numpy()])
    coef, *_ = np.linalg.lstsq(Xm, data["y"].to_numpy(), rcond=None)
    both = df.dropna()
    ols = float(np.cov(both["y"], both["m"], ddof=1)[0, 1] / np.var(both["m"], ddof=1))
    return DimsonResult(float(coef[1:].sum()), dict(zip(cols, coef[1:].tolist())), ols, len(data))


def lagged_cov(returns, lags: int, weights: str = "bartlett") -> np.ndarray:
    """Long-run (lag-summed) covariance for asynchronous / stale marks:
        S_LR = G_0 + sum_{l=1..k} a_l (G_l + G_l'),  G_l = (1/T) sum_t x_t x_{t-l}'
    (x demeaned).  a_l = 1 - l/(k+1) (Bartlett / Newey-West: always PSD) or
    a_l = 1 ('flat', the Dimson / Scholes-Williams sum: may be non-PSD, then
    repaired with repair_covariance)."""
    X = _matrix(returns)
    if lags < 0:
        raise ValidationError("lags must be >= 0")
    T = X.shape[0]
    x = X - X.mean(axis=0)
    out = x.T @ x / T
    for l in range(1, lags + 1):
        G = x[l:].T @ x[:-l] / T
        a = 1.0 - l / (lags + 1.0) if weights == "bartlett" else 1.0 if weights == "flat" else None
        if a is None:
            raise ValidationError(f"unknown weights {weights!r}")
        out = out + a * (G + G.T)
    out = 0.5 * (out + out.T)
    if weights == "flat" and np.linalg.eigvalsh(out)[0] < 0:
        out, _ = repair_covariance(out)
    return out


# --------------------------------------------------------------------------- #
# one-call estimator
# --------------------------------------------------------------------------- #
@dataclass
class CovEstimate:
    """A covariance estimate with its provenance.  ``cov`` is per-period;
    ``annual`` multiplies by periods_per_year."""
    names: list
    cov: np.ndarray
    mean: np.ndarray
    periods_per_year: float
    method: str
    history: str
    n_obs: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    shrinkage: float | None = None
    repair: RepairReport | None = None
    notes: list = field(default_factory=list)

    @property
    def annual(self) -> np.ndarray:
        """Annualised covariance S_annual = S_period * periods_per_year
        (IID scaling; serial correlation is not modelled unless lagged_cov is used)."""
        return self.cov * self.periods_per_year

    @property
    def annual_mean(self) -> np.ndarray:
        """Annualised arithmetic mean = mean_period * periods_per_year."""
        return self.mean * self.periods_per_year


def estimate_cov(returns: pd.DataFrame, method: str = "lw_cc", *, history: str = "common",
                 periods_per_year: float | None = None, freq: str | None = None,
                 halflife: float | None = None, lags: int = 0, min_periods: int = 20) -> CovEstimate:
    """Estimate a per-period covariance.

    method:  'sample' | 'ewma' (needs halflife) | 'lw' (identity target) |
             'lw_cc' (constant-correlation target) | 'lagged' (Bartlett lag-sum, ``lags``)
    history: 'common'   -> use only rows where every stream has data;
             'pairwise' -> pairwise-complete sample covariance + Higham repair
                           (method must be 'sample'; shrinkage needs a common window).
    periods_per_year: explicit, or from ``freq`` via FREQ_PPY."""
    if not isinstance(returns, pd.DataFrame):
        raise ValidationError("returns must be a DataFrame")
    if periods_per_year is None:
        if freq is None or freq.upper() not in FREQ_PPY:
            raise ValidationError("give periods_per_year or a freq in D/W/M/Q/A")
        periods_per_year = FREQ_PPY[freq.upper()]
    names = list(returns.columns)
    if history == "pairwise":
        if method != "sample":
            raise ValidationError("history='pairwise' supports method='sample' only")
        S, counts = pairwise_cov(returns, min_periods=min_periods)
        S2, rep = repair_covariance(S)
        validate_covariance(S2)
        r = returns
        mean = r.mean().to_numpy()
        return CovEstimate(names, S2, mean, float(periods_per_year), method, history, int(counts.min()),
                           r.index[0] if len(r) else None, r.index[-1] if len(r) else None,
                           repair=rep, notes=[f"pairwise overlaps min {int(counts.min())} max {int(counts.max())}"])
    if history != "common":
        raise ValidationError(f"unknown history mode {history!r}")
    r = common_window(returns, min_obs=max(min_periods, 2))
    shrink = None
    if method == "sample":
        S = sample_cov(r)
    elif method == "ewma":
        if halflife is None:
            raise ValidationError("ewma needs halflife")
        S = ewma_cov(r, halflife)
    elif method == "lw":
        S, shrink = ledoit_wolf_identity(r)
    elif method == "lw_cc":
        S, shrink = ledoit_wolf_constant_corr(r)
    elif method == "lagged":
        S = lagged_cov(r, lags)
    else:
        raise ValidationError(f"unknown covariance method {method!r}")
    S = validate_covariance(S)
    return CovEstimate(names, S, r.mean().to_numpy(), float(periods_per_year), method, history, len(r),
                       r.index[0], r.index[-1], shrinkage=shrink)
