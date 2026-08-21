# RAMP v4 — coverage-gated scaling (frozen 2026-08-15)

Supersedes the v3 "4 trades + cum P&L ≥ 0 per rung" ramp. Rationale,
measured: 4 trades of a ~53%-win strategy is a coin flip — the old gate
could pass a broken system and fail a working one, and it put months
between rungs without adding safety. The edge itself is verified only by
the paper track + edge-monitor over years (MinTRL ≈ 2y, measured); the ramp
verifies MECHANICS, and mechanics are per-event proofs, not per-week ones.

## The gate: event-coverage matrix (pre-registered)

Advance past ramp stage 0 only when every row is met, evidenced by the
executor's own coverage counters (`/status.coverage`, persisted state,
incremented inside the real code paths — never by hand):

| event class            | required | how it can be produced            |
|------------------------|----------|-----------------------------------|
| entry_long             | ≥2       | organic only (real limit-entry path) |
| entry_short            | ≥2       | organic only                      |
| stop_placed            | ≥2       | organic or drill (same venue path)|
| stop_filled            | ≥1       | drill `stopfill` or organic       |
| signal_exit (leg close)| ≥2       | organic only                      |
| chase                  | ≥1       | organic (entry_chase)             |
| post_only_cross        | ≥1       | organic short at positive basis   |
| restart_with_position  | ≥1       | ✅ proven 2026-08-15 (redeploy with open trend short) |
| config_change detected | ≥1       | any env change redeploy           |
| halt + resume          | ≥1 pair  | operator-triggered manual test    |
| drill_cycle complete   | ≥3       | drill                             |
| slippage sample        | ≥10 fills| any (drill fills count — they are real fills) |

Honesty note: drills deliberately do NOT count toward entry/exit/chase
coverage — drill entries are market orders, organic entries go through the
limit + post-only + chase machinery, and only the real path proves the real
path. Drills own what organics produce too rarely: the stop lifecycle and
the slippage sample. Organic entry cadence (S3+S4 ≈ 2–4 signals/week)
completes the rest in ~2–3 weeks.

Slippage sanity gate: |mean slip| < 15bps and no slip-CUSUM alarm
(edge-monitor). P&L is explicitly NOT a gate at any stage.

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
10-fill slippage sample counts live fills only.

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
- endpoint-only: no scheduler ever calls it; Casey triggers with the token
- expected cost ≈ spread + taker fees ≈ $1–2 per drill

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
