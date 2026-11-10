#!/usr/bin/env python3
"""Daily parity of the IBKR mirror's books ON THE EXECUTOR (real money, and its paper book) against
Composer (composer/IBKR_MIRROR.md; CLAUDE.md "ONE BRAIN, TWO BROKERS").

mirror_dry.py keeps a simulated book on this side. This reads what the executor itself did: its
read-only feed (GET {MIRROR_EXECUTOR_URL}/mirror/feed, header X-Read-Token = MIRROR_READ_TOKEN: the
token can read the books and nothing else; it cannot trade, halt or resume), and after the close, per
book and per engine, answers three questions:

  1 is the executor healthy: did today's session run, is anything halted, still open, unresolved, or
    did its own account-versus-book check fail
  2 does each sleeve hold what Composer holds (weights within 3% half-L1, plus the slack whole shares
    need on a small sleeve); a difference the shadow ledger explains (knife-edge, no-rebalance) is
    said, not alarmed
  3 did it earn what Composer earned that day (the sleeve's shares and cash valued at the official
    closes, against Composer's deposit-adjusted value), and what the fills cost against the decision
    price

  mirror_parity.py                 today's check, printed (exit 2 when something needs a human)
  monitor.py calls check() after the shadow runner and the paper book; it can never stop the monitor.

Neither env var set: nothing happens and nothing is printed (the mirror is not deployed). No order,
no broker call, no Composer call; one ledger row per book and engine in results/mirror/parity-ledger.jsonl.
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mirror_dry as md  # noqa: E402
import shadow_runner as sr  # noqa: E402

FEED_KIND = "composer-mirror-feed"
LEDGER_PATH = os.path.join(md.OUT_DIR, "parity-ledger.jsonl")
TOL = sr.TOL_DAILY               # same holdings: half-L1 within 3% ...
CASH_SLACK = 0.01                # ... plus the reserve and buy cushion a sleeve keeps in cash
RETURN_ALARM_BPS = 150.0         # same holdings on both days and a day return this far apart: look at the fills
TIMEOUT_S = 15
LOCAL = ("localhost", "127.0.0.1")


def one_line(e, n=200):
    return " ".join(str(e).split())[:n]


def fetch_feed(url, token, history=30, timeout=TIMEOUT_S, opener=None):
    """the executor's /mirror/feed as a dict. https only (plain http to localhost for a local check):
    the read token is never sent in the clear. Raises RuntimeError with a reason that never holds the
    token"""
    base = (url or "").strip().rstrip("/")
    u = urllib.parse.urlparse(base)
    if u.scheme != "https" and not (u.scheme == "http" and (u.hostname or "") in LOCAL):
        raise RuntimeError("MIRROR_EXECUTOR_URL must be https (the read token is never sent over plain http)")
    req = urllib.request.Request(f"{base}/mirror/feed?history={int(history)}", headers={"X-Read-Token": token})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        why = {401: "the read token was refused", 404: "the feed is not there (mirror off, or no READ_TOKEN on the executor)"}
        raise RuntimeError(f"HTTP {e.code}: {why.get(e.code, 'the executor refused the read')}") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(one_line(str(e).replace(token, "***"), 160)) from None
    if not isinstance(body, dict) or body.get("kind") != FEED_KIND or not isinstance(body.get("books"), dict):
        raise RuntimeError("the answer is not a mirror feed")
    return body


def _rows(view):
    """the book's session rows (not its holdings-only rows), oldest first, one per session"""
    out = {}
    for r in list(view.get("history") or []) + [view.get("last_run") or {}]:
        if isinstance(r, dict) and r.get("session") and r.get("outcome") != "holdings":
            out[r["session"]] = r
    return [out[k] for k in sorted(out)]


def _value(sleeve, px):
    """(equity, {symbol: value}) of one sleeve row at prices px; None when a held symbol has no price"""
    vals = {}
    for sym, q in (sleeve.get("shares") or {}).items():
        p = px.get(sym)
        if not isinstance(p, (int, float)) or p <= 0:
            return None, {}
        vals[sym] = q * p
    return float(sleeve.get("cash") or 0.0) + sum(vals.values()), vals


def weights_of(sleeve, px):
    eq, vals = _value(sleeve, px)
    if not eq or eq <= 0:
        return None, eq
    return {s: v / eq for s, v in vals.items() if v > 0}, eq


