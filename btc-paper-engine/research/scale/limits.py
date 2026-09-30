"""What does Hyperliquid itself bound on a single BTC perp position?
READ-ONLY: `meta`, `metaAndAssetCtxs` from the public info endpoint.
Usage: python3 limits.py <out_dir>"""
import json, os, subprocess, sys, time
INFO = "https://api.hyperliquid.xyz/info"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
def post(b):
    r = subprocess.run(["curl","-sS","--max-time","30","-X","POST",INFO,
        "-H","Content-Type: application/json","-d",json.dumps(b)],
        capture_output=True, text=True)
    return json.loads(r.stdout)
mc = post({"type":"metaAndAssetCtxs"})
meta, ctxs = mc[0], mc[1]
i = [k for k,u in enumerate(meta["universe"]) if u["name"]=="BTC"][0]
u, c = meta["universe"][i], ctxs[i]
tables = dict(meta["marginTables"])
tbl = tables.get(u["marginTableId"]) or tables.get(str(u["marginTableId"]))
oi_btc = float(c["openInterest"]); mark = float(c["markPx"])
res = {
 "btc_universe": u,
 "margin_table": tbl,
 "keys_present_in_meta": list(meta.keys()),
 "any_position_or_oi_cap_field_in_meta": sorted(
     {k for uu in meta["universe"] for k in uu} - {"szDecimals","name","maxLeverage",
      "marginTableId","onlyIsolated","isDelisted"}),
 "open_interest_btc": oi_btc, "mark_px": mark,
 "open_interest_usd": oi_btc*mark,
 "day_notional_volume_usd": float(c["dayNtlVlm"]),
 "funding_1h_now": float(c["funding"]), "premium_now": float(c["premium"]),
 "impact_pxs": c["impactPxs"],
 "sz_decimals": u["szDecimals"],
 "min_size_increment_btc": 10**-u["szDecimals"],
 "one_million_as_pct_of_open_interest": 1e6/(oi_btc*mark)*100,
 "one_million_as_pct_of_daily_volume": 1e6/float(c["dayNtlVlm"])*100,
 "docs_stated_2026_09_28": {
   "position_limit": "N/A for BTC (contract specifications page)",
   "max_market_order_value_usd": 30_000_000,
   "max_limit_order_value_usd": 300_000_000,
   "funding_impact_notional_usdc": 20_000,
   "source": "hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications",
 },
}
json.dump(res, open(os.path.join(OUT,"limits.json"),"w"), indent=1)
print(json.dumps(res, indent=1))
