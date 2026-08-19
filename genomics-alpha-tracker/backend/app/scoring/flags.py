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
from ..utils.labels import event_label


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
                    f"High-impact {event_label(nearest.event_type)} in "
                    f"{(nearest.date - asof).days} days"
                ),
                evidence={"catalysts": [_cat_ev(c, asof) for c in imminent]},
            )
        )

    # 6) Pullback into catalyst -----------------------------------------------
    # The desk's confirmed setup, hardened against being a downtrend detector:
    # depth must be meaningful in BOTH percent and ATR terms, capped (30%+ off
    # the high is a breakdown, not a pullback), and occurring WITHIN strength
    # (above the 50dma) — a pullback in an uptrend, not a falling knife.
    f = cfg.get("pullback_into_catalyst", {})
    pullback = raw.get("pullback_pct")
    last_close = raw.get("last_close")
    atr14 = raw.get("atr14")
    if (
        pullback is not None
        and last_close
        and f.get("min_pullback_pct", 0.10) <= pullback <= f.get("max_pullback_pct", 0.30)
    ):
        # Depth in ATRs (volatility-normalized): (peak - close) / ATR.
        peak = last_close / (1.0 - pullback) if pullback < 1.0 else None
        depth_atr = (
            (peak - last_close) / atr14
            if peak is not None and atr14 not in (None, 0) else None
        )
        atr_ok = depth_atr is not None and depth_atr >= f.get("min_pullback_atr", 1.5)
        trend_ok = (
            raw.get("above_50dma") is True
            if f.get("require_above_50dma", True)
            else True
        )
        lo, hi = f.get("catalyst_min_days", 10), f.get("catalyst_max_days", 45)
        tradeable = [
            c
            for c in catalysts
            if lo <= (c.date - asof).days <= hi
            and c.effective_impact >= f.get("min_catalyst_impact", 0.7)
        ]
        if atr_ok and trend_ok and tradeable:
            nearest = min(tradeable, key=lambda c: (c.date - asof).days)
            flags.append(
                FlagEvent(
                    symbol=sec.symbol,
                    flag_type="pullback_into_catalyst",
                    severity="high",
                    message=(
                        f"Pulled back {pullback:.0%} ({depth_atr:.1f} ATRs) from its "
                        f"{f.get('high_lookback_days', 30)}-day high, still above the "
                        f"50-day average, with a high-impact "
                        f"{event_label(nearest.event_type)} in "
                        f"{(nearest.date - asof).days} days"
                    ),
                    evidence={
                        "pullback_pct": pullback,
                        "depth_atr": depth_atr,
                        "above_50dma": raw.get("above_50dma"),
                        "last_close": last_close,
                        "catalysts": [_cat_ev(c, asof) for c in tradeable],
                    },
                )
            )

    # 6b) Quiet before catalyst (OBSERVE-ONLY) ----------------------------------
    # The MRNA/INTerpath setup: a high-impact binary approaching while the
    # price is NOT already running — |drift_z| small = the market is not
    # pricing the event yet (docs/PRE_CATALYST_ASYMMETRY_STUDY.md).
    f = cfg.get("quiet_before_catalyst", {})
    drift_z = raw.get("drift_z")
    if drift_z is not None and abs(drift_z) <= f.get("max_drift_z", 0.75):
        lo, hi = f.get("catalyst_min_days", 5), f.get("catalyst_max_days", 45)
        due = [
            c
            for c in catalysts
            if lo <= (c.date - asof).days <= hi
            and c.effective_impact >= f.get("min_catalyst_impact", 0.85)
        ]
        if due:
            nearest = min(due, key=lambda c: (c.date - asof).days)
            window = f.get("window_days", 10)
            flags.append(
                FlagEvent(
                    symbol=sec.symbol,
                    flag_type="quiet_before_catalyst",
                    severity="info",
                    message=(
                        f"High-impact {event_label(nearest.event_type)} in "
                        f"{(nearest.date - asof).days} days while the last "
                        f"{window} bars drifted only {drift_z:+.2f}σ of the "
                        f"name's own vol — not yet priced"
                    ),
                    evidence={
                        "drift_z": drift_z,
                        "realized_vol_20d": raw.get("realized_vol_20d"),
                        "window_days": window,
                        "catalysts": [_cat_ev(c, asof) for c in due],
                    },
                )
            )

    # 7) Volume anomaly --------------------------------------------------------
    # log-volume z-score with a dollar floor so Tier-C noise can't fire it.
    f = cfg.get("volume_anomaly", {})
    vol_z = raw.get("volume_z")
    dollar_vol = raw.get("last_dollar_volume")
    if (
        vol_z is not None
        and vol_z >= f.get("min_volume_z", 2.5)
        and dollar_vol is not None
        and dollar_vol >= f.get("min_dollar_volume", 1_000_000)
    ):
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="volume_anomaly",
                severity="warn",
                message=(
                    f"Daily volume {vol_z:.1f}σ above its "
                    f"{f.get('lookback_days', 60)}d norm "
                    f"(${dollar_vol/1e6:.1f}M traded)"
                ),
                evidence={"volume_z": vol_z, "dollar_volume": dollar_vol},
            )
        )

    # 8b) Relative-strength leader (OBSERVE-ONLY) ------------------------------
    # The one signal the 10y historical backtest supported (BACKTEST_SIGNALS.md);
    # fires here so its LIVE track record can confirm or refute the backtest.
    f = cfg.get("relative_strength_leader", {})
    rs = raw.get("rs_60d")
    if rs is not None and rs >= f.get("min_rs_60d", 0.15):
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="relative_strength_leader",
                severity="info",
                message=(
                    f"Beating the sector (XBI) by {rs:+.0%} over the last 60 "
                    "trading days — momentum leadership"
                ),
                evidence={"rs_60d": rs},
            )
        )

    # 8) Insider buying cluster ------------------------------------------------
    # CLUSTER = multiple DISTINCT insiders with meaningful aggregate value.
    # One officer's 10b5-1 plan printing twice in a month is not a signal.
    f = cfg.get("insider_buying_cluster", {})
    buys = raw.get("insider_buys") or []
    distinct = {b.insider for b in buys if b.insider}
    total_value = sum(b.value for b in buys if b.value is not None)
    if (
        len(buys) >= f.get("min_buys", 2)
        and len(distinct) >= f.get("min_distinct_insiders", 2)
        and total_value >= f.get("min_total_value", 25_000)
    ):
        flags.append(
            FlagEvent(
                symbol=sec.symbol,
                flag_type="insider_buying_cluster",
                severity="high",
                message=(
                    f"{len(distinct)} distinct insiders bought "
                    f"(~${total_value/1000:.0f}k total) in "
                    f"{f.get('window_days', 30)}d"
                ),
                evidence={
                    "count": len(buys),
                    "distinct_insiders": len(distinct),
                    "total_value": total_value,
                    "buys": [
                        {
                            "date": b.date.isoformat(),
                            "insider": b.insider,
                            "title": b.title,
                            "shares": b.shares,
                            "value": b.value,
                        }
                        for b in buys
                    ],
                },
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
