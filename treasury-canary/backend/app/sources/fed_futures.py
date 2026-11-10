"""Fed-funds-futures-implied FOMC probabilities, computed from the ZQ curve
via Yahoo's keyless quote API (CME's own site is bot-walled, but the futures
PRICES are the underlying data anyway).

Method:
  ZQ settles at 100 minus the arithmetic average of the DAILY effective fed
  funds rate over the CALENDAR month, and stops quoting on the last business
  day of that month. So a contract price P for month M gives that month's
  average rate r_M = 100 - P, and for a decision on day d of an N-day month
      r_M = (d/N) * r_start + ((N-d)/N) * r_end,    post_frac = (N-d)/N
  with r_start the rate going in and r_end the rate coming out. One equation,
  two unknowns: one of them has to come from a neighbouring contract, and the
  OTHER is solved. Solving divides by that side's weight, so we always solve
  the side the month actually measures:

    post_frac >= 0.5 (decision early in its month) -> the month is mostly the
      NEW rate: take r_start from a neighbour and solve r_end (divide by
      post_frac).
    post_frac < 0.5 (decision late in its month) -> the month is mostly the
      OLD rate: take r_end from the NEXT month's contract, when that month is
      verified meeting-free, and solve r_start (divide by 1 - post_frac).
      This is CME's own second form, and it keeps the row self-contained: the
      meeting's own contract is used, nothing is inherited from the chain.

  r_start, when it must come from a neighbour, is taken in this order:
    1. the prior month's contract, when that month held no decision,
    2. the chain — the previous meeting's implied r_end,
    3. SPOT EFFR, for the first UPCOMING meeting only, since no decision falls
       between today and it. Added 2026-09-16: an expired prior month stops
       quoting the moment it settles, and with no spot anchor that silently
       took out the two NEAREST meetings — the rows that matter most. ZQ
       settles on the average of exactly this rate, so spot EFFR is the same
       quantity the expired contract would have carried. The NY Fed publishes
       a day in arrears, so the print is checked against the last decision
       BEFORE the meeting being anchored: the pre-decision rate is exactly
       r_start for the meeting that IS that decision, and is refused for the
       one after it until a print lands on the new stance.

  The implied move delta = r_end - r_start is distributed across the two
  adjacent 25bp outcomes; moves map to the ensemble buckets (<=-50 cut50p,
  -25 cut25, 0 hold, >=+25 hike25p).

Honesty: first-order (no meeting-outcome tree, no term-premium adjustment),
and it ignores that a new target takes effect the day AFTER the decision.
Futures embed small risk premia vs pure expectation. Where it DIVERGES from
CME FedWatch, stated so nobody assumes they match: CME anchors on the nearest
FUTURE meeting-free month and propagates backward, while this chains forward
from the prior one and prefers realized spot EFFR for the front meeting —
measured 2026-09-16, that is worth ~7pp on the front row (90% vs 97% hike),
the gap being the ~1bp by which realized EFFR sits above the curve-implied
start. No historical archive is fetchable for expired contracts, so this
source enters the ensemble AT THE SHRINKAGE PRIOR (n=0) and earns weight as
meetings resolve — stated on the panel. Every meeting this method cannot
price, and every reading it prices on a poorly-conditioned leg, reports
through `notes`, so a dash or a soft number on the panel always says why.
"""
from __future__ import annotations

import calendar
import logging
import math
import statistics
import time
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_MONTH_CODE = "FGHJKMNQUVXZ"          # Jan..Dec
_UA = {"User-Agent": "Mozilla/5.0 (optic-research canary tool)"}
_CACHE: dict = {}
_EFFR_CACHE: dict = {}
_TTL = 900
_TTL_FAIL = 120                       # don't re-dial a dead provider each call

# Below this weight the month average carries essentially no information about
# that side of the decision, so rather than divide by it we report the meeting
# unpriced. Above it but below 0.25 the reading is published WITH a note
# naming the amplification (1 / weight).
MIN_POST_FRAC = 0.03
SOFT_FRAC = 0.25

