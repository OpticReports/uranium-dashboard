import os, time
from concurrent.futures import ThreadPoolExecutor
import httpx
import pandas as pd
SC = os.path.dirname(os.path.abspath(__file__))
K = os.environ["FMP_API_KEY"]
os.makedirs(f"{SC}/prices_full", exist_ok=True)
START, END = "2004-01-02", "2024-12-31"

def fetch(sym):
    f = f"{SC}/prices_full/{sym}.csv"
    if os.path.exists(f) and os.path.getsize(f) > 1000:
        return
    rows, to = [], None
    for _ in range(8):
        try:
            r = httpx.get("https://financialmodelingprep.com/stable/historical-price-eod/full",
                          params={"symbol": sym.replace('-', '.') if sym.count('-') > 1 else sym,
                                  "from": START, "to": to or END, "apikey": K}, timeout=60)
            chunk = r.json()
        except Exception:
            time.sleep(2); continue
        if not isinstance(chunk, list) or not chunk: break
        rows.extend(chunk)
        earliest = min(c["date"] for c in chunk)
        if earliest <= START or len(chunk) < 100: break
        to = (pd.Timestamp(earliest) - pd.Timedelta(days=1)).date().isoformat()
    if rows:
        df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
        df[[c for c in ("date", "open", "close") if c in df.columns]].to_csv(f, index=False)
    time.sleep(0.1)

import glob
syms = [os.path.basename(f)[:-4] for f in glob.glob(f"{SC}/prices_div/*.csv")]
with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(fetch, syms))
print("full pull done:", len(glob.glob(f"{SC}/prices_full/*.csv")))
