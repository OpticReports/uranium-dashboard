# Counter-agent verdict — Google Trends attention-top study + detector (2026-09-08)

Reviewer: adversarial counter-agent pass per repo convention. Every number below was
independently recomputed from `fixtures/*.json` with my own re-implementation of the
CLIMAX rule (as written in the doc's table) and of the forward-return / max-DD
measurement — NOT by re-running `run_study.py`. Script: scratchpad `counter/recompute.py`.

## 1. Data integrity

Pairing convention claimed: interest for the Google week starting Sunday S is paired with
the close of the last trading day ≤ S+6. Spot-checked against calendar anchors:

| series | week (Sun) | fixture close | independent anchor | verdict |
|---|---|---|---|---|
| silver_2011 | 2011-04-24 | 46.88 | SLV 4/29/2011 close ≈ 46.88; spot ~$48.6 (SLV/spot ≈ 0.965) | match |
| silver_2011 | 2011-04-17 | 45.535 | Thu 4/21 close (Good Friday 4/22 closed) | match, holiday handled |
| bitcoin_2017 | 2017-12-10 | 19,650 | Sat 12/16 close ~$19.5–19.7k (ATH intraday Sun 12/17) | match; crypto week ends Saturday |
| gme_2021 | 2021-01-24 | 81.25 | Fri 1/29 close $325 ÷ 4 (2022 split) | match, split-adjusted |
| gme_2021 | 2021-01-17 / 01-31 | 16.25 / 15.94 | $65.01 / $63.77 ÷ 4 | match |
| arkg_2021 | 2021-02-07 | 112.01 | ARKG closing-high week, ~$112 on 2/12/2021 | match |
| bitcoin_2021 | 2021-11-07 | 64,400 | Sat 11/13 close ~$64.4k (ATH 11/10) | match |
| all 11 | — | — | every date is a Sunday, 7-day spacing, no gaps; window-edge partial weeks are `None` (correct) | clean |

- No off-by-one: the GME squeeze week (Jan 27–28) carries the $325 close, not the prior
  Friday's $65. Simulated a one-week price misalignment anyway: 17/18 CLIMAX episodes
  unchanged (uranium_2024 s2 moves 2026-01-04 → 01-18) and every stage-2+ lead time shifts
  by exactly −1 week. So even a pairing slip would move "weeks before top" by one, not
  change the story. None exists.
- 2025–2026 rows (silver $93, gold $445, uranium $50) are beyond what I can verify
  externally; they are internally consistent (silver 2026-01-25 week = 100 on the index,
  close 75.44 = −19% off the 92.91 peak, as the doc says).
- Closes are split-adjusted (GME) but dividend handling is unstated; URA/ARKG/XBI pay
  distributions, so forward returns there are price returns, slightly understated. NIT.

## 2. Independent recomputation

Rule re-implemented from the doc table alone (record ≥ prior 156-wk max with ≥ 52 prior
weeks; ≥ 2× trailing-52w median excl. t; ≥ 2× value 4 wks ago; ≥ 10; price ≥ 0.9 × 52w
high with ≥ 26 valid closes; 8-week episode merge; stage = 1 + prior episode starts within
52 wks). It reproduces every flag date and stage in `study_results.json`.

| quantity | claimed | recomputed | note |
|---|---|---|---|
| CLIMAX episodes / stage-1 / stage-2+ | 18 / 10 / 8 | 18 / 10 / 8 | exact |
| recall: climax within 10 wks of price peak | 8/11 | 8/11 | exact (misses: bitcoin_2021, bitcoin_2025, uranium_2021) |
| base weeks | 1,816 | 1,816 | exact |
| base r12 / r26 / dd26 / DD≤−20% | +5.2 / +10.1 / −9.9 / 30% | +5.1 / +10.1 / −9.9 / 30% | r12 differs by row rounding only |
| CLIMAX r12 / r26 / dd26 / DD≤−20% | +9.1 / +3.5 / −14.5 / 33% | +9.0 / +3.4 / −14.5 / 33% | study rounds rows to 0.1 before the median (9.05, 3.45) |
| stage-1 r12 / r26 / dd26 / up26 | +19.1 / +27.2 / −5.0 / +47.4 | +19.1 / +27.2 / −5.1 / +47.3 | rounding |
| stage-2+ r12 / r26 / dd26 / up26 | −2.7 / −4.5 / −15.9 / +24.2 | −2.7 / −4.5 / −15.9 / +24.3 | rounding |
| CLIMAX up26 median | +31.1 | +31.2 | rounding |
| per-event table in the doc (all 18 rows) | — | all 18 match to the quoted precision | e.g. silver-11 −33/−37, GME −50/−88, gold s3 −17/−17 |
| "stage-2+ sat 2–9 wks before the top in **6 of 8**" | 6/8 | **5/8** | lead times [−170, −139, −28, −9, −6, −4, −4, −2]; three misses (uranium Feb-21, uranium Sep-21, gold Aug-25), not two |
| detector docstring: stage split "found on seven episodes" | 7 | 8 stage-2+ | stale count |
| HYPOTHESES.md H14 numbers | s2+ −4.5/−15.9, s1 +27.2/−5.0, base +10.1/−9.9 | same | match |

Only real discrepancy: the "6 of 8" sentence (and its "two misses" list) — the study's own
`weeks_to_price_peak` list says 5 of 8. The 6th hit only exists if uranium Sep-21 is
measured against the Nov-2021 *local* top (8 wks later) instead of the study's window
top (May 2024). That is a definition the doc does not use elsewhere; pick one and fix.

## 3. Look-ahead audit

`detector.compute`, line by line:
- `prior = vals[lo:t]` — excludes t. Record is vs strictly prior weeks. OK.
- `med = median(vals[t-52:t])` — excludes t. OK. `back = vals[t-4]`. OK.
- `ph52 = max(px[t-51:t+1])` — INCLUDES t. Not a look-ahead: the week-t close is known
  when the week-t interest is; including t just makes `price_ok` trivially true on a
  new-high week, which is the intended semantics ("attention record while price is at/near
  highs"). Excluding t would wrongly fail the condition on the very week price breaks out.
- FADING/COOLED: `sm[last_climax:t+1]`, `px[last_climax:t+1]` — ≤ t. Stage uses
  `climax_starts[:-1]`, which correctly excludes the current episode whether it is new or a
  continuation. DIVERGENCE: `sm[t-51:t+1]`, `rec` (prior) — ≤ t. Gate G2 confirms
  truncation-invariance at 5 points × 3 series.
- One timing caveat NOT in the honesty box: the Google week is final only after Saturday;
  the equity close used is Friday. The earliest executable price for an equity flag is
  Monday. Sensitivity (enter one week later, 25w horizon): stage-2+ r26 −4.5 → −2.9, dd26
  −15.9 → −16.3 (robust); stage-1 r26 +27.2 → **+45.2** (GME flips −50% → +153%). The
  stage-2+ read survives; the stage-1 "early" read is tail-driven.
- `run_study.py` base rate = weeks 52..n−27 with full 26w windows. Flags can only fire at
  t ≥ 52 (record needs 52 prior weeks; DIVERGENCE needs `rec`), so warm-up matches. Flag
  rows CAN sit inside the last 26 weeks: `fwd` returns None (dropped from r26) but `maxdd`
  /`maxup` silently compute on a truncated segment (biased toward 0) and are still pooled.
  Today no flag row is truncated (latest flag 2026-02-22, series end 2026-09-06), so no
  number is affected — but nothing guards it; the next re-freeze could pool a 10-week DD as
  a 26-week one. SHOULD-FIX.
- The price top (`ip`) is hindsight and used only for lead time / recall, as stated. But
  `ip` = window max, which for uranium_2021 is the May-2024 window edge (URA 32.65 vs the
  Nov-2021 local top 30.14). The "recall miss" there is an artifact of the window choice,
  and the uranium_2021 lead times (−179/−170/−139) are meaningless. Recall is 8/11 under
  the study's rule and 9/11 under a local-top rule; say which.

## 4. Statistical honesty

- Stage-1 vs stage-2+ (10 vs 8), 26w return: median gap +31.7 pts; permutation test on
  the 18 rows p = 0.36; Mann-Whitney U = 48, p = 0.48. 26w max DD: gap 10.8 pts, p = 0.30 /
  0.59. 12w: p = 0.29 / 0.33. Bootstrap 90% CI of the r26 median difference:
  **[−17, +72]**. Indistinguishable from noise, as the honesty box says.
- H14's own promotion gate applied in-sample: stage-2+ with dd26 worse than base median
  = 6/8, Wilson-95 lower bound 0.41 (< 0.50). Stage-1: 4/10. The gate is set at n ≥ 20 out
  of sample, which is right; the in-sample record would not pass it.
- Effective n is smaller than "≈ 9". silver_2026 and uranium_2024 top the SAME week
  (2026-01-18), gold_2026 five weeks later, bitcoin_2025 four months earlier — one macro
  episode. With the two-bitcoin and ARKG/CRISPR overlaps, independent tops ≈ 6–7. The
  base rate also double-counts: ARKG's price series enters twice (arkg_2021 and
  crispr_2021 share it) and bitcoin 2022-06..2023-06 appears in two windows.
- Sampling noise: Google Trends values differ by a few points between pulls. With ±2
  uniform jitter on interest, 88% of CLIMAX episodes and 81% of stage-2+ labels survive;
  at ±3, 82% / 76%. Gate G1 pins ONE pull; a live DataForSEO series will not reproduce
  these flag dates exactly (the doc says so — good — but the magnitude is worth stating).
- Doc wording: "Selling a CLIMAX outright underperformed holding (median 26w +3.5% vs base
  +10.1%)" conflates two statements. Holding after a climax returned +3.5% (so selling
  gave up 3.5 pts); the base +10.1% is a different comparison (post-climax weeks are
  worse than average weeks). Rewrite as two sentences.
