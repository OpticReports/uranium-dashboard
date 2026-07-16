"""Pin history hindcast: episodes, lag windows, no-lookahead percentiles,
monthly-max sampling, and damage-window overlap in the collective series."""
from datetime import date, timedelta

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
    # 5 rising values: each is the max of history-so-far -> always 100th pctile
    _, pv = _expanding_percentile(dts, [1, 2, 3, 4, 5], min_obs=1)
    assert pv == [100.0] * 5
    # a mid-history spike ranks against PAST data only, not the later maximum
    _, pv = _expanding_percentile(dts, [1, 2, 10, 3, 50], min_obs=1)
    assert pv[2] == 100.0  # 10 was the max at the time, later 50 can't demote it


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
    assert abs(pv[-1] - _percentile(vals, vals[-1])) < 1e-9


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
