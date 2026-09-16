"""BLOCK regime_petro — spec v1 (oil-shock-recession-weight.md), run 2026-09-15.
Owns: Q3 supply/demand classification (descriptive), R3 descriptive tests,
Q4 H4a (recycling) and H4b (transmission), Figures 5 and 6.
Re-runnable end to end from the frozen inputs; edits nothing under the repo."""
import json, math
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = f"{ROOT}/blocks/regime_petro"
P = pd.read_csv(f"{ROOT}/data/panel.csv", index_col="date", parse_dates=True)
P.index = P.index.to_period("M")
EV = json.load(open(f"{ROOT}/data/events.json"))
T = pd.read_csv(f"{ROOT}/data/tic_oil_exporters.csv", index_col="date", parse_dates=True)
T.index = T.index.to_period("M")
USREC = P["usrec"]
# Frozen WMTSECL1 prints 0 for 2002-12..2007-07-04 (series not yet reported); treat 0 as missing, 12m % from 0 (inf) as missing.
CUST_ZERO_MONTHS = int((P["custody_bn"] == 0).sum())
P.loc[P["custody_bn"] == 0, "custody_bn"] = np.nan
P["custody_12m_pct"] = P["custody_12m_pct"].replace([np.inf, -np.inf], np.nan)
CUST_FIRST = str(P["custody_bn"].dropna().index[0]); CUST12_FIRST = str(P["custody_12m_pct"].dropna().index[0])
M = lambda s: pd.Period(s, "M")
RES_CUT = M(EV["last_resolved_month_h12"])
ONSETS = [M(x) for x in EV["recession_onsets"]]
WSTART = M("1953-04")
H = 12
NUM = {}           # every reported number, with definition
def rec(key, value, definition):
    if isinstance(value, (np.floating, float)) and not isinstance(value, bool):
        value = None if (value is None or (isinstance(value, float) and math.isnan(value))) else round(float(value), 4)
    elif isinstance(value, (np.integer,)): value = int(value)
    NUM[key] = {"value": value, "def": definition}
    return value
def regime(p):
    y = p.year
    return "R0" if y <= 1985 else "R1" if y <= 2008 else "R2" if y <= 2019 else "R3"
def pct(a, b): return (b / a - 1.0) * 100.0

rec("custody_zero_months_treated_missing", CUST_ZERO_MONTHS, "months where the frozen panel custody_bn == 0 (WMTSECL1 prints 0 before 2007-07-11); treated as missing")
rec("custody_first_valid_month", CUST_FIRST, "first month with a non-zero custody_bn")
rec("custody_12m_first_valid_month", CUST12_FIRST, "first month with a finite custody_12m_pct after dropping inf (12m change from a 0 print)")
# ----------------------------------------------------------------------------------
# 1. D1-RED episodes (§4 rule exactly as the event block implements it)
# ----------------------------------------------------------------------------------
def build_episodes(on, col):
    idx = list(on[on].index)
    runs, cur = [], [idx[0]]
    for t in idx[1:]:
        if (t - cur[-1]).n - 1 <= 6: cur.append(t)
        else: runs.append(cur); cur = [t]
    runs.append(cur)
    eps = []
    for r in runs:
        on0 = [t for t in r if USREC[t] == 0]
        vals = P.loc[r, col]
        eps.append(dict(raw_first=r[0], raw_last=r[-1], on0=on0, first0=on0[0] if on0 else None,
                        last0=on0[-1] if on0 else None, n_on=len(r), n_on0=len(on0),
                        peak=float(vals.max()), peak_month=vals.idxmax()))
    return eps

def score_episodes(eps, events, h, wstart, double_dip):
    claimed, out = set(), []
    for ep in sorted(eps, key=lambda e: e["raw_first"]):
        r = dict(ep); hits = []
        if ep["raw_first"] < wstart:
            r.update(status="not scored (before common window 1953-04)", hits=[], coincident_with=[], lead=None)
            out.append(r); continue
        if ep["on0"]:
            for e in events:
                if e in claimed: continue
                on0 = ep["on0"]
                if e == double_dip[0]:
                    on0 = [t for t in on0 if double_dip[1] <= t <= double_dip[2]]
                    if not on0: continue
                if on0[0] < e <= on0[-1] + h: hits.append(e)
        coin = [e for e in events if e <= ep["raw_first"] <= e + 3]
        if hits: status = "hit"; claimed |= set(hits)
        elif coin: status = "coincident"
        elif not ep["on0"]: status = "in-recession (excluded)"
        elif not (ep["last0"] + h <= RES_CUT): status = "pending"
        else: status = "false positive"
        r.update(status=status, hits=hits, coincident_with=coin,
                 lead=(int((hits[0] - ep["first0"]).n) if hits else None))
        out.append(r)
    return out

on_d1 = (P["oil_12m_pct"] >= 50).fillna(False)
EPS = score_episodes(build_episodes(on_d1, "oil_12m_pct"), ONSETS, H, WSTART,
                     (M("1981-08"), M("1980-08"), M("1981-07")))
for e in EPS:
    e["start"] = e["first0"] if e["first0"] is not None else e["raw_first"]   # raw first ON for in-recession-only
    e["label"] = str(e["start"]) + ("" if e["first0"] is not None else " (in-recession)")
rec("episodes_D1RED", [dict(start=str(e["start"]), usrec0_start=(e["first0"] is not None),
                            raw_span=f"{e['raw_first']}..{e['raw_last']}", n_on0=e["n_on0"], n_on=e["n_on"],
                            peak=round(e["peak"], 2), peak_month=str(e["peak_month"]), regime=regime(e["start"]),
                            outcome_h12=e["status"], events=[str(x) for x in e["hits"]],
                            coincident_with=[str(x) for x in e["coincident_with"]]) for e in EPS],
    "D1-RED episodes: ON = oil_12m_pct>=50; runs merge across <=6 OFF months; membership USREC_t=0; start = first USREC=0 ON month "
    "(raw first ON month for in-recession-only episodes, marked); outcome at h=12 by the event-block rules (hit if an onset lies in "
    "(first ON, last ON+12], coincident if raw first ON within [onset, onset+3], pending if last ON+12 > 2025-08, else false positive; "
    "1981-08 scored only on ON months 1980-08..1981-07; each onset credited once)")