- Honesty box otherwise adequate: in-sample, post hoc, tiny n, MTM basis, publication bias
  all stated in one line each. Add the four items above (timing, effective n ≈ 6–7, base
  double-count, noise sensitivity) and correct "6 of 8".

## 5. Code review findings

**BLOCKING** — none.

**SHOULD-FIX**
1. `ingestion/trends.py` docstring: "A keyword already refreshed today is skipped, so a
   restart never double-spends" is false. `_FETCHED`, `_BUDGET` and `_BREAKER` are all
   in-process, and `scheduler.py` fires an immediate first run at startup, so every
   restart/redeploy re-fetches all 8 keywords ($0.072) and resets the daily cap. A
   crash-loop is bounded only by restart frequency. `TrendPoint.fetched_at` is already
   stored: dedupe on `max(fetched_at)` per keyword from the DB (skip if fetched this UTC
   day) — a five-line change that makes the docstring true.
2. Breaker code set `(401, 402, 403, 40100, 40200)` is brittle. DataForSEO returns HTTP 200
   with task-level codes: 40200 "Payment Required" but ALSO **40210 "Insufficient Funds"**,
   40201 (access paused), 40203 (cost limit), 40204 (subscription required), 40207 (IP not
   whitelisted), 40104 (account not verified) — none trip the breaker; each falls to
   `continue`, so all keywords retry every run (no cost — failed tasks are not billed — but
   the 24h pause the docstring promises for "no funds" never happens). 40202/40209
   (rate limit) also deserve a short breaker. Match on `status // 100 in (401, 402)`
   (plus HTTP 403), not exact codes.
