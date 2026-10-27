# DRAWDOWN halt — resume protocol (v1, 2026-10-27)

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

## 0. What the code does (facts, with line refs in btc-executor/app/)

| item | fact | where |
|---|---|---|
| the line | equity < high_water − DD_HALT_PCT × SIZING_BASE_USD. Base is FIXED (100,000), so the halt is a $30,000 drawdown in dollars at every account size. Checked BEFORE the daily line | mirror.py L1750-1766, `_base` L1531 |
| equity | spot USDC (carries every perp's uPnL) + non-USDC spot tokens at mid — the UETH sleeve counts | hl.py `equity()`, EXECUTOR.md "ETH carry sleeve" |
| high water | ratchets up on every poll; shifted by flat-book transfers (deposit/withdrawal ≥ max(0.2% base, $50) while the ledger is empty) | L1686, L1688-1727 |
| debounce | 3 consecutive polls below the line (~60 s at 20 s polls); `halt_pending` WARN on the first | L424, L1844-1855 |
| the halt | sets `halted=DRAWDOWN`, pages RED `halt`; PROBES the venue; cancel_all; re-reads; reduce-only market close of the NET; verifies every ledger order terminal; zeroes the ledger. Carry-executor is a separate service and is NOT touched | L1864-1989 |
| halt failure modes | `halt_blind` (venue unreadable: NOTHING cancelled, stop still resting, flatten by hand); `halt_residue_unsendable` (dust under the venue minimum, stop already cancelled, close by hand on the HL UI); `halt_error` (flatten failed: ledger KEPT on purpose) | L1889, L1927, L1988 |
| plain /resume | REFUSED while equity is still below the line (`resume_refused`); says so in the response (`halted` stays `DRAWDOWN`) | L2030-2051, main.py L684-714 |
| /resume?reanchor=1 | moves high_water AND day_start_equity to current equity, pages RED `resume_reanchored`, clears the halt, re-verifies stop refs, re-checks agent-key expiry. FORGIVES the drawdown: the next line is new equity − $30k | L2052-2075 |
| after resume | the next poll mirrors the engine: a leg the engine HOLDS and we do not is joined by a market chase sized at the CURRENT KELLY_M (`_enter_from_fill`, venue mid, `entries_ok` gated); a pending engine entry is placed as a maker order; stops follow | L2472-2585, L2863+ |
| daily line after a K change | the scaled DAILY_LOSS pct is FROZEN at the last 00:00 UTC rollover; a new KELLY_M moves it at the NEXT rollover (`daily_loss_line_pending`). 15% of base at 0.75, 6% at ≤ 0.30 | L1729-1748, L1797 |
| exposure guard | pages `exposure_over_cap` every poll when K_eff × lev × base > 1.125 × max(equity, high_water) × 1.01. Page-only, never clamps. At base 100k and lev 1.5: K 0.75 needs ≥ $98,999; K 0.30 needs ≥ $39,600 | L107, L574-610 |
| persistence | `halted`, `high_water`, `day_start_equity` live in /app/data/executor_state.json and SURVIVE a redeploy; an env change restarts the container but does not clear the halt | L1201-1206, L1262-1267 |
| engine books | the engine's own paper books halt one-way at dd_halt (S3 −30%, S4 −50% of their paper equity) and the executor opens no new entry for a halted leg (`engine_leg_halted`) | L2404-2443 |

## 1. Where the lines are today (2026-10-27 12:25Z, K 0.75)

| rail | level | from |
|---|---|---|
| high water | $100,239.28 | portfolio accountValueHistory peak (monitor T4 basis) |
| monitor T4 page (90% of HW) | $90,215.35 | routine tripwire — pages Casey, recommends K → 0.30 |
| DAILY_LOSS (15% of base from 00:00Z equity ≈ $100,095) | ≈ $85,095 | auto-rearms at 00:00 UTC |
| DRAWDOWN halt (HW − $30,000) | $70,239.28 | manual resume — THIS protocol |
| equity now | $100,087.62 | USDC 74,303.75 + 11.096 UETH @ 2,326 |

Note the ORDER: T4 pages at −$10k, the daily line at −$15k in one day, the
drawdown halt at −$30k. In a slow bleed Casey hears about it twice before
the halt; only a gap or a cascade reaches the halt without a page first.
The stress study (COVID / 2008 / dot-com analogues on today's book) never
fired this halt in 83 runs; the closest approach was $3,051 of the $30k
budget (COVID, K 0.75). A live DRAWDOWN halt is therefore OUTSIDE the tested
envelope — treat it as a falsification signal, not as a bad day.

## 2. The protocol

### Stage A — the halt fires (T+0 to T+1h). Verify, record, do nothing else.

The monitor routine fires T2 and messages Casey with the numbers. Then:

1. **Confirm the flatten on the VENUE, not the ledger.** HL UI (or
   `clearinghouseState` for 0xAb53…51e2): BTC position 0, no BTC orders.
   `/pulse` (public): `halted: "DRAWDOWN"`, both legs qty 0. If `/status`
   events show `halt_blind`, `halt_residue_unsendable` or `halt_error`:
   the venue still holds something — flatten and cancel BY HAND on the HL
   UI first, then step 5 uses `adopt_venue=1` (see Stage C note).
2. **Check the carry sleeve is untouched.** carry `/pulse`: `on: true`,
   `hedge_gap_usd` < $50, no new red kinds. After a $30k USDC loss the ETH
   short's cross-margin backing shrinks: read `clearinghouseState`
   `liquidationPx` for ETH and confirm it is still > 2× the ETH mid
   (illustrative: USDC ~$74k → ~$44k moves the liq from ~$8.8k to roughly
   $6.6k against ETH ~$2.3k; the carry code unwinds within 15% of liq).
3. **Record the halt**: `/status` → `high_water`, `day_start_equity`,
   `events[-50:]` (the `halt_pending` → `halt` sequence, any failure mode),
   `fills` since the last flat, realized BTC P&L of the episode (HL
   `userFillsByTime`, coin == BTC, closedPnl − fee).
4. **No /resume for 24 hours.** Nothing is at risk while flat: the BTC book
   is out, the sleeve is price-neutral and keeps earning. A plain `/resume`
   is refused by the code anyway.

### Stage B — diagnosis (T+24h to T+7d). Classify before any size decision.

| class | test | consequence |
|---|---|---|
| **B1 strategy loss, mechanics sound** | every live fill matches an engine paper trade (engine `/books/S3,S4/trades`) within slippage; stops were placed and filled where the engine's levels were; no RED kind other than `halt`, `halt_pending` and the known `unbooked_fill_unprotected` window | proceed to Stage C |
| **B2 mechanics fault** | any of: `position_drift`, `netting_inconsistent`, `stop_vanished`, `stop_unplaceable`, `entry_unconfirmed`, a fill with no engine counterpart, a stop that did not fire, slippage > 100 bp on an exit | NO resume. Root cause → fix → gate test → review, exactly as for `LEDGER_DIVERGENCE`. The loss is still real: when the fix ships, resume via Stage C |
| **B3 non-BTC cause** | the equity drop was not BTC P&L: UETH depeg, carry hedge gap, a withdrawal read as a loss (`_reconcile_transfers` only runs while FLAT), a bad equity read (compare `portfolio` accountValue to the executor's) | fix the cause. If the money is NOT really gone, resume WITHOUT reanchor once equity reads above the line (the code accepts a plain `/resume` then). If it is gone, Stage C |

Keep the diagnosis to one page in `btc-executor/docs/` with the fills table
and the classification; the counter-agent rule applies (one independent
reader for B1, two for B2 — the fix touches live money).

### Stage C — resume (B1 or fixed B2/B3). DEFAULTS — Casey confirms once, here, not at the time.

**C1. Size: KELLY_M 0.30. SIZING_BASE_USD and MAX_NOTIONAL_USD unchanged.**
Why 0.30 and not 0.75: once the high water is forgiven, the exposure guard
needs max(equity, HW) ≥ $98,999 for K 0.75 at base 100k — a $70k account
would page `exposure_over_cap` on every poll (that is the guard working, not
noise). 0.30 is the last approved rung below, needs only ≥ $39.6k, and in
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
account, i.e. −43% of what is left). That is why C3 exists.

**C3. Kill criterion (written now, before money moves): a SECOND DRAWDOWN
halt within 180 days of a resume is not resumed.** DRY_RUN=true, book stays
flat, full strategy review (the stress study's worst path used 90% of ONE
$30k budget; two is outside anything modelled). The carry sleeve is
unaffected and keeps running on its own gate.

**C4. Order of operations** (each step has a check; do not skip the check):

| # | action | check before moving on |
|---|---|---|
| 1 | Render → btc-executor env: `KELLY_M` 0.30. Nothing else. Ideally within the hour AFTER 00:00 UTC (see 6) | Render redeploys (same build sha). `/pulse`: `build` unchanged, `halted: "DRAWDOWN"` still set, `red_kinds_24h` gains `config_change` (expected) |
| 2 | Engine books: `btc-paper-engine /status` → S3, S4 `state`, `position.entry_price`, `stop_price`; `/exec/target` is what the mirror consumes and `/status` LAGS it | note which legs the mirror will JOIN at market on resume. Late-join risk R = Σ (leg notional at 0.30 × m) × |mid − stop| / mid, with pullback $31,500 × m and trend $13,500 × m. If R > $6,000 (the 0.30 daily line) wait for that leg to go flat or for its trail to tighten; otherwise proceed |
| 3 | Engine health: `/status` `vol_size.basis == "vol_target"`, `/events` no `degraded` without a later `recovered`, no engine book halted (`halt_reason`) | an `entries_blocked` state is not a reason to wait — it only means the mirror will enter later — but a `degraded` engine is |
| 4 | Carry sleeve still as in Stage A step 2 | `on: true`, gap < $50, liq > 2× mid |
| 5 | `GET https://btc-executor.onrender.com/resume?reanchor=1&token=<EXEC_TOKEN>` (or POST with `x-exec-token`). If Stage A found a failed flatten and the venue was cleaned by hand: `?reanchor=1&adopt_venue=1` — ONLY after looking at the HL UI yourself | response `{"ok": true, "halted": null, "reanchor_requested": true}`. `/status` events: RED `resume_reanchored` (expected), INFO `resume cleared DRAWDOWN`. `high_water` == `day_start_equity` == current equity. If `halted` is still set, read the `resume_refused` text and stop |
| 6 | Daily line: the 15% line (frozen at the last rollover) stays until the next 00:00 UTC, then 6% ($6k). Doing step 1 just after a rollover and step 5 the same day means the first live day runs on the wide line | `/status` `sizing_config.daily_loss_halt_pct_effective` reads 0.06 after the first rollover; `daily_loss_line_pending` INFO before it |
| 7 | First mirror poll: expect `entry_chase` (normal) on any joined leg and `stop_placed`; fresh entries thereafter at $31,500 × m / $13,500 × m | monitor routine: "fresh BTC entry — say which size it matches" must read the 0.30 sizes, never 0.75's |
| 8 | Re-base the monitor (my action, `update_trigger` on trig_0192jctE7J8ocbFmUSjBnvDA): T4 high water := the reanchor mark (trip 90% of it); T1 realized counter restarts at the resume timestamp with the 0.30 budget (−$1,500 = the 0.30-scaled equivalent of −$3,750 at 0.75); expected sizes 0.30; record the halt and resume as REPORTED | routine prompt diff shows the new HW/trip and the resume timestamp |

### Stage D — the way back to 0.75 (DEFAULT — Casey confirms)

All of, measured from the resume timestamp:

- ≥ 30 days at 0.30 with NO halt of any kind on either executor and no B2-class
  red kind;
- equity ≥ $99,000 — the code's own ceiling for 0.75 at base 100k. On a $70k
  account that is +41%, so in practice 0.75 is OFF THE TABLE after a full
  $30k halt unless Casey takes the base-cut override in C1 (a separate
  decision with its own review). State this plainly rather than let the
  guard page it;
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

## 4. Honesty box

- The DRAWDOWN halt has never fired live (the 2026-08-06 event was a bad
  balance read, pre-debounce). Every step above is derived from the code at
  build 9db4356 and the stress harness, not from a live rehearsal. A dry
  rehearsal of steps C4.1 and C4.5 is possible only with a real halt in
  place; `/kill` → `/resume` exercises the resume path without the breach
  logic (the ramp's "halt + resume" row is an operator-triggered pair, RAMP_V4.md).
- The stress-study numbers quoted (maxDD by K, 90% rail use, no halt in 83
  runs) are in-sample analogues scaled onto today's prices with fills at
  the line and no slippage — upper bounds on the book, lower bounds on the
  drawdown. They motivate the 0.30 default; they do not forecast it.
- The late-join risk R in C4.2 uses the engine's current stop; a pullback
  fill has no engine stop until the next 4h bar (the known
  `unbooked_fill_unprotected` window) and R is undefined for it — treat
  such a leg as "wait".
- The $99k figure is 112,500 / (1.125 × 1.01) with lev 1.5 and base
  100,000; it moves with the blend lev the engine publishes.
- What is NOT modelled here: the HL mark-price vs Bitstamp bar difference
  on the halt fill, funding on the joined legs, and the carry sleeve's
  behaviour if the SAME event that drew down BTC also moved ETH funding
  through the 5% disarm (C1 would page separately).

Figure: `docs/resume_protocol_rails.png` (rails before the halt and after a
reanchored resume at 0.30; script `docs/resume_protocol_rails.py`).
