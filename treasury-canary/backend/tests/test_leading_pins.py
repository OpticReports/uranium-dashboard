"""Leading stack + pin board tests."""
from datetime import date, timedelta

from app.metrics.base import Status
from app.metrics.leading import _ma, _off_peak, _yoy, build_leading_metrics
from app.metrics.pins import _grade, _worst, PinPart, build_pin_board
from app.scoring.composite import compute_composite


def _months(n):
    return [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(n)]


def _days(n):
    return [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]


# --- leading helpers ----------------------------------------------------------

def test_yoy():
    vals = [100.0] * 12 + [90.0]
    assert _yoy(vals)[-1] == -10.0
    assert _yoy([100.0] * 5)[-1] is None  # not enough history


def test_off_peak():
    vals = [100.0, 110.0, 99.0]
    assert _off_peak(vals, window=12)[-1] == -10.0
    assert _off_peak([100.0], window=12)[-1] == 0.0


def test_ma3():
    assert _ma([1.0, 2.0, 3.0], 3)[-1] == 2.0
    assert _ma([1.0, 2.0], 3)[-1] is None


def test_leading_metrics_informational_and_thresholds():
    n = 26
    bundle = {
        "permits": (_months(n), [1500.0] * 20 + [1100.0] * 6),    # recent deep YoY drop
        "sloos": (_months(4), [5.0, 8.0, 25.0, 25.0]),            # net 25% tightening
        "temp_help": (_months(n), [3000.0] * n),                   # flat -> green
        "heavy_trucks": (_months(n), [500.0] * 20 + [380.0] * 6),  # ~-24% off peak
        "core_capex": (_months(n), [70.0] * n),
        "cfnai": (_months(n), [0.1] * (n - 3) + [-1.0, -1.0, -1.0]),  # MA3 = -1.0
        "gdpnow": (_months(3), [2.5, 2.0, 1.8]),
        "cp_prob": (_months(6), [0.5, 0.4, 0.6, 0.5, 0.7, 0.5]),
    }
    metrics = build_leading_metrics(bundle)
    by = {m.metric_id: m for m in metrics}

    assert all(m.informational for m in metrics)          # NEVER in the composite
    assert all(m.category == "K" for m in metrics)
    assert by["leading.permits_yoy"].status is Status.RED      # ~-26.7% YoY
    assert by["leading.sloos"].status is Status.RED            # 25 > 20
    assert by["leading.trucks_off_peak"].status is Status.RED  # -24% off peak
    assert by["leading.cfnai_ma3"].status is Status.RED        # -1.0 < -0.70
    assert by["leading.gdpnow"].status is Status.GREEN
    assert by["leading.cp_prob"].status is Status.GREEN

    # composite is untouched by K metrics (all informational)
    comp = compute_composite(metrics)
    assert "K" not in comp.category_scores


def test_leading_all_stale_safe():
    metrics = build_leading_metrics({})
    assert all(m.status is Status.STALE for m in metrics)


# --- pins ----------------------------------------------------------------------

def test_grade_directions():
    assert _grade(60.0, 25.0, 50.0) == "RED"
    assert _grade(30.0, 25.0, 50.0) == "YELLOW"
    assert _grade(10.0, 25.0, 50.0) == "GREEN"
    assert _grade(None, 25.0, 50.0) == "STALE"
    assert _grade(-16.0, -8.0, -15.0, higher_is_worse=False) == "RED"


def test_worst_ignores_stale():
    parts = [PinPart("a", None, "", "STALE"), PinPart("b", 1.0, "", "YELLOW")]
    assert _worst(parts) == "YELLOW"
    assert _worst([PinPart("a", None, "", "STALE")]) == "STALE"


def test_pin_board_oil_shock_red():
    n = 260
    oil = [60.0] * (n - 1) + [95.0]   # +58% vs 252 obs ago
    bundle = {"oil": (_days(n), oil)}
    board = build_pin_board(bundle)
    by = {c["channel_id"]: c for c in board["channels"]}
    assert by["oil_shock"]["status"] == "RED"
    assert board["overall"] == "RED"
    assert board["n_channels"] == 12


def test_pin_board_basis_trade():
    from app.sources.cftc import aggregate_net_short
    rows = [{"report_date_as_yyyy_mm_dd": "2026-07-07T00:00:00.000",
             "contract_market_name": "UST 10Y NOTE",
             "lev_money_positions_long": "400000", "lev_money_positions_short": "2400000"},
            {"report_date_as_yyyy_mm_dd": "2026-07-07T00:00:00.000",
             "contract_market_name": "UST 5Y NOTE",
             "lev_money_positions_long": "500000", "lev_money_positions_short": "2500000"},
            {"report_date_as_yyyy_mm_dd": "2026-06-30T00:00:00.000",
             "contract_market_name": "UST 10Y NOTE",
             "lev_money_positions_long": "500000", "lev_money_positions_short": "1500000"}]
    d, v = aggregate_net_short(rows)
    assert v == [1.0, 4.0]  # per-date sums (short-long)/1e6, oldest first

    from datetime import date, timedelta
    weeks = [date(2025, 1, 1) + timedelta(weeks=i) for i in range(11)]
    # level yellow (4.0M) but BELOW prior highs -> percentile calm -> channel YELLOW
    board = build_pin_board({"cot_net_short": (weeks, [5.0] * 10 + [4.0])})
    by = {c["channel_id"]: c for c in board["channels"]}
    assert by["basis_trade"]["status"] == "YELLOW"
    # record-crowded book (6M, new high) -> level RED + percentile RED -> RED
    board2 = build_pin_board({"cot_net_short": (weeks, [5.0] * 10 + [6.0])})
    by2 = {c["channel_id"]: c for c in board2["channels"]}
    assert by2["basis_trade"]["status"] == "RED"


