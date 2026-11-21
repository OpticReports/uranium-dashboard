"""GDP watch, forecast study v1: what can a simple, honest rule say about the next four quarters of growth?

Target: real GDP growth on the same quarter a year earlier (YoY, %), the series the chart shows, h = 1..4
quarters ahead. Origins: every quarter t from 2006-Q1 on that has its four outcomes. Only data dated <= t
are used, BUT on today's revised data, not real-time vintages: errors are understated against real time.

Methods (nothing is tuned on outcomes):
  N  naive   YoY(t+h) = YoY(t).
  T  trend   each coming quarter grows at mu(t), the median quarter-on-quarter growth of the 40 quarters to t.
  A  AR(1)   quarter-on-quarter growth decays toward mu(t): q(t+i) = mu + phi^i (q(t) - mu), phi(t) the least-squares
             slope through the origin of the deviations on the 40 quarters to t, clipped to [0, 0.8].
  The pandemic quarters 2020-Q1..2021-Q4 never enter mu or phi.
T and A roll the published YoY forward one quarter at a time, so the quarters already in hand count:
  1 + YoY(t+h) = (1 + YoY(t+h-1)) (1 + q(t+h)) / (1 + q(t+h-4)).

Selection rule, written before the run: the lowest mean MAE over h = 1..4 with pandemic targets excluded; a
method within 2% of a simpler one loses to it (simplicity order N, T, A).

    python3 -I backtest_v1.py <snapshot.json.gz> <out_dir>
"""
from __future__ import annotations

import gzip
import json
import math
import os
import statistics
import sys

WINDOW, MIN_WINDOW, MIN_PAIRS = 40, 20, 12
FIRST_ORIGIN = "2006-Q1"
PANDEMIC = {f"{y}-Q{q}" for y in (2020, 2021) for q in (1, 2, 3, 4)}
METHODS = ("N", "T", "A")
H = (1, 2, 3, 4)


def qi(s: str) -> int:
    return int(s[:4]) * 4 + int(s[-1]) - 1


def qs(i: int) -> str:
    return f"{i // 4}-Q{i % 4 + 1}"


def trend_phi(q: dict, t: int) -> tuple[float | None, float]:
    """mu(t): median q/q of the WINDOW quarters to t; phi(t): least-squares slope through the origin (no intercept)
    of the deviations, both without pandemic quarters."""
    win = [qs(i) for i in range(t - WINDOW + 1, t + 1)]
    vals = [q[s] for s in win if s in q and s not in PANDEMIC]
    if len(vals) < MIN_WINDOW:
        return None, 0.0
    mu = statistics.median(vals)
    pairs = [(q[qs(qi(s) - 1)] - mu, q[s] - mu) for s in win
             if s in q and qs(qi(s) - 1) in q and s not in PANDEMIC and qs(qi(s) - 1) not in PANDEMIC]
    sxx = sum(x * x for x, _ in pairs)
    phi = sum(x * y for x, y in pairs) / sxx if len(pairs) >= MIN_PAIRS and sxx > 0 else 0.0
    return mu, min(0.8, max(0.0, phi))


def forecast(y: dict, q: dict, t: int, method: str) -> list[float] | None:
    """YoY path for t+1..t+4 from data <= t, or None when the inputs are missing."""
    if qs(t) not in y:
        return None
    if method == "N":
        return [y[qs(t)]] * 4
    if any(qs(t - k) not in q for k in range(4)):
        return None
    mu, phi = trend_phi(q, t)
    if mu is None:
        return None
    if method == "T":
        phi = 0.0
    path, level = [], 1 + y[qs(t)] / 100
    for h in H:
        qhat = mu + phi ** h * (q[qs(t)] - mu)
        level = level * (1 + qhat / 100) / (1 + q[qs(t + h - 4)] / 100)
        path.append(100 * (level - 1))
    return path


def errors(snap: dict, codes: list[str]) -> list[dict]:
    rows = []
    for c in codes:
        y, q = snap["yoy"].get(c) or {}, snap["qoq"].get(c) or {}
        if not y:
            continue
        last = max(qi(s) for s in y)
        for t in range(qi(FIRST_ORIGIN), last - 3):
            f = {m: forecast(y, q, t, m) for m in METHODS}
            if any(v is None for v in f.values()):
                continue
            for h in H:
                a = y.get(qs(t + h))
                if a is None:
                    continue
                rows.append({"c": c, "t": qs(t), "h": h, "target": qs(t + h), "actual": a,
                             "pandemic": qs(t + h) in PANDEMIC, **{m: a - f[m][h - 1] for m in METHODS}})
    return rows


