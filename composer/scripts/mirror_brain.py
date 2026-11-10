#!/usr/bin/env python3
"""The Composer mirror's BRAIN: each engine's target weights at the decision instant, as JSON
(composer/IBKR_MIRROR.md; the brain <-> executor contract, schema 2).

Keyless with respect to every broker: it reads the approved trees (fixtures/approved, the same files
the shadow runner and the pre-close preview evaluate) and public prices (FMP's 1-minute bars, Yahoo's
daily history), and publishes what each symphony's logic holds. It never reads Composer and never sees
the IBKR account; the executor sizes and trades. The decision itself is the pre-close preview's
(preclose.preview): same price merge, same evaluator, same "how close is the call" label.

  mirror_brain.py                      an ad hoc payload for this minute (monitoring; not tradeable)
  mirror_brain.py --at "2026-11-09 15:54"   the PINNED decision as of that ET instant (a replay when
                                       the day is not today)
  mirror_brain.py --serve [--port N]   HTTP (stdlib): GET /health; GET /mirror/session and GET
                                       /mirror/intents[?after=UTC] (X-API-Token == MIRROR_API_TOKEN);
                                       POST /mirror/attest (X-Attest-Token == MIRROR_ATTEST_TOKEN).
                                       A token left unset answers 404.

THE DECISION INSTANT. /mirror/session gives decide_utc = the close minus shadow_runner.DECISION_MINUTE
minutes exactly (15:54:00 ET on a full day): the END of the decision bar, the instant
shadow_runner.minute_price(day, "15:54") reads and the minute the logic was calibrated on (add. 50).

A PINNED build (build(now=T, pinned=True); /mirror/intents?after=T) is the decision AS OF T, whatever
second it is computed: today's prices are FMP's traded 1-minute bars ENDING at or before T and nothing
else (never Yahoo's last sale, which depends on the second it was fetched); the history is Yahoo's
adjusted closes before the session. Two pinned builds for one T on the same bars give the same targets
and prices, and the live answer equals `--at` afterwards. /mirror/intents?after=T answers 503
"decision bar not published yet" until SPY's traded bar ending at T is in AND FMP has stopped
publishing that minute (it publishes ticker by ticker over 10-25 s: preclose-ledger 2026-11-09 15:16:15,
SPY had the bar and 23 of 48 tickers did not), waiting at most SETTLE_S; then the payload is built once
(concurrent requests share the build), cached by T and never rebuilt.

NEVER A TRADEABLE DECISION ON DEAD DATA (measured on 83 sessions of FMP minutes, 2026-07-15..11-09):
  - pinned: every engine is unavailable unless SPY's price is from the bar ending at T (83 of 83 had it)
  - every engine is unavailable unless at least BREADTH_MIN of the trees' tickers traded within
    BREADTH_AGE_S of the instant (measured share: 92-100%, so a stalled feed or a shut market, 0%, is
    refused and no real session was)
  - an engine is unavailable when a decision ticker it reads has no trade of its own today (the price
    would be an estimate: rebuilt from a sibling fund, or an earlier close carried; 0 of 332
    engine-sessions), when fewer than ENGINE_BREADTH_MIN of its decision tickers traded within
    BREADTH_AGE_S (0 of 332), or when its history is a session short
  A thin fund's own last trade, however old, is used and named (PEJ's was over 15 minutes old on 5
  sessions): Composer trades those days, and refusing them would have cost 1.8% of engine-sessions
  (9.6% at a two-minute limit).

THE TREE-VERSION GATE. A Composer-keyed job (mirror_attest.py) posts each symphony's live version and
the sha1 of its canonical live tree (shadow_runner.tree_sha1, the one function used for the approved
tree too). `sync` says per engine ok / drift / none; drift makes the engine unavailable; none (no
attestation for the session) trades with a line in `problems`, or is unavailable when
MIRROR_REQUIRE_ATTESTATION is set. An engine attested paused is unavailable (Composer will not
rebalance it).

Payload (schema 2): {schema, kind, session, pinned, asof_utc, asof_et, built_utc, decision_bar:
{end_utc, spy_utc, complete} | null, replay, close_et, engines: {NAME: {status: "ok" | "unavailable",
symphony, version, rule: "daily" | "threshold", corridor, target: {ticker: weight}, label, stale,
caveats, note}}, prices: {ticker: raw price} for every ticker of ANY era of the manifest, price_times:
{ticker: UTC time of the trade or bar end the price is from}, price_notes: {ticker: why a price is an
estimate or old}, dividends: [{ticker, ex_date, pay_date | null, amount}], splits: [{ticker, date,
ratio}] (the last ACTIONS_DAYS calendar days), sync, quotes, problems}. `prices` are the executor's
sizing reference, never a fill. Nothing here is a trade instruction for Composer.
"""
import datetime
import functools
import hmac
import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

