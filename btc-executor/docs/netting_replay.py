"""Before/after replay of both netting incidents (docs/netting_replays.png).

Drives one executor build through both incident sequences with the
venue-faithful fake and dumps a per-poll trace as JSON; the chart script in
the same commit renders old vs new. usage:
  python3 docs/netting_replay.py <app_root> <tests_dir> <out.json>
(old build: git archive <sha> btc-executor/app btc-executor/tests into a
scratch dir and point app_root/tests_dir at it)
"""
"""
import json
import os
import sys
import tempfile

app_root, tests_dir, out = sys.argv[1:4]
sys.path.insert(0, app_root)
sys.path.insert(0, tests_dir)

from app import mirror                                   # noqa: E402
import test_executor_gates as G                          # noqa: E402

NOW = G.NOW
MID = 76_808.0
BASE = 16_874.0
Q_P, Q_T = 0.04943, 0.01647
T_ENTRY, S_PULL = NOW - 4 * 14_400, NOW - 14_400


class HLFake(G.FakeVenue):
    """Same model as tests/test_netting_gates.py::HLFake (kept local so the
    OLD build's test dir, which lacks that file, can run too)."""

    def __init__(self, equity=100_000.0, mid=MID, mult=0.00001):
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
        o = self.orders[cloid]
        o["status"] = "FILLED"
        self._sweep()

    def fire_stop(self, cloid):
        o = self.orders[cloid]
        net = self.position()
        if not self._reduces(o, net):
            o["status"], o["raw"] = "CANCELLED", "reduceOnlyCanceled"
            return 0.0
        done = round(min(o["qty"], abs(net)), 8)
        o["status"], o["done"] = "FILLED", done
        self._sweep()
        return done


def mk(v):
    cfg = G.Cfg()
    d = tempfile.mkdtemp()
    cfg.state_path = os.path.join(d, "state.json")
    cfg.dry_run = False
    cfg.sizing_base_usd = BASE
    return mirror.Executor(v, cfg, cfg.state_path)


def snap(ex, v, label):
    stops = [(o["side"], o["qty"]) for o in v.orders.values()
             if o["type"] == "STOP" and o["status"] == "OPEN"]
    return {"label": label, "venue": v.position(),
            "pull": ex.state.legs["pullback"].qty,
            "trend": ex.state.legs["trend"].qty,
            "netted": {n: getattr(l, "netted_qty", 0.0)
                       for n, l in ex.state.legs.items()},
            "stops": stops, "halted": ex.state.halted,
            "events": [e["kind"] for e in ex.state.events]}


def pos(entry_ts, side, stop):
    return G._pos(entry_ts=entry_ts, side=side, stop=stop)


def incident1():
    """pullback long booked, trend enters short, pullback stop fires."""
    v = HLFake()
    ex = mk(v)
    tr = []
    ex.step(G.target(pull={"pending": {"side": "L", "limit": MID,
                                       "signal_ts": S_PULL},
                           "position": None}))
    tr.append(snap(ex, v, "S3 pending: limit rests"))
    v.fill_limit(ex.state.legs["pullback"].entry_cloid)
    s3 = pos(S_PULL + 14_400, "L", 76_642.0)
    ex.step(G.target(pull=s3))
    tr.append(snap(ex, v, "engine books S3 long"))
    ex.step(G.target(pull=s3, trend={"pending": {"side": "S", "limit": -1.0,
                                                 "signal_ts": T_ENTRY - 14_400},
                                     "position": None}))
    tr.append(snap(ex, v, "S4 enters short at market"))
    s4 = pos(T_ENTRY, "S", 80_907.0)
    ex.step(G.target(pull=s3, trend=s4))
    tr.append(snap(ex, v, "engine books S4 short"))
    ex.step(G.target(pull=s3, trend=s4))
    tr.append(snap(ex, v, "steady state"))
    p = ex.state.legs["pullback"]
    if p.stop_cloid and v.orders[p.stop_cloid]["status"] == "OPEN":
        v.fire_stop(p.stop_cloid)
    tr.append(snap(ex, v, "price hits S3 stop (venue fills the NET)"))
    for i in range(3):
        ex.step(G.target(trend=s4))
        tr.append(snap(ex, v, f"poll +{i + 1}: engine S3 stopped, S4 held"))
    return tr


def incident2():
    """trend short on; pullback maker entry rests, fills through it."""
    v = HLFake()
    ex = mk(v)
    tr = []
    ex.step(G.target(trend={"pending": {"side": "S", "limit": -1.0,
                                        "signal_ts": T_ENTRY - 14_400},
                            "position": None}))
    s4 = pos(T_ENTRY, "S", 79_850.0)
    ex.step(G.target(trend=s4))
    tr.append(snap(ex, v, "S4 short on, stop resting"))
    pend = G.target(pull={"pending": {"side": "L", "limit": MID,
                                      "signal_ts": S_PULL}, "position": None},
                    trend=s4)
    ex.step(pend)
    tr.append(snap(ex, v, "S3 pending: maker limit rests"))
    v.fill_limit(ex.state.legs["pullback"].entry_cloid)
    tr.append(snap(ex, v, "limit fills THROUGH the short (00:03:32)"))
    for i in range(2):
        ex.step(pend)
        tr.append(snap(ex, v, f"poll +{i + 1}: engine still PENDING"))
    s3 = pos(S_PULL + 14_400, "L", 75_300.0)
    ex.step(G.target(pull=s3, trend=s4))
    tr.append(snap(ex, v, "04:00 engine books S3"))
    ex.step(G.target(pull=s3, trend=s4))
    tr.append(snap(ex, v, "steady state"))
    ex.step(G.target(pull=s3))
    tr.append(snap(ex, v, "S4 trail hit: engine drops S4"))
    ex.step(G.target(pull=s3))
    tr.append(snap(ex, v, "poll after"))
    return tr


json.dump({"inc1": incident1(), "inc2": incident2()}, open(out, "w"), indent=1)
print("wrote", out)
