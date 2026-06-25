"""End-to-end (offline) test of the scoring engine against a seeded DB.

No network: we hand-seed prices/catalysts/fundamentals/social so the engine's
DB wiring, cross-sectional normalization, auditable formula output, and flag
emission are all exercised deterministically.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models import (
    Catalyst,
    Fundamental,
    PriceBar,
    Security,
    SocialMention,
)
from app.scoring.engine import compute_scores


def _seed(session):
    today = date.today()
    # Two names so cross-sectional z-scores are well-defined.
    session.add(Security(symbol="AAA", name="Alpha", subsector=["gene-editing"]))
    session.add(Security(symbol="BBB", name="Beta", subsector=["dx"]))

    # Prices over the last 14 days: AAA up 10%, BBB flat.
    for i in range(15):
        d = today - timedelta(days=14 - i)
        session.add(PriceBar(symbol="AAA", date=d, close=100 + i))
        session.add(PriceBar(symbol="BBB", date=d, close=100.0))

    # AAA: imminent high-impact catalyst; BBB: none.
    session.add(Catalyst(symbol="AAA", date=today + timedelta(days=10),
                         event_type="pdufa", title="PDUFA", impact_weight=1.0))

    # Fundamentals: AAA short runway (cliff), BBB healthy.
    session.add(Fundamental(symbol="AAA", asof=today, cash=20.0, quarterly_burn=10.0,
                            runway_quarters=2.0, short_interest_pct=0.30, iv=0.9, iv_skew=0.1))
    session.add(Fundamental(symbol="BBB", asof=today, cash=400.0, quarterly_burn=10.0,
                            runway_quarters=40.0, short_interest_pct=0.05, iv=0.4, iv_skew=0.02))

    # Social mentions accelerating for AAA.
    counts = [1, 1, 1, 2, 2, 2, 8, 9, 12, 15, 20, 25, 30, 40]
    for i, c in enumerate(counts):
        d = today - timedelta(days=14 - i)
        session.add(SocialMention(symbol="AAA", date=d, platform="stocktwits",
                                  volume=c, sentiment=0.5))
        session.add(SocialMention(symbol="BBB", date=d, platform="stocktwits",
                                  volume=5, sentiment=0.0))
    session.commit()


def test_compute_scores_produces_auditable_snapshots(session):
    _seed(session)
    snaps = compute_scores(session)
    assert len(snaps) == 2
    by_sym = {s.symbol: s for s in snaps}

    aaa = by_sym["AAA"]
    assert aaa.composite is not None
    # Formula must expose raw + normalized + weight + weighted for every component.
    comps = aaa.formula["components"]
    for key in ("revision_velocity", "catalyst_score", "hype_divergence",
                "positioning", "runway_penalty"):
        assert key in comps
        assert "normalized" in comps[key]

    # AAA has a catalyst, BBB does not -> AAA catalyst contribution higher.
    assert (comps["catalyst_score"]["normalized"]
            >= by_sym["BBB"].formula["components"]["catalyst_score"]["normalized"])


def test_missing_component_listed_and_not_zero_filled(session):
    # A lone name with no analyst revisions: revision_velocity must be "missing",
    # not silently scored 0.
    session.add(Security(symbol="ONLY", name="Solo", subsector=["x"]))
    session.commit()
    snaps = compute_scores(session)
    snap = snaps[0]
    assert "revision_velocity" in snap.missing
    assert snap.components["revision_velocity"] is None


def test_runway_cliff_flag_emitted(session):
    _seed(session)
    compute_scores(session)
    from sqlmodel import select

    from app.models import FlagEvent

    flags = session.exec(select(FlagEvent).where(FlagEvent.symbol == "AAA")).all()
    types = {f.flag_type for f in flags}
    # Short runway + imminent high-impact catalyst should both fire.
    assert "runway_cliff_approaching" in types
    assert "binary_event_within_n_days" in types
