"""CANDIDATE C, step 5: FUNDING PER ASSET. The cost this candidate adds that
BTC-only does not have.

Phase 1 measured BTC perp funding over this book's own holds at +0.0202%/yr of
notional — a small CREDIT, because the book is ~half short. Altcoin perp
funding is structurally hotter and more persistently positive (longs pay), so
a 6-asset book pays funding BTC-only does not. This prices it from HL's own
hourly funding history over the ACTUAL entry/exit timestamps and sides the
engine produced for each asset.

Sign convention: LONG pays when funding > 0 (so signed = -1 x rate x hours),
SHORT receives. Reported per round trip in bp of entry notional and as an
annualised fraction of notional, so it is directly comparable to the 8.64 bp
round-trip fee.

Run: python3 research/scale/candC_funding.py
"""
from __future__ import annotations
import bisect, json, os, time, urllib.request

import numpy as np
from candC_lib import (FEE_TAKER_RT, HERE, asset_path, load_bars, replay_mtm)

API = "https://api.hyperliquid.xyz/info"
FETCH = json.load(open(os.path.join(HERE, "candC_fetch.json")))
UNIVERSE = FETCH["eligible"]
HOUR = 3600


def post(body, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(
                API, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception:                                          # noqa: BLE001
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def funding_series(coin, start_ms, end_ms):
    """HL returns at most 500 stamps per call -> page forward."""
    out, cur = [], start_ms
    while cur < end_ms:
        chunk = post({"type": "fundingHistory", "coin": coin,
                      "startTime": cur, "endTime": end_ms})
        if not chunk:
            break
        out.extend(chunk)
        nxt = chunk[-1]["time"] + 1
        if nxt <= cur:
            break
        cur = nxt
        if len(chunk) < 2:
            break
    seen, ded = set(), []
    for r in sorted(out, key=lambda r: r["time"]):
        if r["time"] not in seen:
            seen.add(r["time"])
            ded.append((r["time"] // 1000, float(r["fundingRate"])))
    return ded


def main():
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe": UNIVERSE, "assets": {}}
    bars0 = load_bars(asset_path("BTC"))
    t0, t1 = bars0[0].ts * 1000, (bars0[-1].ts + 4 * 3600) * 1000

    print("=" * 104)
    print("HL HOURLY FUNDING, fetched per asset over the study window")
    print("=" * 104)
    F = {}
    for coin in UNIVERSE:
        ser = funding_series(coin, t0, t1)
        ts = np.array([x[0] for x in ser])
        rt = np.array([x[1] for x in ser])
        # cumulative sum so a hold's total is two lookups, not a scan
        cum = np.concatenate([[0.0], np.cumsum(rt)])
        F[coin] = (ts, rt, cum)
        ann = rt.mean() * 24 * 365 * 100
        r30 = np.array([rt[max(0, i-720):i+1].mean() * 24 * 365 * 100
                        for i in range(0, len(rt), 24)])
        OUT["assets"][coin] = {
            "n_stamps": len(ts),
            "mean_annualised_pct": float(ann),
            "median_annualised_pct": float(np.median(rt) * 24 * 365 * 100),
            "frac_positive_stamps": float((rt > 0).mean()),
            "rolling30d_min_pct": float(r30.min()), "rolling30d_p10_pct": float(np.percentile(r30, 10)),
            "rolling30d_median_pct": float(np.median(r30)),
            "rolling30d_p90_pct": float(np.percentile(r30, 90)),
            "rolling30d_max_pct": float(r30.max())}
        d = OUT["assets"][coin]
        print(f"  {coin:<6} {len(ts):>6} stamps  mean {ann:>+7.2f}%/yr  "
              f"pos {d['frac_positive_stamps']*100:>5.1f}%  rolling-30d "
              f"[{d['rolling30d_min_pct']:>+7.1f} .. {d['rolling30d_median_pct']:>+6.1f} "
              f".. {d['rolling30d_max_pct']:>+7.1f}]%/yr")

    print()
    print("=" * 104)
    print("SIGNED FUNDING OVER THE ENGINE'S OWN TRADES (long pays, short receives)")
    print("=" * 104)
    print(f"  {'asset':<6} {'leg':<4} {'trades':>7} {'short%':>7} {'held hrs':>9} "
          f"{'bp/round trip':>14} {'%/yr of notional':>17} {'vs 8.64bp fee':>14}")
    TOT = {}
    for coin in UNIVERSE:
        ts, rt, cum = F[coin]
        mtm, pos, trades = replay_mtm(load_bars(asset_path(coin)), FEE_TAKER_RT)
        for leg in ("S3", "S4"):
            tr = trades[leg]
            if not tr:
                continue
            bps, hrs, shorts = [], [], 0
            for t in tr:
                i = bisect.bisect_right(ts, t.entry_ts)
                j = bisect.bisect_right(ts, t.exit_ts)
                tot = cum[j] - cum[i]
                sgn = -1.0 if t.side == "L" else +1.0
                bps.append(sgn * tot * 1e4)
                hrs.append(j - i)
                shorts += (t.side == "S")
            bps = np.array(bps, float)
            hrs = np.array(hrs, float)
            years = (tr[-1].exit_ts - tr[0].entry_ts) / (365.25 * 86400)
            pct_yr = bps.sum() / 1e4 * 100 / years if years > 0 else 0.0
            TOT[(coin, leg)] = {
                "n": len(tr), "short_frac": shorts / len(tr),
                "mean_held_hours": float(hrs.mean()),
                "mean_bp_round_trip": float(bps.mean()),
                "median_bp_round_trip": float(np.median(bps)),
                "worst_bp_round_trip": float(bps.min()),
                "total_pct_per_yr_of_notional": float(pct_yr),
                "vs_fee_ratio": float(-bps.mean() / FEE_TAKER_RT)}
            d = TOT[(coin, leg)]
            print(f"  {coin:<6} {leg:<4} {len(tr):>7} {shorts/len(tr)*100:>6.1f}% "
                  f"{hrs.mean():>9.1f} {bps.mean():>+13.2f} {pct_yr:>+16.3f} "
                  f"{-bps.mean()/FEE_TAKER_RT:>13.1%}")
    OUT["per_leg"] = {f"{c}/{l}": v for (c, l), v in TOT.items()}

    print()
    print("=" * 104)
    print("PORTFOLIO FUNDING — 75/25 within asset, equal across assets")
    print("=" * 104)
    def port_bp(coins):
        """Annualised funding drag as a % of TOTAL gross notional."""
        tot = 0.0
        for c in coins:
            for leg, w in (("S3", 0.75), ("S4", 0.25)):
                d = TOT.get((c, leg))
                if d:
                    tot += (w / len(coins)) * d["total_pct_per_yr_of_notional"]
        return tot
    btc_only = port_bp(["BTC"])
    six = port_bp(UNIVERSE)
    print(f"  BTC only  : {btc_only:+.4f}%/yr of gross notional")
    print(f"  6 assets  : {six:+.4f}%/yr of gross notional")
    print(f"  DELTA the candidate ADDS: {six - btc_only:+.4f}%/yr of gross notional")
    for tgt in (100_000, 1_000_000):
        print(f"    at ${tgt:,} gross: BTC ${btc_only/100*tgt:+,.0f}/yr vs "
              f"6-asset ${six/100*tgt:+,.0f}/yr  (delta "
              f"${(six-btc_only)/100*tgt:+,.0f}/yr)")
    # fee load for scale
    fee_yr = {}
    for c in UNIVERSE:
        for leg, w in (("S3", 0.75), ("S4", 0.25)):
            d = TOT.get((c, leg))
            if d:
                years = 4790 / 2190
                fee_yr[(c, leg)] = d["n"] / years * FEE_TAKER_RT / 1e4 * 100 * w / len(UNIVERSE)
    print(f"  For scale, the FEE load on the same 6-asset book: "
          f"{sum(fee_yr.values()):.3f}%/yr of gross notional at {FEE_TAKER_RT} bp/round trip")
    OUT["portfolio"] = {"btc_only_pct_yr": btc_only, "six_asset_pct_yr": six,
                        "delta_pct_yr": six - btc_only,
                        "fee_load_pct_yr_6asset": float(sum(fee_yr.values()))}

    print()
    print("  HONESTY: this prices funding over the holds that ACTUALLY happened in")
    print("  the replay, at the rates that ACTUALLY printed. It is not in the Kelly")
    print("  numbers in candC_portfolio.json — those are gross of funding. The line")
    print("  above is what to subtract, and it is stated separately rather than")
    print("  folded in, because folding it in would change the registered objective.")

    json.dump(OUT, open(os.path.join(HERE, "candC_funding.json"), "w"), indent=1,
              default=str)
    print("\nfrozen -> candC_funding.json")


if __name__ == "__main__":
    main()
