"""CANDIDATE A - risk-based / volatility-targeted sizing. MEASUREMENT PASS 1.

Runs the REAL engine (app.engine.replay.run_replay) with sizing="vol_target"
against the shipped sizing="fixed", per leg, risk-matched, across a cap ladder.

Per-leg SEPARATE replays: _size() reads tcfg.stop_atr for EVERY book, but the
donchian book's real exit is BookCfg.trail_atr. _process_donchian never reads
tcfg.stop_atr for anything but sizing, so running the trend leg alone with
TradeCfg(stop_atr=X) sets its SIZING stop distance without touching its exits.
That is how the latent core.py defect (phase 1 finding 10) is neutralised
without editing the engine.

Risk matching: under FIXED(leverage=1, cap=1) the equity fraction at risk per
trade is exactly s_i = stop_atr*ATR_e/entry. Under VOL_TARGET it is the
constant `risk`. Setting risk = mean(s_i) over the (identical) trade set
matches MEAN equity-fraction-at-risk per trade. Trade sets are size-invariant
(entries, stops, trails, exits are all price-based), EXCEPT via dd_halt --
which is asserted, not assumed.

Output: candA_voltarget.json
"""
import csv
import json
import math
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from app.engine.core import Bar, BookCfg, TradeCfg          # noqa: E402
from app.engine.replay import run_replay, book_stats        # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402
from app.engine import kelly as K                           # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
BAR_S = 4 * 3600
# S5 blend, verbatim from app/config.py + main.py blend
W_TREND = 0.25
BLEND_LEV = 1.5
# Holdout window per RESEARCH_TRAIL.md's window map (single-touch).
HOLDOUT_START = 1719792000        # 2024-07-01
# Sizing stop multiple per leg. Pullback = the registered 2.5 (TradeCfg).
# Trend = its NOMINAL exit distance trail_atr 5.0 (derivable from config;
# the measured EFFECTIVE 2.87 is run as a sensitivity, not the primary).
SIZING_STOP = {"pullback": 2.5, "trend": 5.0}


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def leg_cfg(leg, sizing, risk=0.0, cap=1.0, dd_halt=None):
    """One-book config for a leg. dd_halt defaults to the shipped value."""
    if leg == "pullback":
        return BookCfg(name="P", sizing=sizing, strategy="pullback",
                       leverage=1.0, risk=risk, long_mult=1.0, cap=cap,
                       start_equity=100_000.0,
                       dd_halt=0.30 if dd_halt is None else dd_halt)
    return BookCfg(name="T", sizing=sizing, strategy="donchian", trail_atr=5.0,
                   leverage=1.0, risk=risk, long_mult=1.0, cap=cap,
                   start_equity=100_000.0,
                   dd_halt=0.50 if dd_halt is None else dd_halt)


def run_leg(bars, leg, sizing, risk=0.0, cap=1.0, tcfg=None, dd_halt=None):
    tc = tcfg or replace(RESEARCH_TRADE, stop_atr=SIZING_STOP[leg])
    res = run_replay(bars, [leg_cfg(leg, sizing, risk, cap, dd_halt)],
                     RESEARCH_SIGNAL, tc, cash_apy=0.0)
    return res.books["P" if leg == "pullback" else "T"], tc


def trade_rows(book, tc):
    """Per-trade sizing facts. s = the stop distance _size() actually used."""
    out = []
    for t in book.trades:
        s = tc.stop_atr * t.atr_at_entry / t.entry_price
        eqb = t.equity_before
        out.append(dict(
            entry_ts=t.entry_ts, exit_ts=t.exit_ts, side=t.side,
            entry=t.entry_price, exit=t.exit_price, reason=t.exit_reason,
            atr=t.atr_at_entry, s=s, notional=t.notional, qty=t.qty,
            eq_before=eqb, eq_after=t.equity_after,
            notional_frac=t.notional / eqb, risk_frac=t.notional / eqb * s,
            pnl_usd=t.pnl_usd, pnl_pct=t.pnl_pct, ret_eq=t.pnl_usd / eqb,
            bars_held=t.bars_held, stop_price=t.stop_price, fees=t.fees_usd))
    return out


def blend_steps(pb, tb, w=W_TREND, lev=BLEND_LEV, t0=None, t1=None):
    """Exit-step blended NAV, verbatim logic from scripts/bench_blend.py."""
    evs = sorted([(t.exit_ts, "P", t) for t in pb.trades]
                 + [(t.exit_ts, "T", t) for t in tb.trades])
    p3 = p4 = 1.0
    eq = 1.0
    ts_out, nav_out, r_out = [], [], []
    for ts, which, t in evs:
        base = (pb if which == "P" else tb).cfg.start_equity
        ratio = t.equity_after / base
        r = (ratio / p3 - 1) * (1 - w) if which == "P" else (ratio / p4 - 1) * w
        if which == "P":
            p3 = ratio
        else:
            p4 = ratio
        if (t0 is None or ts >= t0) and (t1 is None or ts <= t1):
            eq *= 1 + lev * r
            ts_out.append(ts)
            nav_out.append(eq)
            r_out.append(lev * r)
    return np.array(ts_out), np.array(nav_out), np.array(r_out)


