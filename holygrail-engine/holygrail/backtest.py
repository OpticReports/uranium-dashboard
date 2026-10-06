"""Walk-forward backtest of an allocator, with explicit timing:

    At an estimation date t (a schedule date), the covariance is estimated on
    returns r_{t-W+1..t} (data strictly before t+1), weights are computed and
    traded at the CLOSE of t; they earn returns from t+1 on.

Daily mechanics, per period k > t0 (w = risky weights as fractions of equity
at the previous close, cash c = 1 - sum w; c < 0 is borrowing):
    r_p,k = w'r_k + c rf_k + min(c, 0) spread_k        (spread on borrowing only)
    E_k   = E_{k-1} (1 + r_p,k)
    w     <- w * (1 + r_k) / (1 + r_p,k)               (drift)
On a trade at close k:  turnover = sum |w_target - w|,
    cost = turnover * cost_bps / 1e4,  E_k <- E_k (1 - cost),  w <- w_target.
The first trade (from all-cash at t0) is charged too; E starts at 1.0 before it.
Measurement basis: daily mark-to-market of the rebalanced book.  Everything
reported is in-sample history, not a forecast.
"""
from __future__ import annotations

import inspect
import math
from dataclasses import asdict, dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .allocate import get_allocator
from .core import validate_covariance
from .errors import ValidationError
from .estimate import ewma_cov, ledoit_wolf_constant_corr, ledoit_wolf_identity, sample_cov
from .metrics import benchmark_comparison, performance_metrics


@dataclass
class BacktestConfig:
    """Walk-forward settings.  ``allocator`` is a registry name (allocate.ALLOCATORS)
    or a callable f(S_annual) / f(S_annual, window_returns) -> weights."""
    allocator: str | Callable = "erc"
    allocator_kwargs: dict = field(default_factory=dict)
    window: int = 252
    min_periods: int | None = None
    estimator: str = "sample"           # sample | ewma | lw | lw_cc
    halflife: float | None = None
    rebalance: str | int = "M"          # D | W | M | Q | A | every-k-periods int
    band: float | None = None           # trade only when max |w - target| > band
    cost_bps: float = 0.0
    financing_spread: float = 0.0       # annual, charged on borrowed fraction only
    target_vol: float | None = None     # annual ex-ante vol target (gearing)
    max_leverage: float = 1.0           # cap on gross exposure sum |w|
    periods_per_year: float = 252.0
    start_when: str = "all"             # 'all' streams eligible, or 'any'

    def validate(self) -> None:
        """Raise ValidationError on any out-of-range setting (window, estimator, costs, leverage, band, schedule)."""
        if self.window < 2:
            raise ValidationError("window must be >= 2")
        mp = self.min_periods or self.window
        if mp < 2 or mp > self.window:
            raise ValidationError("min_periods must be in [2, window]")
        if self.estimator not in ("sample", "ewma", "lw", "lw_cc"):
            raise ValidationError(f"unknown estimator {self.estimator!r}")
        if self.estimator == "ewma" and not self.halflife:
            raise ValidationError("ewma estimator needs halflife")
        if self.cost_bps < 0 or self.financing_spread < 0:
            raise ValidationError("costs must be >= 0")
        if self.max_leverage <= 0:
            raise ValidationError("max_leverage must be > 0")
        if self.band is not None and self.band < 0:
            raise ValidationError("band must be >= 0")
        if self.target_vol is not None and self.target_vol <= 0:
            raise ValidationError("target_vol must be > 0")
        if self.start_when not in ("all", "any"):
            raise ValidationError("start_when must be 'all' or 'any'")
        if isinstance(self.rebalance, str) and self.rebalance.upper() not in ("D", "W", "M", "Q", "A"):
            raise ValidationError(f"unknown rebalance {self.rebalance!r}")
        if isinstance(self.rebalance, int) and self.rebalance < 1:
            raise ValidationError("rebalance every-k must be >= 1")


@dataclass
class BacktestResult:
    """Everything run_backtest produced: equity/returns series, weights, targets, turnover, costs, leverage, metrics."""
    equity: pd.Series          # E_k, from t0 (after the initial trade cost)
    returns: pd.Series         # per-period net returns from t0+1
    weights: pd.DataFrame      # end-of-period holdings (after any trade)
    targets: pd.DataFrame      # target weights at each estimation date
    turnover: pd.Series
    costs: pd.Series
    leverage: pd.Series        # gross exposure sum |w| at each close
    cash_weight: pd.Series
    ex_ante_vol: pd.Series     # annual ex-ante vol of the target at estimation dates
    metrics: dict
    benchmark: dict | None
    config: dict
    notes: list


