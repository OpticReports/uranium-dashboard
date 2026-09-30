"""MASTER ARITHMETIC: what equity and what envelope reach $100k and $1m gross.

Casey's premise is CORRECT and is the axis of this whole script: scale the book
2x AND the capital 2x and the risk PROPORTION is unchanged. The quantity that
sets drawdown is  gross_notional / equity , not gross_notional. So "how do I
trade $1m" has exactly one answer that holds DD constant (more equity) and
several that do not (more m, more lev, a looser DD budget, a longer horizon).

FRAME, established from the code rather than assumed:
  core.py:214      notional = book.equity * cfg.leverage
  kelly.py         "R is the per-step equity return at the book's CURRENT
                    sizing, so m is a multiplier ON TOP of current sizing"
  => in the Kelly study, m = 1 means gross notional = lev * equity.
  mirror.py:1467   _leg_frac = effective_kelly_m * lev * weight
  mirror.py:1475   _base     = SIZING_BASE_USD or equity
  => executor gross = kelly_m * lev * base.
  So the EXECUTOR's kelly_m equals the STUDY's m only when base == equity.
  With base < equity the live book runs at an EFFECTIVE m of
      m_eff = kelly_m * base / equity
  and that is the number the Kelly recommendation must be compared against.
  Cross-check on the executor's own published sizes: EXECUTOR.md's ramp table
  gives pullback entry $11,250 at KELLY_M 0.20, and 0.20*1.5*0.75*50000 = 11,250.

Reads fee_axis.json (the governing envelope) and liq.json (measured equity and
exchange limits) rather than recomputing them - read once, pass down.

Run: python3 research/scale/fee_axis.py && python3 research/scale/liq.py \
     && python3 research/scale/envelope.py
"""
from __future__ import annotations
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                                # noqa: E402

FEE = json.load(open(os.path.join(HERE, "fee_axis.json")))
LIQ = json.load(open(os.path.join(HERE, "liq.json")))

# ---------------------------------------------------------------- live config
EQUITY = float(LIQ["equity"])          # MEASURED spot USDC; the perp pool
                                       # ($1,497) is NOT a balance
KELLY_M, KELLY_M_CAP = 0.20, 0.20
SIZING_BASE_USD, MAX_NOTIONAL_USD = 50_000.0, 20_000.0
MAX_ACCOUNT_LEV, MAX_EXPOSURE_FRAC = 2.0, 0.30
REFERENCE_LEV, MAX_BLEND_LEV = 1.5, 2.0
DD_HALT_PCT, DAILY_LOSS_HALT_PCT = 0.35, 0.06
W_TREND = 0.25

# governing Kelly cell: MEASURED live round trip 8.64 bps, cash_apy 0.00
GOV = FEE["S5_rt8.64_cash0.00"]["analyze"]
REC_M = float(GOV["recommended_m"])
MSTAR = float(GOV["kelly_m"])
DD30_M = float(GOV["dd_constrained"]["p_maxdd30_le_10pct"])
HALF = float(GOV["half_kelly_m"])
# the full defensible-specification range for S5
SPECS = {k: float(v["analyze"]["recommended_m"])
         for k, v in FEE.items() if k.startswith("S5_")}
REC_LO, REC_HI = min(SPECS.values()), max(SPECS.values())

def say(s=""): print(s)
OUT = {}

say("=" * 78)
say("0. THE GOVERNING ENVELOPE - and why it is a RANGE, not a number")
say("=" * 78)
say(f"  RESEARCH_FEES.md's frozen S5 recommendation (0.30) CANNOT be reproduced:")
say(f"  its runner's fee override is a no-op since the wiring fix "
    f"(fee_axis.py proves it: override_dead={FEE['override_dead']}).")
say(f"  Re-fitted through TradeCfg instead, S5's recommended m by specification:")
for k in sorted(SPECS):
    b = FEE[k]["binding"]
    say(f"    {k:<24} rec m {SPECS[k]:>5.2f}   binding {b[0]} @ {b[1]}")
