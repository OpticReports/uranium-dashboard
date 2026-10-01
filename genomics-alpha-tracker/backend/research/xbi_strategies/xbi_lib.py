"""XBI strategy study - engine. See PREREG.md (frozen before the first run).

One convention everywhere: weights decided on the close of bar i are applied
to the return from close i to close i+1. Cash = 1 - sum(long weights) earns
the BIL total return (SHV before BIL lists, 0 before that); negative cash
(leverage) pays BIL + MARGIN_SPREAD. Short proceeds earn nothing; shorts pay
borrow. Costs are charged on |delta weight| per symbol at that symbol's rate.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))
DATA = BACKEND / "data"
CACHE = DATA / "xbi_study_cache"
NAMES_CACHE = DATA / "backtest_bars.json"          # the 32 survivors, campaign lane

ETFS = ["XBI", "IBB", "XLV", "XPH", "SPY", "QQQ", "IWM", "TLT", "IEF", "GLD",
        "BIL", "SHV", "LABU", "LABD"]
COST_BPS = {"default_etf": 5.0, "name": 25.0, "LABU": 10.0, "LABD": 10.0}
BORROW = {"default_etf": 0.005, "name": 0.03, "LABU": 0.08, "LABD": 0.08}
MARGIN_SPREAD = 0.015
TD = 252


# --- data -----------------------------------------------------------------------------

def _closes(sym: str) -> dict[str, float]:
    from scripts.lib.fmp_prices import fmp_bars
    return {r["date"]: float(r["adjClose"]) for r in fmp_bars(sym, start="2005-01-01", cache_dir=CACHE)
            if r.get("adjClose")}


def _names() -> dict[str, dict[str, float]]:
    if not NAMES_CACHE.exists():
        return {}
    raw = json.loads(NAMES_CACHE.read_text())
    return {s: {r["date"]: float(r["adj_close"]) for r in rows if r.get("adj_close")}
            for s, rows in raw.items() if s != "XBI"}


class Market:
    """Everything aligned to XBI's trading calendar; prices forward-filled,
    NaN before a symbol lists."""

    def __init__(self) -> None:
        px = {s: _closes(s) for s in ETFS}
        px.update(_names())
        self.dates = sorted(px["XBI"])
        self.n = len(self.dates)
        self.idx = {d: i for i, d in enumerate(self.dates)}
        self.syms = list(px)
        self.names = [s for s in self.syms if s not in ETFS]
        self.px: dict[str, np.ndarray] = {}
        for s, ser in px.items():
            a = np.full(self.n, np.nan)
            last = np.nan
            for i, d in enumerate(self.dates):
                if d in ser:
                    last = ser[d]
                a[i] = last
            self.px[s] = a
        self.ret = {s: self._rets(a) for s, a in self.px.items()}
        # cash yield: BIL, else SHV, else 0
        cy = np.where(np.isnan(self.ret["BIL"]), self.ret["SHV"], self.ret["BIL"])
        self.cash = np.nan_to_num(cy, nan=0.0)
        d = [date.fromisoformat(x) for x in self.dates]
        self.d = d
        self.month_end = np.array([i == self.n - 1 or d[i].month != d[i + 1].month for i in range(self.n)])

    @staticmethod
    def _rets(a: np.ndarray) -> np.ndarray:
        r = np.full_like(a, np.nan)
        r[1:] = a[1:] / a[:-1] - 1.0
        return r

    # indicators (all use data through bar i only)
    def sma(self, sym: str, n: int) -> np.ndarray:
        a = self.px[sym]
        out = np.full(self.n, np.nan)
        c = np.nancumsum(np.nan_to_num(a))
        valid = ~np.isnan(a)
        cv = np.cumsum(valid)
        for i in range(n - 1, self.n):
            if cv[i] - (cv[i - n] if i >= n else 0) == n:
                out[i] = (c[i] - (c[i - n] if i >= n else 0.0)) / n
        return out

    def vol(self, sym: str, n: int) -> np.ndarray:
        r = self.ret[sym]
        out = np.full(self.n, np.nan)
        for i in range(n, self.n):
            w = r[i - n + 1:i + 1]
            if not np.isnan(w).any():
                out[i] = w.std(ddof=1) * math.sqrt(TD)
        return out

    def drawdown_from_high(self, sym: str, n: int) -> np.ndarray:
        a = self.px[sym]
        out = np.full(self.n, np.nan)
        for i in range(n - 1, self.n):
            w = a[i - n + 1:i + 1]
            if not np.isnan(w).any():
                out[i] = 1.0 - a[i] / w.max()
        return out

    def momentum(self, sym: str, lookback: int, skip: int) -> np.ndarray:
        a = self.px[sym]
        out = np.full(self.n, np.nan)
        for i in range(lookback, self.n):
            p0, p1 = a[i - lookback], a[i - skip]
            if not (np.isnan(p0) or np.isnan(p1)):
                out[i] = p1 / p0 - 1.0
        return out

    def rsi(self, sym: str, n: int) -> np.ndarray:
        r = np.nan_to_num(np.diff(self.px[sym], prepend=np.nan), nan=0.0)
        up, dn = np.maximum(r, 0), np.maximum(-r, 0)
        out = np.full(self.n, np.nan)
        au = ad = None
        for i in range(1, self.n):
            if au is None:
                if i >= n:
                    au, ad = up[1:i + 1][-n:].mean(), dn[1:i + 1][-n:].mean()
                else:
                    continue
            else:
                au = (au * (n - 1) + up[i]) / n
                ad = (ad * (n - 1) + dn[i]) / n
            out[i] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
        return out

    def beta(self, sym: str, mkt: str, n: int) -> np.ndarray:
        rs, rm = self.ret[sym], self.ret[mkt]
        out = np.full(self.n, np.nan)
        for i in range(n, self.n):
            a, b = rs[i - n + 1:i + 1], rm[i - n + 1:i + 1]
            if not (np.isnan(a).any() or np.isnan(b).any()) and b.var() > 0:
                out[i] = np.cov(a, b, ddof=1)[0, 1] / b.var(ddof=1)
        return out


# --- simulation -----------------------------------------------------------------------

def _rate(table: dict, sym: str, names: list[str]) -> float:
    if sym in table:
        return table[sym]
    return table["name"] if sym in names else table["default_etf"]


def simulate(m: Market, rule, start: int, end: int | None = None) -> dict:
    """rule(i, state) -> dict[sym, weight] decided at the close of bar i.
    Returns the daily equity curve from bar `start` (equity 1.0 at start)."""
    end = m.n - 1 if end is None else end
    eq = np.full(m.n, np.nan)
    eq[start] = 1.0
    w_prev: dict[str, float] = {}
    state: dict = {}
    turnover = 0.0
    costs = 0.0
    weights_log = []
    for i in range(start, end):
        w = rule(i, state)
        w = {s: float(x) for s, x in w.items()
             if x == x and x != 0.0 and not np.isnan(m.px[s][i])}      # x == x drops NaN
        # trade at the close of i: cost on |delta w|
        tc = 0.0
        for s in set(w) | set(w_prev):
            dw = abs(w.get(s, 0.0) - w_prev.get(s, 0.0))
            tc += dw * _rate(COST_BPS, s, m.names) / 1e4
            turnover += dw
        long_sum = sum(x for x in w.values() if x > 0)
        cash = 1.0 - long_sum
        r = 0.0
        for s, x in w.items():
            rs = m.ret[s][i + 1]
            if np.isnan(rs):
                rs = 0.0
            r += x * rs
            if x < 0:
                r -= abs(x) * _rate(BORROW, s, m.names) / TD
        r += cash * m.cash[i + 1] if cash >= 0 else cash * (m.cash[i + 1] + MARGIN_SPREAD / TD)
        eq[i + 1] = eq[i] * (1.0 + r) * (1.0 - tc)
        costs += tc
        w_prev = w
        weights_log.append(long_sum - sum(x for x in w.values() if x < 0))
    years = (m.d[end] - m.d[start]).days / 365.25
    return {"eq": eq, "start": start, "end": end, "turnover_py": turnover / years,
            "cost_drag_py": costs / years, "avg_gross": float(np.mean(weights_log)) if weights_log else 0.0}


# --- statistics -----------------------------------------------------------------------

def stats(dates: list[date], eq: np.ndarray, i0: int, i1: int) -> dict:
    """On the daily curve between i0 and i1 inclusive (positions carry in)."""
    seg = eq[i0:i1 + 1]
    if np.isnan(seg).any() or len(seg) < 3:
        return {}
    r = seg[1:] / seg[:-1] - 1.0
    years = (dates[i1] - dates[i0]).days / 365.25
    cagr = (seg[-1] / seg[0]) ** (1 / years) - 1.0
    sd = r.std(ddof=1)
    sharpe = r.mean() / sd * math.sqrt(TD) if sd > 0 else float("nan")
    dn = math.sqrt(np.mean(np.minimum(r, 0.0) ** 2))
    sortino = r.mean() / dn * math.sqrt(TD) if dn > 0 else float("nan")
    peak = np.maximum.accumulate(seg)
    dd = 1.0 - seg / peak
    mdd = float(dd.max())
    # longest underwater stretch (calendar days)
    longest, cur_start, open_end = 0, None, False
    for k in range(len(seg)):
        if dd[k] > 0 and cur_start is None:
            cur_start = k - 1
        if dd[k] == 0 and cur_start is not None:
            longest = max(longest, (dates[i0 + k] - dates[i0 + cur_start]).days)
            cur_start = None
    if cur_start is not None:                      # a stretch still open at the window end
        open_len = (dates[i1] - dates[i0 + cur_start]).days
        if open_len > longest:                     # flag it only when IT is the longest
            longest, open_end = open_len, True
    # calendar years
    yrs: dict[int, list[float]] = {}
    for k in range(1, len(seg)):
        yrs.setdefault(dates[i0 + k].year, []).append(seg[k])
    yr_ret, prev = {}, seg[0]
    for y in sorted(yrs):
        yr_ret[y] = yrs[y][-1] / prev - 1.0
        prev = yrs[y][-1]
    worst_y = min(yr_ret, key=yr_ret.get) if yr_ret else None
    return {"start": dates[i0].isoformat(), "end": dates[i1].isoformat(), "years": round(years, 2),
            "end_value": float(seg[-1] / seg[0]), "cagr": float(cagr), "vol": float(sd * math.sqrt(TD)),
            "sharpe": float(sharpe), "sortino": float(sortino), "max_dd": mdd,
            "calmar": float(cagr / mdd) if mdd > 0 else float("nan"),
            "underwater_days": int(longest), "underwater_open": open_end,
            "worst_year": worst_y, "worst_year_ret": float(yr_ret[worst_y]) if worst_y else None,
            "years_ret": {str(y): float(v) for y, v in yr_ret.items()}}


def weekly(dates: list[date], eq: np.ndarray, i0: int, i1: int) -> list[list]:
    out = []
    for i in range(i0, i1 + 1):
        if i == i1 or dates[i].isocalendar()[1] != dates[i + 1].isocalendar()[1]:
            out.append([dates[i].isoformat(), round(float(eq[i]), 6)])
    return out


def first_index_on_or_after(m: Market, d: str) -> int:
    for i, x in enumerate(m.dates):
        if x >= d:
            return i
    raise ValueError(d)
