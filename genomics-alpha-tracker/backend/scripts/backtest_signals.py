"""Historical backtest of the REPLAYABLE signals over up to 10 years.

WHAT THIS TESTS: the signals whose inputs can be faithfully reconstructed
point-in-time from daily bars and FINRA archives:

  pullback_price_half   10-30% below the 30d high, >=1.5 ATRs deep, above the
                        50dma (the LIVE flag's price half — its catalyst half
                        cannot be replayed: no historical catalyst calendar)
  volume_anomaly        log-volume z >= 2.5 vs trailing 60 bars + $1M traded
                        (exactly the live thresholds — pre-registered, not fit)
  rel_strength_60d      60-bar return beats XBI by >= 15 points (momentum probe)
  high_short_interest   FINRA days-to-cover >= 10, fired 10 TRADING DAYS after
                        the settlement date (dissemination lag — no look-ahead)

Each fire (with the live 7-day re-fire suppression) is graded exactly like the
live flag track record: forward 5/21/63-bar returns minus XBI over the same
window. Compared against an UNCONDITIONAL baseline (every 5th bar, all names)
so "the signal works" is measured against "just being long these names".

WHAT THIS CANNOT TEST: social/hype, catalyst-conditioned, and analyst-revision
signals — no point-in-time history exists; they earn their record live only.
And the sample is TODAY'S universe: survivorship-biased, so only RELATIVE
readings (signal vs baseline, signal vs signal) are meaningful.

Results are WALLED OFF from live confidence/sizing: they inform which signals
deserve observe-only priority, never the paper book directly (TUNING.md).

Usage: python -m scripts.backtest_signals            # uses cached bars
       python -m scripts.backtest_signals --refresh  # refetch FINRA history
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calls.rules import BarLike  # noqa: E402
from scripts.backtest_calls import (  # noqa: E402
    CACHE,
    fetch_bars,
    to_adjusted_barlikes,
    xbi_above_50dma,
)
from app.config import settings, watchlist_config  # noqa: E402

BENCH = "XBI"
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "BACKTEST_SIGNALS.md"
FINRA_CACHE = Path(__file__).resolve().parent.parent / "data" / "finra_si_history.json"

HORIZONS = {"1w": 5, "1m": 21, "3m": 63}
SUPPRESS_DAYS = 7            # live re-fire suppression, mirrored
BASELINE_GRID = 5            # unconditional baseline: every 5th bar
SI_DTC_MIN = 10.0            # deeply shorted: days-to-cover threshold
SI_LAG_BARS = 10             # FINRA dissemination lag after settlement
BOOT_ITERS = 2000
MIN_DOLLAR_VOL = 1_000_000


# --- rolling feature series (all strictly backward-looking) ---------------------

def atr_series(bars: list[BarLike], window: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    trs: list[float] = []
    for i in range(1, len(bars)):
        p, b = bars[i - 1], bars[i]
        if None in (b.high, b.low, b.close, p.close):
            trs.append(trs[-1] if trs else 0.0)
        else:
            trs.append(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)))
        if len(trs) >= window:
            out[i] = sum(trs[-window:]) / window
    return out


def sma_series(bars: list[BarLike], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    s = 0.0
    for i, b in enumerate(bars):
        s += b.close
        if i >= n:
            s -= bars[i - n].close
        if i >= n - 1:
            out[i] = s / n
    return out


def fires_pullback(bars: list[BarLike], atrs, ma50) -> list[int]:
    idx = []
    for i in range(50, len(bars)):
        b = bars[i]
        window = bars[max(0, i - 29): i + 1]
        peak = max((x.high if x.high is not None else x.close) for x in window)
        if peak <= 0:
            continue
        depth = (peak - b.close) / peak
        a = atrs[i]
        if (0.10 <= depth <= 0.30 and ma50[i] is not None and b.close > ma50[i]
                and a and (peak - b.close) / a >= 1.5):
            idx.append(i)
    return idx


def fires_volume(bars: list[BarLike], volumes) -> list[int]:
    idx = []
    logs = [math.log(v + 1.0) if v is not None and v >= 0 else None for v in volumes]
    for i in range(60, len(bars)):
        base = [l for l in logs[i - 60:i] if l is not None]
        if len(base) < 21 or logs[i] is None:
            continue
        mean = sum(base) / len(base)
        var = sum((x - mean) ** 2 for x in base) / len(base)
        std = var ** 0.5
        if std == 0:
            continue
        z = (logs[i] - mean) / std
        dollar = (volumes[i] or 0) * bars[i].close
        if z >= 2.5 and dollar >= MIN_DOLLAR_VOL:
            idx.append(i)
    return idx


def fires_rel_strength(bars: list[BarLike], bench_close_by_date: dict) -> list[int]:
    idx = []
    for i in range(60, len(bars)):
        b0, b1 = bars[i - 60], bars[i]
        k0, k1 = bench_close_by_date.get(b0.date), bench_close_by_date.get(b1.date)
        if not (b0.close and k0 and k1):
            continue
        rs = (b1.close - b0.close) / b0.close - (k1 - k0) / k0
        if rs >= 0.15:
            idx.append(i)
    return idx


def fires_short_interest(bars: list[BarLike], si_rows: list[dict]) -> list[int]:
    """Fire SI_LAG_BARS trading days AFTER a settlement with days-to-cover >=
    threshold (publication lag — the desk couldn't have known sooner)."""
    idx = []
    dates = [b.date for b in bars]
    for row in si_rows:
        dtc = row.get("daysToCoverQuantity")
        sd = row.get("settlementDate")
        if dtc is None or sd is None or float(dtc) < SI_DTC_MIN:
            continue
        settle = date.fromisoformat(sd[:10])
        j = next((k for k, d in enumerate(dates) if d >= settle), None)
        if j is None or j + SI_LAG_BARS >= len(dates):
            continue
        idx.append(j + SI_LAG_BARS)
    return sorted(set(idx))


def suppress(fire_idx: list[int], bars: list[BarLike]) -> list[int]:
    """Mirror the live 7-calendar-day re-fire suppression."""
    out, last = [], None
    for i in fire_idx:
        d = bars[i].date
        if last is None or (d - last).days > SUPPRESS_DAYS:
            out.append(i)
            last = d
    return out


# --- grading ---------------------------------------------------------------------

def grade(bars: list[BarLike], i: int, bench_closes: list[tuple[date, float]]) -> dict | None:
    base = bars[i].close
    out = {"date": bars[i].date.isoformat(), "month": bars[i].date.strftime("%Y-%m")}
    b_idx = next((k for k, (d, _) in enumerate(bench_closes) if d >= bars[i].date), None)
    if b_idx is not None and bench_closes[b_idx][0] > bars[i].date:
        b_idx -= 1
    any_h = False
    for label, n in HORIZONS.items():
        if i + n < len(bars) and base:
            raw = (bars[i + n].close - base) / base
            exc = None
            if b_idx is not None and b_idx + n < len(bench_closes) and bench_closes[b_idx][1]:
                bret = (bench_closes[b_idx + n][1] - bench_closes[b_idx][1]) / bench_closes[b_idx][1]
                exc = raw - bret
            out[label] = {"raw": raw, "excess": exc}
            any_h = True
    return out if any_h else None


def summarize(rows: list[dict], label: str) -> dict:
    vals = [r[label]["excess"] for r in rows
            if r.get(label) and r[label]["excess"] is not None]
    if not vals:
        return {"n": 0}
    clusters: dict[str, list[float]] = {}
    for r in rows:
        if r.get(label) and r[label]["excess"] is not None:
            clusters.setdefault(f"{r['symbol']}|{r['month']}", []).append(r[label]["excess"])
    keys = list(clusters)
    rng = random.Random(42)
    means = []
    for _ in range(BOOT_ITERS):
        s: list[float] = []
        for _ in range(len(keys)):
            s.extend(clusters[rng.choice(keys)])
        means.append(sum(s) / len(s))
    means.sort()
    return {
        "n": len(vals), "clusters": len(keys),
        "hit_rate": sum(1 for v in vals if v > 0) / len(vals),
        "avg_excess": sum(vals) / len(vals),
        "ci90": [means[int(0.05 * BOOT_ITERS)], means[int(0.95 * BOOT_ITERS)]],
    }


def _fetch_finra(symbols: list[str]) -> dict[str, list[dict]]:
    import httpx
    out: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            r = httpx.post(
                "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest",
                json={"compareFilters": [{"fieldName": "symbolCode", "fieldValue": sym,
                                          "compareType": "EQUAL"}], "limit": 5000},
                headers={"Accept": "application/json"},
                timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            out[sym] = [{"settlementDate": x.get("settlementDate"),
                         "daysToCoverQuantity": x.get("daysToCoverQuantity")}
                        for x in (r.json() or [])]
            print(f"  FINRA {sym}: {len(out[sym])} settlements")
        except Exception as exc:  # noqa: BLE001
            print(f"  FINRA {sym}: failed ({exc})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="refetch FINRA SI history")
    args = ap.parse_args()

    universe = [e["symbol"] for e in watchlist_config().get("universe", [])]
    if not CACHE.exists():
        raw = fetch_bars(universe + [BENCH])
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(raw))
    else:
        raw = json.loads(CACHE.read_text())

    if FINRA_CACHE.exists() and not args.refresh:
        finra = json.loads(FINRA_CACHE.read_text())
    else:
        print("Fetching FINRA short-interest history…")
        finra = _fetch_finra([s for s in universe if s in raw])
        FINRA_CACHE.write_text(json.dumps(finra))

    bench_bars, _ = to_adjusted_barlikes(raw[BENCH])
    bench_closes = [(b.date, b.close) for b in bench_bars]
    bench_by_date = dict(bench_closes)
    regime = xbi_above_50dma(bench_bars)

    signal_rows: dict[str, list[dict]] = {
        "pullback_price_half": [], "volume_anomaly": [],
        "rel_strength_60d": [], "high_short_interest": [], "baseline_all": [],
    }
    n_names = 0
    for sym in universe:
        if sym not in raw or len(raw[sym]) < 120:
            continue
        n_names += 1
        bars, volumes = to_adjusted_barlikes(raw[sym])
        atrs = atr_series(bars)
        ma50 = sma_series(bars, 50)
        fires = {
            "pullback_price_half": suppress(fires_pullback(bars, atrs, ma50), bars),
            "volume_anomaly": suppress(fires_volume(bars, volumes), bars),
            "rel_strength_60d": suppress(fires_rel_strength(bars, bench_by_date), bars),
            "high_short_interest": suppress(
                fires_short_interest(bars, finra.get(sym, [])), bars),
            "baseline_all": list(range(60, len(bars), BASELINE_GRID)),
        }
        for sig, idxs in fires.items():
            for i in idxs:
                g = grade(bars, i, bench_closes)
                if g:
                    g["symbol"] = sym
                    g["regime_up"] = regime.get(bars[i].date)
                    signal_rows[sig].append(g)

    # --- summarize + write report ---
    lines: list[str] = []
    w = lines.append
    w("# Historical Signal Backtest (replayable signals only)")
    w("")
    w(f"_Generated by `scripts/backtest_signals.py` · {n_names} names · data through "
      f"{bench_bars[-1].date.isoformat()} · up to ~10y adjusted daily bars + FINRA archives_")
    w("")
    w("## Read this first")
    w("")
    w("- **Survivorship**: today's universe only — names that died are absent, so")
    w("  ONLY relative readings (signal vs baseline, signal vs signal) mean anything.")
    w("- **This is the replayable HALF of the engine.** Social/hype, catalyst and")
    w("  analyst-revision signals cannot be replayed (no point-in-time history) —")
    w("  they earn their record live. The pullback signal here is its PRICE half")
    w("  only; the live flag also requires a nearby catalyst.")
    w("- Thresholds are the LIVE config values (pre-registered, not fit here).")
    w("- Short interest fires 10 trading days after settlement (publication lag).")
    w("- These results are WALLED OFF from live sizing (TUNING.md): they set")
    w("  observe-only priorities, never the paper book.")
    w("")
    w("## Forward XBI-excess returns per signal")
    w("")
    w("Baseline = unconditional entries (every 5th bar, all names): what 'just being")
    w("long these names' earned vs XBI. A signal must beat ITS OWN baseline row.")
    w("")
    base_1m = summarize(signal_rows["baseline_all"], "1m")
    for horizon in ("1w", "1m", "3m"):
        w(f"### {horizon} horizon")
        w("")
        w("| signal | fires | clusters | hit vs XBI | avg excess | 90% CI (cluster bootstrap) |")
        w("|---|---|---|---|---|---|")
        for sig in ("baseline_all", "pullback_price_half", "volume_anomaly",
                    "rel_strength_60d", "high_short_interest"):
            s = summarize(signal_rows[sig], horizon)
            if s.get("n", 0) == 0:
                w(f"| {sig} | 0 | — | — | — | — |")
                continue
            ci = s["ci90"]
            w(f"| {sig} | {s['n']} | {s['clusters']} | {s['hit_rate']:.0%} "
              f"| {s['avg_excess']:+.2%} | [{ci[0]:+.2%}, {ci[1]:+.2%}] |")
        w("")

    # Verdicts at 1m. THE BAR IS THE BASELINE, NOT ZERO: the unconditional
    # baseline itself earns positive excess (survivorship drift), so a signal
    # only counts as supported if its CI90 LOW clears the baseline MEAN —
    # otherwise "signal works" is just "owning these survivors worked".
    base_avg = base_1m.get("avg_excess") or 0.0
    w(f"## Verdicts (1-month horizon — bar = the baseline's {base_avg:+.2%}, not zero)")
    w("")
    for sig in ("pullback_price_half", "volume_anomaly", "rel_strength_60d",
                "high_short_interest"):
        s = summarize(signal_rows[sig], "1m")
        if s.get("n", 0) < 30:
            verdict = "INSUFFICIENT (n<30)"
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
        w(f"- **{sig}**: {verdict}")
    w("")
    w("Multiple-comparison note: 4 signals × 3 horizons — treat single-horizon")
    w("'SUPPORTED' hits with caution; consistency across horizons is the real tell.")
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"Report written to {REPORT}")
    for sig in signal_rows:
        s = summarize(signal_rows[sig], "1m")
        if s.get("n"):
            print(f"  {sig}: n={s['n']} hit={s['hit_rate']:.0%} avg_excess={s['avg_excess']:+.2%}")


if __name__ == "__main__":
    main()
