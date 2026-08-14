"""Tiingo daily bars (keyed: TIINGO_API_KEY). Third-priority price source."""
from __future__ import annotations

import httpx
import pandas as pd

from .base import ProviderError, canonical, env_key

_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"


class TiingoProvider:
    name = "tiingo"

    def __init__(self) -> None:
        self.api_key = env_key("TIINGO_API_KEY")

    @property
    def available(self) -> bool:
        return self.api_key is not None

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.available:
            raise ProviderError("tiingo: TIINGO_API_KEY not configured")
        params = {"startDate": start, "endDate": end, "token": self.api_key,
                  "resampleFreq": "daily"}
        try:
            r = httpx.get(_URL.format(symbol=symbol), params=params, timeout=60.0)
            r.raise_for_status()
            rows = r.json()
        except httpx.HTTPError as exc:
            # scrub token=... from httpx exception text before it can be logged
            import re
            msg = re.sub(r"(token=)[A-Za-z0-9]+", r"\1<redacted>", str(exc))
            raise ProviderError(f"tiingo:{symbol} request failed: {msg}") from None
        if not rows:
            raise ProviderError(f"tiingo:{symbol} returned no history")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("date")
        out = pd.DataFrame(
            {"close_adj": df["adjClose"], "close_raw": df["close"], "volume": df.get("volume")}
        )
        return canonical(out, symbol, self.name)
