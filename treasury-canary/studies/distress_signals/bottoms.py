#!/usr/bin/env python3
"""studies/distress-bottoms.md, SPEC v1: does the roll-over of failure /
bankruptcy growth mark the bottom?

    python3 bottoms.py            # THE run -> bottoms_results.json

Run once, after SPEC v1 and bottoms_power.json (which fixes theta_A, the floor
and which shots are reachable) are committed. bottoms_power.py scores
synthetic series with the same functions (score_p).
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bottoms_engine as B  # noqa: E402
import engine as E  # noqa: E402
import load as D  # noqa: E402
from engine import M, mstr  # noqa: E402
from study import NBER_PRE  # noqa: E402

SEED = 20261012
PERMS = int(os.environ.get("BOTTOMS_PERMS", 10_000))
CHRON = sorted(NBER_PRE + E.PEAKS)
TROUGHS = [t for _, t in CHRON]
EXCLUDED = {M(1945, 2), M(2020, 2)}
WAR = {M(1918, 8), M(1948, 11)}
P_EPISODES = [(p, t) for p, t in CHRON if M(1895, 12) <= p <= M(1960, 4) and p not in EXCLUDED]
SHOTS = {"MARKS-trough": ("trough", -6, 3), "CONFIRMS-trough": ("trough", 0, 9),
         "MARKS-equity": ("equity", -3, 3)}
GRID_SHIFT = {3: -2, 6: 0, 12: 3}       # noise-free offset of each w from w = 6 (SPEC v1 s.1)
TRUE_BOTTOM = (-6, 9)                     # union of the trough windows


def centre(lo: int, hi: int) -> int:
    return B.half_up((lo + hi) / 2)


def next_peak(p: int) -> int | None:
    later = [q for q, _ in CHRON if q > p]
    return later[0] if later else None


def window_end(p: int, tau: int) -> int:
    nxt = next_peak(p)
    return min(tau + 24, nxt - 1) if nxt is not None else tau + 24


def load_params() -> dict:
    """theta_A, the floor and the reachable shots, frozen by bottoms_power.py."""
    with open(os.path.join(HERE, "bottoms_power.json")) as f:
        pw = json.load(f)
    return {"theta": pw["calibration"]["theta"], "floor": pw["calibration"]["floor"],
            "reachable": pw["reachability"]["reachable"]}


# ------------------------------------------------------------------ equity targets
def equity_targets(P: dict[int, float]) -> dict[int, dict]:
    """b_r per recession (keyed by peak) with validity, ambiguity and censoring."""
    out = {}
    for p, tau in CHRON:
        nxt = next_peak(p)
        lo, hi = p - 6, (min(tau + 12, nxt - 1) if nxt else tau + 12)
        ms = [m for m in range(lo, hi + 1) if m in P]
        if not ms:
            out[p] = {"b": None, "status": "no data"}
            continue
        b = min(ms, key=lambda m: (P[m], m))
        prior = [P[m] for m in range(b - 12, b) if m in P]
        valid = b not in (ms[0], ms[-1]) and bool(prior) and P[b] <= 0.9 * max(prior)
        zone = [m for m in ms if P[m] <= 1.03 * P[b]]
        status = "valid" if valid else "no equity low"
        if valid and any(abs(m - b) > 3 for m in zone):
            status = "ambiguous"
        if valid and p == M(1913, 1):
            status = "censored"            # exchange closed Aug-Nov 1914
        out[p] = {"b": b, "window": [lo, hi], "status": status,
                  "decline_from_12m_high": (P[b] / max(prior) - 1) if prior else None,
                  "zone": [mstr(m) for m in zone]}
    return out


# ------------------------------------------------------------------ series per span
def spans_p(segs: list[dict[int, float]], hard_1933: bool = True, b_for_1937: bool = True,
            mask: set[int] = frozenset()) -> list[dict]:
    """The P spans: A (split at 1933-01 when hard_1933), B, C; each with its own
    month range. Episodes pick their span by date (episode_span)."""
    a, b, c = segs
    a = {m: v for m, v in a.items() if m not in mask}
    spans = []
    if hard_1933:
        spans.append({"name": "A1", "values": {m: v for m, v in a.items() if m < M(1933, 1)}})
        spans.append({"name": "A2", "values": {m: v for m, v in a.items() if m >= M(1933, 1)}})
    else:
        spans.append({"name": "A", "values": a})
    spans.append({"name": "B", "values": dict(b)})
    spans.append({"name": "C", "values": dict(c)})
    for s in spans:
        s["range"] = (min(s["values"]), max(s["values"]))
    return spans


def episode_span(spans: list[dict], p: int, use_b: bool = True) -> list[dict]:
    """Spans an episode's window draws on, in order."""
    names = [s["name"] for s in spans]
    if p >= M(1948, 1):
        want = ["C"]
    elif p == M(1937, 5):
        want = ["B"] if use_b else (["A2"] if "A2" in names else ["A"])
    else:
        want = ["A1", "A2"] if "A1" in names else ["A"]
    return [s for s in spans if s["name"] in want]


