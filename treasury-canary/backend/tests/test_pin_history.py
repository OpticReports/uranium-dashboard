"""Pin history hindcast: episodes, lag windows, no-lookahead percentiles,
monthly-max sampling, and damage-window overlap in the collective series."""
from datetime import date, timedelta

import pytest

from app.metrics.pin_history import (
    LAG_WINDOWS,
    _add_months,
    _expanding_percentile,
    _episodes,
    _monthly_max,
    build_pin_history,
)
from app.metrics.pins import ANCHORS


def _daily(start: date, vals: list[float]) -> tuple[list[date], list[float | None]]:
    return [start + timedelta(days=i) for i in range(len(vals))], list(vals)


def test_add_months_wraps_year():
    assert _add_months("2026-04", 12) == "2027-04"
    assert _add_months("2026-11", 3) == "2027-02"
    assert _add_months("2026-01", 0) == "2026-01"


def test_expanding_percentile_has_no_lookahead():
    dts = [date(2020, 1, 1) + timedelta(days=i) for i in range(5)]
    # 5 rising values: each is the max of history-so-far, so each must sit at the
    # HIGHEST ATTAINABLE percentile for its sample size. Under the Hazen plotting
    # position that ceiling is (n - 0.5)/n, never exactly 100 -- see rank_pct.
    _, pv = _expanding_percentile(dts, [1, 2, 3, 4, 5], min_obs=1)
    assert pv == [50.0, 75.0, pytest.approx(83.333, abs=1e-3), 87.5, 90.0]
    assert all(p < 100.0 for p in pv)
    # a mid-history spike ranks against PAST data only, not the later maximum
    _, pv = _expanding_percentile(dts, [1, 2, 10, 3, 50], min_obs=1)
    assert pv[2] == pytest.approx(100.0 * 2.5 / 3)  # max attainable at n=3
    assert pv[2] > pv[3]                            # later 50 cannot demote it


def test_percentile_never_returns_exactly_100():
    """The ceiling artifact this estimator exists to remove.

    rank/n hits exactly 100.0 on every running max, so a percentile leg anchored
    (50, 85, 95, 100) scored the EXTREME by construction on any new high.
    """
    from app.metrics.pins import _percentile, rank_pct

    for n in (2, 10, 100, 1000, 10_000):
        # an untied all-time high: below = n-1, equal = 1
        assert rank_pct(n - 1, 1, n) == pytest.approx(100.0 - 50.0 / n)
        assert rank_pct(n - 1, 1, n) < 100.0
        assert rank_pct(0, 1, n) > 0.0                      # an all-time low
    # approaches 100 asymptotically, reaches it never
    assert rank_pct(9_999, 1, 10_000) > rank_pct(99, 1, 100)
    # the not-in-sample path (a rolling mean above every raw print) is clamped
    assert rank_pct(500, 0, 500) < 100.0
    assert rank_pct(0, 0, 500) > 0.0

    rising = list(range(1, 1201))   # past n=1000, where the rounding bug appeared
    assert _percentile(rising, rising[-1]) < 100.0      # an all-time high
    assert _percentile(rising, rising[0]) > 0.0         # an all-time low
    dts = [date(2020, 1, 1) + timedelta(days=i) for i in range(1200)]
    _, pv = _expanding_percentile(dts, [float(x) for x in rising], min_obs=1)
    assert max(pv) < 100.0 and min(pv) > 0.0


def test_monthly_max_keeps_intra_month_spike():
    dts, vals = _daily(date(2020, 3, 1), [10.0] * 15 + [95.0] + [12.0] * 10)
    assert _monthly_max(dts, vals)["2020-03"] == 95.0


def test_episode_detection_and_lag_window():
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    scores = [10.0, 70.0, 85.0, 92.0, 60.0, 10.0]
    eps = _episodes(months, scores, "oil_shock")
    assert len(eps) == 1
    e = eps[0]
    assert (e["start"], e["end"]) == ("2026-03", "2026-04")
    assert e["peak_date"] == "2026-04" and e["peak_score"] == 92.0
    lo, hi, _ = LAG_WINDOWS["oil_shock"]
    assert e["window_start"] == _add_months("2026-04", lo)      # from the peak
    assert e["window_end"] == _add_months("2026-04", hi)        # last red month


