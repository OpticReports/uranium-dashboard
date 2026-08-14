"""Combined-book simulator: 80% defensive sleeve + 20% short-vol bot.

Bot return sources, in order of preference:
  1. REAL P&L from the bot's SQLite (bot_pnl table), converted to returns on
     the configured capital base. This is always preferred.
  2. A PARAMETERIZED model (config: portfolio.yaml bot_model) — ONLY when the
     caller explicitly allows it (--bot-model). The model: positive carry in
     benign states; a -20%..-30% month in VIX-spike months (losses placed on
     the days VIX rises); kill-switch flattens exposure on VIX term-structure
     backwardation days, in one of three modes:
        perfect — flat ON the backwardation day
        lag1    — flat starting the NEXT day (signal acted on late)
        fails   — kill-switch never fires; full spike losses taken
     Kill-switch behavior is a config/CLI parameter, never hardcoded.

Every series returned is tagged with provenance so reports can state exactly
what mixture of real/model data produced each number.
"""
from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd

from .. import db
from ..config import load

logger = logging.getLogger(__name__)


class BotDataError(RuntimeError):
    pass


def real_bot_returns(con: sqlite3.Connection) -> pd.Series:
    bot_cfg = load("data")["bot"]
    cap = bot_cfg.get("capital_base")
    df = pd.read_sql_query("SELECT date, realized, unrealized FROM bot_pnl ORDER BY date",
                           con, parse_dates=["date"]).set_index("date")
    if df.empty:
        raise BotDataError("bot_pnl table is empty — run `barbell import-bot` first")
    if not cap:
        raise BotDataError(
            "bot.capital_base is not set in config/data.yaml — cannot convert "
            "P&L dollars to returns. Refusing to guess."
        )
    # Convention (CONFIRM against bot schema): realized is the day's realized
    # P&L flow and unrealized is the day's mark-to-market CHANGE.
    pnl = df["realized"].fillna(0.0) + df["unrealized"].fillna(0.0)
    return (pnl / float(cap)).rename("bot")


def _vix_frames(con: sqlite3.Connection) -> pd.DataFrame:
    vix = db.read_prices(con, "^VIX")["close_raw"].rename("vix")
    vix3m = db.read_prices(con, "^VIX3M")["close_raw"].rename("vix3m")
    out = pd.concat([vix, vix3m], axis=1, sort=True).dropna()
    if out.empty:
        raise BotDataError("no ^VIX/^VIX3M data — run `barbell ingest`")
    return out


def model_bot_returns(con: sqlite3.Connection, kill_switch: str = "perfect") -> pd.Series:
    if kill_switch not in ("perfect", "lag1", "fails"):
        raise ValueError(f"unknown kill_switch mode {kill_switch}")
    m = load("portfolio")["bot_model"]
    carry_daily = float(m["carry_annual"]) / 252.0
    spike_ret = float(m["spike_month_return"])
    thr = float(m["vix_spike_threshold"])
    rise = float(m["vix_spike_month_rise"])

    v = _vix_frames(con)
    ret = pd.Series(carry_daily, index=v.index, name="bot")

    # spike months: VIX breaches threshold AND rose materially within the month
    by_month = v["vix"].groupby(v.index.to_period("M"))
    spike_months = {
        p for p, g in by_month
        if g.max() >= thr and g.max() / g.iloc[0] >= rise
    }
    backwardation = v["vix"] > v["vix3m"]
    flat = pd.Series(False, index=v.index)
    if kill_switch == "perfect":
        flat = backwardation
    elif kill_switch == "lag1":
        flat = backwardation.shift(1, fill_value=False)

    for p in spike_months:
        days = v.index[v.index.to_period("M") == p]
        dv = v.loc[days, "vix"].diff().clip(lower=0.0)
        wts = dv / dv.sum() if dv.sum() > 0 else pd.Series(1 / len(days), index=days)
        # distribute the spike-month loss over rising-VIX days, log-space so
        # the days compound exactly to spike_ret
        log_total = np.log1p(spike_ret)
        ret.loc[days] = np.expm1(log_total * wts)
    ret[flat] = 0.0
    return ret


def bot_return_series(con: sqlite3.Connection, allow_model: bool,
                      kill_switch: str = "perfect") -> pd.Series:
    """Real bot returns, model-extended only if explicitly allowed."""
    try:
        real = real_bot_returns(con)
    except BotDataError as exc:
        if not allow_model:
            raise
        logger.warning("USING PARAMETERIZED BOT MODEL (%s) — no real P&L: %s",
                       kill_switch, exc)
        s = model_bot_returns(con, kill_switch)
        s.attrs["provenance"] = f"model:{kill_switch}"
        return s
    if allow_model:
        model = model_bot_returns(con, kill_switch)
        pre = model[model.index < real.index.min()]
        if len(pre):
            s = pd.concat([pre, real]).sort_index()
            s.attrs["provenance"] = (f"real {real.index.min():%Y-%m-%d}→ + "
                                     f"model:{kill_switch} before")
            return s
    real.attrs["provenance"] = "real"
    return real


def combined_returns(sleeve: pd.Series, bot: pd.Series,
                     sleeve_frac: float = 0.80) -> pd.DataFrame:
    """Joint daily frame on the common calendar. Bot days with no sleeve data
    (or vice versa) are dropped — never zero-filled."""
    joint = pd.concat([sleeve.rename("sleeve"), bot.rename("bot")], axis=1, sort=True).dropna()
    if len(joint) < 250:
        raise BotDataError(f"only {len(joint)} joint sleeve/bot days — not enough to simulate")
    joint["combined"] = sleeve_frac * joint["sleeve"] + (1 - sleeve_frac) * joint["bot"]
    return joint
