"""Merge-blocking gate tests for shadow_runner.py (the shadow decision runner, results.md
addendum 48).

House rule: a gate that cannot fail is not a gate. Each behavioural test is paired with a
BROKEN-INPUT counterpart that must land on the other side. The counter-agent's surviving mutants
(add. 48) each have a test that now kills them.

  S1  indicators: Wilder RSI over all history against a from-scratch reference; Cutler differs;
      the pinned SLEEVE 2026-04-07 condition flips if RSI is cut to 251 closes; percent units for
      CR; population SD; MA window; the 20-session sigma
  S2  windows: either field style, default 10, conflicting fields refused
  S3  tree semantics: if/else order, wt-cash-specified, filters over assets and groups, a group
      filter decides through run_engine (sub-tree warm-up), Unsupported and DataGap fail loudly
  S4  fidelity: the four approved trees on frozen prices reproduce Composer's own backtest on
      160/160 sessions (KMLM on its corridor path); a one-day shift or Cutler RSI breaks it
  S5  classification: 3% daily boundary; KMLM corridor path (trigger, drifted holdings, ambiguity
      band) and the lenient fallback; knife-edge on decision-time prices (bars) and, without bars,
      the 0.3-sigma one-ticker search (rhs tickers searched, corridor respected); what_if restores
  S6  assess(): agree silent; mismatch alerts; no-rebalance per engine from Composer's record even
      when prices fail, STILL / RESUMED, paused symphonies on Mondays only; search-basis knife-edge
      streak (intraday ones never alert; an unavailable session resets it); SHADOW BLIND at 3;
      attempted > D and evaluator errors are per-engine notes
  S7  check_shadow(): Yahoo failure keeps state, counts, and alerts at the 3rd run; the drift check
      runs without prices and survives one engine's SystemExit; a malformed ledger line is skipped;
      the same session is not re-assessed except engines left unavailable; atomic ledger writes
  S8  logic drift: every logic field moves canonical(), display fields and number formats do not;
      alerts when first seen / changed / Mondays, rename is a note, first_diff names the node
  S9  approved registry: eras ordered, files load, every tree validates; HG eras equal the
      gate-watch fixtures
  S10 data plumbing: fetch_yahoo uses adjclose and repairs a lagging dividend or split; the
      fetch_prices cut at 16:15 ET; bar_price; the ET fallback matches zoneinfo; ledger upsert,
      record, live_weights, eras

Run: python3 -m unittest composer.scripts.tests.test_shadow_runner -v
"""
import contextlib
import copy
import datetime
import gzip
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import shadow_runner as sr  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "shadow-2026-10-28.json.gz")
WARMUP = os.path.join(HERE, "fixtures", "shadow-warmup-2026-04-07.json")
UTC = datetime.timezone.utc
N = 120


# ------------------------------------------------------------------ helpers
def dates(n, start=datetime.date(2025, 1, 1)):
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range(n)]


D = dates(N)[-1]           # 2025-04-30
D0 = dates(N)[-2]


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
        lo, hi = (mid, hi) if sr.indicator("relative-strength-index", s[:-1] + [mid], w) < target else (lo, mid)
    return (lo + hi) / 2


def near_threshold_prices(bump=0.0003, n=N):
    """X whose RSI(2) on the last day sits just above 50 (bump = relative distance of its close)"""
    s = path(n, amp=0.01)
    s[-1] = last_for_rsi(s, 2, 50.0) * (1 + bump)
    return px(n, X=s, A=path(n, seed=3), B=path(n, seed=5), C=path(n, seed=19), SPY=path(n, seed=11))


def sigma_x(p):
    return sr.Shadow(p).sigma("X", D)


def flip_bump(sig_ratio):
    """bump that puts X's close sig_ratio daily sigmas above the RSI(2)=50 threshold"""
    return sig_ratio * sigma_x(near_threshold_prices())


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


def bars_for(p, moves, day=D):
    """5-minute bars whose 15:40-15:55 closes sit at close*(1+move) for each ticker (others at the close)"""
    out = {}
    for t, s in p.items():
        c = s[day] * (1 + moves.get(t, 0.0))
        out[t] = {day: {"15:35": c, "15:40": c, "15:45": c, "15:50": c, "15:55": s[day]}}
    return out


# ------------------------------------------------------------------ S1
class S1Indicators(unittest.TestCase):
    def test_wilder_full_history_matches_reference(self):
        s = path(400)
        for w in (2, 10, 45):
            self.assertAlmostEqual(sr.indicator("relative-strength-index", s, w), wilder_ref(s, w), places=9)

    def test_broken_cutler_differs(self):
        s = path(300)
        self.assertGreater(abs(sr.indicator("relative-strength-index", s, 10) - cutler(s, 10)), 0.5)

    def test_pinned_sleeve_warmup(self):
        with open(WARMUP) as f:
            p = json.load(f)["prices"]
        ief = [p["IEF"][d] for d in sorted(p["IEF"])]
        psq = [p["PSQ"][d] for d in sorted(p["PSQ"])]
        rsi = lambda s, w: sr.indicator("relative-strength-index", s, w)  # noqa: E731
        self.assertTrue(rsi(ief, 8) < rsi(psq, 45))                    # Composer: InverseHold branch
        self.assertFalse(rsi(ief[-251:], 8) < rsi(psq[-251:], 45))     # broken: a 250-close warm-up
        # and through the evaluator, which must hand RSI the whole history
        node = cond("relative-strength-index", "IEF", 8, "lt", "PSQ", "relative-strength-index", 45)
        self.assertTrue(sr.Shadow(p).cond(node, "2026-04-07"))

    def test_rsi_needs_60_changes(self):
        s = path(61)
        self.assertIsNotNone(sr.indicator("relative-strength-index", s, 10))
        self.assertIsNone(sr.indicator("relative-strength-index", s[1:], 10))

    def test_ma_window(self):
        self.assertEqual(sr.indicator("moving-average-price", [1, 2, 3, 4], 3), 3.0)
        self.assertEqual(sr.indicator("moving-average-price", [1, 2, 3, 4], 4), 2.5)
        self.assertIsNone(sr.indicator("moving-average-price", [1, 2, 3], 4))

    def test_cumulative_return_in_percent(self):
        v = sr.indicator("cumulative-return", [100.0, 101.76], 1)
        self.assertAlmostEqual(v, 1.76, places=9)
        self.assertTrue(v > 1.75)
        self.assertFalse(v / 100 > 1.75)

    def test_sd_is_population_in_percent(self):
        self.assertAlmostEqual(sr.indicator("standard-deviation-return", [100.0, 101.0, 99.99], 2), 1.0, places=6)

    def test_sigma_uses_20_sessions(self):
        s = [100.0]
        for i in range(60):
            s.append(s[-1] * (1.05 if i < 39 else (1.01 if i % 2 else 0.99)))
        p = {"X": dict(zip(dates(len(s)), s))}
        got = sr.Shadow(p).sigma("X", dates(len(s))[-1])
        self.assertAlmostEqual(got, 0.01, places=4)          # last 20 returns alternate +-1%
        self.assertGreater(abs(sr.Shadow(p).sigma("X", dates(len(s))[-1], 60) - 0.01), 0.002)


# ------------------------------------------------------------------ S2
class S2Windows(unittest.TestCase):
    def test_both_field_styles_and_default(self):
        self.assertEqual(sr.window({"lhs-fn-params": {"window": 14}}, "lhs"), 14)
        self.assertEqual(sr.window({"lhs-window-days": "14"}, "lhs"), 14)
        self.assertEqual(sr.window({"sort-by-window-days": "20"}, "sort-by"), 20)
        self.assertEqual(sr.window({"lhs-fn-params": {"window": 10}, "lhs-window-days": "10"}, "lhs"), 10)
        self.assertEqual(sr.window({}, "lhs"), 10)

    def test_ticker_comparison_needs_rhs_fn(self):
        node = cond("relative-strength-index", "UP", 10, "gt", "DOWN", "relative-strength-index", 10)
        sr.validate(root(if_(node, [asset("A")], [asset("B")])))
        bare = dict(node)
        bare.pop("rhs-fn")                            # Composer's reading of this is not known: refuse
        with self.assertRaises(sr.Unsupported):
            sr.validate(root(if_(bare, [asset("A")], [asset("B")])))
        p = px(N, UP=path(N, drift=0.004), DOWN=path(N, drift=-0.004, seed=9))
        with self.assertRaises(sr.Unsupported):
            sr.Shadow(p).cond(bare, D)

    def test_broken_conflicting_fields_refused(self):
        with self.assertRaises(sr.Unsupported):
            sr.window({"lhs-fn-params": {"window": 10}, "lhs-window-days": "14"}, "lhs")
        t = rsi_tree()
        t["children"][0]["children"][0]["children"][0]["lhs-window-days"] = "5"
        with self.assertRaises(sr.Unsupported):
            sr.validate(t)


