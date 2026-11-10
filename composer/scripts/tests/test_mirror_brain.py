"""Gate tests for mirror_brain.py (the Composer mirror's keyless decision brain; IBKR_MIRROR.md), on
the frozen 2026-10-28 session (Yahoo's prices alone). The pinned decision, the dead-data rules, the
tree-version gate, dividends and the replay are gated on real minute data in test_mirror_pinned.py.

Each behavioural test has a BROKEN-INPUT counterpart that must land on the other side.

  B1  the payload on the frozen 2026-10-28 prices: the approved trees' targets, each engine's rule
      (KMLM threshold 10pp, the rest daily), full tree versions; the KMLM target is the TREE's, not
      the holdings Composer keeps inside its corridor (the executor applies the corridor to its own
      book); an engine whose prices are missing is unavailable while the others still decide
  B2  no decision outside a session, with the reason; Yahoo down likewise; a crash inside the preview
      never escapes: every engine unavailable
  B3  nothing about Composer's holdings leaks into the payload (the brain never reads Composer)
  B4  --at parses ET wall times across DST
  B5  the HTTP surface: /health public; /mirror/intents 404 with no token configured, 401 on a wrong
      token, 200 with the ad hoc payload on the right one, 503 before any payload; the cache recomputes
      when stale, single flight (two overlapping requests share ONE build), and keeps the last good
      payload when a rebuild fails
  B6  the reference prices: every ticker of ANY era of the manifest is priced (a sleeve may still hold
      what a newer tree dropped), the current trees' at the prices the engines were evaluated on, each
      with the time it is from; a price rebuilt or carried is named in price_notes; none without a
      session; an era-only ticker that cannot be priced is said
  B7  the executor's clock (schema 2): decide_utc is the close minus DECISION_MINUTE exactly, the instant
      shadow_runner.minute_price reads, on a full day, a half-day and across DST; a holiday and a weekend
      have no session; a year past the calendar tables has none either, with the reason;
      /mirror/session behind the same token
  B8  ?after=: a malformed, future or off-the-minute instant is refused before anything is computed

Run: python3 -m unittest composer.scripts.tests.test_mirror_brain -v
"""
import datetime
import json
import os
import sys
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.pop("FMP_API_KEY", None)
import mirror_brain as mb  # noqa: E402
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402
from test_preclose import PreviewBase, et  # noqa: E402

UTC = datetime.timezone.utc


def attested(day, **override):
    """an attestation store as mirror_attest.py would leave it: every engine's live tree == the approved"""
    out = {}
    for eng, cfg in sr.load_manifest().items():
        era = mb.era_of(cfg, day)
        out[eng] = dict({"version": era["version"], "tree_sha1": mb.approved_sha1(era), "paused": False,
                         "attested_utc": f"{day}T20:50:00Z"}, **override.get(eng, {}))
    return {day: {"engines": out}}


class Base(PreviewBase):
    def setUp(self):
        super().setUp()
        cal = sorted(self.fx["prices"]["SPY"])
        self.old = sorted(mb.era_tickers(sr.load_manifest()) - set(self.fx["prices"]))   # held by an earlier era only
        for i, t in enumerate(self.old):
            self.extra[t] = {d: 20.0 + i + 0.01 * k for k, d in enumerate(cal)}
        self.attest = attested("2026-10-28")

    def fetch_ca(self, t):
        """as preclose.fetch_live: the chart's meta carries the ticker's dividends and splits"""
        a, r, m = self.fetch(t)
        return a, r, dict(m, corporateActions={"dividends": [], "splits": [], "fmp": True})

    def build(self, now=None, **kw):
        return mb.build(now or self.now, quotes=self.quotes, fetch=self.fetch_ca, attest=self.attest, **kw)


