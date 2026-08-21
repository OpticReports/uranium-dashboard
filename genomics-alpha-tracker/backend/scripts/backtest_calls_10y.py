"""10-year replay of the calls engine across ALL replayable signals —
including, for the FIRST TIME, the catalyst-conditioned ones.

THE UNLOCK: scripts/build_pit_catalysts.py reconstructs a POINT-IN-TIME
catalyst calendar from ClinicalTrials.gov's historical record versions, so the
prior backtests' documented blocker ("no historical catalyst calendar",
BACKTEST_CALLS.md / BACKTEST_SIGNALS.md) is gone. For any past date d we use
what the registry SAID on d — primary completion date (PCD), status, phases —
never what we know today.

REPLAYED FLAGS (LIVE pre-registered thresholds from config/flags.yaml — never
re-fit here; guarded by assertions against silent drift):
  quiet_before_catalyst    FULL flag: |drift_z| <= max vs own vol AND a
                           >=0.85-impact catalyst due in [5,45]d as-known-then
  pullback_into_catalyst   FULL flag: price half (10-30% off 30d high, >=1.5
                           ATRs, above 50dma) AND >=0.7-impact catalyst in [10,45]d
  binary_event_within_n_days  >=0.85-impact catalyst within 21d
  pullback_price_half      price-only continuity row (same as BACKTEST_SIGNALS)
  volume_anomaly           price-only continuity row
  rel_strength_60d         price-only continuity row

TWO FRAMINGS per flag, mirroring the two existing backtests:
  FLAG framing   forward 5/21/63-bar XBI-excess per fire vs the unconditional
                 every-5th-bar baseline (backtest_signals.py conventions:
                 7-day re-fire suppression, symbol|month cluster bootstrap)
  CALLS framing  a call per suppressed fire graded with the PRODUCTION
                 build_levels/grade_call (open-first, gap-aware — NEVER
                 reimplemented), entry at the NEXT bar's open (conservative:
                 a live fire is actionable at the following open, not the
                 signal close), stop 3.0xATR14 / 3:1 RR / 45d from the live
                 calls.yaml, expiry capped at the day BEFORE the driving
                 catalyst's PCD for catalyst-conditioned flags (the live
                 sell-into-the-event rule), tiered slippage as in
                 backtest_calls.py

GATES NOT REPLAYED (LOUD DEVIATION): the live composite>=55 gate and
confidence sizing need hype/analyst/positioning components with no historical
record — every suppressed fire becomes a fixed-1R call here. The live auto-
trigger set (sentiment ramp / revision clusters / options+social) is likewise
not replayable at all; the combined book below is the replayable set, NOT the
live trigger set.

Usage:  python -m scripts.backtest_calls_10y            # cached bars + PIT store
        python -m scripts.backtest_calls_10y --refresh  # refetch bars
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike, atr, build_levels, grade_call  # noqa: E402
from app.config import calls_config, load_yaml_config, scoring_config, watchlist_config  # noqa: E402
from app.ingestion.catalysts import _PHASE_EVENT, _parse_loose_date  # noqa: E402
from app.scoring.components import drift_zscore_raw  # noqa: E402
from scripts.backtest_calls import (  # noqa: E402
    CACHE,
    SLIPPAGE_BPS_BY_TIER,
    fetch_bars,
    median_addv,
    tier_of,
    to_adjusted_barlikes,
    xbi_above_50dma,
)
from scripts.backtest_signals import (  # noqa: E402
    BASELINE_GRID,
    HORIZONS,
    MIN_DOLLAR_VOL,
    SUPPRESS_DAYS,
    atr_series,
    fires_pullback,
    fires_rel_strength,
    fires_volume,
    grade,
    sma_series,
    summarize as summarize_excess,
)

BENCH = "XBI"
START = date(2016, 1, 1)
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_CALLS_10Y.md"
PIT_STORE = Path(__file__).resolve().parent.parent / "data" / "pit_catalysts.json"
RESULTS = Path(__file__).resolve().parent.parent / "data" / "backtest_calls_10y_results.json"

ACTIVE_STATUSES = {"NOT_YET_RECRUITING", "RECRUITING", "ACTIVE_NOT_RECRUITING",
                   "ENROLLING_BY_INVITATION"}
CATALYST_FLAGS = ("quiet_before_catalyst", "pullback_into_catalyst",
                  "binary_event_within_n_days")
PRICE_FLAGS = ("pullback_price_half", "volume_anomaly", "rel_strength_60d")
ALL_FLAGS = CATALYST_FLAGS + PRICE_FLAGS
# The combined book takes the replayed flags that exist as LIVE flag types
# (flags.yaml). pullback_price_half is a continuity diagnostic, not a live
# flag — including it would double-count pullback_into_catalyst's superset.
LIVE_SET_FLAGS = ("quiet_before_catalyst", "pullback_into_catalyst",
                  "binary_event_within_n_days", "volume_anomaly",
                  "rel_strength_60d")
BOOT_ITERS = 2000


def _flags_full_config() -> dict:
    return load_yaml_config("flags.yaml")


def _guard_pre_registered(fcfg: dict) -> None:
    """The price-only fire functions imported from backtest_signals.py bake in
    the live thresholds. If flags.yaml ever drifts, FAIL LOUDLY instead of
    silently replaying stale thresholds."""
    pb = fcfg["flags"]["pullback_into_catalyst"]
    assert pb["min_pullback_pct"] == 0.10 and pb["max_pullback_pct"] == 0.30 \
        and pb["min_pullback_atr"] == 1.5 and pb["require_above_50dma"] is True, \
        "flags.yaml pullback thresholds drifted from backtest_signals.fires_pullback"
    va = fcfg["flags"]["volume_anomaly"]
    assert va["min_volume_z"] == 2.5 and va["min_dollar_volume"] == MIN_DOLLAR_VOL \
        and va["lookback_days"] == 60, \
        "flags.yaml volume_anomaly thresholds drifted from backtest_signals.fires_volume"
    rs = fcfg["flags"]["relative_strength_leader"]
    assert rs["min_rs_60d"] == 0.15, \
        "flags.yaml rel-strength threshold drifted from backtest_signals.fires_rel_strength"
    assert fcfg.get("refire_suppression_days", 7) == SUPPRESS_DAYS, \
        "flags.yaml refire_suppression_days drifted from backtest_signals.SUPPRESS_DAYS"


# --- point-in-time catalyst calendar ---------------------------------------------

def _impact_for_phases(phases: list[str], impact_weights: dict) -> tuple[str, float]:
    """EXACTLY app/ingestion/catalysts.py: first phase in _PHASE_EVENT wins,
    else data_presentation (so a PHASE1|PHASE2 trial maps to phase1_readout)."""
    event_type = "data_presentation"
    for ph in phases:
        if ph in _PHASE_EVENT:
            event_type = _PHASE_EVENT[ph][0]
            break
    return event_type, impact_weights.get(event_type, impact_weights.get("other", 0.2))


def parse_trial_timeline(trial: dict, impact_weights: dict) -> list[dict]:
    """Parse one trial's [from, to) intervals into replay-ready records."""
    out = []
    for iv in trial.get("timeline", []):
        phases = iv.get("phases") or trial.get("phases") or []
        event_type, impact = _impact_for_phases(phases, impact_weights)
        out.append({
            "from": date.fromisoformat(iv["from"]),
            "to": date.fromisoformat(iv["to"]) if iv.get("to") else None,
            "pcd": _parse_loose_date(iv.get("pcd")),   # YYYY-MM -> mid-month
            "active": (iv.get("status") in ACTIVE_STATUSES),
            "impact": impact,
            "event_type": event_type,
            "nct": trial.get("nct"),
        })
    return out


