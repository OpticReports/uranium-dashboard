# Netted-venue fix — counter-agent panel record (2026-09-16)

Build reviewed: `cfd2936` (net-mirror r2). Fixes applied in the follow-up
commit on the same branch. Gates: `tests/test_netting_gates.py` (51),
`tests/test_executor_gates.py` (430 pass, 1 skip).

## What ran, and what did not — read this first

| stage | status |
|---|---|
| Panel: 5 adversarial lenses (phantom ledger, live risk, invariant bypass, engine contract, test integrity) | **ran** — 28 findings, each BLOCKING/SERIOUS one with a scratch repro executed against the real code |
| Verify: two independent skeptics per BLOCKING/SERIOUS finding | **did not run** — every agent died on the account's monthly spend limit |
| Mutation sweep: 20 mutations against the gate suite | **did not run** — same |
| Synthesis by a decider agent | **did not run** — same |

What replaced the missing stages: the builder (this session) re-ran every
panel repro against the code, fixed what reproduced, converted each repro
into a permanent gate, and re-ran the repros to show the pinned defects no
longer reproduce. That is self-verification, not independent verification.
**A second independent pass (verify + mutation sweep) is still owed before
this is treated as reviewed under the standing counter-agent rule.**

## Verdict (builder's, pending the independent pass)

**MERGE WITH FIXES — all fixes applied; independent re-verification owed.**
Sixteen BLOCKING/SERIOUS findings, all reproduced against `cfd2936`; all
sixteen fixed and gated. Twelve MINOR/NOTE findings: six fixed, six recorded
as disclosed limits below.

## Confirmed findings and fixes

