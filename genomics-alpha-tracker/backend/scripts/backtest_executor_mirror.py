"""Executor-mirror replay of the blend3070 book (ibkr-executor/app/blend.py)
on the R2-A fire set — "how would the geo executor have done over 2/5/10
years, and how do we know the max DD?" (Casey, 2026-10-01).

The R2-A paper book (docs/BACKTEST_VARIANTS_R2.md) is a dollar book with
fractional shares, no cash constraint, no commissions, entry at the NEXT
open, a trail that may FALL when ATR rises, and a 90-day stop anchored at
the entry bar. The executor is none of those things. This script replays
the SAME 5,008 fire rows and the SAME bars with the executor's mechanics,
one delta at a time (the variant ladder), so every difference to the paper
number is attributable:

  L0  r2a_ref                 run_call_book(taken)            [reused, asserted to $1]
  L0b r2a_ref_carry           run_call_book_yield(taken, BIL)  [reused]
  L1  exec_t1_nocost_nocarry  executor mechanics only (whole shares, cash clip,
                              uncapped 3xATR risk, day-zero STP, ratchet-up-only
                              trail seeded at the fire close, fire-anchored
                              next-open time stop), T+1 fill, no costs, no carry
  L2  exec_t1_nocarry         + IBKR fixed commissions + $1 BIL raise/sweep
  L3  exec_t2_nocarry         + T+2 fill (pre-fund BIL sell -> MOO post-close)
  L4  exec_t2_carry           + BIL carry on idle sleeve cash   == PRIMARY 0/100
  L5  exec_t1_carry           T+1 at full realism (T+1 vs T+2 delta = L5 - L4)
  B1  blend3070_t2_carry      30/70 with the executor's 5pp band rebalance == PRIMARY comparison
  B2  blend3070_t1_carry      30/70, T+1
  P1  blend3070_paper_t2_carry 30/70 as R3's daily-rebalanced PAPER mix of L4 and SPY

Everything that already exists is IMPORTED, never re-implemented: the bars
loader, the cap selector, the R2-A book, seg_stats, downsample, the BIL
yield loader, the R3 blend helpers. Two machinery checks run before any
number is reported: (1) the reused R2-A recipe reproduces the stored
$430,406.29 within the repo's V0 machinery tolerance (+/-1%, the gate
backtest_variants_10y.py and backtest_summary.py apply) — cache_exact says
whether it also lands to $1; a miss means the bars are not on the campaign
basis (abort, or --allow-cache-drift to publish with cache_verified=false);
(2) the new engine in r2a_mode reduces to run_call_book to 1e-6.

The bars cache (backend/data/backtest_bars.json) is gitignored. The August
2026 campaign cache (raw Yahoo chart API) no longer exists anywhere — it was
built in a cloud session and never committed. The reproducible lane is
`python -m scripts.refresh_backtest_bars` (FMP dividend-adjusted bars, ATAI
basis-normalized, needs FMP_API_KEY), which this script runs for you with
--refresh-bars, or automatically when the cache is absent; the Render data
disk keeps the result across deploys. Tests drive the engines on synthetic
bars (tests/test_executor_mirror.py); no data is read at import time.

Usage:  python -m scripts.backtest_executor_mirror [--out PATH] [--report PATH]
            [--fetch-missing] [--allow-cache-drift] [--draws 2000] [--seed 20261001]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike  # noqa: E402
from scripts.backtest_calls import (  # noqa: E402
    CACHE,
    SLIPPAGE_BPS_BY_TIER,
    fetch_bars,
)
from scripts.backtest_signals import atr_series  # noqa: E402
from scripts.backtest_variants_10y import (  # noqa: E402
    CALLS_RESULTS,
    CAP,
    LIVE_SET_FLAGS,
    RISK_FRAC,
    SPY_RAW,
    START_EQUITY,
    downsample,
    load_market,
    run_call_book,
    seg_stats,
    select_capped,
)
from scripts.backtest_variants_r2 import (  # noqa: E402
    RESULTS as R2_RESULTS,
    build_trailing_rows,
    load_bil_yield,
    run_call_book_yield,
)
from scripts.backtest_variants_r3 import (  # noqa: E402
    R2A_END,
    RESULTS as R3_RESULTS,
    compound,
    max_dd_of,
    sleeve_returns,
)

DATA = Path(__file__).resolve().parent.parent / "data"
SEED_DATA = Path(__file__).resolve().parent.parent / "seed_data"   # image copy (Dockerfile)


def _input(path: Path) -> Path:
    """A committed input: backend/data/<name> if present, else the image's
    seed_data/<name>. On Render the persistent disk is mounted AT /app/data
    and hides the committed files; the Dockerfile keeps a copy in seed_data."""
    if path.exists():
        return path
    alt = SEED_DATA / path.name
    return alt if alt.exists() else path


RESULTS = DATA / "backtest_executor_mirror_results.json"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_EXECUTOR_MIRROR.md"
SCRIPT = "scripts/backtest_executor_mirror.py"

# Bootstrap (stationary block, mean block 21 trading days; new seed, documented)
BOOT_DRAWS = 2000
BOOT_MEAN_BLOCK = 21
BOOT_SEED = 20261001
WINDOW_SEED_OFFSET = {"full": 0, "5y": 1, "2y": 2}
TRAILING_WINDOWS = (("5y", 5), ("2y", 2))
BOOTSTRAP_VARIANTS = ("exec_t2_carry", "blend3070_t2_carry")

# Executor cost assumptions (ibkr-executor/README.md: "$1.00 commission each"
# on the live SPY/BIL legs = IBKR Fixed: $0.005/sh, $1.00 min, 1% of value max)
IBKR_FIXED_PER_SHARE = 0.005
IBKR_FIXED_MIN = 1.0
IBKR_FIXED_MAX_FRAC = 0.01
SPY_BPS = 10 / 10_000           # tier-A slippage on the core ETF, per side
MIN_ORDER_USD = 50.0            # blend.py MIN_ORDER_USD: core/BIL dust floor
MACHINERY_TOL_USD = 1.0          # cache_exact: the campaign cache lands to the dollar
MACHINERY_TOL_REL = 0.01         # cache_verified: the repo's V0 machinery gate (+/-1%)
BASIS_SIDECAR = DATA / "backtest_bars_basis.json"   # written by scripts/refresh_backtest_bars.py
R2A_DAILY = DATA / "r2a_daily.json"                 # the frozen R2-A dollar curve (committed)
# Curve-level reproduction tolerances (the V0 gate's max_dd / sharpe tolerances
# from backtest_variants_10y.V0_TOL; the point-wise gap uses the same 1%)
CURVE_TOL_REL = 0.01
MAXDD_TOL = 0.0065
SHARPE_TOL = 0.005
REDUCTION_TOL = 1e-6

REPORT_BEGIN = "<!-- RESULTS:BEGIN (written by scripts/backtest_executor_mirror.py — do not edit by hand) -->"
REPORT_END = "<!-- RESULTS:END -->"


# --- configuration ------------------------------------------------------------------

@dataclass(frozen=True)
class ExecCfg:
    """One knob per executor-vs-paper delta (see the module docstring)."""
    # ENGINE A — per-fire bar walk
    entry_lag: int = 2                   # fill = open of the bar `entry_lag` sessions after the fire bar
    peak_seed: str = "fire_close"        # 'fire_close' (tracker shadow.py) | 'entry_close' (grade_trailing)
    ratchet: bool = True                 # trail ratchets up only (shadow.py) vs may fall (10y grade_trailing)
    day_zero_stop: bool = True           # protective STP GTC resting from the fill
    risk_cap: float | None = None        # None = uncapped 3xATR (executor); 0.5 = build_levels' 0.5*entry cap
    time_stop_anchor: str = "fire"       # 'fire' (tracker deadline = call_date + 90) | 'entry' (R2-A)
    time_stop_fill: str = "next_open"    # 'next_open' (~10:30 MKT after the tracker's signal) | 'deadline_close'
    trail_mult: float = 3.0
    time_stop_days: int = 90
    # ENGINE B — daily ledger book
    sleeve_target: float = 1.0           # 1.0 sleeve-only | 0.30 = the H13 30/70 book
    band: float = 0.05
    risk_frac: float = RISK_FRAC
    integer_shares: bool = True
    cash_clip: bool = True               # qty <= floor(spendable sleeve cash / entry_ref)
    commission_model: str = "ibkr_fixed"  # 'none' | 'flat' (commission_usd per order) | 'ibkr_fixed'
    commission_usd: float = 1.0          # the flat per-order charge; also the BIL/SPY order charge
    bil_order_cost: bool = True          # +$1 BIL sell at entry (pre-fund), +$1 re-sweep at exit
    carry: bool = True                   # idle sleeve cash earns BIL total return (needs a yield series)
    paper_arith: bool = False            # run_call_book P&L arithmetic (reduction check only)

    @property
    def label(self) -> str:
        return (f"lag={self.entry_lag} seed={self.peak_seed} ratchet={self.ratchet} "
                f"dz_stop={self.day_zero_stop} cap={self.risk_cap} ts={self.time_stop_anchor}/"
                f"{self.time_stop_fill} target={self.sleeve_target} int={self.integer_shares} "
                f"clip={self.cash_clip} comm={self.commission_model} bil$={self.bil_order_cost} "
                f"carry={self.carry}")


EXEC_T2 = ExecCfg()
EXEC_T1 = replace(EXEC_T2, entry_lag=1)

# The paper R2-A recipe expressed in the new engine's knobs: MUST reduce to
# build_trailing_rows + run_call_book exactly (machinery check 2).
R2A_MODE = ExecCfg(
    entry_lag=1, peak_seed="entry_close", ratchet=False, day_zero_stop=False,
    risk_cap=0.5, time_stop_anchor="entry", time_stop_fill="deadline_close",
    sleeve_target=1.0, integer_shares=False, cash_clip=False,
    commission_model="none", bil_order_cost=False, carry=False, paper_arith=True,
)


def ibkr_fixed(qty: float, notional: float) -> float:
    """IBKR Fixed US-stock schedule: $0.005/share, $1.00 minimum, capped at
    1% of trade value (README.md: "$1.00 commission each")."""
    if qty <= 0 or notional <= 0:
        return 0.0
    return min(max(IBKR_FIXED_MIN, IBKR_FIXED_PER_SHARE * qty), IBKR_FIXED_MAX_FRAC * notional)


def commission(cfg: ExecCfg, qty: float, notional: float) -> float:
    if cfg.commission_model == "none" or qty <= 0:
        return 0.0
    if cfg.commission_model in ("flat", "flat1"):
        return cfg.commission_usd if cfg.commission_model == "flat" else 1.0
    if cfg.commission_model == "ibkr_fixed":
        return ibkr_fixed(qty, notional)
    raise ValueError(f"unknown commission_model {cfg.commission_model!r}")


# --- ENGINE A: per-fire bar walk with the executor's exit mechanics ------------------

def grade_executor(bars: list[BarLike], atrs: list[float | None], i_fire: int,
                   cfg: ExecCfg, *, stored_entry: float | None = None,
                   stored_risk: float | None = None) -> dict | None:
    """Walk one fire from its fire bar under `cfg`. Size-independent, so rows
    are graded once per lag (like build_trailing_rows) and re-used by every
    book that shares the lag.

    Returns None while still open at data end (excluded, counted by the
    caller), a dict with status 'skip_*' when the tracker would never have
    published a tradeable row, else the graded row core.

    Executor semantics (cfg = EXEC_*): fill = open of bars[i_fire+entry_lag];
    L0 = close_fire - trail_mult*ATR14 through the fire day (the published
    stop; <= 0 -> 'no sizing reference', skipped); per-share risk = close_fire
    - L0 (UNCAPPED); peak seeded at the fire close, trail live from the bar
    after the fire day, ratchets up only, open-first gap fills; a protective
    stop rests from the fill bar; deadline = fire_date + 90 calendar days,
    exit at the open of the first bar after it. With lag 2 the pre-fill bar
    still moves the tracker's trail; if it pierces, the tracker publishes an
    exit the fill morning: the MOO fills and the executor MKT-sells the same
    day (close approximation) unless the resting L0 stop fills first.

    Paper semantics (cfg = R2A_MODE + stored_entry/stored_risk): exactly
    grade_trailing (10y.py) on the stored row — asserted in run_mirror.
    """
    n = len(bars)
    fb = bars[i_fire]
    if fb.close is None or fb.close <= 0:
        return {"status": "skip_no_fire_close"}
    j = i_fire + cfg.entry_lag
    if j >= n:
        return None
    eb = bars[j]
    fill = eb.open if eb.open is not None else None
    if fill is None or fill <= 0 or eb.close is None:
        return {"status": "skip_no_open"}
    close_fire = fb.close
    atr_fire = atrs[i_fire]
    mult = cfg.trail_mult
    L0 = (close_fire - mult * atr_fire) if (atr_fire is not None and atr_fire > 0) else None

    if stored_risk is not None:
        risk = stored_risk
    else:
        if atr_fire is None or atr_fire <= 0:
            return {"status": "skip_no_sizing_reference"}
        risk = mult * atr_fire
        if cfg.risk_cap is not None:
            risk = min(risk, cfg.risk_cap * fill)
    if cfg.day_zero_stop and (L0 is None or L0 <= 0):
        return {"status": "skip_no_sizing_reference"}   # blend.py:1172-1176
    entry = stored_entry if stored_entry is not None else fill

    # trail state before the fill
    if cfg.peak_seed == "fire_close":
        peak: float | None = close_fire
        trail: float | None = L0
    else:
        peak, trail = None, None
    prefill = False
    for k in range(i_fire + 1, j):          # pre-fill bars (lag >= 2 only)
        b = bars[k]
        if b.low is None or b.high is None or b.close is None:
            continue
        if peak is not None and atrs[k - 1] is not None:
            level = peak - mult * atrs[k - 1]
            trail = level if (trail is None or not cfg.ratchet) else max(trail, level)
        if trail is not None and ((b.open is not None and b.open <= trail) or b.low <= trail):
            prefill = True
        if cfg.peak_seed == "fire_close":
            peak = max(peak, b.close)

    anchor = fb.date if cfg.time_stop_anchor == "fire" else eb.date
    deadline = anchor + timedelta(days=cfg.time_stop_days)
    core = {"entry_date": eb.date, "fill": fill, "entry": entry, "risk": risk,
            "entry_ref": close_fire, "stop0": L0, "prefill_exit": prefill,
            "gate_date": bars[i_fire + 1].date}

    if prefill:
        if eb.open <= L0:
            exit_px = eb.open
        elif eb.low is not None and eb.low <= L0:
            exit_px = L0
        else:
            exit_px = eb.close
        return {**core, "status": "prefill_exit", "exit_date": eb.date, "exit": exit_px}

    prev: BarLike | None = None
    for k in range(j, n):
        b = bars[k]
        if b.low is None or b.high is None or b.close is None:
            continue
        if b.date > deadline:
            if cfg.time_stop_fill == "next_open":
                px = b.open if b.open is not None else b.close
                return {**core, "status": "expired", "exit_date": b.date, "exit": px}
            if prev is not None:                       # grade_trailing semantics
                return {**core, "status": "expired", "exit_date": prev.date, "exit": prev.close}
            px = b.open if b.open is not None else b.close
            return {**core, "status": "expired", "exit_date": b.date, "exit": px}
        if peak is not None and atrs[k - 1] is not None:
            level = peak - mult * atrs[k - 1]
            trail = level if (trail is None or not cfg.ratchet) else max(trail, level)
        elif not cfg.ratchet:
            trail = None                               # grade_trailing: no level, no stop
        if trail is not None and (k > j or cfg.day_zero_stop):
            if b.open is not None and b.open <= trail:
                return {**core, "status": "stopped", "exit_date": b.date, "exit": b.open}
            if b.low <= trail:
                return {**core, "status": "stopped", "exit_date": b.date, "exit": trail}
        if cfg.time_stop_fill == "deadline_close" and b.date == deadline:
            return {**core, "status": "expired", "exit_date": b.date, "exit": b.close}
        peak = b.close if peak is None else max(peak, b.close)
        prev = b
    return None


def build_exec_rows(fire_rows: list[dict], mkt: dict, tiers: dict[str, str],
                    cfg: ExecCfg) -> tuple[list[dict], dict]:
    """Grade every fire row under cfg. In paper_arith (R2A_MODE) the stored
    row's entry/risk are used so the result is row-for-row build_trailing_rows."""
    bars_by_sym = mkt["bars"]
    atr_cache: dict[str, list[float | None]] = {}
    idx_cache: dict[str, dict[date, int]] = {}
    out: list[dict] = []
    meta = {"n_fires": len(fire_rows), "open_at_end_excluded": 0, "no_fire_bar": 0,
            "skip_no_open": 0, "skip_no_sizing_reference": 0, "skip_no_fire_close": 0,
            "prefill_exit": 0}
    for t in fire_rows:
        sym = t["symbol"]
        bars = bars_by_sym.get(sym)
        if not bars:
            meta["no_fire_bar"] += 1
            continue
        if sym not in idx_cache:
            idx_cache[sym] = {b.date: i for i, b in enumerate(bars)}
            atr_cache[sym] = atr_series(bars)
        i_fire = idx_cache[sym].get(date.fromisoformat(t["fire_date"]))
        if i_fire is None or i_fire + 1 >= len(bars):
            meta["no_fire_bar"] += 1
            continue
        kw = ({"stored_entry": t["entry"], "stored_risk": t["risk"]}
              if cfg.paper_arith else {})
        g = grade_executor(bars, atr_cache[sym], i_fire, cfg, **kw)
        if g is None:
            meta["open_at_end_excluded"] += 1
            continue
        if g["status"].startswith("skip_"):
            meta[g["status"]] += 1
            continue
        if g["prefill_exit"]:
            meta["prefill_exit"] += 1
        bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(sym, "C"), 100) / 10_000
        entry, risk, exit_px = g["entry"], g["risk"], g["exit"]
        out.append({
            "fire_date": t["fire_date"], "entry_date": g["entry_date"].isoformat(),
            "gate_date": g["gate_date"].isoformat(),
            "symbol": sym, "flag": t["flag"] + ("_trail" if cfg.paper_arith else "_exec"),
            "entry": entry, "fill": g["fill"], "entry_ref": g["entry_ref"],
            "risk": risk, "stop0": g["stop0"], "exit": exit_px,
            "exit_date": g["exit_date"].isoformat(), "status": g["status"],
            "prefill_exit": g["prefill_exit"], "bps": bps,
            "r": (exit_px - entry) / risk,
            "r_net": (exit_px * (1 - bps) - entry * (1 + bps)) / risk,
            "hold_days": (g["exit_date"] - g["entry_date"]).days,
            "regime_up": t.get("regime_up"),
        })
    return out, meta


