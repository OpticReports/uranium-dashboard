# Stop confirm after placement - specification and review brief (2026-11-14)

Status: built, reviewed by an independent counter-agent (premise), two independent verifiers and an
independent final check (section 6); committed on branch `claude/composer-verification-baseline-omeui0`;
NOT deployed. It deploys only with the owner's OK and only as described in section 7. Service:
btc-executor only.

This document is written so that a reviewer who was not in the session can review the change from it
alone: what went wrong, the evidence (kept in `docs/stop_confirm_evidence/`, because the venue's
public history will roll it out), the requirements, the design with file and line references, what was
verified and by whom, what is deliberately NOT covered, how to run everything, and a checklist
(section 9). Line numbers are in the patched tree unless marked "base". The base is commit 93f74553,
whose `btc-executor/app/` is byte-identical to build 709bf17, which the executor's public `/pulse`
reported as its running build at 13:01 UTC on 2026-11-14.

## 1. The incident

2026-11-14 04:01:10 UTC (Fri 23:01 ET), at the 4-hourly trail ratchet of the live trend SHORT
(0.45387 BTC on Hyperliquid, entry $74,375 per `clearinghouseState`), the executor paged:

> RED stop_unconfirmed: trend stop T-1794182400-S72638-45 not confirmed working (status=CANCELLED)
> - cancelled best-effort; position may be UNPROTECTED; attempt 1

The venue's own record (`historicalOrders`, read-only; `docs/stop_confirm_evidence/`):

| time (UTC) | event |
|---|---|
| 04:01:09.280 | the old stop -44 (trigger 73,941) canceled by the ratchet |
| 04:01:10.085 | new stop -45 (trigger 72,639, cloid 0x80c70e3a8e54cce130aef254f4242b2b) accepted, `open` |
| 04:01:11.098 | -45 `canceled` - by the executor itself |
| 04:01:33.123 | -46 placed by the next poll; it rested (the 16:01 ratchet replaced it with -47 at 71,726, from 16:01:08.937) |

The leg was without a venue stop for about 22.8 s. When checked at 13:02 UTC the same day the stop
sat about 8% above the market (mid $66,922; `live_state_2026-11-14T1302Z.json`); no fill or loss
resulted from the gap.

## 2. The evidence and the mechanism

**Venue record** (`docs/stop_confirm_evidence/btc_stop_order_history.json`: the BTC stop orders from
the account's `historicalOrders`, 2026-08-29 to 2026-11-14; `btc_stop_orders_attributed.txt`: each
order attributed to the executor's id format by brute force over entry_ts / leg / trigger / n, with
`attribute_cloids.py`, the method). 58 BTC trigger orders: 54 executor stops (T-1..47, P-1..7) and 4
drill orders. 11 were canceled within 2 s of placement: 8 executor stops and 3 drill cycles (a drill
cancels its own stop by design, base mirror.py 5641-5646). The 8 executor self-cancels had lifetimes
of 0.875-1.204 s, and the next placement came 22.663-23.916 s later each time (one 20 s poll). On
2026-09-18 three came in a row on one position (T-1789747200-S76265-15, -16, -17 at 20:00:24, 20:00:47,
20:01:10; -18 rested from 20:01:33): with `STOP_REPLACE_MAX = 3` (mirror.py:139) a fourth would have
halted the executor (`STOP_UNPLACEABLE`), and the halt would have flattened a healthy long. No two
executor stops on one leg were ever working at the same time in the record.

**Mechanism** (base line numbers), confirmed by an independent counter-agent and reproduced exactly by
replaying the live code against an info node that lags one read:

1. `_maintain_stop` burns `led.stop_n` (saved before the order) and builds the id
   `T-<entry_ts>-S<int(trigger)>-<n>` (mirror.py 4053-4055); `derive_cloid` (hl.py 80-91) maps it to
   sha256[:16] (T-...-45 -> 0x80c70e3a..., -46 -> 0xd871b4e7...).