# FOMC meetings as (first day, DECISION day) — transcribed from
# federalreserve.gov/monetarypolicy/fomccalendars.htm, retrieved 2026-09-16.
# The decision lands on the second day. 2028 is not published yet, which is
# what FOMC_TABLE_LAST_YEAR encodes.
#
# Transcribed, NEVER inferred: meetings are not confined to
# Jan/Mar/Apr/Jun/Jul/Sep/Oct/Dec — May 2025, Nov 2024, May 2023 and Nov 2021
# all held one — and the Apr-May 2024 and Oct-Nov 2023 meetings SPANNED a
# month boundary, which blends BOTH months' contracts. FOMC_MONTHS below is
# derived from both days of every meeting so a boundary-spanning meeting marks
# both months, and a month that holds a decision is never used as a clean
# anchor. Outside the table a month reads UNKNOWN and is never assumed free.
FOMC_MEETINGS: tuple[tuple[str, str], ...] = (
    ("2026-01-27", "2026-01-28"), ("2026-03-17", "2026-03-18"),
    ("2026-04-28", "2026-04-29"), ("2026-06-16", "2026-06-17"),
    ("2026-07-28", "2026-07-29"), ("2026-09-15", "2026-09-16"),
    ("2026-10-27", "2026-10-28"), ("2026-12-08", "2026-12-09"),
    ("2027-01-26", "2027-01-27"), ("2027-03-16", "2027-03-17"),
    ("2027-04-27", "2027-04-28"), ("2027-06-08", "2027-06-09"),
    ("2027-07-27", "2027-07-28"), ("2027-09-14", "2027-09-15"),
    ("2027-10-26", "2027-10-27"), ("2027-12-07", "2027-12-08"),
)
FOMC_TABLE_FIRST_YEAR, FOMC_TABLE_LAST_YEAR = 2026, 2027
DECISION_DAYS: tuple[date, ...] = tuple(
    date.fromisoformat(d) for _, d in FOMC_MEETINGS)
FOMC_MONTHS: frozenset = frozenset(
    (date.fromisoformat(x).year, date.fromisoformat(x).month)
    for pair in FOMC_MEETINGS for x in pair)


def _symbol(y: int, m: int) -> str:
    return f"ZQ{_MONTH_CODE[m - 1]}{str(y)[2:]}.CBT"


def _meeting_month(y: int, m: int, passed: set[tuple[int, int]]) -> bool | None:
    """True / False / None — None means outside the transcribed table, which is
    never read as meeting-free."""
    if (y, m) in passed or (y, m) in FOMC_MONTHS:
        return True
    if FOMC_TABLE_FIRST_YEAR <= y <= FOMC_TABLE_LAST_YEAR:
        return False
    return None


def snap_to_decision(d: date, tol_days: int = 3) -> date | None:
    """The published FOMC decision day within `tol_days` of `d`, else None.

    Prediction-market metadata (Polymarket endDate, Kalshi close_time) is a UTC
    timestamp truncated to a date and can land a day either side of the real
    decision. post_frac is driven by the day of the month, so a one-day error
    moves a row several points — snap to the Fed's own calendar instead."""
    return next((x for x in DECISION_DAYS if abs((x - d).days) <= tol_days), None)


def last_decision_before(d: date) -> date | None:
    """The most recent published decision STRICTLY before `d`."""
    past = [x for x in DECISION_DAYS if x < d]
    return max(past) if past else None


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


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


# ---------- spot EFFR (the anchor of last resort) ----------

def _effr_nyfed() -> list[tuple[date, float]]:
    """[(observation date, rate)] newest first, from the NY Fed's keyless API."""
    with httpx.Client(timeout=15, headers=_UA) as c:
        r = c.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/"
                  "last/5.json")
        r.raise_for_status()
        rows = r.json().get("refRates") or []
    out = []
    for row in rows:
        if row.get("type") != "EFFR" or row.get("percentRate") is None:
            continue
        try:
            out.append((date.fromisoformat(row["effectiveDate"]),
                        float(row["percentRate"])))
        except (ValueError, TypeError, KeyError):
            continue
    return sorted(out, reverse=True)