# ------------------------------------------------------------------ S3
class S3Semantics(unittest.TestCase):
    def setUp(self):
        self.p = px(N, UP=path(N, drift=0.004), DOWN=path(N, drift=-0.004, seed=9), A=path(N, seed=3), B=path(N, seed=5),
                    VOL=path(N, amp=0.05, seed=13), CALM=path(N, amp=0.001, seed=17))

    def decide(self, tree, prices=None):
        sim = sr.Shadow(copy.deepcopy(prices or self.p))
        return sim.decide(tree, dates(N)[-70:], {D})[D]

    def test_if_else(self):
        t = root(if_(cond("relative-strength-index", "UP", 10, "gt", 50), [asset("A")], [asset("B")]))
        self.assertEqual(self.decide(t)[0], {"A": 1.0})
        t2 = root(if_(cond("relative-strength-index", "UP", 10, "lt", 50), [asset("A")], [asset("B")]))
        self.assertEqual(self.decide(t2)[0], {"B": 1.0})

    def test_first_true_branch(self):
        c1 = dict(cond("relative-strength-index", "DOWN", 10, "gt", 50), children=[asset("A")])
        c2 = dict(cond("relative-strength-index", "UP", 10, "gt", 50), children=[asset("B")])
        els = {"step": "if-child", "id": "e", "is-else-condition?": True, "children": [asset("VOL")]}
        self.assertEqual(self.decide(root({"step": "if", "id": "i", "children": [c1, c2, els]}))[0], {"B": 1.0})
        c2b = dict(cond("relative-strength-index", "UP", 10, "lt", 50), children=[asset("B")])
        self.assertEqual(self.decide(root({"step": "if", "id": "i", "children": [c1, c2b, els]}))[0], {"VOL": 1.0})

    def test_wt_cash_specified(self):
        t = {"step": "root", "id": "r", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
            dict(asset("A"), weight={"num": "75.00", "den": 100}), dict(asset("B"), weight={"num": 25, "den": 100})]}]}
        self.assertEqual(self.decide(t)[0], {"A": 0.75, "B": 0.25})
        t["children"][0]["children"][0]["weight"] = {"num": 25, "den": 100}
        t["children"][0]["children"][1]["weight"] = {"num": "75.00", "den": 100}
        self.assertEqual(self.decide(t)[0], {"A": 0.25, "B": 0.75})

    def test_filter_assets(self):
        f = {"step": "filter", "id": "f", "sort-by-fn": "cumulative-return", "sort-by-fn-params": {"window": 5},
             "select-fn": "top", "select-n": "1", "children": [asset("DOWN"), asset("UP")]}
        self.assertEqual(self.decide(root(f))[0], {"UP": 1.0})
        self.assertEqual(self.decide(root(dict(f, **{"select-fn": "bottom"})))[0], {"DOWN": 1.0})

    def group_filter(self, sel="bottom"):
        g1 = {"step": "group", "id": "g-vol", "name": "vol", "children": [asset("VOL")]}
        g2 = {"step": "group", "id": "g-calm", "name": "calm", "children": [asset("CALM")]}
        return root({"step": "filter", "id": "f", "sort-by-fn": "standard-deviation-return",
                     "sort-by-fn-params": {"window": 20}, "select-fn": sel, "select-n": "1", "children": [g1, g2]})

    def test_filter_groups_by_track_record(self):
        self.assertEqual(self.decide(self.group_filter())[0], {"CALM": 1.0})
        self.assertEqual(self.decide(self.group_filter("top"))[0], {"VOL": 1.0})

    def test_group_filter_decides_through_run_engine(self):
        # the daily path must warm the sub-trees up (a cold start leaves them without history)
        sim, target, err = sr.run_engine(self.p, self.group_filter(), D)
        self.assertEqual(target, {"CALM": 1.0}, err)
        cold = sr.Shadow(copy.deepcopy(self.p)).decide(self.group_filter(), [D], {D})[D]
        self.assertIsNone(cold[0])                                      # broken: no warm-up

    def test_unsupported_fails_loudly(self):
        sr.validate(rsi_tree("UP"))
        for bad in (root({"step": "wt-inverse-vol", "id": "v", "children": [asset("A")]}),
                    root(if_(cond("exponential-moving-average-price", "UP", 10, "gt", 1), [asset("A")], [asset("B")])),
                    root(if_(cond("relative-strength-index", "UP", 10, "gte", 50), [asset("A")], [asset("B")]))):
            with self.assertRaises(sr.Unsupported):
                sr.validate(bad)
        _, target, err = sr.run_engine(self.p, root({"step": "wt-inverse-vol", "id": "v", "children": [asset("A")]}), D)
        self.assertIsNone(target)
        self.assertIn("unsupported", err)

    def test_data_gap_is_not_a_decision(self):
        short = {t: dict(list(s.items())[-30:]) for t, s in self.p.items()}
        t = root(if_(cond("relative-strength-index", "UP", 10, "gt", 50), [asset("A")], [asset("B")]))
        target, err = sr.Shadow(short).decide(t, dates(N)[-30:], {D})[D]
        self.assertIsNone(target)
        self.assertIn("RSI(UP,10)", err)
        self.assertEqual(self.decide(t)[0], {"A": 1.0})


