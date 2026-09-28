"""Run the pre-registered candidates (PREREG.md) against the baseline.

Every candidate goes through the identical code path as the baseline:
engine trades from leg_trades() re-run per window, sized and marked by
simulate() at 4.32 bps/side. Writes candidates.json.

Usage: python3 candidates.py [name ...]      (default: all)
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                                                 # noqa: E402

PAIRS = ["btcusd", "ethusd", "ltcusd", "xrpusd"]
W_P, W_T = 0.75 * 1.5, 0.25 * 1.5          # baseline leg weights at k = 1
LOOKBACK = H.BARS_PER_YEAR                   # 1y of 4h bars for trailing vol
WINDOWS = {"FULL 2013-2026": H.FULL, **H.ERAS}


class World:
    """Bars, closes and indicators per pair, loaded once."""

    def __init__(self):
        self.bars = {p: H.load_bars(p) for p in PAIRS}
        self.closes = {p: H.closes_of(b) for p, b in self.bars.items()}
        self.inds = {(p, 20): H.compute_indicators(b, 20)
                     for p, b in self.bars.items()}
        for ch in (55, 100):
            self.inds[("btcusd", ch)] = H.compute_indicators(
                self.bars["btcusd"], ch)
        self._vol = {}

    def trades(self, pair, strategy, t0, t1, channel=20, donchian_fn=None,
               leg=None):
        return H.leg_trades(self.bars[pair], strategy, start_ts=t0, end_ts=t1,
                            inds=self.inds[(pair, channel)], channel=channel,
                            donchian_fn=donchian_fn, leg=leg)

    def vol_fn(self, key, pair, strategy, channel=20, donchian_fn=None):
        """sigma(T): stdev of this leg's per-bar unit-weight return over the
        LOOKBACK bars whose closes are known at the OPEN of bar T, i.e. up to
        and including bar T-1. Built from a full-history engine run; uses
        volatility only, never the sign of returns."""
        if key in self._vol:
            return self._vol[key]
        tr = self.trades(pair, strategy, None, None, channel, donchian_fn)
        r = H.simulate([H.LegSpec(tr, 1.0, pair)], {pair: self.closes[pair]},
                       k=1.0)
        ts, eq = r.ts, r.equity
        ret = np.diff(eq) / eq[:-1]              # ret[i] known at close ts[i+1]
        c1 = np.concatenate([[0.0], np.cumsum(ret)])
        c2 = np.concatenate([[0.0], np.cumsum(ret * ret)])

        def fn(T):
            j = int(np.searchsorted(ts, T - H.BAR_S))   # bar T-1
            if j >= len(ts) or ts[j] != T - H.BAR_S:
                return float("nan")
            hi = j                                  # returns ret[0..j-1]
            lo = hi - LOOKBACK
            if lo < 0:
                return float("nan")
            n = hi - lo
            m = (c1[hi] - c1[lo]) / n
            v = (c2[hi] - c2[lo]) / n - m * m
            return float(np.sqrt(max(v, 0.0)))
        self._vol[key] = fn
        return fn


# --------------------------------------------------------------------------
# candidate constructions: each returns (legs, closes) for a window
# --------------------------------------------------------------------------
def baseline(W, t0, t1):
    return ([H.LegSpec(W.trades("btcusd", "pullback", t0, t1), W_P),
             H.LegSpec(W.trades("btcusd", "donchian", t0, t1), W_T)],
            {"btcusd": W.closes["btcusd"]})


def h1_resting_stop(W, t0, t1):
    return ([H.LegSpec(W.trades("btcusd", "pullback", t0, t1), W_P),
             H.LegSpec(W.trades("btcusd", "donchian", t0, t1,
                                donchian_fn=H.process_donchian_resting_stop),
                       W_T)],
            {"btcusd": W.closes["btcusd"]})


def h2a_invvol(W, t0, t1):
    sp = W.vol_fn("pull", "btcusd", "pullback")
    st = W.vol_fn("trend", "btcusd", "donchian")

    def weights(T):
        a, b = sp(T), st(T)
        if not (a > 0 and b > 0):
            return W_P, W_T
        c = (W_P * a + W_T * b) / 2.0       # same total standalone risk
        return c / a, c / b
    return ([H.LegSpec(W.trades("btcusd", "pullback", t0, t1), W_P,
                       weight_fn=lambda T: weights(T)[0]),
             H.LegSpec(W.trades("btcusd", "donchian", t0, t1), W_T,
                       weight_fn=lambda T: weights(T)[1])],
            {"btcusd": W.closes["btcusd"]})


def h2b_5050(W, t0, t1):
    return ([H.LegSpec(W.trades("btcusd", "pullback", t0, t1), 0.75),
             H.LegSpec(W.trades("btcusd", "donchian", t0, t1), 0.75)],
            {"btcusd": W.closes["btcusd"]})


def h3_xasset_trend(W, t0, t1):
    vols = {p: W.vol_fn(f"trend-{p}", p, "donchian") for p in PAIRS}

    def sleeve_w(pair):
        def fn(T):
            inv = {p: 1.0 / v for p in PAIRS
                   if (v := vols[p](T)) == v and v > 0}
            if pair not in inv:
                # BTC before its own vol history exists: carry the sleeve
                return W_T if pair == "btcusd" and not inv else 0.0
            return W_T * inv[pair] / sum(inv.values())
        return fn
    legs = [H.LegSpec(W.trades("btcusd", "pullback", t0, t1), W_P)]
    for p in PAIRS:
        legs.append(H.LegSpec(W.trades(p, "donchian", t0, t1, leg=f"trend-{p}"),
                              W_T, asset=p, weight_fn=sleeve_w(p)))
    return legs, {p: W.closes[p] for p in PAIRS}


def h4_ensemble(W, t0, t1):
    legs = [H.LegSpec(W.trades("btcusd", "pullback", t0, t1), W_P)]
    for ch in (20, 55, 100):
        legs.append(H.LegSpec(W.trades("btcusd", "donchian", t0, t1,
                                       channel=ch, leg=f"trend{ch}"), W_T / 3))
    return legs, {"btcusd": W.closes["btcusd"]}


CANDIDATES = {
    "baseline": baseline,
    "H1 resting-stop": h1_resting_stop,
    "H2a inv-vol": h2a_invvol,
    "H2b 50/50": h2b_5050,
    "H3 x-asset trend": h3_xasset_trend,
    "H4 trend ensemble": h4_ensemble,
}


def evaluate(W, build):
    out = {}
    for wname, (a, b) in WINDOWS.items():
        t0, t1 = H.ts_of(a), H.ts_of(b) + 86399
        legs, closes = build(W, t0, t1)
        r1 = H.simulate(legs, closes, k=1.0, start_ts=t0, end_ts=t1)
        row = {"k=1": H.stats(r1)}
        if wname.startswith("FULL"):
            unit = np.diff(r1.equity) / r1.equity[:-1]
            ks, meta = H.k_safe(unit)
            rs = H.simulate(legs, closes, k=ks, start_ts=t0, end_ts=t1)
            row["k_safe"] = dict(k=ks, **meta, **H.stats(rs))
            kd = H.k_at_dd(legs, closes, 0.30, start_ts=t0, end_ts=t1)
            rd = H.simulate(legs, closes, k=kd, start_ts=t0, end_ts=t1)
            row["k_dd30"] = dict(k=kd, **H.stats(rd))
        out[wname] = row
    return out


def main():
    names = sys.argv[1:] or list(CANDIDATES)
    t = time.time()
    W = World()
    print(f"data loaded {time.time() - t:.0f}s", flush=True)
    path = os.path.join(HERE, "candidates.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    for n in names:
        t = time.time()
        res[n] = evaluate(W, CANDIDATES[n])
        f = res[n]["FULL 2013-2026"]
        eras = " ".join(f"{(res[n][e]['k=1']['sharpe'] or 0):5.2f}"
                        for e in list(H.ERAS)[:4])
        print(f"{n:20s} FULL k_safe {f['k_safe']['k']:.3f} -> CAGR "
              f"{f['k_safe']['cagr']*100:5.1f}% (DD {f['k_safe']['maxdd']*100:5.1f}%) | "
              f"k_dd30 {f['k_dd30']['k']:.3f} -> {f['k_dd30']['cagr']*100:5.1f}% | "
              f"Sharpe E1-E4 {eras} | {time.time() - t:.0f}s", flush=True)
        with open(path, "w") as fh:
            json.dump(res, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
