from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.test_case import TestCase


class QAContextSelection(BaseModel):
    table_name: str
    payor: str
    file_type: str


class QAContextRequest(BaseModel):
    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    test_case_id: str
    catalog: str
    schema_name: str = Field(alias="schema")
    selections: list[QAContextSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_selections(self):
        identities = [(selection.table_name, selection.payor, selection.file_type) for selection in self.selections]
        if len(identities) != len(set(identities)):
            raise ValueError("selections must not contain duplicate table, payor, and file type combinations.")
        return self


class TableContext(BaseModel):
    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    catalog: str
    schema_name: str = Field(alias="schema")
    table_name: str
    metadata: dict[str, Any]
    expected_table: str
    payor_config: PayorConfig


class QAContext(BaseModel):
    test_case: TestCase
    tables: list[TableContext]