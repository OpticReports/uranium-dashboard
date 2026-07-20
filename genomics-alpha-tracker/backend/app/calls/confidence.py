"""Confidence score (0-100) for a trade call — how hard to bet.

The confidence score answers "how much do we believe in THIS trade's edge",
and the paper book sizes positions from it (higher confidence -> bigger
position). It is deliberately EVIDENCE-WEIGHTED so "bet heavy on conviction"
can't degrade into "bet heavy on a made-up number":

  confidence = composite (peer-relative setup quality)
             × edge_multiplier   (from the flag type's graded track record,
                                   shrunk toward neutral when the record is thin)
             × corroboration_multiplier (multiple distinct flags on one name)

With no track record yet (today), edge_multiplier ≈ 1.0, so confidence ≈ the
composite Alpha Signal. As flags accrue outcomes, proven signals bend
confidence up and disproven ones bend it down — the book bets heavier exactly
where the learning loop has confirmed an edge.

Pure functions here; the DB-facing generation helper lives in manager.py.
"""
from __future__ import annotations

from ..config import calls_config


def _cfg() -> dict:
    c = calls_config().get("confidence", {}) or {}
    return {
        "prior_n": float(c.get("edge_prior_n", 12)),
        "gain": float(c.get("edge_gain", 0.8)),
        "cap": float(c.get("edge_cap", 0.25)),
        "corrob_step": float(c.get("corroboration_step", 0.05)),
    }


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def edge_multiplier(hit_rate_1m: float | None, n_1m: int, cfg: dict) -> float:
    """Map a flag's 1-month hit rate (vs XBI) to a size multiplier, with
    Bayesian shrinkage toward 0.5 so a thin record barely moves the bet."""
    if hit_rate_1m is None or n_1m <= 0:
        return 1.0  # no evidence -> neutral: confidence == setup quality
    shrunk = (hit_rate_1m * n_1m + 0.5 * cfg["prior_n"]) / (n_1m + cfg["prior_n"])
    mult = 1.0 + (shrunk - 0.5) * cfg["gain"] * 2.0
    return _clip(mult, 1.0 - cfg["cap"], 1.0 + cfg["cap"])


def corroboration_multiplier(n_distinct_flags: int, cfg: dict) -> float:
    """More distinct flags firing on the same name = higher conviction."""
    extra = max(0, min(n_distinct_flags - 1, 3))
    return 1.0 + extra * cfg["corrob_step"]


def compute_confidence(
    composite: float | None,
    hit_rate_1m: float | None = None,
    n_1m: int = 0,
    n_distinct_flags: int = 1,
    cfg: dict | None = None,
) -> float | None:
    """Blend setup quality with graded evidence and corroboration -> 0-100."""
    if composite is None:
        return None
    cfg = cfg or _cfg()
    conf = composite
    conf *= edge_multiplier(hit_rate_1m, n_1m, cfg)
    conf *= corroboration_multiplier(n_distinct_flags, cfg)
    return _clip(conf, 0.0, 100.0)


def display_confidence(call) -> float | None:
    """Confidence for a call: the value frozen at fire-time, or — for calls
    logged before confidence existed — a stable fallback from the stored
    composite (which is exactly the score with no evidence yet)."""
    if getattr(call, "confidence", None) is not None:
        return call.confidence
    return compute_confidence(getattr(call, "composite_at_call", None))
