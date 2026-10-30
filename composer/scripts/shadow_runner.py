#!/usr/bin/env python3
"""Shadow decision runner for the live Composer symphonies (results.md addendum 48).

Every session it works out what each symphony's APPROVED logic says to hold, on independent prices
(Yahoo adjusted closes), and compares that with what Composer actually holds. Read-only toward
Composer (GET only), holds no broker key, never trades or edits a symphony.

It catches what Composer's own numbers cannot show:
  - Composer stops rebalancing (2026-10-26..28: three sessions with no rebalance attempt, seen at
    the time only as API errors)
  - Composer runs logic other than what was approved (an unapproved edit, or an edit that failed
    silently: the 2026-07-30 PUT-wrapper bug returned success and changed nothing)
  - a rule is read differently here than in Composer (data or semantics)
and its ledger is the running proof that the rules reproduce outside Composer, the precondition
for running them anywhere else (IBKR).

Per engine, for session D (the latest final close on Yahoo):
  no-rebalance  Composer made no rebalance attempt on D, or the symphony is paused in Composer. Read
                from Composer's own record alone (when Yahoo is down the session is dated from the
                exchange calendar), so no price outage can hide or end it; a missing attempt date never
                ends it. Alerts on the first session, daily while it lasts (Mondays only for a paused
                symphony), once when it resumes
  agree         Composer holds what the approved logic says: daily engines within 3% (half the L1
                distance between weight vectors). KMLM (threshold corridor 10%): within 1.5% of the
                corridor path, i.e. the target if the previous session's holdings drifted to D's
                closes sit more than 10pp off it, else those drifted holdings; without a previous
                session, every holding within 11pp of the target
  knife-edge    not on closing prices, but yes when every decision ticker's close on D is replaced by
                its price 15, 10 or 5 minutes before the session close (15:45/15:50/15:55; 12:45..
                on a half-day; Yahoo 5-minute bars, none older than 30 minutes): Composer decides on
                prices from those minutes. Logged, not alerted. Without bars, a one-ticker move within
                0.3 sigma counts instead (p95 of the measured 15:45 -> close move), and two such
                sessions in a row for one engine alert
  mismatch      neither explains it -> alert
  unavailable   prices missing, a data gap, the symphony missing from Composer's list, or logic the
                shadow has not been validated on -> note; three sessions in a row for one engine ->
                SHADOW BLIND alert (then Mondays); likewise three days of failed logic-drift checks
LOGIC DRIFT, every run, with or without prices: Composer's live tree differs in logic from the last
approved era in fixtures/approved/manifest.json -> alert when first seen or changed, and on Mondays
while it lasts; a new version with identical logic is a note. Three failed runs in a row -> SHADOW
RUNNER DOWN. A failed run leaves the state as it was; only its failure count moves.

Evaluation semantics: research/synth/tree_sim.py (validated against Composer on these trees) with
Wilder RSI over all fetched history (at least 60 closes). Weights decided at the close of D from
data through D. Ledger: composer/results/monitor/shadow-ledger.jsonl, one line per engine and session.

Usage: shadow_runner.py     today's comparison, printed; state and ledger untouched
"""
import concurrent.futures
import copy
import datetime
import hashlib
import json
import math
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APPROVED = os.path.join(HERE, "..", "fixtures", "approved")
LEDGER = os.path.join(HERE, "..", "results", "monitor", "shadow-ledger.jsonl")

DEFAULT_W = 10
RSI_MIN = 60              # Wilder RSI over all fetched history; at least 60 closes
TOL_DAILY = 0.03          # agree: half-L1 distance between target and live weights (daily engines)
TOL_PATH = 0.015          # KMLM: live vs the corridor path's expected weights (half-L1)
CORRIDOR_SLACK = 0.01     # KMLM: trigger ambiguity band; lenient check without a previous session
KNIFE_OFFSETS = (15, 10, 5)   # minutes before the session close (15:45/15:50/15:55; 12:45.. on half-days)
KNIFE_TIMES = ("15:45", "15:50", "15:55")    # the offsets on a normal day
STALE_BAR_MIN = 30        # a 5-minute bar older than this before the decision time counts as missing
KNIFE_SIGMA = 0.3         # fallback search radius without bars, in 20-session daily sigmas: p95 of the
                          # measured 15:45 ET -> official close move (add. 48 calibration)
CASH_SHARE_MAX = 0.02     # KMLM: uninvested cash above this (a deposit in flight) -> lenient check
NYSE_HOLIDAYS = {         # sessions Composer cannot rebalance; used only to date a run when Yahoo is down
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
SUB_WARMUP = 60           # sessions of filter sub-tree history before the first decision
FINAL_AFTER = (16, 15)    # ET: a session's close counts as final from 16:15
STREAK_ALERT = 2          # unexplained (search-basis) knife-edges in a row before an alert
BLIND_ALERT = 3           # sessions an engine is unavailable, or runs the runner fails, before an alert
DISPLAY = {"id", "name", "description", "collapsed?", "exchange", "has_marketcap", "asset_class",
           "asset_classes"}   # fields that never change what a tree holds
FNS = {"current-price", "moving-average-price", "cumulative-return", "standard-deviation-return",
       "relative-strength-index"}
STEPS = {"root", "group", "wt-cash-equal", "wt-cash-specified", "if", "if-child", "filter", "asset"}
OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b}
SHORT = {"relative-strength-index": "RSI", "moving-average-price": "MA", "cumulative-return": "CR",
         "standard-deviation-return": "SD", "current-price": "price"}
ORDER = ("HG", "KMLM", "SLEEVE", "HARV")


class Unsupported(Exception):
    """the tree uses a step, indicator or comparator the shadow has not been validated on"""


class DataGap(Exception):
    """an indicator on the decision path has no value (missing or too-short history)"""


# ------------------------------------------------------------------ evaluator
def window(node, side):
    """indicator window: newer nodes keep it in <side>-fn-params.window, older ones in
    <side>-window-days (API.md); Composer's default is 10. Both present and different ->
    Unsupported (which one Composer reads is not known)."""
    p = (node.get(f"{side}-fn-params") or {}).get("window")
    wd = node.get(f"{side}-window-days")
    if p not in (None, "") and wd not in (None, "") and int(float(p)) != int(float(wd)):
        raise Unsupported(f"{side} window: fn-params {p} vs window-days {wd}")
    w = p if p not in (None, "") else wd
    return int(float(w)) if w not in (None, "") else DEFAULT_W


