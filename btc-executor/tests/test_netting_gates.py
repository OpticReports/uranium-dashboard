"""Netting gates: the mirror against a venue that holds ONE net position.

Hyperliquid nets both legs into a single BTC position. The executor's ledger
is per-leg. Every order the executor sends is per-leg. Both live halts
(2026-09-10 23:08:57 and 2026-09-14 00:03:35) descend from that one gap, and
each replay below is built from the venue's own records - userFills and
historicalOrders for 0xAb53..51e2 - not from the executor's event log, which
only says what it believed. The two are attributed order by order through
hl.derive_cloid (sha256 of our string ids is invertible by enumeration):

  2026-09-10  P-1788969600-S76641-4   pullback stop, SELL 0.02481 reduce-only
              filled 0.00843 (= the net; the venue clamped it), which left the
              venue FLAT and the trend leg (-0.01638) unbacked
              T-1789056000-S80906-9   trend stop, BUY 0.01638 reduce-only:
              accepted at placement although it OPPOSED the net long, then
              reduceOnlyCanceled by the venue at the same second the book
              went flat
              -> LEDGER_DIVERGENCE "trend: venue net 0.0 vs ledger sum -0.01638"

  2026-09-14  P-1789329600-E5         pullback maker entry BUY 0.04943 rested
              (crossed=false) and filled at 00:03:32 straight THROUGH the
              trend short: venue -0.0164 -> +0.03303. The engine books a
              pending only at its bar close (core.py "pending limit entry
              resolves against this bar"), so the fill sat in led.entry_cloid
              with led.qty still 0.
              T-1789056000-S79849-12  trend stop reduceOnlyCanceled at
              00:03:32 (the flip); _maintain_stop went to re-place it and
              _stop_backing compared want=-0.0164 (the unbooked fill is not
              in the sum) with net=+0.03303
              halt-1789344214          the halt's own flatten, SELL 0.03303
              reduce-only - the "Close Long" three seconds later was the
              halt, not a leg close

Two distinct defects, one venue property:
  (A) per-leg reduce-only stops and closes on an opposed book: the dominant
      leg's stop fills |net| and strands the other leg; the minority leg's
      stop cannot survive a flip and its close is refused forever;
  (B) a venue fill on a resting maker entry is invisible to every ledger-sum
      comparison until the engine's bar close, up to 4h later.

These gates pin the OUTCOME the fix must produce, in the venue's own terms:
never halt on either sequence, venue net == what the ledger believes the
venue holds after every poll, and a booked opposed book carries exactly one
resting reduce-only stop sized to the net. They are written against HLFake,
which models the venue's netting and reduce-only behaviour as observed - the
stock FakeVenue lets a stop fill its full size against a smaller net, which
is exactly the fiction that let both incidents pass every existing gate.
"""
import time

import pytest

from app import mirror
from test_executor_gates import (BLEND, Cfg, FakeVenue, _pos, target)

NOW = int(time.time()) // 14_400 * 14_400
MID = 76_808.0
LOT = 0.00001                       # HL BTC lot
# SIZING_BASE that reproduces the 09-14 pullback size at the 09-14 fill
# price: 0.20 * 1.5 * 0.75 * 16_874 / 76_808 = 0.04943 BTC. Trend sizes to
# 0.01647 (the live 0.0164 was taken at a different mid); the SHAPE - a
# pullback long three times the trend short - is what matters.
BASE = 16_874.0
Q_P, Q_T = 0.04943, 0.01647
NET = round(Q_P - Q_T, 5)           # +0.03296


class HLFake(FakeVenue):
    """FakeVenue plus Hyperliquid's netting and reduce-only semantics, each
    one taken from the account's own historicalOrders / userFills rows:

    - ONE net position; any fill moves it, an entry flips straight through
      (09-14 00:03:32: BUY 0.04943 against -0.0164 -> +0.03303, dir
      "Short > Long").
    - a reduce-only STOP is ACCEPTED at placement even when it opposes the
      net (09-10 20:00:48: BUY 0.01638 stop vs net +0.00843 -> status open).
      The venue validates reduce-only on FILL events, not on placement.
    - on trigger it fills at most |net| (09-10 23:08:57: SELL 0.02481 stop,
      fills 0.00623 + 0.0022 = 0.00843), and the ORDER record still reads
      origSz 0.02481 / sz 0.0 / filled - so order_status over-reports the
      fill; only the position read carries the clamp.
    - every fill sweeps resting reduce-only orders: any that can no longer
      reduce the new net is reduceOnlyCanceled (09-10 23:08:57 on flat;
      09-14 00:03:32 on flip).
    - a reduce-only IOC clamps to |net| and no-ops against flat/opposite
      (inherited from FakeVenue.place_market).
    """

    def __init__(self, equity=100_000.0, mid=MID, mult=LOT):
        super().__init__(equity=equity, mid=mid, mult=mult)
        self.min_notional_usd = 10.0

    def position(self):
        net = 0.0
        for o in self.orders.values():
            if o["status"] == "FILLED":
                net += (1 if o["side"] == "BUY" else -1) * o.get("done", o["qty"])
        return round(net, 8)

    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        self.orders[cloid]["ro"] = True

    def place_market(self, side, qty, cloid, reduce_only=False):
        super().place_market(side, qty, cloid, reduce_only=reduce_only)
        if reduce_only and cloid in self.orders:
            self.orders[cloid]["ro"] = True
        self._sweep()

    def _reduces(self, o, net):
        return abs(net) > 1e-9 and ((net > 0) == (o["side"] == "SELL"))

    def _sweep(self):
        net = self.position()
        for o in self.orders.values():
            if o["status"] == "OPEN" and o.get("ro") and o["type"] == "STOP" \
                    and not self._reduces(o, net):
                o["status"], o["raw"] = "CANCELLED", "reduceOnlyCanceled"

    def fill_limit(self, cloid):
        """A resting maker entry fills (crossed=false)."""
        o = self.orders[cloid]
        assert o["type"] == "LIMIT" and o["status"] == "OPEN", o
        o["status"] = "FILLED"
        self.calls.append(("LIMIT_FILL", o["side"], round(o["qty"], 5), cloid))
        self._sweep()

    def fire_stop(self, cloid):
        """Price reaches the trigger. Returns the qty the venue actually
        traded, which is NOT what order_status will say."""
        o = self.orders[cloid]
        assert o["type"] == "STOP" and o["status"] == "OPEN", o
        net = self.position()
        if not self._reduces(o, net):
            o["status"], o["raw"] = "CANCELLED", "reduceOnlyCanceled"
            return 0.0
        done = round(min(o["qty"], abs(net)), 8)
        o["status"], o["done"] = "FILLED", done
        self.calls.append(("STOP_FILL", o["side"], round(done, 5), cloid))
        self._sweep()
        return done

    # ---- what a human would read off the venue UI ----
    def resting_stops(self):
        return [o for o in self.orders.values()
                if o["type"] == "STOP" and o["status"] == "OPEN"]

    def opened_beyond(self, cloids_before):
        """Non-reduce-only orders sent since `cloids_before`."""
        return [(c, o) for c, o in self.orders.items()
                if c not in cloids_before and o["type"] in ("MARKET", "LIMIT")
                and not o.get("ro")]


def mk(tmp_path, v, **over):
    cfg = Cfg()
    cfg.state_path = str(tmp_path / "state.json")
    cfg.dry_run = False
    cfg.sizing_base_usd = BASE
    for k, val in over.items():
        setattr(cfg, k, val)
    return mirror.Executor(v, cfg, cfg.state_path)


