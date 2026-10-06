"""Shared fixtures.  Network tests (@pytest.mark.network) are skipped unless
pytest is run with --run-network or HOLYGRAIL_NETWORK=1."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from holygrail.data import DataLoader, DataSeries, Provenance


def pytest_addoption(parser):
    parser.addoption("--run-network", action="store_true", default=False,
                     help="run tests that hit live Yahoo/FRED feeds")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network") or os.environ.get("HOLYGRAIL_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="network test: run with --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


def _make_cov(n: int, seed: int = 0, scale: float = 0.04) -> np.ndarray:
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(n, n))
    S = A @ A.T / n * scale + np.diag(rng.uniform(0.2, 1.0, n) * scale * 0.1)
    return 0.5 * (S + S.T)


@pytest.fixture
def make_cov():
    """Factory: make_cov(n, seed) -> random positive-definite covariance."""
    return _make_cov


def synthetic_universe_levels(seed: int = 0, start: str = "2014-01-01", end: str = "2026-09-30") -> dict:
    """Daily level series for a set of symbols: equities on business days, a
    crypto symbol on all 7 days; one equity starts late (unequal history).
    Correlated returns from a fixed factor model.  SYNTHETIC test data."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    n = len(days)
    mkt = rng.normal(0.0003, 0.010, n)
    rates = rng.normal(0.0, 0.006, n)
    infl = rng.normal(0.0, 0.007, n)
    spec = {
        "EQA": (1.0, -0.2, 0.0, 0.006, 0.00025),
        "EQB": (0.9, -0.1, 0.1, 0.008, 0.0002),
        "BND": (-0.1, 1.0, -0.2, 0.002, 0.0001),
        "GLDX": (0.1, 0.2, 1.0, 0.006, 0.0002),
        "CRYX": (1.5, 0.0, 0.5, 0.030, 0.0008),
        "LATE": (0.8, 0.0, 0.0, 0.007, 0.0002),
    }
    out = {}
    bdays = days[days.dayofweek < 5]
    for sym, (bm, br, bi, idio, drift) in spec.items():
        r = drift + bm * mkt + br * rates + bi * infl + rng.normal(0, idio, n)
        lv = pd.Series(100 * np.exp(np.cumsum(np.log1p(r))), index=days)
        if sym != "CRYX":
            lv = lv.loc[bdays]
        if sym == "LATE":
            lv = lv.loc["2019-06-03":]
        out[sym] = lv
    return out


def synthetic_fred(seed: int = 1) -> dict:
    rng = np.random.default_rng(seed)
    d = pd.date_range("2010-01-01", "2026-09-30", freq="B")
    dtb3 = pd.Series(np.clip(2 + np.cumsum(rng.normal(0, 0.02, len(d))), 0.05, None), index=d)
    m = pd.date_range("2000-01-01", "2026-08-01", freq="MS")
    indpro = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0015, 0.008, len(m)))), index=m)
    cpi = pd.Series(170 * np.exp(np.cumsum(rng.normal(0.002, 0.002, len(m)))), index=m)
    return {"DTB3": dtb3, "INDPRO": indpro, "CPIAUCSL": cpi}


@pytest.fixture
def offline_loader(tmp_path):
    """A DataLoader in offline mode over a cache pre-populated with SYNTHETIC
    Yahoo and FRED series (so full pipelines run with no network)."""
    loader = DataLoader(tmp_path / "cache", offline=False, http_get=_no_network)
    now = datetime.now(timezone.utc).isoformat()
    for sym, s in synthetic_universe_levels().items():
        prov = Provenance("yahoo", sym, "synthetic://", "adjclose", True, str(s.index[0].date()),
                          str(s.index[-1].date()), len(s), fetched_at=now, warnings=["SYNTHETIC test series"])
        loader._write_cache("yahoo", sym, DataSeries(s, prov))
    for sid, s in synthetic_fred().items():
        prov = Provenance("fred", sid, "synthetic://", "value", None, str(s.index[0].date()),
                          str(s.index[-1].date()), len(s), fetched_at=now, warnings=["SYNTHETIC"])
        loader._write_cache("fred", sid, DataSeries(s, prov))
    return DataLoader(tmp_path / "cache", offline=True, http_get=_no_network)


def _no_network(url, params, timeout):  # pragma: no cover - must never be called offline
    raise AssertionError(f"network access attempted in an offline test: {url}")


@pytest.fixture
def test_book_yaml(tmp_path):
    """A small book over the synthetic symbols, with every stream type."""
    nav = synthetic_universe_levels()["EQB"].iloc[-1500:] * 1.01
    pd.DataFrame({"date": nav.index.strftime("%Y-%m-%d"), "nav": nav.to_numpy()}).to_csv(tmp_path / "nav.csv", index=False)
    text = """
name: test book
as_of: 2026-09-30
assumptions:
  eq_mu: {value: 0.07, source: test, confidence: medium}
settings:
  risk_free: "fred:DTB3"
  financing_spread: {value: 0.005, source: test, confidence: medium}
  target_vol: 0.10
  freq: W
  window_years: 4
  estimator: lw_cc
  min_obs: 52
streams:
  EQA: {type: market, symbol: EQA, asset_class: equity, expected_return: "@eq_mu"}
  BND: {type: market, symbol: BND, asset_class: nominal_bond}
  GLDX: {type: market, symbol: GLDX, asset_class: gold}
  CRYX: {type: market, symbol: CRYX, environments: [growth_up, inflation_up]}
  LEV: {type: composite, components: {EQA: 0.5, BND: 0.5}, leverage: 2.0,
        financing_spread: {value: 0.004, source: test, confidence: low},
        fee: {value: 0.009, source: test, confidence: high}, asset_class: equity}
  NAV: {type: series, path: nav.csv, date_col: date, value_col: nav, source: "test export", asset_class: equity}
  LOAN:
    type: parametric
    vol: {value: 0.10, source: test, confidence: low}
    factor_correlations: {EQA: {value: 0.3, source: test, confidence: low}}
    default: {prob: {value: 0.02, source: t, confidence: low}, lgd: {value: 0.4, source: t, confidence: low},
              coupon: {value: 0.10, source: t, confidence: medium}}
    asset_class: credit
  cash: {type: cash}
positions:
  - {name: A, value_usd: 40000, stream: EQA, sleeve: core}
  - {name: B, value_usd: 25000, stream: BND, sleeve: core}
  - {name: C, value_usd: 10000, stream: GLDX, sleeve: core}
  - {name: D, value_usd: 5000, stream: CRYX, sleeve: sat, tags: [crypto]}
  - {name: E, value_usd: 5000, stream: LEV, sleeve: sat}
  - {name: F, value_usd: 5000, stream: NAV, sleeve: sat}
  - {name: G, value_usd: 8000, stream: LOAN, sleeve: private, mark_basis: model, liquidity: illiquid}
  - {name: H, value_usd: 2000, stream: cash, sleeve: cash}
  - {name: I, value_usd: 10000, stream: cash, sleeve: cash, investable: false, tags: [spending]}
totals: {total_usd: 110000, sleeves: {core: 75000, sat: 15000, private: 8000, cash: 12000}}
"""
    p = tmp_path / "book.yaml"
    p.write_text(text)
    return p
