#!/usr/bin/env python3
"""Correlation & allocation report across symphonies.

Two data sources, combinable:
  - invested symphonies (default): live deposit-adjusted daily curves from
    the portfolio endpoints — what your money actually did.
  - --ids sid1,sid2,...: any saved/public symphonies via fresh backtests
    (longer history, but in-sample).

Reports pairwise return correlations, per-strategy vol/CAGR/max-DD, and
inverse-volatility weights (a simple risk-balanced allocation). Report only —
it never moves capital; pair with composer-api.py transfer (guarded) if you
decide to act on it.

Usage:
  correlation.py                    # invested symphonies, live curves
  correlation.py --ids A,B,C        # arbitrary symphonies, backtest curves
  correlation.py --ids A,B --start 2023-01-01 [--name my-report]
"""

import argparse
import composerlib as cl


def live_series(acct):
    meta = cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]
    out = {}
    for s in meta:
        pos = cl.get(f"/portfolio/accounts/{acct}/symphonies/{s['id']}")
        dates = [cl.epoch_ms_to_date(ms).isoformat() for ms in pos["epoch_ms"]]
        vals = pos.get("deposit_adjusted_series") or pos["series"]
        label = f"{s['name'][:40]} [{s['id'][:8]}]"
        out[label] = dict(zip(dates, vals))
    return out


def backtest_series(ids, start, end):
    out = {}
    for sid in ids:
        bt = cl.backtest_by_id(sid, start=start, end=end)
        days, vals = cl.equity_curve(bt)
        name = next(iter(bt.get("legend", {}).values()), {}).get("name", sid)
        label = f"{name[:40]} [{sid[:8]}]"
        out[label] = {cl.epoch_day_to_date(d).isoformat(): v
                      for d, v in zip(days, vals)}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ids", help="comma-separated symphony ids (backtest mode)")
    p.add_argument("--account")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--name", default="correlation")
    a = p.parse_args()

    series = {}
    if a.ids:
        series.update(backtest_series([s.strip() for s in a.ids.split(",")],
                                      a.start, a.end))
    else:
        series.update(live_series(a.account or cl.default_account()))
    if len(series) < 2:
        raise SystemExit(f"need >=2 series to correlate, got {len(series)}")

    labels = list(series)
    common = set.intersection(*(set(s) for s in series.values()))
    dates = sorted(common)
    if len(dates) < 20:
        raise SystemExit(
            f"only {len(dates)} overlapping days — not enough. If a symphony "
            "was invested recently, use --ids to correlate backtest curves instead.")

    rets = {}
    for lb in labels:
        vals = [series[lb][d] for d in dates]
        rets[lb] = cl.returns_from_curve(vals)

    print(f"correlation report — {len(labels)} strategies, "
          f"{len(dates)} common days ({dates[0]} .. {dates[-1]})\n")

    stats = {}
    for lb in labels:
        vals = [series[lb][d] for d in dates]
        stats[lb] = cl.curve_stats(vals)
        s = stats[lb]
        print(f"  {lb}")
        print(f"      cagr {s['cagr']:+8.1%}  vol {s['ann_vol']:6.1%}  "
              f"sharpe {s['sharpe']:5.2f}  max dd {s['max_drawdown']:6.1%}")

    print("\ncorrelation matrix (daily returns):")
    header = "      " + "  ".join(f"[{i}]" for i in range(len(labels)))
    print(header)
    matrix = {}
    for i, li in enumerate(labels):
        row = []
        for j, lj in enumerate(labels):
            c = 1.0 if i == j else cl.pearson(rets[li], rets[lj])
            row.append(c)
            matrix[f"{li}|{lj}"] = None if c is None else round(c, 3)
        cells = "  ".join(f"{c:+.2f}" if c is not None else "  n/a" for c in row)
        print(f"  [{i}] {cells}   {li}")

    inv = {lb: (1.0 / stats[lb]["ann_vol"]) if stats[lb]["ann_vol"] else 0.0
           for lb in labels}
    total = sum(inv.values())
    weights = {lb: round(v / total, 4) for lb, v in inv.items()}
    print("\ninverse-volatility weights (risk-balanced allocation):")
    for lb, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"  {w:6.1%}  {lb}")
    print("\n(report only — any reallocation goes through the guarded CLI, "
          "on explicit request)")

    cl.write_json(f"composer/results/{a.name}.json",
                  {"dates": [dates[0], dates[-1]], "n_days": len(dates),
                   "stats": stats, "correlations": matrix,
                   "inverse_vol_weights": weights})


if __name__ == "__main__":
    main()