def belief(ex, v):
    """What the ledger believes the VENUE holds: booked legs plus any fill
    resting on an entry order the engine has not booked yet (defect B)."""
    w = 0.0
    for led in ex.state.legs.values():
        w += led.qty
        if led.qty == 0.0 and led.entry_cloid:
            st = v.order_status(led.entry_cloid) or {}
            f = float(st.get("filled_qty") or 0.0)
            w += f if led.entry_side == "L" else -f
    return round(w, 8)


def assert_mirrored(ex, v, where):
    assert ex.state.halted is None, f"{where}: halted {ex.state.halted}"
    kinds = [e["kind"] for e in ex.state.events]
    assert "ledger_divergence" not in kinds, f"{where}: {kinds}"
    assert abs(v.position() - belief(ex, v)) < 1e-9, \
        f"{where}: venue {v.position()} vs belief {belief(ex, v)}"


def stop_covers_net(v, where):
    """A BOOKED opposed book must carry exactly one resting reduce-only stop
    on the side that reduces the net, sized to the net - never more (it
    would strand the other leg when it fills) and never a second one on
    the other side (the venue would cancel it on the next fill anyway)."""
    net = v.position()
    stops = v.resting_stops()
    assert len(stops) == 1, f"{where}: {len(stops)} resting stops: {stops}"
    s = stops[0]
    assert s["side"] == ("SELL" if net > 0 else "BUY"), f"{where}: {s}"
    assert abs(s["qty"] - abs(net)) < 1e-9, \
        f"{where}: stop {s['qty']} vs net {net}"


# --------------------------------------------------------------------------
# fixtures that walk the executor INTO the two live shapes through its own
# entry paths, so the ledger refs are the ones the real code leaves behind
# --------------------------------------------------------------------------

T_ENTRY = NOW - 4 * 14_400            # trend position entry bar
S_PULL = NOW - 14_400                 # pullback signal bar


def trend_short(ex, v, stop=79_850.0):
    """Trend leg enters short at market and gets its stop."""
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    ex.step(target(trend=_pos(entry_ts=T_ENTRY, side="S", stop=stop)))
    led = ex.state.legs["trend"]
    assert abs(led.qty + Q_T) < 1e-9, led.qty
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert abs(v.position() + Q_T) < 1e-9
    return led


def pullback_limit(ex, v, trend_tl, limit=MID):
    """Pullback leg places its post-only entry while the trend short is on;
    returns the resting order's cloid."""
    ex.step(target(pull={"pending": {"side": "L", "limit": limit,
                                     "signal_ts": S_PULL},
                         "position": None},
                   trend=trend_tl))
    led = ex.state.legs["pullback"]
    assert led.entry_cloid and led.qty == 0.0
    assert v.orders[led.entry_cloid]["status"] == "OPEN"
    assert abs(v.orders[led.entry_cloid]["qty"] - Q_P) < 1e-9
    return led.entry_cloid


def pullback_long_booked(ex, v, stop=76_642.0):
    """Pullback leg: limit placed, filled at the venue, booked by the engine
    at its bar close (branch 1 -> _enter_from_fill, nothing to chase)."""
    cloid = pullback_limit(ex, v, {"pending": None, "position": None})
    v.fill_limit(cloid)
    ex.step(target(pull=_pos(entry_ts=S_PULL + 14_400, side="L", stop=stop)))
    led = ex.state.legs["pullback"]
    assert abs(led.qty - Q_P) < 1e-9, led.qty
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    return led


# --------------------------------------------------------------------------
# GATE 1 - 2026-09-10 23:08:57. The dominant leg's stop fires on the net.
# --------------------------------------------------------------------------

def test_gate_netting_dominant_stop_fill_does_not_strand_the_other_leg(tmp_path):
    """Pullback long 0.04943 (stop below) and trend short 0.01647 (stop
    above) on one netted venue: net +0.03296. Price hits the pullback stop.
    The venue trades 0.03296 - the net - and cancels the trend's reduce-only
    stop because a flat book has nothing for it to reduce. The engine has
    stopped the pullback and still holds the short.

    Live outcome: LEDGER_DIVERGENCE halt, trend short lost. Required: the
    book keeps mirroring the engine - the trend short is re-established on
    the venue and protected - with no halt and no page that says
    divergence."""
    v = HLFake()
    ex = mk(tmp_path, v)
    pull = pullback_long_booked(ex, v, stop=76_642.0)
    # trend enters short against the open long
    ex.step(target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                             stop=76_642.0),
                   trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    both = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                            stop=76_642.0),
                  trend=_pos(entry_ts=T_ENTRY, side="S", stop=80_907.0))
    ex.step(both)
    trend = ex.state.legs["trend"]
    assert abs(trend.qty + Q_T) < 1e-9
    assert abs(v.position() - NET) < 1e-9
    assert_mirrored(ex, v, "opposed book built")
    stop_covers_net(v, "opposed book built")
    pull_stop = pull.stop_cloid
    assert pull_stop and v.orders[pull_stop]["status"] == "OPEN"

    # price falls through the pullback stop
    done = v.fire_stop(pull_stop)
    assert abs(done - NET) < 1e-9, "fake must clamp the stop fill to the net"
    assert abs(v.position()) < 1e-9, "venue is flat"
    # the engine stops the pullback at its next poll (intrabar) and still
    # holds the trend short
    after = target(trend=_pos(entry_ts=T_ENTRY, side="S", stop=80_907.0))
    ex.step(after)
    assert_mirrored(ex, v, "poll after the stop fill")
    assert ex.state.legs["pullback"].qty == 0.0
    assert abs(ex.state.legs["trend"].qty + Q_T) < 1e-9, \
        "trend leg dropped from the ledger"
    assert abs(v.position() + Q_T) < 1e-9, \
        f"trend short not re-established on the venue: {v.position()}"
    ex.step(after)                                   # settle
    assert_mirrored(ex, v, "second poll")
    stops = v.resting_stops()
    assert len(stops) == 1 and stops[0]["side"] == "BUY" \
        and abs(stops[0]["qty"] - Q_T) < 1e-9, stops
    assert ex.state.coverage_live.get("stop_filled", 0) == 1


# --------------------------------------------------------------------------
# GATE 2 - 2026-09-14 00:03:32. A maker entry flips through the other leg
# and rests unbooked until the engine's bar close.
# --------------------------------------------------------------------------

def test_gate_netting_maker_fill_through_the_other_leg_does_not_halt(tmp_path):
    """Trend short 0.01647 on. Pullback's post-only BUY 0.04943 rests, then
    fills at the venue: net -0.01647 -> +0.03296, and the venue cancels the
    trend's reduce-only BUY stop on the flip. The engine still shows the
    pullback as PENDING - it books a limit fill only at its bar close.

    Live outcome: _maintain_stop tried to re-place the trend stop, compared
    the ledger SUM (-0.0164, the unbooked fill absent) with the venue
    (+0.03303), halted, and the halt's flatten sold the lot. Required: no
    halt - the ledger's belief of what the venue holds must include a fill
    the venue has confirmed on our own resting entry, and while the trend
    leg opposes the net it gets no reduce-only stop (the venue would cancel
    it on the next fill anyway)."""
    v = HLFake()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    ecloid = pullback_limit(ex, v, trend_tl)
    before = set(v.orders)

    v.fill_limit(ecloid)
    assert abs(v.position() - NET) < 1e-9, "fake must flip through the short"
    tstop = ex.state.legs["trend"].stop_cloid
    assert v.orders[tstop]["status"] == "CANCELLED", "fake must reduceOnlyCancel"

    # same target as before: pullback PENDING, trend in position
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    for i in range(3):
        ex.step(pend)
        assert_mirrored(ex, v, f"poll {i} in the unbooked window")
    assert not v.opened_beyond(before), \
        f"sent an opening order inside the window: {v.opened_beyond(before)}"
    assert abs(v.position() - NET) < 1e-9
    assert abs(ex.state.legs["trend"].qty + Q_T) < 1e-9
    # no reduce-only BUY stop may be re-armed against a net long: the venue
    # would cancel it on the next fill, and until then it advertises
    # protection the venue will never honour
    assert not [s for s in v.resting_stops() if s["side"] == "BUY"], \
        v.resting_stops()

    # the engine books the pullback at its bar close
    booked = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                              stop=75_300.0),
                    trend=trend_tl)
    ex.step(booked)
    assert_mirrored(ex, v, "engine books the pullback")
    pull = ex.state.legs["pullback"]
    assert abs(pull.qty - Q_P) < 1e-9, pull.qty
    assert "entry_chase" not in [e["kind"] for e in ex.state.events], \
        "chased a fill that was already on the venue"
    ex.step(booked)
    stop_covers_net(v, "booked opposed book")
    assert abs(v.resting_stops()[0]["px"] - 75_300.0) < 1e-9, \
        "the net's stop must sit at the dominant leg's level"


