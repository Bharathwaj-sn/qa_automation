from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from data_health_monitor.config import Settings
from data_health_monitor.core.logging import configure_logging, log_event
from data_health_monitor.main import app


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "application.log"
    configure_logging(
        Settings(
            app_log_file=str(file_path),
            app_log_max_bytes=1024,
            app_log_backup_count=1,
        )
    )
    return file_path


def _records(log_file: Path) -> list[dict]:
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]


def test_requests_receive_unique_request_ids_and_emit_completion_events(log_file: Path):
    client = TestClient(app)

    first_response = client.get("/health")
    second_response = client.get("/health")

    first_request_id = first_response.headers["X-Request-ID"]
    second_request_id = second_response.headers["X-Request-ID"]
    assert first_response.status_code == second_response.status_code == 200
    assert first_request_id != second_request_id
    assert UUID(first_request_id).hex == first_request_id
    assert UUID(second_request_id).hex == second_request_id
    assert [record["event"] for record in _records(log_file)] == [
        "request_completed",
        "request_completed",
    ]


def test_validation_failures_do_not_log_request_payloads(log_file: Path):
    client = TestClient(app)
    secret_value = "do-not-log-this-request-value"

    response = client.post(
        "/api/metadata/refresh",
        json={"scope_type": "table", "catalog_name": secret_value},
    )

    assert response.status_code == 422
    records = _records(log_file)
    assert records[0]["event"] == "request_validation_failed"
    assert records[0]["request_id"] == response.headers["X-Request-ID"]
    assert secret_value not in log_file.read_text(encoding="utf-8")


def test_log_file_rotates_without_removing_the_active_file(tmp_path: Path):
    log_file = tmp_path / "rotating.log"
    configure_logging(
        Settings(
            app_log_file=str(log_file),
            app_log_max_bytes=1,
            app_log_backup_count=1,
        )
    )

    log_event(logging.INFO, "first_rotation_event")
    log_event(logging.INFO, "second_rotation_event")

    assert log_file.exists()
    assert Path(f"{log_file}.1").exists()