from __future__ import annotations

import pytest

from app.config import Settings
from app.models.databricks_sql import SQLExecutionResult
from app.models.validation_sql import ValidationSQL, ValidationSQLCreate
from app.services.databricks_sql_service import DatabricksSQLExecutionError
from app.services.validation_sql_service import (
    ValidationSQLResultPersistenceError,
    ValidationSQLService,
)


class MockSQLService:
    def __init__(self, responses: list[SQLExecutionResult] | None = None) -> None:
        self.calls = []
        self.responses = responses or []

    def execute(self, request):
        self.calls.append(request)
        return self.responses.pop(0) if self.responses else SQLExecutionResult(status="SUCCEEDED")


def test_save_initializes_table_and_uses_parameterized_insert():
    sql_service = MockSQLService()
    settings = Settings(
        validation_sql_catalog="audit",
        validation_sql_schema="qa",
        validation_sql_table_name="validation_sql",
        test_case_results_catalog="results",
        test_case_results_schema="audit",
        test_case_results_table_name="test_case_results",
        databricks_warehouse_id="warehouse",
    )
    service = ValidationSQLService(sql_service, settings)

    result = service.save(
        ValidationSQLCreate(
            test_case_id="TC1",
            target_table="main.qa.members",
            payor="ABC",
            file_type="member",
            generated_sql="SELECT 1",
            genie_space_id="space-1",
            conversation_id="conversation-1",
            message_id="message-1",
        )
    )

    assert len(sql_service.calls) == 3
    assert "CREATE TABLE IF NOT EXISTS audit.qa.validation_sql" in sql_service.calls[0].statement
    assert "ADD COLUMNS (validation_sql_id STRING)" in sql_service.calls[1].statement
    insert_request = sql_service.calls[2]
    assert ":generated_sql" in insert_request.statement
    assert {parameter.name: parameter.value for parameter in insert_request.parameters}["generated_sql"] == "SELECT 1"
    assert result.status == "SAVED"


def test_execute_saved_runs_stored_sql_and_persists_the_result():
    saved_row = [
        "validation-1", "TC1", "main.qa.members", "ABC", "member", "SELECT 1",
        "space-1", "conversation-1", "message-1", "2026-08-31T00:00:00Z", "SAVED",
    ]
    sql_service = MockSQLService(
        responses=[
            SQLExecutionResult(rows=[saved_row]),
            SQLExecutionResult(statement_id="statement-1", status="SUCCEEDED", columns=["result"], rows=[[1]], row_count=1),
        ]
    )
    service = ValidationSQLService(
        sql_service,
        Settings(
            databricks_warehouse_id="warehouse",
            test_case_results_catalog="results",
            test_case_results_schema="audit",
            test_case_results_table_name="execution_results",
        ),
    )

    result = service.execute_saved("validation-1")

    assert sql_service.calls[1].statement == "SELECT 1"
    assert "CREATE TABLE IF NOT EXISTS results.audit.execution_results" in sql_service.calls[2].statement
    assert "INSERT INTO results.audit.execution_results" in sql_service.calls[3].statement
    assert result.rows == [[1]]


def test_get_saved_by_ids_loads_all_requested_definitions_in_one_query():
    saved_rows = [
        [
            "validation-2", "TC2", "main.qa.claims", "ABC", "claim", "SELECT 2",
            "space-1", "conversation-1", "message-2", "2026-08-31T00:00:00Z", "SAVED",
        ],
        [
            "validation-1", "TC1", "main.qa.members", "ABC", "member", "SELECT 1",
            "space-1", "conversation-1", "message-1", "2026-08-31T00:00:00Z", "SAVED",
        ],
    ]
    sql_service = MockSQLService(responses=[SQLExecutionResult(rows=saved_rows)])
    service = ValidationSQLService(sql_service, Settings(databricks_warehouse_id="warehouse"))

    results = service.get_saved_by_ids(["validation-2", "validation-1"])

    assert [result.validation_sql_id for result in results] == ["validation-2", "validation-1"]
    assert len(sql_service.calls) == 1
    assert "IN (:validation_sql_id_0, :validation_sql_id_1)" in sql_service.calls[0].statement
    assert {
        parameter.name: parameter.value for parameter in sql_service.calls[0].parameters
    } == {
        "validation_sql_id_0": "validation-2",
        "validation_sql_id_1": "validation-1",
    }


