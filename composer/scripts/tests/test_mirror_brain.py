"""Gate tests for mirror_brain.py (the Composer mirror's keyless decision brain; IBKR_MIRROR.md).

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
      token, 200 with the payload on the right one, 503 before any payload; the cache recomputes when
      stale, single flight, and keeps the last good payload when a rebuild fails
  B6  the reference prices: every ticker a sleeve can hold is priced at the prices the engines were
      evaluated on; a price rebuilt or carried is named in price_notes; none without a session
  B7  the executor's clock: the decision bar's end and the close on a full day, a half-day, a holiday
      and a weekend, across DST; /mirror/session behind the same token
  B8  ?after=: a payload computed before the asked instant is never served (the cache recomputes), a
      malformed or future instant is refused

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


class Base(PreviewBase):
    def build(self, now=None):
        return mb.build(now or self.now, quotes=self.quotes, fetch=self.fetch)


class B1Payload(Base):
    def test_targets_rules_versions(self):
        p = self.build()
        self.assertEqual((p["schema"], p["kind"], p["session"], p["close_et"]), (1, mb.KIND, "2026-10-28", "16:00"))
        self.assertTrue(p["replay"])
        self.assertEqual(p["problems"], [])
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
            held |= sr.tree_tickers(sr.load_tree(cfg["eras"][-1]))
        self.assertEqual(set(p["prices"]), held)
        for r in p["engines"].values():
            self.assertTrue(set(r["target"]) <= set(p["prices"]))
        for t, px in p["prices"].items():                # the frozen session's own last price
            self.assertAlmostEqual(px, self.fx["prices"][t]["2026-10-28"], places=4, msg=t)
        self.assertEqual(p["price_notes"], {})

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
        self.assertEqual((full["session"], full["decide_bar_et"], full["decide_utc"], full["close_utc"], full["open_utc"]),
                         ("2026-11-10", "15:54", "2026-11-10T20:55:00Z", "2026-11-10T21:00:00Z", "2026-11-10T14:30:00Z"))
        half = mb.session_info(datetime.datetime(2026, 11, 27, 15, 0, tzinfo=UTC))
        self.assertEqual((half["close_et"], half["decide_bar_et"], half["decide_utc"]), ("13:00", "12:54", "2026-11-27T17:55:00Z"))
        summer = mb.session_info(datetime.datetime(2026, 7, 15, 13, 0, tzinfo=UTC))
        self.assertEqual(summer["decide_utc"], "2026-07-15T19:55:00Z")          # EDT
        for shut in ((2026, 11, 26), (2026, 11, 14), (2026, 11, 15)):
            info = mb.session_info(datetime.datetime(*shut, 15, 0, tzinfo=UTC))
            self.assertIsNone(info["session"])
            self.assertNotIn("decide_utc", info)
        self.assertEqual(full["kind"], mb.SESSION_KIND)
        self.assertEqual(mb.parse_utc(full["decide_utc"]), datetime.datetime(2026, 11, 10, 20, 55, tzinfo=UTC))


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

    def test_after_never_serves_an_older_payload(self):
        stamps = ["2026-11-10T20:54:40Z", "2026-11-10T20:55:06Z", "2026-11-10T20:55:06Z"]
        calls = []

        def builder():
            calls.append(1)
            return {"schema": 1, "asof_utc": stamps[len(calls) - 1]}
        cache = mb.Cache(builder, clock=lambda: self.t[0])
        srv = mb.make_server(0, "t", cache, window=lambda: True,
                             wall=lambda: datetime.datetime(2026, 11, 10, 20, 59, tzinfo=UTC))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertEqual(self.get(base + "/mirror/intents", "t")[1]["asof_utc"], stamps[0])
        code, body = self.get(base + "/mirror/intents?after=2026-11-10T20:55:00Z", "t")
        self.assertEqual((code, body["asof_utc"], len(calls)), (200, stamps[1], 2))       # fresh by age, rebuilt anyway
        self.assertEqual(self.get(base + "/mirror/intents?after=2026-11-10T20:55:00Z", "t")[1]["asof_utc"], stamps[1])
        self.assertEqual(len(calls), 2)                                     # the twin: already new enough, reused
        self.assertEqual(self.get(base + "/mirror/intents?after=yesterday", "t")[0], 400)
        self.assertEqual(self.get(base + "/mirror/intents?after=2999-01-01T00:00:00Z", "t")[0], 409)
        # a rebuild that cannot reach the instant is a 503, never the older payload
        code, body = self.get(base + "/mirror/intents?after=2026-11-10T20:58:00Z", "t")
        self.assertEqual(code, 503)

    def test_no_payload_yet_is_a_503(self):
        self.fail = True
        base = self.serve("t")
        code, body = self.get(base + "/mirror/intents", "t")
        self.assertEqual(code, 503)
        self.assertIn("feed down", body["error"])


if __name__ == "__main__":
    unittest.main()
