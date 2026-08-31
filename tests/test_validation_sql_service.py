from __future__ import annotations

from app.config import Settings
from app.models.databricks_sql import SQLExecutionResult
from app.models.validation_sql import ValidationSQLCreate
from app.services.validation_sql_service import ValidationSQLService


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