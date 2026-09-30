"""Merge-blocking gates for the +75bp long-yield spike alert and its words
(studies/rate-spike-recession.md)."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from app.api import routes_rates as R
from app.scoring.events import detect_rate_spike

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
KW = dict(spike_bp=75, rearm_bp=60, approach_bp=60, approach_rearm_bp=45,
          recent_days=10, spike_severity="WARN", approach_severity="INFO",
          spike_text="spike {d60:+.0f} on {date}", approach_text="near {d60:+.0f}")


def _days(vals, start=date(2026, 1, 1)):
    return [start + timedelta(days=i) for i in range(len(vals))], list(vals)


def test_fires_once_per_crossing_with_hysteresis():
    # up through 75, wobble 70-80 (must NOT re-fire), dip to 65 (still no
    # re-arm: needs < 60), back over 75 -> still nothing
    d, v = _days([40, 50, 76, 70, 80, 65, 79, 77])
    ev = detect_rate_spike(d, v, d[-1], **KW)
    spikes = [e for e in ev if e.event_type == "rate_spike"]
    assert len(spikes) == 1
    assert spikes[0].dedup_key == f"rate_spike:{d[2].isoformat()}"
    # the words carry the value AT THE CROSSING, not today's
    assert spikes[0].rationale == f"spike +76 on {d[2].isoformat()}"


def test_rearms_below_60_and_fires_again():
    d, v = _days([40, 76, 55, 78])
    ev = detect_rate_spike(d, v, d[-1], **KW)
    spikes = [e for e in ev if e.event_type == "rate_spike"]
    # only the LATEST crossing is returned (the earlier one was reported then)
    assert len(spikes) == 1 and spikes[0].detail["crossed_on"] == d[3].isoformat()


def test_approach_is_info_and_superseded_by_spike():
    d, v = _days([30, 62, 64])
    ev = detect_rate_spike(d, v, d[-1], **KW)
    assert [(e.event_type, e.severity) for e in ev] == [("rate_spike_approach", "INFO")]
    d, v = _days([30, 62, 77])
    types = [e.event_type for e in detect_rate_spike(d, v, d[-1], **KW)]
    assert types == ["rate_spike"]          # no approach alongside a spike


def test_cold_start_does_not_replay_old_crossings():
    d, v = _days([40, 80] + [70] * 30)
    assert detect_rate_spike(d, v, d[-1], **KW) == []


def test_frozen_numbers_equal_the_study_output():
    res = json.load(open(os.path.join(ROOT, "studies", "rate_spike", "results.json")))
    t = res["T1"]
    s = R.RATE_SPIKE_RECESSION
    assert (s["events"], s["hits"]) == (t["n"], t["k"])
    assert s["rate_pct"] == round(100 * t["rate"])
    assert s["base_pct"] == round(100 * t["base"])
    assert s["ratio"] == round(t["R"], 1)
    assert s["p_one_sided"] == round(t["p_shift_one_sided"], 2)
    since = [e for e in t["events"] if e["date"] >= "1990-04-01"]
    assert s["since_1990"]["events"] == len(since)
    assert s["since_1990"]["hits"] == sum(e["hit"] for e in since)
    assert s["ex_volcker_ratio"] == round(res["T1_ex_volcker"]["R"], 2)
    assert s["beyond_curve"] == res["T2"]["words"]
    assert res["gate_2x"]["pass"] is False    # the words below assume a FAIL


def test_words_state_the_record_and_never_claim_doubling():
    txt = R.spike_alert_template(23.0).format(d60=81, date="2026-10-05")
    assert "10 of 33" in txt and "none of the 17 since" in txt
    assert "23%" in txt                       # always quotes the curve model
    assert "not a reliable recession warning" in txt
    summary = " ".join(R._summary(5.5, 80, "SPIKE", "POS", R.RATE_MATRIX["SPIKE"]["POS"]))
    surfaces = {
        "alert": txt, "summary": summary, "label": R.spike_line_label(),
        "panel": open(os.path.join(ROOT, "frontend", "src", "components",
                                   "RateShockPanel.tsx")).read(),
        "glossary": open(os.path.join(ROOT, "frontend", "src", "lib", "glossary.ts")).read(),
    }
    for name, text in surfaces.items():
        assert not re.search(r"(roughly )?doubl(e|es|ed) (forward )?recession odds|"
                             r"recession odds double", text, re.I), name
        assert "44% vs 21%" not in text or name == "glossary_record", name