# --------------------------------------------------------------------------
# GATE 3 - the third shape, not yet seen live: the DOMINANT leg exits by
# signal while the minority leg is still on. Its close has to cross flat.
# --------------------------------------------------------------------------

def test_gate_netting_dominant_signal_exit_re_establishes_the_minority_leg(tmp_path):
    """Booked opposed book, net +0.03296. The engine exits the pullback
    (position gone at bar close). Today _close_leg clamps the close to the
    net, zeroes the whole pullback leg, and the next _stop_backing sees a
    flat venue against a ledger short - the 09-10 halt through the exit
    door. Required: the venue ends up holding the trend short, protected."""
    v = HLFake()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v)
    ecloid = pullback_limit(ex, v, trend_tl)
    v.fill_limit(ecloid)
    booked = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                              stop=75_300.0),
                    trend=trend_tl)
    ex.step(booked)
    ex.step(booked)
    assert_mirrored(ex, v, "booked")
    stop_covers_net(v, "booked")

    exited = target(trend=trend_tl)                  # pullback gone
    ex.step(exited)
    assert_mirrored(ex, v, "after the pullback exit")
    assert ex.state.legs["pullback"].qty == 0.0
    assert abs(v.position() + Q_T) < 1e-9, \
        f"venue should hold the trend short, holds {v.position()}"
    ex.step(exited)
    assert_mirrored(ex, v, "settled")
    stops = v.resting_stops()
    assert len(stops) == 1 and stops[0]["side"] == "BUY" \
        and abs(stops[0]["qty"] - Q_T) < 1e-9, stops
    assert ex.state.coverage_live.get("signal_exit", 0) == 1


def test_gate_netting_minority_signal_exit_unwinds_the_hedge(tmp_path):
    """Mirror image: the engine exits the TREND short while the pullback
    long is still on. In net terms that close is an OPENING buy - the hedge
    comes off and the venue must go from +0.03296 to +0.04943. Today it is
    close_refused_unbacked on every poll, forever."""
    v = HLFake()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v)
    ecloid = pullback_limit(ex, v, trend_tl)
    v.fill_limit(ecloid)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=75_300.0)
    ex.step(target(pull=pull_tl, trend=trend_tl))
    ex.step(target(pull=pull_tl, trend=trend_tl))
    stop_covers_net(v, "booked")

    ex.step(target(pull=pull_tl))                    # trend gone
    assert_mirrored(ex, v, "after the trend exit")
    assert ex.state.legs["trend"].qty == 0.0
    assert abs(v.position() - Q_P) < 1e-9, v.position()
    ex.step(target(pull=pull_tl))
    stop_covers_net(v, "pullback alone")
    assert "close_refused_unbacked" not in [e["kind"] for e in ex.state.events]


# --------------------------------------------------------------------------
# GATE 4 - the phantom guard survives. An order that OPENS size is sent only
# when the venue agrees with the ledger exactly; anything else still halts.
# --------------------------------------------------------------------------

def test_gate_netting_opening_orders_need_exact_corroboration(tmp_path):
    """The whole 2026-08-26 chain is 'never send an opening order off ledger
    belief'. Crossing flat to keep the minority leg mirrored IS an opening
    order, so it must be gated on the venue agreeing with the ledger to the
    lot, read immediately before the send. Here an operator has flattened
    the book by hand between polls: the ledger still shows both legs, the
    venue shows nothing. No opening order may go out; the book halts."""
    v = HLFake()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v)
    ecloid = pullback_limit(ex, v, trend_tl)
    v.fill_limit(ecloid)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=75_300.0)
    ex.step(target(pull=pull_tl, trend=trend_tl))
    ex.step(target(pull=pull_tl, trend=trend_tl))
    stop_covers_net(v, "booked")

    # operator flattens by hand on the venue UI
    v._add("MARKET", "SELL", NET, "operator-flatten")
    assert abs(v.position()) < 1e-9
    before = set(v.orders)

    ex.step(target(trend=trend_tl))                  # pullback exit arrives
    assert not v.opened_beyond(before), \
        f"opened size against a venue that does not back the ledger: " \
        f"{v.opened_beyond(before)}"
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert abs(v.position()) < 1e-9


