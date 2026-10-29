#!/usr/bin/env python3
"""Shadow decision runner for the live Composer symphonies (results.md addendum 48).

Every session it works out what each symphony's APPROVED logic says to hold, on independent prices
(Yahoo adjusted closes), and compares that with what Composer actually holds. Read-only toward
Composer, holds no broker key, never trades or edits a symphony.

It catches what Composer's own numbers cannot show:
  - Composer stops rebalancing (2026-10-26..28: three sessions with no rebalance attempt, seen at
    the time only as API errors)
  - Composer runs logic other than what was approved (an unapproved edit, or an edit that failed
    silently: the 2026-07-30 PUT-wrapper bug returned success and changed nothing)
  - a rule is read differently here than in Composer (data or semantics)
and its ledger is the running proof that the rules reproduce outside Composer, the precondition
for running them anywhere else (IBKR).

Per engine, for session D (the latest final close on Yahoo):
  agree         Composer holds what the approved logic says: daily engines within 3% (half the L1
                distance between weight vectors); KMLM within its 10% threshold corridor
  knife-edge    it does not, but one decisive ticker closing at most 0.5 sigma (its 20-session daily
                sigma) away from its close turns the logic's answer into Composer's. Composer decides
                on ~15:50 ET prices, the shadow on the close; 0.5 sigma is the p99 of the measured
                15:45 -> close move. Alerts only on a second session in a row for the same engine
  mismatch      it does not, and no such move explains it -> alert
  no-rebalance  Composer made no rebalance attempt on D -> alert on the first session, daily while
                it lasts, once when it resumes
  unavailable   prices missing, a data gap on the decision path, or logic the shadow has not been
                validated on (Unsupported) -> note, never an alert
Separately, LOGIC DRIFT alerts when Composer's live version is not the last approved era in
fixtures/approved/manifest.json and its logic differs (a rename passes with a note).

Evaluation semantics: research/synth/tree_sim.py (validated 0.999-1.000 daily-return correlation
against Composer on these four trees, Wilder RSI) with research/crash/replay.py's bounded RSI
warm-up (up to 250 closes, at least 60). Weights decided at the close of D from data through D.
Ledger: composer/results/monitor/shadow-ledger.jsonl, one line per engine and session.

Usage: shadow_runner.py     today's comparison, printed; state and ledger untouched
"""
import concurrent.futures
import datetime
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APPROVED = os.path.join(HERE, "..", "fixtures", "approved")
LEDGER = os.path.join(HERE, "..", "results", "monitor", "shadow-ledger.jsonl")

DEFAULT_W = 10
RSI_MAX, RSI_MIN = 250, 60
TOL_DAILY = 0.03          # agree: half-L1 distance between target and live weights
CORRIDOR_SLACK = 0.01     # KMLM: every asset within corridor + 1pp of target
KNIFE_SIGMA = 0.5         # knife-edge search radius in 20-session daily sigmas: the p99 of the measured
                          # 15:45 ET -> close move (0.49; p95 0.29, median 0.08; 13 decisive tickers x 59
                          # sessions of Yahoo 5-minute bars to 2026-10-28)
SUB_WARMUP = 60           # sessions of filter sub-tree history before the first decision
FINAL_AFTER = (16, 15)    # ET: a session's close counts as final from 16:15
FNS = {"current-price", "moving-average-price", "cumulative-return", "standard-deviation-return",
       "relative-strength-index"}
STEPS = {"root", "group", "wt-cash-equal", "wt-cash-specified", "if", "if-child", "filter", "asset"}
OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b}
SHORT = {"relative-strength-index": "RSI", "moving-average-price": "MA", "cumulative-return": "CR",
         "standard-deviation-return": "SD", "current-price": "price"}


class Unsupported(Exception):
    """the tree uses a step, indicator or comparator the shadow has not been validated on"""


class DataGap(Exception):
    """an indicator on the decision path has no value (missing or too-short history)"""


