# Mirror executor, round 3 (2026-11-10 evening): review, fixes, re-checks

Scope: ibkr-executor/app/mirror.py and the mirror parts of ib_adapter.py, config.py,
service.py, render.yaml. Every reviewer and checker below was an agent that did not
write the code it read. Everything ran on the FakeIB and Venue doubles; nothing here
has run against the real IBKR gateway.

| Step | Commit read | Verdict | Findings |
|---|---|---|---|
| Review A (round 3, replacement; the first died in a restart with no verdict) | def94b6d | FIX-THEN-SHIP | D-01 double sell after disk failure + restart (short); C-01 resolve commission unbounded; D-04 credits uncapped; minors D-03, C-02, C-52, C-10, D-05 |
| Fixes 1 | 0b1e11b0 | author gates 460 pass | 37 new gates (tests/test_mirror_round3.py) |
| Check V3a (order paths) | 0b1e11b0 | FIX-THEN-SHIP | second flatten over a resting sell goes short; "new" flatten order booked not sent before asking the venue; kill latency doubled (200 s for 5 symbols); stuck flatten sell silent |
| Check V3b (caps, tools, state) | 0b1e11b0 | FIX-THEN-SHIP | /mirror/adjust cash uncapped; staged-rollout credit loophole; seeds vs a lower max book; dividend receivable outside the cap; blank dollar env stops the service. State files from 709bf175 load and trade |
| Fixes 2 | c4ea2434 | author gates 520 pass | 26 new gates (tests/test_mirror_round3b.py); read-only IBAdapter.open_sell_qty added |
| Check V4a (order paths) | c4ea2434 | normal day CLEAN; kill path clean to ship at $10k | MINOR: fill between the cap's two reads; account_flat True with shares left. Normal day byte-identical to before the fixes; kill 100 s for 5 symbols |
| Check V4b (caps, tools, state) | c4ea2434 | FIX-THEN-SHIP | add-shares then remove-for-cash beats the cap (operator, two steps); 10% dividend ceiling would refuse a real year-end payout (KMLM 2022-12: ~13% by the issuer's report, ~8% by two data sites) |
| Fixes 3 | d867cc58 | 520 pass | adjust cash never netted; ceiling 25%; open sells read before positions; account_flat None when shares are left |
| Check V5 | d867cc58 | FIX-THEN-SHIP | shares bought by hand and adjusted in join the book uncapped |
| Fix 4 | 41f6250a | 521 pass | added shares count at the last mark, less cash taken out of the sleeve; no mark needs force |
| Check V6 | 41f6250a | CLEAN | see open items |

## Open, accepted for the $10k start

- A FORCED adjust with an absurd share count (1e307) overflows funded_usd and reopens the cap (V6, MINOR). Fix: refuse a non-finite total even with force.
- A stale mark under-counts shares added by hand (V6, NOTE); sub-cent adjusts are not counted.
- Kill latency: ~20 s per symbol on this gateway (the adapter's own pre-placement lookup); a kill after ~15:57 ET may not finish before the close.
- The buys gate (book cash vs the account's cash, $1 tolerance) can hold a session's buys once the book is most of the account (cash lag, or an unreported commission above $1). Cannot fire at $10k inside ~$118k of idle cash. Settle before scaling up.
- The 25% dividend ceiling lets a x10 slip on a dividend below 2.5% of the position through.
- Position cache lagging order status inside a second flatten (V5, not reproducible on the doubles).
- Not fixed by instruction: C-25, N-05, N-06, N-07, C-36, C-24; blank MIRROR_WEIGHTS turns the mirror off (red alert).
- Not checked by anyone: the real gateway, API-thread vs loop-thread concurrency, blend re-enabled next to a mirror book.

Repros and checker tests: scratchpad mirror_review/{A3b,V3a,V3b,V4a,V4b,V5,V6} (session-local, not in the repo).