def share_slack(symbols, px, eq):
    """the half-L1 distance whole shares alone can cause on this sleeve: half a share's weight per symbol"""
    if not eq or eq <= 0:
        return 0.0
    return 0.5 * sum((px.get(s) or 0.0) / eq for s in symbols)


def book_health(name, view, d, after_close):
    """alerts about the executor's own state for one book"""
    mode = "LIVE" if view.get("mode") == "live" else "PAPER"
    tag = f"MIRROR {mode}"
    out = []
    halt = view.get("halt") or {}
    if halt.get("halted"):
        out.append(f"{tag} HALTED — book {name}: {one_line(halt.get('reason') or 'no reason recorded')} (by {halt.get('by') or '?'}, "
                   f"{halt.get('ts') or '?'}). It trades nothing until POST /mirror/resume."
                   + (" A flatten is still in progress." if halt.get("flatten") and not halt.get("flatten_done") else "")
                   + (" The account was NOT flat when the flatten ended." if halt.get("account_flat") is False else ""))
    if view.get("archived_state"):
        out.append(f"{tag} STATE FILE — book {name}: {one_line(view['archived_state'])}")
    run = view.get("run")
    if run and after_close:
        stuck = [f"{k}: {one_line(v.get('stuck') or v.get('error') or v.get('state'), 80)}"
                 for k, v in (run.get("orders") or {}).items() if v.get("state") != "booked"]
        out.append(f"{tag} RUN STILL OPEN — book {name}, session {run.get('session')}, phase {run.get('phase')}: "
                   + ("; ".join(stuck[:4]) or "no order detail")
                   + ". Nothing new is planned until it closes; an unresolved order needs POST /mirror/resolve.")
    if view.get("last_error"):
        out.append(f"{tag} ERROR — book {name}: {one_line(view['last_error'])}")
    chk = view.get("check") or {}
    if chk.get("problems"):
        out.append(f"{tag} ACCOUNT CHECK — book {name}, session {chk.get('session')}: the account does not hold the book: "
                   + "; ".join(map(str, chk["problems"][:4])))
    if after_close and (view.get("last_session") or "") < d and not halt.get("halted"):
        out.append(f"{tag} DID NOT RUN — book {name}: its last session is {view.get('last_session') or 'none'}, not {d}"
                   + (f" (waiting on: {one_line(view['waiting_on'])})" if view.get("waiting_on") else "")
                   + ". Composer rebalanced on its own.")
    return out


