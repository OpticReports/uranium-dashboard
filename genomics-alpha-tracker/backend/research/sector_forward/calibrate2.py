"""Forward test, calibration part 2 (EXPLORATORY; added after part 1's result).

Part 1 (calibrate.py) found both trial-date rankings BELOW random and plain
60-day volatility far above it. These three checks were declared before
they were computed (DESIGN_SECTOR_FORWARD_TEST.md, calibration section):

  1. Excluding large caps (cap >= $10B on P): do R1 / R2 beat random?
  2. Name-day panel: does being in a readout window (an own phase 2/3 trial
     with primary completion in [P-120d, P+30d], status active or COMPLETED)
     raise the odds of a 20% move on the next trading day, given volatility
     and size? Mantel-Haenszel common odds ratio over strata of
     volatility quintile x cap tercile, 90% interval from a bootstrap that
     resamples NAMES (a name's days are not independent).
  3. Hybrid H1: readout-window names first, each group ordered by
     volatility. Hit@K vs B1, paired, all caps and small/mid caps.

Same universe, events and point-in-time catalyst data as part 1.

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.calibrate2
"""
from __future__ import annotations

import bisect
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from research.sector_forward import calibrate as K1  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402
from research.sector_tier import measure as M  # noqa: E402

OUT = HERE / "calibration2.json"
BIG = 10e9
KS = (10, 25, 40)
SEED = 20261006
BOOT = 1000


def mh_or(table: dict) -> float | None:
    """Mantel-Haenszel common odds ratio over strata {key: [a, b, c, d]}:
    a = exposed & event, b = exposed & no event, c = unexposed & event, d = unexposed & no event."""
    num = den = 0.0
    for a, b, c, d in table.values():
        n = a + b + c + d
        if n:
            num += a * d / n
            den += b * c / n
    return num / den if den else None


