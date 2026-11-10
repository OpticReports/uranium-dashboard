# IBKR mirror — reviewer B, round 2 (parity, data, timing)

**PAPER: CLEAN on my lens.** The brain and the executor's paper book run end to end on real payloads; start the paper clock and fix R1–R4 during it.
**LIVE: FIX-THEN-SHIP.** R1–R4 before live money. S5 (book mix), M2 (KMLM start day) and the residual decision-minute miss rate are owner calls to make on the paper record.

Reviewed code at d0ecccdb; HEAD 8a2bd391 adds only the design doc and one `render.yaml` key. That commit's message calls the executor fixes "WIP, not complete, not verified"; my verdict covers parity, data and timing only. Baseline at HEAD: 175 composer tests and 196 executor tests pass. I did not review `mirror_dry.py` this round.

Evidence, all read-only:
- 15 real pinned builds over the network (2026-10-20..11-09), plus 07-15 and 08-28.
- Composer's trade-activity report and a live read of its four trees.
- Yahoo wire charts and FMP's dividend and split lists for 62 tickers.
- The round-1 minute bars.
- The executor's own `Rig` and `Venue` test doubles.

Exhibit: `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/B2/exhibit2.html` (PNG beside it).

## 1. Round-1 findings

| ID | Status | Evidence |
|---|---|---|
| B1 decision instant | **Fixed as specified** | `decide_utc` is 15:54:00 ET (12:54 on 11-27). Two pinned builds 69 s apart with different Yahoo last sales give identical engines, prices and price times. The real client against the real server gets 409 before T, 503 until SPY's bar, then the same payload at T+25 s and T+200 s. Residual in section 2. |
| B2 distributions | **Fixed** | Receivables from shares at the close before ex, settled on FMP's pay date. On real payloads: PULS ex 10-30 credited 11-03 (HARV $64.92, KMLM $34.66); BIL ex 11-02 credited to HG 11-05. The "composer" rule matches Composer (section 3). |
| B3 dead data | **Fixed for the cases raised** | Feed stalled at 15:38, market shut at 13:00, and a session-short history each make the affected engines unavailable; the first two are also incomplete, so a 503. Residuals: R1, R5. |
| B4 tree gate | **Mechanism fixed; not armed** | Drift makes the engine unavailable; every era's tickers are priced (ANGL, BSV, SPAB, VBF included); Composer's four live trees hash equal to the approved ones through `mirror_attest.py`. Default is still fail-open: R3. |
| S1 unbooked dividends | **Fixed when FMP's list is read** | 302 booked dividends, un-booked one at a time, are each repaired to within 0.02% of Yahoo's own series; two unapplied splits are repaired exactly. On the shadow record, 0 of 308 engine-sessions change target. Not robust to a list failure: R2. |
| S2 splits | **Fixed** | `apply_split` keeps sleeve value across a 1:5; ratio direction is the same on both feeds (SQQQ 1:5 gives 0.2, TQQQ 2:1 gives 2.0). A split listed after the book ran on post-split prices is a red alert and a manual adjust. |
| S3 slow feed | **Fixed** | Four concurrent requests share one build; FMP budget 10 s, timeout 8 s; history cached per session. New: R1, R2. |
| S4 calendar | **Fixed** | 2028 dates return no session with a reason. An early close the table lacks is now a 503 and a red NO TRADE, not orders into a closed market. |
| S5 book mix | **Not addressed** | Still seeds 29/29/27/15 against Composer's 34.3/26.8/26.5/12.4. Owner decision. |
| S6 commissions | Unchanged | Structural; table in section 5. |
| S7 replay | **Fixed** | Real `--at` at 15:54 on 07-15 and 08-28 equals Composer's holdings on 7 of 7 engine-sessions. |
| M1 corridor | **Fixed, exact** | 20,000 random sleeves: largest difference from Composer's measure 0, no decision differs. KMLM record from 09-15: 0 of 36 sessions differ. |
| M2 KMLM start | **Not fixed** | Documented as an owner note in `mirror.py`; nothing aligns the start day. |
| M3 buy cushion | **Fixed** | Buys are limits sized at the limit (section 3). |
| N4 token over http | Not fixed | `mirror_attest.py` enforces https; the executor still sends its token to whatever scheme `MIRROR_BRAIN_URL` has. |
| N5 single source | Wider | FMP is now a hard dependency for the decision; there is no Yahoo fallback in a pinned build. |

