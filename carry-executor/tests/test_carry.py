"""Gate tests for the ETH carry sleeve (app/carry.py). No network.

Merge-blocking semantics:
  - DRY_RUN sends nothing; a fresh deploy (notional 0) never opens.
  - Open: spot first, then the perp hedges what spot ACTUALLY filled.
  - Close: spot sold first, the short bought back reduce-only to match.
  - A stale / unknown / malformed decision HOLDS: no open, no close.
  - Repo cap, kill switch (CARRY_ENABLED=false unwinds), margin guard.
  - Adopt-not-double-buy after a lost state file; month-start re-size.
  - Venue errors never send orders; persistent hedge gaps page.
"""
import json
import time

import pytest

from app import carry as C

NOW = 1_790_000_000.0          # 2026-09-21-ish, a fixed clock


class Cfg:
    dry_run = False
    carry_enabled = True
    perp_coin = "ETH"
    spot_token = "UETH"
    carry_notional_usd = 30_000.0
    max_slip_bps = 15.0
    resize_drift = 0.25
    cross_leverage = 5
    liq_buffer = 0.15


class FakeVenue:
    def __init__(self, px=4000.0):
        self.spot_qty = 0.0
        self.spot_hold = 0.0
        self.perp_qty = 0.0
        self.spot_mid = px
        self.perp_mid = px
        self.liq_px = None
        self.fill = {"spot": 1.0, "perp": 1.0}     # fraction filled per IOC
        self.calls: list[tuple] = []
        self.read_fail = 0
        self.order_fail = None
        self.cross_calls = 0

    def read(self):
        if self.read_fail:
            self.read_fail -= 1
            raise RuntimeError("info down")
        return {"spot_qty": self.spot_qty, "spot_hold": self.spot_hold,
                "usdc": 70_000.0, "perp_qty": self.perp_qty,
                "liq_px": self.liq_px, "perp_mid": self.perp_mid,
                "spot_mid": self.spot_mid}

    def ensure_cross(self, lev):
        self.cross_calls += 1

    def ioc(self, market, is_buy, qty, ref_px, slip_bps, reduce_only=False):
        self.calls.append((market, "BUY" if is_buy else "SELL", round(qty, 6),
                           reduce_only))
        if self.order_fail:
            raise RuntimeError(self.order_fail)
        q = round(qty * self.fill[market], 4)
        sgn = 1 if is_buy else -1
        if market == "spot":
            self.spot_qty = round(self.spot_qty + sgn * q, 8)
        else:
            self.perp_qty = round(self.perp_qty + sgn * q, 8)
        return {"filled": q, "avg_px": ref_px}


def target(armed=True, known=True, age=600, **kw):
    t = {"venue": "HL_ETH", "coin": "ETH", "armed": armed, "known": known,
         "mean_ann_pct": 9.1, "coverage": 1.0, "last_checked": NOW - age,
         "check_seconds": 21_600, "arm_pct": 8.0, "disarm_pct": 5.0}
    t.update(kw)
    return t


@pytest.fixture
def mk(tmp_path):
    def _mk(venue=None, clock=NOW, sub="", **cfg):
        c = Cfg()
        for k, v in cfg.items():
            setattr(c, k, v)
        v = venue or FakeVenue()
        sent = []
        ex = C.CarryExecutor(v, c, str(tmp_path / sub / "state.json"),
                             alert_fn=sent.append, clock=lambda: clock)
        ex.sent = sent
        return ex, v
    return _mk


def kinds(ex, level=None):
    return [e["kind"] for e in ex.state.events if level is None or e["level"] == level]


# ---------------------------------------------------------------- open / close

def test_open_buys_spot_then_hedges_the_filled_quantity(mk):
    ex, v = mk()
    ex.step(target())
    q = 30_000 / 4000.0
    assert v.calls[0] == ("spot", "BUY", q, False)
    assert v.calls[1] == ("perp", "SELL", q, False)
    assert v.spot_qty == pytest.approx(q) and v.perp_qty == pytest.approx(-q)
    assert v.cross_calls == 1                      # cross margin before the short
    assert ex.state.on and "opened" in kinds(ex)
    assert any("carry opened" in m for m in ex.sent)