# ----------------------------------------------------------------------------------
# 2. Supply vs demand (descriptive)
# ----------------------------------------------------------------------------------
DISRUPT = {"1973-10": "OPEC embargo", "1978-11": "Iranian revolution", "1980-09": "Iran-Iraq war",
           "1990-08": "Kuwait invasion", "2002-12": "Venezuela strike", "2003-03": "Iraq war",
           "2011-02": "Libya", "2019-09": "Abqaiq attack", "2022-02": "Ukraine invasion"}
ig12 = P["igrea_12m_chg"]
ig_med = ig12.rolling(120, min_periods=60).median()   # trailing-10-year median, window ends at the start month (inclusive)
ig_n = ig12.rolling(120, min_periods=60).count()
CLS = []
for e in EPS:
    s = e["start"]
    near = [(d, DISRUPT[d]) for d in DISRUPT if M(d) <= s <= M(d) + 3]
    if s >= M("2026-01"):
        narr, why = "unclassified pending Casey", "2026 event not yet named (P1 #2)"
    elif near:
        narr, why = "supply", f"{near[0][1]} {near[0][0]} (+{(s - M(near[0][0])).n}m)"
    else:
        # nearest prior disruption for the reader
        prior = [d for d in DISRUPT if M(d) <= s]
        why = ("no pre-listed disruption in the 3 months before" +
               (f"; nearest prior = {DISRUPT[prior[-1]]} {prior[-1]} ({(s - M(prior[-1])).n}m earlier)" if prior else ""))
        narr = "demand"
    if pd.notna(ig12.get(s, np.nan)) and pd.notna(ig_med.get(s, np.nan)):
        igc = "demand-consistent" if ig12[s] > ig_med[s] else "supply-consistent"
        agree = ("n/a" if narr.startswith("unclassified") else
                 ("yes" if (narr == "demand") == (igc == "demand-consistent") else "no"))
        igv, igm, ign = float(ig12[s]), float(ig_med[s]), int(ig_n[s])
    else:
        igc, agree, igv, igm, ign = "n/a (IGREA starts 1968)", "n/a", None, None, 0
    CLS.append(dict(episode=e["label"], start=s, regime=regime(s), narrative=narr, narrative_basis=why,
                    igrea_12m_chg=igv, igrea_trailing10y_median=igm, igrea_window_n=ign, igrea_class=igc,
                    agree=agree, outcome=e["status"], events=[str(x) for x in e["hits"]]))
rec("supply_demand_table", [dict(episode=c["episode"], regime=c["regime"], narrative=c["narrative"], basis=c["narrative_basis"],
                                 igrea_12m_chg=(None if c["igrea_12m_chg"] is None else round(c["igrea_12m_chg"], 2)),
                                 igrea_trailing10y_median=(None if c["igrea_trailing10y_median"] is None else round(c["igrea_trailing10y_median"], 2)),
                                 igrea_window_n=c["igrea_window_n"], igrea_class=c["igrea_class"], agree=c["agree"],
                                 outcome_h12=c["outcome"], events=c["events"]) for c in CLS],
    "supply-driven iff episode start month s satisfies d <= s <= d+3 for a pre-listed disruption d; else demand-driven; 2026 = unclassified "
    "pending Casey. IGREA class: igrea_12m_chg at s > median of igrea_12m_chg over the 120 months ending at s (min 60) = demand-consistent")
summ = {}
for c in CLS:
    if c["outcome"].startswith("not scored"): continue
    k = c["narrative"]
    summ.setdefault(k, dict(n=0, hit=0, fp=0, coincident=0, pending=0, episodes=[]))
    summ[k]["n"] += 1; summ[k]["episodes"].append(c["episode"])
    st = c["outcome"]
    summ[k]["hit" if st == "hit" else "fp" if st == "false positive" else "coincident" if st == "coincident" else "pending"] += 1
rec("supply_demand_summary", summ, "D1-RED episodes in the common window by narrative class: n, hits, false positives, coincident, pending at h=12 (descriptive; n too small for inference)")

# ----------------------------------------------------------------------------------
# 3. R3 descriptive tests: correlations by regime with moving-block bootstrap
# ----------------------------------------------------------------------------------
REG = {"R1": (M("1986-01"), M("2008-12")), "R2": (M("2009-01"), M("2019-12")), "R3": (M("2020-01"), M("2026-08"))}
SIGN = {"R1": "negative", "R2": "negative", "R3": "positive"}
def block_boot(x, y, blk=12, draws=1000, seed=20260915):
    rng = np.random.default_rng(seed)
    n = len(x); nb = int(math.ceil(n / blk)); starts_max = n - blk
    pe, sp = np.empty(draws), np.empty(draws)
    for i in range(draws):
        st = rng.integers(0, starts_max + 1, size=nb)
        idx = np.concatenate([np.arange(s, s + blk) for s in st])[:n]
        xs, ys = x[idx], y[idx]
        pe[i] = np.corrcoef(xs, ys)[0, 1]
        sp[i] = stats.spearmanr(xs, ys).statistic
    return (np.nanpercentile(pe, [5, 95]), np.nanpercentile(sp, [5, 95]))
def verdict(point, ci, want):
    lo, hi = ci
    if lo > 0 and hi > 0: s = "positive"
    elif lo < 0 and hi < 0: s = "negative"
    else: return "CI straddles zero"
    return "supported" if s == want else "not supported (wrong sign)"
