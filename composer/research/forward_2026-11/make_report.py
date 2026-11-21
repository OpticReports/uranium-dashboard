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
SN = {"A": "As simulated, 2021-06 on", "B": "As simulated, 2015-06 on", "C": "As simulated, 1994 on", "D": "Half the edge", "E": "A quarter of the edge", "F": "One close late", "G": "S&P at 2% a year",
      "Z": "None of the edge", "H": "Half the edge, 1994-on source", "I": "A quarter of the edge, 1994-on source"}
KIND = {"A": "ceiling", "B": "ceiling", "C": "ceiling", "D": "haircut", "E": "haircut", "F": "bound", "G": "ceiling, shifted", "Z": "no edge", "H": "haircut", "I": "haircut"}
WS = ["0.000", "0.100", "0.200", "0.318", "0.400", "0.500"]
WL = ["0%", "10%", "20%", "31.8%", "40%", "50%"]
HN = {"1y": "1 year", "5y": "5 years", "10y": "10 years"}
EN = {"HG": "Holy Grail", "KMLM": "KMLM", "SLEEVE": "Sleeve"}
ORDER = ["A", "B", "C", "G", "D", "E", "H", "I", "Z", "F"]


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
CH["c_med"] = {"type": "line", "yfmt": "mult", "log": True, "logticks": [0.25, 0.5, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000], "xnum": True, "xlabels": XL, "xunit": "",
               "series": [{"name": SN[s], "slot": i + 1, "pts": yr(FAN[f"{s}.{T}"])} for i, s in enumerate(["B", "D", "E", "Z"])]}
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


CS = ["B", "D", "E", "Z"]
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
t_cap = table(["Scenario", "Cap rule"] + WL, [r for s_ in ("B", "D") for r in (
    [SN[s_], "each engine's own target + 10 points (used here): median return a year"] + [pc(MC[s_][wt]["10y"]["per_yr"]["50"]) for wt in WS],
    ["", "&nbsp;&nbsp;chance of a fall deeper than 30%"] + [pu(MC[s_][wt]["10y"]["p_fall_deeper"]["30"]) for wt in WS],
    ["", "one cap, largest target + 10 points (as registered): median return a year"] + [pc(MC[s_][wt + ".largest_cap"]["10y"]["per_yr"]["50"]) for wt in WS],
    ["", "&nbsp;&nbsp;chance of a fall deeper than 30%"] + [pu(MC[s_][wt + ".largest_cap"]["10y"]["p_fall_deeper"]["30"]) for wt in WS])])
t_methods = table(["Method", "What it is", "Used here?"], [
    ["Block-bootstrap Monte Carlo", "resample stretches of the strategy's own daily returns into thousands of future paths", "yes: every scenario"],
    ["Backtest haircut from published decay", "shrink the backtest's edge by what strategies have lost between backtest and live", "yes: scenarios D and E"],
    ["Execution stress", "re-run with worse fills and see what survives", "yes: scenario F (one close late)"],
    ["Building blocks / capital-market assumptions", "split return into market beta and the rest; put a forward view on the market part", "yes: scenario G and the beta table"],
    ["Deflated Sharpe ratio / multiple-testing haircut", "ask whether the best of many tries could look this good by luck", "yes: table above; it cannot produce a forward number"],
    ["Regime-conditioned bootstrap", "resample by market regime with chosen regime odds", "already on record (addendum 13); the long-history scenario C covers the hostile regimes here"],
    ["Live-record updating (Bayesian shrinkage)", "blend the backtest with live results as they accrue", "table only: 94 to 238 live sessions cannot move an estimate yet; worth re-running each quarter"],
    ["Parametric models (GARCH, regime-switching, fat-tailed fits)", "fit a return model and simulate from it", "no: GARCH was tried on the harvester and failed its test (addendum 31); a fitted model adds assumptions the bootstrap does not need"],
    ["Capacity and cost curves", "model how returns shrink as size grows", "no: on record for today's size (addenda 14b, 15); matters at about $1M and up"],
    ["Walk-forward / cross-validated backtests", "re-fit on one period, test on the next", "not applicable: the rules are fixed trees, not re-fitted; the rebuilt pre-2015 history is the nearest thing to an unseen period"]])
