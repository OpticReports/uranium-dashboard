#!/usr/bin/env python3
"""Hindcast v2: can pin-board reds/convergence improve recession prediction?

Grades seven PRE-SPECIFIED aggregation rules (no fitting — channel sets and
thresholds come from the board's documented design, not searched) against two
event sets: NBER recession onsets and >=15% SPX drawdown starts.

v2 corrections after hostile QA (see pin-rule-hindcast.md, "QA corrections"):
  - SPX ground truth from DAILY bars downsampled to true monthly (Yahoo
    silently degrades interval=1mo&range=max to QUARTERLY bars — v1's event
    dates were quarter-open stamps, off by up to ~7 months).
  - Curve = the SAME instrument the deployed gauge uses: daily FRED 3m10y
    (DGS10-DGS3MO) via the canary's public /curve endpoint (1981+), min over
    a trailing 183-DAY window — v1 used Yahoo ^TNX-^IRX (discount-basis,
    ~10-15bp off CMT) over 7 monthly closes, a different rule than shipped.
  - UTC date handling (local-tz runners shifted every v1 month label).
  - Cluster accounting: contiguous signal runs are reported as EPISODES with
    an episode-level hit rate, because 69 "signal months" in ~9 runs is an
    effective sample of ~9, not 69.

Read the results as descriptive context, never calibration.
"""
from __future__ import annotations

import datetime
import json
import urllib.request

API = "https://treasury-canary.onrender.com"
GSPC = ("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
        "?period1=0&period2=4102444800&interval=1d")
