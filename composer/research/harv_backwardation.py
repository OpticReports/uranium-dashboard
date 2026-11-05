#!/usr/bin/env python3
"""HARV ("VIX Harvester + HYG Credit Guard", ORQNCfZnA18wmsMWVhf8) in VIX backwardation: does its ZVOL
(short mid-term vol) entry pay or bleed when the curve is inverted? Owner question after the 2026-11-05
rotation PULS/VXZ -> ZVOL 60 / PULS 40 at a -9.3% VIX3M/VIX close.

What the rule is (fixtures/approved/harv-XVtsDTV1.json = the live logic): nine voters weighted 36/16/8/8/
8/8/8/4/4 on Wilder RSI(SPY, w), w = 2..10. Each voter: RSI < 25 -> ZVOL, unless RSI(UVXY, 14) > 70 (then
PULS); RSI > 80 -> VXZ; otherwise PULS. The ZVOL weight is the summed weight of the voters whose SPY RSI
is under 25. Nothing in the tree reads the VIX term structure and no saved version has an HYG condition
(add. 48): the rule buys short vol because SPY is oversold, and an inverted curve is what an oversold SPY
close usually looks like. "harvester 0.0202" in monitor.py is Composer's last_percent_change for the
symphony: HARV's own day return (+2.02% on 11-05, earned by the VXZ leg it held into the crash day).

Method
 1. Regime at a close D: VIX3M/VIX < 1 (Cboe indices via Yahoo); depth buckets 0..-3%, -3..-8%, < -8%.
    Real VIX3M from 2006-07-17; before that the add. 47 synthetic curve (fitted from the VIX alone), used
    only for the 1995+ full-path split and labelled as such.
 2. ZVOL's next 1/5/20-session returns conditional on D's regime: real ZVOL 2023-04-19+; before that the
    add. 47 proxy (ZVOL = -0.971 x VXZ daily; VXZ real from 2018-01-25, the vix_etp term-structure model on
    the real VIX3M/VIX6M before that). Mirror: VXZ on the same days (an identity before 2023: the proxy IS
    -0.971 x VXZ). Placebo: 2000 draws of the same number of random days from the same era, and a block
    placebo that draws the same number of runs with the same lengths. Episode-start rows and the
    leave-one-episode-out range de-cluster the overlapping windows.
    2018 RE-PRICED (counter-agent, review4): Yahoo's VXZ (Series B, VXZB until the 2019-01-30 rename) prints
    a flat 67.80 at zero volume for 169 sessions 2018-01-25..2019-01-02 (178 of 234 sessions in 2018 have a
    0.00% return, the whole Feb-2018 episode included). Decisions never read VXZ or ZVOL prices, so inside
    this study VXZ's daily returns on 2018-01-26..2019-01-31 are replaced by VIXM's (beta 0.99, corr 0.985
    on 2019-23; VIXM from daily.json) in (a) the ZVOL proxy and the VXZ mirror and (b) the engine's day
    return on the days it held VXZ or the proxy (holdings x re-priced returns; costs and everything else as
    the path). The add. 47 panel and engines_ts_synth.json are NOT rebuilt here: its harvester 2018 rests on
    the same stale prints (upstream fix pending, logged for the add. 47 pipeline).
 3. The engine path (add. 47 pipeline; engines_ts_synth.json HARV: costed daily returns and the weights
    earning each day, 1995-06-02..2026-11-04, plus the live 11-04 and 11-05 decisions): every decision
    close where the ZVOL weight rose, by regime, with ZVOL's and HARV's next 1/5/20 returns; HARV's daily
    return split by the regime at the decision close; the counterfactual that sends the ZVOL weight to
    PULS when the decision close is inverted (add. 39 C1, 2026-10-07: x2.11 -> x2.00, "its backwardation
    entries ARE the edge", killed; re-measured here). The path is the model (the approved logic on Yahoo
    closes), not Composer: the shadow ledger shows where the live weights differed (10-30: engine ZVOL 0.60
    vs live 0.52, a knife-edge).
 4. The live record: every monitor snapshot in git (vix_contango recorded since 2026-08-06; read-only git
    log/show) and the shadow ledger's live holdings per session.
Clustering tests next to every headline (review4): block placebo percentile, leave-one-episode-out range,
Welch t of the filter effect (rule-short vs sat-out inverted closes) with leave-one-run-out, trade LOO min.
Writes composer/results/harv-backwardation-2026-11-05.json (every number quoted in the write-up).
Usage: harv_backwardation.py  (stdlib only; rebuilds the long-panel cache via research/longrun if absent)
"""
import datetime
import json
import math
import os
import random
import statistics
import subprocess
import sys

S = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "composer", "results", "harv-backwardation-2026-11-05.json")
PATHS = os.path.join(S, "long1997", "engines_ts_synth.json")
DAILY = os.path.join(S, "overnight", "daily.json")
PANEL = os.path.join(S, "study4", "panel_vix.json")
LEDGER = os.path.join(REPO, "composer", "results", "monitor", "shadow-ledger.jsonl")
SNAP = "composer/results/monitor/last-snapshot.json"
HARV_SID = "ORQNCfZnA18wmsMWVhf8"
ASOF = "2026-11-05"
ZVOL_START, VXZ_START, VIX3M_START = "2023-04-19", "2018-01-25", "2006-07-17"
LIVE_START = "2026-07-21"              # first session on this logic (uQf3HrDb; XVtsDTV1 from 07-22, identical)
HORIZONS = (1, 5, 20)
BUCKETS = (("0..-3%", -0.03, 0.0), ("-3..-8%", -0.08, -0.03), ("< -8%", -9.0, -0.08))
PLACEBO_N = 2000
BLOCK_RNG = random.Random(20261106)      # its own stream, so the iid placebo draws are the same as before review4
# the stale-VXZ window: daily returns on REPRICE[0] < d <= REPRICE[1] come from VIXM (see the docstring)
REPRICE = ("2018-01-25", "2019-01-31")
REPRICE_BETA = {"ZVOL": -0.971, "VXZ": 1.0}
W18 = "VXZ 2018-01+ (2018 on VIXM)"                 # the window formerly labelled "real VXZ 2018-01+"
W18_COND = "-0.971 x VXZ (2018 on VIXM)"            # formerly "-0.971 x real VXZ"
# Yahoo closes read 2026-11-05 ~22:00 UTC; daily.json's 11-05 rows are the 16:00 closes (same values), but the
# add. 47 panel ends at the 11-04 close, so the day's closes are frozen here (the monitor's own read: VIX3M/VIX -9.33%).
CLOSE_1105 = {"^VIX": 28.18, "^VIX3M": 25.55, "SPY": 733.0, "ZVOL": 6.82, "VXZ": 48.21, "PULS": 49.50, "UVXY": 23.61}
CLOSE_1104 = {"^VIX": 16.61, "^VIX3M": 18.80, "SPY": 766.81, "ZVOL": 7.29, "VXZ": 45.21, "PULS": 49.50, "UVXY": 16.24}
LIVE_1105 = {"last_percent_change": 0.0202, "value": 38077.98, "prev_value": 37310.44,
             "held_during": {"VXZ": 0.3594, "PULS": 0.6396},            # decided at the 11-04 close (ledger: agree)
             "decided_at_close": {"ZVOL": 0.5987, "PULS": 0.4003},      # decided at the 11-05 close (ledger: agree)
             "vix_contango_snapshot": -0.0933}
HYG_1105 = {"close": 77.28, "prev": 77.52, "ret": -0.0031}              # the add. 12 guard reads HYG 1d < -1%
random.seed(20261105)


# ------------------------------------------------------------------ data
def load_panel():
    """ZVOL/VXZ/PULS/SPY/... long series (add. 47 panel, ts_synth mode) + VIX, VIX3M, the synthetic pre-2006 VIX3M"""
    if os.path.exists(PANEL):
        return json.load(open(PANEL))
    sys.path.insert(0, os.path.join(HERE, "longrun"))
    import long_panel as lp
    P, _ = lp.build_long_prices("ts_synth")
    out = {t: P[t] for t in ("ZVOL", "VXZ", "PULS", "SVXY", "SVIX", "VIXM", "VIXY", "UVXY", "SPY", "BIL")}
    for t in ("^VIX", "^VIX3M", "^VIX6M"):
        out[t] = lp.yh(t)
    _, s3, _, coefs = lp.synth_curves()
    out["^VIX3M_synth"] = s3
    out["_synth_coefs"] = coefs
    os.makedirs(os.path.dirname(PANEL), exist_ok=True)
    json.dump(out, open(PANEL, "w"))
    return out


class Px:
    """a price series: forward and daily returns by trading-day offset"""
    def __init__(self, s):
        self.d = sorted(s)
        self.p = [s[k] for k in self.d]
        self.i = {k: j for j, k in enumerate(self.d)}

    def fwd(self, d, k):
        j = self.i.get(d)
        return None if j is None or j + k >= len(self.d) else self.p[j + k] / self.p[j] - 1

    def ret(self, d):
        j = self.i.get(d)
        return None if not j else self.p[j] / self.p[j - 1] - 1

    def prev(self, d):
        j = self.i.get(d)
        return None if not j else self.d[j - 1]