t_hist = table(["Source", "Sessions", "Sleeve weight", "Return a year", "Deepest fall", "Sharpe over T-bills", "Volatility"],
               [[SN[s] if wt == "0.000" else "", HIST[s][wt]["n"] if wt == "0.000" else "", WL[WS.index(wt)], pc(HIST[s][wt]["cagr"]), pu(HIST[s][wt]["maxdd"], 1), f"{HIST[s][wt]['sharpe_over_tbills']:.2f}", pu(HIST[s][wt]["vol"])]
                for s in ORDER for wt in ("0.000", "0.318", "0.500")])
t_def = table(["Source", "Sleeve weight", "Simulated Sharpe", "Best of 10 unskilled tries would show", "of 100", "of 1,000", "Confidence the true Sharpe is above the best-of-1,000 figure"],
              [[SN[s], WL[WS.index(wt)], f"{v['sharpe']:.2f}", f"{v['10']['expected_best_of_unskilled']:.2f}", f"{v['100']['expected_best_of_unskilled']:.2f}", f"{v['1000']['expected_best_of_unskilled']:.2f}",
                "&gt;99.9%" if v["1000"]["prob_observed_beats_it"] > 0.999 else pu(v["1000"]["prob_observed_beats_it"], 1)] for s in ("A", "B", "C") for wt, v in DEF[s].items()])
EK = ("HG", "KMLM", "SLEEVE")
t_beta = table(["Engine", "Average beta to the S&P 500, 2015-06 on", "Mean return over T-bills a year", "of which beta x the S&P's", "Lowered by, with the S&P at 2%", "Beta, 1994 on", "Share from beta, 1994 on"],
               [[EN[e], f"{SIDE['beta_B'][i]:+.2f}", pc(SIDE["engine_mean_over_tbills_per_yr_B"][i]),
                 pu(SIDE["beta_B"][i] * SIDE["spx_mean_over_tbills_per_yr_B"] / SIDE["engine_mean_over_tbills_per_yr_B"][i]), f"{SIDE['g_shift_per_yr'][i] * 100:.1f} points a year", f"{SIDE['beta_C'][i]:+.2f}",
                 pu(SIDE["beta_C"][i] * SIDE["spx_mean_over_tbills_per_yr_C"] / SIDE["engine_mean_over_tbills_per_yr_C"][i])]
                for i, e in enumerate(EK)])
t_live = table(["", "From", "to", "Sessions", "Live return", "Simulated, same closes", "Deepest live fall"],
               [r for e in EK for r in ([[EN[e] + ", since it started", LIVE[e]["from"], LIVE[e]["to"], LIVE[e]["sessions"], pc(LIVE[e]["live_return"], 1), pc(LIVE[e]["simulated_return_same_dates"], 1), pu(LIVE[e]["live_deepest_fall"], 1)]]
                                        + ([[EN[e] + ", since it held $10,000 or more", LIVE[e]["funded_from"], LIVE[e]["to"], LIVE[e]["funded_sessions"], pc(LIVE[e]["live_return_funded"], 1), pc(LIVE[e]["simulated_return_funded"], 1), ""]]
                                           if LIVE[e]["funded_from"] != LIVE[e]["from"] else []))]
               + [["The three together, at the weights actually held", LIVE["three_as_held"]["from"], LIVE["three_as_held"]["to"], LIVE["three_as_held"]["sessions"], pc(LIVE["three_as_held"]["live_return"], 1),
                   pc(LIVE["three_as_held"]["simulated_return_same_weights"], 1), ""]])