def schedule_mask(index: pd.DatetimeIndex, rule: str | int, start: int = 0) -> np.ndarray:
    """Boolean mask of estimation dates.  'D' every date; 'W'/'M'/'Q'/'A' the
    LAST date of each calendar week/month/quarter/year present in ``index``;
    an int k every k-th date counting from position ``start``.  The final
    date of ``index`` is never an estimation date (no return follows it)."""
    n = len(index)
    m = np.zeros(n, bool)
    if isinstance(rule, (int, np.integer)):
        m[start::int(rule)] = True
        m[-1] = False if n > 1 else m[-1]
        return m
    r = rule.upper()
    if r == "D":
        m[:] = True
        m[-1] = False if n > 1 else m[-1]
        return m
    key = {"W": index.to_period("W-FRI"), "M": index.to_period("M"), "Q": index.to_period("Q"),
           "A": index.to_period("Y")}[r]
    k = np.asarray(key.astype(str))
    m[:-1] = k[:-1] != k[1:]
    # The final date is never a calendar estimation date: no return follows
    # it, so a trade there would only book a cost.  (The schedule depends on
    # the trading calendar alone, never on returns.)
    m[-1] = False
    return m


def _estimate(window: pd.DataFrame, cfg: BacktestConfig) -> np.ndarray:
    if cfg.estimator == "sample":
        S = sample_cov(window)
    elif cfg.estimator == "ewma":
        S = ewma_cov(window, cfg.halflife)
    elif cfg.estimator == "lw":
        S, _ = ledoit_wolf_identity(window)
    else:
        S, _ = ledoit_wolf_constant_corr(window)
    return validate_covariance(S) * cfg.periods_per_year


def _make_allocator(cfg: BacktestConfig) -> Callable:
    if callable(cfg.allocator):
        fn = cfg.allocator
        try:
            nparams = len(inspect.signature(fn).parameters)
        except (TypeError, ValueError):
            nparams = 1
        if nparams >= 2:
            return lambda S, win: fn(S, win, **cfg.allocator_kwargs)
        return lambda S, win: fn(S, **cfg.allocator_kwargs)
    base = get_allocator(cfg.allocator)
    return lambda S, win: base(S, **cfg.allocator_kwargs)


