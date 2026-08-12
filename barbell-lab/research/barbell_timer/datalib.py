"""Shared frozen-fixture loaders + return conventions for BARBELL-TIMER.

Reads ONLY research/barbell_timer/fixtures/ (never the network).
All conventions centralized here so replication.py and baselines.py cannot
drift apart:

- Prices are NEVER forward-filled; rates (yields) ARE forward-filled onto
  trading calendars (standard for yields; flagged in PROVENANCE.md).
- GCUSD trades weekends/holidays; when aligned to an equity calendar its
  return between two equity closes compounds every intervening futures
  session (no data dropped).
- Bill returns from a discount-style annual yield y%: per-period return
  (1+y/100)^(dt_years) - 1 with ACT/365 day count. Simple, stated, and the
  error vs exact bank-discount math is <1bp/yr at these rate levels.
- Month-end = last trading day of the calendar month on the relevant series.
"""
import json
import os

import numpy as np
import pandas as pd

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# ---- documented gold lease-rate schedule (%/yr), used to convert spot gold
# returns into gold-FUTURES-EXCESS returns: fut_excess = spot - (bills - lease).
# Basis column is printed in every consumer. Pre-2007 values are literature
# assumptions (central-bank lending era, 3M lease commonly 1-2% in the 80s/90s
# with 1999 spikes; near zero after 2010). 2007+ anchored to REALIZED carry
# measured from DGL-vs-GLD (see replication.py section 3) and 2022+ additionally
# cross-checked against actual GDE.
LEASE_SCHEDULE = [
    # (start_year_inclusive, lease %/yr, basis)
    (1975, 1.00, "assumed (literature: nascent lending market)"),
    (1980, 1.50, "assumed (literature: CB-lending / carry-trade era)"),
    (1990, 1.50, "assumed (literature: 3M lease 1-2%, 1999 spikes)"),
    (2000, 0.75, "assumed pre-2007 / realized via DGL-GLD 2007-09"),
    (2010, 0.25, "realized via DGL-GLD (near zero, sometimes negative)"),
    (2020, 0.50, "realized via DGL-GLD 2020-23 + GDE-implied 2022-26"),
]

# ---- POST-MEASUREMENT revision (Phase 0 finding, applied by baselines.py):
# the realized instruments say the financialized era (2007->) carries an
# EFFECTIVE lease of about -0.4%/yr for a GDE-class fund (GDE NAV 2022-26
# measures -0.41%; DGL-GLD realizes -1.1..-3.3% but includes DGL-specific
# frictions and is treated as an upper bound on drag). baselines.py therefore
# uses: schedule above for 1975-2006 (literature era, positive lease — weakest
# link, pessimistic sensitivity variant reported), and effective lease
# EFFECTIVE_LEASE_2007ON for 2007-onward. The a-priori schedule is kept intact
# above so the validation gate shows what was assumed BEFORE measurement.
EFFECTIVE_LEASE_2007ON = -0.40  # %/yr, GDE-anchored, documented amendment A3

GDE_FEE = 0.0020        # 20 bp/yr expense ratio per brief
ROLL_COST = 0.0005      # 5 bp/yr assumed futures roll/transaction friction
                        # (6 rolls/yr x ~1bp calendar-spread cost, ETF scale);
                        # sensitivity 0-10bp reported in replication.py


