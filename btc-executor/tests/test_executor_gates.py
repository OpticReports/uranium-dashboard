"""Executor gates: the mirror state machine against a scripted fake venue.
No network, no Coinbase SDK — pure logic validation."""
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
    def __init__(self, equity=10_000.0, mid=60_000.0):
        self._equity, self._mid = equity, mid
        self.orders = {}
        self.calls = []

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
                 o.get("part", 0.0)} if o else None)

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
        self._add("MARKET", side, qty, cloid)

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


def mkexec(tmp_path, venue):
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
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
    rollover. DRAWDOWN stays manual — auto-reset there would turn the
    floor into a retry loop."""
    v = FakeVenue(equity=30_000.0)
    ex = mkexec(tmp_path, v)
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
