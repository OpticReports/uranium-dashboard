"""BLOCK = event  (oil-shock study, spec v1 2026-09-15; §3/§4/§5 bind).

Owns: instrument-agreement tables, expected episode lists (pre-outcome), Q1 primary
(D1-RED, h=12, NBER onsets, episode level, common window), kill-rate recount, curve-
conditioned isolation of oil, regime breakdown, Q5 dated readings, Figures 1 and 4.

Re-runnable end to end from the frozen inputs. Never edits the spec or the panel.

Reading choices where the spec text is ambiguous (also logged in results.md):
  * Episode membership = ON months with USREC_t = 0; in-recession ON months are NOT
    "OFF months", so they do not break an episode (this is what makes the 1981-08
    double-dip rule necessary). The episode's RAW first ON month (which may lie inside
    a recession) is what the coincident test uses — the spec's own 1973-12 / 1990-08
    expectations require that.
  * Classification order: hit > coincident > pending > false positive; an episode with
    no USREC_t = 0 month and no coincident onset is listed "in-recession (excluded)".
  * Resolved for horizon h: t + h <= 2025-08 (spec §4 text; events.json's
    last_resolved_month_h12 = 2025-08 is read as that cut-off).
  * Recall evaluability uses the RULE's own data window (oil_12m_pct 1947-01+,
    real_oil 1948-01+, nopi36_sum12 1949-12+, curve_flat_gs6m 1953-09+), not the
    common precision window — so 1953-08 IS evaluable for oil-alone rules.
"""
import json, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = f"{ROOT}/blocks/event"
os.makedirs(OUT, exist_ok=True)

P = pd.read_csv(f"{ROOT}/data/panel.csv", index_col="date", parse_dates=True)
P.index = P.index.to_period("M")
EV = json.load(open(f"{ROOT}/data/events.json"))
M = lambda s: pd.Period(s, "M")
ONSETS = [M(x) for x in EV["recession_onsets"]]
B1 = [(M(m), d) for m, d in EV["drawdown_starts_B1_running_peak"]]
B2 = [(M(m), d) for m, d in EV["drawdown_starts_B2_local_peak"]]
RES_CUT = M(EV["last_resolved_month_h12"])          # 2025-08: t + h <= RES_CUT is resolved
LAST = P.index.max()                                 # 2026-08
USREC = P["usrec"].astype(int)
DOUBLE_DIP = (M("1981-08"), M("1980-08"), M("1981-07"))
COMMON_START = M("1953-04")
CURVE_START = M("1953-09")     # first curve_flat_gs6m value
DD_START = M("1950-01")
NUM = {}                       # every reported number: name -> {"value","def"}
LINES = []                     # results.md
def W(s=""): LINES.append(s)
def N(key, value, definition):
    if isinstance(value, (np.floating, float)): value = round(float(value), 4)
    elif isinstance(value, (np.integer,)): value = int(value)
    NUM[key] = {"value": value, "def": definition}
    return value
def pct(x): return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100*x:.1f}%"
def resolved(t, h): return t + h <= RES_CUT
def regime(t):
    return "R0" if t <= M("1985-12") else "R1" if t <= M("2008-12") else "R2" if t <= M("2019-12") else "R3"
def table(headers, rows):
    W("| " + " | ".join(headers) + " |"); W("|" + "---|" * len(headers))
    for r in rows: W("| " + " | ".join(str(x) for x in r) + " |")
    W()

# --------------------------------------------------------------------------- definitions
DEFS = {   # name: (column, threshold, tier)
    "D1-RED":    ("oil_12m_pct", 50, "primary"),
    "D1-YELLOW": ("oil_12m_pct", 25, "secondary"),
    "D2":        ("nopi36_sum12", 10, "primary"),
    "D3-RED":    ("real_oil_12m_pct", 50, "primary"),
    "D3-YELLOW": ("real_oil_12m_pct", 25, "secondary"),
    "PPI-RED":   ("ppi_crude_12m_pct", 50, "robustness (pre-1983 companion of D1-RED)"),
    "PPI-D2":    ("ppi_nopi36_sum12", 10, "robustness (pre-1983 companion of D2)"),
}
def on_mask(col, th):
    return (P[col] >= th).fillna(False).astype(bool)
def data_start(col): return P[col].first_valid_index()

# --------------------------------------------------------------------------- episodes
def build_episodes(on, col=None):
    """Maximal sets of ON months with consecutive ON months separated by <= 6 OFF months.
    Membership (on0) = USREC_t == 0 months; raw_first/raw_last include in-recession ON months."""
    idx = list(on[on].index)
    if not idx: return []
    runs, cur = [], [idx[0]]
    for t in idx[1:]:
        if (t - cur[-1]).n - 1 <= 6: cur.append(t)
        else: runs.append(cur); cur = [t]
    runs.append(cur)
    eps = []
    for r in runs:
        on0 = [t for t in r if USREC[t] == 0]
        vals = P.loc[r, col] if col else None
        eps.append(dict(raw_first=r[0], raw_last=r[-1], on_all=r, on0=on0,
                        first0=on0[0] if on0 else None, last0=on0[-1] if on0 else None,
                        n_on=len(r), n_on0=len(on0),
                        peak=(float(vals.max()) if col else None),
                        peak_month=(vals.idxmax() if col else None)))
    return eps

def score_episodes(eps, events, h, wstart, double_dip=None):
    """Attach outcomes. Each event credited to at most one (the earliest) episode."""
    claimed, out = set(), []
    for ep in sorted(eps, key=lambda e: e["raw_first"]):
        if ep["raw_first"] < wstart: continue
        rec = dict(ep); hits = []
        if ep["on0"]:
            for e in events:
                if e in claimed: continue
                on0 = ep["on0"]
                if double_dip and e == double_dip[0]:
                    on0 = [t for t in on0 if double_dip[1] <= t <= double_dip[2]]
                    if not on0: continue
                if on0[0] < e <= on0[-1] + h: hits.append(e)
        coin = [e for e in events if e <= ep["raw_first"] <= e + 3]
        if hits:
            status = "hit"; claimed |= set(hits)
        elif coin: status = "coincident"
        elif not ep["on0"]: status = "in-recession (excluded)"
        elif not resolved(ep["last0"], h): status = "pending"
        else: status = "false positive"
        rec.update(status=status, hits=hits, coincident_with=coin,
                   lead=(int((hits[0] - ep["first0"]).n) if hits else None))
        out.append(rec)
    return out

def score_events(on, events, h, dstart, double_dip=None, scored_eps=None):
    """Per-event: caught / coincident / missed / not evaluable (+ lead from crediting episode)."""
    on0 = on & (USREC == 0)
    out = []
    for e in events:
        if e - h < dstart:
            out.append(dict(event=e, cat="not evaluable", lead=None, last_on=None, first_on=None)); continue
        lo, hi = e - h, e - 1
        if double_dip and e == double_dip[0]:
            lo, hi = max(lo, double_dip[1]), min(hi, double_dip[2])
        win = [t for t in pd.period_range(lo, hi, freq="M") if on0.get(t, False)]
        if win:
            cred = [ep for ep in (scored_eps or []) if e in ep["hits"]]
            first = cred[0]["first0"] if cred else win[0]
            out.append(dict(event=e, cat="caught", lead=int((e - first).n), last_on=int((e - win[-1]).n), first_on=first))
        elif any(ep["status"] == "coincident" and e in ep["coincident_with"] for ep in (scored_eps or [])):
            ep = [ep for ep in scored_eps if ep["status"] == "coincident" and e in ep["coincident_with"]][0]
            out.append(dict(event=e, cat="coincident", lead=-int((ep["raw_first"] - e).n), last_on=None, first_on=ep["raw_first"]))
        else:
            out.append(dict(event=e, cat="missed", lead=None, last_on=None, first_on=None))
    return out

def month_precision(on, events, h, wstart, wend=None, exclude_months=()):
    months = [t for t in P.index if t >= wstart and (wend is None or t <= wend) and USREC[t] == 0 and resolved(t, h)]
    pos = lambda t: any(t < e <= t + h for e in events)
    onm = [t for t in months if on[t] and t not in exclude_months]
    return dict(n_on=len(onm), n_on_pos=sum(pos(t) for t in onm),
                precision=(np.mean([pos(t) for t in onm]) if onm else np.nan),
                n_months=len(months), n_pos=sum(pos(t) for t in months),
                base=np.mean([pos(t) for t in months]))

