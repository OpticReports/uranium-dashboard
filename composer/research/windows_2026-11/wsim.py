"""Variant builders and panels for the windows study of HG and the crash sleeve (PREREG.md).

Decisions come from shadow_runner's evaluator through kmlm_2026-11/ksim.simulate. This file only (a) finds
the nodes a variant names and changes their windows, (b) turns a test the evaluator has no function for
(an exponential average) into an injected flag, exactly as addendum 57 did, (c) builds the two price
panels, and (d) lists the pre-registered cells. Every locator refuses to run if the tree is not the shape
it expects."""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("kmlm_2026-11", "kmlm_synth_2026-11", "longrun"):
    sys.path.insert(0, os.path.join(HERE, "..", p))
import data as kdata  # noqa: E402
import ksim as ks  # noqa: E402
import ksynth as ky  # noqa: E402
import sdata  # noqa: E402

sr = ks.sr
END = "2026-11-19"
SPAN = {"HG": {"M": ("1991-04-01", "2006-07-17"), "R": ("2006-07-18", "2015-08-31"), "A": ("2015-09-01", END)},
        "SLEEVE": {"M": ("1994-06-01", "2008-01-31"), "R": ("2008-02-01", "2023-01-31"), "A": ("2023-02-01", END)}}
CACHE = kdata.SCRATCH + "/windows"
RSI, MA, CR, PX = "relative-strength-index", "moving-average-price", "cumulative-return", "current-price"


def approved(engine):
    return sr.load_tree(sr.load_manifest()[engine]["eras"][-1])


# ------------------------------------------------------------------ panels
def real_panel(engine):
    tk = sorted(sr.tree_tickers(approved(engine)))
    P = {t: kdata.series(t, END) for t in tk if t != "KMLM"}
    if "KMLM" in tk:
        P["KMLM"] = sdata.fund_tr(END)
    return P


def long_panel():
    """the repo's long panel with KMLM = the addendum-58 synthetic to 2020-12-01, then the real fund's
    corrected total return chained on"""
    import long_panel as lp
    P, _ = lp.build_long_prices()
    P = dict(P)
    exposure = json.load(open(os.path.join(HERE, "..", "kmlm_synth_2026-11", "out", "fidelity.json")))["exposure"]
    ky.set_calendar([d for d in P["SPY"] if d <= "2024-03-28"])
    syn = ky.level(ky.build(exposure, start="1986-01-01"))
    fund = sdata.fund_tr(END)
    cut = "2020-12-02"
    out = {d: v for d, v in syn.items() if d <= cut}
    k = out[cut] / fund[cut]
    out.update({d: v * k for d, v in fund.items() if d > cut})
    P["KMLM"] = out
    return P


# ------------------------------------------------------------------ locating nodes
def find(tree, n_expected, **want):
    def ok(n):
        if n.get("step") != want.get("step", "if-child") or n.get("is-else-condition?"):
            return False
        for k, v in want.items():
            if k == "step":
                continue
            key = k.replace("_", "-")
            if key == "fixed":
                if bool(n.get("rhs-fixed-value?")) != v:
                    return False
            elif n.get(key) != v:
                return False
        return True
    hit = ks.nodes(tree, ok)
    if len(hit) != n_expected:
        raise RuntimeError(f"{len(hit)} nodes for {want}, expected {n_expected}")
    return hit


def win(node, side):
    return sr.window(node, side)


def to_flag(node, k):
    """the node's test becomes 'pseudo-ticker __FLAGk__ > 1.5' (2.0 when the original test is true)"""
    for key in ("lhs-fn-params", "lhs-window-days", "rhs-fn-params", "rhs-window-days", "rhs-fn"):
        node.pop(key, None)
    node.update({"lhs-fn": PX, "lhs-val": ks.FLAG % k, "comparator": "gt", "rhs-val": "1.5", "rhs-fixed-value?": True})


def set_thr(node, v):
    node["rhs-val"] = repr(round(float(v), 4))


