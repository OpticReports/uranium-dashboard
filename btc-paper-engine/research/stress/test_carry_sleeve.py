"""Gate tests for research/stress/carry_sleeve.py. Every expectation is
computed independently of the module (hand loops, the liq formula written
out, fees from first principles). Run: python3 -m pytest -q test_carry_sleeve.py"""
from __future__ import annotations

import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from carry_sleeve import (BAR_S, CarryResult, liq_px_short,   # noqa: E402
                          simulate_carry)

T0 = 1704067200                      # 2024-01-01 00:00 UTC (Monday)
H = 3600
D = 86400
NOTIONAL = 30000.0
USDC = 70000.0
FEE_RATE = (7.0 + 4.5) / 1e4         # both legs, one way
R10 = 0.10 / 1095                    # 8h rate for +10 %/yr
R6 = 0.06 / 1095


def grid(n_bars: int, px_fn) -> dict[int, float]:
    """4h grid from T0; px_fn(day_float) -> close."""
    return {T0 + i * BAR_S: float(px_fn((i * BAR_S + BAR_S) / D)) for i in range(n_bars)}


def funding(n_days: int, rate_fn) -> dict[int, float]:
    """BitMEX-style stamps at 04/12/20 UTC for n_days from T0;
    rate_fn(day_float) -> raw 8h rate."""
    out = {}
    for d in range(n_days):
        for h in (4, 12, 20):
            s = T0 + d * D + h * H
            out[s * 1000] = float(rate_fn((s - T0) / D))
    return out


