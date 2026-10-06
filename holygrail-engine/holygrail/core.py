"""Dalio Holy Grail core math. Pure functions (numpy/scipy only, no I/O).

Notation used in every docstring:
    N        number of streams
    w        weights, shape (N,). Fractions of NAV; may be geared (sum > 1) or
             carry a cash remainder (sum < 1). Cash is NOT a column of S.
    S        covariance matrix (N, N) of per-period or annualised returns
    sigma_i  sqrt(S_ii), the stream volatilities
    sigma_p  sqrt(w' S w), portfolio volatility
    mu       expected arithmetic returns (same period as S)
    rf       risk-free rate (same period as mu)

The four Holy Grail operations map onto this module as:
    (1) GOOD streams       -> sharpe_ratio / screens in scorecard.py
    (2) UNCORRELATED       -> effective_bets, diversification_ratio
    (3) RISK-BALANCED      -> risk_contributions, percent_risk_contributions
    (4) GEARED to target   -> leverage_for_target, geared_return, kelly_leverage
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from scipy.stats import norm

from .errors import CovarianceError, ValidationError

#: relative tolerance on the smallest eigenvalue when testing PSD:
#: lambda_min >= -PSD_RTOL * max(lambda_max, 1)
PSD_RTOL = 1e-9
#: absolute tolerance on asymmetry |S - S'| (scaled by max|S|, floor 1)
SYM_RTOL = 1e-8


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def as_vector(x, name: str = "vector", *, n: int | None = None) -> np.ndarray:
    """Return ``x`` as a finite 1-D float array; raise ValidationError otherwise.

    Fails on: non 1-D input, length != n (when given), any NaN/inf entry
    (the offending positions are listed in the message).
    """
    a = np.asarray(x, dtype=float)
    if a.ndim != 1:
        raise ValidationError(f"{name} must be 1-D, got shape {a.shape}")
    if n is not None and a.shape[0] != n:
        raise ValidationError(f"{name} has length {a.shape[0]}, expected {n}")
    bad = ~np.isfinite(a)
    if bad.any():
        raise ValidationError(f"{name} contains NaN/inf at positions {np.flatnonzero(bad).tolist()}")
    return a


def validate_covariance(S, *, name: str = "covariance", require_pd: bool = False) -> np.ndarray:
    """Validate and return a symmetric copy of a covariance matrix.

    Checks (each raises CovarianceError with the measured violation):
      * 2-D, square, non-empty, all entries finite;
      * symmetric: max|S - S'| <= SYM_RTOL * max(1, max|S|);
      * non-negative diagonal;
      * PSD: lambda_min(S) >= -PSD_RTOL * max(1, lambda_max(S))
        (``require_pd`` additionally demands lambda_min > 0).
    Returns (S + S') / 2.
    """
    A = np.asarray(S, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1] or A.shape[0] == 0:
        raise CovarianceError(f"{name} must be a non-empty square matrix, got shape {A.shape}")
    if not np.all(np.isfinite(A)):
        bad = np.argwhere(~np.isfinite(A))[:5].tolist()
        raise CovarianceError(f"{name} contains NaN/inf (first entries {bad})")
    scale = max(1.0, float(np.max(np.abs(A))))
    asym = float(np.max(np.abs(A - A.T)))
    if asym > SYM_RTOL * scale:
        raise CovarianceError(f"{name} is not symmetric (max |S-S'| = {asym:.3e})")
    A = 0.5 * (A + A.T)
    d = np.diag(A)
    if np.any(d < 0):
        raise CovarianceError(f"{name} has negative variances at {np.flatnonzero(d < 0).tolist()}")
    eig = np.linalg.eigvalsh(A)
    lo, hi = float(eig[0]), float(eig[-1])
    if lo < -PSD_RTOL * max(1.0, hi):
        raise CovarianceError(
            f"{name} is not positive semi-definite (min eigenvalue {lo:.3e}, max {hi:.3e}); "
            "repair it explicitly with estimate.repair_covariance / nearest_correlation"
        )
    if require_pd and lo <= 0:
        raise CovarianceError(f"{name} is singular (min eigenvalue {lo:.3e}); a positive-definite matrix is required")
    return A


def validate_weights(w, n: int | None = None, *, name: str = "weights", sum_to: float | None = None,
                     tol: float = 1e-8, long_only: bool = False) -> np.ndarray:
    """Validate a weight vector.

    Fails on NaN/inf, wrong length, |sum(w) - sum_to| > tol (when ``sum_to``
    is given) and any w_i < -tol (when ``long_only``).
    """
    a = as_vector(w, name, n=n)
    if sum_to is not None and abs(a.sum() - sum_to) > tol:
        raise ValidationError(f"{name} sum to {a.sum():.12g}, expected {sum_to} (tol {tol})")
    if long_only and np.any(a < -tol):
        raise ValidationError(f"{name} has negative entries at {np.flatnonzero(a < -tol).tolist()} but long_only=True")
    return a


def _check_pair(w, S) -> tuple[np.ndarray, np.ndarray]:
    S = validate_covariance(S)
    w = as_vector(w, "weights", n=S.shape[0])
    return w, S


# --------------------------------------------------------------------------- #
# portfolio risk
# --------------------------------------------------------------------------- #
def portfolio_variance(w, S) -> float:
    """sigma_p^2 = w' S w."""
    w, S = _check_pair(w, S)
    v = float(w @ S @ w)
    return max(v, 0.0) if v > -1e-15 else v


def portfolio_vol(w, S) -> float:
    """sigma_p = sqrt(w' S w)."""
    v = portfolio_variance(w, S)
    if v < 0:
        raise CovarianceError(f"negative portfolio variance {v:.3e}")
    return math.sqrt(v)


def marginal_risk(w, S) -> np.ndarray:
    """Marginal contribution to risk d sigma_p / d w_i = (S w)_i / sigma_p."""
    w, S = _check_pair(w, S)
    sp = math.sqrt(max(float(w @ S @ w), 0.0))
    if sp == 0:
        raise ValidationError("portfolio variance is zero; marginal risk is undefined")
    return (S @ w) / sp


def risk_contributions(w, S) -> np.ndarray:
    """Euler risk contributions RC_i = w_i (S w)_i / sigma_p.  sum_i RC_i = sigma_p."""
    w, S = _check_pair(w, S)
    sp = math.sqrt(max(float(w @ S @ w), 0.0))
    if sp == 0:
        raise ValidationError("portfolio variance is zero; risk contributions are undefined")
    return w * (S @ w) / sp


def percent_risk_contributions(w, S) -> np.ndarray:
    """PRC_i = w_i (S w)_i / sigma_p^2.  sum_i PRC_i = 1; a PRC may be negative
    (a hedge that reduces portfolio variance)."""
    w, S = _check_pair(w, S)
    v = float(w @ S @ w)
    if v <= 0:
        raise ValidationError("portfolio variance is zero; percent risk contributions are undefined")
    return w * (S @ w) / v


def cov_to_corr(S) -> tuple[np.ndarray, np.ndarray]:
    """Split S into (sigma, C) with C_ij = S_ij / (sigma_i sigma_j).

    Raises if any variance is zero (correlation undefined); drop zero-variance
    streams (e.g. cash) before calling.
    """
    S = validate_covariance(S)
    sig = np.sqrt(np.diag(S))
    if np.any(sig == 0):
        raise CovarianceError(f"zero-variance streams at {np.flatnonzero(sig == 0).tolist()}; correlation undefined")
    C = S / np.outer(sig, sig)
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)
    return sig, C


