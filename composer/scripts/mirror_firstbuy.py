#!/usr/bin/env python3
"""Funds the live IBKR mirror is about to buy for the FIRST time (read-only; never trades).

Why (2026-11-16): the mirror's first ever ZVOL buy was rejected by IBKR with only
"[202] Order Canceled - reason:Order was discarded." over the API. The real reason, visible only in
Client Portal, was "Rejected by System: Not allowed to open a position: To accept your order in this
security, please login to Client Portal and verify with the token we emailed you." Permissions were
fine (Stocks, Complex or Leveraged ETPs). IBKR can ask for that one-time verification the first time
an account opens a security, and the API never carries its words. So the only early warning is to
notice, before the decision, that a symphony is about to rotate into a fund the account has never
bought, and say so at the 15:15 preview while there are ~35 minutes to verify.

Two surfaces:
- preview_check(rows, feed): the 15:15 preview's lines and alerts (preclose.py) for each LIVE, unfrozen
  engine whose holdings after today's decision include a fund outside the known set.
- discard_hint(orders): one sentence for the parity UNFILLED alert (mirror_parity.py) when an order
  died with IBKR's bare "discarded" reason.

The known set (funds the live book has bought or holds) is the union of the feed's current positions,
every filled BUY in its history, and a persisted set (results/mirror/ibkr-bought.json, committed by
the daily monitor's add of composer/results/mirror/), so a fund bought once stays known after the
feed's history window has moved on. Only a feed whose live book is in mode "live" teaches the set
(a paper or dry-run book's fills are not IBKR buys). When the feed cannot be read, the check runs
against the saved set alone: a fund bought since the last save can then alert once (a false
positive), never the reverse.

What the mirror buys today (review 2026-11-17, D3; re-check 2026-11-17): Composer's expected
holdings ('after'). For a threshold engine whose corridor does not trip, 'after' is Composer's
current holdings, but the mirror's sleeve still trades to the full target under its own rule
(mirror_core.decide_sleeve): it idles more than 5% of equity in cash (MAX_IDLE_CASH_FRAC) - the state a
rejected first buy leaves - or is in debt, or holds nothing, or the largest single-asset gap between
the target and its INVESTED weights (cash excluded) exceeds the corridor. The feed publishes EQUITY
weights (cash is the remainder), so they are renormalised to invested weights here, and the corridor
is read with preclose's 1-point slack because the feed's marks are a session old at 15:15 (a false
positive is acceptable; a miss is not). For a corridor row the target's funds are checked when the
sleeve will trade.
"""
from __future__ import annotations

import json
import os
import pathlib

KNOWN_PATH = pathlib.Path(__file__).resolve().parent.parent / "results" / "mirror" / "ibkr-bought.json"
MIN_WEIGHT = 0.005          # a holding under half a percent is a rounding remnant, not a buy to warn about
IDLE_CASH_FRAC = 0.05       # mirror_core.MAX_IDLE_CASH_FRAC: a sleeve idling more than this trades to target
DEBT_TOL_USD = 0.005        # mirror_core.DEBT_TOL_USD: cash below minus this is a debt, and a sleeve in debt trades
CORRIDOR_SLACK = 0.01       # shadow_runner.CORRIDOR_SLACK: the feed's marks are a session old at 15:15
DISCARD_MARKERS = ("order was discarded", "not allowed to open a position", "verify with the token")


def _live(feed: dict) -> dict:
    books = (feed or {}).get("books") or {}
    return books.get("live") or {}


def is_live_book(feed: dict | None) -> bool:
    return bool(feed) and _live(feed).get("mode") == "live"


def known_from_feed(feed: dict) -> set[str]:
    """funds the live book holds now or has a filled BUY of in the feed's history"""
    live = _live(feed)
    out = {str(t) for t, q in ((live.get("book") or {}).get("positions") or {}).items() if q}
    for row in live.get("history") or []:
        for o in row.get("orders") or []:
            if o.get("side") == "BUY" and (o.get("filled") or 0) > 0 and o.get("symbol"):
                out.add(str(o["symbol"]))
    return out


def live_engines(feed: dict | None) -> set[str] | None:
    """the live book's trading, unfrozen engines; None when unknown (no feed: every row is checked)"""
    if not feed:
        return None
    live = _live(feed)
    sleeves = (live.get("book") or {}).get("sleeves") or {}
    return {str(e) for e in (live.get("engines") or []) if not (sleeves.get(e) or {}).get("frozen")}


def _sleeve_will_reach_target(sleeve: dict | None, target: dict, corridor: float | None) -> bool:
    """mirror_core.decide_sleeve's threshold rule, read from the feed: the sleeve trades to target when
    it is in debt, holds nothing, idles over 5% of equity in cash, or the largest single-asset gap
    between the target and its INVESTED weights exceeds the corridor (read with a 1-point slack).
    Unknown sleeve or corridor: assume it trades."""
    if not sleeve or corridor is None:
        return True
    eq, cash = float(sleeve.get("equity") or 0), float(sleeve.get("cash") or 0)
    w = {str(k): float(v) for k, v in (sleeve.get("weights") or {}).items() if isinstance(v, (int, float)) and v > 0}
    if cash < -DEBT_TOL_USD or not w:
        return True
    if eq > 0 and cash / eq > IDLE_CASH_FRAC:
        return True
    tot = sum(w.values())
    inv = {k: v / tot for k, v in w.items()}
    gap = max(abs(float(target.get(t, 0) or 0) - inv.get(t, 0.0)) for t in set(target) | set(inv))
    return gap > float(corridor) - CORRIDOR_SLACK