def fmt(p): return p.strftime("%Y-%m") if p is not None else "—"
def ep_name(ep): return f"{fmt(ep['raw_first'])}..{fmt(ep['raw_last'])}"

# =========================================================================== 1. INSTRUMENT AGREEMENT
W("# BLOCK event — results (spec v1, run 2026-09-15)")
W()
W("Inputs: frozen `panel.csv` (1946-01..2026-08), `events.json`. Oil = FRED WTISPLC monthly spot (D1/D2/D3), "
  "WPU0561 PPI crude as the pre-1983 companion. Curve = GS10−TB3MS (`spread_gs`). Resolved month for horizon h: "
  "t + h ≤ 2025-08. Common NBER window: ON months 1953-04..last resolved; onsets 1953-08..2020-03 (11). "
  "Base rate = share of resolved USREC=0 months in the window with an onset in t+1..t+h.")
W()
W("## 1. Instrument agreement (reported BEFORE any result)")
W()
def grade(v):
    return "red" if v >= 50 else "yellow" if v >= 25 else "benign"
both = P.loc[M("1987-01"):, ["oil_12m_pct", "wti_daily_252_pct"]].dropna()
g_m = both["oil_12m_pct"].map(grade); g_d = both["wti_daily_252_pct"].map(grade)
agree3 = (g_m == g_d).mean(); agree_on = ((g_m == "red") == (g_d == "red")).mean()
live_red_panel_not = both[(g_d == "red") & (g_m != "red")]
panel_red_live_not = both[(g_m == "red") & (g_d != "red")]
N("ia_d1_months", len(both), "month-ends 1987-01..2026-08 with both oil_12m_pct and wti_daily_252_pct")
N("ia_d1_grade_agreement", agree3, "share of month-ends where 3-level D1 grade (benign/yellow/red at 25/50) agrees, monthly-mean vs daily 252-obs point")
N("ia_d1_onoff_agreement", agree_on, "share of month-ends where ON(=RED) agrees, monthly-mean vs daily point construction")
N("ia_d1_live_red_panel_not", len(live_red_panel_not), "months daily-point RED but monthly-mean not RED")
N("ia_d1_panel_red_live_not", len(panel_red_live_not), "months monthly-mean RED but daily-point not RED")
W("### 1(i) D1 grade: monthly-mean `oil_12m_pct` vs deployed point construction `wti_daily_252_pct`, month-ends 1987-01..2026-08")
W()
W(f"- months compared: {len(both)}; 3-level grade agreement {pct(agree3)}; ON/OFF (ON = RED) agreement **{pct(agree_on)}** "
  f"(disagreements: {len(live_red_panel_not)} live-RED/panel-not, {len(panel_red_live_not)} panel-RED/live-not).")
verdict = "≥ 90% → the monthly-mean construction STANDS for the overlap (spec §4 D1 clause not triggered)." if agree_on >= 0.90 else \
          "< 90% → per spec §4 the daily construction REPLACES the monthly one for the overlap — APPLIED below."
W(f"- Verdict: {verdict}")
N("ia_d1_replace_monthly_with_daily", bool(agree_on < 0.90), "True iff the spec's <90% ON/OFF agreement clause triggers")
W()
rows = [(fmt(t), f"{r.wti_daily_252_pct:.1f}", g_d[t], f"{r.oil_12m_pct:.1f}", g_m[t]) for t, r in live_red_panel_not.iterrows()]
W("Live-RED / panel-not-RED months:"); W()
table(["month", "daily 252-obs %", "grade", "monthly-mean 12m %", "grade"], rows)
rows = [(fmt(t), f"{r.wti_daily_252_pct:.1f}", g_d[t], f"{r.oil_12m_pct:.1f}", g_m[t]) for t, r in panel_red_live_not.iterrows()]
W("Panel-RED / live-not-RED months:"); W()
table(["month", "daily 252-obs %", "grade", "monthly-mean 12m %", "grade"], rows)
dis3 = both[(g_m != g_d)]
W(f"All 3-level grade disagreements ({len(dis3)} months): " + ", ".join(f"{fmt(t)} (live {g_d[t]}/panel {g_m[t]})" for t in dis3.index))
W()
NUM["ia_d1_grade_disagreement_months"] = {"value": [fmt(t) for t in dis3.index], "def": "month-ends where 3-level D1 grade differs (live vs panel)"}

# (ii) curve flat: monthly gs 6m-min vs daily 183-day min, 1982-01+
cf = P.loc[M("1982-01"):, ["curve_flat_gs6m", "curve_flat_daily183"]].dropna()
cf_m = cf["curve_flat_gs6m"].astype(str).str.lower().eq("true"); cf_d = cf["curve_flat_daily183"].astype(float) == 1.0
agree_cf = (cf_m == cf_d).mean(); dis_cf = cf[cf_m != cf_d]
N("ia_curve_months", len(cf), "months 1982-01..2026-08 with both curve_flat_gs6m and curve_flat_daily183")
N("ia_curve_agreement", agree_cf, "share of months where curve_flat_gs6m (min spread_gs over 6 months < 0.25) == curve_flat_daily183 (deployed: min daily 3m10y over 183 days < 0.25)")
W("### 1(ii) Curve flat: `curve_flat_gs6m` (monthly, GS10−TB3MS) vs `curve_flat_daily183` (deployed daily rule), 1982-01..2026-08")
W()
W(f"- months compared: {len(cf)}; agreement **{pct(agree_cf)}**; disagreements {len(dis_cf)} "
  f"({int((cf_d & ~cf_m).sum())} daily-flat/monthly-not, {int((cf_m & ~cf_d).sum())} monthly-flat/daily-not).")
W("- Named disagreement months: " + ", ".join(f"{fmt(t)} ({'daily' if cf_d[t] else 'monthly'} flat only)" for t in dis_cf.index))
W()
NUM["ia_curve_disagreement_months"] = {"value": [f"{fmt(t)}:{'daily-only' if cf_d[t] else 'monthly-only'}" for t in dis_cf.index], "def": "months where the two curve-flat rules disagree"}

# (iii) spread_cmt vs spread_gs 6-month-min flat condition
flat_cmt = (P["spread_cmt"].rolling(6, min_periods=6).min() < 0.25)
flat_gs = P["spread_gs"].rolling(6, min_periods=6).min() < 0.25
ok = P["spread_cmt"].rolling(6, min_periods=6).min().notna()
cmp = pd.DataFrame({"cmt": flat_cmt[ok], "gs": flat_gs[ok]})
dis_c = cmp[cmp.cmt != cmp.gs]
N("ia_cmt_months", len(cmp), "months (1982-06..2026-08) with a 6-month min of spread_cmt available")
N("ia_cmt_agreement", (cmp.cmt == cmp.gs).mean(), "share of months where flat condition (6m min < 0.25) agrees between T10Y3M (CMT, monthly mean) and GS10−TB3MS")
N("ia_cmt_disagreements", len(dis_c), "count of disagreement months, CMT-flat-only + GS-flat-only")
W("### 1(iii) Flat condition (6-month min < 0.25) on `spread_cmt` (T10Y3M, CMT) vs `spread_gs` (GS10−TB3MS), 1982-06..2026-08")
W()
W(f"- months compared: {len(cmp)}; agreement {pct((cmp.cmt == cmp.gs).mean())}; **{len(dis_c)} disagreement months** "
  f"({int((cmp.cmt & ~cmp.gs).sum())} CMT-flat only, {int((cmp.gs & ~cmp.cmt).sum())} GS-flat only).")
W("- Named: " + ", ".join(f"{fmt(t)} ({'CMT' if r.cmt else 'GS'} flat only)" for t, r in dis_c.iterrows()))
W(f"- The spec's data audit counted 17; this recount on the frozen panel (6-month min requires 6 CMT months, so 1982-01..05 are not comparable) finds {len(dis_c)}. Every disagreement is CMT-flat-only, consistent with CMT − (GS10−TB3MS) averaging −0.12pp. 2026-04 is one of them: the CMT basis and the deployed daily rule (§1(ii)) both read the curve as flat in 2026-04; the fit basis `spread_gs` does not.")
W()
NUM["ia_cmt_disagreement_months"] = {"value": [f"{fmt(t)}:{'CMT-only' if r.cmt else 'GS-only'}" for t, r in dis_c.iterrows()], "def": "months where CMT and GS flat conditions disagree"}

