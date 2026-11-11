# Transfer-only credential (2026-11-11): build, reviews, re-checks

Scope: POST /mirror/transfer also accepts X-Transfer-Token (MIRROR_TRANSFER_TOKEN) on
ibkr-executor; composer/scripts/mirror_transfer.py; transfer-adjusted returns in
mirror_parity.py; no-redirect openers in mirror_parity / mirror_attest. Every reviewer was
an agent that did not write the code it read. Nothing ran against the real gateway.

| Step | Commit | Verdict | Findings |
|---|---|---|---|
| Build | c740d160 | author: 564 + 536 pass | |
| Review T1 | c740d160 | FIX-THEN-SHIP | no privilege escape; cap per date not per session (78% into one plan over a weekend); 1-cent transfers force trades, unbounded count; parity false RETURN GAP on transfer days; script: no double-send guard, 5xx called "not queued", token followed redirects |
| Fixes 1 | 6b7d4683 | 573 + 551 pass | $1 minimum, 6 per period, period renews only after a session; generic refusals; ledger of sends; no redirects; parity transfer-adjusted |
| Re-check T2 | 6b7d4683 | FIX-THEN-SHIP | allowance renews while token transfers are unapplied (skip, in-tick, remainder: 50% in one plan); script double-sends on an immediate re-run; 200 leaks cap; alert bound hides a real fault |
| Fixes 2 | 7d6a2c23 | 583 + 558 pass | no renewal while a token transfer is open; remainder keeps its mark; ledger guard; 200 stripped; unavailable refusals always alerted |
| Check T3 | 7d6a2c23 | FIX-THEN-SHIP (minor only) | under a real loop thread: 100 seeds, worst plan exactly 25% (before the fix 4/4 seeds violated, up to 77.8%). MINOR: missing total file = fresh period; script logs after the POST |
| Fixes 3 | 7785cceb | 591 + 568 pass | missing total refuses while one waits; strict inbox read; flock + intent row before the POST |
| Check T4 | 7785cceb | CLEAN | 8 real processes racing: one POST; kill -9 after the POST: re-run blocked |

With MIRROR_TRANSFER_TOKEN unset the executor's responses are byte-identical to 095a96e5
(997-row route x auth x body matrix), at every step.

## Open (accepted)

- A corrupt executor inbox blocks the token path with an alert that names the wrong cause
  (T4 D-A1, MINOR; fail-closed; needs a disk fault or a hand edit).
- The script's ledger guard is per ET date: a re-run just after midnight, before the
  executor lists the request, can send again (bounded by the executor's 25% / 6).
- After a partial transfer the next leg for the pair can be refused for up to two sessions.
- A planned transfer makes both sleeves trade to target regardless of the corridor (by design).
- Leaked token, worst case: 25% of the book between sleeves per session, real rebalancing
  trades and commissions; no money in or out; the book total unchanged.