def run_backtest(returns: pd.DataFrame, config: BacktestConfig | None = None, *,
                 rf: pd.Series | float = 0.0, benchmark: pd.Series | None = None) -> BacktestResult:
    """Run the walk-forward backtest (timing and mechanics in the module
    docstring).  ``returns``: per-period simple returns (dates x streams), NaN
    before a stream's history starts.  ``rf``: per-period cash return series
    on the same dates, or an ANNUAL constant (divided by periods_per_year).
    Streams enter once they have ``min_periods`` returns inside the window;
    estimation uses the window rows where every eligible stream has data.
    A held stream with a NaN return raises (it cannot be valued)."""
    cfg = config or BacktestConfig()
    cfg.validate()
    if not isinstance(returns, pd.DataFrame) or not isinstance(returns.index, pd.DatetimeIndex):
        raise ValidationError("returns must be a DataFrame with a DatetimeIndex")
    if not returns.index.is_monotonic_increasing or returns.index.has_duplicates:
        raise ValidationError("returns index must be sorted and unique")
    R = returns.astype(float)
    if np.isinf(R.to_numpy()).any():
        raise ValidationError("returns contain inf")
    if (R <= -1).to_numpy().any():
        raise ValidationError("returns contain a value <= -100%")
    idx = R.index
    T, N = R.shape
    q = cfg.periods_per_year
    if isinstance(rf, pd.Series):
        rf_s = rf.reindex(idx)
        if rf_s.isna().any():
            raise ValidationError(f"rf series missing {int(rf_s.isna().sum())} return dates")
    else:
        rf_s = pd.Series(float(rf) / q, index=idx)
    rf_v = rf_s.to_numpy()
    spread_p = cfg.financing_spread / q
    mp = cfg.min_periods or cfg.window
    W = cfg.window
    X = R.to_numpy()
    valid = ~np.isnan(X)
    csum = np.vstack([np.zeros((1, N)), np.cumsum(valid, axis=0)])

    def eligible(k: int) -> np.ndarray:
        lo = max(0, k + 1 - W)
        return (csum[k + 1] - csum[lo]) >= mp

    alloc = _make_allocator(cfg)
    sched_all = schedule_mask(idx, cfg.rebalance)
    k0 = None
    for k in range(T):
        el = eligible(k)
        ok = el.all() if cfg.start_when == "all" else el.any()
        if ok and (sched_all[k] or isinstance(cfg.rebalance, (int, np.integer))):
            k0 = k
            break
    if k0 is None:
        raise ValidationError("no estimation date with enough history; shorten window/min_periods")
    sched = schedule_mask(idx, cfg.rebalance, start=k0) if isinstance(cfg.rebalance, (int, np.integer)) else sched_all

    E = 1.0
    w = np.zeros(N)
    target = None
    eq, wts, turn, cst, lev, cashw = [], [], [], [], [], []
    tgt_rows, tgt_dates, exante = [], [], []
    for k in range(k0, T):
        if k > k0:
            r = X[k]
            held = w != 0
            if np.isnan(r[held]).any():
                bad = [R.columns[i] for i in np.flatnonzero(held & np.isnan(r))]
                raise ValidationError(f"held streams {bad} have no return on {idx[k].date()}")
            r = np.where(np.isnan(r), 0.0, r)
            c = 1.0 - w.sum()
            rp = float(w @ r + c * rf_v[k] + min(c, 0.0) * spread_p)
            if rp <= -1:
                raise ValidationError(f"book wiped out on {idx[k].date()} (return {rp:.2%})")
            E *= 1.0 + rp
            w = w * (1.0 + r) / (1.0 + rp)
        if sched[k]:
            el = eligible(k)
            cols = np.flatnonzero(el)
            if len(cols):
                win = R.iloc[max(0, k + 1 - W): k + 1, cols].dropna(how="any")
                if len(win) < 2:
                    raise ValidationError(f"{idx[k].date()}: estimation window has {len(win)} complete rows")
                S = _estimate(win, cfg)
                wa = np.asarray(alloc(S, win), float)
                if wa.shape != (len(cols),) or not np.all(np.isfinite(wa)):
                    raise ValidationError(f"allocator returned invalid weights on {idx[k].date()}")
                vol = math.sqrt(max(float(wa @ S @ wa), 0.0))
                L = 1.0
                if cfg.target_vol is not None:
                    if vol <= 0:
                        raise ValidationError(f"zero ex-ante vol on {idx[k].date()}; cannot vol-target")
                    L = cfg.target_vol / vol
                gross = float(np.abs(wa).sum()) * L
                if gross > cfg.max_leverage:
                    L *= cfg.max_leverage / gross
                target = np.zeros(N)
                target[cols] = L * wa
                tgt_rows.append(target.copy())
                tgt_dates.append(idx[k])
                exante.append(L * vol)
        trade = False
        if target is not None:
            if k == k0:
                trade = True
            elif cfg.band is None:
                trade = bool(sched[k])
            else:
                trade = bool(np.max(np.abs(w - target)) > cfg.band)
        to = cost = 0.0
        if trade:
            to = float(np.abs(target - w).sum())
            cost = to * cfg.cost_bps / 1e4
            E *= 1.0 - cost
            w = target.copy()
        eq.append(E)
        wts.append(w.copy())
        turn.append(to)
        cst.append(cost)
        lev.append(float(np.abs(w).sum()))
        cashw.append(1.0 - float(w.sum()))
    dates = idx[k0:]
    equity = pd.Series(eq, index=dates, name="equity")
    rets = (equity / equity.shift(1) - 1.0).iloc[1:].rename("return")
    weights = pd.DataFrame(wts, index=dates, columns=R.columns)
    targets = pd.DataFrame(tgt_rows, index=pd.DatetimeIndex(tgt_dates), columns=R.columns)
    notes = [f"first estimation/trade date {dates[0].date()} (warm-up {mp} periods in a {W}-period window)",
             "daily mark-to-market; in-sample history, not a forecast",
             "streams chosen ex post: survivorship / selection bias (today's choices replayed over their history)"]
    metrics = performance_metrics(rets, periods_per_year=q, rf=rf_s.loc[rets.index], base_value=1.0,
                                  start_value=float(equity.iloc[0]), start_date=dates[0]) if len(rets) >= 2 else {}
    bench = None
    if benchmark is not None:
        b = pd.Series(benchmark, dtype=float).reindex(rets.index)
        if b.isna().any():
            raise ValidationError(f"benchmark missing {int(b.isna().sum())} dates of the backtest")
        bench = benchmark_comparison(rets, b, periods_per_year=q, rf=rf_s.loc[rets.index])
    cfgd = asdict(cfg)
    cfgd["allocator"] = cfg.allocator if isinstance(cfg.allocator, str) else getattr(cfg.allocator, "__name__", "callable")
    return BacktestResult(equity, rets, weights, targets, pd.Series(turn, index=dates, name="turnover"),
                          pd.Series(cst, index=dates, name="cost"), pd.Series(lev, index=dates, name="gross"),
                          pd.Series(cashw, index=dates, name="cash"),
                          pd.Series(exante, index=pd.DatetimeIndex(tgt_dates), name="ex_ante_vol"),
                          metrics, bench, cfgd, notes)