SCHEMA = 2
KIND = "composer-mirror-intents"
SESSION_KIND = "composer-mirror-session"
UTC = datetime.timezone.utc
FMP_BUDGET_S = 10         # the mirror's own budget for FMP's minutes after SPY's (preclose's preview keeps 90)
FMP_TIMEOUT_S = 8         # one FMP call, one attempt: a decision cannot wait on a hanging request
BREADTH_AGE_S = 120       # "traded recently": a trade within this many seconds of the instant
BREADTH_MIN = 0.80        # the feed is alive: at least this share of the trees' tickers traded recently
ENGINE_BREADTH_MIN = 0.75  # ... and at least this share of an engine's own decision tickers
LAG_MAX = 0.15            # still publishing: more than this share of the recently traded tickers have their last
                          # bar ending a minute BEFORE the instant (complete days: median 2%, max 6.5% of 83)
SETTLE_S = 45             # seconds after the instant an unsettled bar is waited for; then what FMP has is used
ACTIONS_DAYS = 10         # dividends and splits published: ex-date within this many calendar days of the session
WARM_FROM_MIN = 10        # --serve: Yahoo's history is fetched from this many minutes before the decision instant
WARM_EVERY_S = 60         # ... and what is still missing or incomplete is asked again this often
RECHECK_S = 60            # a history that is not final (no bar for today yet, or a session short) is refetched after this
YAHOO_TIMEOUT_S = 10      # one Yahoo history call from the serving brain (two attempts)
AD_HOC_TTL_S = 60         # an ad hoc (unpinned) payload is reused for this long
ATTEST_MAX_BYTES = 65536
KEEP = 4                  # pinned instants / attested sessions kept in memory


def _utcnow():
    return datetime.datetime.now(UTC)


def _iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text):
    """'YYYY-MM-DDTHH:MM:SSZ' -> an aware UTC datetime (ValueError otherwise)"""
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def parse_at(text):
    """'YYYY-MM-DD HH:MM[:SS]' in ET -> an aware UTC datetime"""
    fmt = "%Y-%m-%d %H:%M:%S" if text.count(":") == 2 else "%Y-%m-%d %H:%M"
    naive = datetime.datetime.strptime(text, fmt)
    tz = sr.et_now(_utcnow()).tzinfo
    return naive.replace(tzinfo=tz).astimezone(UTC)


def _et_instant(day, hhmm, tz):
    return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(int(hhmm[:2]), int(hhmm[3:5])),
                                     tzinfo=tz).astimezone(UTC)


def rule_of(cfg):
    return ("threshold", float(cfg["corridor"])) if cfg.get("corridor") else ("daily", None)


def era_of(cfg, day):
    return sr.era_for(cfg, day) or cfg["eras"][-1]


def era_tickers(cfg_all):
    """every ticker ANY era of the manifest reads or holds: a sleeve may still hold what a newer tree
    dropped, and it can only be sold if it is priced"""
    out = set()
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            out |= sr.tree_tickers(sr.load_tree(era))
    return out


def feed_tickers(cfg_all, day):
    """every ticker a build may ask FMP for: all eras', SPY, and the same-index siblings the preview
    rebuilds a stale price from"""
    out = era_tickers(cfg_all) | {pc.GATE[0]}
    for cfg in cfg_all.values():
        for t in sr.tree_tickers(sr.load_tree(era_of(cfg, day))):
            out |= set(pc.family(t) or {})
    return out


def calendar_reason(day):
    """None, or why `day` cannot be clocked: the static NYSE tables end before its year (a holiday would
    read as a session and a 13:00 close as 16:00)"""
    end = sr.calendar_through()
    if int(day[:4]) > end:
        return (f"the exchange calendar (shadow_runner.NYSE_HOLIDAYS / HALF_DAYS) ends in {end}: {day} cannot be "
                f"clocked; extend the tables")
    return None


def session_info(now=None):
    """the executor's clock for today's session, from the exchange calendar alone (no prices): the
    decision instant and the close. session None: the exchange is shut today (a weekend or a listed
    holiday), or, with a 'reason', the calendar cannot say (its tables end before this year)"""
    now = now or _utcnow()
    e = sr.et_now(now)
    day = e.date().isoformat()
    out = {"schema": SCHEMA, "kind": SESSION_KIND, "now_utc": _iso(now), "session": None}
    if e.weekday() >= 5 or day in sr.NYSE_HOLIDAYS:
        return out
    why = calendar_reason(day)
    if why:
        return dict(out, reason=why)
    close = sr.session_close(day)
    decide = sr._hm(sr._min(close) - sr.DECISION_MINUTE)
    out.update(session=day, open_utc=_iso(_et_instant(day, "09:30", e.tzinfo)), close_utc=_iso(_et_instant(day, close, e.tzinfo)),
               close_et=close, decide_et=decide, decide_utc=_iso(_et_instant(day, decide, e.tzinfo)))
    return out


# ------------------------------------------------------------------ the tree-version gate
@functools.lru_cache(maxsize=64)
def _approved_sha1(tree_file):
    return sr.tree_sha1(sr.load_tree({"tree": tree_file}))


def approved_sha1(era):
    """the fingerprint of an approved era's tree: shadow_runner.tree_sha1, the function mirror_attest.py
    applies to Composer's live tree"""
    return _approved_sha1(era["tree"])


