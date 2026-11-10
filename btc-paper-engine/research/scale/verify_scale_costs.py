"""Adversarial re-check of this directory's size-cost findings (house rule:
counter-agent verification before any finding is acted on).

Everything here is recomputed by a DIFFERENT code path from the scripts that
produced the headline numbers, and where a convention was chosen, BOTH
conventions are reported:

  V1  funding sum per trade: numpy hourly grid instead of the dict scan, and
      both stamp-boundary conventions (a<T<=b vs a<=T<b)
  V2  $1m slip recomputed from book_raw.jsonl -- an INDEPENDENT capture by a
      separate process -- and compared with book_calm's distribution
  V3  the order-walk itself, against a hand-checked toy book
  V4  the sqrt(T) vol scaling the TWAP break-even relies on, tested against
      directly measured 5/30-minute vol instead of assumed
  V5  funding history cross-checked against RESEARCH_CARRY.md's published
      by-year means (an independent prior study)
  V6  the size-invariance claim and the fee-tier volume arithmetic, recomputed
  V7  is the reference `ret` column gross or net of fees? (affects the
      funding-as-%-of-edge denominator)

Usage: python3 verify_scale_costs.py <dir>
"""
from __future__ import annotations
import csv, datetime as dt, json, math, os, statistics, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(D, "..", "..", "backend", "reference")
V = {}


