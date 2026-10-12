"""Fetch Yahoo (primary) + FMP (cross-check) daily bars and Yahoo distribution
events for the B.5-vs-SPY trailing-12m study. Writes prices.parquet + events.json."""
import json, sys, time
from pathlib import Path
import httpx
import pandas as pd
from barbell.ingest.yahoo import YahooProvider, _URL, _HEADERS
from barbell.ingest.fmp import FMPProvider

OUT = Path(sys.argv[1])
FETCH_START, END = "2025-06-01", "2026-10-09"   # END = last COMPLETE close (2026-10-12 is intraday)
TICKERS = ["AVUV", "AVDV", "PHYS", "KMLM", "AVEM", "QUAL", "TAIL", "SPY", "MTUM", "BIL"]

y, f = YahooProvider(), FMPProvider()
frames, events = {}, {}
for t in TICKERS:
    dy = y.daily(t, FETCH_START, END)
    frames[("yahoo", t)] = dy["close_adj"]
    frames[("yahoo_raw", t)] = dy["close_raw"]
    df = f.daily(t, FETCH_START, END)
    frames[("fmp", t)] = df["close_adj"]
    frames[("fmp_raw", t)] = df["close_raw"]
    # distribution events (Yahoo) — the adapter ignores them; we want them listed
    p1 = int(pd.Timestamp(FETCH_START, tz="UTC").timestamp())
    p2 = int((pd.Timestamp(END, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    r = httpx.get(_URL.format(symbol=t), params={"period1": p1, "period2": p2, "interval": "1d",
                  "events": "div,split,capitalGains"}, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    ev = r.json()["chart"]["result"][0].get("events", {})
    events[t] = {k: sorted(({"date": str(pd.to_datetime(v["date"], unit="s").date()),
                             "amount": v.get("amount", v.get("numerator"))} for v in d.values()),
                            key=lambda e: e["date"]) for k, d in ev.items()}
    print(t, "yahoo", len(dy), dy.index.min().date(), dy.index.max().date(),
          "| fmp", len(df), df.index.min().date(), df.index.max().date(), "| ev", {k: len(v) for k, v in events[t].items()})
    time.sleep(0.5)

px = pd.DataFrame(frames)
px.columns = pd.MultiIndex.from_tuples(px.columns, names=["src", "ticker"])
px.to_parquet(OUT / "prices.parquet")
(OUT / "events.json").write_text(json.dumps(events, indent=1))
