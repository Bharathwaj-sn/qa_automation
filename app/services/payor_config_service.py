from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.models.databricks_sql import SQLExecutionRequest, SQLParameter
from app.models.payor_config import PayorConfig
from app.services.databricks_sql_service import DatabricksSQLService


class PayorConfigNotFoundError(RuntimeError):
    def __init__(self, payor: str, table_name: str):
        super().__init__(f"No active payor configuration found for '{payor}' and table '{table_name}'.")


class DuplicatePayorConfigError(RuntimeError):
    def __init__(self, payor: str, table_name: str):
        super().__init__(f"Multiple active payor configurations found for '{payor}' and table '{table_name}'.")


class PayorConfigService:
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
            schema=self.settings.payor_config_schema,
            parameters=parameters,
        )

    @staticmethod
    def _row_to_config(columns: list[str], row: list[Any]) -> PayorConfig:
        return PayorConfig.model_validate(dict(zip(columns, row)))

    def get_config(self, payor: str, table_name: str) -> PayorConfig:
        result = self.sql_service.execute(
            self._request(
                f"SELECT {self._SELECT_COLUMNS}\nFROM {self._table_name}\n"
                "WHERE payor = :payor AND table_name = :table_name AND client_active = 1",
                [SQLParameter(name="payor", value=payor), SQLParameter(name="table_name", value=table_name)],
            )
        )
        if not result.rows:
            raise PayorConfigNotFoundError(payor, table_name)
        if len(result.rows) > 1:
            raise DuplicatePayorConfigError(payor, table_name)
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