class Attestations:
    """what mirror_attest.py last posted, per session, in memory: {session: {'engines': {NAME:
    {'version', 'tree_sha1', 'paused', 'attested_utc'}}}}. A later post for the same session replaces
    an engine's entry"""
    DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    SHA = re.compile(r"^[0-9a-f]{40}$")

    def __init__(self):
        self.lock = threading.Lock()
        self.by_session = {}

    def put(self, body, now, engines):
        """store a POST /mirror/attest body; (session, stored names, ignored names). ValueError: the
        body is not an attestation for today's session"""
        if not isinstance(body, dict) or not isinstance(body.get("session"), str) or not self.DAY.match(body["session"]):
            raise ValueError("body must be {session: 'YYYY-MM-DD', engines: {NAME: {version, tree_sha1}}}")
        day = body["session"]
        if day != sr.et_now(now).date().isoformat():
            raise ValueError(f"an attestation is for today's session, not {day}")
        if not isinstance(body.get("engines"), dict) or not body["engines"]:
            raise ValueError("engines must be a non-empty object")
        good, ignored = {}, []
        for name, rec in body["engines"].items():
            if name not in engines:
                ignored.append(str(name)[:40])
                continue
            if not isinstance(rec, dict) or not isinstance(rec.get("version"), str) or not 0 < len(rec["version"]) <= 80 \
                    or not isinstance(rec.get("tree_sha1"), str) or not self.SHA.match(rec["tree_sha1"]) \
                    or not isinstance(rec.get("paused", False), bool):
                raise ValueError(f"{name}: needs version (text), tree_sha1 (40 hex digits) and, optionally, paused (true/false)")
            good[name] = {"version": rec["version"], "tree_sha1": rec["tree_sha1"], "paused": bool(rec.get("paused", False)),
                          "attested_utc": _iso(now)}
        if not good:
            raise ValueError("no known engine in the attestation")
        with self.lock:
            self.by_session.setdefault(day, {"engines": {}})["engines"].update(good)
            for old in sorted(self.by_session)[:-KEEP]:
                del self.by_session[old]
        return day, sorted(good), sorted(ignored)

    def get(self, day):
        with self.lock:
            rec = self.by_session.get(day)
            return {"engines": {k: dict(v) for k, v in rec["engines"].items()}} if rec else None


def sync_block(cfg_all, day, attest=None):
    """{NAME: {state, approved_version, approved_sha1, live_version, attested_utc[, paused]}}: 'ok' the
    attested live tree hashes equal to the approved tree in use on `day`; 'drift' it does not; 'none'
    nothing was attested for that session. attest: an Attestations (or any .get(day))"""
    rec = (attest.get(day) if attest is not None else None) or {}
    out = {}
    for eng, cfg in cfg_all.items():
        era = era_of(cfg, day)
        a = (rec.get("engines") or {}).get(eng)
        row = {"state": "none", "approved_version": era["version"], "approved_sha1": approved_sha1(era),
               "live_version": None, "attested_utc": None}
        if a:
            row.update(state="ok" if a.get("tree_sha1") == row["approved_sha1"] else "drift",
                       live_version=a.get("version"), attested_utc=a.get("attested_utc"))
            if a.get("paused"):
                row["paused"] = True
        out[eng] = row
    return out


def require_attestation():
    return os.environ.get("MIRROR_REQUIRE_ATTESTATION", "").strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ the payload
def _minutes(t, d, key):
    """FMP's traded 1-minute bars, one short attempt (the mirror's decision cannot wait on a retry)"""
    return sr.fetch_minutes(t, d, key, tries=1, traded=True, timeout=FMP_TIMEOUT_S)


def _stamp_iso(stamp, tz):
    """a price's time for price_times: the trade's (or, for a rebuilt price, the sibling's trade's); an
    earlier session's close for a price carried from it; None when the feed gave no time"""
    kind, when = stamp if stamp else (None, None)
    if isinstance(when, datetime.datetime):
        return _iso(when)
    if kind == "previous" and isinstance(when, str):
        return _iso(_et_instant(when, sr.session_close(when), tz))
    return None


def price_extra(tickers, now, today, fetch, quotes, pinned):
    """(raw prices, stamps, notes, failures) for tickers no current tree reads, through the preview's own
    freshness path (Yahoo's history, FMP's last traded minute, preclose.merge_quotes and live_prices)"""
    try:
        data, bad = pc.fetch_all(tickers, fetch)
        live_q = {}
        if quotes and data:
            try:
                live_q, _ = quotes(set(data), now)
            except Exception:  # noqa: BLE001
                live_q = {}
        horizon = now if (pinned or pc.is_replay(now)) else None
        fac = {t: pc.day_factor(a, r, today) for t, (a, r, _) in data.items()}
        data, _, _ = pc.merge_quotes(data, live_q, today, now, horizon, yahoo_today=not pinned)
        prices, notes, _ = pc.live_prices(data, today, now)
        return ({t: p[today] / fac.get(t, 1.0) for t, p in prices.items() if today in p},
                pc.price_stamps(data, notes, today), notes, bad)
    except Exception as exc:  # noqa: BLE001
        return {}, {}, {}, {t: pc.one_line(repr(exc), 80) for t in tickers}


