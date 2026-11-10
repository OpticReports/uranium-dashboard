**Second independent verification — six blocking fixes and the limit-order path**

No BLOCKING or SERIOUS defect found; three MINOR defects (one in B1, two in B2 sharing a root) and one rollout condition on B4.

Reviewed at `d0ecccdb`; HEAD moved to `c89d3fb7` during the review, and `git diff d0ecccdb c89d3fb7` is empty for `ibkr-executor/` and the four composer scripts. I edited no tracked file. Baseline: 215 executor mirror tests and 69 composer tests pass.

Scratch directory: `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/V2/` (outputs in `out_*.txt`). Run executor files with `V2_NO_FSYNC=1` and `--rootdir` set to that directory.

| # | Item | Verdict |
|---|---|---|
| 1 | A-01 halt / kill / resume mid-tick | VERIFIED |
| 2 | A-03 kill, resume, kill | VERIFIED |
| 3 | Limit-order path | VERIFIED |
| 4 | B1 decision instant, determinism | VERIFIED, 1 MINOR defect |
| 5 | B3 dead data | VERIFIED |
| 6 | B4 tree-version gate | VERIFIED as specified; fail-open by default |
| 7 | B2 dividends and splits | DEFECT, 2 MINOR (one root) |

**1. A-01 — VERIFIED**
- Tried: a halt, a /kill, and a halt with the wake set, fired from inside every instrumented point of a tick (each clock read, venue call, brain call and file write, before and after). Five scenarios: first-day buys, a day-2 rotation with a cross and a transfer, then with a buy resting, a sell resting, two buys resting. 142 / 149 / 540 / 482 / 828 points, about 6,400 runs.
- Result: zero new run orders after the halt beyond the one whose halt check had already passed. Run closed, nothing left working, book equals account in shares and cash. Under /kill only flatten sells follow and the account ends flat.
- /resume at every point of a flatten (three hold variants): no flatten order sent after the cancel.
- Broken twins fail (75 of 149 points; 62 of 91), so the sweep is not vacuous.
- Inherent residual: one order can go out if the halt lands during its write-ahead save.
- Files: `test_v2_a01_sweep.py`, `test_v2_a01_twin.py`.

**2. A-03 — VERIFIED**
- Tried: all 5,425 sequences up to five steps over kill / resume / halt / tick / restart / release with the first flatten's sells resting; 2,500 random sequences of 5–15 steps adding partial fills on cancel and a stuck cancel.
- Result: the account is never short, working sells never exceed holdings, no working order lacks a record, no id is sent twice, and the book equals the account at the end. The reviewed behaviour, re-created as a twin, trips the harness.
- Real adapter (554 sequences with restarts): the same safety invariants hold in all.
- With the repo's fake, 66 sequences end with cancelled flatten orders UNRESOLVED after a restart; they are never booked as zero and need `/mirror/resolve`. The fake does not add `reqAllOpenOrders` results to the session; ib_async 2.1.0 does (read in the installed `wrapper.py`), and with that behaviour 0 of 554 fail.
- Files: `test_v2_a03_sequences.py`, `test_v2_a03_twin.py`, `test_v2_a03_real_adapter.py`.

**3. Limit-order path — VERIFIED**
- Diff `7e61a970..HEAD` on `ib_adapter.py` is +328 / −1. The one changed line is `_await_placement`'s fill wait accepting `"LMT"`, which no existing caller passes (`place_stock_order` rejects it). Existing order types are unchanged.
- Tried on the real adapter:
  - Dedupe after a restart: a resting order is found with completed orders available or not; a filled order is found when completed orders are available, including the bare form.
  - Rounding fuzz, 200,000 prices: buy limits are floored, on the grid, idempotent, and fail closed.
  - Partial fill inside the wait then window-end cancel: books 40 shares at the venue's price.
  - Cancelled and Inactive rejections: book zero, not re-sent; the Inactive order is cancelled.
  - Missing ack: adopted, not re-sent.
  - Tape 1.2% above the brain with fills at the limit: no borrow.
- `size_buys` with limits, 20,000 random books: a sleeve's buys never cost more than its cash before commission. The order is placed at the limit it was sized at.
- Notes, none blocking:
  - A filled order under the key, after a restart with completed orders unavailable, is re-placed at the adapter level. The existing market path does the same (`ib_adapter.py:1254-1263` against `1200-1207`). The manager always looks the order up first, and adoption after such a crash passes.
  - The 0.1% reserve (`mirror_core.py:59`) is below IBKR's $0.005 a share for names under $5. Fuzz worst case with $3 names filled at the limit: a sleeve at −$38 on $60k, the book at −$112. The cheapest holdable names today are LABD $6.58 and ZVOL $7.02, so this is inside the reserve for now.
