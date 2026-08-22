"""ROUND 7 data lane: FMP dividend-adjusted EOD prices + the cross-validation gate.

WHY A NEW LANE. Rounds 4-6 ran on the stockanalysis lane, whose `10Y` range
cannot reach 2006. The round-7 registration
(docs/VARIANTS_PREREGISTRATION_R7_20Y.md) fixes FMP
`historical-price-eod/dividend-adjusted` as the 20-year source and fixes, IN
ADVANCE, the gate that must clear before any result is computed:

    over the overlap with the stockanalysis lane, the two sources must agree
    on DAILY RETURNS for SPY, GLD, EEM, IWN, DLS and XBI to within 5 bps RMS.
    If any ticker fails, the round STOPS and reports the discrepancy rather
    than picking the friendlier source.

`cross_validate()` implements exactly that and `gate_passes()` is the hard
stop. Nothing in this module computes a study result.

The v3 FMP endpoints are 403 on this plan; only `/stable/...` is used. The
plan also caps a response at 5,000 rows, which is what puts the 20-year
window's start at 2006-10-05 rather than 2006-08-22 — that cap is a property
of the data lane, recorded here and in the report, not a choice.

This module NEVER writes into backend/data/px_cache. That directory is the
frozen round 4-6 record and a counter-agent is verifying round 6 against it;
round 7's caches live under backend/data/r7_cache/.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
DATA = BACKEND / "data"
R7_CACHE = DATA / "r7_cache"
FMP_CACHE = R7_CACHE / "fmp"
SA_CACHE = R7_CACHE / "stockanalysis"
# The frozen rounds 4-6 cache. READ-ONLY here: when a cross-validation ticker
# is already in it we read the very file the other lane used, so the gate
# compares against the incumbent bytes rather than a fresh download.
FROZEN_PX_CACHE = DATA / "px_cache"

FMP_BASE = "https://financialmodelingprep.com/stable/historical-price-eod/dividend-adjusted"
SA_BASE = "https://stockanalysis.com/api/symbol/s"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

FMP_START = "2006-01-01"     # ask for everything; the 5,000-row cap decides
FMP_ROW_CAP = 5000
POLITE_DELAY_S = 0.35

# The gate, fixed by the registration. Do not soften.
GATE_TICKERS = ("SPY", "GLD", "EEM", "IWN", "DLS", "XBI")
GATE_RMS_BPS = 5.0


class DataLaneError(RuntimeError):
    """Raised when the lane cannot produce trustworthy data."""


# --- HTTP (one seam, so tests never touch the network) ------------------------------

def _http_json(url: str, *, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310
        return json.load(resp)


# --- FMP lane -----------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        raise DataLaneError("FMP_API_KEY is not set; the round-7 lane cannot fetch.")
    return key


def fmp_bars(symbol: str, *, start: str = FMP_START, cache_dir: Path | None = None,
             delay_s: float = POLITE_DELAY_S) -> list[dict]:
    """Dividend-adjusted daily bars OLDEST-FIRST for `symbol`. Disk-cached.

    The endpoint returns newest-first; this sorts. A cached file is returned
    verbatim without any network call, so a re-run of the study is exactly
    reproducible and costs zero requests.
    """
    cache_dir = cache_dir or FMP_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol.upper()}_{start}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = f"{FMP_BASE}?{urllib.parse.urlencode({'symbol': symbol.upper(), 'from': start, 'apikey': _api_key()})}"
    payload = _http_json(url)
    if isinstance(payload, dict):
        # The plan signals refusals as a dict ({"Error Message": ...}), never a list.
        raise DataLaneError(f"{symbol}: FMP returned {sorted(payload)[:3]} instead of rows")
    rows = sorted(payload or [], key=lambda r: r["date"])
    if not rows:
        raise DataLaneError(f"{symbol}: FMP returned no rows")
    path.write_text(json.dumps(rows))
    if delay_s:
        time.sleep(delay_s)
    return rows


def fmp_adj_close(symbol: str, **kw) -> dict[str, float]:
    """{ISO date: adjClose} — the total-return series the study runs on."""
    return {r["date"]: float(r["adjClose"]) for r in fmp_bars(symbol, **kw)
            if r.get("adjClose")}


def at_row_cap(symbol: str, **kw) -> bool:
    """True when the response hit the plan's 5,000-row cap (history is truncated)."""
    return len(fmp_bars(symbol, **kw)) >= FMP_ROW_CAP


# --- stockanalysis lane (comparison only) -------------------------------------------

