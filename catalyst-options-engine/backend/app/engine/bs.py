"""Black-Scholes pricing + implied-vol solver. Pure functions, no I/O.

Conventions:
  * S spot, K strike, T years to expiry, sigma annualized vol, r continuous
    risk-free rate (default 0 — a deliberate simplification for short-dated
    event structures; documented in the README honesty notes).
  * implied_vol() is a bisection bounded to sigma in [0.01, 5.0] and returns
    None whenever the target price is unsolvable in that band (below intrinsic,
    above the sigma=5 price, bad inputs). NEVER a silent default.
"""
from __future__ import annotations

import math

IV_LO = 0.01
IV_HI = 5.0
_TOL = 1e-8
_MAX_ITER = 200


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float, r: float = 0.0,
             kind: str = "call") -> float:
    """Black-Scholes European option price. T<=0 or sigma<=0 -> intrinsic."""
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive")
    if T <= 0 or sigma <= 0:
        # Expired / zero-vol: discounted intrinsic (plain intrinsic at r=0).
        disc_k = K * math.exp(-r * max(T, 0.0))
        return max(S - disc_k, 0.0) if kind == "call" else max(disc_k - S, 0.0)
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if kind == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_straddle(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    return (bs_price(S, K, T, sigma, r, "call") + bs_price(S, K, T, sigma, r, "put"))


def implied_vol(price: float, S: float, K: float, T: float, r: float = 0.0,
                kind: str = "call") -> float | None:
    """Bisection IV solver bounded to [0.01, 5.0]. None when unsolvable."""
    if price is None or price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    lo_price = bs_price(S, K, T, IV_LO, r, kind)
    hi_price = bs_price(S, K, T, IV_HI, r, kind)
    # Price must be bracketed by the band; otherwise unsolvable — return None
    # (a price below intrinsic, or absurdly high, must never yield a made-up IV).
    if price < lo_price - _TOL or price > hi_price + _TOL:
        return None
    lo, hi = IV_LO, IV_HI
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        pm = bs_price(S, K, T, mid, r, kind)
        if abs(pm - price) < _TOL:
            return mid
        if pm < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)
