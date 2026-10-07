"""Gate tests for the crash stress harness (PREREG.md). Every test pins the
as-of instant to stress.SEED_NOW (2026-10-07 14:24Z) so the seam is the
2026-10-07 08:00Z bar, the one the seed state was taken against, for as long
as research/cagr/data/bars_4h_btcusd.csv is unchanged."""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stress                                                      # noqa: E402
from stress import (BAR, DAY, FEE_BPS, PAPER_SEED, SEED_NOW,       # noqa: E402
                    SEED_LAST_CLOSED_TS, Executor, Trade, build_spliced,
                    cap_qty, daily_loss_pct, engine_state_at, leg_notional,
                    load_closed_bars, paper_book, run_executor, run_path,
                    synthetic_path)
from harness import leg_trades, ts_of                              # noqa: E402
from app.engine.core import TradeCfg                                # noqa: E402

NOW = SEED_NOW


@pytest.fixture(scope="module")
def real():
    return load_closed_bars("btcusd", now=NOW)


# (i) splice continuity ---------------------------------------------------
def test_splice_continuity(real):
    sp = build_spliced("btcusd", "2020-02-13", months=12, offset_days=0, now=NOW)
    assert sp.seam == len(real) >= 2_400
    assert sp.last_real_ts == SEED_LAST_CLOSED_TS
    assert sp.t0 == sp.last_real_ts + BAR
    first = sp[sp.seam]
    assert math.isclose(first.close, sp.today_close * (sp.anchor_close / sp.anchor_close),
                        rel_tol=1e-12)
    import harness
    full = harness.load_bars("btcusd")
    a, e = ts_of("2020-02-13"), ts_of("2021-02-13")
    hist = [b for b in full if a <= b.ts < e]
    assert len(sp.path) == len(hist) == 2196
    for j in range(1, len(hist)):
        s, h, sp_prev, h_prev = sp.path[j], hist[j], sp.path[j - 1], hist[j - 1]
        assert abs(s.close / sp_prev.close - h.close / h_prev.close) <= 1e-9
        assert abs(s.open / sp_prev.close - h.open / h_prev.close) <= 1e-9
        assert abs(s.high / s.close - h.high / h.close) <= 1e-9
        assert abs(s.low / s.close - h.low / h.close) <= 1e-9
        assert s.volume == h.volume                         # unscaled
        assert s.ts == sp.t0 + j * BAR                      # 4h grid continues
    # offset shifts the window, scale re-anchors on the shifted first close
    sp2 = build_spliced("btcusd", "2020-02-13", offset_days=-14, now=NOW)
    assert sp2.anchor_ts == ts_of("2020-01-30")
    assert math.isclose(sp2[sp2.seam].close, sp.today_close, rel_tol=1e-12)


# (ii) nothing halts on a flat path -----------------------------------------
def test_flat_path_nothing_halts(real):
    c = real[-1].close
    sp = synthetic_path([c] * 300, now=NOW)
    r = run_path("flat", sp, 0.75, save=False)
    assert r["halts"] == []
    assert not [e for e in r["events"] if e[1].startswith("HALT")]
    assert min(r["equity_total"]) > 99_000          # fees only
    assert r["engine_halts_info"]["pullback"]["halted"] is False
    assert r["engine_halts_info"]["trend"]["halted"] is False


# helpers for the executor-only tests -----------------------------------------
def _synthetic_longs(sp, exit_bars: int, reason: str = "TIME"):
    t0 = sp.t0
    px = sp[sp.seam].open
    mk = lambda leg: Trade(leg, "L", t0, px, t0 + exit_bars * BAR,  # noqa: E731
                           sp[min(sp.seam + exit_bars, len(sp) - 1)].open, reason)
    return {"pullback": [mk("pullback")], "trend": [mk("trend")]}


def _geom(c0: float, per_bar: float, n: int) -> list[float]:
    return [c0 * (1 + per_bar) ** (j + 1) for j in range(n)]


