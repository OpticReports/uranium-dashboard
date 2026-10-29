"""Merge-blocking gate tests for shadow_runner.py (the shadow decision runner, results.md
addendum 48).

House rule: a gate that cannot fail is not a gate. Each behavioural test is paired with a
BROKEN-INPUT counterpart that must land on the other side.

  S1  indicators: Wilder RSI with bounded warm-up (60..250 closes) against a from-scratch
      reference, and Cutler RSI differs; percent units for CR; population SD; MA window
  S2  windows: <side>-fn-params.window, <side>-window-days, default 10; a 14-day node is not 10
  S3  tree semantics: if/else order, wt-cash-specified {num, den}, filter top/bottom over assets
      and over groups (sub-tree track record); Unsupported and DataGap fail loudly
  S4  fidelity: the four approved trees on frozen prices reproduce Composer's own backtest
      decisions on 40/40 sessions each; shifting the answer key a day, or Cutler RSI, breaks it
  S5  classification: 3% half-L1 boundary (daily engines) and 10pp + 1pp corridor (KMLM);
      knife-edge within 0.5 sigma, mismatch beyond
  S6  assess(): agree is silent; mismatch alerts; knife-edge alerts only on the 2nd session in a
      row (an agree resets it); no-rebalance start / still / resumed; unavailable is a note
  S7  check_shadow(): Yahoo failure -> note, state untouched; composerlib SystemExit in the drift
      check -> note, the day's alerts still delivered; the same session twice -> not re-assessed
  S8  logic drift: approved head silent; rename (same logic) a note; changed logic alerts once,
      again on Mondays; canonical() ignores ids, names and window-field style, sees thresholds
  S9  approved registry: eras ordered, files load, every tree passes validate(); the HG eras equal
      the gate-watch fixtures; an EMA node fails validate()
  S10 ledger upsert by (date, engine), record counts; live_weights; final_through at 16:15 ET in
      summer and winter time; era_for / eras_between

Run: python3 -m unittest composer.scripts.tests.test_shadow_runner -v
"""
import contextlib
import copy
import datetime
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import shadow_runner as sr  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "shadow-2026-10-28.json")
UTC = datetime.timezone.utc


# ------------------------------------------------------------------ helpers
def dates(n, start=datetime.date(2025, 1, 1)):
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range(n)]


def path(n, drift=0.0, amp=0.01, seed=7):
    """deterministic noisy price path (LCG noise, uniform in +-amp)"""
    v, x, out = 100.0, seed, []
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        v *= 1 + drift + amp * (2 * x / 2 ** 31 - 1)
        out.append(v)
    return out


def px(n, **series):
    ds = dates(n)
    return {t: dict(zip(ds, s)) for t, s in series.items()}


def asset(t):
    return {"step": "asset", "ticker": t, "id": f"a-{t}"}


def cond(fn, t, w, op, rhs, rhs_fn=None, rhs_w=None):
    n = {"step": "if-child", "id": f"c-{t}-{op}-{rhs}", "lhs-fn": fn, "lhs-val": t, "lhs-fn-params": {"window": w},
         "comparator": op, "is-else-condition?": False}
    if rhs_fn:
        n.update({"rhs-fn": rhs_fn, "rhs-val": rhs, "rhs-fn-params": {"window": rhs_w}, "rhs-fixed-value?": False})
    else:
        n.update({"rhs-val": str(rhs), "rhs-fixed-value?": True})
    return n


def if_(c, yes, no):
    c = dict(c, children=yes)
    return {"step": "if", "id": f"if-{c['id']}", "children": [c, {"step": "if-child", "id": f"else-{c['id']}",
                                                                 "is-else-condition?": True, "children": no}]}


def root(*kids, **kw):
    return dict({"step": "root", "id": "root", "children": [{"step": "wt-cash-equal", "id": "eq", "children": list(kids)}]}, **kw)


def rsi_tree(t="X", w=2, thr=50):
    return root(if_(cond("relative-strength-index", t, w, "gt", thr), [asset("A")], [asset("B")]))


