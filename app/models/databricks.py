from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CatalogResponse(BaseModel):
    name: str


class SchemaResponse(BaseModel):
    name: str


class TableSummary(BaseModel):
    name: str


class VolumeSummary(BaseModel):
    name: str


class ColumnMetadata(BaseModel):
    name: str
    type_name: Optional[str] = None
    type_text: Optional[str] = None
    nullable: Optional[bool] = None
    position: Optional[int] = None
    comment: Optional[str] = None


class TableMetadata(BaseModel):
    catalog_name: str
    schema_name: str
    name: str
    table_type: Optional[str] = None
    data_source_format: Optional[str] = None
    comment: Optional[str] = None
    storage_location: Optional[str] = None
    columns: list[ColumnMetadata] = Field(default_factory=list)


class SchemaObjectsResponse(BaseModel):
    tables: list[TableSummary]
    volumes: list[VolumeSummary]
