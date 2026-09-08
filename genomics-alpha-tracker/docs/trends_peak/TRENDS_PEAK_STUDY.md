# Google Trends attention tops — event study (rev 1, 2026-09-08)

**Question (Casey):** can search interest tell us when a position has topped?
A friend called the silver blow-off from Google Trends. Does the fingerprint
generalise to bitcoin, genomics, uranium, gold?

**Short answer:** attention climaxes are a *feature* of tops, not a *timer*
for them. In 11 real series, 8 of 11 price peaks had a record-and-parabolic
attention spike (CLIMAX) in the 10 weeks before the top. But 18 CLIMAX
episodes fired in total, and the *first* climax of a run usually came early
(price went on to gain a median +27% over 26 weeks). The tops were the
*second or third* climax of a run. Use it to tighten risk, not to sell.

## What the detector does (`backend/app/trends/detector.py`, weekly)

| flag | rule (all ratios, so the 0-100 window scale does not matter) |
|---|---|
| CLIMAX | interest ≥ prior 3-yr max, ≥ 2× trailing-52w median, ≥ 2× its value 4 wks ago, ≥ 10 on the index; price within 10% of 52w high |
| FADING | CLIMAX within 8 wks, 3-wk smoothed interest −35% from the post-climax peak, price still within 15% of the post-climax high |
| DIVERGENCE | price within 3% of 52w high, smoothed interest ≤ 60% of its 52w peak, and that peak was ≥ 80% of the prior record |
| COOLED | CLIMAX within 8 wks, interest −35% AND price −15%: top confirmed, informational |
| stage | on a CLIMAX week: 1 = first climax episode in 52 wks, 2+ = a re-climax on an already-hot run (post hoc, see honesty box) |

Frozen params: `PARAMS` in the module = `params` in `study_results.json`
(gate G1 pins them).

## Data (frozen in `fixtures/`)

11 weekly series, Google Trends worldwide web search (pytrends pull
2026-09-08, the same index DataForSEO serves), paired with the last trading
close inside each Google week (FMP EOD):

silver price ×2 (SLV 2009-13, 2022-26) · bitcoin ×3 (BTCUSD 2015-19, 2019-23,
2022-26) · ARKG, "CRISPR stocks" (ARKG 2019-23) · uranium stocks ×2 (URA
2019-24, 2022-26) · gamestop stock (GME 2019-22) · gold price (GLD 2022-26).

Two bitcoin windows and both ARKG-proxy series overlap in time; they are
different keywords but not independent tops. Effective n of tops ≈ 9.

## Results (`study_results.json`, `charts/`)

### Where the flags fired vs the price top

| series | price top | CLIMAX episodes (stage, wks before top → 26w return, 26w max DD) |
|---|---|---|
| silver 2011 | 2011-04-24 | s1 −1 wk → **−33%, DD −37%** |
| silver 2026 | 2026-01-18 | s1 −14 wk → +57%, DD −7% · s2 −4 wk → **−25%, DD −25%** |
| bitcoin 2017 | 2017-12-10 | s1 −31 wk → +254% · s2 −6 wk → +32%, DD −14% (top 6 wks later, then −56% in the following 26) |
| bitcoin 2021 | 2021-11-07 | s1 −44 wk → −17%, DD −20% (Jan-2021; the May and Nov tops had NO new record: DIVERGENCE fired 2021-04-04 → 26w −8%, DD −47%) |
| bitcoin 2025 | 2025-09-28 | none — retail never showed up; DIVERGENCE 2025-06-22 → 26w −18%, DD −21% |
| ARKG / CRISPR 2021 | 2021-02-07 | ARKG s1 −10 wk → −11%, DD −15% · CRISPR s1 −31 wk → +90% · s2 −9 wk → −9%, DD −20% |
| uranium 2021 | (window top 2024) | s1 Dec-20 → +64% · s2 Feb-21 → +7% · s3 Sep-21 → +0%, DD −22% (the Sprott spike) |
| uranium 2026 | 2026-01-18 | s1 −24 wk → +31% · s2 −2 wk → **−15%, DD −15%** |
| GME 2021 | 2021-01-24 | s1 0 wk → **−50%, DD −88%** |
| gold 2026 | 2026-02-22 | s1 −46 wk → +24% · s2 −28 wk → +51% · s3 −4 wk → **−17%, DD −17%** |

### Pooled outcomes (median; n = episodes)