# =========================================================================== 2. EXPECTED EPISODE LISTS
W("## 2. Expected episode lists (pre-outcome record; §4 episode rule)")
W()
W("Rule: ON months; consecutive ON months separated by ≤ 6 OFF months form one episode; membership = USREC_t = 0 months "
  "(in-recession ON months are listed in the span but excluded from n and from every numerator/denominator). "
  "`start` = first ON month with USREC=0; `raw span` includes in-recession ON months; peak = max reading over the whole span.")
W()
ON, EPS = {}, {}
for name, (col, th, tier) in DEFS.items():
    ON[name] = on_mask(col, th)
    EPS[name] = build_episodes(ON[name], col)
    W(f"### {name} — `{col}` ≥ {th} ({tier}); series starts {fmt(data_start(col))}")
    W()
    rows = []
    for ep in EPS[name]:
        rows.append((fmt(ep["first0"]), fmt(ep["last0"]), ep["n_on0"], ep_name(ep), ep["n_on"], f"{ep['peak']:.1f}", fmt(ep["peak_month"]),
                     regime(ep["raw_first"])))
    table(["start (USREC=0)", "end (USREC=0)", "n ON (USREC=0)", "raw span (all ON)", "n ON (all)", "peak", "peak month", "regime"], rows)
    NUM[f"episodes_{name}"] = {"value": [dict(start=fmt(e["first0"]), end=fmt(e["last0"]), n_on0=e["n_on0"], raw_span=ep_name(e), n_on=e["n_on"], peak=round(e["peak"], 2), peak_month=fmt(e["peak_month"])) for e in EPS[name]],
                                "def": f"{name}: {col} >= {th}; episode rule §4"}

# =========================================================================== 3. OUTCOMES vs NBER
W("## 3. Outcomes vs NBER onsets (h = 12 headline, h = 18 second)")
W()
W("Common window: ON months 1953-04..last resolved (h=12: 2024-08; h=18: 2024-02), USREC_t=0; onsets 1953-08..2020-03 (11). "
  "1953-08 IS evaluable for every oil-alone rule (series start 1947-01/1948-01/1949-12 ≤ 1953-08 − 18). "
  "Hit = an event in (first ON, last ON + h]; coincident = raw first ON in [onset, onset+3]; 1981-08 scored only against ON months 1980-08..1981-07; "
  "PENDING = episode contains an unresolved month. Month-level precision = share of ON months (USREC=0, resolved) with an onset in t+1..t+h. "
  "Lead = months from the crediting episode's first ON month to the event; a NEGATIVE lead on a coincident row = months AFTER the onset that the rule first fired.")
W()
COMMON_ONSETS = [e for e in ONSETS if e >= M("1953-08")]
SCORED, EVENTS_SC, PREC = {}, {}, {}
STAT_ORDER = ["hit", "false positive", "coincident", "pending", "in-recession (excluded)"]
for h in (12, 18):
    W(f"### 3.{1 if h == 12 else 2} h = {h}")
    W()
    for name, (col, th, tier) in DEFS.items():
        se = score_episodes(EPS[name], ONSETS, h, COMMON_START, DOUBLE_DIP)
        ev = score_events(ON[name], COMMON_ONSETS, h, data_start(col), DOUBLE_DIP, se)
        pr = month_precision(ON[name], ONSETS, h, COMMON_START)
        coin_months = set(t for ep in se if ep["status"] == "coincident" for t in ep["on0"])
        pr_x = month_precision(ON[name], ONSETS, h, COMMON_START, exclude_months=coin_months)
        SCORED[(name, h)], EVENTS_SC[(name, h)], PREC[(name, h)] = se, ev, pr
        hits = [e for e in se if e["status"] == "hit"]; fps = [e for e in se if e["status"] == "false positive"]
        coin = [e for e in se if e["status"] == "coincident"]; pend = [e for e in se if e["status"] == "pending"]
        inrec = [e for e in se if e["status"] == "in-recession (excluded)"]
        n_eval = sum(1 for x in ev if x["cat"] != "not evaluable"); n_caught = sum(1 for x in ev if x["cat"] == "caught")
        scoreable = len(hits) + len(fps)
        W(f"**{name}** (h={h}): episodes in window {len(se)} = {len(hits)} hit, {len(fps)} false positive, {len(coin)} coincident, "
          f"{len(pend)} pending, {len(inrec)} in-recession-only; episode precision hits/(hits+FP) = {len(hits)}/{scoreable} = {pct(len(hits)/scoreable if scoreable else np.nan)}; "
          f"recall {n_caught}/{n_eval}; month-level precision {pr['n_on_pos']}/{pr['n_on']} = {pct(pr['precision'])} vs base {pr['n_pos']}/{pr['n_months']} = {pct(pr['base'])} "
          f"(excluding coincident-episode months: {pr_x['n_on_pos']}/{pr_x['n_on']} = {pct(pr_x['precision'])}).")
        W()
        rows = [(fmt(ep["first0"]) if ep["first0"] else f"({fmt(ep['raw_first'])} in-recession)", ep_name(ep), ep["n_on0"], f"{ep['peak']:.1f}", ep["status"].upper(),
                 ", ".join(fmt(e) for e in ep["hits"]) or ("coincident with " + ", ".join(fmt(e) for e in ep["coincident_with"]) if ep["coincident_with"] else "—"),
                 (f"{ep['lead']}" if ep["lead"] is not None else "—")) for ep in se]
        table(["episode start", "raw span", "n ON (USREC=0)", "peak", "outcome", "event(s) credited / coincident with", "lead first-ON→event (m)"], rows)
        rows = [(fmt(x["event"]), x["cat"].upper(), (x["lead"] if x["lead"] is not None else "—"), (x["last_on"] if x["last_on"] is not None else "—"), fmt(x["first_on"]) if x["first_on"] else "—") for x in ev]
        table(["onset", "per-event", "lead from first ON (m)", "months from last ON before event", "crediting first ON"], rows)
        pre = f"{name}_h{h}"
        N(f"{pre}_episodes", len(se), f"{name} episodes with raw first ON ≥ 1953-04, scored vs NBER onsets at h={h}")
        N(f"{pre}_hits", len(hits), "episodes crediting ≥1 onset"); N(f"{pre}_false_positives", len(fps), "resolved episodes crediting no onset and not coincident")
        N(f"{pre}_coincident", len(coin), "episodes whose raw first ON is in [onset, onset+3]"); N(f"{pre}_pending", len(pend), "episodes containing an unresolved month")
        N(f"{pre}_episode_precision", (len(hits) / scoreable if scoreable else None), "hits / (hits + false positives)")
        N(f"{pre}_recall_caught", n_caught, "onsets 1953-08..2020-03 with an ON (USREC=0) month in [e−h, e−1] (1981-08: 1980-08..1981-07)")
        N(f"{pre}_recall_evaluable", n_eval, "evaluable onsets in the common window")
        N(f"{pre}_month_precision", pr["precision"], "share of ON months (USREC=0, resolved, 1953-04+) followed by an onset within h")
        N(f"{pre}_month_precision_n_on", pr["n_on"], "ON months in the precision denominator")
        N(f"{pre}_month_precision_excl_coincident", pr_x["precision"], "same, excluding months belonging to coincident episodes")
        N(f"{pre}_base_rate", pr["base"], "share of resolved USREC=0 months 1953-04+ with an onset in t+1..t+h")
        NUM[f"{pre}_false_positive_names"] = {"value": [fmt(e["first0"]) for e in fps], "def": "first ON month of each false-positive episode"}
        NUM[f"{pre}_hit_names"] = {"value": [f"{fmt(e['first0'])}→{','.join(fmt(x) for x in e['hits'])}" for e in hits], "def": "hit episodes and the onsets they credit"}
        NUM[f"{pre}_coincident_names"] = {"value": [f"{fmt(e['raw_first'])}~{','.join(fmt(x) for x in e['coincident_with'])}" for e in coin], "def": "coincident episodes (raw first ON ~ onset)"}
        NUM[f"{pre}_pending_names"] = {"value": [fmt(e["first0"]) for e in pend], "def": "pending episodes"}
        NUM[f"{pre}_event_categories"] = {"value": {fmt(x["event"]): x["cat"] for x in ev}, "def": "per-onset category"}
        NUM[f"{pre}_event_leads"] = {"value": {fmt(x["event"]): x["lead"] for x in ev}, "def": "lead in months from the crediting episode's first ON month to the onset (negative = coincident, months after onset)"}
    N(f"base_rate_common_h{h}", PREC[("D1-RED", h)]["base"], f"base rate, common window, h={h}")
    N(f"base_rate_common_h{h}_n_months", PREC[("D1-RED", h)]["n_months"], "resolved USREC=0 months in the common window")

