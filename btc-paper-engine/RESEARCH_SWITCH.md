# RESEARCH_SWITCH.md — dynamic S5↔S6 leverage interleaving study

Run 2026-08-07 on the 4y fixture window (2022-08-07 → 2026-08-07, 285 blend
steps). Script: `backend/scripts/research_switch.py`. Question (Casey): is
there a gate/confidence score that decides when to run S6 (2.0x) vs S5
(1.5x)?

**Framing:** S5 and S6 are the same blend at different leverage, so
"switching books" = a leverage rule m(t) ∈ {1.5, 2.0} on the unlevered blend
steps. Decisions use only information available at each trade exit and apply
to the NEXT step — exactly how the executor would implement it (resize at
flat, never mid-position, so switching itself costs nothing extra).

**Protocol:** 16 rules across 6 families; any tuned threshold computed on the
FIRST 2y only (IS), frozen, validated on the second 2y (OOS). Trade-step
basis, research fees, no cash yield — same basis as the S5/S6 rows
everywhere else in this repo.

## Headline result

| rule | full ret | full maxDD | full MAR | OOS ret | OOS maxDD | OOS MAR | % time at 2x |
|---|---|---|---|---|---|---|---|
| S5 static | +214.5% | −21.4% | 1.55 | +65.0% | −21.4% | 1.33 | 0% |
| S6 static | +327.8% | −27.7% | 1.58 | +88.3% | −27.7% | 1.35 | 100% |
| **EFF gate (30d efficiency > IS-q40)** | **+490.9%** | **−23.3%** | **2.40** | **+127.8%** | **−23.3%** | **2.19** | 56% |

The efficiency gate — run 2.0x when the 30-day price path is DIRECTIONAL
(|net move| ÷ path length above its IS 40th percentile), 1.5x when the
market is chopping — beat BOTH statics on return, drawdown and MAR, in both
halves. It is a direct mechanization of the 5y study's core finding: this
system's failure regime is directionless chop (2024), and its best regimes
are moves in either direction. The gate takes the extra leverage only where
the edge lives and hands it back in the regime that bleeds.

Two independent confirmations of the same mechanism:
- `tr200inv` (2x BELOW the 200d MA — i.e., in bears) beats both statics
  (MAR 1.72 / OOS 1.64): the 2022-style regime is where 2x earns.
- `edgeinv` (2x after LOSING streaks) also beats statics (1.69/1.54):
  naive "lever up when hot" logic is exactly backwards for this system.
- Every intuitive gate (lever up in uptrends, when winning, when not in
  drawdown) UNDERPERFORMED the statics. Worth remembering.

## Robustness

1. **Lookback × threshold sweep** (25 cells): effect holds across the
   20–40-day band (look=120/180/240 all beat statics OOS at every quantile,
   OOS MAR 1.3–2.2) and peaks at 30d. **Yellow flag:** 10-day lookback
   FAILS (OOS MAR ~1.0) — the signal needs ~a month of path to read regime,
   and the peak-at-180-bars means some of the observed edge is
   parameter-luck. Discount the point estimate; the band, not the peak, is
   the finding.
2. **Permutation test** (500 circular shifts of the efficiency series):
   real MAR 2.40 vs shuffled median 1.51, p = 0.002. The signal's
   *alignment* with step outcomes is real, not leverage-timing luck.
3. **Halt-race bootstrap** (20k × 2y block-resampled (r, eff) pairs, −35%
   MTM halt barrier): GATE P(halt) 6.4% vs S5 5.3% / S6 21.4%; median
   terminal +141% vs +77%/+100%; p10 +35% (best of the three). In the
   resampled distribution the gate dominates: S6-beating growth at
   S5-like tail risk.

## Honesty box

- **One asset, one 4-year sample, 285 steps.** The chop regime the gate
  dodges is essentially ONE major episode (Jan–Jul 2024) plus minor
  stretches; the OOS half validates but shares the same market. 2021-style
  euphoria and the full 2022 crash entry are NOT in this window.
- **Multiple testing:** 16 rules + a 25-cell sweep were examined. The
  permutation p-value, cross-threshold consistency, mechanism coherence
  (three independent rules point the same way) and IS/OOS agreement all
  mitigate — but the true edge is likely smaller than +2.40 MAR vs 1.58.
  A priori haircut: assume roughly half the MAR gap survives live.
- **Basis:** trade-step drawdowns; MTM runs ~1–4pp deeper for all rows
  alike. Bootstrap resamples the same 285 steps — regime shifts outside
  the sample are not represented. The efficiency→outcome relation is
  assumed stationary in the resample.
- **Not modeled:** funding-rate differences at 2x notional on the live
  venue; the gate's own estimation lag on the first ~30 days after deploy.

## Recommendation (staged, no live change now)

1. **Do not wire this into live sizing yet.** The S5 ramp plan
   (KELLY_M 0.05 → 0.56 → 0.80) stands unchanged.
2. **Shadow the signal first:** engine logs the 30d efficiency ratio and
   the gate's hypothetical lever each poll alongside live S5. Zero risk;
   builds a live track record of switch timing.
3. **Re-run the study on the full 5y externally-fetched data** (2021 bull +
   complete 2022 crash) before any promotion — the fixture now reaches
   2022-01, but the 2020-09→2022-01 slice of the 5y study's data would
   stress the gate against a regime it hasn't seen.
4. If both hold up after the live ramp completes: implement as an
   engine-side dynamic `lev` in the `/exec/target` blend config (the
   executor already consumes `lev` from the engine, so the change is
   engine-only), gated behind its own env flag, and start at the
   conservative end (q50–q60 threshold, i.e., LESS time at 2x).
