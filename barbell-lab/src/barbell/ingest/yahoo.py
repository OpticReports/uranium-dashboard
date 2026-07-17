"""Yahoo Finance daily bars (keyless). Used as the default/priority provider
and for index symbols (^VIX, ^VIX3M) that FRED does not carry live.

Yahoo's ``adjclose`` is split- AND dividend-adjusted, which is exactly the
total-return series the acceptance gates check.
"""
from __future__ import annotations

import time

import httpx
import pandas as pd

from .base import ProviderError, canonical

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) barbell-lab/0.1"}


class YahooProvider:
    name = "yahoo"

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        p1 = int(pd.Timestamp(start, tz="UTC").timestamp())
        p2 = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).timestamp())
        params = {"period1": p1, "period2": p2, "interval": "1d", "events": "div,split"}
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                r = httpx.get(_URL.format(symbol=symbol), params=params,
                              headers=_HEADERS, timeout=30.0)
                r.raise_for_status()
                return self._parse(r.json(), symbol)
            except (httpx.HTTPError, ProviderError, KeyError, ValueError) as exc:
                last_exc = exc
                time.sleep(2**attempt)
        raise ProviderError(f"yahoo:{symbol} failed after retries: {last_exc}")

    def _parse(self, payload: dict, symbol: str) -> pd.DataFrame:
        result = (payload.get("chart") or {}).get("result")
        if not result:
            err = (payload.get("chart") or {}).get("error")
            raise ProviderError(f"yahoo:{symbol} no result ({err})")
        res = result[0]
        ts = res.get("timestamp")
        if not ts:
            raise ProviderError(f"yahoo:{symbol} returned no timestamps")
        quote = res["indicators"]["quote"][0]
        adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
        close = quote.get("close")
        if adj is None:
            # Indices (^VIX) have no adjclose; raw close IS the level.
            adj = close
        idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York")
        df = pd.DataFrame(
            {"close_adj": adj, "close_raw": close, "volume": quote.get("volume")},
            index=idx.tz_localize(None).normalize(),
        )
        return canonical(df, symbol, self.name)
