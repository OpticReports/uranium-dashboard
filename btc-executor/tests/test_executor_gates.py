"""Executor gates: the mirror state machine against a scripted fake venue.
No network, no Coinbase SDK — pure logic validation."""
import os
import time

import pytest

from app.mirror import Executor, ExecState


class Cfg:
    kelly_m = 0.56
    sizing_base_usd = 0.0
    max_notional_usd = 25_000.0
    max_account_lev = 2.0
    dry_run = True
    daily_loss_halt_pct = 0.06
    dd_halt_pct = 0.25
    stale_bars_max = 2
    drift_tol_frac = 0.02
    stop_replace_bps = 5.0
    stop_limit_offset_pct = 0.5
    state_path = ""


class FakeVenue:
    def __init__(self, equity=10_000.0, mid=60_000.0, mult=None):
        self._equity, self._mid = equity, mid
        self._mult = mult              # None = continuous; 0.01 = CDE nano
        self.orders = {}
        self.calls = []

    def quantize(self, qty):
        if not self._mult:
            return qty
        return int(qty / self._mult + 1e-9) * self._mult

    def equity(self):
        return self._equity

    def position(self):
        net = 0.0
        for o in self.orders.values():
            if o["status"] == "FILLED":
                net += (1 if o["side"] == "BUY" else -1) * o["qty"]
        return net

    def mid(self):
        return self._mid

    def order_status(self, cloid):
        o = self.orders.get(cloid)
        return ({"status": o["status"],
                 "filled_qty": o["qty"] if o["status"] == "FILLED" else
                 o.get("part", 0.0),
                 "avg_price": (o.get("px") or self._mid)
                 if o["status"] == "FILLED" else None} if o else None)

    def _add(self, kind, side, qty, cloid, px=None):
        self.orders[cloid] = {"type": kind, "side": side, "qty": qty,
                              "px": px, "status": "FILLED" if kind == "MARKET"
                              else "OPEN"}
        self.calls.append((kind, side, round(qty, 5), cloid))

    def place_limit(self, side, qty, px, cloid, post_only=True):
        assert post_only, "pullback entries must be maker"
        self._add("LIMIT", side, qty, cloid, px)

    def place_stop(self, side, qty, trigger_px, cloid):
        self._add("STOP", side, qty, cloid, trigger_px)

    def place_market(self, side, qty, cloid):
        self._add("MARKET", side, qty, cloid, px=self._mid)

    def cancel(self, cloid):
        if cloid in self.orders and self.orders[cloid]["status"] == "OPEN":
            self.orders[cloid]["status"] = "CANCELLED"
        self.calls.append(("CANCEL", None, None, cloid))

    def cancel_all(self):
        for o in self.orders.values():
            if o["status"] == "OPEN":
                o["status"] = "CANCELLED"
        self.calls.append(("CANCEL_ALL", None, None, None))


NOW = int(time.time()) // 14_400 * 14_400
BLEND = {"w_trend": 0.25, "lev": 1.5}


def target(pull=None, trend=None, bar_ts=None, degraded=False, data_halt=False):
    return {"bar_ts": bar_ts if bar_ts is not None else NOW,
            "degraded": degraded, "data_halt": data_halt, "blend": BLEND,
            "legs": {"pullback": pull or {"pending": None, "position": None},
                     "trend": trend or {"pending": None, "position": None}}}


def mkexec(tmp_path, venue, dry_run=None):
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    if dry_run is not None:
        # set BEFORE construction: __init__ records the boot mode, so
        # mutating cfg afterwards reads as a real DRY_RUN flip
        cfg.dry_run = dry_run
    return Executor(venue, cfg, cfg.state_path)


def test_gate_pullback_entry_sizing_and_lifecycle(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    kind, side, qty, cloid = v.calls[0]
    assert (kind, side) == ("LIMIT", "BUY") and cloid == f"P-{NOW}-E"
    # 0.56 * 1.5 * 0.75 * 10k / 59k = 0.10678 BTC
    assert qty == pytest.approx(0.56 * 1.5 * 0.75 * 10_000 / 59_000, abs=1e-4)
    # same pending again -> no duplicate order
    ex.step(target(pull=pend))
    assert len([c for c in v.calls if c[0] == "LIMIT"]) == 1
    # engine cancels (flat, no position) -> our order cancelled
    ex.step(target())
    assert v.orders[f"P-{NOW}-E"]["status"] == "CANCELLED"


def test_gate_fill_places_stop_and_exit_closes(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    v.orders[f"P-{NOW}-E"]["status"] = "FILLED"           # limit filled
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))
    stops = [c for c in v.calls if c[0] == "STOP"]
    assert stops and stops[0][1] == "SELL"
    assert ex.state.legs["pullback"].qty > 0
    # no chase happened (order filled exactly)
    assert not [c for c in v.calls if c[0] == "MARKET"]
    # engine exits -> stop cancelled, market close
    ex.step(target())
    assert ex.state.legs["pullback"].qty == 0.0
    mkts = [c for c in v.calls if c[0] == "MARKET"]
    assert mkts and mkts[-1][1] == "SELL"


def test_gate_trend_market_entry_and_trail_ratchet(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "S", "limit": -1.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(trend=pend))
    kind, side, qty, _ = v.calls[0]
    assert (kind, side) == ("MARKET", "SELL")             # trend enters at market
    assert qty == pytest.approx(0.56 * 1.5 * 0.25 * 10_000 / 60_000, abs=1e-4)
    pos = {"pending": None,
           "position": {"side": "S", "entry_price": 60_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 63_000.0, "exit_flag": None}}
    ex.step(target(trend=pos))
    s1 = [c for c in v.calls if c[0] == "STOP"]
    assert len(s1) == 1 and s1[0][1] == "BUY"
    # trail ratchets down -> stop replaced; tiny move -> no churn
    pos["position"]["stop"] = 62_000.0
    ex.step(target(trend=pos))
    assert len([c for c in v.calls if c[0] == "STOP"]) == 2
    pos["position"]["stop"] = 62_001.0                    # < 5bp move
    ex.step(target(trend=pos))
    assert len([c for c in v.calls if c[0] == "STOP"]) == 2


def test_gate_trend_holds_through_repeated_pending(tmp_path):
    """The engine reports `pending` until its own next bar close, but the
    trend leg has already filled at market and carries led.qty. Polling
    again inside that window must be a no-op — the live executor closed the
    position it had just opened (first live trade, 2026-08-10)."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "S", "limit": -1.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(trend=pend))
    qty = ex.state.legs["trend"].qty
    assert qty < 0
    n = len(v.calls)
    for _ in range(3):                                    # same pending again
        ex.step(target(trend=pend))
    assert ex.state.legs["trend"].qty == qty              # still holding
    assert len(v.calls) == n                              # no close, no re-entry
    assert not any(e["kind"] == "leg_closed" for e in ex.state.events)


def test_gate_trend_new_signal_closes_stale_qty(tmp_path):
    """...but a DIFFERENT pending signal still flattens the stale fill."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    ex.step(target(trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": NOW + 14_400},
                          "position": None}))
    assert any(e["kind"] == "leg_closed" for e in ex.state.events)
    assert ex.state.legs["trend"].qty > 0                 # re-entered long
    assert ex.state.legs["trend"].entry_cloid == f"T-{NOW + 14_400}-E"


def test_gate_size_quantized_to_contracts(tmp_path):
    """CDE nano futures fill in whole 0.01-BTC contracts. Sizes must be
    rounded DOWN before ordering so the ledger equals the real position —
    ordering 0.01466 BTC and recording 0.01466 while the venue filled 0.01
    desynchronises every stop and exit that follows (live find, 2026-08-10)."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    kind, side, qty, _ = v.calls[0]
    assert (kind, side) == ("MARKET", "SELL")
    assert qty == pytest.approx(0.03)                     # 0.035 -> 3 contracts
    assert ex.state.legs["trend"].qty == pytest.approx(-0.03)
    assert v.position() == pytest.approx(-0.03)           # ledger == venue


def test_gate_sub_contract_chase_not_sent(tmp_path):
    """A shortfall under one contract is not chaseable. The old code sent it
    and the venue's max(1, ...) floor rounded it up to a FULL contract,
    overshooting the target instead of under-filling it."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "S", "entry_price": 60_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 63_000.0, "exit_flag": None}}
    ex.state.legs["trend"].entry_cloid = f"T-{NOW}-E"
    v.orders[f"T-{NOW}-E"] = {"type": "MARKET", "side": "SELL", "qty": 0.02,
                              "px": 60_000.0, "status": "FILLED"}
    ex.step(target(trend=pos))                            # want 0.03, have 0.02
    chases = [c for c in v.calls if "-C" in c[3]]
    assert len(chases) == 1 and chases[0][2] == pytest.approx(0.01)
    assert ex.state.legs["trend"].qty == pytest.approx(-0.03)
    # now the same setup with a sub-contract shortfall: no chase at all
    v2 = FakeVenue(mult=0.01)
    ex2 = mkexec(tmp_path / "b", v2)
    ex2.state.legs["trend"].entry_cloid = f"T-{NOW}-E"
    v2.orders[f"T-{NOW}-E"] = {"type": "MARKET", "side": "SELL", "qty": 0.028,
                               "px": 60_000.0, "status": "FILLED"}
    ex2.step(target(trend=pos))                           # want 0.03, have 0.028
    assert not [c for c in v2.calls if "-C" in c[3]]
    assert ex2.state.legs["trend"].qty == pytest.approx(-0.028)   # truth, not 0.03


def test_gate_venue_size_never_rounds_up(tmp_path):
    """_to_venue_size must refuse a sub-minimum order rather than inflate it."""
    from app.cb import CoinbaseVenue
    v = object.__new__(CoinbaseVenue)
    v._meta = {"base_increment": 0.0001, "price_increment": 0.1,
               "contract_multiplier": 0.01}
    assert v.quantize(0.01466) == pytest.approx(0.01)
    assert v.quantize(0.00466) == 0.0
    assert v._to_venue_size(0.03) == "3"
    with pytest.raises(ValueError):
        v._to_venue_size(0.00466)                         # used to become "1"
    v._meta["contract_multiplier"] = None                 # INTX perp path
    assert v.quantize(0.014663) == pytest.approx(0.0146)
    with pytest.raises(ValueError):
        v._to_venue_size(0.00001)


def test_gate_venue_stop_fill_no_double_close(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))                             # chase entry + stop
    stop_cloid = ex.state.legs["pullback"].stop_cloid
    v.orders[stop_cloid]["status"] = "FILLED"             # stop fired on venue
    ex.step(target())                                     # engine flat next
    # exactly one closing MARKET would double the exit; the chase entry is
    # the only market order allowed here
    closes = [c for c in v.calls if c[0] == "MARKET" and c[1] == "SELL"]
    assert not closes
    assert ex.state.legs["pullback"].qty == 0.0


def test_gate_orphan_fill_unwound(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    v.orders[f"P-{NOW}-E"]["status"] = "FILLED"           # we filled...
    ex.step(target())                                     # ...paper cancelled
    mkts = [c for c in v.calls if c[0] == "MARKET"]
    assert mkts and mkts[-1][1] == "SELL"                 # unwound
    assert ex.state.legs["pullback"].qty == 0.0
    assert any(e["kind"] == "orphan_fill_unwound" for e in ex.state.events)


def test_gate_caps_clamp(tmp_path):
    v = FakeVenue(equity=1_000_000.0)                     # lev cap not binding
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    _, _, qty, _ = v.calls[0]
    assert qty * 59_000 <= 25_000 * 1.01                  # max_notional respected
    assert any(e["kind"] == "cap_clamp" for e in ex.state.events)


def test_gate_stale_engine_blocks_entries_not_exits(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))
    assert ex.state.legs["pullback"].qty > 0
    stale_ts = NOW - 5 * 14_400
    pend = {"pending": {"side": "S", "limit": 61_000.0, "signal_ts": stale_ts},
            "position": None}
    n_orders = len(v.calls)
    # stale feed: new trend entry must NOT fire...
    ex.step(target(pull=pos, trend=pend, bar_ts=stale_ts))
    assert not [c for c in v.calls[n_orders:] if c[0] in ("LIMIT",)]
    # ...but an engine exit still closes our leg even while stale
    ex.step(target(bar_ts=stale_ts))
    assert ex.state.legs["pullback"].qty == 0.0


