"""Build the HTML report of the synthetic-KMLM study from out/*.json. Page shell and chart code: the
addendum-57 report's (kmlm_2026-11/report_body.html), with decade ticks on log axes.
Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
fid, sym, L, X, RV, FU = J("fidelity"), J("symphony"), J("long"), J("extras"), J("review"), J("followup")
P = json.load(open(os.path.join(HERE, "out", "long_paths.json")))
OUT = sys.argv[1]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
lg = lambda x, d=2: f"{x:+.{d}f}"                                                          # noqa: E731
CH = {}
C = L["cells"]
F1_N = (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)
W, S, S2 = fid["vs_fund"]["whole overlap"], fid["vs_fund"]["second part"], fid["vs_fund"]["pre-registered second half"]
BW, BS, B3 = sym["bars"]["whole"], sym["bars"]["second part"], sym["bars"]["pre-registered second half"]
chall = [c for c in C if not C[c]["is_live_rule"]]


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


ok = lambda b: "pass" if b else "<b>miss</b>"                                              # noqa: E731
# ---- 1. fidelity
ol = X["overlap_levels"]
CH["c_overlap"] = {"type": "line", "yfmt": "mult", "series": [
    {"name": "Real KMLM fund (total return)", "slot": 1, "pts": ol["fund"]},
    {"name": "Rebuilt from the index rules", "slot": 2, "pts": ol["synthetic"]},
    {"name": "Old stand-in (RYMFX)", "slot": 3, "pts": ol["rymfx"]}]}
il = X["index_levels"]
CH["c_index"] = {"type": "line", "yfmt": "mult", "series": [
    {"name": "Published KFA MLM index", "slot": 1, "pts": il["index"]},
    {"name": "Rebuilt (before fees)", "slot": 2, "pts": il["synthetic"]}]}
ix = fid["vs_index_monthly"]["2008-2020 (all 22 markets, today's rules)"]
def f3(v):
    return f"vol {pu(v['synthetic']['vol'], 1)} vs {pu(v['fund']['vol'], 1)}, return {pc(v['return_gap'], 1)} {ok(v['bars']['F3_vol_within_15pct'] and v['bars']['F3_return_within_3pts'])}"


t_bars = table(["Bar (set in advance)", "Whole overlap, 2021-03 to 2024-03 (where the bars are read)", "2022-08 on", f"2023-12 on ({S2['sessions']} sessions)", "Old stand-in"], [
    ["Daily correlation at least 0.90"] + [f"{v['daily_corr']:.3f} {ok(v['bars']['F1_daily_corr>=0.90'])}" for v in (W, S, S2)] + [f"{W['rymfx']['daily_corr']:.2f}"],
    ["Switch reads the same on at least 95% of days"] + [f"{pu(v['flag_agreement'], 1)} {ok(v['bars']['F2_flag>=0.95'])}" for v in (W, S, S2)] + [pu(W['rymfx']['flag_agreement'], 1)],
    ["Volatility within 15%, return within 3 points"] + [f3(v) for v in (W, S, S2)] + [""],
    ["Symphony holds the same funds on at least 95% of sessions; log growth within 10%", f"{pu(BW['same_target'], 1)}; log growth {pu(BW['log_growth']['ratio'], 1)} of the real run {ok(BW['F4_same_holdings>=0.95'] and BW['F4_growth_within_10pct'])}",
     f"{pu(BS['same_target'], 1)}; {pu(BS['log_growth']['ratio'], 1)} {ok(BS['F4_same_holdings>=0.95'] and BS['F4_growth_within_10pct'])}",
     f"{pu(B3['same_target'], 1)}; {pu(B3['log_growth']['ratio'], 1)} {ok(B3['F4_same_holdings>=0.95'] and B3['F4_growth_within_10pct'])}", ""],
    ["Ranks the 74 variants like the real fund (at least 0.80)", f"{BW['spearman_74']:.2f} {ok(BW['F5_spearman>=0.80'])}", f"{BS['spearman_74']:.2f} {ok(BS['F5_spearman>=0.80'])}", f"{B3['spearman_74']:.2f} {ok(B3['F5_spearman>=0.80'])}", ""],
    ["Not a bar: monthly correlation with the published index, 2008-2020", f"{ix['corr']:.3f} ({ix['months']} months; volatility {pu(ix['synthetic_vol'], 1)} vs {pu(ix['index_vol'], 1)})", "", "", ""]])
# ---- 2. stretches
sp = L["spans"]
yrs = {k: v[2] / 252 for k, v in sp.items()}
mk = X["markets_by_year"]
t_stretch = table(["Stretch", "Years", "KMLM leg", "Volatility funds", "Counts as"], [
    [f"Real, {sp['A'][0][:7]} to {sp['A'][1][:7]}", f"{yrs['A']:.1f}", "the real fund", "real (modelled before their 2022 and 2023 launches)", "evidence"],
    [f"Rebuilt, {sp['R'][0][:7]} to {sp['R'][1][:7]}", f"{yrs['R']:.1f}", "rebuilt, all 22 markets", "built from the real VIX futures curve; leveraged funds before launch are index × leverage", "shape only: a fidelity bar was missed"],
    [f"Model, {sp['M'][0][:7]} to {sp['M'][1][:7]}", f"{yrs['M']:.1f}", f"rebuilt on {sum(mk['1991'].values())} to {sum(mk['2007'].values())} of 22 markets (no euro leg before 2000; JGB and Bund data start later)",
     "a model: VIX futures did not trade before 2004", "shape only"]])
# ---- 3. window surface
val = lambda c, k: 0.0 if C[c]["is_live_rule"] else C[c][k]["dlog_per_yr"]                 # noqa: E731
CH["c_surface"] = {"type": "line", "yfmt": "pp", "zero": True, "xnum": True, "xlabels": [str(n) for n in F1_N], "xunit": "-day window", "series": [
    {"name": f"Rebuilt years ({sp['R'][0][:4]}-{sp['R'][1][:4]})", "slot": 1, "pts": [[i, val(f"F1a.rsi{n}", "R")] for i, n in enumerate(F1_N)]},
    {"name": f"Real fund ({sp['A'][0][:4]}-{sp['A'][1][:4]})", "slot": 2, "pts": [[i, val(f"F1a.rsi{n}", "REAL")] for i, n in enumerate(F1_N)]},
    {"name": f"Modelled years ({sp['M'][0][:4]}-{sp['M'][1][:4]})", "slot": 3, "pts": [[i, val(f"F1a.rsi{n}", "M")] for i, n in enumerate(F1_N)]}]}
G = L["groups"]
GN = {"short_3_8": "Short windows, 3 to 8 days", "near_9_12": "Neighbours: 9, 11, 12 days", "long_14_60": "Long windows, 14 to 60 days",
      "ma_price": "Price against a moving average", "ma_cross": "Moving-average crossovers", "momentum": "Relative momentum"}
cellf = lambda g: f"{lg(g['dlog_per_yr'])} (t {g['t']:+.1f}; {g['cells_ahead']} of {g['cells']} ahead)"   # noqa: E731
t_groups = table(["Group", "Modelled 1991-2008", "Rebuilt 2008-2020", "Real fund 2021-2026"], [[GN[k], cellf(G[k]["M"]), cellf(G[k]["R"]), cellf(G[k]["A"])] for k in GN])
# ---- 4. every variant
AL = RV["alone"]["R"]
order = sorted(chall, key=lambda c: C[c]["R"]["t"])
short = lambda c: c.split(".", 1)[1]                                                       # noqa: E731
FAM = {"F1a": "RSI switch", "F1b": "RSI switch+picks", "F2": "vote", "F4": "momentum", "F5": "price vs MA", "F6": "MA cross"}
CH["c_cells"] = {"type": "bars", "yfmt": "raw", "cats": [f"{short(c)} ({FAM[C[c]['family']]})" for c in order], "short": [short(c) for c in order], "every": 5,
                 "vals": [round(C[c]["R"]["t"], 2) for c in order], "ref": round(AL["critical_t_90"], 2), "reflabel": f"needed to count after all the tries",
                 "name": "t-statistic against the live rule"}
t_cells = table(["Variant", "Rebuilt 2008-2020, log-pts/yr", "t", "Real fund 2021-2026", "t", "Modelled 1991-2008", "t"], [
    [f"{short(c)} ({FAM[C[c]['family']]})", lg(C[c]["R"]["dlog_per_yr"], 3), f"{C[c]['R']['t']:+.2f}", lg(C[c]["REAL"]["dlog_per_yr"], 3), f"{C[c]['REAL']['t']:+.2f}",
     lg(C[c]["M"]["dlog_per_yr"], 3), f"{C[c]['M']['t']:+.2f}"] for c in sorted(chall, key=lambda c: -C[c]["R"]["t"])])
# ---- 5. the live rule's path
days, ll = P["days"], P["live_log"]
b1, b2 = P["breaks"]
seg = lambda lo, hi: [[d, round(pow(2.718281828459045, v), 4)] for d, v in zip(days, ll) if lo <= d < hi]   # noqa: E731
CH["c_growth"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [1, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10],
                  "series": [{"name": "Modelled years", "slot": 3, "pts": seg("0", b1)}, {"name": "Rebuilt years", "slot": 1, "pts": seg(b1, b2)},
                             {"name": "Real fund", "slot": 2, "pts": seg(b2, "9")}]}
D = X["live_drawdown"]
CH["c_dd"] = {"type": "line", "yfmt": "pct0", "zero": True, "series": [
    {"name": "Modelled years", "slot": 3, "pts": D["M"]["path"]}, {"name": "Rebuilt years", "slot": 1, "pts": D["R"]["path"]},
    {"name": "Real fund", "slot": 2, "pts": D["A"]["path"]}]}
B = L["base"]
ep = lambda d: f"{d['peak'][:7]} to {d['trough'][:7]}, " + (f"recovered {d['recovered'][:7]}" if d["recovered"] else "not recovered by the end of the stretch")   # noqa: E731
t_live = table(["Stretch", "Return a year", "Max drawdown", "Sharpe", "Deepest fall", "Time more than 30% down"], [
    [n, pc(B[k]["cagr"]), pu(B[k]["maxdd"]), f"{B[k]['sharpe']:.2f}", ep(D[k]), pu(D[k]["share_below_30pct"])]
    for k, n in (("M", "Modelled 1991-2008"), ("R", "Rebuilt 2008-2020"), ("A", "Real 2021-2026"))])
# ---- the switch itself, and what the rebuilt years can resolve
SW, FS, FP = RV["switch"], FU["switch"], FU["path"]
swc = lambda v: f"{lg(v['live_minus_log_per_yr'])} (t {v['t']:+.1f})"                       # noqa: E731
t_switch = table(["Live rule minus", "Modelled 1991-2008", "Rebuilt 2008-2020", "Real fund 2021-2026"], [
    [n] + [swc(SW[k][key]) for k in ("M", "R", "REAL")] for key, n in (("always_risk_on", "always risk-on"), ("always_risk_off", "always risk-off"), ("inverted", "its mirror image"))]
    + [["its mirror image, leaving out 2008 and 2020", "", f"{lg(FS['R']['mirror_without_2008_2020']['log_per_yr'])} (t {FS['R']['mirror_without_2008_2020']['t']:+.1f})", ""],
       ["always risk-on, leaving out 2008", "", f"{lg(FS['R']['risk_on_without_2008']['log_per_yr'])} (t {FS['R']['risk_on_without_2008']['t']:+.1f})", ""],
       ["a fixed mix at the switch's own risk-on share", "", f"{lg(FS['R']['vs_static_mix']['log_per_yr'])} (t {FS['R']['vs_static_mix']['t']:+.1f})", f"{lg(FS['REAL']['vs_static_mix']['log_per_yr'])} (t {FS['REAL']['vs_static_mix']['t']:+.1f})"]]
    + [["Placebo: time-shifted copies at least as good, of 60", "not run", str(SW["R"]["placebo"]["at_or_above_live"]), str(SW["REAL"]["placebo"]["at_or_above_live"])],
       ["Max drawdown: live rule / always risk-on"] + [f"{pu(SW[k]['live']['maxdd'])} / {pu(SW[k]['always_risk_on']['maxdd'])}" for k in ("M", "R", "REAL")]])
RS = RV["resolution"]
RG = {"Neighbouring windows (9, 11, 12 days)": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (9, 11, 12)], "Short windows (3 to 8)": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (3, 5, 7, 8)],
      "Long windows (14 to 60)": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (14, 17, 20, 25, 30, 40, 60)], "Relative momentum (6 forms)": [c for c in RS["cells"] if c.startswith("F4.")]}
yo = RS["sessions"] / 252
rrow = []
for g, cs in RG.items():
    cs = [c for c in cs if c in RS["cells"]]
    v = [RS["cells"][c] for c in cs]
    med = statistics.median(x["corr_of_daily_difference"] for x in v)
    rrow.append([g, f"{med:.2f}", f"{sum((x['real_total'] > 0) == (x['synthetic_total'] > 0) for x in v)} of {len(v)}",
                 f"{(sum((x['real_total'] - x['synthetic_total']) ** 2 for x in v) / len(v)) ** 0.5 / yo:.2f}"])
t_res = table(["Variants", "Typical correlation of daily differences, rebuilt vs real", "Same sign against the live rule", "Typical gap, log-pts/yr"], rrow)
t_open = table(["Priority", "Question", "What it would move", "Status"], [
    ["P2", "Exchange settlement prices for the 22 markets (a paid feed), through 2026", "Removes the stale-close problem at source, the unresolved market-years and the 2024-03 cut-off; lets the bars be re-scored on six years", "open, first asked 2026-11-20"],
    ["P2", "Front-contract histories for crude, corn, wheat and soybeans", "The four markets where the files hold a later contract than the fund", "open, first asked 2026-11-20"],
    ["P2", "CBOE's own VIX futures settlements for 2004-2008", "Would turn four modelled years into rebuilt ones", "open, first asked 2026-11-20; the CBOE file host is reachable, not yet built"],
    ["P3", "The index provider's rulebook (the signal rule here is inferred from holdings)", "Removes the largest assumption in the build", "open, first asked 2026-11-20"],
    ["P3", "When the switcher's rule was last tuned or adopted (its description carries a backtest date of 2022-04-13)", "Which real years count as out of sample for the live rule", "open, first asked 2026-11-21"],
    ["P3", "The fund's own distribution record (its site refused the request)", "Confirms the $4.04 figure at source", "open, first asked 2026-11-20"],
    ["P3", "Licence terms of the public futures dataset", "Whether the rebuild can be kept in the repo's tooling", "open, first asked 2026-11-20"],
    ["P3", "Use the rebuilt fund in place of the RYMFX stand-in in the repo's long panel", "Every other long-history study that reads the KMLM switch", "proposal of 2026-11-20; needs its own review"]])
near = [c for c in L["ahead_all_three"]]
er = sym["erratum"]
ann = lambda g, n: pow(2.718281828459045, g / (n / 252)) - 1                               # noqa: E731
n57 = 1375
FD = X["f1_diagnostics"]
mi = [i for i, d in enumerate(days) if d < b1]
mpk = max(ll[i] for i in mi)
rec = next((d for d, v in zip(days, ll) if d >= b1 and v >= mpk), None)
worse = AL["cells_below_minus_crit"]
r_worse = (f"{len(worse)} are distinguishably worse: " + ", ".join(short(c) for c in worse) + ".") if worse else "None is distinguishably worse either."
near_txt = (f"Ahead on all three stretches ({', '.join(sorted({short(c) for c in near}))}, with and without the ranked picks), by {lg(min(C[c]['R']['dlog_per_yr'] for c in near), 3)} to {lg(max(C[c]['R']['dlog_per_yr'] for c in near), 3)} on the rebuilt years: far inside the noise; the rebuilt fund cannot resolve differences this small, and on the first reviewer's alternative corrected data all four turn negative."
            if near else "Ahead on the real fund (addendum 57), not ahead on all three stretches here. Inside the noise either way.")
subs = {
    "{{f1}}": f"{W['daily_corr']:.3f}", "{{f1_old}}": f"{W['rymfx']['daily_corr']:.2f}", "{{f1_2021}}": f"{FD['by_year']['2021']['corr']:.2f}", "{{f1_2023}}": f"{FD['by_year']['2023']['corr']:.2f}",
    "{{f1_5d}}": f"{FD['five_session_returns']:.2f}", "{{f2}}": pu(W["flag_agreement"], 1), "{{f2_old}}": pu(W["rymfx"]["flag_agreement"]), "{{n_late}}": str(S2["sessions"]),
    "{{f4}}": pu(BW["same_target"], 1), "{{exposure}}": f"{L['exposure']:.2f}",
    "{{n_cells}}": str(len(C)), "{{n_chall}}": str(len(chall)),
    "{{r_best}}": f"{short(AL['best'])} ({FAM[C[AL['best']]['family']]})", "{{r_best_t}}": f"{AL['best_t']:.2f}", "{{r_crit}}": f"{AL['critical_t_90']:.2f}", "{{r_best_p}}": f"{AL['best_p_fw']:.2f}",
    "{{r_ahead}}": str(len([c for c in chall if C[c]["R"]["dlog_per_yr"] > 0])), "{{r_worse}}": r_worse,
    "{{sw_inv}}": lg(SW["R"]["inverted"]["live_minus_log_per_yr"]), "{{sw_inv_t}}": f"{SW['R']['inverted']['t']:.1f}", "{{sw_n}}": f"{SW['R']['sessions']:,}",
    "{{sw_plc}}": str(SW["R"]["placebo"]["at_or_above_live"]),
    "{{sw_x}}": lg(FS["R"]["mirror_without_2008_2020"]["log_per_yr"]), "{{sw_x_t}}": f"{FS['R']['mirror_without_2008_2020']['t']:.1f}",
    "{{sw_conc}}": pu(FS["R"]["share_of_mirror_from_2008_2020"]), "{{sw_mix}}": lg(FS["R"]["vs_static_mix"]["log_per_yr"]), "{{sw_mix_t}}": f"{FS['R']['vs_static_mix']['t']:.1f}",
    "{{sw_after}}": lg(FS["REAL"]["mirror_after_stamp"]["log_per_yr"]), "{{sw_after_t}}": f"{FS['REAL']['mirror_after_stamp']['t']:.1f}", "{{sw_after_n}}": f"{FS['REAL']['mirror_after_stamp']['sessions']:,}",
    "{{rk}}": f"{FU['ranks']['rebuilt_vs_real']:.2f}", "{{f1_2024}}": f"{FD['by_year']['2024']['corr']:.2f}",
    "{{deep}}": pu(FP["deepest"]["depth"]), "{{deep_p}}": FP["deepest"]["peak"][:7], "{{deep_t}}": FP["deepest"]["trough"][:7], "{{deep_r}}": FP["deepest"]["recovered"][:7], "{{deep_h}}": FP["deepest"]["last_session_below_old_high"][:7],
    "{{f1_d}}": pu(FP["falls_from_2008"][0]["depth"]), "{{f1_w}}": f"{FP['falls_from_2008'][0]['peak'][:7]} to {FP['falls_from_2008'][0]['trough'][:7]}",
    "{{f2_d}}": pu(FP["falls_from_2008"][1]["depth"]), "{{f2_w}}": f"{FP['falls_from_2008'][1]['peak'][:7]} to {FP['falls_from_2008'][1]['trough'][:7]}",
    "{{f1_funds}}": "the loss was mostly in " + ", ".join(list(FP["deepest_since_2012_by_fund"])[:3]),
    "{{f1_model}}": pu(sum(v for k, v in FP["deepest_since_2012_by_fund"].items() if k in ("SVIX", "ZVOL")) / sum(v for v in FP["deepest_since_2012_by_fund"].values() if v < 0)),
    "{{vix_rng}}": f"{max(abs(C[c]['M']['other_vix_models'][k] - C[c]['M']['dlog_per_yr']) for c in chall for k in ('plain', 'level')):.2f} log-points a year",
    "{{r_cagr}}": pc(B["R"]["cagr"]), "{{m_cagr}}": pc(B["M"]["cagr"]), "{{a_cagr}}": pc(B["A"]["cagr"]), "{{a_dd}}": pu(B["A"]["maxdd"]),
    "{{m_end_dd}}": pu(FP["depth_at_end_of_model_years"]),
    "{{book_pts}}": f"{FP['falls_from_2008'][0]['depth'] * 34.1:.0f}",
    "{{long_r_n}}": f"{G['long_14_60']['R']['cells_ahead']} of {G['long_14_60']['R']['cells']}", "{{long_r}}": lg(G["long_14_60"]["R"]["dlog_per_yr"], 3), "{{long_r_t}}": f"{G['long_14_60']['R']['t']:.1f}",
    "{{long_a_n}}": f"{G['long_14_60']['A']['cells'] - G['long_14_60']['A']['cells_ahead']} of {G['long_14_60']['A']['cells']}", "{{long_a}}": lg(G["long_14_60"]["A"]["dlog_per_yr"], 3),
    "{{near_txt}}": near_txt,
    "{{old_c_cagr}}": pc(X["addendum_57_standin_live"]["cagr"]), "{{old_c_dd}}": pu(X["addendum_57_standin_live"]["maxdd"]),
    "{{old_agree}}": pu(X["old_standin_flag_agreement"]["2007-09..2020-12 (RYMFX)"]["agreement"]),
    "{{err_days}}": str(len(sym["flag_differs"])), "{{err_rho}}": f"{er['spearman_of_differences']:.2f}", "{{err_max}}": f"{er['max_abs_change_log_per_yr']:.2f}",
    "{{err_old}}": pc(ann(er["base_log_growth"]["yahoo"], n57)), "{{err_new}}": pc(ann(er["base_log_growth"]["corrected"], n57)),
    "{{t_switch}}": t_switch, "{{t_res}}": t_res,
    "{{t_bars}}": t_bars, "{{t_stretch}}": t_stretch, "{{t_groups}}": t_groups, "{{t_cells}}": t_cells, "{{t_live}}": t_live, "{{t_open}}": t_open,
    "{{ch_overlap}}": chart("c_overlap", "Rebuilt fund against the real one", "Growth of $1 from 2021-03, where both exist. The old stand-in is the fund the earlier study had to use before 2021."),
    "{{ch_index}}": chart("c_index", "Rebuilt fund against the published index, before the fund existed", "Growth of $1, monthly, 2008-03 to 2020-11. The exposure was set on this period; the shape was not."),
    "{{ch_surface}}": chart("c_surface", "Switch window against the live 10-day rule", "Growth difference, log-points a year (×100). Each line is one stretch of history."),
    "{{ch_cells}}": chart("c_cells", f"All {len(chall)} challengers on the rebuilt years (2008-2020)", "t-statistic of each variant's growth against the live rule. The dashed line is what a variant needed."),
    "{{ch_growth}}": chart("c_growth", "The live rule, growth of $1 (log scale)", "Simulated, costs included, chained across the three stretches. Each gridline is ten times the one below."),
    "{{ch_dd}}": chart("c_dd", "The live rule, drawdown", "Fall from the running peak, restarted at each stretch."),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Synthetic KMLM History</title>"),
             ("const yt=c.log?[.25,.5,1,2,4,8,16,32].filter(", "const yt=c.log?(c.logticks||[.25,.5,1,2,4,8,16,32]).filter("),
             ('if(f==="mult")return (v>=10?v.toFixed(0):v.toFixed(2))+"×"',
              'if(f==="mult")return (v>=1e9?(v/1e9).toFixed(0)+"B":v>=1e6?(v/1e6).toFixed(0)+"M":v>=1e3?(v/1e3).toFixed(0)+"k":v>=10?v.toFixed(0):v.toFixed(2))+"×"')):
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
