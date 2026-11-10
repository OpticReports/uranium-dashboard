# The exit_flag lag — what it was, what fixing it is worth

**Reproduce:**

```
python3 research/exit_lag/measure.py \
    ../btc-paper-engine/backend/tests/fixtures/bars_4h_btcusd.csv \
    research/exit_lag
python3 research/exit_lag/charts.py research/exit_lag
```

Frozen output: `results.2026-09-09.txt`, `measure.csv`, `exit_lag.png`.

## The defect

The engine decides a close-based exit at bar N's close and books the fill at
bar N+1's **open** (`core.py` `_process_pullback` sets `pos.exit_flag`;
`resolve_open_exit` closes at the next bar's open). The executor never read
that flag. It closed only once the engine reported **flat**, which happens
when bar N+1 *closes* — a full 4h later.

Live, three for three, every close-based exit on the pullback leg:

| engine booked the exit | reached the venue | lag |
|---|---|---|
| 2026-08-31 16:00 | 20:00 | 4h |
| 2026-09-03 16:00 | 20:01 | 4h |
| 2026-09-09 08:00 | 12:00 | 4h |

Entries landed in **37 seconds**. The asymmetry is the tell: the field
arrived on every 20s poll and was consumed nowhere but test fixtures.

Only the pullback leg can lag. S4/donchian exits solely via its chandelier
trail, which the executor holds as a **resting venue stop order** — it fills
at the venue without the engine's involvement, so it was never late. The
2026-08-19 STOP exit above is the control.

## What the fix is worth

Closing on the flag puts our fill at ~the close of bar N, which is the
engine's own reference price (open of bar N+1). So this is a **tracking-error
correction**, and its per-trade value is a coin flip by construction.

Measured over 4.56y of 4h BTC bars, same engine code path, 124 close-based
pullback exits:

| | |
|---|---|
| affected trades | 124 of 190 (65.3%) |
| mean change per trade | +0.0039% of entry |
| median | +0.0959% |
| stdev | 0.858% |
| mean 95% CI (20k bootstrap) | [−0.146%, +0.157%] — **includes zero** |
| better on | 69/124 (55.6%) |
| best / worst | +3.30% / −2.45% |
| cumulative over 4.56y | +0.478% of leg notional = **+0.105%/yr** |
| at base 25k (pullback leg 3,797 USD) | **+4 USD/yr** |

## Honesty box

- The value is **statistically indistinguishable from zero** and always was
  going to be. The reason to fix it is that we were carrying 4h of market
  exposure the strategy never modelled, on every close-based exit — the
  backtest's equity curve assumed the fill happened at bar N+1's open.
  Reducing unmodelled exposure is the whole claim. Do not read +4 USD/yr as
  a return improvement; read the CI.
- **Not modelled:** slippage is assumed equal at both fill times. It is not —
  the 4h boundary is a liquidity peak, so if anything the *old* fill got the
  better book. One extra hour of funding (~0.00125%/hr) is also ignored, an
  order of magnitude below the price term.
- **Basis:** backtest trade-close prices from the same fixture the engine's
  own tests use, not live fills. n=124 is the whole affected population in
  that window, not a sample.
- The live column of the table above is **verified** (engine `/books/S3/trades`,
  read 2026-09-09); the venue-side clock times come from the executor's own
  event log.
- Fee treatment is identical either way and cancels; it is not in the numbers.

## Counter-agent panel (CLAUDE.md: mandatory before merge)

Five lenses over the diff — branch placement, re-entry state machine, venue
failure modes, accounting/ramp, test quality — each finding then verified.
The placement lens returned two **BLOCKING** findings on the first cut. Both
were reproduced end-to-end independently before being accepted, and each now
has a gate test that fails without its fix.

1. **A venue stop fill on the same poll as the flag halted the whole book.**
   `_close_leg` opens with `_stop_backing()`, and a stop that just fired is
   indistinguishable from a ledger divergence to it (venue flat, ledger still
   long) — so it raised `LEDGER_DIVERGENCE` and demanded a manual `/resume`.
   `_maintain_stop` is the code that absorbs this properly, and the old flow
   always reached it first. The two events are **correlated**, not
   independent: the bar that gaps through the stop is the bar likeliest to
   flip the signal. Same input, both ways:

   | | outcome |
   |---|---|
   | with the flag (first cut) | `halted=LEDGER_DIVERGENCE` |
   | without the flag (old path) | `stop_filled_on_venue`, clean |

   Fixed by absorbing the stop fill before attempting the close.

2. **A refused close left the leg naked.** `_close_leg` cancelled the working
   stop *before* either refusal check ran, so `close_refused_unbacked`
   returned having stripped protection off a leg it had just declined to
   close — and the new branch's early return then skipped stop maintenance on
   every later poll.

   Finding 2's root cause is **pre-existing and live in `35ec560`**: it
   reproduces on the ordinary engine-flat exit path with perfectly healthy
   reads, no `exit_flag` involved, whenever the exiting leg's sign opposes the
   venue net. Fixed at source — `_close_leg` now drops the stop only once it
   is committed to sending the close — which closes it on both paths. The
   blind path already had this invariant pinned by
   `test_gate_B2_close_leg_blind_venue_touches_nothing`; the unbacked path
   broke it.

A third defect surfaced from a panel probe: `_cancel_entry` sent **no cancel
at all** when `order_status` returned `None` (an API failure), while clearing
the reference anyway — leaving a live maker entry resting at the venue that
nothing tracked. Also pre-existing, and contrary to the doctrine the entry
path states for itself ("an unverifiable order is treated as POSSIBLY LIVE").
An unreadable status now resolves toward *sending* the cancel.

The first cut of the fix also re-armed the stop inside the branch after a
refused close. Mutation testing showed that deleting it broke nothing — the
`_maintain_stop` call at the head of the branch already reaches every case,
because a leg that is flat at entry never attempts the close at all. It was
removed rather than shipped as defensive code no test could hold to account,
and the reasoning is recorded where it sat. That is the one place the panel's
proposed fix and the fix that shipped differ.

Mutation-checked: every behaviour above has at least one test that fails when
it is reverted.
