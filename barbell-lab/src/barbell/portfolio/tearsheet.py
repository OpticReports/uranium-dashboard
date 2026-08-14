"""Fund-grade tearsheet — the "more than P&L" view.

Sections: headline stats, calendar-year returns, drawdown anatomy (top 5
episodes with dates and recovery), rolling 12m best/worst, correlation
matrix, per-asset risk contribution, and named crisis-episode stress table.
Works on the sleeve in isolation (bot_frac=0) or with the bot overlaid at
any fraction.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from ..config import config_hash, load
from ..backtest.engine import resolve_targets
from ..backtest.metrics import TRADING_DAYS, rolling_annual_returns, summary

# Named stress windows (verified market events; extend as history accrues).
CRISIS_EPISODES = [
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("COVID recovery", "2020-03-23", "2020-08-31"),
    ("2022 hiking cycle", "2022-01-03", "2022-10-12"),
    ("Aug-2024 vol spike", "2024-07-31", "2024-08-05"),
    ("Jan/Feb-2026 metals crash", "2026-01-28", "2026-02-06"),
]


def drawdown_table(returns: pd.Series, top: int = 5) -> list[dict]:
    """Top drawdown episodes with peak/trough/recovery dates."""
    wealth = (1 + returns).cumprod()
    peak = wealth.cummax()
    dd = wealth / peak - 1.0
    episodes, in_dd, start = [], False, None
    for dt, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, dt
        elif v == 0 and in_dd:
            seg = dd.loc[start:dt]
            episodes.append({"peak": start, "trough": seg.idxmin(),
                             "depth": float(seg.min()), "recovered": dt})
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        episodes.append({"peak": start, "trough": seg.idxmin(),
                         "depth": float(seg.min()), "recovered": None})
    return sorted(episodes, key=lambda e: e["depth"])[:top]


def risk_contributions(mat: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Fraction of portfolio variance contributed by each asset:
    RC_i = w_i (Σw)_i / (w'Σw). Sums to 1 by construction."""
    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers])
    cov = mat[tickers].cov().values
    port_var = float(w @ cov @ w)
    if port_var <= 0:
        raise ValueError("degenerate portfolio variance")
    rc = w * (cov @ w) / port_var
    return pd.Series(rc, index=tickers)


def build_tearsheet(con: sqlite3.Connection, tail: str = "TAIL",
                    bot_frac: float = 0.0, allow_bot_model: bool = False,
                    kill_switch: str = "perfect") -> str:
    from ..ingest.series import returns_matrix
    from ..report.render import research_report
    from .book import book_frame

    targets = resolve_targets(tail)
    mat = returns_matrix(con, list(targets.keys()), spliced=True).dropna()
    joint = book_frame(con, bot_frac, tail=tail, allow_bot_model=allow_bot_model,
                       kill_switch=kill_switch)
    series = joint["combined"]
    label = ("sleeve only" if bot_frac == 0
             else f"{1 - bot_frac:.0%} sleeve + {bot_frac:.0%} bot "
                  f"[{joint.attrs.get('bot_provenance', 'real')}]")
    s = summary(series)
    h = config_hash({"tearsheet": True, "tail": tail, "bot_frac": bot_frac})

    # calendar years
    by_year = series.groupby(series.index.year).apply(lambda g: float((1 + g).prod() - 1))
    year_rows = " | ".join(f"{y}: {r:+.1%}" for y, r in by_year.items())

    # rolling 12m extremes
    ann = rolling_annual_returns(series)
    roll_line = (f"best 12m {ann.max():+.1%} (ending {ann.idxmax():%Y-%m}), "
                 f"worst 12m {ann.min():+.1%} (ending {ann.idxmin():%Y-%m})"
                 if len(ann) else "n/a — under one year of joint history")

    # drawdowns
    dd_rows = [
        f"| {e['peak']:%Y-%m-%d} | {e['trough']:%Y-%m-%d} | {e['depth']:+.1%} "
        f"| {e['recovered']:%Y-%m-%d} |" if e["recovered"] is not None else
        f"| {e['peak']:%Y-%m-%d} | {e['trough']:%Y-%m-%d} | {e['depth']:+.1%} | ongoing |"
        for e in drawdown_table(series)
    ]

    # correlation matrix (sleeve constituents)
    corr = mat.corr()
    corr_head = "| | " + " | ".join(corr.columns) + " |"
    corr_sep = "|" + "---|" * (len(corr.columns) + 1)
    corr_rows = [f"| **{r}** | " + " | ".join(f"{corr.loc[r, c]:+.2f}" for c in corr.columns) + " |"
                 for r in corr.index]

    # risk contributions
    rc = risk_contributions(mat, targets).sort_values(ascending=False)
    rc_rows = [f"| {t} | {targets[t]:.1%} | {v:.1%} |" for t, v in rc.items()]

    # crisis episodes
    crisis_rows = []
    for name, a, b in CRISIS_EPISODES:
        a_ts, b_ts = pd.Timestamp(a), pd.Timestamp(b)
        if a_ts < series.index.min() or b_ts > series.index.max():
            crisis_rows.append(f"| {name} | {a} → {b} | n/a (outside joint history) |  |")
            continue
        seg = series.loc[a_ts:b_ts]
        spy = None
        try:
            from .. import db
            spy_px = db.read_prices(con, "SPY")["close_adj"]
            spy = float(spy_px.loc[:b].iloc[-1] / spy_px.loc[:a].iloc[-1] - 1)
        except Exception:  # noqa: BLE001
            pass
        crisis_rows.append(
            f"| {name} | {a} → {b} | {float((1 + seg).prod() - 1):+.2%} "
            f"| {spy:+.2%} |" if spy is not None else
            f"| {name} | {a} → {b} | {float((1 + seg).prod() - 1):+.2%} |  |")

    body = "\n".join([
        f"**Book: {label}** — {s['start']} → {s['end']} ({s['n_days']} days)",
        "",
        "| metric | value |", "|---|---|",
        f"| CAGR | {s['cagr']:+.2%} |",
        f"| ann. vol | {s['ann_vol']:.2%} |",
        f"| Sharpe (ann.) | {s['sharpe_annual']:.2f} |",
        f"| max drawdown | {s['max_drawdown']:+.2%} |",
        f"| CVaR5 (overlapping annual) | {s['cvar5_annual_overlapping']:+.2%} |"
        if s.get("cvar5_annual_overlapping") is not None else "| CVaR5 | n/a |",
        f"| worst day | {s['worst_day']:+.2%} |",
        "",
        f"**Calendar years:** {year_rows}",
        "",
        f"**Rolling 12m:** {roll_line}",
        "",
        "### Drawdown anatomy (top 5)",
        "", "| peak | trough | depth | recovered |", "|---|---|---|---|", *dd_rows, "",
        "### Sleeve correlation matrix (daily, full joint history)",
        "", corr_head, corr_sep, *corr_rows, "",
        "### Risk contribution (share of portfolio variance)",
        "", "| asset | weight | risk contribution |", "|---|---|---|", *rc_rows, "",
        "### Crisis episodes",
        "", "| episode | window | book return | SPY |", "|---|---|---|---|", *crisis_rows,
    ])
    return research_report("tearsheet", f"Tearsheet — {label}", body, h,
                           "proxy-extended history" + ("" if bot_frac == 0 else
                                                       f" + bot[{joint.attrs.get('bot_provenance', 'real')}]"),
                           "NO_CHANGE", "Descriptive analytics — no hypothesis tested; "
                           "no verdict beyond the numbers themselves.")
