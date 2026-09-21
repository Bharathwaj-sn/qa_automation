from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.models.batch_execution import BatchExecutionRequest
from app.models.validation_sql import SavedSQLExecutionResult, TestCaseResult, ValidationSQL
from app.services.batch_execution_service import BatchExecutionService
from app.services.databricks_sql_service import (
    DatabricksSQLExecutionError,
    DatabricksSQLTimeoutError,
)
from app.services.validation_sql_service import (
    ValidationSQLNotFoundError,
    ValidationSQLResultPersistenceError,
)


def make_saved_sql(validation_sql_id: str) -> ValidationSQL:
    return ValidationSQL(
        validation_sql_id=validation_sql_id,
        test_case_id=f"TC-{validation_sql_id}",
        target_table=f"main.qa.{validation_sql_id}",
        payor="ABC",
        file_type="member",
        generated_sql=f"SELECT '{validation_sql_id}'",
        genie_space_id="space-1",
        conversation_id="conversation-1",
        message_id=f"message-{validation_sql_id}",
        created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )


def make_success(saved_sql: ValidationSQL, duration_ms: int = 25) -> SavedSQLExecutionResult:
    return SavedSQLExecutionResult(
        result=TestCaseResult(
            validation_sql_id=saved_sql.validation_sql_id,
            test_case_id=saved_sql.test_case_id,
            target_table=saved_sql.target_table,
            payor=saved_sql.payor,
            file_type=saved_sql.file_type,
            statement_id=f"statement-{saved_sql.validation_sql_id}",
            execution_status="SUCCEEDED",
            row_count=1,
            columns=["result"],
            rows=[[saved_sql.validation_sql_id]],
            executed_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        ),
        duration_ms=duration_ms,
    )


class FakeValidationSQLService:
    def __init__(self, saved_sql_items, outcomes=None):
        self.saved_sql_items = saved_sql_items
        self.outcomes = outcomes or {}
        self.loaded_ids = []
        self.executed_ids = []
        self.execution_timeouts = []

    def get_saved_by_ids(self, validation_sql_ids):
        self.loaded_ids.append(list(validation_sql_ids))
        requested = set(validation_sql_ids)
        return [item for item in self.saved_sql_items if item.validation_sql_id in requested]

    def execute_saved_sql(self, saved_sql, execution_timeout_seconds=None):
        self.executed_ids.append(saved_sql.validation_sql_id)
        self.execution_timeouts.append(execution_timeout_seconds)
        outcome = self.outcomes.get(saved_sql.validation_sql_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or make_success(saved_sql)


def make_service(ids, outcomes=None):
    validation_service = FakeValidationSQLService([make_saved_sql(item_id) for item_id in ids], outcomes)
    service = BatchExecutionService(
        validation_service,
        Settings(sql_execution_timeout_seconds=60, batch_execution_timeout_seconds=300),
    )
    return service, validation_service


@pytest.mark.parametrize("validation_sql_ids", [["validation-1"], ["validation-1", "validation-2"], ["validation-1", "validation-2", "validation-3"]])
def test_batch_executes_one_two_or_three_queries_in_request_order(validation_sql_ids):
    service, validation_service = make_service(list(reversed(validation_sql_ids)))

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.loaded_ids == [validation_sql_ids]
    assert validation_service.executed_ids == validation_sql_ids
    assert [item.validation_sql.validation_sql_id for item in result.query_results] == validation_sql_ids
    assert [item.execution_order for item in result.query_results] == list(range(1, len(validation_sql_ids) + 1))
    assert result.status == "SUCCEEDED"
    assert result.succeeded_count == len(validation_sql_ids)
    assert result.failed_count == 0
    assert result.skipped_count == 0


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_batch_continues_when_first_middle_or_last_query_fails(failed_index):
    validation_sql_ids = ["validation-1", "validation-2", "validation-3"]
    failed_id = validation_sql_ids[failed_index]
    outcomes = {failed_id: DatabricksSQLExecutionError("statement-failed", "Invalid SQL")}
    service, validation_service = make_service(validation_sql_ids, outcomes)

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == validation_sql_ids
    assert [item.status for item in result.query_results][failed_index] == "FAILED"
    assert result.status == "COMPLETED_WITH_FAILURES"
    assert result.succeeded_count == 2
    assert result.failed_count == 1
    assert result.skipped_count == 0
    assert result.query_results[failed_index].error == "Invalid SQL"
    assert result.query_results[failed_index].statement_id == "statement-failed"


def test_batch_preserves_duration_from_successful_execution():
    saved_sql = make_saved_sql("validation-1")
    service = BatchExecutionService(
        FakeValidationSQLService([saved_sql], {saved_sql.validation_sql_id: make_success(saved_sql, 321)}),
        Settings(sql_execution_timeout_seconds=60, batch_execution_timeout_seconds=300),
    )

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=[saved_sql.validation_sql_id]))

    assert result.query_results[0].duration_ms == 321


