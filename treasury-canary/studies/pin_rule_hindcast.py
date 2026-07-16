#!/usr/bin/env python3
"""Hindcast: can pin-board reds/convergence improve recession prediction?

Grades seven PRE-SPECIFIED aggregation rules (no fitting — every set and
threshold is taken from the board's documented design, not searched) against
two event sets: NBER recession onsets and >=15% SPX drawdown starts.

Rules:
  count2            raw damage-window convergence >= 2 (the seductive one)
  fast_window       any FAST_HIGH_MASS channel window open
  fast_red          any FAST_HIGH_MASS channel red that month
  slow_window       oil/policy window open (the two highest documented kill rates)
  curve             10y-3m spread < 0.25pp within trailing 6m (flat/inverted regime)
  fast_red+curve    the transmission-note configuration, measurable form
  slow_window+curve

Data: the live /pins/history endpoint (full FRED-backed hindcast, monthly-max
severity, expanding percentiles) + Yahoo ^TNX/^IRX monthly for the curve.

Result summary lives in pin-rule-hindcast.md next to this script. Run it any
time to refresh; it prints the comparison table and per-event catch detail.
"""
from __future__ import annotations

import datetime
import json
import urllib.request

API = "https://treasury-canary.onrender.com"
YA = "https://query1.finance.yahoo.com/v8/finance/chart/%5E{sym}?period1=0&period2=1893456000&interval=1mo"
FAST = {"credit_event", "plumbing", "basis_trade", "carry_unwind"}  # = pins.FAST_HIGH_MASS
SLOW_LETHAL = {"oil_shock", "policy_shock"}  # Hamilton 10/11; every tightening cycle
CURVE_FLAT_PP = 0.25
HORIZON = 12


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 (canary-study)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def add_m(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def yahoo_monthly(sym: str) -> dict[str, float]:
    r = get(YA.format(sym=sym))["chart"]["result"][0]
    out = {}
    for ts, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
        if c is not None:
            d = datetime.date.fromtimestamp(ts)
            out[f"{d.year:04d}-{d.month:02d}"] = c
    return out


def main() -> None:
    hist = get(f"{API}/pins/history")
    coll = [r for r in hist["collective"]["series"] if not r["projected"]]
    months = [r["date"] for r in coll]
    onsets = [r["start"] for r in hist["recessions"]]
    dds = [(x["start"], x["depth_pct"]) for x in hist["drawdowns"]]
    red = {c["channel_id"]: {p["date"] for p in c["series"] if p["score"] >= 80}
           for c in hist["channels"]}
    covered = {c["channel_id"]: {p["date"] for p in c["series"]} for c in hist["channels"]}
    winopen = {r["date"]: set(r["window_channels"]) for r in coll}

    tnx, irx = yahoo_monthly("TNX"), yahoo_monthly("IRX")
    spread = {m: tnx[m] - irx[m] for m in tnx if m in irx}
    inv6: dict[str, bool | None] = {}
    for m in months:
        win = [spread.get(add_m(m, -k)) for k in range(0, 7)]
        win = [x for x in win if x is not None]
        inv6[m] = (min(win) < CURVE_FLAT_PP) if win else None

    def signal(rule: str, m: str) -> bool | None:
        def has(chs): return any(m in covered[c] for c in chs)
        if rule == "count2":
            return len(winopen[m]) >= 2
        if rule == "fast_window":
            return (len(winopen[m] & FAST) >= 1) if has(FAST) else None
        if rule == "fast_red":
            return any(m in red[c] for c in FAST) if has(FAST) else None
        if rule == "slow_window":
            return (len(winopen[m] & SLOW_LETHAL) >= 1) if has(SLOW_LETHAL) else None
        if rule == "curve":
            return inv6[m]
        if rule == "fast_red+curve":
            f = any(m in red[c] for c in FAST) if has(FAST) else None
            return None if (f is None or inv6[m] is None) else (f and inv6[m])
        if rule == "slow_window+curve":
            s = (len(winopen[m] & SLOW_LETHAL) >= 1) if has(SLOW_LETHAL) else None
            return None if (s is None or inv6[m] is None) else (s and inv6[m])
        raise ValueError(rule)

    def evaluate(rule: str, events: list[str]) -> dict | None:
        sig = {m: signal(rule, m) for m in months}
        live = [m for m in months if sig[m] is not None]
        if not live:
            return None
        lo, hi = live[0], live[-1]
        evs = [e for e in events if lo < e <= add_m(hi, HORIZON)]

        def hit(m: str) -> bool:
            return any(m < e <= add_m(m, HORIZON) for e in evs)

        resolv = [m for m in live if add_m(m, HORIZON) <= max(months)]
        base = sum(1 for m in resolv if hit(m)) / len(resolv) if resolv else 0.0
        on = [m for m in resolv if sig[m]]
        prec = sum(1 for m in on if hit(m)) / len(on) if on else float("nan")
        caught = sum(1 for e in evs
                     if any(sig.get(add_m(e, -k)) for k in range(1, HORIZON + 1)))
        return dict(rule=rule, window=f"{lo}..{hi}", n_on=len(on), n_live=len(live),
                    precision=prec, base=base, recall=f"{caught}/{len(evs)}")

    rules = ("count2", "fast_window", "fast_red", "slow_window",
             "curve", "fast_red+curve", "slow_window+curve")
    for events, name in ((onsets, "RECESSION ONSETS"),
                         ([e for e, _ in dds], "DRAWDOWN STARTS (>=15%)")):
        print(f"\n=== vs {name} (P(event within {HORIZON}m | signal-month)) ===")
        print(f"{'rule':18} {'window':18} {'on/live':>9} {'precision':>10} {'base':>6} {'recall':>7}")
        for rule in rules:
            r = evaluate(rule, events)
            if r:
                print(f"{r['rule']:18} {r['window']:18} {r['n_on']:>4}/{r['n_live']:<4} "
                      f"{r['precision']:>9.0%} {r['base']:>6.0%} {r['recall']:>7}")

    print("\nfast_red+curve — per-drawdown detail:")
    for ev, depth in dds:
        leads = []
        for k in range(1, HORIZON + 1):
            m = add_m(ev, -k)
            s = signal("fast_red+curve", m)
            if s:
                leads.append(k)
        tag = (f"caught, fired {max(leads)}-{min(leads)}m before" if leads else "MISSED")
        print(f"  {ev} ({depth}%): {tag}")


if __name__ == "__main__":
    main()
