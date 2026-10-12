"""B.5 Enhanced sleeve vs SPY — trailing 12 months, total return.

Uses the platform's own machinery so the number means what every other
barbell-lab number means:
  * prices: Yahoo adjclose (split + dividend adjusted) via the platform adapter,
    every ticker cross-checked against FMP's dividend-adjusted feed (fetch.py);
  * weights: config/portfolio.yaml targets resolved by engine.resolve_targets
    (the register's v1.0 seed; tail sleeve = tail_sleeve.current);
  * path: engine.simulate() — holdings drift daily, ±20% relative bands checked
    at month-end, every trade (incl. the initial buy) pays per-ticker costs.
Window: buy at the 2025-10-09 close, mark at the 2026-10-09 close (the last
complete session; 2026-10-12 was intraday when this ran).

usage: python -I b5_vs_spy_12m.py <dir with prices.parquet> <out results.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from barbell.backtest.engine import resolve_targets, simulate
from barbell.backtest.metrics import TRADING_DAYS

T0, T1 = "2025-10-09", "2026-10-09"          # buy close -> mark close
ALT_T0, ALT_T1 = "2025-09-30", "2026-09-30"  # month-end TTM (window sensitivity)
SRC = "yahoo"

# Older "B.5 Enhanced" table on thesis-deployment.html / methodology.html
# (pre-barbell-lab). CASH proxied by BIL.
THESIS_PAGE = {"AVUV": .23, "PHYS": .18, "AVDV": .16, "KMLM": .14, "AVEM": .13,
               "MTUM": .08, "QUAL": .05, "BIL": .03}


def window_returns(px: pd.DataFrame, t0: str, t1: str, src: str = SRC) -> pd.DataFrame:
    p = px[src].loc[t0:t1]
    if p.index[0] != pd.Timestamp(t0) or p.index[-1] != pd.Timestamp(t1):
        raise ValueError(f"window endpoints not trading days in data: {p.index[0]} {p.index[-1]}")
    if p.isna().any().any():
        raise ValueError("NaN prices inside window")
    return p.pct_change().iloc[1:]          # first return = day after the buy close


def replay_weights(r: pd.DataFrame, targets: dict, band: float = 0.20) -> pd.DataFrame:
    """Zero-cost replay of engine.simulate(threshold) that also records each
    day's PRE-return weights (the engine only keeps month-end weights). Used
    for attribution only; asserted equal to the engine's zero-cost path."""
    tk = list(targets)
    wt = np.array([targets[t] for t in tk])
    rr = r[tk]
    month_ends = set(rr.groupby(rr.index.to_period("M")).apply(lambda g: g.index.max()))
    h = wt.copy()
    pre, port = [], []
    for dt, row in zip(rr.index, rr.values):
        w = h / h.sum()
        pre.append(w)
        h = h * (1 + row)
        port.append(float(w @ row))
        if dt in month_ends and (np.abs((h / h.sum()) / wt - 1) > band).any():
            h = wt * h.sum()
    out = pd.DataFrame(pre, index=rr.index, columns=tk)
    out["_port"] = port
    return out


def carino(pre: pd.DataFrame, r: pd.DataFrame) -> dict:
    """Carino-linked contributions: sum exactly to the geometric total return."""
    tk = [c for c in pre.columns if c != "_port"]
    Rt = pre["_port"]
    R = float((1 + Rt).prod() - 1)
    k = np.where(np.abs(Rt) > 1e-12, np.log1p(Rt) / Rt, 1.0)
    K = np.log1p(R) / R
    contrib = {t: float(((k / K) * pre[t] * r[t]).sum()) for t in tk}
    assert abs(sum(contrib.values()) - R) < 1e-10, "Carino contributions do not sum to total"
    return contrib


