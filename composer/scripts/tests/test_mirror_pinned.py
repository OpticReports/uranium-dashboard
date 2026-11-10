"""Gate tests for the mirror brain's schema-2 contract (mirror_brain.py, mirror_attest.py and the shared
pieces in preclose.py / shadow_runner.py), on REAL data: fixtures/mirror-brain-2026-11.json.gz holds
Yahoo's daily charts (wire format, 330 sessions to 2026-11-09, fetched 2026-11-10 05:13 UTC, when Yahoo
still lacked nine dividends that went ex on 2026-11-02), FMP's dividend and split rows, and FMP's traded
1-minute bars for 2026-08-28 and 2026-11-06 around 12:50-12:59 and 15:30-15:57. No network, no key.

Each behavioural test has a BROKEN twin that must land on the other side.

  T1  the pinned decision is AS OF the instant: only bars ending at or before it, never Yahoo's last
      sale; two builds for one instant agree whatever second they run and whatever Yahoo's last sale is
      (2026-11-06, the reviewer's case: ad hoc builds four seconds apart gave two HARV answers); SPY's
      price must be from the bar ending at the instant; the payload says which bar and when it was built
  T2  never a tradeable decision on dead data: a stalled feed, a shut market, a session-short history, a
      decision ticker priced by an estimate (no trade today, or rebuilt from a sibling though it traded
      earlier); a thin fund's old trade of its own is used and named
  T3  /mirror/intents?after=T: 503 until SPY's bar is published and while FMP is still publishing the
      minute, then ONE build shared by concurrent requests, cached and immutable for its ET day whatever
      other instants are asked; a build that could not price SPY is a 503 and is never cached; no key
      -> 503
  T4  the tree-version gate: one hash function for the approved and the live tree; ok / drift / none /
      paused; an ok older than MIRROR_ATTEST_MAX_AGE_S before the instant counts as none;
      MIRROR_REQUIRE_ATTESTATION; POST /mirror/attest (and whether it came too late for today's pinned
      payload); mirror_attest.py end to end against a local brain with a stubbed Composer read
  T5  dividends Yahoo has not booked are applied from FMP's list (CR(SHY,1) on 2026-11-02: -0.29% ->
      +0.02%), never twice, only when recent, and named; one cached call per ticker per day; no key =
      Yahoo's alone, as before; a burst of FMP failures is retried within the warm window; the shadow
      runner's recorded targets since the ex-date are unchanged
  T6  dividends and splits in the payload: Yahoo's events union FMP's list, ten days, cash as paid;
      actions_complete says whether FMP's lists were read for every ticker
  T7  a replay of a past session scales the minute price onto the adjusted series: 2026-08-28 at 15:54
      reproduces Composer's holdings on all four engines (the ledger); without the scaling three differ
  T8  load: the session's Yahoo history is fetched once; a retry asks FMP only for what was missing; the
      mirror's FMP budget is its own; built_utc is stamped when the build ends
  T9  only a SETTLED decision is cached: while FMP has not answered for a ticker, or an engine is
      unavailable for a feed reason, the answer is 503 and a later request rebuilds, at most every
      REBUILD_EVERY_S (a 50-second run of 429s no longer freezes an all-unavailable session); an engine
      unavailable for a reason the feed cannot change is a settled answer

Run: python3 -m unittest composer.scripts.tests.test_mirror_pinned -v
"""
import contextlib
import copy
import datetime
import gzip
import io
import json
import os
import sys
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.pop("FMP_API_KEY", None)
import mirror_attest as ma  # noqa: E402
import mirror_brain as mb  # noqa: E402
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

UTC = datetime.timezone.utc
FIXTURE = os.path.join(HERE, "fixtures", "mirror-brain-2026-11.json.gz")
LEDGER = os.path.join(HERE, "..", "..", "results", "monitor", "shadow-ledger.jsonl")
D = "2026-11-06"
T = datetime.datetime(2026, 11, 6, 20, 54, tzinfo=UTC)          # 15:54:00 ET: the decision instant that day
SEC = datetime.timedelta(seconds=1)
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
ATT = "att-T0KEN-for-the-test"                                   # the brain's MIRROR_ATTEST_TOKEN in these tests


def targets(p):
    return {e: r.get("target") for e, r in p["engines"].items()}


def statuses(p):
    return {e: r["status"] for e, r in p["engines"].items()}


class Real(unittest.TestCase):
    """the fixture's data behind the brain's two seams; no tests of its own"""
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE) as f:
            cls.fx = json.load(f)
        cls._parsed = {}
        cls.man = sr.load_manifest()

    @classmethod
    def actions(cls, t):
        return sr.parse_actions(cls.fx["dividends"][t], cls.fx["splits"][t])

    @classmethod
    def yahoo(cls, t, fmp=True):
        """(adj, raw, meta) as preclose.fetch_live returns it; fmp=False: without FMP's lists (no key)"""
        k = (t, fmp)
        if k not in cls._parsed:
            res = cls.fx["yahoo"].get(t)
            if res is None:
                raise RuntimeError(f"Yahoo {t}: not in the fixture")
            acts = cls.actions(t) if fmp else None
            applied = []
            adj, raw = sr.parse_daily(res, acts, applied)
            ca = dict(sr.corporate_actions(res.get("events") or {}, acts, max(raw)), applied=applied)
            cls._parsed[k] = (adj, raw, dict(res["meta"], corporateActions=ca))
        a, r, m = cls._parsed[k]
        return dict(a), dict(r), dict(m)

    @classmethod
    def bars(cls, t, d, key=None):
        b = cls.fx["bars"].get(d, {}).get(t)
        if b is None:
            raise RuntimeError(f"FMP {t} {d}: not in the fixture")
        return dict(b)

    @classmethod
    def quotes(cls, cut=None, drop=(), only_until=None):
        """the preview's `quotes` seam on the fixture's bars: bars starting after `cut` are not published;
        `drop`: tickers FMP has no bar for; only_until {ticker: last bar start}: a ticker stopped trading"""
        def fetch(t, d, k):
            if t in drop:
                return {}
            last = min(x for x in (cut, (only_until or {}).get(t)) if x) if (cut or t in (only_until or {})) else None
            return {hm: c for hm, c in cls.bars(t, d).items() if last is None or hm <= last}
        return lambda tickers, now: pc.minute_quotes(tickers, now, "k", fetch=fetch)

    def yahoo_with_sale(self, hms, bar):
        """Yahoo's daily chart as on D during the session, its bar for D = the last sale at hh:mm:ss ET
        (priced off FMP's bar starting `bar`): what a live fetch at that second returns"""
        h, mi, s = map(int, hms.split(":"))
        stamp = int((datetime.datetime(2026, 11, 6, h + 5, mi, s, tzinfo=UTC)).timestamp())

        def fetch(t):
            adj, raw, meta = self.yahoo(t)
            adj = {d: v for d, v in adj.items() if d < D}
            raw = {d: v for d, v in raw.items() if d < D}
            b = self.bars(t, D)
            ks = [k for k in b if k <= bar]
            if ks:
                adj[D] = raw[D] = b[max(ks)]
                meta = dict(meta, regularMarketTime=stamp)
            return adj, raw, meta
        return fetch

    def pinned(self, at=T, wall=25, **kw):
        kw.setdefault("quotes", self.quotes())
        kw.setdefault("fetch", self.yahoo)
        return mb.build(at, pinned=True, wall=lambda: at + wall * SEC, **kw)


def ledger(day):
    out = {}
    with open(LEDGER) as f:
        for line in f:
            r = json.loads(line)
            if r.get("date") == day:
                out[r["engine"]] = r
    return out


