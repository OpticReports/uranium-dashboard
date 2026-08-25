"""Fetch Bitstamp BTC/USD 4h bars 2020-06-01 -> now, gap-checked, to CSV.

Data provenance for RESEARCH_WINRATE.md: the study ran on this exact fetch
(13,612 bars, 2020-06-01 -> 2026-08-17, zero gaps). Re-run this script to
regenerate the dataset, then pass the CSV to research_winrate.py /
research_winrate_null.py as argv[1] or BARS_CSV.

Usage: python3 fetch_bars.py [out.csv]
"""
import csv, json, time, urllib.request, sys

import sys

STEP = 14400
START = 1590969600  # 2020-06-01
# output path: first argv, or BARS_CSV env, or ./bars_4h_btcusd_ext.csv
OUT = (sys.argv[1] if len(sys.argv) > 1
       else __import__("os").environ.get("BARS_CSV", "bars_4h_btcusd_ext.csv"))

rows = {}
cur = START
while True:
    url = (f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step={STEP}"
           f"&limit=1000&start={cur}")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)["data"]["ohlc"]
            break
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    if not data:
        break
    for d in data:
        ts = int(d["timestamp"])
        rows[ts] = (d["open"], d["high"], d["low"], d["close"], d["volume"])
    last = int(data[-1]["timestamp"])
    if last <= cur and len(data) < 1000:
        break
    if last == cur:
        break
    cur = last + STEP
    if len(data) < 1000:
        break
    time.sleep(0.35)

ts_sorted = sorted(rows)
gaps = [(a, b) for a, b in zip(ts_sorted, ts_sorted[1:]) if b - a != STEP]
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts_open_unix", "open", "high", "low", "close", "volume"])
    for ts in ts_sorted:
        w.writerow([ts, *rows[ts]])
print(f"bars={len(ts_sorted)} first={ts_sorted[0]} last={ts_sorted[-1]} gaps={len(gaps)}")
for a, b in gaps[:10]:
    print("  gap:", a, "->", b, f"({(b-a)//STEP - 1} missing)")