def last_for_rsi(s, w, target):
    """the last close that puts RSI(w) of s exactly at target (bisection; RSI rises with the close)"""
    lo, hi = s[-2] * 0.8, s[-2] * 1.2
    for _ in range(200):
        mid = (lo + hi) / 2
        v = sr.indicator("relative-strength-index", s[:-1] + [mid], w)
        lo, hi = (mid, hi) if v < target else (lo, mid)
    return (lo + hi) / 2


def near_threshold_prices(n=120, bump=0.0003):
    """X whose RSI(2) on the last day sits just above 50 (bump = relative distance of the close)"""
    s = path(n, amp=0.01)
    s[-1] = last_for_rsi(s, 2, 50.0) * (1 + bump)
    return px(n, X=s, A=path(n, seed=3), B=path(n, seed=5), SPY=path(n, seed=11))


def wilder_ref(s, w):
    d = [s[i] - s[i - 1] for i in range(1, len(s))]
    ag = sum(max(x, 0) for x in d[:w]) / w
    al = sum(max(-x, 0) for x in d[:w]) / w
    for x in d[w:]:
        ag = (ag * (w - 1) + max(x, 0)) / w
        al = (al * (w - 1) + max(-x, 0)) / w
    return 100 - 100 / (1 + ag / al)


def cutler(s, w):
    d = [s[i] - s[i - 1] for i in range(len(s) - w, len(s))]
    ag = sum(max(x, 0) for x in d) / w
    al = sum(max(-x, 0) for x in d) / w
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


# ------------------------------------------------------------------ S1
class S1Indicators(unittest.TestCase):
    def test_wilder_bounded_warmup_matches_reference(self):
        s = path(300)
        for w in (2, 10, 14):
            self.assertAlmostEqual(sr.indicator("relative-strength-index", s, w), wilder_ref(s[-251:], w), places=9)

    def test_broken_cutler_differs(self):
        s = path(300)
        self.assertGreater(abs(sr.indicator("relative-strength-index", s, 10) - cutler(s, 10)), 0.5)

    def test_rsi_needs_60_changes(self):
        s = path(61)
        self.assertIsNotNone(sr.indicator("relative-strength-index", s, 10))
        self.assertIsNone(sr.indicator("relative-strength-index", s[1:], 10))     # broken: 59 changes

    def test_ma_window(self):
        self.assertEqual(sr.indicator("moving-average-price", [1, 2, 3, 4], 3), 3.0)
        self.assertEqual(sr.indicator("moving-average-price", [1, 2, 3, 4], 4), 2.5)
        self.assertIsNone(sr.indicator("moving-average-price", [1, 2, 3], 4))

    def test_cumulative_return_in_percent(self):
        v = sr.indicator("cumulative-return", [100.0, 101.76], 1)
        self.assertAlmostEqual(v, 1.76, places=9)
        self.assertTrue(v > 1.75)                     # Composer's 'CR(HYG,1) > 1.75' means 1.75%
        self.assertFalse(v / 100 > 1.75)              # broken: a fraction never trips it

    def test_sd_is_population_in_percent(self):
        v = sr.indicator("standard-deviation-return", [100.0, 101.0, 99.99], 2)
        self.assertAlmostEqual(v, 1.0, places=6)      # returns +1%, -1%: population SD 1.0, sample 1.41


