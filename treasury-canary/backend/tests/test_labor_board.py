"""Merge-blocking gates for the Labor Stress Board (studies/labor-stress-board.md)."""
from __future__ import annotations

import csv
import json
import os
from datetime import date, timedelta

from app.api import routes_labor as RL
from app.metrics import labor_stress as L

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DATA = os.path.join(ROOT, "studies", "labor_stress", "data")


def _load(sid):
    d, v = [], []
    path = os.path.join(DATA, f"{sid}.csv")
    if not os.path.exists(path):
        return d, v
    for r in csv.reader(open(path)):
        if r[0][:1].isdigit():
            d.append(date.fromisoformat(r[0]))
            v.append(float(r[1]) if r[1] not in (".", "") else None)
    return d, v


def test_weekly_series_enter_the_month_on_the_knowable_week():
    # Aug 2026: the 12th is a Wednesday, reference week ends Sat Aug 15 -> Aug 22
    assert L.ref_week_plus7((2026, 8)) == date(2026, 8, 22)
    # Apr 2026: the 12th is a Sunday, its Sun-Sat week ends Apr 18 -> Apr 25
    assert L.ref_week_plus7((2026, 4)) == date(2026, 4, 25)
    sats = [date(2026, 8, 1) + timedelta(days=7 * i) for i in range(5)]
    got = L.weekly_to_month(sats, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert got[(2026, 8)] == 4.0           # Aug 22, not the month's last week (Aug 29)


def test_claims_yoy_uses_exactly_52_observations():
    d = [date(2020, 1, 4) + timedelta(days=7 * i) for i in range(64)]
    v = [100.0] * 52 + [110.0] * 12
    # week i >= 55: current 4 weeks all 110, the 4 weeks 52 observations
    # earlier all 100 -> exactly +10%. A 53-observation lag would mix in 110s.
    out = L.claims_yoy(d, v)
    assert out and all(abs(x - 10.0) < 1e-9 for x in out.values())
    v2 = [100.0] * 51 + [105.0] + [110.0] * 12    # week 51 differs: only a
    out2 = L.claims_yoy(d, v2)                    # 52-obs lag sees it at i=103
    assert all(abs(x - 10.0) < 1e-9 for x in out2.values())


def test_lit_board_and_strict_sos():
    vals = {"A1": {(2020, 1): 0.20, (2020, 2): 0.201}, "A2": {}, "A3": {},
            "B1": {(2020, 2): 0.5}, "B2": {}, "C1": {(2020, 1): 0.6}}
    lit = L.lit(vals)
    assert lit["A1"][(2020, 1)] is False and lit["A1"][(2020, 2)] is True   # strict >
    b = L.board(lit)
    assert b[(2020, 1)] == "WATCH" and b[(2020, 2)] == "ALERT"


def test_frozen_record_equals_the_study_output():
    res = json.load(open(os.path.join(ROOT, "studies", "labor_stress", "results.json")))
    rec = RL.BOARD_RECORD
    assert rec["hits"] == res["composite"]["hits"]
    assert rec["false_alarms_1972_2020"] == len(res["composite"]["false_alarms"])
    assert rec["sahm_false_alarms_1972_2020"] == len(res["sahm_current_vintage"]["false_alarms"])
    assert rec["paired_timing_vs_sahm"] == res["paired_timing_vs_sahm"]
    assert rec["fired_2024"] in res["composite"]["final_2021_2024"]
    assert (rec["red_gate"] == "fail") == (res["criteria"]["ship_red_alert"] is False)
    assert f"{rec['hits']} of {rec['peaks']}" in rec["text"]
    assert "Aug 2024" in rec["text"]               # the failure travels with the claim


def test_board_payload_on_frozen_data():
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    p = RL.board_payload(series)
    assert p["month"] == "2026-08"                  # evaluated on the jobs-report grid
    assert p["state"] == "CLEAR" and p["n_lit"] == 0
    assert p["ledger"] == []                        # out-of-sample starts 2026-09
    b1 = next(r for r in p["rules"] if r["id"] == "B1")
    assert b1["value"] == 0.4 and b1["lit"] is False
    keys = {s["key"] for s in p["strip"]}
    assert {"u3", "paur", "u6", "nei", "job_finding", "lt_rate", "fb_lfpr"} <= keys
    paur = next(s for s in p["strip"] if s["key"] == "paur")
    assert "upper bound" in paur["label"].lower()


def test_alert_fires_only_on_a_new_episode():
    def payload(states):
        return {"state": states[-1], "month": "2026-10", "n_lit": 2,
                "history": [{"state": s} for s in states],
                "rules": [{"id": "A2", "label": "x", "lit": True}]}
    fresh = RL.board_alert_event(payload(["CLEAR"] * 6 + ["ALERT"]), date(2026, 11, 6))
    assert fresh is not None and fresh.severity == "WARN"
    assert "Aug 2024" in fresh.rationale
    assert RL.board_alert_event(payload(["CLEAR"] * 5 + ["ALERT", "ALERT"]),
                                date(2026, 11, 6)) is None
    assert RL.board_alert_event(payload(["CLEAR"] * 7), date(2026, 11, 6)) is None
