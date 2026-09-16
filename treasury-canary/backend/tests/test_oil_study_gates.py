"""Merge-blocking gates for the oil-shock study's §5 actions
(studies/oil-shock-recession-weight.md, 2026-09-16).

1. The live NOPI12 helper is the study's D2 definition: it reproduces the frozen
   panel's nopi36_sum12 column on the monthly spot series.
2. The extreme anchor is the named worst postwar episode's reading (1974-01),
   not a fitted number.
3. The 12-month change is a context gauge: it can no longer take the channel RED.
4. The headline recession probability never sees oil (the "never blended" rule).
5. The hindcast keeps the oil-alone / policy-alone split.
"""
import csv
import datetime
import inspect
import os

from app.metrics import recession, recession_model
from app.metrics.pins import ANCHORS, build_pin_board, nopi12_series

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "studies", "oil_shock_weight", "data", "panel.csv")
NOPI_LABEL = "Net oil price increase, 12m cumulative (vs 3-year high)"


def _panel():
    rows = list(csv.DictReader(open(PANEL)))
    dates = [datetime.date.fromisoformat(r["date"]) for r in rows]
    wti = [float(r["wti"]) if r["wti"] else None for r in rows]
    ref = {datetime.date.fromisoformat(r["date"]): float(r["nopi36_sum12"])
           for r in rows if r["nopi36_sum12"]}
    return dates, wti, ref


def test_nopi12_helper_reproduces_study_column():
    dates, wti, ref = _panel()
    d, v = nopi12_series(dates, wti)
    got = dict(zip(d, v))
    common = [k for k in ref if k in got]
    assert len(common) > 800
    worst = max(abs(got[k] - ref[k]) for k in common)
    assert worst < 0.02, worst                      # 2-dp rounding only
    assert got[datetime.date(2026, 8, 1)] == 13.28  # the live reading the study quotes


def test_nopi_extreme_anchor_is_the_1974_reading():
    _, _, ref = _panel()
    peak = max(v for k, v in ref.items() if datetime.date(1973, 1, 1) <= k <= datetime.date(1975, 12, 1))
    benign, yellow, red, extreme, higher, cap = ANCHORS[NOPI_LABEL]
    assert (benign, yellow, red) == (0, 10, 25) and higher and cap == 100
    assert round(peak, 1) == extreme == 104.4


def test_wti_change_is_a_capped_context_gauge():
    # +100% in 12 months but < 48 months of history: the NOPI leg is STALE, the
    # 12-month gauge reads +100% and may only take the channel to YELLOW
    days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(400)]
    vals = [50.0] * 337 + [100.0] * 63
    board = build_pin_board({"oil": (days, vals)})
    oil = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    parts = {p["label"]: p for p in oil["parts"]}
    assert parts[NOPI_LABEL]["status"] == "STALE"
    assert parts["WTI, 12-month change"]["value"] == 100.0
    assert parts["WTI, 12-month change"]["score"] == 79.0
    assert oil["status"] == "YELLOW"
    assert ANCHORS["WTI, 12-month change"][5] == 79


def test_recession_probability_never_sees_oil():
    # Q2 decision rule NOT MET: the dial stays curve-only, byte-identical.
    for mod in (recession, recession_model):
        assert "oil" not in inspect.getsource(mod).lower()
    assert recession.recession_probability(0.0) == 29.7
    assert recession.recession_probability(0.86) == 14.1


def test_hindcast_keeps_the_oil_alone_split():
    src = open(os.path.join(ROOT, "studies", "pin_rule_hindcast.py")).read()
    for rule in ("oil_shock_window+curve", "oil_shock_red", "policy_shock_window+curve"):
        assert f'"{rule}"' in src
