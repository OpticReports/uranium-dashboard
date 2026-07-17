"""Grounded chat analyst.

A Claude agent that answers investment questions by calling tools that pull the
dashboard's REAL data (Alpha Signal components, flags, catalysts, fundamentals)
plus live FMP valuation for ANY ticker — then writes a structured trade memo.
The model never invents numbers: every figure traces to a tool result.

v1 is a non-streaming manual tool loop (robust; the memo is long-form anyway).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import (
    AnalystRevision,
    Catalyst,
    Fundamental,
    FlagEvent,
    PriceBar,
    ScoreSnapshot,
    Security,
)

logger = logging.getLogger(__name__)
_FMP = "https://financialmodelingprep.com/stable"

SYSTEM_PROMPT = """\
You are a PhD-level genomics + quant sector analyst embedded in a family office's \
Alpha Tracker dashboard. You help the principal reason about trades.

GROUNDING RULES (critical):
- NEVER invent numbers. Every quantitative claim must come from a tool result. \
Call tools before asserting figures (price, valuation, Alpha Signal, runway, catalysts).
- If a datum is missing, say so explicitly rather than guessing. "n/a" means no data, \
not zero.
- Names in the watchlist have a full Alpha Signal (use get_alpha_analysis). For any \
other ticker (e.g. MU, NVDA), use get_live_valuation — it works for the whole market.
- Cite the figures you used inline (e.g. "forward P/E 9.8x", "Alpha 72", "runway 3.2q").

The Alpha Signal is a 0-100 peer-relative score (50 = universe average) blending \
analyst-revision velocity, catalyst proximity, hype-vs-price divergence, positioning, \
and cash runway. It is a ranking of forward setup, not a price or return.

OUTPUT — unless the user asks for something narrower, structure your answer as a trade memo:
1. **Snapshot** — key facts you pulled (price, valuation, Alpha Signal if in universe).
2. **Thesis & smart entry** — your read + a concrete entry zone/plan with reasoning \
(valuation floor, support, catalyst timing). Staged entries where sensible.
3. **Bull case** — the strongest argument FOR, tied to the data.
4. **Bear case** — the strongest argument AGAINST (adversarial, not a token caveat).
5. **Probability analysis** — base / bull / bear scenarios with rough subjective \
probabilities and price/return implications → an expected-value read, plus risk/reward \
and a conviction-scaled position-size suggestion. Label these clearly as judgment, not fact.
6. **What would change my mind** — the disconfirming signals to watch.

