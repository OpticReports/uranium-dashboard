"""CANDIDATE D charts. Palette per house rules."""
from __future__ import annotations
import json, math, os, statistics, csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURF = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda n: json.load(open(os.path.join(HERE, n)))

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK, "grid.color": GRID,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.grid": True, "grid.linewidth": 0.8, "axes.axisbelow": True,
})
usd = FuncFormatter(lambda v, p: f"${v/1000:,.0f}k" if abs(v) >= 1000 else f"${v:,.0f}")


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)


# ---------------------------------------------------------------- FIG 1
def fig1():
    ax_ = J("candD_fixaxis.json")
    arms = [a for a in ax_["arms"] if a["instrument"] == "spot_signal"]
    fk = J("candD_funding_kelly.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 6.6),
                                 gridspec_kw={"width_ratios": [1.15, 1]})

    labels = ["LIVE today\n(taker entry)", "FIX 1\nmaker entry",
              "CEILING\nboth maker\n(not achievable)"]
    vals = [a["authorised_gross_usd"] for a in arms]
    cols = [MUTED, BLUE, GRID]
    b = a1.bar(labels, vals, color=cols, edgecolor=INK, linewidth=0.9, width=.62)
    for r, v, a in zip(b, vals, arms):
        a1.text(r.get_x() + r.get_width()/2, v + 3000,
                f"${v:,.0f}\nrec_m {a['recommended_m']:.2f}",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    a1.axhline(15000, color=ORANGE, lw=2.2, ls="-")
    a1.text(2.52, 9200, "  live gross\n  $15,000", color=ORANGE, va="center",
            ha="left", fontsize=9.5, fontweight="bold")
    a1.axhline(20000, color=INK, lw=1.6, ls="--")
    a1.text(2.52, 27000, "  MAX_NOTIONAL_USD\n  $20,000 — THE RAIL", color=INK,
            va="center", ha="left", fontsize=9.5, fontweight="bold")
    a1.set_ylabel("authorised gross notional at $100,055 equity")
    a1.set_title("What fixing the entry buys — measured in PERP space, net of funding\n"
                 "(2024-07→2026-07, the window with basis data; in-sample)",
                 loc="left")
    a1.yaxis.set_major_formatter(usd)
    a1.set_ylim(0, 152000)
    a1.set_xlim(-0.6, 3.6)
    style(a1)
    a1.annotate("", xy=(1, vals[1]), xytext=(0, vals[0]),
                arrowprops=dict(arrowstyle="-|>", color=AQUA, lw=2.4,
                                connectionstyle="arc3,rad=-0.25"))
    a1.text(0.30, 112000, "×1.40\npaired-seed 12/12\nt = 63 on the p10", color=AQUA,
            ha="center", fontsize=10.5, fontweight="bold")

    # right: basis + funding haircut waterfall
    w = J("candD_perp_space.json")["result"]["bases"]
    names = ["SPOT\n(what the repo\npublishes)", "+ perp BASIS", "+ FUNDING"]
    v2 = [w["r_spot"]["authorised_gross_usd"], w["r_perp"]["authorised_gross_usd"],
          w["r_perp_fund"]["authorised_gross_usd"]]
    b2 = a2.bar(names, v2, color=[GRID, ORANGE, ORANGE], edgecolor=INK,
                linewidth=0.9, width=.58)
    for r, v in zip(b2, v2):
        a2.text(r.get_x()+r.get_width()/2, v+1200, f"${v:,.0f}", ha="center",
                fontsize=10.5, fontweight="bold")
    for i in (1, 2):
        a2.text(i, v2[i]/2, f"{(v2[i]/v2[0]-1)*100:+.0f}%", ha="center",
                color="white", fontsize=13, fontweight="bold")
    a2.set_ylabel("authorised gross notional")
    a2.set_title("The cost of measuring in the wrong space\n"
                 "trading a PERP off SPOT signals, same trades, same fees",
                 loc="left")
    a2.yaxis.set_major_formatter(usd)
    a2.set_ylim(0, max(v2)*1.25)
    style(a2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "candD_fig1_the_answer.png"), dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------- FIG 2
def fig2():
    bj = J("candD_basis.json")
    alo = J("candD_alo.json")
    rows = list(csv.DictReader(open(os.path.join(HERE, "candD_perp_4h.csv"))))
    b = [float(r["basis_close_bps"]) for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 6.0),
                                 gridspec_kw={"width_ratios": [1.25, 1]})
    a1.hist([x for x in b if -30 <= x <= 30], bins=90, color=BLUE,
            edgecolor="none", alpha=.85)
    a1.axvspan(-1.44, 1.44, color=AQUA, alpha=.28, zorder=0)
    a1.axvspan(-2.88, 2.88, color=AQUA, alpha=.14, zorder=0)
    a1.axvline(0, color=INK, lw=1.1)
    ymax = a1.get_ylim()[1]
    a1.text(0, ymax*0.97, "±2.88 bps = the ENTIRE prize\nfrom fixing the fee",
            ha="center", va="top", fontsize=9.5, fontweight="bold", color=INK)
    st = bj["basis_close_bps"]
    a1.annotate(f"p10 {st['p10']:.1f}", xy=(st["p10"], ymax*0.35),
                xytext=(st["p10"]-11, ymax*0.55), color=ORANGE, fontsize=9.5,
                fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.6))
    a1.annotate(f"p90 +{st['p90']:.1f}", xy=(st["p90"], ymax*0.35),
                xytext=(st["p90"]+3.5, ymax*0.55), color=ORANGE, fontsize=9.5,
                fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.6))
    a1.set_xlabel("Hyperliquid BTC perp close vs Bitstamp spot close, bps")
    a1.set_ylabel("4h bars")
    a1.set_title("Why post-only is rejected: the engine signals on SPOT, the "
                 "account trades a PERP\n"
                 f"basis median {st['median']:+.2f} bps, "
                 f"{st['frac_abs_gt_288']:.0%} of bars exceed the whole fee prize "
                 f"(n={bj['n_bars']:,} bars)", loc="left")
    a1.set_xlim(-30, 30)
    style(a1)

    secs = ["0", "20", "40", "60", "80"]
    cur = [alo["latency_model"][s]["expected_cross_rate"]*100 for s in secs]
    fix = [alo["fix_basis_translated"][s]["expected_cross_rate"]*100 for s in secs]
    x = range(len(secs))
    a2.plot(x, cur, "o-", color=ORANGE, lw=2.4, ms=7, label="today: limit at the SPOT close")
    a2.plot(x, fix, "s--", color=MUTED, lw=2.0, ms=6,
            label="basis-translated to the perp LAST price")
    a2.axhline(0.5, color=AQUA, lw=2.6)
    a2.text(0.08, 2.4, "Alo AT THE NEAR TOUCH: cannot cross by construction",
            color=AQUA, fontsize=9.5, fontweight="bold")
    a2.scatter([2], [100], marker="*", s=420, color=INK, zorder=5)
    a2.annotate("OBSERVED: 4 of 4 live entries crossed.\n"
                "The basis+latency model says 37% —\n"
                "p(4/4)=0.019. UNEXPLAINED → open question.",
                xy=(2, 100), xytext=(0.15, 74), fontsize=9.5, fontweight="bold",
                color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.7))
    a2.set_xticks(list(x)); a2.set_xticklabels([f"{s}s" for s in secs])
    a2.set_xlabel("latency from bar close to the order reaching the venue\n"
                  "(engine poll 60s + executor poll 20s)")
    a2.set_ylabel("expected post-only rejection rate, %")
    a2.set_title("Re-pricing to the touch is the fix;\n"
                 "basis-translation alone is NOT", loc="left")
    a2.set_ylim(-4, 108)
    a2.legend(frameon=False, fontsize=9, loc="center right")
    style(a2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "candD_fig2_mechanism.png"), dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------- FIG 3
