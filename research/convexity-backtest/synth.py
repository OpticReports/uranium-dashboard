"""
Synthetic reconstruction of leveraged / volatility ETFs from underlying indices.

The whole point of the harness: Composer can only backtest to the ETF inception
(~2021 for the vol sleeve). To validate a strategy across more regimes we rebuild
each holding as a DAILY synthetic series from the index it tracks, modelling the
ETF's real mechanics -- because leveraged/vol products are dominated by daily
reset, volatility drag, fees and financing, none of which survive a naive
"multiply the cumulative index return by L" shortcut.

Two tiers of trust, kept strictly separate:

  TIER 1  DATA-GROUNDED   reconstruct from a real index (e.g. TQQQ = 3x NDX).
                          Defensible back to the index inception (NDX -> 1986).
  TIER 2  MODELLED        vol-futures ETF from VIX *spot* + a contango/roll model,
                          because real VIX futures / SPVXSTR are unavailable here.
                          This is ILLUSTRATIVE scenario analysis, NOT validation.

Every function documents its assumptions and every assumption is a parameter, so
the watchdog can sweep them and show whether a result depends on a soft input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def index_returns(level: pd.Series) -> pd.Series:
    """Daily simple returns from an index level series (NaNs dropped)."""
    return level.dropna().pct_change().dropna()


def reconstruct_leveraged_etf(
    idx_ret: pd.Series,
    leverage: float,
    expense_ratio: float,
    financing_rate: pd.Series,
    borrow_spread: float = 0.004,
    div_yield: float = 0.0,
    trading_days: int = 252,
) -> pd.Series:
    """
    TIER 1. Daily-reset leveraged ETF total return, reconstructed from index returns.

        r_etf(t) = L*(r_idx(t) + div/td)                      # levered index total return
                   - expense/td                               # management fee drag
                   - (L-1)*(rate(t)/100 + spread)/td          # financing on borrowed leg

    Notes / honest assumptions:
      * `div_yield` adds back the dividends the FRED PRICE index omits (annual, /td).
      * financing accrues on the borrowed portion (L-1) at the short rate + a swap
        `borrow_spread`. Both are parameters so the watchdog can stress them.
      * daily compounding is preserved -> volatility drag emerges naturally.
    """
    rate = financing_rate.reindex(idx_ret.index).ffill() / 100.0
    daily = (
        leverage * (idx_ret + div_yield / trading_days)
        - expense_ratio / trading_days
        - (leverage - 1.0) * (rate + borrow_spread) / trading_days
    )
    return daily.rename(f"synthetic_{leverage:g}x")


def modelled_short_vol_futures(
    vix_spot: pd.Series,
    daily_roll_drag: float = 0.0016,
    beta_to_spot: float = 0.45,
    trading_days: int = 252,
) -> pd.Series:
    """
    TIER 2 -- ILLUSTRATIVE ONLY. A crude stand-in for the S&P short-term VIX
    futures index (SPVXSTR) that UVXY/VIXY track, built from VIX *spot* because
    real futures are not available in this environment.

    Model: front-month VIX futures move a fraction `beta_to_spot` of spot VIX
    daily changes (futures are less volatile than spot), minus a persistent
    `daily_roll_drag` for rolling up a contango term structure (~0.16%/day is a
    rough long-run average and is itself regime dependent).

    This captures the SHAPE of long-vol behaviour (large crash spikes, chronic
    bleed in calm markets) but the magnitudes are model artefacts. DO NOT quote
    any number derived from this as validation -- it exists to demonstrate the
    machinery and to be replaced the moment real futures data is wired in.
    """
    v = vix_spot.dropna()
    spot_ret = v.pct_change()
    fut_ret = beta_to_spot * spot_ret - daily_roll_drag
    return fut_ret.dropna().rename("modelled_stvix_futures")


def compound(daily_ret: pd.Series, start: float = 100.0) -> pd.Series:
    """Compound a daily return series into a price curve."""
    return start * (1.0 + daily_ret).cumprod()


# Era-correct leverage for products whose multiplier changed. UVXY was 2x through
# 2018-02-27 and 1.5x afterward -- getting this wrong invalidates any vol result.
UVXY_LEVERAGE_SCHEDULE = [
    ("1900-01-01", "2018-02-27", 2.0),
    ("2018-02-28", "2100-01-01", 1.5),
]


def apply_leverage_schedule(idx_ret: pd.Series, schedule) -> pd.Series:
    """Return a per-date leverage Series from (start, end, L) windows."""
    lev = pd.Series(np.nan, index=idx_ret.index)
    for start, end, L in schedule:
        mask = (idx_ret.index >= pd.Timestamp(start)) & (idx_ret.index <= pd.Timestamp(end))
        lev[mask] = L
    return lev.ffill().bfill()
