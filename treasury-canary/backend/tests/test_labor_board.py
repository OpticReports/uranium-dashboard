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
    assert "median 2 months" in rec["text"] and rec["paired_timing_vs_sahm"] == -2
    assert rec["hits_ex2020"] == res["composite"]["hits_ex2020"]
    assert f"{rec['hits_ex2020']} of 6 excluding 2020" in rec["text"]
    # the Board does not beat its best single rule, and says so
    a2 = res["rules"]["A2"]
    best = rec["best_single"]
    assert best["hits"] == a2["hits"] >= rec["hits"]
    assert best["false_alarms_1972_2020"] == len(a2["false_alarms"])
    assert best["fired_2024"] in a2["final_2021_2024"]
    assert f"{best['hits']} of 7 vs {rec['hits']}" in rec["text"] and "did better" in rec["text"]
    # erratum: 1981 is LATE under spec A3 (window must lie INSIDE a spell)
    p81 = next(x for x in res["composite"]["per_peak"] if x["peak"] == "1981-07")
    assert p81["outcome"] == "LATE" and "late for 1973 and 1981" in rec["text"]


def test_board_payload_on_frozen_data():
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    p = RL.board_payload(series)
    json.dumps(p)                                   # the route must serialise (no lambdas)
    assert p["month"] == "2026-08"                  # evaluated on the jobs-report grid
    assert p["state"] == "CLEAR" and p["n_lit"] == 0 and p["missing"] == []
    assert p["c1_source"] == "SAHMREALTIME"
    assert p["ledger"] == []                        # out-of-sample starts 2026-09
    b1 = next(r for r in p["rules"] if r["id"] == "B1")
    assert b1["value"] == 0.4 and b1["lit"] is False
    keys = {s["key"] for s in p["strip"]}
    assert {"u3", "paur", "u6", "nei", "job_finding", "lt_rate", "fb_lfpr"} <= keys
    paur = next(s for s in p["strip"] if s["key"] == "paur")
    assert "upper bound" in paur["label"].lower()
    assert paur["trend"] == "flat"                  # +0.04 sits inside the dead band
    v = p["strip_verdict"]
    assert v.startswith("U-3 4.14% vs participation-adjusted 4.58%: counting every prime-age")
    assert "adds at most 0.44pp" in v and "25th percentile" in v
    assert "slack sits outside the headline" not in v        # U-6 is 3.6pp above U-3
    assert "job-finding rate" in v.split("Better:")[0]          # worse side
    assert "U-6" in v.split("Better:")[1]


def test_missing_rules_never_read_clear():
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    for drop, gone in ((("iursa", "ccnsa", "job_losers"), ["A1", "A2", "A3"]),
                       (("clf",), ["A2", "B2"]), (("epop_prime",), ["B1"])):
        s = dict(series)
        for k in drop:
            s[k] = ([], [])
        p = RL.board_payload(s)
        assert p["state"] == "INCOMPLETE", drop
        assert p["missing"] == gone and p["n_evaluated"] == 6 - len(gone)
        assert all(r["lit"] is None for r in p["rules"] if r["id"] in gone)
    # a lagging layoff series: its stale value is shown, never counted
    s = dict(series)
    d, v = s["job_losers"]
    s["job_losers"] = (d[:-1], v[:-1])
    p = RL.board_payload(s)
    a2 = next(r for r in p["rules"] if r["id"] == "A2")
    assert p["state"] == "INCOMPLETE" and a2["stale"] and a2["lit"] is None
    assert a2["month"] == "2026-07"
    # real-time Sahm missing or a month behind: C1 is MISSING for the CPS
    # month (never CLEAR for an older month, never swapped for UNRATE)
    for sahm in (([], []), (series["sahm"][0][:-1], series["sahm"][1][:-1])):
        s = dict(series)
        s["sahm"] = sahm
        p = RL.board_payload(s)
        assert p["month"] == "2026-08" and p["state"] == "INCOMPLETE"
        assert p["missing"] == ["C1"] and p["c1_source"] == "SAHMREALTIME"
    # no jobs-report month at all -> no state, never CLEAR
    s = dict(series)
    s["sahm"], s["unrate"] = ([], []), ([], [])
    p = RL.board_payload(s)
    assert p["state"] is None and p["month"] is None