class B1Payload(Base):
    def test_targets_rules_versions(self):
        p = self.build()
        self.assertEqual((p["schema"], p["kind"], p["session"], p["close_et"]), (2, mb.KIND, "2026-10-28", "16:00"))
        self.assertTrue(p["replay"])
        self.assertEqual((p["pinned"], p["decision_bar"]), (False, None))     # ad hoc: the executor refuses it
        self.assertEqual(p["asof_utc"], "2026-10-28T19:15:00Z")
        self.assertGreaterEqual(p["built_utc"], "2026-11-10T00:00:00Z")       # stamped by the wall clock at the end
        self.assertEqual(p["problems"], [])
        self.assertEqual({s["state"] for s in p["sync"].values()}, {"ok"})
        self.assertEqual((p["dividends"], p["splits"]), ([], []))
        man = sr.load_manifest()
        self.assertEqual(list(p["engines"]), list(man))
        for eng in ("HG", "SLEEVE", "HARV"):
            r = p["engines"][eng]
            self.assertEqual((r["status"], r["rule"], r["corridor"]), ("ok", "daily", None), eng)
            self.assertTrue(pc.same(r["target"], self.fx["expected"][eng]["2026-10-28"]), eng)
            self.assertAlmostEqual(sum(r["target"].values()), 1.0, places=9)
            self.assertEqual(r["version"], man[eng]["eras"][-1]["version"])
            self.assertEqual(r["symphony"], man[eng]["symphony"])
            self.assertIn(r["label"], ("firm", "close call", "could flip"))
        k = p["engines"]["KMLM"]
        self.assertEqual((k["status"], k["rule"], k["corridor"]), ("ok", "threshold", 0.1))
        # the tree's own target that day; Composer held a different set inside its 10pp corridor
        tree = sr.load_tree(man["KMLM"]["eras"][-1])
        prices = {t: self.fx["prices"][t] for t in sr.tree_tickers(tree)}
        _, target, _ = sr.run_engine(prices, tree, "2026-10-28")
        self.assertTrue(pc.same(k["target"], target))
        self.assertFalse(pc.same(k["target"], self.fx["expected"]["KMLM"]["2026-10-28"]))   # broken twin

    def test_one_engine_without_prices_does_not_stop_the_others(self):
        man = sr.load_manifest()
        trees = {e: sr.tree_tickers(sr.load_tree(c["eras"][-1])) for e, c in man.items()}
        own = {e: sorted(t - set().union(*(trees[o] for o in trees if o != e))) for e, t in trees.items()}
        victim = next(e for e in man if own[e])              # an engine that reads a ticker no other does
        gone = own[victim][0]
        real = self.fetch

        def fetch(t):
            if t == gone:
                raise RuntimeError("delisted")
            return real(t)
        self.fetch = fetch
        p = self.build()
        self.assertEqual(p["engines"][victim]["status"], "unavailable")
        self.assertIn(gone, p["engines"][victim]["note"])
        self.assertNotIn("target", p["engines"][victim])
        for eng in man:
            if eng != victim:
                self.assertEqual(p["engines"][eng]["status"], "ok", eng)


class B2NoDecision(Base):
    def assert_all_unavailable(self, p):
        self.assertEqual({r["status"] for r in p["engines"].values()}, {"unavailable"})
        self.assertTrue(all("target" not in r for r in p["engines"].values()))
        self.assertTrue(p["problems"])
        for r in p["engines"].values():                 # the rule and version still ride along
            self.assertIn(r["rule"], ("daily", "threshold"))
            self.assertTrue(r["version"])

    def test_outside_the_session(self):
        for now in (et(2026, 10, 28, 16, 5), et(2026, 10, 28, 9, 0), et(2026, 10, 31, 12, 0)):
            p = self.build(now)
            self.assert_all_unavailable(p)
        self.assertEqual(self.build()["engines"]["HG"]["status"], "ok")      # the twin: inside the session

    def test_yahoo_down(self):
        self.down = True
        p = self.build()
        self.assert_all_unavailable(p)
        self.assertIn("no prices", " ".join(p["problems"]).lower())

    def test_a_crash_in_the_preview_never_escapes(self):
        with unittest.mock.patch.object(pc, "preview", side_effect=RuntimeError("boom")):
            p = self.build()
        self.assert_all_unavailable(p)
        self.assertIn("boom", p["problems"][0])


class B3NoComposer(Base):
    def test_no_composer_state_in_the_payload(self):
        text = json.dumps(self.build())
        self.assertNotIn("Composer", text)
        self.assertNotIn("holdings", text)
        for r in self.build()["engines"].values():
            self.assertNotIn("live", r)
            self.assertNotIn("value", r)


