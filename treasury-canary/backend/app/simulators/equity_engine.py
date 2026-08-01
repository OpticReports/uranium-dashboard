"""Equity module (spec §4.3, amendment A4): real-yield duration beta +
capex-crack regime jump. Deterministic drift pieces; stress application is
per-path in mc_core.
"""
from __future__ import annotations

import numpy as np

EQUITY_ASSETS = ("SPX", "QQQ", "SOXX")


def equity_drift_det(dreal_pp: np.ndarray, params: dict[str, float]
                     ) -> dict[str, np.ndarray]:
    """Monthly deterministic Δlog per asset: total-return baseline /12 minus
    β_dur × real-yield surprise (β is % per 100bp = per pp; A4 amended
    values 8/11/14)."""
    out = {}
    for asset, bkey, dkey in (("SPX", "beta_spx", "drift_spx"),
                              ("QQQ", "beta_qqq", "drift_qqq"),
                              ("SOXX", "beta_soxx", "drift_soxx")):
        beta = params[bkey] / 100.0     # per pp -> log-return fraction
        out[asset] = params[dkey] / 12.0 - beta * dreal_pp
    return out


def crack_log_monthly(params: dict[str, float]) -> dict[str, float]:
    """Per-month log shock while the capex crack is phasing (total log move
    spread over crack_months)."""
    months = max(params["crack_months"], 1.0)
    return {"SPX": float(np.log1p(params["crack_spx"]) / months),
            "QQQ": float(np.log1p(params["crack_qqq"]) / months),
            "SOXX": float(np.log1p(params["crack_soxx"]) / months)}
