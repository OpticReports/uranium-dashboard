# Composer mirror, round 2: reviewer A

**Verdicts.** PAPER: **CLEAN**. No finding lets the paper book reach the venue, the account or the blend's kill path; three notes apply (N-03, N-07, N-09). LIVE money: **FIX-THEN-SHIP**. Nothing BLOCKING was found this round; fix N-01 and N-02 before any engine is live; N-04 and N-08 are advised; two owner probes are still open.

**What was reviewed.** `ibkr-executor/` at d0ecccdb. HEAD is now c89d3fb7 and `git diff d0ecccdb HEAD -- ibkr-executor` is empty, so this is the current code. The reviewed commit's own message reads "WIP snapshot: executor-side review fixes in progress (not complete, not verified)". The author's gates pass (357). No tracked file was edited.

**Where the repros are.** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/` (run with `run.sh <file>` in that directory). 14 new failing repros, 41 passing verification tests. Line numbers are `ibkr-executor/app/...` at d0ecccdb.

## 1. Round-1 findings: fixed or not

The 49 round-1 tests were re-run unchanged against HEAD with the author's `tests/ibrig.py`: 42 pass, 7 fail. Those 7 are exactly the "consciously superseded" ones, and all seven claims are legitimate; each is re-asked as the original finding in `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_v02_superseded.py` (6 pass; a05c is covered by the session fuzz).

| ID | Status | Evidence |
|---|---|---|
| A-01 halt mid-tick | Fixed | Round-1 a/b/c pass. New sweep: a halt and a kill at each of 46 brain, venue and save points of a rotation, and a resume at every point of a flatten. At most one order (the one in flight) goes out afterwards; after a kill book and account end flat. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_v01_halt_sweep.py` |
| A-03 kill, resume, kill | Fixed | Round-1 a/b pass. 720 random walks over kill/resume/halt/restart with a misbehaving venue: never short, working sells never exceed holdings, no id twice, no orphan. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_f01_flatten_fuzz.py` |
| A-02 stuck order blocks kill | Fixed by redesign | Other symbols are sold, the blocked one is named, a resolve lets the flatten take it, book ends flat (`test_v_a02`). |
| A-07 overnight fill booked as zero | Fixed by redesign, with a cost | Never booked zero; unresolved until the operator resolves; then book equals account and the next session trades (`test_v_a07a`, `test_v_a07b`, real adapter). The cost is N-04. |
| A-04 disk failure | Fixed, one residual | Disk failing at each of 23 rotation saves and 17 flatten saves, with and without a restart: no new run order while latched, no id twice, sound after healing. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_v04_latch_sweep.py`. Residual: a flatten sent under the latch followed by a restart on the stale file leaves a phantom book (account flat, book still holding). It is announced in advance and nothing is sold twice; the repair is manual. |
| A-05 borrow | Fixed | Round-1 a05a passes. 1,800 random live sessions (tape drifting inside the band, fills up to the limit, $1 commissions): account cash never negative, book never above account. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_f02_sessions_fuzz.py`. a05b/a05c: premise gone (a limit buy cannot fill above its limit); debt repair works (`test_v_a05b`). |
| A-24 IBKR credit check | Addressed by design, unproven | Buys are limits sized inside cash at the limit. Still needs one real order on the account (see open items). |
| A-06 unreadable clock | Fixed | a06a/b pass; a brain back at 15:54 is traded on the cadence the book asks for (`test_v_a06c`). |
| A-13 fills lookup | Fixed | a13a passes on the real adapter; a13b re-run at 49.60 (inside the limit) is booked at the venue's price. |
| A-21 one-shot flatten | Partly fixed | One refusal is re-sold next round. Sustained refusals: see N-08. |
| A-16 unreadable fills booked as zero | Fixed | Round-1 repro passes (order stays unresolved). |
| A-23 kill behind the tick | Fixed for sleeps, brain reads, between quotes and orders | Round-1 repro passes in the real loop. Not covered: `_true_up` (mirror.py:2045) has no wake check. |
| A-12 static refusals | Fixed for static reasons | Transient reasons still hold the tick: N-09. |
| A-08, A-09, A-10, A-11, A-14, A-15, A-16, A-17, A-18, A-19, A-20 | Fixed | Round-1 repros pass. A-20 residual: a stuck run still asks for the loop every 60 s indefinitely. |
| A-22 off-state routes | Fixed except N-03 | |
| Round-1 notes | Mostly fixed | No repair path: `/mirror/adjust` added. /resume now names the halt it lifted. Dropped commissions are said. Credits apply debits first. Unchanged: delayed quotes pass as "live" on the IB paper account; `qualifyContracts` unbounded; an open ladder leg would halt the live book. |

## 2. New findings

### N-01 SERIOUS (live): the operator tools accept what cannot be true, and a typo becomes real orders
- **Where:** mirror.py:546-563 and 644-680 (resolve: the only price test is > 0; refused only while the venue says working); 565-583 and 682-709 (adjust: any cash delta); mirror_core.py:265-288 (a sleeve in debt is exempt from corridor and dust rule and sells).
- **What happens:**
  - A buy is resolved above its own limit, at any multiple.
  - A slipped decimal in an adjust (or a negative credit) puts a sleeve in debt and the next session sells it out.
  - A resolve overrides the venue's own terminal answer for an order that is not stuck.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n01_operator_typos.py`
  - a: `the book booked 446 PULS @ 4960.0 for an order whose limit was 49.74: sleeves now in debt {'KMLM': -711700.0, 'HARV': -1477960.0}`
  - b: `the next session SOLD [('BIL', -315)] of HG's {'BIL': 315} 'to repair a cash debt'`
  - c: `the venue answers 'filled' ... (446 PULS in the account); the book booked the operator's 0`
