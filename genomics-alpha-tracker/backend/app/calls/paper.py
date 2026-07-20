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
from .confidence import display_confidence
from .manager import symbol_liquidity

_CLOSED = ("target_hit", "stopped", "expired", "closed_manual")


def _paper_cfg() -> dict:
    p = calls_config().get("paper", {}) or {}
    return {
        "enabled": p.get("enabled", True),
        "starting_capital": float(p.get("starting_capital", 100_000)),
        "sizing": p.get("sizing", "conviction"),
        "min_pos_pct": float(p.get("min_position_pct", 0.04)),
        "max_pos_pct": float(p.get("max_position_pct", 0.14)),
        "concentration": float(p.get("concentration", 1.6)),
        "max_gross_pct": float(p.get("max_gross_exposure_pct", 0.85)),
        "max_heat_pct": float(p.get("max_portfolio_heat_pct", 0.20)),
        "tier_b_max_pct": float(p.get("tier_b_max_position_pct", 0.08)),
        "tier_c_max_pct": float(p.get("tier_c_max_position_pct", 0.0)),
        # legacy fixed-risk fallback
        "risk_pct": float(p.get("risk_per_trade_pct", 0.01)),
    }


def target_position_pct(confidence: float | None, cfg: dict) -> float:
    """Confidence (0-100) -> target position size as a % of equity. Convex in
    confidence (concentration>1) so capital piles onto the very best setups."""
    if confidence is None:
        confidence = 50.0
    f = max(0.0, min(1.0, confidence / 100.0)) ** cfg["concentration"]
    return cfg["min_pos_pct"] + (cfg["max_pos_pct"] - cfg["min_pos_pct"]) * f


def _tier_cap_pct(tier: str | None, cfg: dict) -> float:
    """Per-position ceiling by liquidity tier — can't concentrate into a name
    you can't exit."""
    if tier == "C" or tier is None:
        return cfg["tier_c_max_pct"]
    if tier == "B":
        return cfg["tier_b_max_pct"]
    return cfg["max_pos_pct"]  # Tier A: full conviction sizing allowed


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


