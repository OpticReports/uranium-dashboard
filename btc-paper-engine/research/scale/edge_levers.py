"""RANKING + CHARTS: the edge-side levers, in dollars of extra AUTHORISED gross
notional per unit of implementation risk.

Consumes the frozen JSON from the three measurement scripts in this directory:
  maker_fill.json       fill rates, variant books, per-arm Kelly
  verify_maker.json     adversarial verification of the fill-rate claim
  maker_exit_risk.json  implementation risk of the maker-exit half
  fee_to_notional.json  per-leg venue fees -> authorised gross, THE headline
  blend_corr.json       measured leg correlation -> gross per unit DD

Run AFTER those. python3 research/scale/edge_levers.py
"""
from __future__ import annotations
import json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
import numpy as np                                               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda n: json.load(open(os.path.join(HERE, n)))             # noqa: E731

MF, VM, MER = J("maker_fill.json"), J("verify_maker.json"), J("maker_exit_risk.json")
F2N, BC = J("fee_to_notional.json"), J("blend_corr.json")

# dataviz reference palette, categorical slots 1-3 (all-pairs validated)
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8880"
SURF, GRID = "#fcfcfb", "#e3e2dd"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.edgecolor": GRID, "grid.color": GRID,
    "grid.linewidth": 0.8, "font.size": 9.5, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.spines.top": False,
    "axes.spines.right": False, "lines.linewidth": 2.0,
})

LIVE = F2N["live"]["gross_usd"]
CAP = F2N["live"]["rail_cap_usd"]
MAXN = F2N["live"]["MAX_NOTIONAL_USD"]
gov = F2N["governing"]

SHORT = {
    "LIVE TODAY          entry taker, exit taker": "Today: taker in, taker out (8.64 bps)",
    "FIX 1: maker entry  entry maker, exit taker": "FIX 1  maker entry (5.76 bps)",
    "FIX 1+2: + maker SIGNAL exits (S3 only, measured)": "FIX 1+2 nominal (3.88 bps)",
    "FIX 1+2 RISK-ADJUSTED (measured net exit gain, not nominal)":
        "FIX 1+2 risk-adjusted (measured)",
    "CEILING: both legs fully maker (not achievable)": "Ceiling: fully maker (2.88 bps)",
    "VIP tier 1 ($5m/14d) on top of FIX 1+2": "+ VIP tier 1 ($5m / 14d)",
    "VIP tier 2 ($25m/14d) on top of FIX 1+2": "+ VIP tier 2 ($25m / 14d)",
}

# =====================================================================  FIG 1
fig, ax = plt.subplots(figsize=(11.2, 5.4))
keys = [k for k in SHORT if k in gov]
vals = [gov[k]["authorised_gross_usd"] for k in keys]
labs = [SHORT[k] for k in keys]
order = np.argsort(vals)
y = np.arange(len(order))
cols = [C1 if "Ceiling" not in labs[i] and "VIP" not in labs[i] else C3
        for i in order]
cols = [C2 if "Today" in labs[i] else c for c, i in zip(cols, order)]
ax.barh(y, [vals[i] for i in order], height=0.62, color=cols, zorder=3)
for j, i in enumerate(order):
    ax.text(vals[i] + 2200, j, f"${vals[i]:,.0f}", va="center", ha="left",
            fontsize=9.5, color=INK, fontweight="bold")
ax.set_yticks(y)
ax.set_yticklabels([labs[i] for i in order], fontsize=9.5)
LEVCAP = 2.0 * 50_000.0
ax.axvline(LIVE, color=INK, lw=1.8, ls="-", zorder=5)
ax.axvline(MAXN, color=INK3, lw=1.3, ls=":", zorder=4)
ax.axvline(LEVCAP, color=INK3, lw=1.3, ls="--", zorder=4)
ax.annotate(f"live book\n${LIVE:,.0f}", xy=(LIVE, -0.55), xytext=(LIVE, -1.55),
            ha="center", va="bottom", fontsize=8.5, color=INK,
            fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=INK, lw=1.0))
ax.annotate(f"MAX_NOTIONAL_USD\n${MAXN:,.0f}  (clamps first)",
            xy=(MAXN, -0.55), xytext=(MAXN + 9000, -1.75), ha="left",
            va="bottom", fontsize=8.5, color=INK2,
            arrowprops=dict(arrowstyle="-", color=INK3, lw=1.0))
