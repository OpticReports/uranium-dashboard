"""Merge-blocking gate tests for gate_watch.py (HG's SPY 200-day gate watch, results.md
addendum 46).

House rule: a gate that cannot fail is not a gate. Each behavioural test is paired with a
BROKEN-INPUT counterpart (the same distance path shifted, a day dropped, the wrong weekday, the
wrong holding) that must land on the other side. The I/O hook is exercised with composerlib
mocked in the real wire formats (both tdvm_weights orientations) and with each fetch failing.

  T1  zones and hysteresis (near re-arms > 4%, tight > 2.5%, equality with the line = closed)
  T2  APPROACH fires once per approach; shifted path (+2%) fires nothing
  T3  IMMINENT from near, and directly from far without a separate APPROACH
  T4  CLOSED / weekly STILL CLOSED (Mondays only) / REOPENED with the day count; a path that
      never touches the line never closes; no APPROACH/IMMINENT on the reopen day
  T5  OVERRIDE start/end only when live HG holds BIL where the pre-gate logic holds a trend
      basket; a dip-buy or unknown pre-gate holding is not an override
  T6  APPROACH ENDED needs > 4%, not 3.5%
  T7  report text: base rates by band, HG context per branch
  T8  first run initialises silently (note, no alert)
  T9  check_gate: SPY fetch failure -> note, no alert, state untouched; pre-gate model failure
      -> assessment still runs with ungated=None
  T10 wire parsing: live holding = max allocation; ungated holding from both tdvm orientations

Run: python3 -m unittest composer.scripts.tests.test_gate_watch -v
"""
import datetime
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import gate_watch as gw  # noqa: E402

MON, TUE = 0, 1


def run_path(dists, hg="SSO", ug="SSO", weekdays=None, state=None):
    """feed a distance path through assess(); returns (list of alert prefixes per day, state)"""
    state = {} if state is None else state
    out = []
    for i, d in enumerate(dists):
        wd = weekdays[i] if weekdays else TUE
        alerts, _, state = gw.assess(f"2026-11-{i + 1:02d}", d, None, None, hg, ug, state, wd)
        out.append([a.split(" — ")[0] for a in alerts])
    return out, state


class T1Zones(unittest.TestCase):
    def test_thresholds_and_hysteresis(self):
        self.assertEqual(gw.zone_of(0.05, None), "far")
        self.assertEqual(gw.zone_of(0.03, "far"), "near")          # 3.0% is near
        self.assertEqual(gw.zone_of(0.031, "far"), "far")
        self.assertEqual(gw.zone_of(0.039, "near"), "near")        # stays near until > 4%
        self.assertEqual(gw.zone_of(0.041, "near"), "far")
        self.assertEqual(gw.zone_of(0.015, "near"), "tight")
        self.assertEqual(gw.zone_of(0.024, "tight"), "tight")      # stays tight until > 2.5%
        self.assertEqual(gw.zone_of(0.026, "tight"), "near")
        self.assertEqual(gw.zone_of(0.041, "tight"), "far")
        self.assertEqual(gw.zone_of(0.0, "far"), "closed")         # Composer's 'gt': equality = cash
        self.assertEqual(gw.zone_of(-0.001, "tight"), "closed")

    def test_broken_sign(self):
        self.assertNotEqual(gw.zone_of(0.0001, "far"), "closed")


class T2Approach(unittest.TestCase):
    PATH = [0.05, 0.035, 0.029, 0.032, 0.039, 0.028, 0.036]

    def test_fires_once(self):
        out, st = run_path(self.PATH)
        self.assertEqual([a for day in out for a in day], ["GATE APPROACH"])
        self.assertEqual(out[2], ["GATE APPROACH"])
        self.assertEqual(st["zone"], "near")

    def test_broken_shifted_path_is_silent(self):
        out, _ = run_path([d + 0.02 for d in self.PATH])
        self.assertEqual([a for day in out for a in day], [])

    def test_rearm_after_leaving(self):
        out, _ = run_path([0.05, 0.029, 0.045, 0.029])
        self.assertEqual([a for day in out for a in day], ["GATE APPROACH", "GATE APPROACH ENDED", "GATE APPROACH"])


