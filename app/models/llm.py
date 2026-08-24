from __future__ import annotations

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMResponse(BaseModel):
    content: str
    model: str | None = None
    usage: LLMUsage | None = None
    finish_reason: str | None = None