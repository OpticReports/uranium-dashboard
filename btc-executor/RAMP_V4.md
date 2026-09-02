# RAMP v4 — coverage-gated scaling (frozen 2026-08-15)

Supersedes the v3 "4 trades + cum P&L ≥ 0 per rung" ramp. Rationale,
measured: 4 trades of a ~53%-win strategy is a coin flip — the old gate
could pass a broken system and fail a working one, and it put months
between rungs without adding safety. The edge itself is verified only by
the paper track + edge-monitor over years (MinTRL ≈ 2y, measured); the ramp
verifies MECHANICS, and mechanics are per-event proofs, not per-week ones.

## The gate: event-coverage matrix (pre-registered)

Advance past ramp stage 0 only when every row is met, evidenced by the
executor's own coverage counters (`/status.ramp_v4.rows[*].have`, backed by
`coverage_live` in persisted state, incremented inside the real code paths
— never by hand). **Read `ramp_v4.rows`, not `/status.coverage`:** the
latter is the all-modes total and includes dry-run events, which do not
satisfy any row (see the mode guard below):

| event class            | required | how it can be produced            |
|------------------------|----------|-----------------------------------|
| entry_long             | ≥2       | organic only (real limit-entry path) |
| entry_short            | ≥2       | organic only                      |
| stop_placed            | ≥2       | organic or drill (same venue path)|
| stop_filled            | ≥1       | drill `stopfill` or organic       |
| signal_exit (leg close)| ≥2       | organic only                      |
| chase                  | ≥1       | organic (entry_chase)             |
| post_only_cross        | ≥1       | organic short at positive basis   |
| restart_with_position  | ≥1       | organic redeploy with a leg open (the 2026-08-15 proof predates the mode guard — unattributed, must be re-earned live) |
| config_change detected | ≥1       | any env change redeploy           |
| halt + resume          | ≥1 pair  | operator-triggered manual test    |
| drill_cycle complete   | ≥3       | drill                             |
| slippage sample        | ≥10 fills| any LIVE fill (drill fills count — they are real fills), **VOID fills excluded**. 10 = the slip-CUSUM's arming threshold, NOT a size test; see "Slippage: right diagnosis, wrong prescription" (2026-09-02) |

**Void fills (2026-08-26).** A fill whose `|slip_bps| > 500` is marked
`void` at boot and never counts toward the slippage sample — the phantom
incident produced two such rows (1320bps against a days-stale reference,
one for an execution that never happened at all), and a sizing gate fed by
fictitious slippage authorizes size on evidence that does not exist. The
exclusion lives in the two GATING readers, `mirror._live_fill_count()`
and `main.py`'s `n_live`, and they MUST stay identical: they diverged once,
and auto-drill then read a real 8/10 as complete while `/pulse` showed 8. A
gate whose readers disagree is not a gate. (barbell-lab's
`edge/adapter_coinbase.py` filters voids too, but it feeds the edge monitor,
not this gate. `_ramp_v4`'s `all_modes = len(fills)` deliberately does NOT
filter — it is the all-modes total, and `met` never reads it.) Already-ingested rows downstream
(barbell-lab `edge_trades`, and any `slip_norms` frozen from them) are NOT
cleaned by this filter — that purge is tracked separately.

**Auto-drill is bounded** by `DRILL_NO_FILL_MAX` (3): a drill can report
`ok` and still advance the sample by zero (venue omits
`average_filled_price`, or `mid()` is 0 so the fill watch never queues).
On Hyperliquid the first case was not an edge case but the STEADY STATE
(found 2026-09-01): the venue's orderStatus payload carries no average
fill price at all, so every fill resolved FILLED/None, `_record_fill`
dropped it, and the watch was consumed in the same pass - the sample sat
at 0 through the entire go-live. `hl.order_status` now resolves the
price from `userFills` (size-weighted across partial prints, cached 10s;
a reconstruction short of the known filled qty is rejected so a stale
snapshot can never record a wrong average), and a FILLED watch with no
price is KEPT and retried (`fill_px_unresolved` once, `fill_px_resolved`
when it lands, `fill_px_lost` at 48h). A drill whose watches are still
price-pending is scored `drill_sample_pending`, NOT as a no-fill strike.
Known limits of the loud-loss guarantee (counter-agent 2026-09-01), all
pre-existing to this fix: the watch queue is in-memory, so a deploy
restart drops pending watches without an event; a watch still OPEN at
48h (a long-resting stop) ages out silently; and a partial fill on a
CANCELLED order is consumed without a sample.
Three consecutive no-sample drills disable auto-drill with an ACTION page
rather than spending the daily budget into a row that can never close. Any
drill that DOES record a fill resets the counter — including a sample
that lands on a later poll.