# ------------------------------------------------------------------ S4
class S4Fidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt") as f:
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
            p = {t: dict(self.fx["prices"][t]) for t in tk}
            days = sr.common_days(p, tk, win[-1])
            days = days[max(0, days.index(win[0]) - sr.SUB_WARMUP):]
            dec = sr.Shadow(p).decide(tree, days, set(win))
            exp = self.fx["expected"][eng]
            ds = sorted(exp)
            for i, d in enumerate(win):
                j = ds.index(d) + shift
                if j >= len(ds):
                    continue
                prev = ds[j - 1]
                drifted = sr.drift(exp[prev], p, prev, ds[j]) if cfg.get("corridor") else None
                n += 1
                ok += sr.agrees(dec[d][0], exp[ds[j]], cfg.get("corridor"), drifted)
        return ok, n

    def test_reproduces_composer_backtest(self):
        self.assertEqual(self.run_all(), (160, 160))

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

    def test_corridor_lenient_without_previous_session(self):
        t = {"A": 0.75, "B": 0.25}
        self.assertTrue(sr.agrees(t, {"A": 0.641, "B": 0.359}, corridor=0.10))
        self.assertFalse(sr.agrees(t, {"A": 0.641, "B": 0.359}))
        self.assertFalse(sr.agrees(t, {"A": 0.63, "B": 0.37}, corridor=0.10))

    def test_corridor_path(self):
        t = {"A": 0.75, "B": 0.25}
        far = {"A": 0.62, "B": 0.38}                 # 13pp off: Composer must rebalance to target
        self.assertTrue(sr.agrees(t, t, 0.10, far))
        self.assertFalse(sr.agrees(t, far, 0.10, far))
        near = {"A": 0.70, "B": 0.30}                # 5pp off: Composer must hold the drifted weights
        self.assertTrue(sr.agrees(t, near, 0.10, near))
        self.assertFalse(sr.agrees(t, t, 0.10, near))
        # a 9% leg the target lacks passes the lenient check but not the path
        leg = {"A": 0.75, "B": 0.16, "C": 0.09}
        self.assertTrue(sr.agrees(t, leg, 0.10))
        self.assertFalse(sr.agrees(t, leg, 0.10, t))
        edge = {"A": 0.645, "B": 0.355}              # 10.5pp: inside the ambiguity band, both accepted
        self.assertTrue(sr.agrees(t, t, 0.10, edge) and sr.agrees(t, edge, 0.10, edge))

    def test_drift_and_corridor_base(self):
        p = {"A": {"d0": 100.0, "d1": 110.0}, "B": {"d0": 100.0, "d1": 100.0}, "SPY": {"d0": 1, "d1": 1}}
        w = sr.drift({"A": 0.5, "B": 0.5}, p, "d0", "d1")
        self.assertAlmostEqual(w["A"], 0.55 / 1.05, places=9)
        cfg = {"corridor": 0.1}
        row = {"date": "d0", "live": {"A": 0.5, "B": 0.5}, "net_deposits": 1000}
        self.assertIsNotNone(sr.corridor_base(cfg, row, {"net_deposits": 1000}, p, "d1"))
        self.assertIsNone(sr.corridor_base(cfg, row, {"net_deposits": 6000}, p, "d1"))   # a deposit in between
        self.assertIsNone(sr.corridor_base(cfg, dict(row, date="older"), {}, p, "d1"))    # not the session before
        self.assertIsNone(sr.corridor_base(cfg, dict(row, live_asof="older"), {}, p, "d1"))  # stale holdings
        self.assertIsNone(sr.corridor_base({}, row, {}, p, "d1"))                           # not a threshold engine

    def _classify(self, bump, live, bars=None, tree=None, corridor=None, prices=None):
        p = prices or near_threshold_prices(bump=bump)
        tree = tree or rsi_tree()
        sim, target, tr = sr.run_engine(p, tree, D)
        raw = {t: dict(s) for t, s in p.items()}
        intraday = (lambda: sr.at_times(p, raw, bars(p), tree, D)) if bars else None
        return target, sr.classify(sim, tree, D, target, tr, live, corridor, None, intraday)

    def test_knife_edge_on_decision_time_prices(self):
        target, (status, det) = self._classify(0.0003, {"B": 1.0}, bars=lambda p: bars_for(p, {"X": -0.002}))
        self.assertEqual((target, status, det["edge"]["basis"]), ({"A": 1.0}, "knife-edge", "intraday"))
        self.assertIn(det["edge"]["time"], sr.KNIFE_TIMES)

    def test_broken_bars_that_do_not_flip_are_a_mismatch(self):
        # bars present but X barely moved: the search must NOT then excuse it
        target, (status, det) = self._classify(0.0003, {"B": 1.0}, bars=lambda p: bars_for(p, {"X": 0.0}))
        self.assertEqual(status, "mismatch")
        self.assertIn("15:45", det["checked"])

    def test_search_fallback_radius(self):
        _, (status, det) = self._classify(flip_bump(0.15), {"B": 1.0})
        self.assertEqual((status, det["edge"]["basis"]), ("knife-edge", "search"))
        self.assertLessEqual(det["edge"]["sigma_ratio"], sr.KNIFE_SIGMA)
        _, (status, det) = self._classify(flip_bump(0.45), {"B": 1.0})        # broken: beyond 0.3 sigma
        self.assertEqual(status, "mismatch")
        self.assertIn("RSI(X,2)", det["why"])

    def test_search_reaches_rhs_ticker(self):
        # RSI(CALM,2) > RSI(X,2): CALM barely moves (its sigma is tiny), so only X can explain the flip
        p = near_threshold_prices(bump=flip_bump(0.1))
        p["CALM"] = dict(zip(dates(N), path(N, amp=0.00001, seed=23)))
        lhs = sr.indicator("relative-strength-index", [p["CALM"][d] for d in dates(N)], 2)
        s = [p["X"][d] for d in dates(N)]
        s[-1] = last_for_rsi(s, 2, lhs) * (1 - flip_bump(0.1))                # X's RSI just below CALM's
        p["X"] = dict(zip(dates(N), s))
        tree = root(if_(cond("relative-strength-index", "CALM", 2, "gt", "X", "relative-strength-index", 2),
                        [asset("A")], [asset("B")]))
        target, (status, det) = self._classify(0, {"B": 1.0}, tree=tree, prices=p)
        self.assertEqual((target, status, det["edge"]["ticker"]), ({"A": 1.0}, "knife-edge", "X"))

    def test_search_respects_corridor(self):
        tree = {"step": "root", "id": "r", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
            dict(if_(cond("relative-strength-index", "X", 2, "gt", 50), [asset("A")], [asset("B")]), weight={"num": 75}),
            dict(asset("C"), weight={"num": 25})]}]}
        live = {"B": 0.70, "C": 0.30}                 # the flipped target, drifted 5pp: corridor-agree only
        _, (status, _) = self._classify(flip_bump(0.1), live, tree=tree, corridor=0.10)
        self.assertEqual(status, "knife-edge")
        _, (status, _) = self._classify(flip_bump(0.1), live, tree=tree)       # broken: as a daily engine
        self.assertEqual(status, "mismatch")

    def test_what_if_restores_prices(self):
        p = near_threshold_prices()
        before = copy.deepcopy(p)
        sim, target, tr = sr.run_engine(p, rsi_tree(), D)
        self.assertEqual(sim.what_if(rsi_tree(), D, "X", -0.01), {"B": 1.0})
        self.assertEqual(p, before)
        self.assertEqual(sim.weights(rsi_tree(), D), {"A": 1.0})

    def test_what_if_recomputes_group_track_record(self):
        q = px(N, VOL=path(N, amp=0.05, seed=13), CALM=path(N, amp=0.001, seed=17))
        t = S3Semantics.group_filter(None, "bottom")
        sim, target, _ = sr.run_engine(q, t, D)
        self.assertEqual(target, {"CALM": 1.0})
        # a 60% one-day jump in CALM makes its 20-session SD the larger one
        self.assertEqual(sim.what_if(t, D, "CALM", 0.6), {"VOL": 1.0})

    def test_explain_shows_the_closest_calls(self):
        trace = [{"kind": "cond", "lhs": ("relative-strength-index", "SPY", w), "rhs": None, "op": "lt", "l": l,
                  "r": 25.0, "res": False} for w, l in ((2, 60.0), (3, 25.3), (4, 70.0), (5, 80.0), (6, 26.0))]
        s = sr.explain(trace, 2)
        self.assertIn("RSI(SPY,3) 25.30", s)
        self.assertIn("RSI(SPY,6) 26.00", s)
        self.assertNotIn("RSI(SPY,2)", s)


# ------------------------------------------------------------------ S6
CFG = {"E1": {"symphony": "s1", "eras": [{"version": "v1aaaaaaaa", "from": "2025-01-01", "tree": "t1"}]},
       "E2": {"symphony": "s2", "corridor": 0.10, "eras": [{"version": "v2bbbbbbbb", "from": "2025-01-01", "tree": "t2"}]}}
TREES = {"t1": rsi_tree(), "t2": {"step": "root", "id": "r2", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
    dict(asset("A"), weight={"num": 75, "den": 100}), dict(asset("B"), weight={"num": 25, "den": 100})]}]}}


def load(era):
    return TREES[era["tree"]]


def meta(att1, h1, att2=None, h2=None, paused1=False):
    att2 = att2 or att1
    h2 = h2 or {"A": 0.75, "B": 0.249}
    return [{"id": "s1", "name": "E1", "last_rebalance_attempted_on": att1, "is_paused": paused1,
             "paused_by": "owner" if paused1 else None, "paused_reason": "test" if paused1 else None,
             "holdings": [{"ticker": t, "allocation": w} for t, w in h1.items()]},
            {"id": "s2", "name": "E2", "last_rebalance_attempted_on": att2,
             "holdings": [{"ticker": t, "allocation": w} for t, w in h2.items()]}]


OLD = dates(N)[-4]


