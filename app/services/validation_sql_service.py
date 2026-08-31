from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.models.databricks_sql import SQLExecutionRequest, SQLParameter
from app.models.validation_sql import ValidationSQL, ValidationSQLCreate
from app.services.databricks_sql_service import DatabricksSQLService


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

    def save(self, validation_sql: ValidationSQLCreate) -> ValidationSQL:
        self.initialize_table(self.sql_service, self.settings)
        created_at = datetime.now(timezone.utc)
        statement = f"""
INSERT INTO {self._table_name}
(test_case_id, target_table, payor, file_type, generated_sql, genie_space_id, conversation_id, message_id, created_at, status)
VALUES (:test_case_id, :target_table, :payor, :file_type, :generated_sql, :genie_space_id, :conversation_id, :message_id, :created_at, :status)
        """.strip()
        self.sql_service.execute(
            SQLExecutionRequest(
                statement=statement,
                warehouse_id=self.settings.databricks_warehouse_id or "",
                catalog=self.settings.validation_sql_catalog,
                schema=self.settings.validation_sql_schema,
                parameters=[
                    SQLParameter(name="test_case_id", value=validation_sql.test_case_id),
                    SQLParameter(name="target_table", value=validation_sql.target_table),
                    SQLParameter(name="payor", value=validation_sql.payor),
                    SQLParameter(name="file_type", value=validation_sql.file_type),
                    SQLParameter(name="generated_sql", value=validation_sql.generated_sql),
                    SQLParameter(name="genie_space_id", value=validation_sql.genie_space_id),
                    SQLParameter(name="conversation_id", value=validation_sql.conversation_id),
                    SQLParameter(name="message_id", value=validation_sql.message_id),
                    SQLParameter(name="created_at", value=created_at.isoformat()),
                    SQLParameter(name="status", value="SAVED"),
                ],
            )
        )
        return ValidationSQL(**validation_sql.model_dump(), created_at=created_at)

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