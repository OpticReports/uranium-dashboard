"""yfinance market provider (free baseline, no key).

Computes cash runway (cash / quarterly burn) and pulls short interest + a rough
options IV/skew where available. Thin-float names (ALMR, GENB, QSI, MASS) often
expose none of the options/short data on free sources — those fields come back
as None (explicit "no data"), never 0.
"""
from __future__ import annotations

import logging
from datetime import date

from ...utils.ratelimit import with_backoff
from .base import MarketProvider

logger = logging.getLogger(__name__)


def _safe(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


class YFinanceProvider(MarketProvider):
    name = "yfinance"

    def _ticker(self, symbol: str):
        import yfinance as yf  # imported lazily so the dep is optional at import time

        return yf.Ticker(symbol)

    def validate_symbol(self, symbol: str) -> str | None:
        try:
            t = with_backoff(lambda: self._ticker(symbol))
            info = t.get_info() if hasattr(t, "get_info") else t.info
        except Exception as exc:  # noqa: BLE001
            logger.warning("validate_symbol(%s) failed: %s", symbol, exc)
            return None
        if not info:
            return None
        name = _safe(info, "longName", "shortName", "displayName")
        # A bad symbol typically yields an info dict with no price/name fields.
        if name is None and _safe(info, "regularMarketPrice", "currentPrice") is None:
            return None
        return name or symbol

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        t = self._ticker(symbol)
        hist = with_backoff(
            lambda: t.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        )
        out: list[dict] = []
        if hist is None or hist.empty:
            return out
        for idx, row in hist.iterrows():
            out.append(
                {
                    "date": idx.date().isoformat(),
                    "open": _f(row.get("Open")),
                    "high": _f(row.get("High")),
                    "low": _f(row.get("Low")),
                    "close": _f(row.get("Close")),
                    "adj_close": _f(row.get("Adj Close")),
                    "volume": _f(row.get("Volume")),
                }
            )
        return out

    def get_fundamentals(self, symbol: str) -> dict:
        t = self._ticker(symbol)
        info = with_backoff(lambda: (t.get_info() if hasattr(t, "get_info") else t.info)) or {}

        market_cap = _f(_safe(info, "marketCap"))
        cash = _f(_safe(info, "totalCash"))
        # Quarterly burn approximated from trailing free cash flow when negative.
        op_cf = _f(_safe(info, "operatingCashflow"))
        fcf = _f(_safe(info, "freeCashflow"))
        annual_burn = None
        for candidate in (fcf, op_cf):
            if candidate is not None and candidate < 0:
                annual_burn = -candidate
                break
        quarterly_burn = annual_burn / 4 if annual_burn else None
        runway = None
        if cash is not None and quarterly_burn and quarterly_burn > 0:
            runway = cash / quarterly_burn

        # Short interest as a fraction of float.
        si = _f(_safe(info, "shortPercentOfFloat"))
        rd = _f(_safe(info, "researchAndDevelopment"))

        iv, skew = self._options_iv_skew(t, info)

        return {
            "market_cap": market_cap,
            "cash": cash,
            "quarterly_burn": quarterly_burn,
            "rd_spend": rd,
            "runway_quarters": runway,
            "short_interest_pct": si,
            "iv": iv,
            "iv_skew": skew,
        }

    def _options_iv_skew(self, t, info) -> tuple[float | None, float | None]:
        """Best-effort ATM IV and put-call skew from the nearest expiry.

        Returns (None, None) when the chain is unavailable (common for
        thin-float names) — explicitly, not zero.
        """
        try:
            expiries = t.options
            if not expiries:
                return None, None
            chain = t.option_chain(expiries[0])
            spot = _f(_safe(info, "currentPrice", "regularMarketPrice"))
            if spot is None:
                return None, None
            calls, puts = chain.calls, chain.puts
            if calls is None or calls.empty or puts is None or puts.empty:
                return None, None
            atm_call = calls.iloc[(calls["strike"] - spot).abs().argmin()]
            atm_put = puts.iloc[(puts["strike"] - spot).abs().argmin()]
            iv_call = _f(atm_call.get("impliedVolatility"))
            iv_put = _f(atm_put.get("impliedVolatility"))
            if iv_call is None and iv_put is None:
                return None, None
            iv = None
            if iv_call is not None and iv_put is not None:
                iv = (iv_call + iv_put) / 2
            skew = None
            if iv_call is not None and iv_put is not None:
                skew = iv_put - iv_call  # positive = downside hedging / crowding
            return iv, skew
        except Exception as exc:  # noqa: BLE001
            logger.debug("options chain unavailable for thin name: %s", exc)
            return None, None


def _f(v):
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None
