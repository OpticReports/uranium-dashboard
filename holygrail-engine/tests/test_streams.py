"""Streams, assumptions, exposures and the joint moment model."""
import math

import numpy as np
import pandas as pd
import pytest

from holygrail.errors import AssumptionError, UnknownStreamError, ValidationError
from holygrail.streams import (Assumption, CashStream, CompositeStream, DefaultModel, MarketStream, ParametricStream,
                               SeriesStream, Universe, build_moments)

A = lambda v, c="medium": {"value": v, "source": "test", "confidence": c}  # noqa: E731


def test_assumption_requires_source_and_confidence():
    assert Assumption.parse(A(0.05)).value == 0.05
    with pytest.raises(AssumptionError, match="bare"):
        Assumption.parse(0.05)
    with pytest.raises(AssumptionError, match="missing"):
        Assumption.parse({"value": 0.05, "source": "x"})
    with pytest.raises(AssumptionError, match="confidence"):
        Assumption.parse({"value": 0.05, "source": "x", "confidence": "sure"})
    with pytest.raises(AssumptionError, match="source"):
        Assumption(0.05, " ", "low")
    with pytest.raises(AssumptionError):
        Assumption(float("nan"), "x", "low")


def _hist(n=520, seed=0):
    rng = np.random.default_rng(seed)
    L = np.array([[0.02, 0, 0], [0.008, 0.015, 0], [-0.004, 0.002, 0.01]])
    X = rng.normal(0.001, 1, (n, 3)) @ L.T
    return pd.DataFrame(X, index=pd.date_range("2016-01-01", periods=n, freq="W-FRI"), columns=["EQ", "HY", "BD"])


def _uni(**extra):
    s = [MarketStream(name="EQ", symbol="EQ"), MarketStream(name="HY", symbol="HY"), MarketStream(name="BD", symbol="BD"),
         CashStream(name="cash")]
    return Universe(s + list(extra.values()))


def test_composite_exposure_leverage_and_fee():
    lev = CompositeStream(name="L3", components={"EQ": 1.0}, leverage=3.0, financing_spread=A(0.004), fee=A(0.009))
    u = _uni(lev=lev)
    e = u.exposure("L3")
    assert e.coefs == {"EQ": 3.0} and e.rf_coef == pytest.approx(-2.0)
    assert e.const == pytest.approx(-2 * 0.004 - 0.009)
    nested = CompositeStream(name="N", components={"L3": 0.5, "BD": 0.5})
    u2 = _uni(lev=lev, n=nested)
    e2 = u2.exposure("N")
    assert e2.coefs == {"EQ": 1.5, "BD": 0.5} and e2.rf_coef == pytest.approx(-1.0)
    assert e2.const == pytest.approx(0.5 * (-0.017))


def test_composite_validation():
    with pytest.raises(ValidationError, match="sum"):
        CompositeStream(name="x", components={"EQ": 0.7})
    with pytest.raises(AssumptionError, match="financing_spread"):
        CompositeStream(name="x", components={"EQ": 1.0}, leverage=2.0)
    ok = CompositeStream(name="x", components={"EQ": 0.7}, allow_cash_remainder=True)
    assert _uni(x=ok).exposure("x").rf_coef == pytest.approx(0.3)
    with pytest.raises(UnknownStreamError, match="NOPE"):
        _uni(x=CompositeStream(name="x", components={"NOPE": 1.0}))
    a = CompositeStream(name="a", components={"b": 1.0})
    b = CompositeStream(name="b", components={"a": 1.0})
    with pytest.raises(ValidationError, match="cycle"):
        Universe([a, b])
    with pytest.raises(ValidationError, match="duplicate"):
        Universe([MarketStream(name="EQ", symbol="EQ"), MarketStream(name="EQ", symbol="X")])