def fig3():
    ax_ = J("candD_fixaxis.json")
    sw = [a for a in ax_["arms"] if a["instrument"] == "spot_signal_sweep"]
    live = [a for a in ax_["arms"]
            if a["instrument"] == "spot_signal" and a["label"].startswith("LIVE")][0]
    pen = [a["pullback_rt_bps"] - (1.44 + 4.32) for a in sw]
    val = [a["authorised_gross_usd"] for a in sw]
    fig, ax = plt.subplots(figsize=(10.4, 6.4))
    ax.plot(pen, val, "o-", color=BLUE, lw=2.8, ms=8, zorder=3)
    ax.axhline(live["authorised_gross_usd"], color=ORANGE, lw=2.2, ls="-")
    ax.text(6.05, live["authorised_gross_usd"], "  LIVE today\n  (do nothing)",
            color=ORANGE, va="center", fontsize=10, fontweight="bold")
    ax.axvline(2.88, color=INK, lw=1.8, ls="--")
    ax.fill_between([0, 2.88], 0, 100000, color=AQUA, alpha=.13, zorder=0)
    ax.fill_between([2.88, 6.3], 0, 100000, color=ORANGE, alpha=.11, zorder=0)
    ax.text(1.44, 36000, "FIX 1 WINS", ha="center", color=AQUA, fontsize=14,
            fontweight="bold")
    ax.text(4.55, 36000, "FIX 1 LOSES", ha="center", color=ORANGE, fontsize=14,
            fontweight="bold")
    ax.text(2.95, 90000, "break-even = 2.88 bps\n= exactly the taker/maker spread.\n"
            "A worse fill price and a higher fee\nenter the P&L through the SAME term,\n"
            "so there is no nonlinearity to find.",
            fontsize=9.5, va="top", fontweight="bold", color=INK)
    for p, v in zip(pen, val):
        ax.annotate(f"${v/1000:.0f}k", (p, v), textcoords="offset points",
                    xytext=(0, -17), ha="center", fontsize=8.6, color=MUTED)
    ax.set_xlabel("adverse selection actually suffered by the resting entry, bps per entry")
    ax.set_ylabel("authorised gross notional")
    ax.set_title("The one thing 4h bars CANNOT measure, stated as a tolerance\n"
                 "queue-level selection on a resting order — the fix is worth "
                 "doing iff it costs under 2.88 bps", loc="left")
    ax.yaxis.set_major_formatter(usd)
    ax.set_xlim(-0.25, 6.3); ax.set_ylim(25000, 100000)
    style(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "candD_fig3_adverse_selection.png"), dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------- FIG 4
