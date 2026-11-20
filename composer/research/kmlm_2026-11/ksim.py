"""Simulator for the KMLM switcher study (PREREG.md): the approved tree, or a variant of its 75% block, on
daily adjusted closes, held on Composer's threshold-rebalance path, with costs.

Decisions come from shadow_runner.Shadow (validated against Composer's backtests on every approved tree,
results.md add. 48). Nothing here re-implements a rule the evaluator already reads; what it adds:
  - variant builders that edit ONLY the nodes they name inside the "KMLM switcher" group (never the VIX
    sleeve), on both window encodings;
  - an injected switch flag for forms the evaluator has no function for (votes, EMAs, macro): the switch
    condition becomes "price of __FLAGk__ > 1.5" on a pseudo-ticker that is 2.0 when the flag is on and
    1.0 when off. The pseudo-ticker is never held. Forms the evaluator CAN read are built both ways and
    must agree (gate in run_gates.py);
  - the corridor path: trade to target only when some holding is more than 10 points of the symphony
    from it; cost = bps x turnover, charged on the day of the trade (as Composer's backtest does).
"""
import copy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import shadow_runner as sr  # noqa: E402

COST = 5.856e-4               # fitted to Composer's KMLM backtest (research/crash, add. 39): per unit turnover
CORRIDOR = 0.10
FLAG = "__FLAG%d__"
POPS = ("QQQE", "VTV", "VOX", "TECL", "VOOG", "VOOV", "XLP", "TQQQ", "XLY", "FAS", "SPY")
DIPS = ("TQQQ", "SOXL", "SPXL", "LABU")


def approved():
    return sr.load_tree(sr.load_manifest()["KMLM"]["eras"][-1])


# ------------------------------------------------------------------ locating nodes
def block(tree):
    """the 75% "KMLM switcher" group (not the root, whose name also starts that way)"""
    hits = []

    def walk(n):
        if n.get("step") == "group" and (n.get("name") or "").strip() == "KMLM switcher":
            hits.append(n)
        for k in n.get("children") or []:
            walk(k)
    walk(tree)
    if len(hits) != 1:
        raise RuntimeError(f"{len(hits)} groups named 'KMLM switcher'")
    return hits[0]


def nodes(root, pred):
    out = []

    def walk(n):
        if pred(n):
            out.append(n)
        for k in n.get("children") or []:
            walk(k)
    walk(root)
    return out


def switch_node(tree):
    hit = nodes(block(tree), lambda n: n.get("step") == "if-child" and n.get("lhs-val") == "XLK"
                and n.get("rhs-val") == "KMLM" and not n.get("rhs-fixed-value?"))
    if len(hit) != 1:
        raise RuntimeError(f"{len(hit)} switch conditions")
    return hit[0]


def pick_nodes(tree):
    f = nodes(block(tree), lambda n: n.get("step") == "filter")
    if len(f) != 2:
        raise RuntimeError(f"{len(f)} ranked picks in the block")
    return f


def pop_nodes(tree):
    out = nodes(block(tree), lambda n: n.get("step") == "if-child" and n.get("rhs-fixed-value?")
                and n.get("lhs-fn") == "relative-strength-index" and n.get("comparator") == "gt")
    if tuple(n["lhs-val"] for n in out) != POPS:
        raise RuntimeError(f"pops are {[n['lhs-val'] for n in out]}")
    return out


def dip_nodes(tree):
    out = nodes(block(tree), lambda n: n.get("step") == "if-child" and n.get("rhs-fixed-value?")
                and n.get("lhs-fn") == "relative-strength-index" and n.get("comparator") == "lt")
    if tuple(n["lhs-val"] for n in out) != DIPS:
        raise RuntimeError(f"dips are {[n['lhs-val'] for n in out]}")
    return out


def set_window(node, side, n):
    """the window on BOTH encodings (PREREG G3), so no reader of the tree can see two values"""
    node[f"{side}-fn-params"] = dict(node.get(f"{side}-fn-params") or {}, window=int(n))
    node[f"{side}-window-days"] = int(n)


