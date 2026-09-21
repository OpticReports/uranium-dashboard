"""Fees must track config for EVERY book, not just the donchian one.

Until 2026-09-21 `_process_pullback` built its Position without `fee_bps`, so
it silently took the dataclass default while `_process_donchian` passed
`2 * tcfg.taker_fee_bps`. The consequence was not a rounding difference: S3's
equity and fees were byte-identical across a 4.6x sweep of taker_fee_bps, the
two legs of the DEPLOYED S5 blend ran on different fee bases under one
TradeCfg, and RESEARCH_FEES.md's Kelly re-fit — the study that retired three
sizing rungs and set KELLY_M_CAP = 0.20 — was computed on that stream.
"""
import csv
import dataclasses
import os

import pytest

from app.engine.core import Bar, SignalCfg, TradeCfg
from app.engine.replay import run_replay

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")


@pytest.fixture(scope="module")
def bars():
    with open(FIX) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


@pytest.fixture(scope="module")
def cfg():
    from app.main import ENGINE
    return ENGINE.books_cfg, ENGINE.scfg, ENGINE.tcfg


def _run(bars, cfg, taker):
    books_cfg, scfg, tcfg = cfg
    return run_replay(bars, books_cfg, scfg,
                      dataclasses.replace(tcfg, taker_fee_bps=taker),
                      cash_apy=0.0).books


@pytest.mark.parametrize("book", ["S1", "S2", "S3", "S4"])
def test_every_book_responds_to_the_fee_config(bars, cfg, book):
    """THE REGRESSION GATE. Before the fix S1/S2/S3 gave ONE distinct equity
    across this sweep and S4 gave four."""
    seen = set()
    for taker in (4.32, 6.00, 8.00, 20.00):
        b = _run(bars, cfg, taker)[book]
        seen.add((round(b.equity, 6), round(sum(t.fees_usd for t in b.trades), 6)))
    assert len(seen) == 4, (
        f"{book} produced {len(seen)} distinct (equity, fees) across a 4.6x "
        f"fee sweep; a book whose dollars do not move with the fee is not "
        f"charging the configured fee: {sorted(seen)}")


@pytest.mark.parametrize("book", ["S1", "S2", "S3", "S4"])
def test_fees_equal_notional_times_the_configured_round_trip(bars, cfg, book):
    """Ties the dollars to the arithmetic, so a book cannot pass the sweep
    above by responding to the config in the WRONG proportion."""
    taker = 4.32          # any value; the point is the proportion
    b = _run(bars, cfg, taker)[book]
    assert b.trades, book
    want = sum(t.notional * 2 * taker / 10_000.0 for t in b.trades)
    assert sum(t.fees_usd for t in b.trades) == pytest.approx(want, rel=1e-9)


def test_both_legs_of_the_live_blend_share_one_fee_basis(bars, cfg):
    """S5 is 75% S3 + 25% S4. Before the fix S3 charged a 6.00 bps round trip
    and S4 12.00 under the SAME TradeCfg — one blend, two fee models."""
    books = _run(bars, cfg, 4.32)   # any value; both legs must agree
    rates = {}
    for name in ("S3", "S4"):
        b = books[name]
        rates[name] = sum(t.fees_usd for t in b.trades) / sum(
            t.notional for t in b.trades) * 10_000.0
    assert rates["S3"] == pytest.approx(rates["S4"], rel=1e-9)
    assert rates["S3"] == pytest.approx(8.64, rel=1e-9)


def test_the_default_still_reproduces_the_registered_objective():
    """The default is the REGISTERED OBJECTIVE, not the measured fee.

    research_basis_stats reproduces the reference backtest exactly at 6.00
    per side and at no other value; RESEARCH_FEES.md measured 4.32. Those
    disagree by 2x and reconciling them restates every published MAR, so the
    default may only move with a dated protocol amendment. This test exists
    so that move is deliberate rather than incidental.
    """
    assert TradeCfg().taker_fee_bps == pytest.approx(6.0)
