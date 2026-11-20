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
               "vals": [round(C[c]["joined"]["t"], 2) for c in order], "ref": round(st["critical_t_90"], 2), "reflabel": f"needed to count after {len(order)} tries",
               "name": "t-statistic against the live rule"}


def grid_chart(cid, st, grid, labels=None):
    C, g = st["cells"], w.GRIDS[grid]
    val = lambda c, k: C[c][k]["dlog_per_yr"] if c in C else 0.0                           # noqa: E731
    sp = st["spans"]
    CH[cid] = {"type": "line", "yfmt": "pp", "zero": True, "xnum": True, "xlabels": labels or [short(c).lstrip("abcdefghijklmnopqrstuvwxyz_") for c in g], "xunit": "",
               "series": [{"name": f"Rebuilt years ({yr(sp['R'])})", "slot": 1, "pts": [[i, val(c, "R")] for i, c in enumerate(g)]},
                          {"name": f"Real years ({yr(sp['A'])})", "slot": 2, "pts": [[i, val(c, "REAL")] for i, c in enumerate(g)]},
                          {"name": f"Modelled years ({yr(sp['M'])})", "slot": 3, "pts": [[i, val(c, "M")] for i, c in enumerate(g)]}]}


def groups_table(st, grids):
    def cell(g):
        if not g:
            return ""
        return f"{lg(g['R']['dlog_per_yr'])} / {lg(g['A']['dlog_per_yr'])} / <b>{lg(g['joined']['dlog_per_yr'])}</b> (t {g['joined']['t']:+.1f}; {g['joined']['ahead']} of {g['cells']} ahead)"
    rows = []
    for k in grids:
        v = st["groups"].get(k)
        if v:
            rows.append([GN[k], cell(v.get("shorter")), cell(v.get("longer"))])
    return table(["Family", "Shorter or faster than live: rebuilt / real / <b>both</b>", "Longer or slower than live: rebuilt / real / <b>both</b>"], rows)


def cells_table(st):
    C = st["cells"]
    rows = []
    for c in sorted(C, key=lambda c: -C[c]["joined"]["t"]):
        v = C[c]
        fails = "same as live" if v["same_as_live"] else ", ".join(k[0] for k, x in v["conditions"].items() if not x)
        rows.append([f"{short(c)}", GN[v["grid"]], lg(v["joined"]["dlog_per_yr"], 3), f"{v['joined']['t']:+.2f}", f"{v['joined']['p_fw']:.2f}",
                     f"{lg(v['R']['dlog_per_yr'], 3)} ({pu(v['R']['maxdd'])})", f"{lg(v['REAL']['dlog_per_yr'], 3)} ({pu(v['REAL']['maxdd'])})", lg(v["M"]["dlog_per_yr"], 3), fails])
    return table(["Variant", "Family", "Rebuilt + real, log-pts/yr", "t", "Family-wise p", "Rebuilt (max drawdown)", "Real (max drawdown)", "Modelled", "Tests failed"], rows)


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
                                             ("Sleeve", S["base"], S["spans"], D["SLEEVE"], ("Modelled", "Rebuilt", "Real")),
                                             ("Book", BK["live"], bs, D["BOOK"], ("Rebuilt, shape only", "Part rebuilt", "All real")))
                for k, lab in zip("MRA", labs)])
t_design = table(["", "Holy Grail", "Sleeve"], [
    ["Variants", f"{H['n_cells']}: crossover pairs (21), cash-test window (13), both scaled (11), SPY gate (11), RSI tests (18), pick ranking (11), all RSI together (4); simple and exponential averages",
     f"{S['n_cells']}: IEF window (9), PSQ window (6), both scaled (5), LABD/TMV window (6), KMLM window (5), ladder RSI windows (8), ladder returns and ranks over 2-5 days (6)"],
    ["Modelled years (shape)", f"{H['spans']['M'][0][:7]} to {H['spans']['M'][1][:7]}", f"{S['spans']['M'][0][:7]} to {S['spans']['M'][1][:7]}"],
    ["Rebuilt years", f"{H['spans']['R'][0][:7]} to {H['spans']['R'][1][:7]}", f"{S['spans']['R'][0][:7]} to {S['spans']['R'][1][:7]}"],
    ["Real years", f"{H['spans']['A'][0][:7]} to {H['spans']['A'][1][:7]} (every fund trades)", f"{S['spans']['A'][0][:7]} to {S['spans']['A'][1][:7]} (from BOXX's launch)"],
    ["t needed after all tries", f"{H['critical_t_90']:.2f}", f"{S['critical_t_90']:.2f}"]])
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
    edge(S, sb_, f"The sleeve's best by t ({short(sb_)})", "Inside the noise."),
    f"<li><b>Risk, not edge.</b> On rebuilt history each engine has fallen much further than in its real years (section 4). Holy Grail's {pu(H['base']['R']['maxdd'])} fall of 2011-12 at 34% of the book is about {H['base']['R']['maxdd'] * 34.1:.0f} points of book.</li>"])
