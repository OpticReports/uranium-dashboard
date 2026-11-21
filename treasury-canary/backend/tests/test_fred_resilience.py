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

import pytest

from app.api import routes_composite as rc
from app.metrics import recession_model as rm
from app.sources import fred


@pytest.fixture(autouse=True)
def _closed_breaker(monkeypatch):
    monkeypatch.setattr(fred, "_breaker", {"fails": 0, "open_until": 0.0})
    monkeypatch.setattr(fred, "_failing", {})

OBS = {"observations": [{"date": "2020-03-01", "value": "1"}, {"date": "2020-04-01", "value": "1"},
                        {"date": "2020-05-01", "value": "0"}]}


def _key_and_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fred.settings, "fred_api_key", "test-key")
    monkeypatch.setattr(fred.settings, "cache_dir", str(tmp_path))


def test_a_failed_fetch_serves_the_last_good_copy(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
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


def test_a_running_process_never_masks_a_rejected_key_or_an_expired_copy(monkeypatch):
    """re-check S1: an in-memory keep-previous merge bypassed the key rule and the age cap. A process that
    already holds a good bundle must still let a series go empty (loudly STALE) when fetch_series says so."""
    good = ([1, 2], [0.0, 1.0])
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": 0.0, "data": _full_bundle(good), "degraded": False})
    monkeypatch.setattr(fred, "_fetch_bundle_uncached", lambda start: _full_bundle(([], [])))   # key rejected / >72 h
    b = fred.fetch_bundle()
    assert b["recession"] == ([], []) and fred._bundle_cache["degraded"] is True


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


def _monthly_bundle(with_usrec: bool = True, with_tp: bool = True) -> dict:
    """40 years of first-of-month data: the spread inverts in the 12 months before each recession."""
    from datetime import date
    days, spread, usrec, tp = [], [], [], []
    rec_starts = [1984, 1992, 2000, 2008, 2016]
    for y in range(1980, 2021):
        for m in range(1, 13):
            d = date(y, m, 1)
            in_rec = any(y == r and m <= 8 for r in rec_starts)
            before = any((y == r - 1 and m >= 8) or (y == r and m == 1) for r in rec_starts)
            days.append(d)
            spread.append(-0.6 if before else 1.8)
            usrec.append(1.0 if in_rec else 0.0)
            tp.append(0.4)
    b = {"3mo": (days, [2.0] * len(days)), "10y": (days, [2.0 + s for s in spread]),
         "recession": (days, usrec) if with_usrec else ([], []), "acm_tp10": (days, tp) if with_tp else ([], [])}
    return b


def _count_fits(monkeypatch, bundles):
    calls = []

    def fake_bundle():
        calls.append(1)
        return bundles[min(len(calls), len(bundles)) - 1]
    monkeypatch.setattr("app.sources.fred.fetch_bundle", fake_bundle)
    monkeypatch.setattr(rm, "_model_cache", {"ts": 0.0, "models": None, "spread": None,
                                             "adj_models": None, "adj_spread": None, "tp": None})
    return calls


def test_an_empty_fit_is_refit_within_minutes_through_the_real_entry_point(monkeypatch):
    """re-check M1: the gate drives cached_models_and_spread(), so restoring the old 6 h check fails it."""
    calls = _count_fits(monkeypatch, [_monthly_bundle(with_usrec=False), _monthly_bundle()])
    assert rm.cached_models_and_spread()[0] == {}                  # USREC missing: no model
    rm.cached_models_and_spread()
    assert len(calls) == 1                                          # inside the retry window: no refit herd
    rm._model_cache["ts"] -= rm._EMPTY_RETRY_SECONDS + 1
    models, _ = rm.cached_models_and_spread()
    assert len(calls) == 2 and 12 in models                         # retried, and the recovered data fit
    rm._model_cache["ts"] -= rm._EMPTY_RETRY_SECONDS + 1
    rm.cached_models_and_spread()
    assert len(calls) == 2                                          # a real fit keeps its 6 h


def test_an_empty_adjusted_fit_is_retried_too(monkeypatch):
    """re-check M4: the raw fit succeeds but the ACM term premium is missing, so the adjusted fit is empty."""
    calls = _count_fits(monkeypatch, [_monthly_bundle(with_tp=False), _monthly_bundle()])
    rm.cached_adjusted()
    assert rm._model_cache["models"] and rm._model_cache["adj_models"] == {}
    rm._model_cache["ts"] -= rm._EMPTY_RETRY_SECONDS + 1
    adj, _, _ = rm.cached_adjusted()
    assert len(calls) == 2 and 12 in adj


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


# ---------------------------------------------------------------------------- re-check S1 (2026-11-21)
def _old_copy(tmp_path, series="USREC", hours=30):
    path = fred._cache_path(series, "1976-01-01")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(OBS, fh)
    t = time.time() - hours * 3600
    os.utime(path, (t, t))
    return path


def test_a_rejected_key_is_never_masked_by_old_copies(monkeypatch, tmp_path):
    """re-check S1: with the key rejected, every FRED metric must go STALE as before, never look live."""
    _key_and_cache(monkeypatch, tmp_path)
    _old_copy(tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": "Bad Request. The value for variable api_key is not registered."})
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)
    monkeypatch.setattr(fred, "_stale_served", {})
    assert fred.fetch_series("USREC") == ([], []) and fred.fred_stale_series() == {}


def test_an_old_copy_is_capped_and_what_is_served_stale_is_listed(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred.settings, "fred_stale_max_age_hours", 168)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)
    _old_copy(tmp_path, hours=200)                                  # past the 7-day cap
    assert fred.fetch_series("USREC") == ([], [])
    _old_copy(tmp_path, hours=30)
    assert fred.fetch_series("USREC")[0] and fred.fred_stale_series() == {"USREC": 30.0}
    fresh = {"observations": OBS["observations"] + [{"date": "2020-06-01", "value": "0"}]}
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: fresh)
    fred.fetch_series("USREC")
    assert fred.fred_stale_series() == {}                           # cleared on the next good fetch