def main() -> None:
    import gzip
    labels = json.loads((K1.ST / "labels.json").read_text())
    aliases = json.loads((HERE / "aliases.json").read_text())
    ctg = M.load_ctgov()
    pit = dict(ctg["pit"])
    pit.update(json.loads(gzip.decompress(K1.PIT_EXTRA.read_bytes())))
    lag, _ = M.posting_lag(ctg["pit"], ctg["names"])
    trials = {s: M.Trials({"studies": K1.own_rows(s, aliases)}, pit, lag) for s in aliases}
    pop = {p["symbol"]: p for p in json.loads(P.OUT_POP.read_text())}
    series = {s: M.Series(s) for s in aliases}
    core = M.Core({})
    review = json.loads((K1.ST / "ma_review.json").read_text())
    moves = [m for m in json.loads(P.OUT_MOVES.read_text()) if not m.get("flag_artifact")]
    for m in moves:
        r = review.get(f"{m['symbol']}|{m['date']}")
        if r and r.get("ma") is not None:
            m["flag_ma"] = bool(r["ma"])
    ev = {(m["symbol"], m["prior_date"]) for m in moves
          if not m["flag_ma"] and (labels.get(m["symbol"]) or {}).get("genomics") and m["symbol"] in aliases}

    def listed(s, t):
        fb = series[s].first_bar()
        dd = M.d(pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    # trading days: P with a next trading day inside the window (from a name that traded throughout)
    ref = max(series.values(), key=lambda x: len(x.bdates)).bdates
    days = [ref[i] for i in range(len(ref) - 1) if M.WIN0 <= ref[i + 1] <= M.WIN1]

    rows = []   # (P, sym, vol, cap, readout, r1_days, event)
    for p in days:
        cs = core.symbols(p)
        w = p - timedelta(days=p.weekday())
        for s in aliases:
            if s in cs or not listed(s, p):
                continue
            cap = series[s].cap(p) or 0
            if cap < M.CAP_MIN:
                continue
            vol = K1.vol60(series[s], p)
            ro = K1.readout_key(trials[s], w, p) is not None
            k1 = trials[s].days_to_catalyst(w, p)
            rows.append((p, s, vol, cap, ro, k1, (s, p.isoformat()) in ev))
    n_ev = sum(r[6] for r in rows)
    print(f"panel: {len(rows)} name-days, {n_ev} events, {len(days)} days", flush=True)

    # ---- 1 and 3: rankings per day ----
    by_day = defaultdict(list)
    for r in rows:
        by_day[r[0]].append(r)
    res = {"panel_name_days": len(rows), "panel_events": n_ev, "days": len(days)}
    for scope in ("all", "small_mid"):
        hits = {k: defaultdict(int) for k in KS}
        pair = {k: [0, 0, 0] for k in KS}   # H1 only, B1 only, both
        n_scope = 0
        rnd = {k: 0.0 for k in KS}
        for p, rs in by_day.items():
            u = [r for r in rs if scope == "all" or r[3] < BIG]
            evs = [r for r in u if r[6]]
            if not evs:
                continue
            dv = {r[1]: series[r[1]].dollar_vol_20(p) for r in u}
            r1 = sorted(u, key=lambda r: (r[5] is None, r[5] or 0, -dv[r[1]]))
            b1 = sorted(u, key=lambda r: -r[2])
            h1 = sorted(u, key=lambda r: (not r[4], -r[2]))
            rk = {name: {r[1]: i + 1 for i, r in enumerate(lst)} for name, lst in (("R1", r1), ("B1", b1), ("H1", h1))}
            for e in evs:
                n_scope += 1
                for k in KS:
                    for name in ("R1", "B1", "H1"):
                        hits[k][name] += rk[name][e[1]] <= k
                    rnd[k] += min(1.0, k / len(u))
                    a, b = rk["H1"][e[1]] <= k, rk["B1"][e[1]] <= k
                    pair[k][0] += a and not b
                    pair[k][1] += b and not a
                    pair[k][2] += a and b
        res[f"rankings_{scope}"] = {"events": n_scope, **{str(k): {**{nm: round(hits[k][nm] / n_scope, 3) for nm in ("R1", "B1", "H1")},
                                                                    "random": round(rnd[k] / n_scope, 3),
                                                                    "H1_only_vs_B1_only_both": pair[k]} for k in KS}}

    # ---- 2: Mantel-Haenszel, readout window, strata = vol quintile x cap tercile ----
    vols = sorted(r[2] for r in rows)
    caps = sorted(r[3] for r in rows)
    vq = [vols[int(len(vols) * q / 5)] for q in range(1, 5)]
    ct = [caps[int(len(caps) * q / 3)] for q in range(1, 3)]

    def stratum(r):
        return (bisect.bisect_right(vq, r[2]), bisect.bisect_right(ct, r[3]))

    def table(rs):
        t = defaultdict(lambda: [0, 0, 0, 0])
        for r in rs:
            cell = t[stratum(r)]
            cell[(0 if r[4] else 2) + (0 if r[6] else 1)] += 1
        return t

    est = mh_or(table(rows))
    names = sorted({r[1] for r in rows})
    by_name = defaultdict(list)
    for r in rows:
        by_name[r[1]].append(r)
    rng = random.Random(SEED)
    boots = []
    for _ in range(BOOT):
        pick = [rng.choice(names) for _ in names]
        o = mh_or(table([r for s in pick for r in by_name[s]]))
        if o is not None and math.isfinite(o):
            boots.append(o)
    boots.sort()
    exp_rows = [r for r in rows if r[4]]
    res["readout_window_mh"] = {
        "odds_ratio": round(est, 3) if est else None,
        "ci90_name_bootstrap": [round(boots[int(0.05 * len(boots))], 3), round(boots[int(0.95 * len(boots)) - 1], 3)] if boots else None,
        "name_days_in_window": len(exp_rows), "events_in_window": sum(r[6] for r in exp_rows),
        "event_rate_in_window": round(sum(r[6] for r in exp_rows) / max(1, len(exp_rows)), 5),
        "event_rate_outside": round(sum(r[6] for r in rows if not r[4]) / max(1, len(rows) - len(exp_rows)), 5),
        "strata": "vol60 quintile x cap tercile (pooled over the panel)"}
    # volatility's own gradient, for scale: event rate by vol quintile
    vqr = defaultdict(lambda: [0, 0])
    for r in rows:
        q = bisect.bisect_right(vq, r[2])
        vqr[q][0] += r[6]
        vqr[q][1] += 1
    res["event_rate_by_vol_quintile"] = {q + 1: round(a / b, 5) for q, (a, b) in sorted(vqr.items())}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