def pit_calendar_by_bar(trials: list[dict], bars: list[BarLike],
                        impact_weights: dict) -> list[list[dict]]:
    """For each bar index: the catalysts AS KNOWN THEN — for every trial, the
    timeline interval containing that date gives (pcd, status, phases); the
    trial contributes iff its as-of status is active, its as-of PCD parses and
    the PCD is not in the past."""
    parsed = [parse_trial_timeline(t, impact_weights) for t in trials]
    ptrs = [0] * len(parsed)
    out: list[list[dict]] = []
    for b in bars:
        d = b.date
        cats: list[dict] = []
        for k, ivs in enumerate(parsed):
            while ptrs[k] < len(ivs) and ivs[ptrs[k]]["to"] is not None \
                    and ivs[ptrs[k]]["to"] <= d:
                ptrs[k] += 1
            j = ptrs[k]
            if j >= len(ivs):
                continue
            iv = ivs[j]
            if d < iv["from"]:
                continue  # record did not publicly exist yet
            if iv["active"] and iv["pcd"] is not None and iv["pcd"] >= d:
                cats.append(iv)
        out.append(cats)
    return out


# --- catalyst-conditioned fire generators (each returns [(bar_idx, driving_pcd)]) ---

def _due(cats: list[dict], d: date, lo: int, hi: int, min_impact: float) -> list[dict]:
    return [c for c in cats
            if lo <= (c["pcd"] - d).days <= hi and c["impact"] >= min_impact]


def fires_quiet_before_catalyst(bars, cal, fcfg) -> list[tuple[int, date]]:
    f = fcfg["flags"]["quiet_before_catalyst"]
    lo, hi = f["catalyst_min_days"], f["catalyst_max_days"]
    window, max_z = f["window_days"], f["max_drift_z"]
    closes = [b.close for b in bars]
    out = []
    for i in range(30, len(bars)):
        due = _due(cal[i], bars[i].date, lo, hi, f["min_catalyst_impact"])
        if not due:
            continue
        drift_z, _vol = drift_zscore_raw(closes[max(0, i - 45): i + 1], window)
        if drift_z is None or abs(drift_z) > max_z:
            continue
        nearest = min(due, key=lambda c: c["pcd"])
        out.append((i, nearest["pcd"]))
    return out


