#!/usr/bin/env python3
"""Composer vs IBKR execution-cost study — v3, post-adversarial-QA.

QA fixes vs v2 (all findings from the hostile audit incorporated):
- F1 CRITICAL: dvm_capital is already NET of Composer's engine slippage
  (QA regression: residual -5.2bps per unit turnover, 0 on no-trade days).
  v3 reconstructs TRUE GROSS = cap x Prod(1/(1-5bps*turn_t)); the Composer
  leg is the engine curve itself (+ an illiquid-spread surcharge where half
  the quoted spread exceeds the engine's flat 5bps); the IBKR leg applies
  its costs to true gross. Nothing is double-counted.
- F4: as-traded prices reconstructed from Yahoo split events (tick floors
  and per-share commissions no longer see split-adjusted phantom prices).
- F5: commission notional compounds with the curve (static-slice minimum no
  longer binds spuriously); IBKR per-share all-in raised to $0.0065
  (tiered commission + exchange/venue/clearing pass-throughs).
- F7: turnover is TWO-SIDED traded-notional/NAV (A->B counts 2.0), matching
  Composer's per-traded-dollar charging; labeled as such.
- F9: no compounded multi-year dollar projections from overfit gross curves;
  results are drag rates + dollars at CURRENT book scale + sensitivity.
- Composer-side truth-in-labeling: the 5bps/side is COMPOSER'S OWN engine
  assumption (reproduced from their backtests at 4.99-5.03bps); the
  sensitivity block shows the gap if their real fills are better (2.5bps)
  or worse (7.5bps).
Artifacts: trades-<SYM>.csv, exec_study_results.json.
"""
import csv, json, os

SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/exec_study"
OUT = os.path.dirname(os.path.abspath(__file__))
BOOK = 250_000
WEIGHTS = {"HG": .29, "KMLM": .29, "SLEEVE": .27, "HARV": .15}
EPOCH0 = 719163
ENGINE_BPS = 5.0 / 1e4            # Composer engine slippage (measured 4.99-5.03)
IBKR_IMPROVE = 0.5                # fraction of half-spread paid (sensitivity below)
IBKR_PER_SHARE = 0.0065           # tiered commission + venue/clearing pass-throughs
SPREAD_BPS = {"ANGL": 3, "BIL": 1, "BSV": 2, "HYG": 1, "KIE": 3, "LABD": 6,
    "LABU": 6, "LQD": 1, "PULS": 2, "QLD": 2, "SMH": 2, "SOXL": 2, "SOXS": 3,
    "SPAB": 2, "SPXL": 2, "SQQQ": 1, "SSO": 2, "SVIX": 8, "SVXY": 4, "TECL": 3,
    "TLT": 1, "TMF": 3, "TMV": 4, "TNA": 2, "TQQQ": 1, "UDOW": 3, "UGL": 4,
    "UPRO": 2, "USD": 6, "UVXY": 2, "VBF": 6, "VIXM": 8, "VIXY": 3, "VXZ": 6,
    "ZVOL": 30}                   # F10: thin funds widened (ZVOL 20->30, VIXM/USD up)

def eday(d):
    import datetime
    return datetime.date.fromordinal(EPOCH0 + int(d)).isoformat()

def load_px(t):
    """Returns {date: {a: adjclose, c: split-adjusted close, raw: AS-TRADED close}}."""
    import datetime
    res = json.load(open(f"{SC}/px/{t}.json"))
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    splits = (res.get("events") or {}).get("splits") or {}
    sp = sorted(({"d": datetime.datetime.fromtimestamp(int(v["date"]), tz=datetime.timezone.utc).date().isoformat(),
                  "f": float(v["numerator"]) / float(v["denominator"])} for v in splits.values()),
                key=lambda x: x["d"])
    out = {}
    for i, ts in enumerate(res["timestamp"]):
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()
        if q["close"][i] is None: continue
        fut = 1.0
        for s in sp:
            if s["d"] > d: fut *= s["f"]
        out[d] = {"a": adj[i] or q["close"][i], "c": q["close"][i],
                  "raw": q["close"][i] * fut}
    return out

