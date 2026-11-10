"""Evidence for the RAMP_V4 slippage amendment (2026-09-02).

Walks the LIVE Hyperliquid BTC-PERP order book to measure what a market
order of a given notional actually costs in impact terms, and estimates
the size-INDEPENDENT latency term from recent realized volatility.

Read-only: hits only the public /info endpoint, signs nothing, places
nothing. Safe to run against the production venue at any time.

    python scripts/book_depth_probe.py

The amendment's claim is that impact is flat across the entire range this
system can trade, so a slippage sample at pilot size cannot license a
larger size - and neither could one at the larger size. Re-run this to
check the claim still holds before relying on it.
"""
from __future__ import annotations

import math
import statistics
import time

import httpx

INFO = "https://api.hyperliquid.xyz/info"
COIN = "BTC"
# the sizes that bracket the ramp: today, the next rung, and full scale
SIZES = (151, 281, 500, 1_000, 5_000, 10_000, 25_000, 56_000, 100_000,
         250_000)


def _post(client: httpx.Client, payload: dict):
    r = client.post(INFO, json=payload)
    r.raise_for_status()
    return r.json()


def book(client: httpx.Client) -> tuple[float, float, list[tuple[float, float]]]:
    lv = _post(client, {"type": "l2Book", "coin": COIN})["levels"]
    bids, asks = lv[0], lv[1]
    mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
    spread_bps = (float(asks[0]["px"]) - float(bids[0]["px"])) / mid * 1e4
    return mid, spread_bps, [(float(a["px"]), float(a["sz"])) for a in asks]


def impact_bps(notional: float, mid: float,
               asks: list[tuple[float, float]]) -> tuple[float, bool]:
    """Average fill price walking the ask book for a market BUY, in bps
    over mid. Second value is False when the visible book is exhausted
    (the true cost is then higher than reported)."""
    left, cost, got = notional, 0.0, 0.0
    for px, sz in asks:
        take = min(sz, left / px)
        cost += take * px
        got += take
        left -= take * px
        if left <= 1e-9:
            return (cost / got / mid - 1) * 1e4, True
    return ((cost / got / mid - 1) * 1e4 if got else 0.0), False


def latency_bps(client: httpx.Client, window_s: float, days: int = 3) -> float:
    """Expected |price move| over a window_s gap, from realized 1m vol."""
    now_ms = int(time.time() * 1000)
    candles = _post(client, {"type": "candleSnapshot", "req": {
        "coin": COIN, "interval": "1m",
        "startTime": now_ms - days * 86400 * 1000, "endTime": now_ms}})
    closes = [float(c["c"]) for c in candles]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    sd_1m = statistics.pstdev(rets)
    sd_w = sd_1m * math.sqrt(window_s / 60.0)
    ann = sd_1m * math.sqrt(365 * 24 * 60) * 100
    print(f"realized vol: 1m sd {sd_1m * 1e4:.2f} bps "
          f"(~{ann:.0f}% annualized, {len(closes)} candles)")
    return sd_w * math.sqrt(2 / math.pi) * 1e4


def main(snapshots: int = 20, spacing_s: float = 3.0) -> None:
    """A SINGLE snapshot is not evidence (counter-agent 2026-09-02): the
    first cut of the RAMP_V4 amendment published one draw as a venue
    property, and re-probing moved the large-size cells by 35x. Take many,
    report the distribution, and say plainly where the book is thin."""
    with httpx.Client(timeout=30) as client:
        per_size: dict[int, list[float]] = {n: [] for n in SIZES}
        exhausted: dict[int, int] = {n: 0 for n in SIZES}
        mids, spreads, depths = [], [], []
        for i in range(snapshots):
            mid, spread_bps, asks = book(client)
            mids.append(mid)
            spreads.append(spread_bps)
            depths.append(sum(px * sz for px, sz in asks))
            for n in SIZES:
                imp, complete = impact_bps(n, mid, asks)
                per_size[n].append(imp)
                if not complete:
                    exhausted[n] += 1
            if i < snapshots - 1:
                time.sleep(spacing_s)
        print(f"{COIN}: {snapshots} snapshots {spacing_s:g}s apart | "
              f"mid {min(mids):,.0f}-{max(mids):,.0f}")
        print(f"spread {min(spreads):.3f}-{max(spreads):.3f} bps "
              f"(half-spread {min(spreads) / 2:.3f}-{max(spreads) / 2:.3f} - "
              f"an order that fits at best offer costs EXACTLY this)")
        print(f"visible ask depth (all {len(SIZES) and 20} levels) "
              f"${min(depths):,.0f}-${max(depths):,.0f}\n")
        print(f"{'notional':>12} {'min':>8} {'median':>8} {'max':>8}   "
              f"book exhausted")
        for n in SIZES:
            v = sorted(per_size[n])
            med = v[len(v) // 2]
            ex = exhausted[n]
            print(f"${n:>11,} {v[0]:>8.3f} {med:>8.3f} {v[-1]:>8.3f}   "
                  f"{ex}/{snapshots}" + ("  <-- THIN" if ex else ""))
        lat = latency_bps(client, window_s=20.0)
        print(f"\nlatency term for ONE 20s poll gap: {lat:.2f} bps "
              f"(expected |move|, modeled from realized vol - NOT a measured "
              f"per-fill slip dispersion).")
        print("Read the small sizes, not the large ones: where impact equals "
              "half-spread in every snapshot, the order fit at best offer "
              "and cost is size-INDEPENDENT. Large-size cells move with book "
              "state and are not a venue property. Calm-tape only.")


if __name__ == "__main__":
    main()
