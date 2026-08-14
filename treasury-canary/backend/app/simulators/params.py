"""Parameter registry for the rate-shock simulator.

Every parameter lives in params.json with {default, range, source, note} —
never hardcoded in engine code (spec §7). Overrides are validated against the
registry and CLIPPED to the plausible range (the UI param drawer and the QA
tornado both drive through here).
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache

_PATH = os.path.join(os.path.dirname(__file__), "params.json")


@lru_cache(maxsize=1)
def registry() -> dict:
    with open(_PATH) as f:
        return json.load(f)


def defaults() -> dict[str, float]:
    return {k: float(v["default"]) for k, v in registry().items()}


def apply_overrides(overrides: dict | None) -> tuple[dict[str, float], list[str]]:
    """Defaults + validated overrides. Unknown keys are reported, not applied;
    values clip to the registry range. Returns (params, warnings)."""
    p = defaults()
    warnings: list[str] = []
    for k, v in (overrides or {}).items():
        if k not in p:
            warnings.append(f"unknown param '{k}' ignored")
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            warnings.append(f"non-numeric override for '{k}' ignored")
            continue
        lo, hi = registry()[k]["range"]
        clipped = min(max(val, float(lo)), float(hi))
        if clipped != val:
            warnings.append(f"'{k}' clipped {val} -> {clipped} (range [{lo}, {hi}])")
        p[k] = clipped
    return p, warnings


def params_hash(p: dict[str, float], extra: dict) -> str:
    blob = json.dumps({"p": p, "x": extra}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
