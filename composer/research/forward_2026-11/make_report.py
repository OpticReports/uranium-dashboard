"""Build the HTML report of the forward-range study from out/forward.json. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(HERE, "out", "forward.json")))
OUT = sys.argv[1]
MC, FAN, SIDE, HIST, DEF, LIVE = F["mc"], F["fan"], F["side"], F["hist"], F["deflated"], F["live"]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
mult = lambda v: f"{v:,.0f}x" if v >= 100 else f"{v:.1f}x" if v >= 10 else f"{v:.2f}x"     # noqa: E731
CH = {}
SN = {"A": "As simulated, 2021-06 on", "B": "As simulated, 2015-06 on", "C": "As simulated, 1994 on", "D": "Half the edge", "E": "A quarter of the edge", "F": "One close late", "G": "Low-return decade for stocks"}
KIND = {"A": "ceiling", "B": "ceiling", "C": "ceiling", "D": "planning", "E": "planning", "F": "bound", "G": "planning"}
WS = ["0.000", "0.100", "0.200", "0.318", "0.400", "0.500"]
WL = ["0%", "10%", "20%", "31.8%", "40%", "50%"]
HN = {"1y": "1 year", "5y": "5 years", "10y": "10 years"}
EN = {"HG": "Holy Grail", "KMLM": "KMLM", "SLEEVE": "Sleeve"}
ORDER = ["A", "B", "C", "G", "D", "E", "F"]


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


T = "0.318"
rng3 = lambda v, k="per_yr": f"{pc(v[k]['5'])} / <b>{pc(v[k]['50'])}</b> / {pc(v[k]['95'])}"   # noqa: E731
m3 = lambda v: f"{mult(v['multiple']['5'])} / <b>{mult(v['multiple']['50'])}</b> / {mult(v['multiple']['95'])}"   # noqa: E731
t_today = table(["Scenario", "Kind", "Horizon", "Return a year: 5th / median / 95th", "$1 becomes: 5th / median / 95th", "Chance of ending below the start", "Deepest fall on the way: median / 1-in-20",
                 "Chance of a fall deeper than 30%"],
                [[SN[s] if h == "1y" else "", KIND[s] if h == "1y" else "", HN[h], rng3(MC[s][T][h]), m3(MC[s][T][h]), pu(MC[s][T][h]["p_below_start"], 1), f"{pu(MC[s][T][h]['maxdd_median'])} / {pu(MC[s][T][h]['maxdd_p95'])}",
                  pu(MC[s][T][h]["p_fall_deeper"]["30"])] for s in ORDER for h in HN])
yr = lambda fan: [[0, 1.0]] + [[i + 1, row[3]] for i, row in enumerate(fan[11::12])]       # noqa: E731  (median, yearly)
XL = ["now"] + [f"{i}y" for i in range(1, 11)]
CH["c_med"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.5, 1, 2, 5, 10, 30, 100, 300, 1000, 3000, 10000], "xnum": True, "xlabels": XL, "xunit": "",
               "series": [{"name": SN[s], "slot": i + 1, "pts": yr(FAN[f"{s}.{T}"])} for i, s in enumerate(["B", "G", "D", "E", "F"])]}
fanD = FAN[f"D.{T}"]
CH["c_fan"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.25, 0.5, 1, 2, 5, 10, 30, 100, 300, 1000], "xnum": True, "xlabels": XL, "xunit": "",
               "series": [{"name": nm, "slot": sl, "pts": [[0, 1.0]] + [[i + 1, row[k]] for i, row in enumerate(fanD[11::12])]} for nm, sl, k in
                          (("95th percentile", 3, 5), ("75th", 2, 4), ("Median", 1, 3), ("25th", 2, 2), ("5th percentile", 3, 1))]}
fanE = FAN[f"E.{T}"]
CH["c_fanE"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.25, 0.5, 1, 2, 5, 10, 30, 100], "xnum": True, "xlabels": XL, "xunit": "",
                "series": [{"name": nm, "slot": sl, "pts": [[0, 1.0]] + [[i + 1, row[k]] for i, row in enumerate(fanE[11::12])]} for nm, sl, k in
                           (("95th percentile", 3, 5), ("75th", 2, 4), ("Median", 1, 3), ("25th", 2, 2), ("5th percentile", 3, 1))]}


def by_weight(h):
    rows = []
    for s in ORDER:
        rows.append([f"<b>{SN[s]}</b>: median return a year"] + [pc(MC[s][wt][h]["per_yr"]["50"]) for wt in WS])
        rows.append(["&nbsp;&nbsp;1-in-20 bad outcome, return a year"] + [pc(MC[s][wt][h]["per_yr"]["5"]) for wt in WS])
        rows.append(["&nbsp;&nbsp;deepest fall, median / 1-in-20"] + [f"{pu(MC[s][wt][h]['maxdd_median'])} / {pu(MC[s][wt][h]['maxdd_p95'])}" for wt in WS])
        rows.append(["&nbsp;&nbsp;chance of a fall deeper than 30%"] + [pu(MC[s][wt][h]["p_fall_deeper"]["30"]) for wt in WS])
        rows.append(["&nbsp;&nbsp;chance of ending below the start"] + [pu(MC[s][wt][h]["p_below_start"], 1) for wt in WS])
    return table(["Sleeve weight"] + WL, rows)


CS = ["B", "G", "D", "E", "F"]
CH["c_w_ret"] = {"type": "line", "yfmt": "pct0", "xnum": True, "xlabels": WL, "xunit": " sleeve", "zero": True,
                 "series": [{"name": SN[s], "slot": i + 1, "pts": [[j, MC[s][wt]["10y"]["per_yr"]["50"]] for j, wt in enumerate(WS)]} for i, s in enumerate(CS)]}
CH["c_w_dd"] = {"type": "line", "yfmt": "pct0", "xnum": True, "xlabels": WL, "xunit": " sleeve", "zero": True,
                "series": [{"name": SN[s], "slot": i + 1, "pts": [[j, MC[s][wt]["10y"]["maxdd_p95"]] for j, wt in enumerate(WS)]} for i, s in enumerate(CS)]}
CH["c_w_bad"] = {"type": "line", "yfmt": "pct0", "xnum": True, "xlabels": WL, "xunit": " sleeve", "zero": True,
                 "series": [{"name": SN[s], "slot": i + 1, "pts": [[j, MC[s][wt]["5y"]["per_yr"]["5"]] for j, wt in enumerate(WS)]} for i, s in enumerate(CS)]}
DR = "0.318.daily_reset"
t_drift = table(["Scenario", "Deepest fall in 10 years, weights drift (as run): median / 1-in-20", "Same, reset to target daily (earlier studies): median / 1-in-20", "Median return a year: drift / daily reset", "Cap resets a year"],
                [[SN[s], f"{pu(MC[s][T]['10y']['maxdd_median'])} / {pu(MC[s][T]['10y']['maxdd_p95'])}", f"{pu(MC[s][DR]['10y']['maxdd_median'])} / {pu(MC[s][DR]['10y']['maxdd_p95'])}",
                  f"{pc(MC[s][T]['10y']['per_yr']['50'])} / {pc(MC[s][DR]['10y']['per_yr']['50'])}", f"{MC[s][T]['10y']['resets_per_yr']:.1f}"] for s in ORDER])
t_hist = table(["Source", "Sessions", "Sleeve weight", "Return a year", "Deepest fall", "Sharpe", "Volatility"],
               [[SN[s] if wt == "0.000" else "", HIST[s][wt]["n"] if wt == "0.000" else "", WL[WS.index(wt)], pc(HIST[s][wt]["cagr"]), pu(HIST[s][wt]["maxdd"], 1), f"{HIST[s][wt]['sharpe']:.2f}", pu(HIST[s][wt]["vol"])]
                for s in ORDER for wt in ("0.000", "0.318", "0.500")])
t_def = table(["Source", "Sleeve weight", "Simulated Sharpe", "Best of 10 unskilled tries would show", "of 100", "of 1,000", "Chance the simulated Sharpe beats the best of 1,000"],
              [[SN[s], WL[WS.index(wt)], f"{v['sharpe']:.2f}", f"{v['10']['expected_best_of_unskilled']:.2f}", f"{v['100']['expected_best_of_unskilled']:.2f}", f"{v['1000']['expected_best_of_unskilled']:.2f}",
                "&gt;99.9%" if v["1000"]["prob_observed_beats_it"] > 0.999 else pu(v["1000"]["prob_observed_beats_it"], 1)] for s in ("A", "B", "C") for wt, v in DEF[s].items()])
EK = ("HG", "KMLM", "SLEEVE")
t_beta = table(["Engine", "Beta to the S&P 500, 2015-06 on", "Mean return over T-bills a year", "of which beta x the S&P's", "Lowered by, in the low-return decade", "Beta, 1994 on"],
               [[EN[e], f"{SIDE['beta_B'][i]:+.2f}", pc(SIDE["engine_mean_over_tbills_per_yr_B"][i]),
                 pu(SIDE["beta_B"][i] * (SIDE["spx_growth_per_yr_B"] - SIDE["tbill_per_yr_B"]) / SIDE["engine_mean_over_tbills_per_yr_B"][i]), f"{SIDE['g_shift_per_yr'][i] * 100:.1f} points a year", f"{SIDE['beta_C'][i]:+.2f}"]
                for i, e in enumerate(EK)])
t_live = table(["Symphony", "Live from", "to", "Sessions", "Live return", "Simulated, same dates", "Deepest live fall"],
               [[EN[e], v["from"], v["to"], v["sessions"], pc(v["live_return"], 1), pc(v["simulated_return_same_dates"], 1), pu(v["live_deepest_fall"], 1)] for e, v in LIVE.items()])
t_scen = table(["Scenario", "Kind", "Draws from", "What it assumes", "Evidence behind it"], [
    [SN["A"], "ceiling", "2021-06 to 2026-11", "the all-real simulated years repeat", "in-sample backtest"],
    [SN["B"], "ceiling", "2015-06 to 2026-11", "the simulated years since every traded fund is real repeat (has 2018, 2020, 2022)", "in-sample backtest; KMLM fund rebuilt before 2021"],
    [SN["C"], "ceiling", "1994-06 to 2026-11", "the whole rebuilt history repeats (adds 2000-02, 2007-09)", "shape only before 2015"],
    [SN["G"], "planning", "2015-06 on, shifted", "stocks return 2% a year for a decade; each engine loses its beta times the shortfall", "published 10-year S&P estimates of -0.7% to +6.5% (addendum 13)"],
    [SN["D"], "planning", "2015-06 on, shifted", "each engine keeps half its simulated return over T-bills; same volatility", "strategies lose about half their return after discovery ({{cite_d}})"],
    [SN["E"], "planning", "2015-06 on, shifted", "each engine keeps 27% of it", "{{cite_e}}"],
    [SN["F"], "bound", "2015-06 on, late paths", "every trade fills one close late, forever", "addendum 61; live fills have not been there (addendum 14b)"]])
v = lambda s, h="10y", wt=T: MC[s][wt][h]                                                  # noqa: E731
plan = ("G", "D", "E")
lo_s = min(plan, key=lambda s: v(s)["per_yr"]["50"])
hi_s = max(plan, key=lambda s: v(s)["per_yr"]["50"])
subs = {
    "{{t_scen}}": t_scen, "{{t_today}}": t_today, "{{t_w10}}": by_weight("10y"), "{{t_w5}}": by_weight("5y"), "{{t_w1}}": by_weight("1y"), "{{t_drift}}": t_drift, "{{t_hist}}": t_hist, "{{t_def}}": t_def,
    "{{t_beta}}": t_beta, "{{t_live}}": t_live,
    "{{plan_lo}}": pc(v(lo_s)["per_yr"]["50"]), "{{plan_hi}}": pc(v(hi_s)["per_yr"]["50"]), "{{plan_lo_name}}": SN[lo_s].lower(), "{{plan_hi_name}}": SN[hi_s].lower(),
    "{{plan_1y}}": " to ".join(sorted((pc(v(s, "1y")["per_yr"]["50"]) for s in (lo_s, hi_s)), key=lambda z: float(z[:-1]))),
    "{{plan_1y_bad}}": " to ".join(sorted((pc(v(s, "1y")["per_yr"]["5"]) for s in plan), key=lambda z: float(z[:-1]))[::2]),
    "{{plan_5y}}": " to ".join(sorted((pc(v(s, "5y")["per_yr"]["50"]) for s in (lo_s, hi_s)), key=lambda z: float(z[:-1]))),
    "{{ceil_10}}": pc(v("B")["per_yr"]["50"]), "{{ceil_a}}": pc(v("A")["per_yr"]["50"]), "{{ceil_c}}": pc(v("C")["per_yr"]["50"]),
    "{{f_10}}": pc(v("F")["per_yr"]["50"]), "{{f_dd}}": pu(v("F")["maxdd_median"]),
    "{{dd_plan}}": " to ".join(sorted((pu(v(s)["maxdd_median"]) for s in plan))[::2]), "{{dd_plan95}}": " to ".join(sorted((pu(v(s)["maxdd_p95"]) for s in plan))[::2]),
    "{{p30_plan}}": " to ".join(sorted((pu(v(s)["p_fall_deeper"]["30"]) for s in plan), key=lambda z: float(z[:-1]))[::2]),
    "{{p30_1y}}": " to ".join(sorted((pu(v(s, "1y")["p_fall_deeper"]["30"]) for s in plan), key=lambda z: float(z[:-1]))[::2]),
    "{{ploss_1y}}": " to ".join(sorted((pu(v(s, "1y")["p_below_start"]) for s in plan), key=lambda z: float(z[:-1]))[::2]),
    "{{ploss_5y}}": " to ".join(sorted((pu(v(s, "5y")["p_below_start"], 1) for s in plan), key=lambda z: float(z[:-1]))[::2]),
    "{{drift_dd}}": f"{pu(v('B')['maxdd_median'])} against {pu(MC['B'][DR]['10y']['maxdd_median'])}", "{{drift_dd95}}": f"{pu(v('B')['maxdd_p95'])} against {pu(MC['B'][DR]['10y']['maxdd_p95'])}",
    "{{resets}}": f"{v('B')['resets_per_yr']:.1f}",
    "{{spx_b}}": pc(SIDE["spx_growth_per_yr_B"], 1), "{{paths}}": f"{F['meta']['paths']:,}", "{{block}}": str(F["meta"]["block"]),
    "{{ch_med}}": chart("c_med", "Today's book (31.8% sleeve): the median path in each scenario", "Growth of $1 over ten years, log scale. Half of the drawn paths end above each line and half below. Ceilings A and C are left off; they sit around the top line."),
    "{{ch_fan}}": chart("c_fan", "Today's book under \"half the edge\": the spread of outcomes", "Growth of $1, log scale. Nine in ten drawn paths end between the outer lines."),
    "{{ch_fanE}}": chart("c_fanE", "Today's book under \"a quarter of the edge\": the spread of outcomes", "Growth of $1, log scale."),
    "{{ch_w_ret}}": chart("c_w_ret", "Median return a year over ten years, by sleeve weight", "More sleeve, less return in every scenario where the engines keep an edge."),
    "{{ch_w_bad}}": chart("c_w_bad", "A 1-in-20 bad five years, by sleeve weight", "Return a year at the 5th percentile after five years."),
    "{{ch_w_dd}}": chart("c_w_dd", "A 1-in-20 deepest fall within ten years, by sleeve weight", "More sleeve, smaller fall in every scenario."),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Forward Ranges</title>"),
             ("const yt=c.log?[.25,.5,1,2,4,8,16,32].filter(", "const yt=c.log?(c.logticks||[.25,.5,1,2,4,8,16,32]).filter("),
             ('if(f==="mult")return (v>=10?v.toFixed(0):v.toFixed(2))+"×"',
              'if(f==="mult")return (v>=1e9?(v/1e9).toFixed(0)+"B":v>=1e6?(v/1e6).toFixed(0)+"M":v>=1e3?(v/1e3).toFixed(0)+"k":v>=10?v.toFixed(0):v.toFixed(2))+"×"')):
    assert a in BODY, a
    BODY = BODY.replace(a, b)
BODY = BODY.replace("{{main}}", open(os.path.join(HERE, "report_main.html")).read())
ver = os.path.join(HERE, "VERIFICATION.html")
subs["{{verification}}"] = open(ver).read() if os.path.exists(ver) else "<p class='note'>Independent verification in progress.</p>"
subs["{{charts}}"] = json.dumps(CH, separators=(",", ":"))
CITE = json.load(open(os.path.join(HERE, "citations.json"))) if os.path.exists(os.path.join(HERE, "citations.json")) else {"cite_d": "McLean and Pontiff 2016; Harvey and Liu 2015", "cite_e": "Suhonen, Lennkh and Perez 2017: median 73% fall in Sharpe from backtest to live, 215 bank strategies"}
for _ in range(2):
    for k, val in list(subs.items()) + [("{{" + k + "}}", x) for k, x in CITE.items()]:
        BODY = BODY.replace(k, str(val))
left = re.findall(r"\{\{[a-z_0-9]+\}\}", BODY)
assert not left, left
open(OUT, "w").write(BODY)
print("wrote", OUT, len(BODY) // 1024, "KB;", len(CH), "charts; planning range", lo_s, hi_s)