ax.annotate(f"MAX_ACCOUNT_LEV x SIZING_BASE_USD\n${LEVCAP:,.0f}",
            xy=(LEVCAP, -0.55), xytext=(LEVCAP, -1.75), ha="center",
            va="bottom", fontsize=8.5, color=INK2,
            arrowprops=dict(arrowstyle="-", color=INK3, lw=1.0))
ax.set_xlabel("Authorised GROSS notional at $100,055 equity  (governing = the "
              "more conservative of the two windows)", labelpad=26)
ax.set_title("Edge-side lever 1: fixing execution raises AUTHORISED size at "
             "identical drawdown\nKelly envelope on the shipped pipeline, "
             "per-leg real venue fees, cash_apy 0", pad=14)
ax.set_xlim(0, max(vals) * 1.22)
ax.grid(axis="x", zorder=0)
ax.set_ylim(-2.3, len(y) - 0.35)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "edge_fig1_authorised_notional.png"), dpi=140)
plt.close(fig)

# =====================================================================  FIG 2
# authorised m vs round-trip fee on the pullback leg, both windows
fig, ax = plt.subplots(figsize=(9.2, 5.2))
rows = {}
for k, v in F2N["arms"].items():
    w, arm = k.split("|", 1)
    if abs(v["rt_S4"] - 8.64) > 1e-6:     # hold the TREND leg fixed: one axis,
        continue                           # one variable (drops CEILING + VIP)
    rows.setdefault(w, []).append((v["rt_S3"], v["recommended_m"], arm))
for (w, col, mk, lab) in (("2y", C1, "o", "2y window — binds on bootstrap p10"),
                          ("full", C2, "s", "full window — binds on the DD30 budget")):
    pts = sorted(rows[w])
    xs = [p[0] for p in pts]
    ys = [p[1] * 1.5 * F2N["live"]["equity"] for p in pts]
    ax.plot(xs, ys, marker=mk, ms=7, color=col, label=lab, mec=SURF, mew=1.5,
            zorder=3)
ax.axhline(LIVE, color=INK, lw=1.5, zorder=4)
ax.axhline(MAXN, color=INK3, lw=1.2, ls=":", zorder=4)
ax.text(8.75, LIVE - 3200, f"live book  ${LIVE:,.0f}", color=INK, fontsize=9,
        ha="left", va="top", fontweight="bold")
ax.text(8.75, MAXN + 2600, f"MAX_NOTIONAL_USD  ${MAXN:,.0f}", color=INK2,
        fontsize=8.5, ha="left", va="bottom")
ax.annotate("today: entry crosses,\npays taker both legs",
            xy=(8.64, gov[keys[0]]["authorised_gross_usd"]), xytext=(7.9, 38000),
            fontsize=9, color=INK2, ha="center",
            arrowprops=dict(arrowstyle="->", color=INK3, lw=1.1))
ax.annotate("entry rests as maker", xy=(5.76, 81045), xytext=(5.4, 62000),
            fontsize=9, color=INK2, ha="center",
            arrowprops=dict(arrowstyle="->", color=INK3, lw=1.1))
ax.set_xlabel("Pullback-leg round-trip fee (bps) — trend leg held at 8.64 throughout")
ax.set_ylabel("Authorised gross notional ($)")
ax.set_title("The fee axis IS the sizing axis\nfee changes what trades KEEP, "
             "never which trades win — so this size costs no drawdown", pad=12)
ax.set_xlim(9.0, 3.4)
ax.set_ylim(0, 140000)
ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.grid(axis="y", zorder=0)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "edge_fig2_fee_axis.png"), dpi=140)
plt.close(fig)

# =====================================================================  FIG 3
# maker achievability: penetration-depth ECDF + the queue-risk zone
fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.6, 4.6))
dp = VM["attackA"]["depth_bps_p"]
qs = sorted(int(k) for k in dp)
axA.plot([dp[str(q)] if str(q) in dp else dp[q] for q in qs], qs,
         marker="o", ms=7, color=C1, mec=SURF, mew=1.5, zorder=3)
