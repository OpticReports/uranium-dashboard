"""Fed-funds-futures-implied FOMC probabilities (FedWatch methodology,
computed from the ZQ curve via Yahoo's keyless quote API — CME's own site is
bot-walled, but the futures PRICES are the underlying data anyway).

Method (first-order FedWatch):
  ZQ contract price P for month M implies the month's average daily fed funds
  rate r_M = 100 - P. For a meeting on day d of an N-day month, the old rate
  holds through day d and the new rate applies after:
      r_M = (d/N) * r_start + ((N-d)/N) * r_end   ->  solve r_end.
  r_start (the rate going INTO the meeting) comes, in order, from:
    1. the prior month's contract, when that month held no decision,
    2. the chain — the previous meeting's implied r_end,
    3. SPOT EFFR, for the first upcoming meeting only, since no decision
       falls between today and it. Added 2026-09-16: an expired prior month
       stops quoting the moment it settles, and with no spot anchor that
       silently took out the two NEAREST meetings — the rows that matter
       most. ZQ settles on the monthly average of EFFR, so spot EFFR is the
       same quantity the expired contract would have carried.
  r_end comes from the month-average solve, EXCEPT for a late-month meeting:
  the solve divides by post_frac, so a meeting on the 28th of a 31-day month
  amplifies any quote error ~10x. Below a quarter of the month, r_end is read
  off the NEXT month's contract instead, when that month is verified
  meeting-free.
  The implied move delta = r_end - r_start is distributed across the two
  adjacent 25bp outcomes; moves map to the ensemble buckets (<=-50 cut50p,
  -25 cut25, 0 hold, >=+25 hike25p).

Honesty: first-order approximation (no meeting-outcome tree, no term-premium
adjustment); futures embed small risk premia vs pure expectation. No
historical archive is fetchable for expired contracts, so this source enters
the ensemble AT THE SHRINKAGE PRIOR (n=0) and earns weight as meetings
resolve — stated on the panel. Every meeting this method cannot price
reports a REASON through `notes`, so a dash on the panel always says why.
"""
from __future__ import annotations

import calendar
import logging
import math
import time
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_MONTH_CODE = "FGHJKMNQUVXZ"          # Jan..Dec
_UA = {"User-Agent": "Mozilla/5.0 (optic-research canary tool)"}
_CACHE: dict = {}
_EFFR_CACHE: dict = {}
_TTL = 900

# Prefer the NEXT month's contract for r_end when the meeting leaves less than
# this fraction of its own month behind it: the month-average solve divides by
# post_frac, amplifying quote error by 1/post_frac, so at 0.25 the
# amplification is capped at 4x (a meeting on the 28th of a 31-day month would
# otherwise run at ~10x). Below MIN_POST_FRAC the month average carries
# essentially no post-decision information, so with no next-month contract the
# meeting is reported unpriced rather than guessed.
NEXT_MONTH_PREF = 0.25
MIN_POST_FRAC = 0.03

# FOMC meeting MONTHS. A ZQ contract for a meeting-free month settles at the
# prevailing rate, which is what makes it a clean anchor; a month holding a
# decision settles at a blend and must never be used as one. The Fed's
# published calendars run eight meetings a year, none in Feb/May/Aug/Nov.
# Cross-checked against metrics/squeeze.py FOMC_2026 (day-level) and
# ewm/core.py FOMC (month-level). OUTSIDE this table a month reads UNKNOWN and
# is never treated as meeting-free — the same fail-loud discipline as
# squeeze.py's schedule table. Extend it when the Fed publishes the next year.
FOMC_MONTHS: frozenset = frozenset(
    [(2026, m) for m in (1, 3, 4, 6, 7, 9, 10, 12)]
    + [(2027, m) for m in (1, 3, 4, 6, 7, 9, 10, 12)]
)
FOMC_TABLE_FIRST_YEAR, FOMC_TABLE_LAST_YEAR = 2026, 2027


def _meeting_month(y: int, m: int, passed: set[tuple[int, int]]) -> bool | None:
    """True / False / None — None means outside the verified table, which is
    never read as meeting-free."""
    if (y, m) in passed or (y, m) in FOMC_MONTHS:
        return True
    if FOMC_TABLE_FIRST_YEAR <= y <= FOMC_TABLE_LAST_YEAR:
        return False
    return None


def _effr_nyfed() -> float | None:
    with httpx.Client(timeout=15, headers=_UA) as c:
        r = c.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/"
                  "last/1.json")
        rows = r.json().get("refRates") or []
    for row in rows:
        if row.get("type") == "EFFR" and row.get("percentRate") is not None:
            return float(row["percentRate"])
    return None


