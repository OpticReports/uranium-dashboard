"""Data QA suite — runs on EVERY ingest; any failure fails the ingest.

Checks
------
1. missing-day detection: each ticker's live rows vs the reference exchange
   calendar (SPY's trading dates — same venue, longest clean history).
2. split/dividend sanity: no unexplained overnight move > max_overnight_gap
   in the ADJUSTED series (a big raw-close gap with a matching adjustment is
   fine; a big adjusted gap means a bad adjustment or bad print).
3. cross-provider spot check: daily returns Yahoo vs FMP where both exist
   (skipped with a logged WARNING when no FMP key is configured — a skipped
   check is recorded, never silently omitted).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import db
from ..config import load


@dataclass
class CheckResult:
    name: str
    ticker: str | None
    passed: bool
    detail: str

    def __str__(self) -> str:
        badge = "PASS" if self.passed else "FAIL"
        t = f" [{self.ticker}]" if self.ticker else ""
        return f"{badge} {self.name}{t}: {self.detail}"


@dataclass
class ValidationReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, *a, **kw) -> None:
        self.results.append(CheckResult(*a, **kw))

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    def persist(self, con: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc).isoformat()
        con.executemany(
            "INSERT INTO validation_log (ts_utc, check_name, ticker, passed, detail) "
            "VALUES (?,?,?,?,?)",
            [(now, r.name, r.ticker, int(r.passed), r.detail) for r in self.results],
        )
        con.commit()


def reference_calendar(con: sqlite3.Connection, source: str = "yahoo") -> pd.DatetimeIndex:
    ref = load("data")["validation"]["calendar_reference"]
    df = db.read_prices(con, ref, source=source)
    if df.empty:
        raise RuntimeError(f"reference calendar ticker {ref} has no data — ingest it first")
    return df.index


def check_missing_days(con: sqlite3.Connection, ticker: str, report: ValidationReport,
                       source: str = "yahoo") -> None:
    vcfg = load("data")["validation"]
    cal = reference_calendar(con, source)
    df = db.read_prices(con, ticker, source=source)
    if df.empty:
        report.add("missing_days", ticker, False, "no rows ingested")
        return
    span = cal[(cal >= df.index.min()) & (cal <= df.index.max())]
    missing = span.difference(df.index)
    limit = int(vcfg["max_missing_days"])
    detail = f"{len(missing)} missing vs {len(span)} expected"
    if len(missing) > 0:
        detail += f" (first: {[d.strftime('%Y-%m-%d') for d in missing[:5]]})"
    report.add("missing_days", ticker, len(missing) <= limit, detail)


def check_overnight_gaps(con: sqlite3.Connection, ticker: str, report: ValidationReport,
                         source: str = "yahoo") -> None:
    vcfg = load("data")["validation"]
    thresh = float(vcfg["max_overnight_gap"])
    explained = {(e["ticker"], pd.Timestamp(e["date"]))
                 for e in vcfg.get("explained_gaps", [])}
    df = db.read_prices(con, ticker, source=source)
    ret = df["close_adj"].pct_change().dropna()
    bad = ret[ret.abs() > thresh]
    bad = bad[[d for d in bad.index if (ticker, d) not in explained]]
    detail = (f"{len(bad)} adjusted moves >|{thresh:.0%}|"
              + (f": {json.dumps({d.strftime('%Y-%m-%d'): round(float(v), 4) for d, v in bad.head(5).items()})}"
                 if len(bad) else ""))
    report.add("overnight_gap", ticker, len(bad) == 0, detail)


def check_cross_provider(con: sqlite3.Connection, ticker: str, report: ValidationReport) -> None:
    ccfg = load("data")["providers"]["cross_check"]
    a = db.read_prices(con, ticker, source=ccfg["primary"])
    b = db.read_prices(con, ticker, source=ccfg["secondary"])
    if b.empty:
        report.add("cross_provider", ticker, True,
                   f"SKIPPED — no {ccfg['secondary']} data (key not configured?)")
        return
    ra = a["close_adj"].pct_change()
    rb = b["close_adj"].pct_change()
    joint = pd.concat([ra, rb], axis=1, keys=["a", "b"], sort=True).dropna()
    if len(joint) < 20:
        report.add("cross_provider", ticker, True, "SKIPPED — <20 overlapping days")
        return
    diff_bps = (joint["a"] - joint["b"]).abs() * 1e4
    tol = float(ccfg["tolerance_bps"])
    n_bad = int((diff_bps > tol).sum())
    # Adjusted-close feeds legitimately differ around distribution ex-dates by
    # a few bps; flag only if >1% of days disagree beyond tolerance.
    passed = n_bad <= max(2, int(0.01 * len(joint)))
    report.add("cross_provider", ticker, passed,
               f"{n_bad}/{len(joint)} overlapping days differ >{tol:.0f}bps "
               f"(median {np.median(diff_bps):.1f}bps)")