# ------------------------------------------------------------------ S2
class S2Windows(unittest.TestCase):
    def test_both_field_styles_and_default(self):
        self.assertEqual(sr.window({"lhs-fn-params": {"window": 14}}, "lhs"), 14)
        self.assertEqual(sr.window({"lhs-window-days": "14"}, "lhs"), 14)
        self.assertEqual(sr.window({"sort-by-window-days": "20"}, "sort-by"), 20)
        self.assertEqual(sr.window({}, "lhs"), 10)

    def test_broken_window_days_not_ignored(self):
        # tree_sim.py read only fn-params; a window-days-only 14 must not evaluate as 10
        s = path(300)
        p = {"X": dict(zip(dates(300), s))}
        sim = sr.Shadow(p)
        n14 = {"lhs-fn": "relative-strength-index", "lhs-val": "X", "lhs-window-days": "14", "comparator": "gt",
               "rhs-val": "0", "rhs-fixed-value?": True}
        sim.trace = []
        sim.cond(n14, dates(300)[-1])
        self.assertAlmostEqual(sim.trace[0]["l"], sr.indicator("relative-strength-index", s, 14))
        self.assertNotAlmostEqual(sim.trace[0]["l"], sr.indicator("relative-strength-index", s, 10))


# ------------------------------------------------------------------ S3
class S3Semantics(unittest.TestCase):
    N = 120

    def setUp(self):
        self.p = px(self.N, UP=path(self.N, drift=0.004), DOWN=path(self.N, drift=-0.004, seed=9),
                    A=path(self.N, seed=3), B=path(self.N, seed=5),
                    VOL=path(self.N, amp=0.05, seed=13), CALM=path(self.N, amp=0.001, seed=17))
        self.d = dates(self.N)
        self.D = self.d[-1]

    def decide(self, tree, prices=None):
        sim = sr.Shadow(copy.deepcopy(prices or self.p))
        return sim.decide(tree, self.d[-70:], {self.D})[self.D]

    def test_if_else(self):
        t = root(if_(cond("relative-strength-index", "UP", 10, "gt", 50), [asset("A")], [asset("B")]))
        self.assertEqual(self.decide(t)[0], {"A": 1.0})
        t2 = root(if_(cond("relative-strength-index", "UP", 10, "lt", 50), [asset("A")], [asset("B")]))
        self.assertEqual(self.decide(t2)[0], {"B": 1.0})            # broken: comparator flipped

    def test_first_true_branch(self):
        c1 = dict(cond("relative-strength-index", "DOWN", 10, "gt", 50), children=[asset("A")])
        c2 = dict(cond("relative-strength-index", "UP", 10, "gt", 50), children=[asset("B")])
        els = {"step": "if-child", "id": "e", "is-else-condition?": True, "children": [asset("VOL")]}
        t = root({"step": "if", "id": "i", "children": [c1, c2, els]})
        self.assertEqual(self.decide(t)[0], {"B": 1.0})
        c2b = dict(cond("relative-strength-index", "UP", 10, "lt", 50), children=[asset("B")])
        t2 = root({"step": "if", "id": "i", "children": [c1, c2b, els]})
        self.assertEqual(self.decide(t2)[0], {"VOL": 1.0})          # broken: no true branch -> else

    def test_wt_cash_specified(self):
        t = {"step": "root", "id": "r", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
            dict(asset("A"), weight={"num": "75.00", "den": 100}), dict(asset("B"), weight={"num": 25, "den": 100})]}]}
        self.assertEqual(self.decide(t)[0], {"A": 0.75, "B": 0.25})
        t["children"][0]["children"][0]["weight"] = {"num": 25, "den": 100}
        t["children"][0]["children"][1]["weight"] = {"num": "75.00", "den": 100}
        self.assertEqual(self.decide(t)[0], {"A": 0.25, "B": 0.75})  # broken: weights swapped

    def test_filter_assets(self):
        f = {"step": "filter", "id": "f", "sort-by-fn": "cumulative-return", "sort-by-fn-params": {"window": 5},
             "select-fn": "top", "select-n": "1", "children": [asset("DOWN"), asset("UP")]}
        self.assertEqual(self.decide(root(f))[0], {"UP": 1.0})
        self.assertEqual(self.decide(root(dict(f, **{"select-fn": "bottom"})))[0], {"DOWN": 1.0})

    def test_filter_groups_by_track_record(self):
        g1 = {"step": "group", "id": "g-vol", "name": "vol", "children": [asset("VOL")]}
        g2 = {"step": "group", "id": "g-calm", "name": "calm", "children": [asset("CALM")]}
        f = {"step": "filter", "id": "f", "sort-by-fn": "standard-deviation-return", "sort-by-fn-params": {"window": 20},
             "select-fn": "bottom", "select-n": "1", "children": [g1, g2]}
        self.assertEqual(self.decide(root(f))[0], {"CALM": 1.0})
        self.assertEqual(self.decide(root(dict(f, **{"select-fn": "top"})))[0], {"VOL": 1.0})

    def test_unsupported_fails_loudly(self):
        ok = rsi_tree("UP")
        sr.validate(ok)
        for bad in (root({"step": "wt-inverse-vol", "id": "v", "children": [asset("A")]}),
                    root(if_(cond("exponential-moving-average-price", "UP", 10, "gt", 1), [asset("A")], [asset("B")])),
                    root(if_(cond("relative-strength-index", "UP", 10, "gte", 50), [asset("A")], [asset("B")]))):
            with self.assertRaises(sr.Unsupported):
                sr.validate(bad)
        sim, target, err = sr.run_engine(self.p, root({"step": "wt-inverse-vol", "id": "v", "children": [asset("A")]}), self.D)
        self.assertIsNone(target)
        self.assertIn("unsupported", err)

    def test_data_gap_is_not_a_decision(self):
        short = {t: dict(list(s.items())[-30:]) for t, s in self.p.items()}
        t = root(if_(cond("relative-strength-index", "UP", 10, "gt", 50), [asset("A")], [asset("B")]))
        sim = sr.Shadow(short)
        target, err = sim.decide(t, self.d[-30:], {self.D})[self.D]
        self.assertIsNone(target)
        self.assertIn("RSI(UP,10)", err)
        self.assertEqual(self.decide(t)[0], {"A": 1.0})             # broken: full history decides