def test_gate_daily_loss_halt_flattens_and_blocks(tmp_path):
    v = FakeVenue(equity=10_000.0)
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))
    v._equity = 9_000.0                                   # -10% on the day
    ex.step(target(pull=pos))
    assert ex.state.halted is None                        # debounce: 1/3
    assert any(e["kind"] == "halt_pending" for e in ex.state.events)
    ex.step(target(pull=pos))                             # 2/3
    ex.step(target(pull=pos))                             # 3/3 -> halt
    assert ex.state.halted == "DAILY_LOSS"
    assert ("CANCEL_ALL", None, None, None) in v.calls
    n = len(v.calls)
    ex.step(target(pull=pos))                             # halted -> inert
    assert len(v.calls) == n
    ex.resume()
    assert ex.state.halted is None


def test_gate_kill_switch(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "S", "entry_price": 60_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 63_000.0, "exit_flag": None}}
    ex.step(target(trend=pos))
    ex.halt("KILL", "test")
    assert ex.state.halted == "KILL"
    assert ("CANCEL_ALL", None, None, None) in v.calls
    # venue flattened: net short was closed with a BUY market
    assert [c for c in v.calls if c[0] == "MARKET" and c[1] == "BUY"]
    assert all(l.qty == 0.0 for l in ex.state.legs.values())


def test_gate_restart_resumes_ledger(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    n_orders = len(v.calls)
    # new process, same state file + same venue
    ex2 = Executor(v, ex.cfg, ex.cfg.state_path)
    assert ex2.state.legs["pullback"].entry_cloid == f"P-{NOW}-E"
    ex2.step(target(pull=pend))                           # no duplicate order
    assert len([c for c in v.calls[n_orders:] if c[0] == "LIMIT"]) == 0


def test_gate_drift_detection(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    # venue shows a position our ledger doesn't know about
    v.orders["ghost"] = {"type": "MARKET", "side": "BUY", "qty": 0.5,
                         "px": 60_000.0, "status": "FILLED"}
    ex.step(target())
    assert any(e["kind"] == "position_drift" for e in ex.state.events)


def test_gate_sizing_base_overrides_equity(tmp_path):
    """SIZING_BASE_USD: a $25k account trading a $128k base sizes positions
    on the base, and halt thresholds anchor to the base too."""
    v = FakeVenue(equity=25_000.0)
    ex = mkexec(tmp_path, v)
    ex.cfg.sizing_base_usd = 128_000.0
    ex.cfg.max_notional_usd = 500_000.0        # keep caps out of the way
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    _, _, qty, _ = v.calls[0]
    assert qty == pytest.approx(0.56 * 1.5 * 0.75 * 128_000 / 59_000, abs=1e-4)
    # -6% of the ACCOUNT (=$1.5k) must NOT halt: threshold is 6% of base
    v._equity = 23_400.0
    ex.step(target(pull=pend))
    assert ex.state.halted is None
    # -6% of the BASE (=$7.7k) does halt (after debounce confirms)
    v._equity = 25_000.0 - 0.06 * 128_000 - 1
    for _ in range(ex.HALT_CONFIRM_POLLS):
        ex.step(target(pull=pend))
    assert ex.state.halted == "DAILY_LOSS"


def test_gate_halt_config_coherence_warning(tmp_path):
    """$30k account, $128k base, 25% DD halt = $32k > deposit: warn."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
    ex.cfg.sizing_base_usd = 128_000.0
    ex.cfg.dd_halt_pct = 0.25
    ex.step(target())
    assert any(e["kind"] == "halt_config" for e in ex.state.events)
    # coherent config (15% of base = $19.2k, 64% of deposit): no warning
    v2 = FakeVenue(equity=30_000.0)
    ex2 = mkexec(tmp_path, v2)
    ex2.cfg.sizing_base_usd = 128_000.0
    ex2.cfg.dd_halt_pct = 0.15
    ex2.state.events.clear()
    ex2.step(target())
    assert not any(e["kind"] == "halt_config" for e in ex2.state.events)


def test_gate_daily_marks_recorded(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.step(target())
    assert len(ex.state.marks) == 1
    assert ex.state.marks[0]["equity"] == 10_000.0
    ex.step(target())                          # same UTC day -> no new mark
    assert len(ex.state.marks) == 1


def test_gate_telegram_alerts_on_halt_and_live_trades(tmp_path, monkeypatch):
    sent = []
    import app.alerts as alerts
    monkeypatch.setattr(alerts, "send", lambda t: sent.append(t))
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))                 # dry-run entry -> no alert
    assert not [s for s in sent if "entry" in s]
    ex.halt("KILL", "test")                   # halt -> alert always
    assert any("halt" in s for s in sent)
    ex.cfg.dry_run = False                    # live: entries alert too
    ex.resume()
    ex.step(target(pull=pos))
    assert any("entry" in s for s in sent)


def test_gate_transient_bad_equity_read_no_halt(tmp_path):
    """The 2026-08-06 false halt: one failed balance read (fallback value)
    must not trigger a drawdown halt — debounce + recovery clears it."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
    ex.step(target())                                     # HWM = 30k
    v._equity = 10_000.0                                  # one bad read
    ex.step(target())
    assert ex.state.halted is None
    v._equity = 30_000.0                                  # read recovers
    ex.step(target())
    ex.step(target())
    assert ex.state.halted is None
    assert ex._breach_count == 0


def test_gate_dryrun_equity_last_known_good():
    from app.cb import DryRunVenue

    class Flaky:
        def __init__(self):
            self.ok = True

        def equity(self):
            if self.ok:
                return 29_990.0
            raise RuntimeError("api down")

        def mid(self):
            return 60_000.0

    inner = Flaky()
    v = DryRunVenue(inner)
    assert v.equity() == 29_990.0                         # real read
    inner.ok = False
    assert v.equity() == 29_990.0                         # last-known-good,
    assert v.equity() != 10_000.0                         # never the stand-in


def test_gate_dry_run_venue_never_touches_inner():
    from app.cb import DryRunVenue

    class Boom:
        def __getattr__(self, name):
            if name in ("equity", "mid"):
                return lambda: 10_000.0
            raise AssertionError(f"mutation {name} reached inner venue")

    v = DryRunVenue(Boom())
    v.place_limit("BUY", 0.1, 59_000.0, "x")
    v.place_market("SELL", 0.1, "y")
    v.cancel("x")
    v.cancel_all()
    assert len(v.log) == 4
    assert v.orders["x"]["status"] == "CANCELLED"


def test_gate_alert_tier_labels(tmp_path, monkeypatch):
    """Casey-facing alert contract: halts carry the ACTION NEEDED label +
    resume instruction; non-halt REDs say forward-to-Claude / no action;
    resume reads as all-clear. (Casey: 'make sure all the Tier 3 ones are
    labeled clearly that I need to do something to fix it.')"""
    sent = []
    import app.alerts as alerts
    monkeypatch.setattr(alerts, "send", lambda t: sent.append(t))
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.halt("DRAWDOWN", "test halt")
    assert any("ACTION NEEDED" in s and "/resume" in s for s in sent), sent
    ex.resume()
    assert any("no action needed" in s and "resume" in s for s in sent)
    sent.clear()
    ex._event("RED", "position_drift", "test drift")
    assert len(sent) == 1
    assert "forward this to Claude" in sent[0] and "ACTION NEEDED" not in sent[0]
    sent.clear()
    ex._event("WARN", "halt_config", "dd_halt unreachable")
    assert len(sent) == 1 and "ACTION NEEDED" in sent[0]        # tier-3 WARN
    sent.clear()
    ex._event("WARN", "cap_clamp", "clamped")                   # ordinary WARN
    assert sent == []                                           # stays quiet


def test_gate_daily_loss_auto_rearms_drawdown_does_not(tmp_path):
    """DAILY_LOSS is a rate limiter: it clears itself at the UTC day
    rollover WHILE KELLY_M <= 0.30 (above that: manual, ramp v3 rule).
    DRAWDOWN stays manual — auto-reset there would turn the floor into a
    retry loop."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
    ex.cfg.kelly_m = 0.20                                 # below manual line
    ex.step(target())
    ex.halt("DAILY_LOSS", "test")
    ex.state.day_key = "2000-01-01"                       # force a rollover
    ex.step(target())
    assert ex.state.halted is None
    assert any(e["kind"] == "auto_rearm" for e in ex.state.events)
    ex.halt("DRAWDOWN", "test")
    ex.state.day_key = "2000-01-02"
    ex.step(target())
    assert ex.state.halted == "DRAWDOWN"                  # still waiting on human


def test_gate_transfer_reconciliation_flat_book(tmp_path):
    """Deposits/withdrawals while flat shift the halt anchors instead of
    tripping the breaker (the 2026-08 deposit false-halt category)."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
    ex.step(target()); ex.step(target())                  # baseline, HWM 30k
    v._equity = 50_000.0                                  # $20k deposit lands
    ex.step(target()); ex.step(target()); ex.step(target())
    assert ex.state.halted is None
    assert any(e["kind"] == "transfer_reconciled" for e in ex.state.events)
    assert ex.state.high_water == pytest.approx(50_000.0)
    # withdrawal back out while flat: anchors follow, NO drawdown halt
    v._equity = 30_000.0
    for _ in range(5):
        ex.step(target())
    assert ex.state.halted is None
    assert ex.state.high_water == pytest.approx(30_000.0)
    assert not any(e["kind"] == "halt" for e in ex.state.events)


def test_gate_transfer_reconciliation_never_masks_real_losses(tmp_path):
    """The reconciler must NOT fire while a position is open (equity moves
    are P&L) — a genuine loss still halts through the normal path."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
    pos = {"pending": None,
           "position": {"side": "L", "entry_price": 59_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 56_500.0, "exit_flag": None}}
    ex.step(target(pull=pos))                             # leg has qty now
    v._equity = 8_000.0                                   # catastrophic slide
    for _ in range(ex.HALT_CONFIRM_POLLS + 1):
        ex.step(target(pull=pos))
    assert ex.state.halted in ("DAILY_LOSS", "DRAWDOWN")  # daily line trips first
    assert not any(e["kind"] == "transfer_reconciled" for e in ex.state.events)


def test_gate_trend_exit_no_double_close(tmp_path):
    """QA rehearsal find (2026-08-07): a trend MARKET entry keeps its
    entry_cloid for the position's life; on engine exit the old code both
    orphan-unwound the fill AND closed led.qty — same BTC twice — leaving a
    naked reverse position on the venue. Engine-exit must produce exactly
    one closing order and a flat venue."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    tr_pend = {"pending": {"side": "S", "limit": -1.0, "signal_ts": NOW},
               "position": None}
    ex.step(target(trend=tr_pend))                       # market entry (sentinel)
    v.orders[f"T-{NOW}-E"]["status"] = "FILLED"
    tr_pos = {"pending": None,
              "position": {"side": "S", "entry_price": 60_000.0, "entry_ts": NOW,
                           "signal_ts": NOW, "stop": 63_000.0, "exit_flag": None}}
    ex.step(target(trend=tr_pos))                        # position ack + stop
    ex.step(target())                                    # engine exits
    unwinds = [c for c in v.orders if c.endswith("-UNWIND")]
    assert not unwinds, unwinds                          # no orphan unwind
    assert abs(v.position()) < 1e-9                      # venue truly flat
    assert ex.state.legs["trend"].qty == 0.0
    # branch-2 variant: position -> directly to a NEW pending (no flat step)
    ex.step(target(trend=tr_pend))
    v.orders[f"T-{NOW}-E"]["status"] = "FILLED"
    ex.step(target(trend=tr_pos))
    new_pend = {"pending": {"side": "L", "limit": -1.0, "signal_ts": NOW + 14_400},
                "position": None}
    ex.step(target(trend=new_pend))
    unwinds = [c for c in v.orders if c.endswith("-UNWIND")]
    assert not unwinds, unwinds
    # old short closed + new long entry = net long exactly the new entry qty
    new_e = v.orders.get(f"T-{NOW + 14_400}-E")
    assert new_e is not None


def test_gate_no_blueprint_managed_trading_vars():
    """The DRY_RUN incident, generalized (QA 2026-08-11): ANY trading-
    behavior env var with a literal value: in render.yaml is a pending
    silent reset on the next unrelated commit. All of them must be
    sync:false on BOTH executors; the dashboard owns the values and the
    config_change guard pages on drift."""
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                            "render.yaml")).read()

    def keys_with_literals(service):
        blk = src[src.index(f"name: {service}"):]
        nxt = re.search(r"\n  - type: ", blk[10:])
        blk = blk[:nxt.start() + 10] if nxt else blk
        out = {}
        for m in re.finditer(
                r"- key: (\w+)\n(?:\s*#.*\n)*\s*(value|sync)", blk):
            out[m.group(1)] = m.group(2)
        return out

    exec_vars = keys_with_literals("btc-executor")
    for k in ("DRY_RUN", "KELLY_M", "SIZING_BASE_USD", "MAX_NOTIONAL_USD",
              "MAX_ACCOUNT_LEV", "DD_HALT_PCT", "CB_PRODUCT_ID",
              "AUTO_DRILL"):
        assert exec_vars.get(k) == "sync", (k, exec_vars.get(k))
    ibkr_vars = keys_with_literals("ibkr-executor")
    for k in ("DRY_RUN", "TRADING_MODE", "READ_ONLY_API", "LEG_BUDGET_USD"):
        assert ibkr_vars.get(k) == "sync", (k, ibkr_vars.get(k))