class B6Prices(Base):
    def test_every_holdable_ticker_is_priced_on_the_evaluated_prices(self):
        p = self.build()
        man = sr.load_manifest()
        held = set()
        for cfg in man.values():
            for era in cfg["eras"]:                      # ANY era: a sleeve may still hold what a newer tree dropped
                held |= sr.tree_tickers(sr.load_tree(era))
        self.assertTrue(self.old)                        # the manifest does have tickers no current tree prices
        self.assertEqual(set(p["prices"]), held)
        for r in p["engines"].values():
            self.assertTrue(set(r["target"]) <= set(p["prices"]))
        for t, px in p["prices"].items():                # the frozen session's own last price
            src = self.fx["prices"].get(t) or self.extra[t]
            self.assertAlmostEqual(px, src["2026-10-28"], places=4, msg=t)
        self.assertEqual(p["price_notes"], {})
        self.assertEqual(set(p["price_times"]), set(p["prices"]))             # a time for every price
        self.assertEqual(set(p["price_times"].values()), {"2026-10-28T19:13:00Z"})   # the feed's last trade, 2 min old
        self.assertEqual(p["problems"], [])

    def test_an_era_only_ticker_without_a_price_is_said(self):
        gone = self.old[0]
        del self.extra[gone]                             # broken: Yahoo has nothing for it
        p = self.build()
        self.assertNotIn(gone, p["prices"])
        self.assertNotIn(gone, p["price_times"])
        self.assertTrue(any("no price for " + gone in x for x in p["problems"]), p["problems"])
        self.assertEqual({r["status"] for r in p["engines"].values()}, {"ok"})    # no current tree reads it

    def test_an_estimated_price_is_named(self):
        cap = {}
        real = pc.preview

        def spy(*a, **k):
            out = real(*a, **k)
            cap.update(k["capture"])
            k["capture"]["notes"]["BIL"] = "BIL 15:01 (no fresh sibling: last price used)"
            return out
        with unittest.mock.patch.object(pc, "preview", side_effect=spy):
            p = self.build()
        self.assertIn("last price used", p["price_notes"]["BIL"])
        self.assertEqual(set(p["price_notes"]), {"BIL"})

    def test_no_prices_without_a_session(self):
        p = self.build(et(2026, 10, 31, 12, 0))
        self.assertEqual((p["prices"], p["price_notes"]), ({}, {}))


