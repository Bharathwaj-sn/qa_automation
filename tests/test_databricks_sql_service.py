from __future__ import annotations

from types import SimpleNamespace

import pytest

from data_health_monitor.models.databricks_sql import SQLExecutionRequest, SQLParameter
from data_health_monitor.services.databricks_sql_service import (
    DatabricksSQLExecutionError,
    DatabricksSQLService,
)


class FakeStatementExecution:
    def __init__(self, response_sequence):
        self.response_sequence = list(response_sequence)
        self.calls = []

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return self.response_sequence.pop(0)

    def get_statement(self, statement_id):
        return self.response_sequence.pop(0)


def make_result(rows=None, columns=None, row_count=None, statement_id="stmt-123", status="SUCCEEDED"):
    return SimpleNamespace(
        statement_id=statement_id,
        status=SimpleNamespace(state=status, error=None),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(
                columns=[SimpleNamespace(name=name) for name in (columns or [])],
            )
        ),
        result=SimpleNamespace(
            data_array=rows or [],
            row_count=row_count if row_count is not None else len(rows or []),
        ),
    )


def test_execute_select_returns_normalized_result():
    response = make_result(
        rows=[["A", 1], ["B", 2]],
        columns=["name", "id"],
        row_count=2,
        statement_id="stmt-select",
    )
    client = SimpleNamespace(statement_execution=FakeStatementExecution([response]))
    service = DatabricksSQLService(client=client)

    result = service.execute(
        SQLExecutionRequest(
            statement="SELECT name, id FROM qa.test_cases",
            warehouse_id="wh-123",
        )
    )

    assert result.statement_id == "stmt-select"
    assert result.status == "SUCCEEDED"
    assert result.columns == ["name", "id"]
    assert result.rows == [["A", 1], ["B", 2]]
    assert result.row_count == 2
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


def test_execute_ddl_without_rows_returns_empty_result():
    response = make_result(rows=[], columns=[], row_count=0, statement_id="stmt-ddl", status="SUCCEEDED")
    client = SimpleNamespace(statement_execution=FakeStatementExecution([response]))
    service = DatabricksSQLService(client=client)

    result = service.execute(
        SQLExecutionRequest(
            statement="CREATE TABLE qa.example (id INT)",
            warehouse_id="wh-456",
        )
    )

    assert result.statement_id == "stmt-ddl"
    assert result.status == "SUCCEEDED"
    assert result.columns == []
    assert result.rows == []
    assert result.row_count == 0


def test_parameters_are_passed_to_statement_execution():
    response = make_result(rows=[], columns=[], row_count=0, statement_id="stmt-param", status="SUCCEEDED")
    execution = FakeStatementExecution([response])
    client = SimpleNamespace(statement_execution=execution)
    service = DatabricksSQLService(client=client)

    service.execute(
        SQLExecutionRequest(
            statement="SELECT * FROM qa.test_cases WHERE test_case_id = :test_case_id",
            warehouse_id="wh-789",
            parameters=[SQLParameter(name="test_case_id", value="TC001")],
        )
    )

    assert execution.calls[0]["parameters"] == [{"name": "test_case_id", "value": "TC001", "type": "text"}]


def test_catalog_and_schema_are_passed_to_statement_execution():
    response = make_result(rows=[], columns=[], row_count=0, statement_id="stmt-catalog", status="SUCCEEDED")
    execution = FakeStatementExecution([response])
    client = SimpleNamespace(statement_execution=execution)
    service = DatabricksSQLService(client=client)

    service.execute(
        SQLExecutionRequest(
            statement="SELECT * FROM test_cases",
            warehouse_id="wh-abc",
            catalog="main",
            schema_name="qa",
        )
    )

    assert execution.calls[0]["catalog"] == "main"
    assert execution.calls[0]["schema"] == "qa"


def test_execution_failure_raises_application_error():
    class FailingExecution:
        def execute_statement(self, **kwargs):
            raise RuntimeError("Warehouse unavailable")

    client = SimpleNamespace(statement_execution=FailingExecution())
    service = DatabricksSQLService(client=client)

    with pytest.raises(DatabricksSQLExecutionError) as exc_info:
        service.execute(
            SQLExecutionRequest(
                statement="SELECT 1",
                warehouse_id="wh-fail",
            )
        )

    assert "Warehouse unavailable" in str(exc_info.value)
    assert exc_info.value.statement_id is None


def test_provided_workspace_client_is_reused():
    response = make_result(rows=[], columns=[], row_count=0, statement_id="stmt-client", status="SUCCEEDED")
    client = SimpleNamespace(statement_execution=FakeStatementExecution([response]))
    service = DatabricksSQLService(client=client)

    assert service.client is client


def test_service_does_not_create_second_client_when_injected():
    response = make_result(rows=[], columns=[], row_count=0, statement_id="stmt-injected", status="SUCCEEDED")
    client = SimpleNamespace(statement_execution=FakeStatementExecution([response]))
    service = DatabricksSQLService(client=client)

    _ = service.execute(SQLExecutionRequest(statement="SELECT 1", warehouse_id="wh-1"))
    assert service.client is client


def test_while_pending_then_succeeds_after_polling():
    pending = SimpleNamespace(
        statement_id="stmt-poll",
        status=SimpleNamespace(state="PENDING", error=None),
        manifest=None,
        result=None,
    )
    success = make_result(rows=[[1, "ok"]], columns=["id", "status"], row_count=1, statement_id="stmt-poll", status="SUCCEEDED")
    execution = FakeStatementExecution([pending, success])
    client = SimpleNamespace(statement_execution=execution)
    service = DatabricksSQLService(client=client)

    result = service.execute(SQLExecutionRequest(statement="SELECT 1 as id, 'ok' as status", warehouse_id="wh-poll"))

    assert result.statement_id == "stmt-poll"
    assert result.rows == [[1, "ok"]]
    assert result.status == "SUCCEEDED"
