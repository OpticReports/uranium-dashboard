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
and prices, and on fully published bars the live answer equals `--at` afterwards (see THE ALLOWANCE).
FMP IS A HARD DEPENDENCY of a pinned decision: there is no Yahoo fallback, so FMP down at the decision
instant means no trade that session.

/mirror/intents?after=T answers 503 until the decision is SETTLED, and only a settled payload is cached
(by T; never rebuilt, and never evicted while its ET day is among the KEEP newest held; concurrent
requests share one build):
  - "decision bar not published yet" until SPY's traded bar ending at T is in, and, for at most SETTLE_S,
    while FMP is still publishing that minute (it publishes ticker by ticker over 10-25 s: preclose-ledger
    2026-11-09 15:16:15, SPY had the bar and 23 of 48 tickers did not)
  - "decision not settled yet" while FMP has not answered for a ticker a tree reads or can hold, or an
    engine is unavailable for a FEED reason (SPY's bar, breadth, a decision ticker priced by an
    estimate, a price missing): a later request rebuilds, at most every REBUILD_EVERY_S.
  From T + SETTLE_WAIT_S the wait is scoped to the engine. IF the book-level conditions hold (SPY priced
  from the decision bar, breadth at or above BREADTH_MIN), the build is settled as it is: an engine
  still down for a feed reason OF ITS OWN (a decision ticker unanswered or on an estimate, its own
  breadth, a missing price) is published unavailable with the reason, the others ok, and `problems`
  names what was given up on: one halted ticker must not cost the other sleeves their session. If the
  book-level conditions do NOT hold (the feed as a whole is down) the 503 goes on, and the executor's
  plan-by deadline turns it into a recorded no-trade. (An earlier give-up, at T+45 s whatever the
  feed's state, went out in a 50-second run of FMP 429s with every engine unavailable and was cached
  for the session.) A ticker no approved tree reads or can hold (a same-index sibling asked only to
  rebuild a stale price from) never holds the payload back.
  An engine unavailable for a reason the feed cannot change (tree drift, paused, a history a session
  short, no attestation where one is required) on a healthy feed IS a settled answer at once.
THE ALLOWANCE: a build goes while up to LAG_MAX of the recently traded tickers are still a bar behind
(and, past SETTLE_S, with more, said in `problems`), so a live payload's PRICES for those tickers can
differ slightly from a later rebuild or `--at` of the same instant (the round-2 review: targets did not
move in about 1,000 lag sets tried on the record).

NEVER A TRADEABLE DECISION ON DEAD DATA (measured on 83 sessions of FMP minutes, 2026-07-15..11-09):
  - pinned: every engine is unavailable unless SPY's price is from the bar ending at T (83 of 83 had it)
  - every engine is unavailable unless at least BREADTH_MIN of the trees' tickers traded within
    BREADTH_AGE_S of the instant (measured share: 92-100%, so a stalled feed or a shut market, 0%, is
    refused and no real session was)
  - an engine is unavailable when a decision ticker it reads is priced by an ESTIMATE, i.e. anything
    but a trade of its own today: rebuilt from a sibling fund (also when the fund did trade earlier in
    the day), or an earlier close carried (0 of 327 real engine-sessions); when fewer than
    ENGINE_BREADTH_MIN of its decision tickers traded within BREADTH_AGE_S (0 of 327); or when its
    history is a session short
  A thin fund's own last trade, however old, is used and named (PEJ's was over 15 minutes old on 5
  sessions): Composer trades those days, and refusing them would have cost 1.8% of engine-sessions
  (9.6% at a two-minute limit).
  ON AN NYSE HALF-DAY (shadow_runner.HALF_DAYS: a 13:00 close, the instant 12:54:00) FMP can stop
  carrying VOLUME for part of the book while it still publishes the bars. In its archive of 2025's three
  half-days the volume per minute in the bars after 12:45 falls to 0.31-0.52 of the 12:30-12:44 rate as
  a PER-TICKER MEDIAN (it rises into every other close: 1.8-2.9 on 2024's half-days, 0.7-1.0 at midday on
  the 2025 sessions next to them; in TOTAL volume 11-28 and 12-24 still rose, 1.65x and 1.76x, on the
  busiest funds), and 5-13 of the 62 tickers, SPY itself on 2025-11-28, carry no volume at all after 12:45. The
  rules above refused two of the three (07-03: 37 of 48 traded in the 2 minutes; 11-28: SPY's last traded
  bar ends 12:46) and passed 12-24 by one ticker. So on a half-day, and only then, a ticker counts toward
  both breadths when FMP published a bar WITHOUT volume for it within BREADTH_AGE_S of the instant, its
  own last trade is at most QUIET_TRADE_MAX_S old (the preview's FRESH_MIN: the price it is given is that
  trade's, as on any day), AND at least one of its bars without volume since that trade, up to the
  instant, closed off the trade's price (any bar, not the one at the instant: a live fund can close a
  minute where it last traded). A feed that keeps publishing bars at volume 0 and a frozen price is
  frozen, not quiet: every ticker so counted on 2025's half-days moved. SPY's decision bar counts as
  published when FMP's SPY bar ending AT the instant has no volume and SPY passes the same tests. All of
  it applies only while at least HALF_DAY_REAL_MIN of the trees' tickers REALLY traded within
  BREADTH_AGE_S (2025's half-days: 77%, 75%, 81%): below that the full-day rule alone decides, and
  refuses. Every ticker counted that way is named in `problems`, and quotes.breadth then gives the real
  trades ('recent') and the counted-on-bars-without-volume ('leaned') apart. No bar near the instant, a
  last trade older than that, bars whose price never moved, or too few real trades count as on a full
  day: a dead, stale or frozen feed on a half-day is still refused, and a full day's payload is unchanged.

THE TREE-VERSION GATE. A Composer-keyed job (mirror_attest.py) posts each symphony's live version and
the sha1 of its canonical live tree (shadow_runner.tree_sha1, the one function used for the approved
tree too). `sync` says per engine ok / drift / none; drift makes the engine unavailable; none (no
attestation for the session) trades with a line in `problems`, or is unavailable when
MIRROR_REQUIRE_ATTESTATION is set. An engine attested paused is unavailable (Composer will not
rebalance it). An "ok" attested more than MIRROR_ATTEST_MAX_AGE_S (default 3600) before the instant is
too old to vouch for it and counts as none (attested_utc still shown; a drift or a pause stays one
however old). An attestation posted AFTER the pinned payload for the instant was cached is NOT in that
payload (it is immutable): the POST answers "pinned_already_built": true so the routine can say so.

DIVIDENDS YAHOO HAS NOT BOOKED are applied to the history from FMP's lists (shadow_runner.parse_daily;
each one applied is named in `problems`). Where FMP's lists could not be read for a ticker the history
is Yahoo's alone: the payload then says "actions_complete": false and names the tickers.