def test_execute_preloaded_saved_sql_reuses_execution_and_persistence_without_lookup():
    sql_service = MockSQLService(
        responses=[
            SQLExecutionResult(
                statement_id="statement-1",
                status="SUCCEEDED",
                columns=["result"],
                rows=[[1]],
                row_count=1,
                duration_ms=25,
            )
        ]
    )
    service = ValidationSQLService(sql_service, Settings(databricks_warehouse_id="warehouse"))
    saved_sql = ValidationSQL(
        validation_sql_id="validation-1",
        test_case_id="TC1",
        target_table="main.qa.members",
        payor="ABC",
        file_type="member",
        generated_sql="SELECT 1",
        genie_space_id="space-1",
        conversation_id="conversation-1",
        message_id="message-1",
        created_at="2026-08-31T00:00:00Z",
    )

    execution = service.execute_saved_sql(saved_sql, execution_timeout_seconds=60)

    assert sql_service.calls[0].statement == "SELECT 1"
    assert sql_service.calls[0].execution_timeout_seconds == 60
    assert "CREATE TABLE IF NOT EXISTS" in sql_service.calls[1].statement
    assert "INSERT INTO" in sql_service.calls[2].statement
    assert execution.result.rows == [[1]]
    assert execution.duration_ms == 25


def test_execute_preloaded_saved_sql_identifies_result_persistence_failures():
    class FailingPersistenceSQLService(MockSQLService):
        def execute(self, request):
            self.calls.append(request)
            if len(self.calls) == 1:
                return SQLExecutionResult(status="SUCCEEDED", duration_ms=10)
            raise DatabricksSQLExecutionError(None, "Results table unavailable")

    service = ValidationSQLService(
        FailingPersistenceSQLService(),
        Settings(databricks_warehouse_id="warehouse"),
    )
    saved_sql = ValidationSQL(
        validation_sql_id="validation-1",
        test_case_id="TC1",
        target_table="main.qa.members",
        payor="ABC",
        file_type="member",
        generated_sql="SELECT 1",
        genie_space_id="space-1",
        conversation_id="conversation-1",
        message_id="message-1",
        created_at="2026-08-31T00:00:00Z",
    )

    with pytest.raises(ValidationSQLResultPersistenceError, match="Results table unavailable"):
        service.execute_saved_sql(saved_sql)


def test_execute_preloaded_saved_sql_initializes_results_table_once_per_service():
    first_execution = SQLExecutionResult(status="SUCCEEDED", duration_ms=10)
    second_execution = SQLExecutionResult(status="SUCCEEDED", duration_ms=20)
    sql_service = MockSQLService(
        responses=[
            first_execution,
            SQLExecutionResult(status="SUCCEEDED"),
            SQLExecutionResult(status="SUCCEEDED"),
            second_execution,
            SQLExecutionResult(status="SUCCEEDED"),
        ]
    )
    service = ValidationSQLService(sql_service, Settings(databricks_warehouse_id="warehouse"))
    saved_sql_items = [
        ValidationSQL(
            validation_sql_id=f"validation-{index}",
            test_case_id=f"TC{index}",
            target_table="main.qa.members",
            payor="ABC",
            file_type="member",
            generated_sql=f"SELECT {index}",
            genie_space_id="space-1",
            conversation_id="conversation-1",
            message_id=f"message-{index}",
            created_at="2026-08-31T00:00:00Z",
        )
        for index in (1, 2)
    ]

    for saved_sql in saved_sql_items:
        service.execute_saved_sql(saved_sql)

    assert sum("CREATE TABLE IF NOT EXISTS" in call.statement for call in sql_service.calls) == 1
    assert sum("INSERT INTO" in call.statement for call in sql_service.calls) == 2