# ------------------------------------------------------------------ S4
class S4Fidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.fx = json.load(f)
        cls.cfg = sr.load_manifest()

    def run_all(self, shift=0):
        ok = n = 0
        win = self.fx["window"]
        for eng, cfg in self.cfg.items():
            era = cfg["eras"][-1]
            self.assertEqual(era["version"], self.fx["eras"][eng])
            tree = sr.load_tree(era)
            tk = sr.tree_tickers(tree)
            days = sr.common_days(self.fx["prices"], tk, win[-1])
            days = days[max(0, days.index(win[0]) - sr.SUB_WARMUP):]
            sim = sr.Shadow({t: dict(self.fx["prices"][t]) for t in tk})
            dec = sim.decide(tree, days, set(win))
            for i, d in enumerate(win):
                if i + shift >= len(win):
                    continue
                n += 1
                ok += sr.agrees(dec[d][0], self.fx["expected"][eng][win[i + shift]], cfg.get("corridor"))
        return ok, n

    def test_reproduces_composer_backtest(self):
        ok, n = self.run_all()
        self.assertEqual((ok, n), (160, 160))

    def test_broken_shifted_answer_key(self):
        ok, n = self.run_all(shift=1)
        self.assertLess(ok / n, 0.85)

    def test_broken_cutler_rsi(self):
        orig = sr.indicator

        def patched(fn, s, w):
            if fn == "relative-strength-index":
                return cutler(s, w) if len(s) > w else None
            return orig(fn, s, w)
        sr.indicator = patched
        try:
            ok, n = self.run_all()
        finally:
            sr.indicator = orig
        self.assertLess(ok, n)


