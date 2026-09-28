"""Write Hyperliquid BTC PERP 4h bars in the fixture's own schema, so the
engine can be replayed on the instrument it actually trades.

The engine's bars are Bitstamp/Kraken SPOT (app/sources/bitstamp.py) while the
account trades the HL perp.  candD_perp_space.py measures what that mismatch
costs.  This file exists to test the alternative: signal on the perp itself.

Run: python3 research/scale/candD_perp_bars.py
"""
from __future__ import annotations
import csv, json, os, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://api.hyperliquid.xyz/info"
OUT = os.path.join(HERE, "candD_bars_4h_btcperp.csv")


def post(payload):
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> None:
    out: dict[int, dict] = {}
    end = int(time.time() * 1000)
    H4 = 4 * 3600 * 1000
    for page in range(12):
        start = end - 4900 * H4
        rows = post({"type": "candleSnapshot",
                     "req": {"coin": "BTC", "interval": "4h",
                             "startTime": start, "endTime": end}})
        if not rows:
            break
        new = 0
        lo = min(int(c["t"]) for c in rows)
        for c in rows:
            ts = int(c["t"]) // 1000
            if ts not in out:
                new += 1
            out[ts] = {"ts_open_unix": ts, "open": float(c["o"]),
                       "high": float(c["h"]), "low": float(c["l"]),
                       "close": float(c["c"]), "volume": float(c["v"])}
        print(f"page {page}: {len(rows)} rows, {new} new")
        if new == 0:
            break
        end = lo - 1

    rows = [out[k] for k in sorted(out)]
    # integrity: strict 4h spacing, no duplicates, no zero/NaN prices
    gaps = sum(1 for i in range(1, len(rows))
               if rows[i]["ts_open_unix"] - rows[i-1]["ts_open_unix"] != 14400)
    bad = sum(1 for r in rows if not (r["low"] <= r["open"] <= r["high"]
                                      and r["low"] <= r["close"] <= r["high"]
                                      and r["low"] > 0))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts_open_unix", "open", "high",
                                          "low", "close", "volume"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} perp bars -> {OUT}")
    print(f"  span {time.strftime('%Y-%m-%d', time.gmtime(rows[0]['ts_open_unix']))}"
          f" -> {time.strftime('%Y-%m-%d', time.gmtime(rows[-1]['ts_open_unix']))}")
    print(f"  INTEGRITY non-4h gaps {gaps}, OHLC violations {bad}")


if __name__ == "__main__":
    main()
