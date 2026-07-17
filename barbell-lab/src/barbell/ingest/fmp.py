"""Financial Modeling Prep daily bars (keyed: FMP_API_KEY).

Used as the cross-check feed against Yahoo (the investor already runs FMP for
the genomics tracker, so the key exists in the Render environment) and as a
fallback price source.

Uses the /stable API (the v3 "historical-price-full" endpoint was retired for
post-2025 keys): one call for dividend-adjusted closes, one for raw closes.

SECRET HYGIENE: httpx exception strings embed the full request URL including
``apikey``; every error path here scrubs it before the message can reach a
log line or traceback.
"""
from __future__ import annotations

import re

import httpx
import pandas as pd

from .base import ProviderError, canonical, env_key

_URL = "https://financialmodelingprep.com/stable/historical-price-eod/{kind}"


def _scrub(text: str) -> str:
    return re.sub(r"(apikey=)[A-Za-z0-9]+", r"\1<redacted>", str(text))


class FMPProvider:
    name = "fmp"

    def __init__(self) -> None:
        self.api_key = env_key("FMP_API_KEY")

    @property
    def available(self) -> bool:
        return self.api_key is not None

    def _get(self, kind: str, symbol: str, start: str, end: str) -> list[dict]:
        params = {"symbol": symbol, "from": start, "to": end, "apikey": self.api_key}
        try:
            r = httpx.get(_URL.format(kind=kind), params=params, timeout=60.0)
            r.raise_for_status()
            rows = r.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"fmp:{symbol} {kind} failed: {_scrub(exc)}") from None
        if not isinstance(rows, list) or not rows:
            raise ProviderError(f"fmp:{symbol} {kind} returned no history")
        return rows

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.available:
            raise ProviderError("fmp: FMP_API_KEY not configured")
        adj = pd.DataFrame(self._get("dividend-adjusted", symbol, start, end))
        raw = pd.DataFrame(self._get("full", symbol, start, end))
        adj = adj.set_index(pd.to_datetime(adj["date"]))
        raw = raw.set_index(pd.to_datetime(raw["date"]))
        out = pd.DataFrame(
            {
                "close_adj": adj["adjClose"],
                "close_raw": raw["close"].reindex(adj.index),
                "volume": raw.get("volume", pd.Series(dtype=float)).reindex(adj.index),
            }
        )
        return canonical(out, symbol, self.name)