# ------------------------------------------------------------------ T1 the pinned decision
class T1Pinned(Real):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.p = mb.build(T, quotes=cls.quotes(), fetch=cls.yahoo, pinned=True, wall=lambda: T + 25 * SEC)

    def test_the_payload_names_its_instant_and_its_bar(self):
        p = self.p
        self.assertEqual((p["schema"], p["kind"], p["session"], p["pinned"], p["replay"]), (2, mb.KIND, D, True, False))
        self.assertEqual((p["asof_utc"], p["asof_et"], p["close_et"]), ("2026-11-06T20:54:00Z", "15:54:00", "16:00"))
        self.assertEqual(p["decision_bar"], {"end_utc": "2026-11-06T20:54:00Z", "spy_utc": "2026-11-06T20:54:00Z", "complete": True})
        self.assertEqual(p["built_utc"], "2026-11-06T20:54:25Z")
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        self.assertEqual(p["asof_utc"], mb.session_info(T)["decide_utc"])       # the executor's check: asof == decide
        self.assertEqual(p["quotes"]["breadth"]["of"], 48)
        self.assertGreaterEqual(p["quotes"]["breadth"]["share"], 0.9)

    def test_only_bars_ending_at_or_before_the_instant_are_read(self):
        """the fixture's feed already holds the bars that start 15:54 .. 15:57: none of them is used"""
        p = self.p
        spy = self.bars("SPY", D)
        self.assertEqual(p["prices"]["SPY"], spy["15:53"])                      # the bar that ENDS 15:54:00
        self.assertNotEqual(spy["15:53"], spy["15:54"])
        for t, px in p["prices"].items():
            b = self.bars(t, D)
            last = max(k for k in b if k <= "15:53")
            self.assertEqual(px, round(b[last], 6), t)
            self.assertEqual(p["price_times"][t], mb._iso(pc.bar_end(D, last, sr.et_now(T).tzinfo)), t)
            self.assertLessEqual(p["price_times"][t], p["asof_utc"], t)
        self.assertEqual(set(p["price_times"]), set(p["prices"]))
        early = self.pinned(quotes=self.quotes(cut="15:53"))                    # FMP has published nothing later yet
        self.assertEqual((early["engines"], early["prices"], early["price_times"]), (p["engines"], p["prices"], p["price_times"]))
        late = self.pinned(T + 60 * SEC)                                        # broken: the next bar's end is another decision
        self.assertNotEqual(late["prices"]["SPY"], p["prices"]["SPY"])

    def test_two_builds_for_one_instant_agree_whatever_second_they_run(self):
        """the reviewer's B1b on 2026-11-06: FMP has published through the bar ending 15:54:00; Yahoo's last
        sale is 15:55:00 for one build and 15:55:04 for the other"""
        a = self.pinned(wall=61, quotes=self.quotes(cut="15:53"), fetch=self.yahoo_with_sale("15:55:00", "15:54"))
        b = self.pinned(wall=65, quotes=self.quotes(cut="15:53"), fetch=self.yahoo_with_sale("15:55:04", "15:54"))
        c = self.pinned(wall=3600, quotes=self.quotes(), fetch=self.yahoo)      # an hour later, Yahoo's bar now the close
        for other in (b, c):
            self.assertEqual((other["engines"], other["prices"], other["price_times"], other["decision_bar"]),
                             (a["engines"], a["prices"], a["price_times"], a["decision_bar"]))
        self.assertEqual((a["built_utc"], b["built_utc"]), ("2026-11-06T20:55:01Z", "2026-11-06T20:55:05Z"))
        self.assertEqual(targets(a)["HARV"], {"PULS": 1.0})
        self.assertFalse(c["replay"])                                           # same day: not a replay
        # BROKEN twin: the ad hoc path at those two seconds. SAME_MOMENT (60 s) sits on the boundary: the
        # first reads FMP's bar, the second Yahoo's sale, and HARV and KMLM come out differently
        x = mb.build(T + 61 * SEC, quotes=self.quotes(cut="15:53"), fetch=self.yahoo_with_sale("15:55:00", "15:54"))
        y = mb.build(T + 65 * SEC, quotes=self.quotes(cut="15:53"), fetch=self.yahoo_with_sale("15:55:04", "15:54"))
        self.assertEqual((x["pinned"], x["decision_bar"]), (False, None))
        self.assertEqual(targets(x)["HARV"], {"PULS": 1.0})
        self.assertEqual(targets(y)["HARV"], {"PULS": 0.64, "ZVOL": 0.36})
        self.assertNotEqual(targets(x)["KMLM"], targets(y)["KMLM"])

    def test_yahoos_last_sale_is_never_read_even_when_it_is_before_the_instant(self):
        """VXZ's last traded FMP bar ends 15:52:00. Yahoo shows a sale at 15:53:30, 90 s newer and BEFORE the
        instant: the ad hoc path takes it (more than SAME_MOMENT newer), and which sale Yahoo shows depends on
        the second it is asked. The pinned decision reads bars only"""
        b = self.bars("VXZ", D)
        last = max(k for k in b if k <= "15:53")
        self.assertEqual(last, "15:51")                                         # the bar that ends 15:52:00
        stamp = int(datetime.datetime(2026, 11, 6, 20, 53, 30, tzinfo=UTC).timestamp())

        def fetch(t):
            adj, raw, meta = self.yahoo(t)
            adj = {d: v for d, v in adj.items() if d < D}
            raw = {d: v for d, v in raw.items() if d < D}
            if t == "VXZ":
                adj[D] = raw[D] = b[last] * 1.01
                meta = dict(meta, regularMarketTime=stamp)
            return adj, raw, meta
        p = self.pinned(fetch=fetch)
        self.assertEqual((p["prices"]["VXZ"], p["price_times"]["VXZ"]), (round(b[last], 6), "2026-11-06T20:52:00Z"))
        self.assertEqual(p["prices"], self.p["prices"])
        x = mb.build(T, quotes=self.quotes(), fetch=fetch)                      # BROKEN twin: the ad hoc path reads Yahoo's
        self.assertEqual((x["prices"]["VXZ"], x["price_times"]["VXZ"]), (round(b[last] * 1.01, 6), "2026-11-06T20:53:30Z"))

    def test_a_live_run_cuts_at_the_instant_too(self):
        """seconds after the instant the run is no 'replay' by the five-minute rule, and a feed may already hold
        a later stamp: nothing after the instant is read, and no price_time is ever later than asof_utc"""
        real = self.quotes()

        def ahead(tickers, now):
            q, probs = real(tickers, now)
            if "BIL" in q:
                q["BIL"] = (q["BIL"][0] * 1.5, T + 30 * SEC)                    # a trade stamped after the instant
            return q, probs
        with unittest.mock.patch.object(pc, "is_replay", lambda now, wall=None: False):
            p = self.pinned(quotes=ahead)
            base = self.pinned()
        self.assertEqual((base["engines"], base["prices"]), (self.p["engines"], self.p["prices"]))   # live == replay
        self.assertTrue(all(t <= p["asof_utc"] for t in p["price_times"].values()))
        self.assertNotEqual(p["prices"]["BIL"], round(self.bars("BIL", D)["15:53"] * 1.5, 6))
        self.assertEqual(p["price_times"]["BIL"], "2026-11-05T21:00:00Z")       # the previous close, carried and named
        self.assertIn("BIL", p["price_notes"])

    def test_spy_must_be_priced_from_the_decision_bar(self):
        p = self.pinned(quotes=self.quotes(cut="15:52"))                        # FMP has not published the bar yet
        self.assertEqual(p["decision_bar"], {"end_utc": "2026-11-06T20:54:00Z", "spy_utc": "2026-11-06T20:53:00Z", "complete": False})
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertTrue(all("target" not in r for r in p["engines"].values()))
        self.assertIn("SPY's price is not from the bar ending 15:54:00 ET", p["engines"]["HG"]["note"])
        self.assertIn("15:53:00", p["problems"][0])
        off = self.pinned(T + 30 * SEC)                                         # no bar ends at 15:54:30
        self.assertFalse(off["decision_bar"]["complete"])
        self.assertEqual(statuses(off), dict.fromkeys(ENGINES, "unavailable"))
        self.assertTrue(self.p["decision_bar"]["complete"])                     # the twin

    def test_a_pinned_build_needs_minute_bars(self):
        p = mb.build(T, fetch=self.yahoo, pinned=True, wall=lambda: T + 25 * SEC)   # no key in the suite, no quotes seam
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertIn("FMP_API_KEY not set", p["problems"][0])
        self.assertEqual((p["pinned"], p["decision_bar"]["complete"], p["prices"]), (True, False, {}))

    def test_the_cli_at_is_the_pinned_decision(self):
        seen = []
        with unittest.mock.patch.object(mb, "build", lambda *a, **k: seen.append((a, k)) or {"ok": True}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mb.main(["--at", "2026-11-06 15:54"]), 0)
            mb.main([])                                                         # the twin: no --at is an ad hoc read
        self.assertEqual(seen, [((T,), {"pinned": True}), ((), {})])
        self.assertEqual(json.loads(out.getvalue().split("}")[0] + "}"), {"ok": True})

    def test_a_past_day_is_a_replay(self):
        p = mb.build(T, quotes=self.quotes(), fetch=self.yahoo, pinned=True)     # the wall clock is the real one
        self.assertTrue(p["replay"])
        self.assertEqual((p["engines"], p["prices"]), (self.p["engines"], self.p["prices"]))   # and the same decision


# ------------------------------------------------------------------ T2 dead data
class T2DeadData(Real):
    def test_a_stalled_feed_is_refused(self):
        """FMP stuck at the bar starting 15:38 (the reviewer's B5): every price is 15 minutes old"""
        p = self.pinned(quotes=self.quotes(cut="15:38"))
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertEqual((p["decision_bar"]["complete"], p["decision_bar"]["spy_utc"]), (False, "2026-11-06T20:39:00Z"))
        self.assertEqual(p["quotes"]["breadth"]["recent"], 0)
        self.assertTrue(any("the feed looks dead: 0 of 48" in x for x in p["problems"]), p["problems"])
        self.assertEqual(max(p["price_times"].values()), "2026-11-06T20:39:00Z")   # and the payload shows how old
        # the ad hoc path at 15:55:05, Yahoo no newer (the reviewer's exact case): breadth alone refuses it
        asof = mb.build(T + 65 * SEC, quotes=self.quotes(cut="15:38"), fetch=self.yahoo_with_sale("15:38:59", "15:38"))
        self.assertEqual(statuses(asof), dict.fromkeys(ENGINES, "unavailable"))
        self.assertIn("the feed looks dead", asof["engines"]["KMLM"]["note"])
        self.assertEqual(statuses(self.pinned()), dict.fromkeys(ENGINES, "ok"))    # the twin: the feed is alive

    def test_a_market_that_shut_at_one_is_refused(self):
        """an early close the calendar table does not know (the reviewer's B5b): the last trades are from 12:59"""
        p = self.pinned(quotes=self.quotes(cut="12:59"))
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertEqual((p["decision_bar"]["complete"], p["quotes"]["breadth"]["recent"]), (False, 0))
        self.assertLessEqual(max(p["price_times"].values()), "2026-11-06T18:00:00Z")

    def test_breadth_alone_refuses_when_spy_trades_and_the_rest_do_not(self):
        liquid = [t for t in self.fx["bars"][D] if t != "SPY"]
        p = self.pinned(quotes=self.quotes(only_until=dict.fromkeys(liquid, "15:38")))
        self.assertTrue(p["decision_bar"]["complete"])                          # SPY's bar is there
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertIn("the feed looks dead: 1 of 48", p["engines"]["HG"]["note"])
        few = self.pinned(quotes=self.quotes(only_until=dict.fromkeys(liquid[:5], "15:38")))   # the twin: 5 of 48 lag
        self.assertGreaterEqual(few["quotes"]["breadth"]["share"], mb.BREADTH_MIN)
        self.assertNotIn("the feed looks dead", json.dumps(few["problems"]))

    def test_a_history_a_session_short_is_not_tradeable(self):
        """Yahoo's history lacks the previous session for two decision tickers (the reviewer's B5c)"""
        def fetch(t):
            adj, raw, meta = self.yahoo(t)
            if t in ("UVXY", "TQQQ"):
                adj.pop("2026-11-05")
                raw.pop("2026-11-05")
            return adj, raw, meta
        p = self.pinned(fetch=fetch)
        reads = {e: sr.decision_tickers(sr.load_tree(self.man[e]["eras"][-1])) & {"UVXY", "TQQQ"} for e in ENGINES}
        self.assertTrue(any(reads.values()))
        for e in ENGINES:
            self.assertEqual(p["engines"][e]["status"], "unavailable" if reads[e] else "ok", e)
            if reads[e]:
                self.assertIn("lacks the previous session", p["engines"][e]["note"])
                self.assertNotIn("target", p["engines"][e])
        self.assertEqual(sorted(p["quotes"]["short"]), ["TQQQ", "UVXY"])

    def test_a_decision_ticker_priced_by_an_estimate(self):
        """FMP gives no bar for TQQQ (halted since the open, say): the preview rebuilds its price from a
        same-index fund, which is an estimate: the engines that READ TQQQ do not trade on it"""
        diag = {}
        p = self.pinned(quotes=self.quotes(drop={"TQQQ"}), diag=diag)
        reads = {e: "TQQQ" in sr.decision_tickers(sr.load_tree(self.man[e]["eras"][-1])) for e in ENGINES}
        self.assertTrue(any(reads.values()) and not all(reads.values()))
        for e in ENGINES:
            self.assertEqual(p["engines"][e]["status"], "unavailable" if reads[e] else "ok", e)
            if reads[e]:
                self.assertIn("TQQQ priced by an estimate, not a trade of its own today (TQQQ: no trade today)", p["engines"][e]["note"])
        self.assertEqual(sorted(diag["feed"]), sorted(e for e in ENGINES if reads[e]))   # a reason the feed could change
        self.assertIn("via", p["price_notes"]["TQQQ"])                          # still priced, as an estimate, and named
        self.assertGreater(p["prices"]["TQQQ"], 0)
        self.assertTrue(p["decision_bar"]["complete"])
        # the same when TQQQ DID trade today, last at 15:31: the preview rebuilds a price that old from QQQ, the
        # payload shows the SIBLING's time for it, and a decision must not rest on that either (round 2, R5)
        q = self.pinned(quotes=self.quotes(only_until={"TQQQ": "15:30"}))
        self.assertIn("via", q["price_notes"]["TQQQ"])
        self.assertEqual(q["price_times"]["TQQQ"], "2026-11-06T20:54:00Z")       # not TQQQ's own 15:31
        for e in ENGINES:
            self.assertEqual(q["engines"][e]["status"], "unavailable" if reads[e] else "ok", e)
            if reads[e]:
                self.assertIn("TQQQ priced by an estimate, not a trade of its own today", q["engines"][e]["note"])
                self.assertNotIn("no trade today", q["engines"][e]["note"])
                self.assertNotIn("target", q["engines"][e])
        self.assertEqual(statuses(self.pinned()), dict.fromkeys(ENGINES, "ok"))    # the twin: TQQQ's own trade at the bar

    def test_a_thin_funds_old_trade_is_used_and_named(self):
        """PEJ last traded at 15:20 (measured: its last trade was over 15 minutes old on 5 of 83 sessions, and
        Composer trades those days). The engine that reads it still decides; the payload says how old it is"""
        p = self.pinned(quotes=self.quotes(only_until={"PEJ": "15:20"}))
        reads = [e for e in ENGINES if "PEJ" in sr.decision_tickers(sr.load_tree(self.man[e]["eras"][-1]))]
        self.assertTrue(reads)
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        b = self.bars("PEJ", D)
        last = max(k for k in b if k <= "15:20")
        self.assertEqual(p["prices"]["PEJ"], round(b[last], 6))
        self.assertEqual(p["price_times"]["PEJ"], mb._iso(pc.bar_end(D, last, sr.et_now(T).tzinfo)))
        self.assertIn("last price used", p["price_notes"]["PEJ"])
        for e in reads:
            self.assertTrue(any(x.startswith("PEJ ") for x in p["engines"][e]["stale"]), p["engines"][e])
        # BROKEN twin: most of that engine's decision tickers stopped with it -> its own breadth refuses it
        dec = sorted(sr.decision_tickers(sr.load_tree(self.man[reads[0]]["eras"][-1])) - {"SPY"})
        cut = dec[:len(dec) // 3 + 1]
        q = self.pinned(quotes=self.quotes(only_until=dict.fromkeys(cut, "15:45")))
        self.assertEqual(q["engines"][reads[0]]["status"], "unavailable")
        self.assertIn("decision tickers traded in the last 2 minutes", q["engines"][reads[0]]["note"])

    def test_a_year_past_the_calendar_is_refused(self):
        late = datetime.datetime(2028, 11, 24, 20, 54, tzinfo=UTC)               # a 13:00 close the tables do not hold
        p = mb.build(late, quotes=self.quotes(), fetch=self.yahoo, pinned=True, wall=lambda: late + 25 * SEC)
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))
        self.assertIn("ends in 2027", p["problems"][0])
        self.assertIsNone(p["session"])


