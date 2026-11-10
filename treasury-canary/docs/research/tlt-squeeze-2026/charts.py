"""Study figures. Palette: dataviz reference categorical (validated order),
light mode. Line marks 2px, recessive grid, direct labels, no dual axes —
stacked shared-x panels instead."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
OUT = os.path.dirname(__file__)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
VIOLET, RED = "#4a3aa7", "#e34948"
INK, MUTED, GRID = "#1f2430", "#6b7280", "#e5e7eb"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True,
    "font.size": 10, "text.color": INK, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
})

tlt = pd.read_csv(f"{DATA}/TLT.csv", parse_dates=["date"]).set_index("date")["close"]
dgs30 = pd.read_csv(f"{DATA}/DGS30.csv", parse_dates=["date"]).set_index("date")["DGS30"].dropna()
leg = pd.read_csv(f"{DATA}/legacy_cot.csv"); leg["date"] = pd.to_datetime(leg["report_date_as_yyyy_mm_dd"])
tff = pd.read_csv(f"{DATA}/tff.csv"); tff["date"] = pd.to_datetime(tff["report_date_as_yyyy_mm_dd"])
for df, cols in ((leg, ["noncomm_positions_long_all","noncomm_positions_short_all","open_interest_all"]),
                 (tff, ["lev_money_positions_long","lev_money_positions_short",
                        "asset_mgr_positions_long","asset_mgr_positions_short","open_interest_all"])):
    for c in cols: df[c] = pd.to_numeric(df[c], errors="coerce")

def agg(df, mkts, lc, sc):
    d = df[df["contract_market_name"].isin(mkts)]
    g = d.groupby("date").agg(long=(lc,"sum"), short=(sc,"sum"), oi=("open_interest_all","sum"))
    g["net_pct_oi"] = 100.0*(g["long"]-g["short"])/g["oi"]
    return g.sort_index()

ALL_UST = ["UST BOND","ULTRA UST BOND","UST 10Y NOTE","ULTRA UST 10Y"]
lev = agg(tff, ALL_UST, "lev_money_positions_long","lev_money_positions_short")
am  = agg(tff, ALL_UST, "asset_mgr_positions_long","asset_mgr_positions_short")

# ── FIG 1: the tape vs the positioning, 2006-2026 ───────────────────────────
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10.5, 6.4), sharex=True,
                             gridspec_kw={"height_ratios": [1.15, 1]})
t = tlt[tlt.index >= "2006-01-01"]
a1.plot(t.index, t.values, color=BLUE, lw=1.6)
a1.set_ylabel("TLT close ($)")
lo = t.idxmin()
a1.annotate(f"22-yr low {t.min():.0f}\nAug 17 2026", xy=(lo, t.min()),
            xytext=(lo - pd.Timedelta(days=2200), t.min() + 4),
            fontsize=9, color=INK,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
pk = t.idxmax()
a1.annotate(f"COVID peak {t.max():.0f}", xy=(pk, t.max()),
            xytext=(pk + pd.Timedelta(days=250), t.max() - 6), fontsize=9, color=MUTED)
a1.set_title("TLT vs Treasury-futures positioning — the 'record short' is two mirrored books",
             fontsize=12, loc="left", color=INK, pad=10)

a2.plot(lev.index, lev["net_pct_oi"], color=ORANGE, lw=1.6)
a2.plot(am.index,  am["net_pct_oi"],  color=AQUA, lw=1.6)
a2.axhline(0, color=MUTED, lw=0.8)
a2.set_ylabel("net position, % of OI")
a2.text(pd.Timestamp("2013-06-01"), -33, "Leveraged funds (short leg of basis trade)",
        color=ORANGE, fontsize=9)
a2.text(pd.Timestamp("2013-06-01"), 34, "Asset managers (long leg)", color=AQUA, fontsize=9)
last = lev.index[-1]
a2.annotate(f"{lev['net_pct_oi'].iloc[-1]:+.0f}% (5th pctile)", xy=(last, lev["net_pct_oi"].iloc[-1]),
            xytext=(last - pd.Timedelta(days=1500), -44), fontsize=9, color=ORANGE,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
a2.annotate(f"{am['net_pct_oi'].iloc[-1]:+.0f}% (99th pctile)", xy=(last, am["net_pct_oi"].iloc[-1]),
            xytext=(last - pd.Timedelta(days=1500), 46), fontsize=9, color=AQUA,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
a2.set_ylim(-52, 55)
a2.xaxis.set_major_locator(mdates.YearLocator(2))
a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(f"{OUT}/fig1_tape_vs_positioning.png", dpi=160)
plt.close(fig)

# ── FIG 2: 2023 anatomy — the squeeze that wasn't a squeeze ─────────────────
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10.5, 6.0), sharex=True,
                             gridspec_kw={"height_ratios": [1.15, 1]})
w0, w1 = pd.Timestamp("2023-08-01"), pd.Timestamp("2024-03-01")
t = tlt[(tlt.index >= w0) & (tlt.index <= w1)]
a1.plot(t.index, t.values, color=BLUE, lw=1.8)
a1.set_ylabel("TLT close ($)")
a1.set_title("Nov–Dec 2023: TLT +19% with almost no short-covering in futures positioning",
             fontsize=12, loc="left", color=INK, pad=10)
events = [("2023-11-01", "QRA: issuance\nshifts to bills", 0.2),
          ("2023-11-14", "soft Oct CPI", 3.6),
          ("2023-12-13", "Powell pivot", 0.2)]
for d, lab, dy in events:
    d = pd.Timestamp(d)
    for ax in (a1, a2):
        ax.axvline(d, color=MUTED, lw=0.8, ls=":")
    a1.text(d + pd.Timedelta(days=1.5), t.min() + dy, lab, fontsize=8.5,
            color=INK, va="bottom")
l = lev[(lev.index >= w0) & (lev.index <= w1)]
a2.plot(l.index, l["net_pct_oi"], color=ORANGE, lw=1.8, marker="o", ms=4,
        markerfacecolor="white", markeredgecolor=ORANGE)
a2.set_ylabel("lev-fund net, % of OI")
a2.set_ylim(-32, -24)
a2.text(pd.Timestamp("2023-08-05"), -24.6,
        "peak covering during the +19% rally: -28.7 → -26.9 %OI (Nov 21) —\n"
        "≈6% of the net short book — and back to -28.1 by Dec 26",
        fontsize=9, color=ORANGE)
a2.xaxis.set_major_locator(mdates.MonthLocator())
a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
fig.tight_layout()
fig.savefig(f"{OUT}/fig2_2023_anatomy.png", dpi=160)
plt.close(fig)

# ── FIG 3: what 80bp+ 3m yield drops were made of + conditional rates ───────
episodes = [  # (label, driver) driver: pivot/recession-flight/supply-policy
    ("1986 oil bust", "Macro: disinflation"), ("1987 crash", "Macro: flight"),
    ("1989 slowdown", "Macro: Fed pivot"), ("1990 recession", "Macro: recession"),
    ("1992-93 easing", "Macro: Fed pivot"), ("1993 rally", "Macro: disinflation"),
    ("1995 soft landing", "Macro: Fed pivot"), ("1996 slowdown", "Macro: disinflation"),
    ("1998 LTCM", "Macro: flight (+unwind amplifier)"),
    ("2000 dot-com", "Macro: recession"), ("2001 easing", "Macro: recession"),
    ("2002 crisis", "Macro: flight"), ("2003 deflation scare", "Macro: Fed"),
    ("2008 GFC", "Macro: flight (+QE1)"), ("2010 QE2", "Policy: Fed"),
    ("2011 debt ceiling/EU", "Macro: flight (+Twist)"),
    ("2012 EU crisis", "Macro: flight"), ("2014 oil crash", "Macro (+flash-rally liquidity)"),
    ("2019 trade war", "Macro: Fed pivot (+covering)"),
    ("2019-12 pre-COVID", "Macro: flight"), ("2022-10 pivot hope", "Macro (+UK LDI unwind)"),
    ("2023-10 QRA+CPI+pivot", "Policy+macro (+covering)"),
]
purely_positioning = 0
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.6),
                             gridspec_kw={"width_ratios": [1.15, 1], "wspace": 0.42})
cats = {"Macro trigger (recession, flight, Fed pivot)": 0,
        "Policy trigger (QE, QRA supply shift)": 0,
        "Positioning amplified the move": 0,
        "Positioning was the sole cause": 0}
for _, drv in episodes:
    if drv.startswith("Policy"): cats["Policy trigger (QE, QRA supply shift)"] += 1
    else: cats["Macro trigger (recession, flight, Fed pivot)"] += 1
    if "unwind" in drv or "covering" in drv or "liquidity" in drv or "LDI" in drv:
        cats["Positioning amplified the move"] += 1
names = list(cats); vals = [cats[k] for k in names]
colors = [BLUE, VIOLET, ORANGE, RED]
bars = a1.barh(range(len(names))[::-1], vals, color=colors, height=0.55)
for i, (n, v) in enumerate(zip(names, vals)):
    a1.text(v + 0.3, len(names) - 1 - i, str(v), va="center", color=INK, fontsize=10)
a1.set_yticks(range(len(names))[::-1]); a1.set_yticklabels(names, fontsize=9)
a1.set_xlim(0, 24); a1.set_xlabel("episodes (n=22, all ≥80bp/3m 30-yr drops since 1986)")
a1.set_title("Big rallies: what drove them",
             fontsize=11.5, loc="left", color=INK, pad=10)

# conditional probabilities
labels = ["any week\n(base rate)", "crowded-short week\n(bottom decile)"]
p50 = [38.3, 42.2]; p100 = [8.7, 13.8]
x = np.arange(2); w = 0.34
b1 = a2.bar(x - w/2, p50, w, color=BLUE, label="30y falls ≥50bp at 6-mo best")
b2 = a2.bar(x + w/2, p100, w, color=ORANGE, label="30y falls ≥100bp at 6-mo best")
for bars_ in (b1, b2):
    for b in bars_:
        a2.text(b.get_x() + b.get_width()/2, b.get_height() + 0.8,
                f"{b.get_height():.0f}%", ha="center", fontsize=10, color=INK)
a2.set_xticks(x); a2.set_xticklabels(labels, fontsize=9.5)
a2.set_ylabel("probability (%)"); a2.set_ylim(0, 55)
a2.legend(frameon=False, fontsize=9, loc="upper left")
a2.set_title("Crowded shorts: mild amplifier",
             fontsize=11.5, loc="left", color=INK, pad=10)
fig.tight_layout()
fig.savefig(f"{OUT}/fig3_drivers_and_rates.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("figs written")
