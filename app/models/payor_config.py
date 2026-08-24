from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExcludedFile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    string_field: str | None = Field(default=None, alias="stringField")
    boolean_field: bool | None = Field(default=None, alias="booleanField")


class RegexFunction(BaseModel):
    pattern: str | None = None
    columns: list[str] = Field(default_factory=list)


class PayorConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payor: str | None = None
    file_type: str | None = None
    database_name: str | None = None
    schema_name: str | None = None
    table_name: str | None = None
    container_name: str | None = None
    raw_delta_table_name: str | None = None
    silver_delta_table_name: str | None = None
    unique_records_delta_table_name: str | None = None
    incremental_records_delta_table_name: str | None = None
    full_load: str | None = None
    silver_schema_name: str | None = None
    sql_pool_table: str | None = None
    natural_keys: list[str] = Field(default_factory=list)
    not_null_condition_column: list[str] = Field(default_factory=list)
    date_standardization_column: list[str] = Field(default_factory=list)
    timestamp_standardization_column: list[str] = Field(default_factory=list)
    filter_conditions: list[str] = Field(default_factory=list)
    float_standardization_column: list[str] = Field(default_factory=list)
    integer_standardization_column: list[str] = Field(default_factory=list)
    decimal_standardization_column: list[str] = Field(default_factory=list)
    client_active: int | None = None
    log_container_name: str | None = None
    log_folder_name: str | None = None
    recon_delta_table_name: str | None = None
    pipeline_history_delta_table_name: str | None = None
    pipeline_error_delta_table_name: str | None = None
    folder_name: str | None = None
    raw_folder_name: str | None = None
    silver_folder_name: str | None = None
    archive_folder_name: str | None = None
    error_folder_name: str | None = None
    nk_null_table_name: str | None = None
    source_folder_name: str | None = None
    master_schema_folder_name: str | None = None
    master_schema_filename: str | None = None
    header_column_names: list[str] = Field(default_factory=list)
    rolling_12_month: str | None = Field(default=None, alias="12_month_rolling")
    col_with_spaces: str | None = None
    rolling_12_month_key: str | None = Field(default=None, alias="12_month_rolling_key")
    ingest_new_columns: str | None = None
    business_condition: str | None = None
    excluded_files: list[ExcludedFile] = Field(default_factory=list)
    delimiter: str | None = None
    excel_tab_name: str | None = None
    rolling_period_years: int | None = None
    regex_function: RegexFunction | None = None
    skiprows: int | None = None
    insert_deactivated_records: str | None = None
    excluded_columns: list[str] = Field(default_factory=list)
    sorting_columns: list[str] = Field(default_factory=list)
    threshold: str | None = None
    mbr_id_col: str | None = None
    delimited_text_file: str | None = None