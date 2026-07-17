"""Walk-forward backtest engine with mandatory cost accounting.

Simulation model: portfolio holdings drift with daily asset returns;
rebalancing decisions are evaluated at MONTH-END only (spec granularity).
Modes:
  threshold — rebalance a sleeve only when |weight/target − 1| > band
  calendar  — rebalance every `calendar_months` months
  none      — buy and hold from the start weights
Every trade (including the initial buy) pays the per-ticker one-way cost in
bps of traded notional. There is no zero-cost path through this code.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import load, config_hash
from .metrics import summary


@dataclass
class SimResult:
    returns: pd.Series               # daily net returns
    turnover: float                  # sum |trades| / avg wealth, annualized
    n_rebalances: int
    cost_drag_annual: float          # CAGR difference vs the same run with 0 costs
    weights_path: pd.DataFrame = field(repr=False, default=None)


def _cost_vector(tickers: list[str]) -> np.ndarray:
    cfg = load("backtest")["costs_bps"]
    return np.array([float(cfg.get(t, cfg["default"])) * 1e-4 for t in tickers])


def resolve_targets(tail: str = "TAIL") -> dict[str, float]:
    """Expand the TAIL_SLEEVE placeholder into concrete instruments.
    tail may be 'TAIL', 'CAOS', 'BTAL', 'NONE', or 'X+Y' for a 50/50 split."""
    port = load("portfolio")
    targets = dict(port["targets"])
    tail_w = targets.pop("TAIL_SLEEVE", 0.0)
    if tail.upper() == "NONE":
        # reallocate pro-rata — the "no tail sleeve" counterfactual
        s = sum(targets.values())
        targets = {k: v / s for k, v in targets.items()}
    elif "+" in tail:
        a, b = [t.strip().upper() for t in tail.split("+")]
        targets[a] = targets.get(a, 0.0) + tail_w / 2
        targets[b] = targets.get(b, 0.0) + tail_w / 2
    else:
        t = tail.upper()
        targets[t] = targets.get(t, 0.0) + tail_w
    if abs(sum(targets.values()) - 1.0) > 1e-9:
        raise ValueError(f"targets sum to {sum(targets.values())}, not 1.0")
    return targets


def simulate(returns: pd.DataFrame, targets: dict[str, float], mode: str = "threshold",
             band: float | None = None, calendar_months: int | None = None,
             zero_cost_internal: bool = False) -> SimResult:
    """Simulate the target mix over a daily return matrix (columns=tickers)."""
    bcfg = load("backtest")["rebalance"]
    band = float(bcfg["band_relative"]) if band is None else band
    cal_m = int(bcfg["calendar_months"]) if calendar_months is None else calendar_months
    if mode not in ("threshold", "calendar", "none"):
        raise ValueError(f"unknown rebalance mode {mode}")

    tickers = list(targets.keys())
    r = returns[tickers].dropna()
    if len(r) < 40:
        raise ValueError("too little joint history to simulate")
    w_target = np.array([targets[t] for t in tickers])
    costs = np.zeros(len(tickers)) if zero_cost_internal else _cost_vector(tickers)

    wealth = 1.0
    # initial buy pays costs
    holdings = w_target * wealth * (1 - costs)
    month_ends = set(r.groupby(r.index.to_period("M")).apply(lambda g: g.index.max()))
    out, wpath = [], []
    months_since_reb = 0
    n_reb = 0
    total_traded = 1.0  # the initial buy trades 100% of starting wealth

    for dt, row in zip(r.index, r.values):
        holdings = holdings * (1 + row)
        new_wealth = holdings.sum()
        out.append((dt, new_wealth / wealth - 1.0))
        wealth = new_wealth
        if dt in month_ends:
            months_since_reb += 1
            w_now = holdings / wealth
            do_reb = False
            if mode == "threshold":
                rel = np.abs(w_now / w_target - 1.0)
                do_reb = bool((rel > band).any())
            elif mode == "calendar":
                do_reb = months_since_reb >= cal_m
            if do_reb:
                target_holdings = w_target * wealth
                trades = target_holdings - holdings
                fee = float(np.sum(np.abs(trades) * costs))
                wealth -= fee
                holdings = w_target * wealth
                out[-1] = (dt, out[-1][1] - fee / new_wealth)
                total_traded += float(np.abs(trades).sum())
                n_reb += 1
                months_since_reb = 0
            wpath.append((dt, dict(zip(tickers, w_now))))

    ret = pd.Series({d: v for d, v in out}).sort_index()
    ret.index = pd.DatetimeIndex(ret.index)
    years = len(ret) / 252
    result = SimResult(
        returns=ret,
        turnover=total_traded / max(years, 1e-9),
        n_rebalances=n_reb,
        cost_drag_annual=np.nan,
        weights_path=pd.DataFrame([w for _, w in wpath],
                                  index=pd.DatetimeIndex([d for d, _ in wpath])),
    )
    if not zero_cost_internal:
        free = simulate(returns, targets, mode=mode, band=band,
                        calendar_months=cal_m, zero_cost_internal=True)
        from .metrics import cagr
        result.cost_drag_annual = cagr(free.returns) - cagr(ret)
    return result


def walk_forward(returns: pd.DataFrame, train_fn, scheme: str | None = None) -> list[dict]:
    """Generic walk-forward harness for anything that FITS on history.

    train_fn(train_returns) -> weights dict. Returns one record per test
    window with the out-of-sample summary. Used by the optimizer suite; the
    fixed-target baseline needs no fitting and calls simulate() directly.
    """
    wf = load("backtest")["walk_forward"]
    scheme = scheme or wf["scheme"]
    min_train = int(wf["min_train_years"] * 252)
    test_len = int(wf["test_months"] * 21)
    step = int(wf["step_months"] * 21)
    roll_len = int(wf["rolling_years"] * 252)
    if scheme not in ("expanding", "rolling"):
        raise ValueError(f"unknown walk-forward scheme {scheme}")

    records = []
    start = min_train
    while start + test_len <= len(returns):
        train = returns.iloc[max(0, start - roll_len) if scheme == "rolling" else 0:start]
        test = returns.iloc[start:start + test_len]
        weights = train_fn(train)
        sim = simulate(test, weights, mode="threshold")
        rec = {"train_end": str(returns.index[start - 1].date()),
               "weights": weights, **summary(sim.returns)}
        records.append(rec)
        start += step
    if not records:
        raise ValueError("not enough history for a single walk-forward window")
    return records


def run_and_report(con: sqlite3.Connection, mode: str = "threshold",
                   spliced: bool = True, tail: str = "TAIL") -> str:
    """Baseline sleeve backtest + mandatory statistics block + registered trial."""
    from ..ingest.series import returns_matrix
    from ..report.render import backtest_report
    from ..stats.dsr import moments, sharpe_ratio
    from ..stats.trials import register_trial, significance_block

    targets = resolve_targets(tail)
    mat = returns_matrix(con, list(targets.keys()), spliced=spliced)
    sim = simulate(mat, targets, mode=mode)
    stats = summary(sim.returns)
    mom = moments(sim.returns.values)
    sr = sharpe_ratio(sim.returns.values)

    cfg = {"targets": targets, "mode": mode, "spliced": spliced, "tail": tail,
           "backtest": load("backtest")}
    h = config_hash(cfg)
    register_trial(con, h, "backtest",
                   f"sleeve baseline mode={mode} tail={tail} spliced={spliced}",
                   sr, stats["n_days"], stats)
    sig = significance_block(con, sr, stats["n_days"], mom["skew"], mom["kurt"])

    provenance = "PROXY-EXTENDED history" if spliced else "live ETF history only"
    return backtest_report(
        title=f"B.5 Enhanced sleeve — {mode} rebalancing, tail={tail}",
        config_hash=h, provenance=provenance, stats=stats, sim=sim, sig=sig,
        pbo=None, pbo_note="single variant in this run — selection control is DSR vs cumulative trials",
    )