# ------------------------------------------------------------------ T3 the HTTP path for ?after=T
class Fmp:
    """FMP as it publishes a minute: `cut` is the last bar start it serves, `lag` {ticker: an earlier one}"""
    def __init__(self, bars):
        self.bars, self.cut, self.lag, self.calls, self.delay = bars, "15:53", {}, [], 0.0

    def __call__(self, t, d, key):
        self.calls.append(t)
        if self.delay:
            time.sleep(self.delay)
        last = self.lag.get(t, self.cut)
        return {hm: c for hm, c in self.bars(t, d).items() if hm <= last}


class Http(Real):
    def setUp(self):
        self.now = [T + 20 * SEC]
        self.fmp = Fmp(self.bars)
        self.hist = mb.History(fetch=self.count_yahoo, wall=lambda: self.now[0])
        self.yahoo_calls = []
        self.attests = mb.Attestations()
        self.builds = []
        self.pinned_cache = mb.Pinned(mb.pinned_attempt(self.hist, self.attests, key="k", wall=lambda: self.now[0],
                                                        fetch_minutes=self.fmp))
        self.adhoc = mb.Cache(lambda: {"schema": 2, "pinned": False})
        srv = mb.make_server(0, "tok", self.adhoc, window=lambda: True, wall=lambda: self.now[0], pinned=self.pinned_cache,
                             attest_token=ATT, attests=self.attests)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.url = self.base + "/mirror/intents?after=2026-11-06T20:54:00Z"

    def count_yahoo(self, t):
        self.yahoo_calls.append(t)
        return self.yahoo(t)

    def get(self, url, token="tok"):
        req = urllib.request.Request(url, headers={"X-API-Token": token} if token is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def post(self, body, token=ATT, raw=None):
        req = urllib.request.Request(self.base + "/mirror/attest", data=raw if raw is not None else json.dumps(body).encode(),
                                     method="POST", headers={"X-Attest-Token": token} if token is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class T3After(Http):
    def test_503_until_published_then_one_immutable_payload(self):
        self.fmp.cut = "15:52"                                                  # the bar ending 15:54:00 is not out yet
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "decision bar not published yet"))
        self.assertIn("15:53:00", body["detail"])
        self.assertEqual((self.fmp.calls, self.yahoo_calls), (["SPY"], []))     # one call, nothing else asked
        self.fmp.cut = "15:53"
        self.fmp.lag = dict.fromkeys(("QLD", "SOXL", "SQQQ", "TECL", "TLT", "TNA", "UPRO", "XLK", "XLP", "XLY"), "15:52")
        code, body = self.get(self.url)                                         # SPY is out; ten liquid funds are not
        self.assertEqual((code, body["error"]), (503, "decision bar not published yet"))
        self.assertIn("still publishing", body["detail"])
        self.assertEqual(self.yahoo_calls, [])                                  # no build yet
        asked = len(self.fmp.calls)
        self.fmp.lag = {}
        self.now[0] = T + 26 * SEC
        code, p = self.get(self.url)
        self.assertEqual(code, 200)
        self.assertEqual((p["pinned"], p["asof_utc"], p["built_utc"], p["replay"]), (True, "2026-11-06T20:54:00Z", "2026-11-06T20:54:26Z", False))
        self.assertTrue(p["decision_bar"]["complete"])
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        self.assertNotIn("served_age_s", p)
        again = self.fmp.calls[asked:]
        self.assertLessEqual(len(again), 20)                                    # only the ten that lagged and the thin ones
        self.assertNotIn("SPY", again)
        self.assertTrue(set(self.fmp.lag) <= set(again) or {"QLD", "SOXL"} <= set(again))
        # immutable: FMP now serves later bars, the clock has moved, an attestation arrives: the same payload, no calls
        self.fmp.cut = "15:57"
        self.now[0] = T + 200 * SEC
        fmp_n, yahoo_n = len(self.fmp.calls), len(self.yahoo_calls)
        code, q = self.get(self.url)
        self.assertEqual((code, q), (200, p))
        self.assertEqual((len(self.fmp.calls), len(self.yahoo_calls)), (fmp_n, yahoo_n))
        self.assertEqual(self.pinned_cache.state()["instants"], ["2026-11-06T20:54:00Z"])
        health = self.get(self.base + "/health", None)[1]
        self.assertEqual((health["schema"], health["pinned"]["built_utc"], health["attest_token_set"]), (2, "2026-11-06T20:54:26Z", True))
        self.assertEqual(self.get(self.url, "wrong")[0], 401)

    def test_an_unsettled_bar_is_published_after_the_settle_window(self):
        self.fmp.lag = dict.fromkeys(("QLD", "SOXL", "SQQQ", "TECL", "TLT", "TNA", "UPRO", "XLK", "XLP", "XLY"), "15:52")
        self.now[0] = T + (mb.SETTLE_S - 1) * SEC
        self.assertEqual(self.get(self.url)[0], 503)
        self.now[0] = T + mb.SETTLE_S * SEC                                      # FMP never published them: go with what there is
        code, p = self.get(self.url)
        self.assertEqual(code, 200)
        self.assertTrue(any("not fully published" in x and "QLD" in x for x in p["problems"]), p["problems"])
        self.assertEqual(p["price_times"]["QLD"], "2026-11-06T20:53:00Z")        # and the payload shows the older bar
        self.assertEqual(p["price_times"]["SPY"], "2026-11-06T20:54:00Z")

    def test_a_ticker_fmp_does_not_answer_for_is_waited_for(self):
        real = self.fmp.__call__

        def flaky(t, d, key):
            if t == "TQQQ" and flaky.down:
                self.fmp.calls.append(t)
                raise RuntimeError("FMP TQQQ: timed out")
            return real(t, d, key)
        flaky.down = True
        self.pinned_cache.attempt = mb.pinned_attempt(self.hist, self.attests, key="k", wall=lambda: self.now[0], fetch_minutes=flaky)
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "decision not settled yet"))
        self.assertIn("FMP has not answered for TQQQ", body["detail"])
        flaky.down = False
        self.assertEqual(self.get(self.url)[0], 503)                            # not asked again within REBUILD_EVERY_S
        self.assertEqual(self.fmp.calls.count("TQQQ"), 1)
        self.now[0] += mb.REBUILD_EVERY_S * SEC                                 # the retry gets it: nothing is lost
        code, p = self.get(self.url)
        self.assertEqual((code, statuses(p)), (200, dict.fromkeys(ENGINES, "ok")))
        self.assertEqual(self.fmp.calls.count("TQQQ"), 2)
        self.assertEqual(self.fmp.calls.count("SPY"), 1)                         # what was in is never asked again

    def test_concurrent_requests_share_one_build(self):
        self.fmp.delay = 0.01
        real, n = mb.build, []

        def counted(*a, **k):
            n.append(1)
            return real(*a, **k)
        got = []
        with unittest.mock.patch.object(mb, "build", counted):
            ts = [threading.Thread(target=lambda: got.append(self.get(self.url))) for _ in range(5)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(60)
        self.assertEqual(len(got), 5)
        self.assertEqual({code for code, _ in got}, {200})
        self.assertEqual(len(n), 1)                                             # ONE build for five requests
        self.assertTrue(all(body == got[0][1] for _, body in got))
        self.assertEqual(len(self.yahoo_calls), len(set(self.yahoo_calls)))

    def test_an_incomplete_decision_is_a_503_and_is_never_cached(self):
        """SPY's bar is published, but the build cannot price SPY (Yahoo's history for it fails): that is not a
        decision. The executor's retry gets the real one once Yahoo answers"""
        down = [True]

        def yahoo(t):
            if t == "SPY" and down[0]:
                raise RuntimeError("Yahoo SPY: timed out")
            return self.yahoo(t)
        self.hist._fetch = yahoo
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "decision not settled yet"))
        self.assertIn("SPY", body["detail"])
        self.assertEqual(self.pinned_cache.state()["instants"], [])
        down[0] = False
        self.now[0] += mb.REBUILD_EVERY_S * SEC
        short = [True]                                                          # ... and now Yahoo's SPY history stops a session

        def yahoo2(t):                                                          # early: the preview gives no decision at all
            adj, raw, meta = self.yahoo(t)
            if t == "SPY" and short[0]:
                adj.pop("2026-11-05")
                raw.pop("2026-11-05")
            return adj, raw, meta
        self.hist._fetch = yahoo2
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "decision not settled yet"))
        self.assertIn("Yahoo's SPY history ends 2026-11-04", body["detail"])
        self.assertEqual(self.pinned_cache.state()["instants"], [])
        short[0] = False
        self.hist.data.clear()                                                  # (the warm loop would refetch it)
        self.now[0] += mb.REBUILD_EVERY_S * SEC
        code, p = self.get(self.url)
        self.assertEqual((code, p["decision_bar"]["complete"], statuses(p)), (200, True, dict.fromkeys(ENGINES, "ok")))
        self.assertEqual(self.pinned_cache.state()["instants"], ["2026-11-06T20:54:00Z"])

    def test_the_decision_instants_payload_survives_other_instants(self):
        """the second verifier's case: two bars FMP had not published at T+25 s; later a monitor reads four
        later minutes; then the executor (restarted, say) asks for the decision instant again. It must get
        the payload it was given, not a rebuild on the bars as they are by then"""
        self.fmp.lag = {"PEJ": "15:40", "KIE": "15:52"}
        self.now[0] = T + 25 * SEC
        code, first = self.get(self.url)
        self.assertEqual(code, 200)
        self.fmp.cut, self.fmp.lag = "15:57", {}
        builds = self.pinned_cache.builds
        for k in range(1, 5):
            self.now[0] = T + (60 * k + 30) * SEC
            self.get(self.base + "/mirror/intents?after=" + mb._iso(T + 60 * k * SEC))
        code, again = self.get(self.url)
        self.assertEqual((code, again), (200, first))                           # prices and built_utc included
        self.assertEqual(again["price_times"]["KIE"], "2026-11-06T20:53:00Z")    # the bar it was decided on
        self.assertEqual(self.pinned_cache.builds, builds + 4)                  # the four others; T was not rebuilt
        self.assertEqual(len(self.pinned_cache.state()["instants"]), 5)
        # the twin: another ET DAY's instants do go, the oldest day first, once more than KEEP days are held
        with self.pinned_cache.lock:
            for d in range(1, mb.KEEP + 3):
                self.pinned_cache.done[mb._iso(T - d * 86400 * SEC)] = {"session": "old"}
            self.pinned_cache._evict()
            days = sorted({k[:10] for k in self.pinned_cache.done})
        self.assertEqual(len(days), mb.KEEP)
        self.assertEqual(days[-1], D)
        self.assertEqual(len([k for k in self.pinned_cache.done if k.startswith(D)]), 5)

    def test_without_a_key_the_answer_is_a_503_with_the_reason(self):
        self.pinned_cache.attempt = mb.pinned_attempt(self.hist, self.attests, wall=lambda: self.now[0])   # no key anywhere
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "FMP_API_KEY not set"))
        self.assertEqual(self.get(self.base + "/mirror/intents")[1], {"schema": 2, "pinned": False, "served_age_s": 0.0})

    def test_no_session_at_the_instant_is_never_a_payload(self):
        self.now[0] = datetime.datetime(2026, 11, 7, 20, 54, 20, tzinfo=UTC)    # a Saturday
        code, body = self.get(self.base + "/mirror/intents?after=2026-11-07T20:54:00Z")
        self.assertEqual(code, 503)
        self.assertEqual(self.pinned_cache.state()["instants"], [])


