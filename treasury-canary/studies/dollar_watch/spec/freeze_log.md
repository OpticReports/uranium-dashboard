# Freeze log — append-only

The frozen record is `freeze.json` + `SPEC_v1.md` (sha256 in `freeze.json`). Neither changes. This log
records what happened after the freeze that does not change the design.

| Date | Entry |
|---|---|
| 2026-11-03 | Frozen (commit `fb436499`). |
| 2026-11-03 | Casey answered Q19: **keep the default**. The drift bracket stays as frozen (PASS at −1%/yr, FAIL at +1%/yr). The stronger volatility-regime option is not adopted. No change to the frozen design. |
| 2026-11-03 | Casey asked for the monthly upkeep (R1, SPEC v1 §10) to run as a scheduled task. `fed_emergency_actions_at_freeze.json` keeps the list as frozen (sha256 = `freeze.json` `fed_emergency_actions_sha256`). The shipped list grows append-only from it, and a gate test checks that. |
| 2026-11-03 | The monthly upkeep is scheduled: the 2nd of each month at 19:41 UTC, first run 2026-12-02 (task `trig_01L3x6pH7qPyKTrr5jFYDbSY`, a fresh session each run, push notification on completion). It attaches this repo itself, because the task stores no connectors. Check the first run on 2026-12-02. |
| 2026-11-03 | Readability layer added to the tab: "?" tips on every indicator and plain-language "What this means" bullets per layer. Display only: no rule, threshold, ledger row or scoring changes. |
