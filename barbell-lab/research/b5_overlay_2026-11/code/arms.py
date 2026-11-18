"""The 53 pre-registered timing arms (PREREG.md + DEVIATIONS.md amendment 1), their mirrors, and helpers.

Every builder returns a leg-multiplier path `mult` (T x 7, the DECISION at the close of day t using data <= t).
weights(mult) turns it into target weights with BIL as the residual; lagged() applies the execution lag.
"""
import numpy as np, pandas as pd
import common as C
from common import sma, rsi, monthly_hold, latch, stop_state, fred_daily, monthly_avail

L = C.LEGS; NL = len(L)
ALLI = list(range(NL)); RISKI = [L.index(x) for x in C.RISK]; EQI = [L.index(x) for x in C.EQ]
PRIMARY = ["B3", "B8", "B15", "B17", "A1", "A6", "M1", "M14"]


def weights(mult):
    W = np.zeros((mult.shape[0], NL + 1))
    W[:, :NL] = C.BASE[:NL] * mult
    W[:, NL] = 1.0 - W[:, :NL].sum(1)
    if W.min() < -1e-9:
        raise RuntimeError("negative target weight")
    return np.clip(W, 0, None)


def lagged(W, lag=1):
    """W[t] <- decision of day t-lag (base weights before that). lag=1: signal at close t-1, trade at close t."""
    if lag == 0:
        return W.copy()
    out = np.empty_like(W); out[:lag] = W[0]; out[lag:] = W[:-lag]
    return out


def _f(x):
    """bool/float Series -> float array with NaN (warm-up) = 1.0 (invested)."""
    return np.nan_to_num(np.asarray(x, float), nan=1.0)


def _on(cond_off):
    """cond_off: Series of bool where True = be OUT; NaN-safe (unknown = in)."""
    c = pd.Series(cond_off).astype(float)
    return np.where(c.fillna(0.0).values > 0, 0.0, 1.0)


def expanding_q(x, q, minp=504):
    return x.expanding(min_periods=minp).quantile(q).shift(1)


def vol_indicators(p, tape, leg):
    """A12/A13 ingredients per volume source, spliced 60 trading days after each later source's first bar (D14)."""
    cal = tape["cal"]; srcs = C.VOLSRC[leg]
    ratio = pd.Series(np.nan, index=cal); climax = pd.Series(0.0, index=cal)
    full = p["cal"]
    for k, s in enumerate(srcs):
        v = p["vol"][s].reindex(full).astype(float); r = p["ret"][s].reindex(full)
        if v.dropna().empty:                                   # source not listed yet (truncated-panel tests)
            continue
        dn = (v * (r < 0)).rolling(20, min_periods=20).sum(); up = (v * (r > 0)).rolling(20, min_periods=20).sum()
        rt = (dn / up.replace(0, np.nan))
        z = (v - v.rolling(60, min_periods=60).mean().shift(1)) / v.rolling(60, min_periods=60).std().shift(1)
        cl = ((r < 0) & (z > 3)).astype(float)
        first = v.dropna().index[0]
        start = full[min(full.searchsorted(first) + 60, len(full) - 1)] if k > 0 else full[0]
        m = cal >= start
        ratio[m] = rt.reindex(cal)[m]; climax[m] = cl.reindex(cal)[m]
    return ratio, climax