# ------------------------------------------------------------------ evaluator
def window(node, side):
    """indicator window: newer nodes keep it in <side>-fn-params.window, older ones in
    <side>-window-days (API.md); Composer's default is 10"""
    w = (node.get(f"{side}-fn-params") or {}).get("window")
    if w is None:
        w = node.get(f"{side}-window-days")
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
        n = min(RSI_MAX, len(s) - 1)
        if n < max(RSI_MIN, w + 1):
            return None
        d = [s[i] - s[i - 1] for i in range(len(s) - n, len(s))]
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
    """raise Unsupported if any branch (visited today or not) uses a step, indicator, comparator or
    group metric the evaluator has not been validated on"""
    def walk(n):
        if n.get("step") not in STEPS:
            raise Unsupported(f"step {n.get('step')}")
        if n.get("lhs-fn"):
            if n.get("comparator") not in OPS:
                raise Unsupported(f"comparator {n.get('comparator')}")
            for fn in (n["lhs-fn"], None if n.get("rhs-fixed-value?") else n.get("rhs-fn")):
                if fn and fn not in FNS:
                    raise Unsupported(f"indicator {fn}")
        if n.get("step") == "filter":
            if n.get("sort-by-fn") not in FNS:
                raise Unsupported(f"indicator {n.get('sort-by-fn')}")
            if n.get("select-fn") not in ("top", "bottom"):
                raise Unsupported(f"select-fn {n.get('select-fn')}")
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

    def closes(self, t, d, k):
        i = self.pos.get(t, {}).get(d)
        if i is None:
            return None
        return [self.p[t][x] for x in self.days[t][max(0, i - k + 1):i + 1]]

    def ind(self, fn, t, w, d):
        if fn not in FNS:
            raise Unsupported(f"indicator {fn}")
        key = (fn, t, w, d)
        cache = self.overlay if self.bump == (t, d) else self.cache
        if key not in cache:
            s = self.closes(t, d, RSI_MAX + 1 if fn == "relative-strength-index" else w + 1)
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
            rhs_ref = (n.get("rhs-fn") or n["lhs-fn"], n["rhs-val"], window(n, "rhs"))
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
            n_sel = int(node.get("select-n") or 1)
            scored = []
            for k in kids:
                s = self.ind(fn, k["ticker"], fw, d) if k.get("step") == "asset" else self.sub_metric(k["id"], fn, fw, d)
                if s is not None:
                    scored.append((s, k))
            scored.sort(key=lambda x: x[0], reverse=node.get("select-fn") == "top")
            if self.trace is not None:
                self.trace.append({"kind": "filter", "fn": fn, "w": fw, "select": f"{node.get('select-fn')}-{n_sel}",
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


def agrees(target, live, corridor=None):
    half_l1, max_gap = distance(target, live)
    if corridor:
        return max_gap <= corridor + CORRIDOR_SLACK
    return half_l1 <= TOL_DAILY


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


def knife_edge(sim, tree, d, trace, live, corridor=None):
    """smallest one-ticker move on d, in sigma, that turns the logic's answer into Composer's, if any
    within KNIFE_SIGMA: {'ticker', 'move', 'sigma_ratio', 'target'} or None"""
    steps = [1e-4 * 1.25 ** k for k in range(42)]          # 0.01% .. ~1.2x sigma multiples below
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
        if agrees(alt, live, corridor):
            return {"ticker": t, "move": round(x, 5), "sigma_ratio": round(ratio, 3), "target": alt}
    return None


def fmt_w(w):
    return ", ".join(f"{t} {x:.0%}" for t, x in sorted(w.items(), key=lambda kv: -kv[1])) or "nothing"


def fmt_item(it):
    if it["kind"] == "cond":
        def side(ref, v):
            fn, t, w = ref
            return f"{t} {v:.2f}" if fn == "current-price" else f"{SHORT[fn]}({t},{w}) {v:.2f}"
        l = side(it["lhs"], it["l"]) if it["l"] is not None else f"{it['lhs']} n/a"
        r = (side(it["rhs"], it["r"]) if it["rhs"] else f"{it['r']:g}") if it["r"] is not None else "n/a"
        return f"{l} {'>' if it['op'] == 'gt' else '<'} {r}: {'yes' if it['res'] else 'no'}"
    top = ", ".join(f"{n} {s:.2f}" for s, n in it["ranked"][:4])
    return f"{it['select']} by {SHORT.get(it['fn'], it['fn'])}({it['w']}): {top}"


def explain(trace, limit=4):
    """the decision path in words (the last items decided the branch)"""
    items = [fmt_item(it) for it in trace or []]
    return "; ".join(items[-limit:])


def classify(sim, tree, d, target, trace, live, corridor=None):
    """(status, detail dict) for one engine on one session where Composer attempted a rebalance"""
    half_l1, max_gap = distance(target, live)
    det = {"dist": round(half_l1, 4), "max_gap": round(max_gap, 4)}
    if agrees(target, live, corridor):
        return "agree", det
    edge = knife_edge(sim, tree, d, trace, live, corridor)
    if edge:
        det["edge"] = edge
        return "knife-edge", det
    det["why"] = explain(trace)
    return "mismatch", det


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


def et_now(now):
    try:
        import zoneinfo
        return now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001  no tz database: US DST rule (second Sun Mar .. first Sun Nov)
        y = now.year
        mar = datetime.datetime(y, 3, 8 + (6 - datetime.date(y, 3, 8).weekday()) % 7, 7, tzinfo=datetime.timezone.utc)
        nov = datetime.datetime(y, 11, 1 + (6 - datetime.date(y, 11, 1).weekday()) % 7, 6, tzinfo=datetime.timezone.utc)
        return now + datetime.timedelta(hours=-4 if mar <= now < nov else -5)


def final_through(now):
    """the latest date whose close is final at `now` (today only after 16:15 ET)"""
    e = et_now(now)
    today = e.date()
    return today if (e.hour, e.minute) >= FINAL_AFTER else today - datetime.timedelta(days=1)


def fetch_yahoo(t, rng="2y", tries=3):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
           f"?range={rng}&interval=1d&events=div%2Csplit")
    err = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
            out = {}
            for i, ts in enumerate(res.get("timestamp") or []):
                v = adj[i] if adj and adj[i] is not None else q["close"][i]
                if v:
                    out[datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()] = float(v)
            if out:
                return out
            err = "empty series"
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(1 + k)
    raise RuntimeError(f"Yahoo {t}: {err}")


def fetch_prices(tickers, now, rng="2y"):
    """({ticker: {date: adjusted close}} with closes final at `now`, {ticker: error})"""
    cut = final_through(now).isoformat()
    out, bad = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_yahoo, t, rng): t for t in sorted(tickers)}
        for f in concurrent.futures.as_completed(futs):
            t = futs[f]
            try:
                out[t] = {d: v for d, v in f.result().items() if d <= cut}
            except Exception as e:  # noqa: BLE001
                bad[t] = str(e)
    return out, bad


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
    h = {x["ticker"]: x["allocation"] for x in s.get("holdings") or [] if x.get("allocation")}
    tot = sum(h.values())
    return {t: round(x / tot, 6) for t, x in sorted(h.items())} if tot else {}


