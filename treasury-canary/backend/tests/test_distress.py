"""Merge-blocking gate: the Distress panel shows exactly what the study scored.

studies/distress-signals.md scored each series once under SPEC v1. The panel
recomputes live readings with its own copy of the rule (metrics/distress.py);
these tests pin that copy to the study's onsets on the frozen history, pin the
role labels to the study's grades, and pin that the panel cannot alert —
nothing passed the pre-registered test as a recession warning.
"""
from __future__ import annotations

import json
import os

import pytest

from app.metrics import distress as Dm
from app.sources.uscourts_f2 import load_history, parse_f2

HIST = load_history()
FX = os.path.join(os.path.dirname(__file__), "fixtures")
RESULTS = os.path.join(os.path.dirname(__file__), "..", "..", "studies", "distress_signals", "results.json")


def _q(values: dict[str, float]) -> dict[int, float]:
    return {Dm.qidx(k): v for k, v in values.items()}


def _onsets(values, raws, floor=None):
    return [Dm.qstr(o) for o in Dm.onsets(Dm.rule_path(values, raws, floor=floor))]


COURT = Dm._raws(HIST["rules"]["court_raw_masks"])


def test_business_filings_rule_reproduces_the_study():
    # study (N1, 1995Q4 placement): onsets released 1986-01, 1992-01, 2002-01,
    # i.e. reference quarters 1985Q4, 1991Q4, 2001Q4 - all FALSE ALARMS; none
    # after the 2020-23 mask (the post-mask spell is left-censored)
    assert _onsets(_q(HIST["national_business_q"]), COURT) == ["1985Q4", "1991Q4", "2001Q4"]


def test_consumer_and_chapter11_rules_reproduce_the_study():
    # study N2 quarterly robustness: 2001-10 (LATE) and 2003-07 (FALSE)
    assert _onsets(_q(HIST["national_nonbusiness_q"]), COURT) == ["2001Q3", "2003Q2"]
    # study N3 (display only): 2016-07, 2018-04, 2026-04
    assert _onsets(_q(HIST["national_bus_ch11_q"]), COURT) == ["2016Q2", "2018Q1", "2026Q1"]


@pytest.mark.parametrize("sid,expected", [
    # release month = quarter end + 2 in the study
    ("CORALACBS", ["1988Q3", "1990Q1", "1996Q1", "2001Q1", "2007Q3"]),
    ("DRSFRMACBS", ["2001Q2", "2006Q3"]),
    ("DRALACBS", ["1991Q1", "2001Q2", "2007Q2"]),
    ("DRBLACBS", ["1991Q1", "1999Q3", "2008Q2", "2016Q1"]),
])
def test_bank_rule_reproduces_the_study(sid, expected):
    floor = HIST["record"]["bank"][sid]["floor_pp"]
    vals = _q(HIST["bank_history"][sid])
    assert _onsets(vals, Dm.bank_raws(HIST, sid), floor=floor) == expected


def test_a_masked_block_resets_the_quiet_run():
    # OFF for 4 quarters, a masked quarter, then ON: not an onset (SPEC v1)
    path = [{"q": i, "g": 0.0, "d": 0.0, "on": False} for i in range(4)] + \
           [{"q": 4, "g": None, "d": None, "on": None}, {"q": 5, "g": 0.2, "d": 1, "on": True}]
    assert Dm.onsets(path) == []
    path[4] = {"q": 4, "g": 0.0, "d": 0.0, "on": False}
    assert Dm.onsets(path) == [5]


def test_the_panel_cannot_alert_and_carries_the_study_roles():
    p = Dm.build_distress(HIST)
    assert p["alert"] is None
    assert p["national"]["business"]["role"] == "does not lead"
    assert p["national"]["consumer"]["role"] == "does not lead"
    roles = {b["id"]: b["role"] for b in p["bank"]}
    assert roles["CORALACBS"] == "confirms"
    assert all(r in ("confirms", "does not lead") for r in roles.values())   # nothing 'leads'
    assert p["states"]["role"] == "no evidence of a lead"            # consumer filings
    assert p["states"]["business_role"] == "confirms"                # business Ch 7: same-window only
    assert "transform-sensitive" in {q for b in p["bank"] for q in b["qualifiers"]}
    # the variant's record carries its false alarms and its Holm-adjusted size p
    note = next(b["variant_note"] for b in p["bank"] if b["id"] == "CORALACBS")
    assert "3 false alarms" in note and "after Holm" in note
    assert "untested" in p["national"]["chapter11"]["note"]