def corr_to_cov(sigma, C) -> np.ndarray:
    """S = diag(sigma) C diag(sigma)."""
    sig = as_vector(sigma, "sigma")
    C = validate_covariance(C, name="correlation")
    if C.shape[0] != sig.shape[0]:
        raise ValidationError("sigma and correlation sizes differ")
    return C * np.outer(sig, sig)


# --------------------------------------------------------------------------- #
# Dalio closed forms (equal vol, equal pairwise correlation, equal weights)
# --------------------------------------------------------------------------- #
def _check_rho(rho: float, n: int) -> None:
    if not np.isfinite(rho) or rho > 1 + 1e-15:
        raise ValidationError(f"rho must be finite and <= 1, got {rho}")
    if n > 1 and rho < -1.0 / (n - 1) - 1e-15:
        raise ValidationError(f"rho={rho} < -1/(N-1)={-1/(n-1):.6f}: equal-correlation matrix is not PSD")


def equal_corr_vol(sigma: float, rho: float, n: int) -> float:
    """sigma_p = sigma * sqrt((1 + (N-1) rho) / N) for N equal-vol, equal-rho
    streams held 1/N each.  (Dalio check: sigma=18%, rho=0 -> N=5: 8.050%,
    N=10: 5.692%, N=15: 4.648%.)"""
    n = int(n)
    if n < 1:
        raise ValidationError("N must be >= 1")
    if not np.isfinite(sigma) or sigma < 0:
        raise ValidationError(f"sigma must be finite and >= 0, got {sigma}")
    _check_rho(rho, n)
    return float(sigma * math.sqrt(max(1.0 + (n - 1) * rho, 0.0) / n))


def diversification_improvement(n: int, rho: float) -> float:
    """Return-to-risk improvement of N equal bets over one bet:
    sqrt(N / (1 + (N-1) rho)).  Equals the diversification ratio DR of the
    equal-weight equal-rho portfolio (so improvement^2 = N_eff)."""
    n = int(n)
    _check_rho(rho, n)
    den = 1.0 + (n - 1) * rho
    if den <= 0:
        return float("inf")
    return float(math.sqrt(n / den))


