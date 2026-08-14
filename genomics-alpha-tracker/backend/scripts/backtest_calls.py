"""Backtest of the trade-call EXIT MECHANICS on real market data.

WHAT THIS TESTS: the exit parameterization of the calls engine — stop width
(x ATR14), reward:risk multiple, and time-stop — using the EXACT same level
construction (`build_levels`) and grading (`grade_call`, gap-aware fills) as
the live engine, so measured defaults transfer.

WHAT THIS DOES NOT TEST: the signal (flags/composite). No historical flag,
social or revision data exists yet — signal validation comes from the live
flag track record (/flags/track-record) as it accrues. Entries are a FIXED
bar-index grid, identical for every config (truly paired — see simulate()),
so cross-config differences are pure exit mechanics and only RELATIVE
statements between configs are meaningful. Absolute expectancy is NOT — the
sample is the CURRENT universe (survivorship) with no borrow/fees.

Methodological guards (from the adversarial design review):
  - split-adjusted OHLC (adj factor applied to open/high/low from adj_close)
  - open-first, gap-aware exit fills (an open beyond a level resolves at the
    open — a gap-up-through-target day that fades is a WIN, not a stop)
  - genuinely paired entries: a fixed bar-index grid, identical across all
    configs, truncated so the longest time-stop resolves before data ends
  - cluster bootstrap by (symbol, entry-month) for the avg-R confidence band
    (this carries the overlapping-trade dependence pairing introduces)
  - plateau selection (neighborhood-robust), never the argmax of the grid
  - regime split: XBI above/below its 50dma at entry
  - slippage sensitivity by liquidity tier (10/40/100 bps per side)

Usage:
  python -m scripts.backtest_calls            # uses cached bars if present
  python -m scripts.backtest_calls --refresh  # refetch bars from the provider
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike, atr, build_levels, grade_call  # noqa: E402
from app.config import watchlist_config  # noqa: E402

BENCH = "XBI"
CACHE = Path(__file__).resolve().parent.parent / "data" / "backtest_bars.json"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_CALLS.md"

STOP_MULTS = [1.5, 2.0, 2.5, 3.0]
REWARD_RISKS = [1.5, 2.0, 3.0]
TIME_STOPS = [20, 30, 45]            # calendar days, matching the live engine
ENTRY_GRID_BARS = 5                  # attempt an entry every 5th bar when flat
ATR_WARMUP_BARS = 20
FALLBACK_STOP_PCT = 0.08
BOOTSTRAP_ITERS = 1000
SLIPPAGE_BPS_BY_TIER = {"A": 10, "B": 40, "C": 100}  # per side


# --- data -----------------------------------------------------------------------

def fetch_bars(symbols: list[str], years: int = 10) -> dict[str, list[dict]]:
    from app.ingestion.providers.base import get_provider

    provider = get_provider()
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=int(365.25 * years) + 30)
    out: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            bars = provider.get_ohlcv(sym, start, end)
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym}: fetch failed ({exc}) — skipped")
            continue
        if bars:
            out[sym] = bars
            print(f"  {sym}: {len(bars)} bars")
    return out


def to_adjusted_barlikes(rows: list[dict]) -> tuple[list[BarLike], list[float | None]]:
    """Split/dividend-adjust OHLC via the adj_close/close factor per bar.

    Unadjusted bars make ATR and stop levels fictitious across splits.
    Falls back to raw values when adj_close is missing.
    """
    bars: list[BarLike] = []
    volumes: list[float | None] = []
    for r in sorted(rows, key=lambda r: r["date"]):
        c = r.get("close")
        if c in (None, 0):
            continue
        adj = r.get("adj_close")
        k = (adj / c) if (adj not in (None, 0)) else 1.0
        bars.append(BarLike(
            date=date.fromisoformat(r["date"][:10]),
            high=None if r.get("high") is None else r["high"] * k,
            low=None if r.get("low") is None else r["low"] * k,
            close=c * k,
            open=None if r.get("open") is None else r["open"] * k,
        ))
        volumes.append(r.get("volume"))
    return bars, volumes


# --- helpers --------------------------------------------------------------------

def median_addv(bars: list[BarLike], volumes: list[float | None]) -> float | None:
    dollars = sorted(
        b.close * v for b, v in zip(bars, volumes)
        if b.close is not None and v is not None
    )
    if not dollars:
        return None
    mid = len(dollars) // 2
    return dollars[mid] if len(dollars) % 2 else (dollars[mid - 1] + dollars[mid]) / 2


def tier_of(addv: float | None) -> str:
    if addv is None or addv < 5e6:
        return "C"
    return "A" if addv >= 25e6 else "B"


def xbi_above_50dma(bench: list[BarLike]) -> dict[date, bool]:
    closes = [b.close for b in bench]
    out: dict[date, bool] = {}
    for i, b in enumerate(bench):
        if i >= 49:
            ma = sum(closes[i - 49: i + 1]) / 50
            out[b.date] = closes[i] > ma
    return out


def high_30d(bars: list[BarLike], i: int) -> float | None:
    window = [b.high if b.high is not None else b.close for b in bars[max(0, i - 29): i + 1]]
    window = [h for h in window if h is not None]
    return max(window) if window else None


def sma(bars: list[BarLike], i: int, n: int) -> float | None:
    if i + 1 < n:
        return None
    vals = [b.close for b in bars[i - n + 1: i + 1] if b.close is not None]
    return sum(vals) / len(vals) if len(vals) == n else None


# --- simulation -------------------------------------------------------------------

def simulate(
    bars: list[BarLike],
    stop_mult: float,
    rr: float,
    horizon_days: int,
    entry_filter=None,
) -> list[dict]:
    """Systematic trades on one name with GENUINELY PAIRED entries.

    Entry candidates are every ENTRY_GRID_BARS-th bar by INDEX — independent
    of position state — and the entry set is truncated so that the LONGEST
    time-stop in the grid can still resolve before the data ends. Every config
    therefore trades the *identical* entry dates: cross-config differences are
    pure exit mechanics. The price of pairing is overlapping trades per name;
    the (symbol, entry-month) cluster bootstrap carries that dependence.
    Exits use the LIVE grade_call (open-first, gap-aware).
    """
    trades: list[dict] = []
    if not bars:
        return trades
    last_date = bars[-1].date
    entry_cutoff = last_date - timedelta(days=max(TIME_STOPS) + 7)
    for i in range(ATR_WARMUP_BARS, len(bars) - 1, ENTRY_GRID_BARS):
        b = bars[i]
        if b.close is None or b.date > entry_cutoff:
            continue
        if entry_filter is not None and not entry_filter(bars, i):
            continue
        atr_val = atr(bars[: i + 1], 14)  # strictly bars <= entry date
        lv = build_levels(b.close, "long", atr_val, stop_mult, FALLBACK_STOP_PCT, rr)
        if lv is None:
            continue
        expiry = b.date + timedelta(days=horizon_days)
        ex = grade_call("long", lv.entry, lv.stop, lv.target, expiry, bars[i + 1:])
        if ex is None:
            continue  # data gap past expiry — cutoff makes this rare
        risk = lv.entry - lv.stop
        trades.append({
            "entry_date": b.date.isoformat(),
            "entry_month": b.date.strftime("%Y-%m"),
            "entry": lv.entry,
            "exit": ex.exit_price,
            "risk": risk,
            "status": ex.status,
            "r": (ex.exit_price - lv.entry) / risk,
            "ret": (ex.exit_price - lv.entry) / lv.entry,
            "hold_days": (ex.exit_date - b.date).days,
        })
    return trades


def pullback_filter(bars: list[BarLike], i: int) -> bool:
    """Entry-timing sanity check for the pullback flag's PRICE half:
    >=10% and <=30% below the 30d high, above the 50dma. (The catalyst half
    cannot be backtested — no historical catalyst dataset.)"""
    b = bars[i]
    hi = high_30d(bars, i)
    ma50 = sma(bars, i, 50)
    if b.close is None or hi in (None, 0) or ma50 is None:
        return False
    depth = (hi - b.close) / hi
    return 0.10 <= depth <= 0.30 and b.close > ma50


# --- statistics ---------------------------------------------------------------------

def cluster_bootstrap_ci(trades: list[dict], iters: int = BOOTSTRAP_ITERS) -> tuple[float, float] | None:
    """95% CI of mean R via cluster bootstrap on (symbol, entry-month).

    Overlopping-in-time positions across 32 correlated names mean the naive n
    wildly overstates independence; resampling whole clusters keeps the
    within-cluster correlation intact.
    """
    clusters: dict[str, list[float]] = {}
    for t in trades:
        clusters.setdefault(f"{t['symbol']}|{t['entry_month']}", []).append(t["r"])
    keys = list(clusters)
    if len(keys) < 5:
        return None
    rng = random.Random(42)
    means = []
    for _ in range(iters):
        sample: list[float] = []
        for _ in range(len(keys)):
            sample.extend(clusters[rng.choice(keys)])
        if sample:
            means.append(sum(sample) / len(sample))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means))]


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    rs = [t["r"] for t in trades]
    rs_sorted = sorted(rs)
    return {
        "n": len(trades),
        "clusters": len({f"{t['symbol']}|{t['entry_month']}" for t in trades}),
        "win_rate": sum(1 for r in rs if r > 0) / len(rs),
        "avg_r": sum(rs) / len(rs),
        "median_r": statistics.median(rs),
        "p05_r": rs_sorted[int(0.05 * len(rs_sorted))],
        "p95_r": rs_sorted[min(len(rs_sorted) - 1, int(0.95 * len(rs_sorted)))],
        "avg_hold_days": sum(t["hold_days"] for t in trades) / len(trades),
        "target_rate": sum(1 for t in trades if t["status"] == "target_hit") / len(trades),
        "stop_rate": sum(1 for t in trades if t["status"] == "stopped") / len(trades),
        "expiry_rate": sum(1 for t in trades if t["status"] == "expired") / len(trades),
    }


def with_slippage(trades: list[dict], tiers: dict[str, str]) -> list[dict]:
    """Re-grade every trade with tiered per-side slippage on both fills.

    R is recomputed against the ORIGINAL risk unit — this is exactly why tight
    stops look better frictionless than they trade: a small risk unit makes
    fixed slippage cost several tenths of an R per round trip.
    """
    out = []
    for t in trades:
        bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(t["symbol"], "C"), 100) / 10_000
        entry = t["entry"] * (1 + bps)
        exit_ = t["exit"] * (1 - bps)
        out.append({**t, "r": (exit_ - entry) / t["risk"]})
    return out


# --- plateau selection -----------------------------------------------------------------

def plateau_pick(grid_stats: dict[tuple, dict], key: str = "avg_r") -> tuple | None:
    """Pick the exit config by NEIGHBORHOOD robustness, not argmax.

    Score of a cell = the MINIMUM `key` among itself and its axis-neighbors
    (in stop_mult and rr, same time_stop). The best worst-neighborhood wins:
    a config whose neighbors agree beats a lonely noisy peak.
    """
    def neighbors(cell):
        s, r, h = cell
        si, ri = STOP_MULTS.index(s), REWARD_RISKS.index(r)
        cells = [cell]
        if si > 0:
            cells.append((STOP_MULTS[si - 1], r, h))
        if si < len(STOP_MULTS) - 1:
            cells.append((STOP_MULTS[si + 1], r, h))
        if ri > 0:
            cells.append((s, REWARD_RISKS[ri - 1], h))
        if ri < len(REWARD_RISKS) - 1:
            cells.append((s, REWARD_RISKS[ri + 1], h))
        return cells

    best, best_score = None, None
    for cell, stats in grid_stats.items():
        if stats.get("n", 0) < 100:
            continue
        neigh = [grid_stats.get(c, {}).get(key) for c in neighbors(cell)]
        neigh = [v for v in neigh if v is not None]
        if not neigh:
            continue
        score = min(neigh)
        if best_score is None or score > best_score:
            best, best_score = cell, score
    return best


# --- main -----------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="refetch bars from the provider")
    args = ap.parse_args()

    universe = [e["symbol"] for e in watchlist_config().get("universe", [])]
    symbols = universe + [BENCH]

    if CACHE.exists() and not args.refresh:
        raw = json.loads(CACHE.read_text())
        print(f"Loaded cached bars for {len(raw)} symbols ({CACHE})")
    else:
        print(f"Fetching ~10y daily bars for {len(symbols)} symbols…")
        raw = fetch_bars(symbols)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(raw))
        print(f"Cached to {CACHE}")

    if BENCH not in raw:
        print("FATAL: no benchmark bars; cannot regime-split.")
        sys.exit(1)

    data: dict[str, tuple[list[BarLike], list]] = {}
    tiers: dict[str, str] = {}
    for sym in universe:
        if sym not in raw or len(raw[sym]) < 120:
            print(f"  {sym}: insufficient bars — excluded")
            continue
        bars, volumes = to_adjusted_barlikes(raw[sym])
        data[sym] = (bars, volumes)
        tiers[sym] = tier_of(median_addv(bars, volumes))

    bench_bars, _ = to_adjusted_barlikes(raw[BENCH])
    regime_map = xbi_above_50dma(bench_bars)

    print(f"\nSimulating {len(STOP_MULTS) * len(REWARD_RISKS) * len(TIME_STOPS)} exit configs "
          f"on {len(data)} names (non-overlapping systematic entries)…")

    grid_trades: dict[tuple, list[dict]] = {}
    for s in STOP_MULTS:
        for r in REWARD_RISKS:
            for h in TIME_STOPS:
                all_trades: list[dict] = []
                for sym, (bars, _) in data.items():
                    for t in simulate(bars, s, r, h):
                        t["symbol"] = sym
                        t["regime_up"] = regime_map.get(date.fromisoformat(t["entry_date"]))
                        all_trades.append(t)
                grid_trades[(s, r, h)] = all_trades

    grid_stats = {cell: summarize(tr) for cell, tr in grid_trades.items()}
    for cell, stats in grid_stats.items():
        stats["avg_r_ci95"] = cluster_bootstrap_ci(grid_trades[cell])
        # Net of tiered slippage — the number that decides the pick. Tight
        # stops shrink the risk unit, so frictionless grids systematically
        # flatter them; selecting on net R corrects that.
        net = summarize(with_slippage(grid_trades[cell], tiers))
        stats["avg_r_net"] = net.get("avg_r")
        stats["win_rate_net"] = net.get("win_rate")

    pick = plateau_pick(grid_stats, key="avg_r_net")

    # Regime split (gross AND net) + slippage for the picked config.
    picked_trades = grid_trades.get(pick, [])
    picked_net = with_slippage(picked_trades, tiers)
    up = summarize([t for t in picked_trades if t["regime_up"] is True])
    down = summarize([t for t in picked_trades if t["regime_up"] is False])
    up_net = summarize([t for t in picked_net if t["regime_up"] is True])
    down_net = summarize([t for t in picked_net if t["regime_up"] is False])
    slipped = summarize(picked_net)

    # Pullback entry-timing sanity check under the picked exit config.
    s, r, h = pick if pick else (2.0, 2.0, 30)
    base_trades, pb_trades = [], []
    for sym, (bars, _) in data.items():
        for t in simulate(bars, s, r, h):
            t["symbol"] = sym
            base_trades.append(t)
        for t in simulate(bars, s, r, h, entry_filter=pullback_filter):
            t["symbol"] = sym
            pb_trades.append(t)
    base_sum, pb_sum = summarize(base_trades), summarize(pb_trades)
    pb_ci = cluster_bootstrap_ci(pb_trades)
    base_ci = cluster_bootstrap_ci(base_trades)

    _write_report(grid_stats, pick, up, down, up_net, down_net, slipped,
                  base_sum, pb_sum, base_ci, pb_ci, tiers, len(data), bench_bars)
    print(f"\nReport written to {REPORT}")
    if pick:
        print(f"Plateau pick: stop {pick[0]}xATR, {pick[1]}:1 reward:risk, {pick[2]}d time-stop")


def _fmt(v, dp=2, pct=False):
    if v is None:
        return "n/a"
    return f"{v*100:.0f}%" if pct else f"{v:.{dp}f}"


def _write_report(grid_stats, pick, up, down, up_net, down_net, slipped,
                  base_sum, pb_sum, base_ci, pb_ci, tiers, n_names, bench_bars) -> None:
    lines: list[str] = []
    w = lines.append
    w("# Trade-Call Exit-Mechanics Backtest")
    w("")
    w(f"_Generated by `scripts/backtest_calls.py` · data through "
      f"{bench_bars[-1].date.isoformat()} · {n_names} names, up to ~10y adjusted daily bars (FMP)_")
    w("")
    w("## What this is — and is not")
    w("")
    w("This backtests the **exit mechanics** of the calls engine (stop width x ATR14,")
    w("reward:risk, time-stop) with a **fixed bar-index entry grid** (every 5th trading")
    w("bar, independent of position state, truncated so the longest time-stop resolves")
    w("in-sample) using the *exact* live level/grading code — open-first, gap-aware")
    w("fills. Entries are therefore **identical across all configs (truly paired)**;")
    w("the trades on one name overlap in time, and the cluster bootstrap carries that")
    w("dependence.")
    w("")
    w("**It does NOT validate the signal.** No historical flag/social/revision data")
    w("exists yet; signal validation accrues live via `/flags/track-record`. And because")
    w("the sample is the *current* universe (survivorship — today's dead names are")
    w("absent), **absolute expectancy numbers are not meaningful — only relative")
    w("comparisons between exit configs are.** Do not quote the avg-R of any cell as an")
    w("expected live return.")
    w("")
    w("## Exit-config grid (all cells)")
    w("")
    w("`avg R net` re-grades every trade with tiered per-side slippage (A=10 / B=40 /")
    w("C=100 bps) — **the pick is made on net numbers**. Tight stops shrink the risk")
    w("unit, so a frictionless grid systematically flatters them; net-R corrects that.")
    w("")
    w("| stop xATR | R:R | time-stop | n | clusters | win% | tgt% | stop% | expiry% | avg R | avg R net | 95% CI gross (cluster bootstrap) | med R | p05 R | hold d |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (s, r, h), st in sorted(grid_stats.items()):
        if st.get("n", 0) == 0:
            continue
        ci = st.get("avg_r_ci95")
        ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
        mark = " **⬅ pick**" if (s, r, h) == pick else ""
        w(f"| {s} | {r} | {h}d | {st['n']} | {st['clusters']} | {_fmt(st['win_rate'],pct=True)} "
          f"| {_fmt(st['target_rate'],pct=True)} | {_fmt(st['stop_rate'],pct=True)} "
          f"| {_fmt(st['expiry_rate'],pct=True)} | {_fmt(st['avg_r'],3)} | {_fmt(st.get('avg_r_net'),3)} | {ci_str} "
          f"| {_fmt(st['median_r'],3)} | {_fmt(st['p05_r'],2)} | {_fmt(st['avg_hold_days'],0)}{mark} |")
    w("")
    w("## Selection method: plateau on NET R, not argmax")
    w("")
    w("The pick maximizes the **worst slippage-adjusted avg-R in its parameter")
    w("neighborhood** (adjacent stop and R:R cells at the same time-stop). The argmax of")
    w("36 noisy cells is noise; a config whose neighbors agree is evidence of a real")
    w("plateau — and selecting on gross R would reward exactly the tight-stop configs")
    w("that trading costs punish hardest.")
    w("")
    if pick:
        w(f"**Pick: stop {pick[0]}xATR14 · {pick[1]}:1 reward:risk · {pick[2]}d time-stop**")
    else:
        w("**No pick: insufficient trades per cell.**")
    w("")
    w("### Regime split for the pick (XBI vs its 50dma at entry)")
    w("")
    w("| regime | n | win% | avg R gross | avg R net | med R gross |")
    w("|---|---|---|---|---|---|")
    w(f"| XBI above 50dma | {up.get('n',0)} | {_fmt(up.get('win_rate'),pct=True)} | {_fmt(up.get('avg_r'),3)} | {_fmt(up_net.get('avg_r'),3)} | {_fmt(up.get('median_r'),3)} |")
    w(f"| XBI below 50dma | {down.get('n',0)} | {_fmt(down.get('win_rate'),pct=True)} | {_fmt(down.get('avg_r'),3)} | {_fmt(down_net.get('avg_r'),3)} | {_fmt(down.get('median_r'),3)} |")
    w("")
    w("If the sign of avg-R flips across regimes, treat the pick as regime-conditional —")
    w("the honest default is the one that is robust in both, and the regime strip on the")
    w("Today tab tells you which regime you are in.")
    w("")
    w("### Slippage sensitivity for the pick (per-side, by liquidity tier)")
    w("")
    tier_counts = {}
    for t in tiers.values():
        tier_counts[t] = tier_counts.get(t, 0) + 1
    w(f"Universe tiers: {tier_counts}. Slippage model: A=10bps, B=40bps, C=100bps per side.")
    w("(Backtest tiers use full-sample median ADDV; the live app tiers on the trailing")
    w("20 bars — a name near a boundary can be tiered differently live.)")
    w("")
    w(f"- avg R without slippage: **{_fmt(grid_stats.get(pick, {}).get('avg_r'), 3)}**")
    w(f"- avg R with tiered slippage: **{_fmt(slipped.get('avg_r'), 3)}** (n={slipped.get('n', 0)})")
    w("")
    w("If a comparison you care about flips sign under slippage, that is a finding —")
    w("size down or skip thin names, which is why Tier C is excluded from auto-calls.")
    w("")
    w("## Pullback entry-timing sanity check (NOT flag validation)")
    w("")
    w("Same exit config; entries gated by the pullback flag's **price half** only")
    w("(10-30% below the 30d high AND above the 50dma). The catalyst half cannot be")
    w("backtested (no historical catalyst dataset), and the pullback condition selects")
    w("different volatility regimes than the calendar baseline — read direction, not size.")
    w("")
    w("| entries | n | clusters | win% | avg R | 95% CI | med R |")
    w("|---|---|---|---|---|---|---|")
    bci = f"[{base_ci[0]:.3f}, {base_ci[1]:.3f}]" if base_ci else "n/a"
    pci = f"[{pb_ci[0]:.3f}, {pb_ci[1]:.3f}]" if pb_ci else "n/a"
    w(f"| systematic baseline | {base_sum.get('n',0)} | {base_sum.get('clusters','-')} | {_fmt(base_sum.get('win_rate'),pct=True)} | {_fmt(base_sum.get('avg_r'),3)} | {bci} | {_fmt(base_sum.get('median_r'),3)} |")
    w(f"| pullback-gated | {pb_sum.get('n',0)} | {pb_sum.get('clusters','-')} | {_fmt(pb_sum.get('win_rate'),pct=True)} | {_fmt(pb_sum.get('avg_r'),3)} | {pci} | {_fmt(pb_sum.get('median_r'),3)} |")
    w("")
    w("## Known limitations (read before quoting any number)")
    w("")
    w("- **Survivorship**: current-universe bars only; blown-up names are absent.")
    w("- **No signal selection**: systematic entries ≠ flag-triggered entries.")
    w("- **Up to 10 years spans several regimes** (2020 crash, 2021 biotech bubble,")
    w("  2022 rate shock) — but younger names contribute only their listed history,")
    w("  so the sample tilts recent.")
    w("- **Longs only**, no borrow/fees, daily bars (no intraday stop dynamics).")
    w(f"- Trades overlap within AND across the {n_names} correlated names (the price of")
    w("  truly paired entries) — hence cluster bootstrap, and `clusters` is the honest")
    w("  effective-sample-size guide, not `n`.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