def test_gate_fills_recorded_and_persisted(tmp_path):
    """Execution prices must survive restarts: without them the ramp's
    slippage statistic has sample size zero (the QA blocking finding)."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.state.fills.append({"ts": 1, "leg": "pullback", "role": "entry",
                           "cloid": "X", "px": 60_000.0, "ref_px": 59_970.0,
                           "slip_bps": 5.0})
    ex._save_state()
    ex2 = mkexec(tmp_path, v)
    assert ex2.state.fills and ex2.state.fills[-1]["slip_bps"] == 5.0


def test_gate_leg_error_isolated_and_capclamp_red(tmp_path):
    """One leg's venue error must not skip the other leg (post-only
    rejections were doing exactly that, invisibly), and cap_clamp is a
    silent size reduction -> must be RED so it alerts."""
    class Boom(FakeVenue):
        def place_limit(self, *a, **k):
            raise RuntimeError("post-only rejected")
    v = Boom()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    tr = {"pending": {"side": "S", "limit": -1.0, "signal_ts": NOW},
          "position": None}
    ex.step(target(pull=pend, trend=tr))
    assert any(e["kind"] == "leg_sync_error" for e in ex.state.events)
    # the trend leg still got its market order despite the pullback blowing up
    assert any(c.startswith("T-") for c in v.orders), v.orders
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "app", "mirror.py")).read()
    assert '"RED", "cap_clamp"' in src


def test_gate_mode_change_alerts(tmp_path, monkeypatch):
    """A silent DRY_RUN flip (blueprint sync reset a LIVE account on
    2026-08-10) must page the operator, not pass unnoticed."""
    sent = []
    import app.alerts as alerts
    monkeypatch.setattr(alerts, "send", lambda t: sent.append(t))
    v = FakeVenue()
    ex = mkexec(tmp_path, v, dry_run=False)      # boots LIVE
    ex.step(target())
    assert not [s for s in sent if "mode_change" in s]   # first sight: quiet
    ex._save_state()
    ex2 = mkexec(tmp_path, v, dry_run=True)      # sync silently un-arms it
    ex2.step(target())
    assert any("ACTION NEEDED" in s and "DRY_RUN" in s for s in sent), sent
    assert any(e["kind"] == "mode_change" for e in ex2.state.events)


def test_gate_config_defaults_fail_safe():
    """A missing env must UNDER-size, never over-size."""
    from app.config import Settings
    d = Settings()
    assert d.kelly_m <= 0.05, d.kelly_m
    assert d.dry_run is True


# ---------- 2026-08-11 counter-agent panel gates ----------

class _StubResp:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class _StubClient:
    """Coinbase RESTClient stand-in: rejects the first post-only limit as
    marketable, accepts the resend."""
    def __init__(self):
        self.limit_calls = []

    def get_product(self, product_id=None):
        return _StubResp({"base_increment": "0.0001",
                          "quote_increment": "0.1",
                          "price_increment": "0.1",
                          "future_product_details": {"contract_size": "0.01"}})

    def limit_order_gtc(self, **kw):
        self.limit_calls.append(kw)
        if kw.get("post_only"):
            return _StubResp({"success": False, "error_response": {
                "error": "INVALID_LIMIT_PRICE_POST_ONLY",
                "message": "Post only order would cross",
                "preview_failure_reason": "PREVIEW_POST_ONLY_WOULD_CROSS"}})
        return _StubResp({"success": True,
                          "success_response": {"order_id": "oid-1"}})


def _mk_cb_venue(tmp_path, monkeypatch, client):
    """Build CoinbaseVenue through its REAL __init__ (a stubbed coinbase.rest
    module) - the missing post_only_crosses init lived in __init__ and a
    test that bypasses it cannot catch that class of bug."""
    import sys, types
    mod = types.ModuleType("coinbase.rest")
    mod.RESTClient = lambda api_key=None, api_secret=None: client
    pkg = types.ModuleType("coinbase")
    pkg.rest = mod
    monkeypatch.setitem(sys.modules, "coinbase", pkg)
    monkeypatch.setitem(sys.modules, "coinbase.rest", mod)
    from app.cb import CoinbaseVenue

    class VCfg:
        cb_api_key_name = "k"
        cb_api_private_key = "s"
        cb_product_id = "BIP-20DEC30-CDE"
        state_path = str(tmp_path / "state.json")
        stop_limit_offset_pct = 0.5

    return CoinbaseVenue(VCfg())


def test_gate_post_only_reject_actually_resends(tmp_path, monkeypatch):
    """FATAL find 2026-08-11: post_only_crosses was referenced in place_limit
    but never initialized, so the first live post-only rejection raised
    AttributeError BEFORE the marketable resend - every short pullback entry
    at positive basis crash-looped. This walks the real __init__ + the real
    rejection path."""
    client = _StubClient()
    v = _mk_cb_venue(tmp_path, monkeypatch, client)
    v.place_limit("SELL", 0.03, 64_000.0, "P-1-E", post_only=True)
    assert len(client.limit_calls) == 2                   # reject + resend
    assert client.limit_calls[0]["post_only"] is True
    assert client.limit_calls[1]["post_only"] is False
    assert v.post_only_crosses == ["P-1-E"]
    assert v._orders["P-1-E"] == "oid-1"


def test_gate_post_only_detector_ignores_cross_margin(tmp_path, monkeypatch):
    """The old detector matched bare "CROSS" anywhere in the response - an
    insufficient-funds rejection echoing margin_type CROSS would have been
    resent WITHOUT maker protection."""
    client = _StubClient()
    v = _mk_cb_venue(tmp_path, monkeypatch, client)
    bad = _StubResp({"success": False, "error_response": {
        "error": "INSUFFICIENT_FUND",
        "message": "insufficient funds"},
        "order_configuration": {"margin_type": "CROSS"}})
    assert not v._rejected_post_only(bad)
    good = _StubResp({"success": False, "error_response": {
        "error": "INVALID_LIMIT_PRICE_POST_ONLY",
        "message": "would cross"}})
    assert v._rejected_post_only(good)


def test_gate_venue_size_floors_not_rounds(tmp_path, monkeypatch):
    """round() honored "never rounds up" only below HALF a contract: 0.006
    became a full contract (counter-agent find 2026-08-11). Floor everywhere."""
    v = _mk_cb_venue(tmp_path, monkeypatch, _StubClient())
    assert v._to_venue_size(0.014) == "1"                 # floor(1.4) = 1
    assert v._to_venue_size(0.03) == "3"                  # exact
    for sub in (0.006, 0.0099, 0.00466):
        with pytest.raises(ValueError):
            v._to_venue_size(sub)


def test_gate_order_status_unknown_maps_open(tmp_path, monkeypatch):
    """QUEUED/PENDING must not read as CANCELLED: that skipped the cancel and
    chased full size -> doubled position at session reopen."""
    client = _StubClient()

    class _O:
        def __init__(self, status):
            self.s = status

        def to_dict(self):
            return {"order": {"status": self.s, "filled_size": "0",
                              "average_filled_price": None}}
    v = _mk_cb_venue(tmp_path, monkeypatch, client)
    v._orders["X"] = "oid-x"
    for raw, want in [("QUEUED", "OPEN"), ("PENDING", "OPEN"),
                      ("CANCEL_QUEUED", "OPEN"), ("OPEN", "OPEN"),
                      ("CANCELLED", "CANCELLED"), ("EXPIRED", "CANCELLED"),
                      ("FAILED", "CANCELLED")]:
        client.get_order = lambda oid, _r=raw: _O(_r)
        assert v.order_status("X")["status"] == want, raw


def test_gate_stop_fill_never_resurrects_position(tmp_path):
    """Pre-existing FATAL class (counter-agent 2026-08-11): venue stop fires
    intrabar; engine keeps reporting the position until its next 4h close.
    The flat ledger + still-FILLED entry order re-entered a phantom position
    and armed a live stop on a flat venue. Also: trail moving < 5bp must not
    hide the fill (the churn guard ran first)."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    pos = {"pending": None,
           "position": {"side": "S", "entry_price": 60_000.0, "entry_ts": NOW,
                        "signal_ts": NOW, "stop": 63_000.0, "exit_flag": None}}
    ex.step(target(trend=pos))
    stop_cloid = ex.state.legs["trend"].stop_cloid
    v.orders[stop_cloid]["status"] = "FILLED"             # stop fired on venue
    pos["position"]["stop"] = 62_999.0                    # < 5bp trail move
    ex.step(target(trend=pos))                            # must SEE the fill
    assert ex.state.legs["trend"].qty == 0.0
    assert any(e["kind"] == "stop_filled_on_venue" for e in ex.state.events)
    n = len(v.calls)
    for _ in range(3):                                    # engine still lagging
        ex.step(target(trend=pos))
    assert ex.state.legs["trend"].qty == 0.0              # no phantom re-entry
    assert len(v.calls) == n                              # no orders at all
    ex.step(target())                                     # engine catches up
    # entry was consumed by the stop: no orphan-flatten reverse position
    assert not [c for c in v.calls[n:] if c[0] == "MARKET"]
    # next signal (new entry_ts) trades normally again
    ex.step(target(trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": NOW + 14_400},
                          "position": None}))
    assert ex.state.legs["trend"].qty > 0


def test_gate_fills_recorded_from_real_orders(tmp_path):
    """_record_fill existed with ZERO call sites - the ramp's primary fill-
    quality criterion ran on an empty dataset (counter-agent 2026-08-11).
    Every order now enters a watch queue and lands in state.fills when its
    status resolves. Trend market entry fills instantly in FakeVenue."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    fills = [f for f in ex.state.fills if f["role"] == "entry"]
    assert len(fills) == 1
    f = fills[0]
    assert f["leg"] == "trend" and f["side"] == "SELL"
    assert f["px"] == 60_000.0 and f["slip_bps"] == 0.0


def test_gate_slippage_sign_adverse_positive(tmp_path):
    """The original expression evaluated to +1.0 on BOTH branches - every
    SELL's slippage would have been sign-flipped."""
    ex = mkexec(tmp_path, FakeVenue())
    ex._record_fill("trend", "entry", "c1", {"avg_price": 59_940.0},
                    60_000.0, "SELL")                     # sold 10bp LOW = bad
    ex._record_fill("trend", "entry", "c2", {"avg_price": 60_060.0},
                    60_000.0, "BUY")                      # paid 10bp UP = bad
    s1, s2 = ex.state.fills[-2]["slip_bps"], ex.state.fills[-1]["slip_bps"]
    assert s1 == pytest.approx(10.0) and s2 == pytest.approx(10.0)