def test_ongoing_episode_window_stays_open():
    # a run still red at the latest month: window end anchors to the LAST red
    # month, so a channel red today never shows an already-expired window
    months = [f"2026-{m:02d}" for m in range(1, 7)]
    scores = [85.0, 90.0, 85.0, 85.0, 85.0, 85.0]  # peak in month 2, still red
    eps = _episodes(months, scores, "basis_trade")
    assert len(eps) == 1
    lo, hi, _ = LAG_WINDOWS["basis_trade"]
    assert eps[0]["peak_date"] == "2026-02"
    assert eps[0]["window_start"] == _add_months("2026-02", lo)
    assert eps[0]["window_end"] == _add_months("2026-06", hi)


def test_separate_red_runs_are_separate_episodes():
    months = [f"2025-{m:02d}" for m in range(1, 7)]
    scores = [85.0, 40.0, 85.0, 90.0, 40.0, 85.0]
    assert len(_episodes(months, scores, "credit_event")) == 3


def test_build_history_oil_red_projects_window():
    # 2 years of flat oil, then a +100% jump held for ~3 months -> RED episode
    flat = [50.0] * 504
    spike = [100.0] * 63
    bundle = {"oil": _daily(date(2024, 1, 1), flat + spike)}
    hist = build_pin_history(bundle)
    oil = next(c for c in hist["channels"] if c["channel_id"] == "oil_shock")
    assert oil["series"], "oil hindcast series should be non-empty"
    assert oil["episodes"], "a +100% yoy jump must register as a red episode"
    e = oil["episodes"][0]
    assert e["peak_score"] >= 80.0

    coll = hist["collective"]["series"]
    last_data = hist["collective"]["last_data_month"]
    # the collective series must extend past the data to cover the lag window
    assert coll[-1]["date"] == e["window_end"] and coll[-1]["date"] > last_data
    proj = [r for r in coll if r["projected"]]
    assert proj and all(r["n_red"] is None for r in proj)
    inside = [r for r in coll if e["window_start"] <= r["date"] <= e["window_end"]]
    assert inside and all(r["windows_open"] >= 1 for r in inside)
    assert all("oil_shock" in r["window_channels"] for r in inside)


def test_latest_hindcast_point_matches_live_formula():
    # last expanding-percentile point == full-window percentile == live board
    vals = [3.0, 4.0, 2.0, 5.0, 4.5, 6.0]
    dts = [date(2025, 1, 1) + timedelta(days=7 * i) for i in range(len(vals))]
    _, pv = _expanding_percentile(dts, vals, min_obs=1)
    from app.metrics.pins import _percentile
    # _percentile rounds to 1dp, so parity is asserted to that precision. The old
    # 1e-9 tolerance only passed because rank/n returned exactly 100.0 here --
    # it would not have caught a genuine live-vs-hindcast estimator drift.
    assert pv[-1] == pytest.approx(_percentile(vals, vals[-1]), abs=0.05)
    assert pv[-1] < 100.0


def test_every_lag_channel_has_anchor_backed_parts():
    # each channel in LAG_WINDOWS must hindcast through known anchors only
    from app.metrics.pin_history import _parts_for_channel
    bundle: dict = {}
    for cid in LAG_WINDOWS:
        for label, _series_ in _parts_for_channel(cid, bundle):
            assert label in ANCHORS, f"{cid} part {label!r} missing from ANCHORS"


def test_empty_bundle_degrades_gracefully():
    hist = build_pin_history({})
    assert len(hist["channels"]) == len(LAG_WINDOWS)
    assert hist["collective"]["series"] == []
    assert hist["confluence"] is None
    assert hist["recessions"] == []


def test_drawdown_spans_peak_to_trough():
    from app.metrics.pin_history import _drawdown_spans
    dates = [date(2020, m, 1) for m in range(1, 13)]
    closes = [100, 105, 80, 70, 75, 90, 106, 108, 100, 99, 107, 110]
    lows = [98, 100, 75, 62, 70, 85, 100, 102, 95, 93, 100, 105]
    spans = _drawdown_spans(dates, closes, lows)
    # peak Feb (105) -> trough Apr (low 62, -41%), recovered Jul (close 106);
    # the Aug->Oct decline is only -13.9% so it must NOT register
    assert len(spans) == 1
    assert spans[0]["start"] == "2020-02" and spans[0]["trough"] == "2020-04"
    assert spans[0]["depth_pct"] == round((105 - 62) / 105 * 100, 1)


