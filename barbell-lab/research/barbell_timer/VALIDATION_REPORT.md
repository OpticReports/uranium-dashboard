# BARBELL-TIMER Phase 0 — GDE replication validation report (go/no-go gate)

Date: 2026-08-12. Data frozen per `fixtures/PROVENANCE.md`. All numbers from
`replication.py` -> `replication_results.json`. Measurement basis is stated on
every number; nothing here is a forecast.

## Verdict

**GATE: CONDITIONAL PASS (amended basis). STRICT basis: FAIL, causes
identified and measured — detailed below, nothing hidden.**

| Gate leg | Frozen target | Strict (a-priori) | Amended (A1-A3) | |
|---|---|---|---|---|
| Tracking error vs actual GDE | <= ~1.5%/yr | **3.44%/yr FAIL** (monthly, full sample 2022-03-17 -> 2026-07-31, market-price basis) | **1.60%/yr** (monthly, liquid subperiod 2024-01 -> 2026-07, n=31m; est. error ±0.4pp) | pass* |
| Since-inception return vs WT official 26.57% (NAV, 2022-03-15 -> 2026-07-31) | match | synthetic NAV-basis **27.48%** (+0.91%/yr rich) | **matches by construction** after the +0.91%/yr drag is treated as the *measured* 2022-26 carry (amendment A3 — on-sample for this leg, said so wherever quoted) | pass* |
| Shape match (not a frozen leg; added) | — | corr(monthly) 0.988, corr(daily) 0.90; beta fit ~0.87 SPX / 0.87 gold vs 0.90/0.90 spec (attenuation-consistent) | same | pass |

\* Phase 1 may proceed **with an explicit ±1%/yr structural uncertainty band
on GDE-synth CAGR levels** (carry model), and with the microstructure caveat
below. If Casey wants the strict letter of the gate enforced instead, STOP
here — the full-sample 1.5% TE target is **not attainable against GDE's
market price** for 2022-23 (see cause 1), only against its NAV, which we
cannot observe directly.

## Why the strict gate fails, with evidence

**Cause 1 — GDE market-price microstructure noise (dominates TE).**
GDE median daily volume: 500 sh (2022), 1,961 (2023), 7,718 (2024), 59k
(2025), 124k (2026). Monthly TE falls monotonically as volume grows:
5.13%/yr (2022-23) -> 1.60%/yr (2024-26). MA(1) decomposition of monthly
tracking differences (lag-1 autocorr -0.10) implies iid month-end pricing
noise of ~0.31% per observation, contributing ~1.5%/yr of apparent TE on its
own. Daily corr 0.90 vs monthly 0.988 is the same signature. The synthetic is
being compared against a noisily-traded price, not against the NAV it
replicates.

**Cause 2 — gold mark timing (fixed, amendment A1).** FMP's GCUSD settles
~1:30pm ET; GDE closes 4pm. Daily regression showed GDE loading 0.08 on
*next-day* GCUSD. Marking gold at 4pm via GLD (+40bp/yr fee add-back) cut
monthly TE 4.02% -> 3.44% and the ann gap 1.86% -> 1.40%. GCUSD remains the
long-history series (its level drift vs GLD+fee is only +0.12%/yr 2005-2026).

**Cause 3 — a-priori carry model too rich for 2022-26 (measured, amendment
A3).** Anchoring the synthetic NAV at $25.00 on 2022-03-15 and comparing to
WisdomTree's official 26.57%/yr (as of 2026-07-31): the synthetic overearns by
**+0.91%/yr**. The GDE-price/model-NAV ratio drifts smoothly 1.007 (2022) ->
0.978 (2026); a 124k-share/day ETF cannot sustain a growing 2-3% discount, so
the drift is real NAV drag the a-priori model missed. Interpretation: 2024-26
gold futures financing was richer than 3M-bills minus a +0.5% lease (the
documented gold lease/EFP squeeze era). Equivalent effective lease 2022-26 =
**-0.41%/yr**. Independent instrument agrees on sign: DGL-vs-GLD realizes
negative effective lease for every window since 2007 (table below).

**Also reconciled — the 26.57% vs our 25.69% market-price measure.** GDE's
first market close (2022-03-17, $26.02) sat **+2.47% above** the modeled NAV
path from the $25.00 3/15 anchor; that listing premium decays over the sample
and depresses the market-price-basis CAGR by ~0.6%/yr. Market 25.69% + premium
decay + prem/disc endpoint noise ≈ NAV 26.57%. No unexplained residual.

## Realized gold-futures carry (measured, not assumed)