def load_known(path: pathlib.Path | None = None) -> tuple[set[str], str | None, set[str] | None]:
    """(funds bought, the date saved, the live unfrozen engines then). Anything unreadable or of the
    wrong shape is an empty set (the check then says so), never an exception."""
    p = path or KNOWN_PATH
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return set(), None, None
    if not isinstance(data, dict) or not isinstance(data.get("bought"), list):
        return set(), None, None
    saved = data.get("saved") if isinstance(data.get("saved"), str) else None
    eng = data.get("engines")
    engines = {str(e) for e in eng} if isinstance(eng, list) else None
    return {str(t) for t in data["bought"] if isinstance(t, str)}, saved, engines


def save_known(known: set[str], path: pathlib.Path | None = None, saved: str | None = None,
               engines: set[str] | None = None) -> None:
    p = path or KNOWN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"bought": sorted(known), "saved": saved,
                               "engines": sorted(engines) if engines is not None else None}, indent=1) + "\n")
    os.replace(tmp, p)


def _new(weights: dict, known: set[str]) -> list[str]:
    return sorted(t for t, w in (weights or {}).items()
                  if isinstance(w, (int, float)) and w >= MIN_WEIGHT and t not in known)


def first_buy_alerts(rows: list[dict], known: set[str], feed: dict | None = None, at: str = "15:50",
                     engines: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(lines, alerts): one alert per engine about to buy a fund outside `known`. Rows that are not an
    engine's preview (the GATE row, unavailable engines) and engines the live book does not trade
    (paper-only under staged rollout, or frozen; from the feed, else `engines`) are skipped. `at`: the
    decision time for the message (12:50 on a half-day)."""
    engines = live_engines(feed) if feed else engines
    sleeves = ((_live(feed).get("book") or {}).get("sleeves") or {}) if feed else {}
    lines, alerts = [], []
    for r in rows or []:
        eng = r.get("engine")
        if r.get("status") != "ok" or eng in (None, "GATE") or (engines is not None and eng not in engines):
            continue
        new = _new(r.get("after"), known)
        corridor = r.get("corridor")
        if corridor is not None:
            extra = [t for t in _new(r.get("target"), known) if t not in new]
            if extra:
                if _sleeve_will_reach_target(sleeves.get(eng), r.get("target") or {}, corridor):
                    new = sorted(set(new) | set(extra))
                else:
                    lines.append(f"first-buy check: {eng}'s target holds {', '.join(extra)} (never bought on IBKR); "
                                 f"its corridor does not trip today, so no buy is expected")
        if new:
            alerts.append(f"FIRST BUY ON IBKR — {eng} is set to buy {', '.join(new)} at ~{at}, which the live "
                          f"mirror account has never bought. IBKR may reject a first buy until you verify a token it "
                          f"emails you (2026-11-16: ZVOL). Check your email / Client Portal now; a rejected buy leaves "
                          f"that part of the sleeve in cash until its rule next trades.")
    return lines, alerts


def discard_hint(orders: list[dict]) -> str:
    """'' unless an unfilled order died with IBKR's bare 'discarded' reason (or the portal's own words)"""
    hit = sorted({str(o.get("symbol")) for o in orders or []
                  if (o.get("filled") or 0) < (o.get("qty") or 0)
                  and any(m in str(o.get("how") or "").lower() for m in DISCARD_MARKERS)})
    if not hit:
        return ""
    return (f" IBKR discarded the {', '.join(hit)} order without a reason over the API: this can be its one-time "
            f"verification for a security the account has not opened before (2026-11-16: ZVOL). Open the order's (i) "
            f"in Client Portal (Orders & Trades): if it asks for the emailed token, verify it; the sleeve keeps that "
            f"cash until its rule next trades.")


def preview_check(rows: list[dict], feed: dict | None, path: pathlib.Path | None = None, save: bool = True,
                  why: str | None = None, today: str | None = None, at: str = "15:50") -> tuple[list[str], list[str]]:
    """(lines, alerts) for the 15:15 preview. A readable feed with a live book in mode "live" teaches
    the persisted set. A readable feed with NO live book (DRY_RUN, no credentials): nothing can be
    sent to IBKR, so one line and no alerts. An unread feed, or a live book not in live mode, falls
    back to the saved set and the engines saved with it."""
    saved, saved_on, saved_eng = load_known(path)
    if feed is not None and "live" not in ((feed.get("books") or {})):
        return ["first-buy check: the executor has no live IBKR book: nothing to check"], []
    if not is_live_book(feed):
        reason = why or ("the live book is not in live mode" if feed else "the mirror feed was not read")
        if not saved:
            return [f"first-buy check: {reason}, and no saved set: funds new to IBKR not checked"], []
        lines, alerts = first_buy_alerts(rows, saved, None, at, saved_eng)
        return [f"first-buy check: {reason}; checked against the saved set" + (f" of {saved_on}" if saved_on else "")] + lines, alerts
    known = saved | known_from_feed(feed)
    eng = live_engines(feed)
    if save and (known != saved or saved_on is None or eng != saved_eng):
        try:
            save_known(known, path, today or saved_on, eng)
        except OSError:
            pass
    return first_buy_alerts(rows, known, feed, at)
