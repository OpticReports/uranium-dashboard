"""The harvester rule on a long daily panel (the exact approved tree: nine voters on Wilder RSI(SPY, 2..10),
weights 36/16/8/8/8/8/8/4/4; RSI < 25 -> ZVOL unless RSI(UVXY,14) > 70 -> PULS; RSI > 80 -> VXZ; else PULS).

Panel, by era (total returns, close to close):
  ZVOL  real from 2023-04-19; before: -1 x VIXM + 2 x T-bill - 2.27%/yr - a 1.44%/yr calibration (2011-01+; an inverse fund earns the
        bill on its collateral and pays 1.42%, the long fund it is built from already holds bill - 0.85%);
        before 2011: -1 x the futures-built mid-term index + T-bill - 1.42%/yr.
  VXZ   real from 2019-02-01 (Yahoo's VXZ is stale 2018-01-26..2019-01-31); VIXM 2011-01..2019-01;
        before: futures index + T-bill - 0.89%/yr.
  PULS  real from 2018-04-10; BIL before (2007-05-30+); 4.8%/yr flat before that.
  UVXY  real from 2011-10-04 (RSI only); before: 2 x the futures-built short-term index.
  SVXY* (-0.5x front month, for refinement R1): real SVXY from 2018-03-01 (it was -1x before);
        before: -0.5 x VIXY + 1.5 x T-bill - 1.375%/yr (2011+), futures short-term index before 2011.
Signals use adjusted closes through day d; the weights are held from d's close to d+1's close.
Usage: import sim; P = sim.panel(DATA); res = sim.run(P, variant)"""
import math
import lib

VOTERS = [(2, .36), (3, .16), (4, .08), (5, .08), (6, .08), (7, .08), (8, .08), (9, .04), (10, .04)]
START = "2006-07-03"
# Extra yearly drag so each formula matches the real fund over the years both exist (the formulas run
# ahead of the funds: ZVOL by 1.44%/yr over 2023-04..2026-11, SVXY by 1.79%/yr over 2018-03..2026-11).
ZVOL_CAL = 0.0144
SVXY_CAL = 0.0179


def panel(D):
    C = D + "/cache"
    fut = lib.vx_panel(C)
    mid = lib.vx_index(fut, 4, 7); short = lib.vx_index(fut, 1, 2)
    r = {t: lib.rets(lib.series(t, C, "adj")) for t in ("ZVOL", "VXZ", "VIXM", "VIXY", "PULS", "BIL", "UVXY", "SVXY", "SPY", "HYG")}
    spy = lib.series("SPY", C, "adj")
    days = [d for d in sorted(spy) if START <= d <= lib.END]
    P = {"days": days, "ZVOL": {}, "VXZ": {}, "PULS": {}, "SVXY": {}, "UVXYr": {}, "BIL": {}, "src": {}, "approx_days": 0}
    for d in days:
        bil = r["BIL"].get(d, 0.048 / 252 if d < "2007-05-31" else 0.0)
        P["BIL"][d] = bil
        m = mid.get(d); s = short.get(d)
        if m and m["approx"] and d < "2011-01-05":
            P["approx_days"] += 1
        # ZVOL
        if d in r["ZVOL"]:
            P["ZVOL"][d] = r["ZVOL"][d]; zs = "real"
        elif d in r["VIXM"]:
            P["ZVOL"][d] = -r["VIXM"][d] + 2 * bil - (0.0227 + ZVOL_CAL) / 252; zs = "-VIXM"
        else:
            P["ZVOL"][d] = (-m["ret"] if m else 0.0) + bil - (0.0142 + ZVOL_CAL) / 252; zs = "futures"
        # VXZ
        if d in r["VXZ"] and d >= "2019-02-04":
            P["VXZ"][d] = r["VXZ"][d]
        elif d in r["VIXM"]:
            P["VXZ"][d] = r["VIXM"][d]
        else:
            P["VXZ"][d] = (m["ret"] if m else 0.0) + bil - 0.0089 / 252
        P["PULS"][d] = r["PULS"][d] if d in r["PULS"] else bil
        P["UVXYr"][d] = r["UVXY"][d] if d in r["UVXY"] else 2.0 * (s["ret"] if s else 0.0)
        if d in r["SVXY"] and d >= "2018-03-01":
            P["SVXY"][d] = r["SVXY"][d]
        elif d in r["VIXY"]:
            P["SVXY"][d] = -0.5 * r["VIXY"][d] + 1.5 * bil - (0.01375 + SVXY_CAL) / 252
        else:
            P["SVXY"][d] = -0.5 * (s["ret"] if s else 0.0) + bil - (0.0095 + SVXY_CAL) / 252
        P["src"][d] = zs
    # signals
    closes = [spy[d] for d in sorted(spy) if d <= lib.END]; alld = [d for d in sorted(spy) if d <= lib.END]
    P["rsi"] = {}
    for n, _ in VOTERS:
        x = lib.rsi(closes, n)
        P["rsi"][n] = {alld[i]: x[i] for i in range(len(alld))}
    lvl, u = [1.0], 1.0
    for d in days:
        u *= max(1e-9, 1 + P["UVXYr"][d]); lvl.append(u)
    ux = lib.rsi(lvl, 14)
    P["uvxy_rsi"] = {days[i]: ux[i + 1] for i in range(len(days))}
    P["mid"] = mid; P["short"] = short; P["fut"] = fut
    return P


def weights(P, d, short_fund="ZVOL", long_leg=True, gate=None):
    """the rule's target weights at d's close. gate(d) -> False blocks the short-vol entry (-> PULS)."""
    w = {short_fund: 0.0, "VXZ": 0.0, "PULS": 0.0}
    hot = (P["uvxy_rsi"].get(d) or 0.0) > 70
    ok = gate(d) if gate else True
    for n, wt in VOTERS:
        x = P["rsi"][n].get(d)
        if x is None:
            w["PULS"] += wt
        elif x < 25:
            w["PULS" if (hot or not ok) else short_fund] += wt
        elif x > 80:
            w["VXZ" if long_leg else "PULS"] += wt
        else:
            w["PULS"] += wt
    return w


def run(P, short_fund="ZVOL", long_leg=True, gate=None, cost_bps=0.0, start=None, end=None):
    """{days, ret (net of cost), gross, w: [dict per day, held INTO that day]}"""
    days = [d for d in P["days"] if (start or "") <= d <= (end or "9999")]
    out = {"days": [], "ret": [], "gross": [], "w": [], "turn": []}
    prev = None
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        w = weights(P, d0, short_fund, long_leg, gate)
        g = sum(x * P[t][d1] for t, x in w.items())
        tn = sum(abs(w[t] - (prev or w)[t]) for t in w)
        out["days"].append(d1); out["gross"].append(g); out["ret"].append(g - cost_bps / 1e4 * tn)
        out["w"].append(w); out["turn"].append(tn); prev = w
    return out
