"""Monthly review of the ETH carry sleeve. READ-ONLY: Hyperliquid's public
info API plus the engine's public /funding and /status. It never trades.

Casey, 2026-10-04: a monthly review that shows what the sleeve actually
earned and PROPOSES changes (gate, size) for his approval. Nothing here
changes a setting.

Everything is rebuilt from the venue's own records, not the service's
state file:
  - fills on the ETH perp and the UETH/USDC spot pair since the sleeve
    started (CARRY_START), replayed into spot and perp holdings;
  - every hourly funding payment the short received (userFunding);
  - hourly candles for marking the legs at month boundaries.

P&L of the sleeve, split three ways (all USD):
  funding  = sum of funding payments on the ETH perp (exact, from the venue)
  fees     = perp fees (USDC) + spot fees (taken in UETH on buys, booked at
             that fill's price; USDC on sells). Non-zero only in months with fills.
  price    = everything else, marked to market: the UETH actually held and the
             short, at the same moment. For a matched hedge this is the
             spot-vs-perp basis plus any unhedged remainder.
  total    = funding - fees + price

Funding rows: the venue keeps them hourly for ~8 days, then MERGES each UTC
day into one row (stamped D 00:00:00.000, nSamples = hours paid). So rows
supply only dollars. Hours open, notional and EXPECTED funding come from the
replayed short and the published hourly rates (fundingHistory), and a merged
row is booked on its own day. Windows are half-open [t0, t1) on that booking
time; a payment at a month's 00:00 mark belongs to that month.

Measurement basis: MARK-TO-MARKET at mids (report time) or hourly candle
closes (month boundaries), not at a close of the sleeve. Funding and fees
are exact. Not modelled: UETH bridge risk (Unit, 2-of-3 MPC), the
opportunity cost of the margin the short uses, taxes.

Integrity: the replayed holdings are compared with the venue's live UETH
balance and ETH position, every hour the short was held must carry one
payment (per UTC day, merged rows included), and userFunding since the
current open must equal the venue's cumFunding.sinceOpen. A failed check is
a flag: no number should be acted on until it is explained (exit code 2).
A venue that cannot be read yields an error report and exit code 3 (retry);
an engine outage or a chart failure only degrades the report (notes).

Usage:
  python carry_review.py                    # previous calendar month + inception-to-date
  python carry_review.py --month 2026-10    # a given month
  python carry_review.py --month current    # month to date
  python carry_review.py --out DIR          # where review.{json,md,png} go
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field

INFO_URL = "https://api.hyperliquid.xyz/info"
ENGINE_URL = "https://btc-paper-engine.onrender.com"
ACCOUNT = "0xAb533E69e77881D89D0357166851C9653bC551e2"   # the MAIN account
PERP = "ETH"
SPOT_TOKEN = "UETH"
# The sleeve's first fill was 2026-10-04 16:48:51Z; start one minute earlier.
CARRY_START_MS = int(dt.datetime(2026, 10, 4, 16, 47, tzinfo=dt.timezone.utc)
                     .timestamp() * 1000)
HOUR_MS = 3_600_000
HOURS_PER_YEAR = 8760.0
MIN_QTY = 1e-6                      # below this a quantity is zero
MIN_ON_USD = 11.0                   # a leg under this (the service's min order) is dust
PASS_GROUP_MS = 60_000              # fills this close together are one pass
QTY_TOL = 1e-4                      # replay vs venue tolerance (UETH / ETH)
FUNDING_CHECK_TOL = 0.01            # received vs rate x size x price (model ~0.2%)
MIN_ANN_HOURS = 168                 # annualise only after a week open
DAY_MS = 24 * HOUR_MS
PUBLISH_GRACE_MS = 120_000          # a funding row can trail its mark this long
FUNDING_FLOOR_USD = 1.0             # funding check ignores gaps below this
CUM_TOL_USD = 0.05                  # userFunding vs cumFunding.sinceOpen
CUM_TOL_SCALE = 0.001               # + this x the modelled pre-open amount removed:
                                    # candle close vs the venue's oracle is a ~3.5 bp
                                    # BIAS (max day 4.2 bp), not noise; 10 bp = 2x that
ARM_PCT, DISARM_PCT = 8.0, 5.0      # the engine's gate, for the chart


# ---------------------------------------------------------------- fetching

class FetchError(RuntimeError):
    pass


def _post(body: dict, tries: int = 4) -> object:
    """POST to the info API. The API intermittently answers `null`: retried,
    and never returned as an empty result."""
    data = json.dumps(body).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(INFO_URL, data,
                                         {"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.load(r)
            if out is not None:
                return out
            last = "null response"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(1.5 * (i + 1))
    raise FetchError(f"info {body.get('type')} failed after {tries} tries: {last}")


def _get(url: str, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(2 * (i + 1))
    raise FetchError(f"GET {url} failed: {last}")


def paginate(fetch_page, start_ms: int, end_ms: int, page_cap: int,
             time_key=lambda r: r["time"]) -> list:
    """Collect a time-ordered endpoint that returns at most `page_cap` rows
    per call, by re-requesting from the last timestamp seen. Rows already
    collected (the ones sharing that timestamp) are de-duplicated by their
    JSON form. A full page that is ONE timestamp cannot be paged past
    without losing rows, so it raises instead of dropping them silently."""
    out, seen, cur = [], set(), start_ms
    for _ in range(100_000):
        page = fetch_page(cur, end_ms)
        if not isinstance(page, list):
            raise FetchError(f"expected a list page, got {type(page).__name__}")
        for r in page:
            k = json.dumps(r, sort_keys=True)
            if k not in seen:
                seen.add(k)
                out.append(r)
        if len(page) < page_cap:
            break
        lo = min(time_key(r) for r in page)
        hi = max(time_key(r) for r in page)
        if lo == hi == cur:
            raise FetchError(f"{page_cap}+ rows share timestamp {cur}: cannot page "
                             f"past them without losing rows")
        cur = hi if hi > cur else hi + 1
    else:
        raise FetchError("pagination did not terminate")
    out.sort(key=time_key)
    return out


@dataclass
class VenueData:
    fills: list            # perp + spot fills of the sleeve, time-ordered
    funding: list          # userFunding rows for the perp coin (hourly or merged daily)
    rates: list            # fundingHistory rows for the perp coin (always hourly)
    perp_h: list           # 1h candles, perp (the venue keeps the last 5000)
    perp_d: list           # 1d candles, perp (marks older month boundaries)
    spot_h: list           # 1h candles, spot pair
    spot_d: list           # 1d candles, spot pair
    spot_pair: str         # e.g. "@151"
    snap_spot_qty: float   # venue UETH total now
    snap_perp_szi: float   # venue ETH szi now
    liq_px: float | None
    perp_mid: float
    spot_mid: float
    engine_funding: dict
    cash_apy: float | None
    now_ms: int
    chart_from_ms: int = 0
    cum_since_open: float | None = None   # venue cumFunding.sinceOpen (paid > 0)
    notes: list = field(default_factory=list)   # degraded inputs, not integrity

    def px(self, leg: str, t_ms: int) -> float:
        """Price of 'perp' or 'spot' at t_ms: mids at/after now, else the
        last hourly close, else (older than the hourly history) the last
        daily close."""
        if t_ms >= self.now_ms:
            return self.perp_mid if leg == "perp" else self.spot_mid
        h, d = (self.perp_h, self.perp_d) if leg == "perp" else (self.spot_h, self.spot_d)
        if h and h[0]["t"] <= t_ms:
            return price_at(h, t_ms)
        if d:
            return price_at(d, t_ms)
        return price_at(h, t_ms)

    def rate_at(self, mark_ms: int) -> float | None:
        """The published hourly funding rate paid at this hour mark."""
        if not hasattr(self, "_rates"):
            self._rates = {(r["time"] // HOUR_MS) * HOUR_MS: float(r["fundingRate"])
                           for r in self.rates}
        return self._rates.get(mark_ms)


def resolve_spot_pair(spot_meta: dict, token: str = SPOT_TOKEN) -> str:
    toks = {t["index"]: t["name"] for t in spot_meta.get("tokens", [])}
    usdc = next((i for i, n in toks.items() if n == "USDC"), None)
    for u in spot_meta.get("universe", []):
        p = u.get("tokens") or []
        if len(p) == 2 and p[1] == usdc and toks.get(p[0]) == token:
            return u["name"]
    raise FetchError(f"no {token}/USDC pair in spotMeta")


def clean_candles(cs: list, now_ms: int) -> list:
    """Closed candles only, one per open time. The venue re-serves the
    in-progress candle with new values, so JSON de-dup can keep two copies."""
    by_t = {}
    for c in cs:
        if c["T"] < now_ms:
            by_t[c["t"]] = c
    return [by_t[t] for t in sorted(by_t)]


def fetch_all(now_ms: int, chart_from_ms: int, user: str = ACCOUNT,
              post=_post, get=_get) -> VenueData:
    pair = resolve_spot_pair(post({"type": "spotMeta"}))
    fills = paginate(lambda s, e: post({"type": "userFillsByTime", "user": user,
                                        "startTime": s, "endTime": e}),
                     CARRY_START_MS, now_ms, 2000)
    fills = [f for f in fills if f.get("coin") in (PERP, pair)]
    # From the start of the UTC day: rows older than ~8 days come back merged,
    # one per day stamped D 00:00:00.000, and a mid-day startTime drops them.
    funding = paginate(lambda s, e: post({"type": "userFunding", "user": user,
                                          "startTime": s, "endTime": e}),
                       (CARRY_START_MS // DAY_MS) * DAY_MS, now_ms, 500)
    funding = [r for r in funding if (r.get("delta") or {}).get("coin") == PERP
               and funding_key(r) >= CARRY_START_MS]
    # fundingHistory stays hourly: it carries the expected-funding check, and
    # 30 extra days warm the chart's 30-day mean
    rates = paginate(lambda s, e: post({"type": "fundingHistory", "coin": PERP,
                                        "startTime": s, "endTime": e}),
                     min(chart_from_ms - 30 * 24 * HOUR_MS, CARRY_START_MS - DAY_MS),
                     now_ms, 500)
    c_from = min(chart_from_ms, CARRY_START_MS) - 2 * DAY_MS

    def candles(coin, iv):
        return clean_candles(paginate(lambda s, e: post({"type": "candleSnapshot", "req": {
            "coin": coin, "interval": iv, "startTime": s, "endTime": e}}),
            c_from, now_ms, 5000, time_key=lambda c: c["t"]), now_ms)
    ph, pd, sh, sd = candles(PERP, "1h"), candles(PERP, "1d"), candles(pair, "1h"), candles(pair, "1d")
    if not (ph or pd) or not (sh or sd):
        raise FetchError("no candles returned for the perp or the spot pair")
    st = post({"type": "clearinghouseState", "user": user})
    sp = post({"type": "spotClearinghouseState", "user": user})
    mids = post({"type": "allMids"})
    if not isinstance(st, dict) or "assetPositions" not in st:
        raise FetchError("clearinghouseState unreadable")
    if not isinstance(sp, dict) or "balances" not in sp:
        raise FetchError("spotClearinghouseState unreadable")
    if not isinstance(mids, dict) or PERP not in mids or pair not in mids:
        raise FetchError(f"allMids missing {PERP} or {pair}")
    szi, liq, cum = 0.0, None, None
    for ap in st["assetPositions"]:
        p = (ap or {}).get("position") or {}
        if p.get("coin") == PERP:
            szi = float(p["szi"])
            liq = float(p["liquidationPx"]) if p.get("liquidationPx") else None
            so = (p.get("cumFunding") or {}).get("sinceOpen")
            cum = float(so) if so is not None else None
    spot_qty = sum(float(b.get("total") or 0) for b in sp["balances"]
                   if b.get("coin") == SPOT_TOKEN)
    notes = []
    # the engine only decorates (gate state, cash benchmark): never fatal
    try:
        eng_f = get(f"{ENGINE_URL}/funding")
        if not isinstance(eng_f, dict):
            raise FetchError(f"/funding returned {type(eng_f).__name__}")
    except Exception as exc:  # noqa: BLE001
        eng_f = {}
        notes.append(f"engine /funding unreachable ({exc}): gate state n/a")
    try:
        cash = float(get(f"{ENGINE_URL}/status").get("cash_apy"))
        if not math.isfinite(cash):
            raise ValueError(cash)
    except Exception as exc:  # noqa: BLE001
        cash = None
        notes.append(f"engine cash_apy unavailable ({exc}): cash-relative rules "
                     f"not evaluated")
    return VenueData(fills, funding, rates, ph, pd, sh, sd, pair,
                     spot_qty, szi, liq, float(mids[PERP]), float(mids[pair]),
                     eng_f, cash, now_ms, chart_from_ms, cum, notes)


# ---------------------------------------------------------------- funding rows

def is_daily(r: dict) -> bool:
    return (r.get("delta") or {}).get("nSamples") is not None


def funding_key(r: dict) -> int:
    """The time a funding row is BOOKED at. An hourly row lands a few ms after
    its hour mark and is booked at that mark. A merged daily row (nSamples
    set, stamped D 00:00:00.000) holds the payments at marks D 00:00 .. D 23:00
    and is booked at D 23:00, inside the same UTC day and month as all of
    them. Windows are half-open [t0, t1) on this key."""
    if is_daily(r):
        return (r["time"] // DAY_MS) * DAY_MS + 23 * HOUR_MS
    return (r["time"] // HOUR_MS) * HOUR_MS


def samples(r: dict) -> int:
    """Hourly payments a row holds (a daily row's nSamples = hours held that
    day; checked against the BTC book's history, 2026-10-04)."""
    n = (r.get("delta") or {}).get("nSamples")
    return int(n) if n is not None else 1


def funding_before(v: VenueData, t_ms: int) -> float:
    return sum(float(r["delta"]["usdc"]) for r in v.funding if funding_key(r) < t_ms)


# ---------------------------------------------------------------- replay

@dataclass
class Book:
    """Holdings and cash of the sleeve after a prefix of its fills."""
    s_gross: float = 0.0       # UETH bought - sold, before UETH-denominated fees
    fee_ueth: float = 0.0      # UETH taken as fees
    fee_spot_usd: float = 0.0  # those UETH fees in USD at each fill's price
    spot_cash: float = 0.0     # USDC paid for spot (-) / received (+)
    perp: float = 0.0          # ETH perp szi
    perp_cash: float = 0.0     # -sum(signed size x price) on the perp
    fees_usdc: float = 0.0     # perp fees + USDC spot fees (rebates negative)

    @property
    def s_net(self) -> float:
        return self.s_gross - self.fee_ueth

    def copy(self) -> "Book":
        return Book(**self.__dict__)


@dataclass
class Replay:
    points: list = field(default_factory=list)   # (time_ms, Book) after each fill
    passes: list = field(default_factory=list)   # (time_ms, Book) after each pass
    flags: list = field(default_factory=list)

    def at(self, t_ms: int) -> Book:
        """The book after every fill with time <= t_ms."""
        if not hasattr(self, "_times") or len(self._times) != len(self.points):
            self._times = [t for t, _ in self.points]
        i = bisect.bisect_right(self._times, t_ms)
        return self.points[i - 1][1] if i else Book()

    def perp_open_ms(self) -> int | None:
        """When the current short was opened from flat (None if flat now)."""
        opened = None
        prev = 0.0
        for t, bk in self.points:
            if abs(bk.perp) <= MIN_QTY:
                opened = None
            elif abs(prev) <= MIN_QTY or (prev > 0) != (bk.perp > 0):
                opened = t                       # from flat, or a flip through zero
            prev = bk.perp
        return opened


def replay(fills: list, spot_pair: str, spot_token: str = SPOT_TOKEN,
           perp_coin: str = PERP) -> Replay:
    rp, b = Replay(), Book()
    first = {spot_pair: True, perp_coin: True}
    for f in sorted(fills, key=lambda x: x["time"]):
        coin, sz, px = f["coin"], float(f["sz"]), float(f["px"])
        fee, tok = float(f.get("fee") or 0.0), f.get("feeToken")
        buy = f["side"] == "B"
        start = f.get("startPosition")
        if coin == spot_pair:
            if first[coin] and start is not None and abs(float(start)) > MIN_QTY:
                # UETH held before the sleeve started: the sleeve owns it
                # (CARRY.md), so it enters at this fill's price as cost.
                s0 = float(start)
                b.s_gross += s0
                b.spot_cash -= s0 * px
                rp.flags.append(f"{spot_token} {s0:.6f} held before the first "
                                f"sleeve fill; counted at {px} as cost")
            first[coin] = False
            if start is not None and abs(float(start) - b.s_net) > QTY_TOL:
                rp.flags.append(f"spot replay drift at {iso(f['time'])}: venue had "
                                f"{float(start):.6f}, replay {b.s_net:.6f}")
            b.s_gross += sz if buy else -sz
            b.spot_cash += -sz * px if buy else sz * px
            if tok == spot_token:
                b.fee_ueth += fee
                b.fee_spot_usd += fee * px       # booked at the fill's price
            elif tok == "USDC":
                b.fees_usdc += fee
            else:
                rp.flags.append(f"unknown spot fee token {tok!r} at {iso(f['time'])}")
        elif coin == perp_coin:
            if first[coin] and start is not None and abs(float(start)) > MIN_QTY:
                p0 = float(start)
                b.perp += p0
                b.perp_cash -= p0 * px
                rp.flags.append(f"{perp_coin} perp {p0:+.4f} open before the "
                                f"first sleeve fill; counted at {px}")
            first[coin] = False
            if start is not None and abs(float(start) - b.perp) > QTY_TOL:
                rp.flags.append(f"perp replay drift at {iso(f['time'])}: venue had "
                                f"{float(start):+.6f}, replay {b.perp:+.6f}")
            signed = sz if buy else -sz
            b.perp += signed
            b.perp_cash -= signed * px
            if tok not in ("USDC", None):
                rp.flags.append(f"unknown perp fee token {tok!r} at {iso(f['time'])}")
            b.fees_usdc += fee
        else:
            continue
        rp.points.append((f["time"], b.copy()))
    # passes: a spot leg and its hedge land within seconds of each other
    for i, (t, bk) in enumerate(rp.points):
        nxt = rp.points[i + 1][0] if i + 1 < len(rp.points) else None
        if nxt is None or nxt - t > PASS_GROUP_MS:
            rp.passes.append((t, bk))
    return rp


def value(b: Book, spot_px: float, perp_px: float) -> dict:
    """Mark the book. Fees are booked at each fill's own price, so a month
    with no fills has no fees; price is everything else: the UETH actually
    held and the short, marked at the same moment (basis + unhedged part)."""
    price = (b.s_net * spot_px + b.spot_cash + b.fee_spot_usd) \
        + (b.perp * perp_px + b.perp_cash)
    fees = b.fees_usdc + b.fee_spot_usd
    return {"price": price, "fees": fees}


# ---------------------------------------------------------------- prices

def price_at(candles: list, t_ms: int) -> float:
    """Close of the last candle that closed at or before t_ms; the first
    open if t_ms precedes every close."""
    if not candles:
        raise ValueError("no candles")
    lo, hi = 0, len(candles)
    while lo < hi:                              # first candle with T > t_ms
        mid = (lo + hi) // 2
        if candles[mid]["T"] <= t_ms:
            lo = mid + 1
        else:
            hi = mid
    return float(candles[lo - 1]["c"]) if lo else float(candles[0]["o"])


# ---------------------------------------------------------------- windows

def month_bounds(ym: str) -> tuple[int, int]:
    y, m = (int(x) for x in ym.split("-"))
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    last = calendar.monthrange(y, m)[1]
    b = a + dt.timedelta(days=last)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def ym_of(t_ms: int) -> str:
    return dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc).strftime("%Y-%m")