LOGIC_KEYS = ("step", "ticker", "comparator", "is-else-condition?", "lhs-fn", "lhs-val", "rhs-fn", "rhs-val",
              "rhs-fixed-value?", "select-fn", "select-n", "sort-by-fn", "rebalance", "rebalance-corridor-width")


def canonical(n):
    """a tree's logic only (no ids, names, display fields); windows resolved from either field"""
    c = {k: n[k] for k in LOGIC_KEYS if n.get(k) not in (None, "")}
    if n.get("step") == "if-child" and n.get("lhs-fn"):
        c["lhs-w"] = window(n, "lhs")
        if n.get("rhs-fixed-value?"):
            c.pop("rhs-fn", None)                 # ignored against a fixed value
        else:
            c["rhs-w"] = window(n, "rhs")
    if n.get("step") == "filter":
        c["sort-w"] = window(n, "sort-by")
    if n.get("weight") is not None:
        c["weight"] = round(weight_of(n), 8)
    if n.get("children"):
        c["children"] = [canonical(k) for k in n["children"]]
    return c


def check_drift(cfg_all, get, state_drift, weekday, load=None):
    """(alerts, notes): Composer's live version head vs the last approved era, per engine"""
    load = load or load_tree
    alerts, notes = [], []
    for eng, cfg in cfg_all.items():
        era = cfg["eras"][-1]
        vs = get(f"/symphonies/{cfg['symphony']}/versions")
        vs = vs if isinstance(vs, list) else vs.get("versions", [])
        head = vs[0]["version_id"] if vs else None
        if head is None or head == era["version"]:
            state_drift.pop(eng, None)
            continue
        live = get(f"/symphonies/{cfg['symphony']}/score")
        if canonical(live) == canonical(load(era)):
            notes.append(f"shadow: {eng} has a new version {head} with unchanged logic (a rename?); "
                         f"add it to fixtures/approved/manifest.json")
            state_drift.pop(eng, None)
            continue
        if state_drift.get(eng) != head or weekday == 0:
            alerts.append(f"LOGIC DRIFT — {eng}: Composer runs version {head} ({vs[0].get('created_at', '')[:16]}), "
                          f"not the approved {era['version']}, and the logic differs. The shadow keeps checking the "
                          f"approved logic. Approve the change (new era in fixtures/approved/manifest.json, with a "
                          f"CHANGELOG entry) or roll it back.")
        state_drift[eng] = head
    return alerts, notes