def indicator(fn, s, w):
    """fn over closes s (oldest first, s[-1] = the decision day); None if the history is too short.
    Returns in percent, as Composer's conditions read them."""
    if fn == "current-price":
        return s[-1] if s else None
    if fn == "moving-average-price":
        return sum(s[-w:]) / w if len(s) >= w else None
    if fn == "cumulative-return":
        return (s[-1] / s[-1 - w] - 1) * 100 if len(s) > w else None
    if fn == "standard-deviation-return":
        if len(s) <= w:
            return None
        r = [s[i] / s[i - 1] - 1 for i in range(len(s) - w, len(s))]
        m = sum(r) / w
        return math.sqrt(sum((x - m) ** 2 for x in r) / w) * 100
    if fn == "relative-strength-index":
        if len(s) - 1 < max(RSI_MIN, w + 1):
            return None
        d = [s[i] - s[i - 1] for i in range(1, len(s))]
        ag = sum(max(x, 0) for x in d[:w]) / w
        al = sum(max(-x, 0) for x in d[:w]) / w
        for x in d[w:]:
            ag = (ag * (w - 1) + max(x, 0)) / w
            al = (al * (w - 1) + max(-x, 0)) / w
        return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    raise Unsupported(f"indicator {fn}")


def weight_of(node):
    x = node.get("weight")
    if isinstance(x, dict):
        return float(x["num"]) / float(x.get("den", 100))
    return float(x or 0)


def filter_groups(tree):
    """{id: node} for every non-asset child of a filter: these are ranked on their own simulated
    track record, which the evaluator keeps in Shadow.sub"""
    out = {}

    def walk(n):
        if n.get("step") == "filter":
            for k in n.get("children") or []:
                if k.get("step") != "asset":
                    out[k["id"]] = k
        for k in n.get("children") or []:
            walk(k)
    walk(tree)
    return out


def tree_tickers(tree):
    out = set()

    def walk(n):
        if n.get("step") == "asset":
            out.add(n["ticker"])
        if n.get("lhs-fn"):
            out.add(n["lhs-val"])
            if not n.get("rhs-fixed-value?"):
                out.add(n["rhs-val"])
        for k in n.get("children") or []:
            walk(k)
    walk(tree)
    return out


def validate(tree):
    """raise Unsupported if any branch (visited today or not) uses a step, indicator, comparator,
    window encoding or group metric the evaluator has not been validated on"""
    def walk(n):
        if n.get("step") not in STEPS:
            raise Unsupported(f"step {n.get('step')}")
        if n.get("lhs-fn"):
            if n.get("comparator") not in OPS:
                raise Unsupported(f"comparator {n.get('comparator')}")
            if not n.get("rhs-fixed-value?") and not n.get("rhs-fn"):
                raise Unsupported("comparison against a ticker without rhs-fn")
            for fn in (n["lhs-fn"], None if n.get("rhs-fixed-value?") else n.get("rhs-fn")):
                if fn and fn not in FNS:
                    raise Unsupported(f"indicator {fn}")
            window(n, "lhs")
            if not n.get("rhs-fixed-value?"):
                window(n, "rhs")
        if n.get("step") == "filter":
            if n.get("sort-by-fn") not in FNS:
                raise Unsupported(f"indicator {n.get('sort-by-fn')}")
            if n.get("select-fn") not in ("top", "bottom"):
                raise Unsupported(f"select-fn {n.get('select-fn')}")
            window(n, "sort-by")
            if any(k.get("step") != "asset" for k in n.get("children") or []) and \
                    n["sort-by-fn"] not in ("standard-deviation-return", "cumulative-return"):
                raise Unsupported(f"filter on a group by {n['sort-by-fn']}")
        for k in n.get("children") or []:
            walk(k)
    walk(tree)


def norm(w):
    tot = sum(w.values())
    return {t: round(x / tot, 6) for t, x in sorted(w.items()) if tot and x / tot > 1e-6}


class Shadow:
    """Composer tree evaluator on daily closes. prices: {ticker: {date: adjusted close}}."""

    def __init__(self, prices):
        self.p = prices
        self.days = {t: sorted(s) for t, s in prices.items()}
        self.pos = {t: {d: i for i, d in enumerate(ds)} for t, ds in self.days.items()}
        self.cache, self.sub = {}, {}
        self.trace, self.strict = None, False
        self.bump, self.overlay = None, {}      # what_if: (ticker, day) whose close is moved

    def closes(self, t, d, k=None):
        """closes of t up to and including d: the last k, or all of them"""
        i = self.pos.get(t, {}).get(d)
        if i is None:
            return None
        lo = 0 if k is None else max(0, i - k + 1)
        return [self.p[t][x] for x in self.days[t][lo:i + 1]]

    def ind(self, fn, t, w, d):
        if fn not in FNS:
            raise Unsupported(f"indicator {fn}")
        key = (fn, t, w, d)
        cache = self.overlay if self.bump == (t, d) else self.cache
        if key not in cache:
            s = self.closes(t, d, None if fn == "relative-strength-index" else w + 1)
            cache[key] = indicator(fn, s, w) if s else None
        v = cache[key]
        if v is None and self.strict:
            raise DataGap(f"no {SHORT[fn]}({t},{w}) on {d}")
        return v

    def sub_metric(self, sid, fn, w, d):
        if fn not in ("standard-deviation-return", "cumulative-return"):
            raise Unsupported(f"filter on a group by {fn}")
        vals = [v for x, v in self.sub.get(sid, []) if x <= d][-(w + 1):]
        v = indicator(fn, vals, w) if len(vals) > w else None
        if v is None and self.strict:
            raise DataGap(f"group {sid[:8]} has {len(vals)} of {w + 1} sessions of history on {d}")
        return v

    def cond(self, n, d):
        op = n.get("comparator")
        if op not in OPS:
            raise Unsupported(f"comparator {op}")
        lhs_ref = (n["lhs-fn"], n["lhs-val"], window(n, "lhs"))
        lhs = self.ind(*lhs_ref, d)
        if n.get("rhs-fixed-value?"):
            rhs_ref, rhs = None, float(n["rhs-val"])
        else:
            if not n.get("rhs-fn"):
                raise Unsupported("comparison against a ticker without rhs-fn")
            rhs_ref = (n["rhs-fn"], n["rhs-val"], window(n, "rhs"))
            rhs = self.ind(*rhs_ref, d)
        res = lhs is not None and rhs is not None and OPS[op](lhs, rhs)
        if self.trace is not None:
            self.trace.append({"kind": "cond", "lhs": lhs_ref, "rhs": rhs_ref, "op": op, "l": lhs, "r": rhs, "res": res})
        return res

    def weights(self, node, d, w=1.0, out=None):
        out = {} if out is None else out
        step = node.get("step")
        if step not in STEPS:
            raise Unsupported(f"step {step}")
        kids = node.get("children") or []
        if step == "asset":
            out[node["ticker"]] = out.get(node["ticker"], 0.0) + w
        elif step in ("root", "group"):
            for k in kids:
                self.weights(k, d, w, out)
        elif step == "wt-cash-equal":
            for k in kids:
                self.weights(k, d, w / len(kids), out)
        elif step == "wt-cash-specified":
            ws = [weight_of(k) for k in kids]
            tot = sum(ws)
            for k, x in zip(kids, ws):
                self.weights(k, d, w * (x / tot if tot else 0), out)
        elif step == "if":
            branch = next((k for k in kids if not k.get("is-else-condition?") and self.cond(k, d)), None)
            if branch is None:
                branch = next((k for k in kids if k.get("is-else-condition?")), {})
            for k in branch.get("children") or []:
                self.weights(k, d, w, out)
        elif step == "filter":
            fn, fw = node.get("sort-by-fn"), window(node, "sort-by")
            n_sel = int(float(node.get("select-n") or 1))
            scored = []
            for k in kids:
                s = self.ind(fn, k["ticker"], fw, d) if k.get("step") == "asset" else self.sub_metric(k["id"], fn, fw, d)
                if s is not None:
                    scored.append((s, k))
            scored.sort(key=lambda x: x[0], reverse=node.get("select-fn") == "top")
            if self.trace is not None:
                self.trace.append({"kind": "filter", "fn": fn, "w": fw, "n": n_sel, "select": f"{node.get('select-fn')}-{n_sel}",
                                   "ranked": [(round(s, 4), k.get("ticker") or k.get("name") or k["id"][:8]) for s, k in scored]})
            for s, k in scored[:n_sel]:
                self.weights(k, d, w / n_sel, out)
        return out

    def _sub_step(self, subs, d0, d):
        """append each filter sub-tree's value at d: its weights decided at d0 earn d0 -> d"""
        for sid, st in subs.items():
            sw = self.weights(st, d0)
            tot = sum(sw.values())
            r = 0.0
            for t, x in sw.items():
                p0, p1 = self.p.get(t, {}).get(d0), self.p.get(t, {}).get(d)
                if p0 and p1 and tot:
                    r += x / tot * (p1 / p0 - 1)
            self.sub[sid].append((d, self.sub[sid][-1][1] * (1 + r)))

    def decide(self, tree, days, keep):
        """{d: (normalized weights or None, trace or error text)} for each d in keep, deciding at the
        close of d. Filter sub-trees run from days[0] so they carry their own track record."""
        subs = filter_groups(tree)
        self.sub = {sid: [(days[0], 1.0)] for sid in subs}
        out = {}
        for i, d in enumerate(days):
            if i and subs:
                self._sub_step(subs, days[i - 1], d)
            if d in keep:
                self.strict, self.trace = True, []
                try:
                    out[d] = (norm(self.weights(tree, d)), self.trace)
                except DataGap as e:
                    out[d] = (None, str(e))
                finally:
                    self.strict, self.trace = False, None
        return out

    def what_if(self, tree, d, ticker, x):
        """weights at the close of d had `ticker` closed a fraction x higher on d, all else equal"""
        p0 = self.p[ticker][d]
        saved_sub = {k: list(v) for k, v in self.sub.items()}
        self.p[ticker][d] = p0 * (1 + x)
        self.bump, self.overlay = (ticker, d), {}   # only the moved ticker's indicators on d change
        try:
            subs = filter_groups(tree)
            for sid in subs:
                h = self.sub[sid]
                k = next((i for i, (dd, _) in enumerate(h) if dd == d), None)
                if k:
                    del h[k:]
                    self._sub_step({sid: subs[sid]}, h[-1][0], d)
            return norm(self.weights(tree, d))
        finally:
            self.p[ticker][d] = p0
            self.bump, self.overlay, self.sub = None, {}, saved_sub

    def sigma(self, t, d, n=20):
        s = self.closes(t, d, n + 1)
        if not s or len(s) < n + 1:
            return None
        r = [s[i] / s[i - 1] - 1 for i in range(1, len(s))]
        m = sum(r) / n
        return math.sqrt(sum((x - m) ** 2 for x in r) / n)


