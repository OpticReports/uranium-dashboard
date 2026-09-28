"""Route (b), MEASURED: how much notional does more DATA buy?

fee_axis.py established that S5's authorised size is set by the bootstrap p10
in 5 of 6 defensible specifications. p10 is an ESTIMATION-ERROR term, so unlike
a drawdown budget it CAN be bought with trades. This measures the exchange rate.

METHOD (single-level, self-calibrating)
  The engine's kelly_uncertainty() approximates the sampling distribution of the
  Kelly point estimate m* by stationary-bootstrapping samples OF LENGTH n from
  the observed stream, then takes the 10th percentile. Generalising to a
  hypothetical sample size n' needs exactly one change: draw samples of length
  n' instead of n. At n' = 146 this reduces EXACTLY to the engine's own call, so
  the curve is pinned to the engine's published number at its left end. That
  calibration check is the whole reason to prefer this construction.

  DISCARDED FIRST CUT, recorded because it was wrong in an instructive way: a
  DOUBLE bootstrap (synthesise a length-n' stream, then bootstrap THAT) gave
  p10 = 1.32 at n' = 146 where the engine gives 0.36 - a 3.7x error, because
  the synthetic streams' own means vary far more than the true sampling
  distribution and p10 is a strongly non-linear functional. It failed its own
  calibration check and was replaced, not tuned.

THE TWO TERMS MOVE IN OPPOSITE DIRECTIONS - the point of the script:
  p10(n')  RISES with n'       : less estimation error
  dd30(H)  FALLS with horizon H: a longer path has more chances to draw down
  so the envelope does not open without limit. WHICH H APPLIES IS A POLICY
  CHOICE, NOT A MEASUREMENT: the repo evaluates P(maxDD>30%) over the observed
  window (146 trades ~ 2y). Both readings are reported.

HONESTY - optimistic by construction:
  - the observed 2y distribution is treated as the population (stationarity).
    Any regime change makes the real curve flatter than this one.
  - that window is the one S1-S6 were SELECTED on, so the edge is
    optimism-inflated (KELLY.md's own multiple-comparison caveat). No
    Deflated-Sharpe haircut is applied here either.
  - it answers "how fast would the envelope open IF the edge is real and
    stable" - a best case, not a forecast.
  - trade-close returns, so intra-trade adverse marks are invisible; KELLY.md
    records realised MTM drawdowns running 1-4pp worse than trade-close.

Run: python3 research/scale/nscale.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                                # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine import kelly as K                                 # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

EQUITY = 100_020.906200          # measured spot USDC (liq.py)
LEV = 1.5
DRAWS = 1000
SEEDS = 3
NS = [146, 220, 300, 400, 550, 750, 1000, 1400, 2000]
TRADES_PER_YEAR = 146 / 2.0


def load(p):
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(p))]


def blend_steps(b3, b4, w, lev):
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity)
                  for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity)
                    for t in b4.trades])
    p3 = p4 = 1.0
    out = []
    for _, which, r in evs:
        if which == "P":
            out.append(lev * (r / p3 - 1) * (1 - w)); p3 = r
        else:
            out.append(lev * (r / p4 - 1) * w); p4 = r
    return out


bars = load(os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv"))
tcfg = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=4.32)   # 8.64 rt MEASURED
res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, tcfg,
                 start_ts=bars[-1].ts - 730 * 86400, cash_apy=0.00)
R = np.array(blend_steps(res.books["S3"], res.books["S4"], 0.25, LEV), dtype=float)
N0 = len(R)
print(f"observed S5 stream (8.64bps rt, cash 0%): n={N0}  "
      f"mean={R.mean()*100:.3f}%  sd={R.std()*100:.2f}%  min={R.min()*100:.2f}%")


def kstar_vec(r, cap=K.M_CAP):
    """Vectorized kelly_star. VERIFIED identical to the engine's below."""
    if len(r) == 0 or r.mean() <= 0:
        return 0.0
    grid = K._m_grid(r, cap)                       # engine's own grid
    X = 1.0 + np.outer(grid, r)
    g = np.where((X <= 0).any(axis=1), -np.inf,
                 np.log(np.maximum(X, 1e-300)).mean(axis=1))
    return float(grid[int(np.argmax(g))])


