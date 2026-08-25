"""Duration Squeeze Radar gates — the pre-registered scorecard may not drift.

Spec: docs/research/tlt-squeeze-2026/scorecard_spec.md v2 (frozen 2026-08-25).
These tests pin (a) every registered threshold on both sides, (b) the two
historical calibration points the registration was validated against
(Aug-2026 live state and the Oct-2023 flagship-analog retro-score), and
(c) the STALE degradations. All offline — inputs injected."""
from __future__ import annotations

from datetime import date, timedelta

from app.metrics.squeeze import (F1_WINDOW_WEEKS, MET, NOT_MET, PARTIAL,
                                 STALE, UNVERIFIED, build_calendar,
                                 build_squeeze_radar, cond_f1, cond_f2,
                                 cond_f3, cond_f4, cond_t1, cond_t2, cond_t3,
                                 cond_t5)
from app.sources.cftc import parse_ust_pct_oi
from app.sources.finra import parse_rows


def _weekly(vals, end=date(2026, 8, 18)):
    n = len(vals)
    return [end - timedelta(weeks=n - 1 - i) for i in range(n)], list(vals)


# ── F1: futures short extreme (percentile, registered composition) ───────────

def test_gate_f1_bottom_decile_met_and_reset():
    hist = [float(-i % 20) - 5 for i in range(600)]     # varied history
    d, v = _weekly(hist + [-40.0])                       # record short week
    assert cond_f1(d, v).state == MET
    d, v = _weekly(hist + [+5.0])                        # mid-history week
    assert cond_f1(d, v).state == NOT_MET


def test_gate_f1_percentile_is_trailing_10y_not_alltime():
    # Ancient deep shorts outside the 10y window must NOT dilute the pctile:
    # 600 weeks of -60 (older than the window) then 520 weeks in [-10, 0].
    old = [-60.0] * 600
    recent = [-(i % 10) for i in range(F1_WINDOW_WEEKS - 1)]
    d, v = _weekly(old + recent + [-9.5])
    c = cond_f1(d, v)
    # -9.5 is near the BOTTOM of the trailing window -> MET; against the
    # all-time history it would sit far above the -60 era and read NOT MET.
    assert c.state == MET, c.detail


def test_gate_f1_stale_on_empty():
    assert cond_f1([], []).state == STALE


def test_gate_f1_threshold_straddles_the_10th_percentile():
    """Anti-mutation gate: 500-week window of distinct values; the current
    week is placed just under vs just over the registered decile. A silent
    retune of F1_PCTILE_MAX moves one of these."""
    base = [float(-i) for i in range(500)]              # 0 .. -499
    # current -454.5: 45 of 501 values below -> 8.98th pctile -> MET
    d, v = _weekly(base + [-454.5])
    assert cond_f1(d, v).state == MET
    # current -444.5: 55 below -> 10.98th pctile -> NOT MET
    d, v = _weekly(base + [-444.5])
    assert cond_f1(d, v).state == NOT_MET


def test_gate_f1_registered_composition_is_duration_only():
    """The registration's -30.3%OI / 9.2th pctile was computed on the
    duration complex. A 2Y row must be excluded by the fetch's WHERE, and the
    parser must aggregate what it is given per date."""
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-08-18", "lev_money_positions_long": "10",
         "lev_money_positions_short": "40", "open_interest_all": "100"},
        {"report_date_as_yyyy_mm_dd": "2026-08-18", "lev_money_positions_long": "20",
         "lev_money_positions_short": "20", "open_interest_all": "100"},
    ]
    d, v = parse_ust_pct_oi(rows)
    assert v == [(30 - 60) / 200 * 100.0]                # aggregated, -15%OI
    from app.sources import cftc
    assert "UST 2Y NOTE" not in cftc._DURATION_CONTRACTS
    assert set(cftc._DURATION_CONTRACTS) == {
        "UST 10Y NOTE", "ULTRA UST 10Y", "UST BOND", "ULTRA UST BOND"}


# ── F2: ETF short base ───────────────────────────────────────────────────────

def _si(shares, dtc=3.6, dt="2026-07-31"):
    return {"settlement_date": dt, "shares_short": shares, "adv": 26_400_000,
            "dtc": dtc}


def test_gate_f2_threshold_both_sides():
    so = 571_300_000
    assert cond_f2([_si(95_278_691)], so).state == NOT_MET     # 16.7%
    assert cond_f2([_si(150_497_343)], so).state == MET        # 26.3%