class HG:
    name = "HG"

    def __init__(self, tree):
        self.t = tree
        self.trend = find(tree, 1, lhs_fn=MA, lhs_val="TQQQ", rhs_fn=MA, rhs_val="TQQQ", comparator="gt")[0]
        self.cash = find(tree, 1, lhs_fn=PX, lhs_val="TQQQ", rhs_fn=MA, rhs_val="TQQQ", comparator="lt")[0]
        self.gate = find(tree, 2, lhs_fn=PX, lhs_val="SPY", rhs_fn=MA, rhs_val="SPY", comparator="gt")
        self.pop = find(tree, 1, lhs_fn=RSI, lhs_val="TQQQ", comparator="gt", fixed=True)[0]
        self.dip = find(tree, 1, lhs_fn=RSI, lhs_val="TQQQ", comparator="lt", fixed=True)[0]
        self.soxl = find(tree, 1, lhs_fn=RSI, lhs_val="SOXL", comparator="lt", fixed=True)[0]
        self.picks = find(tree, 4, step="filter", sort_by_fn=RSI)
        live = (win(self.trend, "lhs"), win(self.trend, "rhs"), win(self.cash, "rhs"), win(self.gate[0], "rhs"), win(self.gate[1], "rhs"),
                win(self.pop, "lhs"), win(self.dip, "lhs"), win(self.soxl, "lhs"), self.pop["rhs-val"], self.dip["rhs-val"], self.soxl["rhs-val"])
        if live != (10, 20, 20, 200, 200, 10, 10, 10, "80", "30", "30") or any(win(f, "sort-by") != 10 for f in self.picks):
            raise RuntimeError(f"HG is not the tree this study was registered on: {live}")
        self.tests = (self.pop, self.dip, self.soxl)


class SLEEVE:
    name = "SLEEVE"

    def __init__(self, tree):
        self.t = tree
        self.ih = find(tree, 1, lhs_fn=RSI, lhs_val="IEF", rhs_fn=RSI, rhs_val="PSQ")[0]
        self.hold = find(tree, 1, lhs_fn=RSI, lhs_val="LABD", rhs_val="KMLM") + find(tree, 1, lhs_fn=RSI, lhs_val="TMV", rhs_val="KMLM")
        self.rsi = find(tree, 8, lhs_fn=RSI, fixed=True)
        self.ret = find(tree, 13, lhs_fn=CR, fixed=True)
        self.picks = ks.nodes(tree, lambda n: n.get("step") == "filter" and n.get("sort-by-fn") == CR)
        live = (win(self.ih, "lhs"), win(self.ih, "rhs"), [win(h, "lhs") for h in self.hold], [win(h, "rhs") for h in self.hold],
                [(n["lhs-val"], win(n, "lhs")) for n in self.rsi], {win(n, "lhs") for n in self.ret}, {win(f, "sort-by") for f in self.picks}, len(self.picks))
        want = (8, 45, [20, 20], [10, 10], [("CORP", 15), ("CORP", 16), ("PEJ", 14), ("KIE", 10), ("KIE", 10), ("KIE", 14), ("LQD", 12), ("LQD", 14)], {1}, {1}, 15)
        if live != want:
            raise RuntimeError(f"SLEEVE is not the tree this study was registered on: {live}")


def matched(series, node, n_live, n_new, fn, lo, hi):
    """the threshold at window n_new crossed as often, over [lo, hi], as the node's live threshold at n_live"""
    f = ks.rsi_series if fn == RSI else ks.ret_series
    live, above = float(node["rhs-val"]), node["comparator"] == "gt"
    a = [v for d, v in f(series, n_live).items() if v is not None and lo <= d <= hi]
    b = sorted(v for d, v in f(series, n_new).items() if v is not None and lo <= d <= hi)
    share = sum((v > live) if above else (v < live) for v in a) / len(a)
    if share == 0:
        return 1e6 if above else -1e6
    q = (1 - share) if above else share
    return b[min(len(b) - 1, max(0, int(round(q * (len(b) - 1)))))]


# ------------------------------------------------------------------ the cells: {id: (family, grid key, tree, [flag makers])}
def ma(P, t, n, kind):
    return (ks.sma_series if kind == "sma" else ks.ema_series)(P[t], n)


def cross_flag(t, a, b, kind):
    def make(P):
        x, y = ma(P, t, a, kind), ma(P, t, b, kind)
        return {d: (None if x[d] is None or y[d] is None else x[d] > y[d]) for d in x}
    return make


def price_flag(t, n, kind, below):
    def make(P):
        m = ma(P, t, n, kind)
        return {d: (None if m[d] is None else ((P[t][d] < m[d]) if below else (P[t][d] > m[d]))) for d in m}
    return make


