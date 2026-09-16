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
NOPI_LABEL = "Net oil price increase, 12m (vs 3-yr high)"


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


# --- post-review gates (2026-09-16 counter-agent: blind spots in the first set) ---

def _daily(start: datetime.date, vals):
    return [start + datetime.timedelta(days=i) for i in range(len(vals))], list(vals)


def test_nopi12_window_is_exactly_36_prior_months():
    # a high exactly 36 months back must still suppress the reading; 37 back must not
    base = datetime.date(2010, 1, 1)
    months = 120
    for gap, expect_zero in ((36, True), (37, False)):
        vals = []
        for m in range(months):
            v = 100.0 if m == (months - 1 - gap) else 50.0
            vals.append(v)
        # one print per month, dated the 1st
        dates = [datetime.date(base.year + (base.month - 1 + m) // 12, (base.month - 1 + m) % 12 + 1, 1)
                 for m in range(months)]
        vals[-1] = 100.0  # today's print equals the old high
        d, v = nopi12_series(dates, vals)
        assert d[-1] == dates[-1]
        assert (v[-1] == 0.0) is expect_zero, (gap, v[-1])


def test_nopi12_gap_month_blanks_and_never_stretches():
    # remove one calendar month: no output for the next 48 months, identical after
    n = 365 * 8
    dates, vals = _daily(datetime.date(2015, 1, 1), [50.0 + (i % 400) / 10.0 for i in range(n)])
    full = dict(zip(*nopi12_series(dates, vals)))
    keep = [(d, x) for d, x in zip(dates, vals) if not (d.year == 2018 and d.month == 6)]
    gapped = dict(zip(*nopi12_series([d for d, _ in keep], [x for _, x in keep])))
    assert datetime.date(2018, 6, 1) not in gapped
    blanked = [m for m in full if datetime.date(2018, 6, 1) <= m < datetime.date(2022, 6, 1)]
    assert blanked and all(m not in gapped for m in blanked)
    resumed = [m for m in full if m >= datetime.date(2022, 6, 1)]
    assert resumed and all(gapped[m] == full[m] for m in resumed)


def test_channel_strings_match_the_frozen_study_numbers():
    import json
    blocks = os.path.join(ROOT, "studies", "oil_shock_weight", "blocks")
    ev = json.load(open(os.path.join(blocks, "event", "numbers.json")))
    wk = json.load(open(os.path.join(blocks, "walk", "numbers.json")))
    wk = wk["decision_h12_L_primary_oil12m"]["value"]["inputs"]

    def val(d, k):
        x = d[k]
        return x["value"] if isinstance(x, dict) and "value" in x else x

    d2_hits = int(str(val(ev, "D2_h12_recall_caught")).split("/")[0])
    d2_fp = val(ev, "D2_h12_false_positives")
    d1_recall = val(ev, "Q1_primary_recall")
    d1_fp = val(ev, "Q1_primary_false_positives")
    month = round(val(ev, "Q1_primary_month_precision") * 100)
    base = round(val(ev, "Q1_primary_base_rate") * 100)
    dd = round(val(ev, "curve5_B1_D1-RED_alone_h12_month_precision") * 100)
    ddb = round(val(ev, "curve5_B1_D1-RED_alone_h12_base") * 100)
    a_dauc, b_dauc = wk["A"]["delta_auc"], wk["B"]["delta_auc"]

    n = 365 * 6
    board = build_pin_board({"oil": _daily(datetime.date(2019, 1, 1), [60.0] * n)})
    oil = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    text = " ".join([oil["basis"], oil["certainty"], oil["kill_rate"]])
    assert f"{d2_hits} of 11" in text and f"{d2_fp} named false positives" in text
    assert f"{d1_recall.replace('/', ' of ')}" in text and f"{d1_fp} false positives" in text
    assert f"{month}% vs {base}%" in text
    assert f"{dd}% vs {ddb}% base" in " ".join(p["detail"] for p in oil["parts"])
    assert f"dAUC {b_dauc:.3f} to {a_dauc:.3f}" in text


def test_anchor_comment_episode_peaks_are_the_panel_readings():
    # "+25 = its red anchor -- 1990 / 2000 / 2022 printed 52 / 30 / 48"
    dates, wti, ref = _panel()
    peaks = {}
    for name, lo, hi in (("1990", (1990, 1), (1991, 12)), ("2000", (1999, 1), (2001, 12)), ("2022", (2021, 1), (2023, 12))):
        peaks[name] = max(v for k, v in ref.items() if datetime.date(*lo, 1) <= k <= datetime.date(*hi, 1))
    assert [round(peaks[k]) for k in ("1990", "2000", "2022")] == [52, 30, 48]
    n = 365 * 6
    board = build_pin_board({"oil": _daily(datetime.date(2019, 1, 1), [60.0] * n)})
    oil = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    detail = next(p["detail"] for p in oil["parts"] if p["label"] == NOPI_LABEL)
    assert "52 / 30 / 48" in detail