# (iii) a -40% day trips DAILY_LOSS at the line and re-arms next day ---------
def test_daily_loss_trips_at_line_and_rearms(real):
    c0 = real[-1].close
    # t0 is 12:00Z: three bars of -15.7% (-40% by 00:00), then flat 3 days
    closes = _geom(c0, -0.157, 3) + [c0 * (1 - 0.157) ** 3] * 18
    sp = synthetic_path(closes, now=NOW)
    assert sp.t0 % DAY == 12 * 3600
    trades = _synthetic_longs(sp, 40)
    ex = run_executor(sp, trades, 0.75)
    assert ex.dpct == pytest.approx(0.15)
    m = ex.trades[0]["size_mult"]
    assert m == 1.0, "precondition: the live vol target reads 1.0 at the seam"
    gross = leg_notional(0.75, "pullback", m) + leg_notional(0.75, "trend", m)
    assert gross == pytest.approx(112_500.0)
    assert len(ex.halts) == 1
    h = ex.halts[0]
    assert h["kind"] == "DAILY_LOSS" and h["ts"] == sp.t0       # first bar's low
    assert h["line"] == pytest.approx(85_000.0)
    # flattened AT the line: only the exit fee sits below it
    exit_fee = sum(FEE_BPS / 1e4 * t["qty"] * t["exit_px"] for t in ex.trades
                   if t["reason"] == "HALT_DAILY_LOSS")
    assert h["equity_after"] == pytest.approx(85_000.0 - exit_fee, abs=0.05)
    b0 = sp[sp.seam]
    assert b0.low < h["fill_px"] < b0.open
    # re-arms at the next 00:00 UTC bar (bar 3), day_start = equity then,
    # and the engine's still-open legs are re-mirrored at that open
    rearm_ts = sp.t0 + 3 * BAR
    assert rearm_ts % DAY == 0
    assert h["rearm_ts"] == rearm_ts
    kinds = {(e[0], e[1]) for e in ex.events}
    assert (rearm_ts, "REARM") in kinds
    assert (rearm_ts, "REMIRROR") in kinds
    rearm_ev = [e for e in ex.events if e[1] == "REARM"][0]
    assert rearm_ev[3] == pytest.approx(h["equity_after"], abs=0.01)  # day_start then
    assert ex.halted is None
    # flat afterwards: only the re-mirror entry fees leave the account
    assert ex.eq_tot_out[-1] == pytest.approx(h["equity_after"] - sum(
        p.efee for p in ex.pos.values()), abs=0.01)
    # same event, K 0.30: 6% line = 94,000, trips on the same bar
    ex2 = run_executor(sp, trades, 0.30)
    assert ex2.dpct == pytest.approx(0.06)
    assert ex2.halts[0]["kind"] == "DAILY_LOSS"
    assert ex2.halts[0]["line"] == pytest.approx(94_000.0)
    # the literal-order rule agrees here (the low did not reach the DD line)
    ex3 = run_executor(sp, trades, 0.75, halt_rule="dd_first")
    assert ex3.halts[0]["kind"] == "DAILY_LOSS"


