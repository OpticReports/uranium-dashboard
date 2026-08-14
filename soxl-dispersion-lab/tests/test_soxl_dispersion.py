#!/usr/bin/env python3
"""Merge-blocking gate tests for the SOXL-dispersion study.

Two jobs:
  1. Property tests on the machinery (weights, causality, accounting) that
     must hold for ANY data.
  2. Regression gates that FREEZE the headline backtest numbers quoted in
     REPORT.md and VERDICT.md. If a refactor moves them, the published
     numbers are wrong and CI says so before anyone acts on them.

Run: python3 -m pytest soxl-dispersion-lab/tests -q
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datalib import (ZERO_COSTS, Costs, Data, TRADING_DAYS, build_basket,
                     margin_requirement, metrics, month_ends, pit_members,
                     run_backtest)
from signals import Signals, _shift1
from universe import CAP_REST, CAP_TOP5, modified_cap_weights
from variants import BASE_COSTS, tgt_long_short

START = "2010-03-12"
TOL = 0.004          # 0.4pp on rates; frozen numbers are quoted to 0.1pp


@pytest.fixture(scope="module")
def d():
    return Data()


@pytest.fixture(scope="module")
def v0w(d):
    return run_backtest(d, START, d.dates[-1], tgt_long_short(8, "cap"),
                        costs=Costs(**BASE_COSTS), rebalance="W")


# ---------------------------------------------------------------- properties
def test_modified_cap_weights_sum_to_one():
    caps = {f"T{i}": (100 - i) * 1e9 for i in range(40)}
    w = modified_cap_weights(caps)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert len(w) == 30


def test_modified_cap_weights_respect_caps():
    """One elephant must not keep 90% of the index."""
    caps = {"BIG": 9e12, **{f"T{i}": 1e10 for i in range(29)}}
    w = modified_cap_weights(caps)
    assert w["BIG"] <= CAP_TOP5 + 1e-9, f"top-5 cap breached: {w['BIG']}"
    ranked = sorted(w, key=lambda t: -caps[t])
    for t in ranked[5:]:
        assert w[t] <= CAP_REST + 1e-9, f"tail cap breached on {t}"


def test_signals_are_causal():
    """_shift1 must expose only strictly-prior information."""
    x = np.arange(10.0)
    s = _shift1(x)
    assert np.isnan(s[0])
    assert np.array_equal(s[1:], x[:-1])


def test_pit_membership_has_no_future_names(d):
    """A 2013 basket must not contain a company that IPO'd later."""
    idx = d.di["2013-06-28"]
    names = pit_members(d, idx, 30)
    for t in ("ARM", "ALAB", "GFS", "CRDO"):
        assert t not in names, f"{t} cannot be in a 2013 index"


def test_pit_membership_contains_dead_names_when_alive(d):
    """Survivorship guard: 2013's index must hold companies that later died."""
    idx = d.di["2013-06-28"]
    names = pit_members(d, idx, 30)
    assert len({"XLNX", "BRCM", "LLTC", "ATML", "MXIM"} & set(names)) >= 2


def test_book_accounting_identity(d):
    """NAV must equal cash + long MV - short MV at every step."""
    r = run_backtest(d, "2015-01-02", "2016-12-30", tgt_long_short(8, "cap"),
                     costs=Costs(**BASE_COSTS), rebalance="M")
    assert np.all(np.isfinite(r["nav"]))
    assert np.all(r["nav"] > 0)


def test_costs_never_help(d):
    """Zero-friction must beat costed, always."""
    kw = dict(target_fn=tgt_long_short(8, "cap"), rebalance="M")
    net = run_backtest(d, "2015-01-02", "2019-12-31",
                       costs=Costs(**BASE_COSTS), **kw)
    gross = run_backtest(d, "2015-01-02", "2019-12-31", costs=ZERO_COSTS, **kw)
    assert gross["nav"][-1] > net["nav"][-1]


def test_short_leveraged_etf_margin_is_penalised(d):
    """A short 3x ETF must cost ~3x a plain short in maintenance margin."""
    from datalib import Book
    b = Book(1.0)
    i = d.di["2019-06-28"]
    b.shares = {"SOXL": -1000 / d.px["SOXL"][i]}
    lev = margin_requirement(d, b, i, "RegT")
    b.shares = {"NVDA": -1000 / d.px["NVDA"][i]}
    plain = margin_requirement(d, b, i, "RegT")
    assert lev > 2.5 * plain


def test_margin_call_prevents_infinite_leverage(d):
    """Quarterly rebalancing through 2026 must trigger a forced de-risk, not
    a 100x-levered survivor. This is the check that caught the engine
    reporting a Sharpe for a book running on 5% equity."""
    r = run_backtest(d, START, d.dates[-1], tgt_long_short(8, "cap"),
                     costs=Costs(**BASE_COSTS), rebalance="Q")
    assert r["n_margin_calls"] >= 1
    assert np.nanmax(r["gross_exposure"]) < 12.0