def hour_marks(t0: int, t1: int, now_ms: int) -> list:
    """Funding hour marks m with t0 <= m < t1, after the sleeve started and
    not after now."""
    lo = max(t0, CARRY_START_MS + 1)
    first = -(-lo // HOUR_MS) * HOUR_MS
    last = min(t1 - 1, now_ms)
    return list(range(first, last + 1, HOUR_MS)) if last >= first else []


def held(rp: Replay, mark: int) -> float:
    """The short's size that a payment at this mark is paid on."""
    return rp.at(mark - 1).perp


def window(v: VenueData, rp: Replay, t0: int, t1: int, label: str) -> dict:
    """Sleeve results for [t0, t1), clipped to [CARRY_START, now]. The book
    at each end is marked at that moment (candle close, or mids at now).
    Hours open, notional and expected funding come from the replayed short
    and the published hourly rates, so they do not depend on the venue
    merging old funding rows into days."""
    t0, t1 = max(t0, CARRY_START_MS), min(t1, v.now_ms + 1)
    if t1 <= t0:
        return {"label": label, "empty": True}

    def total_at(t):
        tm = min(t, v.now_ms)
        m = value(rp.at(tm), v.px("spot", tm), v.px("perp", tm))
        return m["price"], m["fees"], funding_before(v, t)

    p0, f0, u0 = total_at(t0) if t0 > CARRY_START_MS else (0.0, 0.0, 0.0)
    p1, f1, u1 = total_at(t1)
    price, fees, funding = p1 - p0, f1 - f0, u1 - u0

    marks = hour_marks(t0, t1, v.now_ms)
    on_hours, notional_hours, expected, no_rate, daily_px = 0, 0.0, 0.0, 0, 0
    h0 = v.perp_h[0]["t"] if v.perp_h else None
    for m in marks:
        p = held(rp, m)
        if abs(p) <= MIN_QTY:
            continue
        on_hours += 1
        if h0 is None or m < h0:
            daily_px += 1
        px = v.px("perp", m)
        notional_hours += abs(p) * px
        rate = v.rate_at(m)
        if rate is None:
            no_rate += 1
        else:
            expected += -p * px * rate
    total = funding - fees + price
    # what ETH itself did over the window, and what the same notional would
    # have made or lost UNHEDGED - the yardstick for the price component
    if t0 <= CARRY_START_MS:          # from the sleeve's own entry, not a candle
        perp_fills = [f for f in v.fills if f.get("coin") == PERP]
        e0 = float(perp_fills[0]["px"]) if perp_fills else v.px("perp", t0)
    else:
        e0 = v.px("perp", t0)
    e1 = v.px("perp", min(t1, v.now_ms))
    eth_move = e1 / e0 - 1 if e0 else None
    held_any = on_hours or abs(rp.at(t0).perp) > MIN_QTY or any(
        f.get("coin") == PERP and t0 <= f["time"] < t1 for f in v.fills)
    naked = naked_long(v, rp, t0, t1) if held_any else None

    def ann(x):
        if not notional_hours or on_hours < MIN_ANN_HOURS:
            return None              # a few hours annualise noise, not a yield
        return x / notional_hours * HOURS_PER_YEAR * 100

    # opens / closes inside the window
    trips, was_on = [], is_on(rp.at(t0 - 1), v.px("spot", t0))
    for t, bk in rp.passes:
        if not (t0 <= t < t1):
            continue
        on = is_on(bk, v.px("spot", t))
        if on != was_on:
            trips.append(("open" if on else "close", t))
        was_on = on
    gaps = [abs(bk.s_net - abs(bk.perp)) * v.px("spot", t)
            for t, bk in rp.passes if t0 <= t < t1]
    return {
        "label": label, "empty": False,
        "from": iso(t0), "to": iso(min(t1, v.now_ms)),
        "hours": round((min(t1, v.now_ms) - t0) / HOUR_MS, 1),
        "hour_marks": len(marks), "on_hours": on_hours,
        "uptime_pct": round(100 * on_hours / len(marks), 1) if marks else None,
        "funding_usd": _r(funding), "fees_usd": _r(fees),
        "price_usd": _r(price), "total_usd": _r(total),
        "avg_notional_usd": round(notional_hours / on_hours, 0) if on_hours else None,
        "funding_yield_ann_pct": _r(ann(funding)),
        "net_yield_ann_pct": _r(ann(total)),
        "expected_funding_usd": round(expected, 2),
        "hours_without_rate": no_rate,
        "hours_priced_daily": daily_px,
        "eth_move_pct": _r(None if eth_move is None else eth_move * 100),
        "unhedged_equiv_usd": _r(naked),
        "opens": sum(1 for k, _ in trips if k == "open"),
        "closes": sum(1 for k, _ in trips if k == "close"),
        "max_pass_gap_usd": round(max(gaps), 2) if gaps else 0.0,
    }


def naked_long(v: VenueData, rp: Replay, t0: int, t1: int) -> float:
    """What a LONG perp of the short's size would have made over exactly the
    time the short was held in [t0, t1): the yardstick for the price line.
    Walks every perp fill at its own price (same-ms fills one at a time);
    t0 and the end are priced like price_usd (hour close, or mid now)."""
    end = min(t1, v.now_ms)
    size, px_prev, total = rp.at(t0).perp, v.px("perp", t0), 0.0
    perp_fills = sorted((f for f in v.fills if f.get("coin") == PERP), key=lambda f: f["time"])
    for i, f in enumerate(perp_fills):
        if not (t0 < f["time"] < end):
            continue
        px = float(f["px"])
        if i == 0 and f.get("startPosition") is not None and abs(size) <= MIN_QTY:
            size = float(f["startPosition"])     # a pre-sleeve perp, seeded as replay() does
            px_prev = px
        if abs(size) > MIN_QTY:
            total += abs(size) * (px - px_prev)
        size += float(f["sz"]) * (1 if f["side"] == "B" else -1)
        px_prev = px
    if abs(size) > MIN_QTY:
        total += abs(size) * (v.px("perp", end) - px_prev)
    return total


def is_on(b: Book, px: float) -> bool:
    """The sleeve is on if either leg is worth an order; UETH dust left by
    fees after a close does not count."""
    return b.s_net * px >= MIN_ON_USD or abs(b.perp) * px >= MIN_ON_USD


def _r(x, n=2):
    return None if x is None else round(x, n) + 0.0     # never -0.0 in the json


def iso(t_ms: int) -> str:
    return dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")


# ---------------------------------------------------------------- checks

def integrity(v: VenueData, rp: Replay) -> list:
    flags = list(rp.flags)
    b = rp.at(v.now_ms)
    if abs(b.s_net - v.snap_spot_qty) > QTY_TOL:
        flags.append(f"replayed {SPOT_TOKEN} {b.s_net:.6f} != venue "
                     f"{v.snap_spot_qty:.6f} (manual trade, transfer or a "
                     f"fill the replay missed)")
    if b.perp > MIN_QTY:
        flags.append(f"the {PERP} perp is LONG {b.perp:+.4f}: the sleeve is a short "
                     f"(manual trade?)")
    if abs(b.perp - v.snap_perp_szi) > QTY_TOL:
        flags.append(f"replayed {PERP} perp {b.perp:+.6f} != venue "
                     f"{v.snap_perp_szi:+.6f} (manual trade or a fill the replay missed)")
    # Every hour the short was held must carry exactly one payment. Compared
    # per UTC day, so merged daily rows (nSamples) count the same as hourly
    # ones. The newest PUBLISH_GRACE of marks is skipped: a run seconds after
    # the hour can precede that hour's row.
    cutoff = v.now_ms - PUBLISH_GRACE_MS
    held_by_day, paid_by_day = {}, {}
    for m in hour_marks(CARRY_START_MS, cutoff + 1, v.now_ms):
        if abs(held(rp, m)) > MIN_QTY:
            held_by_day[m // DAY_MS] = held_by_day.get(m // DAY_MS, 0) + 1
    for r in v.funding:
        k = funding_key(r)
        if is_daily(r) or k <= cutoff:
            paid_by_day[k // DAY_MS] = paid_by_day.get(k // DAY_MS, 0) + samples(r)
    bad = []
    for d in sorted(set(held_by_day) | set(paid_by_day)):
        h, p = held_by_day.get(d, 0), paid_by_day.get(d, 0)
        if h != p:
            bad.append(f"{dt.datetime.fromtimestamp(d * DAY_MS / 1000, dt.timezone.utc):%m-%d}"
                       f" held {h} h, paid {p}")
    if bad:
        flags.append("funding payments do not match the hours the short was held: "
                     + "; ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""))
    # the venue's own running total since the current short opened
    opened = rp.perp_open_ms()
    if v.cum_since_open is not None and opened is not None:
        got = sum(float(r["delta"]["usdc"]) for r in v.funding if funding_key(r) >= opened)
        # A merged row on the day the short (re)opened also holds that day's
        # payments on the PREVIOUS position, which sinceOpen does not count
        # (BTC book, 2026-09-18, verified live): take them out at the
        # published rates on the replayed size (candle-vs-oracle bias ~3.5 bp).
        day0 = (opened // DAY_MS) * DAY_MS
        skip, removed = False, 0.0
        # only if that merged row was actually counted in `got` (a reopen
        # after 23:00 books it before the open), and only for marks whose
        # payment is not already an hourly row of its own
        if any(is_daily(r) and funding_key(r) // DAY_MS == opened // DAY_MS
               and funding_key(r) >= opened for r in v.funding):
            hourly_marks = {funding_key(r) for r in v.funding if not is_daily(r)}
            for m in hour_marks(day0, opened, v.now_ms):
                p, rate = held(rp, m), v.rate_at(m)
                if abs(p) <= MIN_QTY or m in hourly_marks:
                    continue
                if rate is None:
                    skip = True
                    break
                removed += -p * v.px("perp", m) * rate
        got -= removed
        tol = max(CUM_TOL_USD, CUM_TOL_SCALE * abs(removed))
        # the venue settles an hour before userFunding shows it: a run in the
        # first PUBLISH_GRACE of an hour compares a settled total with a row
        # that is not out yet
        newest = (v.now_ms // HOUR_MS) * HOUR_MS
        grace = (not skip and v.now_ms - newest < PUBLISH_GRACE_MS and newest > opened
                 and abs(held(rp, newest)) > MIN_QTY
                 and newest not in {funding_key(r) for r in v.funding if not is_daily(r)})
        if grace:
            v.notes.append("cumFunding check skipped: the newest hour's payment is not "
                           "published yet")
        elif skip:
            v.notes.append("cumFunding check skipped: a published rate is missing on "
                           "the merged day the short opened")
        elif abs(got + v.cum_since_open) > tol:
            flags.append(f"funding since the short opened: ${got:,.4f} received per "
                         f"userFunding vs ${-v.cum_since_open:,.4f} per the venue's "
                         f"cumFunding.sinceOpen")
    return flags


def gate_state(v: VenueData) -> dict:
    """The engine's HL ETH gate, coerced: the engine only decorates the
    review, so a malformed answer reads as unknown, never as a crash."""
    eth = (v.engine_funding or {}).get("venues") if isinstance(v.engine_funding, dict) else None
    eth = (eth or {}).get("HL_ETH") if isinstance(eth, dict) else None
    eth = eth if isinstance(eth, dict) else {}
    x = eth.get("mean_ann_pct")
    try:
        mean = None if x is None or isinstance(x, bool) else float(x)
        if mean is not None and not math.isfinite(mean):
            mean = None
    except (TypeError, ValueError, OverflowError):
        mean = None
    armed = eth.get("armed") if isinstance(eth.get("armed"), bool) else None
    ins = eth.get("insufficient") if isinstance(eth.get("insufficient"), bool) else None
    return {"armed": armed, "mean_ann_pct": mean, "insufficient": ins}


def proposals(month: dict, prev: dict | None, ltd: dict, v: VenueData,
              flags: list) -> list:
    """Rules that PROPOSE a change for Casey's approval. Never applied."""
    out = []
    have = not month.get("empty")
    both = have and prev is not None and not prev.get("empty")
    cash = None if v.cash_apy is None else v.cash_apy * 100
    if flags:
        out.append(("INVESTIGATE", "Integrity flags are open: explain them before "
                    "acting on any number in this review."))
    if cash is not None and both \
            and month.get("net_yield_ann_pct") is not None \
            and prev.get("net_yield_ann_pct") is not None \
            and month["net_yield_ann_pct"] < cash and prev["net_yield_ann_pct"] < cash:
        out.append(("PROPOSE", f"Net yield {month['net_yield_ann_pct']:.1f}% and "
                    f"{prev['net_yield_ann_pct']:.1f}% (two months) below cash "
                    f"{cash:.1f}%: consider raising the ON threshold above "
                    f"{ARM_PCT:g}% or pausing (CARRY_ENABLED=false)."))
    if have and month.get("opens", 0) + month.get("closes", 0) >= 3 \
            and (month.get("uptime_pct") or 0) < 60:
        out.append(("PROPOSE", f"{month['opens']} opens / {month['closes']} closes "
                    f"with {month['uptime_pct']}% uptime: the gate is flapping; "
                    f"consider a wider band than {ARM_PCT:g}/{DISARM_PCT:g}%."))
    if have and month["funding_usd"] > 20 \
            and abs(month["price_usd"]) > 0.5 * month["funding_usd"]:
        out.append(("INVESTIGATE", f"Price residual {_money(month['price_usd'])} is more "
                    f"than half the funding {_money(month['funding_usd'])}: hedge "
                    f"leakage or basis drag."))
    if have:
        diff = month["funding_usd"] - month["expected_funding_usd"]
        if abs(diff) > max(FUNDING_FLOOR_USD,
                           FUNDING_CHECK_TOL * abs(month["expected_funding_usd"])):
            miss = month.get("hours_without_rate") or 0
            out.append(("INVESTIGATE", f"Funding received {_money(month['funding_usd'])} vs "
                        f"{_money(month['expected_funding_usd'])} expected from the "
                        f"published hourly rates on the replayed short"
                        + (f" ({miss} held hours had no published rate)." if miss else ".")))
    if v.liq_px and v.perp_mid and abs(v.snap_perp_szi) > MIN_QTY:
        dist = v.liq_px / v.perp_mid - 1
        if dist < 1.0:
            out.append(("PROPOSE", f"The short liquidates at {v.liq_px:,.0f}, only "
                        f"{dist:.0%} above ETH: consider a smaller sleeve."))
    eth = gate_state(v)
    mean = eth.get("mean_ann_pct")
    near_off = (mean is not None and eth.get("armed") and mean < DISARM_PCT + 1
                and not eth.get("insufficient"))
    if near_off:
        out.append(("NOTE", f"HL ETH 30-day funding {mean:.1f}% is within 1 point "
                    f"of the OFF line ({DISARM_PCT:g}%): a close is likely soon."))
    # size-up only on the carry's OWN yield (funding net of fees, not the
    # basis), and never beside an open question or a proposal to cut back
    def carry_yield(w):
        f, n = w.get("funding_yield_ann_pct"), w.get("funding_usd")
        if f is None or not n:
            return None
        return f * (1 - w["fees_usd"] / n) if n > 0 else f
    cy, py_ = (carry_yield(month), carry_yield(prev)) if both else (None, None)
    def nz(x):
        return -1e9 if x is None else x

    def residual_ok(w):
        return not (w.get("funding_usd", 0) > 20
                    and abs(w.get("price_usd", 0)) > 0.5 * w["funding_usd"])
    if cash is not None and cy is not None and py_ is not None \
            and cy > cash + 4 and py_ > cash + 4 \
            and min(nz(month.get("net_yield_ann_pct")), nz(prev.get("net_yield_ann_pct"))) >= cash \
            and min(nz(month.get("uptime_pct")), nz(prev.get("uptime_pct"))) >= 80 \
            and residual_ok(prev) and not near_off \
            and not any(k in ("INVESTIGATE", "PROPOSE") for k, _ in out) \
            and v.liq_px and v.perp_mid and v.liq_px / v.perp_mid - 1 > 1.5:
        out.append(("CANDIDATE", f"Funding net of fees {cy:.1f}% and {py_:.1f}% (two "
                    f"months) is more than 4 points over cash with wide liquidation "
                    f"room. A larger sleeve COULD be considered; history is not a "
                    f"forecast, and margin headroom must be checked with a full-size "
                    f"BTC book. Casey's call."))
    if cash is None:
        out.append(("NOTE", "Cash benchmark unavailable (engine /status): the "
                    "below-cash and size CANDIDATE rules were not evaluated."))
    if not out:
        out.append(("NONE", "No change proposed."))
    return out


# ---------------------------------------------------------------- chart

COL = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#8a8984",
       "grid": "#e6e5e0", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
       "s1dark": "#184f95", "on": "#eef3fa"}


def funding_by_mark(v: VenueData, rp: Replay) -> dict:
    """Funding per hour mark for the chart. A merged daily row is spread
    evenly over the marks of its day on which the short was held."""
    out = {}
    for r in v.funding:
        usd, k = float(r["delta"]["usdc"]), funding_key(r)
        if is_daily(r):
            day = (k // DAY_MS) * DAY_MS
            ms = [m for m in hour_marks(day, day + DAY_MS, v.now_ms)
                  if abs(held(rp, m)) > MIN_QTY] or [k]
            for m in ms:
                out[m] = out.get(m, 0.0) + usd / len(ms)
        else:
            out[k] = out.get(k, 0.0) + usd
    return out


def series(v: VenueData, rp: Replay) -> dict:
    """Hourly cumulative P&L components since CARRY_START (hourly candle
    closes; mids at the report time), plus the hourly funding rate
    (annualised %) and its 30-day mean over the chart range."""
    by_mark = funding_by_mark(v, rp)
    pts = []
    if rp.passes:
        pts.append(rp.passes[0][0])               # the open, before the first mark
    t = -(-(CARRY_START_MS + 1) // HOUR_MS) * HOUR_MS
    while t < v.now_ms:
        pts.append(t)
        t += HOUR_MS
    pts.append(v.now_ms)
    pts = sorted(set(pts))
    hrs, fund, fees, price, total = [], [], [], [], []
    marks = sorted(by_mark)
    i, cum = 0, 0.0
    for tt in pts:
        while i < len(marks) and marks[i] <= tt:
            cum += by_mark[marks[i]]
            i += 1
        m = value(rp.at(tt), v.px("spot", tt), v.px("perp", tt))
        hrs.append(tt)
        fund.append(cum)
        fees.append(-m["fees"])
        price.append(m["price"])
        total.append(cum - m["fees"] + m["price"])
    rt = [(r["time"], float(r["fundingRate"]) * HOURS_PER_YEAR * 100)
          for r in sorted(v.rates, key=lambda r: r["time"])]
    keep_t, keep_x, keep_m, win, acc = [], [], [], [], 0.0
    for ts, x in rt:
        win.append((ts, x))
        acc += x
        while win and win[0][0] <= ts - 30 * 24 * HOUR_MS:
            acc -= win.pop(0)[1]
        if ts >= v.chart_from_ms:
            keep_t.append(ts)
            keep_x.append(x)
            keep_m.append(acc / len(win))
    return {"t": hrs, "funding": fund, "fees": fees, "price": price, "total": total,
            "rate_t": keep_t, "rate": keep_x, "rate_mean30": keep_m}


RATE_CLIP = 30.0


def _money(x: float) -> str:
    if abs(x) < 0.005:                  # never print "-$0.00"
        return "$0.00"
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def spread(vals: list, gap: float) -> list:
    """Label positions near `vals` with at least `gap` between neighbours,
    order preserved (end-of-line labels that would otherwise overlap)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    pos = [vals[i] for i in order]
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + gap)
    shift = (sum(pos) - sum(vals[i] for i in order)) / len(pos) if pos else 0.0
    out = [0.0] * len(vals)
    for k, i in enumerate(order):
        out[i] = pos[k] - shift
    return out


def chart(v: VenueData, rp: Replay, s: dict, path: str, title: str,
          ltd: dict | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    def d(ts):
        return [dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc) for x in ts]

    plt.rcParams.update({"text.parse_math": False,       # "$" is money, not math
                         "font.size": 10, "axes.edgecolor": COL["grid"],
                         "axes.labelcolor": COL["ink2"], "xtick.color": COL["ink2"],
                         "ytick.color": COL["ink2"], "axes.titlecolor": COL["ink"]})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8.2), facecolor=COL["surface"],
                                 gridspec_kw={"height_ratios": [1.15, 1], "hspace": 0.68})
    for a in (a1, a2):
        a.set_facecolor(COL["surface"])
        a.grid(True, color=COL["grid"], linewidth=0.8)
        a.spines[["top", "right"]].set_visible(False)

    x = d(s["t"])
    lines = [("Funding received", s["funding"], COL["s1"], 2.0),
             ("Fees", s["fees"], COL["s2"], 2.0),
             ("Price (basis + any unhedged part)", s["price"], COL["s3"], 2.0),
             ("Sleeve total", s["total"], COL["ink"], 2.6)]
    for name, y, c, w in lines:
        a1.plot(x, y, color=c, linewidth=w, label=name, solid_capstyle="round",
                marker="o" if len(y) < 40 else None, markersize=3)
    a1.axhline(0, color=COL["muted"], linewidth=0.8)
    if ltd and ltd.get("unhedged_equiv_usd") is not None:
        a1.annotate(f"ETH {ltd['eth_move_pct']:+.1f}% since the open: a naked long of the "
                    f"same size over the hours held would have made "
                    f"{_money(ltd['unhedged_equiv_usd'])}; the sleeve's price line is "
                    f"{_money(ltd['price_usd'])}",
                    (0.5, 0.0), xycoords="axes fraction", xytext=(0, -46),
                    textcoords="offset points", ha="center", va="top", fontsize=9,
                    color=COL["ink"], annotation_clip=False)
    if x:
        lo, hi = a1.get_ylim()
        ends = spread([y[-1] for _, y, _, _ in lines], 0.06 * (hi - lo))
        for (_, y, _, _), yl in zip(lines, ends):
            a1.annotate(_money(y[-1]), (x[-1], yl), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9,
                        color=COL["ink2"], annotation_clip=False)
    a1.set_ylabel("USD, cumulative since open")
    a1.set_title("ETH carry sleeve: where the P&L came from (hourly closes; mids now)",
                 loc="left", fontsize=11.5)
    a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False,
              fontsize=9, ncol=4)
    loc1 = mdates.AutoDateLocator()
    a1.xaxis.set_major_locator(loc1)
    a1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc1))
    a1.margins(x=0.08)

    xr = d(s["rate_t"])
    a2.plot(xr, s["rate"], color=COL["s1"], linewidth=0.9, alpha=0.55,
            label="HL ETH funding, hourly (annualised)")
    a2.plot(xr, s["rate_mean30"], color=COL["s1dark"], linewidth=2.2,
            label="30-day mean (the gate's input)")
    for y, lab, dy, va in ((ARM_PCT, f"ON at {ARM_PCT:g}%", 3, "bottom"),
                           (DISARM_PCT, f"OFF below {DISARM_PCT:g}%", -3, "top")):
        a2.axhline(y, color=COL["muted"], linewidth=1, linestyle=(0, (4, 3)))
        a2.annotate(lab, (1.0, y), xycoords=("axes fraction", "data"), xytext=(4, dy),
                    textcoords="offset points", va=va, fontsize=8.5,
                    color=COL["ink2"], annotation_clip=False)
    # shade the hours the short was held
    on, start = False, None
    for t, bk in rp.points:
        held = abs(bk.perp) > MIN_QTY
        if held and not on:
            start, on = t, True
        elif not held and on:
            a2.axvspan(d([start])[0], d([t])[0], color=COL["on"], zorder=0)
            on = False
    if on:
        a2.axvspan(d([start])[0], d([v.now_ms])[0], color=COL["on"], zorder=0,
                   label="sleeve open")
    if s["rate"]:
        # spikes beyond +-RATE_CLIP would flatten the gate lines; clip, say so
        lo = max(min(min(s["rate"]), 0) - 2, -RATE_CLIP)
        hi = min(max(max(s["rate"]) + 2, ARM_PCT + 6), RATE_CLIP)
        a2.set_ylim(lo, hi)
        if max(s["rate"]) > RATE_CLIP or min(s["rate"]) < -RATE_CLIP:
            a2.annotate(f"axis clipped at +/-{RATE_CLIP:g}%; hourly extremes "
                        f"{min(s['rate']):.0f}% to {max(s['rate']):.0f}%",
                        (1.0, 0.0), xycoords="axes fraction", xytext=(-4, 4),
                        textcoords="offset points", ha="right", va="bottom",
                        fontsize=8, color=COL["ink2"])
    a2.set_ylabel("% per year")
    a2.set_title("Funding regime vs the 8% / 5% gate", loc="left", fontsize=11.5)
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False,
              fontsize=9, ncol=3)
    loc2 = mdates.AutoDateLocator()
    a2.xaxis.set_major_locator(loc2)
    a2.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc2))
    fig.suptitle(title, x=0.06, ha="left", fontsize=13, color=COL["ink"])
    fig.savefig(path, dpi=140, facecolor=COL["surface"], bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- report

def build(v: VenueData, month: str) -> dict:
    rp = replay(v.fills, v.spot_pair)
    flags = integrity(v, rp)
    m0, m1 = month_bounds(month)
    py, pm = (int(x) for x in month.split("-"))
    prev_ym = f"{py - 1}-12" if pm == 1 else f"{py}-{pm - 1:02d}"
    p0, p1 = month_bounds(prev_ym)
    mw = window(v, rp, m0, m1, month)
    pw = window(v, rp, p0, p1, prev_ym)
    ltd = window(v, rp, CARRY_START_MS, v.now_ms + 1, "inception to date")
    # every calendar month since the start, for the trend table
    months, t = [], CARRY_START_MS
    while t < v.now_ms:
        ym = ym_of(t)
        a, b = month_bounds(ym)
        months.append(window(v, rp, a, b, ym))
        t = b
    now_book = rp.at(v.now_ms)
    eth = gate_state(v)
    return {
        "generated": iso(v.now_ms), "account": ACCOUNT, "spot_pair": v.spot_pair,
        "month": mw, "previous_month": pw, "inception_to_date": ltd, "months": months,
        "position_now": {
            "spot_ueth": round(now_book.s_net, 6), "perp_eth": round(now_book.perp, 6),
            "venue_spot_ueth": v.snap_spot_qty, "venue_perp_eth": v.snap_perp_szi,
            "hedge_gap_usd": round(abs(v.snap_spot_qty - abs(v.snap_perp_szi)) * v.spot_mid, 2),
            "notional_usd": round(v.snap_spot_qty * v.spot_mid, 2),
            "eth_mid": v.perp_mid, "ueth_mid": v.spot_mid,
            "basis_bp": round((v.spot_mid / v.perp_mid - 1) * 1e4, 1),
            "liq_px": v.liq_px,
            "liq_distance_pct": round((v.liq_px / v.perp_mid - 1) * 100, 1)
            if v.liq_px else None,
        },
        "gate": {"armed": eth.get("armed"), "mean_ann_pct": eth.get("mean_ann_pct"),
                 "insufficient": eth.get("insufficient"),
                 "arm_pct": ARM_PCT, "disarm_pct": DISARM_PCT},
        "cash_apy_pct": None if v.cash_apy is None else round(v.cash_apy * 100, 2),
        "integrity_flags": flags,
        "notes": list(v.notes),
        "proposals": [{"kind": k, "text": t} for k, t in proposals(mw, pw, ltd, v, flags)],
        "_replay": rp,
    }


def _usd(x):
    if x is None:
        return "n/a"
    return _money(0.0 if abs(x) < 0.005 else x)


def _pct(x):
    return "n/a" if x is None else f"{x:.1f}%"


def markdown(r: dict) -> str:
    m, ltd, pos, g = r["month"], r["inception_to_date"], r["position_now"], r["gate"]
    L = [f"# ETH carry sleeve: monthly review ({m['label']})",
         f"_Generated {r['generated']} - read-only - basis: mark-to-market (hourly "
         f"closes at month boundaries, mids now); funding and fees exact from the venue, "
         f"fees at each fill's price._", ""]
    flags = r["integrity_flags"]
    L += ["**Integrity: " + ("CLEAN** (replayed holdings match the venue; no funding "
          "hour missing)." if not flags else f"{len(flags)} FLAG(S)** - do not act on "
          "the numbers until explained:"), ""]
    L += [f"- {f}" for f in flags] + ([""] if flags else [])
    if r.get("notes"):
        L += ["**Degraded inputs** (the venue numbers stand; these parts are n/a):", ""]
        L += [f"- {n}" for n in r["notes"]] + [""]
    L += ["## Results", "",
          "| | " + m["label"] + " | Inception to date |", "|---|---:|---:|"]

    def row(name, key, fmt):
        a = fmt(m.get(key)) if not m.get("empty") else "-"
        return f"| {name} | {a} | {fmt(ltd.get(key))} |"
    L += [row("Funding received", "funding_usd", _usd), row("Fees", "fees_usd", _usd),
          row("Price (basis + unhedged)", "price_usd", _usd),
          row("_ETH move over the window_", "eth_move_pct", _pct),
          row("_A naked long of the same size, over the hours held_", "unhedged_equiv_usd", _usd),
          row("**Sleeve total**", "total_usd", _usd),
          row("Funding yield (ann., on notional)", "funding_yield_ann_pct", _pct),
          row("**Net yield (ann., on notional)**", "net_yield_ann_pct", _pct),
          f"| _(yields shown after {MIN_ANN_HOURS} hours open; 'n/a' before)_ | | |",
          f"| Hours open / in window | {'-' if m.get('empty') else str(m['on_hours']) + ' / ' + str(m['hour_marks'])} "
          f"| {ltd.get('on_hours', 0)} / {ltd.get('hour_marks', 0)} |",
          row("Uptime", "uptime_pct", _pct),
          f"| Opens / closes | {'-' if m.get('empty') else str(m['opens']) + ' / ' + str(m['closes'])} "
          f"| {ltd.get('opens', 0)} / {ltd.get('closes', 0)} |",
          row("Expected funding (published rates)", "expected_funding_usd", _usd),
          row("Held hours with no published rate", "hours_without_rate",
              lambda x: "n/a" if x is None else str(x)),
          row("Worst hedge gap after a pass", "max_pass_gap_usd", _usd), "",
          "The hedge at a glance: compare **Price** with the naked-long line above it "
          "(same size, same hours held). A matched sleeve keeps Price near zero whatever "
          "ETH does; the earnings are the funding.", ""]
    L += [f"Cash benchmark: {_pct(r['cash_apy_pct'])} (engine `cash_apy`, today's value "
          f"applied to every month).", ""]
    L += ["## Position now", "",
          f"- {pos['venue_spot_ueth']:.4f} UETH vs {pos['venue_perp_eth']:+.4f} ETH perp; "
          f"hedge gap {_usd(pos['hedge_gap_usd'])}; notional {_usd(pos['notional_usd'])}",
          f"- ETH {pos['eth_mid']:,.2f} / UETH {pos['ueth_mid']:,.2f} "
          f"(spot-perp {pos['basis_bp']:+.1f} bp)",
          ((f"- Short liquidates at {pos['liq_px']:,.0f} (ETH {pos['liq_distance_pct']:+.0f}%)"
            if pos["liq_px"] else "- Short open; liquidation price unavailable")
           if abs(pos["venue_perp_eth"]) > MIN_QTY else "- No short open"), ""]
    L += ["## Gate", "",
          f"- HL ETH 30-day funding {_pct(g['mean_ann_pct'])}, "
          f"{'UNKNOWN' if g['armed'] is None else 'ARMED' if g['armed'] else 'DISARMED'}"
          f" (ON >= {g['arm_pct']:g}%, "
          f"OFF < {g['disarm_pct']:g}%)"
          + (" - engine: insufficient data, state frozen" if g.get("insufficient") else ""),
          ""]
    if len(r["months"]) > 1:
        L += ["## By month", "", "| Month | Funding | Fees | Price | Total | Net yield | Uptime |",
              "|---|---:|---:|---:|---:|---:|---:|"]
        for x in r["months"]:
            if not x.get("empty"):
                L.append(f"| {x['label']} | {_usd(x['funding_usd'])} | {_usd(x['fees_usd'])} "
                         f"| {_usd(x['price_usd'])} | {_usd(x['total_usd'])} "
                         f"| {_pct(x['net_yield_ann_pct'])} | {_pct(x['uptime_pct'])} |")
        L.append("")
    L += ["## Proposals (nothing is changed automatically; each needs Casey's approval)", ""]
    L += [f"- **{p['kind']}**: {p['text']}" for p in r["proposals"]] + [""]
    L += ["## Honesty box", "",
          "- Mark-to-market, not a closed result: closing costs ~11 bp more in fees plus "
          "the spot-perp spread at the time.",
          "- Yields are annualised on the sleeve's notional while it was open; a short "
          "window annualises noise.",
          "- History, not a forecast. ETH funding on HL averaged 22% in 2024, 8.5% in "
          "2025 and 5.8% in 2026 to the sleeve's open (Oct 4).",
          "- Not modelled: UETH bridge risk (Unit, 2-of-3 MPC), the margin the short "
          "takes from the shared pool, taxes.",
          "- Hours older than the venue's ~5000 hourly candles are priced at the prior "
          "daily close for notional and expected funding (`hours_priced_daily`).", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--month", default="previous",
                    help="YYYY-MM, 'previous' (default) or 'current'")
    ap.add_argument("--out", default=".")
    ap.add_argument("--now-ms", type=int, default=None)
    ap.add_argument("--chart-days", type=int, default=60)
    a = ap.parse_args(argv)
    now = a.now_ms or int(time.time() * 1000)
    today = dt.datetime.fromtimestamp(now / 1000, dt.timezone.utc)
    if a.month == "current":
        month = today.strftime("%Y-%m")
    elif a.month == "previous":
        first = today.replace(day=1)
        month = (first - dt.timedelta(days=1)).strftime("%Y-%m")
    else:
        month = a.month
    chart_from = min(CARRY_START_MS, now - a.chart_days * 24 * HOUR_MS)
    os.makedirs(a.out, exist_ok=True)
    png = os.path.join(a.out, f"carry_review_{month}.png")
    if os.path.exists(png):
        os.remove(png)                      # never send an earlier run's chart

    def not_produced(why: str, what: str, code: int) -> int:
        msg = (f"# ETH carry sleeve: monthly review ({month}) - NOT PRODUCED\n\n"
               f"{why} at {iso(now)}: {what}\n\nNo numbers are reported. "
               + ("Re-run later.\n" if code == 3 else "This is a defect: investigate.\n"))
        with open(os.path.join(a.out, f"carry_review_{month}.md"), "w") as fh:
            fh.write(msg)
        with open(os.path.join(a.out, f"carry_review_{month}.json"), "w") as fh:
            json.dump({"error": what, "generated": iso(now), "month": month,
                       "exit_code": code}, fh)
        print(msg)
        return code
    try:
        v = fetch_all(now, chart_from)
    except Exception as exc:  # noqa: BLE001 - any unreadable venue answer: retry
        return not_produced("The venue could not be read", repr(exc), 3)
    try:
        r = build(v, month)
        md_probe = markdown({**r, "notes": list(r["notes"])})   # fail before writing
    except Exception as exc:  # noqa: BLE001
        return not_produced("The review could not be computed", repr(exc), 4)
    rp = r.pop("_replay")
    del md_probe
    # a chart failure must never lose the review
    try:
        chart(v, rp, series(v, rp), png, f"Carry review - {month} (generated {r['generated']})",
              ltd=r["inception_to_date"])
    except Exception as exc:  # noqa: BLE001
        png = None
        r["notes"].append(f"chart failed: {exc!r}")
    with open(os.path.join(a.out, f"carry_review_{month}.json"), "w") as fh:
        json.dump(r, fh, indent=2)
    md = markdown(r)
    with open(os.path.join(a.out, f"carry_review_{month}.md"), "w") as fh:
        fh.write(md)
    print(md)
    print(f"\nwrote {png or 'no chart'}")
    return 2 if r["integrity_flags"] else 0


if __name__ == "__main__":
    sys.exit(main())
