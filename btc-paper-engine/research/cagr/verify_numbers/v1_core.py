"""Counter-agent: re-derive H5a/H5b; independent H2a weight + lookahead check."""
import os, sys, json, math, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness as H
import candidates as C

W = C.World()
t0, t1 = H.ts_of("2013-01-01"), H.ts_of("2026-12-31") + 86399
bars = W.bars["btcusd"]; closes = W.closes["btcusd"]

# ---- independent leg trade lists (full history, then windowed by simulate)
pull = W.trades("btcusd", "pullback", None, None)
tr_prod = W.trades("btcusd", "donchian", None, None)
tr_rest = W.trades("btcusd", "donchian", None, None,
                   donchian_fn=H.process_donchian_resting_stop)

# ---- independent unit-weight per-bar return series, my own MTM (not simulate)
ts_all = np.array([b.ts for b in bars]); cl = np.array([b.close for b in bars])
op = np.array([b.open for b in bars])
idx = {t: i for i, t in enumerate(ts_all)}
f = H.LIVE_TAKER_BPS / 1e4
def unit_returns(trades):
    """Per-bar return of a leg at notional = 1x equity at entry (compounding
    within the trade like simulate's fixed-qty). Returns r[i] realised over bar i
    (open..close of bar i, i.e. from close[i-1] to close[i])."""
    eq = np.ones(len(ts_all))
    e = 1.0
    r = np.zeros(len(ts_all))
    for t in trades:
        i0 = idx[t.entry_ts]
        i1 = idx[t.exit_ts] if t.exit_ts is not None else len(ts_all) - 1
        sg = 1 if t.side == "L" else -1
        qty = 1.0 / t.entry_price  # per unit equity at entry
        E = 1.0 - f  # equity after entry fee, per unit equity-at-entry
        prev_mark = E
        # bar i0: from entry price to close
        for i in range(i0, i1 + 1):
            if i == i1 and t.exit_ts is not None:
                val = 1.0 - f + qty * sg * (t.exit_price - t.entry_price) - f * qty * t.exit_price
            else:
                val = 1.0 - f + qty * sg * (cl[i] - t.entry_price)
            base = 1.0 if i == i0 else prev_mark
            r[i] = val / base - 1.0
            prev_mark = val
    return r
rp = unit_returns(pull); rt = unit_returns(tr_prod)
# sigma known at open of bar T (index j): returns r[j-2190 .. j-1]  (r[j-1] completes at close of bar j-1)
def sig_series(r):
    s = pd.Series(r).rolling(H.BARS_PER_YEAR).std(ddof=0).shift(1)
    return s.values
sp_me, st_me = sig_series(rp), sig_series(rt)

# ---- compare against candidates.vol_fn at every entry ts
sp_fn = W.vol_fn("pull", "btcusd", "pullback"); st_fn = W.vol_fn("trend", "btcusd", "donchian")
entries = sorted({t.entry_ts for t in pull + tr_prod + tr_rest if t.entry_ts >= t0})
rows = []
for T in entries:
    j = idx[T]
    rows.append((T, sp_fn(T), sp_me[j], st_fn(T), st_me[j]))
a = np.array([[r[1], r[2], r[3], r[4]] for r in rows])
ok = np.isfinite(a).all(1)
print("entries", len(rows), "finite", ok.sum())
print("pull sigma rel diff max %.2e  med %.2e" % (np.nanmax(abs(a[ok,0]/a[ok,1]-1)), np.nanmedian(abs(a[ok,0]/a[ok,1]-1))))
print("trend sigma rel diff max %.2e med %.2e" % (np.nanmax(abs(a[ok,2]/a[ok,3]-1)), np.nanmedian(abs(a[ok,2]/a[ok,3]-1))))

# ---- lookahead probe: does fn(T) change if we perturb returns at/after bar T?
# direct: recompute harness-style with window shifted by +1 (i.e. including bar T) and see it's different
sp_la = pd.Series(rp).rolling(H.BARS_PER_YEAR).std(ddof=0).values  # includes r[j] (bar T itself) -> lookahead version
d_la = np.array([abs(sp_fn(T) / sp_la[idx[T]] - 1) for T in entries if np.isfinite(sp_la[idx[T]]) and sp_fn(T)==sp_fn(T)])
print("vs LOOKAHEAD variant (incl bar T): median rel diff %.2e (nonzero => harness is NOT the lookahead variant)" % np.median(d_la))

# weights through time
def wts(T):
    a_, b_ = sp_fn(T), st_fn(T)
    c = (C.W_P * a_ + C.W_T * b_) / 2
    return c / a_, c / b_
ww = np.array([wts(T) for T in entries])
yrs = np.array([pd.Timestamp(T, unit="s").year for T in entries])
print("weights by year (pull, trend, gross, trend share):")
for y in sorted(set(yrs)):
    m = ww[yrs == y]
    print(y, "%.3f %.3f %.3f %.2f" % (m[:,0].mean(), m[:,1].mean(), m.sum(1).mean(), (m[:,1]/m.sum(1)).mean()))
print("overall trend share mean %.3f; gross mean %.3f (baseline 1.5)" % ((ww[:,1]/ww.sum(1)).mean(), ww.sum(1).mean()))
pickle.dump(dict(pull=pull, tr_prod=tr_prod, tr_rest=tr_rest), open(os.path.join(HERE, "trades.pkl"), "wb"))