print("\nVERIFY the fast path against the engine's kelly_star:")
rng = np.random.default_rng(7)
bad = 0
for i in range(40):
    s = R if i == 0 else R[K.stationary_bootstrap_idx(N0, rng)]
    if abs(K.kelly_star(s) - kstar_vec(s)) > 1e-9:
        bad += 1
print(f"  40 streams: mismatches = {bad} -> "
      f"{'IDENTICAL' if bad == 0 else 'FAST PATH WRONG'}")
assert bad == 0, "fast path diverged from the engine; do not trust the scan"


def sample(n, rng):
    """Stationary-bootstrap sample of length n from R. Wraps the engine's index
    generator, which emits len(source) indices per call."""
    out = []
    while len(out) < n:
        out.extend(K.stationary_bootstrap_idx(N0, rng).tolist())
    return R[np.array(out[:n])]


def p10_at(n, draws=DRAWS, seed=0):
    """10th percentile of the sampling distribution of m* at sample size n."""
    rng = np.random.default_rng(seed)
    st = np.array([kstar_vec(sample(n, rng)) for _ in range(draws)])
    return float(np.percentile(st, 10)), float((st == 0).mean())


def dd30_at(H, m, draws=600, seed=11):
    """P(maxDD > 30%) at multiplier m over a path of H steps."""
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(draws):
        path = 1.0 + m * sample(H, rng)
        if np.any(path <= 0):
            hits += 1; continue
        eq = np.cumprod(path)
        pk = np.maximum.accumulate(eq)
        if float(np.min(eq / pk - 1.0)) < -0.30:
            hits += 1
    return hits / draws


def dd30_m_at(H, seed=11):
    lo, hi = 0.0, 4.0
    if dd30_at(H, hi, seed=seed) <= 0.10:
        return hi
    for _ in range(16):
        mid = (lo + hi) / 2
        if dd30_at(H, mid, seed=seed) <= 0.10:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


MSTAR = K.kelly_star(R)
HALF = round(MSTAR / 2, 2)
SR = float(R.mean() / R.std())
DD30_2Y = K.dd_constrained_m(R, 0.30, 0.10)      # engine's own, 146-step horizon
ENG_P10 = K.kelly_uncertainty(R)["p10"]
print(f"  engine calibration: kelly_uncertainty p10 at n=146 = {ENG_P10}   "
      f"m*={MSTAR:.2f}  half={HALF}  dd30(2y)={DD30_2Y}  SR/step={SR:.5f}")

print(f"\nSCAN: {DRAWS} draws x {SEEDS} seeds per n'")
print(f"{'n':>6} {'yrs':>5} {'p10':>6} {'p10 seeds':>20} {'c*':>5} {'dd30@2y':>8} "
      f"{'dd30@n':>7} {'REC m':>6} {'binds':>7} {'gross/eq':>9} "
      f"{'$100k needs':>12} {'$1m needs':>12}")