CORR = {}
for pair, col in [("oil_usd", "usd_12m_pct"), ("oil_custody", "custody_12m_pct")]:
    for rg, (a, b) in REG.items():
        if pair == "oil_custody" and rg == "R1": continue
        d = P.loc[a:b, ["oil_12m_pct", col]].dropna()
        if len(d) < 24: continue
        x, y = d["oil_12m_pct"].to_numpy(), d[col].to_numpy()
        pr, sr = float(np.corrcoef(x, y)[0, 1]), float(stats.spearmanr(x, y).statistic)
        cip, cis = block_boot(x, y)
        v = verdict(pr, cip, SIGN[rg])
        CORR[(pair, rg)] = dict(n=len(d), first=str(d.index[0]), last=str(d.index[-1]), pearson=pr, pearson_ci=[float(cip[0]), float(cip[1])],
                                spearman=sr, spearman_ci=[float(cis[0]), float(cis[1])], want=SIGN[rg], verdict=v,
                                verdict_spearman=verdict(sr, cis, SIGN[rg]))
        for k, vv in CORR[(pair, rg)].items():
            rec(f"{pair}_{rg}_{k}", vv, f"{pair.replace('_', '-')} 12m%-change correlation, regime {rg} ({a}..{b}), months with both series; "
                                       "moving-block bootstrap block 12, 1000 draws, seed 20260915, 90% CI = 5th/95th pct; "
                                       f"pre-stated supporting sign {SIGN[rg]}")
# named custody episodes
EPI_CUST = {"2014-16 oil crash": (M("2014-06"), M("2016-02")), "2022 shock": (M("2022-02"), M("2022-12"))}
CUST = {}
for name, (a, b) in EPI_CUST.items():
    d = P.loc[a:b, ["wti", "oil_12m_pct", "custody_bn", "custody_12m_pct"]].copy()
    d["seg2_share_pct"] = T["seg2_share_pct"].reindex(d.index)
    d["norway_share_pct"] = T["norway_share_pct"].reindex(d.index)
    CUST[name] = d
    rec(f"custody_{name[:7].replace(' ', '_').replace('-', '_')}_path",
        {str(i): dict(wti=round(r.wti, 2), oil_12m_pct=round(r.oil_12m_pct, 1), custody_bn=round(r.custody_bn, 1),
                      custody_12m_pct=round(r.custody_12m_pct, 1), seg2_share_pct=round(r.seg2_share_pct, 3),
                      norway_share_pct=round(r.norway_share_pct, 3)) for i, r in d.iterrows()},
        f"named-episode path {a}..{b}: WTISPLC, oil 12m %, Fed custody $bn (WMTSECL1 monthly mean/1000), custody 12m %, seg2 share %, Norway share %")
    rec(f"custody_{name[:7].replace(' ', '_').replace('-', '_')}_change_bn", float(d["custody_bn"].iloc[-1] - d["custody_bn"].iloc[0]),
        f"custody_bn at {b} minus at {a}")
    rec(f"custody_{name[:7].replace(' ', '_').replace('-', '_')}_change_pct", pct(d["custody_bn"].iloc[0], d["custody_bn"].iloc[-1]),
        f"custody_bn % change {a}->{b}")
    rec(f"oil_{name[:7].replace(' ', '_').replace('-', '_')}_change_pct", pct(d["wti"].iloc[0], d["wti"].iloc[-1]),
        f"WTISPLC % change {a}->{b}")

# (iii) 12m-ahead response of INDPRO / PAYEMS
def resp(s):
    out = {}
    for col in ["indpro", "payems"]:
        a, b = P[col].get(s, np.nan), P[col].get(s + 12, np.nan)
        out[col] = float(pct(a, b)) if pd.notna(a) and pd.notna(b) else None
    return out
RESP = []
for c in CLS:
    s = c["start"]
    r = resp(s)
    RESP.append(dict(episode=c["episode"], regime=c["regime"], narrative=c["narrative"], start=str(s), to=str(s + 12),
                     indpro_12m_pct=r["indpro"], payems_12m_pct=r["payems"], outcome=c["outcome"]))
sup01 = [r for r in RESP if r["regime"] in ("R0", "R1") and r["narrative"] == "supply"]
e2022 = [r for r in RESP if r["start"] == "2021-03"][0]
def mr(key):
    v = [r[key] for r in sup01 if r[key] is not None]
    return dict(mean=float(np.mean(v)), min=float(np.min(v)), max=float(np.max(v)), n=len(v), episodes=[r["episode"] for r in sup01 if r[key] is not None])
rec("resp_2022_indpro_12m_pct", e2022["indpro_12m_pct"], "INDPRO % change from 2021-03 (first D1-RED ON month of the 2021-22 episode) to 2022-03")
rec("resp_2022_payems_12m_pct", e2022["payems_12m_pct"], "PAYEMS % change from 2021-03 to 2022-03")
rec("resp_R0R1_supply_indpro", mr("indpro_12m_pct"), "INDPRO % change start->start+12 across R0/R1 supply-classified D1-RED episodes: mean, min, max, n, names")
rec("resp_R0R1_supply_payems", mr("payems_12m_pct"), "PAYEMS % change start->start+12 across R0/R1 supply-classified D1-RED episodes")
rec("resp_table", RESP, "12m-ahead INDPRO/PAYEMS response per D1-RED episode (start->start+12), all episodes for context")

# ----------------------------------------------------------------------------------
# 4. H4a recycling — non-overlapping annual (December) observations
# ----------------------------------------------------------------------------------
def annual(share_col, lo, hi):
    s = T[share_col].dropna()
    s = s[(s.index >= M(lo)) & (s.index <= M(hi))]
    yr = s.groupby(s.index.year).apply(lambda g: g.index.max())   # last available month per year
    pts = pd.Series({p: s[p] for p in yr.values})
    rows = []
    for p in pts.index:
        q = p - 12
        if q in pts.index and q >= M(lo):
            rows.append(dict(month=str(p), d_share_pp=float(pts[p] - pts[q]), share=float(pts[p]),
                             oil_12m_pct=float(pct(P["wti"][q], P["wti"][p]))))
    return pd.DataFrame(rows)
