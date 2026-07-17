"""The BOOK, decoupled from the fixed 80/20 frame.

* sleeve-only view (bot_frac=0): the defensive sleeve analyzed in isolation
* bot overlay at ANY fraction: `bot_frac` is a free parameter
* fraction sweep: map the whole sleeve/bot frontier — geometric growth vs
  joint tail risk under the hard constraints — and report the growth-optimal
  admissible fraction instead of assuming 20%.

Every sweep variant evaluated registers a trial (selection is selection).
"""
from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd

from ..config import config_hash, load
from ..backtest.engine import resolve_targets
from ..backtest.metrics import summary
from ..report.render import research_report
from ..stats.trials import register_trial
from .combined import bot_return_series, combined_returns
from .simulate import bootstrap_paths, path_metrics

logger = logging.getLogger(__name__)


def book_frame(con: sqlite3.Connection, bot_frac: float, tail: str = "TAIL",
               allow_bot_model: bool = False, kill_switch: str = "perfect") -> pd.DataFrame:
    """Daily frame with sleeve, bot (if bot_frac>0) and combined columns."""
    if not 0.0 <= bot_frac < 1.0:
        raise ValueError("bot_frac must be in [0, 1)")
    from .questions import _sleeve_daily
    sleeve = _sleeve_daily(con, tail)
    if bot_frac == 0.0:
        df = sleeve.rename("sleeve").to_frame()
        df["combined"] = df["sleeve"]
        return df
    bot = bot_return_series(con, allow_model=allow_bot_model, kill_switch=kill_switch)
    joint = combined_returns(sleeve, bot, sleeve_frac=1.0 - bot_frac)
    joint.attrs["bot_provenance"] = bot.attrs.get("provenance", "real")
    return joint


def evaluate_fraction(joint: pd.DataFrame, bot_frac: float, n_paths: int,
                      block_len: int, seed: int) -> dict:
    """MC metrics of the book at one sleeve/bot split (1y + 10y horizons)."""
    if bot_frac == 0.0:
        cols, w = ["sleeve"], np.array([1.0])
    else:
        cols, w = ["sleeve", "bot"], np.array([1.0 - bot_frac, bot_frac])
    p1 = bootstrap_paths(joint[cols], w, n_paths, 1, block_len, seed=seed)
    m1 = path_metrics(p1)
    p10 = bootstrap_paths(joint[cols], w, max(2000, n_paths // 10), 10,
                          block_len, seed=seed + 1)
    m10 = path_metrics(p10)
    hist = summary(joint[cols] @ w if len(cols) > 1 else joint["sleeve"])
    return {
        "bot_frac": bot_frac,
        "p5_1y": float(np.percentile(p1["annual_returns"], 5)),
        "median_1y": float(np.median(p1["annual_returns"])),
        "cvar5_annual": m1["cvar5_annual"],
        "maxdd_p5_1y": m1["maxdd_p5"],
        "cagr_median_10y": m10["cagr_median"],
        "cagr_p5_10y": m10["cagr_p5"],
        "terminal_p5_10y": m10["terminal_p5"],
        "hist_cagr": hist["cagr"],
        "hist_maxdd": hist["max_drawdown"],
    }


def sweep_bot_fraction(con: sqlite3.Connection, fracs: list[float] | None = None,
                       tail: str = "TAIL", allow_bot_model: bool = False,
                       kill_switch: str = "perfect", n_paths: int = 20000) -> str:
    mc = load("backtest")["monte_carlo"]
    cons = load("portfolio")["constraints"]
    fracs = fracs if fracs is not None else [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    if any(not 0 <= f < 1 for f in fracs):
        raise ValueError("fractions must be in [0, 1)")
    # one joint frame with bot column present (need a bot series unless all-zero sweep)
    need_bot = any(f > 0 for f in fracs)
    joint = book_frame(con, bot_frac=max(fracs) if need_bot else 0.0, tail=tail,
                       allow_bot_model=allow_bot_model, kill_switch=kill_switch)
    prov = joint.attrs.get("bot_provenance", "none")
    h = config_hash({"sweep": fracs, "tail": tail, "ks": kill_switch, "n_paths": n_paths})

    rows = []
    for f in fracs:
        r = evaluate_fraction(joint, f, n_paths, int(mc["block_len_days"]), int(mc["seed"]))
        # hard-constraint admissibility (CVaR + drawdown; correlation constrains
        # sleeve construction, not the split)
        r["admissible"] = (r["cvar5_annual"] >= float(cons["cvar_5_annual_min"])
                           and r["maxdd_p5_1y"] >= float(cons["p5_max_drawdown_min"]))
        rows.append(r)
        register_trial(con, h, "book_sweep", f"bot_frac={f:.2f} ks={kill_switch}",
                       None, len(joint), r)

    admissible = [r for r in rows if r["admissible"]]
    best = max(admissible, key=lambda r: r["cagr_median_10y"]) if admissible else None
    body = [
        f"Sleeve tail={tail}; bot stream: **{prov}**; kill-switch={kill_switch}; "
        f"joint window {joint.index.min():%Y-%m-%d} → {joint.index.max():%Y-%m-%d} "
        f"({len(joint)} days); {n_paths} bootstrap paths (1y), "
        f"{max(2000, n_paths // 10)} (10y).",
        "",
        "| bot % | p5 1y | median 1y | CVaR5 | p5 maxDD 1y | 10y CAGR p50 | 10y CAGR p5 "
        "| hist CAGR | hist maxDD | admissible |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {r['bot_frac']:.0%} | {r['p5_1y']:+.2%} | {r['median_1y']:+.2%} "
          f"| {r['cvar5_annual']:+.2%} | {r['maxdd_p5_1y']:+.2%} "
          f"| {r['cagr_median_10y']:+.2%} | {r['cagr_p5_10y']:+.2%} "
          f"| {r['hist_cagr']:+.2%} | {r['hist_maxdd']:+.2%} "
          f"| {'YES' if r['admissible'] else '**NO**'} |" for r in rows],
        "",
    ]
    if best is None:
        verdict, basis = "INCONCLUSIVE", ("NO fraction in the sweep satisfies the hard "
                                          "constraints — the book design itself needs revisiting.")
    else:
        baseline = next((r for r in rows if abs(r["bot_frac"] - 0.20) < 1e-9), None)
        body.append(f"**Growth-optimal admissible fraction: {best['bot_frac']:.0%}** "
                    f"(10y median CAGR {best['cagr_median_10y']:+.2%}, "
                    f"CVaR5 {best['cvar5_annual']:+.2%})")
        if baseline is not None and abs(best["bot_frac"] - 0.20) > 1e-9:
            edge = best["cagr_median_10y"] - baseline["cagr_median_10y"]
            verdict = "IMPROVED" if edge > 0.005 else "NO_CHANGE"
            basis = (f"{best['bot_frac']:.0%} bot beats the 20% baseline by "
                     f"{edge:+.2%}/yr (10y median) within constraints."
                     if verdict == "IMPROVED" else
                     f"Optimal fraction {best['bot_frac']:.0%} is within noise of the "
                     f"20% baseline ({edge:+.2%}/yr) — keep 80/20.")
        else:
            verdict, basis = "NO_CHANGE", "The 20% baseline is the growth-optimal admissible split."
    if prov.startswith("model"):
        basis += " CAVEAT: bot stream is the PARAMETERIZED MODEL — rerun with real P&L."
    return research_report("book-sweep", "Sleeve/bot fraction sweep (80/20 challenged)",
                           "\n".join(body), h, f"sleeve[proxy-extended] + bot[{prov}]",
                           verdict, basis)
