from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SQLParameter(BaseModel):
    name: str
    value: str
    type: str | None = None


class SQLExecutionRequest(BaseModel):
    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    statement: str
    warehouse_id: str
    catalog: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    parameters: list[SQLParameter] = Field(default_factory=list)
    wait_timeout: str = "30s"


class SQLExecutionResult(BaseModel):
    statement_id: str | None = None
    status: str = "UNKNOWN"
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: int | None = None
