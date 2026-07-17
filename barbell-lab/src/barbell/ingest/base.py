"""Provider-agnostic ingestion interface.

Every adapter returns the SAME canonical frame so the rest of the platform
never knows which vendor supplied a row:

    index: DatetimeIndex (exchange dates, tz-naive)
    columns: close_adj (split+dividend adjusted), close_raw, volume

A provider that cannot supply data RAISES (fail loudly) — it never returns an
empty frame for a symbol it should have.
"""
from __future__ import annotations

import os
from typing import Protocol

import pandas as pd


class ProviderError(RuntimeError):
    """A feed failed. The run fails visibly — never swallow this."""


class PriceProvider(Protocol):
    name: str

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:  # pragma: no cover
        ...


def canonical(df: pd.DataFrame, symbol: str, provider: str) -> pd.DataFrame:
    """Validate + normalize an adapter frame; raise on structural problems."""
    required = {"close_adj", "close_raw", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ProviderError(f"{provider}:{symbol} frame missing columns {missing}")
    if df.empty:
        raise ProviderError(f"{provider}:{symbol} returned zero rows")
    out = df.copy()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.dropna(subset=["close_adj"])
    if out["close_adj"].le(0).any():
        raise ProviderError(f"{provider}:{symbol} has non-positive adjusted closes")
    return out[["close_adj", "close_raw", "volume"]]


def env_key(name: str) -> str | None:
    """Read an API key from the environment (.env is loaded by the CLI)."""
    v = os.environ.get(name, "").strip()
    return v or None