def test_pin_board_credit_event_discount_window():
    # $150B at the window (SVB-scale), H.4.1 units are $mm
    bundle = {"discount_window": (_days(10), [500.0] * 9 + [150_000.0])}
    board = build_pin_board(bundle)
    by = {c["channel_id"]: c for c in board["channels"]}
    assert by["credit_event"]["status"] == "RED"


def test_pin_board_empty_is_stale():
    board = build_pin_board({})
    assert board["overall"] == "STALE"
    assert board["n_live"] == 0


def test_pin_board_private_credit_bifurcation():
    # 200 calm days of CCC ~7 / BBB ~1.5, then CCC gaps to 12 while BBB stays
    # tight -> CCC pctile RED, dispersion pctile RED. NDFI growth stalls to -2 -> RED.
    days = _days(201)
    ccc = [7.0] * 200 + [12.0]
    bbb = [1.5] * 201
    months = [date(2024, 1, 1) + timedelta(days=30 * i) for i in range(12)]
    ndfi = [15.0] * 11 + [-2.0]
    board = build_pin_board({"ccc_oas": (days, ccc), "bbb_oas": (days, bbb),
                             "ndfi_loans": (months, ndfi)})
    by = {c["channel_id"]: c for c in board["channels"]}
    ch = by["private_credit"]
    assert ch["status"] == "RED"
    parts = {p["label"]: p for p in ch["parts"]}
    assert parts["CCC spread percentile (vs 1996+)"]["status"] == "RED"
    assert parts["CCC−BBB dispersion percentile"]["status"] == "RED"
    assert parts["Bank loans to NDFIs, m/m ann. growth"]["status"] == "RED"
    # attributes ride along for the frontend badges
    assert ch["mass"] and ch["speed"] and ch["kill_rate"]


def test_pin_board_private_credit_calm():
    days = _days(201)
    board = build_pin_board({"ccc_oas": (days, [7.0] * 200 + [6.5]),
                             "bbb_oas": (days, [1.5] * 201)})
    by = {c["channel_id"]: c for c in board["channels"]}
    # mid-history readings -> not RED; NDFI missing -> that part STALE but channel live
    assert by["private_credit"]["status"] in ("GREEN", "YELLOW")


def test_pin_board_carry_unwind():
    days = _days(30)
    # yen appreciates 8% in a month (Aug-2024 scale): 160 -> 147.2
    jpy = [160.0] * 9 + [160.0 - i * (12.8 / 21) for i in range(21)]
    months = [date(2024, 1, 1) + timedelta(days=30 * i) for i in range(14)]
    jgb = [1.0] * 2 + [1.0 + i * 0.06 for i in range(12)]   # +66bps over 12m
    board = build_pin_board({"jpy": (days, jpy), "jgb10": (months, jgb)})
    by = {c["channel_id"]: c for c in board["channels"]}
    ch = by["carry_unwind"]
    parts = {p["label"]: p for p in ch["parts"]}
    assert parts["USD/JPY, 1-month change"]["status"] == "RED"
    assert parts["10y JGB yield, 12-month change"]["status"] == "YELLOW"
    assert ch["status"] == "RED"


def test_pin_board_carry_calm():
    days = _days(30)
    board = build_pin_board({"jpy": (days, [160.0] * 29 + [161.0])})
    by = {c["channel_id"]: c for c in board["channels"]}
    assert by["carry_unwind"]["status"] == "GREEN"


def test_transmission_note_fires_only_on_fast_red_plus_elevated_dial():
    from app.metrics.pins import transmission_note

    def board_with(channel_id, status):
        return {"channels": [{"channel_id": channel_id, "label": channel_id,
                              "status": status}]}

    # fast channel red + elevated prob -> active, message names the channel
    t = transmission_note(board_with("basis_trade", "RED"), 35.0)
    assert t["active"] is True
    assert "basis_trade" in t["fast_red_channels"]
    assert "35%" in t["message"]

    # fast red but calm dial -> silent
    assert transmission_note(board_with("basis_trade", "RED"), 20.0)["active"] is False
    # elevated dial but only a SLOW channel red -> silent (gives time)
    assert transmission_note(board_with("private_credit", "RED"), 40.0)["active"] is False
    # fast channel merely yellow -> silent
    assert transmission_note(board_with("plumbing", "YELLOW"), 40.0)["active"] is False
    # prob unavailable -> silent, never crashes
    assert transmission_note(board_with("credit_event", "RED"), None)["active"] is False
    assert transmission_note({"channels": []}, 90.0)["active"] is False
