"""Executor gates: the mirror state machine against a scripted fake venue.
No network, no Coinbase SDK — pure logic validation."""
import time

import pytest

from app.mirror import Executor, ExecState


class Cfg:
    kelly_m = 0.56
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
