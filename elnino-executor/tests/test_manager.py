"""Ladder-manager gates: trigger discipline, kill rules, sequencing,
house-money accounting. Pure state-machine tests — no broker, no network."""
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
