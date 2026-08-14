"""HYG module (spec §4.2, amendments A2/A3): duration leg + OAS regime terms.

ΔP/P = −D·Δy_treas − SD·ΔOAS + carry·dt. The OAS state machine itself runs in
mc_core (it is per-path stochastic); this module supplies the deterministic
pieces: the normal-state theta path (priced-hike tightening with late-cycle
taper + surprise-hike widening drift) and the vol-blend arithmetic.
"""
from __future__ import annotations

import numpy as np


def theta_normal_path(priced_hikes: np.ndarray, surprise_hikes: np.ndarray,
                      params: dict[str, float], theta0: float) -> np.ndarray:
    """Normal-state OAS attractor per month (bp). Priced hikes tighten it
    (−4bp each, A2) tapering to zero once cumulative delivered hikes reach
    oas_taper_hikes; surprise hikes widen it (+15bp each, symmetric for
    surprise cuts — A3 shows this drift term IS the 2022 grind)."""
    cum_delivered = np.cumsum(np.abs(priced_hikes) + np.clip(surprise_hikes, 0, None))
    taper = np.clip(1.0 - cum_delivered / max(params["oas_taper_hikes"], 1e-9), 0.0, 1.0)
    d_priced = params["oas_dtheta_priced"] * priced_hikes * taper
    d_surprise = params["oas_dtheta_surprise"] * surprise_hikes
    return theta0 + np.cumsum(d_priced + d_surprise)


def hyg_vol_monthly(move_level: float | None, realized_ann: float | None,
                    params: dict[str, float]) -> float:
    """Monthly HYG return vol from blend(w·MOVE-mapped, (1−w)·realized 60d).
    MOVE-mapped: duration × MOVE(bp/yr)/1e4 ≈ annualized price vol from rates.
    Falls back to whichever input exists; last-resort 8% annualized."""
    w = params["hyg_vol_w_move"]
    parts = []
    if move_level is not None:
        parts.append((w, params["hyg_duration"] * move_level / 1e4))
    if realized_ann is not None:
        parts.append((1.0 - w if move_level is not None else 1.0, realized_ann))
    if not parts:
        return 0.08 / np.sqrt(12.0)
    tot_w = sum(p[0] for p in parts)
    ann = sum(w_ * v for w_, v in parts) / max(tot_w, 1e-9)
    return float(ann / np.sqrt(12.0))


def hyg_idio_sigma(blend_monthly: float, sigma_spread_bp,
                   params: dict[str, float]):
    """Per-PATH residual (QA finding 2): the OAS innovation already produces
    SD·σ_spread of price vol on each path; the idiosyncratic residual tops
    each path up to the blend target (floored at zero). Linear, not
    quadrature, because the residual reuses the same shock draw. Accepts a
    scalar or an (n,) array of per-path spread sigmas."""
    spread_leg = params["hyg_spread_dur"] * np.asarray(sigma_spread_bp) / 1e4
    return np.maximum(blend_monthly - spread_leg, 0.0)