# (iv) a -35% drawdown trips DRAWDOWN first; variant A stays flat ------------
def test_drawdown_trips_first_and_stays_flat(real):
    c0 = real[-1].close
    # -0.5% per bar = -3%/day for 16 days: no day crosses the 15% daily line,
    # the drawdown line (30% of base) is crossed on the way to -35%
    closes = _geom(c0, -0.005, 96) + [c0 * 0.995 ** 96] * 60
    sp = synthetic_path(closes, now=NOW)
    trades = _synthetic_longs(sp, 200)
    for rule in ("first_cross", "dd_first"):
        ex = run_executor(sp, trades, 0.75, dd_variant="A", halt_rule=rule)
        assert len(ex.halts) == 1
        h = ex.halts[0]
        assert h["kind"] == "DRAWDOWN"
        assert h["line"] == pytest.approx(70_000.0)
        exit_fee = sum(FEE_BPS / 1e4 * t["qty"] * t["exit_px"] for t in ex.trades
                       if t["reason"] == "HALT_DRAWDOWN")
        assert h["equity_after"] == pytest.approx(70_000.0 - exit_fee, abs=0.05)
        assert ex.halted == "DRAWDOWN" and not ex.pos
        i = ex.ts_out.index(h["ts"])
        assert all(abs(e - h["equity_after"]) < 0.01 for e in ex.eq_tot_out[i:])
        assert not [e for e in ex.events if e[1] in ("REARM", "RESUME", "RESUME_REANCHOR")]
    # variant B: resumed 7 days later; equity is still below the line so the
    # resume re-anchors the marks, and the open legs are re-mirrored
    exb = run_executor(sp, trades, 0.75, dd_variant="B")
    h = exb.halts[0]
    res = [e for e in exb.events if e[1] == "RESUME_REANCHOR"]
    assert len(res) == 1 and res[0][0] >= h["ts"] + 7 * DAY
    assert res[0][0] < h["ts"] + 7 * DAY + BAR
    assert (res[0][0], "REMIRROR") in {(e[0], e[1]) for e in exb.events}
    assert exb.hw == pytest.approx(res[0][3], abs=0.01)   # marks moved to equity
    assert exb.halted is None and set(exb.pos) == {"pullback", "trend"}


# (v) the engine's own paper-book halt drops later trades --------------------
def test_engine_book_halt_drops_later_trades(real):
    t0 = real[-1].ts + BAR
    px = real[-1].close
    t1 = Trade("pullback", "L", t0, px, t0 + 10 * BAR, px * 0.64, "STOP")
    t2 = Trade("pullback", "L", t0 + 12 * BAR, px * 0.6, t0 + 20 * BAR, px * 0.7, "SIGNAL")
    t3 = Trade("pullback", "L", t0 + 30 * BAR, px * 0.7, None, None, "OPEN")
    pub, info = paper_book([t1, t2, t3], t0, PAPER_SEED["pullback"])
    assert info["halted"] and info["halt_ts"] == t1.exit_ts
    assert pub == [t1] and info["dropped"] == 2
    qty = round(104_840.0 / px, 6)
    exp = 104_840.0 + qty * (px * 0.64 - px) - qty * px * 12 / 1e4
    assert info["equity_at_halt"] == pytest.approx(exp, abs=0.01)
    assert exp / 107_860.0 - 1 <= -0.30
    # disabled: everything publishes
    pub2, info2 = paper_book([t1, t2, t3], t0, PAPER_SEED["pullback"], enabled=False)
    assert pub2 == [t1, t2, t3] and not info2["halted"]
    # a -20% loser does not reach -30% from the 107,860 peak
    t1b = Trade("pullback", "L", t0, px, t0 + 10 * BAR, px * 0.8, "STOP")
    pub3, info3 = paper_book([t1b, t2, t3], t0, PAPER_SEED["pullback"])
    assert pub3 == [t1b, t2, t3] and not info3["halted"]
    # the trend book halts at -50%
    t4 = Trade("trend", "L", t0, px, t0 + 10 * BAR, px * 0.45, "STOP")
    pub4, info4 = paper_book([t4, t2], t0, PAPER_SEED["trend"])
    assert info4["halted"] and pub4 == [t4]
    # history (closed before t0) is skipped, not compounded
    th = Trade("trend", "L", t0 - 50 * BAR, px, t0 - 10 * BAR, px * 0.1, "STOP")
    pub5, info5 = paper_book([th, t2], t0, PAPER_SEED["trend"])
    assert pub5 == [t2] and not info5["halted"]


