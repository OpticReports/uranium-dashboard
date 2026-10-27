# DRAWDOWN halt — resume protocol (v1.2, 2026-10-27, counter-agent reviewed)

Casey's call (2026-10-27): the downside threat is treated as DIFFUSE — no
pre-emptive size cut, no dated revert. The control point is therefore what
happens AFTER the $30k drawdown halt fires. This document is that procedure,
written before the halt so that the decision is made once, cold, and the
hot moment is a checklist. It is the `#3` item of the downside-risk menu
(btc-paper-engine/research/stress/, 2026-10-07); `#2` (re-arm rule for the
pullback book's one-way halt) is the next study and is NOT part of this.

Scope: `halted == "DRAWDOWN"` on btc-executor, including a `DAILY_LOSS` halt
relabelled `DRAWDOWN` (mirror.py L1644-1657, L1780-1787). Not covered:
`LEDGER_DIVERGENCE` / `STOP_UNPLACEABLE` (protection failures — root cause
first, EXECUTOR.md "Halt automation"), `KILL`, `VENUE_CHANGED`, `AGENT_EXPIRED`.

**Status at writing.** btc-executor has been halted `LEDGER_DIVERGENCE` since
2026-10-07 08:01Z (root cause open). The halt flattened an S4 long; the
engine's S4 book is now in a different trend position (short since
2026-10-24 16:00Z). This protocol does NOT apply to that halt and does not
authorise resuming it. Stage A below cannot even be reached until it is
closed by its own process (`_check_halts` returns on any existing halt,
L1789). Three things carry over when it IS resumed: C4.2's late-join check
applies to the S4 leg; a plain `/resume` of a non-loss halt performs NO
breach check and the 3-poll debounce lets entries out first, so confirm
`/status high_water − equity` < $30,000 and the day inside its daily line
before pressing; and `?reanchor=1` on a non-loss halt moves nothing — the
reanchor branch lives inside the DAILY_LOSS/DRAWDOWN test (L2030) and the
response's `reanchor_requested` only echoes the request.

## 0. What the code does (facts, with line refs in btc-executor/app/)

