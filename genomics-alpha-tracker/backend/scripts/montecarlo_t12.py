"""Monte Carlo of the paper book's next-12-month (T12) return distribution.

METHOD — empirical, not assumed:
  - Trade outcomes are RESAMPLED from the 10-year backtest's actual trades for
    the LIVE exit config (3xATR / 3:1 / 45d), net of tiered slippage, split by
    regime (XBI above/below its 50dma at entry). No normal-distribution
    assumption — the fat left tail (gap-through-stop) is in the data.
  - Per-trade risk is drawn from the CURRENT conviction-sized book's measured
    range (~1.0-2.1% of equity at the stop).
  - A year = a Poisson number of calls compounded sequentially.

SCENARIOS:
  base      historical regime mix (the 10y up/down frequency), ~48 calls/yr
  risk_on   all trades from the above-50dma pool, ~55 calls/yr
  bear_30   a -30% market-drawdown year: all trades from the below-50dma pool
            (which CONTAINS the 2020 and 2022 crash trades, gap-aware fills
            included), fewer signals (~30 calls/yr), PLUS a one-time crash-gap
            shock on the ~6 positions open at the drawdown's onset (each gaps
            an extra 0.25-1.5R beyond its stop).

HONESTY BLOCK (read before quoting):
  - Survivorship: the trade pool is today's universe — absolute levels are
    OPTIMISTIC; the spread between scenarios is the more trustworthy read.
  - Calls/yr is the weakest input (little live history) — sensitivity shown.
  - Simulates the AUTO paper book only; manual calls/overrides excluded.

Usage: python -m scripts.montecarlo_t12   (uses the cached 10y bars)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_calls import (  # noqa: E402
    CACHE, SLIPPAGE_BPS_BY_TIER, median_addv, simulate, tier_of,
    to_adjusted_barlikes, xbi_above_50dma,
)
from app.config import watchlist_config  # noqa: E402
from datetime import date  # noqa: E402

CONFIG = (3.0, 3.0, 45)          # the live exit config
RISK_RANGE = (0.010, 0.021)      # measured per-trade risk (fraction of equity)
N_SIMS = 10_000
CRASH_OPEN_POSITIONS = 6
CRASH_EXTRA_R = (0.25, 1.5)      # extra loss beyond the stop, per open position
REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "MONTECARLO_T12.md"


def build_trade_pools() -> tuple[list[float], list[float], list[float], float]:
    raw = json.loads(CACHE.read_text())
    universe = [e["symbol"] for e in watchlist_config().get("universe", [])]
    bench_bars, _ = to_adjusted_barlikes(raw["XBI"])
    regime = xbi_above_50dma(bench_bars)

    up, down = [], []
    for sym in universe:
        if sym not in raw or len(raw[sym]) < 120:
            continue
        bars, volumes = to_adjusted_barlikes(raw[sym])
        tier = tier_of(median_addv(bars, volumes))
        bps = SLIPPAGE_BPS_BY_TIER.get(tier, 100) / 10_000
        for t in simulate(bars, *CONFIG):
            net_r = ((t["exit"] * (1 - bps)) - (t["entry"] * (1 + bps))) / t["risk"]
            d = date.fromisoformat(t["entry_date"])
            (up if regime.get(d) else down).append(net_r)
    frac_up = len(up) / (len(up) + len(down))
    return up + down, up, down, frac_up


def simulate_year(pool_a: list[float], pool_b: list[float], frac_a: float,
                  lam: float, rng: random.Random, crash: bool = False) -> float:
    n = max(0, int(rng.gauss(lam, lam ** 0.5)))  # ~Poisson
    equity = 1.0
    crash_at = rng.randrange(max(1, n)) if crash and n else None
    for i in range(n):
        pool = pool_a if rng.random() < frac_a else pool_b
        r = rng.choice(pool)
        risk = rng.uniform(*RISK_RANGE)
        equity *= max(0.0, 1.0 + r * risk)
        if crash_at is not None and i == crash_at:
            for _ in range(CRASH_OPEN_POSITIONS):
                extra = rng.uniform(*CRASH_EXTRA_R)
                equity *= max(0.0, 1.0 - (1.0 + extra) * rng.uniform(*RISK_RANGE))
    return equity - 1.0


def pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def run_scenario(name, pool_a, pool_b, frac_a, lam, rng, crash=False) -> dict:
    outs = [simulate_year(pool_a, pool_b, frac_a, lam, rng, crash) for _ in range(N_SIMS)]
    return {
        "name": name, "lam": lam,
        "p5": pct(outs, 0.05), "p25": pct(outs, 0.25), "median": pct(outs, 0.50),
        "p75": pct(outs, 0.75), "p95": pct(outs, 0.95),
        "mean": sum(outs) / len(outs),
        "p_neg": sum(1 for o in outs if o < 0) / len(outs),
        "p_lt_neg10": sum(1 for o in outs if o < -0.10) / len(outs),
    }


def main() -> None:
    all_pool, up, down, frac_up = build_trade_pools()
    print(f"trade pools: {len(up)} risk-on, {len(down)} risk-off "
          f"(historical mix {frac_up:.0%} risk-on)")
    rng = random.Random(42)

    rows = [
        run_scenario("base (historical mix)", up, down, frac_up, 48, rng),
        run_scenario("risk-on year", up, down, 1.0, 55, rng),
        run_scenario("bear: -30% market year", up, down, 0.0, 30, rng, crash=True),
    ]
    sens = [run_scenario(f"base @ {lam}/yr", up, down, frac_up, lam, rng)
            for lam in (24, 48, 72)]

    lines = ["# Monte Carlo — paper book T12 return distribution", ""]
    lines.append(f"_10,000 sims/scenario · trades resampled from the 10y backtest of the "
                 f"live config (3xATR/3:1/45d), net of slippage · per-trade risk "
                 f"{RISK_RANGE[0]:.1%}-{RISK_RANGE[1]:.1%} of equity (measured) · "
                 f"pools: {len(up)} risk-on / {len(down)} risk-off trades_")
    lines.append("")
    hdr = "| scenario | calls/yr | P5 | P25 | median | P75 | P95 | mean | P(neg yr) | P(<-10%) |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    for title, rowset in (("## Scenarios", rows), ("## Sensitivity to call frequency", sens)):
        lines += [title, "", hdr, sep]
        for r in rowset:
            lines.append(
                f"| {r['name']} | {r['lam']} | {r['p5']:+.1%} | {r['p25']:+.1%} "
                f"| {r['median']:+.1%} | {r['p75']:+.1%} | {r['p95']:+.1%} "
                f"| {r['mean']:+.1%} | {r['p_neg']:.0%} | {r['p_lt_neg10']:.0%} |")
        lines.append("")
    lines += [
        "## Read before quoting",
        "",
        "- **Survivorship**: outcome pools come from today's (surviving) universe —",
        "  absolute levels are optimistic; trust the SPREAD between scenarios more",
        "  than any single number.",
        "- The bear scenario draws only crash-regime trades (2020/2022 included,",
        "  gap-aware fills) plus a one-time gap shock on ~6 open positions.",
        "- Calls/yr is the weakest input (thin live history) — see sensitivity.",
        "- Auto paper book only; manual calls and future signal promotions excluded.",
        "- Research, not investment advice.",
    ]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"report -> {REPORT}")
    for r in rows:
        print(f"  {r['name']}: median {r['median']:+.1%}  [P5 {r['p5']:+.1%} … "
              f"P95 {r['p95']:+.1%}]  P(neg) {r['p_neg']:.0%}")


if __name__ == "__main__":
    main()