BS = F["block_sensitivity"]
t_block = table(["Half the edge / a quarter, today's book", "About a week (5)", "About a month (21, used)", "About a quarter (63)"], [
    ["Half: one-year median return"] + [pc(BS["D"][b]["1y"]["per_yr"]["50"]) for b in ("5", "21", "63")],
    ["Half: chance of ending a year below the start"] + [pu(BS["D"][b]["1y"]["p_below_start"], 1) for b in ("5", "21", "63")],
    ["Half: ten-year median return a year"] + [pc(BS["D"][b]["10y"]["per_yr"]["50"]) for b in ("5", "21", "63")],
    ["Half: median deepest fall in ten years"] + [pu(BS["D"][b]["10y"]["maxdd_median"], 1) for b in ("5", "21", "63")],
    ["Quarter: chance of ending below the start after 5 / 10 years"] + [f"{pu(BS['E'][b]['5y']['p_below_start'], 1)} / {pu(BS['E'][b]['10y']['p_below_start'], 1)}" for b in ("5", "21", "63")],
    ["Quarter: chance of a fall deeper than 50% in ten years"] + [pu(BS["E"][b]["10y"]["p_fall_deeper"]["50"]) for b in ("5", "21", "63")]])
share = lambda sc: 1 - MC[sc]["0.500"]["10y"]["per_yr"]["50"] / MC[sc]["0.000"]["10y"]["per_yr"]["50"]   # noqa: E731
cut = lambda sc: MC[sc]["0.000"]["10y"]["maxdd_p95"] - MC[sc]["0.500"]["10y"]["maxdd_p95"]                 # noqa: E731
t_cost = table(["Scenario", "Median ten-year return a year, 0% to 50% sleeve", "Points of return given up", "Share of the return given up", "Cut in the 1-in-20 deepest fall",
                "1-in-20 bad five years, 0% / 50%", "Chance of ending 5 years below the start, 0% / 50%"],
               [[SN[sc], f"{pc(MC[sc]['0.000']['10y']['per_yr']['50'])} to {pc(MC[sc]['0.500']['10y']['per_yr']['50'])}",
                 f"{(MC[sc]['0.000']['10y']['per_yr']['50'] - MC[sc]['0.500']['10y']['per_yr']['50']) * 100:.0f}",
                 pu(share(sc)) if MC[sc]["0.000"]["10y"]["per_yr"]["50"] > 0.02 else "n/a", f"{cut(sc) * 100:.0f} points",
                 f"{pc(MC[sc]['0.000']['5y']['per_yr']['5'])} / {pc(MC[sc]['0.500']['5y']['per_yr']['5'])}", f"{pu(MC[sc]['0.000']['5y']['p_below_start'], 1)} / {pu(MC[sc]['0.500']['5y']['p_below_start'], 1)}"]
                for sc in ("B", "C", "F", "D", "E", "H", "I", "Z")])
