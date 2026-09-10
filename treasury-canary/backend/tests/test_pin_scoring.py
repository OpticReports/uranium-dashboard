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


# --- anchor-bug regression gates (2026-09-10) ---------------------------------
# Two scoring bugs found during the pin-band calibration study. Both distorted the
# hindcast by pinning a channel at the score ceiling for structural reasons rather
# than stress. These gates are merge-blocking: they encode the fix, not the symptom.

def test_reserves_pct_change_gated_on_base():
    """A 26-week % change on a pre-QE reserve base is noise, not a drain.

    WRESBAL ran $3-24B pre-QE (stdev of the 26w change: 104%, hitting the -15%
    RED anchor 26.1% of the time and the -25% extreme 30 times) versus $603B+
    post-QE (stdev 21%, never once reaching the extreme).
    """
    from app.metrics.pins import RESERVES_MIN_BASE_M, _pct_change

    small = [20_000.0] * 26 + [14_000.0]        # $20B -> $14B: -30%, pure noise
    assert _pct_change(small, 26) == -30.0                      # ungated: spurious
    assert _pct_change(small, 26, min_base=RESERVES_MIN_BASE_M) is None

    ample = [3_000_000.0] * 26 + [2_700_000.0]  # $3T -> $2.7T: a real -10% drain
    assert _pct_change(ample, 26, min_base=RESERVES_MIN_BASE_M) == -10.0


def test_reserves_gate_separates_the_two_regimes():
    """The gate must sit clear of BOTH regimes, not bisect either one."""
    from app.metrics.pins import RESERVES_MIN_BASE_M

    assert 24_000.0 < RESERVES_MIN_BASE_M < 603_000.0   # pre-QE peak / post-QE trough


def test_positioning_percentile_is_a_capped_crowding_gauge():
    """Crowding alone must not take basis_trade RED, and must not pin at 100.

    The channel's own certainty note says the unwind trigger "arrives via the
    other channels". Uncapped, a new expanding-window high scored exactly 100 by
    construction, and leveraged-fund net short trends secularly.
    """
    b, y, r, e, hi, cap = ANCHORS["Positioning percentile (vs 2010+)"]
    assert cap == 79.0
    assert _pscore(100.0, b, y, r, e, hi, cap) == 79.0      # an all-time high: still YELLOW
    assert _status_from_score(_pscore(100.0, b, y, r, e, hi, cap)) == "YELLOW"


def test_gauge_and_cushion_legs_cap_at_yellow():
    """Regression guard: gauges/cushions measure how loaded the spring is; triggers fire it."""
    gauges = [
        "Positioning percentile (vs 2010+)",
        "SPY/RSP ratio percentile (vs 2010+)",
        "Vol-risk premium percentile (VIX − realized)",
        "RRP buffer",
        "10y JGB yield, 12-month change",
    ]
    for label in gauges:
        assert ANCHORS[label][5] == 79.0, f"{label} must cap at YELLOW"


def test_basis_trade_still_reaches_red_via_its_level_leg():
    """The cap must not neuter the channel — the level leg is uncapped."""
    b, y, r, e, hi, cap = ANCHORS["Leveraged-fund net short, UST futures"]
    assert cap == 100.0
    assert _pscore(5.5, b, y, r, e, hi, cap) == 80.0        # red anchor still red
    assert _pscore(8.0, b, y, r, e, hi, cap) == 100.0       # extreme still reachable


def test_hindcast_and_live_board_share_the_reserves_gate():
    """If these drift apart the history stops measuring what the pill shows."""
    from app.metrics import pin_history
    from app.metrics.pins import RESERVES_MIN_BASE_M
    import datetime

    assert pin_history.RESERVES_MIN_BASE_M is RESERVES_MIN_BASE_M
    days = [datetime.date(2003, 1, 1) + datetime.timedelta(weeks=i) for i in range(30)]
    small = [20_000.0] * 26 + [14_000.0] * 4
    d, v = pin_history._roll_pct_change(days, small, 26, min_base=RESERVES_MIN_BASE_M)
    assert d == [] and v == []


