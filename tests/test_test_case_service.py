from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from data_health_monitor.models.databricks_sql import SQLExecutionResult
from data_health_monitor.models.test_case import TestCase, TestCaseCreate
from data_health_monitor.services.databricks_sql_service import DatabricksSQLExecutionError
from data_health_monitor.services.test_case_service import (
    DuplicateTestCaseError,
    TestCaseNotFoundError,
    TestCaseService,
)


class MockSQLService:
    def __init__(self, responses: list[SQLExecutionResult] | None = None, side_effect: Exception | None = None):
        self.responses = responses or []
        self.side_effect = side_effect
        self.calls = []
        self.response_index = 0

    def execute(self, request: Any) -> SQLExecutionResult:
        self.calls.append(request)
        if self.side_effect:
            raise self.side_effect
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response
        return SQLExecutionResult()


def test_test_case_create_validates():
    """TestCaseCreate should validate required fields."""
    create = TestCaseCreate(
        pipeline="Silver",
        component="date standardization",
        test_scenario="All date columns valid",
        target_object="Silver Table",
        input_data="date strings",
        validation_check="Check formats",
        expected_result="Valid format",
    )
    assert create.pipeline == "Silver"


def test_test_case_id_generated():
    """TestCaseService should generate test_case_id when creating."""
    now = datetime.now(timezone.utc)
    id_response = SQLExecutionResult(
        statement_id="stmt-select-max",
        status="SUCCEEDED",
        columns=["max_num"],
        rows=[],
        row_count=0,
    )
    insert_response = SQLExecutionResult(
        statement_id="stmt-insert",
        status="SUCCEEDED",
        columns=[],
        rows=[],
        row_count=0,
    )

    sql_service = MockSQLService(responses=[id_response, insert_response])
    service = TestCaseService(sql_service=sql_service)

    create = TestCaseCreate(
        pipeline="Silver",
        component="date",
        test_scenario="dates valid",
        target_object="Table",
        input_data="data",
        validation_check="check",
        expected_result="ok",
    )

    result = service.create_test_case(create)

    assert result.test_case_id.startswith("TC")
    assert len(result.test_case_id) == 8


def test_create_test_case_uses_parameterized_insert():
    """create_test_case should pass user values as SQL parameters."""
    id_response = SQLExecutionResult(
        statement_id="stmt-select-max",
        status="SUCCEEDED",
        columns=["max_num"],
        rows=[],
        row_count=0,
    )
    insert_response = SQLExecutionResult(
        statement_id="stmt-insert",
        status="SUCCEEDED",
        columns=[],
        rows=[],
        row_count=0,
    )

    sql_service = MockSQLService(responses=[id_response, insert_response])
    service = TestCaseService(sql_service=sql_service)

    create = TestCaseCreate(
        pipeline="Silver",
        component="date standardization",
        test_scenario="All dates valid",
        target_object="Silver Table",
        input_data="date strings",
        validation_check="Check all formats",
        expected_result="Valid dates",
    )

    service.create_test_case(create)

    # First call is SELECT MAX for ID generation, second is INSERT
    assert len(sql_service.calls) == 2
    insert_call = sql_service.calls[1]
    assert insert_call.statement
    assert ":pipeline" in insert_call.statement
    assert ":component" in insert_call.statement
    assert insert_call.parameters
    param_names = {p.name for p in insert_call.parameters}
    assert "pipeline" in param_names
    assert "component" in param_names
    assert "test_scenario" in param_names


def test_databricks_sql_service_is_called():
    """DatabricksSQLService.execute should be called for create."""
    id_response = SQLExecutionResult(
        statement_id="stmt-select-max",
        status="SUCCEEDED",
        columns=["max_num"],
        rows=[],
        row_count=0,
    )
    insert_response = SQLExecutionResult(
        statement_id="stmt-insert",
        status="SUCCEEDED",
        columns=[],
        rows=[],
        row_count=0,
    )

    sql_service = MockSQLService(responses=[id_response, insert_response])
    service = TestCaseService(sql_service=sql_service)

    create = TestCaseCreate(
        pipeline="Silver",
        component="date",
        test_scenario="dates valid",
        target_object="Table",
        input_data="data",
        validation_check="check",
        expected_result="ok",
    )

    service.create_test_case(create)

    # Both ID generation and INSERT should be called
    assert len(sql_service.calls) == 2


