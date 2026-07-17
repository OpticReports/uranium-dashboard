"""Grounded quant chat analyst.

A Claude agent embedded in Barbell Lab with tools that call the PLATFORM
itself — tearsheets, book simulations, fraction sweeps, stored reports,
the trial registry, regime state, raw return windows. Same grounding
philosophy as the genomics Analyst Chat: the model never invents numbers;
every figure traces to a tool result.

Integrity rules carried into the agent:
* every simulation the agent runs registers trials exactly like the CLI;
* interactive runs use fewer MC paths (default 5k) and are labeled
  EXPLORATORY — the agent must direct the user to the >=20k CLI run before
  any conclusion is treated as a result;
* the trial registry has no delete API, chat or no chat.

v1 is a non-streaming manual tool loop (mirrors the genomics agent).
"""
from __future__ import annotations

import json
import logging
import os

from .. import db

logger = logging.getLogger(__name__)

MODEL = os.environ.get("BARBELL_CHAT_MODEL", "claude-opus-4-8")
EXPLORATORY_PATHS = 5000

SYSTEM_PROMPT = """\
You are a PhD-level quantitative researcher embedded in Barbell Lab, a personal
portfolio research platform for a sophisticated investor running a barbell:
a defensive sleeve ("B.5 Enhanced": AVUV/AVDV/PHYS/KMLM/AVEM/QUAL + tail sleeve)
plus a short-volatility SPX options bot. The investor is in Puerto Rico under
Act 60 (0% cap gains), so rebalancing is tax-free.

The sleeve objective is NOT Sharpe. It is: maximize long-horizon geometric CAGR
subject to hard constraints — CVaR(5%, annual) >= -15%, 5th-percentile max
drawdown >= -20%, correlation-to-bot-P&L <= 0.10, no position > 25%.

GROUNDING RULES (critical):
- NEVER invent numbers. Every quantitative claim must come from a tool result
  in this conversation. Call tools before asserting figures.
- If data is missing, say so. "n/a" means no data, not zero.
- Chat simulations run at reduced Monte Carlo paths and are EXPLORATORY.
  Present them as such, and tell the user which CLI command runs the
  full >=20k-path registered version before acting on anything.
- Statistical honesty overrides helpfulness: mention multiple-testing context
  (cumulative trial count) when comparing variants; distinguish in-sample from
  out-of-sample; a result whose CI includes zero is INCONCLUSIVE, and say so.
  "No improvement found" is a first-class, useful answer.
- Proxy-extended history and modeled bot P&L must be flagged whenever a number
  depends on them.

You help the investor tinker: compare tail-sleeve instruments, toggle the bot
overlay at any fraction, stress specific windows, read the platform's reports,
and design the next properly-registered experiment. Be direct, quantitative,
and adversarial with your own hypotheses (state what would refute them).

End every substantive analysis with: "Research, not investment advice."\
"""