def vol_floor(sigma: float, rho: float) -> float:
    """lim_{N->inf} sigma_p = sigma * sqrt(rho): correlation sets a floor that no
    number of equal bets can diversify away."""
    if rho < 0:
        raise ValidationError("vol floor defined for rho >= 0")
    return float(sigma * math.sqrt(rho))


def equal_corr_matrix(n: int, rho: float) -> np.ndarray:
    """C = (1 - rho) I + rho 11'  (validated to be PSD: rho >= -1/(N-1))."""
    n = int(n)
    _check_rho(rho, n)
    C = np.full((n, n), float(rho))
    np.fill_diagonal(C, 1.0)
    return C


def equal_corr_cov(n: int, sigma: float, rho: float) -> np.ndarray:
    """S = sigma^2 [(1 - rho) I + rho 11']."""
    return float(sigma) ** 2 * equal_corr_matrix(n, rho)


def dalio_table(sigma: float = 0.18, mu: float = 0.06, ns: Iterable[int] = (1, 5, 10, 15),
                rhos: Iterable[float] = (0.0,)) -> list[dict]:
    """Rows of Dalio's illustration: for each (N, rho)
        sigma_p          = sigma sqrt((1+(N-1)rho)/N)
        return_to_risk   = mu / sigma_p          (Dalio uses total return / sd)
        improvement      = sqrt(N/(1+(N-1)rho))  (vs a single bet)
        neff             = N / (1+(N-1)rho)
        floor            = sigma sqrt(rho)
    Note: Dalio's text says "factor of 4.3x (0.3 -> 1.29)"; 6%/18% is 0.333,
    and the exact improvement at N=15, rho=0 is sqrt(15) = 3.873.  The 4.3x
    comes from rounding the single-bet ratio down to 0.3."""
    rows = []
    for rho in rhos:
        for n in ns:
            sp = equal_corr_vol(sigma, rho, n)
            rows.append({
                "n": int(n), "rho": float(rho), "sigma": float(sigma), "mu": float(mu),
                "sigma_p": sp,
                "return_to_risk": (mu / sp) if sp > 0 else float("inf"),
                "improvement": diversification_improvement(n, rho),
                "neff": neff_equal_rho(n, rho),
                "floor": vol_floor(sigma, rho) if rho >= 0 else float("nan"),
            })
    return rows


# --------------------------------------------------------------------------- #
# effective number of bets
# --------------------------------------------------------------------------- #
def neff_equal_rho(n: int, rho: float) -> float:
    """(a) Equal-rho closed form N_eff = N / (1 + (N-1) rho)."""
    n = int(n)
    _check_rho(rho, n)
    den = 1.0 + (n - 1) * rho
    return float("inf") if den <= 0 else float(n / den)


def mean_pairwise_correlation(C) -> float:
    """Simple average of the off-diagonal entries of a correlation matrix
    (rho_bar = sum_{i!=j} C_ij / (N(N-1))); 0 for N = 1."""
    C = np.asarray(C, dtype=float)
    n = C.shape[0]
    if n < 2:
        return 0.0
    return float((C.sum() - np.trace(C)) / (n * (n - 1)))


def neff_from_prc(w, S) -> tuple[float, bool]:
    """(b) N_eff = 1 / sum_i PRC_i^2 (inverse Herfindahl of risk shares).

    Returns (value, has_negative_prc).  When any PRC < 0 the measure is no
    longer bounded by N and should be read with that flag.  This is a
    RISK-BALANCE measure: it equals N whenever risk contributions are equal,
    irrespective of correlation."""
    prc = percent_risk_contributions(w, S)
    return float(1.0 / np.sum(prc ** 2)), bool(np.any(prc < -1e-12))


def _entropy_exp(p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 0.0, None)
    s = p.sum()
    if s <= 0:
        raise ValidationError("diversification distribution sums to zero")
    p = p / s
    nz = p[p > 0]
    return float(math.exp(-np.sum(nz * np.log(nz))))


def _is_diagonal(S: np.ndarray, rtol: float = 1e-14) -> bool:
    off = S - np.diag(np.diag(S))
    return bool(np.max(np.abs(off)) <= rtol * max(1e-300, float(np.max(np.abs(np.diag(S))))))


