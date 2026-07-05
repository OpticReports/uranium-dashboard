#!/usr/bin/env python3
"""Parameter sweep harness for a Composer symphony.

Fetches the symphony's logic tree, applies every combination of the requested
parameter values in memory (nothing is saved to Composer), backtests each
variant via POST /backtest, and reports a comparison grid. Optional
walk-forward split computes in-sample and out-of-sample stats separately so
you can see which parameter choices are overfit.

Read-only: never saves, updates, or deploys anything.

Usage:
  sweep.py --id <symphony-id> --list-nodes
      Show tweakable nodes (conditions, filters, assets) with their ids.

  sweep.py --id <symphony-id> \
      --set '<node-id>:rhs-val=75,79,82' \
      --set '<node-id2>:lhs-fn-params.window=10,14' \
      [--split 2025-01-01] [--start ...] [--end ...] [--name uvxy-thresholds]

Each --set is node-id:field=v1,v2,...  Fields use dots for nesting
(lhs-fn-params.window). Values are parsed as numbers when possible; Composer
stores some thresholds as strings, so the original type is preserved when the
existing value is a string. Cartesian product across all --set specs
(baseline value included automatically if not listed).
"""

import argparse
import itertools
import json
import sys
import composerlib as cl


def parse_set(spec):
    try:
        addr, values = spec.split("=", 1)
        node_id, field = addr.split(":", 1)
    except ValueError:
        sys.exit(f"error: bad --set {spec!r} (want node-id:field=v1,v2)")
    vals = []
    for v in values.split(","):
        v = v.strip()
        try:
            vals.append(int(v))
        except ValueError:
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(v)
    return node_id, field, vals


def get_field(node, field):
    cur = node
    parts = field.split(".")
    for p in parts[:-1]:
        cur = cur.get(p, {})
    return cur.get(parts[-1])


def set_field(node, field, value):
    cur = node
    parts = field.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    old = cur.get(parts[-1])
    # Composer stores many numeric thresholds as strings; preserve the type
    if isinstance(old, str) and not isinstance(value, str):
        value = str(value)
    cur[parts[-1]] = value


def describe_condition(n):
    def side(pfx):
        fn = n.get(f"{pfx}-fn") or ""
        val = n.get(f"{pfx}-val")
        w = n.get(f"{pfx}-window-days") or (n.get(f"{pfx}-fn-params") or {}).get("window")
        if n.get("rhs-fixed-value?") and pfx == "rhs":
            return str(val)
        short = {"relative-strength-index": "RSI", "moving-average-price": "SMA",
                 "exponential-moving-average-price": "EMA", "current-price": "price",
                 "cumulative-return": "cumret", "max-drawdown": "maxdd",
                 "standard-deviation-price": "stdev"}.get(fn, fn)
        return f"{short}({w}d) {val}" if w else f"{short} {val}"
    return f"{side('lhs')} {n.get('comparator')} {side('rhs')}"


def list_nodes(tree):
    rows = []
    def visit(n, parents):
        s = n.get("step")
        if s == "if-child" and not n.get("is-else-condition?"):
            rows.append((n["id"], "condition", describe_condition(n),
                         "fields: comparator, rhs-val, lhs-val, lhs-fn-params.window, rhs-fn-params.window"))
        elif s == "filter":
            w = n.get("sort-by-window-days") or (n.get("sort-by-fn-params") or {}).get("window")
            rows.append((n["id"], "filter",
                         f"{n.get('select-fn')} {n.get('select-n')} by {n.get('sort-by-fn')}({w}d)",
                         "fields: select-fn, select-n, sort-by-fn-params.window"))
        elif s == "asset":
            rows.append((n["id"], "asset", n.get("ticker"), "fields: ticker"))
    cl.walk_tree(tree, visit)
    for nid, kind, desc, hint in rows:
        print(f"{nid}  [{kind:9}] {desc}")
        print(f"{'':38}  {hint}")