def test_batch_rejects_unknown_ids_before_executing_any_query():
    service, validation_service = make_service(["validation-1"])

    with pytest.raises(ValidationSQLNotFoundError, match="'validation-missing'"):
        service.execute_batch(
            BatchExecutionRequest(validation_sql_ids=["validation-1", "validation-missing"])
        )

    assert validation_service.executed_ids == []


def test_batch_continues_after_confirmed_query_timeout():
    validation_sql_ids = ["validation-1", "validation-2"]
    outcomes = {
        "validation-1": DatabricksSQLTimeoutError(
            "statement-timeout",
            "Statement timed out.",
            cancellation_confirmed=True,
        )
    }
    service, validation_service = make_service(validation_sql_ids, outcomes)

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == validation_sql_ids
    assert [item.status for item in result.query_results] == ["FAILED", "SUCCEEDED"]
    assert result.query_results[0].statement_id == "statement-timeout"
    assert result.status == "COMPLETED_WITH_FAILURES"


def test_batch_skips_remaining_queries_when_timeout_cancellation_is_unconfirmed():
    validation_sql_ids = ["validation-1", "validation-2", "validation-3"]
    outcomes = {
        "validation-1": DatabricksSQLTimeoutError(
            "statement-timeout",
            "Cancellation could not be confirmed.",
            cancellation_confirmed=False,
        )
    }
    service, validation_service = make_service(validation_sql_ids, outcomes)

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == ["validation-1"]
    assert [item.status for item in result.query_results] == ["FAILED", "SKIPPED", "SKIPPED"]
    assert result.status == "FAILED"
    assert result.skipped_count == 2


def test_batch_preserves_completed_results_after_unexpected_orchestration_failure():
    validation_sql_ids = ["validation-1", "validation-2", "validation-3"]
    service, validation_service = make_service(
        validation_sql_ids,
        {"validation-2": RuntimeError("Result persistence unavailable")},
    )

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == ["validation-1", "validation-2"]
    assert [item.status for item in result.query_results] == ["SUCCEEDED", "FAILED", "SKIPPED"]
    assert result.status == "FAILED"
    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert result.skipped_count == 1
    assert "Result persistence unavailable" in (result.error or "")


def test_batch_stops_after_result_persistence_failure():
    validation_sql_ids = ["validation-1", "validation-2", "validation-3"]
    service, validation_service = make_service(
        validation_sql_ids,
        {
            "validation-2": ValidationSQLResultPersistenceError(
                None,
                "Results table unavailable",
            )
        },
    )

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == ["validation-1", "validation-2"]
    assert [item.status for item in result.query_results] == ["SUCCEEDED", "FAILED", "SKIPPED"]
    assert result.status == "FAILED"
    assert "could not be persisted" in (result.error or "")


def test_batch_marks_all_queries_skipped_when_batch_deadline_is_reached(monkeypatch):
    validation_sql_ids = ["validation-1", "validation-2"]
    service, validation_service = make_service(validation_sql_ids)
    monotonic_values = iter([0.0, 301.0])
    monkeypatch.setattr("app.services.batch_execution_service.time.monotonic", lambda: next(monotonic_values))

    result = service.execute_batch(BatchExecutionRequest(validation_sql_ids=validation_sql_ids))

    assert validation_service.executed_ids == []
    assert [item.status for item in result.query_results] == ["SKIPPED", "SKIPPED"]
    assert result.status == "FAILED"
    assert result.failed_count == 0
    assert result.skipped_count == 2