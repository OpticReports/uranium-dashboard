"""Stage 3 — vectorized Monte Carlo residual engine (spec §4.4, amendment A6).

10k paths x 11 monthly steps, fully vectorized across paths (no Python path
loops — the only loop is over the 11 months, which carries the state machine).
Shocks: Student-t ν=4 via a t-COPULA (A6: shared χ² mixing variable across
assets — Gaussian copula understated joint 5th-pct co-crash by 29% at ρ=0.6).
Antithetic variates on the Gaussian layer (Z and −Z share the same mixing W
and the same transition uniforms, so pairs traverse identical regime draws).
"""
from __future__ import annotations

import numpy as np

from .equity_engine import EQUITY_ASSETS, crack_log_monthly, equity_drift_det
from .hyg_engine import hyg_idio_sigma, hyg_vol_monthly, theta_normal_path
from .rate_paths import MONTHS, N_MONTHS, build_paths, rate_legs

ASSETS = ("SPX", "QQQ", "SOXX", "HYG")
PCTS = (5, 25, 50, 75, 95)


def _apply_copula(z_m: np.ndarray, w_m: np.ndarray, chol: np.ndarray,
                  nu: float) -> np.ndarray:
    """One month of correlated unit-variance t shocks: (z @ chol.T) / sqrt(W)
    / sqrt(nu/(nu-2)). Extracted so tests can pin variance/correlation on the
    REAL code path (QA finding 3: the old test was a sham)."""
    return (z_m @ chol.T) / np.sqrt(w_m) / np.sqrt(nu / (nu - 2.0))


def _chol(rho_eq: float, rho_x: float) -> np.ndarray:
    """4x4 correlation (SPX,QQQ,SOXX,HYG): equities pairwise rho_eq, each
    equity vs HYG rho_x. Repaired to nearest PSD if needed."""
    c = np.full((4, 4), rho_eq)
    np.fill_diagonal(c, 1.0)
    c[3, :3] = c[:3, 3] = rho_x
    try:
        return np.linalg.cholesky(c)
    except np.linalg.LinAlgError:
        w, v = np.linalg.eigh(c)
        c2 = (v * np.clip(w, 1e-6, None)) @ v.T
        d = np.sqrt(np.diag(c2))
        return np.linalg.cholesky(c2 / np.outer(d, d))


