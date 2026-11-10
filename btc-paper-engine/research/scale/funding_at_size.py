"""Does FUNDING bind the book at $100k / $250k / $1m of BTC perp notional?

READ-ONLY. Pulls Hyperliquid's public BTC hourly funding history from the info
endpoint (no credentials, no orders) and prices it against the strategy's OWN
realised holding windows, with SIGN -- the pullback reference book is 46 short /
44 long, so funding is not a pure cost.

Three bases, all reported:
  (1) 24/7 always-long   -- the upper bound the naive question implies
  (2) always-long but only during the reference trades' holding hours
  (3) SIGNED on the actual trades (long pays +rate, short receives +rate)
      -- the honest number for this book

Then: funding expressed as bp per round trip, directly comparable to the
8.64 bp round-trip fee whose correction cost ~39% of authorised size
(RESEARCH_FEES.md), and scaled to dollars at each notional.

Usage: python3 funding_at_size.py <out_dir>
"""
from __future__ import annotations
import csv, datetime as dt, json, math, os, subprocess, sys, time

INFO = "https://api.hyperliquid.xyz/info"
HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "..", "backend", "reference",
                   "btc_pullback_trades_optimized.csv")
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else HERE
NOTIONALS = [15_000, 100_000, 250_000, 1_000_000]
FEE_RT_BP = 8.64          # RESEARCH_FEES.md measured round trip
EQUITY = 100_055.0        # live equity, for %-of-equity framing only


