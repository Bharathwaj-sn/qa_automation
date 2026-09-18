from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogLookupRequest(BaseModel):
    catalog_name: str = Field(min_length=1)


class SchemaLookupRequest(CatalogLookupRequest):
    schema_name: str = Field(min_length=1)


class TableLookupRequest(SchemaLookupRequest):
    table_name: str = Field(min_length=1)


class PayorLookupRequest(BaseModel):
    payor: str = Field(min_length=1)


class PayorConfigLookupRequest(PayorLookupRequest):
    file_type: str = Field(min_length=1)


class ValidationSQLSearchRequest(BaseModel):
    test_case_id: str | None = Field(default=None, min_length=1)