Payload (schema 2): {schema, kind, session, pinned, asof_utc, asof_et, built_utc, decision_bar:
{end_utc, spy_utc, complete} | null, replay, close_et, engines: {NAME: {status: "ok" | "unavailable",
symphony, version, rule: "daily" | "threshold", corridor, target: {ticker: weight}, label, stale,
caveats, note}}, prices: {ticker: raw price} for every ticker of ANY era of the manifest, price_times:
{ticker: UTC time of the trade or bar end the price is from}, price_notes: {ticker: why a price is an
estimate or old}, dividends: [{ticker, ex_date, pay_date | null, amount}], splits: [{ticker, date,
ratio}] (the last ACTIONS_DAYS calendar days), actions_complete (FMP's dividend and split lists were
read for every ticker), sync, quotes, problems}. quotes.breadth: {recent (the trees' tickers with a trade
within within_s of the instant), of, share (the share counted, against min_share), min_share, within_s},
and on a half-day whose rule weighed bars without volume also leaned (counted on them), counted (recent +
leaned: share's numerator), frozen (bars without volume near the instant whose price never moved: not
counted), real_share (recent / of) and real_min_share. On a half-day decision_bar.complete can hold with
spy_utc before end_utc (by at most QUIET_TRADE_MAX_S): SPY priced at its own last trade.
`prices` are the executor's sizing reference, never a fill. Nothing here is a trade instruction for Composer.
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
QUIET_TRADE_MAX_S = pc.FRESH_MIN * 60   # half-day only: a ticker FMP shows a bar WITHOUT volume for near the instant
                          # counts as trading when its own last trade is at most this old (the preview's freshness limit)
HALF_DAY_REAL_MIN = 0.50  # ... and only while at least this share of the trees' tickers REALLY traded (a bar with volume)
                          # within BREADTH_AGE_S of the instant (2025's three half-days: 77%, 75%, 81%)
QUIET_MOVE_TOL = 1e-9     # a bar without volume "moved" off its ticker's last trade when its close differs from that
                          # trade's by more than this fraction (float noise only: a cent on a $1,000 fund is 1e-5)
LAG_MAX = 0.15            # still publishing: more than this share of the recently traded tickers have their last
                          # bar ending a minute BEFORE the instant (complete days: median 2%, max 6.5% of 83)
SETTLE_S = 45             # seconds after the instant a bar still being published is waited for; then what FMP
                          # has ANSWERED is used (a ticker it has not answered for is waited for without limit)
REBUILD_EVERY_S = 10      # an unsettled pinned decision is tried again at most this often
SETTLE_WAIT_S = 120       # seconds after the instant the whole payload waits for an engine's own feed trouble (an
                          # unanswered or estimated decision ticker, a missing price); from then on, if SPY's bar and
                          # the book's breadth are in order, that engine is published unavailable and the rest trade
ATTEST_MAX_AGE_S = 3600   # an "ok" attested longer than this before the instant counts as none
                          # (env MIRROR_ATTEST_MAX_AGE_S)
ACTIONS_DAYS = 10         # dividends and splits published: ex-date within this many calendar days of the session
WARM_FROM_MIN = 30        # --serve: Yahoo's history is fetched from this many minutes before the decision instant
                          # (several times shadow_runner.ACTIONS_RETRY, so a burst of FMP list failures is retried)
