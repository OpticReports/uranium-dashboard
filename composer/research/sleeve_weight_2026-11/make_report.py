"""Build the HTML report of the sleeve-weight study from out/*.json. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
S, X, RV = J("sleeve"), J("extras"), J("review")
OUT = sys.argv[1]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
lg = lambda x, d=2: f"{x:+.{d}f}"                                                          # noqa: E731
CH = {}
Q1, Q2, Q3 = S["q1"], S["q2"], S["q3"]
EN = {"E1": "1994-06 to 2002-07", "E2": "2002-08 to 2011-10", "E3": "2011-11 to 2015-05", "E4": "2015-06 to 2020-12", "E5": "2020-12 to 2023-01", "E6": "2023-02 to 2026-11"}
REALNESS = {"E1": "nothing real", "E2": "bond ETFs real; held funds rebuilt", "E3": "held funds real except LABD", "E4": "every traded fund real; KMLM signal rebuilt", "E5": "real (BOXX is T-bills)", "E6": "all real"}


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


ci = lambda v: f"{lg(v['log_per_yr_ci90'][0])} [{lg(v['log_per_yr_ci90'][1])}, {lg(v['log_per_yr_ci90'][2])}]"   # noqa: E731
cell = lambda v: f"{pc(v['cagr'])}, fall {pu(v['maxdd'])}"                                  # noqa: E731
t_eras = table(["Stretch", "What is real", "Sleeve: return a year, deepest fall", "Yearly log return [90%]", "Days out of cash", "Inverse-fund half", "Shock-ladder half"],
               [[EN[e], REALNESS[e], cell(Q1["sleeve"][e]), ci(Q1["sleeve"][e]), pu(Q1["sleeve"][e]["share_out_of_cash"]), cell(Q1["InverseHold"][e]), cell(Q1["FrontrunBonds"][e])] for e in EN])
g = X["growth"]["from_2015"]
CH["c_growth"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000],
                  "series": [{"name": "Sleeve (both halves, 50/50)", "slot": 1, "pts": g["sleeve"]}, {"name": "Shock ladder alone", "slot": 2, "pts": g["FrontrunBonds"]},
                             {"name": "Inverse-fund half alone", "slot": 3, "pts": g["InverseHold"]}]}
bf = Q1["by_fund_sum_of_daily_returns"]
t_funds = table(["Stretch", "Largest contributions"], [[EN[e], ", ".join(f"{t} {lg(v)}" for t, v in list(bf[e].items())[:5])] for e in EN])
C = X["concentration"]
t_conc = table(["Stretch", "Sleeve: total log growth", "from its 10 best days", "a year without them", "Shock ladder: total", "from its 10 best days", "a year without them"],
               [[EN[e], lg(C["sleeve"][e]["total_log"]), lg(C["sleeve"][e]["best_10_days_log"]), lg(C["sleeve"][e]["without_best_10_per_yr"]),
                 lg(C["FrontrunBonds"][e]["total_log"]), lg(C["FrontrunBonds"][e]["best_10_days_log"]), lg(C["FrontrunBonds"][e]["without_best_10_per_yr"])] for e in EN])
t_days = table(["Stretch", "The shock ladder's best days (date, return of that half, what it held)"],
               [[EN[e], "; ".join(f"{d} {pc(r)} ({', '.join(h)})" for d, r, h in X["top_days"][e][:5])] for e in ("E4", "E5", "E6")])
hc = lambda h: f"{pc(h['sleeve_on_worst'], 2)} vs {pc(h['sleeve_on_other_days'], 2)} (t {h['t']:+.1f})"   # noqa: E731
t_hedge = table(["Stretch", "Sleeve on the worst days of both together vs its other days", "Sleeve on Holy Grail's worst days", "Inverse-fund half on Holy Grail's worst days", "Shock ladder on both together"],
                [[EN[e], hc(Q2[e]["sleeve"]["pair"]), hc(Q2[e]["sleeve"]["HG"]), hc(Q2[e]["InverseHold"]["HG"]), hc(Q2[e]["FrontrunBonds"]["pair"])] for e in EN if e in Q2])
WS = ["0.000", "0.100", "0.200", "0.318", "0.400", "0.500"]
WL = ["0%", "10%", "20%", "31.8%", "40%", "50%"]
ST = (("E4", "2015-06 to 2020-12", 1), ("real_2021_06_on", "2021-06 to 2026-11", 2), ("long_1994_2020", "1994-06 to 2020-12 (mostly rebuilt)", 3))
for cid, key, fmt in (("c_cagr", "cagr", "pct0"), ("c_dd", "maxdd", "pct0")):
    ser = []
    for e, nm, slot in ST[:2]:
        ser.append({"name": f"Sleeve as third leg, {nm}", "slot": slot, "pts": [[i, Q3[e]["by_weight"][wt]["sleeve"][key]] for i, wt in enumerate(WS)]})
    CH[cid] = {"type": "line", "yfmt": fmt, "xnum": True, "xlabels": WL, "xunit": " in the third leg", "zero": key == "maxdd", "series": ser}
ser = []
for e, nm, slot in ST[:2]:
    ser.append({"name": f"Sleeve, {nm}", "slot": slot, "pts": [[i, Q3[e]["by_weight"][wt]["sleeve"]["maxdd"]] for i, wt in enumerate(WS)]})
ser.append({"name": "T-bills instead, 2021-06 to 2026-11", "slot": 3, "pts": [[i, Q3["real_2021_06_on"]["by_weight"][wt]["tbills"]["maxdd"]] for i, wt in enumerate(WS)]})
CH["c_dd"]["series"] = ser
CH["c_cagr"]["series"].append({"name": "T-bills instead, 2021-06 to 2026-11", "slot": 3, "pts": [[i, Q3["real_2021_06_on"]["by_weight"][wt]["tbills"]["cagr"]] for i, wt in enumerate(WS)]})
bw = lambda e, wt, k: Q3[e]["by_weight"][wt][k]                                            # noqa: E731
t_weight = table(["Third-leg weight"] + [f"{nm}: sleeve | T-bills" for _, nm, _ in ST],
                 [[WL[i]] + [f"{pc(bw(e, wt, 'sleeve')['cagr'])}, fall {pu(bw(e, wt, 'sleeve')['maxdd'])}, Sharpe {bw(e, wt, 'sleeve')['sharpe']:.2f} | {pc(bw(e, wt, 'tbills')['cagr'])}, fall {pu(bw(e, wt, 'tbills')['maxdd'])}" for e, _, _ in ST]
                  for i, wt in enumerate(WS)])
SN = {"E1": EN["E1"], "E2": EN["E2"], "E3": EN["E3"], "E4": EN["E4"], "E5b": "2021-06 to 2023-01", "E6": EN["E6"], "real_2021_06_on": "2021-06 to 2026-11 (both)", "long_1994_2020": "1994-06 to 2020-12 (all)"}
tt = lambda v: f"{lg(v['dlog_per_yr'], 3)} [{lg(v['ci90'][0], 3)}, {lg(v['ci90'][1], 3)}]"   # noqa: E731
t_test = table(["Stretch", "Sleeve vs T-bills at 31.8%: book growth, log-pts/yr [90%]", "Deepest fall, change", "Paths with the smaller fall", "Earns it?", "Sleeve at 31.8% vs no third leg: growth", "Deepest fall, change"],
               [[SN[e], tt(Q3[e]["vs_tbills"]), f"{Q3[e]['vs_tbills']['d_maxdd'] * 100:+.1f} pts", pu(Q3[e]["vs_tbills"]["share_of_paths_sleeve_fall_smaller"]), "yes" if Q3[e]["vs_tbills"]["earns_it"] else "no",
                 tt(Q3[e]["vs_no_third_leg"]), f"{Q3[e]['vs_no_third_leg']['d_maxdd'] * 100:+.1f} pts"] for e in SN if e in Q3])
ev = Q1["E4_variants"]
rv = [v["cagr"] for v in ev.values()]
R = Q3["real_2021_06_on"]
e4w = X["E4_without"]
c3 = lambda v: f"{lg(v[0])} [{lg(v[1])}, {lg(v[2])}]"                                      # noqa: E731
TL = RV["third_leg"]
vs = lambda v: f"{lg(v['dlog_per_yr'], 3)} [{lg(v['ci90'][0], 3)}, {lg(v['ci90'][1], 3)}]"   # noqa: E731
bk = lambda v: f"{pc(v['cagr'])}, fall {pu(v['maxdd'], 1)}"                                # noqa: E731
t_third = table(["Third leg at 31.8%"] + [f"{e}: book | growth against T-bills [90%]" for e in TL],
                [[nm] + [f"{bk(TL[e]['book_stats'][k])} | {vs(TL[e][k + '_vs_tbills'])}" for e in TL] for k, nm in (("sleeve", "Live sleeve"), ("ladder", "Shock ladder alone"), ("inverse", "Inverse-fund half alone"))]
                + [["T-bills"] + [f"{bk(TL[e]['book_stats']['tbills'])} | (the control)" for e in TL]])
rt = RV["rare_tests"]
sd = RV["single_days"]["2023-02 on without 2024-08-05"]
E4K, RK = "2015-06 to 2020-12", "2021-06 to 2026-11"
subs = {
    "{{e4_cagr}}": pc(Q1["sleeve"]["E4"]["cagr"]), "{{e6_cagr}}": pc(Q1["sleeve"]["E6"]["cagr"]), "{{e4_dd}}": pu(Q1["sleeve"]["E4"]["maxdd"]),
    "{{e4_ci}}": ci(Q1["sleeve"]["E4"]), "{{real_ci}}": ci(Q1["real_years_from_2020_12"]),
    "{{e3_fb_wo}}": pc(RV["single_days"]["2011-11 to 2015-05 without 2011-11-01"]["ladder"]["without"]), "{{e3_sl_wo}}": pc(RV["single_days"]["2011-11 to 2015-05 without 2011-11-01"]["sleeve"]["without"]),
    "{{vt_10_50}}": "; ".join(f"{e}: {vs(TL[e]['sleeve_vs_tbills_at_10pct'])} and {vs(TL[e]['sleeve_vs_tbills_at_50pct'])}" for e in (E4K, RK)), "{{e4x_ci}}": c3(RV["e4_log_per_yr"]["without_2020_02_to_04"]),
    "{{t_var_inline}}": "; ".join(f"{k} {pc(v['cagr'])}, fall {pu(v['maxdd'])}" for k, v in ev.items()),
    "{{top_share}}": pu(C["sleeve"]["E4"]["best_10_days_log"] / C["sleeve"]["E4"]["total_log"]),
    "{{e4_wo}}": pc(e4w["sleeve"]["without 2020-02..04"]["cagr"]),
    "{{fb_txt}}": ", ".join(f"{pc(Q1['FrontrunBonds'][e]['cagr'])} a year in {EN[e][:4]}-{EN[e][-7:-3]}" for e in ("E3", "E4", "E5", "E6")),
    "{{tlt_up_n}}": str(len(rt["TLT_1d_above_6pct"])), "{{tlt_dn_n}}": str(len(rt["TLT_1d_below_minus_3.5pct"])), "{{tlt_dn_2020}}": str(sum(d.startswith("2020-03") for d in rt["TLT_1d_below_minus_3.5pct"])),
    "{{d0805}}": pc(sd["ladder"]["that_day"]), "{{e6_wo}}": pc(sd["sleeve"]["without"]),
    "{{ih_real}}": f"{pc(Q1['InverseHold']['E5']['cagr'])} then {pc(Q1['InverseHold']['E6']['cagr'])} a year",
    "{{ih_before}}": f"{pc(Q1['InverseHold']['E3']['cagr'])} a year in 2011-2015, {pc(Q1['InverseHold']['E4']['cagr'])} in 2015-2020",
    "{{vt_e4}}": lg(Q3["E4"]["vs_tbills"]["dlog_per_yr"]), "{{vt_real}}": lg(R["vs_tbills"]["dlog_per_yr"]),
    "{{vt_dd}}": f"{Q3['E4']['vs_tbills']['d_maxdd'] * 100:+.1f} and {R['vs_tbills']['d_maxdd'] * 100:+.1f} points",
    "{{w0_real}}": pc(bw("real_2021_06_on", "0.000", "sleeve")["cagr"]), "{{w318_real}}": pc(bw("real_2021_06_on", "0.318", "sleeve")["cagr"]),
    "{{dd0_real}}": pu(bw("real_2021_06_on", "0.000", "sleeve")["maxdd"]), "{{dd318_real}}": pu(bw("real_2021_06_on", "0.318", "sleeve")["maxdd"]),
    "{{la_e3}}": vs(TL["2011-11 to 2015-05"]["ladder_alone_vs_live_sleeve"]), "{{la_e4}}": vs(TL[E4K]["ladder_alone_vs_live_sleeve"]), "{{la_real}}": vs(TL[RK]["ladder_alone_vs_live_sleeve"]),
    "{{t_third}}": t_third,
    "{{t_eras}}": t_eras, "{{t_funds}}": t_funds, "{{t_conc}}": t_conc, "{{t_days}}": t_days, "{{t_hedge}}": t_hedge, "{{t_weight}}": t_weight, "{{t_test}}": t_test,
    "{{t_open}}": table(["Priority", "Question", "What it would move", "Status"], [
        ["P1", "Owner: is the book's deepest fall or its growth the binding constraint? (a third leg trades one for the other)", "The third leg's weight; this study cannot choose it", "asked 2026-11-21"],
        ["P1", "Owner: keep the inverse-fund half? It lost on real funds 2011-2020 and has paid since 2020-12", "Half the sleeve; both brokers and the logic book if changed", "asked 2026-11-21"],
        ["P2", "Were the ladder's thresholds fitted on March 2020? (when and on what data the two community strategies were tuned)", "Whether 2015-2020 counts as out of sample for the ladder", "open, first asked 2026-11-21"],
        ["P2", "Rebuild UVXY and SVXY for 2006-2011 from the published VIX futures index", "The only real-bond-fund years that could test the ladder outside its fitted period", "open, first asked 2026-11-21"],
        ["P2", "Paper-track every ladder trigger from here, with the live fill against the close", "Whether the ladder catches shocks it was not built on, and at what price", "open, first asked 2026-11-21"],
        ["P3", "Sensitivity to deciding at 15:51 rather than the close on shock days", "How much of the simulated ladder return is reachable", "open, first asked 2026-11-21"]]),
    "{{ch_growth}}": chart("c_growth", "The sleeve and its two halves since every traded fund is real", "Growth of $1 from 2015-06 (log scale), simulated, each half run as its own tree."),
    "{{ch_cagr}}": chart("c_cagr", "Book return a year by third-leg weight", "The rest is split equally between Holy Grail and KMLM. More third leg, less growth."),
    "{{ch_dd}}": chart("c_dd", "Book's deepest fall by third-leg weight", "More third leg, smaller fall; T-bills cut it a little more than the sleeve does."),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Sleeve Weight Study</title>"),
             ("const yt=c.log?[.25,.5,1,2,4,8,16,32].filter(", "const yt=c.log?(c.logticks||[.25,.5,1,2,4,8,16,32]).filter(")):
    assert a in BODY, a
    BODY = BODY.replace(a, b)
BODY = BODY.replace("{{main}}", open(os.path.join(HERE, "report_main.html")).read())
ver = os.path.join(HERE, "VERIFICATION.html")
subs["{{verification}}"] = open(ver).read() if os.path.exists(ver) else "<p class='note'>Independent verification in progress.</p>"
for k, v in subs.items():
    BODY = BODY.replace(k, v)
left = re.findall(r"\{\{[a-z_0-9]+\}\}", BODY)
assert not left, left
open(OUT, "w").write(BODY)
print("wrote", OUT, len(BODY) // 1024, "KB;", len(CH), "charts")
