"""Severity index tests — scoring math, direction, composition, degradation."""
from datetime import date, timedelta

from app.metrics.severity import _pctile, _ratio_series, build_severity


def _q(n, start=(2000, 1)):
    y, m = start
    return [date(y + (m - 1 + 3 * i) // 12, (m - 1 + 3 * i) % 12 + 1, 1) for i in range(n)]


def test_pctile_orientation():
    hist = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _pctile(hist, 5.0) == 100.0
    assert _pctile(hist, 5.0, invert=True) == 0.0   # high value, inverted = benign
    assert _pctile(hist, None) is None
    assert _pctile([], 1.0) is None


def test_ratio_series_alignment():
    nd = _q(4)
    dd = _q(4)
    d, v = _ratio_series((nd, [10.0, 20.0, 30.0, 40.0]), (dd, [100.0] * 4))
    assert v == [0.1, 0.2, 0.3, 0.4]


def test_build_severity_empty_bundle_safe():
    out = build_severity({})
    assert out["severity_score"] is None
    assert out["severity_class"] is None
    assert len(out["blocks"]) == 6


def test_household_boom_reads_severe_and_matches_type():
    n = 40
    dates = _q(n)
    # household debt/GDP ramps hard in the last 3 years (2007-style)
    hh = [60.0] * (n - 12) + [60.0 + 1.5 * (i + 1) for i in range(12)]
    bundle = {
        "hh_debt_gdp": (dates, hh),
        "dsr": (dates, [11.0] * (n - 12) + [11.0 + 0.2 * (i + 1) for i in range(12)]),
        "saving_rate": (dates, [8.0] * (n - 12) + [8.0 - 0.4 * (i + 1) for i in range(12)]),
        "gdp": (dates, [15000.0] * n),
    }
    out = build_severity(bundle)
    a = next(b for b in out["blocks"] if b["id"] == "A")
    assert a["score"] is not None and a["score"] > 80          # boom = high severity
    assert out["composition"]["matched_type"] == "household_leverage"
    assert out["severity_score"] is not None


def test_dampeners_reduce_score():
    n = 40
    dates = _q(n)
    hh = [60.0] * (n - 12) + [60.0 + 1.5 * (i + 1) for i in range(12)]
    base_bundle = {"hh_debt_gdp": (dates, hh), "gdp": (dates, [15000.0] * n)}
    out_no_damp = build_severity(base_bundle)
    # add strongly dampening structure: record-low inventories/supply/vacancies
    damp = dict(base_bundle)
    damp["inv_sales"] = (dates, [1.6] * (n - 1) + [1.2])       # low = dampening
    damp["months_supply"] = (dates, [8.0] * (n - 1) + [4.0])
    damp["vac_rental"] = (dates, [9.0] * (n - 1) + [5.0])
    damp["vac_owner"] = (dates, [2.5] * (n - 1) + [0.9])
    out_damp = build_severity(damp)
    assert out_damp["severity_score"] < out_no_damp["severity_score"]


def test_thin_policy_space_raises_score():
    n = 40
    dates = _q(n)
    hh = [60.0] * (n - 12) + [60.0 + 1.0 * (i + 1) for i in range(12)]
    # flat saving rate dilutes block A below the 100 clamp so the D adjustment shows
    base_bundle = {"hh_debt_gdp": (dates, hh), "gdp": (dates, [15000.0] * n),
                   "saving_rate": (dates, [8.0] * n)}
    out_base = build_severity(base_bundle)
    worse = dict(base_bundle)
    worse["fed_debt_gdp"] = (dates, [60.0] * (n - 1) + [125.0])   # record debt
    worse["deficit_gdp"] = (dates, [-2.0] * (n - 1) + [-7.0])     # record deficit
    out_worse = build_severity(worse)
    assert out_worse["severity_score"] > out_base["severity_score"]


def test_hy_complacency_ranks_against_full_history_not_the_truncated_feed():
    """FRED cut ICE BofA history to 3 years in April 2026 (its own series note).

    Ranking the live feed silently became "tightest since 2023" while this
    module's contract promises a full-history rank: today's 2.71 scored 87.2
    instead of 96.1. Asserted through build_severity, NOT the helper -- an
    earlier version of this gate only probed the helper, so reverting the live
    wiring back to the truncated rank left the whole suite green.
    """
    import datetime

    from app.metrics.severity import (HY_OAS_REFERENCE_QUANTILES,
                                      _hy_complacency_score, build_severity)

    q = HY_OAS_REFERENCE_QUANTILES
    assert len(q) == 101 and q[0] == 2.41 and q[-1] == 21.82   # verified extremes
    assert q[50] == 4.50                                        # verified median

    days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(800)]
    # a live window whose OWN minimum is 2.59 -- the truncated feed's floor. If the
    # score is computed against this window rather than the reference, today's 2.71
    # reads ~87; against full history it must read ~96.
    hy = [2.59 + (i % 200) / 100.0 for i in range(799)] + [2.71]
    out = build_severity({"hy_oas": (days, hy)})
    comp = next(c for b in out["blocks"] for c in b["components"]
                if c["id"] == "hy_complacency")
    assert comp["score"] == _hy_complacency_score(2.71)
    assert comp["score"] > 94.0, (
        f"score {comp['score']} looks like a rank against the truncated window, "
        "not the full-history reference")
    assert comp["value"] == 271.0          # displayed in bps, scored in percent

    # monotone: tighter spreads are never scored LESS severe
    scores = [_hy_complacency_score(v) for v in (9.0, 8.0, 6.0, 4.5, 3.3, 2.71, 2.41)]
    assert scores == sorted(scores)

    # the unit contract is guarded: bps passed where percent is expected must not
    # silently read as maximally benign
    assert _hy_complacency_score(271.0) is None
    assert _hy_complacency_score(None) is None


def test_severity_has_no_scoring_exceptions():
    """The module's contract is that EVERY component is a full-history percentile.

    A silent divergence between that sentence and the code is how the 3-year-rank
    bug survived; the previous version of this gate only checked that the
    docstring mentioned an exception, which is not a property of the code.
    """
    import inspect

    import app.metrics.severity as sev

    assert "NO exceptions" in sev.__doc__
    assert not hasattr(sev, "HY_COMPLACENCY_ANCHORS"), \
        "the anchored exception should be gone, replaced by a reference rank"
    # the live wiring must go through the reference-ranked scorer
    src = inspect.getsource(sev.build_severity)
    assert "_hy_complacency_score(" in src
    assert "_pctile(hy," not in src, "hy_complacency must not rank the truncated feed"