def build(now=None, quotes=None, fetch=None, pinned=False, attest=None, wall=None, budget=None):
    """the payload at `now` (UTC datetime; default the wall clock).
    pinned=False: an ad hoc read for monitoring (a `now` more than 5 minutes behind the wall clock is a
    replay and reads nothing stamped later). pinned=True: the decision AS OF `now` exactly (see the
    module docstring); 'replay' is then True only when `now` is on another ET day than the wall clock.
    quotes / fetch: the preview's seams (FMP minutes; Yahoo history); attest: an Attestations; wall: the
    wall clock (a test seam); budget: seconds for FMP's minutes (default FMP_BUDGET_S)."""
    wall = wall or _utcnow
    started = wall()
    now = now or started
    cfg_all = sr.load_manifest()
    e = sr.et_now(now)
    day0 = e.date().isoformat()
    replay = (sr.et_now(started).date() != e.date()) if pinned else pc.is_replay(now, started)
    out = {"schema": SCHEMA, "kind": KIND, "session": None, "pinned": bool(pinned), "asof_utc": _iso(now),
           "asof_et": e.strftime("%H:%M:%S"), "built_utc": None,
           "decision_bar": {"end_utc": _iso(now), "spy_utc": None, "complete": False} if pinned else None,
           "replay": replay, "close_et": None, "engines": {}, "prices": {}, "price_times": {}, "price_notes": {},
           "dividends": [], "splits": [], "sync": sync_block(cfg_all, day0, attest), "quotes": None, "problems": []}

    def done(o):
        o["built_utc"] = _iso(wall())
        return o
    why = calendar_reason(day0)
    if why:
        out["problems"].append(why)
        return done(_unavailable(out, cfg_all, day0, "the exchange calendar does not cover this date"))
    if quotes is None:
        quotes = pc.fmp_quotes(budget=FMP_BUDGET_S if budget is None else budget, fetch=_minutes)   # None without a key
    if pinned and not quotes:
        out["problems"].append("FMP_API_KEY not set: a pinned decision needs FMP's 1-minute bars")
        return done(_unavailable(out, cfg_all, day0, "no 1-minute bars"))
    seen = {}
    base = fetch or pc.fetch_live

    def fetch2(t):
        r = base(t)
        seen[t] = r[2] if len(r) > 2 and isinstance(r[2], dict) else {}
        return r
    cap = {}
    try:
        lines, alerts, led = pc.preview(now, lambda: [], None, fetch2, quotes, capture=cap, pin=pinned)
    except Exception as exc:  # noqa: BLE001
        out["problems"].append(f"brain failed: {pc.one_line(repr(exc))}")
        return done(_unavailable(out, cfg_all, day0, "brain failed"))
    rows = {r["engine"]: r for r in led if r.get("engine") != "GATE"}
    gate = next((r for r in led if r.get("engine") == "GATE"), None)
    if not rows:                                   # no session, before the open, after the close, or no prices
        why = (alerts or lines or ["no decision"])[0]
        out["problems"].append(pc.one_line(why, 300))
        return done(_unavailable(out, cfg_all, day0, "no decision at this time"))
    day = next(iter(rows.values()))["date"]
    out["session"] = day
    out["close_et"] = sr.session_close(day)
    out["sync"] = sync_block(cfg_all, day, attest)
    qrec = (gate or next(iter(rows.values()))).get("quotes") or {}
    out["quotes"] = {k: qrec.get(k) for k in ("source", "fmp", "yahoo", "none", "failed", "short")}
    out["problems"] += [pc.one_line(a, 300) for a in alerts if "UNAVAILABLE" in a]

    # ---- reference prices: every ticker of any era, with the time each price is from
    px, stamps, notes = dict(cap.get("prices") or {}), dict(cap.get("stamps") or {}), dict(cap.get("notes") or {})
    held = era_tickers(cfg_all)
    extra = sorted(t for t in held if t not in px)
    if extra:
        p2, s2, n2, bad = price_extra(extra, now, day, fetch2, quotes, pinned)
        px.update(p2)
        stamps.update({t: s for t, s in s2.items() if t in extra})
        notes.update({t: n for t, n in n2.items() if t in extra})
        lost = sorted(t for t in extra if t not in p2)
        if lost:
            out["problems"].append(f"no price for {', '.join(lost)}: a sleeve still holding one cannot be sized")
    for t in sorted(held):
        v = px.get(t)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            out["prices"][t] = round(float(v), 6)
            out["price_times"][t] = _stamp_iso(stamps.get(t), e.tzinfo)
            if t in notes:
                out["price_notes"][t] = pc.one_line(notes[t], 120)

    # ---- never a tradeable decision on dead data
    tick = list(cap.get("tick") or [])
    short = set(cap.get("short") or [])
    traded = set(cap.get("traded") or [])

    def age(t):
        """seconds from the trade t's price is from to the instant; None when it is not a trade of today"""
        kind, when = stamps.get(t) or (None, None)
        return (now - when).total_seconds() if kind == "trade" and isinstance(when, datetime.datetime) else None

    def recent(t):
        a = age(t)
        return a is not None and a <= BREADTH_AGE_S
    live = [t for t in tick if recent(t)]
    share = len(live) / len(tick) if tick else 0.0
    out["quotes"]["breadth"] = {"recent": len(live), "of": len(tick), "share": round(share, 4), "min_share": BREADTH_MIN,
                                "within_s": BREADTH_AGE_S}
    halt = []
    if pinned:
        kind, when = stamps.get(pc.GATE[0]) or (None, None)
        spy = when if kind == "trade" and isinstance(when, datetime.datetime) else None
        out["decision_bar"] = {"end_utc": _iso(now), "spy_utc": _iso(spy) if spy else None, "complete": spy == now}
        if spy != now:
            halt.append(f"SPY's price is not from the bar ending {e:%H:%M:%S} ET (its last traded bar ends "
                        f"{sr.et_now(spy).strftime('%H:%M:%S') if spy else 'nowhere today'})")
    if share < BREADTH_MIN:
        halt.append(f"the feed looks dead: {len(live)} of {len(tick)} tickers traded in the {BREADTH_AGE_S // 60} minutes "
                    f"to {e:%H:%M:%S} ET")
    out["problems"] += halt
    need = require_attestation()
    unattested = []
    for eng, cfg in cfg_all.items():
        era = era_of(cfg, day)
        rule, corridor = rule_of(cfg)
        base_row = {"symphony": cfg["symphony"], "version": era["version"], "rule": rule, "corridor": corridor}
        r = rows.get(eng)
        if not r or r.get("status") != "ok" or not r.get("target"):
            out["engines"][eng] = dict(base_row, status="unavailable", note=(r or {}).get("note") or "no decision")
            continue
        dec = sorted(sr.decision_tickers(sr.load_tree(era)))
        why = list(halt)
        hit = [t for t in dec if t in short]
        if hit:
            why.append(f"the history of {', '.join(hit)} lacks the previous session (indicators a session short)")
        est = [t for t in dec if t not in traded]
        if est:
            why.append(f"no trade today for {', '.join(est)}: priced by an estimate")
        n_live = sum(recent(t) for t in dec)
        if dec and n_live < ENGINE_BREADTH_MIN * len(dec):
            why.append(f"{n_live} of its {len(dec)} decision tickers traded in the last {BREADTH_AGE_S // 60} minutes")
        s = out["sync"][eng]
        if s["state"] == "drift":
            why.append(f"the live logic (version {s['live_version']}) differs from the approved {s['approved_version']}: "
                       f"not mirrored until the change is approved or rolled back")
        elif s.get("paused"):
            why.append("attested paused: no rebalance to mirror")
        elif s["state"] == "none":
            if need:
                why.append("no attestation of the live logic for this session (MIRROR_REQUIRE_ATTESTATION)")
            else:
                unattested.append(eng)
        if s["state"] == "ok" and s["live_version"] != s["approved_version"]:
            out["problems"].append(f"{eng}: live version {s['live_version']} has the approved logic of "
                                   f"{s['approved_version']} (a rename?): add it to the manifest")
        if why:
            out["engines"][eng] = dict(base_row, status="unavailable", note="; ".join(why))
            continue
        caveats = [c for c in r.get("caveats") or [] if "Composer" not in c]
        out["engines"][eng] = dict(base_row, status="ok", target={t: float(w) for t, w in sorted(r["target"].items())},
                                   label=r.get("label"), stale=r.get("stale") or [], caveats=caveats)
    if unattested:
        out["problems"].append(f"no attestation of the live logic for {day}: {', '.join(unattested)} on the approved "
                               f"trees, unverified")

    # ---- dividends and splits of the last ACTIONS_DAYS days (pure data: the executor does the accounting)
    lo = (datetime.date.fromisoformat(day) - datetime.timedelta(days=ACTIONS_DAYS)).isoformat()
    unread, yahoo_only = [], []
    for t in sorted(held):
        ca = (seen.get(t) or {}).get("corporateActions")
        if not isinstance(ca, dict):
            unread.append(t)
            continue
        if not ca.get("fmp"):
            yahoo_only.append(t)
        for x in ca.get("dividends") or []:
            if lo <= x["ex_date"] <= day:
                out["dividends"].append({"ticker": t, "ex_date": x["ex_date"], "pay_date": x.get("pay_date"),
                                         "amount": round(float(x["amount"]), 6)})
        for x in ca.get("splits") or []:
            if lo <= x["date"] <= day:
                out["splits"].append({"ticker": t, "date": x["date"],
                                      "ratio": round(float(x["numerator"]) / float(x["denominator"]), 8)})
    out["dividends"].sort(key=lambda x: (x["ex_date"], x["ticker"]))
    out["splits"].sort(key=lambda x: (x["date"], x["ticker"]))
    if unread:
        out["problems"].append(f"dividends and splits not read for {len(unread)} ticker(s): {', '.join(unread[:8])}"
                               + (" ..." if len(unread) > 8 else ""))
    if yahoo_only:
        out["problems"].append(f"FMP's dividend list not read for {len(yahoo_only)} ticker(s) ({', '.join(yahoo_only[:8])}"
                               + (" ..." if len(yahoo_only) > 8 else "") + "): Yahoo's events alone, pay dates unknown")
    return done(out)