def gate_rows(rows: list[dict], above: dict[date, bool], key: str = "gate_date") -> list[dict]:
    """200dma PRIOR-close gate keyed on fire_date+1 (= the R2-A entry date)
    for BOTH lags: the tracker evaluates it when it publishes the fire on the
    morning after the fire bar, with bars through the fire day. A missing SMA
    drops the entry (never binds)."""
    return [t for t in rows if above.get(date.fromisoformat(t[key]), False)]


# --- ENGINE B: daily ledger book (sleeve cash / BIL carry / whole shares / SPY core) --

def run_executor_book(rows: list[dict], mkt: dict, cfg: ExecCfg, *,
                      cash_yield: dict[date, float] | None = None,
                      spy_px: dict[date, float | None] | None = None) -> dict:
    """Daily loop on mkt['calendar'] with explicit ledgers.

    sleeve: cash (idle = BIL, accruing cash_yield on the prior close's
    balance), positions {qty, fill, exit, exit_date, risk}; core (30/70
    only): spy_qty + core_cash, band-rebalanced at the close.

    Per day: (0) carry; (1) exits due today; (2) entries whose entry_date is
    today in select_capped order, sized at risk_frac of the SLEEVE equity at
    the close of the FIRE day (= the prior close for lag 1 — run_call_book's
    prev_equity; the nearest daily proxy to the T+1 ~10:30 marks for lag 2),
    qty = min(floor(risk$/risk), floor(spendable cash/entry_ref)), cost at the
    actual fill (cash may dip below zero by the fill-vs-entry_ref gap, as the
    executor's ledger does — never clipped at the fill); (3) MTM on adjusted
    closes; (4) 30/70 band rebalance + core buy.

    paper_arith (R2A_MODE): cash untouched at entry, MTM ((px-entry)/risk)*rd,
    rd*r_net realized at exit, prev-close sizing — run_call_book's exact
    arithmetic, asserted to 1e-6 in run_mirror.
    """
    calendar, px = mkt["calendar"], mkt["px"]
    by_entry: dict[str, list[dict]] = {}
    for t in rows:
        by_entry.setdefault(t["entry_date"], []).append(t)
    target = cfg.sleeve_target
    blend = target < 1.0 - 1e-9
    bil_fee = cfg.commission_usd if cfg.bil_order_cost else 0.0

    sleeve_cash = target * START_EQUITY
    core_cash = (1.0 - target) * START_EQUITY
    spy_qty = 0
    positions: list[dict] = []
    curve: list[tuple[date, float]] = []
    sleeve_curve: list[tuple[date, float]] = []
    sleeve_eq_by: dict[str, float] = {}
    prev_sleeve_eq = sleeve_cash
    prev_sleeve_cash = sleeve_cash
    trades: list[dict] = []
    daily: dict[str, dict] = {}
    first = True

    def _spy(d: date) -> float | None:
        if spy_px is None:
            return None
        v = spy_px.get(d)
        return v if (v is not None and v > 0) else None

    for d in calendar:
        ds = d.isoformat()
        ev = {"commissions": 0.0, "bil_orders": 0, "rebalances": 0, "core_orders": 0,
              "skipped_zero_qty": 0, "entries": 0, "exits": 0, "carry": 0.0}

        # 0. carry: yesterday's idle sleeve cash earns today's BIL total return
        if cash_yield is not None and not first:
            acc = max(prev_sleeve_cash, 0.0) * cash_yield.get(d, 0.0)
            sleeve_cash += acc
            ev["carry"] = acc

        # 1. exits due today
        still: list[dict] = []
        for p in positions:
            if p["exit_date"] <= ds:
                sleeve_cash += _exit_proceeds(cfg, p, ev)
            else:
                still.append(p)
        positions = still

        # 2. entries (select_capped order)
        for t in by_entry.get(ds, []):
            if cfg.paper_arith:
                size_eq = prev_sleeve_eq
            else:
                size_eq = sleeve_eq_by.get(t["fire_date"], prev_sleeve_eq)
            risk_usd = cfg.risk_frac * size_eq
            risk = t["risk"]
            qty = risk_usd / risk
            if cfg.integer_shares:
                qty = math.floor(qty)
            if cfg.cash_clip:
                avail = max(sleeve_cash, 0.0)
                qty = min(qty, math.floor(avail / t["entry_ref"]))
            if qty <= 0:
                ev["skipped_zero_qty"] += 1
                continue
            p = {"row": t, "qty": qty, "fill": t["entry"], "risk": risk,
                 "rd": qty * risk, "exit": t["exit"], "exit_date": t["exit_date"],
                 "symbol": t["symbol"], "bps": t.get("bps", 0.0)}
            if not cfg.paper_arith:
                notional = qty * t["entry"]
                c = commission(cfg, qty, notional)
                sleeve_cash -= notional * (1 + t["bps"]) + c + bil_fee
                ev["commissions"] += c + bil_fee
                ev["bil_orders"] += 1 if cfg.bil_order_cost else 0
            ev["entries"] += 1
            trades.append({"entry_date": ds, "exit_date": t["exit_date"], "status": t["status"],
                           "hold_days": t["hold_days"], "qty": qty, "r_net": t["r_net"],
                           "prefill_exit": t.get("prefill_exit", False), "symbol": t["symbol"]})
            if t["exit_date"] <= ds:                    # same-bar exit: realize now
                sleeve_cash += _exit_proceeds(cfg, p, ev)
            else:
                positions.append(p)

        # 3. mark to market
        mtm = 0.0
        for p in positions:
            c = px[p["symbol"]][d]
            if cfg.paper_arith:
                mtm += ((c - p["fill"]) / p["risk"]) * p["rd"]
            else:
                mtm += p["qty"] * c
        sleeve_eq = sleeve_cash + mtm
        spy = _spy(d)
        core_eq = core_cash + (spy_qty * spy if spy is not None else 0.0)
        equity = sleeve_eq + core_eq

        # 4. 30/70 band rebalance at the close + core buy of idle core cash
        if blend and spy is not None and equity > 0:
            w = sleeve_eq / equity
            if abs(w - target) > cfg.band:
                usd = abs(w - target) * equity
                if w < target:                           # core_to_sleeve: sell SPY
                    n_sh = min(int(round(usd / spy)), spy_qty)
                    if n_sh > 0:
                        c = commission(cfg, n_sh, n_sh * spy)
                        proceeds = n_sh * spy * (1 - SPY_BPS) - c
                        spy_qty -= n_sh
                        sleeve_cash += proceeds
                        ev["commissions"] += c
                        ev["rebalances"] += 1
                        ev["core_orders"] += 1
                else:                                    # sleeve_to_core: move cash
                    moved = min(usd, max(sleeve_cash, 0.0))
                    if moved > 0:
                        sleeve_cash -= moved + bil_fee
                        core_cash += moved
                        ev["commissions"] += bil_fee
                        ev["bil_orders"] += 1 if cfg.bil_order_cost else 0
                        ev["rebalances"] += 1
            if core_cash > max(MIN_ORDER_USD, spy):      # blend.py core_buy
                n_sh = int(core_cash // spy)
                if n_sh > 0:
                    c = commission(cfg, n_sh, n_sh * spy)
                    core_cash -= n_sh * spy * (1 + SPY_BPS) + c
                    spy_qty += n_sh
                    ev["commissions"] += c
                    ev["core_orders"] += 1
            sleeve_eq = sleeve_cash + mtm
            core_eq = core_cash + spy_qty * spy
            equity = sleeve_eq + core_eq

        curve.append((d, equity))
        sleeve_curve.append((d, sleeve_eq))
        sleeve_eq_by[ds] = sleeve_eq
        prev_sleeve_eq = sleeve_eq
        prev_sleeve_cash = sleeve_cash
        ev.update({"sleeve_cash": sleeve_cash, "sleeve_eq": sleeve_eq, "core_cash": core_cash,
                   "spy_qty": spy_qty, "equity": equity, "open_positions": len(positions)})
        daily[ds] = ev
        first = False

    meta = {
        "cfg": asdict(cfg), "n_rows": len(rows), "n_taken": len(trades),
        "skipped_zero_qty": sum(e["skipped_zero_qty"] for e in daily.values()),
        "commissions_paid": sum(e["commissions"] for e in daily.values()),
        "bil_orders": sum(e["bil_orders"] for e in daily.values()),
        "core_orders": sum(e["core_orders"] for e in daily.values()),
        "rebalances": sum(e["rebalances"] for e in daily.values()),
        "carry_usd": sum(e["carry"] for e in daily.values()),
        "end_spy_qty": spy_qty, "end_sleeve_cash": sleeve_cash, "end_core_cash": core_cash,
    }
    return {"curve": curve, "sleeve_curve": sleeve_curve, "meta": meta,
            "trades": trades, "daily": daily}


def _exit_proceeds(cfg: ExecCfg, p: dict, ev: dict) -> float:
    ev["exits"] += 1
    if cfg.paper_arith:
        return p["rd"] * p["row"]["r_net"]
    notional = p["qty"] * p["exit"]
    c = commission(cfg, p["qty"], notional)
    bil_fee = cfg.commission_usd if cfg.bil_order_cost else 0.0
    ev["commissions"] += c + bil_fee
    ev["bil_orders"] += 1 if cfg.bil_order_cost else 0
    return notional * (1 - p["bps"]) - c - bil_fee


def paper_blend_curve(sleeve_curve: list[tuple[date, float]],
                      spy_px: dict[date, float | None], w: float = 0.30) -> list[tuple[date, float]]:
    """R3's PAPER 30/70: daily-rebalanced return mix w*r_sleeve + (1-w)*r_SPY
    on the intersection calendar (sleeve_returns/compound reused), zero
    rebalance cost — the construction R3-A used, NOT the executor's band."""
    s_by = dict(sleeve_curve)
    inter = [d for d, _ in sleeve_curve if spy_px.get(d)]
    if len(inter) < 2:
        return []
    rs = sleeve_returns(s_by, inter)
    rp = sleeve_returns({d: spy_px[d] for d in inter}, inter)
    return compound(inter, [w * a + (1 - w) * b for a, b in zip(rs, rp)])


# --- windows & statistics ------------------------------------------------------------

def window_bounds(calendar: list[date], end: date | None = None) -> dict[str, tuple[date, date]]:
    """full = [first..end]; 'Ny' = [first calendar date >= end - N*365.25d .. end].
    Trailing windows are SLICES of the full-run curve (positions entered
    before the window carry in — the house SUB_PERIODS convention), not
    restarted books."""
    end = end or calendar[-1]
    out = {"full": (calendar[0], end)}
    for name, yrs in TRAILING_WINDOWS:
        cutoff = end - timedelta(days=yrs * 365.25)
        lo = next((d for d in calendar if d >= cutoff), calendar[0])
        out[name] = (lo, end)
    return out


def longest_underwater(seg: list[tuple[date, float]]) -> dict:
    """Longest peak-to-recovery stretch in the segment. An unrecovered
    stretch at the window end is measured to the end and flagged open."""
    if not seg:
        return {}
    best = None
    peak_v, peak_d, peak_i = seg[0][1], seg[0][0], 0
    uw_start: tuple[date, int] | None = None
    for i, (d, v) in enumerate(seg):
        if v >= peak_v:
            if uw_start is not None:
                cand = {"days_calendar": (d - uw_start[0]).days, "days_trading": i - uw_start[1],
                        "peak_date": uw_start[0].isoformat(), "recovery_date": d.isoformat(),
                        "open": False}
                if best is None or cand["days_calendar"] > best["days_calendar"]:
                    best = cand
                uw_start = None
            peak_v, peak_d, peak_i = v, d, i
        elif uw_start is None:
            uw_start = (peak_d, peak_i)
    if uw_start is not None:
        d, i = seg[-1][0], len(seg) - 1
        cand = {"days_calendar": (d - uw_start[0]).days, "days_trading": i - uw_start[1],
                "peak_date": uw_start[0].isoformat(), "recovery_date": None, "open": True}
        if best is None or cand["days_calendar"] > best["days_calendar"]:
            best = cand
    return best or {"days_calendar": 0, "days_trading": 0, "peak_date": None,
                    "recovery_date": None, "open": False}


def calendar_year_returns(seg: list[tuple[date, float]]) -> list[dict]:
    """Per calendar year inside the segment: last close of the year / last
    close of the prior year (the window start for the first year). Years
    not fully covered by the window are flagged partial."""
    if not seg:
        return []
    last_by_year: dict[int, tuple[date, float]] = {}
    for d, v in seg:
        last_by_year[d.year] = (d, v)
    out = []
    anchor = seg[0][1]
    first_year, last_year = seg[0][0].year, seg[-1][0].year
    for y in sorted(last_by_year):
        d, v = last_by_year[y]
        partial = ((y == first_year and seg[0][0] > date(y, 1, 10))
                   or (y == last_year and d < date(y, 12, 20)))
        out.append({"year": y, "return": v / anchor - 1 if anchor > 0 else float("nan"),
                    "partial": partial, "end": d.isoformat()})
        anchor = v
    return out


def extra_stats(curve: list[tuple[date, float]], lo: date, hi: date) -> dict:
    seg = [(d, v) for d, v in curve if lo <= d <= hi]
    years = calendar_year_returns(seg)
    worst = min(years, key=lambda y: y["return"]) if years else None
    return {"longest_underwater": longest_underwater(seg),
            "worst_year": worst, "years": years}


def trade_stats(book: dict, lo: date, hi: date) -> dict:
    los, his = lo.isoformat(), hi.isoformat()
    tr = [t for t in book["trades"] if los <= t["entry_date"] <= his]
    ev = [e for ds, e in book["daily"].items() if los <= ds <= his]
    n = len(tr)
    return {
        "n_trades": n,
        "stop_rate": (sum(1 for t in tr if t["status"] == "stopped") / n) if n else None,
        "avg_hold_days": statistics.fmean([t["hold_days"] for t in tr]) if n else None,
        "avg_r_net": statistics.fmean([t["r_net"] for t in tr]) if n else None,
        "prefill_exits": sum(1 for t in tr if t.get("prefill_exit")),
        "skipped_zero_qty": sum(e["skipped_zero_qty"] for e in ev),
        "commissions_paid": sum(e["commissions"] for e in ev),
        "bil_orders": sum(e["bil_orders"] for e in ev),
        "rebalances": sum(e["rebalances"] for e in ev),
        "carry_usd": sum(e["carry"] for e in ev),
    }


def curve_points(curve: list[tuple[date, float]], lo: date, hi: date) -> list[list]:
    """[[date, equity, dd]] for the window slice: dd = current drawdown from
    the running peak since the window start, computed on the DAILY curve,
    then downsampled (reused) to ~400 points with the last point kept."""
    seg = [(d, v) for d, v in curve if lo <= d <= hi]
    dd_by: dict[str, float] = {}
    peak = -math.inf
    for d, v in seg:
        peak = max(peak, v)
        dd_by[d.isoformat()] = (1 - v / peak) if peak > 0 else 0.0
    return [[ds, v, round(dd_by[ds], 5)] for ds, v in downsample(seg)]


def stationary_bootstrap(rets: list[float], horizon_years: float, draws: int = BOOT_DRAWS,
                         mean_block: int = BOOT_MEAN_BLOCK, seed: int = BOOT_SEED) -> dict:
    """Stationary block bootstrap of daily returns (function copy of the
    R3-G loop in backtest_variants_r3.main, which is inline there):
    p_new = 1/mean_block, wrap-around, horizon = len(rets) steps, empirical
    percentiles. Deterministic per seed."""
    rng = random.Random(seed)
    N = len(rets)
    if N == 0:
        return {}
    p_new = 1.0 / mean_block
    cagrs, dds = [], []
    for _ in range(draws):
        i = rng.randrange(N)
        v, peak, dd = 1.0, 1.0, 0.0
        for _step in range(N):
            v *= 1 + rets[i]
            if v > peak:
                peak = v
            else:
                d_ = 1 - v / peak
                if d_ > dd:
                    dd = d_
            i = rng.randrange(N) if rng.random() < p_new else (i + 1) % N
        cagrs.append(v ** (1 / horizon_years) - 1 if v > 0 else -1.0)
        dds.append(dd)
    cagrs.sort()
    dds.sort()

    def pct(vals: list[float], p: float) -> float:
        return vals[min(len(vals) - 1, max(0, round(p / 100 * (len(vals) - 1))))]

    cagr_tri = {"p5": pct(cagrs, 5), "p50": pct(cagrs, 50), "p95": pct(cagrs, 95)}
    dd_tri = {"p5": pct(dds, 5), "p50": pct(dds, 50), "p95": pct(dds, 95)}
    return {"draws": draws, "mean_block_days": mean_block, "seed": seed,
            "horizon_years": horizon_years, "n_days": N, "wrap_around": True,
            # R3-G naming (cagr_pct/max_dd_pct) + plain aliases for the UI normalizer
            "cagr_pct": cagr_tri, "max_dd_pct": dd_tri, "cagr": cagr_tri, "max_dd": dd_tri,
            "prob_cagr_negative": sum(1 for c in cagrs if c < 0) / len(cagrs)}


def diff_stats(a: dict, b: dict) -> dict:
    return {k: (a[k] - b[k]) if (a and b) else None
            for k in ("cagr", "max_dd", "sharpe", "end_value")}


# --- the study ---------------------------------------------------------------------

VARIANT_ORDER = ["r2a_ref", "r2a_ref_carry", "exec_t1_nocost_nocarry", "exec_t1_nocarry",
                 "exec_t2_nocarry", "exec_t2_carry", "exec_t1_carry",
                 "blend3070_t2_carry", "blend3070_t1_carry", "blend3070_paper_t2_carry"]

LADDER = {
    "exec_t1_nocost_nocarry": replace(EXEC_T1, commission_model="none", bil_order_cost=False, carry=False),
    "exec_t1_nocarry": replace(EXEC_T1, carry=False),
    "exec_t2_nocarry": replace(EXEC_T2, carry=False),
    "exec_t2_carry": EXEC_T2,
    "exec_t1_carry": EXEC_T1,
    "blend3070_t2_carry": replace(EXEC_T2, sleeve_target=0.30),
    "blend3070_t1_carry": replace(EXEC_T1, sleeve_target=0.30),
}

HONESTY = [
    "SURVIVORSHIP: the 32-name universe is today's watchlist; dead/delisted names are absent — absolute numbers flattered.",
    "HINDSIGHT TIERS: liquidity tiers (and so slippage) are full-sample median ADDV, known only ex post.",
    "IN-SAMPLE: the fire thresholds and the 3xATR/90d exit parameters were chosen on this same history; exit-parameter sensitivity per R3-F (2.5-3.5x, 60-120d) is the honest range, not the center.",
    "REPLAYABLE SHADOW, NOT THE LIVE BOOK: sentiment/revision/options lanes are absent, no composite gate, no 14-day per-symbol cooldown — duplicate same-day fires remain distinct calls (242 pairs); the live engine runs rolling tiers + discovery, not this fixed universe.",
    "SELECTION: 21 prior judged variants preceded R2-A; this mirror inherits those selection effects.",
    "COSTS ASSUMED, NOT MEASURED: IBKR Fixed ($0.005/sh, $1 min, 1% cap), $1 per BIL order, tiered slippage 10/40/100 bps per side, SPY 10 bps; BIL bid/ask, partial fills and MOO auction slippage beyond the tiered bps are not modeled.",
    "NOT MODELED: mid-session stop-ratchet lag (the level through bar k-1 is applied from the open of bar k, as grade_trailing does; the executor's ratchet lands ~10:30), STOP_MISSING/budget/pending-order operational skips (can only reduce fills), the unswept pre-fund day and BIL dust, the 30/70 band checked at the close rather than intraday.",
    "SIZING PROXY: lag-2 entries are sized on the sleeve equity at the fire-day close (the executor sizes at T+1 ~10:30 on live marks).",
    "TRAILING WINDOWS ARE SLICES of the 10-year curve (positions entered before the window carry in), not fresh $100k books started at the window open.",
    "MEASUREMENT BASIS: daily mark-to-market on adjusted closes; max DD on the daily curve; CAGR calendar-day (365.25); Sharpe/Sortino sqrt(252), rf = 0; bootstrap = stationary block (mean 21d) of the window's own daily returns.",
    "Never present these in-sample CAGRs as a forecast.",
]


def run_mirror(fire_rows: list[dict], mkt: dict, tiers: dict[str, str], *,
               r2a_stored_end: float | None = None, bil: dict[date, float] | None = None,
               proxy_days: list[date] | tuple = (), spy_px: dict[date, float | None] | None = None,
               spy_source: str = "none", spy_adjusted: bool | None = None,
               draws: int = BOOT_DRAWS, seed: int = BOOT_SEED,
               allow_cache_drift: bool = False, end: date | None = None,
               machinery_tol: float = MACHINERY_TOL_USD,
               machinery_tol_rel: float = MACHINERY_TOL_REL,
               cache_basis: dict | None = None,
               r2a_stored_meta: dict | None = None,
               r2a_stored_curve: list | None = None,
               bars_info: dict | None = None) -> dict:
    """The whole study on injected inputs (no file or network access):
    machinery checks -> rows per lag -> books -> window stats -> bootstrap ->
    results dict (the JSON). Raises SystemExit on a machinery failure unless
    allow_cache_drift (then publishes with protocol.cache_verified=false)."""
    calendar = mkt["calendar"]
    up200 = mkt["xbi_above_prior"][200]
    end = end or calendar[-1]

    # ---- MACHINERY CHECK 1: the reused R2-A recipe reproduces the stored end value
    trail_rows, a_open = build_trailing_rows(fire_rows, mkt, tiers)
    ta, sa = select_capped(gate_rows(trail_rows, up200, key="entry_date"), CAP)
    r2a_curve = run_call_book(ta, mkt)
    r2a_end = r2a_curve[-1][1]
    abs_diff = abs(r2a_end - r2a_stored_end) if r2a_stored_end is not None else None
    rel_diff = (abs_diff / abs(r2a_stored_end)) if abs_diff is not None and r2a_stored_end else None
    cache_exact = (abs_diff is not None and abs_diff <= machinery_tol)
    tol_usd = max(machinery_tol, machinery_tol_rel * abs(r2a_stored_end or 0.0))
    end_ok = (abs_diff is not None and abs_diff <= tol_usd)
    # The same gate verifies the TRADE SET and the CURVE, not one scalar
    # (counter-agent 2026-10-04, HIGH/MED): two curves can meet at the end
    # with different drawdowns, and bars that run past the campaign's data
    # end grade the 44 open-at-end calls the campaign never entered.
    rows_got = {"n_regraded": len(trail_rows), "open_at_end_excluded": a_open,
                "n_taken": len(ta), "skipped_at_cap": sa}
    rows_stored = ({k: r2a_stored_meta.get(k) for k in rows_got} if r2a_stored_meta else None)
    rows_match = (None if rows_stored is None else
                  all(rows_stored[k] == rows_got[k] for k in rows_got))
    # n_regraded / open_at_end_excluded are BAR-COVERAGE facts (a miss means a
    # missing entry-date bar or a wrong clip) and gate the verdict; n_taken /
    # skipped_at_cap may legitimately shift by a row when a lane's high/low
    # lands a stop a day earlier near the cap boundary - reported only.
    coverage_ok = (rows_stored is None or all(
        rows_stored[k] == rows_got[k] for k in ("n_regraded", "open_at_end_excluded")))
    curve_check = _curve_reproduction(r2a_curve, r2a_stored_curve)
    curve_ok = (curve_check is None or (
        curve_check["max_rel_diff"] <= CURVE_TOL_REL
        and curve_check["max_dd_abs_diff"] <= MAXDD_TOL
        and curve_check["sharpe_abs_diff"] <= SHARPE_TOL
        and curve_check["n_compared"] == curve_check["n_stored"] == curve_check["n_got"]))
    cache_verified = end_ok and curve_ok and coverage_ok
    if r2a_stored_end is not None and not cache_verified and not allow_cache_drift:
        why = (f"end ${r2a_end:,.2f} vs stored ${r2a_stored_end:,.2f} (|diff| ${abs_diff:,.2f} = "
               f"{rel_diff:.2%}, tolerance ${tol_usd:,.2f})")
        if curve_check is not None:
            why += (f"; curve max point-wise gap {curve_check['max_rel_diff']:.3%} (tol "
                    f"{CURVE_TOL_REL:.0%}), max DD {curve_check['max_dd_got']:.4f} vs "
                    f"{curve_check['max_dd_stored']:.4f} (tol {MAXDD_TOL}), Sharpe "
                    f"{curve_check['sharpe_got']:.4f} vs {curve_check['sharpe_stored']:.4f} "
                    f"(tol {SHARPE_TOL})")
        if curve_check is not None and not (
                curve_check["n_compared"] == curve_check["n_stored"] == curve_check["n_got"]):
            why += (f"; calendar mismatch: {curve_check['n_compared']} common dates vs "
                    f"{curve_check['n_stored']} stored / {curve_check['n_got']} replayed")
        if rows_match is False:
            why += f"; trade set {rows_got} vs stored {rows_stored}"
        raise SystemExit(
            f"MACHINERY CHECK FAILED: R2-A does not reproduce within the V0 machinery "
            f"tolerances: {why}. The bars are not on the campaign basis — nothing written. "
            f"Rebuild them with `python -m scripts.refresh_backtest_bars` (or --refresh-bars), "
            f"or re-run with --allow-cache-drift to publish with cache_verified=false.")

    # ---- MACHINERY CHECK 2: the new engine in r2a_mode reduces to the reused recipe
    r2a_rows, _ = build_exec_rows(fire_rows, mkt, tiers, R2A_MODE)
    row_mismatch = _row_mismatches(trail_rows, r2a_rows)
    if row_mismatch != 0:
        raise SystemExit(f"grade_executor(R2A_MODE) != build_trailing_rows ({row_mismatch} rows): "
                         f"{_row_mismatch_examples(trail_rows, r2a_rows)}")
    red = run_executor_book(ta, mkt, R2A_MODE)["curve"]
    red_diff = max(abs(a[1] - b[1]) for a, b in zip(red, r2a_curve)) if ta else 0.0
    if not (len(red) == len(r2a_curve) and red_diff <= REDUCTION_TOL):
        raise SystemExit(f"run_executor_book(R2A_MODE) != run_call_book (max |diff| {red_diff})")

    # ---- rows per lag (graded once, shared by every book of that lag)
    rows_by_lag: dict[int, tuple[list[dict], dict, int]] = {}
    for lag in (1, 2):
        cfg = replace(EXEC_T2, entry_lag=lag)
        rows, rmeta = build_exec_rows(fire_rows, mkt, tiers, cfg)
        taken, skipped = select_capped(gate_rows(rows, up200), CAP)
        rows_by_lag[lag] = (taken, {**rmeta, "n_graded": len(rows), "n_gated": len(gate_rows(rows, up200)),
                                    "n_taken": len(taken), "skipped_at_cap": skipped}, skipped)

    # ---- books
    books: dict[str, dict] = {}
    curves: dict[str, list[tuple[date, float]]] = {"r2a_ref": r2a_curve}
    meta: dict[str, dict] = {"r2a_ref": {"desc": "paper R2-A (run_call_book reused)", "n_taken": len(ta),
                                         "skipped_at_cap": sa, "open_at_end_excluded": a_open}}
    curves["r2a_ref_carry"] = run_call_book_yield(ta, mkt, bil)
    meta["r2a_ref_carry"] = {"desc": "paper R2-A with idle cash earning BIL (run_call_book_yield reused)",
                             "n_taken": len(ta), "carry": bil is not None}
    for name, cfg in LADDER.items():
        if cfg.sleeve_target < 1.0 and spy_px is None:
            continue
        taken, rmeta, _ = rows_by_lag[cfg.entry_lag]
        bk = run_executor_book(taken, mkt, cfg, cash_yield=(bil if cfg.carry else None), spy_px=spy_px)
        books[name] = bk
        curves[name] = bk["curve"]
        meta[name] = {"desc": cfg.label, **{k: v for k, v in rmeta.items()},
                      **{k: v for k, v in bk["meta"].items() if k != "cfg"}, "cfg": bk["meta"]["cfg"]}
    if spy_px is not None and "exec_t2_carry" in books:
        pc = paper_blend_curve(books["exec_t2_carry"]["sleeve_curve"], spy_px)
        if pc:
            curves["blend3070_paper_t2_carry"] = pc
            meta["blend3070_paper_t2_carry"] = {
                "desc": "PAPER 30/70: daily-rebalanced 0.3*r(exec_t2_carry) + 0.7*r(SPY), "
                        "R3 construction (sleeve_returns/compound reused), zero rebalance cost"}

    # ---- windows, stats, curves, bootstrap
    windows = window_bounds(calendar, end)
    variants: dict[str, dict] = {}
    for name in VARIANT_ORDER:
        if name not in curves:
            continue
        cv = curves[name]
        wstats, wcurves = {}, {}
        for w, (lo, hi) in windows.items():
            s = seg_stats(cv, lo, hi)
            if not s:
                continue
            s.update(extra_stats(cv, lo, hi))
            if name in books:
                s["trades"] = trade_stats(books[name], lo, hi)
                s["n_trades"] = s["trades"]["n_trades"]      # flat alias for the UI tiles
            wstats[w] = s
            wcurves[w] = curve_points(cv, lo, hi)
        v = {"meta": meta[name], "windows": wstats, "curves": wcurves}
        if name in BOOTSTRAP_VARIANTS:
            v["bootstrap"] = {}
            for w, (lo, hi) in windows.items():
                seg = [x for d, x in cv if lo <= d <= hi]
                if len(seg) < 3:
                    continue
                rets = [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg))]
                horizon = max((hi - lo).days, 1) / 365.25
                v["bootstrap"][w] = stationary_bootstrap(rets, horizon, draws, BOOT_MEAN_BLOCK,
                                                         seed + WINDOW_SEED_OFFSET[w])
        variants[name] = v

    def _d(a: str, b: str) -> dict:
        if a not in variants or b not in variants:
            return {}
        return {w: diff_stats(variants[a]["windows"].get(w, {}), variants[b]["windows"].get(w, {}))
                for w in windows}

    deltas = {"t1_vs_t2": _d("exec_t1_carry", "exec_t2_carry"),
              "carry_on_vs_off": _d("exec_t2_carry", "exec_t2_nocarry"),
              "costs": _d("exec_t1_nocarry", "exec_t1_nocost_nocarry"),
              "exec_vs_r2a": _d("exec_t2_carry", "r2a_ref"),
              "mechanics_vs_r2a": _d("exec_t1_nocost_nocarry", "r2a_ref"),
              "blend_t1_vs_t2": _d("blend3070_t1_carry", "blend3070_t2_carry"),
              "blend_band_vs_paper": _d("blend3070_t2_carry", "blend3070_paper_t2_carry")}

    bil_ann = None
    if bil is not None and len(calendar) > 1 and (calendar[-1] - calendar[0]).days > 0:
        bil_ann = (math.prod(1 + bil.get(d, 0.0) for d in calendar)) ** (
            365.25 / (calendar[-1] - calendar[0]).days) - 1

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "script": SCRIPT,
        "period": [calendar[0].isoformat(), end.isoformat()],
        "windows": {w: [lo.isoformat(), hi.isoformat()] for w, (lo, hi) in windows.items()},
        "protocol": {
            "start_equity": START_EQUITY, "risk_frac": RISK_FRAC, "cap": CAP,
            "slippage_bps": SLIPPAGE_BPS_BY_TIER, "spy_bps_per_side": SPY_BPS * 10_000,
            "commission_model": "ibkr_fixed: min(max($1, $0.005/sh), 1% of value) per fill",
            "bil_order_cost": "$1 BIL sell at each entry (pre-fund), $1 re-sweep at each exit, $1 per sleeve->core move",
            "carry": "BIL total return on prior-close sleeve cash (exact cash balance, clamped >= 0)",
            "bil_annualized": bil_ann, "proxy_days": len(proxy_days),
            "proxy_dates": [d.isoformat() for d in proxy_days],
            "time_stop": "fire_date + 90 calendar days, exit at the next bar's open (tiered slippage)",
            "trail": "fire-close peak, 3xATR14 through the prior bar, ratchet-up-only, day-zero protective stop at the published level",
            "sizing": "qty = min(floor(1% of sleeve equity at the fire-day close / (close_fire - L0)), floor(spendable sleeve cash / close_fire)); whole shares; never leveraged",
            "entry": "open of the bar `lag` sessions after the fire bar (lag 2 = BIL pre-fund then MOO; lag 1 = settled cash)",
            "gate": "XBI > 200dma on the PRIOR close, keyed at fire_date+1 for both lags",
            "blend_3070": "5pp band on sleeve weight checked at each close; SPY sold/bought in whole shares at 10 bps/side + commission; core_buy floor(core_cash/px) when core_cash > max($50, px)",
            "windows_note": "trailing 5y/2y are slices of the full-run curve (positions carry in)",
            "spy_source": spy_source,
            "spy_adjusted": spy_adjusted,
            "cache_verified": cache_verified,
            "cache_exact": cache_exact,
            "cache_basis": cache_basis or {"lane": "unknown (no backtest_bars_basis.json sidecar)"},
            "r2a_reproduction": {"stored": r2a_stored_end, "got": r2a_end, "abs_diff": abs_diff,
                                 "rel_diff": rel_diff, "tolerance_usd": machinery_tol,
                                 "tolerance_rel": machinery_tol_rel,
                                 "tolerance_applied_usd": tol_usd,
                                 "curve": curve_check,
                                 "curve_tolerances": {"max_rel_diff": CURVE_TOL_REL,
                                                      "max_dd": MAXDD_TOL, "sharpe": SHARPE_TOL},
                                 "rows": {"got": rows_got, "stored": rows_stored,
                                          "match": rows_match}},
            "bars": bars_info or {},
            "bootstrap": {"draws": draws, "mean_block_days": BOOT_MEAN_BLOCK, "seed": seed,
                          "seed_offsets": WINDOW_SEED_OFFSET, "variants": list(BOOTSTRAP_VARIANTS)},
            "curves_note": "~400 pts per window for display only; stats computed on the daily curve; dd = drawdown from the running peak since the window start",
        },
        "machinery": {"r2a_end_value": r2a_end, "r2a_stored": r2a_stored_end, "abs_diff": abs_diff,
                      "rel_diff": rel_diff, "cache_verified": cache_verified, "cache_exact": cache_exact,
                      "end_within_tolerance": end_ok, "curve_within_tolerance": curve_ok,
                      "bar_coverage_matches_stored": coverage_ok,
                      "curve": curve_check, "rows": {"got": rows_got, "stored": rows_stored,
                                                     "match": rows_match},
                      "bars": bars_info or {},
                      "row_reduction_mismatches": row_mismatch,
                      "reduction_check_max_abs_diff": red_diff},
        "rows": {str(lag): {k: v for k, v in rows_by_lag[lag][1].items()} for lag in (1, 2)},
        "variants": variants,
        "deltas": deltas,
        "honesty": list(HONESTY) + ([
            "SPY IS PRICE-RETURN ONLY: the cached SPY bars carry adj_close == close (an "
            "unadjusting provider), so the 30/70 rows omit SPY dividends (~1.3-1.5 pp/yr "
            "understated for the core leg); re-run with spy_bars_raw.json present."]
            if spy_adjusted is False else []) + ([
            f"BARS ARE NOT THE AUGUST CAMPAIGN CACHE ({(cache_basis or {}).get('lane', 'unknown')} "
            f"lane{', clipped to ' + bars_info['clipped_to'] if (bars_info or {}).get('clipped_to') else ''}): "
            f"R2-A reproduces to ${r2a_end:,.2f} vs the stored ${r2a_stored_end:,.2f} "
            f"({rel_diff:.3%} off, inside the +/-1% V0 machinery tolerance, not to the dollar)"
            + (f"; full daily curve max point-wise gap {curve_check['max_rel_diff']:.3%}, max DD "
               f"{curve_check['max_dd_got']:.2%} vs {curve_check['max_dd_stored']:.2%}, Sharpe "
               f"{curve_check['sharpe_got']:.3f} vs {curve_check['sharpe_stored']:.3f}"
               if curve_check else "; NO stored daily curve was available for a curve-level check")
            + (f"; trade set identical ({rows_got['n_taken']} taken, {rows_got['open_at_end_excluded']} open at data end)"
               if rows_match else (f"; TRADE SET DIFFERS: {rows_got} vs stored {rows_stored}"
                                   if rows_match is False else ""))
            + ". Absolute levels are comparable to the R2/R3 docs only as far as that curve-level "
            "check goes; the executor deltas are measured within this run."]
            if (cache_verified and not cache_exact and r2a_stored_end is not None) else []) + ([
            f"TRADE SET DIFFERS FROM THE STORED R2-A: {rows_got} vs stored {rows_stored} (bar "
            f"coverage {'matches' if coverage_ok else 'DOES NOT match'}; the end value and curve "
            f"are within tolerance)."]
            if (cache_verified and cache_exact and rows_match is False) else []),
    }


