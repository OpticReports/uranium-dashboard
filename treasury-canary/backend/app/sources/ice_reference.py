"""Frozen pre-truncation history for the ICE BofA series FRED no longer serves.

FRED's note on every BAML* series reads: "Starting in April 2026, this series
will only include 3 years of observations." Anything that RANKS one of these
against "its history" silently became a 3-year rank on that date. Measured
consequences before this module existed: the pin board's CCC percentile read
99.2 when the true full-history rank was ~62, and the severity index's HY
complacency component read 87.2 against a true 96.1.

This module splices a frozen historical file onto whatever FRED still serves, so
those ranks mean again what they say. It is deliberately at the SOURCE layer:
every consumer (pin board, pin history, severity, cross-asset percentiles) is
fixed at once, and none of them needs to know.

PROVENANCE — see app/data/ice_reference/MANIFEST.md for per-file detail. Each
frozen file was reconstructed from public mirrors and reconciled against FRED's
own authoritative window: zero mismatches at 1e-4 on every overlapping date.
Live FRED values always win on overlap; the frozen file only supplies dates FRED
has dropped, and is never fetched at runtime.

KNOWN GAP: BAMLH0A3HYC (CCC) has no data for 2022-07-07..2023-09-10, 432 days.
It is left as a hole ON PURPOSE — interpolating it would fabricate history in a
series used to rank distress. It contains neither the record extremes nor any
episode peak the anchors cite.
"""
from __future__ import annotations

import csv
import os
from datetime import date
from functools import lru_cache

_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ice_reference")

# Series whose FRED history was truncated in April 2026.
FROZEN_SERIES = {"BAMLH0A3HYC", "BAMLC0A4CBBB", "BAMLH0A0HYM2", "BAMLC0A0CM"}


@lru_cache(maxsize=None)
def frozen_history(series_id: str) -> tuple[tuple[date, ...], tuple[float, ...]]:
    """Frozen pre-truncation observations, oldest first. Empty if none on disk."""
    path = os.path.join(_DIR, f"{series_id}.csv")
    if series_id not in FROZEN_SERIES or not os.path.exists(path):
        return (), ()
    dates: list[date] = []
    vals: list[float] = []
    with open(path, newline="") as fh:
        for row in list(csv.reader(fh))[1:]:
            if len(row) < 2 or row[1] in (".", ""):
                continue
            dates.append(date.fromisoformat(row[0]))
            vals.append(float(row[1]))
    return tuple(dates), tuple(vals)


def splice(series_id: str, dates: list[date], values: list[float | None]
           ) -> tuple[list[date], list[float | None]]:
    """Prepend frozen history to a live series. Live wins on any overlap.

    A no-op for series with no frozen file, so callers can apply it blindly.
    """
    fd, fv = frozen_history(series_id)
    if not fd:
        return dates, values
    live = set(dates)
    out_d = [d for d in fd if d not in live]
    out_v: list[float | None] = [v for d, v in zip(fd, fv) if d not in live]
    out_d.extend(dates)
    out_v.extend(values)
    return out_d, out_v
