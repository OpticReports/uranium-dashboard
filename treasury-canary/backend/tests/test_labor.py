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