def fires_pullback_into_catalyst(bars, cal, atrs, ma50, fcfg) -> list[tuple[int, date]]:
    f = fcfg["flags"]["pullback_into_catalyst"]
    lo, hi = f["catalyst_min_days"], f["catalyst_max_days"]
    price_ok = set(fires_pullback(bars, atrs, ma50))  # the flag's PRICE half
    out = []
    for i in sorted(price_ok):
        due = _due(cal[i], bars[i].date, lo, hi, f["min_catalyst_impact"])
        if due:
            nearest = min(due, key=lambda c: c["pcd"])
            out.append((i, nearest["pcd"]))
    return out


def fires_binary_event(bars, cal, fcfg) -> list[tuple[int, date]]:
    f = fcfg["flags"]["binary_event_within_n_days"]
    out = []
    for i in range(len(bars)):
        due = _due(cal[i], bars[i].date, 0, f["within_days"], f["min_catalyst_impact"])
        if due:
            nearest = min(due, key=lambda c: c["pcd"])
            out.append((i, nearest["pcd"]))
    return out


def suppress_rows(rows: list[tuple[int, date | None]], bars) -> list[tuple[int, date | None]]:
    """The live 7-calendar-day re-fire suppression (backtest_signals.suppress,
    carried over to (index, driving_pcd) rows)."""
    out, last = [], None
    for i, pcd in rows:
        d = bars[i].date
        if last is None or (d - last).days > SUPPRESS_DAYS:
            out.append((i, pcd))
            last = d
    return out


# --- calls framing ----------------------------------------------------------------

def make_call(bars, i: int, driving_pcd: date | None, risk_cfg: dict,
              horizon_days: int) -> dict | None:
    """One fixed-1R call per suppressed fire, graded by the PRODUCTION code.

    Entry = NEXT bar's open (a live fire is actionable at the following open;
    conservative vs entering at the signal close). ATR uses bars up to and
    including the fire day — known at that open. Expiry = min(default horizon,
    day BEFORE the driving catalyst's PCD) — the live sell-into-the-event rule
    — clamped to the entry date for a catalyst due immediately.
    """
    if i + 1 >= len(bars):
        return None
    eb = bars[i + 1]
    entry_px = eb.open if eb.open is not None else eb.close
    if entry_px is None:
        return None
    atr_val = atr(bars[: i + 1], risk_cfg.get("atr_window", 14))
    lv = build_levels(entry_px, "long", atr_val, risk_cfg.get("stop_atr_mult", 3.0),
                      risk_cfg.get("fallback_stop_pct", 0.08),
                      risk_cfg.get("reward_risk", 3.0))
    if lv is None:
        return None
    expiry = eb.date + timedelta(days=horizon_days)
    if driving_pcd is not None:
        expiry = min(expiry, driving_pcd - timedelta(days=1))
    expiry = max(expiry, eb.date)
    ex = grade_call("long", lv.entry, lv.stop, lv.target, expiry, bars[i + 1:])
    if ex is None:
        return None  # still open at data end — excluded (counted by caller)
    risk = lv.entry - lv.stop
    return {
        "fire_date": bars[i].date.isoformat(),
        "entry_date": eb.date.isoformat(),
        "entry_month": eb.date.strftime("%Y-%m"),
        "entry": lv.entry, "stop": lv.stop, "target": lv.target,
        "exit": ex.exit_price, "exit_date": ex.exit_date.isoformat(),
        "status": ex.status, "risk": risk,
        "r": (ex.exit_price - lv.entry) / risk,
        "hold_days": (ex.exit_date - eb.date).days,
        "expiry": expiry.isoformat(),
        "driving_pcd": driving_pcd.isoformat() if driving_pcd else None,
    }


def apply_slippage(rows: list[dict], tiers: dict[str, str]) -> None:
    """backtest_calls.py convention: tiered per-side bps on both fills, R
    recomputed against the ORIGINAL risk unit. Stored as r_net on each row."""
    for t in rows:
        bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(t["symbol"], "C"), 100) / 10_000
        entry = t["entry"] * (1 + bps)
        exit_ = t["exit"] * (1 - bps)
        t["r_net"] = (exit_ - entry) / t["risk"]


