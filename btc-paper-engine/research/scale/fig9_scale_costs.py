"""fig9_scale_costs.png -- what actually costs money as the book scales to $1m.

Reads only measured outputs written by the other scripts in this directory:
  book_calm.json      fine-grained l2Book slip distribution (22 min, 3s)
  book_deep.json      coarse (nSigFigs=4) l2Book slip out to $20m
  funding_at_size.json signed funding on the strategy's own 90 trades
  funding_hl_btc.csv  HL BTC hourly funding history
  twap.json           slice benefit, replenishment, timing risk

Usage: python3 fig9_scale_costs.py <dir>
"""
from __future__ import annotations
import csv, datetime as dt, json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8983", "#e6e5e1"
SURF = "#fcfcfb"

calm = json.load(open(os.path.join(D, "book_calm.json")))
deep = json.load(open(os.path.join(D, "book_deep.json")))
fund = json.load(open(os.path.join(D, "funding_at_size.json")))
twap = json.load(open(os.path.join(D, "twap.json")))

plt.rcParams.update({"text.usetex": False, "mathtext.default": "regular",
                     "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "font.size": 10, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.edgecolor": GRID})
fig, axes = plt.subplots(2, 2, figsize=(17.5, 10.6), dpi=130)
fig.suptitle("Scaling BTC notional to $1m: what the exchange charges for size "
             "(all values measured 2026-09-28, Hyperliquid, read-only)",
             fontsize=13.5, fontweight="bold", y=0.985, color=INK)


def style(ax, title, sub=None):
    ax.set_title(title + ("\n" + sub if sub else ""), fontsize=11.5,
                 fontweight="bold", loc="left", color=INK, pad=9)
    ax.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


# ---------------- A: slip vs order size ----------------
ax = axes[0][0]
fine = [20_000, 100_000, 250_000, 500_000]   # $1m+ comes from the unbiased coarse probe
for side, col, mk in (("buy", S1, "o"), ("sell", S2, "s")):
    xs, p50, worst = [], [], []
    for t in fine:
        v = calm["slip"][f"{side}_{t}"]
        if v["p50"] is None:
            continue
        xs.append(t); p50.append(v["p50"]); worst.append(v["worst"])
    ax.plot(xs, p50, mk + "-", color=col, lw=2, ms=8, zorder=4,
            markeredgecolor=SURF, markeredgewidth=1.4,
            label=f"{side} — median of {calm['n_samples']} snapshots")
    ax.vlines(xs, p50, worst, color=col, lw=2, alpha=0.45, zorder=3)
    ax.plot(xs, worst, "_", color=col, ms=11, zorder=4)
    dxs, dp50, dworst = [], [], []
    for t in (1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000):
        v = deep["slip"][f"{side}_{t}"]
        if v["p50"] is None:
            continue
        dxs.append(t); dp50.append(v["p50"]); dworst.append(v["worst"])
    ax.plot(dxs, dp50, mk, color=col, lw=2, ms=8, mfc="none", mew=1.8, zorder=4,
            ls=":", label=f"{side} — coarse book (nSigFigs=4)")
    ax.vlines(dxs, dp50, dworst, color=col, lw=2, alpha=0.3, zorder=3)
ax.axhline(4.32, color=MUTED, lw=1.6, ls="--", zorder=2)
ax.text(1.02e6, 4.62, "taker fee 4.32 bp (one way)", color=MUTED, fontsize=8.5)
d1 = deep["slip"]["buy_1000000"]
ax.annotate(f"$1m buy: {d1['p50']:.2f} bp median, {d1['p90']:.2f} p90,\n"
            f"{d1['worst']:.2f} bp worst of {d1['n_complete']} samples\n"
            f"(single snapshot quoted 1.02 bp — near the BEST)",
            xy=(1e6, d1["worst"]), xytext=(2.05e4, 6.4), fontsize=8.5, color=INK,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2))