def test_gate_f2_threshold_straddles_20pct():
    so = 500_000_000
    assert cond_f2([_si(100_000_000)], so).state == MET        # exactly 20.0
    assert cond_f2([_si(99_500_000)], so).state == NOT_MET     # 19.9


def test_gate_f2_no_denominator_is_stale_not_guessed():
    c = cond_f2([_si(150_000_000)], None)
    assert c.state == STALE
    assert "not computable" in c.detail


# ── F3: term premium percentile since 2015 ───────────────────────────────────

def test_gate_f3_threshold_both_sides():
    n = 500
    dates = [date(2015, 1, 1) + timedelta(days=7 * i) for i in range(n)]
    vals = [i / n for i in range(n)]                    # rising 0 -> 1
    assert cond_f3(dates, vals).state == MET            # last = max
    assert cond_f3(dates, vals[::-1]).state == NOT_MET  # last = min
    # pre-2015 history must be excluded from the percentile basis
    early = [date(1990, 1, 1) + timedelta(days=7 * i) for i in range(200)]
    c = cond_f3(early + dates, [9.9] * 200 + vals)
    assert c.state == MET, "pre-2015 readings leaked into the F3 basis"


def test_gate_f3_threshold_straddles_75th_percentile():
    n = 500
    dates = [date(2015, 1, 1) + timedelta(days=7 * i) for i in range(n)]
    base = [float(i) for i in range(n - 1)]             # 0..498
    # 385 of 500 below -> 77th pctile -> MET; 365 below -> 73rd -> NOT MET
    assert cond_f3(dates, base + [384.5]).state == MET
    assert cond_f3(dates, base + [364.5]).state == NOT_MET


# ── F4: borrow stress is UNVERIFIED, never silently scored ───────────────────

def test_gate_f4_unverified_scores_zero_and_carries_dtc():
    c = cond_f4([_si(95_278_691, dtc=3.61)])
    assert c.state == UNVERIFIED and c.value == 3.61
    r = build_squeeze_radar(
        cot=([], []), si_rows=[_si(95_278_691)], shares_outstanding=None,
        tp=([], []), fed_chg_6m_bp=None, payrolls=([], []), sahm=([], []),
        core_pce=([], []), move=([], []), hy_oas=([], []))
    assert r["fuel_score"] == 0.0                       # UNVERIFIED counts 0


# ── T1: fed path ─────────────────────────────────────────────────────────────

def test_gate_t1_cuts_priced_threshold():
    assert cond_t1(-60.0).state == MET
    assert cond_t1(-50.1).state == MET
    assert cond_t1(-50.0).state == NOT_MET              # STRICT: spec ">50bp"
    assert cond_t1(-49.9).state == NOT_MET
    assert cond_t1(+29.8).state == NOT_MET              # Aug-2026 live state
    assert cond_t1(None).state == STALE


def test_gate_t1_manual_first_cut_leg_is_stated_and_flips(monkeypatch):
    """The first-cut leg is by-commit (T4 pattern). Unconfirmed: the detail
    must SAY it is manual and unscored; confirmed: MET regardless of pricing,
    including with the priced leg STALE."""
    c = cond_t1(+29.8)
    assert "MANUAL" in c.detail and "unconfirmed" in c.detail
    from app.metrics import squeeze as sq
    monkeypatch.setitem(sq.T1_MANUAL_FIRST_CUT, "confirmed", True)
    assert cond_t1(+29.8).state == MET
    assert cond_t1(None).state == MET


def test_gate_t1_implied_change_math():
    from app.sources.fed_futures import implied_6m_change_bp
    today = date.today()
    y6, m6 = (today.year + (today.month + 5) // 12,
              (today.month + 5) % 12 + 1)
    prices = {(today.year, today.month): 96.25, (y6, m6): 96.85}
    assert implied_6m_change_bp(prices) == -60.0        # 3.75 -> 3.15
    assert implied_6m_change_bp({}) is None


# ── T2: labor break ──────────────────────────────────────────────────────────

def _payrolls(chgs, end=date(2026, 7, 1)):
    lvl, out = 160_000.0, []
    for c in chgs:
        lvl += c
        out.append(lvl)
    n = len(out)
    dts = [date(end.year, end.month, 1) - timedelta(days=30 * (n - 1 - i))
           for i in range(n)]
    return dts, out


def test_gate_t2_aug2026_state_is_not_met():
    # +63, +20, -23: 3m avg +20k, Sahm -0.03 — the live Aug-2026 reading. The
    # spec's own counter-agent finding 6a: this is NOT MET, never "partial".
    pay = _payrolls([200, 148, 63, 20, -23])
    c = cond_t2(*pay, [date(2026, 7, 1)], [-0.03])
    assert c.state == NOT_MET and round(c.value) == 20


