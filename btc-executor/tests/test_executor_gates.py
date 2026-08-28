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


def _hold(v, qty=0.01, cloid="seed"):
    """Make the VENUE actually hold what the test's ledger claims.

    MANDATORY for any test that drives a stop placement. _maintain_stop's
    choke point refuses to place against a venue that does not back the
    ledger (re-gate 2026-08-26 B1a/B3) because place_stop is NOT
    reduce-only, so a stop the venue cannot back OPENS a position. A ledger
    claiming 0.01 against a venue holding nothing is not a neutral fixture -
    it is the 2026-08-26 phantom state, and the code is now supposed to
    refuse it. Seven pre-existing tests were written against that fixture.
    """
    v._add("MARKET", "BUY" if qty > 0 else "SELL", abs(qty), cloid)


def test_gate_pullback_entry_sizing_and_lifecycle(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    kind, side, qty, cloid = v.calls[0]
    assert (kind, side) == ("LIMIT", "BUY") and cloid == f"P-{NOW}-E1"
    # 0.56 * 1.5 * 0.75 * 10k / 59k = 0.10678 BTC
    assert qty == pytest.approx(0.56 * 1.5 * 0.75 * 10_000 / 59_000, abs=1e-4)
    # same pending again -> no duplicate order
    ex.step(target(pull=pend))
    assert len([c for c in v.calls if c[0] == "LIMIT"]) == 1
    # engine cancels (flat, no position) -> our order cancelled
    ex.step(target())
    assert v.orders[f"P-{NOW}-E1"]["status"] == "CANCELLED"


def test_gate_fill_places_stop_and_exit_closes(tmp_path):
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    v.orders[f"P-{NOW}-E1"]["status"] = "FILLED"          # limit filled
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
    assert ex.state.legs["trend"].entry_cloid == f"T-{NOW + 14_400}-E2"


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
    v.orders[f"P-{NOW}-E1"]["status"] = "FILLED"          # we filled...
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
    assert ex2.state.legs["pullback"].entry_cloid == f"P-{NOW}-E1"
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
    v.orders[f"T-{NOW}-E1"]["status"] = "FILLED"
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
    v.orders[f"T-{NOW}-E2"]["status"] = "FILLED"
    ex.step(target(trend=tr_pos))
    new_pend = {"pending": {"side": "L", "limit": -1.0, "signal_ts": NOW + 14_400},
                "position": None}
    ex.step(target(trend=new_pend))
    unwinds = [c for c in v.orders if c.endswith("-UNWIND")]
    assert not unwinds, unwinds
    # old short closed + new long entry = net long exactly the new entry qty
    new_e = v.orders.get(f"T-{NOW + 14_400}-E3")
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
        # echoes product_id like the real API - the configured-product probe
        # sanity-gates on it (a 200 with no product_id is not a confirmation)
        return _StubResp({"product_id": product_id or "BIP-20DEC30-CDE",
                          "base_increment": "0.0001",
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
    from app.mirror import DRILL_CYCLE_NEED, SLIPPAGE_SAMPLE_NEED
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    for _ in range(3):
        ex.step(target())
    assert ex.state.coverage_live.get("drill_cycle") == DRILL_CYCLE_NEED
    assert ex.state.coverage.get("drill_cycle") == DRILL_CYCLE_NEED
    assert all(d["kind"] == "cycle" and d["ok"] for d in ex.state.drills)
    assert venue.position() == 0.0
    assert ex.state.auto_drill_off is None
    assert sum("auto-drill cycle ok" in m for m in sent) == 3
    # drill_cycle is met, but 3 cycles yield only 6 live fills and
    # slippage_sample needs 10 - auto-drill must NOT report itself done with
    # the gate stuck at 6/10 (found 2026-08-24)
    assert ex._live_fill_count() == 6
    assert ex._needed_auto_drill() == "cycle"
    # ...and it keeps going until the slippage row is genuinely satisfied
    for _ in range(6):
        ex.step(target())
    assert ex._live_fill_count() >= SLIPPAGE_SAMPLE_NEED
    assert ex._needed_auto_drill() is None            # now, and only now
    assert all(d["kind"] == "cycle" for d in ex.state.drills)   # never stopfill
    assert venue.position() == 0.0
    assert ex.state.auto_drill_off is None


def test_gate_auto_drill_never_schedules_stopfill(tmp_path):
    """stopfill stays manual/organic: Coinbase preview-rejects an
    above-market STOP_DOWN, so an auto stopfill = guaranteed breaker trip."""
    ex, _ = _drill_exec(tmp_path)
    assert ex._needed_auto_drill() == "cycle"
    ex.state.coverage_live = {"drill_cycle": 3}     # stop_filled still unmet
    ex.state.fills = [{"slip_bps": 1.0, "live": True}] * 10
    assert ex._needed_auto_drill() is None          # never "stopfill"


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
    ex.state.fills = [{"slip_bps": 1.0, "live": True}] * 10
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
    # once the gate is genuinely satisfied it stops - which now requires the
    # slippage sample too, not just drill_cycle
    ex.state.coverage_live = {"drill_cycle": 3}
    assert _ramp_v4(ex.state)["rows"]["drill_cycle"]["met"] is True
    assert ex._needed_auto_drill() == "cycle"       # slippage still 0/10
    ex.state.fills = [{"slip_bps": 1.0, "live": True}] * 10
    assert ex._needed_auto_drill() is None
    # attested evidence counts as satisfied too - no pointless drilling
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
    v._add("MARKET", "BUY", 0.01, "seed-fill")           # venue holds it
    v._add("STOP", "SELL", 0.01, "T-1-S71520", px=71_520.89)
    v._add("MARKET", "BUY", 0.0, "T-1-E")                # entry handle exists
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
    _hold(v)
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


# ---------------------------------------------------------------------------
# 2026-08-27 live finding: the discovery banner filtered tickers on BTC/BIT
# and dropped BIP-20DEC30-CDE — the nano BTC perpetual-style future this
# deployment actually trades — so /status venue_products omitted the one
# configured product and the incident diagnosis concluded "your product does
# not exist" from the executor's own diagnostics.
class _DiscoveryStubClient(_StubClient):
    def get_products(self, **kw):
        return _StubResp({"products": [
            {"product_id": "BIT-25SEP26-CDE", "product_venue": "FCM"},
            {"product_id": "BIP-20DEC30-CDE", "product_venue": "FCM"},
            # a BIP product that is NOT the configured one: only the ticker
            # filter can surface it, so this row is what makes the filter
            # test non-vacuous (the configured product would be added by the
            # always-label fallback even with the filter broken - mutation
            # check 2026-08-27)
            {"product_id": "BIP-19DEC31-CDE", "product_venue": "FCM"},
            {"product_id": "ETH-PERP-INTX", "product_venue": "INTX"},
        ]})


class _NoListStubClient(_StubClient):
    """Listings entirely down; only direct get_product probes work."""
    def get_products(self, **kw):
        raise RuntimeError("listing endpoint down")


def test_gate_discovery_matches_bip_prefix(tmp_path, monkeypatch):
    v = _mk_cb_venue(tmp_path, monkeypatch, _DiscoveryStubClient())
    out = v.list_perp_candidates()
    assert any("BIP-20DEC30-CDE" in e for e in out), \
        f"BIP-prefixed product dropped by the ticker filter: {out}"
    # the NON-configured BIP row proves the FILTER matched it - the
    # configured row alone would also appear via the always-label fallback
    assert any("BIP-19DEC31-CDE" in e for e in out), \
        f"ticker filter still drops BIP prefixes: {out}"
    assert not any("ETH" in e for e in out), "not a BTC product list"


def test_gate_discovery_always_labels_configured_product(tmp_path, monkeypatch):
    """The configured product appears LABELED even when every listing query
    fails — a banner that can omit the product we trade is worse than none."""
    for client in (_DiscoveryStubClient(), _NoListStubClient()):
        v = _mk_cb_venue(tmp_path, monkeypatch, client)
        out = v.list_perp_candidates()
        cfg_rows = [e for e in out if "BIP-20DEC30-CDE" in e]
        assert cfg_rows and "(configured)" in cfg_rows[0], \
            f"configured product missing/unlabeled with {type(client).__name__}: {out}"


def test_gate_discovery_unreadable_configured_product_is_loud(tmp_path,
                                                              monkeypatch):
    v = _mk_cb_venue(tmp_path, monkeypatch, _NoListStubClient())

    def _boom(product_id=None):
        raise RuntimeError("api down")
    v.client.get_product = _boom
    out = v.list_perp_candidates()
    assert any("BIP-20DEC30-CDE" in e and "UNREADABLE" in e for e in out), \
        f"an unreachable configured product must be loud, not absent: {out}"


def test_gate_cb_captures_product_flags(tmp_path, monkeypatch):
    class _ViewOnlyClient(_StubClient):
        def get_product(self, product_id=None):
            r = super().get_product(product_id).to_dict()
            r["view_only"] = True
            r["product_venue"] = "FCM"
            return _StubResp(r)
    v = _mk_cb_venue(tmp_path, monkeypatch, _ViewOnlyClient())
    assert v.product_flags["view_only"] is True
    assert v.product_flags["venue"] == "FCM"


def test_gate_untradable_product_pages_at_boot(tmp_path):
    v = FakeVenue(mult=0.01)
    v.product_flags = {"view_only": True, "trading_disabled": False,
                       "venue": "FCM"}
    ex = mkexec(tmp_path, v)
    assert any(e["kind"] == "product_untradable" and e["level"] == "RED"
               for e in ex.state.events), \
        "a view_only product must page at boot, not fail one order at a time"


def test_gate_untradable_product_pages_through_dryrun_wrapper(tmp_path):
    """MUTATION KILLER (counter-agent 2026-08-27 F1): the flags live on the
    INNER venue when DryRunVenue wraps it — which is exactly the mandatory
    shadow stage. Reading only venue.product_flags let a view_only product
    run the whole shadow period silent, with the warning arriving only at
    the LIVE boot after DRY_RUN flips."""
    from app.cb import DryRunVenue        # the REAL wrapper: no __getattr__
    inner = FakeVenue(mult=0.01)          # delegation, flags ONLY on inner —
    inner.product_flags = {"view_only": True, "trading_disabled": False,
                           "venue": "FCM"}
    ex = mkexec(tmp_path, DryRunVenue(inner))
    assert any(e["kind"] == "product_untradable" for e in ex.state.events), \
        "flags on DryRunVenue.inner must still page at boot"


def test_gate_tradable_product_boots_quiet(tmp_path):
    v = FakeVenue(mult=0.01)
    v.product_flags = {"view_only": False, "trading_disabled": False,
                       "venue": "FCM"}
    ex = mkexec(tmp_path, v)
    assert not any(e["kind"] == "product_untradable"
                   for e in ex.state.events)


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
    ex.state.events.clear()          # drop the boot reconcile's own RED
    for _ in range(5):
        ex._check_drift(50_000.0)
    reds = [e for e in ex.state.events if e["kind"] == "venue_read_failed"]
    assert len(reds) == 1, f"must page exactly once inside cooldown: {reds}"
    # and after the cooldown lapses it pages AGAIN - blindness that lasts
    # must keep reaching the phone (review: dedupe muted repeat REDs)
    ex._venue_read_failed_at -= 1801
    ex.state.events[-1]["ts"] -= 1801
    ex._check_drift(50_000.0)
    reds = [e for e in ex.state.events if e["kind"] == "venue_read_failed"]
    assert len(reds) == 2, "cooldown expiry must re-page"


def test_gate_drift_success_stamps_venue_read_ts(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    # the boot reconcile reads the venue unconditionally now (two-sided
    # check), so a healthy boot has already stamped it
    assert ex.state.last_venue_read_ts > 0
    ex.state.last_venue_read_ts = 0
    ex._check_drift(50_000.0)
    assert ex.state.last_venue_read_ts > 0, "drift check must re-stamp"


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


# ---------------------------------------------------------------------------
# Review of the first hotfix cut (2026-08-26): REJECT — the stop cloid was
# still deterministic, and cancel-then-replace at an unchanged trail (the
# boot-reconcile wake-up, every kill->resume) re-sent a client order id the
# venue had already seen. These gates pin the reroll under BOTH possible
# venue dup semantics.
class _DupRejectVenue(FakeVenue):
    """A venue that REJECTS any client order id it has ever seen (the
    semantics the live incident proved for at least some order states)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen = set()

    def _add(self, kind, side, qty, cloid, px=None):
        if cloid in self.seen:
            raise RuntimeError(f"duplicate client_order_id {cloid}")
        self.seen.add(cloid)
        super()._add(kind, side, qty, cloid, px)


class _IdempotentVenue(FakeVenue):
    """A venue that silently maps a reused cloid onto the ORIGINAL order
    (idempotent semantics): the place 'succeeds' but nothing new rests."""
    def _add(self, kind, side, qty, cloid, px=None):
        if cloid in self.orders:
            return                      # old (possibly CANCELLED) order wins
        super()._add(kind, side, qty, cloid, px)


def _long_pos(trigger=74_089.46, entry_ts=NOW):
    return {"side": "L", "entry_price": 68_525.61, "entry_ts": entry_ts,
            "signal_ts": entry_ts - 14_400, "stop": trigger,
            "exit_flag": None}


def test_gate_stop_cloids_never_repeat_across_replace(tmp_path):
    """Cancel-then-replace at an UNCHANGED trigger must use a fresh cloid
    every time — under dup-REJECT semantics a reused one leaves the live
    position stopless."""
    v = _DupRejectVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos())
    first = led.stop_cloid
    assert first and v.orders[first]["status"] == "OPEN"
    # simulate the wake-up: reconcile/halt cancelled the stop and cleared refs
    v.cancel(first)
    led.stop_cloid, led.stop_px = None, None
    ex._maintain_stop("trend", led, _long_pos())      # SAME trigger integer
    second = led.stop_cloid
    assert second and second != first, \
        f"stop cloid reused: {second!r} (dup-reject => stopless position)"
    assert v.orders[second]["status"] == "OPEN"


def test_gate_stop_not_believed_until_venue_confirms(tmp_path):
    """Under IDEMPOTENT semantics a reused cloid maps to the CANCELLED
    original: the place 'succeeds', nothing rests. Belief (stop_cloid set,
    /pulse stop_placed=true) must only follow venue confirmation."""
    v = _IdempotentVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)
    led.qty = 0.01
    # poison: pre-cancelled order under the cloid the NEXT placement would
    # use if it ever reused ids; with salting the id differs, so emulate the
    # idempotent-collision by pre-seeding the exact salted id
    ex._maintain_stop("trend", led, _long_pos())
    cl1 = led.stop_cloid
    v.cancel(cl1)
    led.stop_cloid, led.stop_px = None, None
    # force the NEXT salt to collide with the cancelled order
    nxt = f"T-{NOW}-S74089-{led.stop_n + 1}"
    v.orders[nxt] = {"type": "STOP", "side": "SELL", "qty": 0.01,
                     "px": 74_089.46, "status": "CANCELLED"}
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid is None, \
        "ledger believes in a stop the venue holds as CANCELLED"
    assert any(e["kind"] == "stop_unconfirmed" for e in ex.state.events)
    # next step retries under a fresh salt and succeeds
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"


def test_gate_stop_counter_survives_restart(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos())
    n = led.stop_n
    assert n >= 1
    ex2 = mkexec(tmp_path, v)
    assert ex2.state.legs["trend"].stop_n == n, "salt must persist"


def test_gate_halt_refuses_to_zero_past_a_surviving_order(tmp_path):
    """cancel_all is best-effort in the adapter. If an order the ledger
    believes in is still OPEN afterwards, zeroing the refs would orphan an
    ARMED stop on a flat halted book - the halt must fail loud instead."""
    class _StickyCancelVenue(FakeVenue):
        def cancel_all(self):
            pass                         # silently cancels nothing
    v = _StickyCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("MARKET", "BUY", 0.01, "seed")
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid = 0.01, "T-1-S74089-1"
    ex.halt("KILL", "manual")
    assert led.stop_cloid == "T-1-S74089-1", "refs zeroed past a live order"
    assert led.qty == 0.01
    assert any(e["kind"] == "halt_error" for e in ex.state.events)


def test_gate_halt_retries_transient_reread(tmp_path):
    """One transient on the post-cancel re-read must not strip the stop and
    skip the flatten."""
    class _FlakyVenue(FakeVenue):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.calls_n = 0

        def position(self):
            self.calls_n += 1
            if self.calls_n == 3:        # boot(1) probe(2) ok; re-read blips
                raise RuntimeError("transient")
            return super().position()
    v = _FlakyVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")
    ex.state.legs["trend"].qty = 0.01
    ex.halt("KILL", "manual")
    assert v.position() == 0.0, "flatten must survive one transient re-read"
    assert ex.state.legs["trend"].qty == 0.0


def test_gate_resume_clears_dead_stop_refs(tmp_path):
    """After a failed halt the ledger can hold refs to orders the venue no
    longer honours; the churn guard would then suppress re-placement. Resume
    must verify and clear."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("MARKET", "BUY", 0.01, "seed")          # venue really holds the leg
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert led.stop_cloid is None and led.stop_px is None, \
        "dead stop ref must not survive resume (churn guard would mute it)"
    assert any(e["kind"] == "stop_ref_cleared" for e in ex.state.events)
    assert ex.state.halted is None, "a venue-BACKED leg must resume normally"


def test_gate_boot_reconcile_venue_holds_ledger_flat_blocks_entries(tmp_path):
    """The OTHER side: a crash after an order was sent but before the ledger
    booked it leaves the venue holding what the ledger does not know.
    Re-entering on top would double the position - page, adopt nothing,
    block new entries until it resolves."""
    import json
    from app.mirror import Executor
    v = FakeVenue(mult=0.01)
    v._add("MARKET", "BUY", 0.02, "orphan")
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {}}, open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex._boot_mismatch is True
    assert any(e["kind"] == "position_drift" for e in ex.state.events)
    # entries stay blocked...
    ex.step(target(trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": NOW}, "position": None}))
    assert ex.state.legs["trend"].qty == 0.0, "entered while mismatched"
    # ...until someone resolves the venue side; then the flag clears
    v.orders["orphan"]["status"] = "CANCELLED"
    ex._check_drift(50_000.0)
    assert ex._boot_mismatch is False


def test_gate_fully_filled_entry_not_topped_up(tmp_path):
    """A fully-filled entry re-targeted at the live mid sent a spurious
    market top-up on adverse moves. The entry order's own size is the
    quantity truth; the mid is only the slippage reference."""
    v = FakeVenue(mult=0.01, mid=60_000.0)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.entry_cloid, led.entry_side, led.entry_qty = "T-1-E", "L", 0.01
    v.orders["T-1-E"] = {"type": "MARKET", "side": "BUY", "qty": 0.01,
                         "px": 60_000.0, "status": "FILLED"}
    # adverse move: mid drops, a mid-recomputed want would exceed 0.01
    v._mid = 55_000.0
    ex._enter_from_fill("trend", led, _long_pos(), BLEND, 10_000.0)
    assert not any("-C" in c for c in v.orders if c != "T-1-E"), \
        "spurious top-up chased beyond the entry order's own size"
    assert led.qty == pytest.approx(0.01)


def test_gate_state_load_tolerates_unknown_leg_fields(tmp_path):
    """Roll-back safety: a state file written by a NEWER build must load,
    not brick-and-wipe. Unknown leg fields are dropped."""
    import json
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    json.dump({"halted": "KILL", "legs": {"trend": {
        "qty": 0.01, "stop_n": 4, "chase_n": 2,
        "field_from_the_future": True}}}, open(cfg.state_path, "w"))
    v = FakeVenue(mult=0.01)
    v._add("MARKET", "BUY", 0.01, "seed")
    ex = Executor(v, cfg)
    assert ex.state.halted == "KILL", "state must survive unknown fields"
    assert ex.state.legs["trend"].qty == 0.01
    assert ex.state.legs["trend"].stop_n == 4


def test_gate_pre_hotfix_state_backed_up_once(tmp_path):
    import json, os
    from app.mirror import Executor
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    json.dump({"halted": "", "legs": {}}, open(cfg.state_path, "w"))
    Executor(FakeVenue(), cfg)
    assert os.path.exists(cfg.state_path + ".pre-phantom-fix.bak")


# ---------------------------------------------------------------------------
# Re-review round 3 (2026-08-26): UNKNOWN is not terminal, and no ref is
# cleared without a best-effort cancel first — a confirm-read blip over a
# genuinely-resting stop must never arm a SECOND stop (both fill on trigger
# = naked reversal).
class _BlipStatusVenue(FakeVenue):
    """Returns UNKNOWN for order_status on demand while orders really rest."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.blips = 0                  # consume one UNKNOWN per read while >0
        self.cancels = []

    def order_status(self, cloid):
        if self.blips > 0:
            self.blips -= 1
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        return super().order_status(cloid)

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


def test_gate_confirm_blip_cancels_before_clearing(tmp_path):
    """BLOCKING repro from the re-review: place succeeds, confirm read
    blips. Old code cleared refs and armed a duplicate next poll. Now the
    order is cancelled best-effort BEFORE the refs clear — at most ONE stop
    can ever rest."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)
    led.qty = 0.01
    v.blips = 2                          # confirm read + its retry both blip
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid is None, "must not believe an unconfirmed stop"
    placed = [c for c in v.orders if "-S" in c]
    assert placed and placed[0] in v.cancels, \
        "unconfirmed stop must be cancelled, not abandoned to duplicate"
    # next poll: fresh salt, healthy read -> exactly ONE open stop
    ex._maintain_stop("trend", led, _long_pos())
    open_stops = [c for c, o in v.orders.items()
                  if o["type"] == "STOP" and o["status"] == "OPEN"]
    assert len(open_stops) == 1, f"duplicate stops armed: {open_stops}"


def test_gate_resume_unknown_ref_cancelled_not_abandoned(tmp_path):
    """Resume hygiene on an UNKNOWN ref must cancel first: clearing alone
    would re-place while the old order still rests = two live stops."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("MARKET", "BUY", 0.01, "seed")          # venue really holds the leg
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    v.blips = 2
    ex.resume()
    assert led.stop_cloid is None
    assert "T-1-S74089-1" in v.cancels, "must cancel before clearing"
    assert v.orders["T-1-S74089-1"]["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# Fusion gate (2026-08-26) BLOCKING 2: STOP_REPLACE_MAX only ever watched the
# confirmed-then-vanished door. A stop that never confirms — killed inside the
# ~1s confirm window, or read UNKNOWN forever — cleared its refs and returned,
# so the next poll placed another under a fresh salt, unbounded: 4,320 orders
# a day, the exact storm the cap exists to stop, arriving through the door the
# cap did not watch.
class _AcceptThenCancelVenue(FakeVenue):
    """Accepts every stop, then kills it before the confirm read lands."""
    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        self.orders[cloid]["status"] = "CANCELLED"


def _drive_stop(ex, v, polls=8):
    led = ex.state.legs["trend"]
    for _ in range(polls):
        if ex.state.halted:
            break
        ex._maintain_stop("trend", led, _long_pos())
    return [c for c in v.orders if "-S" in c]


def test_gate_accept_then_cancel_stop_is_bounded(tmp_path):
    from app.mirror import STOP_REPLACE_MAX
    v = _AcceptThenCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")          # venue backs the ledger
    ex.state.legs["trend"].qty = 0.01
    placed = _drive_stop(ex, v)
    assert ex.state.halted == "STOP_UNPLACEABLE", \
        f"unbounded re-placement (halted={ex.state.halted}, n={len(placed)})"
    assert len(placed) <= STOP_REPLACE_MAX + 1, \
        f"placed {len(placed)} stops before halting: {placed}"
    assert any(e["kind"] == "stop_unplaceable" for e in ex.state.events)


def test_gate_persistent_unknown_stop_is_bounded(tmp_path):
    """The other variant of the same hole: reads never resolve, so the stop
    is never believed and never bounded either."""
    from app.mirror import STOP_REPLACE_MAX
    v = _BlipStatusVenue(mult=0.01)
    v.blips = 10_000                     # every read UNKNOWN, forever
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")
    ex.state.legs["trend"].qty = 0.01
    placed = _drive_stop(ex, v)
    assert ex.state.halted == "STOP_UNPLACEABLE"
    assert len(placed) <= STOP_REPLACE_MAX + 1, \
        f"placed {len(placed)} stops before halting: {placed}"


def test_gate_stop_unconfirmed_counter_is_persisted(tmp_path):
    """In-memory, the counter reset on every restart — which is how the
    4,320-order storm survived its first cap. It must ride the state file.

    Asserts a VALUE, not equality of two dicts: `{} == {}` passed while the
    never-confirmed door kept its own in-memory counter, which is precisely
    the defect (re-gate 2026-08-26, vacuous-test finding)."""
    v = _AcceptThenCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    ex.state.legs["trend"].qty = 0.01
    ex._maintain_stop("trend", ex.state.legs["trend"], _long_pos())
    key = f"trend:{NOW}"
    assert ex.state.stop_vanish.get(key) == 1, \
        f"the never-confirmed door did not reach state.stop_vanish: " \
        f"{ex.state.stop_vanish}"
    ex._save_state()
    ex2 = mkexec(tmp_path, v)            # same state path = a "restart"
    assert ex2.state.stop_vanish.get(key) == 1, \
        "stop_vanish must survive a restart or the cap is resettable"


def test_gate_stop_vanish_is_keyed_per_position(tmp_path):
    """MUTATION KILLER: a constant key would let one position's failures
    halt the NEXT one. A new entry_ts starts a fresh allowance."""
    v = _AcceptThenCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos(entry_ts=NOW))
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1
    ex._maintain_stop("trend", led, _long_pos(entry_ts=NOW + 14_400))
    assert ex.state.stop_vanish.get(f"trend:{NOW + 14_400}") == 1, \
        "a new position must start its own count"
    assert f"trend:{NOW}" not in ex.state.stop_vanish, \
        "the superseded position's key must be pruned"


def test_gate_one_poll_counts_one_failure(tmp_path):
    """MUTATION KILLER for the double-bump: a poll where the old stop
    vanished AND its replacement failed to confirm is ONE failed attempt.
    Counting it twice silently cut the allowance from 3 to 2."""
    v = _AcceptThenCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    # seed a stop the venue has already killed -> the CANCELLED door opens,
    # and the replacement then fails to confirm in the SAME call
    v._add("STOP", "SELL", 0.01, "T-1-S74089-0", px=74_089.0)
    v.cancel("T-1-S74089-0")
    led.stop_cloid, led.stop_px = "T-1-S74089-0", 74_089.0
    ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1, \
        f"one poll must count once, got {ex.state.stop_vanish}"


def test_gate_blipped_status_on_a_working_stop_does_not_halt(tmp_path):
    """A blip on the read of an EXISTING stop must not be mistaken for the
    stop having died: UNKNOWN is not CANCELLED, so no vanish is recorded."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    for i in range(1, 21):
        if i % 5 == 0:
            v.blips = 2
        pos = dict(_long_pos())
        pos["stop"] = 74_000.0 + i * 500.0
        ex._maintain_stop("trend", led, pos)
        assert ex.state.halted is None, \
            f"halted at ratchet {i} on isolated blips: {ex.state.stop_vanish}"
    assert led.stop_cloid, "should end the run protected"
    assert not (getattr(ex.state, "stop_vanish", {}) or {}), \
        "an UNKNOWN read of a live stop is not a vanish"


class _FlakyPlaceVenue(FakeVenue):
    """Some placements die before the confirm read; others stick."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.kill_next = False

    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        if self.kill_next:
            self.orders[cloid]["status"] = "CANCELLED"


def test_gate_intermittent_failures_do_not_accumulate_into_a_halt(tmp_path):
    """MUTATION KILLER for the N1 reset. Protection that WORKS must clear the
    counter, or isolated transients spread across a long position accumulate
    into STOP_UNPLACEABLE and force-flatten a winning trade out of a stop
    that is working fine.

    Alternating fail/succeed: with the reset the count oscillates 1,0,1,0 and
    never halts; without it, it marches 1,2,3,4 and halts on the fourth
    failure. Deleting the reset must FAIL this test."""
    v = _FlakyPlaceVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    for i in range(1, 9):
        v.kill_next = (i % 2 == 1)       # odd polls fail, even polls stick
        pos = dict(_long_pos())
        pos["stop"] = 74_000.0 + i * 500.0
        ex._maintain_stop("trend", led, pos)
        assert ex.state.halted is None, \
            f"halted at poll {i}: a working stop did not reset the counter"
    assert led.stop_cloid, "should end the run protected"


def test_gate_reset_does_not_defeat_the_accept_then_cancel_cap(tmp_path):
    """The dangerous half of N1's fix. In a vanish storm EVERY poll both
    vanishes and re-places SUCCESSFULLY, so an unconditional reset-on-confirm
    would clear the counter every poll and the cap would never trip — which
    is the original 4,320-order bug, reintroduced by its own fix."""
    class _KillAfterConfirmVenue(FakeVenue):
        """Every stop confirms OPEN on its confirm read, and is dead by the
        next poll's check — the real accept-then-kill storm, where EVERY
        placement succeeds and every one of them is gone a poll later."""
        def __init__(self, **kw):
            super().__init__(**kw)
            self.reads = {}

        def order_status(self, cloid):
            n = self.reads[cloid] = self.reads.get(cloid, 0) + 1
            if n >= 2 and self.orders.get(cloid, {}).get("status") == "OPEN":
                self.orders[cloid]["status"] = "CANCELLED"
            return super().order_status(cloid)

    v = _KillAfterConfirmVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    for _ in range(10):
        if ex.state.halted:
            break
        ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.halted == "STOP_UNPLACEABLE", \
        "reset-on-confirm re-opened the unbounded vanish storm"


def test_gate_healthy_stop_never_touches_the_counter(tmp_path):
    """The cap must not creep on ordinary trail re-placement, or a long
    winning position halts itself out of a working stop."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")
    led = ex.state.legs["trend"]
    led.qty = 0.01
    for trig in (74_000.0, 75_000.0, 76_000.0, 77_000.0, 78_000.0, 79_000.0):
        pos = dict(_long_pos())
        pos["stop"] = trig
        ex._maintain_stop("trend", led, pos)
    assert ex.state.halted is None, "healthy ratcheting must not halt"
    assert not (getattr(ex.state, "stop_vanish", {}) or {}), \
        "confirmed placements must leave the failure counter untouched"


# ---------------------------------------------------------------------------
# Fusion gate (2026-08-26) BINDING 3: the ramp's two slippage readers must
# agree. They did not — main.py excluded void fills, _live_fill_count did
# not — so at the first boot after _void_absurd_fills auto-drill would read a
# real 8/10 as complete while /pulse correctly showed 8.
def test_gate_live_fill_count_excludes_void(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.fills = [{"live": True}, {"live": True, "void": True},
                      {"live": True}, {"live": False}, {"void": True}]
    assert ex._live_fill_count() == 2


def test_gate_slippage_readers_agree_on_void(tmp_path):
    """Parity checked against the ACTUAL ramp render main.py serves, not a
    copy of its arithmetic. This is the exact first-boot state after
    _void_absurd_fills: 8 real fills + the 2 phantom rows."""
    from app.main import _ramp_v4
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.fills = ([{"live": True} for _ in range(8)]
                      + [{"live": True, "void": True} for _ in range(2)])
    row = _ramp_v4(ex.state)["rows"]["slippage_sample"]
    assert row["have"] == ex._live_fill_count() == 8, \
        f"ramp render says {row['have']}, mirror says {ex._live_fill_count()}"
    assert row["met"] is False, "8 real fills must not read as a met 10"
    # ...and the terminal condition auto-drill reads must agree with both:
    # with the cycle row already satisfied, only the slippage count is left,
    # so this is exactly where the two readers used to diverge.
    from app.mirror import DRILL_CYCLE_NEED
    ex.state.coverage_live = {"drill_cycle": DRILL_CYCLE_NEED}
    assert ex._needed_auto_drill() == "cycle", \
        "auto-drill read 8 real fills + 2 voids as a complete sample"


# ---------------------------------------------------------------------------
# Fusion gate (2026-08-26) BLOCKING 1: the resume hygiene that repairs a
# failed halt could itself arm the naked stop the incident was about. On a
# leg the ledger believes HOLDS, a dead ref is cleared only once the venue
# BACKS the ledger — because clearing it routes _maintain_stop to its
# first-placement path, which is not reduce-only.
def test_gate_resume_dead_ref_on_flat_venue_halts_not_clears(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")             # dead ref...
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()                          # ...on a venue that holds NOTHING
    assert ex.state.halted == "LEDGER_DIVERGENCE", \
        f"must halt, not clear into a naked re-place (halted={ex.state.halted})"
    assert any(e["kind"] == "ledger_divergence" for e in ex.state.events)
    stops = [c for c, o in v.orders.items()
             if o["type"] == "STOP" and o["status"] == "OPEN"]
    assert not stops, f"a NAKED stop was armed on a flat venue: {stops}"


def test_gate_resume_dead_ref_opposite_side_halts(tmp_path):
    """Venue holds the OPPOSITE side: same divergence, same halt. A
    same-sign-only check would sail past this and arm a stop that doubles
    the wrong-way position instead of closing it."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("MARKET", "SELL", 0.01, "seed")         # venue is SHORT
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert ex.state.halted == "LEDGER_DIVERGENCE"


def test_gate_resume_dead_ref_blind_venue_keeps_ref(tmp_path):
    """Unreadable venue: the ref is KEPT (the stop may genuinely rest) and
    the operator gets an ACTION page. Clearing blind is the naked-stop hole;
    halting blind is not available either — _halt_locked would cancel
    nothing anyway. _maintain_stop's CANCELLED dispatch corroborates before
    it ever replaces, so keeping the ref cannot arm anything."""
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.events.clear()
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert led.stop_cloid == "T-1-S74089-1", "must not clear on a blind read"
    assert any(e["kind"] == "stop_ref_unverified" and e["level"] == "RED"
               for e in ex.state.events)


def test_gate_resume_dead_ref_on_flat_leg_still_clears(tmp_path):
    """qty == 0: nothing to protect, so no corroboration is owed and the
    stale ref is simply cleared. The corroboration must not become a way for
    dead refs to accumulate on flat legs."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.0, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert led.stop_cloid is None and ex.state.halted is None


# ---------------------------------------------------------------------------
# Re-gate (2026-08-26) B1: `venue.position()` is the NET across BOTH legs on
# ONE product. The corroboration compared it to a SINGLE leg's qty, which was
# wrong in both directions. Every test below uses a TWO-LEG book, which the
# entire prior test suite never did — and it uses `pullback`, FIRST in LEGS,
# which every prior stop test avoided (they all used `trend`, and this repo
# has already been burned by exactly that iteration-order blind spot).
def _two_leg(ex, pull_qty, trend_qty):
    ex.state.legs["pullback"].qty = pull_qty
    ex.state.legs["trend"].qty = trend_qty


def test_gate_hedged_book_is_not_divergence(tmp_path):
    """B1b: S3 long + S4 short is an ORDINARY S5 state. At 0.01 granularity
    both legs quantize to one contract, so the venue nets to 0.00 — which the
    per-leg test read as 'the venue holds nothing' and halted a perfectly
    correct ledger. Fires on the SILENT 00:00 UTC rearm too."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed-long")
    v._add("MARKET", "SELL", 0.01, "seed-short")     # venue net 0.00
    _two_leg(ex, +0.01, -0.01)                       # ledger sum 0.00 - agrees
    verdict, net, want = ex._stop_backing()
    assert verdict == "ok", f"healthy hedged book read as {verdict}"
    assert net == 0.0 and want == 0.0


def test_gate_hedged_book_resume_does_not_halt(tmp_path):
    """The same thing end-to-end through the path that actually halts."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed-long")
    v._add("MARKET", "SELL", 0.01, "seed-short")
    _two_leg(ex, +0.01, -0.01)
    v._add("STOP", "BUY", 0.01, "T-1-S80000-1", px=80_000.0)
    v.cancel("T-1-S80000-1")                         # dead ref on the short leg
    ex.state.legs["trend"].stop_cloid = "T-1-S80000-1"
    ex.state.legs["trend"].stop_px = 80_000.0
    ex.state.halted = "KILL"
    ex.resume()
    assert ex.state.halted is None, \
        "a legitimate hedged book was halted as LEDGER_DIVERGENCE"


def test_gate_phantom_leg_hiding_behind_a_real_leg(tmp_path):
    """B1a, the money-losing direction. Venue truly holds ONLY trend +0.01.
    The ledger also claims a PHANTOM pullback +0.01. The per-leg test passed
    (net +0.01 is non-zero and same-signed as pullback's +0.01), the ref was
    cleared, and 0.02 BTC of SELL stops went out against 0.01 of real
    position — on trigger, a net 0.01 NAKED SHORT."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")            # ONLY trend is real
    _two_leg(ex, +0.01, +0.01)                       # ledger sum +0.02
    verdict, net, want = ex._stop_backing()
    assert verdict == "diverged", \
        f"phantom leg hid behind the real one: {verdict} (net {net}, want {want})"


def test_gate_phantom_leg_blocks_placement_on_the_pullback_leg(tmp_path):
    """Same fixture, driven end-to-end through PULLBACK — first in LEGS, and
    untouched by every prior stop test."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "seed")
    _two_leg(ex, +0.01, +0.01)
    ex._maintain_stop("pullback", ex.state.legs["pullback"], _long_pos())
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    stops = [c for c, o in v.orders.items()
             if o["type"] == "STOP" and o["status"] == "OPEN"]
    assert not stops, f"naked stops armed against a phantom leg: {stops}"


def test_gate_venue_holding_more_than_the_ledger_is_not_divergence(tmp_path):
    """Asymmetry, deliberate: a reduce-sized stop against a LARGER venue
    position still reduces. Surplus is position_drift's job, not this
    check's — treating it as divergence would halt on every rounding
    difference."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.02, "seed")            # venue holds MORE
    _two_leg(ex, 0.0, +0.01)
    assert ex._stop_backing()[0] == "ok"


def test_gate_short_ledger_against_flat_venue_diverges(tmp_path):
    """MUTATION KILLER for dropping the magnitude half of the predicate. For
    a LONG ledger the sign test alone happens to catch a flat venue
    (`True != False`); for a SHORT one it does not (`False != False`), so a
    sign-only check clears the ref and arms a naked BUY stop. No prior test
    used a short ledger leg."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _two_leg(ex, 0.0, -0.01)                         # venue holds nothing
    verdict, net, want = ex._stop_backing()
    assert verdict == "diverged", \
        f"short ledger vs flat venue read as {verdict} (net {net}, want {want})"


def test_gate_short_leg_placement_refused_on_flat_venue(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _two_leg(ex, 0.0, -0.01)
    pos = {"side": "S", "entry_ts": NOW, "signal_ts": NOW - 14_400,
           "stop": 80_000.0, "exit_flag": None}
    ex._maintain_stop("trend", ex.state.legs["trend"], pos)
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert not [c for c, o in v.orders.items() if o["type"] == "STOP"], \
        "armed a naked BUY stop for a phantom short"


# ---------------------------------------------------------------------------
# Re-gate B3: "keeping the ref" is not a barrier. _handle_stop_vanished only
# opens on a literal CANCELLED status; a BLIND read returns UNKNOWN, falls
# through the churn guard, and once the chandelier ratchets past
# stop_replace_bps went straight to place_stop with NO position read at all.
def test_gate_trail_ratchet_places_nothing_on_a_blind_venue(tmp_path):
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.events.clear()
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74000-1", 74_000.0
    v._add("STOP", "SELL", 0.01, "T-1-S74000-1", px=74_000.0)
    for trig in (74_500.0, 75_000.0, 75_600.0, 76_300.0):   # each >5bp apart
        pos = dict(_long_pos())
        pos["stop"] = trig
        ex._maintain_stop("trend", led, pos)
    new_stops = [c for c in v.orders if c != "T-1-S74000-1"]
    assert not new_stops, \
        f"placed {len(new_stops)} stops with position() raising: {new_stops}"
    assert any(e["kind"] == "stop_backing_blind" for e in ex.state.events)


def test_gate_first_placement_refused_on_a_blind_venue(tmp_path):
    """The other half of the same choke point: no ref at all, blind venue."""
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid is None
    assert not [c for c, o in v.orders.items() if o["type"] == "STOP"]
    assert ex.state.halted is None, "blind is retryable, not a halt"


# ---------------------------------------------------------------------------
# Re-gate B2: the CORRELATED outage — status UNKNOWN *and* position
# unreadable, which is ONE API failure and is exactly what 2026-08-26 looked
# like. Cancel-before-corroborate sent the cancel and then kept the ref:
# killed a live stop and went on believing in it.
class _CorrelatedOutageVenue(FakeVenue):
    """Reads are down (status UNKNOWN, position raises); writes still work."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cancels = []

    def order_status(self, cloid):
        return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}

    def position(self):
        raise RuntimeError("position read down")

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


def test_gate_correlated_outage_resume_touches_nothing(tmp_path):
    v = _CorrelatedOutageVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.events.clear()
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert "T-1-S74089-1" not in v.cancels, \
        "cancelled a live stop it then could not replace"
    assert v.orders["T-1-S74089-1"]["status"] == "OPEN", \
        "the only protection on a real position was killed"
    assert led.stop_cloid == "T-1-S74089-1", "ref must be kept"
    assert any(e["kind"] == "stop_ref_unverified" for e in ex.state.events)


# ---------------------------------------------------------------------------
# Re-gate B4: _halt_locked verifies every LEDGER-known order is terminal
# before zeroing. Clearing the refs BEFORE halting made that loop vacuous, so
# when both cancel paths silently failed the halt zeroed the ledger under
# armed stops and reported success.
def test_gate_unplaceable_halt_cannot_zero_under_a_live_stop(tmp_path):
    class _SilentCancelVenue(FakeVenue):
        """Writes work; status reads UNKNOWN; every cancel silently no-ops."""
        def order_status(self, cloid):
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}

        def cancel(self, cloid):
            pass                         # silently cancels nothing

        def cancel_all(self):
            pass

    v = _SilentCancelVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    _hold(v)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    for _ in range(8):
        if ex.state.halted:
            break
        ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.halted == "STOP_UNPLACEABLE"
    live = [c for c, o in v.orders.items()
            if o["type"] == "STOP" and o["status"] == "OPEN"]
    assert live, "fixture bug: expected surviving stops"
    # the halt must have REFUSED to zero, and said so
    assert led.qty == 0.01, \
        f"ledger zeroed under {len(live)} armed stops on a halted book"
    assert any(e["kind"] == "halt_error" for e in ex.state.events), \
        "a halt that could not verify its cancels must page halt_error"


# ---------------------------------------------------------------------------
# Re-gate N2: a halt whose flatten FAILED keeps its divergent ledger on
# purpose, so LEDGER_DIVERGENCE re-fired on every plain /resume — a deadlock
# only a redeploy could break.
class _StatusBlindVenue(FakeVenue):
    """Position reads fine; ORDER status never resolves. This is what makes
    the deadlock durable: _halt_locked refuses to zero a ledger it cannot
    verify is un-armed, so halt_error KEEPS the divergent ledger, and the
    next /resume finds exactly the state that halted it. (A halt that CAN
    verify its cancels self-heals the ledger, so a plain FakeVenue does not
    reproduce this.)"""
    def order_status(self, cloid):
        return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}


def test_gate_plain_resume_deadlocks_on_a_divergent_ledger(tmp_path):
    """Documents the deadlock the adopt path exists to break: the operator
    does exactly what the halt_error page told them to do — flatten manually
    on Coinbase — and /resume STILL will not clear, because the ledger keeps
    claiming the position."""
    v = _StatusBlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "DRAWDOWN"
    for _ in range(2):
        ex.resume()
        assert ex.state.halted == "LEDGER_DIVERGENCE"
        assert led.qty == 0.01, "halt_error keeps the ledger, by design"
    assert any(e["kind"] == "halt_error" for e in ex.state.events)


def test_gate_adopt_venue_breaks_the_deadlock(tmp_path):
    v = _StatusBlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "DRAWDOWN"
    ex.resume()                          # deadlocked...
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    ex.resume(adopt_venue=True)          # ...and broken in band
    assert ex.state.halted is None, "adopt must clear the halt"
    assert led.qty == 0.0 and led.stop_cloid is None
    assert v.orders["T-1-S74089-1"]["status"] == "CANCELLED", \
        "adopt must cancel the stop it is about to forget about"
    assert any(e["kind"] == "adopt_venue" for e in ex.state.events)


def test_gate_adopt_venue_refuses_on_a_blind_venue(tmp_path):
    """Adopting venue truth requires READING the venue. A blind adopt would
    zero a live position's ledger on no evidence at all."""
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid = 0.01, "T-1-S74089-1"
    ex.state.halted = "DRAWDOWN"
    ex.resume(adopt_venue=True)
    assert ex.state.halted == "DRAWDOWN", "halt must stand"
    assert led.qty == 0.01, "ledger must be untouched"
    assert any(e["kind"] == "adopt_venue_blind" for e in ex.state.events)


def test_gate_adopt_venue_with_real_position_blocks_entries(tmp_path):
    """Venue holds something the ledger cannot attribute to a leg: adopt the
    refs but refuse the split, and block entries exactly as boot does."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.02, "seed")
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid = 0.01, "T-1-S74089-1"
    ex.state.halted = "DRAWDOWN"
    ex.resume(adopt_venue=True)
    assert ex._boot_mismatch is True, "entries must stay blocked"
    assert any(e["kind"] == "adopt_venue_partial" for e in ex.state.events)


# ---------------------------------------------------------------------------
# Re-gate N3: _verify_stop_refs can HALT, and the rearm announced success
# anyway — "cleared" and "halted" on the phone in the same minute.
def test_gate_rearm_does_not_announce_a_clear_it_did_not_make(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.cfg.kelly_m = 0.05
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "DAILY_LOSS"
    ex.state.day_key = "1999-01-01"
    ex._roll_day(50_000.0)
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert not any(e["kind"] == "auto_rearm" for e in ex.state.events), \
        "announced DAILY_LOSS cleared while the book was halted"
    assert any(e["kind"] == "auto_rearm_blocked" for e in ex.state.events)


def test_gate_resume_working_stop_kept(tmp_path):
    """A confirmed-OPEN stop must survive resume untouched."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "KILL"
    ex.resume()
    assert led.stop_cloid == "T-1-S74089-1", "working stop must be kept"
    assert v.orders["T-1-S74089-1"]["status"] == "OPEN"


def test_gate_halt_unknown_status_refuses_to_zero(tmp_path):
    """Correlated outage: cancel_all no-ops AND order_status is UNKNOWN.
    The old verification passed vacuously and zeroed refs past an armed
    orphan stop. UNKNOWN must fail the halt verification."""
    class _V(FakeVenue):
        def cancel_all(self):
            pass

        def order_status(self, cloid):
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
    v = _V(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    v._add("MARKET", "BUY", 0.01, "seed")
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    led.qty, led.stop_cloid = 0.01, "T-1-S74089-1"
    ex.halt("KILL", "manual")
    assert led.stop_cloid == "T-1-S74089-1", "zeroed past an unverifiable order"
    assert any(e["kind"] == "halt_error" for e in ex.state.events)


def test_gate_externally_cancelled_stop_replaced_and_paged(tmp_path):
    """A stop cancelled outside our sight fell through the churn guard and
    was held as a dead ref silently forever. Now: page + re-place under a
    fresh salt in the same maintenance pass."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)                              # venue backs the ledger
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos())
    first = led.stop_cloid
    v.cancel(first)                       # external cancel (operator/venue)
    ex._maintain_stop("trend", led, _long_pos())
    # fused semantics (merge 2026-08-26): CANCELLED routes through main's
    # _handle_stop_vanished - venue-corroborated, capped, paged as
    # stop_vanished - then re-places under this branch's fresh salt
    assert any(e["kind"] == "stop_vanished"
               for e in ex.state.events), "external cancel must page"
    assert led.stop_cloid and led.stop_cloid != first
    assert v.orders[led.stop_cloid]["status"] == "OPEN"


def test_gate_boot_reconcile_survives_transient_read(tmp_path):
    """One boot-time blip must not disarm the phantom-clear."""
    import json
    from app.mirror import Executor
    class _V(FakeVenue):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.n = 0

        def position(self):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("boot blip")
            return super().position()
    v = _V(mult=0.01)
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {"trend": {"qty": 0.01}}},
              open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex.state.legs["trend"].qty == 0.0, \
        "phantom must clear despite one transient read"


def test_gate_boot_mismatch_clears_only_on_exact_agreement(tmp_path):
    """A sub-tolerance orphan must NOT unblock entries."""
    import json
    from app.mirror import Executor
    v = FakeVenue(mult=0.01)
    v._add("MARKET", "BUY", 0.01, "orphan")     # tiny orphan, ~$600
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    json.dump({"halted": "", "legs": {}}, open(cfg.state_path, "w"))
    ex = Executor(v, cfg)
    assert ex._boot_mismatch is True
    ex._check_drift(50_000_000.0)         # huge equity => inside $ tolerance
    assert ex._boot_mismatch is True, \
        "dollar tolerance must not unblock while the orphan rests"
    v.orders["orphan"]["status"] = "CANCELLED"
    ex._check_drift(50_000_000.0)
    assert ex._boot_mismatch is False


def test_gate_entry_cloids_salted_and_burned(tmp_path):
    """Entries carry the same burned-before-send salt as stops/chases: the
    boot-mismatch resolution path re-sends an entry the venue already saw."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": -1.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(trend=pend))
    assert ex.state.legs["trend"].entry_cloid == f"T-{NOW}-E1"
    ex2 = mkexec(tmp_path, v)
    assert ex2.state.legs["trend"].entry_n == 1, "salt must persist"


def test_gate_stop_n_burned_before_order_reaches_venue(tmp_path):
    """MUTATION KILLER: saving the counter AFTER the order would pass every
    ordinary test but reintroduce reuse-on-crash. The venue itself checks
    the persisted state at the moment the order arrives."""
    import json
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    _hold(v)
    led.qty = 0.01
    seen = {}
    real_place_stop = v.place_stop
    def checking_place_stop(side, qty, trigger_px, cloid):
        on_disk = json.load(open(ex.cfg.state_path))
        seen["disk_stop_n"] = on_disk["legs"]["trend"]["stop_n"]
        real_place_stop(side, qty, trigger_px, cloid)
    v.place_stop = checking_place_stop
    ex._maintain_stop("trend", led, _long_pos())
    assert seen["disk_stop_n"] == led.stop_n, \
        "stop_n must be PERSISTED before the order is sent"


# ---------------------------------------------------------------------------
# Round-4 mutant killers (review round 3: fixes without killers do not close
# bindings in this repo's convention).
def test_gate_M14_unknown_entry_confirm_keeps_ref_no_resend(tmp_path):
    """BLOCKING repro: pullback entry placed, confirm reads UNKNOWN. The ref
    must be KEPT so the identity dedupe suppresses the next poll's re-send —
    the round-3 code dropped it and re-sent FULL SIZE every 20s (each fill
    real on a marketable limit, ledger booking nothing)."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    v.blips = 2                          # confirm + retry both UNKNOWN
    ex.step(target(pull=pend))
    led = ex.state.legs["pullback"]
    assert led.entry_cloid, "UNKNOWN must keep the ref (possibly live)"
    n_limits = len([c for c, o in v.orders.items() if o["type"] == "LIMIT"])
    for _ in range(3):                   # subsequent polls, same pending
        ex.step(target(pull=pend))
    n_after = len([c for c, o in v.orders.items() if o["type"] == "LIMIT"])
    assert n_after == n_limits == 1, \
        f"re-sent a possibly-live entry: {n_limits} -> {n_after}"
    assert any(e["kind"] == "entry_unconfirmed" for e in ex.state.events)


def test_gate_M14b_confirmed_dead_entry_cleared_and_retried(tmp_path):
    """The venue-CONFIRMED terminal-and-unfilled case must still clear and
    allow a fresh salted attempt while the signal stands."""
    class _RejectingVenue(FakeVenue):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.reject_next = 0

        def place_limit(self, side, qty, px, cloid, post_only=True):
            super().place_limit(side, qty, px, cloid, post_only=post_only)
            if self.reject_next > 0:
                self.reject_next -= 1
                self.orders[cloid]["status"] = "CANCELLED"
    v = _RejectingVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    v.reject_next = 1
    ex.step(target(pull=pend))
    assert ex.state.legs["pullback"].entry_cloid is None
    ex.step(target(pull=pend))           # retry under a fresh salt
    led = ex.state.legs["pullback"]
    assert led.entry_cloid and led.entry_cloid.endswith("-E2")
    assert v.orders[led.entry_cloid]["status"] == "OPEN"


def test_gate_M2_fill_watch_survives_unknown_status(tmp_path):
    """A truthy UNKNOWN dict silently dropped the watch, starving the
    slippage sample on one API blip."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.01, "W-1")
    v.orders["W-1"]["status"] = "OPEN"
    ex._watch_fill("trend", "entry", "W-1", 60_000.0, "BUY")
    v.blips = 1
    ex._poll_fill_watch()
    assert ex._fill_watch, "UNKNOWN must keep the watch, not drop it"
    v.orders["W-1"]["status"] = "FILLED"
    ex._poll_fill_watch()
    assert any(f["cloid"] == "W-1" for f in ex.state.fills), \
        "the fill must still be recorded after the blip clears"


def test_gate_M1_cb_order_status_api_error_is_unknown(tmp_path, monkeypatch):
    """cb.py's exception branch must return UNKNOWN, never None (None means
    only no-handle). Pins the tri-state at the adapter."""
    client = _StubClient()
    def boom(oid):
        raise RuntimeError("api down")
    client.get_order = boom
    v = _mk_cb_venue(tmp_path, monkeypatch, client)
    v._orders["X-1"] = "oid-x"           # handle exists, API fails
    st = v.order_status("X-1")
    assert st is not None and st.get("status") == "UNKNOWN"
    assert v.order_status("NO-HANDLE") is None


def test_gate_M9_auto_rearm_runs_stop_ref_hygiene(tmp_path):
    """Round-2 binding 5 with the demanded repro: failed-halt stale ref +
    midnight UTC auto-rearm. The rearm must route through the same hygiene
    as manual resume, or the churn guard suppresses re-placement against a
    dead order on the AUTOMATIC path."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.cfg.kelly_m = 0.05                # inside the auto-rearm regime
    led = ex.state.legs["trend"]
    v._add("MARKET", "BUY", 0.01, "seed")  # venue really holds the leg
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")             # the venue no longer honours it
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "DAILY_LOSS"
    ex.state.day_key = "1999-01-01"      # force the rollover branch
    ex._roll_day(50_000.0)
    assert ex.state.halted is None, "auto-rearm must clear DAILY_LOSS"
    assert led.stop_cloid is None, \
        "auto-rearm bypassed stop-ref hygiene: dead ref survives"
    assert any(e["kind"] == "stop_ref_cleared" for e in ex.state.events)


def test_gate_M9b_auto_rearm_halts_on_divergence(tmp_path):
    """The same automatic path, with the venue NOT backing the ledger: the
    rearm must refuse to clear into a naked re-place and halt instead
    (fusion gate 2026-08-26). A silent midnight rearm is the worst possible
    place for the clear-then-arm hole - nobody is watching."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.cfg.kelly_m = 0.05
    led = ex.state.legs["trend"]
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    v.cancel("T-1-S74089-1")
    led.qty, led.stop_cloid, led.stop_px = 0.01, "T-1-S74089-1", 74_089.0
    ex.state.halted = "DAILY_LOSS"
    ex.state.day_key = "1999-01-01"
    ex._roll_day(50_000.0)
    assert ex.state.halted == "LEDGER_DIVERGENCE", \
        "rearm cleared a dead ref against a flat venue"
    stops = [c for c, o in v.orders.items()
             if o["type"] == "STOP" and o["status"] == "OPEN"]
    assert not stops, f"a NAKED stop was armed at rollover: {stops}"


def test_gate_M12_entry_n_burned_before_order_reaches_venue(tmp_path):
    import json
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    seen = {}
    real_place_limit = v.place_limit
    def checking_place_limit(side, qty, px, cloid, post_only=True):
        on_disk = json.load(open(ex.cfg.state_path))
        seen["disk_entry_n"] = on_disk["legs"]["pullback"]["entry_n"]
        real_place_limit(side, qty, px, cloid, post_only=post_only)
    v.place_limit = checking_place_limit
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    ex.step(target(pull=pend))
    assert seen["disk_entry_n"] == ex.state.legs["pullback"].entry_n, \
        "entry_n must be PERSISTED before the order is sent"


def test_gate_M13_new_pager_kinds_are_rate_limited(tmp_path, monkeypatch):
    """stop_unconfirmed can fire every 20s poll during an outage - the pager
    must not (round-2 binding 10: ~180 pages/hour otherwise)."""
    from app import alerts
    sent = []
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    for kind in ("stop_unconfirmed", "entry_unconfirmed",
                 "stop_ref_cleared", "stop_vanished"):
        sent.clear()
        for i in range(4):
            ex._event("RED", kind, f"{kind} occurrence {i}")
        assert len(sent) == 1, f"{kind} paged {len(sent)}x inside cooldown"


def test_gate_C1_blipped_reread_keeps_entry_ref(tmp_path):
    """Final-gate C1 killer: first confirm read says CANCELLED, the re-read
    BLIPS (UNKNOWN - falsy filled_qty). Clearing on that blip violated the
    invariant inside the very block that closed it. The ref must be KEPT
    and no re-send may follow."""
    class _V(FakeVenue):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.seq = []                # scripted statuses, then real

        def order_status(self, cloid):
            if self.seq:
                stt = self.seq.pop(0)
                if stt is None:
                    return None
                return {"status": stt, "filled_qty": 0.0, "avg_price": None}
            return super().order_status(cloid)
    v = _V(mult=0.01)
    ex = mkexec(tmp_path, v)
    pend = {"pending": {"side": "L", "limit": 59_000.0, "signal_ts": NOW},
            "position": None}
    # _ostat first read CANCELLED -> re-read blips UNKNOWN
    v.seq = ["CANCELLED", "UNKNOWN"]
    ex.step(target(pull=pend))
    led = ex.state.legs["pullback"]
    assert led.entry_cloid, "blipped re-read must KEEP the ref"
    n = len([c for c, o in v.orders.items() if o["type"] == "LIMIT"])
    ex.step(target(pull=pend))           # dedupe must hold
    n2 = len([c for c, o in v.orders.items() if o["type"] == "LIMIT"])
    assert n2 == n == 1, f"re-sent past a possibly-live entry: {n}->{n2}"
    # and a None re-read (no handle) must behave the same
    v2 = _V(mult=0.01)
    ex2 = mkexec(tmp_path / "b", v2)
    v2.seq = ["CANCELLED", None]
    ex2.step(target(pull=pend))
    assert ex2.state.legs["pullback"].entry_cloid, \
        "None re-read must KEEP the ref too"

# ---------------------------------------------------------------------------
# (merged 2026-08-26: main's stop_vanished suite below, hotfix suite above)
# --- venue stop verification (live find 2026-08-24) ------------------------
def _armed_leg(tmp_path):
    """Executor holding a trend long with a venue stop armed."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"side": "L", "entry_price": 68525.0, "entry_ts": 1787155200,
           "signal_ts": 1787140800, "stop": 73000.0, "exit_flag": None}
    ex.step(target(trend={"pending": None, "position": pos}))
    return ex, v, pos


def test_gate_venue_cancelled_stop_is_detected_and_replaced(tmp_path):
    """A stop CANCELLED at the venue is not protection. Previously only
    FILLED was handled, so stop_cloid stayed set, the 5bp churn guard
    suppressed the replacement, and /pulse still read stop_placed=true. The
    chandelier only ratchets UP, so self-repair never came in a falling
    market - silent exactly when the stop matters."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    old_cloid = led.stop_cloid
    assert old_cloid and led.stop_px == 73000.0
    v.orders[old_cloid]["status"] = "CANCELLED"        # venue-side death
    ex.step(target(trend={"pending": None, "position": pos}))  # trail UNCHANGED
    assert led.stop_cloid is not None
    assert led.stop_cloid != old_cloid, "no replacement stop was placed"
    assert v.orders[led.stop_cloid]["status"] != "CANCELLED"
    assert any(e["kind"] == "stop_vanished" and e["level"] == "RED"
               for e in ex.state.events), [e["kind"] for e in ex.state.events]
    # the replacement must not reuse the dead order's client id: the cloid is
    # derived from (leg, entry_ts, trigger), so an unchanged trail would
    # regenerate it verbatim and Coinbase rejects duplicate cloids
    # fused semantics: EVERY placement carries the persisted burned salt
    # (strictly stronger than the old conditional -R nonce: ids can never
    # repeat, crash included)
    assert led.stop_cloid != "T-1787155200-S73000-1"
    assert led.stop_cloid.rsplit("-", 1)[-1].isdigit(), led.stop_cloid
    assert led.stop_px == 73000.0


def test_gate_open_or_unknown_stop_never_duplicated(tmp_path):
    """The other half: QUEUED/PENDING map to OPEN and an API failure returns
    None. Neither may provoke a second stop on the same position - that was
    the 2026-08-11 doubled-position failure mode."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    cloid = led.stop_cloid
    before = len([c for c in v.calls if c[0] == "STOP"])
    for _ in range(3):
        ex.step(target(trend={"pending": None, "position": pos}))
    assert led.stop_cloid == cloid
    assert len([c for c in v.calls if c[0] == "STOP"]) == before
    # API failure -> order_status returns None -> still no duplicate
    orig = v.order_status
    v.order_status = lambda c: None
    try:
        for _ in range(3):
            ex.step(target(trend={"pending": None, "position": pos}))
    finally:
        v.order_status = orig
    assert led.stop_cloid == cloid
    assert len([c for c in v.calls if c[0] == "STOP"]) == before
    assert not [e for e in ex.state.events if e["kind"] == "stop_vanished"]


def test_gate_filled_stop_still_takes_the_fill_path(tmp_path):
    """The pre-existing FILLED branch must be untouched by the new one."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    v.orders[led.stop_cloid]["status"] = "FILLED"
    ex.step(target(trend={"pending": None, "position": pos}))
    assert led.qty == 0.0 and led.stop_cloid is None and led.stop_px is None
    assert any(e["kind"] == "stop_filled_on_venue" for e in ex.state.events)
    assert not [e for e in ex.state.events if e["kind"] == "stop_vanished"]


def test_gate_auto_drill_wait_reason_is_visible(tmp_path):
    """Auto-drill blocked behind an open position looked identical to a
    broken one: it returned on a bare `# quietly wait`."""
    ex, v, pos = _armed_leg(tmp_path)
    ex.cfg.auto_drill = True
    ex.cfg.dry_run = False
    ex.cfg.auto_drill_spacing_s = 0
    ex._maybe_auto_drill(True)
    assert ex.state.drills == []
    assert ex._auto_drill_wait == "leg_not_flat:trend", ex._auto_drill_wait
    ex.cfg.auto_drill = False
    ex._maybe_auto_drill(True)
    assert ex._auto_drill_wait == "disarmed"


def test_gate_gate_constants_have_one_source():
    """drill_cycle=3 lived in mirror AND main, slippage=10 only in main.
    They must not be able to drift apart again."""
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "app", "main.py")).read()
    # `is` on small ints is CPython interning - it holds for any literal 3/10,
    # so the only real assertion is that main.py does not hardcode them
    assert not re.search(r'"drill_cycle":\s*\d', src), "drill_cycle hardcoded"
    assert not re.search(r'"slippage_sample",\s*\d', src), "slippage hardcoded"
    assert "DRILL_CYCLE_NEED" in src and "SLIPPAGE_SAMPLE_NEED" in src


# --- counter-agent fixes to the stop/drill change (2026-08-24) -------------
def test_gate_vanished_stop_never_armed_against_a_flat_venue(tmp_path):
    """DEF-1 (regression introduced by the first cut): _maintain_stop gates on
    the LEDGER only. Venue flat + stale ledger + CANCELLED stop meant a fresh
    stop was placed - and place_stop is NOT reduce-only, so if it triggered it
    OPENED an unintended short. Reachable via an operator flatten, a
    liquidation, or dated-contract settlement."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    v.orders[led.stop_cloid]["status"] = "CANCELLED"
    for o in v.orders.values():                    # venue goes flat under us
        o["status"] = "CANCELLED"
    assert v.position() == 0.0
    before = len([c for c in v.calls if c[0] == "STOP"])
    ex.step(target(trend={"pending": None, "position": pos}))
    assert len([c for c in v.calls if c[0] == "STOP"]) == before, \
        "armed a naked stop on a flat venue"
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert any(e["kind"] == "ledger_divergence" for e in ex.state.events)


def test_gate_repeatedly_vanishing_stop_halts_instead_of_looping(tmp_path):
    """DEF-2: no cap meant 4,320 live orders and 4,320 pages per day against
    a persistent accept-then-cancel venue."""
    from app.mirror import STOP_REPLACE_MAX
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    for _ in range(STOP_REPLACE_MAX + 4):
        if led.stop_cloid and led.stop_cloid in v.orders:
            v.orders[led.stop_cloid]["status"] = "CANCELLED"
        ex.step(target(trend={"pending": None, "position": pos}))
    placed = len([c for c in v.calls if c[0] == "STOP"])
    assert placed <= STOP_REPLACE_MAX + 1, f"unbounded replacement: {placed}"
    assert ex.state.halted == "STOP_UNPLACEABLE"


def test_gate_stop_vanished_paging_is_rate_limited(tmp_path, monkeypatch):
    """The msg embedded a changing cloid, defeating kind+msg dedupe."""
    from app import alerts
    sent = []
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    for _ in range(3):
        if led.stop_cloid and led.stop_cloid in v.orders:
            v.orders[led.stop_cloid]["status"] = "CANCELLED"
        ex.step(target(trend={"pending": None, "position": pos}))
    assert len([m for m in sent if "stop_vanished" in m]) <= 1, sent


def test_gate_partially_filled_dead_stop_rearms_only_remainder(tmp_path):
    """DEF-3: Coinbase reports a partially-filled-then-expired stop as
    EXPIRED with filled_size > 0. Re-arming the full ledger size would
    over-hedge into a short if it triggered."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    full = led.qty
    v.orders[led.stop_cloid].update(status="CANCELLED", filled_qty=full / 2)
    orig = v.order_status
    v.order_status = lambda c: ({"status": "CANCELLED",
                                 "filled_qty": full / 2, "avg_price": 73000.0}
                                if c == led.stop_cloid else orig(c))
    ex.step(target(trend={"pending": None, "position": pos}))
    # ledger qty is rounded to 8dp, so compare within that, not below it
    assert abs(led.qty - full / 2) < 1e-7, f"re-armed {led.qty} of {full}"
    sized = [c for c in v.calls if c[0] == "STOP"][-1]
    # the venue rounds the order size, so assert within venue precision -
    # still four orders of magnitude below one 0.01-BTC contract
    assert abs(sized[2] - full / 2) < 1e-4, sized


def test_gate_state_survives_unknown_persisted_leg_keys(tmp_path):
    """DEF-4: a state file from a NEWER build carries fields this LegLedger
    lacks; the bare except discarded the ENTIRE state - un-halting a killed
    executor and zeroing the ledger under a live position."""
    import json
    from app.mirror import Executor
    cfg = Cfg(); cfg.state_path = str(tmp_path / "state.json")
    json.dump({"halted": "DAILY_LOSS",
               "legs": {"trend": {"qty": 0.03, "stop_px": 73000.0,
                                  "from_the_future": 7}},
               "coverage_live": {"drill_cycle": 3}},
              open(cfg.state_path, "w"))
    v = FakeVenue()
    v._add("MARKET", "BUY", 0.03, "seed")   # venue backs the ledger, so the
    ex = Executor(v, cfg)                   # boot reconcile leaves it alone
    assert ex.state.halted == "DAILY_LOSS", "a rollback un-halted the executor"
    assert ex.state.legs["trend"].qty == 0.03
    assert ex.state.coverage_live == {"drill_cycle": 3}


def test_gate_drills_stop_when_they_produce_no_fills(tmp_path, monkeypatch):
    """DEF-5/6: the terminal condition is a MEASUREMENT drilling can fail to
    advance (venue omits average_filled_price). Unbounded, it spends the
    daily budget forever, unattended."""
    from app.mirror import DRILL_NO_FILL_MAX
    # _auto_exec installs its OWN alerts.send patch, so take its list rather
    # than a local one it would overwrite
    ex, venue, sent = _auto_exec(tmp_path, monkeypatch)
    ex.state.coverage_live = {"drill_cycle": 3}      # only slippage remains
    monkeypatch.setattr(ex, "_record_fill", lambda *a, **k: None)
    for _ in range(DRILL_NO_FILL_MAX + 3):
        ex.step(target())
    assert ex._live_fill_count() == 0
    assert ex.state.auto_drill_off, "drilled forever with no slippage sample"
    assert len(ex.state.drills) <= DRILL_NO_FILL_MAX
    assert any("ACTION NEEDED" in m for m in sent)


def test_gate_pulse_never_leaks_position_or_api_errors(tmp_path, monkeypatch):
    """DEF-7: /pulse is unauthenticated and its own docstring promises no
    position sizes or order details. _drill_refusal returns
    venue_not_flat:{pos} and position_unreadable:{exc} (raw API URLs with key
    ids), and those were being published verbatim."""
    from fastapi.testclient import TestClient
    import app.main as m
    ex, v, pos = _armed_leg(tmp_path)
    ex._auto_drill_wait = ("position_unreadable:401 https://api.coinbase.com/"
                           "api/v3/brokerage/portfolios/9f3e-uuid organizations"
                           "/abc123/apiKeys/def456")
    monkeypatch.setattr(m, "EXEC", ex)
    monkeypatch.setattr(m.settings, "exec_token", "")
    body = TestClient(m.app).get("/pulse").text
    assert "http" not in body and "apiKeys" not in body, body
    ex._auto_drill_wait = "venue_not_flat:-0.37"
    body = TestClient(m.app).get("/pulse").json()
    assert body["auto_drill"] == "venue_not_flat"
    assert "0.37" not in str(body["auto_drill"])


def test_gate_status_exposes_auto_drill_waiting_on(tmp_path, monkeypatch):
    """DEF-8: a duplicate "auto_drill" key made the new block dead code."""
    import ast
    from fastapi.testclient import TestClient
    import app.main as m
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "app", "main.py")).read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"
    ex, v, pos = _armed_leg(tmp_path)
    ex._auto_drill_wait = "leg_not_flat:trend"
    monkeypatch.setattr(m, "EXEC", ex)
    monkeypatch.setattr(m.settings, "exec_token", "")
    ad = TestClient(m.app).get("/status").json()["auto_drill"]
    assert ad["waiting_on"] == "leg_not_flat:trend"


def test_gate_dry_run_fills_never_close_the_slippage_gate(tmp_path):
    """Mutation M6 had no test: dropping the live filter would let synthetic
    DryRunVenue prices satisfy the slippage row."""
    ex, v, pos = _armed_leg(tmp_path)
    ex.state.fills = [{"slip_bps": 1.0, "live": False}] * 20
    assert ex._live_fill_count() == 0
    ex.state.coverage_live = {"drill_cycle": 3}
    assert ex._needed_auto_drill() == "cycle"


# --- whole-chain review fixes (2026-08-24) ---------------------------------
def test_gate_mid_step_halt_stops_the_leg_loop(tmp_path):
    """CONFIRMED chain seam: _handle_stop_vanished halts INSIDE the leg loop.
    With pullback (first in LEGS) halting on ledger divergence, trend's
    _sync_leg then saw qty==0 on the flattened ledger and RE-ENTERED AT
    MARKET on the halted book in the same step. Every per-change test used
    the trend leg - the LAST in iteration order - so nothing after it could
    re-enter and the seam stayed invisible."""
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    # arm a pullback position + stop, then kill the stop AND flatten the venue
    ppos = {"side": "L", "entry_price": 60000.0, "entry_ts": 1787000000,
            "signal_ts": 1786990000, "stop": 58000.0, "exit_flag": None}
    ex.step(target(pull={"pending": None, "position": ppos}))
    led = ex.state.legs["pullback"]
    assert led.stop_cloid
    for o in v.orders.values():
        o["status"] = "CANCELLED"
    assert v.position() == 0.0
    # same step: engine also wants a trend position - must NOT be entered
    tpos = {"side": "L", "entry_price": 60000.0, "entry_ts": 1787000100,
            "signal_ts": 1786990100, "stop": 58000.0, "exit_flag": None}
    before = len(v.calls)
    ex.step(target(pull={"pending": None, "position": ppos},
                   trend={"pending": None, "position": tpos}))
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    new = [c for c in v.calls[before:] if c[0] in ("MARKET", "STOP")]
    assert not new, f"halted book traded in the same step: {new}"
    assert ex.state.legs["trend"].qty == 0.0


def test_gate_stop_replace_bound_survives_restarts(tmp_path):
    """The vanish counter was in-memory, so a crash-loop reset it each boot
    and STOP_REPLACE_MAX never tripped - the 4,320-order storm returned."""
    from app.mirror import Executor, STOP_REPLACE_MAX
    v = FakeVenue()
    ex = mkexec(tmp_path, v)
    pos = {"side": "L", "entry_price": 60000.0, "entry_ts": 1787000000,
           "signal_ts": 1786990000, "stop": 58000.0, "exit_flag": None}
    placed = 0
    for i in range(STOP_REPLACE_MAX + 4):
        led = ex.state.legs["trend"]
        if led.stop_cloid and led.stop_cloid in v.orders:
            v.orders[led.stop_cloid]["status"] = "CANCELLED"
        n0 = len([c for c in v.calls if c[0] == "STOP"])
        ex.step(target(trend={"pending": None, "position": pos}))
        placed += len([c for c in v.calls if c[0] == "STOP"]) - n0
        if ex.state.halted:
            break
        # simulate a restart every step - the old in-memory counter reset here
        ex._save_state()
        ex = Executor(v, ex.cfg)
    assert ex.state.halted == "STOP_UNPLACEABLE", \
        f"bound never tripped across restarts ({placed} stops placed)"
    assert placed <= STOP_REPLACE_MAX + 1, placed


def test_gate_partial_fill_on_dying_stop_is_not_clean_evidence(tmp_path):
    """F3: the stop_filled ramp row proves the CLEAN venue stop-fill path.
    A partial fill on a stop the venue killed is also evidence the venue
    misbehaved - it must not be the sole evidence behind a KELLY_M advance."""
    ex, v, pos = _armed_leg(tmp_path)
    led = ex.state.legs["trend"]
    full = led.qty
    orig = v.order_status
    v.order_status = lambda c: ({"status": "CANCELLED",
                                 "filled_qty": full / 2, "avg_price": 73000.0}
                                if c == led.stop_cloid else orig(c))
    ex.step(target(trend={"pending": None, "position": pos}))
    assert abs(led.qty - full / 2) < 1e-7
    assert ex.state.coverage_live.get("stop_filled") is None
    # a FULL consumption still credits
    v.order_status = lambda c: ({"status": "CANCELLED",
                                 "filled_qty": full / 2, "avg_price": 73000.0}
                                if c == led.stop_cloid else orig(c))
    ex.step(target(trend={"pending": None, "position": pos}))
    assert led.qty == 0.0


# ---------------------------------------------------------------------------
# Re-gate 2026-08-27. Four BLOCKING paths, all reproduced by the panel
# end-to-end; three were introduced by the fixes that preceded them. Every
# test below corresponds to a mutation that previously survived all 213.
def _legs(ex, pull, trend):
    ex.state.legs["pullback"].qty = pull
    ex.state.legs["trend"].qty = trend


def test_gate_B1_opposed_leg_gets_no_surplus_credit(tmp_path):
    """The surplus relaxation ('holding MORE is fine') is FALSE when a leg's
    sign opposes the net: the stop's side is _close_side(led.qty), so it
    moves the net AWAY from zero and OPENS size. The stop is sized on ONE
    leg while the check compared the SUM, so |leg| could exceed |sum| freely.
    Panel repro: venue +0.34, ledger {+0.34, -0.14 phantom}, sum +0.20 ->
    'ok' -> a BUY stop armed 0.14 BTC (~$10k) of unmanaged long."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.34, "seed")          # only pullback is real
    _legs(ex, +0.34, -0.14)                        # trend is phantom
    verdict, net, want = ex._stop_backing()
    assert verdict == "diverged", \
        f"opposed phantom leg rode in on the surplus: {verdict} net={net} want={want}"


def test_gate_B1_opposed_leg_blocks_the_placement(tmp_path):
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.34, "seed")
    _legs(ex, +0.34, -0.14)
    pos = {"side": "S", "entry_ts": NOW, "signal_ts": NOW - 14_400,
           "stop": 77_000.0, "exit_flag": None}
    ex._maintain_stop("trend", ex.state.legs["trend"], pos)
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert not [c for c, o in v.orders.items()
                if o["type"] == "STOP" and o["status"] == "OPEN"], \
        "armed a stop that OPENS size on trigger"


def test_gate_B1_flat_ledger_is_not_vacuously_ok(tmp_path):
    """want == 0 used to return 'ok' with NO check in either direction: the
    early return masked net > 0, and `(want > 0)` being False at zero masked
    net < 0. A flat ledger against a venue holding anything is a
    contradiction like any other."""
    for seed_side, qty in (("BUY", 0.02), ("SELL", 0.02)):
        v = FakeVenue(mult=0.01)
        ex = mkexec(tmp_path / seed_side, v)
        v._add("MARKET", seed_side, qty, "seed")
        _legs(ex, 0.0, 0.0)
        assert ex._stop_backing()[0] == "diverged", \
            f"flat ledger vs venue {seed_side} {qty} read as ok"


def test_gate_B1_same_sign_surplus_is_still_allowed(tmp_path):
    """The relaxation must survive where it is sound: no opposed leg, venue
    holds more than the ledger claims. Tightening this into a halt would
    fire on every rounding difference."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.05, "seed")
    _legs(ex, +0.02, +0.01)
    assert ex._stop_backing()[0] == "ok"


def test_gate_B2_close_leg_refuses_to_open_the_reverse_side(tmp_path):
    """_close_leg took side AND size straight off the ledger with no
    position read. Reads fully HEALTHY here: the position was closed outside
    our sight (an operator flatten, which halt_error's own page instructs),
    so the exit path sent MARKET SELL 0.34 into a flat venue and opened a
    naked, stopless SHORT of ~$25k with halted=None."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["pullback"]
    led.qty, led.stop_cloid, led.stop_px = 0.34, "P-1-S70000-1", 70_000.0
    v._add("STOP", "SELL", 0.34, "P-1-S70000-1", px=70_000.0)
    v.cancel("P-1-S70000-1")                       # venue killed it too
    ex._close_leg("pullback", led, "engine_flat")  # venue is FLAT
    assert v.position() == 0.0, \
        f"opened a reverse naked position out of a flat venue: {v.position()}"
    assert not [c for c, o in v.orders.items() if o["type"] == "MARKET"], \
        "sent a market close against a venue that holds nothing"


def test_gate_B2_close_leg_clamps_to_the_venue(tmp_path):
    """Corroboration says the ledger is backed in AGGREGATE; it does not
    bound THIS leg against the net. A close larger than the venue holds
    overshoots through flat and opens the reverse side.

    The fixture has to be a hedged book, or the aggregate check diverges and
    halts before the clamp is ever reached — an earlier version of this test
    did exactly that and passed by reading the HALT's own flatten order, so
    removing the clamp left it green (mutation survived 226 tests)."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.02, "seed")          # venue net +0.02
    _legs(ex, +0.05, -0.03)                        # ledger sum +0.02: agrees
    led = ex.state.legs["pullback"]
    assert ex._stop_backing()[0] == "ok", "fixture must reach the clamp"
    ex._close_leg("pullback", led, "engine_flat")
    assert ex.state.halted is None, "fixture halted instead of clamping"
    assert v.position() >= -1e-9, \
        f"close overshot through flat into a naked short: {v.position()}"
    mkt = [o for c, o in v.orders.items()
           if c != "seed" and o["type"] == "MARKET" and o["side"] == "SELL"]
    assert mkt and all(o["qty"] <= 0.02 + 1e-9 for o in mkt), \
        f"closed more than the venue held: {mkt}"


def test_gate_B2_close_leg_blind_venue_touches_nothing(tmp_path):
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = ex.state.legs["trend"]
    led.qty, led.stop_cloid = 0.01, "T-1-S74089-1"
    v._add("STOP", "SELL", 0.01, "T-1-S74089-1", px=74_089.0)
    ex._close_leg("trend", led, "engine_flat")
    assert v.orders["T-1-S74089-1"]["status"] == "OPEN", \
        "cancelled protection it could not replace"
    assert led.qty == 0.01 and led.stop_cloid == "T-1-S74089-1"
    assert any(e["kind"] == "close_backing_blind" for e in ex.state.events)


def test_gate_B2_dust_still_clears_without_halting(tmp_path):
    """Sub-contract dust is ledger noise, not a position: clearing it sends
    no order, so it must settle BEFORE the divergence check rather than
    halting the book over unholdable noise."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.legs["trend"].qty = -0.004
    ex._close_leg("trend", ex.state.legs["trend"], "engine_flat")
    assert ex.state.legs["trend"].qty == 0.0
    assert ex.state.halted is None, "halted on sub-contract dust"
    assert any(e["kind"] == "ledger_dust_cleared" for e in ex.state.events)


def test_gate_B3_unplaceable_halt_still_flattens(tmp_path):
    """The terminal verify ran BEFORE the flatten and raised, so a venue
    where cancel_all WORKS but order_status reads UNKNOWN - the 2026-08-26
    shape - had its orders stripped and was then never flattened: a live,
    unprotected position behind a halt that blocks re-placement."""
    class _CancelsButBlindStatus(FakeVenue):
        def order_status(self, cloid):
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}

    v = _CancelsButBlindStatus(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.34, "seed")
    led = ex.state.legs["pullback"]
    led.qty = 0.34
    pos = {"side": "L", "entry_price": 70_000.0, "entry_ts": NOW,
           "signal_ts": NOW - 14_400, "stop": 70_000.0, "exit_flag": None}
    for _ in range(8):
        if ex.state.halted:
            break
        ex._maintain_stop("pullback", led, pos)
    assert ex.state.halted == "STOP_UNPLACEABLE"
    assert abs(v.position()) <= 1e-9, \
        f"halt stripped the orders and left {v.position()} BTC live"
    assert any(e["kind"] == "halt_error" for e in ex.state.events), \
        "unverifiable cancels must still page halt_error"
    assert led.qty != 0.0, "ledger zeroed past unverified orders"


def test_gate_B4_adopt_partial_keeps_the_halt_and_the_stop(tmp_path):
    """Adopt used to cancel EVERY believed stop, keep an unattributable
    ledger, and un-halt - so the next poll's _close_leg market-closed a leg
    the venue did not hold and opened a naked position OUT OF A FLAT VENUE,
    by the operator obeying the page's own instruction."""
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "SELL", 0.02, "seed")         # real trend short
    v._add("STOP", "BUY", 0.02, "T-real-S1", px=80_000.0)
    _legs(ex, +0.01, -0.02)                        # pullback is phantom
    ex.state.legs["trend"].stop_cloid = "T-real-S1"
    ex.state.halted = "DRAWDOWN"
    ok = ex.resume(adopt_venue=True)
    assert ok is False, "adopt reported success on an unattributable ledger"
    assert ex.state.halted == "DRAWDOWN", "un-halted into a divergent ledger"
    assert v.orders["T-real-S1"]["status"] == "OPEN", \
        "cancelled the REAL leg's only protection"


def test_gate_N1_isolated_vanishes_decay_on_a_fixed_trigger(tmp_path):
    """The pullback engine stop is a fixed ATR level, never trailed, so the
    churn guard returns before any placement and the reset on a confirmed
    placement is UNREACHABLE. Four isolated, fully-recovered cancellations
    spread over hundreds of polls therefore accumulated into a false
    STOP_UNPLACEABLE that force-flattened a healthy book."""
    from app.mirror import STOP_OK_DECAY_POLLS
    v = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    v._add("MARKET", "BUY", 0.03, "seed")
    led = ex.state.legs["pullback"]
    led.qty = 0.03
    pos = {"side": "L", "entry_price": 70_000.0, "entry_ts": NOW,
           "signal_ts": NOW - 14_400, "stop": 68_000.0, "exit_flag": None}
    for cycle in range(4):
        ex._maintain_stop("pullback", led, pos)        # place / re-place
        assert led.stop_cloid, "leg left unprotected"
        v.cancel(led.stop_cloid)                       # venue kills it once
        ex._maintain_stop("pullback", led, pos)        # detect + re-place
        for _ in range(STOP_OK_DECAY_POLLS + 2):       # then it just rests
            ex._maintain_stop("pullback", led, pos)
        assert ex.state.halted is None, \
            f"false STOP_UNPLACEABLE after {cycle + 1} recovered vanishes"
    assert not (getattr(ex.state, "stop_vanish", {}) or {}), \
        "a stop resting confirmed for many polls must clear the count"


def test_gate_N3_resume_reports_the_adopt_outcome_not_the_request(tmp_path,
                                                                  monkeypatch):
    """`adopted` echoed the query parameter, so a REFUSED adopt on a blind
    venue returned a body byte-identical to a successful one - concealing
    that the stops the operator believes were cancelled are still armed."""
    from fastapi.testclient import TestClient
    import app.main as m
    v = _BlindVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    ex.state.legs["trend"].qty = 0.01
    ex.state.halted = "DRAWDOWN"
    monkeypatch.setattr(m, "EXEC", ex)
    monkeypatch.setattr(m.settings, "exec_token", "")
    body = TestClient(m.app).get("/resume?adopt_venue=1").json()
    assert body["adopted"] is False, f"claimed a refused adopt succeeded: {body}"
    assert body["adopt_requested"] is True
    assert body["halted"] == "DRAWDOWN"


def test_gate_N4_dryrun_adopt_does_not_latch_entries_off(tmp_path):
    """_adopt_venue_locked has no dry-run guard, and _check_drift returned
    on its dry-run guard BEFORE the clearing site - so an adopt in the
    mandatory shadow stage killed entries, chase and auto-drill for the
    process life, with the page's own remedy unable to clear it."""
    from app.cb import DryRunVenue
    inner = FakeVenue(mult=0.01)
    ex = mkexec(tmp_path, DryRunVenue(inner), dry_run=True)
    ex._boot_mismatch = True
    ex._check_drift(50_000.0)
    assert ex._boot_mismatch is False, \
        "dry-run adopt latched entries off with no in-band clear"
