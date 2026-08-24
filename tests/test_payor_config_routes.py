from fastapi.testclient import TestClient

from app.main import app


def test_openapi_includes_payor_config_endpoints():
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/payor-config/{payor}/{table_name}" in schema["paths"]
    assert "/api/payor-config/{payor}" in schema["paths"]
    assert "get" in schema["paths"]["/api/payor-config/{payor}/{table_name}"]
    assert "get" in schema["paths"]["/api/payor-config/{payor}"]