def _effr_fred() -> float | None:
    with httpx.Client(timeout=15, headers=_UA, follow_redirects=True) as c:
        text = c.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                     params={"id": "DFF"}).text
    for line in reversed(text.strip().splitlines()):
        parts = line.split(",")
        if len(parts) == 2:
            try:
                return float(parts[1])
            except ValueError:
                continue
    return None


def current_effr() -> float | None:
    """Latest effective fed funds rate, percent. ZQ settles on the monthly
    average of exactly this rate, so it is the natural r_start for the first
    upcoming meeting — and the only anchor left once the prior meeting-free
    month's contract has expired and stopped quoting. The NY Fed's keyless
    rates API is primary (it publishes EFFR itself); FRED's DFF is the
    fallback. Cached for the same 15 minutes as the contract quotes."""
    hit = _EFFR_CACHE.get("v")
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    for name, fn in (("NY Fed", _effr_nyfed), ("FRED DFF", _effr_fred)):
        try:
            v = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("EFFR via %s failed: %s", name, exc)
            continue
        if v is not None:
            _EFFR_CACHE["v"] = (time.time(), v)
            return v
    return None


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
                  prices: dict[tuple[int, int], float] | None = None,
                  effr: float | None = None,
                  notes: dict[str, str] | None = None) -> dict[str, dict]:
    """{meeting_iso: {bucket: prob}} from the ZQ curve.

    `prices` and `effr` are injectable for tests; when `prices` is given the
    function makes NO network call, so an omitted `effr` means "no spot anchor
    available" rather than "go fetch one".
    `notes`, when a dict is passed, is filled with {meeting_iso: reason} for
    every meeting this method cannot price, plus an "_anchor:<iso>" entry
    naming the anchor whenever spot EFFR stood in for an expired contract.
    """
    meetings = sorted(date.fromisoformat(d) for d in meeting_dates)
    if not meetings:
        return {}
    live = prices is None
    client = httpx.Client(timeout=15, headers=_UA) if live else None
    if live and effr is None:
        effr = current_effr()

    def px(y: int, m: int) -> float | None:
        if prices is not None:
            return prices.get((y, m))
        return _price(y, m, client)

    def note(mt: date, why: str) -> None:
        if notes is not None:
            notes[mt.isoformat()] = why

    passed = {(d.year, d.month) for d in meetings}
    out: dict[str, dict] = {}
    r_chain: float | None = None
    try:
        for i, mt in enumerate(meetings):
            y, m = mt.year, mt.month
            p_meet = px(y, m)
            if p_meet is None:
                note(mt, f"no ZQ contract quoted for {y}-{m:02d}")
                continue
            # r_start, in order: the prior meeting-free month's contract, the
            # chain from the previous meeting, then spot EFFR — valid for the
            # FIRST meeting only, since no decision falls between today and it.
            # Without that third leg an expired prior-month contract takes down
            # the nearest meeting, and the broken chain takes the next one too.
            py, pm = _prev_month(y, m)
            r_start = None
            # a ZQ contract stops quoting once its own month is over, so in
            # live mode don't even ask for one that has settled (it would log
            # a fetch failure every refresh for a contract that simply no
            # longer exists). Injected prices are hypothetical: no expiry.
            expired = live and (py, pm) < (date.today().year, date.today().month)
            if not expired and _meeting_month(py, pm, passed) is False:
                p_prev = px(py, pm)
                if p_prev is not None:
                    r_start = 100.0 - p_prev
            if r_start is None:
                r_start = r_chain
            anchor_effr = False
            if r_start is None and i == 0 and effr is not None:
                r_start, anchor_effr = effr, True
            if r_start is None:
                note(mt, "no anchor rate: the prior meeting-free month's "
                         "contract has expired and spot EFFR is unavailable")
                continue
            n_days = calendar.monthrange(y, m)[1]
            r_month = 100.0 - p_meet
            post_frac = (n_days - mt.day) / n_days
            r_end = None
            if post_frac < NEXT_MONTH_PREF:
                # late-month meeting: read r_end off the next month's contract
                # instead of dividing the month average by a small post_frac
                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                if _meeting_month(ny, nm, passed) is False:
                    p_next = px(ny, nm)
                    if p_next is not None:
                        r_end = 100.0 - p_next
            if r_end is None:
                if post_frac <= MIN_POST_FRAC:
                    note(mt, "meeting sits at the month end and the next "
                             "month's contract is unavailable — the month "
                             "average carries no post-decision information")
                    continue
                r_end = (r_month - (1 - post_frac) * r_start) / post_frac
            delta_steps = (r_end - r_start) / 0.25
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
            if anchor_effr and notes is not None:
                notes["_anchor:" + mt.isoformat()] = (
                    f"r_start anchored on spot EFFR {effr:.2f}% — the prior "
                    "month's contract has expired and no longer quotes")
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
