#!/usr/bin/env python3
"""The Composer mirror's BRAIN: today's target weights per engine, as JSON (composer/IBKR_MIRROR.md).

Keyless with respect to every broker: it reads the approved trees (fixtures/approved, the same files
the shadow runner and the pre-close preview evaluate) and public prices (FMP's 1-minute bars when
FMP_API_KEY is set, Yahoo otherwise), and publishes what each symphony's logic holds at this minute.
It never reads Composer and never sees the IBKR account; the executor sizes and trades.

The decision itself is the pre-close preview's (preclose.preview), run at the decision minute with
no Composer holdings: same price merge, same staleness handling, same evaluator, same "how close is
the call" label. One code path for the 15:15 preview, the shadow check and the mirror.

  mirror_brain.py                      the payload for this minute (a session must be open)
  mirror_brain.py --at "2026-11-09 15:54"   a replay: only bars stamped at or before that ET minute
  mirror_brain.py --serve [--port N]   HTTP: GET /health; GET /mirror/intents[?after=UTC] and GET
                                       /mirror/session (X-API-Token == MIRROR_API_TOKEN; unset =
                                       404). Stdlib only.

Payload (schema 1): {schema, kind, session, asof_utc, asof_et, replay, close_et, engines: {NAME:
{status: "ok" | "unavailable", symphony, version, rule: "daily" | "threshold", corridor, target:
{ticker: weight}, label: "firm" | "close call" | "could flip", stale: [...], caveats: [...]}},
prices: {ticker: price the engines were evaluated on}, price_notes: {ticker: why that price is an
estimate (rebuilt from a sibling fund, or the last trade carried)}, quotes: {...}, problems: [...]}.
An engine that cannot be decided is "unavailable" with a note; the executor then leaves that sleeve
alone. `prices` are the executor's sizing reference, never a fill. Nothing here is a trade
instruction for Composer.

/mirror/session (the executor's clock; no prices are read): {schema, kind, now_utc, session |
null, open_utc, decide_bar_et, decide_utc, close_et, close_utc}. decide_utc is the END of the
decision bar (shadow_runner.DECISION_MINUTE minutes before the close: 15:54 -> 15:55:00 ET), the
first instant a payload can hold that bar. /mirror/intents?after=<UTC ISO> never answers with a
payload computed before that instant: it recomputes instead.
"""
import datetime
import hmac
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

SCHEMA = 1
KIND = "composer-mirror-intents"
SESSION_KIND = "composer-mirror-session"
WINDOW_FROM_MIN = 45      # --serve: recompute continuously from this many minutes before the close
REFRESH_S = 20            # ... at least this often inside the window
IDLE_TTL_S = 120          # outside the window: an on-demand payload is reused for this long


def rule_of(cfg):
    return ("threshold", float(cfg["corridor"])) if cfg.get("corridor") else ("daily", None)


