"""ACCEPTANCE GATES — hard, from the build spec. The platform is untrusted
until every gate passes on freshly ingested data; on any failure the caller
must STOP and report, never proceed to backtests.

Gates (ground truth = published fund total returns):
  1. KMLM calendar-year 2022 total return = +30.4%  (± 0.5pp)
  2. GLD  calendar-year 2022 total return ≈ -0.8%   (± 0.5pp)
  3. TAIL H1-2020 (2019-12-31 → 2020-06-30) ≈ +15.5% (± 1pp)
  4. corr(QUAL, MTUM) daily returns, trailing 3y ≈ 0.84 (± 0.05)

All gates run on LIVE rows only (no proxy splicing) — they verify vendor
adjusted closes, not our splice logic.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd

from .. import db


@dataclass
class Gate:
    name: str
    got: float
    expected: float
    tol: float

    @property
    def passed(self) -> bool:
        return abs(self.got - self.expected) <= self.tol

    def __str__(self) -> str:
        badge = "PASS" if self.passed else "FAIL"
        return (f"{badge} {self.name}: got {self.got:+.2%}, "
                f"expected {self.expected:+.2%} ± {self.tol:.2%}")


def _window_return(con: sqlite3.Connection, ticker: str, start: str, end: str,
                   source: str = "yahoo") -> float:
    """Total return from last close ON/BEFORE start to last close on/before end."""
    px = db.read_prices(con, ticker, source=source)["close_adj"]
    if px.empty:
        raise RuntimeError(f"acceptance: no data for {ticker}")
    base = px.loc[:start]
    final = px.loc[:end]
    if base.empty or final.empty:
        raise RuntimeError(f"acceptance: {ticker} lacks data at {start} or {end}")
    return float(final.iloc[-1] / base.iloc[-1] - 1.0)


def run_gates(con: sqlite3.Connection, source: str = "yahoo") -> list[Gate]:
    gates = [
        Gate("KMLM 2022 total return",
             _window_return(con, "KMLM", "2021-12-31", "2022-12-31", source), 0.304, 0.005),
        Gate("GLD 2022 total return",
             _window_return(con, "GLD", "2021-12-31", "2022-12-31", source), -0.008, 0.005),
        Gate("TAIL H1-2020 total return",
             _window_return(con, "TAIL", "2019-12-31", "2020-06-30", source), 0.155, 0.010),
    ]
    q = db.read_prices(con, "QUAL", source=source)["close_adj"].pct_change()
    m = db.read_prices(con, "MTUM", source=source)["close_adj"].pct_change()
    joint = pd.concat([q, m], axis=1, keys=["QUAL", "MTUM"], sort=True).dropna()
    if joint.empty:
        raise RuntimeError("acceptance: no QUAL/MTUM overlap")
    last = joint.index.max()
    trailing = joint.loc[last - pd.DateOffset(years=3):]
    corr = float(trailing["QUAL"].corr(trailing["MTUM"]))
    gates.append(Gate("QUAL/MTUM 3y daily-return correlation", corr, 0.84, 0.05))
    return gates


def assert_gates(con: sqlite3.Connection, source: str = "yahoo") -> list[Gate]:
    gates = run_gates(con, source)
    failed = [g for g in gates if not g.passed]
    if failed:
        msg = "; ".join(str(g) for g in failed)
        raise AssertionError(f"ACCEPTANCE GATES FAILED — platform untrusted, STOP: {msg}")
    return gates