def test_get_test_case_uses_parameterized_select():
    """get_test_case should use SQL parameter for test_case_id."""
    now = datetime.now(timezone.utc)
    response = SQLExecutionResult(
        statement_id="stmt-select",
        status="SUCCEEDED",
        columns=["test_case_id", "pipeline", "component", "test_scenario", "target_object", "input_data", "validation_check", "expected_result", "status", "created_at", "updated_at"],
        rows=[["TC000001", "Silver", "date", "dates valid", "Table", "data", "check", "ok", "ACTIVE", now.isoformat(), now.isoformat()]],
        row_count=1,
    )
    sql_service = MockSQLService(responses=[response])
    service = TestCaseService(sql_service=sql_service)

    result = service.get_test_case("TC000001")

    assert result.test_case_id == "TC000001"
    assert result.pipeline == "Silver"
    assert len(sql_service.calls) == 1
    call = sql_service.calls[0]
    assert ":test_case_id" in call.statement


def test_get_test_case_not_found_raises_error():
    """get_test_case should raise TestCaseNotFoundError if no rows returned."""
    response = SQLExecutionResult(
        statement_id="stmt-select",
        status="SUCCEEDED",
        columns=["test_case_id"],
        rows=[],
        row_count=0,
    )
    sql_service = MockSQLService(responses=[response])
    service = TestCaseService(sql_service=sql_service)

    with pytest.raises(TestCaseNotFoundError) as exc_info:
        service.get_test_case("TC_MISSING")

    assert "TC_MISSING" in str(exc_info.value)


def test_list_test_cases_returns_multiple():
    """list_test_cases should return all active test cases."""
    now = datetime.now(timezone.utc)
    response = SQLExecutionResult(
        statement_id="stmt-list",
        status="SUCCEEDED",
        columns=["test_case_id", "pipeline", "component", "test_scenario", "target_object", "input_data", "validation_check", "expected_result", "status", "created_at", "updated_at"],
        rows=[
            ["TC000001", "Silver", "date", "dates valid", "Table", "data", "check", "ok", "ACTIVE", now.isoformat(), now.isoformat()],
            ["TC000002", "Gold", "join", "joins valid", "Table", "data", "check", "ok", "ACTIVE", now.isoformat(), now.isoformat()],
        ],
        row_count=2,
    )
    sql_service = MockSQLService(responses=[response])
    service = TestCaseService(sql_service=sql_service)

    results = service.list_test_cases()

    assert len(results) == 2
    assert results[0].test_case_id == "TC000001"
    assert results[1].test_case_id == "TC000002"


def test_create_returns_test_case():
    """create_test_case should return TestCase with all fields populated."""
    id_response = SQLExecutionResult(
        statement_id="stmt-select-max",
        status="SUCCEEDED",
        columns=["max_num"],
        rows=[],
        row_count=0,
    )
    insert_response = SQLExecutionResult(
        statement_id="stmt-insert",
        status="SUCCEEDED",
        columns=[],
        rows=[],
        row_count=0,
    )

    sql_service = MockSQLService(responses=[id_response, insert_response])
    service = TestCaseService(sql_service=sql_service)

    create = TestCaseCreate(
        pipeline="Silver",
        component="date",
        test_scenario="dates valid",
        target_object="Table",
        input_data="data",
        validation_check="check",
        expected_result="ok",
    )

    result = service.create_test_case(create)

    assert isinstance(result, TestCase)
    assert result.pipeline == create.pipeline
    assert result.status == "ACTIVE"
    assert result.created_at is not None


def test_list_test_cases_returns_empty_on_sql_error():
    """list_test_cases should return empty list if DatabricksSQLExecutionError occurs."""
    sql_service = MockSQLService(side_effect=DatabricksSQLExecutionError(None, "Table not found"))
    service = TestCaseService(sql_service=sql_service)

    results = service.list_test_cases()

    assert results == []


def test_sql_parameters_include_values():
    """SQL parameters should include user input values."""
    id_response = SQLExecutionResult(
        statement_id="stmt-select-max",
        status="SUCCEEDED",
        columns=["max_num"],
        rows=[],
        row_count=0,
    )
    insert_response = SQLExecutionResult(
        statement_id="stmt-insert",
        status="SUCCEEDED",
        columns=[],
        rows=[],
        row_count=0,
    )

    sql_service = MockSQLService(responses=[id_response, insert_response])
    service = TestCaseService(sql_service=sql_service)

    create = TestCaseCreate(
        pipeline="Gold",
        component="aggregation",
        test_scenario="sums correct",
        target_object="Agg Table",
        input_data="sales data",
        validation_check="sum validation",
        expected_result="totals match",
    )

    service.create_test_case(create)

    # Second call is the INSERT with parameters
    insert_call = sql_service.calls[1]
    param_map = {p.name: p.value for p in insert_call.parameters}
    assert param_map["pipeline"] == "Gold"
    assert param_map["component"] == "aggregation"
    assert param_map["test_scenario"] == "sums correct"
