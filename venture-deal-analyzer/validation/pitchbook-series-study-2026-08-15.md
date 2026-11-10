# Study — PitchBook "VC Returns by Series" (Parts I–V) vs the deal analyzer

VERIFIED — counter-agent verdict "SAFE TO CALIBRATE FROM" (2026-08-15):
fresh fetches byte-identical, 20+ numbers spot-checked, zero numeric
errors; the inversion is PitchBook's own language ("Series A goes from
first to worst"). Carried caveats: Part I's 76.2% <1x bucket is right
to last-digit rounding (76.1 possible); Parts I–II are exited-only
(survivor) bases while III–IV include tracked failures — never mix
series across that discontinuity; annualization holding-period
convention never stated by PitchBook. Added from verification: Part IV
seed failure by sector — all-VC 38.6%, SaaS 27.5%, life sci 42.3%.
Sources: Parts I–IV fully extracted (I 2019 global · II 2020 global ·
III 2021 global · IV 2024 US-only); **Part V gated — not read, not
guessed; LP asked to supply if desired.** Prompted by Casey supplying
the links, 2026-08-15.

## Finding 1 — the headline is winners-only, and PitchBook's own
## adjustment INVERTS it

The famous numbers (Series A 26.7% vs B–F 15.2–19.4%; seed 25.5%) are
pooled capital-weighted aggregates of EXITED companies. Parts I–II also
published failure-ADJUSTED versions, and they flip the ranking:

| adj. annualized | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Part I (2019) | **−4.3%** | −3.9% | −1.1% | +2.8% | +2.5% | +4.4% |
| Part II (2020) | +2.4% | +1.3% | +6.0% | +10.0% | +11.9% | **+11.3%** |

Early series NEGATIVE-to-worst once you charge them for the companies
that never exit; late series positive. Parts III–IV then dropped the
OOB compounding methodology and the early-best headline returned. The
stage-ranking conclusion is therefore METHODOLOGY-DEPENDENT — it flips
sign on the failure-rate treatment, which is precisely the number
nobody measures well. **Consequence for the instrument: no
stage-preference prior gets encoded from this research.** "Enter at
seed/A" is not a fact; it is one side of an assumption the source
itself contradicts in its own earlier parts.

## Finding 2 — the annualized headlines are the wrong object anyway

Σ(payouts)/Σ(invested), annualized, gross, pre-fee, IPO-pre-money
marks, outlier-dominated (Uber alone = 35% of the entire seed payout in
Part IV; its seed MOIC 5,230x). Not per-deal means, not medians, not
IRRs, not distributions. They cannot calibrate an exit-multiple model
and will not be used as such.

## Finding 3 — what IS usable: real stage-conditional MOIC buckets

Part I (all-VC, D+) and Part IV (seed, Series C+) publish genuine
per-deal MOIC histograms — the first MEASURED stage-conditional
distributions we have seen anywhere:

| bucket | CV all (our seed anchor) | PB I all-VC | our B (constructed) | **PB IV C+ (measured)** | PB I D+ |
|---|---|---|---|---|---|
| <1x | 64.8 | 76.2 | 41.7 | **50** | 39.6 |
| 1–5x | 25.3 | 11.8 | 49.6 | **41** | 40.6 |
| 5–10x | 5.9 | 5.9 | 6.1 | **6** | 14.0 |
| 10–20x | 2.5 | 3.5 | 1.8 | **2** | 4.0 |
| 20–50x | 1.1 | 1.7 | 0.6 | **1** | 1.3 |
| >50x | 0.4 | 1.0 | 0.2 | **0** | 0.5 |

Readings:
- Our CONSTRUCTED Series B buckets land remarkably close to PitchBook's
  measured C+ histogram in shape; the one real divergence is loss mass
  (ours 41.7 vs C+ 50 by count). Since B sits earlier than C+, a B loss
  mass somewhere in 42–50 is defensible; ours is at the optimistic
  edge. ACTION: widen the documented uncertainty band on series_b loss
  mass to 0.40–0.50 and add a cross-check gate (B loss must lie between
  the CV-dollars floor and the PB C+ count ceiling).
- PB IV seed: **81% of seed entries return <1x** vs our seed anchor's
  64.8 (CV, all financings pooled). Different objects (seed-only vs all
  rounds; 6-year-no-raise counted as failure), but directionally our
  "seed" curve is generous for true first-check seed. ACTION: document;
  note that deal-level tilts (we pin P(<1x) at the logged forecast
  anyway) make the verdict-level impact small.
- Sensitivity computed: because the tilt pins P(<1x) and P(≥10x) to the
  logged forecasts, swapping the entire base shape moves Quaise's
  P(net≥20x) by ~0.05pp and EV by ~0.02 — **our deal verdicts are
  robust to which anchor wins.** The recalibration matters for honesty,
  not for any current decision.

## Finding 4 — failure rates by series (usable for the hurdle ledger)

Part III count basis: A 23.6, B 16.7, C 13.5, D 12.1, E 10.8, F 11.8%;
dollar basis roughly two-thirds of count. Part IV (US, stricter
definition incl. 6-yr-no-raise): seed 38.6% → D+ ~13%. These calibrate
the E3 (cash-bridge/financing) hurdle anchors per entry stage — a
direct upgrade over the Carta graduation proxies. Caveat: Part III
self-admits undercounting failures; Part IV's definition overcounts
ambiguously; use as a bracket, not a point.

## Finding 5 — implied holding periods (backed out, Parts I–II)

ln(total)/ln(1+annualized): Series A ≈ 5.3–5.4 yrs, B ≈ 4.8–5.2, F ≈
3.2–3.5. Useful for the time-discounting layer the EV trees currently
flag as unmodeled. Part IV drops total returns so horizons are not
recoverable there.

## What changed in the analyzer (applied post-verification, 2026-08-15)

1. calibration.json: series_b provenance upgraded — loss-mass band
   documented as 0.40–0.50 with PB IV C+ as the measured ceiling; new
   gate test bracketing B loss mass (12 gates now pass). No refit of
   deal verdicts needed (Finding 3 sensitivity). DONE.
2. hurdle-ledger E3 anchors: add Part III/IV per-series failure-rate
   brackets alongside Carta.
3. Instrument note: NO stage-preference prior encoded (Finding 1).
   Any pitch citing "Series A returns 26.7%" gets the winners-only +
   inversion rebuttal from this study.
4. Honesty box addition wherever PB numbers are cited: gross, pre-fee,
   IPO-pre-money marks, outlier-dominated aggregates; Parts I–III
   global vs IV+ US-only — the two methodology vintages are not
   comparable with each other.

## File manifest (per standing rule)

- Part I PDF: READ IN FULL · Part II PDF: READ IN FULL · Part III PDF:
  READ IN FULL · Part IV PDF: READ IN FULL (direct file URL located)
- Part V: **GATED — NOT READ.** Landing-page abstract only (Bay
  Area/NY outperformance, concentration ~65% of 2025 commitments).
  No per-series regional numbers extractable. LP can supply the PDF
  via chat upload for a follow-up.
