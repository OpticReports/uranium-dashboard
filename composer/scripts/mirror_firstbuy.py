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
the 15:15 routine and the daily monitor), so a fund bought once stays known after the feed's history
window has moved on. Only a feed whose live book is in mode "live" teaches the set (a paper or
dry-run book's fills are not IBKR buys). When the feed cannot be read, the check runs against the
saved set and checks EVERY engine; an engine that was not live at the last save still alerts, with a
note. A fund bought since the last save can then alert once (a false positive), never the reverse.

What the mirror buys today. Composer's expected holdings ('after'). For a threshold engine whose
corridor does not trip, 'after' is Composer's current holdings, but the mirror's sleeve still trades
to the full target under its own rule (ibkr-executor mirror.py _plan, mirror_core.build_plan and
decide_sleeve):
- a pending TRANSFER naming the sleeve forces it to trade (build_plan: force=name in moved);
- pending operator CREDITS and due DIVIDENDS are added to its cash BEFORE the decision (_plan runs
  _dividends and _apply_credits first), so they raise its idle cash;
- it trades when it is in debt, holds nothing, idles more than 5% of equity in cash
  (MAX_IDLE_CASH_FRAC) - the state a rejected first buy leaves - or the largest single-asset gap
  between the target and its INVESTED weights (cash excluded) exceeds the corridor.
Reviews 2026-11-17 (re-check, then two verifiers): the feed's marks are the LAST planned session's
prices, often a day old or more, so the sleeve is re-marked here at the preview's own live prices
(the same construction the brain decides on at 15:54) when every holding has one; the feed's equity
weights are the fallback. Both readings keep a slack (1 point on the gap, half a point on idle
cash) for the minutes left before the decision. Every pending credit counts, every open dividend
receivable counts as if due today: a false positive is acceptable, a miss is not.
"""
from __future__ import annotations

import json
import math
import os
import pathlib

KNOWN_PATH = pathlib.Path(__file__).resolve().parent.parent / "results" / "mirror" / "ibkr-bought.json"
MIN_WEIGHT = 0.005          # a holding under half a percent is a rounding remnant, not a buy to warn about
IDLE_CASH_FRAC = 0.05       # mirror_core.MAX_IDLE_CASH_FRAC: a sleeve idling more than this trades to target
IDLE_SLACK = 0.005          # idle cash read up to half a point early (marks move before the decision)
DEBT_TOL_USD = 0.005        # mirror_core.DEBT_TOL_USD: cash below minus this is a debt, and a sleeve in debt trades
CORRIDOR_SLACK = 0.01       # shadow_runner.CORRIDOR_SLACK: the gap is read a point early for the same reason
DISCARD_MARKERS = ("order was discarded", "not allowed to open a position", "verify with the token")


def _num(x) -> float | None:
    """a finite real number (bools are not numbers here), else None"""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


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
    """the live book's trading, unfrozen engines; None when unknown"""
    if not feed:
        return None
    live = _live(feed)
    sleeves = (live.get("book") or {}).get("sleeves") or {}
    return {str(e) for e in (live.get("engines") or []) if not (sleeves.get(e) or {}).get("frozen")}


def queued(feed: dict | None, eng: str) -> tuple[bool, float]:
    """(forced, cash added before the decision) for one engine, from the live book's queue: a pending
    transfer naming it forces it to trade; pending credits (debits negative) and open dividend
    receivables are added to its cash first (mirror.py _plan). Conservative: a credit the executor
    might refuse, and a dividend not yet due, still count."""
    live = _live(feed) if feed else {}
    forced, add = False, 0.0
    for q in live.get("pending_requests") or []:
        if not isinstance(q, dict):
            continue
        if q.get("kind") == "transfer" and eng in (q.get("from"), q.get("to")):
            forced = True
        elif q.get("kind") == "credit" and q.get("sleeve") == eng and _num(q.get("amount")) is not None:
            add += _num(q.get("amount"))
    for d in live.get("dividends_open") or []:
        if isinstance(d, dict) and d.get("sleeve") == eng and (_num(d.get("total")) or 0) > 0:
            add += _num(d.get("total"))
    return forced, add


def sleeve_will_reach_target(sleeve: dict | None, target: dict, corridor, forced: bool = False,
                             add_cash: float = 0.0, prices: dict | None = None) -> bool:
    """mirror_core.decide_sleeve's threshold rule, read from the feed's sleeve: True when the sleeve
    will trade to its target today. Forced (a pending transfer), in debt, holding nothing, idling over
    5% of equity in cash (less IDLE_SLACK), or the largest single-asset gap between the target and its
    INVESTED weights over the corridor (less CORRIDOR_SLACK). The sleeve is re-marked at `prices` (the
    preview's live raw prices) when every holding has one, else read at the feed's marks. Unknown,
    malformed or unpriceable input: True (assume it trades)."""
    if forced:
        return True
    try:
        if not sleeve or corridor is None:
            return True
        corridor = float(corridor)
        cash = float(sleeve.get("cash") or 0) + float(add_cash or 0)
        if cash < -DEBT_TOL_USD:
            return True
        shares = sleeve.get("shares")
        inv, eq = None, None
        if isinstance(shares, dict):
            held = {str(k): float(q) for k, q in shares.items() if _num(q) and float(q) > 0}
            if not held:
                return True                                  # holds nothing: decide_sleeve trades
            px = {k: _num((prices or {}).get(k)) for k in held}
            if all(p is not None and p > 0 for p in px.values()):
                hv = sum(q * px[k] for k, q in held.items())
                if hv > 0:
                    inv = {k: q * px[k] / hv for k, q in held.items()}
                    eq = cash + hv
        if inv is None:                                      # the feed's marks: EQUITY weights, cash the remainder
            w = {str(k): float(v) for k, v in (sleeve.get("weights") or {}).items() if _num(v) and float(v) > 0}
            if not w:
                return True
            tot = sum(w.values())
            inv = {k: v / tot for k, v in w.items()}
            eq = float(sleeve.get("equity") or 0) + float(add_cash or 0)
        if eq is None or eq <= 0:
            return True
        if cash / eq > IDLE_CASH_FRAC - IDLE_SLACK:
            return True
        gap = max(abs(float(target.get(t, 0) or 0) - inv.get(t, 0.0)) for t in set(target) | set(inv))
        return gap > corridor - CORRIDOR_SLACK
    except (TypeError, ValueError, AttributeError, ZeroDivisionError):
        return True


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
    """atomic write; on failure the temporary file is removed and the error raised"""
    p = path or KNOWN_PATH
    tmp = p.with_suffix(".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"bought": sorted(known), "saved": saved,
                                   "engines": sorted(engines) if engines is not None else None}, indent=1) + "\n")
        os.replace(tmp, p)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _new(weights: dict, known: set[str]) -> list[str]:
    return sorted(t for t, w in (weights or {}).items()
                  if isinstance(w, (int, float)) and not isinstance(w, bool) and w >= MIN_WEIGHT and t not in known)