def _size_conviction(equity: float, entry: float, stop: float, confidence: float | None,
                     tier: str | None, gross_room: float, heat_room: float,
                     cfg: dict) -> int:
    """Shares for a conviction-sized position: confidence -> target %, then
    clamped by the tier ceiling, remaining gross-exposure budget, and remaining
    portfolio-heat (risk-at-stop) budget. All whole shares (>= 0)."""
    if entry <= 0 or equity <= 0:
        return 0
    target_pct = min(target_position_pct(confidence, cfg), _tier_cap_pct(tier, cfg))
    notional = target_pct * equity
    notional = min(notional, max(0.0, gross_room))          # dry-powder cap
    per_share_risk = abs(entry - stop)
    if per_share_risk > 0:                                    # heat cap (risk if stopped)
        max_shares_heat = max(0.0, heat_room) / per_share_risk
        notional = min(notional, max_shares_heat * entry)
    return int(max(0, notional // entry))


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
                "invested": 0.0, "gross_exposure_pct": 0.0, "portfolio_heat_pct": 0.0,
                "n_open": 0, "n_closed": 0, "positions": {}, "equity_curve": []}

    # Tier per symbol for ALL calls (closed calls are sized at their open event
    # too, so they need a tier or they'd be treated as thin and zero-sized).
    tiers = {sym: symbol_liquidity(session, sym)["tier"]
             for sym in {c.symbol for c in calls}}

    # Time-ordered events; on a shared date, closes settle before opens (freed
    # capital is available), and same-day OPENS are funded highest-confidence
    # first so a concentrated book puts capital on the best setups before budget
    # runs out.
    events: list[tuple[date, int, float, str, TradeCall]] = []
    for c in calls:
        conf = display_confidence(c) or 0.0
        events.append((c.call_date, 0, -conf, "open", c))
        if c.status in _CLOSED and c.exit_date is not None:
            events.append((c.exit_date, -1, 0.0, "close", c))
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    realized_equity = start
    sizes: dict[int, int] = {}
    realized_pnl_by_call: dict[int, float] = {}
    open_cost = 0.0   # gross notional of still-open positions (deployed capital)
    open_heat = 0.0   # summed risk-at-stop of still-open positions
    curve: list[dict] = [{"date": calls[0].call_date.isoformat(), "equity": round(start, 2)}]

    for ev_date, kind_ord, _, kind, c in events:
        if kind == "open":
            gross_room = cfg["max_gross_pct"] * realized_equity - open_cost
            heat_room = cfg["max_heat_pct"] * realized_equity - open_heat
            sh = _size_conviction(realized_equity, c.entry_price, c.stop_price,
                                  display_confidence(c), tiers.get(c.symbol),
                                  gross_room, heat_room, cfg)
            sizes[c.id] = sh
            if c.status == "open":
                open_cost += sh * c.entry_price
                open_heat += sh * abs(c.entry_price - c.stop_price)
        else:  # close -> realize P&L, free the capital/heat
            sh = sizes.get(c.id, 0)
            sign = -1.0 if c.direction == "short" else 1.0
            pnl = sh * (c.exit_price - c.entry_price) * sign if c.exit_price is not None else 0.0
            realized_equity += pnl
            realized_pnl_by_call[c.id] = pnl
            open_cost -= sh * c.entry_price
            open_heat -= sh * abs(c.entry_price - c.stop_price)
            curve.append({"date": ev_date.isoformat(), "equity": round(realized_equity, 2)})

    # Mark open positions to the latest close.
    open_calls = [c for c in calls if c.status == "open"]
    marks = _last_closes(session, {c.symbol for c in open_calls})
    positions: dict[str, dict] = {}
    open_pnl = 0.0
    invested = 0.0
    positions_value = 0.0
    live_heat = 0.0
    for c in calls:
        sh = sizes.get(c.id, 0)
        sign = -1.0 if c.direction == "short" else 1.0
        cost = sh * c.entry_price
        risk_at_stop = sh * abs(c.entry_price - c.stop_price)
        row = {
            "shares": sh, "entry": c.entry_price, "cost_basis": round(cost, 2),
            "confidence": round(display_confidence(c) or 0.0, 1),
            "status": c.status,
            "risk_at_stop": round(risk_at_stop, 2),
        }
        if c.status == "open":
            mark = marks.get(c.symbol)
            last = mark[1] if mark else c.entry_price
            mv = sh * last
            upnl = sh * (last - c.entry_price) * sign
            open_pnl += upnl
            invested += cost
            positions_value += mv
            live_heat += risk_at_stop
            row.update({"last": last, "market_value": round(mv, 2),
                        "position_pct": (cost / start) if start else None,
                        "risk_pct": (risk_at_stop / start) if start else None,
                        "unrealized_pnl": round(upnl, 2),
                        "unrealized_pct": (upnl / cost) if cost else None,
                        "account_pct": (upnl / start) if start else None})
        else:
            rp = realized_pnl_by_call.get(c.id, 0.0)
            row.update({"exit": c.exit_price, "realized_pnl": round(rp, 2),
                        "position_pct": (cost / start) if start else None,
                        "realized_pct": (rp / cost) if cost else None,
                        "account_pct": (rp / start) if start else None})
        positions[str(c.id)] = row

    realized_pnl = realized_equity - start
    account_value = start + realized_pnl + open_pnl
    cash = account_value - positions_value
    curve.append({"date": "now", "equity": round(account_value, 2)})

    return {
        "enabled": cfg["enabled"],
        "sizing": cfg["sizing"],
        "starting_capital": start,
        "account_value": round(account_value, 2),
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "invested": round(invested, 2),
        "realized_pnl": round(realized_pnl, 2),
        "open_pnl": round(open_pnl, 2),
        "total_return_pct": (account_value - start) / start if start else 0.0,
        "gross_exposure_pct": (invested / account_value) if account_value else 0.0,
        "portfolio_heat_pct": (live_heat / account_value) if account_value else 0.0,
        "max_gross_exposure_pct": cfg["max_gross_pct"],
        "max_portfolio_heat_pct": cfg["max_heat_pct"],
        "n_open": len(open_calls),
        "n_closed": sum(1 for c in calls if c.status in _CLOSED),
        "positions": positions,
        "equity_curve": curve,
    }