def test_partial_spot_fill_never_leaves_a_naked_short(mk):
    v = FakeVenue()
    v.fill["spot"] = 0.4
    ex, v = mk(v)
    ex.step(target())
    assert v.perp_qty == pytest.approx(-v.spot_qty)   # hedged what filled
    assert v.spot_qty == pytest.approx(0.4 * 7.5)
    v.fill["spot"] = 1.0
    ex.step(target())                                  # tops both legs up
    assert v.spot_qty == pytest.approx(7.5) and v.perp_qty == pytest.approx(-7.5)


def test_disarm_sells_spot_first_and_buys_back_reduce_only(mk):
    ex, v = mk()
    ex.step(target())
    n = len(v.calls)
    ex.step(target(armed=False))
    assert v.calls[n] == ("spot", "SELL", 7.5, False)
    assert v.calls[n + 1] == ("perp", "BUY", 7.5, True)
    assert v.spot_qty == 0 and v.perp_qty == 0
    assert not ex.state.on and "closed" in kinds(ex)


def test_partial_spot_sale_buys_back_only_the_matching_short(mk):
    ex, v = mk()
    ex.step(target())
    v.fill["spot"] = 0.5
    ex.step(target(armed=False))
    assert v.perp_qty == pytest.approx(-v.spot_qty)
    assert v.spot_qty == pytest.approx(3.75)


def test_never_opens_a_perp_position_without_spot(mk):
    ex, v = mk()
    ex.step(target(armed=False))
    assert v.calls == []


# ---------------------------------------------------------------- the decision

@pytest.mark.parametrize("t", [None, "junk", {"venue": "HL", "coin": "ETH"},
                               target(known=False), target(armed="yes"),
                               target(age=60_000), target(last_checked=None),
                               target(coin="BTC")])
def test_unusable_signal_never_opens(mk, t):
    ex, v = mk()
    ex.step(t)
    assert v.calls == []
    assert "signal_unusable" in kinds(ex, "RED")


def test_unusable_signal_never_closes_a_hedged_sleeve(mk):
    ex, v = mk()
    ex.step(target())
    n = len(v.calls)
    for t in (None, target(age=60_000), target(known=False)):
        ex.step(t)
    assert len(v.calls) == n and v.spot_qty == pytest.approx(7.5)


def test_signal_age_limit_is_two_checks_plus_grace(mk):
    ex, v = mk()
    ex.step(target(age=2 * 21_600 + C.SIGNAL_GRACE_S - 5))
    assert v.calls                                  # still fresh enough
    ex2, v2 = mk(FakeVenue(), sub="b")
    ex2.step(target(age=2 * 21_600 + C.SIGNAL_GRACE_S + 5))
    assert v2.calls == []


def test_hold_never_rebuys_a_sleeve_the_account_no_longer_holds(mk):
    """Found by the suite: state says ON, the venue is empty (closed by hand,
    or liquidated), the signal is stale. HOLD must hold the venue - it
    re-bought the whole sleeve."""
    ex, v = mk()
    ex.step(target())
    v.spot_qty = v.perp_qty = 0.0
    n = len(v.calls)
    ex.step(target(age=60_000))
    assert len(v.calls) == n


def test_hold_still_repairs_the_hedge(mk):
    ex, v = mk()
    ex.step(target())
    v.perp_qty = -5.0                               # short shrank (partial close)
    ex.step(None)
    assert v.perp_qty == pytest.approx(-7.5) and v.spot_qty == pytest.approx(7.5)


def test_kill_switch_works_without_the_engine(mk):
    ex, v = mk()
    ex.step(target())
    ex.cfg.carry_enabled = False
    ex.step(None)
    assert v.spot_qty == 0 and v.perp_qty == 0


# ---------------------------------------------------------------- safety rails

def test_dry_run_sends_nothing_and_says_what_it_would_do(mk):
    ex, v = mk(dry_run=True)
    ex.step(target())
    ex.step(target())
    assert v.calls == [] and v.cross_calls == 0
    intents = [e for e in ex.state.events if e["kind"] == "dry_run_intent"]
    assert len(intents) == 1 and "spot BUY 7.5000" in intents[0]["msg"]
    assert not ex.state.on


def test_fresh_deploy_without_a_notional_never_opens(mk):
    ex, v = mk(carry_notional_usd=0.0)
    ex.step(target())
    assert v.calls == []


def test_repo_cap_bounds_the_env(mk):
    ex, v = mk(carry_notional_usd=500_000.0)
    ex.step(target())
    assert v.calls[0][2] == pytest.approx(C.CARRY_MAX_NOTIONAL_USD / 4000.0)
    assert "notional_over_cap" in kinds(ex, "RED")
    assert C.CARRY_MAX_NOTIONAL_USD == 50_000.0      # the number is reviewed