def pca_risk_distribution(w, S, n_obs: int | None = None) -> tuple[np.ndarray, bool]:
    """Meucci (2009) principal-portfolio variance shares.

    S = E diag(lambda) E'; principal exposures w~ = E' w;
    p_k = w~_k^2 lambda_k / sigma_p^2  (p_k >= 0, sum = 1).
    For diagonal S the asset basis is used (E = I).  Returns (p, basis_ambiguous).
    basis_ambiguous flags eigenvectors that are not identified, so that p
    depends on an arbitrary rotation:
      * exactly repeated eigenvalues of a non-diagonal S (any n_obs), and
      * when S is ESTIMATED from ``n_obs`` observations, adjacent eigenvalues
        closer than their sampling error, lambda_{k+1} - lambda_k <
        lambda_{k+1} sqrt(2 / n_obs) (North, Bell, Cahalan & Moeng 1982),
        among components carrying at least 1% of the risk (mixing components
        that carry none cannot move p)."""
    w, S = _check_pair(w, S)
    v = float(w @ S @ w)
    if v <= 0:
        raise ValidationError("portfolio variance is zero; PCA risk distribution undefined")
    if _is_diagonal(S) and n_obs is None:
        lam, E, ambiguous = np.diag(S).copy(), np.eye(S.shape[0]), False
    else:
        if _is_diagonal(S):
            lam, E = np.diag(S).copy(), np.eye(S.shape[0])
            order = np.argsort(lam)
            lam, E = lam[order], E[:, order]
            ambiguous = False
        else:
            lam, E = np.linalg.eigh(S)
            lam = np.clip(lam, 0.0, None)
            ambiguous = bool(np.any(np.diff(lam) <= 1e-10 * max(1.0, float(lam[-1]))))
        if n_obs is not None:
            if n_obs < 2:
                raise ValidationError("n_obs must be >= 2")
            pk = (E.T @ w) ** 2 * lam / v
            close = np.diff(lam) < lam[1:] * math.sqrt(2.0 / n_obs)
            carries = np.maximum(pk[:-1], pk[1:]) >= 0.01
            ambiguous = ambiguous or bool(np.any(close & carries))
    wt = E.T @ w
    p = wt ** 2 * lam / v
    return p / p.sum(), ambiguous


def neff_pca_entropy(w, S, n_obs: int | None = None) -> tuple[float, bool]:
    """(c) Meucci (2009) N_ent = exp(-sum_k p_k ln p_k) over principal-portfolio
    variance shares p_k (see pca_risk_distribution).  Returns (value,
    basis_ambiguous).  Caveat: for an equal-weight equal-rho book with rho > 0
    the weight vector IS the first principal portfolio, so N_ent = 1 for every
    rho > 0 but N at rho = 0 (discontinuous); read with the ambiguity flag
    (pass ``n_obs`` for an estimated S).  It tracks how w lines up with the
    eigenvectors, not how high correlations are: eigenbasis-dependent."""
    p, amb = pca_risk_distribution(w, S, n_obs)
    return _entropy_exp(p), amb


@dataclass(frozen=True)
class TorsionResult:
    """Minimum-torsion transformation (Meucci, Santangelo, Deguest 2015).

    t      torsion matrix: f~ = t f are uncorrelated (None if the correlation
           matrix had to be regularised and t would be ill-conditioned)
    c      symmetric (Riccati) root of the correlation matrix C used
    q      orthogonal factor, d diagonal scales: standardised f~ = D q c^{-1} z
    objective ||D q - c||_F (root of the summed tracking variance of the
           standardised uncorrelated factors versus the originals)
    """
    t: np.ndarray | None
    c: np.ndarray
    q: np.ndarray
    d: np.ndarray
    sigma: np.ndarray
    iterations: int
    converged: bool
    regularized: bool
    objective: float


def _sym_sqrt(C: np.ndarray) -> np.ndarray:
    lam, V = np.linalg.eigh(C)
    lam = np.clip(lam, 0.0, None)
    R = (V * np.sqrt(lam)) @ V.T
    return 0.5 * (R + R.T)


def _polar(M: np.ndarray) -> np.ndarray:
    U, _, Vt = np.linalg.svd(M)
    return U @ Vt