def _unavailable(out, cfg_all, day, note):
    for eng, cfg in cfg_all.items():
        era = era_of(cfg, day)
        rule, corridor = rule_of(cfg)
        out["engines"][eng] = {"symphony": cfg["symphony"], "version": era["version"], "rule": rule,
                               "corridor": corridor, "status": "unavailable", "note": note}
    return out


# ------------------------------------------------------------------ the pinned path's data
class NotPublished(Exception):
    """the pinned payload for an instant cannot be built YET (the executor retries on the 503)"""

    def __init__(self, detail, error="decision bar not published yet"):
        super().__init__(detail)
        self.error, self.detail = error, detail

    def body(self):
        return {"error": self.error, "detail": self.detail}


class Bars:
    """FMP's traded 1-minute bars as of ONE instant T, for the pinned build of T. load() asks for every
    ticker within the mirror's budget; a ticker whose answer already holds the bar ending at T is never
    asked again (a published bar does not change), so a retry costs only what was still missing.
    quotes() is the preview's `quotes` seam and serves exactly what the last load() read: the settle
    check and the build see the same bars"""

    def __init__(self, T, key, fetch=None, budget=FMP_BUDGET_S):
        self.T, self.key, self.budget = T, key, budget
        self._fetch = fetch or _minutes
        e = sr.et_now(T)
        self.day, self.tz = e.date().isoformat(), e.tzinfo
        self.lock = threading.Lock()
        self.final = {}                # ticker -> bars, once they hold the bar ending at T
        self.q, self.probs = {}, {}    # the last load()'s answer
        self.calls = 0

    def _ends_at_T(self, bars):
        for k, v in (bars or {}).items():
            try:
                if not k.startswith("_") and v and pc.bar_end(self.day, k, self.tz) == self.T:
                    return True
            except (ValueError, IndexError):
                continue
        return False

    def fetch(self, t, d, key):
        with self.lock:
            if t in self.final:
                return self.final[t]
            self.calls += 1
        bars = self._fetch(t, d, key)
        if self._ends_at_T(bars):
            with self.lock:
                self.final[t] = bars
        return bars

    def load(self, tickers):
        """read every ticker's last traded bar ending at or before T. NotPublished while SPY's bar ending
        at T is not in (one call)"""
        try:
            q, probs = pc.minute_quotes({pc.GATE[0]}, self.T, self.key, fetch=self.fetch, budget=self.budget)
        except Exception as exc:  # noqa: BLE001
            raise NotPublished(pc.one_line(exc, 200)) from None
        if q[pc.GATE[0]][1] != self.T:
            raise NotPublished(f"SPY's last traded bar ends {sr.et_now(q[pc.GATE[0]][1]):%H:%M:%S} ET")
        self.q, self.probs = pc.minute_quotes(tickers, self.T, self.key, fetch=self.fetch, budget=self.budget)

    def unsettled(self):
        """None, or why the bar ending at T does not look fully published yet: FMP has not answered for a
        ticker, or too many of the recently traded tickers still end a minute before T"""
        late = sorted(t for t, m in self.probs.items() if m != "no traded bar today")
        if late:
            return f"FMP has not answered for {', '.join(late[:8])}" + (" ..." if len(late) > 8 else "")
        minute = datetime.timedelta(minutes=1)
        at = sum(1 for _, when in self.q.values() if when == self.T)
        lag = sorted(t for t, (_, when) in self.q.items() if when == self.T - minute)
        if lag and len(lag) > LAG_MAX * (at + len(lag)):
            return (f"FMP is still publishing the bar: {len(lag)} of {at + len(lag)} recently traded tickers end a "
                    f"minute earlier ({', '.join(lag[:8])}" + (" ..." if len(lag) > 8 else "") + ")")
        return None

    def quotes(self, tickers, now):
        if pc.GATE[0] not in self.q:
            raise RuntimeError("no SPY 1-minute bar loaded for this instant")
        return ({t: self.q[t] for t in tickers if t in self.q},
                {t: self.probs.get(t, "not asked") for t in tickers if t not in self.q})


