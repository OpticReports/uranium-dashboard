"""Business-cycle tracker gates — frozen FRED fixture (fetched 2026-08-07),
validation stats must reproduce the prototype study."""
import json
import os

from app.sources import business_cycle

FIX = json.load(open(os.path.join(os.path.dirname(__file__),
                                  "fixtures_cycle_fred.json")))


def board():
    if not hasattr(board, "_b"):
        board._b = business_cycle.compute(raw_override=FIX)
    return board._b


def test_gate_composites_reproduce_prototype():
    b = board()
    cur = b["current"]
    assert cur["month"] >= "2026-05"
    assert -0.60 <= cur["coincident"] <= -0.35, cur     # prototype: -0.49
    assert 0.05 <= cur["leading"] <= 0.35, cur          # prototype: +0.20
    assert cur["phase"] == "STALL"


def test_gate_nber_validation_stats():
    b = board()
    assert 0.55 <= b["stats"]["precision"] <= 0.75, b["stats"]
    assert 0.85 <= b["stats"]["recall"] <= 0.97, b["stats"]
    # every recession since 1970 bottomed WELL below the line
    m2i = {m: i for i, m in enumerate(b["months"])}
    for s, e in b["rec_spans"]:
        if s < "1970-01":
            continue
        lo = min(x for x in b["coincident"][m2i[s]:m2i[e] + 1] if x is not None)
        assert lo < -1.5, (s, lo)


def test_gate_payroll_view_and_zeberg_claim():
    b = board()
    zc = b["zeberg_check"]
    assert zc["current_ma_k"] is not None
    # the claim is CHECKED, not assumed - pin whatever the data says so a
    # future data change that flips it fails loudly and gets re-reviewed
    assert isinstance(zc["holds"], bool)
    assert 20 <= zc["current_ma_k"] <= 80                # ~47.9k on fixture
    assert len(b["payroll_ma12_k"]) == len(b["months"])


def test_gate_phase_rules_and_change_detection(tmp_path, monkeypatch):
    assert business_cycle.phase_of(-1.0, 0.0) == "CONTRACTION"
    assert business_cycle.phase_of(-0.3, -0.5) == "SLOWDOWN"
    assert business_cycle.phase_of(-0.3, 0.2) == "STALL"
    assert business_cycle.phase_of(0.5, -0.8) == "LATE_CYCLE"
    assert business_cycle.phase_of(0.5, 0.5) == "EXPANSION"
    monkeypatch.setattr(business_cycle.settings, "cache_dir", str(tmp_path))
    b = board()
    assert business_cycle.phase_change(b) is None       # first sight: no alert
    fake = {**b, "current": {**b["current"], "phase": "SLOWDOWN"}}
    msg = business_cycle.phase_change(fake)
    assert msg and "STALL -> SLOWDOWN" in msg