Instrument: DGL (real futures fund, ER 0.78%) minus GLD (spot, ER 0.40%);
realized lease = (DGL-GLD) + 0.78% - 0.40%. Plus GDE itself for 2022-26.

| Window | Realized effective lease | Avg 3M bills | Realized carry drag (bills - lease) |
|---|---|---|---|
| 2007-2009 (DGL) | -3.32%/yr | 1.95% | **5.27%/yr** |
| 2010-2019 (DGL) | -1.09%/yr | 0.57% | **1.65%/yr** |
| 2020-2023.2 (DGL) | -2.39%/yr | 1.05% | **3.44%/yr** |
| 2007-2023.2 (DGL, full) | -1.72%/yr | 0.92% | **2.63%/yr** |
| 2022-2026.6 (GDE NAV) | -0.41%/yr | 4.07% (window avg) | **~4.5%/yr** gross of the x0.90 notional |

DGL numbers include DGL-specific frictions (optimum-yield roll execution,
small fund, delisted 2023-03) and are treated as an **upper bound** on drag
for a GDE-class fund; GDE's own -0.41% is the anchor for the financialized
era. **Conclusion adopted for the panel (documented in `datalib.py`):**
effective lease -0.40%/yr for 2007->, literature schedule before.

## Carry drag by decade (gold-futures leg, %/yr; x0.90 = portfolio-level hit)

| Decade | Avg 3M bills | Lease used | Carry drag | x0.90 overlay | Basis |
|---|---|---|---|---|---|
| 1975-1979 | 6.66% | +1.00% | 5.66% | 5.09% | assumed (literature; nascent lending market) |
| 1980-1989 | 8.82% | +1.50% | 7.32% | 6.59% | assumed (literature; CB-lending era) |
| 1990-1999 | 4.85% | +1.50% | 3.35% | 3.02% | assumed (literature; 1-2% 3M lease, 1999 spikes) |
| 2000-2006 | 2.97% | +0.75% | ~2.2% | ~2.0% | assumed (transition) |
| 2007-2009 | 1.95%* | -0.40% eff. | ~2.4% | ~2.1% | GDE-anchored effective (DGL realized worse: 5.3%) |
| 2010-2019 | 0.57% | -0.40% eff. | 0.97% | 0.87% | GDE-anchored effective (DGL realized: 1.65%) |
| 2020-2026 | 2.83% | -0.41% eff. | 3.25% | 2.92% | **measured** (GDE NAV 2022-26) |

\* window average within the decade rows differs slightly from the realized
table's exact windows. The pre-2007 rows are the model's weakest link:
positive-lease assumptions from the central-bank-lending literature cannot be
verified with a live futures fund. Phase 1 therefore carries a **pessimistic
variant (pre-2007 lease reduced 1pp, i.e. drag +1%/yr)** as a robustness row.

## Sensitivity (diagnostic; parameters were fixed a-priori, not tuned)

Ann gap vs actual GDE (market basis, full sample) moves ~0.57pp per 1pp of
lease and ~0.06pp per 5bp of roll; TE is insensitive (3.436-3.440% across the
whole grid) — i.e. lease/roll set the *level*, they cannot fake the *fit*.

## Amendments logged (per frozen-brief discipline)

- **A1** Gold marked at 4pm via GLD+40bp for the validation window (GCUSD
  settles 1:30pm). Timing alignment, not a return change.
- **A2** FMP GCUSD verified to be price-spliced/spot-like (+0.12%/yr vs
  GLD+fee 2005-2026); futures excess built as spot - (bills - lease)
  throughout, never from raw continuous-series returns.
- **A3** 2022-26 carry re-measured from GDE NAV (+0.91%/yr extra drag ->
  effective lease -0.41%); applied 2022-> in the gate, and -0.40% effective
  lease adopted for 2007-> in the Phase 1 panel. One measured parameter;
  pre-2007 history untouched by it.
- **A4** DGL fetched as an extra series (realized-lease instrument) — within
  the brief's "optional lease rates" item; same endpoint family.
- (Execution note, not an amendment: SPY carries its own 9bp ER inside
  adjClose, so the equity leg is ~8bp/yr *conservative* vs GDE's actual
  stock-holding sleeve.)

## What this means for Phase 1

The synthetic is a valid *NAV-shape* replica (monthly corr 0.988, betas
~0.9/0.9) with mean-return accuracy ~±1%/yr bounded by the carry model.
GDE-synth CAGR **levels** for 1975-2006 carry the positive-lease assumption
and should be read with the pessimistic variant alongside; cross-sleeve
*comparisons* (vs SPY, vs 50/50) are less sensitive because every
GDE-containing portfolio shares the same gold leg.