def series(panel, t):
    s = {k: float(v) for k, v in panel[t].items()}
    last = max(s)
    if t in CLOSE_1105 and last == "2026-11-04":
        if t.startswith("^"):
            s[ASOF] = CLOSE_1105[t]
        else:                                       # adjusted series: scale by the raw close ratio
            s[ASOF] = s[last] * CLOSE_1105[t] / CLOSE_1104[t]
    return s


def daily_series(D, t, field="a"):
    rows = D[t]["rows"]
    return {d: float(rows[d][field]) for d in rows}


def reprice_px(s, vm, beta):
    """replace the price series' daily returns on REPRICE[0] < d <= REPRICE[1] with beta x VIXM's, anchored on the
    first unchanged close after the window: prices from there on are the prints, the window is rebuilt backward
    and everything before it is scaled by one factor, so every ratio outside the window is what it was"""
    lo, hi = REPRICE
    cal = sorted(s)
    pos = {d: i for i, d in enumerate(cal)}
    vcal = sorted(vm)
    vpos = {d: i for i, d in enumerate(vcal)}
    win = [d for d in cal if lo < d <= hi]
    assert win and [d for d in vcal if lo <= d <= hi] == [d for d in cal if lo <= d <= hi], "VIXM / series calendars differ in the window"
    out = dict(s)
    for d in reversed(win):
        r = beta * (vm[d] / vm[vcal[vpos[d] - 1]] - 1)
        out[cal[pos[d] - 1]] = out[d] / (1 + r)
    first = cal[pos[win[0]] - 1]
    k = out[first] / s[first]
    for d in cal:
        if d < first:
            out[d] = s[d] * k
    return out


def vxz_stale_diagnostics(D):
    """what is wrong with Yahoo's VXZ in 2018, and the VIXM fit used to replace it"""
    px, vol = daily_series(D, "VXZ"), {d: r["v"] for d, r in D["VXZ"]["rows"].items()}
    vm = daily_series(D, "VIXM")
    cal = sorted(px)
    rx = {cal[i]: px[cal[i]] / px[cal[i - 1]] - 1 for i in range(1, len(cal))}
    vc = sorted(vm)
    rm = {vc[i]: vm[vc[i]] / vm[vc[i - 1]] - 1 for i in range(1, len(vc))}
    zero_vol = [d for d in cal if d >= VXZ_START and vol[d] == 0]
    y18 = [d for d in rx if d[:4] == "2018"]

    def corr(ds):
        a, b = [rx[d] for d in ds], [rm[d] for d in ds]
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        sa, sb = math.sqrt(sum((x - ma) ** 2 for x in a)), math.sqrt(sum((y - mb) ** 2 for y in b))
        return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)

    fit = [d for d in rx if "2019-02-01" <= d <= "2023-04-18" and d in rm]
    a, b = [rm[d] for d in fit], [rx[d] for d in fit]
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    beta = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / sum((x - ma) ** 2 for x in a)
    win = [d for d in rx if REPRICE[0] < d <= REPRICE[1]]          # the sessions whose daily return is replaced
    return {"window": {"returns_from": win[0], "to": win[-1], "sessions": len(win), "anchor_close": REPRICE[0]},
            "source": "VIXM daily returns from daily.json (adjusted closes), beta " + ", ".join(f"{t} {v:+.3f}" for t, v in REPRICE_BETA.items()),
            "vxz_zero_volume_sessions": {"n": len(zero_vol), "from": zero_vol[0] if zero_vol else None, "to": zero_vol[-1] if zero_vol else None,
                                         "price": px.get(zero_vol[0]) if zero_vol else None},
            "vxz_2018_zero_return_sessions": {"n": sum(1 for d in y18 if rx[d] == 0), "of": len(y18)},
            "corr_vxz_vixm_2018": corr([d for d in y18 if d in rm]),
            "fit_2019_02_to_2023_04": {"beta_vxz_on_vixm": beta, "corr": corr(fit), "n": len(fit)},
            "feb_2018": {"2018-02-05": {"VXZ": rx.get("2018-02-05"), "VIXM": rm.get("2018-02-05")}},
            "upstream": "the add. 47 long panel (long_panel.py yh('VXZ') splice from 2018-01-25) and engines_ts_synth.json carry the same stale "
                        "prints, so add. 47's harvester 2018 rests on them too; fix pending upstream, applied inside this study only"}


def regime_map(panel):
    """{close: (depth = VIX3M/VIX - 1, VIX, 'real' | 'synth')}"""
    vix, v3, s3 = series(panel, "^VIX"), series(panel, "^VIX3M"), panel.get("^VIX3M_synth", {})
    R = {}
    for d in sorted(vix):
        if d in v3:
            R[d] = (v3[d] / vix[d] - 1.0, vix[d], "real")
        elif d in s3:
            R[d] = (float(s3[d]) / vix[d] - 1.0, vix[d], "synth")
    return R


def bucket(depth):
    if depth >= 0:
        return "contango"
    for name, lo, hi in BUCKETS:
        if lo < depth <= hi or (name == "0..-3%" and lo < depth < hi):
            return name
    return "< -8%"


# ------------------------------------------------------------------ stats
def stats(xs):
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        return {"n": 0}
    m, med = statistics.fmean(xs), statistics.median(xs)
    sd = statistics.stdev(xs) if n > 1 else 0.0
    return {"n": n, "mean": m, "median": med, "sd": sd, "t": (m / (sd / math.sqrt(n)) if sd > 0 and n > 1 else None),
            "win": sum(1 for x in xs if x > 0) / n, "total": math.prod(1 + x for x in xs) - 1}


