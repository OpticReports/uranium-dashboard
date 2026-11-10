# IBKR mirror — reviewer B (parity, data, timing)

**PAPER: FIX-THEN-SHIP.** No money is at risk, but as built the paper record cannot measure parity: fix B1, B2, B3, S1 and S2 first.
**LIVE: SHIP-BLOCKED.** B1–B4 must be fixed; S1–S4 fixed or explicitly accepted; S5 and S6 are owner decisions.

`report.md` was not written: the harness refuses report files from a subagent. This message is the report; save it to `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/B/report.md` if you want the file.

Reviewed commit eca49668 (`mirror_brain.py`, `preclose.py`, `shadow_runner.py`, `mirror_core.py`, `mirror.py`; all byte-identical to that commit at review time). Baseline: 123 composer tests and 70 executor tests pass.

Evidence used, all read-only:
- Composer's own trade-activity report, 2026-07-10..11-09: 81 sessions, 447 fills, with submit and fill times to the second.
- The committed minute calibration (`composer/results/shadow-minutes-2026-11-01.json`, 69 sessions) plus the same check run on the 6 sessions since.
- The shadow and pre-close ledgers, Yahoo daily bars, FMP 1-minute bars, FMP's dividend list and NYSE's calendar page.
- A 252-session hindcast on the executor's own `mirror_core`.

Repro tests in `test_repro_B.py` assert the behaviour parity needs; 11 of 11 fail on eca49668.

## BLOCKING

### B1 — The brain decides after Composer has traded, on a different bar than calibrated, and not reproducibly
`composer/scripts/mirror_brain.py:142-144`, `preclose.py:595, 669`, `ibkr-executor/app/mirror.py:120, 639`

- **Off by one bar.** The calibration's label "15:54" is the bar *ending* 15:54:00 (`shadow_runner.minute_price`). `session_info` reads 15:54 as a bar *start* and sets `decide_utc` to 15:55:00.
- **Composer is already done.** Composer's first order submit per session: min 15:50:54, p10 15:51:34, median 15:53:04, p90 15:53:51, max 15:55:49. By minute: 15:50 ×2, 15:51 ×10, 15:52 ×28, 15:53 ×37, 15:54 ×3, 15:55 ×1. The mirror's first possible decision (15:55:05) comes after every Composer fill on 80 of 81 sessions, by a median 121 s (max 251 s).
- **The minute changes the answer.** Engine-sessions where the logic on that minute's prices contradicts Composer's real holdings, of 296:

| price at | 15:51 | 15:52 | 15:53 | 15:54 | 15:55 | 15:56 | close |
|---|---|---|---|---|---|---|---|
| contradictions | 5 | 7 | 10 | 5 | 11 | 13 | 22 |

- The live mirror reads 15:55:05 or later, so it sits at 11–13 (3.7–4.4%, about 37–44 engine-days a year) against 5 (1.7%) at the calibrated minute.
- **The calibration is not settled.** In-sample (272): 1 / 9 / 13 at 15:54 / 15:55 / 15:56. The 24 engine-sessions since: 4 / 2 / 0. No fixed minute reproduces Composer; its submit second moves by up to five minutes between days.
- **How often the minute matters:** 22 of 272 engine-sessions (8.1%); at least one engine on 16 of 69 sessions (23%). In my seven replays (10-30, 11-02..11-09, at 15:50–15:57) targets changed across minutes on 3 sessions, for KMLM and HARV only; never for HG or SLEEVE.
- **Not the bar the docstring claims.** FMP publishes a bar 10–25 s after it ends. Pre-close ledger: at 15:16:08 on 11-04 and 15:16:17 on 11-05 SPY's just-ended bar was missing; on 11-09 at 15:16:15, 23 of 48 tickers were on Yahoo. At decide + 5 s, liquid tickers take Yahoo's last sale and thin ones an older FMP bar (up to 15 minutes old, unflagged).
- **Two valid answers for one session.** `SAME_MOMENT = 60` sits exactly on `decide_utc`: a build starting 15:55:01 reads FMP's bar ending 15:54:00, one starting 15:55:05 reads Yahoo. On real 11-06 bars, HARV is PULS 100% vs PULS 64 / ZVOL 36 and KMLM is TECL 75 / PULS 25 vs TECL 75 / PULS 16 / ZVOL 9. `_validate` accepts both, and neither payload says which bar it read.
- **The replay evidence covers a different minute.** The commit's "`--at 15:54` reproduces Composer on 11-09" reads the 15:53 bar; the live path never does.

