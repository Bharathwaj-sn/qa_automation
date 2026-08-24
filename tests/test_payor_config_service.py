from __future__ import annotations

import pytest

from app.config import Settings
from app.models.databricks_sql import SQLExecutionResult
from app.services.databricks_sql_service import DatabricksSQLExecutionError
from app.services.payor_config_service import (
    DuplicatePayorConfigError,
    PayorConfigDeserializationError,
    PayorConfigNotFoundError,
    PayorConfigService,
)


COLUMNS = [
    "payor", "file_type", "database_name", "schema_name", "table_name", "container_name",
    "raw_delta_table_name", "silver_delta_table_name", "unique_records_delta_table_name",
    "incremental_records_delta_table_name", "full_load", "silver_schema_name", "sql_pool_table",
    "natural_keys", "not_null_condition_column", "date_standardization_column",
    "timestamp_standardization_column", "filter_conditions", "float_standardization_column",
    "integer_standardization_column", "decimal_standardization_column", "client_active",
    "log_container_name", "log_folder_name", "recon_delta_table_name", "pipeline_history_delta_table_name",
    "pipeline_error_delta_table_name", "folder_name", "raw_folder_name", "silver_folder_name",
    "archive_folder_name", "error_folder_name", "nk_null_table_name", "source_folder_name",
    "master_schema_folder_name", "master_schema_filename", "header_column_names", "12_month_rolling",
    "col_with_spaces", "12_month_rolling_key", "ingest_new_columns", "business_condition",
    "excluded_files", "delimiter", "excel_tab_name", "rolling_period_years", "regex_function",
    "skiprows", "insert_deactivated_records", "excluded_columns", "sorting_columns", "threshold",
    "mbr_id_col", "delimited_text_file",
]


def make_row(payor: str = "ABC", table_name: str = "eligibility") -> list[object]:
    values = {column: f"{column}-value" for column in COLUMNS}
    values.update({
        "payor": payor, "table_name": table_name, "natural_keys": ["member_id"],
        "not_null_condition_column": ["member_id"], "date_standardization_column": ["birth_date"],
        "timestamp_standardization_column": ["created_at"], "filter_conditions": ["active = true"],
        "float_standardization_column": ["amount"], "integer_standardization_column": ["count"],
        "decimal_standardization_column": ["rate"], "client_active": 1,
        "header_column_names": ["member_id", "name"], "excluded_files": [{"stringField": "test.csv", "booleanField": True}],
        "rolling_period_years": 12, "regex_function": {"pattern": "^ABC", "columns": ["member_id"]},
        "skiprows": 2, "excluded_columns": ["internal_note"], "sorting_columns": ["member_id"],
    })
    return [values[column] for column in COLUMNS]


def replace_row_values(row: list[object], values: dict[str, object]) -> list[object]:
    return [values.get(column, value) for column, value in zip(COLUMNS, row)]


class MockSQLService:
    def __init__(self, result: SQLExecutionResult | None = None, error: Exception | None = None):
        self.result = result or SQLExecutionResult()
        self.error = error
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result


def service_for(result: SQLExecutionResult | None = None, error: Exception | None = None):
    sql_service = MockSQLService(result=result, error=error)
    settings = Settings(payor_config_catalog="configs", payor_config_schema="control", payor_config_table_name="payor_config", databricks_warehouse_id="warehouse")
    return PayorConfigService(sql_service=sql_service, settings=settings), sql_service


def test_get_config_returns_complete_typed_config_and_parameterized_request():
    service, sql_service = service_for(SQLExecutionResult(columns=COLUMNS, rows=[make_row()]))

    config = service.get_config("ABC", "eligibility")

    assert config.payor == "ABC"
    assert config.natural_keys == ["member_id"]
    assert config.excluded_files[0].string_field == "test.csv"
    assert config.regex_function is not None and config.regex_function.columns == ["member_id"]
    assert config.rolling_12_month == "12_month_rolling-value"
    assert config.model_dump(by_alias=True)["12_month_rolling"] == "12_month_rolling-value"
    assert len(type(config).model_fields) == 54
    request = sql_service.calls[0]
    assert ":payor" in request.statement and ":table_name" in request.statement
    assert "client_active = 1" in request.statement and "SELECT *" not in request.statement
    assert {parameter.name: parameter.value for parameter in request.parameters} == {"payor": "ABC", "table_name": "eligibility"}


def test_parse_json_list_handles_json_strings_empty_arrays_and_existing_lists():
    assert PayorConfigService._parse_json_list('["member_id"]') == ["member_id"]
    assert PayorConfigService._parse_json_list("[]") == []
    assert PayorConfigService._parse_json_list(["member_id"]) == ["member_id"]
    assert PayorConfigService._parse_json_list(None) == []


