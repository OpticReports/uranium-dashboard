from datetime import date

from app.metrics.base import Status
from app.metrics.labor import _sahm_from_unrate, build_labor_metrics
from app.scoring.composite import compute_composite


def _months(n, start=(2020, 1)):
    y, m = start
    out = []
    for i in range(n):
        out.append(date(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1, 1))
    return out


def test_sahm_gap_triggers_on_rising_unemployment():
    # unemployment flat at 3.5 then ramps to 4.5 -> gap ~1.0 (well above 0.5)
    dates = _months(24)
    unrate = [3.5] * 12 + [3.6, 3.8, 4.0, 4.2, 4.4, 4.5, 4.5, 4.5, 4.5, 4.5, 4.5, 4.5]
    d, gaps = _sahm_from_unrate(dates, unrate)
    assert gaps[-1] is not None and gaps[-1] >= 0.5


def test_sahm_low_when_flat():
    dates = _months(18)
    d, gaps = _sahm_from_unrate(dates, [4.0] * 18)
    assert gaps[-1] == 0.0


def test_sahm_negative_when_unemployment_falling():
    # Official definition (low of the PRIOR 12 months, excluding current) can go
    # negative while unemployment declines — matches FRED SAHMREALTIME behavior.
    dates = _months(24)
    unrate = [5.0 - i * 0.05 for i in range(24)]  # steadily falling
    d, gaps = _sahm_from_unrate(dates, unrate)
    assert gaps[-1] is not None and gaps[-1] < 0.0


def test_build_labor_metrics_and_informational_unrate():
    dates = _months(30)
    unrate = [3.5] * 18 + [3.7, 3.9, 4.1, 4.3, 4.5, 4.6, 4.6, 4.6, 4.6, 4.6, 4.6, 4.6]
    bundle = {"unrate": (dates, unrate), "sahm": ([], []), "claims_4wk": ([], [])}
    metrics = build_labor_metrics(bundle)
    by = {m.metric_id: m for m in metrics}
    assert by["labor.sahm"].category == "J"
    assert by["labor.sahm"].status in (Status.YELLOW, Status.RED)  # ramp -> elevated
    assert by["labor.unrate"].informational is True

    # informational unrate must NOT drag the composite (it's excluded)
    comp = compute_composite(metrics)
    assert "J" in comp.category_scores
    # J score reflects sahm (+ claims stale), not the GREEN informational unrate
    assert comp.category_scores["J"] > 0


# --- labor demand (V/U ratio, openings YoY, Indeed postings) -----------------

def _demand_bundle(openings, unemployed, months=None):
    dates = months or _months(len(openings), start=(2022, 1))
    return {
        "unrate": ([], []), "sahm": ([], []), "claims_4wk": ([], []),
        "openings": (dates, openings), "unemployed": (dates, unemployed),
    }


def test_vu_ratio_computed_and_classified():
    # openings 8,000k vs 10,000k unemployed -> V/U 0.80 -> RED (<= 0.90)
    bundle = _demand_bundle([8000.0] * 24, [10000.0] * 24)
    by = {m.metric_id: m for m in build_labor_metrics(bundle)}
    vu = by["labor.vu_ratio"]
    assert vu.value == 0.8
    assert vu.status is Status.RED
    assert vu.informational is False  # composite member


def test_openings_yoy_capped_at_yellow_in_excess_demand_regime():
    # openings crash -20% YoY (raw RED) but V/U stays ~2.0 -> normalization, YELLOW
    openings = [10000.0] * 12 + [8000.0] * 12
    bundle = _demand_bundle(openings, [4600.0] * 24)
    by = {m.metric_id: m for m in build_labor_metrics(bundle)}
    oy = by["labor.openings_yoy"]
    assert oy.value == -20.0
    assert oy.status is Status.YELLOW
    assert oy.extra["capped_by_vu"] is True


def test_openings_yoy_red_when_vu_low():
    # same -20% crash but V/U ~0.95 (yellow zone) -> the cap must NOT apply
    openings = [10000.0] * 12 + [8000.0] * 12
    bundle = _demand_bundle(openings, [8400.0] * 24)
    by = {m.metric_id: m for m in build_labor_metrics(bundle)}
    oy = by["labor.openings_yoy"]
    assert oy.value == -20.0
    assert oy.status is Status.RED
    assert oy.extra["capped_by_vu"] is False


def test_indeed_yoy_informational_with_daily_dates():
    from datetime import date, timedelta
    # ~2 years of daily index data declining 10%/yr -> YoY ~ -10 -> YELLOW band
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(730)]
    vals = [120.0 * (1 - 0.10) ** (i / 365.0) for i in range(730)]
    bundle = {
        "unrate": ([], []), "sahm": ([], []), "claims_4wk": ([], []),
        "indeed_postings": (dates, vals),
    }
    by = {m.metric_id: m for m in build_labor_metrics(bundle)}
    im = by["labor.indeed_yoy"]
    assert im.informational is True
    assert im.value is not None and -11.0 < im.value < -9.0
    assert im.status is Status.YELLOW

    # informational -> must not enter the composite J bucket
    comp = compute_composite(build_labor_metrics(bundle))
    assert "J" not in comp.category_scores  # everything else stale/informational


def test_demand_metrics_stale_when_series_missing():
    bundle = {"unrate": ([], []), "sahm": ([], []), "claims_4wk": ([], [])}
    by = {m.metric_id: m for m in build_labor_metrics(bundle)}
    assert by["labor.vu_ratio"].status is Status.STALE
    assert by["labor.openings_yoy"].status is Status.STALE
    assert by["labor.indeed_yoy"].status is Status.STALE