class S6Assess(unittest.TestCase):
    def run_(self, h1, bump=0.0003, att=None, att2=None, st=None, prices=None, weekday=1, bars=None, only=None, paused1=False, ld=load):
        st = {} if st is None else st
        p = prices or near_threshold_prices(bump=bump)
        rows, alerts, notes = sr.assess(CFG, meta(att or D, h1, att2, paused1=paused1), p, D, st, load=ld, raw=p,
                                        bars=bars, weekday=weekday, only=only)
        return {r["engine"]: r["status"] for r in rows}, alerts, notes, st

    def test_agree_is_silent(self):
        s, alerts, _, _ = self.run_({"A": 0.999})
        self.assertEqual((s, alerts), ({"E1": "agree", "E2": "agree"}, []))

    def test_mismatch_alerts(self):
        s, alerts, _, _ = self.run_({"B": 0.999}, bump=0.03)
        self.assertEqual(s["E1"], "mismatch")
        self.assertTrue(alerts[0].startswith("SHADOW MISMATCH — E1"))
        self.assertIn("Closest calls: RSI(X,2)", alerts[0])

    def test_no_rebalance_from_composer_record_even_without_prices(self):
        p = near_threshold_prices()
        del p["X"][D], p["A"][D]                      # Yahoo has nothing for E1 or E2 today
        st = {}
        s, a1, _, st = self.run_({"A": 0.999}, att=OLD, prices=p, st=st)
        self.assertEqual(s, {"E1": "no-rebalance", "E2": "no-rebalance"})
        self.assertTrue(a1[0].startswith(f"COMPOSER DID NOT REBALANCE — no rebalance on {D} for E1, E2"))
        self.assertIn("logic unavailable", a1[0])
        _, a2, _, st = self.run_({"A": 0.999}, att=OLD, prices=p, st=st)
        self.assertTrue(a2[0].startswith("COMPOSER STILL NOT REBALANCING — E1 session 2"))
        self.assertFalse(any("RESUMED" in a for a in a2))     # broken: no false resume during an outage
        self.assertEqual(st["frozen"]["E1"]["since"], D)

    def test_per_engine_freeze_and_resume(self):
        st = {}
        s, a1, _, st = self.run_({"A": 0.999}, att=OLD, att2=D, st=st)
        self.assertEqual((s["E1"], s["E2"]), ("no-rebalance", "agree"))
        self.assertIn(f"for E1 (E1 last attempted {OLD})", a1[0])
        _, a2, _, st = self.run_({"A": 0.999}, st=st)
        self.assertTrue(a2[0].startswith(f"COMPOSER REBALANCING RESUMED on {D} — E1 after 1 session(s)"))
        self.assertEqual(st["frozen"], {})

    def test_paused_symphony_mondays_only(self):
        st = {}
        _, a1, _, st = self.run_({"A": 0.999}, att=OLD, att2=D, st=st, paused1=True)
        self.assertIn("paused in Composer", a1[0])
        _, a2, _, st = self.run_({"A": 0.999}, att=OLD, att2=D, st=st, paused1=True, weekday=2)
        self.assertEqual(a2, [])
        _, a3, _, st = self.run_({"A": 0.999}, att=OLD, att2=D, st=st, paused1=True, weekday=0)
        self.assertTrue(a3[0].startswith("COMPOSER STILL NOT REBALANCING — E1 session 3"))

    def test_broken_attempted_today_is_not_frozen(self):
        _, alerts, _, st = self.run_({"A": 0.999})
        self.assertFalse(any("REBALANC" in a for a in alerts))
        self.assertEqual(st["frozen"], {})

    def test_attempted_after_d_is_a_note(self):
        s, alerts, notes, _ = self.run_({"B": 0.999}, bump=0.03, att="2025-05-01")
        self.assertEqual((s["E1"], alerts), ("unavailable", []))
        self.assertTrue(any("attempted 2025-05-01" in n for n in notes))

    def test_search_knife_edge_alerts_on_second_session(self):
        st = {}
        s, a1, _, st = self.run_({"B": 0.999}, st=st)
        self.assertEqual((s["E1"], a1), ("knife-edge", []))
        _, a2, _, st = self.run_({"B": 0.999}, st=st)
        self.assertTrue(a2[0].startswith("SHADOW KNIFE-EDGE x2 — E1"))

    def test_broken_intraday_knife_edges_never_alert(self):
        st = {}
        for _ in range(3):
            s, a, _, st = self.run_({"B": 0.999}, st=st, bars=lambda tk: bars_for(near_threshold_prices(), {"X": -0.002}))
            self.assertEqual((s["E1"], a), ("knife-edge", []))

    def test_unavailable_resets_the_streak(self):
        st = {}
        self.run_({"B": 0.999}, st=st)
        p = near_threshold_prices()
        del p["X"][D]
        self.run_({"B": 0.999}, st=st, prices=p)
        _, a3, _, _ = self.run_({"B": 0.999}, st=st)
        self.assertEqual(a3, [])

    def test_blind_after_three_sessions(self):
        p = near_threshold_prices()
        del p["X"][D]
        st = {}
        for i in range(1, 4):
            s, a, notes, st = self.run_({"A": 0.999}, st=st, prices=p)
            self.assertEqual(s["E1"], "unavailable")
            self.assertEqual(bool(a), i == 3)
        self.assertTrue(a[0].startswith("SHADOW BLIND — E1: no comparison for 3 sessions"))
        _, a4, _, st = self.run_({"A": 0.999}, st=st, prices=p, only={"E1"})   # a re-run is not a new session
        self.assertEqual((a4, st["blind"]["E1"]), ([], 3))

    def test_evaluator_error_is_one_engines(self):
        def bad(era):
            if era["tree"] == "t1":
                raise ZeroDivisionError("edge case")
            return load(era)
        s, alerts, notes, _ = self.run_({"A": 0.999}, ld=bad)
        self.assertEqual(s, {"E1": "unavailable", "E2": "agree"})
        self.assertTrue(any("ZeroDivisionError" in n for n in notes))

    def test_frozen_text_uses_corridor_for_kmlm(self):
        _, alerts, _ = sr.assess(CFG, meta(OLD, {"A": 0.999}, h2={"A": 0.70, "B": 0.30}), near_threshold_prices(), D, {}, load=load)
        self.assertIn("E2 A 75%, B 25%.", alerts[0])
        _, alerts, _ = sr.assess(CFG, meta(OLD, {"A": 0.999}, h2={"A": 0.60, "B": 0.40}), near_threshold_prices(), D, {}, load=load)
        self.assertIn("E2 A 75%, B 25% (frozen at A 60%, B 40%)", alerts[0])


