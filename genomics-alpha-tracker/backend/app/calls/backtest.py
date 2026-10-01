"""Serve the frozen backtest summary to the Calls Log page.

The file is generated offline by scripts/backtest_summary.py from the
replay's own results and committed INTO THIS PACKAGE on purpose: in
production the Render disk mounts over /app/data and hides anything the
image carried there, so a summary written under backend/data/ would be
missing at runtime while present in the repo - the worst kind of absence,
because every local test would pass.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SUMMARY_PATH = Path(__file__).resolve().parent / "backtest_summary.json"


class SummaryMissing(FileNotFoundError):
    pass


@lru_cache(maxsize=1)
def load_summary() -> dict:
    """Read once per process. The file is a build artifact, not state - a
    change to it is a deploy, never a runtime write."""
    if not SUMMARY_PATH.exists():
        raise SummaryMissing(
            f"{SUMMARY_PATH.name} is not present; run "
            "`python -m scripts.backtest_summary` and commit the result")
    return json.loads(SUMMARY_PATH.read_text())