TOOLS = [
    {
        "name": "get_platform_status",
        "description": "Acceptance-gate status (the platform's trust check), cumulative "
        "trial count, data provenance per ticker, and latest regime snapshot. Call this "
        "first in a conversation to know what data you're standing on.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_tearsheet",
        "description": "Full analytics tearsheet: CAGR/vol/Sharpe/maxDD/CVaR, calendar "
        "years, drawdown anatomy, correlation matrix, per-asset risk contributions, "
        "named crisis-episode stress table. bot_frac=0 analyzes the sleeve in isolation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tail": {"type": "string", "description": "TAIL | CAOS | BTAL | NONE | 'X+Y' 50/50 split"},
                "bot_frac": {"type": "number", "description": "bot capital fraction in [0,1), e.g. 0.2"},
            },
            "required": ["tail"],
        },
    },
    {
        "name": "simulate_book",
        "description": "EXPLORATORY Monte Carlo (block bootstrap, reduced paths) of the "
        "book at one sleeve/bot split: p5 and median 1y outcome, CVaR5, p5 max drawdown, "
        "10y CAGR distribution, historical CAGR/maxDD. Registers a trial.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_frac": {"type": "number", "description": "bot fraction in [0,1)"},
                "tail": {"type": "string", "description": "tail sleeve instrument (default TAIL)"},
                "kill_switch": {"type": "string", "enum": ["perfect", "lag1", "fails"]},
            },
            "required": ["bot_frac"],
        },
    },
    {
        "name": "sweep_bot_fraction",
        "description": "EXPLORATORY sweep of the sleeve/bot split across fractions "
        "(default 0..30%), reporting the growth-optimal admissible fraction under the "
        "hard constraints. Registers one trial per fraction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fractions": {"type": "array", "items": {"type": "number"}},
                "tail": {"type": "string"},
                "kill_switch": {"type": "string", "enum": ["perfect", "lag1", "fails"]},
            },
        },
    },
    {
        "name": "window_stats",
        "description": "Return stats for specific tickers over a specific date window "
        "(total return, ann. vol, max drawdown, pairwise correlations). Use for stress "
        "questions like 'what did KMLM do in March 2020'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "start": {"type": "string", "description": "YYYY-MM-DD"},
                "end": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["tickers", "start", "end"],
        },
    },
    {
        "name": "get_report",
        "description": "Read one of the platform's latest registered reports (full-rigor "
        "CLI runs): backtest, question1, question2, optimize, walkforward, book-sweep, "
        "tearsheet, monitors.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_trials",
        "description": "The cumulative trial registry (multiple-testing denominator) and "
        "the most recent registered trials.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_portfolio",
        "description": "The LIVE portfolio version (B.5 Enhanced): explicit weights, bot "
        "fraction, and the full metrics snapshot (realized CAGR/Sharpe/maxDD, expected "
        "CAGR, CVaR, constraint pass/breach). START HERE for any question about 'the "
        "portfolio'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_portfolio_versions",
        "description": "The improvement ledger: every version of the portfolio (LIVE, "
        "CANDIDATE, RETIRED) with rationale, verdict and deltas vs parent.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_candidate",
        "description": "File a CANDIDATE portfolio version and run the evaluation battery "
        "vs LIVE (registers trials). weights = full explicit dict summing to 1 (omit to "
        "keep live weights and only change bot_frac). NEVER promotes — promotion requires "
        "the investor's typed confirmation in the ledger UI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "weights": {"type": "object",
                            "description": "ticker -> weight, sums to 1.0"},
                "bot_frac": {"type": "number", "description": "bot fraction in [0,1)"},
                "rationale": {"type": "string",
                              "description": "why this change (goes in the ledger)"},
            },
            "required": ["rationale"],
        },
    },
    {
        "name": "compare_versions",
        "description": "Side-by-side metrics for two versions from the ledger (by id).",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
]


# ------------------------------------------------------------------ handlers
def _tool_get_platform_status(con) -> str:
    from ..config import load
    from ..ingest.series import total_return_series
    from ..validate.acceptance import run_gates
    out = {"acceptance_gates": [str(g) for g in run_gates(con)]}
    out["cumulative_trials"] = int(con.execute("SELECT COUNT(*) FROM trials").fetchone()[0])
    out["provenance"] = [total_return_series(con, t).provenance_summary()
                         for t in load("data")["tickers"]]
    row = con.execute("SELECT date, quadrant, labor_z, inflation_z, credit_z, dollar_z "
                      "FROM regime_log ORDER BY date DESC LIMIT 1").fetchone()
    if row:
        out["regime"] = {"date": row[0], "quadrant": row[1], "labor_z": row[2],
                         "inflation_z": row[3], "credit_z": row[4], "dollar_z": row[5]}
    return json.dumps(out)


def _tool_get_tearsheet(con, tail: str, bot_frac: float = 0.0) -> str:
    from ..portfolio.tearsheet import build_tearsheet
    return build_tearsheet(con, tail=tail, bot_frac=float(bot_frac),
                           allow_bot_model=True)