H4A = {}
for seg, col, lo, hi in [("seg1", "seg1_share_pct", "2000-03", "2011-12"), ("seg2", "seg2_share_pct", "2012-01", "2025-12"),
                         ("norway", "norway_share_pct", "2003-01", "2025-12")]:
    a = annual(col, lo, hi)
    pr = stats.pearsonr(a["oil_12m_pct"], a["d_share_pp"]); sr = stats.spearmanr(a["oil_12m_pct"], a["d_share_pp"])
    H4A[seg] = dict(n=len(a), months=f"{a['month'].iloc[0]}..{a['month'].iloc[-1]}", pearson=float(pr.statistic), pearson_p=float(pr.pvalue),
                    spearman=float(sr.statistic), spearman_p=float(sr.pvalue), sign_pearson=("+" if pr.statistic > 0 else "-"),
                    sign_spearman=("+" if sr.statistic > 0 else "-"), rows=a.round(3).to_dict("records"))
    for k in ["n", "months", "pearson", "pearson_p", "spearman", "spearman_p", "sign_pearson", "sign_spearman"]:
        rec(f"h4a_{seg}_{k}", H4A[seg][k], f"H4a {seg} ({col}, {lo}..{hi}): non-overlapping annual obs = last available month of each year "
                                        "(all Decembers); x = WTISPLC 12m % change Dec->Dec, y = 12m change in share of grand total (pp); "
                                        "p-values are plain two-sided (descriptive; the pre-stated test is the sign only)")
    rec(f"h4a_{seg}_rows", H4A[seg]["rows"], f"H4a {seg} annual observations")
s22 = float(T["seg2_share_pct"][M("2022-12")] - T["seg2_share_pct"][M("2021-12")])
rec("h4a_seg2_share_2021_12", float(T["seg2_share_pct"][M("2021-12")]), "seg2 share of grand total, 2021-12, %")
rec("h4a_seg2_share_2022_12", float(T["seg2_share_pct"][M("2022-12")]), "seg2 share of grand total, 2022-12, %")
rec("h4a_seg2_share_change_2022", s22, "seg2 share 2022-12 minus 2021-12, pp (leg 3: must be > 0)")
leg1 = H4A["seg1"]["pearson"] > 0; leg2 = H4A["seg2"]["pearson"] > 0; leg3 = s22 > 0
leg1s = H4A["seg1"]["spearman"] > 0; leg2s = H4A["seg2"]["spearman"] > 0
rec("h4a_leg1_seg1_sign_positive", bool(leg1), "H4a leg 1: Pearson sign > 0 in seg1 (Spearman reported alongside)")
rec("h4a_leg2_seg2_sign_positive", bool(leg2), "H4a leg 2: Pearson sign > 0 in seg2")
rec("h4a_leg3_2022_share_rose", bool(leg3), "H4a leg 3: seg2 share rose over the 12 months to 2022-12")
h4a_overall = "recycling link supported" if (leg1 and leg2 and leg3) else "recycling link NOT supported in the last shock"
h4a_overall_sp = "recycling link supported" if (leg1s and leg2s and leg3) else "recycling link NOT supported in the last shock"
rec("h4a_verdict", h4a_overall, "H4a overall verdict on Pearson signs (all three legs must pass)")
rec("h4a_verdict_spearman", h4a_overall_sp, "H4a overall verdict on Spearman signs")
# 2014-16 named-episode read
d1416 = T.loc[M("2014-06"):M("2016-02"), ["seg2_share_pct", "norway_share_pct", "basket3", "norway", "grand_total"]]
rec("h4a_2014_16_seg2_share_path", {str(i): round(v, 3) for i, v in d1416["seg2_share_pct"].items()}, "seg2 share % path 2014-06..2016-02")
rec("h4a_2014_16_seg2_share_change_pp", float(d1416["seg2_share_pct"].iloc[-1] - d1416["seg2_share_pct"].iloc[0]), "seg2 share 2016-02 minus 2014-06, pp")
rec("h4a_2014_16_seg2_bn_change", float(d1416["basket3"].iloc[-1] - d1416["basket3"].iloc[0]), "Saudi+UAE+Kuwait $bn 2016-02 minus 2014-06")
rec("h4a_2014_16_norway_share_change_pp", float(d1416["norway_share_pct"].iloc[-1] - d1416["norway_share_pct"].iloc[0]), "Norway share 2016-02 minus 2014-06, pp")
rec("h4a_2014_16_oil_change_pct", pct(P["wti"][M("2014-06")], P["wti"][M("2016-02")]), "WTISPLC % change 2014-06 -> 2016-02")
rec("h4a_2014_16_seg2_share_peak", dict(month=str(d1416["seg2_share_pct"].idxmax()), value=round(float(d1416["seg2_share_pct"].max()), 3)), "seg2 share max within 2014-06..2016-02")
rec("h4a_2014_16_seg2_share_trough", dict(month=str(d1416["seg2_share_pct"].idxmin()), value=round(float(d1416["seg2_share_pct"].min()), 3)), "seg2 share min within 2014-06..2016-02")
rec("h4a_2022_norway_share_change_pp", float(T["norway_share_pct"][M("2022-12")] - T["norway_share_pct"][M("2021-12")]), "Norway share 2022-12 minus 2021-12, pp")

# ----------------------------------------------------------------------------------
# 5. H4b verdict lines
# ----------------------------------------------------------------------------------
H4B = {}
for rg in ["R1", "R2", "R3"]:
    c = CORR[("oil_usd", rg)]
    H4B[f"usd_{rg}"] = f"H4b oil-USD {rg}: r = {c['pearson']:+.2f} [{c['pearson_ci'][0]:+.2f}, {c['pearson_ci'][1]:+.2f}] (pre-stated {c['want']}) -> {c['verdict']}"
for rg in ["R2", "R3"]:
    c = CORR[("oil_custody", rg)]
    H4B[f"custody_{rg}"] = f"H4b oil-custody {rg} (descriptive): r = {c['pearson']:+.2f} [{c['pearson_ci'][0]:+.2f}, {c['pearson_ci'][1]:+.2f}] -> {c['verdict']} vs sign {c['want']}"