say(f"  RANGE {REC_LO:.2f} - {REC_HI:.2f}  = a {REC_HI/REC_LO:.1f}x spread in")
say(f"  authorised size from ASSUMPTION choices alone.")
say(f"  GOVERNING CELL (measured live fee 8.64bps rt, cash_apy 0): rec m = {REC_M:.2f}")
say(f"    m* {MSTAR:.2f}  half {HALF:.2f}  dd30 {DD30_M:.2f}  -> p10 binds")
say(f"  m_eff of the LIVE book = KELLY_M x base/equity = "
    f"{KELLY_M*SIZING_BASE_USD/EQUITY:.4f}")
say(f"    vs governing rec {REC_M:.2f}  -> live size is "
    f"{REC_M/(KELLY_M*SIZING_BASE_USD/EQUITY):.1f}x UNDER the envelope")
say(f"    vs the WORST defensible spec {REC_LO:.2f} -> live size is "
    f"{(KELLY_M*SIZING_BASE_USD/EQUITY)/REC_LO:.1f}x OVER it")
say("  Both are true. That is the honest state of the envelope.")
OUT["specs"] = SPECS

say(); say("=" * 78)
say("1. EQUITY REQUIRED FOR $100k AND $1m GROSS - the plain arithmetic")
say("=" * 78)
design = KELLY_M * REFERENCE_LEV * SIZING_BASE_USD
say(f"  gross = KELLY_M x lev x base = {KELLY_M} x {REFERENCE_LEV} x "
    f"{SIZING_BASE_USD:,.0f} = ${design:,.0f}")
say(f"    pullback leg ${design*(1-W_TREND):,.0f}   trend leg ${design*W_TREND:,.0f}")
say(f"  equity (MEASURED spot USDC)          ${EQUITY:,.2f}")
say(f"  design gross / equity                {design/EQUITY:.2%}")
say(f"  SIZING_BASE_USD / equity             {SIZING_BASE_USD/EQUITY:.1%}"
    f"   <- the free headroom lives here")
say()
CEIL = [
    ("live config as deployed", design / EQUITY,
     "KELLY_M x lev x base / equity"),
    ("repo cap MAX_EXPOSURE_FRAC", MAX_EXPOSURE_FRAC,
     "KELLY_M_CAP x REFERENCE_LEV; == 'base <= equity' (verify.py V4)"),
    ("Kelly envelope NOW, governing", REC_M * REFERENCE_LEV,
     f"rec_m {REC_M} x lev {REFERENCE_LEV}; bootstrap p10 binds"),
    ("Kelly envelope, best spec", REC_HI * REFERENCE_LEV,
     "6.00bps rt + cash_apy 4% - needs BOTH assumptions to hold"),
    ("Kelly ceiling, n->inf @DD30", DD30_M * REFERENCE_LEV,
     "dd30 asymptote at a FIXED 2y drawdown horizon"),
    ("liq-safe vs 5ATR p99", float(LIQ["crossover_5ATR p99"]["x_equity"]),
     "above this a p99 adverse excursion liquidates before the stop"),
    ("Hyperliquid BTC initial margin", float(LIQ["btc_max_lev"]),
     "meta.universe[BTC].maxLeverage = 40 (tier 1, < $150m notional)"),
]
say(f"  {'ceiling on gross/equity':<32} {'x eq':>7} {'max gross now':>14} "
    f"{'eq for $100k':>13} {'eq for $1m':>13}")
for nm, f, note in CEIL:
    say(f"  {nm:<32} {f:>6.3f}x {f*EQUITY:>14,.0f} {100_000/f:>13,.0f} "
        f"{1_000_000/f:>13,.0f}")
say()
for nm, f, note in CEIL:
    say(f"    {nm:<32} {note}")
