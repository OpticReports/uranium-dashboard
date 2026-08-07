"""RESEARCH ROUND 2: switching/scaling rules on the LEAK-FREE harness.

Pre-registered BEFORE any OOS look (see RESEARCH_SWITCH.md round-2 section):
- Data: extended Bitstamp 4h 2020-06->present; trading window 2021-01->end.
- Discipline: signals from CLOSED bars only; the rule for step k uses state
  known at step k-1's exit. IS = first 60% of steps (tune), OOS = last 40%
  (frozen). Statics include BOTH lev variants AND static blend-weight
  variants, so weight-switchers must beat the best static weight.
- Promotion bar (registered): OOS MAR > best-static OOS MAR + 0.25 AND
  full MAR > best-of-N selection-noise q95 for the N rules tried here.
- Rule families (N ~ 21): V vol-target lev (continuous), T slow-trend lev,
  W blend-weight regime switching, C combo score (bear+vol), D book-dd.
"""
import csv, json, os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay                         # noqa: E402
from app.main import ENGINE                                      # noqa: E402
from app.config import settings                                  # noqa: E402

EXT = ("/tmp/claude-0/-home-user-uranium-dashboard/"
       "12c903ed-4550-5fbe-8b7c-b52480531ae3/scratchpad/bars_4h_btcusd_ext.csv")
bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(EXT))]
from datetime import datetime, timezone
T0 = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
T1 = bars[-1].ts
res = run_replay(bars, ENGINE.books_cfg, ENGINE.scfg, ENGINE.tcfg,
                 start_ts=T0, end_ts=T1, cash_apy=settings.cash_apy)
b3, b4 = res.books["S3"], res.books["S4"]
evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
             + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
p3 = p4 = 1.0
ts_l, which_l, raw_l = [], [], []          # raw = unweighted book step return
for ts, w, ratio in evs:
    if w == "P":
        raw_l.append(ratio / p3 - 1); p3 = ratio
    else:
        raw_l.append(ratio / p4 - 1); p4 = ratio
    ts_l.append(ts); which_l.append(w)
ts_arr = np.array(ts_l); raw = np.array(raw_l)
isP = np.array([w == "P" for w in which_l])
N = len(raw)
SPLIT_I = int(N * 0.6)
SPLIT_T = ts_arr[SPLIT_I]
closes = np.array([b.close for b in bars]); bts = np.array([b.ts for b in bars])

def _win(t, look):
    i = int(np.searchsorted(bts, t, "right") - 1)
    return closes[max(0, i - look):i]                     # CLOSED bars only

def sig_vol(t, look):
    w = _win(t, look)
    rr = np.diff(np.log(w))
    return float(np.std(rr) * np.sqrt(6 * 365)) if len(rr) > 10 else np.nan

def sig_dist(t, look):
    w = _win(t, look)
    return float(w[-1] / np.mean(w) - 1) if len(w) > 10 else 0.0

VOL120 = np.array([sig_vol(t, 120) for t in ts_arr])
VOL180 = np.array([sig_vol(t, 180) for t in ts_arr])
D200 = np.array([sig_dist(t, 1200) for t in ts_arr])
D100 = np.array([sig_dist(t, 600) for t in ts_arr])
is_m = np.arange(N) < SPLIT_I

def run(levs, wts):
    """levs[k], wts[k] = leverage and w_trend applied to step k (decided at
    k-1). Returns (full, is, oos) stat tuples."""
    def seg(sl):
        eq = peak = 1.0; mdd = 0.0
        for k in sl:
            w_eff = wts[k] if not isP[k] else (1 - wts[k])
            eq *= 1 + levs[k] * w_eff * raw[k] / 1.0
            peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
        yrs = (ts_arr[sl][-1] - ts_arr[sl][0]) / (365.25 * 86400) if len(sl) > 1 else 1
        c = eq ** (1 / yrs) - 1
        return round(100 * (eq - 1), 1), round(100 * mdd, 1), \
            round(c / abs(mdd), 2) if mdd < 0 else None
    return seg(range(N)), seg(range(SPLIT_I)), seg(range(SPLIT_I, N))

def lagged(arr, default):
    out = np.empty(N); out[0] = default
    out[1:] = arr[:-1]
    return out