def gate_path(fund: dict[int, float], n_bars: int, arm=8.0, disarm=5.0):
    """Independent re-derivation of the gate: (armed after each eval) list of
    (E, mean, cov, armed). Starts armed."""
    stamps = sorted((k // 1000, v * 1095 * 100) for k, v in fund.items())
    armed = True
    out = []
    end = T0 + n_bars * BAR_S
    E = T0
    while E < end:
        vals = [a for s, a in stamps if E - 30 * D <= s <= E]
        cov = len(vals) / 90
        mean = sum(vals) / len(vals) if vals else None
        if mean is not None and cov >= 0.5:
            if not armed and mean >= arm - 1e-9:
                armed = True
            elif armed and mean < disarm - 1e-9:
                armed = False
        out.append((E, mean, cov, armed))
        E += 6 * H
    return out


def bar_after(E: int, ts: list[int]) -> int:
    """index of the bar whose close is the first close strictly after E."""
    for i, t in enumerate(ts):
        if t <= E < t + BAR_S:
            return i
    raise AssertionError("no bar")


# --------------------------------------------------------------------------
def test_i_constant_funding_flat_price_pays_qty_px_rate_per_stamp():
    n_bars = 30 * 6
    closes = grid(n_bars, lambda d: 2000.0)
    fund = funding(30, lambda d: R10)
    r = simulate_carry(closes, fund, {"on": False}, notional=NOTIONAL, usdc_backing=USDC)
    assert isinstance(r, CarryResult)
    qty = NOTIONAL / 2000.0
    per_stamp = qty * 2000.0 * R10                 # == 30000 x 0.10 / 1095
    open_fee = NOTIONAL * FEE_RATE                 # 34.50
    # opened at the first close (gate armed from the start), funding from that stamp on
    assert r.on[0] is True and all(r.on)
    assert r.events[0][1] == "gate_on" and r.events[0][0] == T0
    # 90 stamps, each to the cent
    inc = [r.funding_cum[0]] + [r.funding_cum[i] - r.funding_cum[i - 1] for i in range(1, n_bars)]
    paid = [x for x in inc if x != 0.0]
    assert len(paid) == 90
    assert all(abs(x - per_stamp) < 0.005 for x in paid)
    assert abs(r.funding_cum[-1] - 90 * per_stamp) < 0.005
    # fees only on the open: one fee, never again
    assert abs(r.fees_cum[0] - open_fee) < 1e-9
    assert all(abs(f - open_fee) < 1e-9 for f in r.fees_cum)
    assert abs(r.value[-1] - (NOTIONAL - open_fee + 90 * per_stamp)) < 0.005
    # price P&L cancels: value == cash + qty*entry, i.e. value - funding + fees == notional
    assert all(abs(v - fc + fe - NOTIONAL) < 1e-6
               for v, fc, fe in zip(r.value, r.funding_cum, r.fees_cum))
    # value starts at notional (live start, first bar, before any funding)
    r2 = simulate_carry(closes, {}, {"on": True, "qty": 11.096, "entry_px": 2703.9})
    assert abs(r2.value[0] - NOTIONAL) < 1e-9 and r2.fees_cum[0] == 0.0


def test_ii_funding_below_5pct_turns_off_at_next_bar_and_value_freezes():
    n_days = 70
    n_bars = n_days * 6
    closes = grid(n_bars, lambda d: 2000.0)
    fund = funding(n_days, lambda d: R10 if d < 30 else 0.0)
    r = simulate_carry(closes, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0},
                       notional=NOTIONAL, usdc_backing=USDC)
    path = gate_path(fund, n_bars)
    E_off = next(E for E, m, c, a in path if not a)
    i_off = bar_after(E_off, r.ts)
    assert 40 < (E_off - T0) / D < 50          # sanity: mid-window crossing
    assert r.on[i_off - 1] is True and r.on[i_off] is False
    offs = [e for e in r.events if e[1] == "gate_off"]
    assert len(offs) == 1 and offs[0][0] == r.ts[i_off]
    assert [e[1] for e in r.events] == ["gate_off"]
    # close fee on the unwind, both legs
    assert abs(r.fees_cum[i_off] - 15.0 * 2000.0 * FEE_RATE) < 1e-9
    # value stops moving afterwards
    assert all(abs(v - r.value[i_off]) < 1e-9 for v in r.value[i_off:])
    assert all(abs(f - r.funding_cum[i_off]) < 1e-9 for f in r.funding_cum[i_off:])
    assert all(math.isnan(x) for x in r.liq_px[i_off:])
    # the gate reading the module used matches the hand loop at that eval
    m_hand = next(m for E, m, c, a in path if E == E_off)
    assert abs(r.gate_mean[i_off] - m_hand) < 1e-9 and m_hand < 5.0


def test_iii_hysteresis_6pct_stays_off_10pct_turns_on():
    # 30d @10 -> 30d @0 (off ~day 45) -> 40d @6 (mean climbs to 6: must stay
    # OFF) -> 40d @10 (mean crosses 8 -> ON)
    n_days = 140
    n_bars = n_days * 6
    closes = grid(n_bars, lambda d: 2000.0)

    def rate(d):
        if d < 30:
            return R10
        if d < 60:
            return 0.0
        if d < 100:
            return R6
        return R10
    fund = funding(n_days, rate)
    r = simulate_carry(closes, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0})
    kinds = [e[1] for e in r.events]
    assert kinds == ["gate_off", "gate_on"], kinds
    path = gate_path(fund, n_bars)
    E_off = next(E for E, m, c, a in path if not a)
    E_on = next(E for E, m, c, a in path if E > E_off and a)
    assert r.events[0][0] == r.ts[bar_after(E_off, r.ts)]
    assert r.events[1][0] == r.ts[bar_after(E_on, r.ts)]
    # the 6% phase really produced readings in [5, 8) while off, and no re-arm
    i6_lo, i6_hi = 60 * 6, 100 * 6
    seen = [g for g in r.gate_mean[i6_lo:i6_hi] if not math.isnan(g)]
    assert max(seen) > 5.9 and max(seen) < 8.0
    assert not any(r.on[i6_lo:i6_hi])
    # re-armed only once the mean reached 8
    assert r.gate_mean[bar_after(E_on, r.ts)] >= 8.0 - 1e-9
    assert (E_on - T0) / D > 100
    # re-open fee at the open price, size notional/px
    i_on = bar_after(E_on, r.ts)
    assert abs(r.qty[i_on] - NOTIONAL / 2000.0) < 1e-12
    assert abs((r.fees_cum[i_on] - r.fees_cum[i_on - 1]) - NOTIONAL * FEE_RATE) < 1e-9