# (vi) caps clamp gross to 130k -----------------------------------------------
def test_caps_clamp_gross(real, monkeypatch):
    px = 100_000.0
    assert cap_qty("trend", 0.5, px, other_qty=1.0) == pytest.approx(0.3)   # 30k room
    assert cap_qty("pullback", 0.5, px, other_qty=0.0) == pytest.approx(0.5)
    assert cap_qty("pullback", 0.5, px, other_qty=1.3) == 0.0
    # integration: trend long entered at t0, price triples, then the pullback
    # enters: its notional is clamped so gross == 130k (size_mult pinned 1.0)
    monkeypatch.setattr(stress.volsize, "size_mult",
                        lambda closes, ts: {"m": 1.0, "basis": "vol_target"})
    c0 = real[-1].close
    closes = _geom(c0, 0.011, 100) + [c0 * 1.011 ** 100] * 20
    sp = synthetic_path(closes, now=NOW)
    t0 = sp.t0
    e_px = sp[sp.seam + 100].open
    trades = {"trend": [Trade("trend", "L", t0, sp[sp.seam].open, None, None, "OPEN")],
              "pullback": [Trade("pullback", "L", t0 + 100 * BAR, e_px,
                                 t0 + 110 * BAR, e_px, "TIME")]}
    ex = run_executor(sp, trades, 0.75)
    pb = [t for t in ex.trades if t["leg"] == "pullback"][0]
    tr_qty = ex.pos["trend"].qty
    assert pb["notional"] == pytest.approx(130_000.0 - tr_qty * e_px, abs=0.01)
    assert pb["notional"] < leg_notional(0.75, "pullback", 1.0)
    assert [e for e in ex.events if e[1] == "CAP_CLAMP"]
    assert ex.halts == []


# (vii) the engine on real history reproduces the live S4 position ----------
def test_live_s4_reproduced_at_seam(real):
    assert real[-1].ts == SEED_LAST_CLOSED_TS
    tc = TradeCfg(taker_fee_bps=FEE_BPS)
    tt = leg_trades(real, "donchian", trail_atr=5.0, tcfg=tc, leg="trend")
    last = tt[-1]
    assert last.reason == "OPEN" and last.side == "L"
    assert last.entry_price == pytest.approx(80_702.77, abs=0.005)
    assert last.entry_ts == 1_789_747_200                 # 2026-09-18 20:00Z
    book = engine_state_at(real, "donchian")
    assert book.position is not None and book.position.side == "L"
    assert book.position.trail == pytest.approx(83_274.67, abs=0.01)
    assert book.pending is None
    # S3 on this CSV: the long limit 84,121.28 (signal 00:00Z) FILLED on the
    # 04:00Z bar (low 84,010.77 < limit). The live snapshot said PENDING -
    # a feed/timing difference the study discloses; the harness follows the
    # production code path on the data it has.
    pt = leg_trades(real, "pullback", tcfg=tc, leg="pullback")
    assert pt[-1].reason == "OPEN" and pt[-1].side == "L"
    assert pt[-1].entry_price == pytest.approx(84_121.28, abs=0.005)
    assert pt[-1].entry_ts == 1_791_345_600                # 2026-10-07 04:00Z


# accounting / carry hook ------------------------------------------------------
def test_covid_smoke_accounting_and_carry(real):
    r = run_path("covid_test", build_spliced("btcusd", "2020-02-13", now=NOW), 0.75,
                 save=False)
    closed = sum(t["pnl"] for t in r["trades"])
    assert closed == pytest.approx(r["equity_btc"][-1] - 70_000.0, abs=0.05)
    assert r["equity_total"][0] - r["equity_btc"][0] == pytest.approx(30_000.0)
    assert len(r["ts"]) == len(r["equity_total"]) == r["n_path_bars"] == 2196
    assert r["balances"]["365"] is not None and r["max_dd"] <= 0
    assert r["bench_hold_btc"][0] == pytest.approx(100_000.0)
    # the executor re-mirrors the engine's open legs at the first bar's open
    assert r["events"][0][1] == "REMIRROR" and r["events"][0][0] == r["t0"]
    # a carry crash alone (no BTC exposure needed) trips DRAWDOWN, and the
    # carry value is added 1:1 to BTC-book equity before the halt checks
    sp = synthetic_path([real[-1].close] * 60, now=NOW)
    n = len(sp.path)
    carry = [30_000.0] * 10 + [-5_000.0] * (n - 10)       # -35k at bar 10
    ex = run_executor(sp, {"pullback": [], "trend": []}, 0.75, carry_value=carry)
    assert ex.halts and ex.halts[0]["kind"] == "DRAWDOWN"
    assert ex.halts[0]["ts"] == sp.t0 + 10 * BAR
    assert ex.eq_tot_out[10] - ex.eq_btc_out[10] == pytest.approx(-5_000.0)
    with pytest.raises(ValueError):
        run_executor(sp, {"pullback": [], "trend": []}, 0.75, carry_value=[1.0] * 3)


