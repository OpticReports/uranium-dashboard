# Can pin-board reds / convergence improve recession prediction? (v2)

**Study date:** 2026-07-16 (v2, same day — see "QA corrections" below) ·
**Script:** `pin_rule_hindcast.py` (reproducible — live `/pins/history` hindcast,
daily ^GSPC downsampled to true monthly, daily FRED 3m10y via the canary's
public `/curve` endpoint) · **Design:** seven pre-specified rules, zero fitted
parameters; channel sets and thresholds come from the board's documented design.

## QA corrections (v1 → v2)

A hostile QA pass found v1's ground truth defective; v2 fixes all of it:

1. **v1's "monthly" SPX bars were silently QUARTERLY** (Yahoo degrades
   `interval=1mo&range=max`). Event dates were quarter-open stamps — off by up
   to ~7 months — and 1998/2011/2015 were missing entirely. v2 downsamples
   daily bars to true monthly; the event list grew from 8 to 12 and every
   date/depth changed (GFC peak 2007-10 not "2007-03"; COVID depth −32% not −30%).
2. **v1 measured a different curve rule than the one deployed** (Yahoo
   ^TNX−^IRX over 7 monthly closes vs the gauge's daily FRED 3m10y over 183
   days). v2 measures the deployed rule exactly, and the FRED series extends
   the window back to 1981.
3. **Cluster accounting added**: signal months are serially correlated (one
   run lasted 32 straight months), so precision is reported alongside an
   episode-level hit rate — the honest effective sample size (~11 clusters).
4. UTC date handling (v1 shifted month labels on non-UTC runners).

## Results — P(event within 12m | signal-month), plus cluster hit rates

### vs NBER recession onsets (6 onsets; 4 inside each rule's window)

| rule | window | signal months | clusters hit | precision | base |
|---|---|---|---|---|---|
| windows_open ≥ 2 (raw convergence) | 1976– | 205 | 2/24 | **6%** | 12% |
| fast-channel window open | 1976– | 230 | 4/31 | 10% | 12% |
| fast-channel red | 1976– | 186 | 3/38 | 10% | 12% |
| oil/policy window open | 1987– | 216 | 4/13 | 15% | 10% |
| **curve flat/inverted (≤0.25pp, 183d)** | 1981– | 154 | 4/9 | **31%** | 9% |
| fast-red AND curve | 1981– | 77 | 3/11 | 25% | 9% |
| oil/policy window AND curve | 1987– | 82 | 4/6 | 38% | 10% |

### vs ≥15% SPX drawdown starts (12 events; 9–10 inside windows)

| rule | window | signal months | clusters hit | precision | base |
|---|---|---|---|---|---|
| windows_open ≥ 2 | 1976– | 205 | 8/24 | 25% | 20% |
| fast-channel window open | 1976– | 230 | 9/31 | 25% | 20% |
| fast-channel red | 1976– | 186 | 9/38 | 26% | 20% |
| oil/policy window open | 1987– | 216 | 8/13 | 27% | 22% |
| curve flat/inverted | 1981– | 154 | 6/9 | 37% | 20% |
| **fast-red AND curve** | 1981– | 77 | 5/11 | **44%** | 20% |
| **oil/policy window AND curve** | 1987– | 82 | 5/6 | **46%** | 22% |

**fast_red+curve per-event detail** (lead = months before the true peak):
caught 1998 LTCM (4m early), 2007 (up to 12m), 2019 (11m), 2025 (12m);
missed 2018 (curve stayed steep) and 2021 (policy-driven). Pre-2002 "misses"
(1970/72/80/87/90/2000) are largely data gaps — credit/plumbing/basis sources
begin ~2002-2006; only the carry channel existed earlier.

## Conclusions (the measured division of labor)

1. **Recessions belong to the yield curve** (31% precision, 4/4 onsets) and
   nothing built from pin reds *reliably* improved on it — `oil/policy+curve`
   prints 38% but on 82 months in 6 clusters, indistinguishable from the curve
   alone. This reproduces the Berge–Jordà / NFCI horse-race consensus cited in
   `pins.py`.
2. **Raw convergence counts score BELOW base rate on recessions** (6% vs 12%).
   Windows are open in ~2/3 of all months; the seductive chart is anti-signal
   for that question.
3. **Pin reds earn their keep on market accidents.** Fast-channel red on a
   flat/inverted curve → a ≥15% drawdown STARTED within 12m in 44% of signal
   months vs 20% base; 5 of 11 signal-clusters were followed by one, with
   4–12 month leads on the catches. **But**: `oil/policy window + curve`
   scores the same within noise (46%, 5/6 clusters) — the composite the gauge
   ships is *a* measured configuration, not *the* one; treat the pair as one
   family ("stress on an inverted curve").
4. **Therefore:** read the calibrated curve probit for recession odds; read
   this board as an accident radar sized by the mass map. Never blend them —
   with ~11 clusters and 6 onsets, any fitted blend is data-snooping.

## Honest limitations

~11 signal clusters (episode-level 95% CI ≈ ±30pp); serially-correlated
months; fast channels' sources begin 2002-2006 so early misses are partly
data gaps; drawdown threshold (15%) and curve cut (0.25pp) are conventional
but still choices; drawdown "start" is the monthly-close peak (the true daily
peak can be up to ~2 months later — e.g. COVID: monthly-close peak Dec-2019,
daily peak Feb-2020); channel coverage grows over time, so cross-era
comparisons are confounded. Re-run the script to refresh; all numbers are
descriptive context, never calibration.