def cluster_bootstrap_ci90(rows: list[dict], key: str) -> tuple[float, float] | None:
    """90% CI of mean R, cluster bootstrap on (symbol, entry-month) — same
    clustering as both existing scripts."""
    clusters: dict[str, list[float]] = {}
    for t in rows:
        clusters.setdefault(f"{t['symbol']}|{t['entry_month']}", []).append(t[key])
    keys = list(clusters)
    if len(keys) < 5:
        return None
    rng = random.Random(42)
    means = []
    for _ in range(BOOT_ITERS):
        sample: list[float] = []
        for _ in range(len(keys)):
            sample.extend(clusters[rng.choice(keys)])
        if sample:
            means.append(sum(sample) / len(sample))
    means.sort()
    return means[int(0.05 * len(means))], means[int(0.95 * len(means))]


def equity_curve(rows: list[dict], max_open: int | None = None) -> tuple[list, list[dict]]:
    """Equal-risk (1R) sequential book: +r_net at each exit. With max_open set,
    a fire is SKIPPED when max_open calls are already open at its entry date
    (a slot frees the day after its exit). Returns (curve, taken_rows)."""
    ordered = sorted(rows, key=lambda t: (t["entry_date"], t["symbol"], t.get("flag", "")))
    taken: list[dict] = []
    open_exits: list[str] = []
    for t in ordered:
        open_exits = [x for x in open_exits if x >= t["entry_date"]]
        if max_open is not None and len(open_exits) >= max_open:
            continue
        taken.append(t)
        open_exits.append(t["exit_date"])
    events = sorted(taken, key=lambda t: t["exit_date"])
    curve, cum = [], 0.0
    for t in events:
        cum += t["r_net"]
        curve.append([t["exit_date"], round(cum, 4)])
    return curve, taken


