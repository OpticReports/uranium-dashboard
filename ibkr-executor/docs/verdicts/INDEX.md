# Counter-agent verdict index — ibkr-executor / blend3070

**Why this file exists.** CLAUDE.md makes counter-agent verification
mandatory and says the verdict must be *logged alongside the work*. For
this campaign it was not: the verdict documents lived only in a session
scratchpad, and a container restart DESTROYED them. The MF3 implementer
could not read the findings it was told to fix ("The three verdict files
this round was to be read against are absent from disk", cc03347), and the
same restart is why a claim like mf-11 is now unrecoverable. This index is
the durable, in-repo replacement.

**Provenance and its limits.** Nothing here is quoted from a verdict file —
every one of them is gone. This index is RECONSTRUCTED from two sources
that *are* in the repo: the git history of `ibkr-executor/` (each round's
remediation commit names its findings and, sometimes, its verdict), and the
finding ids the code and `tests/probes/README.md` are annotated with.
Anything those two sources do not settle is marked **UNKNOWN** rather than
guessed. In particular, most rounds' verdict WORDS (PASS / PASS WITH
CORRECTIONS / FAIL) were never written into a commit; where a round's
commit does not state one, the verdict column says UNKNOWN and the
findings column carries what is provable.

**Status vocabulary**
* `closed` — remediated, with a merge-blocking gate in the pytest suite.
* `accepted-risk` — understood, deliberately not fixed, reason recorded.
* `open` — real, not fixed, no decision to leave it that way.
* `UNKNOWN` — not reconstructable from the repo.

**Namespace warning.** `M1..M5` appears TWICE, for two different reviews
(round 1's blend materials and round 4's IB-adapter materials). They are
unrelated. Likewise `N1/N2` (round 6) vs `N3/N5/N13/N14/N15` (rounds 2-5).

---

## Round 1 — counter-agent review of the pre-review snapshot
* **Reviewed:** `9fb6d91` (blend3070 execution path, PRE-REVIEW snapshot)
* **Verdict:** **FAIL** (dated 2026-08-20; stated verbatim in the
  remediation commit)
* **Remediated by:** `a5a425b`
* **Materials:** M1 reconciliation-first · M2 single per-cycle cash ledger
  (no negative ledger, no short BIL) · M3 stop-placement retry +
  STOP_MISSING · M4 exits/stops must match call_id AND symbol · M5 stop
  replace is place-new-first · M6 write-ahead entry journal + deterministic
  client ids · M7 no silent zero fill prices (UNRECONCILED instead)
* **Status:** all seven `closed`.

## Round 2 — re-review
* **Reviewed:** `a5a425b`. Verdict document was `blend_rereview_verdict.md`
  (named in the commit; **file absent from the repo and from disk**).
* **Verdict:** UNKNOWN (four NEW materials were raised, so not a clean PASS)
* **Remediated by:** `4b3bd19`
* **Materials:** N13 a tracker outage never skips reconciliation or the
  local time-stop belt · N14 `/kill` reconciles FIRST and closes only
  positions still actually held · N15 write-ahead journal + deterministic
  ids + boot adoption extended to ALL order types · N5 deferred /
  UNRECONCILED exit proceeds are never spent
* **Minors:** 8, listed in the commit body (cancel-of-FILLED raises; fill
  re-queue; non-ASCII credential header 401 not 500; sweep clamped to
  budget headroom; malformed `as_of` is STALE; 2000-id recycle horizon
  documented; journaled-order fills absorbed)
* **Status:** all `closed`.

## Round 3 — final review
* **Reviewed:** `4b3bd19`
* **Verdict:** **PASS WITH CORRECTIONS** (stated in the commit)
* **Remediated by:** `83b85f4`
* **Material:** K-d — a RAISING stop cancel (pinned contract: raise = the
  stop FILLED) folded into the ambiguous-False branch and could reach the
  MKT sell under a double fault. It now parks, loudly, and never sells.
* **Status:** `closed`. K-d is re-asserted by every later round's gates,
  including this one's (`test_gate_b4_*` checks it survives the retry and
  the retry's exhaustion).

## Round 4 — IB-adapter review
* **Reviewed:** `b04348f` (the real `IBAdapter` stock/ETF surfaces)
* **Verdict:** **FAIL** ("the failed IB-adapter review", per the commit)
* **Remediated by:** `e3da227`
* **Materials:** M1 duplicate book orders (blocking) · M2 threading —
  `/status` and `/blend/feed` never touch the adapter · M3 partial-fill
  cancel oversell · M4 a missing quote must not drive a spurious rebalance
  · M5 no gateway reconnect. Plus 2 escalated minors and 4 minors.
* **Status:** all `closed` at the time. **M2 was re-opened and only
  half-closed:** "never touch the adapter" was necessary but not
  sufficient — see B6 in the corrective round.

## Round 5 — adapter re-review
* **Reviewed:** `e3da227`
* **Verdict:** UNKNOWN
* **Remediated by:** `72578af` (R1), `525e4ac` (R2), `8735282` (r3-r7),
  `64c0275` (N3 + mode-transition guard), `5acd80d` (F1/F2)
* **Materials:** R1 the blackout guard was one cycle deep — positions are
  flagged `history_gap` and unpark ONLY on positive venue evidence · R2
  `/kill` becomes TWO-STAGE (ib_async binds its loop per thread, so an
  API-thread flatten pumped a fresh loop against the shared transport) ·
  N3 `/resume` must not race an in-flight flatten; atomic saves
* **Minors:** r3-r7 (armed-flag alert semantics, slippage clamp,
  stuck-order WARN, budget quote gate), F1/F2 mode-guard corrections
* **Status:** all `closed`.

## Round 6 — counter-agent review of the R1 pass-1b code
* **Reviewed:** `72578af`
* **Verdict:** UNKNOWN (both findings MATERIAL, "blocking for live")
* **Remediated by:** `cde6fb7`
* **Materials:** N1 a position parked UNRECONCILED left its resting GTC
  stop at the venue (later naked short) — pass 1b RETIRES the stop first ·
  N2 `stock_position` sums EVERY account STK row, so conflated external
  shares could verify ownership the book never had
* **Status:** both `closed`.