# ------------------------------------------------------------------ S5
class S5Classify(unittest.TestCase):
    def test_daily_boundary(self):
        self.assertTrue(sr.agrees({"A": 1.0}, {"A": 0.971, "B": 0.029}))
        self.assertFalse(sr.agrees({"A": 1.0}, {"A": 0.969, "B": 0.031}))

    def test_corridor_boundary(self):
        t = {"A": 0.75, "B": 0.25}
        self.assertTrue(sr.agrees(t, {"A": 0.641, "B": 0.359}, corridor=0.10))
        self.assertFalse(sr.agrees(t, {"A": 0.641, "B": 0.359}))          # a daily engine would not pass
        self.assertFalse(sr.agrees(t, {"A": 0.63, "B": 0.37}, corridor=0.10))

    def _classify(self, bump, live):
        p = near_threshold_prices(bump=bump)
        tree = rsi_tree()
        sim, target, tr = sr.run_engine(p, tree, dates(120)[-1])
        return target, sr.classify(sim, tree, dates(120)[-1], target, tr, live)

    def test_knife_edge_within_half_sigma(self):
        target, (status, det) = self._classify(0.0003, {"B": 1.0})
        self.assertEqual(target, {"A": 1.0})
        self.assertEqual(status, "knife-edge")
        self.assertEqual(det["edge"]["ticker"], "X")
        self.assertLess(det["edge"]["move"], 0)
        self.assertLessEqual(det["edge"]["sigma_ratio"], sr.KNIFE_SIGMA)

    def test_broken_far_from_threshold_is_mismatch(self):
        target, (status, det) = self._classify(0.03, {"B": 1.0})
        self.assertEqual(target, {"A": 1.0})
        self.assertEqual(status, "mismatch")
        self.assertIn("RSI(X,2)", det["why"])

    def test_agree(self):
        _, (status, det) = self._classify(0.03, {"A": 0.999})
        self.assertEqual(status, "agree")


# ------------------------------------------------------------------ S6
CFG = {"E1": {"symphony": "s1", "eras": [{"version": "v1aaaaaaaa", "from": "2025-01-01", "tree": "t1"}]},
       "E2": {"symphony": "s2", "corridor": 0.10, "eras": [{"version": "v2bbbbbbbb", "from": "2025-01-01", "tree": "t2"}]}}
TREES = {"t1": rsi_tree(), "t2": {"step": "root", "id": "r2", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
    dict(asset("A"), weight={"num": 75, "den": 100}), dict(asset("B"), weight={"num": 25, "den": 100})]}]}}


def load(era):
    return TREES[era["tree"]]


def meta(att1, h1, att2=None, h2=None):
    att2 = att2 or att1
    h2 = h2 or {"A": 0.75, "B": 0.249}
    return [{"id": "s1", "name": "E1", "last_rebalance_attempted_on": att1,
             "holdings": [{"ticker": t, "allocation": w} for t, w in h1.items()]},
            {"id": "s2", "name": "E2", "last_rebalance_attempted_on": att2,
             "holdings": [{"ticker": t, "allocation": w} for t, w in h2.items()]}]