axA.axvspan(0, 2, color=C2, alpha=0.16, zorder=0)
axA.text(2.4, 40, "queue-risk zone\n(<2 bps penetration)\n1.2% of fills",
         fontsize=8.5, color=INK2, va="center")
axA.set_xscale("log")
axA.set_xticks([1, 2, 5, 10, 20, 50, 100])
axA.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
axA.get_xaxis().set_minor_formatter(matplotlib.ticker.NullFormatter())
axA.set_xlim(1, 100)
axA.set_xlabel("How far the next bar trades THROUGH the resting limit (bps, log)")
axA.set_ylabel("Percentile of filled signals")
axA.set_title("Fills are not marginal\nmedian penetration "
              f"{dp.get('50', dp.get(50)):.0f} bps = "
              f"{VM['attackA']['depth_ticks_p'].get('50', 0):,.0f} ticks")
axA.grid(zorder=0)

off = sorted(int(k) for k in VM["tighter_limit_tradeoff"])
fr = [VM["tighter_limit_tradeoff"][str(o)]["fill_rate"] * 100 for o in off]
eb = [VM["tighter_limit_tradeoff"][str(o)]["expected_price_edge_bps"] for o in off]
axB.plot(fr, eb, marker="o", ms=8, color=C1, mec=SURF, mew=1.5, zorder=3)
for o, x, yv in zip(off, fr, eb):
    axB.annotate(f"+{o} bps" if o else "at the close",
                 xy=(x, yv), xytext=(0, 9), textcoords="offset points",
                 ha="center", fontsize=8.5, color=INK2)
axB.axhline(2.88, color=INK3, lw=1.2, ls=":")
axB.text(38, 3.6, "the entire maker/taker fee saving = 2.88 bps", fontsize=8.5,
         color=INK2, ha="left")
axB.set_xlabel("Fill rate within one bar (%)  —  each point is one limit offset")
axB.set_ylabel("Expected price edge (bps)")
axB.set_title("The real trade-off, measured\nselection cost of the skipped "
              "trades is NOT priced here")
axB.set_xlim(30, 104)
axB.grid(zorder=0)
fig.suptitle("Edge-side lever 2: is maker execution achievable? "
             f"Measured fill rate {VM['claim1']['rate']*100:.2f}% "
             f"({VM['claim1']['penetrated']} of {VM['claim1']['signals_all_bars']} signals)",
             fontsize=11, fontweight="bold", y=1.005)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "edge_fig3_maker_achievable.png"), dpi=140,
            bbox_inches="tight")
plt.close(fig)

# =====================================================================  FIG 4
fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.8, 4.8))
cs = BC["cases"]
names = list(cs)
gr = [cs[n]["gross_usd_at_DD30"] for n in names]
o = np.argsort(gr)
axA.barh(np.arange(len(o)), [gr[i] for i in o], height=0.6,
         color=[C1 if "2 leg" in names[i] else C2 for i in o], zorder=3)
for j, i in enumerate(o):
    axA.text(gr[i] + 2200, j, f"${gr[i]:,.0f}", va="center", fontsize=9,
             color=INK, fontweight="bold")
axA.set_yticks(np.arange(len(o)))
axA.set_yticklabels([names[i].replace("  ", " ") for i in o], fontsize=9)
axA.set_xlim(0, max(gr) * 1.25)
axA.set_xlabel("Gross notional at the SAME DD budget: P(maxDD>30%) <= 10% over 2y")
axA.set_title(f"The second leg buys {BC['diversification_ratio']['mb60']:.2f}x gross\n"
              f"measured rho = {BC['rho_all_bars']:+.3f} on per-bar MTM streams")
axA.grid(axis="x", zorder=0)

Ns = [1, 2, 3, 4, 5, 6]
for (rk, col, lab) in ((f"{BC['rho_all_bars']:+.4f}", C1,
                        f"rho = {BC['rho_all_bars']:+.3f}  (MEASURED)"),
                       ("+0.0000", C3, "rho = 0  (textbook sqrt-N)"),
                       ("+0.2500", C2, "rho = +0.25")):
    row = BC["sqrtN_law"][rk]
    axB.plot(Ns, [row[str(n)] for n in Ns], marker="o", ms=7, color=col,
             mec=SURF, mew=1.5, label=lab, zorder=3)
