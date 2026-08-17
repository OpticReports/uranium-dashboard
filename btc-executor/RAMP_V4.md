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