def test_parametric_modes_validation():
    with pytest.raises(AssumptionError, match="expected_return"):
        ParametricStream(name="p", vol=A(0.1))
    with pytest.raises(AssumptionError, match="OR"):
        ParametricStream(name="p", expected_return=A(0.1), vol=A(0.1), factor_loadings={"EQ": A(1)},
                         factor_correlations={"EQ": A(0.5)})
    with pytest.raises(AssumptionError, match="idio_vol"):
        ParametricStream(name="p", expected_return=A(0.1), factor_loadings={"EQ": A(1)})
    with pytest.raises(AssumptionError, match="outside"):
        ParametricStream(name="p", expected_return=A(0.1), vol=A(0.1), factor_correlations={"EQ": A(1.5)})
    with pytest.raises(UnknownStreamError):
        _uni(p=ParametricStream(name="p", expected_return=A(0.1), vol=A(0.1), factor_correlations={"ZZ": A(0.5)}))
    p = ParametricStream(name="p", expected_return=A(0.1), vol=A(0.1), factor_correlations={"q": A(0.5)})
    q = ParametricStream(name="q", expected_return=A(0.1), vol=A(0.1))
    with pytest.raises(ValidationError, match="empirical"):
        _uni(p=p, q=q)


def test_default_model_moments_match_two_point_distribution():
    d = DefaultModel(Assumption(0.03, "t", "low"), Assumption(0.45, "t", "low"), Assumption(0.10, "t", "low"))
    rng = np.random.default_rng(0)
    hit = rng.random(2_000_000) < 0.03
    r = np.where(hit, -0.45, 0.10)
    assert d.expected_return() == pytest.approx(r.mean(), abs=5e-4)
    assert d.jump_variance == pytest.approx(r.var(), rel=0.01)
    s = ParametricStream(name="loan", vol=A(0.12), default={"prob": A(0.03), "lgd": A(0.45), "coupon": A(0.10)})
    assert s.expected_return.value == pytest.approx(0.97 * 0.10 - 0.03 * 0.45)
    assert s.expected_return.source.startswith("derived")


def test_build_moments_loadings_correlations_standalone():
    H = _hist()
    loads = ParametricStream(name="PL", expected_return=A(0.08), factor_loadings={"EQ": A(0.5), "HY": A(0.3)},
                             idio_vol=A(0.05), default={"prob": A(0.02), "lgd": A(0.5)})
    corr = ParametricStream(name="PC", expected_return=A(0.09), vol=A(0.15), factor_correlations={"HY": A(0.6)})
    alone = ParametricStream(name="PS", expected_return=A(0.12), vol=A(0.40))
    u = _uni(a=loads, b=corr, c=alone)
    names = ["EQ", "HY", "PL", "PC", "PS", "cash"]
    m = build_moments(u, names, returns=H, periods_per_year=52, rf=0.04, method="sample")
    S = m.cov
    iE, iH, iL, iC, iS = 0, 1, 2, 3, 4
    beta = np.array([0.5, 0.3])
    SEH = S[np.ix_([iE, iH], [iE, iH])]
    assert S[iL, iE] == pytest.approx(beta @ SEH[:, 0], rel=1e-12)
    jv = 0.02 * 0.98 * 0.5 ** 2
    assert S[iL, iL] == pytest.approx(beta @ SEH @ beta + 0.05 ** 2 + jv, rel=1e-12)
    assert S[iC, iH] / math.sqrt(S[iC, iC] * S[iH, iH]) == pytest.approx(0.6, rel=1e-12)  # assumed rho reproduced
    assert S[iC, iC] == pytest.approx(0.15 ** 2)
    assert np.allclose(S[iS, :iS], 0) and S[iS, iS] == pytest.approx(0.16)
    assert np.all(S[5] == 0) and m.mu[5] == pytest.approx(0.04)
    assert m.mu_basis["EQ"] == "historical_in_sample" and m.mu_basis["PL"] == "assumption"
    assert m.mu[0] == pytest.approx(H["EQ"].mean() * 52)
    assert any("not forecasts" in n for n in m.notes)
    assert m.jumps and m.jumps[0]["name"] == "PL"
    assert m.base_diffusive_cov()[iL, iL] == pytest.approx(S[iL, iL] - jv)


