"""EDGE-SIDE LEVER 1+2: is maker execution achievable, and what does it buy?

The pullback entry model in core.py IS ALREADY A RESTING PASSIVE LIMIT:
  "Entry: limit at close(T) placed at signal close; fills during bar T+1 if it
   trades through (long: low < limit; short: high > limit). Unfilled -> cancel."
...but core.py:337 then charges `fee_bps = 2 * taker_fee_bps` on that fill.
The FILL MODEL is maker; the FEE is taker on both legs. That inconsistency is
the whole of RESEARCH_FEES.md's 8.64 arm.

Live, `hl.place_limit` sends tif=Alo, the venue rejects it as marketable, and
the except branch re-sends Gtc priced into the market. So LIVE:
  (a) pays taker on entry                      -> the FEE channel, and
  (b) fills EVERY signal, including the ones the backtest CANCELS
                                               -> the TRADE-SET channel.
(b) has never been measured. It is strictly larger than (a) and it is measured
here, because the live book is not trading the backtested trade set.

Variants (identical code path, ONE rule changed each):
  PASSIVE_1   shipped: limit rests 1 bar, cancel if unfilled     (maker entry)
  PASSIVE_2/3 limit rests 2 / 3 bars before cancel               (maker entry)
  CROSS_ALL   every signal fills at close(T)                     (taker entry)

Run: python3 research/scale/maker_fill.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                                # noqa: E402
import app.engine.core as core                                    # noqa: E402
from app.engine.core import (Bar, Pending, Position, TradeCfg,     # noqa: E402
                             _size, _close_position)
from app.engine.replay import run_replay                           # noqa: E402
from app.engine.kelly import analyze                               # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,            # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")

# ---- REAL Hyperliquid fee schedule, fetched from the public info endpoint
#      (type=userFees) for the live account on 2026-09-28. Frozen here.
HL = {
    "userCrossRate": 0.00045,      # taker, pre-discount
    "userAddRate":   0.00015,      # maker, pre-discount
    "referralDiscount": 0.04,
}
TAKER_BPS = HL["userCrossRate"] * 1e4 * (1 - HL["referralDiscount"])   # 4.32
MAKER_BPS = HL["userAddRate"]   * 1e4 * (1 - HL["referralDiscount"])   # 1.44


def load(p):
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(p))]


# ---------------------------------------------------------------- variants --
_ORIG = core._process_pullback
LOG: list[dict] = []


def make_pullback(ttl: int, cross_all: bool):
    """Rebuild _process_pullback with ONE rule changed: how the pending limit
    resolves. Everything downstream (sizing, stop, exits, fees) is the shipped
    code, called through the shipped helpers."""
    def _proc(book, bar, ind, scfg, tcfg, signal):
        # ---- 1) pending limit entry resolves against this bar
        if book.pending is not None:
            p = book.pending
            through = (bar.low < p.limit) if p.side == "L" else (bar.high > p.limit)
            age = getattr(p, "_age", 0) + 1
            filled = through or cross_all
            if not filled and age < ttl:
                p._age = age                      # keep resting
                # fall through to position management with pending still live
            else:
                book.pending = None
                if filled and ind.atr14 is not None:
                    a_e = ind.atr14
                    qty, notional = _size(book, p.side, p.limit, a_e, tcfg)
                    if qty > 0:
                        stop = (p.limit - tcfg.stop_atr * a_e if p.side == "L"
                                else p.limit + tcfg.stop_atr * a_e)
                        book.position = Position(
                            side=p.side, entry_ts=bar.ts, entry_price=p.limit,
                            qty=qty, notional=notional, stop_price=stop,
                            atr_at_entry=a_e, signal_ts=p.signal_ts,
                            fee_bps=FEE_RT[0])
                    LOG.append({"book": book.cfg.name, "signal_ts": p.signal_ts,
                                "fill_ts": bar.ts, "side": p.side,
                                "limit": p.limit, "bars_waited": age,
                                "filled": True, "through": through,
                                "open_next": bar.open})
                    return
                LOG.append({"book": book.cfg.name, "signal_ts": p.signal_ts,
                            "fill_ts": None, "side": p.side, "limit": p.limit,
                            "bars_waited": age, "filled": False,
                            "through": through, "open_next": bar.open})
        # ---- 2) manage open position  (verbatim shipped logic)
        pos = book.position
        if pos is not None and bar.ts > pos.entry_ts:
            if pos.side == "L" and bar.low <= pos.stop_price:
                _close_position(book, pos, bar.ts, pos.stop_price, "STOP", tcfg)
            elif pos.side == "S" and bar.high >= pos.stop_price:
                _close_position(book, pos, bar.ts, pos.stop_price, "STOP", tcfg)
            else:
                bars_held = (bar.ts - pos.entry_ts) // core.BAR_SECONDS
                want = None
                if ind.sma50 is not None:
                    if pos.side == "L" and bar.close > ind.sma50:
                        want = "SIGNAL"
                    elif pos.side == "S" and bar.close < ind.sma50:
                        want = "SIGNAL"
                if want is None and bars_held >= tcfg.time_stop_bars:
                    want = "TIME"
                if want:
                    pos.exit_flag = want
                return
        # ---- 3) place entry on this close
        if book.position is None and book.pending is None and not book.halted \
                and signal is not None and ind.atr14 is not None:
            book.pending = Pending(side=signal, limit=bar.close,
                                   signal_ts=bar.ts, atr_signal=ind.atr14)
    return _proc


FEE_RT = [2 * RESEARCH_TRADE.taker_fee_bps]     # mutable: set per run


def run(ttl, cross_all, fee_rt, start_ts=None, cash_apy=0.0, books=None):
    """Returns (ReplayResult, log rows for this run)."""
    global LOG
    LOG = []
    FEE_RT[0] = fee_rt
    core._process_pullback = make_pullback(ttl, cross_all)
    try:
        r = run_replay(load.cache, books or RESEARCH_BOOKS, RESEARCH_SIGNAL,
                       dataclasses.replace(RESEARCH_TRADE,
                                           taker_fee_bps=fee_rt / 2.0),
                       start_ts=start_ts, cash_apy=cash_apy)
    finally:
        core._process_pullback = _ORIG
    return r, list(LOG)


def steps(book):
    out, prev = [], book.cfg.start_equity
    for t in book.trades:
        out.append(t.equity_after / prev - 1); prev = t.equity_after
    return out


def blend_steps(b3, b4, w_trend=0.25, lev=1.5):
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
    p3 = p4 = 1.0; out = []
    for _, w, ratio in evs:
        if w == "P":
            out.append(lev * (ratio / p3 - 1) * (1 - w_trend)); p3 = ratio
        else:
            out.append(lev * (ratio / p4 - 1) * w_trend); p4 = ratio
    return out


def curve_dd(st):
    eq = np.cumprod(1 + np.array(st)); pk = np.maximum.accumulate(eq)
    return float((eq / pk - 1).min()), float(eq[-1])


# ------------------------------------------------------------------- main ---
load.cache = load(BARS)
bars = load.cache
LAST = bars[-1].ts
W = {"full": None, "2y": LAST - 730 * 86400}

print("=" * 80)
print("HYPERLIQUID FEE SCHEDULE — fetched live 2026-09-28, type=userFees")
print("=" * 80)
print(f"  taker (cross) {HL['userCrossRate']*1e4:.2f} bps, 4% referral -> {TAKER_BPS:.2f} bps")
print(f"  maker (add)   {HL['userAddRate']*1e4:.2f} bps, 4% referral -> {MAKER_BPS:.2f} bps")
print(f"  MAKER-TAKER SPREAD PER LEG = {TAKER_BPS - MAKER_BPS:.2f} bps")
print(f"  round trip, taker/taker = {2*TAKER_BPS:.2f} bps   (RESEARCH_FEES.md 8.64 CONFIRMED)")
print(f"  round trip, maker/taker = {MAKER_BPS + TAKER_BPS:.2f} bps")
print(f"  round trip, maker/maker = {2*MAKER_BPS:.2f} bps")
print("  VIP tiers (14d notional): 5M->cross 4.0/add 1.2 | 25M->3.5/0.8 |")
print("    100M->3.0/0.4 | 500M->2.8/0.0 | MM rebate tiers keyed on maker")
print("    fraction of EXCHANGE volume (>=0.5%) -> add -0.1bp. Exchange does")
print("    ~$7bn/day, so 0.5% = ~$35m/day of maker flow. NOT REACHABLE HERE.")

# ---- A. fill-rate measurement -------------------------------------------
print()
print("=" * 80)
print("A. IS MAKER EXECUTION ACHIEVABLE?  passive-fill rate on the fixture")
print("=" * 80)
FILL = {}
for ttl in (1, 2, 3, 4):
    r, log = run(ttl, False, MAKER_BPS + TAKER_BPS)
    lg = [x for x in log if x["book"] == "S3"]
    n = len(lg); f = sum(x["filled"] for x in lg)
    first = sum(1 for x in lg if x["filled"] and x["bars_waited"] == 1)
    FILL[ttl] = {"signals_priced": n, "filled": f, "fill_rate": f / n if n else 0,
                 "filled_on_bar1": first, "n_trades_S3": len(r.books["S3"].trades)}
    print(f"  TTL {ttl} bar(s): {n:4d} limits priced  {f:4d} filled "
          f"({f/n*100:5.1f}%)   first-bar fills {first:4d}   S3 trades {len(r.books['S3'].trades):4d}")
print(f"  -> the SHIPPED model is TTL=1. Passive fill rate "
      f"{FILL[1]['fill_rate']*100:.1f}%: {FILL[1]['signals_priced']-FILL[1]['filled']} of "
      f"{FILL[1]['signals_priced']} signals are CANCELLED and never traded.")
print("  -> maker execution IS achievable for the fills that happen: the")
print("     backtest ALREADY only counts trades where price came to the limit.")
print("     The cost of waiting is ALREADY PAID inside every published number.")

# ---- B. adverse selection: what the cancelled signals were worth ---------
print()
print("=" * 80)
print("B. ADVERSE SELECTION — what do the CANCELLED signals cost / save?")
print("=" * 80)
RES = {}
for wname, st in W.items():
    row = {}
    for tag, ttl, cross, fee in (
            ("PASSIVE_1_makerentry", 1, False, MAKER_BPS + TAKER_BPS),
            ("PASSIVE_1_takerentry", 1, False, 2 * TAKER_BPS),
            ("CROSS_ALL_takerentry", 1, True,  2 * TAKER_BPS),
            ("CROSS_ALL_makerfee_hypothetical", 1, True, MAKER_BPS + TAKER_BPS),
            ("PASSIVE_2_makerentry", 2, False, MAKER_BPS + TAKER_BPS),
            ("PASSIVE_3_makerentry", 3, False, MAKER_BPS + TAKER_BPS)):
        r, log = run(ttl, cross, fee, start_ts=st)
        b3, b4 = r.books["S3"], r.books["S4"]
        s3 = steps(b3); bl = blend_steps(b3, b4)
        dd3, fin3 = curve_dd(s3); ddb, finb = curve_dd(bl)
        exits = {}
        for t in b3.trades:
            exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
        row[tag] = {
            "fee_rt_bps": fee, "n_S3": len(b3.trades),
            "S3_total_return": fin3 - 1, "S3_tradeclose_maxdd": dd3,
            "S3_mtm_maxdd": b3.mtm_max_dd,
            "S3_win_rate": sum(1 for t in b3.trades if t.pnl_usd > 0) / max(1, len(b3.trades)),
            "S3_mean_step_pct": float(np.mean(s3) * 100) if s3 else 0.0,
            "S3_sd_step_pct": float(np.std(s3, ddof=1) * 100) if len(s3) > 1 else 0.0,
            "S3_exit_mix": exits, "S3_fees_usd": sum(t.fees_usd for t in b3.trades),
            "blend_n": len(bl), "blend_total_return": finb - 1,
            "blend_maxdd": ddb,
        }
        print(f"  [{wname:4s}] {tag:34s} rt{fee:5.2f}  n={len(b3.trades):4d} "
              f"ret={fin3-1:+7.2%} DDtc={dd3:+6.2%} DDmtm={b3.mtm_max_dd:+6.2%} "
              f"win={row[tag]['S3_win_rate']:5.1%}")
    RES[wname] = row

for wname in W:
    p, c = RES[wname]["PASSIVE_1_takerentry"], RES[wname]["CROSS_ALL_takerentry"]
    print()
    print(f"  TRADE-SET CHANNEL [{wname}] (fee held at {2*TAKER_BPS:.2f} both sides):")
    print(f"    passive/cancel  n={p['n_S3']:4d}  ret {p['S3_total_return']:+7.2%}  "
          f"DD(tc) {p['S3_tradeclose_maxdd']:+6.2%}  win {p['S3_win_rate']:5.1%}")
    print(f"    cross-everything n={c['n_S3']:4d}  ret {c['S3_total_return']:+7.2%}  "
          f"DD(tc) {c['S3_tradeclose_maxdd']:+6.2%}  win {c['S3_win_rate']:5.1%}")
    extra = c["n_S3"] - p["n_S3"]
    print(f"    -> crossing adds {extra} trades and moves total return by "
          f"{c['S3_total_return']-p['S3_total_return']:+.2%}")

# ---- C. Kelly re-fit: what the fee fix buys in AUTHORISED m --------------
print()
print("=" * 80)
print("C. AUTHORISED SIZE — Kelly re-fit on the shipped pipeline, per arm")
print("=" * 80)
KEL = {}
for wname in W:
    for tag, d in RES[wname].items():
        pass
    for tag in RES[wname]:
        # rebuild the streams for the kelly engine (cheap: rerun)
        pass

def kelly_cell(ttl, cross, fee, st, lev=1.5, label=""):
    r, _ = run(ttl, cross, fee, start_ts=st)
    b3, b4 = r.books["S3"], r.books["S4"]
    bl = blend_steps(b3, b4, 0.25, lev)
    A = analyze(bl, label)
    terms = {"half_kelly": A["half_kelly_m"], "p10": A["bootstrap"]["p10"],
             "c*m*": round(A["shrinkage_c_star"] * A["kelly_m"], 3),
             "dd30": A["dd_constrained"]["p_maxdd30_le_10pct"]}
    bind = min(terms.items(), key=lambda t: t[1])
    return A, terms, bind, len(bl)

ARMS = [("PASSIVE_1 @ taker/taker 8.64  (RESEARCH_FEES.md live arm)", 1, False, 2 * TAKER_BPS),
        ("PASSIVE_1 @ maker/taker 5.76  (EXECUTION FIXED)",            1, False, MAKER_BPS + TAKER_BPS),
        ("PASSIVE_1 @ maker/maker 2.88  (exits passive too)",          1, False, 2 * MAKER_BPS),
        ("PASSIVE_1 @ 6.00 rt (what the frozen study really charged)",  1, False, 6.00),
        ("PASSIVE_2 @ maker/taker 5.76  (limit rests 2 bars)",         2, False, MAKER_BPS + TAKER_BPS),
        ("PASSIVE_3 @ maker/taker 5.76  (limit rests 3 bars)",         3, False, MAKER_BPS + TAKER_BPS),
        ("CROSS_ALL @ taker/taker 8.64  (WHAT LIVE ACTUALLY DOES)",     1, True,  2 * TAKER_BPS)]

for wname, st in W.items():
    print(f"\n  --- window {wname} | S5 blend 75/25 @1.5x | cash_apy 0 ---")
    print(f"  {'arm':<62} {'n':>4} {'m*':>6} {'half':>6} {'p10':>6} {'c*m*':>6} {'dd30':>6} {'REC':>6}  binds")
    for label, ttl, cross, fee in ARMS:
        A, terms, bind, n = kelly_cell(ttl, cross, fee, st, 1.5, f"S5|{wname}|{label}")
        KEL[f"{wname}|{label}"] = {"analyze": A, "terms": terms, "binding": bind, "n": n}
        print(f"  {label:<62} {n:>4} {A['kelly_m']:>6.2f} {terms['half_kelly']:>6.2f} "
              f"{terms['p10']:>6.2f} {terms['c*m*']:>6.2f} {terms['dd30']:>6.2f} "
              f"{A['recommended_m']:>6.2f}  {bind[0]}")

json.dump({"hl_fees": {"taker_bps": TAKER_BPS, "maker_bps": MAKER_BPS,
                       "raw": HL},
           "fill_rates": FILL, "variants": RES, "kelly": KEL},
          open(os.path.join(HERE, "maker_fill.json"), "w"), indent=1, default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'maker_fill.json')}")