def test_alert_stands_with_a_rule_missing_and_quotes_the_margin():
    # data through Aug 2024 (current vintage; FRED dates monthly observations
    # to the 1st, so this is a state test, not a real-time replay), with
    # insured unemployment down
    cut = date(2024, 8, 31)
    series = {}
    for k, sid in RL.BOARD_SERIES.items():
        d, v = _load(sid)
        keep = [i for i, x in enumerate(d) if x <= cut]
        series[k] = ([d[i] for i in keep], [v[i] for i in keep])
    series["iursa"] = ([], [])
    p = RL.board_payload(series)
    assert p["month"] == "2024-08" and p["missing"] == ["A1"]
    assert p["state"] == "ALERT"                     # a missing rule only lowers the count
    ev = RL.board_alert_event(p, date(2024, 9, 6))
    assert ev is not None and "A2 Job losers" in ev.rationale
    assert "+0.309pp (line 0.3)" in ev.rationale     # the marginal crossing is visible
    assert "A1 not yet available" in ev.rationale and ev.detail["missing"] == ["A1"]


def test_ledger_persists_each_onset_at_first_sight():
    p = {"month": "2026-11", "ledger": [
        {"month": "2026-10", "kind": "A2", "event": "A2 onset", "value": 0.31},
        {"month": "2026-11", "kind": "ALERT", "event": "ALERT onset"}]}
    evs = RL.board_ledger_events(p, date(2026, 12, 4))
    assert [e.dedup_key for e in evs] == ["A2:2026-10", "ALERT:2026-11"]
    assert all(e.severity == "INFO" and e.event_type == "labor_board_onset" for e in evs)
    assert evs[0].detail["first_seen"] == "2026-12-04" and evs[0].detail["value"] == 0.31
    # nothing before the out-of-sample start is ever listed
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    assert all(r["month"] >= "2026-09" for r in RL.board_payload(series)["ledger"])


def test_ledger_logic_on_the_2024_replay(monkeypatch):
    # the ledger code path, exercised on real onsets: open the window at 2024-01
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    monkeypatch.setattr(RL, "LEDGER_FROM", (2024, 1))
    got = [(r["month"], r["kind"], r.get("value")) for r in RL.board_payload(series)["ledger"]]
    assert got == [("2024-07", "C1", 0.53), ("2024-08", "A2", 0.309),
                   ("2024-08", "ALERT", None), ("2024-08", "B2", 0.52)]
    monkeypatch.setattr(RL, "LEDGER_FROM", (2024, 8))       # the start month is included
    got = [(r["month"], r["kind"]) for r in RL.board_payload(series)["ledger"]]
    assert got == [("2024-08", "A2"), ("2024-08", "ALERT"), ("2024-08", "B2")]


def test_live_onsets_are_the_study_onsets():
    # the live ledger's onset rule reproduces the frozen study's onsets exactly
    res = json.load(open(os.path.join(ROOT, "studies", "labor_stress", "results.json")))
    series = {k: _load(sid) for k, sid in RL.BOARD_SERIES.items()}
    lit = L.lit(L.rule_values(series, sahm_from="unrate"))
    for rid in L.RULES:
        ons = [L.ym_str(k) for k in L.onsets(lit[rid]) if (1972, 1) <= k <= (2020, 12)]
        assert ons == sorted(res["rules"][rid]["onsets_classified"]), rid


def test_nei_change_is_suppressed_in_jan_2027_and_ordinals():
    d = [date(2026, m, 1) for m in range(1, 13)] + [date(2027, 1, 1)]
    v = [8.07] + [7.6] * 11 + [7.5]
    nei = next(x for x in L.strip({"nei": (d, v)}) if x["key"] == "nei")
    assert nei["chg_12m"] is None and nei["trend"] is None   # not "better" on an artefact
    assert [L._ordinal(n) for n in (1, 2, 3, 11, 12, 13, 21, 22, 25, 101)] == \
        ["1st", "2nd", "3rd", "11th", "12th", "13th", "21st", "22nd", "25th", "101st"]


def test_alert_fires_only_on_a_new_episode():
    def payload(states):
        return {"state": states[-1], "month": "2026-10", "n_lit": 2,
                "history": [{"state": s} for s in states],
                "rules": [{"id": "A2", "label": "x", "lit": True, "stale": False,
                           "value": 0.309, "unit": "pp", "threshold": 0.3}]}
    fresh = RL.board_alert_event(payload(["CLEAR"] * 6 + ["ALERT"]), date(2026, 11, 6))
    assert fresh is not None and fresh.severity == "WARN"
    assert "Aug 2024" in fresh.rationale
    assert RL.board_alert_event(payload(["CLEAR"] * 5 + ["ALERT", "ALERT"]),
                                date(2026, 11, 6)) is None
    assert RL.board_alert_event(payload(["CLEAR"] * 7), date(2026, 11, 6)) is None
