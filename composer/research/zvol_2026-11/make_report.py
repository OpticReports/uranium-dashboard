"""Build the HTML report (charts + tables) from out/*.json and the frozen inputs.
Usage: python3 make_report.py DATA_DIR OUT_HTML"""
import datetime as dt, html, json, math, sys
import lib, sim

D, OUT = sys.argv[1], sys.argv[2]
C = D + "/cache"
J = {k: json.load(open(f"out/{k}.json")) for k in ("q1_live", "q2_attrib", "q2b_long", "q3_events", "q4_books", "q5_predict", "q6_refine", "q7_extra", "q8_robust")}
q8 = J["q8_robust"]
q1, q2, q2b, q3, q4, q5, q6, q7 = (J[k] for k in ("q1_live", "q2_attrib", "q2b_long", "q3_events", "q4_books", "q5_predict", "q6_refine", "q7_extra"))
pc = lambda x, d=1: f"{x * 100:+.{d}f}%"
pu = lambda x, d=1: f"{x * 100:.{d}f}%"
usd = lambda x: ("-" if x < 0 else "+") + f"${abs(x):,.0f}"
CH = {}                                    # chart data, keyed by element id


def thin(pts, k):
    return pts[::k] + ([pts[-1]] if (len(pts) - 1) % k else [])


# 1. ZVOL price vs total return
z = lib.load("ZVOL", C)["rows"]; zd = sorted(z)
CH["c_zvol"] = {"type": "line", "yfmt": "idx", "series": [
    {"name": "Total return (distributions reinvested)", "slot": 1, "pts": thin([[d, 100 * z[d]["adj"] / z[zd[0]]["adj"]] for d in zd], 3)},
    {"name": "Price only (what a price chart shows)", "slot": 2, "pts": thin([[d, 100 * z[d]["close"] / z[zd[0]]["close"]] for d in zd], 3)}]}

# 2. HARV live: displayed, with distributions, T-bills (dollars of P&L)
live = json.load(open(D + "/live.json"))["HARV"]
hds = [dt.datetime.fromtimestamp(m / 1000, tz=dt.timezone.utc).date().isoformat() for m in live["epoch_ms"]]
keep = [i for i, d in enumerate(hds) if d <= lib.END]
hds = [hds[i] for i in keep]; hv = [live["series"][i] for i in keep]; hda = [live["deposit_adjusted_series"][i] for i in keep]
bil = lib.rets(lib.series("BIL", C, "adj")); dist = {}
for d, t, u in q1["HARV"]["distribution_rows"]:
    dist[d] = dist.get(d, 0.0) + u
p_disp, p_tr, p_bil = [[hds[0], 0.0]], [[hds[0], 0.0]], [[hds[0], 0.0]]
a = b = c = 0.0
for i in range(1, len(hds)):
    a += hv[i - 1] * (hda[i] / hda[i - 1] - 1); b += hv[i - 1] * (hda[i] / hda[i - 1] - 1) + dist.get(hds[i], 0.0); c += hv[i - 1] * bil.get(hds[i], 0.0)
    p_disp.append([hds[i], a]); p_tr.append([hds[i], b]); p_bil.append([hds[i], c])
CH["c_live"] = {"type": "line", "yfmt": "usd", "zero": True, "series": [
    {"name": "HARV incl. the ZVOL payout that went to account cash", "slot": 1, "pts": p_tr},
    {"name": "HARV as Composer displays it", "slot": 2, "pts": p_disp},
    {"name": "T-bills on the same dollars", "slot": 3, "pts": p_bil}]}

# 3. long path: rule net vs always-short vs bills (log)
P = sim.panel(D); r = sim.run(P, cost_bps=5.0)
lv = [1.0, 1.0, 1.0]; e1, e2, e3 = [], [], []
for d, x in zip(r["days"], r["ret"]):
    lv[0] *= 1 + x; lv[1] *= 1 + P["ZVOL"][d]; lv[2] *= 1 + P["BIL"][d]
    e1.append([d, lv[0]]); e2.append([d, lv[1]]); e3.append([d, lv[2]])