# ------------------------------------------------------------------ S7
class S7Hook(unittest.TestCase):
    NOW = datetime.datetime(2025, 5, 1, 21, 35, tzinfo=UTC)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (sr.load_manifest, sr.load_tree, sr.fetch_prices)
        sr.load_manifest = lambda: CFG
        sr.load_tree = load
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.prices = near_threshold_prices()

    def tearDown(self):
        sr.load_manifest, sr.load_tree, sr.fetch_prices = self.saved
        self.tmp.cleanup()

    def hook(self, state, m, get=None, now=None, bars="none"):
        alerts, snap, out = [], {}, io.StringIO()
        with contextlib.redirect_stdout(out):
            sr.check_shadow(state, alerts, snap, m, now or self.NOW, get=get, ledger=self.ledger,
                            bars=(lambda tk: {}) if bars == "none" else bars)
        return alerts, snap, out.getvalue()

    def ok_prices(self):
        sr.fetch_prices = lambda *a, **k: (self.prices, self.prices, {})

    def test_yahoo_down_still_judges_composer_record(self):
        def boom(*a, **k):
            raise RuntimeError("Yahoo down")
        sr.fetch_prices = boom
        state = {"shadow": {"last_date": "2025-04-29"}}
        alerts, snap, out = self.hook(state, meta(OLD, {"A": 0.999}))
        self.assertIn("session dated 2025-05-01 from the exchange calendar", out)
        self.assertTrue(alerts and alerts[0].startswith("COMPOSER DID NOT REBALANCE — no rebalance on 2025-05-01"))
        self.assertNotIn("fail", state["shadow"])
        self.assertEqual(snap["shadow"]["status"], {"E1": "no-rebalance", "E2": "no-rebalance"})
        # an engine that did rebalance is unchecked, and that counts toward SHADOW BLIND, not a failure
        state = {}
        for day, wd_now in ((1, datetime.datetime(2025, 5, 1, 21, 35, tzinfo=UTC)), (2, datetime.datetime(2025, 5, 2, 21, 35, tzinfo=UTC)),
                            (3, datetime.datetime(2025, 5, 5, 21, 35, tzinfo=UTC))):
            alerts, snap, out = self.hook(state, meta(wd_now.date().isoformat(), {"A": 0.999}), now=wd_now)
        self.assertTrue(any(a.startswith("SHADOW BLIND — E1: no comparison for 3 sessions") for a in alerts))

    def test_manifest_failure_counts_and_alerts_on_third(self):
        self.ok_prices()

        def broken():
            raise ValueError("manifest unreadable")
        sr.load_manifest = broken
        state = {"shadow": {"last_date": "2025-04-29", "frozen": {}}}
        for i in range(1, 4):
            alerts, _, out = self.hook(state, meta(OLD, {"A": 0.999}))
            self.assertIn("shadow runner unavailable: manifest unreadable", out)
            self.assertEqual((state["shadow"]["last_date"], state["shadow"]["frozen"]), ("2025-04-29", {}))
            self.assertEqual(state["shadow"]["fail"]["n"], i)
            self.assertEqual(bool(alerts), i == 3)
        self.assertTrue(alerts[0].startswith("SHADOW RUNNER DOWN — 3 runs"))
        tue = datetime.datetime(2025, 5, 6, 21, 35, tzinfo=UTC)
        self.assertEqual(self.hook(state, meta(OLD, {"A": 0.999}), now=tue)[0], [])            # run 4, a Tuesday
        mon = datetime.datetime(2025, 5, 12, 21, 35, tzinfo=UTC)
        self.assertEqual(len(self.hook(state, meta(OLD, {"A": 0.999}), now=mon)[0]), 1)        # Mondays repeat
        self.assertEqual(self.hook(state, meta(OLD, {"A": 0.999}), now=mon)[0], [])            # once a day
        sr.load_manifest = lambda: CFG
        self.hook(state, meta(D, {"A": 0.999}))
        self.assertNotIn("fail", state["shadow"])

    def test_drift_runs_without_prices_and_survives_one_engine(self):
        def boom(*a, **k):
            raise RuntimeError("Yahoo down")
        sr.fetch_prices = boom
        changed = copy.deepcopy(TREES["t2"])
        changed["children"][0]["children"][0]["weight"] = {"num": 60, "den": 100}

        def get(path):
            if "/s1/" in path:
                raise SystemExit("error: HTTP 401")
            return [{"version_id": "v2new"}] if path.endswith("/versions") else changed
        state = {}
        alerts, _, out = self.hook(state, meta("2025-05-01", {"A": 0.999}), get=get)
        self.assertTrue(alerts and alerts[0].startswith("LOGIC DRIFT — E2"))
        self.assertIn("logic-drift check for E1 unavailable", out)

    def test_malformed_ledger_line_is_skipped(self):
        self.ok_prices()
        with open(self.ledger, "w") as f:
            f.write('{"date":"2025-04-29","engine":"E1","status":"agree"}\n{"date":"2025-04-30","eng')
        state = {}
        alerts, _, out = self.hook(state, meta(OLD, {"A": 0.999}))
        self.assertTrue(alerts and alerts[0].startswith("COMPOSER DID NOT REBALANCE"))
        self.assertEqual(state["shadow"]["last_date"], D)
        self.assertEqual(state["shadow"]["frozen"]["E1"]["sessions"], 1)
        rows = sr.read_ledger(self.ledger)
        self.assertEqual(sorted((r["date"], r["engine"]) for r in rows),
                         [("2025-04-29", "E1"), (D, "E1"), (D, "E2")])
        self.assertEqual([f for f in os.listdir(self.tmp.name) if f.startswith(".shadow-ledger.")], [])

    def test_same_session_not_reassessed_except_unavailable(self):
        self.ok_prices()
        state = {}
        self.hook(state, meta(OLD, {"A": 0.999}))
        alerts, _, out = self.hook(state, meta(OLD, {"A": 0.999}))
        self.assertEqual(alerts, [])
        self.assertIn("nothing re-assessed", out)
        self.assertEqual(state["shadow"]["frozen"]["E1"]["sessions"], 1)
        # E1 unavailable on the first run (X missing), then Yahoo catches up: only E1 is re-assessed
        p = copy.deepcopy(self.prices)
        del p["X"][D]
        sr.fetch_prices = lambda *a, **k: (p, p, {})
        state = {}
        self.hook(state, meta(D, {"A": 0.999}))
        self.assertEqual(state["shadow"]["pending"], ["E1"])
        self.ok_prices()
        _, snap, out = self.hook(state, meta(D, {"A": 0.999}))
        self.assertEqual(snap["shadow"]["status"], {"E1": "agree", "E2": "agree"})   # merged with the first run
        self.assertEqual(state["shadow"]["pending"], [])

    def test_failure_after_assess_keeps_previous_state(self):
        class BadSnap(dict):
            def __setitem__(self, k, v):
                raise RuntimeError("snapshot write failed")
        self.ok_prices()
        state = {"shadow": {"last_date": "2025-04-29", "frozen": {}}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sr.check_shadow(state, [], BadSnap(), meta(OLD, {"A": 0.999}), self.NOW, ledger=self.ledger, bars=lambda tk: {})
        self.assertEqual(state["shadow"]["last_date"], "2025-04-29")      # assess ran, but its changes are dropped
        self.assertEqual(state["shadow"]["frozen"], {})
        self.assertEqual(state["shadow"]["fail"]["n"], 1)

    def test_malformed_meta_is_one_engines(self):
        self.ok_prices()
        m = meta(D, {"A": 0.999})
        m[1]["holdings"] = 5                           # E2's record is garbage
        m[0]["last_rebalance_attempted_on"] = 20250430
        state = {}
        alerts, snap, out = self.hook(state, m)
        self.assertIn("unreadable rebalance-attempt date", out)
        self.assertEqual(snap["shadow"]["status"]["E1"], "unavailable")
        self.assertEqual(snap["shadow"]["status"]["E2"], "mismatch")      # holds nothing: reported, not a crash

    def test_rerun_does_not_advance_a_freeze(self):
        p = copy.deepcopy(self.prices)
        del p["A"][D]                                   # E2 cannot be checked on the first run
        sr.fetch_prices = lambda *a, **k: (p, p, {})
        state = {}
        self.hook(state, meta(OLD, {"A": 0.999}, att2=D))
        self.assertEqual((state["shadow"]["frozen"]["E1"]["sessions"], state["shadow"]["pending"]), (1, ["E2"]))
        self.ok_prices()
        alerts, snap, _ = self.hook(state, meta(OLD, {"A": 0.999}, att2=D))
        self.assertEqual(alerts, [])                    # no STILL NOT REBALANCING from a re-run
        self.assertEqual(state["shadow"]["frozen"]["E1"]["sessions"], 1)
        self.assertEqual(snap["shadow"]["status"], {"E1": "no-rebalance", "E2": "agree"})

    def test_ledger_write_failure_still_delivers_alerts(self):
        self.ok_prices()
        os.makedirs(self.ledger)                       # a directory where the file should be: write fails
        state = {}
        alerts, _, out = self.hook(state, meta(OLD, {"A": 0.999}))
        self.assertTrue(alerts and alerts[0].startswith("COMPOSER DID NOT REBALANCE"))
        self.assertEqual(state["shadow"]["last_date"], D)


# ------------------------------------------------------------------ S8
class S8Drift(unittest.TestCase):
    def setUp(self):
        self.approved = rsi_tree()

    def get_for(self, head, tree):
        def get(path):
            return [{"version_id": head, "created_at": "2026-11-02T10:00:00-05:00"}] if path.endswith("/versions") else tree
        return get

    def drift(self, head, tree, st, when=datetime.datetime(2026, 11, 3, 21, 35, tzinfo=UTC)):
        return sr.check_drift({"E1": CFG["E1"]}, self.get_for(head, tree), st, sr.et_now(when), load=lambda era: self.approved)

    def test_approved_is_silent_and_rename_a_note(self):
        self.assertEqual(self.drift("v1aaaaaaaa", self.approved, {}), ([], []))
        renamed = copy.deepcopy(self.approved)
        renamed.update(name="new name", id="other-id", description="x")
        renamed["children"][0]["children"][0]["children"][0]["collapsed?"] = True
        alerts, notes = self.drift("v9renamed", renamed, {})
        self.assertEqual(alerts, [])
        self.assertTrue(notes and "approved logic (a rename?)" in notes[0])

    def test_changed_logic_alerts_once_then_mondays_and_on_change(self):
        changed = copy.deepcopy(self.approved)
        changed["children"][0]["children"][0]["children"][0]["rhs-val"] = "55"
        st = {}
        a1, _ = self.drift("v9", changed, st)                                         # Tuesday
        self.assertTrue(a1 and a1[0].startswith("LOGIC DRIFT — E1: Composer's live logic (version v9)"))
        self.assertIn("rhs-val: 50.0 -> 55.0", a1[0])
        self.assertEqual(self.drift("v9", changed, st, datetime.datetime(2026, 11, 4, 21, 35, tzinfo=UTC))[0], [])
        mon = datetime.datetime(2026, 11, 9, 21, 35, tzinfo=UTC)
        self.assertEqual(len(self.drift("v9", changed, st, mon)[0]), 1)
        self.assertEqual(self.drift("v9", changed, st, mon)[0], [])                    # once per Monday
        changed["children"][0]["children"][0]["children"][0]["rhs-val"] = "60"
        self.assertEqual(len(self.drift("v9", changed, st, datetime.datetime(2026, 11, 10, 21, 35, tzinfo=UTC))[0]), 1)

    def test_every_logic_field_moves_canonical(self):
        base = {"step": "filter", "id": "f", "sort-by-fn": "relative-strength-index", "sort-by-fn-params": {"window": 10},
                "select-fn": "top", "select-n": "1", "select?": True, "sort-by?": True,
                "children": [dict(asset("A")), asset("B")]}
        c0 = sr.canonical(base)
        for k, v in (("select-n", "2"), ("select-fn", "bottom"), ("sort-by-fn-params", {"window": 20}),
                     ("sort-by-window-days", "20"), ("select?", False), ("sort-by?", False), ("sort-by-fn", "cumulative-return")):
            m = copy.deepcopy(base)
            if v is None:
                m.pop(k)
            else:
                m[k] = v
            self.assertNotEqual(sr.canonical(m), c0, k)
        c = cond("relative-strength-index", "SPY", 10, "gt", 50)
        cc = sr.canonical(c)
        for k, v in (("lhs-val", "QQQ"), ("lhs-fn-params", {"window": 14}), ("lhs-window-days", "14"), ("rhs-val", "55"),
                     ("is-else-condition?", True), ("comparator", "lt"), ("rhs-fixed-value?", False)):
            self.assertNotEqual(sr.canonical(dict(c, **{k: v})), cc, k)
        r = root(asset("A"), rebalance="daily")
        self.assertNotEqual(sr.canonical(r), sr.canonical(dict(r, rebalance="none")))
        self.assertNotEqual(sr.canonical(r), sr.canonical(dict(r, **{"rebalance-corridor-width": 0.1})))
        spec = {"step": "wt-cash-specified", "children": [dict(asset("A"), weight={"num": 50, "den": 100}),
                                                          dict(asset("B"), weight={"num": 50, "den": 100})]}
        spec2 = copy.deepcopy(spec)
        spec2["children"][0]["weight"] = {"num": 60, "den": 100}
        self.assertNotEqual(sr.canonical(spec), sr.canonical(spec2))
        wm = {"step": "group", "children": [asset("A")]}
        self.assertNotEqual(sr.canonical(wm), sr.canonical(dict(wm, **{"weight-method": "fraction"})))

    def test_broken_display_and_number_format_do_not(self):
        a = {"step": "filter", "select-n": "1", "is-else-condition?": False, "name": "x", "id": "1", "exchange": "ARCA",
             "children": [asset("A")]}
        b = {"step": "filter", "select-n": 1, "name": "y", "id": "2", "children": [dict(asset("A"), exchange="NYSE")]}
        self.assertEqual(sr.canonical(a), sr.canonical(b))
        eq1 = {"step": "wt-cash-equal", "children": [dict(asset("A"), weight={"num": 50})]}
        eq2 = {"step": "wt-cash-equal", "children": [dict(asset("A"), weight={"num": 70})]}
        self.assertEqual(sr.canonical(eq1), sr.canonical(eq2))          # ignored weight under equal weighting
        fixed = dict(cond("relative-strength-index", "SPY", 10, "gt", 50), **{"rhs-fn": "relative-strength-index"})
        self.assertEqual(sr.canonical(fixed), sr.canonical(cond("relative-strength-index", "SPY", 10, "gt", 50)))


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
        self.assertNotEqual(sr.canonical(gated), sr.canonical(pre))


# ------------------------------------------------------------------ S10
def chart(dates_, close, adj=None, events=None):
    ts = [int(datetime.datetime.fromisoformat(d + "T13:30:00+00:00").timestamp()) for d in dates_]
    res = {"timestamp": ts, "indicators": {"quote": [{"close": close}], "adjclose": [{"adjclose": adj}] if adj else []}}
    if events:
        res["events"] = events
    return res


class S10Data(unittest.TestCase):
    def setUp(self):
        self.saved = sr._chart

    def tearDown(self):
        sr._chart = self.saved

    def test_fetch_yahoo_uses_adjclose(self):
        sr._chart = lambda url, timeout=30: chart(["2026-10-01", "2026-10-02"], [100.0, 101.0], [98.0, 101.0])
        adj, raw = sr.fetch_yahoo("X")
        self.assertEqual((adj["2026-10-01"], raw["2026-10-01"]), (98.0, 100.0))

    def test_lagging_dividend_is_applied(self):
        ts = int(datetime.datetime.fromisoformat("2026-10-02T13:30:00+00:00").timestamp())
        ev = {"dividends": {str(ts): {"amount": 2.0, "date": ts}}}
        sr._chart = lambda url, timeout=30: chart(["2026-10-01", "2026-10-02"], [100.0, 99.0], [100.0, 99.0], ev)
        adj, _ = sr.fetch_yahoo("X")
        self.assertAlmostEqual(adj["2026-10-01"], 98.0)                     # 100 x (1 - 2/100)
        sr._chart = lambda url, timeout=30: chart(["2026-10-01", "2026-10-02"], [100.0, 99.0], [98.0, 99.0], ev)
        adj, _ = sr.fetch_yahoo("X")                                         # broken: already applied, unchanged
        self.assertAlmostEqual(adj["2026-10-01"], 98.0)

    def test_lagging_reverse_split_is_applied(self):
        ts = int(datetime.datetime.fromisoformat("2026-10-02T13:30:00+00:00").timestamp())
        ev = {"splits": {str(ts): {"numerator": 1, "denominator": 10, "date": ts}}}
        sr._chart = lambda url, timeout=30: chart(["2026-10-01", "2026-10-02"], [5.0, 51.0], [5.0, 51.0], ev)
        adj, raw = sr.fetch_yahoo("X")
        self.assertAlmostEqual(adj["2026-10-01"], 50.0)
        sr._chart = lambda url, timeout=30: chart(["2026-10-01", "2026-10-02"], [50.0, 51.0], [50.0, 51.0], ev)
        adj, raw = sr.fetch_yahoo("X")                                       # broken: already split-adjusted
        self.assertAlmostEqual(adj["2026-10-01"], 50.0)

    def test_fetch_prices_cut_at_final_close(self):
        saved = sr.fetch_yahoo
        sr.fetch_yahoo = lambda t, rng="2y": ({"2026-07-14": 1.0, "2026-07-15": 2.0}, {"2026-07-14": 1.0, "2026-07-15": 2.0})
        try:
            before = sr.fetch_prices(["X"], datetime.datetime(2026, 7, 15, 20, 14, tzinfo=UTC))[0]["X"]
            after = sr.fetch_prices(["X"], datetime.datetime(2026, 7, 15, 20, 15, tzinfo=UTC))[0]["X"]
        finally:
            sr.fetch_yahoo = saved
        self.assertEqual((sorted(before), sorted(after)), (["2026-07-14"], ["2026-07-14", "2026-07-15"]))

    def test_bar_price(self):
        b = {"15:40": 10.0, "15:45": 11.0, "15:50": 12.0}
        self.assertEqual(sr.bar_price(b, "15:50"), 11.0)      # the bar 15:45-15:50
        self.assertEqual(sr.bar_price(b, "15:55"), 12.0)
        self.assertEqual(sr.bar_price({"15:40": 10.0}, "15:55"), 10.0)
        self.assertIsNone(sr.bar_price({}, "15:50"))

    def test_et_fallback_matches_zoneinfo(self):
        import zoneinfo
        ny = zoneinfo.ZoneInfo("America/New_York")
        for s in ("2026-03-08T06:59", "2026-03-08T07:00", "2026-11-01T05:59", "2026-11-01T06:00", "2026-07-15T20:15",
                  "2026-12-15T21:15", "2027-03-14T07:30"):
            t = datetime.datetime.fromisoformat(s + ":00+00:00")
            self.assertEqual(sr._et_fallback(t).replace(tzinfo=None), t.astimezone(ny).replace(tzinfo=None), s)

    def test_final_through_boundary(self):
        for hm_utc, day in (((20, 14), datetime.date(2026, 7, 15)), ((21, 14), datetime.date(2026, 12, 15))):
            before = datetime.datetime(day.year, day.month, day.day, *hm_utc, tzinfo=UTC)
            self.assertEqual(sr.final_through(before), day - datetime.timedelta(days=1))
            self.assertEqual(sr.final_through(before + datetime.timedelta(minutes=1)), day)

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
        w = sr.live_weights({"holdings": [{"ticker": "A", "allocation": 0.5}, {"ticker": "B", "allocation": 0.499},
                                          {"ticker": "C", "allocation": 0.0}]})
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)
        self.assertNotIn("C", w)
        self.assertEqual(sr.live_weights({"holdings": []}), {})

    def test_eras(self):
        cfg = {"eras": [{"from": "2026-06-30", "v": 1}, {"from": "2026-07-31", "v": 2}, {"from": "2026-10-19", "v": 3}]}
        self.assertEqual(sr.era_for(cfg, "2026-07-30")["v"], 1)
        self.assertEqual(sr.era_for(cfg, "2026-07-31")["v"], 2)
        self.assertIsNone(sr.era_for(cfg, "2026-06-29"))
        self.assertEqual([e["v"] for e in sr.eras_between(cfg, "2026-10-12", "2026-10-22")], [2, 3])
        self.assertEqual([e["v"] for e in sr.eras_between(cfg, "2026-10-20", "2026-10-22")], [3])