def _effr_fred() -> list[tuple[date, float]]:
    with httpx.Client(timeout=15, headers=_UA, follow_redirects=True) as c:
        r = c.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                  params={"id": "DFF"})
        r.raise_for_status()
        text = r.text
    out = []
    for line in text.strip().splitlines()[-10:]:
        parts = line.split(",")
        if len(parts) != 2:
            continue
        try:
            out.append((date.fromisoformat(parts[0].strip()),
                        float(parts[1])))
        except ValueError:
            continue
    return sorted(out, reverse=True)


def current_effr() -> tuple[float, date] | None:
    """(rate, observation date) for the latest published policy stance, or None.

    ZQ settles on the monthly average of exactly this rate, so it is the
    natural r_start for the first upcoming meeting — and the only anchor left
    once the prior meeting-free month's contract has expired and stopped
    quoting. Prints are filtered to those sharing the NEWEST print's stance
    (i.e. after the last decision that precedes it), and the median of what
    survives shrugs off a month-end print, which runs firm. The caller checks
    the returned date against the meeting it is anchoring — the NY Fed
    publishes a day in arrears, so across a decision this value is briefly the
    OLD stance and must not be carried past it. NY Fed is primary (it
    publishes EFFR itself); FRED's DFF is the fallback."""
    hit = _EFFR_CACHE.get("v")
    if hit and time.time() - hit[0] < (_TTL if hit[1] else _TTL_FAIL):
        return hit[1]
    val: tuple[float, date] | None = None
    for name, fn in (("NY Fed", _effr_nyfed), ("FRED DFF", _effr_fred)):
        try:
            rows = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("EFFR via %s failed: %s", name, exc)
            continue
        if not rows:
            continue
        newest = max(d for d, _ in rows)
        last = last_decision_before(newest)
        same_stance = [(d, v) for d, v in rows if last is None or d > last]
        if same_stance:
            val = (round(statistics.median(v for _, v in same_stance), 4), newest)
            break
    _EFFR_CACHE["v"] = (time.time(), val)
    return val


