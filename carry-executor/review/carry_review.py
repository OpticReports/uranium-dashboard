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
  fees     = perp fees (USDC) + spot fees (taken in UETH on buys, valued at
             the marking price; USDC on sells)
  price    = mark-to-market of both legs before fees: spot inventory and the
             short, marked at the same moment. For a matched hedge this is
             the spot-vs-perp basis plus any unhedged remainder.
  total    = funding - fees + price

Measurement basis: MARK-TO-MARKET at mids (report time) or hourly candle
closes (month boundaries), not at a close of the sleeve. Funding and fees
are exact. Not modelled: UETH bridge risk (Unit, 2-of-3 MPC), the
opportunity cost of the margin the short uses, taxes.

Integrity: the replayed holdings are compared with the venue's live UETH
balance and ETH position; a mismatch, a funding hour missing while the
short was held, or a fetch failure is reported as a flag, and the review
says no number should be acted on until it is explained.

Usage:
  python carry_review.py                    # previous calendar month + inception-to-date
  python carry_review.py --month 2026-10    # a given month
  python carry_review.py --month current    # month to date
  python carry_review.py --out DIR          # where review.{json,md,png} go
"""
from __future__ import annotations

import argparse
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
FUNDING_CHECK_TOL = 0.03            # received vs rate x size x price
MIN_ANN_HOURS = 168                 # annualise only after a week open
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
    funding: list          # userFunding rows for the perp coin
    rates: list            # fundingHistory rows for the perp coin
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


def resolve_spot_pair(spot_meta: dict, token: str = SPOT_TOKEN) -> str:
    toks = {t["index"]: t["name"] for t in spot_meta.get("tokens", [])}
    usdc = next((i for i, n in toks.items() if n == "USDC"), None)
    for u in spot_meta.get("universe", []):
        p = u.get("tokens") or []
        if len(p) == 2 and p[1] == usdc and toks.get(p[0]) == token:
            return u["name"]
    raise FetchError(f"no {token}/USDC pair in spotMeta")


def fetch_all(now_ms: int, chart_from_ms: int, user: str = ACCOUNT,
              post=_post, get=_get) -> VenueData:
    pair = resolve_spot_pair(post({"type": "spotMeta"}))
    fills = paginate(lambda s, e: post({"type": "userFillsByTime", "user": user,
                                        "startTime": s, "endTime": e}),
                     CARRY_START_MS, now_ms, 2000)
    fills = [f for f in fills if f.get("coin") in (PERP, pair)]
    funding = paginate(lambda s, e: post({"type": "userFunding", "user": user,
                                          "startTime": s, "endTime": e}),
                       CARRY_START_MS, now_ms, 500)
    funding = [r for r in funding if (r.get("delta") or {}).get("coin") == PERP]
    # 30 extra days so the chart's 30-day mean is warm from its first point
    rates = paginate(lambda s, e: post({"type": "fundingHistory", "coin": PERP,
                                        "startTime": s, "endTime": e}),
                     chart_from_ms - 30 * 24 * HOUR_MS, now_ms, 500)
    c_from = min(chart_from_ms, CARRY_START_MS) - 2 * 24 * HOUR_MS

    def candles(coin, iv):
        return paginate(lambda s, e: post({"type": "candleSnapshot", "req": {
            "coin": coin, "interval": iv, "startTime": s, "endTime": e}}),
            c_from, now_ms, 5000, time_key=lambda c: c["t"])
    st = post({"type": "clearinghouseState", "user": user})
    sp = post({"type": "spotClearinghouseState", "user": user})
    mids = post({"type": "allMids"})
    if not isinstance(st, dict) or "assetPositions" not in st:
        raise FetchError("clearinghouseState unreadable")
    if not isinstance(sp, dict) or "balances" not in sp:
        raise FetchError("spotClearinghouseState unreadable")
    if PERP not in mids or pair not in mids:
        raise FetchError(f"allMids missing {PERP} or {pair}")
    szi, liq = 0.0, None
    for ap in st["assetPositions"]:
        p = (ap or {}).get("position") or {}
        if p.get("coin") == PERP:
            szi = float(p["szi"])
            liq = float(p["liquidationPx"]) if p.get("liquidationPx") else None
    spot_qty = sum(float(b.get("total") or 0) for b in sp["balances"]
                   if b.get("coin") == SPOT_TOKEN)
    eng_f = get(f"{ENGINE_URL}/funding")
    try:
        cash = float(get(f"{ENGINE_URL}/status").get("cash_apy"))
    except Exception:  # noqa: BLE001
        cash = None
    return VenueData(fills, funding, rates, candles(PERP, "1h"), candles(PERP, "1d"),
                     candles(pair, "1h"), candles(pair, "1d"), pair,
                     spot_qty, szi, liq, float(mids[PERP]), float(mids[pair]),
                     eng_f, cash, now_ms, chart_from_ms)


# ---------------------------------------------------------------- replay

@dataclass
class Book:
    """Holdings and cash of the sleeve after a prefix of its fills."""
    s_gross: float = 0.0     # UETH bought - sold, before UETH-denominated fees
    fee_ueth: float = 0.0    # UETH taken as fees
    spot_cash: float = 0.0   # USDC paid for spot (-) / received (+)
    perp: float = 0.0        # ETH perp szi
    perp_cash: float = 0.0   # -sum(signed size x price) on the perp
    fees_usdc: float = 0.0   # perp fees + USDC spot fees (rebates negative)

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
        b = Book()
        for t, bk in self.points:
            if t > t_ms:
                break
            b = bk
        return b


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
                rp.flags.append(f"spot replay drift at {f['time']}: venue had "
                                f"{float(start):.6f}, replay {b.s_net:.6f}")
            b.s_gross += sz if buy else -sz
            b.spot_cash += -sz * px if buy else sz * px
            if tok == spot_token:
                b.fee_ueth += fee
            elif tok == "USDC":
                b.fees_usdc += fee
            else:
                rp.flags.append(f"unknown spot fee token {tok!r} at {f['time']}")
        elif coin == perp_coin:
            if first[coin] and start is not None and abs(float(start)) > MIN_QTY:
                p0 = float(start)
                b.perp += p0
                b.perp_cash -= p0 * px
                rp.flags.append(f"{perp_coin} perp {p0:+.4f} open before the "
                                f"first sleeve fill; counted at {px}")
            first[coin] = False
            if start is not None and abs(float(start) - b.perp) > QTY_TOL:
                rp.flags.append(f"perp replay drift at {f['time']}: venue had "
                                f"{float(start):+.6f}, replay {b.perp:+.6f}")
            signed = sz if buy else -sz
            b.perp += signed
            b.perp_cash -= signed * px
            if tok not in ("USDC", None):
                rp.flags.append(f"unknown perp fee token {tok!r} at {f['time']}")
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
    """Mark the book. price = both legs before fees; fees value the UETH
    taken as fees at the same spot price the inventory is marked at."""
    price = (b.s_gross * spot_px + b.spot_cash) + (b.perp * perp_px + b.perp_cash)
    fees = b.fees_usdc + b.fee_ueth * spot_px
    return {"price": price, "fees": fees}


# ---------------------------------------------------------------- prices

def price_at(candles: list, t_ms: int) -> float:
    """Close of the last candle that closed at or before t_ms; the first
    open if t_ms precedes every close."""
    if not candles:
        raise ValueError("no candles")
    best = None
    for c in candles:
        if c["T"] <= t_ms:
            best = c
        else:
            break
    return float(best["c"]) if best else float(candles[0]["o"])


# ---------------------------------------------------------------- windows

def month_bounds(ym: str) -> tuple[int, int]:
    y, m = (int(x) for x in ym.split("-"))
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    last = calendar.monthrange(y, m)[1]
    b = a + dt.timedelta(days=last)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def ym_of(t_ms: int) -> str:
    return dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc).strftime("%Y-%m")


def window(v: VenueData, rp: Replay, t0: int, t1: int, label: str) -> dict:
    """Sleeve results for (t0, t1]. Clipped to [CARRY_START, now]. The book
    at each end is marked at that moment (candle close, or mids at now)."""
    t0, t1 = max(t0, CARRY_START_MS), min(t1, v.now_ms)
    if t1 <= t0:
        return {"label": label, "empty": True}

    def mark(t):
        return v.px("spot", t), v.px("perp", t)

    def total_at(t):
        b = rp.at(t)
        sp, pp = mark(t)
        m = value(b, sp, pp)
        fund = sum(float(r["delta"]["usdc"]) for r in v.funding if r["time"] <= t)
        return m["price"], m["fees"], fund

    p0, f0, u0 = total_at(t0) if t0 > CARRY_START_MS else (0.0, 0.0, 0.0)
    p1, f1, u1 = total_at(t1)
    price, fees, funding = p1 - p0, f1 - f0, u1 - u0

    rows = [r for r in v.funding if t0 < r["time"] <= t1]
    on_hours = len(rows)
    notional_hours, expected = 0.0, 0.0
    for r in rows:
        d = r["delta"]
        px = v.px("perp", r["time"])
        szi, rate = float(d["szi"]), float(d["fundingRate"])
        notional_hours += abs(szi) * px
        expected += -szi * px * rate
    hours = (t1 - t0) / HOUR_MS
    # funding is paid on the hour: uptime = paid hours / hour marks in (t0, t1]
    marks = t1 // HOUR_MS - t0 // HOUR_MS
    total = funding - fees + price

    def ann(x):
        if not notional_hours or on_hours < MIN_ANN_HOURS:
            return None              # a few hours annualise noise, not a yield
        return x / notional_hours * HOURS_PER_YEAR * 100

    # opens / closes inside the window
    trips, was_on = [], is_on(rp.at(t0), v.px("spot", t0))
    for t, bk in rp.passes:
        if not (t0 < t <= t1):
            continue
        on = is_on(bk, v.px("spot", t))
        if on != was_on:
            trips.append(("open" if on else "close", t))
        was_on = on
    gaps = [abs(bk.s_net - abs(bk.perp)) * v.px("spot", t)
            for t, bk in rp.passes if t0 < t <= t1]
    return {
        "label": label, "empty": False,
        "from": iso(t0), "to": iso(t1), "hours": round(hours, 1),
        "hour_marks": marks, "on_hours": on_hours,
        "uptime_pct": round(100 * on_hours / marks, 1) if marks else None,
        "funding_usd": round(funding, 2), "fees_usd": round(fees, 2),
        "price_usd": round(price, 2), "total_usd": round(total, 2),
        "avg_notional_usd": round(notional_hours / on_hours, 0) if on_hours else None,
        "funding_yield_ann_pct": _r(ann(funding)),
        "net_yield_ann_pct": _r(ann(total)),
        "expected_funding_usd": round(expected, 2),
        "opens": sum(1 for k, _ in trips if k == "open"),
        "closes": sum(1 for k, _ in trips if k == "close"),
        "max_pass_gap_usd": round(max(gaps), 2) if gaps else 0.0,
    }


def is_on(b: Book, px: float) -> bool:
    """The sleeve is on if either leg is worth an order; UETH dust left by
    fees after a close does not count."""
    return b.s_net * px >= MIN_ON_USD or abs(b.perp) * px >= MIN_ON_USD


def _r(x, n=2):
    return None if x is None else round(x, n)


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
    if abs(b.perp - v.snap_perp_szi) > QTY_TOL:
        flags.append(f"replayed {PERP} perp {b.perp:+.6f} != venue "
                     f"{v.snap_perp_szi:+.6f}")
    # every hour the short was held should carry a funding payment
    held_hours = missing = 0
    paid = {r["time"] // HOUR_MS for r in v.funding}
    first = CARRY_START_MS // HOUR_MS + 1
    for h in range(first, v.now_ms // HOUR_MS + 1):
        if abs(rp.at(h * HOUR_MS - 1).perp) > MIN_QTY:
            held_hours += 1
            if h not in paid:
                missing += 1
    if missing > 1:
        flags.append(f"{missing} of {held_hours} hours with the short held carry "
                     f"no funding payment")
    for r in v.funding:
        if abs(rp.at(r["time"]).perp) <= MIN_QTY and abs(float(r["delta"]["szi"])) > MIN_QTY:
            flags.append(f"funding paid at {iso(r['time'])} on szi "
                         f"{r['delta']['szi']} while the replay is flat")
            break
    return flags


def proposals(month: dict, prev: dict | None, ltd: dict, v: VenueData,
              flags: list) -> list:
    """Rules that PROPOSE a change for Casey's approval. Never applied."""
    out = []
    cash = (v.cash_apy or 0.0) * 100
    if flags:
        out.append(("INVESTIGATE", "Integrity flags are open: explain them before "
                    "acting on any number in this review."))
    if (not month.get("empty") and prev and not prev.get("empty")
            and month.get("net_yield_ann_pct") is not None
            and prev.get("net_yield_ann_pct") is not None
            and month["net_yield_ann_pct"] < cash and prev["net_yield_ann_pct"] < cash):
        out.append(("PROPOSE", f"Net yield {month['net_yield_ann_pct']:.1f}% and "
                    f"{prev['net_yield_ann_pct']:.1f}% (two months) below cash "
                    f"{cash:.1f}%: consider raising the ON threshold above "
                    f"{ARM_PCT:g}% or pausing (CARRY_ENABLED=false)."))
    if not month.get("empty") and month.get("opens", 0) + month.get("closes", 0) >= 3 \
            and (month.get("uptime_pct") or 0) < 60:
        out.append(("PROPOSE", f"{month['opens']} opens / {month['closes']} closes "
                    f"with {month['uptime_pct']}% uptime: the gate is flapping; "
                    f"consider a wider band than {ARM_PCT:g}/{DISARM_PCT:g}%."))
    if not month.get("empty") and month["funding_usd"] > 20 \
            and abs(month["price_usd"]) > 0.5 * month["funding_usd"]:
        out.append(("INVESTIGATE", f"Price residual ${month['price_usd']:,.2f} is more "
                    f"than half the funding ${month['funding_usd']:,.2f}: hedge "
                    f"leakage or basis drag."))
    if not month.get("empty") and month["expected_funding_usd"] and \
            abs(month["funding_usd"] / month["expected_funding_usd"] - 1) > FUNDING_CHECK_TOL:
        out.append(("INVESTIGATE", f"Funding received ${month['funding_usd']:,.2f} vs "
                    f"${month['expected_funding_usd']:,.2f} expected from the "
                    f"published rates (>{FUNDING_CHECK_TOL:.0%} apart)."))
    if v.liq_px and v.perp_mid:
        dist = v.liq_px / v.perp_mid - 1
        if dist < 1.0:
            out.append(("PROPOSE", f"The short liquidates at {v.liq_px:,.0f}, only "
                        f"{dist:.0%} above ETH: consider a smaller sleeve."))
    eth = (v.engine_funding.get("venues") or {}).get("HL_ETH") or {}
    mean = eth.get("mean_ann_pct")
    if mean is not None and eth.get("armed") and mean < DISARM_PCT + 1:
        out.append(("NOTE", f"HL ETH 30-day funding {mean:.1f}% is within 1 point "
                    f"of the OFF line ({DISARM_PCT:g}%): a close is likely soon."))
    if (not month.get("empty") and prev and not prev.get("empty")
            and (month.get("net_yield_ann_pct") or -1e9) > cash + 4
            and (prev.get("net_yield_ann_pct") or -1e9) > cash + 4
            and v.liq_px and v.perp_mid and v.liq_px / v.perp_mid - 1 > 1.5):
        out.append(("CANDIDATE", "Two months of net yield more than 4 points over "
                    "cash with wide liquidation room. A larger sleeve COULD be "
                    "considered; history is not a forecast, and margin headroom "
                    "must be checked with a full-size BTC book. Casey's call."))
    if not out:
        out.append(("NONE", "No change proposed."))
    return out


