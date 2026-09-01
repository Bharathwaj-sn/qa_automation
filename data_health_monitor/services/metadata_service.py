from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from data_health_monitor.models.metadata import (
    MetadataCatalog,
    MetadataColumn,
    MetadataNode,
    MetadataRefreshInfo,
    MetadataRefreshRequest,
    MetadataSchema,
    MetadataSnapshot,
    MetadataScope,
    MetadataSummary,
    MetadataTable,
    MetadataVolume,
)
from data_health_monitor.repositories.metadata_repository import MetadataRepository
from data_health_monitor.services.databricks_service import DatabricksService


class MetadataService:
    def __init__(self, databricks_service: DatabricksService, repository: MetadataRepository | None = None):
        self.databricks_service = databricks_service
        self.repository = repository or MetadataRepository()

    @staticmethod
    def _read_value(obj: Any, field_name: str, default=None):
        if isinstance(obj, dict):
            return obj.get(field_name, default)
        return getattr(obj, field_name, default)

    def _column_model(self, column_obj) -> MetadataColumn:
        if isinstance(column_obj, MetadataColumn):
            return column_obj
        if isinstance(column_obj, dict):
            return MetadataColumn(**column_obj)
        return MetadataColumn(
            name=self._read_value(column_obj, "name"),
            type_name=self._read_value(column_obj, "type_name"),
            type_text=self._read_value(column_obj, "type_text"),
            nullable=self._read_value(column_obj, "nullable"),
            position=self._read_value(column_obj, "position"),
            comment=self._read_value(column_obj, "comment"),
        )

    def _table_model(self, catalog_name: str, schema_name: str, table_obj) -> MetadataTable:
        raw_columns = self._read_value(table_obj, "columns", [])
        table = MetadataTable(
            catalog_name=catalog_name,
            schema_name=schema_name,
            name=self._read_value(table_obj, "name"),
            metadata=MetadataNode(refreshed_at=datetime.now(timezone.utc)),
            table_type=self._read_value(table_obj, "table_type"),
            data_source_format=self._read_value(table_obj, "data_source_format"),
            comment=self._read_value(table_obj, "comment"),
            storage_location=self._read_value(table_obj, "storage_location"),
            columns=[self._column_model(col) for col in raw_columns],
        )
        return table

    def refresh(self, request: MetadataRefreshRequest) -> MetadataSnapshot:
        started_at = perf_counter()
        refreshed_at = datetime.now(timezone.utc)

        # CATALOG scope: replace only the named catalog
        if request.scope_type == "catalog":
            catalog_name = request.catalog_name
            # build new catalog model from Databricks
            schemas: list[MetadataSchema] = []
            for schema in self.databricks_service.list_schemas(catalog_name=catalog_name):
                schema_name = self._read_value(schema, "name")
                tables: list[MetadataTable] = []
                for table in self.databricks_service.list_tables(catalog_name=catalog_name, schema_name=schema_name):
                    table_name = self._read_value(table, "name")
                    table_obj = self.databricks_service.get_table_metadata(
                        catalog_name=catalog_name, schema_name=schema_name, table_name=table_name
                    )
                    tmodel = self._table_model(catalog_name, schema_name, table_obj)
                    tables.append(tmodel)
                volumes = [MetadataVolume(name=self._read_value(v, "name")) for v in self.databricks_service.list_volumes(catalog_name=catalog_name, schema_name=schema_name)]
                schemas.append(MetadataSchema(name=schema_name, metadata=MetadataNode(refreshed_at=refreshed_at), tables=tables, volumes=volumes))

            catalog_model = MetadataCatalog(name=catalog_name, metadata=MetadataNode(refreshed_at=refreshed_at), schemas=schemas)

            snapshot = self.repository.update_catalog_metadata(catalog_name=catalog_name, catalog_data=catalog_model)
            # attach refresh info with scope
            snapshot.refresh = MetadataRefreshInfo(
                status="SUCCESS",
                refreshed_at=refreshed_at,
                duration_ms=int((perf_counter() - started_at) * 1000),
                scope=MetadataScope(type="catalog", catalog_name=catalog_name),
            )
            self.repository.save_snapshot(snapshot)
            return snapshot

        # SCHEMA scope: replace only the named schema inside the catalog
        if request.scope_type == "schema":
            catalog_name = request.catalog_name
            schema_name = request.schema_name
            tables: list[MetadataTable] = []
            for table in self.databricks_service.list_tables(catalog_name=catalog_name, schema_name=schema_name):
                table_name = self._read_value(table, "name")
                table_obj = self.databricks_service.get_table_metadata(catalog_name=catalog_name, schema_name=schema_name, table_name=table_name)
                tables.append(self._table_model(catalog_name, schema_name, table_obj))

            volumes = [MetadataVolume(name=self._read_value(v, "name")) for v in self.databricks_service.list_volumes(catalog_name=catalog_name, schema_name=schema_name)]
            schema_model = MetadataSchema(name=schema_name, metadata=MetadataNode(refreshed_at=refreshed_at), tables=tables, volumes=volumes)

            snapshot = self.repository.update_schema_metadata(catalog_name=catalog_name, schema_name=schema_name, schema_data=schema_model)
            snapshot.refresh = MetadataRefreshInfo(
                status="SUCCESS",
                refreshed_at=refreshed_at,
                duration_ms=int((perf_counter() - started_at) * 1000),
                scope=MetadataScope(type="schema", catalog_name=catalog_name, schema_name=schema_name),
            )
            self.repository.save_snapshot(snapshot)
            return snapshot

        # TABLE scope: update/add only the named table
        table_obj = self.databricks_service.get_table_metadata(
            catalog_name=request.catalog_name, schema_name=request.schema_name, table_name=request.table_name
        )
        table_model = self._table_model(request.catalog_name, request.schema_name, table_obj)
        table_model.metadata.refreshed_at = refreshed_at

        snapshot = self.repository.update_table_metadata(catalog_name=request.catalog_name, schema_name=request.schema_name, table_name=request.table_name, table_data=table_model)
        snapshot.refresh = MetadataRefreshInfo(
            status="SUCCESS",
            refreshed_at=refreshed_at,
            duration_ms=int((perf_counter() - started_at) * 1000),
            scope=MetadataScope(type="table", catalog_name=request.catalog_name, schema_name=request.schema_name, table_name=request.table_name),
        )
        self.repository.save_snapshot(snapshot)
        return snapshot

    def get_snapshot(self) -> MetadataSnapshot | None:
        return self.repository.load_snapshot()

    def get_table_metadata(self, catalog_name: str, schema_name: str, table_name: str) -> MetadataTable:
        return self.repository.get_table_metadata(catalog_name, schema_name, table_name)

    def get_summary(self) -> MetadataSummary | None:
        snapshot = self.repository.load_snapshot()
        if not snapshot:
            return None
        summary = self.repository.get_summary()
        # read scope from snapshot.refresh.scope
        scope = getattr(snapshot.refresh, "scope", None)
        return MetadataSummary(
            catalog_count=summary.get("catalog_count", 0),
            schema_count=summary.get("schema_count", 0),
            table_count=summary.get("table_count", 0),
            volume_count=summary.get("volume_count", 0),
            last_refreshed_at=summary.get("last_refreshed_at"),
            status=summary.get("status", "SUCCESS"),
            scope_type=getattr(scope, "type", None),
            catalog_name=getattr(scope, "catalog_name", None),
            schema_name=getattr(scope, "schema_name", None),
        )