# summary table
W("### 3.3 Summary — per definition, per horizon (common window)")
W()
rows = []
for h in (12, 18):
    for name in DEFS:
        se, ev, pr = SCORED[(name, h)], EVENTS_SC[(name, h)], PREC[(name, h)]
        hits = sum(e["status"] == "hit" for e in se); fps = sum(e["status"] == "false positive" for e in se)
        rows.append((h, name, f"{pr['n_on_pos']}/{pr['n_on']} = {pct(pr['precision'])}", pct(pr["base"]), f"{hits}/{hits+fps}" + (f" = {pct(hits/(hits+fps))}" if hits + fps else ""),
                     f"{sum(x['cat']=='caught' for x in ev)}/{sum(x['cat']!='not evaluable' for x in ev)}",
                     ", ".join(fmt(e["first0"]) for e in se if e["status"] == "false positive") or "—",
                     ", ".join(fmt(e["raw_first"]) for e in se if e["status"] == "coincident") or "—",
                     ", ".join(fmt(e["first0"]) for e in se if e["status"] == "pending") or "—"))
table(["h", "definition", "month precision", "base", "episode hits/(hits+FP)", "recall", "false positives (first ON)", "coincident (raw first ON)", "pending"], rows)

# Q1 PRIMARY headline
se, ev, pr = SCORED[("D1-RED", 12)], EVENTS_SC[("D1-RED", 12)], PREC[("D1-RED", 12)]
q1_hits = sum(e["status"] == "hit" for e in se); q1_fp = sum(e["status"] == "false positive" for e in se)
W(f"**Q1 PRIMARY (D1-RED, h = 12, NBER onsets, episode level, common window): {q1_hits} hits of {q1_hits+q1_fp} scoreable episodes = "
  f"{pct(q1_hits/(q1_hits+q1_fp))}; recall {sum(x['cat']=='caught' for x in ev)}/{sum(x['cat']!='not evaluable' for x in ev)}; "
  f"month-level precision {pct(pr['precision'])} vs base {pct(pr['base'])}.**")
W()
N("Q1_primary_episode_precision", q1_hits / (q1_hits + q1_fp), "D1-RED h=12 NBER episode precision = hits/(hits+FP), common window")
N("Q1_primary_hits", q1_hits, "D1-RED h=12 hit episodes"); N("Q1_primary_false_positives", q1_fp, "D1-RED h=12 false-positive episodes")
N("Q1_primary_recall", f"{sum(x['cat']=='caught' for x in ev)}/{sum(x['cat']!='not evaluable' for x in ev)}", "D1-RED h=12 onsets caught / evaluable, 1953-08..2020-03")
N("Q1_primary_month_precision", pr["precision"], "D1-RED h=12 month-level precision"); N("Q1_primary_base_rate", pr["base"], "h=12 base rate, common window")
W("Reading notes (rule artifacts, stated so nobody over-reads the D2 row):")
W()
W("- D2's 2008-01 credit comes from the single 54-month 2004-05..2009-04 episode (NOPI12 never fell below 10 for more than 6 months in 2004–08): lead from first ON = 44 months; the last ON month before the onset was 2007-12. D2's 2020-03 credit rests on ON at exactly e−12 (2019-03, the last month of the 2018-04 episode) and the event is the COVID shock. D2's 1981-08 credit uses the double-dip window (ON 1980-08..1981-01). Descriptively (NOT a spec statistic): without those three credits D2 would be 3 hits / 5 FP (2004-05 and 2018-04 become false positives), recall 3/11 — the same recall as D1-RED — i.e. the D2-over-D1 margin is carried by the long-episode and edge credits the §4 rule allows.")
W("- D1-YELLOW at h=18: the 2004-04..2006-07 episode (23 ON months) reaches 2008-01 (last ON + 18 = 2008-01) and, being the earliest, takes the credit; the 2007-09 episode that actually preceded the onset is then a false positive. Per-event recall is unaffected.")
W("- D1-RED's 2001-04 credit: first ON 1999-08, last ON before onset 2000-06 (10 months); its 2008-01 credit is a single ON month, 2007-11 (2007-12 read +47.9, yellow).")
W("- 1973-12: D1/D3 first ON 1974-01 (coincident, as pre-declared) — but D2 (NOPI12) fired 1973-08 on the WTISPLC posted-price step 3.56→4.31 (+19 log-pct) and PPI-D2 fired 1973-09, so under the NOPI definition 1973-12 is CAUGHT with a 4-month (3-month) lead, NOT coincident. The pre-declared 'every definition' expectation fails for D2. On WPU0561 the 1973-12 print (+27.5%) is YELLOW, not RED, so PPI-RED's first ON is 1974-01, same as WTISPLC.")
W()

# §5 comparison rows: D2 vs D1 on episode precision / recall (h=12)
def ep_stats(name, h):
    se, ev = SCORED[(name, h)], EVENTS_SC[(name, h)]
    hits = sum(e["status"] == "hit" for e in se); fps = sum(e["status"] == "false positive" for e in se)
    return hits, fps, sum(x["cat"] == "caught" for x in ev), sum(x["cat"] != "not evaluable" for x in ev)
d1, d2, d3 = ep_stats("D1-RED", 12), ep_stats("D2", 12), ep_stats("D3-RED", 12)
W("§5 trigger rows (h = 12, NBER, common window; 'D2 beats D1 on episode precision by ≥ 1 episode with equal-or-better recall'):")
W()
table(["definition", "hits", "false positives", "recall"], [("D1-RED", d1[0], d1[1], f"{d1[2]}/{d1[3]}"), ("D2 (NOPI12 ≥ 10)", d2[0], d2[1], f"{d2[2]}/{d2[3]}"), ("D3-RED", d3[0], d3[1], f"{d3[2]}/{d3[3]}")])
d2_better = (d2[1] <= d1[1] - 1 or d2[0] >= d1[0] + 1) and d2[2] >= d1[2]
W(f"- D2 vs D1: precision {d2[0]}/{d2[0]+d2[1]} vs {d1[0]}/{d1[0]+d1[1]}, recall {d2[2]} vs {d1[2]} → "
  f"{'D2 better on both (row candidate — the §5 NOPI12 trigger-leg row applies)' if d2_better else 'mixed/tie → no change'}. "
  "Interpretation of 'by ≥ 1 episode': ≥ 1 more hit OR ≥ 1 fewer false positive, with recall ≥ D1's.")
d3_better = (d3[0] / max(d3[0] + d3[1], 1) > max(d1[0] / max(d1[0] + d1[1], 1), d2[0] / max(d2[0] + d2[1], 1))) and d3[2] >= max(d1[2], d2[2])
W(f"- D3 vs D1 and D2: {'D3 beats both with ≥ recall' if d3_better else 'D3 does NOT beat both on precision with ≥ recall → no real-oil leg'}.")
W()
N("s5_D2_beats_D1", bool(d2_better), "D2 better than D1 by ≥1 episode on precision with ≥ recall (h=12 NBER common window)")
N("s5_D3_beats_D1_D2", bool(d3_better), "D3 beats D1 and D2 on episode precision with ≥ recall")

# secondary full-window row (1947-01+, 12 onsets incl 1948-12)
W("### 3.4 Secondary full-window row (ON months 1947-01+, onsets 1948-12..2020-03; evaluability by each series' own start)")
W()
rows = []
for h in (12, 18):
    for name, (col, th, tier) in DEFS.items():
        se = score_episodes(EPS[name], ONSETS, h, M("1947-01"), DOUBLE_DIP)
        ev = score_events(ON[name], ONSETS, h, data_start(col), DOUBLE_DIP, se)
        pr = month_precision(ON[name], ONSETS, h, M("1947-01"))
        hits = sum(e["status"] == "hit" for e in se); fps = sum(e["status"] == "false positive" for e in se)
        ne = [fmt(x["event"]) for x in ev if x["cat"] == "not evaluable"]
        rows.append((h, name, f"{pr['n_on_pos']}/{pr['n_on']} = {pct(pr['precision'])}", pct(pr["base"]), f"{hits}/{hits+fps}",
                     f"{sum(x['cat']=='caught' for x in ev)}/{sum(x['cat']!='not evaluable' for x in ev)}", ", ".join(ne) or "—",
                     {x["event"]: x["cat"] for x in ev}[M("1948-12")]))
        N(f"full_{name}_h{h}_month_precision", pr["precision"], "full window 1947-01+ month precision"); N(f"full_{name}_h{h}_base", pr["base"], "full window base rate")
        N(f"full_{name}_h{h}_hits_fp", f"{hits}/{fps}", "full window episode hits / false positives")
        N(f"full_{name}_h{h}_recall", f"{sum(x['cat']=='caught' for x in ev)}/{sum(x['cat']!='not evaluable' for x in ev)}", "full window recall")
