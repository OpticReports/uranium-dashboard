"""Chat analyst API — grounded LLM Q&A over the dashboard's data."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..chat.agent import run_chat
from ..config import settings
from ..db import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = []
    deep: bool = False  # True -> Opus "Deep analysis" model


class ChatUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class ChatResponse(BaseModel):
    answer: str
    model: str
    tools_used: list[str]
    usage: ChatUsage | None = None


@router.get("/status")
def status():
    return {
        "enabled": bool(settings.anthropic_api_key or settings.openrouter_api_key),
        "backend": "anthropic" if settings.anthropic_api_key
        else ("openrouter" if settings.openrouter_api_key else None),
        "model_default": settings.chat_model_default,
        "model_deep": settings.chat_model_deep,
    }


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, session: Session = Depends(get_session)):
    if not (settings.anthropic_api_key or settings.openrouter_api_key):
        raise HTTPException(
            503, "Chat is disabled: set ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
        )
    try:
        result = run_chat(
            session,
            payload.message,
            history=[t.model_dump() for t in payload.history],
            deep=payload.deep,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat failed")
        raise HTTPException(500, f"chat error: {exc}")
    return ChatResponse(**result)