Honesty note: drills deliberately do NOT count toward entry/exit/chase
coverage — drill entries are market orders, organic entries go through the
limit + post-only + chase machinery, and only the real path proves the real
path. Drills own what organics produce too rarely: the stop lifecycle and
the slippage sample. Organic entry cadence (S3+S4 ≈ 2–4 signals/week)
completes the rest in ~2–3 weeks.

Slippage sanity gate: |mean slip| < 15bps (computed in `main._slip_sanity`,
published as `/status.ramp_v4.slippage_sanity`; prose-only until 2026-09-02)
and no slip-CUSUM alarm (edge-monitor). P&L is explicitly NOT a gate at any
stage.

### Slippage: right diagnosis, wrong prescription (amended 2026-09-02)

**The row keeps its ≥10 bar. Its stated RATIONALE was wrong, and that is
what changed.** Casey challenged the row as "a stupid test at this size."
He was right about the premise and wrong about the remedy, and so was the
first draft of this amendment, which proposed dropping the bar to 3 and was
REJECTED by counter-agent review (3 of 4 lenses REJECT).

**What the measurement established** (`scripts/book_depth_probe.py`; one
dated run frozen alongside it as `book_depth_probe.2026-09-02.txt`): the row was written to mean "prove execution cost before
trading larger," which only gates size if execution cost RISES with size.
At the sizes actually in front of the ramp it does not. Across 20 snapshots
of the live HL BTC-PERP book, a $151 order (KELLY_M 0.135) and a $281 order
(KELLY_M 0.25) filled at the best offer in 20/20, both sides, impact
identical to each other and equal to half the spread. The one elevated
reading was elevated identically at both sizes because the SPREAD widened —
a size-independent term. So a slippage sample at pilot size cannot license
a larger size, and a sample at the larger size would not either.

**Measurement honesty (counter-agent, and it corrects the first draft).**
The first draft published a table claiming flat impact out to $250k. It
does not reproduce and it is withdrawn. Three things were wrong with it:
"0.06 bps" is exactly HALF THE SPREAD (spread 0.13 bps = $1 = one tick), so
the figure is a binary did-the-order-fit-at-best-offer indicator, not an
impact curve, and its flatness is tick quantization rather than measured
depth resilience; HL's `l2Book` returns exactly 20 levels spanning ~3 bps,
so "depth within 3 bps" was just the whole truncated API response; and the
large-size cells were a single favourable draw — re-probing put $250k
anywhere from 0.065 to 2.28 bps and visible depth as low as $305k, with
top-of-book notional swinging ~400x across 3 seconds in a calm tape. The
claim that survives is narrow and sufficient: **at $151 and $281 the cost
is the spread, on both sides, in every snapshot taken.** Nothing here is
evidence about a stressed tape, which is exactly when stops fill.

**Why the bar stays at 10 anyway — the reason nobody had noticed.**
`MIN_SLIP_TRADES = 10` in `barbell-lab/src/barbell/edge/layers.py`: the slip
CUSUM reports `insufficient` below 10 observations AND freezes its norms
from the first 10. Ten is not an arbitrary sample-size guess; it is the
HANDOFF POINT to the continuous detector. Dropping it to 3 would have
disarmed the very control the first draft nominated as the real one, in
precisely the window where size would increase — 3 fills to arm a monitor
that needs 10. The number survives its own falsified rationale. **Change it
only together with `MIN_SLIP_TRADES`**, which the gate tests now enforce
across both repos.