def max_drawdown_r(curve: list) -> float:
    peak, dd = 0.0, 0.0
    for _, cum in curve:
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def summarize_calls(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    rs = [t["r_net"] for t in rows]
    curve, _ = equity_curve(rows)
    return {
        "n": len(rows),
        "clusters": len({f"{t['symbol']}|{t['entry_month']}" for t in rows}),
        "hit_rate": sum(1 for r in rs if r > 0) / len(rs),
        "avg_r_gross": sum(t["r"] for t in rows) / len(rows),
        "avg_r": sum(rs) / len(rs),
        "median_r": statistics.median(rs),
        "total_r": sum(rs),
        "max_dd_r": max_drawdown_r(curve),
        "avg_hold_days": sum(t["hold_days"] for t in rows) / len(rows),
        "target_rate": sum(1 for t in rows if t["status"] == "target_hit") / len(rows),
        "stop_rate": sum(1 for t in rows if t["status"] == "stopped") / len(rows),
        "expiry_rate": sum(1 for t in rows if t["status"] == "expired") / len(rows),
        "ci90_avg_r": cluster_bootstrap_ci90(rows, "r_net"),
    }


# --- main -------------------------------------------------------------------------

def main() -> None:  # noqa: PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="refetch bars")
    args = ap.parse_args()

    fcfg = _flags_full_config()
    _guard_pre_registered(fcfg)
    ccfg = calls_config()
    risk_cfg = ccfg.get("risk", {})
    horizon_days = ccfg.get("horizon", {}).get("default_days", 45)
    max_open = ccfg.get("max_open_calls", 10)
    impact_weights = scoring_config()["components"]["catalyst_score"]["impact_weights"]

    universe = [e["symbol"] for e in watchlist_config().get("universe", [])
                if e.get("active")]

    if CACHE.exists() and not args.refresh:
        raw = json.loads(CACHE.read_text())
        print(f"Loaded cached bars for {len(raw)} symbols ({CACHE})")
    else:
        print(f"Fetching daily bars for {len(universe) + 1} symbols…")
        raw = fetch_bars(universe + [BENCH], years=11)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(raw))
    if BENCH not in raw:
        print("FATAL: no benchmark bars.")
        sys.exit(1)

    if not PIT_STORE.exists():
        print(f"FATAL: {PIT_STORE} missing — run scripts.build_pit_catalysts first.")
        sys.exit(1)
    pit = json.loads(PIT_STORE.read_text())
    pit_symbols = pit.get("symbols", {})

    bench_bars, _ = to_adjusted_barlikes(raw[BENCH])
    bench_closes = [(b.date, b.close) for b in bench_bars]
    bench_by_date = dict(bench_closes)
    regime = xbi_above_50dma(bench_bars)

    flag_rows: dict[str, list[dict]] = {f: [] for f in ALL_FLAGS}
    flag_rows["baseline_all"] = []
    call_rows: dict[str, list[dict]] = {f: [] for f in ALL_FLAGS}
    open_at_end = {f: 0 for f in ALL_FLAGS}
    n_names, n_with_catalysts = 0, 0

    for sym in universe:
        if sym not in raw or len(raw[sym]) < 120:
            print(f"  {sym}: insufficient bars — excluded")
            continue
        n_names += 1
        bars, volumes = to_adjusted_barlikes(raw[sym])
        atrs = atr_series(bars)
        ma50 = sma_series(bars, 50)
        trials = pit_symbols.get(sym, [])
        cal = pit_calendar_by_bar(trials, bars, impact_weights)
        if any(cal):
            n_with_catalysts += 1

        fires: dict[str, list[tuple[int, date | None]]] = {
            "quiet_before_catalyst": fires_quiet_before_catalyst(bars, cal, fcfg),
            "pullback_into_catalyst": fires_pullback_into_catalyst(bars, cal, atrs, ma50, fcfg),
            "binary_event_within_n_days": fires_binary_event(bars, cal, fcfg),
            "pullback_price_half": [(i, None) for i in fires_pullback(bars, atrs, ma50)],
            "volume_anomaly": [(i, None) for i in fires_volume(bars, volumes)],
            "rel_strength_60d": [(i, None) for i in fires_rel_strength(bars, bench_by_date)],
        }
        for flag, rows in fires.items():
            sup = suppress_rows([(i, p) for i, p in rows if bars[i].date >= START], bars)
            for i, pcd in sup:
                g = grade(bars, i, bench_closes)   # forward XBI-excess framing
                if g:
                    g["symbol"] = sym
                    g["regime_up"] = regime.get(bars[i].date)
                    flag_rows[flag].append(g)
                c = make_call(bars, i, pcd, risk_cfg, horizon_days)  # calls framing
                if c is None:
                    open_at_end[flag] += 1
                    continue
                c["symbol"] = sym
                c["flag"] = flag
                c["regime_up"] = regime.get(date.fromisoformat(c["entry_date"]))
                call_rows[flag].append(c)
        for i in range(60, len(bars), BASELINE_GRID):
            if bars[i].date < START:
                continue
            g = grade(bars, i, bench_closes)
            if g:
                g["symbol"] = sym
                g["regime_up"] = regime.get(bars[i].date)
                flag_rows["baseline_all"].append(g)
        print(f"  {sym}: {len(bars)} bars, {len(trials)} PIT trials, fires "
              + ", ".join(f"{f}={len(fires[f])}" for f in ALL_FLAGS))

    # Slippage (tiers from full-sample median ADDV, as in backtest_calls.py).
    tiers = {}
    for sym in universe:
        if sym in raw and len(raw[sym]) >= 120:
            bars, volumes = to_adjusted_barlikes(raw[sym])
            tiers[sym] = tier_of(median_addv(bars, volumes))
    for rows in call_rows.values():
        apply_slippage(rows, tiers)

    # Sanity: every replayed flag type must fire; zero fires on a catalyst flag
    # over 10 years means a PIT-store or interval bug, not a finding.
    for flag in ALL_FLAGS:
        n = len(flag_rows[flag])
        print(f"fires[{flag}] = {n} (calls graded: {len(call_rows[flag])}, "
              f"open at data end: {open_at_end[flag]})")
        assert n > 0, f"SANITY FAIL: {flag} produced 0 fires over the replay window"

    call_summaries = {f: summarize_calls(call_rows[f]) for f in ALL_FLAGS}
    regime_split = {}
    for f in ALL_FLAGS:
        regime_split[f] = {
            "up": summarize_calls([t for t in call_rows[f] if t["regime_up"] is True]),
            "down": summarize_calls([t for t in call_rows[f] if t["regime_up"] is False]),
        }
    curves = {f: equity_curve(call_rows[f])[0] for f in ALL_FLAGS}
    all_calls = [t for f in LIVE_SET_FLAGS for t in call_rows[f]]
    combined_curve, combined_taken = equity_curve(all_calls, max_open=max_open)
    combined_summary = summarize_calls(combined_taken)
    combined_summary["skipped_at_cap"] = len(all_calls) - len(combined_taken)

    pit_stats = _pit_stats(pit_symbols, universe)

    excess_summaries = {
        h: {f: summarize_excess(flag_rows[f], h)
            for f in list(ALL_FLAGS) + ["baseline_all"]}
        for h in HORIZONS
    }

    _write_report(n_names, n_with_catalysts, bench_bars, pit, pit_stats,
                  excess_summaries, call_summaries, regime_split,
                  combined_summary, curves, combined_curve, open_at_end,
                  tiers, risk_cfg, horizon_days, max_open)
    print(f"Report written to {REPORT}")

    RESULTS.write_text(json.dumps(_round_floats({
        "generated": datetime.now(timezone.utc).isoformat(),
        "period": [START.isoformat(), bench_bars[-1].date.isoformat()],
        "n_names": n_names,
        "pit_stats": pit_stats,
        "flag_rows": flag_rows,
        "call_rows": call_rows,
        "call_summaries": call_summaries,
        "regime_split": regime_split,
        "excess_summaries": excess_summaries,
        "equity_curves": curves,
        "combined_book": {"summary": combined_summary, "curve": combined_curve,
                          "max_open_calls": max_open},
        "tiers": tiers,
    }), default=str))
    print(f"Per-fire rows + summaries written to {RESULTS}")


