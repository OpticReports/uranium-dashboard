"""Data layer: Yahoo chart API (keyless) and FRED CSV, with an on-disk cache
and provenance on every series.

Rules:
  * A failed feed FAILS LOUDLY (DataError).  There is no stale fallback: if a
    refresh is due and the fetch fails, the cached copy is NOT served.
  * ``offline=True`` is an explicit mode that reads the cache only (any age)
    and raises when an entry is missing; provenance records fetched_at so the
    staleness is visible.
  * Proxies are spliced ONLY when declared with an explicit date
    (splice_levels / DataLoader.market_levels(proxies=...)).  Never silently.
  * Yahoo ``adjclose`` is split- and dividend-adjusted (total return).  A
    PRICE INDEX (meta.instrumentType INDEX, or a '^' symbol such as ^GSPC)
    is price-only: Yahoo's adjclose for it just repeats the close, so it is
    labelled total_return=False with a warning; so is any symbol without an
    adjclose.  A splice inherits total_return=False from either side.
"""
from __future__ import annotations

import io
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .errors import DataError, ValidationError

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "data" / "cache"
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) holygrail-engine/0.1"}


@dataclass
class Provenance:
    """Where a series came from.  Attached to every DataSeries."""
    source: str                 # yahoo | fred | user | spliced
    identifier: str             # symbol / series id
    url: str | None
    field: str                  # adjclose | close | value
    total_return: bool | None   # True for adjclose; False for price-only; None for macro
    first_date: str
    last_date: str
    n_obs: int
    fetched_at: str | None = None
    from_cache: bool = False
    proxies: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Plain-dict form (cache metadata / JSON)."""
        return asdict(self)


@dataclass
class DataSeries:
    """A validated level/value series plus its provenance."""
    values: pd.Series
    provenance: Provenance


# --------------------------------------------------------------------------- #
# parsers (pure; tested offline with canned payloads)
# --------------------------------------------------------------------------- #
def parse_yahoo_chart(payload: dict, symbol: str, *, now: datetime | None = None) -> tuple[pd.Series, dict]:
    """Parse a v8 chart payload into a daily level Series (exchange-local
    dates).  Returns (series, info) with info = {field, total_return,
    warnings, timezone}.  Raises DataError on: missing result, error object,
    non-daily granularity, no timestamps, length mismatch.  Drops a final bar
    that belongs to a session still in progress (partial day)."""
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        raise DataError(f"yahoo:{symbol} error {chart['error']}")
    res = chart.get("result")
    if not res:
        raise DataError(f"yahoo:{symbol} returned no result")
    res = res[0]
    meta = res.get("meta") or {}
    gran = meta.get("dataGranularity")
    if gran is not None and gran != "1d":
        raise DataError(f"yahoo:{symbol} granularity {gran!r}, expected '1d' (do not use range=max)")
    ts = res.get("timestamp")
    if not ts:
        raise DataError(f"yahoo:{symbol} returned no timestamps")
    ind = res.get("indicators") or {}
    quote = (ind.get("quote") or [{}])[0]
    close = quote.get("close")
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose") if ind.get("adjclose") else None
    warnings = []
    is_index = str(meta.get("instrumentType") or "").upper() == "INDEX" or symbol.startswith("^")
    if is_index and (close is not None or adj is not None):
        vals, fld, tr = (close if close is not None else adj), "close", False
        warnings.append(f"price index ({symbol}, instrumentType {meta.get('instrumentType') or 'n/a'}): price-only, "
                        "NOT total return (Yahoo adjclose of an index equals its close; dividends are missing)")
    elif adj is not None:
        vals, fld, tr = adj, "adjclose", True
    elif close is not None:
        vals, fld, tr = close, "close", False
        warnings.append("no adjclose: raw close used (price-only, NOT total return)")
    else:
        raise DataError(f"yahoo:{symbol} has neither adjclose nor close")
    if len(vals) != len(ts):
        raise DataError(f"yahoo:{symbol} length mismatch ({len(vals)} values vs {len(ts)} timestamps)")
    tz = meta.get("exchangeTimezoneName") or "America/New_York"
    idx = pd.to_datetime(np.asarray(ts, dtype="int64"), unit="s", utc=True).tz_convert(tz)
    dates = idx.tz_localize(None).normalize()
    s = pd.Series(pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(dtype=float), index=dates)
    # partial session: last bar inside the current regular period that has not ended
    reg = ((meta.get("currentTradingPeriod") or {}).get("regular") or {})
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    if reg.get("start") is not None and reg.get("end") is not None:
        if reg["start"] <= ts[-1] < reg["end"] and now_ts < reg["end"]:
            s = s.iloc[:-1]
            warnings.append("dropped final bar: session in progress")
    s = s[~s.index.duplicated(keep="last")]
    n_nan = int(s.isna().sum())
    if n_nan:
        warnings.append(f"dropped {n_nan} null bars")
    s = s.dropna().sort_index()
    if (s <= 0).any():
        raise DataError(f"yahoo:{symbol} has non-positive levels")
    if len(s) < 2:
        raise DataError(f"yahoo:{symbol} has fewer than 2 usable bars")
    jumps = s.pct_change().abs()
    if (jumps > 0.5).any():
        warnings.append(f"{int((jumps > 0.5).sum())} daily moves > 50% (check splits/data) - not altered")
    return s.rename(symbol), {"field": fld, "total_return": tr, "warnings": warnings, "timezone": tz}


def parse_fred_csv(text: str, series_id: str) -> pd.Series:
    """Parse fredgraph.csv output (header 'observation_date,<ID>' or legacy
    'DATE,<ID>'; missing values '.' or empty) into a float Series."""
    if not text or "<html" in text[:200].lower():
        raise DataError(f"fred:{series_id} returned HTML/empty (unknown series?)")
    try:
        df = pd.read_csv(io.StringIO(text), na_values=[".", ""])
    except Exception as e:  # pragma: no cover - pandas parser error types vary
        raise DataError(f"fred:{series_id} CSV parse failed: {e}") from None
    if df.shape[1] < 2:
        raise DataError(f"fred:{series_id} CSV has {df.shape[1]} columns")
    date_col = df.columns[0]
    if date_col not in ("observation_date", "DATE"):
        raise DataError(f"fred:{series_id} unexpected date column {date_col!r}")
    col = series_id if series_id in df.columns else df.columns[1]
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float),
                  index=pd.DatetimeIndex(pd.to_datetime(df[date_col])).normalize(), name=series_id)
    s = s.dropna().sort_index()
    if s.empty:
        raise DataError(f"fred:{series_id} has no numeric observations")
    return s


# --------------------------------------------------------------------------- #
# splicing and rates
# --------------------------------------------------------------------------- #
def splice_levels(primary: DataSeries, proxy: DataSeries, until, note: str = "", *,
                  max_gap_days: int = 7) -> DataSeries:
    """Declared splice: proxy RETURNS strictly before ``until``, primary from
    ``until`` on, chained so the level is continuous at the splice.  The
    splice date d0 is the first primary observation >= ``until``; the proxy
    must reach it: its last observation on or before d0 must be within
    ``max_gap_days`` calendar days of d0 (a weekend or holiday), otherwise a
    proxy that stopped printing would add a silent 0% return across the gap
    (DataError).  Provenance records proxy, date and both sources."""
    until = pd.Timestamp(until).normalize()
    p, x = primary.values, proxy.values
    after = p.loc[p.index >= until]
    if after.empty:
        raise DataError(f"splice: primary {primary.provenance.identifier} has no data on/after {until.date()}")
    d0 = after.index[0]
    xb = x.loc[x.index <= d0]
    if len(xb) < 2 or xb.index[0] >= d0:
        raise DataError(f"splice: proxy {proxy.provenance.identifier} does not cover dates before {d0.date()}")
    gap = (d0 - xb.index[-1]).days
    if gap > max_gap_days:
        raise DataError(f"splice: proxy {proxy.provenance.identifier} stops at {xb.index[-1].date()}, a {gap}-day gap "
                        f"before the splice date {d0.date()} (> {max_gap_days}); the gap would be a silent 0% return. "
                        f"Move 'until' to on/before {xb.index[-1].date()} or use a proxy that reaches the splice")
    # proxy levels rescaled to equal the primary at d0 (as-of proxy level at d0)
    scale = after.iloc[0] / xb.iloc[-1]
    pre = xb.loc[xb.index < d0] * scale
    out = pd.concat([pre, after]).sort_index()
    prov = Provenance(
        source="spliced", identifier=primary.provenance.identifier, url=primary.provenance.url,
        field=primary.provenance.field,
        total_return=(primary.provenance.total_return and proxy.provenance.total_return),
        first_date=str(out.index[0].date()), last_date=str(out.index[-1].date()), n_obs=len(out),
        fetched_at=primary.provenance.fetched_at, from_cache=primary.provenance.from_cache,
        proxies=list(primary.provenance.proxies) + [{
            "proxy": proxy.provenance.identifier, "used_before": str(d0.date()),
            "proxy_first_date": proxy.provenance.first_date, "note": note}],
        warnings=list(primary.provenance.warnings) + [f"proxy {proxy.provenance.identifier}: {w}"
                                                      for w in proxy.provenance.warnings])
    return DataSeries(out.rename(primary.provenance.identifier), prov)


def tbill_period_returns(rate_pct: pd.Series, index: pd.DatetimeIndex, *, day_count: float = 360.0) -> pd.Series:
    """Per-period cash return on ``index`` from an annualised rate in PERCENT
    (e.g. FRED DTB3): r_t = rate_{t-1}/100 * (days(t) - days(t-1)) / day_count,
    using the last rate published on or before t-1 (no lookahead; actual/360
    money-market convention; the discount-vs-investment-yield difference is
    ignored).  The first date gets the rate known on it times one median period."""
    rate = pd.Series(rate_pct, dtype=float).dropna().sort_index()
    if rate.empty:
        raise DataError("rate series is empty")
    idx = pd.DatetimeIndex(index)
    if idx[0] < rate.index[0]:
        raise DataError(f"rate series starts {rate.index[0].date()}, after the first date {idx[0].date()}")
    asof = rate.reindex(rate.index.union(idx)).ffill().reindex(idx)
    prev = asof.shift(1)
    days = pd.Series(idx, index=idx).diff().dt.days.astype(float)
    med = float(days.median()) if len(idx) > 1 else 1.0
    prev.iloc[0] = asof.iloc[0]
    days.iloc[0] = med
    return (prev / 100.0 * days / day_count).rename("rf")


# --------------------------------------------------------------------------- #
# loader with cache
# --------------------------------------------------------------------------- #
def _default_get(url: str, params: dict, timeout: float):
    import httpx
    return httpx.get(url, params=params, headers=_HEADERS, timeout=timeout, follow_redirects=True)


class DataLoader:
    """Fetch + cache.  ``http_get(url, params, timeout)`` is injectable for
    tests (must return an object with .status_code, .text, .json()).

    cache layout: <cache_dir>/<source>/<id>.csv and <id>.meta.json.
    A cache entry is used when it is younger than ``max_age_hours`` (or
    always, in offline mode).  Otherwise the feed is fetched; any failure
    raises DataError (no stale fallback)."""

    def __init__(self, cache_dir: str | Path | None = None, *, max_age_hours: float = 18.0,
                 offline: bool = False, http_get: Callable | None = None, timeout: float = 30.0,
                 retries: int = 3, backoff: float = 1.5):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        self.max_age = max_age_hours * 3600.0
        self.offline = offline
        self.http_get = http_get or _default_get
        self.timeout = timeout
        self.retries = max(1, retries)
        self.backoff = backoff
        self._mem: dict[tuple, DataSeries] = {}

    # ---- cache -------------------------------------------------------------
    def _paths(self, source: str, ident: str) -> tuple[Path, Path]:
        safe = "".join(ch if ch.isalnum() or ch in "-_.=" else "_" for ch in ident)
        d = self.cache_dir / source
        return d / f"{safe}.csv", d / f"{safe}.meta.json"

    def _read_cache(self, source, ident) -> DataSeries | None:
        csv, meta = self._paths(source, ident)
        if not (csv.exists() and meta.exists()):
            return None
        m = json.loads(meta.read_text())
        df = pd.read_csv(csv, parse_dates=["date"])
        s = pd.Series(df["value"].to_numpy(float), index=pd.DatetimeIndex(df["date"]), name=ident)
        prov = Provenance(**{**m, "from_cache": True})
        return DataSeries(s, prov)

    def _write_cache(self, source, ident, ds: DataSeries) -> None:
        csv, meta = self._paths(source, ident)
        csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": ds.values.index.strftime("%Y-%m-%d"), "value": ds.values.to_numpy()}).to_csv(csv, index=False)
        meta.write_text(json.dumps(ds.provenance.to_dict(), indent=1, default=str))

    def _fresh(self, ds: DataSeries) -> bool:
        if ds.provenance.fetched_at is None:
            return False
        t = datetime.fromisoformat(ds.provenance.fetched_at).timestamp()
        return (time.time() - t) <= self.max_age

    def _get(self, url, params, what):
        last = None
        for attempt in range(self.retries):
            try:
                r = self.http_get(url, params, self.timeout)
                if r.status_code == 404:
                    raise DataError(f"{what}: HTTP 404 (unknown symbol/series)")
                if r.status_code != 200:
                    raise DataError(f"{what}: HTTP {r.status_code}")
                return r
            except DataError as e:
                last = e
                if "404" in str(e):
                    break
            except Exception as e:  # network errors of any client
                last = DataError(f"{what}: {type(e).__name__}: {e}")
            if attempt + 1 < self.retries:
                time.sleep(self.backoff ** attempt)
        raise last

    def _cached_or_fetch(self, source, ident, fetch) -> DataSeries:
        key = (source, ident)
        if key in self._mem:
            return self._mem[key]
        cached = self._read_cache(source, ident)
        if self.offline:
            if cached is None:
                raise DataError(f"{source}:{ident} not in cache {self.cache_dir} and offline=True")
            self._mem[key] = cached
            return cached
        if cached is not None and self._fresh(cached):
            self._mem[key] = cached
            return cached
        ds = fetch()  # raises on failure; the stale cache is NOT used
        self._write_cache(source, ident, ds)
        self._mem[key] = ds
        return ds

    # ---- feeds -------------------------------------------------------------
    def yahoo(self, symbol: str) -> DataSeries:
        """Full daily history of ``symbol`` (adjclose; period1=0)."""
        def fetch():
            url = YAHOO_URL.format(symbol=symbol)
            params = {"period1": 0, "period2": int(time.time()) + 86400, "interval": "1d",
                      "events": "div,split", "includeAdjustedClose": "true"}
            r = self._get(url, params, f"yahoo:{symbol}")
            try:
                payload = r.json()
            except Exception as e:
                raise DataError(f"yahoo:{symbol} non-JSON response: {e}") from None
            s, info = parse_yahoo_chart(payload, symbol)
            prov = Provenance("yahoo", symbol, url, info["field"], info["total_return"],
                              str(s.index[0].date()), str(s.index[-1].date()), len(s),
                              fetched_at=datetime.now(timezone.utc).isoformat(), warnings=info["warnings"])
            return DataSeries(s, prov)
        return self._cached_or_fetch("yahoo", symbol, fetch)

    def fred(self, series_id: str) -> DataSeries:
        """Full history of a FRED series (fredgraph.csv?id=...)."""
        def fetch():
            r = self._get(FRED_URL, {"id": series_id}, f"fred:{series_id}")
            s = parse_fred_csv(r.text, series_id)
            prov = Provenance("fred", series_id, f"{FRED_URL}?id={series_id}", "value", None,
                              str(s.index[0].date()), str(s.index[-1].date()), len(s),
                              fetched_at=datetime.now(timezone.utc).isoformat())
            return DataSeries(s, prov)
        return self._cached_or_fetch("fred", series_id, fetch)

    def market_levels(self, symbol: str, proxies=()) -> DataSeries:
        """Yahoo levels for ``symbol`` with DECLARED proxies applied, most
        recent splice first: each proxy (symbol, until) supplies returns before
        ``until``."""
        ds = self.yahoo(symbol)
        for p in sorted(proxies, key=lambda p: pd.Timestamp(p.until), reverse=True):
            ds = splice_levels(ds, self.yahoo(p.symbol), p.until, getattr(p, "note", ""))
        return ds

    def stream_levels(self, universe, names) -> tuple[pd.DataFrame, dict]:
        """Levels DataFrame + provenance for the EMPIRICAL leaves of ``names``
        (market streams via Yahoo, series streams as supplied)."""
        from .streams import MarketStream, SeriesStream
        emp, _ = universe.leaves(names)
        cols, prov = {}, {}
        for e in emp:
            s = universe[e]
            if isinstance(s, MarketStream):
                ds = self.market_levels(s.symbol, s.proxies)
                cols[e], prov[e] = ds.values, ds.provenance.to_dict()
            elif isinstance(s, SeriesStream):
                cols[e] = s.levels
                prov[e] = Provenance("user", e, None, "level", None, str(s.levels.index[0].date()),
                                     str(s.levels.index[-1].date()), len(s.levels),
                                     warnings=[f"source: {s.source}"]).to_dict()
            else:  # pragma: no cover - leaves() returns empirical only
                raise ValidationError(f"{e} is not empirical")
            gaps = pd.Series(cols[e].dropna().index).diff().dt.days.dropna()
            prov[e]["native_median_gap_days"] = float(gaps.median()) if len(gaps) else None
        if not cols:
            return pd.DataFrame(), prov
        return pd.DataFrame(cols).sort_index(), prov