RULES = {}
# statics: lev x weight grid (baselines every switcher must beat)
for lv in (1.5, 2.0):
    for wt in (0.15, 0.25, 0.40):
        RULES[f"static L{lv} w{wt}"] = (np.full(N, lv), np.full(N, wt))
# V: continuous vol-target leverage (c / realized vol, clipped)
for c in (0.4, 0.5, 0.6):
    for tag, V in (("v120", VOL120), ("v180", VOL180)):
        lv = np.clip(c / lagged(V, np.nanmedian(V[is_m])), 1.0, 2.2)
        lv = np.where(np.isnan(lv), 1.5, lv)
        RULES[f"V {tag} c{c}"] = (lv, np.full(N, 0.25))
# T: slow-trend leverage (bear-lever mechanism from round 1 survivors)
for tag, D in (("d200", D200), ("d100", D100)):
    RULES[f"T {tag} bear2x"] = (np.where(lagged(D, 0) < 0, 2.0, 1.5), np.full(N, 0.25))
RULES["T d200 cont"] = (np.clip(1.75 - 2.0 * lagged(D200, 0), 1.0, 2.2), np.full(N, 0.25))
# W: blend-weight regime switching (|trend distance| gates w_trend)
thrW = np.nanquantile(np.abs(D200[is_m]), 0.6)
for hi, lo, tag in ((0.40, 0.15, "trendy40"), (0.15, 0.40, "inv")):
    RULES[f"W {tag}"] = (np.full(N, 1.5),
                         np.where(np.abs(lagged(D200, 0)) > thrW, hi, lo))
RULES["W vol40"] = (np.full(N, 1.5),
                    np.where(lagged(VOL120, 0) > np.nanquantile(VOL120[is_m], 0.6),
                             0.40, 0.15))
# C: combo score bear+vol (round-1 mechanism, honest)
zb = lambda a: (a - np.nanmean(a[is_m])) / (np.nanstd(a[is_m]) + 1e-9)
for wv, tag in ((0.5, "50/50"), (0.3, "70bear/30vol")):
    score = -(1 - wv) * zb(lagged(D200, 0)) + wv * zb(lagged(VOL120, 0))
    RULES[f"C {tag}"] = (np.clip(1.5 + 0.35 * score, 1.0, 2.2), np.full(N, 0.25))
# D: own-book drawdown de-lever (honest by construction; recompute per path)
def dd_rule(th):
    eq = peak = 1.0
    lv = np.empty(N)
    for k in range(N):
        lv[k] = 1.5 if (eq / peak - 1) < -th else 2.0
        w_eff = 0.75 if isP[k] else 0.25
        eq *= 1 + lv[k] * w_eff * raw[k]
        peak = max(peak, eq)
    return lv
for th in (0.08, 0.12):
    RULES[f"D dd{int(th*100)}"] = (dd_rule(th), np.full(N, 0.25))

rows = []
for name, (lv, wt) in RULES.items():
    full, iseg, oseg = run(lv, wt)
    rows.append({"rule": name, "full": full, "is": iseg, "oos": oseg,
                 "avg_lev": round(float(np.mean(lv)), 2)})
n_switch = len([r for r in rows if not r["rule"].startswith("static")])
print(f"pre-registered switching rules: {n_switch} (+6 static baselines) | steps {N} | split {SPLIT_I}")
best_static_oos = max(r["oos"][2] or 0 for r in rows if r["rule"].startswith("static"))
print(f"{'rule':22} {'full ret':>9} {'mdd':>7} {'MAR':>5} | {'IS MAR':>6} {'OOS MAR':>7} | {'avgL':>4}")
for r in sorted(rows, key=lambda x: -(x["oos"][2] or 0)):
    print(f"{r['rule']:22} {r['full'][0]:>8}% {r['full'][1]:>6}% {str(r['full'][2]):>5} | "
          f"{str(r['is'][2]):>6} {str(r['oos'][2]):>7} | {r['avg_lev']:>4}")
print(f"\nbest STATIC OOS MAR: {best_static_oos} | promotion bar: OOS > {round(best_static_oos+0.25,2)} AND full > selection-noise q95")
json.dump(rows, open(os.path.join(os.path.dirname(__file__), "switch2_results.json"), "w"), indent=1)
