from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_health_monitor.api.routes import (
    get_genie_space_coordinator,
    get_test_case_service,
    get_validation_sql_service,
)
from data_health_monitor.config import Settings
from data_health_monitor.core.logging import configure_logging
from data_health_monitor.main import app
from data_health_monitor.services.databricks_sql_service import DatabricksSQLExecutionError
from data_health_monitor.services.test_case_service import TestCaseNotFoundError


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "application.log"
    configure_logging(Settings(app_log_file=str(file_path)))
    return file_path


def _records(log_file: Path) -> list[dict]:
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]


def test_expected_not_found_error_preserves_response_and_logs_request(log_file: Path):
    class MissingTestCaseService:
        def get_test_case(self, test_case_id: str):
            raise TestCaseNotFoundError(test_case_id)

    app.dependency_overrides[get_test_case_service] = lambda: MissingTestCaseService()
    try:
        response = TestClient(app).get("/api/test-cases/missing")
    finally:
        app.dependency_overrides.pop(get_test_case_service, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Test case 'missing' not found."}
    records = _records(log_file)
    assert records[0]["event"] == "http_exception"
    assert records[0]["level"] == "WARNING"
    assert records[0]["request_id"] == response.headers["X-Request-ID"]


def test_upstream_error_preserves_response_and_logs_without_raw_error(log_file: Path):
    class FailingValidationSQLService:
        def save(self, request):
            raise DatabricksSQLExecutionError(None, "upstream-secret-message")

    app.dependency_overrides[get_validation_sql_service] = lambda: FailingValidationSQLService()
    try:
        response = TestClient(app).post(
            "/api/qa/validation-sql",
            json={
                "test_case_id": "TC1",
                "target_table": "main.qa.members",
                "payor": "ABC",
                "file_type": "member",
                "generated_sql": "SELECT 1",
                "genie_space_id": "space-1",
                "conversation_id": "conversation-1",
                "message_id": "message-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_validation_sql_service, None)

    assert response.status_code == 502
    assert response.json()["detail"].startswith("Unable to save validation SQL.")
    records = _records(log_file)
    assert records[0]["event"] == "http_exception"
    assert records[0]["level"] == "ERROR"
    assert "upstream-secret-message" not in log_file.read_text(encoding="utf-8")


def test_unexpected_error_returns_generic_response_and_sanitized_traceback(log_file: Path):
    class FailingGenieSpaceCoordinator:
        def status(self):
            raise RuntimeError("unexpected-secret-message")

    app.dependency_overrides[get_genie_space_coordinator] = lambda: FailingGenieSpaceCoordinator()
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/genie-space/status")
    finally:
        app.dependency_overrides.pop(get_genie_space_coordinator, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert response.headers["X-Request-ID"]
    records = _records(log_file)
    assert records[0]["event"] == "unhandled_exception"
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["request_id"] == response.headers["X-Request-ID"]
    assert records[0]["traceback"]
    assert "unexpected-secret-message" not in log_file.read_text(encoding="utf-8")