def _curve_reproduction(got: list, stored: list | None) -> dict | None:
    """Point-wise comparison of the replayed R2-A dollar curve with the frozen
    one (data/r2a_daily.json), plus max DD / Sharpe on each over the common
    span. None when no stored curve was supplied."""
    if not stored or not got:
        return None
    st = {}
    for d, v in stored:
        st[d if isinstance(d, date) else date.fromisoformat(str(d)[:10])] = float(v)
    pairs = [(d, v, st[d]) for d, v in got if d in st and st[d]]
    if len(pairs) < 2:
        return None
    max_rel = max(abs(v - w) / abs(w) for _, v, w in pairs)
    lo, hi = pairs[0][0], pairs[-1][0]
    sg = seg_stats([(d, v) for d, v, _ in pairs], lo, hi)
    ss = seg_stats([(d, w) for d, _, w in pairs], lo, hi)
    dd_g, dd_s = sg.get("max_dd", float("nan")), ss.get("max_dd", float("nan"))
    sh_g, sh_s = sg.get("sharpe", float("nan")), ss.get("sharpe", float("nan"))
    return {"n_compared": len(pairs), "n_stored": len(st), "n_got": len(got),
            "span": [lo.isoformat(), hi.isoformat()],
            "max_rel_diff": max_rel, "max_dd_got": dd_g, "max_dd_stored": dd_s,
            "max_dd_abs_diff": abs(dd_g - dd_s), "sharpe_got": sh_g, "sharpe_stored": sh_s,
            "sharpe_abs_diff": abs(sh_g - sh_s)}