def minimum_torsion(S, *, max_iter: int = 10_000, tol: float = 1e-13, ridge: float = 1e-9) -> TorsionResult:
    """Minimum-torsion transformation, exact algorithm of Meucci, Santangelo &
    Deguest (2015, "Risk budgeting and diversification based on optimised
    uncorrelated factors", Risk; SSRN 2276632, appendix / torsion.m).

    Problem: among all t with Cr{t f} = I (uncorrelated factors), minimise
        sum_n Sd{ ((t f)_n - f_n) / Sd{f_n} }^2.
    With z = sigma^{-1} f standardised, C = Cr{f} and c = C^{1/2}, every
    uncorrelated standardised set is z~ = D q c^{-1} z (q orthogonal, D
    diagonal) and the objective equals ||D q - c||_F^2.  Alternating exact
    minimisation (the published iteration):
        q <- polar(D c)            (orthogonal Procrustes, = (D c c D)^{-1/2} D c)
        d <- diag(q c)
    until the objective stops decreasing; then x = D q c^{-1} and
        t = diag(sigma) x diag(sigma)^{-1}.
    For diagonal S: c = I, q = I, d = 1 and t = I exactly.

    A singular correlation matrix (e.g. perfectly correlated streams) makes the
    problem degenerate; it is regularised to (1-ridge) C + ridge I and the
    result is flagged ``regularized``.  Zero-variance streams must be dropped
    by the caller."""
    S = validate_covariance(S)
    sig = np.sqrt(np.diag(S))
    if np.any(sig == 0):
        raise CovarianceError("minimum torsion needs strictly positive variances; drop zero-variance streams")
    n = S.shape[0]
    C = S / np.outer(sig, sig)
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)
    regularized = False
    if np.linalg.eigvalsh(C)[0] < ridge:
        C = (1 - ridge) * C + ridge * np.eye(n)
        regularized = True
    c = _sym_sqrt(C)
    d = np.ones(n)
    q = np.eye(n)
    prev = math.inf
    converged = False
    it = 0
    obj = math.inf
    for it in range(1, max_iter + 1):
        q = _polar(d[:, None] * c)
        d = np.einsum("ij,ji->i", q, c)
        obj = float(np.linalg.norm(d[:, None] * q - c, "fro"))
        if abs(prev - obj) <= tol * max(1.0, obj):
            converged = True
            break
        prev = obj
    t = None
    if not regularized:
        x = (d[:, None] * q) @ np.linalg.inv(c)
        t = (sig[:, None] * x) / sig[None, :]
    return TorsionResult(t=t, c=c, q=q, d=d, sigma=sig, iterations=it, converged=converged,
                         regularized=regularized, objective=obj)


def minimum_torsion_distribution(w, S, torsion: TorsionResult | None = None) -> np.ndarray:
    """Minimum-torsion diversification distribution
        p_k = (t'^{-1} w)_k (t S w)_k / (w' S w)        (MSD 2015, eq. for p_MT)
    computed in the algebraically identical, inversion-free form
        p_k = (q c sigma∘w)_k^2 / ||q c sigma∘w||^2,
    which is >= 0, sums to 1, and stays defined when C is near-singular."""
    w, S = _check_pair(w, S)
    tr = torsion if torsion is not None else minimum_torsion(S)
    v = tr.q @ (tr.c @ (tr.sigma * w))
    tot = float(v @ v)
    if tot <= 0:
        raise ValidationError("portfolio variance is zero; minimum-torsion distribution undefined")
    return v ** 2 / tot


def neff_minimum_torsion(w, S) -> tuple[float, TorsionResult]:
    """(d) Minimum-torsion effective number of bets exp(-sum p_k ln p_k) with
    p from minimum_torsion_distribution.  RISK-BALANCE measure: like (b) it
    equals N for an equal-weight equal-rho book at ANY rho (by symmetry the
    uncorrelated factors carry equal risk); it does not fall to 1 as rho -> 1."""
    tr = minimum_torsion(S)
    return _entropy_exp(minimum_torsion_distribution(w, S, tr)), tr


def diversification_ratio(w, S) -> float:
    """DR = (w' sigma) / sigma_p  (Choueifaty & Coignard 2008).  DR >= 1 for
    long-only books; DR^2 is the correlation-aware effective number of bets and
    equals N/(1+(N-1)rho) in the equal-vol equal-rho equal-weight case."""
    w, S = _check_pair(w, S)
    sp = math.sqrt(max(float(w @ S @ w), 0.0))
    if sp == 0:
        raise ValidationError("portfolio variance is zero; diversification ratio undefined")
    return float(w @ np.sqrt(np.diag(S)) / sp)


def implied_average_correlation(w, S) -> float:
    """The single pairwise rho that reproduces sigma_p given w and sigma:
        rho_bar = (sigma_p^2 - sum (w_i sigma_i)^2) / ((w'sigma)^2 - sum (w_i sigma_i)^2).
    Equivalently, in the equal-weight equal-vol case, (N/DR^2 - 1)/(N - 1).
    NaN when fewer than two streams carry risk."""
    w, S = _check_pair(w, S)
    ws = w * np.sqrt(np.diag(S))
    num = float(w @ S @ w) - float(ws @ ws)
    den = float(ws.sum() ** 2) - float(ws @ ws)
    if abs(den) < 1e-300:
        return float("nan")
    return float(num / den)