## Round 7 — counter-review of the N1/N2 fix
* **Reviewed:** `cde6fb7`
* **Verdict:** **FAIL** (stated in the commit: "Counter-review of cde6fb7
  returned FAIL")
* **Remediated by:** `1d2e1d7` (X1-X4), `6281560` (x10/x11), `ec8384d`
  (x12), `beef1ea`, `9fddbed` (G3), `fff6d3a` (Y1)
* **Materials:** X1 `held > book_qty` + a WORKING stop unparked shares
  whose ownership was never proven · X3 the same cell with a DEAD stop
  left a real position with zero venue cover · X2 the ambiguous (False)
  cancel never reached the RED branch · X4 the park alert claimed
  "nothing sold" when something may have been
* **Adjacent, same round:** x10/x11 (one unique temp file per `save()` —
  measured 467 raises and 52 corrupt published states with 4 concurrent
  savers) · x12 (the same for the LADDER book, which was live paper money)
  · G3 (an unreadable blend book is preserved and loud) · Y1 (the daily
  trail ratchet is a short path too, so it obeys `history_gap`)
* **Status:** all `closed`.

## Round 8 — Z round
* **Reviewed:** the X/x/Y build
* **Verdict:** UNKNOWN ("live-blocking" is stated for Z1)
* **Remediated by:** `08362ce` (Z1), `bd27556` (Z2), `995de0b` (y2),
  `98ffe0d` (Z1 follow-up)
* **Materials:** Z1 resting SELL cover may never exceed venue-verified
  `held` · Z2 a stop fill on an UNVERIFIABLE position is never reported
  green · y2 a leg-row schema drift preserves the ladder book and HALTS
  instead of re-opening live legs
* **Status:** `closed`.
* **Accepted-risk:** `Z-1b` — the probe asserts every allocation is
  `<= that position's own qty`, which directly contradicts `Z-1`, the
  hand-derived table in the same file. The contradictory input is
  unreachable from the only call site and every result is capped before it
  can reach the venue: a documentation defect, not a live one. Preserving
  the reviewer's verified table was judged worth more than silencing the
  probe. `Z-1c` (negative/zero qty) WAS fixed.

## Round 9 — Z counter-review
* **Reviewed:** the Z build
* **Verdict:** UNKNOWN
* **Remediated by:** `e82beb5` (Z-D/Z-J/Z-K), `99e68c5` (Z-A/Z-B/Z-C),
  `f78830a` (Z-E..Z-H + Z-1c); probes landed as `Z-M` in `1485ab4`
* **Materials:** Z-A the peer resize was UNDONE by the next pass · Z-B a
  resized stop's fill must book a PARTIAL · Z-C rejected cover is really
  retried · Z-D a rollback that cannot read the book HALTS it instead of
  returning a fresh un-halted one · Z-J that recovered state is PERSISTED
  at load · Z-K `/resume` names WHICH halt it cleared
* **Minors:** Z-E..Z-H (partial cover must never read as full protection)
* **Process finding:** `Z-M` — probes lived only in a scratch directory and
  one probe's pre-commit text was unrecoverable. Closed by committing the
  probe suites (`1485ab4`, `21c4afe`, `0433d4a`). **This is the same
  failure mode this file exists to close for verdicts.**
* **Status:** all `closed`.

## Round 10 — ZF whole-branch review
* **Reviewed:** the whole branch
* **Verdict:** UNKNOWN
* **Remediated by:** `9861e37` (ZF-1/ZF-5), `4008deb` (ZF-2), `b1c2ac2`
  (ZF-4/ZF-6/ZF-7), `88f7bc7` (ZF-3 deploy note); probes in `21c4afe`
* **Materials:** ZF-1/ZF-5 the resize removes no cover the aggregate did
  not require · ZF-2 a FILLED order is never adopted as working protection
  · ZF-4 a RENAMED or REMOVED position field must not fall through to a
  fresh un-halted book · ZF-6 a row that cannot be rebuilt is NAMED ·
  ZF-7 the boot save must not destroy the only copy of the evidence
* **Status:** those five `closed`.
* **Accepted-risk:** `ZF-3` — **rolling back this build is a book-losing
  operation.** The reader is the older build, so the fix is structurally
  unreachable from this side. Documented in the executor README's deploy
  note; probe `ZF-D3` measures it and needs a worktree to mean anything.
* **Accepted-risk:** `ZF-A9c` — a recorded SCOPE statement, not a defect
  (the invariant holds in cells where `held` was verified this cycle;
  identical at main).
* **Accepted-risk:** `ZF-G4` — the probe ASSERTS the ZF-2 defect and so
  fails now that ZF-2 is fixed. Left exactly as written, per probes rule 3.

## Round 11 — MF whole-branch counter-review
* **Reviewed:** the whole branch (three MATERIALs)
* **Verdict:** UNKNOWN. The reviewer's own re-attack suite went 28/29 ->
  29/29, the one flip being `F4g`, the MF-3 defect.
* **Remediated by:** `38340d6` (MF-1), `de5bd2d` + `6542d6f` (MF-2),
  `77d3ea1` (MF-3), `84b8c4f` (mf-4/mf-5/mf-7)
* **Materials:** MF-1 the queued kill flatten ran at the END of the loop
  iteration, behind both 30s feeds (pre-existing at main) · MF-2 `_loop`
  had no lifecycle, so every lifespan leaked a daemon thread that kept
  acting on the CURRENT globals (pre-existing at main) · MF-3 a drifted
  row rebuilt from STAND-INS is UNVERIFIABLE, not tradeable (NEW,
  introduced by ZF-4)
* **Minors:** mf-4 (a vacuous gate assertion), mf-5, mf-7, mf-8, mf-9,
  mf-10 — all `closed`; mf-6, mf-11, mf-12 are **UNKNOWN** (they appear
  nowhere in the code or history).
* **Open:** `mf-11` — the MF3 round was told it "stands and the fixture now
  hides it" and could not recover what it asserts, because the verdict
  files were gone. **Still UNKNOWN; still open.** It is the single
  clearest cost of not having had this file.

## Round 12 — MF-A / MF-B / MF-C counter-review
* **Reviewed:** the MF build
* **Verdict:** UNKNOWN. Changed no probe file; `attack_final.py` stayed
  29/29.
* **Remediated by:** `672be5f` (MF-C/MF-B), `bc72389` (MF-A), `499aed1`
* **Materials:** MF-A the emergency stop's own halt was NOT immediate — it
  took `BLEND_LOCK`, measured 19.505s of dead air · MF-B a STAND-IN row's
  flag cleared on the very next reconcile · MF-C the only cell where the
  branch was WORSE than main: a stand-in row's fabricated identity
  cancelled a real working stop
* **Status:** all `closed`.

## Round 13 — MF2 counter-review (the ladder half of the kill switch)
* **Reviewed:** the MF-A/B/C build
* **Verdict:** UNKNOWN. `attack_mf2.py` was **48/57 at `499aed1`** and
  **55/57** after the round.
* **Remediated by:** `83fc6cc` (MF2-1..4), `61bace5` (MF2-5), `a62a25b`
  (the MF-1 gate's flake, ruled a TEST defect), `2317b21` (README S6),
  `0433d4a` (probe suite)
* **Materials:** MF2-1 `/kill` made an UNCAPPED `close_spread` call on the
  API thread — measured 20.008s of dead air · MF2-2 the deferred halt
  never reached disk · MF2-3 a queued kill outlived `/resume` · MF2-4
  `ladder: "closed"` when nothing closed · MF2-5 a halt landing mid-cycle
  did not stop the rest of the plan (four venue BUYs measured)
* **Minors:** mf2-6..mf2-13 — `closed`.
* **Accepted-risk:** probe `A6` (a residual of the probe's own shape: the
  one order it counts is the one whose `place_stock_order` the probe is
  blocked INSIDE when the kill lands) and probe `C2` (the ZF-3 one-way
  rollback door in its MF-C form).
* **Note:** MF2-3 was reported closed here and was **not** — see MF3-2.

## Round 14 — MF3 counter-review (of the MF2 round)
* **Reviewed:** `09aa936`/`0433d4a`
* **Verdict:** UNKNOWN (six MATERIALs)
* **Remediated by:** `cc03347`
* **Materials:** MF3-1 `/kill`'s BLEND stage had no exception guard ·
  MF3-2 MF2-3 was not actually closed · MF3-3 the retry claim was false
  and the behaviour it described was the right one · MF3-4 the halt break
  swallowed every ALERT intent, two of them consuming a PERSISTED one-shot
  · MF3-5 the halt guard reached only one of the two intent loops ·
  MF3-6 an unconditional and sometimes-false durability warning
* **Minors:** mf3-7..mf3-10, mf3-13 — `closed`. mf3-11 is the unrecoverable
  mf-11 above; **mf3-12 is UNKNOWN** (it appears nowhere).
* **Status:** MF3-1, MF3-2, MF3-4, MF3-5, MF3-6 `closed` and still hold.
  **MF3-3 shipped with three regressions** — see the next round.

## Round 15 — THE JUDGE'S RULING on cc03347 (the corrective round)
* **Reviewed:** `cc03347`
* **Verdict:** **FAIL** — ruled `MERGE: NO / LIVE-READY: NO`, with the
  explicit instruction not to merge and fix forward on `main`, because
  item 1 is a naked-short path and `main` is `autoDeploy`.
* **Remediated by:** this commit.

### Regressions cc03347 itself introduced

| id | finding | status |
|---|---|---|
| R-a | MF3-3's retry can DOUBLE-SELL real shares across a process restart and report it as "flatten complete". `place_stock_order` resolved the idempotency key against `self.ib.trades()` — this session only — so both halves of the stated no-double-sell law failed together at a session boundary. Reproduced: venue CRSP -10 against a 5-share book position, 0 alerts mentioning a short. | `closed` (= B1) |
| R-b | MF3-3's retry never terminates for `history_gap` / `stand_in_rows` rows, which are parked BEFORE any venue call by design. Base alerted once and cleared; cc03347 re-alerted every cycle forever. | `closed` |
| R-c | cc03347's deviation #4 made a `/kill` message categorically FALSE: "the ladder is NOT halted by this service" emitted while `halted == "KILL"` in memory AND on disk, in the same message that says the halt IS on disk, with the body's `halted: KILL` contradicting its own `ladder: halt_failed`. | `closed` |

### The ten live-blocking items

| id | finding | status |
|---|---|---|
| B1 | the restart-boundary double-sell (= R-a). The placement path now resolves the idempotency key against the VENUE (`reqAllOpenOrders` + `reqCompletedOrders`), the two-stage lookup `find_stock_order` always used. | `closed` |
| B2 | `BLEND_STATE_PATH` undeclared in render.yaml, so the live book sat on the container's EPHEMERAL layer: every deploy destroyed it and re-seeded on top of held shares. Declared onto the mounted disk. | `closed` |
| B3 | `EXEC_TOKEN` defaulted to `""` and `_auth` short-circuited on a falsy token, so `/status`, `/kill`, `/resume` were UNAUTHENTICATED when unset — and `/kill` accepted GET. Fails closed off OFFLINE; mutations are POST-only. | `closed` |
| B4 | unbounded retry + a false convergence promise: 288 cycles/day x (1 row alarm + 1 summary) = >=576 Telegram messages/day for one parked row, ~1,150 for three, forever (the judge's report states the same figures). Bounded to `FLATTEN_MAX_ATTEMPTS`, per-reason alerts, honest wording. | `closed` |
| B5 | `/kill`'s `MGR.clear_kill()` sat unguarded inside the outer try (and it is the DEFAULT path — every leg is WAITING until 2026-11-01, so `open_legs == []` on every `/kill` today); `/resume` 500'd after clearing memory state but before `MGR.save()`. Both guarded; `/resume` always reaches disk. | `closed` |
| B6 | mf3-10's snapshot was applied to `save()` ONLY; `status_summary()` and `feed()` still walked live shared dicts from worker threads. Measured here at 18.2-18.7% of reads raising under load, 0% after. | `closed` |
| B7 | the three halves of the ladder kill record were written by `/kill` under NO lock while `/resume` wrote them under `MGR_LOCK`. `LADDER_KILL_LOCK` (innermost; nothing acquired while held) makes both triples atomic. The judge measured 143/400 split records; this repo's own rig lands 2-3 per 1200, so the *reachability* is the finding and the deterministic gate forces the interleaving rather than waiting for it. | `closed` |
| B8 | `spot()` never called `reqMarketDataType`, used a fixed 3s wait, and ib_async 2.1.0's `marketPrice()` has NO close fallback — a missing market-data subscription was indistinguishable from a thin quote. Fixed, and `ib_async` pinned `>=2.1,<3`. | `closed` |
| B9 | **the blend book has never taken a real fill in any mode.** A PROCESS gate, not a code fix — no amount of code review substitutes for one supervised paper fill end to end. | `open` (by the judge's own instruction: note it, do not close it) |
| B10 | `IB_CLIENT_ID` defaulted to 17 and was undeclared; a TWS session on 17 costs 20x15s and then kills the loop thread. Declared as 1701 and reserved. | `closed` |

### Found by this round, NOT closed

| id | finding | status |
|---|---|---|
| CR-O1 | The LADDER half of the kill retry is still UNBOUNDED: `_consume_ladder_kill` retries and re-alerts every cycle, forever, when a leg will not close — B4's exact flood argument, on the other half of the same kill switch. Changing the ladder emergency path was outside this round's scope, so the CLAIM was corrected (the code and README no longer assert the two halves behave alike) rather than the behaviour. | `open` |

---

## Round 16 — THE JUDGE'S RULING on f5e7154, and the campaign verdict
* **Reviewed:** `f5e7154` (the corrective round: R-a/R-b/R-c + B1-B10)
* **Verdict:** **FAIL** — `MERGE: NO / LIVE-READY: NO`. All thirteen items
  of round 15 were confirmed closed, and the round introduced TWO NEW
  HARMS while the live-blocker count went from 10+3 to 12: *"In count it
  is flat; in kind it is worse — the naked-short class went from one route
  to three, and two blockers are this round's own creation."*
* **The campaign question, asked explicitly as a stopping criterion**
  ("is this converging or thrashing? if each round introduces roughly as
  many as it closes, say so plainly and recommend a different approach"):
  the judge answered **"Both — and that is the actual finding"**, with a
  round-7 tally of ~8 closed against 2 new harms.
* **Remediated by:** this commit — and the response to the thrashing
  finding is the SHAPE of this round, not another open-ended sweep: three
  named defects with one root each, fixed by hand, no new subsystem, no
  new abstraction. See "What this round deliberately did NOT do" below.

| id | finding | status |
|---|---|---|
| CR-N1 | the flatten's completion alert told the operator to hand-sell a position the service had ALREADY sold. Same root as L1-L5: the pass never asked the venue what the account holds, so a row whose sell landed but whose ack was lost parked as "still held" and was then named in "CLOSE ... BY HAND". | `closed` |
| CR-N2 | B8's previous-CLOSE fallback was adopted as a FILL PRICE at the two paths that book a venue fill lacking a reported price, where `cc03347` raised and failed closed. A close is not a price anything traded at today; the basis was written silently. | `closed` |
| L1 · L2 · L3 · L4 · L5 | the naked-short class, five blockers with ONE root: `execute_flatten` fell through to `place_stock_order(sym, -pos.qty, "MKT")` sized from the BOOK, with no venue-position check. The judge named the single call that closes all five. | `closed` |
| L-E1 | **the `entry_ref` validation gap** — the top live blocker. `reference_prices()` has always fetched a real spot for every payload entry symbol, and the one place that sizes real orders from the tracker's `entry_ref` never read it. At a $10k book a 1.00 placeholder on a $50 name sizes ~300 shares, books $300 and fills ~$15,000: a 50x ledger-vs-account divergence on the FIRST trade, with every downstream gate then computed from the fiction. | `closed` |
| B9 | still `open`, unchanged and by instruction: the blend book has never taken a real fill in any mode. No code review substitutes for one supervised fill end to end. | `open` |
| CR-O1 | the ladder half of the kill retry is still unbounded. Unchanged this round. | `open` |
| L6-L12 | the remaining live blockers of the judge's twelve. NOT fixed here. | `open` |

### What this round deliberately did NOT do

The judge's own finding is that each round of this campaign closes roughly
as many defects as it creates. Widening the sweep is the move that
produced that pattern, so this round did the opposite: it fixed the four
items whose root cause the judge had already isolated to a single call
site, added eleven merge-blocking gates (each verified failing at
`f5e7154`), and stopped. L6-L12 are recorded above as open rather than
attempted. That is a scope decision, not a claim that they do not matter.

---

## Round 17 — counter-agent review of the tracker-blind watch

* **Reviewed:** the tracker-blind alerting change (reason taxonomy in
  `fetch_intents`, `_tracker_watch`, the `/health` `tracker` block,
  render.yaml declarations, gate tests) — reviewed at its pre-remediation
  state, diff preserved during the round.
* **Verdict:** **FAIL** — five independent lenses (state machine, silent
  failure, live-trading risk, test honesty, doctrine/merge), all five FAIL,
  45 findings. Every finding below was reproduced by execution before it was
  acted on; the fix's own author had shipped the round green at 306 tests.
* **Remediated by:** this commit.
* **The finding that mattered most:** the change was DECORATIVE at the only
  level that counts. Every gate exercised the pure `_tracker_watch` with an
  injected state dict, and nothing bound the loop to it — deleting the single
  line in `_loop` that arms the watch left the full suite green. A fix for
  silent failure that could itself be silently deleted.

| id | finding | status |
|---|---|---|
| SB-1 · T1 · T5 | the loop call site was ungated: five mutations that each restore the 2026-09-10 defect left all 306 tests passing | `closed` — `test_gate_the_loop_actually_arms_the_tracker_watch` boots the real service with TRACKER_URL unset and asserts the reason reached the watch; verified failing with the call site deleted |
| SB-2 · T1 · CA-3 | a 200 whose JSON body is `null` made `r.json()` return None, so the taxonomy returned `(None, "ok")` — a payload-less HEALTHY poll, the exact silent-blind shape the round exists to kill | `closed` — non-dict payloads raise into `decode` |
| CA-1 · CA-2 | the rename ORPHANED the seam: `tests/probes/mf2/scen.py` (6 sites) and the MF-1 slow-feed gate patch `blend_mod.fetch_intents`, and the loop no longer went through it — two phases of the live-fire probe suite and one merge-blocking gate silently stopped testing anything | `closed` — the wrapper is inverted so `fetch_intents` is still THE seam; a replaced seam is honoured and its reason inferred |
| SB-3 · T6 · CA-7 | `/health` reported `tracker.ok: true` for a service that had NEVER polled — the states a dead loop thread and a ladder-section raise leave behind — rebuilding the green lie inside the block written to end it | `closed` — tri-state; `null` means no poll has ever succeeded |
| T2 · T3 · CA-4 | a FLAPPING tracker re-armed the ladder on every recovery and the new-permanent-reason branch had no rate limit at all: measured 36-42 pages/day, against a README promise of "a handful, not hundreds" | `closed` — 30-min floor between any two pages plus `TRACKER_MAX_PAGES_PER_DAY`; measured ≤6, and a suppressed page is still logged |
| CA-5 · CA-6 · SB-5 | the watch was called UNGUARDED and BEFORE the `_superseded` checkpoint: `alerts.send` can raise, so a reporting call could abort the iteration before the protective `_blend_cycle` ran, and a superseded generation could page (against MF-2's law) | `closed` — moved after the checkpoint, wrapped |
| T4 · SB-9 | a malformed `TRACKER_URL` (`httpx.InvalidURL` / `UnsupportedProtocol`) was classified `transport`, the "usually heals" bucket, telling the operator the opposite of the truth about a permanent config error | `closed` — new `bad_url` config reason |
| T2 (doctrine) | the operator page asserted, as fact, that exits are "NOT affected" during a blind stretch. FALSE: a blind executor receives no intents at all. What saves exits is the tracker's 7-day echo — delayed, not lost | `closed` — page and README corrected; a confidently wrong claim in a live-money file is itself a defect |
| T3 (doctrine) | the recorded justification for in-memory watch state ("an unknown key on rollback is a SCHEMA_DRIFT halt") was FALSE — `BlendState._load` reads every key with `raw.get` and ignores unknown ones | `closed` — comment replaced with the true reason and the real cost named |
| SB-6 | `BLEND_ENABLED` — the flag the whole fix hangs off — was itself UNDECLARED in render.yaml, the identical defect class to B2 and to the incident being fixed | `closed` — declared, with `BLEND_BOOK_USD` / `BLEND_BUDGET` |
| T4 · CA-10 | the render.yaml gate was a substring check that still passed against configurations reproducing the incident | `closed` — structural: if the blend path is declared, its tracker wiring must be too; verified failing with `TRACKER_URL` removed |
| T9 · T5 | escalation rungs dropped the remediation instruction for config reasons — where the remedy IS the alert | `closed` |

### Found by this round, NOT closed

| id | finding | status |
|---|---|---|
| R17-O1 | **the pre-open (09:25 ET) rung is not built** — the most valuable page of the set. The ET/holiday machinery lives only on `main`, and a second copy here would collide at merge (Python silently takes the later definition). Cost, named rather than buried: the ladder decays to once-a-day after 4h, so a tracker blind since Monday pages at 10:10, 11:00, 14:00, then Tue 14:00 — never before an open on days 2+, and each day's fires are lost with the warning arriving after the fact. Build it immediately after the branch merges `main`. | `open` |
| R17-O2 | a STALE-but-successful payload plans zero entries with `tracker.ok: true`. `payload_is_stale` nulls the payload inside `run_cycle`, after the poll was already recorded healthy. Same symptom, different cause. | `open` |
| R17-O3 | nothing pages on a DEAD loop thread or a ladder-section raise. `/health`'s tri-state `null` surfaces both, and `loop_age_s` is the only other signal, but neither pages. | `open` |
| R17-O4 | the watch state is in memory, so a service restarting more often than 3 polls never reaches the transient threshold. Config reasons are immune (first-poll page). | `accepted-risk` |
| CA-9 | `/health` is unauthenticated and now tells any anonymous caller that the executor is blind, for how long and why. Judged acceptable: the endpoint already publishes `mode: LIVE` and, on `main`, gateway outage counts. Recorded rather than silently accepted. | `accepted-risk` |
| CA-8 | an INTERMITTENTLY failing tracker (never 3 consecutive) never pages and never shows blind. No cumulative failure-rate signal exists. | `open` |
| T7 (doctrine) | branch and `main` have diverged BOTH ways; a real `git merge origin/main` conflicts in 10 files, and `main` carries the SAME underlying bug. This change is written to merge as a sibling of `_gateway_watch` rather than duplicate it, but the merge itself is a human job and is not attempted here. | `open` |

**Gates, mutation-verified.** Nine mutations, nine caught, each by a named
gate: call site deleted · `cache_skip` counts as a failure · clock guard
dropped · page floor removed · `tracker.ok` reverted to two-state · null-JSON
guard removed · `bad_url` classification removed · `fetch_intents` seam
bypassed · `TRACKER_URL` removed from render.yaml.

---

## Round 18 — re-review of round 17's remediation

* **Reviewed:** `0dcd845` (round 17's fix) plus the uncommitted layer on top
  of it, across three lenses: new-code defects, regression, claims-and-gates.
* **Verdict:** **FAIL** — 3/3 lenses FAIL, 26 findings. The regression
  question itself came back a genuine PASS (all 8 probe suites land on their
  README marks, `BLEND_ENABLED=false` boot proven byte-identical by diff, no
  order dependence), so the round's shape is the campaign's standing answer
  once again: **no regression, new harms.**
* **Remediated by:** this commit.
* **The finding that mattered most, and it is the same shape as round 17's:**
  round 17's headline gate was STILL decorative. It monkeypatched
  `service._tracker_watch` with a spy, proving only that the loop called
  *some* function with the right string. Passing a throwaway state dict at
  the call site — `_tracker_watch(now, reason, send, dict(TRACKER_WATCH))` —
  restored the 2026-09-10 defect in full (steady `transport` → 0 pages/day
  forever; steady `auth` → 288/day; `/health` pinned at `ok: null`) with all
  316 tests green. Two rounds running, the gate for "this must not fail
  silently" could itself be removed silently.

| id | finding | status |
|---|---|---|
| R18R-1 | the loop gate asserted on a SPY, not on the module-global `TRACKER_WATCH` that `/health`, the ladder, the floor and both budgets all read | `closed` — the gate now lets the real decision function run and asserts the global advanced AND `/health` changed AND the page went out; verified failing against the throwaway-dict mutant |
| R18-1 | the shared daily budget could starve the round's own headline guarantee: a flapping transient spends all six pages, then a rotated token (`auth`) is suppressed for up to 20.5h — measured — with a documented promise of an immediate page | `closed` — config diagnoses bypass the floor and draw on a reserved `TRACKER_MAX_CONFIG_PAGES_PER_DAY` |
| R18-2 | the 30-min floor swallowed the RECOVERED line for the most common outage lengths (15-35 min) while the state reset regardless: the operator got 🚨 BLIND and then permanent silence | `closed` — recovery is exempt from both limits; it is self-bounding, since it only fires for an outage that already paged |
| R17R-1 · R18-4 · R17R-5 | the floor suppressed silently, contradicting "a suppressed page is still logged, never invisible"; and `_page` spent the floor and the budget BEFORE `send_fn` returned, so one broken transport muted the next real page and a raising pager aborted the decision mid-way | `closed` — every refusal logs; the send is attempted first and guarded, and stamps only on success |
| R18R-2 | both budget gates were TAUTOLOGICAL — they imported the constant under test and asserted against it, so setting either to 10**9 left the suite green and the budget could be removed in production | `closed` — absolute bounds, with the constants pinned separately |
| R18R-3 | four round-17 rows marked `closed` were code-only and ungated: the watch's try/except, its position after `_superseded`, the escalation rung's remedy `tail`, and `_TRACKER_BLAST`'s corrected blast-radius text. All four could be deleted with 316/316 green | `closed` — one gate each |
| R17R-2 · R18-3 · R18R-8 | the tri-state did not cover the likelier shape: a loop wedged AFTER one good poll reported `ok: true` forever on a stamp hours old. Round 17's R17-O3 claimed the tri-state covered it; that claim was false when written | `closed` — `null` now also means "last success older than max(3 × POLL_SECONDS, 900s)" |
| R17R-3 · R18R-4 | a hand-typed `TRACKER_URL` with a stray space (it is `sync: false`, so it IS hand-typed) was classified `transport`, the self-healing bucket — the exact misdiagnosis the round exists to prevent. And the `.strip()` that fixed it, plus `_reset_tracker_watch`, were themselves ungated | `closed` — value stripped, and one gate each |
| R17R-4 | `TRACKER_WATCH` was never re-initialised per lifespan, unlike `LADDER_KILL`, so one lifespan's blind state made the next boot's `/health` lie | `closed` — `_start_loop` resets it |
| R18-6 | `_LAST_INTENTS_REASON`'s docstring asserted single-thread access, which `_stop_loop`'s timed join makes untrue | `closed` — docstring states the real window and why the worst case is a mislabelled reason, never a wrong payload |
| R18-7 · R18R-9 | 404 was promoted to a never-self-heals config reason (`no_route`) on the strength of an unsourced claim about Render's edge ("a tracker mid-deploy answers 502/503, not 404") | **REVERTED, not fixed.** 404 stays transient. A single 404 from a router or WAF would have paged 🚨🚨 "this will NOT self-heal" on the first poll, and the justification was an assertion about a third party that nothing here establishes — the house rule is not to publish a verdict conditioned on an input we do not have. The 10-minute transient threshold is a small price. |
| R18R-6 · R18R-7 · R18R-11 | README claims that did not match the code: the budget table implied a config outage's escalation rungs draw on the reserved budget (they are tagged by rung, so they draw on the shared one); the tri-state was said to cover a `_build` raise (that leaves `BLEND` None, so the whole section is ABSENT, not null); "the three that never self-heal" against a four-member set; no composite worst case stated | `closed` |

### Found by this round, NOT closed

| id | finding | status |
|---|---|---|
| R18R-12 · CA-8 | a tracker failing 2 of every 3 polls — losing two thirds of every entry window — produces ZERO pages over seven simulated days, because an `ok` resets `fails` before the 3-consecutive threshold is met, and `/health` sampled after any good poll reads `ok: true`. There is no cumulative failure-rate signal anywhere. Worse than CA-8's one-line round-17 entry implied. | `open` |
| R17-O4 (revised) | the in-memory watch is defeated by a restart loop in TWO ways, not one: a container restarting faster than 3 polls never reaches the transient threshold (recorded), and `_reset_tracker_watch` now also re-arms BOTH daily budgets on every boot (not recorded until now). | `accepted-risk` |
| R17-O1 | the pre-open 09:25 ET rung, unchanged and still the most valuable page not built. Gated on the branch merging `main`. | `open` |
| R17-O2 | a stale-but-successful payload still plans zero entries with `tracker.ok: true`. | `open` |
| T8 (r17 verify) | `_tracker_watch` uses wall-clock `time.time()`, which is not monotonic. A backward NTP step mid-outage makes `blind_for` negative; `_tracker_step(negative)` returns 0, so an escalation rung is delayed until the clock catches up. Never silence — the count-based first page and the config first-page are unaffected — but a rung can arrive late. Confirmed 2/2 by the round-17 verify pass, which completed after round 18 shipped. | `accepted-risk` — the loop has no monotonic clock source today; recorded so it is not rediscovered |
| R18R-0 | **process finding.** Three reviewers read a tree that was being edited under them, and one snapshot they took was RED (a mid-edit gate failing). Their findings were still sound, but a review of a moving target is a review of nothing in particular. Next round: snapshot with `git archive` and review the snapshot. | `closed` (recorded as the rule for the next round) |

### Corrections to round 17's own record

Round 17 stated three things this round found to be wrong, corrected here
rather than left standing:

* **"36-42 pages/day"** is the floor-PRESENT, budget-ABSENT figure. The
  pre-remediation code had neither, and measures **96-288/day**. Round 17
  understated the harm it was fixing by 4-8x.
* **R17-O3's mitigation sentence** ("/health's tri-state null surfaces
  both") was false when written — see R17R-2 above.
* **CA-8** was recorded as "never pages and never shows blind". The second
  half flatters it: after any good poll `/health` reads `ok: true`, which is
  worse than "never shows blind".

**Gates, mutation-verified.** Round 17's nine plus this round's: throwaway
state dict at the call site · shared budget removed · config budget removed ·
watch try/except removed · escalation remedy dropped · per-lifespan reset
removed · `if sent:` guard removed · reserved config budget removed ·
recovery no longer floor-exempt · wedged staleness removed · `.strip()`
removed. Every one caught by a named gate.

---

## 2026-09-10 — B9 partially discharged: the first real venue fill

* **B9** (round 15, by the judge's instruction: "the blend book has never
  taken a real fill in any mode — a PROCESS gate, not a code fix; note it,
  do not close it") has been open since it was written. Today the book took
  its first real fill, supervised: `🧬 blend SWEEP BIL -10` accepted at
  14:53 ET, one cycle after Restart 2, and booked correctly —
  `sleeve_cash 66.34 → 980.02`, `bil_qty 163 → 153`, the ledger moving by
  exactly the fill.
* **Why it had never happened.** Not a code defect. The IB Gateway session
  had been write-denied since 2026-09-08: IBC set the Read-Only API checkbox
  to false on every boot, and the Gateway then raised an "API client needs
  write access action confirmation" dialog that IBC has no handler for.
  Every `placeOrder` and every `cancelOrder` returned 321. Fixed by
  persisting the Gateway's settings on the mounted disk
  (`TWS_SETTINGS_PATH` + `SAVE_TWS_SETTINGS`) so the checkbox is already
  false at login and there is no change to confirm. Runbook in README.
* **What is NOT yet discharged.** The judge's B9 named the full chain: a MOO
  entry adopted by reconcile after the open, its GTC stop landing, and the
  first ratchet cancel/replace. Today's fill is a book-level sweep. The
  entry chain is in flight: GH (call 18, ~6 sh, $966) goes out as MOO after
  16:00 ET today for Friday's open. **B9 stays `open` until GH's stop is
  resting at the venue.** Close it then, with the order refs.
* **Second-order corrections this discharges.** The 2026-09-08 finding that
  "the gateway never answers `reqCompletedOrders` on ANY session"
  (`VENUE_HISTORY_TIMEOUT_S`'s rationale, the execution-report fallback in
  `find_stock_order`) was a symptom of the same write-denied session, not a
  gateway limitation. The fallback is harmless and stays; the rationale
  comment is now wrong and should be corrected when that file is next
  touched.
* **Exposed credentials to rotate.** `TRACKER_API_TOKEN`/`BLEND_API_TOKEN`
  (a value was legible in a screenshot) and `EXEC_TOKEN` (pasted as a bare
  word into a shell command). Both are burned; rotate after GH's stop lands,
  never mid-window.

---

## `main` lineage (not indexed round-by-round)

`main` ran its own counter-agent rounds on the same book between 2026-08-24
and 2026-09-08 while this branch was cut: the market-data posture, the cash
reconcile and funding rules, MF-A / MF-1..3, B8, CR-N2, L-E1. Their verdict
documents were never committed either; their findings are cited inline in
README.md and in the code by id. They are NOT reconstructed here — the
merge round below reviews the COMPOSITION of the two lines, not `main`'s
rounds themselves. If a finding id from that lineage is ever needed by
name, reconstruct it from `git log origin/main -- ibkr-executor/`.

---

## Merge round — `origin/main` (4cab3e2) into this branch, 2026-09-10

* **Reviewed:** the staged merge — 10 conflicts resolved by anchor-based
  hunk composition, the composed test files, the probes README run
  preconditions. Five counter-agents in parallel, one lens each:
  composition (does `main`'s L-E1 / cash / B8 work compose with the branch's
  tracker watch), emergent (interactions neither line had alone), test-edits
  (are the post-merge test rewrites honest or vacuous), docs/config
  (render.yaml, both READMEs, this index), deploy (what the LIVE service
  sees when `main` takes this).
* **Verdicts:** composition PASS WITH CORRECTIONS · emergent PASS WITH
  CORRECTIONS · test-edits PASS WITH CORRECTIONS · docs/config PASS WITH
  CORRECTIONS · deploy **FAIL** (one HIGH: the merge would have flipped the
  live IB client id on the very deploy that restarts the gateway).
* **Remediated by:** the merge commit itself (rule below: verdict and
  remediation in one commit). Every gate below was mutation-verified in the
  same pass — the fix reverted, the gate red, the fix restored.
* **Materials and status:**
  * **Deploy F1** (HIGH) `closed` — render.yaml `IB_CLIENT_ID` kept at the
    code default 17 (the branch had 1701); the B10 gate now asserts
    declared == code default so a blueprint sync is a no-op on the live
    service. The branch's collision story was also wrong and is corrected
    in the comment, the README row and the gate: `_connect` retries 20 x
    (15s + 15s), ~10 min, then raises `ExecutorConnectionError`, which the
    boot-retry loop CATCHES and pages — the loop thread does not die; and
    the gateway is in-container (`TrustedIPs=127.0.0.1`), so no external
    client can hold the id at all. Mutant: value 1701 → red.
  * **Composition F1** (HIGH) `closed` — the pre-fund hold and its release
    charged `entry_ref`; `main`'s L-E1 charges `size_ref` =
    max(entry_ref, venue quote). On a gapped-up quote the BIL raise covered
    the real cost, the hold covered the reference cost, the gap read as
    idle and the sweep bought it back; the post-close placement then
    clipped. Both sites now use `_intent_size_ref`. Gate:
    `test_gate_prefund_hold_is_at_the_charged_price_not_entry_ref`.
    Mutants: each site reverted → red.
  * **Composition F2** (MED) `closed` — `reserved_sleeve_cash()`'s
    resting-entry term at `_intent_size_ref`. Gate:
    `test_gate_resting_entry_reserves_its_charged_cost` (two fires one
    evening on a gapped quote: B may not place against A's reserve; ledger
    ≥ 0 at the open). Mutant: reverted → red.
  * **Composition F3** (MED) `closed` — dead `_await_tick` / `_ticker_price`
    deleted from ib_adapter.py; the three market-data tests that exercised
    the dead twin retargeted at `_await_quote`, asserting the source tuple.
  * **F4 / T2** (LOW) `closed` — the B8 type-before-subscribe gate was
    satisfiable by `connect()` alone. It now clears the connect-time
    request and asserts ORDER on an event log. Mutant: the
    `_apply_market_data_type` call removed from `spot_ex` → red.
  * **T3** (LOW) `closed` — the retire-on-failure gate compared multisets;
    it now asserts strict sub/cancel alternation. Mutant: cancel removed →
    red.
  * **F5** (LOW) `closed` — the MF-A mid-section kill consumption and
    `MGR.save()` sat inside `if settings.ladder_enabled`: with the ladder
    disabled (the deployed posture) a /kill landing after the
    top-of-iteration pass waited a whole poll interval. Dedented. Gate:
    `test_gate_f5_a_kill_landing_mid_iteration_is_consumed_with_the_ladder_off`.
    Mutant: block re-gated on the flag → red.
  * **F6** (LOW) `closed` — the B8 pin rationale claimed `marketPrice()`
    lost its close fallback between ib_async majors. The 1.0.1 and 2.1.0
    sources were fetched and diffed: byte-identical, and neither has a
    close fallback (that was ib_insync's, before the fork). Corrected in
    requirements.txt, both B8 docstrings and the `spot_ex` comment; the pin
    stays as dependency hygiene.
  * **T1** (MED) `closed` — the boot-retry gate's bare try/except passed
    vacuously on a loop that returned without retrying. Now
    `pytest.raises(_Escape)` and attempt == 2. Mutant: early return → red.
  * **EM-1** (LOW) `closed` — the MF-2 supersede checkpoint sat in the
    retry branch only; a loop superseded DURING a successful build walked
    on to announce itself and trade beside the current loop. Checkpoint
    added on the success path. Gate:
    `test_gate_em1_a_loop_superseded_during_a_successful_build_exits`.
    Mutant: check removed → red.
  * **EM-2** (LOW) `open` — during a boot login stall (the state the
    boot-time `_gateway_watch` pages for) `/health` reports
    `mode: OFFLINE` and `gateway.down_since: null` while Telegram says the
    gateway is down: the boot watch is fed `LAST["build_fail_since"]`, which
    the outage ledger and `/health` never see (`IBAdapter._connect` never
    calls `outages.start()`). Two observability surfaces disagree. Not
    fixed in the merge (neither line's regression); follow-up.
  * **EM-3** (LOW) `open` — a payload whose `as_of` is older than
    `STALE_PAYLOAD_DAYS` is fetched with reason `ok`: TRACKER_WATCH records
    ok, `/health tracker.ok` is true, and the loop plans nothing. LOUD,
    not silent — `main`'s per-cycle "tracker payload is stale" alert fires
    every cycle, 288/day, the exact storm shape the branch's decaying
    ladder exists to prevent. README "Not covered" item 2 already names the
    gap; the fix is a `stale` reason routed through the ladder. Follow-up.
  * **DOC-1..7** `closed` — IB_CLIENT_ID comment and README row (DOC-1);
    the orphaned READ_ONLY_API paragraph (main's, stranded when the
    duplicate key was deduped) folded into the key's comment, and the
    outage-ledger paragraph moved onto its keys (DOC-2);
    `TWS_SETTINGS_PATH` (literal — it must be on the disk) and
    `SAVE_TWS_SETTINGS` (sync:false) declared, README write-arming
    paragraph cross-referenced to "Error 321 has TWO causes" (DOC-3);
    README "Not covered" item 3 reworded — the ET helpers are in scope since
    the merge, the rung is unbuilt by scope alone, and it named
    `PREOPEN_FROM/TO`, which does not exist (DOC-4); the README index
    paragraph scoped to this branch's rounds with the lineage stub above
    (DOC-5); probes README preconditions corrected BY EXECUTION —
    `attack_reround`'s traceback and `ZF-E1b` are the session clock, not
    the ladder flag (both reproduce their marks after 16:00 ET with no pin
    and no flag); `attack_mf2` A4/A10 are the flag (52/56 → 54/56) (DOC-6);
    the TRACKER_URL comment rewritten to the incident as it happened — set
    by hand, undeclared — and its "MUST be the canonical host" claim
    corrected: the tracker 308-redirects only `REDIRECT_HOSTS`
    (`genomics.optic.capital`); the onrender host answers directly and is
    what the live service polls at 200 (DOC-7).
* **Open items recorded here, deliberately NOT changed in the merge:**
  * **OPG window.** `SESSION_CLOSE_ET = (16, 0)`, but IBKR refuses an OPG
    order "when market is open" until EXTENDED hours end at 20:00 ET.
    Measured 2026-09-10: GH's MOO placed 16:03 ET rejected `[202]` five
    times → the ENTER breaker paused the kind → the pre-fund hold had
    already been released by the placements → the sweep bought the entry's
    cash back (`BIL +10`, 16:19 ET) → the entry slips a session unless the
    resting sweep is cancelled by hand at 20:00 ET. Systematic for every
    mid-session fire. Fix: close the window at 20:00 ET (17:00 on
    early-close days) AND keep the hold through a venue rejection. Its own
    round, with gates — the FIRST post-merge item.
  * **Pre-open 09:25 ET tracker rung** (README "Not covered" 3): helpers
    in scope since this merge; unbuilt.
  * `VENUE_HISTORY_TIMEOUT_S` rationale comment: still wrong (see the B9
    entry above); correct when the file is next touched.
* **Deploy-time change list — what the live service sees when `main` takes
  this:** `IB_CLIENT_ID` unchanged at 17; new blueprint keys
  `BLEND_ENABLED` / `BLEND_BOOK_USD` / `BLEND_BUDGET` / `TRACKER_URL` /
  `TRACKER_API_TOKEN` / `SAVE_TWS_SETTINGS` are sync:false (a sync does not
  add sync:false keys to an existing service; the dashboard already holds
  them); `TWS_SETTINGS_PATH` is a literal equal to the dashboard's current
  value (no-op); `READ_ONLY_API` declared once (was twice in the raw
  merge); the tracker-blind watch goes live (pages on the first config
  failure, decaying ladder on transients, tri-state `/health tracker.ok`);
  F1/F2 change the hold/reserve arithmetic on the next gapped-up fire. The
  deploy restarts the container and forces a gateway login + IB Key push:
  merge after GH's stop is resting, never mid-window.
* **Suite:** 431 passed; the eight attack probes at their documented marks
  under the corrected preconditions.

---

## Standing UNKNOWNs

* `mf-6`, `mf-11`, `mf-12`, `mf3-12` — referenced by id in this campaign's
  instructions but present nowhere in the code, the tests, the probes or
  the git history. The verdict files that defined them were destroyed with
  the scratchpad. **Do not guess at them; ask.**
* The verdict WORD for rounds 2, 5, 6, 8, 9, 10, 11, 12, 13 and 14. Each
  round's findings are reconstructable; the PASS / PASS WITH CORRECTIONS /
  FAIL label is not, because no commit recorded it.

## Rule for the next round

Write the verdict here, in the same commit as the remediation, before the
scratchpad can eat it. One row is enough: round, what was reviewed, the
verdict word, the material ids, and the status of each.
