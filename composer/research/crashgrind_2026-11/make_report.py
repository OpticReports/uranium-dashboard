"""Build the HTML report of the crash-against-grind study from out/*.json. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
FI, EN, CG, TD = J("fidelity"), J("engines"), J("crashgrind"), J("today")
OUT = sys.argv[1]
lg = lambda x, d=3: "n/a" if x is None else f"{x:+.{d}f}"                                  # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pv = lambda p: "n/a" if p is None else ("&lt;0.001" if p < 0.0005 else f"{p:.3f}" if p < 0.1 else f"{p:.2f}")   # noqa: E731
CH = {}
DN = {"D1": "Speed: S&P down more than 10% in 10 sessions", "D2": "VIX above VIX3M", "D3": "VIX above 40", "D4": "Front VIX future above the second"}
BN = {"B1": "far below its 50-day average", "B2": "far below its 20-day average", "B3": "below its 200-day average"}


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


SY, MO = FI["synthetic"], FI["model"]
BAR = FI["bars"]
yn = lambda b: "met" if b else "MISSED"                                                    # noqa: E731
t_fid = table(["Fund", "Sessions", "Daily correlation: rebuilt | old model", "Two-day | five-day (rebuilt)", "Growth a year less the real fund's: rebuilt | old model", "Worst calendar year: rebuilt | old model",
               "Of the 20 biggest real moves, within 0.8 to 1.25 x: rebuilt | old model"],
              [[nm, f"{SY[nm]['n']:,}", f"{SY[nm]['corr']:.3f} | {MO[nm]['corr']:.3f}", f"{SY[nm]['multi_day_corr']['2']:.3f} | {SY[nm]['multi_day_corr']['5']:.3f}",
                f"{lg(SY[nm]['log_gap_per_yr'])} | {lg(MO[nm]['log_gap_per_yr'])}", f"{SY[nm]['worst_year_gap'][0]} {lg(SY[nm]['worst_year_gap'][1], 2)} | {MO[nm]['worst_year_gap'][0]} {lg(MO[nm]['worst_year_gap'][1], 2)}",
                f"{SY[nm]['top20_within']} | {MO[nm]['top20_within']}"] for nm in ("VIXY", "UVXY", "SVXY")])
A5 = EN["A5"]
t_bars = table(["Bar set in advance", "Result", ""], [
    ["A1 VIXY daily correlation at least 0.98", f"{SY['VIXY']['corr']:.3f}", yn(BAR["A1"])],
    ["A2 VIXY growth a year within 0.03 overall and 0.06 in every year", f"{lg(SY['VIXY']['log_gap_per_yr'])}; worst year {lg(SY['VIXY']['worst_year_gap'][1], 3)}", yn(BAR["A2"])],
    ["A3 UVXY and SVXY correlation at least 0.97, growth within 0.08", f"{SY['UVXY']['corr']:.3f} and {SY['SVXY']['corr']:.3f}; {lg(SY['UVXY']['log_gap_per_yr'])} and {lg(SY['SVXY']['log_gap_per_yr'])}", yn(BAR["A3"])],
    ["A4 at least 17 of the 20 biggest VIXY moves within 0.8 to 1.25 x", f"{SY['VIXY']['top20_within']} of 20", yn(BAR["A4"])],
    ["A5 sleeve on rebuilt funds, 2011-11 to 2020-11: same holdings on 95% of sessions, growth within 10%", f"{pu(A5['same_holdings'], 1)} of sessions; growth {A5['log_growth_rebuilt_funds']:.2f} against {A5['log_growth_real_funds']:.2f} log-points ({pu(A5['ratio'])})", yn(A5["pass"])]])
cv = SY["VIXY"]["curve"]
CH["c_fid"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 0.01, 0.1, 1], "series": [{"name": "VIXY rebuilt from futures settlements", "slot": 1, "pts": [[d, a] for d, a, b in cv]},
                                                                                                                         {"name": "VIXY, the real fund", "slot": 2, "pts": [[d, b] for d, a, b in cv]}]}
yrs = [str(y) for y in range(2006, 2012)]
t_eng = table(["Year", "Sleeve: old model", "Sleeve: funds rebuilt from futures", "of which the shock ladder alone (rebuilt)", "Sleeve at today's fund leverage (rebuilt)", "Holy Grail: old | rebuilt"],
              [[y, lg(EN["SLEEVE"]["log_growth_by_year_old_new"][y][0], 2), lg(EN["SLEEVE"]["log_growth_by_year_old_new"][y][1], 2), lg(EN["FrontrunBonds"]["by_year_new"].get(y), 2),
                lg(TD["log_growth_by_year"].get(y), 2), f"{lg(EN['HG']['log_growth_by_year_old_new'][y][0], 2)} | {lg(EN['HG']['log_growth_by_year_old_new'][y][1], 2)}"] for y in yrs])
EP = [e for e in CG["episodes"]["B1"] if e["washed_out_days"] >= 15]
fl = lambda e, k: "n/a" if e["flags"][k] is None else pu(e["flags"][k])                    # noqa: E731
crash = lambda e: (e["flags"]["D1"] or 0) >= 0.5                                           # noqa: E731
t_ep = table(["Washed-out episode", "Days", "Depth from the year's high", "Fastest 10-session fall", "Speed", "VIX over VIX3M", "VIX over 40", "Futures inverted", "Sleeve", "Other two engines", "Sleeve less others",
              "One close late: sleeve | others", "Sleeve at today's leverage"],
             [[f"{e['from']} to {e['to']}", e["washed_out_days"], pc(e["depth_from_252d_high"]), pc(e["fastest_10_session_fall"]), fl(e, "D1"), fl(e, "D2"), fl(e, "D3"), fl(e, "D4"), lg(e["sleeve"], 2), lg(e["others"], 2),
               ("<b>%s</b>" if e["sleeve"] > e["others"] else "%s") % lg(e["sleeve"] - e["others"], 2), f"{lg(e['sleeve_late'], 2)} | {lg(e['others_late'], 2)}", lg(e["sleeve_today_leverage"], 2)] for e in EP])
CH["c_ep"] = {"type": "bars", "yfmt": "raw", "every": 1, "cats": [f"{e['from']} to {e['to']}" + (" (fast)" if crash(e) else "") for e in EP], "short": [e["from"][:7] + ("*" if crash(e) else "") for e in EP],
              "vals": [e["sleeve"] - e["others"] for e in EP]}
fast = [e for e in EP if crash(e)]
n_fast, n_fast_win = len(fast), sum(e["sleeve"] > e["others"] for e in fast)
slow = [e for e in EP if not crash(e)]
n_slow_win = sum(e["sleeve"] > e["others"] for e in slow)
DAY, POL = CG["day"], CG["policy"]
SK = list(DAY["B1.D1"])
drow = lambda key, sk: (lambda r: [r["washed_out_days"], r["crash_flagged"]] + ([f"{r['same']['spread_crash_per_day'] * 100:+.2f}% | {r['same']['spread_grind_per_day'] * 100:+.2f}%", pv(r["same"]["p"]),   # noqa: E731
                                                                                 f"{r['late']['spread_crash_per_day'] * 100:+.2f}% | {r['late']['spread_grind_per_day'] * 100:+.2f}%"] if "same" in r else ["too few", "", ""]))(DAY[key][sk])
t_day = table(["Crash reading (washed out = " + BN["B1"] + ")", "Stretch", "Washed-out days", "of which flagged", "Sleeve less the other two, a day: flagged | not", "p", "One close late: flagged | not"],
              [[DN[k] if i == 0 else "", sk] + drow(f"B1.{k}", sk) for k in ("D1", "D2", "D3", "D4") for i, sk in enumerate(SK)])
prow = lambda key, sk: (lambda p: [lg(p["same"]["d_growth"]), pv(p["same"]["p"]), f"{p['same']['d_maxdd'] * 100:+.1f}", lg(p["late"]["d_growth"]), lg(p["same"]["crash_only"]), lg(p["same"]["grind_only"]),   # noqa: E731
                                   lg(p["same"]["all_washed_out_low"])])(POL[key][sk])
t_pol = table(["Crash reading", "Stretch", "Three-level policy: growth vs constant book", "p", "Deepest fall, points", "One close late", "Only the crash step (50% when flagged)", "Only the grind step (15% when not flagged)",
               "No reading: 15% on every washed-out day"],
              [[DN[k] if i == 0 else "", sk] + prow(f"B1.{k}", sk) for k in ("D1", "D2") for i, sk in enumerate(SK)])
t_other = table(["Washed-out state", "Crash reading", "Without 2020: sleeve less others a day, flagged | not", "p", "Three-level policy without 2020", "No reading, without 2020"],
                [[BN[b], DN[k]] + (lambda r, p: [f"{r['same']['spread_crash_per_day'] * 100:+.2f}% | {r['same']['spread_grind_per_day'] * 100:+.2f}%", pv(r["same"]["p"]), lg(p["same"]["d_growth"]),
                                                 lg(p["same"]["all_washed_out_low"])])(DAY[f"{b}.{k}"]["all, without 2020"], POL[f"{b}.{k}"]["all, without 2020"]) for b in ("B1", "B2", "B3") for k in ("D1", "D2", "D3", "D4")])
W20 = "all, without 2020"
d1, d2 = DAY["B1.D1"][W20]["same"], DAY["B1.D2"][W20]["same"]
e08 = next(e for e in EP if e["from"].startswith("2008-09"))
e20 = next(e for e in EP if e["from"].startswith("2020-02"))
e11 = next(e for e in EP if e["from"].startswith("2011-08"))
un = lambda sk: lg(POL["B1.D1"][sk]["same"]["all_washed_out_low"])                         # noqa: E731
subs = {
    "{{t_fid}}": t_fid, "{{t_bars}}": t_bars, "{{t_eng}}": t_eng, "{{t_ep}}": t_ep, "{{t_day}}": t_day, "{{t_pol}}": t_pol, "{{t_other}}": t_other,
    "{{n_fast}}": str(n_fast), "{{n_fast_win}}": str(n_fast_win), "{{n_slow}}": str(len(slow)), "{{n_slow_win}}": str(n_slow_win), "{{n_ep}}": str(len(EP)),
    "{{fast_list}}": ", ".join(e["from"][:7] for e in fast), "{{fast_wins}}": " and ".join(e["from"][:7] for e in fast if e["sleeve"] > e["others"]),
    "{{d1_c}}": f"{d1['spread_crash_per_day'] * 100:+.2f}%", "{{d1_g}}": f"{d1['spread_grind_per_day'] * 100:+.2f}%", "{{d1_p}}": pv(d1["p"]), "{{d1_holm}}": pv(d1.get("p_holm")),
    "{{d2_c}}": f"{d2['spread_crash_per_day'] * 100:+.2f}%", "{{d2_g}}": f"{d2['spread_grind_per_day'] * 100:+.2f}%", "{{d2_p}}": pv(d2["p"]), "{{d2_holm}}": pv(d2.get("p_holm")),
    "{{pol_wo}}": lg(POL["B1.D1"][W20]["same"]["d_growth"]), "{{pol_wo2}}": lg(POL["B1.D2"][W20]["same"]["d_growth"]), "{{pol_all}}": lg(POL["B1.D1"]["all"]["same"]["d_growth"]),
    "{{pol_wo_late}}": lg(POL["B1.D1"][W20]["late"]["d_growth"]),
    "{{un_wo}}": un(W20), "{{un_a}}": un(SK[1]), "{{un_b}}": un(SK[2]), "{{un_c}}": un(SK[3]), "{{un_wo_late}}": lg(POL["B1.D1"][W20]["late"]["all_washed_out_low"]),
    "{{e08_s}}": lg(e08["sleeve"], 2), "{{e08_o}}": lg(e08["others"], 2), "{{e20_s}}": lg(e20["sleeve"], 2), "{{e20_o}}": lg(e20["others"], 2), "{{e20_late}}": lg(e20["sleeve_late"], 2),
    "{{e11_s}}": lg(e11["sleeve"], 2), "{{e11_late}}": lg(e11["sleeve_late"], 2), "{{e11_o}}": lg(e11["others"], 2),
    "{{gap}}": lg(SY["VIXY"]["log_gap_per_yr"]), "{{gap_worst}}": lg(SY["VIXY"]["worst_year_gap"][1], 3), "{{corr}}": f"{SY['VIXY']['corr']:.2f}", "{{corr5}}": f"{SY['VIXY']['multi_day_corr']['5']:.3f}",
    "{{mo_gap}}": lg(MO["VIXY"]["log_gap_per_yr"]), "{{mo_worst}}": lg(MO["VIXY"]["worst_year_gap"][1], 2),
    "{{a5_same}}": pu(A5["same_holdings"], 1), "{{a5_ratio}}": pu(A5["ratio"]), "{{a5_2020}}": f"{A5['by_year']['2020'][1]:.2f} against {A5['by_year']['2020'][0]:.2f}",
    "{{bars_met}}": str(sum([BAR["A1"], BAR["A2"], BAR["A3"], BAR["A4"], A5["pass"]])),
    "{{sl08}}": f"{lg(EN['SLEEVE']['log_growth_by_year_old_new']['2008'][0], 2)} to {lg(EN['SLEEVE']['log_growth_by_year_old_new']['2008'][1], 2)}",
    "{{sl09}}": f"{lg(EN['SLEEVE']['log_growth_by_year_old_new']['2009'][0], 2)} to {lg(EN['SLEEVE']['log_growth_by_year_old_new']['2009'][1], 2)}",
    "{{lad_old}}": lg(EN["FrontrunBonds"]["log_growth_2006_2011_old"], 2), "{{lad_new}}": lg(EN["FrontrunBonds"]["log_growth_2006_2011_new"], 2),
    "{{lad08}}": lg(EN["FrontrunBonds"]["by_year_new"]["2008"], 2), "{{lad10}}": lg(EN["FrontrunBonds"]["by_year_new"]["2010"], 2), "{{sl_changed}}": str(EN["SLEEVE"]["sessions_changed"]), "{{hg_changed}}": str(EN["HG"]["sessions_changed"]),
    "{{ch_fid}}": chart("c_fid", "VIXY rebuilt from the exchange's futures settlements against the real fund", "Growth of $1, log scale, 2011 on. The two lines are the test of the rebuild; before 2011 only the rebuilt one exists."),
    "{{ch_ep}}": chart("c_ep", "Each washed-out episode since 2006: what the sleeve earned less the other two engines", "Log-points over the episode's washed-out days. A star marks the fast falls (S&P down more than 10% in 10 sessions). If the sleeve paid in crashes, the starred bars would stand above zero."),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Crash Against Grind</title>"),
             ("const yt=c.log?[.25,.5,1,2,4,8,16,32].filter(", "const yt=c.log?(c.logticks||[.25,.5,1,2,4,8,16,32]).filter("),
             ('if(f==="mult")return (v>=10?v.toFixed(0):v.toFixed(2))+"×"', 'if(f==="mult")return (v>=10?v.toFixed(0):v>=0.01?v.toFixed(2):v.toExponential(0))+"×"')):
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
print("wrote", OUT, len(BODY) // 1024, "KB; fast episodes", n_fast, "sleeve ahead in", n_fast_win, [e["from"] for e in fast], "| slow", len(slow), n_slow_win)
