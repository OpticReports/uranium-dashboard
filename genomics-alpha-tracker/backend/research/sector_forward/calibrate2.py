"""Forward test, calibration part 2 (EXPLORATORY; written after part 1's result).

Part 1 (calibrate.py) found both trial-date rankings BELOW random and plain
60-day volatility far above it. The checks below were written into this
docstring after part 1 was seen; no separate commit witnesses that order.
Checks 4 and 5 were added after the counter-agent review (2026-10-06).

Events follow the forward protocol: de-clustered (a name's further 20%
moves within the next 10 of its trading days are not counted; those name-days
also leave the panel). The un-de-clustered figures are kept beside them.

  1. Excluding large caps (cap >= $10B on P): do R1 / R2 beat random?
  2. Name-day panel: does being in a readout window (an own phase 2/3 trial
     with primary completion in [P-120d, P+30d], status active or COMPLETED)
     raise the odds of a 20% move on the next trading day, given volatility
     and size? Mantel-Haenszel common odds ratio over volatility quintile x
     cap tercile, 90% interval from a bootstrap over NAMES.
  3. Hybrid H1 (readout-window names first, each group by volatility) vs B1,
     paired, at K = 10 / 25 / 40, with exact one-sided sign tests and the
     forward power of half the in-sample edge (discordance held fixed).
  4. Coverage: events with a dated upcoming own phase 2/3 completion on P.
  5. (review) B1's hits split by whether the name moved 20% in the prior 60
     trading days, and B1x - 60-day volatility excluding days with a move
     of 20% or more - as a jump-robust volatility.

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.calibrate2
"""
from __future__ import annotations

import bisect
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from datetime import timedelta
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
DECLUSTER = 10      # trading days
ALPHA = 0.05


def mh_or(table: dict) -> float | None:
    """Mantel-Haenszel common odds ratio over strata {key: [a, b, c, d]}."""
    num = den = 0.0
    for a, b, c, d in table.values():
        n = a + b + c + d
        if n:
            num += a * d / n
            den += b * c / n
    return num / den if den else None


def sign_p(b: int, c: int) -> float:
    """One-sided exact sign test P(X >= b | Bin(b + c, 1/2))."""
    m = b + c
    return sum(math.comb(m, j) for j in range(b, m + 1)) / 2 ** m if m else 1.0


def _logpmf(n: int, k: int, p: float) -> float:
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log1p(-p)


def _crit(m: int) -> int:
    """Smallest b with P(Bin(m, 1/2) >= b) <= ALPHA."""
    acc = 0.0
    for j in range(m, -1, -1):
        acc += math.exp(_logpmf(m, j, 0.5))
        if acc > ALPHA:
            return j + 1
    return 0


def power(pb: float, pc: float, n: int) -> float:
    """Exact power of the one-sided sign test with n events, per-event
    probabilities pb (ranking-only hit) and pc (baseline-only hit)."""
    d = pb + pc
    if d <= 0 or pb <= pc:
        return 0.0
    q = pb / d
    tot = 0.0
    for m in range(0, n + 1):
        pm = math.exp(_logpmf(n, m, d))
        if pm < 1e-12:
            continue
        cr = _crit(m) if m else 1
        tail = sum(math.exp(_logpmf(m, j, q)) for j in range(cr, m + 1)) if m else 0.0
        tot += pm * tail
    return tot


def half_edge(pb: float, pc: float) -> tuple[float, float]:
    d, e = pb + pc, pb - pc
    return d / 2 + e / 4, d / 2 - e / 4


def months_to_power(pb: float, pc: float, per_month: float, target: float = 0.8, cap_months: int = 360) -> int | None:
    for mo in range(1, cap_months + 1):
        if power(pb, pc, round(per_month * mo)) >= target:
            return mo
    return None