WARM_EVERY_S = 60         # ... and what is still missing or incomplete is asked again this often
RECHECK_S = 60            # a history that is not final (no bar for today yet, or a session short) is refetched after this
YAHOO_TIMEOUT_S = 10      # one Yahoo history call from the serving brain (two attempts)
AD_HOC_TTL_S = 60         # an ad hoc (unpinned) payload is reused for this long
ATTEST_MAX_BYTES = 65536
KEEP = 4                  # ET days of pinned payloads / attested sessions kept in memory (today's always)


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


def tree_universe(cfg_all, day):
    """the tickers the trees in use on `day` read or hold, and SPY: the breadth's universe (preclose.preview's
    'tick', on the same era_of)"""
    out = {pc.GATE[0]}
    for cfg in cfg_all.values():
        out |= sr.tree_tickers(sr.load_tree(era_of(cfg, day)))
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


def attest_max_age():
    """seconds an 'ok' attestation may precede the instant (env MIRROR_ATTEST_MAX_AGE_S; default ATTEST_MAX_AGE_S)"""
    try:
        v = float(os.environ.get("MIRROR_ATTEST_MAX_AGE_S", "").strip() or ATTEST_MAX_AGE_S)
    except ValueError:
        return float(ATTEST_MAX_AGE_S)
    return v if v > 0 else float(ATTEST_MAX_AGE_S)


def attest_age(row, asof):
    """seconds from a sync row's attestation to `asof` (negative: attested after it); None if never attested"""
    try:
        return (asof - parse_utc(row["attested_utc"])).total_seconds()
    except (TypeError, ValueError, KeyError):
        return None


def sync_block(cfg_all, day, attest=None, asof=None):
    """{NAME: {state, approved_version, approved_sha1, live_version, attested_utc[, paused]}}: 'ok' the
    attested live tree hashes equal to the approved tree in use on `day`; 'drift' it does not; 'none'
    nothing was attested for that session, or (asof given) the 'ok' is older than attest_max_age()
    before `asof`: too old to vouch for the instant, with attested_utc still shown. A drift or a pause
    is kept however old (it is a reason NOT to trade). attest: an Attestations (or any .get(day))"""
    rec = (attest.get(day) if attest is not None else None) or {}
    limit = attest_max_age()
    out = {}
    for eng, cfg in cfg_all.items():
        era = era_of(cfg, day)
        a = (rec.get("engines") or {}).get(eng)
        row = {"state": "none", "approved_version": era["version"], "approved_sha1": approved_sha1(era),
               "live_version": None, "attested_utc": None}
        if a:
            row.update(state="ok" if a.get("tree_sha1") == row["approved_sha1"] else "drift",
                       live_version=a.get("version"), attested_utc=a.get("attested_utc"))
            age = attest_age(row, asof) if asof is not None else None
            if row["state"] == "ok" and age is not None and age > limit:
                row["state"] = "none"
            if a.get("paused"):
                row["paused"] = True
        out[eng] = row
    return out


def require_attestation():
    return os.environ.get("MIRROR_REQUIRE_ATTESTATION", "").strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ the payload
def _minutes(t, d, key):
    """FMP's traded 1-minute bars, one short attempt (the mirror's decision cannot wait on a retry); the
    bars it published WITHOUT volume ride along under '_quiet', {bar start: close} (the half-day rule)"""
    return sr.fetch_minutes(t, d, key, tries=1, traded=True, timeout=FMP_TIMEOUT_S, quiet=True)


def half_day(day):
    """the exchange calendar's 13:00 close (shadow_runner.HALF_DAYS): the only session the half-day rule
    of the module docstring applies to"""
    return sr.session_close(day) != "16:00"