def simulate(hikes: int, params: dict[str, float], inputs: dict,
             seed: int = 42) -> dict:
    """inputs: {vix, move, hyg_realized_ann, oas0, canary01, d_acm_tp_6m,
    surprise_override_bp?: list[11]} — all optional except none required
    (sane fallbacks). Returns bands/probs/meta per spec §5."""
    rng = np.random.default_rng(seed)
    n = int(params["n_paths"])
    half = max(n // 2, 1)
    n = half * 2
    nu = params["t_nu"]

    # ---- Stage 1 ----
    paths = build_paths(hikes, params)
    if inputs.get("surprise_override_bp") is not None:
        s = np.asarray(inputs["surprise_override_bp"], dtype=float)
        if s.shape != (N_MONTHS,):
            raise ValueError(f"surprise_override_bp must have {N_MONTHS} entries")
        paths["surprise_bp"] = s
        paths["cum_surprise_bp"] = np.cumsum(s)
        paths["surprise_hikes"] = s / 25.0
    kappa = inputs.get("kappa")
    if kappa is None:
        from .params import registry
        from .rate_paths import kappa_live
        lo, hi = registry()["kappa_base"]["range"]
        kappa = kappa_live(params["kappa_base"], params["kappa_tp_coeff"],
                           inputs.get("d_acm_tp_6m"), (float(lo), float(hi)))
    dy10_pp, dreal_pp = rate_legs(paths["surprise_bp"], kappa, params["rho_real"])

    # ---- Stage 2 deterministic pieces ----
    oas0 = float(inputs.get("oas0") or params["oas_theta_normal"])
    theta_n = theta_normal_path(paths["priced_hikes"], paths["surprise_hikes"],
                                params, oas0)
    eq_drift = equity_drift_det(dreal_pp, params)
    crack = crack_log_monthly(params)

    vix = inputs.get("vix")
    sig_eq_m = ((vix if vix is not None else 18.0) * params["vix_haircut"]
                / 100.0) / np.sqrt(12.0)
    hyg_blend_m = hyg_vol_monthly(inputs.get("move"),
                                  inputs.get("hyg_realized_ann"), params)
    canary = float(np.clip(inputs.get("canary01") if inputs.get("canary01")
                           is not None else 0.3, 0.0, 1.0))

    # CS with transition lag (spec 4.3)
    lag = int(round(params["cs_lag_months"]))
    cs = paths["cum_surprise_bp"]
    cs_lagged = np.concatenate([np.zeros(lag), cs])[:N_MONTHS]

    # ---- shock tensors (antithetic on Z; shared W and uniforms per pair) ----
    chol_n = _chol(params["eq_corr"], params["corr_normal"])
    chol_s = _chol(params["eq_corr"], params["corr_stress"])
    z_half = rng.standard_normal((N_MONTHS, half, 4))
    z = np.concatenate([z_half, -z_half], axis=1)              # (11, n, 4)
    w_half = rng.chisquare(nu, (N_MONTHS, half, 1)) / nu
    w = np.concatenate([w_half, w_half], axis=1)               # shared mixing
    u_half = rng.random((2, N_MONTHS, half))
    u = np.concatenate([u_half, u_half], axis=2)               # (2, 11, n)

    # ---- state machine over months (vectorized across paths) ----
    in_stress = np.zeros(n, dtype=bool)
    ever_entered = np.zeros(n, dtype=bool)
    since_entry = np.full(n, 99)
    oas = np.full(n, oas0)
    log_eq = {a: np.zeros(n) for a in EQUITY_ASSETS}
    hyg_idx = np.full(n, 1.0)
    idx_hist = {a: np.empty((N_MONTHS, n)) for a in ASSETS}
    stress_share = np.empty(N_MONTHS)

    for m in range(N_MONTHS):
        # transitions (entry uses lagged CS + canary composite)
        p_enter = 1.0 / (1.0 + np.exp(-(params["logistic_a"]
                                        + params["logistic_b"] * cs_lagged[m] / 100.0
                                        + params["logistic_c"] * canary)))
        entering = (~in_stress) & (u[0, m] < p_enter)
        # QA finding 1: the capex-crack and OAS entry jump are ONE-TIME cycle
        # events — re-entries after a brief exit must not re-fire them (they
        # made softer stress DEEPEN the median, an economically backwards
        # sensitivity, and inflated G1 with ~2 cracks/path).
        first_entry = entering & ~ever_entered
        ever_entered = ever_entered | entering
        exiting = in_stress & (u[1, m] < params["stress_exit_monthly"])
        in_stress = (in_stress | entering) & ~exiting
        since_entry = np.where(first_entry, 0, since_entry)

        # correlated t shocks for this month, state-dependent correlation
        tn = _apply_copula(z[m], w[m], chol_n, nu)
        ts = _apply_copula(z[m], w[m], chol_s, nu)
        shock = np.where(in_stress[:, None], ts, tn)           # (n, 4)

        # OAS evolution (per path): mean-revert to state theta + entry jump;
        # innovation sign: shock>0 = risk-on = spreads tighten
        # QA finding 5: in big-surprise scenarios the grinding normal
        # attractor can exceed theta_stress, making stress spread-TIGHTENING;
        # the stress attractor keeps a premium over wherever normal has ground.
        theta_stress_eff = max(params["oas_theta_stress"],
                               theta_n[m] + params["oas_stress_premium"])
        theta = np.where(in_stress, theta_stress_eff, theta_n[m])
        sig_sp = np.where(in_stress, params["oas_sig_stress"],
                          params["oas_sig_normal"])
        d_oas = (params["oas_mr_speed"] * (theta - oas)
                 + params["oas_jump_entry"] * first_entry
                 - sig_sp * shock[:, 3])
        oas = np.clip(oas + d_oas, 50.0, 2500.0)

        # HYG return: duration leg (scenario-deterministic) + spread leg +
        # carry + idiosyncratic residual topping vol up to the blend target
        # QA finding 2: per-PATH residual top-up — the old cross-path mean
        # starved normal-state paths of 39% of their vol when stress share
        # was high.
        sig_idio = hyg_idio_sigma(hyg_blend_m, sig_sp, params)
        r_hyg = (-params["hyg_duration"] * dy10_pp[m] / 100.0
                 - params["hyg_spread_dur"] * d_oas / 1e4
                 + params["hyg_carry"] / 12.0
                 + sig_idio * shock[:, 3])
        hyg_idx = hyg_idx * (1.0 + r_hyg)
        idx_hist["HYG"][m] = hyg_idx

        # equities: det drift + crack phasing + vol (stress multiplier)
        vol_mult = np.where(since_entry < params["stress_vol_months"],
                            params["stress_vol_mult"], 1.0)
        in_crack = since_entry < params["crack_months"]
        for j, a in enumerate(EQUITY_ASSETS):
            dlog = (eq_drift[a][m]
                    + np.where(in_crack, crack[a], 0.0)
                    + sig_eq_m * vol_mult * shock[:, j])
            log_eq[a] = log_eq[a] + dlog
            idx_hist[a][m] = np.exp(log_eq[a])

        since_entry += 1
        stress_share[m] = float(np.mean(in_stress))

    # ---- outputs ----
    bands, probs, terminal = {}, {}, {}
    for a in ASSETS:
        hist = idx_hist[a] * 100.0                            # start = 100
        bands[a] = {str(p): np.round(np.percentile(hist, p, axis=1), 2).tolist()
                    for p in PCTS}
        peak = np.maximum.accumulate(
            np.vstack([np.full((1, n), 100.0), hist]), axis=0)
        dd = hist / peak[1:] - 1.0
        max_dd = dd.min(axis=0)
        probs[a] = {"dd_gt_10": round(float(np.mean(max_dd < -0.10)), 4),
                    "dd_gt_20": round(float(np.mean(max_dd < -0.20)), 4)}
        counts, edges = np.histogram(hist[-1], bins=21)
        terminal[a] = {"counts": counts.tolist(),
                       "edges": np.round(edges, 1).tolist()}

    return {
        "months": list(MONTHS),
        "bands": bands,
        "probs": probs,
        "terminal": terminal,
        "stress_prob": np.round(stress_share, 4).tolist(),
        "rate_path": {
            "implied_bp": paths["implied_bp"].tolist(),
            "scenario_bp": paths["scenario_bp"].tolist(),
            "cum_surprise_bp": paths["cum_surprise_bp"].tolist(),
            "dy10_pp": np.round(dy10_pp, 4).tolist(),
        },
        "meta": {"kappa_used": round(float(kappa), 3), "seed": seed,
                 "n_paths": n, "sig_eq_monthly": round(float(sig_eq_m), 5),
                 "sig_hyg_monthly": round(float(hyg_blend_m), 5),
                 "canary01": canary, "oas0": oas0, "hikes": hikes},
    }