CH["c_long"] = {"type": "line", "yfmt": "mult", "log": True, "shade": ["2023-04-19", lib.END, "real ZVOL"], "series": [
    {"name": "Harvester rule, net of 5 bps per trade", "slot": 1, "pts": thin(e1, 8)},
    {"name": "Always short mid-term VIX futures (ZVOL held every day)", "slot": 2, "pts": thin(e2, 8)},
    {"name": "T-bills", "slot": 3, "pts": thin(e3, 8)}]}

# 4. calendar years
yrs = q2b["years"]
CH["c_years"] = {"type": "bars", "yfmt": "pct", "cats": list(yrs.keys()), "vals": [v["net"] for v in yrs.values()], "name": "Harvester rule, net return by calendar year",
                 "note": {"2006": "from July", "2026": "to 11-17"}}

# 5. event study: ZVOL weight by day around a +15% VIX day
ev_pre = q3["VIX +15% in a day | pre-ZVOL 2006-07..2023-04"]; ev_real = q3["VIX +15% in a day | real era 2023-04..2026-11"]
ks = [str(k) for k in range(-5, 11)]
CH["c_event"] = {"type": "line", "yfmt": "pct0", "xnum": True, "zero": True, "series": [
    {"name": f"2006-2023 ({ev_pre['n']} spikes)", "slot": 1, "pts": [[int(k), ev_pre["profile"][k]["zvol"]] for k in ks]},
    {"name": f"2023-2026 ({ev_real['n']} spikes)", "slot": 2, "pts": [[int(k), ev_real["profile"][k]["zvol"]] for k in ks]}]}

# 6. forest: change vs KEEP, haircut (a)
LA = "haircut (a): switcher at its live pace"
rows = []
for bname, v in q4["lenses"][LA].items():
    if "vs_keep" in v:
        k = v["vs_keep"]
        short = {"A": "A  HARV → KMLM", "B": "B  HARV → switcher", "C": "C  strip the sleeve", "D": "D  no harvester", "E": "E  HARV → T-bills"}[bname[0]]
        rows.append({"name": short, "cagr": [k["cagr"]["point"], k["cagr"]["lo"], k["cagr"]["hi"]], "dd": [k["maxdd"]["point"], k["maxdd"]["lo"], k["maxdd"]["hi"]]})
CH["c_forest_cagr"] = {"type": "forest", "yfmt": "pp", "rows": [{"name": x["name"], "v": x["cagr"]} for x in rows], "title": "Change in yearly return vs KEEP"}
CH["c_forest_dd"] = {"type": "forest", "yfmt": "pp", "rows": [{"name": x["name"], "v": x["dd"]} for x in rows], "title": "Change in worst drawdown vs KEEP (right = deeper)"}

# 7. rolling one-year return
CH["c_roll"] = {"type": "line", "yfmt": "pct0", "zero": True, "shade": ["2023-04-19", lib.END, "real ZVOL"], "series": [
    {"name": "Harvester rule, net return over the trailing 252 sessions", "slot": 1, "pts": [[d, x] for d, x in q7["rolling_series"]]}]}

# 8. live books KEEP vs A
allv = json.load(open(D + "/live.json"))
def lser(k):
    v = allv[k]; ds = [dt.datetime.fromtimestamp(m / 1000, tz=dt.timezone.utc).date().isoformat() for m in v["epoch_ms"]]
    return {ds[i]: v["deposit_adjusted_series"][i] / v["deposit_adjusted_series"][i - 1] - 1 for i in range(1, len(ds)) if ds[i] <= lib.END}
L = {k: lser(k) for k in ("HG", "KMLM", "SLEEVE", "HARV")}
ld = sorted(d for d in L["HARV"] if all(d in L[k] for k in L))
htr = dict(L["HARV"]); hval = dict(zip(hds, hv))
for d, t, u in q1["HARV"]["distribution_rows"]:
    htr[d] = htr.get(d, 0.0) + u / hval[hds[hds.index(d) - 1]]
ka, aa = 100.0, 100.0; pk, pa = [[hds[0], 100.0]], [[hds[0], 100.0]]
for d in ld:
    ka *= 1 + .29 * L["HG"][d] + .29 * L["KMLM"][d] + .27 * L["SLEEVE"][d] + .15 * htr[d]
    aa *= 1 + .29 * L["HG"][d] + .44 * L["KMLM"][d] + .27 * L["SLEEVE"][d]
    pk.append([d, ka]); pa.append([d, aa])
