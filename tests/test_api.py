from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from data_health_monitor.api.routes import get_databricks_service
from data_health_monitor.main import app
from data_health_monitor.models.metadata import MetadataRefreshRequest
from data_health_monitor.repositories.metadata_repository import MetadataRepository
from data_health_monitor.services.metadata_service import MetadataService


class FakeDatabricksService:
    def list_catalogs(self):
        return [{"name": "main"}, {"name": "sandbox"}]

    def list_schemas(self, catalog_name: str):
        return [{"name": "sales"}, {"name": "public"}]

    def list_tables(self, catalog_name: str, schema_name: str):
        return [{"name": "orders"}, {"name": "customers"}]

    def list_volumes(self, catalog_name: str, schema_name: str):
        return [{"name": "landing"}]

    def get_table_metadata(self, catalog_name: str, schema_name: str, table_name: str):
        return {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "name": table_name,
            "table_type": "MANAGED",
            "data_source_format": "DELTA",
            "comment": "Sample table",
            "storage_location": f"s3://{catalog_name}/{schema_name}/{table_name}",
            "columns": [
                {"name": "id", "type_name": "BIGINT", "nullable": False, "position": 1},
                {"name": "name", "type_name": "STRING", "nullable": True, "position": 2},
            ],
        }


app.dependency_overrides[get_databricks_service] = lambda: FakeDatabricksService()
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_catalogs_endpoint():
    response = client.get("/api/databricks/catalogs")
    assert response.status_code == 200
    assert response.json() == {"catalogs": [{"name": "main"}, {"name": "sandbox"}]}


def test_metadata_refresh_and_summary_endpoints():
    response = client.post(
        "/api/metadata/refresh",
        json={"scope_type": "schema", "catalog_name": "main", "schema_name": "sales"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    # scope is now nested under refresh
    assert payload["refresh"]["scope"]["type"] == "schema"
    assert payload["refresh"]["scope"]["catalog_name"] == "main"
    assert payload["refresh"]["scope"]["schema_name"] == "sales"

    summary = client.get("/api/metadata/summary")
    assert summary.status_code == 200, summary.text
    summary_json = summary.json()
    assert summary_json["scope_type"] == "schema"
    assert summary_json["catalog_name"] == "main"

    saved = client.get("/api/metadata")
    assert saved.status_code == 200, saved.text
    assert saved.json()["refresh"]["scope"]["schema_name"] == "sales"


def test_table_refresh_preserves_sibling_tables(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "table", "catalog_name": "main", "schema_name": "silver", "table_name": "customer"}},
            "catalogs": [
                {
                    "name": "main",
                    "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                    "schemas": [
                        {
                            "name": "silver",
                            "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                            "tables": [
                                {"catalog_name": "main", "schema_name": "silver", "name": "customer", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "old", "storage_location": "loc-a", "columns": [{"name": "id", "type_name": "LONG", "type_text": "BIGINT", "nullable": False, "position": 0, "comment": "old"}]},
                                {"catalog_name": "main", "schema_name": "silver", "name": "orders", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-b", "columns": [{"name": "order_id", "type_name": "LONG", "type_text": "BIGINT", "nullable": False, "position": 0, "comment": "keep"}]},
                            ],
                            "volumes": [{"name": "raw"}],
                        }
                    ],
                },
                {
                    "name": "gold",
                    "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                    "schemas": [
                        {"name": "analytics", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "analytics", "name": "sales", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "do not touch", "storage_location": "loc-c", "columns": []}], "volumes": []}
                    ],
                },
            ],
        }
    )

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [{"name": "raw"}],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": "refreshed",
                    "storage_location": "loc-refresh",
                    "columns": [{"name": "customer_id", "type_name": "LONG", "type_text": "BIGINT", "nullable": False, "position": 0, "comment": "fresh"}],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="table", catalog_name="main", schema_name="silver", table_name="customer"))
    snapshot = repository.load_snapshot()
    table_map = {table.name: table for table in snapshot.catalogs[0].schemas[0].tables}
    assert table_map["customer"].comment == "refreshed"
    assert table_map["orders"].comment == "keep"
    assert snapshot.catalogs[1].schemas[0].tables[0].name == "sales"


def test_new_table_added_without_removing_existing_table(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "table", "catalog_name": "main", "schema_name": "silver", "table_name": "orders"}},
            "catalogs": [{"name": "main", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "schemas": [{"name": "silver", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "silver", "name": "orders", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "existing", "storage_location": "loc-orders", "columns": []}], "volumes": []}]}],
        }
    )

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": "newly added",
                    "storage_location": "loc-customer",
                    "columns": [],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="table", catalog_name="main", schema_name="silver", table_name="customer"))
    snapshot = repository.load_snapshot()
    names = {table.name for table in snapshot.catalogs[0].schemas[0].tables}
    assert {"orders", "customer"} == names


def test_schema_refresh_replaces_only_selected_schema(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "schema", "catalog_name": "main", "schema_name": "silver"}},
            "catalogs": [
                {"name": "main", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "schemas": [{"name": "silver", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "silver", "name": "old_table", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "old", "storage_location": "loc-old", "columns": []}], "volumes": [{"name": "old_volume"}]}, {"name": "gold", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "gold", "name": "sales", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-sales", "columns": []}], "volumes": []}]},
            ],
        }
    )

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}, {"name": "orders"}],
                "list_volumes": lambda self, catalog_name, schema_name: [{"name": "new_volume"}],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": f"fresh-{table_name}",
                    "storage_location": f"loc-{table_name}",
                    "columns": [],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="schema", catalog_name="main", schema_name="silver"))
    snapshot = repository.load_snapshot()
    silver = [schema for schema in snapshot.catalogs[0].schemas if schema.name == "silver"][0]
    gold = [schema for schema in snapshot.catalogs[0].schemas if schema.name == "gold"][0]
    assert {table.name for table in silver.tables} == {"customer", "orders"}
    assert {table.name for table in gold.tables} == {"sales"}


