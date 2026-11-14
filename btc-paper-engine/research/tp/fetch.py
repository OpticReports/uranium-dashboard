"""Fetch Bitstamp 4h OHLCV for one pair, gap-checked, to a gzipped CSV.

Data provenance for RESEARCH_TP.md. Same API and paging as
backend/scripts/fetch_bars.py; only the pair and start differ. The last,
still-forming bar is dropped (a bar is kept only if it closed before the
fetch started). Gaps are reported, never filled.

usage: python3 fetch.py <pair> <start_unix> <out.csv.gz>
"""
import csv
import gzip
import hashlib
import json
import sys
import time
import urllib.request

STEP = 14400
pair, start, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
fetch_t0 = int(time.time())
rows, cur = {}, start
while cur < fetch_t0:
    url = (f"https://www.bitstamp.net/api/v2/ohlc/{pair}/?step={STEP}"
           f"&limit=1000&start={cur}")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)["data"]["ohlc"]
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    for d in data:
        ts = int(d["timestamp"])
        if ts + STEP <= fetch_t0:                     # closed bars only
            rows[ts] = (d["open"], d["high"], d["low"], d["close"], d["volume"])
    # Fixed stride, not "last + STEP": a window that starts before the pair
    # was listed comes back short or empty, and stopping there loses the
    # whole history (ltcusd returned 2 bars that way).
    cur += 1000 * STEP
    if cur >= fetch_t0:
        break
    time.sleep(0.35)

ts_sorted = sorted(rows)
gaps = [(a, b) for a, b in zip(ts_sorted, ts_sorted[1:]) if b - a != STEP]
with gzip.open(out, "wt", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts_open_unix", "open", "high", "low", "close", "volume"])
    for ts in ts_sorted:
        w.writerow([ts, *rows[ts]])
h = hashlib.sha256(gzip.open(out, "rb").read()).hexdigest()
print(f"{pair}: bars={len(ts_sorted)} first={time.strftime('%Y-%m-%d', time.gmtime(ts_sorted[0]))} "
      f"last={time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts_sorted[-1]))} gaps={len(gaps)} "
      f"missing={sum((b - a) // STEP - 1 for a, b in gaps)} sha256(csv)={h[:16]}")
for a, b in gaps[:5]:
    print("  gap:", time.strftime('%Y-%m-%d %H:%M', time.gmtime(a)), "->",
          time.strftime('%Y-%m-%d %H:%M', time.gmtime(b)), f"({(b - a) // STEP - 1} missing)")
