"""Merge-blocking gates for the severity history (studies/severity-history.md)."""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, timedelta

import pytest

from app.metrics import severity_history as SH
from app.metrics.severity import build_severity

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
STUDY = os.path.join(ROOT, "studies", "severity_history")
sys.path.insert(0, STUDY)
import load  # noqa: E402


@pytest.fixture(scope="module")
def bundle():
    b = load.bundle()
    b["unrate"] = load.fred("UNRATE")
    return b


@pytest.fixture(scope="module")
def payload(bundle):
    return SH.history_payload(bundle, end=date(2026, 9, 30))


def test_today_is_the_live_index(bundle, payload):
    # the frozen bundle reproduces the live /severity of 2026-09-30 exactly
    assert build_severity(bundle)["severity_score"] == 68.9
    assert payload["today"] == {"score": 68.9, "class": "SEVERE"}


def test_no_observation_is_used_before_it_was_published(bundle):
    for t in (date(1995, 6, 30), date(2007, 11, 30), date(2020, 1, 31)):
        cut = SH.as_of(bundle, t)
        for key, lag in SH.LAGS.items():
            d, _ = cut[key]
            assert all(x + timedelta(days=lag) <= t for x in d), (key, t)
            if d:   # and only with >= 10 years of as-of history
                assert (d[-1] - d[0]).days >= SH.MIN_HISTORY_DAYS


def test_late_starting_inputs_enter_ten_years_later(bundle):
    # household debt/GDP and debt service start 2005 on FRED: absent until 2015
    assert SH.as_of(bundle, date(2014, 12, 31))["hh_debt_gdp"] == ([], [])
    assert SH.as_of(bundle, date(2016, 6, 30))["hh_debt_gdp"][0]
    assert SH.as_of(bundle, date(2008, 6, 30))["effr"] == ([], [])      # EFFR from 2000-07


def test_payload_matches_the_frozen_study_and_serialises(payload):
    frozen = json.load(open(os.path.join(STUDY, "results.json")))
    assert json.loads(json.dumps(payload, allow_nan=False)) == frozen
    s = {r["month"]: r for r in payload["series"]}
    assert s["2007-11"]["score"] == 70.7 and s["2023-12"]["score"] == 49.6
    assert not s["1986-01"]["drawn"] or s["1986-01"]["live"] >= 0.5 * s["1986-01"]["total"]


def _fred(sid):
    out = {}
    for r in list(csv.reader(open(os.path.join(STUDY, "data", f"{sid}.csv"))))[1:]:
        if r[1] not in (".", ""):
            out[date.fromisoformat(r[0])] = float(r[1])
    return out


def test_recession_outcomes_are_the_data():
    un, gdp = _fred("UNRATE"), _fred("GDPC1")
    for key, want in SH.RECESSION_OUTCOMES.items():
        y, m = map(int, key.split("-"))
        p = date(y, m, 1)
        u0 = un[p]
        months = [date(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1, 1) for i in range(31)]
        assert round(max(un[x] for x in months if x in un) - u0, 1) == want["unemployment_rise_pp"]
        q = {d: v for d, v in gdp.items() if date(y - 1, 1, 1) <= d <= date(y + 3, 12, 31)}
        pk = max((d for d in q if d <= p + timedelta(days=91)), key=lambda d: q[d])
        tr = min((d for d in q if d >= pk), key=lambda d: q[d])
        assert round(100 * (q[tr] / q[pk] - 1), 1) == want["real_gdp_pct"]


def test_analogs(payload):
    starts = {s["peak"]: s for s in payload["analogs"]["recession_starts"]}
    assert starts["2007-12"]["reading"] == 70.7 and starts["2020-02"]["exogenous"]
    near = payload["analogs"]["nearest"]
    assert [(n["from"], n["to"]) for n in near] == [("2001-06", "2002-02"), ("2007-03", "2010-02"),
                                                    ("2012-09", "2015-06")]
    assert near[0]["already_in_recession"] and near[1]["recession_within_24m"] == "2007-12"
    assert near[2]["recession_within_24m"] is None and near[2]["unemployment_chg_24m"] == -1.9
    # the current stretch is never its own analog (no outcome yet)
    assert all(n["to"] < "2024-10" for n in near)