t_scen = table(["Scenario", "Kind", "Draws from", "What it assumes", "Evidence behind it"], [
    [SN["A"], KIND["A"], "2021-06 to 2026-11", "the all-real simulated years repeat", "in-sample backtest"],
    [SN["B"], KIND["B"], "2015-06 to 2026-11", "the simulated years since every traded fund is real repeat (has 2018, 2020, 2022)", "in-sample backtest; KMLM fund rebuilt before 2021; no data 2020-12-02 to 2021-06-01"],
    [SN["C"], KIND["C"], "1994-06 to 2026-11", "the whole rebuilt history repeats (adds 2000-02, 2007-09)", "funds and signals rebuilt or modelled before 2015 (addenda 58 to 60 say which, leg by leg)"],
    [SN["G"], KIND["G"], "2015-06 on, shifted", "the S&P 500 compounds at 2% a year; each engine loses its average beta times the shortfall", "a statement about the backtest's market exposure, not a low-return-decade estimate (section 5)"],
    [SN["D"], KIND["D"], "2015-06 on, shifted", "each engine keeps half its simulated return over T-bills; same swings", "97 published stock-return predictors earned 26% less out of sample and 58% less after publication (McLean and Pontiff 2016); \"half\" is a round number between them, and the 50% rule of thumb for backtest Sharpe ratios, which Harvey and Liu (2015) describe and argue against"],
    [SN["E"], KIND["E"], "2015-06 on, shifted", "each engine keeps 27% of it", "median live Sharpe 73% below the backtest across 215 bank alternative-beta strategies; 30% had a negative live Sharpe (Suhonen, Lennkh and Perez 2017)"],
    [SN["H"], KIND["H"], "1994-06 on, shifted", "half the edge, taken off the longer, rougher history", "added after review: the 2015-on source is the friendliest long one"],
    [SN["I"], KIND["I"], "1994-06 on, shifted", "a quarter of the edge, same source", "as above"],
    [SN["Z"], KIND["Z"], "2015-06 on, shifted", "each engine earns T-bills on average and keeps all its swings", "added after review: 30% of the strategies in the Suhonen sample did worse than this live"],
    [SN["F"], KIND["F"], "2015-06 on, late paths", "every trade fills one close late, forever", "addendum 61; live fills have not been there (addendum 14b)"]])
