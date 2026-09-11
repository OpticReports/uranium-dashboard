import glob, io, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad"
OUT = os.path.join(SC, "tlt_study")
BLUE, ORANGE, RED = "#2a78d6", "#eb6834", "#e34948"
INK, MUTED, GRID = "#1f2430", "#6b7280", "#e5e7eb"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "font.size": 10,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})

rows = []
for f in sorted(glob.glob(f"{SC}/fin20*.json")):
    if os.path.getsize(f) == 0: continue
    try:
        rows.extend(json.load(open(f)))
    except Exception:
        pass
df26 = pd.read_csv(f"{SC}/fin2026.json")
si = pd.DataFrame(rows)[["settlementDate", "currentShortPositionQuantity"]]
si26 = df26[["settlementDate", "currentShortPositionQuantity"]]
si = pd.concat([si, si26]).drop_duplicates("settlementDate")
si["settlementDate"] = pd.to_datetime(si["settlementDate"])
si = si.sort_values("settlementDate").set_index("settlementDate")["currentShortPositionQuantity"] / 1e6

fig, ax = plt.subplots(figsize=(10.5, 4.8))
ax.plot(si.index, si.values, color=BLUE, lw=1.8, marker="o", ms=3,
        markerfacecolor="white", markeredgecolor=BLUE, markeredgewidth=0.8)
ax.set_ylabel("TLT shares sold short (millions) — FINRA bi-monthly")
ax.set_title("The verified record: the 150.5M peak was Dec 2025 — shorts have covered 37% since",
             fontsize=12, loc="left", color=INK, pad=10)
pk = si.idxmax()
ax.annotate(f"peak 150.5M\nDec 15 2025 settlement", xy=(pk, si.max()),
            xytext=(pk - pd.Timedelta(days=800), si.max() - 12), fontsize=9,
            color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
last = si.index[-1]
ax.annotate(f"now {si.iloc[-1]:.0f}M ({last.date()})\n≈17-19% of shares out, DTC 3.6",
            xy=(last, si.iloc[-1]), xytext=(pd.Timestamp("2022-07-01"), 118),
            fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
# the tweet's false 2022 shape
ax.annotate('tweet chart showed "~60M, 2022 inflation peak" —\nFINRA max in 2022 was 34.3M',
            xy=(pd.Timestamp("2022-01-14"), 34.3),
            xytext=(pd.Timestamp("2018-03-01"), 62), fontsize=9, color=RED,
            arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
ax.axhspan(0, 0.1, color="white")  # noop keeps autoscale sane
ax.set_ylim(0, 165)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(f"{OUT}/fig4_verified_si.png", dpi=160)
print("rows", len(si), "range", si.index.min().date(), si.index.max().date(),
      "peak", si.max(), "last", si.iloc[-1])