def vol60x(ser: M.Series, p) -> float:
    """60-day volatility excluding returns of 20% or more (jump-robust)."""
    i = bisect.bisect_right(ser.bdates, p)
    c = ser.close[max(0, i - 61):i]
    r = [math.log(c[k] / c[k - 1]) for k in range(1, len(c)) if c[k - 1] > 0 and c[k] > 0]
    r = [x for x in r if abs(math.exp(x) - 1) < 0.20]
    if len(r) < 20:
        return 0.0
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def main() -> None:
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
    gm = [m for m in moves if not m["flag_ma"] and (labels.get(m["symbol"]) or {}).get("genomics") and m["symbol"] in aliases]

    # de-clustering on each name's own trading calendar
    follow_on: set[tuple[str, str]] = set()       # (sym, prior_date) of follow-on events
    quiet: dict[str, list[tuple]] = defaultdict(list)  # sym -> [(first_excluded_prior, last_excluded_prior)]
    for s in {m["symbol"] for m in gm}:
        bd = series[s].bdates
        last_idx = None
        for m in sorted((m for m in gm if m["symbol"] == s), key=lambda m: m["date"]):
            i = bisect.bisect_left(bd, M.d(m["date"]))
            if last_idx is not None and i - last_idx <= DECLUSTER:
                follow_on.add((s, m["prior_date"]))
                continue
            last_idx = i
            # name-days whose next day falls in (event, event + 10 trading days] leave the panel
            lo, hi = i + 1, min(len(bd) - 1, i + DECLUSTER)   # next day in (event, event + 10]
            if lo < len(bd):
                quiet[s].append((bd[lo], bd[hi]))
    ev_all = {(m["symbol"], m["prior_date"]) for m in gm}
    recent20 = defaultdict(list)    # sym -> dates of any own 20% move (any label), for the fresh/recent split
    for m in moves:
        recent20[m["symbol"]].append(M.d(m["date"]))

    def listed(s, t):
        fb = series[s].first_bar()
        dd = M.d(pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    ref = max(series.values(), key=lambda x: len(x.bdates)).bdates
    days = [ref[i] for i in range(len(ref) - 1) if M.WIN0 <= ref[i + 1] <= M.WIN1]

    rows = []   # dict per name-day
    for p in days:
        cs = core.symbols(p)
        w = p - timedelta(days=p.weekday())
        for s in aliases:
            if s in cs or not listed(s, p):
                continue
            cap = series[s].cap(p) or 0
            if cap < M.CAP_MIN:
                continue
            ser = series[s]
            i = bisect.bisect_right(ser.bdates, p)
            p_idx = i - 1
            win60_start = ser.bdates[max(0, p_idx - 59)] if p_idx >= 0 else p
            is_ev = (s, p.isoformat()) in ev_all
            in_quiet = any(lo <= ser.bdates[min(p_idx + 1, len(ser.bdates) - 1)] <= hi for lo, hi in quiet.get(s, [])) \
                if p_idx + 1 < len(ser.bdates) else False
            rows.append({"p": p, "s": s, "vol": K1.vol60(ser, p), "volx": vol60x(ser, p), "cap": cap,
                         "ro": K1.readout_key(trials[s], w, p) is not None, "k1": trials[s].days_to_catalyst(w, p),
                         "ev": is_ev, "follow": (s, p.isoformat()) in follow_on, "quiet": in_quiet and not is_ev,
                         "recent": any(win60_start <= t <= p for t in recent20.get(s, [])),
                         "own_p23": sum(1 for r in trials[s].rows if r.get("own_p23"))})
    print(f"panel: {len(rows)} name-days, {sum(r['ev'] for r in rows)} events "
          f"({sum(r['ev'] and r['follow'] for r in rows)} follow-ons), {len(days)} days", flush=True)

    res = {"panel_name_days": len(rows), "days": len(days), "decluster_trading_days": DECLUSTER,
           "follow_on_events": sorted(f"{s}|{d}" for s, d in follow_on)}

    def rank_block(declustered: bool, scope: str) -> dict:
        by_day = defaultdict(list)
        for r in rows:
            by_day[r["p"]].append(r)
        names = ("R1", "R2", "B1", "B1x", "H1")
        hits = {k: defaultdict(int) for k in KS}
        pair = {k: [0, 0, 0] for k in KS}
        pairx = {k: [0, 0, 0] for k in KS}   # H1 vs B1x
        big_in_r1 = [0, 0]                    # R1 top-25 slots held by names >= $10B
        rnd = {k: 0.0 for k in KS}
        split = {"recent": defaultdict(int), "fresh": defaultdict(int)}
        n_split = {"recent": 0, "fresh": 0}
        rnd_split = {"recent": 0.0, "fresh": 0.0}
        n = 0
        for p, rs in by_day.items():
            u = [r for r in rs if scope == "all" or r["cap"] < BIG]
            evs = [r for r in u if r["ev"] and not (declustered and r["follow"])]
            if not evs:
                continue
            dv = {r["s"]: series[r["s"]].dollar_vol_20(p) for r in u}
            w = p - timedelta(days=p.weekday())
            k2 = {r["s"]: K1.readout_key(trials[r["s"]], w, p) for r in u}
            order = {
                "R1": sorted(u, key=lambda r: (r["k1"] is None, r["k1"] or 0, -dv[r["s"]])),
                "R2": sorted(u, key=lambda r: (k2[r["s"]] is None, k2[r["s"]] or (0, 0), -dv[r["s"]])),
                "B1": sorted(u, key=lambda r: -r["vol"]),
                "B1x": sorted(u, key=lambda r: -r["volx"]),
                "H1": sorted(u, key=lambda r: (not r["ro"], -r["vol"])),
            }
            rk = {nm: {r["s"]: i + 1 for i, r in enumerate(lst)} for nm, lst in order.items()}
            top = order["R1"][:25]
            big_in_r1[0] += sum(r["cap"] >= BIG for r in top)
            big_in_r1[1] += len(top)
            for e in evs:
                n += 1
                grp = "recent" if e["recent"] else "fresh"
                n_split[grp] += 1
                rnd_split[grp] += min(1.0, 25 / len(u))
                for nm in names:
                    split[grp][nm] += rk[nm][e["s"]] <= 25
                for k in KS:
                    for nm in names:
                        hits[k][nm] += rk[nm][e["s"]] <= k
                    rnd[k] += min(1.0, k / len(u))
                    a, b = rk["H1"][e["s"]] <= k, rk["B1"][e["s"]] <= k
                    pair[k][0] += a and not b
                    pair[k][1] += b and not a
                    pair[k][2] += a and b
                    bx = rk["B1x"][e["s"]] <= k
                    pairx[k][0] += a and not bx
                    pairx[k][1] += bx and not a
                    pairx[k][2] += a and bx
        out = {"events": n, "events_per_month": round(n / 12, 2),
               "R1_top25_share_over_10B_on_event_days": round(big_in_r1[0] / max(1, big_in_r1[1]), 3)}
        for k in KS:
            b, c, both = pair[k]
            blk = {nm: round(hits[k][nm] / n, 3) for nm in names}
            blk["random"] = round(rnd[k] / n, 3)
            blk["H1_only_vs_B1_only_both"] = pair[k]
            blk["sign_test_p_H1_over_B1"] = round(sign_p(b, c), 4)
            blk["sign_test_p_B1_over_H1"] = round(sign_p(c, b), 4)
            if b > c:
                hb, hc = half_edge(b / n, c / n)
                blk["power_half_edge"] = {f"{mo}mo": round(power(hb, hc, round(n / 12 * mo)), 3) for mo in (12, 24, 60)}
                blk["months_to_80pct_power_half_edge"] = months_to_power(hb, hc, n / 12)
            bx_b, bx_c, _ = pairx[k]
            blk["H1_only_vs_B1x_only_both"] = pairx[k]
            blk["sign_test_p_H1_over_B1x"] = round(sign_p(bx_b, bx_c), 4)
            if bx_b > bx_c:
                hb, hc = half_edge(bx_b / n, bx_c / n)
                blk["months_to_80pct_power_half_edge_vs_B1x"] = months_to_power(hb, hc, n / 12)
            out[str(k)] = blk
        out["top25_by_recent_20pct_move"] = {g: {"events": n_split[g], **{nm: round(split[g][nm] / max(1, n_split[g]), 3) for nm in names},
                                                 "random": round(rnd_split[g] / max(1, n_split[g]), 3)} for g in ("recent", "fresh")}
        return out

    for dc in (True, False):
        for scope in ("all", "small_mid"):
            res[f"rankings_{scope}{'' if dc else '_not_declustered'}"] = rank_block(dc, scope)

    # ---- Mantel-Haenszel (declustered panel: follow-on and quiet name-days removed) ----
    def mh_block(panel: list[dict]) -> dict:
        vols = sorted(r["vol"] for r in panel)
        caps = sorted(r["cap"] for r in panel)
        vq = [vols[int(len(vols) * q / 5)] for q in range(1, 5)]
        ct = [caps[int(len(caps) * q / 3)] for q in range(1, 3)]

        def table(rs):
            t = defaultdict(lambda: [0, 0, 0, 0])
            for r in rs:
                t[(bisect.bisect_right(vq, r["vol"]), bisect.bisect_right(ct, r["cap"]))][(0 if r["ro"] else 2) + (0 if r["ev"] else 1)] += 1
            return t
        est = mh_or(table(panel))
        by_name = defaultdict(list)
        for r in panel:
            by_name[r["s"]].append(r)
        names = sorted(by_name)
        rng = random.Random(SEED)
        boots = []
        for _ in range(BOOT):
            pick = [rng.choice(names) for _ in names]
            o = mh_or(table([r for s in pick for r in by_name[s]]))
            if o is not None and math.isfinite(o):
                boots.append(o)
        boots.sort()
        ex = [r for r in panel if r["ro"]]
        vqr = defaultdict(lambda: [0, 0])
        for r in panel:
            q = bisect.bisect_right(vq, r["vol"])
            vqr[q][0] += r["ev"]
            vqr[q][1] += 1
        return {"name_days": len(panel), "events": sum(r["ev"] for r in panel),
                "odds_ratio": round(est, 3) if est else None,
                "ci90_name_bootstrap": [round(boots[int(0.05 * len(boots))], 3), round(boots[int(0.95 * len(boots)) - 1], 3)] if boots else None,
                "name_days_in_window": len(ex), "events_in_window": sum(r["ev"] for r in ex),
                "event_rate_by_vol_quintile": {q + 1: round(a / b, 5) for q, (a, b) in sorted(vqr.items())},
                "strata": "vol60 quintile x cap tercile (cut points pooled over the panel)"}

    res["readout_window_mh"] = mh_block([r for r in rows if not r["follow"] and not r["quiet"]])
    res["readout_window_mh_not_declustered"] = mh_block(rows)
    res["readout_window_mh_small_mid"] = mh_block([r for r in rows if not r["follow"] and not r["quiet"] and r["cap"] < BIG])

    # ---- 4: coverage of trial data on event days (declustered events, all caps) ----
    evr = [r for r in rows if r["ev"] and not r["follow"]]
    res["coverage"] = {"events": len(evr), "with_dated_upcoming_completion": sum(r["k1"] is not None for r in evr),
                       "no_own_phase23_trial": {"events": sum(r["own_p23"] == 0 for r in evr),
                                                "names": sorted({r["s"] for r in evr if r["own_p23"] == 0})},
                       "trials_but_none_upcoming": {"events": sum(r["own_p23"] > 0 and r["k1"] is None for r in evr),
                                                    "names": sorted({r["s"] for r in evr if r["own_p23"] > 0 and r["k1"] is None})},
                       "distinct_names": len({r["s"] for r in evr})}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main()
