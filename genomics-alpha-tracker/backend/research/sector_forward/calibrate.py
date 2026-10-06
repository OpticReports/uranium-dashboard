"""Forward test, setup step 2: CALIBRATION on the past year (exploratory, not a result).

Purpose: set the forward test's free parameters - which of two candidate
rankings, the list length K, the duration - from last year's data, so the
forward test is a single confirmatory comparison. Nothing here is a
finding; labels and the alias table are as of 2026-10-06 (look-ahead), and
the ranking with the better past is expected to look worse forward.

Universe on day P: genomics-labelled names (stage 3 labels), NOT in the core
on P, listed, prior-day cap >= $300M. Events: their one-day adjusted 20%
moves, M&A target days excluded (the sector-tier moves.json + hand check).

Rankings on the prior trading day P (catalyst data as of the Monday on or
before P, the weekly CT.gov refresh):
  R1 catalyst    days to the nearest primary completion date on or after P of
                 an own phase 2/3 trial with an active status; ties by 20-day
                 dollar volume; names without one last (by dollar volume).
  R2 readout     an own phase 2/3 trial whose primary completion falls in
                 [P-120d, P+30d] and whose status is active or COMPLETED (a
                 readout is typically due weeks to months after primary
                 completion): phase 3 before phase 2, then nearest first;
                 names without one last (by dollar volume).
  B1 volatility  60-trading-day realized volatility of daily log returns, desc.
  random         K / |universe| (expected hit rate).
Own trials use the alias table (aliases.json). Point-in-time records come
from the sector-tier history plus histories fetched here for studies the
alias table newly attributes (same method, same 12-day posting lag).

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.calibrate
"""
from __future__ import annotations

import bisect
import gzip
import json
import math
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion import discovery as D  # noqa: E402
from research.sector_forward.build_aliases import sponsors_of  # noqa: E402
from research.sector_tier import build_ctgov as C  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402
from research.sector_tier import measure as M  # noqa: E402

ST = BACKEND / "research" / "sector_tier"
PIT_EXTRA = HERE / "pit_extra.json.gz"
OUT = HERE / "calibration.json"
KS = (10, 15, 25, 40)
WINDOW_BACK, WINDOW_FWD = 120, 30
SEED = 20261006


def own_rows(sym: str, aliases: dict) -> list[dict]:
    al = set(aliases[sym]["aliases"])
    rows, seen = [], set()
    for q in aliases[sym]["queries"]:
        for st in C.search_name(q):
            r = C.compact(st, q)
            if not r["nct"] or r["nct"] in seen:
                continue
            seen.add(r["nct"])
            if set(sponsors_of(st)) & al:
                r["own"] = True
                r["own_p23"] = C.is_p23(r) and (r.get("type") in (None, "INTERVENTIONAL"))
                rows.append(r)
    return rows


def fetch_extra(need: list[str]) -> dict:
    have = json.loads(gzip.decompress(PIT_EXTRA.read_bytes())) if PIT_EXTRA.exists() else {}
    todo = [n for n in need if n not in have]
    print(f"extra histories: {len(have)} cached, {len(todo)} to fetch", flush=True)
    counters: Counter = Counter()
    with ThreadPoolExecutor(max_workers=C.WORKERS) as ex:
        for n, res in zip(todo, ex.map(lambda n: C.pit_history(n, counters), todo)):
            if res is not None:
                have[n] = res
    PIT_EXTRA.write_bytes(gzip.compress(json.dumps(have).encode()))
    print(f"  fetched; counters {dict(counters)}", flush=True)
    return have


def vol60(ser: M.Series, p: date) -> float:
    i = bisect.bisect_right(ser.bdates, p)
    c = ser.close[max(0, i - 61):i]
    r = [math.log(c[k] / c[k - 1]) for k in range(1, len(c)) if c[k - 1] > 0 and c[k] > 0]
    if len(r) < 20:
        return 0.0
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def readout_key(tr: M.Trials, w: date, p: date):
    best = None
    for r in tr.rows:
        if not r.get("own_p23"):
            continue
        s = tr.state(r, w)
        if not s or s[0] not in (M.ACTIVE | {"COMPLETED"}):
            continue
        pcd = D._parse_loose_date(s[1])
        if pcd is None or not (p - timedelta(days=WINDOW_BACK) <= pcd <= p + timedelta(days=WINDOW_FWD)):
            continue
        k = (0 if "PHASE3" in "/".join(s[2] or r["phases"]) else 1, abs((pcd - p).days))
        best = k if best is None or k < best else best
    return best


