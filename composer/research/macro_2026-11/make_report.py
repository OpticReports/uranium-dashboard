"""Build the HTML report of the macro study from out/*.json. Usage: python3 make_report.py OUT_HTML"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda k: json.load(open(os.path.join(HERE, "out", f"{k}.json")))                     # noqa: E731
M, F, C, LI, RV, RB = J("macro"), J("followup"), J("charts"), J("leanin"), J("review"), J("robust")
OUT = sys.argv[1]
lg = lambda x, d=2: "n/a" if x is None else f"{x:+.{d}f}"                                  # noqa: E731
pu = lambda x, d=0: f"{x * 100:.{d}f}%"                                                    # noqa: E731
pp = lambda x, d=1: f"{x * 100:+.{d}f} pts"                                                # noqa: E731
pv = lambda p: "n/a" if p is None else ("&lt;0.001" if p < 0.0005 else f"{p:.3f}" if p < 0.1 else f"{p:.2f}")   # noqa: E731
CH = {}
MAP, P1, P2, RE = M["map"], M["p1"], M["p2"], M["reentry"]
BV, BS, BR = MAP["BOOK.verdict"]["states"], MAP["BOOK.shape"]["states"], MAP["BOOK.real"]["states"]
REG = F["regimes"]["BOOK"]
NAME = {"F_RATES": "Rates and curve", "F_INFLATION": "Inflation", "F_VALUATION": "Valuation (CAPE)", "F_GOLD": "Gold strong", "F_CREDIT": "Credit and financial conditions",
        "F_DOLLAR": "Dollar strong", "F_VOLUME": "Volume shock", "F_LIQUIDITY": "Liquidity tight", "F_OIL": "Oil spike", "GC2": "Any 2 of the 9 families", "GC3": "Any 3 of the 9 families",
        "T1": "S&P 500 below its 200-day average (reference)"}
SINGLE = {"R1": "10y yield up more than 0.50 in a quarter", "R2": "2y yield up more than 0.50 in a quarter", "R3": "10y below 3m (inverted)", "R4": "curve steepening after an inversion",
          "R5": "10y below 2y (inverted)", "R6": "10y real yield up more than 0.40 in a quarter", "R7": "fed funds up more than 0.25 in six months",
          "I1": "10y breakeven up more than 0.25 in a quarter", "I2": "CPI inflation 1 point higher than six months before", "I3": "CPI inflation above 4%",
          "V1": "CAPE above its 90th percentile to date", "V2": "CAPE down more than 10% in a year", "V3": "stock yield minus real bond yield in its lowest quarter to date",
          "G1": "gold above its 200-day average", "G2": "gold/S&P above its 200-day average", "G3": "gold up more than 10% in a year after inflation", "G4": "copper/gold below its 200-day average",
          "G5": "gold up more than 10% in a quarter", "C1": "Baa spread up more than 0.30 in a quarter", "C2": "Baa spread above its 80th percentile to date", "C3": "financial conditions index above zero",
          "C4": "financial conditions index up more than 0.15 in a quarter", "D1": "dollar above its 200-day average", "D2": "dollar up more than 5% in a quarter",
          "M1": "S&P volume 25% above its yearly average", "M2": "S&P volume 15% below its yearly average", "M3": "more than 60% of a month's volume on down days",
          "L1": "M2 growth below 5% and slowing", "L2": "Fed balance sheet smaller than six months before", "O1": "oil up more than 50% in a year", "T1": NAME["T1"]}
SHORT = {"F_RATES": "Rates", "F_INFLATION": "Inflation", "F_VALUATION": "CAPE", "F_GOLD": "Gold", "F_CREDIT": "Credit", "F_DOLLAR": "Dollar", "F_VOLUME": "Volume", "F_LIQUIDITY": "Liquidity", "F_OIL": "Oil",
         "GC2": "Any 2", "GC3": "Any 3"}
FAMS = M["meta"]["families"]
PRIM = M["meta"]["primary"]


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def chart(cid, title, cap):
    return f'<div class="chart"><h4>{title}</h4><p class="cap">{cap}</p><div id="{cid}"></div></div>'


FROM = {"RATES": "1962 (real yield 2003)", "INFLATION": "1947 (breakeven 2003)", "VALUATION": "1881", "GOLD": "daily 2000-09; monthly 1971", "CREDIT": "1986 (conditions index 1971)", "DOLLAR": "1971",
        "VOLUME": "1970", "LIQUIDITY": "1959 (Fed balance sheet 2002-12)", "OIL": "1986"}
t_design = table(["Family", "States (each is the risk-off reading, fixed in advance)", "Data from"],
                 [[f.capitalize(), "; ".join(SINGLE[s] for s in ss), FROM[f]] for f, ss in FAMS.items()]
                 + [["Cross-engine", "Holy Grail's gate off; KMLM switch risk-off; sleeve's shock ladder out of cash; sleeve's inverse-fund test on; two of those three", "the engines' own history"],
                    ["Re-entry", "Baa spread narrowed 0.20 in a quarter; financial conditions easing over a quarter; S&P above its 50-day average (scored on Holy Grail's gate-off days only)", "1986"]])
NWV, NWS = RV["nw"]["verdict"], RV["nw"]["shape"]
oo = lambda r: "not scored" if r is None else f"{lg(r['on_per_yr'])} vs {lg(r['off_per_yr'])}"                                 # noqa: E731
rows = []
for sid in PRIM + ["T1"]:
    v, s = BV.get(sid), BS.get(sid)
    rg = REG.get(sid, {})
    rows.append([NAME[sid], "too rare" if v is None else pu(v["on_share"]), f"{rg.get('merged_regimes', '')} ({rg.get('switches_on', '')})", oo(v), "" if v is None else lg(v["diff_per_yr"]),
                 "" if v is None else pv(v["p_two_sided"]), "" if v is None or "p_holm" not in v else pv(v["p_holm"]), "" if sid not in NWV else pv(max(NWV[sid])), oo(s),
                 "" if s is None else f"{lg(s['diff_per_yr'])} (p {pv(s['p_two_sided'])}; {pv(max(NWS[sid])) if sid in NWS else 'n/a'})"])
t_map = table(["State", "Share of days on, 2015-06 on", "Regimes (switches)", "Book growth on vs off, 2015-06 on", "Difference", "Shift p", "after 11", "Second test p", "On vs off, 1994-2015 (rebuilt)",
               "Difference (shift p; second test)"], rows)
order = [s for s in PRIM if s in BV]
CH["c_map"] = {"type": "bars", "yfmt": "raw", "cats": [NAME[s] for s in order], "short": [SHORT[s] for s in order], "every": 1, "vals": [BV[s]["diff_per_yr"] for s in order]}
t_singles = table(["Family", "State", "Share of days on", "Book on vs off, 2015-06 on", "Difference (p)", "On vs off, 1994-2015", "Difference (p)"],
                  [[f.capitalize(), SINGLE[s], pu(BV[s]["on_share"]) if s in BV else "", oo(BV.get(s)), f"{lg(BV[s]['diff_per_yr'])} ({pv(BV[s]['p_two_sided'])})" if s in BV else "",
                    oo(BS.get(s)), f"{lg(BS[s]['diff_per_yr'])} ({pv(BS[s]['p_two_sided'])})" if s in BS else ""] for f, ss in FAMS.items() for s in ss])
for cid, sid in (("c_t1", "T1"), ("c_gold", "F_GOLD"), ("c_liq", "F_LIQUIDITY")):
    CH[cid] = {"type": "line", "yfmt": "raw", "series": [{"name": "Earned on days the state was on", "slot": 1, "pts": C[sid]["on"]}, {"name": "Earned on days it was off", "slot": 2, "pts": C[sid]["off"]}]}


def rule(sid):
    """The pre-registered 'what counts' rule for P1 on the book, read literally."""
    v, s = P1["BOOK.verdict"].get(sid), P1["BOOK.shape"].get(sid)
    if v is None:
        return "not scored (too rare)"
    why = []
    better = v["d_growth"] > 0 or (v["d_maxdd"] <= -0.03 and v["d_growth"] >= 0)
    if not better:
        why.append("no gain over the even mix")
    if v.get("p_holm_best_of_growth_or_fall", 1) >= 0.05:
        why.append("not above its shifted copies")
    if better and s is not None and not (s["d_growth"] > 0 or s["d_maxdd"] <= -0.03):
        why.append("opposite on the rebuilt years")
    if better and v["mirror_d_growth"] >= v["d_growth"]:
        why.append("mirror as good")
    if v["episodes"] < 8:
        why.append("fewer than 8 episodes")
    return "passes by the letter" if not why else "fails: " + "; ".join(why)


RULE = {s: rule(s) for s in PRIM}
n_scored = sum(1 for s in PRIM if s in P1["BOOK.verdict"])
n_fail = sum(1 for s in PRIM if RULE[s].startswith("fails"))
rows = []
for sid in PRIM + ["T1"]:
    v, s = P1["BOOK.verdict"].get(sid), P1["BOOK.shape"].get(sid)
    if v is None:
        rows.append([NAME[sid], "too rare"] + [""] * 6 + [f"{lg(s['d_growth'], 3)}, {pp(s['d_maxdd'])}" if s else "", RULE.get(sid, "")])
        continue
    rows.append([NAME[sid], pu(v["avg_exposure"]), f"{lg(v['growth'])} vs {lg(v['growth_mix'])}", lg(v["d_growth"], 3), pv(v["p_growth"]), f"{pu(v['maxdd'], 1)} vs {pu(v['maxdd_mix'], 1)} ({pp(v['d_maxdd'])})",
                 pv(v["p_maxdd"]), lg(v["mirror_d_growth"], 3), f"{lg(s['d_growth'], 3)}, {pp(s['d_maxdd'])}" if s else "", RULE.get(sid, "reference; harmful" if v["d_growth"] < 0 else "reference")])
t_p1 = table(["De-risk to half while on", "Average exposure", "Growth: timed vs evenly held", "Difference", "p", "Deepest fall: timed vs even", "p", "Mirror (de-risk while off): growth difference",
              "1994-2015 (rebuilt): growth, fall", "By the rule set in advance"], rows)
OT = F["others"]
SP = (("verdict", "2015-06 on"), ("real_2021_06_on", "of which 2021-06 on (all real)"), ("mostly_real_2015_2020", "of which 2015-06 to 2020-12"), ("shape", "1994-2015 (rebuilt)"))
XN = {"X1_gate_off": ("Holy Grail's gate is off", "KMLM", "SLEEVE"), "X3_ladder_fired": ("The sleeve's shock ladder is out of cash", "HG", "KMLM")}
EN = {"HG": "Holy Grail", "KMLM": "KMLM", "SLEEVE": "Sleeve", "BOOK": "Book"}
rows = []
for xk, (nm, a, b) in XN.items():
    for k, lab in SP:
        v = OT[xk][k]
        rows.append([nm, lab, pu(v["on_share"]), v["merged_regimes"], f"{lg(v['on_per_yr'])} vs {lg(v['off_per_yr'])}", f"{lg(v['diff_per_yr'])} (p {pv(v['p_two_sided'])})",
                     f"{lg(v[a]['diff_per_yr'])} (p {pv(v[a]['p'])})", f"{lg(v[b]['diff_per_yr'])} (p {pv(v[b]['p'])})", lg(v["own_engine_on_per_yr"])])
t_cross = table(["Signal (known the day before)", "Stretch", "Share of days on", "Regimes", "The other two engines: growth on vs off", "Difference (p)", "First other engine alone", "Second other engine alone",
                 "The signalling engine itself on those days"], rows)
XR = {"X2": "KMLM switch risk-off", "X4": "Sleeve's inverse-fund test on", "X5": "Two of gate-off, switch risk-off, inverse test on"}
rows = []
for xk, nm in XR.items():
    for key, v in M["cross"][xk].items():
        e, st = key.split(".")
        if e == "BOOK":
            continue
        rows.append([nm, EN[e], "2015-06 on" if st == "verdict" and e == "SLEEVE" else {"HG.verdict": "2006-07 on", "KMLM.verdict": "2021-06 on"}.get(key, "rebuilt years"), pu(v["on_share"]),
                     f"{lg(v['on_per_yr'])} vs {lg(v['off_per_yr'])}", f"{lg(v['diff_per_yr'])} (p {pv(v['p_two_sided'])})", f"{lg(v['p1']['d_growth'], 3)} (p {pv(v['p1']['p_growth'])})"])
t_cross2 = table(["Signal", "Engine", "Stretch", "Share of days on", "Engine growth next day, on vs off", "Difference (p)", "De-risking that engine on it: growth vs even mix (p)"], rows)
RD = F["redeploy"]
rows = []
for w in RD:
    for k, lab in SP:
        v = RD[w][k]
        rows.append([f"{float(w) * 100:.1f} points" + (" (all of it)" if w == "0.341" else ""), lab, f"{lg(v['policy'][0])} vs {lg(v['fixed'][0])}", f"{lg(v['d_growth'], 3)} (p {pv(v['p_growth'])})",
                     f"{pu(v['policy'][1], 1)} vs {pu(v['fixed'][1], 1)}", lg(v["mirror_d_growth"], 3), f"{v['positive_years']} of {v['years_with_gate_off']}"])
t_redeploy = table(["Weight moved from Holy Grail to the other two while its gate is off", "Stretch", "Book growth: policy vs fixed", "Difference (p)", "Deepest fall: policy vs fixed",
                    "Mirror (move it while the gate is on)", "Years it helped"], rows)
wts = lambda w: "never tilted" if not w else f"HG {w[0] * 100:.0f} / KMLM {w[1] * 100:.0f} / sleeve {w[2] * 100:.0f}"                 # noqa: E731
rows = []
for sid, v in P2["verdict"]["states"].items():
    s = P2["shape"]["states"].get(sid)
    rows.append([NAME[sid], pu(v["share_of_days_tilted"]), wts(v["avg_weights_when_tilted"]), f"{lg(v['d_growth'], 3)} (p {pv(v['p_growth'])})", pv(v["p_holm"]), lg(v["mirror_d_growth"], 3), pp(v["d_maxdd"]),
                 f"{lg(s['d_growth'], 3)} (mirror {lg(s['mirror_d_growth'], 3)})" if s else ""])
t_p2 = table(["Tilt while on", "Share of days tilted, 2015-06 on", "Average weights while tilted", "Book growth vs the fixed book (p)", "p after 10", "Mirror (tilt while off)", "Deepest fall", "1994-2015 (rebuilt): growth (mirror)"], rows)
RN = {"RE1": "Baa spread narrowed more than 0.20 in a quarter", "RE2": "Financial conditions easing over a quarter", "RE3": "S&P 500 above its 50-day average"}
rows = []
for k, lab in (("verdict", "2006-07 on"), ("shape", "1991-2006 (modelled)")):
    for sid, v in RE[k]["states"].items():
        rows.append([RN[sid], lab, RE[k]["gate_off_days"], pu(v["on_share"]), v["episodes"], f"{lg(v['on_per_yr'])} vs {lg(v['off_per_yr'])}", f"{lg(v['diff_per_yr'])} (p {pv(v['p_two_sided'])})", pv(v["p_holm"])])
t_re = table(["Re-entry state", "Stretch", "Gate-off days", "Share with the state on", "Episodes", "Ungated tree less T-bills: state on vs off", "Difference (p)", "p after 3"], rows)
GO, LQ = F["gold_off"]["verdict"], F["liquidity"]["verdict"]
yr = lambda d: [[y, pu(v["on_share"]), lg(v["on_log"]), lg(v["off_log"])] for y, v in d.items()]                                   # noqa: E731
t_years = ("<h4>Gold NOT strong, by year</h4>" + table(["Year", "Share of days gold not strong", "Book log growth earned on those days", "Earned on the other days"], yr(GO["by_year"]))
           + "<h4>Liquidity tight, by year</h4>" + table(["Year", "Share of days tight", "Book log growth earned on those days", "Earned on the other days"], yr(LQ["by_year"])))
X1, X3 = OT["X1_gate_off"], OT["X3_ladder_fired"]
T1v, T1s, G, L = BV["T1"], BS["T1"], BV["F_GOLD"], BV["F_LIQUIDITY"]
PL = P1["BOOK.verdict"]["F_LIQUIDITY"]
R2 = RD["0.200"]["verdict"]
HV = MAP["HG.verdict"]["states"]["F_VOLUME"]
LT = LI["lean_in"]["T1"]
BY = {y: v for y, v in LI["by_year"].items() if y >= "2015"}
tot_b = sum(v["book_log"] for v in BY.values())
eng_sum = {e: sum(v[e] for v in BY.values()) for e in ("HG", "KMLM", "SLEEVE")}
top2 = sorted(BY, key=lambda y: -BY[y]["book_log"])[:2]
lean = lambda v: (f"{lg(v['growth'])} a year against {lg(v['growth_mix'])} for the same cash held evenly (p {pv(v['p_growth'])}) and {lg(v['growth_full'])} for the full book; deepest fall {pu(v['maxdd'], 1)} against "   # noqa: E731
                  f"{pu(v['maxdd_mix'], 1)} and {pu(v['maxdd_full'], 1)}")
T1R, GR, BVR, BSR = RB["t1"], RB["gold"], RB["book_verdict"], RB["book_shape"]
sc, lt = (lambda v: v["same_close"]), (lambda v: v["one_close_late"])                     # noqa: E731
pr = lambda *ps: pv(ps[0]) if pv(min(ps)) == pv(max(ps)) else f"{pv(min(ps))} to {pv(max(ps))}"   # noqa: E731
nwr = lambda v: pr(v["p_newey_west_63"], v["p_newey_west_10"])                             # noqa: E731
allp = lambda v: pr(v["p_two_sided"], v["p_newey_west_63"], v["p_newey_west_10"])          # noqa: E731
RLAB = (("BOOK.verdict", "Book, 2015-06 on"), ("BOOK.2015-06..2020-12", "of which 2015-06 to 2020-12"), ("BOOK.real", "of which 2021-06 on (all real)"), ("BOOK.shape", "Book, 1994-2015 (rebuilt)"),
        ("HG.verdict", "Holy Grail, 2006-07 on"), ("HG.real", "Holy Grail, 2015-09 on (real)"), ("HG.shape", "Holy Grail, 1991-2006 (modelled)"),
        ("KMLM.verdict", "KMLM, 2021-06 on (real)"), ("KMLM.shape", "KMLM, 1991-2020 (rebuilt)"),
        ("SLEEVE.verdict", "Sleeve, 2015-06 on"), ("SLEEVE.real", "Sleeve, 2020-12 on (real)"), ("SLEEVE.shape", "Sleeve, 1994-2015 (rebuilt)"))
t_robust = table(["", "Days below the average", "Regimes (above the off-days' rate)", "Study's paths: below vs above", "Difference", "Shift p", "Second test p", "One close late: below vs above", "Difference", "Second test p"],
                 [[lab, f"{round(sc(T1R[k])['n'] * sc(T1R[k])['on_share']):,}", f"{sc(T1R[k])['regimes']} ({sc(T1R[k])['regimes_above_off_rate']})", oo(sc(T1R[k])), lg(sc(T1R[k])["diff_per_yr"]), pv(sc(T1R[k])["p_two_sided"]),
                   nwr(sc(T1R[k])), oo(lt(T1R[k])), lg(lt(T1R[k])["diff_per_yr"]), nwr(lt(T1R[k]))] for k, lab in RLAB])
BARS = (("BOOK.verdict", "Book 2015-06 on"), ("BOOK.real", "Book 2021-06 on"), ("BOOK.shape", "Book rebuilt"), ("HG.verdict", "Holy Grail"), ("KMLM.verdict", "KMLM"), ("SLEEVE.verdict", "Sleeve"))
CH["c_late"] = {"type": "bars", "yfmt": "raw", "every": 1, "cats": [f"{lab}, {w}" for k, lab in BARS for w in ("study's path", "one close late")],
                "short": [x for k, lab in BARS for x in (lab.replace("Book ", "Book, ").replace("Holy Grail", "HG"), "late")],
                "vals": [f_(T1R[k])["diff_per_yr"] for k, lab in BARS for f_ in (sc, lt)]}
CV = RB["curves"]["BOOK"]
CH["c_curve"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.5, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000],
                 "series": [{"name": "Book, trades at the signal's close (the study's path)", "slot": 1, "pts": CV["same_close"]}, {"name": "Book, every trade one close late", "slot": 2, "pts": CV["one_close_late"]}]}
TB_, BL, AT, GRG, DL, VH, X1R = RB["t1_book"], RB["book_late"], RB["after_trade"], RB["gold_regime"], RB["dollar"], RB["volume_hg"], RB["x1"]
PD = P1["BOOK.verdict"]["F_DOLLAR"]
SN = {"C1": "Baa spread up more than 0.30 in a quarter", "M1": "volume 25% above its yearly average", "M3": "more than 60% of volume on down days"}
XC = M["cross"]
LQV, LQS, XR, PA = RV["liquidity"]["verdict"], RV["liquidity"]["shape"], RV["x1"], RV["p2_always_on"]
LB = LQV["largest_off_block"]
xw = XR["without_top_two"]
subs = {
    "{{t1_p1abs}}": f"{abs(P1['BOOK.verdict']['T1']['d_growth']):.3f}",
    "{{l_p1p}}": pv(PL["p_growth"]), "{{l_p1h}}": pv(PL["p_holm_best_of_growth_or_fall"]),
    "{{t1_yrs}}": f"{TB_['years_on_rate_higher']} of {TB_['years_with_both']}", "{{t1_nw}}": nwr(sc(T1R["BOOK.verdict"])),
    "{{t1_2y_days}}": pu(TB_["share_of_on_days_2020_2022"]), "{{t1_2y_log}}": pu(TB_["share_of_on_log_2020_2022"]),
    "{{t1_wo}}": f"{lg(TB_['without_2020_2022']['on_per_yr'])} against {lg(TB_['without_2020_2022']['off_per_yr'])} (p {allp(TB_['without_2020_2022'])})",
    "{{t1_late_s}}": lg(lt(T1R["BOOK.shape"])["diff_per_yr"]), "{{t1_late_k}}": lg(lt(T1R["KMLM.verdict"])["diff_per_yr"]),
    "{{t1_late_on}}": lg(lt(T1R["BOOK.verdict"])["on_per_yr"]), "{{t1_late_off}}": lg(lt(T1R["BOOK.verdict"])["off_per_yr"]), "{{t1_late_p}}": nwr(lt(T1R["BOOK.verdict"])),
    "{{x1_same}}": pu(X1R["verdict"]["same_reading_as_T1"]), "{{x1_nw}}": nwr(sc(X1R["verdict"])), "{{rd_p}}": pv(R2["p_growth"]),
    "{{x1_late}}": "; ".join(f"{lab}: {lg(lt(X1R[k])['diff_per_yr'])} (p {nwr(lt(X1R[k]))})" for k, lab in SP),
    "{{g_nw}}": nwr(sc(GR["BOOK.verdict"])), "{{g_e4}}": lg(sc(GR["BOOK.2015-06..2020-12"])["diff_per_yr"]), "{{g_real_d}}": lg(sc(GR["BOOK.real"])["diff_per_yr"]),
    "{{g_real_p}}": pv(sc(GR["BOOK.real"])["p_two_sided"]), "{{g_shape_d}}": lg(sc(GR["BOOK.shape"])["diff_per_yr"]),
    "{{g_late}}": f"{lg(lt(GR['BOOK.verdict'])['diff_per_yr'])} (p {allp(lt(GR['BOOK.verdict']))})",
    "{{bl_same}}": lg(BL["same_close"][0]), "{{bl_late}}": lg(BL["one_close_late"][0]), "{{bl_dd_same}}": pu(BL["same_close"][1]), "{{bl_dd_late}}": pu(BL["one_close_late"][1]),
    "{{bl_eng}}": ", ".join(f"{EN[e]} {lg(v[0])} to {lg(v[1])}" for e, v in BL["by_engine"].items()),
    "{{at_txt}}": ", ".join(f"{EN[e]} {pu(v['share_of_T1_on_growth_in_session_after_a_trade'])} (on {pu(v['share_of_T1_on_days_after_a_trade'])} of those days)" for e, v in AT.items()),
    "{{t1_top20}}": pu(TB_["share_of_on_log_from_20_best_days"]), "{{t1_mv}}": f"{TB_['mean_over_vol_on']:.1f} against {TB_['mean_over_vol_off']:.1f}",
    "{{d_txt}}": f"by {abs(PD['d_maxdd']) * 100:.1f} points, p {pv(PD['p_maxdd'])}; {pv(PD['p_holm_best_of_growth_or_fall'])} after correction",
    "{{d_fall}}": f"{DL['book_deepest_fall'][0]} to {DL['book_deepest_fall'][1]}", "{{d_share}}": pu(DL["share_of_that_fall_with_dollar_on"]),
    "{{gt_v}}": lg(RB["gate"]["2006-07 on"]["live_gated_tree_less_tbills_per_yr"]), "{{gt_s}}": lg(RB["gate"]["1991-2006"]["live_gated_tree_less_tbills_per_yr"]),
    "{{t1_n}}": f"{RB['counts']['T1_on_days']:,}", "{{t1_reg}}": str(sc(T1R["BOOK.verdict"])["regimes"]), "{{t1_reg_up}}": str(sc(T1R["BOOK.verdict"])["regimes_above_off_rate"]),
    "{{g2_txt}}": f"{lg(sc(BVR['G2'])['diff_per_yr'])}, p {allp(sc(BVR['G2']))}; one close late {lg(lt(BVR['G2'])['diff_per_yr'])}",
    "{{gr_span}}": f"{GRG['from'][:7]} to {GRG['to'][:7]}", "{{gr_share}}": pu(GRG["share_of_on_log"]), "{{gr_wo}}": f"{lg(GRG['without']['diff_per_yr'])} (p {allp(GRG['without'])})",
    "{{g_eng_own}}": ", ".join(f"{EN[e]} {lg(sc(GR[e + '.verdict'])['diff_per_yr'])} (p {pv(sc(GR[e + '.verdict'])['p_two_sided'])})" for e in ("HG", "KMLM", "SLEEVE")),
    "{{g_k_all}}": lg(-GO["per_engine_diff"]["KMLM"]["diff_per_yr"]),
    "{{l_nw}}": nwr(sc(BVR["F_LIQUIDITY"])), "{{l_late}}": f"{lg(lt(BVR['F_LIQUIDITY'])['diff_per_yr'])} (p {allp(lt(BVR['F_LIQUIDITY']))})",
    "{{lq_within}}": f"each of the {LQV['years_tight_days_earned_less']}" if LQV["years_tight_days_earned_less"] == LQV["years_with_both"] else f"{LQV['years_tight_days_earned_less']} of the {LQV['years_with_both']}",
    "{{same_txt}}": "; ".join(f"{SN[k]}: {lg(sc(BVR[k])['diff_per_yr'])} (shift p {pv(sc(BVR[k])['p_two_sided'])}, second test {nwr(sc(BVR[k]))}), rebuilt {lg(sc(BSR[k])['diff_per_yr'])} "
                              f"(p {pv(sc(BSR[k])['p_two_sided'])}), {pu(BVR[k]['share_of_on_days_with_T1_on'])} of its days are below-average days, one close late {lg(lt(BVR[k])['diff_per_yr'])} and {lg(lt(BSR[k])['diff_per_yr'])}"
                              for k in SN),
    "{{x25_txt}}": f"{lg(XC['X2']['SLEEVE.verdict']['diff_per_yr'])} and {lg(XC['X5']['SLEEVE.verdict']['diff_per_yr'])} a year, shift p {pv(XC['X2']['SLEEVE.verdict']['p_two_sided'])} and {pv(XC['X5']['SLEEVE.verdict']['p_two_sided'])}",
    "{{vol_n}}": str(VH["on_days"]), "{{vol_reg}}": str(sc(VH)["regimes"]), "{{vol_nw}}": nwr(sc(VH)), "{{vol_top3}}": pu(VH["share_of_on_log_from_3_best_days"]),
    "{{vol_late}}": f"at a rate of {lg(lt(VH)['on_per_yr'])}",
    "{{re1_txt}}": f"{lg(RE['verdict']['states']['RE1']['diff_per_yr'])} a year, p {pv(RE['verdict']['states']['RE1']['p_two_sided'])}, since 2006-07; {lg(RE['shape']['states']['RE1']['diff_per_yr'])}, p {pv(RE['shape']['states']['RE1']['p_two_sided'])}, before",
    "{{t_robust}}": t_robust,
    "{{ch_late}}": chart("c_late", "Growth rate below the 200-day average less the rate above it: the study's path, then one close late", "Log-points a year. Each pair is one sample; the second bar fills every trade one close later."),
    "{{ch_curve}}": chart("c_curve", "The book since 2015-06: trades at the signal's close against one close late", "Growth of $1, log scale, simulated. One close late is a bound, not the expected live result."),
    "{{lq_l2}}": f"{LQV['on_days_L2_on']:,}", "{{lq_on}}": f"{LQV['on_days']:,}", "{{lq_sw}}": str(REG["F_LIQUIDITY"]["switches_on"]),
    "{{lq_blk}}": f"{LB['from'][:7]} to {LB['to'][:7]}", "{{lq_blk_share}}": pu(LB["off_days"] / LB["all_off_days"]), "{{lq_blk_log}}": pu(LB["off_log"] / LB["all_off_log"]),
    "{{lq_shape_l1}}": pu(LQS["on_days_L1_only"] / LQS["on_days"]),
    "{{x1_top}}": " and ".join(XR["top_two_years"]), "{{x1_top_share}}": pu(XR["top_two_on_log"] / XR["on_log_total"]),
    "{{x1_wo}}": "not scored" if xw is None else f"{lg(xw['diff_per_yr'])} a year (p {pv(xw['p_two_sided'])})",
    "{{p2_always}}": lg(PA["d_growth"], 3), "{{p2_first}}": PA["first_tilted_day"][:7],
    "{{lean_same}}": f"a plain book {pu(LT['verdict']['same_fall_mix']['exposure'])} invested has the same deepest fall and grows {lg(LT['verdict']['same_fall_mix']['growth'])}",
    "{{gold_same}}": (f"that book grew {lg(LI['lean_in']['F_GOLD']['verdict']['growth'])} with a deepest fall of {pu(LI['lean_in']['F_GOLD']['verdict']['maxdd'], 1)}; a plain book "
                      f"{pu(LI['lean_in']['F_GOLD']['verdict']['same_fall_mix']['exposure'], 1)} invested has the same fall and grows {lg(LI['lean_in']['F_GOLD']['verdict']['same_fall_mix']['growth'])}"),
    "{{lean_v}}": lean(LT["verdict"]), "{{lean_s}}": lean(LT["shape"]), "{{lean_exp}}": pu(LT["verdict"]["avg_exposure"]),
    "{{kmlm_share}}": pu(eng_sum["KMLM"] / sum(eng_sum.values())), "{{top2}}": " and ".join(sorted(top2)), "{{top2_share}}": pu(sum(BY[y]["book_log"] for y in top2) / tot_b),
    "{{n_fail}}": str(n_fail), "{{n_scored}}": str(n_scored),
    "{{t1_on}}": lg(T1v["on_per_yr"]), "{{t1_off}}": lg(T1v["off_per_yr"]), "{{t1_on_s}}": lg(T1s["on_per_yr"]), "{{t1_off_s}}": lg(T1s["off_per_yr"]), "{{t1_ps}}": pv(T1s["p_two_sided"]),
    "{{t1_falls}}": pu(T1v["share_of_deepest_fall_days_on"]), "{{t1_share}}": pu(T1v["on_share"]), "{{t1_p1}}": lg(P1["BOOK.verdict"]["T1"]["d_growth"], 3),
    "{{t1_mirror}}": lg(P1["BOOK.verdict"]["T1"]["mirror_d_growth"], 3), "{{t1_real}}": f"{lg(BR['T1']['on_per_yr'])} vs {lg(BR['T1']['off_per_yr'])}",
    "{{t1_eng}}": ", ".join(f"{EN[e]} {lg(MAP[e + '.verdict']['states']['T1']['diff_per_yr'])} (p {pv(MAP[e + '.verdict']['states']['T1']['p_two_sided'])})" for e in ("HG", "KMLM", "SLEEVE")),
    "{{x1_v}}": lg(X1["verdict"]["diff_per_yr"]), "{{x1_all}}": "; ".join(f"{lab}: {lg(X1[k]['diff_per_yr'])} (p {pv(X1[k]['p_two_sided'])})" for k, lab in SP),
    "{{rd_dg}}": lg(R2["d_growth"], 3), "{{own_on}}": lg(X1["verdict"]["own_engine_on_per_yr"]),
    "{{g_on}}": lg(G["on_per_yr"]), "{{g_off}}": lg(G["off_per_yr"]), "{{g_p}}": pv(G["p_two_sided"]), "{{g_reg}}": str(REG["F_GOLD"]["merged_regimes"]),
    "{{g_eng}}": ", ".join(f"{EN[e]} {lg(-v['diff_per_yr'])} (p {pv(v['p'])})" for e, v in GO["per_engine_diff"].items()),
    "{{g_wo}}": f"{lg(-GO['without_2020_2022']['diff_per_yr'])}, p {pv(GO['without_2020_2022']['p'])}", "{{g_p1}}": lg(GO["p1_test"]["d_growth"], 3), "{{g_p1p}}": pv(GO["p1_test"]["p_growth"]),
    "{{g_p1dd}}": pp(GO["p1_test"]["d_maxdd"]), "{{g_real}}": f"{lg(BR['F_GOLD']['on_per_yr'])} vs {lg(BR['F_GOLD']['off_per_yr'])} (p {pv(BR['F_GOLD']['p_two_sided'])})",
    "{{g_shape}}": f"{lg(BS['F_GOLD']['on_per_yr'])} vs {lg(BS['F_GOLD']['off_per_yr'])}, p {pv(BS['F_GOLD']['p_two_sided'])}",
    "{{l_on}}": lg(L["on_per_yr"]), "{{l_off}}": lg(L["off_per_yr"]), "{{l_p}}": pv(L["p_two_sided"]), "{{l_holm}}": pv(L["p_holm"]), "{{l_ddp}}": f"{PL['d_maxdd'] * 100:.1f}",
    "{{l_pol}}": lg(PL["growth"]), "{{l_full}}": lg(MAP["BOOK.verdict"]["growth_per_yr"]), "{{l_dg}}": lg(PL["d_growth"], 3),
    "{{l_wo}}": f"{lg(LQ['without_2020_2021']['p1_d_growth'], 3)} a year, and the on/off difference is {lg(LQ['without_2020_2021']['diff_per_yr'])} (p {pv(LQ['without_2020_2021']['p'])})",
    "{{x3_e4}}": f"{lg(X3['mostly_real_2015_2020']['diff_per_yr'])}, p {pv(X3['mostly_real_2015_2020']['p_two_sided'])}", "{{x3_s}}": f"{lg(X3['shape']['diff_per_yr'])}, p {pv(X3['shape']['p_two_sided'])}",
    "{{x3_r}}": f"{lg(X3['real_2021_06_on']['diff_per_yr'])}, p {pv(X3['real_2021_06_on']['p_two_sided'])}",
    "{{vol_hg}}": f"{lg(HV['on_per_yr'])} against {lg(HV['off_per_yr'])}", "{{vol_p}}": pv(HV["p_holm"]), "{{vol_share}}": pu(HV["on_share"], 1), "{{vol_ep}}": str(HV["episodes"]),
    "{{re_v}}": lg(RE["verdict"]["ungated_minus_tbills_per_yr"]), "{{re_s}}": lg(RE["shape"]["ungated_minus_tbills_per_yr"]),
    "{{book_g}}": lg(MAP["BOOK.verdict"]["growth_per_yr"]), "{{book_dd}}": pu(MAP["BOOK.verdict"]["maxdd"]),
    "{{t_design}}": t_design, "{{t_map}}": t_map, "{{t_singles}}": t_singles, "{{t_p1}}": t_p1, "{{t_cross}}": t_cross, "{{t_cross2}}": t_cross2, "{{t_redeploy}}": t_redeploy, "{{t_p2}}": t_p2, "{{t_re}}": t_re,
    "{{t_years}}": t_years,
    "{{t_open}}": table(["Priority", "Question", "What it would move", "Status"], [
        ["P1", "Measure decision price against fill on the live record (Composer and the mirror), per engine, with stressed days apart", "How much of the one-close-late gap applies live; it bounds every simulated number in addenda 58 to 61", "open, first asked 2026-11-21"],
        ["P1", "Owner: is the book's deepest fall or its growth the binding constraint?", "Whether any reserve held for stress states is worth its cost; the third leg's weight (addendum 60)", "asked 2026-11-21, open"],
        ["P2", "Track the gold-strong state forward from 2026-11-21 with the definition frozen", "Whether gold is a real risk-on state for this book or an accident of 2015-2021", "open, first asked 2026-11-21"],
        ["P2", "Daily gold before 2000-09 (London fix) in place of monthly averages", "A sharper test of gold on 1994-2000", "open, first asked 2026-11-21"],
        ["P2", "As-published vintages of CPI, M2 and the financial conditions index (ALFRED)", "Whether the liquidity result survives without revised data", "open, first asked 2026-11-21"],
        ["P2", "Owner: keep the inverse-fund half of the sleeve? (carried from addendum 60)", "Half the sleeve; both brokers and the logic book if changed", "asked 2026-11-21, open"],
        ["P3", "Rebuild UVXY and SVXY for 2006-2011 (carried from addendum 60)", "Longer part-real history for the sleeve and so the book", "open, first asked 2026-11-21"]]),
    "{{ch_map}}": chart("c_map", "Book growth while each state is on, less while it is off, 2015-06 on", "Log-points a year. A risk-off state should sit well below zero. Liquidity and the dollar do; gold and credit stress sit well above. Sections 3 and 7 say how much of each survives."),
    "{{ch_t1}}": chart("c_t1", "Where the book's growth came from: S&P 500 below or above its 200-day average",
                       f"Running total of the book's daily log growth from 1994, split by the state the day before. The S&P was below its average on {pu(C['T1']['share_on'])} of days. Rebuilt before 2015."),
    "{{ch_gold}}": chart("c_gold", "The same split by gold: strong or not", f"Gold strong on {pu(C['F_GOLD']['share_on'])} of days. The gap opens after 2015; before it the two lines keep pace with their share of days."),
    "{{ch_liq}}": chart("c_liq", "The same split by liquidity: tight or not", f"Tight on {pu(C['F_LIQUIDITY']['share_on'])} of days. The off-days line makes most of its ground in 2020-2021."),
    "{{charts}}": json.dumps(CH, separators=(",", ":")),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Macro Regime Study</title>"),
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
print("wrote", OUT, len(BODY) // 1024, "KB;", len(CH), "charts;", "fail", n_fail, "of", n_scored, {s: RULE[s] for s in PRIM})