def _tool_simulate_book(con, bot_frac: float, tail: str = "TAIL",
                        kill_switch: str = "perfect") -> str:
    from ..config import load, config_hash
    from ..portfolio.book import book_frame, evaluate_fraction
    from ..stats.trials import register_trial
    mc = load("backtest")["monte_carlo"]
    joint = book_frame(con, float(bot_frac), tail=tail, allow_bot_model=True,
                       kill_switch=kill_switch)
    r = evaluate_fraction(joint, float(bot_frac), EXPLORATORY_PATHS,
                          int(mc["block_len_days"]), int(mc["seed"]))
    r["bot_provenance"] = joint.attrs.get("bot_provenance", "none")
    r["exploratory"] = f"{EXPLORATORY_PATHS} paths — full run: `barbell book --sweep`"
    register_trial(con, config_hash({"chat_sim": r["bot_frac"], "tail": tail,
                                     "ks": kill_switch}),
                   "chat", f"chat sim bot_frac={bot_frac} tail={tail} ks={kill_switch}",
                   None, len(joint), r)
    return json.dumps(r)


def _tool_sweep_bot_fraction(con, fractions=None, tail: str = "TAIL",
                             kill_switch: str = "perfect") -> str:
    from ..portfolio.book import sweep_bot_fraction
    return sweep_bot_fraction(con, fracs=[float(f) for f in fractions] if fractions else None,
                              tail=tail, allow_bot_model=True,
                              kill_switch=kill_switch, n_paths=EXPLORATORY_PATHS)


def _tool_window_stats(con, tickers, start: str, end: str) -> str:
    from ..ingest.series import total_return_series
    out = {}
    frames = {}
    for t in tickers:
        bs = total_return_series(con, str(t).upper())
        px = bs.frame["close_adj"].loc[start:end]
        if len(px) < 2:
            out[t] = "n/a — no data in window"
            continue
        r = px.pct_change().dropna()
        wealth = (1 + r).cumprod()
        out[t] = {
            "total_return": float(px.iloc[-1] / px.iloc[0] - 1),
            "ann_vol": float(r.std(ddof=1) * (252 ** 0.5)),
            "max_drawdown": float((wealth / wealth.cummax() - 1).min()),
            "provenance": bs.provenance_summary(),
        }
        frames[t] = r
    if len(frames) > 1:
        import pandas as pd
        joint = pd.DataFrame(frames).dropna()
        out["correlations"] = {f"{a}/{b}": round(float(joint[a].corr(joint[b])), 3)
                               for i, a in enumerate(joint.columns)
                               for b in list(joint.columns)[i + 1:]}
    return json.dumps(out)


def _tool_get_report(con, name: str) -> str:
    from ..config import REPORT_DIR
    safe = "".join(c for c in name.lower() if c.isalnum() or c == "-")
    path = REPORT_DIR / f"latest-{safe}.md"
    if not path.exists():
        available = sorted(p.name.removeprefix("latest-").removesuffix(".md")
                           for p in REPORT_DIR.glob("latest-*.md"))
        return json.dumps({"error": f"no report '{name}'", "available": available})
    return path.read_text()


def _tool_get_trials(con) -> str:
    from ..stats.trials import trial_summary
    return trial_summary(con)


def _tool_get_portfolio(con) -> str:
    from ..portfolio import registry
    live = registry.get_live(con)
    return json.dumps({"version": {k: live[k] for k in
                                   ("id", "name", "label", "status", "weights",
                                    "bot_frac", "adopted_at", "rationale")},
                       "metrics": registry.version_metrics(con, live)})


def _tool_list_portfolio_versions(con) -> str:
    from ..portfolio import registry
    return json.dumps(registry.ledger(con))


def _tool_propose_candidate(con, rationale: str, weights=None, bot_frac=None) -> str:
    from ..portfolio import registry
    w = ({str(k).upper(): float(v) for k, v in weights.items()} if weights else None)
    cand = registry.propose_candidate(con, weights=w, bot_frac=bot_frac,
                                      rationale=str(rationale))
    return json.dumps({"filed": cand["label"], "id": cand["id"],
                       "evidence": cand["evidence"],
                       "note": "CANDIDATE only — the investor promotes via the "
                               "ledger UI with typed confirmation"})


def _tool_compare_versions(con, a: int, b: int) -> str:
    from ..portfolio import registry
    return json.dumps(registry.compare(con, int(a), int(b)))


