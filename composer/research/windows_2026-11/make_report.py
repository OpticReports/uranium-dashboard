"""Build the HTML report of the windows study from out/*.json. Page shell and chart code: the addendum-57
report's (kmlm_2026-11/report_body.html), with decade ticks on log axes. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wsim as w  # noqa: E402

J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
H, S, BK, GT = J("stats_HG"), J("stats_SLEEVE"), J("book"), J("gates")
OUT = sys.argv[1]
pc = lambda x, d=0: f"{x * 100:+.{d}f}%"                                                   # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
lg = lambda x, d=2: f"{x:+.{d}f}"                                                          # noqa: E731
CH = {}


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


short = lambda c: c.split(".", 1)[1]                                                       # noqa: E731
GN = {"HAs": "Crossover pair, simple", "HAe": "Crossover pair, exponential", "HBs": "Cash test window, simple", "HBe": "Cash test window, exponential",
      "HCs": "Both trend tests scaled, simple", "HCe": "Both trend tests scaled, exponential", "HDs": "SPY gate, simple", "HDe": "SPY gate, exponential",
      "HEm": "RSI tests, matched thresholds", "HEr": "RSI tests, live thresholds", "HF": "Pick ranking window", "HG": "Every RSI window together",
      "SA": "IEF window (live 8)", "SB": "PSQ window (live 45)", "SC": "IEF and PSQ scaled together", "SD": "LABD and TMV window (live 20)", "SE": "KMLM window (live 10)",
      "SFm": "Ladder RSI windows scaled, matched", "SFr": "Ladder RSI windows scaled, live thresholds", "SGt": "Ladder returns over N days, matched", "SGp": "Picks ranked over N days"}
yr = lambda sp: f"{sp[0][:4]}-{sp[1][:4]}"                                                 # noqa: E731


def cells_chart(cid, st):
    C = st["cells"]
    order = sorted((c for c in C if not C[c]["same_as_live"]), key=lambda c: C[c]["joined"]["t"])
    CH[cid] = {"type": "bars", "yfmt": "raw", "cats": [f"{short(c)} ({GN[C[c]['grid']]})" for c in order], "short": [short(c) for c in order], "every": max(4, len(order) // 12),
               "vals": [round(C[c]["joined"]["t"], 2) for c in order], "ref": round(st["critical_t_90"] if st["engine"] == "HG" else st["critical_t_90_bonferroni"], 2), "reflabel": f"needed to count after {len(order)} tries",
               "name": "t-statistic against the live rule"}


def grid_chart(cid, st, grid, labels=None):
    C, g = st["cells"], w.GRIDS[grid]
    val = lambda c, k: C[c][k]["dlog_per_yr"] if c in C else 0.0                           # noqa: E731
    sp = st["spans"]
    lab = {"M": "Modelled years", "R": "Rebuilt years", "A": "Real years"} if st["engine"] == "HG" else {"M": "Rebuilt, shape only", "R": "Part rebuilt", "A": "Real years"}
    CH[cid] = {"type": "line", "yfmt": "pp", "zero": True, "xnum": True, "xlabels": labels or [short(c).lstrip("abcdefghijklmnopqrstuvwxyz_") for c in g], "xunit": "",
               "series": [{"name": f"{lab['R']} ({yr(sp['R'])})", "slot": 1, "pts": [[i, val(c, "R")] for i, c in enumerate(g)]},
                          {"name": f"{lab['A']} ({yr(sp['A'])})", "slot": 2, "pts": [[i, val(c, "REAL")] for i, c in enumerate(g)]},
                          {"name": f"{lab['M']} ({yr(sp['M'])})", "slot": 3, "pts": [[i, val(c, "M")] for i, c in enumerate(g)]}]}


def groups_table(st, grids):
    def cell(g):
        if not g:
            return ""
        return f"{lg(g['M']['dlog_per_yr'])} / {lg(g['R']['dlog_per_yr'])} / {lg(g['A']['dlog_per_yr'])} / <b>{lg(g['joined']['dlog_per_yr'])}</b> (t {g['joined']['t']:+.1f}; {g['joined']['ahead']} of {g['cells']} ahead)"
    rows = []
    for k in grids:
        v = st["groups"].get(k)
        if v:
            rows.append([GN[k], cell(v.get("shorter")), cell(v.get("longer"))])
    a, b, c = (("modelled", "rebuilt", "real") if st["engine"] == "HG" else ("rebuilt to 2020", "2020-12 to 2023-01", "real"))
    return table(["Family", f"Shorter or faster than live: {a} / {b} / {c} / <b>verdict years</b>", f"Longer or slower than live: {a} / {b} / {c} / <b>verdict years</b>"], rows)


def cells_table(st):
    C = st["cells"]
    rows = []
    for c in sorted(C, key=lambda c: -C[c]["joined"]["t"]):
        v = C[c]
        fails = "same as live" if v["same_as_live"] else ", ".join(k[0] for k, x in v["conditions"].items() if not x)
        rows.append([f"{short(c)}", GN[v["grid"]], lg(v["joined"]["dlog_per_yr"], 3), f"{v['joined']['t']:+.2f} ({v['joined']['t_standardised']:+.2f})", f"{v['joined']['p_bonferroni']:.2f}", str(v["days_differing"]),
                     f"{lg(v['R']['dlog_per_yr'], 3)} ({pu(v['R']['maxdd'])})", f"{lg(v['REAL']['dlog_per_yr'], 3)} ({pu(v['REAL']['maxdd'])})", lg(v["M"]["dlog_per_yr"], 3), fails])
    a, b, c = (("Modelled", "Rebuilt", "Real") if st["engine"] == "HG" else ("Rebuilt to 2020 (shape)", "2020-12 to 2023-01", "Real"))
    return table(["Variant", "Family", "Verdict years, log-pts/yr", "t (stretches weighted equally)", "p after all the tries", "Days it differs from live", f"{b} (max drawdown)", f"{c} (max drawdown)", a, "Tests failed"], rows)


# ---- Holy Grail
HC_, SC_ = H["cells"], S["cells"]
cells_chart("c_hg_cells", H)
grid_chart("c_hg_cross", H, "HAs", [f"{a}/{b}" for a, b in w.HA_PAIRS])
grid_chart("c_hg_rsi", H, "HEm", [str(n) for n in w.HE_N])
grid_chart("c_hg_gate", H, "HDs", [str(n) for n in w.HD_N])
grid_chart("c_hg_picks", H, "HF", [str(n) for n in w.HF_N])
cells_chart("c_sl_cells", S)
grid_chart("c_sl_ief", S, "SA", [str(n) for n in w.SA_N])
grid_chart("c_sl_ladder", S, "SGt", [str(n) for n in w.SG_N])
# ---- book
D = BK["drawdowns"]
bs = BK["spans"]
seg = lambda pts, lo, hi: [p for p in pts if lo <= p[0] <= hi]                             # noqa: E731
names = (("M", "Rebuilt years (shape only)", 3), ("R", "Holy Grail and KMLM real, sleeve part rebuilt", 1), ("A", "All three real", 2))
LAB = {"HG": {"M": "Modelled", "R": "Rebuilt", "A": "Real"}, "SLEEVE": {"M": "Rebuilt, shape only", "R": "Part rebuilt", "A": "Real"}}
CH["c_book"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [1, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9],
                "series": [{"name": n, "slot": s, "pts": seg(D["BOOK"]["growth"], bs[k][0], bs[k][1])} for k, n, s in names]}
CH["c_book_dd"] = {"type": "line", "yfmt": "pct0", "zero": True, "series": [{"name": n, "slot": s, "pts": D["BOOK"][k]["path"]} for k, n, s in names]}
sw = BK["swaps"]
rows = []
for e, nm in (("HG", "Holy Grail"), ("KMLM", "KMLM"), ("SLEEVE", "Sleeve")):
    c = sw[e]["best_by_t"]
    j = sw[e]["cells"][c]["joined"]
    rows.append({"name": f"{nm}: {short(c)}", "v": [j["dlog_per_yr"], j["ci90"][0], j["ci90"][1]]})
CH["c_swaps"] = {"type": "forest", "rows": rows}
ep = lambda d: f"{d['peak'][:7]} to {d['trough'][:7]}" + (f", back by {d['recovered'][:7]}" if d["recovered"] else ", not back by the end of the stretch")   # noqa: E731
t_book = table(["", "Stretch", "Return a year", "Max drawdown", "Sharpe", "Deepest fall"],
               [[nm, f"{lab} ({yr(sp[k])})", pc(st[k]["cagr"]), pu(st[k]["maxdd"]), f"{st[k]['sharpe']:.2f}", ep(dd[k])]
                for nm, st, sp, dd, labs in (("Holy Grail", H["base"], H["spans"], D["HG"], ("Modelled", "Rebuilt", "Real")),
                                             ("Sleeve", S["base"], S["spans"], D["SLEEVE"], ("Rebuilt, shape only", "Part rebuilt", "Real")),
                                             ("Book", BK["live"], bs, D["BOOK"], ("Rebuilt, shape only", "Part rebuilt", "All real")))
                for k, lab in zip("MRA", labs)])
t_design = table(["", "Holy Grail", "Sleeve"], [
    ["Variants", f"{H['n_cells']}: crossover pairs (21), cash-test window (13), both scaled (11), SPY gate (11), RSI tests (18), pick ranking (11), all RSI together (4); simple and exponential averages",
     f"{S['n_cells']}: IEF window (9), PSQ window (6), both scaled (5), LABD/TMV window (6), KMLM window (5), ladder RSI windows (8), ladder returns and ranks over 2-5 days (6)"],
    ["Shape only", f"{H['spans']['M'][0][:7]} to {H['spans']['M'][1][:7]} (VIX funds modelled)", f"{S['spans']['M'][0][:7]} to {S['spans']['M'][1][:7]} (rebuilt; the KMLM signal missed its fidelity bar)"],
    ["Rebuilt years in the verdict", f"{H['spans']['R'][0][:7]} to {H['spans']['R'][1][:7]}", f"{S['spans']['R'][0][:7]} to {S['spans']['R'][1][:7]} (real KMLM; BOXX is T-bills)"],
    ["Real years", f"{H['spans']['A'][0][:7]} to {H['spans']['A'][1][:7]} (every fund trades)", f"{S['spans']['A'][0][:7]} to {S['spans']['A'][1][:7]} (from BOXX's launch)"],
    ["t needed after all tries", f"{H['critical_t_90']:.2f}", f"about {S['critical_t_90_bonferroni']:.2f} (section 3)"]])
g1, g2 = GT["G1"], GT["G2"]
t_gates = table(["Check", "Sessions with the same holdings", "Return correlation", "Result"],
                [[f"Live {e} against Composer's stored backtest", f"{v['holdings_same'][0]} of {v['holdings_same'][1]}", f"{v['corr']:.5f}", "pass" if v["pass"] else "FAIL"] for e, v in g1.items()]
                + [[f"{c} run on Composer itself", f"{v['holdings_same'][0]} of {v['holdings_same'][1]}", f"{v['corr']:.5f}", "pass" if v["pass"] else "FAIL"] if "not_run" not in v
                   else [f"{c} on Composer", "", "", "NOT RUN"] for c, v in g2.items()]
                + [["Tree form against injected-flag form, three variants", "every session, both histories", "identical", "pass" if all(v["pass"] for v in GT["G3"].values()) else "FAIL"],
                   ["Stale closes in the real years", "BIL flat for 10 sessions in 2015 (a zero rate, not stale data)", "", "accepted"]])
tot = sum(v["holdings_same"][1] for v in list(g1.values()) + [v for v in g2.values() if "not_run" not in v])
okn = sum(v["holdings_same"][0] for v in list(g1.values()) + [v for v in g2.values() if "not_run" not in v])
# ---- text pieces
em = H["ema_minus_sma"]
ema_txt = ", ".join(f"{n} {lg(em[f]['R']['dlog_per_yr'], 3)} rebuilt and {lg(em[f]['A']['dlog_per_yr'], 3)} real" for f, n in (("HA", "crossovers"), ("HB", "cash test"), ("HD", "SPY gate")))
hb, sb_ = H["best_by_t"], S["best_by_t"]
bad = BK["sleeve_on_bad_days"]
sgt = S["groups"]["SGt"]["longer"]["joined"]["t"]


def edge(st, c, label, extra=""):
    v, b = st["cells"][c], st["base"]
    return (f"<li><b>{label}.</b> Rebuilt years {lg(v['R']['dlog_per_yr'], 3)} log-points a year (t {v['R']['t']:+.1f}), max drawdown {pu(v['R']['maxdd'])} against the live {pu(b['R']['maxdd'])}; "
            f"real years {lg(v['REAL']['dlog_per_yr'], 3)} (t {v['REAL']['t']:+.1f}), drawdown {pu(v['REAL']['maxdd'])} against {pu(b['A']['maxdd'])}; modelled years {lg(v['M']['dlog_per_yr'], 3)}. "
            f"Both together t {v['joined']['t']:+.2f}, family-wise p {v['joined']['p_fw']:.2f}. {extra}</li>")


edges = "".join([
    edge(H, "HA.sma15x30", "Holy Grail on a slower crossover (15/30-day simple)", f"Its exponential twin shows {lg(HC_['HA.ema15x30']['R']['dlog_per_yr'], 3)} on the rebuilt years, so the gain does not survive a change of form. Would need to hold on the real years to be worth a look; it does not."),
    edge(H, "HD.sma100", "Holy Grail with a 100-day SPY gate", "Ahead on both verdict stretches, behind on the modelled one, never by a distinguishable amount."),
    edge(H, hb, f"Holy Grail's best by t ({short(hb)})", "A hundredth of a log-point."),
    edge(S, sb_, f"The sleeve's best by t ({short(sb_)}: the KMLM window in its two hold tests at 5 days instead of 10)", "Ahead since 2020-12 on both stretches, flat on the 26 rebuilt years before. Six years, one of 45 tries: inside the noise. Would need the long history to agree, and it does not."),
    f"<li><b>Risk, not edge.</b> On rebuilt history each engine has fallen much further than in its real years (section 4). Holy Grail's {pu(H['base']['R']['maxdd'])} fall of 2011-12 at 34% of the book is about {H['base']['R']['maxdd'] * 34.1:.0f} points of book.</li>"])
jd = [sw[e]["cells"][sw[e]["best_by_t"]]["joined"]["dlog_per_yr"] for e in ("HG", "KMLM", "SLEEVE")]
excl = [nm for e, nm in (("HG", "Holy Grail's"), ("KMLM", "KMLM's"), ("SLEEVE", "the sleeve's")) if sw[e]["cells"][sw[e]["best_by_t"]]["joined"]["ci90"][0] > 0]
book_ci = ("Every interval spans zero." if not excl else
           f"The plain intervals for {' and '.join(excl)} best sit just above zero, but each is the best of its engine's tries picked after the fact; allowing for that pick none is distinguishable.")
HD_ = BK["hedge"]
pb = lambda x: pc(x, 2)                                                                    # noqa: E731
hrow = lambda lab, v: [lab, str(v["days"]), pb(v["other_mean_on_worst"]), pb(v["sleeve_on_worst"]), pb(v["sleeve_on_other_days"]), f"{v['t']:+.1f}", pb(v["sleeve_on_best"]), f"{v['corr']:+.2f}"]   # noqa: E731
t_hedge = table(["Against", "Bad days", "Its average on them", "Sleeve on those days", "Sleeve on other days", "t", "Sleeve on its best 5%", "Daily correlation"],
                [hrow(f"{nm}, {per}", HD_[k][o]) for k, per in (("verdict_years", "2021-06 on"), ("long_history", "1994-2020 rebuilt"))
                 for o, nm in (("pair", "Holy Grail and KMLM together"), ("HG", "Holy Grail alone"), ("KMLM", "KMLM alone"))])
fall = lambda e: f"{pu(e['depth'])} ({e['peak'][:7]} to {e['trough'][:7]}" + (f", back by {e['recovered'][:7]})" if e["recovered"] else ")")   # noqa: E731
BF = BK["book_falls"]
fams = sw["HG"]["families"] | sw["SLEEVE"]["families"]
t_fams = table(["Family swapped into its engine", "Variants", "Average change in the book, log-pts/yr", "Range", "Ahead", "Average change in the book's deepest fall, 2021-06 to 2023-01"],
               [[GN[g], str(v["n"]), lg(v["mean_dlog_per_yr"], 3), f"{lg(v['min'], 3)} to {lg(v['max'], 3)}", f"{v['ahead']} of {v['n']}", f"{v['mean_d_maxdd_R'] * 100:+.1f} pts"] for g, v in fams.items()])
hbs = max((c for c in HC_ if not HC_[c]["same_as_live"]), key=lambda c: HC_[c]["joined"]["t_standardised"])
sh = lambda v, k: (f"{v['share_of_gain_from_best_10_days'][k] * 100:.0f}%" if v["share_of_gain_from_best_10_days"][k] is not None else "n/a")   # noqa: E731
hbn = lambda fam, k: sum(HC_[c][k]["dlog_per_yr"] > 0 for c in HC_ if HC_[c]["grid"] in fam)   # noqa: E731
edges = "".join([
    edge(H, "HA.sma15x30", "Holy Grail on a slower crossover (15/30-day simple)", f"{sh(HC_['HA.sma15x30'], 'R')} of the rebuilt-years gain is its best 10 days and the smaller drawdown is one episode (2011). Its exponential twin shows {lg(HC_['HA.ema15x30']['R']['dlog_per_yr'], 3)} on the rebuilt years, so the gain does not survive a change of form. Would need to hold on the real years; it does not."),
    edge(H, "HD.sma100", "Holy Grail with a 100-day SPY gate", f"Ahead on both verdict stretches, behind on the modelled one, where its deepest fall is {pu(HC_['HD.sma100']['M']['maxdd'])} against the live {pu(H['base']['M']['maxdd'])}. The 10/30 crossover has the same profile (t {HC_['HA.sma10x30']['joined']['t']:+.2f})."),
    edge(H, hb, f"Holy Grail's best by t ({short(hb)})", f"A hundredth of a log-point; {sh(HC_[hb], 'A')} of its real-years gain is its best 10 days."),
    f"<li><b>The 20-day cash test looks fitted to the real years.</b> Its 13 other windows and forms are ahead of the live rule in {hbn(('HBs', 'HBe'), 'M')} of 13 on the modelled years and {hbn(('HBs', 'HBe'), 'R')} of 13 on the rebuilt years, and in {hbn(('HBs', 'HBe'), 'REAL')} of 13 on the real years. Each gap is small (under 0.05); it says the 20 is not special, not that another number is better.</li>",
    edge(S, sb_, f"The sleeve's best by t ({short(sb_)}: the KMLM window in its two inverse-fund tests at 5 days instead of 10)", "Ahead since 2020-12 on both stretches, flat on the 26 rebuilt years before. Six years, one of 45 tries: inside the noise. Would need the long history to agree, and it does not."),
    f"<li><b>The sleeve's IEF window at 14 or 20 days on the long history.</b> 1994-2020 (rebuilt, shape only): {lg(SC_['SA.ief14']['M']['dlog_per_yr'], 3)} and {lg(SC_['SA.ief20']['M']['dlog_per_yr'], 3)} log-points a year (t {SC_['SA.ief14']['M']['t']:+.1f} and {SC_['SA.ief20']['M']['t']:+.1f}), deepest fall {pu(SC_['SA.ief14']['M']['maxdd'])} against {pu(S['base']['M']['maxdd'])}. On the real years it is {lg(SC_['SA.ief14']['REAL']['dlog_per_yr'], 3)} and {lg(SC_['SA.ief20']['REAL']['dlog_per_yr'], 3)}. Fading over time and reversed where the funds are real: not usable.</li>",
    f"<li><b>The sleeve against Holy Grail alone.</b> On Holy Grail's worst 5% of days since 2021-06 ({HD_['verdict_years']['HG']['days']} days) the sleeve made {pb(HD_['verdict_years']['HG']['sleeve_on_worst'])} against {pb(HD_['verdict_years']['HG']['sleeve_on_other_days'])} on other days (t {HD_['verdict_years']['HG']['t']:+.1f}); mirror: {pb(HD_['verdict_years']['HG']['sleeve_on_best'])} on Holy Grail's best days. On 1994-2020: {pb(HD_['long_history']['HG']['sleeve_on_worst'])} (t {HD_['long_history']['HG']['t']:+.1f}). A real but recent offset; it would take the long history agreeing, or more years, to size on it.</li>",
    f"<li><b>Risk, not edge.</b> On rebuilt history each engine has fallen much further than in its real years, and the book has fallen {pu(BF[0]['depth'])} (section 4).</li>"])
subs = {
    "{{n_all}}": str(H["n_cells"] + S["n_cells"]), "{{hg_n}}": str(H["n_cells"]), "{{sl_n}}": str(S["n_cells"]),
    "{{ema_txt}}": ema_txt, "{{sg_t}}": f"{sgt:+.1f}", "{{sg_tm}}": f"{S['groups']['SGt']['longer']['M']['t']:+.1f}", "{{book_ci}}": book_ci,
    "{{ema_hc}}": f"{lg(em['HC']['R']['dlog_per_yr'], 3)} rebuilt, {lg(em['HC']['A']['dlog_per_yr'], 3)} real, t {em['HC']['A']['t']:+.1f}",
    "{{hg_worse}}": ", ".join((f"the RSI tests at {c.split('rsi')[1]} days with {'the live' if c.startswith('HEr') else 'matched'} thresholds" if c.startswith("HE")
                               else f"every RSI window at {c.split('all')[1]} days" if c.startswith("HG.") else short(c)) for c in H["worse_family_wise"]) or "none",
    "{{bk_falls}}": ", ".join(fall(e) for e in BF[:3]), "{{bk_falls_long}}": "; ".join(fall(e) for e in BF[:4]),
    "{{bk_2011}}": pu(BK["book_in_hg_2011_fall"]["max_fall"]), "{{bk_2011e}}": pu(-BK["book_in_hg_2011_fall"]["end_to_end"]),
    "{{h_pair_w}}": pb(HD_["verdict_years"]["pair"]["sleeve_on_worst"]), "{{h_pair_o}}": pb(HD_["verdict_years"]["pair"]["sleeve_on_other_days"]), "{{h_pair_t}}": f"{HD_['verdict_years']['pair']['t']:.1f}",
    "{{h_pair_b}}": pb(HD_["verdict_years"]["pair"]["sleeve_on_best"]), "{{h_pair_lw}}": pb(HD_["long_history"]["pair"]["sleeve_on_worst"]),
    "{{h_hg_w}}": pb(HD_["verdict_years"]["HG"]["sleeve_on_worst"]), "{{h_hg_t}}": f"{HD_['verdict_years']['HG']['t']:.1f}", "{{h_hg_lw}}": pb(HD_["long_history"]["HG"]["sleeve_on_worst"]), "{{h_hg_lt}}": f"{HD_['long_history']['HG']['t']:.1f}",
    "{{t_hedge}}": t_hedge, "{{t_fams}}": t_fams, "{{bad_unc}}": pc(bad["unconditional_next_20_sessions_others"], 1),
    "{{hg_best_std}}": f"{short(hbs)} at t {HC_[hbs]['joined']['t_standardised']:.2f}", "{{hg_m_ahead}}": str(H["ahead_by_stretch"]["M"]),
    "{{sl_bonf}}": f"{S['critical_t_90_bonferroni']:.2f}",
    "{{sl_all3}}": str(len(S["ahead_all_three"])) + (" (" + ", ".join(short(c) for c in S["ahead_all_three"]) + ")" if S["ahead_all_three"] else ""), "{{book_rng}}": f"{lg(min(jd), 3)} to {lg(max(jd), 3)}",
    "{{hg_r_dd}}": pu(H["base"]["R"]["maxdd"]), "{{hg_m_dd}}": pu(H["base"]["M"]["maxdd"]), "{{hg_a_dd}}": pu(H["base"]["A"]["maxdd"]),
    "{{sl_m_cagr}}": pc(S["base"]["M"]["cagr"]), "{{sl_m_dd}}": pu(S["base"]["M"]["maxdd"]), "{{sl_a_cagr}}": pc(S["base"]["A"]["cagr"]), "{{sl_a_dd}}": pu(S["base"]["A"]["maxdd"]),
    "{{bk_m_dd}}": pu(BK["live"]["M"]["maxdd"]), "{{bk_a_dd}}": pu(BK["live"]["A"]["maxdd"]),
    "{{hg_best}}": f"{short(hb)}, {GN[HC_[hb]['grid']]}", "{{hg_best_t}}": f"{HC_[hb]['joined']['t']:.2f}", "{{hg_crit}}": f"{H['critical_t_90']:.2f}", "{{hg_best_p}}": f"{HC_[hb]['joined']['p_fw']:.2f}",
    "{{hg_ahead}}": str(len(H["ahead_joined"])), "{{hg_both}}": str(len(H["ahead_R_and_REAL"])) + (" (" + ", ".join(short(c) for c in H["ahead_R_and_REAL"]) + ")" if H["ahead_R_and_REAL"] else ""),
    "{{sl_best}}": f"{short(sb_)}, {GN[SC_[sb_]['grid']]}", "{{sl_best_t}}": f"{SC_[sb_]['joined']['t']:.2f}", "{{sl_crit}}": f"{S['critical_t_90']:.2f}", 
    "{{sl_ahead}}": str(len(S["ahead_joined"])),
    "{{gates}}": f"{okn:,} of {tot:,}",
    "{{bad_20}}": pc(bad["next_20_sessions"]["sleeve"], 1), "{{bad_20o}}": pc(bad["next_20_sessions"]["others"], 1),
    "{{bad_best}}": f"{max(bad['cells'].values()) * 1e4:.0f}",
    "{{bk_ver}}": f"{bs['R'][0][:7]} to {bs['A'][1][:7]}",
    "{{hg_mde}}": f"{H['median_mde50']:.2f}", "{{sl_mde}}": f"{S['median_mde50_bonferroni']:.2f}", "{{sl_ver_yrs}}": f"{(S['spans']['R'][2] + S['spans']['A'][2]) / 252:.1f}",
    "{{edges}}": edges,
    "{{t_design}}": t_design, "{{t_gates}}": t_gates, "{{t_book}}": t_book,
    "{{t_hg_groups}}": groups_table(H, ("HAs", "HAe", "HBs", "HBe", "HCs", "HCe", "HDs", "HDe", "HEm", "HEr", "HF", "HG")), "{{t_hg_cells}}": cells_table(H),
    "{{t_sl_groups}}": groups_table(S, ("SA", "SB", "SC", "SD", "SE", "SFm", "SFr", "SGt", "SGp")), "{{t_sl_cells}}": cells_table(S),
    "{{t_open}}": table(["Priority", "Question", "What it would move", "Status"], [
        ["P1", "Is the sleeve's weak 1994-2020 record (about +10% a year, a 47% fall, no hedge of the pair) the rebuilt data or the rule?", "Bears on its 31.8% weight in the book", "open, first asked 2026-11-21"],
        ["P2", "A KMLM rebuild that passes its fidelity bars (needs exchange settlement data)", "Lets the sleeve and the book be judged on 2008-2020 instead of 2020-12 on; fills the 2020-12 to 2021-05 gap in the book", "open, first asked 2026-11-20 (addendum 58)"],
        ["P2", "Do Holy Grail's crossover and SPY gate earn their keep on the rebuilt years? (no \"off\" variant was registered here; addenda 30 and 44 looked on other samples)", "What to expect from Holy Grail outside 2015-2026", "open, first asked 2026-11-21"],
        ["P3", "Real financing and fee histories for the leveraged funds before launch", "Tightens the rebuilt years for Holy Grail", "open, first asked 2026-11-21"],
        ["P3", "Whether to study thresholds (80/30) as well as windows", "Not asked; a separate family of tries", "owner's call, raised 2026-11-21"]]),
    "{{ch_hg_cells}}": chart("c_hg_cells", f"All {H['n_distinct']} Holy Grail variants", "t-statistic of each variant's growth against the live rule, rebuilt plus real years. The dashed line is what a variant needed."),
    "{{ch_hg_cross}}": chart("c_hg_cross", "Trend crossover pair (live 10/20)", "Growth against the live rule, log-points a year (×100), simple averages."),
    "{{ch_hg_rsi}}": chart("c_hg_rsi", "RSI window of the three tests (live 10)", "Thresholds re-set to fire as often as the live ones."),
    "{{ch_hg_gate}}": chart("c_hg_gate", "SPY gate window (live 200)", "Simple averages."),
    "{{ch_hg_picks}}": chart("c_hg_picks", "Pick ranking window (live 10)", "The four ranked picks together."),
    "{{ch_sl_cells}}": chart("c_sl_cells", f"All {S['n_distinct']} sleeve variants", "t-statistic against the live sleeve on the verdict years (2020-12 on)."),
    "{{ch_sl_ief}}": chart("c_sl_ief", "IEF window in the bond switch (live 8)", "Growth against the live sleeve, log-points a year (×100)."),
    "{{ch_sl_ladder}}": chart("c_sl_ladder", "Ladder returns over N days (live 1)", "Thresholds matched to fire as often."),
    "{{ch_book}}": chart("c_book", "The live book, growth of $1 (log scale)", "Simulated, costs included. Each gridline is ten times the one below."),
    "{{ch_book_dd}}": chart("c_book_dd", "The live book, drawdown", "Fall from the running peak, restarted at each stretch."),
    "{{ch_swaps}}": f'<div class="chart"><h4>Best variant of each engine, at book level</h4><p class="cap">Change in the book\'s yearly growth, log-points (×100), 90% interval.</p><div id="c_swaps" style="max-width:560px"></div></div>',
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Symphony Window Study</title>"),
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
