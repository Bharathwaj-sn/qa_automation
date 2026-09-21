from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings, get_settings
from app.models.batch_execution import (
    BatchExecutionRequest,
    BatchExecutionResult,
    BatchQueryExecutionResult,
)
from app.models.validation_sql import ValidationSQL
from app.services.databricks_sql_service import (
    DatabricksSQLExecutionError,
    DatabricksSQLTimeoutError,
)
from app.services.validation_sql_service import (
    ValidationSQLNotFoundError,
    ValidationSQLResultPersistenceError,
    ValidationSQLService,
)


class BatchExecutionService:
    def __init__(
        self,
        validation_sql_service: ValidationSQLService,
        settings: Settings | None = None,
    ):
        self.validation_sql_service = validation_sql_service
        self.settings = settings or get_settings()

    def execute_batch(self, request: BatchExecutionRequest) -> BatchExecutionResult:
        started_at = datetime.now(timezone.utc)
        started_timer = time.perf_counter()
        batch_id = uuid4().hex
        saved_sql_items = self.validation_sql_service.get_saved_by_ids(request.validation_sql_ids)
        saved_sql_by_id = {item.validation_sql_id: item for item in saved_sql_items}
        missing_ids = [
            validation_sql_id
            for validation_sql_id in request.validation_sql_ids
            if validation_sql_id not in saved_sql_by_id
        ]
        if missing_ids:
            missing = ", ".join(f"'{validation_sql_id}'" for validation_sql_id in missing_ids)
            raise ValidationSQLNotFoundError(f"Saved validation SQL was not found for IDs: {missing}.")

        query_results: list[BatchQueryExecutionResult] = []
        batch_error: str | None = None
        batch_deadline = time.monotonic() + self.settings.batch_execution_timeout_seconds

        for index, validation_sql_id in enumerate(request.validation_sql_ids):
            saved_sql = saved_sql_by_id[validation_sql_id]
            execution_order = index + 1
            remaining_seconds = batch_deadline - time.monotonic()
            if remaining_seconds <= 0:
                batch_error = "Batch execution timeout reached before all queries started."
                query_results.extend(
                    self._skipped_results(
                        request.validation_sql_ids[index:],
                        saved_sql_by_id,
                        execution_order,
                        batch_error,
                    )
                )
                break

            query_started = time.perf_counter()
            query_timeout = min(self.settings.sql_execution_timeout_seconds, remaining_seconds)
            try:
                execution = self.validation_sql_service.execute_saved_sql(
                    saved_sql,
                    execution_timeout_seconds=query_timeout,
                )
                if execution.result.execution_status != "SUCCEEDED":
                    query_results.append(
                        BatchQueryExecutionResult(
                            validation_sql=saved_sql,
                            execution_order=execution_order,
                            status="FAILED",
                            duration_ms=execution.duration_ms,
                            statement_id=execution.result.statement_id,
                            result=execution.result,
                            error=(
                                "Statement execution ended with status "
                                f"{execution.result.execution_status}."
                            ),
                        )
                    )
                    continue

                query_results.append(
                    BatchQueryExecutionResult(
                        validation_sql=saved_sql,
                        execution_order=execution_order,
                        status="SUCCEEDED",
                        duration_ms=execution.duration_ms,
                        statement_id=execution.result.statement_id,
                        result=execution.result,
                    )
                )
            except ValidationSQLResultPersistenceError as exc:
                batch_error = f"Batch execution stopped because a query result could not be persisted: {exc}"
                query_results.append(
                    self._failed_result(
                        saved_sql,
                        execution_order,
                        query_started,
                        str(exc),
                        exc.statement_id,
                    )
                )
                query_results.extend(
                    self._skipped_results(
                        request.validation_sql_ids[index + 1:],
                        saved_sql_by_id,
                        execution_order + 1,
                        "Skipped because result persistence failed.",
                    )
                )
                break
            except DatabricksSQLTimeoutError as exc:
                query_results.append(
                    self._failed_result(
                        saved_sql,
                        execution_order,
                        query_started,
                        str(exc),
                        exc.statement_id,
                    )
                )
                if not exc.cancellation_confirmed:
                    batch_error = str(exc)
                    query_results.extend(
                        self._skipped_results(
                            request.validation_sql_ids[index + 1:],
                            saved_sql_by_id,
                            execution_order + 1,
                            "Skipped because cancellation of the timed-out query was not confirmed.",
                        )
                    )
                    break
            except DatabricksSQLExecutionError as exc:
                query_results.append(
                    self._failed_result(
                        saved_sql,
                        execution_order,
                        query_started,
                        str(exc),
                        exc.statement_id,
                    )
                )
            except Exception as exc:
                batch_error = f"Batch execution stopped after an unexpected error: {exc}"
                query_results.append(
                    self._failed_result(saved_sql, execution_order, query_started, str(exc))
                )
                query_results.extend(
                    self._skipped_results(
                        request.validation_sql_ids[index + 1:],
                        saved_sql_by_id,
                        execution_order + 1,
                        "Skipped because batch orchestration stopped unexpectedly.",
                    )
                )
                break

        succeeded_count = sum(result.status == "SUCCEEDED" for result in query_results)
        failed_count = sum(result.status == "FAILED" for result in query_results)
        skipped_count = sum(result.status == "SKIPPED" for result in query_results)
        if skipped_count:
            status = "FAILED"
        elif failed_count:
            status = "COMPLETED_WITH_FAILURES"
        else:
            status = "SUCCEEDED"

        completed_at = datetime.now(timezone.utc)
        return BatchExecutionResult(
            batch_id=batch_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=int((time.perf_counter() - started_timer) * 1000),
            total_count=len(request.validation_sql_ids),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            query_results=query_results,
            error=batch_error,
        )

    @staticmethod
    def _failed_result(
        saved_sql: ValidationSQL,
        execution_order: int,
        started_timer: float,
        error: str,
        statement_id: str | None = None,
    ) -> BatchQueryExecutionResult:
        return BatchQueryExecutionResult(
            validation_sql=saved_sql,
            execution_order=execution_order,
            status="FAILED",
            duration_ms=int((time.perf_counter() - started_timer) * 1000),
            statement_id=statement_id,
            error=error,
        )

    @staticmethod
    def _skipped_results(
        validation_sql_ids: list[str],
        saved_sql_by_id: dict[str, ValidationSQL],
        first_execution_order: int,
        error: str,
    ) -> list[BatchQueryExecutionResult]:
        return [
            BatchQueryExecutionResult(
                validation_sql=saved_sql_by_id[validation_sql_id],
                execution_order=first_execution_order + offset,
                status="SKIPPED",
                duration_ms=0,
                error=error,
            )
            for offset, validation_sql_id in enumerate(validation_sql_ids)
        ]