def test_gate_daily_loss_manual_resume_above_030(tmp_path):
    """Ramp v3's "manual resume above KELLY_M 0.30" was doc-only (counter-
    agent 2026-08-11): _roll_day cleared DAILY_LOSS unconditionally."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)                              # Cfg.kelly_m = 0.56
    ex.state.halted = "DAILY_LOSS"
    ex.state.day_key = "2020-01-01"                       # force a rollover
    ex.step(target())
    assert ex.state.halted == "DAILY_LOSS"                # NOT auto-cleared
    assert not any(e["kind"] == "auto_rearm" for e in ex.state.events)
    ex2 = mkexec(tmp_path / "b", FakeVenue())
    ex2.cfg.kelly_m = 0.05
    ex2.state.halted = "DAILY_LOSS"
    ex2.state.day_key = "2020-01-01"
    ex2.step(target())
    assert ex2.state.halted is None                       # token size: rearms
    assert any(e["kind"] == "auto_rearm" for e in ex2.state.events)


def test_gate_config_change_pages(tmp_path):
    """The DRY_RUN blueprint incident, generalized: ANY sizing/risk config
    change between polls must produce a config_change event."""
    ex = mkexec(tmp_path, FakeVenue())
    ex.step(target())                                     # snapshot stored
    ex.cfg.kelly_m = 0.20
    ex.step(target())
    ev = [e for e in ex.state.events if e["kind"] == "config_change"]
    assert len(ev) == 1 and "kelly_m: 0.56 -> 0.2" in ev[0]["msg"]
    ex.step(target())                                     # stable -> no repeat
    assert len([e for e in ex.state.events
                if e["kind"] == "config_change"]) == 1


def test_gate_stale_ledger_migrated_at_load(tmp_path):
    """Pre-8e27c01 state recorded requested sizes (-0.01466) while the venue
    holds whole contracts. Snap at load; sub-contract residue is dust."""
    import json
    sp = tmp_path / "state.json"
    st = ExecState()
    from dataclasses import asdict
    d = {"halted": None, "day_key": "", "day_start_equity": 0.0,
         "high_water": 0.0, "events": [], "marks": [], "fills": [],
         "last_dry_run": None,
         "legs": {"pullback": {"qty": 0.004},                 # dust
                  "trend": {"qty": -0.01466}}}                # old format
    sp.write_text(json.dumps(d))
    cfg = Cfg()
    cfg.state_path = str(sp)
    v = FakeVenue(mult=0.01)
    v._add("MARKET", "SELL", 0.01, "seed")   # the venue really holds the short
    ex = Executor(v, cfg, cfg.state_path)
    assert ex.state.legs["trend"].qty == pytest.approx(-0.01)
    assert ex.state.legs["pullback"].qty == 0.0
    assert len([e for e in ex.state.events
                if e["kind"] == "ledger_migrated"]) == 2


def test_gate_halt_keeps_ledger_on_flatten_failure(tmp_path):
    """halt() zeroed the ledger even when the flatten FAILED - the transfer
    reconciler then read a naked position's bleed as withdrawals."""
    class BoomVenue(FakeVenue):
        def place_market(self, side, qty, cloid):
            if cloid.startswith("halt-"):
                raise RuntimeError("venue down")
            super().place_market(side, qty, cloid)
    v = BoomVenue()
    ex = mkexec(tmp_path, v)
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    assert ex.state.legs["trend"].qty < 0
    ex.halt("KILL", "test")
    assert any(e["kind"] == "halt_error" for e in ex.state.events)
    assert ex.state.legs["trend"].qty < 0                 # ledger = truth


def test_gate_close_dust_cleared_not_looped(tmp_path):
    """A stale sub-contract residue made _close_leg cancel the stop then
    raise from _to_venue_size forever: permanent naked stopless loop."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.legs["trend"].qty = -0.004                   # unholdable dust
    ex.step(target())                                     # engine flat
    assert ex.state.legs["trend"].qty == 0.0
    assert any(e["kind"] == "ledger_dust_cleared" for e in ex.state.events)
    assert not [c for c in v.calls if c[0] == "MARKET"]


def test_gate_alert_cooldown_limits_repeat_pages(tmp_path, monkeypatch):
    """halt_config embeds a changing equity float, defeating kind+msg dedupe:
    ~180 pages/hour while the condition persisted. Rate-limit sends per kind;
    never rate-limit halts or live-trade events. Events always logged."""
    sent = []
    import app.alerts as alerts
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    ex = mkexec(tmp_path, FakeVenue())
    ex._event("RED", "cap_clamp", "qty 1")
    ex._event("RED", "cap_clamp", "qty 2")                # different msg
    assert len([m for m in sent if "cap_clamp" in m]) == 1
    assert len([e for e in ex.state.events
                if e["kind"] == "cap_clamp"]) == 2        # both logged
    ex._event("RED", "halt", "DAILY_LOSS a")
    ex._event("RED", "halt", "DAILY_LOSS b")
    assert len([m for m in sent if "halt" in m and "DAILY_LOSS" in m]) == 2


# ---------------------------------------------------------------------------
# RAMP v4 (RAMP_V4.md, frozen 2026-08-15): coverage counters + drills
def _drill_exec(tmp_path):
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    venue = DryRunVenue(None)
    return Executor(venue, cfg), venue


def test_gate_drill_cycle_full_path(tmp_path):
    ex, venue = _drill_exec(tmp_path)
    rec = ex.drill("cycle")
    assert rec["ok"], rec
    s = rec["steps"]
    assert s["stop_open"] and s["stop_cancelled"] and s["venue_flat_end"]
    assert ex.state.coverage.get("drill_cycle") == 1
    assert ex.state.coverage.get("stop_placed") == 1
    # fills recorded under leg='drill' (feed slippage, excluded from P&L)
    legs = {f["leg"] for f in ex.state.fills}
    assert legs == {"drill"}
    # drill orders are all D- prefixed and the venue ends flat
    assert all(c.startswith("D-") for c in venue.orders)
    assert venue.position() == 0.0


def test_gate_drill_stopfill_fallback_never_leaves_position(tmp_path):
    """DryRun stops never auto-fill -> the fallback path must cancel and
    flatten; the drill reports UNVERIFIED, never leaves exposure."""
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.drill_cooldown_s = 0
    rec = ex.drill("stopfill")
    assert rec["ok"] is False
    assert rec["steps"]["stop_filled"] is False
    assert rec["steps"]["fallback_flatten"] is True
    assert venue.position() == 0.0
    assert ex.state.coverage.get("stop_filled") is None   # not faked


def test_gate_drill_stopfill_verified_path(tmp_path, monkeypatch):
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.drill_cooldown_s = 0
    real_place_stop = venue.place_stop
    def filling_stop(side, qty, trigger_px, cloid):
        real_place_stop(side, qty, trigger_px, cloid)
        venue.orders[cloid]["status"] = "FILLED"   # venue fires instantly
    monkeypatch.setattr(venue, "place_stop", filling_stop)
    rec = ex.drill("stopfill")
    assert rec["ok"], rec
    assert ex.state.coverage.get("stop_filled") == 1
    assert ex.state.coverage.get("drill_stopfill") == 1
    assert venue.position() == 0.0


def test_gate_drill_refusals(tmp_path):
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.drill_cooldown_s = 0
    # refused while a leg holds anything
    ex.state.legs["trend"].qty = 0.01
    assert "leg_not_flat" in ex.drill("cycle")["refused"]
    ex.state.legs["trend"].qty = 0.0
    # refused while halted
    ex.state.halted = "KILL"
    assert "halted" in ex.drill("cycle")["refused"]
    ex.state.halted = None
    # refused when the venue holds a position we don't ledger
    venue.orders["X"] = {"type": "MARKET", "side": "BUY", "qty": 0.02,
                         "px": 60_000.0, "status": "FILLED"}
    assert "venue_not_flat" in ex.drill("cycle")["refused"]
    del venue.orders["X"]
    # daily budget: cap reached -> refused
    ex.cfg.drill_max_per_day = 2
    assert ex.drill("cycle")["ok"]
    assert ex.drill("cycle")["ok"]
    assert ex.drill("cycle")["refused"] == "daily_budget_exhausted"
    # unknown kind
    assert "unknown" in ex.drill("nope")["refused"]


def test_gate_drill_cooldown(tmp_path):
    ex, _ = _drill_exec(tmp_path)
    assert ex.drill("cycle")["ok"]
    assert ex.drill("cycle")["refused"] == "cooldown"


def test_gate_drill_size_is_always_min_contract(tmp_path):
    """No parameter can raise drill size; with a quantizing venue the drill
    trades exactly one contract."""
    ex, venue = _drill_exec(tmp_path)
    venue.quantize = lambda q: (int(q / 0.01 + 1e-9)) * 0.01
    rec = ex.drill("cycle")
    assert rec["steps"]["qty"] == 0.01


def test_gate_coverage_persists_and_restart_counter(tmp_path):
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    ex = Executor(DryRunVenue(None), cfg)
    ex._cov("entry_long")
    ex._save_state()
    # reboot flat: no restart_with_position increment
    ex2 = Executor(DryRunVenue(None), cfg)
    assert ex2.state.coverage.get("entry_long") == 1
    assert ex2.state.coverage.get("restart_with_position") is None
    # reboot with an open leg: counted
    ex2.state.legs["trend"].qty = 0.01
    ex2._save_state()
    ex3 = Executor(DryRunVenue(None), cfg)
    assert ex3.state.coverage.get("restart_with_position") == 1


def test_gate_ramp_v4_readiness_block():
    from app.main import RAMP_V4_REQUIRED, _ramp_v4
    from app.mirror import ExecState
    st = ExecState()
    r = _ramp_v4(st)
    assert r["coverage_complete"] is False
    # all-modes totals alone must NOT open the gate (mode guard 2026-08-21)
    st.coverage = {k: v for k, v in RAMP_V4_REQUIRED.items()}
    st.fills = [{"slip_bps": 1.0}] * 10
    assert _ramp_v4(st)["coverage_complete"] is False
    # the same evidence, produced live, does
    st.coverage_live = {k: v for k, v in RAMP_V4_REQUIRED.items()}
    st.fills = [{"slip_bps": 1.0, "live": True}] * 10
    r2 = _ramp_v4(st)
    assert r2["coverage_complete"] is True
    assert r2["rows"]["slippage_sample"]["met"] is True


def test_gate_spec_pins_ramp_v4():
    spec = open(os.path.join(os.path.dirname(__file__), "..", "RAMP_V4.md")).read()
    assert "frozen 2026-08-15" in spec
    assert "P&L is explicitly NOT a gate" in spec
    from app.main import RAMP_V4_REQUIRED
    # every spec row that names a counter exists in the code's requirement map
    for key in ("entry_long", "entry_short", "stop_placed", "stop_filled",
                "signal_exit", "chase", "post_only_cross",
                "restart_with_position", "config_change", "drill_cycle"):
        assert key in RAMP_V4_REQUIRED and key in spec


# --- referee-mandated drill-safety gates (2026-08-15) ----------------------
def test_gate_drill_fill_beats_cancel_auto_repairs(tmp_path):
    """Stop fills in the cancel window -> exit must be SKIPPED and any
    residue auto-repaired; drill reports UNVERIFIED, venue ends flat."""
    ex, venue = _drill_exec(tmp_path)
    real_cancel = venue.cancel
    def racing_cancel(cloid):
        if cloid.endswith("-S") and venue.orders.get(cloid, {}).get("status") == "OPEN":
            venue.orders[cloid]["status"] = "FILLED"   # fill beats the cancel
            return
        real_cancel(cloid)
    venue.cancel = racing_cancel
    rec = ex.drill("cycle")
    assert rec["ok"] is False
    assert rec["steps"]["stop_cancelled"] is False
    assert rec["steps"]["exit"] == "skipped_stop_filled"
    assert rec["steps"]["venue_flat_end"] is True
    assert venue.position() == 0.0


def test_gate_drill_exception_path_auto_repairs(tmp_path):
    """place_stop raising after the entry (the likeliest real-Coinbase
    outcome for an above-market STOP_DOWN) must never leave the entry
    position open — auto-repair flattens and the drill pages RED."""
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.drill_cooldown_s = 0
    def raising_stop(side, qty, trigger_px, cloid):
        raise RuntimeError("PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE")
    venue.place_stop = raising_stop
    for kind in ("cycle", "stopfill"):
        rec = ex.drill(kind)
        assert rec["ok"] is False, kind
        assert venue.position() == 0.0, kind
        assert rec["steps"].get("auto_repair") is not None or \
            rec["steps"].get("fallback_flatten") or \
            rec["steps"]["venue_flat_end"] is True
    # unverified drills page: last drill events are RED
    reds = [e for e in ex.state.events if e["kind"] == "drill"]
    assert reds and all(e["level"] == "RED" for e in reds)


def test_gate_kill_serializes_behind_drill(tmp_path):
    """/kill (halt) must take the venue lock: it may not interleave with an
    in-flight drill."""
    import threading as th
    ex, venue = _drill_exec(tmp_path)
    started, order = th.Event(), []
    real_status = venue.order_status
    def slow_status(cloid):
        started.set()
        time.sleep(0.3)
        return real_status(cloid)
    venue.order_status = slow_status
    def run_drill():
        order.append(("drill", ex.drill("cycle")))
    t = th.Thread(target=run_drill)
    t.start()
    started.wait(5)
    ex.halt("KILL", "operator")          # must BLOCK until the drill exits
    order.append(("halt_done", None))
    t.join(10)
    assert order[0][0] == "drill"        # drill completed before halt ran
    assert ex.state.halted == "KILL"
    assert venue.position() == 0.0


def test_gate_ramp_v4_requires_halt_resume():
    """Referee: coverage_complete was reachable without ever exercising the
    kill switch. Spec's halt+resume row must be enforced in code."""
    from app.main import RAMP_V4_REQUIRED, _ramp_v4
    from app.mirror import ExecState
    st = ExecState()
    st.coverage = {k: v for k, v in RAMP_V4_REQUIRED.items()}
    st.coverage_live = {k: v for k, v in RAMP_V4_REQUIRED.items()
                        if k not in ("halt", "resume")}
    st.fills = [{"slip_bps": 1.0, "live": True}] * 10
    assert _ramp_v4(st)["coverage_complete"] is False
    st.coverage_live.update({"halt": 1, "resume": 1})
    assert _ramp_v4(st)["coverage_complete"] is True


