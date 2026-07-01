"""Hard tests for the inversion / re-steepening state machine (the core signal)."""
from datetime import date, timedelta

from app.metrics.curve import (
    CurveState, analyze_spread, build_spread, lag_months_to_recession,
)


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _series(*runs: tuple[float, int]) -> list[float]:
    """Concatenate (value, count) runs into a flat list."""
    out: list[float] = []
    for val, cnt in runs:
        out.extend([val] * cnt)
    return out


def test_normal_inverted_sustained_resteepening():
    # 10d positive -> 15d inverted (sustained) -> 5d positive (recent dis-inversion)
    vals = _series((0.5, 10), (-0.3, 15), (0.4, 5))
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5, steepen_persist_days=10)

    assert a.state is CurveState.RE_STEEPENING
    assert a.dis_inversion_date == date(2020, 1, 1) + timedelta(days=25)
    assert len(a.episodes) == 1
    ep = a.episodes[0]
    assert ep.sustained is True
    assert ep.days_inverted == 15
    assert ep.max_depth_bps == -30.0
    assert ep.dis_inversion == date(2020, 1, 1) + timedelta(days=25)


def test_currently_inverted():
    vals = _series((0.5, 10), (-0.3, 15))  # ends inverted
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5)
    assert a.state is CurveState.INVERTED
    assert a.days_inverted == 15
    assert a.episodes[-1].dis_inversion is None
    assert a.episodes[-1].sustained is True
    assert a.current_depth_bps == -30.0


def test_brief_dip_is_noise_not_resteepening():
    # 3-day dip < min_inversion_days=5 -> not sustained -> stays NORMAL after recovery
    vals = _series((0.5, 10), (-0.2, 3), (0.4, 10))
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5, steepen_persist_days=10)
    assert a.state is CurveState.NORMAL
    assert a.episodes[0].sustained is False
    assert a.dis_inversion_date is None


def test_old_resteepening_reverts_to_normal():
    # dis-inversion far in the past (beyond steepen_persist_days) -> NORMAL now
    vals = _series((0.5, 5), (-0.3, 10), (0.4, 40))
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5, steepen_persist_days=10)
    assert a.state is CurveState.NORMAL
    assert a.episodes[0].sustained is True
    assert a.episodes[0].dis_inversion is not None


def test_none_values_are_skipped():
    vals = [0.5, None, 0.4, None, -0.3, -0.3, -0.3, -0.3, -0.3, 0.2]
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=3, steepen_persist_days=10)
    # 5 inverted obs (sustained >=3) then a positive -> re-steepening
    assert a.state is CurveState.RE_STEEPENING
    assert a.episodes[0].days_inverted == 5


def test_multiple_episodes():
    vals = _series((0.5, 5), (-0.2, 6), (0.5, 20), (-0.3, 8), (0.4, 3))
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5, steepen_persist_days=10)
    assert len(a.episodes) == 2
    assert all(e.sustained for e in a.episodes)
    assert a.state is CurveState.RE_STEEPENING  # most recent dis-inversion is recent


def test_build_spread_alignment():
    da = _dates(3)
    db = _dates(3)
    d, s = build_spread(da, [1.0, 2.0, None], db, [3.0, 3.0, 3.0])
    assert s == [2.0, 1.0, None]  # long(3) - short(1/2/None)


def test_lag_months_to_recession():
    vals = _series((0.5, 5), (-0.3, 10), (0.4, 5))
    a = analyze_spread(_dates(len(vals)), vals, min_inversion_days=5, steepen_persist_days=30)
    ep = a.episodes[0]
    onset = ep.dis_inversion.replace(year=ep.dis_inversion.year + 1)  # +12 months
    assert lag_months_to_recession(ep, [onset]) == 12
    assert lag_months_to_recession(ep, []) is None