def post(body, tries=5):
    for a in range(tries):
        r = subprocess.run(["curl", "-sS", "--max-time", "30", "-X", "POST", INFO,
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(body)], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except Exception:
                pass
        time.sleep(1.5 * (a + 1))
    raise RuntimeError("info endpoint failed")


def fetch_funding(cache):
    if os.path.exists(cache):
        with open(cache) as f:
            rows = [(int(a), float(b)) for a, b in csv.reader(f) if a != "ts_ms"]
        if rows:
            return dict(rows)
    hl = {}
    cur = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000)
    while cur < end:
        data = post({"type": "fundingHistory", "coin": "BTC",
                     "startTime": cur, "endTime": min(cur + 45 * 86400 * 1000, end)})
        for d in (data or []):
            hl[int(d["time"])] = float(d["fundingRate"])
        cur = (max(int(d["time"]) for d in data) + 1) if data else cur + 45 * 86400 * 1000
        time.sleep(0.25)
    with open(cache, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ts_ms", "funding_rate_1h"])
        for t in sorted(hl):
            w.writerow([t, hl[t]])
    return hl


def pctl(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p / 100.0
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main():
    cache = os.path.join(OUTDIR, "funding_hl_btc.csv")
    hl = fetch_funding(cache)
    ts = sorted(hl)
    out = {}

    out["funding_history"] = {
        "n_hourly_stamps": len(ts),
        "first_utc": dt.datetime.utcfromtimestamp(ts[0] / 1000).isoformat() + "Z",
        "last_utc": dt.datetime.utcfromtimestamp(ts[-1] / 1000).isoformat() + "Z",
        "gaps_over_1h": sum(1 for a, b in zip(ts, ts[1:]) if b - a > 3_660_000),
        "mean_annualized_pct_full": sum(hl.values()) / len(hl) * 24 * 365 * 100,
        "pct_hours_positive": 100 * sum(1 for v in hl.values() if v > 0) / len(hl),
        "hourly_rate_pctiles_bp": {f"p{p}": pctl(list(hl.values()), p) * 1e4
                                   for p in (1, 5, 25, 50, 75, 95, 99)},
    }
    by_year = {}
    for t, v in hl.items():
        y = dt.datetime.utcfromtimestamp(t / 1000).year
        by_year.setdefault(y, []).append(v)
    out["funding_history"]["mean_annualized_pct_by_year"] = {
        str(y): sum(v) / len(v) * 24 * 365 * 100 for y, v in sorted(by_year.items())}

    # rolling 30d / 90d mean annualized -- the REGIME RANGE, for stress framing
    vals = [hl[t] for t in ts]
    for win_d, lbl in ((30, "30d"), (90, "90d")):
        w = win_d * 24
        if len(vals) > w:
            roll = [sum(vals[i:i + w]) / w * 24 * 365 * 100
                    for i in range(0, len(vals) - w, 24)]
            out["funding_history"][f"rolling_{lbl}_annualized_pct"] = {
                "min": min(roll), "p10": pctl(roll, 10), "median": pctl(roll, 50),
                "p90": pctl(roll, 90), "max": max(roll),
                "latest": roll[-1], "n_windows": len(roll)}

    # ---------- the strategy's own holding windows ----------
    trades = list(csv.DictReader(open(REF)))
    def parse(s):
        return dt.datetime.fromisoformat(s)
    t0, t1 = parse(trades[0]["entry"]), parse(trades[-1]["exit"])
    span_h = (t1 - t0).total_seconds() / 3600.0
    years = span_h / 8760.0

    # funding stamps inside the trade window only (apples-to-apples regime)
    win = {t: v for t, v in hl.items()
           if t0.timestamp() * 1000 <= t <= t1.timestamp() * 1000}
    mean_win_ann = sum(win.values()) / len(win) * 24 * 365 * 100

    def sum_rate(a, b):
        """Sum of hourly funding stamps applied in [a, b). Stamp at T is settled
        at T (fetch_funding.py audit note), so a position held [a,b) pays stamps
        with a < T <= b."""
        lo, hi = a.timestamp() * 1000, b.timestamp() * 1000
        return sum(v for t, v in hl.items() if lo < t <= hi), \
               sum(1 for t in hl if lo < t <= hi)

    per_trade, missing = [], 0
    held_h = 0.0
    for tr in trades:
        a, b = parse(tr["entry"]), parse(tr["exit"])
        s, n = sum_rate(a, b)
        hrs = (b - a).total_seconds() / 3600.0
        held_h += hrs
        if n < hrs * 0.9:
            missing += 1
        sgn = -1.0 if tr["side"] == "L" else +1.0   # long PAYS +rate; short RECEIVES
        per_trade.append({
            "side": tr["side"], "hours": hrs, "funding_sum": s,
            "signed_return": sgn * s,          # as a fraction of notional
            "gross_return": float(tr["ret"]),
        })
    tim = held_h / span_h

    sum_signed = sum(p["signed_return"] for p in per_trade)
    sum_long_only = -sum(p["funding_sum"] for p in per_trade)   # basis (2)
    always_long_ann = -sum(win.values()) / len(win) * 24 * 365  # basis (1), fraction/yr
    gross_sum = sum(p["gross_return"] for p in per_trade)

    out["trade_window"] = {
        "first_entry": str(t0), "last_exit": str(t1),
        "span_years": years, "n_trades": len(trades),
        "n_long": sum(1 for p in per_trade if p["side"] == "L"),
        "n_short": sum(1 for p in per_trade if p["side"] == "S"),
        "held_hours": held_h, "time_in_market_pct": tim * 100,
        "trades_with_missing_funding_stamps": missing,
        "mean_annualized_funding_pct_in_window": mean_win_ann,
        "gross_return_sum_frac_of_notional": gross_sum,
        "gross_return_per_year_frac_of_notional": gross_sum / years,
        "trades_per_year": len(trades) / years,
    }

    fee_yr = len(trades) / years * FEE_RT_BP / 1e4
    bases = {
        "1_always_long_24_7": {
            "annual_frac_of_notional": always_long_ann,
            "note": "upper bound: long the whole window, never flat",
        },
        "2_always_long_only_while_held": {
            "annual_frac_of_notional": sum_long_only / years,
            "note": "the book's real time-in-market (%.1f%%), but every trade forced long" % (tim * 100),
        },
        "3_signed_actual_trades": {
            "annual_frac_of_notional": sum_signed / years,
            "note": "THE HONEST NUMBER: 46 shorts receive funding, 44 longs pay it",
        },
    }
    for k, v in bases.items():
        f = v["annual_frac_of_notional"]
        v["annual_pct_of_notional"] = f * 100
        v["bp_per_round_trip_equivalent"] = f * years / len(trades) * 1e4
        v["vs_fee_rt_bp_8.64"] = (f * years / len(trades) * 1e4) / FEE_RT_BP
        v["dollars_per_year"] = {str(n): f * n for n in NOTIONALS}
        v["pct_of_gross_edge"] = f / (gross_sum / years) * 100
        # net edge after fees and this funding basis
        v["net_after_fees_and_funding_pct_of_notional_per_yr"] = (
            gross_sum / years - fee_yr + f) * 100
    out["funding_cost_bases"] = bases
    out["fee_load"] = {
        "round_trip_bp": FEE_RT_BP, "trades_per_year": len(trades) / years,
        "annual_pct_of_notional": fee_yr * 100,
        "dollars_per_year": {str(n): fee_yr * n for n in NOTIONALS},
    }

    # -------- the invariance point, stated numerically --------
    inv = {}
    for n in NOTIONALS:
        f3 = bases["3_signed_actual_trades"]["annual_frac_of_notional"]
        inv[str(n)] = {
            "funding_usd_per_yr": f3 * n,
            "gross_edge_usd_per_yr": gross_sum / years * n,
            "fees_usd_per_yr": -fee_yr * n,
            "funding_as_pct_of_gross_edge": f3 / (gross_sum / years) * 100,
            "notional_over_equity_at_100k_equity": n / EQUITY,
        }
    out["size_invariance"] = {
        "table": inv,
        "point": "funding, fees and gross edge are ALL linear in notional, so the "
                 "RATIO is identical at $15k and $1m. Funding is an edge haircut, "
                 "not a size constraint. It is invisible at $15k in dollars and "
                 "equally invisible at $1m in proportion.",
    }

    # -------- stress: worst sustained funding regime in history --------
    if "rolling_90d_annualized_pct" in out["funding_history"]:
        worst = out["funding_history"]["rolling_90d_annualized_pct"]["max"]
        # scale basis-2 (all-long) by the ratio of worst regime to window regime
        scale = worst / mean_win_ann if mean_win_ann else float("nan")
        b2 = bases["2_always_long_only_while_held"]["annual_frac_of_notional"]
        out["stress_all_long_worst_90d_regime"] = {
            "worst_90d_annualized_funding_pct": worst,
            "window_mean_annualized_pct": mean_win_ann,
            "scale_factor": scale,
            "annual_pct_of_notional": b2 * scale * 100,
            "dollars_per_year": {str(n): b2 * scale * n for n in NOTIONALS},
            "pct_of_gross_edge": b2 * scale / (gross_sum / years) * 100,
            "note": "hypothetical: an all-LONG book in the hottest 90d funding "
                    "regime HL has ever printed, at this book's time-in-market. "
                    "The real book is half short, so this is a bound, not a forecast.",
        }

    # -------- sign/regime interaction: are we short when funding is hot? --------
    hot, cold = [], []
    for p in per_trade:
        (hot if p["funding_sum"] / max(p["hours"], 1) * 24 * 365 > 0.10 else cold).append(p)
    out["sign_regime_interaction"] = {
        "trades_in_hot_funding_gt_10pct_ann": len(hot),
        "hot_short_share_pct": 100 * sum(1 for p in hot if p["side"] == "S") / max(len(hot), 1),
        "trades_in_cold_funding": len(cold),
        "cold_short_share_pct": 100 * sum(1 for p in cold if p["side"] == "S") / max(len(cold), 1),
        "hot_signed_funding_bp_mean": 1e4 * sum(p["signed_return"] for p in hot) / max(len(hot), 1),
        "cold_signed_funding_bp_mean": 1e4 * sum(p["signed_return"] for p in cold) / max(len(cold), 1),
        "note": "if the book is short more often when funding is hot, funding is a "
                "net credit -- but this is an in-sample coincidence, not a rule.",
    }

    out["per_trade"] = per_trade
    with open(os.path.join(OUTDIR, "funding_at_size.json"), "w") as f:
        json.dump(out, f, indent=1)
    slim = {k: v for k, v in out.items() if k != "per_trade"}
    print(json.dumps(slim, indent=1))


if __name__ == "__main__":
    main()
