"""Asymmetry score: "how asymmetric is buying optionality here, right now?"

Formula (pinned by tests/test_scoring.py — change both together):

    score = clamp( SCALE * impact_weight
                         * exp(-ln2 * days_to_event / 21)      # time decay
                         * quiet_factor                        # tape quiet?
                         * cheapness_factor,                   # vol cheap?
                   0, 100 )

    quiet_factor     = clamp(1.25 - |drift_z10| / 2, 0.25, 1.25)
    cheapness_factor = clamp(2 - iv_ratio / 2,       0.5,  1.5)
    SCALE            = 96

Semantics:
  * exp(-ln2 * d/21): event proximity with a 21-day half-life — a catalyst
    42 days out is worth a quarter of one tomorrow.
  * quiet_factor: rewards a tape that has NOT already moved (drift_z10 ~ 0).
    A |z|=2 pre-move (news likely leaking / already out) cuts the factor to
    0.25 — the asymmetry is gone.
  * cheapness_factor: rewards option markets that have NOT priced the event.
    iv_ratio 1.0 (IV = realized) -> 1.5 rich reward; iv_ratio 3.0 -> 0.5.
  * missing inputs are NEUTRAL, never fabricated: iv_ratio None -> factor 1.0
    + "IV unknown" flag; drift None -> factor 1.0 + "drift unknown" flag.
  * anchor (test-pinned): impact 1.0, 21 days out, drift 0, iv_ratio 2.0
    -> 96 * 1.0 * 0.5 * 1.25 * 1.0 = 60.0.
  * days_to_event None (no dated event in horizon) -> no score (None);
    watch-only names surface via the watch flag, not a number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

SCALE = 96.0
HALF_LIFE_DAYS = 21.0
_LN2 = math.log(2.0)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class ScoreResult:
    score: float | None
    flags: list[str] = field(default_factory=list)
    quiet_factor: float | None = None
    cheapness_factor: float | None = None
    time_factor: float | None = None


def asymmetry_score(impact_weight: float | None, days_to_event: int | None,
                    drift_z10: float | None, iv_ratio: float | None,
                    half_life_days: float = HALF_LIFE_DAYS) -> ScoreResult:
    """Score in [0, 100]; None when there is no dated event to score."""
    if days_to_event is None or impact_weight is None:
        return ScoreResult(score=None, flags=["no dated event in horizon"])
    if days_to_event < 0:
        return ScoreResult(score=None, flags=["event in the past"])

    flags: list[str] = []
    time_factor = math.exp(-_LN2 * days_to_event / half_life_days)

    if drift_z10 is None:
        quiet = 1.0
        flags.append("drift unknown")
    else:
        quiet = _clamp(1.25 - abs(drift_z10) / 2.0, 0.25, 1.25)

    if iv_ratio is None:
        cheap = 1.0
        flags.append("IV unknown")
    else:
        cheap = _clamp(2.0 - iv_ratio / 2.0, 0.5, 1.5)

    raw = impact_weight * time_factor * quiet * cheap
    return ScoreResult(score=_clamp(SCALE * raw, 0.0, 100.0), flags=flags,
                       quiet_factor=quiet, cheapness_factor=cheap,
                       time_factor=time_factor)
