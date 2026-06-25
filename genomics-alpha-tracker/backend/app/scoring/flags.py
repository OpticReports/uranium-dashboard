"""Named, evidence-linked alpha flags.

Each flag links back to the underlying rows (which catalysts, which revisions,
which posts) via the `evidence` payload, so a lit flag is always auditable.

Thresholds expressed as z-scores in flags.yaml are compared against the
universe z-scores the engine passes in (raw["*_z"]). Threshold values in
"natural" units (days, counts, quarters) are compared directly.
"""
from __future__ import annotations

from datetime import date

from ..config import flags_config
from ..models import FlagEvent, Security


def evaluate_flags(
    sec: Security,
    asof: date,
    raw: dict,
    contributions: dict[str, float | None],
) -> list[FlagEvent]:
    cfg = flags_config()
    flags: list[FlagEvent] = []
    evidence = raw.get("evidence", {})
    catalysts = evidence.get("catalysts", [])
    revisions = evidence.get("revisions", [])

    # 1) Pre-catalyst sentiment ramp ----------------------------------------
    f = cfg.get("pre_catalyst_sentiment_ramp", {})
    accel_z = raw.get("mention_accel_z")
    if accel_z is not None and accel_z >= f.get("min_hype_acceleration_z", 1.0):
        near = [
            c
            for c in catalysts
            if 0 <= (c.date - asof).days <= f.get("within_days", 30)
            and c.effective_impact >= f.get("min_catalyst_impact", 0.6)
        ]
        if near:
            flags.append(
                FlagEvent(
                    symbol=sec.symbol,
                    flag_type="pre_catalyst_sentiment_ramp",
                    severity="high",
                    message=(
                        f"Hype acceleration (z={accel_z:.2f}) ramping into "
                        f"{len(near)} high-impact catalyst(s) within "
                        f"{f.get('within_days', 30)}d"
                    ),
                    evidence={
                        "mention_acceleration_z": accel_z,
                        "catalysts": [_cat_ev(c, asof) for c in near],
                    },
                )
            )

    # 2) Analyst revision cluster -------------------------------------------
    f = cfg.get("analyst_revision_cluster", {})
    window = f.get("window_days", 21)
    recent = [r for r in revisions if 0 <= (asof - r.date).days <= window]
    ups = [r for r in recent if r.direction > 0]
    downs = [r for r in recent if r.direction < 0]
    min_rev = f.get("min_revisions", 3)
    for cluster, label in ((ups, "upward"), (downs, "downward")):
        if len(cluster) >= min_rev:
            flags.append(
                FlagEvent(
                    symbol=sec.symbol,
                    flag_type="analyst_revision_cluster",
                    severity="high" if label == "upward" else "warn",
                    message=(
                        f"{len(cluster)} {label} estimate revisions in {window}d"
                    ),
                    evidence={
                        "direction": label,
                        "count": len(cluster),
                        "revisions": [_rev_ev(r) for r in cluster],
                    },
                )
            )

    # 3) Unusual options + social spike -------------------------------------
    f = cfg.get("unusual_options_social_spike", {})
    iv_z = raw.get("iv_z")
    mention_z = raw.get("mention_z")
    if (
        iv_z is not None
        and mention_z is not None
        and iv_z >= f.get("min_iv_change_z", 1.5)
        and mention_z >= f.get("min_mention_z", 1.5)
    ):
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="unusual_options_social_spike",
                severity="high",
                message=(
                    f"Elevated implied vol (z={iv_z:.2f}) co-occurring with a "
                    f"social mention spike (z={mention_z:.2f})"
                ),
                evidence={"iv_z": iv_z, "mention_z": mention_z},
            )
        )

    # 4) Runway cliff approaching -------------------------------------------
    f = cfg.get("runway_cliff_approaching", {})
    runway = raw.get("runway")
    threshold = f.get("threshold_quarters", 4.0)
    if runway is not None and runway < threshold:
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="runway_cliff_approaching",
                severity="warn",
                message=f"Cash runway {runway:.1f} quarters (< {threshold})",
                evidence={"runway_quarters": runway, "threshold": threshold},
            )
        )

    # 5) Binary event within N days -----------------------------------------
    f = cfg.get("binary_event_within_n_days", {})
    within = f.get("within_days", 21)
    min_impact = f.get("min_catalyst_impact", 0.85)
    imminent = [
        c
        for c in catalysts
        if 0 <= (c.date - asof).days <= within and c.effective_impact >= min_impact
    ]
    if imminent:
        nearest = min(imminent, key=lambda c: (c.date - asof).days)
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="binary_event_within_n_days",
                severity="high",
                message=(
                    f"High-impact {nearest.event_type} in "
                    f"{(nearest.date - asof).days}d"
                ),
                evidence={"catalysts": [_cat_ev(c, asof) for c in imminent]},
            )
        )

    return flags


def _cat_ev(c, asof: date) -> dict:
    return {
        "id": getattr(c, "id", None),
        "title": getattr(c, "title", ""),
        "event_type": c.event_type,
        "date": c.date.isoformat(),
        "days_until": (c.date - asof).days,
        "impact": c.effective_impact,
        "url": getattr(c, "url", None),
    }


def _rev_ev(r) -> dict:
    return {
        "id": getattr(r, "id", None),
        "date": r.date.isoformat(),
        "firm": getattr(r, "firm", None),
        "metric": getattr(r, "metric", None),
        "direction": r.direction,
        "old_value": getattr(r, "old_value", None),
        "new_value": getattr(r, "new_value", None),
    }
