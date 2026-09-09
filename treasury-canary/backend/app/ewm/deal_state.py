"""DEAL_STATE — boom/stall bands for the deal market, the DMHI's companion.

WHAT THIS IS FOR. The DMHI answers "how healthy is the deal market" with a
0..1 scalar. It does not answer "is it climbing or rolling over", which is
the question a sale-timing decision actually turns on. This is the
deal-market analogue of financing_state(): four states, dual-threshold
hysteresis, speed primary and level confirming.

Designed and adversarially audited 2026-09-09 across four independent
approaches (house-idiom, business-cycle turning-point dating, trend-relative,
and merger-wave statistics), each reimplemented from spec by three
independent auditors. The trend-relative design was the only one all three of
its auditors reproduced exactly and none could break; the others lost on
reproduction (an off-by-one that did not produce its own published table;
an underspecified imputation that gave a different tape on reimplementation;
non-deterministic output from a per-process-salted hash).

=== THE PROBLEM THIS SOLVES, AND WHY THE OBVIOUS DESIGN FAILS ===

A percentile-on-level state machine LATCHES. The US listed-company count has
roughly halved since 1997, so merger-proxy counts drift down for reasons that
have nothing to do with deal-market health; a level percentile drifts toward
"low" forever and a stall marker built on it never releases. The first
prototype did exactly this: 12 consecutive quarters of false STALL across
2012Q1-2015Q1.

The fix is not a threshold. Every coordinate here is measured against the
series' OWN one-sided trailing trend, so adding any log-linear trend to the
data is absorbed exactly by the OLS fit and leaves the coordinates unchanged.
That is an algebraic identity, not a tuning outcome. Result: ZERO down-state
quarters in the declared not-a-stall window 2012-2019 (0 of 32).

Seasonality is the other trap. Raw quarterly counts run Q1 90.3 / Q3 110.2 -
Q1 is 18% below Q3 - so ranking a Q1 against Q3s manufactures stalls. The
measure is a trailing-4-quarter mean of deseasonalised log counts, which
leaves a 2.9% residual.

=== READ THIS BEFORE ACTING ON BOOM ===

BOOM OCCUPANCY SITS AT ITS OWN NOISE FLOOR. Measured 10.9% on real data
against 9.5-13.4% on a null series with the same volatility and measured
AR(1) persistence (rho = 0.86) and no cycle in it at all. Precision 0.45,
recall 0.42, and 6 of 11 BOOM quarters are false. The detector fires no more
often on the real market than on noise.

BOOM IS THEREFORE ADVISORY ONLY and is deliberately NOT wired into the Window
Score. STALL is the load-bearing state: 15.8% occupancy against a 7.9-9.5%
noise floor - elevated roughly 2x, which is real but weaker evidence than a
naive null (no persistence) would suggest.

THE WORST RESIDUAL DEFECT, stated plainly because it is the one that could
cost money: the machine held BOOM through 2022Q1-Q2 while the raw count had
already fallen 36% from its 2021Q3 peak, then printed STALL two quarters
later. For a sell-side timer a false "window open" immediately preceding
closure is the worst error available. It is the structural lag of a
trailing-year measure, not a rule bug, and no threshold change removes it
without breaking the stall calls.
"""

import json
import math
import os
import statistics as st

DM = {"K_SHORT": 20, "K_LONG": 40, "MIN_FIT_S": 14, "MIN_FIT_L": 24,
      "MIN_IN_WIN": 3, "SIG_FLOOR": 0.10,
      # Z_NOTABLE / Z_EXTREME are the one-sided 15.9% and 5% normal
      # quantiles - the yellow/red two-tier convention of scoring/thresholds.
      # Z_EXIT is half a sigma of hysteresis giveback, the dual-threshold
      # pattern FIN uses (400/375, 500/425). Z_UNMISTAKABLE is exactly
      # 2 x Z_EXTREME, the 0.05% tail, which declares without confirmation.
      "Z_NOTABLE": 1.0, "Z_EXTREME": 1.645, "Z_EXIT": 0.5,
      "Z_UNMISTAKABLE": 3.29,
      # Escalation only. 16 of 118 quarters are absent and one print moves
      # the trailing-year mean ~8%, so a state that alters a sale decision
      # must not be declarable on a single print. EXITS are never gated -
      # leaving a stall should be prompt.
      "CONFIRM": 2,
      "HSR_Q": 0.20, "HSR_MIN": 5}

