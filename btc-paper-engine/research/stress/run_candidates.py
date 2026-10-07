#!/usr/bin/env python3
"""Run the pre-registered candidate grid (CANDIDATES.md, 2026-10-07).

Configurations: baseline (the book as deployed), C1 (pullback fast vol
brake), C2 (pullback post-stop damper), C1+C2 - stress.Options switches;
production untouched.

  crash: COVID / 2008 / 1999 x offsets -28..28 x 4 configs, K 0.75, variant A,
         intrabar, carry (XBTUSD proxy) and BTC funding as in run_all.py;
  eras:  E2 2017-19, E3 2020-21, E4 2022-24H1, E5 2024H2-26 and 2019-01-01..
         2026-10-07 (through the seed's last closed bar), K 0.75 fixed base,
         paper books 100k/100k, real XBTUSD funding on the book's positions,
         carry flat 30k (the candidates do not touch the sleeve).

Writes candidates.json and fig_candidates.png next to this file, prints the
tables and the PREREG decision per candidate (crash maxDD no worse on every
offset-0 path and on the crash-path offset range, AND 2019+ fixed-base $/yr
>= 90% of the baseline's).

    python3 run_candidates.py            # full grid (~3 min)
    python3 run_candidates.py --charts   # chart + tables from candidates.json
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stress                                                   # noqa: E402
import run_all                                                  # noqa: E402
import carry_sleeve as cs                                       # noqa: E402
import harness                                                  # noqa: E402
from stress import BAR, DAY, Options, build_spliced, run_path, run_era, _date  # noqa: E402

NOW = stress.SEED_NOW
K = 0.75
OFFSETS = run_all.OFFSETS
CONFIGS = [("baseline", Options()),
           ("C1", Options(fast_brake=True)),
           ("C2", Options(post_stop_damper=True)),
           ("C1+C2", Options(fast_brake=True, post_stop_damper=True))]
ERAS = [("E2 2017-19", "2017-01-01", "2020-01-01"),
        ("E3 2020-21", "2020-01-01", "2022-01-01"),
        ("E4 2022-24H1", "2022-01-01", "2024-07-01"),
        ("E5 2024H2-26", "2024-07-01", "2026-08-01"),
        ("2019+ (2019-01-01..2026-10-07)", "2019-01-01", "2026-10-08")]
ERA_2019 = ERAS[-1][0]
YR_TOLERANCE = 0.10              # PREREG: <= 10% lower 2019+ fixed-base $/yr
RESULTS = os.path.join(HERE, "candidates.json")
FIG = os.path.join(HERE, "fig_candidates.png")

# Refuters' pass (2026-10-07, SERIOUS): recorded as text in candidates.json
# meta.honesty; the verdicts (DO NOT PROPOSE x3) stand and are strengthened.
# Full text: CANDIDATES.md "Post-run findings"; summary: ADDENDUM.md item 7.
REFUTER_HONESTY = [
    "Venue reachability: C1's floor 0.25 and any ENGINE-SIDE C2 cannot reach the venue as described - "
    "btc-executor clamps size_mult to [0.5, 1.0] (mirror.py SIZE_MULT_MIN / SIZE_MULT_MAX, L86; clamp at "
    "L1584-1588), so either needs an executor code change. With the clamp emulated (floor 0.5) the crash "
    "cells are COVID 116,537 / -20.92%, 2008 124,214 / -8.50%, 1999 119,158 / -13.28% (12m / maxDD) and "
    "2019+ 13,740 $/yr.",
    "C2 'executor-side' is not implementable: /exec/target carries no exit reason and the executor cannot "
    "see engine STOPs it did not hold; C2 can only live engine-side, where the clamp above applies.",
    "The registered 2019+ cost yardstick is trend-dominated: the S3 paper book (seeded 100k on 2019-01-01) "
    "halts on 2020-03-20 and drops 266 pullback trades, so 2019+ $/yr barely sees the leg the candidates act "
    "on. With the pullback leg alive (engine_halts=False) the 2019+ ratios are C1 91.6%, C2 88.9% (FAILS the "
    "90% test), C1+C2 81.7% (FAILS). Pooled active eras E3+E4+E5 (6.58 years, baseline 27,320 $/yr) against "
    "an exposure-matched uniform pullback cut as the control: C1 93.3% vs uniform 97.3%, C2 86.1% vs 94.9%, "
    "C1+C2 80.8% vs 92.4% - each candidate costs more than a plain cut of the same exposure.",
    "Exposure-matched control reproduces the crash gain: the baseline with the pullback weight scaled to the "
    "candidate's bar-weighted gross pullback exposure (C1 at offset 0: 0.749 COVID / 0.960 2008 / 0.624 "
    "1999) gives 12m uniform vs C1 119,846 vs 119,147 (COVID), 125,468 vs 124,214 (2008), 122,842 vs 123,092 "
    "(1999); maxDD -18.63% vs -18.62%, -8.09% vs -8.50%, -11.66% vs -11.23%. The candidates are a pullback "
    "size cut, not a logic improvement.",
    "+/-30% parameter sweep, 8 variants (C1 floor 0.175 / 0.325, reference window 1,533 / 2,847 bars; C2 "
    "window 3.5 / 6.5 days, multipliers 0.35/0.175 and 0.65/0.325): DO NOT PROPOSE for every variant; C2's "
    "window parameter is inert (3.5 d and 6.5 d reproduce the registered 5 d crash cells).",
    "2019+ C1 decomposition corrected, net of fees and funding: 18 resized pullback entries, -6,917 forgone "
    "on 15 winners / +2,407 saved on 3 stops (gross -7,066 / +2,372); the earlier -5.6k / +2.2k mixed bases.",
    "C1 text corrected: the pullback STOP is built from the FILL bar's ATR14, not the signal bar's; C1 reads "
    "the signal bar's ATR14/close, one bar earlier than the stop it is meant to scale.",
    "Post-stop re-entry outcome by gap (2017-26 engine pullback trades): re-entries within 1 day won 60% (37 "
    "of 62); 5-7 days after the stop 100% (7 of 7). C2 damps the within-1-day group hardest.",
    "Offsets worse / better than the baseline are counted over all five start offsets next to each range-worst "
    "(decision[*].crash[*].offsets_worse_better; e.g. C1 on 2008: close maxDD worse on 4/5, intrabar 5/5, 12m "
    "5/5 although its range-worst improves): a range-worst is set by one offset and is not a summary of the path.",
]


def okey(off: int) -> str:
    return run_all.okey(off)


def summ(r: dict) -> dict:
    eh = r["engine_halts_info"]
    pb = [t for t in r["trades"] if t["leg"] == "pullback"]
    tr = [t for t in r["trades"] if t["leg"] == "trend"]
    return dict(
        tag=r["options"]["tag"], balances={k: (v["equity"] if v else None) for k, v in r["balances"].items()},
        balance_365_exact=r["balances"]["365"]["exact"], final_equity=r["final_equity"],
        final_btc=r["equity_btc"][-1], years=r["years"],
        usd_per_year=round((r["equity_btc"][-1] - (stress.START_EQUITY - stress.CARRY_START)) / r["years"], 2),
        max_dd=r["max_dd"], max_dd_intrabar=r["max_dd_intrabar"], max_dd_btc_book=r["max_dd_btc_book"],
        worst_day_usd=round(r["worst_day"]["usd"], 2), worst_day_intrabar_usd=round(r["worst_day_intrabar"]["usd"], 2),
        rail_daily_used=r["rail_use"]["daily_loss"]["used_pct"], rail_dd_used=r["rail_use"]["drawdown"]["used_pct"],
        halts=[dict(kind=h["kind"], date=h["date"], equity=h["equity_after"]) for h in r["halts"]],
        halts_count=len(r["halts"]),
        engine_halts={leg: (eh[leg]["halt_date"] if eh[leg]["halted"] else None) for leg in stress.LEGS},
        n_trades=r["n_trades"], n_open=r["n_open"], fees=r["fees"], btc_funding=r["btc_funding_total"],
        brake_counts=r["brake_counts"], realised_by_leg=r["realised_by_leg"],
        pullback_mtm_end=r["leg_mtm"]["pullback"][-1], trend_mtm_end=r["leg_mtm"]["trend"][-1],
        pullback_stop_pnl=round(sum(t["pnl"] for t in pb if t["reason"] == "STOP"), 2),
        pullback_n_stops=sum(1 for t in pb if t["reason"] == "STOP"),
        pullback_gross_notional=round(sum(t["notional"] for t in pb), 2),
        trend_n=len(tr), file=(os.path.relpath(r["file"], HERE) if r.get("file") else None))


def run_crash_grid(res: dict) -> None:
    for scen, anchor in run_all.SCENARIOS:
        S = dict(label=run_all.SCEN_LABEL[scen], anchor=anchor, runs={}, curves={}, paths={})
        res["crash"][scen] = S
        for off in OFFSETS:
            bb = build_spliced("btcusd", anchor, run_all.MONTHS, off, now=NOW)
            be = build_spliced("ethusd", anchor, run_all.MONTHS, off, now=NOW)
            fund, fmeta = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, run_all.HEADLINE_FUNDING)
            bf = run_all.btc_funding_from(fund)
            cr = run_all.run_carry(be, fund)
            S["paths"][okey(off)] = dict(btc=run_all.path_moves(bb), funding=fmeta)
            for name, opt in CONFIGS:
                r = run_path(scen, bb, K, carry_value=cr.value, btc_funding=bf, save=True, options=opt,
                             extra=dict(offset_days=off, anchor_input=scen, anchor_date_input=anchor,
                                        months=run_all.MONTHS, carry_funding_source=fmeta["source"]))
                s = summ(r)
                S["runs"].setdefault(name, {})[okey(off)] = s
                print(f"  {scen:5s} {okey(off):6s} {name:8s} 12m {s['balances']['365']:>9,.0f}  maxDD {s['max_dd']:7.2%}  "
                      f"halts {s['halts_count']}  eng {s['engine_halts']['pullback'] or '-':16s}  trades {s['n_trades']:3d}  "
                      f"brake {s['brake_counts']}  pb stops {s['pullback_stop_pnl']:+9,.0f}", flush=True)
                if off == 0:
                    S["curves"][name] = dict(ts=r["ts"], total=r["equity_total"],
                                             dd=run_all.dd_curve(stress.START_EQUITY, r["equity_total"]))
        # crash-path offset rule as in run_all (half the offset-0 low)
        low0 = S["paths"]["off+0"]["btc"]["low_pct"]
        for o in OFFSETS:
            S["paths"][okey(o)]["crash_path"] = S["paths"][okey(o)]["btc"]["low_pct"] <= run_all.CRASH_DEPTH_FRAC * low0
        crash_offs = [okey(o) for o in OFFSETS if S["paths"][okey(o)]["crash_path"]]
        S["crash_offsets"] = crash_offs
        S["range"] = {}
        for name, _ in CONFIGS:
            dd = {k: S["runs"][name][k]["max_dd"] for k in crash_offs}
            b12 = {k: S["runs"][name][k]["balances"]["365"] for k in crash_offs}
            S["range"][name] = dict(max_dd_worst=min(dd.values()), max_dd_best=max(dd.values()),
                                    max_dd_mean=round(float(np.mean(list(dd.values()))), 4),
                                    b12_min=min(b12.values()), b12_max=max(b12.values()),
                                    b12_mean=round(float(np.mean(list(b12.values()))), 2))


SENS_SCEN = ("COVID", "1999")      # the two paths whose S3 paper book halts


def run_sensitivity(res: dict) -> None:
    """Offset 0 WITHOUT the engine's paper-book halts: does a candidate's
    crash gain depend on the S3 halt (a 0.9%-of-peak knife-edge in COVID,
    the open P1 seam input)? The real 2020-21 era, where S3 never halted,
    says the brakes cost there."""
    res["sensitivity"] = {"no_engine_book_halts": {}}
    for scen, anchor in run_all.SCENARIOS:
        if scen not in SENS_SCEN:
            continue
        bb = build_spliced("btcusd", anchor, run_all.MONTHS, 0, now=NOW)
        be = build_spliced("ethusd", anchor, run_all.MONTHS, 0, now=NOW)
        fund, fmeta = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, run_all.HEADLINE_FUNDING)
        bf = run_all.btc_funding_from(fund)
        cr = run_all.run_carry(be, fund)
        out = {}
        for name, opt in CONFIGS:
            r = run_path(scen, bb, K, carry_value=cr.value, btc_funding=bf, save=True, options=opt,
                         engine_halts=False,
                         extra=dict(offset_days=0, anchor_input=scen, anchor_date_input=anchor,
                                    months=run_all.MONTHS, carry_funding_source=fmeta["source"]))
            out[name] = summ(r)
            print(f"  {scen:5s} off+0 no-engine-halts {name:8s} 12m {out[name]['balances']['365']:>9,.0f}  "
                  f"maxDD {out[name]['max_dd']:7.2%}  pb stops {out[name]['pullback_stop_pnl']:+9,.0f}  "
                  f"brake {out[name]['brake_counts']}", flush=True)
        res["sensitivity"]["no_engine_book_halts"][scen] = out


def real_funding(start_date: str, end_date: str) -> dict[int, float]:
    lo = (harness.ts_of(start_date) - DAY) * 1000
    hi = harness.ts_of(end_date) * 1000
    return run_all.btc_funding_from(cs.load_funding(run_all.FUNDING_FILES["XBTUSD"], lo_ms=lo, hi_ms=hi))


def run_eras(res: dict) -> None:
    for name, start, end in ERAS:
        bf = real_funding(start, end)
        E = dict(start=start, end=end, runs={}, n_funding_stamps=len(bf))
        res["eras"][name] = E
        for cname, opt in CONFIGS:
            r = run_era(name.split(" ")[0] if name[0] == "E" else "Y2019plus", start, end, K,
                        carry_value=None, btc_funding=bf, save=True, options=opt, now=NOW)
            s = summ(r)
            E["runs"][cname] = s
            E["n_path_bars"] = r["n_path_bars"]
            print(f"  {name:32s} {cname:8s} $/yr {s['usd_per_year']:>9,.0f}  final BTC book {s['final_btc']:>10,.0f}  "
                  f"maxDD acct {s['max_dd']:7.2%} / BTC book {s['max_dd_btc_book']:7.2%}  halts {s['halts_count']}  "
                  f"eng S3 {s['engine_halts']['pullback'] or '-':16s} S4 {s['engine_halts']['trend'] or '-':16s}  "
                  f"trades {s['n_trades']:4d}  brake {s['brake_counts']}", flush=True)


def decide(res: dict) -> dict:
    base_yr = res["eras"][ERA_2019]["runs"]["baseline"]["usd_per_year"]
    out = {}
    for name, _ in CONFIGS[1:]:
        yr = res["eras"][ERA_2019]["runs"][name]["usd_per_year"]
        yr_ratio = yr / base_yr if base_yr else float("nan")
        crash = {}
        all_ok, any_better = True, False
        for scen, _ in run_all.SCENARIOS:
            S = res["crash"][scen]
            b0, c0 = S["runs"]["baseline"]["off+0"]["max_dd"], S["runs"][name]["off+0"]["max_dd"]
            br, crr = S["range"]["baseline"]["max_dd_worst"], S["range"][name]["max_dd_worst"]
            ok0 = c0 >= b0 - 1e-9
            okr = crr >= br - 1e-9
            # offsets on which the candidate is worse / better than the baseline (all five
            # start offsets; the range itself uses the crash-path offsets) - refuters' point 9
            offs = [okey(o) for o in OFFSETS]

            def _cnt(get):
                w = sum(get(S["runs"][name][k]) < get(S["runs"]["baseline"][k]) for k in offs)
                bt = sum(get(S["runs"][name][k]) > get(S["runs"]["baseline"][k]) for k in offs)
                return dict(worse=int(w), better=int(bt), of=len(offs))
            counts = dict(max_dd=_cnt(lambda r: r["max_dd"]),
                          max_dd_intrabar=_cnt(lambda r: r["max_dd_intrabar"]),
                          b12=_cnt(lambda r: r["balances"]["365"]))
            crash[scen] = dict(max_dd_base=b0, max_dd_cand=c0, d_max_dd=round(c0 - b0, 4), offset0_ok=ok0,
                               range_worst_base=br, range_worst_cand=crr, range_ok=okr,
                               offsets_worse_better=counts,
                               b12_base=S["runs"]["baseline"]["off+0"]["balances"]["365"],
                               b12_cand=S["runs"][name]["off+0"]["balances"]["365"])
            all_ok &= ok0 and okr
            any_better |= (c0 > b0 + 1e-9) or (crr > br + 1e-9)
        yr_ok = yr_ratio >= 1.0 - YR_TOLERANCE
        verdict = "PROPOSE" if (all_ok and any_better and yr_ok) else "DO NOT PROPOSE"
        why = []
        if not all_ok:
            why.append("crash maxDD worse on " + ", ".join(s for s, c in crash.items() if not (c["offset0_ok"] and c["range_ok"])))
        if not any_better:
            why.append("crash maxDD not improved anywhere")
        if not yr_ok:
            why.append(f"2019+ $/yr {yr:,.0f} vs {base_yr:,.0f} = {yr_ratio:.1%} (< 90%)")
        out[name] = dict(verdict=verdict, why="; ".join(why) if why else "crash maxDD no worse anywhere, improved, and 2019+ $/yr within 10%",
                         usd_per_year_2019=yr, usd_per_year_2019_base=base_yr, yr_ratio=round(yr_ratio, 4),
                         crash=crash, crash_ok=all_ok, crash_improved=any_better, yr_ok=yr_ok)
    return out


def _wb(c: dict, key: str) -> str:
    """'4/5 worse, 1/5 better' for a decision crash record (n/a on old files)."""
    k = c.get("offsets_worse_better", {}).get(key)
    return "n/a" if not k else f"{k['worse']}/{k['of']} worse, {k['better']}/{k['of']} better"


# --------------------------------------------------------------------------
def table_lines(res: dict) -> list[str]:
    L = []
    L.append("CRASH (K 0.75, variant A, intrabar, carry XBTUSD proxy, BTC funding; offset 0 | crash-path offset range)")
    hdr = (f"{'scenario':<15}|{'config':<9}|{'3m':>8} |{'6m':>8} |{'9m':>8} |{'12m*':>8} |{'maxDD':>7} |{'range maxDD worst':>17} |"
           f"{'range 12m min..max':>19} |{'pb stops $':>10} |{'halts':>5} |{'S3 halt':>11} |{'trades':>6} |{'brake':>14}")
    L.append(hdr)
    L.append("-" * len(hdr))
    for scen, _ in run_all.SCENARIOS:
        S = res["crash"][scen]
        for name, _ in CONFIGS:
            s = S["runs"][name]["off+0"]
            rg = S["range"][name]
            b = s["balances"]
            star = "" if s["balance_365_exact"] else "*"
            bc = s["brake_counts"]
            L.append(f"{S['label']:<15}|{name:<9}|{b['91']:>8,.0f} |{b['182']:>8,.0f} |{b['273']:>8,.0f} |{b['365']:>7,.0f}{star:1s} |"
                     f"{s['max_dd']:>7.1%} |{rg['max_dd_worst']:>17.1%} |{rg['b12_min']:>9,.0f}..{rg['b12_max']:<8,.0f} |"
                     f"{s['pullback_stop_pnl']:>+10,.0f} |{s['halts_count']:>5d} |{(s['engine_halts']['pullback'] or 'none')[5:16]:>11} |"
                     f"{s['n_trades']:>6d} |{'fast ' + str(bc['fast_binding']) + ' damp ' + str(bc['damped']):>14}")
        L.append(f"  crash-path offsets: {', '.join(S['crash_offsets'])}")
    L.append("")
    L.append("NORMAL ERAS (K 0.75 fixed base 100k, no splice, real XBTUSD funding on the book, carry flat 30k; $/yr on the BTC book from 70k)")
    hdr = (f"{'era':<32}|{'config':<9}|{'$/yr':>9} |{'vs base':>8} |{'maxDD acct':>10} |{'maxDD BTC':>10} |{'halts':>5} |"
           f"{'S3 halt':>11} |{'S4 halt':>11} |{'trades':>6} |{'pb stops $':>11} |{'brake':>16}")
    L.append(hdr)
    L.append("-" * len(hdr))
    for name, _, _ in ERAS:
        E = res["eras"][name]
        base = E["runs"]["baseline"]["usd_per_year"]
        for cname, _ in CONFIGS:
            s = E["runs"][cname]
            bc = s["brake_counts"]
            L.append(f"{name:<32}|{cname:<9}|{s['usd_per_year']:>9,.0f} |{(s['usd_per_year'] / base - 1) if base else 0:>+8.1%} |"
                     f"{s['max_dd']:>10.1%} |{s['max_dd_btc_book']:>10.1%} |{s['halts_count']:>5d} |"
                     f"{(s['engine_halts']['pullback'] or 'none')[:11]:>11} |{(s['engine_halts']['trend'] or 'none')[:11]:>11} |"
                     f"{s['n_trades']:>6d} |{s['pullback_stop_pnl']:>+11,.0f} |{'fast ' + str(bc['fast_binding']) + ' damp ' + str(bc['damped']):>16}")
    L.append("")
    L.append("SENSITIVITY: offset 0 WITHOUT the engine paper-book halts (12m | maxDD) - does the gain depend on the S3 halt?")
    for scen in SENS_SCEN:
        sens = res["sensitivity"]["no_engine_book_halts"][scen]
        L.append(f"  {run_all.SCEN_LABEL[scen]:<15} " + "   ".join(
            f"{n}: {sens[n]['balances']['365']:,.0f} | {sens[n]['max_dd']:.1%}" for n, _ in CONFIGS)
            + "   (with halts: " + "   ".join(f"{n}: {res['crash'][scen]['runs'][n]['off+0']['balances']['365']:,.0f} | "
                                               f"{res['crash'][scen]['runs'][n]['off+0']['max_dd']:.1%}" for n, _ in CONFIGS) + ")")
    L.append("")
    L.append("DECISION (PREREG: propose only if crash maxDD no worse on every offset-0 path and on the crash-path range, improved somewhere, and 2019+ $/yr >= 90% of baseline)")
    for name, d in res["decision"].items():
        L.append(f"  {name:6s} {d['verdict']:15s} 2019+ $/yr {d['usd_per_year_2019']:,.0f} vs {d['usd_per_year_2019_base']:,.0f} ({d['yr_ratio']:.1%}); "
                 + "; ".join(f"{s} maxDD {c['max_dd_base']:.1%}->{c['max_dd_cand']:.1%} (range worst {c['range_worst_base']:.1%}->{c['range_worst_cand']:.1%}; "
                             f"vs baseline by offset: close maxDD {_wb(c, 'max_dd')}, intrabar {_wb(c, 'max_dd_intrabar')}, 12m {_wb(c, 'b12')}), "
                             f"12m {c['b12_base']:,.0f}->{c['b12_cand']:,.0f}" for s, c in d["crash"].items())
                 + f"  | {d['why']}")
    return L


# --------------------------------------------------------------------------
C_CFG = {"baseline": run_all.C_K75, "C1": run_all.C_CARRY, "C2": run_all.C_HOLD, "C1+C2": run_all.C_K30}
INK, INK2, GRID, SURF = run_all.INK, run_all.INK2, run_all.GRID, run_all.SURF


def chart(res: dict) -> str:
    plt, mdates, FuncFormatter, FixedLocator, NullLocator, PercentFormatter = run_all._mpl()
    usd = run_all.usd
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.4))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.81, bottom=0.07, hspace=0.54, wspace=0.24)
    names = [n for n, _ in CONFIGS]
    scen_labels = [run_all.SCEN_LABEL[s] for s, _ in run_all.SCENARIOS]
    fig.suptitle("Guard-logic candidates on the crash paths and the normal eras (K 0.75, fixed base)",
                 x=0.07, ha="left", fontsize=13.5, fontweight="semibold", color=INK, y=0.975)
    fig.text(0.07, 0.94, "C1 = pullback fast vol brake (ATR14/close vs its 1-year median, floor 0.25)   "
             "C2 = pullback post-stop damper (x0.5 / x0.25 within 5 days of a stop-out)   both on the pullback leg only",
             fontsize=9.2, color=INK2, ha="left")
    d = res["decision"]
    fig.text(0.07, 0.92, "Verdicts: " + "   ".join(f"{n}: {d[n]['verdict']} (2019+ $/yr {d[n]['yr_ratio']:.0%} of baseline)" for n in names[1:]),
             fontsize=9.2, color=INK2, ha="left")
    fig.text(0.07, 0.90, "Exposure-matched control: a uniform pullback size cut to C1's exposure (x0.749 / 0.960 / 0.624 on "
             "COVID / 2008 / 1999, offset 0) reproduces the crash gain - a size cut, not a logic improvement.",
             fontsize=9.2, color=INK2, ha="left")
    fig.text(0.07, 0.88, "Candidates chosen after seeing these three paths (in-sample selection); fills at the line, no slippage: upper bounds.",
             fontsize=9.2, color=INK2, ha="left")
    w = 0.19
    xpos = np.arange(len(scen_labels))
    # (1) crash maxDD, offset 0, with the crash-path offset range as a whisker
    ax = axes[0, 0]
    for i, n in enumerate(names):
        xs = xpos + (i - 1.5) * (w + 0.02)
        v0 = [res["crash"][s]["runs"][n]["off+0"]["max_dd"] * 100 for s, _ in run_all.SCENARIOS]
        lo = [res["crash"][s]["range"][n]["max_dd_worst"] * 100 for s, _ in run_all.SCENARIOS]
        hi = [res["crash"][s]["range"][n]["max_dd_best"] * 100 for s, _ in run_all.SCENARIOS]
        ax.bar(xs, v0, width=w, color=C_CFG[n], label=n, zorder=3)
        ax.vlines(xs + 0.4 * w, lo, hi, color=INK2, lw=1.0, zorder=4)
        for xx, v in zip(xs, v0):
            ax.text(xx - 0.12 * w, v - 0.4, f"{v:.1f}%", ha="center", va="top", fontsize=7.5, color=INK2, rotation=90)
    ax.set_xticks(xpos)
    ax.set_xticklabels(scen_labels)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_ylim(min(res["crash"][s]["range"][n]["max_dd_worst"] for s, _ in run_all.SCENARIOS for n in names) * 100 * 1.25, 0)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=0)
    ax.set_title("Crash max drawdown (offset 0; whisker = crash-path offset range)", loc="left", fontsize=10.5, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4, labelcolor=INK2, fontsize=8.5, borderaxespad=0.0)
    # (2) 12m balance, offset 0, whisker = crash-path offset range
    ax = axes[0, 1]
    for i, n in enumerate(names):
        xs = xpos + (i - 1.5) * (w + 0.02)
        v0 = [res["crash"][s]["runs"][n]["off+0"]["balances"]["365"] for s, _ in run_all.SCENARIOS]
        lo = [res["crash"][s]["range"][n]["b12_min"] for s, _ in run_all.SCENARIOS]
        hi = [res["crash"][s]["range"][n]["b12_max"] for s, _ in run_all.SCENARIOS]
        ax.bar(xs, v0, width=w, color=C_CFG[n], label=n, zorder=3)
        ax.vlines(xs + 0.4 * w, lo, hi, color=INK2, lw=1.0, zorder=4)
        for xx, v in zip(xs, v0):
            ax.text(xx - 0.12 * w, v - 1500, usd(v), ha="center", va="top", fontsize=7.5, color=SURF, rotation=90)
    ax.axhline(stress.START_EQUITY, color=run_all.C_CASH, lw=1.0, ls=(0, (1.5, 2.5)), zorder=2, label="start " + r"\$100k")
    ax.set_xticks(xpos)
    ax.set_xticklabels(scen_labels)
    ax.yaxis.set_major_formatter(FuncFormatter(usd))
    allv = [res["crash"][s]["range"][n][k] for s, _ in run_all.SCENARIOS for n in names for k in ("b12_min", "b12_max")]
    ax.set_ylim(min(allv) * 0.9, max(allv) * 1.06)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=0)
    ax.set_title("Balance after 12 months (offset 0; whisker = crash-path offset range)", loc="left", fontsize=10.5, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=5, labelcolor=INK2, fontsize=8.5, borderaxespad=0.0)
    # (3) fixed-base $/yr by era, with the -10% line on 2019+
    ax = axes[1, 0]
    era_names = [n for n, _, _ in ERAS]
    short = ["E2 17-19", "E3 20-21", "E4 22-24H1", "E5 24H2-26", "2019+"]
    xe = np.arange(len(era_names))
    for i, n in enumerate(names):
        xs = xe + (i - 1.5) * (w + 0.02)
        v = [res["eras"][e]["runs"][n]["usd_per_year"] for e in era_names]
        ax.bar(xs, v, width=w, color=C_CFG[n], label=n, zorder=3)
        for xx, vv in zip(xs, v):
            ax.text(xx, vv + (300 if vv >= 0 else -300), usd(vv), ha="center", va="bottom" if vv >= 0 else "top",
                    fontsize=7, color=INK2, rotation=90)
    b19 = res["eras"][ERA_2019]["runs"]["baseline"]["usd_per_year"]
    ax.hlines(b19 * (1 - YR_TOLERANCE), xe[-1] - 0.45, xe[-1] + 0.45, color=INK, lw=1.2, ls=(0, (3, 2)), zorder=5)
    ax.text(xe[-1] + 0.47, b19 * (1 - YR_TOLERANCE), "-10% line\n(PREREG)", fontsize=7.5, color=INK, va="center", ha="left")
    ax.axhline(0, color=GRID, lw=0.8)
    ax.set_xticks(xe)
    ax.set_xticklabels(short)
    ax.yaxis.set_major_formatter(FuncFormatter(usd))
    vals = [res["eras"][e]["runs"][n]["usd_per_year"] for e in era_names for n in names]
    ax.set_ylim(min(0, min(vals)) * 1.3 - 2000, max(vals) * 1.3)
    ax.set_xlim(-0.6, len(era_names) - 0.2)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=0)
    ax.set_title("Normal eras: fixed-base \\$/yr of the BTC book (the cost of the brake)", loc="left", fontsize=10.5, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4, labelcolor=INK2, fontsize=8.5, borderaxespad=0.0)
    # (4) COVID offset-0 equity curves, baseline vs candidates
    ax = axes[1, 1]
    cv = res["crash"]["COVID"]["curves"]
    x = run_all._dates(cv["baseline"]["ts"])
    for n in names:
        ax.plot(x, cv[n]["total"], color=C_CFG[n], lw=2.2 if n == "baseline" else 1.6,
                ls="-" if n in ("baseline", "C1+C2") else (0, (5, 3)), label=n, zorder=5 if n == "baseline" else 4)
    ax.axhline(stress.START_EQUITY, color=run_all.C_CASH, lw=1.0, ls=(0, (1.5, 2.5)), zorder=2)
    run_all._style_axes(ax, mdates)
    ax.yaxis.set_major_formatter(FuncFormatter(usd))
    ax.set_title("COVID-like path, offset 0: account equity by configuration", loc="left", fontsize=10.5, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4, labelcolor=INK2, fontsize=8.5, borderaxespad=0.0)
    ax.set_xlim(x[0], x[-1] + 0.14 * (x[-1] - x[0]))
    run_all._end_labels(ax, [(x, cv[n]["total"], n, C_CFG[n]) for n in names], log=False, min_gap_frac=0.06)
    fig.savefig(FIG, dpi=150)
    plt.close(fig)
    return FIG


def main() -> None:
    if "--charts" in sys.argv:
        with open(RESULTS) as fh:
            res = json.load(fh)
    else:
        t0 = time.time()
        res = dict(meta=dict(generated=_date(time.time()), now_used=NOW, K=K, offsets=list(OFFSETS),
                             configs=[n for n, _ in CONFIGS], eras=ERAS, yr_tolerance=YR_TOLERANCE,
                             constants=dict(FAST_BRAKE_FLOOR=stress.FAST_BRAKE_FLOOR,
                                            FAST_BRAKE_REF_BARS=stress.FAST_BRAKE_REF_BARS,
                                            DAMP_DAYS=stress.DAMP_DAYS, DAMP_MULTS=list(stress.DAMP_MULTS)),
                             honesty=[
                                 "Candidates were chosen AFTER seeing the three baseline crash paths (PREREG's own rule); their "
                                 "parameters were fixed from the pullback leg's statistics on 2017-26 real history, not from the "
                                 "outcomes - but that history contains the analogue windows. In-sample selection on three paths.",
                                 "Crash runs: the headline set-up of results.json (variant A, intrabar, XBTUSD-proxy carry, BTC "
                                 "funding); eras: no splice, real XBTUSD funding, carry flat 30k, paper books 100k/100k. Fills at the "
                                 "line / the engine level, no slippage: upper bounds. The engine's trade lists and paper-book halts are "
                                 "identical across configurations (the candidates change entry SIZE only).",
                                 "2019+ fixed-base $/yr = (BTC-book equity at the end - 70,000) / years, open positions marked; the "
                                 "trend leg is in-sample on 2019-21 (fit window 2013-21), the pullback on 2024-26."]
                                 + REFUTER_HONESTY),
                   crash={}, eras={}, decision={})
        print("crash grid")
        run_crash_grid(res)
        print("sensitivity: no engine-book halts")
        run_sensitivity(res)
        print("eras")
        run_eras(res)
        res["decision"] = decide(res)
        res["meta"]["elapsed_s"] = round(time.time() - t0, 1)
        res["table"] = table_lines(res)
        with open(RESULTS, "w") as fh:
            json.dump(res, fh)
        print(f"saved {RESULTS} ({os.path.getsize(RESULTS) / 1e6:.1f} MB) in {res['meta']['elapsed_s']} s")
    print("\n".join(table_lines(res)))
    print("chart:", chart(res))


if __name__ == "__main__":
    main()