**And the sanity gate it leaned on did not exist.** This document has cited
"|mean slip| < 15bps" as a gate since 2026-08-15. It was PROSE ONLY: the
ramp readout computed a fill COUNT and never once looked at `slip_bps`, so
a book could show 13/13 with every fill 40 bps adverse and no surface
anywhere would say so. It is implemented now (`main._slip_sanity`), reads
the same live/non-void population the count reads, is False on an
unmeasured book, and `/status.ramp_v4` publishes `slippage_sanity` plus
`advance_ok` = every row met AND slippage sane. **A gate named in the spec,
believed by the operator, and absent from the code is worse than no gate.**

**What this row actually proves**, stated honestly now: that fill capture
works end-to-end on the real venue (it did not — the sample sat at 0 from
the Hyperliquid cutover until 2026-09-01 while every surface looked
healthy), that no reference defect is inflating slip (the two void fills
were 1320 bps of broken reference, never market impact), and that the
continuous detector has enough calibrated observations to arm. It is not,
and never was, a proof about size.

**Nothing was weakened.** `entry_short` (≥2), `signal_exit` (≥2),
`drill_cycle` (≥3), `stop_filled` (≥1) are unchanged — size makes a DEFECT
expensive even where it does not make execution expensive, and the short
path has fired ONCE in this system's history. `RAMP_V4_REQUIRED` is now
pinned in full against a frozen dict, so no row can drift unnoticed.

Cost of the correct answer, measured rather than asserted: post-fill-fix,
10 fills is ~5 auto-drill cycles at 1h spacing inside a 6/day budget —
about 5 hours and $8–10 of spread and fees. The first draft's urgency
argument ("the row was the long pole for weeks") expired on 2026-09-01 when
capture was fixed, one day before it was written.

**Follow-on refused in advance.** The template this amendment establishes —
"measurement falsified the row's premise" — points next at `entry_short`,
and drill variants that route the real limit path now exist. Crediting
drills toward `entry_short` would be the actual unlock and is refused: only
the real path proves the real path (see the honesty note above).

Follow-up identified, not implemented: measured slip is dominated by the
reference-snapshot → order-send gap, so the lever for better execution is
shortening that gap, not sampling more.

### Mode guard: live-mode evidence only (amended 2026-08-21)

Every row above is satisfied by **`coverage_live`** — events produced with
`DRY_RUN=false`. `_cov()` keeps two tallies: `coverage` (all modes, the
audit trail) and `coverage_live` (what the gate reads). `/status.ramp_v4`
reports `have` (live), `all_modes`, and `unattributed` per row, plus
`unattributed_total`.

Why: the matrix exists to prove **venue** mechanics. A drill or organic
event in dry-run exercises the state machine against `DryRunVenue` and
proves nothing about Coinbase — but it incremented the same counter, so a
full matrix could read `coverage_complete: true` having never placed an
order. The 2026-08-10 blueprint sync (which silently reset `DRY_RUN` to
true on a LIVE account) is precisely the flip that produces this: the
executor keeps reporting healthy while every subsequent "proof" is
synthetic.

Fills carry the same tag — a `DryRunVenue` fill price is synthetic, so the
slippage sample counts live fills only.

**Counter-agent verdict (2026-08-21): CONFIRMED.** Differential and
mutation testing (8 weakening mutations, all caught) established the two
edited ramp tests are strictly stronger, not relabelled; an end-to-end
adversarial run accumulated 51 dry-run events through the real paths
(organic entries both sides, halt/resume, config_change, 4 drills) and
still produced `coverage_complete: false`, `coverage_live: {}`. Five
defects were raised and all five are fixed here: `_ramp_v4` shape-hardened
(a corrupt state file 500'd `/status` AND the public `/pulse`, blinding
monitoring — regression, now pinned); `coverage_live > coverage` marked
`corrupt` and never `met`; `_is_live()` ties evidence to the venue OBJECT
so a regressed `_build_executor` cannot accrue live counts against a
shadow book; this spec's own table corrected (it still pointed operators
at `/status.coverage`); and the provenance reset now emits a WARN event
plus `ramp_v4_unattributed` on `/pulse`.