def _round_floats(obj, ndigits: int = 5):
    """Compact the results JSON (stats are computed on full precision first)."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def _pit_stats(pit_symbols: dict, universe: list[str]) -> dict:
    n_trials = sum(len(v) for v in pit_symbols.values())
    n_intervals = sum(len(t["timeline"]) for v in pit_symbols.values() for t in v)
    firsts = [t["timeline"][0]["from"] for v in pit_symbols.values()
              for t in v if t.get("timeline")]
    pre2016 = sum(1 for f in firsts if f < "2016-01-01")
    return {
        "names_in_store": len(pit_symbols),
        "names_with_trials": sum(1 for v in pit_symbols.values() if v),
        "names_without_trials": sorted(s for s in universe
                                       if not pit_symbols.get(s)),
        "trials": n_trials,
        "intervals": n_intervals,
        "earliest_record": min(firsts) if firsts else None,
        "trials_visible_before_2016": pre2016,
    }


def _fmt(v, dp=2, pct=False, sign=False):
    if v is None:
        return "n/a"
    if pct:
        return f"{v*100:+.2f}%" if sign else f"{v*100:.0f}%"
    return f"{v:+.{dp}f}" if sign else f"{v:.{dp}f}"


def _ci(ci, pct=False) -> str:
    if not ci:
        return "n/a"
    if pct:
        return f"[{ci[0]:+.2%}, {ci[1]:+.2%}]"
    return f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"


def _write_report(n_names, n_with_catalysts, bench_bars, pit, pit_stats,
                  excess_summaries, call_summaries, regime_split,
                  combined_summary, curves, combined_curve, open_at_end,
                  tiers, risk_cfg, horizon_days, max_open) -> None:
    lines: list[str] = []
    w = lines.append
    end_d = bench_bars[-1].date.isoformat()
    w("# 10-Year Calls-Engine Replay — ALL replayable signals, point-in-time catalyst calendar")
    w("")
    w(f"_Generated by `scripts/backtest_calls_10y.py` · {n_names} names "
      f"({n_with_catalysts} with PIT catalysts) · {START.isoformat()} → {end_d} · "
      f"adjusted daily bars + point-in-time ClinicalTrials.gov record history "
      f"(store built {pit.get('built', '?')[:10]} by `scripts/build_pit_catalysts.py`)_")
    w("")
    w("## Read this first")
    w("")
    w("- **The catalyst-conditioned flags are replayed for the FIRST TIME.** The")
    w("  point-in-time calendar is rebuilt from CT.gov's historical record versions:")
    w("  for each date d it uses what the registry **had been TOLD as of d** (PCD /")
    w("  status / phases at submission-lag granularity — a sponsor's update is only")
    w("  visible from the day it was posted, exactly like the live pipeline).")
    w("- **PCD is an ESTIMATE of primary completion, not a readout date.** Data")
    w("  often reads out months after (or before) the registered PCD; treat the")
    w("  catalyst windows as approximations of event proximity, not event dates.")
    w("- **Survivorship, relative-only**: today's universe — dead names absent.")
    w("  Absolute expectancies are not forecasts; only flag-vs-baseline and")
    w("  flag-vs-flag comparisons are meaningful.")
    w("- **Live gates NOT replayed (loud deviation)**: the composite>=55 gate and")
    w("  confidence/conviction sizing need hype/analyst/positioning history that")
    w("  does not exist. Every suppressed fire becomes a call at FIXED 1R. The live")
    w("  auto-trigger set (sentiment ramp / revision cluster / options+social) is")
    w("  itself not replayable; the combined book here is the REPLAYABLE set.")
    w("- Thresholds are the LIVE pre-registered flags.yaml/calls.yaml values")
    w("  (guarded by assertions), NOT fit on this data.")
    w("- Entry = the NEXT bar's OPEN after a fire (conservative: a fire computed on")
    w("  a close is actionable at the following open). Exits use the production")
    w("  `grade_call` — open-first, gap-aware. Slippage: tiered per-side bps")
    w("  (A=10/B=40/C=100) re-graded against the original risk unit, as in")
    w("  BACKTEST_CALLS.md; `avg R net` is the headline.")
    w("- These results are **WALLED OFF from live sizing** (TUNING.md): they set")
    w("  observe-only priorities and promotion candidates, never the paper book.")
    w("")
    w("## Point-in-time catalyst store")
    w("")
    w(f"- {pit_stats['names_with_trials']}/{pit_stats['names_in_store']} names with ≥1 "
      f"PHASE2/PHASE3 trial · {pit_stats['trials']} trials · "
      f"{pit_stats['intervals']} (pcd, status, phases) intervals")
    w(f"- earliest public record {pit_stats['earliest_record']} · "
      f"{pit_stats['trials_visible_before_2016']} trials already visible before 2016-01-01")
    no_tr = pit_stats["names_without_trials"]
    w(f"- names with NO sponsor-matched P2/P3 trials (radar gaps, same as live): "
      f"{', '.join(no_tr) if no_tr else 'none'}")
    w("- a trial enters the calendar only while its AS-OF-d status is")
    w("  not-yet-recruiting / recruiting / active-not-recruiting / enrolling-by-")
    w("  invitation and its as-of-d PCD is in the future — a completed or")
    w("  terminated record stops being a catalyst the day that update posts.")
    w("")
    w("## FLAG framing: forward XBI-excess per fire vs the unconditional baseline")
    w("")
    w("Same conventions as BACKTEST_SIGNALS.md: 7-day re-fire suppression, forward")
    w("5/21/63-bar return minus XBI, symbol|month cluster bootstrap. Baseline =")
    w("every-5th-bar unconditional entries: a flag must beat ITS OWN baseline row,")
    w("not zero (the survivors drift upward unconditionally).")
    w("")
    for h in ("1w", "1m", "3m"):
        w(f"### {h} horizon")
        w("")
        w("| signal | fires | clusters | hit vs XBI | avg excess | 90% CI (cluster bootstrap) |")
        w("|---|---|---|---|---|---|")
        for f in ["baseline_all", *ALL_FLAGS]:
            s = excess_summaries[h][f]
            if s.get("n", 0) == 0:
                w(f"| {f} | 0 | — | — | — | — |")
                continue
            w(f"| {f} | {s['n']} | {s['clusters']} | {s['hit_rate']:.0%} "
              f"| {s['avg_excess']:+.2%} | {_ci(s['ci90'], pct=True)} |")
        w("")
    base_1m = excess_summaries["1m"]["baseline_all"]
    base_avg = base_1m.get("avg_excess") or 0.0
    w(f"### Verdicts (1-month horizon — bar = the baseline's {base_avg:+.2%}, not zero)")
    w("")
    for f in ALL_FLAGS:
        s = excess_summaries["1m"][f]
        if s.get("n", 0) < 30:
            verdict = f"INSUFFICIENT (n={s.get('n', 0)}<30)"
        else:
            edge = s["avg_excess"] - base_avg
            lo, hi = s["ci90"]
            if edge > 0 and lo > base_avg:
                verdict = (f"SUPPORTED — beats baseline by {edge:+.2%} and CI90 low "
                           f"{lo:+.2%} clears the baseline mean")
            elif edge > 0:
                verdict = (f"WEAK — beats baseline by {edge:+.2%} but CI90 low {lo:+.2%} "
                           f"does not clear the baseline ({base_avg:+.2%}); could be drift")
            elif hi < base_avg:
                verdict = f"NEGATIVE — CI90 high {hi:+.2%} below the baseline (a headwind)"
            else:
                verdict = "UNSUPPORTED — no edge vs baseline"
        w(f"- **{f}**: {verdict}")
    w("")
    w("Multiple-comparison note: 6 signals × 3 horizons — single-horizon 'SUPPORTED'")
    w("hits deserve caution; consistency across horizons is the real tell.")
    w("")
    w("## CALLS framing: one fixed-1R call per suppressed fire")
    w("")
    w(f"Production `build_levels`/`grade_call` · stop {risk_cfg.get('stop_atr_mult')}xATR14 · "
      f"{risk_cfg.get('reward_risk')}:1 RR · expiry min({horizon_days}d, day BEFORE the driving "
      f"catalyst's PCD for catalyst-conditioned flags) · entry next open · net of tiered slippage.")
    w("")
    w("| flag | n | clusters | hit% | tgt% | stop% | expiry% | avg R gross | **avg R net** | 90% CI net (cluster bootstrap) | med R | total R | max DD (R) | hold d |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in ALL_FLAGS:
        s = call_summaries[f]
        if s.get("n", 0) == 0:
            w(f"| {f} | 0 | — | — | — | — | — | — | — | — | — | — | — |")
            continue
        w(f"| {f} | {s['n']} | {s['clusters']} | {_fmt(s['hit_rate'], pct=True)} "
          f"| {_fmt(s['target_rate'], pct=True)} | {_fmt(s['stop_rate'], pct=True)} "
          f"| {_fmt(s['expiry_rate'], pct=True)} | {_fmt(s['avg_r_gross'], 3)} "
          f"| **{_fmt(s['avg_r'], 3)}** | {_ci(s['ci90_avg_r'])} | {_fmt(s['median_r'], 3)} "
          f"| {_fmt(s['total_r'], 1)} | {_fmt(s['max_dd_r'], 1)} | {_fmt(s['avg_hold_days'], 0)} |")
    w("")
    for f in ALL_FLAGS:
        if open_at_end[f]:
            w(f"- {f}: {open_at_end[f]} fire(s) near the data end were still open "
              f"and are excluded.")
    w("")
    w("### Regime split (XBI vs its 50dma at entry, net of slippage)")
    w("")
    w("| flag | regime | n | hit% | avg R net | med R |")
    w("|---|---|---|---|---|---|")
    for f in ALL_FLAGS:
        for reg, label in (("up", "XBI above 50dma"), ("down", "XBI below 50dma")):
            s = regime_split[f][reg]
            if s.get("n", 0) == 0:
                w(f"| {f} | {label} | 0 | — | — | — |")
                continue
            w(f"| {f} | {label} | {s['n']} | {_fmt(s['hit_rate'], pct=True)} "
              f"| {_fmt(s['avg_r'], 3)} | {_fmt(s['median_r'], 3)} |")
    w("")
    w("### Equal-risk (1R) sequential books")
    w("")
    w("Per-flag books take EVERY suppressed fire (no concurrency cap — they answer")
    w("'what does this signal's stream of calls sum to', not 'what could one book")
    w("hold'). The combined book takes the replayed flags that exist as LIVE flag")
    w("types (quiet/pullback-into-catalyst/binary/volume/rel-strength — the")
    w("pullback PRICE-half continuity row is excluded to avoid double-counting its")
    w(f"own superset flag) and respects the live max of {max_open} concurrent open")
    w("calls. NOTE: this is NOT the live auto-trigger set, which is not replayable.")
    w("Full equity curves (date, cumulative R) are in")
    w("`backend/data/backtest_calls_10y_results.json`.")
    w("")
    w("| book | calls taken | total R | max DD (R) | avg R net / call |")
    w("|---|---|---|---|---|")
    for f in ALL_FLAGS:
        w(f"| {f} | {call_summaries[f].get('n', 0)} | "
          f"{_fmt(call_summaries[f].get('total_r'), 1)} | "
          f"{_fmt(call_summaries[f].get('max_dd_r'), 1)} | "
          f"{_fmt(call_summaries[f].get('avg_r'), 3)} |")
    w(f"| **combined (live flag types, ≤{max_open} open)** | {combined_summary.get('n', 0)} "
      f"(+{combined_summary.get('skipped_at_cap', 0)} skipped at cap) | "
      f"{_fmt(combined_summary.get('total_r'), 1)} | "
      f"{_fmt(combined_summary.get('max_dd_r'), 1)} | "
      f"{_fmt(combined_summary.get('avg_r'), 3)} |")
    w("")
    tier_counts: dict[str, int] = {}
    for t in tiers.values():
        tier_counts[t] = tier_counts.get(t, 0) + 1
    w(f"Universe liquidity tiers (full-sample median ADDV): {tier_counts} · "
      f"slippage A=10/B=40/C=100 bps per side.")
    w("")
    w("## Deviations from the live engine (read before acting)")
    w("")
    w("- **No composite>=55 gate, no confidence sizing, no 14d cooldown, no Tier-C")
    w("  exclusion**: hype/analyst/positioning components have no point-in-time")
    w("  history. Fires -> calls 1:1 at fixed 1R (Tier-C names ARE included, with")
    w("  100bps/side slippage). Live behavior would trade FEWER, larger calls.")
    w("- **The combined book is NOT the live trigger set**: none of the live")
    w("  auto-call triggers is replayable; conversely, most replayed flags are")
    w("  observe-only live. This measures signal quality, not the live book.")
    w("- **PIT calendar granularity**: CT.gov submission lag means a sponsor's")
    w("  internal slippage of a readout is invisible until posted — same blindness")
    w("  as the live pipeline, so the replay is faithful to what the desk would see.")
    w("- Catalyst flags replay ONLY CT.gov trial milestones: no PDUFA/AdComm/")
    w("  conference/earnings lanes (operator-curated or other-sourced live), so")
    w("  live catalyst flags fire on a superset of these events.")
    w("- Bars were fetched via the raw Yahoo chart API in this environment (the")
    w("  yfinance cookie flow is blocked here); identical fields/adjustments as the")
    w("  provider path.")
    w("")
    w("## Known limitations")
    w("")
    w("- Survivorship (current universe), longs only, no borrow/fees, daily bars.")
    w("- Younger names contribute only their listed history — the sample tilts recent.")
    w("- Overlapping calls within and across correlated names: `clusters` is the")
    w("  honest effective-sample-size guide, and the cluster bootstrap carries the")
    w("  dependence — but 10 years still spans only ~3 distinct biotech regimes.")
    w("- The per-name trial cap (60, phase-3 first) can drop old phase-2 catalysts")
    w("  for the largest sponsors (logged in the PIT build).")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
