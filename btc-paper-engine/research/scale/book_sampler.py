"""Repeatedly sample Hyperliquid's live BTC l2Book and build a DISTRIBUTION of
the cost to fill $100k / $250k / $1m (both sides), not a single point.

READ-ONLY. POSTs {"type":"l2Book","coin":"BTC"} to the public info endpoint.
No credentials are read, no order is ever placed/modified/cancelled.

Also records the mid every tick so the same run yields a high-frequency
volatility estimate (used by twap.py to price the drift risk of splitting).

Usage: python3 book_sampler.py <out_prefix> [minutes] [period_s] [nSigFigs]
Writes <out_prefix>.jsonl (one row per snapshot) and <out_prefix>.json (summary).
"""
from __future__ import annotations
import json, os, subprocess, sys, time, datetime as dt

INFO = "https://api.hyperliquid.xyz/info"
TARGETS = [20_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000]


def post(body, tries=4):
    for a in range(tries):
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "20", "-X", "POST", INFO,
             "-H", "Content-Type: application/json", "-d", json.dumps(body)],
            capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except Exception:
                pass
        time.sleep(1.5 * (a + 1))
    return None


def walk(levels, target_usd):
    """Walk one side of the book for target_usd of NOTIONAL. Returns
    (vwap, filled_usd, levels_consumed). levels: [{px,sz}] best-first."""
    got = 0.0
    cost = 0.0   # sum(px*qty) in USD
    qty = 0.0
    used = 0
    for lv in levels:
        px = float(lv["px"]); sz = float(lv["sz"])
        lvl_usd = px * sz
        used += 1
        if got + lvl_usd >= target_usd:
            take_usd = target_usd - got
            q = take_usd / px
            qty += q; cost += take_usd; got = target_usd
            break
        got += lvl_usd; qty += sz; cost += lvl_usd
    if qty <= 0:
        return None, 0.0, used
    return cost / qty, got, used


def snapshot(nsig=None):
    body = {"type": "l2Book", "coin": "BTC"}
    if nsig:
        body["nSigFigs"] = nsig
    d = post(body)
    if not d or "levels" not in d:
        return None
    bids, asks = d["levels"][0], d["levels"][1]
    if not bids or not asks:
        return None
    bb = float(bids[0]["px"]); ba = float(asks[0]["px"])
    mid = (bb + ba) / 2.0
    row = {
        "t": d.get("time", int(time.time() * 1000)),
        "mid": mid,
        "spread_bp": (ba - bb) / mid * 1e4,
        "n_ask_lv": len(asks), "n_bid_lv": len(bids),
        "ask_depth_usd": sum(float(l["px"]) * float(l["sz"]) for l in asks),
        "bid_depth_usd": sum(float(l["px"]) * float(l["sz"]) for l in bids),
        "l1_ask_usd": ba * float(asks[0]["sz"]),
        "l1_bid_usd": bb * float(bids[0]["sz"]),
        "buy": {}, "sell": {},
    }
    for tgt in TARGETS:
        vw, filled, used = walk(asks, tgt)
        row["buy"][str(tgt)] = None if vw is None else {
            "slip_bp": (vw / mid - 1.0) * 1e4, "filled_usd": filled,
            "complete": filled >= tgt * 0.999, "levels": used}
        vw, filled, used = walk(bids, tgt)
        row["sell"][str(tgt)] = None if vw is None else {
            "slip_bp": (1.0 - vw / mid) * 1e4, "filled_usd": filled,
            "complete": filled >= tgt * 0.999, "levels": used}
    return row


def pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main():
    prefix = sys.argv[1]
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    period = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    nsig = int(sys.argv[4]) if len(sys.argv) > 4 else None
    deadline = time.time() + minutes * 60
    rows = []
    fails = 0
    with open(prefix + ".jsonl", "w") as f:
        while time.time() < deadline:
            t0 = time.time()
            r = snapshot(nsig)
            if r is None:
                fails += 1
            else:
                rows.append(r)
                f.write(json.dumps(r) + "\n")
                f.flush()
            time.sleep(max(0.0, period - (time.time() - t0)))

    summ = {
        "n_samples": len(rows), "n_failed_polls": fails,
        "nSigFigs": nsig, "period_s": period,
        "wall_start_utc": dt.datetime.utcfromtimestamp(rows[0]["t"] / 1000).isoformat() + "Z",
        "wall_end_utc": dt.datetime.utcfromtimestamp(rows[-1]["t"] / 1000).isoformat() + "Z",
        "span_min": (rows[-1]["t"] - rows[0]["t"]) / 60000.0,
        "mid": {"first": rows[0]["mid"], "last": rows[-1]["mid"],
                "min": min(r["mid"] for r in rows), "max": max(r["mid"] for r in rows)},
        "spread_bp": {k: pct([r["spread_bp"] for r in rows], p)
                      for k, p in [("p50", 50), ("p90", 90), ("p99", 99), ("max", 100)]},
        "ask_depth_usd": {k: pct([r["ask_depth_usd"] for r in rows], p)
                          for k, p in [("min", 0), ("p10", 10), ("p50", 50), ("max", 100)]},
        "bid_depth_usd": {k: pct([r["bid_depth_usd"] for r in rows], p)
                          for k, p in [("min", 0), ("p10", 10), ("p50", 50), ("max", 100)]},
        "slip": {},
    }
    for side in ("buy", "sell"):
        for tgt in TARGETS:
            k = str(tgt)
            vals = [r[side][k]["slip_bp"] for r in rows
                    if r[side][k] and r[side][k]["complete"]]
            inc = [r for r in rows if r[side][k] and not r[side][k]["complete"]]
            summ["slip"][f"{side}_{k}"] = {
                "n_complete": len(vals), "n_incomplete": len(inc),
                "worst_incomplete_filled_usd": (min(r[side][k]["filled_usd"] for r in inc)
                                                if inc else None),
                "p50": pct(vals, 50), "p90": pct(vals, 90), "p99": pct(vals, 99),
                "worst": pct(vals, 100), "best": pct(vals, 0),
                "mean": (sum(vals) / len(vals)) if vals else None,
            }
    # high-frequency mid vol for the TWAP drift calc
    lr = []
    for a, b in zip(rows, rows[1:]):
        dtm = (b["t"] - a["t"]) / 1000.0
        if dtm > 0 and a["mid"] > 0:
            lr.append(((b["mid"] / a["mid"] - 1.0), dtm))
    if lr:
        import math
        # normalise each return to a per-second vol then rescale
        var_per_s = sum(r * r / d for r, d in lr) / len(lr)
        summ["mid_vol"] = {
            "n_returns": len(lr),
            "sigma_per_min_bp": math.sqrt(var_per_s * 60) * 1e4,
            "sigma_per_5min_bp": math.sqrt(var_per_s * 300) * 1e4,
            "sigma_per_30min_bp": math.sqrt(var_per_s * 1800) * 1e4,
            "basis": "realised vol of l2Book mid sampled during THIS calm window; "
                     "annualisation of HF vol understates event vol.",
        }
    with open(prefix + ".json", "w") as f:
        json.dump(summ, f, indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
