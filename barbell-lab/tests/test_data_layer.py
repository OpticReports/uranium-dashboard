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
        proxy_dates = pd.bdate_range("2019-09-20", "2019-09-30")
        proxy_px = [100, 101, 99, 100, 102, 103, 104]
        _insert(con, "DFSVX", proxy_dates[: len(proxy_px)], proxy_px)
        live_dates = pd.bdate_range("2019-10-01", "2019-10-07")
        live_px = [50, 50.5, 51, 50, 52][: len(live_dates)]
        _insert(con, "AVUV", live_dates[: len(live_px)], live_px)

        bs = total_return_series(con, "AVUV")
        f = bs.frame
        # provenance split
        assert (f.loc[: "2019-09-30", "provenance"] == "proxy:DFSVX").all()
        assert (f.loc["2019-10-01":, "provenance"] == "live").all()
        # chained backwards from the live anchor (50) with proxy returns
        pre = f.loc[: "2019-09-30", "close_adj"]
        expected_last_pre = 50 / (104 / 103)  # anchor / (1 + last proxy return)
        assert np.isclose(pre.iloc[-1], expected_last_pre)
        # proxy return sequence preserved exactly
        got = pre.pct_change().dropna().values
        want = pd.Series(proxy_px).pct_change().dropna().values[:-1]
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
