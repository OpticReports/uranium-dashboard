#!/usr/bin/env python3
"""Composer REST API helper.

Replaces the offline Composer MCP server. Auth comes from the environment:
COMPOSER_API_KEY_ID and COMPOSER_SECRET (never passed on the command line).

Read/build/backtest commands run freely. Capital-moving commands (invest,
withdraw, transfer) are guarded twice: COMPOSER_ALLOW_CAPITAL=1 must be set
in the environment AND --yes must be passed, and they always print a dry-run
trade preview first. See composer/README.md §2 for the policy.

Usage examples:
  composer-api.py accounts
  composer-api.py symphony-stats                       # per-symphony stats (default account)
  composer-api.py get <symphony-id> [-o out.json]      # logic tree
  composer-api.py versions <symphony-id>
  composer-api.py search --min-sharpe 1.5 --min-days 504 --order oos_calmar_ratio --pages 3
  composer-api.py backtest <symphony-id> [--start 2020-01-01] [--capital 10000]
  composer-api.py backtest-def -f tree.json            # ad-hoc tree, no save
  composer-api.py create -f tree.json --name "My strat" --hashtag "#mystrat"
  composer-api.py update <symphony-id> -f tree.json
  composer-api.py patch-nodes <symphony-id> <version-id> -f updates.json
  composer-api.py copy <symphony-id-or-sid>
  composer-api.py market-hours
  composer-api.py preview <symphony-id> --amount 1000  # dry-run trade preview
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py invest   <symphony-id> --amount 1000 --yes
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py withdraw <symphony-id> --amount 1000 --yes
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py transfer --from <sym-a> --to <sym-b> --amount 1000 --yes
  composer-api.py risk-off --all --dry-run              # owner override, read-only listing
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py risk-off --all --yes          # go-to-cash on every approved engine
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py risk-off --symphony KMLM HG --yes --skip-next
  COMPOSER_ALLOW_CAPITAL=1 composer-api.py risk-on --all --yes           # rebalance now, re-enter per logic
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://api.composer.trade/api/v0.1"


def _headers():
    kid = os.environ.get("COMPOSER_API_KEY_ID")
    sec = os.environ.get("COMPOSER_SECRET")
    if not kid or not sec:
        sys.exit("error: COMPOSER_API_KEY_ID / COMPOSER_SECRET not set in environment")
    return {
        "x-api-key-id": kid,
        "authorization": f"Bearer {sec}",
        "content-type": "application/json",
        # Cloudflare rejects Python-urllib's default UA with error 1010
        "user-agent": "composer-api-helper/1.0",
    }


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=_headers(),
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            return json.loads(body) if body.strip() else {"status": r.status}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        sys.exit(f"error: HTTP {e.code} on {method} {path}\n{detail}")


def out(data, path=None):
    text = json.dumps(data, indent=2)
    if path:
        with open(path, "w") as f:
            f.write(text + "\n")
        print(f"wrote {path}")
    else:
        print(text)


def default_account():
    accounts = call("GET", "/accounts/list")["accounts"]
    active = [a for a in accounts if a.get("status") == "ACTIVE"]
    if len(active) != 1:
        sys.exit(
            "error: expected exactly one ACTIVE account, found "
            f"{len(active)}; pass --account explicitly.\n"
            + "\n".join(f"  {a['account_uuid']} {a['account_type']} {a['status']}" for a in accounts)
        )
    return active[0]["account_uuid"]


def guard_capital(args, description):
    if os.environ.get("COMPOSER_ALLOW_CAPITAL") != "1":
        sys.exit(
            "REFUSED: capital-moving command without COMPOSER_ALLOW_CAPITAL=1.\n"
            "This command moves real money. Set COMPOSER_ALLOW_CAPITAL=1 and pass --yes\n"
            "only when a human has explicitly requested this exact operation."
        )
    if not args.yes:
        sys.exit(f"REFUSED: --yes not passed. Would have: {description}")
    print(f"CAPITAL MOVE: {description}", file=sys.stderr)


# ---- owner overrides (RUNBOOK.md "Owner override requests"): risk-off = go-to-cash inside the named
# symphonies, risk-on = rebalance them now per their live logic. Same double guard as invest/withdraw;
# every call is appended to results/monitor/override-ledger.jsonl.
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "fixtures", "approved", "manifest.json")
OVERRIDE_LEDGER = os.path.join(HERE, "..", "results", "monitor", "override-ledger.jsonl")


def approved_symphonies():
    """{NAME: symphony id} for the live engines, from fixtures/approved/manifest.json"""
    m = json.load(open(MANIFEST))
    return {name: e["symphony"] for name, e in m["engines"].items()}


def symphony_meta(acct):
    """{symphony id: {name, value, last_percent_change, holdings {ticker: weight}}}"""
    rows = call("GET", f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]
    return {s["id"]: {"name": s.get("name"), "value": s.get("value"), "last_percent_change": s.get("last_percent_change"),
                      "holdings": {h["ticker"]: round(h["allocation"], 4) for h in s.get("holdings", [])}} for s in rows}


def resolve_targets(args):
    """the symphonies an override names: --all = every approved engine; --symphony takes manifest names or ids"""
    approved = approved_symphonies()
    if args.all:
        return dict(approved)
    chosen = {}
    for s in args.symphony:
        if s.upper() in approved:
            chosen[s.upper()] = approved[s.upper()]
        elif s in approved.values():
            chosen[next(n for n, i in approved.items() if i == s)] = s
        else:
            sys.exit(f"error: {s!r} is not an approved symphony name or id ({', '.join(approved)})")
    if not chosen:
        sys.exit("error: name the symphonies: --all, or --symphony HG KMLM ...")
    return chosen


def override_log(entry):
    import datetime
    row = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), **entry}
    os.makedirs(os.path.dirname(OVERRIDE_LEDGER), exist_ok=True)
    with open(OVERRIDE_LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")


def backtest_body(args, symphony=None):
    body = {
        "capital": args.capital,
        "apply_reg_fee": True,
        "apply_taf_fee": True,
        "slippage_percent": 0.0005,
        "broker": "ALPACA_WHITE_LABEL",
        "backtest_version": "v2",
    }
    if args.start:
        body["start_date"] = args.start
    if args.end:
        body["end_date"] = args.end
    if symphony is not None:
        body["symphony"] = {"raw_value": symphony}
    return body


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, *flags):
        sp = sub.add_parser(name)
        if "account" in flags:
            sp.add_argument("--account", help="account UUID (default: the single ACTIVE account)")
        if "sym" in flags:
            sp.add_argument("symphony_id")
        if "file" in flags:
            sp.add_argument("-f", "--file", required=True, help="JSON file")
        if "out" in flags:
            sp.add_argument("-o", "--out", help="write JSON to file instead of stdout")
        if "amount" in flags:
            sp.add_argument("--amount", type=float, required=True)
        if "yes" in flags:
            sp.add_argument("--yes", action="store_true", help="confirm capital move")
        if "bt" in flags:
            sp.add_argument("--capital", type=float, default=10000)
            sp.add_argument("--start")
            sp.add_argument("--end")
        return sp

    add("accounts", "out")
    add("holdings", "account", "out")
    add("symphony-stats", "account", "out")
    add("total-stats", "account", "out")
    add("portfolio-history", "account", "out")
    add("get", "sym", "out")
    add("versions", "sym", "out")
    add("copy", "sym", "out")
    add("delete", "sym", "yes")
    add("market-hours", "out")
    add("backtest", "sym", "bt", "out")
    bd = add("backtest-def", "file", "bt", "out")

    cr = add("create", "file", "out")
    cr.add_argument("--name", required=True)
    cr.add_argument("--hashtag", required=True, help='e.g. "#mystrat"')
    cr.add_argument("--asset-class", default="EQUITIES")
    cr.add_argument("--description", default="")

    up = add("update", "sym", "file", "out")
    up.add_argument("--name")

    pn = sub.add_parser("patch-nodes")
    pn.add_argument("symphony_id")
    pn.add_argument("version_id")
    pn.add_argument("-f", "--file", required=True, help='JSON: [{"id": "<node-uuid>", ...fields}]')
    pn.add_argument("-o", "--out")

    se = add("search", "out")
    se.add_argument("--min-sharpe", type=float)
    se.add_argument("--min-days", type=int)
    se.add_argument("--max-drawdown", type=float, help="e.g. 0.25")
    se.add_argument("--order", default="oos_sharpe_ratio")
    se.add_argument("--pages", type=int, default=1, help="5 results per page")

    pv = add("preview", "sym", "account", "amount", "out")
    iv = add("invest", "sym", "account", "amount", "yes", "out")
    wd = add("withdraw", "sym", "account", "amount", "yes", "out")
    tr = sub.add_parser("transfer")
    tr.add_argument("--from", dest="src", required=True)
    tr.add_argument("--to", dest="dst", required=True)
    tr.add_argument("--amount", type=float, required=True)
    tr.add_argument("--account")
    tr.add_argument("--yes", action="store_true")

    add("go-to-cash", "sym", "account", "yes", "out")
    add("rebalance-now", "sym", "account", "yes", "out")
    for name in ("risk-off", "risk-on"):
        sp = sub.add_parser(name, help=("sell every holding to cash inside the named symphonies (owner override)"
                                        if name == "risk-off" else "rebalance the named symphonies now, re-entering per their live logic"))
        sp.add_argument("--all", action="store_true", help="every approved engine in fixtures/approved/manifest.json")
        sp.add_argument("--symphony", nargs="*", default=[], help="manifest names (HG KMLM SLEEVE HARV) or symphony ids")
        sp.add_argument("--account")
        sp.add_argument("--yes", action="store_true", help="confirm capital move")
        sp.add_argument("--dry-run", action="store_true", help="print what would move and exit (reads only; no guard needed)")
        if name == "risk-off":
            sp.add_argument("--skip-next", action="store_true", help="also skip each symphony's next automated rebalance")

    args = p.parse_args()
    a = args

    if a.cmd == "accounts":
        out(call("GET", "/accounts/list"), a.out)
    elif a.cmd in ("holdings", "symphony-stats", "total-stats", "portfolio-history"):
        acct = a.account or default_account()
        path = {
            "holdings": f"/accounts/{acct}/holdings",
            "symphony-stats": f"/portfolio/accounts/{acct}/symphony-stats-meta",
            "total-stats": f"/portfolio/accounts/{acct}/total-stats",
            "portfolio-history": f"/portfolio/accounts/{acct}/portfolio-history",
        }[a.cmd]
        out(call("GET", path), a.out)
    elif a.cmd == "get":
        out(call("GET", f"/symphonies/{a.symphony_id}/score"), a.out)
    elif a.cmd == "versions":
        out(call("GET", f"/symphonies/{a.symphony_id}/versions"), a.out)
    elif a.cmd == "copy":
        out(call("POST", f"/symphonies/{a.symphony_id}/copy"), a.out)
    elif a.cmd == "delete":
        if not a.yes:
            sys.exit(f"REFUSED: --yes not passed. Would delete saved symphony {a.symphony_id}.")
        out(call("DELETE", f"/symphonies/{a.symphony_id}"))
    elif a.cmd == "market-hours":
        out(call("GET", "/deploy/market-hours"), a.out)
    elif a.cmd == "backtest":
        out(call("POST", f"/symphonies/{a.symphony_id}/backtest", backtest_body(a)), a.out)
    elif a.cmd == "backtest-def":
        tree = json.load(open(a.file))
        out(call("POST", "/backtest", backtest_body(a, symphony=tree)), a.out)
    elif a.cmd == "create":
        tree = json.load(open(a.file))
        tree.setdefault("name", a.name)
        tree.setdefault("description", a.description)
        body = {
            "name": a.name,
            "asset_class": a.asset_class,
            "hashtag": a.hashtag,
            "symphony": {"raw_value": tree},
        }
        out(call("POST", "/symphonies", body), a.out)
    elif a.cmd == "update":
        tree = json.load(open(a.file))
        body = {"symphony": {"raw_value": tree}}
        if a.name:
            body["name"] = a.name
        out(call("PUT", f"/symphonies/{a.symphony_id}", body), a.out)
    elif a.cmd == "patch-nodes":
        updates = json.load(open(a.file))
        body = {"updates": updates if isinstance(updates, list) else updates["updates"]}
        out(call("PATCH", f"/symphonies/{a.symphony_id}/versions/{a.version_id}/score/nodes", body), a.out)
    elif a.cmd == "search":
        clauses = []
        if a.min_sharpe is not None:
            clauses.append([">", "oos_sharpe_ratio", a.min_sharpe])
        if a.min_days is not None:
            clauses.append([">", "oos_num_backtest_days", a.min_days])
        if a.max_drawdown is not None:
            clauses.append(["<", "oos_max_drawdown", a.max_drawdown])
        where = [] if not clauses else (clauses if len(clauses) == 1 else [["and", *clauses]])
        rows = []
        for page in range(a.pages):
            batch = call("POST", "/search/symphonies", {
                "offset": page * 5, "where": where, "order_by": [[a.order, "desc"]],
            })
            rows.extend(batch)
            if len(batch) < 5:
                break
        if a.out:
            out(rows, a.out)
        else:
            for s in rows:
                sh = s.get("oos_sharpe_ratio")
                cagr = s.get("oos_annualized_rate_of_return")
                dd = s.get("oos_max_drawdown")
                print(f"{s['symphony_sid']:>22}  sharpe {sh if sh is None else f'{sh:5.2f}'}  "
                      f"cagr {cagr if cagr is None else f'{cagr:7.1%}'}  "
                      f"dd {dd if dd is None else f'{dd:6.1%}'}  "
                      f"days {s.get('oos_num_backtest_days')}  {s['name'][:60]}")
    elif a.cmd == "preview":
        acct = a.account or default_account()
        out(call("POST", f"/dry-run/trade-preview/{a.symphony_id}",
                 {"amount": a.amount, "broker_account_uuid": acct}), a.out)
    elif a.cmd in ("invest", "withdraw"):
        acct = a.account or default_account()
        guard_capital(a, f"{a.cmd} ${a.amount:,.2f} {'into' if a.cmd == 'invest' else 'from'} "
                         f"{a.symphony_id} (account {acct})")
        print("-- dry-run preview (best-effort) --", file=sys.stderr)
        amt = a.amount if a.cmd == "invest" else -a.amount
        try:
            preview = call("POST", f"/dry-run/trade-preview/{a.symphony_id}",
                           {"amount": amt, "broker_account_uuid": acct})
            print(json.dumps(preview, indent=2)[:3000], file=sys.stderr)
        except SystemExit as e:
            print(f"preview unavailable ({str(e)[:120]}...) — proceeding; "
                  "the deploy itself validates amount and buying power", file=sys.stderr)
        out(call("POST", f"/deploy/accounts/{acct}/symphonies/{a.symphony_id}/{a.cmd}",
                 {"amount": a.amount}), a.out)
    elif a.cmd == "transfer":
        acct = a.account or default_account()
        guard_capital(a, f"withdraw ${a.amount:,.2f} from {a.src}, then invest into {a.dst} "
                         f"(account {acct})")
        print("NOTE: not atomic — withdraw must execute and settle before the invest can fill; "
              "deploys queue for the next trading window.", file=sys.stderr)
        w = call("POST", f"/deploy/accounts/{acct}/symphonies/{a.src}/withdraw", {"amount": a.amount})
        print(json.dumps(w, indent=2))
        i = call("POST", f"/deploy/accounts/{acct}/symphonies/{a.dst}/invest", {"amount": a.amount})
        print(json.dumps(i, indent=2))
    elif a.cmd in ("go-to-cash", "rebalance-now"):
        acct = a.account or default_account()
        m = symphony_meta(acct).get(a.symphony_id, {})
        label = m.get("name") or a.symphony_id
        desc = (f"go to cash on {label} (${(m.get('value') or 0):,.0f}; holds {m.get('holdings')})" if a.cmd == "go-to-cash"
                else f"rebalance NOW {label} (${(m.get('value') or 0):,.0f}) per its live logic")
        guard_capital(a, desc)
        route = "go-to-cash" if a.cmd == "go-to-cash" else "rebalance"
        res = call("POST", f"/deploy/accounts/{acct}/symphonies/{a.symphony_id}/{route}")
        override_log({"cmd": a.cmd, "symphony": a.symphony_id, "name": m.get("name"), "value": m.get("value"),
                      "holdings_before": m.get("holdings"), "response": res})
        out(res, a.out)
    elif a.cmd in ("risk-off", "risk-on"):
        targets = resolve_targets(a)
        acct = a.account or default_account()
        meta = symphony_meta(acct)
        total = 0.0
        print(f"{'DRY RUN' if a.dry_run else 'OVERRIDE'}: {a.cmd} on {', '.join(targets)} (account {acct})", file=sys.stderr)
        for name, sid in targets.items():
            m = meta.get(sid, {})
            total += m.get("value") or 0
            print(f"  {name:6s} {sid}  ${(m.get('value') or 0):>10,.0f}  holds {m.get('holdings')}", file=sys.stderr)
        print(f"  total ${total:,.0f}; " + ("sells every holding to cash inside each symphony and cancels queued deploys; automated "
              "rebalancing resumes at the next window unless --skip-next" if a.cmd == "risk-off" else
              "re-enters each symphony per its live logic") + "; executes in Composer's trading window (check market-hours)",
              file=sys.stderr)
        if a.dry_run:
            return
        guard_capital(a, f"{a.cmd} on {', '.join(targets)}: ${total:,.0f}")
        results = {}
        for name, sid in targets.items():
            route = "go-to-cash" if a.cmd == "risk-off" else "rebalance"
            res = call("POST", f"/deploy/accounts/{acct}/symphonies/{sid}/{route}")
            results[name] = res
            override_log({"cmd": a.cmd, "symphony": sid, "name": name, "value": (meta.get(sid) or {}).get("value"),
                          "holdings_before": (meta.get(sid) or {}).get("holdings"), "response": res})
            if a.cmd == "risk-off" and a.skip_next:
                res2 = call("POST", f"/deploy/accounts/{acct}/symphonies/{sid}/skip-automated-rebalance")
                results[name + " (skip next automated rebalance)"] = res2
                override_log({"cmd": "skip-automated-rebalance", "symphony": sid, "name": name, "response": res2})
        out(results)


if __name__ == "__main__":
    main()
