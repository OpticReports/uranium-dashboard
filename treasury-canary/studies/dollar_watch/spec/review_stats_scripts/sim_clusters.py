"""SYNTHETIC ONLY: does single linkage at 126 US trading days chain into a >24-month cluster
(triggering the SPEC's blind switch to calendar years), and what K results under each unit?
Firing process: the SPEC's own stress windows (lines 99-100 + finder B's 2015-16), each active
currency fires once per window with prob pi_g (uniform date in the window), plus idiosyncratic
firings at rate lam per active currency-year; 120-trading-day cooling per currency.
Currency activity: FRED start (SPEC section 2.2) + 3.25y sigma warm-up, sample from 1973-03,
last firing date 2025-10 (minus the 250-day outcome window). No data file is read."""
import numpy as np

rng = np.random.default_rng(7)
STARTS = [1995.0, 1993.85, 1981.28, 1980.0, 1973.0, 1981.0, 1971.0, 1983.75, 1981.0, 1973.0,
          1971.0, 1971.0, 1971.0, 1971.0, 1971.0]
ACTIVE_FROM = [max(s, 1973.17) + 3.25 for s in STARTS]
END = 2025.8
WINDOWS = [(1980.0, 1983.0), (1984.4, 1985.25), (1992.7, 1993.0), (1994.9, 1995.5), (1997.5, 1998.8),
           (2000.7, 2001.8), (2008.6, 2009.25), (2011.6, 2012.0), (2013.35, 2013.75), (2014.8, 2015.25),
           (2015.6, 2016.1), (2018.3, 2018.85), (2020.1, 2020.35), (2022.2, 2022.85), (2024.5, 2025.3)]
TD = 1 / 252.0


def simulate(pi_g, lam):
    fires = []
    for c, a in enumerate(ACTIVE_FROM):
        f = []
        for (w0, w1) in WINDOWS:
            if w1 > a and rng.random() < pi_g:
                f.append(rng.uniform(max(w0, a), w1))
        span = END - a
        f += list(rng.uniform(a, END, rng.poisson(lam * span)))
        f = sorted(x for x in f if a <= x <= END)
        kept = []
        for x in f:
            if not kept or x - kept[-1] > 120 * TD:
                kept.append(x)
        fires += kept
    return np.sort(np.array(fires))


def single_linkage(t, gap):
    if len(t) == 0:
        return []
    cl = [[t[0]]]
    for x in t[1:]:
        if x - cl[-1][-1] <= gap:
            cl[-1].append(x)
        else:
            cl.append([x])
    return cl


print("pi_g  lam   firings(med)  K126(med)  P(max span>24m)  maxspan_yrs(med)  K_calyear(med)  K250(med)  share singletons@126")
for pi_g, lam in ((0.25, 0.03), (0.35, 0.05), (0.5, 0.08), (0.6, 0.15), (0.7, 0.25)):
    R = []
    for _ in range(2000):
        t = simulate(pi_g, lam)
        c126 = single_linkage(t, 126 * TD)
        spans = [c[-1] - c[0] for c in c126]
        c250 = single_linkage(t, 250 * TD)
        R.append((len(t), len(c126), max(spans) > 2.0, max(spans), len(set(np.floor(t).astype(int))), len(c250),
                  np.mean([len(c) == 1 for c in c126])))
    R = np.array(R, dtype=float)
    print(f"{pi_g:<6}{lam:<6}{np.median(R[:,0]):<14.0f}{np.median(R[:,1]):<11.0f}{R[:,2].mean():<17.2f}"
          f"{np.median(R[:,3]):<18.1f}{np.median(R[:,4]):<16.0f}{np.median(R[:,5]):<11.0f}{np.median(R[:,6]):.2f}")