def study(label):
    bt = json.load(open(f"{SC}/bt-{label}.json"))
    w = bt["tdvm_weights"]
    cap = bt["dvm_capital"][list(bt["dvm_capital"])[0]]
    days = sorted({d for t in w for d in w[t]}, key=int)
    tickers = [t for t in w if t != "$USD"]
    px = {t: load_px(t) for t in tickers}
    years = (int(days[-1]) - int(days[0])) / 365.25

    rows = []
    gross = 1.0                    # true gross factor (engine slippage added back)
    comp_extra = 1.0               # Composer illiquid surcharge factor
    ibkr_net_vs_gross = 1.0        # IBKR net factor applied to true gross
    slice_now = BOOK * WEIGHTS[label]
    ann_turn = 0.0
    for i in range(1, len(days)):
        dp, dc = days[i-1], days[i]
        date_p, date_c = eday(dp), eday(dc)
        drifted, tot = {}, 0.0
        for t in tickers + ["$USD"]:
            wp = w.get(t, {}).get(dp, 0.0)
            r = 0.0
            if t != "$USD":
                pa, pb = px[t].get(date_p, {}).get("a"), px[t].get(date_c, {}).get("a")
                r = (pb/pa - 1) if pa and pb else 0.0
            drifted[t] = wp * (1 + r); tot += drifted[t]
        if tot <= 0: continue
        turn = drag_x = drag_i = 0.0
        cap_ret = cap[dc]/cap[dp] - 1
        slice_now *= (1 + cap_ret)          # book slice compounding with the curve
        for t in tickers:
            delta = abs(w[t].get(dc, 0.0) - drifted[t]/tot)
            if delta < 1e-6: continue
            turn += delta
            raw_price = px[t].get(date_c, {}).get("raw") or 1.0
            tick_bps = 0.01 / raw_price * 1e4
            hs = max(SPREAD_BPS.get(t, 5), tick_bps) / 2 / 1e4
            surcharge = max(0.0, hs - ENGINE_BPS)     # engine underprices illiquids
            notional = delta * slice_now
            commission_frac = max(0.35, IBKR_PER_SHARE * notional/raw_price) / notional
            cost_i = hs * IBKR_IMPROVE + commission_frac
            drag_x += delta * surcharge
            drag_i += delta * cost_i
            rows.append([date_c, t, round((w[t].get(dc,0.0) - drifted[t]/tot)*100, 3),
                         round(notional, 2), round(hs*1e4, 2),
                         round(delta*max(ENGINE_BPS, hs)*1e4, 3), round(delta*cost_i*1e4, 3)])
        ann_turn += turn
        gross *= (1 + cap_ret) / (1 - ENGINE_BPS * turn)   # add engine slippage back
        comp_extra *= (1 - drag_x)
        ibkr_net_vs_gross *= (1 - drag_i)

    with open(f"{OUT}/trades-{label}.csv", "w", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(["date","ticker","delta_weight_pct","notional_compounding_$",
                     "half_spread_bps","drag_composer_bps_of_nav","drag_ibkr_bps_of_nav"])
        cw.writerows(rows)

    cap_ratio = cap[days[-1]] / cap[days[0]]
    net_c = cap_ratio * comp_extra                 # engine curve + illiquid surcharge
    net_i = gross * ibkr_net_vs_gross
    dr_c = -(((net_c/gross))**(1/years) - 1) * 1e4
    dr_i = -(((net_i/gross))**(1/years) - 1) * 1e4
    return {"label": label, "window": f"{eday(days[0])}..{eday(days[-1])}",
            "years": round(years, 2),
            "turnover_2sided_x_yr": round(ann_turn/years, 1),
            "true_gross_x": round(gross, 2),
            "engine_curve_x": round(cap_ratio, 2),
            "drag_composer_bps_yr": round(dr_c, 0),
            "drag_ibkr_bps_yr": round(dr_i, 0),
            "edge_bps_yr": round(dr_c - dr_i, 0)}

def main():
    res = [study(lab) for lab in WEIGHTS]
    json.dump(res, open(f"{OUT}/exec_study_results.json", "w"), indent=1)
    print(f"{'sym':7} {'window':24} {'turn2s/yr':>9} {'gross x':>8} "
          f"{'Comp drag':>10} {'IBKR drag':>10} {'edge/yr':>9}")
    blend_c = blend_i = 0.0
    for r in res:
        print(f"{r['label']:7} {r['window']:24} {r['turnover_2sided_x_yr']:>8}x "
              f"{r['true_gross_x']:>8} {r['drag_composer_bps_yr']:>7,.0f}bps "
              f"{r['drag_ibkr_bps_yr']:>7,.0f}bps {r['edge_bps_yr']:>6,.0f}bps")
        blend_c += WEIGHTS[r["label"]] * r["drag_composer_bps_yr"]
        blend_i += WEIGHTS[r["label"]] * r["drag_ibkr_bps_yr"]
    edge = blend_c - blend_i
    print(f"\nblended 29/29/27/15 drag: Composer {blend_c:,.0f}bps/yr, IBKR {blend_i:,.0f}bps/yr")
    print(f"IBKR edge: {edge:,.0f}bps/yr = ${BOOK*edge/1e4:,.0f}/yr on ${BOOK:,} "
          f"(~${BOOK*edge/1e4*5:,.0f} over 5y at current scale, before compounding)")
    print("\nsensitivity (Composer engine's real per-side cost is an assumption):")
    for eng in (2.5, 5.0, 7.5):
        c = sum(WEIGHTS[r["label"]] * (r["drag_composer_bps_yr"] - (5.0-eng)*r["turnover_2sided_x_yr"]) for r in res)
        print(f"  Composer at {eng}bps/side: gap {c-blend_i:+,.0f}bps/yr "
              f"(${BOOK*(c-blend_i)/1e4:+,.0f}/yr)")

if __name__ == "__main__":
    main()
