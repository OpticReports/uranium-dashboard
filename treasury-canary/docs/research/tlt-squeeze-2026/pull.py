"""Data pulls for the TLT squeeze study. All public/keyed sources, cached to CSV."""
import io, json, os, sys, time
import httpx
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
FMP = os.environ.get("FMP_API_KEY", "")

def fmp_prices(symbol, out):
    # /stable full gives adjClose+volume; paginate backwards past the 5k cap
    url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    rows, to = [], None
    for _ in range(10):
        params = {"symbol": symbol, "apikey": FMP}
        if to: params["to"] = to
        r = httpx.get(url, params=params, timeout=60); r.raise_for_status()
        chunk = r.json()
        if not chunk: break
        rows.extend(chunk)
        earliest = min(c["date"] for c in chunk)
        if len(chunk) < 4999: break
        to = (pd.Timestamp(earliest) - pd.Timedelta(days=1)).date().isoformat()
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df.to_csv(out, index=False)
    print(symbol, len(df), df["date"].min(), "->", df["date"].max(),
          "cols:", [c for c in df.columns][:8])

def fredgraph(series, out):
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                  params={"id": series}, timeout=60, follow_redirects=True)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", series]
    df[series] = pd.to_numeric(df[series], errors="coerce")
    df.to_csv(out, index=False)
    print(series, len(df), df["date"].iloc[0], "->", df["date"].iloc[-1],
          "last:", df[series].dropna().iloc[-1])

def cftc_tff(out):
    # Traders in Financial Futures, 2010+: lev funds + asset managers, UST complex
    url = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
    names = ",".join(f"'{c}'" for c in (
        "UST 2Y NOTE", "UST 5Y NOTE", "UST 10Y NOTE",
        "ULTRA UST 10Y", "UST BOND", "ULTRA UST BOND"))
    r = httpx.get(url, params={
        "$where": f"contract_market_name in({names})",
        "$select": ("report_date_as_yyyy_mm_dd,contract_market_name,"
                    "lev_money_positions_long,lev_money_positions_short,"
                    "asset_mgr_positions_long,asset_mgr_positions_short,"
                    "open_interest_all"),
        "$limit": "50000"}, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df.to_csv(out, index=False)
    print("TFF rows:", len(df), df["report_date_as_yyyy_mm_dd"].min(), "->",
          df["report_date_as_yyyy_mm_dd"].max())

def cftc_legacy(out):
    # Legacy COT futures-only (1986+): noncommercial positioning, long history
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    r = httpx.get(url, params={
        "$where": "contract_market_name in('UST BOND','UST 10Y NOTE','ULTRA UST BOND','ULTRA UST 10Y')",
        "$select": ("report_date_as_yyyy_mm_dd,contract_market_name,"
                    "noncomm_positions_long_all,noncomm_positions_short_all,"
                    "open_interest_all"),
        "$limit": "50000"}, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df.to_csv(out, index=False)
    print("Legacy COT rows:", len(df), df["report_date_as_yyyy_mm_dd"].min(),
          "->", df["report_date_as_yyyy_mm_dd"].max())

if __name__ == "__main__":
    for sym in ("TLT", "^MOVE", "^TNX", "^TYX"):
        try: fmp_prices(sym, f"{DATA}/{sym.replace('^','')}.csv")
        except Exception as e: print(sym, "FAILED:", e)
    for s in ("DGS30", "DGS10", "DGS2", "THREEFYTP10", "T10Y2Y", "WALCL"):
        try: fredgraph(s, f"{DATA}/{s}.csv")
        except Exception as e: print(s, "FAILED:", e)
    try: cftc_tff(f"{DATA}/tff.csv")
    except Exception as e: print("TFF FAILED:", e)
    try: cftc_legacy(f"{DATA}/legacy_cot.csv")
    except Exception as e: print("legacy FAILED:", e)
