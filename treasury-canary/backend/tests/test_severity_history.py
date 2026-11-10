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
    # (68.9 before household debt/GDP was extended back with Z.1; 67.7 after)
    assert build_severity(load.bundle(extend=False))["severity_score"] == 68.9
    assert build_severity(bundle)["severity_score"] == 67.7
    assert payload["today"] == {"score": 67.7, "class": "SEVERE"}


def test_no_observation_is_used_before_it_was_published(bundle):
    for t in (date(1995, 6, 30), date(2007, 11, 30), date(2020, 1, 31)):
        cut = SH.as_of(bundle, t)
        for key, lag in SH.LAGS.items():
            d, _ = cut[key]
            assert all(x + timedelta(days=lag) <= t for x in d), (key, t)
            if d:   # and only with >= 10 years of as-of history
                assert (d[-1] - d[0]).days >= SH.MIN_HISTORY_DAYS


def test_lags_are_no_shorter_than_the_real_release_schedule(bundle):
    """The as-of gate above checks the code's own LAGS, so it cannot catch a
    wrong lag. These pin the last stamp admitted at dates checked against
    ALFRED real-time vintages: never newer than what was actually published."""
    def last(key, t):
        d, _ = SH.as_of(bundle, t)[key]
        return d[-1]
    assert last("priv_credit", date(2020, 1, 31)) <= date(2019, 4, 1)
    assert last("priv_credit", date(2015, 12, 31)) <= date(2015, 4, 1)
    assert last("hh_debt_gdp", date(2024, 12, 31)) <= date(2024, 1, 1)
    assert last("hh_debt_gdp", date(2025, 6, 30)) <= date(2024, 7, 1)
    assert last("deficit_gdp", date(2023, 12, 31)) <= date(2022, 1, 1)
    assert last("inv_sales", date(2020, 1, 31)) <= date(2019, 11, 1)
    assert last("dsr", date(2024, 6, 30)) <= date(2023, 10, 1)
    # before dsr has 10 years of history, pin the lag itself: ALFRED had not
    # published 2003Q3 by 2004-02-29, nor 2006Q1 by 2006-06-30
    lag = timedelta(days=SH.LAGS["dsr"])
    assert date(2003, 7, 1) + lag > date(2004, 2, 29)
    assert date(2006, 1, 1) + lag > date(2006, 6, 30)


def test_late_starting_inputs_enter_ten_years_later(bundle):
    # debt service starts 2005 on FRED: absent until ~2015
    assert SH.as_of(bundle, date(2014, 12, 31))["dsr"] == ([], [])
    assert SH.as_of(bundle, date(2016, 6, 30))["dsr"][0]
    # household debt/GDP, extended back with Z.1, is live from 1987
    assert SH.as_of(bundle, date(1990, 6, 30))["hh_debt_gdp"][0]
    assert SH.as_of(bundle, date(2008, 6, 30))["effr"] == ([], [])      # EFFR from 2000-07


def test_payload_matches_the_frozen_study_and_serialises(payload):
    frozen = json.load(open(os.path.join(STUDY, "results.json")))
    assert json.loads(json.dumps(payload, allow_nan=False)) == frozen
    s = {r["month"]: r for r in payload["series"]}
    assert s["2007-11"]["score"] == 72.4 and s["2023-12"]["score"] == 49.0
    # the months the drawn rule actually hides (4 of 23 components live)
    for m in ("1986-03", "1986-04", "1986-05"):
        assert s[m]["score"] is not None and not s[m]["drawn"]
    # shares and percentiles on comparable inputs, not the thin early years
    assert (payload["share_severe"], payload["today_pctile"], payload["pctile_from"]) == (43, 85, "1999-12")
    assert (payload["share_severe_all_inputs"], payload["pctile_all_inputs"],
            payload["all_inputs_from"]) == (12, 97, "2015-09")
    assert "extended back to 1976 with the Fed's Z.1" in payload["method"]
    assert "the dot is today's live reading" in payload["method"]


