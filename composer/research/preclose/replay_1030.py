#!/usr/bin/env python3
"""results.md addendum 49: the revised preview replayed on 2026-10-30, the first live day, at the given
minutes. Yahoo's 5-minute bars stand in for the live feed: a ticker whose bars stop is stale from its
last bar, as Yahoo served it that afternoon (11 froze at ~14:25-14:55 ET). Composer's holdings are the
pre-rebalance ones read at 15:13-15:35 ET. Needs Yahoo's 1-day 5-minute bars for 2026-10-30, which it
keeps for about 60 days. Output saved as results/preclose-replay-2026-10-30.txt.

Usage: replay_1030.py 15:15 15:27"""
import datetime
import os
import sys
import zoneinfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402
NY = zoneinfo.ZoneInfo("America/New_York")
today = "2026-10-30"
cfg = sr.load_manifest()
tick = {"SPY"}
for c in cfg.values():
    tick |= sr.tree_tickers(sr.load_tree(c["eras"][-1]))
fams = set()
for t in tick:
    fams |= set(pc.family(t) or {}) | set(pc.approx_family(t) or {})
daily, bad = pc.fetch_all(tick | fams)
bars = sr.bars_fetcher("5d")(sorted(tick | fams))
META = [{"id": cfg["HG"]["symphony"], "value": 86900.0, "last_rebalance_attempted_on": "2026-10-29", "holdings": [{"ticker": "BIL", "allocation": 1.0}]},
        {"id": cfg["KMLM"]["symphony"], "value": 92144.0, "last_rebalance_attempted_on": "2026-10-29",
         "holdings": [{"ticker": "TECL", "allocation": 0.38}, {"ticker": "SOXL", "allocation": 0.32}, {"ticker": "PULS", "allocation": 0.30}]},
        {"id": cfg["SLEEVE"]["symphony"], "value": 81666.0, "last_rebalance_attempted_on": "2026-10-29", "holdings": [{"ticker": "BOXX", "allocation": 1.0}]},
        {"id": cfg["HARV"]["symphony"], "value": 37350.0, "last_rebalance_attempted_on": "2026-10-29", "holdings": [{"ticker": "PULS", "allocation": 1.0}]}]
for hhmm in sys.argv[1:]:
    now = datetime.datetime(2026, 10, 30, *map(int, hhmm.split(":")), tzinfo=NY).astimezone(datetime.timezone.utc)
    def fetch(t):
        adj, raw, meta = daily[t]
        b = (bars.get(t) or {}).get(today) or {}
        ks = [k for k in b if not k.startswith("_") and sr._min(k) + 5 <= sr._min(hhmm)]
        if not ks:
            a = {d: v for d, v in adj.items() if d < today}
            return a, {d: v for d, v in raw.items() if d < today}, {}
        k = max(ks, key=sr._min)
        prev = max(d for d in raw if d < today)
        a, r = dict(adj), dict(raw)
        r[today] = b[k]
        a[today] = adj[prev] * b[k] / raw[prev]
        last = datetime.datetime(2026, 10, 30, *map(int, k.split(":")), tzinfo=NY) + datetime.timedelta(minutes=5)
        return a, r, {"regularMarketTime": int(last.timestamp()),
                      "currentTradingPeriod": {"regular": {"start": int(datetime.datetime(2026, 10, 30, 9, 30, tzinfo=NY).timestamp()),
                                                           "end": int(datetime.datetime(2026, 10, 30, 16, 0, tzinfo=NY).timestamp())}}}
    lines, alerts, _ = pc.preview(now, lambda: META, fetch=fetch)
    print("\n".join(lines)); print("ALERTS:", alerts); print()