def test_gate_netting_same_side_book_is_untouched(tmp_path):
    """Fence: two legs on the SAME side are not netted against each other,
    and today's per-leg stops - which sum to the net and each reduce it -
    must keep working exactly as before. The fix is for the opposed book
    only."""
    v = HLFake()
    ex = mk(tmp_path, v)
    pullback_long_booked(ex, v, stop=76_642.0)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=76_642.0)
    ex.step(target(pull=pull_tl,
                   trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    both = target(pull=pull_tl, trend=_pos(entry_ts=T_ENTRY, side="L",
                                           stop=74_000.0))
    ex.step(both)
    ex.step(both)
    assert_mirrored(ex, v, "same-side book")
    stops = v.resting_stops()
    assert len(stops) == 2 and all(s["side"] == "SELL" for s in stops)
    assert abs(sum(s["qty"] for s in stops) - v.position()) < 1e-9
    assert abs(v.position() - (Q_P + Q_T)) < 1e-9


# ==========================================================================
# B. Exact-number reproductions - the ledger seeded with the live sizes and
#    the venue holding what it held (docs/NETTING_FIX_DESIGN.md §4.6.B)
# ==========================================================================

INC1_P, INC1_T, INC1_NET = 0.02481, 0.01638, 0.00843
INC1_P_TS, INC1_T_TS = 1788969600, 1789056000       # engine entry bars
INC2_T, INC2_P, INC2_NET = 0.0164, 0.04943, 0.03303
INC2_SIG, INC2_P_TS = 1789329600, 1789344000


class HLFake2(HLFake):
    """HLFake plus the knobs the folded-fix gates need: partial prints on a
    resting maker order, a partial IOC, a position read that lags its own
    fill, reads that come back UNKNOWN, an IOC the venue leaves unfilled,
    and an order the venue rejects."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.unknown_reads: dict = {}       # cloid prefix -> reads left
        self.unfilled_prefix: str | None = None
        self.reject_prefix: str | None = None
        self.partial_market_qty: float | None = None
        self.lag_reads = 0                  # position() reads that lag
        self._pos_history = [0.0]
        self.on_reject = None

    def position(self):
        now = super().position()
        if self.lag_reads > 0 and self._pos_history:
            self.lag_reads -= 1
            return self._pos_history[-1]
        self._pos_history.append(now)
        return now

    def _add(self, kind, side, qty, cloid, px=None):
        if kind == "MARKET" and self.partial_market_qty is not None:
            qty, self.partial_market_qty = self.partial_market_qty, None
        super()._add(kind, side, qty, cloid, px)
        self._pos_history.append(super().position())

    def order_status(self, cloid):
        for pref, n in list(self.unknown_reads.items()):
            if cloid.startswith(pref) and n > 0:
                self.unknown_reads[pref] = n - 1
                return {"status": "UNKNOWN", "filled_qty": 0.0,
                        "avg_price": None}
        return super().order_status(cloid)

    def place_market(self, side, qty, cloid, reduce_only=False):
        if self.reject_prefix and cloid.startswith(self.reject_prefix):
            if self.on_reject:
                self.on_reject()
            raise RuntimeError("order rejected: simulated")
        if self.unfilled_prefix and cloid.startswith(self.unfilled_prefix):
            self.orders[cloid] = {"type": "MARKET", "side": side, "qty": qty,
                                  "px": None, "status": "CANCELLED",
                                  "part": 0.0}
            self.calls.append(("MARKET_UNFILLED", side, round(qty, 5), cloid))
            return
        super().place_market(side, qty, cloid, reduce_only=reduce_only)

    def partial_fill(self, cloid, qty):
        """A resting maker order prints `qty` and keeps resting."""
        o = self.orders[cloid]
        assert o["type"] == "LIMIT" and o["status"] == "OPEN"
        o["part"] = round(o.get("part", 0.0) + qty, 8)
        n = sum(1 for c in self.orders if c.startswith(cloid + "-part"))
        self.orders[f"{cloid}-part{n + 1}"] = {
            "type": "MARKET", "side": o["side"], "qty": qty, "px": o["px"],
            "status": "FILLED"}
        self._pos_history.append(super().position())
        self._sweep()


def _open_stops(v):
    return [o for o in v.orders.values()
            if o["type"] == "STOP" and o["status"] == "OPEN"]


def _mkts(v, since=0):
    return [c for c in v.calls[since:] if c[0] == "MARKET"]


def test_gate_cloid_pin_observed_ids_and_the_R_letter():
    """The attribution in this file's docstring is only as good as the
    derivation: pin the four observed venue ids to their executor strings,
    and pin that the new R letter cannot collide with any other path's."""
    from app.hl import derive_cloid
    assert derive_cloid("P-1789329600-E5").startswith("0x9801d99dec")
    assert derive_cloid("halt-1789344214").startswith("0x1459893a92")
    assert derive_cloid("P-1788969600-S76641-4").startswith("0x0109a2c125")
    assert derive_cloid("T-1789056000-S80906-9").startswith("0x65502ceef5")
    assert derive_cloid("T-1789056000-S79849-12").startswith("0x879afcb767")
    r = derive_cloid("T-1789056000-R1")
    for other in ("T-1789056000-E1", "T-1789056000-C1",
                  "T-1789056000-S80906-1", "T-1789056000-X",
                  "T-1789056000-E1-UNWIND"):
        assert r[:14] != derive_cloid(other)[:14]


def _seed_inc1(tmp_path):
    v = HLFake2(mid=76_600.0)
    ex = mk(tmp_path, v)
    v._add("MARKET", "BUY", INC1_P, "P-1788969600-E4")
    v._add("MARKET", "SELL", INC1_T, "T-1789056000-E1")
    assert abs(v.position() - INC1_NET) < 1e-9
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    p.qty, p.signal_ts, p.entry_n = INC1_P, INC1_P_TS - 14_400, 4
    p.stop_cloid, p.stop_px = "P-1788969600-S76641-3", 76_641.73
    p.stop_qty, p.stop_mode, p.stop_n = INC1_P, "venue", 3
    v.place_stop("SELL", INC1_P, 76_641.73, "P-1788969600-S76641-3")
    t.qty, t.signal_ts, t.entry_n = -INC1_T, INC1_T_TS - 14_400, 1
    t.entry_cloid, t.entry_side, t.entry_qty = "T-1789056000-E1", "S", INC1_T
    s3 = _pos(entry_ts=INC1_P_TS, side="L", stop=76_641.73)
    s4 = _pos(entry_ts=INC1_T_TS, side="S", stop=80_906.0)
    return ex, v, s3, s4


@pytest.mark.parametrize("engine_still_reports_s3", [True, False])
def test_gate_inc1_exact_replay(tmp_path, engine_still_reports_s3):
    """2026-09-10 23:08:57 with the live numbers. The first poll must
    re-size the pullback's stop from 0.02481 to the net 0.00843 - and mint
    exactly the id the venue recorded, `P-1788969600-S76641-4` - and must
    NOT place the trend's `T-1789056000-S80906-9`. When the stop fires the
    venue trades 0.00843 and goes flat; the next poll re-establishes the
    trend short through `T-1789056000-R1` (entry-class), whichever way the
    engine reports S3 at that moment."""
    ex, v, s3, s4 = _seed_inc1(tmp_path)
    ex.step(target(pull=s3, trend=s4))
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    stops = _open_stops(v)
    assert len(stops) == 1 and stops[0]["side"] == "SELL" \
        and abs(stops[0]["qty"] - INC1_NET) < 1e-9, stops
    assert p.stop_cloid == "P-1788969600-S76641-4"
    assert abs(p.stop_qty - INC1_NET) < 1e-9 and p.stop_mode == "venue"
    assert t.stop_cloid is None and t.stop_mode == "engine"
    assert "T-1789056000-S80906-9" not in v.orders
    assert "stop_vanished" not in [e["kind"] for e in ex.state.events]

    done = v.fire_stop(p.stop_cloid)
    assert abs(done - INC1_NET) < 1e-9 and abs(v.position()) < 1e-9

    n0 = len(v.calls)
    ex.step(target(pull=s3 if engine_still_reports_s3 else None, trend=s4))
    assert ex.state.halted is None
    kinds = [e["kind"] for e in ex.state.events]
    assert "ledger_divergence" not in kinds
    assert "leg_netted_out" in kinds and "leg_reestablished" in kinds
    assert p.qty == 0.0
    if engine_still_reports_s3:
        assert p.stopped_entry_ts == INC1_P_TS
    r = [c for c in v.calls[n0:] if c[0] == "MARKET" and c[3].endswith("-R1")]
    assert r == [("MARKET", "SELL", INC1_T, "T-1789056000-R1")], r
    assert "T-1789056000-R1" not in getattr(v, "reduce_only_cloids", [])
    assert abs(v.position() + INC1_T) < 1e-9
    assert abs(t.qty + INC1_T) < 1e-9 and t.netted_qty == 0.0
    stops = _open_stops(v)
    assert len(stops) == 1 and stops[0]["side"] == "BUY" \
        and abs(stops[0]["qty"] - INC1_T) < 1e-9 \
        and abs(stops[0]["px"] - 80_906.0) < 1e-9, stops
    assert ex.state.coverage_live.get("stop_filled", 0) == 1
    assert ex.state.coverage_live.get("netted_reopen", 0) == 1


def _seed_inc2(tmp_path):
    v = HLFake2(mid=MID)
    ex = mk(tmp_path, v)
    v._add("MARKET", "SELL", INC2_T, "T-1789056000-C3")
    t = ex.state.legs["trend"]
    t.qty, t.signal_ts, t.chase_n = -INC2_T, INC1_T_TS - 14_400, 3
    t.stop_cloid, t.stop_px = "T-1789056000-S79910-11", 79_910.0
    t.stop_qty, t.stop_mode, t.stop_n = INC2_T, "venue", 11
    v.place_stop("BUY", INC2_T, 79_910.0, "T-1789056000-S79910-11")
    s4 = _pos(entry_ts=INC1_T_TS, side="S", stop=79_910.0)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": INC2_SIG},
                        "position": None}, trend=s4)
    return ex, v, s4, pend


