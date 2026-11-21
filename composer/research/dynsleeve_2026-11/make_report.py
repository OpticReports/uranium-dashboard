"""Build the HTML report of the dynamic sleeve weight study from out/dynsleeve.json. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "out", "dynsleeve.json")))
OUT = sys.argv[1]
ST, FX, PRIM = D["states"], D["fixed"], D["meta"]["primary"]
lg = lambda x, d=3: "n/a" if x is None else f"{x:+.{d}f}"                                  # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
pp = lambda x: f"{x * 100:+.1f}"                                                           # noqa: E731
pv = lambda p: "n/a" if p is None else ("&lt;0.001" if p < 0.0005 else f"{p:.3f}" if p < 0.1 else f"{p:.2f}")   # noqa: E731
CH = {}
NAME = {"V1": "CAPE in the top tenth of all history", "VA": "CAPE above its own 10-year median", "VB": "CAPE in the top third of its last 20 years", "V3": "Stocks dear against bonds (earnings yield less real yield, lowest quarter)",
        "RA": "10-year yield above its 5-year average", "RB": "10-year yield above its 1-year average", "R1": "10-year yield up more than 0.50 in a quarter", "R3": "Curve inverted (10-year below 3-month)",
        "R7": "Fed funds up more than 0.25 in six months", "OA": "Oil above its 200-day average", "OB": "Oil up more than 25% in a quarter", "O1": "Oil up more than 50% in a year",
        "TA.SPY": "S&P 500 above its 200-day average", "TA.QQQ": "QQQ above its 200-day average"}
for x in ("SPY", "QQQ"):
    for k, kn in (("s", "simple"), ("e", "exponential")):
        for n in (20, 50):
            NAME[f"SU.{x}.{k}.{n}"] = f"{x} stretched above its {n}-day {kn} average"
            NAME[f"SD.{x}.{k}.{n}"] = f"{x} washed out below its {n}-day {kn} average"
FAM = [("Valuation", ["VA", "VB", "V1", "V3"]), ("Rates", ["RA", "RB", "R1", "R3", "R7"]), ("Oil", ["OA", "OB", "O1"]), ("Trend", ["TA.SPY", "TA.QQQ"]),
       ("Stretched up", [k for k in ST if k.startswith("SU.")]), ("Washed out", [k for k in ST if k.startswith("SD.")])]


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


def verdict_of(sid):
    """PREREG 'What counts', read literally, in the better direction on the verdict sample"""
    v = ST[sid].get("verdict")
    if v is None:
        return "not scored"
    k = "on_high" if v["on_high"]["d_growth"] >= v["on_low"]["d_growth"] else "on_low"
    a, why = v[k], []
    if not ((a["d_growth"] > 0 and a["d_maxdd"] <= 0.01) or (a["d_maxdd"] <= -0.03 and a["d_growth"] >= 0)):
        why.append("no gain over the constant book")
    if a.get("p_holm", 1) >= 0.05:
        why.append("not distinguishable after correction" if sid in PRIM else "not a primary state")
    s = ST[sid].get("shape")
    if s is None or s[k]["d_growth"] <= 0:
        why.append("no gain on the rebuilt years")
    if v["one_close_late"][k]["d_growth"] <= 0:
        why.append("gone one close late")
    if v["lag2"][k]["d_growth"] <= 0:
        why.append("gone with a two-session lag")
    wo = a["d_growth_without_2020_2022"]
    if wo is not None and wo <= 0:
        why.append("gone without 2020 and 2022")
    if v["regimes"] < 6:
        why.append("fewer than 6 on-regimes" + (f" ({v['regimes_off']} off-regimes)" if v["regimes_off"] >= 6 else ""))
    return ("passes" if not why else "fails: " + "; ".join(why)), k


def row(sid, sample="verdict"):
    v = ST[sid].get(sample)
    if v is None:
        return [("<b>%s</b>" if sid in PRIM else "%s") % NAME[sid]] + ["not scored"] + [""] * 9
    a, b = v["on_high"], v["on_low"]
    hp = lambda x: f"; {pv(x['p_holm'])} after 9" if sid in PRIM and sample == "verdict" and "p_holm" in x else ""   # noqa: E731
    return [("<b>%s</b>" if sid in PRIM else "%s") % NAME[sid], pu(v["on_share"]), f"{v['regimes']} / {v['regimes_off']} ({v['switches_per_yr']:.0f} a year)",
            f"{lg(v['sleeve_minus_others_per_yr']['on'], 2)} / {lg(v['sleeve_minus_others_per_yr']['off'], 2)}",
            f"{lg(a['d_growth'])} ({pp(a['d_maxdd'])} pts)", f"p {pv(a['p_newey_west'])}{hp(a)}", f"{lg(b['d_growth'])} ({pp(b['d_maxdd'])} pts)", f"p {pv(b['p_newey_west'])}{hp(b)}",
            f"{lg(v['one_close_late']['on_high']['d_growth'])} / {lg(v['one_close_late']['on_low']['d_growth'])}", f"{lg(v['lag2']['on_high']['d_growth'])} / {lg(v['lag2']['on_low']['d_growth'])}",
            f"{lg(a['d_growth_without_2020_2022'])} / {lg(b['d_growth_without_2020_2022'])}"]


HEAD = ["State (bold = primary)", "Share of days on", "Regimes on / off (switches)", "Sleeve less the other two, a year: on / off", "More sleeve while on: growth vs constant book (deepest fall)", "its p",
        "Less sleeve while on (the mirror)", "its p", "One close late: more / less", "Two-session lag: more / less", "Without 2020 and 2022: more / less"]
STR = (("shape", "1994-06 to 2015-05 (rebuilt)"), ("mid", "2015-06 to 2020-11"), ("real", "2021-06 on (all real)"), ("verdict", "2015-06 on, both"))
cellx = lambda sid, sm, k: "n/a" if sm not in ST[sid] else f"{lg(ST[sid][sm][k]['d_growth'])} (p {pv(ST[sid][sm][k]['p_newey_west'])})"   # noqa: E731
t_stretch = table(["Primary state", "Direction"] + [lab for _, lab in STR],
                  [r for sid in PRIM for r in ([NAME[sid], "more sleeve while on"] + [cellx(sid, sm, "on_high") for sm, _ in STR], ["", "less sleeve while on"] + [cellx(sid, sm, "on_low") for sm, _ in STR])])
WO = [k for k in ST if k.startswith("SD.")]
t_washed = table(["Washed-out state", "Less sleeve while on: 1994 to 2015", "2015-06 to 2020-11", "2021-06 on (all real)", "all real, one close late", "all real, without 2022"],
                 [[NAME[k], cellx(k, "shape", "on_low"), cellx(k, "mid", "on_low"), cellx(k, "real", "on_low"), lg(ST[k]["real"]["one_close_late"]["on_low"]["d_growth"]),
                   lg(ST[k]["real"]["on_low"]["d_growth_without_2020_2022"])] for k in WO])
t_prim = table(HEAD, [row(s) for s in PRIM])
t_prim_shape = table(HEAD, [row(s, "shape") for s in PRIM])
t_all = "".join(f"<h4>{f}</h4>" + table(HEAD, [row(s) for s in ids]) for f, ids in FAM)
t_all_shape = "".join(f"<h4>{f}</h4>" + table(HEAD, [row(s, "shape") for s in ids]) for f, ids in FAM)
t_rule = table(["Primary state", "Better direction since 2015-06", "Growth vs constant book", "By the rule set in advance"],
               [[NAME[s], "more sleeve while on" if verdict_of(s)[1] == "on_high" else "less sleeve while on", lg(ST[s]["verdict"][verdict_of(s)[1]]["d_growth"]), verdict_of(s)[0]] for s in PRIM])
n_pass = sum(verdict_of(s)[0] == "passes" for s in PRIM)
SH = {"VA": "CAPE>10y", "V3": "Dear vs bonds", "RA": "Yield>5y", "R1": "Yield up", "OA": "Oil>200d", "SU.SPY.s.50": "SPY stretched", "SD.SPY.s.50": "SPY washed", "SU.QQQ.s.50": "QQQ stretched", "TA.SPY": "SPY>200d"}
CH["c_v"] = {"type": "bars", "yfmt": "raw", "every": 1, "cats": [NAME[s] for s in PRIM], "short": [SH[s] for s in PRIM], "vals": [ST[s]["verdict"]["on_high"]["d_growth"] * 100 for s in PRIM]}
CH["c_s"] = {"type": "bars", "yfmt": "raw", "every": 1, "cats": [NAME[s] for s in PRIM], "short": [SH[s] for s in PRIM], "vals": [ST[s]["shape"]["on_high"]["d_growth"] * 100 for s in PRIM]}
CS = ["SU.SPY.s.50", "SD.SPY.s.50", "VA"]
CH["c_cum"] = {"type": "line", "yfmt": "raw", "zero": True, "series": [{"name": NAME[s], "slot": i + 1, "pts": D["curves"][s]} for i, s in enumerate(CS)]}
fx = lambda sm, wt: f"{lg(FX[sm][wt]['growth'], 2)} a year, fall {pu(FX[sm][wt]['maxdd'])}"   # noqa: E731
FL = D["fixed_late"]
fl = lambda sm, wt: f"{lg(FL[sm][wt]['growth'], 2)} a year, fall {pu(FL[sm][wt]['maxdd'])}"   # noqa: E731
t_fixed = table(["Constant sleeve weight", "2015-06 on", "the same, one close late (a bound)", "1994 to 2015 (rebuilt)", "2021-06 on (all real)"],
                [[lab, fx("verdict", wt), fl("verdict", wt), fx("shape", wt), fx("real", wt)] for wt, lab in (("0.150", "15%"), ("0.318", "31.8% (today)"), ("0.500", "50%"))])
V = lambda s, k="on_high", sm="verdict": ST[s][sm][k]                                       # noqa: E731
best = max(((s, k) for s in ST for k in ("on_high", "on_low") if "verdict" in ST[s]), key=lambda z: ST[z[0]]["verdict"][z[1]]["d_growth"])
gap = FX["verdict"]["0.150"]["growth"] - FX["verdict"]["0.500"]["growth"]
gap_late = FL["verdict"]["0.150"]["growth"] - FL["verdict"]["0.500"]["growth"]
worst = min(ST[s_]["verdict"][k]["d_growth"] for s_ in ST for k in ("on_high", "on_low") if "verdict" in ST[s_])
su, sd, va, tq = ST["SU.SPY.s.50"], ST["SD.SPY.s.50"], ST["VA"], ST["TA.QQQ"]
sul, sdl = su["verdict"]["on_low"], sd["verdict"]["on_low"]
dv = lambda st, sm, k="on_low": lg(st[sm][k]["d_growth"])                                  # noqa: E731
dp = lambda st, sm, k="on_low": pv(st[sm][k]["p_newey_west"])                              # noqa: E731
subs = {
    "{{t_prim}}": t_prim, "{{t_prim_shape}}": t_prim_shape, "{{t_all}}": t_all, "{{t_all_shape}}": t_all_shape, "{{t_rule}}": t_rule, "{{t_fixed}}": t_fixed,
    "{{t_stretch}}": t_stretch, "{{t_washed}}": t_washed,
    "{{gap_late}}": lg(gap_late, 2), "{{late_dd}}": f"{pu(FL['verdict']['0.500']['maxdd'])} to {pu(FL['verdict']['0.150']['maxdd'])}", "{{worst}}": lg(worst), "{{worst_share}}": pu(abs(worst) / gap),
    "{{best_share}}": pu(ST[best[0]]["verdict"][best[1]]["d_growth"] / gap),
    "{{va_hi_shape_late}}": lg(va["shape"]["one_close_late"]["on_high"]["d_growth"]),
    "{{su_lo_p}}": pv(sul["p_newey_west"]), "{{su_lo_holm}}": pv(sul["p_holm"]), "{{su_2020}}": pu(sul["by_year"]["2020"] / sul["sum_of_daily_edge"]),
    "{{su_lo_real}}": dv(su, "real"), "{{su_lo_mid}}": dv(su, "mid"), "{{su_best20}}": pu(sul["best_20_sessions"] / sul["sum_of_daily_edge"]),
    "{{su_reg_real}}": str(su["real"]["regimes"]), "{{suq_lo_p}}": dp(ST["SU.QQQ.s.50"], "verdict"), "{{suq_lo_real}}": dv(ST["SU.QQQ.s.50"], "real"),
    "{{su_vol}}": pu(su["verdict"]["spread_vol"]["on"] / su["verdict"]["spread_vol"]["off"] - 1), "{{su_shift}}": pv(su["verdict"]["p_shift"]),
    "{{sd_lo_p_shape}}": dp(sd, "shape"), "{{sd_lo_real}}": dv(sd, "real"), "{{sd_lo_p_real}}": dp(sd, "real"), "{{sd_reg_real}}": str(sd["real"]["regimes"]),
    "{{sd_lo_mid}}": dv(sd, "mid"), "{{sd_2020}}": lg(sdl["by_year"]["2020"], 2), "{{sd_lo_dd}}": pp(sdl["d_maxdd"]),
    "{{sd_2022}}": pu(sd["real"]["on_low"]["by_year"]["2022"] / sd["real"]["on_low"]["sum_of_daily_edge"]),
    "{{sd20_real}}": f"{dv(ST['SD.SPY.s.20'], 'real')} (p {dp(ST['SD.SPY.s.20'], 'real')}; one close late {lg(ST['SD.SPY.s.20']['real']['one_close_late']['on_low']['d_growth'])}; two-session lag {lg(ST['SD.SPY.s.20']['real']['lag2']['on_low']['d_growth'])})",
    "{{tq_real}}": lg(tq["real"]["on_high"]["d_growth"]), "{{tq_mid}}": lg(tq["mid"]["on_high"]["d_growth"]), "{{tq_lag2}}": lg(tq["verdict"]["lag2"]["on_high"]["d_growth"]), "{{tq_off}}": str(tq["verdict"]["regimes_off"]),
    "{{va_lo_p_shape}}": dp(va, "shape"), "{{va_lo_late_shape}}": lg(va["shape"]["one_close_late"]["on_low"]["d_growth"]),
    "{{v3_lo_shape}}": dv(ST["V3"], "shape"), "{{v3_lo_p_shape}}": dp(ST["V3"], "shape"), "{{v3_lo_late_shape}}": lg(ST["V3"]["shape"]["one_close_late"]["on_low"]["d_growth"]),
    "{{oa_p}}": pv(ST["OA"]["verdict"]["on_high"]["p_newey_west"]),
    "{{sd_real_dd}}": f"{min(ST[k]['real']['on_low']['d_maxdd'] for k in WO) * 100:.1f} to {max(ST[k]['real']['on_low']['d_maxdd'] for k in WO) * 100:.1f}",
    "{{sd_lo_ddabs}}": f"{abs(sdl['d_maxdd']) * 100:.1f}", "{{tq_ddabs}}": f"{abs(tq['verdict']['on_high']['d_maxdd']) * 100:.1f}",
    "{{n_pass}}": str(n_pass), "{{n_states}}": str(len(ST)),
    "{{best_name}}": NAME[best[0]], "{{best_dir}}": "more" if best[1] == "on_high" else "less", "{{best_dg}}": lg(ST[best[0]]["verdict"][best[1]]["d_growth"]),
    "{{gap}}": lg(gap, 2), "{{g15}}": lg(FX["verdict"]["0.150"]["growth"], 2), "{{g50}}": lg(FX["verdict"]["0.500"]["growth"], 2),
    "{{dd15}}": pu(FX["verdict"]["0.150"]["maxdd"]), "{{dd50}}": pu(FX["verdict"]["0.500"]["maxdd"]),
    "{{su_hi}}": lg(su["verdict"]["on_high"]["d_growth"]), "{{su_lo}}": lg(su["verdict"]["on_low"]["d_growth"]), "{{su_p}}": pv(su["verdict"]["on_high"]["p_newey_west"]), "{{su_holm}}": pv(su["verdict"]["p_holm"]),
    "{{su_spread}}": f"{lg(su['verdict']['sleeve_minus_others_per_yr']['on'], 2)} against {lg(su['verdict']['sleeve_minus_others_per_yr']['off'], 2)}",
    "{{su_lo_shape}}": lg(su["shape"]["on_low"]["d_growth"]), "{{su_lo_late}}": lg(su["verdict"]["one_close_late"]["on_low"]["d_growth"]), "{{su_lo_wo}}": lg(su["verdict"]["on_low"]["d_growth_without_2020_2022"]),
    "{{su_reg}}": str(su["verdict"]["regimes"]), "{{su_share}}": pu(su["verdict"]["on_share"]), "{{su_lo_dd}}": pp(su["verdict"]["on_low"]["d_maxdd"]),
    "{{suq_lo}}": lg(ST["SU.QQQ.s.50"]["verdict"]["on_low"]["d_growth"]), "{{suq_p}}": pv(ST["SU.QQQ.s.50"]["verdict"]["on_high"]["p_newey_west"]),
    "{{sd_lo_shape}}": lg(sd["shape"]["on_low"]["d_growth"]), "{{sd_p_shape}}": pv(sd["shape"]["on_high"]["p_newey_west"]), "{{sd_lo}}": lg(sd["verdict"]["on_low"]["d_growth"]),
    "{{sd_lo_late_shape}}": lg(sd["shape"]["one_close_late"]["on_low"]["d_growth"]), "{{sd_reg_shape}}": str(sd["shape"]["regimes"]),
    "{{sd_spread_shape}}": f"{lg(sd['shape']['sleeve_minus_others_per_yr']['on'], 2)} against {lg(sd['shape']['sleeve_minus_others_per_yr']['off'], 2)}",
    "{{va_hi_shape}}": lg(va["shape"]["on_high"]["d_growth"]), "{{va_lo_shape}}": lg(va["shape"]["on_low"]["d_growth"]), "{{va_p_shape}}": pv(va["shape"]["on_high"]["p_newey_west"]), "{{va_reg_shape}}": str(va["shape"]["regimes"]),
    "{{va_on}}": pu(va["verdict"]["on_share"]), "{{va_hi}}": lg(va["verdict"]["on_high"]["d_growth"]), "{{v1_on}}": pu(ST["V1"]["verdict"]["on_share"]),
    "{{v3_hi_shape}}": lg(ST["V3"]["shape"]["on_high"]["d_growth"]), "{{v3_p_shape}}": pv(ST["V3"]["shape"]["on_high"]["p_newey_west"]), "{{v3_reg_shape}}": str(ST["V3"]["shape"]["regimes"]),
    "{{tq_hi}}": lg(tq["verdict"]["on_high"]["d_growth"]), "{{tq_p}}": pv(tq["verdict"]["on_high"]["p_newey_west"]), "{{tq_hi_shape}}": lg(tq["shape"]["on_high"]["d_growth"]), "{{tq_p_shape}}": pv(tq["shape"]["on_high"]["p_newey_west"]),
    "{{tq_dd}}": pp(tq["verdict"]["on_high"]["d_maxdd"]), "{{tq_late}}": lg(tq["verdict"]["one_close_late"]["on_high"]["d_growth"]), "{{tq_reg}}": str(tq["verdict"]["regimes"]),
    "{{oa_hi}}": lg(ST["OA"]["verdict"]["on_high"]["d_growth"]), "{{oa_hi_shape}}": lg(ST["OA"]["shape"]["on_high"]["d_growth"]),
    "{{ra_hi}}": lg(ST["RA"]["verdict"]["on_high"]["d_growth"]), "{{r1_hi}}": lg(ST["R1"]["verdict"]["on_high"]["d_growth"]),
    "{{ch_v}}": chart("c_v", "More sleeve while the state is on: growth against the constant book, 2015-06 on", "Hundredths of a log-point a year (1 = about 1% more growth a year). The mirror, less sleeve while on, is roughly the same bar upside down."),
    "{{ch_s}}": chart("c_s", "The same on 1994 to 2015 (rebuilt and modelled funds)", "Hundredths of a log-point a year."),
    "{{ch_cum}}": chart("c_cum", "What three of the switches added or lost over time", "Running total of the policy's daily growth less the constant book's, from 1994 (more sleeve while the state is on). A rule that worked would climb steadily. Each stretch is measured against its own average weight; the yardstick resets at 2015-06."),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Dynamic Sleeve Weight</title>"),):
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
print("wrote", OUT, len(BODY) // 1024, "KB; pass", n_pass, "of", len(PRIM), "| best", best, {s: verdict_of(s)[0][:60] for s in PRIM})
