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
SEAM = ("1993-10-01", "1994-09-30")     # window that sets the splice offset


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
    The constant is the mean DGS20-DGS30 over the 12 months after DGS20
    resumed — a level adjustment only; it cancels in every 12m CHANGE that
    lies wholly inside the splice."""
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

    cpi = pd.read_csv(os.path.join(DATA, "CPIAUCSL.csv"), na_values=".")
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

    p = pd.DataFrame({"y3": y3, "y10": y10, "y20": y20, "bill": bill,
                      "spx": spx, "cpi_yoy_lag": cpi_yoy_lag, "rec": rec})
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
    p["dC20_3"] = p["C20_3"] - p["C20_3"].shift(12)
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
            "C10_3", "C20_3", "dC20_3"]
DEADBAND = 0.25


def regime(a: float, b: float) -> str | None:
    """Curve-move regime from the 12m change in the 3y (a) and 20y (b)."""
    if pd.isna(a) or pd.isna(b):
        return None
    if abs(a) < DEADBAND and abs(b) < DEADBAND:
        return "QUIET"
    if a > 0 and b > 0:
        return "BEAR-FLAT" if a > b else "BEAR-STEEP"
    if a < 0 and b < 0:
        return "BULL-STEEP" if a < b else "BULL-FLAT"
    return "TWIST"


def outcomes(p: pd.DataFrame, horizons=(6, 12, 18)) -> pd.DataFrame:
    """Forward S&P price returns. Kept apart from build() on purpose."""
    out = pd.DataFrame(index=p.index)
    for h in horizons:
        out[f"r{h}"] = p["spx"].shift(-h) / p["spx"] - 1
        out[f"up{h}"] = (out[f"r{h}"] > 0).where(out[f"r{h}"].notna())
    return out


if __name__ == "__main__":
    p = build()
    print(f"splice offset (DGS20-DGS30, 1993-10..1994-09): "
          f"{p.attrs['splice_offset']:+.3f}pp")
    q = p.loc[START:]
    print(f"origins {q.index[0]}..{q.index[-1]}  n={len(q)}")
    print(q[FEATURES].isna().sum().to_string())
    print("\nLATEST:")
    print(q[FEATURES + ["regime", "bill", "spx"]].tail(3).T.to_string())
    print("\nregime counts:", q["regime"].value_counts().to_dict())