# ------------------------------------------------------------------ T4 the tree-version gate
def attestation(man, day, **override):
    out = {}
    for eng, cfg in man.items():
        era = mb.era_of(cfg, day)
        out[eng] = dict({"version": era["version"], "tree_sha1": mb.approved_sha1(era)}, **override.get(eng, {}))
    return {"session": day, "engines": out}


class Store(dict):
    """a stand-in for mb.Attestations in build(): {day: {'engines': {...}}}"""


class T4Gate(Real):
    def test_one_hash_for_the_approved_and_the_live_tree(self):
        for eng, cfg in self.man.items():
            era = cfg["eras"][-1]
            tree = sr.load_tree(era)
            self.assertEqual(mb.approved_sha1(era), sr.tree_sha1(tree))
            self.assertEqual(sr.tree_sha1(tree), sr.sha1_of(sr.canonical(tree)))    # what check_drift hashes
            self.assertRegex(sr.tree_sha1(tree), r"^[0-9a-f]{40}$")
            shown = copy.deepcopy(tree)                                          # display-only edits do not move it
            shown["name"], shown["description"] = "renamed", "x"
            self.assertEqual(sr.tree_sha1(shown), sr.tree_sha1(tree))
            self.assertNotEqual(sr.tree_sha1(edited(tree)), sr.tree_sha1(tree))  # broken: a logic edit does
        self.assertEqual(len({mb.approved_sha1(c["eras"][-1]) for c in self.man.values()}), 4)

    def gated(self, body=None, at="2026-11-06T20:50:10Z", **kw):
        store = Store()
        if body:
            store[body["session"]] = {"engines": {e: dict(r, paused=r.get("paused", False), attested_utc=at)
                                                  for e, r in body["engines"].items()}}
        return self.pinned(attest=store, **kw)

    def test_an_ok_attested_too_long_before_the_instant_counts_as_none(self):
        """round 2, R3: the tree could have been edited since. Default limit one hour before the instant"""
        ok = attestation(self.man, D)
        p = self.gated(ok, at=mb._iso(T - 3601 * SEC))
        self.assertEqual({e: s["state"] for e, s in p["sync"].items()}, dict.fromkeys(ENGINES, "none"))
        self.assertEqual(p["sync"]["HG"]["attested_utc"], "2026-11-06T19:53:59Z")        # still shown
        self.assertEqual(p["sync"]["HG"]["live_version"], self.man["HG"]["eras"][-1]["version"])
        line = next(x for x in p["problems"] if "older than 3600 s" in x)
        self.assertIn("HG 3601 s", line)
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))             # as any 'none': trades, loudly ...
        self.assertTrue(any("no attestation of the live logic" in x for x in p["problems"]))
        with unittest.mock.patch.dict(os.environ, {"MIRROR_REQUIRE_ATTESTATION": "1"}):
            self.assertEqual(statuses(self.gated(ok, at=mb._iso(T - 3601 * SEC))), dict.fromkeys(ENGINES, "unavailable"))   # ... or not at all
        edge = self.gated(ok, at=mb._iso(T - 3600 * SEC))                        # the twin: exactly the limit is fresh
        self.assertEqual({e: s["state"] for e, s in edge["sync"].items()}, dict.fromkeys(ENGINES, "ok"))
        self.assertFalse(any("older than" in x for x in edge["problems"]))
        after = self.gated(ok, at=mb._iso(T + 10 * SEC))                         # attested between the instant and the build
        self.assertEqual({e: s["state"] for e, s in after["sync"].items()}, dict.fromkeys(ENGINES, "ok"))
        with unittest.mock.patch.dict(os.environ, {"MIRROR_ATTEST_MAX_AGE_S": "7200"}):
            wide = self.gated(ok, at=mb._iso(T - 3601 * SEC))
            self.assertEqual({e: s["state"] for e, s in wide["sync"].items()}, dict.fromkeys(ENGINES, "ok"))
        with unittest.mock.patch.dict(os.environ, {"MIRROR_ATTEST_MAX_AGE_S": "soon"}):   # unreadable: the default
            self.assertEqual(mb.attest_max_age(), 3600.0)
        # a DRIFT or a pause attested long ago is still a reason not to trade: it is never softened to none
        live = sr.tree_sha1(edited(sr.load_tree(self.man["KMLM"]["eras"][-1])))
        old = self.gated(attestation(self.man, D, KMLM={"version": "NEWVERSION0000000001", "tree_sha1": live}, HG={"paused": True}),
                         at=mb._iso(T - 7200 * SEC))
        self.assertEqual((old["sync"]["KMLM"]["state"], old["sync"]["HG"]["state"], old["sync"]["HG"]["paused"]), ("drift", "none", True))
        self.assertEqual(statuses(old), {"HG": "unavailable", "KMLM": "unavailable", "SLEEVE": "ok", "HARV": "ok"})

    def test_ok_drift_none(self):
        p = self.gated(attestation(self.man, D))
        self.assertEqual({e: s["state"] for e, s in p["sync"].items()}, dict.fromkeys(ENGINES, "ok"))
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        s = p["sync"]["HG"]
        era = self.man["HG"]["eras"][-1]
        self.assertEqual(s, {"state": "ok", "approved_version": era["version"], "approved_sha1": mb.approved_sha1(era),
                             "live_version": era["version"], "attested_utc": "2026-11-06T20:50:10Z"})
        self.assertFalse(any("attestation" in x for x in p["problems"]))
        # drift: Composer runs an edited KMLM under a new version
        live = sr.tree_sha1(edited(sr.load_tree(self.man["KMLM"]["eras"][-1])))
        p = self.gated(attestation(self.man, D, KMLM={"version": "NEWVERSION0000000001", "tree_sha1": live}))
        self.assertEqual({e: s["state"] for e, s in p["sync"].items()}, {"HG": "ok", "KMLM": "drift", "SLEEVE": "ok", "HARV": "ok"})
        self.assertEqual(statuses(p), {"HG": "ok", "KMLM": "unavailable", "SLEEVE": "ok", "HARV": "ok"})
        note = p["engines"]["KMLM"]["note"]
        self.assertIn("NEWVERSION0000000001", note)                             # both versions are named
        self.assertIn(self.man["KMLM"]["eras"][-1]["version"], note)
        self.assertNotIn("target", p["engines"]["KMLM"])
        self.assertEqual(p["sync"]["KMLM"]["live_version"], "NEWVERSION0000000001")
        # a new version with the approved logic (a rename) trades, and is said
        p = self.gated(attestation(self.man, D, HARV={"version": "RENAMED0000000000001"}))
        self.assertEqual((p["sync"]["HARV"]["state"], p["engines"]["HARV"]["status"]), ("ok", "ok"))
        self.assertTrue(any("RENAMED0000000000001" in x and "rename" in x for x in p["problems"]))
        # none: no attestation for this session (yesterday's does not count)
        p = self.gated(attestation(self.man, "2026-11-05"))
        self.assertEqual({e: s["state"] for e, s in p["sync"].items()}, dict.fromkeys(ENGINES, "none"))
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))             # trades, loudly
        self.assertTrue(any("no attestation of the live logic for 2026-11-06: HG, KMLM, SLEEVE, HARV" in x for x in p["problems"]))
        self.assertEqual((p["sync"]["HG"]["live_version"], p["sync"]["HG"]["attested_utc"]), (None, None))

    def test_require_attestation_makes_none_unavailable(self):
        partial = attestation(self.man, D)
        del partial["engines"]["SLEEVE"]
        with unittest.mock.patch.dict(os.environ, {"MIRROR_REQUIRE_ATTESTATION": "1"}):
            p = self.gated(partial)
            self.assertEqual(statuses(p), {"HG": "ok", "KMLM": "ok", "SLEEVE": "unavailable", "HARV": "ok"})
            self.assertIn("no attestation", p["engines"]["SLEEVE"]["note"])
            self.assertEqual(statuses(self.gated()), dict.fromkeys(ENGINES, "unavailable"))
        with unittest.mock.patch.dict(os.environ, {"MIRROR_REQUIRE_ATTESTATION": "0"}):
            self.assertEqual(statuses(self.gated(partial)), dict.fromkeys(ENGINES, "ok"))     # the twin

    def test_an_engine_attested_paused_is_not_mirrored(self):
        p = self.gated(attestation(self.man, D, HG={"paused": True}))
        self.assertEqual(statuses(p), {"HG": "unavailable", "KMLM": "ok", "SLEEVE": "ok", "HARV": "ok"})
        self.assertIn("paused", p["engines"]["HG"]["note"])
        self.assertEqual((p["sync"]["HG"]["state"], p["sync"]["HG"]["paused"]), ("ok", True))
        self.assertNotIn("paused", p["sync"]["KMLM"])


def edited(tree):
    """the tree with one LOGIC change: the first asset becomes another ticker"""
    out = copy.deepcopy(tree)

    def walk(n):
        if n.get("step") == "asset":
            n["ticker"] = "ZZZZ"
            return True
        return any(walk(k) for k in n.get("children") or [])
    assert walk(out)
    return out