def main() -> None:
    labels = json.loads((ST / "labels.json").read_text())
    aliases = json.loads((HERE / "aliases.json").read_text())
    ctg = M.load_ctgov()
    pit = dict(ctg["pit"])
    rows = {s: own_rows(s, aliases) for s in aliases}
    need = []
    for s, rs in rows.items():
        cand = [r for r in rs if r.get("own_p23") and C.needs_pit(r) and r["nct"] not in pit]
        cand.sort(key=lambda r: r["last_update"], reverse=True)
        cand.sort(key=lambda r: not any("PHASE3" in p for p in r["phases"]))
        need += [r["nct"] for r in cand[:C.MAX_PIT_PER_NAME]]
    pit.update(fetch_extra(sorted(set(need))))
    lag, _ = M.posting_lag(ctg["pit"], ctg["names"])
    trials = {s: M.Trials({"studies": rs}, pit, lag) for s, rs in rows.items()}

    pop = {p["symbol"]: p for p in json.loads(P.OUT_POP.read_text())}
    series = {s: M.Series(s) for s in aliases}
    core = M.Core({})
    review = json.loads((ST / "ma_review.json").read_text())
    moves = [m for m in json.loads(P.OUT_MOVES.read_text()) if not m.get("flag_artifact")]
    for m in moves:
        r = review.get(f"{m['symbol']}|{m['date']}")
        if r and r.get("ma") is not None:
            m["flag_ma"] = bool(r["ma"])

    def listed(s, t):
        fb = series[s].first_bar()
        dd = M.d(pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    def universe(p: date) -> list[str]:
        cs = core.symbols(p)
        return [s for s in aliases if s not in cs and listed(s, p) and (series[s].cap(p) or 0) >= M.CAP_MIN]

    def monday(p: date) -> date:
        return p - timedelta(days=p.weekday())

    cache: dict = {}

    def ranks(p: date) -> dict:
        if p in cache:
            return cache[p]
        u, w = universe(p), monday(p)
        dv = {s: series[s].dollar_vol_20(p) for s in u}
        k1 = {s: trials[s].days_to_catalyst(w, p) for s in u}
        r1 = sorted(u, key=lambda s: (k1[s] is None, k1[s] or 0, -dv[s]))
        k2 = {s: readout_key(trials[s], w, p) for s in u}
        r2 = sorted(u, key=lambda s: (k2[s] is None, k2[s] or (0, 0), -dv[s]))
        vv = {s: vol60(series[s], p) for s in u}
        b1 = sorted(u, key=lambda s: -vv[s])
        cache[p] = {"n": len(u), "R1": {s: i + 1 for i, s in enumerate(r1)}, "R2": {s: i + 1 for i, s in enumerate(r2)},
                    "B1": {s: i + 1 for i, s in enumerate(b1)}, "dated_R1": sum(v is not None for v in k1.values()),
                    "in_window_R2": sum(v is not None for v in k2.values())}
        return cache[p]

    events = []
    for m in moves:
        s = m["symbol"]
        if m["flag_ma"] or not (labels.get(s) or {}).get("genomics") or s not in aliases:
            continue
        p = M.d(m["prior_date"])
        if s in core.symbols(p):
            continue
        rk = ranks(p)
        if s not in rk["R1"]:
            continue
        events.append({"id": f"{s}|{m['date']}", "ret": m["ret"], "n": rk["n"],
                       **{k: rk[k][s] for k in ("R1", "R2", "B1")}})
    n = len(events)
    months = 12.0
    res = {"events": n, "events_per_month": round(n / months, 2),
           "universe_mean": round(sum(e["n"] for e in events) / n, 1) if n else None,
           "hit_rate": {}, "paired_vs_B1": {}, "power": {}}
    for K in KS:
        hr = {k: sum(e[k] <= K for e in events) / n for k in ("R1", "R2", "B1")}
        hr["random"] = sum(min(1.0, K / e["n"]) for e in events) / n
        res["hit_rate"][K] = {k: round(v, 3) for k, v in hr.items()}
        for k in ("R1", "R2"):
            b = sum(e[k] <= K < e["B1"] for e in events)
            c = sum(e["B1"] <= K < e[k] for e in events)
            res["paired_vs_B1"][f"{k}@{K}"] = {"ranking_only": b, "B1_only": c, "both": sum(e[k] <= K and e["B1"] <= K for e in events)}
    # power of a one-sided exact sign test on discordant events, by simulation
    rng = random.Random(SEED)

    def power(pb: float, pc: float, n_ev: int, sims: int = 4000, alpha: float = 0.05) -> float:
        def crit(m):
            # smallest b with P(Bin(m, .5) >= b) <= alpha
            tail, b = 0.0, m
            probs = [math.comb(m, j) / 2 ** m for j in range(m + 1)]
            acc = 0.0
            for j in range(m, -1, -1):
                acc += probs[j]
                if acc > alpha:
                    return j + 1
            return 0
        hits = 0
        for _ in range(sims):
            b = c = 0
            for _ in range(n_ev):
                u = rng.random()
                if u < pb:
                    b += 1
                elif u < pb + pc:
                    c += 1
            m = b + c
            if m and b >= crit(m):
                hits += 1
        return hits / sims

    for K in KS:
        for k in ("R1", "R2"):
            d = res["paired_vs_B1"][f"{k}@{K}"]
            pb, pc = d["ranking_only"] / n, d["B1_only"] / n
            res["power"][f"{k}@{K}"] = {f"{mo}mo": round(power(pb, pc, round(res['events_per_month'] * mo)), 2)
                                        for mo in (6, 9, 12)} if pb > pc else "ranking not ahead of B1 in calibration"
    res["events_detail"] = events
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "events_detail"}, indent=1))


if __name__ == "__main__":
    main()