def test_iv_liq_px_formula_and_margin_guard():
    # live-like start, flat 2000 for 2 days, then the price doubles to 4000
    # (does NOT fire: 4000 < 0.85 x liq), then 5600 (fires), 24h latch, re-open
    n_days = 8
    n_bars = n_days * 6

    def px(d):
        if d <= 2:
            return 2000.0
        if d <= 4:
            return 4000.0
        return 5600.0
    closes = grid(n_bars, px)
    fund = funding(n_days, lambda d: R10)
    r = simulate_carry(closes, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0},
                       notional=NOTIONAL, usdc_backing=USDC)
    liq0 = (USDC / 15.0 + 2000.0) / 1.02
    assert abs(liq0 - 6535.947) < 0.01
    assert abs(liq_px_short(USDC, 15.0, 2000.0) - liq0) < 1e-9
    # bar 0: usdc moved only by the 04:00 funding payment (2.74 -> liq +0.18)
    pay0 = 15.0 * 2000.0 * R10
    assert abs(r.usdc_eff[0] - (USDC + pay0)) < 1e-9
    assert abs(r.liq_px[0] - (r.usdc_eff[0] / 15.0 + 2000.0) / 1.02) < 1e-9
    assert abs(r.liq_px[0] - ((USDC + pay0) / 15.0 + 2000.0) / 1.02) < 1e-9
    assert abs(r.liq_px[0] - liq0) < 0.2
    # doubled price: formula unchanged (price is not an input), no fire
    i_dbl = next(i for i, t in enumerate(r.ts) if closes[t] == 4000.0)
    assert r.on[i_dbl] is True
    assert abs(r.liq_px[i_dbl] - (r.usdc_eff[i_dbl] / r.qty[i_dbl] + r.entry_px[i_dbl]) / 1.02) < 1e-9
    assert 4000.0 < 0.85 * r.liq_px[i_dbl]
    # 5600 >= 0.85 x liq -> guard fires at THAT bar's close
    i_fire = next(i for i, t in enumerate(r.ts) if closes[t] == 5600.0)
    assert 5600.0 >= 0.85 * r.liq_px[i_fire - 1]
    guards = [e for e in r.events if e[1] == "margin_guard"]
    assert len(guards) == 1 and guards[0][0] == r.ts[i_fire]
    assert r.on[i_fire - 1] is True and r.on[i_fire] is False
    # unwind fee on both legs at 5600, and the USDC path: +30k back (spot sale
    # 84k, perp realised -54k) less fees
    unwind_fee = 15.0 * 5600.0 * FEE_RATE
    assert abs((r.fees_cum[i_fire] - r.fees_cum[i_fire - 1]) - unwind_fee) < 1e-9
    assert abs(r.usdc_eff[i_fire] - (r.usdc_eff[i_fire - 1] + 30000.0 - unwind_fee)) < 1e-6
    # value unchanged by the price move: only fees and funding
    assert abs(r.value[i_fire] - (NOTIONAL + r.funding_cum[i_fire] - r.fees_cum[i_fire])) < 1e-6
    # 24h latch: flat for 6 bars though the gate is armed, re-open on the 6th close
    assert all(r.armed[i_fire:i_fire + 7])
    assert not any(r.on[i_fire:i_fire + 6])
    assert r.on[i_fire + 6] is True
    reopen = [e for e in r.events if e[1] == "gate_on"]
    assert len(reopen) == 1 and reopen[0][0] == r.ts[i_fire + 6]
    assert "re-open" in reopen[0][2]["note"]
    assert abs(r.qty[i_fire + 6] - NOTIONAL / 5600.0) < 1e-12
    assert abs(r.entry_px[i_fire + 6] - 5600.0) < 1e-9
    # new liq from the formula with the new entry; far from 5600
    assert abs(r.liq_px[i_fire + 6] - (r.usdc_eff[i_fire + 6] / r.qty[i_fire + 6] + 5600.0) / 1.02) < 1e-9
    assert r.liq_px[i_fire + 6] * 0.85 > 5600.0 * 2

    # a doubling followed by the monthly resize MOVES liq by the formula:
    # qty halves, the realised perp loss leaves USDC
    n_days2 = 40
    closes2 = grid(n_days2 * 6, lambda d: 2000.0 if d <= 20 else 4000.0)
    fund2 = funding(n_days2, lambda d: R10)
    r2 = simulate_carry(closes2, fund2, {"on": True, "qty": 15.0, "entry_px": 2000.0},
                        notional=NOTIONAL, usdc_backing=USDC)
    rs = [e for e in r2.events if e[1] == "resize"]
    assert len(rs) == 1
    i_rs = r2.ts.index(rs[0][0])
    assert abs(r2.qty[i_rs] - 7.5) < 1e-12 and abs(r2.entry_px[i_rs] - 2000.0) < 1e-9
    resize_fee = 7.5 * 4000.0 * FEE_RATE
    usdc_expected = r2.usdc_eff[i_rs - 1] + 7.5 * 4000.0 - 7.5 * 2000.0 - resize_fee + (
        r2.funding_cum[i_rs] - r2.funding_cum[i_rs - 1])
    assert abs(r2.usdc_eff[i_rs] - usdc_expected) < 1e-6
    liq_expected = (usdc_expected / 7.5 + 2000.0) / 1.02
    assert abs(r2.liq_px[i_rs] - liq_expected) < 1e-6
    # fully by hand, no module state: USDC = 70k + 30k spot sale - 15k perp
    # realised + all funding received - all fees paid; qty 7.5 from 2000
    liq_hand = ((USDC + 30000.0 - 15000.0 + r2.funding_cum[i_rs] - r2.fees_cum[i_rs]) / 7.5
                + 2000.0) / 1.02
    assert abs(r2.liq_px[i_rs] - liq_hand) < 1e-6
    assert 13000.0 < liq_hand < 13200.0 and r2.liq_px[i_rs] > r2.liq_px[i_rs - 1] * 1.9
    assert not any(e[1] == "margin_guard" for e in r2.events)


