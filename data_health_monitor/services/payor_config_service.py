from __future__ import annotations

import json
from typing import Any

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.databricks_sql import SQLExecutionRequest, SQLParameter
from data_health_monitor.models.payor_config import ExcludedFile, PayorConfig, RegexFunction
from data_health_monitor.services.databricks_sql_service import DatabricksSQLService


class PayorConfigNotFoundError(RuntimeError):
    def __init__(self, payor: str, file_type: str):
        super().__init__(f"No active payor configuration found for '{payor}' and file type '{file_type}'.")


class DuplicatePayorConfigError(RuntimeError):
    def __init__(self, payor: str, file_type: str):
        super().__init__(f"Multiple active payor configurations found for '{payor}' and file type '{file_type}'.")


class PayorConfigDeserializationError(RuntimeError):
    pass


class PayorConfigService:
    _LIST_FIELDS = (
        "natural_keys",
        "not_null_condition_column",
        "date_standardization_column",
        "timestamp_standardization_column",
        "filter_conditions",
        "float_standardization_column",
        "integer_standardization_column",
        "decimal_standardization_column",
        "header_column_names",
        "excluded_columns",
        "sorting_columns",
    )

    _SELECT_COLUMNS = """payor,
file_type,
database_name,
schema_name,
table_name,
container_name,
raw_delta_table_name,
silver_delta_table_name,
unique_records_delta_table_name,
incremental_records_delta_table_name,
full_load,
silver_schema_name,
sql_pool_table,
natural_keys,
not_null_condition_column,
date_standardization_column,
timestamp_standardization_column,
filter_conditions,
float_standardization_column,
integer_standardization_column,
decimal_standardization_column,
client_active,
log_container_name,
log_folder_name,
recon_delta_table_name,
pipeline_history_delta_table_name,
pipeline_error_delta_table_name,
folder_name,
raw_folder_name,
silver_folder_name,
archive_folder_name,
error_folder_name,
nk_null_table_name,
source_folder_name,
master_schema_folder_name,
master_schema_filename,
header_column_names,
`12_month_rolling`,
col_with_spaces,
`12_month_rolling_key`,
ingest_new_columns,
business_condition,
excluded_files,
delimiter,
excel_tab_name,
rolling_period_years,
regex_function,
skiprows,
insert_deactivated_records,
excluded_columns,
sorting_columns,
threshold,
mbr_id_col,
delimited_text_file"""

    def __init__(self, sql_service: DatabricksSQLService, settings: Settings | None = None):
        self.sql_service = sql_service
        self.settings = settings or get_settings()

    @property
    def _table_name(self) -> str:
        return (
            f"{self.settings.payor_config_catalog}."
            f"{self.settings.payor_config_schema}."
            f"{self.settings.payor_config_table_name}"
        )

    def _request(self, statement: str, parameters: list[SQLParameter]) -> SQLExecutionRequest:
        return SQLExecutionRequest(
            statement=statement,
            warehouse_id=self.settings.databricks_warehouse_id or "",
            catalog=self.settings.payor_config_catalog,
            schema_name=self.settings.payor_config_schema,
            parameters=parameters,
        )

    @staticmethod
    def _parse_json_list(value: Any) -> list[Any]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            raise PayorConfigDeserializationError(f"Expected a JSON array or list, got {type(value).__name__}.")
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError as error:
            raise PayorConfigDeserializationError("Invalid JSON array in payor configuration.") from error
        if parsed_value is None:
            return []
        if not isinstance(parsed_value, list):
            raise PayorConfigDeserializationError("Expected a JSON array in payor configuration.")
        return parsed_value

    @staticmethod
    def _parse_json_object(value: Any) -> dict[str, Any] | None:
        if value is None or value == "":
            return None
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            raise PayorConfigDeserializationError(f"Expected a JSON object or dict, got {type(value).__name__}.")
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError as error:
            raise PayorConfigDeserializationError("Invalid JSON object in payor configuration.") from error
        if parsed_value is None:
            return None
        if not isinstance(parsed_value, dict):
            raise PayorConfigDeserializationError("Expected a JSON object in payor configuration.")
        return parsed_value

    @classmethod
    def _row_to_config(cls, columns: list[str], row: list[Any]) -> PayorConfig:
        values = dict(zip(columns, row))
        for field_name in cls._LIST_FIELDS:
            values[field_name] = cls._parse_json_list(values.get(field_name))

        excluded_files = cls._parse_json_list(values.get("excluded_files"))
        values["excluded_files"] = [ExcludedFile.model_validate(item) for item in excluded_files]

        regex_function = cls._parse_json_object(values.get("regex_function"))
        values["regex_function"] = (
            RegexFunction.model_validate(regex_function) if regex_function is not None else None
        )
        return PayorConfig.model_validate(values)

    def get_config(self, payor: str, file_type: str) -> PayorConfig:
        result = self.sql_service.execute(
            self._request(
                f"SELECT {self._SELECT_COLUMNS}\nFROM {self._table_name}\n"
                "WHERE payor = :payor AND file_type = :file_type AND client_active = 1",
                [SQLParameter(name="payor", value=payor), SQLParameter(name="file_type", value=file_type)],
            )
        )
        if not result.rows:
            raise PayorConfigNotFoundError(payor, file_type)
        if len(result.rows) > 1:
            raise DuplicatePayorConfigError(payor, file_type)
        return self._row_to_config(result.columns, result.rows[0])

    def list_configs(self, payor: str) -> list[PayorConfig]:
        result = self.sql_service.execute(
            self._request(
                f"SELECT {self._SELECT_COLUMNS}\nFROM {self._table_name}\n"
                "WHERE payor = :payor AND client_active = 1",
                [SQLParameter(name="payor", value=payor)],
            )
        )
        return [self._row_to_config(result.columns, row) for row in result.rows]

    def list_payors(self) -> list[str]:
        result = self.sql_service.execute(
            self._request(
                f"SELECT DISTINCT payor\nFROM {self._table_name}\n"
                "WHERE client_active = 1\nORDER BY payor",
                [],
            )
        )
        return [str(row[0]) for row in result.rows if row and row[0] is not None]

    def list_file_types(self, payor: str) -> list[str]:
        result = self.sql_service.execute(
            self._request(
                f"SELECT DISTINCT file_type\nFROM {self._table_name}\n"
                "WHERE payor = :payor AND client_active = 1\nORDER BY file_type",
                [SQLParameter(name="payor", value=payor)],
            )
        )
        return [str(row[0]) for row in result.rows if row and row[0] is not None]

    def list_configs_for_table(self, catalog_table_name: str) -> list[PayorConfig]:
        result = self.sql_service.execute(
            self._request(
                f"SELECT {self._SELECT_COLUMNS}\nFROM {self._table_name}\n"
                "WHERE client_active = 1 AND LOWER(sql_pool_table) = :catalog_table_name",
                [SQLParameter(name="catalog_table_name", value=catalog_table_name.lower())],
            )
        )
        return [self._row_to_config(result.columns, row) for row in result.rows]