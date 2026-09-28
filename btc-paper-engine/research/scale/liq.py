"""Is exchange margin / liquidation the binding constraint at $1m, or is Kelly?

Everything here is MEASURED: Hyperliquid's live `meta` margin tiers, the live
account's own maintenance-margin ratio, and ATR14 from the 10,002-bar fixture
using the engine's own indicator (app.indicators.atr), not a re-derivation.

Run: python3 research/scale/liq.py
"""
from __future__ import annotations
import csv, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                                # noqa: E402
from app.indicators import atr                                    # noqa: E402
from app.config import RESEARCH_BOOKS, RESEARCH_TRADE             # noqa: E402

ACCOUNT = "0xAb533E69e77881D89D0357166851C9653bC551e2"
INFO = "https://api.hyperliquid.xyz/info"
OUT = {}
def post(body):
    r = subprocess.run(["curl", "-sS", "-X", "POST", INFO,
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps(body)], capture_output=True, text=True)
    return json.loads(r.stdout)

print("=" * 78)
print("1. HYPERLIQUID'S REAL MARGIN TIERS FOR BTC (live `meta`, read-only)")
print("=" * 78)
meta = post({"type": "meta"})
btc = next(a for a in meta["universe"] if a["name"] == "BTC")
tbl = dict(meta["marginTables"])[btc["marginTableId"]]
print(f"  BTC: maxLeverage {btc['maxLeverage']}  marginTableId {btc['marginTableId']}"
      f"  szDecimals {btc['szDecimals']}")
print(f"  table '{tbl['description']}':")
for t in tbl["marginTiers"]:
    print(f"    notional >= ${float(t['lowerBound']):>15,.0f}  ->  max leverage "
          f"{t['maxLeverage']}x  (initial margin {100/t['maxLeverage']:.2f}%, "
          f"maintenance {100/(2*t['maxLeverage']):.3f}%)")
print("  Hyperliquid maintenance margin = HALF the initial margin at max")
print("  leverage, i.e. 1/(2*maxLeverage) of position value.")
OUT["btc_tiers"] = tbl["marginTiers"]; OUT["btc_max_lev"] = btc["maxLeverage"]

print()
print("=" * 78)
print("2. WHICH POOL ACTUALLY BACKS LIQUIDATION - measured, not assumed")
print("=" * 78)
ch = post({"type": "clearinghouseState", "user": ACCOUNT})
sp = post({"type": "spotClearinghouseState", "user": ACCOUNT})
pf = post({"type": "portfolio", "user": ACCOUNT})
usdc = next(b for b in sp["balances"] if b["coin"] == "USDC")
spot_total = float(usdc["total"]); spot_hold = float(usdc["hold"])
perp_av = float(ch["marginSummary"]["accountValue"])
mm = float(ch["crossMaintenanceMarginUsed"])
pos = (ch.get("assetPositions") or [{}])[0].get("position", {})
pv = float(pos.get("positionValue", 0.0))
avail = float(sp["tokenToAvailableAfterMaintenance"][0][1])
print(f"  spot USDC total                     ${spot_total:,.6f}   <- hl.py equity()")
print(f"  spot USDC hold                      ${spot_hold:,.6f}")
print(f"  perp marginSummary.accountValue     ${perp_av:,.6f}   <- PERP POOL ONLY, not a balance")
print(f"  crossMaintenanceMarginUsed          ${mm:,.6f}")
print(f"  live BTC positionValue              ${pv:,.6f}  (szi {pos.get('szi')})")
print(f"  tokenToAvailableAfterMaintenance    ${avail:,.6f}")
print()
print(f"  PROOF the SPOT pool is the collateral backing maintenance:")
print(f"    spot_total - crossMaintenanceMarginUsed = "
      f"{spot_total:,.6f} - {mm:,.6f} = {spot_total-mm:,.6f}")
print(f"    tokenToAvailableAfterMaintenance       = {avail:,.6f}")
print(f"    MATCH TO THE CENT: {abs((spot_total-mm)-avail) < 0.01}")
print(f"  -> liquidation-relevant equity is ${spot_total:,.0f}, NOT the "
      f"${perp_av:,.0f} perp pool.")
print(f"  Measured maintenance ratio: {mm:,.6f} / {pv:,.6f} = {mm/pv:.6f}"
      f"  = 1/(2 x {btc['maxLeverage']}) = {1/(2*btc['maxLeverage']):.6f}  "
      f"({abs(mm/pv - 1/(2*btc['maxLeverage'])) < 1e-6})")
EQUITY = spot_total
MAINT = mm / pv
OUT["equity"] = EQUITY; OUT["maint_ratio"] = MAINT; OUT["perp_pool"] = perp_av

