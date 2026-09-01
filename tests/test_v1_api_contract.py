from fastapi.testclient import TestClient

from data_health_monitor.api.dependencies import (
    get_databricks_service,
    get_payor_config_service,
    get_validation_sql_service,
)
from data_health_monitor.main import app
from data_health_monitor.models.databricks import SchemaResponse


EXPECTED_V1_OPERATIONS = {
    "/api/v1/databricks/whoami": {"get"},
    "/api/v1/databricks/catalogs": {"get"},
    "/api/v1/databricks/schemas:lookup": {"post"},
    "/api/v1/databricks/schema-objects:lookup": {"post"},
    "/api/v1/databricks/tables:lookup": {"post"},
    "/api/v1/metadata/refresh": {"post"},
    "/api/v1/metadata": {"get"},
    "/api/v1/metadata/summary": {"get"},
    "/api/v1/test-cases": {"get", "post"},
    "/api/v1/test-cases/{test_case_id}": {"get"},
    "/api/v1/payor-config/payors": {"get"},
    "/api/v1/payor-config/file-types:lookup": {"post"},
    "/api/v1/payor-config:lookup": {"post"},
    "/api/v1/payor-config:search": {"post"},
    "/api/v1/qa/context": {"post"},
    "/api/v1/qa/genie-context": {"post"},
    "/api/v1/qa/genie-space": {"post"},
    "/api/v1/qa/genie/conversations/{conversation_id}/messages": {"post"},
    "/api/v1/qa/validation-sql": {"post"},
    "/api/v1/qa/validation-sql:search": {"post"},
    "/api/v1/qa/validation-sql/{validation_sql_id}:execute": {"post"},
    "/api/v1/genie-space/status": {"get"},
}

V1_JSON_BODY_OPERATIONS = {
    ("/api/v1/databricks/schemas:lookup", "post"),
    ("/api/v1/databricks/schema-objects:lookup", "post"),
    ("/api/v1/databricks/tables:lookup", "post"),
    ("/api/v1/metadata/refresh", "post"),
    ("/api/v1/test-cases", "post"),
    ("/api/v1/payor-config/file-types:lookup", "post"),
    ("/api/v1/payor-config:lookup", "post"),
    ("/api/v1/payor-config:search", "post"),
    ("/api/v1/qa/context", "post"),
    ("/api/v1/qa/genie-context", "post"),
    ("/api/v1/qa/genie-space", "post"),
    ("/api/v1/qa/genie/conversations/{conversation_id}/messages", "post"),
    ("/api/v1/qa/validation-sql", "post"),
    ("/api/v1/qa/validation-sql:search", "post"),
}


def test_v1_openapi_exposes_only_the_versioned_contract():
    schema = app.openapi()
    v1_operations = {
        path: {
            method
            for method in path_item
            if method in {"get", "post", "put", "patch", "delete"}
        }
        for path, path_item in schema["paths"].items()
        if path.startswith("/api/v1/")
    }
    v1_body_operations = {
        (path, method)
        for path, path_item in schema["paths"].items()
        if path.startswith("/api/v1/")
        for method, operation in path_item.items()
        if "requestBody" in operation
    }

    assert v1_operations == EXPECTED_V1_OPERATIONS
    assert v1_body_operations == V1_JSON_BODY_OPERATIONS
    assert not any("{catalog_name}" in path or "{schema_name}" in path for path in v1_operations)
    assert not any(path.startswith("/api/v1/llm/") for path in v1_operations)
    assert not any(path.startswith("/api/v1/model-serving/") for path in v1_operations)


def test_v1_schema_lookup_reads_the_catalog_from_the_request_body():
    captured_catalog_names = []

    class FakeDatabricksService:
        def list_schemas(self, catalog_name):
            captured_catalog_names.append(catalog_name)
            return [SchemaResponse(name="qa")]

    app.dependency_overrides[get_databricks_service] = lambda: FakeDatabricksService()
    try:
        response = TestClient(app).post(
            "/api/v1/databricks/schemas:lookup",
            json={"catalog_name": "main"},
        )
        invalid_response = TestClient(app).post(
            "/api/v1/databricks/schemas:lookup",
            json={"catalog_name": ""},
        )
    finally:
        app.dependency_overrides.pop(get_databricks_service, None)

    assert response.status_code == 200
    assert response.json() == {"schemas": [{"name": "qa"}]}
    assert captured_catalog_names == ["main"]
    assert invalid_response.status_code == 422


def test_v1_payor_file_type_lookup_reads_payor_from_the_request_body():
    captured_payors = []

    class FakePayorConfigService:
        def list_file_types(self, payor):
            captured_payors.append(payor)
            return ["claims"]

    app.dependency_overrides[get_payor_config_service] = lambda: FakePayorConfigService()
    try:
        response = TestClient(app).post(
            "/api/v1/payor-config/file-types:lookup",
            json={"payor": "ABC"},
        )
    finally:
        app.dependency_overrides.pop(get_payor_config_service, None)

    assert response.status_code == 200
    assert response.json() == {"file_types": ["claims"]}
    assert captured_payors == ["ABC"]


def test_v1_validation_sql_search_accepts_an_empty_filter_body():
    captured_filters = []

    class FakeValidationSQLService:
        def list_saved(self, test_case_id):
            captured_filters.append(test_case_id)
            return []

    app.dependency_overrides[get_validation_sql_service] = lambda: FakeValidationSQLService()
    try:
        response = TestClient(app).post("/api/v1/qa/validation-sql:search", json={})
    finally:
        app.dependency_overrides.pop(get_validation_sql_service, None)

    assert response.status_code == 200
    assert response.json() == []
    assert captured_filters == [None]