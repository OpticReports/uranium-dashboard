"""CANDIDATE D: does fixing execution + carry really buy size?

Phase 1 (edge-headroom) measured the FEE channel only and got 1.45x, while
flagging its own open question: the Alo-rejected entries filled at our limit
or better, so "only the fee changes" is an assumption, not a measurement.

This script closes that gap by re-basing the whole book from SPOT space (what
the backtest measures) into PERP space (what the account actually trades), and
then adds funding on BOTH legs -- phase 1 measured the pullback leg only and
explicitly refused to guess the trend leg, which holds 92.7% of bars.

Three bases, same trades, same fees:
  SPOT           what every published number in this repo is measured on
  PERP           + the measured spot/perp basis change over each hold
  PERP+FUNDING   + hourly funding paid/received on both legs

Run: python3 research/scale/candD_perp_space.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay                         # noqa: E402
from app.engine.kelly import analyze                             # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,         # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
PERP = os.path.join(HERE, "candD_perp_4h.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
OUT = os.path.join(HERE, "candD_perp_space.json")

EQUITY, REF_LEV, W_TREND = 100_055.0, 1.5, 0.25
TAKER, MAKER = 4.32, 1.44          # bps per side, live userFees + 4% referral

P_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S3"]
T_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S4"]


def load_bars() -> list[Bar]:
    out = []
    with open(BARS) as f:
        for r in csv.DictReader(f):
            out.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                           high=float(r["high"]), low=float(r["low"]),
                           close=float(r["close"]), volume=float(r["volume"])))
    return out


def load_basis() -> tuple[dict[int, float], dict[int, float]]:
    """ts -> basis as a FRACTION (perp/spot - 1), at close and at open."""
    bc, bo = {}, {}
    with open(PERP) as f:
        for r in csv.DictReader(f):
            ts = int(r["ts"])
            bc[ts] = float(r["basis_close_bps"]) / 1e4
            bo[ts] = float(r["basis_open_bps"]) / 1e4
    return bc, bo


def load_funding() -> tuple[list[int], list[float]]:
    ts, rate = [], []
    with open(FUND) as f:
        for r in csv.DictReader(f):
            ts.append(int(r["ts_ms"]) // 1000)
            rate.append(float(r["funding_rate_1h"]))
    order = sorted(range(len(ts)), key=lambda i: ts[i])
    ts = [ts[i] for i in order]
    rate = [rate[i] for i in order]
    pre = [0.0]
    for x in rate:
        pre.append(pre[-1] + x)
    return ts, pre


def funding_sum(fts: list[int], pre: list[float], t0: int, t1: int) -> float:
    """Sum of hourly funding rates stamped in (t0, t1]."""
    i = bisect.bisect_right(fts, t0)
    j = bisect.bisect_right(fts, t1)
    return pre[j] - pre[i]


def leg_trades(books, rt_bps: float, start_ts: int, bars):
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt_bps / 2.0)
    r = run_replay(bars, books, RESEARCH_SIGNAL, tc, start_ts=start_ts,
                   cash_apy=0.0)
    return r.books[books[0].name].trades


def pct(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs); i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def rebase(trades, bc, bo, fts, pre, exit_basis="close"):
    """Per-trade fractional equity returns in each basis, plus diagnostics."""
    rows = []
    for t in trades:
        b0 = bc.get(t.signal_ts)          # limit priced at the SIGNAL close
        b1 = (bc if exit_basis == "close" else bo).get(t.exit_ts)
        if b0 is None or b1 is None:
            continue
        sgn = 1.0 if t.side == "L" else -1.0
        # gross directional spot return on notional, before fees
        g = sgn * (t.exit_price - t.entry_price) / t.entry_price
        fee_frac = t.fees_usd / t.notional
        net_spot = g - fee_frac
        # exact perp transform: both prices translate by their own basis
        ratio = (t.exit_price * (1 + b1)) / (t.entry_price * (1 + b0))
        g_perp = (ratio - 1) if t.side == "L" else (1 - ratio)
        net_perp = g_perp - fee_frac
        # funding: long PAYS positive funding, short RECEIVES
        fr = funding_sum(fts, pre, t.entry_ts, t.exit_ts)
        fund_frac = -sgn * fr
        lev_i = t.notional / t.equity_before
        rows.append({
            "book": t.book, "side": t.side, "signal_ts": t.signal_ts,
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
            "exit_reason": t.exit_reason, "bars_held": t.bars_held,
            "hold_hours": (t.exit_ts - t.entry_ts) / 3600.0,
            "notional_over_equity": lev_i,
            "basis_entry_bps": b0 * 1e4, "basis_exit_bps": b1 * 1e4,
            "basis_drag_bps": (net_perp - net_spot) * 1e4,
            "funding_bps": fund_frac * 1e4,
            "funding_rate_sum": fr,
            "r_spot": net_spot * lev_i,
            "r_perp": net_perp * lev_i,
            "r_perp_fund": (net_perp + fund_frac) * lev_i,
            "engine_pnl_pct": t.pnl_pct,
            "check_net_spot_pct": net_spot * 100.0,
        })
    return rows


def blend(p_rows, t_rows, key, lev=REF_LEV, w_trend=W_TREND):
    evs = sorted([(r["exit_ts"], "P", r[key]) for r in p_rows]
                 + [(r["exit_ts"], "T", r[key]) for r in t_rows])
    return [lev * v * ((1 - w_trend) if w == "P" else w_trend)
            for _, w, v in evs]


def main() -> None:
    bars = load_bars()
    bc, bo = load_basis()
    fts, pre = load_funding()
    overlap_lo, overlap_hi = min(bc), max(bc)
    print(f"basis overlap: {overlap_lo} -> {overlap_hi} ({len(bc)} bars)")

    res = {"window_unix": [overlap_lo, overlap_hi],
           "taker_bps_per_side": TAKER, "maker_bps_per_side": MAKER}

    # ---- integrity check: reproduce the engine's own pnl_pct from prices ----
    p_all = leg_trades(P_BOOKS, 2 * TAKER, overlap_lo, bars)
    t_all = leg_trades(T_BOOKS, 2 * TAKER, overlap_lo, bars)
    print(f"trades in window: S3 pullback {len(p_all)}, S4 trend {len(t_all)}")

    p_rows = rebase(p_all, bc, bo, fts, pre)
    t_rows = rebase(t_all, bc, bo, fts, pre)
    print(f"rebased (both ends inside basis window): "
          f"S3 {len(p_rows)}, S4 {len(t_rows)}")
    chk = [abs(r["engine_pnl_pct"] - r["check_net_spot_pct"])
           for r in p_rows + t_rows]
    res["integrity_max_abs_pnl_pct_diff"] = max(chk) if chk else None
    print(f"CHECK reconstructed pnl_pct vs engine: max abs diff "
          f"{max(chk):.3e} pct-points")

    # ---------------- basis + funding descriptive ----------------
    for nm, rows in (("pullback_S3", p_rows), ("trend_S4", t_rows)):
        bd = [r["basis_drag_bps"] for r in rows]
        fd = [r["funding_bps"] for r in rows]
        hh = [r["hold_hours"] for r in rows]
        shorts = sum(1 for r in rows if r["side"] == "S")
        res[nm] = {
            "n": len(rows), "n_short": shorts,
            "short_frac": shorts / len(rows) if rows else None,
            "mean_hold_hours": sum(hh) / len(hh) if hh else None,
            "total_hold_hours": sum(hh),
            "basis_drag_bps": {"mean": sum(bd) / len(bd), "median": pct(bd, .5),
                               "sd": (sum((x - sum(bd)/len(bd))**2 for x in bd)
                                      / (len(bd) - 1)) ** .5,
                               "p10": pct(bd, .1), "p90": pct(bd, .9),
                               "min": min(bd), "max": max(bd)},
            "funding_bps": {"mean": sum(fd) / len(fd), "median": pct(fd, .5),
                            "sd": (sum((x - sum(fd)/len(fd))**2 for x in fd)
                                   / (len(fd) - 1)) ** .5,
                            "p10": pct(fd, .1), "p90": pct(fd, .9),
                            "min": min(fd), "max": max(fd),
                            "total_bps_of_notional": sum(fd)},
        }
        print(f"\n{nm}: n={len(rows)} short={shorts} "
              f"mean_hold={sum(hh)/len(hh):.1f}h")
        print(f"  basis drag  mean {sum(bd)/len(bd):+7.3f} bps  "
              f"sd {res[nm]['basis_drag_bps']['sd']:6.2f}  "
              f"p10 {pct(bd,.1):+7.2f}  p90 {pct(bd,.9):+7.2f}")
        print(f"  funding     mean {sum(fd)/len(fd):+7.3f} bps  "
              f"sd {res[nm]['funding_bps']['sd']:6.2f}  "
              f"p10 {pct(fd,.1):+7.2f}  p90 {pct(fd,.9):+7.2f}")

    # annualised funding as % of notional, per leg and blended
    YEARS = (overlap_hi - overlap_lo) / (365.25 * 86400)
    res["years_in_window"] = YEARS
    for nm, rows, w in (("pullback_S3", p_rows, 1 - W_TREND),
                        ("trend_S4", t_rows, W_TREND)):
        tot = sum(r["funding_bps"] for r in rows) / 1e4
        res[nm]["funding_pct_of_notional_per_year"] = tot / YEARS * 100
        res[nm]["funding_weighted_pct_gross_per_year"] = tot / YEARS * 100 * w
    res["funding_blend_pct_of_gross_per_year"] = (
        res["pullback_S3"]["funding_weighted_pct_gross_per_year"]
        + res["trend_S4"]["funding_weighted_pct_gross_per_year"])
    print(f"\nFUNDING, annualised over {YEARS:.2f}y in window:")
    print(f"  pullback leg {res['pullback_S3']['funding_pct_of_notional_per_year']:+.4f}%/yr of ITS notional")
    print(f"  trend leg    {res['trend_S4']['funding_pct_of_notional_per_year']:+.4f}%/yr of ITS notional")
    print(f"  BLEND        {res['funding_blend_pct_of_gross_per_year']:+.4f}%/yr of GROSS notional")

    # ---------------- Kelly across the three bases ----------------
    res["bases"] = {}
    for key, label in (("r_spot", "SPOT (the backtest's basis)"),
                       ("r_perp", "PERP (basis-adjusted)"),
                       ("r_perp_fund", "PERP + FUNDING")):
        s = blend(p_rows, t_rows, key)
        A = analyze(s, f"S5|{label}")
        auth = A["recommended_m"] * REF_LEV * EQUITY
        res["bases"][key] = {
            "label": label, "n_steps": A["n"],
            "mean_step": float(sum(s) / len(s)),
            "sd_step": float((sum((x - sum(s)/len(s))**2 for x in s)
                              / (len(s) - 1)) ** .5),
            "kelly_m": A["kelly_m"], "recommended_m": A["recommended_m"],
            "half_kelly_m": A["half_kelly_m"],
            "conservative_m": A["conservative_m"],
            "p10": A["bootstrap"]["p10"],
            "prob_negative_edge": A["bootstrap"]["prob_negative_edge"],
            "dd30": A["dd_constrained"]["p_maxdd30_le_10pct"],
            "verdict": A["verdict"], "authorised_gross_usd": auth,
        }
        print(f"\n{label}: n={A['n']} mean={sum(s)/len(s)*100:.4f}% "
              f"sd={res['bases'][key]['sd_step']*100:.4f}% "
              f"kelly_m={A['kelly_m']} p10={A['bootstrap']['p10']} "
              f"dd30={A['dd_constrained']['p_maxdd30_le_10pct']} "
              f"rec_m={A['recommended_m']} -> ${auth:,.0f}")

    # ---------------- exit-basis sensitivity ----------------
    p_o = rebase(p_all, bc, bo, fts, pre, exit_basis="open")
    t_o = rebase(t_all, bc, bo, fts, pre, exit_basis="open")
    s_o = blend(p_o, t_o, "r_perp_fund")
    A_o = analyze(s_o, "S5|perp+fund|exit basis at OPEN")
    res["exit_basis_open_variant"] = {
        "recommended_m": A_o["recommended_m"],
        "authorised_gross_usd": A_o["recommended_m"] * REF_LEV * EQUITY,
        "mean_step": float(sum(s_o) / len(s_o))}
    print(f"\nexit-basis sensitivity (open instead of close): "
          f"rec_m {A_o['recommended_m']} -> "
          f"${A_o['recommended_m']*REF_LEV*EQUITY:,.0f}")

    with open(OUT, "w") as f:
        json.dump({"result": res,
                   "pullback_rows": p_rows, "trend_rows": t_rows}, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