# ------------------------------------------------------------------ S11 (round-2 survivors)
def timed_bars(p, moves_at, day=D, close="16:00"):
    """bars for every ticker at its close, except X, moved by moves_at[hh:mm] in the bar ending at that minute"""
    times = sr.decision_times(close)
    out = {}
    for t, s in p.items():
        b = {}
        for i in range(-6, 1):
            hh = sr._hm(sr._min(close) - 5 + 5 * i)
            b[hh] = s[day]
        if t == "X":
            for hh, mv in moves_at.items():
                b[sr._hm(sr._min(hh) - 5)] = s[day] * (1 + mv)
        b["_close"] = close
        out[t] = {day: b}
    return out


class S11Intraday(unittest.TestCase):
    def classify(self, live, bars, tree=None, corridor=None, drifted=None, prices=None, raw=None):
        p = prices or near_threshold_prices()
        tree = tree or rsi_tree()
        sim, target, tr = sr.run_engine(p, tree, D)
        intraday = lambda: sr.at_times(p, raw or {t: dict(s) for t, s in p.items()}, bars, tree, D)  # noqa: E731
        return target, sr.classify(sim, tree, D, target, tr, live, corridor, drifted, intraday)

    def test_each_decision_minute_is_tried(self):
        for hh in ("15:45", "15:50", "15:55"):
            _, (status, det) = self.classify({"B": 1.0}, timed_bars(near_threshold_prices(), {hh: -0.002}))
            self.assertEqual((status, det["edge"]["time"]), ("knife-edge", hh), hh)

    def test_half_day_uses_its_own_close(self):
        bars = timed_bars(near_threshold_prices(), {"12:50": -0.002}, close="13:00")
        self.assertEqual(sr.decision_times("13:00"), ("12:45", "12:50", "12:55"))
        _, (status, det) = self.classify({"B": 1.0}, bars)
        self.assertEqual((status, det["edge"]["time"]), ("knife-edge", "12:50"))
        for b in bars.values():                                   # broken: treated as a 16:00 close
            b[D].pop("_close")
        _, (status, _) = self.classify({"B": 1.0}, bars)
        self.assertEqual(status, "knife-edge")                    # stale 12:5x bars -> no bars -> fallback search
        self.assertIsNone(sr.at_times(near_threshold_prices(), near_threshold_prices(), bars, rsi_tree(), D))

    def test_intraday_prices_are_scaled_onto_the_adjusted_series(self):
        p = near_threshold_prices()
        adj = {t: {d: v / 2 for d, v in s.items()} for t, s in p.items()}       # adjusted = half the raw price
        bars = timed_bars(p, {"15:50": -0.002})                                  # raw-price bars
        sim, target, tr = sr.run_engine(adj, rsi_tree(), D)
        status, det = sr.classify(sim, rsi_tree(), D, target, tr, {"B": 1.0}, None, None,
                                  lambda: sr.at_times(adj, p, bars, rsi_tree(), D))
        self.assertEqual((status, det["edge"]["time"]), ("knife-edge", "15:50"))

    def test_missing_bars_for_a_decision_ticker_fall_back_to_search(self):
        bars = timed_bars(near_threshold_prices(), {"15:50": -0.002})
        del bars["X"]
        _, (status, det) = self.classify({"B": 1.0}, bars)
        self.assertEqual((status, det["edge"]["basis"]), ("knife-edge", "search"))

    def test_held_only_tickers_need_no_bars(self):
        bars = timed_bars(near_threshold_prices(), {"15:50": -0.002})
        del bars["A"], bars["B"]                              # held, never read by a condition
        _, (status, det) = self.classify({"B": 1.0}, bars)
        self.assertEqual((status, det["edge"]["basis"]), ("knife-edge", "intraday"))

    def test_stale_bars_are_missing(self):
        b = {"13:00": 10.0, "15:40": 11.0}
        self.assertIsNone(sr.bar_price({"13:00": 10.0}, "15:50"))
        self.assertEqual(sr.bar_price(b, "15:50"), 11.0)
        self.assertEqual(sr.bar_price({"15:20": 9.0}, "15:50"), 9.0)          # 25 minutes: still fresh
        self.assertIsNone(sr.bar_price({"15:05": 9.0}, "15:50"))              # 40 minutes: stale

    def test_intraday_check_keeps_the_corridor_path(self):
        tree = {"step": "root", "id": "r", "children": [{"step": "wt-cash-specified", "id": "s", "children": [
            dict(if_(cond("relative-strength-index", "X", 2, "gt", 50), [asset("A")], [asset("B")]), weight={"num": 75}),
            dict(asset("C"), weight={"num": 25})]}]}
        drifted = {"B": 0.70, "C": 0.30}                       # yesterday's holdings at today's close
        live = {"B": 0.75, "C": 0.25}                          # Composer rebalanced inside the corridor: wrong
        _, (status, _) = self.classify(live, timed_bars(near_threshold_prices(), {"15:50": -0.002}), tree=tree,
                                       corridor=0.10, drifted=drifted)
        self.assertEqual(status, "mismatch")
        _, (status, _) = self.classify(drifted, timed_bars(near_threshold_prices(), {"15:50": -0.002}), tree=tree,
                                       corridor=0.10, drifted=drifted)
        self.assertEqual(status, "knife-edge")                 # broken pair: Composer held the drifted weights

    def test_fallback_radius_boundary(self):
        _, (status, det) = S5Classify._classify(None, flip_bump(0.31), {"B": 1.0})
        self.assertEqual(status, "mismatch")                   # 0.31 sigma is outside 0.3 (and inside 0.4)