class T3Imminent(unittest.TestCase):
    def test_from_near(self):
        out, _ = run_path([0.05, 0.025, 0.014, 0.02, 0.014])
        self.assertEqual([a for day in out for a in day], ["GATE APPROACH", "GATE IMMINENT"])

    def test_direct_from_far(self):
        out, _ = run_path([0.05, 0.012])
        self.assertEqual(out[1], ["GATE IMMINENT"])

    def test_broken_not_quite(self):
        out, _ = run_path([0.05, 0.025, 0.016])
        self.assertEqual([a for day in out for a in day], ["GATE APPROACH"])


class T4CrossAndReopen(unittest.TestCase):
    def test_close_weekly_reopen(self):
        path = [0.02, 0.005, -0.004, -0.01, -0.02, -0.003, 0.004, 0.02]
        wk = [TUE, TUE, TUE, MON, TUE, MON, TUE, TUE]
        out, st = run_path(path, weekdays=wk)
        self.assertEqual(out[2], ["GATE CLOSED"])
        self.assertEqual(out[3], ["GATE STILL CLOSED"])                 # Monday while closed
        self.assertEqual(out[4], [])                                    # Tuesday: silent
        self.assertEqual(out[5], ["GATE STILL CLOSED"])
        self.assertEqual(out[6], ["GATE REOPENED"])                     # no APPROACH/IMMINENT on the same day
        self.assertIn("after 4 session(s) below", gw.assess("x", 0.004, None, None, "SSO", "SSO",
                                                           {"zone": "closed", "closed_days": 4}, TUE)[0][0])
        self.assertEqual(out[7], [])
        self.assertEqual(st["closed_days"], 0)
        self.assertIsNone(st["closed_since"])

    def test_broken_never_touches(self):
        out, _ = run_path([0.02, 0.005, 0.0004, 0.001, 0.02], weekdays=[TUE, TUE, MON, MON, TUE])
        self.assertNotIn("GATE CLOSED", [a for day in out for a in day])
        self.assertNotIn("GATE STILL CLOSED", [a for day in out for a in day])

    def test_broken_weekday(self):
        out, _ = run_path([0.005, -0.01, -0.01], weekdays=[TUE, TUE, TUE])
        self.assertEqual(out[2], [])


class T5Override(unittest.TestCase):
    def test_start_and_end(self):
        st = {"zone": "closed", "closed_days": 2, "override": False}
        a, _, st = gw.assess("d1", -0.01, None, None, "BIL", "TQQQ", st, TUE)
        self.assertEqual([x.split(" — ")[0] for x in a], ["GATE OVERRIDE START"])
        self.assertTrue(st["override"])
        a, _, st = gw.assess("d2", -0.01, None, None, "BIL", "TQQQ", st, TUE)
        self.assertEqual(a, [])
        a, _, st = gw.assess("d3", -0.01, None, None, "BIL", "BIL", st, TUE)
        self.assertEqual([x.split(" — ")[0] for x in a], ["GATE OVERRIDE END"])
        self.assertFalse(st["override"])

    def test_broken_not_an_override(self):
        for hg, ug in (("BIL", "QLD"), ("BIL", None), ("USD", "TQQQ"), ("TQQQ", "TQQQ")):
            a, _, st = gw.assess("d", -0.01, None, None, hg, ug, {"zone": "closed", "closed_days": 1}, TUE)
            self.assertFalse(st["override"], (hg, ug))
            self.assertNotIn("GATE OVERRIDE START", [x.split(" — ")[0] for x in a], (hg, ug))