Repro:
- `test_B1_…` → `decide_utc 2026-11-09T20:55:00Z is the end of the NEXT bar; the calibrated instant is 2026-11-09T20:54:00Z`.
- `test_B1b_…` → the two 11-06 answers above.
- Scripts: `decision_time.py`, `minute_profile.py`, `composer_fills2.py`, `replay.py`.

Smallest fix:
1. Set `decide_utc` to close − 6 min exactly (drop the `+ 1 minute`).
2. For a request with `after`, build pinned to that instant (`now` = `horizon` = `decide_utc`, as the replay path already does), so live equals `--at`.
3. Raise `decide_offset_s` to about 25 s and have the brain answer 503 until SPY's bar ending at the instant is present.
4. Publish `decision_bar_end_utc` and each price's time and source; `_validate` rejects a payload whose SPY price time is not that bar.
5. Expect 2–4% of engine-days to differ whatever minute is chosen; the parity monitor should classify them using Composer's own submit time.

### B2 — Distributions never reach the sleeves
`ibkr-executor/app/mirror.py:363` (manual `request_credit` is the only path); `mirror_core.py` has no dividend concept

- ZVOL pays $0.485 a month on a $7.02 price (6.9% a month, 83% a year). PULS, BIL, TLT, SQQQ and TECL pay 3–8% a year.
- On the $118k book (hindcast), $6,575 a year (5.6%) lands in the account outside every sleeve:

| sleeve | $ a year | % of the sleeve |
|---|---|---|
| KMLM | 3,045 | 8.9% |
| HARV | 2,409 | 13.6% |
| HG | 980 | 2.9% |
| SLEEVE | 141 | 0.4% |

- Composer credits $2,176 of that inside its symphonies, where the payer is still held on the pay date (lags from add. 38). That is the sleeve-level return gap: 1.8% of the book a year (HARV 4.9%, KMLM 2.4%, HG 1.2%, SLEEVE 0.3%). The other $4,398 leaks to account cash on Composer too.
- HARV's hindcast price return is +1.1% against +15.9% with distributions: nearly all of its return is the part the sleeve never sees.
- The manual route means about 60 ex-dates a year across 16 payers, each split by shares held at the prior close (KMLM and HARV hold PULS and ZVOL together). The paper adapter has no dividends at all.

Repro: `drag_sim.py`, `div_split.py`.

Smallest fix:
- The brain publishes today's ex-dividends per ticker (it already fetches `events=div`; union with FMP's list, see S1).
- The executor books a receivable per sleeve (shares at the prior close × amount) and converts it to a credit once the account's cash exceeds the book's by that amount (the guard `_apply_credits` already has), alerting if not seen within 7 sessions.
- Paper credits on the pay date.
- Owner decision: credit every dividend to the holding sleeve, or copy Composer's leak rule.

### B3 — Stale, halted or short data is published "ok / firm" and the executor acts on it
`mirror_brain.py:102-107`, `preclose.py:61, 144, 189-195, 731, 819-821`, `mirror.py:628-648, 683-701`

