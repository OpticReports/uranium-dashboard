"""Allocators: turn a covariance matrix into weights.

Every allocator returns risky weights summing to 1 (gearing is a separate,
explicit step: target_vol_gearing).  Solutions are VERIFIED, not trusted:
risk budgeting checks max |PRC_i - b_i| <= 1e-10, QP solutions pass a KKT
check, and failures raise OptimizationError.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import lsq_linear, minimize
from scipy.spatial.distance import pdist

from .core import as_vector, percent_risk_contributions, portfolio_vol, validate_covariance
from .errors import OptimizationError, ValidationError

RB_TOL = 1e-10  # verified max |PRC - budget| for risk budgeting


def _cov(S) -> np.ndarray:
    S = validate_covariance(S)
    if np.any(np.diag(S) <= 0):
        raise ValidationError("allocators need strictly positive variances (drop cash / zero-vol streams first)")
    return S


# --------------------------------------------------------------------------- #
# heuristics
# --------------------------------------------------------------------------- #
def equal_weight(S) -> np.ndarray:
    """w_i = 1/N."""
    n = validate_covariance(S).shape[0]
    return np.full(n, 1.0 / n)


def inverse_vol(S) -> np.ndarray:
    """w_i = (1/sigma_i) / sum_j (1/sigma_j).  Equals ERC when S is diagonal."""
    S = _cov(S)
    iv = 1.0 / np.sqrt(np.diag(S))
    return iv / iv.sum()


def inverse_variance(S) -> np.ndarray:
    """w_i = (1/sigma_i^2) / sum_j (1/sigma_j^2).  Minimum variance when S is diagonal."""
    S = _cov(S)
    iv = 1.0 / np.diag(S)
    return iv / iv.sum()


# --------------------------------------------------------------------------- #
# risk budgeting / ERC
# --------------------------------------------------------------------------- #
def _rb_newton(S, b, max_iter, tol):
    y = 1.0 / np.sqrt(np.diag(S))
    v0 = float(y @ S @ y)
    if not v0 > 1e-14 * float(np.max(np.diag(S))) * float(y @ y):
        raise OptimizationError("risk budgeting: the inverse-vol start has zero variance (a perfectly hedged "
                                "combination exists); risk contributions are undefined")
    y *= math.sqrt(b.sum() / v0)

    def F(v):
        return 0.5 * float(v @ S @ v) - float(b @ np.log(v))

    for it in range(max_iter):
        g = S @ y - b / y
        H = S + np.diag(b / y ** 2)
        try:
            dy = np.linalg.solve(H, -g)
        except np.linalg.LinAlgError as e:
            raise OptimizationError(f"risk budgeting Newton step failed ({e}); covariance is singular") from None
        if not np.all(np.isfinite(dy)):
            raise OptimizationError("risk budgeting Newton step is not finite; covariance is singular")
        dec2 = float(-g @ dy)
        if dec2 < tol:
            return y, it
        step = 1.0
        while np.any(y + step * dy <= 0):
            step *= 0.5
        # Armijo backtracking far from the optimum only: near it the decrease
        # (~dec2/2) falls below the floating-point resolution of F and the
        # line search would stall; there the full Newton step converges
        # quadratically.
        if dec2 > 1e-8:
            f0 = F(y)
            while F(y + step * dy) > f0 - 1e-4 * step * dec2 and step > 1e-12:
                step *= 0.5
        y = y + step * dy
    return y, max_iter


def _rb_ccd(S, b, max_iter, tol):
    n = len(b)
    y = 1.0 / np.sqrt(np.diag(S))
    d = np.diag(S)
    for it in range(max_iter):
        for i in range(n):
            ci = float(S[i] @ y) - d[i] * y[i]
            y[i] = (-ci + math.sqrt(ci * ci + 4 * d[i] * b[i])) / (2 * d[i])
        w = y / y.sum()
        prc = w * (S @ w) / float(w @ S @ w)
        if np.max(np.abs(prc - b / b.sum())) < tol:
            return y, it
    return y, max_iter


def risk_budget_weights(S, budgets, *, method: str = "newton", max_iter: int = 500,
                        tol: float = 1e-24) -> np.ndarray:
    """Long-only weights whose percent risk contributions equal ``budgets``.

    Spinu (2013) convex formulation:  y* = argmin_{y>0} 1/2 y'Sy - sum_i b_i ln y_i.
    First-order condition y_i (S y)_i = b_i  =>  w = y*/sum(y*) has
    PRC_i = w_i (S w)_i / w'Sw = b_i.  Solved by damped Newton
    (method='newton', Hessian S + diag(b/y^2) is PD for PSD S) or cyclical
    coordinate descent (method='ccd', Griveau-Billion, Richard & Roncalli 2013:
    y_i = (-c_i + sqrt(c_i^2 + 4 S_ii b_i)) / (2 S_ii), c_i = sum_{j!=i} S_ij y_j).
    Zero budgets give zero weight (solved on the positive-budget subset).
    The result is verified: max |PRC - b| <= 1e-10 or OptimizationError."""
    S = _cov(S)
    b = as_vector(budgets, "budgets", n=S.shape[0])
    if np.any(b < 0) or b.sum() <= 0:
        raise ValidationError("budgets must be >= 0 with a positive sum")
    b = b / b.sum()
    pos = b > 0
    w = np.zeros_like(b)
    Sp, bp = S[np.ix_(pos, pos)], b[pos]
    if method == "newton":
        y, _ = _rb_newton(Sp, bp, max_iter, tol)
    elif method == "ccd":
        y, _ = _rb_ccd(Sp, bp, max(max_iter, 100_000), 1e-12)
    else:
        raise ValidationError(f"unknown method {method!r}")
    w[pos] = y / y.sum()
    prc = percent_risk_contributions(w, S)
    err = float(np.max(np.abs(prc - b)))
    if not np.isfinite(err) or err > RB_TOL:
        raise OptimizationError(f"risk budgeting failed verification: max |PRC - b| = {err:.3e}")
    return w


def erc(S, *, method: str = "newton") -> np.ndarray:
    """Equal risk contribution (risk parity): risk_budget_weights with b_i = 1/N."""
    n = validate_covariance(S).shape[0]
    return risk_budget_weights(S, np.full(n, 1.0 / n), method=method)


# --------------------------------------------------------------------------- #
# QP machinery (SLSQP + exact active-set polish + KKT verification)
# --------------------------------------------------------------------------- #
def _kkt_polish(Q, c, A, b, G, h, x, act_tol=1e-7):
    """Solve the equality-constrained QP on the active set exactly and accept
    it if primal feasible with non-negative inequality multipliers."""
    act = (G @ x >= h - act_tol) if G is not None else np.zeros(0, bool)
    Aeq = A if A is not None else np.zeros((0, len(x)))
    beq = b if b is not None else np.zeros(0)
    if G is not None and act.any():
        Aall = np.vstack([Aeq, G[act]])
        ball = np.concatenate([beq, h[act]])
    else:
        Aall, ball = Aeq, beq
    m = Aall.shape[0]
    K = np.block([[Q, Aall.T], [Aall, np.zeros((m, m))]])
    rhs = np.concatenate([-c, ball])
    sol, *_ = np.linalg.lstsq(K, rhs, rcond=None)
    xp, lam = sol[: len(x)], sol[len(x):]
    lam_ineq = lam[Aeq.shape[0]:]
    feas = True
    if A is not None:
        feas &= np.max(np.abs(A @ xp - b)) <= 1e-10
    if G is not None:
        feas &= np.all(G @ xp <= h + 1e-10)
    stat = np.linalg.norm(Q @ xp + c + Aall.T @ lam) <= 1e-9 * max(1.0, np.linalg.norm(c), np.linalg.norm(Q))
    if feas and stat and np.all(lam_ineq >= -1e-10):
        return xp
    return None


def _kkt_residual(Q, c, A, b, G, h, x) -> float:
    grad = Q @ x + c
    cols = []
    lo, hi = [], []
    if A is not None:
        cols.append(A.T)
        lo += [-np.inf] * A.shape[0]
        hi += [np.inf] * A.shape[0]
    if G is not None:
        act = G @ x >= h - 1e-7
        if act.any():
            cols.append(G[act].T)
            lo += [0.0] * int(act.sum())
            hi += [np.inf] * int(act.sum())
    if not cols:
        return float(np.linalg.norm(grad))
    M = np.hstack(cols)
    res = lsq_linear(M, -grad, bounds=(np.array(lo), np.array(hi)))
    return float(np.linalg.norm(M @ res.x + grad))


def solve_qp(Q, c, A_eq=None, b_eq=None, G=None, h=None, x0=None) -> np.ndarray:
    """min 1/2 x'Qx + c'x  s.t.  A_eq x = b_eq,  G x <= h   (Q PSD).

    SLSQP for the active set, then an exact KKT solve on that active set; the
    returned point is verified for feasibility (1e-9) and KKT stationarity with
    non-negative multipliers (lsq_linear residual <= 1e-6 scaled), else
    OptimizationError."""
    Q = np.asarray(Q, float)
    n = Q.shape[0]
    c = np.zeros(n) if c is None else np.asarray(c, float)
    scale = max(1e-300, float(np.max(np.abs(Q))), float(np.max(np.abs(c))) if c.size else 0.0)
    Qs, cs = Q / scale, c / scale
    cons = []
    if A_eq is not None:
        A_eq = np.atleast_2d(np.asarray(A_eq, float))
        b_eq = np.atleast_1d(np.asarray(b_eq, float))
        cons.append({"type": "eq", "fun": lambda x: A_eq @ x - b_eq, "jac": lambda x: A_eq})
    if G is not None:
        G = np.atleast_2d(np.asarray(G, float))
        h = np.atleast_1d(np.asarray(h, float))
        cons.append({"type": "ineq", "fun": lambda x: h - G @ x, "jac": lambda x: -G})
    if x0 is None:
        x0 = np.full(n, 1.0 / n)
    res = minimize(lambda x: 0.5 * x @ Qs @ x + cs @ x, x0, jac=lambda x: Qs @ x + cs,
                   constraints=cons, method="SLSQP", options={"ftol": 1e-16, "maxiter": 2000})
    x = res.x
    xp = _kkt_polish(Qs, cs, A_eq, b_eq, G, h, x)
    if xp is not None:
        return xp
    feas_eq = 0.0 if A_eq is None else float(np.max(np.abs(A_eq @ x - b_eq)))
    feas_in = 0.0 if G is None else float(np.max(G @ x - h, initial=0.0))
    kkt = _kkt_residual(Qs, cs, A_eq, b_eq, G, h, x)
    gscale = max(1.0, float(np.linalg.norm(Qs @ x + cs)))
    if feas_eq > 1e-9 or feas_in > 1e-9 or kkt > 1e-6 * gscale:
        raise OptimizationError(
            f"QP failed verification (status {res.status}: {res.message}); eq viol {feas_eq:.2e}, "
            f"ineq viol {feas_in:.2e}, KKT residual {kkt:.2e}")
    return x


def _bounds_as_G(n, lb, ub):
    rows, rhs = [], []
    if lb is not None:
        for i in range(n):
            if np.isfinite(lb[i]):
                r = np.zeros(n); r[i] = -1.0
                rows.append(r); rhs.append(-lb[i])
    if ub is not None:
        for i in range(n):
            if np.isfinite(ub[i]):
                r = np.zeros(n); r[i] = 1.0
                rows.append(r); rhs.append(ub[i])
    if not rows:
        return None, None
    return np.array(rows), np.array(rhs)


def _caps_vector(caps, n):
    if caps is None:
        return None
    c = np.full(n, float(caps)) if np.isscalar(caps) else as_vector(caps, "caps", n=n)
    if np.any(c <= 0):
        raise ValidationError("caps must be > 0")
    if c.sum() < 1 - 1e-12:
        raise ValidationError(f"caps sum to {c.sum():.4f} < 1: no fully-invested portfolio satisfies them")
    return c


# --------------------------------------------------------------------------- #
# optimisers
# --------------------------------------------------------------------------- #
def min_variance(S, *, long_only: bool = True, caps=None) -> np.ndarray:
    """Minimum-variance weights, 1'w = 1.  Unconstrained closed form
    w = S^{-1} 1 / (1' S^{-1} 1) (needs PD S); with long_only / caps a QP."""
    S = _cov(S)
    n = S.shape[0]
    cv = _caps_vector(caps, n)
    if not long_only and cv is None:
        validate_covariance(S, require_pd=True)
        x = np.linalg.solve(S, np.ones(n))
        return x / x.sum()
    G, h = _bounds_as_G(n, np.zeros(n) if long_only else None, cv)
    w = solve_qp(S, np.zeros(n), np.ones((1, n)), np.array([1.0]), G, h)
    return _clean(w)


def max_diversification(S, *, long_only: bool = True, caps=None) -> np.ndarray:
    """Most-diversified portfolio (Choueifaty & Coignard 2008): argmax DR(w).
    Unconstrained: w ∝ S^{-1} sigma.  Long-only: solve
        min y'Sy  s.t. sigma'y = 1, y >= 0, y_i <= cap_i 1'y,
    then w = y / 1'y (DR is scale-invariant, so this is exact)."""
    S = _cov(S)
    n = S.shape[0]
    sig = np.sqrt(np.diag(S))
    cv = _caps_vector(caps, n)
    if not long_only:
        if cv is not None:
            raise ValidationError("caps require long_only=True for max_diversification")
        validate_covariance(S, require_pd=True)
        x = np.linalg.solve(S, sig)
        return x / x.sum()
    rows = [-np.eye(n)]
    rhs = [np.zeros(n)]
    if cv is not None:
        rows.append(np.eye(n) - cv[:, None] * np.ones((1, n)))
        rhs.append(np.zeros(n))
    G, h = np.vstack(rows), np.concatenate(rhs)
    y0 = np.full(n, 1.0 / sig.sum())
    y = solve_qp(S, np.zeros(n), sig[None, :], np.array([1.0]), G, h, x0=y0)
    y = np.clip(y, 0.0, None)
    return _clean(y / y.sum())


def _clean(w, eps: float = 1e-12) -> np.ndarray:
    w = np.where(np.abs(w) < eps, 0.0, w)
    return w / w.sum()


def hrp(S, *, linkage_method: str = "single") -> np.ndarray:
    """Hierarchical Risk Parity (Lopez de Prado 2016, JPM 42(4)).
    1) d_ij = sqrt((1 - rho_ij)/2);  2) cluster on the Euclidean distance
    between columns of d (``linkage_method``, paper: single);  3) quasi-
    diagonalise (dendrogram leaf order);  4) recursive bisection of the ordered
    list: split in halves, cluster variance V = w_ivp' S_c w_ivp with inverse-
    variance weights inside the cluster, alpha = 1 - V_1/(V_1 + V_2) to the
    first half.  For diagonal S the result is the inverse-variance portfolio."""
    S = _cov(S)
    n = S.shape[0]
    if n == 1:
        return np.ones(1)
    sig = np.sqrt(np.diag(S))
    C = np.clip(S / np.outer(sig, sig), -1.0, 1.0)
    D = np.sqrt(np.clip(0.5 * (1.0 - C), 0.0, None))
    Z = linkage(pdist(D), method=linkage_method)
    order = leaves_list(Z).tolist()
    w = np.ones(n)

    def cvar(idx):
        Sc = S[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(Sc)
        iv /= iv.sum()
        return float(iv @ Sc @ iv)

    clusters = [order]
    while clusters:
        nxt = []
        for cl in clusters:
            if len(cl) <= 1:
                continue
            half = len(cl) // 2
            a, b = cl[:half], cl[half:]
            va, vb = cvar(a), cvar(b)
            alpha = 1.0 - va / (va + vb)
            w[a] *= alpha
            w[b] *= 1.0 - alpha
            nxt += [a, b]
        clusters = nxt
    return w / w.sum()


# --------------------------------------------------------------------------- #
# constraints and gearing
# --------------------------------------------------------------------------- #
def apply_caps(w, caps) -> np.ndarray:
    """Water-filling cap: clip w_i at cap_i and redistribute the excess to the
    uncapped names pro rata to their weights, repeating until no cap binds.
    For long-only weights summing to 1.  Note: a capped ERC/HRP is no longer
    exactly risk-balanced; the scorecard reports the resulting PRCs."""
    w = as_vector(w, "weights")
    if np.any(w < -1e-12) or abs(w.sum() - 1) > 1e-9:
        raise ValidationError("apply_caps needs long-only weights summing to 1")
    cv = _caps_vector(caps, len(w))
    w = np.clip(w, 0.0, None)
    for _ in range(len(w) + 1):
        over = w > cv + 1e-15
        if not over.any():
            return w / w.sum()
        excess = float(np.sum(w[over] - cv[over]))
        w[over] = cv[over]
        free = w < cv - 1e-15
        if not free.any() or w[free].sum() <= 0:
            raise ValidationError("caps infeasible: no uncapped weight left to absorb the excess")
        w[free] += excess * w[free] / w[free].sum()
    return w / w.sum()


@dataclass
class GearingResult:
    """Output of target_vol_gearing."""
    weights: np.ndarray       # geared risky weights (sum = leverage * sum(w))
    leverage: float           # L applied
    ex_ante_vol: float        # sigma_p of the geared book
    unlevered_vol: float      # sigma_p of the input weights
    cash_weight: float        # 1 - sum(geared weights); < 0 means borrowing
    cap_binding: bool         # True if max_leverage limited L


def target_vol_gearing(w, S, target_vol: float, *, max_leverage: float = math.inf) -> GearingResult:
    """Gear weights to a target volatility: L = sigma* / sigma_p(w), capped so
    that gross exposure L * sum|w| <= max_leverage.  Geared weights L w; the
    remainder 1 - L sum(w) is cash (earns rf) or, if negative, borrowing (pays
    rf + spread in the backtest / geared_return)."""
    S = validate_covariance(S)
    w = as_vector(w, "weights", n=S.shape[0])
    sp = portfolio_vol(w, S)
    if sp <= 0:
        raise ValidationError("cannot gear a zero-volatility portfolio")
    if target_vol <= 0:
        raise ValidationError("target_vol must be > 0")
    L = target_vol / sp
    gross = float(np.sum(np.abs(w)))
    cap = max_leverage / gross if gross > 0 else math.inf
    binding = L > cap
    L = min(L, cap)
    wg = L * w
    return GearingResult(wg, float(L), float(L * sp), float(sp), float(1.0 - wg.sum()), bool(binding))


# --------------------------------------------------------------------------- #
# environment (quadrant) balance
# --------------------------------------------------------------------------- #
@dataclass
class QuadrantBalanceResult:
    """quadrant_balance output: weights, risk budgets b, box risk shares M'PRC, box names."""
    weights: np.ndarray
    budgets: np.ndarray
    box_shares: np.ndarray
    boxes: list


def quadrant_balance(S, exposures, boxes=None) -> QuadrantBalanceResult:
    """Equal risk per environment box (All Weather: 25% risk each to growth up,
    growth down, inflation up, inflation down).

    ``exposures`` M is (N x K), M_ik >= 0 = share of stream i's risk attributed
    to box k (rows sum to 1, or 0 for unmapped streams, which get zero weight).
    Risk budgets b solve  min ||b - u||^2  s.t. M'b = 1/K, b >= 0  (u uniform
    over mapped streams); then w = risk_budget_weights(S, b), so box risk
    shares M' PRC = 1/K exactly.  Raises if a box has no stream (infeasible)."""
    S = _cov(S)
    M = np.asarray(exposures, float)
    n = S.shape[0]
    if M.ndim != 2 or M.shape[0] != n:
        raise ValidationError(f"exposures must be (N={n}, K)")
    if np.any(M < 0) or not np.all(np.isfinite(M)):
        raise ValidationError("exposures must be finite and >= 0")
    rs = M.sum(axis=1)
    if np.any((rs > 1e-12) & (np.abs(rs - 1) > 1e-9)):
        raise ValidationError("each mapped stream's exposures must sum to 1")
    K = M.shape[1]
    boxes = list(boxes) if boxes is not None else [f"box{k}" for k in range(K)]
    empty = [boxes[k] for k in range(K) if M[:, k].sum() <= 0]
    if empty:
        raise OptimizationError(f"environment balance infeasible: no stream exposed to {empty}")
    mapped = rs > 0
    Mm = M[mapped]
    m = int(mapped.sum())
    u = np.full(m, 1.0 / m)
    G, h = -np.eye(m), np.zeros(m)
    bm = solve_qp(np.eye(m), -u, Mm.T, np.full(K, 1.0 / K), G, h, x0=u)
    bm = np.clip(bm, 0.0, None)
    if np.max(np.abs(Mm.T @ bm - 1.0 / K)) > 1e-8:
        raise OptimizationError("environment balance infeasible with these exposures")
    b = np.zeros(n)
    b[mapped] = bm
    b[b < 1e-12] = 0.0
    w = risk_budget_weights(S, b)
    prc = percent_risk_contributions(w, S)
    return QuadrantBalanceResult(w, b / b.sum(), M.T @ prc, boxes)


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
ALLOCATORS: dict[str, Callable] = {
    "equal_weight": equal_weight,
    "inverse_vol": inverse_vol,
    "inverse_variance": inverse_variance,
    "erc": erc,
    "min_variance": min_variance,
    "max_diversification": max_diversification,
    "hrp": hrp,
}


def get_allocator(name: str) -> Callable:
    """Look up an allocator by name (raises with the valid list)."""
    try:
        return ALLOCATORS[name]
    except KeyError:
        raise ValidationError(f"unknown allocator {name!r}; choose from {sorted(ALLOCATORS)}") from None
