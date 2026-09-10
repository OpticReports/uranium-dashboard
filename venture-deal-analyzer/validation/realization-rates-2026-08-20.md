# Study — will a Series A ever produce a REALIZED multiple at all?

VERIFIED 2026-08-20 (counter-agent pass run inside the research leg;
one fabricated table caught and discarded — see Integrity note).
Prompted by Casey: *"what is the probability that a series a will even
have a realized multiple."*

This is a different question from "what multiple does it return," and
the answer materially qualifies every other number in this repo.

## Headline

**By count, only about a quarter of US venture-backed companies ever
reach a liquidity event — and the largest terminal state is neither
exit nor death. It is limbo.**

Best measured object located: the **PitchBook Part IV funnel**, n=31,642
US companies taking a first VC round **2009–2018**, measured as of
2024-06-06 (so cohort ages 5.5–15.5 years), **count basis, includes
still-held positions**. All six round transitions sum exactly to their
round populations — strong evidence of correct transcription.

| terminal state | share |
|---|---|
| Exited (M&A or IPO) | **25.5%** |
| Bankrupt / out of business | 31.1% |
| **Never raised again, no outcome (limbo)** | **39.6%** |
| Still raising | 3.8% |

**Conditional on reaching round 2** — the closest available proxy for
"raised a Series A", n=18,232 [DERIVED, flagged as such]:

| | share |
|---|---|
| Exit | **29.4%** |
| Dead | 20.6% |
| Limbo | 43.4% |
| Still raising | 6.6% |

So the honest answer to Casey's question is **roughly 30%, over a
5.5–15.5 year observation window** — and the single most likely outcome
is not a multiple at all, it is an unresolved position.

Exit share *peaks* around round 3 and then falls: later survivors are
disproportionately **unresolved**, not resolved well.

## Corroborators

- **CB Insights**, 1,100+ seed companies 2008–2010 tracked to Aug 2018:
  **30% exited**; 67% dead or self-sustaining.
- **Carta**, class of 2018, n=3,067, ~6 years: 49% shut down, 5%
  acquired, 0.2% IPO → **54% resolved, almost entirely via the death
  channel.** [SECONDARY — carta.com Cloudflare-blocked; figures via ACA]
- **PitchBook**: of 1,300+ US companies valued >$500M, 40 exited in
  2024 ≈ **3%/yr realization on the best slice of the market.**

## Time to realization

Ritter (University of Florida, primary, Table 4i) — median
**founding-to-IPO age** for VC-backed tech IPOs: 8 yrs (1995) → 4
(1999) → 10 (2010–15) → 11 (2020–21) → 12 (2025). Decade averages
7.6 / 9.0 / 10.8 / 11.7. **Caveat: 2022–24 samples are n=1, 4, 8 — not
readable as trend.**

Our own back-out from PitchBook Parts I–II (Series A ≈ 5.3–5.4 yrs)
**reproduces exactly** (5.38 / 5.29). But it is **exited-only,
2019-vintage, and excludes the 39.6% limbo bucket entirely** — so it is
the holding period of the *winners plus the resolved losers*, not of a
position. No published Series-A-to-exit or founding-to-M&A duration
series exists.

## The unrealized overhang — why this is worse now than the base rates suggest

- PitchBook Venture Monitor Q1 2026, verbatim: *"the median
  distributions to paid-in multiple for vintages over the past decade
  remains below 1x."*
- Net US VC cash flow **negative every year 2022–2025**;
  *"$196.9B net drawn more than returned since 2022."*
- Stanford GSB / PitchBook (n=1,600 funds): share of funds with DPI
  <25% at year four rose 46.1% (2017) → 60.6% (2019) → **74.8%
  (2021).**
- Unrealized NAV **$3.2T** (2025), ~$1.7T of it in 2019-and-earlier
  vintages.
- Secondaries are only a partial escape: $106B in 2025 (~30% of exit
  value), but **the 20 most-traded companies are 86.4% of volume** —
  the channel is effectively closed to the long tail.

