"""Post hoc, from the statistics review (review B): how much of each headline survives (a) every trade
filled ONE CLOSE LATER than the close its signal is read from (a bound, not the expected live fill: the
engines decide near 15:51 and fill at that close), (b) a test that allows for the state being tied to
volatility (Newey-West, 63 lags) and a regime count, (c) dropping the years or the regime that carry it.
Writes out/robust.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m1_run as m1  # noqa: E402
import m2_followup as m2  # noqa: E402  (gate_off; re-writes followup.json)

md, w, ks, S, E, TB, pos, days = m1.md, m1.w, m1.ks, m1.S, m1.E, m1.TB, m1.pos, m1.days
COST = m1.COST
W = {"HG": 0.341, "KMLM": 0.341, "SLEEVE": 0.318}
prev = {b: a for a, b in zip(days, days[1:])}
out = {}


# ---------------------------------------------------------------- one close late
def late_path(held, P, cached, label):
    """held[d] = weights after the trade at close d. Same close: held[d] earns d -> d+1. One close late:
    the trade decided at d fills at d+1, so held[d-1] earns d -> d+1. Costs as in the cached path."""
    hd = sorted(held)
    same, late, to = {}, {}, {}
    for i in range(len(hd) - 1):
        d, d1 = hd[i], hd[i + 1]
        h, hp = held[d], (held[hd[i - 1]] if i else held[d])
        to[d] = sum(abs(h.get(k, 0) - hp.get(k, 0)) for k in set(h) | set(hp))
        same[d1] = sum(x * (P[t][d1] / P[t][d] - 1) for t, x in h.items())
        if all(t in P and d in P[t] and d1 in P[t] for t in hp):
            # gross of the late holdings, less the cost the study's path paid that day (cached is net, same is gross)
            late[d1] = sum(x * (P[t][d1] / P[t][d] - 1) for t, x in hp.items()) + ((cached[d1] - same[d1]) if d1 in cached else 0.0)
    gap = [abs(same[d] - cached[d]) for d in same if d in cached]
    print(f"  {label}: {len(same)} sessions; rebuilt-from-holdings vs cached path, median gap {np.median(gap):.6f}, max {max(gap):.5f}; late path missing on {len(same) - len(late)}", flush=True)
    return late, to


PL = w.long_panel()
LATE, TO = {}, {}
for eng in ("HG", "SLEEVE"):
    o = json.load(open(w.CACHE + f"/cells_{eng}.json"))
    b = o["cells"]["base"]
    LATE[eng], TO[eng] = {}, {}
    for part, P, dl in (("long", PL, o["long_days"]), ("real", w.real_panel(eng), o["real_days"])):
        la, to = late_path(b[part]["held"], P, dict(zip(dl, b[part]["ret"])), f"{eng}.{part}")
        LATE[eng].update(la)
        TO[eng].update(to)
import q1_cells as q1  # noqa: E402
tree = ks.approved()
Pab = dict(w.kdata.panel_ab(md.END), KMLM=w.sdata.fund_tr(md.END))
LATE["KMLM"], TO["KMLM"] = {}, {}
for part, P, a, b_ in (("long", PL, "1991-04-01", "2020-12-01"), ("real", Pab, q1.B_START, q1.END)):
    fl = q1.switch_flags(P)["F1a.rsi10"]
    r = ks.simulate(tree, P, a, b_, flags=[fl[0]])
    cached = {d: E["KMLM"][d] for d in r["days"] if d in E["KMLM"]}
    print("  KMLM", part, "re-simulated vs the study's path, max gap", max(abs(x - cached[d]) for d, x in zip(r["days"], r["ret"]) if d in cached), flush=True)
    la, to = late_path(r["held"], P, cached, f"KMLM.{part}")
    LATE["KMLM"].update(la)
    TO["KMLM"].update(to)
LATE = {e: {d: v for d, v in LATE[e].items() if d in E[e]} for e in LATE}
LATE["BOOK"] = {d: sum(W[e] * LATE[e][d] for e in W) for d in E["BOOK"] if all(d in LATE[e] for e in W)}


# ---------------------------------------------------------------- tests
def nw(s, lr, lags=63):
    x = s - s.mean()
    b = (x @ lr) / (x @ x)
    z = x * (lr - lr.mean() - b * x)
    s0 = z @ z
    for k in range(1, lags + 1):
        s0 += 2 * (1 - k / (lags + 1)) * (z[k:] @ z[:-k])
    t = b / (math.sqrt(s0) / (x @ x))
    return float(math.erfc(abs(t) / math.sqrt(2)))


def regimes(s, lr, gap=63):
    on = np.flatnonzero(s == 1)
    if len(on) == 0:
        return None
    cut = np.flatnonzero(np.diff(on) > gap)
    groups = np.split(on, cut + 1)
    off = lr[s == 0].mean()
    return {"regimes": len(groups), "regimes_above_off_rate": int(sum(lr[g].mean() > off for g in groups)), "regimes_of_20_days_or_more": int(sum(len(g) >= 20 for g in groups))}


def row(s, r):
    """on/off growth, shifted-state p, Newey-West p, regime count"""
    ok = ~np.isnan(s)
    s, r = s[ok], r[ok]
    res = m1.map_row(s, r)
    if res is None:
        return None
    o = res[0]
    lr = np.log1p(r)
    o["p_newey_west_63"] = nw(s, lr)
    o["p_newey_west_10"] = nw(s, lr, 10)
    o.update(regimes(s, lr))
    return o


def both(target, ds, s):
    """the same row on the study's path and on the one-close-late path, on the days both exist"""
    ds2 = [d for d in ds if d in LATE[target]] if target in LATE else ds
    k = np.array([d in set(ds2) for d in ds])
    same = row(s, np.array([E[target][d] for d in ds])) if target in E else None
    late = row(s[k], np.array([LATE[target][d] for d in ds2])) if target in LATE else None
    return {"same_close": same, "one_close_late": late}