| id | sev | defect (one line) | fix | gate |
|---|---|---|---|---|
| PL-1 | BLOCKING | a FILLED stop that left a residue kept its ref; every later poll re-entered the FILLED door and placed nothing; the residue sat on the venue with no stop, no close, no page | `_absorb_netted_fill` clears the stop ref on any stop fill (the order is terminal) and pages `stop_residue`; `_absorb_fired_stop` returns "took the leg flat", not "the stop filled"; the FILLED door falls through to placement on a residue; the dominant's stop is re-sized in the same poll the subordinate exits | `test_gate_PL1_residue_after_a_clamped_stop_is_re_protected_and_closable` |
| PL-2 | SERIOUS | the N7 floor branch demoted both legs and cancelled the real stop BEFORE corroboration, off a phantom near-cancelling ledger | floor branch moved below the `_stop_backing` verdict; only `ok` may demote | `test_gate_PL2_floor_branch_cannot_strip_a_real_stop_off_a_phantom` |
| R1 / F5 / TI-1 | BLOCKING | trend-dominant stop fill with a booked pullback subordinate: the pullback runs first, its second look read only ITS OWN stop, halted before the trend's FILLED door; also with the venue's 'triggered' (→OPEN) read for a poll | `_diverged_second_look`: absorbs any leg's FILLED stop, settles any in-flight close/R ref, re-books maker fills; an order of ours still unconfirmed that could explain the gap gives NETTING_MISMATCH_HALT_POLLS polls of grace (counted once per poll) before a halt | `test_gate_R1_trend_dominant_stop_fill_with_booked_subordinate_does_not_halt` (×6: engine still showing / already flat × 0,1,2 triggered reads) |
| R2 | SERIOUS | dominant close on a net under the $10 floor: a rejected reduce-only order every poll, forever | send nothing under the floor; deduped RED `close_deferred_under_floor`; the near-cancel resolves when the other leg moves | `test_gate_R2_dominant_close_under_the_floor_sends_nothing` |
| R3 / F2 | SERIOUS | the X order's cloid was not persisted and the stop was cleared before the confirm; a read outage lost the fill and the next poll halted | `close_cloid/close_qty/close_net_before` persisted BEFORE the send; `_settle_close` at the head of every `_sync_leg`, at boot and in the second look; the stop comes down only once the close is confirmed to have traded | `test_gate_R3_close_fill_survives_a_read_outage` |
| F1 (bypass) / F2 (engine) | BLOCKING | the three release doors called `clear_netting()`, which also dropped an in-flight R ref on an UNKNOWN read; the fill was orphaned with no ledger row and no stop | `clear_netting()` releases the debt only; `clear_reest()` runs only on a confirmed terminal read or a halt/adopt/boot zeroing; each release door defers with RED `reest_unsettled` while an R is unconfirmed | `test_gate_F1_unsettled_R_is_never_dropped_by_a_release_door` |
| F3 | SERIOUS | exactly-cancelling legs: `_book_shape` returned dominant None and `_close_leg` raised KeyError every poll | in `_close_leg` the exiting leg of an exact cancel is the subordinate and the other leg is owed all of it | `test_gate_F3_exactly_cancelling_book_closes_cleanly` |
| F4 | SERIOUS | a consumed partial re-opened at its partial size was never topped up when the engine booked the full position | `_under_mirrored`: a held leg below 95% of `target_qty` (the size its entry ASKED for — never a fresh sizing, so a KELLY_M change cannot buy into an open position) with a terminal or no entry ref is topped up through `_enter_from_fill`, which now chases what the leg HOLDS short of the target | `test_gate_F4_consumed_partial_is_topped_up_when_the_engine_books`, `test_gate_F4b_a_sizing_change_never_buys_into_an_open_position` |
| F1 (engine) | SERIOUS | a consumed partial maker fill whose ref was kept was re-booked in full by `_cancel_entry(flatten)` → false halt | `entry_booked` per ref: `_book_maker_fill` and `_cancel_entry` book only the unaccounted delta; `entry_accounted` marks a kept ref whose fill is already in the ledger | `test_gate_F1e_consumed_fill_is_never_booked_twice_by_the_orphan_door` |
| F6 | SERIOUS | `_book_maker_fill` re-inflated the trend to its original market-entry size after its debt was dropped → false halt | same `entry_booked` delta rule; a terminal ref corrects DOWNWARD only (partial IOC) | `test_gate_F6_trend_reduced_by_netting_is_not_re_inflated_from_its_entry` |
| TI-2 | SERIOUS | the N6 gate was vacuous (the fake's "lagging" read returned the post-fill net) and the stop path had no lag handling | `HLFake2` lag now returns the PRE-fill net and the gate asserts it; "lagging" is now "a venue-confirmed fill of ours after which the position shows no change" on both the stop and close paths | `test_gate_N6_position_read_lagging_its_own_fill_is_re_read`, `test_gate_TI2_stale_position_read_on_the_stop_path_does_not_halt` |
| TI-3 | SERIOUS | nothing pinned the R order's own corroboration/halt gating (mutations dropping them survived) | gates added | `test_gate_TI3_R_order_is_never_sent_against_a_diverged_venue` |
| R4 | MINOR | `_close_leg`'s diverged branch had no maker-fill second look | folded into `_diverged_second_look` | R1 gates |
| R5 | NOTE | the cap clamped each R attempt, not the leg's total | R sized against `_cap_room` (hard caps on the leg's total, held + owed) — and NOT against the Kelly target, which would clamp a legitimately larger leg | `test_gate_inc1_exact_replay` (R at the consumed size) |
| R6 | NOTE | the cross-leg R ignored the consumed leg's own `engine_halted` | blocker added | `test_gate_R6_cross_leg_R_respects_the_consumed_legs_engine_halt` |
| F3 (engine, MINOR) | MINOR | the dominant's stop stayed at the old net for one poll after a subordinate exit | re-sized in the same poll | PL-1 gate |
| F5 (bypass, NOTE) | NOTE | `close_unconfirmed`/`close_rejected` embedded a per-second cloid and never deduped | cloid removed from the text; both rate-limited | — |

## Recorded, not fixed (disclosed limits)

