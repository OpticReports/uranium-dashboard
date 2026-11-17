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

What the mirror buys today. Composer's expected holdings ('after'). A DAILY engine (by the manifest
OR the executor's own published rule: either one saying daily wins) trades to its target every
session, so the target's funds count too. For a threshold engine whose corridor does not trip,
'after' is Composer's current holdings, but the mirror's sleeve still trades to the full target
under its own rule (ibkr-executor mirror.py _apply_repairs and _plan, mirror_core.build_plan and
decide_sleeve):
- a pending TRANSFER naming the sleeve forces it to trade (build_plan: force=name in moved); a
  pending ADJUST naming it, or any pending RESOLVE, is treated the same way (conservative);
- pending operator CREDITS and due DIVIDENDS reach its cash BEFORE the decision, but the executor
  may refuse a credit or debit, or skip a receivable not yet due or not yet arrived. Its real cash
  therefore lies in an interval: the base cash plus every debit (lo) to the base cash plus every
  credit and receivable (hi). Debt is tested at lo and idle cash at hi (round-4 verifier: one summed
  figure hid a debt the executor then repaired by trading);
- it trades when it is in debt, holds nothing, idles more than 5% of equity in cash
  (MAX_IDLE_CASH_FRAC) - the state a rejected first buy leaves - or the largest single-asset gap
  between the target and its INVESTED weights (cash excluded) exceeds the corridor.
The feed's marks are the LAST planned session's prices, often a day old or more, so the sleeve is
read twice - at the feed's marks and re-marked at the preview's own live prices (fund by fund; a fund
with no live price keeps its implied mark) - and counted as trading if EITHER reading trades. Both
keep a slack (1 point on the gap, half a point on idle cash) for the minutes left.

Alternatives (round-4 verifiers): the preview's own other outcomes - a flip of the closest decision
('flip.instead'), a market move of 1-2 sigma ('market'), and for HG the gate's two sides when the
gate is within reach - are checked too. 2026-11-06: HARV's 15:16 preview ended in PULS 1.0, 'could
flip' (SPY -0.36%, 1.6 sigma) to {PULS .64, ZVOL .36}, and Composer took it. They go in ONE combined
"FIRST BUY ON IBKR (if a call flips)" alert, naming what flips each one, except a 'firm' call's flip
and market alternatives, which are a line only; HG's gate sides push whenever the gate is within 3
sigma, flipping or at an unknown distance, and on a firm call are read first so the firm flip's line
never swallows them. (Round 5: of 6 sessions with an alternative first buy, the one that happened
was a 'could flip'; the firm rule quiets 1 of the 6 - 16 -> 15 FIRST BUY pushes in 12 sessions, one
15:15 run per session with the 2026-11-16 bought set and a feed without sleeve data; 20 -> 19 over
all 14 runs. On 2026-11-10 a 'firm' SLEEVE showed
a 2-sigma SHY flip to {BOXX .5, UVXY .5} that SHY crossed only by the close, after the decision,
and Composer stayed in BOXX.) For a daily engine
an alternative is a target, read with floor 0; for a threshold engine it is Composer's end state,
not the sleeve's alternative target, so a small alternative change inside Composer's corridor that
the mirror sleeve trades to on its own rule is not seen (documented limit).

What the owner can do with it: IBKR asked for the verification on 2026-11-16 only after an order
was placed ("To accept your order in this security ... verify with the token we emailed you").
Whether a fund can be cleared BEFORE its first order is asked of IBKR. Until then the alert means:
watch for IBKR's email after the decision, verify it in Client Portal, and the sleeve buys it when
its rule next trades (a daily sleeve at the next session).

A false positive is acceptable; a miss is not. Known limits: a request queued in the last minutes
before 15:15 may still be in the executor's inbox (not yet in the feed); a split dated today is
applied at the decision; a target fund whose allocation is under one share is never bought.
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


def queued(feed: dict | None, eng: str) -> tuple[bool, float, float]:
    """(forced, lo, hi) for one engine, from the live book's queue. forced: a pending transfer naming
    it (build_plan forces it), a pending adjust naming it, or any pending resolve. lo: the sum of its
    pending DEBITS (credits < 0); hi: the sum of its pending credits > 0 plus its open dividend
    receivables. The executor may refuse or skip any of them, so its cash at the decision lies in
    [cash + lo, cash + hi]: debt is tested at the low end, idle cash at the high end."""
    live = _live(feed) if feed else {}
    forced, lo, hi = False, 0.0, 0.0
    for q in live.get("pending_requests") or []:
        if not isinstance(q, dict):
            continue
        kind = q.get("kind")
        if kind == "transfer" and eng in (q.get("from"), q.get("to")):
            forced = True
        elif kind == "adjust" and q.get("sleeve") == eng:
            forced = True
        elif kind == "resolve":
            forced = True
        elif kind == "credit" and q.get("sleeve") == eng and _num(q.get("amount")) is not None:
            a = _num(q.get("amount"))
            if a < 0:
                lo += a
            else:
                hi += a
    for d in live.get("dividends_open") or []:
        if isinstance(d, dict) and d.get("sleeve") == eng and (_num(d.get("total")) or 0) > 0:
            hi += _num(d.get("total"))
    return forced, lo, hi


