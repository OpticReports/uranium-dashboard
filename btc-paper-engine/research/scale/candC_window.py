"""CANDIDATE C counter-check W: the S4 sign flip — window effect or data
artefact?

candC_multi.py measures BTC's donchian trend leg (S4) at ann.SR -0.75 on HL
data over 2024-06 -> 2026-09. blend_corr.py measured the SAME leg at +0.67 on
the repo's own fixture over 2022-02 -> 2026-07. Two candidate explanations:
  (a) WINDOW: the trend edge simply is not there in the last ~2.2 years;
  (b) DATA: HL candles differ from the fixture enough to flip the sign.
This separates them by running the repo's OWN fixture restricted to the HL
window, and HL data over the fixture's overlap, and comparing all four cells.

If (a), the candidate's baseline is far weaker than KELLY.md implies and that
has to be stated. If (b), every cross-asset number is suspect.

Run: python3 research/scale/candC_window.py
"""
from __future__ import annotations
import json, os, time

import numpy as np
from candC_lib import (BACKEND, FEE_TAKER_RT, HERE, ann_stats, asset_path,
                       boot_stats, load_bars, replay_mtm)

FIXTURE = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
HL_BTC = asset_path("BTC")


def streams(bars, rt=FEE_TAKER_RT, start=None, end=None):
    bb = [b for b in bars if (start is None or b.ts >= start)
          and (end is None or b.ts <= end)]
    mtm, pos, tr = replay_mtm(bb, rt)
    out = {}
    for leg in ("S3", "S4"):
        r = np.diff(mtm[leg]) / mtm[leg][:-1]
        out[leg] = {"r": r, "trades": tr[leg], "pos": pos[leg][1:]}
    out["blend"] = {"r": 0.75 * out["S3"]["r"] + 0.25 * out["S4"]["r"]}
    return out


def row(lbl, s, key):
    r = s[key]["r"]
    st = ann_stats(r)
    p10, p50, pneg = boot_stats(r)
    ntr = len(s[key]["trades"]) if "trades" in s[key] else None
    return {"cell": lbl, "leg": key, "n_bars": len(r), "n_trades": ntr,
            **st, "kstar_p10": p10, "prob_neg_edge": pneg}


def main():
    fx = load_bars(FIXTURE)
    hl = load_bars(HL_BTC)
    HL_START, HL_END = hl[0].ts, hl[-1].ts
    FX_END = fx[-1].ts
    print("=" * 96)
    print("FOUR CELLS — same engine, same fee, BTC only")
    print("=" * 96)
    print(f"  fixture window: {time.strftime('%Y-%m-%d', time.gmtime(fx[0].ts))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(FX_END))}  ({len(fx)} bars)")
    print(f"  HL window:      {time.strftime('%Y-%m-%d', time.gmtime(HL_START))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(HL_END))}  ({len(hl)} bars)")
    OV_END = min(FX_END, HL_END)

    CELLS = {}
    CELLS["A fixture, FULL 2022-02->2026-07"] = streams(fx)
    CELLS["B fixture, HL window only"] = streams(fx, start=HL_START, end=OV_END)
    CELLS["C HL, HL window (= candC basis)"] = streams(hl, end=OV_END)
    CELLS["D HL, full to 2026-09"] = streams(hl)
    # and the pre-HL era, to locate where the trend edge lived
    CELLS["E fixture, PRE-HL 2022-02->2024-06"] = streams(fx, end=HL_START)

    print()
    print(f"  {'cell':<36} {'leg':<6} {'bars':>6} {'trd':>5} {'annSR':>7} "
          f"{'mean bp':>8} {'annSD':>7} {'P(neg)':>7}")
    ROWS = []
    for lbl, s in CELLS.items():
        for key in ("S3", "S4", "blend"):
            rr = row(lbl, s, key)
            ROWS.append(rr)
            print(f"  {lbl:<36} {key:<6} {rr['n_bars']:>6} "
                  f"{(rr['n_trades'] if rr['n_trades'] is not None else 0):>5} "
                  f"{rr['ann_SR']:>+7.2f} {rr['mean_bp_bar']:>+8.2f} "
                  f"{rr['ann_sd_pct']:>6.1f}% {rr['prob_neg_edge']:>7.3f}")
        print()

    def get(cell, leg):
        return next(r for r in ROWS if r["cell"] == cell and r["leg"] == leg)

    print("=" * 96)
    print("VERDICT")
    print("=" * 96)
    b_s4 = get("B fixture, HL window only", "S4")["ann_SR"]
    c_s4 = get("C HL, HL window (= candC basis)", "S4")["ann_SR"]
    a_s4 = get("A fixture, FULL 2022-02->2026-07", "S4")["ann_SR"]
    e_s4 = get("E fixture, PRE-HL 2022-02->2024-06", "S4")["ann_SR"]
    print(f"  SAME WINDOW, different data (B vs C): S4 ann.SR {b_s4:+.2f} vs {c_s4:+.2f}"
          f"   -> data effect = {abs(b_s4-c_s4):.2f}")
    print(f"  SAME DATA, different window (A vs B): S4 ann.SR {a_s4:+.2f} vs {b_s4:+.2f}"
          f"   -> window effect = {abs(a_s4-b_s4):.2f}")
    print(f"  PRE-HL era (E):                       S4 ann.SR {e_s4:+.2f}")
    verdict = ("WINDOW" if abs(a_s4 - b_s4) > 2 * abs(b_s4 - c_s4) else
               "DATA or MIXED")
    print(f"  -> dominant explanation: {verdict}")
    b_bl = get("B fixture, HL window only", "blend")["ann_SR"]
    a_bl = get("A fixture, FULL 2022-02->2026-07", "blend")["ann_SR"]
    print(f"  S5 blend ann.SR: full fixture {a_bl:+.2f} -> HL window {b_bl:+.2f}")
    print("  This is the baseline candidate C is measured against. If it has")
    print("  collapsed on the recent window, every multiple below is a multiple of")
    print("  a much smaller number, and that must be said out loud.")

    json.dump({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "hl_window": [HL_START, HL_END], "fixture_end": FX_END,
               "rows": ROWS,
               "data_effect_s4_annSR": abs(b_s4 - c_s4),
               "window_effect_s4_annSR": abs(a_s4 - b_s4),
               "verdict": verdict},
              open(os.path.join(HERE, "candC_window.json"), "w"), indent=1,
              default=str)
    print("\nfrozen -> candC_window.json")


if __name__ == "__main__":
    main()