axB.axhline(BC["diversification_ratio"]["mb60"], color=INK, lw=1.4, ls="-")
axB.text(6, BC["diversification_ratio"]["mb60"] + 0.12,
         f"what the 2nd leg ACTUALLY measured: "
         f"{BC['diversification_ratio']['mb60']:.2f}x", fontsize=8.5,
         color=INK, ha="right", fontweight="bold")
axB.set_xlabel("Number of equally-weighted legs")
axB.set_ylabel("Gross multiplier at constant portfolio vol")
axB.set_ylim(0.8, 4.6)
axB.set_title("The law over-promises vs the measurement\nthe law prices vol; "
              "the DD budget prices tails too")
axB.legend(frameon=False, fontsize=9, loc="upper left")
axB.grid(zorder=0)
fig.suptitle("Edge-side lever 3: diversification. Measured on real legs for "
             "N=2; N>=3 has NO strategy behind it", fontsize=11,
             fontweight="bold", y=1.005)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "edge_fig4_diversification.png"), dpi=140,
            bbox_inches="tight")
plt.close(fig)

# ================================================================== RANKING
base = gov["LIVE TODAY          entry taker, exit taker"]["authorised_gross_usd"]
RANK = [
    {"lever": "FIX 1 — make the entry actually rest (maker)",
     "extra_authorised_gross_usd": gov["FIX 1: maker entry  entry maker, exit taker"]["authorised_gross_usd"] - base,
     "implementation_risk": "LOWEST",
     "risk_evidence": (f"measured passive fill rate {VM['claim1']['rate']*100:.2f}% "
                       f"({VM['claim1']['penetrated']}/{VM['claim1']['signals_all_bars']}); "
                       f"only {VM['attackA']['frac_under_bps']['2']*100:.1f}% of fills "
                       f"penetrate <2bps; worst-case rate if EVERY marginal fill missed "
                       f"= {VM['attackA']['worst_case_fill_rate_if_all_sub2bp_miss']*100:.1f}%. "
                       "The backtest ALREADY cancels non-fills, so the selection cost "
                       "is already inside every published number. One code change in "
                       "hl.place_limit (do not re-send Gtc on Alo rejection; re-price "
                       "and rest)."),
     "change": "executor only; no strategy change; no rail change"},
    {"lever": "Rails: MAX_NOTIONAL_USD / SIZING_BASE_USD (NOT an edge lever)",
     "extra_authorised_gross_usd": None,
     "implementation_risk": "n/a — this is the binding constraint, not a lever",
     "risk_evidence": (f"even the UN-fixed edge authorises ${base:,.0f}, "
                       f"{base/LIVE:.1f}x the live ${LIVE:,.0f}. MAX_NOTIONAL_USD "
                       f"${MAXN:,.0f} clamps first. The edge side is not what holds "
                       "the book at $15,000."),
     "change": "config; out of scope for this study"},
    {"lever": "Charge the TREND leg its real fee (documentation defect, not a change)",
     "extra_authorised_gross_usd": "folded into every arm above",
     "implementation_risk": "NONE — it is a measurement correction",
     "risk_evidence": ("RESEARCH_FEES.md honesty box item 5: its S5/S6 rows charged "
                       "the donchian leg 12.0 bps while the venue charges 4.32. Every "
                       "arm here charges each leg its own real fee."),
     "change": "research only"},
    {"lever": "FIX 2 — rest the SIGNAL/TIME exits as maker (INCREMENTAL over FIX 1)",
     "extra_authorised_gross_usd": (
         gov["FIX 1+2 RISK-ADJUSTED (measured net exit gain, not nominal)"]["authorised_gross_usd"]
         - gov["FIX 1: maker entry  entry maker, exit taker"]["authorised_gross_usd"]),
     "note": ("nominal (un-risk-adjusted) incremental would be "
              f"+${gov['FIX 1+2: + maker SIGNAL exits (S3 only, measured)']['authorised_gross_usd'] - gov['FIX 1: maker entry  entry maker, exit taker']['authorised_gross_usd']:,.0f}; "
              "the risk-adjusted figure is the one to use"),
     "implementation_risk": "MEDIUM",
     "risk_evidence": (f"measured net {MER['TTL1']['net_bps']:+.2f} bps per exit, NOT "
                       f"the nominal +2.86: the passive exit gives up "
                       f"{-MER['TTL1']['mean_bps_all']:.2f} bps of PRICE because the "
                       "shipped exit at the next bar's open captures the momentum "
                       f"continuation. Price-effect sd is {MER['TTL1']['sd_bps_all']:.0f} "
                       "bps — an order of magnitude above the fee being saved, so the "
                       "sign of the mean is not established at n=124."),
     "change": "executor; changes WHEN you are flat, so it touches the strategy's risk"},
    {"lever": "VIP fee tier — a free consequence of scaling, not a lever",
     "extra_authorised_gross_usd": gov["VIP tier 1 ($5m/14d) on top of FIX 1+2"]["authorised_gross_usd"] - gov["FIX 1+2: + maker SIGNAL exits (S3 only, measured)"]["authorised_gross_usd"],
     "implementation_risk": "NONE, but it is CONDITIONAL on already being large",
     "risk_evidence": ("tier 1 needs $5m of 14-day notional. At 42.5 pullback + 28.6 "
                       "trend trades/yr that is ~2.7 round trips per 14 days, so it "
                       "needs ~$925k of gross per trade. It arrives only at Casey's "
                       "$1m target and cannot help him get there."),
     "change": "none; it happens on its own"},
    {"lever": "3rd uncorrelated leg",
     "extra_authorised_gross_usd": "NOT MEASURABLE — no third strategy exists",
     "implementation_risk": "HIGHEST",
     "risk_evidence": ("the simulated third leg is non-monotone in rho "
                       + ", ".join(f"rho {k}: {v['vs_2leg']:.2f}x"
                                   for k, v in BC["third_leg_simulated"].items())
                       + " — a non-monotone response IS the signature of noise, so "
                         "this measurement does not resolve the question. The 2-leg "
                         f"{BC['diversification_ratio']['mb60']:.2f}x IS measured and "
                         "block-robust; N>=3 is not."),
     "change": "a whole new validated strategy + a new leg in the executor"},
]
# MM maker rebate — priced and dismissed
RANK.append({
    "lever": "Hyperliquid NEGATIVE maker fee (MM rebate tiers)",
    "extra_authorised_gross_usd": 0.0,
    "implementation_risk": "NOT REACHABLE",
    "risk_evidence": ("fetched schedule: the mm tiers key on makerFractionCutoff = "
                      "the account's maker share of EXCHANGE volume. The lowest tier "
                      "is 0.5% and pays only -0.1 bp. Exchange volume in the fetched "
                      "dailyUserVlm is $3.2bn-$12.2bn/day, so 0.5% is $16m-$61m/day of "
                      "maker flow. This book does ~71 trades/yr. The rebate case is "
                      "priced at zero, not modelled optimistically."),
    "change": "none"})