def summary(rows: list[dict], m: str, h: int, exclude_pandemic: bool) -> dict:
    e = [r[m] for r in rows if r["h"] == h and not (exclude_pandemic and r["pandemic"])]
    if not e:
        return {"n": 0}
    return {"n": len(e), "mae": round(statistics.fmean(abs(x) for x in e), 3),
            "rmse": round(math.sqrt(statistics.fmean(x * x for x in e)), 3), "bias": round(statistics.fmean(e), 3)}


def quantiles(e: list[float]) -> dict | None:
    if len(e) < 20:
        return None
    s = sorted(e)
    pick = lambda p: s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]   # noqa: E731
    return {"p10": round(pick(0.10), 3), "p25": round(pick(0.25), 3), "p50": round(pick(0.50), 3),
            "p75": round(pick(0.75), 3), "p90": round(pick(0.90), 3), "n": len(s)}


def identity_residual(snap: dict, c: str) -> dict | None:
    """How well rolling the published YoY with the published q/q reproduces next quarter's published YoY."""
    y, q = snap["yoy"].get(c) or {}, snap["qoq"].get(c) or {}
    res = []
    for s in y:
        t = qi(s)
        nxt, keys = qs(t + 1), [qs(t + 1), qs(t - 3)]
        if nxt in y and all(k in q for k in keys) and qi(s) >= qi("2000-Q1"):
            implied = 100 * ((1 + y[s] / 100) * (1 + q[qs(t + 1)] / 100) / (1 + q[qs(t - 3)] / 100) - 1)
            res.append(y[nxt] - implied)
    return {"n": len(res), "mae": round(statistics.fmean(abs(x) for x in res), 3)} if res else None


def choose(pooled: dict) -> str:
    mean = {m: statistics.fmean(pooled[m][str(h)]["mae"] for h in H) for m in METHODS}
    best = min(METHODS, key=lambda m: mean[m])
    for m in METHODS:                      # simplicity order: a simpler method within 2% wins
        if m == best:
            break
        if mean[m] <= 1.02 * mean[best]:
            return m
    return best


if __name__ == "__main__":
    snap_path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    with gzip.open(snap_path, "rt", encoding="utf-8") as fh:
        snap = json.load(fh)
    codes = snap["countries"]
    rows = errors(snap, codes)
    pooled = {m: {str(h): summary(rows, m, h, True) for h in H} for m in METHODS}
    pooled_all = {m: {str(h): summary(rows, m, h, False) for h in H} for m in METHODS}
    pick = choose(pooled)
    by_country, bands = {}, {}
    for c in codes:
        rc = [r for r in rows if r["c"] == c]
        if not rc:
            continue
        by_country[c] = {m: {str(h): summary(rc, m, h, True) for h in H} for m in METHODS}
        by_country[c]["origins"] = [min(r["t"] for r in rc), max(r["t"] for r in rc)]
        bands[c] = {str(h): quantiles([r[pick] for r in rc if r["h"] == h and not r["pandemic"]]) for h in H}
    pooled_bands = {str(h): quantiles([r[pick] for r in rows if r["h"] == h and not r["pandemic"]]) for h in H}
    res = {"study": "gdp_watch backtest v1", "snapshot": os.path.basename(snap_path), "as_of": snap["as_of"],
           "basis": __doc__.split("\n\n")[1].strip(), "first_origin": FIRST_ORIGIN, "window": WINDOW,
           "pandemic_targets_excluded": sorted(PANDEMIC), "chosen": pick,
           "pooled_ex_pandemic": pooled, "pooled_all": pooled_all, "by_country_ex_pandemic": by_country,
           "bands": bands, "bands_pooled": pooled_bands,
           "identity_residual": {c: identity_residual(snap, c) for c in codes}}
    with open(os.path.join(out, "backtest_v1.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    with gzip.open(os.path.join(out, "backtest_v1_errors.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump(rows, fh, separators=(",", ":"))
    print("chosen:", pick)
    for m in METHODS:
        print(m, " ".join(f"h{h} MAE {pooled[m][str(h)]['mae']} (all {pooled_all[m][str(h)]['mae']})" for h in H),
              "n", pooled[m]["1"]["n"])