class S6Assess(unittest.TestCase):
    D = dates(120)[-1]

    def run_(self, h1, bump=0.0003, att=None, st=None, prices=None):
        st = {} if st is None else st
        p = prices or near_threshold_prices(bump=bump)
        rows, alerts, notes = sr.assess(CFG, meta(att or self.D, h1), p, self.D, st, load=load)
        return {r["engine"]: r["status"] for r in rows}, alerts, notes, st

    def test_agree_is_silent(self):
        s, alerts, _, _ = self.run_(h1={"A": 0.999})
        self.assertEqual(s, {"E1": "agree", "E2": "agree"})
        self.assertEqual(alerts, [])

    def test_mismatch_alerts(self):
        s, alerts, _, _ = self.run_(h1={"B": 0.999}, bump=0.03)
        self.assertEqual(s["E1"], "mismatch")
        self.assertTrue(alerts and alerts[0].startswith("SHADOW MISMATCH — E1"))

    def test_knife_edge_second_session_alerts(self):
        st = {}
        s, a1, _, st = self.run_(h1={"B": 0.999}, st=st)
        self.assertEqual((s["E1"], a1), ("knife-edge", []))
        _, a2, _, st = self.run_(h1={"B": 0.999}, st=st)
        self.assertTrue(a2 and a2[0].startswith("SHADOW KNIFE-EDGE x2 — E1"))

    def test_broken_agree_resets_knife_streak(self):
        st = {}
        self.run_(h1={"B": 0.999}, st=st)
        self.run_(h1={"A": 0.999}, st=st)                            # agree in between
        _, a3, _, _ = self.run_(h1={"B": 0.999}, st=st)
        self.assertEqual(a3, [])

    def test_no_rebalance_start_still_resumed(self):
        st = {}
        old = dates(120)[-4]
        s, a1, _, st = self.run_(h1={"A": 0.999}, att=old, st=st)
        self.assertEqual(s, {"E1": "no-rebalance", "E2": "no-rebalance"})
        self.assertTrue(a1[0].startswith("COMPOSER DID NOT REBALANCE — no rebalance attempt on " + self.D))
        self.assertIn(f"last attempt {old}", a1[0])
        _, a2, _, st = self.run_(h1={"A": 0.999}, att=old, st=st)
        self.assertTrue(a2[0].startswith("COMPOSER STILL NOT REBALANCING (session 2)"))
        _, a3, _, st = self.run_(h1={"A": 0.999}, st=st)
        self.assertTrue(a3[0].startswith("COMPOSER REBALANCING RESUMED"))
        self.assertIsNone(st["frozen_since"])

    def test_broken_attempted_today_is_not_frozen(self):
        _, alerts, _, st = self.run_(h1={"A": 0.999})
        self.assertFalse(any("REBALANC" in a for a in alerts))
        self.assertNotIn("frozen_since", st)

    def test_frozen_text_uses_corridor_for_kmlm(self):
        # E2 frozen 70/30 is inside its 10% corridor: no '(frozen at ...)' for E2
        rows, alerts, _ = sr.assess(CFG, meta(dates(120)[-4], {"A": 0.999}, h2={"A": 0.70, "B": 0.30}),
                                    near_threshold_prices(), self.D, {}, load=load)
        self.assertIn("E2 A 75%, B 25%.", alerts[0])
        rows, alerts, _ = sr.assess(CFG, meta(dates(120)[-4], {"A": 0.999}, h2={"A": 0.60, "B": 0.40}),
                                    near_threshold_prices(), self.D, {}, load=load)
        self.assertIn("E2 A 75%, B 25% (frozen at A 60%, B 40%)", alerts[0])   # broken: outside the corridor

    def test_unavailable_is_a_note(self):
        p = near_threshold_prices()
        del p["X"][self.D]
        s, alerts, notes, _ = self.run_(h1={"A": 0.999}, prices=p)
        self.assertEqual(s["E1"], "unavailable")
        self.assertEqual(alerts, [])
        self.assertTrue(any("no close on" in n for n in notes))