def test_reserves_gate_is_wired_into_the_live_board():
    """INTEGRATION gate: asserting the parameter exists is not asserting it is used.

    Deleting `min_base=` at the pins.py call site must fail HERE, not pass.
    """
    import datetime
    weeks = [datetime.date(2003, 1, 1) + datetime.timedelta(weeks=i) for i in range(30)]
    pre_qe = [20_000.0] * 26 + [14_000.0] * 4      # $20B -> $14B, -30% of noise
    board = build_pin_board({"reserves": (weeks, pre_qe)})
    plumb = next(c for c in board["channels"] if c["channel_id"] == "plumbing")
    res = next(p for p in plumb["parts"] if p["label"].startswith("Reserves"))
    assert res["value"] is None and res["status"] == "STALE"
    assert plumb["status"] == "STALE"          # not GREEN — we cannot see, we do not guess
    assert plumb["score"] is None

    ample = [3_000_000.0] * 26 + [2_550_000.0] * 4  # $3T -> $2.55T, a real -15% drain
    board = build_pin_board({"reserves": (weeks, ample)})
    plumb = next(c for c in board["channels"] if c["channel_id"] == "plumbing")
    res = next(p for p in plumb["parts"] if p["label"].startswith("Reserves"))
    assert res["value"] == -15.0 and res["status"] == "RED"


def test_reserves_gate_is_wired_into_the_hindcast():
    """INTEGRATION gate for the pin_history call site (same mutation test)."""
    import datetime
    from app.metrics.pin_history import _parts_for_channel

    weeks = [datetime.date(2003, 1, 1) + datetime.timedelta(weeks=i) for i in range(30)]
    parts = dict(_parts_for_channel("plumbing", {"reserves": (weeks, [20_000.0] * 26 + [14_000.0] * 4)}))
    assert parts["Reserves, 26-week change"] == ([], [])

    parts = dict(_parts_for_channel("plumbing", {"reserves": (weeks, [3_000_000.0] * 26 + [2_550_000.0] * 4)}))
    d, v = parts["Reserves, 26-week change"]
    assert len(d) == 4 and all(abs(x - -15.0) < 1e-9 for x in v)


def test_gate_does_not_silence_a_drain_through_the_floor():
    """A monitor must never go quiet AFTER the worst outcome.

    Gating on the base alone would mute a catastrophic drain that takes the level
    below the gate. Gate on both ends: only when BOTH are small is it pre-QE noise.
    """
    from app.metrics.pins import RESERVES_MIN_BASE_M, _pct_change

    collapse = [3_000_000.0] * 26 + [50_000.0]   # $3T -> $50B: the end of the world
    assert _pct_change(collapse, 26, min_base=RESERVES_MIN_BASE_M) == -98.3

    rebuild = [50_000.0] * 26 + [3_000_000.0]    # small -> ample: still reported
    assert _pct_change(rebuild, 26, min_base=RESERVES_MIN_BASE_M) is not None

    noise = [20_000.0] * 26 + [14_000.0]         # both ends small: the actual bug
    assert _pct_change(noise, 26, min_base=RESERVES_MIN_BASE_M) is None


def test_stale_fast_channel_never_reads_as_a_silent_all_clear():
    """fast_red=False while a FAST_HIGH_MASS channel is dark is a false all-clear."""
    import datetime
    days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(60)]
    # credit_event readable and calm; plumbing dark. Condition 1 must be UNKNOWN.
    board = build_pin_board({"hy_oas": (days, [300.0] * 60)})
    g = board["accident_gauge"]
    assert g["fast_red"] is None, "a dark fast channel must not report 'condition false'"
    assert "fast channels" in g["unknown"]
    assert g["fast_stale_channels"], "the dark channels must be named, not just counted"
    assert g["status"] != "GREEN"



def test_percentile_never_reaches_the_ceiling_at_REALISTIC_sample_sizes():
    """The end-to-end gate. rank_pct stopping at (n-0.5)/n is not enough.

    round(99.9933, 1) is 100.0, so _percentile handed back the exact ceiling for
    every n >= 1000 -- which is every percentile leg on the board except CFTC
    (CCC ~7,500; dispersion ~7,500; EPU 15,227; SPY/RSP ~3,900; VRP ~2,500).
    An earlier version of this gate used n=500, one step below where the bug
    appears, so it passed while the board was broken.
    """
    from app.metrics.pins import _percentile

    for n in (500, 1000, 4001, 7500, 15227, 20000):
        rising = list(range(n))
        high = _percentile(rising, rising[-1])
        low = _percentile(rising, rising[0])
        assert high < 100.0, f"all-time high hit the ceiling at n={n}"
        assert low > 0.0, f"all-time low hit the floor at n={n}"
        # and the SCORE must not manufacture the extreme by rounding either
        assert _pscore(high, 50, 85, 95, 100) < 100.0, f"score hit 100 at n={n}"
        assert _pscore(high, 50, 90, 97.5, 100) < 100.0, f"EPU-anchored score hit 100 at n={n}"