class T6ApproachEnded(unittest.TestCase):
    def test_needs_four_percent(self):
        out, _ = run_path([0.05, 0.029, 0.035, 0.041])
        self.assertEqual([a for day in out for a in day], ["GATE APPROACH", "GATE APPROACH ENDED"])
        self.assertEqual(out[2], [])


class T7Text(unittest.TestCase):
    def test_base_rates(self):
        self.assertEqual(gw.base_rate(0.057), (0.03, 0.09))
        self.assertEqual(gw.base_rate(0.012), (0.62, 0.69))
        self.assertEqual(gw.base_rate(-0.01), (0.78, 0.85))
        self.assertEqual(gw.base_rate(-0.04), (0.26, 0.47))
        self.assertIsNone(gw.base_rate(0.2))

    def test_hg_context(self):
        self.assertIn("trend branch", gw.hg_context("TQQQ", "TQQQ", True))
        self.assertIn("overriding", gw.hg_context("BIL", "UDOW", False))
        self.assertIn("dip-buy", gw.hg_context("USD", "USD", True))
        self.assertIn("long-vol", gw.hg_context("UVXY", "UVXY", True))
        self.assertIn("own rules", gw.hg_context("BIL", "BIL", True))

    def test_describe(self):
        s = gw.describe("2026-10-16", 0.0573, 0.082, 0.013, "USD", "USD", True)
        self.assertIn("5.7% above", s)
        self.assertIn("fall of 5.4%", s)
        self.assertIn("3% / 9%", s)
        self.assertIn("rising 1.3%", s)
        s2 = gw.describe("d", -0.02, None, None, "BIL", "TQQQ", False)
        self.assertIn("2.0% below", s2)
        self.assertIn("rise of 2.0%", s2)
        self.assertIn("46% / 66%", s2)


class T8FirstRun(unittest.TestCase):
    def test_silent_init(self):
        for d in (0.05, 0.01, -0.02):
            a, notes, st = gw.assess("d", d, None, None, "SSO", "SSO", {}, MON)
            self.assertEqual(a, [], d)
            self.assertEqual(len(notes), 1)
            self.assertEqual(st["zone"], gw.zone_of(d, None))


class _Fail(Exception):
    pass


class T9Hook(unittest.TestCase):
    META = [{"id": gw.HG, "last_rebalance_on": "2026-10-16", "holdings": [{"ticker": "USD", "allocation": 0.999}, {"ticker": "BIL", "allocation": 0.001}]}]

    def setUp(self):
        self.orig = (gw.spy_distance, gw.ungated_holding)
        self.now = datetime.datetime(2026, 10, 20, 21, 35, tzinfo=datetime.timezone.utc)

    def tearDown(self):
        gw.spy_distance, gw.ungated_holding = self.orig

    def test_spy_failure_is_a_note(self):
        gw.spy_distance = lambda today: (_ for _ in ()).throw(_Fail("down"))
        state, alerts, snap = {"gate": {"zone": "near", "last_dist": 0.02}}, [], {}
        gw.check_gate(state, alerts, snap, self.META, self.now)
        self.assertEqual(alerts, [])
        self.assertEqual(state["gate"], {"zone": "near", "last_dist": 0.02})
        self.assertNotIn("gate", snap)

    def test_pregate_failure_still_assesses(self):
        gw.spy_distance = lambda today: ("2026-10-20", 0.012, 0.03, 0.01)
        gw.ungated_holding = lambda today: (_ for _ in ()).throw(_Fail("down"))
        state, alerts, snap = {"gate": {"zone": "far"}}, [], {}
        gw.check_gate(state, alerts, snap, self.META, self.now)
        self.assertEqual([a.split(" — ")[0] for a in alerts], ["GATE IMMINENT"])
        self.assertEqual(snap["gate"]["ungated_holding"], None)
        self.assertEqual(snap["gate"]["hg_holding"], "USD")

    def test_quiet_day_no_alert(self):
        gw.spy_distance = lambda today: ("2026-10-20", 0.057, 0.08, 0.013)
        gw.ungated_holding = lambda today: ("2026-10-20", "USD")
        state, alerts, snap = {"gate": {"zone": "far"}}, [], {}
        gw.check_gate(state, alerts, snap, self.META, self.now)
        self.assertEqual(alerts, [])
        self.assertEqual(snap["gate"]["zone"], "far")


