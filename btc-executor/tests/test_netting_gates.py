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


# RED until the netting fix lands: strict, so the day one of these passes
# without the fix being the reason, the suite says so.
RED = pytest.mark.xfail(strict=True,
                        reason="netting fix not built yet (task #40)")


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

@RED
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

@RED
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

@RED
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


@RED
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

@RED
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