# ------------------------------------------------------------------ variants (each returns a new tree)
def v_switch_rsi(tree, n, picks=False):
    t = copy.deepcopy(tree)
    s = switch_node(t)
    set_window(s, "lhs", n)
    set_window(s, "rhs", n)
    if picks:
        for f in pick_nodes(t):
            set_window(f, "sort-by", n)
    return t


def v_switch_form(tree, lhs, rhs):
    """the switch condition as <fn, ticker, window> > <fn, ticker, window>; window None for current-price"""
    t = copy.deepcopy(tree)
    s = switch_node(t)
    for side, (fn, tk, w) in (("lhs", lhs), ("rhs", rhs)):
        s[f"{side}-fn"], s[f"{side}-val"] = fn, tk
        s.pop(f"{side}-fn-params", None)
        s.pop(f"{side}-window-days", None)
        if w is not None:
            set_window(s, side, w)
    s["comparator"], s["rhs-fixed-value?"] = "gt", False
    return t


def v_switch_flag(tree, k=0):
    """the switch condition read from pseudo-ticker __FLAGk__ (2.0 on, 1.0 off)"""
    t = copy.deepcopy(tree)
    s = switch_node(t)
    for key in ("lhs-fn-params", "lhs-window-days", "rhs-fn-params", "rhs-window-days", "rhs-fn"):
        s.pop(key, None)
    s.update({"lhs-fn": "current-price", "lhs-val": FLAG % k, "comparator": "gt", "rhs-val": "1.5",
              "rhs-fixed-value?": True})
    return t


def v_thresholds(tree, n, pops=None, dips=None):
    """pops / dips at window n with the given thresholds ({ticker: value}); None leaves that set as live"""
    t = copy.deepcopy(tree)
    for group, thr in ((pop_nodes(t), pops), (dip_nodes(t), dips)):
        if thr is None:
            continue
        for node in group:
            set_window(node, "lhs", n)
            node["rhs-val"] = repr(round(float(thr[node["lhs-val"]]), 4))
    return t


def v_split(tree, members):
    """Composer form of a window ensemble: the 75% block split equally across clones at each window"""
    t = copy.deepcopy(tree)
    b = block(t)
    inner = b["children"]
    if len(inner) != 1:
        raise RuntimeError("the block has more than one child")
    clones = []
    for n in members:
        c = copy.deepcopy(inner[0])
        holder = {"step": "group", "name": "KMLM switcher", "children": [c]}
        wrap = {"step": "root", "children": [holder]}
        s = switch_node(wrap)
        set_window(s, "lhs", n)
        set_window(s, "rhs", n)
        clones.append({"step": "group", "name": f"window {n}", "children": [c]})
    b["children"] = [{"step": "wt-cash-equal", "children": clones}]
    return t