OUT["ceilings"] = [{"name": n, "x_equity": f, "note": t,
                    "max_gross_now": f * EQUITY,
                    "equity_for_100k": 100_000 / f,
                    "equity_for_1m": 1_000_000 / f} for n, f, t in CEIL]

say(); say("=" * 78)
say("2. THE DRAWDOWN PRICE OF EACH NOTIONAL LEVEL")
say("=" * 78)
say("  Thorp's infinite-horizon law - the same one kelly.py publishes as its")
say("  analytic cross-check:   P(maxDD > d) = (1-d)^(2/c - 1),  c = m / m*")
say("  Inverted for the drawdown you must budget at p = 0.10:")
say("        d(c) = 1 - exp( ln(0.10) / (2/c - 1) )")
say(f"  m* (governing S5 cell) = {MSTAR:.2f}")
say()

def thorp_p(c, d=0.30):
    if c <= 0: return 0.0
    e = 2.0 / c - 1.0
    return 1.0 if e <= 0 else min(1.0, (1.0 - d) ** e)

def thorp_d(c, p=0.10):
    if c <= 0: return 0.0
    e = 2.0 / c - 1.0
    return None if e <= 0 else 1.0 - math.exp(math.log(p) / e)

scen = [("live as deployed", design),
        ("base=equity (the free 2x)", MAX_EXPOSURE_FRAC * EQUITY),
        ("Kelly envelope now", REC_M * REFERENCE_LEV * EQUITY),
        ("n->inf DD30 ceiling", DD30_M * REFERENCE_LEV * EQUITY),
        ("$100k on current equity", 100_000.0),
        ("$1m on current equity", 1_000_000.0)]
say(f"  {'scenario':<27} {'gross':>11} {'g/eq':>7} {'m_eff':>7} {'c=m/m*':>8} "
    f"{'Thorp P(DD>30%)':>16} {'DD@p=10%':>9}")
ROWS = []
for nm, g in scen:
    m = g / (REFERENCE_LEV * EQUITY)
    c = m / MSTAR
    tp, td = thorp_p(c), thorp_d(c)
    ROWS.append({"scenario": nm, "gross": g, "g_over_eq": g / EQUITY,
                 "m_eff": m, "c": c, "thorp_p_dd30": tp, "dd_at_p10": td})
    say(f"  {nm:<27} {g:>11,.0f} {g/EQUITY:>6.3f}x {m:>7.3f} {c:>8.3f} "
        f"{tp:>15.1%} {(f'{td:>8.1%}' if td is not None else '    RUIN ')}")
say()
say("  'DD@p=10%' is the drawdown you have a 10% chance of exceeding - the")
say("  repo's whole doctrine is that this number stays <= 30%.")
say("  $1m on $100k equity sits at c = 2.55x FULL Kelly. Past c = 2 the growth")
say("  rate itself is NEGATIVE: it is not a drawdown budget question any more,")
say("  it is ruin. (verify.py V1 cross-checks this against the engine's own")
say("  empirical bootstrap over the tradeable range.)")
OUT["dd_pricing"] = ROWS

say(); say("=" * 78)
say("3. THE RAILS: what actually breaks, and the co-move rule")
say("=" * 78)
say("  Three independent rails, only TWO of which clamp:")
say("    _leg_qty        cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV*base)")
say("                    -> CLAMPS, pages RED cap_clamp")
say("    _check_exposure kelly*lev*base/equity <= MAX_EXPOSURE_FRAC")
say("                    -> PAGES ONLY. Never clamps. (verify.py V6)")
say("    _check_halts    DD_HALT_PCT*base <= cap_notional -> WARN halt_config")
say()
say("  Two rules that fall straight out of the code:")
say("   (i) at the shipped blend MAX_EXPOSURE_FRAC == KELLY_M_CAP*REFERENCE_LEV,")
say("       so 'gross/equity <= 0.30' is EXACTLY 'base <= equity'. The 30%")
say("       ceiling is the statement 'never size above fully funded' - it is a")
say("       funding rule, not a Kelly result. (verify.py V4, 0/20000 counterex.)")
say(f"  (ii) halt coherence needs MAX_NOTIONAL_USD >= DD_HALT_PCT*base = "
    f"{DD_HALT_PCT}*base.")