jd = [sw[e]["cells"][sw[e]["best_by_t"]]["joined"]["dlog_per_yr"] for e in ("HG", "KMLM", "SLEEVE")]
subs = {
    "{{n_all}}": str(H["n_cells"] + S["n_cells"]), "{{hg_n}}": str(H["n_cells"]), "{{sl_n}}": str(S["n_cells"]),
    "{{ema_txt}}": ema_txt, "{{sg_t}}": f"{sgt:+.1f}", "{{book_rng}}": f"{lg(min(jd), 3)} to {lg(max(jd), 3)}",
    "{{hg_r_dd}}": pu(H["base"]["R"]["maxdd"]), "{{hg_m_dd}}": pu(H["base"]["M"]["maxdd"]), "{{hg_a_dd}}": pu(H["base"]["A"]["maxdd"]),
    "{{sl_m_cagr}}": pc(S["base"]["M"]["cagr"]), "{{sl_m_dd}}": pu(S["base"]["M"]["maxdd"]), "{{sl_a_cagr}}": pc(S["base"]["A"]["cagr"]), "{{sl_a_dd}}": pu(S["base"]["A"]["maxdd"]),
    "{{bk_m_dd}}": pu(BK["live"]["M"]["maxdd"]), "{{bk_a_dd}}": pu(BK["live"]["A"]["maxdd"]),
    "{{hg_best}}": f"{short(hb)} ({GN[HC_[hb]['grid']].lower()})", "{{hg_best_t}}": f"{HC_[hb]['joined']['t']:.2f}", "{{hg_crit}}": f"{H['critical_t_90']:.2f}", "{{hg_best_p}}": f"{HC_[hb]['joined']['p_fw']:.2f}",
    "{{hg_ahead}}": str(len(H["ahead_joined"])), "{{hg_both}}": str(len(H["ahead_R_and_REAL"])) + (" (" + ", ".join(short(c) for c in H["ahead_R_and_REAL"]) + ")" if H["ahead_R_and_REAL"] else ""),
    "{{sl_best}}": f"{short(sb_)} ({GN[SC_[sb_]['grid']].lower()})", "{{sl_best_t}}": f"{SC_[sb_]['joined']['t']:.2f}", "{{sl_crit}}": f"{S['critical_t_90']:.2f}", "{{sl_best_p}}": f"{SC_[sb_]['joined']['p_fw']:.2f}",
    "{{sl_ahead}}": str(len(S["ahead_joined"])), "{{sl_gain}}": f"{max(SC_[c]['joined']['dlog_per_yr'] for c in SC_):.3f}",
    "{{gates}}": f"{pu(okn / tot, 2)}",
    "{{bad_n}}": str(bad["days"]), "{{bad_others}}": pu(-bad["others_mean"], 1), "{{bad_sleeve}}": pc(bad["live_sleeve_mean"], 2), "{{bad_pos}}": pu(bad["live_sleeve_positive_share"]),
    "{{bad_all}}": pc(bad["live_sleeve_all_days_mean"], 2), "{{bad_20}}": pc(bad["next_20_sessions"]["sleeve"], 1), "{{bad_20o}}": pc(bad["next_20_sessions"]["others"], 1),
    "{{bad_best}}": f"{max(bad['cells'].values()) * 1e4:.0f}",
    "{{bk_ver}}": f"{bs['R'][0][:7]} to {bs['A'][1][:7]}",
    "{{hg_mde}}": f"{H['median_mde50']:.2f}", "{{sl_mde}}": f"{S['median_mde50']:.2f}", "{{sl_ver_yrs}}": f"{(S['spans']['R'][2] + S['spans']['A'][2]) / 252:.1f}",
    "{{edges}}": edges,
    "{{t_design}}": t_design, "{{t_gates}}": t_gates, "{{t_book}}": t_book,
    "{{t_hg_groups}}": groups_table(H, ("HAs", "HAe", "HBs", "HBe", "HCs", "HCe", "HDs", "HDe", "HEm", "HEr", "HF", "HG")), "{{t_hg_cells}}": cells_table(H),
    "{{t_sl_groups}}": groups_table(S, ("SA", "SB", "SC", "SD", "SE", "SFm", "SFr", "SGt", "SGp")), "{{t_sl_cells}}": cells_table(S),
    "{{t_open}}": table(["Priority", "Question", "What it would move", "Status"], [
        ["P2", "A KMLM rebuild that passes its fidelity bars (needs exchange settlement data)", "Lets the sleeve and the book be judged on 2008-2020 instead of 2020-12 on", "open, first asked 2026-11-20 (addendum 58)"],
        ["P3", "Real financing and fee histories for the leveraged funds before launch", "Tightens the rebuilt years for Holy Grail", "open"],
        ["P3", "Whether to study thresholds (80/30) as well as windows", "Not asked; a separate family of tries", "owner's call"]]),
    "{{ch_hg_cells}}": chart("c_hg_cells", f"All {H['n_distinct']} Holy Grail variants", "t-statistic of each variant's growth against the live rule, rebuilt plus real years. The dashed line is what a variant needed."),
    "{{ch_hg_cross}}": chart("c_hg_cross", "Trend crossover pair (live 10/20)", "Growth against the live rule, log-points a year (×100), simple averages."),
    "{{ch_hg_rsi}}": chart("c_hg_rsi", "RSI window of the three tests (live 10)", "Thresholds re-set to fire as often as the live ones."),
    "{{ch_hg_gate}}": chart("c_hg_gate", "SPY gate window (live 200)", "Simple averages."),
    "{{ch_hg_picks}}": chart("c_hg_picks", "Pick ranking window (live 10)", "The four ranked picks together."),
    "{{ch_sl_cells}}": chart("c_sl_cells", f"All {S['n_distinct']} sleeve variants", "t-statistic against the live sleeve, rebuilt plus real years."),
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
