#!/usr/bin/env python3
"""POST-BLOWOFF ROLLOVER state — pre-registered rule + historical scoring.

A-PRIORI RULE (frozen 2026-08-15, BEFORE any forward statistic was computed;
thresholds of the existing level states are unchanged):
- level(t) = existing leverage_state(yoy, excess)  (WASHOUT/SQUEEZE/BLOWOFF/
  ELEVATED/NEUTRAL, crossasset.py:128).
- POST_BLOWOFF: level(t) in {ELEVATED, NEUTRAL} AND some month within the
  trailing 6 months (t-6..t-1) had level BLOWOFF. Window W=6 chosen a priori
  (FINRA cadence: two quarters to resolve). Path anchor uses ONLY past
  months — no lookahead.
- Precedence: SQUEEZE/WASHOUT (yoy<0) and BLOWOFF always win — re-inflation
  (excess back >= +25pp or yoy >= 40) returns to BLOWOFF and re-anchors the
  window; yoy < 0 hands off to SQUEEZE. A rollover that sits in ELEVATED/
  NEUTRAL beyond 6 months FIZZLES back to its plain level state.
- Scoring: monthly, FINRA era (1997+), forward 3/6/12m ^GSPC price returns
  (same "S&P higher/lower" direction basis as the existing playbook table);
  overlapping windows -> descriptive; episode-level permutation p for the
  fwd12 mean vs all-months baseline (4000 draws, episodes = contiguous runs).
"""
import json
import os
import sys

import httpx
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.metrics.crossasset import leverage_state  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0"}
W = 6


def path_states(levels: list) -> list:
    out, last_blow = [], None
    for i, lvl in enumerate(levels):
        if lvl == "BLOWOFF":
            last_blow = i
        if (lvl in ("ELEVATED", "NEUTRAL") and last_blow is not None
                and 1 <= i - last_blow <= W):
            out.append("POST_BLOWOFF")
        else:
            out.append(lvl)
    return out


def main() -> None:
    lev = httpx.get("https://treasury-canary.onrender.com/margin/leverage",
                    timeout=120, headers=UA,
                    verify="/root/.ccr/ca-bundle.crt").json()
    series = [p for p in lev["series"] if p["margin_yoy"] is not None]
    months = [p["date"][:7] for p in series]
    levels = [leverage_state(p["margin_yoy"], p["excess_yoy"]) for p in series]
    paths = path_states(levels)

    r = httpx.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
                  params={"range": "35y", "interval": "1mo"}, headers=UA,
                  timeout=60, verify="/root/.ccr/ca-bundle.crt").json()
    res = r["chart"]["result"][0]
    import datetime as dt
    spx = {}
    for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c:
            spx[dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m")] = c

    def fwd(m, h):
        y, mo = int(m[:4]), int(m[5:7])
        mo2 = mo + h
        t = f"{y + (mo2 - 1) // 12:04d}-{(mo2 - 1) % 12 + 1:02d}"
        return (spx[t] / spx[m] - 1) * 100 if (m in spx and t in spx) else None

    # FINRA era only (match existing playbook basis)
    idx = [i for i, m in enumerate(months) if m >= "1997-01"]
    rows = {"POST_BLOWOFF": [], "_ALL": []}
    for i in idx:
        f = {h: fwd(months[i], h) for h in (3, 6, 12)}
        rows["_ALL"].append(f)
        if paths[i] == "POST_BLOWOFF":
            rows["POST_BLOWOFF"].append((months[i], f))

    pb = rows["POST_BLOWOFF"]
    eps, cur = [], []
    for i in idx:
        if paths[i] == "POST_BLOWOFF":
            cur.append(months[i])
        elif cur:
            eps.append(cur)
            cur = []
    if cur:
        eps.append(cur)

    def stats(h):
        v = [f[h] for _, f in pb if f[h] is not None]
        return {"n": len(v), "mean": round(float(np.mean(v)), 1),
                "median": round(float(np.median(v)), 1),
                "pct_lower": round(100 * float(np.mean(np.array(v) < 0))),
                "worst": round(float(np.min(v)), 1)} if v else None

    out = {"rule": "POST_BLOWOFF = level in {ELEVATED,NEUTRAL} and BLOWOFF "
                   f"within trailing {W} months; frozen before scoring",
           "months": [m for m, _ in pb], "n_months": len(pb),
           "episodes": [[e[0], e[-1]] for e in eps], "n_episodes": len(eps),
           "fwd3": stats(3), "fwd6": stats(6), "fwd12": stats(12)}

    v12 = np.array([f[12] for _, f in pb if f[12] is not None])
    all12 = np.array([f[12] for f in rows["_ALL"] if f[12] is not None])
    if len(v12) and len(eps):
        rng = np.random.default_rng(20260815)
        sizes = [len(e) for e in eps]
        draws = []
        for _ in range(4000):
            sim = []
            for s in sizes:
                st = rng.integers(0, max(len(all12) - s, 1))
                sim.extend(all12[st:st + s])
            draws.append(np.mean(sim))
        p = float(np.mean(np.array(draws) <= v12.mean()))
        out["fwd12_vs_baseline"] = {"state_mean": round(float(v12.mean()), 1),
                                    "baseline_mean": round(float(all12.mean()), 1),
                                    "perm_p_lower": round(p, 3)}
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
              "post_blowoff_study.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