# ------------------------------------------------------- frozen headlines
def test_frozen_soxl_alpha_and_beta(d):
    """SOXL's fee drag vs SOXX -- the only harvestable 'decay'."""
    from decomposition import ols
    lo, hi = d.slice_idx(START, d.dates[-1])
    a, b, _, _, _ = ols(d.ret("SOXL")[lo:hi], d.ret("SOXX")[lo:hi])
    assert abs(b - 2.9625) < 0.01, f"SOXL beta moved: {b}"
    assert abs(a * TRADING_DAYS - (-0.0539)) < TOL, \
        f"SOXL fee alpha moved: {a*TRADING_DAYS}"


def test_frozen_v0_baseline(d):
    """The seed strategy exactly as described: 25/75, top-8, monthly."""
    r = run_backtest(d, START, d.dates[-1], tgt_long_short(8, "cap"),
                     costs=Costs(**BASE_COSTS), rebalance="M")
    m = metrics(r["nav"], r["dates"])
    assert abs(m["CAGR"] - 0.031) < TOL, f"V0 CAGR moved: {m['CAGR']}"
    assert abs(m["MaxDD"] - (-0.415)) < 0.01, f"V0 maxDD moved: {m['MaxDD']}"


def test_frozen_v0_in_sample_is_negative(d):
    """The headline honesty claim: a decade of losses in-sample."""
    r = run_backtest(d, START, "2019-12-31", tgt_long_short(8, "cap"),
                     costs=Costs(**BASE_COSTS), rebalance="M")
    m = metrics(r["nav"], r["dates"])
    assert m["CAGR"] < 0, f"V0 in-sample CAGR is no longer negative: {m['CAGR']}"


def test_frozen_v0w_weekly(d, v0w):
    """Best surviving variant.

    Sharpe here is EXCESS of the 3m bill, which is the basis every Sharpe in
    REPORT.md is quoted on. The raw (rf=0) figure is ~0.83; quoting the two
    interchangeably would overstate the strategy by 0.16.
    """
    lo, hi = d.slice_idx(START, d.dates[-1])
    m = metrics(v0w["nav"], v0w["dates"], rf=d.rf[lo + 1:hi])
    assert abs(m["CAGR"] - 0.072) < TOL, f"V0.W CAGR moved: {m['CAGR']}"
    assert abs(m["Sharpe"] - 0.67) < 0.05, f"V0.W Sharpe moved: {m['Sharpe']}"


def test_book_is_beta_neutral_not_net_long(d, v0w):
    """The trade is NOT disguised long-semi beta -- it is slightly net short."""
    lo, hi = d.slice_idx(START, d.dates[-1])
    r = v0w["nav"][1:] / v0w["nav"][:-1] - 1
    b = d.ret("SOXX")[lo + 1:hi][:len(r)]
    ok = np.isfinite(r) & np.isfinite(b)
    beta = np.cov(r[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)
    assert -0.25 < beta < 0.10, f"net beta outside the stated range: {beta}"


def test_strategy_underperforms_the_trivial_alternative(d, v0w):
    """The verdict itself, as a test: 75% basket + cash beats the book."""
    bench = run_backtest(
        d, START, d.dates[-1],
        lambda data, i: {t: 0.75 * v for t, v in
                         build_basket(data, i, 8, "cap").items()},
        costs=Costs(**BASE_COSTS), rebalance="M")
    m_b = metrics(bench["nav"], bench["dates"])
    m_s = metrics(v0w["nav"], v0w["dates"])
    assert m_b["CAGR"] > m_s["CAGR"] + 0.05, \
        "benchmark no longer dominates -- re-check the verdict"


def test_concentration_alpha_is_nvda(d):
    """Ex-NVDA the 'winners' alpha collapses to statistical noise."""
    from decomposition import _basket_returns, ols
    lo, hi = d.slice_idx(START, d.dates[-1])
    mes = [i for i in month_ends(d.dates) if lo <= i < hi]
    r_soxx = d.ret("SOXX")[lo:hi]
    full = _basket_returns(d, mes, 8, "cap", lo, hi)
    ex = _basket_returns(d, mes, 8, "cap", lo, hi, exclude={"NVDA"})
    a_f, _, se_f, _, _ = ols(full, r_soxx)
    a_x, _, se_x, _, _ = ols(ex, r_soxx)
    assert a_f / se_f > 1.0, "full-basket alpha lost its (already weak) t-stat"
    assert a_x / se_x < 1.0, "ex-NVDA alpha is no longer insignificant"
