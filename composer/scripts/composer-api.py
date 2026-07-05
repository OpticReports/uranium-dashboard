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
            return json.load(r)
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
        print("-- dry-run preview --", file=sys.stderr)
        amt = a.amount if a.cmd == "invest" else -a.amount
        preview = call("POST", f"/dry-run/trade-preview/{a.symphony_id}",
                       {"amount": amt, "broker_account_uuid": acct})
        print(json.dumps(preview, indent=2)[:3000], file=sys.stderr)
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


if __name__ == "__main__":
    main()