def divergence_report(got: list, stored: list, taken: list[dict], mkt: dict,
                      tol: float = 1e-4, lookback_days: int = 15, bar_pad: int = 4) -> dict:
    """Where and why the replayed R2-A curve leaves the frozen one. The
    stored rows carry the ENTRY and the risk unit, so a divergence can only
    come from an EXIT (a trailing-stop bar the lane prints differently) or a
    gate day; this names the first divergent date, the taken calls whose
    entry or exit falls in the lookback window before it, and the lane's
    bars around each of those exits, so the suspect bar can be compared with
    another source by hand."""
    st = {}
    for d, v in stored:
        st[d if isinstance(d, date) else date.fromisoformat(str(d)[:10])] = float(v)
    first = None
    for d, v in got:
        w = st.get(d)
        if w and abs(v - w) / abs(w) > tol:
            first = (d, v, w)
            break
    if first is None:
        return {"first_divergence": None}
    d0, v0, w0 = first
    lo = d0 - timedelta(days=lookback_days)
    hi = d0 + timedelta(days=2)
    suspects = []
    for t in taken:
        ed = date.fromisoformat(t["entry_date"])
        xd = date.fromisoformat(t["exit_date"])
        if lo <= xd <= hi or lo <= ed <= hi:
            bars = mkt["bars"].get(t["symbol"], [])
            idx = {b.date: i for i, b in enumerate(bars)}
            j = idx.get(xd)
            around = []
            if j is not None:
                for b in bars[max(0, j - bar_pad): j + bar_pad + 1]:
                    around.append({"date": b.date.isoformat(), "open": b.open, "high": b.high,
                                   "low": b.low, "close": b.close})
            suspects.append({"symbol": t["symbol"], "flag": t["flag"], "entry_date": t["entry_date"],
                             "entry": t["entry"], "risk": t["risk"], "exit_date": t["exit_date"],
                             "exit": t["exit"], "status": t["status"], "bars_around_exit": around})
    suspects.sort(key=lambda t: t["exit_date"])
    return {"first_divergence": {"date": d0.isoformat(), "got": v0, "stored": w0,
                                 "rel_diff": (v0 - w0) / w0},
            "window": [lo.isoformat(), hi.isoformat()], "suspects": suspects}


