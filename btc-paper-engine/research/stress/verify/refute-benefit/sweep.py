"""Refuter step B: +-30% on every candidate parameter, all 5 offsets x 3
scenarios + eras E3/E4/E5/2019+. Real re-runs; constants monkeypatched on
the stress module (fast_brake_mult and Executor._open read them at call
time). save=False: nothing is written under research/stress."""
import json, os, sys, time
import numpy as np
HERE = "/home/user/uranium-dashboard/btc-paper-engine/research/stress"
sys.path.insert(0, HERE)
import stress, run_all, harness
import carry_sleeve as cs
from stress import Options, build_spliced, run_path, run_era, DAY
NOW = stress.SEED_NOW; K = 0.75
OUT = "/home/user/uranium-dashboard/btc-paper-engine/research/stress/verify/refute-benefit/sweep.json"

VARIANTS = [  # (label, candidate options, {constant: value})
    ("C1 floor 0.175 (-30%)", Options(fast_brake=True), dict(FAST_BRAKE_FLOOR=0.175)),
    ("C1 floor 0.325 (+30%)", Options(fast_brake=True), dict(FAST_BRAKE_FLOOR=0.325)),
    ("C1 ref 1533 (-30%)", Options(fast_brake=True), dict(FAST_BRAKE_REF_BARS=1533)),
    ("C1 ref 2847 (+30%)", Options(fast_brake=True), dict(FAST_BRAKE_REF_BARS=2847)),
    ("C2 window 3.5d (-30%)", Options(post_stop_damper=True), dict(DAMP_DAYS=3.5)),
    ("C2 window 6.5d (+30%)", Options(post_stop_damper=True), dict(DAMP_DAYS=6.5)),
    ("C2 mults 0.35/0.175 (-30%)", Options(post_stop_damper=True), dict(DAMP_MULTS=(0.35, 0.175))),
    ("C2 mults 0.65/0.325 (+30%)", Options(post_stop_damper=True), dict(DAMP_MULTS=(0.65, 0.325))),
]
DEFAULTS = dict(FAST_BRAKE_FLOOR=0.25, FAST_BRAKE_REF_BARS=2190, DAMP_DAYS=5, DAMP_MULTS=(0.5, 0.25))

def set_consts(d):
    for k, v in DEFAULTS.items():
        setattr(stress, k, d.get(k, v))

def real_funding(start, end):
    lo = (harness.ts_of(start) - DAY) * 1000; hi = harness.ts_of(end) * 1000
    return run_all.btc_funding_from(cs.load_funding(run_all.FUNDING_FILES["XBTUSD"], lo_ms=lo, hi_ms=hi))

ERAS = [("E3", "2020-01-01", "2022-01-01"), ("E4", "2022-01-01", "2024-07-01"),
        ("E5", "2024-07-01", "2026-08-01"), ("Y2019plus", "2019-01-01", "2026-10-08")]
t_start = time.time()
# build the crash inputs once
inputs = {}
for scen, anchor in run_all.SCENARIOS:
    for off in run_all.OFFSETS:
        bb = build_spliced("btcusd", anchor, run_all.MONTHS, off, now=NOW)
        be = build_spliced("ethusd", anchor, run_all.MONTHS, off, now=NOW)
        fund, fmeta = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, run_all.HEADLINE_FUNDING)
        inputs[(scen, off)] = (bb, run_all.run_carry(be, fund).value, run_all.btc_funding_from(fund))
era_fund = {e[0]: real_funding(e[1], e[2]) for e in ERAS}
print("inputs built", round(time.time() - t_start, 1), "s", flush=True)

res = {}
# sanity: defaults reproduce the saved C1 / C2 headline
set_consts({})
bb, cv, bf = inputs[("COVID", 0)]
r = run_path("x", bb, K, carry_value=cv, btc_funding=bf, save=False, options=Options(fast_brake=True), extra=dict(offset_days=0))
assert abs(r["balances"]["365"]["equity"] - 119147.24) < 0.01, r["balances"]["365"]["equity"]
r = run_path("x", bb, K, carry_value=cv, btc_funding=bf, save=False, options=Options(post_stop_damper=True), extra=dict(offset_days=0))
assert abs(r["balances"]["365"]["equity"] - 118178) < 1, r["balances"]["365"]["equity"]
print("defaults reproduce saved C1/C2 COVID off0", flush=True)

for label, opt, consts in VARIANTS:
    set_consts(consts)
    V = dict(crash={}, eras={})
    for scen, anchor in run_all.SCENARIOS:
        V["crash"][scen] = {}
        for off in run_all.OFFSETS:
            bb, cv, bf = inputs[(scen, off)]
            r = run_path("x", bb, K, carry_value=cv, btc_funding=bf, save=False, options=opt, extra=dict(offset_days=off))
            V["crash"][scen][str(off)] = dict(b12=r["balances"]["365"]["equity"], max_dd=r["max_dd"], max_dd_intrabar=r["max_dd_intrabar"],
                                             brake=r["brake_counts"], halts=len(r["halts"]))
    for name, s, e in ERAS:
        r = run_era(name, s, e, K, carry_value=None, btc_funding=era_fund[name], save=False, options=opt, now=NOW)
        V["eras"][name] = dict(usd_per_year=(r["equity_btc"][-1] - 70000.0) / r["years"], max_dd=r["max_dd"], brake=r["brake_counts"], halts=len(r["halts"]))
    res[label] = V
    print(f"{label:28s} done {round(time.time() - t_start)} s | COVID off0 12m {V['crash']['COVID']['0']['b12']:,.0f} dd {V['crash']['COVID']['0']['max_dd']:.1%} | E3 $/yr {V['eras']['E3']['usd_per_year']:,.0f}", flush=True)
set_consts({})
json.dump(res, open(OUT, "w"))
print("saved", OUT, "elapsed", round(time.time() - t_start), "s")