# ---------------------------------------------------------------- chart

COL = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#8a8984",
       "grid": "#e6e5e0", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
       "s1dark": "#184f95", "on": "#eef3fa"}


def series(v: VenueData, rp: Replay) -> dict:
    """Hourly cumulative P&L components since CARRY_START, plus the hourly
    funding rate (annualised %) and its 30-day mean over the chart range."""
    hrs, fund, fees, price, total = [], [], [], [], []
    fsorted = sorted(v.funding, key=lambda r: r["time"])
    i, cum = 0, 0.0
    if rp.points:
        b0 = rp.points[0][0]
        first_pass = next(t for t, _ in rp.passes if t >= b0)
        m = value(rp.at(first_pass), v.px("spot", first_pass), v.px("perp", first_pass))
        hrs.append(first_pass)
        fund.append(0.0)
        fees.append(-m["fees"])
        price.append(m["price"])
        total.append(m["price"] - m["fees"])
    t = (CARRY_START_MS // HOUR_MS + 1) * HOUR_MS
    while t <= v.now_ms + HOUR_MS:
        tt = min(t, v.now_ms)
        while i < len(fsorted) and fsorted[i]["time"] <= tt:
            cum += float(fsorted[i]["delta"]["usdc"])
            i += 1
        b = rp.at(tt)
        m = value(b, v.px("spot", tt), v.px("perp", tt))
        hrs.append(tt)
        fund.append(cum)
        fees.append(-m["fees"])
        price.append(m["price"])
        total.append(cum - m["fees"] + m["price"])
        if tt == v.now_ms:
            break
        t += HOUR_MS
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


def chart(v: VenueData, rp: Replay, s: dict, path: str, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    def d(ts):
        return [dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc) for x in ts]

    plt.rcParams.update({"font.size": 10, "axes.edgecolor": COL["grid"],
                         "axes.labelcolor": COL["ink2"], "xtick.color": COL["ink2"],
                         "ytick.color": COL["ink2"], "axes.titlecolor": COL["ink"]})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8.2), facecolor=COL["surface"],
                                 gridspec_kw={"height_ratios": [1.15, 1], "hspace": 0.55})
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
    if x:
        lo, hi = a1.get_ylim()
        ends = spread([y[-1] for _, y, _, _ in lines], 0.06 * (hi - lo))
        for (_, y, _, _), yl in zip(lines, ends):
            a1.annotate(_money(y[-1]), (x[-1], yl), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9,
                        color=COL["ink2"], annotation_clip=False)
    a1.set_ylabel("USD, cumulative since open")
    a1.set_title("ETH carry sleeve: where the P&L came from (mark-to-market at mids)",
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
    ltd = window(v, rp, CARRY_START_MS, v.now_ms, "inception to date")
    # every calendar month since the start, for the trend table
    months, t = [], CARRY_START_MS
    while t < v.now_ms:
        ym = ym_of(t)
        a, b = month_bounds(ym)
        months.append(window(v, rp, a, b, ym))
        t = b
    now_book = rp.at(v.now_ms)
    eth = (v.engine_funding.get("venues") or {}).get("HL_ETH") or {}
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
                 "arm_pct": ARM_PCT, "disarm_pct": DISARM_PCT},
        "cash_apy_pct": None if v.cash_apy is None else round(v.cash_apy * 100, 2),
        "integrity_flags": flags,
        "proposals": [{"kind": k, "text": t} for k, t in proposals(mw, pw, ltd, v, flags)],
        "_replay": rp,
    }