def _fmp(name, col):
    d = json.load(open(os.path.join(FIX, name)))["rows"]
    s = pd.Series({r["date"]: r[col] for r in d}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _fred(name):
    d = json.load(open(os.path.join(FIX, name)))["rows"]
    s = pd.Series({r[0]: r[1] for r in d}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_daily():
    """All daily series, raw calendars."""
    return {
        "gde": _fmp("fmp_gde_dividend_adjusted.json", "adjClose"),
        "gde_raw": _fmp("fmp_gde_full.json", "close"),
        "spy": _fmp("fmp_spy_dividend_adjusted.json", "adjClose"),
        "gld": _fmp("fmp_gld_dividend_adjusted.json", "adjClose"),
        "dgl": _fmp("fmp_dgl_dividend_adjusted.json", "adjClose"),
        "boxx": _fmp("fmp_boxx_dividend_adjusted.json", "adjClose"),
        "gc": _fmp("fmp_gcusd_light.json", "price"),
        "gspc": _fmp("fmp_gspc_light.json", "price"),
        "dtb3": _fred("fred_dtb3.json"),
    }


def load_monthly_raw():
    j = json.load(open(os.path.join(FIX, "longhist_shiller_spx.json")))
    sh_px = pd.Series({k: v for k, v in j["px"]}, dtype=float)
    sh_div = pd.Series({k: v for k, v in j["div"]}, dtype=float)
    g = json.load(open(os.path.join(FIX, "longhist_gold_monthly.json")))["rows"]
    gold_m = pd.Series({k: v for k, v in g}, dtype=float)
    tb3 = _fred("fred_tb3ms.json")
    tb3.index = tb3.index.to_period("M").astype(str)
    for s in (sh_px, sh_div, gold_m):
        pass  # keyed by 'YYYY-MM' strings already
    return sh_px, sh_div, gold_m, tb3


def align_returns_to(calendar_px, other_px):
    """Return of `other_px` between consecutive dates of `calendar_px`'s index,
    compounding any intervening sessions of `other_px` (used for GCUSD ->
    NYSE-calendar alignment). Result indexed like calendar_px (minus first)."""
    cal = calendar_px.index
    snapped = other_px.reindex(other_px.index.union(cal)).ffill().reindex(cal)
    return snapped.pct_change().dropna()


def bill_daily_returns(calendar_index, dtb3):
    """Bill return accrued between consecutive calendar dates from the ffilled
    DTB3 yield in effect at the START of the gap (no lookahead)."""
    y = dtb3.reindex(dtb3.index.union(calendar_index)).ffill().reindex(calendar_index)
    dt_years = calendar_index.to_series().diff().dt.days / 365.0
    r = (1.0 + y.shift(1) / 100.0) ** dt_years - 1.0
    return r.dropna()


def lease_rate_for(ts):
    lease = LEASE_SCHEDULE[0][1]
    for y0, val, _ in LEASE_SCHEDULE:
        if ts.year >= y0:
            lease = val
    return lease


def lease_series(index):
    return pd.Series([lease_rate_for(t) for t in index], index=index)


# ---------------- stats conventions (stated once, used everywhere) ----------
def ann_return(cum_first, cum_last, years):
    return (cum_last / cum_first) ** (1.0 / years) - 1.0


def perf_stats(ret_m, rf_m, freq=12):
    """Monthly-return stat block. Conventions:
    - CAGR: geometric, from compounded monthly returns.
    - Vol: std of monthly returns (ddof=1) * sqrt(12).
    - Sharpe: mean ARITHMETIC monthly excess over bills * 12 / (std of monthly
      EXCESS returns * sqrt(12)). Excess-return std, not raw std.
    - Sortino: MAR = bills (rf). Downside deviation = sqrt(mean over ALL months
      of min(0, r - rf)^2) * sqrt(12) (full-sample denominator convention).
      Numerator = annualized arithmetic mean excess.
    - maxDD / underwater / Calmar / Ulcer: on the MONTHLY equity curve
      (month-end closes) -> intramonth-blind, flagged by callers.
    - Ulcer index: sqrt(mean(drawdown_pct^2)), drawdown in % units.
    - Worst 12m: minimum rolling 12-month compounded return.
    - %positive: fraction of months with r > 0.
    """
    r = ret_m.dropna()
    rf = rf_m.reindex(r.index)
    ex = r - rf
    n = len(r)
    yrs = n / freq
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std(ddof=1) * np.sqrt(freq)
    sharpe = (ex.mean() * freq) / (ex.std(ddof=1) * np.sqrt(freq))
    dd_dev = np.sqrt((np.minimum(ex, 0.0) ** 2).mean()) * np.sqrt(freq)
    sortino = (ex.mean() * freq) / dd_dev if dd_dev > 0 else np.nan
    peak = eq.cummax()
    dd = eq / peak - 1
    maxdd = dd.min()
    # longest underwater: max run of months below prior peak
    uw, longest, cur = dd < -1e-12, 0, 0
    for flag in uw:
        cur = cur + 1 if flag else 0
        longest = max(longest, cur)
    calmar = cagr / abs(maxdd) if maxdd < 0 else np.nan
    ulcer = np.sqrt(((dd * 100) ** 2).mean())
    r12 = (1 + r).rolling(12).apply(np.prod, raw=True) - 1
    worst12 = r12.min()
    return {
        "months": n, "CAGR": cagr, "Vol": vol, "Sharpe": sharpe,
        "Sortino": sortino, "MaxDD_m": maxdd, "UnderwaterMax_m": longest,
        "Calmar": calmar, "Ulcer": ulcer, "Worst12m": worst12,
        "PctPos": (r > 0).mean(),
    }
