# Counter-agent verdict — Duration Squeeze Radar BUILD (2026-08-25)

**VERDICT: FAIL → all 14 findings remediated in the follow-up commit.**
The reviewer confirmed implementation fidelity first (every threshold matches
spec v2; live run reproduces the registration exactly: F1 -30.35%OI @ 9.23th
pctile MET, F2 16.7% NOT_MET; month math verified for all 12 months; QRA/FOMC
dates verified; first-refresh fires nothing; dedup idempotent; pagination
bounds sufficient) — then failed the build on the gates and two house laws.

| # | severity | finding | remediation |
|---|---|---|---|
| 1 | BLOCKER | threshold gates FAKE for 5/7 registered numbers — proven by mutation (F1→0.45, F3→0.99, F2→25, T3→2.2, T5→130 all left 20/20 green) | boundary-straddling fixtures added for F1/F2/F3/T3/T5; mutation attack re-run on ALL SEVEN constants: each now kills exactly the gate that pins it |
| 2 | MAJOR | stale-preferred violated on 200-but-empty responses (finra, cftc UST %OI, fmp MOVE — the last PERSISTED [] over a good disk cache) | empty-parse-with-nonempty-cache now treated as failure everywhere; MOVE never writes [] over data |
| 3 | MAJOR | STALE interlude swallowed real flips (MET→STALE→NOT_MET alerted nothing) | flip baseline is now the last NON-STALE snapshot |
| 4 | MAJOR | T1's first-cut leg unimplemented while the detail text claimed "event-scored" | T1_MANUAL_FIRST_CUT (T4 pattern, by commit, as-of + rationale); detail states plainly the leg is manual; gate covers both states |
| 5 | MAJOR | FOMC table dies silently after 2026-12-09 | exhaustion emits a loud WARNING calendar entry; gated |
| 6 | MINOR | T1 boundary drift (≤ vs spec's strict ">50bp") | strict <; gate pins -50.0→NOT_MET, -50.1→MET |
| 7 | MINOR | T2/T3 silently bridge missing months (basis shift) | >100-day span over 4 prints degrades that leg to STALE; gated |
| 8 | MINOR | fetch_shares_outstanding not stale-preferred | expired cache now beats None |
| 9 | MINOR | fetch_ust_lev_pct_oi docstring contradicted the composition registration; pre-2016 3-contract weeks unlabeled in /squeeze/history | docstring fixed; history payload carries cot_note |
| 10 | MINOR | cond_t1 ignored injected `today` | passed through |
| 11 | MINOR | no hysteresis — boundary oscillation could alert daily | flip alerts debounced to one per (condition, state) per ISO week |
| 12 | MINOR | mangled line in refresh.py | rewritten |
| 13 | MINOR | stray /data cache dir at repo root | gitignored |
| 14 | MINOR | T5 with <91d OAS history scored NOT_MET (a verdict from an unverifiable leg) | STALE |

Post-remediation: 29 gates green; mutation attack on all 7 registered
constants kills a test each; full canary suite 256 passed (2 pre-existing
env failures unrelated: openpyxl absent locally, stat_regime hmmlearn);
tsc + vite build clean; live assemble_radar() reproduces the registration.