def test_an_empty_reply_never_overwrites_the_good_copy(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    path = _old_copy(tmp_path, hours=30)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: {"observations": []})
    assert len(fred.fetch_series("USREC")[0]) == 3
    assert len(json.load(open(path, encoding="utf-8"))["observations"]) == 3


def test_health_and_refresh_list_the_stale_served_series(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    now = time.time()
    monkeypatch.setattr(fred, "_stale_served", {"USREC": now - 30 * 3600})      # mtime of the copy served
    monkeypatch.setattr(fred, "_failing", {"USREC": now})
    body = TestClient(main.app).get("/health").json()
    assert body["fred_stale_series"] == {"USREC": 30.0} and "fred_key_error" in body


# ---------------------------------------------------------------------------- re-check A (2026-11-21)
class _Resp:
    def __init__(self, code, text="", payload=None):
        self.status_code, self.text, self._payload = code, text, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_a_real_api_key_rejection_sets_the_key_error_and_serves_nothing(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    _old_copy(tmp_path, hours=30)
    body = "Bad Request.  The value for variable api_key is not registered."
    monkeypatch.setattr(fred.httpx, "get", lambda *a, **k: _Resp(400, body))
    assert fred.fetch_series("USREC") == ([], []) and fred.fred_key_error() and fred.fred_stale_series() == {}


def test_the_stale_path_still_splices_the_frozen_ice_history(monkeypatch, tmp_path):
    """re-check M2 mutant: without the splice an outage would shrink HY/IG OAS to FRED's truncated window."""
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    sid = "BAMLH0A0HYM2"
    path = fred._cache_path(sid, "1976-01-01")
    recent = {"observations": [{"date": "2026-05-01", "value": "3.1"}, {"date": "2026-05-04", "value": "3.0"}]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(recent, fh)
    os.utime(path, (time.time() - 30 * 3600,) * 2)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)
    dates, _ = fred.fetch_series(sid)
    assert dates[0].year < 2026 and dates[-1].isoformat() == "2026-05-04"


def test_twenty_waiting_callers_cause_one_fetch_and_one_fit(monkeypatch):
    """re-check M7/M10 mutants: the double-checks inside both locks keep a refetch single-flight."""
    import threading
    fetches = []

    def slow_uncached(start):
        fetches.append(1)
        time.sleep(0.3)
        return _full_bundle(([1, 2], [0.0, 1.0]))
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": 0.0, "data": None, "degraded": False})
    monkeypatch.setattr(fred, "_fetch_bundle_uncached", slow_uncached)
    ts = [threading.Thread(target=fred.fetch_bundle) for _ in range(20)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert len(fetches) == 1
    fits = _count_fits(monkeypatch, [_monthly_bundle()])
    real_fit = rm._fit_all

    def slow_fit():
        time.sleep(0.2)
        real_fit()
    monkeypatch.setattr(rm, "_fit_all", slow_fit)
    ts = [threading.Thread(target=rm.cached_models_and_spread) for _ in range(20)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert len(fits) == 1 and 12 in rm._model_cache["models"]


def test_a_down_fred_fails_fast_after_a_few_failures(monkeypatch, tmp_path):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("connection refused")
    monkeypatch.setattr(fred.httpx, "get", boom)
    monkeypatch.setattr(fred.time, "sleep", lambda s: None)          # skip the backoff waits
    for _ in range(fred._BREAKER_FAILS):
        assert fred._get_with_backoff({"series_id": "X"}) is None
    n = len(calls)
    assert fred._get_with_backoff({"series_id": "Y"}) is None and len(calls) == n   # open: no network call
    fred._breaker["open_until"] = 0.0
    monkeypatch.setattr(fred.httpx, "get", lambda *a, **k: _Resp(200, payload={"observations": []}))
    assert fred._get_with_backoff({"series_id": "Z"}) == {"observations": []} and fred._breaker["fails"] == 0


def test_the_stale_list_is_keyed_by_start_and_cleared_when_the_copy_expires(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred.settings, "fred_stale_max_age_hours", 72)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)
    for start in ("1976-01-01", "1945-01-01"):
        path = fred._cache_path("USREC", start)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(OBS, fh)
        os.utime(path, (time.time() - 30 * 3600,) * 2)
        fred.fetch_series("USREC", start=start)
    assert fred.fred_stale_series() == {"USREC": 30.0, "USREC (from 1945-01-01)": 30.0}
    os.utime(fred._cache_path("USREC", "1976-01-01"), (time.time() - 80 * 3600,) * 2)   # past the cap
    assert fred.fetch_series("USREC") == ([], [])
    assert fred.fred_stale_series() == {"USREC (from 1945-01-01)": 30.0}                  # no stale age left behind
    monkeypatch.setattr(fred, "_key_error", {"msg": "api_key not registered"})
    fred.fetch_series("USREC", start="1945-01-01")
    assert fred.fred_stale_series() == {}


# ---------------------------------------------------------------------------- re-check A, round 3
def test_a_bundle_served_partly_stale_retries_in_minutes(monkeypatch):
    """a short blip opens the breaker and every remaining series is served stale: that must not stand 6 h."""
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": 0.0, "data": None, "degraded": False})

    def blip(start):
        fred._stale_served[fred._stale_tag("USREC", start)] = 7.5       # served from the copy this pass
        return _full_bundle(([1, 2], [0.0, 1.0]))                         # no holes
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred, "_fetch_bundle_uncached", blip)
    fred.fetch_bundle()
    assert fred._bundle_cache["degraded"] is True


def test_four_hundreds_never_open_the_breaker(monkeypatch):
    monkeypatch.setattr(fred.httpx, "get", lambda *a, **k: _Resp(400, "series does not exist"))
    for _ in range(fred._BREAKER_FAILS + 3):
        assert fred._get_with_backoff({"series_id": "NOPE"}) is None
    assert fred._breaker["open_until"] == 0.0 and fred._breaker["fails"] == 0


def test_the_copy_is_written_atomically(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    from app.sources import fred_csv
    writes = []
    monkeypatch.setattr(fred_csv, "_write_atomic", lambda path, data: writes.append(path))
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: OBS)
    fred.fetch_series("USREC", use_cache=False)
    assert writes == [fred._cache_path("USREC", "1976-01-01")]


def test_no_number_means_no_basis(monkeypatch):
    from datetime import date, timedelta
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(400)]
    monkeypatch.setattr(rc, "fetch_bundle", lambda: {"3mo": (days, [4.0] * 400), "10y": (days, [4.7] * 400),
                                                    "recession": ([], [])})
    monkeypatch.setattr("app.metrics.recession_model.cached_models_and_spread", lambda: ({}, None))
    p = rc.canary(pair="3m10y")
    assert p["recession_probability_pct"] is None and p["recession_probability_basis"] is None


# ---------------------------------------------------------------------------- re-check B, round 3
def test_a_failing_series_stays_visible_past_the_cap_or_with_no_copy(monkeypatch, tmp_path):
    """past the cap, or with no copy at all, a failing series is empty and not stale-served; /health must
    still list it, or the header's FRED dot reads green while the metrics read STALE."""
    from fastapi.testclient import TestClient

    from app import main
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred.settings, "fred_stale_max_age_hours", 72)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)
    _old_copy(tmp_path, hours=80)                                   # past the 72 h cap
    assert fred.fetch_series("USREC") == ([], []) and fred.fetch_series("NOCOPY") == ([], [])
    assert fred.fred_stale_series() == {} and set(fred.fred_failing_series()) == {"USREC", "NOCOPY"}
    fred._failing["USREC"] -= 2 * 3600                              # failed two hours ago...
    fred.fetch_series("USREC")                                      # ...and again now: the latest failure counts
    assert fred.fred_failing_series()["USREC"] == 0.0
    body = TestClient(main.app).get("/health").json()
    assert set(body["fred_failing_series"]) == {"USREC", "NOCOPY"}
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: OBS)
    fred.fetch_series("USREC")
    assert set(fred.fred_failing_series()) == {"NOCOPY"}            # cleared on the next good fetch