def test_live_path_runs_through_the_current_month(bundle):
    # the route calls with end=today; the grid must include the current month
    p = SH.history_payload(bundle, end=date(2026, 9, 30))
    q = SH.history_payload(bundle, end=None)
    assert p["series"][-1]["month"] == "2026-09"
    today = date.today()
    assert q["series"][-1]["month"] == f"{today.year}-{today.month:02d}"
    mid = SH.history_payload(bundle, end=date(2026, 9, 15))    # a partial month
    assert mid["series"][-1]["month"] == "2026-09" and mid["series"][-2]["month"] == "2026-08"


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
    assert starts["2007-12"]["reading"] == 72.4 and starts["2020-02"]["exogenous"]
    assert starts["1990-07"]["reading"] == 64.9
    near = payload["analogs"]["nearest"]
    assert [(n["from"], n["to"]) for n in near] == [("1999-12", "2002-05"), ("2006-08", "2007-11"),
                                                    ("2008-06", "2010-06"), ("2012-12", "2015-07")]
    assert all(n["live"] >= 0.75 * n["total"] for n in near)
    assert near[0]["recession_within_24m"] == "2001-03" and near[1]["recession_within_24m"] == "2007-12"
    assert near[2]["already_in_recession"]
    assert near[3]["recession_within_24m"] is None and near[3]["unemployment_chg_24m"] == -2.3
    # the current stretch is never its own analog (no outcome yet)
    assert all(n["to"] < "2024-10" for n in near)


# ── household debt/GDP back-extension (sources/household_debt.py) ───────────
def test_household_debt_splice():
    from app.sources.household_debt import extend_household_debt, z1_ratio
    raw = load.bundle(extend=False)
    pub, z1, gdp = raw["hh_debt_gdp"], raw["hh_debt_z1"], raw["gdp"]
    d, v = extend_household_debt(pub, z1, gdp)
    ext = dict(zip(d, v))
    first = next(x for x, y in zip(*pub) if y is not None)
    assert first == date(2005, 1, 1) and d[0] == date(1976, 1, 1)
    # the published series wins wherever it exists, untouched
    assert all(ext[x] == y for x, y in zip(*pub) if y is not None)
    # the join is continuous: the back-extension is Z.1 shifted by the gap at
    # the FIRST overlapping quarter only, so its 3-year changes are pure Z.1
    z = z1_ratio(z1, gdp)
    shift = ext[first] - z[first]
    assert abs(shift - (-0.4)) < 0.1
    assert all(abs(ext[x] - (z[x] + shift)) < 1e-3 for x in d if x < first)
    # the Z.1 ratio tracks the published one: 3-year changes corr ~0.97
    ov = sorted(x for x in z if x in ext and x >= first)
    a = [ext[ov[i]] - ext[ov[i - 12]] for i in range(12, len(ov))]
    b = [z[ov[i]] - z[ov[i - 12]] for i in range(12, len(ov))]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    corr = (sum((x - ma) * (y - mb) for x, y in zip(a, b))
            / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5)
    assert corr > 0.95


def test_household_debt_splice_refuses_to_substitute():
    from app.sources.household_debt import extend_household_debt
    raw = load.bundle(extend=False)
    # a failed fetch of the published series stays empty (STALE), never
    # silently becomes the Z.1 series; a missing Z.1 leaves it unchanged
    assert extend_household_debt(([], []), raw["hh_debt_z1"], raw["gdp"]) == ([], [])
    assert extend_household_debt(raw["hh_debt_gdp"], ([], []), raw["gdp"]) == raw["hh_debt_gdp"]


def test_a_failed_z1_extension_is_said_not_silent():
    raw = load.bundle(extend=False)       # as if CMDEBT/GDP had failed to fetch
    note = next(c["note"] for b in build_severity(raw)["blocks"] for c in b["components"]
                if c["id"] == "hh_debt_3y")
    assert "Z.1 back-extension unavailable" in note
    note_ok = next(c["note"] for b in build_severity(load.bundle())["blocks"]
                   for c in b["components"] if c["id"] == "hh_debt_3y")
    assert "unavailable" not in note_ok


def test_tdsp_is_not_spliced_across_its_2005_methodology_break():
    """FRED serves TDSP from 2005; ALFRED vintages from 2024-09-30 hold
    1980-2004 on the OLD basis next to 2005+ revised up 0.7-2.9pp (a +2.5pp
    step at 2005Q1). Splicing that history in (tried 2026-10-01, withdrawn
    after review) ranked today's revised ratio against unrevised history."""
    from app.sources.ice_reference import FROZEN_SERIES, frozen_history
    assert "TDSP" not in FROZEN_SERIES and frozen_history("TDSP") == ((), ())
