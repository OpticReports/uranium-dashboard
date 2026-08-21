"""Black-Scholes + IV solver: round-trips and edge cases."""
from __future__ import annotations

import math

import pytest

from app.engine.bs import IV_HI, IV_LO, bs_price, bs_straddle, implied_vol


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("sigma", [0.15, 0.5, 1.0, 2.5])
@pytest.mark.parametrize("moneyness", [0.9, 1.0, 1.1])
def test_iv_round_trip(kind, sigma, moneyness):
    S, T = 100.0, 45 / 365
    K = S * moneyness
    price = bs_price(S, K, T, sigma, kind=kind)
    iv = implied_vol(price, S, K, T, kind=kind)
    assert iv is not None
    assert abs(iv - sigma) < 1e-4
    # price -> iv -> price round trip
    assert abs(bs_price(S, K, T, iv, kind=kind) - price) < 1e-6


def test_known_value():
    # S=100 K=100 T=1 sigma=0.2 r=0: canonical BS call ~7.9656
    assert abs(bs_price(100, 100, 1.0, 0.2) - 7.9656) < 1e-3


def test_put_call_parity():
    S, K, T, sigma = 105.0, 100.0, 0.25, 0.6
    c = bs_price(S, K, T, sigma, kind="call")
    p = bs_price(S, K, T, sigma, kind="put")
    assert abs((c - p) - (S - K)) < 1e-9  # r=0


def test_expired_and_zero_vol_are_intrinsic():
    assert bs_price(120, 100, 0.0, 0.5, kind="call") == 20.0
    assert bs_price(120, 100, 0.5, 0.0, kind="put") == 0.0
    assert bs_price(90, 100, 0.0, 0.5, kind="put") == 10.0


def test_iv_unsolvable_below_intrinsic_returns_none():
    # Deep ITM call quoted BELOW intrinsic: no vol can produce it.
    assert implied_vol(price=5.0, S=120.0, K=100.0, T=0.1, kind="call") is None


def test_iv_unsolvable_above_band_returns_none():
    # Price above even sigma=5.0 -> None, never a clamped guess.
    too_high = bs_price(100, 100, 0.1, IV_HI) + 1.0
    assert implied_vol(too_high, 100, 100, 0.1, kind="call") is None


def test_iv_bad_inputs_return_none():
    assert implied_vol(0.0, 100, 100, 0.1) is None
    assert implied_vol(-1.0, 100, 100, 0.1) is None
    assert implied_vol(5.0, 100, 100, 0.0) is None
    assert implied_vol(None, 100, 100, 0.1) is None


def test_iv_bounds_solvable_at_edges():
    lo_price = bs_price(100, 100, 0.2, IV_LO)
    iv = implied_vol(lo_price, 100, 100, 0.2)
    assert iv is not None and abs(iv - IV_LO) < 1e-3


def test_straddle_is_call_plus_put():
    S, K, T, sigma = 100.0, 100.0, 30 / 365, 1.0
    assert math.isclose(
        bs_straddle(S, K, T, sigma),
        bs_price(S, K, T, sigma, kind="call") + bs_price(S, K, T, sigma, kind="put"))