def _reading_trades(inv: dict, eq: float, cash: float, target: dict, corridor: float) -> bool:
    if eq <= 0:
        return True
    if cash / eq > IDLE_CASH_FRAC - IDLE_SLACK:
        return True
    gap = max(abs(float(target.get(t, 0) or 0) - inv.get(t, 0.0)) for t in set(target) | set(inv))
    return gap > corridor - CORRIDOR_SLACK


def sleeve_will_reach_target(sleeve: dict | None, target: dict, corridor, forced: bool = False,
                             lo: float = 0.0, hi: float = 0.0, prices: dict | None = None) -> bool:
    """mirror_core.decide_sleeve's threshold rule, read from the feed's sleeve: True when the sleeve
    may trade to its target today. Forced; in debt at the LOW end of its cash interval (cash + lo); no
    holdings; or, at the HIGH end (cash + hi), idle cash over 5% of equity (less IDLE_SLACK) or the
    largest single-asset gap between the target and its INVESTED weights over the corridor (less
    CORRIDOR_SLACK) - at the feed's marks OR re-marked at `prices` (the preview's live raw prices, fund
    by fund; a fund with none keeps its implied mark). Unknown, malformed or unpriceable input: True."""
    if forced:
        return True
    try:
        if not sleeve or corridor is None:
            return True
        corridor = float(corridor)
        base = float(sleeve.get("cash") or 0)
        if base + float(lo or 0) < -DEBT_TOL_USD:
            return True
        cash = base + float(hi or 0)
        weights = sleeve.get("weights") or {}
        shares = sleeve.get("shares")
        held = None
        if isinstance(shares, dict):
            held = {str(k): float(q) for k, q in shares.items() if _num(q) and float(q) > 0}
            if not held:
                return True                                  # holds nothing: decide_sleeve trades
        readings = []
        w = {str(k): float(v) for k, v in weights.items() if _num(v) and float(v) > 0}
        if w:                                                # the feed's marks: EQUITY weights, cash the remainder
            tot = sum(w.values())
            readings.append(({k: v / tot for k, v in w.items()}, float(sleeve.get("equity") or 0) + float(hi or 0)))
        if held and prices:                                  # re-marked at the preview's prices, fund by fund
            feq = float(sleeve.get("equity") or 0)
            px = {}
            for k, q in held.items():
                p = _num((prices or {}).get(k))
                if p is not None and p > 0:
                    px[k] = p
                elif _num(weights.get(k)) and feq > 0:
                    px[k] = float(weights[k]) * feq / q      # its implied mark
            if len(px) == len(held):
                hv = sum(q * px[k] for k, q in held.items())
                if hv > 0:
                    readings.append(({k: q * px[k] / hv for k, q in held.items()}, cash + hv))
        if not readings:
            return True
        return any(_reading_trades(inv, eq, cash, target, corridor) for inv, eq in readings)
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


def _new(weights, known: set[str], floor: float = MIN_WEIGHT) -> list[str]:
    """funds in `weights` outside `known`: an end state's remnant under `floor` is ignored; a TARGET is
    read with floor 0 (any weight there is a buy)"""
    if not isinstance(weights, dict):
        return []
    return sorted(t for t, w in weights.items()
                  if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0 and w >= floor and t not in known)


def _alternatives(r: dict) -> list[tuple[dict, str, bool]]:
    """the preview's other outcomes for one engine row, as (holdings, what flips it, gate side): the
    closest flip's end state, the 1-2 sigma market end states, and any 'alts' attached by the caller
    (HG: the gate's two sides, attached only when the gate is within reach)"""
    out = []
    fl = r.get("flip")
    if isinstance(fl, dict) and isinstance(fl.get("instead"), dict):
        mv, sg = _num(fl.get("move")), _num(fl.get("sigma"))
        out.append((fl["instead"], f"{fl.get('ticker') or 'a ticker'}"
                    + (f" {mv:+.2%}" if mv is not None else "") + (f", {sg:g} sigma" if sg is not None else ""), False))
    mk = r.get("market")
    if isinstance(mk, dict):
        out += [(v, f"market {k if str(k)[:1] in '+-' else '+' + str(k)} sigma", False)
                for k, v in mk.items() if isinstance(v, dict)]
    out += [(x, "SPY across its 200-day", True) for x in (r.get("alts") or []) if isinstance(x, dict)]
    return out


