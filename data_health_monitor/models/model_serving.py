from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ModelServingMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelServingRequest(BaseModel):
    messages: list[ModelServingMessage] = Field(min_length=1)
    max_tokens: int = Field(default=1000, gt=0)


class ModelServingResponse(BaseModel):
    predictions: str
    request_id: str | None = None