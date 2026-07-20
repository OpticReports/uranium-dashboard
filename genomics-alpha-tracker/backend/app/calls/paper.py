"""Paper-trading account over the logged calls — turns the Calls Log into a
simulated book with a starting balance and a tracked account value.

Deterministic reconstruction (no new tables, no migration): every call is
sized at its OPEN off the account's realized equity at that moment, using
fixed-fractional risk — each call risks `risk_per_trade_pct` of equity at its
stop, capped at `max_position_pct` notional. Because risk is a constant % of
equity, 1R equals that % of the account by construction (default 1R = 1%),
so the R-multiples already shown map straight to account moves.

Sizing is frozen by construction: a past call's size depends only on realized
equity as of its open date, which never changes retroactively — so the book
is reproducible and past positions never re-size when new calls appear.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from ..config import calls_config
from ..models import PriceBar, TradeCall

_CLOSED = ("target_hit", "stopped", "expired", "closed_manual")


def _paper_cfg() -> dict:
    p = calls_config().get("paper", {}) or {}
    return {
        "enabled": p.get("enabled", True),
        "starting_capital": float(p.get("starting_capital", 100_000)),
        "risk_pct": float(p.get("risk_per_trade_pct", 0.01)),
        "max_pos_pct": float(p.get("max_position_pct", 0.20)),
    }


def _last_closes(session: Session, symbols: set[str]) -> dict[str, tuple[date, float]]:
    out: dict[str, tuple[date, float]] = {}
    for sym in symbols:
        bar = session.exec(
            select(PriceBar).where(PriceBar.symbol == sym)
            .where(PriceBar.close != None)  # noqa: E711
            .order_by(PriceBar.date.desc()).limit(1)
        ).first()
        if bar is not None:
            out[sym] = (bar.date, bar.close)
    return out


def _size(equity: float, entry: float, stop: float, cfg: dict) -> int:
    """Shares such that hitting the stop loses risk_pct of equity, capped at
    max_position_pct of equity by notional. Returns whole shares (>= 0)."""
    per_share_risk = abs(entry - stop)
    if per_share_risk <= 0 or entry <= 0 or equity <= 0:
        return 0
    shares = (cfg["risk_pct"] * equity) / per_share_risk
    max_shares_notional = (cfg["max_pos_pct"] * equity) / entry
    return int(max(0, min(shares, max_shares_notional)))


def paper_account(session: Session) -> dict:
    """Reconstruct the paper book from all calls. Returns account summary,
    per-position detail (by call_id), and a stepped equity curve."""
    cfg = _paper_cfg()
    start = cfg["starting_capital"]

    calls = session.exec(select(TradeCall).order_by(TradeCall.call_date.asc(),
                                                    TradeCall.id.asc())).all()
    if not calls:
        return {"enabled": cfg["enabled"], "starting_capital": start,
                "account_value": start, "cash": start, "positions_value": 0.0,
                "realized_pnl": 0.0, "open_pnl": 0.0, "total_return_pct": 0.0,
                "invested": 0.0, "n_open": 0, "n_closed": 0,
                "positions": {}, "equity_curve": [], "risk_per_trade_pct": cfg["risk_pct"]}

    # Time-ordered events; on a shared date, closes settle before opens so freed
    # equity is available to size the new call.
    events: list[tuple[date, int, str, TradeCall]] = []
    for c in calls:
        events.append((c.call_date, 0, "open", c))
        if c.status in _CLOSED and c.exit_date is not None:
            events.append((c.exit_date, -1, "close", c))
    events.sort(key=lambda e: (e[0], e[1]))

    realized_equity = start
    sizes: dict[int, int] = {}
    realized_pnl_by_call: dict[int, float] = {}
    curve: list[dict] = [{"date": calls[0].call_date.isoformat(), "equity": round(start, 2)}]

    for ev_date, _, kind, c in events:
        if kind == "open":
            sizes[c.id] = _size(realized_equity, c.entry_price, c.stop_price, cfg)
        else:  # close -> realize P&L
            sh = sizes.get(c.id, 0)
            sign = -1.0 if c.direction == "short" else 1.0
            pnl = sh * (c.exit_price - c.entry_price) * sign if c.exit_price is not None else 0.0
            realized_equity += pnl
            realized_pnl_by_call[c.id] = pnl
            curve.append({"date": ev_date.isoformat(), "equity": round(realized_equity, 2)})

    # Mark open positions to the latest close.
    open_calls = [c for c in calls if c.status == "open"]
    marks = _last_closes(session, {c.symbol for c in open_calls})
    positions: dict[str, dict] = {}
    open_pnl = 0.0
    invested = 0.0
    positions_value = 0.0
    for c in calls:
        sh = sizes.get(c.id, 0)
        sign = -1.0 if c.direction == "short" else 1.0
        cost = sh * c.entry_price
        entry_pct = None
        row = {
            "shares": sh, "entry": c.entry_price, "cost_basis": round(cost, 2),
            "status": c.status,
        }
        if c.status == "open":
            mark = marks.get(c.symbol)
            last = mark[1] if mark else c.entry_price
            mv = sh * last
            upnl = sh * (last - c.entry_price) * sign
            open_pnl += upnl
            invested += cost
            positions_value += mv
            row.update({"last": last, "market_value": round(mv, 2),
                        "unrealized_pnl": round(upnl, 2),
                        "unrealized_pct": (upnl / cost) if cost else None,
                        "account_pct": (upnl / start) if start else None})
        else:
            rp = realized_pnl_by_call.get(c.id, 0.0)
            row.update({"exit": c.exit_price, "realized_pnl": round(rp, 2),
                        "realized_pct": (rp / cost) if cost else None,
                        "account_pct": (rp / start) if start else None})
        positions[str(c.id)] = row

    realized_pnl = realized_equity - start
    account_value = start + realized_pnl + open_pnl
    cash = account_value - positions_value
    curve.append({"date": "now", "equity": round(account_value, 2)})

    return {
        "enabled": cfg["enabled"],
        "starting_capital": start,
        "account_value": round(account_value, 2),
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "invested": round(invested, 2),
        "realized_pnl": round(realized_pnl, 2),
        "open_pnl": round(open_pnl, 2),
        "total_return_pct": (account_value - start) / start if start else 0.0,
        "n_open": len(open_calls),
        "n_closed": sum(1 for c in calls if c.status in _CLOSED),
        "risk_per_trade_pct": cfg["risk_pct"],
        "positions": positions,
        "equity_curve": curve,
    }
