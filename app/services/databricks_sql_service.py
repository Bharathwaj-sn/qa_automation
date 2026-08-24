from __future__ import annotations

import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem


from app.config import Settings, get_settings
from app.models.databricks_sql import SQLExecutionRequest, SQLExecutionResult, SQLParameter


class DatabricksSQLExecutionError(RuntimeError):
    def __init__(self, statement_id: str | None, message: str, original_exception: Exception | None = None):
        self.statement_id = statement_id
        self.message = message
        super().__init__(message)
        if original_exception is not None:
            self.__cause__ = original_exception


class DatabricksSQLService:
    def __init__(
        self,
        client: WorkspaceClient | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()

        if client:
            self.client = client
        elif self.settings.databricks_profile:
            self.client = WorkspaceClient(profile=self.settings.databricks_profile)
        else:
            self.client = WorkspaceClient()

    @staticmethod
    def _status_value(status: Any) -> str:
        if status is None:
            return "UNKNOWN"
        state = getattr(status, "state", None)
        if state is None:
            return "UNKNOWN"
        if hasattr(state, "value"):
            return str(state.value)
        return str(state)

    @staticmethod
    def _error_message(status: Any) -> str | None:
        if status is None:
            return None
        error = getattr(status, "error", None)
        if error is None:
            return None
        return getattr(error, "message", None) or str(error)

    @staticmethod
    def _parameter_payload(
        parameters: list[SQLParameter],
    ) -> list[StatementParameterListItem]:
        return [
            StatementParameterListItem(
                name=parameter.name,
                value=parameter.value,
                type=parameter.type or "STRING",
            )
            for parameter in parameters
        ]

    @staticmethod
    def _column_names(response: Any) -> list[str]:
        manifest = getattr(response, "manifest", None)
        schema = getattr(manifest, "schema", None) if manifest is not None else None
        columns = getattr(schema, "columns", None) or []
        return [str(getattr(column, "name", "")) for column in columns if getattr(column, "name", None)]

    @staticmethod
    def _normalize_result(response: Any) -> SQLExecutionResult:
        status_value = DatabricksSQLService._status_value(getattr(response, "status", None))
        result_data = getattr(response, "result", None)
        rows = list(getattr(result_data, "data_array", None) or [])
        row_count = getattr(result_data, "row_count", None)
        if row_count is None:
            row_count = len(rows)

        return SQLExecutionResult(
            statement_id=getattr(response, "statement_id", None),
            status=status_value,
            columns=DatabricksSQLService._column_names(response),
            rows=rows,
            row_count=row_count,
        )

    def _wait_for_completion(self, response: Any) -> Any:
        current = response
        while True:
            status = getattr(current, "status", None)
            state = self._status_value(status)
            if state not in {"PENDING", "RUNNING"}:
                error_message = self._error_message(status)
                if state in {"FAILED", "CANCELED", "CLOSED"} and error_message:
                    raise DatabricksSQLExecutionError(
                        statement_id=getattr(current, "statement_id", None),
                        message=error_message,
                    )
                return current

            statement_id = getattr(current, "statement_id", None)
            if not statement_id:
                return current

            current = self.client.statement_execution.get_statement(statement_id)
            time.sleep(0.25)

    def execute(self, request: SQLExecutionRequest) -> SQLExecutionResult:
        started_at = time.perf_counter()
        try:
            response = self.client.statement_execution.execute_statement(
                statement=request.statement,
                warehouse_id=request.warehouse_id,
                catalog=request.catalog,
                schema=request.schema,
                parameters=self._parameter_payload(request.parameters),
                wait_timeout=request.wait_timeout,
            )

            response = self._wait_for_completion(response)
            result = self._normalize_result(response)
            result.duration_ms = int((time.perf_counter() - started_at) * 1000)
            return result
        except DatabricksSQLExecutionError:
            raise
        except Exception as exc:
            raise DatabricksSQLExecutionError(
                statement_id=None,
                message=str(exc),
                original_exception=exc,
            ) from exc