| after | n | 12w | 26w | 26w max DD | DD ≤ −20% |
|---|---|---|---|---|---|
| all weeks (base rate, 1,816 wks) | — | +5.2% | +10.1% | −9.9% | 30% |
| CLIMAX, all | 18 | +9.1% | +3.5% | −14.5% | 33% |
| CLIMAX stage 1 (post hoc) | 10 | +19.1% | **+27.2%** | −5.0% | 30% |
| CLIMAX stage 2+ (post hoc) | 8 | −2.7% | **−4.5%** | −15.9% | 38% |
| FADING | 8 | −0.5% | +22.1% | −10.7% | 38% |
| DIVERGENCE | 6 | +6.0% | −0.3% | −11.2% | 50% |
| COOLED | 5 | +14.3% | −10.4% | −18.2% | 40% |

Recall: 8/11 price tops had a CLIMAX in the prior 10 weeks; 9/11 had a
CLIMAX or a DIVERGENCE. Stage-2+ climaxes sat 2–9 weeks before the top in
6 of 8 cases (the misses: uranium Feb-21 and gold Aug-25, both mid-run).

### Read-through for the books

- **Silver (the friend's call):** the 2026-01-25 week printed 100 on the
  index as SLV closed the week −19% off the high. The tradable warnings were
  earlier: stage-2 CLIMAX on 2025-12-21/28 at $71/66 (top $93 four weeks
  later, then −25% over 26 wks), and FADING 2026-02-22 at $85 (−40% max DD
  after). The detector would NOT have sold the exact top; it would have
  said "second attention climax of this run, tighten" a month before it.
- **Bitcoin:** the last two cycle tops (Nov-2021, Oct-2025) came with LESS
  attention than the prior spike. CLIMAX is silent there; DIVERGENCE is the
  flag that fired (both → −20% DD within 26 wks). Watch DIVERGENCE on BTC.
- **Genomics:** "CRISPR stocks" stage-2 CLIMAX 2020-12-06 was 9 wks before
  the ARKG top and price only gained 17% more. Sector-theme keywords work;
  single small-cap tickers are index noise (not configured).
- **Uranium / gold:** stage-1 climaxes in 2025 were early by 24–46 weeks
  and price went +30–50%. Stage-3 gold (Jan-26) and stage-2 uranium
  (Jan-26) were the tops.

## Honesty box

- **In-sample.** Every threshold was chosen looking at these 11 series.
  The stage split was noticed AFTER the first run of the study (post hoc);
  it is the hypothesis to test out of sample, not a result.
- **n is tiny**: 18 climax episodes, ~9 independent tops. The stage-2+ vs
  stage-1 gap (−4.5% vs +27.2% at 26w) is 8 vs 10 episodes; a bootstrap
  would not separate them from noise with confidence. Treat as a lead.
- **Weekly closes, MTM.** Forward returns are from the flag week's close.
  Blow-offs move 20–100% inside the 2–6 weeks between the flag and the top;
  the median 26w max *upside* after any CLIMAX is +31%. Selling a CLIMAX
  outright underperformed holding (median 26w +3.5% vs base +10.1%).
- **Look-ahead**: none in the detector (gate G2). The price top itself is
  known only in hindsight and is used here only to measure lead time.
- **Renormalisation**: Google rescales 0–100 per request window; the
  detector is scale-invariant (gate G3) except the noise floor of 10.
  DataForSEO serves the same index; a live 5-year window will not equal
  these fixtures' windows exactly, so live flag dates can differ by a week
  or a level.
- **Not modelled**: daily granularity (the top week is a single bar here),
  transaction costs, the news-search or YouTube indexes, regional splits,
  keyword choice sensitivity (one keyword per asset; "bitcoin price" or
  "buy silver" may lead/lag "silver price").
- **Publication bias**: the sample is famous manias. Attention spikes on
  non-mania assets (a drug approval, an earnings blow-up) are not studied;
  the false-positive rate outside manias is unknown.

## Status and next

Ships OBSERVE-ONLY as **H14** in `HYPOTHESES.md`: an Attention Tops tab and
`/trends`, no score, no call. Promotion needs out-of-sample stage-2+
climaxes: the daily job records flags from 2026-09-08 forward; grade at
n ≥ 20 by the standard gate. Next steps (not done): daily-granularity
overlay (DataForSEO `past_90_days`), a second keyword per asset, and the
non-mania false-positive study.

Counter-agent verdict: `counter_agent_verdict.md` (alongside).