print("=" * 92)
print("EDGE-SIDE LEVERS RANKED — extra AUTHORISED gross notional per unit of "
      "implementation risk")
print("=" * 92)
print(f"  baseline (today's un-fixed edge, governing window): ${base:,.0f} "
      f"authorised vs ${LIVE:,.0f} live")
for i, r in enumerate(RANK, 1):
    e = r["extra_authorised_gross_usd"]
    es = f"+${e:,.0f}" if isinstance(e, (int, float)) and e else str(e)
    print()
    print(f"  {i}. {r['lever']}")
    print(f"     extra authorised gross : {es}")
    print(f"     implementation risk    : {r['implementation_risk']}")
    print(f"     evidence               : {r['risk_evidence'][:400]}")
    print(f"     what changes           : {r['change']}")

json.dump({"baseline_authorised_gross_usd": base, "live_gross_usd": LIVE,
           "ranking": RANK,
           "charts": ["edge_fig1_authorised_notional.png",
                      "edge_fig2_fee_axis.png",
                      "edge_fig3_maker_achievable.png",
                      "edge_fig4_diversification.png"]},
          open(os.path.join(HERE, "edge_levers.json"), "w"), indent=1, default=str)
print()
print("charts -> edge_fig1..4 in " + HERE)
print("frozen -> " + os.path.join(HERE, "edge_levers.json"))
