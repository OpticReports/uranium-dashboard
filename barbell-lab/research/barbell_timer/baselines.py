#!/usr/bin/env python3
"""Phase 1 — monthly baselines 1975-> per frozen brief.

Sleeves: GDE-synth (Phase 0 construction, carry model per VALIDATION_REPORT),
SPY (SPX TR splice), bills (TB3MS). Portfolios: B&H GDE-synth, B&H SPY, static
25/75 / 50/50 / 75/25 GDE/SPY at monthly AND quarterly rebalancing.

Conventions (stated once here, repeated in BASELINES.md):
- Monthly panel, month-END convention. SPX TR 1975-01..1993-01 = ^GSPC
  month-end close + Shiller dividend rate D/(12*P) (dividends smeared evenly;
  Shiller D is a trailing annualized rate — flagged); 1993-02.. = SPY
  dividend-adjusted month-end (splice month uses SPY only, no cross-source
  return). Gold 1975-02..1976-03 = datahub monthly-AVERAGE London fix
  (convention mismatch flagged, 14 months); 1976-04.. = GCUSD month-end.
- Bills: TB3MS monthly-average yield y -> (1+y/100)^(1/12)-1, accrued in the
  SAME month (yield known during the month; no lookahead).
- Gold futures excess = gold spot return - (TB3 - effective lease)/yr, lease =
  literature schedule pre-2007, -0.40%/yr (GDE-anchored, measured) 2007->.
- GDE-synth = 0.90*SPX_TR + 0.10*bills + 0.90*fut_excess - 25bp/yr (20 fee +
  5 roll). Pre-2022 the fund did not exist: fee/roll held constant, flagged.
- Rebalancing happens at month-end closes (Phase 1 has no signals; the
  next-month-open convention binds Phases 2-3). Quarterly = reset at
  Mar/Jun/Sep/Dec month-ends, weights drift in between.
- Stats: see datalib.perf_stats docstring (Sharpe = arithmetic monthly excess
  over bills / std of excess * sqrt12; Sortino MAR = bills with full-sample
  downside denominator; DD stats on month-end curve -> intramonth-blind).
- Robustness row: pessimistic carry variant, pre-2007 lease reduced by 1pp.
- Daily maxDD estimates 1976-03-> where daily data allows (GSPC+smeared divs
  pre-1993 — flagged approximation), to size the intramonth-blind bias.
"""
import json
import os

import numpy as np
import pandas as pd

import datalib as dl

HERE = os.path.dirname(os.path.abspath(__file__))
START, END = "1975-01", "2026-07"   # full months only


# --------------------------------------------------------------------------
def month_end(px):
    return px.groupby(px.index.to_period("M")).last()


def build_monthly_panel(pessimistic=False):
    d = dl.load_daily()
    sh_px, sh_div, gold_dh, tb3 = dl.load_monthly_raw()

    # ---- SPX TR monthly ----
    gspc_me = month_end(d["gspc"])          # PeriodIndex[M]
    spy_me = month_end(d["spy"])
    div_rate = pd.Series(sh_div.values, index=pd.PeriodIndex(sh_div.index, freq="M"))
    pre = gspc_me.loc[:"1993-01"]
    pre_ret = pre.pct_change() + (div_rate / 12.0 / pre).reindex(pre.index)
    post_ret = spy_me.pct_change().loc["1993-02":]
    spx_tr = pd.concat([pre_ret.loc["1975-02":"1993-01"], post_ret]).dropna()

    # ---- gold monthly ----
    gold_dh_p = pd.Series(gold_dh.values, index=pd.PeriodIndex(gold_dh.index, freq="M"))
    gc_me = month_end(d["gc"])
    gold_pre = gold_dh_p.pct_change().loc["1975-02":"1976-03"]  # avg convention, flagged
    gold_post = gc_me.pct_change().loc["1976-04":]
    gold = pd.concat([gold_pre, gold_post]).dropna()

    # ---- bills / carry ----
    tb3_p = pd.Series(tb3.values, index=pd.PeriodIndex(tb3.index, freq="M"))
    bills = (1.0 + tb3_p / 100.0) ** (1.0 / 12.0) - 1.0
    lease = pd.Series([
        (dl.EFFECTIVE_LEASE_2007ON if p.year >= 2007 else
         dl.lease_rate_for(pd.Timestamp(p.start_time)) - (1.0 if pessimistic else 0.0))
        for p in bills.index], index=bills.index)
    carry = (1.0 + (tb3_p - lease) / 100.0) ** (1.0 / 12.0) - 1.0

    idx = spx_tr.index.intersection(gold.index).intersection(bills.index)
    idx = idx[(idx >= START) & (idx <= END)]
    spx_tr, gold, bills, carry = (s.reindex(idx) for s in (spx_tr, gold, bills, carry))
    fut_ex = gold - carry
    gde = 0.90 * spx_tr + 0.10 * bills + 0.90 * fut_ex - (dl.GDE_FEE + dl.ROLL_COST) / 12.0
    return pd.DataFrame({"spx_tr": spx_tr, "gold": gold, "bills": bills,
                         "fut_ex": fut_ex, "gde_synth": gde})