def curve_stats(ts, nav):
    if len(nav) < 3:
        return {}
    yrs = (ts[-1] - ts[0]) / (365.25 * 86400)
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    cagr = float(nav[-1] ** (1 / yrs) - 1)
    r = np.diff(np.concatenate([[1.0], nav])) / np.concatenate([[1.0], nav])[:-1]
    return dict(total_pct=100 * (float(nav[-1]) - 1), cagr_pct=100 * cagr,
                maxdd_pct=100 * mdd, mar=cagr / abs(mdd) if mdd < -0.005 else None,
                sharpe=float(r.mean() / (r.std() + 1e-12) * math.sqrt(len(r) / yrs)),
                years=yrs, n=len(nav))


def pct(a, q):
    return float(np.percentile(np.asarray(a, dtype=float), q))


def dist(a, label=""):
    a = np.asarray(a, dtype=float)
    return dict(n=int(len(a)), mean=float(a.mean()), median=pct(a, 50),
                p1=pct(a, 1), p10=pct(a, 10), p90=pct(a, 90), p99=pct(a, 99),
                min=float(a.min()), max=float(a.max()), sd=float(a.std()))


def main():
    bars = load_bars()
    out = {"meta": dict(
        bars=len(bars), first_ts=bars[0].ts, last_ts=bars[-1].ts,
        fee_basis_bps_round_trip=2 * RESEARCH_TRADE.taker_fee_bps,
        fee_note="RESEARCH_TRADE default = the REGISTERED objective "
                 "(TradeCfg L65-74). 8.64 run as sensitivity in candA_fee.",
        sizing_stop=SIZING_STOP, blend="0.75 pullback / 0.25 trend @ lev 1.5",
        holdout_start=HOLDOUT_START, cash_apy=0.0)}

    # ---- 1. FIXED baseline, per leg -------------------------------------
    base = {}
    for leg in ("pullback", "trend"):
        bk, tc = run_leg(bars, leg, "fixed", cap=1.0)
        rows = trade_rows(bk, tc)
        base[leg] = dict(book=bk, tc=tc, rows=rows, stats=book_stats(bk))
        print(f"FIXED {leg}: n={len(rows)} eq={bk.equity:,.0f} "
              f"halted={bk.halted} mean_s={np.mean([r['s'] for r in rows]):.4%}")

    # risk-match target: mean equity-fraction-at-risk per trade under FIXED
    risk_match = {leg: float(np.mean([r["risk_frac"] for r in base[leg]["rows"]]))
                  for leg in base}
    out["risk_match"] = {leg: dict(
        risk_frac_mean=risk_match[leg],
        s_dist=dist([r["s"] for r in base[leg]["rows"]]),
        notional_frac_dist=dist([r["notional_frac"] for r in base[leg]["rows"]]))
        for leg in base}
    print("risk-match targets:", {k: f"{v:.4%}" for k, v in risk_match.items()})

    # ---- 2. VOL_TARGET arms across a cap ladder -------------------------
    CAPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 99.0]
    vt = {}
    for cap in CAPS:
        vt[cap] = {}
        for leg in ("pullback", "trend"):
            bk, tc = run_leg(bars, leg, "vol_target", risk=risk_match[leg], cap=cap)
            rows = trade_rows(bk, tc)
            vt[cap][leg] = dict(book=bk, tc=tc, rows=rows, stats=book_stats(bk))
        print(f"VT cap={cap}: P n={len(vt[cap]['pullback']['rows'])} "
              f"eq={vt[cap]['pullback']['book'].equity:,.0f} | "
              f"T n={len(vt[cap]['trend']['rows'])} "
              f"eq={vt[cap]['trend']['book'].equity:,.0f}")

    # ---- 3. trade-set identity assertion --------------------------------
    ident = {}
    for cap in CAPS:
        d = {}
        for leg in ("pullback", "trend"):
            a = base[leg]["rows"]
            b = vt[cap][leg]["rows"]
            same_n = len(a) == len(b)
            same_keys = same_n and all(
                (x["entry_ts"], x["exit_ts"], round(x["entry"], 8),
                 round(x["exit"], 8), x["reason"]) ==
                (y["entry_ts"], y["exit_ts"], round(y["entry"], 8),
                 round(y["exit"], 8), y["reason"]) for x, y in zip(a, b))
            d[leg] = dict(n_fixed=len(a), n_vt=len(b), identical=bool(same_keys),
                          halted_fixed=base[leg]["book"].halted,
                          halted_vt=vt[cap][leg]["book"].halted)
        ident[str(cap)] = d
    out["trade_set_identity"] = ident
    bad = [(c, l) for c, d in ident.items() for l, v in d.items() if not v["identical"]]
    print("trade-set identity breaks:", bad if bad else "NONE")

    # ---- 4. notional + risk distributions, VT vs FIXED ------------------
    notional = {}
    for cap in CAPS:
        e = {}
        for leg in ("pullback", "trend"):
            f = base[leg]["rows"]
            v = vt[cap][leg]["rows"]
            nf_f = np.array([r["notional_frac"] for r in f])
            nf_v = np.array([r["notional_frac"] for r in v])
            rf_v = np.array([r["risk_frac"] for r in v])
            rf_f = np.array([r["risk_frac"] for r in f])
            n = min(len(nf_f), len(nf_v))
            e[leg] = dict(
                fixed_notional_frac=dist(nf_f), vt_notional_frac=dist(nf_v),
                fixed_risk_frac=dist(rf_f), vt_risk_frac=dist(rf_v),
                mult_mean=float(nf_v[:n].mean() / nf_f[:n].mean()),
                mult_median=float(np.median(nf_v[:n] / nf_f[:n])),
                mult_p99=float(np.percentile(nf_v[:n] / nf_f[:n], 99)),
                mult_max=float((nf_v[:n] / nf_f[:n]).max()),
                pct_capped=float((nf_v >= cap - 1e-9).mean()),
                risk_frac_mean_ratio=float(rf_v[:n].mean() / rf_f[:n].mean()))
        notional[str(cap)] = e
    out["notional"] = notional

    # ---- 5. blend curves + Kelly ----------------------------------------
    def arm_blend(pb, tb, tag):
        res = {}
        for wname, t0 in (("full", None), ("holdout", HOLDOUT_START)):
            ts, nav, r = blend_steps(pb, tb, t0=t0)
            st = curve_stats(ts, nav)
            kk = K.analyze(list(r), f"{tag}-{wname}", cap=K.M_CAP)
            res[wname] = dict(stats=st, kelly={
                k: kk[k] for k in ("n", "mean_pct", "sd_pct", "kelly_m",
                                   "bootstrap", "half_kelly_m",
                                   "shrinkage_c_star", "conservative_m",
                                   "dd_constrained", "recommended_m", "verdict")})
            res[wname]["curve"] = [[int(a), float(b)] for a, b in zip(ts, nav)]
            res[wname]["steps"] = [float(x) for x in r]
        return res

    out["blend"] = {"FIXED": arm_blend(base["pullback"]["book"],
                                      base["trend"]["book"], "FIXED")}
    for cap in CAPS:
        out["blend"][f"VT_cap{cap}"] = arm_blend(
            vt[cap]["pullback"]["book"], vt[cap]["trend"]["book"], f"VT{cap}")
    for k, v in out["blend"].items():
        f, h = v["full"], v["holdout"]
        print(f"{k:12s} FULL cagr={f['stats']['cagr_pct']:6.2f}% "
              f"dd={f['stats']['maxdd_pct']:7.2f}% MAR={f['stats']['mar'] or 0:.2f} "
              f"rec_m={f['kelly']['recommended_m']:.2f} | "
              f"HOLD cagr={h['stats']['cagr_pct']:6.2f}% dd={h['stats']['maxdd_pct']:7.2f}% "
              f"rec_m={h['kelly']['recommended_m']:.2f}")

    # ---- 6. per-leg book stats + MTM ------------------------------------
    out["leg_stats"] = {"FIXED": {l: base[l]["stats"] for l in base}}
    out["leg_mtm"] = {"FIXED": {l: dict(
        mtm_max_dd_pct=100 * base[l]["book"].mtm_max_dd,
        trade_close_dd_pct=base[l]["stats"]["max_dd_pct"]) for l in base}}
    for cap in CAPS:
        out["leg_stats"][f"VT_cap{cap}"] = {l: vt[cap][l]["stats"] for l in ("pullback", "trend")}
        out["leg_mtm"][f"VT_cap{cap}"] = {l: dict(
            mtm_max_dd_pct=100 * vt[cap][l]["book"].mtm_max_dd,
            trade_close_dd_pct=vt[cap][l]["stats"]["max_dd_pct"])
            for l in ("pullback", "trend")}

    # ---- 7. dump raw per-trade rows for the forward-vol pass ------------
    out["rows"] = {"FIXED": {l: base[l]["rows"] for l in base},
                   "VT_cap2.0": {l: vt[2.0][l]["rows"] for l in ("pullback", "trend")},
                   "VT_cap99.0": {l: vt[99.0][l]["rows"] for l in ("pullback", "trend")}}

    p = os.path.join(HERE, "candA_voltarget.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
