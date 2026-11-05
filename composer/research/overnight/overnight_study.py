#!/usr/bin/env python3
"""Overnight / pre-open overlays on the Composer engines' leveraged legs, as an IBKR engine could run
them (results.md addendum 53). Owner, 2026-11-05: "see if there are overnight indicators like semis
etc. or others ... a series or individual ones we can run ... think second order ... trying to see if
it makes sense to switch all this logic over on IBKR."

The engines' 15:50 decisions are left untouched. The question is what an IBKR layer could add BETWEEN
decisions: on the morning after a leveraged entry, read what is known before 09:30 (Asia's closes,
VIX, the fund's own pre-open print, the sector's pre-open print) and either EXIT at the open (hold cash
until the next 15:50 decision), FLIP into the inverse fund for the session, or do nothing. The same
for the short legs (SQQQ/SOXS/SPXS) on gap-ups. Plus a flip-frequency BREAKER (after N direction
changes in M sessions, sit in cash K sessions).

Data (scratchpad overnight/): daily.json — Yahoo daily OHLC with adjusted close (period-bounded
pulls, 2006-), funds, sector ETFs, Asia/Europe indices, VIX, dollar-yen, semis names; the engine paths
from the add. 47 pipeline (long1997/engines_ts_synth.json: days, rets, hold per engine). Pre-market
history (04:00-09:25) does not exist in our sources (FMP's 1-minute bars are 09:30-15:59; Yahoo keeps
60 days), so the historical test uses the 09:30 OPEN as the exit print; a 60-day bridge measures how
the 08:00 / 09:25 pre-market prints sit against the open (premarket_bridge.json).

Honesty: the engine paths before each fund's launch run on add. 47's proxies (in sample 2015-26); the
overlays are evaluated on the real funds' opens and closes from their launch (SOXL 2010, TECL 2008,
TQQQ 2010, SPXL 2008, LABU 2015-05). Costs are assumed (EXIT_BPS at the open, REENTRY_BPS at the close
when the engine re-holds the fund). Placebo: the same number of fires on random eligible days; inverse:
the mirrored signal. Writes composer/results/overnight-2026-11-05.json. Usage: overnight_study.py
"""
import json
import math
import os
import random
import statistics
import sys

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "overnight-2026-11-05.json")
PATHS = os.path.join(S, "long1997", "engines_ts_synth.json")
DAILY = os.path.join(S, "overnight", "daily.json")
BRIDGE = os.path.join(S, "overnight", "premarket_bridge.json")
START = "2015-06-01"                       # LABU's first month; the rules' own years
LONG3 = {"SOXL": "SMH", "TECL": "XLK", "TQQQ": "QQQ", "SPXL": "SPY", "LABU": "XBI", "UPRO": "SPY", "UDOW": "SPY", "SSO": "SPY", "QLD": "QQQ", "FAS": "SPY",
         "TNA": "IWM", "USD": "SMH"}
INVERSE = {"SOXL": "SOXS", "TECL": "SQQQ", "TQQQ": "SQQQ", "SPXL": "SPXS", "LABU": "SQQQ", "UPRO": "SPXS", "UDOW": "SPXS", "SSO": "SPXS", "QLD": "SQQQ", "FAS": "SPXS",
           "TNA": "TZA", "USD": "SOXS"}
SHORT3 = {"SQQQ": "QQQ", "SOXS": "SMH", "SPXS": "SPY"}
EXIT_BPS, REENTRY_BPS = 15, 10
MIN_W = 0.30                               # a leg counts when it carries at least this weight
PLACEBO_N = 2000
random.seed(20261105)


# ------------------------------------------------------------------ data
def load_daily():
    d = json.load(open(DAILY))
    return {t: v["rows"] for t, v in d.items()}


def load_paths():
    """{engine: {days, rets, hold}} aligned lists: rets[i] is the engine's costed return on days[i] and
    hold[i] the weights that EARN on days[i] (decided at the previous close). The add. 47 file keys
    rets and hold by the earning date."""
    p = json.load(open(PATHS))
    out = {}
    for e, v in p.items():
        rets, hold = v["rets"], v["hold"]
        if isinstance(rets, dict):
            days = sorted(d for d in rets if d in hold)
            out[e] = {"days": days, "rets": [float(rets[d]) for d in days], "hold": [{k: float(x) for k, x in hold[d].items()} for d in days]}
        else:                                   # list form: hold[i] decided at the close of days[i]
            days = list(v["days"])
            H = [({k: float(x) for k, x in h.items()} if isinstance(h, dict) else {}) for h in hold]
            out[e] = {"days": days[1:], "rets": [float(r) for r in rets[1:]], "hold": H[:-1]}
    return out