Nothing regressed.

## 2. New findings

### R1 — SERIOUS. A 45-second FMP hiccup freezes an all-unavailable answer for the session
`composer/scripts/mirror_brain.py:88, 652-657, 688-694`

- FMP answers 429 for 40% of the tickers until T+50 s, then is healthy. The brain answers 503 until T+44 s; at T+47 s it builds with what it has: breadth 27 of 48, every engine unavailable, `complete: true`. That payload is cached for good.
- T+60, T+120 and T+200 s return the same payload although the feed is back. The executor's deadline is T+240 s.
- On a live book the result is outcome `no-targets` and one info-level line (see R4).
- Repro: `pinned_giveup.py` case 1.
- Smallest fix: when the give-up build has unanswered tickers, or any engine is unavailable for a feed reason, keep answering 503 and retry; the executor's plan-by already bounds lateness. Cache only a settled build.

### R2 — SERIOUS. One failed burst of FMP list calls at warm-up switches S1 off for the session, silently
`mirror_brain.py:90, 589-591`; `shadow_runner.py:96-97`

- The first warm pass at T−10 min makes 62 Yahoo calls and 124 FMP list calls. Five list failures open the breaker for 600 s, which is the whole warm window.
- `History` then caches all 62 Yahoo-only histories as "final". Nine more warm passes with FMP healthy refetch nothing.
- The pinned build at T is `ok` for all four engines on the unrepaired history: CR(SHY,1) on 11-02 reads −0.29% (true +0.02%). The payload carries one `problems` line, which the executor does not read.
- The dividends list loses the 11-02 events and every pay date; the executor then assumes ex + 7 days for a receivable first seen that way, permanently.
- Repro: `history_fmp_blip.py`.
- Smallest fix:
  - Treat a history as not final while `corporateActions.fmp` is false.
  - Make the breaker shorter than the warm window and warm from T−30.
  - Do not mark a dividend as seen in the executor until its pay date is known.

### R3 — SERIOUS for live. The tree gate is opt-in, has no freshness bound, lives in memory, and nothing schedules it
`mirror_brain.py:195-233, 241-262`; `ibkr-executor/app/mirror.py:1203-1221`

- With no attestation the brain publishes all four engines `ok` and the live book trades them. The only trace is a `problems` line; no alert mentions it.
- An attestation stamped 09:34 ET counts as `ok` at 15:54. An edit after the job runs is not seen.
- A brain restart loses the attestations and falls back to trading unverified.
- `MIRROR_REQUIRE_ATTESTATION` defaults off, and no routine runs `mirror_attest.py`.
- Auth is sound: no token, the read token, yesterday's or tomorrow's session, a bad hash and an unknown engine are all refused; no secret appears in output.
- Repro: `attest_attacks.py`, `executor_loudness.py` case 4.
- Smallest fix:
  - Set `MIRROR_REQUIRE_ATTESTATION=1` on the brain for any live engine.
  - Schedule the job at about 15:50 ET and repeat it each minute to 15:54.
  - Treat an attestation older than about 15 minutes before T as none.
  - Have a live book refuse a sleeve whose `sync.state` is not `ok`.

### R4 — SERIOUS for live. A sleeve the brain holds back is reported at info level
`mirror.py:1955, 2015`

- Every engine unavailable on a live book: `no-targets`, one info line.
- HG in drift (Composer running unapproved logic): the other three trade; the drift appears only inside the normal daily info line.
- By contrast a 503 all window is a red NO TRADE.
- Repro: `executor_loudness.py`.
- Smallest fix: use the loud level whenever an active sleeve's action is `skip`, and put the payload's `problems` in the message.

### R5 — MINOR. A decision ticker rebuilt from a sibling still decides
`mirror_brain.py:426`; `preclose.py:186`

- TQQQ's own bars cut at 15:30 with everything else normal: TQQQ is priced "via QQQ", `price_times` shows T (the sibling's time), and HG, KMLM and SLEEVE stay `ok` and `firm`. The same holds with TQQQ, SOXL and TECL cut since 14:00.
- The docstring says an estimate makes the engine unavailable; the code checks only "traded today". HARV is caught by the 75% rule (1 of 2).
- Not seen on real data: 0 of 13 sessions.
- Fix: count a decision ticker whose stamp is not a trade of its own as an estimate.

