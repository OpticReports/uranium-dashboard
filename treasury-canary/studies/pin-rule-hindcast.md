# Can pin-board reds / convergence improve recession prediction?

**Study date:** 2026-07-16 · **Script:** `pin_rule_hindcast.py` (reproducible —
fetches the live `/pins/history` hindcast + Yahoo ^TNX/^IRX) · **Design:** seven
pre-specified rules, zero fitted parameters; every channel set and threshold is
taken from the board's documented design (FAST_HIGH_MASS, kill-rate notes,
standard flat-curve cut), not searched over.

## Results — P(event within 12m | signal-month), vs base rate

### vs NBER recession onsets (6 onsets 1980–2020)

| rule | window | signal months | precision | base | onsets caught |
|---|---|---|---|---|---|
| windows_open ≥ 2 (raw convergence) | 1976–2026 | 217 | **6%** | 12% | 2/6 |
| fast-channel window open | 1976–2026 | 242 | 10% | 12% | 3/6 |
| fast-channel red | 1976–2026 | 198 | 10% | 12% | 2/6 |
| oil/policy window open | 1987–2026 | 218 | 15% | 10% | 4/4 |
| **curve flat/inverted (≤0.25pp, 6m)** | 1985–2026 | 117 | **38%** | 10% | **4/4** |
| fast-red AND curve | 1985–2026 | 76 | 28% | 10% | 2/4 |
| oil/policy window AND curve | 1987–2026 | 74 | 36% | 10% | 4/4 |

### vs ≥15% SPX drawdown starts (8 events 1987–2024)

| rule | window | signal months | precision | base | events caught |
|---|---|---|---|---|---|
| windows_open ≥ 2 | 1976–2026 | 217 | 26% | 16% | 6/8 |
| fast-channel window open | 1976–2026 | 242 | 21% | 16% | 6/8 |
| fast-channel red | 1976–2026 | 198 | 23% | 16% | 6/8 |
| oil/policy window open | 1987–2026 | 218 | 25% | 19% | 7/8 |
| curve flat/inverted | 1985–2026 | 117 | 36% | 20% | 4/8 |
| **fast-red AND curve** | 1985–2026 | 76 | **41%** | 20% | 3/8* |

\* Of the 5 drawdowns inside the fast channels' data era (2002+), it caught 3 —
2007 (fired 12m early), 2019-09 (repo spasm → COVID, 6m early), 2024-09 (12m
early) — and missed 2018 (curve still steep) and 2021-22 (policy-driven, the
slow channels' domain). The 1987/1990/2000 "misses" are data gaps, not signal
failures: credit/plumbing/basis sources begin ~2002.

## Conclusions (the measured division of labor)

1. **Recessions belong to the yield curve.** 38% precision, 4/4 onsets caught,
   and *nothing built from pin reds improved it* — combining fast reds with the
   curve (28%) DILUTED the curve alone. This independently reproduces the
   Berge–Jordà / NFCI horse-race literature already cited in `pins.py`: financial
   conditions add nothing to onset prediction beyond the curve.
2. **Raw convergence counts score BELOW base rate on recessions** (6% vs 12%).
   The seductive chart is anti-signal for that question: windows are open in
   ~69% of all months, dominated by often-firing fast channels.
3. **Pin reds earn their keep on market accidents.** Fast-channel red on a
   flat/inverted curve → ≥15% drawdown within 12m in 41% of months vs a 20%
   base — double the odds, with 6–12 month leads on the catches. This is the
   transmission-note configuration, now measured.
4. **Therefore:** read the curve model (calibrated probit, the dashboard's
   22.6%/CI as of this writing) for recession odds; read this board as an
   accident radar sized by the mass map. Do not blend them into one number —
   with 6 onsets any fitted blend is data-snooping.

## Honest limitations

Six onsets; serially-correlated months; curve series only reaches 1985 via
Yahoo (4 onsets in-window); fast channels' sources begin ~2002-2006; drawdown
threshold (15%) and curve cut (0.25pp) are conventional but still choices.
Re-run the script to refresh; treat all numbers as descriptive context, never
calibration.