class History:
    """Yahoo's daily history per ticker, fetched once per ET day and reused by every pinned build that
    day: it does not change intraday (only today's own bar does, and a pinned build never reads that
    bar). fetch() is the builds' seam: what is cached is used as it is (a decision never waits on Yahoo
    for a ticker it already has), a miss is fetched. refresh() is the warm loop's: an answer that is not
    final yet (no bar for today, or a session short of the previous one) is asked again after RECHECK_S.
    A failure is never kept"""

    def __init__(self, fetch=None, wall=None, clock=time.time):
        self._fetch = fetch or (lambda t: pc.fetch_live(t, timeout=YAHOO_TIMEOUT_S))
        self.wall, self.clock = wall or _utcnow, clock
        self.lock = threading.Lock()
        self.day, self.data, self.calls = None, {}, 0

    def _final(self, r, day):
        adj = r[0]
        return bool(adj) and day in adj and max((d for d in adj if d < day), default=None) == pc.previous_session(day)

    def _get(self, t, again):
        day = sr.et_now(self.wall()).date().isoformat()
        with self.lock:
            if self.day != day:
                self.day, self.data = day, {}
            hit = self.data.get(t)
        if hit is None or (again and not (hit[1] or self.clock() - hit[2] < RECHECK_S)):
            r = self._fetch(t)
            hit = (r, self._final(r, day), self.clock())
            with self.lock:
                self.calls += 1
                if self.day == day:
                    self.data[t] = hit
        adj, raw, meta = hit[0]
        return dict(adj), dict(raw), dict(meta)

    def fetch(self, t):
        return self._get(t, False)

    def refresh(self, t):
        return self._get(t, True)

    def warm(self, tickers):
        """fetch what is missing or not final; {ticker: error} for the failures"""
        return pc.fetch_all(tickers, self.refresh)[1]

    def state(self):
        with self.lock:
            return {"day": self.day, "tickers": len(self.data), "final": sum(1 for h in self.data.values() if h[1]),
                    "calls": self.calls}