def test_daily_loss_pct_scales_with_k():
    assert daily_loss_pct(0.30) == pytest.approx(0.06)
    assert daily_loss_pct(0.75) == pytest.approx(0.15)
    assert daily_loss_pct(0.10) == pytest.approx(0.06)
    assert Executor(synthetic_path([1.0], now=NOW), {"pullback": [], "trend": []},
                    2.0).K == pytest.approx(0.75)           # KELLY_M_CAP clamp


# ---------------------------------------------------------------------------
# gate tests added after the independent review (2026-10-07); each fails on
# the pre-review code (the parameter / key / function did not exist there)
# ---------------------------------------------------------------------------

# (viii) BTC perp funding on the book's own positions (SERIOUS) -----------------
def test_btc_funding_per_stamp(real):
    c0 = real[-1].close
    sp = synthetic_path([c0] * 30, now=NOW)            # flat price: open == close == c0
    t0 = sp.t0
    rate = 0.0005                                      # 0.05% per 8h
    # stamps on the closes of bars 0, 2 (positive), 5 (negative), 9 (the exit
    # bar: nothing held by its close) and 12 (flat); one off-grid stamp 1h
    # after bar 1's close must land on bar 2's close
    stamps = {t0 + BAR: rate, t0 + 3 * BAR: rate, t0 + 6 * BAR: -rate,
              t0 + 10 * BAR: rate, t0 + 13 * BAR: rate}
    assert stress.funding_by_close({t0 + 2 * BAR + 3600: rate}) == {t0 + 3 * BAR: [rate]}
    px = sp[sp.seam].open
    exit_ts = t0 + 9 * BAR
    trades = {"pullback": [Trade("pullback", "L", t0, px, exit_ts, sp[sp.seam + 9].open, "TIME")],
              "trend": [Trade("trend", "S", t0, px, exit_ts, sp[sp.seam + 9].open, "TIME")]}
    ex = run_executor(sp, trades, 0.75, btc_funding=stamps)
    ex0 = run_executor(sp, trades, 0.75)               # not modelled
    assert ex0.btc_funding_modelled is False and ex0.funding == 0.0
    assert ex.btc_funding_modelled is True
    pb = [t for t in ex.trades if t["leg"] == "pullback"][0]
    tr = [t for t in ex.trades if t["leg"] == "trend"][0]
    qp, qt = pb["qty"], tr["qty"]
    # long pays the positive stamps and receives the negative one; short the reverse
    assert pb["funding"] == pytest.approx(-qp * c0 * rate, abs=0.01)
    assert tr["funding"] == pytest.approx(+qt * c0 * rate, abs=0.01)
    assert ex.funding_by_leg["pullback"] == pytest.approx(pb["funding"], abs=0.01)
    assert ex.funding_by_leg["trend"] == pytest.approx(tr["funding"], abs=0.01)
    assert ex.funding_stamps == 6                     # 3 paid stamps x 2 positions
    assert ex.funding == pytest.approx(pb["funding"] + tr["funding"], abs=0.01)
    # it is in the P&L and in the cash: the two runs differ by exactly the funding
    assert pb["pnl"] == pytest.approx(pb["gross"] - pb["fees"] + pb["funding"], abs=0.01)
    assert ex.eq_tot_out[-1] - ex0.eq_tot_out[-1] == pytest.approx(ex.funding, abs=0.01)
    assert sum(t["pnl"] for t in ex.trades) == pytest.approx(ex.eq_btc_out[-1] - 70_000.0, abs=0.05)
    # timing: paid at the stamps' closes, nothing before bar 0's close, nothing after the exit
    cum = ex.funding_cum_out
    assert cum[0] == pytest.approx((-qp + qt) * c0 * rate, abs=0.01)
    assert cum[1] == pytest.approx(cum[0]) and cum[2] == pytest.approx(2 * cum[0], abs=0.01)
    assert cum[5] == pytest.approx(cum[0], abs=0.01)   # the negative stamp cancels one
    assert cum[9] == pytest.approx(cum[8]) and cum[-1] == pytest.approx(cum[8])
    # the live scenario: run_path reports the totals (COVID K0.75 offset 0,
    # XBTUSD stamps of the analogue window shifted onto today's grid)
    import run_all
    sp2 = build_spliced("btcusd", "2020-02-13", now=NOW)
    fund, meta = run_all.funding_for(sp2.anchor_ts, len(sp2.path), sp2.t0, "XBTUSD")
    r = run_path("fund_test", sp2, 0.75, save=False, btc_funding=run_all.btc_funding_from(fund))
    assert r["btc_funding_modelled"] and r["btc_funding_stamps"] > 500
    assert r["btc_funding_total"] == pytest.approx(
        r["btc_funding_by_leg"]["pullback"] + r["btc_funding_by_leg"]["trend"], abs=0.02)
    assert r["btc_funding_total"] == pytest.approx(-2_820.12, abs=1.0)   # the verifier's T7
    assert r["btc_funding_by_leg"]["trend"] == pytest.approx(-2_272.81, abs=1.0)
    assert sum(t["pnl"] for t in r["trades"]) == pytest.approx(r["equity_btc"][-1] - 70_000.0, abs=0.05)


