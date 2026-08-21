"""Ladder-manager gates: trigger discipline, kill rules, sequencing,
house-money accounting. Pure state-machine tests — no broker, no network."""
import json
import os
import time

import pytest

from app.manager import LadderManager, LADDER


class Cfg:
    leg_budget_usd = 10_000.0
    compound = False
    max_concurrent_legs = 2


def mk(tmp_path):
    return LadderManager(Cfg(), str(tmp_path / "ladder.json"))


def test_gate_no_entry_before_window_or_below_strength(tmp_path):
    m = mk(tmp_path)
    assert m.step("2026-08-07", 2.3, {}) == []          # window not open
    assert m.step("2026-11-05", 1.7, {}) == []          # open, but nino < 2.0
    out = m.step("2026-11-05", 2.3, {})
    assert len(out) == 1 and out[0]["action"] == "OPEN" and out[0]["leg"] == "NG"
    assert out[0]["budget"] == 10_000.0


def test_gate_sequential_ladder_and_concurrency(tmp_path):
    m = mk(tmp_path)
    out = m.step("2026-12-05", 2.4, {})
    # NG and SB windows both open; SLV requires SB resolved -> only 2 intents
    legs = [o["leg"] for o in out if o["action"] == "OPEN"]
    assert legs == ["NG", "SB"]
    m.on_opened("NG", 9_800, "ref1", "2026-12-05")
    m.on_opened("SB", 4_100, "ref2", "2026-12-05")
    # max_concurrent 2 -> SLV blocked even after its window opens
    out = m.step("2026-12-10", 2.4, {"NG": 9_900, "SB": 4_000})
    assert not [o for o in out if o["action"] == "OPEN"]


def test_gate_event_collapse_closes_all_and_halts(tmp_path):
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "r", "2026-11-05")
    out = m.step("2026-12-01", 0.8, {"NG": 7_000})
    assert [o["action"] for o in out] == ["CLOSE"]
    assert "COLLAPSE" in out[0]["reason"]
    assert m.state.halted == "EVENT_COLLAPSE"
    assert m.step("2026-12-02", 2.5, {}) == []          # halted stays halted


def test_gate_target_and_expiry_exits(tmp_path):
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "r", "2026-11-05")
    # target 1.5x gain -> close at >= 25k value
    out = m.step("2026-12-20", 2.4, {"NG": 26_000})
    close = [o for o in out if o["action"] == "CLOSE" and o["leg"] == "NG"]
    assert close and "target" in close[0]["reason"]
    m2 = mk(tmp_path)
    m2.state.legs["NG"].status = "OPEN"
    m2.state.legs["NG"].entry_premium = 10_000
    out = m2.step("2027-02-21", 2.4, {"NG": 12_000})
    assert any("expiry" in o["reason"] for o in out)


def test_gate_salvage_only_when_thesis_weakens(tmp_path):
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "r", "2026-11-05")
    # deep drawdown but event still strong -> HOLD NG (premium is the stop);
    # SB may legitimately arm at its window, so filter to CLOSE intents
    out = m.step("2026-12-20", 2.4, {"NG": 3_000})
    assert not [o for o in out if o["action"] == "CLOSE"]
    # same mark with event weakening (below ARM, above KILL) -> salvage NG
    out = m.step("2026-12-21", 1.5, {"NG": 3_000})
    closes = [o for o in out if o["action"] == "CLOSE"]
    assert closes and "salvage" in closes[0]["reason"]


def test_gate_house_money_accounting(tmp_path):
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "r", "2026-11-05")
    m.on_closed("NG", 28_000, "target hit", "2027-01-15")
    assert m.state.banked == pytest.approx(18_000)
    assert m.leg_budget() == 10_000                      # compound off: base only
    m.cfg.compound = True
    assert m.leg_budget() == 28_000                      # banked rolls in

    # persistence across restart
    m2 = LadderManager(m.cfg, m.state_path)
    assert m2.state.banked == pytest.approx(18_000)
    assert m2.state.legs["NG"].status == "CLOSED"


# --- x12 (counter-review): persistence safety on the LIVE paper ladder --------
# LadderManager.save() was a plain json.dump(..., open(path,"w")) — no temp
# file, no fsync — and it IS genuinely raced in production (/kill and /resume
# mutate from API threads while _loop() saves on the loop thread). A
# truncated file then fell through _load's bare except to a FRESH
# LadderState(): open legs and `halted` silently forgotten.


def test_gate_x12_ladder_save_is_atomic_under_a_mid_write_crash(tmp_path):
    import app.manager as manager_mod

    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "ng-ref", "2026-11-05")
    m.state.halted = "KILL"
    m.save()
    real_dump = manager_mod.json.dump

    def bad_dump(obj, fh, **kw):
        fh.write('{"partial')
        raise IOError("disk full mid-write")

    manager_mod.json.dump = bad_dump
    try:
        m.state.banked = 999.0
        with pytest.raises(IOError):
            m.save()
    finally:
        manager_mod.json.dump = real_dump
    m2 = LadderManager(m.cfg, m.state_path)         # reload: LAST GOOD book
    assert m2.state.legs["NG"].status == "OPEN"     # open leg not forgotten
    assert m2.state.legs["NG"].order_ref == "ng-ref"
    assert m2.state.halted == "KILL"                # and still halted
    assert m2.state.banked == 0.0                   # not the failed write
    assert m2.archived_state is None                # nothing was corrupt
    # no scratch files left behind next to the state file
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []


