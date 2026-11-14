"""Read-only explainer: BTC 4h price vs the S4 trailing stop actually resting on
Hyperliquid since the 2026-11-10 entry. Needs matplotlib. Writes s4_trail_<date>.png here."""
import json, time, urllib.request, calendar
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone

ADDR = "0xAb533E69e77881D89D0357166851C9653bC551e2"
def info(body):
    req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())

ENTRY_MS = calendar.timegm((2026, 11, 10, 14, 59, 57)) * 1000
start = calendar.timegm((2026, 11, 8, 0, 0, 0)) * 1000
now = int(time.time() * 1000)
c = info({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "4h", "startTime": start, "endTime": now}})
ct = [datetime.fromtimestamp(x["t"] / 1000, timezone.utc) for x in c]
hi = [float(x["h"]) for x in c]; lo = [float(x["l"]) for x in c]; cl = [float(x["c"]) for x in c]
mid = float(info({"type": "allMids"})["BTC"])

ho = info({"type": "historicalOrders", "user": ADDR})
stops = {}
for r in ho:
    o = r.get("order", {})
    if o.get("coin") != "BTC" or o.get("orderType") != "Stop Market" or o.get("timestamp", 0) < ENTRY_MS - 60000:
        continue
    stops[o["cloid"] if o.get("cloid") else o["oid"]] = (o["timestamp"], float(o["triggerPx"]))
path = sorted(stops.values())
# collapse the re-placed duplicate at the same level (11-14 04:01 retry)
steps = []
for t, px in path:
    if steps and steps[-1][1] == px:
        continue
    steps.append((t, px))
sx = [datetime.fromtimestamp(t / 1000, timezone.utc) for t, _ in steps] + [datetime.fromtimestamp(now / 1000, timezone.utc)]
sy = [px for _, px in steps] + [steps[-1][1]]

ENTRY, QTY = 74375.0, 0.45387
INK, INK2, SURF, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"

fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
# 4h range as a thin band, close as the line
ax.vlines(ct, lo, hi, color=BLUE, alpha=0.28, linewidth=2.2, zorder=1)
ax.plot(ct, cl, color=BLUE, linewidth=2, zorder=3, label="BTC, 4h close (bars = 4h high-low)")
ax.step(sx, sy, where="post", color=ORANGE, linewidth=2, zorder=4, label="Trailing stop (resting buy-stop on Hyperliquid)")
ax.hlines(ENTRY, ct[0], sx[-1], color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
ax.axvline(datetime.fromtimestamp(ENTRY_MS / 1000, timezone.utc), color=GRID, linewidth=1, zorder=0)

x_end = sx[-1]
ax.annotate(f"Entry {ENTRY:,.0f}", xy=(x_end, ENTRY), xytext=(6, -3), textcoords="offset points",
            color=INK2, fontsize=9)
ax.annotate(f"Stop {sy[-1]:,.0f}", xy=(x_end, sy[-1]), xytext=(6, -3), textcoords="offset points",
            color=INK, fontsize=9, fontweight="bold")
ax.annotate(f"Now {mid:,.0f}", xy=(x_end, mid), xytext=(6, -3), textcoords="offset points",
            color=INK, fontsize=9, fontweight="bold")
ax.plot([x_end], [mid], marker="o", markersize=5, color=BLUE, markeredgecolor=SURF, markeredgewidth=1.5, zorder=5)

first_below = next((t for t, px in steps if px < ENTRY), None)
if first_below:
    fb = datetime.fromtimestamp(first_below / 1000, timezone.utc)
    ax.annotate("Stop crosses below entry:\nfrom here a stop-out is a profit",
                xy=(fb, sy[[t for t, _ in steps].index(first_below)] + 40),
                xytext=(datetime(2026, 11, 13, 14, tzinfo=timezone.utc), 76700), textcoords="data",
                color=INK2, fontsize=8.5, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.annotate("Joined the engine's short\n11-10 15:00Z", xy=(datetime.fromtimestamp(ENTRY_MS / 1000, timezone.utc), max(hi) - 300),
            xytext=(6, 0), textcoords="offset points", color=INK2, fontsize=8.5, va="top")

locked = (ENTRY - sy[-1]) * QTY
unreal = (ENTRY - mid) * QTY
ax.set_title("No take-profit: the trend leg's only exit is a stop that follows price down",
             loc="left", fontsize=12.5, color=INK, fontweight="bold", pad=22)
ax.text(0, 1.02, f"Stop = 4h close + 5 x ATR(14); it moves down each 4h bar, never up.   "
        f"Short 0.454 BTC.  Open profit \\${unreal:,.0f}  |  locked in if the stop fills \\${locked:,.0f} (before fees)",
        transform=ax.transAxes, fontsize=9, color=INK2)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.xaxis.set_major_locator(mdates.DayLocator())
for s in ("top", "right"): ax.spines[s].set_visible(False)
for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
ax.tick_params(colors=INK2, labelsize=9, length=0)
ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.set_xlim(ct[0], x_end + (x_end - ct[0]) * 0.09)
leg = ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK2)
fig.tight_layout()
import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), time.strftime("s4_trail_%Y-%m-%d.png", time.gmtime()))
fig.savefig(out, facecolor=SURF)
print("saved", out, "| steps", [(datetime.fromtimestamp(t/1000, timezone.utc).strftime('%m-%d %H:%M'), px) for t, px in steps], "| mid", mid, "| unreal", round(unreal), "| locked", round(locked))