class T4Attest(Http):
    def test_post_attest_auth_validation_and_storage(self):
        body = attestation(self.man, D)
        self.assertEqual(self.post(body, token="wrong")[0], 401)
        self.assertEqual(self.post(body, token=None)[0], 401)
        self.assertIsNone(self.attests.get(D))
        for bad in ({"session": D}, {"session": "tomorrow", "engines": body["engines"]}, {"session": D, "engines": {}},
                    {"session": "2026-11-05", "engines": body["engines"]},             # not today's session
                    {"session": D, "engines": {"HG": {"version": "v", "tree_sha1": "short"}}},
                    {"session": D, "engines": {"HG": {"version": "", "tree_sha1": "a" * 40}}},
                    {"session": D, "engines": {"HG": {"version": "v", "tree_sha1": "a" * 40, "paused": "yes"}}},
                    {"session": D, "engines": {"NOPE": {"version": "v", "tree_sha1": "a" * 40}}}, [1, 2]):
            self.assertEqual(self.post(bad)[0], 400, bad)
        self.assertEqual(self.post(None, raw=b"{not json")[0], 400)
        self.assertEqual(self.post(None, raw=b"x" * (mb.ATTEST_MAX_BYTES + 1))[0], 400)
        self.assertIsNone(self.attests.get(D))
        code, out = self.post(dict(body, engines=dict(body["engines"], OTHER={"version": "v", "tree_sha1": "b" * 40})))
        self.assertEqual((code, out["ok"], out["session"], out["stored"], out["ignored"]), (200, True, D, sorted(ENGINES), ["OTHER"]))
        self.assertEqual({e: s["state"] for e, s in out["sync"].items()}, dict.fromkeys(ENGINES, "ok"))
        self.assertEqual(self.attests.get(D)["engines"]["HG"]["attested_utc"], "2026-11-06T20:54:20Z")
        self.assertIs(out["pinned_already_built"], False)                       # in time: today's decision is not built yet
        code, p = self.get(self.url)                                            # and the pinned payload carries it
        self.assertEqual((code, {e: s["state"] for e, s in p["sync"].items()}), (200, dict.fromkeys(ENGINES, "ok")))
        self.assertEqual(self.get(self.base + "/mirror/attest")[0], 404)        # POST only

    def test_an_attestation_after_the_pinned_build_is_told_it_is_too_late(self):
        """the cached payload is immutable: an attestation posted after it is stored but not in it"""
        code, p = self.get(self.url)
        self.assertEqual((code, {e: s["state"] for e, s in p["sync"].items()}), (200, dict.fromkeys(ENGINES, "none")))
        code, out = self.post(attestation(self.man, D))
        self.assertEqual((code, out["ok"], out["pinned_already_built"]), (200, True, True))
        self.assertEqual(self.get(self.url)[1], p)                              # the payload did not move
        code, line, _ = self.run_attest()                                       # and the routine reports it
        self.assertEqual(code, 1)
        self.assertIn("TOO LATE", line)
        self.assertIn("posted 4 of 4", line)
        other = self.get(self.base + "/mirror/intents?after=" + mb._iso(T - 60 * SEC))[1]   # the twin: an instant built after it
        self.assertEqual({e: s["state"] for e, s in other["sync"].items()}, dict.fromkeys(ENGINES, "ok"))

    def test_attest_is_off_without_its_token(self):
        srv = mb.make_server(0, "tok", self.adhoc, window=lambda: False, attests=self.attests)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertEqual(self.post(attestation(self.man, D), token="")[0], 404)
        self.assertEqual(self.post(attestation(self.man, D), token="tok")[0], 404)   # the intents token is not the attest token

    def composer(self, drift=(), fail=(), paused=()):
        """a stubbed Composer read (GET only): each symphony's live tree and versions"""
        by_id = {cfg["symphony"]: eng for eng, cfg in self.man.items()}
        seen = []

        def get(path):
            seen.append(path)
            _, _, sid, what = path.split("/")
            eng = by_id[sid]
            if eng in fail:
                raise SystemExit(f"error: HTTP 503 on GET {path}\nService Unavailable")
            era = self.man[eng]["eras"][-1]
            if what == "score":
                tree = sr.load_tree(era)
                return edited(tree) if eng in drift else dict(tree, name="as Composer shows it")
            return [{"version_id": "EDITED00000000000001" if eng in drift else era["version"]}, {"version_id": "older"}]

        def meta():
            return [{"id": cfg["symphony"], "is_paused": eng in paused} for eng, cfg in self.man.items()]
        return get, meta, seen

    def run_attest(self, argv=(), env=None, **stub):
        get, meta, seen = self.composer(**stub)
        env = {"MIRROR_BRAIN_URL": self.base, "MIRROR_ATTEST_TOKEN": ATT} if env is None else env
        code, line = ma.run(list(argv), env, get=get, get_meta=meta, now=self.now[0])
        return code, line, seen

    def test_mirror_attest_end_to_end(self):
        code, line, seen = self.run_attest()
        self.assertEqual(code, 0, line)
        self.assertEqual(len(seen), 8)                                          # two GETs a symphony, nothing else
        self.assertTrue(all(p.endswith("/score") or p.endswith("/versions") for p in seen))
        self.assertIn("MIRROR ATTEST 2026-11-06", line)
        self.assertIn("posted 4 of 4", line)
        self.assertNotIn("\n", line)
        self.assertNotIn(ATT, line)
        stored = self.attests.get(D)["engines"]
        for eng, cfg in self.man.items():                                       # the live hash equals the brain's own
            self.assertEqual(stored[eng]["tree_sha1"], mb.approved_sha1(cfg["eras"][-1]))
            self.assertEqual(stored[eng]["paused"], False)
        code, p = self.get(self.url)
        self.assertEqual({e: s["state"] for e, s in p["sync"].items()}, dict.fromkeys(ENGINES, "ok"))

    def test_mirror_attest_reports_drift_and_the_brain_holds_that_engine(self):
        code, line, _ = self.run_attest(drift={"SLEEVE"}, paused={"HARV"})
        self.assertEqual(code, 0, line)                                         # posted: the brain decides what it means
        self.assertIn("SLEEVE drift (EDITED00", line)
        self.assertIn("the brain reads: HG ok, KMLM ok, SLEEVE drift, HARV ok", line)
        self.assertIn("paused", line)
        code, p = self.get(self.url)
        self.assertEqual(statuses(p), {"HG": "ok", "KMLM": "ok", "SLEEVE": "unavailable", "HARV": "unavailable"})
        self.assertIn("EDITED00000000000001", p["engines"]["SLEEVE"]["note"])
        self.assertIn("paused", p["engines"]["HARV"]["note"])

    def test_mirror_attest_failures_exit_1_and_leak_nothing(self):
        code, line, _ = self.run_attest(fail={"KMLM"})                          # one symphony unreadable: the rest are posted
        self.assertEqual(code, 1)
        self.assertIn("KMLM NOT READ", line)
        self.assertIn("posted 3 of 4", line)
        self.assertEqual(sorted(self.attests.get(D)["engines"]), ["HARV", "HG", "SLEEVE"])
        self.assertEqual(self.pinned(attest=self.attests)["sync"]["KMLM"]["state"], "none")
        secret = "S3CRET-TOKEN-VALUE"
        code, line, _ = self.run_attest(env={"MIRROR_BRAIN_URL": self.base, "MIRROR_ATTEST_TOKEN": secret})   # the wrong token
        self.assertEqual(code, 1)
        self.assertIn("NOT POSTED (HTTP 401", line)
        self.assertNotIn(secret, line)
        code, line, seen = self.run_attest(env={"MIRROR_BRAIN_URL": "http://brain.example.com", "MIRROR_ATTEST_TOKEN": secret})
        self.assertEqual((code, seen), (1, []))                                 # plain http to another host: refused unread
        self.assertIn("https", line)
        self.assertNotIn(secret, line)
        code, line, seen = self.run_attest(env={"MIRROR_BRAIN_URL": self.base})
        self.assertEqual((code, seen), (1, []))
        self.assertIn("MIRROR_ATTEST_TOKEN not set", line)
        code, line, _ = self.run_attest(fail=set(ENGINES))
        self.assertEqual(code, 1)
        self.assertIn("nothing to post", line)
        before = copy.deepcopy(self.attests.get(D))
        code, line, _ = self.run_attest(["--dry-run"], env={}, drift={"HG"})     # dry run: reads, compares, posts nothing
        self.assertEqual(code, 0)
        self.assertIn("HG drift", line)
        self.assertIn("dry run: not posted", line)
        self.assertEqual(self.attests.get(D), before)