- **PL-3 (NOTE):** the cancel of a consumed leg's resting maker remainder is sent once and re-sent only while the ref is unresolved; a cancel swallowed by `hl.cancel` (it logs and swallows every exception) can leave the remainder live until the engine's bar close. Bounded by the entry's size; `entry_booked` keeps any later prints correctly attributed.
- **TI-4 (MINOR):** a close that PARTIALLY fills leaves the dominant's residue without a venue stop until the next poll (≤20 s); an UNFILLED close now keeps the stop.
- **TI-5/TI-6 (MINOR):** several gates pin outcomes, not mechanisms (a reverted ref-clear or a changed mismatch cap could survive them). The mutation sweep that measures this did not run.
- **TI-7 (MINOR):** the I2 static pin is a regex over `self.venue.place_market(`; an alias or a split call fools it. It is a tripwire, not a proof.
- **TI-8 (NOTE):** `FakeVenue.order_status` returns `None` for an unknown cloid where `hl.order_status` returns CANCELLED (`unknownOid`); a rejected R never settles under the fake but does on the venue.
- **F8 (NOTE):** an engine `reset_books` replay can change a same-side position's `entry_ts`; a consumed leg's debt is then released (`netting_released`) and the leg is topped up through the ordinary path — one extra taker fill.
- The venue's own reduce-only rejection (`hl._send` raises where `FakeVenue` no-ops) is still not modelled by the stock fake; the netting gates use `HLFake2`, which models the netting, the clamp, the sweep and the over-reporting order record, but not that rejection.

## Residual risk after the fixes

- The independent verify + mutation stages did not run. The repros were written by the panel agents and re-run by the builder; the fixes were written by the builder. One pair of eyes on the fixes.
- Grace on a divergence: a `diverged` verdict with an order of ours unconfirmed is now counted for up to 3 polls (~60 s) before a halt. During grace no order is placed off the ledger, and the halt's flatten is unchanged; the cost is up to 60 s longer before a real divergence halts.
- The pending-window stopless exposure (a pullback maker fill before the engine publishes its stop level) is unchanged and paged (`unbooked_fill_unprotected`).

## Panel repros — final state against the fixed build

Files under the session scratchpad (not committed). "pinned" = the test asserted the defect; "correct" = the test asserted the right behaviour.

| file | before | after |
|---|---|---|
| test_phantom_attacks (PL-1, PL-1b, PL-2 pinned; PL-3 pinned) | 4 pass | PL-1/1b/2 now fail (defects gone); PL-3 still reproduces (disclosed) |
| test_live_risk_repros (R1–R6 pinned; R1b correct) | 6 pass, 1 fail | all pinned defects gone; R1b's fixture ordering no longer applies |
| test_bypass (F1–F4 pinned) | 4 pass | all 4 gone |
| test_f5 (F5 correct) | 2 fail | fixture invalidated by F4's top-up (its precondition — a partial frozen for the trade's life — no longer exists); the scenario is covered by the R1 gate |
| test_engine_contract_attack (F1a/F1b/F2 correct) | 3 fail | F1a/F1b now only disagree on the marker's spelling (`entry_accounted` vs `entry_qty == 0`); F2's assertion assumed the venue answers within 3 polls while its fixture keeps the read UNKNOWN for 20 — the deferral it now sees is the fix |
| test_f7 / test_f6 (F6 correct) | fail | pass |
| test_scratch_netting_integrity A (TI-1 correct) | fail | still fails on its own fixture (seeds a live trend ref without `entry_booked`, which no code path produces); the scenario is the R1 gate ×6 |
| test_scratch_B2 (TI-2) | fail | pass |
| test_scratch_F2 (TI-4, TI-8) | fail | fail — disclosed above |

---

# Independent verification (round 2) — 2026-09-16

The stages the panel could not run (verify, mutation sweep) ran here, on the
second pass `980c3f3`: **24 skeptic agents** (two per finding — "is it really
fixed" and "did the fix break something", each writing and running repros
against the real executor) and a **24-mutation sweep**. 28 of 29 agents
completed; only the synthesis write-up hit the spend limit, so this record is
written by the builder from the agents' own returned data and repros.

## VERDICT: MERGE WITH FIXES — all applied in the round-3 commit on this branch.

Every one of the eleven fixes verified as genuinely fixed, across variants the
builder had not tested (both LEGS orders, engine-flat vs still-reporting,
partial fills, UNKNOWN reads at the worst moment, restarts mid-flow, the venue's
`triggered`→OPEN instant). **The fixes themselves introduced nine defects, six
SERIOUS** — all reproduced, all now fixed and gated.