### One-shot attestation (`POST /coverage/attest?confirm=true`)

For the single migration where counts were genuinely earned live but
predate provenance recording, a token-gated one-shot promotes `coverage`
into `coverage_live`. It is a deliberate hole in the guard, so it is
bounded hard. Refusals:

| refusal | meaning |
|---|---|
| `already_attributed` | one-shot; keyed on the `attestation` record, never tops up later evidence |
| `not_live` | not live at call time — checks the DRY_RUN flag AND the venue object |
| `mode_flips_recorded` | the durable flip counter is non-zero |
| `dryrun_fills_in_state` | state holds fills tagged `live: false` |
| `mode_change_in_log` | a flip is still visible in the retained event log |
| `live_evidence_predates_call` | `coverage_live` holds counts from an earlier process — the migration window has passed |
| `nothing_to_attest` | no positive-integer pre-split counts to promote |
| `persist_failed:*` | rolled back; safe to retry |

**Why the bounds read durable state, not the event log** (counter-agent
2026-08-21, verdict FATAL on the first cut): the log retains 200 entries
and rate-limited conditions fire every poll, so a `mode_change` ages out in
roughly **67 minutes of ordinary operation**. A refusal that only scanned
events therefore self-cleared on a timer — no override needed, just
patience. The load-bearing witnesses are now `mode_flips` (monotonic,
persisted) and dry-run-tagged fills; the log scan is kept only as a third
signal. Flip detection also runs at `__init__`, not just inside `step()`,
because a flip across a redeploy would otherwise never be recorded before
an operator could act.

**The first migration cannot be witnessed, and says so.** `witnessing_since`
records when durable provenance tracking began; counts that already existed
at that instant are frozen into `unwitnessed_coverage`. Every refusal above
is blind to that period by construction — `mode_flips` was not tracked and
fills were not mode-tagged while those counts accrued. Promoting them
therefore requires `acknowledge_unwitnessed=true`, an explicit operator
judgement recorded permanently in the attestation record
(`operator_acknowledged_unwitnessed`, `unwitnessed_rows`). The stamp is
frozen across restarts, so a reboot cannot launder unwitnessed history into
witnessed history. Counts earned after `witnessing_since` are covered by
the durable checks and need no acknowledgement.

**Attestation can never complete the matrix.** `slippage_sample` reads
per-fill `live` tags, is not attestable, and gates `coverage_complete` —
so 10 genuinely live fills are still required no matter what is attested.

Promoted counts are the pre-split DELTA only; anything observed live in
the current process stays observed. They persist in `coverage_attested`
and every affected row renders `"attested": N` alongside `"observed": N`:
**attested is weaker evidence than observed, and the matrix keeps saying
so.** `/pulse` carries `ramp_v4_attested` so the drop of
`ramp_v4_unattributed` to zero is never silent. The promotion emits a WARN
event and runs under the venue lock (it was the only `_save_state` writer
outside it, which could publish a torn ledger mid-step).

Operational note: an open leg at deploy fires `_cov("restart_with_position")`
inside `__init__`. That is expected and does NOT foreclose attestation —
only live counts from an *earlier* process do.

Counts persisted **before** this amendment have no provenance recorded.
They are therefore treated as `unattributed`: visible in `all_modes`,
never credited to a row. They must be re-earned live. This is deliberately
the conservative direction — the alternative is granting the gate evidence
it never actually had.

## Drills (the accelerator)

Token-gated `POST /drill?kind=cycle|stopfill` — one deliberate min-size
(1 contract, 0.01 BTC) round trip through the REAL live code paths:

- `cycle`: market entry → protective stop placed → stop verified OPEN →
  stop cancelled → market flatten → venue position verified back to start.