# ------------------------------------------------------------------ T5 dividends Yahoo has not booked
class T5Dividends(Real):
    def setUp(self):
        self.saved = {k: (dict(v) if isinstance(v, dict) else v) for k, v in sr._ACTIONS.items() if k != "lock"}
        sr._ACTIONS.update(ok={}, bad={}, run=0, until=0.0)

    def tearDown(self):
        sr._ACTIONS.update(self.saved)

    def ind(self, fmp, fn, t, w, d):
        return sr.Shadow({t: self.yahoo(t, fmp)[0]}).ind(fn, t, w, d)

    def test_the_reviewers_numbers_before_and_after(self):
        cr, rsi = "cumulative-return", "relative-strength-index"
        for fn, t, w, d, before, after in ((cr, "SHY", 1, "2026-11-02", -0.29, 0.02), (cr, "TLT", 1, "2026-11-02", -0.13, 0.29),
                                           (cr, "HYG", 1, "2026-11-02", -0.70, -0.18), (rsi, "IEF", 8, "2026-11-09", 65.00, 69.87),
                                           (rsi, "CORP", 15, "2026-11-09", 59.64, 65.88), (rsi, "LQD", 12, "2026-11-09", 62.91, 68.16)):
            self.assertAlmostEqual(self.ind(False, fn, t, w, d), before, places=2, msg=f"{t} Yahoo alone")
            self.assertAlmostEqual(self.ind(True, fn, t, w, d), after, places=2, msg=f"{t} with FMP's list")
        # the amount applied is exactly the dividend: the closes before the ex-date move by 1 - amount / previous close
        a0, r0, _ = self.yahoo("SHY", False)
        a1, r1, _ = self.yahoo("SHY", True)
        self.assertEqual(r0, r1)                                                # raw closes are untouched
        prev = max(d for d in r0 if d < "2026-11-02")
        self.assertAlmostEqual(a1[prev] / a0[prev], 1 - 0.25443 / r0[prev], places=9)
        self.assertEqual({d: a1[d] for d in a1 if d >= "2026-11-02"}, {d: a0[d] for d in a0 if d >= "2026-11-02"})

    def test_a_dividend_yahoo_has_booked_is_never_applied_twice(self):
        booked = [t for t in self.fx["yahoo"] if self.fx["dividends"][t] and all(
            x["src"] != "fmp" or x["ex_date"] > "2026-11-09" for x in self.yahoo(t)[2]["corporateActions"]["dividends"])]
        self.assertGreater(len(booked), 25)                                     # e.g. PULS, BSV, TQQQ, ZVOL ...
        for t in booked:
            self.assertEqual(self.yahoo(t, True)[0], self.yahoo(t, False)[0], t)
        lacking = sorted(t for t in self.fx["yahoo"] if self.yahoo(t, True)[0] != self.yahoo(t, False)[0])
        self.assertEqual(lacking, ["ANGL", "BIL", "CORP", "HYG", "IEF", "LQD", "SHY", "SPAB", "TLT"])
        # a date the two sources disagree on by a day is ONE dividend (Yahoo's stands), never two
        res = self.fx["yahoo"]["PULS"]
        acts = self.actions("PULS")
        moved = {"dividends": [dict(x, ex_date=(datetime.date.fromisoformat(x["ex_date"]) - datetime.timedelta(days=1)).isoformat())
                               for x in acts["dividends"]], "splits": []}
        self.assertEqual(sr.parse_daily(res, moved), sr.parse_daily(res))
        ca = sr.corporate_actions(res["events"], moved, "2026-11-09")
        self.assertEqual({x["src"] for x in ca["dividends"]}, {"both"})
        far = {"dividends": [{"ex_date": "2026-10-14", "pay_date": None, "amount": 0.5}], "splits": []}   # broken twin: a real extra one
        self.assertNotEqual(sr.parse_daily(res, far)[0], sr.parse_daily(res)[0])

    def test_amounts_follow_a_later_split(self):
        """LABD: 1:10 reverse split on 2025-09-29. Yahoo restates earlier dividends (x10); FMP's 'dividend' is
        the cash as paid. An FMP-only dividend before the split is applied on the series' basis"""
        ev = {"splits": {"1": {"date": sr._noon("2025-09-29"), "numerator": 1, "denominator": 10}},
              "dividends": {"1": {"date": sr._noon("2025-09-23"), "amount": 0.5}}}
        acts = {"dividends": [{"ex_date": "2025-09-23", "pay_date": "2025-09-30", "amount": 0.05},
                              {"ex_date": "2025-06-24", "pay_date": "2025-07-01", "amount": 0.04}],
                "splits": [{"date": "2025-09-29", "numerator": 1.0, "denominator": 10.0}, {"date": "2026-12-01", "numerator": 2.0, "denominator": 1.0}]}
        ca = sr.corporate_actions(ev, acts, "2026-11-09")
        by = {x["ex_date"]: x for x in ca["dividends"]}
        self.assertEqual((by["2025-09-23"]["src"], by["2025-09-23"]["amount"], by["2025-09-23"]["pay_date"]), ("both", 0.05, "2025-09-30"))
        self.assertEqual(by["2025-06-24"]["src"], "fmp")
        self.assertAlmostEqual(by["2025-06-24"]["adj"], 0.4)                    # as paid 0.04, x10 on today's share basis
        self.assertAlmostEqual(by["2025-06-24"]["amount"], 0.04)
        self.assertEqual([(s["date"], s["src"]) for s in ca["splits"]], [("2025-09-29", "both"), ("2026-12-01", "fmp")])
        self.assertTrue(ca["fmp"])
        alone = sr.corporate_actions(ev, None, "2026-11-09")                    # Yahoo's alone: as paid = restated / 10
        self.assertFalse(alone["fmp"])
        self.assertAlmostEqual(alone["dividends"][0]["amount"], 0.05)
        self.assertIsNone(alone["dividends"][0]["pay_date"])

    def test_one_cached_call_per_ticker_per_day_and_none_without_a_key(self):
        calls, clock = [], [1_794_300_000.0]

        def fake(t, key):
            calls.append((t, key))
            return self.actions(t)
        chart = lambda url, timeout=30: self.fx["yahoo"]["SHY"]                 # noqa: E731
        with unittest.mock.patch.object(sr, "_chart", chart), unittest.mock.patch.object(sr, "fetch_actions", fake), \
                unittest.mock.patch.object(time, "time", lambda: clock[0]):
            plain = sr.fetch_yahoo("SHY")[0]                                    # no key: Yahoo's alone, FMP never asked
            self.assertEqual((calls, plain), ([], self.yahoo("SHY", False)[0]))
            self.assertNotIn("fmp", [x["src"] for x in pc.fetch_live("SHY")[2]["corporateActions"]["dividends"]])
            with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}):
                self.assertEqual(sr.fetch_yahoo("SHY")[0], self.yahoo("SHY", True)[0])     # the shadow runner's history
                adj, raw, meta = pc.fetch_live("SHY")                                       # the preview's and the brain's
                self.assertEqual(adj, self.yahoo("SHY", True)[0])
                self.assertEqual(meta["corporateActions"]["dividends"][-1],
                                 {"ex_date": "2026-11-02", "pay_date": "2026-11-05", "amount": 0.25443, "adj": 0.25443, "src": "fmp"})
                sr.fetch_yahoo("SHY")
                self.assertEqual(calls, [("SHY", "KEY")])                       # asked ONCE that day
                clock[0] += 86400
                sr.fetch_yahoo("SHY")
                self.assertEqual(len(calls), 2)                                 # and once the next

    def test_fmp_down_is_yahoo_alone_and_does_not_slow_every_fetch(self):
        calls, clock = [], [1_794_300_000.0]

        def down(t, key):
            calls.append(t)
            raise RuntimeError("FMP dividends/splits: HTTP 429")
        with unittest.mock.patch.object(sr, "fetch_actions", down), unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}):
            for t in ("A", "B", "A", "C", "D", "E", "F", "G"):
                self.assertIsNone(sr.fmp_actions(t, clock=lambda: clock[0]))
            self.assertEqual(calls, ["A", "B", "C", "D", "E"])                  # A not re-asked; after ACTIONS_TRIP, nobody
            clock[0] += sr.ACTIONS_RETRY + 1
            sr.fmp_actions("A", clock=lambda: clock[0])
            self.assertEqual(calls[-1], "A")                                    # tried again after the pause
        self.assertEqual(sr.parse_daily(self.fx["yahoo"]["SHY"], None), sr.parse_daily(self.fx["yahoo"]["SHY"]))

    def test_fmp_alone_is_trusted_only_for_a_recent_event_and_what_it_applied_is_named(self):
        """round 2, R7: an FMP-only dividend is taken when it is at most ACTIONS_RECENT days old at the series'
        last date (2026-11-09 here); an older one Yahoo would have booked, so it is more likely FMP's error"""
        res = self.fx["yahoo"]["PULS"]
        plain = sr.parse_daily(res)

        def only(ex_date):
            applied = []
            out = sr.parse_daily(res, {"dividends": [{"ex_date": ex_date, "pay_date": None, "amount": 0.5}], "splits": []}, applied)
            return out, applied
        out, applied = only("2026-10-12")                                       # 28 days
        self.assertNotEqual(out[0], plain[0])
        self.assertEqual(applied, [{"kind": "dividend", "date": "2026-10-12", "amount": 0.5}])
        out, applied = only("2026-10-09")                                       # 31 days: left alone, and not claimed
        self.assertEqual((out, applied), (plain, []))
        self.assertEqual(sr.ACTIONS_RECENT, 30)
        applied = []                                                            # one Yahoo has booked is not "applied" again
        booked = sr.parse_daily(res, self.actions("PULS"), applied)
        self.assertEqual((booked, applied), (plain, []))
        applied = []                                                            # an FMP-only split with no such jump in the prices
        sr.parse_daily(res, {"dividends": [], "splits": [{"date": "2026-11-05", "numerator": 1.0, "denominator": 5.0}]}, applied)
        self.assertEqual(applied, [])
        applied = []
        sr.parse_daily(self.fx["yahoo"]["SHY"], self.actions("SHY"), applied)
        self.assertEqual(applied, [{"kind": "dividend", "date": "2026-11-02", "amount": 0.25443}])
        # the brain says what was applied, in ONE line of `problems` for the run
        p = self.pinned()
        lines = [x for x in p["problems"] if x.startswith("history repaired from FMP's lists")]
        self.assertEqual(len(lines), 1)
        for t in ("ANGL", "BIL", "CORP", "HYG", "IEF", "LQD", "SHY", "SPAB", "TLT"):
            self.assertIn(f"{t} dividend 2026-11-02 ", lines[0])
        self.assertIn("SHY dividend 2026-11-02 0.25443", lines[0])
        self.assertEqual(lines[0].count("dividend"), 9)
        y = self.pinned(fetch=lambda t: self.yahoo(t, False))                    # the twin: nothing applied, nothing claimed
        self.assertFalse(any("history repaired" in x for x in y["problems"]))

    def test_a_burst_of_fmp_list_failures_is_repaired_within_the_warm_window(self):
        """round 2, R2 (the reviewer's history_fmp_blip): FMP's list calls fail at the first warm pass. The
        breaker closes again well inside the 30-minute window, a history whose lists were not read is not
        final, and a later warm pass repairs it. With the old 600 s pause and 'final' histories the whole
        session decided on Yahoo's unrepaired series"""
        self.assertLess(sr.ACTIONS_RETRY * 10, 30 * 60 + 1)
        clock, fail, asked = [1_794_340_000.0], [True], []
        now = [T - 30 * 60 * SEC]

        def chart(url, timeout=30):
            return self.fx["yahoo"][url.split("/chart/")[1].split("?")[0]]

        def lists(t, key, timeout=10):
            asked.append(t)
            if fail[0]:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            return self.actions(t)
        want = sorted(mb.feed_tickers(self.man, D))
        with unittest.mock.patch.object(sr, "_chart", chart), unittest.mock.patch.object(sr, "fetch_actions", lists), \
                unittest.mock.patch.object(time, "time", lambda: clock[0]), \
                unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}):
            h = mb.History(wall=lambda: now[0], clock=lambda: clock[0])         # the real preclose.fetch_live behind it
            self.assertEqual(h.warm(want), {})                                  # T-30 min: Yahoo answers, FMP's lists do not
            st = h.state()
            self.assertEqual((st["tickers"], st["final"], st["lists_unread"]), (len(want), 0, want))
            self.assertLessEqual(len(asked), sr.ACTIONS_TRIP + 8)               # the breaker: FMP is not hammered
            self.assertAlmostEqual(sr.Shadow({"SHY": h.fetch("SHY")[0]}).ind("cumulative-return", "SHY", 1, "2026-11-02"), -0.29, places=2)
            p = mb.build(T, quotes=self.quotes(), fetch=h.fetch, pinned=True, wall=lambda: T + 25 * SEC)
            self.assertIs(p["actions_complete"], False)                         # a decision that went out now would say so
            fail[0] = False
            for k in range(1, 4):                                               # T-29, T-28, T-27: the breaker's pause ends
                clock[0] += 60
                now[0] += 60 * SEC
                h.warm(want)
            st = h.state()
            self.assertEqual((st["final"], st["lists_unread"]), (len(want), []))
            self.assertAlmostEqual(sr.Shadow({"SHY": h.fetch("SHY")[0]}).ind("cumulative-return", "SHY", 1, "2026-11-02"), 0.02, places=2)
            calls = st["calls"]
            for k in range(10):                                                 # and once final nothing is asked again
                clock[0] += 60
                now[0] += 60 * SEC
                h.warm(want)
            self.assertEqual(h.state()["calls"], calls)
            now[0] = T + 25 * SEC
            p = mb.build(T, quotes=self.quotes(), fetch=h.fetch, pinned=True, wall=lambda: T + 25 * SEC)
            self.assertIs(p["actions_complete"], True)
            self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))

    def test_the_build_itself_retries_a_history_whose_lists_were_not_read(self):
        """no warm pass got to it (the brain restarted at the instant, say): the build asks again, RECHECK_S apart,
        and keeps what it has if that fails; a history that only lacks a bar is NOT refetched by a build"""
        clock, now, mode, calls = [1000.0], [T + 25 * SEC], ["yahoo"], []

        def fetch(t):
            calls.append(t)
            if mode[0] == "down":
                raise RuntimeError("Yahoo down")
            return self.yahoo(t, mode[0] == "fmp")
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}):
            h = mb.History(fetch=fetch, wall=lambda: now[0], clock=lambda: clock[0])
            self.assertFalse(h.fetch("SHY")[2]["corporateActions"]["fmp"])
            h.fetch("SHY")
            self.assertEqual(len(calls), 1)                                     # not again within RECHECK_S
            clock[0] += mb.RECHECK_S
            mode[0] = "down"
            self.assertFalse(h.fetch("SHY")[2]["corporateActions"]["fmp"])      # the retry failed: what it had stands
            self.assertEqual(len(calls), 2)
            clock[0] += mb.RECHECK_S
            mode[0] = "fmp"
            self.assertTrue(h.fetch("SHY")[2]["corporateActions"]["fmp"])       # repaired by the build's own retry
            clock[0] += 10 * mb.RECHECK_S
            h.fetch("SHY")
            self.assertEqual(len(calls), 3)                                     # final now
        h2 = mb.History(fetch=fetch, wall=lambda: now[0], clock=lambda: clock[0])   # the twin: no key, nothing to retry
        mode[0] = "yahoo"
        h2.fetch("SHY")
        clock[0] += 10 * mb.RECHECK_S
        h2.fetch("SHY")
        self.assertEqual(len(calls), 4)
        self.assertEqual(h2.state()["final"], 1)

    def test_the_shadow_runners_recorded_targets_do_not_move(self):
        """the post-close check reads the same history: on closing prices, its ledger targets for the six
        sessions since the unbooked ex-date are reproduced with FMP's dividends applied (and without)"""
        days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
        n = 0
        for fmp in (True, False):
            prices = {}
            for eng, cfg in self.man.items():
                tree = sr.load_tree(cfg["eras"][-1])
                for t in sr.tree_tickers(tree):
                    if t not in prices:
                        prices[t] = self.yahoo(t, fmp)[0]
                for d in days:
                    row = ledger(d)[eng]
                    _, target, _ = sr.run_engine(prices, tree, d)
                    self.assertTrue(pc.same(target, row["target"]), (fmp, eng, d, target, row["target"]))
                    n += 1
        self.assertEqual(n, 48)