def test_the_refresh_job_reports_the_stale_and_failing_series(monkeypatch, tmp_path):
    """through the real run_refresh, offline (a name-in-source check passed on the import line alone)."""
    from datetime import date

    from app.jobs import refresh
    from app.metrics.base import Status
    from tests.test_flip_baseline import _m, _offline_refresh, _session_factory
    SL = _session_factory(tmp_path)
    _offline_refresh(monkeypatch, [_m("curve.x", 1.0, Status.GREEN, date(2026, 10, 23))])
    now = time.time()
    monkeypatch.setattr(fred, "_stale_served", {"USREC": now - 30 * 3600})
    monkeypatch.setattr(fred, "_failing", {"USREC": now - 3600, "NOCOPY": now - 2 * 3600})
    with SL() as s:
        out = refresh.run_refresh(s)
    assert out["fred_stale_series"] == {"USREC": 30.0}
    assert out["fred_failing_series"] == {"NOCOPY": 2.0, "USREC": 1.0}


# ---------------------------------------------------------------------------- re-check B, round 5
def _failing_fred(monkeypatch, tmp_path):
    _key_and_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fred, "_key_error", {"msg": None})
    monkeypatch.setattr(fred, "_stale_served", {})
    monkeypatch.setattr(fred.settings, "fred_stale_max_age_hours", 72)
    monkeypatch.setattr(fred, "_get_with_backoff", lambda params, tries=4: None)


