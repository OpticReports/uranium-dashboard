"""Fetch Bitstamp 4h OHLC for any pair from its first available bar, gap-checked.

Generalises backend/scripts/fetch_bars.py (BTC from 2020-06) to the full
history, because the only honest out-of-sample data left for this book is
the history the pullback was never fitted on (RESEARCH_PROTOCOL.md 9a: the
2024-07..2026-07 holdout is spent).

Usage: python3 fetch_pairs.py <pair> [<pair> ...]     e.g. btcusd ethusd
Writes research/cagr/data/bars_4h_<pair>.csv
"""
import csv, json, os, sys, time, urllib.request

STEP = 14400
HERE = os.path.dirname(os.path.abspath(__file__))
START = 1293840000          # 2011-01-01; Bitstamp returns from its first bar


def fetch(pair: str) -> str:
    rows, cur = {}, START
    while True:
        url = (f"https://www.bitstamp.net/api/v2/ohlc/{pair}/?step={STEP}"
               f"&limit=1000&start={cur}")
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = json.load(r)["data"]["ohlc"]
                break
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        if not data:
            # Before the pair's first bar Bitstamp returns an empty page
            # rather than jumping forward; walk forward until it starts.
            if not rows and cur < time.time():
                cur += 1000 * STEP
                continue
            break
        for d in data:
            rows[int(d["timestamp"])] = (d["open"], d["high"], d["low"],
                                         d["close"], d["volume"])
        last = int(data[-1]["timestamp"])
        # A short page is NOT end-of-data: early Bitstamp history is sparse
        # (no-trade 4h bars are simply absent), so a 1000-bar window can come
        # back with fewer rows mid-history. Stop only on reaching the present.
        nxt = max(last + STEP, cur + STEP)
        if nxt > time.time():
            break
        cur = nxt if len(data) >= 1000 else max(last + STEP, cur + 1000 * STEP)
        time.sleep(0.3)
    ts = sorted(rows)
    gaps = [(a, b) for a, b in zip(ts, ts[1:]) if b - a != STEP]
    out = os.path.join(HERE, "data", f"bars_4h_{pair}.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_open_unix", "open", "high", "low", "close", "volume"])
        for t in ts:
            w.writerow([t, *rows[t]])
    missing = sum((b - a) // STEP - 1 for a, b in gaps)
    return (f"{pair}: bars={len(ts)} first={time.strftime('%Y-%m-%d', time.gmtime(ts[0]))} "
            f"last={time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts[-1]))} "
            f"gaps={len(gaps)} missing_bars={missing}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(fetch(p), flush=True)
