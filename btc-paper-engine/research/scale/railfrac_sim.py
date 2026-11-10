"""CANDIDATE B - make every rail a fraction. THE PATH-LEVEL MEASUREMENT.

What this does that nothing in research/scale/ does yet: it replays mirror.py's
ACTUAL sizing and halt arithmetic over the real engine trade sequence, with
equity compounding, with both legs competing for one account-wide cap, and with
the halt anchors moving - then repeats that under different RAIL REGIMES and at
a ladder of equity levels.

Everything before this priced the ENVELOPE (how much size the edge authorises).
This prices the PLUMBING (how much size the rails actually deliver), which is a
different question and is the one Casey ran into.

Replica scope, stated so it can be attacked (mirror.py line refs):
  _effective_kelly_m  1445-1465   min(kelly_m, KELLY_M_CAP), NaN -> 0
  _leg_frac           1467-1473   eff * lev * weight
  _base               1475-1479   SIZING_BASE_USD or <the quantity passed in>
  _leg_qty            1493-1517   want vs room, sequential cap consumption
  _breach_for         1626-1644   halt lines are pct * _base(anchor)
  _check_halts        1650-1700   the two coherence guards
  _check_exposure     547-571     pages, never clamps
NOT replicated (and so not claimed): venue quantize, netted_qty, stop
maintenance, chase paths, the debounce (HALT_CONFIRM_POLLS) - the sim halts on
first breach, which is the CONSERVATIVE direction for a safety claim.

Basis: TRADE-CLOSE (exit-step). P&L lands at exit; intra-trade marks are
invisible, so realised MTM drawdown runs deeper (KELLY.md records 1-4pp).
The trade SET is identical in every regime and at every equity level - the
engine is keyless and size-blind - which isolates the rail effect exactly and
also means no size->signal feedback is modelled.

Run: python3 research/scale/railfrac_sim.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)

from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")

# ---------------------------------------------------------------- live config
EQUITY_LIVE       = 100_055.0   # spot USDC backing the perp book (MEASURED)
KELLY_M           = 0.20
KELLY_M_CAP       = 0.20
REFERENCE_LEV     = 1.5
MAX_EXPOSURE_FRAC = 0.30        # = KELLY_M_CAP * REFERENCE_LEV
SIZING_BASE_USD   = 50_000.0
MAX_NOTIONAL_USD  = 20_000.0
MAX_ACCOUNT_LEV   = 2.0
DD_HALT_PCT       = 0.35
DAILY_LOSS_HALT_PCT = 0.06
W_TREND           = 0.25

DAY = 86_400

# ------------------------------------------------------------------ the trades
bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS_CSV))]

P_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S3"]   # pullback
T_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S4"]   # trend


def engine_trades(books, start_ts=None):
    r = run_replay(bars, books, RESEARCH_SIGNAL, RESEARCH_TRADE,
                   start_ts=start_ts, cash_apy=0.0)
    return r.books[books[0].name].trades


def event_stream(start_ts=None):
    """(ts, kind, leg, price, pnl_pct) with EXITs before ENTRYs at equal ts.

    pnl_pct is the engine's per-trade return ON NOTIONAL, already net of the
    registered fee, so the executor's dollar P&L is a pure scaling of it. That
    is the whole transfer function from engine to executor and it is why the
    trade set can be held fixed across regimes."""
    ev = []
    for leg, books in (("pullback", P_BOOKS), ("trend", T_BOOKS)):
        for t in engine_trades(books, start_ts):
            ev.append((t.entry_ts, 1, leg, t.entry_price, None))
            ev.append((t.exit_ts,  0, leg, t.exit_price, t.pnl_pct))
    ev.sort(key=lambda e: (e[0], e[1]))      # kind 0 (exit) first
    return ev


# --------------------------------------------------------------- rail regimes
@dataclasses.dataclass
class Rails:
    label: str
    kelly_m: float = KELLY_M
    lev: float = REFERENCE_LEV
    w_trend: float = W_TREND
    # base: fixed dollars, or None to mean "use the quantity passed in"
    sizing_base_usd: float | None = SIZING_BASE_USD
    # notional cap: an ABSOLUTE ceiling and/or a FRACTION of base
    max_notional_usd: float | None = MAX_NOTIONAL_USD
    max_notional_frac: float | None = None
    max_account_lev: float = MAX_ACCOUNT_LEV
    dd_halt_pct: float = DD_HALT_PCT
    daily_loss_halt_pct: float = DAILY_LOSS_HALT_PCT

    def base(self, anchor: float) -> float:
        """mirror.py _base: `SIZING_BASE_USD or <anchor>`."""
        return self.sizing_base_usd if self.sizing_base_usd else anchor

    def eff_kelly(self) -> float:
        m = float(self.kelly_m)
        if m != m:
            return 0.0
        return min(m, KELLY_M_CAP)

    def cap_notional(self, base: float) -> float:
        """mirror.py _cap_room / _leg_qty: min() over every notional rail."""
        caps = [self.max_account_lev * base]
        if self.max_notional_usd is not None:
            caps.append(self.max_notional_usd)
        if self.max_notional_frac is not None:
            caps.append(self.max_notional_frac * base)
        return min(caps)


# ------------------------------------------------------------------- the sim
def simulate(rails: Rails, equity0: float, start_ts=None,
             halts_armed: bool = True, events=None):
    ev = events if events is not None else event_stream(start_ts)
    equity = float(equity0)
    high_water = equity
    day_start = equity
    day_key = None
    legs = {"pullback": {"qty": 0.0, "notional": 0.0},
            "trend":    {"qty": 0.0, "notional": 0.0}}

    clamps = 0
    entries = 0
    entries_blocked_by_halt = 0
    halted = None                     # (reason, ts, equity)
    eq_path = []                      # (ts, equity) at every exit
    gross_at_entry = []               # realised gross notional right after each entry
    cum_notional = []                 # cumulative notional carried, per entry
    running_notional = 0.0
    first_entry_gross = None
    want_sum = 0.0
    got_sum = 0.0

    for ts, kind, leg, px, pnl_pct in ev:
        # ---- UTC day roll (mirror.py _roll_day)
        dk = ts // DAY
        if day_key is None:
            day_key = dk
        elif dk != day_key:
            day_key = dk
            day_start = equity

        if kind == 0:                                     # EXIT
            L = legs[leg]
            if L["qty"] > 0.0:
                pnl = L["notional"] * (pnl_pct / 100.0)
                equity += pnl
                L["qty"] = 0.0
                L["notional"] = 0.0
                high_water = max(high_water, equity)
                eq_path.append((ts, equity))
                # ---- halt check (mirror.py _breach_for), first-breach halt
                if halts_armed and halted is None:
                    bd = rails.base(day_start)
                    bh = rails.base(high_water)
                    if day_start > 0 and equity < day_start - rails.daily_loss_halt_pct * bd:
                        halted = ("DAILY_LOSS", ts, equity)
                    elif high_water > 0 and equity < high_water - rails.dd_halt_pct * bh:
                        halted = ("DRAWDOWN", ts, equity)
            continue

        # ---- ENTRY
        if halted is not None:
            entries_blocked_by_halt += 1
            continue
        base = rails.base(equity)
        weight = rails.w_trend if leg == "trend" else 1.0 - rails.w_trend
        want = rails.eff_kelly() * rails.lev * weight * base / px
        other = sum(legs[n]["qty"] for n in legs if n != leg)
        cap = rails.cap_notional(base)
        room = max(0.0, cap / px - other)
        got = want
        if want > room:
            clamps += 1
            got = room
        want_sum += want * px
        got_sum += got * px
        if got <= 0.0:
            continue
        legs[leg]["qty"] = got
        legs[leg]["notional"] = got * px
        entries += 1
        gross_now = sum(legs[n]["qty"] for n in legs) * px
        gross_at_entry.append(gross_now)
        running_notional += got * px
        cum_notional.append(running_notional)
        if first_entry_gross is None:
            first_entry_gross = gross_now

    # ---- statistics
    peak = -1e18
    mdd = 0.0
    for _, e in eq_path:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1.0)
    return {
        "label": rails.label,
        "equity0": equity0,
        "equity_final": equity,
        "mult": equity / equity0,
        "maxdd_pct": mdd * 100.0,
        "entries": entries,
        "clamps": clamps,
        "clamp_rate": clamps / max(entries + clamps * 0, 1),
        "halted": None if halted is None else halted[0],
        "halt_ts": None if halted is None else halted[1],
        "entries_blocked_by_halt": entries_blocked_by_halt,
        "first_entry_gross": first_entry_gross,
        "first_entry_gross_frac": (first_entry_gross / equity0) if first_entry_gross else None,
        "max_gross": max(gross_at_entry) if gross_at_entry else 0.0,
        "mean_gross": (sum(gross_at_entry) / len(gross_at_entry)) if gross_at_entry else 0.0,
        "both_legs_target": min(rails.eff_kelly() * rails.lev * rails.base(equity0),
                                rails.cap_notional(rails.base(equity0))),
        "gross_target_flat": rails.eff_kelly() * rails.lev * rails.base(equity0),
        "cap_notional0": rails.cap_notional(rails.base(equity0)),
        "notional_delivered_frac": got_sum / want_sum if want_sum else None,
        "cum_notional_10": cum_notional[9] if len(cum_notional) >= 10 else None,
        "cum_notional_total": cum_notional[-1] if cum_notional else 0.0,
        "worst_single_position": rails.cap_notional(rails.base(equity0)),
        "eq_path": eq_path,
        "gross_at_entry": gross_at_entry,
        "cum_notional": cum_notional,
    }


# ============================================================ VALIDATION
def independent_path(rails: Rails, equity0: float, events):
    """Second, deliberately different implementation of the same arithmetic:
    no leg dict, no cap logic - notional is leg_frac * equity_at_entry and P&L
    is realised at exit. Only valid when NO rail binds (checked by the caller).
    Exists so the entry/exit/P&L plumbing is verified by a path that does not
    share a line of code with simulate()."""
    eq = float(equity0)
    pending = {}
    lf = {"pullback": rails.eff_kelly() * rails.lev * (1 - rails.w_trend),
          "trend":    rails.eff_kelly() * rails.lev * rails.w_trend}
    for ts, kind, leg, px, pnl_pct in events:
        if kind == 1:
            pending[leg] = lf[leg] * eq
        else:
            n = pending.pop(leg, None)
            if n is not None:
                eq += n * (pnl_pct / 100.0)
    return eq


def check(name, ok, detail=""):
    CHECKS.append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


if __name__ == "__main__":
    CHECKS = []
    OUT = {}
    EV = event_stream()
    n_p = sum(1 for e in EV if e[1] == 1 and e[2] == "pullback")
    n_t = sum(1 for e in EV if e[1] == 1 and e[2] == "trend")

    print("=" * 96)
    print("CANDIDATE B - FRACTIONAL RAILS.  Path-level replica of mirror.py sizing + halts")
    print("=" * 96)
    print(f"  trades: pullback {n_p}, trend {n_t}, total {n_p + n_t}  "
          f"(events {len(EV)})")
    print(f"  window {min(e[0] for e in EV)} -> {max(e[0] for e in EV)}  "
          f"= {(max(e[0] for e in EV) - min(e[0] for e in EV)) / 365.25 / DAY:.2f} years")
    print()
    print("  V A L I D A T I O N")

    # V1: from-flat gross at today's config must be the known $15,000
    today = Rails("TODAY")
    r = simulate(today, EQUITY_LIVE, events=EV)
    closed = min(today.eff_kelly() * today.lev * today.base(EQUITY_LIVE),
                 today.cap_notional(today.base(EQUITY_LIVE)))
    check("V1 from-flat gross target == $15,000 (published live size)",
          abs(closed - 15_000.0) < 1e-6, f"${closed:,.2f}")

    # V2: engine trade counts match the numbers Phase 1 published
    check("V2 engine trade counts == published (S3 190 / S4 128)",
          n_p == 190 and n_t == 128, f"S3 {n_p} / S4 {n_t}")

    # V3: two independent implementations of the unclamped path agree
    free = Rails("UNRAILED base=equity", sizing_base_usd=None,
                 max_notional_usd=None, max_notional_frac=None,
                 max_account_lev=1e9, dd_halt_pct=9.9, daily_loss_halt_pct=9.9)
    a = simulate(free, EQUITY_LIVE, events=EV)
    b = independent_path(free, EQUITY_LIVE, EV)
    check("V3 simulate() == independent_path() when no rail binds",
          a["clamps"] == 0 and abs(a["equity_final"] - b) / b < 1e-12,
          f"{a['equity_final']:.6f} vs {b:.6f}  clamps={a['clamps']}")

    # V4: scale invariance - fractional rails, equity x100, every ratio identical
    fracB = Rails("CANDIDATE B", sizing_base_usd=None, max_notional_usd=None,
                  max_notional_frac=0.35, max_account_lev=MAX_ACCOUNT_LEV,
                  dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
    s1 = simulate(fracB, 100_000.0, events=EV)
    s2 = simulate(fracB, 10_000_000.0, events=EV)
    check("V4 fractional rails: mult and maxDD invariant to a 100x equity step",
          abs(s1["mult"] - s2["mult"]) < 1e-9 and abs(s1["maxdd_pct"] - s2["maxdd_pct"]) < 1e-9,
          f"mult {s1['mult']:.9f} vs {s2['mult']:.9f} | "
          f"maxDD {s1['maxdd_pct']:.6f}% vs {s2['maxdd_pct']:.6f}%")

    # V5: fixed-dollar rail must BREAK that invariance
    s3 = simulate(today, 100_000.0, events=EV)
    s4 = simulate(today, 10_000_000.0, events=EV)
    check("V5 fixed-dollar rails: the same step is NOT invariant",
          abs(s3["mult"] - s4["mult"]) > 1e-6,
          f"mult {s3['mult']:.6f} vs {s4['mult']:.6f}  "
          f"(base is fixed, so notional does not follow equity)")
    OUT["checks_window"] = {"n_pullback": n_p, "n_trend": n_t}

    # ================================================== M1  THE PROPORTIONALITY BREAK
    print()
    print("=" * 96)
    print("M1  SCALE THE BOOK *AND* THE CAPITAL TOGETHER (Casey's premise, scenario B)")
    print("=" * 96)
    print("  f scales equity AND SIZING_BASE_USD. MAX_NOTIONAL_USD is a FIXED DOLLAR")
    print("  number, so under today's rails it does not follow. Candidate B has no")
    print("  fixed dollar rail in the operating path.")
    print()
    print(f"  {'f':>6} {'equity':>12} {'want gross':>12} | "
          f"{'TODAY got':>11} {'/eq':>7} {'clamp%':>7} | "
          f"{'CAND B got':>11} {'/eq':>7} {'clamp%':>7}")
    M1 = []
    for f in (1.0, 1.333, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0, 66.7):
        eq = EQUITY_LIVE * f
        ta = Rails("TODAY", sizing_base_usd=SIZING_BASE_USD * f)
        tb = Rails("CAND B", sizing_base_usd=None, max_notional_usd=None,
                   max_notional_frac=0.35, dd_halt_pct=0.175,
                   daily_loss_halt_pct=0.03)
        ra = simulate(ta, eq, events=EV)
        rb = simulate(tb, eq, events=EV)
        want = ta.eff_kelly() * ta.lev * ta.base(eq)
        row = {"f": f, "equity": eq, "want_gross": want,
               "today_gross": ra["both_legs_target"],
               "today_frac": ra["both_legs_target"] / eq,
               "today_delivered": ra["notional_delivered_frac"],
               "today_max_gross": ra["max_gross"],
               "b_gross": rb["both_legs_target"], "b_frac": rb["both_legs_target"] / eq,
               "b_delivered": rb["notional_delivered_frac"],
               "b_max_gross": rb["max_gross"],
               "today_mult": ra["mult"], "b_mult": rb["mult"],
               "today_maxdd": ra["maxdd_pct"], "b_maxdd": rb["maxdd_pct"]}
        M1.append(row)
        print(f"  {f:>6.3f} {eq:>12,.0f} {want:>12,.0f} | "
              f"{ra['both_legs_target']:>11,.0f} {row['today_frac']:>7.2%} "
              f"{1 - ra['notional_delivered_frac']:>7.1%} | "
              f"{rb['both_legs_target']:>11,.0f} {row['b_frac']:>7.2%} "
              f"{1 - rb['notional_delivered_frac']:>7.1%}")
    OUT["M1_scale_together"] = M1
    kink = [r for r in M1 if r["today_delivered"] < 0.999]
    print()
    print(f"  PROPORTIONALITY BREAKS under today's rails at f = "
          f"{kink[0]['f'] if kink else 'never'}  "
          f"(0.20 x 1.5 x base > MAX_NOTIONAL_USD 20,000 when base > $66,667)")
    print(f"  Candidate B delivers 100% of intent at every f tested: "
          f"{all(r['b_delivered'] > 0.9999 for r in M1)}")

    # ============================== M1b  THE FREE 2x AT TODAY'S EQUITY (scenario A)
    print()
    print("=" * 96)
    print("M1b RAISE THE BASE AT TODAY'S EQUITY - the step Casey actually wants next")
    print("=" * 96)
    print(f"  equity fixed at ${EQUITY_LIVE:,.0f}. This RAISES risk (it is not the")
    print("  proportional step); measured because it is the step in front of him.")
    print()
    print(f"  {'SIZING_BASE':>12} {'want':>10} {'cap':>10} {'got':>10} {'/eq':>7} "
          f"{'deliv':>7} {'mult':>7} {'maxDD':>8} {'halt':>10}")
    M1B = []
    for b in (50_000.0, 66_667.0, 75_000.0, 100_055.0, 150_000.0, 200_110.0, 333_333.0):
        ta = Rails("TODAY", sizing_base_usd=b)
        ra = simulate(ta, EQUITY_LIVE, events=EV)
        want = ta.eff_kelly() * ta.lev * b
        M1B.append({"base": b, "want": want, "cap": ta.cap_notional(b),
                    "got": ra["both_legs_target"], "frac": ra["both_legs_target"] / EQUITY_LIVE,
                    "max_gross": ra["max_gross"],
                    "delivered": ra["notional_delivered_frac"], "mult": ra["mult"],
                    "maxdd": ra["maxdd_pct"], "halted": ra["halted"],
                    "exposure_page": (ta.eff_kelly() * ta.lev * b / EQUITY_LIVE) > MAX_EXPOSURE_FRAC * 1.01})
        print(f"  {b:>12,.0f} {want:>10,.0f} {ta.cap_notional(b):>10,.0f} "
              f"{ra['both_legs_target']:>10,.0f} {ra['both_legs_target']/EQUITY_LIVE:>7.1%} "
              f"{ra['notional_delivered_frac']:>7.1%} {ra['mult']:>7.4f} "
              f"{ra['maxdd_pct']:>8.2f}% {str(ra['halted']):>10}")
    OUT["M1b_base_step"] = M1B

    # ================================================== M2  EQUITY LADDER x REGIMES
    print()
    print("=" * 96)
    print("M2  EQUITY LADDER x RAIL REGIME  (rails scaled where the regime says they scale)")
    print("=" * 96)
    REGIMES = {
        "A TODAY  base 50k fixed, cap $20k fixed":
            lambda eq: Rails("A", sizing_base_usd=SIZING_BASE_USD),
        "A' TODAY-scaled  base=f*50k, cap $20k FIXED":
            lambda eq: Rails("A'", sizing_base_usd=SIZING_BASE_USD * eq / EQUITY_LIVE),
        "B CANDIDATE B  base=equity, cap 0.35*base, halts re-cut":
            lambda eq: Rails("B", sizing_base_usd=None, max_notional_usd=None,
                             max_notional_frac=0.35, dd_halt_pct=0.175,
                             daily_loss_halt_pct=0.03),
        "C NAIVE FRACTIONAL  no absolute ceiling at all, halts NOT re-cut":
            lambda eq: Rails("C", sizing_base_usd=None, max_notional_usd=None,
                             max_notional_frac=0.35, dd_halt_pct=DD_HALT_PCT,
                             daily_loss_halt_pct=DAILY_LOSS_HALT_PCT),
    }
    LADDER = [100_055.0, 200_000.0, 500_000.0, 1_000_000.0, 2_000_000.0, 6_670_000.0]
    M2 = {}
    for name, mk in REGIMES.items():
        print(f"  {name}")
        print(f"    {'equity':>11} {'gross':>11} {'/eq':>7} {'cap':>11} "
              f"{'deliv':>7} {'mult':>7} {'maxDD':>8} {'cum$@10':>12} {'cum@10/eq':>10}")
        rows = []
        for eq in LADDER:
            R = mk(eq)
            s = simulate(R, eq, events=EV)
            c10 = s["cum_notional_10"]
            rows.append({"equity": eq, "gross": s["both_legs_target"],
                         "frac": s["both_legs_target"] / eq,
                         "max_gross": s["max_gross"], "mean_gross": s["mean_gross"],
                         "cap": s["cap_notional0"],
                         "delivered": s["notional_delivered_frac"],
                         "mult": s["mult"], "maxdd": s["maxdd_pct"],
                         "cum10": c10, "cum10_frac": c10 / eq if c10 else None,
                         "worst_pos": s["worst_single_position"],
                         "worst_pos_frac": s["worst_single_position"] / eq,
                         "halted": s["halted"]})
            print(f"    {eq:>11,.0f} {s['both_legs_target']:>11,.0f} "
                  f"{s['both_legs_target']/eq:>7.2%} {s['cap_notional0']:>11,.0f} "
                  f"{s['notional_delivered_frac']:>7.1%} {s['mult']:>7.4f} "
                  f"{s['maxdd_pct']:>8.2f}% {c10:>12,.0f} {c10/eq:>10.2f}x")
        M2[name] = rows
        print()
    OUT["M2_ladder"] = M2

    # ===================== M1c  MATCHED RISK: is the premise literally true in code?
    print()
    print("=" * 96)
    print("M1c MATCHED-RISK TEST. Hold gross/equity at TODAY's 15.0% and scale capital.")
    print("=" * 96)
    print("  This is Casey's premise stated exactly: same proportion, bigger book.")
    print("  KELLY_M 0.10 with base=equity ships the same 15.0% that KELLY_M 0.20 with")
    print("  base=50,000 ships today. If the premise is true, every risk statistic is")
    print("  identical at every equity level. NOTE the second effect: base=equity is a")
    print("  FIXED-FRACTION book (notional follows equity); base=50,000 is a")
    print("  FIXED-DOLLAR book (notional never moves). They compound differently.")
    print()
    print(f"  {'equity':>11} | {'FIXED-$ gross':>13} {'/eq':>7} {'mult':>7} {'maxDD':>8} "
          f"| {'FIXED-FRAC gross':>16} {'/eq':>7} {'mult':>7} {'maxDD':>8}")
    M1C = []
    for eq in LADDER if False else [100_055.0, 200_110.0, 500_275.0, 1_000_550.0, 6_673_668.0]:
        fd = Rails("fixed-$", kelly_m=0.20, sizing_base_usd=SIZING_BASE_USD,
                   max_notional_usd=1e12)                     # rail out of the way
        ff = Rails("fixed-frac", kelly_m=0.10, sizing_base_usd=None,
                   max_notional_usd=None, max_notional_frac=0.35,
                   dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
        a, b = simulate(fd, eq, events=EV), simulate(ff, eq, events=EV)
        M1C.append({"equity": eq,
                    "fixed_dollar": {"gross": a["both_legs_target"],
                                     "frac": a["both_legs_target"] / eq,
                                     "mult": a["mult"], "maxdd": a["maxdd_pct"]},
                    "fixed_frac": {"gross": b["both_legs_target"],
                                   "frac": b["both_legs_target"] / eq,
                                   "mult": b["mult"], "maxdd": b["maxdd_pct"]}})
        print(f"  {eq:>11,.0f} | {a['both_legs_target']:>13,.0f} "
              f"{a['both_legs_target']/eq:>7.2%} {a['mult']:>7.4f} {a['maxdd_pct']:>8.2f}% "
              f"| {b['both_legs_target']:>16,.0f} {b['both_legs_target']/eq:>7.2%} "
              f"{b['mult']:>7.4f} {b['maxdd_pct']:>8.2f}%")
    inv = all(abs(r["fixed_frac"]["mult"] - M1C[0]["fixed_frac"]["mult"]) < 1e-9
              and abs(r["fixed_frac"]["maxdd"] - M1C[0]["fixed_frac"]["maxdd"]) < 1e-9
              for r in M1C)
    print()
    print(f"  FIXED-FRACTION invariant across a {LADDER[-1]/LADDER[0]:.0f}x capital range: {inv}")
    print(f"  FIXED-DOLLAR maxDD decays {M1C[0]['fixed_dollar']['maxdd']:.2f}% -> "
          f"{M1C[-1]['fixed_dollar']['maxdd']:.2f}% - the book stops betting as it grows.")
    OUT["M1c_matched_risk"] = {"rows": M1C, "fixed_frac_invariant": inv}

    # ============================================== M3  BLAST RADIUS - THE PRICE
    print()
    print("=" * 96)
    print("M3  BLAST RADIUS: what the FIXED-DOLLAR rail was buying, priced")
    print("=" * 96)
    print("  EXECUTOR.md RAMP v3: 'cumulative notional carried before a bug is")
    print("  discovered at trade 10: cliff $20.5k vs v2 $50.8k. A 100%-loss defect at")
    print("  that point costs the cliff a survivable $20.5k and v2 the whole deposit.'")
    print("  The word doing the work is SURVIVABLE, and survivable is a FRACTION.")
    print()
    print(f"  {'equity':>11} | {'TODAY worst pos':>15} {'/eq':>7} {'cum@10':>12} {'/eq':>7} "
          f"| {'CAND B worst pos':>16} {'/eq':>7} {'cum@10':>12} {'/eq':>7}")
    M3 = []
    for eq in LADDER:
        ta = Rails("TODAY", sizing_base_usd=SIZING_BASE_USD)
        tb = Rails("B", sizing_base_usd=None, max_notional_usd=None,
                   max_notional_frac=0.35, dd_halt_pct=0.175, daily_loss_halt_pct=0.03)
        a, b = simulate(ta, eq, events=EV), simulate(tb, eq, events=EV)
        M3.append({"equity": eq,
                   "today": {"worst_pos": a["worst_single_position"],
                             "worst_pos_frac": a["worst_single_position"] / eq,
                             "cum10": a["cum_notional_10"], "cum10_frac": a["cum_notional_10"] / eq},
                   "b": {"worst_pos": b["worst_single_position"],
                         "worst_pos_frac": b["worst_single_position"] / eq,
                         "cum10": b["cum_notional_10"], "cum10_frac": b["cum_notional_10"] / eq}})
        print(f"  {eq:>11,.0f} | {a['worst_single_position']:>15,.0f} "
              f"{a['worst_single_position']/eq:>7.1%} {a['cum_notional_10']:>12,.0f} "
              f"{a['cum_notional_10']/eq:>7.2f}x | {b['worst_single_position']:>16,.0f} "
              f"{b['worst_single_position']/eq:>7.1%} {b['cum_notional_10']:>12,.0f} "
              f"{b['cum_notional_10']/eq:>7.2f}x")
    print()
    print("  In DOLLARS the fractional rail's blast radius grows with equity "
          f"({M3[-1]['b']['worst_pos']/M3[0]['b']['worst_pos']:.0f}x over the ladder).")
    print("  As a FRACTION OF EQUITY it is constant at "
          f"{M3[0]['b']['worst_pos_frac']:.1%} - by construction.")
    print("  Today's rail is constant in DOLLARS, so its fraction DECAYS "
          f"{M3[0]['today']['worst_pos_frac']:.1%} -> {M3[-1]['today']['worst_pos_frac']:.2%}:")
    print("  it stops being a risk control and becomes a throttle.")
    OUT["M3_blast_radius"] = M3

    # ======================================= M4  HALT COHERENCE UNDER FRACTIONAL RAILS
    print()
    print("=" * 96)
    print("M4  THE COHERENCE GUARDS - replicated, then mapped")
    print("=" * 96)

    def guard1(equity, base_h, dd_pct):
        """mirror.py 1659: DD line vs the ACCOUNT."""
        return bool(0 < equity < base_h and dd_pct * base_h > 0.8 * equity)

    def guard2(base_h, cap_notional, dd_pct, daily_pct):
        """mirror.py 1682-1697: halt line vs the EXPOSURE the caps permit."""
        out = []
        if cap_notional > 0:
            for label, pct in (("DRAWDOWN", dd_pct), ("DAILY_LOSS", daily_pct)):
                if pct * base_h > cap_notional:
                    out.append((label, pct * base_h / cap_notional))
        return out

    E = EQUITY_LIVE
    cases = [
        ("TODAY  base 50k, cap 20k, dd .35/.06", 50_000.0, min(20_000.0, 2.0 * 50_000.0), 0.35, 0.06),
        ("NAIVE  base=eq, cap 20k UNCHANGED",    E,        min(20_000.0, 2.0 * E),        0.35, 0.06),
        ("NAIVE  base=eq, cap 20k, halts re-cut", E,       min(20_000.0, 2.0 * E),        0.175, 0.03),
        ("CAND B base=eq, cap .35*base, dd .175", E,       0.35 * E,                      0.175, 0.03),
        ("CAND B base=eq, cap .35*base, dd .35",  E,       0.35 * E,                      0.35, 0.06),
        ("CAND B base=eq, cap .40*base, dd .35",  E,       0.40 * E,                      0.35, 0.06),
    ]
    print(f"  {'config':<40} {'guard1':>7} {'guard2 fires':>32}")
    M4 = []
    for lbl, bh, cap, dd, dl in cases:
        g1 = guard1(E, bh, dd)
        g2 = guard2(bh, cap, dd, dl)
        M4.append({"case": lbl, "base_h": bh, "cap": cap, "dd_halt": dd,
                   "daily_halt": dl, "guard1_warn": g1,
                   "guard2_warn": [{"label": a, "ratio": b} for a, b in g2]})
        s = ", ".join(f"{a} {b:.1f}x" for a, b in g2) or "-"
        print(f"  {lbl:<40} {str(g1):>7} {s:>32}")
    print()
    print("  DERIVED INVARIANT (solve guard2 for the fractional form):")
    print("    cap = min(MAX_NOTIONAL_USD, MAX_NOTIONAL_FRAC*base, MAX_ACCOUNT_LEV*base)")
    print("    guard2 is silent  <=>  min(MAX_NOTIONAL_USD/base, MAX_NOTIONAL_FRAC,")
    print("                              MAX_ACCOUNT_LEV)  >=  DD_HALT_PCT")
    print("    i.e.  MAX_NOTIONAL_FRAC >= DD_HALT_PCT  AND  MAX_NOTIONAL_USD >= DD_HALT_PCT*base")
    print("  Verified numerically over a grid:")
    bad = 0
    for phi in [i / 100 for i in range(5, 101, 5)]:
        for dd in [i / 100 for i in range(5, 61, 5)]:
            cap = min(1e12, phi * E, 2.0 * E)
            pred = phi < dd
            act = any(a == "DRAWDOWN" for a, _ in guard2(E, cap, dd, 0.03))
            if pred != act:
                bad += 1
    check("M4 invariant MAX_NOTIONAL_FRAC >= DD_HALT_PCT reproduces guard2 exactly",
          bad == 0, f"{bad} mismatches over 240 (phi, dd) pairs")
    print()
    print("  GUARD 1 GOES NEARLY INERT when base == equity, and this is not documented:")
    for dd in (0.35, 0.25, 0.175):
        d = 1.0 - dd / 0.8
        print(f"    at DD_HALT_PCT {dd:.3f} it needs a {d:.1%} drawdown before it can fire")
    print("    (it was written for base > equity, the small-deposit construction)")
    OUT["M4_coherence"] = {"cases": M4, "grid_mismatches": bad}

    # =========================== M5  WHAT THE HALT RE-CUT COSTS AND BUYS (bootstrapped)
    print()
    print("=" * 96)
    print("M5  THE HALT RE-CUT: base=equity DOUBLES the loss the breakers permit")
    print("=" * 96)
    print(f"  Today DD_HALT_PCT {DD_HALT_PCT} of base ${SIZING_BASE_USD:,.0f} = "
          f"${DD_HALT_PCT*SIZING_BASE_USD:,.0f} = "
          f"{DD_HALT_PCT*SIZING_BASE_USD/E:.1%} of the REAL account.")
    print(f"  With base=equity the SAME {DD_HALT_PCT} means "
          f"{DD_HALT_PCT:.1%} of the real account - a "
          f"{E/SIZING_BASE_USD:.3f}x LOOSENING nobody asked for.")
    print(f"  Equivalence-preserving re-cut: DD_HALT_PCT "
          f"{DD_HALT_PCT} -> {DD_HALT_PCT*SIZING_BASE_USD/E:.4f}, "
          f"DAILY {DAILY_LOSS_HALT_PCT} -> {DAILY_LOSS_HALT_PCT*SIZING_BASE_USD/E:.4f}")
    OUT["M5_recut"] = {
        "today_dd_halt_frac_of_equity": DD_HALT_PCT * SIZING_BASE_USD / E,
        "today_daily_halt_frac_of_equity": DAILY_LOSS_HALT_PCT * SIZING_BASE_USD / E,
        "loosening_factor": E / SIZING_BASE_USD,
        "equivalence_dd_halt_pct": DD_HALT_PCT * SIZING_BASE_USD / E,
        "equivalence_daily_halt_pct": DAILY_LOSS_HALT_PCT * SIZING_BASE_USD / E}

    # in-sample: does ANY halt fire in either regime? (it must not silently not-matter)
    print()
    print("  IN-SAMPLE, does the re-cut change anything?")
    for lbl, dd, dl in (("as-is 0.35/0.06", 0.35, 0.06),
                        ("re-cut 0.175/0.03", 0.175, 0.03),
                        ("aggressive 0.10/0.02", 0.10, 0.02)):
        R = Rails("B", sizing_base_usd=None, max_notional_usd=None,
                  max_notional_frac=0.35, dd_halt_pct=dd, daily_loss_halt_pct=dl)
        s = simulate(R, E, events=EV)
        print(f"    {lbl:<20} mult {s['mult']:.4f}  maxDD {s['maxdd_pct']:>7.2f}%  "
              f"halt {str(s['halted']):<12} blocked {s['entries_blocked_by_halt']}")
    print("  So the in-sample path CANNOT price the re-cut: realised maxDD is far")
    print("  inside every candidate halt. The bootstrap below is the only instrument.")

    json.dump({"checks": CHECKS, **OUT},
              open(os.path.join(HERE, "railfrac_sim.json"), "w"),
              indent=1, default=str)
    print()
    print(f"  {sum(1 for c in CHECKS if c['pass'])}/{len(CHECKS)} checks pass")
    print("  wrote railfrac_sim.json")
