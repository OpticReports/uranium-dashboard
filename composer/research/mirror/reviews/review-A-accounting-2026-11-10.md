**Verdict: SHIP-BLOCKED** — 2 BLOCKING, 9 SERIOUS, 9 MINOR, plus notes. The paper stage is affected too: A-12 and A-23 let a paper book hold up the live blend's loop.

`report.md` was not written: the harness refuses report files from subagents, so this message is the report. The repro tests, harness and run script are on disk.

- **Reviewed:** `ibkr-executor/` at eca49668. HEAD has since moved to 7f4b1060, but `git diff eca49668 HEAD -- ibkr-executor` is empty, so the reviewed code is the current code. No tracked file was edited.
- **Repros:** 34 failing tests (one per defect facet) and 15 passing probes, in `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/`.
- **Run all:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/run.sh /tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A --show-capture=no` gives `34 failed, 15 passed`.
- **Harnesses:** the author's own `Rig`/`Venue` doubles from `tests/test_mirror.py`, and `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/ibrig.py`, which drives the manager through the real `IBAdapter` over the repo's `FakeIB`, shaped after the installed ib_async 2.1.0.

Line numbers are `ibkr-executor/app/...` at eca49668.

## BLOCKING

### A-01 BLOCKING: a halt or /kill landing mid-tick does not stop the plan; a /resume mid-flatten does not stop the flatten
- **Where:** mirror.py:434 (halt read once per tick), 650-671 (`_decide` → `_start` → `_drive`, no re-read), 820-828 (`_drive` checks the halt only after `_advance`), 842-866 (`_advance` places every sell, then sizes and places every buy in one call), 1128 and 1161 (`cancelled` read once per flatten step).
- **What happens:** between "tick started" and "first order" there can be 25 s of intents read plus 45 s of quote check, then N orders at up to 10 s ack or 6.5 s fill wait each. A halt anywhere in there is acknowledged to the operator and the whole day's plan still goes out. With /kill, the flatten then sells what was just bought. This is the MF2-5 / MF3-5 class the repo already treats as merge-blocking; M10 only halts between two ticks.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a01_halt_mid_plan.py`
  - a: `6 NEW orders reached the venue AFTER the halt was in force: [('BOXX', -238), ('PULS', -448), ('SOXL', -271), ('TECL', -108), ('SPY', 72), ('TQQQ', 697)]`
  - b: `/kill was acknowledged before any order existed, yet 5 BUY orders were sent afterwards`
  - c: `/resume answered flatten_cancelled=True after the first sell; the flatten then sold 5 of 5 positions anyway ... book now {}, halted=False`
- **Smallest fix:** re-read `halt_state()` wherever a new order can originate: in `_decide` before `_start` and again before the run is saved; in `_work` before every `_place`; in `_advance` before `size_buys`. Flatten orders re-read `flatten_cancelled`.

### A-03 BLOCKING: /kill, /resume, /kill before the first flatten settles sells the same shares twice
- **Where:** mirror.py:300-301 (`halt()` rebuilds the record when not halted, dropping the flatten keys that /resume had only marked cancelled); 1135-1158 (`_flatten_step` replaces `state['flatten']` on an id mismatch without cancelling or booking the old orders).
- **What happens:** it needs flatten orders that rest (a trading halt, or the fallback 09:30-16:00 clock on a holiday or half-day afternoon). The second kill builds a new flatten from a book and an account that both still hold everything. A flatten whose cancel is stuck would make the window unbounded (read, not run). Variant b: resume then /mirror/halt leaves five working sells with no record.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a03_kill_resume_kill.py`
  - a: `the account is SHORT after two kills: {'BIL': -315, 'BOXX': -238, 'PULS': -448, 'SOXL': -271, 'TECL': -108}`
  - b: `5 flatten SELL orders are still WORKING at the venue with the book halted 'positions kept' and no flatten on record`
- **Smallest fix:** `halt()` carries an unfinished flatten's keys over, so a re-kill un-cancels the same id. `_flatten_step` never replaces `state['flatten']` while any of its orders is unbooked; it settles the old one first.

## SERIOUS

### A-02 SERIOUS: one unresolved order blocks the /kill flatten of every other symbol and every later session, with no operator override
- **Where:** mirror.py:900-904 (`placed` + find None → `_stuck`, under abort too), 1131-1134 (flatten refuses to start while a run exists), 476-478 (2 s then 60 s cadence indefinitely).
- **What happens:** the real adapter answers None for an acknowledged order that died unfilled once the session has turned over and completed orders are unavailable (ib_adapter.py:1387-1403; the gateway is recorded at 879-885 as never answering reqCompletedOrders). No route can book or drop the order; the only way out is hand-editing the JSON on the Render disk. M8 never sends a kill.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a02_stuck_order_blocks_kill.py`: `/kill sold 0 orders; the book still holds {'BIL': 315, 'BOXX': 238, 'PULS': 448, 'SOXL': 271} a day later, flatten_done=False, run still open=True, next_wait=5.0`
- **Smallest fix:** flatten every symbol that has no unresolved order; add an authenticated `POST /mirror/resolve {id, filled, price}`; re-alert daily while a run is stuck.

