import os, time
import httpx
import pandas as pd
DATA = os.path.join(os.path.dirname(__file__), "data")
FMP = os.environ["FMP_API_KEY"]

def fmp_full(symbol, out, start="2002-01-01"):
    url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    rows = []
    to = None
    while True:
        params = {"symbol": symbol, "apikey": FMP, "from": start}
        if to: params["to"] = to
        r = httpx.get(url, params=params, timeout=60); r.raise_for_status()
        chunk = r.json()
        if not chunk: break
        rows.extend(chunk)
        earliest = min(c["date"] for c in chunk)
        if earliest <= start: break
        nxt = (pd.Timestamp(earliest) - pd.Timedelta(days=1)).date().isoformat()
        if to == nxt: break
        to = nxt
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df.to_csv(out, index=False)
    print(symbol, len(df), df["date"].min(), "->", df["date"].max(), list(df.columns))

fmp_full("TLT", f"{DATA}/TLT.csv")
fmp_full("^MOVE", f"{DATA}/MOVE.csv", start="2003-01-01")

for attempt in range(4):
    try:
        r = httpx.get("https://publicreporting.cftc.gov/resource/6dca-aqww.json",
                      params={"$where": "contract_market_name in('UST BOND','UST 10Y NOTE','ULTRA UST BOND','ULTRA UST 10Y')",
                              "$select": ("report_date_as_yyyy_mm_dd,contract_market_name,"
                                          "noncomm_positions_long_all,noncomm_positions_short_all,"
                                          "open_interest_all"),
                              "$limit": "50000"}, timeout=180)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        df.to_csv(f"{DATA}/legacy_cot.csv", index=False)
        print("legacy rows:", len(df), df["report_date_as_yyyy_mm_dd"].min(), "->",
              df["report_date_as_yyyy_mm_dd"].max())
        break
    except Exception as e:
        print("attempt", attempt, "failed:", e); time.sleep(2 ** (attempt + 1))
