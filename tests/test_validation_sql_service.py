from __future__ import annotations

from app.config import Settings
from app.models.databricks_sql import SQLExecutionResult
from app.models.validation_sql import ValidationSQLCreate
from app.services.validation_sql_service import ValidationSQLService


class MockSQLService:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return SQLExecutionResult(status="SUCCEEDED")


def test_save_initializes_table_and_uses_parameterized_insert():
    sql_service = MockSQLService()
    settings = Settings(
        validation_sql_catalog="audit",
        validation_sql_schema="qa",
        validation_sql_table_name="validation_sql",
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

    assert len(sql_service.calls) == 2
    assert "CREATE TABLE IF NOT EXISTS audit.qa.validation_sql" in sql_service.calls[0].statement
    insert_request = sql_service.calls[1]
    assert ":generated_sql" in insert_request.statement
    assert {parameter.name: parameter.value for parameter in insert_request.parameters}["generated_sql"] == "SELECT 1"
    assert result.status == "SAVED"