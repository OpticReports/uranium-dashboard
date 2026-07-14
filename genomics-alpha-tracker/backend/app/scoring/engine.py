"""Alpha Signal scoring engine.

Pipeline per run:
  1. Gather raw per-name features from the DB (NULL-aware).
  2. Normalize each component across the active universe (z-score -> 0-100, or
     percentile), so scores are comparable and a name "lights up" relative to
     its peers.
  3. Combine with config weights (missing components excluded from the
     denominator, never zero-filled).
  4. Persist an auditable ScoreSnapshot whose `formula` exposes every raw value,
     normalized contribution, weight, and weighted term -- so you can see WHY a
     name scored what it did, not just the number.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ..config import flags_config, scoring_config
from ..models import (
    AnalystRevision,
    Catalyst,
    Fundamental,
    InsiderTxn,
    PriceBar,
    ScoreSnapshot,
    Security,
    SocialMention,
)
from ..utils.normalize import percentile_rank, zscore, zscore_to_0_100
from . import components as C
from .flags import evaluate_flags

logger = logging.getLogger(__name__)


def _latest_fundamental(session: Session, symbol: str) -> Fundamental | None:
    stmt = (
        select(Fundamental)
        .where(Fundamental.symbol == symbol)
        .order_by(Fundamental.asof.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def _gather_raw(session: Session, sec: Security, asof: date, cfg: dict) -> dict:
    comp = cfg["components"]

    # --- revision velocity ---
    rv_cfg = comp["revision_velocity"]
    since = asof - timedelta(days=rv_cfg["window_days"])
    revs = session.exec(
        select(AnalystRevision)
        .where(AnalystRevision.symbol == sec.symbol)
        .where(AnalystRevision.date >= since)
    ).all()
    rev_raw = C.revision_velocity_raw(
        [C.RevisionLike(r.date, r.direction) for r in revs],
        asof,
        rv_cfg["window_days"],
        rv_cfg["half_life_days"],
    )

    # --- catalyst score ---
    cat_cfg = comp["catalyst_score"]
    cats = session.exec(
        select(Catalyst).where(Catalyst.symbol == sec.symbol)
    ).all()
    cat_raw = C.catalyst_score_raw(
        [C.CatalystLike(c.date, c.event_type, c.impact_override) for c in cats],
        asof,
        cat_cfg["horizon_days"],
        cat_cfg["half_life_days"],
        cat_cfg["impact_weights"],
    )

    # --- hype: mention acceleration + price change ---
    hd_cfg = comp["hype_divergence"]
    m_since = asof - timedelta(days=hd_cfg["mention_window_days"])
    mentions = session.exec(
        select(SocialMention)
        .where(SocialMention.symbol == sec.symbol)
        .where(SocialMention.date >= m_since)
    ).all()
    if mentions:
        by_day: dict[date, float] = {}
        for m in mentions:
            by_day[m.date] = by_day.get(m.date, 0.0) + m.volume
        # Dense daily series across the window (gaps = genuine 0 chatter days).
        series = [
            by_day.get(m_since + timedelta(days=i), 0.0)
            for i in range(hd_cfg["mention_window_days"] + 1)
        ]
        mention_accel = C.mention_acceleration_raw(series)
        mention_level = float(sum(series))
    else:
        mention_accel = None  # no social data at all => missing, not zero
        mention_level = None

    # One extended bar window serves price change (14d), the pullback check
    # (30d high + ATR + 50dma trend qualifier) and the volume anomaly baseline
    # (60d) without extra queries. 90 calendar days ≈ 62 trading bars.
    fcfg = flags_config()
    pb_cfg = fcfg.get("pullback_into_catalyst", {})
    va_cfg = fcfg.get("volume_anomaly", {})
    bar_window = max(
        hd_cfg["price_window_days"],
        pb_cfg.get("high_lookback_days", 30),
        va_cfg.get("lookback_days", 60),
        90,
    )
    bars = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == sec.symbol)
        .where(PriceBar.date >= asof - timedelta(days=bar_window))
        .order_by(PriceBar.date.asc())
    ).all()
    p_since = asof - timedelta(days=hd_cfg["price_window_days"])
    price_change = C.price_change_raw([b.close for b in bars if b.date >= p_since])

    hb_since = asof - timedelta(days=pb_cfg.get("high_lookback_days", 30))
    hb_bars = [b for b in bars if b.date >= hb_since]
    last_close = next((b.close for b in reversed(bars) if b.close is not None), None)
    pullback_pct = C.pullback_from_high_raw(
        [(b.high if b.high is not None else b.close) for b in hb_bars], last_close
    )
    volume_z = C.volume_zscore_raw([b.volume for b in bars])

    # Trend/volatility context for the hardened pullback flag + volume floor.
    from ..calls.rules import BarLike, atr as _atr

    atr14 = _atr([BarLike(b.date, b.high, b.low, b.close, b.open) for b in bars], 14)
    closes_only = [b.close for b in bars if b.close is not None]
    above_50dma = (
        closes_only[-1] > sum(closes_only[-50:]) / 50
        if len(closes_only) >= 50 else None
    )
    last_bar = bars[-1] if bars else None
    last_dollar_volume = (
        last_bar.close * last_bar.volume
        if last_bar is not None and last_bar.close is not None and last_bar.volume is not None
        else None
    )

    # --- insider open-market buys (for the insider cluster flag) ---
    ins_cfg = fcfg.get("insider_buying_cluster", {})
    ins_since = asof - timedelta(days=ins_cfg.get("window_days", 30))
    insider_buys = session.exec(
        select(InsiderTxn)
        .where(InsiderTxn.symbol == sec.symbol)
        .where(InsiderTxn.txn_type == "buy")
        .where(InsiderTxn.date >= ins_since)
    ).all()

    # --- positioning + runway (from latest fundamental) ---
    fund = _latest_fundamental(session, sec.symbol)
    short_interest = fund.short_interest_pct if fund else None
    skew = fund.iv_skew if fund else None
    iv = fund.iv if fund else None
    runway = fund.runway_quarters if fund else None

    return {
        "pullback_pct": pullback_pct,
        "last_close": last_close,
        "volume_z": volume_z,
        "insider_buys": insider_buys,
        "atr14": atr14,
        "above_50dma": above_50dma,
        "last_dollar_volume": last_dollar_volume,
        "rev_raw": rev_raw,
        "cat_raw": cat_raw,
        "mention_accel": mention_accel,
        "mention_level": mention_level,
        "price_change": price_change,
        "short_interest": short_interest,
        "skew": skew,
        "iv": iv,
        "runway": runway,
        "evidence": {
            "revisions": revs,
            "catalysts": cats,
            "mentions": mentions,
            "fundamental": fund,
        },
    }


def compute_scores(session: Session, asof: date | None = None) -> list[ScoreSnapshot]:
    """Compute and persist Alpha Signal snapshots for all ACTIVE names."""
    asof = asof or date.today()
    cfg = scoring_config()
    weights = cfg["weights"]
    rp_cfg = cfg["components"]["runway_penalty"]

    securities = session.exec(select(Security).where(Security.active == True)).all()  # noqa: E712
    if not securities:
        return []

    # Re-fire suppression: state-like conditions (a pullback, an insider-buy
    # window) stay true across many scoring runs; without dedup they'd re-flag
    # several times a day, spamming the views and pseudo-replicating the
    # track-record stats. One fire per (symbol, flag_type) per window.
    from ..config import load_yaml_config
    from ..models import FlagEvent

    suppress_days = load_yaml_config("flags.yaml").get("refire_suppression_days", 7)
    recent_cutoff = datetime.utcnow() - timedelta(days=suppress_days)
    suppressed: set[tuple[str, str]] = {
        (f.symbol, f.flag_type)
        for f in session.exec(select(FlagEvent).where(FlagEvent.asof >= recent_cutoff)).all()
    }

    raws = {sec.symbol: _gather_raw(session, sec, asof, cfg) for sec in securities}

    # Universe-level arrays for cross-sectional normalization.
    rev_pop = [raws[s].get("rev_raw") for s in raws]
    cat_pop = [raws[s].get("cat_raw") for s in raws]
    accel_pop = [raws[s].get("mention_accel") for s in raws]
    price_pop = [raws[s].get("price_change") for s in raws]
    si_pop = [raws[s].get("short_interest") for s in raws]
    skew_pop = [raws[s].get("skew") for s in raws]
    iv_pop = [raws[s].get("iv") for s in raws]
    mention_level_pop = [raws[s].get("mention_level") for s in raws]

    # hype_divergence = z(accel) - z(price); then z-scored across the universe.
    divergences: dict[str, float | None] = {}
    for sym, r in raws.items():
        z_a = zscore(r["mention_accel"], accel_pop)
        z_p = zscore(r["price_change"], price_pop)
        divergences[sym] = None if (z_a is None or z_p is None) else (z_a - z_p)
    div_pop = list(divergences.values())

    snapshots: list[ScoreSnapshot] = []
    now = datetime.utcnow()

    for sec in securities:
        r = raws[sec.symbol]

        # Universe z-scores consumed by the flag evaluator.
        r["mention_accel_z"] = zscore(r["mention_accel"], accel_pop)
        r["mention_z"] = zscore(r["mention_level"], mention_level_pop)
        r["iv_z"] = zscore(r["iv"], iv_pop)

        # --- normalize each component to 0-100 (higher = more bullish) ---
        rev_contrib = zscore_to_0_100(zscore(r["rev_raw"], rev_pop))
        cat_contrib = zscore_to_0_100(zscore(r["cat_raw"], cat_pop))
        hype_contrib = zscore_to_0_100(zscore(divergences[sec.symbol], div_pop))

        si_pctile = percentile_rank(r["short_interest"], si_pop)
        skew_pctile = percentile_rank(r["skew"], skew_pop)
        pos_parts = [p for p in (si_pctile, skew_pctile) if p is not None]
        pos_contrib = (sum(pos_parts) / len(pos_parts)) * 100.0 if pos_parts else None

        penalty = C.runway_penalty_magnitude(
            r["runway"], rp_cfg["threshold_quarters"], rp_cfg["floor_quarters"]
        )
        runway_contrib = None if penalty is None else (100.0 - penalty)

        contributions = {
            "revision_velocity": rev_contrib,
            "catalyst_score": cat_contrib,
            "hype_divergence": hype_contrib,
            "positioning": pos_contrib,
            "runway_penalty": runway_contrib,
        }
        composite, used_weights = C.combine(contributions, weights)
        missing = [k for k, v in contributions.items() if v is None]

        formula = {
            "method": "weighted mean of present components, each scaled 0-100",
            "asof": asof.isoformat(),
            "weights_config": weights,
            "weights_used": used_weights,
            "components": {
                "revision_velocity": {
                    "raw": r["rev_raw"],
                    "normalized": rev_contrib,
                    "weight": weights.get("revision_velocity"),
                    "weighted": _wt(rev_contrib, used_weights.get("revision_velocity")),
                },
                "catalyst_score": {
                    "raw": r["cat_raw"],
                    "normalized": cat_contrib,
                    "weight": weights.get("catalyst_score"),
                    "weighted": _wt(cat_contrib, used_weights.get("catalyst_score")),
                },
                "hype_divergence": {
                    "raw_divergence": divergences[sec.symbol],
                    "mention_acceleration": r["mention_accel"],
                    "price_change": r["price_change"],
                    "normalized": hype_contrib,
                    "weight": weights.get("hype_divergence"),
                    "weighted": _wt(hype_contrib, used_weights.get("hype_divergence")),
                },
                "positioning": {
                    "short_interest_pct": r["short_interest"],
                    "short_interest_percentile": si_pctile,
                    "skew": r["skew"],
                    "skew_percentile": skew_pctile,
                    "normalized": pos_contrib,
                    "weight": weights.get("positioning"),
                    "weighted": _wt(pos_contrib, used_weights.get("positioning")),
                },
                "runway_penalty": {
                    "runway_quarters": r["runway"],
                    "penalty_magnitude": penalty,
                    "normalized": runway_contrib,
                    "weight": weights.get("runway_penalty"),
                    "weighted": _wt(runway_contrib, used_weights.get("runway_penalty")),
                },
            },
            "composite": composite,
        }

        snap = ScoreSnapshot(
            symbol=sec.symbol,
            asof=now,
            composite=composite,
            components={k: v for k, v in contributions.items()},
            missing=missing,
            formula=formula,
        )
        session.add(snap)
        snapshots.append(snap)

        # Flags reference the same evidence rows. Suppressed = fired within
        # the re-fire window already; skipping keeps the flag stream eventful.
        for flag in evaluate_flags(sec, asof, r, contributions):
            if (flag.symbol, flag.flag_type) in suppressed:
                continue
            session.add(flag)
            suppressed.add((flag.symbol, flag.flag_type))

    session.commit()
    for snap in snapshots:
        session.refresh(snap)
    logger.info("Computed %d Alpha Signal snapshots", len(snapshots))
    return snapshots


def _wt(contrib: float | None, weight: float | None) -> float | None:
    if contrib is None or weight is None:
        return None
    return contrib * weight
