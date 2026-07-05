#!/usr/bin/env python3
"""Search public Composer symphonies and independently verify their stats.

The search endpoint returns each symphony's out-of-sample (OOS) stats as
computed by Composer. This tool re-backtests each candidate over (roughly)
the same OOS window with our own cost assumptions and compares. Symphonies
whose claimed edge doesn't reproduce get flagged.

The OOS window is approximated from oos_num_backtest_days (trading days ->
calendar days x 7/5), so small deltas are expected; big ones are the signal.

Read-only. Usage:
  verify-community.py --min-sharpe 1.5 --min-days 504 --order oos_calmar_ratio \
      --top 5 [--max-drawdown 0.3] [--name best-calmar]
"""

import argparse
import datetime
import sys
import composerlib as cl


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-sharpe", type=float)
    p.add_argument("--min-days", type=int, default=252)
    p.add_argument("--max-drawdown", type=float)
    p.add_argument("--order", default="oos_sharpe_ratio")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--name", default="community-verify")
    p.add_argument("--today", help="override 'today' (YYYY-MM-DD), mostly for tests")
    a = p.parse_args()

    clauses = [[">", "oos_num_backtest_days", a.min_days]]
    if a.min_sharpe is not None:
        clauses.append([">", "oos_sharpe_ratio", a.min_sharpe])
    if a.max_drawdown is not None:
        clauses.append(["<", "oos_max_drawdown", a.max_drawdown])
    where = clauses if len(clauses) == 1 else [["and", *clauses]]

    rows, offset, seen = [], 0, set()
    while len(rows) < a.top:
        batch = cl.post("/search/symphonies",
                        {"offset": offset, "where": where,
                         "order_by": [[a.order, "desc"]]})
        if not batch:
            break
        for s in batch:
            # the same strategy is often shared under several sids/names
            k = (s["name"], s.get("oos_num_backtest_days"))
            if k not in seen:
                seen.add(k)
                rows.append(s)
        offset += 5
        if offset > a.top * 10:
            break
    rows = rows[: a.top]
    if not rows:
        sys.exit("no symphonies matched the filters")

    today = (datetime.date.fromisoformat(a.today) if a.today
             else datetime.date.today())
    out = []
    print(f"verifying {len(rows)} candidates "
          f"(claimed vs our re-backtest over ~the same window)\n")
    for s in rows:
        sid = s["symphony_sid"]
        tdays = s["oos_num_backtest_days"]
        start = today - datetime.timedelta(days=round(tdays * 7 / 5) + 5)
        try:
            bt = cl.backtest_by_id(sid, start=start.isoformat())
        except SystemExit as e:
            print(f"  {sid}  BACKTEST FAILED: {e}")
            out.append({"sid": sid, "name": s["name"], "error": str(e)})
            continue
        st = bt["stats"]
        claimed = {"cagr": s.get("oos_annualized_rate_of_return"),
                   "sharpe": s.get("oos_sharpe_ratio"),
                   "max_drawdown": s.get("oos_max_drawdown")}
        ours = {"cagr": round(st["annualized_rate_of_return"], 4),
                "sharpe": round(st["sharpe_ratio"], 3),
                "max_drawdown": round(st["max_drawdown"], 4),
                "days": st["size"]}
        # flag if our sharpe is under 60% of claimed, or our DD is >1.5x claimed
        flags = []
        if claimed["sharpe"] and ours["sharpe"] is not None \
                and ours["sharpe"] < 0.6 * claimed["sharpe"]:
            flags.append("SHARPE_NOT_REPRODUCED")
        if claimed["max_drawdown"] and ours["max_drawdown"] > 1.5 * claimed["max_drawdown"]:
            flags.append("DRAWDOWN_WORSE")
        verdict = "FLAGGED " + "+".join(flags) if flags else "ok"
        print(f"  {sid}  {s['name'][:55]}")
        print(f"      claimed: cagr {claimed['cagr']:+8.1%}  sharpe {claimed['sharpe']:5.2f}  "
              f"dd {claimed['max_drawdown']:6.1%}  ({tdays} td)")
        print(f"      ours:    cagr {ours['cagr']:+8.1%}  sharpe {ours['sharpe']:5.2f}  "
              f"dd {ours['max_drawdown']:6.1%}  ({ours['days']} td)   -> {verdict}")
        out.append({"sid": sid, "name": s["name"], "claimed": claimed,
                    "ours": ours, "verdict": verdict})

    cl.write_json(f"composer/results/{a.name}.json",
                  {"filters": {"min_sharpe": a.min_sharpe, "min_days": a.min_days,
                               "max_drawdown": a.max_drawdown, "order": a.order},
                   "results": out})


if __name__ == "__main__":
    main()