def test_inconsistent_correlation_assumptions_fail():
    H = _hist()
    bad = ParametricStream(name="P", expected_return=A(0.1), vol=A(0.10), factor_correlations={"EQ": A(0.9), "HY": A(-0.9)})
    with pytest.raises(AssumptionError, match="inconsistent"):
        build_moments(_uni(p=bad), ["P"], returns=H, periods_per_year=52, rf=0.0, method="sample")
    jumpy = ParametricStream(name="J", vol=A(0.05), default={"prob": A(0.1), "lgd": A(0.6), "coupon": A(0.1)})
    with pytest.raises(AssumptionError):
        build_moments(_uni(j=jumpy), ["J"], returns=None, periods_per_year=52, rf=0.0)


def test_composite_moments_are_linear_look_through():
    H = _hist()
    lev = CompositeStream(name="L2", components={"EQ": 0.6, "BD": 0.4}, leverage=2.0, financing_spread=A(0.005),
                          fee=A(0.01), expected_return=None)
    u = _uni(l=lev)
    m = build_moments(u, ["L2", "EQ", "BD"], returns=H, periods_per_year=52, rf=0.03, method="sample")
    w = np.array([1.2, 0.8])
    Sb = m.cov[np.ix_([1, 2], [1, 2])]
    assert m.cov[0, 0] == pytest.approx(w @ Sb @ w, rel=1e-12)
    assert m.mu[0] == pytest.approx(w @ m.mu[1:] + (1 - 2.0) * 0.03 - 1.0 * 0.005 - 0.01, rel=1e-12)
    x, c = m.look_through(np.array([0.5, 0.25, 0.25]))
    assert x == pytest.approx(np.array([0.5 * 1.2 + 0.25, 0.5 * 0.8 + 0.25, 0.0])[: len(x)])
    own = CompositeStream(name="L2", components={"EQ": 0.6, "BD": 0.4}, leverage=2.0, financing_spread=A(0.005),
                          expected_return=A(0.15))
    m2 = build_moments(_uni(l=own), ["L2"], returns=H, periods_per_year=52, rf=0.03)
    assert m2.mu[0] == pytest.approx(0.15) and m2.mu_basis["L2"] == "assumption"
    with pytest.raises(ValidationError, match="history"):
        build_moments(u, ["EQ"], returns=None, periods_per_year=52, rf=0.0)
    with pytest.raises(UnknownStreamError):
        build_moments(u, ["nope"], returns=H, periods_per_year=52, rf=0.0)


def test_series_returns_daily_reset():
    idx = pd.bdate_range("2024-01-01", periods=4)
    leaf = pd.DataFrame({"EQ": [0.0, 0.01, -0.02, 0.03], "HY": 0.0, "BD": 0.0}, index=idx)
    lev = CompositeStream(name="L3", components={"EQ": 1.0}, leverage=3.0, financing_spread=A(0.0252), fee=A(0.0252))
    u = _uni(l=lev)
    r = u.series_returns("L3", leaf, pd.Series(0.0001, index=idx), 252)
    exp = 3 * leaf["EQ"] - 2 * 0.0001 - (2 * 0.0252 + 0.0252) / 252
    np.testing.assert_allclose(r.to_numpy(), exp.to_numpy(), atol=1e-15)


def test_series_stream_constructors(tmp_path):
    idx = pd.bdate_range("2024-01-01", periods=5)
    s = SeriesStream.from_returns("S", pd.Series([0.01, -0.02, 0.0, 0.03, 0.01], index=idx), "test")
    assert s.levels.iloc[-1] == pytest.approx(1.01 * 0.98 * 1.0 * 1.03 * 1.01)
    p = tmp_path / "nav.csv"
    pd.DataFrame({"d": idx.strftime("%Y-%m-%d"), "nav": [1, 1.1, 1.2, 1.1, 1.3]}).to_csv(p, index=False)
    s2 = SeriesStream.from_csv("N", p, date_col="d", value_col="nav")
    assert len(s2.levels) == 5 and s2.source.startswith("csv:")
    with pytest.raises(ValidationError, match="column"):
        SeriesStream.from_csv("N", p, date_col="date", value_col="nav")
    with pytest.raises(ValidationError, match="> 0"):
        SeriesStream(name="bad", levels=pd.Series([1.0, -1.0, 2.0], index=idx[:3]), source="t")