FAST = {"credit_event", "plumbing", "basis_trade", "carry_unwind"}  # = pins.FAST_HIGH_MASS
SLOW_LETHAL = {"oil_shock", "policy_shock"}  # Hamilton 10/11; every tightening cycle
CURVE_FLAT_PP = 0.25
CURVE_WINDOW_DAYS = 183      # matches the deployed gauge exactly
HORIZON = 12


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 (canary-study)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def add_m(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def spx_monthly() -> list[tuple[str, float, float]]:
    """[(ym, close, low)] true monthly bars from dailies, UTC-labeled."""
    res = get(GSPC)["chart"]["result"][0]
    assert res["meta"]["dataGranularity"] == "1d", "Yahoo degraded granularity"
    quote = res["indicators"]["quote"][0]
    out: dict[str, list[float]] = {}
    for ts, c, l in zip(res["timestamp"], quote["close"], quote["low"]):
        if c is None:
            continue
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date()
        ym = f"{d.year:04d}-{d.month:02d}"
        low = l if l is not None else c
        if ym not in out:
            out[ym] = [c, low]
        else:
            out[ym][0] = c
            out[ym][1] = min(out[ym][1], low)
    return [(ym, v[0], v[1]) for ym, v in sorted(out.items())]


def drawdown_starts(bars, threshold=15.0) -> list[tuple[str, float]]:
    """[(peak_ym, depth_pct)] of >=threshold peak-to-trough declines (mirrors
    backend _drawdown_spans: low checked BEFORE the close can reset the peak)."""
    spans, peak, peak_ym, active, depth_max = [], None, None, None, 0.0
    for ym, c, low in bars:
        if peak is not None and peak > 0:
            depth = (peak - low) / peak * 100.0
            if depth >= threshold:
                if active is None:
                    active = [peak_ym, depth]
                    depth_max = depth
                elif depth > depth_max:
                    active[1] = depth
                    depth_max = depth
        if peak is None or c >= peak:
            if active is not None:
                spans.append(tuple(active))
                active = None
                depth_max = 0.0
            peak, peak_ym = c, ym
    if active is not None:
        spans.append(tuple(active))
    return [(s, round(d, 1)) for s, d in spans]


def curve_flat_by_month(months: list[str]) -> dict[str, bool | None]:
    """min(daily FRED 3m10y over trailing 183d) < 0.25, per month — the
    deployed gauge's exact rule, evaluated at each month-end."""
    series = get(f"{API}/curve/canary?pair=3m10y")["series"]
    days = [(datetime.date.fromisoformat(p["date"]), p["spread"])
            for p in series if p["spread"] is not None]
    days.sort()
    out: dict[str, bool | None] = {}
    i = 0
    for m in months:
        y, mm = int(m[:4]), int(m[5:7])
        eom = (datetime.date(y + (mm == 12), mm % 12 + 1, 1)
               - datetime.timedelta(days=1))
        window = [v for d, v in days if eom - datetime.timedelta(days=CURVE_WINDOW_DAYS) <= d <= eom]
        out[m] = (min(window) < CURVE_FLAT_PP) if window else None
    return out


def clusters(sig_months: list[str]) -> list[list[str]]:
    runs: list[list[str]] = []
    for m in sig_months:
        if runs and add_m(runs[-1][-1], 1) == m:
            runs[-1].append(m)
        else:
            runs.append([m])
    return runs


def main() -> None:
    hist = get(f"{API}/pins/history")
    coll = [r for r in hist["collective"]["series"] if not r["projected"]]
    months = [r["date"] for r in coll]
    onsets = [r["start"] for r in hist["recessions"]]
    bars = spx_monthly()
    dds = drawdown_starts(bars)
    print("recession onsets:", onsets)
    print("drawdown starts (>=15%):", dds)

    red = {c["channel_id"]: {p["date"] for p in c["series"] if p["score"] >= 80}
           for c in hist["channels"]}
    covered = {c["channel_id"]: {p["date"] for p in c["series"]} for c in hist["channels"]}
    winopen = {r["date"]: set(r["window_channels"]) for r in coll}
    inv = curve_flat_by_month(months)

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
            return inv[m]
        if rule == "fast_red+curve":
            f = any(m in red[c] for c in FAST) if has(FAST) else None
            return None if (f is None or inv[m] is None) else (f and inv[m])
        if rule == "slow_window+curve":
            s = (len(winopen[m] & SLOW_LETHAL) >= 1) if has(SLOW_LETHAL) else None
            return None if (s is None or inv[m] is None) else (s and inv[m])
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
        cl = clusters(on)
        cl_hits = sum(1 for c in cl if any(hit(m) for m in c))
        caught = sum(1 for e in evs
                     if any(sig.get(add_m(e, -k)) for k in range(1, HORIZON + 1)))
        return dict(rule=rule, window=f"{lo}..{hi}", n_on=len(on),
                    n_clusters=len(cl), cl_hits=cl_hits,
                    precision=prec, base=base, recall=f"{caught}/{len(evs)}")

    rules = ("count2", "fast_window", "fast_red", "slow_window",
             "curve", "fast_red+curve", "slow_window+curve")
    for events, name in ((onsets, "RECESSION ONSETS"),
                         ([e for e, _ in dds], "DRAWDOWN STARTS (>=15%)")):
        print(f"\n=== vs {name} (P(event within {HORIZON}m | signal-month)) ===")
        print(f"{'rule':18} {'window':18} {'months':>7} {'clusters':>9} "
              f"{'precision':>10} {'base':>6} {'recall':>7}")
        for rule in rules:
            r = evaluate(rule, events)
            if r:
                print(f"{r['rule']:18} {r['window']:18} {r['n_on']:>7} "
                      f"{r['cl_hits']}/{r['n_clusters']:<7} "
                      f"{r['precision']:>9.0%} {r['base']:>6.0%} {r['recall']:>7}")

    print("\nfast_red+curve — per-drawdown detail (lead = months before the PEAK):")
    for ev, depth in dds:
        leads = [k for k in range(1, HORIZON + 1)
                 if signal("fast_red+curve", add_m(ev, -k))]
        tag = (f"caught, fired {max(leads)}-{min(leads)}m before the peak"
               if leads else "MISSED")
        print(f"  {ev} (-{depth}%): {tag}")


if __name__ == "__main__":
    main()