def clip_bars_to(mkt: dict, end: date) -> dict:
    """Drop every bar after `end` from mkt['bars'] (in place) and report what
    was there. The graders walk the whole bar list, so bars past the
    campaign's data end would ENTER calls the campaign counted as open at
    data end (44 of them) and change the trade set (counter-agent
    2026-10-04, HIGH). The calendar/px are already clipped by load_market."""
    last = max((b.date for bars in mkt["bars"].values() for b in bars[-1:]), default=None)
    n_dropped = 0
    for sym, bars in mkt["bars"].items():
        keep = [b for b in bars if b.date <= end]
        n_dropped += len(bars) - len(keep)
        mkt["bars"][sym] = keep
    gate = mkt.get("xbi_above_prior", {}).get(200, {})
    return {"last_bar_before_clip": last.isoformat() if last else None,
            "clipped_to": end.isoformat(), "bars_dropped": n_dropped,
            "gate_defined_from": min(gate).isoformat() if gate else None}


def _row_mismatches(a: list[dict], b: list[dict], tol: float = 1e-9) -> int:
    key = lambda t: (t["fire_date"], t["symbol"], t["flag"].rsplit("_", 1)[0])  # noqa: E731
    ba = {key(t): t for t in a}
    bb = {key(t): t for t in b}
    bad = len(set(ba) ^ set(bb))
    for k in set(ba) & set(bb):
        x, y = ba[k], bb[k]
        if (x["entry_date"] != y["entry_date"] or x["exit_date"] != y["exit_date"]
                or x["status"] != y["status"] or abs(x["entry"] - y["entry"]) > tol
                or abs(x["exit"] - y["exit"]) > tol or abs(x["r_net"] - y["r_net"]) > tol):
            bad += 1
    return bad


