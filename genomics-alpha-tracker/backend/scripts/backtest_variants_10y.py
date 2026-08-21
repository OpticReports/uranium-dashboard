"""Pre-registered variant campaign on the 10-year calls replay
(docs/VARIANTS_PREREGISTRATION.md — the contract; registered BEFORE any
variant was run).

Reuses the per-call rows of scripts/backtest_calls_10y.py verbatim
(backend/data/backtest_calls_10y_results.json) for V0-V5 and V7-V9 — fires
are NEVER regenerated for those. V6a/V6b build a monthly rank-portfolio from
the cached bars; V10 (EXPLORATORY) re-grades the rel_strength fires with a
trailing-ATR exit, bar-walking with grade_call's open-first conventions.

Judgment protocol (fixed by the pre-registration):
  $100k book, risk 1% of current equity per call (sizing on the PREVIOUS
  close's equity — this convention reproduces the BACKTEST_CALLS_10Y.md
  dollar-book addendum to $4), daily MTM on adjusted closes, realized r_net
  (tiered slippage) on the exit date, rf = 0. Full period 2016-01-01 ->
  2026-08-19 plus three sub-periods. A variant SURVIVES only if it improves
  BOTH Sharpe and Calmar vs V0 over the full period AND in >=2 of 3
  sub-periods.

Usage:  python -m scripts.backtest_variants_10y
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike  # noqa: E402
from scripts.backtest_calls import (  # noqa: E402
    SLIPPAGE_BPS_BY_TIER,
    to_adjusted_barlikes,
)
from scripts.backtest_signals import atr_series  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
BARS_CACHE = DATA / "backtest_bars.json"
SPY_RAW = DATA / "spy_bars_raw.json"
CALLS_RESULTS = DATA / "backtest_calls_10y_results.json"
RESULTS = DATA / "backtest_variants_10y_results.json"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_VARIANTS_10Y.md"

START = date(2016, 1, 1)
END = date(2026, 8, 19)
SUB_PERIODS = [
    ("2016-2019", date(2016, 1, 1), date(2019, 12, 31)),
    ("2020-2022", date(2020, 1, 1), date(2022, 12, 31)),
    ("2023-2026", date(2023, 1, 1), date(2026, 8, 19)),
]
LIVE_SET_FLAGS = ("quiet_before_catalyst", "pullback_into_catalyst",
                  "binary_event_within_n_days", "volume_anomaly",
                  "rel_strength_60d")
ALL_SIX_FLAGS = LIVE_SET_FLAGS + ("pullback_price_half",)

START_EQUITY = 100_000.0
RISK_FRAC = 0.01
CAP = 10
TRADING_DAYS = 252

# V0 machinery check — the documented dollar-book addendum numbers
# (BACKTEST_CALLS_10Y.md). Reproduction within ±1% is REQUIRED before any
# variant runs; a miss means the engine drifted from the addendum's protocol.
V0_EXPECTED = {"end": 208_764.0, "cagr": 0.0719, "max_dd": 0.655, "sharpe": 0.42}
# the documented stats are ROUNDED (2dp / 0.1pp); the check allows ±1% or half
# the printed precision, whichever is larger
V0_TOL = {"end": 2087.64, "cagr": 0.0005, "max_dd": 0.0065, "sharpe": 0.005}

# V6 parameters (fixed by the pre-registration — not tunable this round)
V6_TOP_N = 5
V6_LOOKBACK_BARS = 60
V6_SLIPPAGE_PER_SIDE = 0.0010  # 10 bps
# V9 parameters (fixed)
V9_VOL_TARGET = 0.20
V9_VOL_WINDOW = 20
V9_CLAMP = (0.25, 2.0)
# V10 parameters (fixed)
V10_TRAIL_ATR_MULT = 3.0
V10_TIME_STOP_DAYS = 90


# --- market data ------------------------------------------------------------------

def load_market() -> dict:
    raw = json.loads(BARS_CACHE.read_text())
    bars_by_sym: dict[str, list[BarLike]] = {}
    for sym in raw:
        bars_by_sym[sym], _ = to_adjusted_barlikes(raw[sym])
    xbi = bars_by_sym["XBI"]
    calendar = [b.date for b in xbi if START <= b.date <= END]

    # adjusted closes forward-filled onto the XBI calendar (a halted name
    # marks at its last close — same convention as the addendum book)
    px: dict[str, dict[date, float | None]] = {}
    for sym, bars in bars_by_sym.items():
        by = {b.date: b.close for b in bars}
        series: dict[date, float | None] = {}
        last = None
        for d in calendar:
            if d in by:
                last = by[d]
            series[d] = last
        px[sym] = series

    # XBI vs its 50/200dma (close > SMA including the current bar — the exact
    # xbi_above_50dma convention the replay's regime_up rows used; kept ONLY
    # for the descriptive regime_up sanity check, never as a trading gate)
    closes = [b.close for b in xbi]
    above: dict[int, dict[date, bool]] = {50: {}, 200: {}}
    for n in (50, 200):
        s = 0.0
        for i, b in enumerate(xbi):
            s += closes[i]
            if i >= n:
                s -= closes[i - n]
            if i >= n - 1:
                above[n][b.date] = closes[i] > s / n

    # PRIOR-day gate series — COUNTER-AGENT CORRECTION (verdict 2026-08-20,
    # MATERIAL #1): the original run gated entries/rebalances on the gate
    # day's OWN close vs SMA while filling at that day's open — a same-day
    # look-ahead (the close is unknowable at the open). The actionable level
    # is the PRIOR trading day's close vs the prior-day SMA. ALL regime gates
    # (V1/V2/V4/V5/V6b/V10) now key off above_prior; the counter-agent's
    # rerun showed no survival verdict flips (asserted in main()).
    above_prior: dict[int, dict[date, bool]] = {50: {}, 200: {}}
    for n in (50, 200):
        for i in range(1, len(xbi)):
            prev = above[n].get(xbi[i - 1].date)
            if prev is not None:
                above_prior[n][xbi[i].date] = prev
    return {"bars": bars_by_sym, "calendar": calendar, "px": px,
            "xbi_above": above, "xbi_above_prior": above_prior}


def load_spy_curve(calendar: list[date]) -> list[tuple[date, float]]:
    rows = json.loads(SPY_RAW.read_text())["data"]
    by = {date.fromisoformat(r["t"]): r["a"] for r in rows
          if r.get("a") not in (None, 0)}
    curve, last, base = [], None, None
    for d in calendar:
        if d in by:
            last = by[d]
        if last is None:
            continue
        if base is None:
            base = last
        curve.append((d, START_EQUITY * last / base))
    return curve


def buyhold_curve(px: dict[date, float | None], calendar: list[date]) -> list[tuple[date, float]]:
    base = None
    curve = []
    for d in calendar:
        v = px[d]
        if v is None:
            continue
        if base is None:
            base = v
        curve.append((d, START_EQUITY * v / base))
    return curve


# --- selection (EXACT semantics of backtest_calls_10y.equity_curve) ---------------

def select_capped(rows: list[dict], cap: int | None) -> tuple[list[dict], int]:
    """Sort by (entry_date, symbol, flag); skip a fire when `cap` calls are
    already open at its entry date; a slot frees the day AFTER its exit."""
    ordered = sorted(rows, key=lambda t: (t["entry_date"], t["symbol"], t.get("flag", "")))
    taken: list[dict] = []
    open_exits: list[str] = []
    for t in ordered:
        open_exits = [x for x in open_exits if x >= t["entry_date"]]
        if cap is not None and len(open_exits) >= cap:
            continue
        taken.append(t)
        open_exits.append(t["exit_date"])
    return taken, len(rows) - len(taken)


# --- dollar-book engine -----------------------------------------------------------

def run_call_book(taken: list[dict], mkt: dict, *, hedge: bool = False,
                  vol_target: bool = False) -> list[tuple[date, float]]:
    """$100k book: risk RISK_FRAC of the PREVIOUS close's equity per call,
    daily MTM ((px-entry)/risk * risk_dollars) on adjusted closes, realized
    r_net on the exit date.

    hedge (V3/V4): per taken call an XBI short of equal dollar notional
    (risk_dollars/(entry-stop)*entry), opened at the entry-date close and
    closed at the exit-date close, no slippage/borrow (deep ETF; unmodeled).
    vol_target (V9): risk_frac_t = 0.01 * clamp(0.20/realized_vol, 0.25, 2.0)
    from the book's own trailing 20 daily returns (sample stdev, sqrt(252)
    annualization); the first 20 trading days use 1%.
    """
    calendar, px = mkt["calendar"], mkt["px"]
    xbi_px = px["XBI"]
    by_entry: dict[str, list[dict]] = {}
    for t in taken:
        by_entry.setdefault(t["entry_date"], []).append(t)

    cash = START_EQUITY
    open_pos: list[dict] = []
    curve: list[tuple[date, float]] = []
    prev_equity = START_EQUITY
    rets: list[float] = []

    for d in calendar:
        ds = d.isoformat()
        # 1. realize exits due today (r_net includes tiered slippage)
        still = []
        for p in open_pos:
            if p["row"]["exit_date"] <= ds:
                cash += p["rd"] * p["row"]["r_net"]
                if hedge:
                    xe = px["XBI"][date.fromisoformat(p["row"]["exit_date"])] \
                        if date.fromisoformat(p["row"]["exit_date"]) in xbi_px else xbi_px[d]
                    cash += -p["h_sh"] * (xe - p["h_px"])
            else:
                still.append(p)
        open_pos = still

        # 2. open entries (sized on the previous close's equity)
        frac = RISK_FRAC
        if vol_target and len(rets) >= V9_VOL_WINDOW:
            vol = statistics.stdev(rets[-V9_VOL_WINDOW:]) * math.sqrt(TRADING_DAYS)
            scale = V9_VOL_TARGET / vol if vol > 0 else V9_CLAMP[1]
            frac = RISK_FRAC * min(max(scale, V9_CLAMP[0]), V9_CLAMP[1])
        for t in by_entry.get(ds, []):
            rd = frac * prev_equity
            h_sh = h_px = 0.0
            if hedge:
                h_px = xbi_px[d]
                h_sh = (rd / t["risk"] * t["entry"]) / h_px
            if t["exit_date"] <= ds:  # same-bar exit: realize immediately
                cash += rd * t["r_net"]  # hedge opens+closes on the same close: 0 P&L
            else:
                open_pos.append({"row": t, "rd": rd, "h_sh": h_sh, "h_px": h_px})

        # 3. mark to market on adjusted closes
        mtm = 0.0
        for p in open_pos:
            t = p["row"]
            c = px[t["symbol"]][d]
            mtm += ((c - t["entry"]) / t["risk"]) * p["rd"]
            if hedge:
                mtm += -p["h_sh"] * (xbi_px[d] - p["h_px"])
        equity = cash + mtm
        curve.append((d, equity))
        if prev_equity > 0:
            rets.append(equity / prev_equity - 1)
        prev_equity = equity
    return curve


# --- V6: monthly cross-sectional momentum book -------------------------------------

def run_v6(mkt: dict, tiers: dict[str, str], universe: list[str],
           gated: bool) -> tuple[list[tuple[date, float]], int]:
    """Monthly rebalance at each month's first trading day: rank names by
    trailing 60-bar return minus XBI's, take the top 5 with liquidity tier
    A/B (no tier -> excluded), equal-weight 100% of equity; V6b holds cash
    when XBI <= 50dma as of the PRIOR trading day's close (counter-agent
    correction: the same-day close is not knowable before the rebalance
    execution). 10 bps per side on turnover. No stops; positions marked
    daily on adjusted closes."""
    calendar, px, bars = mkt["calendar"], mkt["px"], mkt["bars"]
    idx_by_date = {sym: {b.date: i for i, b in enumerate(bs)}
                   for sym, bs in bars.items()}
    # last bar index at-or-before each calendar date, per symbol
    eligible = [s for s in universe if tiers.get(s) in ("A", "B") and s in bars]

    rebal_days = []
    seen = set()
    for d in calendar:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            rebal_days.append(d)
    rebal_set = set(rebal_days)

    def ret60(sym: str, d: date) -> float | None:
        bs = bars[sym]
        i = idx_by_date[sym].get(d)
        if i is None:  # no bar today: use the last bar before d
            lo = [k for k, b in enumerate(bs) if b.date <= d]
            if not lo:
                return None
            i = lo[-1]
            if (d - bs[i].date).days > 7:
                return None  # stale — excluded this month
        if i < V6_LOOKBACK_BARS:
            return None
        c0, c1 = bs[i - V6_LOOKBACK_BARS].close, bs[i].close
        if not c0 or not c1:
            return None
        return c1 / c0 - 1

    cash = START_EQUITY
    shares: dict[str, float] = {}
    curve: list[tuple[date, float]] = []
    n_rebal = 0
    for d in calendar:
        pos_val = {s: sh * px[s][d] for s, sh in shares.items()}
        equity = cash + sum(pos_val.values())
        if d in rebal_set:
            n_rebal += 1
            picks: list[str] = []
            if not gated or mkt["xbi_above_prior"][50].get(d, False):
                xbi_r = ret60("XBI", d)
                scored = []
                for s in eligible:
                    r = ret60(s, d)
                    if r is not None and xbi_r is not None and px[s][d]:
                        scored.append((r - xbi_r, s))
                scored.sort(key=lambda x: (-x[0], x[1]))
                picks = [s for _, s in scored[:V6_TOP_N]]
            target_each = (equity / len(picks)) if picks else 0.0
            turnover = sum(abs((target_each if s in picks else 0.0) - pos_val.get(s, 0.0))
                           for s in set(picks) | set(pos_val))
            cost = V6_SLIPPAGE_PER_SIDE * turnover
            equity -= cost
            target_each = (equity / len(picks)) if picks else 0.0
            shares = {s: target_each / px[s][d] for s in picks}
            cash = equity - target_each * len(picks)
        curve.append((d, equity))
    return curve, n_rebal


# --- V10: trailing-ATR re-grade of the rel_strength fires --------------------------

def grade_trailing(bars: list[BarLike], atrs: list[float | None], j: int,
                   entry: float, expiry: date) -> tuple[str, date, float] | None:
    """Bar-walk from the entry bar j (entry at its open). Trailing stop =
    max(close since entry) - 3.0*ATR14, BOTH recomputed daily from bars up to
    the PRIOR close (the level actionable at today's open — no same-bar
    peeking); the trail is live from the bar after entry. Open-first,
    gap-aware like grade_call: an open at/below the trail fills at the open,
    an intrabar touch at the trail. Time stop at the close of the last bar
    at-or-before expiry. None while still open at data end."""
    peak: float | None = None
    prev: BarLike | None = None
    for k in range(j, len(bars)):
        b = bars[k]
        if b.low is None or b.high is None or b.close is None:
            continue
        if b.date > expiry:
            if prev is not None:
                return ("expired", prev.date, prev.close)
            return ("expired", b.date, b.open if b.open is not None else b.close)
        if peak is not None and atrs[k - 1] is not None:
            trail = peak - V10_TRAIL_ATR_MULT * atrs[k - 1]
            if b.open is not None and b.open <= trail:
                return ("stopped", b.date, b.open)
            if b.low <= trail:
                return ("stopped", b.date, trail)
        if b.date == expiry:
            return ("expired", b.date, b.close)
        peak = b.close if peak is None else max(peak, b.close)
        prev = b
    return None


def build_v10_rows(rs_rows: list[dict], mkt: dict, tiers: dict[str, str]) -> tuple[list[dict], int]:
    bars_by_sym = mkt["bars"]
    atr_cache: dict[str, list[float | None]] = {}
    idx_cache: dict[str, dict[date, int]] = {}
    out: list[dict] = []
    open_at_end = 0
    for t in rs_rows:
        sym = t["symbol"]
        bars = bars_by_sym[sym]
        if sym not in idx_cache:
            idx_cache[sym] = {b.date: i for i, b in enumerate(bars)}
            atr_cache[sym] = atr_series(bars)
        j = idx_cache[sym].get(date.fromisoformat(t["entry_date"]))
        if j is None:
            continue
        entry = t["entry"]                       # next open after fire (stored row)
        risk = t["risk"]                         # INITIAL 3xATR14 risk unit (build_levels)
        expiry = date.fromisoformat(t["entry_date"]) + timedelta(days=V10_TIME_STOP_DAYS)
        g = grade_trailing(bars, atr_cache[sym], j, entry, expiry)
        if g is None:
            open_at_end += 1
            continue
        status, exit_date, exit_px = g
        bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(sym, "C"), 100) / 10_000
        out.append({
            "fire_date": t["fire_date"], "entry_date": t["entry_date"],
            "symbol": sym, "flag": "rel_strength_60d_trail",
            "entry": entry, "risk": risk, "exit": exit_px,
            "exit_date": exit_date.isoformat(), "status": status,
            "r": (exit_px - entry) / risk,
            "r_net": (exit_px * (1 - bps) - entry * (1 + bps)) / risk,
            "hold_days": (exit_date - date.fromisoformat(t["entry_date"])).days,
            "regime_up": t.get("regime_up"),
        })
    return out, open_at_end


# --- statistics ---------------------------------------------------------------------

def seg_stats(curve: list[tuple[date, float]], lo: date, hi: date) -> dict:
    seg = [(d, v) for d, v in curve if lo <= d <= hi]
    if len(seg) < 2:
        return {}
    vals = [v for _, v in seg]
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
    years = (seg[-1][0] - seg[0][0]).days / 365.25
    cagr = (vals[-1] / vals[0]) ** (1 / years) - 1 if vals[0] > 0 else float("nan")
    peak, dd = -math.inf, 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak) if peak > 0 else dd
    mu = statistics.fmean(rets)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0.0
    downside = math.sqrt(statistics.fmean([min(r, 0.0) ** 2 for r in rets]))
    return {
        "start": seg[0][0].isoformat(), "end": seg[-1][0].isoformat(),
        "end_value": vals[-1], "cagr": cagr, "max_dd": dd,
        "sharpe": (mu / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan"),
        "sortino": (mu / downside * math.sqrt(TRADING_DAYS)) if downside > 0 else float("nan"),
        "calmar": (cagr / dd) if dd > 0 else float("nan"),
    }


def all_stats(curve: list[tuple[date, float]]) -> dict:
    out = {"full": seg_stats(curve, START, END)}
    for name, lo, hi in SUB_PERIODS:
        out[name] = seg_stats(curve, lo, hi)
    return out


def survives(stats: dict, v0: dict) -> bool:
    """The pre-registered bar: Sharpe AND Calmar beat V0 over the full period
    AND in at least 2 of 3 sub-periods."""
    def beats(a: dict, b: dict) -> bool:
        return (a and b and a["sharpe"] > b["sharpe"] and a["calmar"] > b["calmar"])
    if not beats(stats["full"], v0["full"]):
        return False
    wins = sum(1 for name, _, _ in SUB_PERIODS if beats(stats[name], v0[name]))
    return wins >= 2


def downsample(curve: list[tuple[date, float]], target: int = 400) -> list[list]:
    step = max(1, math.ceil(len(curve) / target))
    pts = curve[::step]
    if curve and pts[-1][0] != curve[-1][0]:
        pts.append(curve[-1])
    return [[d.isoformat(), round(v, 2)] for d, v in pts]


# --- V7 confluence qualifier --------------------------------------------------------

def v7_qualify(live_rows: list[dict], all_rows: list[dict], mkt: dict) -> list[dict]:
    """Keep a live-set row only if >=2 DISTINCT flag types (across all SIX
    replayed flag types' rows, incl. pullback_price_half) fired on the name
    within the trailing 5 trading days ending at its fire_date — the window
    measured on the symbol's own bar calendar."""
    fires_by_sym: dict[str, list[tuple[str, str]]] = {}
    for t in all_rows:
        fires_by_sym.setdefault(t["symbol"], []).append((t["fire_date"], t["flag"]))
    idx = {sym: {b.date.isoformat(): i for i, b in enumerate(bs)}
           for sym, bs in mkt["bars"].items()}
    out = []
    for t in live_rows:
        sym = t["symbol"]
        bars = mkt["bars"][sym]
        i = idx[sym].get(t["fire_date"])
        if i is None:
            continue
        lo = bars[max(0, i - 4)].date.isoformat()
        flags = {fl for fd, fl in fires_by_sym.get(sym, [])
                 if lo <= fd <= t["fire_date"]}
        if len(flags) >= 2:
            out.append(t)
    return out


# --- main ---------------------------------------------------------------------------

def main() -> None:  # noqa: PLR0915
    res = json.loads(CALLS_RESULTS.read_text())
    call_rows: dict[str, list[dict]] = res["call_rows"]
    tiers: dict[str, str] = res["tiers"]
    mkt = load_market()
    calendar = mkt["calendar"]
    universe = sorted(tiers)  # the replay's included names

    live_rows = [t for f in LIVE_SET_FLAGS for t in call_rows[f]]
    all_six_rows = [t for f in ALL_SIX_FLAGS for t in call_rows[f]]
    rs_rows = call_rows["rel_strength_60d"]

    # Gates use the PRIOR trading day's close vs prior-day SMA — the level
    # actionable at the entry date's open. COUNTER-AGENT CORRECTION
    # (verdict 2026-08-20, MATERIAL #1): the original run tested the entry
    # date's own close (same-day look-ahead, non-implementable at the open).
    up50 = mkt["xbi_above_prior"][50]
    up200 = mkt["xbi_above_prior"][200]

    def gate(rows: list[dict], above: dict[date, bool]) -> list[dict]:
        # entry-date gate only; a missing SMA value drops the entry (conservative)
        return [t for t in rows
                if above.get(date.fromisoformat(t["entry_date"]), False)]

    # sanity: our recomputed SAME-DAY 50dma regime matches the replay's stored
    # regime_up (which used the same-day convention DESCRIPTIVELY, never as a
    # trading rule — this check validates the SMA recomputation, not the gate)
    up50_sameday = mkt["xbi_above"][50]
    mismatch = sum(1 for t in live_rows
                   if t.get("regime_up") is not None
                   and t["regime_up"] != up50_sameday.get(date.fromisoformat(t["entry_date"])))
    assert mismatch == 0, f"50dma regime recomputation mismatches {mismatch} rows"

    curves: dict[str, list[tuple[date, float]]] = {}
    meta: dict[str, dict] = {}

    # V0 — baseline + machinery check
    taken0, skipped0 = select_capped(live_rows, CAP)
    assert len(taken0) == res["combined_book"]["summary"]["n"], "V0 selection drifted"
    curves["V0"] = run_call_book(taken0, mkt)
    meta["V0"] = {"desc": "combined live-flag book, <=10 open (baseline)",
                  "n_taken": len(taken0), "skipped_at_cap": skipped0}
    v0_full = seg_stats(curves["V0"], START, END)
    for key, exp in V0_EXPECTED.items():
        got = {"end": v0_full["end_value"], "cagr": v0_full["cagr"],
               "max_dd": v0_full["max_dd"], "sharpe": v0_full["sharpe"]}[key]
        assert abs(got - exp) <= max(0.01 * abs(exp), V0_TOL[key]), \
            f"V0 machinery check FAILED: {key} {got} vs documented {exp}"
    print(f"V0 machinery check PASSED: end ${v0_full['end_value']:,.0f} "
          f"CAGR {v0_full['cagr']:+.2%} maxDD {v0_full['max_dd']:.1%} "
          f"Sharpe {v0_full['sharpe']:.2f} (docs: $208,764 / +7.19% / 65.5% / 0.42)")

    # V1 / V2 — regime gates at entry
    t1, s1 = select_capped(gate(live_rows, up50), CAP)
    curves["V1"] = run_call_book(t1, mkt)
    meta["V1"] = {"desc": "V0 + entries only while XBI > 50dma",
                  "n_taken": len(t1), "skipped_at_cap": s1}
    t2, s2 = select_capped(gate(live_rows, up200), CAP)
    curves["V2"] = run_call_book(t2, mkt)
    meta["V2"] = {"desc": "V0 + entries only while XBI > 200dma",
                  "n_taken": len(t2), "skipped_at_cap": s2}

    # V3 / V4 — per-position XBI hedge (equal notional, no slippage/borrow)
    curves["V3"] = run_call_book(taken0, mkt, hedge=True)
    meta["V3"] = {"desc": "V0 + per-position equal-notional XBI short",
                  "n_taken": len(taken0), "skipped_at_cap": skipped0}
    curves["V4"] = run_call_book(t1, mkt, hedge=True)
    meta["V4"] = {"desc": "V1 gating + V3 hedging",
                  "n_taken": len(t1), "skipped_at_cap": s1}

    # V5 — rel_strength only + 50dma gate
    t5, s5 = select_capped(gate(rs_rows, up50), CAP)
    curves["V5"] = run_call_book(t5, mkt)
    meta["V5"] = {"desc": "rel_strength_60d fires only, <=10 open, 50dma gate",
                  "n_taken": len(t5), "skipped_at_cap": s5}

    # V6a / V6b — monthly cross-sectional momentum book
    curves["V6a"], n_rebal_a = run_v6(mkt, tiers, universe, gated=False)
    meta["V6a"] = {"desc": "monthly top-5 60-bar RS-vs-XBI book, tier A/B, equal weight",
                   "rebalances": n_rebal_a}
    curves["V6b"], n_rebal_b = run_v6(mkt, tiers, universe, gated=True)
    meta["V6b"] = {"desc": "V6a + 50dma regime gate (cash when off)",
                   "rebalances": n_rebal_b}

    # V7 — confluence (>=2 distinct flag types within trailing 5 trading days)
    q7 = v7_qualify(live_rows, all_six_rows, mkt)
    t7, s7 = select_capped(q7, CAP)
    curves["V7"] = run_call_book(t7, mkt)
    meta["V7"] = {"desc": "V0 + >=2 distinct flag types on the name within 5 trading days",
                  "n_qualifying": len(q7), "n_taken": len(t7), "skipped_at_cap": s7}

    # V8 — cap 5
    t8, s8 = select_capped(live_rows, 5)
    curves["V8"] = run_call_book(t8, mkt)
    meta["V8"] = {"desc": "V0 with max_open 5", "n_taken": len(t8), "skipped_at_cap": s8}

    # V9 — portfolio vol targeting (sizing only; same taken set as V0)
    curves["V9"] = run_call_book(taken0, mkt, vol_target=True)
    meta["V9"] = {"desc": "V0 + daily risk scaled to 20% target vol (clamp 0.25x-2x)",
                  "n_taken": len(taken0), "skipped_at_cap": skipped0}

    # V10 — EXPLORATORY trailing-ATR re-grade of rel_strength fires
    v10_rows, v10_open = build_v10_rows(rs_rows, mkt, tiers)
    t10, s10 = select_capped(gate(v10_rows, up50), CAP)
    curves["V10"] = run_call_book(t10, mkt)
    meta["V10"] = {"desc": "[EXPLORATORY] rel_strength, 3xATR trailing stop, 90d time stop, 50dma gate",
                   "n_regraded": len(v10_rows), "open_at_end_excluded": v10_open,
                   "n_taken": len(t10), "skipped_at_cap": s10,
                   "avg_r_net": statistics.fmean([t["r_net"] for t in v10_rows]),
                   "stop_rate": sum(1 for t in v10_rows if t["status"] == "stopped") / len(v10_rows),
                   "avg_hold_days": statistics.fmean([t["hold_days"] for t in v10_rows])}

    # Benchmarks
    curves["XBI"] = buyhold_curve(mkt["px"]["XBI"], calendar)
    curves["SPY"] = load_spy_curve(calendar)
    meta["XBI"] = {"desc": "XBI buy & hold (adjusted closes)"}
    meta["SPY"] = {"desc": "SPY buy & hold (adjusted closes)"}

    # Stats + verdicts
    order = ["V0", "V1", "V2", "V3", "V4", "V5", "V6a", "V6b", "V7", "V8",
             "V9", "V10", "XBI", "SPY"]
    stats = {k: all_stats(curves[k]) for k in order}
    v0s = stats["V0"]
    verdicts = {k: (survives(stats[k], v0s) if k not in ("V0",) else None)
                for k in order}

    # COUNTER-AGENT CORRECTION GUARD: the prior-day gate fix restates the
    # gated variants' magnitudes but — per the counter-agent's own rerun —
    # flips NO survival verdict. If any row below flips, the restatement is
    # wrong (or the engine drifted) and the run must fail loudly.
    expected_survival = {"V0": None, "V1": True, "V2": True, "V3": False,
                         "V4": False, "V5": False, "V6a": True, "V6b": True,
                         "V7": True, "V8": False, "V9": False, "V10": True,
                         "XBI": True, "SPY": True}
    flips = {k: (expected_survival[k], verdicts[k]) for k in order
             if verdicts[k] != expected_survival[k]}
    assert not flips, ("SURVIVAL VERDICT FLIPPED after the prior-day gate "
                       f"correction — counter-agent predicted none: {flips}")
    print("Survival column UNCHANGED after the prior-day gate correction "
          "(counter-agent guard passed)")

    # Sanity: non-degenerate curves, no NaNs, V6 rebalance count
    for k in order:
        vals = [v for _, v in curves[k]]
        assert len(vals) > 2000 and min(vals) > 0, f"{k}: degenerate curve"
        assert len({round(v, 2) for v in vals}) > 100, f"{k}: flat curve"
        for seg in stats[k].values():
            for key, v in seg.items():
                assert not (isinstance(v, float) and math.isnan(v)), f"{k}.{key} NaN"
    assert 120 <= n_rebal_a <= 130 and n_rebal_a == n_rebal_b, \
        f"V6 rebalances {n_rebal_a}/{n_rebal_b} != ~128"
    print(f"Sanity PASSED: 14 curves x {len(calendar)} days, no NaNs, "
          f"V6 rebalances {n_rebal_a}")

    _print_table(order, stats, verdicts)
    _write_results(order, stats, verdicts, curves, meta)
    _write_report(order, stats, verdicts, meta)
    print(f"\nReport written to {REPORT}")
    print(f"Results JSON written to {RESULTS}")


def _fmt_row(k: str, s: dict, verdict: bool | None) -> str:
    f = s["full"]
    sv = "—" if verdict is None else ("YES" if verdict else "no")
    return (f"| {k} | ${f['end_value']:,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
            f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {sv} |")


def _print_table(order, stats, verdicts) -> None:
    print("\nvariant | end$ | CAGR | maxDD | Sharpe | Sortino | Calmar | survives?")
    for k in order:
        f = stats[k]["full"]
        sv = "—" if verdicts[k] is None else ("YES" if verdicts[k] else "no")
        print(f"{k:5s} | ${f['end_value']:>9,.0f} | {f['cagr']:+.2%} | {f['max_dd']:.1%} "
              f"| {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['calmar']:.2f} | {sv}")


def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def _write_results(order, stats, verdicts, curves, meta) -> None:
    RESULTS.write_text(json.dumps(_round({
        "generated": datetime.now(timezone.utc).isoformat(),
        "contract": "docs/VARIANTS_PREREGISTRATION.md",
        "period": [START.isoformat(), END.isoformat()],
        "sub_periods": {n: [lo.isoformat(), hi.isoformat()] for n, lo, hi in SUB_PERIODS},
        "protocol": {"start_equity": START_EQUITY, "risk_frac": RISK_FRAC,
                     "sizing_basis": "previous close equity", "rf": 0,
                     "mtm": "adjusted closes, forward-filled on the XBI calendar",
                     "regime_gates": ("PRIOR trading day's close vs prior-day SMA "
                                      "(counter-agent correction 2026-08-20: the "
                                      "first run's same-day gate was a look-ahead; "
                                      "restated, no survival flips)"),
                     "curves_note": ("curve arrays are downsampled to ~400 pts for "
                                     "display only — stats were computed from the "
                                     "full daily curves; do not recompute maxDD "
                                     "from the stored points"),
                     "survives": "Sharpe AND Calmar > V0, full period AND >=2 of 3 sub-periods"},
        "variants": {k: {"meta": meta[k], "stats": stats[k],
                         "survives": verdicts[k],
                         "curve": downsample(curves[k])} for k in order},
    }), default=str))


def _write_report(order, stats, verdicts, meta) -> None:
    lines: list[str] = []
    w = lines.append
    w("# 10-Year Variant Campaign — pre-registered (VARIANTS_PREREGISTRATION.md)")
    w("")
    w(f"_Generated by `scripts/backtest_variants_10y.py` · {START} → {END} · "
      f"reuses the per-call rows and adjusted bars of BACKTEST_CALLS_10Y.md; "
      f"fires were NOT regenerated (except V10's exit re-grade, per contract)_")
    w("")
    w("## Read this first")
    w("")
    w("Inherits EVERY caveat of BACKTEST_CALLS_10Y.md — one line each:")
    w("")
    w("- **Survivorship**: today's universe; dead names absent — absolute numbers flattered.")
    w("- **Alias/universe hindsight**: today's aliases and membership applied across all 10 years.")
    w("- **PIT submit-date lag**: catalyst knowledge at CT.gov posting granularity.")
    w("- **No composite/confidence gates**: every suppressed fire trades at fixed fraction —")
    w("  the live engine would trade fewer, larger calls.")
    w("- **Unreplayable live triggers**: sentiment/revision/options lanes absent; this is the")
    w("  replayable shadow, not the live book.")
    w("")
    w("Campaign-specific caveats:")
    w("")
    w("- **11 variants = multiple comparisons**: one full-period winner alone is noise;")
    w("  the pre-registered bar (Sharpe AND Calmar, full period AND ≥2/3 sub-periods) is the test.")
    w("- **V10 is EXPLORATORY** (different exit engine, highest overfit risk — flagged in the")
    w("  contract; a survival here is a hypothesis to re-derive, not a result).")
    w("- **V6 is a different engine shape**: monthly rebalance, always-in, no stops — its")
    w("  Sharpe/Calmar are not like-for-like with call books, though the bar is applied anyway;")
    w("  V6a additionally carries the warnings in its own block below the table.")
    w("- **Hedging costs nothing here**: V3/V4's XBI shorts carry no borrow/fees/slippage")
    w("  (deep ETF, but not free in practice) — treat hedged results as upper bounds.")
    w("- **rf = 0 understates the gated variants**: V1/V2/V6b sit in cash for large fractions")
    w("  of the decade and real cash earns T-bills (~2%+ avg 2016–2026) — the omission's")
    w("  direction FAVORS them in reality.")
    w("- **XBI buy-and-hold itself clears the survival bar vs V0**: \"survives\" means")
    w("  \"better than a strategy that was no better than its own sector ETF\" — this")
    w("  campaign is fixing a broken baseline, not certifying alpha.")
    w("- **Survivors are HYPOTHESES** (TUNING.md law): never direct config changes.")
    w("")
    w("## Protocol")
    w("")
    w("$100k start · risk 1% of the previous close's equity per call (V9 scales this; V6")
    w("is fully invested) · daily MTM on adjusted closes ((px−entry)/risk × risk$) ·")
    w("realized r_net (tiered slippage A=10/B=40/C=100 bps per side) on the exit date ·")
    w("rf = 0 · Sharpe/Sortino annualized √252 · sub-period stats on that segment of the")
    w("same curve, CAGR annualized on segment length. Machinery check: V0 reproduces the")
    w("BACKTEST_CALLS_10Y.md addendum ($208,764 / +7.19% / 65.5% / 0.42) within ±1%.")
    w("")
    w("**SURVIVES** = Sharpe AND Calmar beat V0 over the full period AND in ≥2 of 3")
    w("sub-periods (2016-2019, 2020-2022, 2023-2026Aug).")
    w("")
    w("## Full period 2016-01-04 → 2026-08-19")
    w("")
    w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | SURVIVES |")
    w("|---|---|---|---|---|---|---|---|")
    for k in order:
        w(_fmt_row(k, stats[k], verdicts[k]))
    w("")
    v6a = stats["V6a"]["full"]
    w("### V6a — do NOT carry the headline number without these")
    w("")
    w(f"- **{v6a['max_dd']:.1%} max drawdown is untradeable as a standalone book.** No")
    w("  mandate survives it; the row is an engine-shape comparison, not a candidate book.")
    w("- **5-name equal weight is extreme idiosyncratic concentration**: each pick is a")
    w("  binary-event lottery ticket at 20% of the book, drawn from a 24-name eligible")
    w("  universe.")
    w("- **Cross-sectional momentum on a survivor-only universe is the WORST CASE of the")
    w("  inherited survivorship bias**: \"buy the recent winners among names known today to")
    w("  have survived and mattered\" — the blown-up names momentum would have chased into")
    w("  zero (the strategy's actual tail) are absent by construction. **V6a's absolute")
    w("  CAGR is unusable.** The ONLY reading that survives is the RELATIVE one: momentum")
    w("  ranking adds selection value INSIDE this universe.")
    w("- Robustness (counter-agent reruns): the plumbing is NOT manufacturing the result —")
    w("  no tier filter (all 32 names) ends at $2,177,355 (BETTER: the hindsight tier")
    w("  filter cost ~3pp CAGR); tier-true costs (B=40 bps/side) end at $1,529,190")
    w("  (−1.3pp CAGR, still clears the bar); a 1-day execution delay also survives.")
    w("  The universe and the drawdown are the problem, not the tier filter or the costs.")
    w("")
    for name, _, _ in SUB_PERIODS:
        w(f"## Sub-period {name}")
        w("")
        w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | beats V0 (Sharpe&Calmar) |")
        w("|---|---|---|---|---|---|---|---|")
        v0 = stats["V0"][name]
        for k in order:
            s = stats[k][name]
            beat = "—" if k == "V0" else \
                ("yes" if (s["sharpe"] > v0["sharpe"] and s["calmar"] > v0["calmar"]) else "no")
            w(f"| {k} | ${s['end_value']:,.0f} | {s['cagr']:+.2%} | {s['max_dd']:.1%} "
              f"| {s['sharpe']:.2f} | {s['sortino']:.2f} | {s['calmar']:.2f} | {beat} |")
        w("")
    w("## Variant notes")
    w("")
    for k in order:
        m = meta[k]
        extra = ", ".join(f"{kk}={vv:,.3f}" if isinstance(vv, float) else f"{kk}={vv}"
                          for kk, vv in m.items() if kk != "desc")
        w(f"- **{k}** — {m['desc']}" + (f" ({extra})" if extra else ""))
    w("")
    w("## Ambiguity calls (most conservative reading, per contract)")
    w("")
    w("- Sizing equity reference = the PREVIOUS close's equity (reproduces the addendum")
    w("  book to $4; a same-close reference would embed a look-ahead).")
    w("- V3/V4 hedge notional fixed at entry (never rebalanced), opened/closed at the")
    w("  entry/exit-date XBI closes, zero costs (noted above as an upper bound).")
    w("- V7 window = the symbol's own last 5 trading days ending at fire_date; the fire")
    w("  record is the replay's graded call rows (fires still open at data end are absent).")
    w("- V9 vol = sample stdev of the book's trailing 20 daily returns × √252; the scaled")
    w("  fraction applies to entries from day 21 on (first 20 trading days at 1%).")
    w("- V10 trail uses peak close AND ATR14 through the PRIOR bar (the level actionable")
    w("  at today's open — recomputed daily, per the registered 'trailing' reading); the")
    w("  trail activates the bar after entry; initial risk unit = the stored build_levels")
    w("  risk (3×ATR14 with the 0.5×entry cap); fires still open at data end excluded,")
    w("  matching the replay's convention.")
    w("- V6 turnover cost computed on pre-cost target turnover, then post-cost equity")
    w("  split equally; a name with no bar within 7 days of a rebalance is excluded that")
    w("  month; if fewer than 5 names qualify, the qualifiers are equal-weighted.")
    w("- Regime gates (V1/V2/V4/V5/V10 entries; V6b rebalances) test the PRIOR trading")
    w("  day's close vs the prior-day SMA — the level actionable at the fill. RESTATED:")
    w("  the first run gated on the gate day's own close, a same-day look-ahead the")
    w("  counter-agent caught (its rerun: no survival flips; magnitudes restated here).")
    w("  An undefined SMA drops the entry (never binds: XBI has full history).")
    w("")
    w("## Counter-agent verdict")
    w("")
    w("**PASS WITH CORRECTIONS (2026-08-20)** — adversarial review before results were")
    w("acted on (scratch reruns; repo untouched during review):")
    w("")
    w("- Pre-registration commit verified to PREDATE the results (contract committed")
    w("  before the results JSON was generated; prereg file byte-identical to the")
    w("  committed version).")
    w("- Reproduction EXACT: all 14 curves reproduce independently to ≤2.2e-4 relative;")
    w("  independent Sharpe/Sortino/Calmar math matches to 4dp; V0 machinery check")
    w("  reproduces the addendum book.")
    w("- **Same-day gate look-ahead found and FIXED**: the original run gated")
    w("  V1/V2/V4/V5/V6b/V10 on the gate day's own close while filling at that day's")
    w("  open/close — non-implementable. All gates now use the prior trading day's")
    w("  close vs prior-day SMA; the tables in THIS document are the restated numbers.")
    w("- **V6a reframed**: untradeable-as-standalone DD, 5-name concentration,")
    w("  survivorship worst-case — see the V6a block under the full-period table.")
    w("- **Survival verdicts UNCHANGED by the correction** (asserted in the script;")
    w("  any flip fails the run loudly).")
    w("")
    w("## Verdict")
    w("")
    survivors = [k for k in order if verdicts[k] and k not in ("XBI", "SPY")]
    bench_pass = [k for k in ("XBI", "SPY") if verdicts[k]]
    if bench_pass:
        w(f"_Benchmark rows clearing the same bar (context, not variants): "
          f"{', '.join(bench_pass)}._ Read that plainly: **XBI buy-and-hold itself")
        w("beats V0 on the pre-registered criterion**, so \"survives vs V0\" means")
        w("\"better than a strategy that was itself no better than its sector ETF\" —")
        w("a low bar (fixing a broken baseline), not evidence of alpha. SPY dominates")
        w("every survivor except V6a on end value, with a fraction of V6a's drawdown.")
        w("")
    if survivors:
        w(f"Survivors under the pre-registered bar: **{', '.join(survivors)}**. Per the")
        w("contract these become HYPOTHESES.md entries / TUNING proposals — never direct")
        w("config changes. Everything else is registered as failed in this round; any")
        w("refinement goes to a NEXT round's registration.")
    else:
        w("**No variant survived** the pre-registered bar. Per the contract, nothing is")
        w("promoted; follow-up ideas go to a NEXT round's registration.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
