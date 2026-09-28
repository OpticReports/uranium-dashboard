"""Is order-splitting / TWAP worth it at $1m? Quantified, not assumed.

READ-ONLY (public info endpoint; no credentials, no orders).

Three measured inputs, then one comparison:
  A. SLIP SAVED by slicing -- from the book_sampler distribution: cost of one
     $1m taker order vs 4 x $250k vs 10 x $100k. Slices are priced at the
     SNAPSHOT cost of that size, i.e. assuming the book FULLY replenishes
     between slices -> an UPPER BOUND on the saving.
  B. REPLENISHMENT rate -- from book_raw.jsonl, level-by-level added size per
     second near the touch. Sets the minimum slice spacing at which (A) is even
     physically available.
  C. TIMING RISK paid for the delay -- realised BTC vol over 1/5/15/30 min from
     Hyperliquid's own 1m candles (candleSnapshot), unconditional.

Then: break-even execution window T* where sigma(T) == slip saved. Plus the HL
volume-tier arithmetic, which is the one cost that gets BETTER with size.

Usage: python3 twap.py <out_dir>
"""
from __future__ import annotations
import datetime as dt, json, math, os, statistics, subprocess, sys, time

INFO = "https://api.hyperliquid.xyz/info"
HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else HERE
# live account's own measured rates (maker_fill.json, userFees): 4% referral disc.
TAKER_BP_T0, REF_DISC = 4.5, 0.04
# HL published perp tiers: (14d volume USD, taker %, maker %)
TIERS = [(0, 0.045, 0.015), (5e6, 0.040, 0.012), (25e6, 0.035, 0.008),
         (100e6, 0.030, 0.004), (500e6, 0.028, 0.0), (2e9, 0.026, 0.0)]
TRADES_PER_YR = 45.667      # measured, pullback reference book (90 / 1.9708y)
PULLBACK_W = 0.75           # live blend weight


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


def pctl(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p / 100.0
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ---------------- C. realised short-horizon vol from 1m candles ----------------
def vol_from_candles(days=10):
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    cs = post({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1m",
                                                 "startTime": start, "endTime": end}})
    cs = sorted(cs, key=lambda c: c["t"])
    closes = [(int(c["t"]), float(c["c"])) for c in cs]
    out = {"n_1m_candles": len(closes),
           "first_utc": dt.datetime.utcfromtimestamp(closes[0][0] / 1000).isoformat() + "Z",
           "last_utc": dt.datetime.utcfromtimestamp(closes[-1][0] / 1000).isoformat() + "Z",
           "horizons": {}}
    px = [c for _, c in closes]
    for h in (1, 2, 5, 10, 15, 30):
        moves = [abs(px[i + h] / px[i] - 1.0) * 1e4 for i in range(len(px) - h)]
        signed = [(px[i + h] / px[i] - 1.0) * 1e4 for i in range(len(px) - h)]
        out["horizons"][f"{h}min"] = {
            "sigma_bp": statistics.pstdev(signed),
            "mean_abs_bp": sum(moves) / len(moves),
            "median_abs_bp": pctl(moves, 50), "p90_abs_bp": pctl(moves, 90),
            "p99_abs_bp": pctl(moves, 99), "max_abs_bp": max(moves),
            "n": len(moves)}
    return out


# ---------------- B. replenishment near the touch ----------------
def replenishment(path, bp_band=10.0):
    if not os.path.exists(path):
        return {"error": "no raw book capture"}
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if len(rows) < 5:
        return {"error": f"only {len(rows)} raw snapshots"}
    add_rates = {"ask": [], "bid": []}
    net_rates = {"ask": [], "bid": []}
    band_depth = {"ask": [], "bid": []}
    for a, b in zip(rows, rows[1:]):
        dtm = (b["t"] - a["t"]) / 1000.0
        if dtm <= 0 or dtm > 15:
            continue
        for si, side in ((0, "bid"), (1, "ask")):
            la, lb = a["levels"][si], b["levels"][si]
            if not la or not lb:
                continue
            mid_b = (float(b["levels"][0][0]["px"]) + float(b["levels"][1][0]["px"])) / 2
            lim = mid_b * bp_band / 1e4
            fa = {float(l["px"]): float(l["sz"]) for l in la
                  if abs(float(l["px"]) - mid_b) <= lim}
            fb = {float(l["px"]): float(l["sz"]) for l in lb
                  if abs(float(l["px"]) - mid_b) <= lim}
            added = sum(max(0.0, fb.get(p, 0.0) - fa.get(p, 0.0)) * p
                        for p in set(fa) | set(fb))
            net = sum(fb.get(p, 0.0) * p for p in fb) - sum(fa.get(p, 0.0) * p for p in fa)
            add_rates[side].append(added / dtm)
            net_rates[side].append(net / dtm)
            band_depth[side].append(sum(fb.get(p, 0.0) * p for p in fb))
    out = {"band_bp": bp_band, "n_intervals": len(add_rates["ask"]),
           "caveat": "added size at a price level includes levels that merely came "
                     "INTO the band as mid drifted -> an UPPER bound on true refill."}
    for side in ("ask", "bid"):
        if not add_rates[side]:
            continue
        out[side] = {
            "gross_added_usd_per_s": {"p50": pctl(add_rates[side], 50),
                                      "p10": pctl(add_rates[side], 10),
                                      "p90": pctl(add_rates[side], 90)},
            "net_change_usd_per_s_p50": pctl(net_rates[side], 50),
            "band_depth_usd": {"p10": pctl(band_depth[side], 10),
                               "p50": pctl(band_depth[side], 50),
                               "p90": pctl(band_depth[side], 90)},
        }
        r = out[side]["gross_added_usd_per_s"]["p50"]
        out[side]["seconds_to_refill_1m_at_p50_rate"] = (1e6 / r) if r else None
    return out


