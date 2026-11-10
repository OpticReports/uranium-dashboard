"""Real BTC perp funding history from the venues Casey named:
Hyperliquid (hourly) + Coinbase INTX BTC-PERP (hourly). Gap-checked CSVs.

Usage: python3 fetch_funding.py <out_dir>   (default: cwd)
Writes funding_hyperliquid_btc.csv + funding_intx_btcperp.csv there.
NOTE (audit 2026-08-26): HL `fundingHistory.time` is the APPLICATION time
of a rate computed from the preceding hour's premium — a stamp at T is
settled/known at T, which is what research_carry.py's accrual assumes."""
import csv, json, time, urllib.request, sys, datetime as dt

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else "."

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if a == 4: raise
            time.sleep(2 ** a)

def get(url):
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception:
            if a == 4: raise
            time.sleep(2 ** a)

# ---- Hyperliquid: hourly funding, paginate forward ----
hl = {}
cur = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
end = int(time.time() * 1000)
while cur < end:
    data = post("https://api.hyperliquid.xyz/info",
                {"type": "fundingHistory", "coin": "BTC",
                 "startTime": cur, "endTime": min(cur + 45*86400*1000, end)})
    for d in (data or []):
        hl[int(d["time"])] = float(d["fundingRate"])
    if data:
        cur = max(int(d["time"]) for d in data) + 1
    else:
        cur += 45*86400*1000
    time.sleep(0.3)
hts = sorted(hl)
with open(f"{SCRATCH}/funding_hyperliquid_btc.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ts_ms", "funding_rate_1h"])
    for t in hts: w.writerow([t, hl[t]])
gaps = sum(1 for a, b in zip(hts, hts[1:]) if b - a > 3600_000 + 60_000)
ann = sum(hl.values()) / len(hl) * 24 * 365 * 100
print(f"Hyperliquid: {len(hl)} hourly stamps "
      f"{dt.datetime.utcfromtimestamp(hts[0]/1000).date()}.."
      f"{dt.datetime.utcfromtimestamp(hts[-1]/1000).date()} "
      f"gaps(>1h)={gaps} mean_annualized={ann:.1f}%")

# ---- Coinbase INTX: hourly funding, paginate by offset ----
cb, off = {}, 0
while True:
    d = get(f"https://api.international.coinbase.com/api/v1/instruments/"
            f"BTC-PERP/funding?result_limit=100&result_offset={off}")
    res = d.get("results") or []
    if not res: break
    for r in res:
        ts = r["event_time"]
        cb[ts] = float(r["funding_rate"])
    off += len(res)
    if len(res) < 100: break
    time.sleep(0.15)
cts = sorted(cb)
with open(f"{SCRATCH}/funding_intx_btcperp.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ts_iso", "funding_rate_1h"])
    for t in cts: w.writerow([t, cb[t]])
annc = sum(cb.values()) / max(1, len(cb)) * 24 * 365 * 100
print(f"INTX: {len(cb)} hourly stamps {cts[0][:10]}..{cts[-1][:10]} "
      f"mean_annualized={annc:.1f}%")
