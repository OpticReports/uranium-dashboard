"""Build the HTML report of the synthetic-KMLM study from out/*.json. Page shell and chart code: the
addendum-57 report's (kmlm_2026-11/report_body.html), with decade ticks on log axes.
Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
fid, sym, L, X = J("fidelity"), J("symphony"), J("long"), J("extras")
P = json.load(open(os.path.join(HERE, "out", "long_paths.json")))
OUT = sys.argv[1]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
lg = lambda x, d=2: f"{x:+.{d}f}"                                                          # noqa: E731
CH = {}
C = L["cells"]
F1_N = (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)
W, S = fid["vs_fund"]["whole overlap"], fid["vs_fund"]["second part"]
BW, BS = sym["bars"]["whole"], sym["bars"]["second part"]
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
t_bars = table(["Bar (set in advance)", "Whole overlap, 2021-03 to 2024-03", "Later part, 2022-08 on", "Old stand-in"], [
    ["F1 daily correlation at least 0.90", f"{W['daily_corr']:.3f} {ok(W['bars']['F1_daily_corr>=0.90'])}", f"{S['daily_corr']:.3f} {ok(S['bars']['F1_daily_corr>=0.90'])}", f"{W['rymfx']['daily_corr']:.2f}"],
    ["F2 switch reads the same on at least 95% of days", f"{pu(W['flag_agreement'], 1)} {ok(W['bars']['F2_flag>=0.95'])}", f"{pu(S['flag_agreement'], 1)} {ok(S['bars']['F2_flag>=0.95'])}", pu(W['rymfx']['flag_agreement'], 1)],
    ["F3 volatility within 15%, return within 3 points", f"vol {pu(W['synthetic']['vol'], 1)} vs {pu(W['fund']['vol'], 1)} (ratio {W['vol_ratio']:.3f}), return {pc(W['return_gap'], 1)} {ok(W['bars']['F3_vol_within_15pct'] and W['bars']['F3_return_within_3pts'])}",
     f"vol {pu(S['synthetic']['vol'], 1)} vs {pu(S['fund']['vol'], 1)}, return {pc(S['return_gap'], 1)} {ok(S['bars']['F3_vol_within_15pct'] and S['bars']['F3_return_within_3pts'])}", ""],
    ["F4 symphony holds the same funds on at least 95% of sessions; growth within 10%", f"{pu(BW['same_target'], 1)}; growth {pu(BW['log_growth']['ratio'], 1)} of the real run {ok(BW['F4_same_holdings>=0.95'] and BW['F4_growth_within_10pct'])}",
     f"{pu(BS['same_target'], 1)}; {pu(BS['log_growth']['ratio'], 1)} {ok(BS['F4_same_holdings>=0.95'] and BS['F4_growth_within_10pct'])}", "9 to 23× growth where the real flag gave 61× (addendum 57)"],
    ["F5 ranks the 74 variants like the real fund (at least 0.80)", f"{BW['spearman_74']:.2f} {ok(BW['F5_spearman>=0.80'])}", f"{BS['spearman_74']:.2f} {ok(BS['F5_spearman>=0.80'])}", ""],
    ["Not a bar: monthly correlation with the published index, 2008-2020", f"{ix['corr']:.3f} ({ix['months']} months; volatility {pu(ix['synthetic_vol'], 1)} vs {pu(ix['index_vol'], 1)})", "", ""]])
# ---- 2. stretches
sp = L["spans"]
yrs = {k: v[2] / 252 for k, v in sp.items()}
mk = X["markets_by_year"]
t_stretch = table(["Stretch", "Years", "KMLM leg", "Volatility funds", "Counts as"], [
    [f"Real, {sp['A'][0][:7]} to {sp['A'][1][:7]}", f"{yrs['A']:.1f}", "the real fund", "real (modelled before their 2022 and 2023 launches)", "evidence"],
    [f"Replication, {sp['R'][0][:7]} to {sp['R'][1][:7]}", f"{yrs['R']:.1f}", "rebuilt, all 22 markets", "built from the real VIX futures curve; leveraged funds before launch are index × leverage", "evidence, with the fidelity caveat"],
    [f"Model, {sp['M'][0][:7]} to {sp['M'][1][:7]}", f"{yrs['M']:.1f}", f"rebuilt on {sum(mk['1991'].values())} to {sum(mk['2007'].values())} of 22 markets (no euro before 1999; JGB and Bund data start later)",
     "a model: VIX futures did not trade before 2004", "shape only"]])
# ---- 3. window surface
val = lambda c, k: 0.0 if C[c]["is_live_rule"] else C[c][k]["dlog_per_yr"]                 # noqa: E731
CH["c_surface"] = {"type": "line", "yfmt": "pp", "zero": True, "xnum": True, "xlabels": [str(n) for n in F1_N], "xunit": "-day window", "series": [
    {"name": f"Replication years ({sp['R'][0][:4]}-{sp['R'][1][:4]})", "slot": 1, "pts": [[i, val(f"F1a.rsi{n}", "R")] for i, n in enumerate(F1_N)]},
    {"name": f"Real fund ({sp['A'][0][:4]}-{sp['A'][1][:4]})", "slot": 2, "pts": [[i, val(f"F1a.rsi{n}", "REAL")] for i, n in enumerate(F1_N)]},
    {"name": f"Modelled years ({sp['M'][0][:4]}-{sp['M'][1][:4]})", "slot": 3, "pts": [[i, val(f"F1a.rsi{n}", "M")] for i, n in enumerate(F1_N)]}]}
G = L["groups"]
GN = {"short_3_8": "Short windows, 3 to 8 days", "near_9_12": "Neighbours: 9, 11, 12 days", "long_14_60": "Long windows, 14 to 60 days",
      "ma_price": "Price against a moving average", "ma_cross": "Moving-average crossovers", "momentum": "Relative momentum"}
cellf = lambda g: f"{lg(g['dlog_per_yr'])} (t {g['t']:+.1f}; {g['cells_ahead']} of {g['cells']} ahead)"   # noqa: E731
t_groups = table(["Group", "Modelled 1991-2008", "Replication 2008-2020", "Real 2021-2026", "Replication + real"], [
    [GN[k], cellf(G[k]["M"]), cellf(G[k]["R"]), cellf(G[k]["A"]), f"{lg(G[k]['joined']['dlog_per_yr'])} (t {G[k]['joined']['t']:+.1f})" if "joined" in G[k] else ""] for k in GN])
# ---- 4. every variant
order = sorted(chall, key=lambda c: C[c]["joined"]["t"])
short = lambda c: c.split(".", 1)[1]                                                       # noqa: E731
FAM = {"F1a": "RSI switch", "F1b": "RSI switch+picks", "F2": "vote", "F4": "momentum", "F5": "price vs MA", "F6": "MA cross"}
CH["c_cells"] = {"type": "bars", "yfmt": "raw", "cats": [f"{short(c)} ({FAM[C[c]['family']]})" for c in order], "short": [short(c) for c in order], "every": 5,
                 "vals": [round(C[c]["joined"]["t"], 2) for c in order], "ref": round(L["critical_t_90"], 2), "reflabel": f"needed to count after {len(C)} tries",
                 "name": "t-statistic against the live rule"}
t_cells = table(["Variant", "Joined, log-pts/yr", "t", "Family-wise p", "Replication", "Real", "Modelled", "Conditions failed"], [
    [f"{short(c)} ({FAM[C[c]['family']]})", lg(C[c]["joined"]["dlog_per_yr"], 3), f"{C[c]['joined']['t']:+.2f}", f"{C[c]['joined']['p_fw']:.2f}", lg(C[c]["R"]["dlog_per_yr"], 3), lg(C[c]["REAL"]["dlog_per_yr"], 3),
     lg(C[c]["M"]["dlog_per_yr"], 3), ", ".join(k[0] for k, v in C[c]["conditions"].items() if not v)] for c in sorted(chall, key=lambda c: -C[c]["joined"]["t"])])
# ---- 5. the live rule's path
days, ll = P["days"], P["live_log"]
b1, b2 = P["breaks"]
seg = lambda lo, hi: [[d, round(pow(2.718281828459045, v), 4)] for d, v in zip(days, ll) if lo <= d < hi]   # noqa: E731
CH["c_growth"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [1, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10],
                  "series": [{"name": "Modelled years", "slot": 3, "pts": seg("0", b1)}, {"name": "Replication years", "slot": 1, "pts": seg(b1, b2)},
                             {"name": "Real fund", "slot": 2, "pts": seg(b2, "9")}]}
D = X["live_drawdown"]
CH["c_dd"] = {"type": "line", "yfmt": "pct0", "zero": True, "series": [
    {"name": "Modelled years", "slot": 3, "pts": D["M"]["path"]}, {"name": "Replication years", "slot": 1, "pts": D["R"]["path"]},
    {"name": "Real fund", "slot": 2, "pts": D["A"]["path"]}]}
B = L["base"]
ep = lambda d: f"{d['peak'][:7]} to {d['trough'][:7]}, " + (f"recovered {d['recovered'][:7]}" if d["recovered"] else "not recovered by the end of the stretch")   # noqa: E731
t_live = table(["Stretch", "Return a year", "Max drawdown", "Sharpe", "Deepest fall", "Time more than 30% down"], [
    [n, pc(B[k]["cagr"]), pu(B[k]["maxdd"]), f"{B[k]['sharpe']:.2f}", ep(D[k]), pu(D[k]["share_below_30pct"])]
    for k, n in (("M", "Modelled 1991-2008"), ("R", "Replication 2008-2020"), ("A", "Real 2021-2026"))])
# ---- 6. power
pw = X["power"]
PN = {"F1a.rsi11": "11-day window", "F1b.rsi12": "12-day window and picks", "F1a.rsi14": "14-day window", "F1a.rsi20": "20-day window", "F5.ema50": "Price against 50-day EMA"}
t_power = table(["Variant", "Real-fund years only (addendum 57)", "Replication + real", "Sharper by"],
                [[PN[k], f"{v['real_only']:.2f}", f"{v['long']:.2f}", f"{v['real_only'] / v['long']:.1f}×"] for k, v in pw["cells"].items()]
                + [["Typical variant", f"{pw['median_mde50']['real_only_addendum_57']:.2f}", f"{pw['median_mde50']['long']:.2f}", f"{pw['median_mde50']['real_only_addendum_57'] / pw['median_mde50']['long']:.1f}×"],
                   ["t needed after all the tries", f"{pw['critical_t']['real_only']:.2f}", f"{pw['critical_t']['long']:.2f}", ""]])
t_open = table(["Priority", "Question", "What it would move", "Status"], [
    ["P2", "Roll-adjusted futures data after 2024-03 (a paid feed, or the fund's daily holdings files)", "Extends the check against the real fund from 3 years to 6 and settles the missed bar", "open, first asked 2026-11-20"],
    ["P2", "CBOE's own VIX futures settlements for 2004-2008", "Would turn four modelled years into replication", "open; the CBOE file host is reachable, not yet built"],
    ["P3", "The index provider's rulebook (the signal rule here is inferred from holdings)", "Removes the largest assumption in the build", "open"],
    ["P3", "Use the rebuilt fund in place of the RYMFX stand-in in the repo's long panel", "Every other long-history study that reads the KMLM switch", "proposal; needs its own review"]])
near = [c for c in L["ahead_all_three"]]
er = sym["erratum"]
best = L["best_by_t"]
ann = lambda g, n: pow(2.718281828459045, g / (n / 252)) - 1                               # noqa: E731
n57 = 1375
subs = {
    "{{f1}}": f"{W['daily_corr']:.3f}", "{{f1_late}}": f"{X['f1_diagnostics']['from_2022-04-01']:.3f}", "{{f1_2021}}": f"{X['f1_diagnostics']['by_year']['2021']['corr']:.2f}",
    "{{f1_5d}}": f"{X['f1_diagnostics']['five_session_returns']:.2f}", "{{f2}}": pu(W["flag_agreement"], 1), "{{f2_old}}": pu(W["rymfx"]["flag_agreement"]),
    "{{f4}}": pu(BW["same_target"], 1), "{{f4_gap}}": pu(abs(BW["log_growth"]["ratio"] - 1), 1), "{{f5}}": f"{BW['spearman_74']:.2f}",
    "{{vol_s}}": pu(W["synthetic"]["vol"], 1), "{{vol_f}}": pu(W["fund"]["vol"], 1), "{{exposure}}": f"{L['exposure']:.2f}",
    "{{n_cells}}": str(len(C)), "{{n_chall}}": str(len(chall)), "{{n_ahead}}": str(len([c for c in chall if C[c]["joined"]["dlog_per_yr"] > 0])),
    "{{yrs_joined}}": f"{yrs['R'] + yrs['A']:.0f}", "{{short_t}}": f"{G['short_3_8']['joined']['t']:+.1f}",
    "{{mde_near}}": f"{pw['cells']['F1a.rsi11']['long']:.2f} to {pw['cells']['F1a.rsi14']['long']:.2f}", "{{mde_near_old}}": f"{pw['cells']['F1a.rsi11']['real_only']:.2f} to {pw['cells']['F1a.rsi14']['real_only']:.2f}",
    "{{power_x}}": f"{pw['median_mde50']['real_only_addendum_57'] / pw['median_mde50']['long']:.0f}",
    "{{r_cagr}}": pc(B["R"]["cagr"]), "{{r_dd}}": pu(B["R"]["maxdd"]), "{{m_cagr}}": pc(B["M"]["cagr"]), "{{m_dd}}": pu(B["M"]["maxdd"]), "{{a_cagr}}": pc(B["A"]["cagr"]), "{{a_dd}}": pu(B["A"]["maxdd"]),
    "{{best}}": f"{short(best)} ({FAM[C[best]['family']]})", "{{best_t}}": f"{C[best]['joined']['t']:.2f}", "{{crit}}": f"{L['critical_t_90']:.2f}", "{{best_p}}": f"{C[best]['joined']['p_fw']:.2f}",
    "{{max_ahead}}": f"{max(C[c]['joined']['dlog_per_yr'] for c in chall):.2f}",
    "{{near_lo}}": lg(min(C[c]["joined"]["dlog_per_yr"] for c in near), 3), "{{near_hi}}": lg(max(C[c]["joined"]["dlog_per_yr"] for c in near), 3),
    "{{near_t}}": f"{max(C[c]['joined']['t'] for c in near):.1f}", "{{near_p}}": f"{min(C[c]['joined']['p_fw'] for c in near):.2f}",
    "{{long_r_n}}": f"{G['long_14_60']['R']['cells_ahead']} of {G['long_14_60']['R']['cells']}", "{{long_r}}": lg(G["long_14_60"]["R"]["dlog_per_yr"], 3), "{{long_r_t}}": f"{G['long_14_60']['R']['t']:.1f}",
    "{{long_a}}": lg(G["long_14_60"]["A"]["dlog_per_yr"], 3),
    "{{old_c_cagr}}": pc(X["addendum_57_standin_live"]["cagr"]), "{{old_c_dd}}": pu(X["addendum_57_standin_live"]["maxdd"]),
    "{{old_agree}}": pu(X["old_standin_flag_agreement"]["2007-09..2020-12 (RYMFX)"]["agreement"]),
    "{{err_days}}": str(len(sym["flag_differs"])), "{{err_rho}}": f"{er['spearman_of_differences']:.2f}",
    "{{err_old}}": pc(ann(er["base_log_growth"]["yahoo"], n57)), "{{err_new}}": pc(ann(er["base_log_growth"]["corrected"], n57)),
    "{{t_bars}}": t_bars, "{{t_stretch}}": t_stretch, "{{t_groups}}": t_groups, "{{t_cells}}": t_cells, "{{t_live}}": t_live, "{{t_power}}": t_power, "{{t_open}}": t_open,
    "{{ch_overlap}}": chart("c_overlap", "Rebuilt fund against the real one", "Growth of $1 from 2021-03, where both exist. The old stand-in is the fund the earlier study had to use before 2021."),
    "{{ch_index}}": chart("c_index", "Rebuilt fund against the published index, before the fund existed", "Growth of $1, monthly, 2008-03 to 2020-11. The exposure was set on this period; the shape was not."),
    "{{ch_surface}}": chart("c_surface", "Switch window against the live 10-day rule", "Growth difference, log-points a year (×100). Each line is one stretch of history."),
    "{{ch_cells}}": chart("c_cells", f"All {len(chall)} challengers on replication plus real years", "t-statistic of each variant's growth against the live rule. The dashed line is what a variant needed."),
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
