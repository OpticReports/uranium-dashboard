"""Probit MLE + horizon model tests. We generate data from a KNOWN probit and
check the fitter recovers the coefficients, the CI brackets the truth, and AUC is
sensible."""
import math
from datetime import date

from app.metrics.recession_model import (
    _Phi, auc, build_dataset, build_models, fit_probit, predict,
)


def _synth(b0: float, b1: float, n: int = 4000):
    """Deterministic dataset drawn from Phi(b0+b1*x). No RNG (seedless env) — use a
    fine grid of x with the expected label frequency realized via a threshold ramp."""
    xs, ys = [], []
    for i in range(n):
        x = -3.0 + 6.0 * (i / (n - 1))          # sweep spread in [-3, 3]
        p = _Phi(b0 + b1 * x)
        # realize `p` deterministically: emit ceil(p*K) positives out of K copies
        K = 20
        pos = round(p * K)
        for k in range(K):
            xs.append(x)
            ys.append(1 if k < pos else 0)
    return xs, ys


def test_probit_recovers_known_coefficients():
    xs, ys = _synth(-0.5333, -0.6330)
    b0, b1, cov = fit_probit(xs, ys)
    assert abs(b0 - (-0.5333)) < 0.08
    assert abs(b1 - (-0.6330)) < 0.08
    assert cov[0][0] > 0 and cov[1][1] > 0        # positive variances


def test_predict_ci_brackets_point_and_orders():
    xs, ys = _synth(-0.5333, -0.6330)
    b0, b1, cov = fit_probit(xs, ys)
    r = predict(b0, b1, cov, spread=0.0)
    assert r["ci_low_pct"] <= r["probability_pct"] <= r["ci_high_pct"]
    # near spread 0 the Estrella-Mishkin prob is ~30%
    assert 25.0 < r["probability_pct"] < 35.0
    # more inverted -> higher probability
    assert predict(b0, b1, cov, -1.0)["probability_pct"] > r["probability_pct"]


def test_auc_of_a_good_model_exceeds_half():
    xs, ys = _synth(-0.5333, -0.6330)  # negative b1 => inverted curve predicts recession
    a = auc(xs, ys)
    assert a is not None and a > 0.6


def test_build_dataset_labels_within_horizon():
    # spread monthly for 4 months; recession in month index (2024,4)
    sm = {(2024, 1): 0.5, (2024, 2): 0.4, (2024, 3): -0.1}
    um = {(2024, 1): 0, (2024, 2): 0, (2024, 3): 0, (2024, 4): 1, (2024, 5): 1}
    xs, ys = build_dataset(sm, um, horizon=2)
    # (2024,1): looks at Feb,Mar -> no recession -> 0
    # (2024,2): looks at Mar,Apr -> Apr=1 -> 1
    # (2024,3): looks at Apr,May -> 1
    assert ys == [0, 1, 1]
    assert xs == [0.5, 0.4, -0.1]


def test_build_models_empty_on_no_data():
    assert build_models([], [], [], []) == {}


def test_build_models_fits_horizons_from_synthetic_series():
    # 40 years of monthly data; a recession every ~10 years lasting 12 months,
    # preceded by an inverted spread (so the curve is predictive).
    sdates, svals, udates, uvals = [], [], [], []
    for i in range(480):  # 480 months
        y, m = 1985 + i // 12, i % 12 + 1
        d = date(y, m, 1)
        in_rec = (i % 120) >= 108  # last 12 months of each 10y block
        pre_rec = 96 <= (i % 120) < 108  # inversion ~12mo before
        sdates.append(d); svals.append(-0.5 if pre_rec else 1.0)
        udates.append(d); uvals.append(1.0 if in_rec else 0.0)
    models = build_models(sdates, svals, udates, uvals)
    assert 12 in models
    assert models[12]["auc"] is not None and models[12]["auc"] > 0.5