- `_validate` checks the build's wall clock (`asof_utc`), never the age of the prices. `_targets` ignores `label`, `stale`, `caveats` and `quotes`.
- **Stalled feed.** FMP stalled at the 15:38 bar with Yahoo no newer: at 15:55:05 all 48 prices are carried, all four engines are `ok` and `firm`, and the payload is accepted.
- **Unknown early close.** The exchange shut at 13:00 with no Yahoo trading period: all four engines `ok` on three-hour-old prices at 15:55:05, accepted. A live book would send market orders into a closed market.
- **Short history.** Yahoo's history a session short for UVXY and TQQQ: all four engines `ok` with a caveat only.
- **Preview tolerance.** A price up to 15 minutes old is "fresh" with no note (`FRESH_MIN`).
- **Precedent.** Pre-close ledger 2026-10-30 15:33: SPY stamped 14:34, four engines status ok.

Repro: `test_B5_…`, `test_B5b_…`, `test_B5c_…`; `out/explore1.txt`.

Smallest fix, in `mirror_brain.build`:
- An engine is `unavailable` when a decision ticker it reads is carried, rebuilt, older than about 2 minutes at the decision bar, or in `short`.
- All engines are unavailable when SPY's price is not from the decision bar.
- Carry price times in the payload and reject on them in `_validate`.

### B4 — Nothing ties the mirror's tree to Composer's live version at decision time
`mirror_brain.py:71` (`preview(now, lambda: [], None, …)`, so `get_drift=None`), `:88-96`

- The brain trades whatever `fixtures/approved/manifest.json` says in its deployed checkout. Nothing in the mirror path compares it with Composer. The existing checks are the 15:15 preview (report only) and the post-close shadow run at 21:35 UTC.
- After an edit on Composer, Composer trades the new tree at about 15:53 and the mirror trades yesterday's the same day. It keeps doing so until a new era is committed and the brain redeployed.
- Edit rate: 7 versions across the four symphonies since 06-30. Today live equals approved on all four (checked: 8 GETs, 2.4 s).
- **Dropped tickers strand a sleeve.** The brain prices only the current trees' tickers, and `build_plan` skips a sleeve with an unpriced holding (`mirror_core.py:279`). HG's first era held ANGL, BSV, SPAB and VBF, which no current tree prices; a sleeve holding one can never sell it.

Repro: `test_B3_…` → `{'action': 'skip', 'reason': 'no price for ANGL'}`. The gate's absence is by inspection.

Smallest sound gate, keeping the brain keyless:
1. A Composer-keyed job runs `sr.check_drift` at about 15:50 ET and posts an attestation to the brain: session, plus each engine's head version and the sha1 of its canonical live tree.
2. `build()` marks an engine `unavailable`, naming both versions, unless today's attestation exists and its hash equals the approved tree in use.
3. Effect: an unsynced edit makes that sleeve hold, loudly, instead of trading the old tree. With Composer's API down it also holds, which on 10-26..28 is what Composer did.
4. For dropped tickers: price the union of each engine's last two eras, or let the executor fall back to the venue quote for held symbols missing from the payload.

## SERIOUS

### S1 — Yahoo's adjusted history, the brain's only history, is missing dividends right now
`shadow_runner.py:888-909` (`apply_events` repairs only events Yahoo lists), `preclose.py:535-551`

- FMP lists 221 dividends on the trees' 48 tickers over 12 months; Yahoo has not booked 7. All seven went ex on 2026-11-02 and were still missing six sessions later: BIL, CORP, HYG, IEF, LQD, SHY, TLT. Six are decision tickers.
- Indicators are wrong today: CR(SHY,1) on 11-02 reads −0.29 (true +0.02); CR(TLT,1) −0.13 (true +0.29); RSI(IEF,8) on 11-09 reads 65.0 (true 69.9); RSI(CORP,15) 59.6 (true 65.9).
- No target changed on 11-02..11-09 (0 of 24). The same omission replayed on the 11 earlier shared ex-dates changes SLEEVE's target on 20 of 66 sessions (10 of 11 ex-dates) and KMLM's on 4 of 66.
- This also affects the shadow runner and the 15:15 preview.

Repro: `div_check.py`, `div_impact.py`.
Fix: merge FMP's dividend list into `events` before `apply_events`, which already applies only what the series lacks; one cached call per ticker per day.

