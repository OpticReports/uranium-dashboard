"""OpenRouter backend helpers (OpenAI-format API, Claude models).

Used when OPENROUTER_API_KEY is configured and no native ANTHROPIC_API_KEY is
present. The same Claude models are reached via OpenRouter's model namespace;
tool definitions written in Anthropic format are converted on the fly.
"""
from __future__ import annotations

import httpx

from ..config import settings

_URL = "https://openrouter.ai/api/v1/chat/completions"

# native Anthropic model id -> OpenRouter model id
_MODEL_MAP = {
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-opus-4-8": "anthropic/claude-opus-4.8",
    "claude-opus-4-7": "anthropic/claude-opus-4.7",
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
}


def available() -> bool:
    return bool(settings.openrouter_api_key)


def openrouter_model(native_id: str) -> str:
    return _MODEL_MAP.get(native_id, f"anthropic/{native_id}")


def anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}} for t in tools]


def chat_completion(model: str, messages: list[dict], tools: list[dict] | None = None,
                    max_tokens: int = 4096, timeout: float = 240.0) -> dict:
    """One OpenRouter chat-completions call. Raises RuntimeError with a scrubbed
    message on HTTP failure; returns the parsed payload."""
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    try:
        r = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                     "X-Title": "Genomics Alpha Tracker"},
            json=body, timeout=timeout,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"OpenRouter error {exc.response.status_code}: {exc.response.text[:200]}"
        ) from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc}") from None