def test_gate_spec_rows_covered_by_code():
    """Both directions: every counter-named row in the spec table exists in
    RAMP_V4_REQUIRED (the direction that was broken), and vice versa."""
    import re
    from app.main import RAMP_V4_REQUIRED
    spec = open(os.path.join(os.path.dirname(__file__), "..", "RAMP_V4.md")).read()
    table = spec[spec.index("| event class"):spec.index("Honesty note")]
    spec_rows = set(re.findall(r"^\| (\w+)", table, re.M)) - {"event"}
    aliases = {"halt": {"halt", "resume"}, "drill_cycle": {"drill_cycle"},
               "signal_exit": {"signal_exit"}, "slippage": set()}
    covered = set()
    for row in spec_rows:
        covered |= aliases.get(row, {row})
    covered.discard("slippage")
    assert covered <= set(RAMP_V4_REQUIRED), covered - set(RAMP_V4_REQUIRED)
    assert set(RAMP_V4_REQUIRED) <= covered, set(RAMP_V4_REQUIRED) - covered


# --- mode guard on coverage counters (2026-08-21) --------------------------
def test_gate_dry_run_events_never_satisfy_coverage(tmp_path):
    """A full matrix accumulated in DRY_RUN must NOT open the ramp gate: a
    DryRunVenue event proves the state machine, not the venue, and the gate
    exists to prove the venue. Regression guard for the class of failure the
    2026-08-10 blueprint sync produced (DRY_RUN silently true on a live
    account) - drills fired in that window would otherwise tick rows."""
    from app.cb import DryRunVenue
    from app.main import RAMP_V4_REQUIRED, _ramp_v4
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = True
    ex = Executor(DryRunVenue(None), cfg)
    for key, need in RAMP_V4_REQUIRED.items():
        for _ in range(need):
            ex._cov(key)
    assert ex.state.coverage["entry_long"] == RAMP_V4_REQUIRED["entry_long"]
    assert ex.state.coverage_live == {}
    r = _ramp_v4(ex.state)
    assert r["coverage_complete"] is False
    assert r["rows"]["entry_long"]["have"] == 0
    assert r["rows"]["entry_long"]["all_modes"] == RAMP_V4_REQUIRED["entry_long"]
    assert r["rows"]["entry_long"]["unattributed"] == RAMP_V4_REQUIRED["entry_long"]
    assert r["unattributed_total"] > 0


def test_gate_live_events_attributed_and_persist(tmp_path):
    """Live-mode counts land in coverage_live, survive a reboot, and a mode
    flip mid-life keeps the two tallies correctly separated."""
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    ex = Executor(FakeVenue(), cfg)
    ex._cov("entry_long")
    ex._cov("entry_long")
    # flip to dry-run: total keeps climbing, live tally frozen
    cfg.dry_run = True
    ex._cov("entry_long")
    ex._save_state()
    assert ex.state.coverage["entry_long"] == 3
    assert ex.state.coverage_live["entry_long"] == 2
    ex2 = Executor(DryRunVenue(None), cfg)
    assert ex2.state.coverage["entry_long"] == 3
    assert ex2.state.coverage_live["entry_long"] == 2


def test_gate_legacy_coverage_is_unattributed_not_live(tmp_path):
    """State written before the split has `coverage` but no `coverage_live`.
    Those counts must read as unattributed - never silently promoted to
    live evidence, which would hand the gate provenance it never had."""
    import json
    from app.cb import DryRunVenue
    from app.main import _ramp_v4
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    json.dump({"halted": "", "legs": {},
               "coverage": {"entry_long": 5, "drill_cycle": 3},
               "fills": [{"slip_bps": 1.0}] * 12},
              open(cfg.state_path, "w"))
    ex = Executor(DryRunVenue(None), cfg)
    assert ex.state.coverage["entry_long"] == 5
    assert ex.state.coverage_live == {}
    r = _ramp_v4(ex.state)
    assert r["rows"]["entry_long"]["met"] is False
    assert r["rows"]["entry_long"]["unattributed"] == 5
    assert r["rows"]["slippage_sample"]["met"] is False
    assert r["rows"]["slippage_sample"]["all_modes"] == 12


def test_gate_dry_run_fills_excluded_from_slippage_sample(tmp_path):
    """Synthetic DryRunVenue prices must not feed the slippage dataset."""
    from app.cb import DryRunVenue
    from app.main import _ramp_v4
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = True
    ex = Executor(DryRunVenue(None), cfg)
    for i in range(11):
        ex._record_fill("pullback", "entry", f"c{i}", {"avg_price": 60_030.0},
                        60_000.0, "BUY")
    assert len(ex.state.fills) == 11
    assert all(f["live"] is False for f in ex.state.fills)
    assert _ramp_v4(ex.state)["rows"]["slippage_sample"]["met"] is False
    cfg.dry_run = False
    live_ex = Executor(FakeVenue(), cfg)
    live_ex.state = ex.state          # same state, real venue
    for i in range(10):
        live_ex._record_fill("pullback", "entry", f"L{i}",
                             {"avg_price": 60_030.0}, 60_000.0, "BUY")
    r = _ramp_v4(ex.state)
    assert r["rows"]["slippage_sample"]["have"] == 10
    assert r["rows"]["slippage_sample"]["met"] is True


def test_gate_spec_pins_mode_guard():
    """The spec must state the live-only basis - doc/code drift on the ramp
    gate is exactly the failure this repo keeps re-finding."""
    spec = open(os.path.join(os.path.dirname(__file__), "..", "RAMP_V4.md")).read()
    assert "coverage_live" in spec
    assert "DRY_RUN" in spec


# --- counter-agent fixes to the mode guard (2026-08-21) --------------------
def test_gate_ramp_v4_survives_shape_corrupt_state(tmp_path):
    """/status AND the public /pulse both render _ramp_v4, and _load_state
    accepts any JSON that parses. A corrupt row must not 500 them - that
    blinds monitoring on exactly the state file worth looking at."""
    from app.main import _ramp_v4

    class St:
        coverage = {"halt": "nine"}
        coverage_live = "all of them"
        fills = ["corrupt-row", {"slip_bps": 1.0, "live": True}]
    r = _ramp_v4(St())
    assert r["coverage_complete"] is False
    assert r["rows"]["halt"]["all_modes"] == 0
    assert r["rows"]["slippage_sample"]["have"] == 1
    assert r["rows"]["slippage_sample"]["all_modes"] == 2


def test_gate_impossible_live_excess_marked_corrupt_not_met():
    """coverage_live > coverage is unreachable via _cov (it writes both) and
    can only come from a tampered or rolled-back state file. It must never
    render as satisfied."""
    from app.main import _ramp_v4
    from app.mirror import ExecState
    st = ExecState()
    st.coverage = {"halt": 1}
    st.coverage_live = {"halt": 99}
    row = _ramp_v4(st)["rows"]["halt"]
    assert row["corrupt"] is True
    assert row["met"] is False


def test_gate_live_flag_alone_cannot_earn_against_dryrun_venue(tmp_path):
    """The linchpin: _cov trusts cfg.dry_run as a proxy for 'the venue can
    take an order'. _build_executor enforces that today; if it ever
    regresses, live evidence must still not accrue against a shadow book."""
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False                      # flag lies
    ex = Executor(DryRunVenue(None), cfg)    # venue tells the truth
    ex._cov("entry_long")
    ex._record_fill("pullback", "entry", "c1", {"avg_price": 60_030.0},
                    60_000.0, "BUY")
    assert ex.state.coverage["entry_long"] == 1
    assert ex.state.coverage_live == {}
    assert ex.state.fills[0]["live"] is False


def test_gate_live_venue_init_failure_never_demotes_to_dryrun(monkeypatch):
    """The invariant _cov leans on: LIVE mode raises rather than falling
    through to a shadow book."""
    import app.main as m
    monkeypatch.setattr(m.settings, "dry_run", False)
    monkeypatch.setattr(m.settings, "cb_api_key_name", "")
    monkeypatch.setattr(m.settings, "cb_api_private_key", "")
    monkeypatch.setattr(m, "send", lambda *a, **k: None, raising=False)
    with pytest.raises(RuntimeError):
        m._build_executor()


def test_gate_provenance_reset_is_announced(tmp_path):
    """The 13/13 -> 0/13 drop must page, not happen silently: every other
    surprising transition in this service alerts."""
    import json
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    json.dump({"halted": "", "legs": {},
               "coverage": {"entry_long": 5, "drill_cycle": 3}},
              open(cfg.state_path, "w"))
    ex = Executor(DryRunVenue(None), cfg)
    kinds = [e["kind"] for e in ex.state.events]
    assert "coverage_provenance_reset" in kinds
    msg = [e for e in ex.state.events
           if e["kind"] == "coverage_provenance_reset"][0]["msg"]
    assert "8" in msg and "not" in msg.lower()
    # already-split state (live counts present) must NOT re-announce
    ex._save_state()
    ex.state.coverage_live["entry_long"] = 1
    ex._save_state()
    ex2 = Executor(DryRunVenue(None), cfg)
    assert "coverage_provenance_reset" not in [
        e["kind"] for e in ex2.state.events[len(ex.state.events):]]


def test_gate_pulse_exposes_unattributed(tmp_path):
    """/pulse is what gets watched; a 0/13 with no explanation reads as
    data loss."""
    from app.main import _ramp_v4
    from app.mirror import ExecState
    st = ExecState()
    st.coverage = {"entry_long": 5}
    assert _ramp_v4(st)["unattributed_total"] == 5
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "app", "main.py")).read()
    assert "ramp_v4_unattributed" in src


def test_gate_spec_reads_ramp_rows_not_raw_coverage():
    """D4: the spec table told operators to read /status.coverage, which
    still shows a complete matrix after the split."""
    spec = open(os.path.join(os.path.dirname(__file__), "..", "RAMP_V4.md")).read()
    assert "ramp_v4.rows" in spec
    assert "any LIVE fill" in spec
    head = spec[:spec.index("Honesty note")]
    assert "✅ proven 2026-08-15" not in head


# --- one-shot coverage attestation (2026-08-21) ---------------------------
def _attest_ex(tmp_path, coverage, events=None, live_venue=True):
    import json
    from app.cb import DryRunVenue
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = not live_venue
    json.dump({"halted": "", "legs": {}, "coverage": coverage,
               "events": events or []}, open(cfg.state_path, "w"))
    venue = FakeVenue() if live_venue else DryRunVenue(None)
    return Executor(venue, cfg)


def test_gate_attest_promotes_and_marks_rows_attested(tmp_path):
    from app.main import _ramp_v4
    ex = _attest_ex(tmp_path, {"entry_long": 2, "chase": 1})
    assert _ramp_v4(ex.state)["rows"]["entry_long"]["met"] is False
    r = ex.attest_coverage("dry_run false since 2026-08-15", acknowledge_unwitnessed=True)
    assert r["ok"] is True and r["attested_events"] == 3
    rows = _ramp_v4(ex.state)["rows"]
    assert rows["entry_long"]["met"] is True
    # provenance must remain visible: attested != observed
    assert rows["entry_long"]["attested"] == 2
    assert rows["entry_long"]["unattributed"] == 0
    assert _ramp_v4(ex.state)["attestation"]["events"] == 3
    assert "coverage_attested" in [e["kind"] for e in ex.state.events]


