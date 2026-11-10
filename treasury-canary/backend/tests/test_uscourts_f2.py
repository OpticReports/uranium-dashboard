"""AO Table F-2 parser (sources/uscourts_f2.py) against two real tables.

Fixtures are the AO's own workbooks for the quarter ending 2026-06-30
(three-month and twelve-month). The expected numbers are the national rows as
printed, and state sums that equal the study's independently parsed
district file (studies/distress_signals/data/derived, checked 2026-10-12)."""
from __future__ import annotations

import os
from datetime import date

from app.sources.uscourts_f2 import new_quarters, parse_f2, quarter_end, url

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_three_month_table():
    p = parse_f2(os.path.join(FX, "bf_f2.3_0630.2026.xlsx"))
    n = p["national"]
    assert (n["total_all"], n["bus_all"], n["nb_all"]) == (162772, 6965, 155807)
    assert n["bus_ch7"] == 4060 and n["bus_ch11"] == 2382
    # 50 states + DC; territories (PR, VI, GU, NMI) dropped
    assert len(p["states"]) == 51 and "PR" not in p["states"] and "DC" in p["states"]
    # Arkansas is printed as 'AR ²' (footnote mark) and must still parse
    assert p["states"]["AR"]["total_all"] == 2047
    # multi-district states are summed: New York = N + E + S + W
    ny = p["states"]["NY"]
    assert ny["nb_all"] + ny["bus_all"] == ny["total_all"]
    # states + territories = nation
    terr = n["total_all"] - sum(s["total_all"] for s in p["states"].values())
    assert 0 < terr < 0.02 * n["total_all"]


def test_twelve_month_table():
    p = parse_f2(os.path.join(FX, "bf_f2_0630.2026.xlsx"))
    assert p["national"]["total_all"] == 608511
    assert len(p["states"]) == 51


def test_urls_follow_the_2025_pattern():
    assert url("3month", quarter_end(2026, 3)) == \
        "https://www.uscourts.gov/sites/default/files/document/bf_f2.3_0930.2026.xlsx"
    assert url("12month", quarter_end(2025, 4)) == \
        "https://www.uscourts.gov/sites/default/files/document/bf_f2_1231.2025.xlsx"


def test_no_probe_for_quarters_not_yet_ended():
    # 2026Q3 ends 2026-09-30: nothing is fetched on or before that day
    assert new_quarters((2026, 2), today=date(2026, 9, 30)) == {}
