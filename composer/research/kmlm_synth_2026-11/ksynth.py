"""The synthetic KMLM series (PREREG.md; rules and their sources in DEVIATIONS.md 3-7).

build(exposure, start, end) -> {day: daily return}, on NYSE sessions:
  strength_k(D) = mean over the 21 sessions ending D-1 of sign(X_k > its 252-session simple average),
                  X_k the market's excess-return index (None until 273 sessions of history)
  on the first session of a month, each market with data gets notional n_k = exposure x basket share /
  (markets with data in the basket) of the month-start NAV; within the month its dollar position is that
  notional x strength x (X_k now / X_k at the month start), so contract counts are fixed and only the
  strength moves them, as the fund's holdings show
  return(D) = sum_k position_k(D-1) x (X_k(D) / X_k(D-1) - 1) / NAV(D-1) + T-bill(D) - costs
"""
import bisect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "kmlm_2026-11"))
import data as kdata  # noqa: E402
import sdata  # noqa: E402

SHARE = {"commodities": 0.25, "currencies": 0.325, "bonds": 0.425}
MA, SMOOTH = 252, 21
COSTS = 0.0090 + 0.0015
_cache = {}


def calendar():
    if "cal" not in _cache:
        _cache["cal"] = sorted(kdata.series("SPY"))
    return _cache["cal"]


def on_calendar(x, cal):
    """the series carried forward onto the calendar (a market closed on a US session keeps its last level)"""
    ds, out = sorted(x), {}
    for d in cal:
        i = bisect.bisect_right(ds, d) - 1
        if i >= 0:
            out[d] = x[ds[i]]
    return out


def strengths(x, cal):
    """{day D: strength in the book at the close of D} = mean of the 21 daily signs ending D-1"""
    days = [d for d in cal if d in x]
    v = [x[d] for d in days]
    sign, run = [None] * len(v), 0.0
    for i in range(len(v)):
        run += v[i]
        if i >= MA:
            run -= v[i - MA]
        if i >= MA - 1:
            sign[i] = 1.0 if v[i] > run / MA else -1.0
    out = {}
    for i in range(MA + SMOOTH - 1, len(v) - 1):
        out[days[i + 1]] = sum(sign[i - SMOOTH + 1:i + 1]) / SMOOTH
    return out


def markets(cal):
    if "mk" not in _cache:
        mk = {}
        for b, names in sdata.BASKETS.items():
            for m in names:
                x = on_calendar(sdata.xr_index(m), cal)
                mk[m] = (b, x, strengths(x, cal), min(sdata.xr_index(m)))
        _cache["mk"] = mk
    return _cache["mk"]


def build(exposure=1.0, start="1980-01-01", end="2024-03-28", gross=False, detail=False):
    cal = [d for d in calendar() if d <= end]
    mk = markets(calendar())
    tb = sdata.tbill()
    out, info = {}, {}
    nav = 1.0
    units = {}                                           # market -> notional at the month start / X at the month start
    for i in range(1, len(cal)):
        d0, d1 = cal[i - 1], cal[i]
        if d1 < start:
            continue
        if not units or d0[:7] != cal[i - 2][:7]:        # d0 is the first session of its month: reset
            live = {m: v for m, v in mk.items() if d0 in v[2] and d0 in v[1]}
            n_in = {b: sum(1 for v in live.values() if v[0] == b) for b in SHARE}
            units = {m: exposure * SHARE[v[0]] / n_in[v[0]] * nav / v[1][d0] for m, v in live.items()}
            info[d0] = dict(n_in)
        pnl = 0.0
        for m, u in units.items():
            _, x, s, _ = mk[m]
            if d0 in s and d1 in x:
                pnl += u * s[d0] * (x[d1] - x[d0])
        r = pnl / nav + (0.0 if gross else tb.get(d1, 0.0) - COSTS / 252)
        out[d1] = r
        nav *= 1 + r
    return (out, info) if detail else out


def level(rets):
    lvl, out = 1.0, {}
    for d in sorted(rets):
        lvl *= 1 + rets[d]
        out[d] = lvl
    return out


def monthly(rets):
    out = {}
    for d in sorted(rets):
        out[d[:7]] = (1 + out.get(d[:7], 0.0)) * (1 + rets[d]) - 1
    return out
