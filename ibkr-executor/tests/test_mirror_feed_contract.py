"""ONE BRAIN, TWO BROKERS: the executor's feed against the parity monitor that reads it.

composer/scripts/mirror_parity.py compares the executor's books with Composer every day from
GET /mirror/feed. This gate runs a paper book through a session, takes the view the feed serves, and
(1) pins every field the monitor reads, (2) hands the view to the monitor's own code and checks it
reads four engines holding their targets. A rename on this side then fails here, not silently in a
daily check. Part 2 is skipped (never failed) where composer/ is not in the checkout.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

import test_mirror as tm

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "composer", "scripts")


def _session(tmp_path):
    r = tm.Rig(tmp_path)
    r.tick("15:54:30")
    assert r.m.state["last_session"] == tm.DAY
    return r, json.loads(json.dumps(r.m.view(history=30), default=str))


def test_feed_the_fields_the_parity_monitor_reads_are_all_there(tmp_path):
    r, view = _session(tmp_path)
    for key in ("mode", "halt", "run", "last_error", "check", "last_session", "waiting_on", "archived_state",
                "history", "last_run"):
        assert key in view, key
    assert view["mode"] == "paper" and view["last_session"] == tm.DAY and view["run"] is None
    row = view["last_run"]
    assert row == view["history"][-1]
    for key in ("session", "outcome", "sleeves", "orders", "prices", "notes", "problems"):
        assert key in row, key
    assert set(row["sleeves"]) == set(tm.ENGINES)
    for name, s in row["sleeves"].items():
        for key in ("action", "reason", "cash", "shares", "version"):
            assert key in s, (name, key)
        assert set(s["shares"]) <= set(row["prices"])                 # every holding is priced in the same row
    assert row["orders"]
    for o in row["orders"]:
        for key in ("symbol", "qty", "filled", "cost_bps", "side"):
            assert key in o, key


def test_feed_the_parity_monitors_own_code_reads_it(tmp_path):
    if not os.path.isdir(SCRIPTS):
        pytest.skip("composer/scripts is not in this checkout")
    sys.path.insert(0, SCRIPTS)
    try:
        import mirror_parity as mp
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the parity monitor is not importable here: {exc!r}")
    finally:
        sys.path.remove(SCRIPTS)
    r, view = _session(tmp_path)
    comp = {e: {"holdings": dict(t), "ret": None, "basis": None, "kind": "close", "taken_at": "x"} for e, t in tm.T1.items()}
    lines, alerts, led = mp.book_parity("dry", view, tm.DAY, comp, {})
    assert alerts == []
    assert {x["engine"]: x["parity"] for x in led} == {e: "same" for e in tm.ENGINES}
    assert "4 of 4 engines hold the same" in "\n".join(lines)
    assert mp.book_health("dry", view, tm.DAY, after_close=True) == []
    # the twin: Composer holds something else, and the monitor says so from this same view
    comp["HG"]["holdings"] = {"TQQQ": 1.0}
    _, alerts, _ = mp.book_parity("dry", view, tm.DAY, comp, {})
    assert len(alerts) == 1 and "MISMATCH — HG" in alerts[0]
    # ... and a halted book is relayed
    r.m.halt("operator")
    halted = json.loads(json.dumps(r.m.view(history=5), default=str))
    assert any("HALTED" in a for a in mp.book_health("dry", halted, tm.DAY, after_close=True))