def _pos(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def quiet_evidence(bars, day, tz, now):
    """the half-day evidence in ONE FMP answer for a ticker (fetch_minutes quiet=True: its traded bars, and
    under '_quiet' {bar start: close} the bars it published WITHOUT volume), as of `now` on session `day`
    (tz: ET): None when no bar without volume ends at or before `now`; else (the UTC end of the last one,
    moved). moved: at least one bar without volume ending after the ticker's last TRADED bar (the last
    ending at or before `now`) and at or before `now` closed off that trade's price by more than
    QUIET_MOVE_TOL. Any bar, not the one at the instant: a live fund can close a minute at its last trade's
    price; a feed replaying the last print at volume 0 never moves. No traded bar: moved is False"""
    quiet = bars.get("_quiet") if isinstance(bars, dict) else None
    if not isinstance(quiet, dict):
        return None

    def end_of(hm):
        try:
            return pc.bar_end(day, hm, tz)
        except (ValueError, IndexError, TypeError, AttributeError):
            return None
    trade = None                                   # (end, close) of the last traded bar ending at or before now
    for hm, c in bars.items():
        if not isinstance(hm, str) or hm.startswith("_") or not _pos(c):
            continue
        end = end_of(hm)
        if end is not None and end <= now and (trade is None or end > trade[0]):
            trade = (end, float(c))
    last, moved = None, False
    for hm, c in quiet.items():
        end = end_of(hm) if isinstance(hm, str) and _pos(c) else None
        if end is None or end > now:
            continue
        if last is None or end > last:
            last = end
        if trade is not None and end > trade[0] and abs(float(c) - trade[1]) > QUIET_MOVE_TOL * trade[1]:
            moved = True
    return None if last is None else (last, moved)


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


def build(now=None, quotes=None, fetch=None, pinned=False, attest=None, wall=None, budget=None, diag=None, quiet=None):
    """the payload at `now` (UTC datetime; default the wall clock).
    pinned=False: an ad hoc read for monitoring (a `now` more than 5 minutes behind the wall clock is a
    replay and reads nothing stamped later). pinned=True: the decision AS OF `now` exactly (see the
    module docstring); 'replay' is then True only when `now` is on another ET day than the wall clock.
    quotes / fetch: the preview's seams (FMP minutes; Yahoo history); attest: an Attestations; wall: the
    wall clock (a test seam); budget: seconds for FMP's minutes (default FMP_BUDGET_S); diag: a dict
    that receives 'feed' {engine: why it is unavailable for a reason a later read of the feed could
    change} (the pinned path settles on it; not part of the payload). quiet: (tickers, now) -> {ticker:
    quiet_evidence(...) = (UTC end of its last 1-minute bar WITHOUT volume ending at or before now, moved)},
    read only on a half-day (the module docstring); default: the quotes seam's own `quiet` attribute, or,
    when this build reads FMP itself, what those reads saw."""
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
           "dividends": [], "splits": [], "actions_complete": False, "sync": sync_block(cfg_all, day0, attest, now),
           "quotes": None, "problems": []}

    def done(o):
        o["built_utc"] = _iso(wall())
        return o
    why = calendar_reason(day0)
    if why:
        out["problems"].append(why)
        return done(_unavailable(out, cfg_all, day0, "the exchange calendar does not cover this date"))
    if quotes is None:
        read = _minutes
        if half_day(day0):                         # FMP's answers kept: the bars without volume (the half-day rule)
            heard = {}

            def _read(t, d, key):
                bars = _minutes(t, d, key)
                heard[t] = bars
                return bars
            read = _read
            if quiet is None:
                quiet = lambda tickers, at: {t: x for t in tickers                              # noqa: E731
                                             for x in [quiet_evidence(heard.get(t), day0, e.tzinfo, at)] if x is not None}
        quotes = pc.fmp_quotes(budget=FMP_BUDGET_S if budget is None else budget, fetch=read)   # None without a key
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
    out["sync"] = sync_block(cfg_all, day, attest, now)
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
    still = {}                                     # half-day: {ticker: (end of its last bar WITHOUT volume, moved)}
    if half_day(day):
        src = quiet if quiet is not None else getattr(quotes, "quiet", None)
        try:
            got = (src(sorted(set(tick) | {pc.GATE[0]}), now) or {}) if callable(src) else {}
            still = {t: (v[0], v[1] is True) for t, v in got.items()
                     if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], datetime.datetime) and v[0] <= now}
        except Exception:  # noqa: BLE001
            still = {}

    def age(t):
        """seconds from the trade t's price is from to the instant; None when it is not a trade of today"""
        kind, when = stamps.get(t) or (None, None)
        return (now - when).total_seconds() if kind == "trade" and isinstance(when, datetime.datetime) else None

    def real(t):
        """t REALLY traded (a bar with volume) within BREADTH_AGE_S of the instant: the full-day rule"""
        a = age(t)
        return a is not None and a <= BREADTH_AGE_S

    def quiet_near(t):
        """half-day only (still is empty otherwise): FMP published a bar for t WITHOUT volume within
        BREADTH_AGE_S of the instant, and t's own last trade, its price, is at most QUIET_TRADE_MAX_S old
        (whether one of its bars without volume since moved off that price: still[t][1])"""
        a, q = age(t), still.get(t)
        return a is not None and a <= QUIET_TRADE_MAX_S and q is not None and (now - q[0]).total_seconds() <= BREADTH_AGE_S
    n_real = sum(1 for t in tick if real(t))
    relax = bool(still) and bool(tick) and n_real >= HALF_DAY_REAL_MIN * len(tick)   # below the floor: the full-day rule

    def recent(t):
        return real(t) or (relax and quiet_near(t) and still[t][1])
    live = [t for t in tick if recent(t)]
    share = len(live) / len(tick) if tick else 0.0
    weighed = sorted(t for t in tick if quiet_near(t) and not real(t))  # what the half-day rule weighed ...
    leaned = [t for t in weighed if recent(t)]                          # ... counted
    frozen = [t for t in weighed if not still[t][1]]                    # ... its bars never moved: not counted
    breadth = out["quotes"]["breadth"] = {"recent": len(live), "of": len(tick), "share": round(share, 4),
                                          "min_share": BREADTH_MIN, "within_s": BREADTH_AGE_S}
    halt, half, spy_quiet = [], [], False
    if pinned:
        kind, when = stamps.get(pc.GATE[0]) or (None, None)
        spy = when if kind == "trade" and isinstance(when, datetime.datetime) else None
        sq = still.get(pc.GATE[0])
        spy_quiet = (spy is not None and spy != now and sq is not None and sq[0] == now      # half-day: SPY's bar at the
                     and (now - spy).total_seconds() <= QUIET_TRADE_MAX_S)                    # instant, without volume
        bar = spy == now or (spy_quiet and relax and sq[1])
        out["decision_bar"] = {"end_utc": _iso(now), "spy_utc": _iso(spy) if spy else None, "complete": bar}
        if not bar:
            halt.append(f"SPY's price is not from the bar ending {e:%H:%M:%S} ET (its last traded bar ends "
                        f"{sr.et_now(spy).strftime('%H:%M:%S') if spy else 'nowhere today'})")
            if spy_quiet and relax:
                half.append(f"half-day: FMP's SPY bar ending {e:%H:%M:%S} ET has no volume, but none of SPY's bars without "
                            f"volume since its last trade (bar ending {sr.et_now(spy):%H:%M:%S} ET) moved off that trade's "
                            f"price: a frozen feed is not taken as the decision bar")
        elif spy != now:
            half.append(f"half-day: FMP's SPY bar ending {e:%H:%M:%S} ET has no volume; the decision bar is taken as "
                        f"published and SPY is priced at its own last trade (bar ending {sr.et_now(spy):%H:%M:%S} ET; a "
                        f"bar without volume since moved off that price)")
    if share < BREADTH_MIN:
        halt.append(f"the feed looks dead: {len(live)} of {len(tick)} tickers traded in the {BREADTH_AGE_S // 60} minutes "
                    f"to {e:%H:%M:%S} ET" + (f" ({len(leaned)} of them counted on bars without volume, the half-day rule)"
                                             if leaned else ""))
    if weighed or spy_quiet:                       # the half-day rule weighed bars without volume: its counts apart
        breadth.update(recent=n_real, leaned=len(leaned), counted=len(live), frozen=len(frozen),
                       real_share=round(n_real / len(tick), 4), real_min_share=HALF_DAY_REAL_MIN)
        if not relax:
            half.append(f"half-day ({out['close_et']} close): only {n_real} of {len(tick)} tickers really traded in the "
                        f"{BREADTH_AGE_S // 60} minutes to {e:%H:%M:%S} ET, below the {HALF_DAY_REAL_MIN:.0%} the half-day "
                        f"rule needs: bars without volume are not counted (the full-day rule decides)")
    if leaned:
        half.append(f"half-day ({out['close_et']} close): {len(leaned)} ticker(s) counted as trading on a bar FMP published "
                    f"without volume near {e:%H:%M:%S} ET, each priced at its own last trade (at most "
                    f"{QUIET_TRADE_MAX_S // 60} min old; the bar it ends) and moved off it since; {n_real} of {len(tick)} "
                    f"really traded in the {BREADTH_AGE_S // 60} minutes: "
                    + ", ".join(f"{t} {sr.et_now(stamps[t][1]):%H:%M}" for t in leaned))
    if frozen:
        half.append(f"half-day ({out['close_et']} close): {len(frozen)} ticker(s) with bars without volume near "
                    f"{e:%H:%M:%S} ET NOT counted: none of their bars since their last trade moved off its price (a "
                    f"frozen feed): " + ", ".join(f"{t} {sr.et_now(stamps[t][1]):%H:%M}" for t in frozen))
    out["problems"] += halt + half
    need = require_attestation()
    unattested, aged = [], []
    feed = diag.setdefault("feed", {}) if diag is not None else {}
    if diag is not None:
        diag["halt"] = list(halt)                  # the book-level reasons: they hold EVERY engine
    silent = {t for t, m in (cap.get("problems") or {}).items() if m != "no traded bar today"}   # FMP gave no answer
    for eng, cfg in cfg_all.items():
        era = era_of(cfg, day)
        rule, corridor = rule_of(cfg)
        base_row = {"symphony": cfg["symphony"], "version": era["version"], "rule": rule, "corridor": corridor}
        r = rows.get(eng)
        if not r or r.get("status") != "ok" or not r.get("target"):
            note = (r or {}).get("note") or "no decision"
            out["engines"][eng] = dict(base_row, status="unavailable", note=note)
            if halt or note.startswith(("no prices for", "no close on")):      # a price the feed did not give
                feed[eng] = "; ".join(halt + [note])
            continue
        dec = sorted(sr.decision_tickers(sr.load_tree(era)))
        why = list(halt)                           # the reasons a later read of the feed could change come first
        est = [t for t in dec if (stamps.get(t) or (None,))[0] != "trade"]
        if est:
            mute, none = [t for t in est if t in silent], [t for t in est if t not in silent and t not in traded]
            why.append(f"{', '.join(est)} priced by an estimate, not a trade of its own today"
                       + (f" ({', '.join(mute)}: FMP did not answer)" if mute else "")
                       + (f" ({', '.join(none)}: no trade today)" if none else ""))
        n_live = sum(recent(t) for t in dec)
        if dec and n_live < ENGINE_BREADTH_MIN * len(dec):
            why.append(f"{n_live} of its {len(dec)} decision tickers traded in the last {BREADTH_AGE_S // 60} minutes")
        if why:
            feed[eng] = "; ".join(why)
        hit = [t for t in dec if t in short]
        if hit:
            why.append(f"the history of {', '.join(hit)} lacks the previous session (indicators a session short)")
        s = out["sync"][eng]
        waited = attest_age(s, now)
        if waited is not None and waited > attest_max_age():
            aged.append(f"{eng} {waited:.0f} s")
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
    if aged:
        out["problems"].append(f"the attestation of the live logic is older than {attest_max_age():.0f} s at the instant "
                               f"({', '.join(aged)}): an ok that old counts as none")
    if unattested:
        out["problems"].append(f"no attestation of the live logic for {day}: {', '.join(unattested)} on the approved "
                               f"trees, unverified")

    # ---- dividends and splits of the last ACTIONS_DAYS days (pure data: the executor does the accounting)
    lo = (datetime.date.fromisoformat(day) - datetime.timedelta(days=ACTIONS_DAYS)).isoformat()
    unread, yahoo_only, applied = [], [], []
    for t in sorted(seen):                         # what FMP's lists added to a history this decision read
        ca = seen[t].get("corporateActions")
        for x in (ca.get("applied") or []) if isinstance(ca, dict) else []:
            applied.append(f"{t} {x.get('kind')} {x.get('date')} {x.get('amount')}")
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
    out["actions_complete"] = not unread and not yahoo_only
    if unread:
        out["problems"].append(f"dividends and splits not read for {len(unread)} ticker(s): {', '.join(unread)}")
    if yahoo_only:
        out["problems"].append(f"FMP's dividend and split lists not read for {len(yahoo_only)} ticker(s) ({', '.join(yahoo_only)}): "
                               f"their history and events are Yahoo's alone (a dividend Yahoo has not booked is "
                               f"missing; pay dates unknown)")
    if applied:
        out["problems"].append(f"history repaired from FMP's lists (events Yahoo has not booked): {'; '.join(applied)}")
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
    """the pinned payload for an instant cannot be built YET (the executor retries on the 503).
    retry_s: the next attempt is not made before this many seconds (0: on the next request)"""

    def __init__(self, detail, error="decision bar not published yet", retry_s=0):
        super().__init__(detail)
        self.error, self.detail, self.retry_s = error, detail, retry_s

    def body(self):
        return {"error": self.error, "detail": self.detail}