def book_parity(name, view, d, comp, shadow, closes=None, prev_d=None, comp_prev=None):
    """(lines, alerts, ledger rows) for one book on session d. comp / comp_prev: mirror_dry.composer_day
    of d and of the session before; shadow: {(date, engine): ledger row}; closes(day, symbols) ->
    {symbol: official close} or None. The day's return is compared only as a number; it is ALARMED
    only when the two books went into the day holding the same (else the difference is yesterday's
    mismatch, already reported then)"""
    mode = "LIVE" if view.get("mode") == "live" else "PAPER"
    tag = f"MIRROR {mode}"
    rows = {r["session"]: r for r in _rows(view)}
    row = rows.get(d)
    lines, alerts, led = [], [], []
    if not row:
        return lines, alerts, led
    if row.get("outcome") == "skipped" or not row.get("sleeves"):
        alerts.append(f"{tag} NO TRADE — book {name} on {d}: {one_line(row.get('reason') or row.get('outcome'), 300)}")
        return [f"{tag.lower()} {name} {d}: no trade ({one_line(row.get('reason') or row.get('outcome'), 120)})"], alerts, led
    px = row.get("prices") or {}
    same = compared = 0
    diffs, parts = [], []
    prev = rows.get(prev_d) if prev_d else None
    for eng, s in (row.get("sleeves") or {}).items():
        w, eq = weights_of(s, px)
        c, sh = comp.get(eng), shadow.get((d, eng)) or {}
        rec = {"date": d, "book": name, "mode": mode.lower(), "engine": eng, "action": s.get("action"),
               "reason": s.get("reason"), "weights": w, "equity": None if eq is None else round(eq, 2),
               "cash": s.get("cash"), "shares": s.get("shares"), "version": s.get("version"), "shadow": sh.get("status")}
        if s.get("action") == "skip":
            alerts.append(f"{tag} SLEEVE LEFT OUT — {eng} on {d} (book {name}): {one_line(s.get('reason'), 240)}. It kept "
                          f"yesterday's holdings; Composer rebalanced on its own.")
        if w is None or not c:
            rec["parity"] = "no Composer snapshot" if w is not None else "sleeve not priced"
            led.append(rec)
            continue
        dist = sr.distance(w, c["holdings"])[0]
        tol = max(TOL, share_slack(set(w) | set(c["holdings"]), px, eq) + CASH_SLACK)
        compared += 1
        rec.update(composer=c["holdings"], dist=round(dist, 4), tol=round(tol, 4))
        if dist <= tol:
            rec["parity"] = "same"
            same += 1
        elif sh.get("status") in ("knife-edge", "no-rebalance"):
            rec["parity"] = f"explained ({sh['status']})"
        else:
            rec["parity"] = "MISMATCH"
            hint = ""
            if s.get("action") == "hold" and "corridor" in (s.get("reason") or ""):
                hint = f" The sleeve held ({s['reason']}): the two books may be on different corridor paths."
            elif s.get("action") == "skip":
                hint = " The sleeve sat the session out (see above)."
            alerts.append(f"{tag} MISMATCH — {eng} on {d} (book {name}): the mirror holds {sr.fmt_w(w)}; Composer holds "
                          f"{sr.fmt_w(c['holdings'])} (half-L1 {dist:.1%}, allowed {tol:.1%}). The shadow ledger says "
                          f"{sh.get('status') or 'nothing for this session'}.{hint}")
        # the day's return at the official closes, when yesterday's row and both days' closes are there
        if closes and prev and (prev.get("sleeves") or {}).get(eng) and c.get("ret") is not None and c.get("kind") != "next-day":
            p0 = prev["sleeves"][eng]
            c1 = closes(d, set(s.get("shares") or {}))
            c0 = closes(prev_d, set(p0.get("shares") or {}))
            e1, _ = _value(s, c1 or {}) if c1 is not None else (None, {})
            e0, _ = _value(p0, c0 or {}) if c0 is not None else (None, {})
            if e1 and e0 and e0 > 0:
                ret = e1 / e0 - 1
                # did the two books go INTO the day holding the same?
                w0, eq0 = weights_of(p0, prev.get("prices") or {})
                cp = (comp_prev or {}).get(eng)
                carried = None
                if w0 is not None and cp:
                    tol0 = max(TOL, share_slack(set(w0) | set(cp["holdings"]), prev.get("prices") or {}, eq0) + CASH_SLACK)
                    carried = sr.distance(w0, cp["holdings"])[0] <= tol0
                rec.update(ret=round(ret, 6), composer_ret=round(c["ret"], 6), diff_bps=round((ret - c["ret"]) * 1e4, 1),
                           carried_same=carried)
                diffs.append((eng, rec["diff_bps"], carried))
                if carried and abs(rec["diff_bps"]) > RETURN_ALARM_BPS:
                    alerts.append(f"{tag} RETURN GAP — {eng} on {d} (book {name}): {ret:+.2%} against Composer's {c['ret']:+.2%} "
                                  f"though both went into the day holding the same: look at the fills and the booking.")
        led.append(rec)
        parts.append(f"{eng} {s.get('action')}")
    orders = row.get("orders") or []
    short = [f"{o['symbol']} {o.get('filled', 0)}/{o['qty']}" for o in orders if o.get("filled", 0) < o.get("qty", 0)]
    cost = [o["cost_bps"] for o in orders if isinstance(o.get("cost_bps"), (int, float))]
    lines.append(f"{tag.lower()} {name} {d}: " + " | ".join(parts) + f"; {len(orders)} order(s)"
                 + (f", fills {sum(cost) / len(cost):+.1f} bps vs the decision price" if cost and mode == "LIVE" else "")
                 + (f"; NOT FULLY FILLED: {', '.join(short)}" if short else ""))
    if short and mode == "LIVE":
        alerts.append(f"{tag} UNFILLED — book {name} on {d}: {', '.join(short)}. The cash waits for the next session.")
    if compared:
        lines.append(f"  parity vs Composer: {same} of {compared} engines hold the same"
                     + ("; day return, mirror - Composer: "
                        + ", ".join(f"{e} {x:+.0f} bps" + ("" if same_in else " (different holdings into the day)" if same_in is False
                                                          else " (yesterday not comparable)") for e, x, same_in in diffs)
                        if diffs else ""))
    else:
        lines.append(f"  parity vs Composer: no snapshot for {d} on disk yet")
    notes = [n for n in (row.get("notes") or []) if "not attested" not in str(n)]
    unattested = len(row.get("notes") or []) - len(notes)
    if unattested:
        lines.append(f"  note: {unattested} sleeve(s) traded on a tree nobody attested today (paper only; a live book refuses)")
    for n in notes[:3]:
        lines.append(f"  note: {one_line(n, 200)}")
    for pr in (row.get("problems") or [])[:2]:
        lines.append(f"  brain: {one_line(pr, 200)}")
    return lines, alerts, led