def read_ledger(path=None):
    path = path or LEDGER
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def write_ledger(rows, path=None):
    """upsert by (date, engine); file sorted by date then engine"""
    path = path or LEDGER
    keep = {(r["date"], r["engine"]): r for r in read_ledger(path)}
    for r in rows:
        keep[(r["date"], r["engine"])] = r
    os.makedirs(os.path.dirname(path), exist_ok=True)
    order = {"HG": 0, "KMLM": 1, "SLEEVE": 2, "HARV": 3}
    with open(path, "w") as f:
        for k in sorted(keep, key=lambda k: (k[0], order.get(k[1], 9), k[1])):
            f.write(json.dumps(keep[k], separators=(",", ":")) + "\n")


def record(rows_all, n=20):
    """counts of statuses over the last n sessions in the ledger"""
    dates = sorted({r["date"] for r in rows_all})[-n:]
    out = {}
    for r in rows_all:
        if r["date"] in dates:
            out[r["status"]] = out.get(r["status"], 0) + 1
    return len(dates), out


# --------------------------------------------------------------- daily check
def assess(cfg_all, meta, prices, d, st, load=None):
    """Pure core of the daily check (no network). st: persisted shadow state (mutated); load: era ->
    tree (default: the approved fixtures). Returns (rows, alerts, notes)."""
    load = load or load_tree
    rows, alerts, notes, frozen = [], [], [], []
    by_id = {s["id"]: s for s in meta}
    for eng, cfg in cfg_all.items():
        era = era_for(cfg, d)
        s = by_id.get(cfg["symphony"])
        if not era or not s:
            notes.append(f"shadow: {eng} not live on {d}")
            continue
        tree = load(era)
        sim, target, tr = run_engine(prices, tree, d)
        live, attempted = live_weights(s), s.get("last_rebalance_attempted_on")
        row = {"date": d, "engine": eng, "version": era["version"][:8], "src": "live", "target": target,
               "live": live, "attempted": attempted}
        if target is None:
            row.update(status="unavailable", note=tr)
            notes.append(f"shadow: {eng} unavailable on {d} ({tr})")
        elif attempted and attempted < d:
            row["status"] = "no-rebalance"
            frozen.append((eng, s, target, live, cfg.get("corridor")))
        elif attempted and attempted > d:
            row.update(status="unavailable", note=f"Composer attempted {attempted}, newest final close here is {d}")
            notes.append(f"shadow: {eng}: {row['note']}")
        else:
            status, det = classify(sim, tree, d, target, tr, live, cfg.get("corridor"))
            row.update(status=status, **det)
            ks = st.setdefault("knife_streak", {})
            ks[eng] = ks.get(eng, 0) + 1 if status == "knife-edge" else 0
            if status == "mismatch":
                alerts.append(f"SHADOW MISMATCH — {eng} on {d}: Composer holds {fmt_w(live)}; its approved logic "
                              f"({era['version'][:8]}) says {fmt_w(target)}, and no single-ticker move within "
                              f"{KNIFE_SIGMA:g} sigma of the close explains it. Path: {det['why']}. Check the symphony "
                              f"and the data before the next rebalance; no trade is implied.")
            elif status == "knife-edge" and ks[eng] >= 2:
                e = det["edge"]
                alerts.append(f"SHADOW KNIFE-EDGE x{ks[eng]} — {eng} on {d}: Composer holds {fmt_w(live)}, the "
                              f"approved logic on closing prices says {fmt_w(target)}; a {e['move']:+.2%} {e['ticker']} "
                              f"move ({e['sigma_ratio']:.2f} sigma) explains it. A real knife-edge rarely repeats: "
                              f"check the data feed and the symphony if it continues.")
        rows.append(row)
    # book-level no-rebalance state machine (one alert line for all frozen engines)
    if frozen:
        since = st.get("frozen_since") or d
        n = st.get("frozen_sessions", 0) + 1
        last = sorted({s.get("last_rebalance_attempted_on") for _, s, *_ in frozen})
        wants = "; ".join(f"{e} {fmt_w(t)}" + ("" if agrees(t, lv, c) else f" (frozen at {fmt_w(lv)})")
                          for e, _, t, lv, c in frozen)
        paused = [f"{e} paused by {s.get('paused_by')}: {s.get('paused_reason')}" for e, s, *_ in frozen if s.get("is_paused")]
        head = ("COMPOSER DID NOT REBALANCE" if n == 1 else f"COMPOSER STILL NOT REBALANCING (session {n})")
        alerts.append(f"{head} — no rebalance attempt on {d} for {', '.join(e for e, *_ in frozen)} (last attempt "
                      f"{', '.join(x or 'unknown' for x in last)}); holdings are frozen. "
                      + (f"{'; '.join(paused)}. " if paused else "")
                      + f"Approved logic now: {wants}. The 2026-10-26..28 subscription lapse looked like this.")
        st["frozen_since"], st["frozen_sessions"] = since, n
    elif st.get("frozen_since"):
        alerts.append(f"COMPOSER REBALANCING RESUMED on {d} after {st.get('frozen_sessions', 0)} session(s) without an "
                      f"attempt (since {st['frozen_since']}).")
        st["frozen_since"], st["frozen_sessions"] = None, 0
    return rows, alerts, notes