def test_gate_inc2_exact_replay(tmp_path):
    """2026-09-14 00:00-00:03 with the live numbers, then the 04:00 booking
    and the trend's later exit. The maker fill flips the venue to +0.03303
    and the venue cancels the trend's stop; the poll after must halt
    nothing, send nothing (no `halt-…` flatten, no 0.03303 SELL), book the
    fill early, and subordinate the trend silently. At 04:00 the pullback
    is booked without a chase and ONE stop rests, sized to the net at the
    pullback's level. When the trend exits, the pullback is made whole
    through `P-1789344000-R1` and its stop re-sizes."""
    ex, v, s4, pend = _seed_inc2(tmp_path)
    ex.step(pend)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert p.entry_cloid == "P-1789329600-E1" and p.qty == 0.0
    assert v.orders[p.entry_cloid]["status"] == "OPEN"
    assert abs(v.orders[p.entry_cloid]["qty"] - INC2_P) < 1e-9

    v.fill_limit(p.entry_cloid)
    assert abs(v.position() - INC2_NET) < 1e-9
    assert v.orders[t.stop_cloid]["status"] == "CANCELLED"
    assert v.orders[t.stop_cloid].get("raw") == "reduceOnlyCanceled"

    n0 = len(v.calls)
    ex.step(pend)
    assert ex.state.halted is None
    assert not _mkts(v, n0), f"sent a market order in the window: {_mkts(v, n0)}"
    assert not [c for c in v.orders if c.startswith("halt-")]
    assert abs(p.qty - INC2_P) < 1e-9 and p.entry_cloid == "P-1789329600-E1"
    assert t.stop_cloid is None and t.stop_mode == "engine"
    kinds = [e["kind"] for e in ex.state.events]
    assert "stop_subordinated" in kinds and "entry_filled_early" in kinds
    assert "stop_vanished" not in kinds and "ledger_divergence" not in kinds
    assert not (getattr(ex.state, "stop_vanish", None) or {})
    assert abs(v.position() - sum(l.qty for l in ex.state.legs.values())) < 1e-9
    assert kinds.count("unbooked_fill_unprotected") == 1
    for _ in range(3):                                # the rest of the window
        ex.step(pend)
    assert ex.state.halted is None and not _mkts(v, n0)

    booked = target(pull=_pos(entry_ts=INC2_P_TS, side="L", stop=75_900.0),
                    trend=s4)
    ex.step(booked)
    assert p.entry_cloid is None and abs(p.qty - INC2_P) < 1e-9
    assert "entry_chase" not in [e["kind"] for e in ex.state.events]
    stops = _open_stops(v)
    assert len(stops) == 1 and stops[0]["side"] == "SELL" \
        and abs(stops[0]["qty"] - INC2_NET) < 1e-9 \
        and abs(stops[0]["px"] - 75_900.0) < 1e-9, stops
    assert abs(v.position() - INC2_NET) < 1e-9

    # the trend's trail is hit: the engine drops S4
    n1 = len(v.calls)
    alone = target(pull=_pos(entry_ts=INC2_P_TS, side="L", stop=75_900.0))
    ex.step(alone)
    assert ex.state.halted is None
    ro = [c for c in v.calls[n1:] if c[0] == "MARKET"
          and c[3] in getattr(v, "reduce_only_cloids", [])]
    assert not ro, f"reduce-only order sent for a subordinate exit: {ro}"
    r = [c for c in v.calls[n1:] if c[0] == "MARKET" and c[3].endswith("-R1")]
    assert r == [("MARKET", "BUY", INC2_T, "P-1789344000-R1")], r
    assert abs(v.position() - INC2_P) < 1e-9 and abs(p.qty - INC2_P) < 1e-9
    assert t.qty == 0.0 and p.netted_qty == 0.0
    ex.step(alone)
    stops = _open_stops(v)
    assert len(stops) == 1 and abs(stops[0]["qty"] - INC2_P) < 1e-9, stops
    assert ex.state.coverage_live.get("signal_exit", 0) == 1


def test_gate_inc2_engine_declines_the_pullback_after_the_window(tmp_path):
    """Same window, but at 04:00 the engine reports the pullback FLAT: the
    early-booked fill is an orphan. No `-UNWIND`; a reduce-only close of
    the NET, which nets the trend away, and the trend is re-established
    through its R order so the venue ends holding S4 alone."""
    ex, v, s4, pend = _seed_inc2(tmp_path)
    ex.step(pend)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    v.fill_limit(p.entry_cloid)
    ex.step(pend)
    n0 = len(v.calls)
    ex.step(target(trend=s4))
    assert ex.state.halted is None
    assert not [c for c in v.orders if c.endswith("-UNWIND")]
    mk_calls = _mkts(v, n0)
    assert len(mk_calls) == 2, mk_calls
    x, r = mk_calls
    assert x[1] == "SELL" and abs(x[2] - INC2_NET) < 1e-9 and x[3].endswith("-X")
    assert x[3] in v.reduce_only_cloids
    assert r == ("MARKET", "SELL", INC2_T, "T-1789056000-R1")
    assert r[3] not in v.reduce_only_cloids
    assert abs(v.position() + INC2_T) < 1e-9
    assert p.qty == 0.0 and abs(t.qty + INC2_T) < 1e-9 and t.netted_qty == 0.0
    stops = _open_stops(v)
    assert len(stops) == 1 and stops[0]["side"] == "BUY" \
        and abs(stops[0]["qty"] - INC2_T) < 1e-9, stops


# ==========================================================================
# C. Gates for the folded critique fixes N1-N10
# ==========================================================================