@dataclass
class EffectiveBets:
    """All effective-number-of-bets measures for one (w, S), each labelled.

    correlation-aware (fall toward 1 as correlations rise):
        equal_rho   (a) N/(1+(N-1) rho_bar), rho_bar = mean pairwise corr
        dr2         (e) diversification ratio squared  <- headline: Holy Grail N_eff
    eigenbasis-dependent (how w lines up with the principal components; 1
    under perfect correlation, but unstable when eigenvalues are close):
        pca_entropy (c) Meucci 2009 principal-portfolio entropy
    risk-balance (equal N whenever risk contributions are equal):
        prc_inverse_hhi (b) 1/sum PRC^2
        min_torsion     (d) Meucci-Santangelo-Deguest 2015
    DR uses the SIGNED w'sigma: with short weights (has_short) it is not an
    effective number of bets, and negative correlations push DR^2 and (a)
    above N; both are flagged in rows().
    """
    n: int
    rho_bar: float
    equal_rho: float
    prc_inverse_hhi: float
    prc_has_negative: bool
    pca_entropy: float
    pca_basis_ambiguous: bool
    min_torsion: float
    min_torsion_regularized: bool
    min_torsion_converged: bool
    dr: float
    dr2: float
    implied_avg_corr: float
    dropped_zero_variance: list[int] = field(default_factory=list)
    has_short: bool = False
    n_obs: int | None = None

    @property
    def dr_warnings(self) -> list[str]:
        """Why DR / DR^2 cannot be read as a count of independent bets here."""
        out = []
        if self.has_short:
            out.append("short weights: DR uses signed w'sigma, DR^2 is not an effective number of bets")
        if self.dr2 > self.n + 1e-9:
            out.append(f"DR^2 exceeds the stream count N={self.n} (negative correlations / hedges)")
        return out

    def rows(self) -> list[dict]:
        """Labelled rows for reports: measure, value, class, flag."""
        amb = ("eigenbasis not identified: eigenvalues within sampling error (North et al. 1982)"
               if self.n_obs is not None else "eigenbasis not unique (repeated eigenvalues)")
        eq_flag = "uses simple mean pairwise correlation"
        if self.equal_rho > self.n + 1e-9:
            eq_flag += f"; exceeds N={self.n} (negative mean correlation)"
        return [
            {"measure": "dr2", "label": "(e) Diversification ratio squared DR^2 [headline Holy Grail N_eff]",
             "value": self.dr2, "class": "correlation-aware", "flag": "; ".join(self.dr_warnings)},
            {"measure": "equal_rho", "label": f"(a) Equal-rho closed form N/(1+(N-1)rho_bar), rho_bar={self.rho_bar:.3f}",
             "value": self.equal_rho, "class": "correlation-aware", "flag": eq_flag},
            {"measure": "pca_entropy", "label": "(c) Meucci 2009 PCA risk entropy", "value": self.pca_entropy,
             "class": "eigenbasis-dependent", "flag": amb if self.pca_basis_ambiguous else ""},
            {"measure": "prc_inverse_hhi", "label": "(b) 1/sum(PRC^2) inverse HHI of risk shares",
             "value": self.prc_inverse_hhi, "class": "risk-balance",
             "flag": "negative PRC present (hedges); not bounded by N" if self.prc_has_negative else ""},
            {"measure": "min_torsion", "label": "(d) Minimum-torsion bets (Meucci-Santangelo-Deguest 2015)",
             "value": self.min_torsion, "class": "risk-balance",
             "flag": ("correlation matrix singular: regularised" if self.min_torsion_regularized else "")
             + ("; not converged" if not self.min_torsion_converged else "")},
        ]


def effective_bets(w, S, n_obs: int | None = None) -> EffectiveBets:
    """Compute every N_eff measure (a)-(e) plus DR and the implied average
    correlation.  Streams with zero variance (cash) or zero weight are dropped
    from the correlation-based measures (they carry no risk) and listed in
    ``dropped_zero_variance``; N counts the remaining risk-carrying streams.
    ``n_obs``: observations behind an ESTIMATED S (enables the sampling-error
    ambiguity flag of the PCA entropy)."""
    w, S = _check_pair(w, S)
    if float(w @ S @ w) <= 0:
        raise ValidationError("portfolio variance is zero; effective bets undefined")
    var = np.diag(S)
    keep = (var > 0) & (w != 0)
    dropped = np.flatnonzero(~keep).tolist()
    wk, Sk = w[keep], S[np.ix_(keep, keep)]
    n = int(keep.sum())
    sig, C = cov_to_corr(Sk)
    rho_bar = mean_pairwise_correlation(C)
    prc_val, prc_neg = neff_from_prc(wk, Sk)
    pca_val, amb = neff_pca_entropy(wk, Sk, n_obs)
    mt_val, tr = neff_minimum_torsion(wk, Sk)
    dr = diversification_ratio(wk, Sk)
    return EffectiveBets(
        n=n, rho_bar=rho_bar,
        equal_rho=neff_equal_rho(n, max(rho_bar, -1.0 / (n - 1) if n > 1 else 0.0)),
        prc_inverse_hhi=prc_val, prc_has_negative=prc_neg,
        pca_entropy=pca_val, pca_basis_ambiguous=amb,
        min_torsion=mt_val, min_torsion_regularized=tr.regularized, min_torsion_converged=tr.converged,
        dr=dr, dr2=dr * dr, implied_avg_corr=implied_average_correlation(wk, Sk),
        dropped_zero_variance=dropped, has_short=bool(np.any(wk < 0)), n_obs=n_obs,
    )


