from fastapi.testclient import TestClient

from data_health_monitor.api.dependencies import (
    get_genie_context_service,
    get_genie_space_coordinator,
    get_payor_config_service,
    get_qa_context_service,
    get_test_case_service,
    get_validation_sql_service,
)
from data_health_monitor.main import app
from data_health_monitor.models.genie import GenieSQLGeneration, GenieSerializedSpace
from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.qa_context import QAContext, QAContextRequest, TableContext
from data_health_monitor.services.genie_service import GenieError
from data_health_monitor.models.test_case import TestCase
from data_health_monitor.models.validation_sql import ValidationSQL
from data_health_monitor.services.qa_context_service import QAContextTestCaseNotFoundError


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
        response = client.post("/api/v1/qa/context", json=payload)
        missing = client.post("/api/v1/qa/context", json={**payload, "test_case_id": "missing"})
    finally:
        app.dependency_overrides.pop(get_qa_context_service, None)

    assert response.status_code == 200
    assert response.json()["tables"][0]["table_name"] == "members"
    assert missing.status_code == 404


def test_test_case_create_route_returns_the_created_test_case():
    class FakeTestCaseService:
        def create_test_case(self, test_case):
            return TestCase(test_case_id="TC000001", **test_case.model_dump())

    app.dependency_overrides[get_test_case_service] = lambda: FakeTestCaseService()
    client = TestClient(app)
    payload = {
        "pipeline": "Silver",
        "component": "Member validation",
        "test_scenario": "Validate member IDs",
        "target_object": "main.qa.members",
        "input_data": "Daily member file",
        "validation_check": "Member ID is populated",
        "expected_result": "No missing member IDs",
    }
    try:
        response = client.post("/api/v1/test-cases", json=payload)
    finally:
        app.dependency_overrides.pop(get_test_case_service, None)

    assert response.status_code == 200
    assert response.json()["test_case_id"] == "TC000001"
    assert response.json()["validation_check"] == "Member ID is populated"


def test_payor_discovery_route_precedes_dynamic_payor_route():
    app.dependency_overrides[get_payor_config_service] = lambda: type(
        "Service", (), {"list_payors": lambda self: ["ABC", "XYZ"]}
    )()
    client = TestClient(app)
    try:
        response = client.get("/api/v1/payor-config/payors")
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
        response = client.post("/api/v1/payor-config/file-types:lookup", json={"payor": "ABC"})
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
            "/api/v1/qa/genie-context",
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


def test_genie_space_route_applies_context_then_generates_sql():
    captured_spaces = []

    class FakeGenieContextService:
        def build_context(self, qa_context):
            return GenieSerializedSpace(version=2)

    class FakeGenieSpaceCoordinator:
        def generate_sql(self, serialized_space, content):
            captured_spaces.append((serialized_space, content))
            return GenieSQLGeneration(
                space_id="qa-space",
                conversation_id="conversation-1",
                message_id="message-1",
                sql="SELECT 1",
            )

    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    app.dependency_overrides[get_genie_context_service] = lambda: FakeGenieContextService()
    app.dependency_overrides[get_genie_space_coordinator] = lambda: FakeGenieSpaceCoordinator()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/qa/genie-space",
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
    assert response.json()["sql"] == "SELECT 1"
    assert captured_spaces == [
        (
            GenieSerializedSpace(version=2),
            "Generate validation SQL for test case TC1. "
            "1. Query main.qa.test_cases where test_case_id is TC1; use validation_check and "
            "expected_result as the requirement. "
            "2. Execute the test-case lookup separately and inspect its result; do not combine lookup and validation work in a CTE. "
            "3. For each target, separately query main.qa.payor_config where payor and file_type match the listed values. "
            "4. Validate only these target tables: dev.poc.members (ABC/member). "
            "5. Use metadata to verify columns; execute small intermediate lookup and sample queries, observe each result, and reason before the next query. "
            "6. Generate the candidate validation SQL without inventing validation logic, execute it, and inspect the result. "
            "7. If it fails, is incomplete, or does not test the requirement, investigate and revise it before responding. "
            "8. Return only the final executable validation SQL that directly validates the target; never return a CTE, CASE, CONCAT, or other query that constructs SQL as text.",
        )
    ]