class Pinned:
    """the pinned payload per decision instant: built once, one build at a time, then immutable.
    attempt(T) -> payload, or raises NotPublished"""

    def __init__(self, attempt):
        self.attempt = attempt
        self.lock, self.flight = threading.Lock(), threading.Lock()
        self.done, self.builds, self.error = {}, 0, None

    def get(self, T):
        """(payload, None), or (None, the 503 body)"""
        key = _iso(T)
        with self.lock:
            if key in self.done:
                return self.done[key], None
        with self.flight:
            with self.lock:                        # the request ahead of this one may have built it meanwhile
                if key in self.done:
                    return self.done[key], None
                self.builds += 1
            try:
                p = self.attempt(T)
            except NotPublished as exc:
                err = exc.body()
            except Exception as exc:  # noqa: BLE001
                err = {"error": f"brain failed: {pc.one_line(repr(exc))}"}
            else:
                if (p.get("decision_bar") or {}).get("complete"):
                    with self.lock:
                        self.done[key], self.error = p, None
                        for old in sorted(self.done)[:-KEEP]:
                            del self.done[old]
                    return p, None
                err = {"error": (p.get("problems") or ["no decision at that instant"])[0]}
            with self.lock:
                self.error = err.get("detail") or err["error"]
            return None, err

    def state(self):
        with self.lock:
            last = max(self.done) if self.done else None
            return {"instants": sorted(self.done), "built_utc": self.done[last].get("built_utc") if last else None,
                    "builds": self.builds, "last_error": self.error}


def pinned_attempt(history=None, attest=None, key=None, wall=None, fetch_minutes=None, settle_s=SETTLE_S):
    """the attempt(T) of a Pinned: load FMP's bars as of T (kept per T across retries), wait while the
    bar is still being published (at most settle_s past T by the wall clock), then build pinned"""
    wall = wall or _utcnow
    feeds, lock = {}, threading.Lock()

    def attempt(T):
        k = key or os.environ.get("FMP_API_KEY")
        if not k:
            raise NotPublished("the mirror needs FMP's 1-minute bars", "FMP_API_KEY not set")
        with lock:
            bars = feeds.get(T)
            if bars is None:
                bars = feeds[T] = Bars(T, k, fetch_minutes)
                for old in sorted(feeds)[:-KEEP]:
                    del feeds[old]
        bars.load(feed_tickers(sr.load_manifest(), bars.day))
        why = bars.unsettled()
        if why and (wall() - T).total_seconds() < settle_s:
            raise NotPublished(why)
        p = build(T, quotes=bars.quotes, fetch=history.fetch if history is not None else None, pinned=True,
                  attest=attest, wall=wall)
        if why:
            p["problems"].append(f"built {settle_s} s after the instant with the bar not fully published: {why}")
        return p
    return attempt


# ------------------------------------------------------------------ HTTP (stdlib)
class Cache:
    """the latest AD HOC payload (monitoring), recomputed on demand, single flight"""

    def __init__(self, builder=build, clock=time.time):
        self.builder, self.clock = builder, clock
        self.lock = threading.Lock()
        self.flight = threading.Lock()
        self.payload, self.at, self.error = None, 0.0, None

    def _build(self):
        try:
            p = self.builder()
            with self.lock:
                self.payload, self.at, self.error = p, self.clock(), None
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.error = pc.one_line(repr(exc))

    def refresh(self):
        with self.flight:                          # one computation at a time
            self._build()

    def get(self, max_age):
        """(payload, its age in seconds, the last rebuild's error)"""
        def fresh():
            return self.payload is not None and self.clock() - self.at <= max_age
        with self.lock:
            ok = fresh()
        if not ok:
            with self.flight:
                with self.lock:                    # the build this request waited for may be the one it needs
                    ok = fresh()
                if not ok:
                    self._build()
        with self.lock:
            return self.payload, self.clock() - self.at, self.error


