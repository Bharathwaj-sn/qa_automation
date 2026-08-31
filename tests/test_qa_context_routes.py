from fastapi.testclient import TestClient

from app.api.routes import (
    get_genie_context_service,
    get_genie_space_coordinator,
    get_payor_config_service,
    get_qa_context_service,
)
from app.main import app
from app.models.genie import GenieSerializedSpace, GenieSpace
from app.models.payor_config import PayorConfig
from app.models.qa_context import QAContext, QAContextRequest, TableContext
from app.models.test_case import TestCase
from app.services.qa_context_service import QAContextTestCaseNotFoundError


class FakeContextService:
    def build_context(self, request):
        if request.test_case_id == "missing":
            raise QAContextTestCaseNotFoundError(request.test_case_id)
        return QAContext(
            test_case=TestCase(test_case_id=request.test_case_id, pipeline="Silver", component="dates", test_scenario="valid", target_object="table", input_data="data", validation_check="check", expected_result="valid"),
            tables=[
                TableContext(
                    catalog=request.catalog,
                    schema=request.schema,
                    table_name=selection.table_name,
                    metadata={},
                    expected_table=selection.table_name,
                    payor_config=PayorConfig(payor=selection.payor, file_type=selection.file_type),
                )
                for selection in request.selections
            ],
        )


def test_qa_context_route_returns_context_and_maps_missing_test_case():
    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    client = TestClient(app)
    try:
        payload = {
            "test_case_id": "TC1",
            "catalog": "dev",
            "schema": "poc",
            "selections": [{"table_name": "members", "payor": "ABC", "file_type": "member"}],
        }
        response = client.post("/api/qa/context", json=payload)
        missing = client.post("/api/qa/context", json={**payload, "test_case_id": "missing"})
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


def test_file_type_discovery_route_precedes_dynamic_payor_route():
    app.dependency_overrides[get_payor_config_service] = lambda: type(
        "Service", (), {"list_file_types": lambda self, payor: ["member", "claims"]}
    )()
    client = TestClient(app)
    try:
        response = client.get("/api/payor-config/ABC/file-types")
    finally:
        app.dependency_overrides.pop(get_payor_config_service, None)

    assert response.status_code == 200
    assert response.json() == {"file_types": ["member", "claims"]}


def test_genie_context_route_builds_qa_context_before_generating_serialized_space():
    captured_contexts = []

    class FakeGenieContextService:
        def build_context(self, qa_context):
            captured_contexts.append(qa_context)
            return GenieSerializedSpace(version=2)

    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    app.dependency_overrides[get_genie_context_service] = lambda: FakeGenieContextService()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/qa/genie-context",
            json={
                "test_case_id": "TC1",
                "catalog": "dev",
                "schema": "poc",
                "selections": [{"table_name": "members", "payor": "ABC", "file_type": "member"}],
            },
        )
    finally:
        app.dependency_overrides.pop(get_qa_context_service, None)
        app.dependency_overrides.pop(get_genie_context_service, None)

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert captured_contexts[0].tables[0].table_name == "members"


def test_genie_space_route_applies_the_generated_serialized_space():
    captured_spaces = []

    class FakeGenieContextService:
        def build_context(self, qa_context):
            return GenieSerializedSpace(version=2)

    class FakeGenieSpaceCoordinator:
        def apply_context(self, serialized_space):
            captured_spaces.append(serialized_space)
            return GenieSpace(space_id="qa-space", serialized_space=serialized_space)

    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    app.dependency_overrides[get_genie_context_service] = lambda: FakeGenieContextService()
    app.dependency_overrides[get_genie_space_coordinator] = lambda: FakeGenieSpaceCoordinator()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/qa/genie-space",
            json={
                "test_case_id": "TC1",
                "catalog": "dev",
                "schema": "poc",
                "selections": [{"table_name": "members", "payor": "ABC", "file_type": "member"}],
            },
        )
    finally:
        app.dependency_overrides.pop(get_qa_context_service, None)
        app.dependency_overrides.pop(get_genie_context_service, None)
        app.dependency_overrides.pop(get_genie_space_coordinator, None)

    assert response.status_code == 200
    assert response.json()["space_id"] == "qa-space"
    assert captured_spaces == [GenieSerializedSpace(version=2)]