def test_genie_space_route_includes_the_raw_sdk_error_in_a_bad_gateway_response():
    class FakeGenieContextService:
        def build_context(self, qa_context):
            return GenieSerializedSpace(version=2)

    class FakeGenieSpaceCoordinator:
        def generate_sql(self, serialized_space, content):
            try:
                raise RuntimeError("Databricks rejected the warehouse ID")
            except RuntimeError as error:
                raise GenieError("Unable to create Genie space.") from error

    app.dependency_overrides[get_qa_context_service] = lambda: FakeContextService()
    app.dependency_overrides[get_genie_context_service] = lambda: FakeGenieContextService()
    app.dependency_overrides[get_genie_space_coordinator] = lambda: FakeGenieSpaceCoordinator()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/qa/genie-space",
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

    assert response.status_code == 502
    assert response.json()["detail"] == "Unable to create Genie space."


def test_genie_conversation_route_continues_the_existing_conversation():
    captured_messages = []

    class FakeGenieSpaceCoordinator:
        def continue_conversation(self, conversation_id, content):
            captured_messages.append((conversation_id, content))
            return GenieSQLGeneration(
                space_id="qa-space",
                conversation_id=conversation_id,
                message_id="message-2",
                sql="SELECT revised",
            )

    app.dependency_overrides[get_genie_space_coordinator] = lambda: FakeGenieSpaceCoordinator()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/qa/genie/conversations/conversation-1/messages",
            json={"content": "Check duplicate health_plan_id values."},
        )
    finally:
        app.dependency_overrides.pop(get_genie_space_coordinator, None)

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT revised"
    assert captured_messages == [("conversation-1", "Check duplicate health_plan_id values.")]


def test_validation_sql_route_saves_the_finalized_sql():
    captured_requests = []

    class FakeValidationSQLService:
        def save(self, request):
            captured_requests.append(request)
            return ValidationSQL(
                **request.model_dump(),
                validation_sql_id="validation-1",
                created_at="2026-08-31T00:00:00Z",
            )

    app.dependency_overrides[get_validation_sql_service] = lambda: FakeValidationSQLService()
    client = TestClient(app)
    payload = {
        "test_case_id": "TC1",
        "target_table": "dev.poc.members",
        "payor": "ABC",
        "file_type": "member",
        "generated_sql": "SELECT 1",
        "genie_space_id": "qa-space",
        "conversation_id": "conversation-1",
        "message_id": "message-2",
    }
    try:
        response = client.post("/api/v1/qa/validation-sql", json=payload)
    finally:
        app.dependency_overrides.pop(get_validation_sql_service, None)

    assert response.status_code == 200
    assert response.json()["status"] == "SAVED"
    assert captured_requests[0].generated_sql == "SELECT 1"


def test_validation_sql_execution_route_executes_a_saved_statement():
    class FakeValidationSQLService:
        def execute_saved(self, validation_sql_id):
            return {
                "validation_sql_id": validation_sql_id,
                "test_case_id": "TC1",
                "target_table": "dev.poc.members",
                "payor": "ABC",
                "file_type": "member",
                "statement_id": "statement-1",
                "execution_status": "SUCCEEDED",
                "row_count": 1,
                "columns": ["invalid_count"],
                "rows": [[0]],
                "executed_at": "2026-08-31T00:00:00Z",
            }

    app.dependency_overrides[get_validation_sql_service] = lambda: FakeValidationSQLService()
    client = TestClient(app)
    try:
        response = client.post("/api/v1/qa/validation-sql/validation-1:execute")
    finally:
        app.dependency_overrides.pop(get_validation_sql_service, None)

    assert response.status_code == 200
    assert response.json()["execution_status"] == "SUCCEEDED"
    assert response.json()["rows"] == [[0]]