class S12Corridor(unittest.TestCase):
    def test_tolerance_and_ambiguity_band(self):
        t = {"A": 0.75, "B": 0.25}
        near = {"A": 0.70, "B": 0.30}
        self.assertTrue(sr.agrees(t, {"A": 0.714, "B": 0.286}, 0.10, near))      # 1.4% from the drifted weights
        self.assertFalse(sr.agrees(t, {"A": 0.716, "B": 0.284}, 0.10, near))     # 1.6%
        band = {"A": 0.655, "B": 0.345}                                         # 9.5pp: inside the band
        self.assertTrue(sr.agrees(t, t, 0.10, band) and sr.agrees(t, band, 0.10, band))

    def test_deposit_in_flight_means_lenient(self):
        p = {"A": {"d0": 100.0, "d1": 100.0}, "B": {"d0": 100.0, "d1": 100.0}, "SPY": {"d0": 1, "d1": 1}}
        cfg = {"corridor": 0.1}
        row = {"date": "d0", "live": {"A": 0.5, "B": 0.5}, "net_deposits": 1000, "cash_share": 0.001}
        s = {"net_deposits": 1000, "value": 1000.0, "cash": 1.0}
        self.assertIsNotNone(sr.corridor_base(cfg, row, s, p, "d1"))
        for bad_row, bad_s in ((dict(row, deposit_moved=True), s), (dict(row, queued=True), s),
                               (dict(row, cash_share=0.05), s), (row, dict(s, has_queued_deploy=True)),
                               (row, dict(s, cash=50.0))):
            self.assertIsNone(sr.corridor_base(cfg, bad_row, bad_s, p, "d1"))

    def test_rows_record_what_the_guard_reads(self):
        m = meta(D, {"A": 0.999})
        m[1].update(net_deposits=5000.0, cash=10.0, value=1000.0, has_queued_deploy=True)
        prev = {"E2": {"date": D0, "engine": "E2", "live": {"A": 0.75, "B": 0.25}, "net_deposits": 4000.0}}
        p = near_threshold_prices()
        rows, _, _ = sr.assess(CFG, m, p, D, {}, load=load, raw=p, prev=prev)
        e2 = next(r for r in rows if r["engine"] == "E2")
        self.assertEqual((e2["net_deposits"], e2["queued"], e2["cash_share"], e2["deposit_moved"], e2["corridor_check"]),
                         (5000.0, True, 0.01, True, "lenient"))


class S13Wiring(unittest.TestCase):
    NOW = datetime.datetime(2025, 5, 1, 21, 35, tzinfo=UTC)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (sr.load_manifest, sr.load_tree, sr.fetch_prices, sr.fetch_intraday)
        sr.load_manifest = lambda: CFG
        sr.load_tree = load
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.p = near_threshold_prices()
        sr.fetch_prices = lambda *a, **k: (self.p, self.p, {})

    def tearDown(self):
        sr.load_manifest, sr.load_tree, sr.fetch_prices, sr.fetch_intraday = self.saved
        self.tmp.cleanup()

    def run_hook(self, m, bars=None):
        alerts, snap = [], {}
        with contextlib.redirect_stdout(io.StringIO()):
            sr.check_shadow({}, alerts, snap, m, self.NOW, ledger=self.ledger, bars=bars)
        return {r["engine"]: r for r in sr.read_ledger(self.ledger) if r["date"] == D}

    def test_daily_path_fetches_bars_itself(self):
        b = timed_bars(self.p, {"15:50": -0.002})
        calls = []

        def fake(t, rng="5d"):
            calls.append(t)
            return b.get(t, {})
        sr.fetch_intraday = fake
        rows = self.run_hook(meta(D, {"B": 0.999}))
        self.assertEqual((rows["E1"]["status"], rows["E1"]["edge"]["basis"]), ("knife-edge", "intraday"))
        self.assertIn("X", calls)

    def test_previous_row_feeds_the_corridor_path(self):
        def seed(date):
            sr.write_ledger([{"date": date, "engine": "E2", "live": {"A": 0.75, "B": 0.25}, "status": "agree"}], self.ledger)
        seed(D0)
        self.assertEqual(self.run_hook(meta(D, {"A": 0.999}))["E2"]["corridor_check"], "path")
        os.remove(self.ledger)
        seed(dates(N)[-3])                                     # two sessions back: not usable
        self.assertEqual(self.run_hook(meta(D, {"A": 0.999}))["E2"]["corridor_check"], "lenient")
        os.remove(self.ledger)
        seed(D)                                                # the session itself: not the previous one
        self.assertEqual(self.run_hook(meta(D, {"A": 0.999}))["E2"]["corridor_check"], "lenient")


class S14Freeze(unittest.TestCase):
    def assess(self, m, st, weekday=1):
        p = near_threshold_prices()
        return sr.assess(CFG, m, p, D, st, load=load, raw=p, weekday=weekday)

    def test_missing_attempt_date_never_ends_a_freeze(self):
        st = {}
        self.assess(meta(OLD, {"A": 0.999}, att2=D), st)       # only E1 frozen
        m = meta(D, {"A": 0.999})
        m[0]["last_rebalance_attempted_on"] = None
        rows, alerts, _ = self.assess(m, st)
        self.assertEqual(rows[0]["status"], "no-rebalance")
        self.assertTrue(alerts[0].startswith("COMPOSER STILL NOT REBALANCING — E1 session 2"))
        self.assertFalse(any("RESUMED" in a for a in alerts))

    def test_paused_counts_even_with_a_fresh_attempt(self):
        rows, alerts, _ = self.assess(meta(D, {"A": 0.999}, paused1=True), {})
        self.assertEqual((rows[0]["status"], rows[0]["paused"]), ("no-rebalance", True))
        self.assertIn("E1 is paused in Composer (owner: test)", alerts[0])

    def test_engine_missing_from_composer_goes_blind(self):
        st = {}
        for i in range(1, 4):
            rows, alerts, _ = self.assess(meta(D, {"A": 0.999})[1:], st)
            self.assertEqual(rows[0]["note"], "not in Composer's symphony list")
        self.assertTrue(alerts[0].startswith("SHADOW BLIND — E1: no comparison for 3 sessions"))

    def test_blind_resets_and_repeats_on_mondays(self):
        p = near_threshold_prices()
        del p["X"][D]
        st = {}
        for prices in (p, p, near_threshold_prices(), p):
            rows, alerts, _ = sr.assess(CFG, meta(D, {"A": 0.999}), prices, D, st, load=load, raw=prices)
        self.assertEqual(alerts, [])                           # the agree session in between reset it
        for wd in (1, 1, 1, 0):
            rows, alerts, _ = sr.assess(CFG, meta(D, {"A": 0.999}), p, D, st, load=load, raw=p, weekday=wd)
        self.assertEqual(st["blind"]["E1"], 5)
        self.assertTrue(alerts and alerts[0].startswith("SHADOW BLIND — E1: no comparison for 5 sessions"))