v = lambda s, h="10y", wt=T: MC[s][wt][h]                                                  # noqa: E731
plan = ("G", "D", "E")
lo_s = min(plan, key=lambda s: v(s)["per_yr"]["50"])
hi_s = max(plan, key=lambda s: v(s)["per_yr"]["50"])
subs = {
    "{{t_scen}}": t_scen, "{{t_today}}": t_today, "{{t_w10}}": by_weight("10y"), "{{t_w5}}": by_weight("5y"), "{{t_w1}}": by_weight("1y"), "{{t_drift}}": t_drift, "{{t_hist}}": t_hist, "{{t_def}}": t_def,
    "{{t_beta}}": t_beta, "{{t_live}}": t_live, "{{t_cap}}": t_cap, "{{t_methods}}": t_methods, "{{t_block}}": t_block, "{{t_cost}}": t_cost,
    "{{z_10}}": pc(v("Z")["per_yr"]["50"], 1), "{{z_dd}}": f"{pu(v('Z')['maxdd_median'])} (1-in-20: {pu(v('Z')['maxdd_p95'])})", "{{z_ddm}}": pu(v("Z")["maxdd_median"]),
    "{{z_loss}}": f"{pu(v('Z', '1y')['p_below_start'])} / {pu(v('Z', '5y')['p_below_start'])} / {pu(v('Z', '10y')['p_below_start'])}",
    "{{w_z}}": f"{pc(v('Z', wt='0.000')['per_yr']['50'], 1)} / {pc(v('Z')['per_yr']['50'], 1)} / {pc(v('Z', wt='0.500')['per_yr']['50'], 1)}",
    "{{w_z_dd}}": f"{pu(v('Z', wt='0.000')['maxdd_median'])} / {pu(v('Z')['maxdd_median'])} / {pu(v('Z', wt='0.500')['maxdd_median'])}",
    "{{h_10}}": pc(v("H")["per_yr"]["50"]), "{{i_10}}": pc(v("I")["per_yr"]["50"]), "{{h_dd}}": pu(v("H")["maxdd_median"]), "{{i_dd}}": pu(v("I")["maxdd_median"]),
    "{{h_loss1}}": pu(v("H", "1y")["p_below_start"]), "{{i_loss10}}": pu(v("I", "10y")["p_below_start"]),
    "{{c_10}}": pc(v("C")["per_yr"]["50"]),
    "{{sh_b}}": pu(share("B")), "{{sh_c}}": pu(share("C")), "{{sh_f}}": pu(share("F")), "{{sh_d}}": pu(share("D")), "{{sh_e}}": pu(share("E")), "{{sh_h}}": pu(share("H")), "{{sh_i}}": pu(share("I")),
    "{{pts_bde}}": ", ".join(f"{(MC[sc]['0.000']['10y']['per_yr']['50'] - MC[sc]['0.500']['10y']['per_yr']['50']) * 100:.0f}" for sc in ("B", "D", "E")),
    "{{cut_rng}}": f"{min(cut(sc) for sc in ('B', 'D', 'E')) * 100:.0f} to {max(cut(sc) for sc in ('B', 'D', 'E')) * 100:.0f}",
    "{{kept_late}}": " / ".join(pu(x) for x in SIDE["edge_kept_one_close_late"]), "{{kept_pre}}": " / ".join(pu(x) for x in SIDE["edge_kept_before_2015"]),
    "{{dec_book}}": pc(SIDE["book_cagr_2000_2009"]), "{{dec_spx}}": pc(SIDE["spx_cagr_2000_2009"], 1), "{{pre_book}}": pc(SIDE["book_cagr_before_2015"]), "{{b_book}}": pc(SIDE["book_cagr_B"]),
    "{{top50}}": " / ".join(pu(SIDE["share_of_edge_from_best_50_sessions"][e]) for e in EK), "{{wo50}}": pc(SIDE["book_cagr_B_without_its_best_50_sessions"]), "{{wo2020}}": pc(SIDE["book_cagr_B_without_2020"]),
    "{{y2020}}": pc(SIDE["book_return_2020"]),
    "{{hg_f}}": f"{pc(LIVE['HG']['live_return_funded'], 1)} against {pc(LIVE['HG']['simulated_return_funded'], 1)}", "{{hg_f_n}}": str(LIVE["HG"]["funded_sessions"]),
    "{{held}}": f"{pc(LIVE['three_as_held']['live_return'], 1)} live against {pc(LIVE['three_as_held']['simulated_return_same_weights'], 1)} simulated at the same weights",
    "{{d_1med}}": " to ".join(sorted((pc(BS["D"][b]["1y"]["per_yr"]["50"]) for b in ("5", "21", "63")), key=lambda z: float(z[:-1]))[::2]),
    "{{d_1loss}}": " to ".join(sorted((pu(BS["D"][b]["1y"]["p_below_start"]) for b in ("5", "21", "63")), key=lambda z: float(z[:-1]))[::2]),
    "{{e_10loss}}": " to ".join(sorted((pu(BS["E"][b]["10y"]["p_below_start"], 1) for b in ("5", "21", "63")), key=lambda z: float(z[:-1]))[::2]),
    "{{sr_tb}}": f"{HIST['B']['0.318']['sharpe_over_tbills']:.2f}", "{{sr_late}}": f"{HIST['F']['0.318']['sharpe_over_tbills']:.2f}",
    "{{sr_d}}": f"{HIST['D']['0.318']['sharpe_over_tbills']:.2f}", "{{sr_e}}": f"{HIST['E']['0.318']['sharpe_over_tbills']:.2f}",
    "{{d_10}}": pc(v("D")["per_yr"]["50"]), "{{e_10}}": pc(v("E")["per_yr"]["50"]), "{{g_10}}": pc(v("G")["per_yr"]["50"]),
    "{{d_5}}": rng3(v("D", "5y")), "{{e_5}}": rng3(v("E", "5y")), "{{d_1}}": rng3(v("D", "1y")), "{{e_1}}": rng3(v("E", "1y")),
    "{{d_dd}}": f"{pu(v('D')['maxdd_median'])} (1-in-20: {pu(v('D')['maxdd_p95'])})", "{{e_dd}}": f"{pu(v('E')['maxdd_median'])} (1-in-20: {pu(v('E')['maxdd_p95'])})",
    "{{d_p30}}": pu(v("D")["p_fall_deeper"]["30"]), "{{e_p30}}": pu(v("E")["p_fall_deeper"]["30"]), "{{e_p50}}": pu(v("E")["p_fall_deeper"]["50"]), "{{d_p50}}": pu(v("D")["p_fall_deeper"]["50"]),
    "{{d_loss1}}": pu(v("D", "1y")["p_below_start"]), "{{e_loss1}}": pu(v("E", "1y")["p_below_start"]), "{{e_loss5}}": pu(v("E", "5y")["p_below_start"]), "{{e_loss10}}": pu(v("E", "10y")["p_below_start"], 1),
    "{{b_dd}}": f"{pu(v('B')['maxdd_median'])} (1-in-20: {pu(v('B')['maxdd_p95'])})",
    "{{w_b}}": f"{pc(v('B', wt='0.000')['per_yr']['50'])} / {pc(v('B')['per_yr']['50'])} / {pc(v('B', wt='0.500')['per_yr']['50'])}",
    "{{w_d}}": f"{pc(v('D', wt='0.000')['per_yr']['50'])} / {pc(v('D')['per_yr']['50'])} / {pc(v('D', wt='0.500')['per_yr']['50'])}",
    "{{w_e}}": f"{pc(v('E', wt='0.000')['per_yr']['50'])} / {pc(v('E')['per_yr']['50'])} / {pc(v('E', wt='0.500')['per_yr']['50'])}",
    "{{w_d_dd}}": f"{pu(v('D', wt='0.000')['maxdd_p95'])} / {pu(v('D')['maxdd_p95'])} / {pu(v('D', wt='0.500')['maxdd_p95'])}",
    "{{w_e_dd}}": f"{pu(v('E', wt='0.000')['maxdd_p95'])} / {pu(v('E')['maxdd_p95'])} / {pu(v('E', wt='0.500')['maxdd_p95'])}",
    "{{w_b_dd}}": f"{pu(v('B', wt='0.000')['maxdd_p95'])} / {pu(v('B')['maxdd_p95'])} / {pu(v('B', wt='0.500')['maxdd_p95'])}",
    "{{def_best}}": f"{DEF['B']['0.318']['1000']['expected_best_of_unskilled']:.2f}", "{{def_sr}}": f"{DEF['B']['0.318']['sharpe']:.2f}",
    "{{beta_txt}}": ", ".join(f"{EN[e]} {SIDE['beta_B'][i]:+.2f}" for i, e in enumerate(EK)),
    "{{beta_share}}": (f"about {pu(SIDE['beta_B'][0] * SIDE['spx_mean_over_tbills_per_yr_B'] / SIDE['engine_mean_over_tbills_per_yr_B'][0])} of Holy Grail's and "
                       f"{pu(SIDE['beta_B'][1] * SIDE['spx_mean_over_tbills_per_yr_B'] / SIDE['engine_mean_over_tbills_per_yr_B'][1])} of KMLM's return over T-bills comes from market beta; the sleeve's beta is negative"),

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
    "{{spx_b}}": pc(SIDE["spx_cagr_B"], 1), "{{paths}}": f"{F['meta']['paths']:,}", "{{block}}": str(F["meta"]["block"]),
    "{{ch_med}}": chart("c_med", "Today's book (31.8% sleeve): the median path in each scenario", "Growth of $1 over ten years, log scale. Half of the drawn paths end above each line and half below. The other scenarios are in the table."),
    "{{ch_fan}}": chart("c_fan", "Today's book under \"half the edge\": the spread of outcomes", "Growth of $1, log scale. Nine in ten drawn paths end between the outer lines."),
    "{{ch_fanE}}": chart("c_fanE", "Today's book under \"a quarter of the edge\": the spread of outcomes", "Growth of $1, log scale."),
    "{{ch_w_ret}}": chart("c_w_ret", "Median return a year over ten years, by sleeve weight", "More sleeve, less return wherever the engines keep an edge; with no edge the order flips."),
    "{{ch_w_bad}}": chart("c_w_bad", "A 1-in-20 bad five years, by sleeve weight", "Return a year at the 5th percentile after five years."),
    "{{ch_w_dd}}": chart("c_w_dd", "A 1-in-20 deepest fall within ten years, by sleeve weight", "More sleeve, smaller fall in every scenario."),
}
BODY = open(os.path.join(HERE, "..", "kmlm_2026-11", "report_body.html")).read()
for a, b in (("<title>KMLM Switcher Windows</title>", "<title>Forward Ranges</title>"), ("--s3:#199e70;", "--s3:#199e70;--s4:#8a63d2;"), ("--s3:#1baf7a;", "--s3:#1baf7a;--s4:#a78bea;"),
             ("const yt=c.log?[.25,.5,1,2,4,8,16,32].filter(", "const yt=c.log?(c.logticks||[.25,.5,1,2,4,8,16,32]).filter("),
             ('if(f==="mult")return (v>=10?v.toFixed(0):v.toFixed(2))+"×"',
              'if(f==="mult")return (v>=1e9?(v/1e9).toFixed(0)+"B":v>=1e6?(v/1e6).toFixed(0)+"M":v>=1e3?(v/1e3).toFixed(0)+"k":v>=10?v.toFixed(0):v.toFixed(2))+"×"')):
    assert a in BODY, a
    BODY = BODY.replace(a, b)
