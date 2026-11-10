"""ONE BRAIN, TWO BROKERS: the executor against the brain's OWN payloads (contract schema 2).

The other mirror gates feed the manager hand-built payloads (tests/test_mirror.py: payload()), which
can drift from what the brain really publishes without any of them noticing. This gate builds a
PINNED payload with the brain's own code (composer/scripts/mirror_brain.py) on the brain's own
recorded data (its tests' fixture: 2026-11-06, decision instant 15:54:00 ET), takes the brain's own
/mirror/session answer, and runs both through a paper book: the clock is parsed, every 'Executor
check' of the contract passes, and the session is traded on the brain's targets.

Skipped (never failed) where the composer side is not importable - the executor's image does not
ship it - or its test helper has changed shape; a contract mismatch FAILS.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

import test_mirror as tm
from app import mirror as mm
from app import mirror_core as mc

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "composer", "scripts")


@pytest.fixture(scope="module")
def brain():
    if not os.path.isdir(SCRIPTS):
        pytest.skip("composer/scripts is not in this checkout")
    added = [p for p in (SCRIPTS, os.path.join(SCRIPTS, "tests")) if p not in sys.path]
    sys.path[:0] = added
    try:
        import mirror_brain as mb
        import test_mirror_pinned as tp
        tp.T1Pinned.setUpClass()
        payload, instant = tp.T1Pinned.p, tp.T
    except Exception as exc:  # noqa: BLE001  the brain side's helper is not what this gate was written against
        pytest.skip(f"the brain's fixture build is not available here: {exc!r}")
    finally:
        for p in added:
            if p in sys.path:
                sys.path.remove(p)
    return mb, json.loads(json.dumps(payload)), instant


def test_contract_the_brains_own_pinned_payload_passes_every_executor_check_and_trades(tmp_path, brain):
    mb, payload, instant = brain
    r = tm.Rig(tmp_path)
    served = []

    class RealBrain:
        def session(self):
            return mb.session_info(r.clock.now), "ok"

        def intents(self, after):
            served.append(after)
            return json.loads(json.dumps(payload)), "ok"
    r.brain = RealBrain()
    r.boot()
    r.clock.now = instant + datetime.timedelta(seconds=10)
    r.m.tick(None)
    assert served == [] and r.m.next_wait() == pytest.approx(15.2)        # decide_utc AS GIVEN, + the 25 s offset
    r.clock.now = instant + datetime.timedelta(seconds=25)
    r.m.tick(None)
    assert served == [mm._iso(instant)] == [payload["asof_utc"]]          # asked for exactly the instant the brain pins
    assert r.m.brain_status["session"]["ok"] and r.m.brain_status["intents"] == {
        "ok": True, "reason": "ok", "utc": mm._iso(r.clock.now)}
    row = r.m.state["last_run"]
    assert row["session"] == payload["session"] and row["outcome"] == "traded"
    assert row["decision_bar"] == payload["decision_bar"] and row["decision_bar"]["complete"] is True
    assert row["sync"] == payload["sync"] and row["built_utc"] == payload["built_utc"]
    for name, eng in payload["engines"].items():                          # every engine the brain says ok is on its target
        assert eng["status"] == "ok" and row["sleeves"][name]["action"] == "trade"
        s = r.m.book.sleeves[name]
        assert (s.rule, s.corridor) == (eng["rule"], eng["corridor"])
        held = mc.invested_weights(s, payload["prices"])
        assert set(held) == {t for t, w in eng["target"].items() if w > 0}
        for t, w in eng["target"].items():
            assert held.get(t, 0.0) == pytest.approx(w, abs=0.01), (name, t)
    assert set(r.m.book.positions()) <= set(payload["prices"])           # everything it holds is priced by the brain
    # the brain's dividend and split rows are in the shape the book reads: every one in the window is
    # seen, and none creates an entitlement for a book that held nothing before its ex-date
    assert all(mc.clean_dividend(d) is not None for d in payload["dividends"])
    seen = {mc.dividend_key(d["ticker"], d["ex_date"]) for d in payload["dividends"] if d["ex_date"] <= payload["session"]}
    assert set(r.m.state["div_seen"]) == seen and r.m.state["dividends"] == []
    assert isinstance(payload["price_times"], dict) and row["price_times"]
    tm.sound(r)


def test_contract_the_same_payload_in_a_later_second_of_the_window_still_trades(tmp_path, brain):
    """the payload is immutable: built at T + 25 s, served again to a process that only starts at T + 3 min"""
    mb, payload, instant = brain
    r = tm.Rig(tmp_path)

    class RealBrain:
        def session(self):
            return mb.session_info(r.clock.now), "ok"

        def intents(self, after):
            return json.loads(json.dumps(payload)), "ok"
    r.brain = RealBrain()
    r.boot()
    r.clock.now = instant + datetime.timedelta(seconds=180)
    r.m.tick(None)
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.state["last_run"]["built_utc"] == payload["built_utc"]
