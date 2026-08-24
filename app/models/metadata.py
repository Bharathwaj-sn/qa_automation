from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MetadataNode(BaseModel):
    refreshed_at: datetime | None = None


class MetadataRefreshRequest(BaseModel):
    scope_type: Literal["table", "schema", "catalog"]
    catalog_name: str
    schema_name: str | None = None
    table_name: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "table":
            if not self.schema_name:
                raise ValueError("Table scope requires schema_name.")
            if not self.table_name:
                raise ValueError("Table scope requires table_name.")
        elif self.scope_type == "schema":
            if not self.schema_name:
                raise ValueError("Schema scope requires schema_name.")
            if self.table_name is not None:
                raise ValueError("Table name must be omitted for schema scope.")
        elif self.scope_type == "catalog":
            if self.schema_name is not None or self.table_name is not None:
                raise ValueError("Schema name and table name must be omitted for catalog scope.")

        return self


class MetadataScope(BaseModel):
    type: Literal["table", "schema", "catalog"]
    catalog_name: str
    schema_name: str | None = None
    table_name: str | None = None


class MetadataRefreshInfo(BaseModel):
    status: Literal["SUCCESS", "FAILED"] = "SUCCESS"
    refreshed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    scope: MetadataScope | None = None


class MetadataColumn(BaseModel):
    name: str
    type_name: str | None = None
    type_text: str | None = None
    nullable: bool | None = None
    position: int | None = None
    comment: str | None = None


class MetadataVolume(BaseModel):
    name: str


class MetadataTable(BaseModel):
    catalog_name: str
    schema_name: str
    name: str
    metadata: MetadataNode = Field(default_factory=MetadataNode)
    table_type: str | None = None
    data_source_format: str | None = None
    comment: str | None = None
    storage_location: str | None = None
    columns: list[MetadataColumn] = Field(default_factory=list)


class MetadataSchema(BaseModel):
    name: str
    metadata: MetadataNode = Field(default_factory=MetadataNode)
    tables: list[MetadataTable] = Field(default_factory=list)
    volumes: list[MetadataVolume] = Field(default_factory=list)


class MetadataCatalog(BaseModel):
    name: str
    metadata: MetadataNode = Field(default_factory=MetadataNode)
    schemas: list[MetadataSchema] = Field(default_factory=list)


class MetadataSnapshot(BaseModel):
    metadata_version: str = "1.0"
    refresh: MetadataRefreshInfo
    catalogs: list[MetadataCatalog] = Field(default_factory=list)


class MetadataSummary(BaseModel):
    catalog_count: int = 0
    schema_count: int = 0
    table_count: int = 0
    volume_count: int = 0
    last_refreshed_at: str | None = None
    status: str = "SUCCESS"
    scope_type: str | None = None
    catalog_name: str | None = None
    schema_name: str | None = None