def growth_by_span(spans: list[dict], rule: B.Rule, bad: set[int] = frozenset()) -> dict[str, dict]:
    out = {}
    for s in spans:
        g = B.growth(s["values"], rule, bad=bad, span=s["range"])
        periods = range(s["range"][0], s["range"][1] + 1)
        out[s["name"]] = {"g": g, "signals": B.signals(g, periods, rule), "range": s["range"]}
    return out


# ------------------------------------------------------------------ episode scoring
def score_episode(gs: list[dict], lag: int, lo: int, hi: int, T: int | None, wlo: int, whi: int,
                  p: int, rule: B.Rule) -> dict:
    """First roll-over released in [lo, hi] across the episode's spans (in
    time order), CENSORED when none is released before an uncomputable g inside
    the window. e = release - T; HIT window [wlo, whi]."""
    months = range(lo, hi + 1)
    comp = {}
    for d in months:
        dm = d - lag
        comp[d] = any(dm in s["g"] for s in gs)
    gap = next((d for d in months if not comp[d]), None)
    first = None
    for s in gs:
        hit = B.first_released(s["signals"], lambda t: t + lag, lo, hi)
        if hit is not None and (first is None or hit["release"] < first["release"]):
            first = hit
    status = None
    if first is not None and gap is not None and first["release"] > gap:
        first, status = None, "CENSORED"
    if first is None and status is None:
        status = "CENSORED" if gap is not None else "MISS"
    if first is None or T is None:
        return {"signal": None, "e": None, "outcome": status if T is not None else "NO TARGET",
                "gap_from": mstr(gap) if gap is not None else None}
    e = first["release"] - T
    flags = []
    if first["high_at"] + lag < p - 12:
        flags.append("carry-over")
    return {"signal": {"data_month": mstr(first["t"]), "release": mstr(first["release"]),
                       "g": round(first["g"], 4), "high": round(first["high"], 4),
                       "high_set": mstr(first["high_at"]), "rearmed_at": (mstr(first["rearmed_at"])
                                                                          if first["rearmed_at"] else None)},
            "release_m": first["release"], "e": e, "outcome": B.classify(e, wlo, whi), "flags": flags,
            "false_start": first["rearmed_at"] is not None and first["rearmed_at"] + lag <= hi,
            "gap_from": mstr(gap) if gap is not None else None}


def first_armed(gs: list[dict], lag: int, lo: int, hi: int, rule: B.Rule) -> tuple[int | None, bool]:
    """(first armed release month in [lo, hi], whether H was undefined at lo)."""
    undefined_at_lo = not any(B.trailing_high(s["g"], lo - lag, rule.look) is not None for s in gs)
    for d in range(lo, hi + 1):
        if any(B.armed(s["g"], d - lag, rule) for s in gs):
            return d, undefined_at_lo
    return None, undefined_at_lo


def lag_perm_p(rel: list[int | None], peaks: list[int], lags: list[int], wlo: int, whi: int,
               perms: int, rng: np.random.Generator) -> tuple[int, float]:
    """Observed HITS and the lag-permutation p (SPEC v1 s.1)."""
    rel_a = np.array([np.nan if r is None else r for r in rel], float)
    pk = np.array(peaks, float)
    L = np.array(lags, float)
    obs = int(np.sum((rel_a - (pk + L) >= wlo) & (rel_a - (pk + L) <= whi)))
    if perms == 0 or len(L) == 0:
        return obs, None
    idx = np.array([rng.permutation(len(L)) for _ in range(perms)])
    T = pk[None, :] + L[idx]
    e = rel_a[None, :] - T
    hits = np.sum((e >= wlo) & (e <= whi), axis=1)
    return obs, float((1 + np.sum(hits >= obs)) / (1 + perms))


