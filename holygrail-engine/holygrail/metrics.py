"""Realised performance metrics on a per-period simple-return series.

Measurement basis: whatever the input is.  Backtests feed daily MARK-TO-MARKET
returns of the rebalanced book (not trade-close P&L).  Every metric here is
in-sample history; none is a forecast.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .errors import ValidationError


def _series(r, name: str = "returns") -> pd.Series:
    if not isinstance(r, pd.Series):
        raise ValidationError(f"{name} must be a pandas Series with a DatetimeIndex")
    if not isinstance(r.index, pd.DatetimeIndex):
        raise ValidationError(f"{name} index must be a DatetimeIndex")
    if r.isna().any():
        raise ValidationError(f"{name} contains NaN at {list(r.index[r.isna()][:5])}")
    if (r <= -1).any():
        raise ValidationError(f"{name} has a return <= -100% (wipe-out) at {list(r.index[r <= -1][:3])}")
    return r.astype(float)


def equity_curve(r: pd.Series, base: float = 1.0) -> pd.Series:
    """E_t = base * prod_{s<=t} (1 + r_s)."""
    return base * (1.0 + _series(r)).cumprod()


def drawdown(equity: pd.Series) -> pd.Series:
    """DD_t = E_t / max_{s<=t} E_s - 1  (<= 0)."""
    e = pd.Series(equity, dtype=float)
    return e / e.cummax() - 1.0


def max_drawdown(equity: pd.Series) -> float:
    """min_t DD_t (a negative number, 0 if never under water)."""
    return float(drawdown(equity).min())


def cagr(final_over_initial: float, years: float) -> float:
    """CAGR = (E_end / E_start)^(1/years) - 1 (geometric)."""
    if years <= 0:
        raise ValidationError("years must be > 0")
    if final_over_initial <= 0:
        return -1.0
    return float(final_over_initial ** (1.0 / years) - 1.0)


def ulcer_index(equity: pd.Series) -> float:
    """Ulcer index = sqrt(mean_t DD_t^2) (Martin 1987), as a fraction."""
    dd = drawdown(equity)
    return float(math.sqrt(np.mean(dd.to_numpy() ** 2)))


def time_under_water(equity: pd.Series) -> dict:
    """Longest stretch below a prior peak (calendar days, from the peak date to
    recovery or to the last date if unrecovered) and the fraction of periods
    spent below the running peak."""
    e = pd.Series(equity, dtype=float)
    peak = e.cummax()
    under = e < peak - 1e-15
    longest = 0
    longest_start = longest_end = None
    peak_date = e.index[0]
    for d, u, v, p in zip(e.index, under.to_numpy(), e.to_numpy(), peak.to_numpy()):
        if not u:
            peak_date = d
        else:
            dur = (d - peak_date).days
            if dur > longest:
                longest, longest_start, longest_end = dur, peak_date, d
    return {"max_days": int(longest), "start": longest_start, "end": longest_end,
            "fraction_under_water": float(under.mean())}


def calendar_year_returns(r: pd.Series, start_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """Compounded return per calendar year with a ``complete`` flag: a year is
    complete unless it is the first year and its first return PERIOD starts
    after Jan 10, or the last year ending before Dec 20 (partial years are
    reported but excluded from worst-year and P(loss year)).  A return is
    labelled at the END of its period, so the first period starts at
    ``start_date`` (default: the first label minus one median step) -- a
    month-end series whose first label is Jan 31 covers all of January."""
    r = _series(r)
    if r.empty:
        return pd.DataFrame(columns=["return", "complete", "n"])
    g = (1 + r).groupby(r.index.year)
    out = pd.DataFrame({"return": g.prod() - 1.0, "n": g.size()})
    first, last = r.index[0], r.index[-1]
    if start_date is None:
        start_date = first - pd.Series(r.index).diff().median() if len(r) > 1 else first
    out["complete"] = True
    if pd.Timestamp(start_date) > pd.Timestamp(first.year, 1, 10):
        out.loc[first.year, "complete"] = False
    if last < pd.Timestamp(last.year, 12, 20):
        out.loc[last.year, "complete"] = False
    return out


def performance_metrics(r: pd.Series, *, periods_per_year: float, rf: pd.Series | float = 0.0,
                        base_value: float = 1.0, start_value: float | None = None,
                        start_date: pd.Timestamp | None = None) -> dict:
    """Standard realised metrics for per-period simple returns ``r``.

    CAGR        (E_end / base_value)^(365.25/days) - 1, days from ``start_date``
                (default: one median period before the first return) to the last date
    vol         std(r, ddof=1) sqrt(q)
    sharpe      mean(r - rf) / std(r - rf) sqrt(q)     (rf per period)
    sortino     mean(r - rf) q / (sqrt(mean(min(r - rf, 0)^2)) sqrt(q))
    max_dd      min DD on the equity curve (including the start point)
    calmar      CAGR / |max_dd|
    worst_year, p_loss_year   over COMPLETE calendar years only
    ulcer       sqrt(mean DD^2)
    time_under_water  longest peak-to-recovery stretch (days), fraction under water
    ``start_value`` lets the equity start below base (e.g. after an initial
    trading cost) while CAGR is still measured from base_value."""
    r = _series(r)
    if len(r) < 2:
        raise ValidationError("need at least 2 returns")
    q = float(periods_per_year)
    rf_s = pd.Series(rf, index=r.index, dtype=float) if np.isscalar(rf) else pd.Series(rf, dtype=float).reindex(r.index)
    if rf_s.isna().any():
        raise ValidationError("rf series does not cover every return date")
    ex = r - rf_s
    if start_date is None:
        step = pd.Series(r.index).diff().median()
        start_date = r.index[0] - step
    sv = base_value if start_value is None else start_value
    eq = pd.concat([pd.Series([sv], index=[start_date]), sv * (1 + r).cumprod()])
    days = (r.index[-1] - start_date).days
    years = days / 365.25
    total = float(eq.iloc[-1] / base_value)
    sd = float(r.std(ddof=1))
    exsd = float(ex.std(ddof=1))
    downside = float(np.sqrt(np.mean(np.minimum(ex.to_numpy(), 0.0) ** 2)))
    c = cagr(total, years)
    mdd = max_drawdown(eq)
    cy = calendar_year_returns(r, start_date=start_date)
    full = cy[cy["complete"]]
    tuw = time_under_water(eq)
    return {
        "start": str(start_date.date()), "end": str(r.index[-1].date()), "years": years, "n_periods": len(r),
        "total_return": total - 1.0, "cagr": c,
        "vol": sd * math.sqrt(q),
        "mean_excess_annual": float(ex.mean() * q),
        "sharpe": float(ex.mean() / exsd * math.sqrt(q)) if exsd > 0 else float("nan"),
        "sortino": float(ex.mean() * q / (downside * math.sqrt(q))) if downside > 0 else float("nan"),
        "max_drawdown": mdd,
        "calmar": float(c / abs(mdd)) if mdd < 0 else float("nan"),
        "worst_year": float(full["return"].min()) if len(full) else float("nan"),
        "best_year": float(full["return"].max()) if len(full) else float("nan"),
        "p_loss_year": float((full["return"] < 0).mean()) if len(full) else float("nan"),
        "n_complete_years": int(len(full)),
        "ulcer_index": ulcer_index(eq),
        "max_days_under_water": tuw["max_days"],
        "fraction_under_water": tuw["fraction_under_water"],
        "basis": "per-period mark-to-market returns; in-sample history, not a forecast",
    }


def benchmark_comparison(r: pd.Series, b: pd.Series, *, periods_per_year: float,
                         rf: pd.Series | float = 0.0) -> dict:
    """Strategy vs benchmark on their common dates: both metric sets plus
    excess CAGR, tracking error std(r - b) sqrt(q), information ratio
    mean(r - b) q / TE, beta cov(r, b)/var(b) and correlation."""
    r = _series(r, "strategy")
    b = _series(b, "benchmark")
    idx = r.index.intersection(b.index)
    if len(idx) < 10:
        raise ValidationError("strategy and benchmark share fewer than 10 dates")
    r, b = r.loc[idx], b.loc[idx]
    rf_v = rf if np.isscalar(rf) else pd.Series(rf).reindex(idx)
    ms = performance_metrics(r, periods_per_year=periods_per_year, rf=rf_v)
    mb = performance_metrics(b, periods_per_year=periods_per_year, rf=rf_v)
    a = r - b
    te = float(a.std(ddof=1) * math.sqrt(periods_per_year))
    return {
        "strategy": ms, "benchmark": mb,
        "excess_cagr": ms["cagr"] - mb["cagr"],
        "tracking_error": te,
        "information_ratio": float(a.mean() * periods_per_year / te) if te > 0 else float("nan"),
        "beta": float(np.cov(r, b, ddof=1)[0, 1] / np.var(b, ddof=1)),
        "correlation": float(np.corrcoef(r, b)[0, 1]),
        "max_dd_difference": ms["max_drawdown"] - mb["max_drawdown"],
    }
