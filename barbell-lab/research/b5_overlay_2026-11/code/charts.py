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
                       ref=round(E["placebo"]["mean_sharpe"] - E["ctrl"]["sharpe"], 3),
                       tip=[["Sharpe, rule / static", f"{E['arm']['sharpe']:.2f} / {E['ctrl']['sharpe']:.2f}"], ["Change", SG(E["d"]["d_sharpe"])],
                            ["95% interval", f"{SG(b['ci'][0])} to {SG(b['ci'][1])}"], ["Strong-hedge tape", SG(b2["d"]["d_sharpe"])],
                            ["First half / second half", f"{SG(a['win']['DISC']['d']['d_sharpe'])} / {SG(a['win']['CONF']['d']['d_sharpe'])}"],
                            ["Max drawdown, rule / static", f"{P(E['arm']['maxdd'])} / {P(E['ctrl']['maxdd'])}"],
                            ["CAGR, rule / static / live", f"{P(E['arm']['cagr'])} / {P(E['ctrl']['cagr'])} / {P(L['EXT']['cagr'])}"],
                            ["Average invested", P(a["avg_exposure"]["EXT"], 0)], ["Same rule, timing shuffled", SG(E["placebo"]["mean_sharpe"] - E["ctrl"]["sharpe"])],
                            ["Percentile among shuffled versions", f"{E['placebo']['pct_sharpe']:.0f}"],
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

# ---------- text and small tables (numbers pulled from results.json)
W = T1["walkforward"]["sharpe"]; W2 = T2["walkforward"]["sharpe"]; a2 = A["A2"]; B = T2["arms"]
d12 = json.load(open(os.path.join(C.STUDY, "d12_etf_proxy.json")))
ds = np.array([A[k]["win"]["EXT"]["d"]["d_sharpe"] for k in A])
ap = np.array([A[k]["win"]["EXT"]["arm"]["sharpe"] - A[k]["win"]["EXT"]["placebo"]["mean_sharpe"] for k in A])
pm = np.array([A[k]["win"]["EXT"]["placebo"]["mean_sharpe"] - A[k]["win"]["EXT"]["ctrl"]["sharpe"] for k in A])
n90 = [sum(a["win"]["EXT"]["placebo"]["pct_sharpe"] >= 90 for a in X.values()) for X in (A, B)]
best = max(A, key=lambda k: A[k]["win"]["EXT"]["d"]["d_sharpe"]); bE = A[best]["win"]["EXT"]
st = T1["static"]; c80 = st["S-CASH80"]["win"]
n_pass = sum(a["verdict"]["survives"]["pass"] for X in (A, B) for a in X.values()) + sum(d12[v]["n_survive"] for v in d12)
n_dd = sum(a["verdict"]["drawdown_tool"]["pass"] for X in (A, B) for a in X.values()) + sum(d12[v]["n_drawdown_tool"] for v in d12)
p_min = min(a["verdict"]["survives"]["p_adj"] for X in (A, B) for a in X.values())
bs = [A[f"B{i}"]["win"]["EXT"]["arm"]["sharpe"] for i in range(1, 16)]
rb = [A[f"B{i}"]["episodes"]["COVID rebound"]["ret"] * 100 for i in range(7, 15)]
mde = sorted(A[k]["win"]["EXT"]["b21"]["mde_family"] for k in ("B3", "B8", "B15", "A1", "A6", "M1", "M14"))
FAIL = dict(dd2_both="drawdown not 2 pts better in both halves", ulcer_both="time under water not better", cagr_within="CAGR more than 0.5 pt below control",
            p_fw_lt_10="family-wise placebo p above 0.10", lag2="fails with one more day of lag")
near = dict(head=["Rule", "Max DD rule / static", "1st half", "2nd half", "Ulcer index 2017+ rule / static", "CAGR vs static", "CAGR vs live", "Placebo p raw / studentised", "Failed (tape 1; tape 2)"], rows=[])
for k in ("A2", "A15", "A6", "A8", "A7", "A10"):
    a = A[k]; w = a["win"]; dt = a["verdict"]["drawdown_tool"]; dt2 = B[k]["verdict"]["drawdown_tool"]; pl = w["EXT"]["placebo"]
    pz = pl["pz_fw8_maxdd"] if a["primary"] else pl["pz_fw53_maxdd"]
    f1 = "; ".join(FAIL[x] for x in FAIL if not dt[x]); f2 = "; ".join(FAIL[x] for x in FAIL if not dt2[x])
    near["rows"].append([f"<b>{k}</b> {a['label']}" + (" (primary)" if a["primary"] else ""), f"{P(w['EXT']['arm']['maxdd'])} / {P(w['EXT']['ctrl']['maxdd'])}",
                         SG(w["DISC"]["d"]["d_maxdd"] * 100, 1), SG(w["CONF"]["d"]["d_maxdd"] * 100, 1), f"{w['CONF']['arm']['ulcer'] * 100:.1f} / {w['CONF']['ctrl']['ulcer'] * 100:.1f}",
                         SG(w["EXT"]["d"]["d_cagr"] * 100) + " pt", SG(w["EXT"]["d_live"]["d_cagr"] * 100) + " pt", f"{dt['p_fw']:.2f} / {pz:.2f}", f1 if f1 == f2 else f"{f1} (tape 2: {f2})"])
lev = dict(head=["Static change to the book", "Drawdown, 2017+ (pts)", "95% interval", "CAGR, 2017+", "Sharpe, 2017+", "Drawdown, 2007+ (pts)", "CAGR, 2007+", "Drawdown pts per CAGR pt, 2017+"], rows=[])
for k, nm in (("S-CASH80", "20% T-bills (80/20)"), ("S-CASH90", "10% T-bills (90/10)"), ("S-KMLM20", "KMLM 14% → 20%"), ("S-KMLM25", "KMLM 14% → 25%"),
              ("S-TAIL10", "TAIL 6% → 10%"), ("S-TAIL15", "TAIL 6% → 15%"), ("S-TAIL0", "TAIL 6% → 0%"), ("LOO-TAIL-bil", "TAIL → T-bills")):
    x = st[k]["win"]["CONF"]; e = st[k]["win"]["EXT"]; ratio = x["d"]["d_maxdd"] / -x["d"]["d_cagr"] if x["d"]["d_cagr"] < 0 and x["d"]["d_maxdd"] > 0 else None
    lev["rows"].append([nm, SG(x["d"]["d_maxdd"] * 100, 1), f"{SG(x['ci_dd'][0] * 100, 1)} to {SG(x['ci_dd'][1] * 100, 1)}", SG(x["d"]["d_cagr"] * 100) + " pt", SG(x["d"]["d_sharpe"]),
                        SG(e["d"]["d_maxdd"] * 100, 1), SG(e["d"]["d_cagr"] * 100) + " pt", f"{ratio:.1f}" if ratio else "–"])
km = st["S-KMLM25"]["win"]["CONF"]; t10 = st["S-TAIL10"]["win"]["CONF"]
def above(w):
    xs = [L[w]["maxdd"]] + [st[k]["win"][w]["m"]["maxdd"] for k in ("S-CASH90", "S-CASH80", "S-CASH70")]
    ys = [L[w]["cagr"]] + [st[k]["win"][w]["m"]["cagr"] for k in ("S-CASH90", "S-CASH80", "S-CASH70")]
    sl = np.polyfit(xs, ys, 1)
    return {k for k, a in A.items() if a["win"][w]["arm"]["cagr"] > np.polyval(sl, a["win"][w]["arm"]["maxdd"])}
ab = {w: above(w) for w in ("EXT", "DISC", "CONF")}; both = ab["DISC"] & ab["CONF"]
ppc = lambda k: st[k]["win"]["CONF"]["d"]["d_maxdd"] / -st[k]["win"]["CONF"]["d"]["d_cagr"]
text = dict(
    lede=f"53 pre-registered rules (trend exits, trailing stops, RSI and run-up harvesting, volume signals, CAPE, VIX, credit, unemployment) were run on the live "
         f"weights from 2007 to 2026, each against a static book with the same average exposure. None passes the Sharpe test and none passes the weaker drawdown test, on either "
         f"data tape or with ETF proxies. Picking each year-end the rule with the best record so far would have returned {P(W['arm']['cagr'])} a year against {P(W['live']['cagr'])} for leaving the book alone.",
    t1=f"The live book compounded at {P(L['EXT']['cagr'])} with a {P(L['EXT']['maxdd'])} worst drawdown (2008, on stand-in data). The closest rule, holding each risk leg only above "
       f"its own 10-month average, cut the worst drawdown to {P(a2['win']['EXT']['arm']['maxdd'])} and compounded at {P(a2['win']['EXT']['arm']['cagr'])}. A 6% trailing stop on the whole book "
       f"did worse than simply holding less.",
    eq_sub="2007-06 to 2026-11, daily closes, costs included; signal at one close, trade at the next",
    eq_cap="Before 2017 TAIL earns T-bills and KMLM is a managed-futures mutual fund; before 2019 the Avantis legs are DFA funds. The walk-forward line equals the live book until 2010.",
    dd_sub="Weekly low of the daily drawdown",
    dd_cap=f"Worst drawdown: live {P(L['EXT']['maxdd'])}, 10-month rule {P(a2['win']['EXT']['arm']['maxdd'])}, 6% stop {P(A['B8']['win']['EXT']['arm']['maxdd'])}. "
           f"A static book at the 10-month rule's {P(a2['avg_exposure']['EXT'], 0)} average exposure: {P(a2['win']['EXT']['ctrl']['maxdd'])}.",
    t2=f"Rules that step aside during a fall are still out when the market turns. In 2020 the live book fell 22% and then gained 51% by year-end; the eight book-level stops gained "
       f"{min(rb):.0f}% to {max(rb):.0f}% in that rebound. 2008 was a long decline, which is why exit rules look good there and why it flatters the 19-year averages.",
    ep_sub="Peak-to-trough windows for the falls; 2020-03-24 to year-end for the rebound",
    ep_cap="2008 numbers rest on stand-in data for TAIL, KMLM, QUAL and the Avantis legs.",
    t3=f"{int((ds < 0).sum())} of 53 rules have a lower Sharpe than their matched static book (median {SG(float(np.median(ds)))}). About {abs(float(np.median(pm))):.2f} of that is structural: any rule that "
       f"switches in and out loses to a book that holds the same average exposure steadily, even with no information (grey ticks). Against that no-information version the rules split "
       f"{int((ap < 0).sum())} below and {int((ap > 0).sum())} above. {n90[0]} rules (tape 2: {n90[1]}) rank in the top tenth of their shuffled versions; about 5 would by chance. "
       f"The lowest multiplicity-adjusted p-value is {p_min:.2f}. Book-level rules span Sharpe {min(bs):.2f} to {max(bs):.2f} against {L['EXT']['sharpe']:.2f} for the live book. Bold rows are the eight primary rules.",
    forest_cap="Paired circular block bootstrap, 21-day blocks, 4,000 draws; 63-day blocks give the same reading. The best raw gain, CAPE half-weight, was switched on 87% of the time and had a deeper drawdown than its control.",
    t3b="Six per-leg rules cut the worst drawdown by at least 2 pts in both halves against a static book with the same exposure, and each ranks in the top 3% of its own shuffled versions. "
        "All six fail the registered test, mainly because since 2017 they spent more time under water than the static book: they shortened the deepest hole, not the time spent in holes. "
        "With ETF proxies in place of mutual-fund data the picture is the same and still nothing passes. Studentised across the family, none of the placebo p-values is below 0.10 except the 12% stop within the primary eight.",
    t4=f"Mixing the live book with T-bills moves along a straight line: 80/20 keeps the Sharpe ({SG(c80['EXT']['d']['d_sharpe'])}), cuts the drawdown by {c80['EXT']['d']['d_maxdd'] * 100:.1f} pts and costs "
       f"{abs(c80['EXT']['d']['d_cagr']) * 100:.1f} pts a year. A rule adds value only if it sits above that line. {len(ab['EXT'])} of 53 do over the full period, {len(ab['CONF'])} since 2017 and {len(both)} in both halves "
       f"(a coin flip per half would give about 13). Four of those {len(both)} are the per-leg trend rules above.",
    t4b=f"Three static levers were registered alongside the rules. Per point of CAGR given up since 2017, T-bills bought {ppc('S-CASH90'):.1f} to {ppc('S-CASH80'):.1f} pts of drawdown and extra TAIL "
        f"{ppc('S-TAIL10'):.1f} to {ppc('S-TAIL15'):.1f}, both with intervals that exclude zero. Extra KMLM bought {ppc('S-KMLM20'):.1f} to {ppc('S-KMLM25'):.1f}, the best price, but its interval "
        f"includes zero ({SG(km['ci_dd'][0] * 100, 1)} to {SG(km['ci_dd'][1] * 100, 1)} for 25%) and KMLM is proxy data before 2020-12.",
    t5=f"Each year-end from 2009, pick the rule with the best Sharpe since 2007 and run it for the next year (the live book is a candidate). Result 2010-2026: Sharpe {W['arm']['sharpe']:.2f} against {W['live']['sharpe']:.2f}, "
       f"CAGR {P(W['arm']['cagr'])} against {P(W['live']['cagr'])} (tape 2: {P(W2['arm']['cagr'])}, {W2['arm']['sharpe']:.2f}). The picks were macro gates that had dodged 2008 and then sat out the recoveries of 2019, 2022-23 and 2025.",
    wf_sub="Hover a year to see which rule was picked",
    wf_cap=f"The stitched path ranks at percentile {W['placebo_pct_sharpe']:.0f} of its own time-shifted placebos (tape 2: {W2['placebo_pct_sharpe']:.0f}). The rule menu was written with hindsight, so even this is an upper bound on what tuning would have paid.",
    t6="No leg is flagged: every Sharpe interval contains zero. Gold is the leg the book can least afford to lose. AVUV has the weakest point estimate and the widest interval. "
       "KMLM and TAIL do not lift Sharpe; they shave the drawdown.",
    t7="Six of 120 conditional-return tests have an interval that excludes zero; five or six would by chance. They agree with each other and with the earlier finding that selling into weakness is the wrong side, but none is tradeable as it stands.",
    edges=[], honesty=[])
D = dict(text=text, tiles=[], eq=dict(t=t, **eq), dd=dd, exp=expo, ep=ep, forest=forest, table=table, near=near, levers=lev, frontier=fr, wf=wf, loo=loo, edges=edges)
D["tiles"] = [dict(l="Rules that pass the Sharpe test", v="0 of 53", d="both tapes and the ETF-proxy rerun"),
              dict(l="Rules that pass the drawdown test", v="0 of 53", d="six per-leg rules come close"),
              dict(l="Walk-forward optimizer, CAGR", v=P(W["arm"]["cagr"]), d=f"live book {P(W['live']['cagr'])}, 2010-2026"),
              dict(l="Live book Sharpe, 2007-2026", v=f"{L['EXT']['sharpe']:.2f}", d=f"CAGR {P(L['EXT']['cagr'])}, max drawdown {P(L['EXT']['maxdd'])}")]
assert n_pass == 0 and n_dd == 0
q = iso["QUAL"]["RSI14 < 30"]["21"]; g = iso["PHYS"]["RSI14 < 30"]["21"]; dv = iso["AVDV"]["RSI14 > 70"]["21"]; em = iso["AVEM"]["RSI14 > 70"]["21"]
vc = iso["QUAL"]["volume climax (down day, z>3)"]["5"]; gv = iso["PHYS"]["VIX > VIX3M"]["5"]; lt = r["leg_tier"]
CI = lambda x, d=1: f"{SG(x['ci'][0] * 100, d)} to {SG(x['ci'][1] * 100, d)}"
text["edges"] = [
    f"<b>Oversold bounce.</b> After RSI(14) below 30 the next 21 days beat other days by {SG(q['diff'] * 100, 1)} pts on the SPY/QUAL leg ({q['n_days']} days in {q['spells']} spells, interval {CI(q)}) "
    f"and {SG(g['diff'] * 100, 1)} pts on gold ({g['n_days']} days in {g['spells']} spells, {CI(g)}). The overbought mirror is not negative. To use it: never sell a leg into an oversold reading; if a band rebalance falls due then, do it.",
    f"<b>Strength persists on the international legs.</b> After RSI(14) above 70 the AVDV and AVEM proxies beat other days by {SG(dv['diff'] * 100, 1)} and {SG(em['diff'] * 100, 1)} pts over 21 days ({CI(dv)}; {CI(em)}). "
    f"Trimming them on that signal lowered Sharpe by {abs(lt['AVDV']['rules']['RSI70 half-trim']['d']['d_sharpe']):.2f} and {abs(lt['AVEM']['rules']['RSI70 half-trim']['d']['d_sharpe']):.2f} over 30 years, "
    f"but most of that sits in 1996-2006 ({SG(lt['AVDV']['rules']['RSI70 half-trim']['sub']['1996-2006']['d_sharpe'])} then, {SG(lt['AVDV']['rules']['RSI70 half-trim']['sub']['2017-2026']['d_sharpe'])} since 2017 for AVDV), when mutual-fund prices were stale.",
    f"<b>High-volume down days.</b> On the SPY/QUAL leg the next 5 days were {SG(vc['diff'] * 100, 1)} pt better than usual ({vc['n_days']} days, {CI(vc)}). Selling after one is the wrong side.",
    f"<b>Gold after VIX backwardation.</b> When VIX closed above VIX3M, gold's next 5 days were {SG(gv['diff'] * 100, 1)} pt better ({gv['n_days']} days in {gv['spells']} spells, {CI(gv, 2)}).",
    f"<b>Trend filters by leg.</b> Against same-exposure controls a 200-day filter helped emerging markets ({SG(lt['AVEM']['rules']['SMA200']['d']['d_sharpe'])}) and international small value ({SG(lt['AVDV']['rules']['SMA200']['d']['d_sharpe'])}), "
    f"a 10-month filter helped large-cap ({SG(lt['QUAL']['rules']['10-month SMA']['d']['d_sharpe'])}); US small value was mixed ({SG(lt['AVUV']['rules']['SMA200']['d']['d_sharpe'])} on 200-day, {SG(lt['AVUV']['rules']['10-month SMA']['d']['d_sharpe'])} on 10-month) "
    f"and gold was worse ({SG(lt['PHYS']['rules']['SMA200']['d']['d_sharpe'])}, 21 years of data). No interval excludes zero. Turning any of these into a rule needs one pre-registered test on new data."]
tf = T2["tail_fit"]
text["honesty"] = [
    "Daily closes, mark-to-market, Sharpe measured over T-bills. A signal at one close trades at the next close. Costs of 3 to 12 bps one-way per leg are charged. Every number is history, not a forecast.",
    f"Power: over 19 years this design can detect a Sharpe gain of about {mde[0]:.1f} to {mde[-1]:.1f} for rules that switch large parts of the book, and about {A['B17']['win']['EXT']['b21']['mde_family']:.2f} for small trims. It rules out a large edge, not a small one.",
    "Max drawdown is one or two events per window (2008, 2020, 2022). A rule that happened to be out for one of them looks good on that measure; that is why the registered test also asked for less time under water.",
    f"Data before 2017 uses stand-ins: TAIL earns T-bills, or on a second tape a Treasuries-plus-puts model that over-earns real TAIL by {(tf['ann_ret_model'] - tf['ann_ret_real']) * 100:.1f} pts a year; KMLM is a managed-futures mutual fund (doubled on the second tape before 2010); QUAL is SPY before 2013; the Avantis legs are DFA funds before 2019. Verdicts are the same on both tapes and with ETF proxies.",
    "The two halves (2007-2017 and 2017-2026) are a consistency check, not a holdout. The design and its one amendment were committed before any result existed.",
    "Checked by three independent reviewers: the design before the build, a from-scratch recomputation of the headline numbers (agrees), and a code-and-claims audit (no code defect; its corrections to the write-up are applied here).",
    "Not modelled: intraday stops, partial fills, option hedges, revisions to unemployment and CAPE data, taxes (none under Act 60)."]
json.dump(D, open(os.path.join(C.CACHE, "report_data.json"), "w"))
tpl = open(os.path.join(C.HERE, "report_template.html")).read()
open(os.path.join(C.STUDY, "report.html"), "w").write(tpl.replace("/*DATA*/", json.dumps(D, separators=(",", ":"))))
print(text["t4"]); print(text["t4b"]); print(sorted(both))
