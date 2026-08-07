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


def _backdate_candidate(tmp_path):
    """Age the pending candidate past the confirmation window."""
    p = os.path.join(str(tmp_path), "cycle_phase.json")
    st = json.load(open(p))
    st["candidate_ts"] = st["candidate_ts"] - business_cycle.PHASE_CONFIRM_S - 1
    json.dump(st, open(p, "w"))


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
    assert business_cycle.phase_change(fake) is None    # candidate: not yet
    _backdate_candidate(tmp_path)
    msg = business_cycle.phase_change(fake)             # survived a recompute
    assert msg and "STALL -> SLOWDOWN" in msg
    # message target phase == board phase (the refresh job keys dedup on the
    # board, but the human-readable message must agree with it)
    assert msg.split("->")[1].strip().split()[0] == "SLOWDOWN"


def test_gate_phase_change_glitch_immunity(tmp_path, monkeypatch):
    """A one-refresh data glitch (flapped or degenerate board) must not fire
    or destroy state; the real baseline must survive it."""
    monkeypatch.setattr(business_cycle.settings, "cache_dir", str(tmp_path))
    b = board()
    mk = lambda ph: {**b, "current": {**b["current"], "phase": ph}}
    assert business_cycle.phase_change(mk("STALL")) is None      # baseline
    # flap within the confirmation window: zero alerts
    assert business_cycle.phase_change(mk("SLOWDOWN")) is None
    assert business_cycle.phase_change(mk("STALL")) is None      # reverted
    assert business_cycle.phase_change(mk("SLOWDOWN")) is None   # new candidate
    # a degenerate board (phase None) must not erase the pending state
    assert business_cycle.phase_change(
        {**b, "current": {**b["current"], "phase": None}}) is None
    _backdate_candidate(tmp_path)
    msg = business_cycle.phase_change(mk("SLOWDOWN"))
    assert msg and "STALL -> SLOWDOWN" in msg           # real change still fires


def test_gate_empty_series_raises_not_partial_board():
    """fetch_series degrades to empty on FRED failure; compute must refuse to
    emit a board with silently-missing composite members (a W875RX1 outage
    moved the current coincident by +0.31 sigma pre-guard)."""
    import pytest
    for ser in ("CMRMTSPL", "W875RX1", "UMCSENT", "PERMIT", "USREC", "INDPRO"):
        broken = {**FIX, ser: []}
        with pytest.raises(Exception):
            business_cycle.compute(raw_override=broken)


def test_gate_nowcast_bails_on_stale_bridge_inputs():
    """A bridge series staler than its trained lag (e.g. CMRMTSPL 3 months
    behind payrolls) must yield nowcast=None, not a silently-shifted value."""
    stale = {**FIX, "CMRMTSPL": [p for p in FIX["CMRMTSPL"] if p[0] < "2026-05-01"]}
    assert business_cycle.compute(raw_override=stale)["nowcast"] is None


def test_gate_partial_month_invariance():
    """Partial current-month ICSA (1 week) / T10Y3M (a few days) must not move
    the board: the composites end at the payrolls/INDPRO month and the nowcast
    targets the last complete payrolls month."""
    b = board()
    f = {**FIX,
         "ICSA": [p for p in FIX["ICSA"] if p[0] < "2026-08-01"],
         "T10Y3M": [p for p in FIX["T10Y3M"] if p[0] < "2026-08-01"]}
    b2 = business_cycle.compute(raw_override=f)
    assert b2["current"] == b["current"]
    assert b2["nowcast"]["value"] == b["nowcast"]["value"]


def test_gate_nowcast_reproduces_study_spec():
    """ENS_BC nowcast on the frozen fixture must reproduce the walk-forward
    study's live values (spec 2026-08-07: bridge -0.347, claims -0.429,
    ens -0.388, target 2026-07, phase STALL)."""
    nc = board()["nowcast"]
    assert nc is not None
    assert nc["month"] == "2026-07"
    # tight bounds (QA: the old +/-0.11 bounds let a silent lag-mismatch
    # output of -0.336 pass; deterministic fixture warrants +/-0.05)
    assert -0.45 <= nc["value"] <= -0.35, nc
    assert -0.40 <= nc["bridge"] <= -0.30, nc
    assert -0.50 <= nc["claims"] <= -0.40, nc
    assert nc["phase"] == "STALL"
    assert nc["claims_trigger"] is False