- **Smallest fix:** resolve only an order flagged stuck; refuse a buy price above its limit or any price more than about 20% from its reference; if the venue answers terminally, book the venue's answer. Refuse an adjust or debit that takes a sleeve's cash below zero unless a `force` flag is sent.

### N-02 SERIOUS (live): /kill reports "flatten complete" while the account still holds shares
- **Where:** mirror.py:2167-2181 (sells min(book, account) per book symbol), 2212-2217 (reports only what the book still holds).
- **What happens:** shares the account holds beyond the book are never looked at: a split not yet listed, a manual buy. The closing line is info-level.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n02_flatten_complete_but_account_holds.py`: `the account still holds {'SOXL': 270} ... the kill ended with: 'flatten complete: ... | book cash $100,000.00' and nothing names the shares left in the account`
- **Smallest fix:** in `_flatten_finish`, read the account's positions; if any stock position remains, say it in red and do not call the flatten complete.

### N-04 MINOR (live operations): on this gateway a never-sent order wedges the run until the operator resolves it
- **Where:** mirror.py:1660-1674 and 1698-1703. "None is conclusive" requires `history_complete()`, which is False after every lookup on a gateway that never answers reqCompletedOrders.
- **What happens:** a placement that raised before any order existed, or a restart between write-ahead and placement, leaves the run open the same day. Round 1 retried these. Every later session is NO TRADE until `/mirror/resolve`. For today's order, "not in open orders and no execution today" already proves zero filled.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n04_unsent_order_is_unresolved.py` (real adapter)
  - a: `TECL's placement raised 'cannot qualify stock contract TECL' before any order existed, and the run of 2026-11-10 is still open the next day`
  - b: `SOXL was never sent ...; 20 s later the run cannot go on: "... the venue's completed-order history is unavailable"`
- **Smallest fix:** for today's intent, accept None when the open-orders request and the executions refresh both answered; have the adapter raise a distinct "not sent" error for failures before `placeOrder`.

### N-08 MINOR (live): the flatten gives up after about 25 seconds of refusals
- **Where:** mirror.py:125-126, 2186-2190 (five rounds, five seconds apart).
- **What happens:** a venue refusing for longer ends the kill with the book on; nothing retries. A halted book never refreshes the brain's clock, so a flatten queued overnight uses the plain weekday clock, including on a weekday holiday; whether IBKR queues or refuses market orders then is not known to me.
- **Repro:** `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n08_flatten_gives_up_in_seconds.py`: `the flatten was marked done 25 s after it started ... the venue took orders again at +60 s and for the next two minutes nothing was sent`
- **Smallest fix:** bound by elapsed session time (for example 30 minutes, widening gaps), and use the service's existing holiday table in `_rth`.