class T10Wire(unittest.TestCase):
    def test_live_holding(self):
        self.assertEqual(gw.live_holding(T9Hook.META), ("2026-10-16", "USD"))
        self.assertEqual(gw.live_holding([{"id": "other", "holdings": []}]), (None, None))

    def test_ungated_both_orientations(self):
        import composerlib as cl
        orig = cl.backtest_tree
        day = (datetime.date(2026, 10, 16) - datetime.date(1970, 1, 1)).days
        try:
            cl.backtest_tree = lambda tree, **kw: {"tdvm_weights": {"UDOW": {str(day - 1): 1.0, str(day): 0.0}, "USD": {str(day - 1): 0.0, str(day): 1.0}}}
            self.assertEqual(gw.ungated_holding(datetime.date(2026, 10, 18)), ("2026-10-16", "USD"))
            cl.backtest_tree = lambda tree, **kw: {"tdvm_weights": {str(day - 1): {"UDOW": 1.0}, str(day): {"TQQQ": 1.0}}}
            self.assertEqual(gw.ungated_holding(datetime.date(2026, 10, 18)), ("2026-10-16", "TQQQ"))
        finally:
            cl.backtest_tree = orig


class T11Review(unittest.TestCase):
    """counter-agent round (2026-10-18): surviving mutants and the three behavioural fixes"""

    def test_monday_close_day_emits_closed_only(self):
        out, _ = run_path([0.02, -0.01], weekdays=[TUE, MON])
        self.assertEqual(out[1], ["GATE CLOSED"])

    def test_tight_rearm_to_near_is_silent_then_far_ends(self):
        out, _ = run_path([0.05, 0.012, 0.026, 0.02, 0.045])
        self.assertEqual(out, [[], ["GATE IMMINENT"], [], [], ["GATE APPROACH ENDED"]])

    def test_closed_days_and_closed_since_from_a_path(self):
        dists = [0.01, -0.01, -0.02, -0.01, 0.01]
        state, texts = {}, []
        for i, d in enumerate(dists):
            a, _, state = gw.assess(f"2026-11-{i + 1:02d}", d, None, None, "SSO", "SSO", state, TUE)
            texts.append(a)
            if i == 1:
                self.assertEqual(state["closed_since"], "2026-11-02")
            if i in (1, 2, 3):
                self.assertEqual(state["closed_days"], i)
        self.assertIn("after 3 session(s) below", texts[4][0])

    def test_base_rate_edges_and_rise(self):
        self.assertEqual(gw.base_rate(0.015), (0.62, 0.69))
        self.assertEqual(gw.base_rate(0.03), (0.28, 0.41))
        self.assertEqual(gw.base_rate(-0.015), (0.78, 0.85))
        self.assertIn("rise of 11.1%", gw.describe("d", -0.10, None, None, "BIL", "BIL", False))
        self.assertIn("moves to BIL", gw.hg_context("TQQQ", "TQQQ", False))

    def test_override_missing_data_keeps_state(self):
        st = {"zone": "closed", "closed_days": 3, "override": True, "override_since": "d0"}
        for hg, ug in ((None, "TQQQ"), ("BIL", None), (None, None)):
            a, _, st = gw.assess("d1", -0.01, None, None, hg, ug, dict(st), TUE)
            self.assertTrue(st["override"], (hg, ug))
            self.assertEqual(a, [], (hg, ug))
        a, _, st2 = gw.assess("d2", -0.01, None, None, "BIL", "BIL", dict(st), TUE)   # real end still reported
        self.assertEqual([x.split(" — ")[0] for x in a], ["GATE OVERRIDE END"])

    def test_spy_distance_window_includes_today(self):
        import composerlib as cl
        orig = cl.backtest_tree
        d0 = (datetime.date(2025, 10, 1) - datetime.date(1970, 1, 1)).days
        vals = [100.0 + i for i in range(230)]
        try:
            cl.backtest_tree = lambda tree, **kw: {"dvm_capital": {"x": {str(d0 + i): v for i, v in enumerate(vals)}}}
            date, dist, dist5, slope20 = gw.spy_distance(datetime.date(2026, 10, 20))
        finally:
            cl.backtest_tree = orig
        L = len(vals) - 1
        sma = lambda i: sum(vals[i - 199:i + 1]) / 200  # noqa: E731
        self.assertAlmostEqual(dist, vals[L] / sma(L) - 1, places=12)
        self.assertAlmostEqual(dist5, vals[L - 5] / sma(L - 5) - 1, places=12)
        self.assertAlmostEqual(slope20, sma(L) / sma(L - 20) - 1, places=12)
        self.assertNotAlmostEqual(dist, vals[L] / (sum(vals[L - 200:L]) / 200) - 1, places=6)  # window ending yesterday
        self.assertEqual(date, (datetime.date(1970, 1, 1) + datetime.timedelta(days=d0 + L)).isoformat())

    def test_duplicate_session_is_skipped(self):
        orig = gw.spy_distance
        gw.spy_distance = lambda today: ("2026-10-20", -0.01, 0.0, 0.0)
        try:
            state = {"gate": {"zone": "closed", "closed_days": 2, "last_date": "2026-10-20", "last_dist": -0.01, "override": False}}
            before = json.dumps(state, sort_keys=True)
            alerts, snap = [], {}
            gw.check_gate(state, alerts, snap, T9Hook.META, datetime.datetime(2026, 10, 21, 21, 35, tzinfo=datetime.timezone.utc))
            self.assertEqual(alerts, [])
            hist = state["gate"].pop("live_hist")                         # the live holding is still recorded
            self.assertEqual(hist, {"2026-10-16": "USD"})
            self.assertEqual(json.dumps(state, sort_keys=True), before)   # the assessment state is untouched
            self.assertTrue(snap["gate"]["stale"])
        finally:
            gw.spy_distance = orig

    def test_override_compares_like_dates(self):
        """the pre-gate model lags a session: its date is matched to live HG's holding of THAT date, recorded by
        decision date (last_rebalance_attempted_on), never to today's holding; last_rebalance_on only moves on trades"""
        orig = (gw.spy_distance, gw.ungated_holding)
        gw.spy_distance = lambda today: ("2026-10-16", -0.01, 0.0, 0.0)
        gw.ungated_holding = lambda today: ("2026-10-16", "TQQQ")
        now = datetime.datetime(2026, 10, 19, 21, 35, tzinfo=datetime.timezone.utc)
        meta = [{"id": gw.HG, "last_rebalance_on": "2026-10-09", "last_rebalance_attempted_on": "2026-10-19",
                 "holdings": [{"ticker": "BIL", "allocation": 1.0}]}]
        try:
            # no live record for the model's date: unknown, state kept, the gap is reported
            state, alerts, snap = {"gate": {"zone": "closed", "closed_days": 1, "override": False, "last_date": "2026-10-15"}}, [], {}
            gw.check_gate(state, alerts, snap, meta, now)
            self.assertNotIn("GATE OVERRIDE START", [a.split(" — ")[0] for a in alerts])
            self.assertFalse(state["gate"]["override"])
            self.assertEqual(state["gate"]["live_hist"], {"2026-10-19": "BIL"})       # recorded by decision date
            # live record for the model's date: BIL where the pre-gate logic holds TQQQ -> START
            state, alerts, snap = {"gate": {"zone": "closed", "closed_days": 1, "override": False, "last_date": "2026-10-15",
                                            "live_hist": {"2026-10-16": "BIL"}}}, [], {}
            gw.check_gate(state, alerts, snap, meta, now)
            self.assertIn("GATE OVERRIDE START", [a.split(" — ")[0] for a in alerts])
            # broken: same model date, but live HG that day held TQQQ (no override) -> nothing
            state, alerts, snap = {"gate": {"zone": "closed", "closed_days": 1, "override": False, "last_date": "2026-10-15",
                                            "live_hist": {"2026-10-16": "TQQQ"}}}, [], {}
            gw.check_gate(state, alerts, snap, meta, now)
            self.assertNotIn("GATE OVERRIDE START", [a.split(" — ")[0] for a in alerts])
        finally:
            gw.spy_distance, gw.ungated_holding = orig

    def test_override_persists_while_hg_does_not_trade_and_ends(self):
        """a real override: HG sits in BIL for days without trading; the check must keep running and end it"""
        orig = (gw.spy_distance, gw.ungated_holding)
        try:
            state = {"gate": {"zone": "closed", "closed_days": 3, "override": True, "override_since": "2026-11-02",
                              "last_date": "2026-11-04", "live_hist": {"2026-11-04": "BIL"}}}
            for day, model_hold, live_hold, expect in (("2026-11-05", "UPRO", "BIL", []), ("2026-11-06", "BIL", "BIL", ["GATE OVERRIDE END"])):
                gw.spy_distance = lambda today, d=day: (d, -0.01, 0.0, 0.0)
                gw.ungated_holding = lambda today, d=day, m=model_hold: (d, m)
                state["gate"]["live_hist"][day] = live_hold                       # yesterday's run recorded it
                meta = [{"id": gw.HG, "last_rebalance_on": "2026-11-02", "last_rebalance_attempted_on": day,
                         "holdings": [{"ticker": live_hold, "allocation": 1.0}]}]
                alerts, snap = [], {}
                gw.check_gate(state, alerts, snap, meta, datetime.datetime(2026, 11, int(day[-2:]), 21, 35, tzinfo=datetime.timezone.utc))
                self.assertEqual([a.split(" — ")[0] for a in alerts if "OVERRIDE" in a], expect, day)
            self.assertFalse(state["gate"]["override"])
        finally:
            gw.spy_distance, gw.ungated_holding = orig

    def test_live_hist_is_pruned(self):
        orig = (gw.spy_distance, gw.ungated_holding)
        gw.spy_distance = lambda today: ("2026-10-30", 0.05, 0.05, 0.01)
        gw.ungated_holding = lambda today: ("2026-10-30", "BIL")
        try:
            state = {"gate": {"zone": "far", "last_date": "2026-10-29", "live_hist": {f"2026-10-{d:02d}": "BIL" for d in range(1, 15)}}}
            meta = [{"id": gw.HG, "last_rebalance_attempted_on": "2026-10-30", "holdings": [{"ticker": "BIL", "allocation": 1.0}]}]
            gw.check_gate(state, [], {}, meta, datetime.datetime(2026, 10, 30, 21, 35, tzinfo=datetime.timezone.utc))
            self.assertEqual(len(state["gate"]["live_hist"]), 10)
            self.assertIn("2026-10-30", state["gate"]["live_hist"])
        finally:
            gw.spy_distance, gw.ungated_holding = orig

    def test_systemexit_from_composerlib_is_contained(self):
        orig = gw.spy_distance
        gw.spy_distance = lambda today: (_ for _ in ()).throw(SystemExit("error: HTTP 500"))
        try:
            state, alerts, snap = {"gate": {"zone": "far"}}, [], {}
            gw.check_gate(state, alerts, snap, T9Hook.META, datetime.datetime(2026, 10, 21, 21, 35, tzinfo=datetime.timezone.utc))
            self.assertEqual(alerts, [])
            self.assertEqual(state["gate"], {"zone": "far"})
        finally:
            gw.spy_distance = orig


if __name__ == "__main__":
    unittest.main()