CH["c_livebook"] = {"type": "line", "yfmt": "idx", "series": [{"name": "KEEP: harvester at 15%", "slot": 1, "pts": pk},
                                                              {"name": "A: harvester's 15% moved into the KMLM symphony", "slot": 2, "pts": pa}]}

# ---- tables -------------------------------------------------------------------------------------
def table(head, body, cls=""):
    h = "".join(f"<th>{html.escape(str(x))}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in row) + "</tr>" for row in body)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


H, K = q1["HARV"], q1["KMLM"]
t_live = table(["Since funding, to 11-17", "HARV", "VIX sleeve inside KMLM (from holdings, before trading costs)", "Switcher part of KMLM (the remainder)"],
               [["Window", f"{H['from']} → {H['to']} ({H['sessions']} sessions)", f"{K['from']} → {K['to']} ({K['sessions']} sessions)", "same"],
                ["As Composer displays it", f"{usd(H['pnl_displayed_usd'])} ({pc(H['twr_displayed'])})", usd(K["parts_usd_displayed_basis"]["sleeve"]), usd(K["parts_usd_displayed_basis"]["switcher"])],
                ["ZVOL payout that went to account cash (08-19)", usd(H["distributions_paid_outside_usd"]), usd(K["distributions_paid_outside_usd"]), "—"],
                ["Including it", f"<b>{usd(H['pnl_with_distributions_usd'])}</b> ({pc(H['twr_with_distributions_approx'])})", f"<b>{usd(K['parts_usd_total_return']['sleeve'])}</b>", f"<b>{usd(K['parts_usd_total_return']['switcher'])}</b> ({pc(K['part_twr']['switcher'][0])})"],
                ["T-bills on the same dollars", usd(H["tbills_same_dollars_usd"]), "", ""],
                ["The model on the same dates", pc(H["model_same_dates"], 2), "", ""],
                ["HARV's dollars in the switcher instead", usd(H["same_dollars_in_switcher_usd"]), "", ""],
                ["Worst drawdown / worst day", f"{pu(H['live_stats']['harv']['maxdd'])} / {pc(H['live_stats']['harv']['worst'])}", "", f"{pu(H['live_stats']['switcher']['maxdd'])} / {pc(H['live_stats']['switcher']['worst'])} (in HARV's window)"]])

SPN = {"2006-07..2009": "2006-07 → 2009", "2010..2019": "<b>2010 → 2019</b>", "2020..2023-04-18": "2020 → 2023-04", "2023-04-19..2025": "2023-04 → 2025 (real ZVOL)", "2026 to 11-17": "<b>2026 to 11-17</b>",
       "all before ZVOL, without 2008": "All before ZVOL, without 2008", "all before ZVOL": "All before ZVOL existed"}
t_sub = table(["Period", "Sessions", "Rule, net/yr", "Over T-bills/yr", "Sharpe", "Max DD"],
              [[SPN[k], v["n"], pc(v["cagr"]), pc(v["excess_cagr"]), f"{v['sharpe']:.2f}", pu(v["maxdd"], 0)] for k, v in q8["subperiods"].items()])
L8, C8 = q8["lag"], q8["cost"]
t_frag = table(["Change to the test", "2006-07 → 2023-04, net/yr", "2023-04 → 2026-11, net/yr"],
               [["As modelled: trade at the signal's close, 5 bps a trade", pc(L8["all before ZVOL | lag 0"]["cagr"]), pc(L8["real era | lag 0"]["cagr"])],
                ["<b>Every trade one close late</b>", f"<b>{pc(L8['all before ZVOL | lag 1']['cagr'])}</b>", pc(L8["real era | lag 1"]["cagr"])],
                ["ZVOL bps per held day: on time → one close late", f"{L8['all before ZVOL | lag 0']['zvol_bps_when_held']:.0f} → {L8['all before ZVOL | lag 1']['zvol_bps_when_held']:.0f}", f"{L8['real era | lag 0']['zvol_bps_when_held']:.0f} → {L8['real era | lag 1']['zvol_bps_when_held']:.0f}"]]
               + [[f"{c} bps a trade", pc(C8[c]["all before ZVOL"]), pc(C8[c]["real era"])] for c in ("0", "10", "15", "20", "30")]
               + [["Priced by fund: ZVOL 14 / VXZ 3 / PULS 0 bps", pc(C8["ZVOL 14 / VXZ 3 / PULS 0"]["all before ZVOL"]), pc(C8["ZVOL 14 / VXZ 3 / PULS 0"]["real era"])]])
BV = q8["bills_vs_harvester"]
rng3 = lambda v, d=1: f"{pc(v[0], d)} [{pc(v[1], d)}, {pc(v[2], d)}]"
pts3 = lambda v: f"{v[0] * 100:+.1f} [{v[1] * 100:+.1f}, {v[2] * 100:+.1f}]"
t_pace = table(["If the harvester earns…", "Its pace", "Book return if it were T-bills instead [90%]", "Book return if it moved into KMLM [90%]", "On HARV's $37.5k, per year over bills"],
               [[{"as measured 2023-26": "what it did in 2023–2026", "long-run pace before ZVOL": "its 2006–2023 margin over bills", "2010-19 pace": "its 2010–2019 margin over bills"}[k], pc(v["harvester_cagr"]),
                 rng3(v["E_minus_KEEP_cagr"]), rng3(v["A_minus_KEEP_cagr"]), usd(round(v["usd_per_year_over_bills_on_37.5k"], -2))] for k, v in BV.items()])
OD = q8["other_destinations"]
t_alt = table(["Book", "Return/yr", "Max DD", "Δ return vs KEEP [90%]", "Δ Sharpe [90%]", "Δ max DD, pts [90%]"],
              [[html.escape(k), pc(v["cagr"]), pu(v["maxdd"]), rng3(v["d_cagr"]), f"{v['d_sharpe'][0]:+.2f} [{v['d_sharpe'][1]:+.2f}, {v['d_sharpe'][2]:+.2f}]", pts3(v["d_maxdd"])] for k, v in OD.items()])

E = q2b["eras"]
def era_row(k, label):
    v = E[k]
    return [label, v["n"], pc(v["net"]["cagr"]), f"{v['net']['sharpe']:.2f}", pu(v["net"]["maxdd"]), pc(v["static_mix"]["cagr"]), pc(v["always_short_midterm"]["cagr"]) + f" (DD {pu(v['always_short_midterm']['maxdd'], 0)})",
            pc(v["tbills_cagr"]), f"{v['zvol_bps_when_held']:.0f} vs {v['zvol_bps_all_days']:.0f}", ("&lt; 0.001" if v["placebo_p"] < 0.001 else f"{v['placebo_p']:.3f}")]
t_eras = table(["Era", "Sessions", "Rule, net/yr", "Sharpe", "Max DD", "Same funds, no timing", "Always short", "T-bills", "ZVOL bps/day: held vs all days", "Placebo p"],
               [era_row("2006-07..2010-12 (futures-built)", "2006-07 → 2010 (futures-built)"), era_row("2011-01..2017-12", "2011 → 2017"), era_row("2018-01..2023-04-18", "2018 → 2023-04"),
                era_row("pre-ZVOL all (2006-07..2023-04-18)", "<b>All before ZVOL existed</b>"), era_row("real ZVOL era (2023-04-19..2026-11-17)", "<b>Real ZVOL era (2023-04 → now)</b>")])

def book_rows(lens):
    out = []
    for bname, v in q4["lenses"][lens].items():
        p = v["point"]; row = [html.escape(bname), pc(p["cagr"]), pu(p["vol"]), f"{p['sharpe']:.2f}", pu(p["maxdd"]), pc(p["worst21"]), pc(p["worst_day"])]
        if "vs_keep" in v:
            k = v["vs_keep"]
            row += [f"{pc(k['cagr']['point'])} [{pc(k['cagr']['lo'])}, {pc(k['cagr']['hi'])}]", f"{k['sharpe']['point']:+.2f} [{k['sharpe']['lo']:+.2f}, {k['sharpe']['hi']:+.2f}]",
                    f"{k['maxdd']['point'] * 100:+.1f} [{k['maxdd']['lo'] * 100:+.1f}, {k['maxdd']['hi'] * 100:+.1f}]"]
        else:
            row += ["—", "—", "—"]
        out.append(row)
    return out
BH = ["Book (HG / KMLM / SLEEVE / HARV)", "Return/yr", "Vol", "Sharpe", "Max DD", "Worst 21 sessions", "Worst day", "Δ return vs KEEP [90%]", "Δ Sharpe [90%]", "Δ max DD, pts [90%]"]
t_books_a = table(BH, book_rows(LA)); t_books_m = table(BH, book_rows("as-measured")); t_books_b = table(BH, book_rows("haircut (b): half of that"))
lw = q4["live_window"]["books"]
t_livebooks = table(["Book, live 2026-07-23 → 11-17", "Total return", "Worst drawdown", "Worst day"],
                    [[html.escape(b), pc(v["with distributions"]["total"]), pu(v["with distributions"]["maxdd"]), pc(v["with distributions"]["worst_day"])] for b, v in lw.items()])

NAMES = {"roll_yield_mid": "Mid-term roll yield (4th vs 7th month)", "vix3m_over_vix": "VIX3M / VIX (front slope)", "vix6m_over_vix3m": "VIX6M / VIX3M", "vrp": "Variance risk premium (VIX² − realised)",
         "vvix": "VVIX", "vix_pctile_1y": "VIX percentile, 1 year", "hyg_5d": "HYG 5-day return", "spy_rsi2": "SPY RSI(2): the rule's own trigger"}
pr = []
for k, nm in NAMES.items():
    v = q5["predictors"][k]; row = [nm]
    for h in ("1", "5", "21"):
        s = v[h]; row.append(f"t {s['t_nw']:+.1f}, OOS R² {s['oos_r2'] * 100:+.2f}%" + (" ✔" if s["works"] else ""))
    e = q5["entries"][k]; row.append(f"{pc(e['below_median_mean'], 2)} vs {pc(e['above_median_mean'], 2)} (t {e['t_diff']:+.1f})")
    pr.append(row)
t_pred = table(["Known at the close", "Next 1 session", "Next 5", "Next 21", "On the rule's ZVOL entries: below- vs above-median"], pr)

rr = []
for wn, res in q6.items():
    for k, v in res.items():
        row = [html.escape(wn), html.escape(k), pc(v["cagr"]), f"{v['sharpe']:.2f}", pu(v["maxdd"]), pc(v["worst_day"])]
        if "vs_base" in v:
            b = v["vs_base"]; row += [f"{pc(b['cagr'][0])} [{pc(b['cagr'][1])}, {pc(b['cagr'][2])}]", f"{b['maxdd'][0] * 100:+.1f} [{b['maxdd'][1] * 100:+.1f}, {b['maxdd'][2] * 100:+.1f}]"]
        else:
            row += ["—", "—"]
        rr.append(row)
t_ref = table(["Window", "Variant", "Net/yr", "Sharpe", "Max DD", "Worst day", "Δ return vs unchanged [90%]", "Δ max DD, pts [90%]"], rr)

ep = q3["zvol_episodes"]
def ep_row(era, g):
    s = ep[era][g]
    return [era, g, s["n"], pc(s["mean_fund_return"], 2), pu(s["win"], 0), pc(s["worst"])] if s.get("n") else None
t_ep = table(["Era", "Curve / VIX at entry", "Entries", "Mean return of the ZVOL holding", "Win rate", "Worst"],
             [x for x in (ep_row(e, g) for e in ep for g in ("all", "contango (VIX3M > VIX)", "inverted (VIX3M <= VIX)", "VIX >= 30")) if x])

leg = q2["leg_contribution"]
t_legs = table(["Leg (real era, before trading costs)", "2023 (from 04-20)", "2024", "2025", "2026 (to 11-17)", "All", "Average weight", "bps/day when held vs every day"],
               [[t] + [f"{leg[t][y] * 100:+.1f} pts" for y in ("2023", "2024", "2025", "2026", "all")] + [pu(q2["avg_weight"][t]), f"{q2['fund_mean_bps'][t]['when_held']:.0f} vs {q2['fund_mean_bps'][t]['all_days']:.1f}"] for t in ("ZVOL", "VXZ", "PULS")])

X = q7["ex_date_2026_11_18"]; RM = q7["risk_matched"][LA]; RO = q7["rolling_1y"]
A = q4["lenses"][LA]["A  HARV -> KMLM symphony"]["vs_keep"]; Em = q4["lenses"]["as-measured"]["E  HARV -> T-bills"]["vs_keep"]; Am = q4["lenses"]["as-measured"]["A  HARV -> KMLM symphony"]["vs_keep"]
pre = E["pre-ZVOL all (2006-07..2023-04-18)"]; real = E["real ZVOL era (2023-04-19..2026-11-17)"]
BODY = open("report_body.html").read()
Cb = q4["lenses"][LA]["C  strip the VIX sleeve only"]["vs_keep"]
G8 = OD["G  half of HARV -> KMLM symphony"]; F8 = OD["F  HARV -> pro rata to HG / KMLM / SLEEVE"]
EMV = BV["as measured 2023-26"]["E_minus_KEEP_cagr"]; ELV = BV["long-run pace before ZVOL"]["E_minus_KEEP_cagr"]
FZ = q8["zvol_fills_vs_close"]; LV = q8["live_vol_lens"]; SUBP = q8["subperiods"]
VER = open("VERIFICATION.html").read()
BODY = BODY.replace("{{main}}", open("report_main.html").read())
subs = {
    "{{t_live}}": t_live, "{{t_eras}}": t_eras, "{{t_books_a}}": t_books_a, "{{t_books_m}}": t_books_m, "{{t_books_b}}": t_books_b, "{{t_livebooks}}": t_livebooks,
    "{{t_pred}}": t_pred, "{{t_ref}}": t_ref, "{{t_ep}}": t_ep, "{{t_legs}}": t_legs, "{{t_sub}}": t_sub, "{{t_frag}}": t_frag, "{{t_pace}}": t_pace, "{{t_alt}}": t_alt,
    "{{harv_disp}}": usd(H["pnl_displayed_usd"]), "{{harv_dist}}": usd(H["distributions_paid_outside_usd"]).lstrip("+"), "{{harv_true}}": usd(H["pnl_with_distributions_usd"]),
    "{{harv_bills}}": usd(H["tbills_same_dollars_usd"]), "{{harv_sw}}": usd(H["same_dollars_in_switcher_usd"]), "{{sw_dd}}": pu(H["live_stats"]["switcher"]["maxdd"], 0), "{{sw_worst}}": pc(H["live_stats"]["switcher"]["worst"], 0),
    "{{ex_harv}}": f"${X['HARV']['distribution_usd']:,.0f}", "{{ex_kmlm}}": f"${X['KMLM']['distribution_usd']:,.0f}", "{{ex_harv_drop}}": pu(X["HARV"]["displayed_drop"]), "{{ex_kmlm_drop}}": pu(X["KMLM"]["displayed_drop"]),
    "{{pre_cagr}}": pc(pre["net"]["cagr"]), "{{sub_1019}}": pc(SUBP["2010..2019"]["cagr"]), "{{sub_1019_abs}}": pu(abs(SUBP["2010..2019"]["cagr"])), "{{sub_no08}}": pc(SUBP["all before ZVOL, without 2008"]["cagr"]),
    "{{lag0}}": pc(L8["all before ZVOL | lag 0"]["cagr"]), "{{lag1}}": pc(L8["all before ZVOL | lag 1"]["cagr"]), "{{cost10}}": pc(C8["10"]["all before ZVOL"]), "{{cost_fund}}": pc(C8["ZVOL 14 / VXZ 3 / PULS 0"]["all before ZVOL"]),
    "{{fill_med}}": f"{FZ['median_bps']:.0f}", "{{fill_nw}}": f"{FZ['notional_weighted_bps']:.0f}", "{{fill_adv}}": f"{round(FZ['share_adverse'] * FZ['n'])}",
    "{{e_meas}}": "%.1f points [%.1f to %.1f]" % (-EMV[0] * 100, -EMV[2] * 100, -EMV[1] * 100),
    "{{e_long}}": "%+.1f points [%+.1f, %+.1f]" % (ELV[0] * 100, ELV[1] * 100, ELV[2] * 100),
    "{{usd_meas}}": usd(round(BV["as measured 2023-26"]["usd_per_year_over_bills_on_37.5k"], -2)).lstrip("+"), "{{usd_long}}": usd(round(BV["long-run pace before ZVOL"]["usd_per_year_over_bills_on_37.5k"], -2)).lstrip("+"), "{{usd_1019}}": usd(round(BV["2010-19 pace"]["usd_per_year_over_bills_on_37.5k"], -2)),
    "{{a_ddd_pt}}": f"{A['maxdd']['point'] * 100:+.1f} pts", "{{a_ddd_rng}}": f"{A['maxdd']['lo'] * 100:.1f} to {A['maxdd']['hi'] * 100:.1f}",
    "{{roll_last}}": pc(RO["last"]), "{{roll_ex_pct}}": f"{q8['rolling_excess_1y']['pctile_pre_ZVOL'] * 100:.0f}",
    "{{a_dcagr}}": f"{pc(A['cagr']['point'])} [{pc(A['cagr']['lo'])}, {pc(A['cagr']['hi'])}]", "{{a_ddd}}": f"{A['maxdd']['point'] * 100:+.1f} pts [{A['maxdd']['lo'] * 100:+.1f}, {A['maxdd']['hi'] * 100:+.1f}]",
    "{{c_dcagr}}": f"{pc(Cb['cagr']['point'])} [{pc(Cb['cagr']['lo'])}, {pc(Cb['cagr']['hi'])}]", "{{c_ddd}}": f"{Cb['maxdd']['point'] * 100:+.1f} [{Cb['maxdd']['lo'] * 100:+.1f}, {Cb['maxdd']['hi'] * 100:+.1f}]",
    "{{g_dcagr}}": rng3(G8["d_cagr"]), "{{g_ddd}}": pts3(G8["d_maxdd"]), "{{f_dcagr}}": rng3(F8["d_cagr"]), "{{f_ddd}}": pts3(F8["d_maxdd"]),
    "{{be_meas}}": pc(q8["breakeven_switcher_cagr"]["harvester as measured"], 0), "{{be_long}}": pc(q8["breakeven_switcher_cagr"]["harvester at its long-run pace"], 0),
    "{{lv_keep_dd}}": pu(LV["live pace"]["keep"]["maxdd"], 0), "{{lv_a_dd}}": pu(LV["live pace"]["A"]["maxdd"], 0), "{{sw_live_ann}}": pc(q4["switcher_live_annualised"], 0),
    "{{live_keep}}": pc(lw["KEEP 29/29/27/15"]["with distributions"]["total"]), "{{live_a}}": pc(lw["A  HARV -> KMLM symphony"]["with distributions"]["total"]),
    "{{live_keep_dd}}": pu(lw["KEEP 29/29/27/15"]["with distributions"]["maxdd"]), "{{live_a_dd}}": pu(lw["A  HARV -> KMLM symphony"]["with distributions"]["maxdd"]),
    "{{ev_w0}}": pu(ev_pre["profile"]["0"]["zvol"], 0), "{{ev_wavg}}": pu(q8["worst_short_vol_days"]["avg_weight_all_days"], 0), "{{worst_held}}": str(q8["worst_short_vol_days"]["held_zvol_on"]),
    "{{ev_after}}": pc(ev_pre["harv_d1_10_mean"], 2), "{{ev_after_real}}": pc(ev_real["harv_d1_10_mean"], 2), "{{usual_pre}}": pc(q8["usual_10_sessions"]["pre"], 2), "{{usual_real}}": pc(q8["usual_10_sessions"]["real"], 2),
    "{{pt_pre}}": f"{q8['plain_trigger']['pre']['zvol_bps_next_day']:.0f}", "{{pt_real}}": f"{q8['plain_trigger']['real']['zvol_bps_next_day']:.0f}", "{{pt_all}}": f"{q8['plain_trigger']['pre']['all_days_bps']:.0f}",
    "{{static}}": pc(q2["static_mix"]["cagr"]), "{{mirror}}": pc(q2["mirror_rule"]["cagr"], 0).lstrip("-").lstrip("+"),
    "{{verification}}": VER, "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
for k, v in subs.items():
    BODY = BODY.replace(k, v)
left = [x for x in __import__("re").findall(r"\{\{[a-z_0-9]+\}\}", BODY)]
assert not left, left
open(OUT, "w").write(BODY)
print("wrote", OUT, len(BODY) // 1024, "KB")