# ------------------------------------------------------------------ T6 dividends and splits in the payload
class T6Published(Real):
    def test_dividends_of_the_last_ten_days(self):
        p = self.pinned()
        self.assertEqual([(x["ticker"], x["ex_date"]) for x in p["dividends"]],
                         [("PULS", "2026-10-30")] + [(t, "2026-11-02") for t in ("ANGL", "BIL", "BSV", "CORP", "HYG", "IEF", "LQD", "SHY", "SPAB", "TLT")])
        by = {x["ticker"]: x for x in p["dividends"]}
        self.assertEqual(by["SHY"], {"ticker": "SHY", "ex_date": "2026-11-02", "pay_date": "2026-11-05", "amount": 0.25443})
        self.assertEqual(by["PULS"], {"ticker": "PULS", "ex_date": "2026-10-30", "pay_date": "2026-11-03", "amount": 0.1834})
        self.assertEqual(by["BSV"]["amount"], 0.27431)                          # FMP's cash as paid, not Yahoo's rounded 0.274
        self.assertEqual(p["splits"], [])
        self.assertTrue(set(by) <= mb.era_tickers(self.man))                    # every era's tickers: ANGL, SPAB are era-only
        self.assertTrue({"ANGL", "SPAB"} <= set(by))
        self.assertIs(p["actions_complete"], True)
        self.assertFalse(any("not read" in x for x in p["problems"]))
        # ten calendar days, to the session: the same ex-dates are out of the window on 08-28
        aug = self.pinned(datetime.datetime(2026, 8, 28, 19, 54, tzinfo=UTC))
        self.assertTrue(aug["dividends"])
        self.assertTrue(all("2026-08-18" <= x["ex_date"] <= "2026-08-28" for x in aug["dividends"]))
        # BROKEN twin: without FMP's list only what Yahoo has booked is there, with no pay date, and it is said
        y = self.pinned(fetch=lambda t: self.yahoo(t, False))
        self.assertEqual(y["dividends"], [{"ticker": "PULS", "ex_date": "2026-10-30", "pay_date": None, "amount": 0.183},
                                          {"ticker": "BSV", "ex_date": "2026-11-02", "pay_date": None, "amount": 0.274}])
        self.assertIs(y["actions_complete"], False)                             # ... as a field, not only as text
        line = next(x for x in y["problems"] if "lists not read for 52 ticker(s)" in x)
        for t in mb.era_tickers(self.man):                                      # every ticker is named, none cut off
            self.assertIn(t, line)

    def test_splits_as_new_shares_per_old_share(self):
        extra = {"SQQQ": [{"date": "2026-11-05", "numerator": 1.0, "denominator": 5.0, "src": "both"}],        # 1:5 reverse
                 "TQQQ": [{"date": "2026-11-06", "numerator": 2.0, "denominator": 1.0, "src": "yahoo"},        # 2:1 today
                          {"date": "2026-10-26", "numerator": 3.0, "denominator": 1.0, "src": "yahoo"}],       # eleven days ago
                 "VIXM": [{"date": "2026-11-19", "numerator": 1.0, "denominator": 2.0, "src": "fmp"}]}         # announced, not yet

        def fetch(t):
            adj, raw, meta = self.yahoo(t)
            ca = dict(meta["corporateActions"], splits=meta["corporateActions"]["splits"] + extra.get(t, []))
            return adj, raw, dict(meta, corporateActions=ca)
        p = self.pinned(fetch=fetch)
        self.assertEqual(p["splits"], [{"ticker": "SQQQ", "date": "2026-11-05", "ratio": 0.2},
                                       {"ticker": "TQQQ", "date": "2026-11-06", "ratio": 2.0}])
        real = [s for s in self.yahoo("VIXM")[2]["corporateActions"]["splits"]]  # FMP lists the 2026-11-19 1:2 ahead of Yahoo
        self.assertEqual([(s["date"], s["src"]) for s in real], [("2026-11-19", "fmp")])

    def test_a_history_source_without_events_is_said(self):
        def bare(t):
            adj, raw, meta = self.yahoo(t)
            meta.pop("corporateActions")
            return adj, raw, meta
        p = self.pinned(fetch=bare)
        self.assertEqual((p["dividends"], p["splits"], p["actions_complete"]), ([], [], False))
        self.assertTrue(any("dividends and splits not read for 52 ticker(s)" in x for x in p["problems"]), p["problems"])
        closed = self.pinned(T + 3600 * SEC)                                    # no decision at all: nothing was read
        self.assertIs(closed["actions_complete"], False)


# ------------------------------------------------------------------ T7 an honest replay
class T7Replay(Real):
    A = "2026-08-28"

    def test_2026_08_28_reproduces_composer(self):
        at = datetime.datetime(2026, 8, 28, 19, 54, tzinfo=UTC)                 # 15:54 EDT
        p = mb.build(at, quotes=self.quotes(), fetch=self.yahoo, pinned=True)
        self.assertEqual((p["session"], p["replay"], p["decision_bar"]["complete"]), (self.A, True, True))
        rows = ledger(self.A)
        for eng in ENGINES:
            self.assertEqual(p["engines"][eng]["status"], "ok", eng)
            self.assertTrue(pc.same(p["engines"][eng]["target"], rows[eng]["live"]), (eng, p["engines"][eng]["target"], rows[eng]["live"]))
        # the history is today's (every dividend since taken out), so that day's factor is below 1 for the payers ...
        adj, raw, _ = self.yahoo("TLT")
        self.assertLess(pc.day_factor(adj, raw, self.A), 0.99)
        # ... and the published prices are still the RAW minute prices of that day
        for t in ("TLT", "PULS", "SPY", "LABD"):
            b = self.bars(t, self.A)
            self.assertAlmostEqual(p["prices"][t], b[max(k for k in b if k <= "15:53")], places=6, msg=t)

        # BROKEN twin (what `--at` did): the raw minute price on the adjusted history, no scaling. Yahoo's own bar
        # for the day is what gives the factor: without it every dividend since reads as a return on 08-28
        def no_bar(t):
            adj, raw, meta = self.yahoo(t)
            adj.pop(self.A)
            raw.pop(self.A)
            return adj, raw, meta
        q = mb.build(at, quotes=self.quotes(), fetch=no_bar, pinned=True)
        wrong = [eng for eng in ENGINES if not pc.same(q["engines"][eng]["target"], rows[eng]["live"])]
        self.assertEqual(wrong, ["KMLM", "SLEEVE", "HARV"])
        self.assertEqual(q["prices"], p["prices"])

    def test_merge_quotes_scales_only_a_past_day(self):
        now = datetime.datetime(2026, 8, 28, 19, 54, tzinfo=UTC)
        adj, raw, meta = self.yahoo("TLT")
        f = adj[self.A] / raw[self.A]
        q = {"TLT": (80.0, now)}
        out, src, _ = pc.merge_quotes({"TLT": (adj, raw, meta)}, q, self.A, now, now)
        self.assertEqual((src["TLT"], out["TLT"][1][self.A]), ("fmp", 80.0))
        self.assertAlmostEqual(out["TLT"][0][self.A], 80.0 * f, places=9)       # on the adjusted series' scale
        self.assertAlmostEqual(out["TLT"][0][self.A] / out["TLT"][0]["2026-08-27"], 80.0 / raw["2026-08-27"], places=6)   # no phantom return
        live = {d: v for d, v in raw.items() if d <= self.A}                    # a live day: adjusted == raw on the last bar
        out, _, _ = pc.merge_quotes({"TLT": (dict(live), dict(live), dict(meta, regularMarketTime=int(now.timestamp()) - 30))},
                                    q, self.A, now, None)
        self.assertEqual((out["TLT"][0][self.A], out["TLT"][1][self.A]), (80.0, 80.0))   # exactly as before
        self.assertEqual(pc.day_factor(live, live, self.A), 1.0)
        self.assertEqual(pc.day_factor({}, {}, self.A), 1.0)


# ------------------------------------------------------------------ T8 load and time
class T8Load(Real):
    def test_the_sessions_history_is_fetched_once(self):
        calls, now = [], [T - 600 * SEC]

        def fetch(t):
            calls.append(t)
            return self.yahoo(t)
        h = mb.History(fetch=fetch, wall=lambda: now[0], clock=lambda: now[0].timestamp())
        want = mb.feed_tickers(self.man, D)                                     # every era's tickers, SPY, the siblings
        self.assertTrue(mb.era_tickers(self.man) | {"SPY"} < want)
        self.assertTrue(mb.warm_once(h, now[0]))                                # ten minutes before the instant
        self.assertEqual(sorted(calls), sorted(want))
        self.assertEqual(h.state()["final"], len(want))
        for k in range(1, 10):                                                  # every later warm and build: no call
            now[0] = T - 600 * SEC + 60 * k * SEC
            mb.warm_once(h, now[0])
        p = mb.build(T, quotes=self.quotes(), fetch=h.fetch, pinned=True, wall=lambda: T + 25 * SEC)
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        self.assertEqual(len(calls), len(want))
        self.assertFalse(mb.warm_once(h, T - 3600 * SEC))                        # outside the window nothing is asked
        self.assertFalse(mb.in_window(T - 31 * 60 * SEC))
        self.assertTrue(mb.in_window(T - 30 * 60 * SEC))                         # thirty minutes: room to retry FMP's lists
        self.assertGreaterEqual(mb.WARM_FROM_MIN * 60, 10 * sr.ACTIONS_RETRY)
        self.assertFalse(mb.in_window(T + 6 * 60 * SEC))                         # the close
        now[0] = T + 86400 * 3 * SEC                                            # another day: the cache starts over
        h.fetch("SPY")
        self.assertEqual(calls[-1], "SPY")

    def test_a_history_that_is_not_final_is_asked_again(self):
        calls, now, short = [], [T - 300 * SEC], [True]

        def fetch(t):
            calls.append(t)
            adj, raw, meta = self.yahoo(t)
            if short[0]:                                                        # Yahoo has not posted yesterday's bar yet
                adj.pop("2026-11-05")
                raw.pop("2026-11-05")
            return adj, raw, meta
        h = mb.History(fetch=fetch, wall=lambda: now[0], clock=lambda: now[0].timestamp())
        self.assertNotIn("2026-11-05", h.refresh("TQQQ")[0])
        h.refresh("TQQQ")
        self.assertEqual(len(calls), 1)                                         # not hammered ...
        now[0] += (mb.RECHECK_S + 1) * SEC
        short[0] = False
        self.assertNotIn("2026-11-05", h.fetch("TQQQ")[0])                      # a BUILD never waits on Yahoo for what it has
        self.assertEqual(len(calls), 1)
        self.assertIn("2026-11-05", h.refresh("TQQQ")[0])                       # ... the warm loop asks again: now complete
        now[0] += 3600 * SEC
        h.refresh("TQQQ")
        self.assertEqual(len(calls), 2)
        self.assertIn("2026-11-05", h.fetch("TQQQ")[0])

        calls.clear()                                                           # the interval runs on the WALL clock (the
        short[0] = True                                                         # one the day is read from), no other
        h1 = mb.History(fetch=fetch, wall=lambda: now[0])
        h1.refresh("TQQQ")
        now[0] += (mb.RECHECK_S - 1) * SEC
        h1.refresh("TQQQ")
        self.assertEqual(len(calls), 1)
        now[0] += 1 * SEC
        h1.refresh("TQQQ")
        self.assertEqual(len(calls), 2)

        def down(t):
            raise RuntimeError("Yahoo down")
        h2 = mb.History(fetch=down, wall=lambda: now[0])
        self.assertRaises(RuntimeError, h2.fetch, "SPY")
        self.assertEqual(h2.state()["tickers"], 0)                               # a failure is never kept

    def test_the_mirrors_fmp_budget_is_its_own(self):
        self.assertEqual(pc.FMP_BUDGET, 90)                                     # the 15:15 preview's is untouched
        self.assertLessEqual(mb.FMP_BUDGET_S, 10)
        seen = {}
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}), \
                unittest.mock.patch.object(pc, "minute_quotes", lambda tickers, now, key, **kw: seen.update(kw) or ({}, {})):
            pc.fmp_quotes(budget=mb.FMP_BUDGET_S, fetch=mb._minutes)({"SPY"}, T)
        self.assertEqual(seen, {"fetch": mb._minutes, "budget": mb.FMP_BUDGET_S})
        with unittest.mock.patch.object(sr, "fetch_minutes", lambda t, d, key, **kw: seen.update(kw) or {}):
            mb._minutes("SPY", D, "KEY")
        self.assertEqual((seen["tries"], seen["traded"], seen["timeout"]), (1, True, mb.FMP_TIMEOUT_S))
        asked = []                                                              # and build() itself asks FMP that way

        def fake(tickers, now, key, fetch=None, budget=None):
            asked.append((fetch, budget))
            raise RuntimeError("stop here")
        with unittest.mock.patch.dict(os.environ, {"FMP_API_KEY": "KEY"}), unittest.mock.patch.object(pc, "minute_quotes", fake):
            mb.build(T, fetch=self.yahoo, pinned=True, wall=lambda: T + 25 * SEC)
        self.assertEqual(asked[0], (mb._minutes, mb.FMP_BUDGET_S))

        def slow(t, d, key):                                                    # one ticker hangs
            if t == "TQQQ":
                time.sleep(3)
            return self.bars(t, d)
        b = mb.Bars(T, "k", fetch=slow, budget=0.5)
        t0 = time.time()
        b.load(mb.feed_tickers(self.man, D))
        self.assertLess(time.time() - t0, 2.5)                                  # the budget, not the hang
        self.assertIn("no answer within 0.5 s", b.probs["TQQQ"])
        self.assertIn("FMP has not answered for TQQQ", b.unsettled())
        p = mb.build(T, quotes=b.quotes, fetch=self.yahoo, pinned=True, wall=lambda: T + 50 * SEC)
        self.assertIn("via", p["price_notes"]["TQQQ"])                          # flagged, as the preview does
        self.assertIn("unavailable", {r["status"] for r in p["engines"].values()})

    def test_built_utc_is_stamped_when_the_build_ends(self):
        ticks = iter([T + 25 * SEC, T + 31 * SEC])
        p = mb.build(T, quotes=self.quotes(), fetch=self.yahoo, pinned=True, wall=lambda: next(ticks))
        self.assertEqual((p["asof_utc"], p["built_utc"]), ("2026-11-06T20:54:00Z", "2026-11-06T20:54:31Z"))

    def test_a_retry_asks_fmp_only_for_what_was_missing(self):
        fmp = Fmp(self.bars)
        fmp.lag = {"QLD": "15:52", "SOXL": "15:52"}
        b = mb.Bars(T, "k", fetch=fmp)
        want = mb.feed_tickers(self.man, D)
        b.load(want)
        first = len(fmp.calls)
        self.assertEqual(first, len(want))
        self.assertEqual(b.q["QLD"][1], T - 60 * SEC)
        fmp.lag = {}
        b.load(want)
        again = fmp.calls[first:]
        self.assertTrue({"QLD", "SOXL"} <= set(again))
        self.assertLess(len(again), 12)                                         # the two that lagged and the thin funds
        self.assertEqual(b.q["QLD"][1], T)
        self.assertIsNone(b.unsettled())
        cut = Fmp(self.bars)
        cut.cut = "15:52"
        self.assertRaises(mb.NotPublished, mb.Bars(T, "k", fetch=cut).load, want)
        self.assertEqual(cut.calls, ["SPY"])


