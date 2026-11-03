# Forward-ledger snapshots (SPEC v1 §6.4, §10 R1)

The monthly upkeep downloads `GET /dollar-watch/ledger` from the live service and commits it here as
`dollar_ledger_YYYY-MM-DD.json`. Snapshots are never edited. A later snapshot that lacks a row an earlier
one had means the ledger was reset or lost; the upkeep stops and reports it.
