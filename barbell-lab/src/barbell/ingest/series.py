"""Series construction with EXPLICIT proxy splicing and provenance.

Splicing is a read-time transform, never persisted: the DB always holds each
instrument's raw vendor rows under its own ticker. ``total_return_series``
returns a frame with a ``provenance`` column so every downstream metric can
report which rows are live ETF vs proxy-extended.

Splice mechanics: proxy daily total returns strictly BEFORE the effective
splice date are chain-linked backwards from the live series' first adjusted
close. Only returns cross the boundary — never price levels — so premium /
expense-ratio level differences between proxy and ETF cannot distort returns.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import db
from ..config import load


class SeriesError(RuntimeError):
    pass


@dataclass
class BuiltSeries:
    ticker: str
    frame: pd.DataFrame          # index date; columns close_adj, provenance
    proxy: str | None
    splice_date: pd.Timestamp | None

    @property
    def returns(self) -> pd.Series:
        return self.frame["close_adj"].pct_change().dropna()

    def provenance_summary(self) -> str:
        n = len(self.frame)
        live = int((self.frame["provenance"] == "live").sum())
        if self.proxy and live < n:
            return (f"{self.ticker}: {n - live} proxy rows ({self.proxy}) + {live} live rows, "
                    f"spliced {self.splice_date:%Y-%m-%d}")
        return f"{self.ticker}: {live} live rows (no proxy)"


def _read_one(con: sqlite3.Connection, ticker: str, source: str) -> pd.DataFrame:
    df = db.read_prices(con, ticker, source=source)
    if df.empty:
        raise SeriesError(f"no ingested data for {ticker} (source={source}) — run `barbell ingest`")
    return df


def total_return_series(con: sqlite3.Connection, ticker: str,
                        source: str = "yahoo") -> BuiltSeries:
    """Build the canonical adjusted-close series for a config ticker,
    proxy-extended only if config/data.yaml declares a proxy explicitly."""
    cfg = load("data")
    spec = cfg["tickers"].get(ticker)
    if spec is None:
        raise SeriesError(f"{ticker} is not declared in config/data.yaml")

    live = _read_one(con, ticker, source)
    frame = pd.DataFrame({"close_adj": live["close_adj"]})
    frame["provenance"] = "live"

    proxy = spec.get("proxy")
    if proxy:
        splice = pd.Timestamp(spec["splice_date"])
        effective = max(splice, frame.index.min())
        pdf = _read_one(con, proxy, source)
        pre = pdf.loc[pdf.index < effective, "close_adj"]
        if len(pre) < 2:
            raise SeriesError(f"{ticker}: proxy {proxy} has <2 rows before splice {effective:%Y-%m-%d}")
        pre_ret = pre.pct_change().dropna()
        anchor = float(frame.loc[frame.index >= effective, "close_adj"].iloc[0])
        # chain backwards: price[t-1] = price[t] / (1 + r[t])
        back = anchor / np.cumprod(1.0 + pre_ret.values[::-1])
        ext = pd.DataFrame(
            {"close_adj": back[::-1], "provenance": f"proxy:{proxy}"},
            index=pre_ret.index,
        )
        frame = pd.concat([ext, frame.loc[frame.index >= effective]]).sort_index()
        return BuiltSeries(ticker, frame, proxy, effective)
    return BuiltSeries(ticker, frame, None, None)


def returns_matrix(con: sqlite3.Connection, tickers: list[str],
                   source: str = "yahoo", spliced: bool = True) -> pd.DataFrame:
    """Aligned daily total-return matrix. With spliced=False, only live rows."""
    cols = {}
    for t in tickers:
        bs = total_return_series(con, t, source=source)
        f = bs.frame if spliced else bs.frame[bs.frame["provenance"] == "live"]
        cols[t] = f["close_adj"].pct_change()
    mat = pd.DataFrame(cols).dropna(how="all")
    return mat
