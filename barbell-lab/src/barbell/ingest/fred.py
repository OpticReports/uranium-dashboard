"""FRED series ingestion.

Uses the official API (api.stlouisfed.org) when FRED_API_KEY is set (the
treasury-canary service already provisions one); otherwise falls back to the
public fredgraph.csv endpoint, which needs no key and serves the same daily
observations. Either path failing raises — no silent gaps.
"""
from __future__ import annotations

import io

import httpx
import pandas as pd

from .base import ProviderError, env_key

_API = "https://api.stlouisfed.org/fred/series/observations"
_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch_series(series_id: str, start: str, end: str) -> pd.Series:
    key = env_key("FRED_API_KEY")
    if key:
        return _via_api(series_id, start, end, key)
    return _via_csv(series_id, start, end)


def _via_api(series_id: str, start: str, end: str, key: str) -> pd.Series:
    params = {
        "series_id": series_id, "api_key": key, "file_type": "json",
        "observation_start": start, "observation_end": end,
    }
    try:
        r = httpx.get(_API, params=params, timeout=60.0)
        r.raise_for_status()
        obs = r.json().get("observations", [])
    except httpx.HTTPError as exc:
        raise ProviderError(f"fred:{series_id} api failed: {exc}") from exc
    if not obs:
        raise ProviderError(f"fred:{series_id} returned no observations")
    df = pd.DataFrame(obs)
    s = pd.to_numeric(df["value"], errors="coerce")
    s.index = pd.to_datetime(df["date"])
    return s.rename(series_id)


def _via_csv(series_id: str, start: str, end: str) -> pd.Series:
    params = {"id": series_id, "cosd": start, "coed": end}
    try:
        r = httpx.get(_CSV, params=params, timeout=60.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError(f"fred:{series_id} csv failed: {exc}") from exc
    df = pd.read_csv(io.StringIO(r.text))
    if df.empty or df.shape[1] != 2:
        raise ProviderError(f"fred:{series_id} csv returned unexpected shape {df.shape}")
    date_col, val_col = df.columns[0], df.columns[1]
    s = pd.to_numeric(df[val_col], errors="coerce")  # FRED encodes missing as "."
    s.index = pd.to_datetime(df[date_col])
    return s.rename(series_id)