- `stopfill`: market entry → sell-stop with trigger just above market
  (fires immediately) → stop FILL verified → flat. If the venue rejects or
  the fill doesn't confirm within the poll budget: cancel + market flatten
  fallback, drill marked `unverified`, never left open.
  LIVE-SEMANTICS CAVEAT (referee 2026-08-15): Coinbase validates stop
  price vs last trade and may REJECT an above-market STOP_DOWN sell — the
  first live stopfill drill is therefore also a venue experiment; if
  rejected, the fallback flattens safely and stopfill gets redesigned
  (below-market trigger + longer poll budget) before the stop_filled row
  relies on it.
- AUTO-REPAIR tail (all kinds, all exception paths): residual venue
  position after a drill is flattened immediately with a reducing market
  order, recorded as `auto_repair`, and the drill event escalates to RED
  (pages Telegram). Trend organic entries (market path) count toward entry
  coverage; pullback entries prove the limit/post-only path.

Hard bounds (all enforced in code, not convention):
- size is ALWAYS exactly one venue contract; no parameter can raise it
- preconditions: not halted, BOTH legs flat (qty 0, no open entry/stop
  cloids), venue position ≈ 0 — a drill can never touch a real position
- budget: `DRILL_MAX_PER_DAY` (default 6) + 5-minute cooldown
- every drill order carries a `D-` cloid prefix; fills recorded with
  leg="drill" — included in slippage stats, EXCLUDED from all P&L
- triggered by the token-gated endpoint, or by AUTO-DRILL (below)
- expected cost ≈ spread + taker fees ≈ $1–2 per drill

## AUTO-DRILL (amendment 2026-08-17, Casey: zero-touch drill QA)

Supersedes the original "endpoint-only, no scheduler" rule. Flat windows
between S4 trades are short (1–5 days), unpredictable, and were being
missed — so the executor now runs its own drills inside the step loop when
ALL of: `AUTO_DRILL=true` (Render env, sync:false, default off), LIVE mode
(dry-run drills would fake live coverage), engine feed healthy, book+venue
flat (the same refusal preconditions), drill coverage rows still unmet, and
≥ `AUTO_DRILL_SPACING_S` (default 1h) since the last drill. Every
manual-drill hard bound applies unchanged — size, budget, cooldown,
auto-repair tail, RED paging.

CYCLES ONLY (referee 2026-08-17): auto-drill never schedules `stopfill`.
Coinbase maps a SELL stop to STOP_DOWN and preview-rejects an above-market
trigger, so an auto stopfill fails deterministically and would latch the
breaker on its first attempt. The stop_filled row is covered organically
(S4's stops fill in the normal course of trading) or by a supervised
manual stopfill after redesign — never automatically.

Coverage honesty: a drill credits its coverage rows only AFTER the repair
tail confirms it fully verified (`ok=true`). A failed drill advances
nothing — broken mechanics must not count as proven.

Circuit breaker: ONE failed auto drill sets `auto_drill_off` (persisted,
shown in /status.auto_drill) and pages — it never retries into a venue
that just failed. If the repair tail could not VERIFY flatness the page
escalates to ACTION-NEEDED (check Coinbase manually). Re-arm path: any
subsequent VERIFIED drill (a human running `/drill` supervised) clears
the breaker and logs `auto_drill_rearmed`. `AUTO_DRILL` itself is in the
config_change snapshot, so a silent flip pages like any other
trading-behavior var. The halt+resume coverage pair stays a HUMAN test by
design: it proves the operator's kill switch, so automating it would
prove nothing.

## Rung advancement (after coverage complete)

KELLY_M 0.05 → 0.10 → 0.20 → 0.30. Per rung: ONE organic trade whose
realized notional is within 5% of the sizing target (verified from fills +
/status), caps intact (MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV, DD_HALT_PCT
unchanged — these are the risk bound, not the ramp), then advance. Casey
moves KELLY_M in Render (human-in-loop preserved; the executor never
resizes itself). `/status.ramp_v4` computes gate satisfaction live.

## What this does NOT change

DRY_RUN law; all caps and halts; keyless engine separation; the honesty
that the EDGE remains unproven at these timescales — scaling is a
Kelly-fraction decision under uncertainty, with edge-monitor watching the
downside from day one.