### A-07 SERIOUS: after an overnight outage a filled order is booked as "never reached the venue", or wedges the run (real adapter)
- **Where:** mirror.py:887-890 (`intent` + find None + past → book 0); 900-904 (`placed` + find None → stuck). The adapter's own rule, `history_complete()` at ib_adapter.py:996-1002, is never consulted.
- **What happens:** `place_stock_order` returns only after its fill and commission waits, so each order can sit at the venue for up to 6.5 s with only `intent` on disk. The service autodeploys on any push under `ibkr-executor/app/**` (render.yaml:845-863) and a restart waits on a 2FA approval. The next day reqExecutions covers today only. The book then disagrees with the account: pre-trade refuses every session, the flatten does not know the shares, and there is no repair tool.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a07_history_horizon.py`
  - a: `the account holds {'BIL': 315}, the book {}; the run was closed with BIL booked as (0, 'never reached the venue'); book cash $100,000.00 vs account $71,176.50`
  - b: `a day later the run of 2026-11-10 is still open on an order the account filled (stuck='the venue has no record of an order it acknowledged'); 2026-11-11 was neither traded nor recorded`
- **Smallest fix:** in `_work`, a None for an order whose intent is not from today (ET), or with `ad.history_complete()` False, is unresolved, never zero. Pair with A-02's resolve route.

### A-04 SERIOUS: when the state file cannot be written, the book keeps trading from memory with no write-ahead record
- **Where:** mirror.py:254-259 (`_save` raises after memory advanced), 879-881 (`rec['state']='intent'` set before the save), 409-412 (tick swallows the error and says it once), 433 and 388-390 (`_drain_inbox` is the first statement of `_tick`).
- **What happens:** each tick fails at its first save and the next resumes from the advanced in-memory state, so the whole plan reaches the venue with nothing changed on disk. Separately, an inbox that cannot be rewritten kills every tick before the halt path, so a queued flatten never starts.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a04_save_fails.py`
  - a: `5 orders were sent to the venue while the state file could not be written (disk: run=None, last_session=None, book cash $100,000; venue now holds {...}); halted=False`
  - b: `/kill: no flatten order in 100 s; the tick dies in _drain_inbox before it reaches the halt`
- **Smallest fix:** a failed `_save` sets an in-memory latch that forbids every `_place` and re-alerts each tick until a save succeeds. Set `rec['state']` only after the save returns. Wrap `_drain_inbox` so the halt and flatten path always runs.

