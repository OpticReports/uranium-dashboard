"""Pluggable sentiment scoring.

Default engine is a dependency-free lexicon scorer (VADER-style) so the social
layer works with ZERO paid keys. An Anthropic-backed engine can be swapped in by
setting SENTIMENT_ENGINE=anthropic and providing ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import logging
import re

from ..config import settings

logger = logging.getLogger(__name__)

# Small finance/biotech-tuned lexicon. Scores roughly -1..+1 per token.
_POSITIVE = {
    "beat": 0.6, "beats": 0.6, "surge": 0.7, "surged": 0.7, "soar": 0.8,
    "approval": 0.8, "approved": 0.8, "breakthrough": 0.9, "positive": 0.6,
    "strong": 0.5, "buy": 0.6, "bullish": 0.8, "upgrade": 0.7, "upgraded": 0.7,
    "win": 0.5, "wins": 0.5, "success": 0.7, "successful": 0.7, "efficacy": 0.5,
    "rally": 0.6, "moon": 0.7, "squeeze": 0.4, "topline": 0.3, "hit": 0.3,
    "partnership": 0.5, "fast-track": 0.6, "granted": 0.4, "outperform": 0.6,
}
_NEGATIVE = {
    "miss": -0.6, "missed": -0.6, "plunge": -0.8, "plunged": -0.8, "crash": -0.8,
    "halt": -0.7, "halted": -0.7, "reject": -0.8, "rejected": -0.8, "crl": -0.9,
    "negative": -0.6, "weak": -0.5, "sell": -0.6, "bearish": -0.8, "downgrade": -0.7,
    "downgraded": -0.7, "fail": -0.8, "failed": -0.8, "failure": -0.8, "dilution": -0.6,
    "offering": -0.4, "lawsuit": -0.5, "warning": -0.4, "delay": -0.5, "delayed": -0.5,
    "drop": -0.5, "dropped": -0.5, "loss": -0.4, "fda reject": -0.9, "discontinue": -0.7,
}
_NEGATORS = {"not", "no", "never", "without", "n't"}
_TOKEN_RE = re.compile(r"[a-z][a-z'\-]+")


def _lexicon_score(text: str) -> float:
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return 0.0
    score = 0.0
    hits = 0
    for i, tok in enumerate(tokens):
        val = _POSITIVE.get(tok, _NEGATIVE.get(tok, 0.0))
        if val == 0.0:
            continue
        # Negation flip on the preceding token.
        if i > 0 and tokens[i - 1] in _NEGATORS:
            val = -val
        score += val
        hits += 1
    if hits == 0:
        return 0.0
    # Normalize and squash to (-1, 1).
    raw = score / hits
    return max(-1.0, min(1.0, raw))


def score_text(text: str) -> float:
    """Return sentiment in [-1, 1] for a single piece of text."""
    if not text:
        return 0.0
    if settings.sentiment_engine == "anthropic" and (
        settings.anthropic_api_key or settings.openrouter_api_key
    ):
        try:
            return _llm_score(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM sentiment failed (%s); using lexicon", exc)
    return _lexicon_score(text)


def score_many(texts: list[str]) -> float:
    """Mean sentiment across many texts; 0.0 when empty."""
    if not texts:
        return 0.0
    return sum(score_text(t) for t in texts) / len(texts)


_SENTIMENT_PROMPT = (
    "Rate the investor sentiment of this text from -1 (very "
    "bearish) to 1 (very bullish). Reply with ONLY the number.\n\n"
)


def _llm_score(text: str) -> float:
    """Optional LLM scorer: native Anthropic key preferred, OpenRouter fallback."""
    if not settings.anthropic_api_key:
        from .openrouter import chat_completion

        payload = chat_completion(
            "anthropic/claude-haiku-4.5",
            [{"role": "user", "content": _SENTIMENT_PROMPT + text[:1500]}],
            max_tokens=8, timeout=30.0,
        )
        raw = (payload["choices"][0]["message"].get("content") or "").strip()
        return max(-1.0, min(1.0, float(raw)))

    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8,
        messages=[
            {
                "role": "user",
                "content": (
                    "Rate the investor sentiment of this text from -1 (very "
                    "bearish) to 1 (very bullish). Reply with ONLY the number.\n\n"
                    + text[:1500]
                ),
            }
        ],
    )
    raw = msg.content[0].text.strip()
    return max(-1.0, min(1.0, float(raw)))