class B7Clock(unittest.TestCase):
    def test_full_day_half_day_holiday_weekend(self):
        full = mb.session_info(datetime.datetime(2026, 11, 10, 15, 0, tzinfo=UTC))
        self.assertEqual((full["schema"], full["kind"]), (2, mb.SESSION_KIND))
        self.assertEqual((full["session"], full["decide_et"], full["decide_utc"], full["close_utc"], full["open_utc"]),
                         ("2026-11-10", "15:54", "2026-11-10T20:54:00Z", "2026-11-10T21:00:00Z", "2026-11-10T14:30:00Z"))
        self.assertNotIn("decide_bar_et", full)                                 # schema 1's name is gone
        half = mb.session_info(datetime.datetime(2026, 11, 27, 15, 0, tzinfo=UTC))
        self.assertEqual((half["close_et"], half["decide_et"], half["decide_utc"]), ("13:00", "12:54", "2026-11-27T17:54:00Z"))
        summer = mb.session_info(datetime.datetime(2026, 7, 15, 13, 0, tzinfo=UTC))
        self.assertEqual(summer["decide_utc"], "2026-07-15T19:54:00Z")          # EDT
        for shut in ((2026, 11, 26), (2026, 11, 14), (2026, 11, 15)):
            info = mb.session_info(datetime.datetime(*shut, 15, 0, tzinfo=UTC))
            self.assertIsNone(info["session"])
            self.assertNotIn("decide_utc", info)
            self.assertNotIn("reason", info)                                    # a weekend or a listed holiday needs none
        self.assertEqual(mb.parse_utc(full["decide_utc"]), datetime.datetime(2026, 11, 10, 20, 54, tzinfo=UTC))

    def test_decide_utc_is_the_instant_the_calibration_reads(self):
        """add. 50: the price 'at 15:54' is the close of the 1-minute bar ENDING 15:54:00 (the bar that starts
        15:53). decide_utc is that instant, not the end of the next bar"""
        s = mb.session_info(mb.parse_at("2026-11-09 12:00"))
        label = sr._hm(sr._min(s["close_et"]) - sr.DECISION_MINUTE)
        self.assertEqual((label, s["decide_et"]), ("15:54", "15:54"))
        bars = {"15:52": 1.0, "15:53": 2.0, "15:54": 3.0}                       # keyed by bar START, as FMP sends them
        self.assertEqual(sr.minute_price(bars, label), 2.0)                     # the shadow reads the bar starting 15:53
        tz = sr.et_now(mb.parse_utc(s["decide_utc"])).tzinfo
        self.assertEqual(pc.bar_end("2026-11-09", "15:53", tz), mb.parse_utc(s["decide_utc"]))    # ... which ends here
        self.assertNotEqual(pc.bar_end("2026-11-09", "15:54", tz), mb.parse_utc(s["decide_utc"]))  # broken: schema 1's bar
        close = mb.parse_utc(s["close_utc"])
        self.assertEqual(close - mb.parse_utc(s["decide_utc"]), datetime.timedelta(minutes=sr.DECISION_MINUTE))

    def test_a_year_past_the_calendar_tables_has_no_session_and_says_why(self):
        """S4: the tables end in 2027. 2028-01-17 is a holiday they do not list and 2028-11-24 closes at 13:00"""
        self.assertEqual(sr.calendar_through(), 2027)
        for when in (datetime.datetime(2028, 1, 17, 17, 0, tzinfo=UTC), datetime.datetime(2028, 11, 24, 15, 0, tzinfo=UTC)):
            info = mb.session_info(when)
            self.assertIsNone(info["session"])
            self.assertNotIn("decide_utc", info)
            self.assertIn("ends in 2027", info["reason"])
        last = mb.session_info(datetime.datetime(2027, 12, 31, 15, 0, tzinfo=UTC))   # the twin: the last covered year
        self.assertEqual((last["session"], last.get("reason")), ("2027-12-31", None))
        with unittest.mock.patch.dict(sr.HALF_DAYS, {"2028-11-24": "13:00"}):     # one table extended is not enough
            self.assertIsNone(mb.session_info(datetime.datetime(2028, 11, 24, 15, 0, tzinfo=UTC))["session"])
            with unittest.mock.patch.object(sr, "NYSE_HOLIDAYS", sr.NYSE_HOLIDAYS | {"2028-01-17"}):
                info = mb.session_info(datetime.datetime(2028, 11, 24, 15, 0, tzinfo=UTC))
                self.assertEqual((info["session"], info["close_et"], info["decide_utc"]), ("2028-11-24", "13:00", "2028-11-24T17:54:00Z"))
                self.assertIsNone(mb.session_info(datetime.datetime(2028, 1, 17, 17, 0, tzinfo=UTC))["session"])


class B4ParseAt(unittest.TestCase):
    def test_et_wall_time(self):
        self.assertEqual(mb.parse_at("2026-11-09 15:54"), datetime.datetime(2026, 11, 9, 20, 54, tzinfo=UTC))
        self.assertEqual(mb.parse_at("2026-11-09 15:54:30"), datetime.datetime(2026, 11, 9, 20, 54, 30, tzinfo=UTC))
        self.assertEqual(mb.rule_of({"corridor": 0.1}), ("threshold", 0.1))
        self.assertEqual(mb.rule_of({}), ("daily", None))


