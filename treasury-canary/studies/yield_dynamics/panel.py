"""Month-end panel for studies/yield-dynamics-forward-spx.md.

Everything here is known at the origin's close: yields and the S&P are the
LAST trading day of each calendar month; CPI is lagged one month for its
publication delay. Forward returns are built by `outcomes()` and are kept
separate so the feature panel can be inspected without looking at them.

Data: keyless FRED CSV + Yahoo ^GSPC daily JSON, frozen in ./data/
(fetch commands in the spec). Needs numpy + pandas only.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
START = "1971-01"          # first origin
SPLICE = ("1987-01-01", "1993-09-30")   # DGS20 missing; filled from DGS30
SEAM = ("1986-01-01", "1986-12-31")     # sets the splice offset — known in real time (spec A4)


def fred_daily(sid: str) -> pd.Series:
    df = pd.read_csv(os.path.join(DATA, f"{sid}.csv"), na_values=".")
    df.columns = ["date", sid]
    s = df.set_index(pd.to_datetime(df["date"]))[sid].dropna()
    return s.astype(float)


def gspc_daily() -> pd.Series:
    j = json.load(open(os.path.join(DATA, "gspc_daily.json")))
    r = j["chart"]["result"][0]
    idx = pd.to_datetime(r["timestamp"], unit="s").normalize()
    s = pd.Series(r["indicators"]["quote"][0]["close"], index=idx, dtype=float)
    return s.dropna().groupby(level=0).last()


def month_end(s: pd.Series) -> pd.Series:
    """Last available observation in each calendar month, indexed by the
    month (Period). Never forward-fills across a month with no data."""
    return s.groupby(s.index.to_period("M")).last()


def twenty_year() -> tuple[pd.Series, float]:
    """DGS20 with the 1987-01..1993-09 hole filled by DGS30 + a constant.
    The constant is the mean DGS20-DGS30 over 1986, the last year both
    existed — known in real time (spec A4; v0 used 1993-94, a look-ahead).
    A level adjustment only; it cancels in every 12m CHANGE wholly inside
    the splice. Measured fill error: RMSE 0.21pp level, 0.15pp 12m change."""
    d20, d30 = fred_daily("DGS20"), fred_daily("DGS30")
    both = pd.concat([d20, d30], axis=1, sort=True).dropna().loc[SEAM[0]:SEAM[1]]
    offset = float((both["DGS20"] - both["DGS30"]).mean())
    fill = (d30.loc[SPLICE[0]:SPLICE[1]] + offset).rename("DGS20")
    out = pd.concat([d20, fill], sort=True).sort_index()
    return out[~out.index.duplicated(keep="first")], offset


def build() -> pd.DataFrame:
    """Feature panel, one row per month-end, 1962+ (features need history;
    origins start at START)."""
    y3 = month_end(fred_daily("DGS3"))
    y10 = month_end(fred_daily("DGS10"))
    d20, offset = twenty_year()
    y20 = month_end(d20)
    bill = month_end(fred_daily("DTB3"))
    spx = month_end(gspc_daily())

    # CPIAUCNS: never revised, so the YoY is what was published (spec A11)
    cpi = pd.read_csv(os.path.join(DATA, "CPIAUCNS.csv"), na_values=".")
    cpi.columns = ["date", "cpi"]
    cpi = cpi.set_index(pd.to_datetime(cpi["date"]).dt.to_period("M"))["cpi"]
    full = pd.period_range(cpi.index[0], pd.Timestamp.today().to_period("M"), freq="M")
    cpi = cpi.reindex(full)
    cpi_yoy = (cpi / cpi.shift(12) - 1) * 100
    # Month t's CPI is published ~mid t+1, so at an origin t the newest print
    # known is t-1. A missing print (Oct-2025, shutdown) or a not-yet-
    # published month carries the last PUBLISHED value — what was knowable —
    # for at most 2 months, never longer.
    cpi_yoy_lag = cpi_yoy.shift(1).ffill(limit=2)

    rec = pd.read_csv(os.path.join(DATA, "USREC.csv"), na_values=".")
    rec.columns = ["date", "rec"]
    rec = rec.set_index(pd.to_datetime(rec["date"]).dt.to_period("M"))["rec"]

    val = pd.read_csv(os.path.join(DATA, "valuation_monthly.csv"))
    val = val.set_index(pd.PeriodIndex(val["Date"], freq="M"))

    p = pd.DataFrame({"y3": y3, "y10": y10, "y20": y20, "bill": bill,
                      "spx": spx, "cpi_yoy_lag": cpi_yoy_lag, "rec": rec,
                      "cape": val["cape"], "dy": val["dy"]})
    p = p.loc["1962-01":]
    p["L10"] = p["y10"]
    p["L10_dev"] = p["y10"] - p["y10"].rolling(60, min_periods=60).mean()
    p["R10"] = p["y10"] - p["cpi_yoy_lag"]
    p["S3_12"] = p["y3"] - p["y3"].shift(12)
    p["S10_12"] = p["y10"] - p["y10"].shift(12)
    p["S20_12"] = p["y20"] - p["y20"].shift(12)
    p["S10_6"] = p["y10"] - p["y10"].shift(6)
    p["C10_3"] = p["y10"] - p["y3"]
    p["C20_3"] = p["y20"] - p["y3"]
    p["dC20_3"] = p["C20_3"] - p["C20_3"].shift(12)   # = S20_12 - S3_12; not a feature (A5)
    p["SB_12"] = p["bill"] - p["bill"].shift(12)       # policy stance (A5)
    # R5 alt speed: change relative to the starting level
    p["S10_12_rel"] = p["S10_12"] / p["y10"].shift(12)
    # R3 flag: any 20y input inside the splice (level now, or 12 months ago)
    in_splice = (p.index >= pd.Period(SPLICE[0][:7], "M")) & \
                (p.index <= pd.Period(SPLICE[1][:7], "M"))
    p["splice20"] = in_splice | pd.Series(in_splice, index=p.index).shift(12,
                                                                          fill_value=False).values
    p["regime"] = [regime(a, b) for a, b in zip(p["S3_12"], p["S20_12"])]
    p.attrs["splice_offset"] = offset
    return p


FEATURES = ["L10", "L10_dev", "R10", "S3_12", "S10_12", "S20_12", "S10_6",
            "C10_3", "C20_3", "SB_12"]
DEADBAND = 0.25


def regime(a: float, b: float) -> str | None:
    """Curve-move regime from the 12m change in the 3y (a) and 20y (b).
    Deadband PER LEG (spec A7): a leg inside +/-0.25pp counts as flat, so
    3y +0.05 / 20y -0.60 is a bull-flattener, not a twist."""
    if pd.isna(a) or pd.isna(b):
        return None
    sa = 0 if abs(a) < DEADBAND else (1 if a > 0 else -1)
    sb = 0 if abs(b) < DEADBAND else (1 if b > 0 else -1)
    if sa == 0 and sb == 0:
        return "QUIET"
    if sa * sb < 0:
        return "TWIST"
    if sa > 0 or sb > 0:                      # bear: at least one leg up
        return "BEAR-FLAT" if a > b else "BEAR-STEEP"
    return "BULL-STEEP" if a < b else "BULL-FLAT"


def outcomes(p: pd.DataFrame, horizons=(6, 12, 18)) -> pd.DataFrame:
    """Forward S&P outcomes. Kept apart from build() on purpose.

    r{h}    price return, month-end to month-end (the headline outcome)
    tr{h}   total return: monthly price relative + dividend yield/12 accrued
    dd{h}   worst drawdown from the origin close, DAILY closes, inside (t, t+h]
    carry{h} 3-month-bill carry over the window (bill yield at t x h/12) —
             the cash hurdle for proceeds; discount-basis bill, ~bp-level bias
    """
    out = pd.DataFrame(index=p.index)
    daily = gspc_daily()
    dper = daily.index.to_period("M")
    spx = p["spx"].copy()
    # A month whose last close is before its last business day is PARTIAL
    # (today: 2026-09-25). It may be an ORIGIN (today's reading) but never a
    # return ENDPOINT — that would be an h-month return missing its last days.
    last = daily.index[-1]
    if last < last + pd.offsets.BMonthEnd(0):
        spx.iloc[-1] = np.nan
    rel = (spx / spx.shift(1)).shift(-1)                    # month m -> m+1
    div = (p["dy"] / 100 / 12)
    for h in horizons:
        out[f"r{h}"] = spx.shift(-h) / p["spx"] - 1
        out[f"up{h}"] = (out[f"r{h}"] > 0).where(out[f"r{h}"].notna())
        growth = (rel + div).rolling(h).apply(np.prod, raw=True).shift(-(h - 1))
        out[f"tr{h}"] = (growth - 1).where(out[f"r{h}"].notna())
        out[f"carry{h}"] = p["bill"] / 100 * h / 12
        dd = []
        for per, ok in zip(p.index, out[f"r{h}"].notna()):
            w = daily[(dper > per) & (dper <= per + h)] if ok else ()
            dd.append(w.min() / p.at[per, "spx"] - 1 if len(w) else np.nan)
        out[f"dd{h}"] = pd.Series(dd, index=p.index).where(out[f"r{h}"].notna())
    return out


if __name__ == "__main__":
    p = build()
    print(f"splice offset (DGS20-DGS30, 1986): "
          f"{p.attrs['splice_offset']:+.3f}pp")
    q = p.loc[START:]
    print(f"origins {q.index[0]}..{q.index[-1]}  n={len(q)}")
    print(q[FEATURES].isna().sum().to_string())
    print("\nLATEST:")
    print(q[FEATURES + ["regime", "bill", "spx"]].tail(3).T.to_string())
    print("\nregime counts:", q["regime"].value_counts().to_dict())
