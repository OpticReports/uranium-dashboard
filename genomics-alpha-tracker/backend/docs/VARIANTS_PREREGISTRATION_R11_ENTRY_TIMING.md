# R11-EXEC pre-registration — entry timing & order type

Registered 2026-09-10 BEFORE any result was computed, and BEFORE any change to
live order semantics. Origin (Casey, 2026-09-10): "shouldn't prices be set as
limits, so can be entered anytime during the trading session and still be the
desired trade? ... i don't see why we wait for session opens only, potentially
will ruin exit and entry timings, giving us problems if i am a day late on
entries. i think it should be more dynamic on trading".

House position, stated up front: this study governs LIVE FILL SEMANTICS on a
real-money sleeve. No arm is promoted to live order behaviour on a favourable
point estimate alone; "the current MOO rule is fine" and "limits are worse"
are valid, reportable outcomes. No arm may be added or retuned after results
are seen.

## Operational trigger (why now)

On 2026-09-10 the IB gateway was down from 20:34 ET (2026-09-09) through the
09:25 ET MOO cutoff. The blend3070 entry path has exactly ONE placement window
per session — `entry_window_open()` is false during 09:25-16:00 ET because
MOO/OPG is not placeable intraday — so every entry for that session was missed
outright, with no fallback path. This study measures what that costs and
whether a more continuous entry rule is better or worse.

## What is NOT in question (scope fence)

Exits are already continuous and are OUT of scope: stops rest at the venue as
`STP`/`GTC` and fire any moment intraday; signalled exits go out as `MKT`
intraday. `entry_window_open()` gates ENTRIES ONLY. Nothing in this study
changes exit behaviour.

## A structural gap this study must also measure

The calls book grades from `entry_price` = **the fire-day close** (R2-A entry
convention; `routers/blend.py:232` publishes `entry_ref = c.entry_price`, the
"fire-day close the call's levels were built from"). The live executor fills
at the **next session's open**. The book's reported R therefore starts from a
price the live sleeve never pays. That overnight gap is unmodelled slippage
carried by every live entry to date, and it is measurable here. It is reported
whether or not any arm ships.

## Frozen baseline & measurement basis

The replayable 10y calls book (`backtest_calls_10y` production rows, all 6
flags, net R): 1R = 1% of book equity per call, P&L compounded on exit dates,
2016-2026. Headline: CAGR and maxDD. Measurement basis is trade-close (not
MTM). Exit logic is held FIXED across all arms — only the entry fill changes,
so any difference is attributable to entry timing alone.

Notation: T = fire date (signal computed on close of T). `entry_ref` =
close(T). Trading days only.

## Arms

- **B0 — book convention (reference, NOT shippable).** Fill at close(T). This
  is what the backtest has always assumed. Included solely to size the gap
  against B; it is not executable (the signal does not exist until that close).
- **B — live-current (the null).** Fill at open(T+1) via MOO/OPG. This is what
  the executor does today and what every other arm must beat.
- **L(k) — same-window day limit.** On T+1, a DAY limit at
  `entry_ref x (1+k)`, k in {0, 25bp, 50bp, 100bp}. Unfilled = no trade.
- **D1 — one session late (the outage case).** Fill at open(T+2). This is what
  today's missed window actually produces once the deferred MOO goes out.
- **D1L(k) — late entry with a price band (the proposed fallback).** On T+2, a
  DAY limit at `entry_ref x (1+k)`, same k grid. This is the arm that decides
  whether the late-entry fallback ships.
- **S — skip.** Signals whose window was missed are dropped entirely. The
  honest alternative to entering late, and the correct comparison for D1/D1L.

Exit grading for every arm runs from that arm's realised entry price.

## Fill model and its bias (stated before results)

Daily bars only (`PriceBar.open/high/low`); no intraday tape. A BUY limit at
price L on day d is modelled as: fills iff `low(d) <= L`; fill price =
`min(L, open(d))` (a gap through the limit fills at the better open price).

This is **optimistic**. It assumes any touch of the limit fills, with no queue
position, no partial fills, and no adverse tick at the touch. The bias runs in
FAVOUR of every limit arm. Therefore:

- a limit arm that still LOSES under this model is a robust negative;
- a limit arm that WINS is **not** confirmed by this study alone and requires
  a forward paper test before any live change.

That asymmetry is registered now so it cannot be reinterpreted later.

## Primary ship criteria (frozen)

An arm SHIPS to live order semantics only if ALL hold versus B:

1. CAGR_arm > CAGR_B, AND
2. maxDD_arm <= maxDD_B (DD stored negative; the comparison is on magnitude —
   an explicit guard against the R10 sign-inversion defect), AND
3. Westfall-Young max-T p < 0.05 across the full arm family on the paired
   monthly-cluster bootstrap of book-return differences (4000 draws, seed
   20260910), AND
4. the CAGR edge's sign holds in BOTH halves (2016-2021 / 2022-2026), AND
5. for any limit arm, fill rate >= 80% — an arm that ships by trading much
   less is a different strategy, not a better entry rule.

D1L(k) is judged against **D1 and S**, not against B: its decision is "given
the window was already missed, is a banded late entry better than an unbanded
one, or than skipping?"

## Diagnostics required regardless of ship outcome

- **Entry-slippage census.** Distribution of `open(T+1)/close(T) - 1` across
  all fires, overall and by flag type. Quantifies the B0-vs-B gap above.
- **Decay curve.** Mean and median net R by entry delay (0 / 1 / 2 sessions).
  This is the direct answer to "how bad is being a day late".
- **Adverse selection.** For each k: forward 21d XBI-excess of FILLED versus
  UNFILLED signals. If unfilled signals systematically outperform filled ones,
  the limit is selecting against the strategy — the effect that can make a
  better average fill price coincide with worse P&L. Reported as a signed
  spread with a cluster bootstrap CI.
- **Fill rate** per k, overall and by half.

## Gates (run and recorded BEFORE any result is read)

Registered in response to the R10 finding that gates ran after results (CF-6):
the harness refuses to emit arm P&L until every gate below has written a
PASS/FAIL row.

1. **OHLC coverage gate.** Fraction of fire dates with non-null `open` and
   `low` on T+1 and T+2. `PriceBar.open/high/low` are Optional; an arm whose
   fills depend on missing bars is not evaluable. FAIL below 95% coverage —
   report coverage per year, and treat any excluded fire as an explicit census
   line, never a silent drop.
2. **Alignment micro-test.** Hand-check 10 fires end-to-end: fire date,
   entry_ref, T+1/T+2 bars, modelled fill, graded exit. Any mismatch fails.
3. **Planted-leak detector.** A synthetic arm that fills at the day's LOW must
   show an implausibly high Sharpe; if it does not, the harness is not
   measuring what it claims.
4. **Sharpe > 3 tripwire.** Any arm returning Sharpe > 3 triggers a leak audit
   before its number is reported.
5. **B0-vs-B sanity.** B0 must beat B on average (the fire-day close precedes
   the next open in the signal's direction, on the prior). If it does not, the
   fill plumbing is suspect and results are held.

## Counter-agent verification

Mandatory before any finding is acted on, merged, or presented (CLAUDE.md).
Adversarial review covers data integrity, the fill model, the bootstrap, and
the gate log itself. The verdict is committed beside the results.

## Visual deliverables (Casey standing rule)

Shipped with the summary, not on request: equity curves per arm (log scale,
vs XBI), the entry-delay decay curve with dispersion, fill-rate versus
adverse-selection scatter across k, and the overnight-gap distribution.

## Known limits (stated now, not after)

- Daily bars only: no intraday path, so limit fills are touch-based and
  optimistic, per the fill model above.
- 33-name survivor universe, inherited from the calls book; survivorship is
  not corrected here.
- The fire is computed on close(T) and published to the executor on the
  following cycle; this study assumes the intent set is available before
  open(T+1). Live, that assumption failed on 2026-09-10 — which is arm D1.
- No borrow, commission, or market-impact model. Impact is most likely to
  matter for the small-caps where the limit arms differ most, and is NOT
  modelled: an arm that wins by pennies per share is not a win.
- Options-based entry structures remain out of scope (no historical option
  prices), as in R10.
