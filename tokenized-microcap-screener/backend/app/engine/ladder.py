"""The ladder: which rung a ticker is on, and when that is worth waking Casey.

Rungs, earliest to latest:

  TOKENIZED      a tokenized equity token for this listing exists on-chain.
                 For a nanocap this is itself the signal — nobody wraps a
                 15-employee mushroom exporter by accident. In the Farmmi
                 case the tokenized FAMI pool was seeded at 21:54 UTC on
                 2026-09-01, ~15.5h before the Nasdaq session that moved.
  PAIRED         a meme token has been pooled against it.
  RAMPING        that pool's volume is accelerating.
  CLUSTER        several distinct memes are pooled against the SAME ticker.
  EQUITY_MOVING  the listing itself has broken out on volume. Not a signal —
                 a receipt. Alerts are SUPPRESSED here by design.
  FADED          on-chain heat decayed without the equity ever responding.

The alert fires on entry to RAMPING or CLUSTER while the equity is still
quiet. Everything else is bookkeeping — but the bookkeeping is the point:
StageEvent rows are what will eventually let the lead time be measured rather
than asserted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import STAGES
from .scoring import EquityView

_RANK = {s: i for i, s in enumerate(STAGES)}


@dataclass
class LadderInput:
    meme_count: int
    max_heat: float
    equity: EquityView


def equity_is_moving(eq: EquityView, cfg: dict) -> bool:
    """A move counts only when price AND volume both confirm.

    Price alone is noise on a sub-$1 name — a single tick is several percent —
    so the volume leg is required.
    """
    l = (cfg or {}).get("ladder", {})
    if eq.dark or eq.change_pct is None:
        return False
    if abs(eq.change_pct) < l.get("equity_move_pct", 15.0):
        return False
    if eq.volume and eq.avg_volume:
        return (eq.volume / eq.avg_volume) >= l.get("equity_move_rvol", 3.0)
    return False


def decide_stage(current: str, inp: LadderInput, cfg: dict) -> str:
    l = (cfg or {}).get("ladder", {})

    if equity_is_moving(inp.equity, cfg):
        return "EQUITY_MOVING"

    if inp.meme_count <= 0:
        return "TOKENIZED"

    ramping = inp.max_heat >= l.get("ramping_heat", 45.0)
    if ramping and inp.meme_count >= l.get("cluster_min_memes", 3):
        return "CLUSTER"
    if ramping:
        return "RAMPING"

    # Cooled off after having been hot, and the equity never responded.
    if (_RANK.get(current, 0) >= _RANK["RAMPING"]
            and current != "FADED"
            and inp.max_heat <= l.get("faded_heat", 20.0)):
        return "FADED"
    if current in ("RAMPING", "CLUSTER"):
        return current            # hysteresis: don't flap on one cool reading
    return "PAIRED"


def is_upgrade(previous: str | None, new: str) -> bool:
    if previous is None:
        return True
    if new == "FADED":
        return previous != "FADED"
    return _RANK.get(new, -1) > _RANK.get(previous, -1)


def should_alert(new_stage: str, previous_stage: str | None, score: float,
                 eq: EquityView, cfg: dict,
                 pumpability: float = 0.0) -> tuple[bool, str]:
    """Fire on a fresh climb onto an alerting rung while the stock is quiet.

    TOKENIZED is an alerting rung, and on the evidence the most valuable one:
    in the Farmmi case the wrapper was seeded 15.8h before the tape moved,
    while the meme cascade rungs were coincident (+13 min) or outright lagging
    (-1.9h). It only alerts for a genuine nanocap — a wrapper appearing for a
    large cap is routine and says nothing.
    """
    a = (cfg or {}).get("alert", {})
    if new_stage == "TOKENIZED":
        if not a.get("tokenized_alert", True):
            return False, "cold-tokenization alerts disabled"
        if not is_upgrade(previous_stage, new_stage):
            return False, "already seen this wrapper"
        if pumpability < a.get("min_tokenized_pumpability", 60.0):
            return False, f"not a nanocap (pumpability {pumpability:.0f})"
        if equity_is_moving(eq, cfg):
            return False, "equity already moving — the window has closed"
        threshold = a.get("min_tokenized_score", 55.0)
        if score < threshold:
            return False, f"score {score:.0f} < {threshold:.0f}"
        return True, f"cold tokenization of a nanocap, score {score:.0f}"

    if new_stage not in ("RAMPING", "CLUSTER"):
        return False, f"stage {new_stage} is not an alerting rung"
    if not is_upgrade(previous_stage, new_stage):
        return False, f"already at or past {new_stage}"
    if equity_is_moving(eq, cfg):
        return False, "equity already moving — the window has closed"
    threshold = a.get("min_alert_score", 45.0)
    if score < threshold:
        return False, f"score {score:.0f} < {threshold:.0f}"
    return True, f"{new_stage} while equity quiet, score {score:.0f}"


def hours_since(earlier: datetime | None, later: datetime) -> float | None:
    if earlier is None:
        return None
    return round((later - earlier).total_seconds() / 3600.0, 3)
