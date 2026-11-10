# R10 pre-registration — CAGR-up-DD-flat edge campaign

Registered 2026-09-04 BEFORE any result was computed. Origin (Casey): "improve
the genomics engine CAGR without increasing DD... tests we haven't run...
think outside the box... run them."

House position, stated up front: this campaign runs until its registered arms
are exhausted; "nothing survives" remains a valid, reportable outcome
(R4-R6/R8/R9 precedent). No arm may be added or retuned after results are
seen. The instruction "don't come back until CAGR improved" is honored as
"come back with survivors or with the honest null" — never by fitting until
something looks green (the Unicorn autopsy is the standing exhibit of that
failure mode).

## Baseline & metric (frozen)
The replayable 10y calls book (backtest_calls_10y production rows, all 6
flags, net R): 1R = 1% of book equity per call, P&L compounded on exit dates,
2016-2026. Headline: CAGR and maxDD of that book. An arm SHIPS only if:
CAGR_arm > CAGR_base AND maxDD_arm <= maxDD_base AND Westfall-Young p < 0.05
on the paired monthly-cluster bootstrap of book-return differences (4000
draws, seed 20260904) AND the CAGR edge's sign holds in both halves
(2016-2021 / 2022-2026).

## Book arms (7 + baseline)
- A1a size-gate: skip catalyst-flag entries (quiet/pullback-into/binary-event)
  when PIT mktcap < $1B. A1b: also skip when mktcap unknown.
  TAINT DISCLOSURE: derived from R9's diagnostic ON THESE SAME FIRES; judged
  PRIMARILY on the 2022-2026 half (quasi-holdout; imperfect, stated).
- A4a/b/c run-up harvest: catalyst-flag calls' expiry tightened from PCD-1 to
  PCD-N trading days, N in {3,5,10}; stop/target hits before the truncation
  date keep their original exits; later exits become truncation-date close.
  Prior: documented pre-event run-up given back (Rothenstein 2011; our
  asymmetry study).
- A2v slip veto: skip any entry when the symbol logged a >=2-month PCD slip
  in the prior 60 days (PIT registry store).
- A5 financing veto: skip entries when PIT runway < 2 quarters (filing-dated).

## Event studies (promotion track, not book arms)
- A2 registry-revision events (PIT store census: 409 slips >=2mo / 113
  pull-ins <=-2mo / 34 status downgrades; dense 2021+): forward 5/21/63d
  XBI-excess from the first bar after the revision date; events within 5d of
  a prior same-symbol event excluded; split small/large ($10B). Inference:
  symbol|month cluster bootstrap; WY across the event-study family.
- A3 post-readout drift: resolution day = first bar with |1d move| >= 15%
  within [PCD-5, PCD+10] of a catalyst-flagged trial; forward 21/63d
  XBI-excess by resolution direction.
Promotion to a live candidate flag requires: WY p < 0.05, >= 8 contributing
symbols, leave-one-symbol-out sign-stable. Otherwise DIAGNOSTIC.

## Gates (before results are read)
Alignment micro-test (hand-checked forward returns), planted-leak detector,
census tables per arm (fires removed/kept, events per symbol/year), and the
Sharpe>3 leak-audit tripwire. Counter-agent verification before presentation;
verdict committed beside results.

## Known limits (stated now)
33-name survivor universe; slip density is 2021+ so A2 is effectively a
5-year test; A1/A4 taint as above; options-based structures (the asymmetry
study's straddle lane) are OUT of this round - no historical option prices,
paper-engine forward test is their instrument.