def _row_mismatch_examples(a: list[dict], b: list[dict], n: int = 5, tol: float = 1e-9) -> list:
    """The first n (fire_date, symbol, flag) keys on which the two graders differ,
    for the SystemExit message (a bare count hides which name's bars are at fault)."""
    key = lambda t: (t["fire_date"], t["symbol"], t["flag"].rsplit("_", 1)[0])  # noqa: E731
    ba = {key(t): t for t in a}
    bb = {key(t): t for t in b}
    out = sorted(set(ba) ^ set(bb))
    for k in sorted(set(ba) & set(bb)):
        x, y = ba[k], bb[k]
        if (x["entry_date"] != y["entry_date"] or x["exit_date"] != y["exit_date"]
                or x["status"] != y["status"] or abs(x["entry"] - y["entry"]) > tol
                or abs(x["exit"] - y["exit"]) > tol or abs(x["r_net"] - y["r_net"]) > tol):
            out.append(k)
    return [list(k) for k in out[:n]]


# --- I/O ----------------------------------------------------------------------------

def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd) if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def write_results(res: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(_round(res), default=str))
    tmp.replace(out)


def load_spy_px(calendar: list[date], mkt: dict) -> tuple[dict[date, float | None] | None, str]:
    """SPY adjusted prices on the calendar: spy_bars_raw.json 'a' (the
    load_spy_curve convention) if present, else the bars cache 'SPY'."""
    if SPY_RAW.exists():
        rows = json.loads(SPY_RAW.read_text())["data"]
        by = {date.fromisoformat(r["t"]): r["a"] for r in rows if r.get("a") not in (None, 0)}
        out, last = {}, None
        for d in calendar:
            if d in by:
                last = by[d]
            out[d] = last
        return out, "spy_bars_raw.json (adjusted 'a'; lane per protocol.cache_basis)"
    if "SPY" in mkt["px"]:
        return mkt["px"]["SPY"], "backtest_bars.json SPY adj_close"
    return None, "none (30/70 variants skipped — run with --fetch-missing)"