# ---------------- A. slip saved by slicing ----------------
def slice_benefit(summary_path, deep_path):
    s = json.load(open(summary_path))
    deep = json.load(open(deep_path))
    sl = s["slip"]
    res = {"n_samples": s["n_samples"], "span_min": s["span_min"],
           "window_utc": [s["wall_start_utc"], s["wall_end_utc"]],
           "SELECTION_BIAS_FOUND": (
               "In the fine (default 20-level) book, %d of %d snapshots could not "
               "show a full $1m on the ask -- min visible ask depth $%s. Those are "
               "exactly the THIN snapshots, and excluding them biases the fine-book "
               "$1m distribution LOW. The $1m reference below therefore comes from "
               "the coarse (nSigFigs=4) probe, where all %d samples filled."
               % (sl["buy_1000000"]["n_incomplete"], s["n_samples"],
                  f"{sl['buy_1000000']['worst_incomplete_filled_usd']:,.0f}",
                  deep["n_samples"])),
           "plans": {}}
    for side in ("buy", "sell"):
        one = deep["slip"][f"{side}_1000000"]      # unbiased $1m reference
        one = {"p50": one["p50"], "p90": one["p90"], "worst": one["worst"],
               "n_complete": one["n_complete"], "n_incomplete": one["n_incomplete"],
               "source": "book_deep (nSigFigs=4), all samples filled"}
        for label, (n, tgt) in {"1x1,000,000": (1, 1_000_000),
                                "2x500,000": (2, 500_000),
                                "4x250,000": (4, 250_000),
                                "10x100,000": (10, 100_000)}.items():
            leg = sl[f"{side}_{tgt}"]
            if leg["p50"] is None:
                continue
            res["plans"][f"{side} {label}"] = {
                "slip_p50_bp": leg["p50"], "slip_p90_bp": leg["p90"],
                "slip_worst_bp": leg["worst"],
                "saving_vs_one_shot_p50_bp": (one["p50"] - leg["p50"]) if one["p50"] else None,
                "saving_vs_one_shot_p90_bp": (one["p90"] - leg["p90"]) if one["p90"] else None,
                "saving_vs_one_shot_worst_bp": (one["worst"] - leg["worst"]) if one["worst"] else None,
                "saving_usd_on_1m_p50": ((one["p50"] - leg["p50"]) / 1e4 * 1e6)
                                        if one["p50"] else None,
                "saving_usd_on_1m_worst": ((one["worst"] - leg["worst"]) / 1e4 * 1e6)
                                          if one["worst"] else None,
                "n_slices": n,
                "incomplete_snapshots": leg["n_incomplete"],
            }
        res[f"{side}_one_shot_1m"] = one
    return res