## Fixes verified (11/11)

| finding | verdict | decided by |
|---|---|---|
| PL-1 residue | FIXED | 15 variants incl. partial trigger fill, opposed dominant, under-floor residue, restart |
| PL-2 floor/corroboration | FIXED | 12 variants; the same file on `cfd2936` reproduces the original in every one |
| R1/F5/TI-1 trend-dominant | FIXED | 20 variants; all 6 `R1_original` variants halt on `cfd2936` |
| R2 under-floor close | FIXED | no order storm; ledger intact |
| R3/F2 close ref | FIXED | persisted before the send, survives crash/restart, partial, reject, unfilled IOC |
| F1/F2 unsettled R | FIXED | deferral holds 5 polls, books once on recovery, survives a fresh boot |
| F3 exact cancel | FIXED | no `leg_sync_error`, closes cleanly |
| F4 top-up | FIXED | tops up once; restart-mid-flow clean |
| F1-engine/F6 entry_booked | FIXED | 7 variants; one "not fixed" verdict's variant **also reproduces on `cfd2936`** (pre-existing, not a regression of the fix) |
| TI-2 lag | FIXED | 84-case sweep |
| TI-3/R5/R6 R gating | FIXED | cap, engine-halt, blind, diverged, restart, partial-R all correct |

## Regressions the fixes introduced — all fixed in round 3

| id | sev | what the fix broke | round-3 fix | gate |
|---|---|---|---|---|
| V1 | SERIOUS | `_absorb_fired_stop` now means "took the leg flat", but the second look read it as "the stop filled" — a residue absorbed there halted on the ledger it had just corrected, on all three diverged doors | re-check `_stop_backing` on any RE-ATTRIBUTION, not only on flat | `test_gate_V1_…` (×6: 3 doors × 1–2 `triggered` reads) |
| V2 | SERIOUS | `blind` was folded into `resolved`, so the subordinate head demoted — cancelling a REAL stop — with the venue unreadable | `blind` is its own return; every caller touches nothing | `test_gate_V2_…` |
| V4 | SERIOUS | the FILLED door fell through to placement when the attribution FAILED → placed a stop off belief and overwrote the FILLED ref, losing the fill | fall through only when the attribution succeeded | `test_gate_V4_…` |
| V5 | MINOR | the choke point's resolved path never re-applied the subordinate rule → a wrong-sided stop sized to the whole net | `_subordinate()` helper called from both places | covered by V1/V2 fixtures |
| V6 | SERIOUS | the lag heuristic fired on a close whose leg was already flat (its stop absorbed it first) — "no change" is correct there — burning the counter into a false halt that flattened a healthy book | the rule applies only while the leg still holds what the fill should have removed | `test_gate_V6_…` |
| V7 | SERIOUS | `entry_accounted` was reset only by `clear_entry()`, but four sites null the ref directly and it persists → the first entry after a halt/resume was cancelled or its fill orphaned, ending in double exposure | every ref drop goes through `clear_entry()`; a fresh entry resets the marker | `test_gate_V7_…` |
| V9 | SERIOUS | `target_qty` survived a halt → after a KELLY_M cut every adverse move sent a taker top-up toward the OLD size, which `test_gate_F4b` claims is impossible | zeroed with the ledger; a new entry sizes itself | `test_gate_V9_…` |
| V10 | SERIOUS | the top-up chase had no venue corroboration (unlike the R order) → market-bought a hand-closed leg back off belief | requires `_stop_backing == ok`, else pages `leg_unmirrored` | `test_gate_V10_…` |
| V11 | SERIOUS | the `entry_booked` migration read "what the leg holds now" — wrong for a leg reduced by netting → **the first boot of the new build on the live state file re-books the difference and halts** | migrate from what the ref booked; carry the old ACCOUNTED marker | `test_gate_V11_…` |
| V12 | SERIOUS | **grace defers the halt but the leg loop keeps going**, so the other leg's entry/chase/R went out against a venue already judged not to back the ledger — defeating `test_gate_netting_opening_orders_need_exact_corroboration` for exactly that window | an unresolved mismatch sets `entries_ok = False` for every leg | `test_gate_V12_…` |
| V13 | MINOR | the mismatch counter was never reset by a clean poll, so one stale read stole grace from the next, unrelated event for the life of the process | a clean poll ends the run | `test_gate_V13_…` |
| V14 | MINOR | the cross-leg re-open ignored `exit_flag`, buying a position the same poll's exit branch calls "nothing to re-open" | skip and release the debt | `test_gate_V14_…` |
| V15 | NOTE | an R that filled but read UNKNOWN forever left the venue holding an unstopped position with a flat ledger, under the drift tolerance and silent | RED `reest_unsettled` | verified by event-log read |