End every memo with: "Research, not investment advice." Be direct and quantitative. \
Use the genomics/biotech context (binary catalysts, cash runway, dilution risk) where relevant.\
"""

TOOLS = [
    {
        "name": "get_alpha_analysis",
        "description": "Full Alpha Signal breakdown for a watchlist name: composite score, "
        "each component (raw + normalized + weight), active flags, latest fundamentals "
        "(market cap, cash, runway, short interest), recent analyst-revision count, and "
        "upcoming catalysts. Returns in_universe=false if the symbol isn't tracked.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker, e.g. CRSP"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_live_valuation",
        "description": "Live market valuation for ANY US ticker (works outside the watchlist): "
        "price, market cap, trailing & forward P/E, P/S, P/B, margins, revenue growth, "
        "debt/equity, beta, 52-week range. Use for tickers like MU, NVDA, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_price_history",
        "description": "Recent daily closing prices for a ticker (for entry levels, support, "
        "and recent momentum). Returns the last N trading days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "days": {"type": "integer", "description": "Lookback in days (default 90)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_catalysts",
        "description": "Upcoming catalysts (FDA/PDUFA, trial readouts, earnings) for a watchlist "
        "name, with estimated dates and impact weights.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_top_alpha",
        "description": "The watchlist names with the highest current Alpha Signal — use to answer "
        "'what looks best in my universe' or to compare a name against the leaders.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many (default 10)"}},
        },
    },
]


# --- tool executors ---------------------------------------------------------

def _fmp_get(path: str, params: dict) -> object:
    if not settings.fmp_api_key:
        return {"error": "no FMP key configured"}
    try:
        r = httpx.get(f"{_FMP}{path}", params={**params, "apikey": settings.fmp_api_key},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": repr(exc)[:160]}


def _tool_get_alpha_analysis(session: Session, symbol: str) -> dict:
    symbol = symbol.upper()
    sec = session.get(Security, symbol)
    if sec is None:
        return {"in_universe": False, "symbol": symbol,
                "note": "Not in the watchlist; use get_live_valuation instead."}
    snap = session.exec(
        select(ScoreSnapshot).where(ScoreSnapshot.symbol == symbol)
        .order_by(ScoreSnapshot.asof.desc()).limit(1)
    ).first()
    fund = session.exec(
        select(Fundamental).where(Fundamental.symbol == symbol)
        .order_by(Fundamental.asof.desc()).limit(1)
    ).first()
    since = datetime.utcnow() - timedelta(days=21)
    flags = session.exec(
        select(FlagEvent).where(FlagEvent.symbol == symbol).where(FlagEvent.asof >= since)
    ).all()
    rev_count = len(session.exec(
        select(AnalystRevision).where(AnalystRevision.symbol == symbol)
        .where(AnalystRevision.date >= date.today() - timedelta(days=90))
    ).all())
    cats = session.exec(
        select(Catalyst).where(Catalyst.symbol == symbol).where(Catalyst.date >= date.today())
        .order_by(Catalyst.date.asc()).limit(5)
    ).all()
    return {
        "in_universe": True, "symbol": symbol, "name": sec.name, "subsector": sec.subsector,
        "alpha_signal": snap.composite if snap else None,
        # components (0-100 per driver) is enough to reason on; the full `formula`
        # dict is large and redundant, and would be re-sent every loop iteration.
        "components": snap.components if snap else None,
        "missing_components": snap.missing if snap else None,
        "fundamentals": None if fund is None else {
            "market_cap": fund.market_cap, "cash": fund.cash,
            "quarterly_burn": fund.quarterly_burn, "runway_quarters": fund.runway_quarters,
            "rd_spend": fund.rd_spend, "short_interest_pct": fund.short_interest_pct,
            "iv": fund.iv, "iv_skew": fund.iv_skew,
        },
        "active_flags": [{"type": f.flag_type, "severity": f.severity, "message": f.message}
                         for f in {f.flag_type: f for f in flags}.values()],
        "analyst_revisions_90d": rev_count,
        "upcoming_catalysts": [{"date": c.date.isoformat(), "event_type": c.event_type,
                                "title": c.title, "impact": c.effective_impact} for c in cats],
    }


def _tool_get_live_valuation(symbol: str) -> dict:
    symbol = symbol.upper()
    profile = _fmp_get("/profile", {"symbol": symbol})
    ratios = _fmp_get("/ratios-ttm", {"symbol": symbol})
    metrics = _fmp_get("/key-metrics-ttm", {"symbol": symbol})
    est = _fmp_get("/analyst-estimates", {"symbol": symbol, "period": "annual", "limit": 2})
    p = profile[0] if isinstance(profile, list) and profile else {}
    r = ratios[0] if isinstance(ratios, list) and ratios else {}
    m = metrics[0] if isinstance(metrics, list) and metrics else {}
    price = p.get("price")
    # Forward P/E from next fiscal year's consensus EPS, if available.
    fwd_pe = None
    if isinstance(est, list):
        future = [e for e in est if e.get("date", "") > date.today().isoformat()]
        nxt = future[0] if future else (est[0] if est else None)
        eps = nxt.get("epsAvg") if nxt else None
        if price and eps and eps > 0:
            fwd_pe = round(price / eps, 2)
    return {
        "symbol": symbol, "company": p.get("companyName"), "price": price,
        "market_cap": p.get("marketCap"), "beta": p.get("beta"),
        "range_52w": p.get("range"), "sector": p.get("sector"), "industry": p.get("industry"),
        "pe_ttm": r.get("priceToEarningsRatioTTM"),
        "forward_pe": fwd_pe,
        "ps_ttm": r.get("priceToSalesRatioTTM"),
        "pb_ttm": r.get("priceToBookRatioTTM"),
        "gross_margin_ttm": r.get("grossProfitMarginTTM"),
        "net_margin_ttm": r.get("netProfitMarginTTM"),
        "debt_to_equity_ttm": r.get("debtToEquityRatioTTM"),
        "free_cash_flow_yield_ttm": m.get("freeCashFlowYieldTTM"),
        "note": "Live FMP TTM data. forward_pe derived from consensus next-FY EPS.",
    }


def _tool_get_price_history(session: Session, symbol: str, days: int = 90) -> dict:
    symbol = symbol.upper()
    since = date.today() - timedelta(days=days)
    bars = session.exec(
        select(PriceBar).where(PriceBar.symbol == symbol).where(PriceBar.date >= since)
        .order_by(PriceBar.date.asc())
    ).all()
    if bars:
        closes = [{"date": b.date.isoformat(), "close": b.close} for b in bars if b.close]
        src = "dashboard"
    else:
        data = _fmp_get("/historical-price-eod/light", {"symbol": symbol})
        closes = []
        if isinstance(data, list):
            for d in list(reversed(data))[-days:]:
                closes.append({"date": (d.get("date") or "")[:10], "close": d.get("price")})
        src = "fmp-live"
    if not closes:
        return {"symbol": symbol, "error": "no price data"}
    vals = [c["close"] for c in closes if c["close"]]
    return {
        "symbol": symbol, "source": src, "points": len(closes),
        "latest": closes[-1], "period_low": min(vals), "period_high": max(vals),
        "change_pct": round((vals[-1] - vals[0]) / vals[0] * 100, 1) if len(vals) > 1 and vals[0] else None,
        "recent": closes[-15:],
    }


def _tool_get_catalysts(session: Session, symbol: str) -> dict:
    symbol = symbol.upper()
    cats = session.exec(
        select(Catalyst).where(Catalyst.symbol == symbol).where(Catalyst.date >= date.today())
        .order_by(Catalyst.date.asc())
    ).all()
    return {"symbol": symbol, "catalysts": [
        {"date": c.date.isoformat(), "days_until": (c.date - date.today()).days,
         "event_type": c.event_type, "title": c.title, "impact": c.effective_impact,
         "confirmed": c.confirmed} for c in cats]}


def _tool_get_top_alpha(session: Session, limit: int = 10) -> dict:
    latest: dict[str, ScoreSnapshot] = {}
    for snap in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
        latest[snap.symbol] = snap
    secs = {s.symbol: s for s in session.exec(select(Security)).all()}
    rows = [{"symbol": sym, "name": secs.get(sym).name if secs.get(sym) else sym,
             "alpha_signal": s.composite}
            for sym, s in latest.items()
            if secs.get(sym) and secs[sym].active and s.composite is not None]
    rows.sort(key=lambda r: -r["alpha_signal"])
    return {"top": rows[:limit]}


def _set_conversation_cache(messages: list[dict]) -> None:
    """Put a single ephemeral cache breakpoint on the last block of the last message.

    The agent re-sends the entire conversation on every loop iteration AND every
    follow-up turn — that's quadratic token growth. A breakpoint at the tail lets
    each subsequent request read the whole prior prefix (system + tools + all prior
    turns/tool-results) from cache at ~0.1x instead of full price. We strip any
    earlier message-level breakpoint first so we never exceed the 4-breakpoint cap
    (the static system+tools breakpoint is the only other one).
    """
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            for blk in c:
                if isinstance(blk, dict):
                    blk.pop("cache_control", None)
    if not messages:
        return
    last = messages[-1]
    c = last["content"]
    if isinstance(c, str):
        c = [{"type": "text", "text": c}]
        last["content"] = c
    if isinstance(c, list) and c and isinstance(c[-1], dict):
        c[-1]["cache_control"] = {"type": "ephemeral"}


def _dispatch(session: Session, name: str, args: dict) -> dict:
    if name == "get_alpha_analysis":
        return _tool_get_alpha_analysis(session, args["symbol"])
    if name == "get_live_valuation":
        return _tool_get_live_valuation(args["symbol"])
    if name == "get_price_history":
        return _tool_get_price_history(session, args["symbol"], args.get("days", 90))
    if name == "get_catalysts":
        return _tool_get_catalysts(session, args["symbol"])
    if name == "get_top_alpha":
        return _tool_get_top_alpha(session, args.get("limit", 10))
    return {"error": f"unknown tool {name}"}


def _accumulate(usage: dict, resp) -> None:
    u = getattr(resp, "usage", None)
    if u is None:
        return
    usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
    usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
    usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
    usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0


def run_chat(session: Session, message: str, history: list[dict] | None = None,
             deep: bool = False) -> dict:
    """Run one chat turn. Returns {answer, model, tools_used, usage}. Raises on
    config error. Backend: native ANTHROPIC_API_KEY preferred; otherwise
    OPENROUTER_API_KEY drives the same Claude models via OpenRouter."""
    if not (settings.anthropic_api_key or settings.openrouter_api_key):
        raise RuntimeError("neither ANTHROPIC_API_KEY nor OPENROUTER_API_KEY is set")

    messages: list[dict] = []
    for turn in (history or [])[-8:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    if not settings.anthropic_api_key:
        return _run_chat_openrouter(session, messages, deep)

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = settings.chat_model_deep if deep else settings.chat_model_default

    tools_used: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    for _ in range(settings.chat_max_tool_iters):
        # Move the conversation cache breakpoint to the tail before each call so the
        # whole prior prefix is read from cache (~0.1x) instead of re-paid in full.
        _set_conversation_cache(messages)
        resp = client.messages.create(
            model=model,
            max_tokens=settings.chat_max_tokens,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            output_config={"effort": "high" if deep else "medium"},
            messages=messages,
        )
        _accumulate(usage, resp)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"answer": text, "model": resp.model,
                    "tools_used": tools_used, "usage": usage}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                tools_used.append(f"{block.name}({block.input.get('symbol', block.input.get('limit', ''))})")
                try:
                    out = _dispatch(session, block.name, block.input)
                except Exception as exc:  # noqa: BLE001
                    out = {"error": repr(exc)[:160]}
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})

    return {"answer": "(Reached tool-call limit without a final answer — try rephrasing.)",
            "model": model, "tools_used": tools_used, "usage": usage}


def _run_chat_openrouter(session: Session, messages: list[dict], deep: bool) -> dict:
    """Same grounded tool loop via OpenRouter's OpenAI-format API."""
    from ..utils.openrouter import anthropic_tools_to_openai, chat_completion

    model = (settings.openrouter_chat_model_deep if deep
             else settings.openrouter_chat_model_default)
    convo: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    oa_tools = anthropic_tools_to_openai(TOOLS)
    tools_used: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

    for _ in range(settings.chat_max_tool_iters):
        payload = chat_completion(model, convo, tools=oa_tools,
                                  max_tokens=settings.chat_max_tokens)
        u = payload.get("usage") or {}
        usage["input_tokens"] += int(u.get("prompt_tokens") or 0)
        usage["output_tokens"] += int(u.get("completion_tokens") or 0)
        msg = payload["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"answer": msg.get("content") or "",
                    "model": payload.get("model", model),
                    "tools_used": tools_used, "usage": usage}
        convo.append({"role": "assistant", "content": msg.get("content"),
                      "tool_calls": calls})
        for call in calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tools_used.append(f"{fn['name']}({args.get('symbol', args.get('limit', ''))})")
            try:
                out = _dispatch(session, fn["name"], args)
            except Exception as exc:  # noqa: BLE001
                out = {"error": repr(exc)[:160]}
            convo.append({"role": "tool", "tool_call_id": call["id"],
                          "content": json.dumps(out, default=str)})

    return {"answer": "(Reached tool-call limit without a final answer — try rephrasing.)",
            "model": model, "tools_used": tools_used, "usage": usage}
