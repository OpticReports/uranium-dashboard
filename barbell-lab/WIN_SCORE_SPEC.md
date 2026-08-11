# Per-position win scores — pre-registered spec

Frozen 2026-08-11 BEFORE the table was computed. Conventions below are
fixed; a change is a new study reported alongside this one. Basis: the
2026-08-11 referee report that validated the phase-conditional path
(tracks base rate ±9pp in every 5y block since 1975; no bearish tilt) and
confirmed the false-precision hazard (today's cell = 20 episodes behind a
±5pp-looking month count).

## Definitions (frozen)

- WIN: asset sleeve's total return beats CASH (TB3MS) over the horizon.
- Horizons: 6m and 12m.
- Conditioning: the phase label from the phase-barbell study's tiered,
  publication-lagged labels (research/phase_barbell.py::labels), months
  1935→. Phase-conditional ONLY — the analog-conditioned variant is NOT
  scored (two-sided error record; the analog panel already carries its
  own caveats).
- Assets: stocks, bonds, gold (gold post-1971 only).
- Estimator: historical hit rate over all months carrying the label whose
  outcome window is closed. Reported BOTH ways:
  - month-counted: wins / months;
  - episode-counted: episodes are maximal runs of same-label months where
    consecutive members are <= 12 months apart; the episode's outcome is
    the outcome AT ITS FIRST MONTH (the month a decision-maker would
    first have acted on the label).
- Interval: Wilson 95% on the EPISODE counts (the honest sample size).
- Base rate: unconditional hit rate over all months with closed windows,
  same data. Every displayed score shows the delta vs base rate.
- Data: the frozen phase-barbell fixture (research/fixtures/
  phase_data.json — Shiller monthly-average total-return convention,
  synthetic validated bonds; captions must carry the convention note).

## Evaluation (already run by the independent referee, 2026-08-11)

Walk-forward from 1975 the phase-conditional equity score tracked its
base rate (full-sample delta +0.3pp; max |block delta| ~9pp) and showed
no 2023-26 bearish tilt (+4.1pp above base). This spec ships the score as
DESCRIPTIVE CONTEXT, not a forecast; the standing sentence "conditional
win rates are descriptive statistics of a small number of historical
episodes, not forecasts" is mandatory on the panel.

## Display rules (fiduciary)

Each position card: win % (episode-counted headline), "N of M episodes",
Wilson interval, month-counted rate, base rate with delta, one-line
driver. No composite 0-100 scores. Sector sleeves are out of scope until
sector data with >= 4 episodes per cell exists.

## Ship gates

Table recompute-parity from the fixture (served constants == recomputed),
Wilson formula pin, episode-chaining pin, closed-window-only pin (no
outcome window may extend past the fixture edge), display-field presence,
and the mandatory caveat sentence. Counter-agent verification of the
computed table BEFORE the cards ship.

## ADDENDUM: industry-level win scores (frozen 2026-08-11, before computation)

Owner request: sector granularity a la the Zeberg industry list. SPDR ETF
data (1999->) spans ~3 recessions - exactly the fake-sample-size hazard
this spec exists to avoid - so industries use the Ken French 12-industry
VALUE-WEIGHTED monthly portfolios (1926->, CRSP; NoDur, Durbl, Manuf,
Enrgy, Chems, BusEq, Telcm, Utils, Shops, Hlth, Money, Other), aligned to
the same 1935-01 start and identical conventions as the asset table: win =
industry total return beats CASH (TB3MS) over 6m/12m; same episode
chaining, first-month outcome, Wilson-95 on episodes, month + episode
rates both displayed, per-industry month-counted base rate. -99.99/-999
are missing and disqualify a window. Display: all 12 industries ranked by
month-counted edge vs own base for the CURRENT phase, episode counts
always visible; cells with < 4 episodes print "insufficient episodes".
Modern SPDR tickers shown as approximate reference mapping only (NoDur~XLP,
Durbl/Shops~XLY, Manuf~XLI, Enrgy~XLE, Chems~XLB, BusEq~XLK, Telcm~XLC,
Utils~XLU, Hlth~XLV, Money~XLF; Other unmapped) - NOT tradeable parity.
Same ship gates (recompute parity, conventions) + independent verification
of parsing and a sample of cells before the panel goes live.
