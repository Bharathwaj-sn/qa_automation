from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings, get_settings
from app.models.databricks_sql import SQLExecutionRequest, SQLExecutionResult, SQLParameter
from app.models.validation_sql import TestCaseResult, ValidationSQL, ValidationSQLCreate
from app.services.databricks_sql_service import DatabricksSQLExecutionError, DatabricksSQLService


class ValidationSQLNotFoundError(RuntimeError):
    pass


class ValidationSQLService:
    def __init__(self, sql_service: DatabricksSQLService, settings: Settings | None = None):
        self.sql_service = sql_service
        self.settings = settings or get_settings()

    @property
    def _table_name(self) -> str:
        return (
            f"{self.settings.validation_sql_catalog}.{self.settings.validation_sql_schema}."
            f"{self.settings.validation_sql_table_name}"
        )

    @property
    def _results_table_name(self) -> str:
        return (
            f"{self.settings.test_case_results_catalog}.{self.settings.test_case_results_schema}."
            f"{self.settings.test_case_results_table_name}"
        )

    def save(self, validation_sql: ValidationSQLCreate) -> ValidationSQL:
        self.initialize_table(self.sql_service, self.settings)
        created_at = datetime.now(timezone.utc)
        validation_sql_id = uuid4().hex
        self.sql_service.execute(
            SQLExecutionRequest(
                statement=f"""
INSERT INTO {self._table_name}
(validation_sql_id, test_case_id, target_table, payor, file_type, generated_sql, genie_space_id, conversation_id, message_id, created_at, status)
VALUES (:validation_sql_id, :test_case_id, :target_table, :payor, :file_type, :generated_sql, :genie_space_id, :conversation_id, :message_id, :created_at, :status)
                """.strip(),
                warehouse_id=self.settings.databricks_warehouse_id or "",
                catalog=self.settings.validation_sql_catalog,
                schema=self.settings.validation_sql_schema,
                parameters=self._parameters(
                    validation_sql_id=validation_sql_id,
                    **validation_sql.model_dump(),
                    created_at=created_at.isoformat(),
                    status="SAVED",
                ),
            )
        )
        return ValidationSQL(
            **validation_sql.model_dump(),
            validation_sql_id=validation_sql_id,
            created_at=created_at,
        )

    def list_saved(self, test_case_id: str | None = None) -> list[ValidationSQL]:
        statement = (
            "SELECT COALESCE(validation_sql_id, message_id), test_case_id, target_table, payor, file_type, generated_sql, "
            f"genie_space_id, conversation_id, message_id, created_at, status FROM {self._table_name}"
        )
        parameters = []
        if test_case_id:
            statement += " WHERE test_case_id = :test_case_id"
            parameters.append(SQLParameter(name="test_case_id", value=test_case_id))
        result = self.sql_service.execute(
            SQLExecutionRequest(
                statement=f"{statement} ORDER BY created_at DESC",
                warehouse_id=self.settings.databricks_warehouse_id or "",
                catalog=self.settings.validation_sql_catalog,
                schema=self.settings.validation_sql_schema,
                parameters=parameters,
            )
        )
        return [
            ValidationSQL(
                validation_sql_id=str(row[0]), test_case_id=str(row[1]), target_table=str(row[2]),
                payor=str(row[3]), file_type=str(row[4]), generated_sql=str(row[5]),
                genie_space_id=str(row[6]), conversation_id=str(row[7]), message_id=str(row[8]),
                created_at=row[9], status=str(row[10]),
            )
            for row in result.rows
        ]

    def execute_saved(self, validation_sql_id: str) -> TestCaseResult:
        saved_sql = next((item for item in self.list_saved() if item.validation_sql_id == validation_sql_id), None)
        if saved_sql is None:
            raise ValidationSQLNotFoundError(f"Saved validation SQL '{validation_sql_id}' was not found.")

        execution = self.sql_service.execute(
            SQLExecutionRequest(
                statement=saved_sql.generated_sql,
                warehouse_id=self.settings.databricks_warehouse_id or "",
                catalog=self.settings.databricks_catalog,
                schema=self.settings.databricks_schema,
            )
        )
        return self._save_result(saved_sql, execution)

    def _save_result(self, saved_sql: ValidationSQL, execution: SQLExecutionResult) -> TestCaseResult:
        self.initialize_results_table(self.sql_service, self.settings)
        result = TestCaseResult(
            validation_sql_id=saved_sql.validation_sql_id,
            test_case_id=saved_sql.test_case_id,
            target_table=saved_sql.target_table,
            payor=saved_sql.payor,
            file_type=saved_sql.file_type,
            statement_id=execution.statement_id,
            execution_status=execution.status,
            row_count=execution.row_count,
            columns=execution.columns,
            rows=execution.rows,
            executed_at=datetime.now(timezone.utc),
        )
        self.sql_service.execute(
            SQLExecutionRequest(
                statement=f"""
INSERT INTO {self._results_table_name}
(validation_sql_id, test_case_id, target_table, payor, file_type, statement_id, execution_status, row_count, columns_json, rows_json, executed_at)
VALUES (:validation_sql_id, :test_case_id, :target_table, :payor, :file_type, :statement_id, :execution_status, :row_count, :columns_json, :rows_json, :executed_at)
                """.strip(),
                warehouse_id=self.settings.databricks_warehouse_id or "",
                catalog=self.settings.databricks_catalog,
                schema=self.settings.databricks_schema,
                parameters=self._parameters(
                    validation_sql_id=result.validation_sql_id,
                    test_case_id=result.test_case_id,
                    target_table=result.target_table,
                    payor=result.payor,
                    file_type=result.file_type,
                    statement_id=result.statement_id or "",
                    execution_status=result.execution_status,
                    row_count=str(result.row_count),
                    columns_json=json.dumps(result.columns),
                    rows_json=json.dumps(result.rows, default=str),
                    executed_at=result.executed_at.isoformat(),
                ),
            )
        )
        return result

    @staticmethod
    def _parameters(**values: str) -> list[SQLParameter]:
        return [SQLParameter(name=name, value=value) for name, value in values.items()]

    @staticmethod
    def initialize_table(sql_service: DatabricksSQLService, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        table_name = (
            f"{settings.validation_sql_catalog}.{settings.validation_sql_schema}."
            f"{settings.validation_sql_table_name}"
        )
        sql_service.execute(
            SQLExecutionRequest(
                statement=f"""
CREATE TABLE IF NOT EXISTS {table_name}
(
    validation_sql_id STRING NOT NULL,
    test_case_id STRING NOT NULL,
    target_table STRING NOT NULL,
    payor STRING NOT NULL,
    file_type STRING NOT NULL,
    generated_sql STRING NOT NULL,
    genie_space_id STRING NOT NULL,
    conversation_id STRING NOT NULL,
    message_id STRING NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status STRING NOT NULL
)
USING DELTA
                """.strip(),
                warehouse_id=settings.databricks_warehouse_id or "",
                catalog=settings.validation_sql_catalog,
                schema=settings.validation_sql_schema,
            )
        )
        try:
            sql_service.execute(
                SQLExecutionRequest(
                    statement=f"ALTER TABLE {table_name} ADD COLUMNS (validation_sql_id STRING)",
                    warehouse_id=settings.databricks_warehouse_id or "",
                    catalog=settings.validation_sql_catalog,
                    schema=settings.validation_sql_schema,
                )
            )
        except DatabricksSQLExecutionError as exc:
            if "already exists" not in str(exc).lower():
                raise

    @staticmethod
    def initialize_results_table(sql_service: DatabricksSQLService, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        table_name = (
            f"{settings.test_case_results_catalog}.{settings.test_case_results_schema}."
            f"{settings.test_case_results_table_name}"
        )
        sql_service.execute(
            SQLExecutionRequest(
                statement=f"""
CREATE TABLE IF NOT EXISTS {table_name}
(
    validation_sql_id STRING NOT NULL,
    test_case_id STRING NOT NULL,
    target_table STRING NOT NULL,
    payor STRING NOT NULL,
    file_type STRING NOT NULL,
    statement_id STRING,
    execution_status STRING NOT NULL,
    row_count BIGINT NOT NULL,
    columns_json STRING NOT NULL,
    rows_json STRING NOT NULL,
    executed_at TIMESTAMP NOT NULL
)
USING DELTA
                """.strip(),
                warehouse_id=settings.databricks_warehouse_id or "",
                catalog=settings.test_case_results_catalog,
                schema=settings.test_case_results_schema,
            )
        )