def test_rounding_never_manufactures_the_extreme_but_real_extremes_still_reach_it():
    """The guard must not cost a genuine documented extreme its 100."""
    # at or beyond the extreme anchor -> still exactly 100
    assert _pscore(8.0, 2, 4, 5.5, 8) == 100.0          # net short at the extreme
    assert _pscore(500, 0, 25, 50, 100) == 100.0        # WTI far beyond it
    assert _pscore(-10, 10, 5, 0, -10, False, 100) == 100.0   # lower-is-worse extreme
    assert _pscore(-36.1, 10, 5, 0, -10, False, 100) == 100.0  # beyond it
    # just short of the extreme -> must NOT round up into it
    assert _pscore(7.999, 2, 4, 5.5, 8) < 100.0
    # the other anchors are untouched
    assert _pscore(5.5, 2, 4, 5.5, 8) == 80.0
    assert _pscore(4.0, 2, 4, 5.5, 8) == 50.0


def test_ccc_percentile_label_does_not_claim_history_it_does_not_have():
    """FRED's ICE BofA licence serves a rolling ~3-year window, not 1996+.

    The old label "(vs 1996+)" was false: the live board's 99.2 CCC percentile
    and 99.7 dispersion percentile reproduce EXACTLY off 787 daily observations
    (2023-09..2026-09). Today's 10.64% CCC OAS is nowhere near the 99th
    percentile of true 1996+ history, which includes ~40% in 2008-09 and ~18%
    in 2020. If a future data source restores the full history, change the
    label and re-check the anchors deliberately -- do not let it drift back.
    """
    assert "CCC spread percentile (vs available history)" in ANCHORS
    assert not any("1996+" in label for label in ANCHORS), \
        "no anchor may claim a history depth the data source does not serve"


def test_private_credit_percentiles_cannot_carry_red_alone():
    """The 2026-09-10 recalibration: a rolling ~3-year percentile is a gauge.

    Before it, CCC at a 3-year high scored 96.8 and took the channel RED on its
    own — i.e. "highest in ~3 years" was being reported as absolute distress.
    """
    for label in ("CCC spread percentile (vs available history)",
                  "CCC−BBB dispersion percentile"):
        b, y, r, e, hi, cap = ANCHORS[label]
        assert cap == 79.0
        assert _pscore(100.0, b, y, r, e, hi, cap) == 79.0   # a 3-year high: YELLOW
        assert _status_from_score(_pscore(100.0, b, y, r, e, hi, cap)) == "YELLOW"


def test_ccc_level_trigger_registers_the_documented_episodes():
    """The level leg must fire on the episodes its anchors cite, and stay calm below."""
    b, y, r, e, hi, cap = ANCHORS["CCC-and-lower OAS"]
    assert cap == 100.0                                    # this leg IS the trigger
    assert _status_from_score(_pscore(6.0, b, y, r, e, hi, cap)) == "GREEN"    # 2007/2021 lows
    assert _status_from_score(_pscore(11.0, b, y, r, e, hi, cap)) == "YELLOW"  # 2018-Q4
    assert _status_from_score(_pscore(16.0, b, y, r, e, hi, cap)) == "RED"
    assert _status_from_score(_pscore(18.0, b, y, r, e, hi, cap)) == "RED"     # 2020 COVID
    assert _status_from_score(_pscore(20.0, b, y, r, e, hi, cap)) == "RED"     # 2016 energy
    assert _pscore(44.0, b, y, r, e, hi, cap) == 100.0                         # Dec-2008 peak
    # today's 10.64% is NOT distressed by absolute standards, whatever its 3y rank
    assert _status_from_score(_pscore(10.64, b, y, r, e, hi, cap)) == "GREEN"