class NotSettled(NotPublished):
    """the feed is not whole yet (a ticker unanswered, or an engine unavailable for a feed reason), and
    it is either too early to give up on one engine (SETTLE_WAIT_S) or the trouble is book-wide: nothing
    is cached, and the decision is tried again in REBUILD_EVERY_S"""

    def __init__(self, detail):
        super().__init__(detail, "decision not settled yet", REBUILD_EVERY_S)


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
        self.got = {}                  # ticker -> its latest answer (the bars without volume, with their closes, ride on
                                       # it: '_quiet')
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
        final = self._ends_at_T(bars)
        with self.lock:
            self.got[t] = bars
            if final:
                self.final[t] = bars
        return bars

    def quiet(self, tickers, now):
        """{ticker: quiet_evidence(...) = (UTC end of its last bar WITHOUT volume ending at or before now,
        moved)} in what was read: the evidence build() weighs on a half-day (the module docstring)"""
        with self.lock:
            got = {t: self.got.get(t) for t in tickers}
        return {t: x for t, b in got.items() for x in [quiet_evidence(b, self.day, self.tz, now)] if x is not None}

    def load(self, tickers, tick=None):
        """read every ticker's last traded bar ending at or before T. NotPublished while SPY's bar ending
        at T is not in (one call); on a half-day, a SPY bar ending at T WITHOUT volume is in when SPY's
        own last trade is at most QUIET_TRADE_MAX_S old and one of SPY's bars without volume since that
        trade moved off its price, and - once the book is read - while at least HALF_DAY_REAL_MIN of `tick`
        (the trees' tickers: tree_universe) REALLY traded within BREADTH_AGE_S of T; below that floor the
        answer is the full-day one, word for word (build() takes the same rule)"""
        try:
            q, probs = pc.minute_quotes({pc.GATE[0]}, self.T, self.key, fetch=self.fetch, budget=self.budget)
        except Exception as exc:  # noqa: BLE001
            raise NotPublished(pc.one_line(exc, 200)) from None
        spy = q[pc.GATE[0]][1]
        if spy != self.T:
            ev = self.quiet([pc.GATE[0]], self.T).get(pc.GATE[0]) if half_day(self.day) else None
            at_T = ev is not None and ev[0] == self.T and (self.T - spy).total_seconds() <= QUIET_TRADE_MAX_S
            if not (at_T and ev[1]):
                raise NotPublished(f"SPY's last traded bar ends {sr.et_now(spy):%H:%M:%S} ET"
                                   + (" (half-day: FMP's SPY bar ending at the instant has no volume, and none of SPY's "
                                      "bars without volume since that trade moved off its price: a frozen feed)"
                                      if at_T else ""))
        self.q, self.probs = pc.minute_quotes(tickers, self.T, self.key, fetch=self.fetch, budget=self.budget)
        now_spy = (self.q.get(pc.GATE[0]) or (None, spy))[1]
        if now_spy != self.T and tick is not None:      # SPY's decision bar leans on the half-day rule: its floor
            tick = sorted(set(tick))
            real = sum(1 for t in tick if t in self.q and (self.T - self.q[t][1]).total_seconds() <= BREADTH_AGE_S)
            if not tick or real < HALF_DAY_REAL_MIN * len(tick):
                raise NotPublished(f"SPY's last traded bar ends {sr.et_now(now_spy):%H:%M:%S} ET")

    def unanswered(self, matter=None):
        """None, or the tickers FMP has not answered for (refused, failed, slower than the budget).
        matter: only these count (the pinned path passes every ticker a tree reads or can hold: a
        sibling asked only to rebuild a stale price from never holds a decision back)"""
        late = sorted(t for t, m in self.probs.items() if m != "no traded bar today" and (matter is None or t in matter))
        if late:
            return f"FMP has not answered for {', '.join(late[:8])}" + (f" ... ({len(late)} tickers)" if len(late) > 8 else "")
        return None

    def lagging(self):
        """None, or that too many of the recently traded tickers still end a minute before T (FMP is
        still publishing the bar)"""
        minute = datetime.timedelta(minutes=1)
        at = sum(1 for _, when in self.q.values() if when == self.T)
        lag = sorted(t for t, (_, when) in self.q.items() if when == self.T - minute)
        if lag and len(lag) > LAG_MAX * (at + len(lag)):
            return (f"FMP is still publishing the bar: {len(lag)} of {at + len(lag)} recently traded tickers end a "
                    f"minute earlier ({', '.join(lag[:8])}" + (" ..." if len(lag) > 8 else "") + ")")
        return None

    def unsettled(self):
        """None, or why the bar ending at T does not look fully published yet"""
        return self.unanswered() or self.lagging()

    def quotes(self, tickers, now):
        if pc.GATE[0] not in self.q:
            raise RuntimeError("no SPY 1-minute bar loaded for this instant")
        return ({t: self.q[t] for t in tickers if t in self.q},
                {t: self.probs.get(t, "not asked") for t in tickers if t not in self.q})


