"""RESEARCH: raise the S6 blend's per-trade WIN RATE without degrading MAR.

PRE-REGISTERED before any out-of-sample look (2026-08-17). Target set by
Casey: blend trade win rate >= 54-55% ("top-quant zone"), with the explicit
guard that win rate is NOT the objective function of the strategy — any rule
that buys win rate by degrading risk-adjusted return is rejected.

Data: Bitstamp 4h BTC/USD 2020-06 -> present (refetched, gap-checked);
trading window 2021-01 -> end; research basis (cash_apy=0, 6bp fees).
Discipline: gates evaluate on the SIGNAL bar's closed indicators only
(same bar the engine itself signals on); entries fill next bar — no new
timestamp semantics introduced anywhere.

Split protocol (per RESEARCH_5Y.md research queue): halves A = 2021-01 ->
2023-12-31, B = 2024-01 -> end (trades assigned by exit ts). Parameterized
rules choose their parameter on ONE half (objective: max blend win rate
subject to blend S6 MAR >= baseline S6 MAR on that half) and are scored
FROZEN on the other half; both fit directions are run (A->B and B->A).
Parameter-free rules are simply scored on both halves.

Rule families (search burden N = 12 — counted for selection noise):
  P1a/P1b pullback efficiency-ratio gate, ER(180 bars), threshold in
          {fit-half q25, q40} of signal-bar ER          (parameterized)
  P2      pullback SMA50-slope alignment (30-bar slope sign = trade side)
  P3      pullback trend separation |SMA50-SMA200| >= 1.0 x ATR14
  P4      pullback ADX(14) >= 20
  D1      donchian SMA200 alignment (long above / short below)
  D2      donchian breakout margin >= {0.25, 0.5} x ATR beyond channel
          (parameterized)
  D3      donchian SMA50-slope alignment
  E1      pullback stop 3.0 x ATR (wider — fewer stopouts)
  E2      pullback stop 2.0 x ATR (tighter — control/symmetry)
  C1      best P rule + best D rule combined (chosen on fit half only)

PROMOTION BAR (frozen): on the VALIDATION half, all of —
  1. blend win rate >= 54.0% AND >= baseline+2.0pp on that half
  2. blend S6 MAR >= baseline S6 MAR on that half
  3. blend mean per-trade step return >= baseline
  4. holds in BOTH fit directions
  5. win-rate gain > q95 of best-of-12 random block-gate null (30-day
     blocks, matched per-leg drop fraction, 200 draws, trade-list basis)
Anything short of all five is reported as NOT PROMOTED.

Honesty notes registered up front: (a) with ~150 trades per half, the
binomial SE of a win rate is ~4pp — a 50->54 move is inside one SE and the
null in (5) is the real referee; (b) blend win rate can be lifted by MIX
SHIFT (dropping low-WR donchian trades) — mix is reported per rule and a
mix-shift-only rule is flagged even if promoted; (c) exit-shape rules (E)
mechanically trade win rate against tail size — MAR + mean-step guards
(2)(3) are the defense.
"""
import csv
import os
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE  # noqa: E402
from app.engine.core import (                                            # noqa: E402
    Bar, Book, TradeCfg, eval_donchian, eval_signal,
    process_closed_bar, resolve_open_exit,
)
from app.engine.replay import compute_indicators                         # noqa: E402

BARS_CSV = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BARS_CSV")
bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS_CSV))]
T0 = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
SPLIT = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
INDS = compute_indicators(bars)
N_BARS = len(bars)

# ---------------------------------------------------------------- gate inputs
closes = np.array([b.close for b in bars])
highs = np.array([b.high for b in bars])
lows = np.array([b.low for b in bars])

ER_W = 180  # 30 days of 4h bars
_abs_d = np.abs(np.diff(closes, prepend=closes[0]))
_cum = np.cumsum(_abs_d)
ER = np.full(N_BARS, np.nan)
for i in range(ER_W, N_BARS):
    path = _cum[i] - _cum[i - ER_W]
    ER[i] = abs(closes[i] - closes[i - ER_W]) / path if path > 0 else 0.0

SLOPE_W = 30
S50 = np.array([i.sma50 if i.sma50 is not None else np.nan for i in INDS])
S200 = np.array([i.sma200 if i.sma200 is not None else np.nan for i in INDS])
ATR = np.array([i.atr14 if i.atr14 is not None else np.nan for i in INDS])
HI20 = np.array([i.hi20 if i.hi20 is not None else np.nan for i in INDS])
LO20 = np.array([i.lo20 if i.lo20 is not None else np.nan for i in INDS])
SLOPE50 = np.full(N_BARS, np.nan)
SLOPE50[SLOPE_W:] = S50[SLOPE_W:] - S50[:-SLOPE_W]