### R6 — MINOR. Every 503 reads as "bar not published"
`mirror.py:232-245, 1139`. A brain with no FMP key answers 503 `FMP_API_KEY not set`; the executor's alert says the decision bar is not published yet. Fix: read the 503 body.

### R7 — MINOR. The dividend merge trusts FMP and dedupes within 4 days
`shadow_runner.py:92, 1079-1084`; `mirror.py:1342`

- A dividend that never happened is applied with no check (CR(SHY,1) 0.000% to +0.306%).
- A date 7 days off Yahoo's is applied twice (0.30%).
- A special 4 days after a booked regular is dropped from the history and the payload.
- If Yahoo later books an FMP-only dividend under a date 1–4 days off, the executor sees a second key and a second receivable.
- None occurs in the real lists: 302 on both feeds, 10 FMP-only, 0 Yahoo-only, no pair within 4 days in two years.
- Fix: apply FMP-only dividends only within about 30 days of today, and name each one applied.

### R8 — NOTE. "Same instant, same answer" holds only up to the 15% lag allowance
`mirror_brain.py:86, 554-566`. UVXY's bar published at T+40 s: a build at T+26 s prices it from the earlier bar, a rebuild after a restart from the bar at T; both are complete, with no `problems` line. Targets did not move: withholding one decision ticker's last bar changed a target in 0 of 552 builds over 13 sessions.

### R9 — NOTE. The decision-minute miss rate is unsettled out of sample
- Real pinned builds equal Composer on 44 of 48 engine-sessions. All four misses are KMLM and HARV on 11-02 and 11-06, both after the calibration window: 4 of 24 since, against 0 of 272 inside it.
- 11-02 cost −2 bp of HARV. 11-06 cost −160 bp of HARV and −71 bp of KMLM, about −45 bp of the book.
- The rollout starts live with HARV, the most minute-sensitive engine.

### R10 — NOTE. `divergence.py`'s held-through test is not what Composer does
It tests continuity from ex to pay; Composer credited HG on 11-05 after HG sold BIL on the ex-date and re-bought it (section 3). The executor has it right; the divergence model would label that event leaked.

## 3. Parity accounting

**The "composer" dividend rule matches Composer.**
- FMP's pay date equals the day Composer was observed to credit on 8 of 8 events (ZVOL, PULS, BIL ×2, TQQQ, SSO, LABD, TMV). All 311 FMP dividends of the last 12 months carry a pay date.
- Four BIL distributions, HG the only holder, read from Composer's own fills:

| ex / pay | held before ex | held before pay | cash appearing in HG on pay date |
|---|---|---|---|
| 08-03 / 08-06 | yes | no | $0 |
| 09-01 / 09-04 | yes | yes | $227 = 813 sh × $0.2798 |
| 10-01 / 10-06 | no | no | −$2 |
| 11-02 / 11-05 | yes | yes, after selling on ex and re-buying | $292 = 947 sh × $0.3085 |

- The last row separates "held on the pay date" from "held continuously"; Composer uses the first, with the ex-date entitlement as the amount. That is what `settle_receivable` does. One discriminating case.
- Unverified: how Composer splits a payer held by two symphonies.

**Dividend gap re-estimated** (hindcast, $118k): credited to sleeves $2,723 a year (2.3%), left unallocated in the account $4,167 (3.5%).

| sleeve | credited | unallocated |
|---|---|---|
| HG | $640 | $564 |
| KMLM | $1,111 | $1,960 |
| SLEEVE | $93 | $49 |
| HARV | $879 | $1,595 |

With equal holdings the sleeve-level gap against Composer is about zero. The unallocated part sits idle on both brokers until swept by hand. Rule "holder" would credit $7,056 and out-earn Composer's symphonies by the leaked part.

**Corridor:** exact (M1 above). A threshold sleeve with more than 5% cash trades, a deliberate departure for a state Composer never reaches.

