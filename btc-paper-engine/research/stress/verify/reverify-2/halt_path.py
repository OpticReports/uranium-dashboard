"""Synthetic-path tests of stress.Executor's halt / re-arm / re-mirror /
variant-B / funding-while-halted behaviour (the paths no real scenario
exercises). Hand-built engine trades, K 0.75, flat carry 30k."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, STRESS)
import stress
from stress import BAR, DAY, Executor, synthetic_path
from harness import Trade
NOW = stress.SEED_NOW
def d(ts): return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
real = stress.load_closed_bars("btcusd", NOW)
P0 = real[-1].close; t0 = real[-1].ts + BAR
print("t0", d(t0), "P0", P0)
fails = []
def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond: fails.append(msg)

# ---------- T1: DAILY_LOSS intrabar, re-arm at 00:00, re-mirror ----------
# bar0 12:00 flat; bar1 16:00 low -25%, close -10%; bar2 20:00 flat; bar3 00:00 (next day) flat ...
def ohlc(j, prev, c):
    if j == 1: return (prev, prev, prev * 0.75, c)
    return (prev, max(prev, c), min(prev, c), c)
closes = [P0, P0 * 0.90] + [P0 * 0.90] * 10
bars = synthetic_path(closes, now=NOW, ohlc_fn=ohlc)
pub = {"pullback": [Trade("pullback", "L", t0 - 2 * BAR, P0, None, None, "OPEN")], "trend": []}
ex = Executor(bars, pub, 0.75); ex.run()
h = ex.halts
print("T1 events:"); [print("   ", d(e[0]), e[1], e[2], e[3]) for e in ex.events]
check(len(h) == 1 and h[0]["kind"] == "DAILY_LOSS" and h[0]["how"] == "at the line", f"one DAILY_LOSS halt at the line: {h}")
check(h[0]["ts"] == t0 + BAR, "halt on bar 1 (intrabar)")
check(abs(h[0]["line"] - (100000 - 15000)) < 1e-6, f"daily line = day_start 100k - 15k: {h[0]['line']}")
check(abs(h[0]["equity_after"] - 85000) < 100, f"equity after flatten ~85k minus exit fee: {h[0]['equity_after']}")
# fill price consistency: equity at fill == line (before exit fee)
t1 = ex.trades[0]
eq_at_fill = (100000 - 30000 - t1["fees"] + t1["funding"]) + t1["qty"] * (t1["exit_px"] - t1["entry_px"]) + 30000 + (t1["fees"] - t1["qty"] * t1["entry_px"] * 4.32e-4)  # entry fee only
check(abs(eq_at_fill - 85000) < 1.0, f"fill px puts equity on the line before the exit fee: {eq_at_fill:.2f}")
rearm_ts = next((e[0] for e in ex.events if e[1] == "REARM"), None)
check(rearm_ts is not None and rearm_ts % DAY == 0 and rearm_ts == h[0].get("rearm_ts"), f"re-armed at 00:00 UTC: {d(rearm_ts) if rearm_ts else None}")
rem = [e for e in ex.events if e[1] == "REMIRROR" and e[0] == rearm_ts]
check(len(rem) == 1 and "rearm" in rem[0][2], f"re-mirrored the still-open engine long at the re-arm bar's open: {rem}")
check(abs(ex.day_start - ex.eq_tot_out[2]) < 1e-6, f"day_start reset to the 00:00 open equity (= flat equity {ex.eq_tot_out[2]:.2f}): {ex.day_start:.2f}")
check(all(not a for a, t in zip(ex.armed_out, ex.ts_out) if h[0]["ts"] <= t < rearm_ts) and all(a for a, t in zip(ex.armed_out, ex.ts_out) if t >= rearm_ts), "rails flagged disarmed between the halt and the re-arm")
# close-only variant: -10% close = -7.9k < 15k -> no halt
ex2 = Executor(bars, pub, 0.75, intrabar=False); ex2.run()
check(len(ex2.halts) == 0, "close-only variant: no halt on a -10% close")
# K 0.30: line 6k -> -10% close alone (-3.15k) no halt; intrabar -25% (-7.9k) halts
ex3 = Executor(bars, pub, 0.30); ex3.run()
check(len(ex3.halts) == 1 and abs(ex3.halts[0]["line"] - 94000) < 1e-6, f"K0.30: daily line 94k, halt {ex3.halts[0] if ex3.halts else None}")

# ---------- T2: DRAWDOWN (first_cross picks the HIGHER line), variant A vs B ----------
# day1: -15% close (no halt), day2: -14% close (no halt; day_start lower), day3: -25% intrabar -> dd line 70k above daily line -> DRAWDOWN
closes = [P0] * 6 + [P0 * 0.85] * 6 + [P0 * 0.85 * 0.86] * 6 + [P0 * 0.85 * 0.86 * 0.80] * 6 + [P0 * 0.85 * 0.86 * 0.80] * 6 * 10
def ohlc2(j, prev, c): return (prev, max(prev, c), min(prev, c), c)
bars2 = synthetic_path(closes, now=NOW, ohlc_fn=ohlc2)
pub2 = {"pullback": [Trade("pullback", "L", t0 - 2 * BAR, P0, None, None, "OPEN")], "trend": []}
exA = Executor(bars2, pub2, 0.75, dd_variant="A"); exA.run()
print("T2 A events:"); [print("   ", d(e[0]), e[1], e[2], e[3]) for e in exA.events]
hA = exA.halts
check(len(hA) == 1 and hA[0]["kind"] == "DRAWDOWN", f"DRAWDOWN halt: {hA}")
check(abs(hA[0]["line"] - (exA.hw and (hA[0]['hw'] - 30000))) < 1e-6, f"dd line = HW - 30k of base: line {hA[0]['line']} hw {hA[0]['hw']}")
check(hA[0]["line"] > hA[0]["day_start"] - 15000, "the dd line was the higher one (first_cross)")
check(len(exA.pos) == 0 and not any(e[1] in ("REARM", "RESUME", "RESUME_REANCHOR") for e in exA.events), "variant A: flat to the horizon, never re-arms")
check(abs(exA.eq_tot_out[-1] - hA[0]["equity_after"]) < 1e-6, "variant A: equity frozen after the flatten (flat carry)")
exB = Executor(bars2, pub2, 0.75, dd_variant="B"); exB.run()
print("T2 B events:"); [print("   ", d(e[0]), e[1], e[2], e[3]) for e in exB.events]
res_ev = [e for e in exB.events if e[1] in ("RESUME", "RESUME_REANCHOR")]
check(len(res_ev) == 1 and res_ev[0][1] == "RESUME_REANCHOR" and res_ev[0][0] >= exB.halts[0]["ts"] + 7 * DAY, f"variant B: reanchored resume >= 7 days later: {res_ev}")
check(any(e[1] == "REMIRROR" and e[0] == res_ev[0][0] for e in exB.events), "variant B: re-mirrored at the resume bar's open")
check(abs(exB.hw - max(exB.eq_tot_out[-1], exB.halts[0]["equity_after"])) < 1.0 or exB.hw < exA.hw, f"variant B: HW moved to equity at reanchor (hw {exB.hw:.0f} vs A {exA.hw:.0f})")
# dd_first rule should give the same answer here (dd line crossed)
exD = Executor(bars2, pub2, 0.75, halt_rule="dd_first"); exD.run()
check(exD.halts[0]["kind"] == "DRAWDOWN" and abs(exD.halts[0]["line"] - hA[0]["line"]) < 1e-6, "dd_first agrees when the dd line is the higher one")

# ---------- T3: funding while halted / only on held positions ----------
fund = {bars[stress_seam := bars.seam].ts + BAR * (k + 1): 0.001 for k in range(len(closes))}   # a +0.1% stamp at every close (longs pay)
bars3 = bars
ex4 = Executor(bars3, pub, 0.75, btc_funding={ts: 0.001 for ts in range(t0 + BAR, t0 + 13 * BAR, BAR)}); ex4.run()
stamps_held = sum(1 for j, t in enumerate(ex4.ts_out) if any(tr["entry_ts"] <= t and (tr["exit_ts"] is None or tr["exit_ts"] > t) for tr in ex4.trades + ex4.open_positions()))
print("T3 funding", ex4.funding, "stamps", ex4.funding_stamps, "bars with a position held at the close", stamps_held, "trades", [(d(t['entry_ts']), d(t['exit_ts']) if t['exit_ts'] else None, t['funding']) for t in ex4.trades + ex4.open_positions()])
check(ex4.funding_stamps == stamps_held, "funding stamps == bars with a position held at the close (none while halted)")
check(ex4.funding < 0, "long pays a positive rate")
check(all(ex4.funding_cum_out[j] == ex4.funding_cum_out[j - 1] for j, t in enumerate(ex4.ts_out) if j > 0 and ex4.halts[0]["ts"] <= t < rearm_ts), "no funding accrues while the executor is halted (flat)")
check(all(t["funding"] == 0.0 for t in ex4.trades if t["exit_ts"] == t["entry_ts"]), "a same-bar round trip pays no funding")

# ---------- T4: gap through the line at the open ----------
def ohlc4(j, prev, c):
    if j == 1: return (prev * 0.75, prev * 0.75, prev * 0.74, c)
    return (prev, max(prev, c), min(prev, c), c)
closes4 = [P0, P0 * 0.745] + [P0 * 0.745] * 5
bars4 = synthetic_path(closes4, now=NOW, ohlc_fn=ohlc4)
ex5 = Executor(bars4, pub, 0.75); ex5.run()
print("T4 halts", ex5.halts)
check(len(ex5.halts) == 1 and ex5.halts[0]["how"] == "gap at open" and abs(ex5.halts[0]["fill_px"] - P0 * 0.75) < 0.01, "gap through the daily line at the open fills at the open, not the line")
check(ex5.halts[0]["kind"] == "DAILY_LOSS" and ex5.halts[0]["equity_after"] < 85000, "label DAILY_LOSS at the open (dd line 70k not crossed), equity lands below the line")

# ---------- T5: a net-flat opposed book on the intrabar check ----------
pub5 = {"pullback": [Trade("pullback", "S", t0 - 2 * BAR, P0, None, None, "OPEN")],
        "trend": [Trade("trend", "L", t0 - 2 * BAR, P0, None, None, "OPEN")]}
ex6 = Executor(bars, pub5, 0.75); ex6.run()
print("T5 pos", {k: (p.side, round(p.qty, 4)) for k, p in ex6.pos.items()}, "halts", ex6.halts, "net", ex6._net_qty())
check(len(ex6.halts) == 0 or ex6.halts[0]["kind"] in ("DAILY_LOSS", "DRAWDOWN"), "opposed book: no crash, halt only if net exposure loses enough")

print("\nFAILS:", fails if fails else "none")
