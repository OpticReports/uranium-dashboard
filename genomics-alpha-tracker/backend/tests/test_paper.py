"""Paper-account reconstruction tests: sizing, realized/open P&L, equity curve."""
from __future__ import annotations

from datetime import date, timedelta

from app.calls.paper import _size, paper_account
from app.models import PriceBar, Security, TradeCall


def test_size_risks_fixed_fraction_of_equity():
    cfg = {"risk_pct": 0.01, "max_pos_pct": 0.20}
    # $100k, risk 1% = $1000, per-share risk $20 -> 50 shares.
    assert _size(100_000, 100.0, 80.0, cfg) == 50
    # Notional cap: 50sh × $100 = $5k = 5% < 20% cap, so risk sizing wins.
    # Tight stop blows past the notional cap -> capped.
    capped = _size(100_000, 100.0, 99.0, cfg)  # risk sizing -> 1000 sh = $100k
    assert capped == 200  # 20% notional cap = $20k / $100 = 200 sh
    assert _size(100_000, 100.0, 100.0, cfg) == 0  # no risk distance -> no position


def _mk_call(session, symbol, entry, stop, target, call_date, status="open",
             exit_price=None, exit_date=None, direction="long"):
    c = TradeCall(symbol=symbol, call_date=call_date, direction=direction,
                  source="auto_flag", entry_price=entry, stop_price=stop,
                  target_price=target, expires_on=call_date + timedelta(days=45),
                  status=status, exit_price=exit_price, exit_date=exit_date,
                  return_pct=None, r_multiple=None)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def test_empty_account_is_starting_capital(session):
    acct = paper_account(session)
    assert acct["account_value"] == 100_000
    assert acct["cash"] == 100_000
    assert acct["n_open"] == 0 and acct["positions"] == {}


def test_open_position_marks_to_last_close(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d = date.today() - timedelta(days=10)
    c = _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d)
    session.add(PriceBar(symbol="CRSP", date=date.today(), close=110.0))
    session.commit()

    acct = paper_account(session)
    pos = acct["positions"][str(c.id)]
    assert pos["shares"] == 50                      # 1% of 100k / $20 risk
    assert pos["last"] == 110.0
    assert abs(pos["unrealized_pnl"] - 500.0) < 1e-6   # 50 × $10
    # 1R == 1% of account by construction: +$500 on a $1000-risk trade = +0.5R = +0.5%.
    assert abs(pos["account_pct"] - 0.005) < 1e-9
    assert abs(acct["open_pnl"] - 500.0) < 1e-6
    assert abs(acct["account_value"] - 100_500.0) < 1e-6


def test_closed_winner_realizes_pnl(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d = date.today() - timedelta(days=30)
    _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d, status="target_hit",
             exit_price=160.0, exit_date=d + timedelta(days=10))
    acct = paper_account(session)
    # 50 shares × ($160-$100) = +$3000 = +3R = +3% (a 3:1 target).
    assert abs(acct["realized_pnl"] - 3000.0) < 1e-6
    assert abs(acct["account_value"] - 103_000.0) < 1e-6
    assert abs(acct["total_return_pct"] - 0.03) < 1e-9
    assert acct["n_closed"] == 1 and acct["n_open"] == 0


def test_sizing_grows_with_equity_after_a_win(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d0 = date.today() - timedelta(days=60)
    # First call wins, lifting equity to 103k before the second call opens.
    _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d0, status="target_hit",
             exit_price=160.0, exit_date=d0 + timedelta(days=5))
    c2 = _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d0 + timedelta(days=10))
    session.add(PriceBar(symbol="CRSP", date=date.today(), close=100.0))
    session.commit()
    acct = paper_account(session)
    # Second call sizes off 103k realized equity: 1% of 103k / $20 = 51 shares.
    assert acct["positions"][str(c2.id)]["shares"] == 51


def test_short_position_pnl_is_direction_aware(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d = date.today() - timedelta(days=30)
    _mk_call(session, "CRSP", 100.0, 120.0, 60.0, d, status="target_hit",
             exit_price=60.0, exit_date=d + timedelta(days=10), direction="short")
    acct = paper_account(session)
    # Short: 50sh × (entry100 - exit60) = +$2000 gain.
    assert abs(acct["realized_pnl"] - 2000.0) < 1e-6


def test_equity_curve_steps_at_closes(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    d = date.today() - timedelta(days=40)
    _mk_call(session, "CRSP", 100.0, 80.0, 160.0, d, status="stopped",
             exit_price=80.0, exit_date=d + timedelta(days=8))
    acct = paper_account(session)
    # Start point, a close step (-$1000), and the current mark.
    equities = [p["equity"] for p in acct["equity_curve"]]
    assert equities[0] == 100_000
    assert 99_000 in equities                 # -1R stop = -$1000
    assert acct["equity_curve"][-1]["date"] == "now"