def stats(ret: pd.Series, spy: pd.Series, rf: pd.Series) -> dict:
    wealth = pd.concat([pd.Series([1.0], index=[ret.index[0] - pd.Timedelta(days=1)]),
                        (1 + ret).cumprod()])          # include the t0 base as a peak
    dd = wealth / wealth.cummax() - 1
    trough = dd.idxmin()
    peak = wealth.loc[:trough].idxmax()
    ex = ret - rf
    m = (1 + ret).groupby(ret.index.to_period("M")).prod() - 1
    ms = (1 + spy).groupby(spy.index.to_period("M")).prod() - 1
    up, dn = ms > 0, ms < 0
    cov = np.cov(ret, spy, ddof=1)
    return {
        "total_return": float(wealth.iloc[-1] - 1),
        "ann_vol": float(ret.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "sharpe_ex_bil": float(ex.mean() / ex.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "max_drawdown": float(dd.min()),
        "mdd_peak": str(peak.date()), "mdd_trough": str(trough.date()),
        "beta_to_spy_daily": float(cov[0, 1] / cov[1, 1]),
        "corr_to_spy_daily": float(np.corrcoef(ret, spy)[0, 1]),
        "worst_day": float(ret.min()), "worst_day_date": str(ret.idxmin().date()),
        "best_month": float(m.max()), "worst_month": float(m.min()),
        "up_capture_monthly": float((1 + m[up]).prod() ** (1 / up.sum()) - 1) /
                              float((1 + ms[up]).prod() ** (1 / up.sum()) - 1) if up.any() else None,
        "down_capture_monthly": float((1 + m[dn]).prod() ** (1 / dn.sum()) - 1) /
                                float((1 + ms[dn]).prod() ** (1 / dn.sum()) - 1) if dn.any() else None,
        "months_beating_spy": f"{int((m > ms).sum())}/{len(m)}",
        "monthly": {str(k): float(v) for k, v in m.items()},
    }


def run(px: pd.DataFrame, t0: str, t1: str, src: str = SRC) -> dict:
    r = window_returns(px, t0, t1, src)
    spy_sim = simulate(r, {"SPY": 1.0}, mode="none")       # pays SPY's 1bp entry cost
    spy, rf = spy_sim.returns, r["BIL"]
    variants = {
        "B5_v1.0_TAIL_bands": (resolve_targets("TAIL"), "threshold"),
        "B5_v1.0_TAIL_buyhold": (resolve_targets("TAIL"), "none"),
        "B5_tail_NONE_bands": (resolve_targets("NONE"), "threshold"),
        "B5_thesis_page_bands": (THESIS_PAGE, "threshold"),
    }
    out = {"window": {"buy_close": t0, "mark_close": t1, "n_return_days": len(r), "price_source": src},
           "SPY": stats(spy, spy, rf),
           "per_ticker_total_return": {t: float((1 + r[t]).prod() - 1) for t in r.columns}}
    for name, (tg, mode) in variants.items():
        sim = simulate(r, tg, mode=mode)
        s = stats(sim.returns, spy, rf)
        s.update(targets=tg, mode=mode, n_rebalances=sim.n_rebalances,
                 cost_drag_bp=float(sim.cost_drag_annual * 1e4),
                 excess_vs_spy=s["total_return"] - out["SPY"]["total_return"])
        if mode == "threshold":
            pre = replay_weights(r, tg)
            free = simulate(r, tg, mode=mode, zero_cost_internal=True).returns
            gap = float((pre["_port"] - free).abs().max())
            assert gap < 1e-12, f"replay diverges from engine by {gap}"
            s["attribution_pp_zero_cost"] = {t: v * 100 for t, v in carino(pre, r[list(tg)]).items()}
            s["rebalance_dates"] = [str(d.date()) for d in pre.index
                                    if d in set(sim.weights_path.index)
                                    and (np.abs(sim.weights_path.loc[d].values /
                                                np.array([tg[t] for t in sim.weights_path.columns]) - 1) > 0.20).any()]
            s["month_end_weights"] = {str(d.date()): {t: round(float(v), 4) for t, v in row.items()}
                                      for d, row in sim.weights_path.iterrows()}
        s["daily_returns"] = {str(d.date()): float(v) for d, v in sim.returns.items()}
        out[name] = s
    out["SPY"]["daily_returns"] = {str(d.date()): float(v) for d, v in spy.items()}
    return out


if __name__ == "__main__":
    px = pd.read_parquet(Path(sys.argv[1]) / "prices.parquet")
    res = {"primary": run(px, T0, T1),
           "window_sensitivity_month_end": run(px, ALT_T0, ALT_T1),
           "provider_sensitivity_fmp": run(px, T0, T1, src="fmp")}
    for k in ("window_sensitivity_month_end", "provider_sensitivity_fmp"):   # keep the file small
        for v in res[k].values():
            if isinstance(v, dict):
                for drop in ("daily_returns", "month_end_weights", "monthly"):
                    v.pop(drop, None)
    Path(sys.argv[2]).write_text(json.dumps(res, indent=1))
    p = res["primary"]
    print("window", p["window"])
    fmt = lambda d: (f"TR {d['total_return']:+.2%} vol {d['ann_vol']:.1%} SR {d['sharpe_ex_bil']:.2f} "
                     f"MDD {d['max_drawdown']:.1%} ({d['mdd_peak']}->{d['mdd_trough']}) beta {d['beta_to_spy_daily']:.2f} "
                     f"corr {d['corr_to_spy_daily']:.2f} beat {d['months_beating_spy']}")
    print("SPY                 ", fmt(p["SPY"]))
    for k in [k for k in p if k.startswith("B5")]:
        d = p[k]
        print(f"{k:20s}", fmt(d), f"| xs {d['excess_vs_spy']:+.2%} reb {d['n_rebalances']} cost {d['cost_drag_bp']:.1f}bp",
              f"| up/down cap {d['up_capture_monthly']:.2f}/{d['down_capture_monthly']:.2f}")
    print("attribution pp (zero-cost):", {t: round(v, 2) for t, v in p["B5_v1.0_TAIL_bands"]["attribution_pp_zero_cost"].items()})
    print("rebalance dates:", p["B5_v1.0_TAIL_bands"]["rebalance_dates"])
    for k in ("window_sensitivity_month_end", "provider_sensitivity_fmp"):
        q = res[k]
        print(k, "SPY", f"{q['SPY']['total_return']:+.2%}", " ".join(f"{n}:{q[n]['total_return']:+.2%}" for n in q if n.startswith("B5")))
    print("monthly B5 vs SPY:")
    for mth in p["SPY"]["monthly"]:
        print(" ", mth, f"{p['B5_v1.0_TAIL_bands']['monthly'][mth]:+.2%}", f"{p['SPY']['monthly'][mth]:+.2%}")