class History:
    """Yahoo's daily history per ticker, fetched once per ET day and reused by every pinned build that
    day: it does not change intraday (only today's own bar does, and a pinned build never reads that
    bar). An answer is FINAL when it has a bar for today, reaches the previous session, and FMP's
    dividend and split lists were read for it (the repair of what Yahoo has not booked rides on the same
    fetch: a history taken while FMP's lists failed is Yahoo's alone). refresh() is the warm loop's
    seam: an answer that is not final is asked again after RECHECK_S. fetch() is the builds': what is
    cached is used as it is (a decision does not wait on Yahoo for a bar), EXCEPT an answer whose FMP
    lists are still unread, which is asked again after RECHECK_S, the cached one standing if that
    fails. A miss is fetched; a failure is never kept"""

    def __init__(self, fetch=None, wall=None, clock=None):
        self._fetch = fetch or (lambda t: pc.fetch_live(t, timeout=YAHOO_TIMEOUT_S))
        self.wall = wall or _utcnow
        self.clock = clock or (lambda: self.wall().timestamp())   # RECHECK_S runs on the same clock as the day
        self.lock = threading.Lock()
        self.day, self.data, self.calls = None, {}, 0

    @staticmethod
    def lists_read(r):
        """FMP's dividend and split lists were read for this answer (or there is no key to read them
        with, or the source carries no events at all: nothing a retry could add)"""
        ca = r[2].get("corporateActions") if len(r) > 2 and isinstance(r[2], dict) else None
        return not isinstance(ca, dict) or bool(ca.get("fmp")) or not os.environ.get("FMP_API_KEY")

    def _final(self, r, day):
        adj = r[0]
        return (bool(adj) and day in adj and max((d for d in adj if d < day), default=None) == pc.previous_session(day)
                and self.lists_read(r))

    def _get(self, t, warm):
        day = sr.et_now(self.wall()).date().isoformat()
        with self.lock:
            if self.day != day:
                self.day, self.data = day, {}
            hit = self.data.get(t)
        due = hit is not None and not hit[1] and self.clock() - hit[2] >= RECHECK_S
        if hit is None or (due and (warm or not self.lists_read(hit[0]))):
            try:
                r = self._fetch(t)
            except Exception:  # noqa: BLE001
                if hit is None or warm:
                    raise
                r = hit[0]                           # a build keeps what it has; asked again after RECHECK_S
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
                    "lists_unread": sorted(t for t, h in self.data.items() if not self.lists_read(h[0])), "calls": self.calls}