RANK = {"STALL": -2, "COOLING": -1, "NORMAL": 0, "BOOM": 1}


def _deal_activity():
    fp = os.path.join(os.path.dirname(__file__), "data", "deal_activity.json")
    try:
        with open(fp, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _seasonal(qs, x, i):
    """Causal AND trend-free seasonal factors.

    Uses only years STRICTLY BEFORE year(t), and subtracts each year's OWN
    mean before taking the cross-year median per calendar quarter - so a
    secularly declining series cannot bias the factors. Requires >=5 years
    per quarter, else that quarter's factor is 0.
    """
    by_year = {}
    for j, (y, q) in enumerate(qs):
        if y >= qs[i][0]:
            break
        if x[j] is not None:
            by_year.setdefault(y, {})[q] = math.log(x[j])
    dev = {1: [], 2: [], 3: [], 4: []}
    for _y, dd in by_year.items():
        if len(dd) < 3:
            continue
        m = sum(dd.values()) / len(dd)
        for q, v in dd.items():
            dev[q].append(v - m)
    f = {q: (st.median(dev[q]) if len(dev[q]) >= DM["HSR_MIN"] else 0.0)
         for q in (1, 2, 3, 4)}
    mu = sum(f.values()) / 4.0
    return {q: f[q] - mu for q in f}


def _trailing_a(qs, x):
    """A_t = trailing-4q mean of deseasonalised log counts.

    Averaging the AVAILABLE quarters is exactly imputing a missing one at the
    window's own mean, so no imputation model is needed - which matters,
    because an underspecified imputation is what made a competing design
    irreproducible.
    """
    out = [None] * len(qs)
    for i in range(len(qs)):
        f = _seasonal(qs, x, i)
        v = [math.log(x[j]) - f[qs[j][1]]
             for j in range(max(0, i - 3), i + 1) if x[j] is not None]
        if len(v) >= DM["MIN_IN_WIN"]:
            out[i] = sum(v) / len(v)
    return out


def _fit(a, i, k, minfit):
    """One-sided OLS over [i-k+1, i]. Data <= t only, drift extrapolated to t.
    Scale is a MAD, floored: without the floor a self-standardising sigma
    collapses in calm windows and manufactures stalls out of 2% wiggles."""
    pts = [(j, a[j]) for j in range(max(0, i - k + 1), i + 1)
           if a[j] is not None]
    if a[i] is None or len(pts) < minfit:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    b = sxy / sxx if sxx else 0.0
    intercept = my - b * mx
    res = [yy - (intercept + b * jj) for jj, yy in pts]
    med = st.median(res)
    sig = max(DM["SIG_FLOOR"],
              1.4826 * st.median([abs(r - med) for r in res]))
    return (a[i] - (intercept + b * i), b, sig)


def _coords(a, i):
    """The two coordinates, both unitless, both ZERO for a steady decline of
    any rate - which is the whole point.

      zg  LEVEL  = deviation from the trailing 5y trend, in sigma
      zs  SPEED  = drift-adjusted annualised change, in sigma
      zL  GATE   = deviation from the trailing 10y trend (upside gate only)
    """
    fs = _fit(a, i, DM["K_SHORT"], DM["MIN_FIT_S"])
    fl = _fit(a, i, DM["K_LONG"], DM["MIN_FIT_L"])
    if fs is None:
        return None
    dev, b, sig = fs
    j = next((c for c in (i - 4, i - 3, i - 5)
              if c >= 0 and a[c] is not None), None)
    if j is None:
        return None
    lag = i - j
    return {"zg": dev / sig,
            "zs": ((a[i] - a[j] - b * lag) * (4.0 / lag))
                  / (sig * math.sqrt(2.0)),
            "zL": (fl[0] / fl[2]) if fl else None,
            "drift_yr": b * 4.0, "sigma": sig}


def step(prev, pend, zs, zg, z_long):
    """PURE state transition. Speed primary, level confirming.

    Mirrors financing_state(): STALL is its SHUT, COOLING its TIGHT. The
    difference is that level may never fire alone - on a series with a
    secular trend a level-only trigger latches forever.
    """
    n, e, x, u, c = (DM["Z_NOTABLE"], DM["Z_EXTREME"], DM["Z_EXIT"],
                     DM["Z_UNMISTAKABLE"], DM["CONFIRM"])
    s = prev if prev in RANK else "NORMAL"
    stall_in = (zs <= -e) or (zs <= -n and zg <= -n)
    boom_in = (zs >= n) and (zg >= 0.0) and (z_long is not None and z_long >= 0.0)
    cool_in = (zs <= -n) or (zg <= -e and zs <= 0.0)
    want = ("STALL" if stall_in else "BOOM" if boom_in
            else "COOLING" if cool_in else None)

    # Hysteretic exits first; leaving a state is never confirmation-gated.
    if s == "STALL" and not (zs <= -n or zg <= -e):
        s = "COOLING"
    elif s == "BOOM" and (zs < x or zg < 0.0):
        s = "NORMAL"
    elif s == "COOLING" and (zs > -x and zg > -e):
        s = "NORMAL"

    # A BOOM whose downside entry condition is already met has REVERSED, not
    # lapsed. Routing it through NORMAL prints "no signal" in the quarter the
    # reversal is most extreme - it did exactly that at 2022Q3, zs = -1.98.
    if prev == "BOOM" and s == "NORMAL" and (cool_in or stall_in):
        s = "COOLING"

    def _sgn(r):
        return (r > 0) - (r < 0)

    same_side = _sgn(RANK[s]) == 0 or _sgn(RANK[want or s]) == _sgn(RANK[s])
    if want and abs(RANK[want]) > abs(RANK[s]) and same_side:
        pend = {"state": want,
                "n": (pend["n"] + 1 if pend and pend["state"] == want else 1)}
        if abs(zs) >= u or pend["n"] >= c:
            s, pend = want, None
    else:
        pend = None
    return s, pend


def _grid(da, today_q=None):
    """Calendar grid, not a value list - so t-4 always means one year even
    across the 16 absent quarters. The CURRENT, INCOMPLETE quarter is
    dropped: at 66% completion it already satisfies every BOOM entry
    condition and tips the state when it lands as the confirming quarter."""
    eg = (da.get("edgar_merger_proxies") or {}).get("by_quarter") or {}
    if not eg:
        return [], []
    last = max(eg)
    qs, xs = [], []
    for y in range(1997, int(last[:4]) + 1):
        for q in (1, 2, 3, 4):
            key = f"{y}Q{q}"
            if key > last:
                break
            qs.append((y, q))
            xs.append(float(eg[key]) if key in eg else None)
    return qs, xs


def hsr_ledger(hsr):
    """HSR arrears corroboration: expanding bottom-quintile test on the
    fiscal-year log change of the $150-300M tier.

    The single most discriminating statistic in the whole design record - 4
    corroborations in 32 evaluable years (12%), landing on exactly FY2001,
    FY2009, FY2020, FY2023: the ground-truth stall list, zero extras, and
    declining every year across FY2012-2019.

    IN ARREARS ONLY. FY y is readable from (y+1)Q3. A live HSR confirm/deny
    gate was built and REJECTED during design: across 33 down-state quarters
    the newest published HSR contradicted 20 of them, and at GFC entry the
    newest figures available were FY2006 +5% and FY2007 +13%, so a live gate
    would have damped the true GFC signal for five quarters.
    """
    h = {int(k): v for k, v in hsr.items()}
    yrs = sorted(h)
    ch = {y: math.log(h[y] / h[y - 1])
          for i, y in enumerate(yrs) if i > 0 and yrs[i - 1] == y - 1}
    out = {}
    for y in sorted(ch):
        hist = sorted(v for yy, v in ch.items() if yy <= y)
        if len(hist) < DM["HSR_MIN"]:
            continue
        k = (len(hist) - 1) * DM["HSR_Q"]
        lo = int(k)
        p20 = hist[lo] + (hist[min(lo + 1, len(hist) - 1)] - hist[lo]) * (k - lo)
        out[y] = {"yoy_log": ch[y], "p20": p20,
                  "corroborates": ch[y] <= p20, "published": f"{y + 1}Q3"}
    return out


def hsr_asof(ledger, qtup):
    """Newest fiscal year PUBLISHED as of this quarter. FY y is readable
    from (y+1)Q3 - a ~10 month lag.

    The publication gate is the whole point and dropping it is a live
    look-ahead leak: without it, standing at 2026Q2 the ledger hands back
    FY2025, which does not publish until 2026Q3. Every corroboration in the
    backtest would then be reading a report that did not exist yet.
    """
    best = None
    for y in ledger:
        if (y + 1, 3) <= qtup and (best is None or y > best):
            best = y
    return best


def fast_chip(qs, x, i):
    """Single-quarter deviation vs its own trailing-5y band. DISPLAY ONLY.

    The trailing-year smoothing that kills the seasonal also makes the state
    machine structurally blind to single-quarter air pockets - it cannot see
    2025Q2, which the operator's own work found at the 3.9th percentile. This
    chip does (z = -1.95).

    It is NOT wired into the state and must never be: an uncorrected
    pointwise 5% test fires on ~5 of every 100 quarters BY CONSTRUCTION, and
    this one fires 6 times in 101 (5.9%) - two of them (2012Q1, 2019Q2)
    inside declared not-a-stall windows. Print its base rate beside it.
    """
    if x[i] is None:
        return None
    f = _seasonal(qs, x, i)
    cur = math.log(x[i]) - f[qs[i][1]]
    hist = [math.log(x[j]) - f[qs[j][1]]
            for j in range(max(0, i - 20), i) if x[j] is not None]
    if len(hist) < 12:
        return None
    med = st.median(hist)
    sd = max(DM["SIG_FLOOR"],
             1.4826 * st.median([abs(v - med) for v in hist]))
    z = (cur - med) / sd
    return {"z": round(z, 2), "air_pocket": z <= -DM["Z_EXTREME"],
            "soft": z <= -DM["Z_NOTABLE"]}


def deal_state(prev="NORMAL", pend=None):
    """The live reading. Same shape as financing_state(); None on failure,
    in which case the caller HOLDS the persisted prior state."""
    da = _deal_activity()
    if not da:
        return None
    qs, x = _grid(da)
    if not qs:
        return None
    a = _trailing_a(qs, x)
    state, p = prev if prev in RANK else "NORMAL", pend
    coords = None
    for i in range(len(qs)):
        c = _coords(a, i)
        if c is None:
            continue
        state, p = step(state, p, c["zs"], c["zg"], c["zL"])
        coords = c
        last_i = i
    if coords is None:
        return None
    led = hsr_ledger((da.get("hsr_tier_150_300m") or {}).get("by_fiscal_year") or {})
    latest_fy = hsr_asof(led, qs[last_i])
    return {
        "state": state,
        "pending": p,
        "quarter": f"{qs[last_i][0]}Q{qs[last_i][1]}",
        "zs": round(coords["zs"], 2), "zg": round(coords["zg"], 2),
        "zL": round(coords["zL"], 2) if coords["zL"] is not None else None,
        "drift_yr_pct": round(100 * (math.exp(coords["drift_yr"]) - 1), 1),
        "fast_chip": fast_chip(qs, x, last_i),
        "hsr_corroborates": (led.get(latest_fy) or {}).get("corroborates"),
        "hsr_fy": latest_fy,
        "advisory_only": state == "BOOM",
        "source": "EDGAR merger proxies, trend-relative 4-state marker "
                  "(HSR corroborates in arrears)",
        "note": "BOOM is ADVISORY - its 10.9% occupancy sits at its own "
                "9.5-13.4% noise floor. STALL is the load-bearing state "
                "(15.8% vs a 7.9-9.5% floor).",
    }