inc = calm["slip"]["buy_1000000"]
ax.annotate(f"thin-ask events: {inc['n_incomplete']} of {calm['n_samples']} snapshots\n"
            f"showed under $1m in the top 20 levels\n(min ${inc['worst_incomplete_filled_usd']:,.0f})",
            xy=(5e5, 0.16), xytext=(1.9e4, 0.105), fontsize=8, color=INK2,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("order notional (USD, log)"); ax.set_ylabel("slippage vs mid (bp, log)")
ax.xaxis.set_major_formatter(FuncFormatter(
    lambda v, _: f"${v/1e6:.0f}m" if v >= 1e6 else f"${v/1e3:.0f}k"))
ax.set_xticks(fine + [1e6, 2e6, 5e6, 1e7, 2e7])
ax.legend(frameon=False, fontsize=8, loc="lower right", ncol=1,
          handlelength=2.2, borderpad=0.2)
style(ax, "A. Impact stays under the taker fee out to \\$20m",
      f"but the distribution is 4x its median. Whiskers = worst single snapshot of "
      f"{calm['n_samples']}. Hollow = coarse book.")

# ---------------- B: every cost in bp per round trip ----------------
ax = axes[0][1]
hold_h = fund["trade_window"]["held_hours"] / fund["trade_window"]["n_trades"]
hot30 = fund["funding_history"]["rolling_30d_annualized_pct"]["max"]
fund_hot = hot30 / 100 * hold_h / 8760 * 1e4
items = [
    ("Taker fees (measured round trip)", fund["fee_load"]["round_trip_bp"], S2, "fee"),
    ("Funding — signed, the book's own 90 trades",
     abs(fund["funding_cost_bases"]["3_signed_actual_trades"]["bp_per_round_trip_equivalent"]), S4, "funding"),
    ("Funding — if every trade were long (same holds)",
     abs(fund["funding_cost_bases"]["2_always_long_only_while_held"]["bp_per_round_trip_equivalent"]), S4, "funding"),
    (f"Funding — all long, hottest 30d regime on record ({hot30:.0f}%/yr)",
     fund_hot, S4, "funding"),
    ("Market impact, \\$100k round trip",
     2 * calm["slip"]["buy_100000"]["p50"], S1, "impact"),
    ("Market impact, \\$1m round trip (median)",
     2 * deep["slip"]["buy_1000000"]["p50"], S1, "impact"),
    ("Market impact, \\$1m round trip (worst of 160)",
     2 * deep["slip"]["buy_1000000"]["worst"], S1, "impact"),
    ("Market impact, \\$10m round trip (median)",
     2 * deep["slip"]["buy_10000000"]["p50"], S1, "impact"),
]
ys = range(len(items))[::-1]
seen = set()
for y, (lab, val, col, fam) in zip(ys, items):
    ax.barh(y, val, color=col, height=0.62, zorder=3,
            label=fam if fam not in seen else None, edgecolor=SURF, lw=2)
    seen.add(fam)
    ax.text(val * 1.08, y, f"{val:.2f} bp", va="center", fontsize=9.5,
            color=INK, fontweight="bold")
ax.set_yticks(list(ys)); ax.set_yticklabels([i[0] for i in items], fontsize=9)
ax.set_xscale("log"); ax.set_xlim(0.02, 200)
ax.set_xlabel("cost per round trip (bp of notional, log)")
ax.legend(frameon=False, fontsize=9, loc="lower right", title="cost family",
          title_fontsize=9)
style(ax, "B. Size is the cheapest line item",
      f"the funding REGIME is the expensive one ({hold_h:.0f} h mean hold)")

# ---------------- C: TWAP -- what splitting saves vs what waiting risks ----
ax = axes[1][0]
best = twap["E_twap_1m_explicit"]["max_slip_saving_available_bp"]
h = twap["C_timing_risk"]["horizons"]
bars = [("slip saved by\nslicing \\$1m", best, S3),
        ("σ of BTC over\n1 min", h["1min"]["sigma_bp"], S2),
        ("σ over 5 min\n(4 x \\$250k)", h["5min"]["sigma_bp"], S2),
        ("σ over 30 min\n(10 x \\$100k, spaced)", h["30min"]["sigma_bp"], S2),
        ("p99 |move|\nover 30 min", h["30min"]["p99_abs_bp"], S2)]
for i, (lab, v, col) in enumerate(bars):
    ax.bar(i, v, color=col, width=0.62, zorder=3, edgecolor=SURF, lw=2,
           label=("what splitting SAVES" if i == 0 else
                  ("what the DELAY risks" if i == 1 else None)))
    ax.text(i, v * 1.13, f"{v:.1f} bp\n(\\${v/1e4*1e6:,.0f} on \\$1m)", ha="center",
            fontsize=9, color=INK, fontweight="bold")
ax.set_xticks(range(len(bars))); ax.set_xticklabels([b[0] for b in bars], fontsize=9)
ax.set_yscale("log"); ax.set_ylim(0.1, 400)
ax.set_ylabel("bp of the \\$1m order (log)")
ax.legend(frameon=False, fontsize=9, loc="upper left")
style(ax, "C. TWAP buys 1 bp of slip with 10-20 bp of timing risk",
      f"break-even execution window {twap['D_breakeven'].get('buy 10x100,000', {}).get('breakeven_window_s', float('nan')):.1f} s "
      f"— shorter than one slice. 1m vol from {twap['C_timing_risk']['n_1m_candles']} HL 1m candles.")

# ---------------- D: the funding regime, which is the real variable ----------
ax = axes[1][1]
ts, rates = [], []
with open(os.path.join(D, "funding_hl_btc.csv")) as f:
    for a, b in csv.reader(f):
        if a == "ts_ms":
            continue
        ts.append(int(a)); rates.append(float(b))
w = 30 * 24
xs = [dt.datetime.utcfromtimestamp(ts[i + w] / 1000) for i in range(0, len(ts) - w, 24)]
ys = [sum(rates[i:i + w]) / w * 24 * 365 * 100 for i in range(0, len(ts) - w, 24)]
ax.plot(xs, ys, color=S1, lw=2, zorder=4)
ax.fill_between(xs, 0, ys, color=S1, alpha=0.10, zorder=2)
ax.axhline(8, color=S3, lw=1.5, ls="--", zorder=3)
ax.text(xs[2], 8.6, "8%/yr — RESEARCH_CARRY ARM level", color=S3, fontsize=9)
ax.axhline(0, color=MUTED, lw=1)
t0 = dt.datetime.fromisoformat(fund["trade_window"]["first_entry"]).replace(tzinfo=None)
t1 = dt.datetime.fromisoformat(fund["trade_window"]["last_exit"]).replace(tzinfo=None)
ax.axvspan(t0, t1, color=MUTED, alpha=0.10, zorder=1)
ax.text(t0, max(ys) * 0.93, " backtest trade window\n (mean %.1f%%/yr)"
        % fund["trade_window"]["mean_annualized_funding_pct_in_window"],
        fontsize=9, color=INK2, va="top")
ax.annotate(f"now {ys[-1]:.1f}%/yr", xy=(xs[-1], ys[-1]),
            xytext=(xs[-1], max(ys) * 0.62), ha="right", fontsize=9.5, color=INK,
            fontweight="bold", arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2))
ax.set_ylabel("30d trailing mean funding, annualized (%)")
import matplotlib.dates as mdates
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
style(ax, "D. Funding is a regime, not a size problem",
      "46 short / 44 long nets ~0 — a cancellation, not a hedge")

fig.tight_layout(rect=(0, 0.012, 1, 0.965))
fig.text(0.006, 0.004,
         "Measured read-only from Hyperliquid public info endpoints; no orders placed. "
         "Sampling window sat at the 83rd percentile of 10-day 1-minute volatility - "
         "busier than most minutes, but still NOT a stressed book (see stress.json). "
         "In-sample: funding priced on the 90-trade pullback reference, 2024-07..2026-07.",
         fontsize=8, color=MUTED)
out = os.path.join(D, "fig9_scale_costs.png")
fig.savefig(out, facecolor=SURF)
print("wrote", out)
