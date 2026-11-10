#!/usr/bin/env python3
"""Attribute the baseline damage (K 0.75, offset 0, headline funding) to
mechanisms with dollars - ATTRIBUTION.md is written from this output.

For each scenario the headline run is re-run (stress.run_path, options off;
it reproduces results.json to the cent) with the per-bar per-leg MTM the
harness now records, plus the no-engine-book-halt counterfactual, and the
12-month P&L and the max drawdown window are decomposed into:

  (a) pullback leg: realised before / after the S3 paper-book halt (by side
      and exit reason), the seam re-mirror, and the halt's forgone P&L
      (no-halt counterfactual, pullback MTM only);
  (b) trend leg: winners vs stop-out losers, crash phase (entered before the
      BTC low) vs after, the trail give-back of the crash short, longest
      losing streak and the trade that followed it, open MTM at the end;
  (c) daily-loss halts: count, cost, re-entry cost (none fired: rail use);
  (d) drawdown halt: count (none fired: rail use);
  (e) carry sleeve: value change, funding, fees, flips, worst dip;
  (f) fees and BTC perp funding by leg.

    python3 attribution.py            # prints the tables, writes attribution.json
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
from stress import BAR, DAY, build_spliced, run_path, _date      # noqa: E402

NOW = stress.SEED_NOW
K = 0.75
OUT = os.path.join(HERE, "attribution.json")


def _d(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))


def run_headline(scen: str, anchor: str, engine_halts: bool = True) -> tuple[dict, object, dict]:
    bb = build_spliced("btcusd", anchor, run_all.MONTHS, 0, now=NOW)
    be = build_spliced("ethusd", anchor, run_all.MONTHS, 0, now=NOW)
    fund, fmeta = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, run_all.HEADLINE_FUNDING)
    cr = run_all.run_carry(be, fund)
    r = run_path(scen, bb, K, carry_value=cr.value, btc_funding=run_all.btc_funding_from(fund),
                 engine_halts=engine_halts, save=False,
                 extra=dict(offset_days=0, carry_funding_source=fmeta["source"]))
    return r, cr, fmeta


def trade_groups(trades: list[dict], leg: str, halt_ts: int | None) -> dict:
    """Realised P&L of `leg` grouped by (before/after halt) x side x reason."""
    g = {}
    for t in trades:
        if t["leg"] != leg:
            continue
        phase = "after_halt" if (halt_ts is not None and t["entry_ts"] > halt_ts) else "before_halt"
        key = (phase, t["kind"], t["side"], t["reason"])
        g.setdefault(key, dict(n=0, pnl=0.0, gross=0.0, fees=0.0, funding=0.0))
        e = g[key]
        e["n"] += 1
        e["pnl"] += t["pnl"]
        e["gross"] += t["gross"]
        e["fees"] += t["fees"]
        e["funding"] += t["funding"]
    return {"|".join(k): {kk: round(v, 2) if isinstance(v, float) else v for kk, v in e.items()}
            for k, e in g.items()}


def trend_detail(r: dict, low_ts: int) -> dict:
    """Trend leg: winners/losers, crash phase vs after, give-back, streaks."""
    tr = [t for t in r["trades"] if t["leg"] == "trend"]
    closed = [t for t in tr if t["reason"] != "OPEN"]
    open_ = [t for t in tr if t["reason"] == "OPEN"]
    win = [t for t in closed if t["pnl"] > 0]
    lose = [t for t in closed if t["pnl"] <= 0]
    crash = [t for t in closed if t["entry_ts"] <= low_ts]
    after = [t for t in closed if t["entry_ts"] > low_ts]
    stop_losers = [t for t in lose if t["reason"] == "STOP"]
    # longest losing streak (closed trades in exit order) and what followed it
    seq = sorted(closed, key=lambda t: t["exit_ts"])
    best, cur = [], []
    for t in seq:
        if t["pnl"] <= 0:
            cur.append(t)
            if len(cur) > len(best):
                best = list(cur)
        else:
            cur = []
    nxt = None
    if best:
        j = seq.index(best[-1])
        nxt = seq[j + 1] if j + 1 < len(seq) else None
    # trail give-back of the crash short: MTM peak of the trade vs its realised gross
    give = None
    ts = np.asarray(r["ts"])
    closes = np.asarray([c for _, c in r["spliced_closes"]])
    shorts = [t for t in crash if t["side"] == "S" and t["pnl"] > 0]
    if shorts:
        t = max(shorts, key=lambda t: t["pnl"])
        sel = (ts >= t["entry_ts"]) & (ts < t["exit_ts"])
        mtm = t["qty"] * (t["entry_px"] - closes[sel])
        jbest = int(np.argmax(mtm))
        give = dict(entry_date=t["entry_date"], exit_date=t["exit_date"], realised_gross=t["gross"],
                    mtm_peak=round(float(mtm[jbest]), 2), mtm_peak_date=_d(ts[sel][jbest]),
                    give_back=round(float(mtm[jbest]) - t["gross"], 2))
    sm = lambda L: round(sum(t["pnl"] for t in L), 2)  # noqa: E731
    return dict(n_closed=len(closed), n_open=len(open_), open_mtm=sm(open_),
                winners=dict(n=len(win), pnl=sm(win)), losers=dict(n=len(lose), pnl=sm(lose)),
                stop_losers=dict(n=len(stop_losers), pnl=sm(stop_losers)),
                crash_phase=dict(n=len(crash), pnl=sm(crash), to=_d(low_ts)),
                after_low=dict(n=len(after), pnl=sm(after)),
                longest_losing_streak=dict(n=len(best), pnl=sm(best),
                                           from_date=best[0]["entry_date"] if best else None,
                                           to_date=best[-1]["exit_date"] if best else None,
                                           followed_by=(dict(entry_date=nxt["entry_date"], pnl=nxt["pnl"],
                                                             side=nxt["side"]) if nxt else None)),
                crash_short_give_back=give,
                top3=[dict(side=t["side"], entry_date=t["entry_date"], exit_date=t["exit_date"],
                           pnl=t["pnl"], mult=t["size_mult"])
                      for t in sorted(tr, key=lambda t: -t["pnl"])[:3]])


def dd_window(r: dict, cr) -> dict:
    """Peak -> trough of the max MTM drawdown and what moved in between."""
    eq = np.asarray(r["equity_total"])
    ts = np.asarray(r["ts"])
    path = np.concatenate([[stress.START_EQUITY], eq])
    peak = np.maximum.accumulate(path)
    dd = path / peak - 1.0
    jt = int(np.argmin(dd))                      # index into path (0 = start)
    jp = int(np.argmax(path[:jt + 1]))
    def at(j, arr, start):                       # value at path index j
        return start if j == 0 else float(arr[j - 1])
    pb = r["leg_mtm"]["pullback"]
    tr = r["leg_mtm"]["trend"]
    cv = r["carry_value"]
    fc = r["btc_funding_cum"]
    d_pb = at(jt, pb, 0.0) - at(jp, pb, 0.0)
    d_tr = at(jt, tr, 0.0) - at(jp, tr, 0.0)
    d_cv = at(jt, cv, stress.CARRY_START) - at(jp, cv, stress.CARRY_START)
    d_fund = at(jt, fc, 0.0) - at(jp, fc, 0.0)
    t_lo = ts[jp - 1] if jp > 0 else r["t0"] - 1
    t_hi = ts[jt - 1] if jt > 0 else r["t0"] - 1
    fees_in = sum(t["fees"] for t in r["trades"] if t["reason"] != "OPEN"
                  and t_lo < t["exit_ts"] <= t_hi)
    # per-leg realised trades closed inside the window (for the narrative)
    inside = [t for t in r["trades"] if t["reason"] != "OPEN" and t_lo < t["exit_ts"] <= t_hi]
    by_leg = {}
    for t in inside:
        e = by_leg.setdefault(t["leg"], dict(n=0, pnl=0.0, winners=0, losers=0))
        e["n"] += 1
        e["pnl"] += t["pnl"]
        e["winners" if t["pnl"] > 0 else "losers"] += 1
    return dict(max_dd=round(float(dd[jt]), 4), peak_equity=round(float(path[jp]), 2),
                peak_date=_date(t_lo + 1) if jp > 0 else "start", trough_equity=round(float(path[jt]), 2),
                trough_date=_date(ts[jt - 1]), fall=round(float(path[jt] - path[jp]), 2),
                d_pullback=round(d_pb, 2), d_trend=round(d_tr, 2), d_carry=round(d_cv, 2),
                of_which_btc_funding=round(d_fund, 2), of_which_fees_closed=round(fees_in, 2),
                closed_in_window={k: {kk: (round(v, 2) if isinstance(v, float) else v)
                                      for kk, v in e.items()} for k, e in by_leg.items()},
                identity_err=round(abs((d_pb + d_tr + d_cv) - (path[jt] - path[jp])), 2))


def attribute(scen: str, anchor: str) -> dict:
    r, cr, fmeta = run_headline(scen, anchor, engine_halts=True)
    r0, _, _ = run_headline(scen, anchor, engine_halts=False)
    closes = np.asarray([c for _, c in r["spliced_closes"]])
    ts = np.asarray(r["ts"])
    low_j = int(np.argmin(closes))
    low_ts = int(ts[low_j])
    eh = r["engine_halts_info"]
    halt_ts = eh["pullback"]["halt_ts"]
    bal12 = r["balances"]["365"]["equity"]
    j12 = r["ts"].index(r["balances"]["365"]["ts"])
    pb_end, tr_end = r["leg_mtm"]["pullback"][j12], r["leg_mtm"]["trend"][j12]
    cv_end = r["carry_value"][j12]
    pb = [t for t in r["trades"] if t["leg"] == "pullback"]
    fees_leg = {leg: round(sum(t["fees"] for t in r["trades"] if t["leg"] == leg), 2) for leg in stress.LEGS}
    # carry
    n = len(cr.ts)
    cv = np.asarray(r["carry_value"])
    cmin = int(np.argmin(cv))
    carry = dict(start=round(float(cv[0]), 2), at_12m=round(float(cv_end), 2),
                 change_12m=round(float(cv_end - stress.CARRY_START), 2),
                 funding_received=round(cr.funding_cum[j12], 2), fees=round(cr.fees_cum[j12], 2),
                 flips=len(cr.flips()), bars_on_pct=round(100.0 * sum(cr.on[:j12 + 1]) / (j12 + 1), 1),
                 worst_dip_from_start=round(float(cv.min() - cv[0]), 2), worst_dip_date=_d(ts[cmin]),
                 max_dd=round(float((cv / np.maximum.accumulate(cv) - 1.0).min()), 4),
                 funding_source=fmeta["source"])
    # forgone by the S3 halt: pullback MTM at 12m, halt vs no-halt (trend identical)
    pb0_end = r0["leg_mtm"]["pullback"][j12]
    tr0_end = r0["leg_mtm"]["trend"][j12]
    forgone = dict(no_halt_12m=r0["balances"]["365"]["equity"], halt_12m=bal12,
                   pullback_mtm_no_halt=round(pb0_end, 2), pullback_mtm_halt=round(pb_end, 2),
                   d_pullback=round(pb0_end - pb_end, 2), d_trend=round(tr0_end - tr_end, 2),
                   dropped_trades=eh["pullback"]["dropped"],
                   no_halt_max_dd=r0["max_dd"], halt_max_dd=r["max_dd"])
    out = dict(
        scenario=scen, label=run_all.SCEN_LABEL[scen], K=K, offset=0,
        btc=dict(low_pct=round(float(closes.min() / closes[0] - 1), 4), low_date=_d(low_ts),
                 end_pct=round(float(closes[-1] / closes[0] - 1), 4)),
        balance_12m=bal12, balance_12m_exact=r["balances"]["365"]["exact"],
        pnl_12m=round(bal12 - stress.START_EQUITY, 2),
        decomposition_12m=dict(pullback_mtm=round(pb_end, 2), trend_mtm=round(tr_end, 2),
                               carry=round(cv_end - stress.CARRY_START, 2),
                               identity_err=round(abs(70_000 + pb_end + tr_end + cv_end - bal12), 2)),
        pullback=dict(groups=trade_groups(r["trades"], "pullback", halt_ts),
                      n_trades=len(pb), realised=round(sum(t["pnl"] for t in pb if t["reason"] != "OPEN"), 2),
                      stops=dict(n=sum(1 for t in pb if t["reason"] == "STOP"),
                                 pnl=round(sum(t["pnl"] for t in pb if t["reason"] == "STOP"), 2)),
                      signals=dict(n=sum(1 for t in pb if t["reason"] in ("SIGNAL", "TIME")),
                                   pnl=round(sum(t["pnl"] for t in pb if t["reason"] in ("SIGNAL", "TIME")), 2)),
                      by_side={s: round(sum(t["pnl"] for t in pb if t["side"] == s), 2) for s in "LS"},
                      mult_at_entry=[t["size_mult"] for t in pb],
                      s3_halt=dict(halted=eh["pullback"]["halted"], date=eh["pullback"]["halt_date"],
                                   margin=eh["pullback"]["margin_at_halt"], dropped=eh["pullback"]["dropped"]),
                      forgone_by_halt=forgone,
                      trades=[dict(side=t["side"], entry_date=t["entry_date"], exit_date=t["exit_date"],
                                   pnl=t["pnl"], mult=t["size_mult"], reason=t["reason"], kind=t["kind"],
                                   notional=t["notional"]) for t in pb]),
        trend=trend_detail(r, low_ts),
        daily_loss_halts=dict(n=len([h for h in r["halts"] if h["kind"] == "DAILY_LOSS"]), cost=0.0,
                              reentry_cost=0.0, rail_used_pct=r["rail_use"]["daily_loss"]["used_pct"],
                              closest_margin=r["rail_use"]["daily_loss"]["min_margin"],
                              closest_date=r["rail_use"]["daily_loss"]["date"],
                              worst_intrabar_day=r["worst_day_intrabar"]),
        drawdown_halt=dict(n=len([h for h in r["halts"] if h["kind"] == "DRAWDOWN"]), cost=0.0,
                           rail_used_pct=r["rail_use"]["drawdown"]["used_pct"],
                           closest_margin=r["rail_use"]["drawdown"]["min_margin"],
                           closest_date=r["rail_use"]["drawdown"]["date"]),
        carry=carry,
        fees=dict(total=r["fees"], by_leg=fees_leg, n_fills=2 * r["n_trades"] + r["n_open"]),
        btc_funding=dict(total=r["btc_funding_total"], by_leg=r["btc_funding_by_leg"]),
        max_dd_window=dd_window(r, cr),
        earned=dict(top3=sorted([dict(leg=t["leg"], side=t["side"], entry_date=t["entry_date"],
                                      exit_date=t["exit_date"], pnl=t["pnl"]) for t in r["trades"]],
                                key=lambda d: -d["pnl"])[:3],
                    positive_by_leg={leg: round(sum(t["pnl"] for t in r["trades"] if t["leg"] == leg and t["pnl"] > 0), 2)
                                     for leg in stress.LEGS},
                    negative_by_leg={leg: round(sum(t["pnl"] for t in r["trades"] if t["leg"] == leg and t["pnl"] <= 0), 2)
                                     for leg in stress.LEGS}),
    )
    return out


def print_scenario(a: dict) -> None:
    print(f"\n=== {a['label']}  K {a['K']}  offset 0  |  BTC low {a['btc']['low_pct']:+.0%} on {a['btc']['low_date']}, "
          f"12m {a['btc']['end_pct']:+.0%}  |  12m balance {a['balance_12m']:,.0f} "
          f"({a['pnl_12m']:+,.0f}{'' if a['balance_12m_exact'] else ', 12m*'})")
    d = a["decomposition_12m"]
    print(f"  12m = 70,000 + pullback {d['pullback_mtm']:+,.0f} + trend {d['trend_mtm']:+,.0f} + 30,000 + carry "
          f"{d['carry']:+,.0f}  (identity err {d['identity_err']})")
    p = a["pullback"]
    print(f"  (a) pullback: {p['n_trades']} trades, realised {p['realised']:+,.0f}; stops {p['stops']['n']} "
          f"{p['stops']['pnl']:+,.0f}; signal/time exits {p['signals']['n']} {p['signals']['pnl']:+,.0f}; "
          f"longs {p['by_side']['L']:+,.0f} shorts {p['by_side']['S']:+,.0f}")
    for k, e in p["groups"].items():
        print(f"      {k:40s} n {e['n']:2d}  pnl {e['pnl']:+9,.0f}  (gross {e['gross']:+,.0f} fees {e['fees']:,.0f} funding {e['funding']:+,.0f})")
    h = p["s3_halt"]
    f = p["forgone_by_halt"]
    print(f"      S3 paper-book halt: {h['halted']} {h['date']} margin {h['margin']} dropped {h['dropped']}; "
          f"no-halt counterfactual 12m {f['no_halt_12m']:,.0f} vs {f['halt_12m']:,.0f}: pullback MTM "
          f"{f['pullback_mtm_no_halt']:+,.0f} vs {f['pullback_mtm_halt']:+,.0f} (d {f['d_pullback']:+,.0f}; trend d {f['d_trend']:+,.0f}); "
          f"maxDD {f['no_halt_max_dd']:.1%} vs {f['halt_max_dd']:.1%}")
    print("      mult at entry:", p["mult_at_entry"])
    t = a["trend"]
    print(f"  (b) trend: {t['n_closed']} closed (+{t['n_open']} open, MTM {t['open_mtm']:+,.0f}); winners {t['winners']['n']} "
          f"{t['winners']['pnl']:+,.0f}; losers {t['losers']['n']} {t['losers']['pnl']:+,.0f} (stop-outs {t['stop_losers']['n']} "
          f"{t['stop_losers']['pnl']:+,.0f}); crash phase (entered by {t['crash_phase']['to']}) {t['crash_phase']['n']} "
          f"{t['crash_phase']['pnl']:+,.0f}; after the low {t['after_low']['n']} {t['after_low']['pnl']:+,.0f}")
    s = t["longest_losing_streak"]
    print(f"      longest losing streak {s['n']} trades {s['pnl']:+,.0f} ({s['from_date']} .. {s['to_date']}), followed by {s['followed_by']}")
    print(f"      crash-short give-back: {t['crash_short_give_back']}")
    print(f"      top3: {t['top3']}")
    dl = a["daily_loss_halts"]
    print(f"  (c) daily-loss halts: {dl['n']} (cost 0); rail used {dl['rail_used_pct']:.0%}, closest {dl['closest_margin']:,.0f} on "
          f"{dl['closest_date']}; worst intrabar day {dl['worst_intrabar_day']['date']} {dl['worst_intrabar_day']['usd']:+,.0f}")
    dd = a["drawdown_halt"]
    print(f"  (d) drawdown halt: {dd['n']} (cost 0); rail used {dd['rail_used_pct']:.0%}, closest {dd['closest_margin']:,.0f} on {dd['closest_date']}")
    c = a["carry"]
    print(f"  (e) carry: {c['change_12m']:+,.0f} at 12m (funding {c['funding_received']:+,.0f}, fees {c['fees']:,.0f}, {c['flips']} flips, "
          f"on {c['bars_on_pct']:.0f}% of bars; worst dip {c['worst_dip_from_start']:+,.0f} on {c['worst_dip_date']}, maxDD {c['max_dd']:.1%}; {c['funding_source']})")
    print(f"  (f) fees {a['fees']['total']:,.0f} (pullback {a['fees']['by_leg']['pullback']:,.0f}, trend {a['fees']['by_leg']['trend']:,.0f}); "
          f"BTC funding {a['btc_funding']['total']:+,.0f} (pullback {a['btc_funding']['by_leg']['pullback']:+,.0f}, trend {a['btc_funding']['by_leg']['trend']:+,.0f})")
    w = a["max_dd_window"]
    print(f"  maxDD {w['max_dd']:.1%}: peak {w['peak_equity']:,.0f} ({w['peak_date']}) -> trough {w['trough_equity']:,.0f} ({w['trough_date']}) = {w['fall']:+,.0f}: "
          f"pullback {w['d_pullback']:+,.0f}, trend {w['d_trend']:+,.0f}, carry {w['d_carry']:+,.0f} (inside the legs: BTC funding "
          f"{w['of_which_btc_funding']:+,.0f}, fees on trades closed in the window {w['of_which_fees_closed']:,.0f}); closed in window {w['closed_in_window']}; identity err {w['identity_err']}")
    e = a["earned"]
    print(f"  earned: positive trades pullback {e['positive_by_leg']['pullback']:+,.0f} / trend {e['positive_by_leg']['trend']:+,.0f}; "
          f"negative pullback {e['negative_by_leg']['pullback']:+,.0f} / trend {e['negative_by_leg']['trend']:+,.0f}; top3 {e['top3']}")


def main() -> None:
    res = {}
    for scen, anchor in run_all.SCENARIOS:
        a = attribute(scen, anchor)
        res[scen] = a
        print_scenario(a)
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1)
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()
