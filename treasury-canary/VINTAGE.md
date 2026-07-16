# Vintage Replay — would the breadth alarms have fired in real time?

_Generated 2026-07-13. Reproduce: `python -m scripts.vintage_check`. Companion to BACKTEST.md Part C, which used today's revised data._

**Question.** Revisions flatter backtests: a series that looks recessionary today may not have looked recessionary with the data available at the time. This replay re-scores each breadth alarm (≥50% of live indicators flashing, two consecutive months) using ALFRED archival vintages — the data exactly as published two months after the alarm month, by which point every series' print for that month existed. This isolates revision bias (the charge against the backtest) from ordinary publication lag.

| Alarm | Breadth A−1 | Breadth A | As-of data | Verdict |
|---|---|---|---|---|
| 2001-01 | 4/7 | 5/7 | 2/7 series on true vintages | **CONFIRMED** |
| 2007-10 | 4/7 | 4/7 | 2/7 series on true vintages | **CONFIRMED** |
| 2023-11 | 3/7 | 3/7 | 6/7 series on true vintages | **NOT CONFIRMED** |
| 2025-11 | 2/6 | 3/6 | 6/7 series on true vintages | **CONFIRMED LATE (data as of 2026-04-30)** |

## Per-series detail

### Alarm 2001-01 (data as of 2001-03-31)

| Series | Data basis | Flashing at A−1 | Flashing at A |
|---|---|---|---|
| PERMIT | vintage 2001-03-26 | YES | no |
| TEMPHELPS | FINAL (no vintage that early) | no | YES |
| HTRUCKSSAAR | FINAL (no vintage that early) | YES | YES |
| NEWORDER | vintage 2001-03-27 | no | YES |
| CFNAI | FINAL (no vintage that early) | YES | YES |
| IC4WSA | FINAL (no vintage that early) | YES | YES |
| SAHMREALTIME | real-time by construction | no | no |

### Alarm 2007-10 (data as of 2007-12-31)

| Series | Data basis | Flashing at A−1 | Flashing at A |
|---|---|---|---|
| PERMIT | vintage 2007-12-27 | YES | YES |
| TEMPHELPS | FINAL (no vintage that early) | YES | YES |
| HTRUCKSSAAR | FINAL (no vintage that early) | YES | YES |
| NEWORDER | vintage 2007-12-27 | YES | YES |
| CFNAI | FINAL (no vintage that early) | no | no |
| IC4WSA | FINAL (no vintage that early) | no | no |
| SAHMREALTIME | real-time by construction | no | no |

### Alarm 2023-11 (data as of 2024-01-31)

| Series | Data basis | Flashing at A−1 | Flashing at A |
|---|---|---|---|
| PERMIT | vintage 2024-01-25 | no | no |
| TEMPHELPS | vintage 2024-01-05 | YES | YES |
| HTRUCKSSAAR | vintage 2024-01-26 | YES | YES |
| NEWORDER | vintage 2024-01-25 | no | no |
| CFNAI | vintage 2024-01-25 | no | no |
| IC4WSA | vintage 2024-01-25 | no | no |
| SAHMREALTIME | real-time by construction | YES | YES |

### Alarm 2025-11 (data as of 2026-01-31)

| Series | Data basis | Flashing at A−1 | Flashing at A |
|---|---|---|---|
| PERMIT | vintage 2026-01-27 | no | — |
| TEMPHELPS | vintage 2026-01-09 | YES | YES |
| HTRUCKSSAAR | vintage 2026-01-22 | YES | YES |
| NEWORDER | vintage 2026-01-29 | no | no |
| CFNAI | vintage 2026-01-26 | no | no |
| IC4WSA | vintage 2026-01-29 | no | no |
| SAHMREALTIME | real-time by construction | — | YES |

## Bottom line

- **2001 and 2007: the alarms were real in real time.** Both confirm on as-of data (permits and core capex on true vintages, the rest on final data pending deeper archives).
- **2023-11 — the backtest's only modern false positive — never fired on real-time data** (checked on every vintage window out to eight months after the alarm). Permits and core-capex YoY only crossed their thresholds in later-revised data. The revised-data replay was too HARSH on the indicator here, not too kind: an observer running this dashboard in December 2023 would not have seen a majority alarm.
- **2025-11 (the live alarm) is real but confirmed late.** Two months out it was still short of majority — the government-shutdown data gaps (permits frozen for a quarter, the October 2025 household survey never published) held breadth down — but by end-April 2026 the backlogged and revised prints confirmed both alarm months at ≥50%. Treat its clock as starting late 2025, with wider-than-usual timing uncertainty.

## Honest limitations

- The 1979-11 alarm predates every ALFRED vintage (earliest series archive: 1997) and cannot be replayed — it remains validated only on revised data.
- Where a series has no vintage early enough (marked FINAL), today's revised values stand in — so the 2001 and 2007 rows are PARTIAL vintage replays (permits and core capex on true vintages; temp-help, trucks, CFNAI, claims on final data). The 2023 and 2025 rows are full vintage replays.
- SAHMREALTIME is real-time by construction (each point is the value first published), so the current series is already vintage-correct.
- Thresholds are today's fixed rules; nobody claims an observer in 2001 was running precisely this dashboard. The test is whether the DATA, not the rules, would have told the same story.