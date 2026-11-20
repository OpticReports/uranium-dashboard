"""Build the HTML report of the KMLM switcher study from out/*.json (charts + tables). Page shell and chart
code: report_body.html (the ZVOL report's, with category x-labels, a reference line and a plain number format).
Usage: python3 make_report.py OUT_HTML"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
st, mac, bk, ab, g1, g4, rb = J("stats"), J("macro"), J("book"), J("cells_ab"), J("gates"), J("g4"), J("robust")
OUT = sys.argv[1]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
lg = lambda x: f"{x:+.2f}"                                                                 # noqa: E731
CH = {}
C, B = st["cells"], st["base"]
F1_N = (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)
LIVE = ("F1a.rsi10", "F1b.rsi10")


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap, narrow=False):
    box = f'<div id="{cid}" style="max-width:560px"></div>' if narrow else f'<div id="{cid}"></div>'
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p>{box}</div>'


# ---- 1. the window surface on the real-fund period
val = lambda c, k: 0.0 if c in LIVE else C[c][k]                                           # noqa: E731
XL = {"xnum": True, "xlabels": [str(n) for n in F1_N], "xunit": "-day window"}
CH["c_surface"] = {"type": "line", "yfmt": "pp", "zero": True, **XL, "series": [
    {"name": "Both periods pooled (2021-06 to 2026-11)", "slot": 1, "pts": [[i, val(f"F1a.rsi{n}", "dlog_per_yr")] for i, n in enumerate(F1_N)]},
    {"name": "2023-04 onward only", "slot": 2, "pts": [[i, val(f"F1a.rsi{n}", "dlog_A")] for i, n in enumerate(F1_N)]},
    {"name": "2021-06 to 2023-04 only (not looked at before the test)", "slot": 3, "pts": [[i, val(f"F1a.rsi{n}", "dlog_B")] for i, n in enumerate(F1_N)]}]}
tc = st["tier_c"]["cells"]
CH["c_surface_c"] = {"type": "line", "yfmt": "pp", "zero": True, **XL, "series": [
    {"name": "Switch window only", "slot": 1, "pts": [[i, 0.0 if n == 10 else tc[f"F1a.rsi{n}"]["dlog_per_yr"]] for i, n in enumerate(F1_N)]},
    {"name": "Switch and ranked picks", "slot": 2, "pts": [[i, 0.0 if n == 10 else tc[f"F1b.rsi{n}"]["dlog_per_yr"]] for i, n in enumerate(F1_N)]}]}

# ---- 2. every cell's t against the live rule
order = sorted((c for c in C if c not in LIVE), key=lambda c: C[c]["t"])
short = lambda c: c.split(".", 1)[1]                                                       # noqa: E731
FAM = {"F1a": "RSI switch", "F1b": "RSI switch+picks", "F2": "vote", "F3": "pops/dips", "F4": "momentum", "F5": "price vs MA", "F6": "MA cross"}
CH["c_cells"] = {"type": "bars", "yfmt": "raw", "cats": [f"{short(c)} ({FAM[C[c]['family']]})" for c in order],
                 "short": [short(c) for c in order], "every": 6, "vals": [round(C[c]["t"], 2) for c in order],
                 "ref": round(st["beside"]["max_stat_90"], 2), "reflabel": "needed to count after 74 tries",
                 "name": "t-statistic of each variant's growth against the live rule"}

# ---- 3. equity and drawdown: live, the nearest miss, the best moving-average form
days = ab["days"]
best = st["beside"]["best_by_t"]
ma = max((c for c in C if c.startswith(("F5.", "F6."))), key=lambda c: C[c]["dlog_per_yr"])
worst = min(C, key=lambda c: C[c]["dlog_per_yr"])


def curve(cid):
    lvl, pk, eq, dd = 1.0, 1.0, [], []
    for d, r in zip(days, ab["cells"][cid]["ret"]):
        lvl *= 1 + r
        pk = max(pk, lvl)
        eq.append([d, lvl])
        dd.append([d, lvl / pk - 1])
    return eq[::3] + [eq[-1]], dd[::3] + [dd[-1]]


names = {"base": "Live rule (10-day RSI)", best: f"Nearest miss: {short(best)} (not significant)", ma: f"Best moving-average form: {short(ma)}"}
eqs = {c: curve(c) for c in names}
CH["c_equity"] = {"type": "line", "yfmt": "mult", "log": True, "shade": [ab["a_start"], days[-1], "2023-04 onward"],
                  "series": [{"name": names[c], "slot": i + 1, "pts": eqs[c][0]} for i, c in enumerate(names)]}
CH["c_dd"] = {"type": "line", "yfmt": "pct0", "zero": True,
              "series": [{"name": names[c], "slot": i + 1, "pts": eqs[c][1]} for i, c in enumerate(names)]}

# ---- 4. macro: forward 21-session return of the risk-on basket, favourable state minus unfavourable
MN = {"M1_credit": "Credit appetite (HYG/IEF above its 50-day average)", "M2_stress": "Low financial stress (OFR index below zero)",
      "M3_stockbond": "Stock-bond correlation negative (60 days)", "M4_dollar": "Dollar below its 50-day average",
      "M5_curve": "Yield curve positive (10y minus 3m)", "M6_realrate": "No real-rate shock (10y TIPS, 20 days)"}
CH["c_macro"] = {"type": "bars", "yfmt": "pct", "cats": [k.split("_")[0] for k in MN],
                 "vals": [mac["inputs"][k]["on.h21"]["diff"] for k in MN],
                 "name": "Risk-on basket, next 21 sessions: favourable state minus unfavourable"}

# ---- 5. book: change in yearly return against the live book
bf = bk["books"]["daily_fixed"]
CH["c_book"] = {"type": "forest", "yfmt": "pp", "title": "Book return a year vs the live book",
                "rows": [{"name": short(c) + (" *" if c == bk["illustration_only"] else ""),
                          "v": [v["diff_vs_live"]["cagr"][k] for k in ("point", "lo", "hi")]}
                         for c, v in bf.items() if c != "base"]}

# ---- tables
fam_names = {"F1a": "RSI window, switch only (3 to 60 days)", "F1b": "RSI window, switch and ranked picks", "F2": "Voting or splitting across windows",
             "F3": "Overbought and dip-buy tests at 5, 7, 14, 20 days", "F4": "Relative momentum (XLK return vs KMLM return)",
             "F5": "Price above its moving average (simple and exponential)", "F6": "Fast/slow moving-average crossovers"}
rows = []
for f, nm in fam_names.items():
    ids = [c for c in C if C[c]["family"] == f and c not in LIVE]
    b_ = max(ids, key=lambda c: C[c]["dlog_per_yr"])
    w_ = min(ids, key=lambda c: C[c]["dlog_per_yr"])
    rows.append([nm, len(ids), sum(C[c]["dlog_per_yr"] > 0 for c in ids), sum(bool(C[c]["passes"]) for c in ids),
                 f"{short(b_)}: {pc(C[b_]['all']['cagr'])}, t {lg(C[b_]['t'])}", f"{short(w_)}: {pc(C[w_]['all']['cagr'])}, t {lg(C[w_]['t'])}"])
t_fam = table(["Family", "Variants", "Ahead of the live rule", "Pass all five tests", "Best (return a year, t)", "Worst"], rows)

rows = [["<b>Live rule (10)</b>", pc(B["all"]["cagr"]), pu(B["all"]["maxdd"]), f"{B['all']['sharpe']:.2f}", pc(B["A"]["cagr"]), pc(B["B"]["cagr"]), "", "", B["flips"], pu(B["knife_share"], 1)]]
for n in F1_N:
    if n == 10:
        continue
    v = C[f"F1a.rsi{n}"]
    rows.append([f"{n} days", pc(v["all"]["cagr"]), pu(v["all"]["maxdd"]), f"{v['all']['sharpe']:.2f}", pc(v["A"]["cagr"]), pc(v["B"]["cagr"]),
                 lg(v["t"]), f"{v['p_fw']:.2f}", v["flips"], pu(v["knife_share"], 1)])
t_win = table(["Switch window", "Return a year", "Max drawdown", "Sharpe", "2023-04 on", "2021-06 to 2023-04", "t vs live", "Family-wise p",
               "Flips", "Knife-edge days"], rows)

rows = []
for k, nm in MN.items():
    a, s = mac["inputs"][k]["on.h21"], mac["inputs"][k]["spread.h21"]
    rows.append([nm, pu(mac["share_on"][k]), pc(a["on_mean"], 1), pc(a["off_mean"], 1), lg(a["t_nw"]), lg(s["t_nw"]), f"{a['p_holm']:.2f}",
                 f"{a['oos_r2']:+.3f}", f"{a['mirror_p']:.2f}", "on" if mac["current"][k] else "off"])
t_mac = table(["Input (the favourable state)", "Share of days", "Risk-on, next 21 sessions: favourable", "Unfavourable", "t", "t (on minus off)",
               "Holm p", "Out-of-sample R²", "Placebo p", "Now"], rows)

rows = []
for c, v in bf.items():
    m, d = v["metrics"], v.get("diff_vs_live")
    dv = bk["books"]["drift_cap44"][c]
    rows.append([("<b>Live rule</b>" if c == "base" else short(c) + (" *" if c == bk["illustration_only"] else "")), pc(m["cagr"]), pu(m["maxdd"], 1),
                 f"{m['sharpe']:.2f}", pc(v["kmlm_alone"]["cagr"]), pu(v["kmlm_alone"]["maxdd"]),
                 "" if not d else f"{d['cagr']['point'] * 100:+.1f} [{d['cagr']['lo'] * 100:+.1f}, {d['cagr']['hi'] * 100:+.1f}]",
                 "" if not d else f"{d['maxdd']['point'] * 100:+.1f} [{d['maxdd']['lo'] * 100:+.1f}, {d['maxdd']['hi'] * 100:+.1f}]",
                 pc(dv["metrics"]["cagr"])])
t_book = table(["KMLM variant in the book", "Book return a year", "Book max drawdown", "Book Sharpe", "KMLM alone: return", "KMLM alone: drawdown",
                "Δ book return, pts [90%]", "Δ book drawdown, pts [90%]", "Book return with drift and the 44% cap"], rows)

gate_rows = [["Live rule vs Composer's own backtest", f"{g1['G1']['holdings_within_1.5pct'][0]} of {g1['G1']['holdings_within_1.5pct'][1]} sessions' holdings",
              f"{g1['G1']['corr']:.5f}", f"{pc(g1['G1']['sim']['cagr'], 1)} vs {pc(g1['G1']['composer']['cagr'], 1)}"]]
for k, nm in (("rsi14", "14-day RSI switch"), ("sma50", "Price above 50-day simple average"), ("ema50", "Price above 50-day exponential average")):
    gate_rows.append([nm + " vs Composer", f"{g4[k]['holdings_same'][0]} of {g4[k]['holdings_same'][1]}", f"{g4[k]['corr']:.5f}",
                      f"{pc(g4[k]['sim']['cagr'], 1)} vs {pc(g4[k]['composer']['cagr'], 1)}"])
t_gate = table(["Check", "Same holdings", "Daily-return correlation", "Return a year: simulator vs Composer"], gate_rows)

n_ahead = sum(C[c]["dlog_per_yr"] > 0 for c in C if c not in LIVE)
c_ahead = sum(v["dlog_per_yr"] > 0 for k, v in tc.items() if k not in LIVE)
subs = {
    "{{n_cells}}": "74", "{{n_pass}}": str(len(st["passing"])), "{{n_ahead}}": str(n_ahead), "{{n_chall}}": str(len(C) - 2),
    "{{best}}": short(best), "{{best_t}}": lg(C[best]["t"]), "{{best_p}}": f"{C[best]['p_fw']:.2f}", "{{best_d}}": lg(C[best]["dlog_per_yr"]),
    "{{crit}}": f"{st['beside']['max_stat_90']:.2f}", "{{live_cagr}}": pc(B["all"]["cagr"]), "{{live_dd}}": pu(B["all"]["maxdd"]),
    "{{live_a}}": pc(B["A"]["cagr"]), "{{live_b}}": pc(B["B"]["cagr"]), "{{ma}}": short(ma), "{{ma_t}}": lg(C[ma]["t"]), "{{ma_cagr}}": pc(C[ma]["all"]["cagr"]),
    "{{pbo}}": f"{st['beside']['pbo']['pbo']:.2f}", "{{dsr}}": f"{st['beside']['deflated_sharpe_of_best_difference']['dsr']:.2f}",
    "{{c_ahead}}": str(c_ahead), "{{c_n}}": str(len(tc) - 2), "{{c_span}}": " to ".join(st["tier_c"]["span"]),
    "{{c_cagr}}": pc(st["tier_c"]["base"]["cagr"]), "{{c_dd}}": pu(st["tier_c"]["base"]["maxdd"]),
    "{{n_sess}}": f"{st['n_sessions']:,}", "{{span_b}}": st["tier_b"][0], "{{span_a}}": st["tier_a"][0], "{{end}}": st["tier_a"][1],
    "{{book_cagr}}": pc(bf["base"]["metrics"]["cagr"]), "{{book_dd}}": pu(bf["base"]["metrics"]["maxdd"], 1), "{{book_span}}": " to ".join(bk["span"]),
    "{{mac_span}}": " to ".join(mac["sample"]), "{{mac_works}}": ", ".join(mac["works"]) or "none",
    "{{stress_on}}": pc(mac["inputs"]["M2_stress"]["on.h21"]["on_mean"], 1), "{{stress_off}}": pc(mac["inputs"]["M2_stress"]["on.h21"]["off_mean"], 1),
    "{{stress_t}}": lg(mac["inputs"]["M2_stress"]["on.h21"]["t_nw"]), "{{stress_mp}}": f"{mac['inputs']['M2_stress']['on.h21']['mirror_p']:.2f}",
    "{{short_a}}": lg(rb["short"]["A_per_yr"]), "{{short_b}}": lg(rb["short"]["B_per_yr"]), "{{short_at}}": f"{rb['short']['A_t']:+.1f}",
    "{{short_bt}}": f"{rb['short']['B_t']:+.1f}", "{{long_a}}": lg(rb["long"]["A_per_yr"]), "{{long_at}}": f"{rb['long']['A_t']:+.1f}",
    "{{long_b}}": lg(rb["long"]["B_per_yr"]), "{{long_bt}}": f"{rb['long']['B_t']:+.1f}", "{{long_day}}": rb["long"]["B_worst_days"][0][0],
    "{{c_long}}": lg(rb["tier_c"]["long_per_yr"]), "{{c_long_t}}": f"{rb['tier_c']['long_t']:.1f}", "{{c_best_p}}": f"{rb['tier_c']['best_p_fw']:.2f}",
    "{{c_top10}}": pu(rb["tier_c"]["top10_days_share"]),
    "{{mac_neg}}": str(sum(mac["inputs"][k]["on.h21"]["diff"] < 0 for k in MN)),
    "{{dollar_on}}": pc(mac["inputs"]["M4_dollar"]["on.h21"]["on_mean"], 1), "{{dollar_off}}": pc(mac["inputs"]["M4_dollar"]["on.h21"]["off_mean"], 1),
    "{{dollar_t}}": lg(mac["inputs"]["M4_dollar"]["on.h21"]["t_nw"]),
    "{{mde_near}}": f"{rb['power']['F1a.rsi11']['mde50']:.2f}", "{{mde_best}}": f"{rb['power'][best]['mde50']:.2f}",
    "{{mde_med}}": f"{rb['power_median_mde50']:.2f}",
    "{{t_fam}}": t_fam, "{{t_win}}": t_win, "{{t_mac}}": t_mac, "{{t_book}}": t_book, "{{t_gate}}": t_gate,
    "{{ch_surface}}": chart("c_surface", "Growth against the live rule, by switch window (real KMLM fund)",
                            "Log-points a year ×100; zero is the live 10-day rule. Below zero means slower growth."),
    "{{ch_surface_c}}": chart("c_surface_c", "The same surface on 2007 to 2020, where the switch reads a stand-in fund",
                              "Log-points a year ×100 against the 10-day rule. A different signal: shape only, never used to choose."),
    "{{ch_cells}}": chart("c_cells", "All 72 challengers, ranked", f"t-statistic of growth against the live rule. To count after 74 tries a bar must pass +{st['beside']['max_stat_90']:.2f}."),
    "{{ch_equity}}": chart("c_equity", "Growth of $1 (log scale)", "Simulated on the symphony's own rules, costs included. Shaded: the period where every fund is real."),
    "{{ch_dd}}": chart("c_dd", "Drawdown", "Fall from the running peak."),
    "{{ch_macro}}": chart("c_macro", "Do macro states predict the risk-on side?", "Risk-on basket (TECL and SOXL), next 21 sessions: return when the state is favourable minus when it is not. None is significant. M1 credit, M2 stress, M3 stock-bond, M4 dollar, M5 curve, M6 real rates."),
    "{{ch_book}}": chart("c_book", "At the level of the whole book", "Change in the three-engine book's yearly return, points, with 90% intervals. * chosen after the fact: illustration only.", narrow=True),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "report_body.html")).read()
BODY = BODY.replace("{{main}}", open(os.path.join(HERE, "report_main.html")).read())
ver = os.path.join(HERE, "VERIFICATION.html")
subs["{{verification}}"] = open(ver).read() if os.path.exists(ver) else "<p class='note'>Independent verification pending.</p>"
for k, v in subs.items():
    BODY = BODY.replace(k, v)
left = re.findall(r"\{\{[a-z_0-9]+\}\}", BODY)
assert not left, left
open(OUT, "w").write(BODY)
print("wrote", OUT, len(BODY) // 1024, "KB;", math.floor(len(CH)), "charts")