def test_gate_N1_consumption_never_forgets_a_resting_maker_order(tmp_path):
    """BLOCKING (both lenses). A pullback maker order printed 0.01 of
    0.04943 and keeps resting; the trend's stop (now the dominant, net
    -0.00647) fires and the venue goes flat, consuming the 0.01. The
    consumed leg's entry ref must not be cleared while the order may still
    be live: the remainder is CANCELLED, the ref is kept until the venue
    confirms it terminal, no second entry is ever sent, and the 0.01 is
    re-established through the R order (stamped with the signal_ts, N9c)."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    pcloid = pullback_limit(ex, v, trend_tl)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    v.partial_fill(pcloid, 0.01)
    assert abs(v.position() + (Q_T - 0.01)) < 1e-9
    ex.step(pend)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert abs(p.qty - 0.01) < 1e-9 and p.entry_cloid == pcloid
    stops = _open_stops(v)
    assert len(stops) == 1 and abs(stops[0]["qty"] - (Q_T - 0.01)) < 1e-9

    v.fire_stop(t.stop_cloid)
    assert abs(v.position()) < 1e-9
    entries_before = [c for c in v.calls if c[0] == "LIMIT"]
    for i in range(10):
        ex.step(pend)
        assert_mirrored(ex, v, f"poll {i}")
        assert [c for c in v.calls if c[0] == "LIMIT"] == entries_before, \
            "a second full-size entry was sent beside the remainder"
    assert v.orders[pcloid]["status"] == "CANCELLED", "remainder left resting"
    assert p.entry_cloid is None, "ref not released after a confirmed terminal"
    assert abs(p.qty - 0.01) < 1e-9 and p.netted_qty == 0.0
    assert abs(v.position() - 0.01) < 1e-9
    r = [c for c in v.calls if c[0] == "MARKET" and c[3].endswith("-R1")]
    assert r == [("MARKET", "BUY", 0.01, f"P-{S_PULL}-R1")], r
    assert t.qty == 0.0 and t.stopped_entry_ts == T_ENTRY


def test_gate_N2_R_order_is_belief_before_confirm(tmp_path):
    """BLOCKING (both lenses). The R order's refs are persisted BEFORE the
    send; an UNKNOWN confirm books nothing, drops nothing and re-sends
    nothing (no chase either); the next confirmed read books it."""
    ex, v, s3, s4 = _seed_inc1(tmp_path)
    ex.step(target(pull=s3, trend=s4))
    v.fire_stop(ex.state.legs["pullback"].stop_cloid)
    v.unknown_reads["T-1789056000-R"] = 3
    saved = []
    real_save = ex._save_state

    def spy():
        real_save()
        t = ex.state.legs["trend"]
        saved.append((t.reest_cloid, len([c for c in v.calls
                                          if c[3] == "T-1789056000-R1"])))
    ex._save_state = spy
    ex.step(target(pull=s3, trend=s4))
    t = ex.state.legs["trend"]
    assert t.reest_cloid == "T-1789056000-R1" and t.qty == 0.0
    assert abs(t.netted_qty + INC1_T) < 1e-9, "netted dropped on UNKNOWN"
    assert ("T-1789056000-R1", 0) in saved, "ref not persisted before the send"
    ex.step(target(pull=s3, trend=s4))                 # still UNKNOWN
    rs = [c for c in v.calls if c[3].startswith("T-1789056000-R")]
    assert len(rs) == 1, f"re-sent while unconfirmed: {rs}"
    assert "entry_chase" not in [e["kind"] for e in ex.state.events]
    assert ex.state.halted is None
    ex.step(target(pull=s3, trend=s4))                 # read resolves
    assert t.reest_cloid is None and abs(t.qty + INC1_T) < 1e-9
    assert t.netted_qty == 0.0 and abs(v.position() + INC1_T) < 1e-9
    assert len([c for c in v.calls if c[3].startswith("T-1789056000-R")]) == 1


def test_gate_N2_unfilled_R_orders_are_capped_then_dropped_loudly(tmp_path):
    """A venue-confirmed unfilled IOC may be re-sent, REEST_MAX times per
    event, then the owed exposure is dropped with a RED and the chase is
    kept from re-opening it at fresh size behind the cap."""
    ex, v, s3, s4 = _seed_inc1(tmp_path)
    ex.step(target(pull=s3, trend=s4))
    v.fire_stop(ex.state.legs["pullback"].stop_cloid)
    v.unfilled_prefix = "T-1789056000-R"
    for _ in range(6):
        ex.step(target(pull=s3, trend=s4))
        assert ex.state.halted is None
    rs = [c for c in v.calls if c[3].startswith("T-1789056000-R")]
    assert len(rs) == mirror.REEST_MAX, rs
    t = ex.state.legs["trend"]
    assert t.netted_qty == 0.0 and t.qty == 0.0 and t.reest_cloid is None
    kinds = [e["kind"] for e in ex.state.events]
    assert "netted_shortfall" in kinds
    assert "entry_chase" not in kinds, "the chase re-opened it behind the cap"
    assert abs(v.position()) < 1e-9


def test_gate_N3_phantom_dominant_halts_instead_of_stripping_a_real_stop(tmp_path):
    """SERIOUS (phantom lens). Ledger {pullback +0.04943 PHANTOM, trend
    -0.0164 real}, venue -0.0164 with a real BUY stop. The ledger says the
    trend is the subordinate; corroboration must run BEFORE anything is
    demoted. Outcome: LEDGER_DIVERGENCE, the halt's own reduce-only flatten
    off a fresh read, no R order, no entry-class order of any kind."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_short(ex, v, stop=79_850.0)
    p = ex.state.legs["pullback"]
    p.qty, p.signal_ts = Q_P, S_PULL                   # the phantom
    n0 = len(v.calls)
    ex.step(target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                             stop=75_300.0),
                   trend=_pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)))
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    opened = [c for c in v.calls[n0:] if c[0] in ("MARKET", "LIMIT")
              and c[3] not in v.reduce_only_cloids]
    assert not opened, f"entry-class order off a phantom: {opened}"
    assert not [c for c in v.calls if c[3] and c[3].endswith("-R1")]
    assert abs(v.position()) < 1e-9, "halt did not flatten off the read"
    assert "stop_subordinated" not in [e["kind"] for e in ex.state.events]


def test_gate_N3_boot_other_mismatch_blocks_entries(tmp_path):
    """`_reconcile_boot`'s ambiguous-mismatch branch now latches
    _boot_mismatch (entries blocked) instead of only paging."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_short(ex, v, stop=79_850.0)
    ex.state.legs["pullback"].qty = Q_P                  # stale opposed ledger
    ex._save_state()
    ex2 = mk(tmp_path, v)                                # restart
    assert ex2._boot_mismatch is True
    assert "position_drift" in [e["kind"] for e in ex2.state.events]


def test_gate_N4_unknown_entry_read_at_booking_does_not_chase(tmp_path):
    """SERIOUS (phantom lens), universal under early booking: the engine
    books the position while the entry read blips UNKNOWN. No chase on top
    of a fill that already rests, qty unchanged, ref kept, one RED."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    pcloid = pullback_limit(ex, v, trend_tl)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    v.fill_limit(pcloid)
    ex.step(pend)                                         # early-booked
    p = ex.state.legs["pullback"]
    assert abs(p.qty - Q_P) < 1e-9
    v.unknown_reads[pcloid] = 5
    n0 = len(v.calls)
    booked = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                              stop=75_300.0), trend=trend_tl)
    ex.step(booked)
    assert not _mkts(v, n0), f"chased on an UNKNOWN read: {_mkts(v, n0)}"
    assert abs(p.qty - Q_P) < 1e-9 and p.entry_cloid == pcloid
    kinds = [e["kind"] for e in ex.state.events]
    assert kinds.count("entry_unconfirmed") == 1
    assert ex.state.halted is None
    assert abs(v.position() - belief(ex, v)) < 1e-9


def test_gate_N5_fill_landing_between_the_two_legs_is_not_a_vanish(tmp_path):
    """SERIOUS (live lens). The maker fill lands AFTER the pullback's
    _sync_leg read its order (OPEN/0) and BEFORE the trend's _maintain_stop
    read its stop (now reduceOnlyCanceled). The trend must see the fill
    when it decides the book shape: no halt, no order, no vanish count."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    pcloid = pullback_limit(ex, v, trend_tl)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    real = v.order_status
    fired = {"done": False}

    def racing(cloid):
        st = real(cloid)
        if cloid == pcloid and not fired["done"]:
            fired["done"] = True
            v.fill_limit(pcloid)              # lands right after this read
            return {"status": "OPEN", "filled_qty": 0.0, "avg_price": None}
        return st
    v.order_status = racing
    n0 = len(v.calls)
    ex.step(pend)
    assert ex.state.halted is None
    assert not _mkts(v, n0)
    assert not (getattr(ex.state, "stop_vanish", None) or {})
    kinds = [e["kind"] for e in ex.state.events]
    assert "stop_subordinated" in kinds and "stop_vanished" not in kinds
    assert abs(ex.state.legs["pullback"].qty - Q_P) < 1e-9
    assert abs(v.position() - belief(ex, v)) < 1e-9


def test_gate_N5_subordinate_stop_that_filled_before_the_flip_is_absorbed(tmp_path):
    """The trend's stop fires (venue flat), THEN the pullback's maker order
    fills (venue +0.04943). The trend leg is fully closed by its own stop
    and nothing was netted away - the FILLED door runs before the
    subordinate head and the attribution reads 'D closed, others hold the
    venue' rather than an inconsistency."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    pcloid = pullback_limit(ex, v, trend_tl)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    v.fire_stop(ex.state.legs["trend"].stop_cloid)
    v.fill_limit(pcloid)
    assert abs(v.position() - Q_P) < 1e-9
    n0 = len(v.calls)
    ex.step(pend)
    assert ex.state.halted is None and not _mkts(v, n0)
    t, p = ex.state.legs["trend"], ex.state.legs["pullback"]
    assert t.qty == 0.0 and t.netted_qty == 0.0 and t.stopped_entry_ts == T_ENTRY
    assert abs(p.qty - Q_P) < 1e-9 and p.netted_qty == 0.0
    kinds = [e["kind"] for e in ex.state.events]
    assert "leg_netted_out" not in kinds and "netting_inconsistent" not in kinds
    assert ex.state.coverage_live.get("stop_filled", 0) == 1


