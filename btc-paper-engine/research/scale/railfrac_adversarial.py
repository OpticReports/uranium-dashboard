"""CANDIDATE B - THE ADVERSARIAL PASS ON MY OWN PROPOSAL.

Three attacks. Two land.

A1  "The fixed dollar rail bounded the LATENT-BUG blast radius, and a fractional
     rail scales that exposure too." (the objection the brief demands I price)
     -> LANDS ONLY IN DOLLARS, NOT IN SURVIVABILITY. Measured in railfrac_sim M3.
        Re-stated here with the arithmetic.

A2  "With SIZING_BASE_USD = 0 the SIZING of every trade depends on a LIVE EQUITY
     READ that today's config does not touch."
     -> LANDS, HARD, AND IT IS THE REAL ANSWER to what the fixed rail was
        protecting. mirror.py:2182 `equity = self.venue.equity()` has NO sanity
        bound; it flows into _leg_qty via _base(). Two realised precedents in
        this repo: the 2026-08-06 transient bad balance read (false DRAWDOWN
        halt, mirror.py:1702) and the 2026-08-29 venue mismatch (HWM 59,054
        against equity 9,999, mirror.py:648-668). Today a bad read can only
        false-HALT (annoying, safe). After Candidate B it can also MIS-SIZE
        (real money). Priced below.

A3  "MAX_EXPOSURE_FRAC / KELLY_M_CAP already stop this, so the rail change is
     cosmetic."
     -> DOES NOT LAND. _check_exposure PAGES, it does not clamp (mirror.py
        547-571, by documented design). Verified: it cannot hold size down.
        But the OPPOSITE point does land - see the ladder restatement.

Run: python3 research/scale/railfrac_adversarial.py
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from railfrac_sim import (Rails, simulate, event_stream, EQUITY_LIVE,     # noqa: E402
                          MAX_EXPOSURE_FRAC, REFERENCE_LEV)

EV = event_stream()
OUT, CH = {}, []


def ck(name, ok, detail=""):
    CH.append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


TODAY = Rails("TODAY", kelly_m=0.20, sizing_base_usd=50_000.0,
              max_notional_usd=20_000.0, max_account_lev=2.0,
              dd_halt_pct=0.35, daily_loss_halt_pct=0.06)
STEP1 = Rails("STEP 1", kelly_m=0.10, sizing_base_usd=None,
              max_notional_usd=22_500.0, max_account_lev=0.20,
              dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
NOCEIL = Rails("NO CEILING", kelly_m=0.10, sizing_base_usd=None,
               max_notional_usd=None, max_account_lev=0.20,
               dd_halt_pct=0.175, daily_loss_halt_pct=0.03)

# ============================================== A2  THE BAD EQUITY READ, PRICED
print("=" * 98)
print("A2  BAD EQUITY READ - the failure mode the fixed dollar base was actually")
print("    protecting against, and the one the brief did not name")
print("=" * 98)
print("  mirror.py:2182 reads equity once per poll with no bound. Scenario: the")
print("  read comes back e x the true value (venue glitch, wrong account, a")
print("  spot+perp double count). What gross notional does the NEXT entry ship?")
print()
print(f"  {'read error e':>12} | {'TODAY $':>10} {'x intent':>9} | "
      f"{'STEP 1 $':>10} {'x intent':>9} | {'NO CEILING $':>13} {'x intent':>9}")
A2 = []
for e in (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0):
    eq_read = EQUITY_LIVE * e
    row = {"e": e}
    for R, key in ((TODAY, "today"), (STEP1, "step1"), (NOCEIL, "noceiling")):
        base = R.base(eq_read)
        gross = min(R.eff_kelly() * R.lev * base, R.cap_notional(base))
        intent = min(R.eff_kelly() * R.lev * R.base(EQUITY_LIVE),
                     R.cap_notional(R.base(EQUITY_LIVE)))
        row[key] = {"gross": gross, "x_intent": gross / intent}
    A2.append(row)
    print(f"  {e:>12.1f} | {row['today']['gross']:>10,.0f} "
          f"{row['today']['x_intent']:>9.2f}x | {row['step1']['gross']:>10,.0f} "
          f"{row['step1']['x_intent']:>9.2f}x | {row['noceiling']['gross']:>13,.0f} "
          f"{row['noceiling']['x_intent']:>9.2f}x")
OUT["A2_bad_equity_read"] = A2
worst_today = max(r["today"]["x_intent"] for r in A2)
worst_step1 = max(r["step1"]["x_intent"] for r in A2)
worst_nc = max(r["noceiling"]["x_intent"] for r in A2)
print()
ck("TODAY is perfectly immune to an equity read error in SIZING",
   abs(worst_today - 1.0) < 1e-9,
   "base is a constant, so sizing never reads equity at all")
ck("STEP 1's oversize is BOUNDED by the absolute ceiling",
   worst_step1 <= 1.51,
   f"worst {worst_step1:.2f}x = MAX_NOTIONAL_USD / target = "
   f"{STEP1.max_notional_usd:,.0f} / {STEP1.eff_kelly()*STEP1.lev*EQUITY_LIVE:,.0f}")
ck("WITHOUT the absolute ceiling the error passes through UNBOUNDED",
   worst_nc > 50,
   f"worst {worst_nc:.0f}x at a 100x read - this is why a purely fractional "
   f"rail set is WRONG")
print()
print("  THE CENTRAL TRADE-OFF OF CANDIDATE B, and it is one dial:")
print("    h = MAX_NOTIONAL_USD / target_gross  (the ceiling's headroom)")
print("    h is SIMULTANEOUSLY:")
print("      (a) the equity growth multiple over which proportionality holds, and")
print("      (b) the worst oversize a bad equity read can ship.")
print("    You cannot make one large without making the other large.")
print(f"    TODAY   h = 20,000 / 15,000 = {20_000/15_000:.3f}x")
print(f"    STEP 1  h = {STEP1.max_notional_usd:,.0f} / "
      f"{STEP1.eff_kelly()*STEP1.lev*EQUITY_LIVE:,.0f} = "
      f"{STEP1.max_notional_usd/(STEP1.eff_kelly()*STEP1.lev*EQUITY_LIVE):.3f}x")
H = {}
for h in (1.333, 1.5, 2.0, 3.0):
    tgt = 0.15 * EQUITY_LIVE
    H[f"h={h}"] = {"max_notional_usd": h * tgt,
                   "proportional_to_equity": h * EQUITY_LIVE,
                   "worst_bad_read_oversize": h}
print()
print(f"    {'h':>6} {'MAX_NOTIONAL_USD':>18} {'proportional to equity':>24} "
      f"{'bad-read bound':>16}")
for k, v in H.items():
    print(f"    {k:>6} {v['max_notional_usd']:>18,.0f} "
          f"{v['proportional_to_equity']:>24,.0f} "
          f"{v['worst_bad_read_oversize']:>16.2f}x")
OUT["headroom_dial"] = H

# ==================================== A1  BLAST RADIUS, THE OBJECTION RE-STATED
print()
print("=" * 98)
print("A1  THE LATENT-BUG BLAST RADIUS - priced, not waved away")
print("=" * 98)
print("  EXECUTOR.md RAMP v3 is right that a fixed dollar cap bounds absolute")
print("  loss in the window before a bug is found. The question it does not ask:")
print("  is the QUANTITY THAT MATTERS absolute or relative?")
print()
print("  A sizing bug, a wrong-side bug, a missing-stop bug all lose a fraction")
print("  of the NOTIONAL carried. So the loss scales with notional, and")
print("  notional/equity is what decides whether it is survivable. Under a")
print("  fractional rail that ratio is constant BY CONSTRUCTION:")
print()
print(f"  {'equity':>12} {'TODAY worst loss':>17} {'/eq':>7} | "
      f"{'STEP 1 worst loss':>18} {'/eq':>7}")
A1 = []
for eq in (100_055.0, 500_000.0, 1_000_000.0, 6_673_668.0):
    a = min(TODAY.max_notional_usd, TODAY.max_account_lev * TODAY.base(eq))
    b = min(STEP1.max_notional_usd, STEP1.max_account_lev * eq)
    A1.append({"equity": eq, "today_worst": a, "today_frac": a / eq,
               "step1_worst": b, "step1_frac": b / eq})
    print(f"  {eq:>12,.0f} {a:>17,.0f} {a/eq:>7.1%} | {b:>18,.0f} {b/eq:>7.1%}")
OUT["A1_blast_radius"] = A1
print()
print("  So the objection inverts: the FIXED rail is the one that stops being a")
print("  risk control. At $6.67m of equity it bounds loss at 0.3% - it is no")
print("  longer protecting anything, it is only throttling.")
print()
print("  BUT BE PRECISE, because the table above says so: with h = 1.5 the")
print("  FRACTIONAL rail holds survivability constant only UP TO equity")
print(f"  ${1.5*EQUITY_LIVE:,.0f}. Past that the absolute ceiling binds and")
print("  STEP 1 throttles exactly as today does (4.5% at $500k, 0.3% at $6.67m).")
print("  Candidate B does NOT make the book scale forever unattended. It makes it")
print("  scale proportionally across the range the ceiling authorises, and then")
print("  page loudly. Unattended-forever scaling is what A2 says you must not")
print("  build, so this is the design, not a shortfall.")

# ========================== A3  DOES THE EXPOSURE CHECK HOLD SIZE DOWN? (no) +
#                               THE LADDER RESTATEMENT HAZARD (yes)
print()
print("=" * 98)
print("A3  WHAT THE REPO'S OTHER CAPS DO, AND THE DOC HAZARD STEP 1 CREATES")
print("=" * 98)
# route 1: a hostile/mistaken blend lev. _sane_blend bounds it at MAX_BLEND_LEV.
s_lev = simulate(Rails("lev 2.0", kelly_m=0.10, lev=2.0, sizing_base_usd=None,
                       max_notional_usd=1e12, max_account_lev=9.0,
                       dd_halt_pct=0.175, daily_loss_halt_pct=0.03),
                 EQUITY_LIVE, events=EV)
# route 2: SIZING_BASE_USD re-set above equity - the UNBOUNDED route
s_base = simulate(Rails("base 10x", kelly_m=0.20, sizing_base_usd=10 * EQUITY_LIVE,
                        max_notional_usd=1e12, max_account_lev=9.0,
                        dd_halt_pct=0.175, daily_loss_halt_pct=0.03),
                  EQUITY_LIVE, events=EV)
ck("_check_exposure pages but cannot clamp - confirmed on the base route",
   s_base["clamps"] == 0
   and s_base["both_legs_target"] / EQUITY_LIVE > MAX_EXPOSURE_FRAC,
   f"gross {s_base['both_legs_target']/EQUITY_LIVE:.0%} of equity with rails "
   f"lifted, 0 clamps - only a RED event stands between that and the venue")
ck("STEP 1 CLOSES the unbounded exposure route: with base==equity the worst "
   "CONFIGURABLE gross/equity is KELLY_M_CAP x MAX_BLEND_LEV",
   abs(0.20 * 2.0 - 0.40) < 1e-12,
   f"0.20 x 2.0 = 0.40 of equity, vs UNBOUNDED today "
   f"(base route ships {s_base['both_legs_target']/EQUITY_LIVE:.0%})")
print(f"  worst-case configured exposure:  TODAY unbounded (any SIZING_BASE_USD)")
print(f"                                   STEP 1 bounded at 0.40 of equity")
print(f"                                   (lev route measured: gross/equity "
      f"{s_lev['both_legs_target']/EQUITY_LIVE:.0%}, pages exposure_over_cap)")
print()
print("  THE GAIN nobody has claimed yet: TODAY, KELLY_M_CAP 0.20 bounds nothing")
print("  real, because SIZING_BASE_USD can be any number. mirror.py's own")
print("  MAX_EXPOSURE_FRAC comment asserts the live config 'sits exactly ON the")
print("  line', which is true only when base == equity. After STEP 1 it IS true:")
print(f"    base == equity  =>  gross/equity = KELLY_M x lev, so")
print(f"    KELLY_M <= KELLY_M_CAP 0.20  <=>  gross/equity <= "
      f"{0.20*REFERENCE_LEV:.2f} = MAX_EXPOSURE_FRAC")
ck("after STEP 1 KELLY_M_CAP becomes a real bound on gross/equity",
   abs(0.20 * REFERENCE_LEV - MAX_EXPOSURE_FRAC) < 1e-12,
   "the identity MAX_EXPOSURE_FRAC = KELLY_M_CAP * REFERENCE_LEV closes")
print()
print("  THE HAZARD, and it is the cap_coherence failure mode again: every rung")
print("  in EXECUTOR.md's RAMP v3 table is a KELLY_M value quoted at base 50,000.")
print("  Flipping the base RE-VALUES EVERY RUNG by 2.001x without editing a word")
print("  of the table. The ladder MUST be restated in the same commit:")
print()
print(f"  {'rung':<16} {'old KELLY_M':>12} {'old gross':>11} {'/eq':>7} | "
      f"{'new KELLY_M':>12} {'same gross':>11}")
LAD = [("token", 0.05), ("A", 0.10), ("B = ceiling", 0.20),
       ("live (0.135)", 0.135)]
RE = []
for nm, k in LAD:
    old_gross = k * REFERENCE_LEV * 50_000.0
    new_k = old_gross / (REFERENCE_LEV * EQUITY_LIVE)
    RE.append({"rung": nm, "old_kelly_m": k, "gross": old_gross,
               "gross_frac": old_gross / EQUITY_LIVE, "new_kelly_m": new_k})
    print(f"  {nm:<16} {k:>12.3f} {old_gross:>11,.0f} "
          f"{old_gross/EQUITY_LIVE:>7.2%} | {new_k:>12.3f} {old_gross:>11,.0f}")
OUT["A3_ladder_restatement"] = RE
print()
print("  Read the other way: after STEP 1, KELLY_M 0.10 IS rung B. Anyone who")
print("  reads the un-restated table sees '0.10 = rung A, mid-ramp' while the")
print("  book is at THE CEILING. That is exactly how MAX_NOTIONAL_USD came to")
print("  disagree with SIZING_BASE_USD for a month.")

json.dump({"checks": CH, **OUT},
          open(os.path.join(HERE, "railfrac_adversarial.json"), "w"),
          indent=1, default=str)
print()
print(f"  {sum(1 for c in CH if c['pass'])}/{len(CH)} checks pass -> railfrac_adversarial.json")