table(["h", "definition", "month precision", "base", "episode hits/(hits+FP)", "recall", "not evaluable onsets", "1948-12"], rows)

# =========================================================================== 4. KILL-RATE RECOUNT
W("## 4. Kill-rate recount (common window, WTISPLC; h = 12 for 'preceded')")
W()
rows = []
for name in DEFS:
    se, ev = SCORED[(name, 12)], EVENTS_SC[(name, 12)]
    n = sum(x["cat"] == "caught" for x in ev); m = sum(x["cat"] != "not evaluable" for x in ev)
    fps = [fmt(e["first0"]) for e in se if e["status"] == "false positive"]; coin = [fmt(e["raw_first"]) for e in se if e["status"] == "coincident"]
    txt = f"{n} of {m} postwar onsets (1953-08..2020-03) preceded, {len(fps)} named false positives ({', '.join(fps)}), {len(coin)} coincident ({', '.join(coin) or '—'})"
    rows.append((name, txt))
    N(f"kill_rate_{name}", txt, "measured kill_rate string, ON in [e−12, e−1], common window")
table(["definition", "measured kill_rate (replaces 'preceded ~10 of 11 postwar recessions')"], rows)
W("Hamilton's '10 of 11' is a narrative count (his own 1983/2011 dating of oil-price events); it is NOT reproducible from this instrument on any definition — see the "
  "per-event tables above. The recount is what `pins.py` `kill_rate` must say per §5.")
W()
# PPI robustness rows, pre-1983 onsets
W("### 4.1 PPI (WPU0561) robustness rows for pre-1983 onsets — WTISPLC rule / PPI companion, h = 12")
W()
pre83 = [e for e in COMMON_ONSETS if e < M("1983-01")]
for a, b in (("D1-RED", "PPI-RED"), ("D2", "PPI-D2")):
    rows = []
    for e in pre83:
        xa = [x for x in EVENTS_SC[(a, 12)] if x["event"] == e][0]; xb = [x for x in EVENTS_SC[(b, 12)] if x["event"] == e][0]
        lab = lambda x: {"caught": "hit", "missed": "miss", "coincident": "coincident", "not evaluable": "n/e"}[x["cat"]]
        rows.append((fmt(e), f"{lab(xa)}/{lab(xb)}", fmt(xa["first_on"]) if xa["first_on"] else "—", fmt(xb["first_on"]) if xb["first_on"] else "—",
                     xa["lead"] if xa["lead"] is not None else "—", xb["lead"] if xb["lead"] is not None else "—"))
        N(f"ppi_row_{a}_vs_{b}_{fmt(e)}", f"{lab(xa)}/{lab(xb)}", f"{a} / {b} per-event outcome for onset {fmt(e)}, h=12; first ON months {fmt(xa['first_on'])} / {fmt(xb['first_on'])}")
    W(f"**{a} / {b}**"); W()
    table(["onset", "WTISPLC / PPI", "first ON (WTISPLC rule)", "first ON (PPI rule)", "lead WTISPLC (m)", "lead PPI (m)"], rows)
# pre-declared expectations
W("### 4.2 Pre-declared expectations — checked")
W()
def cat_of(name, h, e): return [x for x in EVENTS_SC[(name, h)] if x["event"] == e][0]
def first_on_raw(name, e_lo, e_hi):
    c = [ep for ep in EPS[name] if e_lo <= ep["raw_first"] <= e_hi]; return fmt(c[0]["raw_first"]) if c else "—"
rows = []
for name in ("D1-RED", "D2", "D3-RED", "PPI-RED", "PPI-D2"):
    x = cat_of(name, 12, M("1973-12"))
    rows.append(("1973-12 coincident/missed", name, x["cat"].upper(), first_on_raw(name, M("1973-01"), M("1974-06")),
                 "as pre-declared" if x["cat"] in ("coincident", "missed") else "**NOT as pre-declared — caught with a lead**"))
    N(f"expect_1973_{name}", x["cat"], f"1973-12 per-event outcome under {name}, h=12 (pre-declared: coincident/missed)")
for name in ("D1-RED", "D2", "D3-RED", "PPI-RED", "PPI-D2"):
    x = cat_of(name, 12, M("1990-08"))
    rows.append(("1990-08 coincident", name, x["cat"].upper(), first_on_raw(name, M("1990-01"), M("1990-12")), "as pre-declared" if x["cat"] == "coincident" else "**NOT as pre-declared**"))
    N(f"expect_1990_{name}", x["cat"], f"1990-08 per-event outcome under {name}, h=12 (pre-declared: coincident)")
for name in ("D1-RED", "D2", "D3-RED"):
    for h in (12, 18):
        eps22 = [ep for ep in SCORED[(name, h)] if M("2021-01") <= ep["raw_first"] <= M("2022-12")]
        st = eps22[0]["status"] if eps22 else "no episode"
        rows.append((f"2022 false positive (h={h})", name, st.upper(), fmt(eps22[0]["first0"]) if eps22 else "—", "as pre-declared" if st == "false positive" else "**NOT as pre-declared**"))
        N(f"expect_2022_{name}_h{h}", st, f"status of the 2021-22 {name} episode at h={h} (pre-declared: false positive)")
table(["expectation", "definition", "measured", "first ON (raw)", "verdict"], rows)

# =========================================================================== 5. CURVE-CONDITIONED
W("## 5. Curve-conditioned rules (1957-09 onward, 10 onsets; ON months 1953-09..last resolved) — oil isolated from the policy channel")
W()
W("This is the first time the canary's oil signal is scored ALONE and beside the curve, instead of inside the bundled oil-OR-policy window of "
  "`studies/pin-rule-hindcast.md` v3 (deployed accident gauge: fast-red+curve 34% / 4 of 13; oil-or-policy window + curve 45% / 5 of 6 on drawdowns, 37% / 4 of 4 on onsets). "
  "Curve flat = min `spread_gs` over the trailing 6 months < 0.25. 1953-08 is NOT TESTABLE for curve rules (4 months of curve history) and is excluded from every denominator here; "
  "for like-for-like the oil-alone rows in this section use the same 1953-09+ window and the same 10 onsets. Drawdown events: B1 running-peak (headline), B2 local-peak (second); "
  "same episode rule, same USREC=0 filter, same coincident/pending rules; no double-dip rule applies to drawdowns. Recall evaluability uses the rule's data start (curve rules 1953-09).")
W()
curve = P["curve_flat_gs6m"].astype(str).str.lower().eq("true")
RULES5 = {
    "curve flat alone": curve,
    "D1-RED alone": ON["D1-RED"], "D1-RED AND curve flat": ON["D1-RED"] & curve,
    "D2 alone": ON["D2"], "D2 AND curve flat": ON["D2"] & curve,
    "D3-RED alone": ON["D3-RED"], "D3-RED AND curve flat": ON["D3-RED"] & curve,
}
RULE_START = {k: (CURVE_START if "curve" in k else data_start(DEFS[k.split(" ")[0]][0])) for k in RULES5}
CURVE_ONSETS = [e for e in ONSETS if e >= M("1957-09")]
EVSETS = {"NBER onsets": (CURVE_ONSETS, DOUBLE_DIP), "B1 drawdown starts": ([m for m, _ in B1], None), "B2 drawdown starts": ([m for m, _ in B2], None)}
EPS5 = {k: build_episodes(v, None) for k, v in RULES5.items()}
for k in EPS5:
    col = None if k == "curve flat alone" else DEFS[k.split(" ")[0]][0]
    for ep in EPS5[k]:
        if col: ep["peak"] = float(P.loc[ep["on_all"], col].max()); ep["peak_month"] = P.loc[ep["on_all"], col].idxmax()
