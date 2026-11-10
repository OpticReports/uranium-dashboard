"""CANDIDATE B - pricing the HALT RE-CUT that fractionalising the base forces.

The in-sample path cannot do this (railfrac_sim.py M5: realised maxDD is -4.78%,
far inside every candidate halt, so as-is / re-cut / aggressive are byte-
identical runs). The only instrument is the bootstrap, and the repo already
ships it: app.engine.kelly.dd_prob, the same function the Kelly envelope's
P(maxDD>30%)<=10% budget is computed with.

WHAT IS BEING PRICED. With SIZING_BASE_USD = 0 the DD halt condition
  equity < high_water - DD_HALT_PCT * _base(high_water)
becomes exactly  drawdown-from-high-water > DD_HALT_PCT , because
_base(high_water) == high_water. So P(the breaker fires in a 4.4y path with no
bug) is literally P(maxDD > DD_HALT_PCT) - which dd_prob returns.

With SIZING_BASE_USD = 50,000 the same condition is
  drawdown > DD_HALT_PCT * 50,000 / high_water = 17.5% of a $100,055 account.
That is why flipping the base without re-cutting the percentage is a 2.001x
loosening: the threshold goes 17.5% -> 35.0% of the real account.

Basis: TRADE-CLOSE (exit-step) equity returns from railfrac_sim's executor
replica. MTM drawdown runs DEEPER (KELLY.md: 1-4pp), so every P(fire) here is
an UNDER-estimate of the real false-fire rate and every "safe" margin is
optimistic. Stated, not corrected - the executor halts on the equity read it
actually gets, which is MTM, and modelling that is unbuilt work.

Run: python3 research/scale/railfrac_halt.py
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)
import numpy as np                                                # noqa: E402
from app.engine.kelly import dd_prob, SEED                        # noqa: E402
from railfrac_sim import (Rails, simulate, event_stream,          # noqa: E402
                          EQUITY_LIVE, SIZING_BASE_USD, DD_HALT_PCT,
                          DAILY_LOSS_HALT_PCT, REFERENCE_LEV)

EV = event_stream()
OUT = {}
DRAWS = 2000            # kelly.py's own BOOT_DRAWS

# Reference run: Candidate B at base=equity, KELLY_M 0.20 -> gross/equity 0.300
REF = Rails("B", sizing_base_usd=None, max_notional_usd=None,
            max_notional_frac=0.35, dd_halt_pct=9.9, daily_loss_halt_pct=9.9)
s = simulate(REF, EQUITY_LIVE, events=EV)
eq = np.array([e for _, e in s["eq_path"]], dtype=float)
rets = np.diff(np.concatenate([[EQUITY_LIVE], eq])) / np.concatenate([[EQUITY_LIVE], eq])[:-1]
GROSS_FRAC_REF = s["both_legs_target"] / EQUITY_LIVE

print("=" * 92)
print("CANDIDATE B - HALT RE-CUT, bootstrapped with the shipped dd_prob")
print("=" * 92)
print(f"  reference stream: {len(rets)} exit-step returns, executor basis,")
print(f"  gross/equity {GROSS_FRAC_REF:.4f}  (KELLY_M 0.20 x lev 1.5 x base=equity)")
print(f"  realised in-sample maxDD {s['maxdd_pct']:.2f}%   mult {s['mult']:.4f}")
print(f"  mean step {rets.mean()*100:+.4f}%  sd {rets.std(ddof=1)*100:.4f}%  "
      f"draws {DRAWS}  seed {SEED}")

# sanity: reconstruct maxDD from rets and compare to the sim's own
p = np.cumprod(1.0 + rets)
mdd = float(np.min(p / np.maximum.accumulate(p) - 1.0)) * 100
ok = abs(mdd - s["maxdd_pct"]) < 1e-9
print(f"  [{'PASS' if ok else 'FAIL'}] returns reconstruct the sim's maxDD "
      f"({mdd:.6f}% vs {s['maxdd_pct']:.6f}%)")
OUT["reference"] = {"n": len(rets), "gross_frac": GROSS_FRAC_REF,
                    "maxdd_pct": s["maxdd_pct"], "mult": s["mult"],
                    "mean_step_pct": rets.mean() * 100,
                    "sd_step_pct": rets.std(ddof=1) * 100,
                    "reconstruct_ok": ok}

# ---------------------------------------------------------------- the 2-D map
# m is a multiplier on the reference sizing, so gross/equity = m * GROSS_FRAC_REF
SIZES = [("live today          15.0% of equity", 0.15),
         ("CAND B @ KELLY_M .20 30.0% of equity", 0.30),
         ("Kelly envelope now  54.0% of equity", 0.54),
         ("DD30 asymptote     132.0% of equity", 1.32)]
LEVELS = [0.05, 0.10, 0.15, 0.175, 0.20, 0.25, 0.30, 0.35, 0.50]

print()
print("  P(a 4.4y path with NO BUG draws a drawdown past the halt line)")
print("  = the FALSE-FIRE rate of the breaker. Rows are operating size.")
print()
hdr = "  " + f"{'gross/equity':<38}" + "".join(f"{l:>7.1%}" for l in LEVELS)
print(hdr)
GRID = {}
for lbl, gf in SIZES:
    m = gf / GROSS_FRAC_REF
    row = [dd_prob(rets, m, L, draws=DRAWS) for L in LEVELS]
    GRID[lbl] = {"gross_frac": gf, "m": m,
                 "p_fire": dict(zip([str(l) for l in LEVELS], row))}
    print(f"  {lbl:<38}" + "".join(f"{v:>7.1%}" for v in row))
OUT["false_fire_grid"] = GRID
OUT["levels"] = LEVELS

print()
print("  READ-OFF at the size Candidate B actually ships (30.0% of equity):")
g = GRID["CAND B @ KELLY_M .20 30.0% of equity"]["p_fire"]
for L in (0.175, 0.30, 0.35):
    print(f"    DD_HALT_PCT {L:<6} -> P(fire | no bug) {g[str(L)]:.2%}")
print(f"  and the Kelly budget this size was authorised against is "
      f"P(maxDD>30%) <= 10%: measured {g['0.3']:.2%}")

# --------------------------------------- where does the halt sit vs the budget?
print()
print("=" * 92)
print("  THE POLICY FACT, not a measurement: where the breaker sits vs the budget")
print("=" * 92)
print(f"  Kelly drawdown BUDGET (KELLY.md)          30.0% of equity")
print(f"  today's breaker, base 50k                 "
      f"{DD_HALT_PCT*SIZING_BASE_USD/EQUITY_LIVE:.1%} of equity  -> INSIDE the budget")
print(f"  base=equity, DD_HALT_PCT left at 0.35     {DD_HALT_PCT:.1%} of equity  "
      f"-> OUTSIDE the budget (fires only after it is blown)")
print(f"  equivalence re-cut 0.175                  17.5% of equity  -> INSIDE, as today")
print()
print("  A breaker INSIDE the budget will fire on drawdowns the sizing was")
print("  authorised to take; a breaker OUTSIDE it can never protect the budget.")
print("  Both are defensible policies. They are NOT the same policy, and flipping")
print("  the base silently switches from the first to the second.")

# ----------------------------------------- the fixed-dollar halt's drift, priced
print()
print("=" * 92)
print("  WHY THE HALT PERCENTAGE MUST MOVE WITH THE BASE, arithmetically")
print("=" * 92)
print(f"  {'base':>12} {'gross':>10} {'DD line $':>11} {'DD line %eq':>12} "
      f"{'line/gross':>11} {'P(fire) @30%eq size':>20}")
DRIFT = []
for b in (50_000.0, 100_055.0, 200_110.0, 333_333.0):
    gross = 0.20 * REFERENCE_LEV * b
    line = DD_HALT_PCT * b
    frac_eq = line / EQUITY_LIVE
    DRIFT.append({"base": b, "gross": gross, "dd_line_usd": line,
                  "dd_line_frac_equity": frac_eq, "line_over_gross": line / gross})
    print(f"  {b:>12,.0f} {gross:>10,.0f} {line:>11,.0f} {frac_eq:>12.1%} "
          f"{line/gross:>11.3f}x {'-':>20}")
print("  line/gross is CONSTANT at 1.167x - so DD_HALT_PCT*base already scales")
print("  with the book. The halt is NOT the broken rail. What changes when base")
print("  goes 50,000 -> equity is the halt's position relative to the ACCOUNT,")
print("  and that is the 2.001x loosening.")
OUT["halt_drift"] = DRIFT

json.dump(OUT, open(os.path.join(HERE, "railfrac_halt.json"), "w"), indent=1, default=str)
print()
print("  wrote railfrac_halt.json")