def fig4():
    f = J("candD_funding.json"); fk = J("candD_funding_kelly.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 6.2),
                                 gridspec_kw={"width_ratios": [1, 1.05]})
    yrs = sorted(fk["funding_by_year"])
    v = [fk["funding_by_year"][y]["blend_pct_of_gross_per_year"] for y in yrs]
    cols = [ORANGE if x < 0 else AQUA for x in v]
    b = a1.bar(yrs, v, color=cols, edgecolor=INK, linewidth=0.9, width=.6)
    for r, x in zip(b, v):
        a1.text(r.get_x()+r.get_width()/2, x + (0.18 if x >= 0 else -0.18),
                f"{x:+.2f}%", ha="center", va="bottom" if x >= 0 else "top",
                fontsize=10.5, fontweight="bold")
    a1.axhline(0, color=INK, lw=1.2)
    a1.set_ylabel("blended funding, % of GROSS notional per year")
    a1.set_title("Funding is a REGIME, not a constant\n"
                 "the same book pays 5.7%/yr of gross in 2023 and EARNS 0.4% in 2026",
                 loc="left")
    a1.set_ylim(min(v)*1.45, max(max(v)*2.6, 1.4))
    style(a1)

    ns = ["15,000", "100,000", "1,000,000"]
    keys = ["15000", "100000", "1000000"]
    fund = [-f["at_notional"][k]["funding_usd_per_year"] for k in keys]
    fees = [-f["at_notional"][k]["fees_usd_per_year"] for k in keys]
    stress = [-f["at_notional"][k]["funding_all_long_worst_regime_usd_per_year"]
              for k in keys]
    x = range(3); w = .26
    a2.bar([i-w for i in x], fees, w, color=MUTED, edgecolor=INK, lw=.8,
           label="fees (8.64 bps round trip)")
    a2.bar([i for i in x], fund, w, color=ORANGE, edgecolor=INK, lw=.8,
           label="funding, as the book actually traded")
    a2.bar([i+w for i in x], stress, w, color=INK, edgecolor=INK, lw=.8,
           label="funding, ALL-LONG in the worst 90d regime (a bound)")
    a2.set_yscale("log")
    for i, (a, bb, c) in enumerate(zip(fees, fund, stress)):
        a2.text(i-w, a*1.13, f"${a:,.0f}", ha="center", fontsize=8.4, rotation=90)
        a2.text(i, bb*1.13, f"${bb:,.0f}", ha="center", fontsize=8.4, rotation=90)
        a2.text(i+w, c*1.13, f"${c:,.0f}", ha="center", fontsize=8.4, rotation=90)
    a2.set_xticks(list(x)); a2.set_xticklabels([f"${n}\ngross notional" for n in ns])
    a2.set_ylabel("cost per year, USD (log scale)")
    a2.set_title("Funding at size: 56% of the fee load, and it scales with\n"
                 "notional exactly like fees — a haircut, not a ceiling", loc="left")
    a2.set_ylim(100, max(stress)*9)
    a2.legend(frameon=False, fontsize=8.8, loc="upper left")
    style(a2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "candD_fig4_funding.png"), dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------- FIG 5