### S2 — Splits: the book keeps the old share count
`mirror_core.py` (no split handling), `mirror.py:609-617`

- Nine split events on holdable tickers in 12 months: QLD, SSO, TQQQ, UDOW, USD 2:1 and SQQQ, UVXY 1:5 on 2025-11-20; SOXS 1:20 on 2026-03-05 and 1:10 on 2026-07-15.
- Live: the exact position check fails, so no sleeve trades until the state file is edited by hand. There is no route to adjust shares.
- Paper: silent. `test_B3b_…` → `sleeve equity 33,515 -> 133,515 across a 1:5 reverse split; the plan: trade {'PULS': 502, 'SQQQ': -504} (the account holds 500 SQQQ)`.

Fix: the brain publishes today's split ratios (already in `events`); the executor rescales sleeve shares before the pre-trade check and credits cash in lieu.

### S3 — A slow feed becomes a missed session
`mirror_brain.py:66, 167-189, 268-277`, `preclose.py:84, 606`, `mirror.py:61-63`

- `Cache.refresh` takes the flight lock and builds again without re-checking freshness. `test_B5e_…` → `2 builds for two overlapping requests; the second waited 1.5 build-times`. Once a build takes more than about 12 s, every 25 s read times out and every retry queues another build.
- `asof_utc` is stamped at build start. `FMP_BUDGET` is 90 s and `INTENTS_MAX_AGE_S` is 90 s, so one hanging ticker makes every payload too old on arrival. The window is 175 s (15:55:05 to 15:58:00).
- Measured build: 6.6–8.0 s off-hours, with 48 Yahoo and 58 FMP calls. In the 45-minute window that is about 100 builds: roughly 5,800 FMP and 4,800 Yahoo calls a session for one payload used.
- No repro of how often FMP is slow at 15:55; build time is not logged.

Fix:
- Re-check `fresh()` after acquiring the flight lock.
- Give the mirror its own FMP budget of at most 10 s (the Yahoo fallback exists).
- Cache the 2-year history per session and start refreshing a few minutes before the decision.

### S4 — The executor's clock is a static table
`shadow_runner.py:89-96`, `mirror_brain.py:129-145`, `mirror.py:512-528`