def st(sid, ds):
    return S[sid][np.array([pos[d] for d in ds])]


SPL = {"BOOK": {"verdict": None, "real": None, "shape": None, "2015-06..2020-12": ("2015-06-01", "2020-12-02")},
       "HG": {"verdict": None, "real": None, "shape": None}, "KMLM": {"verdict": None, "shape": None}, "SLEEVE": {"verdict": None, "real": None, "shape": None}}


def days_of(target, which):
    if SPL[target][which] is None:
        return m1.sample(target, which)[0]
    lo, hi = SPL[target][which]
    return [d for d in sorted(E[target]) if lo <= d < hi and d in TB]


out["t1"], out["gold"] = {}, {}
for target in SPL:
    for which in SPL[target]:
        ds = days_of(target, which)
        out["t1"][f"{target}.{which}"] = both(target, ds, st("T1", ds))
        out["gold"][f"{target}.{which}"] = both(target, ds, st("F_GOLD", ds))
ds = days_of("BOOK", "verdict")
for sid in ("F_LIQUIDITY", "L2", "F_DOLLAR", "F_CREDIT", "C1", "M1", "M3", "G1", "G2", "G3", "G4", "G5"):
    out.setdefault("book_verdict", {})[sid] = both("BOOK", ds, st(sid, ds))
    t1, x = np.nan_to_num(st("T1", ds)), np.nan_to_num(st(sid, ds))
    out["book_verdict"][sid]["share_of_on_days_with_T1_on"] = float(t1[x == 1].mean()) if x.sum() else None
dsh = days_of("BOOK", "shape")
out["book_shape"] = {sid: both("BOOK", dsh, st(sid, dsh)) for sid in ("C1", "M1", "M3", "G2")}
# ---- T1 on the book: years, concentration, the session after a trade
lr = np.log1p(np.array([E["BOOK"][d] for d in ds]))
s = np.nan_to_num(st("T1", ds))
yrs = sorted({d[:4] for d in ds})
ym = {y: np.array([d[:4] == y for d in ds]) for y in yrs}
by = {y: {"on_days": int(s[ym[y]].sum()), "on_log": float(lr[ym[y] & (s == 1)].sum()), "on_rate": float(lr[ym[y] & (s == 1)].mean() * 252) if s[ym[y]].sum() else None,
          "off_rate": float(lr[ym[y] & (s == 0)].mean() * 252) if (s[ym[y]] == 0).sum() else None} for y in yrs}