def wilder_adx(period: int = 14) -> np.ndarray:
    up = highs[1:] - highs[:-1]
    dn = lows[:-1] - lows[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([highs[1:] - lows[1:],
                            np.abs(highs[1:] - closes[:-1]),
                            np.abs(lows[1:] - closes[:-1])])
    n = len(tr)
    atr_s = np.full(n, np.nan)
    pdm_s = np.full(n, np.nan)
    mdm_s = np.full(n, np.nan)
    if n <= period:
        return np.full(N_BARS, np.nan)
    atr_s[period - 1] = tr[:period].sum()
    pdm_s[period - 1] = plus_dm[:period].sum()
    mdm_s[period - 1] = minus_dm[:period].sum()
    for i in range(period, n):
        atr_s[i] = atr_s[i - 1] - atr_s[i - 1] / period + tr[i]
        pdm_s[i] = pdm_s[i - 1] - pdm_s[i - 1] / period + plus_dm[i]
        mdm_s[i] = mdm_s[i - 1] - mdm_s[i - 1] / period + minus_dm[i]
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * pdm_s / atr_s
        mdi = 100 * mdm_s / atr_s
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = np.full(n, np.nan)
    first = 2 * period - 1
    if n > first:
        adx[first] = np.nanmean(dx[period - 1:first + 1])
        for i in range(first + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    out = np.full(N_BARS, np.nan)
    out[1:] = adx
    return out


ADX = wilder_adx(14)

# ------------------------------------------------------------------- harness


def run_gated(pull_gate=None, don_gate=None, pull_tcfg: TradeCfg | None = None,
              warmup_bars: int = 210):
    """Identical loop to replay.run_replay for S3+S4 only, with optional
    entry gates gate(i, side)->bool on the SIGNAL bar index, and an optional
    pullback-specific TradeCfg (stop width study). Engine code untouched."""
    scfg, tcfg = RESEARCH_SIGNAL, RESEARCH_TRADE
    ptc = pull_tcfg or tcfg
    cfgs = {c.name: c for c in RESEARCH_BOOKS}
    b3, b4 = Book(cfg=cfgs["S3"]), Book(cfg=cfgs["S4"])
    for i, bar in enumerate(bars):
        if i < warmup_bars or bar.ts < T0:
            continue
        resolve_open_exit(b3, bar, ptc)
        resolve_open_exit(b4, bar, tcfg)
        sig_p = eval_signal(bar, INDS[i], scfg)
        if sig_p is not None and pull_gate is not None and not pull_gate(i, sig_p):
            sig_p = None
        sig_d = eval_donchian(bar, INDS[i])
        if sig_d is not None and don_gate is not None and not don_gate(i, sig_d):
            sig_d = None
        process_closed_bar(b3, bar, INDS[i], scfg, ptc, sig_p)
        process_closed_bar(b4, bar, INDS[i], scfg, tcfg, sig_d)
    return b3, b4


def blend_metrics(b3, b4, w_trend=0.25, lev=2.0):
    """Per-half + full metrics on the S6 blend per-trade step stream."""
    evs = sorted([(t.exit_ts, "P", t) for t in b3.trades]
                 + [(t.exit_ts, "T", t) for t in b4.trades])
    p3 = p4 = 1.0
    steps = []                        # (exit_ts, leg, lev-weighted step ret)
    for ts, which, t in evs:
        ratio = t.equity_after / (b3 if which == "P" else b4).cfg.start_equity
        if which == "P":
            r = (ratio / p3 - 1) * (1 - w_trend)
            p3 = ratio
        else:
            r = (ratio / p4 - 1) * w_trend
            p4 = ratio
        steps.append((ts, which, lev * r))

    def _stats(sel):
        if not sel:
            return dict(n=0)
        rets = np.array([s[2] for s in sel])
        wins = int((rets > 0).sum())
        losses = int((rets < 0).sum())
        eq = np.cumprod(1 + rets)
        peak = np.maximum.accumulate(eq)
        mdd = float((eq / peak - 1).min())
        yrs = (sel[-1][0] - sel[0][0]) / (365.25 * 86400)
        cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0.2 else None
        mar = (cagr / abs(mdd)) if cagr is not None and mdd < -0.005 else None
        return dict(n=len(sel),
                    wr=100 * wins / (wins + losses) if wins + losses else None,
                    ret=100 * (eq[-1] - 1), mdd=100 * mdd,
                    mar=mar, mean_step=float(rets.mean()),
                    n_p=sum(1 for s in sel if s[1] == "P"),
                    n_t=sum(1 for s in sel if s[1] == "T"))

    return {"FULL": _stats(steps),
            "A": _stats([s for s in steps if s[0] < SPLIT]),
            "B": _stats([s for s in steps if s[0] >= SPLIT])}


def fmt(m):
    if m["n"] == 0:
        return "n=0"
    return (f"WR={m['wr']:5.1f}% n={m['n']:3d} (P{m['n_p']}/T{m['n_t']}) "
            f"ret={m['ret']:7.1f}% mdd={m['mdd']:5.1f}% "
            f"MAR={m['mar'] if m['mar'] is None else round(m['mar'], 2)} "
            f"mean={100 * m['mean_step']:+.3f}%")


# ------------------------------------------------------------------- rules
def er_thresh(half, q):
    """ER threshold = q-quantile of ER over PULLBACK SIGNAL bars in a half."""
    vals = [ER[i] for i, b in enumerate(bars)
            if b.ts >= T0 and (b.ts < SPLIT if half == "A" else b.ts >= SPLIT)
            and i >= 210 and eval_signal(b, INDS[i], RESEARCH_SIGNAL) is not None
            and not np.isnan(ER[i])]
    return float(np.quantile(vals, q))


def make_er_gate(th):
    return lambda i, s: not np.isnan(ER[i]) and ER[i] >= th


def slope_gate(i, s):
    if np.isnan(SLOPE50[i]):
        return False
    return SLOPE50[i] > 0 if s == "L" else SLOPE50[i] < 0


def sep_gate(i, s):
    if np.isnan(S200[i]) or np.isnan(ATR[i]):
        return False
    return abs(S50[i] - S200[i]) >= 1.0 * ATR[i]


def adx_gate(i, s):
    return not np.isnan(ADX[i]) and ADX[i] >= 20.0


def d_sma200_gate(i, s):
    if np.isnan(S200[i]):
        return False
    return closes[i] > S200[i] if s == "L" else closes[i] < S200[i]


def make_margin_gate(mult):
    def g(i, s):
        if np.isnan(ATR[i]) or np.isnan(HI20[i]):
            return False
        return (closes[i] >= HI20[i] + mult * ATR[i] if s == "L"
                else closes[i] <= LO20[i] - mult * ATR[i])
    return g


RULES = {
    # name: (kind, builder) — parameterized builders take the FIT half
    "P1a-ER-q25": ("pull", lambda h: make_er_gate(er_thresh(h, 0.25))),
    "P1b-ER-q40": ("pull", lambda h: make_er_gate(er_thresh(h, 0.40))),
    "P2-slope50": ("pull", None, slope_gate),
    "P3-sep1atr": ("pull", None, sep_gate),
    "P4-adx20":   ("pull", None, adx_gate),
    "D1-sma200":  ("don", None, d_sma200_gate),
    "D2a-margin.25": ("don", None, make_margin_gate(0.25)),
    "D2b-margin.50": ("don", None, make_margin_gate(0.50)),
    "D3-slope50": ("don", None, slope_gate),
    "E1-stop3.0": ("stop", 3.0),
    "E2-stop2.0": ("stop", 2.0),
    # C1 combo constructed at runtime from best P + best D on the fit half
}


def run_rule(name, fit_half=None):
    spec = RULES[name]
    if spec[0] == "pull":
        gate = spec[1](fit_half) if spec[1] is not None else spec[2]
        return run_gated(pull_gate=gate)
    if spec[0] == "don":
        return run_gated(don_gate=spec[2])
    if spec[0] == "stop":
        tc = TradeCfg(stop_atr=spec[1], time_stop_bars=RESEARCH_TRADE.time_stop_bars,
                      taker_fee_bps=RESEARCH_TRADE.taker_fee_bps,
                      maker_fee_bps=RESEARCH_TRADE.maker_fee_bps)
        return run_gated(pull_tcfg=tc)
    raise ValueError(name)


# ------------------------------------------------------------------- main
if __name__ == "__main__":
    base3, base4 = run_gated()
    BASE = blend_metrics(base3, base4)
    print("== BASELINE S6 (75/25 @2.0x) ==")
    for k in ("FULL", "A", "B"):
        print(f"  {k:4s} {fmt(BASE[k])}")

    results = {}
    for name in RULES:
        spec = RULES[name]
        if spec[0] == "pull" and spec[1] is not None:   # parameterized: per fit half
            for h in ("A", "B"):
                b3, b4 = run_rule(name, fit_half=h)
                results[f"{name}|fit{h}"] = blend_metrics(b3, b4)
        else:
            results[name] = blend_metrics(run_rule(name)[0], run_rule(name)[1]) \
                if False else blend_metrics(*run_rule(name))

    print("\n== RULES (A = 2021-23, B = 2024-26; fitX means threshold fit on X) ==")
    for name, m in results.items():
        print(f"{name}")
        for k in ("FULL", "A", "B"):
            print(f"  {k:4s} {fmt(m[k])}")

    import json
    out = {"baseline": BASE, "rules": results}
    path = os.environ.get("WINRATE_OUT", "/tmp/winrate_results.json")
    json.dump(out, open(path, "w"), default=float, indent=1)
    print(f"\nwrote {path}")