def main():
    out = {"basis": "all numbers measured 2026-09-28 from Hyperliquid public "
                    "endpoints; read-only, no orders placed."}
    out["A_slice_benefit"] = slice_benefit(os.path.join(OUTDIR, "book_calm.json"),
                                          os.path.join(OUTDIR, "book_deep.json"))
    out["B_replenishment"] = replenishment(os.path.join(OUTDIR, "book_raw.jsonl"))
    out["C_timing_risk"] = vol_from_candles()

    # ---- break-even: how long may an execution take before vol > slip saved ----
    sig1 = out["C_timing_risk"]["horizons"]["1min"]["sigma_bp"]
    be = {}
    for k, v in out["A_slice_benefit"]["plans"].items():
        sav = v.get("saving_vs_one_shot_p50_bp")
        if sav is None or sav <= 0:
            be[k] = {"saving_bp": sav, "verdict": "no saving to buy"}
            continue
        # sigma(T) = sig1 * sqrt(T_min) ; solve sigma(T) = saving
        t_star_min = (sav / sig1) ** 2
        savw = v.get("saving_vs_one_shot_worst_bp") or 0.0
        be[k] = {"saving_bp": sav, "sigma_1min_bp": sig1,
                 "breakeven_window_min": t_star_min,
                 "breakeven_window_s": t_star_min * 60,
                 "saving_worst_case_bp": savw,
                 "breakeven_window_s_worst_case": ((savw / sig1) ** 2) * 60,
                 "verdict": ("TWAP defensible" if t_star_min > 5 else
                             "timing risk swamps the saving")}
    out["D_breakeven"] = be
    out["D_breakeven"]["reading"] = (
        "A slice plan is only worth it if the execution window it needs is SHORTER "
        "than the break-even window. Spacing slices far enough apart for the book to "
        "refill costs multiples of the slip it saves.")

    # 30-min TWAP explicit cost/benefit on $1m
    h5 = out["C_timing_risk"]["horizons"]["5min"]
    h30 = out["C_timing_risk"]["horizons"]["30min"]
    best = max((v.get("saving_vs_one_shot_p50_bp") or 0)
               for v in out["A_slice_benefit"]["plans"].values())
    out["E_twap_1m_explicit"] = {
        "max_slip_saving_available_bp": best,
        "max_slip_saving_usd_on_1m": best / 1e4 * 1e6,
        "5min_window_sigma_bp": h5["sigma_bp"],
        "5min_window_sigma_usd_on_1m": h5["sigma_bp"] / 1e4 * 1e6,
        "5min_p90_abs_move_usd_on_1m": h5["p90_abs_bp"] / 1e4 * 1e6,
        "30min_window_sigma_usd_on_1m": h30["sigma_bp"] / 1e4 * 1e6,
        "30min_p99_abs_move_usd_on_1m": h30["p99_abs_bp"] / 1e4 * 1e6,
        "risk_over_reward_5min": h5["sigma_bp"] / best if best else None,
        "note": "unconditional vol is zero-mean, so this is variance added, not "
                "expected loss. For a signal-triggered entry the conditional drift "
                "is the wrong way (you delay buying a market the signal says is "
                "moving), so the unconditional figure UNDERSTATES the cost of delay.",
    }

    # ---- HL volume tiers: the one cost that improves with size ----
    vol_mult = TRADES_PER_YR * 2 * PULLBACK_W        # annual volume / gross notional
    tier_tbl = {}
    for g in (15_000, 100_000, 250_000, 1_000_000, 2_000_000, 10_000_000):
        v14 = g * vol_mult * 14 / 365.0
        tier = max(i for i, t in enumerate(TIERS) if v14 >= t[0])
        tk = TIERS[tier][1] * 100 * (1 - REF_DISC)   # bp, with the account's referral disc
        tier_tbl[str(g)] = {
            "volume_14d_usd": v14, "volume_yr_usd": g * vol_mult,
            "tier": tier, "taker_bp_after_referral_disc": tk,
            "round_trip_taker_bp": 2 * tk,
            "vs_today_rt_bp": 2 * tk - 2 * TAKER_BP_T0 * (1 - REF_DISC),
        }
    thresh = {}
    for i, (v, tk, mk) in enumerate(TIERS[1:4], start=1):
        thresh[f"tier{i}_at_14d_vol_{v:,.0f}"] = {
            "gross_notional_needed_usd": v / (vol_mult * 14 / 365.0),
            "taker_bp": tk * 100 * (1 - REF_DISC),
            "rt_saving_vs_tier0_bp": 2 * (TIERS[0][1] - tk) * 100 * (1 - REF_DISC),
            "rt_saving_pct_of_notional_per_yr":
                2 * (TIERS[0][1] - tk) * 100 * (1 - REF_DISC) / 1e4 * TRADES_PER_YR * 100,
        }
    out["F_volume_tiers"] = {
        "annual_volume_per_dollar_of_gross_notional": vol_mult,
        "basis": "pullback leg only (0.75 weight, 45.667 round trips/yr measured). "
                 "The trend leg adds turnover, so tiers arrive SOONER than this.",
        "by_gross_notional": tier_tbl, "thresholds": thresh,
        "live_rates_measured": {"taker_bp": TAKER_BP_T0 * (1 - REF_DISC),
                                "maker_bp": 1.5 * (1 - REF_DISC)},
    }

    with open(os.path.join(OUTDIR, "twap.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
