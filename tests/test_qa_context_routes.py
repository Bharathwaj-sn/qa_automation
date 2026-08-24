from fastapi.testclient import TestClient

from app.api.routes import get_payor_config_service, get_qa_context_service
from app.main import app
from app.models.qa_context import QAContext, QAContextRequest, TableContext
from app.models.test_case import TestCase
from app.services.qa_context_service import QAContextTestCaseNotFoundError


class FakeContextService:
    def build_context(self, request):
        if request.test_case_id == "missing":
            raise QAContextTestCaseNotFoundError(request.test_case_id)
        return QAContext(
            test_case=TestCase(test_case_id=request.test_case_id, pipeline="Silver", component="dates", test_scenario="valid", target_object="table", input_data="data", validation_check="check", expected_result="valid"),
            tables=[TableContext(catalog=request.catalog, schema=request.schema, table_name=request.table_name or "members", metadata={}, payor_configs=[])],
        )


def test_qa_context_route_returns_context_and_maps_missing_test_case():
    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    client = TestClient(app)
    try:
        response = client.post("/api/qa/context", json={"test_case_id": "TC1", "catalog": "dev", "schema": "poc", "table_name": "members"})
        missing = client.post("/api/qa/context", json={"test_case_id": "missing", "catalog": "dev", "schema": "poc", "table_name": "members"})
    finally:
        app.dependency_overrides.pop(get_qa_context_service, None)

    assert response.status_code == 200
    assert response.json()["tables"][0]["table_name"] == "members"
    assert missing.status_code == 404


def test_payor_discovery_route_precedes_dynamic_payor_route():
    app.dependency_overrides[get_payor_config_service] = lambda: type(
        "Service", (), {"list_payors": lambda self: ["ABC", "XYZ"]}
    )()
    client = TestClient(app)
    try:
        response = client.get("/api/payor-config/payors")
    finally:
        app.dependency_overrides.pop(get_payor_config_service, None)

    assert response.status_code == 200
    assert response.json() == {"payors": ["ABC", "XYZ"]}