def fig5():
    h = J("candD_hybrid.json")["arms"]
    ag = J("candD_signal_agree.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(16.0, 7.6),
                                 gridspec_kw={"width_ratios": [1.35, 1]})
    order = list(h)
    vals = [h[k]["authorised_gross_usd"] for k in order]
    cols = [AQUA, ORANGE, ORANGE, ORANGE]
    base = ["spot price\n+ spot volume\nTHE LIVE CONFIG",
            "perp price\n+ perp volume",
            "perp price\n+ SPOT volume",
            "spot price\n+ PERP volume"]
    ticks = []
    for nm, k in zip(base, order):
        d = h[k]
        ticks.append(f"{nm}\n\nrec_m {d['recommended_m']:.2f}\n"
                     f"p10 {d['p10']:.2f}\nmean {d['mean_pct']}%\nn={d['n']}")
    b = a1.bar(range(4), vals, color=cols, edgecolor=INK, linewidth=1.0, width=.6)
    for r, v in zip(b, vals):
        a1.text(r.get_x()+r.get_width()/2, v+1800,
                f"${v:,.0f}" if v > 0 else "$0",
                ha="center", va="bottom", fontsize=11, fontweight="bold",
                color=INK if v > 0 else ORANGE)
    a1.text(2.33, 5200, "no authorised size on ANY perturbed series",
            ha="center", fontsize=10.5, fontweight="bold", color=ORANGE)
    a1.axhline(15000, color=INK, lw=1.6, ls="--")
    a1.text(3.44, 16500, "live $15,000", fontsize=9, fontweight="bold")
    a1.set_xticks(range(4))
    a1.set_xticklabels(ticks, fontsize=9)
    a1.set_ylabel("authorised gross notional (perp space, net of funding)")
    a1.set_title("THE BLOCKER: authorised size survives only on the exact\n"
                 "series the strategy was selected on", loc="left", fontsize=12.5)
    a1.yaxis.set_major_formatter(usd)
    a1.set_ylim(0, max(vals)*1.30)
    a1.set_xlim(-0.6, 3.9)
    style(a1)
    a1.text(0.02, 0.62,
            "4h close returns of the two price series\n"
            "correlate 0.9991. Swapping EITHER the price\n"
            "series or the volume series — even with n held\n"
            "at 145 — still takes the bootstrap p10 to zero.",
            transform=a1.transAxes, fontsize=9.6, color=INK,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=MUTED, lw=.9))

    names = ["pullback signal\nWITH volume filter\n(shipped)",
             "pullback signal\nWITHOUT volume filter",
             "donchian signal\n(pure price control)"]
    v = [ag["vol_filter_True"]["pullback"]["jaccard_agreement"]*100,
         ag["vol_filter_False"]["pullback"]["jaccard_agreement"]*100,
         ag["vol_filter_True"]["donchian_control"]["jaccard_agreement"]*100]
    bb = a2.barh(names, v, color=[ORANGE, BLUE, MUTED], edgecolor=INK,
                 linewidth=0.9, height=.52)
    for r, x in zip(bb, v):
        a2.text(x+1.5, r.get_y()+r.get_height()/2, f"{x:.1f}%", va="center",
                fontsize=13, fontweight="bold")
    a2.set_xlim(0, 116)
    a2.set_xlabel("share of bars where BOTH series fire the same signal\n"
                  "(intersection / union)")
    a2.set_title("Where the fragility lives: the volume filter", loc="left",
                 fontsize=12.5)
    a2.text(0.02, 0.06,
            "The price conditions transfer at 94% — the same\n"
            "as the pure-price control. The volume filter drops\n"
            "agreement to 69%, and removing it takes rec_m\n"
            "from 0.47 to 0.00 on spot bars. The edge is\n"
            "concentrated in the most venue-specific input.",
            transform=a2.transAxes, fontsize=9.6, color=INK,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=MUTED, lw=.9))
    a2.invert_yaxis()
    style(a2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "candD_fig5_robustness.png"), dpi=140)
    plt.close(fig)


for fn in (fig1, fig2, fig3, fig4, fig5):
    try:
        fn()
        print(f"{fn.__name__} ok")
    except Exception as e:
        print(f"{fn.__name__} FAILED: {type(e).__name__}: {e}")
