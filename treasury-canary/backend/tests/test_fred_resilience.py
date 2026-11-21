"""Merge-blocking gates: one failed FRED call never blanks a series for hours (2026-11-21).

Casey saw the yield-curve chart with no NBER recession bands, the composite's recession probability at
"n/a" and the curve tile at 16.4% (the static Estrella-Mishkin fallback at a 0.70 spread) while every
endpoint answered 200. Cause: fetch_series returned an EMPTY series when a FRED call failed, ignoring the
good copy on disk; fetch_bundle memoized that hole for 6 h; build_models returned {} without USREC and
_ensure_fit treated {} as a fit for another 6 h. Each gate fails if its fix is removed.
"""
from __future__ import annotations

import json
import os
import time

from app.api import routes_composite as rc
from app.metrics import recession_model as rm
from app.sources import fred

OBS = {"observations": [{"date": "2020-03-01", "value": "1"}, {"date": "2020-04-01", "value": "1"},
                        {"date": "2020-05-01", "value": "0"}]}


def _key_and_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fred.settings, "fred_api_key", "test-key")
    monkeypatch.setattr(fred.settings, "cache_dir", str(tmp_path))


def test_a_failed_fetch_serves_the_last_good_copy(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    path = fred._cache_path("USREC", "1976-01-01")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(OBS, fh)
    old = time.time() - 30 * 3600                       # far past the disk TTL: a refetch is due
    os.utime(path, (old, old))
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)   # FRED down / 429
    dates, vals = fred.fetch_series("USREC")
    assert [d.isoformat() for d in dates] == ["2020-03-01", "2020-04-01", "2020-05-01"] and vals == [1.0, 1.0, 0.0]
    assert fred.fetch_series("NOCOPY") == ([], [])      # no copy on disk: still empty, never invented


def test_a_fresh_fetch_still_replaces_the_copy(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    path = fred._cache_path("USREC", "1976-01-01")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(OBS, fh)
    os.utime(path, (time.time() - 30 * 3600,) * 2)
    newer = {"observations": OBS["observations"] + [{"date": "2020-06-01", "value": "0"}]}
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: newer)
    dates, _ = fred.fetch_series("USREC")
    assert dates[-1].isoformat() == "2020-06-01"


def _full_bundle(recession):
    return {k: ([1], [1.0]) for k in fred._fred_plan()} | {"recession": recession}


def test_the_bundle_never_swaps_a_good_series_for_an_empty_one(monkeypatch):
    good = ([1, 2], [0.0, 1.0])
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": 0.0, "data": _full_bundle(good), "degraded": False})
    monkeypatch.setattr(fred, "_fetch_bundle_uncached", lambda start: _full_bundle(([], [])))
    b = fred.fetch_bundle()                             # expired: refetched, USREC failed this time
    assert b["recession"] == good and fred._bundle_cache["degraded"] is False


def test_a_degraded_bundle_retries_in_minutes_not_hours(monkeypatch):
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": 0.0, "data": None, "degraded": False})
    calls = []
    monkeypatch.setattr(fred, "_fetch_bundle_uncached", lambda start: calls.append(1) or _full_bundle(([], [])))
    fred.fetch_bundle()
    assert fred._bundle_cache["degraded"] is True and fred._bundle_fresh()
    fred._bundle_cache["ts"] = time.time() - fred._DEGRADED_TTL_SECONDS - 1
    assert not fred._bundle_fresh()
    fred.fetch_bundle()
    assert len(calls) == 2
    fred._bundle_cache.update(degraded=False, ts=time.time() - fred._DEGRADED_TTL_SECONDS - 1)
    assert fred._bundle_fresh()                         # a healthy bundle keeps its 6 h


def test_an_empty_model_fit_is_retried_in_minutes(monkeypatch):
    now = time.time()
    monkeypatch.setattr(rm, "_model_cache", dict(rm._model_cache, models={}, ts=now - rm._EMPTY_RETRY_SECONDS - 1))
    assert not rm._fit_fresh()
    rm._model_cache["ts"] = now - 60
    assert rm._fit_fresh()
    rm._model_cache.update(models={12: {"b0": 0}}, ts=now - 5 * 3600)
    assert rm._fit_fresh()                              # a real fit keeps its 6 h
    rm._model_cache["ts"] = now - rm._MODEL_TTL_SECONDS - 1
    assert not rm._fit_fresh()


def test_the_curve_says_when_its_probability_is_the_static_fallback(monkeypatch):
    from datetime import date, timedelta
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(400)]
    bundle = {"3mo": (days, [4.0] * 400), "10y": (days, [4.7] * 400), "recession": ([], [])}
    monkeypatch.setattr(rc, "fetch_bundle", lambda: bundle)
    monkeypatch.setattr("app.metrics.recession_model.cached_models_and_spread", lambda: ({}, 0.70))
    p = rc.canary(pair="3m10y")
    assert p["recession_probability_pct"] == 16.4 and p["recession_probability_basis"] == "static"
    assert p["recessions"] == []
    monkeypatch.setattr("app.metrics.recession_model.cached_models_and_spread",
                        lambda: ({12: {"b0": -0.5, "b1": -0.6, "cov": [[0.0, 0.0], [0.0, 0.0]]}}, 0.70))
    assert rc.canary(pair="3m10y")["recession_probability_basis"] == "fitted"