print()
print("=" * 78)
print("3. ATR14 ON 4h BARS - the real stop distances (engine's own indicator)")
print("=" * 78)
rows = list(csv.DictReader(open(os.path.join(BACKEND, "tests", "fixtures",
                                            "bars_4h_btcusd.csv"))))
hi = [float(r["high"]) for r in rows]; lo = [float(r["low"]) for r in rows]
cl = [float(r["close"]) for r in rows]
a14 = atr(hi, lo, cl, 14)
pct = np.array([a / c for a, c in zip(a14, cl) if a is not None and c > 0])
STOP_ATR = RESEARCH_TRADE.stop_atr                        # 2.5 (pullback)
TRAIL_ATR = next(b.trail_atr for b in RESEARCH_BOOKS if b.name == "S4")  # 5.0
print(f"  n bars {len(rows)}  ATR14 defined on {len(pct)}")
print(f"  ATR14 as % of close:  median {np.median(pct):.3%}  p90 {np.percentile(pct,90):.3%}"
      f"  p99 {np.percentile(pct,99):.3%}  max {pct.max():.3%}")
print(f"  config: pullback stop_atr = {STOP_ATR}   S4 chandelier trail_atr = {TRAIL_ATR}")
for name, mult in (("pullback stop (2.5 ATR)", STOP_ATR),
                   ("S4 chandelier trail (5.0 ATR)", TRAIL_ATR)):
    d = pct * mult
    print(f"  {name:<32} median {np.median(d):6.2%}  p90 {np.percentile(d,90):6.2%}"
          f"  p99 {np.percentile(d,99):6.2%}  max {d.max():6.2%}")
    OUT[name] = {"median": float(np.median(d)), "p90": float(np.percentile(d, 90)),
                 "p99": float(np.percentile(d, 99)), "max": float(d.max())}
trail = pct * TRAIL_ATR
TRAIL_P99, TRAIL_MAX, TRAIL_MED = (float(np.percentile(trail, 99)),
                                   float(trail.max()), float(np.median(trail)))

print()
print("=" * 78)
print("4. LIQUIDATION DISTANCE vs STOP DISTANCE")
print("=" * 78)
print("  Cross margin: liquidated when equity + PnL <= maint x position_value.")
print("  For a long of notional N on equity E, adverse return r at liquidation:")
print("      E + N*r = maint*N*(1+r)   ->   r = (maint*N - E) / (N*(1 - maint))")
def liq_move(N, E, maint=MAINT):
    den = N * (1.0 - maint)
    return (maint * N - E) / den if den > 0 else float("nan")
print()
print(f"  {'gross N':>12} {'N/E':>7} {'liq move':>10} {'vs 5ATR med':>12} "
      f"{'vs 5ATR p99':>12} {'vs 5ATR max':>12}")
LIQROWS = []
for N in (13_924.0, 15_000.0, 30_010.0, 100_000.0, 200_000.0, 500_000.0, 1_000_000.0):
    r = liq_move(N, EQUITY)
    d = abs(r)
    surv = lambda ref: "SURVIVES" if d > ref else "LIQUIDATES FIRST"
    print(f"  {N:>12,.0f} {N/EQUITY:>6.2f}x {r:>9.2%} "
          f"{surv(TRAIL_MED):>12} {surv(TRAIL_P99):>12} {surv(TRAIL_MAX):>12}"
          + ("   (no liq possible: > -100%)" if r <= -1.0 else ""))
    LIQROWS.append({"N": N, "N_over_E": N/EQUITY, "liq_move": r,
                    "survives_trail_median": d > TRAIL_MED,
                    "survives_trail_p99": d > TRAIL_P99,
                    "survives_trail_max": d > TRAIL_MAX})
OUT["liq"] = LIQROWS
print()
print(f"  Reference stop distances: 5xATR14 median {TRAIL_MED:.2%}, "
      f"p99 {TRAIL_P99:.2%}, max {TRAIL_MAX:.2%}")
print()
# the crossover: what N/E makes liq distance equal the p99 trail
for label, ref in (("5ATR median", TRAIL_MED), ("5ATR p99", TRAIL_P99),
                   ("5ATR max", TRAIL_MAX)):
    # solve |r| = ref  ->  (E - maint*N)/(N(1-maint)) = ref
    Nx = EQUITY / (ref * (1 - MAINT) + MAINT)
    print(f"  Liquidation distance equals {label:<12} ({ref:6.2%}) at gross "
          f"${Nx:>12,.0f} = {Nx/EQUITY:5.2f}x equity")
    OUT[f"crossover_{label}"] = {"gross": Nx, "x_equity": Nx/EQUITY}
print()
print("  Exchange ceiling for comparison: BTC 40x tier-1 -> initial margin")
print(f"  allows ${EQUITY*btc['maxLeverage']:,.0f} gross on this equity.")
json.dump(OUT, open(os.path.join(HERE, "liq.json"), "w"), indent=1, default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'liq.json')}")
