"""Where the open S4 trade actually exits (research/s4_trail_exit.png).

There is no take profit. `_process_donchian`'s docstring: "exit ONLY via a
ratcheting chandelier trail (cfg.trail_atr x rolling ATR)" — its single
_close_position call carries reason STOP, and there is no time stop or signal
exit on this book. This reconstructs the trail from Hyperliquid 4h bars using
the engine's own rule, trail = max over bars of (close - 5 x ATR14), and
prices what the ratchet has actually locked in.
usage: python3 research/s4_trail_exit.py <btc4h.json> <out.png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

cpath, out = sys.argv[1], sys.argv[2]
bars = sorted(json.load(open(cpath)), key=lambda b: b["t"])

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

ENTRY_TS = 1789747200          # 2026-09-18 16:00Z, SECONDS
ENTRY_MS = ENTRY_TS * 1000     # bar["t"] is MILLISECONDS - comparing the
#                                two directly let every pre-entry bar through
ENTRY = 80_757.0               # venue fill
QTY = 0.03134
TRAIL_ATR = 5.0                # BookCfg.trail_atr for S4
LIVE_TRAIL = 80_817.81         # engine, after the 12:00Z bar
MID = 85_892.0
FEE_BPS = 8.64                 # measured round trip

tr, atr, atrs = [], None, {}
for i in range(1, len(bars)):
    p, x = bars[i - 1]["c"], bars[i]
    tr.append(max(x["h"] - x["l"], abs(x["h"] - p), abs(x["l"] - p)))
    if len(tr) == 14:
        atr = sum(tr) / 14
    elif len(tr) > 14:
        atr = (atr * 13 + tr[-1]) / 14
    if atr:
        atrs[x["t"]] = atr

held = [b for b in bars if b["t"] >= ENTRY_MS and b["t"] in atrs]
hrs, px, trail = [], [], []
run = None
for b in held:
    cand = b["c"] - TRAIL_ATR * atrs[b["t"]]
    run = cand if run is None else max(run, cand)
    hrs.append((b["t"] / 1000 - ENTRY_TS) / 3600)
    px.append(b["c"])
    trail.append(run)

fig, (a, b) = plt.subplots(1, 2, figsize=(14.8, 6.0), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1.85, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: price, the ratchet, and the give-back zone --------------------------
a.grid(color=GRID, lw=0.8)
a.fill_between(hrs, px, trail, color=ORANGE, alpha=0.13, zorder=1)
a.plot(hrs, px, color=INK, lw=2.0, zorder=5, label="BTC 4h close")
a.step(hrs, trail, where="post", color=AQUA, lw=2.2, zorder=4,
       label="chandelier trail (close - 5 x ATR14), ratchets UP only")
a.axhline(ENTRY, color=BLUE, ls="--", lw=1.4, zorder=3)
a.text(0.5, ENTRY + 180, f"entry {ENTRY:,.0f}", color=BLUE, fontsize=8.8)
a.plot([hrs[-1]], [MID], "o", color=INK, ms=9, zorder=6)
a.annotate(f"mark {MID:,.0f}\n+${(MID-ENTRY)*QTY:,.0f} unrealized",
           xy=(hrs[-1], MID), xytext=(hrs[-1] - 34, MID - 900),
           color=INK, fontsize=9, fontweight="bold",
           arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))
a.plot([hrs[-1]], [LIVE_TRAIL], "o", color=AQUA, ms=9, zorder=6)
a.annotate(f"trail {LIVE_TRAIL:,.0f}\njust crossed ABOVE entry",
           xy=(hrs[-1], LIVE_TRAIL), xytext=(hrs[-1] - 40, LIVE_TRAIL - 1400),
           color=AQUA, fontsize=9, fontweight="bold",
           arrowprops=dict(arrowstyle="->", color=AQUA, lw=1.2))
a.text(hrs[len(hrs) // 2], (MID + LIVE_TRAIL) / 2,
       "EVERYTHING IN HERE IS\nGIVE-BACK RISK\n"
       f"${(MID - LIVE_TRAIL) * QTY:,.0f}", color=ORANGE, fontsize=10,
       ha="center", va="center", fontweight="bold")
a.set_xlabel("hours since entry (2026-09-18 16:00Z)", color=SEC, fontsize=9.5)
a.set_ylabel("BTC", color=SEC, fontsize=9.5)
a.set_title("There is no take profit — the trail IS the exit", color=INK,
            fontsize=12, fontweight="bold", loc="left")
a.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper left")

# --- B: what each outcome is actually worth ---------------------------------
b.grid(axis="y", color=GRID, lw=0.8)
def net(exit_px):
    return QTY * (exit_px - ENTRY) - QTY * exit_px * FEE_BPS / 10_000.0
scen = [("stopped at\nthe trail\nnow", LIVE_TRAIL, AQUA),
        ("mark today\n(if it kept\nrunning)", MID, INK),
        ("trail at\n90,000", 90_000 - TRAIL_ATR * 1004, MUTED),
        ("trail at\n95,000", 95_000 - TRAIL_ATR * 1004, MUTED)]
vals = [net(p) for _, p, _ in scen]
cols = [c for _, _, c in scen]
bb = b.bar(range(len(scen)), vals, 0.58, color=cols, zorder=3)
bb[1].set_alpha(0.35)
b.axhline(0, color=AX, lw=1.2, zorder=4)
for i, v in enumerate(vals):
    b.text(i, v + (4 if v >= 0 else -9), f"${v:+,.0f}", ha="center",
           color=INK, fontsize=10, fontweight="bold")
b.set_xticks(range(len(scen)))
b.set_xticklabels([s for s, _, _ in scen], fontsize=8.4, color=SEC)
b.set_ylabel(f"net USD on {QTY} BTC, after {FEE_BPS} bps", color=SEC,
             fontsize=9.2)
b.set_title("The trail locks in ~break-even, not $161", color=INK,
            fontsize=12, fontweight="bold", loc="left")
b.text(0.5, max(vals) * 0.62, "a trend book pays for its\nbig winners with "
       "give-back\non every trade that turns", color=SEC, fontsize=8.6)

fig.suptitle("btc-executor open trade — S4 long 0.03134 BTC from 80,757, "
             "2026-09-21 16:25Z", color=INK, fontsize=12.5,
             fontweight="bold", x=0.008, ha="left", y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
print(f"reconstructed trail: {trail[-1]:,.2f}  vs live engine {LIVE_TRAIL:,.2f}"
      f"  (delta {trail[-1]-LIVE_TRAIL:+,.2f})")
print(f"bars held: {len(held)}  first {hrs[0]:.0f}h  last {hrs[-1]:.0f}h")
print(f"net if stopped at trail now: {net(LIVE_TRAIL):+,.2f}")
print(f"unrealized at mark:          {QTY*(MID-ENTRY):+,.2f}")