def test_no_credit_for_reverse_causality():
    # a red firing MID-collapse (window overlaps the decline span but the
    # drawdown STARTED before the window opened) must be a miss, not a hit
    from app.metrics.pin_history import _annotate_outcomes
    channels = [{"channel_id": "x", "episodes": [
        {"window_start": "2002-08", "window_end": "2002-11"},
    ]}]
    drawdowns = [{"start": "2000-03", "trough": "2002-10", "depth_pct": 49.4}]
    _annotate_outcomes(channels, [], drawdowns, last_data="2026-07")
    assert channels[0]["episodes"][0]["outcome"] == "miss"


def test_unjudged_when_no_ground_truth():
    from app.metrics.pin_history import _annotate_outcomes
    channels = [{"channel_id": "x", "episodes": [
        {"window_start": "2014-01", "window_end": "2014-06"},
    ]}]
    _annotate_outcomes(channels, [], [], last_data="2026-07")
    assert channels[0]["outcomes"] is None
    assert "outcome" not in channels[0]["episodes"][0]


def test_drawdown_crash_and_recover_month_still_registers():
    # low dips -20% intra-month but the close prints a NEW HIGH: the low is
    # evaluated against the prior peak before the close resets it
    from app.metrics.pin_history import _drawdown_spans
    dates = [date(2020, m, 1) for m in range(1, 5)]
    closes = [100.0, 101.0, 103.0, 104.0]
    lows = [99.0, 100.0, 80.0, 103.0]  # March: -20.8% vs Feb close, then recovered
    spans = _drawdown_spans(dates, closes, lows)
    assert len(spans) == 1
    assert spans[0]["start"] == "2020-02" and spans[0]["trough"] == "2020-03"


def test_episode_outcomes_hit_miss_open():
    from app.metrics.pin_history import _annotate_outcomes
    channels = [{
        "channel_id": "x",
        "episodes": [
            {"window_start": "2007-11", "window_end": "2008-06"},  # recession onset inside
            {"window_start": "2018-01", "window_end": "2018-12"},  # drawdown overlap
            {"window_start": "2014-01", "window_end": "2014-06"},  # nothing -> miss
            {"window_start": "2026-06", "window_end": "2026-12"},  # still running -> open
        ],
    }]
    recessions = [{"start": "2008-01", "end": "2009-06"}]
    drawdowns = [{"start": "2018-09", "trough": "2018-12", "depth_pct": 19.8}]
    _annotate_outcomes(channels, recessions, drawdowns, last_data="2026-07")
    eps = channels[0]["episodes"]
    assert eps[0]["outcome"] == "hit_recession"
    assert eps[1]["outcome"] == "hit_drawdown"
    assert eps[2]["outcome"] == "miss"
    assert eps[3]["outcome"] == "open"
    assert channels[0]["outcomes"] == {"hit": 2, "miss": 1, "open": 1}


def test_measured_roles_note_present():
    flat = [50.0] * 504
    hist = build_pin_history({"oil": _daily(date(2024, 1, 1), flat)})
    assert "accident radar" in hist["measured_roles"]


def test_recession_spans_extracted():
    from app.metrics.pin_history import _recession_spans
    dates, vals = [], []
    d = date(2007, 1, 1)
    while d <= date(2010, 12, 1):
        dates.append(d)
        vals.append(1.0 if date(2008, 1, 1) <= d <= date(2009, 6, 1) else 0.0)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    spans = _recession_spans(dates, vals)
    assert spans == [{"start": "2008-01", "end": "2009-06"}]
    # ongoing recession at the end of the series still closes its span
    spans = _recession_spans(dates, [1.0] * len(dates))
    assert spans == [{"start": "2007-01", "end": "2010-12"}]


def test_confluence_forward_window_is_intersection_arithmetic():
    # oil red episode -> its 3-12m damage window ahead must be the peak window
    flat = [50.0] * 504
    spike = [100.0] * 63
    bundle = {"oil": _daily(date(2024, 1, 1), flat + spike)}
    conf = build_pin_history(bundle)["confluence"]
    assert conf is not None
    assert conf["peak_ahead"] >= 1
    assert conf["peak_window"] is not None
    assert "oil_shock" in conf["peak_channels"]
    # without a recession series there is no validation block
    assert conf["validation"] is None


