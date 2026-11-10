"""Keyless data lanes. Every lane degrades gracefully: on failure it logs a
warning and returns empty/None — the engine keeps running with that lane dark
and says so on every affected row."""