def test_a_series_whose_caller_stopped_retrying_drops_off_after_six_hours(monkeypatch, tmp_path):
    """a caller (the labor board) failed once during a blip and never asked again. While a cache can
    still hold data built from that call it is listed, saying when it last failed; then it drops off."""
    _failing_fred(monkeypatch, tmp_path)
    _old_copy(tmp_path, hours=30)
    fred.fetch_series("USREC")                                      # served from the 30 h copy
    fred.fetch_series("NOCOPY")                                     # nothing to serve
    assert set(fred.fred_failing_series()) == {"USREC", "NOCOPY"} and set(fred.fred_stale_series()) == {"USREC"}
    for tag in fred._failing:
        fred._failing[tag] = time.time() - 5 * 3600                 # last failed 5 h ago, not retried
    assert fred.fred_failing_series() == {"NOCOPY": 5.0, "USREC": 5.0} and set(fred.fred_stale_series()) == {"USREC"}
    for tag in fred._failing:
        fred._failing[tag] = time.time() - 6 * 3600 - 60            # past the window
    assert fred.fred_failing_series() == {} and fred.fred_stale_series() == {}
    fred.fetch_series("NOCOPY")                                     # fails again
    assert fred.fred_failing_series() == {"NOCOPY": 0.0}


def test_the_failing_window_covers_the_cache_fed_by_direct_fetches():
    """/cycle builds from fetch_series directly and holds the board 6 h: a board built during a failure
    must stay under an amber dot that long. Caches built from the bundle take ttl_for_bundle_build."""
    from app.api import routes_cycle
    assert fred._FAILING_RECENT_SECONDS >= routes_cycle._TTL


