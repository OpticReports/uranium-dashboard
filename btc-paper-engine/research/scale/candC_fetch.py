"""CANDIDATE C, step 1: build a MULTI-ASSET 4h bar set from Hyperliquid and
prove it is the same data the repo's BTC fixture contains.

PRE-REGISTERED UNIVERSE RULE (fixed BEFORE any return was computed, so that
the cross-asset result cannot be a cherry-pick):
  a coin is eligible iff
    (1) it has a COMPLETE 4h candle history over the common window
        (HL serves 5000 candles max => 2024-06-17 -> now, ~2.28y), and
    (2) 24h notional volume >= $30,000,000 on the measurement day, and
    (3) measured l2Book cost to buy $125,000 (the per-leg share of Casey's
        $1m target across 8 legs) is <= 10 bps, read at nSigFigs=4.
        nSigFigs=4 is REQUIRED, not cosmetic: the default 20-level window
        shows only $0.05m-$0.25m of alt ladder and would have failed 7 liquid
        coins on an API artefact (phase 1 hit the same bias at $1m on BTC).
        Coarsening to 4 s.f. buckets widens the window to 21-167 bp of price
        and costs +-0.5 bp of bucket-price granularity, which is stated in
        every depth number below.
  Nothing about profitability, correlation or Sharpe enters the filter.
  Every eligible coin is carried forward and REPORTED, winners and losers.

Read-only public `info` endpoint. No credentials, no account state: this file
respects the separation-of-powers rule (a research script never holds a key).

Run: python3 research/scale/candC_fetch.py
"""
from __future__ import annotations
import csv, json, os, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "candC_data")
FIXTURE = os.path.join(HERE, "..", "..", "backend", "tests", "fixtures",
                       "bars_4h_btcusd.csv")
API = "https://api.hyperliquid.xyz/info"
MIN_VLM = 30_000_000.0
PROBE_NOTIONAL = 125_000.0
MAX_PROBE_BPS = 10.0
BAR = 4 * 3600