def clock_errors(anchors: list[int | None], targets: list[int], c: int) -> list[float]:
    """|e - c| of a leave-one-out clock aimed at T + c (MISS -> inf)."""
    out = []
    for i, (a, tg) in enumerate(zip(anchors, targets)):
        lags = [targets[j] + c - anchors[j] for j in range(len(anchors)) if j != i and anchors[j] is not None]
        if a is None or not lags:
            out.append(math.inf)
        else:
            sig = a + B.half_up(float(np.median(lags)))
            out.append(abs(sig - tg - c))
    return out


def os_ci(es: list[int], conf: float = 0.90) -> dict:
    """Median and the order-statistic interval [e(j), e(n-j+1)] with the
    largest j whose two-sided coverage is >= conf (n = 16 -> j = 5, 92.3%)."""
    from scipy.stats import binom
    es = sorted(es)
    n = len(es)
    if n == 0:
        return {"n": 0}
    j_best = None
    for j in range(1, n // 2 + 1):
        cov = 1 - 2 * binom.cdf(j - 1, n, 0.5)
        if cov >= conf:
            j_best = (j, cov)
    out = {"n": n, "median": float(np.median(es))}
    if j_best:
        j, cov = j_best
        out.update({"ci": [es[j - 1], es[n - j]], "coverage": round(cov, 3)})
    return out


def score_p(segs: list[dict[int, float]], rule: B.Rule, lag: int, targets_eq: dict[int, dict],
            rng: np.random.Generator, perms: int, hard_1933: bool = True, use_b: bool = True,
            mask: set[int] = frozenset(), episodes=P_EPISODES, shots=SHOTS, grid: bool = True) -> dict:
    """Score the P shots for one series (observed or synthetic)."""
    spans = spans_p(segs, hard_1933=hard_1933, mask=mask)
    G = growth_by_span(spans, rule)
    res = {}
    for shot, (kind, wlo, whi) in shots.items():
        c = centre(wlo, whi)
        eps = []
        for p, tau in episodes:
            if kind == "equity":
                tg = targets_eq[p]
                if tg["status"] == "no equity low" or tg["b"] is None:
                    continue
                T = tg["b"]
                lo = min(p, T - 3)
            else:
                T, lo = tau, p
            hi = window_end(p, tau)
            gs = [G[s["name"]] for s in episode_span(spans, p, use_b)]
            ep = score_episode(gs, lag, lo, hi, T, wlo, whi, p, rule)
            if kind == "equity" and targets_eq[p]["status"] == "censored":
                ep.update({"outcome": "CENSORED", "e": None, "release_m": None})
            arm, h_undef = first_armed(gs, lag, p - 12, hi, rule)
            ep.update({"peak": mstr(p), "trough": mstr(tau), "target": mstr(T), "T": T, "p": p,
                       "arm": mstr(arm) if arm is not None else None, "arm_m": arm,
                       "pre_armed": arm == p - 12, "h_undefined_at_arm_start": h_undef,
                       "war": p in WAR})
            if kind == "equity":
                ep["equity_status"] = targets_eq[p]["status"]
            eps.append(ep)
        rel = [e.get("release_m") for e in eps]
        Ts = [e["T"] for e in eps]
        pks = [e["p"] for e in eps]
        obs, pval = lag_perm_p(rel, pks, [t - q for t, q in zip(Ts, pks)], wlo, whi, perms, rng)
        acc = [abs(e["e"] - c) if e["e"] is not None else math.inf for e in eps]
        arm_err = clock_errors([e["arm_m"] for e in eps], Ts, c)
        peak_err = clock_errors(pks, Ts, c)
        n = len(eps)
        out = {"n": n, "hits": obs, "early": sum(e["outcome"] == "EARLY" for e in eps),
               "late": sum(e["outcome"] == "LATE" for e in eps),
               "miss": sum(e["outcome"] == "MISS" for e in eps),
               "censored": sum(e["outcome"] == "CENSORED" for e in eps),
               "p_lagperm": pval, "median_abs_err": float(np.median(acc)),
               "arm_clock_median_abs_err": float(np.median(arm_err)),
               "peak_clock_median_abs_err": float(np.median(peak_err)),
               "episodes": eps, "window": [wlo, whi], "centre": c}
        need = math.ceil(2 * n / 3)
        out["need_hits"] = need
        out["early_cap"] = n // 6
        # war-flagged and (equity) ambiguous / censored excluded
        keep = [i for i, e in enumerate(eps) if not e["war"]]
        out["hits_without_war"] = sum(eps[i]["outcome"] == "HIT" for i in keep)
        out["need_without_war"] = math.ceil(2 * len(keep) / 3)
        if kind == "equity":
            keep2 = [i for i, e in enumerate(eps) if e["equity_status"] == "valid"]
            out["hits_valid_only"] = sum(eps[i]["outcome"] == "HIT" for i in keep2)
            out["need_valid_only"] = math.ceil(2 * len(keep2) / 3)
            out["n_valid_only"] = len(keep2)
        res[shot] = out
    if grid:
        for w, shift in GRID_SHIFT.items():
            if w == rule.w:
                continue
            sub = score_p(segs, replace(rule, w=w), lag, targets_eq, rng, 0, hard_1933, use_b, mask,
                          episodes, {k: (v[0], v[1] + shift, v[2] + shift) for k, v in shots.items()}, grid=False)
            for shot in shots:
                res[shot].setdefault("grid", {})[str(w)] = {"hits": sub[shot]["hits"],
                                                           "need": sub[shot]["need_hits"]}
    return res


def grade(res: dict, holm: dict[str, float]) -> dict:
    """The SPEC v1 grade per shot given the Holm-adjusted p of the tested shots."""
    out = {}
    for shot, r in res.items():
        grid_ok = 1 + sum(v["hits"] >= v["need"] for v in r.get("grid", {}).values())  # the w=6 row counts once
        conds = {
            "hits": r["hits"] >= r["need_hits"],
            "early": r["early"] <= r["early_cap"],
            "holm_p": holm.get(shot) is not None and holm[shot] <= 0.10,
            "beats_clocks": r["median_abs_err"] < min(r["arm_clock_median_abs_err"], r["peak_clock_median_abs_err"]),
            "grid": (r["hits"] >= r["need_hits"]) and grid_ok >= 2,
            "without_war": r["hits_without_war"] >= r["need_without_war"],
        }
        if "hits_valid_only" in r:
            conds["valid_only"] = r["hits_valid_only"] >= r["need_valid_only"]
        out[shot] = {"conditions": conds, "pass": all(conds.values())}
    return out


# ------------------------------------------------------------------ false bottoms
def false_bottoms(G: dict[str, dict], periods_by_span: dict[str, tuple[int, int]], lag: int,
                  rule: B.Rule) -> dict:
    """Every roll-over released in each span's assigned period: TRUE BOTTOM if
    within TRUE_BOTTOM of some trough, else FALSE BOTTOM; per decade of months
    with H defined."""
    rows, months = [], 0
    for name, (a, b) in periods_by_span.items():
        g = G[name]["g"]
        months += sum(1 for t in range(a, b + 1) if B.trailing_high(g, t, rule.look) is not None)
        for s in G[name]["signals"]:
            if a <= s["t"] <= b:
                r = s["t"] + lag
                near = [tau for tau in TROUGHS if TRUE_BOTTOM[0] <= r - tau <= TRUE_BOTTOM[1]]
                pre = [p for p, _ in CHRON if p - 12 <= r <= p - 1]
                rows.append({"release": mstr(r), "kind": "TRUE BOTTOM" if near else "FALSE BOTTOM",
                             "trough": mstr(near[0]) if near else None,
                             "before_peak": mstr(pre[0]) if pre else None})
    n_false = sum(r["kind"] == "FALSE BOTTOM" for r in rows)
    decades = months / 120
    return {"signals": rows, "n": len(rows), "n_false": n_false,
            "precision": (len(rows) - n_false) / len(rows) if rows else None,
            "false_per_decade": n_false / decades if decades else None, "decades_observed": round(decades, 2)}


# ------------------------------------------------------------------ the run
def run() -> dict:
    prm = load_params()
    rule = B.Rule(theta=prm["theta"], floor=prm["floor"])
    P, _ = D.shiller_monthly()
    eqt = equity_targets(P)
    rng = np.random.default_rng(SEED)
    segs = D.dnb_count_segments()
    out: dict = {"spec": "SPEC v1", "seed": SEED, "perms": PERMS, "rule": rule.__dict__,
                 "reachable": prm["reachable"],
                 "equity_targets": {mstr(p): {**v, "b": mstr(v["b"]) if v["b"] is not None else None,
                                              "window": [mstr(x) for x in v.get("window", [])]}
                                    for p, v in eqt.items()}}
    prim = score_p(segs, rule, 1, eqt, rng, PERMS)
    tested = [s for s in SHOTS if prm["reachable"].get(s)]
    holm = E.holm({s: prim[s]["p_lagperm"] for s in tested})
    out["P"] = {"shots": prim, "holm": holm, "grade": grade(prim, holm)}
    # timing estimates (the deliverable for shots out of reach) and the hindsight g-peak
    timing = {}
    for shot, r in prim.items():
        timing[shot] = os_ci([e["e"] for e in r["episodes"] if e["e"] is not None])
    out["P"]["timing"] = timing
    out["P"]["g_peak"] = g_peak_diagnostic(segs, rule, eqt)
    out["P"]["romer"] = romer_view(prim)
    # sensitivities
    sens = {}
    sens["release_plus2"] = summarize(score_p(segs, rule, 2, eqt, rng, PERMS, grid=False))
    sens["1898_06_masked"] = summarize(score_p(D.dnb_count_segments(fix=False), rule, 1, eqt, rng, PERMS,
                                               mask={M(1898, 6)}, grid=False))
    sens["1933_straight_across"] = summarize(score_p(segs, rule, 1, eqt, rng, PERMS, hard_1933=False, grid=False))
    sens["1937_on_A"] = summarize(score_p(segs, rule, 1, eqt, rng, PERMS, use_b=False, grid=False))
    out["P"]["sensitivities"] = sens
    # false bottoms over the whole P record
    spans = spans_p(segs)
    G = growth_by_span(spans, rule)
    b_first_h = next(t for t in range(*spans[2]["range"]) if B.trailing_high(G["B"]["g"], t, rule.look))
    periods = {"A1": (spans[0]["range"][0], M(1932, 12)), "A2": (M(1933, 1), b_first_h - 1),
               "B": (b_first_h, M(1939, 12)), "C": (M(1940, 1), spans[3]["range"][1])}
    out["P"]["false_bottoms"] = false_bottoms(G, periods, 1, rule)
    out["R"] = score_r(rule, eqt)
    out["claims"] = score_claims(rule, eqt)
    out["liabilities"] = score_liabilities(rule, eqt)
    out["trader"] = trader_view(out, rule, eqt)
    return out


def summarize(res: dict) -> dict:
    return {s: {k: r[k] for k in ("n", "hits", "early", "late", "miss", "censored", "p_lagperm")}
            | {"outcomes": {e["peak"]: e["outcome"] for e in r["episodes"]}} for s, r in res.items()}


def romer_troughs() -> dict[int, int]:
    """NBER peak -> Romer (1994) trough for the prewar cycles she dates."""
    out = {}
    for r in D._rows(os.path.join(D.DER, "romer1994_prewar_peaks_troughs.csv")):
        if r["nber_peak"] and r["romer_trough"]:
            y, mo = map(int, r["nber_peak"].split("-"))
            y2, mo2 = map(int, r["romer_trough"].split("-"))
            out[M(y, mo)] = M(y2, mo2)
    return out


def romer_view(shots: dict) -> dict:
    """Descriptive: the same signals scored against Romer's prewar troughs."""
    rt = romer_troughs()
    out = {}
    for shot, (kind, wlo, whi) in SHOTS.items():
        if kind != "trough":
            continue
        rows = {}
        for e in shots[shot]["episodes"]:
            if e["p"] in rt:
                er = e["release_m"] - rt[e["p"]] if e.get("release_m") is not None else None
                rows[e["peak"]] = {"romer_trough": mstr(rt[e["p"]]), "e_nber": e["e"], "e_romer": er,
                                   "outcome_nber": e["outcome"],
                                   "outcome_romer": B.classify(er, wlo, whi) if er is not None else e["outcome"]}
        out[shot] = {"episodes": rows,
                     "hits_nber": sum(r["outcome_nber"] == "HIT" for r in rows.values()),
                     "hits_romer": sum(r["outcome_romer"] == "HIT" for r in rows.values())}
    return out


def g_peak_diagnostic(segs, rule, eqt) -> dict:
    """Hindsight: the month of the highest w = 12 growth in each trough window."""
    r12 = replace(rule, w=12)
    spans = spans_p(segs)
    G = growth_by_span(spans, r12)
    rows = []
    for p, tau in P_EPISODES:
        hi = window_end(p, tau)
        best = None
        for s in episode_span(spans, p):
            for t, v in G[s["name"]]["g"].items():
                if p <= t + 1 <= hi and (best is None or v > best[1]):
                    best = (t, v)
        if best:
            rows.append({"peak": mstr(p), "g_peak_release": mstr(best[0] + 1), "e_trough": best[0] + 1 - tau,
                         "e_equity": (best[0] + 1 - eqt[p]["b"]) if eqt[p]["b"] is not None else None})
    return {"episodes": rows, "trough": os_ci([r["e_trough"] for r in rows]),
            "equity": os_ci([r["e_equity"] for r in rows if r["e_equity"] is not None])}


# ------------------------------------------------------------------ R: court business filings
def court_series(mask_1980q1: bool = False) -> tuple[dict[int, float], set[int]]:
    vals = dict(D.abi_quarterly_business())
    vals.update({t: v for t, v in D.f2_national("3month", "bus_all").items() if t >= D.qi(2026, 1)})
    vals[D.qi(1995, 4)] += 1000          # ABI's 1995 quarters sum 1,000 below its printed total
    bad = set(range(D.qi(2005, 2), D.qi(2008, 4) + 1)) | set(range(D.qi(2020, 2), D.qi(2021, 4) + 1))
    if mask_1980q1:
        bad.add(D.qi(1980, 1))
    return vals, bad


def q_release(q: int, lag_months: int = 1) -> int:
    return 12 * (q // 4) + 3 * (q % 4 + 1) - 1 + lag_months


def score_r(rule: B.Rule, eqt: dict) -> dict:
    rq = B.Rule(w=2, lag=4, look=4, theta=rule.theta, frac=rule.frac, floor=rule.floor, k=1)
    out = {}
    for name, m80, lagm in (("primary", False, 1), ("mask_1980Q1", True, 1), ("release_plus2", False, 2)):
        vals, bad = court_series(m80)
        g = B.growth(vals, rq, bad=bad)
        qs = range(min(vals), max(vals) + 1)
        sig = B.signals(g, qs, rq)
        eps = {}
        for p, tau in CHRON:
            if p < M(1981, 1) or p in EXCLUDED:
                continue
            hi = window_end(p, tau)
            row = {}
            for shot, (kind, wlo, whi) in SHOTS.items():
                T = tau if kind == "trough" else eqt[p]["b"]
                if T is None or (kind == "equity" and eqt[p]["status"] == "no equity low"):
                    continue
                lo = p if kind == "trough" else min(p, T - 3)
                first = B.first_released(sig, lambda q: q_release(q, lagm), lo, hi)
                inwin = [q for q in qs if lo <= q_release(q, lagm) <= hi]
                gap = next((q_release(q, lagm) for q in inwin if q not in g), None)
                if first is not None and gap is not None and first["release"] > gap:
                    first = None
                if first is None:
                    row[shot] = {"outcome": "CENSORED" if gap is not None else "MISS"}
                else:
                    e = first["release"] - T
                    row[shot] = {"release": mstr(first["release"]), "e": e, "outcome": B.classify(e, wlo, whi),
                                 "g": round(first["g"], 4), "high": round(first["high"], 4)}
            eps[mstr(p)] = row
        # false bottoms 1981-2026 and the live status
        rows = []
        for s in sig:
            r = q_release(s["t"], lagm)
            near = [tau for tau in TROUGHS if TRUE_BOTTOM[0] <= r - tau <= TRUE_BOTTOM[1]]
            rows.append({"release": mstr(r), "kind": "TRUE BOTTOM" if near else "FALSE BOTTOM"})
        last = max(g)
        hh = B.trailing_high(g, last, rq.look)
        last_sig = sig[-1] if sig else None
        out[name] = {"episodes": eps, "signals": rows,
                     "n_false": sum(r["kind"] == "FALSE BOTTOM" for r in rows),
                     "live": {"asof": D.qstr(last), "g": round(g[last], 4),
                              "high": round(hh[0], 4) if hh else None,
                              "armed": bool(hh and hh[0] >= rq.theta),
                              "last_signal": mstr(q_release(last_sig["t"], lagm)) if last_sig else None,
                              "rolled_over_now": bool(last_sig and last_sig["rearmed_at"] is None)}}
    return out


# ------------------------------------------------------------------ claims benchmarks (1967+)
def c1_signals() -> list[int]:
    """C1: release months of 4-week-average claims-peak confirmations (SPEC v0 s.3)."""
    w = D.claims_weekly(sa=True)
    days = sorted(w)
    vals = [w[d] for d in days]
    ma = {days[i]: sum(vals[i - 3:i + 1]) / 4 for i in range(3, len(days))}
    ks = sorted(ma)
    out, armed, mx, mx_at = [], False, None, None
    for i, d in enumerate(ks):
        if i >= 52 and not armed and ma[d] >= 1.2 * ma[ks[i - 52]]:
            armed, mx, mx_at = True, ma[d], i
        if armed:
            if ma[d] > mx:
                mx, mx_at = ma[d], i
            if ma[d] <= 0.9 * mx and i - mx_at >= 8:
                r = d + __import__("datetime").timedelta(days=5)
                out.append(12 * r.year + r.month - 1)
                armed = False
    return out


def score_claims(rule: B.Rule, eqt: dict) -> dict:
    val, rel = D.claims_monthly_nsa()
    g = B.growth(val, rule)
    sig = B.signals(g, range(min(val), max(val) + 1), rule)
    c2 = [rel[s["t"]] for s in sig]
    c1 = c1_signals()
    out = {}
    for p, tau in CHRON:
        if p < M(1969, 1):
            continue
        hi = window_end(p, tau)
        row = {}
        for name, rels in (("C1", c1), ("C2", c2)):
            for shot, (kind, wlo, whi) in SHOTS.items():
                T = tau if kind == "trough" else eqt[p]["b"]
                if T is None:
                    continue
                lo = p if kind == "trough" else min(p, T - 3)
                first = next((r for r in rels if lo <= r <= hi), None)
                row[f"{name}/{shot}"] = ({"release": mstr(first), "e": first - T,
                                          "outcome": B.classify(first - T, wlo, whi)} if first is not None
                                         else {"outcome": "MISS"})
        row["flags"] = [f for f, cond in (("GM strike Sep-Nov 1970", p == M(1969, 12)),
                                          ("UI coverage change (1972-01 / 1978-01) inside the inputs",
                                           p in (M(1969, 12), M(1973, 11), M(1980, 1))))
                        if cond]
        out[mstr(p)] = row
    return out


# ------------------------------------------------------------------ D&B liabilities (secondary)
def score_liabilities(rule: B.Rule, eqt: dict) -> dict:
    rl = replace(rule, w=12)
    la, lc = D.dnb_liability_segments()
    spans = [{"name": "A", "values": la}, {"name": "C", "values": lc}]
    for s in spans:
        s["range"] = (min(s["values"]), max(s["values"]))
    G = growth_by_span(spans, rl)
    out = {}
    for p, tau in CHRON:
        if p < M(1895, 12) or p > M(1981, 7) or p in EXCLUDED:
            continue
        gs = [G["A"]] if p < M(1939, 1) else [G["C"]]
        hi = window_end(p, tau)
        row = {}
        for shot, (kind, wlo, whi) in SHOTS.items():
            T = tau if kind == "trough" else eqt[p]["b"]
            if T is None or (kind == "equity" and eqt[p]["status"] == "no equity low"):
                continue
            lo = p if kind == "trough" else min(p, T - 3)
            ep = score_episode(gs, 2, lo, hi, T, wlo, whi, p, rl)
            row[shot] = {k: ep[k] for k in ("e", "outcome")}
        out[mstr(p)] = row
    return out


# ------------------------------------------------------------------ trader's view
def _stats_row(tr, P, p, hi, b, entries: dict[str, int | None]) -> dict:
    row = {k: ({"entry": mstr(m)} | B.entry_stats(tr, m, b)) if m is not None else {"entry": None}
           for k, m in entries.items()}
    trig = B.drawdown_trigger(P, p - 6, hi)
    row["minus_20pct"] = ({"entry": mstr(trig + 1)} | B.entry_stats(tr, trig + 1, b)) if trig is not None \
        else {"entry": None}
    row["peak_plus_6"] = {"entry": mstr(p + 6)} | B.entry_stats(tr, p + 6, b)
    return row


def trader_view(res: dict, rule: B.Rule, eqt: dict) -> dict:
    """Total-return outcomes of entering the month after each rule fires
    (SPEC v1 s.5), on every scored episode; 'no entry' recorded."""
    tr = D.equity_total_return()
    P, _ = D.shiller_monthly()
    rng = np.random.default_rng(SEED + 1)
    spans = spans_p(D.dnb_count_segments())
    G = growth_by_span(spans, rule)
    rows = {}
    for ep in res["P"]["shots"]["CONFIRMS-trough"]["episodes"]:
        p = ep["p"]
        tau = M(int(ep["trough"][:4]), int(ep["trough"][5:]))
        hi = window_end(p, tau)
        b = eqt[p]["b"] if eqt[p]["status"] != "no equity low" else None
        row = _stats_row(tr, P, p, hi, b, {
            "rollover_P": ep["release_m"] + 1 if ep.get("release_m") is not None else None,
            "arm_P": ep["arm_m"] + 1 if ep.get("arm_m") is not None else None})
        sup = []
        for s in episode_span(spans, p):
            g = G[s["name"]]["g"]
            sup += [t + 2 for t in g if p <= t + 1 <= hi and B.armed(g, t, rule)]
        sup = [m for m in sup if m in tr]
        if sup:
            draws = [B.entry_stats(tr, int(m), b) for m in rng.choice(sup, size=1000)]
            row["random_armed_P"] = {k: float(np.median([d[k] for d in draws if k in d]))
                                     for k in set().union(*draws)} | {"entry": "random"}
        rows[ep["peak"]] = row
    for pk, r in res["R"]["primary"]["episodes"].items():
        p = M(int(pk[:4]), int(pk[5:]))
        tau = dict(CHRON)[p]
        hi = window_end(p, tau)
        b = eqt[p]["b"] if eqt[p]["status"] != "no equity low" else None
        rel = r.get("CONFIRMS-trough", {}).get("release")
        cl = res["claims"].get(pk, {})
        ent = {"rollover_R": (M(int(rel[:4]), int(rel[5:])) + 1) if rel else None}
        for c in ("C1", "C2"):
            x = cl.get(f"{c}/CONFIRMS-trough", {}).get("release")
            ent[f"claims_{c}"] = (M(int(x[:4]), int(x[5:])) + 1) if x else None
        rows[pk] = _stats_row(tr, P, p, hi, b, ent)
    summary = {}
    names = sorted({k for r in rows.values() for k in r})
    for k in names:
        vals = [r[k] for r in rows.values() if k in r]
        got = [v for v in vals if v.get("entry")]
        summary[k] = {"episodes": len(vals), "entries": len(got)}
        for stat in ("ret_6m", "ret_12m", "ret_24m", "worst_dd_12m", "rebound_missed"):
            xs = [v[stat] for v in got if stat in v]
            if xs:
                summary[k][stat] = float(np.median(xs))
    return {"episodes": rows, "median": summary}


if __name__ == "__main__":
    res = run()
    with open(os.environ.get("BOTTOMS_OUT", os.path.join(HERE, "bottoms_results.json")), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: None)
    print("wrote bottoms_results.json")