# ------------------------------------------------------------------ S7
class S7Hook(unittest.TestCase):
    NOW = datetime.datetime(2025, 5, 1, 21, 35, tzinfo=UTC)
    D = dates(120)[-1]                  # 2025-04-30

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (sr.load_manifest, sr.load_tree, sr.fetch_prices, sr.LEDGER)
        sr.load_manifest = lambda: CFG
        sr.load_tree = load
        sr.LEDGER = os.path.join(self.tmp.name, "ledger.jsonl")
        self.prices = near_threshold_prices()

    def tearDown(self):
        sr.load_manifest, sr.load_tree, sr.fetch_prices, sr.LEDGER = self.saved
        self.tmp.cleanup()

    def hook(self, state, m, get=None):
        alerts, snap, out = [], {}, io.StringIO()
        with contextlib.redirect_stdout(out):
            sr.check_shadow(state, alerts, snap, m, self.NOW, get=get)
        return alerts, snap, out.getvalue()

    def test_yahoo_failure_is_a_note(self):
        def boom(*a, **k):
            raise RuntimeError("Yahoo down")
        sr.fetch_prices = boom
        state = {}
        alerts, snap, out = self.hook(state, meta(dates(120)[-4], {"A": 0.999}))
        self.assertEqual(alerts, [])
        self.assertIn("shadow runner unavailable: Yahoo down", out)
        self.assertNotIn("last_date", state.get("shadow", {}))
        self.assertFalse(os.path.exists(sr.LEDGER))

    def test_drift_exit_keeps_day_alerts(self):
        sr.fetch_prices = lambda *a, **k: (self.prices, {})

        def get(path):
            raise SystemExit("error: HTTP 401")
        state = {}
        alerts, snap, out = self.hook(state, meta(dates(120)[-4], {"A": 0.999}), get=get)
        self.assertTrue(alerts and alerts[0].startswith("COMPOSER DID NOT REBALANCE"))
        self.assertIn("logic-drift check unavailable", out)
        self.assertEqual(state["shadow"]["last_date"], self.D)
        self.assertEqual(len(sr.read_ledger()), 2)

    def test_same_session_not_reassessed(self):
        sr.fetch_prices = lambda *a, **k: (self.prices, {})
        state = {}
        self.hook(state, meta(dates(120)[-4], {"A": 0.999}))
        alerts, snap, out = self.hook(state, meta(dates(120)[-4], {"A": 0.999}))
        self.assertEqual(alerts, [])
        self.assertIn("nothing re-assessed", out)
        self.assertEqual(state["shadow"]["frozen_sessions"], 1)        # not double-counted


# ------------------------------------------------------------------ S8
class S8Drift(unittest.TestCase):
    def setUp(self):
        self.approved = rsi_tree()

    def get_for(self, head, tree):
        def get(path):
            if path.endswith("/versions"):
                return [{"version_id": head, "created_at": "2026-11-02T10:00:00-05:00"}]
            return tree
        return get

    def drift(self, head, tree, st, weekday=1):
        cfg = {"E1": CFG["E1"]}
        return sr.check_drift(cfg, self.get_for(head, tree), st, weekday, load=lambda era: self.approved)

    def test_approved_head_is_silent(self):
        self.assertEqual(self.drift("v1aaaaaaaa", self.approved, {}), ([], []))

    def test_rename_is_a_note(self):
        renamed = copy.deepcopy(self.approved)
        renamed["name"], renamed["id"] = "new name", "other-id"
        c = renamed["children"][0]["children"][0]["children"][0]
        c["lhs-window-days"] = str(c.pop("lhs-fn-params")["window"])     # same window, other field style
        alerts, notes = self.drift("v9renamed", renamed, {})
        self.assertEqual(alerts, [])
        self.assertTrue(notes and "unchanged logic" in notes[0])

    def test_changed_logic_alerts_once_then_mondays(self):
        changed = copy.deepcopy(self.approved)
        changed["children"][0]["children"][0]["children"][0]["rhs-val"] = "55"
        st = {}
        a1, _ = self.drift("v9changed", changed, st)
        self.assertTrue(a1 and a1[0].startswith("LOGIC DRIFT — E1: Composer runs version v9changed"))
        a2, _ = self.drift("v9changed", changed, st, weekday=2)
        self.assertEqual(a2, [])
        a3, _ = self.drift("v9changed", changed, st, weekday=0)
        self.assertEqual(len(a3), 1)

    def test_canonical_sees_logic_not_display(self):
        a = rsi_tree()
        b = copy.deepcopy(a)
        b["children"][0]["children"][0]["children"][0]["comparator"] = "lt"
        c = copy.deepcopy(a)
        c["children"][0]["children"][0]["children"][0]["children"][0]["ticker"] = "Z"
        self.assertNotEqual(sr.canonical(a), sr.canonical(b))
        self.assertNotEqual(sr.canonical(a), sr.canonical(c))
        w1 = {"step": "wt-cash-specified", "children": [dict(asset("A"), weight={"num": "50.00", "den": 100})]}
        w2 = {"step": "wt-cash-specified", "children": [dict(asset("A"), weight={"num": 50, "den": 100}, id="x")]}
        self.assertEqual(sr.canonical(w1), sr.canonical(w2))