keep = np.array([d[:4] not in ("2020", "2022") for d in ds])
srt = np.sort(lr[s == 1])[::-1]
out["t1_book"] = {"by_year": by, "years_with_both": int(sum(1 for v in by.values() if v["on_rate"] is not None and v["off_rate"] is not None and v["on_days"] >= 5)),
                  "years_on_rate_higher": int(sum(1 for v in by.values() if v["on_rate"] is not None and v["off_rate"] is not None and v["on_days"] >= 5 and v["on_rate"] > v["off_rate"])),
                  "share_of_on_days_2020_2022": float((s[~keep]).sum() / s.sum()), "share_of_on_log_2020_2022": float(lr[~keep & (s == 1)].sum() / lr[s == 1].sum()),
                  "without_2020_2022": row(s[keep], np.expm1(lr[keep])), "share_of_on_log_from_20_best_days": float(srt[:20].sum() / srt.sum()),
                  "mean_over_vol_on": float(lr[s == 1].mean() / lr[s == 1].std() * math.sqrt(252)), "mean_over_vol_off": float(lr[s == 0].mean() / lr[s == 0].std() * math.sqrt(252))}
out["after_trade"] = {}
for e, which in (("HG", "verdict"), ("SLEEVE", "verdict"), ("KMLM", "verdict")):
    de = m1.sample(e, which)[0]
    le = np.log1p(np.array([E[e][d] for d in de]))
    se = np.nan_to_num(st("T1", de))
    tr = np.array([TO[e].get(prev.get(d), 0.0) > 0.05 for d in de])
    on = se == 1
    out["after_trade"][e] = {"share_of_T1_on_growth_in_session_after_a_trade": float(le[on & tr].sum() / le[on].sum()), "share_of_T1_on_days_after_a_trade": float(tr[on].mean())}
# ---- the book as a whole, same close vs one close late
dl = [d for d in ds if d in LATE["BOOK"]]
g = lambda x: float(np.log1p(x).mean() * 252)                                # noqa: E731
out["book_late"] = {"n": len(dl), "same_close": [g(np.array([E["BOOK"][d] for d in dl])), float(m1.maxdd(np.array([E["BOOK"][d] for d in dl])))],
                    "one_close_late": [g(np.array([LATE["BOOK"][d] for d in dl])), float(m1.maxdd(np.array([LATE["BOOK"][d] for d in dl])))],
                    "by_engine": {e: [g(np.array([E[e][d] for d in dl])), g(np.array([LATE[e][d] for d in dl]))] for e in W}}
# ---- gate off: the other two engines, same close vs late; overlap with T1; the gated tree itself
out["x1"] = {}
for which, lo, hi in (("verdict", "2015-06-01", "9999"), ("real_2021_06_on", "2021-06-02", "9999"), ("mostly_real_2015_2020", "2015-06-01", "2020-12-02"), ("shape", "1994-06-01", "2015-06-01")):
    dx = [d for d in sorted(E["BOOK"]) if lo <= d < hi and d in LATE["KMLM"] and d in LATE["SLEEVE"]]
    sx = np.array([np.nan if m2.gate_off.get(prev.get(d)) is None else float(m2.gate_off[prev[d]]) for d in dx])
    oth = lambda src: np.array([(0.341 * src["KMLM"][d] + 0.318 * src["SLEEVE"][d]) / 0.659 for d in dx])   # noqa: E731
    out["x1"][which] = {"same_close": row(sx, oth(E)), "one_close_late": row(sx, oth(LATE)), "same_reading_as_T1": float(np.mean(np.nan_to_num(sx) == np.nan_to_num(st("T1", dx))))}
out["gate"] = {}
for which, lo, hi in (("2006-07 on", "2006-07-18", "9999"), ("1991-2006", "1991-04-01", "2006-07-18"), ("2015-09 on", "2015-09-01", "9999")):
    dg = [d for d in sorted(E["HG"]) if lo <= d < hi and d in TB and m2.gate_off.get(prev.get(d)) is True and d in m2.m1.E["HG"]]
    out["gate"][which] = {"gate_off_days": len(dg), "live_gated_tree_less_tbills_per_yr": float(np.log1p(np.array([E["HG"][d] - TB[d] for d in dg])).mean() * 252)}