# --------------------------------------------------------------------------- #
# return / risk ratios
# --------------------------------------------------------------------------- #
def sharpe_ratio(mu_p: float, sigma_p: float, rf: float = 0.0) -> float:
    """Sharpe = (mu_p - rf) / sigma_p."""
    if not (np.isfinite(mu_p) and np.isfinite(sigma_p) and np.isfinite(rf)):
        raise ValidationError("sharpe_ratio inputs must be finite")
    if sigma_p <= 0:
        raise ValidationError("sigma_p must be > 0")
    return float((mu_p - rf) / sigma_p)


def portfolio_sharpe(w, mu, S, rf: float = 0.0) -> float:
    """General portfolio Sharpe = w'(mu - rf) / sigma_p (w = risky weights;
    any cash remainder earns rf and so adds nothing to the excess return)."""
    w, S = _check_pair(w, S)
    mu = as_vector(mu, "mu", n=S.shape[0])
    return sharpe_ratio(float(w @ mu) + (1 - w.sum()) * rf, portfolio_vol(w, S), rf)


def equal_sharpe_identity(stream_sharpe: float, w, S) -> float:
    """Holy Grail multiplier identity: if every stream has the same Sharpe s
    (mu_i - rf = s sigma_i) then portfolio Sharpe = s * DR, because
    w'(mu - rf) = s w'sigma and DR = w'sigma / sigma_p."""
    return float(stream_sharpe * diversification_ratio(w, S))


# --------------------------------------------------------------------------- #
# gearing
# --------------------------------------------------------------------------- #
def leverage_for_target(sigma_p: float, target_vol: float, max_leverage: float = math.inf) -> float:
    """L = min(sigma* / sigma_p, max_leverage)."""
    if sigma_p <= 0 or not np.isfinite(sigma_p):
        raise ValidationError(f"sigma_p must be finite and > 0, got {sigma_p}")
    if target_vol < 0 or not np.isfinite(target_vol):
        raise ValidationError(f"target_vol must be finite and >= 0, got {target_vol}")
    if max_leverage <= 0:
        raise ValidationError("max_leverage must be > 0")
    return float(min(target_vol / sigma_p, max_leverage))


def _noncash_share(cash_share: float) -> float:
    u = 1.0 - float(cash_share)
    if not np.isfinite(u) or u <= 0:
        raise ValidationError(f"cash_share must be finite and < 1 (the book needs a risky part), got {cash_share}")
    return u


def new_borrowing(leverage: float, cash_share: float = 0.0) -> float:
    """Fraction of NAV NEWLY borrowed when the book's non-cash part
    u = 1 - cash_share is scaled by L and the extra exposure is funded first
    from the book's own net cash:
        B(L) = max( max(L u - 1, 0) - max(u - 1, 0), 0 ).
    cash_share = 0 gives the plain (L - 1)+.  A book that already borrows
    (cash_share < 0, e.g. a margin-loan liability carried at its own rate)
    borrows all of its extra exposure: B = (L - 1) u for L >= 1.  De-gearing
    (L < 1) never earns a spread rebate."""
    if leverage < 0:
        raise ValidationError("leverage must be >= 0")
    u = _noncash_share(cash_share)
    return float(max(max(leverage * u - 1.0, 0.0) - max(u - 1.0, 0.0), 0.0))


def geared_return(mu_p: float, rf: float, leverage: float, spread: float = 0.0, *, cash_share: float = 0.0) -> float:
    """Expected return of the book with its NON-CASH part geared L x:
        r(L) = rf + L (mu_p - rf) - B(L) * spread,   B(L) = new_borrowing(L, cash_share).
    ``mu_p`` is the book's expected return with its cash earning rf (cash adds
    no excess return, so the geared excess is L (mu_p - rf)); ``cash_share`` is
    the share of NAV in cash.  The financing spread applies ONLY to new
    borrowing: the book's own cash funds the first cash_share/(1-cash_share)
    of extra exposure spread-free.  For L < 1 the freed exposure earns rf."""
    return float(rf + leverage * (mu_p - rf) - new_borrowing(leverage, cash_share) * spread)


