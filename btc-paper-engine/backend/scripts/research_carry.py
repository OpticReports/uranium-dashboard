"""RESEARCH: Flood-framework carry/basis variants on BTC vs our S5/S6 book.

PRE-REGISTERED (2026-08-26) before any results were seen. Casey's ask: test
the "spot long + perp short, funding-subsidized, delta-managed" framework
against our current executor strategy; 2y and long-window backtests.

DATA (venues Casey named; BitMEX explicitly excluded):
  spot   : Bitstamp BTC/USD 4h bars (same feed as the live engine)
  funding: Hyperliquid BTC perp, HOURLY stamps, 2023-05-12 -> present
           (PRIMARY - the framework's home venue); Coinbase INTX BTC-PERP
           as cross-check where its early thin-book data is sane.
WINDOWS: 2y = last 730d. "4y" IS NOT AVAILABLE - Hyperliquid launched
  2023-05; the long window is its full life (~3.3y) and is labeled so.

MECHANICS (one engine, all variants):
  state = cash + spot_btc + perp short (units, avg entry). 4h step loop on
  spot bars; hedge target h_t (short notional / spot notional) decided at
  bar t CLOSE from data known at t; trades execute at that close, 6bp fee
  on traded notional both legs (matches the engine's decoded fee basis).
  Funding: every hourly stamp inside (t, t+1] credits cash with
  rate * mark * short_units (positive rate -> shorts RECEIVE; HL/INTX
  convention), using the spot close as mark proxy. Missing funding hours
  accrue zero (570 of ~28.8k hour-slots; 567 sit in HL's first 7 weeks,
  May-Jun 2023, only 1 inside the 2y window; 16 further stamps land on
  misaligned seconds and are never accrued - conservative, understates
  early-2023 carry). Rebalance only when |h_target - h| > 5pp.
  NAV marked at every bar close (true MTM, unlike the blend's exit-step).

VARIANTS (ALL reported; no post-hoc additions):
  V0  HOLD           100% spot
  V1  CARRY-100      spot 100%, short 100% (delta~0; the funding floor)
  V2a/b/c STATIC     short h in {25, 50, 75}% (delta-managed, constant)
  V3a/b BAND         h_t = clip(0.5 + k*(px/SMA200_4h - 1), 0.15, 1.0),
                     k in {1, 2}. Flush -> h drops (cover shorts = "the
                     button"); rip -> h rises toward flat.
  V4  FUNDING-BINS   7d EMA of annualized funding f: h = 0.75 if f>5%,
                     0.50 if 0<f<=5%, 0.15 if f<=0 (declared bins, unfit)
  V5  FLUSH-COVER    h0=0.60; drawdown >= 20% from 90d high -> h=0.30;
                     restore at a new 90d high (one discrete "button")
  V3F COMBO          h_t = min(V3a, V4) (band AND funding gates)
  V6  S6+CARRY       70% our S6 blend (research replay, exit-step equity
                     carried between exits) + 30% V1 sleeve, monthly rebal
BENCHMARKS on identical windows: V0, S5, S6 (replay research basis).
METRICS: total, CAGR, maxDD (bar MTM), MAR, Sharpe (4h ann.), funding P&L
  share, turnover x/yr, worst 30d.

HONESTY, registered up front: unified collateral is assumed (spot margins
the short) - realistic on INTX portfolio margin, NOT on Hyperliquid where
spot and perp collateral are separate; basis MTM between perp and spot is
ignored (funding ties them; second-order at 4h); the cross-venue
dislocation leg and options overlay of the original framework are NOT
tested (no tick-level multi-venue data, no options surface) - what is
tested is the carry + delta-management core. Windows overlap a bull-heavy
regime; funding was positive 87.0% of hours - the subsidy is regime-
dependent and 2022-style bears are OUTSIDE the data.

POST-AUDIT CORRECTIONS (2026-08-26, counter-agent; mechanics passed -
no look-ahead, lag-1 rerun IMPROVES the funding-conditioned variants):
  - missing-hours count above corrected 88 -> 570 (audit recount);
    positive-hours share corrected ~76% -> 87.0%.
  - curve[0] is recorded AFTER entry fees, so ~12bp of entry cost is
    excluded from all return stats (one-time, sub-noise, flattering).
  - curve points carry bar-OPEN timestamps with bar-CLOSE NAVs; uniform
    4h shift, harmless within a curve, at most one-bar skew in the V6
    30d-rolling blend. Fix stamps to close-time in any follow-up.
  - V1's MAR is an artifact on BOTH windows (basis MTM suppressed):
    mask the 3.3y value (25.6) exactly as the 2y one.
"""
import csv
import json
import math
import os
import sys
import datetime as dt

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine.core import Bar                                   # noqa: E402