def test_gate_t2_missing_months_fall_back_to_sahm_leg():
    d, v = _payrolls([200, 148, 63, 20, -23])
    d = d[:-1] + [d[-1] + timedelta(days=120)]           # a hole in the series
    c = cond_t2(d, v, [date(2026, 7, 1)], [-0.03])
    assert c.state == NOT_MET and "missing months" in c.detail
    c = cond_t2(d, v, [date(2026, 7, 1)], [0.55])        # Sahm leg still works
    assert c.state == MET


def test_gate_t2_either_leg_fires():
    pay_neg = _payrolls([50, -40, -30, -20])            # 3m avg -30
    assert cond_t2(*pay_neg, [date(2026, 7, 1)], [0.10]).state == MET
    pay_ok = _payrolls([200, 150, 150, 150])
    assert cond_t2(*pay_ok, [date(2026, 7, 1)], [0.50]).state == MET  # Sahm leg
    assert cond_t2(*pay_ok, [date(2026, 7, 1)], [0.49]).state == NOT_MET


# ── T3: inflation runway ─────────────────────────────────────────────────────

def _pce(m3_ann_pct, n=6, end=date(2026, 6, 1)):
    g = (1 + m3_ann_pct / 100.0) ** (1 / 12.0)
    lvls = [100.0 * g ** i for i in range(n)]
    dts = [date(end.year, end.month, 1) - timedelta(days=30 * (n - 1 - i))
           for i in range(n)]
    return dts, lvls


def test_gate_t3_threshold_both_sides():
    d, v = _pce(2.0)
    assert cond_t3(d, v).state == MET
    d, v = _pce(2.89)                                    # Aug-2026 live state
    c = cond_t3(d, v)
    assert c.state == NOT_MET and abs(c.value - 2.89) < 0.05
    assert cond_t3(d[:3], v[:3]).state == STALE          # <4 prints
    d, v = _pce(2.45)                                    # straddle the bar
    assert cond_t3(d, v).state == MET
    d, v = _pce(2.55)
    assert cond_t3(d, v).state == NOT_MET


def test_gate_t3_missing_months_degrade_to_stale():
    d, v = _pce(2.0, n=6)
    gapped_d = d[:3] + [d[3] + timedelta(days=90), d[4] + timedelta(days=90),
                        d[5] + timedelta(days=90)]
    c = cond_t3(gapped_d, v)
    assert c.state == STALE and "missing months" in c.detail


# ── T5: vol/dislocation ──────────────────────────────────────────────────────

def _daily(vals, end=date(2026, 8, 24)):
    n = len(vals)
    return [end - timedelta(days=n - 1 - i) for i in range(n)], list(vals)


def test_gate_t5_needs_both_legs():
    oas_wide = _daily([2.5] * 150 + [3.5] * 50)          # step OUTSIDE the 91d lookback
    oas_flat = _daily([2.7] * 200)
    move_hot = _daily([135.0] * 200)
    move_calm = _daily([74.0] * 200)
    assert cond_t5(*move_hot, *oas_wide).state == MET
    assert cond_t5(*move_hot, *oas_flat).state == NOT_MET
    assert cond_t5(*move_calm, *oas_wide).state == NOT_MET
    assert cond_t5([], [], *oas_wide).state == STALE


def test_gate_t5_threshold_straddles_120():
    oas_wide = _daily([2.5] * 150 + [3.5] * 50)
    assert cond_t5(*_daily([120.1] * 200), *oas_wide).state == MET
    assert cond_t5(*_daily([120.0] * 200), *oas_wide).state == NOT_MET


def test_gate_t5_short_history_is_stale_not_a_verdict():
    # <91d of OAS: the widening leg is unverifiable -> STALE, never NOT_MET
    c = cond_t5(*_daily([135.0] * 30), *_daily([3.5] * 30))
    assert c.state == STALE and "unverifiable" in c.detail


def test_gate_calendar_fomc_exhaustion_is_loud():
    cal = build_calendar(date(2027, 1, 5))
    assert any(e.get("warning") and "EXHAUSTED" in e["event"] for e in cal), cal


# ── the two calibration points the registration was validated on ─────────────