BODY = BODY.replace("{{main}}", open(os.path.join(HERE, "report_main.html")).read())
ver = os.path.join(HERE, "VERIFICATION.html")
subs["{{verification}}"] = open(ver).read() if os.path.exists(ver) else "<p class='note'>Independent verification in progress.</p>"
subs["{{charts}}"] = json.dumps(CH, separators=(",", ":"))
subs["{{t_open}}"] = table(["Priority", "Question", "What it would move", "Status"], [
    ["P1", "Owner: is the book's deepest fall or its growth the binding constraint?", "The sleeve weight: this study prices the trade in each scenario but cannot choose", "asked 2026-11-21, open"],
    ["P1", "Owner: which scenario do you want to plan on (half the edge, a quarter, something else)?", "Every forward number quoted to you from here; the monitor's expectations", "asked 2026-11-21"],
    ["P2", "Re-run the live-against-simulated table each quarter and start a live-decay estimate once a year of unchanged rules exists", "Replaces the borrowed 50% and 73% haircuts with this book's own", "open, first asked 2026-11-21"],
    ["P2", "If the sleeve target changes: set each engine's cap from its own target", "POLICY operation 5; otherwise a large-sleeve book drifts back to a small-sleeve one", "open, first asked 2026-11-21"],
    ["P2", "Split the measured-fill and 15:54-versus-close checks by weak-market days (carried from addendum 61)", "How far towards the one-close-late floor live trading can slip", "open, first asked 2026-11-21"],
    ["P3", "A worst-day stress outside the sample (a leveraged fund losing most of its value in a session)", "The left tail no draw contains", "open, first asked 2026-11-21"]])
CITE = json.load(open(os.path.join(HERE, "citations.json"))) if os.path.exists(os.path.join(HERE, "citations.json")) else {"cite_d": "McLean and Pontiff 2016; Harvey and Liu 2015", "cite_e": "Suhonen, Lennkh and Perez 2017: median 73% fall in Sharpe from backtest to live, 215 bank strategies"}
for _ in range(2):
    for k, val in list(subs.items()) + [("{{" + k + "}}", x) for k, x in CITE.items()]:
        BODY = BODY.replace(k, str(val))
left = re.findall(r"\{\{[a-z_0-9]+\}\}", BODY)
assert not left, left
open(OUT, "w").write(BODY)
print("wrote", OUT, len(BODY) // 1024, "KB;", len(CH), "charts; planning range", lo_s, hi_s)
