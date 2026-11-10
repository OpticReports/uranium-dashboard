"""Cost-of-monitoring simulation: what does the edge-monitor STATE MACHINE
(not the detectors in isolation) do to returns?

Question the blueprint never asked: the false-alarm budget prices alarms in
ANNOYANCE (alerts/yr) but never in RETURN DRAG (time spent at half size on a
healthy strategy) or in SAVINGS (loss avoided when the edge dies). This sim
prices the whole policy.

Setup (a priori):
- Truth process: daily Gaussian, vol 15% ann. Healthy: SR 1.2. Decay
  scenario: SR 1.2 until day 400, then 0 forever.
- Baseline registered from a SEPARATE 1500d healthy draw (realistic
  baseline estimation error included).
- Monitor (as blueprint L1): downward CUSUM (k = half dead-edge shift,
  h calibrated to ARL 500 on the baseline draw) + max-DD/underwater
  percentile vs a length-matched MC grid from the baseline draw.
- State machine: YELLOW (size 0.5) on CUSUM alarm or DD>=p95;
  YELLOW->GREEN after 20 consecutive clean days (CUSUM stat < h/2 and
  DD < p95); RED (size 0, terminal) on DD>=p99 or both detectors alarmed
  within 30 days of each other. CUSUM resets on entering YELLOW.
- Horizon 1260d (5y), 400 paths per scenario. Metrics: terminal-wealth
  ratio monitored/unmonitored, CAGR drag (null), CAGR saved (decay),
  false-RED rate, share of days in each state.
"""
import math

import numpy as np

import sys

import sys; sys.path.insert(0, "/home/user/uranium-dashboard/barbell-lab/src")
from barbell.edge import cusum  # noqa: E402

VOL = 0.15 / math.sqrt(252)
MU = 1.2 * VOL / math.sqrt(252) * math.sqrt(252) / 252 * 252  # = 1.2*vol_d
MU = 1.2 * VOL          # daily mean for SR_ann 1.2 (SR_d = 1.2/sqrt252)
MU = 1.2 * 0.15 / 252.0
H_DAYS, N_PATHS, DECAY_DAY = 1260, 400, 400

rng0 = np.random.default_rng(2026)
baseline = rng0.normal(MU, VOL, 1500)
b_mu, b_sd = baseline.mean(), baseline.std(ddof=1)
shift = (1.2 / math.sqrt(252.0))
cal = cusum.calibrate_h(baseline, target_arl=500.0, k=shift / 2,
                        n_sims=600, seed=5)
K, H = cal["k"], cal["h"]

# length-matched DD grids from the baseline draw (every 21d, interpolated)
GRID_L = np.arange(21, H_DAYS + 21, 21)
N_MC = 1500
rngg = np.random.default_rng(7)
block = 20
nblk = int(np.ceil(H_DAYS / block))
starts = rngg.integers(0, len(baseline), size=(N_MC, nblk))
idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % len(baseline)
       ).reshape(N_MC, -1)[:, :H_DAYS]
R_MC = baseline[idx]
eq = np.cumprod(1 + R_MC, axis=1)
peak = np.maximum.accumulate(eq, axis=1)
DD_MC = eq / peak - 1.0
P95 = {L: np.percentile(DD_MC[:, :L].min(axis=1), 5) for L in GRID_L}
P99 = {L: np.percentile(DD_MC[:, :L].min(axis=1), 1) for L in GRID_L}


def thr(day, q):
    L = GRID_L[min(np.searchsorted(GRID_L, max(day, 21)), len(GRID_L) - 1)]
    return (P95 if q == 95 else P99)[L]


def run_path(r):
    """Returns (wealth_monitored, wealth_raw, days_yellow, red_day)."""
    w_m = w_r = 1.0
    eqty = peak = 1.0
    s = 0.0
    state, clean, red_day = "GREEN", 0, None
    last_cusum_alarm = last_dd_alarm = -10_000
    size = 1.0
    for t in range(len(r)):
        w_r *= 1 + r[t]
        w_m *= 1 + size * r[t]
        eqty *= 1 + r[t]                    # DD measured on the STRATEGY
        peak = max(peak, eqty)
        dd = eqty / peak - 1.0
        z = (r[t] - b_mu) / b_sd
        s = max(0.0, s + (-z) - K)
        cusum_alarm = s > H
        dd95 = dd <= thr(t + 1, 95)
        dd99 = dd <= thr(t + 1, 99)
        if cusum_alarm:
            last_cusum_alarm = t
        if dd95:
            last_dd_alarm = t
        if state != "RED":
            if dd99 or (abs(last_cusum_alarm - last_dd_alarm) <= 30
                        and last_cusum_alarm > -10_000 and last_dd_alarm > -10_000
                        and max(last_cusum_alarm, last_dd_alarm) == t):
                state, size, red_day = "RED", 0.0, t
            elif state == "GREEN" and (cusum_alarm or dd95):
                state, size, clean = "YELLOW", 0.5, 0
                s = 0.0                      # CUSUM resets on state change
            elif state == "YELLOW":
                if (s < H / 2) and not dd95:
                    clean += 1
                    if clean >= 20:
                        state, size = "GREEN", 1.0
                else:
                    clean = 0
    return w_m, w_r, red_day


def scenario(mu_after, seed):
    """mu_after: post-decay daily mean (None = healthy throughout).
    Metric = GEOMETRIC (log-wealth) CAGR delta: the Kelly-relevant number —
    arithmetic mean-of-ratios hides the variance benefit of de-sizing a
    zero-edge asset."""
    rng = np.random.default_rng(seed)
    lw_m, lw_r, reds, mdd_m, mdd_r = [], [], 0, [], []
    for _ in range(N_PATHS):
        mu_path = np.full(H_DAYS, MU)
        if mu_after is not None:
            mu_path[DECAY_DAY:] = mu_after
        r = rng.normal(mu_path, VOL)
        w_m, w_r, red_day = run_path(r)
        lw_m.append(math.log(w_m)); lw_r.append(math.log(w_r))
        reds += red_day is not None
    yrs = H_DAYS / 252.0
    g_m = math.exp(np.mean(lw_m) / yrs) - 1
    g_r = math.exp(np.mean(lw_r) / yrs) - 1
    return {"geo_cagr_monitored": g_m, "geo_cagr_raw": g_r,
            "geo_delta_pp": (g_m - g_r) * 100, "red_rate": reds / N_PATHS}


print(f"CUSUM cal: k={K:.3f} h={H:.2f} achieved ARL {cal['achieved_arl']}")
null = scenario(None, 42)
dec0 = scenario(0.0, 99)
decn = scenario(-0.4 * 0.15 / 252.0, 77)     # dies to SR -0.4 (edge + costs)
for nm, sc in (("NULL healthy 5y", null), ("DECAY -> SR 0 @d400", dec0),
               ("DECAY -> SR -0.4 @d400", decn)):
    print(f"{nm:24s} geo CAGR {sc['geo_cagr_monitored']:+.2%} monitored vs "
          f"{sc['geo_cagr_raw']:+.2%} raw -> delta {sc['geo_delta_pp']:+.2f}pp/yr, "
          f"RED {sc['red_rate']:.1%}")
d = null["geo_delta_pp"]
for nm, sc in (("SR0", dec0), ("SR-0.4", decn)):
    sv = sc["geo_delta_pp"]
    if sv > 0 > d:
        print(f"breakeven P(decay within 5y) vs {nm}: {-d/(sv-d):.1%}")
