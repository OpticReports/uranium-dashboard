"""Series construction with EXPLICIT proxy splicing and provenance.

Splicing is a read-time transform, never persisted: the DB always holds each
instrument's raw vendor rows under its own ticker. ``total_return_series``
returns a frame with a ``provenance`` column so every downstream metric can
report which rows are live ETF vs proxy-extended.

Splice mechanics: proxy daily total returns on every proxy date strictly
BEFORE the effective splice date, plus the splice-day return (the proxy's own,
or the live return over the same interval if the proxy did not print that
day), are chain-linked backwards from the live series' first adjusted close
on/after the splice. Each pre-splice date carries the proxy's SAME-day return.
Only returns cross the boundary — never price levels — so premium /
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
        post = frame.loc[frame.index >= effective]
        anchor_date = post.index[0]
        anchor = float(post["close_adj"].iloc[0])
        last_pre = pre.index[-1]
        # Splice-day return covers exactly (last_pre, anchor_date]: the
        # proxy's own return when it printed on anchor_date, else the live
        # return over the same interval; if neither exists, refuse.
        if anchor_date in pdf.index:
            r_splice = float(pdf.at[anchor_date, "close_adj"]) / float(pre.iloc[-1]) - 1.0
        elif last_pre in live.index:
            r_splice = anchor / float(live.at[last_pre, "close_adj"]) - 1.0
        else:
            raise SeriesError(
                f"{ticker}: splice-day return unknown — proxy {proxy} has no row on "
                f"{anchor_date:%Y-%m-%d} and live has no row on {last_pre:%Y-%m-%d}")
        # level[d] = level[last_pre] * P[d]/P[last_pre], so every pre-splice
        # date carries the proxy's SAME-day return and no return is dropped
        back = anchor / (1.0 + r_splice) * (pre.values / float(pre.iloc[-1]))
        ext = pd.DataFrame(
            {"close_adj": back, "provenance": f"proxy:{proxy}"},
            index=pre.index,
        )
        frame = pd.concat([ext, post]).sort_index()
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