2. It cancels the OLD stop by its own cloid (4056-4057), then places the new one (4060:
   `hl.place_stop` -> SDK `Exchange.order` -> POST /exchange). Base `place_stop` discarded the
   exchange's reply. The reply shape for a trigger order (assumed `{"statuses": [{"resting":
   {"oid": N}}]}`, as the test fakes model it) has never been captured live here.
3. It reads the new order's status at once (4081: `_ostat` -> `hl.order_status` ->
   `Info.query_order_by_cloid` -> POST /info `orderStatus`), a fraction of a second after the place
   returns (inferred from the 0.875-1.204 s lifetimes; not measured).
4. An info node that has not yet indexed the order answers `{"status": "unknownOid"}`; base
   `hl.order_status` maps that to CANCELLED / 0 (hl.py 620-622, "the venue affirmatively does not
   know this id"). `_ostat` re-reads only on UNKNOWN (1367-1370), so CANCELLED returns at once.
5. Anything but OPEN/FILLED bumps the per-position counter (4094-4095), sends a best-effort cancel for
   the order (cancel-before-clear, 4117-4127) - which cancels the HEALTHY stop on the venue ~1.0 s
   after placement - clears the refs and pages `stop_unconfirmed` (4128-4132).
6. The next poll (`poll_seconds` 20, main.py 187-209) sees no ref and places n+1, which confirms; a
   confirmed placement resets the counter.

**Alternatives ruled out** by the counter-agent: a second instance or client on the account (one
instance; no other cancel path matches the timing); a cloid collision (old and new ids derive to
different cloids, verified for -44/-45/-46/-47); the venue cancelling by itself (it would use statuses
such as `reduceOnlyCanceled`; these are plain `canceled`, i.e. a cancel request); the vanish handler
(it runs at the head of `_maintain_stop`, patched :4012-4015, but sends no cancel, and at 04:01 the
head read found -44 OPEN - the page said attempt 1). A cancelled order stays queryable as `canceled`;
only a never-indexed id answers `unknownOid`, so for an order the exchange accepted, `unknownOid`
means "not indexed yet".

## 3. Requirements (what the fix must do)

Owner-approved scope (2026-11-14, in the session): "before treating a just-placed stop as dead,
re-check its status a few times over about 3 seconds; keep everything else as is, including
cancel-before-clear when it really is dead."

- R1 A just-placed stop is not judged dead on one read: a bounded confirm of at most ~3 s of sleep.
- R2 OPEN or FILLED on ANY read confirms at once; nothing is read after a hit.
- R3 A CANCELLED that carries a venue record (any raw status other than `unknownOid`, or no raw at all
  - Coinbase, DryRun) is final at once: a venue that really refuses or kills a stop is handled exactly
  as before, with no delay.
- R4 No record (`unknownOid`, a non-dict reply), UNKNOWN, no handle, or a read that raises is re-read
  within the window.
- R5 Still not OPEN/FILLED after the window -> the OLD path, unchanged: one count per poll,
  `STOP_REPLACE_MAX`, `STOP_UNPLACEABLE` with the cloid handed to the halt, cancel-before-clear, the
  `stop_unconfirmed` page (its old text kept as an exact prefix).
- R6 A late confirm resets the counter exactly as a first-read confirm does, and is logged (INFO,
  never paged) so the window can be tuned from live data.
- R7 Every other caller of `hl.order_status` sees exactly what it saw before (only `_confirm_placed`,
  mirror.py:1429, reads `raw`).
- R8 Never two working stops for one leg; never a ledger that believes in a stop the venue does not
  hold.
- R9 The stop placement's ack decides nothing: it feeds only the page and the lag event. Both reply
  parsers (`_ack_from_response`, and `_fill_from_response`, whose result DOES book a single-leg close
  when it parses) never raise: a reply shape they do not know gives None, which for the fill parser is
  its documented "no usable answer, settle later" path.
- R10 Coinbase keeps working: its explicit statuses stay final at once.

## 4. Design (patched tree)

`app/hl.py`
- :68 `NO_RECORD_RAW = "unknownOid"`.
- `order_status` (:613-716; the edited comment at :710-714): a reply with no record still returns
  CANCELLED / 0 (R7), now tagged `raw="unknownOid"`; a non-dict reply logs a warning.
- `place_stop` (:853-890) returns the exchange's acceptance via `_ack_from_response` (:893-908):
  `{"accepted": "resting"|"filled"|<a bare status string>, "oid": N|None}` or None (a bare string such
  as "waitingForTrigger" carries no oid). The order sent is unchanged (reduce-only stop-market at the
  snapped trigger). The ack is evidence only (R9): the live reply shape is unverified, and believing
  an acceptance would let a venue that accepts and then kills look healthy.
- `_ack_from_response` and `_fill_from_response` (:941) catch every exception (R9; section 6's final
  follow-up).

`app/mirror.py`
- :151 `STOP_CONFIRM_DELAYS_S = (0.5, 0.75, 0.75, 1.0)`: reads at ~0 / 0.5 / 1.25 / 2.0 / 3.0 s, at
  most 3.0 s of sleep and 4 extra reads (about 4.5-6 s of wall clock with 0.3-0.6 s per read - a
  modelled latency, not a measured one).
- :155 `NO_RECORD_RAW` (spelled as in hl; a test pins that). :214-218 the Venue protocol's
  `place_stop` now returns `dict | None`.
- `_confirm_placed` (:1392-1434), used ONLY at the stop placement (`_ostat` is untouched): R2, R3, R4.
- `_maintain_stop` (:3902-): captures the ack; calls `_confirm_placed` instead of the single read; a
  REJECTED placement is still not read at all; an unresolved window takes the old path (R5); the page
  appends what the confirm saw, e.g. " (5 status read(s) over 4.8s, last raw unknownOid, venue ack
  resting oid N)" - the span is measured; a confirm that needed more than one read logs INFO
  `stop_confirm_lag` (:4227); a late confirm resets the count (R6). The `_bump_stop_vanish` docstring
  no longer says "~1s window".

`tests/`: the new merge-blocking file `test_stop_confirm_gates.py` (its module docstring restates
sections 1-4) and ONE edited existing gate: `test_executor_gates.py::test_gate_confirm_blip_cancels_before_clearing`,
whose blip count went from 2 to `1 + len(STOP_CONFIRM_DELAYS_S)` (healed after the call) so that it
still pins "never confirmed -> cancel before clearing, and the next poll has exactly one stop"; it
passes on the base and on the fix.

`EXECUTOR.md`: the BOUNDED row no longer says "~1s window"; a new row "a just-placed stop gets a
BOUNDED CONFIRM" states the behaviour, the cost and what is not covered; the belief-asymmetry note is
corrected ("safe for the LEDGER, but not free").

**Cost.** Nothing when the first read confirms. 46 of the 54 live placements were never self-cancelled
(an UNKNOWN read followed by the old 1 s retry would look the same in the venue record). For a
placement whose first read finds no record: up to 3.0 s of sleep plus 4 status reads, inside the
venue lock, so `/kill`, `/resume`, `/drill` and `/coverage/attest` (the last two give up after 30 s)
wait that much longer; `/health`, `/pulse` and `/status` do not take the lock. A poll can place more
than one stop (one per leg, plus the dominant's re-size after a netted exit), so its worst case is a
multiple. Coinbase: an UNKNOWN read now gets up to 4 re-reads over 3 s instead of one after 1 s.

**A side effect the final check found (positive).** On the base an object-shaped `statuses` in an IOC
reply raised KeyError out of `place_market` AFTER the IOC executed; on the trend market entry
(mirror.py:2964) that left the fill unbooked and the next poll sent a SECOND entry. With the widened
fill parser the entry is sent once and booked by intent. No such reply shape is known to be sent.

## 5. NOT covered (honesty box)

| Item | Consequence | Status |
|---|---|---|
| a lag longer than the window | still self-cancels exactly as before; visible only in the page's appended detail; `stop_confirm_lag` records only caught lags; both rotate out of the 200-entry event log in ~1 h | accepted; harvest Render logs before tuning; the complete fix is an age-aware no-record rule like the close path's `CLOSE_SETTLE_MIN_AGE_S` |
| a stop that FIRES inside the window while the lag outlasts it | the window ends unresolved, the cancel is a no-op on the filled order and the ref is cleared, so the fill is booked nowhere and the next poll halts `LEDGER_DIVERGENCE` (needs an operator `/resume`) | WIDENED by this change: the exposure was the ~1 s before the old cancel, now the whole window (verifier A reproduced it) |
| a crash between the placement and the end-of-step save | the new ref is persisted only by the end-of-step `_save_state` (mirror.py:2533/2547), so the window runs from the placement to the end of the step (the other leg and its own window, then `_poll_fill_watch`), now +3.0 s of sleep and 4 reads per lagging placement. After a ratchet, the reboot's head read finds the persisted OLD ref `canceled`: it pages `stop_vanished`, counts 1 toward the cap and arms a second reduce-only stop beside the orphan. After a FIRST placement (no old ref) the second stop is armed with no page and no count | disclosed; deploy precautions in section 7 |
| head read of an EXISTING stop | a no-record answer still reads CANCELLED: the stop is taken as vanished, its ref cleared WITHOUT a cancel and another reduce-only stop armed beside the live one (stacking; counts via the vanish door). This change makes it somewhat likelier (verifier B's two-node model stacked 4 stops against the base's 3) | pre-existing, never seen in the venue record; owner decision |
| fill-watch after a LATE confirm | a stop confirmed late gets a fill-watch read at the end of the same step, which can land on the lagging node and drop the watch; when the stop later fills there is no trade_pnl line or slippage sample (the fill still pages `stop_filled_on_venue`) | NEW with this change (on the base the stop was self-cancelled instead); out of scope |
| pullback maker-entry confirm | two no-record reads clear the entry ref; the next poll can send a SECOND maker entry beside a live one | pre-existing, SERIOUS per verifier A; strict xfail `test_latent_pullback_entry_no_record_sends_a_second_entry`; owner decision |
| `_reestablish` settle | `place_market`'s fill answer is discarded; one no-record read books a FILLED R order as unfilled, leaving a venue leg with no ledger row and no stop (with an odd reply shape, the widened parser now settles at once through this same site instead of a poll later) | pre-existing, SERIOUS per verifier A; strict xfail `test_latent_reestablish_no_record_leaves_the_leg_unbooked`; owner decision |
| the drill's and the halt verify's reads | unchanged single reads | pre-existing, out of scope |

## 6. Verification record

| Step | Who | Verdict | Key findings |
|---|---|---|---|
| Premise | independent counter-agent, before any build | CONFIRMED | mechanism reproduced from the live code; 8 (not 11) executor self-cancels; the 09-18 triple; the fix belongs at the placement site in mirror.py, not inside `hl.order_status` (~20 callers); found the two latent sites |
| Build | fixer | - | 16 gate cases fail on the base and pass; 23 twins pass on both; 2 strict xfails; 24 of 24 mutants killed; suite 642 passed + 2 xfailed (603 on the base) |
| Verify A (order paths on a lagging simulated venue) | independent | FIX-THEN-SHIP | sound: one stop at every instant under lags of 0.3-3.9 s; genuine failures still halt at the cap; /kill during the window waits and flattens; no new pages. MINOR introduced: the ack parser's narrow except (KeyError) could turn an accepted stop into a self-cancel. Two SERIOUS pre-existing out-of-scope sites (section 5) |
| Verify B (venue semantics, evidence, Coinbase, docs) | independent | FIX-THEN-SHIP | the same MINOR; the head-read stacking (MINOR, pre-existing); notes on the window's wall-clock cost, telemetry gaps, deploy runbook additions |
| Follow-up | author | - | both parsers catch every exception; two gates against the FIRST CUT (an object-shaped `statuses` never turns an accepted stop into a raise; both parsers never raise on an odd shape - its 3 object cases gate the first cut, its string and integer cases pass on it); EXECUTOR.md wording; suite 648 passed + 2 xfailed |
| Final check (the follow-up, and this spec read as a newcomer) | independent | FIX-THEN-SHIP: code sound, no new code defect; widening both parsers safe on every caller path (2 of 2 mutants killed) | the spec corrections applied in this version: the deploy action and route, a pre-check `/status` cannot answer, the unverified reply shape, the residuals added to section 5, the side effect in section 4, precise line spans and wording |

## 7. Deploy plan (only with the owner's OK)

- **The push to main IS the deploy**: btc-executor has `autoDeploy: true` with a buildFilter on its
  own paths, so the commit that changes `btc-executor/app/**` redeploys it when it lands on main.
- **Route**: cherry-pick ONLY this change's btc-executor commit onto main (its paths are
  `btc-executor/**` alone) and push that. NEVER merge the branch for this deploy: the branch carries
  other unmerged work (see `git log origin/main..<branch>`; 15 commits at the time of writing) that
  changes ibkr-executor and composer/scripts, whose services auto-deploy too and await their own OK.
- **When** (the checks below gate the PUSH): away from the 4 h bar boundaries (not within HH:58-HH+:03
  of 00/04/08/12/16/20 UTC), after the current bar's ratchet has landed (a new trigger visible on the
  venue), and not right after an entry fill.
- **Before**: `/pulse` shows `halted` null, the expected `build`, and both legs' `entry_open` false;
  `/status` shows no in-flight close or re-establish, and its events show no `stop_unconfirmed` or
  `stop_vanished` since the last confirmed placement (`/status` does not expose the `stop_vanish`
  counter; reading it means reading the state file on the Render disk); the venue holds exactly ONE
  reduce-only BTC trigger for the trend leg - match it by size and by trigger within a tick (`/status`
  shows the unsnapped engine trigger, e.g. 72638.6 against the venue's 72639) or by `derive_cloid` of
  the id `/status` shows (the venue stores the derived cloid, not the human id).
- Render stops the old instance before starting the new one (persistent disk), so the resting stop is
  the only protection during the gap - which is why the venue check matters.
- **After**: `/pulse` shows the new build and `legs.trend.stop_placed` true; no `stop_unconfirmed`,
  `stop_vanished` or `step_failed` events; the venue still holds exactly one stop; at the next ratchet,
  watch for INFO `stop_confirm_lag`.
- **Rollback**: revert the cherry-picked commit on main and push (it auto-redeploys). No environment,
  render.yaml or state-format change, so build 709bf17's code reads the state this build writes.

## 8. How to run

From `btc-executor/` with its pinned requirements (hyperliquid-python-sdk 0.24.0, coinbase-advanced-py
1.8.4) and `render.yaml` present at the repository root (one gate reads it):

    python -m pytest -q -p no:cacheprovider tests/test_stop_confirm_gates.py
    python -m pytest -q -p no:cacheprovider tests            # the whole suite: 648 passed, 2 xfailed

The gate file needs no network and no real SDK: it builds the REAL `HyperliquidVenue` over a fake SDK
whose info node lags its exchange by N reads per order. Re-derive the evidence with
`python3 -I docs/stop_confirm_evidence/attribute_cloids.py <a historicalOrders JSON dump>`.

## 9. Review checklist

1. Is the diagnosis right? Re-derive section 2 from the code and from `docs/stop_confirm_evidence/`
   (the venue's live `historicalOrders` keeps only the most recent orders, and this account's other
   activity will push these rows out).
2. Do `_confirm_placed` and its call site meet R1-R6 exactly? In particular: an explicit venue record
   is final at once (R3); nothing is read after a hit (R2); the unresolved path is byte-for-byte the
   old one (R5); a late confirm resets the counter (R6).
3. Can any path now leave two working stops for one leg, or a ledger believing in a stop the venue does
   not hold (R8)? Consider a lagged read that turns OPEN late, a genuine cancel that reads OPEN late, a
   fill or a trigger inside the window (section 5 records one widened residual), the ratchet (cancel
   old, place new), the opposed / netted book, and a crash inside the window.
4. Is every other caller of `hl.order_status` unchanged (R7)? Do the reply parsers never raise (R9),
   and is a None from `_fill_from_response` safe on each of its callers (mirror.py :2964, :3119,
   :2068, :3832, :5310, :5421)?
5. Is Coinbase unchanged apart from the documented UNKNOWN window (R10)?
6. Do the gates fail where they say they fail? Most fail on the base and pass on the fix; the two
   follow-up gates are against the FIRST CUT (the odd-ack gate passes on the base by design). Do the
   twins pass on both, and do the strict xfails still fail for the stated reason?
7. Is the cost acceptable: up to 3.0 s of sleep (about 4.5-6 s of wall clock) inside the venue lock,
   per lagging placement?
8. Are the NOT-covered items (section 5) correctly described, and should the owner widen the scope to
   the two SERIOUS pre-existing sites and the head read before or after deploying this?
9. Is the deploy plan (section 7) safe for a live book holding a position and a resting stop?

## 10. Also pending review on this branch: the IBKR mirror, rounds 4-7

A separate service (ibkr-executor and the composer brain), on the same branch and also not on main yet:
the half-day rule, the open-orders (K5) replacement schedule, the buying guard and the scale-up
planner. Every round's verdicts, the final two-reviewer comparison against main (c1aaca77), the open
items and the pending owner decisions are in `composer/research/mirror/reviews/rounds4-7-2026-11-14.md`;
the behaviour is documented in `composer/IBKR_MIRROR.md`. Its round snapshots are 170191c0, 33850e01,
952177fa and 4f4282c1, and 93f74553 holds its final review fixes and the review log; the full list of
unmerged commits is `git log origin/main..claude/composer-verification-baseline-omeui0`.
