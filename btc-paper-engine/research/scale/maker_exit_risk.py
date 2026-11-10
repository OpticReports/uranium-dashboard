"""IMPLEMENTATION RISK of the second fee fix: resting the SIGNAL/TIME exits.

FIX 1 (maker ENTRY) has essentially no implementation risk: verify_maker.py
shows the limit fills 99.0% of the time and the backtest ALREADY cancels the
non-fills, so the cost is already inside every published number.

FIX 2 (maker EXIT on the 65.3% of S3 exits that are SIGNAL/TIME) is different.
A resting exit that does not fill leaves you IN a position you decided to
leave. That is a real risk and it is priced here, not asserted.

Measurement, on the same fixture, using the shipped exit rule:
  - SIGNAL/TIME exits fill at the NEXT bar's OPEN (core.resolve_open_exit).
  - Passive alternative: rest a limit at the flagging bar's CLOSE on the
    favourable side (for a long exit, a SELL at the close: it is above the
    market only if the next bar trades up through it).
  - Fill test on the exit bar: long exit fills if next_bar.high > limit.
  - If unfilled: you carry the position one more bar. Repeat up to TTL bars,
    then cross. The cost is the extra bar(s) of exposure, measured in bps on
    notional, PLUS the distribution of how bad the worst carry gets.

Run: python3 research/scale/maker_exit_risk.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                            # noqa: E402
from app.engine.core import Bar                               # noqa: E402
from app.engine.replay import run_replay                      # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,      # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
TAKER, MAKER = 4.32, 1.44

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS))]
BY_TS = {b.ts: i for i, b in enumerate(bars)}

res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                 dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=TAKER),
                 cash_apy=0.0)
tr = [t for t in res.books["S3"].trades if t.exit_reason in ("SIGNAL", "TIME")]
print("=" * 88)
print("MAKER-EXIT IMPLEMENTATION RISK — S3 SIGNAL/TIME exits only")
print("=" * 88)
print(f"  candidate exits: {len(tr)} of {len(res.books['S3'].trades)} S3 trades "
      f"({len(tr)/len(res.books['S3'].trades)*100:.1f}%)")
print("  shipped: cross at the NEXT bar's open (that IS the exit_price).")
print("  passive: rest a limit at the FLAGGING bar's close, on the far side.")
print()

OUT = {"n_candidate_exits": len(tr), "n_total_S3": len(res.books["S3"].trades)}
for TTL in (1, 2, 3):
    filled, carry_bps, worst_bps, crossed_bps = 0, [], [], []
    for t in tr:
        i = BY_TS.get(t.exit_ts)          # the bar whose OPEN the shipped exit used
        if i is None or i - 1 < 0 or i + TTL >= len(bars):
            continue
        flag_bar = bars[i - 1]            # the bar whose close flagged the exit
        limit = flag_bar.close            # rest here, on the far side
        sgn = 1.0 if t.side == "L" else -1.0
        got, px, waited = False, None, 0
        for k in range(TTL):
            b = bars[i + k]
            hit = (b.high > limit) if t.side == "L" else (b.low < limit)
            waited = k + 1
            if hit:
                got, px = True, limit
                break
        if not got:
            px = bars[i + TTL].open       # cross after TTL bars
        # cost vs the SHIPPED exit price, in bps of notional, sign-aware
        d = sgn * (px - t.exit_price) / t.entry_price * 1e4
        if got:
            filled += 1
            carry_bps.append(d)
        else:
            crossed_bps.append(d)
        worst_bps.append(d)
    fr = filled / max(1, len(carry_bps) + len(crossed_bps))
    cb = np.array(carry_bps) if carry_bps else np.array([0.0])
    xb = np.array(crossed_bps) if crossed_bps else np.array([0.0])
    wb = np.array(worst_bps)
    fee_saved = fr * (TAKER - MAKER)
    net = fee_saved + wb.mean()
    print(f"  TTL {TTL} bar(s):")
    print(f"    passive exit fill rate           {fr*100:6.2f}%  ({filled} of "
          f"{len(carry_bps)+len(crossed_bps)})")
    print(f"    price effect when it FILLS       {cb.mean():+7.2f} bps mean "
          f"(p10 {np.percentile(cb,10):+.0f}, p90 {np.percentile(cb,90):+.0f})")
    print(f"    price effect when it MISSES      {xb.mean():+7.2f} bps mean "
          f"(p10 {np.percentile(xb,10):+.0f}, worst {xb.min():+.0f})")
    print(f"    ALL exits, mean price effect     {wb.mean():+7.2f} bps   "
          f"sd {wb.std(ddof=1):.0f} bps")
    print(f"    fee saved (maker on fills)       {fee_saved:+7.2f} bps")
    print(f"    NET vs shipped exit              {net:+7.2f} bps per exit")
    OUT[f"TTL{TTL}"] = {"fill_rate": fr, "mean_bps_when_filled": float(cb.mean()),
                        "mean_bps_when_missed": float(xb.mean()),
                        "mean_bps_all": float(wb.mean()),
                        "sd_bps_all": float(wb.std(ddof=1)),
                        "fee_saved_bps": fee_saved, "net_bps": net,
                        "n": len(wb)}

print()
print("  READ: the fee saving is at most (TAKER-MAKER) x fill_rate = "
      f"{(TAKER-MAKER):.2f} x fill_rate bps.")
print("  The price effect has a standard deviation of HUNDREDS of bps, i.e. two")
print("  orders of magnitude larger than the fee it is trying to save. Whether")
print("  the MEAN price effect is positive is a coin-flip on this sample size.")
print("  That asymmetry IS the implementation risk of FIX 2, and it is why FIX 1")
print("  (entry) and FIX 2 (exit) must not be ranked together.")

# ---- how much the fee fix is worth in RAW DOLLARS PER YEAR ---------------
print()
print("=" * 88)
print("THE FEE SAVING IN RAW DOLLARS PER YEAR (separate from authorised size)")
print("=" * 88)
YEARS = (bars[-1].ts - bars[210].ts) / (365.25 * 86400)
n3 = len(res.books["S3"].trades)
n4 = len(res.books["S4"].trades)
print(f"  sample: {YEARS:.2f} years, S3 {n3} trades ({n3/YEARS:.1f}/yr), "
      f"S4 {n4} trades ({n4/YEARS:.1f}/yr)")
SAVE = {}
for gross in (15_000, 20_000, 54_030, 100_000, 250_000, 1_000_000):
    pb, tl = 0.75 * gross, 0.25 * gross
    per_yr_entry = (n3 / YEARS) * pb * (TAKER - MAKER) / 1e4
    per_yr_exit = (n3 / YEARS) * pb * (124/190) * (TAKER - MAKER) / 1e4
    SAVE[gross] = {"fix1_entry_usd_per_yr": per_yr_entry,
                   "fix2_exit_usd_per_yr": per_yr_exit,
                   "both_usd_per_yr": per_yr_entry + per_yr_exit}
    print(f"  gross ${gross:>9,}:  FIX1 ${per_yr_entry:>9,.0f}/yr   "
          f"FIX2 ${per_yr_exit:>9,.0f}/yr   both ${per_yr_entry+per_yr_exit:>9,.0f}/yr")
print("  RESEARCH_FEES.md put FIX 1 at '~$30/yr'. That was at KELLY_M 0.135 on")
print("  the pullback leg alone. At the live $15,000 gross it is the row above;")
print("  the raw saving is small and is NOT the reason to do it. The reason is")
print("  the AUTHORISED-SIZE channel in fee_to_notional.py, which is ~1000x")
print("  larger because it multiplies the whole book, not one leg's fees.")
OUT["annual_fee_saving_usd"] = SAVE
OUT["sample_years"] = YEARS

json.dump(OUT, open(os.path.join(HERE, "maker_exit_risk.json"), "w"), indent=1,
          default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'maker_exit_risk.json')}")
