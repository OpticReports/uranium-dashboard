"""Telegram wording reads like a note, not a log line (Casey, 2026-09-13)."""
from datetime import date

from app import alerts


def test_header_is_plain_english():
    t = alerts.format_event("squeeze_condition_flip", "WARN", "x")
    assert t.startswith("🟡 Canary — Squeeze Radar — a condition changed (heads-up)\nx")
    assert "[WARN]" not in t and "squeeze_condition_flip" not in t
    assert alerts.format_event("metric_red:vol.move", "RED", "x").startswith(
        "🔴 Canary — A metric turned red (alert)")


def test_squeeze_flip_reads_plainly():
    c = {"id": "F1", "label": "Futures short extreme", "state": "NOT_MET",
         "detail": "13% pctile of trailing 10y"}
    t = alerts.squeeze_flip_text(c, "MET", 1.0, 0.5)
    assert t.splitlines() == [
        "Fuel F1 (Futures short extreme) switched OFF — was ON.",
        "It watches hedge funds' short in bond futures.",
        "Reading now: 13% pctile of trailing 10y.",
        "Scorecard: fuel 1 of 4 · triggers 0.5 of 5. Nothing has fired.",
    ]
    t2 = alerts.squeeze_flip_text({"id": "T2", "label": "Labor break", "state": "MET"}, "NOT_MET", 1.0, 1.5)
    assert "Trigger T2 (Labor break) switched ON — was OFF." in t2
    assert "A trigger just went live" in t2


def test_squeeze_prebrief_reads_plainly():
    t = alerts.squeeze_prebrief_text("FOMC decision", date(2026, 9, 16), 3, False, 1.0, 0.5)
    assert t.splitlines() == [
        "FOMC decision is in 3 days (Wed Sep 16).",
        "Triggers fire on scheduled dates like this one — worth watching.",
        "Scorecard going in: fuel 1 of 4 · triggers 0.5 of 5.",
    ]
    assert "is tomorrow (around" in alerts.squeeze_prebrief_text("CPI release", date(2026, 10, 14), 1, True, 2, 1)
