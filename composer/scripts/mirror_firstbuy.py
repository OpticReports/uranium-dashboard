#!/usr/bin/env python3
"""Funds the live IBKR mirror is about to buy for the FIRST time (read-only; never trades).

Why (2026-11-16): the mirror's first ever ZVOL buy was rejected by IBKR with only
"[202] Order Canceled - reason:Order was discarded." over the API. The real reason, visible only in
Client Portal, was "Rejected by System: Not allowed to open a position: To accept your order in this
security, please login to Client Portal and verify with the token we emailed you." Permissions were
fine (Stocks, Complex or Leveraged ETPs). IBKR asks for that one-time verification the first time an
account opens some securities, and the API never carries its words. So the only early warning is to
notice, before the decision, that a symphony is about to rotate into a fund the account has never
bought, and say so at the 15:15 preview while there are ~35 minutes to verify.

Two surfaces:
- first_buy_alerts(rows, known): the 15:15 preview's alert lines (preclose.py) for each engine whose
  expected post-trade holdings include a fund outside `known`.
- discard_hint(orders): one sentence for the parity UNFILLED alert (mirror_parity.py) when an order
  died with IBKR's bare "discarded" reason.

`known` (the funds the live book has bought or holds) is the union of the feed's current positions,
every filled BUY in its history, and a persisted set (results/mirror/ibkr-bought.json), so a fund
bought once stays known after the feed's history window has moved on.
"""
from __future__ import annotations

import json
import os
import pathlib

KNOWN_PATH = pathlib.Path(__file__).resolve().parent.parent / "results" / "mirror" / "ibkr-bought.json"
MIN_WEIGHT = 0.005          # a holding under half a percent is a rounding remnant, not a buy to warn about
DISCARD_MARKERS = ("order was discarded", "not allowed to open a position", "verify with the token")


def _live(feed: dict) -> dict:
    books = (feed or {}).get("books") or {}
    return books.get("live") or {}


def known_from_feed(feed: dict) -> set[str]:
    """funds the live book holds now or has a filled BUY of in the feed's history"""
    live = _live(feed)
    out = {str(t) for t, q in ((live.get("book") or {}).get("positions") or {}).items() if q}
    for row in live.get("history") or []:
        for o in row.get("orders") or []:
            if o.get("side") == "BUY" and (o.get("filled") or 0) > 0 and o.get("symbol"):
                out.add(str(o["symbol"]))
    return out


def load_known(path: pathlib.Path | None = None) -> set[str]:
    p = path or KNOWN_PATH
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return set()
    return {str(t) for t in (data.get("bought") or [])} if isinstance(data, dict) else set()


def save_known(known: set[str], path: pathlib.Path | None = None) -> None:
    p = path or KNOWN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"bought": sorted(known)}, indent=1) + "\n")
    os.replace(tmp, p)


def first_buy_alerts(rows: list[dict], known: set[str]) -> list[str]:
    """one alert per engine whose expected post-trade holdings ('after') include a fund outside `known`.
    Rows that are not previews of an engine (the GATE row, unavailable engines) are skipped."""
    out = []
    for r in rows or []:
        if r.get("status") != "ok" or r.get("engine") in (None, "GATE"):
            continue
        new = sorted(t for t, w in (r.get("after") or {}).items()
                     if isinstance(w, (int, float)) and w >= MIN_WEIGHT and t not in known)
        if new:
            out.append(f"FIRST BUY ON IBKR — {r['engine']} is set to buy {', '.join(new)} at ~15:50, which the live "
                       f"mirror account has never bought. IBKR may reject a first buy until you verify a token it "
                       f"emails you (2026-11-16: ZVOL). Check your email / Client Portal now; a rejected buy leaves "
                       f"that part of the sleeve in cash and retries next session.")
    return out


def discard_hint(orders: list[dict]) -> str:
    """'' unless an unfilled order died with IBKR's bare 'discarded' reason (or the portal's own words)"""
    hit = sorted({str(o.get("symbol")) for o in orders or []
                  if (o.get("filled") or 0) < (o.get("qty") or 0)
                  and any(m in str(o.get("how") or "").lower() for m in DISCARD_MARKERS)})
    if not hit:
        return ""
    return (f" IBKR discarded the {', '.join(hit)} order without a reason over the API: on a first buy this is "
            f"usually its one-time verification. Open the order's (i) in Client Portal (Orders & Trades) and verify "
            f"the token IBKR emailed you; the mirror retries next session.")


def preview_check(rows: list[dict], feed: dict | None, path: pathlib.Path | None = None) -> tuple[list[str], list[str]]:
    """(lines, alerts) for the 15:15 preview. feed None (no read token, or unreadable): one line, no
    alert. Updates the persisted known set with what the feed shows."""
    if feed is None:
        return ["first-buy check: the mirror feed was not read; funds new to IBKR not checked"], []
    known = load_known(path) | known_from_feed(feed)
    try:
        save_known(known, path)
    except OSError:
        pass
    return [], first_buy_alerts(rows, known)