def placebo(pool, n, actual, draws=PLACEBO_N):
    """mean of n random days from pool, drawn `draws` times: band and the percentile of the actual mean"""
    if n == 0 or n > len(pool) or actual is None:
        return None
    ms = sorted(statistics.fmean(random.sample(pool, n)) for _ in range(draws))
    return {"p05": ms[int(0.05 * draws)], "p50": ms[draws // 2], "p95": ms[int(0.95 * draws) - 1],
            "pct": sum(1 for m in ms if m <= actual) / draws, "draws": draws}


def runs_of(days, cal):
    """runs (episodes) of consecutive trading days (cal = the full calendar) -> list of lists"""
    pos = {d: i for i, d in enumerate(cal)}
    runs, prev = [], None
    for d in days:
        if prev is None or pos[d] != pos[prev] + 1:
            runs.append([d])
        else:
            runs[-1].append(d)
        prev = d
    return runs


def episodes(days, cal):
    """first day of each run"""
    return [r[0] for r in runs_of(days, cal)]


def block_placebo(pool, lens, actual, draws=PLACEBO_N):
    """the same number of runs with the same lengths, each a block of consecutive closes drawn at random from the
    era (pool in date order): keeps the clustering the iid placebo ignores"""
    if actual is None or not lens or max(lens) >= len(pool):
        return None
    ms = []
    for _ in range(draws):
        got = []
        for L in lens:
            st = BLOCK_RNG.randrange(0, len(pool) - L)
            got.extend(pool[st:st + L])
        ms.append(statistics.fmean(got))
    ms.sort()
    return {"p05": ms[int(0.05 * draws)], "p50": ms[draws // 2], "p95": ms[int(0.95 * draws) - 1],
            "pct": sum(1 for m in ms if m <= actual) / draws, "draws": draws, "runs": len(lens)}


def loo_runs(runs, val):
    """leave one run (episode) out: the mean and t of the rest; each run's share of the sum"""
    if len(runs) < 2:
        return None
    tot = sum(val[d] for r in runs for d in r)
    rows = []
    for r in runs:
        st = stats([val[d] for q in runs if q is not r for d in q])
        rows.append({"start": r[0], "len": len(r), "share_of_sum": (sum(val[d] for d in r) / tot) if tot else None,
                     "mean_without": st.get("mean"), "t_without": st.get("t")})
    lo_, hi_ = min(rows, key=lambda x: x["mean_without"]), max(rows, key=lambda x: x["mean_without"])
    return {"min": lo_["mean_without"], "max": hi_["mean_without"], "min_without": lo_, "max_without": hi_,
            "largest_shares": sorted(rows, key=lambda x: -abs(x["share_of_sum"] or 0))[:3]}


def welch(a, b):
    """Welch t for the difference of two means (unequal variances)"""
    a, b = [x for x in a if x is not None], [x for x in b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    return (statistics.fmean(a) - statistics.fmean(b)) / se if se > 0 else None


# ------------------------------------------------------------------ 1-2. ZVOL conditional on the regime
def conditional(Z, X, R):
    eras = [("real ZVOL", ZVOL_START, ASOF), (W18_COND, VXZ_START, "2023-04-18"),
            ("modeled VXZ", VIX3M_START, "2018-01-24"), ("all since 2006-07", VIX3M_START, ASOF)]
    out = {}
    for name, lo, hi in eras:
        era = {"from": lo, "to": hi, "horizons": {}}
        for k in HORIZONS:
            days = [d for d in Z.d if lo <= d <= hi and d in R and R[d][2] == "real" and Z.fwd(d, k) is not None]
            groups = {"all": days, "contango": [d for d in days if R[d][0] >= 0], "backwardation": [d for d in days if R[d][0] < 0]}
            for b, _, _ in BUCKETS:
                groups[b] = [d for d in days if bucket(R[d][0]) == b]
            pool = [Z.fwd(d, k) for d in days]
            h = {}
            for g, ds in groups.items():
                zs = [Z.fwd(d, k) for d in ds]
                row = {"zvol": stats(zs), "vxz": stats([X.fwd(d, k) for d in ds])}
                if g != "all" and ds:
                    row["placebo"] = placebo(pool, len(ds), row["zvol"]["mean"])
                    runs = runs_of(ds, Z.d)
                    row["episodes"] = len(runs)
                    row["episode_start"] = stats([Z.fwd(r[0], k) for r in runs])
                    if g in ("backwardation", "< -8%"):      # the clustering tests next to the headline numbers
                        row["block_placebo"] = block_placebo(pool, [len(r) for r in runs], row["zvol"]["mean"])
                        row["loo_episodes"] = loo_runs(runs, {d: Z.fwd(d, k) for d in ds})
                h[g] = row
            era["horizons"][str(k)] = h
            era["days"] = len(days) if k == 1 else era.get("days")
        out[name] = era
    return out


# ------------------------------------------------------------------ 3. the engine path
def load_engine():
    E = json.load(open(PATHS))["HARV"]
    rets = {d: float(v) for d, v in E["rets"].items()}
    hold = {d: {t: float(w) for t, w in h.items()} for d, h in E["hold"].items()}
    days = sorted(d for d in rets if d in hold)
    # the live days past the panel: 11-05 earned the 11-04 decision (live +2.02%); 11-05's decision earns 11-06
    rets[ASOF] = LIVE_1105["last_percent_change"]
    hold[ASOF] = dict(LIVE_1105["held_during"])
    days.append(ASOF)
    return days, rets, hold


def reprice_engine(days, rets, hold, Z0, X0, Z, X):
    """the engine's day return on the re-priced days = the path's return + holdings x (re-priced minus printed leg
    return); decisions never read those prices and the costs stay as the path has them"""
    lo, hi = REPRICE
    out, n_on, cum0, cum1, worst = dict(rets), 0, 1.0, 1.0, (0.0, None)
    for d in days:
        if lo < d <= hi:
            wz, wx = hold[d].get("ZVOL", 0.0), hold[d].get("VXZ", 0.0)
            dz = (Z.ret(d) - Z0.ret(d)) if wz else 0.0
            dx = (X.ret(d) - X0.ret(d)) if wx else 0.0
            out[d] = rets[d] + wz * dz + wx * dx
            n_on += (wz > 0 or wx > 0)
            cum0 *= 1 + rets[d]
            cum1 *= 1 + out[d]
            if out[d] < worst[0]:
                worst = (out[d], d)
    return out, {"engine_sessions_in_window": sum(1 for d in days if lo < d <= hi), "sessions_on_vxz_or_zvol": n_on,
                 "window_compounded_as_printed": cum0 - 1, "window_compounded_repriced": cum1 - 1,
                 "worst_repriced_day": {"date": worst[1], "harv": worst[0], "as_printed": rets.get(worst[1]), "hold": hold.get(worst[1])}}


def fwd_engine(days, rets, i, k):
    if i + k >= len(days):
        return None
    return math.prod(1 + rets[days[j]] for j in range(i + 1, i + k + 1)) - 1


def entries(days, rets, hold, R, Z, X, SPY):
    """every decision close at which the ZVOL weight rose (weights earning the next day > weights earning today)"""
    dec = [(days[i], hold[days[i]], hold[days[i + 1]], i) for i in range(len(days) - 1)]
    dec.append((ASOF, hold[ASOF], dict(LIVE_1105["decided_at_close"]), len(days) - 1))
    rows = []
    for D, w0, w1, i in dec:
        z0, z1 = w0.get("ZVOL", 0.0), w1.get("ZVOL", 0.0)
        if z1 <= z0 + 1e-9 or D not in R or R[D][2] != "real":
            continue
        depth, vix, _ = R[D]
        rows.append({"date": D, "depth": depth, "bucket": bucket(depth), "vix": vix, "spy_day": SPY.ret(D), "harv_day": rets.get(D),
                     "vxz_held": w0.get("VXZ", 0.0), "zvol_from": z0, "zvol_to": z1, "fresh": z0 < 1e-9,
                     "zvol_fwd": {str(k): Z.fwd(D, k) for k in HORIZONS}, "vxz_fwd": {str(k): X.fwd(D, k) for k in HORIZONS},
                     "harv_fwd": {str(k): fwd_engine(days, rets, i, k) for k in HORIZONS},
                     "era": "real" if D >= ZVOL_START else ("vxz" if D >= VXZ_START else "model"),
                     "repriced": any(REPRICE[0] < days[j] <= REPRICE[1] for j in range(i + 1, min(i + 21, len(days)))),
                     "live": D >= LIVE_START})
    return rows


WINDOWS = (("real ZVOL 2023-04+", ZVOL_START), (W18, VXZ_START), ("2015-06+", "2015-06-01"), ("2006-07+", VIX3M_START))


def hold_lengths(days, hold, rows):
    """sessions the engine kept any ZVOL weight after each entry (the earning days until the weight returns to 0)"""
    pos = {d: i for i, d in enumerate(days)}
    for r in rows:
        i = pos.get(r["date"])
        n = 0
        if i is not None:
            j = i + 1
            while j < len(days) and hold[days[j]].get("ZVOL", 0.0) > 0:
                n += 1
                j += 1
            if j >= len(days):
                n = None                      # still open at the end of the path
        r["hold_len"] = n


def trades(days, rets, hold, R, Z):
    """ZVOL episodes: from a fresh entry (weight 0 -> >0 at the decision close) to the first close that sends the
    weight back to 0. P&L = the engine's compounded return over the episode's earning days; the ZVOL leg's
    contribution = sum of weight x ZVOL return; regime = the entry close"""
    out, i = [], 0
    while i < len(days) - 1:
        D = days[i]
        if hold[D].get("ZVOL", 0.0) < 1e-9 and hold[days[i + 1]].get("ZVOL", 0.0) > 1e-9 and D in R and R[D][2] == "real":
            j, pnl, contrib, mx = i + 1, 1.0, 0.0, 0.0
            while j < len(days) and hold[days[j]].get("ZVOL", 0.0) > 1e-9:
                pnl *= 1 + rets[days[j]]
                rz = Z.ret(days[j])
                w = hold[days[j]]["ZVOL"]
                contrib += w * rz if rz is not None else 0.0
                mx = max(mx, w)
                j += 1
            out.append({"entry": D, "exit_close": days[j - 1], "sessions": j - 1 - i, "open": j >= len(days), "depth": R[D][0], "bucket": bucket(R[D][0]),
                        "vix": R[D][1], "max_w": mx, "pnl": pnl - 1, "zvol_contrib": contrib,
                        "era": "real" if D >= ZVOL_START else ("vxz" if D >= VXZ_START else "model")})
            i = j
        else:
            i += 1
    summary = {}
    for wname, lo in WINDOWS:
        sub = [t for t in out if t["entry"] >= lo and not t["open"]]
        W = {"from": lo, "n": len(sub), "open": sum(1 for t in out if t["entry"] >= lo and t["open"]), "groups": {}}
        for g in ("contango", "backwardation", "0..-3%", "-3..-8%", "< -8%"):
            ts = [t for t in sub if (t["bucket"] == g) or (g == "backwardation" and t["depth"] < 0)]
            best = max(ts, key=lambda t: t["pnl"]) if ts else None
            W["groups"][g] = {"n": len(ts), "pnl": stats([t["pnl"] for t in ts]), "zvol_contrib": stats([t["zvol_contrib"] for t in ts]),
                              "sessions_mean": statistics.fmean([t["sessions"] for t in ts]) if ts else None,
                              "sessions_median": statistics.median([t["sessions"] for t in ts]) if ts else None,
                              "sum_pnl_pp": sum(t["pnl"] for t in ts) * 100, "worst": min(ts, key=lambda t: t["pnl"])["entry"] if ts else None,
                              "worst_pnl": min(t["pnl"] for t in ts) if ts else None,
                              "best": best["entry"] if best else None, "best_pnl": best["pnl"] if best else None,
                              # leave-one-trade-out: the smallest mean after dropping any one trade (= dropping the best)
                              "loo_min": min(statistics.fmean([t["pnl"] for t in ts if t is not u]) for u in ts) if len(ts) > 1 else None}
        summary[wname] = W
    return {"rows": out, "summary": summary}


def summarize_entries(rows):
    out = {}
    for wname, lo in WINDOWS:
        sub = [r for r in rows if r["date"] >= lo and r["date"] < ASOF]       # 11-05's outcomes are pending
        W = {"from": lo, "n": len(sub), "pending": sum(1 for r in rows if r["date"] >= lo and r["date"] >= ASOF), "groups": {}}
        for g in ("contango", "backwardation", "0..-3%", "-3..-8%", "< -8%"):
            rs = [r for r in sub if (r["bucket"] == g) or (g == "backwardation" and r["depth"] < 0)]
            hl = [r["hold_len"] for r in rs if r.get("hold_len") is not None]
            row = {"n": len(rs), "fresh": sum(1 for r in rs if r["fresh"]),
                   "mean_zvol_to": statistics.fmean([r["zvol_to"] for r in rs]) if rs else None,
                   "mean_vix": statistics.fmean([r["vix"] for r in rs]) if rs else None,
                   "hold_len_mean": statistics.fmean(hl) if hl else None, "hold_len_median": statistics.median(hl) if hl else None}
            for k in HORIZONS:
                row[f"zvol_{k}"] = stats([r["zvol_fwd"][str(k)] for r in rs])
                row[f"vxz_{k}"] = stats([r["vxz_fwd"][str(k)] for r in rs])
                row[f"harv_{k}"] = stats([r["harv_fwd"][str(k)] for r in rs])
            fr = [r for r in rs if r["fresh"]]
            row["fresh_harv_20"] = stats([r["harv_fwd"]["20"] for r in fr])
            row["fresh_zvol_20"] = stats([r["zvol_fwd"]["20"] for r in fr])
            W["groups"][g] = row
        out[wname] = W
    return out


def path_split(days, rets, hold, R, Z, P):
    """HARV's daily return by the regime at the decision close (the previous session), per window, with the
    ZVOL-leg contribution and the counterfactuals ZVOL -> PULS on inverted decision closes"""
    out = {}
    for wname, lo, synth_ok in (("1995-06+ (synthetic curve before 2006-07)", "1995-06-02", True), ("2006-07+", VIX3M_START, False),
                                ("2015-06+", "2015-06-01", False), (W18, VXZ_START, False), ("real ZVOL 2023-04+", ZVOL_START, False)):
        acc = {}
        base, cf_all, cf_deep = 1.0, 1.0, 1.0
        peak = {"base": 1.0, "cf_all": 1.0, "cf_deep": 1.0}
        dd = {"base": 0.0, "cf_all": 0.0, "cf_deep": 0.0}
        n_days, n_synth, legs = 0, 0, []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            if d < lo or p not in R or (R[p][2] == "synth" and not synth_ok):
                continue
            depth, _, src = R[p]
            n_days += 1
            n_synth += src == "synth"
            r = rets[d]
            wz = hold[d].get("ZVOL", 0.0)
            rz, rp = Z.ret(d), P.ret(d)
            cz = wz * rz if (wz and rz is not None) else 0.0
            g = "backwardation" if depth < 0 else "contango"
            for key in {g, bucket(depth)}:            # a contango day has one key, an inverted day two (regime + depth bucket)
                a = acc.setdefault(key, {"n": 0, "zvol_days": 0, "zvol_w": 0.0, "vxz_days": 0, "sum_r": 0.0, "log_r": 0.0, "zvol_contrib": 0.0, "wins": 0})
                a["n"] += 1
                a["zvol_days"] += wz > 0
                a["vxz_days"] += hold[d].get("VXZ", 0.0) > 0
                a["zvol_w"] += wz
                a["sum_r"] += r
                a["log_r"] += math.log1p(r)
                a["zvol_contrib"] += cz
                a["wins"] += r > 0
            base *= 1 + r
            adj = (wz * ((rz or 0.0) - (rp or 0.0))) if wz else 0.0
            cf_all *= 1 + (r - adj if depth < 0 else r)
            cf_deep *= 1 + (r - adj if depth <= -0.08 else r)
            if depth < 0 and wz:
                legs.append((adj, d))
            for key, v in (("base", base), ("cf_all", cf_all), ("cf_deep", cf_deep)):
                peak[key] = max(peak[key], v)
                dd[key] = max(dd[key], 1 - v / peak[key])
        legs.sort()
        yrs = n_days / 252
        for key, a in acc.items():
            a["mean_daily"] = a["sum_r"] / a["n"]
            a["compounded"] = math.exp(a["log_r"]) - 1
            a["zvol_share_of_days"] = a["zvol_days"] / a["n"]
            a["mean_zvol_w"] = a["zvol_w"] / a["n"]
            a["win"] = a["wins"] / a["n"]
        tot_log = sum(a["log_r"] for k, a in acc.items() if k in ("backwardation", "contango"))
        for key in ("backwardation", "contango"):
            if key in acc:
                acc[key]["share_of_log_return"] = acc[key]["log_r"] / tot_log if tot_log else None
        out[wname] = {"from": lo, "days": n_days, "synthetic_regime_days": n_synth, "regimes": acc,
                      "base": {"multiple": base, "cagr": base ** (1 / yrs) - 1 if yrs else None, "maxdd": dd["base"]},
                      "cf_zvol_to_puls_when_inverted": {"multiple": cf_all, "cagr": cf_all ** (1 / yrs) - 1 if yrs else None, "maxdd": dd["cf_all"]},
                      "cf_zvol_to_puls_when_deep": {"multiple": cf_deep, "cagr": cf_deep ** (1 / yrs) - 1 if yrs else None, "maxdd": dd["cf_deep"]},
                      # concentration of the counterfactual: the largest single ZVOL-leg days on inverted decisions
                      "ratio_base_over_cf": base / cf_all if cf_all else None,
                      "largest_zvol_leg_days": [{"date": d, "leg": a} for a, d in legs[-3:][::-1]],
                      "worst_zvol_leg_days": [{"date": d, "leg": a} for a, d in legs[:2]],
                      "ratio_without_largest_leg_day": (base / cf_all / (1 + legs[-1][0])) if legs and cf_all else None}
    return out


# ------------------------------------------------------------------ 4. the harvester number
def harvester_number(days, rets, hold, Z, X, R, snaps):
    vxz_ret = CLOSE_1105["VXZ"] / CLOSE_1104["VXZ"] - 1
    model = LIVE_1105["held_during"]["VXZ"] * vxz_ret + LIVE_1105["held_during"]["PULS"] * (CLOSE_1105["PULS"] / CLOSE_1104["PULS"] - 1)
    real = [d for d in days if ZVOL_START <= d <= "2026-11-04"]
    xs = sorted(rets[d] for d in real)
    lpc = LIVE_1105["last_percent_change"]
    rank = sum(1 for x in xs if x <= lpc) / len(xs)
    qs = {q: xs[min(len(xs) - 1, int(q * len(xs)))] for q in (0.5, 0.9, 0.99)}
    # the number as a signal: HARV's day return vs ZVOL's next 20 sessions
    def corr(a, b):
        n = len(a)
        if n < 3:
            return None
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        sa, sb = math.sqrt(sum((x - ma) ** 2 for x in a)), math.sqrt(sum((y - mb) ** 2 for y in b))
        return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else None
    sig = {}
    for wname, lo in (("real ZVOL 2023-04+", ZVOL_START), ("2006-07+", VIX3M_START)):
        ds = [d for d in days if d >= lo and d in R and R[d][2] == "real" and Z.fwd(d, 20) is not None and d in rets]
        a, b = [rets[d] for d in ds], [Z.fwd(d, 20) for d in ds]
        big = [d for d in ds if rets[d] >= 0.01]
        bigv = [d for d in big if hold[d].get("VXZ", 0.0) > 0]
        sig[wname] = {"n": len(ds), "corr_harv_day_vs_zvol_fwd20": corr(a, b),
                      "harv_day_ge_1pct": {"n": len(big), "zvol_fwd20": stats([Z.fwd(d, 20) for d in big]), "vxz_fwd20": stats([X.fwd(d, 20) for d in big])},
                      "harv_day_ge_1pct_on_vxz": {"n": len(bigv), "zvol_fwd20": stats([Z.fwd(d, 20) for d in bigv]), "backwardation_share": (statistics.fmean([R[d][0] < 0 for d in bigv]) if bigv else None)},
                      "unconditional_zvol_fwd20": stats(b)}
    live = {}
    for s in snaps:
        if s["lpc"] is not None:
            live[s["session"]] = s["lpc"]
    lv = sorted(live.values())
    return {"what_it_is": "monitor.py line 333: the symphony's last_percent_change from Composer's symphony-stats-meta, i.e. HARV's own day return; not a signal",
            "live_1105": lpc, "value_based_1105": LIVE_1105["value"] / LIVE_1105["prev_value"] - 1,
            "model_close_to_close_1105": model, "vxz_ret_1105": vxz_ret, "held_during_1105": LIVE_1105["held_during"],
            "gap_live_minus_model": lpc - model,
            "gap_attribution": "plausibly the 15:50 fills on 11-04 and 11-05 against the 16:00 closes (lpc +2.02 vs deposit-adjusted value "
                               "+2.06 vs close-to-close model +2.38%); asserted from the mechanism, not measured against fill prints",
            "history_engine_real_era": {"from": real[0], "to": real[-1], "n": len(xs), "mean": statistics.fmean(xs), "sd": statistics.stdev(xs),
                                        "p50": qs[0.5], "p90": qs[0.9], "p99": qs[0.99], "max": xs[-1], "min": xs[0],
                                        "days_ge_1105": sum(1 for x in xs if x >= lpc), "percentile_of_1105": rank},
            "history_live_snapshots": {"n": len(lv), "from": min(live), "to": max(live), "mean": statistics.fmean(lv) if lv else None, "max": lv[-1] if lv else None,
                                       "rank_of_1105": (sum(1 for x in lv if x <= lpc) / len(lv)) if lv else None},
            "as_a_signal": sig}


# ------------------------------------------------------------------ 5. the live record
def git_snapshots():
    """every committed last-snapshot.json: (taken_at, vix_contango, HARV holdings, last_percent_change, value)"""
    try:
        shas = subprocess.run(["git", "-C", REPO, "log", "--format=%H", "--", SNAP], capture_output=True, text=True, check=True).stdout.split()
    except Exception as e:  # noqa: BLE001
        print("  (git history unavailable:", e, ")")
        return []
    out = []
    for sha in shas:
        try:
            s = json.loads(subprocess.run(["git", "-C", REPO, "show", f"{sha}:{SNAP}"], capture_output=True, text=True, check=True).stdout)
        except Exception:  # noqa: BLE001
            continue
        h = s.get("symphonies", {}).get(HARV_SID) or {}
        ta = s.get("taken_at")
        if not ta:
            continue
        t = datetime.datetime.fromisoformat(ta)
        et = t.astimezone(datetime.timezone(datetime.timedelta(hours=-4 if "2026-03-08" <= ta[:10] < "2026-11-01" else -5)))
        out.append({"taken_at": ta, "session": et.date().isoformat(), "et_time": et.strftime("%H:%M"), "vix_contango": s.get("vix_contango"),
                    "holdings": h.get("holdings"), "lpc": h.get("last_percent_change"), "value": h.get("value")})
    out.sort(key=lambda x: x["taken_at"])
    seen, dedup = set(), []
    for x in out:
        key = (x["taken_at"], json.dumps(x["holdings"], sort_keys=True))
        if key not in seen:
            seen.add(key)
            dedup.append(x)
    return dedup


def live_record(snaps, R, Z, X, days, rets, hold):
    ledger = {}
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("engine") == "HARV" and r.get("live"):
                ledger[r["date"]] = {"live": r["live"], "status": r.get("status"), "target": r.get("target"), "src": r.get("src")}
    sessions = sorted(d for d in Z.d if LIVE_START <= d <= ASOF and d in R)
    last_snap = {}
    for s in snaps:
        if s["et_time"] >= "16:00" or s["session"] not in last_snap:
            last_snap[s["session"]] = s
    rows = []
    for d in sessions:
        sn = last_snap.get(d) or {}
        lg = ledger.get(d) or {}
        rows.append({"date": d, "depth_close": R[d][0], "vix": R[d][1], "snapshot_contango": sn.get("vix_contango"), "snapshot_et": sn.get("et_time"),
                     "decided_at_close": lg.get("live") or sn.get("holdings"), "status": lg.get("status"), "harv_day": sn.get("lpc"),
                     "zvol_day": Z.ret(d), "vxz_day": X.ret(d), "zvol_fwd": {str(k): Z.fwd(d, k) for k in HORIZONS}})
    bw_close = [r for r in rows if r["depth_close"] < 0]
    alerts = [s for s in snaps if s["vix_contango"] is not None and s["vix_contango"] < 0]
    # the engine path is the model, not Composer: ledger sessions where the live weights differ from the engine's
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    mvl = []
    for d, lg in sorted(ledger.items()):
        eng = dict(LIVE_1105["decided_at_close"]) if d == ASOF else hold.get(nxt.get(d))
        if eng is None or not lg["live"]:
            continue
        gap = max(abs(lg["live"].get(t, 0.0) - eng.get(t, 0.0)) for t in set(lg["live"]) | set(eng))
        if gap > 0.02:
            mvl.append({"date": d, "live": lg["live"], "engine": eng, "status": lg["status"], "max_gap": gap})
    return {"from": LIVE_START, "to": ASOF, "sessions": len(sessions), "snapshots_with_contango": sum(1 for s in snaps if s["vix_contango"] is not None),
            "model_vs_live": {"ledger_sessions": len(ledger), "off_by_more_than_2pp": len(mvl), "rows": mvl,
                              "note": "the engine path = the approved logic on Yahoo closes (the model); Composer's live weights differ on knife-edge "
                                      "and no-rebalance sessions, e.g. 10-30 engine ZVOL 0.60 vs live 0.52"},
            "first_snapshot_with_contango": next((s["session"] for s in snaps if s["vix_contango"] is not None), None),
            "backwardation_closes": [{k: r[k] for k in ("date", "depth_close", "vix", "snapshot_contango", "decided_at_close", "status", "harv_day", "zvol_day", "zvol_fwd")} for r in bw_close],
            "backwardation_alerts": [{"session": s["session"], "et_time": s["et_time"], "vix_contango": s["vix_contango"], "holdings": s["holdings"], "lpc": s["lpc"]} for s in alerts],
            "shallowest_contango_closes": sorted(({"date": r["date"], "depth": r["depth_close"]} for r in rows), key=lambda x: x["depth"])[:6],
            "zvol_sessions_live": sum(1 for r in rows if (r["decided_at_close"] or {}).get("ZVOL")),
            "rows": rows}


# ------------------------------------------------------------------ the rule, with its 11-05 values
def rule_trace(D):
    sys.path.insert(0, os.path.join(REPO, "composer", "scripts"))
    try:
        import shadow_runner as sr
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    cfg = sr.load_manifest()["HARV"]
    era = sr.era_for(cfg, ASOF)
    tree = sr.load_tree(era)
    prices = {}
    for t in sr.tree_tickers(tree):
        rows = D[t]["rows"]
        prices[t] = {d: float(rows[d]["a"]) for d in sorted(rows) if d < ASOF}
        prices[t][ASOF] = prices[t]["2026-11-04"] * CLOSE_1105[t] / CLOSE_1104[t]
    out = {"version": era["version"], "tree": era["tree"], "weights_by_window": {"2": 36, "3": 16, "4": 8, "5": 8, "6": 8, "7": 8, "8": 8, "9": 4, "10": 4},
           "words": ("nine voters on Wilder RSI(SPY, w), w = 2..10, weighted 36/16/8/8/8/8/8/4/4: RSI < 25 -> ZVOL (unless RSI(UVXY,14) > 70 -> PULS); "
                     "RSI > 80 -> VXZ; else PULS. ZVOL weight = sum of the weights of the voters with SPY RSI under 25. No term-structure input; "
                     "no HYG condition in any saved version (add. 48)."), "decisions": {}}
    sim = sr.Shadow({t: prices[t] for t in prices})
    for d in ("2026-11-04", ASOF):
        _, target, tr = sr.run_engine(prices, tree, d)
        out["decisions"][d] = {"target": target, "rsi_spy": {str(w): sim.ind("relative-strength-index", "SPY", w, d) for w in range(2, 11)},
                               "rsi_uvxy_14": sim.ind("relative-strength-index", "UVXY", 14, d),
                               "closest": sr.explain(tr) if isinstance(tr, list) else tr}
    return out


# ------------------------------------------------------------------ main
def main():
    panel = load_panel()
    for t in ("^VIX", "^VIX3M", "ZVOL", "VXZ"):
        v = float(panel[t]["2026-11-04"])
        assert abs(v / CLOSE_1104[t] - 1) < 2e-3, (t, v, CLOSE_1104[t])
    D = json.load(open(DAILY))
    R = regime_map(panel)
    z_raw, x_raw = series(panel, "ZVOL"), series(panel, "VXZ")
    Z0, X0 = Px(z_raw), Px(x_raw)                       # as printed (stale 2018): used only for the re-pricing delta
    vm = daily_series(D, "VIXM")
    Z, X = Px(reprice_px(z_raw, vm, REPRICE_BETA["ZVOL"])), Px(reprice_px(x_raw, vm, REPRICE_BETA["VXZ"]))
    P, SPY = Px(series(panel, "PULS")), Px(series(panel, "SPY"))
    days, rets0, hold = load_engine()
    rets, rp_engine = reprice_engine(days, rets0, hold, Z0, X0, Z, X)
    reprice = vxz_stale_diagnostics(D)
    reprice["engine"] = rp_engine
    reprice["check_2018_02_05"] = {"as_printed": rets0.get("2018-02-05"), "repriced": rets.get("2018-02-05"), "hold": hold.get("2018-02-05"),
                                   "zvol_proxy_as_printed": Z0.ret("2018-02-05"), "zvol_proxy_repriced": Z.ret("2018-02-05")}
    assert abs(Z.fwd("2019-01-31", 20) - Z0.fwd("2019-01-31", 20)) < 1e-12 and abs(Z.fwd("2017-11-01", 20) - Z0.fwd("2017-11-01", 20)) < 1e-12, "re-pricing leaked outside its window"
    snaps = git_snapshots()

    real_bw = [d for d in Z.d if d >= ZVOL_START and d in R and R[d][0] < 0]
    real_bw_out = [d for d in real_bw if d < ASOF]                       # closes with an outcome (11-05's is pending)
    real_deep = [d for d in real_bw if R[d][0] <= -0.08]
    real_deep_out = [d for d in real_deep if d < ASOF]
    res = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "asof": ASOF,
           "inputs": {"engine_path": PATHS, "panel": PANEL, "daily": DAILY, "closes_1105": CLOSE_1105, "closes_1104": CLOSE_1104, "live_1105": LIVE_1105,
                      "hyg_1105": HYG_1105, "zvol_proxy": "ZVOL = -0.971 x VXZ daily before 2023-04-19 (add. 47 long_panel.py); VXZ real from 2018-01-25 but "
                      "re-priced on VIXM through 2019-01-31 in this study (see vxz_reprice), the vix_etp term-structure model on the real VIX3M/VIX6M from "
                      "2006-07-18, a synthetic VIX-only curve before (ts_synth); PULS = BIL in the panel. The VXZ 'mirror' is an identity before 2023-04-19",
                      "vxz_reprice": reprice,
                      "regime": "VIX3M/VIX - 1 at the close; real VIX3M from 2006-07-17; synthetic curve (coefs in panel) before, used only for the 1995+ split",
                      "synth_curve_coefs": panel.get("_synth_coefs")},
           "regime_counts": {"real_zvol_era_days": sum(1 for d in Z.d if d >= ZVOL_START and d in R), "real_zvol_era_backwardation_days": len(real_bw),
                             "real_zvol_era_episodes": len(episodes(real_bw, Z.d)), "real_zvol_era_backwardation_dates": real_bw,
                             "real_zvol_era_backwardation_days_with_outcomes": len(real_bw_out), "real_zvol_era_episodes_with_outcomes": len(episodes(real_bw_out, Z.d)),
                             "real_zvol_era_deep_days": len(real_deep), "real_zvol_era_deep_episodes": len(episodes(real_deep, Z.d)),
                             "real_zvol_era_deep_days_with_outcomes": len(real_deep_out), "real_zvol_era_deep_episodes_with_outcomes": len(episodes(real_deep_out, Z.d)),
                             "count_bases": "'with outcomes' = closes before 2026-11-05 (every table of outcomes); the other base adds the 11-05 close, "
                                            "which is one more close, episode, deep close and deep episode",
                             "since_2006_days": sum(1 for d in R if R[d][2] == "real"), "since_2006_backwardation_days": sum(1 for d in R if R[d][2] == "real" and R[d][0] < 0),
                             "depth_1105": R[ASOF][0], "vix_1105": R[ASOF][1], "bucket_1105": bucket(R[ASOF][0]), "spy_1105": SPY.ret(ASOF), "zvol_1105": Z.ret(ASOF), "vxz_1105": X.ret(ASOF)},
           "rule": rule_trace(D)}
    print("conditional ZVOL table ...", flush=True)
    res["conditional"] = conditional(Z, X, R)
    rows = entries(days, rets, hold, R, Z, X, SPY)
    hold_lengths(days, hold, rows)
    res["entries"] = {"rows": rows, "summary": summarize_entries(rows)}
    res["trades"] = trades(days, rets, hold, R, Z)
    res["path_split"] = path_split(days, rets, hold, R, Z, P)
    # the filter effect: inverted closes the rule shorts vol into (ZVOL weight > 0 the next session) vs the others
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    nxt[ASOF] = "2026-11-06"
    hold_next = {d: hold[nxt[d]].get("ZVOL", 0.0) for d in days if nxt[d] in hold}
    hold_next[ASOF] = LIVE_1105["decided_at_close"]["ZVOL"]
    fe = {}
    for wname, lo in WINDOWS:
        inv = [d for d in Z.d if lo <= d < ASOF and d in R and R[d][2] == "real" and R[d][0] < 0 and d in hold_next]
        g_in = [d for d in inv if hold_next[d] > 0]
        g_out = [d for d in inv if hold_next[d] <= 0]
        runs_in = runs_of(g_in, Z.d)
        v1 = {d: Z.fwd(d, 1) for d in g_in}
        lo1 = loo_runs(runs_in, v1)
        fe[wname] = {"inverted_closes": len(inv), "rule_short_vol": len(g_in), "rule_not": len(g_out),
                     "with": {str(k): stats([Z.fwd(d, k) for d in g_in]) for k in HORIZONS},
                     "without": {str(k): stats([Z.fwd(d, k) for d in g_out]) for k in HORIZONS},
                     "deep_with": {str(k): stats([Z.fwd(d, k) for d in g_in if R[d][0] <= -0.08]) for k in HORIZONS},
                     "deep_without": {str(k): stats([Z.fwd(d, k) for d in g_out if R[d][0] <= -0.08]) for k in HORIZONS},
                     # the fair tests of the selection (the contango entries are NOT a placebo for it): Welch t of with vs without,
                     # and the next-1 mean across the runs the rule-short closes fall in, leaving one run out
                     "welch_t": {str(k): welch([Z.fwd(d, k) for d in g_in], [Z.fwd(d, k) for d in g_out]) for k in HORIZONS},
                     "short_vol_runs": len(runs_in),
                     "run_mean_of_means_1": statistics.fmean([statistics.fmean([v1[d] for d in r if v1[d] is not None]) for r in runs_in]) if runs_in else None,
                     "loo_run_min_1": lo1["min"] if lo1 else None, "loo_run_max_1": lo1["max"] if lo1 else None}
    res["filter_effect"] = fe
    # daily series for the exhibit: the earning day d, ZVOL's return on d, the regime at the decision close (d-1),
    # the engine's return and ZVOL weight on d (2006-07+; 11-05 = live)
    ser = []
    for i in range(1, len(days)):
        d, p = days[i], days[i - 1]
        if d < VIX3M_START or p not in R or R[p][2] != "real":
            continue
        ser.append([d, round(Z.ret(d) or 0.0, 5), round(R[p][0], 4), round(rets[d], 5), hold[d].get("ZVOL", 0.0), hold[d].get("VXZ", 0.0)])
    res["series"] = {"columns": ["date", "zvol_ret", "depth_at_decision_close", "harv_ret", "zvol_w", "vxz_w"], "rows": ser,
                     "zvol_1105": {"ret": Z.ret(ASOF), "depth_prev": R["2026-11-04"][0]},
                     "reprice_window": {"from": REPRICE[0], "to": REPRICE[1], "label": "VXZ re-priced on VIXM"}}
    res["harvester_number"] = harvester_number(days, rets, hold, Z, X, R, snaps)
    res["live"] = live_record(snaps, R, Z, X, days, rets, hold)
    # 11-05 in context: where today's entry sits among past backwardation entries
    bw = [r for r in rows if r["depth"] < 0 and r["date"] < ASOF]
    deep = [r for r in bw if r["depth"] <= -0.08]
    flips = [r for r in bw if r["vxz_held"] > 0 and (r["harv_day"] or 0) >= 0.01]
    today = next(r for r in rows if r["date"] == ASOF)
    res["context_1105"] = {"entry": today, "n_backwardation_entries_before": len(bw),
                           "depth_percentile_among_bw_entries": sum(1 for r in bw if r["depth"] <= today["depth"]) / len(bw) if bw else None,
                           "vix_percentile_among_bw_entries": sum(1 for r in bw if r["vix"] <= today["vix"]) / len(bw) if bw else None,
                           "weight_percentile_among_bw_entries": sum(1 for r in bw if r["zvol_to"] <= today["zvol_to"]) / len(bw) if bw else None,
                           "deep_entries": deep, "deep_summary": {k: stats([r["harv_fwd"][str(k)] for r in deep]) for k in HORIZONS},
                           "deep_zvol_20": stats([r["zvol_fwd"]["20"] for r in deep]),
                           "deep_by_era": {e: {"n": sum(1 for r in deep if r["era"] == e), "harv_1": stats([r["harv_fwd"]["1"] for r in deep if r["era"] == e]),
                                               "harv_20": stats([r["harv_fwd"]["20"] for r in deep if r["era"] == e])} for e in ("model", "vxz", "real")},
                           "deep_verdict": "the two real-era deep entries lost; the full record (29 entries, 23 modeled + 4 on -VXZ + 2 real) says the opposite, "
                                           "the deep-only counterfactual hurts on 2006+ and is noise on 2018+, and real-era ZVOL itself after deep closes is "
                                           "positive over 20 sessions: a watch item, 11-05 = observation 3, not a candidate",
                           "vxz_to_zvol_flips": flips, "flip_summary": {k: stats([r["harv_fwd"][str(k)] for r in flips]) for k in HORIZONS},
                           "flip_zvol_20": stats([r["zvol_fwd"]["20"] for r in flips])}
    res["guard"] = {"in_live_tree": False, "note": "no HYG condition in any saved HARV version (add. 48); the only guard is RSI(UVXY,14) > 70 -> PULS, "
                    "which read 66.7 at the 11-05 close (not tripped). The add. 12 design (block ZVOL when HYG 1d < -1%) exists only in research/harv_sim.py; "
                    "HYG was -0.31% on 11-05, so even that guard would not have fired.",
                    "harv_guard_sim": summarize_guard_sim()}
    json.dump(res, open(OUT, "w"), separators=(",", ":"), default=float)
    report(res)
    print("wrote", OUT)


def summarize_guard_sim():
    p = os.path.join(HERE, "harv_guard_sim.json")
    if not os.path.exists(p):
        return None
    m = json.load(open(p))
    ks = sorted(m)
    cum = math.prod(1 + m[k] for k in ks) - 1
    worst = sorted(ks, key=lambda k: m[k])[:5]
    return {"what": "monthly returns of the add. 12 GUARD variant (block ZVOL when HYG 1d < -1%), offline reconstruction 2018-02..2023-04",
            "months": len(ks), "cumulative": cum, "worst_months": {k: m[k] for k in worst},
            "add12_numbers": "BASE 2018-01..2023-04 +19.1%/yr, Sharpe 1.62, max DD 20.9% (a slow bleed, Feb-2018..Feb-2019); GUARD cuts the COVID crash "
                             "from -5.5% to -1.5%, costs 1.5pp CAGR, never fired 2023+"}


def pc(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def report(res):
    rc = res["regime_counts"]
    rp = res["inputs"]["vxz_reprice"]
    print(f"\n11-05: VIX {rc['vix_1105']:.2f}, VIX3M/VIX {pc(rc['depth_1105'])} ({rc['bucket_1105']}), SPY {pc(rc['spy_1105'])}, ZVOL {pc(rc['zvol_1105'])}, VXZ {pc(rc['vxz_1105'])}")
    print(f"real ZVOL era: {rc['real_zvol_era_days']} closes, {rc['real_zvol_era_backwardation_days']} in backwardation ({rc['real_zvol_era_episodes']} episodes) incl. 11-05 = "
          f"{rc['real_zvol_era_backwardation_days_with_outcomes']} / {rc['real_zvol_era_episodes_with_outcomes']} with outcomes; deep {rc['real_zvol_era_deep_days']} / "
          f"{rc['real_zvol_era_deep_episodes']} incl. 11-05 = {rc['real_zvol_era_deep_days_with_outcomes']} / {rc['real_zvol_era_deep_episodes_with_outcomes']} with outcomes")
    print(f"VXZ RE-PRICED {rp['window']['returns_from']}..{rp['window']['to']} ({rp['window']['sessions']} sessions) on VIXM: Yahoo VXZ zero-volume sessions {rp['vxz_zero_volume_sessions']['n']} "
          f"({rp['vxz_zero_volume_sessions']['from']}..{rp['vxz_zero_volume_sessions']['to']} at {rp['vxz_zero_volume_sessions']['price']}); 2018 zero-return sessions "
          f"{rp['vxz_2018_zero_return_sessions']['n']} of {rp['vxz_2018_zero_return_sessions']['of']}; corr(VXZ, VIXM) 2018 {rp['corr_vxz_vixm_2018']:.3f}; fit 2019-02..2023-04 beta "
          f"{rp['fit_2019_02_to_2023_04']['beta_vxz_on_vixm']:.3f} corr {rp['fit_2019_02_to_2023_04']['corr']:.3f} n {rp['fit_2019_02_to_2023_04']['n']}; engine days on VXZ/ZVOL in the window "
          f"{rp['engine']['sessions_on_vxz_or_zvol']} of {rp['engine']['engine_sessions_in_window']}, window compounded as printed {pc(rp['engine']['window_compounded_as_printed'])} -> re-priced "
          f"{pc(rp['engine']['window_compounded_repriced'])}; 2018-02-05 HARV {pc(rp['check_2018_02_05']['as_printed'],2)} -> {pc(rp['check_2018_02_05']['repriced'],2)} "
          f"(ZVOL proxy {pc(rp['check_2018_02_05']['zvol_proxy_as_printed'],2)} -> {pc(rp['check_2018_02_05']['zvol_proxy_repriced'],2)}, hold {rp['check_2018_02_05']['hold']})")
    for era, E in res["conditional"].items():
        print(f"\n[{era}] {E['from']}..{E['to']}")
        for k in ("1", "5", "20"):
            h = E["horizons"][k]
            for g in ("all", "contango", "backwardation", "0..-3%", "-3..-8%", "< -8%"):
                z, v = h[g]["zvol"], h[g]["vxz"]
                if not z["n"]:
                    continue
                pl = h[g].get("placebo") or {}
                ep = h[g].get("episode_start") or {}
                print(f"  {k:>2}d {g:14} n {z['n']:5} ZVOL mean {pc(z['mean'],2)} med {pc(z['median'],2)} t {z['t'] if z['t'] is None else round(z['t'],2)} win {z['win']:.0%} | "
                      f"VXZ {pc(v['mean'],2)} | placebo pct {pl.get('pct')} band {pc(pl.get('p05'),2)}..{pc(pl.get('p95'),2)}"
                      + (f" | episodes {h[g].get('episodes')} start-mean {pc(ep.get('mean'),2)} t {None if ep.get('t') is None else round(ep['t'],2)}" if ep else ""))
                bp, lo_ = h[g].get("block_placebo"), h[g].get("loo_episodes")
                if bp or lo_:
                    print("      " + (f"block placebo pct {bp['pct']:.3f} band {pc(bp['p05'],2)}..{pc(bp['p95'],2)} ({bp['runs']} runs)" if bp else "block placebo n/a")
                          + (f" | LOO-episode {pc(lo_['min'],2)}..{pc(lo_['max'],2)}; min without {lo_['min_without']['start']} (len {lo_['min_without']['len']}, "
                             f"share {lo_['min_without']['share_of_sum']:+.2f}, t {None if lo_['min_without']['t_without'] is None else round(lo_['min_without']['t_without'],2)}); "
                             "largest shares " + ", ".join(f"{x['start']} len {x['len']} {x['share_of_sum']:+.2f}" for x in lo_['largest_shares']) if lo_ else ""))
    print("\nENGINE ENTRIES (ZVOL weight up at the decision close; 11-05 pending, excluded)")
    for w, W in res["entries"]["summary"].items():
        print(f" [{w}] entries {W['n']} (pending {W['pending']})")
        for g, r in W["groups"].items():
            if r["n"]:
                print(f"   {g:14} n {r['n']:4} (fresh {r['fresh']}) w {r['mean_zvol_to']:.2f} VIX {r['mean_vix']:.1f} hold {r['hold_len_median']} ({r['hold_len_mean']:.1f}) | ZVOL 1/5/20 {pc(r['zvol_1']['mean'],2)} {pc(r['zvol_5']['mean'],2)} {pc(r['zvol_20']['mean'],2)} "
                      f"| HARV 1/5/20 {pc(r['harv_1']['mean'],2)} {pc(r['harv_5']['mean'],2)} {pc(r['harv_20']['mean'],2)} t20 {None if r['harv_20']['t'] is None else round(r['harv_20']['t'],2)} win20 {round(r['harv_20'].get('win'),2)}")
    print("\nZVOL TRADES (fresh entry -> weight back to 0), engine P&L over the episode")
    for w, W in res["trades"]["summary"].items():
        print(f" [{w}] trades {W['n']} (open {W['open']})")
        for g, r in W["groups"].items():
            if r["n"]:
                print(f"   {g:14} n {r['n']:4} sessions med {r['sessions_median']} mean {r['sessions_mean']:.1f} | P&L mean {pc(r['pnl']['mean'],2)} med {pc(r['pnl']['median'],2)} t {None if r['pnl']['t'] is None else round(r['pnl']['t'],2)} "
                      f"win {r['pnl']['win']:.0%} sum {r['sum_pnl_pp']:+.1f}pp | ZVOL-leg contrib mean {pc(r['zvol_contrib']['mean'],2)} | worst {r['worst']} {pc(r['worst_pnl'])} | best {r['best']} {pc(r['best_pnl'])} LOO min {pc(r['loo_min'],2)}")
    print("\nPATH SPLIT by the regime at the decision close")
    for w, W in res["path_split"].items():
        b, c = W["regimes"].get("backwardation", {}), W["regimes"].get("contango", {})
        print(f" [{w}] {W['days']} days (synthetic regime {W['synthetic_regime_days']}): base x{W['base']['multiple']:.2f} CAGR {pc(W['base']['cagr'])} DD {W['base']['maxdd']:.1%}; "
              f"cf ZVOL->PULS when inverted x{W['cf_zvol_to_puls_when_inverted']['multiple']:.2f} CAGR {pc(W['cf_zvol_to_puls_when_inverted']['cagr'])} DD {W['cf_zvol_to_puls_when_inverted']['maxdd']:.1%}; "
              f"deep only x{W['cf_zvol_to_puls_when_deep']['multiple']:.2f} | ratio {W['ratio_base_over_cf']:.3f}, without the largest ZVOL-leg day "
              f"({W['largest_zvol_leg_days'][0]['date'] if W['largest_zvol_leg_days'] else None} {pc(W['largest_zvol_leg_days'][0]['leg'],2) if W['largest_zvol_leg_days'] else ''}) "
              f"{W['ratio_without_largest_leg_day'] if W['ratio_without_largest_leg_day'] is None else round(W['ratio_without_largest_leg_day'],3)}; worst "
              + ", ".join(f"{x['date']} {pc(x['leg'],2)}" for x in W['worst_zvol_leg_days']))
        for g, a in (("backwardation", b), ("contango", c)):
            if a:
                print(f"   {g:14} n {a['n']:5} mean {pc(a['mean_daily'],3)} compounded {pc(a['compounded'])} ZVOL held {a['zvol_share_of_days']:.0%} of days (avg w {a['mean_zvol_w']:.2f}) "
                      f"ZVOL-leg contrib {a['zvol_contrib']*100:+.1f}pp share of log ret {a.get('share_of_log_return')}")
        for g in ("0..-3%", "-3..-8%", "< -8%"):
            a = W["regimes"].get(g)
            if a:
                print(f"   {g:14} n {a['n']:5} mean {pc(a['mean_daily'],3)} compounded {pc(a['compounded'])} ZVOL held {a['zvol_share_of_days']:.0%} contrib {a['zvol_contrib']*100:+.1f}pp")
    print("\nFILTER EFFECT: inverted closes the rule shorts vol into (ZVOL next session) vs the rest — ZVOL next 1/5/20")
    for w, F in res["filter_effect"].items():
        print(f" [{w}] inverted closes {F['inverted_closes']}: rule short {F['rule_short_vol']} -> "
              + " ".join(f"{pc(F['with'][k]['mean'],2)}" for k in ('1', '5', '20')) + f" (win1 {F['with']['1'].get('win')}); not {F['rule_not']} -> "
              + " ".join(f"{pc(F['without'][k]['mean'],2)}" for k in ('1', '5', '20')) + f" (win1 {F['without']['1'].get('win')})"
              + f" | deep: short n {F['deep_with']['1']['n']} " + " ".join(f"{pc(F['deep_with'][k].get('mean'),2)}" for k in ('1', '5', '20'))
              + f"; not n {F['deep_without']['1']['n']} " + " ".join(f"{pc(F['deep_without'][k].get('mean'),2)}" for k in ('1', '5', '20'))
              + f" | Welch t 1/5/20 " + " ".join("n/a" if F['welch_t'][k] is None else f"{F['welch_t'][k]:.2f}" for k in ('1', '5', '20'))
              + f"; short closes in {F['short_vol_runs']} runs, run-mean-of-means(+1) {pc(F['run_mean_of_means_1'],2)}, LOO-run min {pc(F['loo_run_min_1'],2)}")
    H = res["harvester_number"]
    print(f"\nHARVESTER NUMBER: live {pc(H['live_1105'],2)} value-based {pc(H['value_based_1105'],2)} model close-to-close {pc(H['model_close_to_close_1105'],2)} (VXZ {pc(H['vxz_ret_1105'],2)} x 0.3594); "
          f"engine real-era history n {H['history_engine_real_era']['n']} sd {pc(H['history_engine_real_era']['sd'],2)} p99 {pc(H['history_engine_real_era']['p99'],2)} max {pc(H['history_engine_real_era']['max'],2)} "
          f"days >= 11-05 {H['history_engine_real_era']['days_ge_1105']} pct {H['history_engine_real_era']['percentile_of_1105']:.3f}; live snapshots n {H['history_live_snapshots']['n']} rank {H['history_live_snapshots']['rank_of_1105']}")
    for w, s in H["as_a_signal"].items():
        print(f"  signal [{w}] corr(day, ZVOL fwd20) {s['corr_harv_day_vs_zvol_fwd20']:.3f}; day>=+1%: n {s['harv_day_ge_1pct']['n']} ZVOL fwd20 {pc(s['harv_day_ge_1pct']['zvol_fwd20'].get('mean'),2)}; "
              f"on VXZ: n {s['harv_day_ge_1pct_on_vxz']['n']} ZVOL fwd20 {pc(s['harv_day_ge_1pct_on_vxz']['zvol_fwd20'].get('mean'),2)}; uncond {pc(s['unconditional_zvol_fwd20']['mean'],2)}")
    L = res["live"]
    print(f"\nLIVE RECORD {L['from']}..{L['to']}: {L['sessions']} sessions, contango recorded in {L['snapshots_with_contango']} snapshots from {L['first_snapshot_with_contango']}; "
          f"backwardation closes {len(L['backwardation_closes'])}, alerts {len(L['backwardation_alerts'])}, sessions decided into ZVOL {L['zvol_sessions_live']}")
    for r in L["backwardation_closes"]:
        print("  close:", r["date"], pc(r["depth_close"]), r["decided_at_close"], "harv day", r["harv_day"], "zvol day", pc(r["zvol_day"],2), "fwd", {k: pc(v, 2) for k, v in r["zvol_fwd"].items()})
    for a in L["backwardation_alerts"]:
        print("  alert:", a["session"], a["et_time"], a["vix_contango"], a["holdings"], a["lpc"])
    print("  shallowest contango closes:", [(x["date"], pc(x["depth"])) for x in L["shallowest_contango_closes"]])
    M = L["model_vs_live"]
    print(f"  MODEL vs LIVE: {M['off_by_more_than_2pp']} of {M['ledger_sessions']} ledger sessions have live weights > 2pp from the engine's: "
          + "; ".join(f"{r['date']} {r['status']} live ZVOL {r['live'].get('ZVOL', 0):.2f} vs engine {r['engine'].get('ZVOL', 0):.2f}" for r in M["rows"]))
    C = res["context_1105"]
    print(f"\n11-05 IN CONTEXT: {C['n_backwardation_entries_before']} prior backwardation entries since 2006-07; depth pct {C['depth_percentile_among_bw_entries']:.2f} VIX pct {C['vix_percentile_among_bw_entries']:.2f} weight pct {C['weight_percentile_among_bw_entries']:.2f}")
    print(f"  deep (< -8%) entries n {len(C['deep_entries'])}: HARV fwd20 {pc(C['deep_summary'][20].get('mean'))} win {C['deep_summary'][20].get('win')} ZVOL fwd20 {pc(C['deep_zvol_20'].get('mean'))}; by era "
          + "; ".join(f"{e} n {v['n']} HARV +1 {pc(v['harv_1'].get('mean'))} +20 {pc(v['harv_20'].get('mean'))} win20 {v['harv_20'].get('win')}" for e, v in C["deep_by_era"].items()))
    for r in C["deep_entries"]:
        print(f"    {r['date']} depth {pc(r['depth'])} VIX {r['vix']:.1f} SPY {pc(r['spy_day'])} w {r['zvol_from']:.2f}->{r['zvol_to']:.2f} ZVOL 1/5/20 {pc(r['zvol_fwd']['1'])} {pc(r['zvol_fwd']['5'])} {pc(r['zvol_fwd']['20'])} HARV {pc(r['harv_fwd']['1'])} {pc(r['harv_fwd']['5'])} {pc(r['harv_fwd']['20'])} [{r['era']}]")
    print(f"  VXZ->ZVOL flips (held VXZ, day >= +1%, entered ZVOL) n {len(C['vxz_to_zvol_flips'])}: HARV fwd20 {pc(C['flip_summary'][20].get('mean'))} win {C['flip_summary'][20].get('win')} ZVOL fwd20 {pc(C['flip_zvol_20'].get('mean'))}")
    for r in C["vxz_to_zvol_flips"]:
        print(f"    {r['date']} depth {pc(r['depth'])} VIX {r['vix']:.1f} day {pc(r['harv_day'],2)} w ->{r['zvol_to']:.2f} ZVOL 20 {pc(r['zvol_fwd']['20'])} HARV 20 {pc(r['harv_fwd']['20'])} [{r['era']}]")


if __name__ == "__main__":
    main()