def check_shadow(state, alerts, snap, meta, now, get=None, write=True):
    """monitor.py hook. Any failure degrades to a printed note (no alert, state untouched)."""
    try:
        cfg_all = load_manifest()
        st = state.setdefault("shadow", {})
        hi = final_through(now)
        lo = (hi - datetime.timedelta(days=10)).isoformat()   # D is the latest session on or before hi
        tick = set()
        for cfg in cfg_all.values():
            for era in eras_between(cfg, lo, hi.isoformat()):
                tick |= tree_tickers(load_tree(era))
        prices, bad = fetch_prices(tick | {"SPY"}, now)
        if "SPY" not in prices:
            raise RuntimeError(f"no SPY prices ({bad.get('SPY')})")
        d = max(prices["SPY"])
        if bad:
            print(f"  (shadow: Yahoo failed for {', '.join(sorted(bad))})")
        if st.get("last_date") == d:
            print(f"  (shadow: no session newer than {d}; nothing re-assessed)")
            snap["shadow"] = {"date": d, "stale": True}
            return
        rows, new_alerts, notes = assess(cfg_all, meta, prices, d, st)
        if get is not None:
            try:
                a2, n2 = check_drift(cfg_all, get, st.setdefault("drift", {}), now.weekday())
                new_alerts += a2
                notes += n2
            except (Exception, SystemExit) as e:  # noqa: BLE001  composerlib exits on HTTP errors
                notes.append(f"shadow: logic-drift check unavailable ({e})")
        for n in notes:
            print(f"  ({n})")
        if write:
            write_ledger(rows)
            st["last_date"] = d
        n, rec = record(read_ledger() if write else rows)
        line = " | ".join(f"{r['engine']} {r['status']}" + (f" {fmt_w(r['target'])}" if r.get("target") else "")
                          for r in rows)
        print(f"  shadow {d}: {line}")
        print(f"  shadow record, last {n} session(s): " + ", ".join(f"{v} {k}" for k, v in sorted(rec.items())))
        alerts.extend(new_alerts)
        snap["shadow"] = {"date": d, "status": {r["engine"]: r["status"] for r in rows}}
    except (Exception, SystemExit) as e:  # noqa: BLE001  never take the monitor down
        print(f"  (shadow runner unavailable: {e})")


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