# ------------------------------------------------------------- classification
def distance(target, live):
    """(half-L1 distance, largest single-asset gap) between two weight dicts"""
    keys = set(target) | set(live)
    gaps = [abs(live.get(k, 0.0) - target.get(k, 0.0)) for k in keys]
    return (0.5 * sum(gaps), max(gaps)) if gaps else (0.0, 0.0)


def agrees(target, live, corridor=None, drifted=None):
    """daily engines: half-L1 <= 3%. A threshold engine (corridor c) holds the target if the previous
    session's holdings, drifted to today's closes, sit more than c off it, else those drifted holdings
    (either is accepted within 1pp of the trigger, which Composer reads at ~15:50 prices), each within
    1.5% half-L1; without previous holdings, every asset within c + 1pp of the target"""
    if not corridor:
        return distance(target, live)[0] <= TOL_DAILY
    if drifted is None:
        return distance(target, live)[1] <= corridor + CORRIDOR_SLACK
    gap = distance(target, drifted)[1]
    expect = ([target] if gap >= corridor - CORRIDOR_SLACK else []) + ([drifted] if gap <= corridor + CORRIDOR_SLACK else [])
    return any(distance(e, live)[0] <= TOL_PATH for e in expect)


def drift(w, prices, d0, d):
    """weights w held from the close of d0, drifted to the close of d (None if a price is missing)"""
    g = {}
    for t, x in w.items():
        p0, p1 = prices.get(t, {}).get(d0), prices.get(t, {}).get(d)
        if not p0 or not p1:
            return None
        g[t] = x * p1 / p0
    tot = sum(g.values())
    return {t: x / tot for t, x in g.items()} if tot else None


def cash_share(s):
    """uninvested cash as a share of the symphony's value (0 if unknown)"""
    try:
        v, c = float((s or {}).get("value") or 0), float((s or {}).get("cash") or 0)
    except (TypeError, ValueError):
        return 0.0
    return c / v if v > 0 else 0.0


def corridor_base(cfg, prev_row, s, prices, d):
    """for a threshold engine: the previous session's live holdings drifted to d's closes. None (the
    lenient check applies) without a ledger row for the session before d that carries that day's own
    holdings, or while a deposit or withdrawal may be in flight: net deposits moved on either day, a
    queued deploy, or uninvested cash above CASH_SHARE_MAX on either day (Composer invests new cash at
    the next rebalance, at target weights)"""
    if not cfg.get("corridor") or not prev_row or not prev_row.get("live"):
        return None
    cal = sorted(x for x in prices.get("SPY", {}) if x < d)
    if not cal or prev_row.get("date") != cal[-1] or prev_row.get("live_asof", cal[-1]) != cal[-1]:
        return None
    s = s or {}
    n0, n1 = prev_row.get("net_deposits"), s.get("net_deposits")
    if n0 is not None and n1 is not None and abs(float(n1) - float(n0)) > 1.0:
        return None
    if prev_row.get("deposit_moved") or prev_row.get("queued") or s.get("has_queued_deploy"):
        return None
    if float(prev_row.get("cash_share") or 0) > CASH_SHARE_MAX or cash_share(s) > CASH_SHARE_MAX:
        return None
    return drift(prev_row["live"], prices, cal[-1], d)


def trace_tickers(trace, tree):
    """tickers whose close can change a decision on the traced path"""
    out, groups = set(), filter_groups(tree)
    for it in trace or []:
        if it["kind"] == "cond":
            out.add(it["lhs"][1])
            if it["rhs"]:
                out.add(it["rhs"][1])
        else:
            for _, name in it["ranked"]:
                g = next((n for n in groups.values() if (n.get("name") or n["id"][:8]) == name), None)
                out |= tree_tickers(g) if g else {name}
    return sorted(out)