def test_the_stale_copy_age_is_its_age_when_listed(monkeypatch, tmp_path):
    _failing_fred(monkeypatch, tmp_path)
    _old_copy(tmp_path, hours=30)
    fred.fetch_series("USREC")
    assert fred.fred_stale_series() == {"USREC": 30.0}
    later = time.time() + 2 * 3600
    fred._failing["USREC"] = later - 60                             # still failing, two hours on
    monkeypatch.setattr(fred.time, "time", lambda: later)
    assert fred.fred_stale_series() == {"USREC": 32.0}              # not the 30.0 frozen when served


def test_a_fresh_disk_hit_clears_both_lists(monkeypatch, tmp_path):
    """one series, two callers: one call failed (listed stale), the other wrote a fresh copy. The next
    reads hit that fresh copy; it must clear the lists, or the bundle stays degraded for the cache TTL."""
    _failing_fred(monkeypatch, tmp_path)
    _old_copy(tmp_path, hours=30)
    fred.fetch_series("USREC")
    assert "USREC" in fred._stale_served and "USREC" in fred._failing
    _old_copy(tmp_path, hours=0)                                    # the other caller's good fetch

    def no_network(params, tries=4):
        raise AssertionError("a fresh disk copy must not refetch")
    monkeypatch.setattr(fred, "_get_with_backoff", no_network)
    assert len(fred.fetch_series("USREC")[0]) == 3
    assert fred._stale_served == {} and fred._failing == {}


def test_the_breaker_closes_before_a_degraded_bundle_retries():
    """re-check A, round 4 NOTE: a blip-degraded bundle recovers on its 15 min retry only because the
    10 min breaker has closed by then; a longer window would serve that retry stale again, and the next."""
    assert fred._BREAKER_SECONDS < fred._DEGRADED_TTL_SECONDS


# ---------------------------------------------------------------------------- re-check B, round 6
# A stale copy passes every "is the input complete?" check, so a cache built from a degraded bundle
# kept that build for its full 6-12 h after FRED came back, under a green dot. Each now holds it only
# as long as the bundle holds the stale copies (15 min), and keeps its own TTL when the bundle is good.
def _bundle_now(monkeypatch, degraded):
    monkeypatch.setattr(fred, "_bundle_cache", {"ts": time.time(), "data": _full_bundle(([1], [0.0])),
                                                "degraded": degraded})


def _rebuilds_after_16_min(build, cache, counter):
    cache["ts"] = time.time() - fred._DEGRADED_TTL_SECONDS - 1
    n = len(counter)
    build()
    return len(counter) == n + 1


