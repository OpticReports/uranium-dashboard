"""Ingest orchestration: fetch → persist → validate → (optionally) gate.

Any provider failure or validation failure raises; a partial ingest never
looks like a complete one.
"""
from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from .. import db
from ..config import PARQUET_DIR, ensure_dirs, load
from .base import ProviderError
from .fmp import FMPProvider
from .fred import fetch_series
from .tiingo import TiingoProvider
from .yahoo import YahooProvider
from ..validate.checks import (
    ValidationReport,
    check_cross_provider,
    check_missing_days,
    check_overnight_gaps,
)

logger = logging.getLogger(__name__)

_PROVIDERS = {"yahoo": YahooProvider, "fmp": FMPProvider, "tiingo": TiingoProvider}


def _apply_distribution_corrections(df: pd.DataFrame, ticker: str, source: str) -> pd.DataFrame:
    """Fix documented vendor errors in dividend adjustments (config-declared,
    citation-required). CRSP-style: an ex-date distribution D scales every
    adjusted close BEFORE the ex-date by f = 1 - D/prev_raw_close. We replace
    the vendor's factor with the true one: multiply pre-ex-date adjusted
    closes by f_true/f_vendor."""
    for corr in load("data").get("distribution_corrections", []):
        if corr["ticker"] != ticker or corr["vendor"] != source:
            continue
        ex = pd.Timestamp(corr["ex_date"])
        before = df.index < ex
        if not before.any() or (df.index >= ex).sum() == 0:
            raise RuntimeError(f"distribution correction for {ticker} @ {ex:%Y-%m-%d}: "
                               "ex-date not inside fetched range")
        prev_close = float(df.loc[before, "close_raw"].iloc[-1])
        f_vendor = 1.0 - float(corr["vendor_amount"]) / prev_close
        f_true = 1.0 - float(corr["true_amount"]) / prev_close
        df = df.copy()
        df.loc[before, "close_adj"] *= f_true / f_vendor
        logger.warning(
            "applied distribution correction %s %s: vendor %.4f -> true %.4f "
            "(pre-ex adj scaled by %.5f) sources=%s",
            ticker, ex.date(), corr["vendor_amount"], corr["true_amount"],
            f_true / f_vendor, "; ".join(corr["sources"]),
        )
    return df


def _to_rows(df: pd.DataFrame, ticker: str, source: str) -> pd.DataFrame:
    out = df.reset_index(names="date")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["ticker"] = ticker
    out["source"] = source
    return out


def ingest_prices(con: sqlite3.Connection, end: str, tickers: list[str] | None = None) -> None:
    cfg = load("data")
    start = str(cfg["history_start"])
    names = tickers or list(cfg["tickers"].keys()) + list(cfg.get("indices", []))
    primary = YahooProvider()
    fmp = FMPProvider()

    for t in names:
        df = primary.daily(t, start, end)          # raises on failure — no skip
        df = _apply_distribution_corrections(df, t, primary.name)
        n = db.upsert_prices(con, _to_rows(df, t, primary.name))
        logger.info("ingested %s: %d rows (yahoo)", t, n)
        # Cross-check feed (only for non-index tickers, only if key present).
        if fmp.available and not t.startswith("^"):
            try:
                dfx = fmp.daily(t, start, end)
                db.upsert_prices(con, _to_rows(dfx, t, fmp.name))
            except ProviderError as exc:
                # Mutual funds / trusts sometimes absent on FMP: the cross-check
                # records a SKIP; the primary feed is unaffected.
                logger.warning("fmp cross-feed unavailable for %s: %s", t, exc)


def ingest_fred(con: sqlite3.Connection, end: str) -> None:
    cfg = load("data")
    start = str(cfg["history_start"])
    for sid in cfg["fred"]:
        s = fetch_series(sid, start, end)
        n = db.upsert_fred(con, sid, s)
        logger.info("ingested FRED %s: %d obs", sid, n)


def validate_all(con: sqlite3.Connection) -> ValidationReport:
    cfg = load("data")
    report = ValidationReport()
    for t in cfg["tickers"]:
        check_missing_days(con, t, report)
        check_overnight_gaps(con, t, report)
        check_cross_provider(con, t, report)
    report.persist(con)
    return report


def snapshot_parquet(con: sqlite3.Connection) -> None:
    """Persist the canonical return matrix to parquet (data snapshot for
    reproducibility: results = f(config hash, this file))."""
    from .series import returns_matrix
    cfg = load("data")
    tickers = [t for t in cfg["tickers"]]
    mat = returns_matrix(con, tickers)
    ensure_dirs()
    path = PARQUET_DIR / "returns_daily.parquet"
    mat.to_parquet(path)
    logger.info("snapshot written: %s (%d rows x %d cols)", path, *mat.shape)


def full_ingest(con: sqlite3.Connection, end: str, gate: bool = True) -> ValidationReport:
    ingest_prices(con, end)
    ingest_fred(con, end)
    report = validate_all(con)
    if not report.ok:
        raise RuntimeError(
            "ingest validation FAILED:\n  " + "\n  ".join(str(f) for f in report.failures())
        )
    if gate:
        from ..validate.acceptance import assert_gates
        for g in assert_gates(con):
            logger.info("%s", g)
    snapshot_parquet(con)
    return report