def test_current_readings_on_the_frozen_history():
    p = Dm.build_distress(HIST)
    c = p["national"]["consumer"]
    assert c["asof"] == "2026Q2" and c["filings_12m"] == 581_570      # AO F-2 12-month national row, Jun-2026
    # one per-capita basis: 50 states + DC filings over their population at the
    # window's midpoint (2026.0) - reproduced by the study's load.pop_at
    assert c["filings_12m_50dc"] == 575_614
    # 3 decimals pin the midpoint: 2025.75 would give 1.682, 2026.25 1.678
    assert c["per_1000"] == 1.68 and abs(c["yoy_12m"] - 0.12) < 0.01
    assert round(c["per_1000_by_year"]["2010"], 1) == 4.9 and round(c["per_1000_by_year"]["2019"], 1) == 2.3
    assert min(v for y, v in c["per_1000_by_year"].items() if 1986 <= int(y) <= 2019) > c["per_1000"]
    st = {r["state"]: r["per_1000"] for r in p["states"]["rows"]}
    assert st["TN"] == 3.043                                          # 3.056 on the 2025-population basis
    b = p["national"]["business"]["rule"]
    # above +10% since 2026Q1 but only 3 quarters off before it: not a fresh onset
    assert b["asof"] == "2026Q2" and b["on"] is True and b["fresh_onset"] is False
    assert len(p["states"]["rows"]) == 51


def test_a_newly_published_quarter_is_merged():
    t3 = parse_f2(os.path.join(FX, "bf_f2.3_0630.2026.xlsx"))
    t12 = parse_f2(os.path.join(FX, "bf_f2_0630.2026.xlsx"))
    p = Dm.build_distress(HIST, live={"2026Q3": {"3month": t3, "12month": t12}})
    assert p["live_quarters"] == ["2026Q3"]
    assert p["national"]["consumer"]["asof"] == "2026Q3"
    # the fixture is the Jun-2026 table relabelled: same numerator, population at
    # the 2026.25 midpoint, growth against the frozen 2025Q3 state rows
    assert p["national"]["consumer"]["per_1000"] == 1.678
    assert p["national"]["consumer"]["yoy_12m"] == 0.0915
    assert p["states"]["asof"] == "2026Q3"
    assert p["national"]["business"]["rule"]["asof"] == "2026Q3"


@pytest.mark.skipif(not os.path.exists(RESULTS), reason="study results not in this checkout")
def test_record_matches_the_study_results():
    r = json.load(open(RESULTS))
    for sid, rec in HIST["record"]["bank"].items():
        s = r["Q_C"]["series"][sid]
        want = "leads" if s["ALERT"] else ("confirms" if s["PANEL"] else "does not lead")
        assert rec["role"] == want, sid
        assert rec["false_alarms"] == s["grade"]["primary"]["false_alarms"], sid
    assert not r["Q_N"]["N1_ALERT"] and not r["Q_N"]["N2_ALERT"] and not r["Q_H"]["SHIP"]
    assert all(v["verdict"] != "REGIONAL ALERT" for v in r["Q_R"]["ship"].values())
    assert HIST["record"]["bank"]["CORALACBS"]["qualifiers"] == r["Q_C"]["series"]["CORALACBS"]["qualifiers"]
    assert (HIST["record"]["states"]["business_role"] == "confirms") == \
        r["Q_R"]["ship"]["S2"]["verdict"].startswith("confirms")


def test_the_bottoming_watch_reproduces_the_study_and_cannot_alert():
    # studies/distress-bottoms.md, R (court business filings): roll-overs released
    # 1983-04 (5 months after the 1982 trough), 1987-10 (no recession), 2002-04
    # (5 after 2001) and 2024-10 (no recession); 2026Q2 armed, not rolled over
    p = Dm.build_distress(HIST)
    w = p["bottoming_watch"]
    assert w["signals"] == ["1983-04", "1987-10", "2002-04", "2024-10"]
    assert w["asof"] == "2026Q2" and abs(w["g"] - 0.1917) < 0.0005 and w["armed"] and not w["rolled_over_now"]
    assert w["status"] == "armed, not rolled over"
    assert p["alert"] is None


@pytest.mark.skipif(not os.path.exists(os.path.join(os.path.dirname(RESULTS), "bottoms_results.json")),
                    reason="bottoms study results not in this checkout")
def test_the_bottoming_watch_matches_the_bottoms_results():
    r = json.load(open(os.path.join(os.path.dirname(RESULTS), "bottoms_results.json")))
    w = Dm.build_distress(HIST)["bottoming_watch"]
    assert w["signals"] == [x["release"] for x in r["R"]["primary"]["signals"]]
    assert r["P"]["grade"]["tested"] == ["CONFIRMS-trough"]
    assert not r["P"]["grade"]["conditions_descriptive"]["CONFIRMS-trough"]["pass"]   # nothing passed