## Zombies, and a definition trap

The **39.6% limbo bucket IS the measured zombie rate.** Competing
failure definitions must be quoted, never blended:

- PitchBook Part IV counts **6 years with no new round** as failure —
  which interacts badly with lengthening round gaps and inflates
  measured failure.
- PitchBook Part III **excludes non-outcomes entirely** and self-admits
  undercounting.
- Exit Predictor bundles failure together with "self-sustaining."

**The widely circulated "30–40% zombie rate" traces to an uncited
content-marketing blog post** — fetched, confirmed to carry zero
citations. Tagged UNVERIFIED. **Do not use it**, even though the real
figure happens to land in that range; a right answer from a fabricated
source is still a fabricated source.

## A hypothesis of ours that the data REFUTED

We proposed that failures resolve faster than successes, which would
bias early realized multiples downward. **Hall & Woodward (AER 2009,
n=22,004 — the only published joint distribution of lifetime × exit
value) runs the other way:** mean lifetime **3.35 yrs for $200M+ exits,
3.85 for $50M+, 4.42 for zeros, 4.84 for any positive outcome.** Their
words: *"a distinct negative correlation between exit value and venture
lifetime."*

Caveats that matter: 4,220 of ~7,572 zeros are **imputed with randomly
assigned dates**, and the sample ends in 2008.

What does survive: **69–75% of every lifetime bucket past year five
ends at zero, and 18.2% of zeros took 7+ years.** The dominant failure
mode is a **slow write-off**, not a fast one — which is the practical
version of the intuition, even though the clean timing asymmetry is
refuted.

## CONSEQUENCE FOR THE ANALYZER — the important part

**`models/calibration.json` and the hurdle ledger are calibrated on
EXITED-ONLY bases** (Correlation Ventures; PitchBook Parts I–III).
Those distributions describe outcomes *conditional on an outcome
occurring*. On the Part IV evidence, **roughly 40% of positions never
enter that base at all.**

Therefore every P(<1x), P(>=10x) and EV this repo publishes should be
read as **conditional on realization**, and the unconditional picture
for a fresh Series A check is materially worse:

- P(realization within ~10 yrs) ≈ 0.30
- P(any given multiple) = P(realization) x P(multiple | realization)

ACTION TAKEN: this is now stated explicitly wherever curve outputs are
displayed, rather than left as an unstated conditioning. It is NOT
folded into the curves themselves — the exited-only bases are the
measured objects and remain the right thing to fit; the conditioning
is a disclosure, not a parameter.

## Not measured anywhere (do not fabricate)

1. A Series A cohort survival curve at years 5 / 7 / 10 / 12.
2. Exit rates by single vintage year — every published funnel pools a
   ~10-year window.
3. M&A vs IPO durations measured from a defined entry point.
4. Any post-2010 joint lifetime x value distribution.
5. The split of the limbo bucket into profitable / unprofitable /
   silently dead.
6. Position-level stale-mark-to-write-off lag.

## Integrity note (standing counter-agent rule)

A first automated read of the CB Insights funnel produced a
stage-by-stage count table (528 / 333 / 165) **that does not exist in
the article** — a verbatim re-read found only percentages, and the
fabricated table was discarded before use. Also disclosed: the WEF DPI
chart **contradicts its own body text** (11.5% vs "<6%"), and a
PitchBook Part III global funnel (n=36,897) was **excluded** because no
consistent decomposition of its extracted cells exists.

## Blocked / not read

carta.com (Cloudflare 403 direct and via reader proxy — all Carta
figures SECONDARY); files.pitchbook.com PDFs (403; Parts I–IV read via
verified full-text extracts held in-repo); **Part V still gated — not
read, not guessed**; Q3 2024 Quantitative Perspectives gated (its
"70% of exits below cost" figure used only as SECONDARY); Scribd Exit
Predictor document would not render.