- File: `test_v2_limit.py`.

**4. B1 — VERIFIED, one MINOR defect**
- `decide_utc` is the close minus six minutes exactly on a full day, a half day and in summer time. The pinned read at T takes the same bar `minute_price(day, "15:54")` does for all 62 fixture tickers and never the next bar.
- Two builds for one T are identical in every field but `built_utc` across five variations: later second, later FMP bars, Yahoo sale before / inside / after the decision minute, no Yahoo bar for today, wall clock a second behind. Targets and prices also equal a build on data fetched days later.
- Incomplete builds are a 503 and never cached (SPY bar missing, build raises, SPY history short). 400 and 409 are correct.
- **DEFECT, MINOR** — `mirror_brain.py:655-656`: the pinned cache evicts the oldest instants once four later ones are asked, which is the decision instant first, and the next request rebuilds it.
  - Repro: `v2_brain_defect_eviction.py`. Output: `REBUILT (builds=6); built_utc 20:54:25Z -> 20:58:30Z; prices that moved for the SAME asof_utc: KIE 64.34 -> 64.30, PEJ 66.92 -> 66.655`.
  - Fix: never evict an instant of the current ET day.
- Residual: `unsettled()` (`mirror_brain.py:554-566`) lets a build go with up to 15% of tickers a bar behind, so a live payload's prices can differ from a rebuild or `--at`. Targets did not move in about 1,000 lag sets on the two fixture days.
- Files: `v2_brain.py`, `probe_latebar.py`.

**5. B3 — VERIFIED**
- All five cases leave the affected engines unavailable with no target: feed stalled 16 minutes; shut at 13:00 with no Yahoo trading period (pinned and ad hoc); SPY fresh with the rest stale; a decision ticker with no trade today; history a session short (SPY short makes all four unavailable and the payload incomplete).
- Executor: an unavailable engine is not traded, crossed or transferred with, even with a target left in its row or a status of "OK". Eight invalid payload shapes are never acted on.
- Residual, by design: an engine stays ok with under 25% of its decision tickers arbitrarily old if they traded today. Example: SLEEVE ok with BOXX, CORP, HYG, IEF, KIE 16 minutes old. They are named in `stale`, which the executor ignores.
- Files: `v2_brain.py`, `test_v2_b3_executor.py`.

**6. B4 — VERIFIED as specified in contract-v2**
- A drifted engine is unavailable. Posts for another day are refused (400) and yesterday's stored attestation reads "none" today. No token gives 404; a wrong, API, empty or truncated token gives 401. One hash function on both sides, and it covers `rebalance` and the corridor width.
- Condition for live: the gate is fail-open by default. A missing or late attestation trades the approved tree with a line in `problems` (`mirror_brain.py:438-442`), and the executor does not read `sync`.
- A drift attested 14 seconds after the pinned build is not seen that session; the payload still says HARV ok, sync none.
- No schedule for `mirror_attest.py` exists in the repo. Live needs `MIRROR_REQUIRE_ATTESTATION=1` and the routine finished before about 15:54:20.

**7. B2 — DEFECT, two MINOR with one root**
- Holds: 160 random 12-session histories per rule (621 receivables, 80 splits, restarts, skipped sessions, ten-day relisting, a venue that pays on the pay date). In 159 of 160, every receivable matches an independent model in shares, total and status, none is credited twice, splits apply once, and book cash equals account cash less leaks and cash in lieu. A live credit waits for the account's cash and is credited once.
- Root: `mirror.py:1319-1329` (`_holdings_before`) reads only history rows, and shares change outside a run with no row: the flatten, `_apply_splits` (`:1301`), `_adjust` (`:697-702`).
- **(a)** A /kill flatten, then an ex-date on a session with no plan: the next plan books a receivable for shares already sold. Output: `receivables for shares the book sold BEFORE the ex-date (the account was paid nothing): HARV 301 $60.20 credited, KMLM 145 $29.00 credited`. It is credited only when the account holds cash outside the book (a staged rollout); otherwise it waits and expires loudly.
- **(b)** A split, then an ex-date, with neither session planned: pre-split shares at the post-split amount. Output: `split x3: account paid $267.60; book booked $89.20` and `split x0.2: account paid $17.80; book booked $89.20`. The reverse split over-credits under the same cash condition. Seed 5 of the property test is this case.
- Fix: append a holdings row to the history whenever shares change outside a run, dated the day of the flatten or adjust, and the split's own date for a split.
- File: `test_v2_b2_dividends.py`.

**Do the blocking fixes hold: yes.** B4 is fail-closed for live only with `MIRROR_REQUIRE_ATTESTATION` set.