"""RESEARCH: dynamic S5<->S6 leverage switching (see RESEARCH_SWITCH.md).

S5 and S6 are the SAME blend at 1.5x vs 2.0x, so 'switching books' == a
leverage rule m(t) in {1.5, 2.0} applied to the unlevered blend steps.
Decisions use ONLY information available at each trade-exit time; the chosen
leverage applies to the NEXT step (matches how the executor would do it:
resize at flat, never mid-position). Trade-step basis, research fees, no
cash yield — same basis as the S5/S6 comparison rows.

Protocol: tune thresholds in-sample (first 2y), freeze, validate OOS
(second 2y). Report both halves separately + full period.
"""
import csv, json, os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay                         # noqa: E402
from app.main import ENGINE                                      # noqa: E402
from app.config import settings                                  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures",
                   "bars_4h_btcusd.csv")
bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(FIX))]
T1 = bars[-1].ts
T0 = T1 - 1461 * 86400
SPLIT = T1 - 730 * 86400                                          # IS/OOS boundary

res = run_replay(bars, ENGINE.books_cfg, ENGINE.scfg, ENGINE.tcfg,
                 start_ts=T0, end_ts=T1, cash_apy=settings.cash_apy)
b3, b4 = res.books["S3"], res.books["S4"]
evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
             + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
p3 = p4 = 1.0
steps = []                                                        # (ts, unlevered r)
for ts, which, ratio in evs:
    if which == "P":
        steps.append((ts, (ratio / p3 - 1) * 0.75)); p3 = ratio
    else:
        steps.append((ts, (ratio / p4 - 1) * 0.25)); p4 = ratio

ts_arr = np.array([t for t, _ in steps])
r_arr = np.array([x for _, x in steps])
closes = np.array([b.close for b in bars]); bts = np.array([b.ts for b in bars])

def bar_idx(t):
    return int(np.searchsorted(bts, t, side="right") - 1)

# --- signal library ---------------------------------------------------------
# QA FIX (counter-agent audit, 2026-08-07): exit_ts is a bar-OPEN timestamp,
# so the bar at bar_idx(t) CLOSES 4h in the future. Signals must use only
# CLOSED bars: window ends at index i-1 (the bar ending exactly at t).
def sig_vol(t, look=120):                                         # 20d realized vol
    i = bar_idx(t)
    w = closes[max(0, i - look):i]                                # closed bars only
    rr = np.diff(np.log(w))
    return float(np.std(rr) * np.sqrt(6 * 365)) if len(rr) > 10 else np.nan

def sig_trend(t, look):                                           # last close vs SMA
    i = bar_idx(t)
    w = closes[max(0, i - look):i]
    return float(w[-1] / np.mean(w) - 1) if len(w) else 0.0

def sig_eff(t, look=180):                                         # efficiency ratio
    i = bar_idx(t)
    w = closes[max(0, i - look):i]
    if len(w) < 10:
        return 0.0
    path = np.sum(np.abs(np.diff(w)))
    return float(abs(w[-1] - w[0]) / path) if path > 0 else 0.0

VOL = np.array([sig_vol(t) for t in ts_arr])
TR50 = np.array([sig_trend(t, 300) for t in ts_arr])              # 50d SMA
TR200 = np.array([sig_trend(t, 1200) for t in ts_arr])            # 200d SMA
EFF = np.array([sig_eff(t) for t in ts_arr])

def run_rule(lev_fn):
    """lev_fn(j, own_dd, own_eq) -> 1.5 or 2.0. QA FIX: the decision for step
    k is made at step k-1's EXIT (the executor resizes at the previous flat),
    so signal-indexed rules receive j = k-1. j = -1 on the first step (no
    prior exit): rules must default to 1.5 there. Combined with closed-bar
    signal windows above, no part of step k's own path can reach its lever."""
    eq = peak = 1.0; mdd = 0.0
    occ2 = 0; levs = []
    for k in range(len(r_arr)):
        m = lev_fn(k - 1, eq / peak - 1, eq) if k > 0 else 1.5
        levs.append(m)
        occ2 += (m == 2.0)
        eq *= 1 + m * r_arr[k]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return eq, mdd, occ2 / len(r_arr), np.array(levs)

