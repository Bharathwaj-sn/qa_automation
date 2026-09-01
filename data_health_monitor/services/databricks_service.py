from __future__ import annotations

from databricks.sdk import WorkspaceClient

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.databricks import (
    CatalogResponse,
    ColumnMetadata,
    SchemaObjectsResponse,
    SchemaResponse,
    TableMetadata,
    TableSummary,
    VolumeSummary,
)


class DatabricksService:
    def __init__(
        self,
        client: WorkspaceClient | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()

        if client:
            self.client = client
        elif self.settings.databricks_profile:
            self.client = WorkspaceClient(profile=self.settings.databricks_profile)
        else:
            self.client = WorkspaceClient()

    def get_current_user(self):
        user = self.client.current_user.me()
        return {
            "authenticated": True,
            "user_name": getattr(user, "user_name", None) or getattr(user, "display_name", None),
            "emails": getattr(user, "emails", None),
        }

    def list_catalogs(self):
        catalogs = self.client.catalogs.list()
        return [CatalogResponse(name=catalog.name) for catalog in catalogs]

    def list_schemas(self, catalog_name: str):
        schemas = self.client.schemas.list(catalog_name=catalog_name)
        return [SchemaResponse(name=schema.name) for schema in schemas]

    def list_tables(self, catalog_name: str, schema_name: str):
        tables = self.client.tables.list(catalog_name=catalog_name, schema_name=schema_name)
        return [TableSummary(name=table.name) for table in tables]

    def list_volumes(self, catalog_name: str, schema_name: str):
        volumes = self.client.volumes.list(catalog_name=catalog_name, schema_name=schema_name)
        return [VolumeSummary(name=volume.name) for volume in volumes]

    def list_schema_objects(self, catalog_name: str, schema_name: str):
        tables = self.list_tables(catalog_name, schema_name)
        volumes = self.list_volumes(catalog_name, schema_name)
        return SchemaObjectsResponse(tables=tables, volumes=volumes)

    def get_table_metadata(self, catalog_name: str, schema_name: str, table_name: str):
        table = self.client.tables.get(full_name=f"{catalog_name}.{schema_name}.{table_name}")

        columns = [
            ColumnMetadata(
                name=column.name,
                type_name=getattr(column, "type_name", None),
                type_text=getattr(column, "type_text", None),
                nullable=getattr(column, "nullable", None),
                position=getattr(column, "position", None),
                comment=getattr(column, "comment", None),
            )
            for column in table.columns or []
        ]

        return TableMetadata(
            catalog_name=table.catalog_name,
            schema_name=table.schema_name,
            name=table.name,
            table_type=getattr(table, "table_type", None),
            data_source_format=getattr(table, "data_source_format", None),
            comment=getattr(table, "comment", None),
            storage_location=getattr(table, "storage_location", None),
            columns=columns,
        )
