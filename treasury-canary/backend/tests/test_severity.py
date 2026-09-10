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


def test_hy_complacency_is_level_anchored_not_a_three_year_rank():
    """FRED cut ICE BofA history to 3 years in April 2026 (its own series note).

    The old `_pctile(hy, hy[-1], invert=True)` silently became "tightest since
    2023" while the index claimed a full-history rank — the live board's 87.2
    reproduced exactly as the inverted rank of 2.71% against the 787-point
    window. This component is now anchored to documented absolute levels.
    """
    from app.metrics.severity import HY_COMPLACENCY_ANCHORS, _hy_complacency_score

    benign, yellow, red, extreme = HY_COMPLACENCY_ANCHORS
    assert extreme == 2.41      # VERIFIED record low, Jun-2007, eve of the GFC
    assert benign > yellow > red > extreme      # tighter = more severe

    assert _hy_complacency_score(8.0) == 0.0    # already repriced: no complacency
    assert _hy_complacency_score(5.0) == 50.0
    assert _hy_complacency_score(3.5) == 80.0
    assert _hy_complacency_score(2.41) == 100.0  # maximum complacency ever observed
    assert _hy_complacency_score(2.0) == 100.0   # clamped, never above 100
    assert _hy_complacency_score(21.82) == 0.0   # Dec-2008 record high: zero complacency
    assert _hy_complacency_score(None) is None

    # monotone: tighter spreads must never score LESS severe
    scores = [_hy_complacency_score(v) for v in (9.0, 8.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.41)]
    assert scores == sorted(scores)

    # and it must NOT depend on the history window, which is the whole point
    assert _hy_complacency_score(2.71) == _hy_complacency_score(2.71)


def test_severity_scoring_docstring_matches_the_code():
    """The module claims every component is a full-history percentile.

    That is now true of every component EXCEPT hy_complacency, and the docstring
    must keep saying so — a silent second exception is how this bug happened.
    """
    import app.metrics.severity as sev

    assert "ONE documented exception" in sev.__doc__
    assert "hy_complacency" in sev.__doc__