class B5Http(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.calls = []

        def builder():
            self.calls.append(self.t[0])
            if self.fail:
                raise RuntimeError("feed down")
            return {"schema": 1, "n": len(self.calls)}
        self.fail = False
        self.cache = mb.Cache(builder, clock=lambda: self.t[0])

    def serve(self, token):
        srv = mb.make_server(0, token, self.cache, window=lambda: False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def get(self, url, token=None):
        req = urllib.request.Request(url, headers={"X-API-Token": token} if token is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_auth_and_payload(self):
        base = self.serve("s3cret")
        code, body = self.get(base + "/health")
        self.assertEqual((code, body["service"], body["token_set"], body["payload_age_s"]), (200, "composer-brain", True, None))
        self.assertEqual(self.get(base + "/mirror/intents")[0], 401)
        self.assertEqual(self.get(base + "/mirror/intents", "wrong")[0], 401)
        self.assertEqual(self.calls, [])                                    # nothing computed for a stranger
        code, body = self.get(base + "/mirror/intents", "s3cret")
        self.assertEqual((code, body["n"], body["served_age_s"]), (200, 1, 0.0))
        self.assertEqual(self.get(base + "/nope", "s3cret")[0], 404)

    def test_disabled_without_a_token(self):
        base = self.serve("")
        self.assertEqual(self.get(base + "/mirror/intents", "")[0], 404)
        self.assertEqual(self.get(base + "/mirror/intents", "anything")[0], 404)
        self.assertEqual(self.get(base + "/health")[1]["token_set"], False)

    def test_cache_refreshes_when_stale_and_keeps_the_last_good_payload(self):
        p, age, err = self.cache.get(120)
        self.assertEqual((p["n"], age, err), (1, 0.0, None))
        self.t[0] += 60
        self.assertEqual(self.cache.get(120)[0]["n"], 1)                    # still fresh: not rebuilt
        self.t[0] += 61
        self.assertEqual(self.cache.get(120)[0]["n"], 2)                    # stale: rebuilt
        self.fail = True
        self.t[0] += 500
        p, age, err = self.cache.get(120)
        self.assertEqual(p["n"], 2)                                         # the last good one, with its age
        self.assertEqual(age, 500.0)
        self.assertIn("feed down", err)

    def test_session_clock_behind_the_token(self):
        srv = mb.make_server(0, "s3cret", self.cache, window=lambda: False,
                             clock_info=lambda: {"kind": mb.SESSION_KIND, "session": "2026-11-10"})
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertEqual(self.get(base + "/mirror/session")[0], 401)
        self.assertEqual(self.get(base + "/mirror/session", "s3cret"), (200, {"kind": mb.SESSION_KIND, "session": "2026-11-10"}))
        self.assertEqual(self.calls, [])                                    # the clock reads no prices
        off = self.serve("")
        self.assertEqual(self.get(off + "/mirror/session", "x")[0], 404)

    def test_after_is_validated_before_anything_is_computed(self):
        srv = mb.make_server(0, "t", self.cache, window=lambda: True,
                             wall=lambda: datetime.datetime(2026, 11, 10, 20, 59, tzinfo=UTC))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertEqual(self.get(base + "/mirror/intents?after=yesterday", "t")[0], 400)
        self.assertEqual(self.get(base + "/mirror/intents?after=2999-01-01T00:00:00Z", "t")[0], 409)
        self.assertEqual(self.get(base + "/mirror/intents?after=2026-11-10T20:59:06Z", "t")[0], 409)    # > 5 s ahead
        code, body = self.get(base + "/mirror/intents?after=2026-11-10T20:54:30Z", "t")                # no bar ends there
        self.assertEqual(code, 400)
        self.assertIn("1-minute bar", body["error"])
        self.assertEqual(self.get(base + "/mirror/intents?after=2026-11-10T20:54:00Z", "t")[0], 503)    # no pinned path here
        self.assertEqual(self.calls, [])                                    # the ad hoc builder never stands in for it
        self.assertEqual(self.get(base + "/mirror/intents?after=2026-11-10T20:54:00Z")[0], 401)

    def test_overlapping_requests_share_one_build(self):
        """S3: a request that arrives while a build runs waits for it and then USES it (the reviewer's B5e:
        refresh() built again without looking)"""
        n, gate = [0], threading.Event()

        def builder():
            n[0] += 1
            gate.wait(5)
            return {"n": n[0]}
        cache = mb.Cache(builder)
        got = []
        ts = [threading.Thread(target=lambda: got.append(cache.get(60)[0]["n"])) for _ in range(4)]
        for t in ts:
            t.start()
        import time
        time.sleep(0.2)                                                     # all four are waiting on the first build
        gate.set()
        for t in ts:
            t.join(5)
        self.assertEqual((n[0], got), (1, [1, 1, 1, 1]))
        cache.refresh()                                                     # the twin: an explicit refresh does rebuild
        self.assertEqual(n[0], 2)

    def test_no_payload_yet_is_a_503(self):
        self.fail = True
        base = self.serve("t")
        code, body = self.get(base + "/mirror/intents", "t")
        self.assertEqual(code, 503)
        self.assertIn("feed down", body["error"])


if __name__ == "__main__":
    unittest.main()