def build(p, tape, nav):
    """nav: pd.Series of the BASE book NAV on the tape calendar. Returns ordered dict id -> arm dict."""
    cal = tape["cal"]; me = tape["me"]; T = len(cal)
    P = (1 + tape["R"][L]).cumprod()
    ones = np.ones((T, NL))
    arms = {}

    def add(i, label, fam, mult, timed, lo=0.0, hi=1.0, thr=1e-9, mirror=None):
        mult = np.asarray(mult, float)
        if mirror is None:
            mirror = mult.copy(); mirror[:, timed] = lo + hi - mult[:, timed]
        arms[i] = dict(id=i, label=label, fam=fam, mult=mult, mirror=mirror, timed=timed, thr=thr,
                       primary=i in PRIMARY)

    def book(e):
        return np.repeat(np.asarray(e, float)[:, None], NL, 1)

    def legs(states, idx):
        m = ones.copy()
        for j, s in zip(idx, states):
            m[:, j] = s
        return m

    # ---------------- BOOK ----------------
    for i, n in zip(["B1", "B2", "B3"], [50, 100, 200]):
        add(i, f"Book > SMA{n}", "BOOK", book(_on(nav < sma(nav, n))), ALLI)
    nav_me = nav[me]
    m10n = nav_me.rolling(10, min_periods=10).mean()
    add("B4", "Book > 10-month SMA", "BOOK",
        book(monthly_hold((nav_me >= m10n).astype(float).where(m10n.notna()).reindex(cal), me)), ALLI)
    cnav = (1 + tape["R"]["BIL"]).cumprod()
    for i, n in zip(["B5", "B6"], [126, 252]):
        ok = (nav / nav.shift(n) > cnav / cnav.shift(n)).astype(float).where(nav.shift(n).notna())
        add(i, f"Book {n}d return > bills", "BOOK", book(monthly_hold(ok, me)), ALLI)
    s100 = sma(nav, 100)
    for i, x in zip(["B7", "B8", "B9", "B10"], [.04, .06, .08, .10]):
        add(i, f"Book stop {x:.0%}, back on SMA100 cross", "BOOK", book(stop_state(nav.values, x, s100.values)), ALLI)
    for i, x in zip(["B11", "B12", "B13", "B14"], [.04, .06, .08, .10]):
        add(i, f"Book stop {x:.0%}, back after 21d", "BOOK", book(stop_state(nav.values, x, None, 21)), ALLI)
    dd = nav / nav.rolling(252, min_periods=1).max() - 1
    add("B15", "Book graded drawdown 4% / 8%", "BOOK", book(np.where(dd > -.04, 1.0, np.where(dd > -.08, .5, 0.0))), ALLI)
    st = nav / sma(nav, 200) - 1
    add("B16", "Harvest: half when stretch over SMA200 is top decile", "BOOK",
        book(np.where((st > expanding_q(st, .9)).fillna(False), .5, 1.0)), ALLI, lo=.5)
    rs = rsi(nav)
    for i, x in zip(["B17", "B18"], [70, 80]):
        add(i, f"Harvest: half from RSI>{x} until <50", "BOOK", book(latch(rs > x, rs < 50, 1.0, .5)), ALLI, lo=.5)
    r126 = nav / nav.shift(126) - 1
    add("B19", "Harvest: half when 126d return is top decile", "BOOK",
        book(np.where((r126 > expanding_q(r126, .9)).fillna(False), .5, 1.0)), ALLI, lo=.5)
    v20 = nav.pct_change().rolling(20, min_periods=20).std() * np.sqrt(252)
    def quant(e):
        """hold the target until it moves >= 0.05 of book, or sync at a month-end (PREREG engine rule, applied
        in decision space so every arm runs with the same engine threshold)."""
        e = np.asarray(e, float); out = e.copy()
        for t in range(1, len(e)):
            out[t] = e[t] if (abs(e[t] - out[t - 1]) >= .05 or me[t]) else out[t - 1]
        return out
    for i, x in zip(["B20", "B21"], [.08, .10]):
        add(i, f"Vol target {x:.0%} (cap 1.0)", "BOOK", book(quant(np.minimum(1.0, x / v20).fillna(1.0))), ALLI)

    # ---------------- ASSET ----------------
    def per_leg(fn, idx=RISKI):
        return legs([fn(P[L[j]], j) for j in idx], idx)

    a1 = per_leg(lambda x, j: _on(x < sma(x, 200)))
    add("A1", "Each risk leg > its SMA200", "ASSET", a1, RISKI)

    def m10(x, j):
        xm = x[me]; c = (xm >= xm.rolling(10, min_periods=10).mean()).astype(float).where(xm.rolling(10, min_periods=10).mean().notna())
        return monthly_hold(c.reindex(cal), me).values
    add("A2", "Each risk leg > its 10-month SMA", "ASSET", per_leg(m10), RISKI)
    add("A3", "Each risk leg 252d return > bills", "ASSET", per_leg(
        lambda x, j: monthly_hold((x / x.shift(252) > cnav / cnav.shift(252)).astype(float).where(x.shift(252).notna()), me).values), RISKI)

    def redistribute(state):
        """off-weight of RISK legs to the on RISK legs pro-rata, each capped at 1.5x target, rest BIL."""
        m = ones.copy(); b = C.BASE[:NL]
        for t in range(T):
            on = [j for j in RISKI if state[t, j] > 0]
            off = sum(b[j] for j in RISKI if state[t, j] == 0)
            for j in RISKI:
                m[t, j] = 0.0 if state[t, j] == 0 else 1.0
            if on and off > 0:
                tot_on = sum(b[j] for j in on)
                for j in on:
                    m[t, j] = min(1.5, 1.0 + off / tot_on)
        return m
    inv = ones.copy(); inv[:, RISKI] = 1 - a1[:, RISKI]
    add("A4", "A1, off-weight redistributed to on legs", "ASSET", redistribute(a1), RISKI, mirror=redistribute(inv))
    for i, x in zip(["A5", "A6", "A7"], [.08, .12, .16]):
        add(i, f"Per-leg stop {x:.0%}, back on SMA100 cross", "ASSET",
            per_leg(lambda px, j: stop_state(px.values, x, sma(px, 100).values)), RISKI)
    add("A8", "Per-leg vol stop (2.5 monthly sigma)", "ASSET", per_leg(
        lambda px, j: stop_state(px.values, (2.5 * px.pct_change().rolling(60, min_periods=60).std() * np.sqrt(21)).values,
                                 sma(px, 100).values)), RISKI)
    add("A9", "Per-leg harvest: half from RSI>70 until <50", "ASSET",
        per_leg(lambda px, j: latch(rsi(px) > 70, rsi(px) < 50, 1.0, .5)), RISKI, lo=.5)
    a10 = ones.copy(); a10[:, EQI] = a1[:, EQI]
    add("A10", "Equity legs > SMA200 (gold untimed)", "ASSET", a10, EQI)
    gi = [L.index("PHYS")]; a11 = ones.copy(); a11[:, gi] = a1[:, gi]
    add("A11", "Gold > SMA200 (equity untimed)", "ASSET", a11, gi)
    vi = {L[j]: vol_indicators(p, tape, L[j]) for j in RISKI}
    add("A12", "Volume distribution (down/up vol > 1.5 and < SMA50)", "ASSET", per_leg(
        lambda px, j: _on((vi[L[j]][0] > 1.5) & (px < sma(px, 50)))), RISKI)

    def climax(px, j):
        c = vi[L[j]][1].values; out = np.ones(T); left = 0
        for t in range(T):
            if c[t] > 0:
                left = 10
            if left > 0:
                out[t] = 0.0; left -= 1
        return out
    add("A13", "Volume climax: off 10d after a high-volume down day", "ASSET", per_leg(climax), RISKI)

    mom = (P.shift(21) / P.shift(252) - 1)[[L[j] for j in RISKI]]

    def tilt(sign):
        m = ones.copy(); last = np.ones(len(RISKI)); b = C.BASE[:NL][RISKI]
        for t in range(T):
            if me[t] and mom.iloc[t].notna().all():
                rk = mom.iloc[t].values.argsort().argsort()            # 0 = worst
                mm = np.ones(len(RISKI)); mm[rk >= 3] = 1 + .25 * sign; mm[rk <= 1] = 1 - .25 * sign
                last = mm * b.sum() / (mm * b).sum()                   # D11: RISK weight unchanged
            m[t, RISKI] = last
        return m
    add("A14", "Relative-momentum tilt (+/-25%)", "ASSET", tilt(1), RISKI, mirror=tilt(-1))
    add("A15", "Each risk leg vs SMA200 with 2% buffer", "ASSET", per_leg(
        lambda px, j: latch(px < .98 * sma(px, 200), px > 1.02 * sma(px, 200))), RISKI)

    # ---------------- MACRO ----------------
    adj = p["adj"]
    spy = adj["SPY"]; f1 = (spy < sma(spy, 200)).reindex(cal)
    vix = adj["^VIX"].reindex(cal); v3 = adj["^VIX3M"].reindex(cal)
    f2 = (vix > v3).where(v3.notna())
    baa = fred_daily(p, "BAA10Y", p["cal"], 1); f4 = (baa > sma(baa, 252) + .25).where(sma(baa, 252).notna()).reindex(cal)
    un = p["fred"]["UNRATE"]; unf = (un > un.rolling(12, min_periods=12).mean()).where(un.rolling(12, min_periods=12).mean().notna()).dropna()
    f10 = monthly_avail(unf, cal, day=12)

    def eq(state):
        return legs([state] * len(EQI), EQI)
    add("M1", "Equity legs off when SPY < SMA200", "MACRO", eq(_on(f1)), EQI)
    add("M2", "Equity legs off when VIX > VIX3M", "MACRO", eq(_on(f2)), EQI)
    add("M3", "Equity legs off when VIX > 30 (on < 25)", "MACRO", eq(latch(vix > 30, vix < 25)), EQI)
    add("M4", "Equity legs off when Baa spread > 1y avg + 0.25", "MACRO", eq(_on(f4)), EQI)
    hy = (adj["HYG"] / adj["IEF"])
    add("M5", "Equity legs off when HYG/IEF < SMA200", "MACRO", eq(_on((hy < sma(hy, 200)).where(sma(hy, 200).notna()).reindex(cal))), EQI)
    t103 = fred_daily(p, "T10Y3M", cal, 1)
    add("M6", "Equity legs off when 10y-3m curve inverted", "MACRO", eq(_on(t103 < 0)), EQI)
    cp = p["cape"]; cp = cp.groupby(cp.index.to_period("M")).first(); cp.index = cp.index.to_timestamp()
    cp = cp[cp.index >= "1881-01-01"]
    hi80 = monthly_avail((cp > cp.expanding(min_periods=120).quantile(.8).shift(1)).dropna(), cal, months=2)
    hi90 = monthly_avail((cp > cp.expanding(min_periods=120).quantile(.9).shift(1)).dropna(), cal, months=2)
    add("M7", "Equity legs half when CAPE > its 80th pct", "MACRO", eq(np.where(hi80.fillna(0) > 0, .5, 1.0)), EQI, lo=.5)
    add("M8", "Equity legs half when CAPE > its 90th pct", "MACRO", eq(np.where(hi90.fillna(0) > 0, .5, 1.0)), EQI, lo=.5)
    add("M9", "Equity legs off when CAPE > 80th pct AND SPY < SMA200", "MACRO",
        eq(_on((hi80.fillna(0) > 0) & (f1.fillna(False).astype(bool)))), EQI)
    add("M10", "Equity legs off when unemployment > 12m avg", "MACRO", eq(_on(f10)), EQI)
    spm = spy.reindex(cal)[me]; s10 = (spm < spm.rolling(10, min_periods=10).mean())
    spy10 = 1 - monthly_hold((~s10).astype(float).where(spm.rolling(10, min_periods=10).mean().notna()).reindex(cal), me)
    add("M11", "Equity legs off when unemployment rising AND SPY < 10m SMA", "MACRO",
        eq(_on((f10.fillna(0) > 0) & (spy10 > 0))), EQI)
    usd = fred_daily(p, "DTWEXBGS", p["cal"], 6); intl = [L.index("AVDV"), L.index("AVEM")]
    add("M12", "Intl + EM legs off when dollar > SMA200", "MACRO",
        legs([_on((usd > sma(usd, 200)).where(sma(usd, 200).notna()).reindex(cal))] * 2, intl), intl)
    ry = fred_daily(p, "DFII10", p["cal"], 1)
    add("M13", "Gold off when real yield > 126d avg + 0.25", "MACRO",
        legs([_on((ry > sma(ry, 126) + .25).where(sma(ry, 126).notna()).reindex(cal))], gi), gi)
    cnt = sum((x.astype(float).fillna(0) > 0).astype(int) for x in [f1, f2, f4, f10])
    add("M14", "Equity legs off when >= 2 of 4 risk flags", "MACRO", eq(np.where(cnt >= 2, 0.0, 1.0)), EQI)
    add("M15", "Equity legs graded on risk flags (1 = half, 2+ = off)", "MACRO",
        eq(np.where(cnt >= 2, 0.0, np.where(cnt == 1, .5, 1.0))), EQI)
    add("M16", "Equity legs off May-October", "MACRO", eq(np.where((cal.month >= 5) & (cal.month <= 10), 0.0, 1.0)), EQI)
    add("M17", "Whole book off when >= 2 of 4 risk flags", "MACRO", book(np.where(cnt >= 2, 0.0, 1.0)), ALLI)
    assert len(arms) == 53, len(arms)
    flags = dict(spy_below_sma200=f1, vix_backwardation=f2, baa_wide=f4, unrate_rising=f10, cape_hi80=hi80, count=cnt)
    return arms, flags
