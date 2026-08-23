# The "bet the market is wrong on payrolls" trade — does it exist?

**Study date:** 2026-08-23 · **Script:** `nfp_surprise_study.py` (reproducible
from `data/nfp_surprises.json`) · **Gates:** `tests/test_gates.py` (15 passing)
· **Sample:** 160 NFP releases, 2013-04-05 → 2026-08-07, consensus vs
**first print** (what a pre-release bet actually resolves against).

## Verdict

**The standing trade does not exist.** Consensus is not directionally biased,
so "bet the market is wrong" is a coin flip. The 75% recollection is real but
it describes a *different* trade — a private information edge, not a rule.

| era | n | mean surprise | t | "bet above consensus" |
|---|---|---|---|---|
| 2013–2019 (clean) | 81 | +1.2k | +0.17 | **40/80 = 50.0%** (p=1.00) |
| 2022–2024 (reopening) | 36 | +60.8k | +3.19 | 26/36 = 72.2% (p=0.011) |
| 2025–2026 | 19 | +3.5k | +0.18 | 10/19 = 52.6% (p=1.00) |
| core (ex-COVID, all) | 138 | +17.4k | +2.39 | 77/137 = 56.2% (p=0.17) |

The only period that looks like "75%" is **2022–2024, and only in hindsight**.
Pre-COVID it is 50.0% — the cleanest possible null. The core-sample `t=+2.39`
is *entirely* the 2022–24 block; drop it and the bias vanishes. Picking that
window after seeing the data is the definition of an in-sample result.

Everything else we tested is dead too:

| rule (out-of-sample, no lookahead) | hit rate | p |
|---|---|---|
| month-of-year direction, walk-forward | 38/70 = 54.3% | 0.55 |
| consensus vs 3-mo actual trend (anchoring) | 71/133 = 53.4% | 0.49 |
| lag-1 autocorrelation of surprise | −0.042 | — |
| CES 4-week vs 5-week reference gap | −16.9k | Welch t=−1.19 |

**Residual seasonality** — the closest living descendant of the original edge —
is a ghost: the best single month is November (9/11, p=0.065), but that is one
of 12 simultaneous tests. Šidák-corrected: **p=0.556**. Noise.

## What Lonsdale's trade actually was

From his April 2024 *My First Million* interview (ep. 578), describing his
stint at **Clarium Capital**, Peter Thiel's global-macro fund, ~2003–04:

> "Kevin Harrington, the head of research, discovered an error in the seasonal
> adjustment of the numbers, allowing them to predict whether the number would
> hit or miss."

First Friday of the month, desk in at 5:30am PT for the 8:30am ET print, large
bets on **the market's reaction** — mostly bonds — with millions at stake.

The mechanism matters more than the anecdote. This was **not** "the market is
usually wrong, so fade it." It was: *we have a better model of the BLS's own
seasonal-adjustment machinery than anyone else does, so we know the print
before it lands.* An information edge in a specific published algorithm.

That distinction is the whole finding. A behavioural rule you can state in one
sentence is arbitraged away; a modelling edge in a government statistical
process is not, but it also isn't something you can adopt by hearing about it.

Why it is far harder now than in 2004:
- BLS moved CES to **concurrent** seasonal adjustment (factors recomputed each
  month with all data through the current month), shrinking the stale-factor
  error that a static-factor model could exploit.
- Seasonal factors and methodology are published; the 2004 asymmetry is gone.
- Nowcasting desks, ADP, and prediction markets all compete on the same gap.

## Follow-up: do other signals tilt the odds? (No.)

Casey's follow-up — consensus may be unbiased on average, but other indicators
could still be tells. Eight pre-specified candidates, each measured as its own
surprise from the last print **strictly before** the NFP release (no lookahead),
`signal_study.py`:

| candidate | n | Pearson | Spearman | sign hit rate |
|---|---|---|---|---|
| ADP employment change | 135 | −0.229 (p=0.007) | **+0.037 (p=0.67)** | 72/135 = 53.3% |
| ISM manufacturing PMI | 126 | +0.112 | +0.171 (p=0.053) | 70/125 = 56.0% |
| Continuing jobless claims | 137 | +0.017 | −0.171 (p=0.044) | 61/135 = 45.2% |
| Initial jobless claims | 131 | −0.049 | −0.085 | 57/129 = 44.2% |
| ISM non-mfg employment | 40 | −0.248 | −0.206 | 15/39 = 38.5% |
| Challenger job cuts | 90 | −0.112 | −0.130 | 46/90 = 51.1% |
| ISM manufacturing employment | 103 | +0.042 | +0.019 | 51/101 = 50.5% |
| NFIB business optimism | 123 | +0.037 | −0.016 | 65/121 = 53.7% |

**The Pearson column is a trap.** ADP looks like a real find at p=0.007 (Šidák
0.052) — until you rank it. Spearman **+0.037, p=0.67**: the entire Pearson is
two or three outliers. Same story for the direct test of Casey's framing,
"consensus is misaligned with the freshest hard read":

| consensus vs ADP actual | n | NFP beat |
|---|---|---|
| survey well **below** ADP | 45 | 58% |
| middle | 45 | 51% |
| survey well **above** ADP | 45 | 58% |

Pearson +0.224 (p=0.008), Spearman −0.020 (p=0.82), rule hit rate 49.6%. The
terciles are flat-to-U-shaped — no monotonic relationship of any kind.

Walk-forward, every candidate lands between 42% and 53%; none is significant.

**Why this is the expected answer.** Economists set their NFP forecast *after*
reading ADP, claims, ISM, and Challenger. Consensus already impounds them — that
is precisely *why* it is unbiased. Any public pre-release indicator is priced in
by construction. The only thing that can work is information consensus does not
already have, which is exactly what Clarium had and what we do not.

## Honesty box

- **Measurement basis:** first print vs consensus captured at release. No
  transaction costs, no slippage, no position sizing — these are raw
  directional hit rates, an upper bound on any real strategy.
- **In-sample warning:** the 2022–24 72% is in-sample and window-selected. It
  is shown to explain where a "75%" impression comes from, **not** as a
  forecast. Do not size anything off it.
- **NOT modelled:** the market's *reaction* to the print (Lonsdale's actual
  P&L driver — bonds can rally on a hot number). We measured only whether the
  number beats consensus. A reaction study is a separate build and needs
  intraday ZN/ZB tick data we do not have.
- **NOT modelled:** revisions. FMP's `previous` field is back-filled with
  revised values, so it cannot measure revision-at-the-time. Any revision claim
  needs ALFRED/FRED vintages. We ran the test, got a result contradicting the
  well-documented 2024–25 downward revisions, and **discarded it** rather than
  publish a number our data could not support.
- **Consensus source:** FMP's `estimate`, a survey median. Spot-checked against
  known Bloomberg consensus (Mar-24 200k/303k, Apr-24 243k/175k, May-24
  185k/272k) — all match. Not independently audited beyond that.
- **Data gaps:** October 2025 has no standalone release (folded into the
  2025-12-16 print). The 2025-11-20 release is the **September** report, not
  October — FMP's implied labelling is wrong there and is overridden in
  `build_dataset.py`. Both are gated.
- **Sample start 2013:** FMP's calendar does not reach further back, so the
  Clarium-era (2003–07) claim **cannot be tested directly with this data**.

## If we wanted to build the real version

The only honest path is to rebuild the *information* edge, not the rule:
a genuine NFP nowcast from independent high-frequency inputs (ADP, initial
claims in the reference week, ISM/PMI employment, withholding-tax receipts,
Indeed postings, WARN filings), plus our own X-13 seasonal reconstruction from
`PAYNSA`.

The bar is unambiguous, and it is the gate we would enforce:

> **beat the consensus median on out-of-sample RMSE across ≥24 consecutive
> releases before any capital is committed.**

Absent that, there is nothing here to trade. Venue if it ever clears the bar:
Kalshi lists monthly payroll contracts (since March 2023) — the Fed's own
working paper *Kalshi and the Rise of Macro Markets* (FEDS 2026-010) treats
them as a well-behaved, distributionally rich benchmark. Note the arithmetic:
a 56% edge on a ~50c binary is ~6c gross, and Kalshi spread + fees on these
eat most of that.