SC5 = {}
for evname, (events, dd) in EVSETS.items():
    W(f"### 5.{list(EVSETS).index(evname)+1} vs {evname} ({len(events)} events: {', '.join(fmt(e) for e in events)})")
    W()
    rows = []
    for h in (12, 18):
        for k, on in RULES5.items():
            se = score_episodes(EPS5[k], events, h, CURVE_START, dd)
            ev = score_events(on, events, h, max(RULE_START[k], CURVE_START), dd, se)
            pr = month_precision(on, events, h, CURVE_START)
            SC5[(evname, k, h)] = (se, ev, pr)
            hits = [e for e in se if e["status"] == "hit"]; fps = [e for e in se if e["status"] == "false positive"]
            coin = [e for e in se if e["status"] == "coincident"]; pend = [e for e in se if e["status"] == "pending"]
            nc = sum(x["cat"] == "caught" for x in ev); ne = sum(x["cat"] != "not evaluable" for x in ev)
            rows.append((h, k, f"{pr['n_on_pos']}/{pr['n_on']} = {pct(pr['precision'])}", pct(pr["base"]), f"{len(hits)}/{len(hits)+len(fps)}" + (f" = {pct(len(hits)/(len(hits)+len(fps)))}" if hits or fps else ""),
                         f"{nc}/{ne}", ", ".join(fmt(x["event"]) for x in ev if x["cat"] == "caught") or "—",
                         ", ".join(fmt(e["first0"]) for e in fps) or "—", ", ".join(fmt(e["raw_first"]) for e in coin) or "—", ", ".join(fmt(e["first0"]) for e in pend) or "—"))
            key = f"curve5_{evname.split()[0]}_{k.replace(' ', '_')}_h{h}"
            N(f"{key}_month_precision", pr["precision"], f"{k} vs {evname}, h={h}: month-level precision (ON, USREC=0, resolved, 1953-09+)")
            N(f"{key}_base", pr["base"], f"base rate vs {evname}, h={h}, 1953-09+")
            N(f"{key}_hits", len(hits), "hit episodes"); N(f"{key}_false_positives", len(fps), "false-positive episodes")
            N(f"{key}_recall", f"{nc}/{ne}", "events caught / evaluable")
            NUM[f"{key}_false_positive_names"] = {"value": [fmt(e["first0"]) for e in fps], "def": "false-positive episode first ON months"}
            NUM[f"{key}_caught_events"] = {"value": [fmt(x["event"]) for x in ev if x["cat"] == "caught"], "def": "events caught"}
    table(["h", "rule", "month precision", "base", "episode hits/(hits+FP)", "recall", "events caught", "false positives (first ON)", "coincident", "pending"], rows)
def _r(ev, k, h):
    se, evs, pr = SC5[(ev, k, h)]; hits = sum(e["status"] == "hit" for e in se); fps = sum(e["status"] == "false positive" for e in se)
    return f"{k}: month precision {pct(pr['precision'])} (base {pct(pr['base'])}), episodes {hits}/{hits+fps}, recall {sum(x['cat']=='caught' for x in evs)}/{sum(x['cat']!='not evaluable' for x in evs)}"
W("Read-out (h = 12):")
W()
for ev in ("NBER onsets", "B1 drawdown starts"):
    W(f"- vs {ev}: " + "; ".join(_r(ev, k, 12) for k in ("curve flat alone", "D1-RED alone", "D1-RED AND curve flat", "D2 alone", "D2 AND curve flat")) + ".")
W("- On NBER onsets oil alone (D1-RED) is indistinguishable from the base rate at month level (18.4% vs 16.2%) and catches 3 of 10; the curve alone catches 10 of 10 at 55% month precision. Requiring oil AND curve leaves 7 ON months, 2 episodes, both hits (1979-08→1980-02, 2007-11→2008-01) — precision 100% on a recall of 2/10, i.e. oil removes 8 of the curve's 10 catches and adds no episode the curve did not already have. D2 AND curve: 5/6 episodes, 6/10 recall, 69% month precision — better than D2 alone but still strictly inside the curve's own catch set.")
W("- On S&P drawdowns oil alone does BETTER than on recessions: D1-RED alone 51% month precision vs 23% base, 5/9 episodes (1980-11, 1987-08, 2000-08, 2018-09, 2021-12), and the four D1 false positives on drawdowns (2002-12, 2004-09, 2009-12, 2017-01) are also NBER false positives. That is the oil-shock/equity-drawdown link the pin board's 3–12m damage window is about, not a recession link.")
W("- Against the deployed bundled numbers (oil-OR-policy window + curve: 45% / 5-of-6 on drawdowns, 37% / 4-of-4 on onsets; fast-red + curve 34% / 4-of-13): the isolated oil+curve leg is 1/1 (42.9% month) on B1 drawdowns and 2/2 (100% month) on onsets with recall 1/15 and 2/10. The bundled rule's hits were therefore coming mostly from the policy leg and the curve, not from oil; §5 'Always' row (split oil-alone / policy-alone in pin_rule_hindcast) is confirmed as necessary.")
W()
W("Comparison to the deployed accident gauge: the bundled oil-OR-policy+curve rule reported 45% / 5-of-6 on drawdowns and 37% / 4-of-4 on onsets. "
  "Oil-alone and oil-AND-curve numbers above are the isolated equivalents; where 'D1-RED AND curve flat' has fewer hits than 'curve flat alone', "
  "the oil leg is REMOVING recall from the curve rather than adding precision — see the rows.")
W()

# =========================================================================== 6. REGIME BREAKDOWN
W("## 6. Regime breakdown by SIGNAL month (R0 1947–1985, R1 1986–2008, R2 2009–2019, R3 2020+); NBER onsets, common window")
W()
for h in (12, 18):
    W(f"### 6.{1 if h == 12 else 2} h = {h}")
    W()
    rows = []
    months = [t for t in P.index if t >= COMMON_START and USREC[t] == 0 and resolved(t, h)]
    pos = lambda t: any(t < e <= t + h for e in ONSETS)
    for R in ("R0", "R1", "R2", "R3"):
        rm = [t for t in months if regime(t) == R]
        base = np.mean([pos(t) for t in rm]) if rm else np.nan
        N(f"regime_{R}_h{h}_base", base, f"base rate in {R} (resolved USREC=0 months, 1953-04+)"); N(f"regime_{R}_h{h}_n_months", len(rm), f"resolved USREC=0 months in {R}")
        for name in ("D1-RED", "D2", "D3-RED", "D1-YELLOW", "D3-YELLOW"):
            se = [ep for ep in SCORED[(name, h)] if regime(ep["raw_first"]) == R]
            onm = [t for t in rm if ON[name][t]]
            prec = np.mean([pos(t) for t in onm]) if onm else np.nan
            hits = [e for e in se if e["status"] == "hit"]; fps = [e for e in se if e["status"] == "false positive"]
            coin = [e for e in se if e["status"] == "coincident"]; pend = [e for e in se if e["status"] == "pending"]
            if R == "R3":
                rows.append((R, name, len(onm), len(se), "n/a (no scoreable onset)", "—", ", ".join(fmt(e["first0"]) for e in fps) or "—", ", ".join(fmt(e["first0"]) for e in pend) or "—", pct(base)))
            else:
                rows.append((R, name, len(onm), len(se), len(hits), f"{sum(pos(t) for t in onm)}/{len(onm)} = {pct(prec)}", ", ".join(fmt(e["first0"]) for e in fps) or "—",
                             ", ".join(fmt(e["first0"]) for e in pend) or "—", pct(base)))
            key = f"regime_{R}_{name}_h{h}"
            N(f"{key}_on_months", len(onm), f"{name} ON months (USREC=0, resolved) in {R}"); N(f"{key}_episodes", len(se), "episodes starting in the regime")
            N(f"{key}_hits", len(hits), "hits"); N(f"{key}_false_positives", len(fps), "false positives"); N(f"{key}_month_precision", prec, "month precision within regime")
            NUM[f"{key}_false_positive_names"] = {"value": [fmt(e["first0"]) for e in fps], "def": "named false positives"}
            NUM[f"{key}_coincident_names"] = {"value": [fmt(e["raw_first"]) for e in coin], "def": "coincident episodes"}
    table(["regime", "definition", "ON months", "episodes", "hits", "month precision", "false positives (first ON)", "pending", "base rate"], rows)