def static_mix(gde, spy, w, freq_months):
    """Static w GDE / (1-w) SPY, rebalanced every `freq_months` month-ends."""
    if freq_months == 1:
        return w * gde + (1 - w) * spy
    va, vb, wealth = w, 1.0 - w, []
    for p in gde.index:
        va *= (1.0 + gde[p])
        vb *= (1.0 + spy[p])
        tot = va + vb
        wealth.append(tot)
        if p.month % freq_months == 0:      # Mar/Jun/Sep/Dec for freq=3
            va, vb = tot * w, tot * (1.0 - w)
    wl = pd.Series(wealth, index=gde.index)
    ret = wl / wl.shift(1) - 1.0
    ret.iloc[0] = wl.iloc[0] - 1.0          # wealth starts at 1.0
    return ret


def rolling_ann(r, window=120):
    cum = (1 + r).rolling(window).apply(np.prod, raw=True)
    return cum ** (12.0 / window) - 1.0


# --------------------------------------------------------------------------
def daily_maxdd_estimates(panel_m):
    """Daily curves 1976-03-> for intramonth-blind bias sizing.
    Pre-1993 equity = ^GSPC price + Shiller D/P smeared over days (flagged)."""
    d = dl.load_daily()
    sh_px, sh_div, _, tb3 = dl.load_monthly_raw()
    cal = d["gspc"].loc["1976-03-01":].index
    spy_r = d["spy"].pct_change().dropna()
    gspc_r = d["gspc"].pct_change().reindex(cal)
    # smear dividends: monthly D/(12*P_me) spread over that month's trading days
    div_rate = pd.Series(sh_div.values, index=pd.PeriodIndex(sh_div.index, freq="M"))
    gspc_me = month_end(d["gspc"])
    dy_m = (div_rate / 12.0 / gspc_me).dropna()
    per = pd.PeriodIndex(cal, freq="M")
    days_in_m = pd.Series(1, index=cal).groupby(per).transform("sum").values
    dy_d = pd.Series(dy_m.reindex(per).values / days_in_m, index=cal)
    eq_r = (gspc_r + dy_d)
    eq_r.loc[spy_r.index.intersection(cal[cal >= "1993-02-01"])] = \
        spy_r.reindex(cal).loc["1993-02-01":]
    gc_r = dl.align_returns_to(d["gspc"].loc["1976-02-25":], d["gc"]).reindex(cal)
    dtb3 = d["dtb3"]
    bill_r = dl.bill_daily_returns(cal, dtb3).reindex(cal)
    dty = cal.to_series().diff().dt.days / 365.0
    y = dtb3.reindex(dtb3.index.union(cal)).ffill().reindex(cal)
    lease = pd.Series([(dl.EFFECTIVE_LEASE_2007ON if t.year >= 2007
                        else dl.lease_rate_for(t)) for t in cal], index=cal)
    carry = ((y.shift(1) - lease) / 100.0) * dty
    fut_ex = gc_r - carry
    gde_d = (0.90 * eq_r + 0.10 * bill_r + 0.90 * fut_ex
             - (dl.GDE_FEE + dl.ROLL_COST) * dty)
    frame = pd.DataFrame({"gde": gde_d, "spy": eq_r}).dropna()

    def maxdd_daily(r):
        eqc = (1 + r).cumprod()
        return float((eqc / eqc.cummax() - 1).min())

    # 50/50 with month-end rebalancing, daily valuation
    w = 0.5
    va = vb = 0.5
    rets = []
    months = frame.index.to_period("M")
    last_month = months[0]
    for i in range(len(frame)):
        if months[i] != last_month:        # first day of new month: rebalance
            tot = va + vb
            va, vb = tot * w, tot * w
            last_month = months[i]
        va *= (1 + frame["gde"].iloc[i])
        vb *= (1 + frame["spy"].iloc[i])
        rets.append(va + vb)
    eq5050 = pd.Series(rets, index=frame.index) / 1.0
    dd5050 = float((eq5050 / eq5050.cummax() - 1).min())
    return {"window": f"{frame.index[0].date()} -> {frame.index[-1].date()}",
            "note": ("pre-1993 equity leg = ^GSPC price + smeared Shiller"
                     " dividends (approximation, flagged); gold = GCUSD daily"
                     " (1:30pm settle vs 4pm equity close — daily-only"
                     " mismatch)"),
            "GDE-synth": maxdd_daily(frame["gde"]),
            "SPY": maxdd_daily(frame["spy"]),
            "50/50 monthly-rebal": dd5050}