def in_window(now=None):
    """from WARM_FROM_MIN minutes before the decision instant to the close of a session (False if the
    calendar says no session)"""
    now = now or _utcnow()
    info = session_info(now)
    if not info.get("session"):
        return False
    start = parse_utc(info["decide_utc"]) - datetime.timedelta(minutes=WARM_FROM_MIN)
    return start <= now < parse_utc(info["close_utc"])


def make_server(port, token, cache, window=in_window, clock_info=session_info, wall=None, pinned=None,
                attest_token="", attests=None, status=None):
    """the HTTP server (not started). GET /health is public; GET /mirror/intents and /mirror/session need
    X-API-Token == token; POST /mirror/attest needs X-Attest-Token == attest_token (constant-time
    compares; an unset token answers 404). pinned: a Pinned (the ?after= path); attests: the
    Attestations POSTs are stored in; status: () -> extra fields for /health; wall: the wall clock (a
    test seam; default the system's UTC)"""
    wall = wall or _utcnow
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

        def _authorized(self, header="X-API-Token", want=token, what="intents disabled (MIRROR_API_TOKEN unset)"):
            """None when the token matches, else the (code, body) to answer with"""
            if not want:
                return 404, {"error": what}
            if not hmac.compare_digest(self.headers.get(header, "").encode(), want.encode()):
                return 401, {"error": "unauthorized"}
            return None

        def do_GET(self):  # noqa: N802
            path, _, query = self.path.partition("?")
            if path == "/health":
                with cache.lock:
                    age = round(cache.clock() - cache.at, 1) if cache.payload else None
                    err = cache.error
                body = {"status": "ok", "service": "composer-brain", "schema": SCHEMA, "in_window": window(),
                        "payload_age_s": age, "last_error": err, "token_set": bool(token),
                        "attest_token_set": bool(attest_token)}
                if pinned is not None:
                    body["pinned"] = pinned.state()
                if status:
                    body.update(status())
                return self._send(200, body)
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
                    if want.second:
                        return self._send(400, {"error": "after must be the end of a 1-minute bar (seconds 00)"})
                    if pinned is None:
                        return self._send(503, {"error": "pinned builds are not configured"})
                    payload, err = pinned.get(want)
                    return self._send(200, payload) if payload is not None else self._send(503, err)
                payload, age, err = cache.get(AD_HOC_TTL_S)
                if payload is None:
                    return self._send(503, {"error": err or "no payload yet"})
                return self._send(200, dict(payload, served_age_s=round(age, 1)))
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path.partition("?")[0] != "/mirror/attest":
                return self._send(404, {"error": "not found"})
            refused = self._authorized("X-Attest-Token", attest_token, "attestation disabled (MIRROR_ATTEST_TOKEN unset)")
            if refused:
                return self._send(*refused)
            if attests is None:
                return self._send(503, {"error": "attestations are not configured"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n <= ATTEST_MAX_BYTES:
                    raise ValueError("a JSON body is required")
                cfg_all = sr.load_manifest()
                day, stored, ignored = attests.put(json.loads(self.rfile.read(n)), wall(), cfg_all)
            except ValueError as exc:               # json.JSONDecodeError included
                return self._send(400, {"error": pc.one_line(exc, 200)})
            return self._send(200, {"ok": True, "session": day, "stored": stored, "ignored": ignored,
                                    "sync": sync_block(cfg_all, day, attests)})

        def log_message(self, fmt, *args):         # no access log: the tokens ride in headers, not the URL
            return
    return ThreadingHTTPServer(("0.0.0.0", port), H)


def warm_once(history, now=None):
    """inside the window: fetch the session's Yahoo history that is missing or not final, for every
    ticker a build may read (the same-index siblings included, so the decision itself asks Yahoo for
    nothing); FMP's dividend and split lists ride along, once per ticker per day. True if it was asked"""
    now = now or _utcnow()
    if not in_window(now):
        return False
    history.warm(feed_tickers(sr.load_manifest(), sr.et_now(now).date().isoformat()))
    return True


def serve(port):
    attests, history = Attestations(), History()
    pinned = Pinned(pinned_attempt(history, attests))
    cache = Cache(lambda: build(attest=attests))

    def loop():
        while True:
            try:
                warm_once(history)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(WARM_EVERY_S)

    def status():
        today = attests.get(sr.et_now(_utcnow()).date().isoformat()) or {}
        return {"history": history.state(), "attested": sorted(today.get("engines") or {}),
                "require_attestation": require_attestation()}
    threading.Thread(target=loop, daemon=True).start()
    make_server(port, os.environ.get("MIRROR_API_TOKEN", ""), cache, pinned=pinned,
                attest_token=os.environ.get("MIRROR_ATTEST_TOKEN", ""), attests=attests, status=status).serve_forever()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--serve" in argv:
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else int(os.environ.get("PORT", "10000"))
        return serve(port)
    if "--at" in argv:
        payload = build(parse_at(argv[argv.index("--at") + 1]), pinned=True)
    else:
        payload = build()
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    sys.stdout.flush()
    os._exit(code or 0)                             # FMP fetches past the budget may still be in flight