def test_catalog_refresh_preserves_other_catalogs(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "catalog", "catalog_name": "main"}},
            "catalogs": [
                {"name": "main", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "schemas": [{"name": "silver", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "silver", "name": "old", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "old", "storage_location": "loc-old", "columns": []}], "volumes": []}]},
                {"name": "dev", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "schemas": [{"name": "bronze", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "dev", "schema_name": "bronze", "name": "raw_events", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-dev", "columns": []}], "volumes": []}]},
            ],
        }
    )

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": "fresh-main",
                    "storage_location": "loc-main",
                    "columns": [],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="catalog", catalog_name="main"))
    snapshot = repository.load_snapshot()
    names = {catalog.name for catalog in snapshot.catalogs}
    assert {"main", "dev"} == names
    assert {table.name for table in snapshot.catalogs[0].schemas[0].tables} == {"customer"}
    assert snapshot.catalogs[1].schemas[0].tables[0].name == "raw_events"


def test_refresh_timestamps_are_scoped_to_updated_object(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "table", "catalog_name": "main", "schema_name": "silver", "table_name": "customer"}},
            "catalogs": [
                {
                    "name": "main",
                    "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                    "schemas": [
                        {
                            "name": "silver",
                            "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                            "tables": [
                                {"catalog_name": "main", "schema_name": "silver", "name": "customer", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "old", "storage_location": "loc-a", "columns": []},
                                {"catalog_name": "main", "schema_name": "silver", "name": "orders", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-b", "columns": []},
                            ],
                            "volumes": [],
                        },
                        {
                            "name": "gold",
                            "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"},
                            "tables": [
                                {"catalog_name": "main", "schema_name": "gold", "name": "sales", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-c", "columns": []}
                            ],
                            "volumes": [],
                        },
                    ],
                }
            ],
        }
    )

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": "fresh",
                    "storage_location": "loc-new",
                    "columns": [],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="table", catalog_name="main", schema_name="silver", table_name="customer"))
    snapshot = repository.load_snapshot()
    customer = next(table for table in snapshot.catalogs[0].schemas[0].tables if table.name == "customer")
    orders = next(table for table in snapshot.catalogs[0].schemas[0].tables if table.name == "orders")
    sales = next(table for table in snapshot.catalogs[0].schemas[1].tables if table.name == "sales")
    assert customer.metadata.refreshed_at != datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)
    assert orders.metadata.refreshed_at == datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)
    assert sales.metadata.refreshed_at == datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)


def test_first_run_creates_hierarchy_for_new_table(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: {
                    "catalog_name": catalog_name,
                    "schema_name": schema_name,
                    "name": table_name,
                    "table_type": "MANAGED",
                    "data_source_format": "DELTA",
                    "comment": "fresh",
                    "storage_location": "loc-main",
                    "columns": [],
                },
            },
        )(),
        repository=repository,
    )

    service.refresh(MetadataRefreshRequest(scope_type="table", catalog_name="main", schema_name="silver", table_name="customer"))
    snapshot = repository.load_snapshot()
    assert snapshot.catalogs[0].name == "main"
    assert snapshot.catalogs[0].schemas[0].name == "silver"
    assert {table.name for table in snapshot.catalogs[0].schemas[0].tables} == {"customer"}


def test_failed_refresh_does_not_replace_existing_metadata(tmp_path):
    repository = MetadataRepository(file_path=tmp_path / "metadata.json")
    repository.save_snapshot(
        {
            "metadata_version": "1.0",
            "refresh": {"status": "SUCCESS", "refreshed_at": "2026-08-24T00:00:00Z", "duration_ms": 1, "scope": {"type": "table", "catalog_name": "main", "schema_name": "silver", "table_name": "customer"}},
            "catalogs": [{"name": "main", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "schemas": [{"name": "silver", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "tables": [{"catalog_name": "main", "schema_name": "silver", "name": "customer", "metadata": {"refreshed_at": "2026-08-24T00:00:00Z"}, "table_type": "MANAGED", "data_source_format": "DELTA", "comment": "keep", "storage_location": "loc-keep", "columns": []}], "volumes": []}]}],
        }
    )
    before_contents = repository.get_metadata_document()

    service = MetadataService(
        databricks_service=type(
            "Service",
            (),
            {
                "list_catalogs": lambda self: [{"name": "main"}],
                "list_schemas": lambda self, catalog_name: [{"name": "silver"}],
                "list_tables": lambda self, catalog_name, schema_name: [{"name": "customer"}],
                "list_volumes": lambda self, catalog_name, schema_name: [],
                "get_table_metadata": lambda self, catalog_name, schema_name, table_name: (_ for _ in ()).throw(ValueError("boom")),
            },
        )(),
        repository=repository,
    )

    with pytest.raises(ValueError, match="boom"):
        service.refresh(MetadataRefreshRequest(scope_type="table", catalog_name="main", schema_name="silver", table_name="customer"))

    after_contents = repository.get_metadata_document()
    assert before_contents == after_contents