say(f"       Since {DD_HALT_PCT} > {MAX_EXPOSURE_FRAC}, the HALT is the tighter")
say("       rail: MAX_NOTIONAL_USD must lead SIZING_BASE_USD, not follow it.")
say()

def rails(base, mn, eq, kelly=KELLY_M, lev=REFERENCE_LEV):
    gross = min(kelly, KELLY_M_CAP) * lev * base
    cap = min(mn, MAX_ACCOUNT_LEV * base)
    return {"gross_target": gross, "cap_notional": cap,
            "delivered": min(gross, cap), "clamped": gross > cap,
            "exposure_frac": gross / eq,
            "exposure_pages": gross / eq > MAX_EXPOSURE_FRAC * 1.01,
            "dd_halt_need": DD_HALT_PCT * base,
            "halt_incoherent": DD_HALT_PCT * base > cap,
            "min_max_notional": max(DD_HALT_PCT * base, gross)}

CASES = [("TODAY", SIZING_BASE_USD, MAX_NOTIONAL_USD, EQUITY),
         ("base->equity, rail untouched", EQUITY, MAX_NOTIONAL_USD, EQUITY),
         ("base->equity, rail co-moved", EQUITY, 36_000.0, EQUITY),
         ("chase $100k by base alone", 100_000/(KELLY_M*REFERENCE_LEV),
          MAX_NOTIONAL_USD, EQUITY),
         ("$100k, equity+rails correct", 333_334.0, 120_000.0, 333_334.0),
         ("$1m, equity+rails correct", 3_333_334.0, 1_200_000.0, 3_333_334.0)]
for nm, b, mn, eq in CASES:
    r = rails(b, mn, eq)
    say(f"  {nm}")
    say(f"    base ${b:,.0f}  MAX_NOTIONAL ${mn:,.0f}  equity ${eq:,.0f}")
    say(f"    target ${r['gross_target']:,.0f} -> DELIVERED ${r['delivered']:,.0f}"
        f"{'   [RED cap_clamp]' if r['clamped'] else ''}")
    say(f"    exposure {r['exposure_frac']:.1%}"
        f"{'  [RED exposure_over_cap]' if r['exposure_pages'] else '  (inside 30%)'}"
        f"   DD halt needs ${r['dd_halt_need']:,.0f} vs cap "
        f"${r['cap_notional']:,.0f}"
        f"{'  [WARN halt_config]' if r['halt_incoherent'] else '  coherent'}")
    say(f"    MAX_NOTIONAL_USD must be >= ${r['min_max_notional']:,.0f}")
    OUT.setdefault("rails", {})[nm] = r
say()
say(f"  ROUTE (d): MAX_NOTIONAL_USD ${MAX_NOTIONAL_USD:,.0f} is pure plumbing. Not")
say(f"  binding today (target ${design:,.0f} < ${MAX_NOTIONAL_USD:,.0f}) but it binds the")
say("  instant base rises, and it binds LOUDLY - every entry clamps and pages.")
say(f"  Chasing $100k with SIZING_BASE_USD alone delivers "
    f"${rails(100_000/(KELLY_M*REFERENCE_LEV), MAX_NOTIONAL_USD, EQUITY)['delivered']:,.0f}.")
say("  It is worth exactly one env var and ZERO extra drawdown - but it is a")
say("  PRECONDITION for the other routes, never a source of notional by itself.")

json.dump(OUT, open(os.path.join(HERE, "envelope.json"), "w"), indent=1, default=str)
say(); say(f"  frozen -> {os.path.join(HERE, 'envelope.json')}")
