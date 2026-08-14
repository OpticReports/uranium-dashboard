"""Shared helpers for the Composer REST API scripts. Stdlib only.

Auth from COMPOSER_API_KEY_ID / COMPOSER_SECRET env vars. Read-only helpers
plus backtest utilities. Capital-moving routes are deliberately NOT wrapped
here — see composer-api.py and README §2.
"""

import json
import math
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


def call(method, path, body=None, timeout=120):
    req = urllib.request.Request(
        BASE + path, method=method, headers=_headers(),
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return json.loads(body) if body.strip() else {"status": r.status}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        sys.exit(f"error: HTTP {e.code} on {method} {path}\n{detail}")


def get(path, **kw):
    return call("GET", path, **kw)


def post(path, body, **kw):
    return call("POST", path, body, **kw)


def default_account():
    accounts = get("/accounts/list")["accounts"]
    active = [a for a in accounts if a.get("status") == "ACTIVE"]
    if len(active) != 1:
        sys.exit("error: expected exactly one ACTIVE account; pass --account.\n"
                 + "\n".join(f"  {a['account_uuid']} {a['account_type']} {a['status']}"
                             for a in accounts))
    return active[0]["account_uuid"]


def backtest_body(capital=10000, start=None, end=None, tree=None):
    body = {
        "capital": capital, "apply_reg_fee": True, "apply_taf_fee": True,
        "slippage_percent": 0.0005, "broker": "ALPACA_WHITE_LABEL",
        "backtest_version": "v2",
    }
    if start:
        body["start_date"] = start
    if end:
        body["end_date"] = end
    if tree is not None:
        body["symphony"] = {"raw_value": tree}
    return body


def backtest_by_id(symphony_id, **kw):
    return post(f"/symphonies/{symphony_id}/backtest", backtest_body(**kw))


def backtest_tree(tree, **kw):
    return post("/backtest", backtest_body(tree=tree, **kw))


def equity_curve(backtest):
    """(sorted_epoch_days, values) for the primary series in a backtest."""
    dvm = backtest["dvm_capital"]
    key = next(iter(backtest.get("legend") or dvm))
    series = dvm[key]
    days = sorted(int(d) for d in series)
    return days, [series[str(d)] for d in days]


def returns_from_curve(values):
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))
            if values[i - 1] > 0]


def max_drawdown(values):
    peak, mdd = values[0], 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = 1.0 - v / peak
        if dd > mdd:
            mdd = dd
    return mdd


def curve_stats(values):
    """CAGR / sharpe / max DD computed locally from a value series."""
    rets = returns_from_curve(values)
    if not rets:
        return None
    years = len(rets) / 252.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    sd = math.sqrt(var)
    total = values[-1] / values[0]
    return {
        "days": len(rets),
        "cumulative_return": round(total - 1.0, 4),
        "cagr": round(total ** (1.0 / years) - 1.0, 4) if years > 0 and total > 0 else None,
        "sharpe": round(mean / sd * math.sqrt(252), 3) if sd > 0 else None,
        "ann_vol": round(sd * math.sqrt(252), 4),
        "max_drawdown": round(max_drawdown(values), 4),
    }


def walk_tree(node, fn, parents=()):
    """Depth-first visit; fn(node, parents)."""
    fn(node, parents)
    for c in node.get("children", []):
        walk_tree(c, fn, parents + (node,))


def find_node(tree, node_id):
    hit = []
    walk_tree(tree, lambda n, _: hit.append(n) if n.get("id") == node_id else None)
    return hit[0] if hit else None


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def epoch_ms_to_date(ms):
    import datetime
    return datetime.datetime.utcfromtimestamp(ms / 1000).date()


def epoch_day_to_date(day):
    import datetime
    return datetime.date(1970, 1, 1) + datetime.timedelta(days=day)


def write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"wrote {path}")