def test_gate_attest_is_one_shot(tmp_path):
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    assert ex.attest_coverage(acknowledge_unwitnessed=True)["ok"] is True
    ex.state.coverage["entry_long"] = 9          # later evidence
    again = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert again["ok"] is False
    assert again["refused"] == "already_attributed"
    assert ex.state.coverage_live["entry_long"] == 2   # not topped up


def test_gate_attest_refuses_when_mode_flipped(tmp_path):
    """The load-bearing refusal: a DRY_RUN flip means a window of unknown
    mode existed, counts carry no timestamps, so nothing is attributable.
    Not operator-overridable - overriding it IS the failure mode."""
    ex = _attest_ex(tmp_path, {"entry_long": 2}, events=[
        {"ts": 1, "level": "RED", "kind": "mode_change",
         "msg": "DRY_RUN False -> True: trading is now SIMULATED"}])
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is False and r["refused"] == "mode_change_in_log"
    assert ex.state.coverage_live == {}
    assert r["flips"]


def test_gate_attest_refuses_in_dry_run(tmp_path):
    ex = _attest_ex(tmp_path, {"entry_long": 2}, live_venue=False)
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is False and r["refused"] == "not_live"
    assert ex.state.coverage_live == {}


def test_gate_attest_survives_restart(tmp_path):
    from app.mirror import Executor
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    ex.attest_coverage(acknowledge_unwitnessed=True)
    ex2 = Executor(FakeVenue(), ex.cfg)
    assert ex2.state.coverage_live["entry_long"] == 2
    assert ex2.state.coverage_attested["entry_long"] == 2
    assert ex2.state.attestation["events"] == 2
    # and it stays one-shot across the reboot
    assert ex2.attest_coverage(acknowledge_unwitnessed=True)["refused"] == "already_attributed"


def test_gate_attest_endpoint_requires_token_and_confirm(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m
    monkeypatch.setattr(m.settings, "exec_token", "sekret")

    class _E:
        def attest_coverage(self, note="", acknowledge_unwitnessed=False):
            return {"ok": True, "attested_events": 1,
                    "ack": acknowledge_unwitnessed}
    monkeypatch.setattr(m, "EXEC", _E())
    c = TestClient(m.app)
    assert c.post("/coverage/attest?confirm=true").status_code == 401
    # authed but unconfirmed must not fire
    r = c.post("/coverage/attest", headers={"X-Exec-Token": "sekret"})
    assert r.status_code == 400
    ok = c.post("/coverage/attest?confirm=true",
                headers={"X-Exec-Token": "sekret"})
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert ok.json()["ack"] is False          # not acknowledged by default
    ack = c.post("/coverage/attest?confirm=true&acknowledge_unwitnessed=true",
                 headers={"X-Exec-Token": "sekret"})
    assert ack.json()["ack"] is True


def test_gate_spec_documents_attestation():
    spec = open(os.path.join(os.path.dirname(__file__), "..", "RAMP_V4.md")).read()
    assert "/coverage/attest" in spec
    assert "mode_change" in spec


# --- attestation hardening (counter-agent FATAL, 2026-08-21) --------------
def test_gate_attest_refuses_on_durable_flip_after_log_rotation(tmp_path):
    """THE fatal find: the event log holds 200 entries and rate-limited
    conditions fire every poll, so a mode_change ages out in ~67 minutes of
    ordinary operation. The refusal must rest on a witness that does not
    rotate."""
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    ex.state.mode_flips = 1                       # durable counter
    ex.state.events = [{"ts": 1, "level": "WARN", "kind": "halt_config",
                        "msg": "noise"}] * 201    # flip long since rotated
    assert not [e for e in ex.state.events if e["kind"] == "mode_change"]
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is False and r["refused"] == "mode_flips_recorded"
    assert ex.state.coverage_live == {}


def test_gate_attest_refuses_on_dryrun_fills_in_state(tmp_path):
    """Second durable witness: fills tagged live=False prove the executor
    ran against a shadow venue while these counts accrued."""
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    ex.state.fills = [{"slip_bps": 1.0, "live": False}]
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is False and r["refused"] == "dryrun_fills_in_state"


def test_gate_boot_detects_flip_across_redeploy(tmp_path):
    """_check_mode_change only ran inside step(), so a flip across a
    redeploy was never recorded before an operator could act."""
    from app.mirror import Executor
    ex = _attest_ex(tmp_path, {"entry_long": 2})   # live venue, dry_run False
    ex._save_state()
    assert ex.state.last_dry_run is False
    cfg2 = ex.cfg
    cfg2.dry_run = True                            # silent un-arm
    ex2 = Executor(FakeVenue(), cfg2)              # no step() called
    assert ex2.state.mode_flips == 1
    assert any(e["kind"] == "mode_change" for e in ex2.state.events)


def test_gate_attest_allowed_with_open_position_at_deploy(tmp_path):
    """A5: an open leg at deploy fires _cov('restart_with_position') inside
    __init__, before the operator can call. That must NOT foreclose the
    migration - but live counts from an EARLIER process must."""
    import json
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "coverage": {"entry_long": 2, "chase": 1},
               "legs": {"trend": {"qty": 0.05}}, "last_dry_run": False},
              open(cfg.state_path, "w"))
    v = FakeVenue()
    v._add("MARKET", "BUY", 0.05, "seed")    # venue really holds the leg
    ex = Executor(v, cfg)
    assert ex.state.coverage_live == {"restart_with_position": 1}
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is True
    # the boot-observed count is NOT attested - only the pre-split delta
    assert "restart_with_position" not in r["rows"]
    assert ex.state.coverage_attested == {"entry_long": 2, "chase": 1}
    # a later process carrying prior live evidence is refused
    ex.state.attestation = None
    ex._cov_since_boot = {}
    assert ex.attest_coverage(acknowledge_unwitnessed=True)["refused"] == "live_evidence_predates_call"


def test_gate_attest_is_atomic_on_persist_failure(tmp_path):
    """A 500 must not burn the one-shot in memory only."""
    ex = _attest_ex(tmp_path, {"entry_long": 2})

    def boom():
        raise OSError("disk full")
    ex._save_state = boom
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is False and r["refused"].startswith("persist_failed")
    assert ex.state.coverage_live == {}
    assert ex.state.attestation is None
    del ex._save_state
    assert ex.attest_coverage(acknowledge_unwitnessed=True)["ok"] is True     # retry works


def test_gate_attest_serializes_behind_venue_lock(tmp_path):
    """attest was the only _save_state writer outside _venue_lock, which
    let it publish a torn ledger mid-step."""
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    import threading
    out = {}
    ex._venue_lock.acquire()
    try:
        t = threading.Thread(
            target=lambda: out.update(ex.attest_coverage(acknowledge_unwitnessed=True)), daemon=True)
        t.start()
        t.join(timeout=2)
        # still blocked on the lock: nothing mutated, nothing persisted
        assert t.is_alive(), "attest ran while the venue lock was held"
        assert out == {}
        assert ex.state.coverage_live == {}
        assert ex.state.attestation is None
    finally:
        ex._venue_lock.release()
    t.join(timeout=10)
    assert out.get("ok") is True          # proceeds once the lock frees


def test_gate_attest_sanitizes_promoted_counts(tmp_path):
    """_load_state accepts any JSON that parses; promoted counts must not
    carry negatives or strings into a monitored field."""
    from app.main import _ramp_v4
    ex = _attest_ex(tmp_path, {"entry_long": -5, "chase": "9",
                               "stop_placed": 2})
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is True and r["rows"] == ["stop_placed"]
    rows = _ramp_v4(ex.state)["rows"]
    assert rows["stop_placed"]["attested"] == 2
    assert rows["stop_placed"]["observed"] == 0
    assert "attested" not in rows["entry_long"]
    assert rows["chase"]["have"] == 0


def test_gate_attest_nothing_to_attest(tmp_path):
    ex = _attest_ex(tmp_path, {})
    assert ex.attest_coverage(acknowledge_unwitnessed=True)["refused"] == "nothing_to_attest"


def test_gate_attest_note_truncated_and_recorded(tmp_path):
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    ex.attest_coverage("x" * 500, acknowledge_unwitnessed=True)
    assert len(ex.state.attestation["note"]) == 200
    assert ex.state.attestation["limitation"]      # caveat outlives the curl


def test_gate_attest_observed_vs_attested_distinguished(tmp_path):
    """have: 7, attested: 2 is ambiguous without observed."""
    from app.main import _ramp_v4
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    ex.attest_coverage(acknowledge_unwitnessed=True)
    for _ in range(5):
        ex._cov("entry_long")
    row = _ramp_v4(ex.state)["rows"]["entry_long"]
    assert row["have"] == 7 and row["attested"] == 2 and row["observed"] == 5


def test_gate_pulse_reports_attested_rows(tmp_path, monkeypatch):
    """Attestation drives ramp_v4_unattributed to 0; the heartbeat must not
    then look identical to observed evidence."""
    from fastapi.testclient import TestClient
    import app.main as m
    ex = _attest_ex(tmp_path, {"entry_long": 2, "chase": 1})
    ex.attest_coverage(acknowledge_unwitnessed=True)
    monkeypatch.setattr(m, "EXEC", ex)
    monkeypatch.setattr(m.settings, "exec_token", "")
    p = TestClient(m.app).get("/pulse").json()
    assert p["ramp_v4_unattributed"] == 0
    assert p["ramp_v4_attested"] == 2


def test_gate_attest_cannot_satisfy_slippage_sample(tmp_path):
    """The strongest bound in the design: attestation can never complete
    the matrix - 10 genuinely live fills are still required."""
    from app.main import RAMP_V4_REQUIRED, _ramp_v4
    ex = _attest_ex(tmp_path, {k: v for k, v in RAMP_V4_REQUIRED.items()})
    r = ex.attest_coverage(acknowledge_unwitnessed=True)
    assert r["ok"] is True
    rv = _ramp_v4(ex.state)
    assert rv["rows"]["slippage_sample"]["met"] is False
    assert rv["coverage_complete"] is False
    assert "slippage_sample" in r["still_required"]


def test_gate_attest_requires_ack_for_unwitnessed_history(tmp_path):
    """A1, the honest residue: the FIRST migration is exactly the case the
    durable witnesses cannot cover - mode_flips was not tracked and fills
    were not mode-tagged while those counts accrued. The operator must say
    so explicitly, and the acknowledgement is recorded permanently."""
    ex = _attest_ex(tmp_path, {"entry_long": 2, "chase": 1})
    assert ex.state.unwitnessed_coverage == {"entry_long": 2, "chase": 1}
    r = ex.attest_coverage("no ack")
    assert r["ok"] is False
    assert r["refused"] == "unwitnessed_history_requires_acknowledgement"
    assert sorted(r["unwitnessed_rows"]) == ["chase", "entry_long"]
    assert ex.state.attestation is None
    ok = ex.attest_coverage("DRY_RUN false throughout",
                            acknowledge_unwitnessed=True)
    assert ok["ok"] is True
    assert ex.state.attestation["operator_acknowledged_unwitnessed"] is True
    assert sorted(ex.state.attestation["unwitnessed_rows"]) == ["chase",
                                                               "entry_long"]


def test_gate_witnessing_stamp_is_frozen_across_restarts(tmp_path):
    """A restart must not quietly convert unwitnessed history into
    witnessed history."""
    from app.mirror import Executor
    ex = _attest_ex(tmp_path, {"entry_long": 2})
    stamp = ex.state.witnessing_since
    assert stamp is not None
    ex._save_state()
    ex2 = Executor(FakeVenue(), ex.cfg)
    assert ex2.state.witnessing_since == stamp
    assert ex2.state.unwitnessed_coverage == {"entry_long": 2}
    assert ex2.attest_coverage()["refused"] == \
        "unwitnessed_history_requires_acknowledgement"


def test_gate_counts_earned_after_witnessing_need_no_ack(tmp_path):
    """Evidence earned under witnessing is covered by the durable checks,
    so it must not demand an acknowledgement."""
    import json
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {}, "coverage": {},
               "witnessing_since": 1000, "unwitnessed_coverage": {},
               "last_dry_run": False}, open(cfg.state_path, "w"))
    ex = Executor(FakeVenue(), cfg)
    ex.state.coverage = {"entry_long": 2}      # accrued under witnessing
    r = ex.attest_coverage("post-witnessing")
    assert r["ok"] is True
    assert r["rows"] == ["entry_long"]
