"""Module 1 tests: splice mechanics, provenance, validation checks, and the
live acceptance gates (network-marked)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from barbell import db
from barbell.ingest.series import total_return_series
from barbell.validate.checks import ValidationReport, check_overnight_gaps


def _insert(con, ticker, dates, closes, source="yahoo"):
    df = pd.DataFrame(
        {
            "ticker": ticker,
            "date": [d.strftime("%Y-%m-%d") for d in dates],
            "close_adj": closes,
            "close_raw": closes,
            "volume": 1000,
            "source": source,
        }
    )
    db.upsert_prices(con, df)


@pytest.fixture()
def con(tmp_path):
    return db.connect(tmp_path / "t.db")


class TestSplice:
    def test_proxy_extension_uses_returns_not_levels(self, con):
        # AVUV is declared in config with proxy DFSVX, splice 2019-10-01.
        # Proxy trades at a wildly different price level; only its RETURNS
        # may cross the splice boundary.
        proxy_dates = pd.bdate_range("2019-09-20", "2019-10-01")
        proxy_px = [100, 101, 99, 100, 102, 103, 104, 106]
        _insert(con, "DFSVX", proxy_dates[: len(proxy_px)], proxy_px)
        live_dates = pd.bdate_range("2019-10-01", "2019-10-07")
        live_px = [50, 50.5, 51, 50, 52][: len(live_dates)]
        _insert(con, "AVUV", live_dates[: len(live_px)], live_px)

        bs = total_return_series(con, "AVUV")
        f = bs.frame
        # provenance split
        assert (f.loc[: "2019-09-30", "provenance"] == "proxy:DFSVX").all()
        assert (f.loc["2019-10-01":, "provenance"] == "live").all()
        # chained backwards from the live anchor (50) with proxy returns:
        # the last pre-splice level carries the proxy's SPLICE-DAY return
        pre = f.loc[: "2019-09-30", "close_adj"]
        expected_last_pre = 50 / (106 / 104)
        assert np.isclose(pre.iloc[-1], expected_last_pre)
        # proxy return sequence preserved exactly (none dropped)
        got = f["close_adj"].pct_change().dropna().values[: len(proxy_px) - 1]
        want = pd.Series(proxy_px).pct_change().dropna().values
        assert np.allclose(got, want)

    def test_no_proxy_ticker_is_pure_live(self, con):
        dates = pd.bdate_range("2020-01-01", periods=5)
        _insert(con, "SPY", dates, [300, 301, 302, 301, 303])
        bs = total_return_series(con, "SPY")
        assert bs.proxy is None
        assert (bs.frame["provenance"] == "live").all()

    def test_undeclared_ticker_refused(self, con):
        _insert(con, "ZZZT", pd.bdate_range("2020-01-01", periods=3), [1, 2, 3])
        with pytest.raises(Exception, match="not declared"):
            total_return_series(con, "ZZZT")


class TestSpliceAlignment:
    """Pins same-day alignment of proxy returns across the splice (the
    original backward chain shifted every pre-splice return by one day)."""

    # distinct, non-repeating daily returns so any shift is detectable
    PROXY_RETS = [0.010, -0.020, 0.030, -0.005, 0.015, 0.025, -0.012,
                  0.007, -0.031, 0.022, 0.004, -0.017]

    def _proxy(self, start="2019-09-13", drop=()):
        dates = pd.bdate_range(start, periods=len(self.PROXY_RETS) + 1)
        px = 200.0 * np.cumprod([1.0] + [1 + r for r in self.PROXY_RETS])
        s = pd.Series(px, index=dates)
        return s.drop([pd.Timestamp(d) for d in drop])

    def _live(self, dates, start_px=40.0):
        rets = [0.003, -0.004, 0.006, -0.002, 0.005, 0.001, -0.003]
        px = start_px * np.cumprod([1.0] + rets[: len(dates) - 1])
        return pd.Series(px, index=dates)

    def test_pre_splice_returns_are_same_day_proxy_returns(self, con):
        proxy = self._proxy()                       # 2019-09-13 .. 2019-10-01
        assert pd.Timestamp("2019-10-01") in proxy.index
        live = self._live(pd.bdate_range("2019-10-01", periods=6))
        _insert(con, "DFSVX", proxy.index, proxy.values)
        _insert(con, "AVUV", live.index, live.values)

        f = total_return_series(con, "AVUV").frame
        eff = pd.Timestamp("2019-10-01")
        assert f.index.is_unique and f.index.is_monotonic_increasing
        # every proxy date before the splice is present (no dropped row)
        pre_dates = proxy.index[proxy.index < eff]
        assert list(f.index[f.index < eff]) == list(pre_dates)
        assert (f.loc[f.index < eff, "provenance"] == "proxy:DFSVX").all()

        sret = f["close_adj"].pct_change()
        pret = proxy.pct_change()
        # same-day alignment on every pre-splice date with a return
        for d in pre_dates[1:]:
            assert np.isclose(sret[d], pret[d]), d
        # splice day carries the proxy's splice-day return, once
        assert np.isclose(sret[eff], pret[eff])
        # level continuity: the live anchor is untouched at the splice
        assert f.at[eff, "close_adj"] == live[eff]
        assert np.isclose(f.loc[f.index < eff, "close_adj"].iloc[-1],
                          live[eff] / (1 + pret[eff]))
        # live returns after the splice untouched
        post = f.loc[f.index > eff]
        assert (post["provenance"] == "live").all()
        assert np.allclose(sret[post.index], live.pct_change()[post.index])
        # compounded pre+splice growth == proxy growth over the same span
        assert np.isclose(f.at[eff, "close_adj"] / f["close_adj"].iloc[0],
                          proxy[eff] / proxy.iloc[0])
        # the lag signature is gone: not correlated 1.0 with previous day
        common = pre_dates[2:]
        lag_corr = np.corrcoef(sret[common], pret.shift(1)[common])[0, 1]
        assert lag_corr < 0.9

    def test_proxy_missing_a_pre_splice_day(self, con):
        # proxy has no print on 2019-09-24; live calendar is complete
        proxy = self._proxy(drop=["2019-09-24"])
        live = self._live(pd.bdate_range("2019-10-01", periods=6))
        _insert(con, "DFSVX", proxy.index, proxy.values)
        _insert(con, "AVUV", live.index, live.values)

        f = total_return_series(con, "AVUV").frame
        assert pd.Timestamp("2019-09-24") not in f.index
        sret = f["close_adj"].pct_change()
        # the gap return spans two sessions, attributed to the next print
        want = proxy[pd.Timestamp("2019-09-25")] / proxy[pd.Timestamp("2019-09-23")] - 1
        assert np.isclose(sret[pd.Timestamp("2019-09-25")], want)
        pret = proxy.pct_change()
        eff = pd.Timestamp("2019-10-01")
        for d in proxy.index[(proxy.index < eff)][1:]:
            assert np.isclose(sret[d], pret[d]), d
        assert np.isclose(sret[eff], pret[eff])
        assert f.at[eff, "close_adj"] == live[eff]

    def test_proxy_missing_splice_day_bridges_with_live(self, con):
        # proxy has no print ON the splice day; live trades from 2019-09-26,
        # so its own 09-30 -> 10-01 return bridges the boundary
        proxy = self._proxy(drop=["2019-10-01"])
        live = self._live(pd.bdate_range("2019-09-26", periods=7))
        _insert(con, "DFSVX", proxy.index, proxy.values)
        _insert(con, "AVUV", live.index, live.values)

        f = total_return_series(con, "AVUV").frame
        eff = pd.Timestamp("2019-10-01")
        sret = f["close_adj"].pct_change()
        assert np.isclose(sret[eff], live[eff] / live[pd.Timestamp("2019-09-30")] - 1)
        pret = proxy.pct_change()
        for d in proxy.index[proxy.index < eff][1:]:
            assert np.isclose(sret[d], pret[d]), d
        assert f.at[eff, "close_adj"] == live[eff]
        assert f.index.is_unique

    def test_splice_day_return_unknowable_refuses(self, con):
        # no proxy print on the splice day AND no live print before it:
        # the boundary return is unknown -> fail visibly, never guess
        proxy = self._proxy(drop=["2019-10-01"])
        live = self._live(pd.bdate_range("2019-10-01", periods=5))
        _insert(con, "DFSVX", proxy.index, proxy.values)
        _insert(con, "AVUV", live.index, live.values)
        with pytest.raises(Exception, match="splice-day return"):
            total_return_series(con, "AVUV")


class TestValidation:
    def test_gap_detection_fires(self, con):
        dates = pd.bdate_range("2020-01-01", periods=6)
        _insert(con, "QUAL", dates, [100, 101, 100, 130, 131, 130])  # +30% print
        rep = ValidationReport()
        check_overnight_gaps(con, "QUAL", rep)
        assert not rep.ok
        assert "2020-01-06" in rep.results[0].detail

    def test_explained_gap_is_allowlisted(self, con):
        # PSLV 2011-09-23 is in config explained_gaps.
        dates = [pd.Timestamp(d) for d in
                 ["2011-09-21", "2011-09-22", "2011-09-23", "2011-09-26"]]
        _insert(con, "PSLV", dates, [19.04, 17.37, 14.52, 14.40])
        rep = ValidationReport()
        check_overnight_gaps(con, "PSLV", rep)
        assert rep.ok, rep.results[0].detail


@pytest.mark.network
class TestAcceptanceGates:
    """The four hard gates from the spec, against the real ingested store.
    Run `barbell ingest` first; skips (visibly) if no store exists."""

    def test_gates(self):
        if not db.DB_PATH.exists():
            pytest.skip("no ingested data store — run `barbell ingest`")
        from barbell.validate.acceptance import run_gates
        con = db.connect()
        gates = run_gates(con)
        for g in gates:
            assert g.passed, str(g)
