from fastapi.testclient import TestClient

from data_health_monitor.api.routes import get_databricks_service
from data_health_monitor.main import app


EXPECTED_OPERATIONS = {
    "/health": {"get": {"200"}},
    "/api/databricks/whoami": {"get": {"200"}},
    "/api/databricks/catalogs": {"get": {"200"}},
    "/api/databricks/catalogs/{catalog_name}/schemas": {"get": {"200", "422"}},
    "/api/databricks/catalogs/{catalog_name}/schemas/{schema_name}/objects": {"get": {"200", "422"}},
    "/api/databricks/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}": {
        "get": {"200", "422"}
    },
    "/api/metadata/refresh": {"post": {"200", "422"}},
    "/api/metadata": {"get": {"200"}},
    "/api/metadata/summary": {"get": {"200"}},
    "/api/test-cases": {"get": {"200"}, "post": {"200", "422"}},
    "/api/test-cases/{test_case_id}": {"get": {"200", "422"}},
    "/api/payor-config/{payor}/file-types": {"get": {"200", "422"}},
    "/api/payor-config/{payor}/{file_type}": {"get": {"200", "422"}},
    "/api/payor-config/payors": {"get": {"200"}},
    "/api/payor-config/{payor}": {"get": {"200", "422"}},
    "/api/qa/context": {"post": {"200", "422"}},
    "/api/qa/genie-context": {"post": {"200", "422"}},
    "/api/qa/genie-space": {"post": {"200", "422"}},
    "/api/qa/genie/conversations/{conversation_id}/messages": {"post": {"200", "422"}},
    "/api/qa/validation-sql": {"get": {"200", "422"}, "post": {"200", "422"}},
    "/api/qa/validation-sql/{validation_sql_id}/execute": {"post": {"200", "422"}},
    "/api/genie-space/status": {"get": {"200"}},
    "/api/llm/chat": {"post": {"200", "422"}},
    "/api/model-serving/predict": {"post": {"200", "422"}},
}

JSON_BODY_OPERATIONS = {
    ("/api/metadata/refresh", "post"),
    ("/api/test-cases", "post"),
    ("/api/qa/context", "post"),
    ("/api/qa/genie-context", "post"),
    ("/api/qa/genie-space", "post"),
    ("/api/qa/genie/conversations/{conversation_id}/messages", "post"),
    ("/api/qa/validation-sql", "post"),
    ("/api/llm/chat", "post"),
    ("/api/model-serving/predict", "post"),
}


def test_legacy_openapi_paths_methods_and_responses_are_stable():
    schema = app.openapi()
    operations = {
        path: {
            method: set(operation["responses"])
            for method, operation in path_item.items()
            if method in {"get", "post", "put", "patch", "delete"}
        }
        for path, path_item in schema["paths"].items()
        if path == "/health" or (path.startswith("/api/") and not path.startswith("/api/v1/"))
    }

    assert schema["info"] == {"title": "Data Health Monitor API", "version": "0.1.0"}
    assert operations == EXPECTED_OPERATIONS
    assert {
        (path, method)
        for path, path_item in schema["paths"].items()
        if path == "/health" or (path.startswith("/api/") and not path.startswith("/api/v1/"))
        for method, operation in path_item.items()
        if "requestBody" in operation
    } == JSON_BODY_OPERATIONS


def test_legacy_whoami_uses_the_first_registered_handler():
    class FakeDatabricksService:
        def get_current_user(self):
            return {
                "authenticated": True,
                "user_name": "test.user@example.com",
                "emails": ["test.user@example.com"],
            }

    app.dependency_overrides[get_databricks_service] = lambda: FakeDatabricksService()
    try:
        response = TestClient(app).get("/api/databricks/whoami")
    finally:
        app.dependency_overrides.pop(get_databricks_service, None)

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user_name": "test.user@example.com",
        "emails": ["test.user@example.com"],
    }