# ------------------------------------------------------------------ T9 only a settled decision is cached
class T9Settled(Http):
    def attempt_with(self, fetch):
        self.pinned_cache.attempt = mb.pinned_attempt(self.hist, self.attests, key="k", wall=lambda: self.now[0], fetch_minutes=fetch)

    def test_a_run_of_fmp_429s_does_not_freeze_the_session(self):
        """the reviewer's case (round 2, R1): FMP answers 429 for 40% of the tickers until T+50 s, then is
        healthy. The build that used to go out at T+47 s (breadth 27 of 48, every engine unavailable, complete,
        cached for good) is never made; the first request after the feed is back gets the real decision"""
        feed = sorted(mb.feed_tickers(self.man, D))
        bad = {t for i, t in enumerate(feed) if i % 5 in (1, 3) and t != "SPY"}
        self.assertGreater(len(bad), 20)
        real, n = self.fmp.__call__, []

        def flaky(t, d, key):
            if t in bad and self.now[0] < T + 50 * SEC:
                self.fmp.calls.append(t)
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            return real(t, d, key)
        self.attempt_with(flaky)
        built = mb.build

        def counted(*a, **k):
            n.append(self.now[0])
            return built(*a, **k)
        asked = []
        with unittest.mock.patch.object(mb, "build", counted):
            for s in (26, 29, 35, 44, 47):
                self.now[0] = T + s * SEC
                code, body = self.get(self.url)
                self.assertEqual((code, body["error"]), (503, "decision not settled yet"), s)
                self.assertIn("FMP has not answered for", body["detail"])
                asked.append(len(self.fmp.calls))
            self.assertEqual(n, [])                                             # no decision is built on a partial answer
            self.assertEqual(self.pinned_cache.state()["instants"], [])
            self.assertEqual(self.pinned_cache.builds, 2)                       # tried at T+26 and T+44: every 10 s at most
            self.assertEqual((asked[1], asked[2], asked[4]), (asked[0], asked[0], asked[3]))   # the rest asked FMP nothing
            self.assertLess(asked[3] - asked[0], len(bad) + 12)                 # and a retry asks only for what was missing
            self.now[0] = T + 60 * SEC
            code, p = self.get(self.url)
            self.assertEqual(code, 200)
            self.assertEqual(n, [T + 60 * SEC])
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "ok"))
        self.assertEqual((p["quotes"]["breadth"]["recent"], p["decision_bar"]["complete"], p["built_utc"]), (48, True, "2026-11-06T20:55:00Z"))
        self.assertFalse(any("FMP" in x and "answered" in x for x in p["problems"]))
        for s in (120, 200):                                                    # settled: cached, never rebuilt
            self.now[0] = T + s * SEC
            self.assertEqual(self.get(self.url), (200, p))
        self.assertEqual(self.pinned_cache.builds, 3)

    def test_an_engine_down_for_a_feed_reason_is_never_a_cached_answer(self):
        """breadth: every ticker but SPY stuck at the bar starting 15:38, FMP answering for all of them"""
        stuck = dict.fromkeys([t for t in self.fx["bars"][D] if t != "SPY"], "15:38")
        self.fmp.lag = dict(stuck)
        for s in (26, 50, 100, 200):                                            # no give-up build, however long it lasts
            self.now[0] = T + s * SEC
            code, body = self.get(self.url)
            self.assertEqual((code, body["error"]), (503, "decision not settled yet"), s)
            self.assertIn("the feed looks dead: 1 of 48", body["detail"])
        self.assertEqual(self.pinned_cache.state()["instants"], [])
        builds = self.pinned_cache.builds
        self.assertEqual(self.get(self.url)[0], 503)                            # within REBUILD_EVERY_S: the answer stands
        self.now[0] += (mb.REBUILD_EVERY_S - 1) * SEC
        self.assertEqual(self.get(self.url)[0], 503)
        self.assertEqual(self.pinned_cache.builds, builds)
        got = []                                                                # five requests at once while unsettled: one attempt
        self.now[0] += 1 * SEC
        ts = [threading.Thread(target=lambda: got.append(self.get(self.url)[0])) for _ in range(5)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        self.assertEqual((got, self.pinned_cache.builds), ([503] * 5, builds + 1))
        self.fmp.lag = {}                                                       # the feed comes back
        self.now[0] += mb.REBUILD_EVERY_S * SEC
        code, p = self.get(self.url)
        self.assertEqual((code, statuses(p)), (200, dict.fromkeys(ENGINES, "ok")))

    def test_a_decision_ticker_on_an_estimate_keeps_the_answer_open(self):
        self.fmp.lag = {"TQQQ": "15:30"}                                        # FMP answers; TQQQ's last trade is 15:31
        code, body = self.get(self.url)
        self.assertEqual((code, body["error"]), (503, "decision not settled yet"))
        self.assertIn("TQQQ priced by an estimate", body["detail"])
        self.assertIn("unavailable on the feed as it is", body["detail"])
        self.fmp.lag = {}
        self.now[0] += mb.REBUILD_EVERY_S * SEC
        code, p = self.get(self.url)
        self.assertEqual((code, statuses(p)), (200, dict.fromkeys(ENGINES, "ok")))
        self.assertEqual(p["price_times"]["TQQQ"], "2026-11-06T20:54:00Z")

    def test_an_engine_down_for_a_reason_the_feed_cannot_change_is_a_settled_answer(self):
        """the twin: tree drift, a pause and a history a session short, on a healthy feed"""
        live = sr.tree_sha1(edited(sr.load_tree(self.man["KMLM"]["eras"][-1])))
        body = attestation(self.man, D, KMLM={"version": "NEWVERSION0000000001", "tree_sha1": live}, HARV={"paused": True})
        self.assertEqual(self.post(body)[0], 200)

        def yahoo(t):
            adj, raw, meta = self.yahoo(t)
            if t == "LABD":                                                     # read by SLEEVE alone among the engines left
                adj.pop("2026-11-05")
                raw.pop("2026-11-05")
            return adj, raw, meta
        only = [e for e in ENGINES if "LABD" in sr.decision_tickers(sr.load_tree(self.man[e]["eras"][-1]))]
        self.hist._fetch = yahoo
        code, p = self.get(self.url)
        self.assertEqual(code, 200)                                             # at once: nothing here will change
        want = {e: "unavailable" if e in ("KMLM", "HARV") or e in only else "ok" for e in ENGINES}
        self.assertEqual(statuses(p), want)
        self.assertIn("unavailable", want.values())
        self.assertIn("ok", want.values())
        self.assertEqual(self.pinned_cache.state()["instants"], ["2026-11-06T20:54:00Z"])
        self.now[0] = T + 200 * SEC
        self.assertEqual(self.get(self.url), (200, p))

    def test_build_reports_feed_reasons_apart_from_the_others(self):
        diag = {}
        self.pinned(diag=diag)
        self.assertEqual(diag, {"feed": {}})
        diag = {}
        p = self.pinned(quotes=self.quotes(cut="15:38"), diag=diag)             # a stalled feed: every engine, for the feed
        self.assertEqual(sorted(diag["feed"]), sorted(ENGINES))
        self.assertIn("the feed looks dead", diag["feed"]["HG"])
        self.assertEqual(statuses(p), dict.fromkeys(ENGINES, "unavailable"))

        def short(t):
            adj, raw, meta = self.yahoo(t)
            if t in ("UVXY", "TQQQ"):
                adj.pop("2026-11-05")
                raw.pop("2026-11-05")
            return adj, raw, meta
        diag = {}
        p = self.pinned(fetch=short, diag=diag)                                 # a short history: unavailable, not for the feed
        self.assertIn("unavailable", statuses(p).values())
        self.assertEqual(diag["feed"], {})

        def gone(t):
            if t == "PEJ":
                raise RuntimeError("Yahoo PEJ: timed out")
            return self.yahoo(t)
        diag = {}
        p = self.pinned(fetch=gone, diag=diag)                                  # a price the read did not get: the feed's
        reads = [e for e in ENGINES if "PEJ" in sr.tree_tickers(sr.load_tree(self.man[e]["eras"][-1]))]
        self.assertEqual(sorted(diag["feed"]), sorted(reads))
        self.assertIn("no prices for PEJ", diag["feed"][reads[0]])


if __name__ == "__main__":
    unittest.main()
