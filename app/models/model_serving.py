from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ModelServingRequest(BaseModel):
    inputs: Any


class ModelServingResponse(BaseModel):
    predictions: Any
    request_id: str | None = None