def previous_session(d):
    """the NYSE session before d, from the weekday calendar and shadow_runner.NYSE_HOLIDAYS"""
    x = datetime.date.fromisoformat(d)
    while True:
        x -= datetime.timedelta(days=1)
        if x.weekday() < 5 and x.isoformat() not in sr.NYSE_HOLIDAYS:
            return x.isoformat()


def _closes():
    """closes(day, symbols) from Yahoo through the simulator's market reader; None when it cannot be read"""
    market = md.Market(yahoo=md.Yahoo())

    def closes(day, symbols):
        try:
            market.need(set(symbols) | {market.cal_ticker})
            got = market.closes(day)
            return {s: got[s] for s in symbols if s in got} if all(s in got for s in symbols) else None
        except Exception:  # noqa: BLE001
            return None
    return closes


def _write_ledger(rows, path):
    if not rows:
        return
    keep = []
    keys = {(r["date"], r["book"], r["engine"]) for r in rows}
    if os.path.isfile(path):
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (r.get("date"), r.get("book"), r.get("engine")) not in keys:
                    keep.append(r)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in keep + rows))
    os.replace(tmp, path)


def check(now=None, *, env=None, feed=None, snapshot_dir=None, shadow_path=None, ledger_path=LEDGER_PATH, closes=None,
          date=None):
    """(lines, alerts) for the executor's books after session `date` (default: the latest session whose
    close is final at `now`). feed: the feed dict (a test seam; else fetched from the env's URL and
    token). Never raises; with neither env var set and no feed given: ([], [])."""
    try:
        env = os.environ if env is None else env
        url, token = (env.get("MIRROR_EXECUTOR_URL") or "").strip(), (env.get("MIRROR_READ_TOKEN") or "").strip()
        if feed is None and not url and not token:
            return [], []
        now = now or datetime.datetime.now(datetime.timezone.utc)
        d = date or sr.expected_session(now)
        if feed is None:
            if not url or not token:
                return [f"mirror parity: MIRROR_EXECUTOR_URL and MIRROR_READ_TOKEN must both be set ({'URL' if not url else 'token'} "
                        f"missing); nothing checked"], []
            try:
                feed = fetch_feed(url, token)
            except RuntimeError as e:
                return [f"mirror parity {d}: the executor's feed could not be read"], \
                       [f"MIRROR FEED UNREADABLE — {d}: {e}. The executor's books were not checked against Composer today."]
        shadow = md.read_shadow(shadow_path)
        prev_d = previous_session(d)
        cal = sorted({k[0] for k in shadow} | {d, prev_d})
        comp = md.composer_day(d, cal, snapshot_dir)
        comp_prev = md.composer_day(prev_d, cal, snapshot_dir) if prev_d else {}
        after_close = sr.expected_session(now) >= d
        if closes is None:
            closes = _closes()
        lines, alerts, led = [], [], []
        books = feed.get("books") or {}
        if not books:
            return [f"mirror parity {d}: the executor reports no mirror book"], []
        for name in sorted(books, key=lambda n: (books[n].get("mode") != "live", n)):      # the live book first
            view = books[name] or {}
            alerts += book_health(name, view, d, after_close)
            ln, al, rows = book_parity(name, view, d, comp, shadow, closes, prev_d, comp_prev)
            lines += ln
            alerts += al
            led += rows
        _write_ledger(led, ledger_path)
        return lines, alerts
    except BaseException as e:  # noqa: BLE001  the monitor must go on
        if isinstance(e, KeyboardInterrupt):
            raise
        return [f"mirror parity: failed ({type(e).__name__})"], \
               [f"MIRROR PARITY FAILED — {type(e).__name__}: {one_line(e)}. The executor's books were not checked today."]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    date = argv[argv.index("--date") + 1] if "--date" in argv else None
    lines, alerts = check(date=date)
    if not lines and not alerts:
        print("mirror parity: MIRROR_EXECUTOR_URL / MIRROR_READ_TOKEN not set; nothing to check")
        return 0
    for ln in lines:
        print(ln)
    for al in alerts:
        print(f"!! {al}")
    return 2 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
