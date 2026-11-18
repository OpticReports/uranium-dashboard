"""Portfolio engine + metrics + bootstrap for the B.5 overlay study.

simulate(): weights drift daily; the LAST column is cash (BIL). At the close of day t, in this order:
  1. returns of day t accrue;
  2. optional per-leg trim (H5/H6): a leg in trim_mask above trim_mult x its target is sold back to target,
     proceeds pro-rata to the other non-cash legs' targets;
  3. SIGNAL trade when the target row W[t] differs from the target last traded to by more than `thr` on any
     leg (or by anything on the trading day after a check day). With partial=True only the legs whose target
     changed trade, against cash; if cash cannot fund it the whole book rebalances to W[t];
  4. BAND trade (whole book to W[t]) when the previous day was a check day whose band check breached
     (|w/target-1| > band on a leg with target > 0.005) or >= cal_days trading days since the last trade;
  5. if day t is a check day (me[t]) the band check is evaluated on end-of-day weights for a fill on t+1.
The CALLER lags the target path: W[t] may only contain information from closes <= t-1.
Costs: one-way fraction per leg on |traded notional|. Returns: daily net return, turnover, cost, trigger code
(0 none, 1 band, 2 signal, 3 trim) and the sum of end-of-day realized weights over rows [i0, i1).
"""
import numpy as np
from numba import njit, prange


@njit(cache=True)
def simulate(R, W, cost, me, band, cal_days, thr, partial, trim_mask, trim_mult, i0, i1):
    T, N = R.shape
    C = N - 1
    out = np.empty(T); turn = np.zeros(T); cst = np.zeros(T); trig = np.zeros(T, np.int8)
    wsum = np.zeros(N)
    h = np.zeros(N); newh = np.zeros(N)
    cur = W[0].copy()
    c0 = 0.0
    for i in range(N):
        c0 += cost[i] * abs(cur[i])
    for i in range(N):
        h[i] = cur[i] * (1.0 - c0)
    cst[0] = c0; turn[0] = 1.0; trig[0] = 2
    pending = False
    since = 0
    prev = 1.0
    for t in range(T):
        tot = 0.0
        for i in range(N):
            h[i] *= (1.0 + R[t, i]); tot += h[i]
        since += 1
        if t > 0:
            # 2. per-leg trim
            if trim_mult > 0.0:
                for i in range(C):
                    if trim_mask[i] and cur[i] > 0.0 and h[i] > trim_mult * cur[i] * tot:
                        ex = h[i] - cur[i] * tot
                        den = 0.0
                        for j in range(C):
                            if j != i:
                                den += cur[j]
                        if den <= 0.0:
                            continue
                        cc = cost[i] * ex
                        h[i] -= ex
                        net = ex - cc
                        for j in range(C):
                            if j != i:
                                buy = net * cur[j] / den
                                c2 = cost[j] * buy
                                h[j] += buy - c2
                                cc += c2
                        turn[t] += 2.0 * ex / tot; cst[t] += cc / tot; trig[t] = 3
                        tot -= cc
            # 3/4. signal or band trade
            md = 0.0
            for i in range(N):
                d = abs(W[t, i] - cur[i])
                if d > md:
                    md = d
            do = 0
            if md > thr or (me[t - 1] and md > 1e-12):
                do = 2
            elif pending:
                do = 1
            was_pending = pending
            pending = False
            if do == 2 and partial and not was_pending:
                s = 0.0
                for i in range(C):
                    if abs(W[t, i] - cur[i]) > 1e-12:
                        newh[i] = W[t, i] * tot
                    else:
                        newh[i] = h[i]
                    s += newh[i]
                newh[C] = tot - s
                tv = 0.0; cc = 0.0
                for i in range(N):
                    d = abs(newh[i] - h[i]); tv += d; cc += cost[i] * d
                if newh[C] - cc >= 0.0:
                    for i in range(N):
                        h[i] = newh[i]; cur[i] = W[t, i]
                    h[C] -= cc
                    turn[t] += tv / tot; cst[t] += cc / tot; trig[t] = 2
                    tot -= cc
                    do = 0
                    # a partial trade does not reset the calendar clock
            if do > 0:
                tv = 0.0; cc = 0.0
                for i in range(N):
                    d = abs(W[t, i] * tot - h[i]); tv += d; cc += cost[i] * d
                tot2 = tot - cc
                for i in range(N):
                    h[i] = W[t, i] * tot2; cur[i] = W[t, i]
                turn[t] += tv / tot; cst[t] += cc / tot; trig[t] = do
                tot = tot2
                since = 0
        # 5. band check for a fill tomorrow
        if me[t]:
            br = since >= cal_days
            if not br:
                for i in range(N):
                    if cur[i] > 0.005:
                        if abs(h[i] / tot / cur[i] - 1.0) > band:
                            br = True
                            break
            pending = br
        out[t] = tot / prev - 1.0
        prev = tot
        if t >= i0 and t < i1:
            for i in range(N):
                wsum[i] += h[i] / tot
    return out, turn, cst, trig, wsum


