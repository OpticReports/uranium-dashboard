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


def test_exposure_map_sums_mass_by_status():
    board = build_pin_board({})
    exp = board["exposure"]
    # all channels STALE on an empty bundle -> no colored mass, but the
    # monitored total and the unbounded exclusions are still reported
    assert exp["red_trillions"] == exp["yellow_trillions"] == exp["green_trillions"] == 0
    # sums count the Treasury market ONCE: demand_strike (same $28T market as
    # the fiscal pin) shows a bar but is excluded from the dollar totals
    summed = [c["mass_trillions"] for c in board["channels"]
              if c["mass_trillions"] is not None and c["channel_id"] != "demand_strike"]
    assert exp["monitored_trillions"] == round(sum(summed), 1)
    assert len(exp["unsized"]) == 2  # policy shock + uncertainty: unbounded
    for c in board["channels"]:
        assert "leverage" in c


def test_accident_gauge_arming_states():
    import datetime
    # dates must END TODAY: the gauge treats a stale curve tape as unknown
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=399 - i) for i in range(400)]

    def curve(spread):
        return {"3mo": (days, [4.0] * 400), "10y": (days, [4.0 + spread] * 400)}

    # steep curve, no fast channel reporting -> curve known false, fast
    # UNKNOWN (None) -> GREEN with the unknown disclosed
    g = build_pin_board(curve(1.0))["accident_gauge"]
    assert g["status"] == "GREEN" and g["fast_red"] is None and g["curve_flat"] is False
    assert "fast channels" in g["unknown"]
    # flat curve alone -> YELLOW (one condition)
    g = build_pin_board(curve(0.1))["accident_gauge"]
    assert g["status"] == "YELLOW" and g["curve_flat"]
    # fast-channel red alone (HY OAS gap) on a steep curve -> YELLOW (armed)
    hy = [3.0] * 380 + [3.0 + 0.10 * i for i in range(20)]  # +190bps/20 obs > 150 RED
    b = curve(1.0); b["hy_oas"] = (days, hy)
    g = build_pin_board(b)["accident_gauge"]
    assert g["fast_red"] is True and g["status"] == "YELLOW" and g["unknown"] == []
    # both -> RED (triggered)
    b = curve(0.1); b["hy_oas"] = (days, hy)
    g = build_pin_board(b)["accident_gauge"]
    assert g["status"] == "RED" and g["fast_red"] and g["curve_flat"]
    # empty bundle -> STALE (both conditions unknowable), never a false alarm
    g = build_pin_board({})["accident_gauge"]
    assert g["status"] == "STALE" and g["fast_red"] is None and g["curve_flat"] is None


def test_accident_gauge_stale_curve_tape_is_unknown_not_green():
    import datetime
    # curve data that ENDS 18 months ago: an old min must not masquerade as a
    # current "6m low" — the curve condition reads UNKNOWN (None)
    end = datetime.date.today() - datetime.timedelta(days=540)
    days = [end - datetime.timedelta(days=399 - i) for i in range(400)]
    g = build_pin_board({"3mo": (days, [4.0] * 400),
                         "10y": (days, [3.0] * 400)})["accident_gauge"]  # inverted!
    assert g["curve_flat"] is None
    assert g["spread_3m10y_min_6m"] is None
    assert "curve" in g["unknown"]
    assert g["status"] == "STALE"  # nothing else knowable either


def test_exposure_counts_red_mass():
    # +100% oil yoy -> oil channel RED -> its $20T consumption base counts red
    import datetime
    days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(400)]
    vals = [50.0] * 337 + [100.0] * 63
    board = build_pin_board({"oil": (days, vals)})
    oil = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    assert oil["status"] == "RED"
    assert board["exposure"]["red_trillions"] == 20.0


def test_scores_flow_from_synthetic_data():
    # oil +60% y/y -> RED with score in (80, 100)
    dates = [None] * 260
    oil = [100.0] * 130 + [160.0] * 130
    board = build_pin_board({"oil": (dates, oil)})
    ch = next(c for c in board["channels"] if c["channel_id"] == "oil_shock")
    assert ch["status"] == "RED"
    assert 80.0 <= ch["score"] <= 100.0
    assert board["pressure"] is not None