# =========================================================================== 7. Q5 dated readings
W("## 7. Q5 — the three dated readings")
W()
live = dict(date="2026-09-15", print_date="2026-09-09", wti=97.26, pct=52.4, grade="RED", score=81.0, rm12=21.5, band=(17.8, 25.7), auc=0.686, spread_cmt=0.86, tp12=21.9)
last = P.loc[LAST]
d1v, d3v, d2v = float(last["oil_12m_pct"]), float(last["real_oil_12m_pct"]), float(last["nopi36_sum12"])
rows = [("Live daily channel (deployed, /pins as of 2026-09-15)", f"WTI 12m change +{live['pct']}% (print {live['print_date']} ${live['wti']} vs 252 trading days earlier)", live["grade"], f"score {live['score']}; /recession-model 12m {live['rm12']}% (band {live['band'][0]}–{live['band'][1]}, AUC {live['auc']}) on 3m10y CMT +{live['spread_cmt']}; TP-adj 12m {live['tp12']}%"),
        (f"Monthly mean, latest complete month {fmt(LAST)} — D1", f"oil_12m_pct = {d1v:+.1f}% (WTISPLC {last['wti']:.2f})", grade(d1v).upper(), "peak of the 2026 episode: " + f"{float(P.loc[M('2026-01'):, 'oil_12m_pct'].max()):+.1f}% in {fmt(P.loc[M('2026-01'):, 'oil_12m_pct'].idxmax())}"),
        (f"Monthly mean {fmt(LAST)} — D3 real", f"real_oil_12m_pct = {d3v:+.1f}%", grade(d3v).upper(), "peak " + f"{float(P.loc[M('2026-01'):, 'real_oil_12m_pct'].max()):+.1f}% in {fmt(P.loc[M('2026-01'):, 'real_oil_12m_pct'].idxmax())}"),
        (f"NOPI12 {fmt(LAST)} — D2", f"nopi36_sum12 = {d2v:.1f} log-pct", f"ON at 8: {'ON' if d2v >= 8 else 'OFF'} / ON at 10 (headline): {'ON' if d2v >= 10 else 'OFF'} / ON at 12: {'ON' if d2v >= 12 else 'OFF'}",
         f"monthly spikes since 2026-01: " + ", ".join(f"{fmt(t)} {v:.1f}" for t, v in P.loc[M("2026-01"):, "nopi36_monthly"].items() if v > 0) + f"; peak sum12 {float(P.loc[M('2026-01'):, 'nopi36_sum12'].max()):.1f} in {fmt(P.loc[M('2026-01'):, 'nopi36_sum12'].idxmax())}")]
table(["reading", "value", "grade / state", "notes"], rows)
N("q5_live_pct", live["pct"], "live deployed WTI 12m % (daily 252-obs point, print 2026-09-09)"); N("q5_live_grade", live["grade"], "live channel grade")
N("q5_monthly_D1_2026_08", d1v, "oil_12m_pct 2026-08"); N("q5_monthly_D1_grade", grade(d1v), "D1 grade 2026-08")
N("q5_monthly_D3_2026_08", d3v, "real_oil_12m_pct 2026-08"); N("q5_monthly_D3_grade", grade(d3v), "D3 grade 2026-08")
N("q5_D2_2026_08", d2v, "nopi36_sum12 2026-08 (log-pct)"); N("q5_D2_on_8", bool(d2v >= 8), "D2 ON at 8"); N("q5_D2_on_10", bool(d2v >= 10), "D2 ON at 10 (headline)"); N("q5_D2_on_12", bool(d2v >= 12), "D2 ON at 12")
N("q5_spread_gs_2026_08", float(last["spread_gs"]), "spread_gs 2026-08"); N("q5_curve_flat_gs6m_2026_08", bool(curve[LAST]), "curve_flat_gs6m 2026-08")
W(f"- Curve state now: spread_gs {float(last['spread_gs']):+.2f}pp, 6-month min {float(P['spread_gs'].rolling(6).min().loc[LAST]):+.2f} → curve flat = {bool(curve[LAST])}; live CMT +{live['spread_cmt']}.")
W(f"- Curve-state caveat for the analogs: the fit basis (`spread_gs` 6-month min) says NOT flat throughout 2026, but the deployed daily-183 rule and the CMT basis both read flat in 2026-04 (§1(ii)/(iii)); on the deployed rule the closest curve-state analogs would be the flat-at-first-ON episodes 1979-08 (hit) and 2007-11 (hit) rather than the not-flat set below.")
W(f"- The live daily print (RED, +52.4%) and the monthly-mean D1 ({d1v:+.1f}%, {grade(d1v).upper()}) disagree on grade for the current month — exactly the point-vs-mean gap of §1(i); "
  "the monthly-mean episode (D1-RED) was ON only in 2026-04..05 and is PENDING.")
W()
# analogs
W("### 7.1 Closest analog episodes (by peak reading, then by curve state at first ON)")
W()
def analogs(name, cur_peak, cur_flat):
    rows = []
    for ep in SCORED[(name, 12)]:
        if ep["raw_first"] >= M("2026-01"): continue
        f = ep["first0"] or ep["raw_first"]
        fl = bool(curve.get(f, False)); sp = P["spread_gs"].get(f, np.nan)
        rows.append((abs(ep["peak"] - cur_peak), ep, fl, sp))
    rows.sort(key=lambda r: r[0])
    return rows
cur = {"D1-RED": (float(P.loc[M("2026-01"):, "oil_12m_pct"].max()), bool(curve[LAST])), "D2": (float(P.loc[M("2026-01"):, "nopi36_sum12"].max()), bool(curve[LAST])), "D3-RED": (float(P.loc[M("2026-01"):, "real_oil_12m_pct"].max()), bool(curve[LAST]))}
for name, (cp, cf_) in cur.items():
    W(f"**{name}** — current episode peak {cp:.1f}, curve flat at first ON = {bool(curve[M('2026-04')])} (spread_gs {float(P.loc[M('2026-04'), 'spread_gs']):+.2f})")
    W()
    rs = analogs(name, cp, cf_)
    rows = [(fmt(ep["first0"] or ep["raw_first"]), f"{ep['peak']:.1f}", f"{d:.1f}", "flat" if fl else "not flat", f"{sp:+.2f}", ep["status"].upper(), ", ".join(fmt(e) for e in ep["hits"]) or "—") for d, ep, fl, sp in rs[:4]]
    same = [(fmt(ep["first0"] or ep["raw_first"]), f"{ep['peak']:.1f}", ep["status"].upper()) for d, ep, fl, sp in rs if fl == cf_][:4]
    table(["analog (first ON)", "peak", "abs Δpeak", "curve at first ON", "spread_gs", "outcome (h=12)", "event"], rows)
    W(f"Same curve state ({'flat' if cf_ else 'not flat'}) analogs, nearest by peak: " + "; ".join(f"{a} (peak {b}, {c})" for a, b, c in same))
    W()
    NUM[f"q5_analogs_{name}"] = {"value": [dict(first_on=r[0], peak=r[1], curve=r[3], outcome=r[5]) for r in rows], "def": "4 nearest episodes by |peak − current peak|"}

# =========================================================================== FIGURES
BG, BAND, GRID, INK, INK2 = "#fcfcfb", "#e5e4e0", "#e6e5e1", "#0b0b0b", "#52514e"
C_D1, C_OIL, C_D2, C_D3 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
ST = {"hit": ("#008300", "o", "hit"), "false positive": ("#e34948", "X", "FP"), "coincident": ("#eda100", "D", "coinc"),
      "pending": ("#8a8985", "s", "pending"), "in-recession (excluded)": ("#8a8985", "v", "in-rec")}
plt.rcParams.update({"font.size": 9, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})
TS = P.index.to_timestamp()
def shade(ax):
    u = USREC.values; i = 0
    while i < len(u):
        if u[i] == 1:
            j = i
            while j + 1 < len(u) and u[j + 1] == 1: j += 1
            ax.axvspan(TS[i], TS[j] + pd.offsets.MonthEnd(0), color=BAND, alpha=0.6, lw=0)
            i = j + 1
        else: i += 1
def style(ax):
    ax.set_facecolor(BG); ax.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)

