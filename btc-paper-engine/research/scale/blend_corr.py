"""EDGE-SIDE LEVER 3: how much gross notional does DIVERSIFICATION buy at
constant drawdown, with this book's REAL leg correlation?

Basis upgrade over KELLY.md: that study sized S5/S6 on TRADE-CLOSE blend
streams. Trade-close streams cannot express correlation (the legs close on
different dates) and they hide intra-trade drawdown. Here every leg is a
PER-BAR MTM equity return on the SAME 4h grid, so:
  - correlation is MEASURED, not asserted;
  - all N-leg variants have IDENTICAL stream length, so the drawdown
    comparison is apples-to-apples (kelly.dd_prob bootstraps paths of the
    OBSERVED length, so comparing 190 trades to 380 would confound horizon
    with diversification);
  - the drawdown horizon is fixed in CALENDAR terms (2 years of 4h bars);
  - block length is set in BARS.

CAVEAT STATED UP FRONT: a per-bar stream is not more information about the
edge than the trade stream -- it is the same trades observed more finely. The
bootstrap p10 on a bar stream is therefore NOT comparable to KELLY.md's p10 on
a trade stream, and block-length sensitivity is reported for exactly that
reason. The DD-budget column is the one this study leans on.

Vectorised stationary bootstrap (kelly.py's is O(n) pure Python per draw and
unusable at n=9,791); validated against kelly.py's version below.

Run: python3 research/scale/blend_corr.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                               # noqa: E402
import app.engine.core as core                                   # noqa: E402
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay                         # noqa: E402
from app.engine.kelly import stationary_bootstrap_idx as _REF     # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,         # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SEED, BARS_PER_YEAR = 20260804, 2190
EQUITY, REF_LEV = 100_055.0, 1.5
LIVE_GROSS = 0.20 * REF_LEV * 50_000.0            # $15,000
TAKER, MAKER = 4.32, 1.44


def load(p):
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(p))]


# ---- vectorised stationary bootstrap -------------------------------------
def sb_idx(n, out_len, rng, mean_block):
    """Politis-Romano stationary bootstrap indices, vectorised. Same law as
    kelly.stationary_bootstrap_idx: geometric blocks (restart prob
    1/mean_block), uniform starts, wrap-around."""
    p = 1.0 / mean_block
    restart = rng.random(out_len) < p
    restart[0] = True
    seg = np.cumsum(restart) - 1
    nseg = int(seg[-1]) + 1
    pos = np.arange(out_len)
    seg_start = np.zeros(nseg, dtype=np.int64)
    seg_start[seg[restart]] = pos[restart]
    starts = rng.integers(0, n, nseg)
    return (starts[seg] + (pos - seg_start[seg])) % n


def dd_prob(r, m, dd_limit, horizon, draws=400, mean_block=60, seed=SEED):
    rng = np.random.default_rng(seed + 1)
    n = len(r)
    hits = 0
    CH = 80
    done = 0
    while done < draws:
        k = min(CH, draws - done)
        idx = np.stack([sb_idx(n, horizon, rng, mean_block) for _ in range(k)])
        path = 1.0 + m * r[idx]
        bad = np.any(path <= 0, axis=1)
        eq = np.cumprod(np.where(path <= 0, 1e-12, path), axis=1)
        mdd = (eq / np.maximum.accumulate(eq, axis=1) - 1.0).min(axis=1)
        hits += int(np.sum(bad | (mdd < -dd_limit)))
        done += k
    return hits / draws


def dd_constrained(r, dd_limit, p_limit, horizon, cap=30.0, mean_block=60,
                   seed=SEED, steps=14):
    r = np.asarray(r, float)
    if r.mean() <= 0:
        return 0.0
    mn = r.min()
    hi = cap if mn >= 0 else min(cap, 0.99 / abs(mn))
    if dd_prob(r, hi, dd_limit, horizon, mean_block=mean_block, seed=seed) <= p_limit:
        return round(hi, 3)
    lo = 0.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        if dd_prob(r, mid, dd_limit, horizon, mean_block=mean_block, seed=seed) <= p_limit:
            lo = mid
        else:
            hi = mid
    return round(lo, 3)


def kstar_rows(R, cap, npts=121):
    """argmax_m mean(log(1+m*r)) per row of R."""
    out = np.zeros(len(R))
    grid = np.linspace(0, 1, npts)
    for i in range(len(R)):
        r = R[i]
        if r.mean() <= 0:
            continue
        mn = r.min()
        hi = cap if mn >= 0 else min(cap, 0.99 / abs(mn))
        ms = grid * hi
        x = 1.0 + np.outer(ms, r)
        g = np.where(np.any(x <= 0, axis=1), -np.inf,
                     np.log(np.maximum(x, 1e-300)).mean(axis=1))
        out[i] = ms[int(np.argmax(g))]
    return out


def kelly_star1(r, cap=30.0):
    return float(kstar_rows(np.asarray(r, float)[None, :], cap)[0])


def boot_stats(r, draws=300, mean_block=60, cap=30.0, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(r)
    idx = np.stack([sb_idx(n, n, rng, mean_block) for _ in range(draws)])
    stars = kstar_rows(r[idx], cap)
    return (round(float(np.percentile(stars, 10)), 3),
            round(float(np.percentile(stars, 50)), 3),
            round(float((stars == 0).mean()), 3))


# ---- capture per-bar MTM equity ------------------------------------------
TRACE: dict = {}
_ORIG = core._mark_to_market


def _traced(book, close):
    _ORIG(book, close)
    TRACE.setdefault(book.cfg.name, []).append((book.mtm_equity,
                                                book.position is not None))


def replay_traced(rt, start_ts=None):
    global TRACE
    TRACE = {}
    core._mark_to_market = _traced
    try:
        run_replay(load.cache, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                   dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt / 2.0),
                   start_ts=start_ts, cash_apy=0.0)
    finally:
        core._mark_to_market = _ORIG
    return ({k: np.array([x[0] for x in v]) for k, v in TRACE.items()},
            {k: np.array([x[1] for x in v]) for k, v in TRACE.items()})


load.cache = load(BARS)

print("=" * 90)
print("BOOTSTRAP VALIDATION — vectorised vs kelly.py's reference implementation")
print("=" * 90)
rg = np.random.default_rng(7)
a = np.stack([_REF(400, rg, 10) for _ in range(400)])
rg = np.random.default_rng(7)
b = np.stack([sb_idx(400, 400, rg, 10) for _ in range(400)])
print(f"  P(idx[i+1] == idx[i]+1): ref {np.mean(np.diff(a, axis=1) == 1):.4f}  "
      f"mine {np.mean(np.diff(b, axis=1) == 1):.4f}   (target {1-1/10:.4f})")
print(f"  index mean: ref {a.mean():.2f}  mine {b.mean():.2f}   (target {399/2:.2f})")
print(f"  index sd:   ref {a.std():.2f}  mine {b.std():.2f}")
print("  -> same law, ~100x faster. The absolute draws differ (different RNG")
print("     consumption order); every number below is seeded and reproducible.")

mtm, inpos = replay_traced(MAKER + TAKER)
legs = {k: np.diff(mtm[k]) / mtm[k][:-1] for k in ("S3", "S4")}
POS = {k: inpos[k][1:] for k in ("S3", "S4")}
n_bars = len(legs["S3"])
HORIZON = 2 * BARS_PER_YEAR
DD_LIMIT, P_LIMIT = 0.30, 0.10

print()
print("=" * 90)
print("PER-BAR MTM LEG STREAMS")
print("=" * 90)
print(f"  bars: {n_bars} ({n_bars/BARS_PER_YEAR:.2f} years). DD horizon fixed at "
      f"{HORIZON} bars (2.00 years) for EVERY case below.")
for k, v in legs.items():
    print(f"  {k}: in-market {POS[k].mean()*100:5.1f}% | mean {v.mean()*1e4:+6.2f} bp/bar | "
          f"ann.sd {v.std(ddof=1)*np.sqrt(BARS_PER_YEAR)*100:5.1f}% | "
          f"ann.SR {v.mean()/v.std(ddof=1)*np.sqrt(BARS_PER_YEAR):5.2f}")

both = POS["S3"] & POS["S4"]
rho_all = float(np.corrcoef(legs["S3"], legs["S4"])[0, 1])
rho_both = float(np.corrcoef(legs["S3"][both], legs["S4"][both])[0, 1])
print()
print("=" * 90)
print("MEASURED LEG CORRELATION  (RESEARCH_BOOKS asserts -0.15 in a comment)")
print("=" * 90)
print(f"  all {n_bars} bars (flat bars = 0, the portfolio-correct view): rho = {rho_all:+.4f}")
print(f"  both legs in market ({both.sum()} bars, {both.mean()*100:.1f}%):      rho = {rho_both:+.4f}")
print(f"  S3 is in market only {POS['S3'].mean()*100:.0f}% of bars, so "
      f"{1-POS['S3'].mean():.0%} of its capital is IDLE.")
print("  That idle time, not the negative correlation, is the main reason a")
print("  third leg is cheap: it can be in the market when S3 is not.")

OUT = {"rho_all_bars": rho_all, "rho_both_in_market": rho_both, "n_bars": n_bars,
       "horizon_bars": HORIZON, "dd_limit": DD_LIMIT, "p_limit": P_LIMIT,
       "equity": EQUITY, "live_gross_usd": LIVE_GROSS,
       "leg_stats": {k: {"mean_bp_bar": float(v.mean()*1e4),
                         "ann_sd_pct": float(v.std(ddof=1)*np.sqrt(BARS_PER_YEAR)*100),
                         "ann_SR": float(v.mean()/v.std(ddof=1)*np.sqrt(BARS_PER_YEAR)),
                         "in_market_frac": float(POS[k].mean())} for k, v in legs.items()},
       "cases": {}}

sd3, sd4 = legs["S3"].std(ddof=1), legs["S4"].std(ddof=1)
iv = (1/sd3) / (1/sd3 + 1/sd4)
CASES = {"1 leg  pullback only (S3)": {"S3": 1.0},
         "1 leg  trend only (S4)": {"S4": 1.0},
         "2 leg  75/25 = S5 shipped mix": {"S3": 0.75, "S4": 0.25},
         "2 leg  inverse-vol %.2f/%.2f" % (iv, 1-iv): {"S3": iv, "S4": 1-iv},
         "2 leg  50/50": {"S3": 0.5, "S4": 0.5}}

print()
print("=" * 90)
print("WHAT THE SECOND LEG BUYS — gross notional at the SAME DD budget")
print(f"  (largest k = gross/equity with P(maxDD > {DD_LIMIT:.0%}) <= {P_LIMIT:.0%} over 2y)")
print("=" * 90)
print(f"  {'case':<34} {'annSR':>6} {'annsd':>6} {'k@DD30':>7} {'gross$':>10} "
      f"{'x live':>7} {'p10 k':>7}")
for lbl, w in CASES.items():
    s = sum(wi * legs[k] for k, wi in w.items())
    k_dd = dd_constrained(s, DD_LIMIT, P_LIMIT, HORIZON)
    p10, p50, pneg = boot_stats(s)
    OUT["cases"][lbl] = {
        "weights": w, "k_at_DD30": k_dd, "gross_usd_at_DD30": k_dd * EQUITY,
        "x_live": k_dd * EQUITY / LIVE_GROSS,
        "ann_SR": float(s.mean()/s.std(ddof=1)*np.sqrt(BARS_PER_YEAR)),
        "ann_sd_pct": float(s.std(ddof=1)*np.sqrt(BARS_PER_YEAR)*100),
        "p10": p10, "p50": p50, "prob_neg": pneg}
    c = OUT["cases"][lbl]
    print(f"  {lbl:<34} {c['ann_SR']:>6.2f} {c['ann_sd_pct']:>5.1f}% {k_dd:>7.3f} "
          f"{k_dd*EQUITY:>10,.0f} {c['x_live']:>6.2f}x {p10:>7.3f}")

b1 = OUT["cases"]["1 leg  pullback only (S3)"]
b2 = OUT["cases"]["2 leg  75/25 = S5 shipped mix"]
print()
print(f"  1 leg -> 2 legs at the shipped mix, SAME DD budget: "
      f"${b1['gross_usd_at_DD30']:,.0f} -> ${b2['gross_usd_at_DD30']:,.0f} "
      f"= {b2['k_at_DD30']/b1['k_at_DD30']:.2f}x gross")
print(f"  vol route as a cross-check: ann.sd {b1['ann_sd_pct']:.1f}% -> "
      f"{b2['ann_sd_pct']:.1f}% = {b1['ann_sd_pct']/b2['ann_sd_pct']:.2f}x")

# ---- the general N-leg law with this book's numbers ---------------------
print()
print("=" * 90)
print("THE sqrt(N) LAW WITH THIS BOOK'S REAL rho")
print("=" * 90)
print("  Equal-weight N legs at this book's per-leg vol and pairwise rho:")
print("  gross multiplier at CONSTANT portfolio vol = sqrt(N / (1 + (N-1) rho))")
print(f"  {'rho':>8} " + " ".join(f"{'N='+str(n):>7}" for n in (1, 2, 3, 4, 5, 6, 8)))
NT = {}
for rho, tag in ((rho_all, "MEASURED all-bars"), (rho_both, "MEASURED both-in-mkt"),
                 (0.0, "textbook sqrt(N)"), (0.10, ""), (0.25, ""), (0.50, "")):
    row, line = {}, f"  {rho:>+8.3f} "
    for N in (1, 2, 3, 4, 5, 6, 8):
        d = 1 + (N - 1) * rho
        f = float(np.sqrt(N / d)) if d > 1e-9 else float("inf")
        row[N] = f
        line += (f"{f:>7.2f} " if np.isfinite(f) else f"{'inf':>7} ")
    NT[f"{rho:+.4f}"] = row
    print(line + ("  <- " + tag if tag else ""))
OUT["sqrtN_law"] = NT
print()
print(f"  rho is NEGATIVE here, so the law is SUPER-sqrt(N): 2 legs buy "
      f"{np.sqrt(2/(1+rho_all)):.2f}x gross, not 1.41x.")
print(f"  It breaks at N >= 1 + 1/|rho| = {1+1/abs(rho_all):.1f}: a uniform "
      f"negative correlation")
print("  matrix stops being a valid covariance there. Read N=2 and N=3; the")
print("  tail of that row is the formula failing, not a real result.")

# ---- a third leg: SIMULATED --------------------------------------------
print()
print("=" * 90)
print("A THIRD LEG — SIMULATED. No third strategy exists in this repo.")
print("=" * 90)
print("  Gaussian copula on S4's EMPIRICAL marginal (so it inherits S4's fat")
print("  tails and S4's edge), correlated rho_target to the mean of the two")
print("  real legs. ITS SHARPE IS AN ASSUMPTION, NOT A MEASUREMENT.")
rng = np.random.default_rng(SEED)
zb = np.mean([(legs[b] - legs[b].mean()) / legs[b].std(ddof=1)
              for b in ("S3", "S4")], axis=0)
zb = (zb - zb.mean()) / zb.std(ddof=1)
src = np.sort(legs["S4"])
print()
print(f"  {'rho(3rd,others)':<16} {'annSR':>6} {'k@DD30':>7} {'gross$':>10} "
      f"{'vs 2leg':>8} {'vs live':>8}")
TH = {}
for tgt in (rho_all, 0.0, 0.10, 0.25, 0.50):
    z = tgt * zb + np.sqrt(max(0.0, 1 - tgt ** 2)) * rng.standard_normal(n_bars)
    l3 = src[np.argsort(np.argsort(z))]
    s = 0.50 * legs["S3"] + 0.25 * legs["S4"] + 0.25 * l3
    k_dd = dd_constrained(s, DD_LIMIT, P_LIMIT, HORIZON)
    TH[f"{tgt:+.4f}"] = {"mix": "S3 0.50 / S4 0.25 / synth 0.25", "k_at_DD30": k_dd,
                         "gross_usd_at_DD30": k_dd * EQUITY,
                         "vs_2leg": k_dd / b2["k_at_DD30"],
                         "x_live": k_dd * EQUITY / LIVE_GROSS,
                         "ann_SR": float(s.mean()/s.std(ddof=1)*np.sqrt(BARS_PER_YEAR))}
    t = TH[f"{tgt:+.4f}"]
    print(f"  {tgt:>+8.4f}        {t['ann_SR']:>6.2f} {k_dd:>7.3f} "
          f"{k_dd*EQUITY:>10,.0f} {t['vs_2leg']:>7.2f}x {t['x_live']:>7.2f}x")
OUT["third_leg_simulated"] = TH

print()
print("=" * 90)
print("BLOCK-LENGTH SENSITIVITY (the one free parameter in the DD estimate)")
print("=" * 90)
SENS = {}
s = 0.75 * legs["S3"] + 0.25 * legs["S4"]
for mb in (20, 60, 120, 240):
    k = dd_constrained(s, DD_LIMIT, P_LIMIT, HORIZON, mean_block=mb)
    SENS[mb] = {"k": k, "gross_usd": k * EQUITY}
    print(f"  mean_block {mb:>3d} bars ({mb*4/24:>5.1f} days): k = {k:>6.3f} -> "
          f"${k*EQUITY:>10,.0f} gross")
OUT["block_sensitivity"] = SENS
print("  The LEVEL moves with block length. The RATIO between cases -- which is")
print("  what the diversification claim rests on -- is the robust part:")
for lbl in ("1 leg  pullback only (S3)", "2 leg  75/25 = S5 shipped mix"):
    w = OUT["cases"][lbl]["weights"]
    ss = sum(wi * legs[k] for k, wi in w.items())
    k240 = dd_constrained(ss, DD_LIMIT, P_LIMIT, HORIZON, mean_block=240)
    OUT["cases"][lbl]["k_at_DD30_mb240"] = k240
    print(f"    {lbl:<34} k(mb=240) = {k240:.3f}")
r60 = b2["k_at_DD30"] / b1["k_at_DD30"]
r240 = (OUT["cases"]["2 leg  75/25 = S5 shipped mix"]["k_at_DD30_mb240"]
        / OUT["cases"]["1 leg  pullback only (S3)"]["k_at_DD30_mb240"])
print(f"    diversification RATIO: {r60:.2f}x (mb=60) vs {r240:.2f}x (mb=240)")
OUT["diversification_ratio"] = {"mb60": r60, "mb240": r240}

json.dump(OUT, open(os.path.join(HERE, "blend_corr.json"), "w"), indent=1, default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'blend_corr.json')}")