def test_v_monthly_resize_only_beyond_25pct_drift():
    # Jan flat 2000; +20% (2400) into Feb 1 -> no resize; +30% (2600) into
    # Mar 1 -> resize at the first bar of March
    n_days = 31 + 29 + 5                     # 2024 is a leap year
    n_bars = n_days * 6
    feb1 = T0 + 31 * D
    mar1 = feb1 + 29 * D

    def px(d):
        t = T0 + d * D
        if t <= T0 + 20 * D:
            return 2000.0
        if t <= feb1 + 20 * D:
            return 2400.0
        return 2600.0
    closes = grid(n_bars, px)
    fund = funding(n_days, lambda d: R10)
    r = simulate_carry(closes, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0},
                       notional=NOTIONAL, usdc_backing=USDC)
    assert all(r.on) and all(r.armed)
    rs = [e for e in r.events if e[1] == "resize"]
    assert len(rs) == 1 and rs[0][0] == mar1
    assert [e[1] for e in r.events] == ["resize"]
    i_feb = r.ts.index(feb1)
    assert abs(r.qty[i_feb] - 15.0) < 1e-12            # 20% drift: untouched
    assert abs(15.0 * 2400.0 / NOTIONAL - 1.0 - 0.20) < 1e-12
    i_mar = r.ts.index(mar1)
    assert abs(r.qty[i_mar - 1] - 15.0) < 1e-12
    assert abs(r.qty[i_mar] - NOTIONAL / 2600.0) < 1e-12
    dq = 15.0 - NOTIONAL / 2600.0
    assert abs((r.fees_cum[i_mar] - r.fees_cum[i_mar - 1]) - dq * 2600.0 * FEE_RATE) < 1e-9
    assert abs(rs[0][2]["drift"] - 0.30) < 1e-12
    # value still == notional + funding - fees (price P&L cancelled through the resize)
    assert all(abs(v - fc + fe - NOTIONAL) < 1e-6
               for v, fc, fe in zip(r.value, r.funding_cum, r.fees_cum))
    # exactly-25% drift does not fire (strict >)
    closes_b = grid(n_bars, lambda d: 2000.0 if T0 + d * D <= T0 + 20 * D else 2500.0)
    rb = simulate_carry(closes_b, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0})
    assert not any(e[1] == "resize" for e in rb.events)


def test_vi_payment_uses_the_close_at_or_before_the_stamp():
    n_days = 3
    n_bars = n_days * 6
    closes = grid(n_bars, lambda d: 2000.0 + 100.0 * d)   # a new close every bar
    fund = funding(n_days, lambda d: R10)
    r = simulate_carry(closes, fund, {"on": True, "qty": 15.0, "entry_px": 2000.0})
    stamps = sorted(k // 1000 for k in fund)
    exp = 0.0
    j = 0
    for i, t in enumerate(r.ts):
        C = t + BAR_S
        while j < len(stamps) and stamps[j] <= C:
            assert stamps[j] == C                       # 04/12/20 stamps sit on 4h closes
            exp += 15.0 * closes[t] * R10
            j += 1
        assert abs(r.funding_cum[i] - exp) < 1e-9
    assert j == 9
    # a negative rate: the short PAYS
    fund_neg = funding(n_days, lambda d: -R10)
    rn = simulate_carry(closes, fund_neg, {"on": True, "qty": 15.0, "entry_px": 2000.0})
    assert rn.funding_cum[-1] < 0 and abs(rn.funding_cum[-1] + r.funding_cum[-1]) < 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
