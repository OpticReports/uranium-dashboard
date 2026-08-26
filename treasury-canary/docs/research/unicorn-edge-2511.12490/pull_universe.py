"""Bulk pull: current S&P 500 members, 2004-2025, dividend-adjusted (returns)
+ non-split-adjusted (true price signal). Throttled; per-symbol CSV cache;
idempotent (skips complete files on rerun)."""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor
import httpx
import pandas as pd

SC = os.path.dirname(os.path.abspath(__file__))
K = os.environ["FMP_API_KEY"]
START = "2004-01-02"
END = "2024-12-31"

def fetch_paged(path, symbol):
    rows, to = [], None
    for _ in range(8):
        params = {"symbol": symbol, "from": START, "to": to or END, "apikey": K}
        for attempt in range(4):
            try:
                r = httpx.get(f"https://financialmodelingprep.com/stable/{path}",
                              params=params, timeout=60)
                r.raise_for_status()
                chunk = r.json()
                break
            except Exception:
                time.sleep(2 ** attempt)
        else:
            return None                      # hard failure after retries
        if not isinstance(chunk, list) or not chunk:
            break
        rows.extend(chunk)
        earliest = min(c["date"] for c in chunk)
        if earliest <= START or len(chunk) < 100:
            break
        to = (pd.Timestamp(earliest) - pd.Timedelta(days=1)).date().isoformat()
    if not rows:
        return None
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    keep = [c for c in ("date", "open", "close", "adjClose", "volume") if c in df.columns]
    return df[keep]

def pull_symbol(sym):
    out = []
    for path, sub in (("historical-price-eod/dividend-adjusted", "prices_div"),
                      ("historical-price-eod/non-split-adjusted", "prices_raw")):
        f = f"{SC}/{sub}/{sym.replace('.', '-')}.csv"
        if os.path.exists(f) and os.path.getsize(f) > 1000:
            out.append("cached")
            continue
        df = fetch_paged(path, sym)
        if df is None or df.empty:
            out.append("FAIL")
            continue
        df.to_csv(f, index=False)
        out.append(str(len(df)))
        time.sleep(0.15)                     # ~global throttle w/ 6 workers
    return sym, out

r = httpx.get("https://financialmodelingprep.com/stable/sp500-constituent",
              params={"apikey": K}, timeout=60)
r.raise_for_status()
members = sorted({row["symbol"] for row in r.json()})
print(f"{len(members)} constituents", flush=True)

fails = []
with ThreadPoolExecutor(max_workers=6) as pool:
    for i, (sym, res) in enumerate(pool.map(pull_symbol, members)):
        if "FAIL" in res:
            fails.append(sym)
        if i % 50 == 0:
            print(f"{i}/{len(members)} {sym} {res}", flush=True)
print("DONE. failures:", fails, flush=True)

# constituent CHANGE history for the PIT attempt (single call)
r = httpx.get("https://financialmodelingprep.com/stable/historical-sp500-constituent",
              params={"apikey": K}, timeout=60)
if r.status_code == 200 and isinstance(r.json(), list) and r.json():
    pd.DataFrame(r.json()).to_csv(f"{SC}/constituent_changes.csv", index=False)
    print("constituent changes:", len(r.json()), "earliest:",
          min(x.get("date", "?") for x in r.json()), flush=True)
else:
    print("constituent-change endpoint unavailable:", r.status_code, flush=True)