### Notes (each with a repro unless stated)
- **N-03:** with the mirror off, a malformed JSON body on the four POST routes gets 422, not 404; FastAPI validates the body before the handler. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n03_off_routes.py`
- **N-05:** `place_limit_order`'s dedupe (ib_adapter.py:1247) misses a filled prior when completed orders are unavailable; same blind spot as the existing `place_stock_order`. Not reachable through the manager today. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n05_notes.py`: `the account holds 20 BIL`
- **N-06:** the live "dividend cash has arrived" guard (mirror.py:1362-1366) is satisfied by any surplus cash in the account: `HG was credited $94.50 as a dividend out of the $500 buffer`. Nothing is borrowed. Same file.
- **N-07:** a paper limit buy always fills at the reference; a live one the tape has left rests and the sleeve sits in cash overnight: `live: 5 of 5 buys unfilled ...; paper, same session: 0 unfilled`. The design doc already says this. Same file.
- **N-09 (paper):** with the brain down or answering 503, a paper tick still holds the loop for 150 s (51 brain reads), wake-interruptible; with the clock unreadable the whole service loop runs every 60 s (20 s from 15:30) all session. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_n09_paper_loop_hold.py`
- **Read, not run:**
  - A dividend first seen after a skipped session uses the last history row. A split, flatten or adjust in between makes that count wrong.
  - Two feed rows for one distribution with different ex-dates would make two receivables.
  - A split listed a day late corrupts the paper book for that day; it is said in red the next day.
  - A buy with no reported price is booked at the reference; booking at its limit would keep book cash at or below the account's.
  - A threshold sleeve whose target holds a share worth more than 5% of the sleeve trades inside its corridor: 979 of 5,000 sessions at $3,000 with a $600 share, 6 of 5,000 at $34,000 (all after an unfilled buy). `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_s05_corridor_thrash.py`

## 3. Service with the mirror off, and existing adapter behaviour
- `service.py` and `ib_adapter.py` diffs since 7e61a970 were read whole. Every change is additive or behind `MIRROR`.
- The one edit to existing code is `_await_placement`'s fill-wait condition, now `("MKT", "LMT")` (ib_adapter.py:1110). MKT, MOO and STP behave as before.
- `DryAdapter` gained `history_complete()` returning True, which matches the default the blend already assumed (blend.py:4224).
- Only difference with the flag off: N-03.

## 4. Gate vacuity
76 single-line mutations were run on a scratch copy against the author's gates: 66 killed, 4 equivalent, 6 behaviours no gate covers:
- **Flatten hold-back** (mirror.py `if sym in blocked: continue`): removing it sells a symbol whose run sell is unresolved and possibly still resting, and every gate still passes. My `test_v_a02` kills it.
- **Halt/latch look before re-placing an unconfirmed order** (mirror.py:1707).
- **Resolve of a never-sent order** (mirror.py:654).
- **`_flatten_finish` race guard** (mirror.py:2206).
- **MKT's bounded fill wait:** dropping MKT from the tuple at ib_adapter.py:1110 passes the whole adapter suite (pre-existing gap, on the one line this round touched).
- **Multi-attempt executions** in `stock_order_fills`.

The author's crash sweep runs on a venue that remembers every order; with history unavailable every "intent" crash point is unresolved by design (N-04).

## 5. Checked and found sound
- **Exactly-once on the new order path:** the author's ported sweep passes; my additions:
  - a resting limit buy with a partial at the window end, and one the tape has left, crashed at every save and venue call including `place_limit_order` — `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_v03_limit_buy_sweep.py`
  - resolve and adjust applied exactly once at each of 16 crash points — `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_v05_repairs_sweep.py`
- **Dividends and splits:** in the 1,800 live sessions, with ten-day relisting, brain-down days and restarts, no receivable was created or credited twice and no split applied twice.
- **Paper book:** 2,240 random sessions with transfers, credits, dividends, splits, halts, restarts and an engine leaving. The paper account always equals the paper book and every session is recorded. `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/A2/test_f03_paper_fuzz.py`. The paper book never touches the service adapter (every adapter use read).
- **Flatten rounds:** a new round is built only when every order of the current one is booked; a restart mid-round resumes it; a venue that forgets orders leaves them openly unresolved, never orphaned.
- **Brain worker:** an abandoned call's result is never used; the pinned cache is keyed by instant and guarded.
- **Buy re-quote:** bounded to 20 s, falls back when out of band, limit floored to the tick. A sub-dollar limit takes the 0.0001 grid; the choice of grid uses the unrounded limit.
- **Morning pre-check:** reads only.
- **Repair routes:** behind the exec token, POST-only, validated.

## 6. Open before a live engine (owner)
- One real limit buy sized to cash on the actual account, to settle the credit-check hypothesis.
- Whether the account can fund a buy from same-minute sale proceeds.