def test_gate_N6_position_read_lagging_its_own_fill_is_re_read(tmp_path, monkeypatch):
    """SERIOUS (live lens). After the dominant's reduce-only close the
    position endpoint answers with the PRE-close net once. That read
    contradicts the venue-confirmed fill and must be re-read, not booked
    as 'the close did nothing' and not halted."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v)
    v.fill_limit(pullback_limit(ex, v, trend_tl))
    booked = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                              stop=75_300.0), trend=trend_tl)
    ex.step(booked)
    ex.step(booked)
    real_pm = v.place_market

    def lagging_pm(side, qty, cloid, reduce_only=False):
        real_pm(side, qty, cloid, reduce_only=reduce_only)
        if cloid.endswith("-X"):
            v.lag_reads = 1                   # the next read is stale
    v.place_market = lagging_pm
    ex.step(target(trend=trend_tl))           # pullback exits
    assert ex.state.halted is None
    kinds = [e["kind"] for e in ex.state.events]
    assert "close_unconfirmed" not in kinds and "ledger_divergence" not in kinds
    assert ex.state.legs["pullback"].qty == 0.0
    assert abs(v.position() + Q_T) < 1e-9
    assert abs(ex.state.legs["trend"].qty + Q_T) < 1e-9


def test_gate_N6_persistent_inconsistency_halts_after_three_polls(tmp_path, monkeypatch):
    """A stop fill whose attribution cannot be made (the venue reports a
    net no split of the ledger explains) leaves the ledger untouched and
    counts; the third consecutive poll halts. One bad read is not a
    divergence; three in a row is."""
    monkeypatch.setattr(mirror, "NETTING_REREAD_SLEEP_S", 0.0)
    v = HLFake2()
    ex = mk(tmp_path, v)
    pullback_long_booked(ex, v, stop=76_642.0)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=76_642.0)
    p = ex.state.legs["pullback"]
    v.orders[p.stop_cloid]["status"] = "FILLED"          # stop 'fired'...
    v._add("MARKET", "BUY", 0.09, "external")            # ...but the venue
    v.orders["external"]["status"] = "FILLED"            # holds MORE long
    polls = 0
    while ex.state.halted is None and polls < 6:
        ex.step(target(pull=pull_tl))
        polls += 1
    assert ex.state.halted == "LEDGER_DIVERGENCE"
    assert polls == mirror.NETTING_MISMATCH_HALT_POLLS, polls
    kinds = [e["kind"] for e in ex.state.events]
    assert kinds.count("netting_inconsistent") == mirror.NETTING_MISMATCH_HALT_POLLS


def test_gate_N7_net_under_the_floor_arms_nothing_and_does_not_halt(tmp_path):
    """SERIOUS (live lens). {+0.0165, -0.0164} nets to 0.0001 BTC ($7.66 at
    76,600): no stop the venue would accept exists. Place none, mark both
    legs engine-enforced, one RED, no vanish count, no halt; when the net
    grows past the floor the stop is placed."""
    v = HLFake2(mid=76_600.0)
    ex = mk(tmp_path, v)
    v._add("MARKET", "BUY", 0.0165, "p-seed")
    v._add("MARKET", "SELL", 0.0164, "t-seed")
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    p.qty, t.qty = 0.0165, -0.0164
    s3 = _pos(entry_ts=S_PULL + 14_400, side="L", stop=75_000.0)
    s4 = _pos(entry_ts=T_ENTRY, side="S", stop=80_000.0)
    for _ in range(3):
        ex.step(target(pull=s3, trend=s4))
    assert ex.state.halted is None
    assert not [c for c in v.calls if c[0] == "STOP"]
    assert p.stop_mode == "engine" and t.stop_mode == "engine"
    kinds = [e["kind"] for e in ex.state.events]
    assert kinds.count("book_stop_under_floor") == 1
    assert "stop_unconfirmed" not in kinds and "stop_unplaceable" not in kinds
    # the net grows past $10
    v._add("MARKET", "BUY", 0.01, "p-more")
    p.qty = 0.0265
    ex.step(target(pull=s3, trend=s4))
    stops = _open_stops(v)
    assert len(stops) == 1 and abs(stops[0]["qty"] - 0.0101) < 1e-9, stops
    assert p.stop_mode == "venue"


def test_gate_N8_same_side_stop_outs_are_never_consumption(tmp_path):
    """BLOCKING (found in MINIMAL-PATCH's identical primitive). Two SAME-
    sign legs, both stops fill on one poll, venue flat: each is its own
    stop-out. Nothing is 'netted out', nothing is re-opened, no order is
    sent, both re-entry guards arm."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    pullback_long_booked(ex, v, stop=76_642.0)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=76_642.0)
    ex.step(target(pull=pull_tl,
                   trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    both = target(pull=pull_tl, trend=_pos(entry_ts=T_ENTRY, side="L",
                                           stop=74_000.0))
    ex.step(both)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert p.stop_cloid and t.stop_cloid
    v.fire_stop(p.stop_cloid)
    v.fire_stop(t.stop_cloid)
    assert abs(v.position()) < 1e-9
    n0 = len(v.calls)
    ex.step(both)
    assert ex.state.halted is None and not _mkts(v, n0)
    assert p.qty == 0.0 and t.qty == 0.0
    assert p.netted_qty == 0.0 and t.netted_qty == 0.0
    assert p.stopped_entry_ts == S_PULL + 14_400 and t.stopped_entry_ts == T_ENTRY
    kinds = [e["kind"] for e in ex.state.events]
    assert "leg_netted_out" not in kinds and "netting_inconsistent" not in kinds
    assert ex.state.coverage_live.get("stop_filled", 0) == 2


def test_gate_N8_only_one_same_side_stop_fills_leaves_the_other_alone(tmp_path):
    v = HLFake2()
    ex = mk(tmp_path, v)
    pullback_long_booked(ex, v, stop=76_642.0)
    pull_tl = _pos(entry_ts=S_PULL + 14_400, side="L", stop=76_642.0)
    ex.step(target(pull=pull_tl,
                   trend={"pending": {"side": "L", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    both = target(pull=pull_tl, trend=_pos(entry_ts=T_ENTRY, side="L",
                                           stop=74_000.0))
    ex.step(both)
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    v.fire_stop(p.stop_cloid)
    assert abs(v.position() - Q_T) < 1e-9
    n0 = len(v.calls)
    ex.step(both)
    assert ex.state.halted is None and not _mkts(v, n0)
    assert p.qty == 0.0 and abs(t.qty - Q_T) < 1e-9 and t.netted_qty == 0.0
    assert t.stop_cloid and v.orders[t.stop_cloid]["status"] == "OPEN"
    assert "leg_netted_out" not in [e["kind"] for e in ex.state.events]


def test_gate_N9a_engine_flipping_the_consumed_leg_releases_the_debt(tmp_path):
    """A consumed SHORT whose engine then reports a LONG with a new
    entry_ts: nothing to re-establish at the stale size - the debt is
    released silently and the ordinary entry path takes over."""
    ex, v, s3, s4 = _seed_inc1(tmp_path)
    ex.step(target(pull=s3, trend=s4))
    v.fire_stop(ex.state.legs["pullback"].stop_cloid)
    # a degraded feed blocks the same-poll re-open, so the debt is owed
    ex.step(target(pull=s3, trend=s4, degraded=True))
    t = ex.state.legs["trend"]
    assert "leg_unmirrored" in [e["kind"] for e in ex.state.events]
    assert abs(t.netted_qty + INC1_T) < 1e-9
    flipped = _pos(entry_ts=INC1_T_TS + 14_400, side="L", stop=70_000.0)
    n0 = len(v.calls)
    ex.step(target(trend=flipped))
    assert t.netted_qty == 0.0 and t.reest_cloid is None
    assert not [c for c in v.calls[n0:] if c[3].endswith("-R1")]
    kinds = [e["kind"] for e in ex.state.events]
    assert "netting_released" in kinds
    ex.step(target(trend=flipped))           # next poll: the ordinary chase
    assert t.qty > 0, "ordinary entry path did not take over"
    assert not [c for c in v.calls[n0:] if c[3] and c[3].endswith("-R1")]


def test_gate_N9b_crash_after_the_R_send_is_booked_at_boot(tmp_path):
    """The process dies between the R send and its confirm. A fresh
    Executor from the state file reads the persisted reest_cloid, books the
    venue's answer BEFORE the ledger is compared, and protects the leg on
    its first poll. No _boot_mismatch."""
    ex, v, s3, s4 = _seed_inc1(tmp_path)
    ex.step(target(pull=s3, trend=s4))
    v.fire_stop(ex.state.legs["pullback"].stop_cloid)
    v.unknown_reads["T-1789056000-R"] = 3            # confirm blips, then die
    ex.step(target(pull=s3, trend=s4))
    t = ex.state.legs["trend"]
    assert t.reest_cloid == "T-1789056000-R1" and t.qty == 0.0
    assert abs(v.position() + INC1_T) < 1e-9        # the R did fill
    ex2 = mk(tmp_path, v)                            # restart
    t2 = ex2.state.legs["trend"]
    assert t2.reest_cloid is None and abs(t2.qty + INC1_T) < 1e-9
    assert t2.netted_qty == 0.0
    assert ex2._boot_mismatch is False
    assert "phantom_position_cleared" not in [e["kind"] for e in ex2.state.events]
    ex2.step(target(trend=s4))
    assert ex2.state.halted is None
    stops = _open_stops(v)
    assert len(stops) == 1 and abs(stops[0]["qty"] - INC1_T) < 1e-9


def test_gate_N9d_close_rejected_because_the_stop_fired_is_absorbed(tmp_path):
    """The dominant's X order is rejected because its stop fired inside
    the cancel window. The stop was kept up until the confirm, so it is
    re-read FILLED and absorbed - the netted trend is re-established, no
    halt, nothing naked."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v)
    v.fill_limit(pullback_limit(ex, v, trend_tl))
    booked = target(pull=_pos(entry_ts=S_PULL + 14_400, side="L",
                              stop=75_300.0), trend=trend_tl)
    ex.step(booked)
    ex.step(booked)
    p = ex.state.legs["pullback"]
    stop_cloid = p.stop_cloid
    v.reject_prefix = "P-"
    v.on_reject = lambda: v.fire_stop(stop_cloid)
    ex.step(target(trend=trend_tl))
    assert ex.state.halted is None
    kinds = [e["kind"] for e in ex.state.events]
    assert "close_rejected" in kinds and "stop_filled_on_venue" in kinds
    assert p.qty == 0.0
    v.reject_prefix = None
    ex.step(target(trend=trend_tl))
    assert_mirrored(ex, v, "settled")
    assert abs(v.position() + Q_T) < 1e-9


def test_gate_N9e_partial_market_entry_is_booked_by_the_confirmed_fill(tmp_path):
    """The trend's IOC fills 0.015 of 0.01647: the ledger carries 0.015,
    the stop is sized 0.015, nothing halts."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    v.partial_market_qty = 0.015
    ex.step(target(trend={"pending": {"side": "S", "limit": -1.0,
                                      "signal_ts": T_ENTRY - 14_400},
                          "position": None}))
    ex.step(target(trend=_pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)))
    t = ex.state.legs["trend"]
    assert ex.state.halted is None
    assert abs(t.qty + 0.015) < 1e-9
    stops = _open_stops(v)
    assert len(stops) == 1 and abs(stops[0]["qty"] - 0.015) < 1e-9
    assert abs(v.position() + 0.015) < 1e-9


def test_gate_N10_pulse_shows_the_new_leg_state_without_sizes(tmp_path):
    import app.main as m
    from fastapi.testclient import TestClient
    from app.main import app
    v = HLFake2()
    ex = mk(tmp_path, v)
    t = ex.state.legs["trend"]
    t.stop_mode, t.netted_qty, t.reest_cloid = "engine", -0.0164, "T-1-R1"
    old = m.EXEC
    m.EXEC = ex
    try:
        with TestClient(app) as c:
            body = c.get("/pulse").json()
    finally:
        m.EXEC = old
    leg = body["legs"]["trend"]
    assert leg["stop_placed"] is False and leg["stop_mode"] == "engine"
    assert leg["netted"] is True and leg["reest_open"] is True
    assert "0.0164" not in str(body) and "netted_qty" not in leg


def test_gate_every_non_reduce_only_market_order_is_entry_class():
    """Static pin of I2: every `venue.place_market` in mirror.py either
    passes reduce_only=True or lives in one of the entry-class functions.
    A third order category cannot appear without editing this list."""
    import inspect
    import re
    src = inspect.getsource(mirror)
    lines = src.splitlines()
    allowed = {"_sync_leg", "_enter_from_fill", "_reestablish",
               "_drill_locked", "_drill_stopfill_locked"}
    hits = []
    for i, line in enumerate(lines):
        if "self.venue.place_market(" not in line:
            continue
        call = " ".join(lines[i:i + 4])
        j = i
        while j >= 0 and not re.match(r"\s{4}def (\w+)", lines[j]):
            j -= 1
        fn = re.match(r"\s{4}def (\w+)", lines[j]).group(1)
        if "reduce_only=True" in call:
            continue
        hits.append(fn)
    assert set(hits) <= allowed, set(hits) - allowed
    assert "_reestablish" in hits and "_enter_from_fill" in hits


def test_gate_N1_subordinate_exit_with_a_resting_remainder_is_not_rebooked(tmp_path):
    """The close-door twin of N1: a pullback maker order printed 0.01 and
    keeps resting; the engine exits the pullback by SIGNAL while it is the
    subordinate (trend -0.01647 dominant). Its 0.01 moves into the
    dominant's debt, the remainder is cancelled, and the accounted ref must
    never re-book the consumed 0.01 while the cancel lands. Venue == ledger
    on every poll, no halt, no second entry."""
    v = HLFake2()
    ex = mk(tmp_path, v)
    trend_tl = _pos(entry_ts=T_ENTRY, side="S", stop=79_850.0)
    trend_short(ex, v, stop=79_850.0)
    pcloid = pullback_limit(ex, v, trend_tl)
    v.partial_fill(pcloid, 0.01)
    pend = target(pull={"pending": {"side": "L", "limit": MID,
                                    "signal_ts": S_PULL}, "position": None},
                  trend=trend_tl)
    ex.step(pend)                                        # books the 0.01
    p, t = ex.state.legs["pullback"], ex.state.legs["trend"]
    assert abs(p.qty - 0.01) < 1e-9
    entries_before = [c for c in v.calls if c[0] == "LIMIT"]
    # engine drops the pullback entirely (pending cancelled, nothing held)
    for i in range(4):
        ex.step(target(trend=trend_tl))
        assert_mirrored(ex, v, f"poll {i}")
        assert [c for c in v.calls if c[0] == "LIMIT"] == entries_before
    assert p.qty == 0.0 and p.entry_cloid is None
    assert v.orders[pcloid]["status"] == "CANCELLED"
    assert abs(t.qty + Q_T) < 1e-9 and t.netted_qty == 0.0
    assert abs(v.position() + Q_T) < 1e-9
    kinds = [e["kind"] for e in ex.state.events]
    assert "ledger_divergence" not in kinds