def prev_day(rows, d):
    """the last date in rows strictly before d"""
    ks = rows.get("_keys")
    if ks is None:
        ks = rows["_keys"] = sorted(k for k in rows if not k.startswith("_"))
    import bisect
    i = bisect.bisect_left(ks, d)
    return ks[i - 1] if i > 0 else None


def gap_intraday(D, t, d):
    """(gap = open/prev close - 1, intraday = close/open - 1, day = close/prev close - 1) on raw prices"""
    r = D[t].get(d)
    pd = prev_day(D[t], d)
    if not r or not pd or r.get("o") in (None, 0) or D[t][pd].get("c") in (None, 0):
        return None
    pc = D[t][pd]["c"]
    return {"gap": r["o"] / pc - 1, "intra": r["c"] / r["o"] - 1, "day": r["c"] / pc - 1, "prev": pd}


def asia(D, d):
    """mean close-to-close return of Nikkei, Kospi, Taiwan on calendar day d (all close before the US
    open); None if fewer than two printed"""
    vals = []
    for t in ("^N225", "^KS11", "^TWII"):
        r = D[t].get(d)
        pd = prev_day(D[t], d)
        if r and pd and D[t][pd].get("c"):
            vals.append(r["c"] / D[t][pd]["c"] - 1)
    return statistics.mean(vals) if len(vals) >= 2 else None


def asia_semi(D, d):
    vals = []
    for t in ("^KS11", "^TWII"):
        r = D[t].get(d)
        pd = prev_day(D[t], d)
        if r and pd and D[t][pd].get("c"):
            vals.append(r["c"] / D[t][pd]["c"] - 1)
    return statistics.mean(vals) if len(vals) == 2 else None


def level(D, t, d):
    pd = prev_day(D[t], d)
    return D[t][pd]["c"] if pd else None


# ------------------------------------------------------------------ stats
def cagr(rets, n_per_year=252):
    g = 1.0
    for r in rets:
        g *= 1 + r
    return g ** (n_per_year / len(rets)) - 1 if rets else float("nan")


def sharpe(rets):
    m = statistics.mean(rets)
    s = statistics.pstdev(rets)
    return m / s * math.sqrt(252) if s else float("nan")


def maxdd(rets):
    peak = lv = 1.0
    worst = 0.0
    for r in rets:
        lv *= 1 + r
        peak = max(peak, lv)
        worst = min(worst, lv / peak - 1)
    return worst


def summary(rets):
    return {"cagr": cagr(rets), "sharpe": sharpe(rets), "maxdd": maxdd(rets), "n": len(rets),
            "worst_day": min(rets), "total": math.prod(1 + r for r in rets) - 1}


# ------------------------------------------------------------------ the morning table
def mornings(D, path, start=START):
    """one row per session on which the engine entered the overnight with a leveraged leg (long or
    short) of weight >= MIN_W: everything known before 09:30 plus what the leg then did"""
    days, hold = path["days"], path["hold"]
    rows = []
    for i in range(len(days)):
        d, h = days[i], hold[i]                # hold[i]: decided at the previous close, earns on days[i]
        if d < start:
            continue
        for t, w in h.items():
            side = "long" if t in LONG3 else ("short" if t in SHORT3 else None)
            if side is None or w < MIN_W or t not in D:
                continue
            gi = gap_intraday(D, t, d)
            if gi is None:
                continue
            sec = LONG3.get(t) or SHORT3.get(t)
            sg = gap_intraday(D, sec, d) if sec in D else None
            inv = INVERSE.get(t)
            ig = gap_intraday(D, inv, d) if inv in D else None
            vix = level(D, "^VIX", d)
            vix3 = level(D, "^VIX3M", d)
            pdv = prev_day(D["^VIX"], d)
            ppdv = prev_day(D["^VIX"], pdv) if pdv else None
            dvix = (D["^VIX"][pdv]["c"] / D["^VIX"][ppdv]["c"] - 1) if (pdv and ppdv) else None
            entry = gap_intraday(D, t, gi["prev"])          # the fund's move on the entry day
            eu = gap_intraday(D, "^GDAXI", d)                # DAX open (03:00 ET) vs its prior close: known before 09:30
            rows.append({"date": d, "i": i, "fund": t, "w": w, "side": side, "gap": gi["gap"], "intra": gi["intra"],
                         "day": gi["day"], "sector": sec, "sec_gap": sg["gap"] if sg else None,
                         "asia": asia(D, d), "asia_semi": asia_semi(D, d), "eu_open": eu["gap"] if eu else None, "vix": vix, "dvix": dvix,
                         "vix_curve": (vix / vix3 - 1) if (vix and vix3) else None,
                         "entry_day": entry["day"] if entry else None,
                         "inv_intra": ig["intra"] if ig else None,
                         "still_held": (hold[i + 1].get(t, 0.0) >= MIN_W) if i + 1 < len(hold) else False})
    return rows


