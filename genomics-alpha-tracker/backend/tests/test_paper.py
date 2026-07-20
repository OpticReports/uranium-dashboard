"""Paper-account reconstruction tests: conviction sizing, caps, P&L, curve."""
from __future__ import annotations

from datetime import date, timedelta

from app.calls.confidence import (
    compute_confidence,
    corroboration_multiplier,
    edge_multiplier,
)
from app.calls.paper import _paper_cfg, paper_account, target_position_pct
from app.models import PriceBar, Security, TradeCall


# --- confidence math ------------------------------------------------------------

def test_no_evidence_confidence_equals_composite():
    # With no track record and a single flag, confidence == the composite.
    assert compute_confidence(72.0) == 72.0
    assert compute_confidence(72.0, hit_rate_1m=None, n_1m=0, n_distinct_flags=1) == 72.0


def test_proven_signal_raises_confidence():
    # A strong, well-sampled hit rate bends confidence up (capped).
    hi = compute_confidence(70.0, hit_rate_1m=0.80, n_1m=40)
    assert hi > 70.0
    lo = compute_confidence(70.0, hit_rate_1m=0.20, n_1m=40)
    assert lo < 70.0


def test_thin_record_moves_confidence_less_than_thick():
    # Shrinkage: a 2-sample 100% hit barely nudges; a 40-sample 80% moves more.
    thin = compute_confidence(70.0, hit_rate_1m=1.0, n_1m=2) - 70.0
    thick = compute_confidence(70.0, hit_rate_1m=0.80, n_1m=40) - 70.0
    assert 0 < thin < thick


def test_edge_multiplier_shrinkage_and_cap():
    cfg = {"prior_n": 12, "gain": 0.8, "cap": 0.25, "corrob_step": 0.05}
    assert edge_multiplier(None, 0, cfg) == 1.0
    assert edge_multiplier(1.0, 200, cfg) <= 1.25  # capped
    assert edge_multiplier(0.0, 200, cfg) >= 0.75


def test_corroboration_multiplier_steps():
    cfg = {"corrob_step": 0.05}
    assert corroboration_multiplier(1, cfg) == 1.0
    assert abs(corroboration_multiplier(3, cfg) - 1.10) < 1e-9
    assert abs(corroboration_multiplier(9, cfg) - 1.15) < 1e-9  # capped at +3 flags


def test_target_pct_is_convex_in_confidence():
    cfg = _paper_cfg()
    lo = target_position_pct(40, cfg)
    hi = target_position_pct(90, cfg)
    assert cfg["min_pos_pct"] <= lo < hi <= cfg["max_pos_pct"]
    # Convexity: the top end pulls away — high conviction gets disproportionate size.
    mid = target_position_pct(65, cfg)
    assert (hi - mid) > (mid - lo)


# --- account reconstruction ------------------------------------------------------

def _mk_call(session, symbol, entry, stop, target, call_date, confidence=70.0,
             status="open", exit_price=None, exit_date=None, direction="long"):
    c = TradeCall(symbol=symbol, call_date=call_date, direction=direction,
                  source="auto_flag", entry_price=entry, stop_price=stop,
                  target_price=target, expires_on=call_date + timedelta(days=45),
                  composite_at_call=confidence, confidence=confidence,
                  status=status, exit_price=exit_price, exit_date=exit_date)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _bars(session, symbol, last_close):
    session.add(Security(symbol=symbol, name=symbol, active=True))
    # 20 sessions of decent dollar volume -> Tier A so sizing isn't liquidity-capped.
    d0 = date.today() - timedelta(days=25)
    for i in range(24):
        session.add(PriceBar(symbol=symbol, date=d0 + timedelta(days=i),
                             open=last_close, high=last_close, low=last_close,
                             close=last_close, volume=2_000_000))
    session.add(PriceBar(symbol=symbol, date=date.today(), close=last_close, volume=2_000_000))
    session.commit()


def test_higher_confidence_gets_more_capital(session):
    _bars(session, "HIGH", 100.0)
    _bars(session, "LOW", 100.0)
    hi = _mk_call(session, "HIGH", 100.0, 85.0, 145.0, date.today() - timedelta(days=3), confidence=95.0)
    lo = _mk_call(session, "LOW", 100.0, 85.0, 145.0, date.today() - timedelta(days=3), confidence=45.0)
    acct = paper_account(session)
    hi_cost = acct["positions"][str(hi.id)]["cost_basis"]
    lo_cost = acct["positions"][str(lo.id)]["cost_basis"]
    assert hi_cost > lo_cost  # conviction concentrates capital


def test_tier_c_name_gets_zero_size(session):
    # Thin name: $10 × 10k shares = $100k/day -> Tier C -> excluded from the book.
    session.add(Security(symbol="THIN", name="Thin", active=True))
    d0 = date.today() - timedelta(days=25)
    for i in range(24):
        session.add(PriceBar(symbol="THIN", date=d0 + timedelta(days=i),
                             open=10.0, high=10.0, low=10.0, close=10.0, volume=10_000))
    session.add(PriceBar(symbol="THIN", date=date.today(), close=10.0, volume=10_000))
    session.commit()
    c = _mk_call(session, "THIN", 10.0, 8.0, 16.0, date.today() - timedelta(days=3), confidence=95.0)
    acct = paper_account(session)
    assert acct["positions"][str(c.id)]["shares"] == 0


def test_gross_exposure_capped(session):
    # Ten max-confidence calls can't deploy more than the gross cap.
    for i in range(10):
        _bars(session, f"N{i}", 100.0)
        _mk_call(session, f"N{i}", 100.0, 85.0, 145.0, date.today() - timedelta(days=3), confidence=100.0)
    acct = paper_account(session)
    assert acct["gross_exposure_pct"] <= acct["max_gross_exposure_pct"] + 1e-6


def test_portfolio_heat_capped(session):
    for i in range(10):
        _bars(session, f"H{i}", 100.0)
        _mk_call(session, f"H{i}", 100.0, 70.0, 190.0, date.today() - timedelta(days=3), confidence=100.0)
    acct = paper_account(session)
    assert acct["portfolio_heat_pct"] <= acct["max_portfolio_heat_pct"] + 1e-6


def test_closed_winner_realizes_pnl(session):
    _bars(session, "CRSP", 100.0)
    d = date.today() - timedelta(days=30)
    c = _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d, confidence=70.0,
                 status="target_hit", exit_price=160.0, exit_date=d + timedelta(days=10))
    acct = paper_account(session)
    shares = acct["positions"][str(c.id)]["shares"]
    assert shares > 0
    assert abs(acct["realized_pnl"] - shares * 60.0) < 1e-6  # (160-100) × shares
    assert acct["account_value"] > acct["starting_capital"]


def test_empty_account_is_starting_capital(session):
    acct = paper_account(session)
    assert acct["account_value"] == 100_000 and acct["positions"] == {}