def build(now=None, quotes=None, fetch=None):
    """the payload at `now` (UTC datetime; default the wall clock). A `now` more than 5 minutes behind
    the wall clock is a replay and reads nothing stamped later. quotes / fetch: test seams, passed to
    preclose.preview."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cfg_all = sr.load_manifest()
    e = sr.et_now(now)
    out = {"schema": SCHEMA, "kind": KIND, "session": None, "asof_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "asof_et": e.strftime("%H:%M:%S"), "replay": pc.is_replay(now), "close_et": None, "engines": {},
           "prices": {}, "price_notes": {}, "quotes": None, "problems": []}
    cap = {}
    try:
        lines, alerts, led = pc.preview(now, lambda: [], None, fetch, quotes, capture=cap)
    except Exception as exc:  # noqa: BLE001
        out["problems"].append(f"brain failed: {pc.one_line(repr(exc))}")
        return _unavailable(out, cfg_all, e.date().isoformat(), "brain failed")
    rows = {r["engine"]: r for r in led if r.get("engine") != "GATE"}
    gate = next((r for r in led if r.get("engine") == "GATE"), None)
    if not rows:                                   # no session, before the open, after the close, or no prices
        why = (alerts or lines or ["no decision"])[0]
        out["problems"].append(pc.one_line(why, 300))
        return _unavailable(out, cfg_all, e.date().isoformat(), "no decision at this time")
    day = next(iter(rows.values()))["date"]
    out["session"] = day
    out["close_et"] = sr.session_close(day)
    qrec = (gate or next(iter(rows.values()))).get("quotes")
    if qrec:
        out["quotes"] = {k: qrec.get(k) for k in ("source", "fmp", "yahoo", "none", "failed", "short")}
    out["problems"] += [pc.one_line(a, 300) for a in alerts if "UNAVAILABLE" in a]
    held = set()                                   # every ticker an approved tree can hold or read
    for cfg in cfg_all.values():
        held |= sr.tree_tickers(sr.load_tree(sr.era_for(cfg, day) or cfg["eras"][-1]))
    for t in sorted(held):
        px = (cap.get("prices") or {}).get(t)
        if isinstance(px, (int, float)) and not isinstance(px, bool) and px > 0:
            out["prices"][t] = round(float(px), 6)
            if t in (cap.get("notes") or {}):
                out["price_notes"][t] = pc.one_line(cap["notes"][t], 120)
    for eng, cfg in cfg_all.items():
        era = sr.era_for(cfg, day) or cfg["eras"][-1]
        rule, corridor = rule_of(cfg)
        base = {"symphony": cfg["symphony"], "version": era["version"], "rule": rule, "corridor": corridor}
        r = rows.get(eng)
        if not r or r.get("status") != "ok" or not r.get("target"):
            out["engines"][eng] = dict(base, status="unavailable", note=(r or {}).get("note") or "no decision")
            continue
        caveats = [c for c in r.get("caveats") or [] if "Composer" not in c]
        out["engines"][eng] = dict(base, status="ok", target={t: float(w) for t, w in sorted(r["target"].items())},
                                   label=r.get("label"), stale=r.get("stale") or [], caveats=caveats)
    return out


def _unavailable(out, cfg_all, day, note):
    for eng, cfg in cfg_all.items():
        era = sr.era_for(cfg, day) or cfg["eras"][-1]
        rule, corridor = rule_of(cfg)
        out["engines"][eng] = {"symphony": cfg["symphony"], "version": era["version"], "rule": rule,
                               "corridor": corridor, "status": "unavailable", "note": note}
    return out


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text):
    """'YYYY-MM-DDTHH:MM:SSZ' -> an aware UTC datetime (ValueError otherwise)"""
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def session_info(now=None):
    """the executor's clock for today's session, from the exchange calendar alone (no prices): when
    the decision bar ends and when the session closes. session None: the exchange is shut today"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    e = sr.et_now(now)
    day = e.date().isoformat()
    out = {"schema": SCHEMA, "kind": SESSION_KIND, "now_utc": _iso(now), "session": None}
    if e.weekday() >= 5 or day in sr.NYSE_HOLIDAYS:
        return out
    close = sr.session_close(day)

    def at(hhmm):
        return datetime.datetime.combine(e.date(), datetime.time(int(hhmm[:2]), int(hhmm[3:5])), tzinfo=e.tzinfo)
    bar = sr._hm(sr._min(close) - sr.DECISION_MINUTE)
    out.update(session=day, open_utc=_iso(at("09:30")), decide_bar_et=bar,
               decide_utc=_iso(at(bar) + datetime.timedelta(minutes=1)), close_et=close, close_utc=_iso(at(close)))
    return out


def parse_at(text):
    """'YYYY-MM-DD HH:MM[:SS]' in ET -> an aware UTC datetime"""
    fmt = "%Y-%m-%d %H:%M:%S" if text.count(":") == 2 else "%Y-%m-%d %H:%M"
    naive = datetime.datetime.strptime(text, fmt)
    tz = sr.et_now(datetime.datetime.now(datetime.timezone.utc)).tzinfo
    return naive.replace(tzinfo=tz).astimezone(datetime.timezone.utc)


