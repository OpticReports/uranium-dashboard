"""Pre-catalyst asymmetry study: shared data + metrics library.

Price source: stockanalysis.com daily history API (adjusted close in field
'a'). Cached to disk per ticker. All returns computed on adjusted closes;
event-day gap uses raw open vs prior raw close only when adjusted opens are
unavailable (stockanalysis 'o' is unadjusted; for recent, split-free windows
this is acceptable and is noted in the honesty box).
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request

CACHE = os.path.join(os.path.dirname(__file__), "px_cache")
os.makedirs(CACHE, exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch_prices(ticker: str, rng: str = "10Y") -> list[dict]:
    """Daily bars oldest-first: [{t,o,h,l,c,a,v}]. Disk-cached."""
    path = os.path.join(CACHE, f"{ticker.upper()}_{rng}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    url = (f"https://stockanalysis.com/api/symbol/s/{ticker.upper()}"
           f"/history?range={rng}&period=Daily")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    data = payload.get("data") or []
    data = sorted(data, key=lambda r: r["t"])
    if data:
        with open(path, "w") as f:
            json.dump(data, f)
    time.sleep(0.4)  # be polite; ~40 tickers total
    return data


def index_of_date(bars: list[dict], date: str) -> int | None:
    """Index of the bar exactly on `date`, else None."""
    lo, hi = 0, len(bars) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid]["t"] == date:
            return mid
        if bars[mid]["t"] < date:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def realized_vol(bars: list[dict], end_idx: int, window: int = 20) -> float | None:
    """Annualized close-to-close log-return vol over `window` days ending at end_idx (inclusive)."""
    if end_idx - window < 0:
        return None
    rets = []
    for i in range(end_idx - window + 1, end_idx + 1):
        p0, p1 = bars[i - 1]["a"], bars[i]["a"]
        if p0 and p1:
            rets.append(math.log(p1 / p0))
    if len(rets) < window // 2:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252)


def event_metrics(bars: list[dict], event_date: str) -> dict | None:
    """Pre-event drift/quietness and event-day move for one event.

    Windows end at t-1 (the close BEFORE the event day) — the last moment a
    position could have been established without the news.
    """
    idx = index_of_date(bars, event_date)
    if idx is None or idx < 65:
        return None
    prev = idx - 1  # t-1 close
    a = lambda i: bars[i]["a"]

    def window_ret(n: int) -> float | None:
        if prev - n < 0:
            return None
        return a(prev) / a(prev - n) - 1.0

    vol20 = realized_vol(bars, prev, 20)
    r5, r10, r20, r60 = (window_ret(n) for n in (5, 10, 20, 60))
    drift_z = None
    if r10 is not None and vol20 not in (None, 0):
        drift_z = r10 / (vol20 * math.sqrt(10 / 252))
    event_ret = a(idx) / a(prev) - 1.0
    # Open gap (unadjusted o vs unadjusted prior close c — see module docstring)
    gap = None
    if bars[idx].get("o") and bars[prev].get("c"):
        gap = bars[idx]["o"] / bars[prev]["c"] - 1.0
    return {
        "event_idx": idx,
        "pre_close": a(prev),
        "event_close": a(idx),
        "r5": r5, "r10": r10, "r20": r20, "r60": r60,
        "vol20_ann": vol20,
        "drift_z10": drift_z,
        "event_ret": event_ret,
        "open_gap": gap,
    }


# ---------------------------------------------------------------------------
# Option payoff simulation (ASSUMPTION-DRIVEN — no historical options data).
# Black-Scholes entry pricing at a scenario IV; exit at INTRINSIC value on the
# event close (conservative: all remaining time value forfeited).
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(s: float, k: float, t_years: float, iv: float, r: float = 0.04) -> float:
    if t_years <= 0 or iv <= 0:
        return max(s - k, 0.0)
    d1 = (math.log(s / k) + (r + iv * iv / 2) * t_years) / (iv * math.sqrt(t_years))
    d2 = d1 - iv * math.sqrt(t_years)
    return s * _norm_cdf(d1) - k * math.exp(-r * t_years) * _norm_cdf(d2)


def bs_put(s: float, k: float, t_years: float, iv: float, r: float = 0.04) -> float:
    call = bs_call(s, k, t_years, iv, r)
    return call - s + k * math.exp(-r * t_years)  # parity


def simulate_structures(bars: list[dict], event_idx: int, entry_days_before: int,
                        iv: float, expiry_days_after: int = 5) -> dict | None:
    """Buy at close of t - entry_days_before; mark at intrinsic on event close.

    Structures: ATM call, ATM straddle, 20%-OTM call. Strikes set off the
    ENTRY-DAY close (rounded to whole dollars like listed strikes).
    Returns payoff multiples (exit_value / premium).
    """
    entry_idx = event_idx - entry_days_before
    if entry_idx < 0:
        return None
    s0 = bars[entry_idx]["a"]
    s1 = bars[event_idx]["a"]
    if not s0 or not s1:
        return None
    t_years = (entry_days_before + expiry_days_after) / 252.0
    k_atm = max(1.0, round(s0))
    # On low-priced names round(1.2*s) can collide with the ATM strike
    # (counter-agent finding: GERN/MREO) — force at least one strike of OTM.
    k_otm = max(k_atm + 1.0, round(s0 * 1.20))
    atm_call = bs_call(s0, k_atm, t_years, iv)
    atm_put = bs_put(s0, k_atm, t_years, iv)
    otm_call = bs_call(s0, k_otm, t_years, iv)
    out = {}
    if atm_call > 0.01:
        out["atm_call_mult"] = max(s1 - k_atm, 0.0) / atm_call
        out["atm_call_cost_pct"] = atm_call / s0
    if atm_call + atm_put > 0.01:
        out["straddle_mult"] = (max(s1 - k_atm, 0.0) + max(k_atm - s1, 0.0)) / (atm_call + atm_put)
        out["straddle_cost_pct"] = (atm_call + atm_put) / s0
    if otm_call > 0.005:
        out["otm_call_mult"] = max(s1 - k_otm, 0.0) / otm_call
        out["otm_call_cost_pct"] = otm_call / s0
    out["entry_spot"] = s0
    out["event_spot"] = s1
    return out
