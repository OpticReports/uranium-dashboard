"""Fed-funds-futures-implied FOMC probabilities (FedWatch methodology,
computed from the ZQ curve via Yahoo's keyless quote API — CME's own site is
bot-walled, but the futures PRICES are the underlying data anyway).

Method (first-order FedWatch):
  ZQ contract price P for month M implies the month's average daily fed funds
  rate r_M = 100 - P. For a meeting on day d of an N-day month, the old rate
  holds through day d and the new rate applies after:
      r_M = (d/N) * r_start + ((N-d)/N) * r_end   ->  solve r_end.
  r_start comes from the nearest prior meeting-free month's contract, or
  chains from the previous meeting's implied r_end. The implied move
  delta = r_end - r_start is distributed across the two adjacent 25bp
  outcomes; moves map to the ensemble buckets (<=-50 cut50p, -25 cut25,
  0 hold, >=+25 hike25p).

Honesty: first-order approximation (no meeting-outcome tree, no term-premium
adjustment); futures embed small risk premia vs pure expectation. No
historical archive is fetchable for expired contracts, so this source enters
the ensemble AT THE SHRINKAGE PRIOR (n=0) and earns weight as meetings
resolve — stated on the panel.
"""
from __future__ import annotations

import calendar
import logging
import time
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_MONTH_CODE = "FGHJKMNQUVXZ"          # Jan..Dec
_UA = {"User-Agent": "Mozilla/5.0 (optic-research canary tool)"}
_CACHE: dict = {}
_TTL = 900


def _symbol(y: int, m: int) -> str:
    return f"ZQ{_MONTH_CODE[m - 1]}{str(y)[2:]}.CBT"


def _price(y: int, m: int, client: httpx.Client) -> float | None:
    sym = _symbol(y, m)
    hit = _CACHE.get(sym)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        r = client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                       params={"range": "1d", "interval": "1d"})
        meta = r.json()["chart"]["result"][0]["meta"]
        px = float(meta["regularMarketPrice"])
        _CACHE[sym] = (time.time(), px)
        return px
    except Exception as exc:  # noqa: BLE001
        logger.warning("ZQ fetch %s failed: %s", sym, exc)
        return None


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def implied_probs(meeting_dates: list[str],
                  prices: dict[tuple[int, int], float] | None = None) -> dict[str, dict]:
    """{meeting_iso: {bucket: prob}} from the ZQ curve. `prices` injectable
    for tests: {(year, month): price}."""
    meetings = sorted(date.fromisoformat(d) for d in meeting_dates)
    if not meetings:
        return {}
    client = None
    if prices is None:
        client = httpx.Client(timeout=15, headers=_UA)

    def px(y: int, m: int) -> float | None:
        if prices is not None:
            return prices.get((y, m))
        return _price(y, m, client)

    meeting_months = {(d.year, d.month) for d in meetings}
    out: dict[str, dict] = {}
    r_chain: float | None = None
    try:
        for mt in meetings:
            y, m = mt.year, mt.month
            p_meet = px(y, m)
            if p_meet is None:
                continue
            # anchor: prior meeting-free month's contract beats the chain
            py, pm = _prev_month(y, m)
            r_start = None
            if (py, pm) not in meeting_months:
                p_prev = px(py, pm)
                if p_prev is not None:
                    r_start = 100.0 - p_prev
            if r_start is None:
                r_start = r_chain
            if r_start is None:
                continue
            n_days = calendar.monthrange(y, m)[1]
            d_day = mt.day
            r_month = 100.0 - p_meet
            post_frac = (n_days - d_day) / n_days
            if post_frac <= 0.03:
                # meeting at month end: month avg carries no post-meeting info;
                # use the NEXT month's contract as r_end if it is meeting-free
                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                if (ny, nm) in meeting_months:
                    continue
                p_next = px(ny, nm)
                if p_next is None:
                    continue
                r_end = 100.0 - p_next
            else:
                r_end = (r_month - (1 - post_frac) * r_start) / post_frac
            delta_steps = (r_end - r_start) / 0.25
            import math
            lo = math.floor(delta_steps)
            frac = delta_steps - lo
            move_p = {lo: 1.0 - frac, lo + 1: frac}
            probs = {"cut50p": 0.0, "cut25": 0.0, "hold": 0.0, "hike25p": 0.0}
            for mv, p in move_p.items():
                if p <= 0:
                    continue
                if mv <= -2:
                    probs["cut50p"] += p
                elif mv == -1:
                    probs["cut25"] += p
                elif mv == 0:
                    probs["hold"] += p
                else:
                    probs["hike25p"] += p
            out[mt.isoformat()] = {k: round(v, 4) for k, v in probs.items()}
            r_chain = r_end
    finally:
        if client is not None:
            client.close()
    return out


def implied_6m_change_bp(prices: dict[tuple[int, int], float] | None = None
                         ) -> float | None:
    """Squeeze Radar T1: the ZQ-implied change in the fed funds rate over the
    next ~6 months, in bp (negative = cuts priced). Front month vs the
    contract 6 months out; same first-order caveats as implied_probs. None
    when either leg is unavailable."""
    today = date.today()
    y0, m0 = today.year, today.month
    y6, m6 = (y0 + (m0 + 6 - 1) // 12, (m0 + 6 - 1) % 12 + 1)
    client = None
    if prices is None:
        client = httpx.Client(timeout=15, headers=_UA)

    def px(y: int, m: int) -> float | None:
        if prices is not None:
            return prices.get((y, m))
        return _price(y, m, client)

    try:
        p0, p6 = px(y0, m0), px(y6, m6)
    finally:
        if client is not None:
            client.close()
    if p0 is None or p6 is None:
        return None
    return round(((100.0 - p6) - (100.0 - p0)) * 100.0, 1)