r3v = CORR[("oil_usd", "R3")]["verdict"]
h4b_r3 = ("thesis supported in the current regime" if r3v == "supported" else "thesis not supported in the current regime")
rec("h4b_R3_verdict", h4b_r3, "H4b headline: R3 oil-USD sign test (positive, CI excluding zero) — a CI straddling zero = not supported")
rec("h4b_lines", H4B, "H4b verdict lines")

# ----------------------------------------------------------------------------------
# 6. Figures
# ----------------------------------------------------------------------------------
INK, INK2, SURF, GRID, BAND = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e1", "#e5e4e0"
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_VIOLET, C_MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7", "#e87ba4"
S_HIT, S_FP, S_COIN, S_PEND = "#008300", "#e34948", "#eda100", "#8a8985"
plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
def style(ax):
    ax.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
def rec_bands(ax, lo, hi):
    u = USREC.loc[lo:hi]; on = False
    for t, v in u.items():
        if v == 1 and not on: st = t; on = True
        if v == 0 and on: ax.axvspan(st.to_timestamp(), t.to_timestamp(), color=BAND, alpha=0.6, lw=0); on = False
    if on: ax.axvspan(st.to_timestamp(), hi.to_timestamp(how="end"), color=BAND, alpha=0.6, lw=0)
def ts(s): return s.index.to_timestamp()

# Fig 5
lo5, hi5 = M("2000-01"), M("2026-08")
fig, axs = plt.subplots(3, 1, figsize=(11, 15), sharex=True)
for ax in axs: style(ax); rec_bands(ax, lo5, hi5)
shade_lbl = False
for ax in axs:
    for (a, b) in EPI_CUST.values():
        ax.axvspan(a.to_timestamp(), b.to_timestamp(how="end"), color=C_MAGENTA, alpha=0.12, lw=0)
o = P.loc[lo5:hi5, "oil_12m_pct"]
axs[0].plot(ts(o), o.values, color=C_ORANGE, lw=2, label="WTI 12m % change (WTISPLC monthly mean)")
axs[0].axhline(0, color=INK2, lw=0.8); axs[0].axhline(50, color=C_ORANGE, lw=1, ls="--", label="D1 RED anchor (+50)")
axs[0].set_ylabel("oil, 12m % change"); axs[0].set_title("Oil shocks vs oil-exporter Treasury share and Fed custody — top: WTI 12-month % change", loc="left", fontsize=12, color=INK)
FULLT = pd.period_range(T.index.min(), T.index.max(), freq="M")
s1 = T["seg1_share_pct"].reindex(FULLT); s2 = T["seg2_share_pct"].reindex(FULLT); sn = T["norway_share_pct"].reindex(FULLT)
axs[1].plot(ts(s1), s1.values, color=C_BLUE, lw=2, label="seg1: TIC 'Oil Exporters' aggregate, 2000-03..2011-12 (share of grand total, %)")
axs[1].plot(ts(s2), s2.values, color=C_MAGENTA, lw=2, label="seg2: Saudi + UAE + Kuwait, 2012-01+ (share of grand total, %) — separate basket, never joined")
axs[1].plot(ts(sn), sn.values, color=C_YELLOW, lw=2, label="Norway (GPFG), 2003-01+ (share of grand total, %) — reported separately, never summed")
axs[1].axvline(M("2012-01").to_timestamp(), color=INK2, lw=1, ls=":")
axs[1].text(M("2012-03").to_timestamp(), 2.35, "segment break 2011-12 | 2012-01\n(different baskets, not spliced)", color=INK2, fontsize=8, va="top")
axs[1].set_ylabel("share of foreign holdings, %"); axs[1].set_title("Middle: oil-exporter share of foreign Treasury holdings (TIC MFH, two unspliced segments)", loc="left", fontsize=12, color=INK)
cb = P.loc[lo5:hi5, "custody_bn"]
axs[2].plot(ts(cb), cb.values, color=C_AQUA, lw=2, label="Fed custody holdings for foreign official accounts, $bn (WMTSECL1, monthly mean)")
axs[2].set_ylabel("$ bn"); axs[2].set_title("Bottom: Fed custody holdings, $bn (all foreign official — oil exporters are a small share; reported from 2007-07)", loc="left", fontsize=12, color=INK)
axs[2].set_xlabel("Data: FRED WTISPLC, WMTSECL1 (reported from 2007-07), USREC; TIC mfhhis01.txt (to 2025-12). 2000-01..2026-08.\n"
                  "Shaded: NBER recessions (grey); named episodes 2014-06..2016-02 and 2022-02..2022-12 (pink). Norway gap = not listed by TIC in 2005.", color=INK2, fontsize=9)
for ax in axs:
    h, l = ax.get_legend_handles_labels()
    h += [Patch(facecolor=BAND, alpha=0.6, label="NBER recession"), Patch(facecolor=C_MAGENTA, alpha=0.12, label="named episode (2014-16, 2022)")]
    ax.legend(handles=h, loc="upper left", fontsize=8, frameon=False)
fig.suptitle("Fig 5 — Petrodollar recycling: oil, oil-exporter Treasury share (seg1 / seg2 / Norway) and Fed custody, 2000–2026", x=0.01, ha="left", fontsize=14, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.98)); fig.savefig(f"{OUT}/fig5_petrodollar.png", dpi=150); plt.close(fig)

# Fig 6
fig, ax = plt.subplots(figsize=(11, 5.5)); style(ax)
ax.axhline(0, color=INK2, lw=1)
xs = {"R1": 0, "R2": 1, "R3": 2}
MK = {"supported": "o", "not supported (wrong sign)": "X", "CI straddles zero": "s"}
for pair, colr, off, name in [("oil_usd", C_VIOLET, -0.12, "oil vs broad USD (12m % changes)"), ("oil_custody", C_AQUA, 0.12, "oil vs Fed custody (12m % changes)")]:
    first = True
    for rg, xo in xs.items():
        if (pair, rg) not in CORR: continue
        c = CORR[(pair, rg)]; x = xo + off
        ax.errorbar([x], [c["pearson"]], yerr=[[c["pearson"] - c["pearson_ci"][0]], [c["pearson_ci"][1] - c["pearson"]]], color=colr, lw=2, capsize=6, zorder=2)
        ax.plot([x], [c["pearson"]], marker=MK[c["verdict"]], ms=11, color=colr, mec=INK, mew=0.8, ls="none", zorder=3, label=name + " — Pearson, 90% block-bootstrap CI" if first else None)
        ax.plot([x + 0.05], [c["spearman"]], marker="D", ms=8, mfc="none", mec=colr, mew=2, ls="none", zorder=3, label=name + " — Spearman (hollow)" if first else None)
        first = False
        ax.text(x, c["pearson_ci"][1] + 0.04, f"{c['verdict']}\nr={c['pearson']:+.2f}, n={c['n']}", ha="center", va="bottom", fontsize=8, color=INK)