def _usd(x):
    return "n/a" if x is None else f"${x:,.2f}"


def _pct(x):
    return "n/a" if x is None else f"{x:.1f}%"


def markdown(r: dict) -> str:
    m, ltd, pos, g = r["month"], r["inception_to_date"], r["position_now"], r["gate"]
    L = [f"# ETH carry sleeve: monthly review ({m['label']})",
         f"_Generated {r['generated']} - read-only - basis: mark-to-market at mids; "
         f"funding and fees exact from the venue._", ""]
    flags = r["integrity_flags"]
    L += ["**Integrity: " + ("CLEAN** (replayed holdings match the venue; no funding "
          "hour missing)." if not flags else f"{len(flags)} FLAG(S)** - do not act on "
          "the numbers until explained:"), ""]
    L += [f"- {f}" for f in flags] + ([""] if flags else [])
    L += ["## Results", "",
          "| | " + m["label"] + " | Inception to date |", "|---|---:|---:|"]

    def row(name, key, fmt):
        a = fmt(m.get(key)) if not m.get("empty") else "-"
        return f"| {name} | {a} | {fmt(ltd.get(key))} |"
    L += [row("Funding received", "funding_usd", _usd), row("Fees", "fees_usd", _usd),
          row("Price (basis + unhedged)", "price_usd", _usd),
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
          row("Worst hedge gap after a pass", "max_pass_gap_usd", _usd), ""]
    L += [f"Cash benchmark: {_pct(r['cash_apy_pct'])} (engine `cash_apy`, today's value "
          f"applied to every month).", ""]
    L += ["## Position now", "",
          f"- {pos['venue_spot_ueth']:.4f} UETH vs {pos['venue_perp_eth']:+.4f} ETH perp; "
          f"hedge gap {_usd(pos['hedge_gap_usd'])}; notional {_usd(pos['notional_usd'])}",
          f"- ETH {pos['eth_mid']:,.2f} / UETH {pos['ueth_mid']:,.2f} "
          f"(spot-perp {pos['basis_bp']:+.1f} bp)",
          f"- Short liquidates at {pos['liq_px']:,.0f} (ETH +{pos['liq_distance_pct']:.0f}%)"
          if pos["liq_px"] else "- No short open", ""]
    L += ["## Gate", "",
          f"- HL ETH 30-day funding {_pct(g['mean_ann_pct'])}, "
          f"{'ARMED' if g['armed'] else 'DISARMED'} (ON >= {g['arm_pct']:g}%, "
          f"OFF < {g['disarm_pct']:g}%)", ""]
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
          "- History, not a forecast. ETH funding ran 22% (2024), 8.5% (2025), 5.8% "
          "(2026 YTD to Oct).",
          "- Not modelled: UETH bridge risk (Unit, 2-of-3 MPC), the margin the short "
          "takes from the shared pool, taxes.", ""]
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
    v = fetch_all(now, chart_from)
    r = build(v, month)
    os.makedirs(a.out, exist_ok=True)
    rp = r.pop("_replay")
    png = os.path.join(a.out, f"carry_review_{month}.png")
    chart(v, rp, series(v, rp), png, f"Carry review - {month} (generated {r['generated']})")
    with open(os.path.join(a.out, f"carry_review_{month}.json"), "w") as fh:
        json.dump(r, fh, indent=2)
    md = markdown(r)
    with open(os.path.join(a.out, f"carry_review_{month}.md"), "w") as fh:
        fh.write(md)
    print(md)
    print(f"\nwrote {png}")
    return 2 if r["integrity_flags"] else 0


if __name__ == "__main__":
    sys.exit(main())
