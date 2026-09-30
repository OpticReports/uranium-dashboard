"""CANDIDATE B - THE PROPOSAL, measured. Two steps, because the repo's own
discipline rule forbids one ("Never move SIZING_BASE_USD and KELLY_M in the
same step", EXECUTOR.md). That rule turns out to be exactly right here, and it
is what makes this change verifiable by an EQUALITY test instead of a judgement.

KEY DESIGN RESULT, found by reading _cap_room rather than by adding to it:
  cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV * base)   [mirror.py 1486]
MAX_ACCOUNT_LEV IS ALREADY A FRACTION OF BASE. So Candidate B needs NO new
sizing constant and NO change to the sizing arithmetic - only new VALUES. Adding
a MAX_NOTIONAL_FRAC would have been a third rail redundant with the second
(min of two fractions of the same quantity is just the smaller fraction), which
would have DELETED a rail while appearing to add one.

STEP 1  FRACTIONALISE AT MATCHED RISK - ships ZERO size change.
  KELLY_M            0.20   -> 0.10       (halved because base doubles)
  SIZING_BASE_USD    50,000 -> 0          (0 = "use equity", mirror.py _base)
  MAX_ACCOUNT_LEV    2.0    -> 0.20       (becomes THE operating rail, a fraction)
  MAX_NOTIONAL_USD   20,000 -> 45,000     (demoted to a ratcheted NOVELTY ceiling:
                                           does NOT auto-scale, by design)
  EQUITY_SANITY_MULT (new)  -> 1.25       (code constant; bounds a bad equity read
                                           at 1.25x - TIGHTER than today's 1.333x.
                                           railfrac_sanity.py measures why this is
                                           what lets MAX_NOTIONAL_USD be generous.)
  DD_HALT_PCT        0.35   -> 0.175      (preserves today's 17.5%-of-equity line)
  DAILY_LOSS_HALT_PCT 0.06  -> 0.03       (preserves today's 3.0%-of-equity line)
  Net: gross 15,000 -> 15,008. Blast radius 20.0% -> 20.0% of equity. Halt lines
  unchanged in real terms. The book now scales with equity with no further edit.

STEP 2  TAKE THE FREE 2x - a separate, separately gated size decision, and NOT
  one this study authorises (it rests on the unresolved fee-basis question).
  KELLY_M 0.10 -> 0.20, MAX_ACCOUNT_LEV 0.20 -> 0.40, MAX_NOTIONAL_USD 45,000 ->
  90,000 together, preserving every ratio.

Run: python3 research/scale/railfrac_proposal.py
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from railfrac_sim import (Rails, simulate, event_stream, EQUITY_LIVE,   # noqa: E402
                          SIZING_BASE_USD, MAX_NOTIONAL_USD, DD_HALT_PCT,
                          DAILY_LOSS_HALT_PCT, REFERENCE_LEV, MAX_ACCOUNT_LEV,
                          MAX_EXPOSURE_FRAC)

EV = event_stream()
OUT, CH = {}, []


def ck(name, ok, detail=""):
    CH.append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


TODAY = Rails("TODAY", kelly_m=0.20, sizing_base_usd=50_000.0,
              max_notional_usd=20_000.0, max_notional_frac=None,
              max_account_lev=2.0, dd_halt_pct=0.35, daily_loss_halt_pct=0.06)
# NOTE: max_notional_frac is left None throughout - the fractional rail IS
# max_account_lev, which is what mirror.py already multiplies by base.
STEP1 = Rails("STEP 1", kelly_m=0.10, sizing_base_usd=None,
              max_notional_usd=45_000.0, max_notional_frac=None,
              max_account_lev=0.20, dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
STEP2 = Rails("STEP 2", kelly_m=0.20, sizing_base_usd=None,
              max_notional_usd=90_000.0, max_notional_frac=None,
              max_account_lev=0.40, dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
NAIVE = Rails("NAIVE flip", kelly_m=0.20, sizing_base_usd=None,
              max_notional_usd=20_000.0, max_notional_frac=None,
              max_account_lev=2.0, dd_halt_pct=0.35, daily_loss_halt_pct=0.06)

print("=" * 98)
print("CANDIDATE B PROPOSAL - measured against today, at today's equity")
print("=" * 98)
print(f"  {'config':<12} {'gross':>9} {'/eq':>7} {'cap$':>9} {'cap/eq':>7} "
      f"{'headroom':>9} {'DDline/eq':>10} {'mult':>7} {'maxDD':>8} {'deliv':>7}")
ROWS = {}
for R in (TODAY, STEP1, STEP2, NAIVE):
    s = simulate(R, EQUITY_LIVE, events=EV)
    base = R.base(EQUITY_LIVE)
    gross = R.eff_kelly() * R.lev * base
    cap = R.cap_notional(base)
    ddline = R.dd_halt_pct * base
    ROWS[R.label] = {
        "kelly_m": R.kelly_m, "base": base, "gross": gross,
        "gross_frac": gross / EQUITY_LIVE, "cap": cap,
        "cap_frac": cap / EQUITY_LIVE, "headroom": cap / gross,
        "dd_line_usd": ddline, "dd_line_frac": ddline / EQUITY_LIVE,
        "daily_line_usd": R.daily_loss_halt_pct * base,
        "daily_line_frac": R.daily_loss_halt_pct * base / EQUITY_LIVE,
        "mult": s["mult"], "maxdd_pct": s["maxdd_pct"],
        "delivered": s["notional_delivered_frac"], "clamps": s["clamps"],
        "exposure_frac": gross / EQUITY_LIVE,
        "exposure_pages": (gross / EQUITY_LIVE) > MAX_EXPOSURE_FRAC * 1.01}
    r = ROWS[R.label]
    print(f"  {R.label:<12} {gross:>9,.0f} {r['gross_frac']:>7.2%} {cap:>9,.0f} "
          f"{r['cap_frac']:>7.2%} {r['headroom']:>9.3f}x {r['dd_line_frac']:>10.2%} "
          f"{s['mult']:>7.4f} {s['maxdd_pct']:>8.2f}% {r['delivered']:>7.1%}")
OUT["configs_at_live_equity"] = ROWS

print()
print("  STEP 1 IS RISK-NEUTRAL BY CONSTRUCTION - the tests that prove it:")
t, s1 = ROWS["TODAY"], ROWS["STEP 1"]
ck("gross notional within 0.1% of today",
   abs(s1["gross"] / t["gross"] - 1) < 0.001,
   f"${t['gross']:,.0f} -> ${s1['gross']:,.0f} ({s1['gross']/t['gross']-1:+.3%})")
ck("blast radius (cap as a fraction of equity) UNCHANGED",
   abs(s1["cap_frac"] - t["cap_frac"]) < 0.005,
   f"{t['cap_frac']:.2%} -> {s1['cap_frac']:.2%}")
ck("DD halt line unchanged in real terms",
   abs(s1["dd_line_frac"] - t["dd_line_frac"]) < 0.005,
   f"{t['dd_line_frac']:.2%} -> {s1['dd_line_frac']:.2%} of equity")
ck("DAILY halt line unchanged in real terms",
   abs(s1["daily_line_frac"] - t["daily_line_frac"]) < 0.002,
   f"{t['daily_line_frac']:.2%} -> {s1['daily_line_frac']:.2%} of equity")
ck("cap/target headroom ratio preserved",
   abs(s1["headroom"] / t["headroom"] - 1) < 0.02,
   f"{t['headroom']:.3f}x -> {s1['headroom']:.3f}x")
ck("in-sample maxDD within 0.3pp of today",
   abs(s1["maxdd_pct"] - t["maxdd_pct"]) < 0.3,
   f"{t['maxdd_pct']:.2f}% -> {s1['maxdd_pct']:.2f}%")
ck("guard2 invariant MAX_ACCOUNT_LEV >= DD_HALT_PCT holds",
   STEP1.max_account_lev >= STEP1.dd_halt_pct,
   f"{STEP1.max_account_lev} >= {STEP1.dd_halt_pct}")
ck("no new sizing constant is required (frac rail == MAX_ACCOUNT_LEV)",
   STEP1.max_notional_frac is None and STEP2.max_notional_frac is None,
   "cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV*base), unchanged code")
ck("cap_clamp RED always precedes guard2 WARN as equity grows",
   STEP1.max_notional_usd / STEP1.max_account_lev
   < STEP1.max_notional_usd / STEP1.dd_halt_pct,
   f"clamp at equity ${STEP1.max_notional_usd/STEP1.max_account_lev:,.0f} "
   f"< WARN at ${STEP1.max_notional_usd/STEP1.dd_halt_pct:,.0f} "
   f"(provable while MAX_ACCOUNT_LEV > DD_HALT_PCT)")
ck("MAX_NOTIONAL_USD >= DD_HALT_PCT * base (guard2, absolute arm)",
   STEP1.max_notional_usd >= STEP1.dd_halt_pct * EQUITY_LIVE,
   f"{STEP1.max_notional_usd:,.0f} >= {STEP1.dd_halt_pct*EQUITY_LIVE:,.0f}")
ck("NAIVE flip (base only) is NOT risk-neutral - it is the trap",
   abs(ROWS["NAIVE flip"]["gross"] / t["gross"] - 1) > 0.2
   and ROWS["NAIVE flip"]["delivered"] < 0.999,
   f"wants ${0.20*1.5*EQUITY_LIVE:,.0f}, rail delivers "
   f"{ROWS['NAIVE flip']['delivered']:.1%}, halt line "
   f"{t['dd_line_frac']:.1%} -> {ROWS['NAIVE flip']['dd_line_frac']:.1%} of equity")

# ------------------------------------- does STEP 1 scale, forever, with no edit?
print()
print("=" * 98)
print("  STEP 1 AT EVERY EQUITY - the whole point. No config edit at any row.")
print("=" * 98)
print(f"  {'equity':>12} {'gross':>12} {'/eq':>7} {'cap':>12} {'ABS ceiling':>12} "
      f"{'binds?':>8} {'mult':>7} {'maxDD':>8} {'guard2':>8}")
LAD = [100_055.0, 125_000.0, 150_000.0, 200_000.0, 500_000.0, 1_000_000.0,
       3_000_000.0, 6_673_668.0]
SC = []
for eq in LAD:
    s = simulate(STEP1, eq, events=EV)
    base = eq
    frac_cap, abs_cap = STEP1.max_account_lev * base, STEP1.max_notional_usd
    binds = "ABSOLUTE" if abs_cap < frac_cap else "fraction"
    g2 = STEP1.dd_halt_pct * base > min(abs_cap, frac_cap)
    SC.append({"equity": eq, "gross": s["both_legs_target"],
               "frac": s["both_legs_target"] / eq, "cap": s["cap_notional0"],
               "frac_cap": frac_cap, "abs_cap": abs_cap, "binding": binds,
               "mult": s["mult"], "maxdd": s["maxdd_pct"],
               "delivered": s["notional_delivered_frac"], "guard2_warn": g2})
    print(f"  {eq:>12,.0f} {s['both_legs_target']:>12,.0f} "
          f"{s['both_legs_target']/eq:>7.2%} {s['cap_notional0']:>12,.0f} "
          f"{abs_cap:>12,.0f} {binds:>8} {s['mult']:>7.4f} {s['maxdd_pct']:>8.2f}% "
          f"{('WARN' if g2 else '-'):>8}")
OUT["step1_ladder"] = SC
print()
print("  The ABSOLUTE ceiling is what stops proportionality, deliberately, at")
print(f"  equity ${STEP1.max_notional_usd/STEP1.max_account_lev:,.0f} "
      f"(= MAX_NOTIONAL_USD / MAX_ACCOUNT_LEV).")
print("  Past that the book under-sizes and cap_clamp RED fires every entry, and")
print(f"  at equity ${STEP1.max_notional_usd/STEP1.dd_halt_pct:,.0f} guard2's "
      f"halt_config WARN starts too.")
print("  That pair IS the ratchet: it is loud, it is bounded, and it needs a")
print("  human. Nothing silently scales past the size the machinery has proven.")
OUT["ratchet"] = {
    "proportional_to_equity": STEP1.max_notional_usd / STEP1.max_account_lev,
    "guard2_warns_at_equity": STEP1.max_notional_usd / STEP1.dd_halt_pct}

# --------------------------------------------------- what $100k and $1m require
print()
print("=" * 98)
print("  THE HONEST ANSWER: what equity Casey's targets need, under STEP 1 and STEP 2")
print("=" * 98)
print(f"  {'target gross':>13} | {'STEP 1 (15% of eq)':>20} | {'STEP 2 (30% of eq)':>20} "
      f"| {'Kelly env 54%':>15} | {'DD30 ceil 132%':>15}")
ANS = {}
for tgt in (100_000.0, 1_000_000.0):
    row = {"step1_equity": tgt / 0.15, "step2_equity": tgt / 0.30,
           "kelly_env_equity": tgt / 0.54, "dd30_equity": tgt / 1.32,
           "abs_ceiling_needed_step1": tgt / 0.20 * 0.20,
           "max_notional_usd_needed_step1": tgt * (0.20 / 0.15),
           "max_notional_usd_needed_step2": tgt * (0.40 / 0.30)}
    ANS[f"${tgt:,.0f}"] = row
    print(f"  {tgt:>13,.0f} | {row['step1_equity']:>20,.0f} | "
          f"{row['step2_equity']:>20,.0f} | {row['kelly_env_equity']:>15,.0f} | "
          f"{row['dd30_equity']:>15,.0f}")
OUT["answer"] = ANS
print()
print("  Candidate B moves NONE of those equity numbers. It is PLUMBING: it makes")
print("  the rails follow whatever equity exists. The multiplier on equity is set")
print("  by the EDGE (the Kelly envelope), which is a different lane.")
print(f"  What it does buy today: the rail stops being the binding constraint, so")
print(f"  the free 2x (STEP 2) becomes reachable at all - ${ROWS['TODAY']['gross']:,.0f}")
print(f"  -> ${ROWS['STEP 2']['gross']:,.0f} with the caps no longer clamping.")

json.dump({"checks": CH, **OUT},
          open(os.path.join(HERE, "railfrac_proposal.json"), "w"), indent=1, default=str)
print()
print(f"  {sum(1 for c in CH if c['pass'])}/{len(CH)} checks pass -> railfrac_proposal.json")