- The tables are correct through 2027-12-31 (checked against NYSE's page today). They break on 2028-01-17 (holiday), 2028-07-03 and 2028-11-24 (13:00 closes). `test_B6_…` → the holiday reads as a session and the half-day as closing 16:00, with `decide_utc` three hours after the real close. The session payload gives no warning.
- A holiday the table lacks: the brain sees no trades and publishes nothing. Safe.
- An early close the table lacks, Yahoo reporting the period: the brain refuses at 15:55, the session is missed, and Composer rebalanced at about 12:53.
- The same without Yahoo's period: B3's case, orders into a closed market, cancelled at 15:59 by the static clock. What IBKR does with a DAY market order sent after the close was not verified.
- The executor never checks the venue's own hours.

Fix: `session_info` returns `session: None` with a reason when the year is past the table. The executor compares `close_utc` with IBKR's liquid hours for SPY before planning.

### S5 — The book mix is not Composer's (owner decision)
`ibkr-executor/app/config.py:107`, `mirror.py:1266-1267`

- The mirror seeds 29/29/27/15. Composer on 11-09 was 34.3 / 26.8 / 26.5 / 12.4 ($308k).
- Engine-level parity is unaffected. Book-level return differs by a mean 9.7 bp a day (p95 32, max 94) and +5.5% for Composer's mix over the hindcast year.
- POLICY operations 3 and 5 move capital on Composer; `/mirror/transfer` exists but nothing triggers it in the same change set.

### S6 — Commissions are a structural drag of 1.5–2.8% a year
- The hindcast trades $20.0M a year (170× the book) in 1,016 venue orders and 486k shares.
- Tiered commission alone $1,751; fixed $2,672; tiered plus exchange, clearing and TAF pass-through $3,348. A further ~$207 applies if the $20.60/M SEC fee is in force.
- This is an estimate from IBKR's published schedules as I recall them. Composer charges none. It cannot be fixed, only chosen (tiered) and accepted. The dust rule skips 134 trims.

### S7 — `mirror_brain.py --at` is not a valid replay of a past session
`preclose.py:659-673` (`adj[today] = raw[today] = q[0]`)

- A replay puts the day's raw FMP price on Yahoo's history as adjusted today, so every dividend paid since shows up as a phantom return on the replayed day.
- 2026-08-28 and 08-31: 5 of 8 engine decisions are wrong. On 08-28 KMLM, SLEEVE and HARV all differ (for example SLEEVE BOXX 100% instead of BOXX 50 / LABD 25 / TMV 25). With the history as it stood that day, all 8 match Composer's holdings.
- Live runs are unaffected. 09-25..09-30 and the seven recent sessions replay identically either way.

Repro: `replay_artifact.py`.
Fix: scale the minute price onto the adjusted series for the replayed day, as `shadow_runner.at_minutes` does; add a gate test replaying 08-28 against the ledger.

## MINOR

- **M1 — Corridor read on equity including cash** (`mirror_core.py:163-174, 231-235`).
  - Held weights are divided by equity with cash (mean 0.5% of the sleeve, max 1.4%), so the gap is biased by ± cash share × weight, both ways.
  - `test_B2_…` → `(1) Composer's measure 0.1010 -> trade; mirror gap 0.0980 -> hold. (2) Composer's measure 0.0990 -> hold; mirror gap 0.1010 -> trade`.
  - On the record it never mattered: 0 of 71 KMLM sessions within ±0.5pp of the trigger, 2 within ±1pp.
  - Fix: divide by holdings value.
- **M2 — KMLM starts off Composer's path** (`mirror_core.py:235, 301`).
  - A sleeve seeded from cash buys the target while Composer sits inside its corridor.
  - On 7 of 36 start days (19%) holdings differ by 6–10.5% of the sleeve for 2–4 sessions; after the first common trip, 0 of 672 simulated sessions differ.
  - A transfer forces a threshold sleeve to target; how Composer treats that is unverified.
  - Fix: start KMLM on a session Composer's KMLM trades.
- **M3 — The 0.3% buy cushion is thinner than one minute of a 3x fund.**
  - On 12 of 208 Composer buy-days (5.8%) the price a minute after the reference was more than 0.3% higher (LABD +107 bp, SOXL +76 bp), so that sleeve's cash goes negative by the excess.
  - The 1.5% band was exceeded in a minute on 1 of 447.

## NOTE

- **N1.** Composer no-rebalance days (12 of 308, all 10-26..28): the mirror would trade and Composer did not. The B4 attestation could carry `is_paused`.
- **N2.** 2026-10-29, Composer's first day back: KMLM landed 5.3pp off target on SOXL and PULS. Unexplained. On the other 45 clear trip days Composer went to the whole target within 1.5%.
- **N3.** No half-day is in the record; 2026-11-27 is the mirror's first. Winter time is confirmed by Composer's fills on 11-02..11-09 (15:51–15:54 ET).
- **N4.** `/health` is public; `mirror_brain_url`'s scheme is not checked before the token header is sent. Token compare is constant-time and unset returns 404.
- **N5.** Yahoo is the only source of history; an outage at 15:55 means no trade while Composer trades.
- **N6.** `mirror_dry.py` was still being edited at the end of the review (uncommitted, modified 04:50 UTC), so it was not reviewed. It uses its own as-of history, so S7 does not apply to it directly.

## Structural drag on $118k (HG 29 / KMLM 29 / SLEEVE 27 / HARV 15), per year, estimates

| Source | $ a year | % of book | Fix before live |
|---|---|---|---|
| Distributions outside the sleeves (all) | 6,575 | 5.6 | yes (B2) |
| — of which Composer credits inside its symphonies | 2,176 | 1.8 | yes (B2) |
| IBKR commissions and fees | 1,751–3,348 | 1.5–2.8 | cannot; accept (S6) |
| 0.3% reserve | 92 | 0.08 | no |
| Whole-share residue | 81 | 0.07 | no |
| Dust rule | 66 | 0.06 | no |
| Decision-to-fill gap vs Composer's real fills | 0 ± 2,400 | 0 ± 2.0 | no |
| Book mix vs Composer's live split | not a drag | mean 9.7 bp a day either way | owner (S5) |

- The three cash rows scale with engine return, and the hindcast year was strongly positive, so they are high-side. Mean cash is 0.37–0.52% of a sleeve.
- Decision-to-fill: the mirror at about 15:55:30 against Composer's actual fills is −0.9 bp ± 1.2 of traded notional (409 fills, 79 sessions). Noise is 10.9 bp of traded notional per session, about 7 bp of the book a day. The ±$2,400 is one standard error times 170× turnover.
- Spread is paid on both brokers and is not a parity term.

## Checked and found sound

- **Corridor rule.** Same measure as the verified model (largest single-asset gap, union of keys, entering and leaving assets, strict `>`). On the real record the gap is never between 9.01pp and 12.94pp, so reserve bias and tie-breaking have had no effect. The mirror rebalances every leg on a trip.
- **Dust rule.** Entries and exits are never suppressed (`have > 0 and w > 0` only). Largest single-asset weight error after trading is 0.47pp (mean 0.05pp), with 134 skipped trims in 252 sessions.
- **`prices` are raw for today in a live run.**
  - FMP bars are unadjusted and Yahoo's latest bar has factor 1 (checked on PULS's 10-30 ex-date).
  - Rebuilt and carried prices are flagged; live widens the band to 5% and sizes on the venue quote.
  - The 1.5% band blocks a grossly wrong price live; paper fills at whatever the brain says.