def spy_is_adjusted(cache_path: Path) -> bool | None:
    """False when the cached SPY bars carry adj_close == close on every bar:
    a provider that does not adjust (FMP sets adj_close = close) gives a
    PRICE-return SPY, no dividends, ~1.3-1.5 pp/yr too low for the 30/70
    rows (counter-agent 2026-10-01). None when SPY is not in the cache."""
    try:
        raw = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        return None
    bars = raw.get("SPY")
    if not bars:
        return None
    pairs = [(b.get("adj_close"), b.get("close")) for b in bars
             if b.get("adj_close") is not None and b.get("close") is not None]
    if not pairs:
        return None
    return any(abs(float(a) - float(c)) > 1e-9 for a, c in pairs)


def fetch_missing_into_cache(symbols: list[str]) -> list[str]:
    """Fetch only symbols ABSENT from the bars cache; never overwrites an
    existing entry (the campaign cache must stay byte-identical)."""
    raw = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    missing = [s for s in symbols if s not in raw]
    if not missing:
        return []
    got = fetch_bars(missing, years=11)
    for s, bars in got.items():
        raw.setdefault(s, bars)
    # atomic: a crash mid-write must never destroy the campaign cache, which
    # cannot be regenerated (counter-agent 2026-10-01)
    tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
    tmp.write_text(json.dumps(raw))
    tmp.replace(CACHE)
    return sorted(got)


def refresh_bars() -> None:
    """Rebuild the bars cache on the FMP dividend-adjusted lane (ATAI basis-normalized),
    via scripts/refresh_backtest_bars.py — the only reproducible source now that the
    August campaign cache is gone. Needs FMP_API_KEY; writes backtest_bars.json,
    spy_bars_raw.json and the basis sidecar next to each other under data/."""
    import scripts.refresh_backtest_bars as _rb
    _rb.main()


def load_cache_basis() -> dict | None:
    """The refresh script's sidecar (lane + per-symbol basis factors), if present."""
    path = _input(BASIS_SIDECAR)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_inputs(fetch_missing: bool = False, refresh_bars_if_missing: bool = False,
                force_refresh: bool = False) -> dict:
    """Everything main() needs from disk (the only place files are read)."""
    import scripts.backtest_variants_10y as _v10
    import scripts.backtest_variants_r2 as _r2
    # 1) decide on a rebuild BEFORE any path is resolved (a seed_data copy
    #    must never shadow a freshly written data/ cache - counter-agent MED)
    incomplete = _cache_incomplete() if (force_refresh or refresh_bars_if_missing) else None
    if force_refresh or (refresh_bars_if_missing and incomplete):
        print(f"bars cache {'refresh requested' if force_refresh else incomplete}: rebuilding on the "
              f"FMP dividend-adjusted lane (scripts/refresh_backtest_bars.py)")
        refresh_bars()
    # 2) committed campaign inputs may live in the image's seed_data copy
    _v10.BARS_CACHE = _input(_v10.BARS_CACHE)
    _r2.BIL_RAW = _input(_r2.BIL_RAW)
    calls_results, r2_results, r3_results = _input(CALLS_RESULTS), _input(R2_RESULTS), _input(R3_RESULTS)
    if not CACHE.exists():
        raise SystemExit(
            f"bars cache missing: {CACHE} — it is gitignored. The August 2026 campaign cache no "
            f"longer exists; rebuild on the FMP dividend-adjusted lane with "
            f"`python -m scripts.refresh_backtest_bars` (needs FMP_API_KEY) or re-run this "
            f"script with --refresh-bars. Machinery check 1 then decides whether the rebuilt "
            f"bars reproduce the stored R2-A.")
    if fetch_missing:
        added = fetch_missing_into_cache(["SPY"])
        if added:
            print(f"fetched into cache (new symbols only): {added}")
    res = json.loads(calls_results.read_text())
    fire_rows = [t for f in LIVE_SET_FLAGS for t in res["call_rows"][f]]
    tiers = res["tiers"]
    mkt = load_market()
    # 3) the campaign's data ended at END (fetched 2026-08-20 before the
    #    close); a lane that runs past it would enter the open-at-end calls
    bars_info = clip_bars_to(mkt, _v10.END)
    calendar = mkt["calendar"]
    bil, proxy_days = load_bil_yield(calendar)
    spy_px, spy_source = load_spy_px(calendar, mkt)
    r2a_var = json.loads(r2_results.read_text())["variants"]["R2-A"]
    stored = r2a_var["stats"]["full"]["end_value"]
    if abs(stored - R2A_END) > 1.0:
        raise SystemExit(f"stored R2-A {stored} != R2A_END constant {R2A_END}")
    stored_meta = r2a_var.get("meta") or None
    r2a_daily = _input(R2A_DAILY)
    if not r2a_daily.exists():
        raise SystemExit(f"frozen R2-A daily curve missing: {R2A_DAILY} (committed input; without "
                         f"it machinery check 1 would degrade to an end-value-only check)")
    stored_curve = json.loads(r2a_daily.read_text())
    r3 = json.loads(r3_results.read_text()) if r3_results.exists() else None
    spy_adjusted = (True if spy_source.startswith("spy_bars_raw") else
                    (spy_is_adjusted(CACHE) if spy_px is not None else None))
    return {"fire_rows": fire_rows, "tiers": tiers, "mkt": mkt, "bil": bil,
            "proxy_days": proxy_days, "spy_px": spy_px, "spy_source": spy_source,
            "spy_adjusted": spy_adjusted, "r2a_stored_end": stored, "r3": r3,
            "cache_basis": load_cache_basis(), "r2a_stored_meta": stored_meta,
            "r2a_stored_curve": stored_curve, "bars_info": bars_info}


def _cache_incomplete() -> str | None:
    """Why the bars cache needs a rebuild, or None. A lane cache (sidecar
    present) without spy_bars_raw.json, or an unreadable JSON, counts as
    incomplete: both used to be silently used (counter-agent 2026-10-04)."""
    if not CACHE.exists():
        return "missing"
    try:
        json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return "unreadable"
    if BASIS_SIDECAR.exists() and not SPY_RAW.exists():
        return "incomplete (lane cache without spy_bars_raw.json)"
    return None


def print_table(res: dict) -> None:
    for w, (lo, hi) in res["windows"].items():
        print(f"\n== window {w}: {lo} -> {hi} ==")
        print(f"{'variant':28s} {'end value':>12s} {'CAGR':>8s} {'maxDD':>7s} {'Sharpe':>7s} "
              f"{'Sortino':>8s} {'Calmar':>7s} {'uw days':>8s} {'worst yr':>14s}")
        for name, v in res["variants"].items():
            s = v["windows"].get(w)
            if not s:
                continue
            uw = s["longest_underwater"].get("days_calendar", 0)
            wy = s["worst_year"] or {}
            print(f"{name:28s} ${s['end_value']:>11,.0f} {s['cagr']:>+8.2%} {s['max_dd']:>7.1%} "
                  f"{s['sharpe']:>7.2f} {s['sortino']:>8.2f} {s['calmar']:>7.2f} {uw:>8d} "
                  f"{wy.get('year', '-')!s:>6s} {wy.get('return', float('nan')):>+7.1%}")
    m = res["machinery"]
    print(f"\nmachinery: R2-A ${m['r2a_end_value']:,.2f} vs stored {m['r2a_stored']} "
          f"(|diff| {m['abs_diff']}, verified={m['cache_verified']}); reduction max|diff| "
          f"{m['reduction_check_max_abs_diff']:.2e}, row mismatches {m['row_reduction_mismatches']}")
    for k, dd in res["deltas"].items():
        full = dd.get("full") or {}
        if full.get("cagr") is not None:
            print(f"delta {k:22s} full: CAGR {full['cagr']:+.2%}  maxDD {full['max_dd']:+.2%}  "
                  f"Sharpe {full['sharpe']:+.2f}  end ${full['end_value']:+,.0f}")


# --- report ---------------------------------------------------------------------------

def _fmt_stats_row(name: str, s: dict) -> str:
    uw = s["longest_underwater"]
    wy = s["worst_year"] or {}
    tr = s.get("trades") or {}
    return (f"| {name} | ${s['end_value']:,.0f} | {s['cagr']:+.2%} | {s['max_dd']:.1%} | "
            f"{s['sharpe']:.2f} | {s['sortino']:.2f} | {s['calmar']:.2f} | "
            f"{uw.get('days_calendar', 0)}{' (open)' if uw.get('open') else ''} | "
            f"{wy.get('year', '-')} {wy.get('return', float('nan')):+.1%}{' (partial)' if wy.get('partial') else ''} | "
            f"{tr.get('n_trades', '-')} |")