# ------------------------------------------------------------------ HTTP (stdlib)
class Cache:
    """the latest payload, recomputed by one background thread inside the decision window and on
    demand (single flight) outside it"""

    def __init__(self, builder=build, clock=time.time):
        self.builder, self.clock = builder, clock
        self.lock = threading.Lock()
        self.flight = threading.Lock()
        self.payload, self.at, self.error = None, 0.0, None

    def refresh(self):
        with self.flight:                          # one computation at a time
            try:
                p = self.builder()
                with self.lock:
                    self.payload, self.at, self.error = p, self.clock(), None
            except Exception as exc:  # noqa: BLE001
                with self.lock:
                    self.error = pc.one_line(repr(exc))

    def get(self, max_age, after=None):
        """(payload, its age in seconds, the last rebuild's error). after: a 'YYYY-MM-DDTHH:MM:SSZ'
        stamp; a cached payload computed before it is not fresh, whatever its age"""
        def fresh():
            if self.payload is None or self.clock() - self.at > max_age:
                return False
            return after is None or str(self.payload.get("asof_utc") or "") >= after
        with self.lock:
            ok = fresh()
        if not ok:
            self.refresh()
        with self.lock:
            return self.payload, self.clock() - self.at, self.error


def in_window(now=None):
    """inside the last WINDOW_FROM_MIN minutes of a session (False if the calendar says no session)"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ss = pc.session(now)
    return bool(ss and 0 < ss["left"] + pc.DECIDE_BEFORE <= WINDOW_FROM_MIN)


def make_server(port, token, cache, window=in_window, clock_info=session_info, wall=None):
    """the HTTP server (not started): GET /health is public; GET /mirror/intents and /mirror/session
    need X-API-Token == token (constant-time compare) and answer 404 while no token is configured.
    wall: the wall clock (a test seam; default the system's UTC)"""
    wall = wall or (lambda: datetime.datetime.now(datetime.timezone.utc))
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            """None when the token matches, else the (code, body) to answer with"""
            if not token:
                return 404, {"error": "intents disabled (MIRROR_API_TOKEN unset)"}
            if not hmac.compare_digest(self.headers.get("X-API-Token", "").encode(), token.encode()):
                return 401, {"error": "unauthorized"}
            return None

        def do_GET(self):  # noqa: N802
            path, _, query = self.path.partition("?")
            if path == "/health":
                with cache.lock:
                    age = round(cache.clock() - cache.at, 1) if cache.payload else None
                    err = cache.error
                return self._send(200, {"status": "ok", "service": "composer-brain", "in_window": window(),
                                        "payload_age_s": age, "last_error": err, "token_set": bool(token)})
            if path == "/mirror/session":
                refused = self._authorized()
                if refused:
                    return self._send(*refused)
                return self._send(200, clock_info())
            if path == "/mirror/intents":
                refused = self._authorized()
                if refused:
                    return self._send(*refused)
                after = None
                for part in query.split("&"):
                    if part.startswith("after="):
                        after = part[len("after="):].replace("%3A", ":").replace("%3a", ":")
                if after is not None:
                    try:
                        want = parse_utc(after)
                    except ValueError:
                        return self._send(400, {"error": "after must be YYYY-MM-DDTHH:MM:SSZ"})
                    if want > wall() + datetime.timedelta(seconds=5):
                        return self._send(409, {"error": "after is in the future: nothing can be computed yet"})
                payload, age, err = cache.get(REFRESH_S * 2 if window() else IDLE_TTL_S, after)
                if payload is None:
                    return self._send(503, {"error": err or "no payload yet"})
                if after is not None and str(payload.get("asof_utc") or "") < after:
                    return self._send(503, {"error": err or "no payload computed after the requested instant"})
                return self._send(200, dict(payload, served_age_s=round(age, 1)))
            return self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):         # no access log: the token rides in a header, not the URL
            return
    return ThreadingHTTPServer(("0.0.0.0", port), H)


def serve(port):
    cache = Cache()

    def loop():
        while True:
            try:
                if in_window():
                    cache.refresh()
                    time.sleep(REFRESH_S)
                else:
                    time.sleep(15)
            except Exception:  # noqa: BLE001
                time.sleep(15)
    threading.Thread(target=loop, daemon=True).start()
    make_server(port, os.environ.get("MIRROR_API_TOKEN", ""), cache).serve_forever()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--serve" in argv:
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else int(os.environ.get("PORT", "10000"))
        return serve(port)
    now = parse_at(argv[argv.index("--at") + 1]) if "--at" in argv else None
    print(json.dumps(build(now), indent=1))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    sys.stdout.flush()
    os._exit(code or 0)                             # FMP fetches past the budget may still be in flight