_HANDLERS = {
    "get_platform_status": _tool_get_platform_status,
    "get_tearsheet": _tool_get_tearsheet,
    "simulate_book": _tool_simulate_book,
    "sweep_bot_fraction": _tool_sweep_bot_fraction,
    "window_stats": _tool_window_stats,
    "get_report": _tool_get_report,
    "get_trials": _tool_get_trials,
    "get_portfolio": _tool_get_portfolio,
    "list_portfolio_versions": _tool_list_portfolio_versions,
    "propose_candidate": _tool_propose_candidate,
    "compare_versions": _tool_compare_versions,
}


def _execute(con, name: str, args: dict) -> tuple[str, bool]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"unknown tool {name}", True
    try:
        return handler(con, **args), False
    except Exception as exc:  # noqa: BLE001 — surface the error to the model
        logger.warning("chat tool %s failed: %s", name, exc)
        return f"tool error: {exc}", True


def answer(messages: list[dict], max_turns: int = 12) -> dict:
    """Run the grounded agent loop. `messages` is the prior conversation as
    [{"role": "user"|"assistant", "content": str}]. Returns final text +
    the tool calls made (for UI display).

    Backend selection: a native ANTHROPIC_API_KEY is preferred; otherwise an
    OPENROUTER_API_KEY routes the same Claude model through OpenRouter's
    OpenAI-format API. Same tools, same grounding rules either way."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _answer_anthropic(messages, max_turns)
    if os.environ.get("OPENROUTER_API_KEY"):
        return _answer_openrouter(messages, max_turns)
    raise RuntimeError("chat analyst disabled — set ANTHROPIC_API_KEY or "
                       "OPENROUTER_API_KEY on the service")


def _answer_anthropic(messages: list[dict], max_turns: int) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    con = db.connect()
    convo = list(messages)
    tool_trace: list[dict] = []
    try:
        for _ in range(max_turns):
            response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS,
                messages=convo,
            )
            if response.stop_reason != "tool_use":
                text = "".join(b.text for b in response.content if b.type == "text")
                return {"text": text, "tool_trace": tool_trace}
            convo.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                out, is_err = _execute(con, block.name, dict(block.input))
                tool_trace.append({"tool": block.name, "input": dict(block.input),
                                   "error": is_err})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": out[:60_000], "is_error": is_err})
            convo.append({"role": "user", "content": results})
        return {"text": "(analysis exceeded the tool-call budget — ask a narrower "
                        "question or run the CLI command directly)",
                "tool_trace": tool_trace}
    finally:
        con.close()


# ------------------------------------------------------------- OpenRouter
# Default model for the OpenRouter path (override with the env var; any
# OpenRouter model id with tool support works, e.g. anthropic/claude-opus-4.8).
OPENROUTER_MODEL = os.environ.get("BARBELL_CHAT_MODEL_OPENROUTER",
                                  "moonshotai/kimi-k3")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openai_tools() -> list[dict]:
    """Our Anthropic-format tool defs converted to OpenAI/OpenRouter format."""
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}} for t in TOOLS]


def _answer_openrouter(messages: list[dict], max_turns: int) -> dict:
    import httpx
    key = os.environ["OPENROUTER_API_KEY"]
    con = db.connect()
    convo: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
    tool_trace: list[dict] = []
    try:
        for _ in range(max_turns):
            try:
                r = httpx.post(
                    _OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {key}",
                             "X-Title": "Barbell Lab"},
                    json={"model": OPENROUTER_MODEL, "max_tokens": 8192,
                          "messages": convo, "tools": _openai_tools()},
                    timeout=300.0,
                )
                r.raise_for_status()
                payload = r.json()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:300]
                raise RuntimeError(f"OpenRouter error {exc.response.status_code}: "
                                   f"{detail}") from None
            msg = payload["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"text": msg.get("content") or "", "tool_trace": tool_trace}
            convo.append({"role": "assistant", "content": msg.get("content"),
                          "tool_calls": calls})
            for call in calls:
                fn = call["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                out, is_err = _execute(con, fn["name"], args)
                tool_trace.append({"tool": fn["name"], "input": args, "error": is_err})
                convo.append({"role": "tool", "tool_call_id": call["id"],
                              "content": out[:60_000]})
        return {"text": "(analysis exceeded the tool-call budget — ask a narrower "
                        "question or run the CLI command directly)",
                "tool_trace": tool_trace}
    finally:
        con.close()
