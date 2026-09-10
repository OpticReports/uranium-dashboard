# Can pin-board reds / convergence improve recession prediction? (v2)

> **RE-MEASURED 2026-09-10 (v3).** The v2 numbers below were frozen against an instrument
> that has since changed three ways: the plumbing reserves leg is gated to the ample-reserves
> regime (its pre-QE readings were noise), the basis_trade positioning percentile is capped as a
> gauge, and the ICE BofA series FRED truncated in April 2026 are restored from a frozen
> reference (so the credit_event and private_credit legs now carry 1996+ history). The script
> was re-run against the deployed `/pins/history` after that build went live; the diff is in
> **"v3 re-measurement"** below. The headline moved: **fast-red AND curve 44% / 5-of-11 → 34% /
> 4-of-13** on drawdowns, and on recession onsets **24% → 6%, below base rate**. The 2007 catch —
> the only NBER onset this gauge ever flagged — was the pre-QE reserves artifact. The sibling
> oil/policy-window+curve rule is unchanged at 45% / 5-of-6 and is now clearly the stronger
> configuration, not "the same within noise". Sections below are kept verbatim as the v2 record.

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


## v3 re-measurement (2026-09-10)

Same script, same pre-specified rules, same event sets. Only the deployed instrument changed.
Baseline run against the pre-change deployment reproduced v2 within data vintage (43% / 5-of-11).

### vs ≥15% SPX drawdown starts

| rule | v2 (frozen) | **v3 (re-measured)** | moved by |
|---|---|---|---|
| windows_open ≥ 2 | 26% · 8/22 · 184 mo | 23% · 8/24 · 183 mo | private_credit history now 1998+ |
| fast-channel window open | 25% · 9/31 · 232 mo | 18% · 8/33 · 177 mo | plumbing gate, basis cap, HY history |
| fast-channel red | 26% · 9/38 · 188 mo | 22% · 9/46 · 111 mo | same |
| oil/policy window open | 27% · 8/13 · 218 mo | 27% · 8/13 · 218 mo | — |
| curve flat/inverted | 37% · 6/9 · 156 mo | 37% · 6/9 · 156 mo | — |
| **fast-red AND curve** | **44% · 5/11 · 77 mo** | **34% · 4/13 · 50 mo** | lost the 2007 cluster |
| **oil/policy window AND curve** | 46% · 5/6 · 82 mo | **45% · 5/6 · 84 mo** | — (now the stronger rule) |

Base rate 20% throughout (22% for the 1987+ windows).

### vs NBER recession onsets

| rule | v2 (frozen) | **v3 (re-measured)** |
|---|---|---|
| windows_open ≥ 2 | 7% · 2/22 | 10% · 3/24 |
| fast-channel red | 10% · 3/38 | 3% · 2/46 |
| curve flat/inverted | 30% · 4/9 · recall 4/4 | 30% · 4/9 · recall 4/4 |
| **fast-red AND curve** | 24% · 3/11 · recall 2/4 | **6% · 2/13 · recall 2/4** |
| **oil/policy window AND curve** | 37% · 4/6 · recall 4/4 | 37% · 4/6 · recall 4/4 |

Base rate 9–12%.

### fast-red AND curve, per-drawdown detail (v3)

caught 1998 LTCM (4m early), 2019 (11–7m early), 2025 (12m early); **missed 2007** (v2 had it
"up to 12m early" — that firing was the plumbing reserves leg reading a pre-QE $3–47B base as a
drain), 2018 (curve stayed steep), 2021 (policy-driven). The 2019 lead narrowed from 11–1m to
11–7m because the basis_trade cap removed the late-run months that had been pinned at 100.

### What changes in the conclusions

1. **Recessions still belong to the yield curve** (30%, 4/4). Unchanged.
2. **Raw convergence counts still score below base rate on recessions** (10% vs 12%). Unchanged
   in direction, narrower in margin.
3. **Pin reds earn their keep on market accidents — more modestly than v2 said.** 34% vs 20%
   base on 4 of 13 clusters is still above base, but the 2007 catch that anchored the v2 story
   was an artifact, and on recession onsets the composite is now *below* base rate. The
   sibling `oil/policy window + curve` (45%, 5/6; 37%, 4/4 on onsets) is no longer "the same
   within noise" — it is the better configuration on both event sets, on fewer, cleaner
   clusters. The accident gauge as shipped remains *a* measured configuration; v3 makes it
   clearer that it is not *the* one.
4. **Never blend them.** Unchanged, and reinforced: v2's headline moved by 10 points from data
   corrections alone, which is the noise floor a 13-cluster sample carries.

Episode-level record for the whole board, all channels: v2 115 episodes / 14 hits / 93 misses;
v3 **120 / 15 / 98** (precision 13.1% → 12.5%). Live `_overlap_validation` (recomputed
server-side): base 12.3%; k=1 10.2% (n=353), k=2 10.3% (n=195), k=3 9.3% (n=86), k=4 15.4%
(n=26).
## Honest limitations

~11 signal clusters (episode-level 95% CI ≈ ±30pp); serially-correlated
months; fast channels' sources begin 2002-2006 so early misses are partly
data gaps; drawdown threshold (15%) and curve cut (0.25pp) are conventional
but still choices; drawdown "start" is the monthly-close peak (the true daily
peak can be up to ~2 months later — e.g. COVID: monthly-close peak Dec-2019,
daily peak Feb-2020); channel coverage grows over time, so cross-era
comparisons are confounded. Re-run the script to refresh; all numbers are
descriptive context, never calibration.
