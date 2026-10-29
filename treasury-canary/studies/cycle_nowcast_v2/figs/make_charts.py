"""Charts for studies/cycle-nowcast-v2.md RESULTS. Reads results.json (committed, unedited) and,
for the 655-row lag-simulation series that results.json summarises only, re-runs the engine's
deterministic IS-A simulation on F5 (chart-only; no scoring, nothing armed)."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date

STUDY = "/home/user/uranium-dashboard/treasury-canary/studies/cycle_nowcast_v2"
sys.path.insert(0, STUDY)
import engine as E
import metrics as X

OUT = os.path.join(STUDY, "figs")
R = json.load(open(os.path.join(STUDY, "results.json")))
res = R["results"]

C = {"ens": "#1d4ed8", "pers": "#c2410c", "ads": "#0d9488", "comp": "#7e22ce", "ink": "#1f2937",
     "muted": "#6b7280", "grid": "#e5e7eb", "rec": "#d1d5db", "surface": "#fcfcfb"}
plt.rcParams.update({"font.size": 9, "axes.edgecolor": C["muted"], "axes.labelcolor": C["ink"],
                     "xtick.color": C["ink"], "ytick.color": C["ink"], "axes.grid": True,
                     "grid.color": C["grid"], "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": C["surface"], "axes.facecolor": C["surface"],
                     "legend.frameon": False})

def md(m):  # "YYYY-MM" -> date
    y, mo = m.split("-")[:2]
    return date(int(y), int(mo), 1)

def shade_recessions(ax, usrec_months, usrec_vals, lo=None, hi=None):
    on = None
    for m, v in zip(usrec_months, usrec_vals):
        d = md(m)
        if (lo and d < lo) or (hi and d > hi):
            continue
        if v >= 0.5 and on is None:
            on = d
        if v < 0.5 and on is not None:
            ax.axvspan(on, d, color=C["rec"], alpha=0.55, lw=0)
            on = None
    if on is not None:
        ax.axvspan(on, hi or md(usrec_months[-1]), color=C["rec"], alpha=0.55, lw=0)

# ------------------------------------------------------------------ data: F5 + IS-A simulation
SERIES13 = ["PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "PERMIT", "ICSA", "AWHMAN", "UMCSENT",
            "T10Y3M", "BAA10YM", "GS10", "TB3MS", "USREC"]
f5 = E.load_fred_csv_dir(os.path.join(STUDY, "data", "fred_2026-10-28"), SERIES13)
ds = E.build(f5)
hi = E.scored_window_end(ds)
targets = E.eval_targets(ds, ("1972-01", hi))
sim = E.simulate(ds, E.PATTERNS["A"], "scoring", targets, "hh", window=("1972-01", hi))
months = sim["months"]; y = sim["y"]; pers = sim["pers_real"]; ens = sim["ens"]
usrec_m = ds.months
usrec_v = np.array([f5["USREC"].get(m, np.nan) for m in ds.months])
dates = [md(m) for m in months]

# cross-check against the committed decision numbers (chart integrity, not a re-score)
e, ep = ens - y, pers - y
m = np.isfinite(e) & np.isfinite(ep); ex = X.ex2020_mask(months) & m
pct_full = X.pct_change(X.rmse(e, m), X.rmse(ep, m)); pct_ex = X.pct_change(X.rmse(e, ex), X.rmse(ep, ex))
d1 = res["decision_D1"]["conditions"]["value"]
assert abs(pct_full - d1["rmse_pct_vs_pers_full"]) < 1e-9 and abs(pct_ex - d1["rmse_pct_vs_pers_ex2020"]) < 1e-9, (pct_full, pct_ex, d1)
print("D1 chart series reproduce results.json:", round(pct_full, 3), round(pct_ex, 3))

# ------------------------------------------------------------------ FIG 1: D-1 lag simulation
fig, axes = plt.subplots(3, 1, figsize=(11, 9.2), gridspec_kw={"height_ratios": [2.2, 2.2, 1.3]})
ax = axes[0]
shade_recessions(ax, usrec_m, usrec_v, md("1972-01"), md(hi))
ax.plot(dates, y, color=C["ink"], lw=1.4, label="realized coincident COIN(M), final vintage")
ax.plot(dates, ens, color=C["ens"], lw=1.1, label="ENS_HH nowcast at IS-A (one month ahead, walk-forward)")
ax.axhline(-0.75, color=C["muted"], lw=0.7, ls="--"); ax.text(md("2024-06"), -0.72, "contraction line −0.75", color=C["muted"], fontsize=7.5, va="bottom", ha="right")
ax.set_ylim(-4.2, 2.6); ax.set_ylabel("composite z")
ax.set_title("D-1  one-month-ahead nowcast vs realized, 1972-01 .. %s (final-vintage replay, n = %d)" % (hi, len(months)), loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="lower left", fontsize=8)
ax.xaxis.set_major_locator(mdates.YearLocator(5)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

ax = axes[1]
lo2 = md("2005-01")
sel = [d >= lo2 for d in dates]
shade_recessions(ax, usrec_m, usrec_v, lo2, md(hi))
ax.plot([d for d, s in zip(dates, sel) if s], y[sel], color=C["ink"], lw=1.5, label="realized COIN(M)")
ax.plot([d for d, s in zip(dates, sel) if s], pers[sel], color=C["pers"], lw=1.1, ls=(0, (3, 2)), label="PERS = realized COIN(M−1)")
ax.plot([d for d, s in zip(dates, sel) if s], ens[sel], color=C["ens"], lw=1.3, label="ENS_HH at IS-A")
ax.axhline(-0.75, color=C["muted"], lw=0.7, ls="--")
ax.set_ylim(-4.2, 2.0); ax.set_ylabel("composite z")
ax.set_title("zoom 2005+ : the nowcast against the persistence baseline it must beat", loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="lower left", fontsize=8, ncol=3)
ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

ax = axes[2]
# rolling 36-month RMSE ratio ENS/PERS (ex-2020 rows dropped, series concatenated as in the spec)
idx = np.flatnonzero(ex)
w = 36
rr_d, rr = [], []
for k in range(w, len(idx) + 1):
    ii = idx[k - w:k]
    rr_d.append(dates[ii[-1]]); rr.append(X.rmse(e[ii]) / X.rmse(ep[ii]))
ax.plot(rr_d, rr, color=C["ens"], lw=1.2, label="rolling 36-month RMSE ratio ENS_HH / PERS (2020 rows dropped)")
ax.axhline(1.0, color=C["ink"], lw=0.8)
ax.axhline(0.92, color=C["pers"], lw=0.8, ls="--"); ax.text(md("1973-06"), 0.935, "ex-2020 bar: ratio ≤ 0.92 (−8%)", color=C["pers"], fontsize=7.5, va="bottom")
ax.axhline(1 + d1["rmse_pct_vs_pers_ex2020"] / 100, color=C["ens"], lw=0.8, ls=":")
ax.text(md("1973-06"), 1 + d1["rmse_pct_vs_pers_ex2020"] / 100 - 0.015, "whole-sample ex-2020 ratio %.3f" % (1 + d1["rmse_pct_vs_pers_ex2020"] / 100), color=C["ens"], fontsize=7.5, va="top")
ax.set_ylim(0.55, 1.5); ax.set_ylabel("RMSE ratio")
ax.set_title("where the edge comes from: strong 1975–2015, thin since (2013+ ex-2020 ratio 0.94; 2016+ 0.93)", loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="upper left", fontsize=8, bbox_to_anchor=(0.0, 1.0))
ax.xaxis.set_major_locator(mdates.YearLocator(5)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.text(0.01, 0.005, "Decision D-1 PASS: RMSE vs PERS %.1f%% full (bar −25) · %.1f%% ex-2020 (bar −8) · DM NW-6 t = %.2f (bar −1.645). Final-vintage data; publication calendars not modelled; in-sample z-score histories." % (d1["rmse_pct_vs_pers_full"], d1["rmse_pct_vs_pers_ex2020"], d1["dm_t_ex2020"]), fontsize=7.5, color=C["muted"])
fig.tight_layout(rect=(0, 0.02, 1, 1))
fig.savefig(os.path.join(OUT, "fig_cnv2_d1_lagsim.png"), dpi=150); plt.close(fig)

# ------------------------------------------------------------------ FIG 2: D-2 completed vs partial
d2 = res["decision_D2"]
# rebuild the D-2 error series (same construction as scoring.section_bands)
def pattern_errors(pattern):
    n = ds.n; ee = np.full(n, np.nan); keys = [None] * n
    for i in range(n):
        if not np.isfinite(ds.coin[i]) or not ds.complete[i]:
            continue
        cm = E.complete_month(ds, i, pattern, "scoring"); keys[i] = cm["pattern_key"]; ee[i] = ds.coin[i] - cm["value"]
    return ee, keys
e1, keys1 = pattern_errors({"CMRMTSPL": 1})
partial = np.array([ds.available_mean(i, ("PAYEMS", "INDPRO", "W875RX1")) for i in range(ds.n)])
epart = ds.coin - partial
k1 = E.pattern_key({"CMRMTSPL": 1})
allm = ds.months
m77 = np.array([(mm >= "1977-07") and (mm <= hi) and (k == k1) for mm, k in zip(allm, keys1)]) & np.isfinite(e1) & np.isfinite(epart)
ec, epp = e1[m77], epart[m77]; dm77 = [md(mm) for mm, ok in zip(allm, m77) if ok]
rec = d2["distribution_completed"]["value"]; rep = d2["distribution_partial"]["value"]
assert abs(X.rmse(ec) - rec["rmse"]) < 1e-9 and abs(X.rmse(epp) - rep["rmse"]) < 1e-9, (X.rmse(ec), rec["rmse"], X.rmse(epp), rep["rmse"])
print("D2 chart series reproduce results.json:", round(X.rmse(ec), 4), round(X.rmse(epp), 4))

fig, axes = plt.subplots(2, 1, figsize=(11, 6.6), gridspec_kw={"height_ratios": [2, 1.4]})
ax = axes[0]
shade_recessions(ax, usrec_m, usrec_v, md("1977-07"), md(hi))
ax.plot(dm77, epp, color=C["pers"], lw=0.9, label="realized − partial 3-member mean (what the board showed)")
ax.plot(dm77, ec, color=C["comp"], lw=1.0, label="realized − completed COIN_HH (CMRMTSPL bridged one month)")
ax.axhline(0, color=C["ink"], lw=0.7)
ax.set_ylim(-0.9, 0.9); ax.set_ylabel("error (z units)")
ax.set_title("D-2  error of the headline coincident value when real sales lag one month, 1977-07 .. %s (n = %d)" % (hi, int(m77.sum())), loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="lower left", fontsize=8)
ax.xaxis.set_major_locator(mdates.YearLocator(5)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax = axes[1]
bins = np.linspace(-0.6, 0.6, 61)
ax.hist(epp, bins=bins, color=C["pers"], alpha=0.55, label="partial: RMSE %.3f, bias %+.3f, p10/p90 %+.2f/%+.2f" % (rep["rmse"], rep["bias"], rep["p10"], rep["p90"]))
ax.hist(ec, bins=bins, color=C["comp"], alpha=0.55, label="completed: RMSE %.3f, bias %+.3f, p10/p90 %+.2f/%+.2f" % (rec["rmse"], rec["bias"], rec["p10"], rec["p90"]))
ax.axvline(0, color=C["ink"], lw=0.7)
ax.set_xlabel("realized − shown value"); ax.set_ylabel("months")
ax.set_title("distribution: the completed value is unbiased and tighter; the partial mean runs cold (realized averages +0.04 above it)", loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="upper left", fontsize=8)
rm = d2["rmse"]["value"] if "rmse" in d2 else None
fig.text(0.01, 0.005, "Decision D-2 PASS: completed RMSE < partial RMSE full (%.3f vs %.3f) and ex-2020 (%.3f vs %.3f). Completion error only, final-vintage data; first-print revision of W875RX1 (0.47 sd) not included in these bands." % (rec["rmse"], rep["rmse"], d2["distribution_completed_ex2020"]["value"]["rmse"], d2["distribution_partial_ex2020"]["value"]["rmse"]), fontsize=7.5, color=C["muted"])
fig.tight_layout(rect=(0, 0.02, 1, 1))
fig.savefig(os.path.join(OUT, "fig_cnv2_d2_completed.png"), dpi=150); plt.close(fig)

# ------------------------------------------------------------------ FIG 3: regime (i) real time + D-3 comparator
rows = [r for r in res["comparator"]["rows"]["value"] if r["IS"] == "A"]
rows.sort(key=lambda r: r["issue_date"])
def iso(d): y_, m_, d_ = d.split("-"); return date(int(y_), int(m_), int(d_))
idates = [iso(r["issue_date"]) for r in rows]
ens_raw = np.array([r["ens_hh"] if r["ens_hh"] is not None else np.nan for r in rows])
ens_cal = np.array([r["ens_cal"] if r["ens_cal"] is not None else np.nan for r in rows])
ads_cal = np.array([r["ads_cal"] if r["ads_cal"] is not None else np.nan for r in rows])
tl = np.array([r["target_latest"] if r["target_latest"] is not None else np.nan for r in rows])
tf = np.array([r["target_first"] if r["target_first"] is not None else np.nan for r in rows])
d3 = res["decision_D3"]
cw = d3["calibration_warmup"]["value"]; out3 = d3["outcome"]["value"] if isinstance(d3["outcome"]["value"], dict) else None
r_ex = d3["loyo_r_ex2020"]["value"]["ratio"]; dm3 = d3["dm_one_sided_ex2020"]["value"]
fig, axes = plt.subplots(3, 1, figsize=(11, 9.6), gridspec_kw={"height_ratios": [2.2, 2.0, 1.3]})
ax = axes[0]
shade_recessions(ax, usrec_m, usrec_v, date(2013, 1, 1), date(2026, 11, 1))
ax.plot(idates, tl, color=C["ink"], lw=1.4, label="target: realized COIN(M) on F5 (latest)")
ax.plot(idates, tf, color=C["muted"], lw=0.9, ls=(0, (2, 2)), label="target: COIN(M) at its first vintage")
ax.plot(idates, ens_raw, color=C["ens"], lw=1.1, marker="o", ms=2.2, label="ENS_HH issued on payroll day (IS-A), true real time")
ax.axhline(-0.75, color=C["muted"], lw=0.7, ls="--")
ax.set_ylim(-4.5, 2.2); ax.set_ylabel("composite z")
ax.set_title("Regime (i)  true real-time replay from ALFRED vintages, issue dates 2013-06-14 .. %s (%d IS-A rows, one recession)" % (rows[-1]["issue_date"], len(rows)), loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="lower left", fontsize=8)
ax.xaxis.set_major_locator(mdates.YearLocator(1)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax = axes[1]
shade_recessions(ax, usrec_m, usrec_v, date(2015, 1, 1), date(2026, 11, 1))
ok = np.isfinite(ens_cal) & np.isfinite(ads_cal) & np.isfinite(tl)
ax.plot([d for d, o in zip(idates, ok) if o], tl[ok], color=C["ink"], lw=1.4, label="realized COIN(M)")
ax.plot([d for d, o in zip(idates, ok) if o], ads_cal[ok], color=C["ads"], lw=1.1, label="ADS (Philly Fed, archived vintage ≤ d), walk-forward calibrated to COIN")
ax.plot([d for d, o in zip(idates, ok) if o], ens_cal[ok], color=C["ens"], lw=1.2, label="ENS_HH, same calibration")
ax.set_xlim(date(2015, 1, 1), date(2026, 11, 1)); ax.set_ylim(-4.5, 2.2); ax.set_ylabel("composite z")
ax.set_title("D-3  home-built ENS_HH vs the external ADS comparator, both calibrated on the same stored rows (first calibrated %s, %d rows ex-2020)" % (cw["first_calibrated_month"], cw["n_ex2020"]), loc="left", fontsize=10, color=C["ink"])
ax.legend(loc="lower left", fontsize=8)
ax.xaxis.set_major_locator(mdates.YearLocator(1)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax = axes[2]
by = d3["loyo_r_ex2020"]["value"]["by_year"]
yrs = sorted(by); vals = [by[k] for k in yrs]
ax.bar(yrs, vals, color=C["ens"], width=0.7)
ax.axhline(r_ex, color=C["ink"], lw=0.9); ax.text(len(yrs) - 0.6, r_ex + 0.01, "r = %.3f (all rows)" % r_ex, ha="right", fontsize=8, color=C["ink"])
ax.axhline(1.10, color=C["pers"], lw=0.8, ls="--"); ax.text(-0.4, 1.115, "SUCCESS ≤ 1.10 · KILL > 1.25 and DM p < 0.10", fontsize=7.5, color=C["pers"], va="bottom")
ax.axhline(1.25, color=C["pers"], lw=0.8, ls=":")
ax.set_ylim(0, 1.38); ax.set_ylabel("RMSE ratio ENS/ADS"); ax.set_xlabel("calendar year dropped (leave-one-year-out, ex-2020 rows)")
ax.set_title("r = RMSE(ENS_HH cal) / RMSE(ADS cal): dropping any single year keeps r between %.2f and %.2f" % (min(vals), max(vals)), loc="left", fontsize=10, color=C["ink"])
fig.text(0.01, 0.005, "Decision D-3 SUCCESS: r = %.3f ≤ 1.10 on n = %d (spec expected ≈145; 25 warm-up rows uncalibrated) · one-sided DM t = %.2f (ENS not worse) · same class under first-vintage targets (r_first %.3f).\nOne recession in regime (i); ADS shares the same four inputs (a different model, not independent data); calibration = walk-forward affine fit of each reading to realized COIN on identical stored rows." % (r_ex, cw["n_ex2020"], dm3["t"], d3["class_under_target_first"]["value"]["r_first_ex2020"]), fontsize=7.5, color=C["muted"])
fig.tight_layout(rect=(0, 0.035, 1, 1))
fig.savefig(os.path.join(OUT, "fig_cnv2_regime_i_d3.png"), dpi=150); plt.close(fig)

# ------------------------------------------------------------------ FIG 4: Chauvet-Piger real-time path
cp = res["chauvet_piger"]
path = cp["path"]["value"]
rd = [iso(p["release_date"]) for p in path]; pct = np.array([p["pct"] for p in path])
fig, ax = plt.subplots(figsize=(11, 4.6))
shade_recessions(ax, usrec_m, usrec_v, date(2006, 1, 1), date(2026, 11, 1))
ax.step(rd, pct, where="post", color=C["ads"], lw=1.2, label="Chauvet–Piger real-time recession probability, latest month at each release (Piger archive + ALFRED)")
for lvl, lab in ((80, "3×80% declare"), (50, "50%"), (20, "3×20% end")):
    ax.axhline(lvl, color=C["muted"], lw=0.7, ls="--"); ax.text(date(2006, 2, 1), lvl + 1.5, lab, fontsize=7.5, color=C["muted"])
decl = cp["declarations_3x80"]["value"]
for dcl in decl:
    d0 = iso(dcl["release_date"]); 
    ax.axvline(d0, color=C["pers"], lw=1.0)
    if dcl["kind"] == "start":
        ax.annotate("3×80%% declared %s\n(NBER peak month %s; +%d days vs NBER's own announcement)" % (dcl["release_date"], dcl["nber_peak_month"], dcl["days_vs_nber_announcement"]),
                    xy=(d0, 92), xytext=(date(2010, 6, 1), 92), fontsize=7.5, color=C["pers"], arrowprops=dict(arrowstyle="-", color=C["pers"], lw=0.6), va="center")
    else:
        ax.annotate("3×20%% end declared %s" % dcl["release_date"], xy=(d0, 40), xytext=(date(2011, 3, 1), 40), fontsize=7.5, color=C["pers"], arrowprops=dict(arrowstyle="-", color=C["pers"], lw=0.6), va="center")
nd = cp["onsets_never_declared_3x80"]["value"]
ax.annotate("2020-03 onset: 100% print at the 2020-04-30 release but never three consecutive ≥80% months\n(the 1-month ≥50% sensitivity catches it); Mar–Jul 2020 re-based on 2020-12-23", xy=(date(2020, 4, 30), 100), xytext=(date(2014, 6, 1), 62), fontsize=7.5, color=C["ink"], arrowprops=dict(arrowstyle="-", color=C["ink"], lw=0.6))
ax.set_ylim(-2, 105); ax.set_ylabel("probability, %"); ax.set_xlim(date(2006, 1, 1), date(2026, 11, 1))
ax.set_title("Chauvet–Piger real-time recession probability, latest month at each release (Piger archive + ALFRED), 2006-08 .. 2026-09: 240 releases, two recessions; descriptive, no grade", loc="left", fontsize=10, color=C["ink"])
ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.text(0.01, 0.005, "Same four inputs as our composite (a different model, not independent data). Shaded = NBER recessions. Latest release 2026-09-30: 2026-08 at 0.62%.\nALFRED vintage 2023-02-01 differs from Piger's column by >1 pp (flagged); 80 of 240 releases read from Piger's own archive where ALFRED has no vintage.", fontsize=7.5, color=C["muted"])
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(os.path.join(OUT, "fig_cnv2_chauvet_piger.png"), dpi=150); plt.close(fig)

# ------------------------------------------------------------------ FIG 5: regime (i) baselines in hand vs hindsight
sc = [x for x in res["regime_i"]["scorecards"]["value"] if x["IS"] == "A"]
def arr(f): return np.array([f(x) if f(x) is not None else np.nan for x in sc], float)
tl_ = arr(lambda x: x.get("target_latest")); ens_ = arr(lambda x: x["ens_hh"])
ph_ = arr(lambda x: x["persistence_in_hand"]["hh"]); pa_ = arr(lambda x: x["persistence_in_hand"]["available"]); pr_ = arr(lambda x: x["pers_realized_latest"])
Ms = [x["M"] for x in sc]; exm = X.ex2020_mask(Ms)
bars = []
for name, p_ in (("ENS_HH nowcast\n(issued on the day)", ens_), ("persistence in hand:\navailable-members mean", pa_), ("persistence in hand:\ncompleted COIN_HH(M−1)", ph_), ("persistence with hindsight:\nfinal-vintage COIN(M−1)", pr_)):
    mm = np.isfinite(p_) & np.isfinite(tl_)
    bars.append((name, X.rmse(p_ - tl_, mm & exm), int((mm & exm).sum())))
A_ = res["regime_i"]["per_is"]["A"]["value"]
assert abs(bars[0][1] - A_["rmse_vs_latest_ex2020"]["ENS_HH"]) < 1e-9 and abs(bars[3][1] - A_["rmse_vs_latest_ex2020"]["PERS_realized_latest"]) < 1e-9
fig, ax = plt.subplots(figsize=(9.5, 4.4))
cols = [C["ens"], C["pers"], C["pers"], C["muted"]]
xs = np.arange(len(bars))
ax.bar(xs, [b[1] for b in bars], color=cols, width=0.62)
for i, b in enumerate(bars):
    ax.text(i, b[1] + 0.004, "%.3f" % b[1], ha="center", fontsize=8.5, color=C["ink"])
ax.set_xticks(xs); ax.set_xticklabels([b[0] for b in bars], fontsize=8)
ax.set_ylabel("RMSE vs realized COIN(M), ex-2020"); ax.set_ylim(0, 0.33)
ax.set_title("Regime (i) true real time, IS-A rows 2013-06 .. 2026-09 ex-2020 (n = %d):\nthe nowcast beats every baseline available on the day, not the hindsight one" % bars[0][2], loc="left", fontsize=9.5, color=C["ink"])
fig.text(0.01, 0.01, "Descriptive, no pass/fail (one recession). DM NW-6 one-sided: vs the hindsight baseline t = +1.37 (nowcast worse, p = 0.085);\nvs available-members t = −2.13 (nowcast better, p = 0.017); vs completed COIN_HH(M−1) t = −1.64 (p = 0.05). Target = realized COIN(M) on F5.", fontsize=7.2, color=C["muted"])
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "fig_cnv2_regime_i_baselines.png"), dpi=150); plt.close(fig)
print("written", sorted(os.listdir(OUT)))