ROWS = []
for n in NS:
    ps = [p10_at(n, seed=900 + 37 * s + n)[0] for s in range(SEEDS)]
    p10 = float(np.median(ps))
    c_star = n * SR ** 2 / (n * SR ** 2 + 1)
    dd_n = dd30_m_at(n)
    row_fixed = None
    for tag, dd in (("fixed2y", DD30_2Y), ("horizon_n", dd_n)):
        terms = {"half": HALF, "p10": round(p10, 2),
                 "c*xm*": round(c_star * MSTAR, 2), "dd30": dd}
        rec = round(max(0.0, min(terms.values())), 2)
        bind = min(terms.items(), key=lambda t: t[1])[0]
        g = rec * LEV
        row = {"n": n, "years": n / TRADES_PER_YEAR, "dd_basis": tag,
               "p10": p10, "p10_seeds": ps, "c_star": c_star, "dd30": dd,
               "half": HALF, "rec_m": rec, "binding": bind,
               "gross_over_equity": g,
               "max_gross_at_current_equity": g * EQUITY,
               "equity_for_100k": (100_000 / g) if g else None,
               "equity_for_1m": (1_000_000 / g) if g else None}
        ROWS.append(row)
        if tag == "fixed2y":
            row_fixed = row
    g = row_fixed["gross_over_equity"]
    print(f"{n:>6} {n/TRADES_PER_YEAR:>5.1f} {p10:>6.2f} "
          f"{str([round(x, 2) for x in ps]):>20} {c_star:>5.2f} {DD30_2Y:>8.2f} "
          f"{dd_n:>7.2f} {row_fixed['rec_m']:>6.2f} {row_fixed['binding']:>7} "
          f"{g:>8.2f}x {(100_000/g if g else 0):>12,.0f} "
          f"{(1_000_000/g if g else 0):>12,.0f}")

print()
print("=" * 78)
print("THE c* QUESTION (asked explicitly), at the governing numbers")
print("=" * 78)
c146 = N0 * SR ** 2 / (N0 * SR ** 2 + 1)
h = 1 - c146
c_t = 1 - h / 2
n_need = (c_t / (1 - c_t)) / SR ** 2
print(f"  per-step SR = {SR:.5f}   n = {N0}   c* = {c146:.4f}   "
      f"haircut 1-c* = {h:.4f}")
print(f"  halving the haircut to {h/2:.4f} needs c* = {c_t:.4f}")
print(f"    n = (c/(1-c))/SR^2 = {n_need:,.0f} trades = {n_need/N0:.2f}x the sample")
print(f"    = ~{(n_need-N0)/TRADES_PER_YEAR:.1f} MORE YEARS at "
      f"{TRADES_PER_YEAR:.0f} trades/yr")
print(f"  effect on size: c*.m* {c146*MSTAR:.2f} -> {c_t*MSTAR:.2f}; but the min()")
print(f"    also holds p10 and dd30={DD30_2Y:.2f}, and c*.m* is not binding at")
print(f"    either value => HALVING THE c* HAIRCUT BUYS ZERO NOTIONAL.")
ASYM = min(HALF, MSTAR, DD30_2Y)
print(f"  ASYMPTOTE (n->inf: p10->m*={MSTAR:.2f}, c*->1):")
print(f"    rec -> min(half {HALF:.2f}, m* {MSTAR:.2f}, dd30 {DD30_2Y:.2f}) "
      f"= {ASYM:.2f}")
print(f"    ceiling gross/equity = {ASYM*LEV:.2f}x")
print(f"    equity for $100k with a PERFECT sample: ${100_000/(ASYM*LEV):,.0f}")
print(f"    equity for $1m   with a PERFECT sample: ${1_000_000/(ASYM*LEV):,.0f}")

json.dump({"stream": {"n": N0, "mean": float(R.mean()), "sd": float(R.std()),
                      "SR_per_step": SR, "m_star": MSTAR, "half": HALF,
                      "dd30_2y": DD30_2Y, "engine_p10": ENG_P10},
           "scan": ROWS,
           "c_star_question": {"c_star": c146, "haircut": h,
                               "n_to_halve_haircut": n_need,
                               "extra_years": (n_need - N0) / TRADES_PER_YEAR,
                               "moves_authorised_size": False},
           "asymptote": {"rec_m": ASYM, "gross_over_equity": ASYM * LEV,
                         "equity_for_100k": 100_000 / (ASYM * LEV),
                         "equity_for_1m": 1_000_000 / (ASYM * LEV)}},
          open(os.path.join(HERE, "nscale.json"), "w"), indent=1, default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'nscale.json')}")