def implied_probs(meeting_dates: list[str],
                  prices: dict[tuple[int, int], float] | None = None,
                  effr: float | None = None,
                  notes: dict[str, str] | None = None,
                  today: date | None = None,
                  effr_date: date | None = None) -> dict[str, dict]:
    """{meeting_iso: {bucket: prob}} from the ZQ curve.

    Keys are the dates PASSED IN, so the caller's table lines up, but each is
    snapped to the published FOMC decision day for the arithmetic.
    `prices`, `effr` and `today` are injectable for tests; when `prices` is
    given the function makes NO network call, so an omitted `effr` means "no
    spot anchor available" rather than "go fetch one".
    `notes`, when a dict is passed, collects {meeting_iso: reason} for every
    meeting this method cannot price, "_anchor:<iso>" naming the anchor when
    spot EFFR stood in, and "_soft:<iso>" when a reading had to be solved on a
    poorly-conditioned leg.
    """
    today = today or date.today()
    # an injected rate with no date is trusted as current (tests construct the
    # scenario); the live path always carries the observation date
    stale_ok = effr_date is None
    seen: dict[date, str] = {}
    for iso in meeting_dates:                       # de-duplicate: a repeated
        d = date.fromisoformat(iso)                 # date would re-price the
        seen.setdefault(d, iso)                     # same meeting off its own
    meetings = sorted(seen)                         # r_end and corrupt the chain
    if not meetings:
        return {}
    live = prices is None
    out: dict[str, dict] = {}
    r_chain: float | None = None
    client = None
    try:
        if live:
            client = httpx.Client(timeout=15, headers=_UA)
            if effr is None:
                spot = current_effr()
                if spot is not None:
                    effr, effr_date = spot
                    stale_ok = False

        def px(y: int, m: int) -> float | None:
            if prices is not None:
                return prices.get((y, m))
            return _price(y, m, client)

        def note(key: str, why: str) -> None:
            if notes is not None:
                notes[key] = why

        passed = {(d.year, d.month) for d in meetings}
        for i, raw in enumerate(meetings):
            iso = seen[raw]
            mt = snap_to_decision(raw)
            if mt is None:
                if raw.year > FOMC_TABLE_LAST_YEAR:
                    note("_soft:" + iso,
                         "meeting day taken from market metadata — the "
                         f"published FOMC table ends {FOMC_TABLE_LAST_YEAR}")
                    mt = raw
                else:
                    note(iso, "date matches no published FOMC decision within "
                              "3 days")
                    r_chain = None
                    continue
            y, m = mt.year, mt.month
            p_meet = px(y, m)
            if p_meet is None:
                note(iso, f"no ZQ contract quoted for {y}-{m:02d}")
                r_chain = None
                continue
            n_days = calendar.monthrange(y, m)[1]
            r_month = 100.0 - p_meet
            post_frac = (n_days - mt.day) / n_days

            # the next month's contract reads the post-decision rate directly,
            # but only when that month is verified to hold no decision of its
            # own (otherwise it settles at a blend and is not a clean read)
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            next_free = _meeting_month(ny, nm, passed) is False
            p_next = px(ny, nm) if next_free else None

            r_start = r_end = None
            if p_next is not None and post_frac < 0.5 and (1 - post_frac) > MIN_POST_FRAC:
                # decision late in its month: solve the side the month measures
                r_end = 100.0 - p_next
                r_start = (r_month - post_frac * r_end) / (1.0 - post_frac)
            else:
                py, pm = _prev_month(y, m)
                # a ZQ contract stops quoting once its month is over, so in
                # live mode don't even ask for one that has settled — it would
                # log a fetch failure every refresh for a contract that simply
                # no longer exists. Injected prices are hypothetical: no expiry.
                expired = live and (py, pm) < (today.year, today.month)
                prior_free = _meeting_month(py, pm, passed) is False
                prior_why = ("has expired and no longer quotes" if expired else
                             "is not quoted" if prior_free else
                             "holds a decision, so it is not a clean anchor")
                if not expired and prior_free:
                    p_prev = px(py, pm)
                    if p_prev is not None:
                        r_start = 100.0 - p_prev
                if r_start is None:
                    r_start = r_chain
                anchor_effr = False
                if r_start is None and i == 0 and mt >= today and effr is not None:
                    # spot EFFR must reflect the stance going INTO this meeting.
                    # The NY Fed publishes a day in arrears, so for a day or two
                    # after a decision the newest print is still the old stance —
                    # refuse it rather than carry a pre-decision rate forward.
                    prev_decision = last_decision_before(mt)
                    if stale_ok or prev_decision is None or effr_date > prev_decision:
                        r_start, anchor_effr = effr, True
                    else:
                        note(iso, "spot EFFR has not printed since the "
                                  f"{prev_decision} decision, so it would "
                                  "anchor on the previous stance")
                        r_chain = None
                        continue
                if r_start is None:
                    note(iso, f"no anchor rate: the prior month's contract "
                              f"{prior_why} and spot EFFR is unavailable")
                    r_chain = None
                    continue
                if post_frac <= MIN_POST_FRAC:
                    note(iso, "decision sits at the month end and the next "
                              "month's contract is unavailable — the month "
                              "average carries no post-decision information")
                    r_chain = None
                    continue
                r_end = (r_month - (1 - post_frac) * r_start) / post_frac
                if anchor_effr:
                    note("_anchor:" + iso,
                         f"r_start is spot EFFR {effr:.2f}%"
                         + (f" (as of {effr_date})" if effr_date else "")
                         + f" — the prior month's contract {prior_why}")
                if post_frac < SOFT_FRAC:
                    why = ("outside the published FOMC table"
                           if _meeting_month(ny, nm, passed) is None else
                           "holds a decision" if not next_free else
                           "is not quoted")
                    note("_soft:" + iso,
                         f"solved off {post_frac:.0%} of the month because the "
                         f"next month {why}: this amplifies any quote error "
                         f"~{1 / post_frac:.0f}x")

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
            out[iso] = {k: round(v, 4) for k, v in probs.items()}
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