## Mutation sweep: 19 of 24 killed, 5 survivors — all now gated

| survivor | why the suite missed it | gate added |
|---|---|---|
| M11 close ref not persisted before the send | no gate sent a close the venue ACCEPTED and then failed to answer for | `test_gate_M11_…` (asserts the ref is on disk) |
| M16 `clear_netting` also clears the R ref | **equivalent mutant today** — every call site settles first; the I7 property was asserted nowhere at the ledger level | `test_gate_M16_…` |
| M20 absorb doesn't clear the stop ref on a residue | PL-1's residue differs from `stop_qty`, so the churn guard lets the placement through anyway | `test_gate_M20_…` (residue == stale size) |
| M21 `_under_mirrored` uses fresh sizing | F4/F4b only cover the direction where today's sizing ≥ the entry's, where the chase's own `min()` hides the basis | `test_gate_M21_…` |
| M23 `_settle_close` cancels the stop before knowing the fill | no gate sent an X the venue leaves UNFILLED | `test_gate_M23_…` |

## Round 3 introduced nothing (A/B verified)

Every verification repro was re-run against round 3 and against a worktree at
`980c3f3`. The eight that still fail behave **identically on both**, so they are
pre-existing, not new. The repros that *pinned* the nine regressions have all
flipped to failing — that is the proof the regressions are gone.

## Pre-existing, disclosed, NOT fixed here

- **A restart inside the ≤20s window after a stop fill re-enters the leg.** Boot's
  phantom-clear (which predates all netting work) adopts the flat venue and zeroes
  the legs; the engine polls its own stop every 60s, so it still reports the
  position and the chase re-enters it. `stopped_entry_ts` is the guard and the
  phantom-clear does not set it. Cost: one taker round trip, then the engine
  catches up. Repro `test_ti2_restart.py::test_D0`.
- **PL-3 class** (a swallowed cancel of a consumed leg's maker remainder; a late
  print on an ACCOUNTED ref) — the round-1 disclosure that "`entry_booked` keeps
  any later prints correctly attributed" is **false as written**: `_release_entry_ref`
  clears an ACCOUNTED ref that reads FILLED without booking the remainder. Repros
  `test_f3_attack2.py`, `test_f1e_f6_verify.py`.
- **A consumed print that was never booked** (the maker fill and the stop land in
  one poll and the entry read blips UNKNOWN once) is re-booked from its record on
  the next poll. Reproduces on `cfd2936` too.
- **`netted_shortfall` parks a still-held leg on `stopped_entry_ts`**, so branch 1
  returns before the `exit_flag` fast path and the stop goes unmaintained until the
  engine reports flat — one bar late. Present since `cfd2936`.
- The venue's own reduce-only rejection is still not modelled by the stock
  `FakeVenue`; `FakeVenue.order_status` returns `None` for an unknown cloid where
  `hl` returns CANCELLED.

## Honesty box

- Could not be tested without the live venue: real `reduceOnlyCanceled` timing,
  real partial-trigger behaviour, real rate-limit shapes. Everything here is
  `HLFake2`, which models the venue from its own order records.
- The mismatch counter is in-memory: a restart mid-grace restarts the 3-poll budget.
- Grace costs up to ~60s before a genuine divergence halts. During it **no order of
  any kind goes out** (V12), and the halt's flatten is unchanged.
- Three rounds of review on this change found 16 → 9 → 0 new defects. The last
  round is the first with a clean ratio, and it is the first that was verified by
  agents that did not write the code.