# ---- gold: without its largest regime
gs = np.nan_to_num(st("F_GOLD", ds))
on = np.flatnonzero(gs == 1)
grp = max(np.split(on, np.flatnonzero(np.diff(on) > 63) + 1), key=lambda q: lr[q].sum())      # the regime that earned the most
kg = np.ones(len(ds), bool)
kg[grp[0]:grp[-1] + 1] = False
dlk = [d for d, k in zip(ds, kg) if k and d in LATE["BOOK"]]
out["gold_regime"] = {"from": ds[grp[0]], "to": ds[grp[-1]], "on_days": int(len(grp)), "all_on_days": int(gs.sum()), "rate_in_regime": float(lr[grp].mean() * 252), "without": row(gs[kg], np.expm1(lr[kg])),
                      "share_of_on_log": float(lr[grp].sum() / lr[gs == 1].sum())}
# ---- the three single states that agree in sign on both stretches, and the shock ladder (X3)
out["counts"] = {"T1_on_days": int(s.sum()), "gate_off_days_verdict": int(np.nansum(np.array([float(bool(m2.gate_off.get(prev.get(d)))) for d in ds])))}
# ---- dollar: where its fall cut comes from
r = np.array([E["BOOK"][d] for d in ds])
fl = m1.falls(r, 1)[0]
lvl = np.cumprod(1 + r)
pk = int(np.argmax(lvl[:fl[2] + 1]))
out["dollar"] = {"book_deepest_fall": [ds[pk], ds[fl[2]], float(fl[0])], "share_of_that_fall_with_dollar_on": float(np.nan_to_num(st("F_DOLLAR", ds))[pk + 1:fl[2] + 1].mean())}
# ---- volume on Holy Grail
dv = m1.sample("HG", "verdict")[0]
sv = st("F_VOLUME", dv)
lv = np.log1p(np.array([E["HG"][d] for d in dv]))
onv = np.nan_to_num(sv) == 1
tv = np.sort(lv[onv])[::-1]
out["volume_hg"] = dict(both("HG", dv, sv), on_days=int(onv.sum()), share_of_on_log_from_3_best_days=float(tv[:3].sum() / tv.sum()))
# ---- growth of $1, the study's path against one close late (2015-06 on), for the chart
cur = {}
for e in ("BOOK", "HG", "KMLM", "SLEEVE"):
    a_, b_ = np.cumsum(np.log1p([E[e][d] for d in dl])), np.cumsum(np.log1p([LATE[e][d] for d in dl]))
    cur[e] = {"same_close": [[d, round(float(math.exp(v)), 4)] for d, v in list(zip(dl, a_))[::5]], "one_close_late": [[d, round(float(math.exp(v)), 4)] for d, v in list(zip(dl, b_))[::5]]}
out["curves"] = cur
json.dump(out, open(os.path.join(HERE, "out", "robust.json"), "w"), indent=1)
f = lambda v: None if v is None else (round(v["on_per_yr"], 2), round(v["off_per_yr"], 2), round(v["diff_per_yr"], 3), "shift", round(v["p_two_sided"], 4), "nw", round(v["p_newey_west_63"], 4), round(v["p_newey_west_10"], 4), "reg", v["regimes_above_off_rate"], v["regimes"])   # noqa: E731
for k, v in out["t1"].items():
    print("T1", k, "same", f(v["same_close"]), "| late", f(v["one_close_late"]))
for k, v in out["gold"].items():
    if k.startswith("BOOK") or k.endswith("verdict"):
        print("GOLD", k, "same", f(v["same_close"]), "| late", f(v["one_close_late"]))
for k, v in out["book_verdict"].items():
    print("BOOK", k, "same", f(v["same_close"]), "| late", f(v["one_close_late"]), "T1 overlap", v["share_of_on_days_with_T1_on"])
for k, v in out["book_shape"].items():
    print("SHAPE", k, f(v["same_close"]), "| late", f(v["one_close_late"]))
for k, v in out["x1"].items():
    print("X1", k, "same", f(v["same_close"]), "| late", f(v["one_close_late"]), "=T1", round(v["same_reading_as_T1"], 3))
print({k: v for k, v in out["t1_book"].items() if k not in ("by_year", "without_2020_2022")}, "without 2020/2022:", f(out["t1_book"]["without_2020_2022"]))
print(out["after_trade"], out["book_late"], out["gate"], out["gold_regime"]["from"], out["gold_regime"]["to"], out["gold_regime"]["on_days"], f(out["gold_regime"]["without"]), out["dollar"])
print("VOL", f(out["volume_hg"]["same_close"]), f(out["volume_hg"]["one_close_late"]), out["volume_hg"]["on_days"], out["volume_hg"]["share_of_on_log_from_3_best_days"])