**Limit buys at quote × 1.005, reserve 0.1%:**
- On 198 real Composer buys, the next minute closes above the limit on 4 (2.0%); it opens and closes above on 0; it stays above to 15:59 on 0. Expect about 2% of buys to fill late and essentially none to go unfilled.
- Idle cash after trading averages 0.43–0.59% of a sleeve (max 1.3%), the same as round 1: the smaller reserve offsets sizing at the limit.

## 4. Contract conformance

- 15 real pinned payloads and the brain's own session answer through `_read_session`, `_validate` and a paper book: the untouched replays are refused for one reason only (`replay`). With `replay` and `built_utc` set as a live day would have them, all 15 sessions trade.
- The book is sound after 15 sessions; holdings are within 3% of Composer's on 44 of 48 engine-sessions. The misses are 10-29 KMLM (Composer's own odd day), 11-02 HARV, and 11-06 KMLM and HARV.
- No field is written one way and read another. `sync`, `problems`, `label` and `price_times` are recorded by the executor but never acted on (R3, R4).

## 5. Structural drag as the design now stands ($118k, per year, estimates)

| Source | $ a year | % of book | Change |
|---|---|---|---|
| Distribution gap against Composer's symphonies | about 0 | 0 | was 2,176 |
| Distributions left unallocated (both brokers) | 4,167 | 3.5 | idle until swept |
| IBKR commissions | 1,788 tiered; 2,734 fixed; up to about 3,400 with pass-through fees | 1.5–2.9 | unchanged |
| Idle cash, whole shares, dust rule | 330 | 0.28 | was 239 on the round-1 run |
| Execution timing against Composer's fills | 0 ± 1,900 | 0 ± 1.6 | orders about 40 s earlier |
| Unfilled limit buys | about 0 | 0 | new |
| Knife-edge days | zero-mean; 11-06 was −45 bp of the book | n/a | see R9 |
| Book mix against Composer's live split | not a drag; mean 9.7 bp a day either way | n/a | unchanged |

- Execution timing now measures +0.5 bp notional-weighted (per session −0.4 ± 0.9 bp); noise is 8.3 bp of traded notional per session.
- The hindcast trades $20.3M a year in 1,041 venue orders. Idle-cash drag scales with engine return, and the hindcast year was strongly positive.

## 6. Checked and found sound

- **Dead-data thresholds are not tuned to pass.** At 15:54 on 13 sessions, book breadth is at least 95.8% (limit 80%) and every engine's share at least 95% (limit 75%). Over all 442 session-minutes 15:25–15:58 the minimums are 85% and 86%, with 0 refusals. Midday (12:45–12:58, the stand-in for a half-day) gives 88% and 85%, 0 refusals. No real half-day is in the data.
- **FMP down for SPY all window:** 503 throughout, then a red NO TRADE at plan-by.
- **Cost of the shared S1 change:** +96 GETs per 15:15 preview run, +124 for the brain. A hanging FMP slows one fetch by about 20 s before the breaker opens. No key means unchanged behaviour.
- **Dividend and split lists:** amounts are as paid (SQQQ 0.2427 before its 1:5, restated 1.2135 for the history); future-dated events do nothing; the window is ex-date within 10 calendar days.
- **Real pinned builds** take 7–13 s cold.
- **Edge:** none surfaced.

## 7. Not modeled

- FMP's publication timing and rate limits at 15:54 and at the T−10 warm burst were not observed live; the market was closed.
- No half-day data.
- The drag and dividend numbers are a hindcast of today's trees on closes, not a forecast.
- IBKR's behaviour (same-minute proceeds, limit fills, dividend posting time) is not exercised.
- Commission schedules are from memory.
- No tracked file was changed and no credential was printed.

## Files

All under `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/B2/`:
- `exhibit2.html`, `exhibit2.png`
- `test_round2_ported.py` (12 pass; run with `venv-ibkr/bin/python -m pytest -q -p no:cacheprovider`)
- `pinned_record.py`, `pinned_giveup.py`, `thresholds.py`, `http_roundtrip.py`
- `attest_attacks.py`, `executor_loudness.py`, `history_fmp_blip.py`
- `s1_attacks.py`, `s1_record.py`, `s7_real_replay.py`
- `composer_div_rule.py`, `drag2.py`, `corridor_limits.py`, `e2e_paper.py`
- `h.py` (helpers), `out/*.txt` (every script's output), `cache/` (inputs)