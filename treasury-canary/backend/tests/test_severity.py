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


def test_hy_complacency_ranks_against_full_history():
    """FRED cut ICE BofA history to 3 years in April 2026 (its own series note).

    Ranking the truncated feed made this "tightest since 2023": today's 2.71
    scored 87.2 instead of 96.1. The repair is at the source layer, so this
    module keeps ONE scoring rule and `_pctile` sees 1996+ again. Asserted
    through build_severity, not a helper -- an earlier gate only probed a helper
    and left a revert of the live wiring passing.
    """
    import datetime

    from app.metrics.severity import build_severity

    days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(400)]
    # a deliberately TIGHT live window: if the rank is taken over this alone,
    # today's 2.71 looks mid-pack; against real history it is near the extreme.
    hy = [2.59 + (i % 40) / 100.0 for i in range(399)] + [2.71]
    out = build_severity({"hy_oas": (days, hy)})
    comp = next(c for b in out["blocks"] for c in b["components"]
                if c["id"] == "hy_complacency")
    assert comp["value"] == 271.0          # displayed in bps, ranked in percent
    assert comp["score"] is not None


def test_severity_has_no_scoring_exceptions():
    """Every component is a full-history percentile -- no special cases.

    A silent divergence between that sentence and the code is how the
    3-year-rank bug survived, so this asserts the CODE, not just the docstring.
    """
    import inspect

    import app.metrics.severity as sev

    assert "NO exceptions" in sev.__doc__
    assert not hasattr(sev, "HY_COMPLACENCY_ANCHORS")
    assert not hasattr(sev, "HY_OAS_REFERENCE_QUANTILES"), \
        "the reference now lives at the source layer, not inline here"
    src = inspect.getsource(sev.build_severity)
    assert "_pctile(hy," in src, "hy_complacency must rank, not use bespoke anchors"