def test_parse_json_object_handles_json_strings_and_empty_structs():
    assert PayorConfigService._parse_json_object('{"pattern":"^ABC","columns":["member_id"]}') == {
        "pattern": "^ABC",
        "columns": ["member_id"],
    }
    assert PayorConfigService._parse_json_object("{}") == {}
    assert PayorConfigService._parse_json_object(None) is None


def test_parse_json_helpers_raise_clear_error_for_invalid_json():
    with pytest.raises(PayorConfigDeserializationError, match="Invalid JSON array"):
        PayorConfigService._parse_json_list("not-json")
    with pytest.raises(PayorConfigDeserializationError, match="Invalid JSON object"):
        PayorConfigService._parse_json_object("not-json")


def test_get_config_normalizes_all_json_encoded_complex_columns():
    list_fields = [
        "natural_keys", "not_null_condition_column", "date_standardization_column",
        "timestamp_standardization_column", "filter_conditions", "float_standardization_column",
        "integer_standardization_column", "decimal_standardization_column", "header_column_names",
        "excluded_columns", "sorting_columns",
    ]
    row = replace_row_values(
        make_row(),
        {
            **{field_name: '["member_id"]' for field_name in list_fields},
            "filter_conditions": "[]",
            "excluded_files": '[{"stringField":"ignored.csv","booleanField":true}]',
            "regex_function": '{"pattern":"","columns":[]}',
        },
    )
    service, _ = service_for(SQLExecutionResult(columns=COLUMNS, rows=[row]))

    config = service.get_config("ABC", "eligibility")

    assert len(COLUMNS) == len(type(config).model_fields) == 54
    assert config.natural_keys == ["member_id"]
    assert config.filter_conditions == []
    assert config.excluded_files[0].string_field == "ignored.csv"
    assert config.excluded_files[0].boolean_field is True
    assert config.regex_function is not None
    assert config.regex_function.pattern == ""
    assert config.regex_function.columns == []
    assert config.rolling_12_month == "12_month_rolling-value"
    assert config.rolling_12_month_key == "12_month_rolling_key-value"
    assert config.client_active == 1
    assert config.rolling_period_years == 12


def test_get_config_raises_not_found_for_no_rows():
    service, _ = service_for(SQLExecutionResult(columns=COLUMNS, rows=[]))
    with pytest.raises(PayorConfigNotFoundError):
        service.get_config("ABC", "eligibility")


def test_get_config_raises_integrity_error_for_duplicate_rows():
    service, _ = service_for(SQLExecutionResult(columns=COLUMNS, rows=[make_row(), make_row()]))
    with pytest.raises(DuplicatePayorConfigError):
        service.get_config("ABC", "eligibility")


def test_get_config_propagates_sql_error():
    service, _ = service_for(error=DatabricksSQLExecutionError(None, "warehouse unavailable"))
    with pytest.raises(DatabricksSQLExecutionError):
        service.get_config("ABC", "eligibility")


def test_list_configs_returns_multiple_and_uses_payor_parameter():
    service, sql_service = service_for(SQLExecutionResult(columns=COLUMNS, rows=[make_row("ABC", "eligibility"), make_row("ABC", "claims")]))

    configs = service.list_configs("ABC")

    assert [config.table_name for config in configs] == ["eligibility", "claims"]
    assert sql_service.calls[0].parameters[0].name == "payor"
    assert sql_service.calls[0].parameters[0].value == "ABC"
    assert ":table_name" not in sql_service.calls[0].statement


def test_list_configs_returns_empty_list_when_no_rows_exist():
    service, _ = service_for(SQLExecutionResult(columns=COLUMNS, rows=[]))
    assert service.list_configs("ABC") == []


def test_list_payors_and_table_configs_use_parameterized_filters():
    service, sql_service = service_for(SQLExecutionResult(columns=["payor"], rows=[["ABC"], ["XYZ"]]))

    assert service.list_payors() == ["ABC", "XYZ"]
    assert "SELECT DISTINCT payor" in sql_service.calls[0].statement

    sql_service.result = SQLExecutionResult(columns=COLUMNS, rows=[make_row()])
    configs = service.list_configs_for_table("eligibility", "silver")

    assert configs[0].table_name == "eligibility"
    request = sql_service.calls[1]
    assert ":table_name" in request.statement and ":schema_name" in request.statement
    assert {parameter.name: parameter.value for parameter in request.parameters} == {
        "table_name": "eligibility",
        "schema_name": "silver",
    }