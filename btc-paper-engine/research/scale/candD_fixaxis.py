"""CANDIDATE D: the size multiple, measured on the basis the account trades.

Phase 1 measured the fee axis on SPOT-space returns and got 1.45x.  This
re-measures it on PERP+FUNDING returns -- the basis the money is actually made
on -- and adds the alternative fix nobody has priced: signal on the PERP bars
instead of the spot bars, which removes the basis drag at source.

Arms cross (fee vector) x (signal instrument).  The adverse-selection sweep
converts the one thing 4h bars cannot measure -- queue-level selection on a
resting order -- into a stated tolerance.

Run: python3 research/scale/candD_fixaxis.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze, SEED                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOT_BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
PERP_BARS = os.path.join(HERE, "candD_bars_4h_btcperp.csv")
BASIS = os.path.join(HERE, "candD_perp_4h.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
OUT = os.path.join(HERE, "candD_fixaxis.json")

EQUITY, REF_LEV, W_TREND = 100_055.0, 1.5, 0.25
TAKER, MAKER = 4.32, 1.44
LIVE_GROSS = 0.20 * REF_LEV * 50_000.0            # $15,000
MAX_NOTIONAL_USD = 20_000.0
P_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S3"]
T_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S4"]
SEEDS = [SEED, 11, 101, 1009, 20250101, 777, 4242, 31337, 90210, 5, 68, 2026]


def bars_from(path) -> list[Bar]:
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            out.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                           high=float(r["high"]), low=float(r["low"]),
                           close=float(r["close"]), volume=float(r["volume"])))
    return out


def load_basis():
    bc = {}
    with open(BASIS) as f:
        for r in csv.DictReader(f):
            bc[int(r["ts"])] = float(r["basis_close_bps"]) / 1e4
    return bc


def load_funding():
    ts, rate = [], []
    with open(FUND) as f:
        for r in csv.DictReader(f):
            ts.append(int(r["ts_ms"]) // 1000)
            rate.append(float(r["funding_rate_1h"]))
    o = sorted(range(len(ts)), key=lambda i: ts[i])
    ts = [ts[i] for i in o]; rate = [rate[i] for i in o]
    pre = [0.0]
    for x in rate:
        pre.append(pre[-1] + x)
    return ts, pre


def fsum(fts, pre, t0, t1):
    return pre[bisect.bisect_right(fts, t1)] - pre[bisect.bisect_right(fts, t0)]


def run_leg(bars, books, rt_bps, start_ts):
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt_bps / 2.0)
    return run_replay(bars, books, RESEARCH_SIGNAL, tc, start_ts=start_ts,
                      cash_apy=0.0).books[books[0].name].trades


def to_returns(trades, bc, fts, pre, apply_basis: bool):
    """Fractional equity return per trade, in perp space, with funding."""
    out = []
    for t in trades:
        sgn = 1.0 if t.side == "L" else -1.0
        fee_frac = t.fees_usd / t.notional
        if apply_basis:
            b0, b1 = bc.get(t.signal_ts), bc.get(t.exit_ts)
            if b0 is None or b1 is None:
                continue
            ratio = (t.exit_price * (1 + b1)) / (t.entry_price * (1 + b0))
        else:
            ratio = t.exit_price / t.entry_price
        g = (ratio - 1) if t.side == "L" else (1 - ratio)
        fund = -sgn * fsum(fts, pre, t.entry_ts, t.exit_ts)
        out.append((t.exit_ts, (g - fee_frac + fund) * t.notional / t.equity_before))
    return out


def blend(p, t, lev=REF_LEV, w=W_TREND):
    evs = sorted([(ts, "P", r) for ts, r in p] + [(ts, "T", r) for ts, r in t])
    return [lev * r * ((1 - w) if k == "P" else w) for _, k, r in evs]


def score(steps, seed=SEED):
    A = analyze(steps, "S5", seed=seed)
    return A


def main() -> None:
    spot, perp = bars_from(SPOT_BARS), bars_from(PERP_BARS)
    bc = load_basis(); fts, pre = load_funding()
    # SAME tradeable window for both instruments: the perp series needs its own
    # 210-bar warmup, so gate the spot run to the same first tradeable bar.
    start_ts = perp[210].ts
    print(f"common tradeable window starts {start_ts} "
          f"({len(perp)-210} perp bars available)")

    res = {"start_ts": start_ts, "equity": EQUITY, "live_gross": LIVE_GROSS,
           "taker_bps": TAKER, "maker_bps": MAKER, "seeds": SEEDS, "arms": []}

    # arm = (label, pullback round-trip bps, trend round-trip bps, instrument)
    arms = []
    for inst in ("spot_signal", "perp_signal"):
        arms += [
            (f"LIVE today: entry taker + exit taker", 2 * TAKER, 2 * TAKER, inst),
            (f"FIX 1: maker entry (pullback leg only)", MAKER + TAKER, 2 * TAKER, inst),
            (f"CEILING: pullback fully maker (not achievable)", 2 * MAKER, 2 * TAKER, inst),
        ]
    # adverse-selection sweep on FIX 1, spot signal
    for p in (0.0, 0.5, 1.0, 1.5, 2.0, 2.88, 4.0, 6.0):
        arms.append((f"FIX 1 + {p:.2f} bps adverse selection",
                     MAKER + p + TAKER, 2 * TAKER, "spot_signal_sweep"))

    cache: dict[tuple, list] = {}

    def steps_for(rt_p, rt_t, inst):
        key = (round(rt_p, 4), round(rt_t, 4), inst)
        if key in cache:
            return cache[key]
        use_perp_bars = inst.startswith("perp")
        bars = perp if use_perp_bars else spot
        pt = run_leg(bars, P_BOOKS, rt_p, start_ts)
        tt = run_leg(bars, T_BOOKS, rt_t, start_ts)
        pr = to_returns(pt, bc, fts, pre, apply_basis=not use_perp_bars)
        tr = to_returns(tt, bc, fts, pre, apply_basis=not use_perp_bars)
        s = blend(pr, tr)
        cache[key] = (s, len(pt), len(tt))
        return cache[key]

    print(f"\n{'arm':<52}{'inst':<13}{'n':>5}{'rec_m':>8}{'gross $':>12}{'x live':>8}")
    print("-" * 98)
    for label, rt_p, rt_t, inst in arms:
        s, n_p, n_t = steps_for(rt_p, rt_t, inst)
        A = score(s)
        auth = A["recommended_m"] * REF_LEV * EQUITY
        row = {"label": label, "instrument": inst, "pullback_rt_bps": rt_p,
               "trend_rt_bps": rt_t, "n_steps": A["n"],
               "n_pullback": n_p, "n_trend": n_t,
               "mean_step_pct": A["mean_pct"], "sd_step_pct": A["sd_pct"],
               "kelly_m": A["kelly_m"], "half_kelly_m": A["half_kelly_m"],
               "p10": A["bootstrap"]["p10"],
               "prob_negative_edge": A["bootstrap"]["prob_negative_edge"],
               "dd30_m": A["dd_constrained"]["p_maxdd30_le_10pct"],
               "conservative_m": A["conservative_m"],
               "recommended_m": A["recommended_m"],
               "authorised_gross_usd": auth,
               "x_live_gross": auth / LIVE_GROSS,
               "clamped_by_max_notional": auth > MAX_NOTIONAL_USD,
               "verdict": A["verdict"]}
        res["arms"].append(row)
        print(f"{label:<52}{inst:<13}{A['n']:>5}{A['recommended_m']:>8.2f}"
              f"{auth:>12,.0f}{auth/LIVE_GROSS:>8.2f}")

    # ---------- paired-seed test on the RATIO (level is seed-noisy) ----------
    print("\nPAIRED-SEED TEST on the FIX 1 / LIVE ratio (same seed both arms)")
    res["paired"] = {}
    for inst in ("spot_signal", "perp_signal"):
        s_live, _, _ = steps_for(2 * TAKER, 2 * TAKER, inst)
        s_fix, _, _ = steps_for(MAKER + TAKER, 2 * TAKER, inst)
        ratios, d_p10, lv, fx = [], [], [], []
        for sd in SEEDS:
            a = score(s_live, sd); b = score(s_fix, sd)
            lv.append(a["recommended_m"]); fx.append(b["recommended_m"])
            if a["recommended_m"] > 0:
                ratios.append(b["recommended_m"] / a["recommended_m"])
            d_p10.append(b["bootstrap"]["p10"] - a["bootstrap"]["p10"])
        if not ratios:
            res["paired"][inst] = {
                "n_seeds": len(SEEDS), "ratio_mean": None,
                "note": "LIVE arm recommended_m is 0.00 at every seed on this "
                        "instrument, so the ratio is undefined: there is no "
                        "authorised size to multiply.",
                "live_rec_m_range": [min(lv), max(lv)],
                "fix_rec_m_range": [min(fx), max(fx)]}
            print(f"  {inst:<12} LIVE rec_m is 0.00 at all {len(SEEDS)} seeds "
                  f"-> ratio undefined (no edge to scale)")
            continue
        res["paired"][inst] = {
            "n_seeds": len(SEEDS),
            "ratio_mean": statistics.fmean(ratios),
            "ratio_sd": statistics.stdev(ratios),
            "ratio_min": min(ratios), "ratio_max": max(ratios),
            "positive_of_n": sum(1 for r in ratios if r > 1.0),
            "d_p10_mean": statistics.fmean(d_p10),
            "d_p10_sd": statistics.stdev(d_p10),
            "d_p10_positive_of_n": sum(1 for d in d_p10 if d > 0),
            "live_rec_m_range": [min(lv), max(lv)],
            "fix_rec_m_range": [min(fx), max(fx)],
            "live_gross_range": [min(lv) * REF_LEV * EQUITY,
                                 max(lv) * REF_LEV * EQUITY],
            "fix_gross_range": [min(fx) * REF_LEV * EQUITY,
                                max(fx) * REF_LEV * EQUITY]}
        r = res["paired"][inst]
        print(f"  {inst:<12} ratio mean {r['ratio_mean']:.3f} "
              f"sd {r['ratio_sd']:.3f} range {r['ratio_min']:.2f}-"
              f"{r['ratio_max']:.2f} positive {r['positive_of_n']}/{len(SEEDS)}")
        print(f"               d_p10 mean {r['d_p10_mean']:+.4f} "
              f"sd {r['d_p10_sd']:.4f} positive "
              f"{r['d_p10_positive_of_n']}/{len(SEEDS)}  "
              f"t={r['d_p10_mean']/(r['d_p10_sd']/len(SEEDS)**.5):.1f}"
              if r["d_p10_sd"] > 0 else "               d_p10 sd 0")

    # ---------- spot-signal vs perp-signal, same fee ----------
    a_s = score(steps_for(2 * TAKER, 2 * TAKER, "spot_signal")[0])
    a_p = score(steps_for(2 * TAKER, 2 * TAKER, "perp_signal")[0])
    res["instrument_compare_live_fee"] = {
        "spot_signal_rec_m": a_s["recommended_m"],
        "perp_signal_rec_m": a_p["recommended_m"],
        "spot_signal_gross": a_s["recommended_m"] * REF_LEV * EQUITY,
        "perp_signal_gross": a_p["recommended_m"] * REF_LEV * EQUITY,
        "spot_mean_pct": a_s["mean_pct"], "perp_mean_pct": a_p["mean_pct"],
        "spot_sd_pct": a_s["sd_pct"], "perp_sd_pct": a_p["sd_pct"],
        "spot_n": a_s["n"], "perp_n": a_p["n"]}
    print(f"\nINSTRUMENT (live fee): spot-signal rec_m {a_s['recommended_m']} "
          f"(${a_s['recommended_m']*REF_LEV*EQUITY:,.0f}) vs perp-signal "
          f"{a_p['recommended_m']} (${a_p['recommended_m']*REF_LEV*EQUITY:,.0f})")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
