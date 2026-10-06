import numpy as np
import pandas as pd
import pytest

from holygrail import robustness as R
from holygrail.core import effective_bets


def _iid(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    C = np.array([[1, .3, .1, .0], [.3, 1, .2, .1], [.1, .2, 1, .4], [.0, .1, .4, 1]])
    sig = np.array([0.01, 0.008, 0.012, 0.006])
    S = C * np.outer(sig, sig)
    X = rng.multivariate_normal(np.full(4, 0.0003), S, size=n)
    return pd.DataFrame(X, index=pd.bdate_range("2015-01-01", periods=n), columns=list("abcd")), S


def test_bootstrap_ci_deterministic_and_covers_truth():
    df, S = _iid()
    w = np.full(4, 0.25)
    a = R.bootstrap_neff_sharpe(df, w, periods_per_year=252, n_boot=300, seed=1)
    b = R.bootstrap_neff_sharpe(df, w, periods_per_year=252, n_boot=300, seed=1)
    assert a == b
    assert a["sharpe"]["lo"] < a["sharpe"]["point"] < a["sharpe"]["hi"]
    assert a["n_ok"] == 300
    # frequentist check: the 90% interval covers the true DR^2 in ~90% of samples
    true = effective_bets(w, S).dr2
    hits = 0
    for s in range(20):
        d, _ = _iid(seed=s + 10)
        ci = R.bootstrap_neff_sharpe(d, w, periods_per_year=252, n_boot=200, seed=s)["dr2"]
        hits += ci["lo"] <= true <= ci["hi"]
    assert hits >= 15


def test_neff_sensitivity_monotone():
    df, S = _iid()
    rows = R.neff_sensitivity(np.full(4, 0.25), S * 252)
    base = [r for r in rows if r["delta_rho"] == 0][0]
    assert base["dr2"] == pytest.approx(effective_bets(np.full(4, 0.25), S).dr2)
    dr2 = [r["dr2"] for r in rows]
    assert all(x >= y - 1e-12 for x, y in zip(dr2, dr2[1:]))
    big = R.neff_sensitivity(np.full(4, 0.25), S * 252, deltas=(-0.6,))
    assert big[0]["repaired"]


def test_stress_mask_and_regime_correlations():
    idx = pd.bdate_range("2020-01-01", periods=300)
    p = pd.Series(100.0, index=idx)
    p.iloc[100:130] = np.linspace(100, 80, 30)
    p.iloc[130:] = 80.0
    vix = pd.Series(15.0, index=idx); vix.iloc[250:260] = 40
    m = R.stress_mask(p, vix=vix)
    assert not m.iloc[:105].any() and m.iloc[125] and m.iloc[255]
    rng = np.random.default_rng(0)
    f = rng.normal(0, 0.01, 300)
    stress = m.to_numpy()
    a = f + rng.normal(0, 0.01, 300)
    b = np.where(stress, f, 0) + rng.normal(0, 0.01, 300) * np.where(stress, 0.2, 1)
    out = R.regime_correlations(pd.DataFrame({"a": a, "b": b}, index=idx), m)
    assert out["mean_rho_stress"] > out["mean_rho_calm"] + 0.3
    assert out["n_stress"] == int(m.sum())


def test_rolling_and_shrinkage_comparison():
    df, S = _iid(n=600)
    rc = R.rolling_correlation(df, 60)
    assert rc.shape[1] == 6 and rc.iloc[59:].notna().all().all()
    rn = R.rolling_neff(df, np.full(4, 0.25), 120)
    assert len(rn) == 600 - 120 + 1 and (rn["dr2"] >= 1).all()
    rows = R.shrinkage_comparison(df, np.full(4, 0.25), periods_per_year=252)
    assert [r["estimator"] for r in rows] == ["sample", "lw_identity", "lw_constant_corr", "ewma"]
    assert all(r["condition_number"] >= 1 for r in rows)