# --------------------------------------------------------------------------
def main():
    panel = build_monthly_panel()
    panel_p = build_monthly_panel(pessimistic=True)
    rf = panel["bills"]

    ports = {
        "B&H GDE-synth": panel["gde_synth"],
        "B&H SPY": panel["spx_tr"],
        "25/75 GDE/SPY (M)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.25, 1),
        "50/50 GDE/SPY (M)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.50, 1),
        "75/25 GDE/SPY (M)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.75, 1),
        "25/75 GDE/SPY (Q)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.25, 3),
        "50/50 GDE/SPY (Q)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.50, 3),
        "75/25 GDE/SPY (Q)": static_mix(panel["gde_synth"], panel["spx_tr"], 0.75, 3),
        "Bills (TB3MS)": panel["bills"],
        "[pessimistic carry] B&H GDE-synth": panel_p["gde_synth"],
        "[pessimistic carry] 50/50 (M)":
            static_mix(panel_p["gde_synth"], panel_p["spx_tr"], 0.50, 1),
    }

    stats = {}
    print(f"panel {panel.index[0]} -> {panel.index[-1]}  ({len(panel)} months)")
    hdr = (f"{'portfolio':34s} {'CAGR':>7s} {'Vol':>6s} {'Sharpe':>6s}"
           f" {'Sortino':>7s} {'MaxDD':>7s} {'UW(m)':>5s} {'Calmar':>6s}"
           f" {'Ulcer':>6s} {'Worst12m':>8s} {'%pos':>5s}")
    print(hdr)
    for name, r in ports.items():
        s = dl.perf_stats(r, rf)
        stats[name] = s
        print(f"{name:34s} {s['CAGR']:7.2%} {s['Vol']:6.2%} {s['Sharpe']:6.2f}"
              f" {s['Sortino']:7.2f} {s['MaxDD_m']:7.1%} {s['UnderwaterMax_m']:5d}"
              f" {s['Calmar']:6.2f} {s['Ulcer']:6.1f} {s['Worst12m']:8.1%}"
              f" {s['PctPos']:5.1%}")
        if s["Sharpe"] > 1.2:
            print(f"  ^^ TRIPWIRE: Sharpe > 1.2 on {name} — audit before use")

    # decade CAGR blocks for context/regime honesty
    dec = {}
    for name in ["B&H GDE-synth", "B&H SPY", "50/50 GDE/SPY (M)"]:
        r = ports[name]
        by = {}
        for y0, y1 in [(1975, 1979), (1980, 1989), (1990, 1999), (2000, 2009),
                       (2010, 2019), (2020, 2026)]:
            w = r.loc[f"{y0}-01":f"{y1}-12"]
            by[f"{y0}s"] = float((1 + w).prod() ** (12.0 / len(w)) - 1.0)
        dec[name] = by
    print("\ndecade CAGRs:")
    for n, by in dec.items():
        print(f"  {n:22s}", {k: f"{v:.1%}" for k, v in by.items()})

    # rolling 10y spreads
    roll = {}
    r10 = {n: rolling_ann(ports[n]) for n in
           ["B&H GDE-synth", "B&H SPY", "50/50 GDE/SPY (M)",
            "25/75 GDE/SPY (M)", "75/25 GDE/SPY (M)"]}
    for n in ["B&H GDE-synth", "50/50 GDE/SPY (M)", "25/75 GDE/SPY (M)",
              "75/25 GDE/SPY (M)"]:
        sp_spy = (r10[n] - r10["B&H SPY"]).dropna()
        sp_5050 = (r10[n] - r10["50/50 GDE/SPY (M)"]).dropna()
        roll[n] = {
            "vs_SPY": {"win_rate": float((sp_spy > 0).mean()),
                       "mean": float(sp_spy.mean()), "min": float(sp_spy.min()),
                       "max": float(sp_spy.max())},
            "vs_5050M": {"win_rate": float((sp_5050 > 0).mean()),
                         "mean": float(sp_5050.mean()),
                         "min": float(sp_5050.min()),
                         "max": float(sp_5050.max())}}
        print(f"rolling10y {n:22s} vs SPY win {roll[n]['vs_SPY']['win_rate']:.0%}"
              f" [{roll[n]['vs_SPY']['min']:+.1%},{roll[n]['vs_SPY']['max']:+.1%}]"
              f"  vs 50/50 win {roll[n]['vs_5050M']['win_rate']:.0%}")

    # intramonth-blind bias
    dd_daily = daily_maxdd_estimates(panel)
    print("\ndaily maxDD estimates:", {k: (f"{v:.1%}" if isinstance(v, float) else v)
                                       for k, v in dd_daily.items()})

    # persist: frozen monthly panel + results
    panel_out = {str(k): {c: (None if pd.isna(panel.loc[k, c]) else float(panel.loc[k, c]))
                          for c in panel.columns} for k in panel.index}
    with open(os.path.join(HERE, "panel_monthly.json"), "w") as fh:
        json.dump({"convention": "see baselines.py docstring; month-end, "
                   "signals (Phases 2-3) must execute NEXT month open",
                   "panel": panel_out}, fh)
    with open(os.path.join(HERE, "baselines_results.json"), "w") as fh:
        json.dump({"stats": stats, "decade_cagr": dec, "rolling10y": roll,
                   "daily_maxdd": dd_daily,
                   "portfolio_returns": {n: {str(k): float(v)
                                             for k, v in r.items()}
                                         for n, r in ports.items()}},
                  fh, default=float)
    print("\nwrote panel_monthly.json, baselines_results.json")


if __name__ == "__main__":
    main()
