"""Funding history for the Sharpe study (PREREG.md, H3).

BitMEX XBTUSD 8-hourly funding 2016-05-14 -> now: the only series reachable
from here that spans the 2018 and 2022 bears (Binance/Bybit refuse this
location; OKX serves recent history only). Hyperliquid hourly BTC funding
2023-05 -> now via backend/scripts/fetch_funding.py, for the overlap check.

Usage: python3 fetch_funding.py      -> data/funding_bitmex_xbtusd.csv
                                        data/funding_hyperliquid_btc.csv
Convention (both venues): rate > 0 means longs pay shorts; a stamp at T is
the rate settled AT T."""
import calendar
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def get(url):
    for a in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:                       # noqa: BLE001
            if a == 5:
                raise
            print(f"  retry {a}: {e}", flush=True)
            time.sleep(2 ** (a + 1))


def bitmex():
    rows, start = [], 0
    while True:
        url = ("https://www.bitmex.com/api/v1/funding?symbol=XBTUSD"
               f"&count=500&start={start}&reverse=false")
        page = get(url)
        if not page:
            break
        for p in page:
            ts = calendar.timegm(time.strptime(p["timestamp"][:19],
                                               "%Y-%m-%dT%H:%M:%S"))
            rows.append((ts, float(p["fundingRate"])))
        start += len(page)
        if len(page) < 500:
            break
        time.sleep(2.5)                              # 30 req/min unauthenticated
    rows = sorted(set(rows))
    gaps = [(a, b) for (a, _), (b, _) in zip(rows, rows[1:]) if b - a != 8 * 3600]
    path = os.path.join(DATA, "funding_bitmex_xbtusd.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "funding_rate_8h"])
        w.writerows(rows)
    print(f"BitMEX: {len(rows)} stamps "
          f"{time.strftime('%Y-%m-%d', time.gmtime(rows[0][0]))}.."
          f"{time.strftime('%Y-%m-%d', time.gmtime(rows[-1][0]))}  "
          f"non-8h steps: {len(gaps)} {gaps[:5]}")


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    bitmex()
    subprocess.run([sys.executable, os.path.join(
        HERE, "..", "..", "backend", "scripts", "fetch_funding.py"), DATA],
        check=True)
