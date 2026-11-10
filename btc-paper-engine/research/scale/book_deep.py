"""How much BTC depth sits inside ~23bp of mid, sampled over time?

The default l2Book returns 20 levels/side, which on BTC is only ~2-3bp wide and
~$3.7m -- so it CANNOT answer "what does $5m cost". Requesting nSigFigs=4
coarsens the price buckets ($10 on BTC), so the same 20 levels span ~23bp and
reveal far more depth. READ-ONLY; no credentials, no orders.

Caveat recorded in the output: bucket prices are rounded to 4 significant
figures, so each level's price is up to ~$5 (0.6bp) off the true limit prices
inside it. Fine for orders whose fill spans many buckets; too coarse for <$1m.

Usage: python3 book_deep.py <out_prefix> [minutes] [period_s]
"""
import json, subprocess, sys, time
INFO = "https://api.hyperliquid.xyz/info"
TARGETS = [1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000]
pre, mins, per = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

def walk(levels, tgt):
    got = cost = qty = 0.0
    for l in levels:
        px, sz = float(l["px"]), float(l["sz"])
        u = px * sz
        if got + u >= tgt:
            q = (tgt - got) / px; qty += q; cost += tgt - got; got = tgt; break
        got += u; qty += sz; cost += u
    return (cost / qty if qty else None), got

def pctl(xs, p):
    s = sorted(xs)
    if not s: return None
    k = (len(s)-1)*p/100.0; lo=int(k); hi=min(lo+1,len(s)-1)
    return s[lo] + (s[hi]-s[lo])*(k-lo)

rows = []
dl = time.time() + mins*60
while time.time() < dl:
    t0 = time.time()
    r = subprocess.run(["curl","-sS","--max-time","20","-X","POST",INFO,
        "-H","Content-Type: application/json",
        "-d",'{"type":"l2Book","coin":"BTC","nSigFigs":4}'],capture_output=True,text=True)
    try:
        d = json.loads(r.stdout); bids, asks = d["levels"]
        mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
        row = {"t": d["time"], "mid": mid,
               "ask_depth_usd": sum(float(l["px"])*float(l["sz"]) for l in asks),
               "bid_depth_usd": sum(float(l["px"])*float(l["sz"]) for l in bids),
               "ask_span_bp": abs(float(asks[-1]["px"])-mid)/mid*1e4,
               "bid_span_bp": abs(float(bids[-1]["px"])-mid)/mid*1e4,
               "buy": {}, "sell": {}}
        for t in TARGETS:
            vw, f = walk(asks, t)
            row["buy"][str(t)] = {"slip_bp": (vw/mid-1)*1e4 if vw else None,
                                  "filled": f, "complete": f >= t*0.999}
            vw, f = walk(bids, t)
            row["sell"][str(t)] = {"slip_bp": (1-vw/mid)*1e4 if vw else None,
                                   "filled": f, "complete": f >= t*0.999}
        rows.append(row)
    except Exception:
        pass
    time.sleep(max(0.0, per-(time.time()-t0)))

with open(pre+".jsonl","w") as f:
    for r in rows: f.write(json.dumps(r)+"\n")
summ = {"n_samples": len(rows), "aggregation": "nSigFigs=4 (~$10 buckets)",
        "span_min": (rows[-1]["t"]-rows[0]["t"])/60000.0,
        "price_band_bp": {"ask_p50": pctl([r["ask_span_bp"] for r in rows],50),
                          "bid_p50": pctl([r["bid_span_bp"] for r in rows],50)},
        "depth_usd_in_band": {s: {f"p{p}": pctl([r[f"{s}_depth_usd"] for r in rows],p)
                                  for p in (0,10,50,90,100)} for s in ("ask","bid")},
        "bucket_rounding_caveat": "level prices rounded to 4 s.f. (~$5 / 0.6bp); "
                                  "understates precision for sub-$1m orders",
        "slip": {}}
for side in ("buy","sell"):
    for t in TARGETS:
        k=str(t)
        v=[r[side][k]["slip_bp"] for r in rows if r[side][k]["complete"]]
        inc=[r[side][k]["filled"] for r in rows if not r[side][k]["complete"]]
        summ["slip"][f"{side}_{k}"]={"n_complete":len(v),"n_incomplete":len(inc),
            "p50":pctl(v,50),"p90":pctl(v,90),"worst":pctl(v,100),
            "worst_incomplete_filled_usd":min(inc) if inc else None}
json.dump(summ, open(pre+".json","w"), indent=1)
print(json.dumps(summ, indent=1))