def test_kill_switch_unwinds_and_stays_flat(mk):
    ex, v = mk()
    ex.step(target())
    ex.cfg.carry_enabled = False
    ex.step(target())
    ex.step(target())
    assert v.spot_qty == 0 and v.perp_qty == 0 and not ex.state.on


def test_margin_guard_unwinds_near_liquidation(mk):
    ex, v = mk()
    ex.step(target())
    v.liq_px = 4500.0
    v.perp_mid = v.spot_mid = 3900.0                # 13% below liq: inside 15%
    ex.step(target())
    assert v.spot_qty == 0 and v.perp_qty == 0
    assert "margin_guard" in kinds(ex, "RED")


def test_halted_sends_nothing(mk):
    ex, v = mk()
    ex.halt("test")
    ex.step(target())
    assert v.calls == []
    ex.resume()
    ex.step(target())
    assert v.calls


def test_venue_read_failure_sends_nothing_and_pages_after_three(mk):
    v = FakeVenue()
    v.read_fail = 3
    ex, v = mk(v)
    for _ in range(3):
        ex.step(target())
    assert v.calls == []
    assert "venue_unreadable" in kinds(ex, "RED")


def test_order_failure_is_recorded_and_the_next_pass_repairs(mk):
    v = FakeVenue()
    ex, v = mk(v)
    v.order_fail = "rate limited"
    ex.step(target())
    assert "step_error" in kinds(ex, "RED")
    v.order_fail = None
    ex.step(target())
    assert v.spot_qty == pytest.approx(7.5) and v.perp_qty == pytest.approx(-7.5)


def test_a_persistent_hedge_gap_pages(mk):
    v = FakeVenue()
    v.fill["perp"] = 0.0                            # the short never fills
    ex, v = mk(v)
    ex.step(target())
    assert "unhedged" not in kinds(ex, "RED")
    ex.step(target())
    assert "unhedged" in kinds(ex, "RED")


# ---------------------------------------------------------------- lifecycle

def test_lost_state_file_adopts_the_sleeve_instead_of_buying_more(mk):
    v = FakeVenue()
    v.spot_qty, v.perp_qty = 7.5, -7.5
    ex, v = mk(v)                                   # fresh state, sleeve exists
    ex.step(target())
    assert v.calls == [] and ex.state.on
    assert ex.state.target_qty == pytest.approx(7.5)


def test_month_start_resize_only_beyond_the_drift(mk, tmp_path):
    ex, v = mk()
    ex.step(target())
    assert ex.state.last_resize_month
    # same month, big price move: no resize
    v.spot_mid = v.perp_mid = 6000.0
    ex.step(target())
    assert v.spot_qty == pytest.approx(7.5)
    # next month: 7.5 x 6000 = 45k vs 30k target -> +50% drift -> resize to 5.0
    ex.clock = lambda: NOW + 40 * 86400
    ex.step(target(last_checked=NOW + 40 * 86400 - 600))
    assert v.spot_qty == pytest.approx(5.0) and v.perp_qty == pytest.approx(-5.0)
    assert "resized" in kinds(ex)
    # following month, inside the drift band: no change
    v.spot_mid = v.perp_mid = 6600.0                # 5 x 6600 = 33k, +10%
    ex.clock = lambda: NOW + 75 * 86400
    n = len(v.calls)
    ex.step(target(last_checked=NOW + 75 * 86400 - 600))
    assert len(v.calls) == n


def test_state_survives_a_restart(mk, tmp_path):
    ex, v = mk()
    ex.step(target())
    raw = json.load(open(tmp_path / "state.json"))
    assert raw["on"] is True and raw["target_qty"] == pytest.approx(7.5)
    ex2, _ = mk(v)
    assert ex2.state.on and ex2.state.target_qty == pytest.approx(7.5)


def test_unreadable_state_file_starts_halted(mk, tmp_path):
    (tmp_path / "state.json").write_text("{not json")
    ex, v = mk()
    assert ex.state.halted == "STATE_UNREADABLE"
    ex.step(target())
    assert v.calls == []


def test_pulse_shape(mk):
    ex, v = mk()
    ex.step(target())
    p = ex.pulse()
    assert p["on"] is True and p["hedge_gap_usd"] == 0
    assert set(p) >= {"dry_run", "enabled", "halted", "spot_qty", "perp_qty",
                      "signal", "last_step_ts", "red_kinds_24h"}