HA_PAIRS = ((3, 10), (5, 10), (5, 20), (8, 21), (10, 20), (10, 30), (10, 50), (15, 30), (20, 50), (20, 100), (50, 200))
HB_N = (5, 10, 15, 20, 30, 50, 100)
HC_K = (0.5, 1, 1.5, 2, 3, 5)
HD_N = (50, 100, 150, 200, 250, 300)
HE_N = (5, 7, 8, 9, 10, 11, 12, 14, 17, 20)
HF_N = (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 30)
HG_N = (5, 7, 10, 14, 20)


def hg_cells(Pcal):
    """Pcal: the long panel, for the matched thresholds (MODEL years only)"""
    base = approved("HG")
    lo, hi = SPAN["HG"]["M"]
    cells = {}

    def new():
        t = copy.deepcopy(base)
        return t, HG(t)

    def thr(h, n):
        for node in h.tests:
            set_thr(node, matched(Pcal[node["lhs-val"]], node, 10, n, RSI, lo, hi))

    for a, b in HA_PAIRS:
        if (a, b) != (10, 20):
            t, h = new()
            ks.set_window(h.trend, "lhs", a)
            ks.set_window(h.trend, "rhs", b)
            cells[f"HA.sma{a}x{b}"] = ("HA", "HAs", t, [])
        t, h = new()
        to_flag(h.trend, 0)
        cells[f"HA.ema{a}x{b}"] = ("HA", "HAe", t, [cross_flag("TQQQ", a, b, "ema")])
    for n in HB_N:
        if n != 20:
            t, h = new()
            ks.set_window(h.cash, "rhs", n)
            cells[f"HB.sma{n}"] = ("HB", "HBs", t, [])
        t, h = new()
        to_flag(h.cash, 0)
        cells[f"HB.ema{n}"] = ("HB", "HBe", t, [price_flag("TQQQ", n, "ema", True)])
    for k in HC_K:
        a, b = int(round(10 * k)), int(round(20 * k))
        if k != 1:
            t, h = new()
            ks.set_window(h.trend, "lhs", a)
            ks.set_window(h.trend, "rhs", b)
            ks.set_window(h.cash, "rhs", b)
            cells[f"HC.sma_x{k}"] = ("HC", "HCs", t, [])
        t, h = new()
        to_flag(h.trend, 0)
        to_flag(h.cash, 1)
        cells[f"HC.ema_x{k}"] = ("HC", "HCe", t, [cross_flag("TQQQ", a, b, "ema"), price_flag("TQQQ", b, "ema", True)])
    for n in HD_N:
        if n != 200:
            t, h = new()
            for g in h.gate:
                ks.set_window(g, "rhs", n)
            cells[f"HD.sma{n}"] = ("HD", "HDs", t, [])
        t, h = new()
        for g in h.gate:
            to_flag(g, 0)
        cells[f"HD.ema{n}"] = ("HD", "HDe", t, [price_flag("SPY", n, "ema", False)])
    for n in HE_N:
        if n == 10:
            continue
        for kind in ("m", "r"):
            t, h = new()
            if kind == "m":
                thr(h, n)
            for node in h.tests:
                ks.set_window(node, "lhs", n)
            cells[f"HE{kind}.rsi{n}"] = ("HE", "HE" + kind, t, [])
    for n in HF_N:
        if n != 10:
            t, h = new()
            for f in h.picks:
                ks.set_window(f, "sort-by", n)
            cells[f"HF.picks{n}"] = ("HF", "HF", t, [])
    for n in HG_N:
        if n != 10:
            t, h = new()
            thr(h, n)
            for node in h.tests:
                ks.set_window(node, "lhs", n)
            for f in h.picks:
                ks.set_window(f, "sort-by", n)
            cells[f"HG.all{n}"] = ("HG", "HG", t, [])
    return base, cells


SA_N = (4, 5, 6, 7, 8, 9, 10, 12, 14, 20)
SB_N = (20, 30, 40, 45, 50, 60, 90)
SC_P = ((4, 22), (6, 34), (8, 45), (10, 56), (12, 68), (16, 90))
SD_N = (10, 14, 17, 20, 25, 30, 40)
SE_N = (5, 7, 10, 14, 20, 30)
SF_K = (0.5, 0.7, 1, 1.4, 2)
SG_N = (1, 2, 3, 5)