def knife_edge(sim, tree, d, trace, live, corridor=None, drifted=None):
    """fallback when 5-minute bars are missing: the smallest one-ticker move on d, in sigma, that turns
    the logic's answer into Composer's, if any within KNIFE_SIGMA: {'ticker', 'move', 'sigma_ratio',
    'target'} or None"""
    steps = [1e-4 * 1.25 ** k for k in range(42)]
    trials = []
    for t in trace_tickers(trace, tree):
        sg = sim.sigma(t, d)
        if not sg or d not in sim.p.get(t, {}):
            continue
        for s in steps:
            if s > KNIFE_SIGMA * sg:
                break
            trials += [(s / sg, t, s), (s / sg, t, -s)]
    for ratio, t, x in sorted(trials):
        alt = sim.what_if(tree, d, t, x)
        if agrees(alt, live, corridor, drifted):
            return {"ticker": t, "move": round(x, 5), "sigma_ratio": round(ratio, 3), "target": alt}
    return None


def _hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _min(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def decision_times(close="16:00"):
    """Composer's decision minutes for a session closing at `close` (ET): 15, 10 and 5 minutes before"""
    return tuple(_hm(_min(close) - k) for k in KNIFE_OFFSETS)


def bar_price(day_bars, hhmm, max_age=STALE_BAR_MIN):
    """price at hh:mm ET = close of the 5-minute bar ending then; the last earlier bar if that one is
    missing, but none older than max_age minutes (a stale print is not a decision-time price)"""
    end = _min(hhmm) - 5
    ks = [k for k, v in day_bars.items() if not k.startswith("_") and v and end - max_age <= _min(k) <= end]
    return day_bars[max(ks, key=_min)] if ks else None


def decision_tickers(tree):
    """tickers whose price on the decision day can change what the tree holds: those read by a
    condition, ranked by a filter, or held inside a filter group (its track record); a ticker that is
    only held elsewhere cannot"""
    out = set()

    def walk(n):
        if n.get("lhs-fn"):
            out.add(n["lhs-val"])
            if not n.get("rhs-fixed-value?"):
                out.add(n["rhs-val"])
        if n.get("step") == "filter":
            for k in n.get("children") or []:
                out.update({k["ticker"]} if k.get("step") == "asset" else tree_tickers(k))
        for k in n.get("children") or []:
            walk(k)
    walk(tree)
    return out


def at_times(prices, raw, bars, tree, d):
    """{hh:mm: target} with every decision ticker's close on d replaced by its price at Composer's
    decision minutes (Yahoo 5-minute bars, scaled onto the adjusted series by the official close);
    None if a bar or a raw close is missing for a decision ticker"""
    bars = bars or {}
    close = next((b[d]["_close"] for b in bars.values() if (b or {}).get(d, {}).get("_close")), "16:00")
    tk = decision_tickers(tree)
    out = {}
    for hh in decision_times(close):
        p = dict(prices)
        for t in tk:
            px = bar_price(((bars.get(t) or {}).get(d)) or {}, hh)
            rc = (raw.get(t) or {}).get(d)
            if px is None or not rc or d not in prices.get(t, {}):
                return None
            p[t] = dict(prices[t])
            p[t][d] = prices[t][d] * px / rc
        _, alt, _ = run_engine(p, tree, d)
        out[hh] = alt
    return out


def margin(it):
    """how close a traced check came to the other answer (relative; small = decisive)"""
    if it["kind"] == "cond":
        if it["l"] is None or it["r"] is None:
            return 0.0
        return abs(it["l"] - it["r"]) / max(1.0, abs(it["r"]))
    r, n = it["ranked"], it.get("n", 1)
    if len(r) <= n:
        return float("inf")
    return abs(r[n - 1][0] - r[n][0]) / max(1.0, abs(r[n - 1][0]))


def fmt_w(w):
    return ", ".join(f"{t} {x:.0%}" for t, x in sorted(w.items(), key=lambda kv: -kv[1])) or "nothing"


def fmt_item(it):
    if it["kind"] == "cond":
        def side(ref, v):
            fn, t, w = ref
            return f"{t} {v:.2f}" if fn == "current-price" else f"{SHORT[fn]}({t},{w}) {v:.2f}"
        lft = side(it["lhs"], it["l"]) if it["l"] is not None else f"{it['lhs']} n/a"
        rgt = (side(it["rhs"], it["r"]) if it["rhs"] else f"{it['r']:g}") if it["r"] is not None else "n/a"
        return f"{lft} {'>' if it['op'] == 'gt' else '<'} {rgt}: {'yes' if it['res'] else 'no'}"
    top = ", ".join(f"{n} {s:.2f}" for s, n in it["ranked"][:4])
    return f"{it['select']} by {SHORT.get(it['fn'], it['fn'])}({it['w']}): {top}"


def explain(trace, limit=4):
    """the closest calls on the decision path, in path order"""
    idx = sorted(sorted(range(len(trace or [])), key=lambda i: margin(trace[i]))[:limit])
    return "; ".join(fmt_item(trace[i]) for i in idx)


def classify(sim, tree, d, target, trace, live, corridor=None, drifted=None, intraday=None):
    """(status, detail) for one engine on a session where Composer attempted a rebalance.
    intraday: callable -> {hh:mm: target} (None when 5-minute bars are missing)"""
    half_l1, max_gap = distance(target, live)
    det = {"dist": round(half_l1, 4), "max_gap": round(max_gap, 4)}
    if agrees(target, live, corridor, drifted):
        return "agree", det
    alts = intraday() if intraday else None
    if alts is not None:
        hit = next((hh for hh, alt in alts.items() if alt and agrees(alt, live, corridor, drifted)), None)
        if hit:
            det["edge"] = {"basis": "intraday", "time": hit, "target": alts[hit]}
            return "knife-edge", det
        det.update(why=explain(trace), checked=f"prices at {', '.join(alts)} ET")
        return "mismatch", det
    edge = knife_edge(sim, tree, d, trace, live, corridor, drifted)
    if edge:
        det["edge"] = dict(edge, basis="search")
        return "knife-edge", det
    det.update(why=explain(trace), checked=f"one-ticker moves to {KNIFE_SIGMA:g} sigma (no 5-minute bars)")
    return "mismatch", det


# ------------------------------------------------------------- logic drift
def _num(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


DEFAULT_TRUE = {"select?", "sort-by?"}     # absent means on (47 of 48 approved filters omit them)


def canonical(n, parent=None, wnorm=None):
    """a tree's logic for comparison: every field except display-only ones (an unknown new field
    counts), numbers normalised ('10' == 10), a flag at its default == absent, each window as the one
    the evaluator reads (moving it between fn-params and window-days is no change; conflicting fields
    are), a weight only where the parent reads it (wt-cash-specified) and as a share of its siblings,
    rhs-fn only when the right side is not a fixed value"""
    c = {}
    for k, v in n.items():
        if k in DISPLAY or k in ("children", "weight") or k.endswith("-window-days"):
            continue
        if k in DEFAULT_TRUE:
            if v is False:
                c[k] = False
            continue
        if v is None or v is False or v in ("", {}, []):
            continue
        if k == "rhs-fn" and n.get("rhs-fixed-value?"):
            continue
        if isinstance(v, dict):
            v = {kk: _num(vv) for kk, vv in sorted(v.items())
                 if vv not in (None, "") and not (k.endswith("-fn-params") and kk == "window")}
            if v:
                c[k] = v
        else:
            c[k] = _num(v)
    for side in ("lhs", "rhs", "sort-by"):
        if n.get(f"{side}-fn") and not (side == "rhs" and n.get("rhs-fixed-value?")):
            try:
                c[f"{side}-window"] = window(n, side)
            except Unsupported:
                c[f"{side}-window"] = f"conflict {n.get(f'{side}-fn-params')} {n.get(f'{side}-window-days')}"
    if parent == "wt-cash-specified" and wnorm is not None:
        c["weight"] = round(wnorm, 10)
    kids = n.get("children") or []
    if kids and n.get("step") == "wt-cash-specified":
        tot = sum(weight_of(k) for k in kids)
        c["children"] = [canonical(k, "wt-cash-specified", weight_of(k) / tot if tot else 0.0) for k in kids]
    elif kids:
        c["children"] = [canonical(k, n.get("step")) for k in kids]
    return c


def first_diff(a, b, path="root"):
    """where two canonical trees first differ, as 'path: approved -> live'"""
    def short(v):
        return json.dumps(v)[:60]
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k == "children" and k in a and k in b:
                for i, (x, y) in enumerate(zip(a[k], b[k])):
                    lab = f"{path}>{x.get('step', '?')}#{i}" + (f"({x.get('ticker') or x.get('lhs-val')})"
                                                              if x.get("ticker") or x.get("lhs-val") else "")
                    r = first_diff(x, y, lab)
                    if r:
                        return r
                if len(a[k]) != len(b[k]):
                    return f"{path}: {len(a[k])} -> {len(b[k])} children"
                continue
            if k not in a:
                return f"{path}.{k}: (absent) -> {short(b[k])}"
            if k not in b:
                return f"{path}.{k}: {short(a[k])} -> (absent)"
            if a[k] != b[k]:
                return f"{path}.{k}: {short(a[k])} -> {short(b[k])}"
        return None
    return None if a == b else f"{path}: {short(a)} -> {short(b)}"


def check_drift(cfg_all, get, st_drift, e_now, load=None):
    """(alerts, notes): Composer's live tree vs the last approved era, for every engine, every run.
    One engine's failure (composerlib exits on HTTP errors) does not stop the others."""
    load = load or load_tree
    alerts, notes = [], []
    today = e_now.date().isoformat()
    fails = st_drift.setdefault("_fail", {})
    for eng, cfg in cfg_all.items():
        try:
            era = cfg["eras"][-1]
            want = canonical(load(era))
            have = canonical(get(f"/symphonies/{cfg['symphony']}/score"))
            vs = get(f"/symphonies/{cfg['symphony']}/versions")
            vs = vs if isinstance(vs, list) else (vs or {}).get("versions", [])
            head = vs[0].get("version_id") if vs else None
            if have == want:
                if eng in st_drift:
                    notes.append(f"shadow: {eng} runs the approved logic again")
                    st_drift.pop(eng)
                if head and head != era["version"]:
                    notes.append(f"shadow: {eng} has a new version {head} with the approved logic (a rename?); "
                                 f"add it to fixtures/approved/manifest.json")
                continue
            h = hashlib.sha1(json.dumps(have, sort_keys=True).encode()).hexdigest()[:12]
            prev = st_drift.get(eng) or {}
            if prev.get("hash") != h or (e_now.weekday() == 0 and prev.get("alerted") != today):
                alerts.append(f"LOGIC DRIFT — {eng}: Composer's live logic (version {head or 'unknown'}) differs from the "
                              f"approved {era['version']} at {first_diff(want, have)}. The shadow keeps checking the "
                              f"approved logic. Approve the change (a new era in fixtures/approved/manifest.json, with a "
                              f"CHANGELOG entry) or roll it back.")
                prev = {"hash": h, "alerted": today, "version": head}
            st_drift[eng] = prev
            fails.pop(eng, None)
        except (Exception, SystemExit) as e:  # noqa: BLE001
            notes.append(f"shadow: logic-drift check for {eng} unavailable ({e})")
            f = fails.setdefault(eng, {"n": 0, "day": None})
            if f["day"] != today:                    # once per ET day: re-runs do not count twice
                f["n"], f["day"] = f["n"] + 1, today
                if f["n"] == BLIND_ALERT or (f["n"] > BLIND_ALERT and e_now.weekday() == 0):
                    alerts.append(f"SHADOW BLIND — {eng}: the logic-drift check failed on {f['n']} days in a row "
                                  f"(latest: {str(e)[:120]}). Composer could be running unapproved logic unnoticed.")
    return alerts, notes


# ----------------------------------------------------------------- data I/O
def load_manifest():
    with open(os.path.join(APPROVED, "manifest.json")) as f:
        return json.load(f)["engines"]


def era_for(cfg, d):
    eras = [e for e in cfg["eras"] if e["from"] <= d]
    return eras[-1] if eras else None


def eras_between(cfg, lo, hi):
    """eras that govern at least one date in [lo, hi]"""
    out = []
    for i, e in enumerate(cfg["eras"]):
        nxt = cfg["eras"][i + 1]["from"] if i + 1 < len(cfg["eras"]) else "9999"
        if e["from"] <= hi and nxt > lo:
            out.append(e)
    return out


def load_tree(era):
    with open(os.path.join(APPROVED, era["tree"])) as f:
        return json.load(f)


def _et_fallback(now):
    """UTC -> US Eastern without a tz database (DST: second Sunday of March 07:00 UTC to the first
    Sunday of November 06:00 UTC)"""
    y = now.year
    mar = datetime.datetime(y, 3, 8 + (6 - datetime.date(y, 3, 8).weekday()) % 7, 7, tzinfo=datetime.timezone.utc)
    nov = datetime.datetime(y, 11, 1 + (6 - datetime.date(y, 11, 1).weekday()) % 7, 6, tzinfo=datetime.timezone.utc)
    off = -4 if mar <= now < nov else -5
    return now.astimezone(datetime.timezone(datetime.timedelta(hours=off)))


def et_now(now):
    try:
        import zoneinfo
        return now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001
        return _et_fallback(now)


def final_through(now):
    """the latest date whose close is final at `now` (today only after 16:15 ET)"""
    e = et_now(now)
    today = e.date()
    return today if (e.hour, e.minute) >= FINAL_AFTER else today - datetime.timedelta(days=1)


def _chart(url, timeout=30):
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["chart"]["result"][0]


def _utc_date(ts):
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()


def apply_events(dates, adj, raw, events):
    """in place: a dividend or split Yahoo has booked but not yet applied to the closes before it (its
    adjusted series can lag on the ex-date) is applied here, multiplicatively, as Yahoo does"""
    idx = {d: i for i, d in enumerate(dates)}
    for ev in (events.get("dividends") or {}).values():
        i = idx.get(_utc_date(ev["date"]))
        if not i:
            continue
        k = 1 - float(ev["amount"]) / raw[i - 1]
        if abs((adj[i - 1] / raw[i - 1]) / (adj[i] / raw[i]) - 1) < 1e-6 and abs(k - 1) > 1e-6:
            for j in range(i):
                adj[j] *= k
    for ev in (events.get("splits") or {}).values():
        i = idx.get(_utc_date(ev["date"]))
        if not i or not ev.get("numerator") or not ev.get("denominator"):
            continue
        m = float(ev["denominator"]) / float(ev["numerator"])
        jump = raw[i] / raw[i - 1]
        if m > 0 and abs(math.log(jump) - math.log(m)) < abs(math.log(jump)):
            for j in range(i):
                adj[j] *= m
                raw[j] *= m


def parse_daily(res):
    """({date: adjusted close}, {date: raw close}) from a Yahoo daily chart result; empty if no bars"""
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    rows = {}
    for i, ts in enumerate(res.get("timestamp") or []):
        c = q["close"][i]
        if c:
            rows[_utc_date(ts)] = (float(adj[i] if adj and adj[i] else c), float(c))
    if not rows:
        return {}, {}
    dates = sorted(rows)
    a_, r_ = [rows[d][0] for d in dates], [rows[d][1] for d in dates]
    apply_events(dates, a_, r_, res.get("events") or {})
    return dict(zip(dates, a_)), dict(zip(dates, r_))


def fetch_yahoo(t, rng="2y", tries=3):
    """({date: adjusted close}, {date: raw close}) from Yahoo daily bars"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
           f"?range={rng}&interval=1d&events=div%2Csplit")
    err = None
    for k in range(tries):
        try:
            adj, raw = parse_daily(_chart(url))
            if adj:
                return adj, raw
            err = "empty series"
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(1 + k)
    raise RuntimeError(f"Yahoo {t}: {err}")


def fetch_prices(tickers, now, rng="2y"):
    """({ticker: {date: adjusted close}}, {ticker: {date: raw close}}, {ticker: error}), closes final
    at `now`"""
    cut = final_through(now).isoformat()
    out, raw, bad = {}, {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_yahoo, t, rng): t for t in sorted(tickers)}
        for f in concurrent.futures.as_completed(futs):
            t = futs[f]
            try:
                a, r = f.result()
                out[t] = {d: v for d, v in a.items() if d <= cut}
                raw[t] = {d: v for d, v in r.items() if d <= cut}
            except Exception as e:  # noqa: BLE001
                bad[t] = str(e)
    return out, raw, bad


def _session_closes(res, out):
    """{date: 'HH:MM'} regular-session close per day: Yahoo's tradingPeriods, else inferred from the
    bars (a closing-auction bar sits at the close itself; otherwise the last bar ends at the close)"""
    closes = {}

    def walk(x):
        if isinstance(x, dict) and "end" in x and "start" in x:
            e = et_now(datetime.datetime.fromtimestamp(x["end"], tz=datetime.timezone.utc))
            closes[e.date().isoformat()] = e.strftime("%H:%M")
        elif isinstance(x, dict):
            walk(x.get("regular") or [])
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk((res.get("meta") or {}).get("tradingPeriods") or [])
    for d, b in out.items():
        if d not in closes:
            ks = sorted((k for k in b if not k.startswith("_")), key=_min)
            if ks:
                last = _min(ks[-1])
                auction = last % 30 == 0 and len(ks) > 1 and _min(ks[-2]) == last - 5
                closes[d] = _hm(last if auction else last + 5)
    return closes


def fetch_intraday(t, rng="5d"):
    """{date: {'HH:MM' bar start, ET: bar close, '_close': regular-session close}} from Yahoo
    5-minute bars"""
    res = _chart(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
                 f"?range={rng}&interval=5m&includePrePost=false")
    out = {}
    for ts, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0]["close"]):
        if c:
            e = et_now(datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc))
            out.setdefault(e.date().isoformat(), {})[e.strftime("%H:%M")] = float(c)
    for d, c in _session_closes(res, out).items():
        if d in out:
            out[d]["_close"] = c
    return out


def bars_fetcher(rng="5d"):
    """a cached callable tickers -> {ticker: intraday bars}; tickers without bars are absent. SPY's
    session closes (always fetched) date every ticker's day, so a thin fund's sparse bars cannot
    shift the decision minutes"""
    cache = {}

    def get(tickers):
        need = [t for t in set(tickers) | {"SPY"} if t not in cache]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for t, res in zip(need, ex.map(lambda t: _try(fetch_intraday, t, rng), need)):
                cache[t] = res
        cal = {d: b.get("_close") for d, b in (cache.get("SPY") or {}).items() if b.get("_close")}
        out = {}
        for t in tickers:
            if cache.get(t):
                out[t] = {d: (dict(b, _close=cal[d]) if d in cal else b) for d, b in cache[t].items()}
        return out
    return get


def _try(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


def common_days(prices, tickers, end):
    ds = None
    for t in tickers:
        s = {d for d in prices.get(t, {}) if d <= end}
        ds = s if ds is None else ds & s
    return sorted(ds or [])


def run_engine(prices, tree, d):
    """(Shadow, target, trace or error) for one tree at the close of d"""
    try:
        validate(tree)
    except Unsupported as e:
        return None, None, f"unsupported logic: {e}"
    tick = tree_tickers(tree)
    missing = sorted(t for t in tick if d not in prices.get(t, {}))
    if missing:
        return None, None, f"no close on {d} for {', '.join(missing)}"
    days = common_days(prices, tick, d)
    days = days[-(SUB_WARMUP + 1):] if filter_groups(tree) else [d]
    sim = Shadow({t: prices[t] for t in tick})
    try:
        target, tr = sim.decide(tree, days, {d})[d]
    except Unsupported as e:
        return None, None, f"unsupported logic: {e}"
    return sim, target, tr


def live_weights(s):
    """Composer's holdings as weights summing to 1; malformed entries are skipped"""
    hs = s.get("holdings")
    h = {}
    for x in hs if isinstance(hs, list) else []:
        if isinstance(x, dict) and isinstance(x.get("ticker"), str) and isinstance(x.get("allocation"), (int, float)) \
                and x["allocation"] > 0:
            h[x["ticker"]] = h.get(x["ticker"], 0.0) + float(x["allocation"])
    tot = sum(h.values())
    return {t: round(x / tot, 6) for t, x in sorted(h.items())} if tot else {}


def read_ledger(path=None, strict=False):
    """ledger rows (date and engine strings); a malformed line is skipped. A missing file is empty;
    any other read error is too, unless strict (the write path: never rewrite a history it could not
    read)"""
    path = path or LEDGER
    out = []
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return out
    except OSError:
        if strict:
            raise
        return out
    for x in lines:
        try:
            r = json.loads(x)
        except ValueError:
            continue
        if isinstance(r, dict) and isinstance(r.get("date"), str) and isinstance(r.get("engine"), str):
            out.append(r)
    return out


def write_ledger(rows, path=None):
    """upsert by (date, engine), sorted by date then engine; written to a temp file and renamed, so a
    crash cannot leave a half-written ledger"""
    path = path or LEDGER
    keep = {(r["date"], r["engine"]): r for r in read_ledger(path, strict=True)}
    for r in rows:
        keep[(r["date"], r["engine"])] = r
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    order = {e: i for i, e in enumerate(ORDER)}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".shadow-ledger.")
    try:
        with os.fdopen(fd, "w") as f:
            for k in sorted(keep, key=lambda k: (k[0], order.get(k[1], 9), k[1])):
                f.write(json.dumps(keep[k], separators=(",", ":")) + "\n")
        os.chmod(tmp, os.stat(path).st_mode & 0o777 if os.path.isfile(path) else 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def previous_rows(path, d, prices):
    """{engine: ledger row} for the session immediately before d (SPY calendar)"""
    cal = sorted(x for x in prices.get("SPY", {}) if x < d)
    return {r["engine"]: r for r in read_ledger(path) if cal and r.get("date") == cal[-1]}


def record(rows_all, n=20):
    """counts of statuses over the last n sessions in the ledger"""
    dates = sorted({r["date"] for r in rows_all})[-n:]
    out = {}
    for r in rows_all:
        if r["date"] in dates:
            k = r.get("status", "unknown")
            out[k] = out.get(k, 0) + 1
    return len(dates), out


# --------------------------------------------------------------- daily check
def expected_session(now):
    """the latest session whose close is final at `now`, from the weekday calendar and NYSE_HOLIDAYS;
    dates a run only when Yahoo is down (so no-rebalance can still be judged from Composer's record)"""
    d = final_through(now)
    while d.weekday() >= 5 or d.isoformat() in NYSE_HOLIDAYS:
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def assess(cfg_all, meta, prices, d, st, load=None, raw=None, bars=None, prev=None, weekday=1, only=None):
    """Pure core of the daily check (no network). st: shadow state, mutated (the caller works on a
    copy and keeps it only on success). raw: {ticker: {date: raw close}}; bars: callable(tickers) ->
    5-minute bars, called only on a disagreement; prev: {engine: ledger row of the previous session};
    weekday: ET weekday of the run; only: re-assess just these engines (a re-run of the same session:
    no no-rebalance or blind-count transitions). Returns (rows, alerts, notes)."""
    load = load or load_tree
    raw = raw or {}
    rows, alerts, notes = [], [], []
    by_id = {s.get("id"): s for s in meta if isinstance(s, dict)}
    fz, ks, bl = st.setdefault("frozen", {}), st.setdefault("knife_streak", {}), st.setdefault("blind", {})
    stat = st.setdefault("status", {})
    new, still, resumed, wants = [], [], [], {}
    for eng, cfg in cfg_all.items():
        if only is not None and eng not in only:
            continue
        era = era_for(cfg, d)
        if not era:
            notes.append(f"shadow: {eng} has no approved era on {d}")
            continue
        s = by_id.get(cfg["symphony"])
        row = {"date": d, "engine": eng, "version": era["version"][:8], "src": "live"}
        if not s:
            row.update(status="unavailable", note="not in Composer's symphony list")
        else:
            attempted, live = s.get("last_rebalance_attempted_on"), live_weights(s)
            if attempted is not None and not isinstance(attempted, str):
                notes.append(f"shadow: {eng}: unreadable rebalance-attempt date {attempted!r}; treated as missing")
                attempted = None
            p0 = (prev or {}).get(eng) or {}
            n0, n1 = p0.get("net_deposits"), s.get("net_deposits")
            try:
                moved = n0 is not None and n1 is not None and abs(float(n1) - float(n0)) > 1.0
            except (TypeError, ValueError):
                moved = False
            row.update(live=live, attempted=attempted, net_deposits=n1, queued=bool(s.get("has_queued_deploy")),
                       cash_share=round(cash_share(s), 4), deposit_moved=moved)
            paused = bool(s.get("is_paused"))
            # 1. no-rebalance, from Composer's own record alone (no price outage can hide or end it); a
            #    paused symphony counts, and a missing attempt date never ends a freeze
            frozen = paused or bool(attempted and attempted < d) or (attempted is None and eng in fz)
            if only is None:
                if frozen:
                    f = fz.get(eng)
                    if f:
                        f["sessions"] += 1
                        still.append(eng)
                    else:
                        fz[eng] = {"since": d, "sessions": 1, "last": attempted}
                        new.append(eng)
                elif eng in fz:
                    resumed.append((eng, fz.pop(eng)))
            # 2. the approved logic on D's closes; any failure is this engine's, not the run's
            try:
                tree = load(era)
                sim, target, tr = run_engine(prices, tree, d)
            except Exception as e:  # noqa: BLE001
                tree, sim, target, tr = None, None, None, f"evaluator error: {e!r}"
            row["target"] = target
            if frozen:
                row["status"] = "no-rebalance"
                if paused:
                    row["paused"] = True
                wants[eng] = (target, live, cfg.get("corridor"), s, tr)
            elif target is None:
                row.update(status="unavailable", note=tr)
            elif not attempted or attempted > d:
                row.update(status="unavailable", note=(f"Composer attempted {attempted}; the newest final close here is {d}"
                                                       if attempted else "Composer reports no rebalance attempt date"))
            else:
                try:
                    base = corridor_base(cfg, p0, s, prices, d)
                    intraday = (lambda: at_times(prices, raw, bars(sorted(decision_tickers(tree))), tree, d)) if bars else None
                    status, det = classify(sim, tree, d, target, tr, live, cfg.get("corridor"), base, intraday)
                    row.update(status=status, **det)
                    if cfg.get("corridor"):
                        row["corridor_check"] = "path" if base else "lenient"
                except Exception as e:  # noqa: BLE001
                    row.update(status="unavailable", note=f"classifier error: {e!r}")
        # 3. per-engine streaks and alerts
        status = row["status"]
        if status == "unavailable":
            notes.append(f"shadow: {eng} unavailable on {d} ({row['note']})")
            if only is None:
                bl[eng] = bl.get(eng, 0) + 1
                if bl[eng] == BLIND_ALERT or (bl[eng] > BLIND_ALERT and weekday == 0):
                    alerts.append(f"SHADOW BLIND — {eng}: no comparison for {bl[eng]} sessions in a row "
                                  f"(latest: {row['note']}). The runner cannot vouch for this engine until it clears.")
        else:
            bl.pop(eng, None)
        if status == "knife-edge" and row["edge"]["basis"] == "search":
            ks[eng] = ks.get(eng, 0) + 1
        else:
            ks.pop(eng, None)
        if status == "mismatch":
            alerts.append(f"SHADOW MISMATCH — {eng} on {d}: Composer holds {fmt_w(row['live'])}; its approved logic "
                          f"({era['version'][:8]}) says {fmt_w(row['target'])}, on closing prices and on {row['checked']}. "
                          f"Closest calls: {row['why']}. Check the symphony and the data before the next "
                          f"rebalance; no trade is implied.")
        elif status == "knife-edge" and ks.get(eng, 0) >= STREAK_ALERT:
            e = row["edge"]
            alerts.append(f"SHADOW KNIFE-EDGE x{ks[eng]} — {eng} on {d}: Composer holds {fmt_w(row['live'])}, the "
                          f"approved logic on closing prices says {fmt_w(row['target'])}; with no 5-minute bars to "
                          f"check, a {e['move']:+.2%} {e['ticker']} move ({e['sigma_ratio']:.2f} sigma) is the "
                          f"explanation. Check the data feed and the symphony if it continues.")
        stat[eng] = status
        rows.append(row)

    def wanted(e):
        t, lv, c, s, tr = wants[e]
        if t is None:
            return f"{e} logic unavailable ({tr})"
        return f"{e} {fmt_w(t)}" + ("" if agrees(t, lv, c) else f" (frozen at {fmt_w(lv)})")

    def why(e):
        s = wants[e][3]
        if s.get("is_paused"):
            return f"{e} is paused in Composer ({s.get('paused_by')}: {s.get('paused_reason')})"
        att = s.get("last_rebalance_attempted_on")
        return f"{e} last attempted {att}" if isinstance(att, str) else f"{e} reports no attempt date"
    if new:
        alerts.append(f"COMPOSER DID NOT REBALANCE — no rebalance on {d} for {', '.join(new)} "
                      f"({'; '.join(why(e) for e in new)}); holdings are frozen. Approved logic now: "
                      f"{'; '.join(wanted(e) for e in new)}. The 2026-10-26..28 subscription lapse looked like this.")
    loud = [e for e in still if not wants[e][3].get("is_paused") or weekday == 0]
    if loud:
        alerts.append("COMPOSER STILL NOT REBALANCING — " + "; ".join(
            f"{e} session {fz[e]['sessions']} without a rebalance (since {fz[e]['since']})" for e in loud)
            + f". Approved logic now: {'; '.join(wanted(e) for e in loud)}.")
    if resumed:
        alerts.append(f"COMPOSER REBALANCING RESUMED on {d} — " + "; ".join(
            f"{e} after {f['sessions']} session(s) without a rebalance (since {f['since']})" for e, f in resumed) + ".")
    return rows, alerts, notes


def check_shadow(state, alerts, snap, meta, now, get=None, write=True, ledger=None, bars=None):
    """monitor.py hook. The logic-drift check needs no prices; a Yahoo outage dates the session from
    the exchange calendar so Composer's own record is still judged. Alerts are delivered even if the
    ledger cannot be written. A failed run keeps the previous state (only its failure count moves);
    three in a row alert."""
    ledger = ledger or LEDGER
    st = copy.deepcopy(state.get("shadow") or {})
    e_now = et_now(now)
    new_alerts, notes, rows, d = [], [], [], None
    try:
        cfg_all = load_manifest()
        if get is not None:
            a, n = check_drift(cfg_all, get, st.setdefault("drift", {}), e_now)
            new_alerts += a
            notes += n
        work = copy.deepcopy(st)
        hi = final_through(now)
        lo = (hi - datetime.timedelta(days=10)).isoformat()   # D is the latest session on or before hi
        tick = {"SPY"}
        for cfg in cfg_all.values():
            for era in eras_between(cfg, lo, hi.isoformat()):
                tick |= tree_tickers(load_tree(era))
        try:
            prices, raw, bad = fetch_prices(tick, now)
        except Exception as e:  # noqa: BLE001
            prices, raw, bad = {}, {}, {"*": str(e)}
        if prices.get("SPY"):
            d = max(prices["SPY"])
        else:
            d = expected_session(now)
            notes.append(f"shadow: no SPY prices from Yahoo; session dated {d} from the exchange calendar")
        if bad:
            notes.append(f"shadow: Yahoo failed for {', '.join(sorted(bad))}")
        pending = work.get("pending") or []
        if work.get("last_date") == d and not pending:
            notes.append(f"shadow: no session newer than {d}; nothing re-assessed")
            snap["shadow"] = {"date": d, "stale": True, "status": dict(work.get("status") or {})}
        else:
            only = set(pending) if work.get("last_date") == d else None
            rows, a, n = assess(cfg_all, meta, prices, d, work, raw=raw, bars=bars or bars_fetcher(),
                                prev=previous_rows(ledger, d, prices), weekday=e_now.weekday(), only=only)
            new_alerts += a
            notes += n
            work["last_date"] = d
            work["pending"] = sorted(e for e, x in work.get("status", {}).items() if x == "unavailable")
            snap["shadow"] = {"date": d, "status": dict(work["status"])}
        work.pop("fail", None)
        st = work
    except (Exception, SystemExit) as e:  # noqa: BLE001  never take the monitor down
        f = st.setdefault("fail", {"n": 0})
        f["n"] += 1
        f["last"] = str(e)[:300]
        notes.append(f"shadow runner unavailable: {e}")
        if f["n"] == BLIND_ALERT or (f["n"] > BLIND_ALERT and e_now.weekday() == 0 and f.get("alerted") != e_now.date().isoformat()):
            new_alerts.append(f"SHADOW RUNNER DOWN — {f['n']} runs in a row failed (latest: {f['last']}). Composer is "
                              f"not being checked against the approved logic until this clears.")
            f["alerted"] = e_now.date().isoformat()
    for n in notes:
        print(f"  ({n})")
    if rows:
        line = " | ".join(f"{r['engine']} {r['status']}" + (f" @{r['edge']['time']}" if r.get("edge", {}).get("basis") == "intraday" else "")
                          + (f" {fmt_w(r['target'])}" if r.get("target") else "") for r in rows)
        print(f"  shadow {d}: {line}")
    alerts.extend(new_alerts)
    if not write:
        return
    state["shadow"] = st
    if rows:
        try:
            write_ledger(rows, ledger)
        except Exception as e:  # noqa: BLE001
            print(f"  (shadow ledger not written: {e})")
            return
        try:
            n, rec = record(read_ledger(ledger))
            print(f"  shadow record, last {n} session(s): " + ", ".join(f"{v} {k}" for k, v in sorted(rec.items())))
        except Exception as e:  # noqa: BLE001
            print(f"  (shadow record unavailable: {e})")


def main():
    sys.path.insert(0, HERE)
    import composerlib as cl
    now = datetime.datetime.now(datetime.timezone.utc)
    meta = cl.get(f"/portfolio/accounts/{cl.default_account()}/symphony-stats-meta")["symphonies"]
    state, alerts, snap = {"shadow": {}}, [], {}
    check_shadow(state, alerts, snap, meta, now, get=cl.get, write=False)
    print("\nalerts now:", alerts or "none")


if __name__ == "__main__":
    main()