for rg, xo in xs.items():
    ax.text(xo, -1.17, f"{rg} ({REG[rg][0].year}–{REG[rg][1].year})\npre-stated sign: {SIGN[rg]}\n(net {'importer' if SIGN[rg]=='negative' else 'exporter'})", ha="center", va="bottom", fontsize=9, color=INK)
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["R1", "R2", "R3"]); ax.set_ylim(-1.2, 1.05); ax.set_xlim(-0.6, 2.6)
ax.set_ylabel("correlation of 12m % changes")
ax.set_title("Fig 6 — Does oil co-move with the dollar and with Fed custody? Correlation by regime with 90% block-bootstrap bars", loc="left", fontsize=12, color=INK)
ax.set_xlabel("Data: FRED WTISPLC, DTWEXM/DTWEXBGS (ratio-spliced), WMTSECL1; monthly 12m % changes 1986-01..2026-08 (custody: R2/R3 only, finite 12m changes from 2008-07).\n"
              "Moving-block bootstrap, block 12, 1,000 draws, seed 20260915. Marker: circle = supported, square = CI straddles zero, X = wrong sign.", color=INK2, fontsize=8)
h, l = ax.get_legend_handles_labels()
h += [Line2D([], [], marker="o", color=INK2, ls="none", ms=9, label="verdict marker: supported"), Line2D([], [], marker="s", color=INK2, ls="none", ms=9, label="CI straddles zero"), Line2D([], [], marker="X", color=INK2, ls="none", ms=9, label="wrong sign")]
ax.legend(handles=h, loc="upper left", fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(f"{OUT}/fig6_oil_usd_corr.png", dpi=150); plt.close(fig)

# ----------------------------------------------------------------------------------
# 7. results.md
# ----------------------------------------------------------------------------------
L = []
L.append("# BLOCK regime_petro — results (spec v1, run 2026-09-15)\n")
L.append("Inputs: frozen `panel.csv`, `events.json`, `tic_oil_exporters.csv`. Everything here is DESCRIPTIVE under §4/§5 except the H4a/H4b sign tests, whose outcomes move certainty/glossary wording only (never a weight). Colour assignments in this block's figures: oil = orange, seg1 share = blue, seg2 share = magenta, Norway share = yellow, custody = aqua, oil–USD correlation = violet.\n")
L.append("## 1. D1-RED episodes (§4 rule, matches the event block)\n")
L.append("| start | raw span (all ON) | n ON (USREC=0) | peak | regime | outcome h=12 | event |\n|---|---|---|---|---|---|---|")
for e in EPS:
    L.append(f"| {e['label']} | {e['raw_first']}..{e['raw_last']} | {e['n_on0']} | {e['peak']:.1f} | {regime(e['start'])} | {e['status'].upper()} | {', '.join(str(x) for x in e['hits']) or (('coincident with ' + ', '.join(str(x) for x in e['coincident_with'])) if e['coincident_with'] else '—')} |")
L.append("\nTwo episodes (1974-01, 1990-09) have no USREC=0 ON month; they are kept in the classification table under their raw first ON month because they are the narrative anchor supply shocks, and carry the event block's COINCIDENT outcome. 1948-01 lies before the 1953-04 common window and is not scored.\n")
L.append("## 2. Supply vs demand (descriptive; cannot trigger a §5 action)\n")
L.append("Rule: supply-driven iff the episode start is within 3 months after a pre-listed disruption (d ≤ start ≤ d+3); otherwise demand-driven; 2026 unclassified pending Casey (P1 #2). IGREA cross-check: `igrea_12m_chg` at the start vs the median of the trailing 120 months (min 60) — above = demand-consistent.\n")
L.append("| episode | regime | narrative class | basis | IGREA 12m chg | trailing-10y median (n) | IGREA class | agree? | outcome h=12 |\n|---|---|---|---|---|---|---|---|---|")
for c in CLS:
    igv = "—" if c["igrea_12m_chg"] is None else f"{c['igrea_12m_chg']:+.1f}"
    igm = "—" if c["igrea_trailing10y_median"] is None else f"{c['igrea_trailing10y_median']:+.1f} ({c['igrea_window_n']})"
    L.append(f"| {c['episode']} | {c['regime']} | {c['narrative']} | {c['narrative_basis']} | {igv} | {igm} | {c['igrea_class']} | {c['agree']} | {c['outcome'].upper()}{(' ' + ', '.join(c['events'])) if c['events'] else ''} |")
L.append("\n**Hits by class (h = 12, common window):**\n")
L.append("| class | n | hit | false positive | coincident | pending | episodes |\n|---|---|---|---|---|---|---|")
for k, v in summ.items():
    L.append(f"| {k} | {v['n']} | {v['hit']} | {v['fp']} | {v['coincident']} | {v['pending']} | {', '.join(v['episodes'])} |")
L.append("\nPlainly: with 3 supply-classified and 9 demand-classified episodes in the window, n is far too small for any inference about supply vs demand shocks and recession odds; this table is a description, not a test. Note what the mechanical rule does: the 1979-08 episode is DEMAND by the rule (WTISPLC crossed +50 nine months after the 1978-11 Iranian revolution — the regulated series lags), and the 2021-03 episode is DEMAND by the rule (it began eleven months BEFORE the 2022-02 invasion, in the post-COVID demand recovery); the IGREA cross-check reads both the same way.\n")
L.append("## 3. R3 descriptive tests\n")
L.append("### 3(i) corr(oil 12m %, broad-USD 12m %) by regime — this IS H4b (transmission)\n")
L.append("Months where both exist; Pearson and Spearman; moving-block bootstrap (block 12, 1,000 draws, seed 20260915) 90% CI. Pre-stated supporting signs: R1, R2 negative (net importer), R3 positive (net exporter).\n")
L.append("| regime | months | n | Pearson [90% CI] | Spearman [90% CI] | pre-stated sign | verdict (Pearson) | verdict (Spearman) |\n|---|---|---|---|---|---|---|---|")
for rg in ["R1", "R2", "R3"]:
    c = CORR[("oil_usd", rg)]
    L.append(f"| {rg} | {c['first']}..{c['last']} | {c['n']} | {c['pearson']:+.2f} [{c['pearson_ci'][0]:+.2f}, {c['pearson_ci'][1]:+.2f}] | {c['spearman']:+.2f} [{c['spearman_ci'][0]:+.2f}, {c['spearman_ci'][1]:+.2f}] | {c['want']} | **{c['verdict']}** | {c['verdict_spearman']} |")
L.append("\n### 3(ii) corr(oil 12m %, Fed custody 12m %) by regime — descriptive only (custody reported from 2007-07 in the frozen WMTSECL1 — earlier prints are 0 and treated as missing; finite 12m changes from 2008-07)\n")
L.append("| regime | months | n | Pearson [90% CI] | Spearman [90% CI] | pre-stated sign | verdict (Pearson) | verdict (Spearman) |\n|---|---|---|---|---|---|---|---|")
for rg in ["R2", "R3"]:
    c = CORR[("oil_custody", rg)]
    L.append(f"| {rg} | {c['first']}..{c['last']} | {c['n']} | {c['pearson']:+.2f} [{c['pearson_ci'][0]:+.2f}, {c['pearson_ci'][1]:+.2f}] | {c['spearman']:+.2f} [{c['spearman_ci'][0]:+.2f}, {c['spearman_ci'][1]:+.2f}] | {c['want']} | {c['verdict']} | {c['verdict_spearman']} |")
L.append("\nCustody is ALL foreign official holdings (oil exporters are a small share, and Gulf holdings via European custodians are unobserved) — a null here is weak evidence either way.\n")
for name, d in CUST.items():
    a, b = EPI_CUST[name]
    L.append(f"**Named episode {name} ({a}..{b}):** WTI {pct(d['wti'].iloc[0], d['wti'].iloc[-1]):+.0f}%, custody {d['custody_bn'].iloc[0]:.0f} → {d['custody_bn'].iloc[-1]:.0f} $bn ({pct(d['custody_bn'].iloc[0], d['custody_bn'].iloc[-1]):+.1f}%), seg2 share {d['seg2_share_pct'].iloc[0]:.2f} → {d['seg2_share_pct'].iloc[-1]:.2f}%.\n")
    L.append("| month | WTI $ | oil 12m % | custody $bn | custody 12m % | seg2 share % | Norway share % |\n|---|---|---|---|---|---|---|")
    for i, r in d.iterrows():
        L.append(f"| {i} | {r.wti:.1f} | {r.oil_12m_pct:+.0f} | {r.custody_bn:.0f} | {r.custody_12m_pct:+.1f} | {r.seg2_share_pct:.2f} | {r.norway_share_pct:.2f} |")
    L.append("")
L.append("### 3(iii) 12-month-ahead response of INDPRO and PAYEMS: the 2021–22 episode vs R0/R1 supply-classified episodes\n")
L.append("% change from the episode's first ON month to +12 (INDPRO is revised data — context only).\n")
L.append("| episode | regime | narrative class | window | INDPRO 12m % | PAYEMS 12m % | outcome h=12 |\n|---|---|---|---|---|---|---|")
for r in RESP:
    if r["regime"] in ("R0", "R1") and r["narrative"] == "supply" or r["start"] == "2021-03":
        L.append(f"| **{r['episode']}** | {r['regime']} | {r['narrative']} | {r['start']}→{r['to']} | {r['indpro_12m_pct']:+.1f} | {r['payems_12m_pct']:+.1f} | {r['outcome'].upper()} |")
mi, mp = mr("indpro_12m_pct"), mr("payems_12m_pct")
L.append(f"| R0/R1 supply mean (range), n={mi['n']} | | | | {mi['mean']:+.1f} ({mi['min']:+.1f} to {mi['max']:+.1f}) | {mp['mean']:+.1f} ({mp['min']:+.1f} to {mp['max']:+.1f}) | |")
L.append("\nContext — every other D1-RED episode (not part of the comparison):\n")
L.append("| episode | regime | narrative class | window | INDPRO 12m % | PAYEMS 12m % | outcome h=12 |\n|---|---|---|---|---|---|---|")
for r in RESP:
    if not (r["regime"] in ("R0", "R1") and r["narrative"] == "supply" or r["start"] == "2021-03"):
        ip = "—" if r["indpro_12m_pct"] is None else f"{r['indpro_12m_pct']:+.1f}"; pp = "—" if r["payems_12m_pct"] is None else f"{r['payems_12m_pct']:+.1f}"
        L.append(f"| {r['episode']} | {r['regime']} | {r['narrative']} | {r['start']}→{r['to']} | {ip} | {pp} | {r['outcome'].upper()} |")
L.append("\nRead: the 2021–22 episode's 12-month path (+%.1f INDPRO, +%.1f PAYEMS) sits at the top of the R0/R1 supply range (mean %+.1f / %+.1f). Three comparison episodes; the 1974-01 and 1990-09 starts are already inside recessions, which mechanically depresses their 12m paths. Descriptive." % (e2022["indpro_12m_pct"], e2022["payems_12m_pct"], mi["mean"], mp["mean"]))
L.append("\n## 4. H4a — recycling (oil up ⇒ oil-exporter Treasury demand up)\n")
L.append("Non-overlapping annual observations = last available month of each year (all Decembers); y = 12m change in share of the TIC grand total (pp), x = WTISPLC 12m % change over the same Dec→Dec window. seg1 = TIC 'Oil Exporters' aggregate 2000-03..2011-12; seg2 = Saudi+UAE+Kuwait 2012-01+; Norway separate, never summed. The pre-stated test is the SIGN only (p-values are shown for scale, not as a test).\n")
L.append("| segment | obs | n | Pearson (p) | Spearman (p) | sign |\n|---|---|---|---|---|---|")
for seg in ["seg1", "seg2", "norway"]:
    h = H4A[seg]
    L.append(f"| {seg} | {h['months']} | {h['n']} | {h['pearson']:+.2f} ({h['pearson_p']:.2f}) | {h['spearman']:+.2f} ({h['spearman_p']:.2f}) | Pearson {h['sign_pearson']}, Spearman {h['sign_spearman']} |")
L.append(f"\n- Leg 1 (seg1 sign > 0): Pearson {H4A['seg1']['pearson']:+.2f} → **{'PASS' if leg1 else 'FAIL'}** (Spearman {H4A['seg1']['spearman']:+.2f} → {'pass' if leg1s else 'fail'})")
L.append(f"- Leg 2 (seg2 sign > 0): Pearson {H4A['seg2']['pearson']:+.2f} → **{'PASS' if leg2 else 'FAIL'}** (Spearman {H4A['seg2']['spearman']:+.2f} → {'pass' if leg2s else 'fail'})")
L.append(f"- Leg 3 (seg2 share rose over the 12 months to 2022-12): {T['seg2_share_pct'][M('2021-12')]:.3f}% → {T['seg2_share_pct'][M('2022-12')]:.3f}% = {s22:+.3f}pp → **{'PASS' if leg3 else 'FAIL'}**")
L.append(f"- **H4a verdict: {h4a_overall}** (Pearson legs); on Spearman legs: {h4a_overall_sp}.")
L.append(f"- Norway (separate): Pearson {H4A['norway']['pearson']:+.2f}, Spearman {H4A['norway']['spearman']:+.2f}, n = {H4A['norway']['n']}; Norway share 2021-12→2022-12 {NUM['h4a_2022_norway_share_change_pp']['value']:+.3f}pp.")
L.append(f"- 2014–16 named-episode read (oil {NUM['h4a_2014_16_oil_change_pct']['value']:+.0f}% 2014-06→2016-02): seg2 share {d1416['seg2_share_pct'].iloc[0]:.2f}% → {d1416['seg2_share_pct'].iloc[-1]:.2f}% ({NUM['h4a_2014_16_seg2_share_change_pp']['value']:+.2f}pp; peak {NUM['h4a_2014_16_seg2_share_peak']['value']['value']:.2f}% in {NUM['h4a_2014_16_seg2_share_peak']['value']['month']}, trough {NUM['h4a_2014_16_seg2_share_trough']['value']['value']:.2f}% in {NUM['h4a_2014_16_seg2_share_trough']['value']['month']}), Saudi+UAE+Kuwait $bn {d1416['basket3'].iloc[0]:.0f} → {d1416['basket3'].iloc[-1]:.0f}; Norway share {d1416['norway_share_pct'].iloc[0]:.2f}% → {d1416['norway_share_pct'].iloc[-1]:.2f}%.\n")
L.append("Annual observations (seg1 / seg2 / Norway):\n")
for seg in ["seg1", "seg2", "norway"]:
    L.append(f"| {seg} month | share % | Δshare 12m (pp) | oil 12m % |\n|---|---|---|---|")
    for r in H4A[seg]["rows"]:
        L.append(f"| {r['month']} | {r['share']:.2f} | {r['d_share_pp']:+.2f} | {r['oil_12m_pct']:+.0f} |")
    L.append("")
L.append("## 5. H4b — transmission (verdict lines)\n")
for k, v in H4B.items(): L.append(f"- {v}")
L.append(f"- **H4b headline (R3): {h4b_r3}.** Signs are findings; magnitudes are not. §5 consequence: `demand_strike` certainty string and glossary wording only, never a weight.\n")
L.append("## 6. Figures\n")
L.append("- `fig5_petrodollar.png` — Fig 5: three stacked panels (oil 12m %, oil-exporter share seg1/seg2/Norway as three separate lines, Fed custody $bn) 2000–2026 with NBER bands and the 2014–16 / 2022 named episodes shaded; the seg2 share rises through 2022 while custody falls.")
L.append("- `fig6_oil_usd_corr.png` — Fig 6: per-regime oil–USD (violet) and oil–custody (aqua) correlations with 90% block-bootstrap bars, Spearman as hollow diamonds, verdict by marker shape and label, pre-stated sign printed under each regime.\n")
L.append("## 7. Caveats (one line each)\n")
L.append("- Supply/demand split: mechanical narrative rule + IGREA; 12 scoreable episodes, 3 supply — description only.")
L.append("- IGREA trailing-10-year median uses a 120-month window ending at the start month, min 60 months (1974-01 window has 61 months).")
L.append("- H4a: TIC = custodian country; Gulf holdings via Belgium/UK/Cayman/Luxembourg unobserved, recycling under-stated; Dec→Dec share changes cross a June benchmark revision inside seg1 (2002–2011) because the spec's n≈11 annual design requires it; n = 11 / 13 / 20 (Norway: TIC does not list Norway in 2005, so the 2005-12 and 2006-12 annual observations do not exist).")
L.append("- H4b: R3 has 80 months = ~7 independent 12-month blocks; custody is all-foreign-official; usd_broad is a ratio-splice at 2006.")
L.append("- 3(iii): INDPRO is revised; the 1974-01 and 1990-09 supply starts are in-recession months.")
open(f"{OUT}/results.md", "w").write("\n".join(L) + "\n")
json.dump(NUM, open(f"{OUT}/numbers.json", "w"), indent=1, default=str)
print("\n".join(L))