- **`after` handling.**
  - A payload stamped before `decide_utc` is never served (503).
  - A failed rebuild cannot resurrect an older stamp past the 90 s age check.
  - Replays are refused, clock skew over 60 s is refused, and a future `after` gets 409.
- **Calendar tables for 2026–2027** match NYSE, including the 11-27 and 12-24 half-days. ET conversion uses zoneinfo on both sides.
- **Execution timing** costs nothing measurable against Composer's fills.
- **Edge:** none surfaced. The −0.9 bp execution difference is inside one standard error.

## Not modeled, and what the numbers rest on

- The drag simulation is a hindcast of today's trees on Yahoo closes, with decisions and fills at the close; it scales costs and is not a forecast.
- The minute tables use FMP bar closes; Composer's price feed and exact decision instant are unknown. The 24 post-calibration engine-sessions are a small sample.
- The dividend split uses pay lags observed for 7 funds and ex+4 for the rest.
- Commission schedules are from memory. IBKR's handling of after-close DAY orders is unverified.
- FMP's bar publication lag is read from 8 ledger runs at 15:16, not measured at 15:55.
- Composer's API was read with GET only; derived fill times sit in `cache/composer_fill_times.json` in the scratchpad. No tracked file was changed and no credential was printed.

## Files

All under `/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/mirror_review/B/`:
- `exhibit.html`, `exhibit.png` (three panels: Composer's submit minute against the mirror's decision, contradictions by price minute, drag by source)
- `test_repro_B.py` (run with `venv-ibkr/bin/python -m pytest -q -p no:cacheprovider test_repro_B.py`)
- `decision_time.py`, `minute_profile.py`, `composer_fills2.py`, `replay.py`, `replay_artifact.py`, `exec_gap.py`
- `drag_sim.py`, `div_split.py`, `div_check.py`, `div_impact.py`
- `kmlm_corridor.py`, `kmlm_inception.py`, `explore1.py`
- `out/*.txt` (every script's output), `cache/` (inputs)