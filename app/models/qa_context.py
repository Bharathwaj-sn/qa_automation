from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from app.models.payor_config import PayorConfig
from app.models.test_case import TestCase


class QAContextRequest(BaseModel):
    test_case_id: str
    catalog: str
    schema: str
    table_name: str | None = None
    include_all_tables: bool = False

    @model_validator(mode="after")
    def validate_table_scope(self):
        if self.table_name and self.include_all_tables:
            raise ValueError("table_name and include_all_tables cannot both be supplied.")
        if not self.table_name and not self.include_all_tables:
            raise ValueError("Specify table_name or set include_all_tables to true.")
        return self


class TableContext(BaseModel):
    catalog: str
    schema: str
    table_name: str
    metadata: dict[str, Any]
    payor_configs: list[PayorConfig]


class QAContext(BaseModel):
    test_case: TestCase
    tables: list[TableContext]