def sleeve_cells(Pcal):
    base = approved("SLEEVE")
    lo, hi = SPAN["SLEEVE"]["M"]
    cells = {}

    def new():
        t = copy.deepcopy(base)
        return t, SLEEVE(t)

    for n in SA_N:
        if n != 8:
            t, s = new()
            ks.set_window(s.ih, "lhs", n)
            cells[f"SA.ief{n}"] = ("SA", "SA", t, [])
    for n in SB_N:
        if n != 45:
            t, s = new()
            ks.set_window(s.ih, "rhs", n)
            cells[f"SB.psq{n}"] = ("SB", "SB", t, [])
    for a, b in SC_P:
        if (a, b) != (8, 45):
            t, s = new()
            ks.set_window(s.ih, "lhs", a)
            ks.set_window(s.ih, "rhs", b)
            cells[f"SC.{a}x{b}"] = ("SC", "SC", t, [])
    for n in SD_N:
        if n != 20:
            t, s = new()
            for hnode in s.hold:
                ks.set_window(hnode, "lhs", n)
            cells[f"SD.hold{n}"] = ("SD", "SD", t, [])
    for n in SE_N:
        if n != 10:
            t, s = new()
            for hnode in s.hold:
                ks.set_window(hnode, "rhs", n)
            cells[f"SE.kmlm{n}"] = ("SE", "SE", t, [])
    for k in SF_K:
        if k == 1:
            continue
        for kind in ("m", "r"):
            t, s = new()
            for node in s.rsi:
                w0 = win(node, "lhs")
                w1 = max(2, int(round(w0 * k)))
                if kind == "m":
                    set_thr(node, matched(Pcal[node["lhs-val"]], node, w0, w1, RSI, lo, hi))
                ks.set_window(node, "lhs", w1)
            cells[f"SF{kind}.x{k}"] = ("SF", "SF" + kind, t, [])
    for n in SG_N:
        if n == 1:
            continue
        t, s = new()
        for node in s.ret:
            set_thr(node, matched(Pcal[node["lhs-val"]], node, 1, n, CR, lo, hi))
            ks.set_window(node, "lhs", n)
        cells[f"SGt.ret{n}"] = ("SG", "SGt", t, [])
        t, s = new()
        for f in s.picks:
            ks.set_window(f, "sort-by", n)
        cells[f"SGp.rank{n}"] = ("SG", "SGp", t, [])
    return base, cells


GRIDS = {
    "HAs": [f"HA.sma{a}x{b}" for a, b in HA_PAIRS], "HAe": [f"HA.ema{a}x{b}" for a, b in HA_PAIRS],
    "HBs": [f"HB.sma{n}" for n in HB_N], "HBe": [f"HB.ema{n}" for n in HB_N],
    "HCs": [f"HC.sma_x{k}" for k in HC_K], "HCe": [f"HC.ema_x{k}" for k in HC_K],
    "HDs": [f"HD.sma{n}" for n in HD_N], "HDe": [f"HD.ema{n}" for n in HD_N],
    "HEm": [f"HEm.rsi{n}" for n in HE_N], "HEr": [f"HEr.rsi{n}" for n in HE_N],
    "HF": [f"HF.picks{n}" for n in HF_N], "HG": [f"HG.all{n}" for n in HG_N],
    "SA": [f"SA.ief{n}" for n in SA_N], "SB": [f"SB.psq{n}" for n in SB_N], "SC": [f"SC.{a}x{b}" for a, b in SC_P],
    "SD": [f"SD.hold{n}" for n in SD_N], "SE": [f"SE.kmlm{n}" for n in SE_N],
    "SFm": [f"SFm.x{k}" for k in SF_K], "SFr": [f"SFr.x{k}" for k in SF_K],
    "SGt": [f"SGt.ret{n}" for n in SG_N], "SGp": [f"SGp.rank{n}" for n in SG_N],
}
LIVE = {"HA.sma10x20", "HB.sma20", "HC.sma_x1", "HD.sma200", "HEm.rsi10", "HEr.rsi10", "HF.picks10", "HG.all10", "SA.ief8", "SB.psq45",
        "SC.8x45", "SD.hold20", "SE.kmlm10", "SFm.x1", "SFr.x1", "SGt.ret1", "SGp.rank1"}       # grid positions that ARE the live rule


def simulate(tree, P, start, end, makers=()):
    flags = [m(P) for m in makers]
    return ks.simulate(tree, P, start, end, flags=flags or None, corridor=0.0)