def first_buy_alerts(rows: list[dict], known: set[str], feed: dict | None = None, at: str = "15:50",
                     engines: set[str] | None = None, prices: dict | None = None,
                     saved_on: str | None = None) -> tuple[list[str], list[str]]:
    """(lines, alerts): one alert per engine about to buy a fund outside `known`, plus ONE combined
    alert for funds only the preview's alternative outcomes would buy. Rows that are not an engine's
    preview (the GATE row) are skipped; a live engine whose preview is unavailable gets a line. With a
    feed, engines the live book does not trade (paper-only under staged rollout, or frozen) are
    skipped. Without one, every engine is checked, and an engine outside `engines` (those live at the
    last save) alerts with a note. `at`: the decision time (12:50 on a half-day). `prices`: the
    preview's live raw prices, to re-mark threshold sleeves."""
    strict = live_engines(feed) if feed else None
    sleeves = ((_live(feed).get("book") or {}).get("sleeves") or {}) if feed else {}
    lines, alerts, maybe = [], [], []
    for r in rows or []:
        eng = r.get("engine")
        if eng in (None, "GATE") or (strict is not None and eng not in strict):
            continue
        if r.get("status") != "ok":
            lines.append(f"first-buy check: {eng} NOT checked (its preview is unavailable"
                         + (f": {r.get('note')}" if r.get("note") else "") + ")")
            continue
        note = ""
        if strict is None and engines is not None and eng not in engines:
            note = (f" ({eng} was not trading live" + (f" on {saved_on}" if saved_on else "")
                    + ": ignore this if it is still paper-only.)")
        corridor = r.get("corridor")
        fs = sleeves.get(eng) if isinstance(sleeves.get(eng), dict) else None
        if fs is not None and fs.get("rule") in ("daily", "threshold"):   # the executor's own rule: daily wins
            if fs["rule"] == "daily" or not _num(fs.get("corridor")):         # (a threshold with no corridor trades daily)
                corridor = None
            elif corridor is not None:
                corridor = min(float(corridor), float(fs["corridor"]))
        new = _new(r.get("after"), known)
        if corridor is None:                                 # a daily sleeve trades to its target every session
            new = sorted(set(new) | set(_new(r.get("target"), known, 0.0)))
        else:
            extra = [t for t in _new(r.get("target"), known, 0.0) if t not in new]
            if extra:
                forced, lo, hi = queued(feed, eng)
                if feed is None or sleeve_will_reach_target(fs, r.get("target") or {}, corridor,
                                                            forced, lo, hi, prices):
                    new = sorted(set(new) | set(extra))
                else:
                    lines.append(f"first-buy check: {eng}'s target holds {', '.join(extra)} (never bought on IBKR); "
                                 f"its own rule does not trade it today, so no buy is expected")
        if new:
            alerts.append(f"FIRST BUY ON IBKR — {eng} is set to buy {', '.join(new)} at ~{at}, which the live "
                          f"mirror account has never bought. IBKR may hold a first order for a one-time verification "
                          f"(2026-11-16: ZVOL): it then emails you a token - verify it in Client Portal (Orders & "
                          f"Trades, the order's (i)) and the sleeve buys {'it' if len(new) == 1 else 'them'} when "
                          f"its rule next trades (a daily sleeve at the next session); until then that part stays in "
                          f"cash." + note)
        floor = 0.0 if corridor is None else MIN_WEIGHT     # a daily engine's alternative is a target
        label = r.get("label") or "alternative"
        seen = set(new)
        for holdings, why, gate_side in sorted(_alternatives(r), key=lambda a: label == "firm" and not a[2]):
            # a firm call: gate sides first, so a firm flip's line never swallows a gate side's push;
            # otherwise the preview's own order: its closest one-ticker flip, then the market moves as
            # stored (-2 before -1), then the gate sides
            funds = [t for t in _new(holdings, known, floor) if t not in seen]
            if not funds:
                continue
            seen |= set(funds)
            if label == "firm" and not gate_side:              # round 5: a firm call's alternative is a line
                lines.append(f"first-buy check: {eng} could buy {', '.join(funds)} if {why} (a firm call: not pushed)")
            else:
                maybe.append(f"{eng} {', '.join(funds)} ({label}; {why})" + note)
    if maybe:
        alerts.append(f"FIRST BUY ON IBKR (if a call flips) — at ~{at}: " + "; ".join(maybe) + ". The preview's "
                      f"alternative outcome would buy these, and the live mirror account has never bought them. If "
                      f"one is bought and IBKR holds it for a one-time verification, it emails you a token: verify "
                      f"it in Client Portal and it is bought when that sleeve's rule next trades.")
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