def results_section(res: dict, r3: dict | None = None) -> str:
    lines: list[str] = []
    w = lines.append
    p, m = res["protocol"], res["machinery"]
    w(REPORT_BEGIN)
    w("")
    w(f"_Generated {res['generated']} by `{res['script']}` · period {res['period'][0]} → "
      f"{res['period'][1]} · results JSON `backend/data/backtest_executor_mirror_results.json`_")
    w("")
    if not p["cache_verified"]:
        w("> **RED: cache NOT verified.** The reused R2-A recipe reproduced "
          f"${m['r2a_end_value']:,.2f} vs stored ${m['r2a_stored']:,.2f} (|diff| ${m['abs_diff']:,.2f}). "
          "The bars cache is not the campaign cache; every number below is on different bars. "
          "Run on the campaign cache before acting on anything here.")
        w("")
    w(f"**Machinery**: R2-A reproduces to ${m['r2a_end_value']:,.2f} (stored ${m['r2a_stored']:,.2f}, "
      f"|diff| ${m['abs_diff']:,.4f}, verified={p['cache_verified']}); the new engine in r2a_mode "
      f"reduces to run_call_book with max |diff| {m['reduction_check_max_abs_diff']:.2e} and "
      f"{m['row_reduction_mismatches']} row mismatches. SPY source: {p['spy_source']}. "
      f"BIL annualized {p['bil_annualized']:+.2%} ({p['proxy_days']} proxy days)."
      if p["bil_annualized"] is not None else
      f"**Machinery**: R2-A reproduces to ${m['r2a_end_value']:,.2f}; reduction max |diff| "
      f"{m['reduction_check_max_abs_diff']:.2e}. SPY source: {p['spy_source']}.")
    w("")
    rows_meta = res.get("rows", {})
    for lag, rm in rows_meta.items():
        w(f"- lag {lag}: {rm['n_fires']} fires → {rm['n_graded']} graded ({rm['open_at_end_excluded']} "
          f"open at data end excluded, {rm['skip_no_sizing_reference']} no sizing reference, "
          f"{rm['skip_no_open']} no open, {rm['no_fire_bar']} no fire bar) → {rm['n_gated']} gate-on → "
          f"{rm['n_taken']} taken ({rm['skipped_at_cap']} skipped at the cap); "
          f"{rm['prefill_exit']} pre-fill tracker exits.")
    w("")
    for wn, (lo, hi) in res["windows"].items():
        w(f"### Window {wn}: {lo} → {hi}")
        w("")
        w("| variant | end value | CAGR | max DD | Sharpe | Sortino | Calmar | longest underwater (cal days) | worst year | trades |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for name, v in res["variants"].items():
            s = v["windows"].get(wn)
            if s:
                w(_fmt_stats_row(name, s))
        w("")
    w("### Attribution ladder (full window, each step adds one delta)")
    w("")
    w("| step | variant | adds | end value | CAGR | max DD | Sharpe |")
    w("|---|---|---|---|---|---|---|")
    ladder = [("L0", "r2a_ref", "paper R2-A (reused)"),
              ("L0b", "r2a_ref_carry", "+ BIL on idle cash (paper)"),
              ("L1", "exec_t1_nocost_nocarry", "executor mechanics (whole shares, cash clip, uncapped risk, day-zero stop, ratchet, fire-close peak, fire+90 next-open time stop), T+1"),
              ("L2", "exec_t1_nocarry", "+ IBKR fixed commissions + $1 BIL orders"),
              ("L3", "exec_t2_nocarry", "+ T+2 fill (pre-fund)"),
              ("L4", "exec_t2_carry", "+ BIL carry = PRIMARY 0/100"),
              ("L5", "exec_t1_carry", "T+1 at full realism"),
              ("B1", "blend3070_t2_carry", "30/70 band-rebalanced, T+2 = PRIMARY comparison"),
              ("B2", "blend3070_t1_carry", "30/70, T+1"),
              ("P1", "blend3070_paper_t2_carry", "30/70 PAPER daily mix (R3 construction)")]
    for step, name, adds in ladder:
        s = res["variants"].get(name, {}).get("windows", {}).get("full")
        if s:
            w(f"| {step} | {name} | {adds} | ${s['end_value']:,.0f} | {s['cagr']:+.2%} | "
              f"{s['max_dd']:.1%} | {s['sharpe']:.2f} |")
    w("")
    w("### Deltas (A − B, per window)")
    w("")
    w("| delta | window | CAGR | max DD | Sharpe | end value |")
    w("|---|---|---|---|---|---|")
    for k, dd in res["deltas"].items():
        for wn, d in dd.items():
            if d and d.get("cagr") is not None:
                w(f"| {k} | {wn} | {d['cagr']:+.2%} | {d['max_dd']:+.2%} | {d['sharpe']:+.2f} | "
                  f"${d['end_value']:+,.0f} |")
    w("")
    w("### Bootstrap cones (stationary block, mean 21d; window's own daily returns)")
    w("")
    w("| variant | window | draws | CAGR p5 / p50 / p95 | max DD p5 / p50 / p95 | P(CAGR<0) |")
    w("|---|---|---|---|---|---|")
    for name, v in res["variants"].items():
        for wn, b in (v.get("bootstrap") or {}).items():
            if b:
                w(f"| {name} | {wn} | {b['draws']} | {b['cagr_pct']['p5']:+.1%} / {b['cagr_pct']['p50']:+.1%} / "
                  f"{b['cagr_pct']['p95']:+.1%} | {b['max_dd_pct']['p5']:.1%} / {b['max_dd_pct']['p50']:.1%} / "
                  f"{b['max_dd_pct']['p95']:.1%} | {b['prob_cagr_negative']:.1%} |")
    w("")
    if r3:
        try:
            ra = r3["variants"]["R3-A"]["stats"]["full"]
            bs = r3["baseline"]["stats"]["full"]
            w("### 30/70 context (stored R3 numbers, different construction)")
            w("")
            w(f"- R3 paper 30/70 baseline: ${bs['end_value']:,.0f} / {bs['cagr']:+.2%} / {bs['max_dd']:.1%} / "
              f"Sharpe {bs['sharpe']:.2f}; R3-A (BIL on idle sleeve cash): ${ra['end_value']:,.0f} / "
              f"{ra['cagr']:+.2%} / {ra['max_dd']:.1%} / Sharpe {ra['sharpe']:.2f} — daily-rebalanced "
              f"paper mixes of the PAPER R2-A; B1 above is the executor's band-rebalanced book on the "
              f"executor-mechanics sleeve.")
            w("")
        except KeyError:
            pass
    w(REPORT_END)
    return "\n".join(lines)


def write_report(res: dict, path: Path = REPORT, r3: dict | None = None) -> None:
    """Replace the results section between the markers (append it when the
    doc has no markers yet; create a minimal doc when it is missing)."""
    section = results_section(res, r3)
    if path.exists():
        text = path.read_text()
        if REPORT_BEGIN in text and REPORT_END in text:
            a = text.index(REPORT_BEGIN)
            b = text.index(REPORT_END) + len(REPORT_END)
            text = text[:a] + section + text[b:]
        else:
            text = text.rstrip("\n") + "\n\n## Results\n\n" + section + "\n"
    else:
        text = "# Executor mirror backtest\n\n## Results\n\n" + section + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# --- main -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=RESULTS, help="results JSON path (data disk on Render)")
    ap.add_argument("--report", type=Path, default=REPORT, help="markdown doc whose results section is rewritten")
    ap.add_argument("--fetch-missing", action="store_true",
                    help="fetch symbols absent from the bars cache (SPY) via the market provider; never overwrites")
    ap.add_argument("--allow-cache-drift", action="store_true",
                    help="publish even when R2-A does not reproduce within the +/-1% V0 tolerance "
                         "(cache_verified=false, red banner)")
    ap.add_argument("--refresh-bars", action="store_true",
                    help="rebuild the bars cache on the FMP dividend-adjusted lane first "
                         "(scripts/refresh_backtest_bars.py, needs FMP_API_KEY); a missing cache "
                         "is rebuilt automatically")
    ap.add_argument("--draws", type=int, default=BOOT_DRAWS)
    ap.add_argument("--seed", type=int, default=BOOT_SEED)
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--diagnose", action="store_true",
                    help="no replay: print where the lane's R2-A curve first leaves the frozen one "
                         "and the taken calls / bars around it, then exit 0")
    args = ap.parse_args(argv)

    inp = load_inputs(fetch_missing=args.fetch_missing, refresh_bars_if_missing=True,
                      force_refresh=args.refresh_bars)
    if args.diagnose:
        mkt = inp["mkt"]
        trail_rows, a_open = build_trailing_rows(inp["fire_rows"], mkt, inp["tiers"])
        ta, sa = select_capped(gate_rows(trail_rows, mkt["xbi_above_prior"][200], key="entry_date"), CAP)
        curve = run_call_book(ta, mkt)
        rep = divergence_report(curve, inp.get("r2a_stored_curve") or [], ta, mkt)
        rep["counts"] = {"n_regraded": len(trail_rows), "open_at_end_excluded": a_open,
                         "n_taken": len(ta), "skipped_at_cap": sa}
        rep["bars"] = inp.get("bars_info")
        print(json.dumps(_round(rep, 6), indent=1))
        return 0
    res = run_mirror(inp["fire_rows"], inp["mkt"], inp["tiers"],
                     r2a_stored_end=inp["r2a_stored_end"], bil=inp["bil"],
                     proxy_days=inp["proxy_days"], spy_px=inp["spy_px"],
                     spy_source=inp["spy_source"], spy_adjusted=inp.get("spy_adjusted"),
                     draws=args.draws, seed=args.seed,
                     allow_cache_drift=args.allow_cache_drift,
                     cache_basis=inp.get("cache_basis"),
                     r2a_stored_meta=inp.get("r2a_stored_meta"),
                     r2a_stored_curve=inp.get("r2a_stored_curve"),
                     bars_info=inp.get("bars_info"))
    write_results(res, args.out)
    print_table(res)
    print(f"\nResults written to {args.out}")
    if not args.no_report:
        write_report(res, args.report, inp.get("r3"))
        print(f"Report section written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