class Pinned:
    """the pinned payload per decision instant: one attempt at a time; a SETTLED payload is cached and
    then immutable. Eviction is by ET DAY, the newest KEEP days kept: no instant can be later than the
    wall clock, so today's instants are always among them and are never evicted, however many other
    instants are asked for (evicting the oldest INSTANTS dropped the decision instant first, and the
    next request for it rebuilt it on moved bars). attempt(T) -> a settled payload, or raises
    NotPublished / NotSettled; while it raises with retry_s the answer stands for that long and no new
    attempt is made (requests that waited on the attempt in flight get its answer)"""

    def __init__(self, attempt, wall=None):
        self.attempt = attempt
        self.wall = wall or getattr(attempt, "wall", None) or _utcnow
        self.lock, self.flight = threading.Lock(), threading.Lock()
        self.done, self.hold, self.builds, self.error = {}, {}, 0, None

    def _evict(self):
        day = lambda k: sr.et_now(parse_utc(k)).date()                           # noqa: E731
        keep = set(sorted({day(k) for k in self.done})[-KEEP:])
        for k in [k for k in self.done if day(k) not in keep]:
            del self.done[k]
        for k in [k for k in self.hold if day(k) not in keep]:
            del self.hold[k]

    def has(self, T):
        with self.lock:
            return _iso(T) in self.done

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
                held = self.hold.get(key)
                if held and self.wall() < held[0]:  # ... or found it unsettled: its answer stands for now
                    return None, held[1]
                self.builds += 1
            pause = REBUILD_EVERY_S
            try:
                p = self.attempt(T)
            except NotPublished as exc:
                err, pause = exc.body(), exc.retry_s
            except Exception as exc:  # noqa: BLE001
                err = {"error": f"brain failed: {pc.one_line(repr(exc))}"}
            else:
                if (p.get("decision_bar") or {}).get("complete"):
                    with self.lock:
                        self.done[key], self.error = p, None
                        self.hold.pop(key, None)
                        self._evict()
                    return p, None
                err = {"error": (p.get("problems") or ["no decision at that instant"])[0]}
            with self.lock:
                self.error = err.get("detail") or err["error"]
                if pause:
                    self.hold[key] = (self.wall() + datetime.timedelta(seconds=pause), err)
                else:
                    self.hold.pop(key, None)
            return None, err

    def state(self):
        with self.lock:
            last = max(self.done) if self.done else None
            return {"instants": sorted(self.done), "built_utc": self.done[last].get("built_utc") if last else None,
                    "builds": self.builds, "last_error": self.error}


