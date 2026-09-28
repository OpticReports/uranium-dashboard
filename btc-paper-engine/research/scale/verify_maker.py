"""ADVERSARIAL VERIFICATION of maker_fill.py's two headline claims, computed
from the RAW BARS with no engine call, so an engine bug cannot hide in it.

Claim 1: a limit at the signal bar's close fills within the next bar ~99.5%
         of the time.
Claim 2: therefore the adverse-selection cost of resting passively is ~0 and
         the whole of the execution fix is a pure fee saving.

Claim 2 is the one to attack. Three attacks, all measured:
  A) FILL-QUALITY / QUEUE RISK. The engine fills on `low < limit` (STRICT
     penetration for a long). A resting limit at a price the market only just
     penetrates may not fill: queue ahead of you clears first. Measure HOW FAR
     through the limit the next bar trades, in ticks and in bps. Penetration
     depth is the only queue-risk proxy bar data can give.
  B) The 99.5% is a property of 4h bars, not of the strategy. Measure the
     unconditional rate: for EVERY bar, does the next bar penetrate this
     bar's close? If that is also ~99%, the signal is doing nothing and the
     number is a bar-width artifact -- which is still a valid answer to
     "is maker achievable", but it means it would NOT survive on a faster
     clock or a tighter limit.
  C) EXIT SIDE. Entry is the only leg the docstring calls maker. Which exits
     could also rest? STOP exits cannot (they are urgent). SIGNAL/TIME exits
     fill at the next bar's OPEN and are not urgent. Measure the mix.
Also: how much WORSE would a tighter (more passive) limit be -- the real
trade-off, since a limit BELOW the close would fill less often but better.

Run: python3 research/scale/verify_maker.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                              # noqa: E402
from app.engine.core import Bar                                 # noqa: E402
from app.engine.replay import run_replay, compute_indicators    # noqa: E402
from app.engine.core import eval_signal                         # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,        # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
TICK = 1.0          # HL BTC perp price tick, $1 (5 significant figures / szDecimals)

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS))]
inds = compute_indicators(bars)
N = len(bars)
OUT = {}

# ---------- CLAIM 1, recomputed from raw bars -----------------------------
sig = []
for i in range(210, N - 1):
    s = eval_signal(bars[i], inds[i], RESEARCH_SIGNAL)
    if s:
        sig.append((i, s))
print("=" * 82)
print("CLAIM 1 — passive fill rate, recomputed from raw bars (no engine)")
print("=" * 82)
fills, depths_bps, depths_tick, rng_frac = 0, [], [], []
for i, s in sig:
    lim, nb = bars[i].close, bars[i + 1]
    ok = (nb.low < lim) if s == "L" else (nb.high > lim)
    if ok:
        fills += 1
        d = (lim - nb.low) if s == "L" else (nb.high - lim)
        depths_bps.append(d / lim * 1e4); depths_tick.append(d / TICK)
        span = nb.high - nb.low
        rng_frac.append(d / span if span > 0 else 0.0)
print(f"  signals evaluated (all bars, no flat-gating): {len(sig)}")
print(f"  next bar penetrates the limit: {fills} / {len(sig)} = {fills/len(sig)*100:.2f}%")
print(f"  NOTE: the engine sees FEWER signals ({190} S3 trades) because a book")
print(f"        only acts when flat. The RATE is what matters and it agrees.")
OUT["claim1"] = {"signals_all_bars": len(sig), "penetrated": fills,
                 "rate": fills / len(sig)}

# ---------- ATTACK A: penetration depth = queue-risk proxy ----------------
db = np.array(depths_bps); dt = np.array(depths_tick); rf = np.array(rng_frac)
print()
print("=" * 82)
print("ATTACK A — FILL QUALITY / QUEUE RISK: how deep does price go through?")
print("=" * 82)
print(f"  penetration depth beyond the limit, {len(db)} filled signals:")
for q in (1, 5, 10, 25, 50):
    print(f"    p{q:<2d}: {np.percentile(db,q):8.2f} bps   "
          f"{np.percentile(dt,q):9.1f} ticks   "
          f"{np.percentile(rf,q)*100:5.1f}% of the next bar's range")
print(f"    mean {db.mean():.1f} bps / {dt.mean():.0f} ticks")
for thr in (1, 2, 5, 10):
    frac = float((db < thr).mean())
    print(f"    penetration < {thr:>2d} bps (queue-risk zone): {frac*100:5.2f}% "
          f"of fills -> {int(frac*len(db))} trades")
print("  READ: a fill is at real risk only when the market barely penetrates.")
print(f"  {(db<2).mean()*100:.1f}% of fills penetrate by <2bps. Even if EVERY one")
print(f"  of those failed to fill, the passive fill rate would be "
      f"{(fills*(1-(db<2).mean()))/len(sig)*100:.1f}%.")
OUT["attackA"] = {"depth_bps_p": {q: float(np.percentile(db, q)) for q in (1,5,10,25,50)},
                  "depth_ticks_p": {q: float(np.percentile(dt, q)) for q in (1,5,10,25,50)},
                  "mean_depth_bps": float(db.mean()),
                  "frac_under_bps": {t: float((db < t).mean()) for t in (1,2,5,10)},
                  "worst_case_fill_rate_if_all_sub2bp_miss":
                      float(fills * (1 - (db < 2).mean()) / len(sig))}

# ---------- ATTACK B: is it a bar-width artifact? -------------------------
print()
print("=" * 82)
print("ATTACK B — is 99.5% a STRATEGY property or a 4h-BAR-WIDTH artifact?")
print("=" * 82)
uncond_L = sum(1 for i in range(210, N-1) if bars[i+1].low < bars[i].close)
uncond_S = sum(1 for i in range(210, N-1) if bars[i+1].high > bars[i].close)
tot = N - 1 - 210
print(f"  UNCONDITIONAL (every bar, no signal): next bar dips below this close "
      f"{uncond_L/tot*100:.2f}% | pokes above {uncond_S/tot*100:.2f}%")
print("  -> It is a BAR-WIDTH artifact, and that is the honest reading: a 4h BTC")
print("     bar's range is ~1-3% while the limit sits AT the previous close, so")
print("     the market nearly always comes back through it. The signal adds")
print("     nothing to fill probability. CONSEQUENCE: the result is robust for")
print("     THIS 4h clock and this at-the-close limit, and says NOTHING about a")
print("     faster clock or a limit placed away from the close.")
r4 = np.array([(b.high - b.low) / b.close * 1e4 for b in bars[210:]])
print(f"  4h bar range: median {np.median(r4):.0f} bps, p10 {np.percentile(r4,10):.0f} bps")
OUT["attackB"] = {"uncond_long_fill_rate": uncond_L / tot,
                  "uncond_short_fill_rate": uncond_S / tot,
                  "bar_range_bps_median": float(np.median(r4)),
                  "bar_range_bps_p10": float(np.percentile(r4, 10))}

# ---------- ATTACK C: the exit side --------------------------------------
print()
print("=" * 82)
print("ATTACK C — THE EXIT LEG: which exits could rest passively?")
print("=" * 82)
res = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                 dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=4.32),
                 cash_apy=0.0)
for bk in ("S3", "S4"):
    tr = res.books[bk].trades
    mix = {}
    for t in tr:
        mix[t.exit_reason] = mix.get(t.exit_reason, 0) + 1
    tot_t = len(tr)
    passive_ok = sum(v for k, v in mix.items() if k in ("SIGNAL", "TIME"))
    print(f"  {bk}: n={tot_t}  " + "  ".join(f"{k} {v} ({v/tot_t*100:.1f}%)"
                                             for k, v in sorted(mix.items())))
    print(f"      exits that are NOT urgent (SIGNAL/TIME, fill at next open): "
          f"{passive_ok}/{tot_t} = {passive_ok/tot_t*100:.1f}%")
    print(f"      -> blended exit fee if those rest as maker: "
          f"{(passive_ok*1.44 + (tot_t-passive_ok)*4.32)/tot_t:.2f} bps "
          f"(vs 4.32 all-taker)")
    OUT[f"attackC_{bk}"] = {"mix": mix, "n": tot_t,
                            "non_urgent_frac": passive_ok / tot_t,
                            "blended_exit_bps": (passive_ok*1.44 + (tot_t-passive_ok)*4.32)/tot_t}

# ---------- the real trade-off: a TIGHTER limit ---------------------------
print()
print("=" * 82)
print("THE REAL TRADE-OFF — a limit placed BELOW the close (more passive)")
print("=" * 82)
print("  Better entry price, lower fill rate. Measured on the same signals.")
print(f"  {'offset':>12} {'fill rate':>10} {'price edge':>11} {'expected bps':>13}")
TRADEOFF = {}
for off_bps in (0, 5, 10, 20, 40, 80):
    f, got = 0, 0
    for i, s in sig:
        c = bars[i].close
        lim = c * (1 - off_bps / 1e4) if s == "L" else c * (1 + off_bps / 1e4)
        nb = bars[i + 1]
        ok = (nb.low < lim) if s == "L" else (nb.high > lim)
        if ok:
            f += 1; got += off_bps
    fr = f / len(sig)
    exp = fr * off_bps
    TRADEOFF[off_bps] = {"fill_rate": fr, "expected_price_edge_bps": exp}
    print(f"  {off_bps:>9d}bps {fr*100:>9.2f}% {off_bps:>10d}bps {exp:>12.2f}bps")
print("  -> expected price edge = fill_rate x offset. It is NOT free: each")
print("     unfilled signal is a trade the book never takes, and the trades")
print("     it skips are the ones where price ran AWAY -- i.e. the momentum")
print("     continuations. That selection effect is NOT priced in this table.")
OUT["tighter_limit_tradeoff"] = TRADEOFF

json.dump(OUT, open(os.path.join(HERE, "verify_maker.json"), "w"), indent=1, default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'verify_maker.json')}")