def metrics(r, c, turn=None, cst=None, trig=None):
    """r, c: daily simple returns of the book and of BIL over the evaluation window."""
    r = np.asarray(r, float); c = np.asarray(c, float); n = len(r)
    nav = np.cumprod(1 + r); yrs = n / 252.0
    ex = r - c
    peak = np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    dd = nav / peak - 1
    dn = np.minimum(ex, 0.0)
    cagr = nav[-1] ** (1 / yrs) - 1
    lnav = np.log(np.concatenate([[1.0], nav]))
    w252 = float(np.exp((lnav[252:] - lnav[:-252]).min()) - 1) if n > 252 else float("nan")
    m = dict(cagr=cagr, vol=r.std(ddof=1) * np.sqrt(252), sharpe=ex.mean() / ex.std(ddof=1) * np.sqrt(252),
             sortino=ex.mean() * 252 / (np.sqrt((dn ** 2).mean()) * np.sqrt(252)),
             maxdd=dd.min(), calmar=cagr / abs(dd.min()) if dd.min() < 0 else float("nan"),
             ulcer=np.sqrt((dd ** 2).mean()), worst252=w252, total=nav[-1] - 1, years=yrs)
    if turn is not None:
        m["turnover_yr"] = float(turn.sum() / yrs); m["cost_bps_yr"] = float(cst.sum() / yrs * 1e4)
        m["signal_trades_yr"] = float((trig == 2).sum() / yrs); m["band_trades_yr"] = float((trig == 1).sum() / yrs)
        m["trim_trades_yr"] = float((trig == 3).sum() / yrs)
    return {k: float(v) for k, v in m.items()}


def block_index(T, block, draws, seed):
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, T, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % T
    return idx.reshape(draws, -1)[:, :T].astype(np.int32)


@njit(parallel=True, cache=True)
def boot_pairs(A, B, idx):
    """A, B: T x K BIL-excess daily returns (arm, control). idx: D x T resampled rows.
    Returns D x K arrays of arm-minus-control: Sharpe, annualised mean excess return, max drawdown
    (positive = shallower) and ulcer index (negative = better); drawdowns on the excess-return path."""
    D, T = idx.shape; K = A.shape[1]
    dS = np.empty((D, K)); dM = np.empty((D, K)); dD = np.empty((D, K)); dU = np.empty((D, K))
    for d in prange(D):
        for k in range(K):
            sa = 0.0; sa2 = 0.0; sb = 0.0; sb2 = 0.0
            na = 1.0; pa = 1.0; ma = 0.0; ua = 0.0; nb = 1.0; pb = 1.0; mb = 0.0; ub = 0.0
            for t in range(T):
                j = idx[d, t]
                a = A[j, k]; b = B[j, k]
                sa += a; sa2 += a * a; sb += b; sb2 += b * b
                na *= 1.0 + a
                if na > pa:
                    pa = na
                x = na / pa - 1.0
                ua += x * x
                if x < ma:
                    ma = x
                nb *= 1.0 + b
                if nb > pb:
                    pb = nb
                x = nb / pb - 1.0
                ub += x * x
                if x < mb:
                    mb = x
            mua = sa / T; mub = sb / T
            va = (sa2 - T * mua * mua) / (T - 1); vb = (sb2 - T * mub * mub) / (T - 1)
            s_a = mua / np.sqrt(va) * np.sqrt(252.0) if va > 0 else 0.0
            s_b = mub / np.sqrt(vb) * np.sqrt(252.0) if vb > 0 else 0.0
            dS[d, k] = s_a - s_b; dM[d, k] = (mua - mub) * 252.0; dD[d, k] = ma - mb
            dU[d, k] = np.sqrt(ua / T) - np.sqrt(ub / T)
    return dS, dM, dD, dU


@njit(parallel=True, cache=True)
def placebo_shift(R, Wwin, base_pre, cost, me, band, cal_days, thr, partial, tm, tmult, i0, i1, offsets, c):
    """Circular-shift placebo within the window rows [i0, i1): the arm's own target rows rolled by each offset.
    Rows before i0 hold `base_pre`; rows after i1 hold the last shifted row. Returns per-offset Sharpe (BIL-excess),
    max drawdown, ulcer and CAGR over the window."""
    n = i1 - i0; T = R.shape[0]; N = R.shape[1]; K = len(offsets)
    out = np.empty((K, 4))
    for q in prange(K):
        W = np.empty((T, N))
        for t in range(T):
            if t < i0:
                src = -1
            elif t < i1:
                src = (t - i0 + offsets[q]) % n
            else:
                src = (n - 1 + offsets[q]) % n
            for i in range(N):
                W[t, i] = base_pre[i] if src < 0 else Wwin[src, i]
        r, _, _, _, _ = simulate(R, W, cost, me, band, cal_days, thr, partial, tm, tmult, i0, i1)
        s = 0.0; s2 = 0.0; nav = 1.0; pk = 1.0; md = 0.0; u = 0.0
        for t in range(i0, i1):
            e = r[t] - c[t]; s += e; s2 += e * e
            nav *= 1.0 + r[t]
            if nav > pk:
                pk = nav
            x = nav / pk - 1.0
            u += x * x
            if x < md:
                md = x
        mu = s / n; v = (s2 - n * mu * mu) / (n - 1)
        out[q, 0] = mu / np.sqrt(v) * np.sqrt(252.0)
        out[q, 1] = md; out[q, 2] = np.sqrt(u / n); out[q, 3] = nav ** (252.0 / n) - 1.0
    return out


def sharpe(ex):
    ex = np.asarray(ex, float)
    return float(ex.mean() / ex.std(ddof=1) * np.sqrt(252))


def maxdd(r):
    nav = np.cumprod(1 + np.asarray(r, float)); peak = np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    return float((nav / peak - 1).min())