# ------------------------------------------------------------------ overlays
def apply(path, rows, fire, action="exit", exit_bps=EXIT_BPS, reentry_bps=REENTRY_BPS):
    """the engine path with the overlay: on each morning row where fire(row) is true, the leg's
    close-to-close return is replaced by its gap (exit at the open) or by gap + the inverse fund's
    intraday (flip). Returns (overlay daily returns, fires)"""
    rets = list(path["rets"])
    fires = []
    for r in rows:
        if not fire(r):
            continue
        w = r["w"]
        base = w * r["day"]
        if action == "exit":
            new = w * (r["gap"] - exit_bps / 1e4) - (w * reentry_bps / 1e4 if r["still_held"] else 0.0)
        elif action == "flip":
            if r["inv_intra"] is None:
                continue
            new = w * (r["gap"] - exit_bps / 1e4) + w * (r["inv_intra"] - exit_bps / 1e4) - (w * reentry_bps / 1e4 if r["still_held"] else 0.0)
        else:
            raise ValueError(action)
        rets[r["i"]] = rets[r["i"]] - base + new
        fires.append({"date": r["date"], "fund": r["fund"], "saved": new - base, "gap": r["gap"], "intra": r["intra"]})
    return rets, fires


def evaluate(path, rows, fire, action="exit", placebo=True, start=START):
    """metrics on the START.. window only (the overlays apply there; the full path's 1995-2015 proxy
    years would dilute every delta and hide the drawdown change)"""
    sel = [i for i, d in enumerate(path["days"]) if d >= start]
    full, fires = apply(path, rows, fire, action)
    rets = [full[i] for i in sel]
    base = [path["rets"][i] for i in sel]
    out = {"n_fires": len(fires), "saved_total": sum(f["saved"] for f in fires),
           "saved_mean": statistics.mean([f["saved"] for f in fires]) if fires else 0.0,
           "hit_rate": (sum(1 for f in fires if f["saved"] > 0) / len(fires)) if fires else None,
           "overlay": summary(rets), "base": summary(base),
           "delta_cagr": cagr(rets) - cagr(base), "delta_sharpe": sharpe(rets) - sharpe(base), "delta_maxdd": maxdd(rets) - maxdd(base),
           "worst_fire": min(fires, key=lambda f: f["saved"]) if fires else None,
           "best_fire": max(fires, key=lambda f: f["saved"]) if fires else None,
           "by_year": {}}
    for f in fires:
        y = f["date"][:4]
        out["by_year"].setdefault(y, {"n": 0, "saved": 0.0})
        out["by_year"][y]["n"] += 1
        out["by_year"][y]["saved"] += f["saved"]
    if placebo and fires:
        # the same number of fires on random eligible mornings of the same side(s)
        sides = {f["fund"] in LONG3 for f in fires}
        elig = [r for r in rows if (r["fund"] in LONG3) in sides]
        k = min(len(fires), len(elig))
        draws = []
        base_cagr = cagr(base)
        for _ in range(PLACEBO_N):
            pick = random.sample(elig, k)
            chosen = {(r["date"], r["fund"]) for r in pick}
            pr, pf = apply(path, rows, lambda r: (r["date"], r["fund"]) in chosen, action)
            draws.append(cagr([pr[i] for i in sel]) - base_cagr)
        draws.sort()
        out["placebo"] = {"n": PLACEBO_N, "k": k, "p50": draws[len(draws) // 2], "p95": draws[int(0.95 * len(draws))],
                          "p05": draws[int(0.05 * len(draws))], "percentile_of_actual": sum(1 for x in draws if x < out["delta_cagr"]) / len(draws)}
    return out


# ------------------------------------------------------------------ breaker
def direction(h):
    l = sum(w for t, w in h.items() if t in LONG3)
    s = sum(w for t, w in h.items() if t in SHORT3)
    return "L" if l >= MIN_W else ("S" if s >= MIN_W else "N")


def breaker(path, n_flips, m_sessions, k_cash, start=START):
    """after n direction changes within the last m sessions, replace the next k sessions' returns with
    0 (cash); the engine's own decisions resume after"""
    days, rets, hold = path["days"], list(path["rets"]), path["hold"]
    dirs = [direction(h) for h in hold]
    flips = [0] * len(days)
    for i in range(1, len(days)):
        flips[i] = 1 if (dirs[i] != dirs[i - 1] and "N" not in (dirs[i], dirs[i - 1])) else 0
    out = list(rets)
    i, trips, cash_days = 1, [], 0
    while i < len(days):
        if days[i] >= start and sum(flips[max(0, i - m_sessions + 1):i + 1]) >= n_flips:
            for j in range(i + 1, min(len(days), i + 1 + k_cash)):
                out[j] = 0.0
                cash_days += 1
            trips.append(days[i])
            i += k_cash + 1
            continue
        i += 1
    return out, trips, cash_days


def flip_rate(path, window=25, start=START):
    days, hold = path["days"], path["hold"]
    dirs = [direction(h) for h in hold]
    fl = [1 if (i and dirs[i] != dirs[i - 1] and "N" not in (dirs[i], dirs[i - 1])) else 0 for i in range(len(days))]
    idx = [i for i, d in enumerate(days) if d >= start]
    counts = [sum(fl[i - window + 1:i + 1]) for i in idx if i >= window]
    return {"window": window, "n_windows": len(counts), "mean": statistics.mean(counts), "p90": sorted(counts)[int(0.9 * len(counts))],
            "p99": sorted(counts)[int(0.99 * len(counts))], "max": max(counts), "share_ge_10": sum(1 for c in counts if c >= 10) / len(counts),
            "total_flips": sum(fl[i] for i in idx), "sessions": len(idx)}


# ------------------------------------------------------------------ main
def main():
    D = load_daily()
    P = load_paths()
    res = {"generated": "2026-11-05", "start": START, "exit_bps": EXIT_BPS, "reentry_bps": REENTRY_BPS, "min_w": MIN_W, "engines": {}}
    if os.path.exists(BRIDGE):
        res["premarket_bridge"] = json.load(open(BRIDGE))
    for e in ("KMLM", "HG"):
        if e not in P:
            continue
        path = P[e]
        rows = mornings(D, path)
        longs = [r for r in rows if r["side"] == "long"]
        shorts = [r for r in rows if r["side"] == "short"]
        E = {"sessions": sum(1 for d in path["days"] if d >= START), "from": next(d for d in path["days"] if d >= START), "to": path["days"][-1],
             "long_mornings": len(longs), "short_mornings": len(shorts),
             "funds": {t: sum(1 for r in longs if r["fund"] == t) for t in LONG3 if any(r["fund"] == t for r in longs)},
             "base": summary([r for d, r in zip(path["days"], path["rets"]) if d >= START])}
        # unconditional: what the leveraged legs did overnight vs intraday
        E["legs"] = {"gap_mean": statistics.mean(r["gap"] for r in longs), "intra_mean": statistics.mean(r["intra"] for r in longs),
                     "intra_after_gap_down": {}, "intra_after_gap_up": {}}
        for thr in (0.02, 0.05, 0.08):
            dn = [r["intra"] for r in longs if r["gap"] <= -thr]
            up = [r["intra"] for r in longs if r["gap"] >= thr]
            E["legs"]["intra_after_gap_down"][f"{thr:.2f}"] = {"n": len(dn), "mean": statistics.mean(dn) if dn else None, "share_neg": (sum(1 for x in dn if x < 0) / len(dn)) if dn else None}
            E["legs"]["intra_after_gap_up"][f"{thr:.2f}"] = {"n": len(up), "mean": statistics.mean(up) if up else None, "share_neg": (sum(1 for x in up if x < 0) / len(up)) if up else None}
        # signal sweeps (long legs: exit at the open)
        rules = {}
        for thr in (0.02, 0.03, 0.05, 0.08, 0.10):
            rules[f"fund gap <= -{thr:.0%}"] = lambda r, t=thr: r["side"] == "long" and r["gap"] <= -t
            rules[f"INVERSE fund gap >= +{thr:.0%}"] = lambda r, t=thr: r["side"] == "long" and r["gap"] >= t
        for thr in (0.005, 0.01, 0.02, 0.03):
            rules[f"sector gap <= -{thr:.1%}"] = lambda r, t=thr: r["side"] == "long" and r["sec_gap"] is not None and r["sec_gap"] <= -t
        for thr in (0.005, 0.01, 0.015, 0.02, 0.03):
            rules[f"Asia <= -{thr:.1%}"] = lambda r, t=thr: r["side"] == "long" and r["asia"] is not None and r["asia"] <= -t
            rules[f"INVERSE Asia >= +{thr:.1%}"] = lambda r, t=thr: r["side"] == "long" and r["asia"] is not None and r["asia"] >= t
            rules[f"Asia semis (KS11+TWII) <= -{thr:.1%}"] = lambda r, t=thr: r["side"] == "long" and r["asia_semi"] is not None and r["asia_semi"] <= -t
        for thr in (0.005, 0.01, 0.02):
            rules[f"Europe open (DAX) <= -{thr:.1%}"] = lambda r, t=thr: r["side"] == "long" and r["eu_open"] is not None and r["eu_open"] <= -t
        rules["combo: Asia <= -1% AND Europe open <= -1%"] = lambda r: r["side"] == "long" and r["asia"] is not None and r["asia"] <= -0.01 and r["eu_open"] is not None and r["eu_open"] <= -0.01
        for lvl in (20, 25, 30):
            rules[f"VIX close > {lvl}"] = lambda r, v=lvl: r["side"] == "long" and r["vix"] is not None and r["vix"] > v
        for thr in (0.05, 0.10):
            rules[f"VIX up >= {thr:.0%} on entry day"] = lambda r, t=thr: r["side"] == "long" and r["dvix"] is not None and r["dvix"] >= t
        rules["VIX backwardation (VIX > VIX3M)"] = lambda r: r["side"] == "long" and r["vix_curve"] is not None and r["vix_curve"] > 0
        for thr in (0.05, 0.08, 0.10):
            rules[f"entry day <= -{thr:.0%} (bought a crash)"] = lambda r, t=thr: r["side"] == "long" and r["entry_day"] is not None and r["entry_day"] <= -t
        rules["combo: fund gap <= -5% AND Asia <= -1%"] = lambda r: r["side"] == "long" and r["gap"] <= -0.05 and r["asia"] is not None and r["asia"] <= -0.01
        rules["combo: fund gap <= -5% AND sector gap <= -1.5%"] = lambda r: r["side"] == "long" and r["gap"] <= -0.05 and r["sec_gap"] is not None and r["sec_gap"] <= -0.015
        rules["combo: fund gap <= -3% AND VIX > 25"] = lambda r: r["side"] == "long" and r["gap"] <= -0.03 and r["vix"] is not None and r["vix"] > 25
        rules["combo: Asia <= -1% AND VIX > 25"] = lambda r: r["side"] == "long" and r["asia"] is not None and r["asia"] <= -0.01 and r["vix"] is not None and r["vix"] > 25
        rules["combo: entry day <= -8% AND fund gap <= -5%"] = lambda r: r["side"] == "long" and r["entry_day"] is not None and r["entry_day"] <= -0.08 and r["gap"] <= -0.05
        E["rules_exit"] = {name: evaluate(path, rows, f, "exit") for name, f in rules.items()}
        # flip variants for the main gap rules
        E["rules_flip"] = {name: evaluate(path, rows, f, "flip") for name, f in rules.items() if name.startswith("fund gap") or name.startswith("combo")}
        # short legs: exit at the open on a gap UP of the short fund (= market up overnight)
        srules = {}
        for thr in (0.02, 0.03, 0.05, 0.08):
            srules[f"short fund gap <= -{thr:.0%} (market up overnight)"] = lambda r, t=thr: r["side"] == "short" and r["gap"] <= -t
            srules[f"INVERSE short fund gap >= +{thr:.0%}"] = lambda r, t=thr: r["side"] == "short" and r["gap"] >= t
        for thr in (0.01, 0.02):
            srules[f"short leg: Asia >= +{thr:.1%}"] = lambda r, t=thr: r["side"] == "short" and r["asia"] is not None and r["asia"] >= t
        E["rules_short_exit"] = {name: evaluate(path, rows, f, "exit") for name, f in srules.items()}
        # breaker
        E["breaker"] = {}
        for n, m, k in ((2, 3, 3), (2, 3, 5), (3, 5, 5), (3, 5, 10), (4, 10, 10)):
            br, trips, cash_days = breaker(path, n, m, k)
            sel = [r for d, r in zip(path["days"], br) if d >= START]
            E["breaker"][f"{n} flips in {m} -> cash {k}"] = {"trips": len(trips), "cash_days": cash_days, "overlay": summary(sel),
                                                              "delta_cagr": cagr(sel) - E["base"]["cagr"], "delta_sharpe": sharpe(sel) - E["base"]["sharpe"],
                                                              "delta_maxdd": maxdd(sel) - E["base"]["maxdd"], "last_trips": trips[-5:]}
        E["flip_rate"] = flip_rate(path)
        # this week's mornings, for the record
        E["recent"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "i"} for r in rows if r["date"] >= "2026-10-27"]
        res["engines"][e] = E
    json.dump(res, open(OUT, "w"), indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)

    # ---- console
    for e, E in res["engines"].items():
        b = E["base"]
        print(f"\n===== {e}: {E['from']}..{E['to']} ({E['sessions']} sessions); as built CAGR {b['cagr']:.1%} Sharpe {b['sharpe']:.2f} maxDD {b['maxdd']:.0%}; "
              f"{E['long_mornings']} leveraged-long mornings {E['funds']}, {E['short_mornings']} short mornings")
        L = E["legs"]
        print(f"  long legs: mean gap {L['gap_mean']:+.2%}, mean intraday {L['intra_mean']:+.2%}; after gap-down 2/5/8%: " +
              ", ".join(f"n{v['n']} intra {v['mean']:+.2%} ({v['share_neg']:.0%} neg)" if v['n'] else "n0" for v in L["intra_after_gap_down"].values()) +
              "; after gap-up 2/5/8%: " + ", ".join(f"n{v['n']} intra {v['mean']:+.2%}" if v['n'] else "n0" for v in L["intra_after_gap_up"].values()))
        print("  rule (exit at the open)                      fires  hit  saved/fire  dCAGR   dSharpe  dMaxDD  placebo pct (p05..p95 dCAGR)")
        for name, v in E["rules_exit"].items():
            pl = v.get("placebo")
            print(f"  {name:44s} {v['n_fires']:5d} {(v['hit_rate'] or 0):5.0%} {v['saved_mean']:+9.2%} {v['delta_cagr']:+7.1%} {v['delta_sharpe']:+8.2f} {v['delta_maxdd']:+7.1%}"
                  + (f"   {pl['percentile_of_actual']:4.0%} ({pl['p05']:+.1%}..{pl['p95']:+.1%})" if pl else ""))
        print("  flip variants:")
        for name, v in E["rules_flip"].items():
            pl = v.get("placebo")
            print(f"  {name:44s} {v['n_fires']:5d} {(v['hit_rate'] or 0):5.0%} {v['saved_mean']:+9.2%} {v['delta_cagr']:+7.1%} {v['delta_sharpe']:+8.2f} {v['delta_maxdd']:+7.1%}"
                  + (f"   {pl['percentile_of_actual']:4.0%}" if pl else ""))
        print("  short legs:")
        for name, v in E["rules_short_exit"].items():
            pl = v.get("placebo")
            print(f"  {name:44s} {v['n_fires']:5d} {(v['hit_rate'] or 0):5.0%} {v['saved_mean']:+9.2%} {v['delta_cagr']:+7.1%} {v['delta_sharpe']:+8.2f} {v['delta_maxdd']:+7.1%}"
                  + (f"   {pl['percentile_of_actual']:4.0%}" if pl else ""))
        print("  breaker:")
        for name, v in E["breaker"].items():
            print(f"  {name:30s} trips {v['trips']:3d} cash days {v['cash_days']:4d}  dCAGR {v['delta_cagr']:+7.1%} dSharpe {v['delta_sharpe']:+.2f} dMaxDD {v['delta_maxdd']:+.1%}  last {v['last_trips']}")
        fr = E["flip_rate"]
        print(f"  flip rate per {fr['window']} sessions: mean {fr['mean']:.1f}, p90 {fr['p90']}, p99 {fr['p99']}, max {fr['max']}; share of windows >= 10: {fr['share_ge_10']:.1%}; "
              f"total {fr['total_flips']} flips in {fr['sessions']} sessions")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
