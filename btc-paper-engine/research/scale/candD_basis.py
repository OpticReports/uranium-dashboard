"""CANDIDATE D, measurement 1: THE PERP/SPOT BASIS.

mirror.py:4486 states the mechanism in its own words: "The engine prices
signals off SPOT but we trade a FUTURE; at a positive basis short limits are
marketable and post-only is rejected."  The engine's bars are Bitstamp/Kraken
SPOT (app/sources/bitstamp.py); the venue is the Hyperliquid BTC PERP.

Nothing in phase 1 measured that basis.  It is the whole mechanism behind the
4-of-4 Alo rejections, and its SIZE decides whether FIX 1 is a re-pricing
(cheap) or a redesign.

Fetches HL BTC perp 4h candles and aligns them to the spot fixture bar-for-bar
on ts_open_unix.  No credentials: public /info endpoint.

Run: python3 research/scale/candD_basis.py
"""
from __future__ import annotations
import csv, json, os, time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
URL = "https://api.hyperliquid.xyz/info"
OUT_CSV = os.path.join(HERE, "candD_perp_4h.csv")
OUT_JSON = os.path.join(HERE, "candD_basis.json")


def post(payload: dict) -> object:
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def fetch_perp_4h() -> dict[int, dict]:
    """Paginate candleSnapshot backwards.  HL caps a response at 5000 candles."""
    out: dict[int, dict] = {}
    end = int(time.time() * 1000)
    H4 = 4 * 3600 * 1000
    for page in range(12):
        start = end - 4900 * H4
        try:
            rows = post({"type": "candleSnapshot",
                         "req": {"coin": "BTC", "interval": "4h",
                                 "startTime": start, "endTime": end}})
        except Exception as exc:            # noqa: BLE001
            print(f"  page {page}: FAILED {exc}")
            break
        if not isinstance(rows, list) or not rows:
            print(f"  page {page}: empty, stopping")
            break
        new = 0
        lo = min(int(c["t"]) for c in rows)
        for c in rows:
            ts = int(c["t"]) // 1000
            if ts not in out:
                new += 1
            out[ts] = {"open": float(c["o"]), "high": float(c["h"]),
                       "low": float(c["l"]), "close": float(c["c"]),
                       "volume": float(c["v"])}
        print(f"  page {page}: {len(rows)} rows, {new} new, "
              f"earliest {time.strftime('%Y-%m-%d', time.gmtime(lo/1000))}")
        if new == 0:
            break
        end = lo - 1
    return out


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def main() -> None:
    print("Fetching Hyperliquid BTC perp 4h candles...")
    perp = fetch_perp_4h()
    print(f"perp candles: {len(perp)}")

    spot: dict[int, dict] = {}
    with open(BARS) as f:
        for row in csv.DictReader(f):
            spot[int(row["ts_open_unix"])] = {
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"])}
    print(f"spot bars   : {len(spot)}")

    common = sorted(set(spot) & set(perp))
    print(f"overlap     : {len(common)} bars "
          f"{time.strftime('%Y-%m-%d', time.gmtime(common[0]))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(common[-1]))}" if common
          else "overlap: NONE")
    if not common:
        raise SystemExit("no overlap - cannot measure basis")

    rows = []
    for ts in common:
        s, p = spot[ts], perp[ts]
        # basis in bps of spot close, measured at the SAME bar close: this is
        # exactly the quantity mirror.py's limit price is wrong by.
        b_close = (p["close"] / s["close"] - 1.0) * 1e4
        b_open = (p["open"] / s["open"] - 1.0) * 1e4
        rows.append({"ts": ts, "spot_close": s["close"], "perp_close": p["close"],
                     "basis_close_bps": b_close, "basis_open_bps": b_open,
                     "perp_high": p["high"], "perp_low": p["low"],
                     "spot_high": s["high"], "spot_low": s["low"]})

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    b = [r["basis_close_bps"] for r in rows]
    by_year: dict[str, list[float]] = {}
    for r in rows:
        by_year.setdefault(time.strftime("%Y", time.gmtime(r["ts"])), []
                           ).append(r["basis_close_bps"])

    res = {
        "n_bars": len(rows),
        "span": [time.strftime("%Y-%m-%d", time.gmtime(rows[0]["ts"])),
                 time.strftime("%Y-%m-%d", time.gmtime(rows[-1]["ts"]))],
        "basis_close_bps": {
            "mean": sum(b) / len(b), "median": pct(b, .5),
            "p1": pct(b, .01), "p10": pct(b, .10), "p25": pct(b, .25),
            "p75": pct(b, .75), "p90": pct(b, .90), "p99": pct(b, .99),
            "min": min(b), "max": max(b),
            "frac_positive": sum(1 for x in b if x > 0) / len(b),
            "frac_abs_gt_144": sum(1 for x in b if abs(x) > 1.44) / len(b),
            "frac_abs_gt_288": sum(1 for x in b if abs(x) > 2.88) / len(b),
        },
        "by_year_median_bps": {k: pct(v, .5) for k, v in sorted(by_year.items())},
        "by_year_mean_bps": {k: sum(v) / len(v) for k, v in sorted(by_year.items())},
        "by_year_frac_positive": {
            k: sum(1 for x in v if x > 0) / len(v) for k, v in sorted(by_year.items())},
    }
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