def test_gate_aug2026_scores_fuel2_triggers_half():
    """The live 2026-08-25 state as measured (study + counter-agent): F1 MET,
    F2 NOT (16.7%), F3 MET (99.7th), F4 UNVERIFIED, T1-T3/T5 NOT, T4 PARTIAL
    -> 2/4 and 0.5/5. If this test breaks, either a threshold drifted or the
    fixture no longer matches the registration — both are merge-blockers."""
    hist = [10.0 - i * 0.08 for i in range(520)]         # drifts to deep short
    cot = _weekly(hist + [-45.0])
    tp_d = [date(2015, 1, 1) + timedelta(days=7 * i) for i in range(600)]
    tp_v = [0.1 + 0.001 * i for i in range(599)] + [0.84]
    r = build_squeeze_radar(
        cot=cot, si_rows=[_si(95_278_691)], shares_outstanding=571_300_000,
        tp=(tp_d, tp_v), fed_chg_6m_bp=+29.8,
        payrolls=_payrolls([200, 148, 63, 20, -23]),
        sahm=([date(2026, 7, 1)], [-0.03]), core_pce=_pce(2.89),
        move=_daily([74.0] * 200), hy_oas=_daily([2.7] * 200),
        today=date(2026, 8, 25))
    assert r["fuel_score"] == 2.0, [c["state"] for c in r["fuel"]]
    assert r["trigger_score"] == 0.5, [c["state"] for c in r["triggers"]]


def test_gate_oct2023_retroscore_triggers_2of5():
    """The flagship analog, PIT (counter-agent finding 5): T3 and T5 MET,
    T1/T2 NOT — the card must separate Oct-2023 from Aug-2026, and this
    fixture is the separation. T4 is manual and reflects TODAY's commit, so
    only the four automated triggers are pinned here."""
    t1 = cond_t1(-10.0)                                  # no cuts priced Oct-23
    t2 = cond_t2(*_payrolls([250, 200, 180, 160], end=date(2023, 9, 1)),
                 [date(2023, 9, 1)], [0.33])
    t3 = cond_t3(*_pce(2.05, end=date(2023, 8, 1)))
    t5 = cond_t5(_daily([135.0] * 200, end=date(2023, 10, 31))[0],
                 _daily([135.0] * 200, end=date(2023, 10, 31))[1],
                 *_daily([3.77] * 150 + [4.42] * 50, end=date(2023, 10, 31)))
    states = [t1.state, t2.state, t3.state, t5.state]
    assert states == [NOT_MET, NOT_MET, MET, MET], states


# ── calendar + parser + payload honesty ──────────────────────────────────────

def test_gate_calendar_qra_and_fomc():
    cal = build_calendar(date(2026, 10, 20))
    events = {e["event"]: e for e in cal}
    assert events["QRA refunding statement"]["date"] == "2026-11-04"
    assert events["QRA refunding statement"]["estimated"] is True
    assert events["FOMC decision"]["date"] == "2026-10-28"
    assert events["FOMC decision"]["estimated"] is False
    for e in cal:
        assert date.fromisoformat(e["date"]) >= date(2026, 10, 20)


def test_gate_finra_parser_dedupes_and_sorts():
    csv_text = (
        "\"settlementDate\",\"currentShortPositionQuantity\","
        "\"averageDailyVolumeQuantity\",\"daysToCoverQuantity\"\n"
        "\"2026-07-31\",\"95278691\",\"26400000\",\"3.61\"\n"
        "\"2026-07-15\",\"93857485\",\"20800000\",\"4.51\"\n"
        "\"2026-07-31\",\"95278691\",\"26400000\",\"3.61\"\n")
    rows = parse_rows(csv_text)
    assert [r["settlement_date"] for r in rows] == ["2026-07-15", "2026-07-31"]
    assert rows[-1]["shares_short"] == 95_278_691 and rows[-1]["dtc"] == 3.61


def test_gate_payload_carries_registration_and_honesty():
    r = build_squeeze_radar(
        cot=([], []), si_rows=[], shares_outstanding=None, tp=([], []),
        fed_chg_6m_bp=None, payrolls=([], []), sahm=([], []),
        core_pce=([], []), move=([], []), hy_oas=([], []))
    assert "scorecard_spec.md v2" in r["spec"]
    assert any("fuel, never ignition" in h for h in r["honesty"])
    assert any("WITHIN NOISE" in h for h in r["honesty"])
    assert any("2/5 the day before" in h for h in r["honesty"])
    # all-STALE inputs -> zero scores, never a phantom MET
    assert r["fuel_score"] == 0.0 and r["trigger_score"] == 0.5  # T4 manual


def test_gate_t4_is_manual_partial_with_asof():
    from app.metrics.squeeze import cond_t4
    c = cond_t4()
    assert c.state == PARTIAL and c.asof == "2026-08-25"
    assert "manual (by commit)" in c.detail
