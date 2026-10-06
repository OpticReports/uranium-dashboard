"""Data layer: parsers, cache, no-stale-fallback rule, declared splicing.
Network tests at the bottom are skipped unless --run-network."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from holygrail.data import (DataLoader, DataSeries, Provenance, parse_fred_csv, parse_yahoo_chart, splice_levels,
                            tbill_period_returns)
from holygrail.errors import DataError


def _payload(ts, close, adj=None, tz="America/New_York", gran="1d", reg=None):
    ind = {"quote": [{"close": close, "volume": [1] * len(close)}]}
    if adj is not None:
        ind["adjclose"] = [{"adjclose": adj}]
    meta = {"dataGranularity": gran, "exchangeTimezoneName": tz}
    if reg:
        meta["currentTradingPeriod"] = {"regular": reg}
    return {"chart": {"result": [{"meta": meta, "timestamp": ts, "indicators": ind}], "error": None}}


def _ts(dates, hour=14, minute=30):
    return [int(pd.Timestamp(d, tz="UTC").replace(hour=hour, minute=minute).timestamp()) for d in dates]


def test_parse_yahoo_adjclose_close_fallback_and_errors():
    ts = _ts(["2024-01-02", "2024-01-03", "2024-01-04"])
    s, info = parse_yahoo_chart(_payload(ts, [10, 11, 12], [9, 10, 11]), "X")
    assert list(s) == [9, 10, 11] and info["field"] == "adjclose" and info["total_return"]
    assert list(s.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))
    s2, info2 = parse_yahoo_chart(_payload(ts, [10, 11, 12]), "^IDX")
    assert info2["field"] == "close" and not info2["total_return"] and "NOT total return" in info2["warnings"][0]
    with pytest.raises(DataError, match="granularity"):
        parse_yahoo_chart(_payload(ts, [1, 2, 3], gran="1mo"), "X")
    with pytest.raises(DataError, match="error"):
        parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}, "X")
    with pytest.raises(DataError, match="mismatch"):
        parse_yahoo_chart(_payload(ts, [1, 2]), "X")
    s3, info3 = parse_yahoo_chart(_payload(ts, [10, None, 12], [9, None, 11]), "X")
    assert len(s3) == 2 and "null" in info3["warnings"][0]


def test_parse_yahoo_timezone_and_partial_session():
    # crypto prints at 00:00 UTC: date must stay the UTC date
    ts = _ts(["2024-01-06", "2024-01-07"], hour=0, minute=0)
    s, _ = parse_yahoo_chart(_payload(ts, [1, 2], [1, 2], tz="UTC"), "BTC-USD")
    assert list(s.index) == list(pd.to_datetime(["2024-01-06", "2024-01-07"]))
    ts = _ts(["2024-01-02", "2024-01-03", "2024-01-04"])
    reg = {"start": ts[-1] - 60, "end": ts[-1] + 6 * 3600}
    during = datetime.fromtimestamp(ts[-1] + 3600, tz=timezone.utc)
    s2, info = parse_yahoo_chart(_payload(ts, [1, 2, 3], [1, 2, 3], reg=reg), "X", now=during)
    assert len(s2) == 2 and "in progress" in info["warnings"][0]
    after = datetime.fromtimestamp(ts[-1] + 7 * 3600, tz=timezone.utc)
    assert len(parse_yahoo_chart(_payload(ts, [1, 2, 3], [1, 2, 3], reg=reg), "X", now=after)[0]) == 3


def test_parse_fred_csv():
    s = parse_fred_csv("observation_date,DTB3\n2024-01-02,5.2\n2024-01-03,.\n2024-01-04,5.1\n", "DTB3")
    assert list(s) == [5.2, 5.1]
    s2 = parse_fred_csv("DATE,X\n2024-01-01,1\n", "X")
    assert s2.iloc[0] == 1
    with pytest.raises(DataError, match="HTML"):
        parse_fred_csv("<!DOCTYPE html><html>", "NOPE")
    with pytest.raises(DataError, match="no numeric"):
        parse_fred_csv("observation_date,X\n2024-01-01,.\n", "X")


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._p, self.text = status, payload, text

    def json(self):
        return self._p


def _yahoo_get(calls):
    ts = _ts(["2024-01-02", "2024-01-03", "2024-01-04"])

    def get(url, params, timeout):
        calls.append(url)
        if "BAD" in url:
            return _Resp(404)
        if "FAIL" in url:
            raise ConnectionError("boom")
        return _Resp(200, _payload(ts, [10, 11, 12], [9, 10, 11]))
    return get


def test_loader_cache_and_no_stale_fallback(tmp_path):
    calls = []
    ld = DataLoader(tmp_path, http_get=_yahoo_get(calls), retries=2, backoff=0.01)
    ds = ld.yahoo("SPY")
    assert ds.provenance.source == "yahoo" and not ds.provenance.from_cache and len(calls) == 1
    assert (tmp_path / "yahoo" / "SPY.csv").exists()
    ld2 = DataLoader(tmp_path, http_get=_yahoo_get(calls))
    assert ld2.yahoo("SPY").provenance.from_cache and len(calls) == 1  # fresh cache, no fetch
    # make the cache stale, then let the feed fail: must raise, never serve the stale copy
    meta = tmp_path / "yahoo" / "SPY.meta.json"
    m = json.loads(meta.read_text())
    m["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    meta.write_text(json.dumps(m))
    def failing(url, params, timeout):
        raise ConnectionError("feed down")
    with pytest.raises(DataError, match="feed down"):
        DataLoader(tmp_path, http_get=failing, retries=2, backoff=0.01).yahoo("SPY")
    # offline mode reads the (stale) cache explicitly, with fetched_at visible
    off = DataLoader(tmp_path, offline=True, http_get=failing).yahoo("SPY")
    assert off.provenance.from_cache and off.provenance.fetched_at == m["fetched_at"]
    with pytest.raises(DataError, match="offline"):
        DataLoader(tmp_path, offline=True, http_get=failing).yahoo("QQQ")
    n = len(calls)
    with pytest.raises(DataError, match="404"):
        DataLoader(tmp_path, http_get=_yahoo_get(calls), retries=3, backoff=0.01).yahoo("BAD")
    assert len(calls) == n + 1  # 404 is not retried


def _ds(s, ident):
    return DataSeries(s, Provenance("yahoo", ident, None, "adjclose", True, str(s.index[0].date()),
                                    str(s.index[-1].date()), len(s)))


def test_declared_splice():
    idx = pd.bdate_range("2020-01-01", periods=10)
    proxy = pd.Series(np.linspace(50, 59, 10), index=idx)
    primary = pd.Series([200.0, 202.0, 201.0, 205.0], index=idx[6:])
    out = splice_levels(_ds(primary, "NEW"), _ds(proxy, "OLD"), idx[6], note="declared")
    lv = out.values
    assert lv.loc[idx[6]:].equals(primary)
    pr = lv.pct_change().loc[idx[1]:idx[6]]
    np.testing.assert_allclose(pr.to_numpy(), proxy.pct_change().loc[idx[1]:idx[6]].to_numpy())  # proxy returns kept
    assert out.provenance.proxies[0]["proxy"] == "OLD" and out.provenance.proxies[0]["used_before"] == str(idx[6].date())
    with pytest.raises(DataError):
        splice_levels(_ds(primary, "NEW"), _ds(proxy.loc[idx[6]:], "OLD"), idx[6])
    with pytest.raises(DataError):
        splice_levels(_ds(primary, "NEW"), _ds(proxy, "OLD"), "2021-01-01")


def test_tbill_period_returns_no_lookahead():
    rate = pd.Series([5.0, 4.0, 3.0], index=pd.to_datetime(["2024-01-02", "2024-01-05", "2024-01-08"]))
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-08", "2024-01-09"])
    r = tbill_period_returns(rate, idx)
    assert r.iloc[1] == pytest.approx(0.05 * 1 / 360)
    assert r.iloc[2] == pytest.approx(0.05 * 5 / 360)    # rate known on 01-03 (5%), not 01-05's 4%
    assert r.iloc[3] == pytest.approx(0.03 * 1 / 360)
    with pytest.raises(DataError):
        tbill_period_returns(rate, pd.to_datetime(["2023-12-01", "2024-01-03"]))


# ------------------------------------------------------------- network ----
@pytest.mark.network
def test_network_yahoo_equity_and_crypto(tmp_path):
    ld = DataLoader(tmp_path)
    spy = ld.yahoo("SPY")
    assert spy.provenance.field == "adjclose" and spy.provenance.first_date <= "1993-02-01"
    assert spy.values.index.is_monotonic_increasing and (spy.values > 0).all() and len(spy.values) > 8000
    btc = ld.yahoo("BTC-USD")
    assert btc.values.index.dayofweek.max() == 6  # trades weekends
    with pytest.raises(DataError):
        ld.yahoo("NOPE_NOT_A_SYMBOL_XX")


@pytest.mark.network
def test_network_fred(tmp_path):
    ld = DataLoader(tmp_path)
    d = ld.fred("DTB3")
    assert d.values.index[0] <= pd.Timestamp("1954-01-04") and 0 <= d.values.iloc[-1] < 20
    cpi = ld.fred("CPIAUCSL").values
    gaps = pd.Series(cpi.index).diff().dt.days.dropna()
    assert 28 <= gaps.median() <= 31                                  # monthly cadence
    assert (pd.Timestamp.now() - cpi.index[-1]).days <= 90            # current (released ~2 weeks after month end)
    with pytest.raises(DataError):
        ld.fred("NOPE_SERIES_XX")