def pinned_attempt(history=None, attest=None, key=None, wall=None, fetch_minutes=None, settle_s=SETTLE_S,
                   wait_s=SETTLE_WAIT_S):
    """the attempt(T) of a Pinned. FMP's bars as of T are loaded (kept per T across attempts, so a retry
    asks only for what was missing). NotPublished while SPY's bar ending at T is not in, or, for settle_s
    past T by the wall clock, while the minute is still being published. NotSettled while FMP has not
    answered for a ticker a tree reads or can hold (no build is made on a partial answer), and after a
    build in which the decision bar is not complete or an engine is unavailable for a feed reason:
    until wait_s past T, whatever the reason; from then on only while a BOOK-level reason stands (SPY's
    bar, the book's breadth). Past wait_s with the book in order the build is settled as it is: the
    engines still down for a feed reason of their own are published unavailable, the others ok, and
    `problems` names what was given up on. Otherwise the payload: settled"""
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
                today = sr.et_now(wall()).date()
                for old in [x for x in feeds if sr.et_now(x).date() not in (today, sr.et_now(T).date())]:
                    del feeds[old]
        cfg_all = sr.load_manifest()
        bars.load(feed_tickers(cfg_all, bars.day), tick=tree_universe(cfg_all, bars.day))
        waited = (wall() - T).total_seconds()
        late = bars.unanswered(era_tickers(cfg_all) | {pc.GATE[0]})   # a pure sibling never holds the payload back
        if late and waited < wait_s:
            raise NotSettled(late)                 # no build on a partial answer while it may still come
        lag = bars.lagging()
        if lag and waited < settle_s:
            raise NotPublished(lag)
        diag = {}
        p = build(T, quotes=bars.quotes, fetch=history.fetch if history is not None else None, pinned=True,
                  attest=attest, wall=wall, diag=diag, quiet=bars.quiet)
        if not (p.get("decision_bar") or {}).get("complete"):
            raise NotSettled((p.get("problems") or ["no decision at that instant"])[0])
        feed = diag.get("feed") or {}
        if feed or late:
            why = sorted(set(feed.values()))
            down = (f"{', '.join(feed)} unavailable on the feed as it is: {why[0]}"
                    + (f" (and {len(why) - 1} more)" if len(why) > 1 else "")) if feed else None
            if waited < wait_s or diag.get("halt"):   # still inside the wait, or the feed as a whole is down
                raise NotSettled(down or late)
            p["problems"].append(f"settled {wait_s} s after the instant with the feed still incomplete; given up on: "
                                 + "; ".join(x for x in (late, down) if x))
        if lag:
            p["problems"].append(f"built {settle_s} s after the instant with the bar not fully published: {lag}")
        with lock:
            feeds.pop(T, None)                     # settled: the payload is the record now
        return p
    attempt.wall = wall
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
    Attestations POSTs are stored in (the answer says "pinned_already_built": true when today's pinned
    payload was cached before this attestation and so does not carry it); status: () -> extra fields
    for /health; wall: the wall clock (a test seam; default the system's UTC)"""
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
            now = wall()
            info = session_info(now)
            late = bool(pinned is not None and info.get("decide_utc") and pinned.has(parse_utc(info["decide_utc"])))
            return self._send(200, {"ok": True, "session": day, "stored": stored, "ignored": ignored,
                                    "sync": sync_block(cfg_all, day, attests, now), "pinned_already_built": late})

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
