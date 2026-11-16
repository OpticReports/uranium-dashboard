"""EXIT2 runner (PREREG.md). Writes results_sel.json, then results_holdout.json.

usage: python3 run2.py sel        # all 28 configs on the in-sample set; picks finalists
       python3 run2.py holdout    # the finalists, ONCE, on the 12 fresh coins
"""
import dataclasses
import json
import os
import statistics
import sys
import time

from harness2 import (BASE, HOLDOUT, INSAMPLE, LIVE_LEV, LIVE_W_TREND, MODELS,
                      S4_CFG, T_2013, T_2022, T_FWD, T_IS_END, blend_exit_step,
                      blend_mtm, collect_samples, curve_stats, extend,
                      load_asset, load_holdout, run_s3, run_s4x, trade_stats,
                      train_models)
from variants2 import ALL, family

HERE = os.path.dirname(os.path.abspath(__file__))
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
W, LEV = LIVE_W_TREND, LIVE_LEV

AS = {s: load_asset(s) for s in INSAMPLE}
EX = {s: extend(A) for s, A in AS.items()}
BTC, EB = AS["btc"], EX["btc"]
B3, M3 = run_s3(BTC, T_2022, T_IS_END)


def setup_models():
    samples = []
    for s in INSAMPLE:
        end = T_IS_END if s == "btc" else None
        samples += collect_samples(AS[s], EX[s], NOHALT, T_2013 if s == "btc" else None, end)
    train_models(samples)
    return len(samples), sorted(MODELS)


def mar(x):
    return x["mar"] if x["mar"] is not None else 0.0


def kept(book):
    """Median share of the peak favorable move kept, over trades whose peak
    move was >= 10% of entry (the runs the trail exists for)."""
    by = {}
    for t in book.trades:
        by.setdefault(t.entry_ts, []).append(t)
    ks = []
    for parts in by.values():
        t0 = parts[0]
        mfe = getattr(parts[-1], "mfe_px", None)
        if mfe is None:
            continue
        d = 1 if t0.side == "L" else -1
        best = d * (mfe - t0.entry_price)
        if best / t0.entry_price < 0.10:
            continue
        q = sum(p.qty for p in parts)
        got = sum(p.qty * d * (p.exit_price - p.entry_price) for p in parts) / q
        ks.append(got / best)
    return dict(n=len(ks), median=statistics.median(ks) if ks else None)


def crit_a(x):
    b4, m4 = run_s4x(BTC, EB, x, T_2022, T_IS_END)
    ce = blend_exit_step(B3, b4, W, LEV, T_2022, T_IS_END)
    if ce[-1][0] < T_IS_END:
        ce.append((T_IS_END, ce[-1][1]))
    return dict(exit=curve_stats(ce), mtm=curve_stats(blend_mtm(M3, m4, W, LEV), bar_returns=True),
                halted=b4.halted, trades=trade_stats(b4), kept=kept(b4))


def crit_b(x):
    b, m = run_s4x(BTC, EB, x, T_2013, T_IS_END, cfg=NOHALT)
    return dict(mtm=curve_stats(m, bar_returns=True), trades=trade_stats(b), kept=kept(b),
                end_x=m[-1][1] / m[0][1])


def s4_alone(A, E, x):
    b, m = run_s4x(A, E, x, None, None, cfg=NOHALT)
    return dict(mtm=curve_stats(m, bar_returns=True), n=len({t.entry_ts for t in b.trades}),
                kept=kept(b))


def evaluate(x):
    return dict(name=x.name, family=family(x), spec=dataclasses.asdict(x),
                A=crit_a(x), B=crit_b(x),
                D={s: s4_alone(AS[s], EX[s], x) for s in INSAMPLE if s != "btc"},
                F=dict(mtm=curve_stats(run_s4x(BTC, EB, x, T_FWD, None)[1], bar_returns=True)))


def judge(r, base):
    da_e = mar(r["A"]["exit"]) - mar(base["A"]["exit"])
    da_m = mar(r["A"]["mtm"]) - mar(base["A"]["mtm"])
    a = da_e >= 0.10 * abs(mar(base["A"]["exit"])) and da_m >= 0.10 * abs(mar(base["A"]["mtm"]))
    b = mar(r["B"]["mtm"]) >= mar(base["B"]["mtm"])
    dd = {s: mar(r["D"][s]["mtm"]) - mar(base["D"][s]["mtm"]) for s in r["D"]}
    d = sum(v > 0 for v in dd.values()) >= 3 and statistics.mean(dd.values()) > 0
    return dict(dA_exit=da_e, dA_mtm=da_m, dB=mar(r["B"]["mtm"]) - mar(base["B"]["mtm"]),
                dD=dd, A=a, B=b, D=d, selected=a and b and d)


def main():
    what = sys.argv[1]
    t0 = time.time()
    n_samp, yrs = setup_models()
    print(f"V5 models: {len(yrs)} years {yrs[:1]}..{yrs[-1:]} from {n_samp} samples")
    if what == "sel":
        base = evaluate(BASE)
        rows = []
        for x in ALL:
            r = evaluate(x)
            r["judge"] = judge(r, base)
            rows.append(r)
            j = r["judge"]
            print(f"{x.name:28s} dA {j['dA_exit']:+.3f}/{j['dA_mtm']:+.3f} dB {j['dB']:+.3f} "
                  f"alts+ {sum(v > 0 for v in j['dD'].values())}/4 kept {r['B']['kept']['median'] or 0:.2f} "
                  f"A{int(j['A'])} B{int(j['B'])} D{int(j['D'])}{'  SELECTED' if j['selected'] else ''}")
        fin = sorted([r for r in rows if r["judge"]["selected"]], key=lambda r: -r["judge"]["dA_exit"])[:3]
        json.dump(dict(base=base, rows=rows, finalists=[r["name"] for r in fin]),
                  open(os.path.join(HERE, "results_sel.json"), "w"), default=float)
        print(f"base A {mar(base['A']['exit']):.3f}/{mar(base['A']['mtm']):.3f} B {mar(base['B']['mtm']):.3f} "
              f"kept {base['B']['kept']['median']:.2f} | finalists {[r['name'] for r in fin]} | {time.time() - t0:.0f}s")
        return
    if what == "holdout":
        sel = json.load(open(os.path.join(HERE, "results_sel.json")))
        fins = [x for x in ALL if x.name in sel["finalists"]]
        if not fins:
            print("no finalists: the holdout is not touched")
            return
        HO = {s: load_holdout(s) for s in HOLDOUT}
        HE = {s: extend(A) for s, A in HO.items()}
        base = {s: s4_alone(HO[s], HE[s], BASE) for s in HOLDOUT}
        out = []
        for x in fins:
            res = {s: s4_alone(HO[s], HE[s], x) for s in HOLDOUT}
            dd = {s: mar(res[s]["mtm"]) - mar(base[s]["mtm"]) for s in HOLDOUT}
            vals = list(dd.values())
            h = (sum(v > 0 for v in vals) >= 8 and statistics.mean(vals) > 0
                 and statistics.median(vals) > 0)
            out.append(dict(name=x.name, res=res, dH=dd, H=h))
            print(f"{x.name:28s} holdout better {sum(v > 0 for v in vals)}/12 mean {statistics.mean(vals):+.3f} "
                  f"median {statistics.median(vals):+.3f} H{int(h)}{'  ADOPT-ELIGIBLE' if h else ''}")
        json.dump(dict(base=base, rows=out), open(os.path.join(HERE, "results_holdout.json"), "w"),
                  default=float)
        return
    raise SystemExit(f"unknown command {what!r}")


if __name__ == "__main__":
    main()
