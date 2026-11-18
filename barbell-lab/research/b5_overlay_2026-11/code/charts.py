"""Build report.html (self-contained, interactive) from results.json + _cache/series.pkl.
Run: python charts.py ; then python shots.py to render charts/*.png from the same page."""
import json, os, pickle
import numpy as np, pandas as pd
import common as C

r = json.load(open(os.path.join(C.STUDY, "results.json")))
S = pickle.load(open(os.path.join(C.CACHE, "series.pkl"), "rb"))
T1 = r["T1"]; T2 = r["T2"]; s = S["T1"]; cal = s["cal"]; A = T1["arms"]
i0 = int(cal.searchsorted(C.EXT0)); L = T1["live"]
P = lambda x, d=1: f"{x * 100:.{d}f}%"
SG = lambda x, d=2: ("+" if x >= 0 else "−") + f"{abs(x):.{d}f}"

# ---------- weekly series
idx = pd.Series(np.arange(len(cal)), index=cal).loc[cal[i0]:].resample("W-FRI").last().dropna().astype(int).values
t = [int(pd.Timestamp(cal[i]).value // 10 ** 6) for i in idx]
ser = {"live": s["live"], "a2": s["arms"]["A2"], "b8": s["arms"]["B8"], "wf": s["wf_sharpe"]}
eq, dd = {}, {}
for k, x in ser.items():
    nav = np.cumprod(1 + x[i0:]); d = nav / np.maximum.accumulate(nav) - 1
    eq[k] = [round(float(nav[i - i0]), 4) for i in idx]
    lo = np.minimum.reduceat(d, np.concatenate([[0], idx[:-1] - i0 + 1]))          # weekly minimum keeps the troughs
    dd[k] = [round(float(v) * 100, 2) for v in lo]
expo = pd.Series(s["exposure"]["A2"][i0:], index=cal[i0:]).resample("W-FRI").mean().dropna().values
expo = [round(float(v) * 100, 1) for v in expo][:len(t)]

# ---------- episodes
eps = ["GFC", "COVID crash", "COVID rebound", "2022"]
notes = {"GFC": "2007-10-09 to 2009-03-09", "COVID crash": "2020-02-19 to 2020-03-23", "COVID rebound": "2020-03-24 to 2020-12-31", "2022": "2022-01-03 to 2022-10-14"}
ep = dict(cats=["2008 crisis", "2020 fall", "2020 rebound", "2022"], notes=[notes[e] for e in eps], series=[
    dict(name="Live book", c="--s1", v=[round(T1["live_episodes"][e]["ret"] * 100, 1) for e in eps]),
    dict(name="10-month rule per leg", c="--s2", v=[round(A["A2"]["episodes"][e]["ret"] * 100, 1) for e in eps]),
    dict(name="Book stop 6%", c="--s3", v=[round(A["B8"]["episodes"][e]["ret"] * 100, 1) for e in eps]),
    dict(name="Equity off when SPY < 200-day", c="--s4", v=[round(A["M1"]["episodes"][e]["ret"] * 100, 1) for e in eps])])

# ---------- forest + table
FC = {"BOOK": "--s1", "ASSET": "--s2", "MACRO": "--s3"}
order = sorted(A, key=lambda k: -A[k]["win"]["EXT"]["d"]["d_sharpe"])
forest, rows = [], []
for k in order:
    a = A[k]; E = a["win"]["EXT"]; b = E["b21"]; b2 = T2["arms"][k]["win"]["EXT"]
    forest.append(dict(label=f"{k} {a['label']}", v=round(E["d"]["d_sharpe"], 3), lo=round(b["ci"][0], 3), hi=round(b["ci"][1], 3), c=FC[a["fam"]], strong=a["primary"],
                       tip=[["Sharpe, rule / static", f"{E['arm']['sharpe']:.2f} / {E['ctrl']['sharpe']:.2f}"], ["Change", SG(E["d"]["d_sharpe"])],
                            ["95% interval", f"{SG(b['ci'][0])} to {SG(b['ci'][1])}"], ["Strong-hedge tape", SG(b2["d"]["d_sharpe"])],
                            ["First half / second half", f"{SG(a['win']['DISC']['d']['d_sharpe'])} / {SG(a['win']['CONF']['d']['d_sharpe'])}"],
                            ["Max drawdown, rule / static", f"{P(E['arm']['maxdd'])} / {P(E['ctrl']['maxdd'])}"],
                            ["CAGR, rule / static / live", f"{P(E['arm']['cagr'])} / {P(E['ctrl']['cagr'])} / {P(L['EXT']['cagr'])}"],
                            ["Average invested", P(a["avg_exposure"]["EXT"], 0)], ["Timing placebo percentile", f"{E['placebo']['pct_sharpe']:.0f}"],
                            ["Pre-registered primary", "yes" if a["primary"] else "no"]]))
    rows.append([k, a["label"], P(a["avg_exposure"]["EXT"], 0), f"{E['arm']['sharpe']:.2f}", f"{E['ctrl']['sharpe']:.2f}", SG(E["d"]["d_sharpe"]),
                 f"{SG(b['ci'][0])} to {SG(b['ci'][1])}", f"{a['verdict']['survives']['p_adj']:.2f}", SG(a["win"]["DISC"]["d"]["d_sharpe"]), SG(a["win"]["CONF"]["d"]["d_sharpe"]),
                 P(E["arm"]["maxdd"]), P(E["ctrl"]["maxdd"]), P(E["arm"]["cagr"]), P(E["ctrl"]["cagr"]), f"{E['placebo']['pct_sharpe']:.0f}", f"{E['placebo']['pct_maxdd']:.0f}",
                 SG(b2["d"]["d_sharpe"]), SG(a["mirror"]["EXT"]["d"]["d_sharpe"])])
table = dict(head=["Rule", "What it does", "Invested", "Sharpe", "Static", "Change", "95% interval", "Adj. p", "1st half", "2nd half", "Max DD", "Static DD",
                   "CAGR", "Static CAGR", "Placebo pct (Sharpe)", "Placebo pct (DD)", "Strong-hedge tape", "Mirror rule"], rows=rows)

# ---------- frontier
def frontier(w, title, sub, xr, yr):
    st = T1["static"]; line = [dict(x=round(L[w]["maxdd"] * 100, 1), y=round(L[w]["cagr"] * 100, 2), short="Live 100%", label="Live book", dy=-10, dx=6)]
    for k, nm in (("S-CASH90", "90/10"), ("S-CASH80", "80/20"), ("S-CASH70", "70/30")):
        m = st[k]["win"][w]["m"]; line.append(dict(x=round(m["maxdd"] * 100, 1), y=round(m["cagr"] * 100, 2), short=nm, label=st[k]["label"], dy=15, dx=-7, anchor="end"))
    for p in line:
        p["tip"] = [["CAGR", f"{p['y']:.1f}%"], ["Max drawdown", f"{p['x']:.1f}%"]]
    pts = []
    for k, a in A.items():
        m = a["win"][w]["arm"]
        pts.append(dict(x=round(m["maxdd"] * 100, 1), y=round(m["cagr"] * 100, 2), c=FC[a["fam"]], label=f"{k} {a['label']}",
                        tip=[["CAGR", P(m["cagr"])], ["Max drawdown", P(m["maxdd"])], ["Sharpe", f"{m['sharpe']:.2f}"], ["Average invested", P(a["avg_exposure"][w], 0)]]))
    return dict(title=title, sub=sub, x=xr, y=yr, line=line, pts=pts,
                callouts=[dict(x=round(A["A2"]["win"][w]["arm"]["maxdd"] * 100, 1), y=round(A["A2"]["win"][w]["arm"]["cagr"] * 100, 2), short="A2")])
fr = dict(ext=frontier("EXT", "2007-06 to 2026-11 (includes 2008)", "CAGR (vertical) against worst drawdown. Each dot is one rule; the line is the live book diluted with T-bills", [-40, -10], [2, 9]),
          conf=frontier("CONF", "2017-04 to 2026-11 (real holdings era)", "CAGR against worst drawdown on the period with the real TAIL and no 2008", [-28, -6], [4, 11.5]))

# ---------- walk-forward by year
wfp = T1["walkforward"]["sharpe"]["picks"]; yrs = sorted(int(y) for y in wfp)
lv = pd.Series(s["live"], index=cal); wv = pd.Series(s["wf_sharpe"], index=cal)
wf = dict(years=[str(y) for y in yrs], picks=[f"Pick: {wfp[str(y)]}" + ("" if wfp[str(y)] == "LIVE" else f" - {A[wfp[str(y)]]['label']}") for y in yrs],
          live=[round(float((1 + lv.loc[str(y)]).prod() - 1) * 100, 1) for y in yrs], wf=[round(float((1 + wv.loc[str(y)]).prod() - 1) * 100, 1) for y in yrs])

# ---------- leave-one-out (2017+; same on both tapes because 2017+ uses real holdings)
legs = sorted(C.LEGS, key=lambda l: -T1["static"][f"LOO-{l}-prorata"]["win"]["CONF"]["d"]["d_sharpe"])
def loo_rows(key, ci, scale, fmt):
    out = []
    for l in legs:
        w = T1["static"][f"LOO-{l}-prorata"]["win"]["CONF"]
        out.append(dict(label=f"Without {l}", v=round(w["d"][key] * scale, 3), lo=round(w[ci][0] * scale, 3), hi=round(w[ci][1] * scale, 3), c="--s1",
                        tip=[["Change", fmt(w["d"][key] * scale)], ["95% interval", f"{fmt(w[ci][0] * scale)} to {fmt(w[ci][1] * scale)}"],
                             ["CAGR change", SG(w["d"]["d_cagr"] * 100) + " pts/yr"], ["Sharpe without it", f"{w['m']['sharpe']:.2f}"], ["Max drawdown without it", P(w["m"]["maxdd"])]]))
    return out
loo = dict(sharpe=dict(title="Sharpe change if the leg is dropped", sub="2017-04 to 2026-11, rest of the book scaled up; bar = 95% interval", rows=loo_rows("d_sharpe", "ci", 1, SG),
                       lo=-.4, hi=.4, ticks=[-.4, -.2, 0, .2, .4], axisLabel=["← leg helps", "leg hurts →"]),
           dd=dict(title="Max drawdown change if the leg is dropped (pts)", sub="Negative = deeper drawdown without the leg", rows=loo_rows("d_maxdd", "ci_dd", 100, lambda v: SG(v, 1)),
                   lo=-14, hi=16, ticks=[-10, -5, 0, 5, 10, 15], axisLabel=["← leg protects", "leg adds drawdown →"]))

# ---------- candidate edges
iso = r["isolation"]
def iso_rows(state):
    out = []
    for l in C.RISK:
        x = iso[l][state]["21"]
        out.append(dict(label=l, v=round(x["diff"] * 100, 2), lo=round(x["ci"][0] * 100, 2), hi=round(x["ci"][1] * 100, 2), c="--s1",
                        tip=[["Next 21 days, in state", SG(x["mean_in"] * 100) + "%"], ["Other days", SG(x["mean_out"] * 100) + "%"], ["Difference", SG(x["diff"] * 100) + " pts"],
                             ["95% interval", f"{SG(x['ci'][0] * 100)} to {SG(x['ci'][1] * 100)}"], ["Days / separate spells", f"{x['n_days']} / {x['spells']}"],
                             ["History from", r["leg_tier"][l]["start"]]]))
    return out
edges = dict(os=dict(title="After RSI(14) < 30: next-21-day return vs other days (pts)", sub="Each leg alone on its long history, entered at the next close", rows=iso_rows("RSI14 < 30"),
                     lo=-3, hi=5, ticks=[-2, 0, 2, 4], axisLabel=["← weaker after oversold", "stronger →"]),
             ob=dict(title="After RSI(14) > 70: next-21-day return vs other days (pts)", sub="Overbought readings were not followed by weakness", rows=iso_rows("RSI14 > 70"),
                     lo=-3, hi=5, ticks=[-2, 0, 2, 4], axisLabel=["← weaker after overbought", "stronger →"]))

# ---------- text (numbers pulled from results.json)
W = T1["walkforward"]["sharpe"]; a2 = A["A2"]; ds = np.array([A[k]["win"]["EXT"]["d"]["d_sharpe"] for k in A])
best = max(A, key=lambda k: A[k]["win"]["EXT"]["d"]["d_sharpe"]); bE = A[best]["win"]["EXT"]
c80 = T1["static"]["S-CASH80"]["win"]
n_pass = sum(a["verdict"]["survives"]["pass"] for a in A.values()) + sum(a["verdict"]["survives"]["pass"] for a in T2["arms"].values())
n_dd = sum(a["verdict"]["drawdown_tool"]["pass"] for a in A.values()) + sum(a["verdict"]["drawdown_tool"]["pass"] for a in T2["arms"].values())
conf_macro = {k: A[k]["win"]["CONF"]["d"]["d_sharpe"] for k in ("M1", "M2", "M3", "M4", "M5", "M10", "M11", "M14", "M15", "M17")}
text = dict(
    lede=f"53 pre-registered rules (trend exits, trailing stops, RSI and run-up harvesting, volume signals, CAPE, VIX, credit, unemployment) were run on the live "
         f"weights from 2007 to 2026, each against a static book with the same average exposure. {n_pass} pass the Sharpe test and {n_dd} pass the weaker drawdown test. "
         f"Choosing each year the rule that had worked best would have returned {P(W['arm']['cagr'])} a year against {P(W['live']['cagr'])} for leaving the book alone.",
    t1=f"The live book compounded at {P(L['EXT']['cagr'])} with a {P(L['EXT']['maxdd'])} worst drawdown (2008, on stand-in data). The closest rule, holding each risk leg only above "
       f"its own 10-month average, cut the drawdown to {P(a2['win']['EXT']['arm']['maxdd'])} but compounded at {P(a2['win']['EXT']['arm']['cagr'])}. A 6% trailing stop on the whole book "
       f"did worse on both counts than simply holding less.",
    eq_sub=f"2007-06 to 2026-11, daily closes, costs included; signal at one close, trade at the next",
    eq_cap="Before 2017 TAIL earns T-bills and KMLM is a managed-futures mutual fund; before 2019 the Avantis legs are DFA funds. The walk-forward line equals the live book until 2010.",
    dd_sub="Weekly low of the daily drawdown",
    dd_cap=f"Worst drawdown: live {P(L['EXT']['maxdd'])}, 10-month rule {P(a2['win']['EXT']['arm']['maxdd'])}, 6% stop {P(A['B8']['win']['EXT']['arm']['maxdd'])}. "
           f"A static book at the 10-month rule's 76% average exposure: {P(a2['win']['EXT']['ctrl']['maxdd'])}.",
    t2="Rules that step aside during a fall are still out when the market turns. In 2020 the live book fell 22% and then gained 51%; the rules avoided most of the fall and missed most of the gain. "
       "2008 was a long decline, which is why every exit rule looks good there and why it flatters the 19-year averages.",
    ep_sub="Peak-to-trough windows for the falls; 2020-03-24 to year-end for the rebound",
    ep_cap="GFC numbers rest on stand-in data for TAIL, KMLM, QUAL and the Avantis legs.",
    t3=f"{int((ds < 0).sum())} of 53 rules lowered Sharpe against their matched static book (median {SG(float(np.median(ds)))}). The best, {best} ({A[best]['label'].lower()}), gained "
       f"{SG(bE['d']['d_sharpe'])} with an interval of {SG(bE['b21']['ci'][0])} to {SG(bE['b21']['ci'][1])} and a deeper drawdown than its control. "
       f"The lowest multiplicity-adjusted p-value is {min(a['verdict']['survives']['p_adj'] for a in A.values()):.2f}. Bold rows are the eight primary rules fixed before the run.",
    forest_cap="Paired circular block bootstrap, 21-day blocks, 4,000 draws; 63-day blocks give the same reading. Results on the strong-hedge tape are in the hover and the table.",
    t4=f"Mixing the live book with T-bills moves down a straight line: 80/20 keeps the Sharpe ({SG(c80['EXT']['d']['d_sharpe'])}), cuts the drawdown by {c80['EXT']['d']['d_maxdd'] * 100:.1f} pts and costs "
       f"{abs(c80['EXT']['d']['d_cagr']) * 100:.1f} pts a year. A rule only adds value if it sits above that line in both periods. With 2008 included several per-leg rules do; since 2017 almost none do.",
    t5=f"Each year-end from 2009, pick the rule with the best Sharpe so far and run it for the next year. Result 2010-2026: Sharpe {W['arm']['sharpe']:.2f} against {W['live']['sharpe']:.2f}, "
       f"CAGR {P(W['arm']['cagr'])} against {P(W['live']['cagr'])}. The picks were macro gates that had dodged 2008 and then sat out the recoveries of 2019, 2022-23 and 2025.",
    wf_sub="Hover a year to see which rule was picked",
    wf_cap=f"The stitched path lands at the {W['placebo_pct_sharpe']:.0f}th percentile of its own time-shifted placebos. The rule menu was written with hindsight, so this is an upper bound.",
    t6="No leg is flagged: every Sharpe interval contains zero. Gold is the leg the book can least afford to lose. AVUV has the weakest point estimate but the widest interval. "
       "KMLM and TAIL do not lift Sharpe; they shave the drawdown, and since 2017 TAIL has done that no more cheaply than T-bills would have.",
    t7="None of these clears a multiple-testing bar (120 tests were run; about six would look significant by chance). They are consistent with each other and with the earlier finding that selling into weakness is the wrong side.",
    edges=[], honesty=[])
D = dict(text=text, tiles=[], eq=dict(t=t, **eq), dd=dd, exp=expo, ep=ep, forest=forest, table=table, frontier=fr, wf=wf, loo=loo, edges=edges)
D["tiles"] = [dict(l="Rules that pass the Sharpe test", v=f"{n_pass} of 53", d="on either data tape"),
              dict(l="Rules that pass the drawdown test", v=f"{n_dd} of 53", d="closest: 10-month rule per leg"),
              dict(l="Walk-forward optimizer, CAGR", v=P(W["arm"]["cagr"]), d=f"live book {P(W['live']['cagr'])}, 2010-2026"),
              dict(l="Live book Sharpe, 2007-2026", v=f"{L['EXT']['sharpe']:.2f}", d=f"CAGR {P(L['EXT']['cagr'])}, max drawdown {P(L['EXT']['maxdd'])}")]
q = iso["QUAL"]["RSI14 < 30"]["21"]; g = iso["PHYS"]["RSI14 < 30"]["21"]; dv = iso["AVDV"]["RSI14 > 70"]["21"]; em = iso["AVEM"]["RSI14 > 70"]["21"]
vc = iso["QUAL"]["volume climax (down day, z>3)"]["5"]; lt = r["leg_tier"]
text["edges"] = [
    f"<b>Oversold bounce.</b> After RSI(14) below 30 the next 21 days beat other days by {SG(q['diff'] * 100, 1)} pts on SPY/QUAL ({q['n_days']} days in {q['spells']} spells, interval {SG(q['ci'][0] * 100, 1)} to {SG(q['ci'][1] * 100, 1)}) "
    f"and {SG(g['diff'] * 100, 1)} pts on gold ({g['n_days']} days, {SG(g['ci'][0] * 100, 1)} to {SG(g['ci'][1] * 100, 1)}). To use it: never sell a leg into an oversold reading; if a band rebalance falls due then, do it.",
    f"<b>Strength persists on the international legs.</b> After RSI(14) above 70, the AVDV and AVEM proxies beat other days by {SG(dv['diff'] * 100, 1)} and {SG(em['diff'] * 100, 1)} pts over 21 days. "
    f"Trimming them on that signal lowered Sharpe by {abs(lt['AVDV']['rules']['RSI70 half-trim']['d']['d_sharpe']):.2f} and {abs(lt['AVEM']['rules']['RSI70 half-trim']['d']['d_sharpe']):.2f} over 30 years, the only significant results in the study. Mutual-fund pricing flatters this somewhat.",
    f"<b>High-volume down days.</b> On SPY the next 5 days were {SG(vc['diff'] * 100, 1)} pt better than usual ({vc['n_days']} days, interval {SG(vc['ci'][0] * 100, 1)} to {SG(vc['ci'][1] * 100, 1)}). Selling after one is the wrong side.",
    f"<b>Trend filters by leg, 30 years.</b> A 10-month or 200-day filter helped emerging markets ({SG(lt['AVEM']['rules']['SMA200']['d']['d_sharpe'])}), international small value ({SG(lt['AVDV']['rules']['SMA200']['d']['d_sharpe'])}) "
    f"and large-cap ({SG(lt['QUAL']['rules']['10-month SMA']['d']['d_sharpe'])}) against same-exposure controls, and hurt US small value ({SG(lt['AVUV']['rules']['SMA200']['d']['d_sharpe'])}) and gold ({SG(lt['PHYS']['rules']['SMA200']['d']['d_sharpe'])}). "
    "No interval excludes zero. Turning any of these into a rule needs a single pre-registered test on new data."]
tf = T2["tail_fit"]
text["honesty"] = [
    "Daily closes, mark-to-market, Sharpe measured over T-bills. A signal at one close trades at the next close. Costs of 3 to 12 bps one-way per leg are charged. Every number is history, not a forecast.",
    f"Power: over 19 years this design can detect a Sharpe gain of roughly {min(a['win']['EXT']['b21']['mde_family'] for a in A.values() if a['fam'] == 'BOOK' and a['avg_exposure']['EXT'] < .9):.1f} or more for rules that switch the whole book. It rules out a large edge, not a small one.",
    f"Data before 2017 uses stand-ins: TAIL earns T-bills, or on a second tape a Treasuries-plus-puts model that over-earns real TAIL by {(tf['ann_ret_model'] - tf['ann_ret_real']) * 100:.1f} pts a year; KMLM is a managed-futures mutual fund (doubled on the second tape before 2010); QUAL is SPY before 2013; the Avantis legs are DFA funds before 2019. Verdicts are the same on both tapes.",
    "The two halves (2007-2017 and 2017-2026) are a consistency check, not a holdout. The design and its one amendment were committed before any result existed.",
    "Not modelled: intraday stops, partial fills, option hedges, revisions to unemployment and CAPE data, taxes (none under Act 60)."]
json.dump(D, open(os.path.join(C.CACHE, "report_data.json"), "w"))
tpl = open(os.path.join(C.HERE, "report_template.html")).read()
open(os.path.join(C.STUDY, "report.html"), "w").write(tpl.replace("/*DATA*/", json.dumps(D, separators=(",", ":"))))
print(json.dumps(text, indent=1))