def log_growth(mu_p: float, sigma_p: float, rf: float, leverage: float, spread: float = 0.0, *,
               cash_share: float = 0.0) -> float:
    """Expected log-growth (continuous approximation)
        g(L) = rf + L (mu_p - rf) - B(L) spread - L^2 sigma_p^2 / 2   (B as in geared_return)."""
    return float(geared_return(mu_p, rf, leverage, spread, cash_share=cash_share) - 0.5 * leverage ** 2 * sigma_p ** 2)


def kelly_leverage(mu_p: float, sigma_p: float, rf: float, spread: float = 0.0, *, cash_share: float = 0.0) -> float:
    """Growth-optimal leverage L* = argmax_{L>=0} g(L) (g as in log_growth).

    g is concave with a kink where new borrowing starts, L_k = max(1, 1/u)
    (u = 1 - cash_share; L_k = 1/u when the book holds cash).  Below it the
    slope of the mean is mu_p - rf, above it mu_p - rf - u spread:
        a = (mu_p - rf)/sigma_p^2,  b = (mu_p - rf - u spread)/sigma_p^2,
        L* = max(a, 0) if a <= L_k, b if b >= L_k, else L_k.
    cash_share = 0 gives the textbook kink at L = 1 and b = (mu_p - rf - spread)/sigma_p^2."""
    if sigma_p <= 0:
        raise ValidationError("sigma_p must be > 0")
    u = _noncash_share(cash_share)
    kink = max(1.0, 1.0 / u)
    a = (mu_p - rf) / sigma_p ** 2
    if a <= kink:
        return float(max(a, 0.0))
    b = (mu_p - rf - u * spread) / sigma_p ** 2
    return float(b if b >= kink else kink)


def prob_loss(mu: float, sigma: float, years: float = 1.0, model: str = "normal") -> float:
    """Probability the book loses money over ``years``.

    normal:    R_h ~ N(mu h, sigma^2 h)               -> Phi(-mu sqrt(h) / sigma)
    lognormal: ln W_h ~ N((mu - sigma^2/2) h, sigma^2 h) -> Phi(-(mu - sigma^2/2) sqrt(h) / sigma)
    (mu = annual arithmetic mean, sigma = annual vol).  The 1-year normal case
    is Phi(-mu/sigma).  Empirical / Monte Carlo versions live in metrics/forward."""
    if sigma <= 0:
        raise ValidationError("sigma must be > 0")
    if years <= 0:
        raise ValidationError("years must be > 0")
    if model == "normal":
        z = -mu * math.sqrt(years) / sigma
    elif model == "lognormal":
        z = -(mu - 0.5 * sigma ** 2) * math.sqrt(years) / sigma
    else:
        raise ValidationError(f"unknown model {model!r}")
    return float(norm.cdf(z))


# --------------------------------------------------------------------------- #
# estimation-error helpers
# --------------------------------------------------------------------------- #
def sharpe_se(sharpe: float, n_obs: float) -> float:
    """Lo (2002) IID standard error SE(S^) ~ sqrt((1 + S^2/2) / T), with the
    Sharpe and T in the SAME period units (annual Sharpe with T in years, or
    per-period Sharpe with T periods)."""
    if n_obs <= 0:
        raise ValidationError("n_obs must be > 0")
    return float(math.sqrt((1.0 + 0.5 * sharpe ** 2) / n_obs))


def sharpe_se_annualized(sharpe_annual: float, years: float, periods_per_year: float) -> float:
    """SE of an annualised Sharpe estimated from q = periods_per_year
    observations per year over ``years``:  SE = sqrt((1 + S_a^2/(2q)) / years)
    (Lo 2002 with S_period = S_a/sqrt(q), T = q*years, scaled by sqrt(q))."""
    if years <= 0 or periods_per_year <= 0:
        raise ValidationError("years and periods_per_year must be > 0")
    return float(math.sqrt((1.0 + sharpe_annual ** 2 / (2.0 * periods_per_year)) / years))


def corr_se(rho: float, n_obs: float) -> float:
    """Large-sample SE(rho^) ~ (1 - rho^2) / sqrt(T)."""
    if n_obs <= 0:
        raise ValidationError("n_obs must be > 0")
    if abs(rho) > 1:
        raise ValidationError("|rho| must be <= 1")
    return float((1.0 - rho ** 2) / math.sqrt(n_obs))


def corr_ci(rho: float, n_obs: int, level: float = 0.95) -> tuple[float, float]:
    """Fisher-z confidence interval: z = atanh(rho), SE_z = 1/sqrt(T-3),
    CI = tanh(z +/- z_{(1+level)/2} SE_z)."""
    if n_obs <= 3:
        raise ValidationError("need n_obs > 3 for the Fisher-z interval")
    if abs(rho) >= 1:
        return (float(rho), float(rho))
    z = math.atanh(rho)
    h = norm.ppf(0.5 + level / 2) / math.sqrt(n_obs - 3)
    return (math.tanh(z - h), math.tanh(z + h))