def seg_stats(levs, lo_ts, hi_ts):
    mask = (ts_arr >= lo_ts) & (ts_arr < hi_ts)
    eq = peak = 1.0; mdd = 0.0
    for k in np.nonzero(mask)[0]:
        eq *= 1 + levs[k] * r_arr[k]
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    yrs = (hi_ts - lo_ts) / (365.25 * 86400)
    cagr = eq ** (1 / yrs) - 1
    return {"ret": round(100 * (eq - 1), 1), "cagr": round(100 * cagr, 1),
            "mdd": round(100 * mdd, 1),
            "mar": round(cagr / abs(mdd), 2) if mdd < 0 else None}

RULES = {
  "S5 static":  lambda k, dd, eq: 1.5,
  "S6 static":  lambda k, dd, eq: 2.0,
  # A. drawdown ratchet: de-lever when own book is underwater
  "A dd5":      lambda k, dd, eq: 1.5 if dd < -0.05 else 2.0,
  "A dd10":     lambda k, dd, eq: 1.5 if dd < -0.10 else 2.0,
  "A dd15":     lambda k, dd, eq: 1.5 if dd < -0.15 else 2.0,
  # B. volatility gate (thresholds = IS quantiles, computed below)
  # C. trend gates
  "C tr50":     lambda k, dd, eq: 2.0 if TR50[k] > 0 else 1.5,
  "C tr200":    lambda k, dd, eq: 2.0 if TR200[k] > 0 else 1.5,
  "C tr200inv": lambda k, dd, eq: 1.5 if TR200[k] > 0 else 2.0,   # bear=our best regime
  # D. edge momentum: trailing sum of last 10 unlevered steps
  "D edge10":   lambda k, dd, eq: 2.0 if k >= 10 and r_arr[k-10:k].sum() > 0 else 1.5,
  "D edge20":   lambda k, dd, eq: 2.0 if k >= 20 and r_arr[k-20:k].sum() > 0 else 1.5,
  "D edgeinv":  lambda k, dd, eq: 1.5 if k >= 10 and r_arr[k-10:k].sum() > 0 else 2.0,
  # E. efficiency / chop gate
  # F. combo: trend up AND not in drawdown
  "F tr50+dd10": lambda k, dd, eq: 2.0 if (TR50[k] > 0 and dd > -0.10) else 1.5,
}
is_mask = ts_arr < SPLIT
for q, tag in ((0.4, "E eff-q40"), (0.5, "E eff-q50"), (0.6, "E eff-q60")):
    thr = float(np.quantile(EFF[is_mask], q))                     # IS-only threshold
    RULES[tag] = (lambda thr: lambda k, dd, eq: 2.0 if EFF[k] > thr else 1.5)(thr)
for q, tag in ((0.5, "B vol-q50"), (0.6, "B vol-q60"), (0.7, "B vol-q70")):
    thr = float(np.nanquantile(VOL[is_mask], q))
    RULES[tag] = (lambda thr: lambda k, dd, eq: 1.5 if VOL[k] > thr else 2.0)(thr)

rows = []
for name, fn in RULES.items():
    eq, mdd, occ2, levs = run_rule(fn)
    yrs = (T1 - T0) / (365.25 * 86400)
    cagr = eq ** (1 / yrs) - 1
    rows.append({"rule": name,
                 "full": {"ret": round(100 * (eq - 1), 1), "cagr": round(100 * cagr, 1),
                          "mdd": round(100 * mdd, 1),
                          "mar": round(cagr / abs(mdd), 2) if mdd < 0 else None},
                 "is": seg_stats(levs, T0, SPLIT),
                 "oos": seg_stats(levs, SPLIT, T1),
                 "pct_at_2x": round(100 * occ2)})
out = {"steps": len(r_arr), "window": [int(T0), int(SPLIT), int(T1)], "rows": rows}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "switch_results.json"), "w"), indent=1)
hdr = f"{'rule':13} {'full ret':>9} {'mdd':>7} {'MAR':>5} | {'IS MAR':>6} {'OOS ret':>8} {'OOS mdd':>8} {'OOS MAR':>7} | {'%2x':>4}"
print(hdr)
for x in rows:
    print(f"{x['rule']:13} {x['full']['ret']:>8}% {x['full']['mdd']:>6}% {x['full']['mar']:>5} | "
          f"{x['is']['mar']:>6} {x['oos']['ret']:>7}% {x['oos']['mdd']:>7}% {x['oos']['mar']:>7} | {x['pct_at_2x']:>3}%")