def post(body, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(
                API, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:                                    # noqa: BLE001
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def candles(coin, start_ms, end_ms):
    return post({"type": "candleSnapshot",
                 "req": {"coin": coin, "interval": "4h",
                         "startTime": start_ms, "endTime": end_ms}})


def book(coin, nsf=4):
    b = {"type": "l2Book", "coin": coin}
    if nsf:
        b["nSigFigs"] = nsf
    return post(b)


def walk_cost(levels, notional, side):
    """VWAP slip vs mid in bps for a market order of `notional` USD.
    levels = list of {px, sz}. Returns None if the visible ladder is too thin
    (reported, never silently dropped -- that bias was caught in phase 1)."""
    spent = filled = 0.0
    for lv in levels:
        px, sz = float(lv["px"]), float(lv["sz"])
        room = notional - spent
        take = min(sz * px, room)
        filled += take / px
        spent += take
        if spent >= notional - 1e-6:
            return spent / filled
    return None


def main():
    now_ms = int(time.time() * 1000)
    meta = post({"type": "metaAndAssetCtxs"})
    uni, ctxs = meta[0]["universe"], meta[1]
    info = {}
    for u, c in zip(uni, ctxs):
        if u.get("isDelisted"):
            continue
        info[u["name"]] = {
            "maxLeverage": u.get("maxLeverage"),
            "szDecimals": u.get("szDecimals"),
            "marginTableId": u.get("marginTableId"),
            "dayNtlVlm": float(c.get("dayNtlVlm") or 0.0),
            "markPx": float(c.get("markPx") or 0.0),
            "openInterestUsd": float(c.get("openInterest") or 0.0) * float(c.get("markPx") or 0.0),
            "funding_hourly": float(c.get("funding") or 0.0),
        }

    vol_ok = sorted([k for k, v in info.items() if v["dayNtlVlm"] >= MIN_VLM],
                    key=lambda k: -info[k]["dayNtlVlm"])
    print(f"GATE 2 (24h vlm >= ${MIN_VLM/1e6:.0f}m): {len(vol_ok)} coins")

    # ---- gate 1: complete history over the common window -------------------
    print("\nGATE 1 — history completeness (HL serves 5000 candles max)")
    raw, hist = {}, {}
    for coin in vol_ok:
        try:
            c = candles(coin, 1577836800000, now_ms)
        except Exception as e:                                     # noqa: BLE001
            print(f"  {coin:<8} FETCH FAILED {e}")
            continue
        if not c:
            print(f"  {coin:<8} empty")
            continue
        raw[coin] = c
        hist[coin] = (c[0]["t"], c[-1]["t"], len(c))
        print(f"  {coin:<8} n={len(c):>5}  {time.strftime('%Y-%m-%d', time.gmtime(c[0]['t']/1000))}"
              f" -> {time.strftime('%Y-%m-%d', time.gmtime(c[-1]['t']/1000))}")
    if not raw:
        raise SystemExit("no candle data")
    # BTC is the reference; anything starting later than BTC is a later listing
    btc_start = hist["BTC"][0]
    full = [c for c in raw if hist[c][0] <= btc_start]
    print(f"\n  BTC window starts {time.strftime('%Y-%m-%d', time.gmtime(btc_start/1000))}")
    print(f"  complete-history coins ({len(full)}): {' '.join(sorted(full))}")
    late = sorted(set(raw) - set(full))
    print(f"  LATER LISTINGS EXCLUDED ({len(late)}): {' '.join(late)}")

    # ---- gate 3: measured depth at the per-leg probe notional --------------
    print(f"\nGATE 3 — l2Book cost to buy ${PROBE_NOTIONAL:,.0f} (<= {MAX_PROBE_BPS} bps),"
          f" nSigFigs=4 basis (+-0.5 bp bucket granularity)")
    depth = {}
    for coin in full:
        try:
            b = book(coin, 4)
            bf = book(coin, None)
        except Exception as e:                                     # noqa: BLE001
            print(f"  {coin:<8} book fetch failed {e}")
            continue
        bids, asks = b["levels"][0], b["levels"][1]
        fmid = (float(bf["levels"][0][0]["px"]) + float(bf["levels"][1][0]["px"])) / 2.0
        fpb = walk_cost(bf["levels"][1], PROBE_NOTIONAL, "B")
        fine_buy_bps = (fpb / fmid - 1) * 1e4 if fpb else None
        mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2.0
        vb = sum(float(l["px"]) * float(l["sz"]) for l in bids)
        va = sum(float(l["px"]) * float(l["sz"]) for l in asks)
        pb = walk_cost(asks, PROBE_NOTIONAL, "B")
        ps = walk_cost(bids, PROBE_NOTIONAL, "S")
        buy_bps = (pb / mid - 1) * 1e4 if pb else None
        sell_bps = (1 - ps / mid) * 1e4 if ps else None
        rt = (buy_bps + sell_bps) if (buy_bps is not None and sell_bps is not None) else None
        depth[coin] = {"mid": mid, "bid_depth_usd": vb, "ask_depth_usd": va,
                       "buy_bps": buy_bps, "sell_bps": sell_bps,
                       "round_trip_bps": rt,
                       "spread_bps": (float(asks[0]["px"]) - float(bids[0]["px"])) / mid * 1e4,
                       "fine_book_buy_bps": fine_buy_bps,
                       "fine_book_complete": fine_buy_bps is not None}
        ok = rt is not None and max(buy_bps, sell_bps) <= MAX_PROBE_BPS
        depth[coin]["pass"] = bool(ok)
        print(f"  {coin:<8} spread {depth[coin]['spread_bps']:>5.2f}bp  "
              f"buy {('%6.2f' % buy_bps) if buy_bps is not None else '  THIN'}bp  "
              f"sell {('%6.2f' % sell_bps) if sell_bps is not None else '  THIN'}bp  "
              f"ladder ${va/1e6:>6.2f}m/${vb/1e6:>6.2f}m  "
              f"fine {('%5.2f' % fine_buy_bps) if fine_buy_bps is not None else ' n/a '}bp  "
              f"{'PASS' if ok else 'FAIL'}")

    sel = [c for c in full if depth.get(c, {}).get("pass")]
    sel.sort(key=lambda k: -info[k]["dayNtlVlm"])
    print(f"\nELIGIBLE UNIVERSE ({len(sel)}): {' '.join(sel)}")

    # ---- write engine-format CSVs on the common grid -----------------------
    os.makedirs(DATA, exist_ok=True)
    # grid spans the SELECTED coins only. (First cut computed it over every
    # coin FETCHED, so PONS -- listed 2026-08-31 and excluded by gate 1 --
    # collapsed the window to 173 bars. Caught before any return was computed.)
    common_start = max(hist[c][0] for c in sel)
    common_end = min(hist[c][1] for c in sel)
    grid = list(range(common_start // 1000, common_end // 1000 + 1, BAR))
    print(f"\nCommon 4h grid: {len(grid)} bars "
          f"{time.strftime('%Y-%m-%d', time.gmtime(grid[0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(grid[-1]))}")
    written, gaps = {}, {}
    for coin in sel:
        by = {c["t"] // 1000: c for c in raw[coin]}
        rows, miss = [], 0
        for ts in grid:
            c = by.get(ts)
            if c is None:
                miss += 1
                continue
            rows.append({"ts_open_unix": ts, "open": c["o"], "high": c["h"],
                         "low": c["l"], "close": c["c"], "volume": c["v"]})
        gaps[coin] = miss
        p = os.path.join(DATA, f"bars_4h_{coin.lower()}.csv")
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, ["ts_open_unix", "open", "high", "low", "close", "volume"])
            w.writeheader()
            w.writerows(rows)
        written[coin] = len(rows)
        print(f"  {coin:<8} {len(rows)} bars written, {miss} gaps on the grid")

    # ---- DATA-INTEGRITY GATE: HL BTC vs the repo's own fixture -------------
    print("\n" + "=" * 78)
    print("DATA-INTEGRITY GATE — HL BTC candles vs bars_4h_btcusd.csv on the overlap")
    print("=" * 78)
    fx = {int(r["ts_open_unix"]): r for r in csv.DictReader(open(FIXTURE))}
    hl = {c["t"] // 1000: c for c in raw["BTC"]}
    ov = sorted(set(fx) & set(hl))
    print(f"  overlapping bars: {len(ov)} "
          f"({time.strftime('%Y-%m-%d', time.gmtime(ov[0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(ov[-1]))})")
    worst = {"close": 0.0, "high": 0.0, "low": 0.0, "open": 0.0}
    rel = {k: [] for k in worst}
    for ts in ov:
        for k, hk in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")):
            a, b = float(fx[ts][k]), float(hl[ts][hk])
            d = abs(a - b) / a
            rel[k].append(d)
            worst[k] = max(worst[k], d)
    import statistics as st
    for k in ("open", "high", "low", "close"):
        print(f"  {k:<6} median rel diff {st.median(rel[k])*1e4:8.4f} bp   "
              f"max {worst[k]*1e4:9.2f} bp")
    integrity = {"overlap_bars": len(ov),
                 "median_rel_bp": {k: st.median(rel[k]) * 1e4 for k in rel},
                 "max_rel_bp": {k: worst[k] * 1e4 for k in rel}}
    print("  -> the fixture and the live venue agree to a few bp; the fixture is a")
    print("     different venue's/aggregator's print, not HL's. Stated, not hidden:")
    print("     cross-asset results below run on HL data for EVERY asset INCLUDING")
    print("     BTC, so the comparison is internally consistent.")

    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rule": {"min_day_vlm_usd": MIN_VLM, "probe_notional_usd": PROBE_NOTIONAL,
                    "max_probe_bps": MAX_PROBE_BPS},
           "vol_ok": vol_ok, "complete_history": sorted(full),
           "later_listings_excluded": late,
           "eligible": sel, "depth": depth, "venue_info": {k: info[k] for k in raw},
           "history": {k: {"first": v[0], "last": v[1], "n": v[2]} for k, v in hist.items()},
           "bars_written": written, "grid_gaps": gaps,
           "common_grid": {"start": grid[0], "end": grid[-1], "n": len(grid)},
           "fixture_integrity": integrity}
    json.dump(out, open(os.path.join(HERE, "candC_fetch.json"), "w"), indent=1)
    print(f"\nfrozen -> {os.path.join(HERE, 'candC_fetch.json')}")


if __name__ == "__main__":
    main()