# ---------------------------------------------------------------------------
# AUTO-DRILL (RAMP_V4.md amendment 2026-08-17): executor self-runs drills
def _auto_exec(tmp_path, monkeypatch):
    """Live-mode executor over a REAL-venue double with auto-drill armed and
    all pacing zeroed; captures Telegram sends.

    FakeVenue, not DryRunVenue: live mode over a shadow venue is a
    combination production forbids (_build_executor raises), and the
    coverage guard rejects it, so a DryRunVenue here would model a state
    that cannot exist and never advance coverage_live."""
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    venue = FakeVenue()
    ex = Executor(venue, cfg)
    ex.cfg.auto_drill = True
    ex.cfg.auto_drill_spacing_s = 0
    ex.cfg.drill_cooldown_s = 0
    sent = []
    from app import alerts
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    return ex, venue, sent


def test_gate_auto_drill_runs_cycles_in_flat_window(tmp_path, monkeypatch):
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    for _ in range(3):
        ex.step(target())
    assert ex.state.coverage_live.get("drill_cycle") == 3
    assert ex.state.coverage.get("drill_cycle") == 3
    assert all(d["kind"] == "cycle" and d["ok"] for d in ex.state.drills)
    assert venue.position() == 0.0
    assert ex.state.auto_drill_off is None
    assert sum("auto-drill cycle ok" in m for m in sent) == 3
    # cycles complete -> auto-drill is DONE; it never over-runs and never
    # schedules stopfill (deterministic live rejection, referee 2026-08-17)
    assert ex._needed_auto_drill() is None


def test_gate_auto_drill_never_schedules_stopfill(tmp_path):
    """stopfill stays manual/organic: Coinbase preview-rejects an
    above-market STOP_DOWN, so an auto stopfill = guaranteed breaker trip."""
    ex, _ = _drill_exec(tmp_path)
    assert ex._needed_auto_drill() == "cycle"
    ex.state.coverage_live = {"drill_cycle": 3}     # stop_filled still unmet
    assert ex._needed_auto_drill() is None


def test_gate_auto_drill_respects_spacing(tmp_path, monkeypatch):
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.cfg.auto_drill_spacing_s = 3600
    ex.step(target())
    ex.step(target())
    assert len(ex.state.drills) == 1


def test_gate_auto_drill_gated_off_dry_run_stale_and_flag(tmp_path, monkeypatch):
    """No auto drill when: disarmed, dry-run, degraded feed, or breaker set.
    Coverage integrity: dry-run fills must never mark live rows met."""
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.cfg.auto_drill = False
    ex.step(target())
    ex.cfg.auto_drill = True
    ex.cfg.dry_run = True
    ex.step(target())
    ex.cfg.dry_run = False
    ex.step(target(degraded=True))
    ex.state.auto_drill_off = "stopfill failed at 2026-08-17"
    ex.step(target())
    assert ex.state.drills == []


def test_gate_auto_drill_waits_for_flat_book(tmp_path, monkeypatch):
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.state.legs["trend"].qty = -0.01
    ex.step(target(trend={"pending": None, "position": {
        "side": "S", "entry_ts": NOW, "entry_price": 60_000.0,
        "qty": 0.01, "stop_price": 61_000.0}}))
    assert ex.state.drills == []          # refusal, silent - no breaker trip
    assert ex.state.auto_drill_off is None


def test_gate_auto_drill_breaker_trips_on_failure(tmp_path, monkeypatch):
    """One failed auto drill (venue rejects the stop) must auto-repair,
    disable auto-drill persistently, and page - never retry next poll."""
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    def raising_stop(side, qty, trigger_px, cloid):
        raise RuntimeError("PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE")
    venue.place_stop = raising_stop
    ex.step(target())
    assert len(ex.state.drills) == 1 and ex.state.drills[0]["ok"] is False
    assert venue.position() == 0.0        # auto-repair flattened
    assert ex.state.auto_drill_off
    assert any("auto-drill cycle FAILED" in m for m in sent)
    ex.step(target())
    assert len(ex.state.drills) == 1      # breaker holds
    # breaker survives restart (persisted)
    ex2 = Executor(venue, ex.cfg)
    assert ex2.state.auto_drill_off


def test_gate_auto_drill_stops_at_coverage_complete(tmp_path, monkeypatch):
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.state.coverage_live = {"drill_cycle": 3, "stop_filled": 1}
    ex.step(target())
    assert ex.state.drills == []


def test_gate_failed_drill_credits_no_coverage(tmp_path, monkeypatch):
    """Referee 2026-08-17: coverage rows authorize the ramp, so a drill
    that ends unverified must advance NOTHING (previously stop_placed /
    drill counters incremented before the repair tail knew the outcome)."""
    ex, venue = _drill_exec(tmp_path)
    orig_place_stop = venue.place_stop
    def raising_stop(side, qty, trigger_px, cloid):
        raise RuntimeError("PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE")
    venue.place_stop = raising_stop
    rec = ex.drill("cycle")
    assert rec["ok"] is False
    assert ex.state.coverage == {}
    # and a verified drill still credits normally
    venue.place_stop = orig_place_stop
    ex.cfg.drill_cooldown_s = 0
    rec2 = ex.drill("cycle")
    assert rec2["ok"] and ex.state.coverage.get("drill_cycle") == 1
    assert ex.state.coverage.get("stop_placed") == 1


def test_gate_verified_manual_drill_rearms_breaker(tmp_path):
    """The breaker's only re-arm path: a human-supervised drill that fully
    verifies. There was previously NO way to clear auto_drill_off short of
    editing the state file on the Render disk."""
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.drill_cooldown_s = 0
    ex.state.auto_drill_off = "cycle failed at 2026-08-17"
    rec = ex.drill("cycle")
    assert rec["ok"] is True
    assert ex.state.auto_drill_off is None
    assert any(e["kind"] == "auto_drill_rearmed" for e in ex.state.events)
    # a FAILED manual drill must NOT re-arm
    ex.state.auto_drill_off = "cycle failed again"
    def raising_stop(side, qty, trigger_px, cloid):
        raise RuntimeError("boom")
    venue.place_stop = raising_stop
    rec2 = ex.drill("cycle")
    assert rec2["ok"] is False and ex.state.auto_drill_off


def test_gate_auto_drill_flip_pages_config_change(tmp_path, monkeypatch):
    """AUTO_DRILL is a trading-behavior var: a silent flip (sync /
    fat-finger) must page like KELLY_M would (referee 2026-08-17)."""
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.cfg.auto_drill = False
    ex.step(target())
    ex.cfg.auto_drill = True
    ex.step(target())
    assert any(e["kind"] == "config_change" and "auto_drill" in e["msg"]
               for e in ex.state.events)


# --- merge integration: auto-drill (2026-08-17) x mode guard (2026-08-21) --
def test_gate_auto_drill_coverage_still_requires_live_venue(tmp_path):
    """The two changes must compose: auto-drill credits coverage rows after
    a VERIFIED drill, and the mode guard credits coverage_live only for real
    venue evidence. A verified drill against a shadow venue must therefore
    advance the audit total but NOT the ramp gate - even with dry_run
    flipped false, which auto-drill's own precondition would allow."""
    from app.main import _ramp_v4
    ex, venue = _drill_exec(tmp_path)
    ex.cfg.dry_run = False                 # flag lies; venue is DryRunVenue
    r = ex.drill("cycle")
    assert r.get("ok") is True, r          # drill itself verifies fine
    assert ex.state.coverage.get("drill_cycle") == 1      # audit trail
    assert ex.state.coverage_live == {}                   # gate unmoved
    assert _ramp_v4(ex.state)["rows"]["drill_cycle"]["met"] is False
    assert all(f["live"] is False for f in ex.state.fills)


def test_gate_auto_drill_never_fires_in_dry_run(tmp_path):
    """Main's own precondition, re-pinned after the merge: a dry-run auto
    drill would fabricate coverage that the guard would then have to
    discard."""
    ex, _ = _drill_exec(tmp_path)
    ex.cfg.auto_drill = True
    ex.cfg.auto_drill_spacing_s = 0
    ex.cfg.dry_run = True
    ex._maybe_auto_drill(True)
    assert ex.state.drills == []
    assert ex.state.coverage == {}


def test_gate_auto_drill_reads_gate_source_not_all_modes_total(tmp_path):
    """REGRESSION (2026-08-21): _needed_auto_drill read state.coverage, the
    all-modes total. After the provenance split that total still carries
    pre-split counts, so auto-drill saw drill_cycle as satisfied, returned
    None forever, and silently stopped advancing the ramp gate - the exact
    failure mode with AUTO_DRILL=true and a matrix stuck at 1/13.

    Auto-drill must want a drill whenever the GATE still wants one."""
    from app.main import _ramp_v4
    ex, _ = _drill_exec(tmp_path)
    # pre-split evidence: audit total satisfied, gate unsatisfied
    ex.state.coverage = {"drill_cycle": 9, "stop_placed": 9}
    ex.state.coverage_live = {}
    assert _ramp_v4(ex.state)["rows"]["drill_cycle"]["met"] is False
    assert ex._needed_auto_drill() == "cycle", \
        "auto-drill went blind to an unmet gate row"
    # once the gate is genuinely satisfied it stops
    ex.state.coverage_live = {"drill_cycle": 3}
    assert _ramp_v4(ex.state)["rows"]["drill_cycle"]["met"] is True
    assert ex._needed_auto_drill() is None
    # attested evidence counts as satisfied too - no pointless drilling
    ex.state.coverage_live = {"drill_cycle": 3}
    ex.state.coverage_attested = {"drill_cycle": 3}
    assert ex._needed_auto_drill() is None


def test_gate_coverage_events_actually_page(tmp_path, monkeypatch):
    """The provenance reset and attestation were WARN events whose kind
    matched no send branch: logged, never phoned. An event meant to stop a
    silent matrix reset must not itself be silent (found 2026-08-21 when
    the expected Telegram message never arrived)."""
    import json
    from app.mirror import Executor
    from app import alerts
    sent = []
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {},
               "coverage": {"entry_long": 2, "chase": 1},
               "last_dry_run": False}, open(cfg.state_path, "w"))
    ex = Executor(FakeVenue(), cfg)
    assert any("coverage_provenance_reset" in m for m in sent), sent
    sent.clear()
    ex.attest_coverage("test", acknowledge_unwitnessed=True)
    msg = [m for m in sent if "coverage_attested" in m]
    assert msg, sent
    # attestation is security-relevant: it must say what to do if unexpected
    assert "ACTION NEEDED" in msg[0] and "EXEC_TOKEN" in msg[0]


# ---------------------------------------------------------------------------
# LIVE FIND 2026-08-23 (Casey's halt/resume RAMP test, at 1 contract): after
# /kill -> /resume the leg re-entered and sat UNPROTECTED. halt() cleared
# stop_cloid but NOT stop_px, so _maintain_stop's churn guard compared the
# engine's unchanged trail against the stale price, saw "no material move",
# and returned without placing anything. The ledger advertised a stop price
# that no venue order backed, and self-correction had to wait for the trail
# to move >stop_replace_bps - up to a day on a daily ratchet.
def _long_target(entry_ts, stop):
    return target(trend={"pending": None,
                         "position": {"side": "L", "entry_price": 68_525.0,
                                      "entry_ts": entry_ts,
                                      "signal_ts": entry_ts - 14_400,
                                      "stop": stop, "exit_flag": None}})


def test_gate_halt_clears_stop_px_not_just_cloid(tmp_path):
    v = FakeVenue(mult=0.01, mid=77_500.0)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S71520", 71_520.89
    led.entry_cloid, led.entry_side, led.entry_qty = "T-1-E", "L", 0.01
    ex.halt("KILL", "manual")
    assert led.qty == 0.0
    assert led.stop_cloid is None
    assert led.stop_px is None, \
        "a stop PRICE that outlives its order suppresses the next placement"
    assert led.entry_cloid is None and led.entry_qty == 0.0