FEE = 6e-4          # per side, on traded notional (engine's decoded basis)
REBAL_BAND = 0.05   # min |h_target-h| to trade the perp leg
BAR_S = 4 * 3600

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else "."
BARS_CSV = os.path.join(SCRATCH, "bars_4h_btcusd_ext.csv")
FUND_CSV = os.path.join(SCRATCH, "funding_hyperliquid_btc.csv")


def load_data():
    bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]
    fund = {}
    for r in csv.DictReader(open(FUND_CSV)):
        fund[int(r["ts_ms"]) // 1000] = float(r["funding_rate_1h"])
    return bars, fund


def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


class Book:
    """Unified-collateral spot+perp book, bar-close MTM."""

    def __init__(self, nav0=100_000.0):
        self.cash = nav0
        self.spot = 0.0            # BTC units held
        self.short = 0.0           # perp units short (>=0)
        self.short_avg = 0.0       # avg entry px of the short
        self.funding_pnl = 0.0
        self.fees = 0.0
        self.turnover = 0.0

    def nav(self, px):
        return (self.cash + self.spot * px
                + self.short * (self.short_avg - px))

    def trade_spot(self, units, px):
        cost = units * px
        fee = abs(cost) * FEE
        self.cash -= cost + fee
        self.spot += units
        self.fees += fee
        self.turnover += abs(cost)

    def adjust_short(self, target_units, px):
        d = target_units - self.short
        if d == 0:
            return
        fee = abs(d) * px * FEE
        if d > 0:                  # increase short
            self.short_avg = ((self.short * self.short_avg + d * px)
                              / (self.short + d))
            self.short += d
        else:                      # cover: realize pnl on covered units
            self.cash += (-d) * (self.short_avg - px)
            self.short += d
            if self.short <= 1e-12:
                self.short, self.short_avg = 0.0, 0.0
        self.cash -= fee
        self.fees += fee
        self.turnover += abs(d) * px

    def accrue_funding(self, rate, px):
        amt = rate * px * self.short          # +rate -> short receives
        self.cash += amt
        self.funding_pnl += amt


def run_variant(bars, fund, h_fn, t0, t1, nav0=100_000.0):
    """h_fn(i, ctx) -> target hedge ratio in [0,1] using data through bar i."""
    closes = [b.close for b in bars]
    s200 = sma(closes, 200)
    hi90 = [None] * len(bars)
    for i in range(540, len(bars)):
        hi90[i] = max(closes[i - 540:i + 1])
    # 7d EMA of annualized funding, causal, stamped hourly -> sampled per bar
    f_ann = {}
    ema, alpha = None, 2 / (7 * 24 + 1)
    for ts in sorted(fund):
        x = fund[ts] * 24 * 365
        ema = x if ema is None else ema + alpha * (x - ema)
        f_ann[ts] = ema
    f_keys = sorted(f_ann)

    def f_ema_at(ts):
        import bisect
        j = bisect.bisect_right(f_keys, ts) - 1
        return f_ann[f_keys[j]] if j >= 0 else 0.0

    bk = Book(nav0)
    curve, meta = [], {"h": []}
    started = False
    for i, b in enumerate(bars):
        if b.ts < t0 or s200[i] is None or hi90[i] is None:
            continue
        if b.ts > t1:
            break
        px = b.close
        if not started:
            bk.trade_spot(bk.cash / px * (1 - FEE), px)   # deploy fully
            started = True
        # funding for stamps inside (bar open, bar close]
        for hts in range(b.ts + 3600, b.ts + BAR_S + 1, 3600):
            if hts in fund:
                bk.accrue_funding(fund[hts], px)
        ctx = {"px": px, "sma200": s200[i], "hi90": hi90[i],
               "f_ema": f_ema_at(b.ts + BAR_S), "book": bk}
        h_t = h_fn(i, ctx)
        cur_h = (bk.short * px) / max(1e-9, bk.spot * px)
        if abs(h_t - cur_h) > REBAL_BAND:
            bk.adjust_short(h_t * bk.spot, px)
        nav = bk.nav(px)
        curve.append((b.ts, nav))
        meta["h"].append((b.ts, h_t))
        if nav <= 0:
            break
    return bk, curve, meta


# ---------------- variant hedge functions (all pre-registered) --------------
def v_hold(i, c):        return 0.0
def v_carry(i, c):       return 1.0
def v_static(h):         return lambda i, c: h
def v_band(k):
    return lambda i, c: min(1.0, max(0.15, 0.5 + k * (c["px"] / c["sma200"] - 1)))
def v_fbins(i, c):
    f = c["f_ema"]
    return 0.75 if f > 0.05 else (0.50 if f > 0 else 0.15)
_v5state = {}
def v_flush(i, c):
    dd = c["px"] / c["hi90"] - 1
    st = _v5state
    if c["px"] >= c["hi90"] - 1e-9:
        st["covered"] = False
    if dd <= -0.20:
        st["covered"] = True
    return 0.30 if st.get("covered") else 0.60
def v_combo(i, c):       return min(v_band(1)(i, c), v_fbins(i, c))

VARIANTS = [
    ("V0-HOLD", v_hold), ("V1-CARRY100", v_carry),
    ("V2a-static25", v_static(0.25)), ("V2b-static50", v_static(0.50)),
    ("V2c-static75", v_static(0.75)),
    ("V3a-band-k1", v_band(1)), ("V3b-band-k2", v_band(2)),
    ("V4-fundbins", v_fbins), ("V5-flushcover", v_flush),
    ("V3F-combo", v_combo),
]


def stats(curve, bk=None):
    ts = np.array([c[0] for c in curve])
    nav = np.array([c[1] for c in curve])
    rets = np.diff(nav) / nav[:-1]
    yrs = (ts[-1] - ts[0]) / (365.25 * 86400)
    tot = nav[-1] / nav[0] - 1
    cagr = (nav[-1] / nav[0]) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    sharpe = (rets.mean() / (rets.std() + 1e-12)) * math.sqrt(6 * 365)
    # worst rolling 30d
    w = 180
    worst30 = float(min((nav[j + w] / nav[j] - 1)
                        for j in range(len(nav) - w))) if len(nav) > w else None
    out = {"total_pct": 100 * tot, "cagr_pct": 100 * cagr,
           "maxdd_pct": 100 * mdd,
           "mar": cagr / abs(mdd) if mdd < -0.005 else None,
           "sharpe": sharpe, "worst30d_pct": 100 * worst30 if worst30 else None,
           "years": yrs}
    if bk:
        out["funding_pnl"] = bk.funding_pnl
        out["funding_share_pct"] = (100 * bk.funding_pnl
                                    / max(1e-9, nav[-1] - nav[0])
                                    if nav[-1] > nav[0] else None)
        out["fees"] = bk.fees
        out["turnover_x_yr"] = bk.turnover / nav[0] / yrs
    return out


def compose_v6(wname, curves, results):
    """V6 = 70% S6 blend + 30% V1 carry sleeve, 30d-rolling rebalance,
    6bp on both legs of the traded notional. S6 exit-step curve carried
    (causal step function) between exits, sampled on the carry 4h grid.
    Needs blend_bench.json (scripts/bench_blend.py) in the scratch dir.
    Audit 2026-08-26: reproduced independently to 1.5e-5; exit-step DD
    label + MTM MAR floors (1.32 2y / 1.53 3.3y) are mandatory wording."""
    import bisect
    bench_path = os.path.join(SCRATCH, "blend_bench.json")
    if not os.path.exists(bench_path):
        print(f"  [{wname}] V6-s6carry SKIPPED: blend_bench.json missing "
              f"(generate with scripts/bench_blend.py)")
        return
    bb = json.load(open(bench_path))
    carry = {int(t): n for t, n in curves[f"{wname}|V1-CARRY100"]}
    s6 = {int(t): n for t, n in bb[wname]["S6_curve"]}
    s6k = sorted(s6)
    s6v = [s6[k] for k in s6k]

    def s6_at(ts):
        j = bisect.bisect_right(s6k, ts) - 1
        return s6v[j] if j >= 0 else 1.0

    ts = sorted(carry)
    w_s6 = 0.70
    u_s6 = w_s6 / s6_at(ts[0])
    u_c = (1 - w_s6) / carry[ts[0]]
    last_rb = ts[0]
    nav = []
    for t in ts:
        v = u_s6 * s6_at(t) + u_c * carry[t]
        if t - last_rb >= 30 * 86400:
            tgt_s6 = w_s6 * v
            traded = abs(tgt_s6 - u_s6 * s6_at(t))
            v -= 2 * traded * FEE
            u_s6 = tgt_s6 / s6_at(t)
            u_c = (v - tgt_s6) / carry[t]
            last_rb = t
        nav.append(v)
    curve = list(zip(ts, nav))
    results[wname]["V6-s6carry"] = stats(curve)
    curves[f"{wname}|V6-s6carry"] = curve


def main():
    bars, fund = load_data()
    fstart = min(fund) // 3600 * 3600
    fend = max(fund)
    now = bars[-1].ts + BAR_S
    windows = {
        "2y": (now - 730 * 86400, now),
        "3.3y-full-HL": (fstart, now),
    }
    print(f"funding coverage: {dt.datetime.utcfromtimestamp(fstart).date()} "
          f".. {dt.datetime.utcfromtimestamp(fend).date()}; "
          f"positive hours: "
          f"{100 * sum(1 for v in fund.values() if v > 0) / len(fund):.0f}%")
    results = {}
    curves = {}
    for wname, (t0, t1) in windows.items():
        t0 = max(t0, fstart)          # never trade before funding data exists
        results[wname] = {}
        for vname, fn in VARIANTS:
            _v5state.clear()
            bk, curve, meta = run_variant(bars, fund, fn, t0, t1)
            st = stats(curve, bk)
            if vname == "V1-CARRY100":
                # basis MTM suppressed (spot==perp mark): drawdown-based
                # stats are artifacts on every window, not just where the
                # mdd<-0.5% guard happens to catch them (audit 2026-08-26)
                st["mar"] = None
            results[wname][vname] = st
            curves[f"{wname}|{vname}"] = curve
            if vname in ("V3a-band-k1", "V5-flushcover"):
                curves[f"{wname}|{vname}|h"] = meta["h"]
        compose_v6(wname, curves, results)
        print(f"\n== {wname}  "
              f"({dt.datetime.utcfromtimestamp(t0).date()} -> "
              f"{dt.datetime.utcfromtimestamp(t1).date()}) ==")
        for vname, st in results[wname].items():
            mar = f"{st['mar']:.2f}" if st["mar"] else "  - "
            fs = (f" fund%={st['funding_share_pct']:.0f}"
                  if st.get("funding_share_pct") is not None else "")
            print(f"  {vname:14s} tot={st['total_pct']:7.1f}% "
                  f"cagr={st['cagr_pct']:6.1f}% mdd={st['maxdd_pct']:6.1f}% "
                  f"MAR={mar} shp={st['sharpe']:5.2f} "
                  f"to={st.get('turnover_x_yr', 0):4.1f}x/y{fs}")
    json.dump({"results": results,
               "curves": {k: v for k, v in curves.items()}},
              open(os.path.join(SCRATCH, "carry_results.json"), "w"),
              default=float)
    print(f"\nwrote {os.path.join(SCRATCH, 'carry_results.json')}")


if __name__ == "__main__":
    main()
