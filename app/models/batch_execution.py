from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.validation_sql import TestCaseResult, ValidationSQL


class BatchExecutionRequest(BaseModel):
    validation_sql_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if len(self.validation_sql_ids) != len(set(self.validation_sql_ids)):
            raise ValueError("validation_sql_ids must not contain duplicates.")
        return self


class BatchQueryExecutionResult(BaseModel):
    validation_sql: ValidationSQL
    execution_order: int
    status: Literal["SUCCEEDED", "FAILED", "SKIPPED"]
    duration_ms: int
    statement_id: str | None = None
    result: TestCaseResult | None = None
    error: str | None = None


class BatchExecutionResult(BaseModel):
    batch_id: str
    status: Literal["SUCCEEDED", "COMPLETED_WITH_FAILURES", "FAILED"]
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    total_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    query_results: list[BatchQueryExecutionResult] = Field(default_factory=list)
    error: str | None = None