3. `run_study.py`: guard `maxdd`/`maxup` (and pooled rows) to require the full horizon,
   or set them None when `i + h >= len(close)` like `fwd` does. Currently unaffected;
   silently wrong on the next re-freeze.
4. Doc/docstring corrections: "6 of 8" → 5 of 8 with three misses; detector docstring
   "seven episodes" → eight; add the Section 4 caveats.

**NIT**
5. Partial current week: DataForSEO's last point is the in-progress week (`missing` /
   partial). Router pairs it with whatever close exists so far (BTC: Sunday's) and the
   detector treats it as a full week; `summary.state` can therefore flip during the week.
   Either drop the last point when `missing` is set or label `asof` as partial.
6. `config/trends.yaml` ships three keywords never in the study (ethereum, biotech
   stocks, gene therapy) and uses ARKG as proxy for two keywords. Fine for observe-only,
   but H14's out-of-sample count should say whether these count toward n ≥ 20.
7. Credential paths: `auth=(login, password)` goes to httpx only; logs print keyword,
   status code, `redact(str(exc))`; `/health` and `/trends/status` expose booleans only.
   No leak found. `redact` would not catch a login echoed in a DataForSEO
   `status_message`, which the API does not do. OK.
8. Router `_weekly_closes` (`bisect_right(dates, ws+6d)`, require `dates[j] >= ws`) is the
   same convention as the fixtures (Friday for equities, Saturday for BTC). Consistent.
9. `replace_series` delete + insert + single commit: a mid-insert failure rolls back the
   delete, so the previous series survives. Short (<52) responses keep the old series.
   `_spend()` increments before the fetch, so a thrown fetch still consumes a cap slot
   (conservative). OK.

## 6. Verdict: SAFE AFTER CORRECTIONS

Gate tests: `tests/test_trends_detector.py` + `tests/test_trends_lane.py` — **32 passed**.
Mirror `config/trends_study_frozen.json` identical to `docs/trends_peak/study_results.json`.

The detector has no look-ahead, the fixtures are correctly paired, and every headline
number reproduces from an independent implementation. Observe-only shipping (no score, no
call) is appropriate. Required before the doc is quoted or H14 is graded:

1. Fix "6 of 8" → "5 of 8" (misses: uranium Feb-21, uranium Sep-21, gold Aug-25) in
   `TRENDS_PEAK_STUDY.md`, or define the local-top rule and apply it everywhere
   (which also makes recall 9/11). Fix "seven episodes" in `detector.py`.
2. Honesty box additions: Friday-close vs Saturday-final-week timing and its stage-1
   sensitivity; effective independent tops ≈ 6–7 (Jan-2026 cluster); base rate
   double-counts ARKG and BTC 2022–23; ±2-point sampling jitter moves ~1 in 5
   stage-2+ labels.
3. `ingestion/trends.py`: DB-backed per-day dedupe (`fetched_at`), and range-based
   breaker matching that catches 40210/40201/40203/40204/40207. Then the docstring's
   "never double-spends" is true.
4. `run_study.py`: None out `maxdd`/`maxup` when the 26w window is truncated.