def test_gate_reentry_after_resume_is_protected(tmp_path):
    """End-to-end reproduction of the live sequence: hold a long with a
    trailing stop, /kill, /resume, and step against the SAME engine target
    (the engine's trail has not moved). The re-entered position must carry a
    real venue stop, not an inherited price."""
    v = FakeVenue(mult=0.01, mid=77_500.0)
    ex = mkexec(tmp_path, v)
    ets, stop = NOW - 14_400, 71_520.89
    ex.step(_long_target(ets, stop))                 # enter + protect
    led = ex.state.legs["trend"]
    assert led.qty != 0.0 and led.stop_cloid, "setup: leg must be protected"

    ex.halt("KILL", "manual")
    assert v.position() == 0.0
    ex.resume()
    ex.step(_long_target(ets, stop))                 # identical trail
    ex.step(_long_target(ets, stop))                 # settle any chase

    assert led.qty != 0.0, "resume must re-mirror the engine's open position"
    assert led.stop_cloid, "RE-ENTERED POSITION LEFT UNPROTECTED"
    assert led.stop_px == stop
    live = [c for c, o in v.orders.items()
            if c == led.stop_cloid and o.get("status") != "CANCELLED"]
    assert live, "ledger claims a stop the venue does not hold"


def test_gate_churn_guard_cannot_block_first_placement(tmp_path):
    """Defence in depth: whatever leaves a stale stop_px behind, a leg with
    no stop_cloid has no order to churn, so the guard must never suppress
    the placement."""
    v = FakeVenue(mult=0.01, mid=77_500.0)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid, led.stop_px = 0.01, None, 71_520.89
    ex._maintain_stop("trend", led, {"entry_ts": NOW, "stop": 71_520.89})
    assert led.stop_cloid, "churn guard blocked the FIRST stop placement"


# ---------------------------------------------------------------------------
# 2026-08-26 PHANTOM POSITION incident. Venue flat for three days while the
# ledger claimed a long and a resting stop sat armed as a naked-short entry.
# Root chain: duplicate chase cloid -> Coinbase dup-reject -> fill-watch
# confirmed against the OLD order -> ledger booked a fill that never
# happened -> position read raised on FLAT (flat products are omitted from
# /cfm/positions) -> drift check swallowed the raise silently.
class _FlatStubClient(_StubClient):
    """CFM returns a clean 200 with no row for our product = FLAT."""
    def list_futures_positions(self):
        return _StubResp({"positions": [
            {"product_id": "OTHER-PRODUCT", "side": "LONG",
             "number_of_contracts": "3"}]})


class _BothFailStubClient(_StubClient):
    def list_futures_positions(self):
        raise RuntimeError("cfm scope denied")

    def get_futures_position(self, product_id=None):
        raise RuntimeError("single-product read denied")


class _LongStubClient(_StubClient):
    def list_futures_positions(self):
        return _StubResp({"positions": [
            {"product_id": "BIP-20DEC30-CDE", "side": "LONG",
             "number_of_contracts": "1"}]})


def test_gate_position_flat_returns_zero_not_raise(tmp_path, monkeypatch):
    """Coinbase omits flat products from /cfm/positions. A clean response
    with no row IS the flat signal - raising on it (the old behaviour) made
    'flat' and 'broken' indistinguishable for three live days."""
    v = _mk_cb_venue(tmp_path, monkeypatch, _FlatStubClient())
    assert v.position() == 0.0


def test_gate_position_long_reads_signed_qty(tmp_path, monkeypatch):
    v = _mk_cb_venue(tmp_path, monkeypatch, _LongStubClient())
    assert v.position() == 0.01            # 1 contract x 0.01 multiplier


def test_gate_position_dual_failure_reports_both_errors(tmp_path, monkeypatch):
    """The first path's exception used to be swallowed by `pass`, so the
    surfaced error was always the dead fallback's AttributeError - masking
    the actual fault for the whole incident."""
    v = _mk_cb_venue(tmp_path, monkeypatch, _BothFailStubClient())
    with pytest.raises(RuntimeError) as e:
        v.position()
    msg = str(e.value)
    assert "cfm scope denied" in msg, "first-path error must be visible"
    assert "single-product read denied" in msg


def test_gate_position_never_calls_nonexistent_sdk_method():
    """get_intx_position exists in NO published coinbase-advanced-py. The
    venue adapter must never CALL it again (prose may mention it — the
    incident postmortem lives in the docstring)."""
    import ast as _ast
    import app.cb as cbmod
    tree = _ast.parse(open(cbmod.__file__).read())
    called = {n.attr for n in _ast.walk(tree) if isinstance(n, _ast.Attribute)}
    assert "get_intx_position" not in called


def test_gate_cb_calls_only_real_sdk_methods():
    """THE test that would have caught the incident at merge: every method
    cb.py invokes on self.client must exist on the pinned RESTClient."""
    real = pytest.importorskip("coinbase.rest",
                               reason="pinned SDK not installed")
    import ast as _ast
    import app.cb as cbmod
    tree = _ast.parse(open(cbmod.__file__).read())
    called = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Attribute) \
                and isinstance(node.value, _ast.Attribute) \
                and node.value.attr == "client":
            called.add(node.attr)
    assert called, "expected client.* calls in cb.py"
    missing = [m for m in sorted(called)
               if not hasattr(real.RESTClient, m)]
    assert not missing, f"cb.py calls SDK methods that do not exist: {missing}"


# --- halt path: never strip a stop you cannot replace ----------------------
class _BlindVenue(FakeVenue):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cancel_all_calls = 0

    def position(self):
        raise RuntimeError("venue unreadable")

    def cancel_all(self):
        self.cancel_all_calls += 1
        super().cancel_all()


def test_gate_halt_on_unreadable_venue_leaves_stop_alive(tmp_path):
    """2026-08-26 worst finding: cancel_all ran BEFORE the position read, so
    a halt against a blind venue cancelled the protective stop and then
    aborted - leaving a live position naked and the loop frozen."""
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089", 74_089.46
    v._add("STOP", "SELL", 0.01, "T-1-S74089", px=74_089.46)
    ex.halt("KILL", "manual")
    assert v.cancel_all_calls == 0, "cancelled orders on an unreadable venue"
    assert v.orders["T-1-S74089"]["status"] == "OPEN", "stop must stay resting"
    assert led.qty == 0.01, "ledger must not be zeroed blind"
    assert ex.state.halted == "KILL", "trading must still stop"
    assert any(e["kind"] == "halt_blind" for e in ex.state.events)


def test_gate_halt_readable_venue_still_flattens(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid = 0.01, "T-1-S74089"
    v._add("MARKET", "BUY", 0.01, "seed")          # venue really holds it
    v._add("STOP", "SELL", 0.01, "T-1-S74089", px=74_089.0)
    ex.halt("KILL", "manual")
    assert v.position() == 0.0, "readable venue must still be flattened"
    assert led.qty == 0.0 and led.stop_cloid is None


# --- drift check: blindness is loud, once per cooldown ---------------------
def test_gate_drift_blindness_pages_with_cooldown(tmp_path):
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    for _ in range(5):
        ex._check_drift(50_000.0)
    reds = [e for e in ex.state.events if e["kind"] == "venue_read_failed"]
    assert len(reds) == 1, f"must page exactly once inside cooldown: {reds}"


def test_gate_drift_success_stamps_venue_read_ts(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    assert getattr(ex.state, "last_venue_read_ts", 0) == 0
    ex._check_drift(50_000.0)
    assert ex.state.last_venue_read_ts > 0


# --- boot reconcile: phantom clears, ambiguity does not --------------------
def test_gate_boot_reconcile_clears_phantom(tmp_path):
    """The live incident state: ledger long 0.01, venue FLAT, stop resting.
    Boot must adopt venue truth, cancel the trap order, and page."""
    import json
    from app.mirror import Executor
    v = FakeVenue(mult=0.01)
    v._add("STOP", "SELL", 0.01, "T-1787155200-S74089", px=74_089.46)
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {"trend": {
        "qty": 0.01, "stop_cloid": "T-1787155200-S74089",
        "stop_px": 74089.46}}}, open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    led = ex.state.legs["trend"]
    assert led.qty == 0.0, "phantom must be cleared at boot"
    assert led.stop_cloid is None
    assert v.orders["T-1787155200-S74089"]["status"] == "CANCELLED", \
        "the naked-short trap order must be cancelled"
    assert any(e["kind"] == "phantom_position_cleared"
               for e in ex.state.events)


def test_gate_boot_reconcile_ambiguous_mismatch_only_pages(tmp_path):
    """Venue holds SOMETHING but not what the ledger says: too ambiguous to
    auto-fix at boot - page, adopt nothing."""
    import json
    from app.mirror import Executor
    v = FakeVenue(mult=0.01)
    v._add("MARKET", "BUY", 0.03, "ext")           # venue holds 0.03
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {"trend": {"qty": 0.01}}},
              open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex.state.legs["trend"].qty == 0.01, "must NOT auto-fix ambiguity"
    assert any(e["kind"] == "position_drift" for e in ex.state.events)


def test_gate_boot_reconcile_blind_venue_adopts_nothing(tmp_path):
    import json
    from app.mirror import Executor
    v = _BlindVenue(mult=0.01)
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {"trend": {"qty": 0.01}}},
              open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex.state.legs["trend"].qty == 0.01
    assert any(e["kind"] == "venue_read_failed" for e in ex.state.events)


# --- chase: unique cloids, live pricing, no blind buying -------------------
def _trend_pos(entry_ts=NOW, px=68_525.61):
    return {"side": "L", "entry_price": px, "entry_ts": entry_ts,
            "signal_ts": entry_ts - 14_400, "stop": None, "exit_flag": None}


def test_gate_chase_cloids_never_repeat(tmp_path):
    """The phantom's root: resume#2's chase re-used resume#1's client order
    id, Coinbase rejected the duplicate, and the fill-watch confirmed
    against the first order. Cloids must be unique per attempt and the
    counter must survive restarts."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    ex._enter_from_fill("trend", led, _trend_pos(), BLEND, 10_000.0)
    first = [c for c in v.orders if c.endswith("-C1")]
    assert first, f"expected -C1 chase cloid: {list(v.orders)}"
    led.qty = 0.0                                  # simulate flatten/resume
    ex._enter_from_fill("trend", led, _trend_pos(), BLEND, 10_000.0)
    assert any(c.endswith("-C2") for c in v.orders), \
        f"second chase must use a NEW cloid: {list(v.orders)}"
    # restart: counter persists, no reuse after reload
    ex2 = mkexec(tmp_path, v)
    assert ex2.state.legs["trend"].chase_n == 2


def test_gate_chase_sizes_and_references_live_mid(tmp_path):
    """Sizing and the slippage reference must use the venue mid at send
    time. The engine's entry price can be days stale: it recorded 1320bps
    of fictitious slippage and oversized the chase (and its caps)."""
    v = FakeVenue(mult=0.01, mid=77_575.0)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    ex._enter_from_fill("trend", led, _trend_pos(px=68_525.61), BLEND,
                        50_000.0)
    ex._poll_fill_watch()
    chases = [f for f in ex.state.fills if f["role"] == "chase"]
    assert chases, "chase fill must be recorded"
    assert abs(chases[-1]["slip_bps"]) < 100, \
        f"slippage vs live mid must be sane, got {chases[-1]['slip_bps']}"


def test_gate_chase_blocked_when_feed_stale(tmp_path):
    """A market chase is NEW RISK: with the feed stale/degraded it must not
    buy. Exits and stop maintenance stay ungated elsewhere."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    ex._enter_from_fill("trend", led, _trend_pos(), BLEND, 10_000.0,
                        entries_ok=False)
    assert not any(o["type"] == "MARKET" for o in v.orders.values()), \
        "must not market-buy while blind"
    assert led.qty == 0.0
    assert any(e["kind"] == "entries_blocked" for e in ex.state.events)


# --- polluted samples: voided, excluded, kept for audit --------------------
def test_gate_absurd_fills_voided_and_excluded(tmp_path):
    import json
    from app.main import _ramp_v4
    from app.mirror import Executor
    v = FakeVenue(mult=0.01)
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {}, "fills": [
        {"ts": 1, "leg": "trend", "role": "chase", "cloid": "x",
         "side": "BUY", "px": 77575.0, "ref_px": 68525.61,
         "slip_bps": 1320.59, "live": True},
        {"ts": 2, "leg": "trend", "role": "entry", "cloid": "y",
         "side": "BUY", "px": 64865.0, "ref_px": 64862.5,
         "slip_bps": 0.39, "live": True}]}, open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex.state.fills[0].get("void") is True
    assert ex.state.fills[1].get("void") is None
    rows = _ramp_v4(ex.state)["rows"]
    assert rows["slippage_sample"]["have"] == 1, \
        "voided garbage must not gate the ramp"
    assert any(e["kind"] == "fills_voided" for e in ex.state.events)