def first_buy_alerts(rows: list[dict], known: set[str], feed: dict | None = None, at: str = "15:50",
                     engines: set[str] | None = None, prices: dict | None = None,
                     saved_on: str | None = None) -> tuple[list[str], list[str]]:
    """(lines, alerts): one alert per engine about to buy a fund outside `known`. Rows that are not an
    engine's preview (the GATE row, unavailable engines) are skipped. With a feed, engines the live
    book does not trade (paper-only under staged rollout, or frozen) are skipped. Without one, every
    engine is checked, and an engine outside `engines` (those live at the last save) alerts with a
    note. `at`: the decision time for the message (12:50 on a half-day). `prices`: the preview's live
    raw prices, to re-mark threshold sleeves."""
    strict = live_engines(feed) if feed else None
    sleeves = ((_live(feed).get("book") or {}).get("sleeves") or {}) if feed else {}
    lines, alerts = [], []
    for r in rows or []:
        eng = r.get("engine")
        if r.get("status") != "ok" or eng in (None, "GATE") or (strict is not None and eng not in strict):
            continue
        new = _new(r.get("after"), known)
        corridor = r.get("corridor")
        if corridor is not None:
            extra = [t for t in _new(r.get("target"), known) if t not in new]
            if extra:
                forced, add = queued(feed, eng)
                if feed is None or sleeve_will_reach_target(sleeves.get(eng), r.get("target") or {}, corridor,
                                                            forced, add, prices):
                    new = sorted(set(new) | set(extra))
                else:
                    lines.append(f"first-buy check: {eng}'s target holds {', '.join(extra)} (never bought on IBKR); "
                                 f"its own rule does not trade it today, so no buy is expected")
        if new:
            note = ""
            if strict is None and engines is not None and eng not in engines:
                note = (f" ({eng} was not trading live" + (f" on {saved_on}" if saved_on else "")
                        + ": ignore this if it is still paper-only.)")
            alerts.append(f"FIRST BUY ON IBKR — {eng} is set to buy {', '.join(new)} at ~{at}, which the live "
                          f"mirror account has never bought. IBKR may reject a first buy until you verify a token it "
                          f"emails you (2026-11-16: ZVOL). Check your email / Client Portal now; a rejected buy leaves "
                          f"that part of the sleeve in cash until its rule next trades." + note)
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
                  why: str | None = None, today: str | None = None, at: str = "15:50",
                  prices: dict | None = None) -> tuple[list[str], list[str]]:
    """(lines, alerts) for the 15:15 preview. A readable feed with a live book in mode "live" teaches
    the persisted set. A readable feed with NO live book (DRY_RUN, no credentials): nothing can be
    sent to IBKR, so one line and no alerts. An unread feed, or a live book not in live mode, falls
    back to the saved set and checks every engine."""
    saved, saved_on, saved_eng = load_known(path)
    if feed is not None and "live" not in ((feed.get("books") or {})):
        return ["first-buy check: the executor has no live IBKR book: nothing to check"], []
    if not is_live_book(feed):
        reason = why or ("the live book is not in live mode" if feed else "the mirror feed was not read")
        if not saved:
            return [f"first-buy check: {reason}, and no saved set: funds new to IBKR not checked"], []
        lines, alerts = first_buy_alerts(rows, saved, None, at, saved_eng, prices, saved_on)
        return [f"first-buy check: {reason}; checked against the saved set" + (f" of {saved_on}" if saved_on else "")
                + "; every engine checked"] + lines, alerts
    known = saved | known_from_feed(feed)
    eng = live_engines(feed)
    out = []
    stamp = max([d for d in (today, saved_on) if d], default=None)        # the saved date never moves back
    if save and (known != saved or saved_on is None or eng != saved_eng or stamp != saved_on):
        try:
            save_known(known, path, stamp, eng)
        except OSError as e:
            out.append(f"first-buy check: the set of funds bought was not saved ({type(e).__name__})")
    lines, alerts = first_buy_alerts(rows, known, feed, at, prices=prices)
    return out + lines, alerts