# ------------------------------------------------------------------ indicators for injected flags
def rsi_series(p, w):
    """{day: Wilder RSI over all history}, None before max(60, w+1) changes: shadow_runner.indicator's values"""
    ds = sorted(p)
    out, ag, al = {ds[0]: None}, 0.0, 0.0
    for i in range(1, len(ds)):
        x = p[ds[i]] - p[ds[i - 1]]
        if i <= w:
            ag += max(x, 0) / w
            al += max(-x, 0) / w
        else:
            ag = (ag * (w - 1) + max(x, 0)) / w
            al = (al * (w - 1) + max(-x, 0)) / w
        out[ds[i]] = None if i < max(sr.RSI_MIN, w + 1) else (100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return out


def sma_series(p, w):
    ds = sorted(p)
    out, run = {}, 0.0
    for i, d in enumerate(ds):
        run += p[d]
        if i >= w:
            run -= p[ds[i - w]]
        out[d] = run / w if i >= w - 1 else None
    return out


def ema_series(p, w):
    """exponential average, alpha = 2/(w+1), seeded with the simple average of the first w closes"""
    ds = sorted(p)
    out, a, e = {}, 2.0 / (w + 1), None
    for i, d in enumerate(ds):
        if i < w - 1:
            out[d] = None
        elif i == w - 1:
            e = sum(p[x] for x in ds[:w]) / w
            out[d] = e
        else:
            e = a * p[d] + (1 - a) * e
            out[d] = e
    return out


def ret_series(p, w):
    ds = sorted(p)
    return {d: (p[d] / p[ds[i - w]] - 1) * 100 if i >= w else None for i, d in enumerate(ds)}


def prefill_rsi(sim, tree):
    """fill the evaluator's cache with every RSI the tree reads, in one pass per (ticker, window): the same
    values shadow_runner.indicator gives, 150x faster (checked in run_gates.py)"""
    want = set()

    def walk(n):
        if n.get("lhs-fn") == "relative-strength-index":
            want.add((n["lhs-val"], sr.window(n, "lhs")))
        if not n.get("rhs-fixed-value?") and n.get("rhs-fn") == "relative-strength-index":
            want.add((n["rhs-val"], sr.window(n, "rhs")))
        if n.get("step") == "filter" and n.get("sort-by-fn") == "relative-strength-index":
            for k in n.get("children") or []:
                if k.get("step") == "asset":
                    want.add((k["ticker"], sr.window(n, "sort-by")))
        for k in n.get("children") or []:
            walk(k)
    walk(tree)
    for t, w in want:
        for d, v in rsi_series(sim.p[t], w).items():
            sim.cache[("relative-strength-index", t, w, d)] = v


# ------------------------------------------------------------------ the path
def simulate(tree, P, start, end, flags=None, cost=COST, corridor=CORRIDOR, warm=300, fast=True):
    """{days, ret, target, held, turnover, trades}: ret[i] is the return of days[i] (close of days[i-1] to
    close of days[i]) less the cost of the trade made AT days[i]'s close. days[0] = start is the first
    decision; ret starts the session after it. flags: [{day: bool}] for __FLAG0__, __FLAG1__, ..."""
    sr.validate(tree)
    P = dict(P)
    for k, f in enumerate(flags or []):
        P[FLAG % k] = {d: (2.0 if v else 1.0) for d, v in f.items() if v is not None}
    tk = sr.tree_tickers(tree)
    missing = [t for t in tk if t not in P]
    if missing:
        raise RuntimeError(f"no prices for {missing}")
    run = sr.common_days(P, tk, end)
    if start not in run:
        start = next(d for d in run if d >= start)
    i0 = run.index(start)
    run = run[max(0, i0 - warm):]
    keep = [d for d in run if d >= start]
    sim = sr.Shadow({t: P[t] for t in tk})
    if fast:
        prefill_rsi(sim, tree)
    dec = sim.decide(tree, run, set(keep))
    out = {"days": [], "ret": [], "target": {}, "held": {}, "turnover": [], "trades": 0}
    held = None
    for i, d in enumerate(keep):
        tgt = dec[d][0]
        if tgt is None:
            raise RuntimeError(f"no decision on {d}: {dec[d][1]}")
        tgt = {t: w for t, w in tgt.items() if w > 1e-12}
        if held is None:
            new, to = dict(tgt), 0.0
        else:
            keys = set(held) | set(tgt)
            if max(abs(held.get(k, 0) - tgt.get(k, 0)) for k in keys) > corridor:
                to = sum(abs(held.get(k, 0) - tgt.get(k, 0)) for k in keys)
                new = dict(tgt)
                out["trades"] += 1
            else:
                new, to = held, 0.0
        if i:                                   # the cost of today's trade comes out of today's return
            out["ret"][-1] -= cost * to
            out["turnover"][-1] = to
        out["target"][d], out["held"][d] = tgt, dict(new)
        if i + 1 < len(keep):
            d1 = keep[i + 1]
            g = {t: P[t][d1] / P[t][d] for t in new}
            tot = sum(w * g[t] for t, w in new.items())
            out["days"].append(d1)
            out["ret"].append(tot - 1)
            out["turnover"].append(0.0)
            held = {t: w * g[t] / tot for t, w in new.items()}
    return out


def stats(r, ann=252):
    lvl = pk = 1.0
    mdd = 0.0
    for x in r:
        lvl *= 1 + x
        pk = max(pk, lvl)
        mdd = max(mdd, 1 - lvl / pk)
    m = sum(r) / len(r)
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    return {"cagr": lvl ** (ann / len(r)) - 1, "maxdd": mdd, "sharpe": m / sd * math.sqrt(ann) if sd else 0.0,
            "vol": sd * math.sqrt(ann), "n": len(r), "total": lvl - 1}


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else float("nan")
