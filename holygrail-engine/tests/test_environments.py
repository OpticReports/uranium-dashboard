import numpy as np
import pandas as pd
import pytest

from holygrail import environments as V
from holygrail.allocate import quadrant_balance
from holygrail.errors import ValidationError
from holygrail.streams import MarketStream, Universe


def _levels(n=200, seed=0):
    rng = np.random.default_rng(seed)
    m = pd.date_range("2000-01-31", periods=n, freq="ME")
    g = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.01, n))), index=m)
    i = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.003, n))), index=m)
    return g, i


def test_macro_surprises_definition_and_lag():
    g, i = _levels()
    d0 = V.RegimeDefinition(trend_window=24, release_lag=0)
    s0 = V.macro_surprises(g, i, d0)
    yoy = g / g.shift(12) - 1
    t = s0.index[10]
    loc = yoy.index.get_loc(t)
    trend = yoy.iloc[loc - 24: loc].mean()  # strictly trailing, excludes t
    assert s0.loc[t, "growth_trend"] == pytest.approx(trend)
    assert s0.loc[t, "growth_surprise"] == pytest.approx(yoy.iloc[loc] - trend)
    s1 = V.macro_surprises(g, i, V.RegimeDefinition(trend_window=24, release_lag=1))
    assert s1.loc[s0.index[11], "growth_surprise"] == pytest.approx(s0.loc[s0.index[10], "growth_surprise"])
    q = V.classify_regimes(s1)
    for idx in q.index[:20]:
        gs, is_ = s1.loc[idx, "growth_surprise"], s1.loc[idx, "inflation_surprise"]
        assert q[idx] == f"{'growth_up' if gs > 0 else 'growth_down'}_{'inflation_up' if is_ > 0 else 'inflation_down'}"
    assert "trailing" in d0.describe()


def test_quadrant_table_and_betas_recover_planted_structure():
    g, i = _levels(400, 1)
    s = V.macro_surprises(g, i, V.RegimeDefinition(trend_window=24, release_lag=0))
    reg = V.classify_regimes(s)
    rng = np.random.default_rng(2)
    z = (s[["growth_surprise", "inflation_surprise"]] - s[["growth_surprise", "inflation_surprise"]].mean()) / \
        s[["growth_surprise", "inflation_surprise"]].std()
    eq = 0.005 + 0.02 * z["growth_surprise"] - 0.01 * z["inflation_surprise"] + rng.normal(0, 0.002, len(z))
    bd = 0.003 - 0.01 * z["growth_surprise"] - 0.015 * z["inflation_surprise"] + rng.normal(0, 0.002, len(z))
    monthly = pd.DataFrame({"EQ": eq, "BD": bd})
    qt = V.quadrant_table(monthly, reg)
    cell = qt[(qt.stream == "EQ") & (qt.quadrant == "growth_up_inflation_down")].iloc[0]
    sel = reg == "growth_up_inflation_down"
    assert cell["ann_mean"] == pytest.approx(eq[sel].mean() * 12) and cell["months"] == int(sel.sum())
    bt = V.environment_betas(monthly, s).set_index("stream")
    assert bt.loc["EQ", "beta_growth"] == pytest.approx(0.02, abs=0.002)
    assert bt.loc["BD", "beta_inflation"] == pytest.approx(-0.015, abs=0.002)
    M, un = V.exposures_from_betas(bt.reset_index(), ["EQ", "BD", "X"])
    assert un == ["X"]
    assert M[0, V.BOXES.index("growth_up")] == pytest.approx(2 / 3, abs=0.05)
    assert M[1, V.BOXES.index("inflation_down")] > M[1, V.BOXES.index("growth_down")]


def test_environment_balance_score():
    S = np.diag([0.04, 0.01, 0.0064, 0.0256])
    names = ["equity", "nominal_bond", "ilb", "gold"]
    M, un = V.exposures_from_mapping(names, {n: V.CANONICAL_MAP[n] for n in names})
    assert not un and np.allclose(M.sum(1), 1)
    eq_only = V.environment_balance(np.array([1.0, 0, 0, 0]), S, M)
    assert eq_only["risk_share"]["growth_up"] == pytest.approx(0.5)
    assert eq_only["balance_score"] == pytest.approx(1 - 0.5 / 0.75)
    r = quadrant_balance(S, M, list(V.BOXES))
    bal = V.environment_balance(r.weights, S, M, mu=np.array([0.07, 0.04, 0.035, 0.05]))
    assert bal["balance_score"] == pytest.approx(1.0, abs=1e-8)
    assert sum(bal["return_share"].values()) == pytest.approx(1.0)
    M2, un2 = V.exposures_from_mapping(names + ["crypto"], {n: V.CANONICAL_MAP[n] for n in names})
    S2 = np.diag([0.04, 0.01, 0.0064, 0.0256, 0.25])
    part = V.environment_balance(np.full(5, 0.2), S2, M2)
    assert un2 == ["crypto"] and part["unmapped_risk_share"] > 0.5
    with pytest.raises(ValidationError):
        V.exposures_from_mapping(["x"], {"x": ("growth_sideways",)})


def test_stream_box_mapping_manual_beats_canonical():
    u = Universe([MarketStream(name="SPY", symbol="SPY", asset_class="equity"),
                  MarketStream(name="BTC", symbol="BTC-USD", environments=("growth_up", "inflation_up")),
                  MarketStream(name="X", symbol="X")])
    m, src = V.stream_box_mapping(u, ["SPY", "BTC", "X"])
    assert m["SPY"] == ("growth_up", "inflation_down") and src["BTC"] == "manual" and "X" not in m


def test_regimes_from_fred_offline(offline_loader):
    s, prov = V.regimes_from_fred(offline_loader)
    assert set(s["quadrant"].unique()) <= set(V.QUADRANTS)
    assert prov["growth"]["identifier"] == "INDPRO" and "lagged 1m" in prov["definition"]