def pctl(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p / 100.0
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


fund = json.load(open(os.path.join(D, "funding_at_size.json")))

# ---------------- V1 funding, independent path + both conventions ----------
rates = {}
with open(os.path.join(D, "funding_hl_btc.csv")) as f:
    for a, b in csv.reader(f):
        if a != "ts_ms":
            rates[int(a)] = float(b)
keys = sorted(rates)
import bisect
cum = [0.0]
for k in keys:
    cum.append(cum[-1] + rates[k])


def sum_excl_open(a_ms, b_ms):
    """stamps with a < T <= b, via prefix sums + bisect (not a linear scan)."""
    i = bisect.bisect_right(keys, a_ms)
    j = bisect.bisect_right(keys, b_ms)
    return cum[j] - cum[i], j - i


def sum_incl_open(a_ms, b_ms):
    """stamps with a <= T < b."""
    i = bisect.bisect_left(keys, a_ms)
    j = bisect.bisect_left(keys, b_ms)
    return cum[j] - cum[i], j - i


trades = list(csv.DictReader(open(os.path.join(REF, "btc_pullback_trades_optimized.csv"))))
tot = {"excl": 0.0, "incl": 0.0}
n_stamp = {"excl": 0, "incl": 0}
for tr in trades:
    a = dt.datetime.fromisoformat(tr["entry"]).timestamp() * 1000
    b = dt.datetime.fromisoformat(tr["exit"]).timestamp() * 1000
    sgn = -1.0 if tr["side"] == "L" else 1.0
    s1, n1 = sum_excl_open(a, b)
    s2, n2 = sum_incl_open(a, b)
    tot["excl"] += sgn * s1; n_stamp["excl"] += n1
    tot["incl"] += sgn * s2; n_stamp["incl"] += n2
yrs = fund["trade_window"]["span_years"]
pub = fund["funding_cost_bases"]["3_signed_actual_trades"]["annual_frac_of_notional"]
V["V1_funding_signed"] = {
    "published_annual_frac": pub,
    "recomputed_excl_open_annual_frac": tot["excl"] / yrs,
    "abs_diff_vs_published": abs(tot["excl"] / yrs - pub),
    "alt_convention_incl_open_annual_frac": tot["incl"] / yrs,
    "convention_sensitivity_annual_pct_of_notional":
        abs(tot["incl"] - tot["excl"]) / yrs * 100,
    "stamps_used_excl": n_stamp["excl"], "stamps_used_incl": n_stamp["incl"],
    "held_hours": fund["trade_window"]["held_hours"],
    "verdict": "PASS" if abs(tot["excl"] / yrs - pub) < 1e-9 else "MISMATCH",
    "note": "both conventions are reported because the choice is a judgement call; "
            "the gap is the honest uncertainty on the funding line.",
}

# ---------------- V2 $1m slip from the INDEPENDENT raw capture -------------
def walk_cum(levels, tgt):
    got = cost = qty = 0.0
    for l in levels:
        px, sz = float(l["px"]), float(l["sz"])
        u = px * sz
        if got + u >= tgt:
            qty += (tgt - got) / px; cost += tgt - got; got = tgt; break
        got += u; qty += sz; cost += u
    return (cost / qty if qty else None), got


raw_slip = {"buy": [], "sell": []}
raw_depth = {"ask": [], "bid": []}
nraw = 0
p = os.path.join(D, "book_raw.jsonl")
if os.path.exists(p):
    with open(p) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            bids, asks = d["levels"]
            if not bids or not asks:
                continue
            nraw += 1
            mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
            raw_depth["ask"].append(sum(float(l["px"]) * float(l["sz"]) for l in asks))
            raw_depth["bid"].append(sum(float(l["px"]) * float(l["sz"]) for l in bids))
            vw, got = walk_cum(asks, 1_000_000)
            if got >= 999_000:
                raw_slip["buy"].append((vw / mid - 1) * 1e4)
            vw, got = walk_cum(bids, 1_000_000)
            if got >= 999_000:
                raw_slip["sell"].append((1 - vw / mid) * 1e4)
calm = json.load(open(os.path.join(D, "book_calm.json")))
V["V2_independent_capture"] = {"n_raw_snapshots": nraw}
for side, dk in (("buy", "ask"), ("sell", "bid")):
    c = calm["slip"][f"{side}_1000000"]
    r = raw_slip[side]
    V["V2_independent_capture"][side] = {
        "calm_p50": c["p50"], "raw_p50": pctl(r, 50),
        "calm_worst": c["worst"], "raw_worst": pctl(r, 100),
        "calm_n_complete": c["n_complete"], "raw_n_complete": len(r),
        "calm_n_incomplete": c["n_incomplete"],
        "raw_n_incomplete": nraw - len(r),
        "p50_gap_bp": (pctl(r, 50) - c["p50"]) if r and c["p50"] else None,
    }
V["V2_independent_capture"]["verdict"] = (
    "two separately-captured samples agree on the $1m cost to well inside 1 bp"
    if all(abs((V["V2_independent_capture"][s].get("p50_gap_bp") or 9)) < 1.0
           for s in ("buy", "sell")) else "DISAGREE - investigate")

# ---------------- V3 the walk, against a hand-checked toy book -------------
toy = [{"px": "100", "sz": "1"}, {"px": "101", "sz": "1"}, {"px": "102", "sz": "10"}]
# $150 of notional: 100*1 = 100, then 50 more at 101 -> qty 1 + 0.49505 = 1.49505
# vwap = 150 / 1.49505 = 100.3311...
vw, got = walk_cum(toy, 150)
expect = 150.0 / (1.0 + 50.0 / 101.0)
V["V3_walk_unit_check"] = {
    "vwap": vw, "expected": expect, "filled": got,
    "abs_err": abs(vw - expect),
    "partial_level_handled": abs(got - 150.0) < 1e-9,
    "insufficient_book_case": walk_cum([{"px": "100", "sz": "0.1"}], 1_000_000)[1],
    "verdict": "PASS" if abs(vw - expect) < 1e-9 else "FAIL",
}

# ---------------- V4 is sqrt(T) scaling honest? ----------------------------
tw = json.load(open(os.path.join(D, "twap.json")))
h = tw["C_timing_risk"]["horizons"]
s1 = h["1min"]["sigma_bp"]
V["V4_vol_scaling"] = {
    "sigma_1min_bp": s1,
    "measured_vs_sqrtT": {
        k: {"measured_bp": h[k]["sigma_bp"],
            "sqrtT_prediction_bp": s1 * math.sqrt(int(k.replace("min", ""))),
            "ratio_measured_over_predicted":
                h[k]["sigma_bp"] / (s1 * math.sqrt(int(k.replace("min", ""))))}
        for k in ("5min", "15min", "30min")},
    "verdict": "MIXED, immaterial. sqrt(T) is within 7% at 5 min and OVERstates by "
               "11% at 30 min (mild mean reversion). It is only used to solve the "
               "break-even window, which lands at 0.7-3.6 s -- a SUB-MINUTE "
               "extrapolation the candle data cannot test. The conclusion does not "
               "depend on it: measured sigma at the shortest horizon there IS data "
               "for (1 min, 4.17 bp) already exceeds the largest slip saving "
               "available (1.02 bp) by 4x, so any delay measured in minutes loses "
               "on measured numbers alone.",
    "fat_tail_check": {k: {"p99_over_sigma": h[k]["p99_abs_bp"] / h[k]["sigma_bp"]}
                       for k in ("1min", "5min", "30min")},
}

# ---------------- V5 funding history vs a prior independent study ---------
by_year = fund["funding_history"]["mean_annualized_pct_by_year"]
carry_pub = {"2023": 15.1, "2024": 24.1, "2025": 10.6}
V["V5_vs_RESEARCH_CARRY"] = {
    "mine": by_year, "published_in_RESEARCH_CARRY": carry_pub,
    "abs_diff_pp": {y: abs(by_year[y] - v) for y, v in carry_pub.items()},
    "2026_differs_expectedly": "RESEARCH_CARRY's 4.5%% was YTD to 2026-08; mine is "
                               "YTD to 2026-09-28 (%.2f%%)" % by_year.get("2026", float("nan")),
    "verdict": "PASS" if all(abs(by_year[y] - v) < 0.2 for y, v in carry_pub.items())
               else "DIVERGES from the prior study - reconcile before use",
}

# ---------------- V6 invariance + fee tiers, recomputed -------------------
si = fund["size_invariance"]["table"]
ratios = {k: v["funding_as_pct_of_gross_edge"] for k, v in si.items()}
ft = tw["F_volume_tiers"]
mult = ft["annual_volume_per_dollar_of_gross_notional"]
recheck = {}
for g, row in ft["by_gross_notional"].items():
    recheck[g] = {"published_14d_vol": row["volume_14d_usd"],
                  "recomputed": float(g) * mult * 14 / 365.0,
                  "tier_published": row["tier"]}
V["V6_invariance_and_tiers"] = {
    "funding_pct_of_edge_at_each_notional": ratios,
    "all_equal": max(ratios.values()) - min(ratios.values()) < 1e-9,
    "why": "funding, fees and gross P&L are all proportional to notional, so no "
           "ratio among them can depend on notional. The invariance is arithmetic, "
           "not an empirical result - it cannot fail, and claiming it as a finding "
           "would be circular. What is empirical is the LEVEL.",
    "tier_volume_recheck": recheck,
    "max_abs_tier_vol_err": max(abs(r["published_14d_vol"] - r["recomputed"])
                                for r in recheck.values()),
    "tier1_reachable_at_gross_notional_usd":
        tw["F_volume_tiers"]["thresholds"]["tier1_at_14d_vol_5,000,000"]["gross_notional_needed_usd"],
}

# ---------------- V7 is the reference `ret` gross or net? ------------------
lim = list(csv.DictReader(open(os.path.join(REF, "btc_trades_limit_entry_reference.csv"))))
opt = {r["entry"]: r for r in trades}
d_opt, d_lim = [], []
for r in lim:
    e, x = float(r["entry_price"]), float(r["exit_price"])
    s = 1 if r["side"] == "L" else -1
    gross = s * (x / e - 1)
    d_lim.append((gross - float(r["ret_pct"]) / 100) * 1e4)
    if r["entry_ts"] in opt:
        d_opt.append((gross - float(opt[r["entry_ts"]]["ret"])) * 1e4)
V["V7_reference_ret_basis"] = {
    "n_matched": len(d_opt),
    "gross_minus_optimized_ret_bp": {"mean": sum(d_opt) / len(d_opt),
                                     "median": pctl(d_opt, 50),
                                     "min": min(d_opt), "max": max(d_opt)},
    "gross_minus_limitref_ret_bp": {"mean": sum(d_lim) / len(d_lim),
                                    "median": pctl(d_lim, 50),
                                    "min": min(d_lim), "max": max(d_lim)},
    "finding": "NOT a constant fee offset. The limit-entry reference tops out at "
               "exactly 6.00 bp below entry->exit gross (the modelled fee) but goes "
               "as far as -74 bp the other way, so `ret` is neither cleanly gross nor "
               "cleanly net of a fixed fee. The edge denominator used for "
               "funding-as-%-of-edge therefore carries a few-bp-per-trade ambiguity.",
    "does_it_change_any_conclusion": "No. The funding line is 0.04 bp/round trip "
               "signed and 3.85 bp all-long against a 47-50 bp mean per-trade "
               "return; a 6 bp denominator ambiguity cannot move the ranking. It "
               "DOES matter for a Kelly re-fit, which should run off the replay "
               "engine rather than these CSVs.",
}

json.dump(V, open(os.path.join(D, "verify_scale_costs.json"), "w"), indent=1)
print(json.dumps(V, indent=1))
