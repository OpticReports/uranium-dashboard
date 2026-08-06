#!/usr/bin/env python3
"""Generic Composer symphony-tree simulator (Phase B of the synthetic-history
build, results.md addendum 27).

Semantics (validated against Composer backtests; see fidelity gates):
- Daily evaluation: target weights decided at close t-1 from data through
  t-1, position earns the t-1 -> t return (same convention that reproduced
  the TSMOM prototype at r=0.9987).
- Indicators: current-price, moving-average-price(w), cumulative-return(w),
  standard-deviation-return(w), relative-strength-index(w) — RSI method
  (Wilder vs Cutler) selected per validation; default window 10.
- Steps: root/group/wt-cash-equal (equal split across children),
  wt-cash-specified (explicit weights), if/if-child (first true branch,
  else-branch fallback), filter (sort-by-fn, select top/bottom n), asset.
"""
import json, math

DEFAULT_W = 10

class Sim:
    def __init__(self, prices, rsi_method="cutler"):
        """prices: {ticker: {date: close}} — spliced real+synthetic series."""
        self.p = prices
        self.days = {t: sorted(d) for t, d in prices.items()}
        self.idx = {t: {d: i for i, d in enumerate(ds)} for t, ds in self.days.items()}
        self.rsi_method = rsi_method
        self._cache = {}

    def _series(self, tick, day, n):
        ds = self.days[tick]; i = self.idx[tick].get(day)
        if i is None or i - n < 0: return None
        return [self.p[tick][d] for d in ds[i-n:i+1]]

    def ind(self, fn, tick, window, day):
        key = (fn, tick, window, day)
        if key in self._cache: return self._cache[key]
        w = int(window or DEFAULT_W)
        v = None
        if fn == "current-price":
            v = self.p[tick].get(day)
        elif fn == "moving-average-price":
            s = self._series(tick, day, w-1)
            if s: v = sum(s)/len(s)
        elif fn == "cumulative-return":
            s = self._series(tick, day, w)
            if s: v = s[-1]/s[0] - 1
            if v is not None: v *= 100.0
        elif fn == "standard-deviation-return":
            s = self._series(tick, day, w)
            if s:
                r = [s[i]/s[i-1]-1 for i in range(1, len(s))]
                m = sum(r)/len(r)
                v = math.sqrt(sum((x-m)**2 for x in r)/len(r)) * 100.0
        elif fn == "relative-strength-index":
            s = self._series(tick, day, w if self.rsi_method == "cutler" else 250)
            if s and len(s) >= w+1:
                r = [s[i]-s[i-1] for i in range(1, len(s))]
                if self.rsi_method == "cutler":
                    g = [max(x,0) for x in r[-w:]]; l = [max(-x,0) for x in r[-w:]]
                    ag, al = sum(g)/w, sum(l)/w
                else:  # wilder
                    g = [max(x,0) for x in r]; l = [max(-x,0) for x in r]
                    ag, al = sum(g[:w])/w, sum(l[:w])/w
                    for x in r[w:]:
                        ag = (ag*(w-1) + max(x,0))/w
                        al = (al*(w-1) + max(-x,0))/w
                v = 100.0 if al == 0 else 100 - 100/(1 + ag/al)
        self._cache[key] = v
        return v

    def cond(self, n, day):
        lhs = self.ind(n["lhs-fn"], n["lhs-val"], (n.get("lhs-fn-params") or {}).get("window"), day)
        if n.get("rhs-fixed-value?"):
            rhs = float(n["rhs-val"])
        else:
            rhs = self.ind(n.get("rhs-fn") or n["lhs-fn"], n["rhs-val"],
                           (n.get("rhs-fn-params") or {}).get("window"), day)
        if lhs is None or rhs is None: return False
        return lhs > rhs if n["comparator"] == "gt" else lhs < rhs

    def weights(self, node, day, w=1.0, out=None):
        if out is None: out = {}
        step = node.get("step")
        kids = node.get("children") or []
        if step == "asset":
            out[node["ticker"]] = out.get(node["ticker"], 0.0) + w
        elif step in ("root", "group"):
            for k in kids: self.weights(k, day, w, out)
        elif step == "wt-cash-equal":
            for k in kids: self.weights(k, day, w/len(kids), out)
        elif step == "wt-cash-specified":
            tot = 0.0; ws = []
            for k in kids:
                kw = k.get("weight")
                x = (float(kw["num"])/float(kw.get("den", 100))) if isinstance(kw, dict) else float(kw or 0)
                ws.append(x); tot += x
            for k, x in zip(kids, ws):
                self.weights(k, day, w*(x/tot if tot else 0), out)
        elif step == "if":
            for k in kids:
                if k.get("is-else-condition?"):
                    continue
                if self.cond(k, day):
                    for kk in k.get("children") or []: self.weights(kk, day, w, out)
                    return out
            for k in kids:
                if k.get("is-else-condition?"):
                    for kk in k.get("children") or []: self.weights(kk, day, w, out)
            return out
        elif step == "filter":
            scored = []
            for k in kids:
                if k.get("step") == "asset":
                    s = self.ind(node["sort-by-fn"], k["ticker"],
                                 (node.get("sort-by-fn-params") or {}).get("window"), day)
                else:
                    # group child: metric computed on the subtree's simulated
                    # value index (tracked in self.sub during run())
                    s = self.sub_metric(k["id"], node["sort-by-fn"],
                                        (node.get("sort-by-fn-params") or {}).get("window"), day)
                if s is not None: scored.append((s, k))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=(node.get("select-fn") == "top"))
                n_sel = int(node.get("select-n") or 1)
                for s, k in scored[:n_sel]:
                    self.weights(k, day, w/n_sel, out)
        return out

    def _find_filter_groups(self, tree):
        subs = {}
        def walk(n):
            if n.get("step") == "filter":
                for k in n.get("children") or []:
                    if k.get("step") != "asset":
                        subs[k["id"]] = k
            for k in n.get("children") or []: walk(k)
        walk(tree)
        return subs

    def sub_metric(self, node_id, fn, window, day):
        hist = self.sub.get(node_id)
        if not hist: return None
        w = int(window or DEFAULT_W)
        vals = [v for d, v in hist if d <= day][-(w+1):]
        if len(vals) < w+1: return None
        if fn == "standard-deviation-return":
            import math as _m
            r = [vals[i]/vals[i-1]-1 for i in range(1, len(vals))]
            m = sum(r)/len(r)
            return _m.sqrt(sum((x-m)**2 for x in r)/len(r)) * 100.0
        if fn == "cumulative-return":
            return (vals[-1]/vals[0] - 1) * 100.0
        return None

    def run(self, tree, days):
        """days: sorted trading days (must exist in all needed series).
        Returns {day: portfolio_return} using close(t-1) decisions."""
        rets = {}
        subs = self._find_filter_groups(tree)
        self.sub = {sid: [(days[0], 1.0)] for sid in subs}
        for i in range(1, len(days)):
            d0, d1 = days[i-1], days[i]
            # update tracked subtree indices first (their own close-t-1 weights)
            for sid, sub_tree in subs.items():
                sw = self.weights(sub_tree, d0)
                tot_s = sum(sw.values())
                sr = 0.0
                for t, x in sw.items():
                    p0, p1 = self.p[t].get(d0), self.p[t].get(d1)
                    if p0 and p1: sr += (x/tot_s if tot_s else 0) * (p1/p0 - 1)
                self.sub[sid].append((d1, self.sub[sid][-1][1] * (1 + sr)))
            w = self.weights(tree, d0)
            tot = sum(w.values())
            r = 0.0
            for t, x in w.items():
                p0, p1 = self.p[t].get(d0), self.p[t].get(d1)
                if p0 and p1: r += (x/tot if tot else 0) * (p1/p0 - 1)
            rets[d1] = r
        return rets