def test_a_recession_fit_on_a_degraded_bundle_refits_with_it(monkeypatch):
    fits = []
    monkeypatch.setattr(rm, "build_models", lambda *a, **k: fits.append(1) or {12: {"b0": -0.5, "b1": -0.6}})
    monkeypatch.setattr(rm, "_model_cache", dict(rm._model_cache, models=None, adj_models=None))
    for degraded, ttl in ((True, fred._DEGRADED_TTL_SECONDS), (False, rm._MODEL_TTL_SECONDS)):
        _bundle_now(monkeypatch, degraded)
        rm._fit_all()
        assert rm._model_cache["ttl"] == ttl
        rm._model_cache["ts"] = time.time() - fred._DEGRADED_TTL_SECONDS - 1
        assert rm._fit_fresh() is (not degraded)       # 16 min on: a fit on stale copies is due


def test_distress_built_on_a_degraded_bundle_rebuilds_with_it(monkeypatch):
    from app.api import routes_distress as rd
    builds = []
    monkeypatch.setattr(rd, "load_history", lambda: {"history_end": "2026Q2"})
    monkeypatch.setattr(rd, "qidx", lambda q: 8106)
    monkeypatch.setattr(rd, "new_quarters", lambda q: {})
    monkeypatch.setattr(rd, "bank_from_bundle", lambda bundle, hist: {})
    monkeypatch.setattr(rd, "build_distress", lambda hist, live, bank: builds.append(1) or {"n": len(builds)})
    monkeypatch.setattr(rd, "_cache", {"ts": 0.0, "data": None, "ttl": rd._TTL})
    for degraded, ttl in ((True, fred._DEGRADED_TTL_SECONDS), (False, rd._TTL)):
        _bundle_now(monkeypatch, degraded)
        rd.distress_payload(force=True)
        assert rd._cache["ttl"] == ttl
        assert _rebuilds_after_16_min(rd.distress_payload, rd._cache, builds) is degraded


def test_pins_history_built_on_a_degraded_bundle_rebuilds_with_it(monkeypatch):
    from app.api import routes_pins as rp
    builds = []
    monkeypatch.setattr(rp, "_assemble_bundle", lambda with_auctions=False: {})
    monkeypatch.setattr("app.sources.yahoo.fetch_spx_monthly", lambda: ([], []))
    monkeypatch.setattr(rp, "build_pin_history", lambda bundle: builds.append(1) or {"n": len(builds)})
    monkeypatch.setattr(rp, "_hist_complete", lambda data: True)
    monkeypatch.setattr(rp, "_hist_cache", {"ts": 0.0, "data": None, "ok": False, "ttl": rp._HIST_TTL_FAIL})
    for degraded, ttl in ((True, fred._DEGRADED_TTL_SECONDS), (False, rp._HIST_TTL_OK)):
        _bundle_now(monkeypatch, degraded)
        rp._hist_cache["data"] = None
        rp.pin_history()
        assert rp._hist_cache["ttl"] == ttl
        assert _rebuilds_after_16_min(rp.pin_history, rp._hist_cache, builds) is degraded


def test_severity_history_on_stale_copies_is_held_minutes_not_12_hours(monkeypatch):
    from app.api import routes_severity as rs
    builds = []
    monkeypatch.setattr("app.metrics.severity_history.history_payload",
                        lambda bundle, end: builds.append(1) or {"n": len(builds)})
    monkeypatch.setattr(rs, "_complete", lambda bundle: True)       # complete: the stale copies pass
    monkeypatch.setattr(rs, "_HIST", {"ts": 0.0, "data": None})
    for degraded, ttl in ((True, fred._DEGRADED_TTL_SECONDS), (False, rs._HIST_TTL)):
        _bundle_now(monkeypatch, degraded)
        rs.warm_history(force=True)
        assert rs._HIST["ttl"] == ttl
        assert _rebuilds_after_16_min(rs.warm_history, rs._HIST, builds) is degraded
