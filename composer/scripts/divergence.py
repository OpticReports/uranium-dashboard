#!/usr/bin/env python3
"""Live-vs-backtest divergence for an invested symphony.

Compares the deposit-adjusted live curve (what your money actually did) with
a fresh backtest of the same symphony over the same dates (what the strategy
"should" have done). Persistent negative daily gaps = implementation
shortfall: slippage, rebalance-timing, fees beyond the model.

Read-only. Usage:
  divergence.py <symphony-id> [--account UUID] [--name divergence-<x>]
  divergence.py --all          # every invested symphony
"""

import argparse
import composerlib as cl


def analyze(acct, sym_id, sym_name):
    pos = cl.get(f"/portfolio/accounts/{acct}/symphonies/{sym_id}")
    dates = [cl.epoch_ms_to_date(ms).isoformat() for ms in pos["epoch_ms"]]
    live_vals = pos.get("deposit_adjusted_series") or pos["series"]
    live = dict(zip(dates, live_vals))
    if len(live) < 5:
        return {"symphony": sym_id, "name": sym_name,
                "error": f"only {len(live)} live days — too new to compare"}

    bt = cl.backtest_by_id(sym_id, start=dates[0], end=dates[-1])
    days, vals = cl.equity_curve(bt)
    model = {cl.epoch_day_to_date(d).isoformat(): v for d, v in zip(days, vals)}

    common = sorted(set(live) & set(model))
    if len(common) < 5:
        return {"symphony": sym_id, "name": sym_name,
                "error": f"only {len(common)} overlapping days"}

    lv = [live[d] for d in common]
    mv = [model[d] for d in common]
    lr = cl.returns_from_curve(lv)
    mr = cl.returns_from_curve(mv)
    gaps = [a - b for a, b in zip(lr, mr)]  # live minus model, daily

    live_cum = lv[-1] / lv[0] - 1.0
    model_cum = mv[-1] / mv[0] - 1.0
    n = len(gaps)
    mean_gap = sum(gaps) / n
    return {
        "symphony": sym_id, "name": sym_name,
        "window": [common[0], common[-1]], "n_days": n,
        "live_cumulative_return": round(live_cum, 4),
        "model_cumulative_return": round(model_cum, 4),
        "cumulative_gap": round(live_cum - model_cum, 4),
        "mean_daily_gap_bps": round(mean_gap * 1e4, 2),
        "annualized_gap": round(mean_gap * 252, 4),
        "worst_daily_gap_bps": round(min(gaps) * 1e4, 1),
        "best_daily_gap_bps": round(max(gaps) * 1e4, 1),
        "daily_return_correlation": round(cl.pearson(lr, mr) or 0.0, 3),
        # earn-back fat-tail detectors (results.md addendum 21): live beta to
        # model, live/model vol ratio, and live max drawdown over the window
        "live_beta_to_model": round(_beta(lr, mr), 3),
        "live_model_vol_ratio": round(_vol_ratio(lr, mr), 3),
        "live_max_drawdown": round(cl.max_drawdown(lv), 4),
    }


def _beta(lr, mr):
    n = len(mr)
    if n < 3:
        return 0.0
    ma = sum(lr) / n
    mb = sum(mr) / n
    var = sum((y - mb) ** 2 for y in mr) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(lr, mr)) / n
    return cov / var if var else 0.0


def _vol_ratio(lr, mr):
    import statistics
    sm = statistics.pstdev(mr)
    return statistics.pstdev(lr) / sm if sm else 0.0


def show(r):
    print(f"  {r['name'][:60]} [{r['symphony'][:8]}]")
    if "error" in r:
        print(f"      {r['error']}")
        return
    print(f"      window {r['window'][0]} .. {r['window'][1]} ({r['n_days']} days)")
    print(f"      cumulative: live {r['live_cumulative_return']:+7.2%}  "
          f"model {r['model_cumulative_return']:+7.2%}  "
          f"gap {r['cumulative_gap']:+7.2%}")
    print(f"      beta {r['live_beta_to_model']:.2f}  vol-ratio "
          f"{r['live_model_vol_ratio']:.2f}  live maxDD {r['live_max_drawdown']:.1%}")
    print(f"      daily gap: mean {r['mean_daily_gap_bps']:+6.1f} bps "
          f"(~{r['annualized_gap']:+.1%}/yr)  "
          f"range [{r['worst_daily_gap_bps']:+.0f}, {r['best_daily_gap_bps']:+.0f}] bps")
    print(f"      daily return correlation live~model: {r['daily_return_correlation']:+.3f}"
          + ("   <- LOW: check rebalance timing/fills"
             if abs(r["daily_return_correlation"]) < 0.9 else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("symphony_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--account")
    p.add_argument("--name", default="divergence")
    a = p.parse_args()
    if not a.all and not a.symphony_id:
        raise SystemExit("error: pass a symphony id or --all")

    acct = a.account or cl.default_account()
    meta = {s["id"]: s["name"] for s in
            cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]}
    targets = list(meta) if a.all else [a.symphony_id]

    results = []
    print("live vs backtest divergence (deposit-adjusted)\n")
    for sid in targets:
        if sid not in meta:
            raise SystemExit(f"error: {sid} is not an invested symphony in this account")
        r = analyze(acct, sid, meta[sid])
        results.append(r)
        show(r)

    cl.write_json(f"composer/results/{a.name}.json", {"results": results})


if __name__ == "__main__":
    main()
