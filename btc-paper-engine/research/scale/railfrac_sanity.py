"""CANDIDATE B - the one NEW code path the design needs, and why it makes the
whole thing strictly better than today rather than a trade.

railfrac_adversarial.py A2 found the real cost of fractionalising: with
SIZING_BASE_USD = 0, mirror.py's unbounded live equity read (2182) starts sizing
trades. It also found that the absolute ceiling's headroom h is simultaneously
the growth room AND the bad-read oversize bound, so one dial cannot serve both.

THE FIX decouples them, using state mirror.py ALREADY maintains - no new
persisted field, no new env var beyond the multiple itself:

    def _base(self, equity):                      # mirror.py 1475
        b = self.cfg.sizing_base_usd or equity
        return b                                   # <- today

    def _sizing_base(self, equity):                # NEW, sizing call sites only
        b = self.cfg.sizing_base_usd or equity
        hw = self.state.high_water
        if not self.cfg.sizing_base_usd and hw > 0:
            lim = EQUITY_SANITY_MULT * hw
            if b > lim:
                self._event("RED", "equity_read_clamped", ...)
                b = lim
        return b

high_water is the right anchor because it already exists, is already persisted,
and is already transfer-adjusted (_reconcile_transfers, 1585-1624), so a genuine
deposit raises it rather than being fought. The HALT path deliberately keeps the
RAW read: it has its own defence (HALT_CONFIRM_POLLS = 3, "so one bad balance
read can't flatten the book", mirror.py 398-399) and clamping there would mask a
real loss.

Run: python3 research/scale/railfrac_sanity.py
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from railfrac_sim import EQUITY_LIVE, REFERENCE_LEV                   # noqa: E402

OUT, CH = {}, []


def ck(name, ok, detail=""):
    CH.append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


E = EQUITY_LIVE
KM, LEV = 0.10, REFERENCE_LEV
TARGET = KM * LEV * E                      # $15,008, matched to today's $15,000
FRAC_RAIL = 0.20                           # MAX_ACCOUNT_LEV after STEP 1


def ships(e_mult, max_notional_usd, sanity_mult=None, hwm=E):
    """Gross notional the next entry ships when the equity read is e_mult x true."""
    read = E * e_mult
    base = read
    if sanity_mult is not None and hwm > 0:
        base = min(base, sanity_mult * hwm)
    return min(KM * LEV * base, max_notional_usd, FRAC_RAIL * base)


print("=" * 98)
print("EQUITY-READ SANITY CLAMP - the dial that stops h doing two jobs")
print("=" * 98)
print(f"  target gross ${TARGET:,.0f} (matched to today's $15,000)")
print(f"  today's bad-read bound, for reference: 1.333x (base is a constant, so")
print(f"  today the bound is really 1.00x in SIZING and 1.333x is the cap ratio)")
print()
print(f"  {'read error':>11} | {'h=1.5 no clamp':>15} {'x':>6} | "
      f"{'h=3.0 no clamp':>15} {'x':>6} | {'h=3.0 clamp 1.25':>17} {'x':>6}")
ROWS = []
for e in (1.0, 1.1, 1.25, 1.5, 2.0, 5.0, 10.0, 100.0):
    a = ships(e, 1.5 * TARGET)
    b = ships(e, 3.0 * TARGET)
    c = ships(e, 3.0 * TARGET, sanity_mult=1.25)
    ROWS.append({"e": e, "h1.5_noclamp": a, "h1.5_x": a / TARGET,
                 "h3_noclamp": b, "h3_x": b / TARGET,
                 "h3_clamp125": c, "h3_clamp_x": c / TARGET})
    print(f"  {e:>11.2f} | {a:>15,.0f} {a/TARGET:>6.2f}x | {b:>15,.0f} "
          f"{b/TARGET:>6.2f}x | {c:>17,.0f} {c/TARGET:>6.2f}x")
OUT["bad_read_rows"] = ROWS

w_a = max(r["h1.5_x"] for r in ROWS)
w_b = max(r["h3_x"] for r in ROWS)
w_c = max(r["h3_clamp_x"] for r in ROWS)
print()
ck("without the clamp, h sets the bad-read bound (h=1.5 -> 1.50x, h=3 -> 3.00x)",
   abs(w_a - 1.5) < 0.02 and abs(w_b - 3.0) < 0.02,
   f"worst {w_a:.2f}x / {w_b:.2f}x")
ck("with the clamp the bound is the SANITY MULT, independent of h",
   abs(w_c - 1.25) < 0.02, f"worst {w_c:.2f}x at h=3.0")
ck("clamped design is TIGHTER than today's 1.333x cap ratio",
   w_c < 20_000.0 / 15_000.0,
   f"{w_c:.3f}x vs today's {20_000/15_000:.3f}x - a safety GAIN, not a trade")

print()
print("  So the recommended STEP 1 uses BOTH dials, each for its own job:")
print(f"    MAX_ACCOUNT_LEV      0.20   the risk rail (constant fraction of equity)")
print(f"    EQUITY_SANITY_MULT   1.25   the bad-INPUT rail (bounds oversize)")
print(f"    MAX_NOTIONAL_USD     {3.0*TARGET:,.0f}   the NOVELTY rail (bounds dollars at a")
print(f"                                size the machinery has not proven), giving")
print(f"                                proportionality to equity ${3.0*TARGET/FRAC_RAIL*FRAC_RAIL/0.15:,.0f}")

# --------------------- does the clamp ever bite in NORMAL operation? (it must not)
print()
print("=" * 98)
print("  DOES THE CLAMP FALSE-FIRE? It bites only when equity > 1.25 x high_water.")
print("=" * 98)
print("  high_water is a RUNNING MAXIMUM, so equity can only exceed it by the gain")
print("  made since the last peak. A 25% gain from a fresh peak in ONE poll (20s)")
print("  is not a return, it is a deposit or a bad read - and deposits are already")
print("  reconciled into high_water when the book is flat (_reconcile_transfers).")
print()
print("  THE ONE REAL FALSE-FIRE CASE, stated because it is not hypothetical:")
print("    a deposit that lands WHILE A POSITION IS OPEN is not reconciled")
print("    (_reconcile_transfers requires a flat book), so high_water lags until")
print("    the next peak. The clamp then under-sizes and pages equity_read_clamped")
print("    until equity/high_water falls back under 1.25. UNDER-sizing + a page is")
print("    the safe direction, and it is self-clearing.")
print("    mirror.py's own docstring already names this limitation: 'a transfer")
print("    that lands during a restart window is seen as a baseline, not a jump'.")
OUT["design"] = {"max_account_lev": FRAC_RAIL, "equity_sanity_mult": 1.25,
                 "max_notional_usd": 3.0 * TARGET,
                 "target_gross": TARGET,
                 "bad_read_bound_clamped": w_c,
                 "bad_read_bound_today_cap_ratio": 20_000.0 / 15_000.0}

json.dump({"checks": CH, **OUT},
          open(os.path.join(HERE, "railfrac_sanity.json"), "w"), indent=1, default=str)
print()
print(f"  {sum(1 for c in CH if c['pass'])}/{len(CH)} checks pass -> railfrac_sanity.json")