def test_overlap_validation_counts_hits_vs_base_rate():
    # a +100% oil spike in the MIDDLE of history, so its 3-12m damage window
    # falls inside observed months, plus a synthetic USREC onset inside it
    vals = [50.0] * 504 + [100.0] * 63 + [50.0] * 504
    oil_dates = [date(2022, 1, 1) + timedelta(days=i) for i in range(len(vals))]
    # spike ~2023-05..07 -> red peak ~2023-07 -> window ~2023-10..2024-07;
    # recession onset 2024-01 sits inside it
    rec_dates, rec_vals = [], []
    d = date(2020, 1, 1)
    while d <= date(2027, 12, 1):
        rec_dates.append(d)
        rec_vals.append(1.0 if date(2024, 1, 1) <= d <= date(2024, 6, 1) else 0.0)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    bundle = {"oil": (oil_dates, vals), "recession": (rec_dates, rec_vals)}
    conf = build_pin_history(bundle)["confluence"]
    v = conf["validation"]
    assert v is not None
    assert v["n_onsets_covered"] >= 1
    k1 = next((t for t in v["thresholds"] if t["k"] == 1), None)
    assert k1 is not None and 0.0 <= k1["hit_rate"] <= 1.0
    assert 0.0 <= v["base_rate"] <= 1.0
    # conditional months are few; the caveat must always ride along
    assert "never a calibrated probability" in conf["caveat"]


def test_mid_rank_reduces_to_hazen_when_untied():
    """The mid-rank form must not move anything on untied data."""
    from app.metrics.pins import rank_pct

    for n in (2, 7, 100, 1056, 7_500):
        for rank in (1, 2, n // 2, n - 1, n):
            hazen = 100.0 * (rank - 0.5) / n
            assert rank_pct(rank - 1, 1, n) == pytest.approx(hazen, abs=1e-12)


def test_ties_share_the_midpoint_of_their_block():
    """Highest-rank-on-ties scored every member as if it were the top of the block.

    CCC OAS is quoted to 2dp and its percentile is the primary private-credit
    driver, so this bias is not cosmetic.
    """
    from app.metrics.pins import _percentile, rank_pct

    # 10-way tie occupying ranks 91..100 of 1000
    assert rank_pct(90, 10, 1000) == pytest.approx(9.5)
    assert 100.0 * (100 - 0.5) / 1000 == pytest.approx(9.95)   # the old, biased value

    # every member of a tie block gets the SAME percentile, and it is the midpoint
    vals = [1.0] * 5 + [2.0] * 10 + [3.0] * 5
    assert _percentile(vals, 2.0) == pytest.approx(50.0)       # 5 below + 10/2 = 10 of 20
    assert _percentile(vals, 1.0) == pytest.approx(12.5)       # 0 below + 5/2 = 2.5 of 20
    assert _percentile(vals, 3.0) == pytest.approx(87.5)       # 15 below + 5/2 of 20
    # and a tied all-time high is no longer scored as an untied one
    assert _percentile(vals, 3.0) < 100.0 - 50.0 / len(vals)


def test_live_and_hindcast_agree_on_a_tied_series():
    """Parity must survive ties, not just the untied happy path."""
    from app.metrics.pins import _percentile

    vals = [5.0, 5.0, 7.0, 5.0, 9.0, 7.0, 9.0, 9.0]
    dts = [date(2025, 1, 1) + timedelta(days=7 * i) for i in range(len(vals))]
    _, pv = _expanding_percentile(dts, vals, min_obs=1)
    assert pv[-1] == pytest.approx(_percentile(vals, vals[-1]), abs=0.05)



def test_live_and_hindcast_agree_at_a_REALISTIC_sample_size():
    """The small-n parity tests ran where rounding does not bite.

    At n=1,056 the live/hindcast gap from the ceiling bug was 0.047 -- INSIDE
    the 0.05 tolerance the other parity tests use, so they passed while the live
    board returned exactly 100.0 and the hindcast did not.
    """
    from app.metrics.pins import _percentile

    n = 1200
    vals = [float(x) for x in range(n)]
    dts = [date(2000, 1, 1) + timedelta(days=i) for i in range(n)]
    _, pv = _expanding_percentile(dts, vals, min_obs=1)
    live = _percentile(vals, vals[-1])
    assert live < 100.0 and pv[-1] < 100.0          # the invariant, on BOTH sides
    assert pv[-1] == pytest.approx(live, abs=0.1)   # 1dp rounding band at this n