def test_gate_x12_ladder_concurrent_saves_never_publish_a_torn_file(tmp_path):
    import threading

    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "ng-ref", "2026-11-05")
    m.state.events = [{"ts": 1, "level": "INFO", "msg": f"e{i} " + "x" * 120}
                      for i in range(300)]
    m.save()
    errors: list[BaseException] = []
    corrupt: list[str] = []
    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            try:
                m.save()
            except BaseException as exc:            # noqa: BLE001
                errors.append(exc)
                return

    def reader():
        while not stop.is_set():
            try:
                json.load(open(m.state_path))
            except FileNotFoundError:
                corrupt.append("missing")
            except ValueError:
                corrupt.append("truncated")

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    threads.append(threading.Thread(target=reader))
    for t in threads:
        t.start()
    time.sleep(1.0)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert corrupt == []
    assert LadderManager(m.cfg, m.state_path).state.legs["NG"].status == "OPEN"


def test_gate_x12_unreadable_ladder_state_is_preserved_and_loud(tmp_path):
    """A corrupt file must never degrade to a fresh, un-halted ladder in
    silence: the file is preserved for forensics and the service alerts."""
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "ng-ref", "2026-11-05")
    m.state.halted = "KILL"
    m.save()
    with open(m.state_path, "w") as fh:
        fh.write('{"legs": {"NG": {"status": "OPE')     # truncated externally
    m2 = LadderManager(m.cfg, m.state_path)
    assert m2.archived_state and "unreadable" in m2.archived_state
    assert [f for f in os.listdir(tmp_path) if ".corrupt-" in f]
    assert m2.state.legs["NG"].status == "WAITING"      # fresh, but LOUD
    m2.save()                                           # never overwrites it
    assert [f for f in os.listdir(tmp_path) if ".corrupt-" in f]


def test_gate_x12_kill_and_resume_serialize_behind_the_ladder_lock(
        tmp_path, monkeypatch):
    """/kill and /resume mutate legs/halted on API threads with no lock at
    all while the loop steps and saves. They must serialize behind
    MGR_LOCK, exactly as the blend's /kill and /resume do behind
    BLEND_LOCK."""
    import threading

    from fastapi.testclient import TestClient

    from app import service
    from app.config import settings
    from app.service import app

    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", False)
    monkeypatch.setattr(service, "send", lambda *_a, **_k: None)
    with TestClient(app) as c:
        for _ in range(200):
            if service.MGR is not None:
                break
            time.sleep(0.05)
        assert service.MGR is not None
        for endpoint in ("/kill", "/resume"):
            done = threading.Event()
            with service.MGR_LOCK:                  # a cycle is "in flight"
                t = threading.Thread(
                    target=lambda: (c.get(endpoint, params={"token": "sekrit"}),
                                    done.set()))
                t.start()
                assert not done.wait(0.4)           # blocked on the lock
            assert done.wait(5)                     # released -> completes
            t.join(timeout=5)


def test_gate_y2_leg_row_schema_drift_preserves_and_halts(tmp_path):
    """y2: a leg-row schema drift (a deploy ROLLBACK reading rows a newer
    build wrote) reset every leg to WAITING/order_ref=None, left the file in
    place for the loop's next save() to destroy, and left the ladder
    UNHALTED — so step() re-OPENed a spread that is still live at the venue,
    with the real one orphaned and never closed. The drifted book must be
    preserved exactly as the outer corrupt branch does, the live leg's
    handle kept, and the ladder HALTED before step() can act."""
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "live-spread-ref", "2026-11-05")
    m.state.banked = 999.0
    m.save()
    raw = json.load(open(m.state_path))
    raw["legs"]["NG"]["future_field_from_a_newer_deploy"] = 1
    with open(m.state_path, "w") as fh:
        json.dump(raw, fh)

    m2 = LadderManager(m.cfg, m.state_path)
    # the leg is inside its window with the event at strength: the old
    # branch re-OPENed it here, duplicating a live spread
    assert m2.step("2026-11-20", 2.4, {"NG": 9_000}) == []
    assert m2.state.halted == "SCHEMA_DRIFT"        # step() cannot act
    assert m2.state.legs["NG"].status == "OPEN"     # the live leg is not lost
    assert m2.state.legs["NG"].order_ref == "live-spread-ref"
    assert [f for f in os.listdir(tmp_path) if ".corrupt-" in f]   # evidence
    assert m2.state.banked == 999.0
    assert m2.archived_state and "HALTED" in m2.archived_state
    m2.save()                                       # never overwrites it
    assert [f for f in os.listdir(tmp_path) if ".corrupt-" in f]
    assert json.load(open(m2.state_path))["halted"] == "SCHEMA_DRIFT"


def test_gate_y2_schema_drift_keeps_an_existing_halt_reason(tmp_path):
    """`banked`/`halted` semantics stay intact: a book already halted for a
    REAL reason keeps that reason (SCHEMA_DRIFT never overwrites it), and
    the ladder stays halted either way."""
    m = mk(tmp_path)
    m.on_opened("NG", 10_000, "live-spread-ref", "2026-11-05")
    m.state.halted = "EVENT_COLLAPSE"
    m.save()
    raw = json.load(open(m.state_path))
    raw["legs"]["SB"]["unknown_key"] = "x"
    with open(m.state_path, "w") as fh:
        json.dump(raw, fh)
    m2 = LadderManager(m.cfg, m.state_path)
    assert m2.step("2026-11-20", 2.4, {"NG": 9_000}) == []
    assert m2.state.legs["NG"].order_ref == "live-spread-ref"
    assert m2.state.halted == "EVENT_COLLAPSE"
    assert m2.archived_state and "EVENT_COLLAPSE" in m2.archived_state
