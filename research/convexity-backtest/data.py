"""
Data loaders for the long-horizon reconstruction harness.

Primary source is FRED (St. Louis Fed), which is reachable from this environment
and carries long, clean, dividend-unadjusted index history plus risk-free rates:

    NASDAQ100  NASDAQ-100 index level         1986-01-02 -> present
    VIXCLS     CBOE VIX (spot)                1990-01-02 -> present
    DGS3MO     3-month T-bill (financing leg) 1981-09-01 -> present

IMPORTANT DATA-HONESTY NOTES
----------------------------
* FRED equity series are PRICE indices (no dividends). For NDX the dividend
  yield is small (~0.6%/yr) but non-zero; we subtract an explicit dividend
  assumption so the omission is visible and adjustable, not hidden.
* FRED does NOT carry VIX *futures* or the SPVXSTR short-term VIX futures index
  that UVXY/VIXY actually track. Only VIX *spot* is available here. Any vol-ETF
  reconstruction from spot is therefore a MODEL, not data -- see synth.py.

Fetching is done via `curl` (proven to work through this environment's proxy);
results are cached under ./data so re-runs are deterministic and offline.
"""
from __future__ import annotations

import io
import os
import subprocess
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data")
os.makedirs(CACHE, exist_ok=True)

FRED_SERIES = {
    "NASDAQ100": "NASDAQ100",  # NDX price index, 1986+
    "VIXCLS": "VIXCLS",        # VIX spot, 1990+
    "DGS3MO": "DGS3MO",        # 3M T-bill yield (%), 1981+
}


def _fred_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def fetch_fred(series_id: str, force: bool = False) -> pd.Series:
    """Download one FRED series (cached). Returns a float Series indexed by date."""
    path = os.path.join(CACHE, f"{series_id}.csv")
    if force or not os.path.exists(path):
        out = subprocess.run(
            ["curl", "-sS", "--max-time", "60", _fred_url(series_id)],
            capture_output=True, text=True, check=True,
        ).stdout
        if "<html" in out.lower() or not out.strip():
            raise RuntimeError(f"FRED fetch for {series_id} did not return CSV")
        with open(path, "w") as f:
            f.write(out)
    df = pd.read_csv(path)
    date_col, val_col = df.columns[0], df.columns[1]
    df[date_col] = pd.to_datetime(df[date_col])
    # FRED encodes missing values as ".": coerce to NaN, then forward-fill rates only.
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    s = df.set_index(date_col)[val_col].rename(series_id)
    return s


def load_panel(force: bool = False) -> pd.DataFrame:
    """Load all series aligned on a business-day index (raw levels, NaNs kept)."""
    cols = {name: fetch_fred(sid, force=force) for name, sid in FRED_SERIES.items()}
    panel = pd.DataFrame(cols).sort_index()
    return panel


if __name__ == "__main__":
    p = load_panel()
    print("Loaded panel:")
    print("  span:", p.index.min().date(), "->", p.index.max().date())
    print("  rows:", len(p))
    for c in p.columns:
        s = p[c].dropna()
        print(f"  {c:10s} {s.index.min().date()} -> {s.index.max().date()}  n={len(s)}")
