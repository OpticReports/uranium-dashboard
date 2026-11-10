"""CANDIDATE A - fee-basis sensitivity. Everything else ran at the REGISTERED
objective (TradeCfg.taker_fee_bps 6.0 => 12.00 bps round trip). RESEARCH_FEES.md
MEASURED 8.64 live (4.32/side). Does the verdict move? Both arms re-run at
4.32 and at 2.88 (fully-maker ceiling) through TradeCfg, which core.py:261/337
actually read."""
import csv, json, os, sys
from dataclasses import replace
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from app.engine.core import Bar, BookCfg                    # noqa: E402
from app.engine.replay import run_replay                    # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SIZ = {"pullback": 2.5, "trend": 5.0}; W = {"pullback": 0.75, "trend": 0.25}
BLEND_LEV, EQUITY = 1.5, 100_055.0
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY); HOLDOUT = 1719792000
DD_LIMIT, P_LIMIT, DRAWS, SEED = 0.30, 0.10, 2000, 20260804

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS))]


def run_leg(leg, fee):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZ[leg], taker_fee_bps=fee)
    cfg = (BookCfg(name="P", sizing="fixed", strategy="pullback", leverage=1.0,
                   cap=1.0, dd_halt=0.30) if leg == "pullback" else
           BookCfg(name="T", sizing="fixed", strategy="donchian", trail_atr=5.0,
                   leverage=1.0, cap=1.0, dd_halt=0.50))
    bk = run_replay(bars, [cfg], RESEARCH_SIGNAL, tc, cash_apy=0.0).books[cfg.name]
    return [dict(exit_ts=t.exit_ts, s=tc.stop_atr * t.atr_at_entry / t.entry_price,
                 gross=(1.0 if t.side == "L" else -1.0) * (t.exit_price / t.entry_price - 1),
                 fee=t.fees_usd / t.notional) for t in bk.trades]


def boot_idx(n, draws, rng, mb=10):
    p = 1.0 / mb
    idx = np.empty((draws, n), dtype=np.int64); idx[:, 0] = rng.integers(0, n, draws)
    rs = rng.random((draws, n)) < p; jp = rng.integers(0, n, (draws, n))
    for i in range(1, n):
        idx[:, i] = np.where(rs[:, i], jp[:, i], (idx[:, i - 1] + 1) % n)
    return idx


def ddp(st, k, idx):
    x = 1.0 + k * st[idx]; ruin = (x <= 0).any(axis=1)
    nav = np.cumprod(np.where(x <= 0, 1e-12, x), axis=1)
    mdd = (nav / np.maximum.accumulate(nav, axis=1) - 1.0).min(axis=1)
    return float(((mdd < -DD_LIMIT) | ruin).mean())


def kmax(st, idx, hi=6.0):
    lo = 0.0
    if ddp(st, hi, idx) <= P_LIMIT:
        return hi
    for _ in range(40):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if ddp(st, m, idx) <= P_LIMIT else (lo, m)
    return lo


def build(rows, beta, cap, r0, sbar, t0=None):
    e = []
    for leg, rr in rows.items():
        for r in rr:
            su = (r["s"] ** beta) * (sbar[leg] ** (1 - beta))
            nf = min(r0[leg] / su, cap)
            e.append((r["exit_ts"], BLEND_LEV * W[leg] * nf * (r["gross"] - r["fee"]),
                      BLEND_LEV * W[leg] * nf))
    e.sort(key=lambda z: z[0]); e = [z for z in e if t0 is None or z[0] >= t0]
    return np.array([z[1] for z in e]), np.array([z[2] for z in e])


out = {}
for fee, lab in ((6.00, "12.00_registered"), (4.32, "8.64_measured"), (1.44, "2.88_full_maker")):
    rows = {l: run_leg(l, fee) for l in ("pullback", "trend")}
    sbar = {l: float(np.mean([r["s"] for r in rows[l]])) for l in rows}
    out[lab] = {}
    for wname, t0 in (("full", None), ("holdout", HOLDOUT)):
        ref, _ = build(rows, 0.0, 1.0, sbar, sbar, t0)
        idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1))
        sf, nf_ = build(rows, 0.0, 1.0, sbar, sbar, t0)
        sv, nv = build(rows, 1.0, 99.0, sbar, sbar, t0)
        kf, kv = kmax(sf, idx), kmax(sv, idx)
        out[lab][wname] = dict(
            k_fixed=kf, k_vt=kv, k_ratio=kv / kf,
            mean_notional_ratio=float((nv * kv).mean() / (nf_ * kf).mean()),
            max_notional_ratio=float((nv * kv).max() / (nf_ * kf).max()),
            sr_fixed=float(sf.mean() / sf.std()), sr_vt=float(sv.mean() / sv.std()),
            sr_ratio=float((sv.mean() / sv.std()) / (sf.mean() / sf.std())),
            mean_notional_bonus_uncapped=float(nv.mean() / nf_.mean()))
        v = out[lab][wname]
        print(f"fee {lab:18s} {wname:8s} k_ratio={v['k_ratio']:.3f} "
              f"SR_ratio={v['sr_ratio']:.3f} mean_notl={v['mean_notional_ratio']:.3f}x "
              f"max_notl={v['max_notional_ratio']:.3f}x "
              f"(raw notional bonus {v['mean_notional_bonus_uncapped']:.4f}x)")
json.dump(out, open(os.path.join(HERE, "candA_feesens.json"), "w"), default=float)
print("wrote candA_feesens.json")