class S15Data(unittest.TestCase):
    def setUp(self):
        self.saved = (sr._chart, sr.fetch_intraday)

    def tearDown(self):
        sr._chart, sr.fetch_intraday = self.saved

    def test_fetch_intraday_keys_bars_in_et_with_the_session_close(self):
        start = int(datetime.datetime(2026, 11, 27, 12, 45, tzinfo=sr.et_now(datetime.datetime(2026, 11, 27, 17, 0, tzinfo=UTC)).tzinfo).timestamp())
        ts = [start, start + 300, start + 600, start + 900]                   # 12:45 .. 13:00 ET on a half-day
        end = start + 900
        res = {"timestamp": ts, "indicators": {"quote": [{"close": [1.0, None, 2.0, 3.0]}]},
               "meta": {"tradingPeriods": [[{"start": end - 3.5 * 3600, "end": end}]]}}
        sr._chart = lambda url, timeout=30: res
        b = sr.fetch_intraday("X")["2026-11-27"]
        self.assertEqual(b, {"12:45": 1.0, "12:55": 2.0, "13:00": 3.0, "_close": "13:00"})
        res["timestamp"], res["indicators"]["quote"][0]["close"] = [start - 900], [1.0]   # thin: last bar 12:30
        self.assertEqual(sr.fetch_intraday("X")["2026-11-27"]["_close"], "13:00")         # the exchange's close
        res["timestamp"], res["indicators"]["quote"][0]["close"] = ts, [1.0, None, 2.0, 3.0]
        res["meta"] = {}                                                      # inferred: the 13:00 auction bar
        self.assertEqual(sr.fetch_intraday("X")["2026-11-27"]["_close"], "13:00")
        res["timestamp"], res["indicators"]["quote"][0]["close"] = ts[:3], [1.0, None, 2.0]
        self.assertEqual(sr.fetch_intraday("X")["2026-11-27"]["_close"], "13:00")   # last bar 12:55 ends at 13:00

    def test_bars_fetcher_dates_thin_funds_by_spy(self):
        def fake(t, rng="5d"):
            return {"2026-11-27": {"12:50": 1.0, "_close": "13:00"}} if t == "SPY" else {"2026-11-27": {"11:00": 2.0}}
        sr.fetch_intraday = fake
        got = sr.bars_fetcher()(["ZVOL"])
        self.assertEqual(got["ZVOL"]["2026-11-27"]["_close"], "13:00")
        self.assertNotIn("SPY", got)

    def test_expected_session_skips_weekends_and_holidays(self):
        self.assertEqual(sr.expected_session(datetime.datetime(2026, 10, 31, 22, 0, tzinfo=UTC)), "2026-10-30")   # Saturday
        self.assertEqual(sr.expected_session(datetime.datetime(2026, 11, 26, 22, 0, tzinfo=UTC)), "2026-11-25")   # Thanksgiving
        self.assertEqual(sr.expected_session(datetime.datetime(2026, 11, 27, 22, 0, tzinfo=UTC)), "2026-11-27")

    def test_ledger_write_is_atomic_and_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "l.jsonl")
            sr.write_ledger([{"date": "2026-10-01", "engine": "HG", "status": "agree"}], p)
            def text():
                with open(p) as f:
                    return f.read()
            before = text()
            with self.assertRaises(TypeError):
                sr.write_ledger([{"date": "2026-10-02", "engine": "HG", "bad": object()}], p)
            self.assertEqual(text(), before)                                   # a crash mid-write leaves it whole
            self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o644")
            with open(p, "a") as f:
                f.write('{"date":null,"engine":"HG"}\n{"date":"2026-10-03","engine":7}\n')
            self.assertEqual(len(sr.read_ledger(p)), 1)                        # untyped rows skipped
            sr.write_ledger([{"date": "2026-10-02", "engine": "HG", "status": "agree"}], p)
            self.assertEqual(len(sr.read_ledger(p)), 2)
            good = text()
            real_open = open

            def failing_open(f, *a, **k):
                if f == p:
                    raise PermissionError("read refused")
                return real_open(f, *a, **k)
            sr.open = failing_open
            try:
                self.assertEqual(sr.read_ledger(p), [])
                with self.assertRaises(PermissionError):
                    sr.write_ledger([{"date": "2026-10-05", "engine": "HG"}], p)
            finally:
                del sr.open
            self.assertEqual(text(), good)                                    # history intact
            unreadable = os.path.join(tmp, "dir.jsonl")
            os.makedirs(unreadable)                                            # an I/O error even root gets
            self.assertEqual(sr.read_ledger(unreadable), [])
            with self.assertRaises(OSError):
                sr.write_ledger([{"date": "2026-10-04", "engine": "HG"}], unreadable)   # never rewrite an unread history

    def test_duplicate_holdings_are_summed(self):
        w = sr.live_weights({"holdings": [{"ticker": "A", "allocation": 0.25}, {"ticker": "A", "allocation": 0.25},
                                          {"ticker": "B", "allocation": 0.5}]})
        self.assertEqual(w, {"A": 0.5, "B": 0.5})


class S16Canonical(unittest.TestCase):
    def test_equal_forms(self):
        c = cond("relative-strength-index", "SPY", 10, "gt", 50)
        moved = dict(c)
        moved.pop("lhs-fn-params")
        moved["lhs-window-days"] = "10"
        self.assertEqual(sr.canonical(c), sr.canonical(moved))                 # same window, other field
        f = {"step": "filter", "sort-by-fn": "relative-strength-index", "sort-by-fn-params": {"window": 10},
             "select-fn": "top", "select-n": 1, "children": [asset("A")]}
        self.assertEqual(sr.canonical(f), sr.canonical(dict(f, **{"select?": True, "sort-by?": True})))
        self.assertNotEqual(sr.canonical(f), sr.canonical(dict(f, **{"select?": False})))
        w1 = {"step": "wt-cash-specified", "children": [dict(asset("A"), weight={"num": 50}), dict(asset("B"), weight={"num": 50})]}
        w2 = {"step": "wt-cash-specified", "children": [dict(asset("A"), weight={"num": 30}), dict(asset("B"), weight={"num": 30})]}
        self.assertEqual(sr.canonical(w1), sr.canonical(w2))                   # same shares

    def test_non_window_params_count(self):
        c = cond("relative-strength-index", "SPY", 10, "gt", 50)
        c["lhs-fn-params"] = {"window": 10, "smoothing": 2}             # a parameter a future indicator might take
        self.assertNotEqual(sr.canonical(c), sr.canonical(dict(c, **{"lhs-fn-params": {"window": 10, "smoothing": 3}})))

    def test_same_version_with_edited_logic_alerts(self):
        changed = rsi_tree()
        changed["children"][0]["children"][0]["children"][0]["rhs-val"] = "55"
        get = lambda path: [{"version_id": "v1aaaaaaaa"}] if path.endswith("/versions") else changed  # noqa: E731
        alerts, _ = sr.check_drift({"E1": CFG["E1"]}, get, {}, sr.et_now(datetime.datetime(2026, 11, 3, 21, 35, tzinfo=UTC)),
                                   load=lambda era: rsi_tree())
        self.assertTrue(alerts and alerts[0].startswith("LOGIC DRIFT — E1"))

    def test_drift_check_failures_go_blind_once_a_day(self):
        def get(path):
            raise SystemExit("error: HTTP 503")
        st = {}
        days = [datetime.datetime(2026, 11, d, 21, 35, tzinfo=UTC) for d in (3, 3, 4, 5)]
        out = [sr.check_drift({"E1": CFG["E1"]}, get, st, sr.et_now(t), load=lambda era: rsi_tree())[0] for t in days]
        self.assertEqual([len(a) for a in out], [0, 0, 0, 1])                 # a re-run the same day does not count
        self.assertTrue(out[-1][0].startswith("SHADOW BLIND — E1: the logic-drift check failed on 3 days"))


if __name__ == "__main__":
    unittest.main()
