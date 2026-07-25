from datetime import date, timedelta

from app.metrics.base import Status
from app.metrics.crossasset import build_crossasset_metrics
from app.metrics.severity import build_severity
from app.scoring.composite import compute_composite
from app.sources.finra_margin import parse_margin_workbook


def _months(n, start=(2022, 1)):
    y, m = start
    return [date(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1, 1) for i in range(n)]


def _sp_daily(months, monthly_vals):
    """Daily-ish S&P series (one obs mid-month) matching the monthly closes."""
    return ([d + timedelta(days=14) for d in months], list(monthly_vals))


def _bundle(margin, credit, sp_vals, months=None):
    ms = months or _months(len(margin))
    return {
        "margin_debit": (ms, margin),
        "margin_credit": (ms, credit),
        "sp500": _sp_daily(ms, sp_vals),
        "10y": ([], []), "hy_oas": ([], []), "ig_oas": ([], []),
    }


def _by_id(bundle):
    return {m.metric_id: m for m in build_crossasset_metrics(bundle)}


def test_margin_excess_yoy_red_on_2000_style_blowoff():
    # margin +50% YoY while the market gains +10% -> excess +40pp -> RED
    margin = [1000.0] * 12 + [1500.0] * 12
    sp = [100.0] * 12 + [110.0] * 12
    by = _by_id(_bundle(margin, [500.0] * 24, sp))
    ex = by["crossasset.margin_excess_yoy"]
    assert ex.value == 40.0
    assert ex.status is Status.RED
    assert ex.informational is False  # composite member

    yoy = by["crossasset.margin_yoy"]
    assert yoy.value == 50.0
    assert yoy.status is Status.RED
    assert yoy.informational is True


def test_margin_excess_green_when_leverage_tracks_market():
    # both up 20% -> excess ~0 -> GREEN even though raw YoY is elevated-ish
    margin = [1000.0] * 12 + [1200.0] * 12
    sp = [100.0] * 12 + [120.0] * 12
    by = _by_id(_bundle(margin, [500.0] * 24, sp))
    assert by["crossasset.margin_excess_yoy"].value == 0.0
    assert by["crossasset.margin_excess_yoy"].status is Status.GREEN


def test_margin_coverage_informational_and_never_alarms():
    # record-low coverage (the viral chart) must stay GREEN + informational
    margin = [1000.0] * 24
    by = _by_id(_bundle(margin, [290.0] * 24, [100.0] * 24))
    cov = by["crossasset.margin_coverage"]
    assert cov.value == 0.29
    assert cov.informational is True
    assert cov.status is Status.GREEN

    # and none of the informational margin tiles enter the composite
    metrics = build_crossasset_metrics(_bundle(margin, [290.0] * 24, [100.0] * 24))
    comp = compute_composite(metrics)
    ids_in_h = [m.metric_id for m in metrics
                if m.category == "H" and not m.informational and m.status is not Status.STALE]
    assert "crossasset.margin_coverage" not in ids_in_h
    assert "crossasset.margin_yoy" not in ids_in_h
    assert comp is not None


def test_margin_metrics_stale_when_source_missing():
    by = _by_id({"sp500": ([], []), "10y": ([], []), "hy_oas": ([], []),
                 "ig_oas": ([], [])})
    assert by["crossasset.margin_excess_yoy"].status is Status.STALE
    assert by["crossasset.margin_yoy"].status is Status.STALE
    assert by["crossasset.margin_coverage"].status is Status.STALE


def test_excess_stale_without_sp500_but_yoy_still_lives():
    # FRED SP500 outage: raw YoY still computes; excess (needs SPX) goes STALE
    margin = [1000.0] * 12 + [1500.0] * 12
    b = _bundle(margin, [500.0] * 24, [100.0] * 24)
    b["sp500"] = ([], [])
    by = _by_id(b)
    assert by["crossasset.margin_yoy"].value == 50.0
    assert by["crossasset.margin_excess_yoy"].status is Status.STALE


