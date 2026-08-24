from __future__ import annotations

from pydantic import BaseModel, Field


class SQLParameter(BaseModel):
    name: str
    value: str


class SQLExecutionRequest(BaseModel):
    statement: str
    warehouse_id: str
    catalog: str | None = None
    schema: str | None = None
    parameters: list[SQLParameter] = Field(default_factory=list)
    wait_timeout: str = "30s"


class SQLExecutionResult(BaseModel):
    statement_id: str | None = None
    status: str = "UNKNOWN"
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: int | None = None