# ------------------------------------------------------------------ S9
class S9Registry(unittest.TestCase):
    def test_eras_ordered_and_supported(self):
        for eng, cfg in sr.load_manifest().items():
            froms = [e["from"] for e in cfg["eras"]]
            self.assertEqual(froms, sorted(froms), eng)
            self.assertEqual(len({e["version"] for e in cfg["eras"]}), len(cfg["eras"]))
            for era in cfg["eras"]:
                sr.validate(sr.load_tree(era))

    def test_hg_eras_equal_gate_watch_fixtures(self):
        hg = {e["version"]: sr.load_tree(e) for e in sr.load_manifest()["HG"]["eras"]}
        fx = os.path.join(HERE, "..", "..", "fixtures")
        with open(os.path.join(fx, "hg-live-gated-2026-10-18.raw.json")) as f:
            gated = json.load(f)
        with open(os.path.join(fx, "hg-live-pre-gate-2026-10-18.raw.json")) as f:
            pre = json.load(f)
        self.assertEqual(sr.canonical(hg["2oyXahw1VWpFtV15dhIi"]), sr.canonical(gated))
        self.assertEqual(sr.canonical(hg["bP4mvRy6YHHejuPGUBNY"]), sr.canonical(pre))
        self.assertNotEqual(sr.canonical(gated), sr.canonical(pre))   # broken: the gate is a logic change


# ------------------------------------------------------------------ S10
class S10Plumbing(unittest.TestCase):
    def test_ledger_upsert_and_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "l.jsonl")
            sr.write_ledger([{"date": "2026-10-02", "engine": "HARV", "status": "agree"},
                             {"date": "2026-10-01", "engine": "HG", "status": "knife-edge"}], p)
            sr.write_ledger([{"date": "2026-10-01", "engine": "HG", "status": "agree"},
                             {"date": "2026-10-02", "engine": "HG", "status": "agree"}], p)
            rows = sr.read_ledger(p)
            self.assertEqual([(r["date"], r["engine"], r["status"]) for r in rows],
                             [("2026-10-01", "HG", "agree"), ("2026-10-02", "HG", "agree"), ("2026-10-02", "HARV", "agree")])
            self.assertEqual(sr.record(rows, 1), (1, {"agree": 2}))

    def test_live_weights(self):
        s = {"holdings": [{"ticker": "A", "allocation": 0.5}, {"ticker": "B", "allocation": 0.499},
                          {"ticker": "C", "allocation": 0.0}]}
        w = sr.live_weights(s)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)
        self.assertNotIn("C", w)
        self.assertEqual(sr.live_weights({"holdings": []}), {})

    def test_final_through_boundary(self):
        for hm_utc, tz in (((20, 14), "summer"), ((21, 14), "winter")):
            day = datetime.date(2026, 7, 15) if tz == "summer" else datetime.date(2026, 12, 15)
            before = datetime.datetime(day.year, day.month, day.day, *hm_utc, tzinfo=UTC)
            after = before + datetime.timedelta(minutes=1)
            self.assertEqual(sr.final_through(before), day - datetime.timedelta(days=1), tz)
            self.assertEqual(sr.final_through(after), day, tz)

    def test_eras(self):
        cfg = {"eras": [{"from": "2026-06-30", "v": 1}, {"from": "2026-07-31", "v": 2}, {"from": "2026-10-19", "v": 3}]}
        self.assertEqual(sr.era_for(cfg, "2026-07-30")["v"], 1)
        self.assertEqual(sr.era_for(cfg, "2026-07-31")["v"], 2)
        self.assertIsNone(sr.era_for(cfg, "2026-06-29"))
        self.assertEqual([e["v"] for e in sr.eras_between(cfg, "2026-10-12", "2026-10-22")], [2, 3])
        self.assertEqual([e["v"] for e in sr.eras_between(cfg, "2026-10-20", "2026-10-22")], [3])


if __name__ == "__main__":
    unittest.main()
