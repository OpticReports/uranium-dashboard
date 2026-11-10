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
  mirror_brain.py --serve [--port N]   HTTP: GET /health, GET /mirror/intents (X-API-Token ==
                                       MIRROR_API_TOKEN; unset = 404). Stdlib only.

Payload (schema 1): {schema, kind, session, asof_utc, asof_et, replay, close_et, engines: {NAME:
{status: "ok" | "unavailable", symphony, version, rule: "daily" | "threshold", corridor, target:
{ticker: weight}, label: "firm" | "close call" | "could flip", stale: [...], caveats: [...]}},
quotes: {...}, problems: [...]}. An engine that cannot be decided is "unavailable" with a note; the
executor then leaves that sleeve alone. Nothing here is a trade instruction for Composer.
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
           "quotes": None, "problems": []}
    try:
        lines, alerts, led = pc.preview(now, lambda: [], None, fetch, quotes)
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

    def get(self, max_age):
        with self.lock:
            fresh = self.payload is not None and self.clock() - self.at <= max_age
        if not fresh:
            self.refresh()
        with self.lock:
            return self.payload, self.clock() - self.at, self.error


def in_window(now=None):
    """inside the last WINDOW_FROM_MIN minutes of a session (False if the calendar says no session)"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ss = pc.session(now)
    return bool(ss and 0 < ss["left"] + pc.DECIDE_BEFORE <= WINDOW_FROM_MIN)


def make_server(port, token, cache, window=in_window):
    """the HTTP server (not started): GET /health is public; GET /mirror/intents needs X-API-Token ==
    token (constant-time compare) and answers 404 while no token is configured"""
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

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/health":
                with cache.lock:
                    age = round(cache.clock() - cache.at, 1) if cache.payload else None
                    err = cache.error
                return self._send(200, {"status": "ok", "service": "composer-brain", "in_window": window(),
                                        "payload_age_s": age, "last_error": err, "token_set": bool(token)})
            if path == "/mirror/intents":
                given = self.headers.get("X-API-Token", "")
                if not token:
                    return self._send(404, {"error": "intents disabled (MIRROR_API_TOKEN unset)"})
                if not hmac.compare_digest(given.encode(), token.encode()):
                    return self._send(401, {"error": "unauthorized"})
                payload, age, err = cache.get(REFRESH_S * 2 if window() else IDLE_TTL_S)
                if payload is None:
                    return self._send(503, {"error": err or "no payload yet"})
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