def key_stats(bt):
    s = bt["stats"]
    return {
        "cagr": round(s["annualized_rate_of_return"], 4),
        "sharpe": round(s["sharpe_ratio"], 3),
        "max_drawdown": round(s["max_drawdown"], 4),
        "cumulative_return": round(s["cumulative_return"], 2),
        "days": s["size"],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", required=True)
    p.add_argument("--list-nodes", action="store_true")
    p.add_argument("--set", action="append", default=[], metavar="NODE:FIELD=V1,V2")
    p.add_argument("--split", help="walk-forward split date YYYY-MM-DD: stats reported "
                                   "separately before (in-sample) and after (out-of-sample)")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--capital", type=float, default=10000)
    p.add_argument("--name", default="sweep", help="basename for results/sweeps/<name>.json")
    p.add_argument("--max-variants", type=int, default=32,
                   help="refuse to run more backtests than this (default 32)")
    a = p.parse_args()

    tree = cl.get(f"/symphonies/{a.id}/score")
    if a.list_nodes:
        list_nodes(tree)
        return
    if not a.set:
        sys.exit("error: need at least one --set (or --list-nodes)")

    specs = [parse_set(s) for s in a.set]
    for node_id, field, vals in specs:
        node = cl.find_node(tree, node_id)
        if node is None:
            sys.exit(f"error: node {node_id} not found in tree")
        baseline = get_field(node, field)
        if baseline is None:
            sys.exit(f"error: node {node_id} has no field {field!r}")
        base_cmp = str(baseline)
        if not any(str(v) == base_cmp for v in vals):
            vals.insert(0, baseline)  # always include the baseline value

    combos = list(itertools.product(*[[(nid, f, v) for v in vals]
                                      for nid, f, vals in specs]))
    if len(combos) > a.max_variants:
        sys.exit(f"error: {len(combos)} variants exceeds --max-variants {a.max_variants}")

    def run(tree, start, end):
        bt = cl.backtest_tree(tree, capital=a.capital, start=start, end=end)
        return key_stats(bt)

    results = []
    for i, combo in enumerate(combos):
        variant = json.loads(json.dumps(tree))  # deep copy
        label = {}
        for node_id, field, value in combo:
            set_field(cl.find_node(variant, node_id), field, value)
            label[f"{node_id[:8]}:{field}"] = value
        row = {"params": label}
        if a.split:
            row["in_sample"] = run(variant, a.start, a.split)
            row["out_of_sample"] = run(variant, a.split, a.end)
        else:
            row["full"] = run(variant, a.start, a.end)
        results.append(row)
        done = json.dumps(label)
        print(f"[{i+1}/{len(combos)}] {done}", file=sys.stderr)

    # rank by out-of-sample sharpe if split, else full sharpe
    section = "out_of_sample" if a.split else "full"
    results.sort(key=lambda r: (r[section]["sharpe"] is not None,
                                r[section]["sharpe"] or -99), reverse=True)

    print(f"\n=== sweep: {a.id} ({len(results)} variants, ranked by {section} sharpe) ===")
    for r in results:
        parts = [f"{k.split(':',1)[1]}={v}" for k, v in r["params"].items()]
        tag = ", ".join(parts)
        if a.split:
            i_, o_ = r["in_sample"], r["out_of_sample"]
            print(f"  IS  cagr {i_['cagr']:+8.1%} sharpe {i_['sharpe']:5.2f} dd {i_['max_drawdown']:6.1%} | "
                  f"OOS cagr {o_['cagr']:+8.1%} sharpe {o_['sharpe']:5.2f} dd {o_['max_drawdown']:6.1%}  <- {tag}")
        else:
            f_ = r["full"]
            print(f"  cagr {f_['cagr']:+8.1%}  sharpe {f_['sharpe']:5.2f}  dd {f_['max_drawdown']:6.1%}  "
                  f"days {f_['days']}  <- {tag}")

    out = {"symphony_id": a.id, "split": a.split, "start": a.start, "end": a.end,
           "capital": a.capital, "results": results}
    cl.write_json(f"composer/results/sweeps/{a.name}.json", out)


if __name__ == "__main__":
    main()