# (ix) the S3 seam variants change only the pullback leg at the seam (SERIOUS/MINOR)
def test_seam_variants_pullback_only(real):
    sp = build_spliced("btcusd", "2020-02-13", now=NOW)
    t0 = sp.t0
    csv = stress.engine_trades(sp, "csv")
    pl = stress.engine_trades(sp, "pending_live")
    ds = stress.engine_trades(sp, "drop_seam")
    assert stress.engine_trades(sp) == csv
    assert csv["trend"] == pl["trend"] == ds["trend"]
    seam = [t for t in csv["pullback"] if t.entry_ts < t0 and (t.exit_ts is None or t.exit_ts >= t0)]
    assert len(seam) == 1 and seam[0].entry_price == pytest.approx(84_121.28, abs=0.005)
    assert seam[0].entry_ts == 1_791_345_600            # the CSV's 04:00Z fill
    # drop_seam: exactly that trade removed, everything else kept in order
    assert ds["pullback"] == [t for t in csv["pullback"] if t is not seam[0]]
    # pending_live: no pullback trade spans the seam; history before it is the
    # CSV's; the first path trade is the live limit (the 08:00Z close), long
    hist = lambda d: [t for t in d["pullback"] if t.exit_ts is not None and t.exit_ts < t0]  # noqa: E731
    assert hist(pl) == hist(csv)
    live = [t for t in pl["pullback"] if t.exit_ts is None or t.exit_ts >= t0]
    assert live and all(t.entry_ts >= t0 for t in live)
    assert live[0].side == "L" and live[0].entry_price == pytest.approx(real[-1].close, abs=0.005)
    assert live[0].entry_price == pytest.approx(83_706.22, abs=0.005)
    with pytest.raises(ValueError):
        stress.engine_trades(sp, "flat")
    r = run_path("seam_test", sp, 0.75, save=False, seam_variant="pending_live")
    assert r["seam_variant"] == "pending_live"
    assert r["published_trades"]["pullback"][0]["entry_price"] == pytest.approx(83_706.22, abs=0.005)