### A-05 SERIOUS: "never borrow" does not hold at the account level
- **Where:** mirror.py:726-733 (a venue quote up to 1.5% from the brain's price passes and is then discarded), 859 (`size_buys` is passed `None` for prices); mirror_core.py:413-415 (buys costed at brain price × 1.003), 355 (no floor on a buy), 235 (a sleeve in debt inside its corridor holds).
- **What happens:** with the tape 1.2% above the brain's bar, every symbol passes the check and the account ends the first session at −$726.89 on $100,000. The threshold sleeve is still −$213.40 a session later. On a margin account that is a loan; on a cash account the last buys are refused.
- **Repro:**
  - `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a05_borrow.py` — a: `the ACCOUNT's cash is $-726.89 after one session`; b: `still borrowed a session later: {'KMLM': -213.4} ... 'KMLM': 'hold: inside the corridor: largest gap 0.3% vs 10%'`
  - `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_s02_core_fuzz.py` (`test_a05c`): `book cash went as low as $-369.22`
- **Smallest fix:** keep the quotes `_venue_prices` already read and pass `max(ref, quote)` to `size_buys(prices=...)`. Make the cushion at least as wide as the band. Treat negative sleeve cash as outside the corridor and exempt debt-repair trims from the dust rule.

### A-24 SERIOUS (suspicion, no repro): IBKR may refuse these buys outright on this account
- **Where:** mirror_core.py:43-44 (0.3% reserve, 0.3% cushion) against blend.py:203-232. From 2026-10-07 to 10-26 every market buy sized within one share of available cash came back Inactive on this account; the blend now sizes market buys 5% above the quote and holds 2% back.
- **What would happen:** sells fill, buys are refused, sleeves sit in cash. The manager books 0 and does not resend (probe p2 passes), with a warn-level alert only.
- **No repro:** it is IBKR's credit check. `IBKR_MIRROR.md` lists the account type as an open owner question; a cash account also raises whether same-minute sale proceeds can fund the buys at all.
- **Smallest fix:** before stage 3, place one real market buy sized to 99.4% of free cash on the real account. Otherwise adopt the blend's cushion or use marketable limits.

### A-06 SERIOUS: an unreadable brain clock is a silent no-trade day
- **Where:** mirror.py:451-452 (returns before `_skip` can record), 480-484 (`next_wait()` is None when today's session is unknown, so the loop parks 300 s against a 175 s window).
- **What happens:** no trade, no history row, no alert. Yesterday's leveraged holdings are kept while Composer rebalances. A brain that comes back at 15:54 is still missed on about one loop phase in five (my estimate: 60 s of each 300 s cycle).
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a06_clock_unreadable.py`
  - a: `a whole session went by untraded with 0 alerts and no history row`
  - b: `next_wait() is None with today's session unknown`
  - c: `brain up from 15:54, session lost anyway: missed the decision window: the brain's clock is unreadable (transport)`
- **Smallest fix:** when the session is unknown on a weekday 09:00-16:10 ET, `next_wait()` returns 20 s; red alert after N minutes; write a skip row at the fallback close.

### A-13 SERIOUS: the new `stock_order_fills()` misses executions the adapter already holds (real adapter)
- **Where:** ib_adapter.py:1525-1552 reads only `trade.fills` and `orderStatus.filled`. ib_async 2.1.0 builds a completed-order Trade with no fills and `filled == 0`, and never attaches an execution it stored earlier. `_result_from_executions` (929-967) reads `ib.fills()` by orderRef and gets it right.
- **What happens:** when completed orders time out at connect and answer on a later refresh, a partial fill cancelled at the close is booked as 0. A filled order is booked at the reference price, and its commission can never be trued up (dropped silently after 3 days, mirror.py:1110-1114).
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a13_fills_lookup.py`
  - a: `TECL booked 0 of 108 (cancelled (no venue reason recorded)); the account holds 40, the book None`
  - b: `PULS booked at 49.5 (the brain's reference), the venue's executions say 49.80: book cash $463.50 vs account $328.10`
- **Smallest fix:** when the trade has no fills, fall back to the execution store by orderRef. Answer `filled_qty: None` when neither source is conclusive.

### A-21 SERIOUS: the /kill flatten is one shot
- **Where:** mirror.py:1161-1181 marks the flatten done as soon as every order is booked, whatever filled.
- **What happens:** one refused or venue-cancelled sell and the flatten is done with the shares still on; `next_wait()` returns to None. The blend's flatten is retried every cycle (service.py:890-896).
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a21_flatten_gives_up.py`: `five minutes after /kill the book still holds {'SOXL': 271}; flatten_done=True, next_wait()=None, SOXL sells sent: [-271]`
- **Smallest fix:** while book and account both still hold shares, rebuild the flatten for the remainder under a new id suffix, with bounded tries and an alert each try.

### A-16 SERIOUS: "could not read what the cancelled order executed" is booked as "executed nothing"
- **Where:** mirror.py:980-984. A raise from `stock_order_fills` is noted and qty stays 0; every other unreadable answer in `_work` and `_settle` leaves the order unresolved.
- **Also:** for a session trade with no fills, that call forces a venue-history refresh (ib_adapter.py:1535-1538). On a gateway that does not answer reqCompletedOrders that is up to 20 s per rejected order, and a timeout on open orders disconnects the session mid-run. This part is inferred from the code, not measured.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a16_fills_lookup_raises.py`: `the run was closed: TECL booked 0 shares while the account holds 40; the lookup that would have said so raised`
- **Smallest fix:** on exception call `_stuck(...)` and return False. Skip the refresh when the trade is already in the session.

## MINOR

### A-23 MINOR: the loop thread's emergency-stop work waits behind the mirror tick's blocking calls
- **Where:** service.py:899-902, 1260; mirror.py `INTENTS_DEADLINE_S`, `QUOTE_BUDGET_S`.
- **What happens:** only the mirror's sleeps wait on `wake`. The blend flatten and ladder closes wait for the brain read (25 s, paper too), the quote check (45 s) and every order of a phase. The /kill alert still quotes only the two feed deadlines (service.py:1889-1890).
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a23_kill_waits_behind_the_mirror_tick.py` (real service loop): `the loop thread got back to its emergency-stop stage 3.0 s after /kill: it sat in the paper book's brain read`
- **Smallest fix:** wait for the brain worker on `wake`; check `wake` between quote symbols and between orders; state the bound in the alert.

### A-12 MINOR: static refusals hold the single loop thread for the whole tick budget, every session
- **Where:** mirror.py:652-668.
- **What happens:** every pre-trade failure is retried every 3 s. The loop is parked from 15:55:05 to 15:57:35 and again to 15:58. A paper book with `MIRROR_CAPITAL_USD` at its default 0 does this inside the live blend service.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a12_static_reason_busy_wait.py`: `one tick held the loop thread for 150 s (50 retries) on 'the blend strategy is still enabled...'` and `the PAPER book held the loop thread for 150 s (50 retries) on 'the book has no sleeve to trade'`
- **Smallest fix:** skip at once on static reasons (blend enabled, no sleeve); retry only transient ones.

### A-08 MINOR: stage 3 stops the paper book
- **Where:** mirror.py:206-210, 548-556.
- **What happens:** the private DryAdapter keeps the shares of the sleeve that went live, so pre-trade refuses every paper session until a later restart. M15 drops the sleeve and never trades again.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a08_paper_book_after_graduation.py`: `the paper book of the three remaining engines did not trade: ... PULS: the book holds 146, the venue 448`
- **Smallest fix:** rebuild the paper adapter's positions from the book after `_reconcile_sleeves` drops a sleeve.

### A-09 MINOR: a small transfer is silently short-changed
- **Where:** mirror_core.py:247, 393-396; mirror.py:771-772, 797-800.
- **What happens:** a transfer under the dust floor sells nothing, moves only the giver's cash reserve, is consumed, and is reported nowhere. The same applies to a transfer caught by an aborted run. This breaks "the same amount, the same day".
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a09_small_transfer.py`: `asked $300.00 KMLM -> HARV, moved $133.00 (status 'partial'); KMLM decided 'hold' (at target); notes=[] ... KMLM cash now $0.00; the request is consumed`
- **Smallest fix:** note and red-alert on `partial` and re-queue the remainder. Exempt forced trims from the dust rule, or refuse sub-floor transfers at request time.

### A-14 MINOR: the "cannot happen" guard fires and halts the live book on a healthy day
- **Where:** mirror.py:786-790, 771-772.
- **What happens:** the quote check drops the giver, so the transfer is refused in the rebuild. The taker now trims a symbol that was at target with the inflow and was never checked. That raises `MirrorError`, the book halts, and the transfer is gone from memory.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a14_unchecked_symbols.py`: `[disk still has 1 request(s); memory has 0] the live book HALTED itself: "book error: the rebuilt plan trades unchecked symbols ['SOXL']"`
- **Smallest fix:** quote-check the extra symbols; skip the session instead of halting; restore `state['requests']` on any raise in `_start`.

### A-11 MINOR: an order that turns Inactive after its ack is booked dead and left at the venue
- **Where:** mirror.py:978-986; ib_adapter.py:1098-1114.
- **What happens:** the adapter's own note says Inactive "can go LIVE later", which is why placement cancels it on sight. `_settle` books it as cancelled and sends no cancel.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a11_inactive_not_cancelled.py` (real adapter): `the run is closed with TECL booked 0 ... and NO cancel was sent (cancels=[]); the order is still at the venue as 'Inactive'`
- **Smallest fix:** expose the raw status; cancel before booking a `cancelled` answer that is Inactive, then re-find.

### A-17 MINOR: new orders go out after the cancel instant on a slow venue
- **Where:** mirror.py:846-848, 863-864.
- **What happens:** `past` is evaluated once per phase, not per order. A DAY market order arriving after 16:00 would rest for the next open.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a17_orders_after_the_cancel_instant.py`: `NEW orders sent at or after the 15:59:00 cancel instant: [('SOXL', '15:59:13'), ('TECL', '15:59:39')]`
- **Smallest fix:** re-evaluate `past` inside `_work` before each placement.

### A-10 MINOR: a halt whose file write failed is reported as a halt and lost on restart
- **Where:** mirror.py:321-326; service.py:937-944.
- **What happens:** `_write_halt` swallows the error and `halt()` returns the same dict either way. A restart forgets the halt and the promised flatten. The blend stage of the same /kill has a durability warning; the mirror's has none.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a10_halt_not_durable.py`: `halt() answered {...} (no sign the write failed); after a restart the halt is {}`
- **Smallest fix:** `_write_halt` returns success; `halt()` carries `persisted: False`; `_kill_mirror` says so.

### A-15 MINOR: the unauthenticated /health now shows account positions and cash
- **Where:** mirror.py:1241; service.py:1569.
- **What happens:** `waiting_on` publishes the pre-trade reason verbatim, account figures included.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a15_health_leak.py`: `GET /health with no token returned account detail: ['the venue 3', "exceeds the account's $90,000.00"]`
- **Smallest fix:** /health carries booleans only; the text stays on /status.

## NOTE

With repro, all in `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a18_notes.py`:
- **A-22:** "byte-for-byte as before" holds for every existing route, the loop, the boot message and the /kill and /resume bodies (diff read line by line). It does not hold for the five new paths with the flag off: `{'POST /mirror/halt, no token': 401, 'GET /mirror/halt': 405, 'POST /mirror/halt, token': (404, {'detail': 'not found'}), 'unknown path, for reference': (404, {'detail': 'Not Found'})}`.
- **A-20** (mirror.py:470-471): a flatten queued off hours makes `next_wait()` 5 s, so the whole loop (ladder step and save, tracker poll, blend cycle) runs every 5 s until the next open: `next_wait() = [5.0, 5.0, 5.0]` across a night and a weekend. A stuck run does the same at 60 s indefinitely.
- **A-19:** `MIRROR_CANCEL_BEFORE_CLOSE_S` is not validated. At 240 every session is `'skipped'` with `'missed the decision window: the executor was not ready in time'`.
- **A-18** (service.py:985): `{"book": ["dry"]}` gives `500 (unhandled TypeError: unhashable type: 'list')`.

Read, not run:
- There is no repair path for a share-count divergence (a split of TQQQ, SOXL or TECL, a manual trade, or A-07). Pre-trade refuses indefinitely and the only tool is hand-editing the state JSON.
- The global /resume also lifts the mirror's self-imposed halts (book error, account mismatch, unreadable state) and reports only "mirror resumed (live)". The ladder reports its prior halt (service.py:2183-2189). The pre-trade gate contains the damage.
- `_true_up` drops an unreported commission after 3 days without a word. Pre-trade tolerance is $1, so two dropped commissions or one broker fee block every session until a manual negative credit, and the operator learns it at 15:58.
- Credits are checked one at a time in arrival order: a dividend posted before the fee that offsets it is refused.
- On the IB paper account `ib_allow_delayed` defaults true and `spot_ex` labels a 15-minute-delayed tick "live", so it passes as a cross-check. Live trading mode refuses to boot that way.
- `QUOTE_BUDGET_S` is checked between symbols only; one `spot_ex` inherits `qualifyContracts` with RequestTimeout 0 (pre-existing).
- `tick_lock` does not serialize two loop generations, because each `_loop` builds its own managers (service.py:1139-1141). In production this only matters at a process boundary.
- An open ladder leg would count as "positions that are not whole stock lots" and halt the live book at the post-check. Only the blend exclusion is documented.

## Existing gates that are vacuous where it matters
- M10 halts between ticks, the one place the check exists (A-01).
- M11 "resume cancels" is exercised only before any flatten order is sent (A-03).
- M8 never sends a kill at a stuck run (A-02).
- `sound()` asserts cash ≥ 0, but no test fills above ref × 1.003; the core fuzz uses sigma 0.2% and tolerates −$1 (A-05).
- M5 restarts onto the same `Venue` object, whose order memory survives, i.e. a venue that always answers find (A-07, A-13). M16's true-up uses the same double.
- M13 tests a readable save, never a failing one (A-04).
- M2 "a missed window is a recorded NO TRADE" holds only with the clock known (A-06).
- M15 drops the sleeve and never trades the book again (A-08). M14 transfers $5,000 only (A-09).

## Checked and found sound
- **Exactly-once in the state machine.** A crash at each of 576 points (before and after every save and venue call) across five scenarios: a rotation with crosses and a transfer, a credit session, a window-end cancel with a partial, a flatten, and a halt mid-run. Every restart ends with no id sent twice and book equal to account in shares and cash. Where fills are timing-independent, the book matches the uncrashed run sleeve by sleeve. Test: `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_s01_crash_sweep.py`. The paper book likewise at every save: `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_s03_paper_crash_sweep.py`. What breaks exactly-once is the venue lookups it trusts and a disk that stops writing, not the machine.
- **JSON round trip of the plan after a restart** (types, key order, None vs missing): covered by the same sweep.
- **mirror_core.** 4,000 random sessions with planned, partial and refused transfers, crosses, and partial and zero fills. No core call raises; shares and cash conserve; crosses and transfers are zero-sum; there is never a sell and a buy of one symbol at the venue; no sleeve sells what it does not own; no borrow while fills stay within the cushion. Test: `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_s02_core_fuzz.py` (`test_s02`). `allocate` never over-gives (argued, not tested).
- **Real adapter, same-day paths.** All pass in `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a00_real_adapter_sanity.py` and `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A/test_a00b_real_adapter_probes.py`:
  - a full session, then a restart
  - a partial then cancel at the window end, booked at the venue's price
  - a crash after a fill, adopted once with completed orders available or not (the latter through execution reports with `filled_qty`)
  - a buy answered Inactive at placement books 0 and is not resent
  - a refused cancel keeps the run open until the venue speaks
  - a fill that beats the window cancel is booked whole
  - a placement that raises "no venue ack" after the order landed is adopted, not resent
  - `duplicate=True` results are handled like any other (read, not exercised through the manager)
- **Flatten ceiling.** Never more than the account holds; a short or absent venue position sells nothing; a flatten never starts while a run's orders are unbooked (that guard is also A-02's wedge).
- **Halted book.** With the halt already in force at the top of a tick, nothing new is sent, in-flight orders are cancelled and booked, and the halt survives a restart when its file was written. An unreadable halt file means halted. An unreadable or wrong-book state file is archived and halted, never a fresh book.
- **Inbox.** Dedupe holds across a crash between the state save and the inbox rewrite; a request arriving mid-drain is kept; credits and transfers apply exactly once.
- **Service with the mirror off.** No manager, no import of `app.mirror`, no file; `_loop_wait()` is `settings.poll_seconds`; /kill and /resume bodies and alert text are unchanged.
- **Service with it on.** `tick()` cannot let an Exception out; `_loop_wait` and the /health block are guarded; `halt_lock`, `inbox_lock` and `tick_lock` never nest; API threads never take `tick_lock` or touch the adapter; `_kill_mirror` cannot raise into the ladder stage; every new route is behind EXEC_TOKEN or READ_TOKEN, and mutations are POST-only.
- **Clock.** All instants come from the brain in UTC; ET is used only for the day string and the fallback session clock (DST-safe, tzdata pinned). The skew check works both ways; today's last good read survives a failed one; the half-day close is honoured. Booting after the decision instant or restarting inside the window still trades if before `plan_by`. A replay, stale, future-stamped or pre-bar payload is refused.
- **The two new adapter methods** are additive and read-only; nothing else in `app/` calls them; `positions_snapshot` never truncates a fractional lot and names non-stock positions.
- **Baseline.** The 77 mirror tests pass. The full existing suite was run with `-x` and stopped at the known `test_gate_mf3_5...` failure, so tests after it were not run.