| item | fact | where |
|---|---|---|
| the line | equity < high_water − DD_HALT_PCT × SIZING_BASE_USD. Base is FIXED (100,000), so the halt is a $30,000 drawdown in dollars at every account size. Checked BEFORE the daily line | mirror.py L1750-1766, `_base` L1531 |
| equity | spot USDC (carries every perp's uPnL) + non-USDC spot tokens at mid — the UETH sleeve counts. The same read backs `/resume` (L2032) | hl.py `equity()` L508-552 |
| high water | ratchets up on every poll (L1686). Shifted by ANY flat-book equity jump ≥ max(0.2% of base, $50) = $200 between two polls while the venue is BTC-flat — deposits, withdrawals, a bad read recovering, an unhedged UETH move — and this runs WHILE HALTED too (`_reconcile_transfers` sits before the halted return, L2330-2339). The code has no transfer notion, only "flat-book jump" | L1686, L1688-1727 |
| debounce | 3 consecutive polls below the line (~60 s at 20 s polls); `halt_pending` WARN on the first. The RELABEL path is immediate: a `DAILY_LOSS` halt whose flatten lands under the drawdown line becomes `DRAWDOWN` at the next poll or at the rollover with no second `halt_pending` (sequence: `halt_pending DAILY_LOSS` → `halt DAILY_LOSS` → `halt … upgraded to DRAWDOWN` / `DRAWDOWN at UTC rollover`) | L424, L1844-1855; L1780-1787, L1644-1657 |
| the halt | sets `halted=DRAWDOWN`, pages RED `halt`; PROBES the venue; cancel_all; re-reads; reduce-only market close of the NET; verifies every ledger order terminal; zeroes the ledger. BTC-scoped: `position()`, `cancel_all()` and the close filter on `HL_COIN` (hl.py L565, L757, L876), so the ETH short and carry-executor's orders are untouched | L1864-1989 |
| halt failure modes | `halt_blind` (venue unreadable: NOTHING cancelled, stop still resting, flatten by hand); `halt_residue_unsendable` (dust under the venue minimum, stop already cancelled, close by hand on the HL UI — the ledger is still zeroed, so `/pulse` reads flat); `halt_error` (flatten failed: ledger KEPT on purpose) | L1889, L1927, L1988 |
| the halt page | the phone page for kind `halt` says "hit /resume?token=…". For DRAWDOWN that line does not apply; this document does. (Pointing the page here is a small code change, deferred: `app/` edits rebuild the executor) | L1330-1332 |
| plain /resume | REFUSED while equity is still below the line (`resume_refused`); `halted` stays `DRAWDOWN` in the response | L2030-2051, main.py L684-714 |
| /resume?reanchor=1 | moves high_water AND day_start_equity to current equity, pages RED `resume_reanchored`, clears the halt, re-verifies stop refs, re-checks agent-key expiry. FORGIVES the drawdown: the next line is new equity − $30k. UNCONDITIONAL: it lowers high_water to equity even when equity is already back above the old line. Does not touch the frozen daily pct | L2052-2075 |
| after resume | the next poll mirrors the engine: a leg the engine HOLDS and we do not is joined by a market chase at the venue mid, sized at the CURRENT KELLY_M (`_enter_from_fill`); a pending PULLBACK entry is placed post-only at the engine's limit, a pending TREND entry is a market IOC booked by intent; stops follow. Entries are blocked by: engine stale, `degraded`, `data_halt`, a boot venue-vs-ledger mismatch (`position_drift` at boot), a netting mismatch, or that leg's engine book halted | L2344-2348, L2458-2470; join L2612-2625; pending L2634-2826; L2863+ |
| daily line after a K change | the scaled DAILY_LOSS pct is FROZEN at each 00:00 UTC rollover from the KELLY_M in force THEN; `_roll_day` runs before the halted return, so a rollover re-freezes it while halted. 15% of base at 0.75, 6% at ≤ 0.30. `daily_loss_line_pending` is only emitted when NOT halted (after a resume) | L1729-1748, L1680-1684, L1789-1797 |
| exposure guard | once trading (it sits after the halted return), pages `exposure_over_cap` every poll when K_eff × lev × base > 1.125 × max(equity, high_water) × 1.01. Page-only, never clamps. At base 100k and the engine's lev 1.5: K 0.75 needs max(equity, HW) ≥ $99,010; K 0.30 needs ≥ $39,604 | L107, L574-610 |
| persistence | `halted`, `high_water`, `day_start_equity`, `day_loss_pct` live in /app/data/executor_state.json (Render disk) and SURVIVE a redeploy; an env change restarts the container but does not clear the halt; `config_change` pages within one poll even while halted | L1201-1206, L1262-1267, L2302-2316 |
| engine books | the engine's own paper books halt one-way at dd_halt (S3 −30%, S4 −50% of their paper peak); a halted book is FLAT; the executor pages `engine_leg_halted` and opens no new entry for that leg. Public engine `/status` shows `books.<S>.halted` and `state`; the reason (`dd_halt` / `manual`) is on `/exec/target` (token) | L2404-2443, L2470; engine config.py L66/L73 |
| stale references | EXECUTOR.md said 35% in two places (fixed in this commit to 0.30). Still stale, left for a code commit: hl.py L516 docstring "35% drawdown", mirror.py L2027 comment "the NEXT 35%", render.yaml L605 "MAX_EXPOSURE_FRAC (0.45 …)". Live is DD_HALT_PCT 0.30 and MAX_EXPOSURE_FRAC 1.125 | render.yaml L611, mirror.py L107 |

## 1. Where the lines are today (2026-10-27 12:25Z, K 0.75)

| rail | level | from |
|---|---|---|
| high water | $100,239.28 | the executor's `/status high_water` (token) is the authoritative rail; the portfolio accountValueHistory peak quoted here is the monitor's cross-check and can differ by the executor's own mid read |
| monitor T4 page (90% of HW) | $90,215.35 | routine tripwire — pages Casey, recommends K → 0.30 |
| DAILY_LOSS (15% of base from 00:00Z equity $100,095.49) | $85,095.49 | auto-rearms at 00:00 UTC |
| DRAWDOWN halt (HW − $30,000) | $70,239.28 | manual resume — THIS protocol |
| equity now | $100,087.62 | executor read: USDC 74,303.75 + 11.096 UETH @ ~2,324 |
| BTC cross leverage setting | ___ (HL UI; not readable from the API while flat) | the adapter never sets leverage; initial margin for $45k gross at 0.30 = 45,000 / leverage against ~$44k USDC after the loss |

Note the ORDER: T4 pages at −$10k from the high water, the daily line at
−$15k within one UTC day, the drawdown halt at −$30k. A slow multi-day
bleed pages T4 once and then reaches the halt without the daily line (it
re-arms every 00:00Z); a one-day cascade hits the daily halt first and needs
a second day, or a gap, to reach the drawdown line.

The stress study (COVID / 2008 / dot-com analogues on today's book) never
fired this halt in 83 runs, but the worst path came close: it left $3,051 of
the $30k budget, 90% used (COVID, K 0.75, offset 0). A live DRAWDOWN halt
at 0.75 is therefore the tail the study nearly reached — a size-falsification
signal at 0.75, which is exactly why C1 steps to 0.30, not evidence that the
strategy is broken.

## 2. The protocol

### Stage A — the halt fires (T+0 to T+1h). Verify, record, do nothing else.

The monitor routine fires T2 and messages Casey with the numbers. Then:

1. **Confirm the flatten on the VENUE, not the ledger.** HL UI (or
   `clearinghouseState` for 0xAb53…51e2): BTC position 0, no BTC orders.
   `/pulse` (public): `halted: "DRAWDOWN"`, `legs.pullback.in_position` and
   `legs.trend.in_position` both false, `stop_placed` false — that is the
   ledger's belief, zeroed even in the residue case, not venue truth.
   `/status` (token): `legs.*.qty == 0`. If `/status` events show
   `halt_blind`, `halt_residue_unsendable` or `halt_error`: the venue still
   holds something — flatten and cancel BY HAND on the HL UI first; step C4.5
   then uses `adopt_venue=1`.
2. **Check the carry sleeve.** carry `/pulse`: `on: true` with
   `hedge_gap_usd` < $50 and no new red kind is the normal pass. `on: false`
   WITH a stated reason (engine DISARM below 5%, margin guard) is a
   legitimate state, not a failed check — C1 of the routine reports it
   separately. Margin after the loss: the ETH short's cross backing is the
   account's USDC, so read `clearinghouseState` `liquidationPx` for ETH and
   require liq > 2 × ETH mid. Reconstruction for the operator's own
   arithmetic: liq ≈ mid + (USDC − maintenance) / (qty × 1.02); today
   2,326 + (74,304 − 516) / (11.096 × 1.02) = $8,846 (matches the venue);
   after a $30k loss ≈ $6,200 against ETH ~$2,300 — the carry code unwinds
   within 15% of liq (~$5,270). If carry's red kinds carry
   `margin_guard_unreliable`, the venue's figure is not trusted by the code
   either: rely on the 15% guard and say so. If liq < 2 × mid, the only
   levers are carry-executor's `CARRY_NOTIONAL_USD` / `CARRY_ENABLED`
   — never a transfer.
3. **Record the halt**: `/status` → `high_water`, `day_start_equity`,
   `events[-50:]` (the `halt_pending` → `halt` sequence, or the relabel
   sequence, and any failure mode), `fills` since the last flat, realized
   BTC P&L of the episode (HL `userFillsByTime`, coin == BTC, closedPnl −
   fee), and `/pulse agent_days_left` (the expiry rail keeps reading hourly while
   halted and can page `agent_expiring`, but will not halt again until
   `/resume`, which re-checks immediately; under 1 day means renew the agent
   key first).
4. **No /resume for 24 hours.** Nothing is at risk while flat: the BTC book
   is out, the sleeve is price-neutral and keeps earning. A plain `/resume`
   is refused by the code anyway, and the halt page's "hit /resume" line is
   the generic text, not this halt's instruction.

### Stage B — diagnosis (T+24h to T+7d). Classify before any size decision.

| class | test | consequence |
|---|---|---|
| **B1 strategy loss, mechanics sound** | every live fill matches an engine paper trade (engine `/books/S3,S4/trades`) within slippage; stops were placed and filled where the engine's levels were; no RED kind other than `halt`, `halt_pending` and the known `unbooked_fill_unprotected` window | proceed to Stage C |
| **B2 mechanics fault** | any of: `position_drift`, `netting_inconsistent`, `stop_vanished`, `stop_unplaceable`, `entry_unconfirmed`, a fill with no engine counterpart, a stop that did not fire, slippage > 100 bp on an exit | NO resume. Root cause → fix → gate test → review, exactly as for `LEDGER_DIVERGENCE`. The loss is still real: when the fix ships, resume via Stage C |
| **B3 non-BTC cause** | the equity drop was not BTC P&L: UETH depeg, carry hedge gap, a withdrawal, a bad equity read (compare `portfolio` accountValue with the executor's) | fix the cause. If the money is NOT really gone, the recovery is usually ABSORBED while halted: a flat-book jump ≥ $200 between polls shifts high_water by the same amount (`transfer_reconciled` INFO), the gap to the line is unchanged and a plain `/resume` stays refused. Not absorbed, and the gap closes instead: a recovery landing on the FIRST flat poll after the halt (the baseline is only seeded there), or across any restart — C4 step 1's own redeploy included (`_last_flat_equity` is not persisted). So check `/status high_water − equity`: under $30,000 the plain form works and keeps the drawdown room; otherwise, after confirming on `portfolio` that the money is back, use `?reanchor=1` — it forgives nothing real in this case — and record the `transfer_reconciled` events. SIZE in this class (CONFIRMED by Casey 2026-10-27): with the money intact and the old high water kept, nothing was falsified — resume at the size in force (0.75 does not page while max(equity, high_water) ≥ $99,010; the high water is $100,239 today); if the money IS gone, Stage C applies in full |

Keep the diagnosis to one page in `btc-executor/docs/` with the fills table
and the classification; the counter-agent rule applies (one independent
reader for B1, two for B2 — the fix touches live money).

### Stage C — resume (B1 or fixed B2/B3). DEFAULTS — CONFIRMED by Casey 2026-10-27 (C1, C3, C4a and B3's size rule).

**C1. Size: KELLY_M 0.30. SIZING_BASE_USD and MAX_NOTIONAL_USD unchanged.**
Why 0.30 and not 0.75: once the high water is forgiven, the exposure guard
needs max(equity, HW) ≥ $99,010 for K 0.75 at base 100k — a $70k account
would page `exposure_over_cap` on every poll (that is the guard working, not
noise). 0.30 is the last approved rung below, needs only ≥ $39,604, and in
the stress study held maxDD to −8.3% / −3.9% / −5.1% (COVID / 2008 / 1999)
against −21.0% / −8.2% / −13.6% at 0.75. Why the base stays: the render.yaml
rule — change KELLY_M one step at a time, never alongside SIZING_BASE_USD —
and a base cut is the dated-threat posture Casey declined. (Alternative,
Casey's override only: SIZING_BASE_USD = equity WITH MAX_NOTIONAL_USD moved
together, which keeps 0.75's leverage and makes the next halt $21k instead
of $30k; it is a ramp step with its own review.)

**C2. Reanchor: yes.** `/resume?reanchor=1`. The money is below the line and
nothing about pressing resume changes that; the code refuses the plain form.
Reanchoring sets the NEXT halt at new equity − $30k (≈ $40k on a $70k
account, i.e. −43% of what is left). That is why C3 exists. Read
`/status high_water − equity` before pressing: the flag is unconditional
and would also lower a high water that equity has already climbed back
above; the plain form is right only in B3 with the gap under $30k and a few
thousand dollars of room (a few hundred dollars above the line re-halts
inside the 3-poll debounce on the next dip). If a plain `/resume` is
accepted after C4 step 1 on a B1/B2 resume, the recovery landed in an
un-absorbed window (across the step-1 redeploy, or on the first flat poll
after the halt) and the old high water is kept — that is fine; record it.

**C3. Kill criterion (written now, before money moves): a SECOND DRAWDOWN
halt within 180 days of a resume is not resumed.** DRY_RUN=true, book stays
flat, full strategy review (the stress study's worst path used 90% of ONE
$30k budget; two is outside anything modelled). The carry sleeve is
unaffected and keeps running on its own gate.

**C4a. If the engine's S3 (pullback) paper book is itself halted at resume
— the LIKELY case** (it halted one-way on two of the three crash analogues,
at both K: COVID 11-30, 1999 12-08; not on 2008): DEFAULT = resume
TREND-ONLY at 0.30. The executor blocks pullback entries while the engine
publishes `legs.pullback.halted` (the public `/status` `books.S3.halted`)
and pages `engine_leg_halted`; the book is then $13,500 × m of trend
exposure with the same rails. This is a MEASURED case: after those S3 halts
the study's COVID and 1999 paths ran trend-only to the horizon. What the
numbers say (results.json curves, offset 0, intrabar rail; recomputed
independently twice): the crash drawdowns were mostly built BEFORE the S3
halt with both legs on — 63% / 69% of the COVID fall at 0.75 / 0.30 and
63% / 61% of the 1999 fall — and the trend-only tail added the rest (COVID
−$8.7k / −$2.7k; 1999 −$5.1k / −$2.0k). The 90% rail reading on 05-27 was
taken inside the trend-only stretch, but the rail was already 62% used when
S3 halted. Measured from its own peak, the trend-only stretch used 44% / 17%
of a fresh $30k budget on COVID and 25% / 9% on 1999 at 0.75 / 0.30. So the
size step is the sign-certain lever (rail 90% → 34% on COVID, 59% → 22% on
1999); the leg mix is worth ±12–19 rail points with the sign set by the
path (two legs better on COVID: the halt forwent +$12.2k; worse on 1999: it
saved $11.2k), which is why the re-arm rule is the `#2` study and not a
default here. The pullback leg lost on COVID and 1999 (−$15.4k / −$16.6k
before its halt) and earned on 2008 (+$11.4k). Casey's alternatives: resume
the engine's book by hand (`POST btc-paper-engine/books/S3/resume`,
`x-exec-token`; it also resets the paper book's peak), a separate decision
with its own review, or hold the resume until `#2` ships. Default CONFIRMED by Casey 2026-10-27.

**C4. Order of operations** (each step has a check; do not skip the check):

| # | action | check before moving on |
|---|---|---|
| 1 | Render → btc-executor env: `KELLY_M` 0.30. Nothing else. Do it BEFORE a 00:00 UTC rollover, so the rollover re-freezes the daily line at 6% while the book is still halted (a change just AFTER 00:00 would leave the 0.75 line, $15k, on a 0.30 book for the first live day) | Render redeploys (same build sha). `/pulse`: `build` unchanged, `halted: "DRAWDOWN"` still set, `red_kinds_24h` gains `config_change` (expected, fires while halted) |
| 2 | Which legs will JOIN: btc-executor `/status.last_target` (token) is the payload the mirror consumes; the engine's public `/status` books are the same in-process books as a cross-check. Late-join risk R = Σ over legs with `position != null` of (leg notional at 0.30 × m) × |mid − stop| / mid, with pullback $31,500 × m and trend $13,500 × m; the stop is `position.stop` on `last_target` (the trail already folded in for the trend leg; `trail` on the engine's public `/status`). Every held position carries a stop, so R is defined for every joinable leg. A PENDING pullback is the normal state: it is placed post-only at resume and its fill carries the disclosed unbooked window (B1) — not a wait condition. On an opposed book R is an upper bound (the venue nets the two legs; one stop sized to the net) | if R > $6,000 (the 0.30 daily line in force after step 1's rollover) wait for that leg to go flat or for its trail to tighten; otherwise proceed |
| 3 | Engine health: `/status` `vol_size.basis == "vol_target"`; `/events` no `degraded` without a later `recovered`; `/exec/target` (token) `data_halt` false; no boot `position_drift` event in btc-executor `/status` since the step-1 redeploy; `books.S3.halted` / `books.S4.halted` on the public `/status` | `entries_blocked` for staleness is not a reason to wait — the mirror enters later — but a `degraded` engine is. `books.S3.halted: true` → apply C4a (trend-only) and re-derive R for the trend leg alone |
| 4 | Carry sleeve as in Stage A step 2; `/pulse agent_days_left` > 1 | `on` as expected, gap < $50, liq > 2 × mid; a key under 1 day would hand the halt straight back as `AGENT_EXPIRED` |
| 5 | PRECONDITION: one 00:00 UTC rollover has passed since step 1 — `/status sizing_config.daily_loss_halt_pct_effective` reads 0.06. (If resuming on the same UTC day as step 1 is unavoidable, the first live day runs on $15k: say so and test R against $15k.) Then `GET https://btc-executor.onrender.com/resume?reanchor=1&token=<EXEC_TOKEN>` (or POST with `x-exec-token`). If Stage A found a failed flatten and the venue was cleaned by hand: `?reanchor=1&adopt_venue=1` — ONLY after looking at the HL UI yourself; the adopt never clears the halt by itself, so the reanchor branch still runs | response keys: `ok`, `halted`, `adopt_requested`, `adopted`, `reanchor_requested` (echo only — not a confirmation). PASS = `halted: null` AND `/status` events show RED `resume_reanchored` and INFO `resume cleared DRAWDOWN` AND `high_water == day_start_equity ==` current equity. If `halted` is non-null for ANY value, stop: `resume_refused` = the breach is still live; a `halt` / `halt_*` event of another kind = the resume ran and something else halted it (`LEDGER_DIVERGENCE` from stop-ref hygiene, `AGENT_EXPIRED`) |
| 6 | First mirror poll: WARN `entry_chase` (normal) on any joined leg; fresh entries thereafter at $31,500 × m / $13,500 × m | `/pulse legs.<leg>.stop_placed: true` (or `stop_mode: "engine"` on the subordinate leg of an opposed book); no `stop_unconfirmed` / `stop_place_failed` / `stop_backing_blind` event; `daily_loss_line_pending` appears only if step 5 ran on the same day as step 1. Monitor routine: "fresh BTC entry — say which size it matches" must read the 0.30 sizes, never 0.75's |
| 7 | Re-base the monitor (my action, `update_trigger` on trig_0192jctE7J8ocbFmUSjBnvDA): T4 high water := the reanchor mark (trip 90% of it); T1 realized counter restarts at the resume timestamp with the 0.30 budget (−$1,500 = the 0.30-scaled equivalent of −$3,750 at 0.75); expected sizes 0.30; trend-only if C4a applied; record the halt and resume as REPORTED | routine prompt diff shows the new HW/trip and the resume timestamp |

### Stage D — the way back to 0.75 (DEFAULT — follows from C1; not separately confirmed)

All of, measured from the resume timestamp:

- ≥ 30 days at 0.30 with NO halt of any kind on either executor and no B2-class
  red kind;
- `/status high_water` ≥ $99,010 — the code's own ceiling for 0.75 at base
  100k (it reads max(equity, high_water), and after a reanchor the high water
  ratchets with equity). On a $70k account that is +41%, so in practice 0.75
  is OFF THE TABLE after a full $30k halt unless Casey takes the base-cut
  override in C1 (a separate decision with its own review). State this
  plainly rather than let the guard page it;
- the step is 0.30 → 0.75 in one move, as approved on 2026-10-01, with
  MAX_NOTIONAL_USD 130000 confirmed FIRST and the T1–T5 tripwires re-armed
  from the new high water.

## 3. Never, at any stage

- Never ask Casey to move funds; `marginSummary.accountValue` is the perp pool
  only. Quote `portfolio` / `spotClearinghouseState` for any balance claim.
- Never `adopt_venue=1` without a human having just looked at the HL UI.
- Never change SIZING_BASE_USD and KELLY_M in the same step.
- Never roll btc-executor back past the spot-token equity build while the
  sleeve is on (carry-executor would page `sleeve_unseen`).
- Never resume to "see if it recovers": the rung is chosen in Stage B/C, and
  a second halt is the kill criterion, not a second chance.
- Never apply this document to a halt that is not `DRAWDOWN`.

## 4. Honesty box

- The DRAWDOWN halt has never fired live (the 2026-08-06 event was a bad
  balance read, pre-debounce). Every step above is derived from the code at
  build 9db4356 (no `app/` diff to HEAD) and the stress harness, not from a
  live rehearsal. `/kill` → `/resume` exercises the resume path without the
  breach logic (the ramp's "halt + resume" row is an operator-triggered pair,
  RAMP_V4.md); the reanchor branch itself can only be rehearsed with a real
  loss halt in place.
- The stress-study numbers quoted (maxDD by K, 90% rail use, no halt in 83
  runs) are in-sample analogues scaled onto today's prices with fills at
  the line and no slippage — upper bounds on the book, lower bounds on the
  drawdown. They motivate the 0.30 default; they do not forecast it. The
  COVID and 1999 maxDD figures at both K are two-leg drawdowns deepened by a
  trend-only tail: 61–69% of each fall was in before S3 halted (11-30 /
  12-08). Measured from its own peak, the trend-only stretch used 44% / 17%
  (COVID) and 25% / 9% (1999) of a fresh $30k budget at 0.75 / 0.30; 2008's
  figures include both legs throughout. No path in the study had S3
  re-armed after its halt.
- The late-join risk R in C4.2 is defined for every held engine leg (each
  publishes a stop) and is an upper bound on an opposed book. The
  `unbooked_fill_unprotected` window opens only AFTER our own maker fill,
  post-resume; it is the known window listed under B1, not a resume gate.
- The $99,010 / $39,604 figures are 112,500 and 45,000 divided by
  (1.125 × 1.01) with lev 1.5 and base 100,000; they move with the blend lev
  the engine publishes.
- The ETH liquidation arithmetic in Stage A is a reconstruction calibrated on
  one venue read; the carry code itself treats `liquidationPx` under the
  unified account as unverified (`margin_guard_unreliable`). The venue's own
  number governs; the formula is for sanity, not for action.
- What is NOT modelled here: the HL mark-price vs Bitstamp bar difference
  on the halt fill, funding on the joined legs, the account's BTC leverage
  setting (not recorded — see the blank in Section 1), and the carry
  sleeve's behaviour if the SAME event that drew down BTC also moved ETH
  funding through the 5% disarm (C1 of the routine would page separately).

Figure: `docs/resume_protocol_rails.png` (rails before the halt and after a
reanchored resume at 0.30; script `docs/resume_protocol_rails.py`).

Review record (staffing per CLAUDE.md: two readers on every SERIOUS item;
no agent verified text it wrote):
- Round 1, two independent verifiers (code-truth; operator/risk): 6 SERIOUS,
  18 MINOR, 8 NOTE, no BLOCKING — folded into v1.1.
- Round 2, one re-verifier on the six SERIOUS fixes: all six FIXED; 1 new
  SERIOUS (C4a misread the stress attribution), 3 MINOR, 5 NOTE — folded in.
- Round 3, one narrow checker on the rewritten C4a: 2 SERIOUS (the drawdown
  share before vs after the S3 halt; the honesty bullet's basis), 3 MINOR,
  1 NOTE. Its numbers were recomputed independently from results.json
  (match to the dollar) and are what v1.2 states.