def test_severity_prefers_finra_monthly_margin():
    # 6y of monthly FINRA margin + quarterly GDP: the margin_3y component must
    # use the 36-month lag (a real 3y change), not the quarterly 12-obs lag.
    ms = _months(72, start=(2019, 1))
    margin = [10000.0 + 1000.0 * i for i in range(72)]       # steady build
    qtrs = [d for d in ms if d.month in (1, 4, 7, 10)]
    gdp = ([d for d in qtrs], [25000.0] * len(qtrs))
    sev = build_severity({"margin_debit": (ms, margin), "gdp": gdp})
    comp = {c["id"]: c for b in sev["blocks"] for c in b["components"]}
    m3 = comp["margin_3y"]
    # ratio step/month = 0.1*1000/25000 = 4e-3 -> 3y change 0.144 (0.14 rounded).
    # A wrongly-applied quarterly lag (12 obs) would give 0.05 instead.
    assert m3["value"] is not None
    assert abs(m3["value"] - 0.14) < 0.011


def test_leverage_state_machine():
    from app.metrics.crossasset import LEVERAGE_PLAYBOOK, leverage_state
    assert leverage_state(None, None) is None
    assert leverage_state(-20.0, None) == "WASHOUT"
    assert leverage_state(-5.0, None) == "SQUEEZE"
    assert leverage_state(49.0, 28.2) == "BLOWOFF"      # June-2026 reading
    assert leverage_state(45.0, None) == "BLOWOFF"      # excess stale -> raw fallback
    assert leverage_state(20.0, 18.0) == "ELEVATED"
    assert leverage_state(32.0, None) == "ELEVATED"
    assert leverage_state(10.0, 2.0) == "NEUTRAL"
    # contraction outranks blowoff bands (can't be both)
    assert leverage_state(-1.0, 30.0) == "SQUEEZE"
    # every reachable state has a playbook entry with 12m stats + action
    for s in ("BLOWOFF", "ELEVATED", "NEUTRAL", "SQUEEZE", "WASHOUT"):
        pb = LEVERAGE_PLAYBOOK[s]
        assert pb["stats"]["fwd12"]["n"] > 0
        assert pb["action"]


def test_margin_series_shared_builder():
    from app.metrics.crossasset import margin_series
    margin = [1000.0] * 12 + [1500.0] * 12
    b = _bundle(margin, [450.0] * 24, [100.0] * 12 + [110.0] * 12)
    dates, yoy, excess, cov = margin_series(b, b["sp500"])
    assert len(dates) == len(yoy) == len(excess) == len(cov) == 24
    assert yoy[-1] == 50.0 and excess[-1] == 40.0 and cov[-1] == 0.3
    assert yoy[0] is None  # no 12m base yet


def test_margin_leverage_endpoint_price_overlays():
    from unittest.mock import patch
    margin = [1000.0] * 12 + [1500.0] * 12
    b = _bundle(margin, [500.0] * 24, [100.0] * 12 + [110.0] * 12)
    ms = b["margin_debit"][0]
    b["btc"] = ([d for d in b["sp500"][0]], [200.0 + i for i in range(len(ms))])
    b["recession"] = ([], [])
    with patch("app.api.routes_margin.fetch_bundle", return_value=b):
        from app.api.routes_margin import margin_leverage
        r = margin_leverage()
    first, last = r["series"][0], r["series"][-1]
    # overlays: raw month-end price passthrough + indexed-to-100-at-first-month
    assert first["spx"] == 110.0 and first["spx_idx"] == 100.0
    assert first["btc_idx"] == 100.0
    assert last["btc_idx"] > 100.0          # btc ramps -> index rises
    assert r["current"]["state"] == "BLOWOFF"
    assert "CBBTCUSD" in r["source"]


def test_parse_margin_workbook(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Year-Month", "Debit", "Credit cash", "Credit margin"])
    ws.append(["2026-06", 1502072, 217441, 223412])   # newest first, like FINRA
    ws.append(["2026-05", 1415557, 206600, 217256])
    ws.append(["1997-01", 103337, 68856, None])       # early rows: no margin col
    p = tmp_path / "m.xlsx"
    wb.save(p)
    out = parse_margin_workbook(str(p))
    d, v = out["margin_debit"]
    assert d == [date(1997, 1, 1), date(2026, 5, 1), date(2026, 6, 1)]  # ascending
    assert v[-1] == 1502072.0
    cd, cv = out["margin_credit"]
    assert cv[-1] == 217441.0 + 223412.0
    assert cv[0] == 68856.0   # cash-only months still count
