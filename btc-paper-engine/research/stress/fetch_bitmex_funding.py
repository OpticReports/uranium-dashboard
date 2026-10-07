"""BitMEX funding history (8-hourly), the only source reachable from this
environment that covers 2018 / 2020 / 2022. XBTUSD from 2016-05, ETHUSD perp
from 2018-08-02. Writes data/funding_bitmex_<sym>.csv: ts_ms, rate_8h.
Usage: python3 fetch_bitmex_funding.py XBTUSD 2016-05-01 ; ... ETHUSD 2018-08-01"""
import csv, json, os, sys, time, urllib.request, datetime as dt
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)
sym = sys.argv[1]; start = sys.argv[2]
rows, cur = {}, start
while True:
    url = f"https://www.bitmex.com/api/v1/funding?symbol={sym}&count=500&startTime={cur}"
    for a in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r: data = json.load(r)
            break
        except Exception as e:
            print("retry", a, e, flush=True); time.sleep(5 * (a + 1))
    else:
        raise SystemExit("failed")
    if not data: break
    for d in data:
        t = dt.datetime.strptime(d["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc)
        rows[int(t.timestamp() * 1000)] = float(d["fundingRate"])
    last = max(rows); nxt = dt.datetime.utcfromtimestamp(last / 1000) + dt.timedelta(seconds=1)
    if len(data) < 500: break
    cur = nxt.strftime("%Y-%m-%dT%H:%M:%S.000Z"); time.sleep(2.2)
with open(os.path.join(OUT, f"funding_bitmex_{sym}.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ts_ms", "rate_8h"])
    for t in sorted(rows): w.writerow([t, rows[t]])
ts = sorted(rows)
print(sym, len(ts), dt.datetime.utcfromtimestamp(ts[0]/1000), dt.datetime.utcfromtimestamp(ts[-1]/1000))