# (x) the paper book reports its margin to the halt line (knife-edge) -----------
def test_paper_book_margin_to_line(real):
    t0 = real[-1].ts + BAR
    px = real[-1].close
    line0 = 0.7 * 107_860.0
    _, info0 = paper_book([], t0, PAPER_SEED["pullback"])
    assert info0["line_seed"] == pytest.approx(line0, abs=0.01)
    assert info0["min_margin"] == pytest.approx(104_840.0 - line0, abs=0.01)
    assert info0["margin_at_halt"] is None and info0["line_at_halt"] is None
    # -20% loser: no halt; the closest approach is after that trade
    t1 = Trade("pullback", "L", t0, px, t0 + 10 * BAR, px * 0.8, "STOP")
    qty = round(104_840.0 / px, 6)
    eq1 = 104_840.0 + qty * (px * 0.8 - px) - qty * px * 12 / 1e4
    _, info1 = paper_book([t1], t0, PAPER_SEED["pullback"])
    assert not info1["halted"]
    assert info1["min_margin"] == pytest.approx(eq1 - line0, abs=0.01) and info1["min_margin"] > 0
    assert info1["min_margin_date"] == stress._date(t1.exit_ts)
    assert info1["min_equity"] == pytest.approx(eq1, abs=0.01)
    # -36% loser: halts; the margin is negative and equals equity - line
    t2 = Trade("pullback", "L", t0, px, t0 + 10 * BAR, px * 0.64, "STOP")
    eq2 = 104_840.0 + qty * (px * 0.64 - px) - qty * px * 12 / 1e4
    _, info2 = paper_book([t2], t0, PAPER_SEED["pullback"])
    assert info2["halted"] and info2["line_at_halt"] == pytest.approx(line0, abs=0.01)
    assert info2["margin_at_halt"] == pytest.approx(eq2 - line0, abs=0.01)
    assert info2["margin_at_halt"] < 0
    assert info2["min_margin"] == info2["margin_at_halt"]
    # the live knife-edge: COVID S3 halts 1,016 under its line
    r = run_path("knife", build_spliced("btcusd", "2020-02-13", now=NOW), 0.75, save=False)
    e = r["engine_halts_info"]["pullback"]
    assert e["halted"] and e["halt_date"] == "2026-11-30 04:00"
    assert e["margin_at_halt"] == pytest.approx(-1_015.55, abs=0.5)
    assert e["line_at_halt"] == pytest.approx(75_502.0, abs=0.01)


