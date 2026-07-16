"""Severity scoring: anchors -> 0-100, colors derived from the same bands."""
from app.metrics.pins import ANCHORS, _pscore, _status_from_score, build_pin_board


def test_score_hits_bands_at_thresholds():
    # yellow anchor -> exactly 50 (YELLOW), red anchor -> exactly 80 (RED)
    assert _pscore(25, 0, 25, 50, 100) == 50.0
    assert _pscore(50, 0, 25, 50, 100) == 80.0
    assert _status_from_score(49.9) == "GREEN"
    assert _status_from_score(50.0) == "YELLOW"
    assert _status_from_score(80.0) == "RED"


def test_score_monotone_and_clamped():
    vals = [_pscore(v, 0, 25, 50, 100) for v in (-10, 0, 10, 25, 40, 50, 75, 100, 500)]
    assert vals == sorted(vals)
    assert vals[0] == 0.0 and vals[-1] == 100.0


def test_lower_is_worse_orientation():
    # bid-to-cover: 2.2 (red anchor) must score 80; 2.6 benign -> 0
    b, y, r, e, hi, cap = ANCHORS["Coupon bid-to-cover, last 4 auctions"]
    assert _pscore(2.6, b, y, r, e, hi, cap) == 0.0
    assert _pscore(2.2, b, y, r, e, hi, cap) == 80.0


def test_cushion_legs_cap_at_yellow():
    b, y, r, e, hi, cap = ANCHORS["RRP buffer"]
    assert _pscore(0, b, y, r, e, hi, cap) == 79.0        # worst case still YELLOW
    assert _status_from_score(79.0) == "YELLOW"


def test_board_has_new_channels_and_pressure_fields():
    board = build_pin_board({})
    ids = {c["channel_id"] for c in board["channels"]}
    assert {"demand_strike", "concentration", "vol_supply"} <= ids
    assert "pressure" in board and "hottest" in board
    for c in board["channels"]:
        assert "score" in c


def test_scores_flow_from_synthetic_data():
    # oil +60% y/y -> RED with score in (80, 100)
    dates = [None] * 260
    oil = [100.0] * 130 + [160.0] * 130
    board = build_pin_board({"oil": (dates, oil)})
    ch = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    assert ch["status"] == "RED"
    assert 80.0 <= ch["score"] <= 100.0
    assert board["pressure"] is not None