def stockanalysis_bars(ticker: str, rng: str = "10Y",
                       delay_s: float = POLITE_DELAY_S) -> list[dict]:
    """Bars oldest-first from the rounds 4-6 lane, for the gate ONLY.

    Reads the frozen backend/data/px_cache file when one exists — the gate
    should compare against the exact bytes rounds 4-6 used — and otherwise
    caches its own copy under r7_cache/stockanalysis (never into the frozen
    directory).
    """
    frozen = FROZEN_PX_CACHE / f"{ticker.upper()}_{rng}.json"
    if frozen.exists():
        return json.loads(frozen.read_text())
    SA_CACHE.mkdir(parents=True, exist_ok=True)
    path = SA_CACHE / f"{ticker.upper()}_{rng}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = f"{SA_BASE}/{ticker.upper()}/history?range={rng}&period=Daily"
    payload = _http_json(url)
    rows = sorted(payload.get("data") or [], key=lambda r: r["t"])
    if not rows:
        raise DataLaneError(f"{ticker}: stockanalysis returned no rows")
    path.write_text(json.dumps(rows))
    if delay_s:
        time.sleep(delay_s)
    return rows


def stockanalysis_adj_close(ticker: str, rng: str = "10Y", **kw) -> dict[str, float]:
    """{ISO date: adjusted close} from field 'a' — the rounds 4-6 convention."""
    return {b["t"]: float(b["a"]) for b in stockanalysis_bars(ticker, rng, **kw)
            if b.get("a")}


# --- returns + the gate --------------------------------------------------------------

def daily_returns(series: dict[str, float], dates: list[str]) -> list[float]:
    return [series[dates[i]] / series[dates[i - 1]] - 1.0 for i in range(1, len(dates))]


def compare_lanes(fmp: dict[str, float], sa: dict[str, float]) -> dict:
    """Daily-return agreement between the two lanes over their shared dates.

    Returns are compared on CONSECUTIVE shared dates only: a date present in
    one lane and missing from the other would otherwise turn a one-day return
    into a two-day return and manufacture a disagreement that is a calendar
    artifact, not a price disagreement.
    """
    dates = sorted(set(fmp) & set(sa))
    if len(dates) < 2:
        return {"n": 0, "rms_bps": float("nan"), "max_bps": float("nan"),
                "start": None, "end": None, "worst_date": None}
    ra, rb = daily_returns(fmp, dates), daily_returns(sa, dates)
    diffs = [a - b for a, b in zip(ra, rb, strict=True)]
    rms = math.sqrt(sum(d * d for d in diffs) / len(diffs)) * 1e4
    worst_i = max(range(len(diffs)), key=lambda i: abs(diffs[i]))
    return {
        "n": len(diffs),
        "start": dates[0], "end": dates[-1],
        "rms_bps": rms,
        "max_bps": abs(diffs[worst_i]) * 1e4,
        "worst_date": dates[worst_i + 1],
        "mean_bps": sum(diffs) / len(diffs) * 1e4,
    }


def cross_validate(tickers=GATE_TICKERS, *, threshold_bps: float = GATE_RMS_BPS,
                   fmp_loader=None, sa_loader=None) -> dict:
    """THE REGISTERED GATE. Run before any result is computed.

    Per ticker: overlap size, RMS and max daily-return difference in bps, and
    pass/fail against `threshold_bps`. `passed` is True only when EVERY ticker
    clears; a ticker whose overlap is empty is a FAILURE, not a skip.
    """
    fmp_loader = fmp_loader or fmp_adj_close
    sa_loader = sa_loader or stockanalysis_adj_close
    per: dict[str, dict] = {}
    for t in tickers:
        try:
            row = compare_lanes(fmp_loader(t), sa_loader(t))
        except Exception as exc:                      # noqa: BLE001 - reported, not raised
            row = {"n": 0, "rms_bps": float("nan"), "max_bps": float("nan"),
                   "error": f"{type(exc).__name__}: {exc}"}
        row["threshold_bps"] = threshold_bps
        row["pass"] = bool(row["n"] >= 2 and row["rms_bps"] <= threshold_bps)
        per[t] = row
    return {"threshold_bps": threshold_bps,
            "tickers": per,
            "passed": all(r["pass"] for r in per.values())}


def gate_passes(result: dict) -> bool:
    return bool(result.get("passed"))


def require_gate(result: dict) -> None:
    """Hard stop. The registration: a failure reports the discrepancy and the
    round produces NO study results."""
    if not gate_passes(result):
        bad = [f"{t}: RMS {r['rms_bps']:.2f} bps over n={r['n']}"
               + (f" ({r['error']})" if r.get("error") else "")
               for t, r in result["tickers"].items() if not r["pass"]]
        raise DataLaneError(
            "CROSS-VALIDATION GATE FAILED — no round-7 result may be computed. "
            + "; ".join(bad))