# (xi) intrabar worst day and rail consumption (MINOR) -------------------------
def test_worst_day_intrabar_and_rail_use(real):
    c0 = real[-1].close

    def ohlc(j, prev, c):
        if j == 5:                                     # a -12% wick that closes flat
            return prev, prev, prev * 0.88, c
        return prev, max(prev, c), min(prev, c), c
    sp = synthetic_path([c0] * 12, now=NOW, ohlc_fn=ohlc)
    assert sp[sp.seam + 5].ts % DAY != 0               # not a rollover bar
    trades = _synthetic_longs(sp, 40)
    ex = run_executor(sp, trades, 0.75)
    assert ex.halts == [] and ex.trades[0]["size_mult"] == 1.0 if ex.trades else True
    gross = sum(p.qty for p in ex.pos.values()) * c0
    assert gross == pytest.approx(112_500.0, abs=0.01)
    c2c = stress.worst_day(ex.ts_out, ex.eq_tot_out, 100_000.0)
    wdi = stress.worst_day_intrabar(ex.ts_out, ex.worst_intrabar_out, ex.day_start_out,
                                    ex.armed_out)
    assert c2c["usd"] > -100                           # close-to-close sees only fees
    assert wdi["usd"] == pytest.approx(-0.12 * 112_500.0, abs=0.01)   # the executor's reading
    assert wdi["date"] == stress._day(sp[sp.seam + 5].ts)
    assert wdi["from_equity"] == pytest.approx(ex.day_start_out[5], abs=1e-6)
    ru = stress.rail_use(ex.ts_out, ex.margin_day_out, ex.margin_dd_out, ex.armed_out, ex.dpct)
    assert ru["daily_loss"]["budget"] == pytest.approx(15_000.0)
    assert ru["daily_loss"]["min_margin"] == pytest.approx(15_000.0 - 13_500.0, abs=0.01)
    assert ru["daily_loss"]["used_pct"] == pytest.approx(0.90, abs=1e-6)
    assert ru["daily_loss"]["date"] == stress._date(sp[sp.seam + 5].ts)
    fees = sum(p.efee for p in ex.pos.values())
    assert ru["drawdown"]["min_margin"] == pytest.approx(100_000.0 - fees - 13_500.0 - 70_000.0, abs=0.01)
    assert ru["drawdown"]["used_pct"] == pytest.approx((13_500.0 + fees) / 30_000.0, abs=1e-4)  # 4 dp
    # K 0.30: 6,000 budget, 45,000 gross -> -5,400 at the wick = 90% used, no halt
    ex3 = run_executor(sp, trades, 0.30)
    ru3 = stress.rail_use(ex3.ts_out, ex3.margin_day_out, ex3.margin_dd_out, ex3.armed_out, ex3.dpct)
    assert ex3.halts == [] and ru3["daily_loss"]["used_pct"] == pytest.approx(0.90, abs=1e-6)
    # disarmed bars are skipped: a 13% wick halts; the halting bar still counts
    def ohlc2(j, prev, c):
        if j == 5:
            return prev, prev, prev * 0.86, c
        return prev, max(prev, c), min(prev, c), c
    sp2 = synthetic_path([c0] * 12, now=NOW, ohlc_fn=ohlc2)
    ex2 = run_executor(sp2, _synthetic_longs(sp2, 40), 0.75)
    assert ex2.halts and ex2.halts[0]["kind"] == "DAILY_LOSS"
    assert ex2.armed_out[5] is True and ex2.armed_out[6] is False
    ru2 = stress.rail_use(ex2.ts_out, ex2.margin_day_out, ex2.margin_dd_out, ex2.armed_out, ex2.dpct)
    assert ru2["daily_loss"]["min_margin"] <= 0 and ru2["daily_loss"]["date"] == stress._date(sp2[sp2.seam + 5].ts)
    r = run_path("wd_test", build_spliced("btcusd", "2020-02-13", now=NOW), 0.30, save=False)
    assert r["worst_day_intrabar"]["usd"] <= 0 and 0 < r["rail_use"]["daily_loss"]["used_pct"] < 1
    assert len(r["margin_daily"]) == len(r["ts"]) == len(r["rails_armed"])


# (xii) the 365-day balance says whether the bar is exact (NOTE) ---------------
def test_balances_exact_flag():
    sp_c = build_spliced("btcusd", "2020-02-13", now=NOW)      # leap-year window: 2,196 bars
    sp_8 = build_spliced("btcusd", "2021-11-09", now=NOW)      # 365-day window: 2,190 bars
    # exactness is judged on the bar's CLOSE (ts + BAR == target; re-verification
    # 2026-10-07): the 365-day window's last bar closes ON day 365 (exact); the
    # COVID window's day-365 balance is the bar OPENING on that instant, which
    # closes 4h after it (shortfall_s = target - close < 0)
    for sp, exact in ((sp_c, False), (sp_8, True)):
        ts = [b.ts for b in sp.path]
        b = stress.balances_at(ts, [1.0] * len(ts), sp.t0)
        assert b["365"]["exact"] is exact
        assert b["365"]["shortfall_s"] == (0 if exact else -BAR)
        assert b["365"]["ts"] + BAR + b["365"]["shortfall_s"] == sp.t0 + 365 * 86400
        # every 91-day balance is the bar opening on day 91: its close is 4h after
        assert b["91"]["exact"] is False and b["91"]["shortfall_s"] == -BAR
    assert len(sp_8.path) == 2190 and len(sp_c.path) == 2196
