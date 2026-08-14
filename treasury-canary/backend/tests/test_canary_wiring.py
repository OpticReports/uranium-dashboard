"""Regression tests for the two in-process canary hooks that were silently
broken (EWM board and shock-sim stress-transition input). Both previously
swallowed a TypeError and degraded to hardcoded fallbacks (0.25 / 0.3)
forever. These tests exercise the real call paths offline."""
from datetime import date, timedelta

import numpy as np


class _FakeComposite:
    def __init__(self, score, coverage):
        self.score = score
        self.coverage = coverage


def test_ewm_canary01_reads_composite(monkeypatch):
    import app.jobs.refresh as refresh
    import app.sources.fred as fred
    from app.ewm.api import _canary01

    monkeypatch.setattr(fred, "fetch_bundle", lambda: {"stub": ([], [])})
    monkeypatch.setattr(refresh, "compute_all",
                        lambda bundle, auctions=None: ([], {}, _FakeComposite(42.0, 0.9), []))
    assert _canary01() == 0.42


def test_ewm_canary01_degrades_on_low_coverage(monkeypatch):
    import app.jobs.refresh as refresh
    import app.sources.fred as fred
    from app.ewm.api import _canary01

    monkeypatch.setattr(fred, "fetch_bundle", lambda: {"stub": ([], [])})
    monkeypatch.setattr(refresh, "compute_all",
                        lambda bundle, auctions=None: ([], {}, _FakeComposite(0.0, 0.07), []))
    assert _canary01() is None                # board falls back, not "all calm"


def _synth_bundle(n=120, spread=-0.5):
    """10y and 3mo tenors with an inverted 3m10y spread and mild 10y vol."""
    d0 = date(2026, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(n)]
    rng = np.random.default_rng(5)
    v10 = list(4.0 + np.cumsum(rng.normal(0, 0.02, n)))
    v3 = [x - spread for x in v10]            # 3mo = 10y - spread
    return {"10y": (dates, v10), "3mo": (dates, v3)}


def test_shock_sim_canary01_no_fallback(monkeypatch):
    import app.api.routes_shock_sim as rss

    def _boom(*a, **k):                       # any swallowed error -> test fails
        raise AssertionError(f"canary01 hit the fallback path: {a}")

    monkeypatch.setattr(rss.logger, "warning", _boom)
    v = rss._canary01(_synth_bundle())
    assert 0.0 <= v <= 1.0
    # inverted curve => probit meaningfully above zero => not the 0.3 constant
    v_steep = rss._canary01(_synth_bundle(spread=1.5))
    assert v > v_steep                        # inversion scores riskier than steep