# ---- Figure 1
fig, axes = plt.subplots(2, 1, figsize=(11, 10), sharex=True); fig.patch.set_facecolor(BG)
for ax, col, color, lab, defs, ylev in ((axes[0], "oil_12m_pct", C_OIL, "nominal WTI, 12-month % change (WTISPLC monthly mean)", ("D1-RED", "D2"), (235, 315)),
                                        (axes[1], "real_oil_12m_pct", C_D3, "real WTI (WTI/CPI), 12-month % change", ("D3-RED",), (235,))):
    style(ax); shade(ax)
    s = P[col].loc[M("1947-01"):]
    ax.plot(s.index.to_timestamp(), s.values, color=color, lw=2, label=lab)
    ax.axhline(25, color=INK2, lw=1, ls="--"); ax.axhline(50, color=INK2, lw=1, ls=":")
    ax.text(pd.Timestamp("1947-03-01"), 27, "+25 (yellow)", color=INK2, fontsize=8, va="bottom"); ax.text(pd.Timestamp("1947-03-01"), 52, "+50 (red)", color=INK2, fontsize=8, va="bottom")
    ax.set_ylim(-100, 400); ax.set_ylabel("12-month % change")
    for dname, y in zip(defs, ylev):
        ax.text(pd.Timestamp("1946-06-01"), y, f"{dname} episodes →", color=INK, fontsize=8, va="center", fontweight="bold")
        for ep in score_episodes(EPS[dname], ONSETS, 12, M("1947-01"), DOUBLE_DIP):
            c, mk, lab_ = ST[ep["status"]]
            mo = ep["raw_first"] if ep["status"] == "coincident" or not ep["first0"] else ep["first0"]
            x = mo.to_timestamp()
            ax.plot([x], [y], marker=mk, ms=9, color=c, mec=INK, mew=0.5, ls="none")
            ax.text(x, y + 7, f"{fmt(mo)} {lab_}", rotation=90, fontsize=6.5, color=INK, va="bottom", ha="center")
    handles = [Line2D([], [], color=color, lw=2, label=lab)] + [Line2D([], [], marker=mk, color=c, mec=INK, mew=0.5, ls="none", ms=8, label=f"episode start: {k}") for k, (c, mk, _) in ST.items()]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 0.62), fontsize=7.5, frameon=False, ncol=3)
axes[0].set_title("Oil shocks 1947–2026 and what followed: every D1 (nominal) and D2 (NOPI12) episode start, scored against NBER onsets at h = 12\n"
                  "WTISPLC monthly mean, 1947-01..2026-08; NBER recessions shaded; marker shape + label = outcome (hit / false positive / coincident / pending)", fontsize=10, loc="left")
axes[1].set_title("Real oil (WTI/CPI) 12-month % change and every D3 episode start, scored at h = 12\nWTISPLC/CPIAUCSL, 1948-01..2026-08; same outcome coding", fontsize=10, loc="left")
axes[1].set_xlabel("")
fig.tight_layout(); fig.savefig(f"{OUT}/fig1_oil_history.png", dpi=150, facecolor=BG); plt.close(fig)

# ---- Figure 4: lead strip
fig, axes = plt.subplots(2, 1, figsize=(11, 12), gridspec_kw={"height_ratios": [11, 15]}); fig.patch.set_facecolor(BG)
DEFC = {"D1-RED": (C_D1, "D1-RED (nominal ≥ +50)"), "D2": (C_D2, "D2 (NOPI12 ≥ 10)"), "D3-RED": (C_D3, "D3-RED (real ≥ +50)")}
def lead_rows(events, evsc_fn, ax, title):
    style(ax)
    ys = list(range(len(events)))[::-1]
    for y, e in zip(ys, events):
        ax.axhline(y, color=GRID, lw=0.8)
        for k, (dname, (c, lab)) in enumerate(DEFC.items()):
            off = (k - 1) * 0.27
            x = evsc_fn(dname, e)
            if x["cat"] == "caught":
                ax.plot([x["last_on"], x["lead"]], [y + off] * 2, color=c, lw=2, alpha=0.6)
                ax.plot([x["lead"]], [y + off], marker="o", ms=9, color=c, mec=INK, mew=0.5, ls="none")
                ax.text(x["lead"] + 0.6, y + off, f"{x['lead']}m", fontsize=7, color=INK, va="center")
            elif x["cat"] == "coincident":
                ax.plot([x["lead"]], [y + off], marker="D", ms=8, color=c, mec=INK, mew=0.5, ls="none")
                ax.text(x["lead"] - 0.7, y + off, "coincident", fontsize=7, color=INK, va="center", ha="right")
            elif x["cat"] == "missed":
                ax.plot([0], [y + off], marker="x", ms=9, color=c, mew=2, ls="none")
                ax.text(-0.8, y + off, "missed", fontsize=7, color=INK2, va="center", ha="right")
            else:
                ax.text(-0.8, y + off, "not evaluable", fontsize=7, color=INK2, va="center", ha="right")
    ax.set_yticks(ys); ax.set_yticklabels([fmt(e) for e in events]); ax.set_ylim(-0.7, len(events) - 0.3)
    ax.axvline(12, color=INK2, lw=1, ls="--"); ax.axvline(18, color=INK2, lw=1, ls=":")
    ax.text(12.2, len(events) - 0.45, "h = 12", color=INK2, fontsize=8); ax.text(18.2, len(events) - 0.45, "h = 18", color=INK2, fontsize=8)
    ax.set_xlim(-8, 50); ax.set_xlabel("months before the event (dot = first ON month of the crediting episode; bar = span back to the last ON month before the event)")
    ax.set_title(title, fontsize=10, loc="left")
    ax.legend(handles=[Line2D([], [], marker="o", color=c, mec=INK, ls="none", ms=8, label=lab) for c, lab in DEFC.values()] +
              [Line2D([], [], marker="D", color=INK2, ls="none", ms=8, label="coincident (first ON 0–3 m after event)"), Line2D([], [], marker="x", color=INK2, ls="none", ms=8, mew=2, label="missed")],
              loc="upper right", fontsize=7.5, frameon=False)
lead_rows(COMMON_ONSETS, lambda d, e: [x for x in EVENTS_SC[(d, 18)] if x["event"] == e][0], axes[0],
          "Lead time of the oil signal before each NBER onset, 1953-08..2020-03 (h = 18 scoring; leads > 12 are h=18-only or long-episode credits)\n"
          "WTISPLC monthly mean; ON months with USREC=0; 1981-08 scored on ON months 1980-08..1981-07 only")
b1_events = [m for m, _ in B1]
def b1_sc(d, e):
    return [x for x in SC5[("B1 drawdown starts", f"{d} alone", 18)][1] if x["event"] == e][0]
lead_rows(b1_events, b1_sc, axes[1], "Lead time of the oil signal before each ≥15% S&P 500 drawdown start (B1 running-peak, 1950+; h = 18 scoring)\n"
          "same episode rule and USREC=0 filter; depth of each drawdown in events.json")
fig.tight_layout(); fig.savefig(f"{OUT}/fig4_lead_strip.png", dpi=150, facecolor=BG); plt.close(fig)

W("## 8. Figures")
W()
W("- `fig1_oil_history.png` — nominal (top) and real (bottom) WTI 12-month % change 1947–2026 with NBER bands, +25/+50 lines, and every D1-RED / D2 / D3-RED episode start marked with its h = 12 outcome (shape + label + status colour).")
W("- `fig4_lead_strip.png` — one row per NBER onset (top, 11) and per B1 drawdown start (bottom, 15): lead in months from the crediting episode's first ON month for D1-RED / D2 / D3-RED, with coincident and missed labelled; vertical guides at h = 12 and 18.")
W()

# =========================================================================== reading choices
W("## 9. Reading choices where the spec is ambiguous (logged, not searched)")
W()
W("1. In-recession ON months are not 'OFF months': they neither count (USREC=0 filter) nor break an episode; the raw first ON month (possibly in-recession) drives the coincident test — required to reproduce the spec's own 1973-12 / 1990-08 expectations.")
W("2. Classification precedence: hit > coincident > pending > false positive; an episode with no USREC=0 month and no coincident onset is 'in-recession (excluded)'.")
W("3. Resolved: t + h ≤ 2025-08 (spec text), so the last resolved ON month is 2024-08 (h=12) / 2024-02 (h=18).")
W("4. Recall evaluability by the rule's own series start (not the common precision window); curve rules start 1953-09.")
W("5. Drawdown scoring re-uses the NBER episode machinery (USREC=0 filter, coincident window [e, e+3], resolved rule) with no double-dip rule; evaluable if e − h ≥ series start.")
W("6. Month-level precision is mechanical over all USREC=0 resolved ON months; the variant excluding coincident-episode months is shown beside it.")
W("7. '≥ 1 episode better' (§5 D2-vs-D1 row) read as ≥ 1 more hit or ≥ 1 fewer false positive with recall ≥ D1's.")
W()

open(f"{OUT}/results.md", "w").write("\n".join(LINES))
json.dump(NUM, open(f"{OUT}/numbers.json", "w"), indent=1, default=str)
print("done;", len(NUM), "numbers;", len(LINES), "lines")
